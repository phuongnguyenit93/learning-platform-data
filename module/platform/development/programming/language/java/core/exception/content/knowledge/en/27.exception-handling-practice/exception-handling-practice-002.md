# Comparing Local Exception Handling with Propagation Using `throws` in Java

In Java, when a method encounters an error, programmers generally have two main approaches: **catch and handle the exception locally** using `try`–`catch`, or **let the exception propagate to the caller** and, for checked exceptions, declare that possibility with `throws`. Both approaches are valid in the appropriate context, but they carry different responsibilities. Choosing the wrong one can lose diagnostic information, mask a failure as a "success," force a low-level layer to know about high-level business policy, or cause resources not to be cleaned up properly.

The most important question is not "can I write a `catch` here?" but rather:

> **Does the current layer have enough information and authority to handle the error properly?**

If there is a recovery strategy permitted by the contract and the state remains valid, handling locally may be appropriate. If not, you should **delegate responsibility** by letting the exception propagate upward or translating it into a more appropriate exception while **preserving `cause`**. `throws` is not an "error-fixing" mechanism; it is part of the method contract for checked exceptions that may escape.

## 1. Two Approaches and Control Flow Diagram

### Handling Locally

A method catches the exception and implements the handling policy itself:

```java
String displayName(String raw) {
    try {
        return normalizeName(raw);
    } catch (InvalidNameException exception) {
        return "Unknown"; // Only correct if this fallback is allowed by the contract.
    }
}
```

This is **non-standalone illustrative code**; `normalizeName(...)` and `InvalidNameException` must be defined. When `catch` completes normally and returns a fallback, the method no longer passes the caught exception to the caller. This is useful when `Unknown` is genuinely a valid result, but dangerous if the application is processing a payment, authentication, or a data update that must succeed.

### Propagating to the Caller

The method lets the checked exception escape and declares it in the signature:

```java
String loadConfiguration() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.properties"));
}
```

This is an **illustrative method snippet** that must be placed inside a Java class. It does not decide whether to use a default configuration, try another source, notify the user, or abort startup. That choice belongs to a caller with sufficient context.

```text
Low-level layer: load()
       |
       +-- read succeeds ------------------> return data
       |
       +-- IOException
                |
                +-- A: catch here
                |        |
                |        +-- valid recovery ---> return normal result
                |        +-- cannot recover ---> rethrow / translate error
                |
                +-- B: throws IOException
                         |
                         v
                   Caller decides
                         |
                  +------+------+
                  |             |
                 catch       throws further
                  |             |
              handle at      higher layer
              boundary
```

A call chain can have multiple consecutive `throws` layers. An exception only stops propagating when a handler actually handles it, or when it reaches an appropriate execution boundary without a handler. Do not assume that `throws` creates an implicit `catch`.

## 2. Quick Comparison Table

| Criterion | Local handling with `try`–`catch` | Propagation with `throws` |
| --- | --- | --- |
| Primary responsibility | Defines and executes the handling policy at the current layer | Transfers handling responsibility to the caller |
| Does the exception leave the method? | No, **if** fully handled and not rethrown | Possibly, if the execution path throws that exception |
| Signature impact | Does not necessarily need to declare an exception that is completely handled | Escaping checked exceptions usually must appear in `throws` or a suitable supertype |
| Requires fallback/retry? | Only when that is a genuinely valid policy | No need to decide on a fallback at the low-level layer |
| Preserving stack/cause | Must be careful when logging, wrapping, or rethrowing | Original exception continues propagating upward unless replaced by a wrapper |
| Low-level reusability | Can be poor if the low-level layer enforces UI/API policy | Often better when higher layers decide based on context |
| Suitable for | Immediately recoverable errors, boundary validation, local cleanup | I/O, infrastructure errors, or cases where the current layer lacks authority to handle |
| Notable risks | Swallowing errors, returning false success, partially modified state | Exposing low-level exceptions in an inappropriate API or forgetting the final handler |

