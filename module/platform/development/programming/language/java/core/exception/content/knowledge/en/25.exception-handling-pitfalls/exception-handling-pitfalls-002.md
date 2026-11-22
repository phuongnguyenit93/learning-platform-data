# Catching Exception or Throwable Too Broadly at Every Layer: A Common Mistake in Java

## 1. Nature of the Problem

Java uses exceptions to signal that a call **cannot complete according to its contract**. When an exception occurs, the JVM searches for a matching `catch` on the call stack of the **currently executing thread**, runs the necessary cleanup blocks, and then transfers control to the handler. Therefore, it is neither necessary nor advisable to place a generic `catch` in every intermediate method.

A common anti-pattern:

```java
try {
    performBusinessOperation();
} catch (Exception ex) {
    System.err.println(ex.getMessage());
    return null;
}
```

This is a **code snippet intentionally illustrating a mistake**, assuming `performBusinessOperation()` is already defined and the enclosing method permits `return null`. It looks safe because no exception escapes, yet it can:

- Hide I/O errors or programming bugs and turn a failure into a fake valid result.
- Lose the ability to distinguish between input errors, state errors, dependency errors, and cancellation errors.
- Prevent the caller from performing appropriate retries, rollbacks, error code display, or alerting.
- Log sensitive data via `getMessage()` while still failing to preserve the full stack trace.
- Cause the system to continue in a state that violates its contract.

A more severe variant:

```java
try {
    performBusinessOperation();
} catch (Throwable error) {
    return null;
}
```

`Throwable` also includes `Error`; catching and swallowing it does not guarantee that the JVM or underlying components can still operate safely.

**Principle:** a layer should only catch the types of errors that it **truly has the responsibility and capability to handle**: valid recovery, translating the error to the layer's contract, cleanup/rollback within its scope of ownership, recording a failure status, or returning a response at a boundary. Other errors should continue to propagate.

"Not catching here" does not mean "ignoring the error." It can be the way to let a more appropriate layer decide the policy.

## 2. Important Exception Hierarchy

```text
java.lang.Throwable
├── Error
│   ├── OutOfMemoryError
│   ├── StackOverflowError
│   ├── LinkageError
│   └── AssertionError
└── Exception
    ├── IOException
    │   └── FileNotFoundException
    ├── SQLException
    ├── InterruptedException
    ├── ExecutionException
    └── RuntimeException
        ├── IllegalArgumentException
        ├── IllegalStateException
        ├── NullPointerException
        └── IndexOutOfBoundsException
```

This is a **simplified** tree and does not list every class.

| Catch | Scope Caught | Notes |
| --- | --- | --- |
| `catch (IOException ex)` | `IOException` and subclasses such as `FileNotFoundException` | Appropriate if the layer handles I/O errors |
| `catch (RuntimeException ex)` | Runtime exceptions | Can accidentally swallow bugs like `NullPointerException` |
| `catch (Exception ex)` | Checked and unchecked exceptions under `Exception` | Does **not** catch `Error`, but **does** catch `InterruptedException` |
| `catch (Throwable ex)` | Both `Exception` and `Error` | Does not guarantee the ability to recover from all errors |
| `catch (InterruptedException ex)` | Wait interruption signal | Must decide whether to propagate or restore the interrupt flag |

Checked exceptions require the caller to handle or declare them at compile time; subclasses of `RuntimeException` and `Error` are not subject to that requirement. However, **checked/unchecked does not by itself determine where to catch**. That is a matter of contract and policy.

In particular, `catch (Throwable)` does not mean "able to catch every JVM-destroying condition": the process can be killed, the machine can lose power, or the runtime may no longer have resources to execute the handler.

## 3. Why Does Catching Broadly at Every Layer Weaken the Architecture?

Suppose a system has:

```text
Controller -> OrderService -> OrderRepository -> Database
```

If every layer does:

```java
try {
    callNextLayer();
} catch (Exception ex) {
    logger.error("failed", ex);
    throw new RuntimeException("failed");
}
```

then an `SQLException` can turn into a chain of multiple untyped `RuntimeException` wrappers. Because the new constructor has no `cause`, **the original error can be completely lost**. If each layer logs, a single event produces multiple duplicate stack traces, cluttering dashboards and increasing the risk of data leakage from the cause.

