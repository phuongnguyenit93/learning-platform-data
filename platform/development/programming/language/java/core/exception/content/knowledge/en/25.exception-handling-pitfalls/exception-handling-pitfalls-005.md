# `return` in `finally` or Cleanup Errors Masking the Primary Exception

In Java, `finally` is commonly used to clean up resources. However, a `return`, `throw`, or a `close()` call that throws an exception from inside `finally` can **completely alter the result that the `try` or `catch` block was about to return**. Particularly dangerous is the situation where a business operation has already thrown a diagnostically valuable exception, yet the cleanup operation fails and **masks the original business error**.

This lesson belongs to **Java Core – Exception / Common Pitfalls**, illustrated on **Java 17+**. After studying it, you should be able to answer: when `finally` executes, why `return` in `finally` can swallow an error, which exception is propagated when both `try` and `finally` throw, how `try-with-resources` preserves errors via `Suppressed`, and how to structure cleanup without losing the root cause.

## 1. Summary of the Most Important Principle

**Do not place `return` in `finally`. Do not let a cleanup error accidentally replace the primary error without an explicit policy.** Prefer:

- `try-with-resources` for resources implementing `AutoCloseable`, because Java has a built-in mechanism to retain secondary exceptions via `addSuppressed`.
- `finally` only for performing necessary cleanup, **without `return` or intentionally altering the outcome** of `try`/`catch`.
- If manual cleanup that may throw is unavoidable, decide how to **preserve the primary exception** and **report the cleanup failure**, instead of letting whichever error happens last win by default.
- Preserve `cause` when wrapping exceptions across layers; preserve `suppressed` when multiple independent failures occur during cleanup.

A short summary table:

| Outcome of `try`/`catch` | What happens in `finally` | What the caller observes |
|---|---|---|
| Completes normally | `finally` completes normally | Normal result |
| Preparing to `return x` | `finally` completes normally | Returns `x` |
| Preparing to `return x` | `finally` executes `return y` | Returns **`y`**, replacing `x` |
| Preparing to throw error A | `finally` completes normally | Error **A** continues to be thrown |
| Preparing to throw error A | `finally` throws error B | Error **B** is propagated; A is **not automatically retained** under `Suppressed` in a plain `try-finally` |
| Preparing to `return x` | `finally` throws error B | Caller receives error **B**, not `x` |

The technical rule behind this: if `finally` **completes normally**, the pending completion reason from `try` or `catch` is resumed. If `finally` **completes abruptly** (such as via `return` or `throw`), the new completion reason from `finally` **replaces** the previous one.

## 2. When Does `finally` Actually Run?

In the construct:

```java
try {
    performWork();
} catch (Exception e) {
    handle(e);
} finally {
    cleanup();
}
```

`finally` normally runs after the `try`/`catch` part finishes, even when a `return` or an exception is being propagated. The snippet above is **only an example inside a method**: `performWork()`, `handle(...)`, and `cleanup()` are application-defined methods.

However, you must not claim that `finally` **always** executes under every conceivable condition. Situations such as JVM termination/`Runtime.halt`, the process being killed by the operating system, or a thread never exiting the currently running code can prevent cleanup from executing. `finally` is guaranteed under **normal Java execution control**, not as an absolute fail-safe recovery mechanism against every kind of failure.

Key point to remember: `finally` is not only for the **success** path; it also runs when throwing or preparing to `return`. Therefore, any control flow inside it must be written with great care.

## 3. Why Does `return` in `finally` Override `return` in `try`?

Consider the method:

```java
static int calculate() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

Java has already evaluated `10` and is preparing to return it. Before the method exits, the `finally` block must run; the `return 20` statement creates a **new return outcome**. The final value the caller receives is **20**, not 10.

An even more dangerous case:

```java
static String hideFailure() {
    try {
        throw new IllegalStateException("primary failure");
    } finally {
        return "success";
    }
}
```

The `IllegalStateException` is **swallowed**: the caller receives the string `"success"` instead of the error. There is no `catch` performing business recovery here; just a misplaced `return` statement accidentally erasing the failure signal.

### Standalone Java 17 Example: Two Forms of Overriding

Create `FinallyReturnDemo.java`:

```java
public class FinallyReturnDemo {
    static int overrideValue() {
        try {
            System.out.println("try: return 10");
            return 10;
        } finally {
            System.out.println("finally: return 20");
            return 20;
        }
    }