The two approaches are **not mutually exclusive**. A method can catch a low-level exception and throw a **new exception appropriate to the abstraction layer**; or catch a recoverable error type while letting another type propagate upward. Good design often combines them across clear boundaries.

## 3. How `throw` Differs from `throws`

They are easy to confuse because their names look similar:

```java
void read() throws java.io.IOException {
    throw new java.io.IOException("read failed");
}
```

This is an **illustrative Java method** placed inside a class. In this snippet:

- `throw expression;` is an **executable statement** that makes control flow exit the normal branch with a `Throwable` object.
- `throws IOException` is a **clause in the signature** declaring a checked exception that may escape the method.
- Writing `throws` does not create or throw an error by itself. A method declaring `throws IOException` can still return a normal result.
- Writing `throw new IOException(...)` inside a method generally requires either catching the error or declaring `throws IOException` (or an allowed supertype) because `IOException` is a checked exception.
- For unchecked exceptions such as `IllegalArgumentException`, `IllegalStateException`, or `NullPointerException`, Java **does not require** declaring `throws`, though it can be declared for documentation purposes.

`throws` is also not a statement telling the JVM to "ignore the error." The exception can still propagate back through the call stack, execute `finally` blocks according to Java rules, and reach the nearest matching handler.

## 4. Checked vs. Unchecked Exceptions: Impact on Choice

### Checked Exceptions

Classes that extend `Exception` but not `RuntimeException` are generally **checked exceptions**, for example `IOException`, `SQLException`, `InterruptedException`. The compiler checks that they are appropriately **caught** or **declared/propagated**.

```java
void load() throws java.io.IOException {
    readFromDisk();
}
```

This is illustrative code; `readFromDisk()` must be a method declared in the application. Without a `try`–`catch` handling `IOException`, the `throws` signature informs the caller of that risk.

### Unchecked Exceptions

`RuntimeException` and its subclasses are unchecked exceptions. These errors can propagate upward **without `throws`** in the signature:

```java
int parsePositive(String input) {
    int value = Integer.parseInt(input);
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
```

This is an illustrative method placed in a class. Both `NumberFormatException` (from `parseInt`) and `IllegalArgumentException` are unchecked. The author is not forced by the compiler to add `throws`, but callers can still catch them when an appropriate handling policy exists.

**Do not equate checked with "recoverable" and unchecked with "must not be caught."** Choosing where to handle depends on **the contract, state recoverability, and business policy**, not just the language category. For instance, `NumberFormatException` may be an expected input error at a UI boundary; whereas `IOException` may be an unrecoverable failure in a process that must terminate the request.

## 5. Java 17+ Example: Same Error, Three Ways to Divide Responsibility

Create the file **`LocalVsThrowsDemo.java`**:

```java
import java.io.IOException;

public class LocalVsThrowsDemo {
    static String fetch(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("storage unavailable");
        }
        return "REAL_DATA";
    }

    static String handleLocally(boolean fail) {
        try {
            return fetch(fail);
        } catch (IOException exception) {
            return "CACHED_DATA"; // Assumes fallback is valid for the screen.
        }
    }

    static String propagate(boolean fail) throws IOException {
        return fetch(fail);
    }

    static String translate(boolean fail) {
        try {
            return fetch(fail);
        } catch (IOException original) {
            throw new IllegalStateException("cannot assemble report", original);
        }
    }

    static String handleAtBoundary(boolean fail) {
        try {
            return propagate(fail);
        } catch (IOException exception) {
            return "REQUEST_FAILED:" + exception.getMessage();
        }
    }

    public static void main(String[] args) {
        System.out.println("localSuccess=" + handleLocally(false));
        System.out.println("localFallback=" + handleLocally(true));
        System.out.println("propagateSuccess=" + handleAtBoundary(false));
        System.out.println("boundaryFailure=" + handleAtBoundary(true));

        try {
            translate(true);
        } catch (IllegalStateException exception) {
            System.out.println("wrapper="
                    + exception.getClass().getSimpleName());
            System.out.println("cause="
                    + exception.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + exception.getCause().getMessage());
        }
    }
}
```