Worse, if the repository returns `null` when the DB is unavailable, the service may think "order not found." The HTTP layer returns 404 instead of 503, causing the client not to retry even though the real error is only transient.

Some symptoms:

1. Every method has an almost identical `try/catch (Exception)` doing no useful work.
2. Handlers return `null`, `false`, `0`, a default object, or a "success" status when success cannot be guaranteed.
3. Input errors, business errors, and infrastructure errors are wrapped into the same class.
4. Exceptions only have their message logged without preserving the cause/stack, or are logged at too many layers.
5. Tasks being cancelled are also put into a retry loop like any other error.
6. Serious `Error`s are swallowed so the process "just keeps running."

Do not optimize for "no exceptions appearing on the console" while ignoring **data correctness and caller behavior**.

## 4. The Call Stack Already Propagates Errors Across Layers

Conceptual example:

```java
static void repository() throws IOException {
    throw new IOException("dependency unavailable");
}

static void service() throws IOException {
    repository();
}

static void entryPoint() {
    try {
        service();
    } catch (IOException ex) {
        // A place responsible for translating the error into an appropriate response.
    }
}
```

These are **illustrative methods** that need to be placed in a class and import `java.io.IOException`. `service()` does not need to catch just to rethrow. If it has no business recovery or translation logic, letting the exception propagate is reasonable.

While an exception unwinds up the stack:

- `finally` has the opportunity to clean up according to Java rules.
- `try-with-resources` closes `AutoCloseable` resources.
- Monitors of `synchronized` blocks are released during unwinding.
- Changes already made to objects, files, or the DB are **not automatically rolled back**.
- An exception in a worker thread **does not automatically** jump to a `catch` in another thread; a `Future` or result-passing channel is required.

A redundant `catch` does not make stack unwinding safer. It only adds a place that can mask errors, mutate state, or throw a new exception.

## 5. Three Main Anti-Patterns

### 5.1. Swallowing and Returning a Fake Value

```java
String loadOrder(String id) {
    try {
        return repository.fetch(id);
    } catch (Exception ignored) {
        return "ORDER_READY";
    }
}
```

**Code snippet illustrating a mistake**, with `repository` already defined. If the repository is offline, the caller still receives `ORDER_READY`. If the return type is `Optional<T>`, returning `Optional.empty()` for a connection error is also wrong if empty means "no record found."

Only use a fallback when that value is **permitted by business rules** and the caller can understand the degraded state if needed. For example, stale cache is only acceptable if the system allows stale reads; it must not be arbitrarily used for payments.

### 5.2. Losing the Cause When Rethrowing

```java
catch (Exception ex) {
    throw new RuntimeException("Operation failed");
}
```

Loses `cause`, leaving outer layers unaware of the failure source.

A better pattern at a **boundary that needs error translation**:

```java
catch (IOException ex) {
    throw new DependencyUnavailableException("Storage unavailable", ex);
}
```

This snippet requires a custom-defined domain exception `DependencyUnavailableException`. The constructor takes `cause` to preserve the error link. However, **preserving the cause is still not enough** if all kinds of errors are caught and forced into an inappropriate class.

### 5.3. Logging and Rethrowing at Every Layer

```java
catch (Exception ex) {
    logger.error("Operation failed", ex);
    throw ex;
}
```

This snippet uses a logging framework and requires a signature compatible with checked exceptions. If the caller also logs, there will be multiple events for the same error. Each layer should only log when it genuinely has **distinct operational information or observability responsibility**; typically logging happens at the final boundary or where the status is decided.

## 6. Standalone, Runnable Java 17+ Example

This program demonstrates how to **catch I/O error types with different semantics**, preserve the cause, avoid masking validation errors, and also shows the consequences of catching too broadly and handling interruption.