    static String swallowException() {
        try {
            throw new IllegalStateException("business failed");
        } finally {
            return "apparently successful";
        }
    }

    public static void main(String[] args) {
        System.out.println("result = " + overrideValue());
        System.out.println("result after error = " + swallowException());
    }
}
```

Compile/run:

```bash
javac FinallyReturnDemo.java
java FinallyReturnDemo
```

Standard output:

```text
try: return 10
finally: return 20
result = 20
result after error = apparently successful
```

This example intentionally contains **anti-patterns** to demonstrate language behavior. In production, do not use these two patterns. When compiler warnings are enabled with `javac -Xlint:finally FinallyReturnDemo.java`, the tool may warn that `finally` does not complete normally; treat this warning as a sign that the code needs to be fixed.

Real-world impact: a request might record a "success" status even though order creation logic failed; a batch job might return a default result despite data loss; or an exception might go unrecorded by monitoring systems because the caller never sees it.

## 4. `return` in `try`, Cleanup in `finally` Done Properly

`return` inside `try` is not wrong in itself. The following pattern is completely valid as long as cleanup does not alter the outcome:

```java
static int readValue() {
    try {
        return 10;
    } finally {
        System.out.println("cleanup");
    }
}
```

The caller receives `10`, and `"cleanup"` is printed before the method returns. Here `finally` **completes normally**, so it does not override the `return`.

Standalone program `SafeFinallyReturnDemo.java`:

```java
public class SafeFinallyReturnDemo {
    static int read() {
        try {
            System.out.println("work");
            return 7;
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        int result = read();
        System.out.println("result = " + result);
    }
}
```

Run:

```bash
javac SafeFinallyReturnDemo.java
java SafeFinallyReturnDemo
```

Output:

```text
work
cleanup
result = 7
```

**Important distinction:** the expression after `return` in `try` is evaluated **before** `finally` runs. If you return a reference to a mutable object and `finally` **mutates that same object**, the caller may observe the modified state; that is a mutation effect, **not a `return` statement in `finally` overriding the value**.

Illustrative example:

```java
static java.util.List<String> createList() {
    java.util.List<String> list = new java.util.ArrayList<>();
    try {
        list.add("work");
        return list;
    } finally {
        list.add("cleanup");
    }
}
```

When the caller receives the list, it contains `"work"` and `"cleanup"`; the same object is returned. This pattern can still cause surprises if cleanup modifies the returned object. It is best to keep the result state clearly separated from cleanup logic.

## 5. An Exception from `finally` Can Mask the Primary Exception

Suppose the operation fails first:

```java
try {
    throw new IllegalArgumentException("invalid input");
} finally {
    throw new IllegalStateException("close failed");
}
```

Java will propagate **`IllegalStateException("close failed")`** to the caller. `IllegalArgumentException("invalid input")` is replaced according to control-flow rules. With the manual `try-finally` above, Java **does not automatically** add the first error to `getSuppressed()` of the second error.

That is why a log might show only:

```text
java.lang.IllegalStateException: close failed
```

when in reality validation had failed first. Investigators may spend time fixing the cleanup branch without realizing the original error information was lost.

### Standalone Java 17 Example: Second Error Masks the First

File `CleanupMasksPrimaryDemo.java`:

```java
public class CleanupMasksPrimaryDemo {
    static void doWork() {
        try {
            throw new IllegalArgumentException("primary: bad request");
        } finally {
            throw new IllegalStateException("cleanup: close failed");
        }
    }