Run on Java 17 or later:

```bash
javac --release 17 LocalVsThrowsDemo.java
java LocalVsThrowsDemo
```

Output:

```text
localSuccess=REAL_DATA
localFallback=CACHED_DATA
propagateSuccess=REAL_DATA
boundaryFailure=REQUEST_FAILED:storage unavailable
wrapper=IllegalStateException
cause=IOException
causeMessage=storage unavailable
```

Analysis of the three policies:

1. `handleLocally` catches `IOException` and returns `CACHED_DATA`. The outcome is a **normal completion**. This is only correct when cached data is acceptable and the application distinguishes the data source if needed.
2. `propagate` declares `throws IOException` and does not decide the response itself. `handleAtBoundary` is where the error is turned into a request failure state. The string `"REQUEST_FAILED:..."` is only for easy observation in the demo; real systems should use safe result types or error codes rather than string parsing.
3. `translate` catches `IOException` and throws `IllegalStateException` with a **cause**. It changes the semantic layer without discarding the underlying technical error. This is not "handled" in the sense of recovery: the caller still sees a failure.

The example uses `boolean fail` to produce a **deterministic** error without depending on real files or networks. A test involving a real storage system will need dedicated environment data and isolation.

## 6. What Counts as Proper Local Handling?

A `catch` branch cannot be considered recovery just because it logs:

```java
try {
    savePayment();
} catch (Exception exception) {
    System.out.println(exception.getMessage());
}
// Code below still returns success: dangerous.
```

This is illustrative code, not a standalone program. If `savePayment()` fails and the code continues to send a "payment succeeded" notification, the system hides a real failure.

**Valid local handling** must have a clear contract. For example:

- Input validation: reject malformed values, keep state unmodified, and return a specific error.
- Optional data: return a permitted default value while ensuring the caller understands it is a fallback when necessary.
- Controlled retry: only retry transient errors, with limits and checks for side effects/idempotency.
- An independent failed record in a batch: mark that record as failed and process the next record, if record states are isolated.

**It is inappropriate to swallow locally** if an internal invariant is found to be broken, data has been partially updated, or an external operation may have occurred with an unknown outcome.

A useful decision table:

| Question | If "yes" | If "no" |
| --- | --- | --- |
| Does this layer understand the exact error type and impact? | Can classify to handle | Propagate to a layer with sufficient context |
| Is the state valid after recovery? | Can return fallback/retry per contract | Stop the operation and propagate failure |
| Does it have authority to decide business policy? | Local handling may be reasonable | Do not turn the error into a result yourself |
| Can duplicate side effects be ruled out? | May consider retry | Do not retry automatically |
| Does the caller need to know a fallback occurred? | Return appropriate metadata/result type | Can return a normal value if the contract allows |

If recovering locally, log/record metrics at an appropriate level for an expected situation. Do not wrap an entire method in a broad `catch` just so the program "never throws an exception."

## 7. Propagating with `throws` Separates Policy from Mechanism

A low-level module should focus on **execution**: reading files, calling a database, sending requests, or transforming data. Higher layers can decide:

- During application startup: failure to read required configuration may cause startup to **fail**.
- When displaying a non-essential feature: failure to read an optional source may fall back to cache.
- During batch processing: failure of an independent input may be recorded in that record's error report.
- When handling an API request: an I/O error may become a stable error response while the stack trace is written to internal logs.

If a repository always catches `IOException` and returns an empty string, it **enforces a fallback policy on all layers**, even though service A needs to stop while service B can recover. Letting the exception propagate via `throws` improves low-level reusability and places policy where the decision belongs.

However, `throws IOException` from the repository layer leaking through every public API can expose **technical details** to the business layer. In that case, you can **translate the exception** at an appropriate boundary to balance reusability with API semantics.

## 8. Exception Translation: Catching Without Recovering