Save the file **`BroadCatchDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.concurrent.CountDownLatch;

public class BroadCatchDemo {
    static final class OrderNotFoundException extends RuntimeException {
        OrderNotFoundException(String id, Throwable cause) {
            super("Order not found: " + id, cause);
        }
    }

    static final class DependencyUnavailableException extends RuntimeException {
        DependencyUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class Repository {
        String fetch(String id) throws IOException {
            if ("missing".equals(id)) {
                throw new FileNotFoundException("no row");
            }
            if ("offline".equals(id)) {
                throw new IOException("connection failed");
            }
            return "ORDER:" + id;
        }
    }

    static final class OrderService {
        private final Repository repository = new Repository();

        String load(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            try {
                return repository.fetch(id);
            } catch (FileNotFoundException ex) {
                throw new OrderNotFoundException(id, ex);
            } catch (IOException ex) {
                throw new DependencyUnavailableException(
                        "Order repository unavailable", ex);
            }
        }
    }

    static String brokenFallback(OrderService service, String id) {
        try {
            return service.load(id);
        } catch (Exception ignored) {
            return "FAKE_SUCCESS";
        }
    }

    static void waitForWork(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            boolean clearedByAwait = !Thread.currentThread().isInterrupted();
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPT: cleared=" + clearedByAwait
                    + " restored=" + Thread.currentThread().isInterrupted());
        }
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        System.out.println("SUCCESS: " + service.load("42"));

        try {
            service.load("missing");
        } catch (OrderNotFoundException ex) {
            System.out.println("NOT_FOUND: cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            service.load("offline");
        } catch (DependencyUnavailableException ex) {
            System.out.println("UNAVAILABLE: cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            service.load("");
        } catch (IllegalArgumentException ex) {
            System.out.println("VALIDATION: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("BROAD_CATCH_BUG: "
                + brokenFallback(service, "offline"));

        Thread.currentThread().interrupt();
        waitForWork(new CountDownLatch(1));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac -encoding UTF-8 BroadCatchDemo.java
java BroadCatchDemo
```

Verified standard output:

```text
SUCCESS: ORDER:42
NOT_FOUND: cause=FileNotFoundException
UNAVAILABLE: cause=IOException
VALIDATION: IllegalArgumentException
BROAD_CATCH_BUG: FAKE_SUCCESS
INTERRUPT: cleared=true restored=true
```

**Explanation:**

1. `service.load("42")` succeeds and returns a meaningful result.
2. `FileNotFoundException` is caught **before** `IOException` because it is a subclass; the service translates it into `OrderNotFoundException` and preserves the cause.
3. Other `IOException`s are translated into `DependencyUnavailableException`. The caller can distinguish a dependency error from not found.
4. Blank-input validation occurs before calling the repository; `IllegalArgumentException` is not mistakenly turned into a dependency error.
5. `brokenFallback("offline")` is **faulty code included for comparison**, returning `FAKE_SUCCESS` while the repository actually failed.
6. `CountDownLatch.await()` sees that the thread is already interrupted, throws `InterruptedException`, and clears the flag; the handler restores the flag and finishes the work. The last line confirms `cleared=true restored=true`.
7. IDs such as `42` and `missing` are dummy values. If real IDs involve personal data or secrets, do not put them into exception messages/logs by default as in this simple demo.

The code uses Java 17 with no external libraries, and does not access a real DB or network. Therefore, the output has a deterministic order and does not depend on scheduler timing.

## 7. Catch Specific Enough According to Policy, Not Necessarily Leaf Classes

"Catching narrowly" does not mean every subclass must have its own `catch`. If all `IOException`s from an API share the same handling, `catch (IOException)` is completely reasonable:

```java
try {
    remoteClient.fetch();
} catch (IOException ex) {
    throw new DependencyUnavailableException("Remote dependency failed", ex);
}
```

This snippet assumes `remoteClient` and the domain exception are already defined. However, if `FileNotFoundException` means "resource does not exist" in business terms while `SocketTimeoutException` means "slow dependency," the service may need to distinguish them.

In Java, ordering catch blocks with subclass before superclass is very important:

```java
try {
    read();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

The snippet requires importing `java.io.FileNotFoundException` and `java.io.IOException` along with the application methods. Placing `catch (IOException)` before `catch (FileNotFoundException)` will cause a compile error because the subclass branch is unreachable.

You can use multi-catch for types that **do not have a subclass relationship** if they are handled the same way:

```java
catch (SocketTimeoutException | ConnectException ex) {
    markTemporaryFailure(ex);
}
```

This snippet requires importing `java.net.SocketTimeoutException`, `java.net.ConnectException`, and defining `markTemporaryFailure`. Do not write `catch (Exception | IOException ex)` because `IOException` is a subclass of `Exception`.

Another important point is the **try scope**: if you only want to turn an I/O error into a dependency error, wrap only the I/O call in the `try` block instead of wrapping validation, business computation, notification, and cleanup as well.

## 8. Which Layers Should Own Which Error Types?

| Layer | Primary Responsibility | Action on Error |
| --- | --- | --- |
| Input validation | Validate parameters and schema | Report specific parameter errors; do not disguise them as system errors |
| Repository/adapter | Connect to database, filesystem, HTTP client | Preserve or translate dependency errors with cause |
| Service/use case | Business rules and state | Handle domain errors, decide retry/compensation when permitted |
| Controller/API boundary | Safe HTTP codes/responses | Public error codes, correlation ID, 500 fallback for unexpected errors |
| Worker/job runner | Task lifecycle management | Distinguish FAILED, CANCELLED, retryable; persist status |
| Framework/global handler | Handle unexpected failures | Report the error and keep the system in an allowed state |

This table is a **guideline**, not a mandate that an architecture must have all of these layers. The goal is for each error to have **one place responsible for handling it**, while the remaining layers do not mask it or duplicate logs needlessly.

A very effective code review question: **if we remove the catch at this layer, is any necessary action lost?** If nothing is lost other than a `"failed"` log line, the catch can likely be removed.

## 9. When Can `catch (Exception)` Be Reasonable?

Not every `catch (Exception)` is an anti-pattern. It can be appropriate at the **final boundary**, provided that expected error types have already been handled specifically, and unexpected ones are recorded as failures rather than turned into success.

### HTTP/controller boundary

```java
try {
    return handler.handle(request);
} catch (InvalidRequestException ex) {
    return badRequest();
} catch (UpstreamUnavailableException ex) {
    return serviceUnavailable();
} catch (Exception ex) {
    return internalServerError();
}
```

This is a conceptual snippet requiring definitions for the exceptions, `handler`, and response helpers. The final broad handler only deals with **unpredictable** errors: returning a safe response, not exposing stack traces or raw messages to the client, and recording the event in the responsible place.

### Transaction owner

A component that owns a transaction may need to catch errors to **attempt a rollback** and preserve the original error. It must not conclude "rolled back" merely because the handler ran, especially if rollback also throws an exception.

### Worker/job boundary

A job runner can catch unexpected errors to update the status to FAILED, preventing a failure from turning into a job SUCCESS. If the worker supports cancellation, handle `InterruptedException` or cancellation separately before using the generic fallback.

### Legacy adapter

An external API that only declares `throws Exception` can be wrapped **once** in an adapter with a new contract. Do not copy that catch across every layer of the application.

**Criteria:** have a clear policy, do not swallow errors, do not keep the process running "blindly" after an error, and do not lose information needed by the caller.

## 10. `catch (Throwable)` Is More Dangerous Because It Includes `Error`

`Error` can indicate a serious JVM or linkage failure. When receiving `OutOfMemoryError`, even the logger, fallback data structures, or retry logic may no longer have enough resources. `StackOverflowError` can occur when recursion exceeds stack capacity. `LinkageError` can be related to incompatible bytecode/classpath.

Anti-pattern:

```java
catch (Throwable error) {
    logger.warn("ignored", error);
    return defaultValue;
}
```

This is a **not-recommended** snippet. It assumes that after any error condition, it is still possible to print a log, create a fallback, and continue serving requests correctly.

There are **special boundaries** that have a reason to observe `Throwable`, such as test harnesses or plugin hosts that need to record a module's failure state. Even then, the action is usually to **report failure, isolate, or rethrow according to policy**, not to promise full recovery. If you only want cleanup regardless of exit path, `finally` and `try-with-resources` are usually the more appropriate tools.

Do not turn `catch (Throwable)` into an everywhere safety net. It cannot protect against power loss, process termination, or severe resource exhaustion, and it can create a false sense of security.

## 11. `InterruptedException` Swallowed by `catch (Exception)`

`InterruptedException` is usually a signal that a waiting thread has been asked to stop/cancel. APIs such as `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, and `Future.get` can throw it. When throwing this exception, many APIs **clear the interrupt flag** of the waiting thread.