    public static void main(String[] args) {
        try {
            doWork();
        } catch (RuntimeException e) {
            System.out.println("observed = "
                    + e.getClass().getSimpleName());
            System.out.println("message = " + e.getMessage());
            System.out.println("cause = " + e.getCause());
            System.out.println("suppressed count = "
                    + e.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac CleanupMasksPrimaryDemo.java
java CleanupMasksPrimaryDemo
```

Output:

```text
observed = IllegalStateException
message = cleanup: close failed
cause = null
suppressed count = 0
```

Because this code **never links the two exceptions** via a cause constructor or `addSuppressed`, the caller cannot recover `IllegalArgumentException` from the received exception. This is not caused by the logging framework truncating the stack; it is information loss in the **exception handling logic**.

This mistake does not happen only when writing `throw` directly in `finally`. A `close()`, `rollback()`, `flush()`, or `release()` method called there can throw a checked/unchecked exception and **override the exception currently being propagated**, if there is no proper preservation mechanism.

## 6. Rules Determining Which Exception Wins

The concept of "completion reason" helps trace complex paths:

1. `try` may complete normally, or via `return`, `break`, `continue`, or `throw`.
2. `catch`, if matched, may change how the error is handled.
3. `finally` runs before the method leaves the construct.
4. If `finally` completes normally, the completion reason from `try`/`catch` is preserved.
5. If `finally` completes abruptly, the new reason **takes precedence** over the pending reason.

Dangerous example:

```java
static boolean work() {
    try {
        throw new IllegalStateException("failure");
    } catch (IllegalStateException e) {
        throw e;
    } finally {
        return true;
    }
}
```

This is an **illustrative method**, not to be used. Even though `catch` executed `throw e`, `finally` still returns `true` and **cancels the rethrown exception**.

Similarly:

```java
static int read() {
    try {
        return 42;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

The caller receives the exception, **not the number 42**.

**Conclusion:** do not assume an earlier `return`/`throw` is always the final outcome. You must check whether `finally` can execute competing control flow or throw an error.

## 7. Why Is `try-with-resources` Usually the Best Solution?

For `AutoCloseable` resources, Java provides the syntax:

```java
try (Resource resource = open()) {
    doWork(resource);
}
```

This is an illustrative snippet requiring a `Resource` type and the two corresponding methods. Java closes the resource upon exiting the scope. If the `try` body throws error A and `close()` throws B, **A remains the primary**, and B is placed in `A.getSuppressed()`. If only closing fails, B becomes the primary. Multiple resources are closed in **reverse order of declaration**.

Key distinction from manual `finally`: a `throw` or `return` in `finally` can **replace** the pending error/result. The lesson on *manual resource closing missing failure branches* goes deeper into partial open failures, closing multiple resources, ownership, and testing all cleanup paths.

## 8. Standalone Java 17 Example: Primary and Suppressed When Closing Two Resources

Create `SuppressedOnCloseDemo.java`:

```java
import java.io.IOException;

public class SuppressedOnCloseDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    static void work() throws Exception {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            throw new IllegalArgumentException("body failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception e) {
            System.out.println("primary = "
                    + e.getClass().getSimpleName()
                    + ": " + e.getMessage());

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed = "
                        + suppressed.getClass().getSimpleName()
                        + ": " + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac SuppressedOnCloseDemo.java
java SuppressedOnCloseDemo
```

Output:

```text
primary = IllegalArgumentException: body failed
suppressed = IOException: close second
suppressed = IOException: close first
```

Reading the behavior:

1. The `try` body throws `IllegalArgumentException("body failed")`; this is the **primary exception**.
2. Java closes `second` before `first`.
3. Both `close()` calls throw `IOException`.
4. Instead of losing the `try` body error, Java attaches both `close()` errors to the **suppressed array** of the primary.
5. The caller receives the primary and can inspect the cleanup errors via `e.getSuppressed()`.

In logs produced by `printStackTrace()`, you will see indented `Suppressed:` branches beneath the main exception. That does not mean a close error is unimportant; it simply reflects its **secondary role in that specific failure flow**.

### When the `try` Body Succeeds but `close()` Fails

File `CloseAsPrimaryDemo.java`:

```java
import java.io.IOException;

public class CloseAsPrimaryDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    static void work() throws Exception {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            System.out.println("body: success");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception e) {
            System.out.println("primary = " + e.getMessage());
            for (Throwable extra : e.getSuppressed()) {
                System.out.println("suppressed = " + extra.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac CloseAsPrimaryDemo.java
java CloseAsPrimaryDemo
```

Output:

```text
body: success
primary = close second
suppressed = close first
```

Because there was no error in the `try` body, the first close in **reverse closing order** (`second`) produces the primary exception. The error closing `first` becomes a suppressed exception on that primary.

Do not interpret "primary" as "business error" in every case. **Primary is the exception prioritized for propagation according to the rules of the executing construct**. If the `try` body completes, a resource-closing error may be the exact error that needs handling.

## 9. How Do `Caused by` and `Suppressed` Differ?

It is easy to confuse these two parts when reading a stack trace:

| Mechanism | API | Meaning |
|---|---|---|
| **Cause** | `getCause()`, constructor taking `Throwable cause` | An earlier exception that gave rise to the current exception, typically in a context-wrapping chain |
| **Suppressed** | `getSuppressed()`, `addSuppressed(...)` | An additional error retained while already handling another error, e.g., closing a resource after the `try` body has already failed |

An exception can have **one cause** and **multiple suppressed exceptions**. When `try-with-resources` encounters body failure A and close failure B, B is placed in **A's suppressed list**, not **A's cause**; cleanup B did not cause body A to fail earlier.

Example stack trace (paths/line numbers are **illustrative**, not guaranteed output of the programs above):

```text
java.lang.IllegalStateException: Unable to write report
    at app.ReportService.generate(ReportService.java:50)
    Suppressed: java.io.IOException: Unable to close stream
        at app.ReportWriter.close(ReportWriter.java:18)
        ... 1 more
Caused by: java.io.IOException: Unable to write data
    at app.ReportWriter.write(ReportWriter.java:12)
    ... 1 more
```

How to read it correctly:

- The outermost exception describes the failed operation.
- `Caused by` indicates the underlying cause that was wrapped.
- `Suppressed` records an additional error that occurred during cleanup.
- `... 1 more` is the count of trailing duplicate stack frames elided relative to the enclosing trace; it is **not** another exception.

If a plain `finally` throws a new exception and loses the first error, the caller's stack trace may **contain no information about the replaced error**. In that case, you cannot expect `Caused by` or `Suppressed` to appear on their own if the code never established them.

## 10. Manual Cleanup: Preserve the Primary Error with an Explicit Policy

Not every resource implements `AutoCloseable`, and sometimes cleanup has special requirements. If you must use a manual `finally`, do not let a cleanup error automatically overwrite an earlier error.

Conceptual flow:

```text
Execute work
    |
    +-- succeeds ---------------------+
    |                                 |
    +-- fails: save primary           |
                                      v
                                 Run cleanup
                                      |
                         +------------+------------+
                         |                         |
                    cleanup OK                cleanup fails
                         |                         |
                 propagate old             if primary exists:
                 result/error              attach cleanup as suppressed
                                           if no primary exists:
                                           propagate cleanup failure
```

Standalone Java 17 example applied to a specific checked exception type. File `ManualCleanupPreserveDemo.java`:

```java
import java.io.IOException;

public class ManualCleanupPreserveDemo {
    static void work() throws IOException {
        throw new IOException("write failed");
    }

    static void cleanup() throws IOException {
        throw new IOException("close failed");
    }

    static void run() throws IOException {
        IOException primary = null;

        try {
            work();
        } catch (IOException e) {
            primary = e;
            throw e;
        } finally {
            try {
                cleanup();
            } catch (IOException closeError) {
                if (primary != null) {
                    primary.addSuppressed(closeError);
                } else {
                    throw closeError;
                }
            }
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException e) {
            System.out.println("primary = " + e.getMessage());

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println(
                        "suppressed = " + suppressed.getMessage());
            }
        }
    }
}
```

Commands:

```bash
javac ManualCleanupPreserveDemo.java
java ManualCleanupPreserveDemo
```

Output:

```text
primary = write failed
suppressed = close failed
```

The code preserves `IOException("write failed")` to propagate to the caller while attaching the close error to `getSuppressed()`. If `work()` succeeds and `cleanup()` fails, the `primary == null` branch throws the cleanup error as the primary error.

**Important limitation:** this example only catches **`IOException`** per the contract of `work()` and `cleanup()`. If another `RuntimeException` or `Error` occurs in `work()`, and then `cleanup()` throws `IOException`, the `finally` block can still mask the exception that was not of the saved type. Handling every `Throwable` manually in full generality is complex, requiring consideration of `Error`, disabled suppression, self-suppression, and cancellation policies. Therefore, **prefer `try-with-resources`** whenever possible rather than copying a narrow pattern everywhere.

If cleanup has multiple steps, consider how each step throws exceptions and avoid letting a failure in the first step skip all remaining steps when continued cleanup is required.

## 11. How Calling `close()` in `finally` Can Lose Information

Classic pattern:

```java
Resource resource = acquire();

try {
    use(resource);
} finally {
    resource.close();
}
```

This is an **illustrative code snippet**, assuming `Resource`, `acquire`, `use`, and `close` already exist. If `use` throws error A and `close` throws error B, **B can replace A**, because `finally` completes with `throw B`. A plain construct **does not automatically create suppressed exceptions**.

If `resource` is `AutoCloseable`, use:

```java
try (Resource resource = acquire()) {
    use(resource);
}
```

The compiler generates the resource cleanup and suppression logic according to the `try-with-resources` contract. This is both shorter and reduces the risk of losing the primary error.

Several other issues with manual cleanup:

- `resource` might not be initialized yet, leading to a `NullPointerException` in `finally` if not checked.
- If the resource is opened **outside** `try`, an error before entering `try` can prevent `finally` from running.
- Multiple resources may need to be closed in **reverse order** of acquisition.
- Close operations are not necessarily idempotent; closing twice can cause side effects or another error.
- Cleanup should avoid calling external services for too long, because when a primary error occurs the system may already be overloaded.

`try-with-resources` handles resource management issues well under Java's contract, but **does not automatically guarantee** that a `close()` always succeeds or that all business side effects have been rolled back.

## 12. Distinguishing Resource Cleanup, Transaction Rollback, and Business Recovery

Some operations called in `finally` are more than just `close()`:

```java
try {
    updateDatabase();
} finally {
    rollbackIfNeeded();
}
```

This is an illustrative snippet. If `updateDatabase()` throws an error and `rollbackIfNeeded()` also throws, the first cause **may be masked**. Yet completely ignoring a rollback error can also be dangerous: the transaction or connection may be left in an indeterminate state.

Proper handling depends on the contract of the transaction manager and library:

- Preserve the cause of the first failure when it is the key diagnostic information.
- Attach or record additional cleanup/rollback errors, clearly distinguishing their consequences.
- If a rollback failure is more severe, you may need **a composite error policy**. That decision must be explicit, not an accidental side effect of `finally`.
- Do not proceed as if successful when the transaction or cleanup may have failed.
- Do not hand-roll transaction logic if a framework/transaction manager already provides appropriate management boundaries and error rules.

Some operations require **detecting up front** that they can throw checked exceptions, such as `IOException` or `SQLException`. Putting these methods in `finally` does not remove the obligation to declare/catch exceptions. If you carelessly catch too broadly and log generically without handling, errors still risk getting lost.

## 13. Exception in `catch` Masked by `finally`

It is not only exceptions originating from `try` that get masked. `catch` can translate or rethrow an exception, and then `finally` throws another error:

```java
try {
    perform();
} catch (Exception e) {
    throw new IllegalStateException("operation failed", e);
} finally {
    riskyCleanup();
}
```

This is an illustrative snippet. If `riskyCleanup()` throws exception B, the caller may see only B even though `catch` carefully preserved the cause from `perform()`.

This leads to a strong rule: **properly wrapping an exception is still not enough if the final cleanup path can override the wrapped exception**. Inspect `finally`, resource-closing hooks, request-completion callbacks, interceptors, and outer-layer rollback steps as well.

Conversely, if cleanup does not throw, the wrapper created in `catch` will preserve the cause as designed.

## 14. Logging: Why "Log and Rethrow" Does Not Replace Exception Preservation

Some people try to avoid losing errors by doing:

```java
try {
    perform();
} catch (Exception e) {
    logger.error("business failed", e);
    throw e;
} finally {
    cleanup();
}
```

This is an integration snippet where `logger` is defined in the real environment. If `cleanup()` throws an error, the caller may still receive only the cleanup error. Logging in `catch` may retain partial information, but:

1. It does not preserve the **`Throwable` object and its cause/suppressed chain** in the exception flow received by the caller.
2. It can produce duplicate error logs if an outer layer also logs the cleanup error.
3. If the logging system fails to emit the event, the original information can still be lost.
4. It is no substitute for making the right decision about **primary** and **secondary failures**.

A better strategy is to **preserve the exception chain**, then let the responsible boundary report a complete error event (according to policy). `Throwable.printStackTrace()` and logger overloads that accept a `Throwable` will display both cause and suppressed exceptions when configured properly.

SLF4J-style integration logging example:

```java
logger.error("Failed to complete operation={}, requestId={}",
        operation, requestId, failure);
```

This is an illustrative snippet only, requiring a compatible logger and existing variables. Pass the **`Throwable`** rather than only `failure.getMessage()` so the stack trace and suppressed exceptions are not lost. Avoid exposing sensitive data in messages and stack traces to end users.

## 15. Testing: Do Not Check Only the Outermost Exception Message

When writing tests for cleanup handling, verify both the **primary cause** and **suppressed exceptions**, rather than only checking that `assertThrows(...)` throws some error.

JUnit 5 example (integration snippet, not standalone because it requires the testing library):

```java
IOException failure = assertThrows(IOException.class,
        () -> runOperation());

assertEquals("write failed", failure.getMessage());
assertEquals(1, failure.getSuppressed().length);
assertEquals("close failed",
        failure.getSuppressed()[0].getMessage());
```

`runOperation()` is an application-defined method. Similarly, for wrapped errors, verify `getCause()` with the appropriate type/message. These assertions catch regressions when someone replaces `try-with-resources` with a manual `try-finally` or adds a `return` to cleanup.

A practical test suite should cover these scenarios:

| Main work | Cleanup | Expectation |
|---|---|---|
| Succeeds | Succeeds | Returns success result |
| Fails with A | Succeeds | Propagates A |
| Succeeds | Fails with B | Reports B |
| Fails with A | Fails with B | With TWR: A primary, B suppressed |
| Fails with A | Two cleanups fail with B, C | With TWR: A primary, B/C suppressed in close order |
| `return` from `try` | Cleanup completes normally | Preserves return value |
| `return` from `try` | Cleanup throws B | Reports B, does not return value |
| Error from `try` | `finally` contains `return` | Anti-pattern: error swallowed; test must detect and eliminate it |

Tests for **closing order** should be designed using mock/fake resources with deterministic output. Avoid relying on sleeps or external state when you only want to verify `finally` semantics.

## 16. `finally` in Asynchronous Tasks Follows the Same Rules

A `Callable` or `Runnable` running in an `ExecutorService` can also have a buggy `finally`:

```java
java.util.concurrent.Callable<String> task = () -> {
    try {
        throw new IllegalStateException("task failed");
    } finally {
        return "done";
    }
};
```

This is an illustrative Java snippet, with `Callable` using its fully qualified name. If submitted to an executor, `Future.get()` can receive `"done"` as a **successful result** even though the main logic threw `IllegalStateException`. Because `finally` returns a value, the exception is swallowed **before the executor can record the failure**.

Conversely:

```java
java.util.concurrent.Callable<String> task = () -> {
    try {
        throw new IllegalStateException("task failed");
    } finally {
        throw new IllegalArgumentException("cleanup failed");
    }
};
```

If the task is submitted normally, `Future.get()` will throw `ExecutionException` containing **`IllegalArgumentException`** from cleanup as its cause; the original `IllegalStateException` has been replaced.

In `CompletableFuture`, a callback throwing an error from cleanup can cause the stage to complete exceptionally. Callers observing via `join()` typically see a `CompletionException` whose cause is the propagated error. Do not assume async wrappers automatically recover a primary exception lost in `finally` logic.

Broadly applicable rule: **do not use `return` in `finally` inside a callable**, and **preserve secondary exceptions via suppression or an explicit handling contract** before letting the task finish. This is even more critical when errors cross multiple threads and you rarely have a chance to inspect logs on the original worker.

## 17. `finally` and Interrupt/Cancellation: Do Not Accidentally Break Stop Signals

In multithreaded applications, cleanup may run when a thread receives `InterruptedException`:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    cleanup();
}
```

This is an illustrative snippet inside a `void` method, with `queue` and `cleanup()` already declared. The `cleanup()` method needs an appropriate contract so it does not throw unexpected errors and mask interrupt handling. If cleanup performs an interruptible wait operation, the restored interrupt flag can cause the new wait call to immediately throw `InterruptedException`; design shutdown and cleanup paths deliberately.

For a cancelled `Future`, cancellation does not guarantee cleanup finishes immediately. If a worker unexpectedly swallows an exception via `return` in `finally`, execution state and coordinator state can diverge from expectations. Separate **the stop request**, **the worker exiting**, and **whether resources have been cleaned up**.

Do not log every `InterruptedException` as `ERROR` if it is an expected shutdown signal, but also do not discard a serious cleanup failure just because the thread is stopping.

## 18. Common Misconceptions

### "`finally` is for cleanup, so it's okay to `return` inside it"

False. `return` in `finally` replaces any pending `return`/`throw`, causing the caller to receive the wrong result or lose the exception. `finally` should focus on cleanup **without altering control flow**.

### "Once I `throw e` in `catch`, the caller is guaranteed to see `e`"

False if `finally` completes abruptly via `return` or a new `throw`. You must inspect the entire handling path.

### "Whichever exception happens first will automatically appear in `Caused by`"

Incorrect. Cause must be set via a constructor/`initCause` or equivalent mechanism. Two exceptions occurring sequentially in `try` and `finally` **do not automatically form a cause relationship**.

### "An exception in `finally` will automatically be suppressed onto the original exception"

Incorrect for **plain manual `try-finally`**. `try-with-resources` has a suppression mechanism for `close()` errors by contract, whereas hand-written `finally` requires an explicit policy.

### "A suppressed exception is an error that can be ignored"

Not necessarily. Errors closing streams/transactions can cause data loss, connection leaks, or hide cleanup consequences. `Suppressed` only denotes a role in error propagation, not severity.

### "Having an empty `getSuppressed()` means cleanup succeeded"

You cannot infer that. The application may have used `try-finally` incorrectly and lost the error, or failed to record secondary exceptions; logs could also be truncated. Seeing `getSuppressed().length == 0` alone does not prove cleanup was safe.

### "Adding `catch (Exception e)` around every cleanup is enough"

If you catch and stay silent, the cleanup failure disappears. If you always throw a new exception, it can mask the primary error. You need a clear policy: propagate the cleanup failure when there is no primary, or record it as suppressed when a primary exists, and consider any side effects that need separate handling.

### "Manually closing resources always gives better control"

For `AutoCloseable` resources, `try-with-resources` is usually safer, shorter, and more compliant with exception rules. Rewriting manual logic makes it easy to get close order wrong and lose suppressed exceptions.

### "Seeing `ExecutionException` in `Future.get()` tells you the root error"

`ExecutionException` is usually just a wrapper around the worker's error. If the worker lost the primary exception due to cleanup, `getCause()` only shows **the error that remained after `finally` finished**, and cannot automatically recover a swallowed error.

## 19. Checklist for Reviewing a `finally` Block

When reading code, check in order:

1. Does `finally` contain **`return`**, an explicit `throw`, or unusual control-flow logic?
2. Is there any cleanup method that **can throw a checked or unchecked exception**?
3. If the `try` body throws A and cleanup throws B, **what will the caller see**? Is A still preserved via cause/suppressed?
4. Does the resource implement `AutoCloseable` so it can be replaced with `try-with-resources`?
5. Are there multiple resources? Is the closing order right, and could subsequent close errors be lost?
6. If there is **no primary error**, is the cleanup error reported properly (not swallowed)?
7. If cleanup fails, is there a risk to transactions, files, sockets, locks, or written data?
8. Does logging print the **full `Throwable`** including suppressed exceptions at the right boundary, avoiding duplicate log-and-rethrow?
9. In async code, are post-cleanup exceptions properly recorded in `Future`/`CompletableFuture`?
10. Do tests cover **simultaneous `try`-body failure and cleanup failure**, rather than testing only the happy path?

## 20. Design Guidance by Scenario

| Scenario | Usually appropriate choice |
|---|---|
| File, stream, or JDBC resource with `AutoCloseable` | **`try-with-resources`**; inspect both cause and suppressed |
| Cleanup cannot throw and is very short | Plain `finally`, without `return`/`throw` |
| Cleanup can throw a checked exception, but resource is not `AutoCloseable` | Write a primary-preserving policy; consider an `AutoCloseable` adapter |
| Cleanup is more critical or creates an independent incident | Define explicit precedence/aggregation and alerting, do not rely on accidental "last throw wins" |
| Method must return a result, yet cleanup may fail | Decide whether the result remains valid when cleanup fails; retain error info per contract |
| Task executor/`Future` | Avoid `return` in `finally`; do not let cleanup accidentally mask worker failure |
| Multi-layer pipeline | Preserve cause and suppressed, log at the responsible boundary |

**Conclusion:** `finally` takes precedence in the completion path of `try`/`catch`, so a `return` or exception in `finally` can **override the result and lose the primary error**. Use `try-with-resources` for eligible resources, perform only safe cleanup in `finally`, and when multiple exceptions occur, explicitly preserve both **primary** and **suppressed** rather than letting the last error accidentally dictate the story seen by the caller and logs.