There are three kinds of actions inside a `catch`:

1. **Recover:** handle the error successfully and return a valid result.
2. **Rethrow:** `throw error;` to preserve the exact exception object and existing cause chain.
3. **Translate/wrap:** `throw new DomainException("context", error);` to provide a higher-level error type while preserving the cause.

Illustrative application snippet:

```java
try {
    repository.load(customerId);
} catch (java.io.IOException original) {
    throw new CustomerLoadException(
            "Cannot load customer " + customerId, original);
}
```

This snippet requires `repository`, `customerId`, and a `CustomerLoadException` class with a constructor taking `(String, Throwable)`. It is **exception translation**, not recovery. The caller must still decide whether to report failure or handle the new error type.

**Avoid this mistake:**

```java
catch (java.io.IOException original) {
    throw new IllegalStateException(original.getMessage());
}
```

This only copies the message; it does not set `getCause()` to `original`, losing the `IOException` trace, original stack, deeper causes, and suppressed exceptions.

When translating exceptions, the message should provide **operation context** without repeating or exposing all technical data. You can log the `Throwable` itself at an appropriate logging boundary instead of only `getMessage()`.

## 9. Controlling Checked Exceptions Across Multiple Layers

Suppose each method has a clear responsibility:

```java
void lowLevel() throws java.io.IOException {
    throw new java.io.IOException("read failed");
}

void service() throws java.io.IOException {
    lowLevel();
}

void requestBoundary() {
    try {
        service();
    } catch (java.io.IOException exception) {
        reportFailure(exception);
    }
}
```

This is an **illustrative set of methods inside a class**, depending on `reportFailure(...)`. When `lowLevel()` throws `IOException`, `service()` does not handle it and lets the error propagate via its `throws` signature. `requestBoundary()` catches it and reports the failure according to its policy. Declaring `throws` on `service()` does not mean `service()` did anything to fix the error.

What matters for **checked exceptions**: if a method calls code that can throw a checked exception and cannot catch all escaping cases, its signature must allow the corresponding exception. In overriding/interface implementation, an overriding method **must not broaden the set of checked exceptions** beyond the parent method's contract. Thus, the API can guide where exceptions should be translated or use a defined domain exception type.

For **unchecked exceptions**, signatures are not required to declare them. A method may write `throws IllegalStateException` to aid documentation, but that does not guarantee that only this type can be thrown.

## 10. Java 17+ Example: Low-Level Propagates Error, Outer Layer Handles and Cleans Up Resources

In many programs, the issue is not only **catching vs. throwing**, but also **cleaning up resources** when an exception propagates. `try-with-resources` allows closing the resource right where it is owned even when error-handling responsibility lies at a higher layer.

Create the file **`PropagationAndCleanupDemo.java`**:

```java
import java.io.IOException;

public class PropagationAndCleanupDemo {
    static final class DemoResource implements AutoCloseable {
        private final boolean failClose;
        int closeCount;

        DemoResource(boolean failClose) {
            this.failClose = failClose;
        }

        String read(boolean failRead) throws IOException {
            if (failRead) {
                throw new IOException("read failed");
            }
            return "OK";
        }

        @Override
        public void close() throws IOException {
            closeCount++;
            if (failClose) {
                throw new IOException("close failed");
            }
        }
    }

    static String readAndPropagate(
            DemoResource resource, boolean failRead) throws IOException {
        try (resource) {
            return resource.read(failRead);
        }
    }

    static void observe(String label, boolean failRead, boolean failClose) {
        DemoResource resource = new DemoResource(failClose);
        try {
            String result = readAndPropagate(resource, failRead);
            System.out.println(label + " result=" + result);
        } catch (IOException error) {
            System.out.println(label + " primary=" + error.getMessage());
            System.out.println(label + " suppressed="
                    + error.getSuppressed().length);
            if (error.getSuppressed().length > 0) {
                System.out.println(label + " cleanup="
                        + error.getSuppressed()[0].getMessage());
            }
        }
        System.out.println(label + " closes=" + resource.closeCount);
    }

    public static void main(String[] args) {
        observe("success", false, false);
        observe("readFailure", true, false);
        observe("closeFailure", false, true);
        observe("bothFailure", true, true);
    }
}
```