Anti-pattern:

```java
while (true) {
    try {
        process(queue.take());
    } catch (Exception ex) {
        logger.warn("retrying", ex);
    }
}
```

This snippet assumes `queue`, `process`, and logger belong to the application. When the thread is interrupted during `take()`, the exception is caught by the generic catch; the loop continues and may block again as if it had never been asked to stop.

If a method can declare `throws InterruptedException`, it is usually better to **propagate it**:

```java
void consume(BlockingQueue<Job> queue) throws InterruptedException {
    process(queue.take());
}
```

This snippet requires importing `BlockingQueue`, and defining `Job` and `process`.

If inside `Runnable.run()`, which cannot throw checked `InterruptedException`:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            process(queue.take());
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

This snippet is inside a class with `queue` and cleanup. **Restoring the flag + exiting the execution path** is preferable to restoring and looping back into `while (true)`, because the next waiting operation might be interrupted immediately, causing a hot loop.

However, it is not mandatory to restore the flag at every layer if `InterruptedException` is already propagated per contract, or if a layer that **owns the entire cancellation protocol** has definitively handled the signal.

## 12. Catching `RuntimeException` Too Broadly Can Hide Programming Bugs

`RuntimeException` includes both unchecked domain errors and programming bugs such as `NullPointerException` and `IndexOutOfBoundsException`. The snippet:

```java
try {
    return calculateInvoice();
} catch (RuntimeException ex) {
    return BigDecimal.ZERO;
}
```

is faulty code if `calculateInvoice` returns `BigDecimal` and a bug must not be turned into a `0` invoice; requires importing `java.math.BigDecimal`.

If missing data is a valid case, the API should represent it in its contract, such as `Optional.empty()` or a domain result. If an unexpected NPE occurs, let the error reach the final boundary for investigation instead of producing incorrect financial data.

Similarly, a programming bug must be fixed at the source; do not treat every runtime exception as a transient network glitch to be retried.

## 13. Proper Cleanup Mechanisms Instead of Meaningless Catching

One reason many people catch broadly is fear of resource leaks. But if a resource implements `AutoCloseable`, Java already provides `try-with-resources`:

```java
try (InputStream in = Files.newInputStream(path)) {
    return in.read();
}
```

This snippet is in a method declaring `throws IOException` with a `Path path` variable, requiring imports for `java.io.InputStream` and `java.nio.file.Files`. The resource is closed upon leaving the block per contract, even if reading fails.

For locks:

```java
lock.lock();
try {
    mutateSharedState();
} finally {
    lock.unlock();
}
```

This snippet is inside a class with `lock` and `mutateSharedState()`. `finally` is appropriate for releasing the lock without needing a broad catch. Note that releasing the lock **does not roll back** changes made before the exception.

When both the `try-with-resources` body and `close()` fail, Java typically preserves the error from `close()` in `getSuppressed()` of the primary exception. If you write manual cleanup and cleanup throws, you must preserve the original error. Do not add `catch (Throwable)` just to reimplement a cleanup mechanism that already exists.

## 14. Transactions, Rollback, and State After Failure

Exceptions do not automatically roll back DB, file, or network operations. For example:

```java
try {
    debitAccount();   // May have already committed.
    sendReceipt();    // May fail after commit.
    return true;
} catch (Exception ex) {
    return false;
}
```

This is an anti-pattern snippet in a method returning boolean with business methods already defined. If `debitAccount` has already committed and `sendReceipt` throws, the method returns `false` while the money **may have already been debited**. A caller retrying the whole flow could debit again.

In the transaction owner, it must be clear:

1. Which operations truly belong to the **same transaction**?
2. Did the error occur before or after commit?
3. If `rollback()` also fails, has the state been verified?
4. If `commit()` loses its response, can it be known for sure whether the DB committed or not?
5. Are side effects in other systems compensated or reconciled separately?
6. Does retry have idempotency and appropriate limits?

