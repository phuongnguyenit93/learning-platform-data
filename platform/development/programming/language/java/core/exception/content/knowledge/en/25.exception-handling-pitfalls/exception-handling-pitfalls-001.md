# Empty Catch Blocks and Swallowing Failure Signals in Java

## 1. Why Is an Empty `catch` Block Dangerous?

In Java, an exception is a **control signal** indicating that the normal execution flow has been interrupted. When code throws an exception, the JVM searches for an appropriate `catch` block up the call stack. If a `catch` catches the exception and **does not rethrow it, does not return an error status, does not recover, and does not report the failure according to contract**, execution usually continues as if the problem had been handled.

Example:

~~~java
try {
    saveOrder();
} catch (IOException ignored) {
}
sendSuccessResponse();
~~~

This is an **illustrative fragment**, assuming `saveOrder()` and `sendSuccessResponse()` are already declared. If `saveOrder()` throws `IOException`, `sendSuccessResponse()` is still called, even though the order may not have been saved or may have been only partially saved. An empty `catch` does not automatically undo file writes, committed transactions, HTTP calls, or in-memory object mutations.

This is **exception swallowing**. It can cause three kinds of consequences:

1. **Incorrect business outcomes:** The API returns `true`, `200 OK`, or "saved" when it is actually unknown whether the work completed.
2. **Loss of diagnostic evidence:** The exception class, message, stack trace, and `cause` are discarded from the channels observed by those responsible for monitoring.
3. **Incorrect orchestration:** The caller does not retry, rollback, compensate, or alert because it receives no failure signal; monitoring systems may count the request as a success.

Not every `catch` has to rethrow. A `catch` can **handle an error successfully** when it genuinely restores the required condition—for example, a valid cache fallback or skipping an optional configuration file according to contract. The issue is not the two braces `{}` by themselves, but **losing failure information that the caller or system must know**.

**Core principle:** Catching an exception is only the step of receiving the error; to consider an error handled, you must prove the postconditions, recovery mechanism, and information path to the party responsible.

## 2. How `try-catch` Works: Where Does the Program Go After Catch?

Basic structure:

~~~java
try {
    performOperation();
} catch (IOException e) {
    handle(e);
}
continueProcessing();
~~~

This is a fragment with hypothetical methods. If `performOperation()` throws `IOException` and `handle(e)` **completes normally**, execution continues at `continueProcessing()`. The JVM does not decide on its own that "this error is unresolved, propagate it"; from a program-control standpoint, `catch` has handled the exception-throwing flow.

If `handle(e)` throws a new exception, or `catch` executes `throw e`, the exception propagates outward again. If `catch` executes `return`, the current method terminates along that return branch; if there is an associated `finally` block, it executes according to Java rules. If `catch` calls a fallback method and the fallback fails, that new error must also be accounted for.

### 2.1. Comparing Four Ways to Handle Caught Exceptions

| Action in `catch` | What does the caller observe? | When to use |
| --- | --- | --- |
| `catch (IOException ignored) {}` | Does not receive that exception; code after catch continues | Almost only when ignoring is **proven** safe and intentional |
| `throw e;` | Receives that exact exception if the signature/type system permits | The current layer cannot handle it and wants to preserve type/cause/trace |
| `throw new ServiceException("...", e);` | Receives a new exception with the original cause | Translating the error to another layer's contract while adding context |
| `return Result.failure(code, e);` | Receives a structured failure status | The API chooses a result type to represent expected/classified failures |

Depending on the API, logging in `catch` and then **returning an error status** is also reasonable; logging is not a substitute for a result. Some errors can be recovered via a fallback and return a success value, but the fallback must satisfy invariants and must not falsely claim that the original operation completed.

### 2.2. Seeing No Stack Trace Does Not Mean There Was No Error

An exception can be created, thrown, caught, and ignored without a single log line. Java **has no default mechanism to print every caught exception**. Only uncaught exceptions reaching an uncaught handler, or code paths that explicitly log or inspect the `Throwable`, produce visible output. Therefore, a system can have "no errors in the logs" while several steps have already failed.

## 3. A Short Example: Reporting Success When State Has Already Changed

Suppose an operation consists of:
1. Writing an "order created" record.
2. Writing a mandatory audit record to confirm the process completed.