Compile and run:

```bash
javac --release 17 PropagationAndCleanupDemo.java
java PropagationAndCleanupDemo
```

Output:

```text
success result=OK
success closes=1
readFailure primary=read failed
readFailure suppressed=0
readFailure closes=1
closeFailure primary=close failed
closeFailure suppressed=0
closeFailure closes=1
bothFailure primary=read failed
bothFailure suppressed=1
bothFailure cleanup=close failed
bothFailure closes=1
```

Explanation:

- `readAndPropagate(...)` retains responsibility for **closing the resource** where its scope is opened using `try (resource)` and lets `IOException` propagate via `throws`. It does not need to decide how outer layers display or handle the error.
- `observe(...)` acts as the caller layer that decides how to report the error; in the demo it prints to the console. Real applications should turn the state into a clear result and log with context.
- When the `try` body fails but `close()` succeeds, the read error propagates normally.
- When only `close()` fails, the resource-closing exception escapes as the primary error. Do not treat the operation as "succeeded" if closing the resource is important for data correctness.
- When **both `read()` and `close()` fail**, the read error is the primary exception and the close error is kept in `getSuppressed()`. Thus, handling at the outer layer **does not lose the original cause**.
- `closeCount=1` in all cases shows that `try-with-resources` cleans up the resource on both success and failure paths.

The code uses `try (resource)` with an effectively final resource variable, supported in Java 9+. It is a resource cleanup technique, **not** a mechanism to roll back all business changes made before the exception.

## 11. Distinguishing `finally`/`try-with-resources` from Error Handling

When letting an exception propagate, Java still executes matching `finally` blocks along the exit path. However, if `finally` itself throws another exception or executes `return`, it can **replace** the propagating exception:

```java
try {
    throw new IllegalArgumentException("original");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

This is an illustrative snippet; the caller typically receives `IllegalStateException`, not the original error. Manual `try/finally` does not automatically add `original` to suppressed exceptions. Therefore, even when choosing `throws` correctly, poor cleanup code can mask the root cause.

Recommendations:

- Prefer `try-with-resources` for `AutoCloseable`, especially when `close()` can throw.
- Do not `return` inside `finally` to avoid swallowing exceptions.
- If manual cleanup can fail, design a way to preserve the primary error and report the cleanup error; do not arbitrarily discard serious cleanup errors.
- Do not mark a business operation as successful in `finally`, because `finally` also runs when the operation fails.
- Test scenarios where both the primary error and a cleanup error occur together.

**Error propagation** and **resource release** are two separate responsibilities: a method can clean up resources locally while continuing to pass the exception to the caller to handle.

## 12. `InterruptedException`: When Should It Propagate?

`InterruptedException` is a checked exception that usually indicates a thread waiting at an interruptible point received a cancellation request. If a method can declare `throws InterruptedException`, propagating the exception up to the layer responsible for stopping the task is usually the right approach:

```java
String takeNext(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

This is an illustrative method snippet. It does not know whether to cancel the processing loop, stop the worker, or notify the caller, so it transfers responsibility to the higher layer.

If implementing `Runnable.run()` (which does not declare checked exceptions) and a blocking call throws `InterruptedException`, a usually reasonable approach is to restore the interrupt flag and exit the work:

```java
@Override
public void run() {
    try {
        processBlockingWork();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

This is a **code fragment inside a class implementing `Runnable`** that has a `processBlockingWork()` method throwing `InterruptedException`. It is not standalone. Calling `Thread.currentThread().interrupt()` is important because many waiting APIs clear the interrupted status flag when throwing `InterruptedException`; restoring it lets thread-management code know the task was requested to stop.

Do not catch `InterruptedException` and loop indefinitely as if nothing happened, unless a special contract explicitly specifies consuming the interrupt request. When handling interruption, any continuation must also ensure consistent resources/state.

## 13. Catch Narrowly; Do Not Use `catch (Exception)` as a Catch-All Formula

Some situations warrant catching multiple exception types, but choose based on **handling policy** rather than writing convenience.

Example:

```java
try {
    loadOptionalMetadata();
} catch (java.io.FileNotFoundException missing) {
    useOptionalDefault();
}
```

This snippet requires `loadOptionalMetadata()` and `useOptionalDefault()`. It only recovers for the specific "optional file not found" exception. Other `IOException`s such as permission denied or device errors can still propagate upward if the method declares `throws` appropriately.

Conversely:

```java
try {
    loadOptionalMetadata();
} catch (Exception ignored) {
    useOptionalDefault();
}
```

This snippet catches too broadly: a `NullPointerException` from a bug, an unexpected conversion error, or other failures can all be masked as "no metadata." It makes diagnostic signals hard to see.

With multi-catch, exception types in the same `catch` should genuinely share a handling policy:

```java
catch (java.net.SocketTimeoutException
        | java.net.ConnectException transientError) {
    recordTransientFailure(transientError);
}
```

This is an illustrative fragment inside a method that may encounter those network errors and has declared `recordTransientFailure`. Do not assume every network error can be retried: whether the request already caused side effects and idempotency must still be considered.

## 14. API Boundaries, Business Errors, and Caller Experience

The caller may be an HTTP controller, a command-line interface, a scheduled job, or a batch processor. The same infrastructure exception can lead to different decisions:

| Boundary | Potentially reasonable policy | Avoid |
| --- | --- | --- |
| HTTP API | Map error to a stable code/response, log `Throwable` | Returning technical detail strings, tokens, or stack traces to the client |
| CLI | Print a helpful message, return a failure exit code | Returning exit code `0` after a failed operation |
| Batch | Record error result for the independent item and continue others | Mixing failed item state into successful results |
| Startup | Halt startup if required configuration is missing | Using default configuration not allowed by the contract |
| Optional data UI | Display cache/fallback when permitted | Treating fallback as freshly updated data |
| Financial transaction | Fail clearly, roll back/reconcile | Swallowing the error and recording "paid" |

The outer boundary may **catch to terminate the request as failed**, not necessarily to **recover to success**. Distinguish two goals:

- *Catch to recover*: fix the condition and produce a valid result.
- *Catch to report*: intercept the exception at the communication boundary, preserve the failure state, and convert it into an allowed report.

Both are local handling at a boundary, but their business outcomes differ. An exception may propagate via `throws` through many layers and finally be caught to report an error without any fallback.

## 15. Data Modified Before an Error: `throws` Does Not Auto-Rollback

Example:

```java
void reserve(Order order) throws java.io.IOException {
    order.markReserved();
    remoteService.confirmReservation(order);
}
```

This is an illustrative snippet requiring `Order` and `remoteService`; it is **not standalone**. If `markReserved()` already changed state and then `confirmReservation()` throws `IOException`, propagating the exception does not automatically revert `order` to its previous state.

Conversely, catching and returning a fallback here does not fix the error either; it can hide the fact that the remote service already received the request while the client does not know the outcome.

You must add a consistency policy:

1. Validate all checkable preconditions before making changes.
2. Define transaction boundaries for updates within the same data store.
3. If the remote call has side effects, consider an idempotency key, outbox, or reconciliation instead of blind retries.
4. When the true outcome is uncertain, use a state such as `PENDING_RECONCILIATION` instead of `SUCCESS`.
5. Test the state after an error, not only whether the exception was thrown.

Therefore, `throws` **preserves the error signal**, but it does not preserve data state in place of a proper transaction or business protocol.

## 16. Exception Propagation in Lambdas and Asynchronous APIs

One detail to watch in Java: common functional interfaces such as `Supplier<T>` and `Runnable` **do not declare checked exceptions**. Therefore, you cannot freely propagate `IOException` from a lambda used in `CompletableFuture.supplyAsync(...)` without handling or wrapping it.

Illustrative example:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    try {
        return readFromStorage();
    } catch (java.io.IOException original) {
        throw new java.util.concurrent.CompletionException(
                "Read failed asynchronously", original);
    }
});
```

This snippet requires importing/declaring `CompletableFuture` and defining `readFromStorage()` returning `String` and throwing `IOException`. `CompletionException` is unchecked so the lambda can throw it; the constructor with `cause` preserves the original error.

On the observing side:

```java
try {
    String value = future.join();
} catch (java.util.concurrent.CompletionException wrapper) {
    Throwable cause = wrapper.getCause();
    // Classify cause, report failure; do not pretend it succeeded.
}
```

This is also illustrative code requiring `future` to be declared. `join()` reports errors via the asynchronous wrapper; if you need to identify the root cause, inspect `getCause()` and possible wrapper layers.

With an `ExecutorService`, `Future.get()` can throw `ExecutionException` when the task fails. A checked `InterruptedException` on the **waiting thread** has a different meaning from an exception produced by the task itself. Do not turn everything into the same `RuntimeException("failed")` just to avoid thinking about the contract.

## 17. Testing Local Handling vs. Propagation Choices

Test suites should verify **not only the exception type**, but also the effectiveness of the policy:

| Test case | With local handling | With propagation |
| --- | --- | --- |
| Operation succeeds | Returns actual result | Returns actual result |
| Recoverable error type | Returns valid fallback and records if needed | Caller receives error and decides |
| Unexpected error/bug | Does not silently turn into success | Error propagates with proper cause class |
| Cleanup runs after error | Resource cleaned up, state valid | Resource cleaned up, error still present |
| Both body and `close()` fail | Does not hide primary; preserves suppressed | Caller sees primary and suppressed |
| Error translated into wrapper | Caller sees appropriate wrapper and intact cause | Wrapper continues propagating to handling layer |
| Partially modified state | Verified rollback/compensation | Caller knows failure and has state-handling policy |
| Task interruption | Preserves or propagates interrupt signal | `InterruptedException` propagated per contract |

JUnit 5 example (illustrative code, requires JUnit dependency and `import org.junit.jupiter.api.Assertions.*`):

```java
@Test
void propagatePreservesIOException() {
    IOException error = assertThrows(IOException.class,
            () -> service.propagate(true));
    assertEquals("storage unavailable", error.getMessage());
}

@Test
void recoverOnlyWithAllowedFallback() {
    assertEquals("CACHED_DATA", service.handleLocally(true));
}

@Test
void translatedErrorKeepsCause() {
    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.translate(true));
    assertInstanceOf(IOException.class, error.getCause());
}
```

This is a **test fragment**, not a standalone program: it requires declaring `service`, `@Test`, `IOException`, and JUnit Jupiter configuration. On plain JDK Java 17, you can write an assertion helper in `main` or use the runnable code in the earlier example to observe behavior.

A test that sees a fallback is not enough to prove safe recovery if data has already been updated. When state is involved, always assert postconditions as well: resources closed, transaction not wrongly committed, no `SUCCESS` event emitted after failure, and data received by the caller matches the contract.

## 18. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| "Declaring `throws` means the error is handled." | `throws` only declares checked exceptions that may escape | Place `catch`/policy at the layer that truly owns the decision |
| Catching `Exception` and returning success | Masks unexpected errors and invalid state | Catch only types you know how to recover from; otherwise propagate |
| `catch` that only calls `printStackTrace()` and continues | Logging does not mean recovery | Propagate failure upward or restore valid state |
| New wrapper only contains `error.getMessage()` | Loses original cause and stack | Use constructor `(message, error)` |
| Catching errors in repository and returning default for all callers | Low-level layer enforces wrong-context policy | Propagate or translate exception; let higher layers decide |
| Exposing `IOException` across all domain APIs without thought | Leaks infrastructure details | Translate exception at the domain boundary when valuable |
| Not cleaning up resources because `throws` is used | Leaks files/sockets/DB connections | Use `try-with-resources` or proper cleanup |
| `finally` throws cleanup error and loses primary error | Misdiagnoses root cause | Preserve primary/suppressed; prefer `try-with-resources` |
| Retrying every exception | Easily increases load/side effects, hides bugs | Retry only with classification and idempotency |
| Catching `InterruptedException` and ignoring it | Loses task cancellation request | Propagate or restore flag and exit per contract |
| Testing only "does not crash" | Fails to detect false success | Assert error type, cause, state, and cleanup |
| `throws Exception` arbitrarily at every layer | Contract too broad and hard to know error types | Declare meaningful checked exceptions or use suitable abstractions |

## 19. Self-Check Questions

**Question 1.** Does the method `void read() throws IOException` definitely throw an exception every time it is called?  
**Answer:** No. `throws` only declares the possibility; the method can still complete normally.

**Question 2.** How do `throw new IOException("failed")` and `throws IOException` differ?  
**Answer:** `throw` is a statement that throws an object; `throws` is part of the signature declaring checked exceptions that may escape.

**Question 3.** A repository knows a file read failed, but does not know whether the caller is allowed to use cache. What should it do?  
**Answer:** Usually it should propagate `IOException` or translate the error at an appropriate boundary so the policy-owning layer can decide.

**Question 4.** When catching `NumberFormatException` from user input, can returning an `INVALID_INPUT` status be valid?  
**Answer:** Yes, if it is an expected situation, no data has been updated, and the result reflects the real error.

**Question 5.** Does `catch (IOException e) { throw new IllegalStateException(e.getMessage()); }` preserve the cause?  
**Answer:** No. Use `new IllegalStateException("context", e)` to link the original exception.

**Question 6.** Does letting `IOException` propagate from `try-with-resources` skip `close()`?  
**Answer:** No. The resource is still closed according to `try-with-resources` rules; if both body and close fail, the close error is typically in `getSuppressed()` of the body error.

**Question 7.** If a method returns `"CACHED_DATA"` from a catch branch, does that mean the source operation succeeded?  
**Answer:** No. That is fallback recovery, valid only if allowed by the contract and the caller is not misled about the source/result.

**Question 8.** Do all `RuntimeException`s need `throws RuntimeException` added?  
**Answer:** No. Unchecked exceptions are not required to be declared.

**Question 9.** Why does `throws` not automatically guarantee transaction rollback?  
**Answer:** It only propagates the exception; already-modified data requires a separate transaction/rollback/compensation policy.

**Question 10.** When handling `InterruptedException` in `Runnable.run()`, what must you pay attention to?  
**Answer:** Do not swallow the interrupt request; if it cannot be propagated, typically restore the interrupted status and exit the task per contract.

**Question 11.** Is an HTTP layer catching an exception to return a failure response necessarily "successful recovery"?  
**Answer:** No. That may simply be converting an internal failure into a safe error response at the boundary.

**Question 12.** When should you both `catch` and throw a new exception?  
**Answer:** When you need to translate an error to an appropriate abstraction layer, add useful context, and preserve the cause, while not yet able to recover the business result.

## 20. References

- [Java Language Specification §11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): exception mechanism, checked/unchecked, and throwability checking.
- [Java Language Specification §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): `throws` declarations in method signatures.
- [Java SE 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, stack traces, and suppressed exceptions.
- [Java SE 17 — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception for many I/O operations.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource contract of `try-with-resources`.

**Summary:** *Catch locally* when the current layer can handle the error properly and guarantee valid state. *Propagate with `throws`* when the current layer lacks sufficient context or decision authority; doing so keeps responsibility at higher layers without handling the error prematurely. If you need to change the exception type, use a wrapper with `cause`. In all cases, clean up resources properly, never mask the root error, and test post-failure state as well.