A broad catch used to **attempt rollback and then rethrow** can be reasonable within the transaction owner's scope. However, catching does not automatically guarantee "every system was undone." If rollback throws an error, preserve the original error and the rollback failure information (e.g., `addSuppressed`) along with the uncertain state.

## 15. `Future`, `CompletableFuture`, and Asynchronous Errors

A `catch (Exception)` around task submission:

```java
try {
    CompletableFuture<Integer> future =
            CompletableFuture.supplyAsync(() -> compute());
} catch (Exception ex) {
    // Only catches synchronous errors on the submitting thread.
}
```

This snippet assumes `compute` is already defined. If `compute` later throws an exception on a worker thread, it is recorded in the future's state and **does not propagate into the catch around future creation**.

When the caller observes the result:

```java
try {
    int result = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

This snippet is in a `void` method, with `future`, `handleTaskFailure`, and importing `ExecutionException`. Distinguish `InterruptedException` of the **waiting caller thread** from `ExecutionException` whose cause comes from the worker. `CancellationException` means cancellation; `get(timeout, unit)` can also throw `TimeoutException`, which does not mean the task has stopped.

With `CompletableFuture.join()`, errors are typically reported as `CompletionException`. Use `exceptionally` or `handle` to recover only when a fallback is meaningful in business terms; if you put `exceptionally(ex -> null)` on every stage, the pipeline can finish "successfully" with invalid data.

A job scheduler also needs to know whether a task is FAILED or CANCELLED; catching broadly and returning normally can make the framework mark the job as SUCCESS and continue scheduling under the wrong policy.

## 16. Logging Exceptions: Few Log Points, Enough Context, No Data Leaks

If every layer logs and rethrows, dashboards can get ten alerts for one error. Choose **one final observation point** per request/task when possible, plus dedicated metrics/context where truly needed.

A useful policy:

- Stable domain/API error code for the caller.
- Allowlisted operation name, safe request/correlation ID.
- Retry, timeout, and dependency category information when appropriate.
- Internal `Throwable` cause preserved for diagnostics if permitted.
- Do not put passwords, tokens, cookies, raw request bodies, or personal data into exception messages/logs.

Do not return `ex.getMessage()` or `ex.toString()` directly in an HTTP response; a dependency may have embedded URLs, headers, or secrets into the message. Conversely, do not blindly strip the cause at every layer, as that makes investigation difficult. You must **distinguish between data kept inside the exception and data allowed to be emitted to sinks**.

A fallback boundary can send a safe 500 response and record an event ID; the controller does not need to re-log the entire exception that has already been fully logged elsewhere.

## 17. Checked Exceptions and Overly Broad `throws Exception` Declarations

A pattern that goes hand-in-hand with catching too broadly is:

```java
public void process() throws Exception {
    repositoryCall();
}
```

This snippet assumes `repositoryCall` is already defined. It may be acceptable in a few tests or short entrypoints, but a public API declaring only `Exception` leaves callers unaware of what conditions to prepare for, often leading to `catch (Exception)` spreading further.

A narrower contract example:

```java
void readConfig(Path path) throws IOException {
    Files.readString(path);
}
```

This snippet requires importing `java.nio.file.Path`, `java.nio.file.Files`, and `java.io.IOException`. It expresses the appropriate I/O error group. There is no need to list every subclass unless the caller has a specific policy.

If "data not found" is a normal case, consider `Optional<T>` or a domain result instead of throwing and catching across multiple layers. However, do not equate a DB connection error with `Optional.empty()`, because **not knowing whether data exists** is completely different from **knowing that no data exists**.

## 18. Retries Cannot Be Applied to Every Exception

This loop is especially dangerous:

```java
while (true) {
    try {
        return chargeCustomer();
    } catch (Exception ignored) {
        // Retry immediately, with no limit.
    }
}
```

This is an **anti-pattern snippet**, assuming the method returns the corresponding result and `chargeCustomer()` has side effects. It can retry validation bugs, exhaust CPU, or create duplicate transactions if the previous call **committed but the response was lost**.

Responsible retries must know:

- Which error types are truly transient.
- Whether the command has an idempotency key.
- Whether the outcome after a timeout is a definite failure or unknown.
- Retry budget, timeout, and backoff/jitter.
- Whether there is an `InterruptedException`/cancellation signal from the caller.
- Whether another layer is already retrying, to avoid multiplying call counts.

A method that catches broadly and retries at every layer can cause a *retry storm*. Catching specifically according to policy helps avoid this.

## 19. When Should You Log and Rethrow?

There is no need to catch just to do:

```java
try {
    call();
} catch (IOException ex) {
    throw ex;
}
```

This snippet is in a method with `throws IOException`; removing the catch does not change the basic behavior.

Catching and rethrowing is valuable when:

1. Translating an error at an adapter boundary into a domain exception, **preserving the cause**.
2. Updating a FAILED/CANCELLED status that lower layers do not own.
3. Attempting rollback in the transaction owner.
4. Adding necessary **non-sensitive** context, rather than just writing `"failed"`.
5. Recording a meaningful metric in a single place.
6. Ensuring specialized cleanup that cannot be expressed more clearly via `finally`/`try-with-resources`.

If the handler itself can throw another error while handling, you must decide how to preserve the cause/suppressed exceptions and the post-failure state. Do not claim recovery succeeded when rollback or cleanup is not guaranteed to have succeeded.

## 20. Tests to Detect Incorrect Behavior from Broad Catches

Tests should inject faults to inspect not only the exception type, but also **the state and side effects after failure**.

| Scenario | Expectation |
| --- | --- |
| Invalid input | Appropriate validation error, repository is not called |
| Data does not exist | Clear not-found contract, distinct from unavailable |
| Repository offline | Dependency error is reported, no fake success |
| `NullPointerException` bug | Not turned into `0`, `null`, or success |
| Blocking worker interrupted | Signal is not swallowed, worker terminates per policy |
| Future completes exceptionally | Caller obtains the right `getCause()` |
| Transaction fails mid-steps | Rollback within proper scope or marked unverified |
| Timeout/unknown commit outcome | No blind retry causing duplicate side effects |
| Cleanup or rollback also fails | Primary error and secondary error info are preserved |
| Logger encounters sensitive Throwable | Client/broad-access logs do not leak tokens or PII |
| Serious `Error` | No generic catch swallows it and lets the system run as success |

For `BroadCatchDemo`, the important tests are that `service.load("missing")` and `service.load("offline")` have different domain types while both preserve the cause, blank validation keeps the right type, and `brokenFallback` must be marked **intentionally faulty** when returning `FAKE_SUCCESS`.

Every test involving workers needs timeouts and cleanup so the process does not hang. Rollback tests must inspect side effects, not just `assertThrows`.

## 21. Practical Code Review Checklist

1. Every `catch` must have a **reason to handle the error at that layer**.
2. If it only rethrows as-is without adding any action, it should usually be removed.
3. Catch an exception group narrow enough per policy; subclass before superclass.
4. Do not catch `Throwable` indiscriminately; do not assume recovery from `Error` is possible.
5. Do not turn validation, dependency, cancellation, and bugs into the same vague exception.
6. When translating error types, preserve the cause and a meaningful error code.
7. Do not return fake results to mask errors where fallback is not allowed.
8. Do not swallow `InterruptedException`; propagate it or restore and stop on the proper path.
9. Use `try-with-resources`/`finally` for cleanup, not meaningless broad catches.
10. Rollback must follow transaction boundaries; catching does not automatically undo committed changes.
11. Retry only when the error and operation satisfy a safe retry policy.
12. Avoid duplicate logging across multiple layers; do not expose secrets/PII via messages and causes.
13. With futures/async, observe the asynchronous result rather than relying on catching at submission time.
14. The final boundary may have a fallback for unexpected `Exception`s, while still marking failure and returning a safe error.
15. Test expected errors, unexpected bugs, interrupts, and post-failure state.

**Conclusion:** `catch (Exception)` and `catch (Throwable)` are not insurance policies to paste into every method. Catching too broadly at every layer loses classification, hides bugs, swallows cancellation signals, causes duplicate logs, and turns failures into fake successes. Catch at **the layer that owns the handling action**, let unhandled errors continue propagating, and use the right mechanisms for cleanup, rollback, reporting, and retries.