If the audit fails **after step 1**, swallowing the exception makes the caller think both steps succeeded, while the state only has the first part.

~~~text
Order written successfully
        |
        v
Audit write failed -> IOException
        |
        v
empty catch
        |
        v
returns "SUCCESS" even though audit is missing
~~~

Important: even if we fix `catch` to propagate the exception, **the earlier order write is not automatically undone**. There are two independent concerns:
- **Signaling failure accurately:** the caller knows the process did not complete.
- **Preserving/restoring state:** transactions, staging, outbox, or compensation designed for the scope of the resources involved.

If you only add `throw` and ignore data consistency, you have restored error observability, but you have not made the business operation atomic.

## 4. Complete Java 17 Example: Swallowing Errors, Propagating Cause, and Returning Meaningful Results

The program below uses an in-memory `EventStore` to observe state. It intentionally triggers an I/O error in the audit step, then compares:
- The **`broken`** method has an empty catch and prints a success message.
- The **`honest`** method adds context, preserves the cause, and propagates the exception to the caller.
- The lookup method returns `Optional.empty()` **only when there is no data**.
- A method demonstrating a minimal structured fallback: returning a boolean reflecting whether the audit step succeeded or failed, without falsely claiming success.

Save as **`EmptyCatchLessonDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class EmptyCatchLessonDemo {
    static final class EventStore {
        private final List<String> events = new ArrayList<>();
        void append(String value) { events.add(value); }
        List<String> snapshot() { return List.copyOf(events); }
    }

    static void writeAudit() throws IOException {
        throw new IOException("audit unavailable");
    }

    static void broken(EventStore store) {
        try {
            store.append("order-created");
            writeAudit();
        } catch (IOException ignored) {
        }
        System.out.println("broken: reported success");
    }

    static void honest(EventStore store) throws IOException {
        store.append("order-created");
        try {
            writeAudit();
        } catch (IOException cause) {
            throw new IOException("order may be partially processed", cause);
        }
    }

    static Optional<String> find(String id) {
        return "A".equals(id) ? Optional.of("Alice") : Optional.empty();
    }

    static boolean attemptWithFallback() {
        try {
            writeAudit();
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    public static void main(String[] args) {
        EventStore first = new EventStore();
        broken(first);
        System.out.println("broken state: " + first.snapshot());

        EventStore second = new EventStore();
        try {
            honest(second);
        } catch (IOException e) {
            System.out.println("honest: " + e.getMessage());
            System.out.println("cause: " + e.getCause().getMessage());
        }
        System.out.println("honest state: " + second.snapshot());
        System.out.println("lookup: " + find("B").isEmpty());
        System.out.println("fallback: " + attemptWithFallback());
    }
}
~~~

Compile and run with **JDK 17 or later** in the directory containing the file:

~~~bash
javac --release 17 EmptyCatchLessonDemo.java
java EmptyCatchLessonDemo
~~~

Verified stdout:

~~~text
broken: reported success
broken state: [order-created]
honest: order may be partially processed
cause: audit unavailable
honest state: [order-created]
lookup: true
fallback: false
~~~

### 4.1. What the Output Proves

- **`broken: reported success`:** `broken` continues after the empty `catch` and prints success even though `writeAudit` always throws `IOException`.
- **`broken state: [order-created]`:** the in-memory write already occurred. An empty `catch` does not roll back state.
- **`honest: order may be partially processed`:** the error is not lost; the code wraps it with context that the work may have been partially processed.
- **`cause: audit unavailable`:** the constructor `new IOException(message, cause)` preserves the underlying exception; the caller can inspect `getCause()` and its corresponding stack trace.
- **`honest state: [order-created]`:** rethrowing an exception does not reverse effects that occurred before the error. If the business logic requires atomicity, an appropriate mechanism must be designed.
- **`lookup: true`:** `Optional.empty()` represents a valid search result where `"B"` was not found; do not use it to replace a storage read error.
- **`fallback: false`:** the boolean example reflects that the audit did not succeed. This is a minimal API choice, not advice to use booleans for all error types; larger systems should consider a result with a reason code.

In real applications, choose clearer return names (such as `auditSucceeded`), retain errors for logging/reconciliation when needed, and ensure sensitive data is not exposed. The `attemptWithFallback` pattern can only be considered "handled" if the contract publicly states that `false` is a **meaningful failure result**, not `true` in all cases or an ignored variable.

## 5. Distinguishing "Catch and Handle" from "Catch and Swallow"

A `catch` is valid handling when it performs at least one action consistent with the API contract:
- **Genuine recovery:** controlled retry or using a qualifying backup source, then verifying the result is valid.
- **Propagation:** `throw` the same exception, or wrap it with cause and context.
- **Returning a failure result:** typed result, error code, pending/unknown status, or an appropriate checked outcome.
- **Marking a transaction rollback-only:** when the transaction manager actually supports it and the program is still within the transaction scope.
- **Intentionally ignoring an insignificant situation:** with an explicit policy, no impact on invariants, and a clear explanation of why losing that event is safe.

Example of a reasonable ignore: attempting to delete a **temporary file determined to be no longer needed**, encountering a "file no longer exists" error in a cleanup method designed to be **idempotent**. Even then, prefer a direct API such as `Files.deleteIfExists(path)` and handle other errors (such as permission denied) according to their severity; do not catch all `IOException`s and assume every one means "does not exist".

### 5.1. How to Verify Whether a Fallback Truly Recovers

Ask:
1. Does the result after fallback satisfy the same contract as the success branch, or is a different contract declared?
2. Could fallback data be stale or incomplete? Does the caller need to know the source?
3. Did any side effect of the original step already occur before the exception was thrown?
4. Could retrying create duplicates or violate idempotency?
5. If the fallback also fails, what signal is propagated?

For example, reading from cache when the database loses connection may be reasonable for a read-only UI that tolerates stale data, provided freshness is clearly documented. However, a cache fallback is not reasonable for a payment operation that requires an exact committed outcome.

## 6. Do Not Use `Optional.empty()` or `null` to Hide Every Error

Wrong approach:

~~~java
Optional<Customer> findCustomer(String id) {
    try {
        return repository.findById(id);
    } catch (Exception ignored) {
        return Optional.empty();
    }
}
~~~

This is a **non-standalone illustrative fragment**; `Customer` and `repository` are not defined. It makes "customer does not exist" indistinguishable from "database is down", "access denied", or a `NullPointerException` bug. The caller might create a duplicate customer, write incorrect state, or return HTTP 404 instead of 503.

A clearer contract:
- `Optional<Customer>` only represents **whether a customer exists or not** when the query executes validly.
- Unrecovered storage errors should propagate the exception or return a separate `Result.Error(code, cause)`.
- If the caller needs to distinguish between "does not exist" and "could not be checked", a sealed result type such as `Found`, `NotFound`, `Unavailable` can express it fully.

Using `null` for both absence and error is even more dangerous because it easily causes `NullPointerException` in upper layers while losing information about the original exception. Do not use default values such as `0`, `false`, empty strings, or empty lists to mean "an error occurred" if they are simultaneously valid results.

## 7. Checked Exceptions, Unchecked Exceptions, and Broad Catches

`IOException` and `SQLException` are **checked exceptions**, which generally must be caught or declared with `throws`; `NullPointerException`, `IllegalArgumentException`, and `IllegalStateException` are **unchecked exceptions**. `Error` also extends `Throwable` but belongs to a different branch, usually indicating serious errors that should not be hidden.

~~~java
try {
    executeBusinessOperation();
} catch (Exception ignored) {
    // Anti-pattern: swallows both infrastructure errors and RuntimeException bugs.
}
~~~

This is an illustrative snippet requiring `executeBusinessOperation()`. A `catch (Exception)` originally intended to ignore an I/O error can, after refactoring, also swallow an NPE or an invariant violation. `catch (Throwable)` even catches `Error`.

**The focus here:** an empty `catch` loses the failure signal. Catch scope and error classification are related concerns: only combine multiple exceptions in a multi-catch if they share the same handling policy. A specialized supervisor or framework may catch broadly to report failure and terminate a unit of work, but **must not report success** without restoring state.

## 8. Preserve the Cause: Rethrow, Wrap, and Do Not Fabricate Success

If `catch` cannot recover, **do not complete normally**. Keep the same exception with `throw e;` when the signature allows, or translate to a new abstraction while preserving `cause`:

~~~java
try {
    persist();
} catch (IOException e) {
    throw new IllegalStateException("Could not persist order " + orderId, e);
}
~~~

This is an illustrative snippet with `persist()` and `orderId` from the application; the message must avoid exposing sensitive data. The `(String, Throwable)` constructor preserves the original error in `getCause()`. Conversely, `new IllegalStateException("failed")` drops the cause.

If you only want the error to propagate and have no context to add, **removing the `catch` block altogether** is usually better. A dedicated lesson on *throwing a new exception while losing the cause* covers the cause chain and suppressed exceptions in detail; the key takeaway here is not to **swallow** an error and produce a false success.

## 9. `InterruptedException` Is a Cancellation Signal; Swallowing It Is Especially Dangerous

A common bug in worker loops:

~~~java
while (running) {
    try {
        Thread.sleep(1_000);
        poll();
    } catch (InterruptedException ignored) {
    }
}
~~~

This is an illustrative fragment; `running` and `poll()` are undefined. When a thread is interrupted for cancellation or shutdown, `Thread.sleep` typically throws `InterruptedException` and clears the interrupt status. An empty `catch` makes the loop continue; the system may fail to stop the task even though the executor requested cancellation.

Cooperative pattern:

~~~java
Runnable worker = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Thread.sleep(1_000);
            pollOnce();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
};
~~~

This is a fragment; `pollOnce()` is undeclared. Restoring the interrupt flag and exiting lets upper layers or teardown code know that the thread received an interrupt request. If the current method is allowed to declare `throws InterruptedException`, it can propagate it instead of catching.

Note: `Future.cancel(true)` does not guarantee killing an uncooperative task, and `CompletableFuture.cancel(true)` does not interrupt the underlying supplier per the `CompletableFuture` contract. Swallowing interrupts makes these limitations even harder to control.

### 9.1. Why Not Equate Interrupts with "Business Errors"?

`InterruptedException` usually indicates that the waiting thread was requested to be interrupted, not that a task failed on its data. A method may return a canceled status, propagate the interrupt, or restore the flag depending on its API. Never catch it and return `true` as if the request had completed.

When a worker has side effects, stopping after an interrupt also does not automatically undo changes that already occurred; transactions, idempotency, compensation, or reporting a partial/unknown status are needed if applicable.

## 10. Empty Catch Inside a Loop Creates "Invisible Errors" and Hot Retry Loops

Snippets like:

~~~java
while (true) {
    try {
        consumeMessage();
    } catch (Exception ignored) {
    }
}
~~~

are illustrative fragments with `consumeMessage` undefined. If `consumeMessage` repeatedly fails immediately, the loop can burn CPU, generate thousands of swallowed errors, have no backoff, emit no metrics, and fail to stop under a shutdown policy. If a poison message causes infinite retries, the process can get stuck on the same message.

An intentional worker typically needs:
- classification of recoverable vs. permanent errors;
- retry limits, appropriate delay/backoff, and jitter;
- a dead-letter queue or terminal failure state for unprocessable events;
- idempotency/deduplication when messages may be redelivered;
- cooperative interruption, deadlines, and cleanup;
- error recording with a corresponding code/ID.

Do not turn "having a retry loop" into an excuse to ignore every exception. Retrying without limits, backoff, and status tracking is still a prolonged form of exception swallowing.

## 11. Catching in Background Tasks: The Caller May Never Know

A `Runnable` that catches every exception and returns normally makes the orchestrator see the task as **having completed normally**.

~~~java
Future<?> f = executor.submit(() -> {
    try {
        process();
    } catch (Exception ignored) {
    }
});
f.get(); // May return normally even though process() failed.
~~~

This is a fragment assuming `executor`, `process`, and checked exceptions from `get()` are declared/handled. `ExecutorService.submit` records exceptions **that escape the task** into the `Future`. If the task catches and swallows the exception itself, the `Future` cannot detect the failure hidden inside the lambda.

Similarly with `CompletableFuture`:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> {
            try {
                return remoteRead();
            } catch (RuntimeException ignored) {
                return "";
            }
        });
~~~

This fragment assumes `remoteRead()` returns a `String` and throws no unhandled checked exceptions. If an empty string is valid data, `future.join()` may return a false "success" result, preventing outer `exceptionally` or `whenComplete` handlers from seeing the error.

**Good design:** If you want to turn an exception into a result, return `Failed(ErrorCode, cause)`, do not turn it into `Success("")`. If there is no proper recovery, let the exception escape the task so `Future.get()` or `CompletableFuture.join()` propagates the failure across the thread boundary.

### 11.1. Do Not Drop the Future After Submitting

Even when the worker does **not** have an empty catch, if the caller calls `submit()` and does not keep/read the `Future`, the exception may be stored inside the handle with nobody handling it. The result is an "invisible error" at the application level. Someone must own the result: a caller calling `get()`, an aggregating coordinator, a callback handling `exceptionally`/`handle`, or a job monitor with a durable status channel when needed.

`UncaughtExceptionHandler` does not replace `Future.get()` for all executor-run tasks; `submit` typically captures errors inside the `Future` structure. Having only a raw-thread handler without a result channel is also insufficient to report success/failure to the caller.

## 12. Should You Log in Every `catch`?

No. Another anti-pattern is:

~~~java
catch (IOException e) {
    logger.error("Repository failed", e);
    throw e;
}
~~~

This is a fragment with a hypothetical logger. If the upper service, controller, and handler all repeat "log and rethrow", **a single actual error** can produce four identical stack traces. Metrics systems may count the error multiple times, and investigators struggle to identify which record represents the final outcome.

A good policy:
- A layer that **can recover**: record a recovery metric or warning as needed, then continue with the real result.
- A layer that **only propagates errors**: preserve the cause and add context if needed; logging at every hop is unnecessary.
- **The boundary responsible for returning results/monitoring**: log the error once at the appropriate level, along with request/job ID, operation type, and stack trace when needed.
- If a secondary operation (audit, cleanup, metrics) fails separately: distinguish the error source and observation point, without masking the primary exception.

Even without logging at every layer, the failure signal must still **reach a place capable of acting on it**. "Avoid duplicate logging" does not mean "swallow the exception".

### 12.1. Do Not Log Only the Message and Drop the Stack/Cause

Example:

~~~java
logger.warn("failed: {}", e.getMessage());
~~~

This is an illustrative fragment (the logging API depends on the framework); it can drop the stack trace and cause. If the application needs diagnostics, pass the `Throwable` in the position supported by the logging framework and ensure sensitive data is controlled. However, user-facing messages must not contain raw stack traces, passwords, tokens, or personal data.

## 13. Side Effects That Occurred Before the Error Do Not Vanish

A business example:

~~~text
begin operation
   |
   +-- write output file succeeded
   +-- commit DB transaction succeeded
   +-- send HTTP request to payment service
   +-- response timeout -> IOException
   |
   +-- empty catch
   +-- return "OK"
~~~

Even if the empty catch is replaced with `throw`, the file and committed database changes do not automatically revert, and the payment service **may have already processed the request** despite the client timeout.

Four states to distinguish:
1. **An error occurred** — exception/result information must exist.
2. **Changes already occurred** — possibly before the exception appeared.
3. **Whether rollback is still possible** — depends on the transaction/file/protocol.
4. **Whether the external outcome is certain** — a timeout may represent an unknown state.

Therefore, do not automatically return "failed, nothing happened". When the remote outcome cannot be determined, an `UNKNOWN`/`PENDING` status with an operation ID and reconciliation process is usually more accurate. To safely retry commands with side effects, use an idempotency key **genuinely supported by the server**, not just a nicely named header.

### 13.1. Transaction Rollback Requires Proper Boundaries

If using JDBC with `autoCommit=false` and operating within a valid transaction, calling `rollback()` on an error before commit is possible. However:
- `rollback()` does not undo changes that were committed earlier;
- it does not automatically roll back HTTP calls, emails, or files outside the transaction;
- rollback itself can fail;
- losing the connection right at commit time can leave the commit outcome **uncertain**.

Swallowing `SQLException` and continuing to use a connection in an unclear transaction state can corrupt data or affect subsequent requests. A clear transaction manager/policy is required.

## 14. `try-with-resources`, `finally`, and Cleanup Errors

Empty `catch` blocks can also appear in resource-closing code:

~~~java
try {
    writeOutput();
} finally {
    try {
        resource.close();
    } catch (IOException ignored) {
    }
}
~~~

This is a fragment with hypothetical `writeOutput` and `resource`. If `close()` fails, the system may not know whether buffered data was flushed or whether the resource was actually closed. There are cases where closing is best-effort, but there must be a **reasonable contract and diagnostic channel**.

For resources implementing `AutoCloseable`, try-with-resources is usually clearer:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(payload);
}
~~~

This is a fragment; `OutputStream`/`Files` imports are needed, and `path`/`payload` are undeclared. If both the body and `close()` throw exceptions, try-with-resources attaches the closing error to the primary exception as a **suppressed exception** per Java rules. Use `e.getSuppressed()` for diagnostics if needed. Putting an empty catch around `close()` yourself can lose a noteworthy secondary error.

However, **closing a resource is not a rollback**. `close()` or flushing may cause buffered data to actually be written, rather than restoring the previous file. When using a temp-file-and-publish protocol, clean up only temporary files owned by the operation; do not arbitrarily delete the main file in `finally`.

## 15. Ignore Exceptions Only When the Contract Truly Permits

There are "non-essential" tasks such as best-effort cache updates, attempting to delete a temporary file that no longer exists, or emitting a secondary metric. Not failing the primary request **can be a valid policy**. However, the policy should be stated clearly:

| Scenario | Can ignoring be right? | Conditions |
| --- | --- | --- |
| Auxiliary cache warm-up | Possibly | Miss/failure does not alter primary result, with proper observability |
| Deleting a temp file already cleaned elsewhere | Possibly for the specific case | Distinguish "file does not exist" from real permission/I/O errors |
| Recording a non-essential metric | Possibly | Metric loss is acceptable; does not break primary result, with error bounds |
| Persisting business data | Usually no | Caller needs to know persistence failed |
| Writing mandatory audit | Usually no | Violates legal/business requirements if trail is lost |
| Charging money, creating orders, publishing critical events | Cannot swallow broadly | Needs clear outcome/cancellation/idempotency/reconciliation |
| Worker `InterruptedException` | Usually no | Must respect shutdown/cancellation signals |
| Serious JVM `Error` | No | Must not be treated as a normal error and blindly continued |

Even when ignoring is permitted, you can use:
- an aggregated error-count metric so alerting capability is not lost;
- **rate-limited** logging when needed;
- a degraded/best-effort status described in the API;
- a fallback mechanism that does not alter invariants;
- a durable audit channel if a secondary error becomes a mandatory requirement.

Do not force every situation to log an ERROR-level stack trace; excessive logging also obscures primary incidents.

### 15.1. Ignorable Exceptions Must Be the Right Type at the Right Time

For example, `Files.deleteIfExists(path)` returns `false` when the file does not exist, so catching `NoSuchFileException` separately is usually unnecessary for the normal case. If there is a race or the filesystem throws another exception, you still need to treat it as a resource issue. Broadly catching `IOException` and ignoring all of them can hide permission denied or disk failures that the system needs to know about.

Similarly, an operation canceled by user request may return a `CANCELLED` status instead of surfacing an exception to the UI. Still, do not swallow every unrelated exception along the cancellation path.

## 16. Result Types as an Alternative to Hiding Errors

In an API that needs to handle multiple expected scenarios, you can design a typed result:

~~~java
sealed interface SaveOutcome
        permits Saved, Rejected, TemporarilyUnavailable {}

record Saved(String id) implements SaveOutcome {}
record Rejected(String reason) implements SaveOutcome {}
record TemporarilyUnavailable(String code, Throwable cause)
        implements SaveOutcome {}
~~~

This is a **Java 17 fragment**, without an enclosing application class or save method. It shows:
- `Saved`: genuinely completed.
- `Rejected`: rejected due to a known business rule.
- `TemporarilyUnavailable`: classified infrastructure error, carrying an **internal** cause.

If an API returns `SaveOutcome`, the caller must inspect each branch, not just check `outcome != null` and treat it as success. For external responses, do not directly serialize `Throwable`, stack traces, or sensitive information; include only error codes and safe messages.

A result type is not magic: if the method swallows `IOException` and always constructs `new Saved(id)`, it is still wrong. Typed results are only useful when the implementation **sets the status accurately based on the reality of the work**.

### 16.1. Checked Exceptions and Upper-Layer Contracts

If a Java API uses exceptions natively to represent I/O errors, declaring `throws IOException` and letting the caller decide recovery is often simpler than a new hierarchy. Conversely, for an API that must aggregate multiple tasks and classify retry/rejected/not-found outcomes, a structured result can be clearer.

There is no rule that "every exception must become a Result" or "every error must throw unchecked". The right choice depends on how expected the error is, the caller's decision-making authority, and the ability to preserve information across boundaries.

## 17. "Empty Catch to Avoid Crashing" Often Creates Harder-to-Diagnose Crashes

A common argument is "if we let the exception propagate, the request/thread will die; an empty catch keeps the application stable." Yet if a critical step fails:
- memory/cache may fall out of sync with the database;
- locks/transactions may remain in a bad state;
- the caller uses bogus data;
- subsequent steps throw `NullPointerException` far from the real root cause;
- retries may duplicate side effects;
- monitoring systems have no idea intervention is needed.

Therefore, **isolating failure** is different from **hiding failure**. A worker supervisor can catch exceptions at the task boundary, record `FAILED`, ensure cleanup, and continue accepting other work. That is a more stable design than swallowing errors right inside the business-logic layer.

Example of a job handler:

~~~java
try {
    processJob(job);
    markCompleted(job.id());
} catch (IOException e) {
    markFailed(job.id(), "IO_ERROR", e);
}
~~~

This is a fragment with hypothetical methods. The policy is sound if `markFailed` has a reliable status-recording mechanism, `processJob` has not already committed a conflicting outcome, and callers distinguish the failure status. If `markFailed` also throws an exception, the system must have rules to handle/recover from it. Do not consider a catch complete just because `markFailed` appears on paper.

## 18. How Do Tools Detect Empty Catches?

Static analysis can detect:
- `catch (Exception e) {}` or blocks containing only comments;
- variables named `ignored`/`unused` with no handling policy;
- a `catch` returning a success value despite the exception;
- an empty `catch` on `InterruptedException`;
- catching `Throwable` or overly broad exceptions;
- log-and-rethrow causing duplicate reporting;
- ignoring a significant `Future`.

IDEs and tools such as Checkstyle, PMD, SpotBugs, or Sonar have related rules/inspections depending on configuration and version. **Do not rely on a fixed rule ID** without checking the tool version in use. A linter may skip cases containing an "ignored" comment; such a comment does not prove the design is safe.

An effective code review policy is to require the author of a `catch` to state clearly:
1. What kind of exception is this, and why does it occur?
2. Could there still be side effects or unknown state?
3. Who needs to know about it?
4. Why was recovery/fallback/return/throw chosen?
5. Which tests prove both the failure branch and the success branch?

These questions are better than a mechanical ban on every `catch` without logging.

## 19. Testing to Catch Swallowed Errors

Merely checking that a method "does not throw an exception" is too weak. You need to **inject faults** into dependencies and assert the resulting state:

| Fault injection point | What to verify |
| --- | --- |
| Error before writing data | API reports failure; no success message is emitted |
| Error after partial write | Caller receives partial/failed/unknown per contract |
| `IOException` from repository | Not turned into `Optional.empty()` or a fake empty list |
| Audit callback fails after commit | Does not claim DB rolled back; reconciliation status exists |
| `InterruptedException` in worker | Task exits/restores flag or propagates per policy |
| Future task throws exception | Caller/worker manager observes `ExecutionException.getCause()` |
| Retry hits consecutive errors | Does not spin in an infinite hot loop; has limits/backoff/metrics |
| Cleanup error | Does not mask primary error; preserves suppressed/secondary record where appropriate |
| Fallback also fails | Error is propagated or result reflects failed recovery |
| Secondary log/metrics fail | Does not accidentally turn business success into failure if policy is best-effort |

### 19.1. Unit Test Example Showing the Failure Signal Must Exist

The following JUnit 5 fragment assumes the `EmptyCatchLessonDemo` class above is available:

~~~java
var store = new EmptyCatchLessonDemo.EventStore();

IOException thrown = assertThrows(IOException.class,
        () -> EmptyCatchLessonDemo.honest(store));

assertEquals("order may be partially processed", thrown.getMessage());
assertEquals("audit unavailable", thrown.getCause().getMessage());
assertEquals(List.of("order-created"), store.snapshot());
~~~

This is a **non-standalone fragment**: it requires the JUnit Jupiter dependency, imports for `java.io.IOException` and `java.util.List`, and static imports for `assertThrows` and `assertEquals`. The test proves the caller knows about the error and its cause **even when state has already changed**. That separates the requirement to signal failure from the requirement to restore all state.

If the API promises "whenever save fails, no new data is present", the test above must assert an empty snapshot and the implementation must use transactions/staging to fulfill that promise. Never change an expected test to "valid" just because a catch swallowed the exception.

### 19.2. Testing Lost Signals When a Worker Swallows Errors

With a `Callable<T>`, configure a fake dependency to throw an exception. If the task catches and returns a default, `Future.get()` will return a normal value. The test should assert a `Result.Failed` value or `ExecutionException`, depending on the contract. With `CompletableFuture`, verify that `join()` raises `CompletionException` or returns a `Failed` branch when the application intentionally classifies it, rather than only checking `isDone()`.

In particular, if you only assert that a task finished within a timeout, a silently failing task can still be counted as a success.

## 20. Checklist When Reviewing Every `catch` Block

- [ ] Is the caught exception type **specific** and appropriate for the handling layer?
- [ ] If the catch is empty or ignores the error, is there a **verified business reason** rather than just an "ignore" comment?
- [ ] Could side effects or partial state occur before the exception?
- [ ] After the catch, does any line report a **false success**?
- [ ] Can the caller still distinguish success, absence, failure, and unknown?
- [ ] If using a fallback, does the fallback data satisfy invariants and freshness?
- [ ] If retrying, are there limits/backoff and idempotency?
- [ ] If translating the exception, are `cause`/stack trace and context preserved?
- [ ] If encountering `InterruptedException`, is it propagated or is the flag restored/exited appropriately?
- [ ] If an error occurs inside a `Future`/`CompletableFuture`, does someone own observing the failure?
- [ ] If resource cleanup fails, are suppressed exceptions or diagnostic signals preserved appropriately?
- [ ] Is logging done at the right boundary, without duplicate logging at every layer and without leaking secrets?
- [ ] Do unit/integration tests inject faults and verify **post-error state**?
- [ ] If ignoring secondary errors is policy, are **best-effort** semantics and degradation metrics/monitoring documented?

## 21. Practice Exercise

A system receives an order request and performs three steps:

~~~text
(1) Save order to database
(2) Publish OrderCreated event
(3) Send confirmation email
~~~

The source contains:

~~~java
try {
    saveOrder(order);
    publishEvent(order);
    sendEmail(order);
} catch (Exception ignored) {
}
return "ORDER_CREATED";
~~~

This is a fragment with hypothetical functions and variables.

Analyze and fix it for the following scenarios:

1. `saveOrder` throws an exception **before commit**. What should the caller receive? If a transaction is still open, where should rollback happen?
2. `saveOrder` committed, but `publishEvent` throws an exception. Why must you not claim "order was not created"?
3. `publishEvent` actually sent the event, but the client timed out; how should retries work to avoid duplicating effects?
4. `sendEmail` fails, but the requirement only mandates saving the order and email is best-effort. How should this be expressed in the contract and monitoring?
5. If `ExecutorService.submit` is used to send the email, who holds the `Future`/observes errors? If the task has an empty catch, will the caller know?
6. Write unit tests that intentionally throw `IOException` at each step, asserting outcome/cause/state. Add a test where a cleanup callback fails without masking the primary error.
7. Design an approach that saves business data and an outbox record in the **same DB transaction** when events must be published after commit; explain why the outbox still needs an idempotent consumer on retry.

## 22. Summary of Principles

**An empty catch does not mean the exception was resolved.** It usually just severs the failure-reporting path from where the error occurred to the caller or orchestrator. Operations that happened before the exception may remain intact; continuing and returning "success" can propagate corrupted state to subsequent steps.

When writing or reviewing a `catch`, choose one of the actions with an **explicit contract**: genuine recovery, propagating the exception with its cause, returning a structured error, marking the transaction failed, or ignoring a non-essential error proven to be safe. For interruptions and asynchronous tasks, do not swallow cancellation signals or drop errors inside a `Future`. Most importantly, test **failure branches and post-error state**, rather than seeing the program not crash and concluding it works correctly.
