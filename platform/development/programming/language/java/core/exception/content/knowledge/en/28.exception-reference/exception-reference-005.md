# Decision Table for Error Handling by API or Thread Boundary

## 1. Purpose of This Lookup Table

When an error occurs in Java, the first question should not be "where do I put a catch block to make the red squiggles go away?", but rather **"which component has enough responsibility and information to decide what happens next?"**. The data access layer, business service, controller, worker thread, callback, executor, and `Future` caller do not share the same contract. An error-handling approach that is appropriate at one boundary can distort the meaning at another.

This README is a **decision lookup table for exception handling by API or thread boundary** in Java Core. It helps you choose among the following directions:

- **Propagate as-is** using `throws` or `throw e` when the caller is allowed and expected to decide.
- **Wrap with a cause** into an exception belonging to a higher abstraction when the API boundary requires it.
- **Recover with a fallback** if a genuinely valid alternative result exists according to the contract.
- **Stop the task and preserve the interrupt flag** when a callback is not allowed to throw `InterruptedException`.
- **Cancel or stop waiting** according to a specific policy, without conflating timeout, interruption, and cancellation.
- **Clean up resources / roll back** according to ownership, while preserving primary and suppressed exceptions.
- **Log, return an error result, or notify externally** at the responsible boundary, rather than logging repeatedly at every layer.

This table is a **decision framework**, not a mandatory rule requiring every system to use a specific exception type or status code. For example, HTTP statuses 400/503 in the program are illustrative mappings, not an automatic Java rule.

**Guiding rule:** Intermediate layers should generally **preserve error information and pass it to the layer that can make the decision**. The layer that owns the lifecycle of the request, job, or task decides whether to stop, retry, fall back, return a response, or raise an alert.

## 2. Identify the Boundary Before Deciding to Catch

A **boundary** is where responsibility or contract changes. Examples include:

| Boundary | Who is calling whom? | What the receiving side can actually decide |
| --- | --- | --- |
| Internal method | Helper → another helper | Precondition checks, adding context, or rethrowing |
| I/O adapter | Repository → filesystem/network/database | Translating I/O errors into the adapter contract, managing owned resources |
| Service | Controller/job → business service | Business rules, atomicity, whether recovery is possible |
| Public API | Client → public API | Committed exception types or a stable error result type |
| HTTP controller | Remote caller → endpoint | Response code, safe error payload, correlation ID |
| Runnable | Executor/thread → `Runnable.run` | Cannot declare checked exceptions on `run` |
| Callable | Executor → `Callable.call` | Can throw `Exception`; executor can store the failure in a `Future` |
| `Future.get` | Caller thread → `Future` | Wait for result; observe task failure via `ExecutionException` |
| `CompletableFuture.join` | Caller thread → `CompletionStage` | Observe normal exceptional completion via `CompletionException` |
| Callback/event handler | Framework → callback | Follow the framework signature, avoid breaking the event loop |
| Thread boundary | Worker ↔ supervisor | Observe termination, interruption, uncaught exceptions, and worker lifecycle |
| Resource boundary | Owner → `AutoCloseable` | Close at the right time, preserve primary/cleanup errors |
| Transaction boundary | Unit of work → database | Commit/rollback/compensation per contract |
| Service-to-service | Application → dependency | Deadlines, bounded retries, idempotency, external system errors |

A **catch** block should only appear when that layer can do something useful: proper recovery, abstraction translation, responsible cleanup, or routing the error to a coordinating system. **Catching and continuing as if nothing happened** is not the default choice.

## 3. Quick Decision Table — Choosing How to Handle by Scenario

| Scenario | Responsible boundary | Preferred choice | Avoid |
| --- | --- | --- | --- |
| Helper receives invalid input | Method/API owning validation | Throw the contracted input exception, usually `IllegalArgumentException` or a subtype | Throwing an unrelated I/O error; masking invalid data with `null` |
| Caller invokes a helper that `throws IOException` | Caller/upper layer allowed to receive checked exceptions | Let `IOException` propagate if unable to decide yet | Catching just to `printStackTrace` and returning success |
| Repository raises a storage-layer error | Adapter/service boundary | Keep `IOException`/`SQLException` or wrap into a domain/infrastructure exception **with cause** per contract | Creating a generic `RuntimeException` without a cause |
| Service has a genuinely equivalent fallback | Service authorized for recovery | Return a valid fallback and record degraded mode if needed | Falling back for every error, including data integrity errors |
| Service violates an invariant | Business boundary | Throw an exception type representing the invalid state | Retrying infinitely on a condition that cannot self-heal |
| Controller receives invalid input | Controller/API boundary | Translate into a client error response per API rules | Returning a success status or exposing stack traces |
| Dependency is temporarily unavailable | Boundary with retry policy | Bounded retry **if the operation is safe/idempotent**, or return an availability error | Retrying all `Throwable` |
| `Runnable` encounters `InterruptedException` | `Runnable.run` does not declare checked exceptions | Restore `Thread.currentThread().interrupt()` and exit per contract | Swallowing interruption and continuing the wait loop |
| Method allowed to `throws InterruptedException` | Caller layer that knows how to handle it | Propagate as-is | Restoring the flag and continuing to block without reason |
| `Callable` throws an exception | `Callable.call` has `throws Exception` | Let the exception propagate out if the executor manages the result | Assuming the `Future.get` caller receives the worker error directly |
| `Future.get` reports `ExecutionException` | Caller thread reading the task | Inspect `getCause()`, decide at the caller | Treating `Future.get` itself as the site of the original bug |
| `Future.get` throws `InterruptedException` | Caller thread interrupted while waiting | Propagate or restore the flag at the appropriate boundary | Assuming the task has definitely been canceled |
| `Future.get(timeout)` reports `TimeoutException` | Caller wait timed out | Stop waiting/apply deadline; consider canceling based on ownership | Thinking timeout automatically cancels the task |
| `CompletableFuture.join` reports `CompletionException` | Consumer stage | Inspect cause, distinguish recoverable errors | Catching only `CompletionException` and ignoring cancellation |
| `Future` was canceled | Caller/worker boundary | Handle `CancellationException` and cancellation state separately | Claiming the worker has stopped or rolled back |
| `try-with-resources` body and `close` both fail | Resource boundary | Keep body error as primary, `close` error as suppressed | Letting `finally` `close` mask the body error |
| Transaction fails | Transaction owner | Appropriate rollback/compensation, preserve rollback error | Assuming `close` automatically rolls back all changes |
| Uncaught exception in a worker thread | Thread/supervisor boundary | Observe, mark job failed, manage worker lifecycle | Relying on the main thread to always see worker errors |
| Serious `Error` | Diagnostic/operational boundary | Let it propagate and perform necessary cleanup when safe | Catching `Throwable` and returning a fallback like a normal error |

**How to read the table in order:** identify the **actual scenario** → identify **who owns the work/resource** → choose the **error contract** → determine **whether recovery is possible** → preserve **cause/interrupt/state** → write tests to verify.

This table is a guide for Java 17+, and does not guarantee identical behavior when using frameworks with their own policies. For example, an executor may catch exceptions, an HTTP mapper may be customized, or an API may return a `Result` instead of throwing; in those cases, follow the application's official contract.

## 4. Question-Based Decision Flow

When encountering an exception, ask sequentially:

**Question 1 — Is this a normal condition that can be returned as a result?** If "not found" is an expected state, you can use `Optional`/`Result` or a meaningful value. There is no need to create exceptions just to represent every control-flow branch.

**Question 2 — Does this layer have the authority and capability to recover?** If a valid fallback, controlled retry, or proper compensation step is known, it can be handled here. Otherwise, pass the error to the caller.

**Question 3 — Does the error cross an abstraction boundary?** In a public API, it is not necessary to expose a specific `SQLException`/provider type. You can wrap it into a domain or infrastructure-level exception, **but you must preserve the cause**.

**Question 4 — Does the signature allow checked exceptions?** Regular methods can declare `throws`; `Runnable.run` and many callbacks cannot. When direct propagation is not possible, there must be a clear conversion or termination policy.

**Question 5 — Are timeout, interrupt, or cancel involved?** These three events are distinct. A wait timing out does not prove the task has finished. Interruption belongs to the waiting thread. Cancellation belongs to the `Future` state or task cancellation mechanism.

**Question 6 — Are there resources or side effects to clean up?** Cleanup and rollback must be handled by the owner; a propagating exception does not automatically revert state.

**Question 7 — Who logs and who reports the final outcome?** The boundary layer can log once, return an API response, complete a `Future` exceptionally, or report job status. Do not log duplicates just because each layer has a `catch`.

If the answer to Question 2 or 6 is "don't know", **do not turn the exception into success**. Preserve the cause information and let the authorized layer handle it.

## 5. Choosing Between `throws`, `throw e`, Wrapping, and Fallback

| Approach | When appropriate | What must be preserved |
| --- | --- | --- |
| Declare **`throws IOException`** | Caller can handle I/O errors; abstraction allows it | Checked exception type and original stack trace |
| Do not catch; let exception propagate | Intermediate layer adds no policy | Do not alter the `Throwable` |
| **`catch(E e) { throw e; }`** | Need brief handling before propagating | The exact `e` object and any cleanup errors |
| **`throw new DomainException(..., e)`** | Boundary translates infrastructure error to business error | Cause, appropriate context, and new contract |
| **`return fallback`** | Layer has a genuinely valid alternative result | Error classification, recording degraded behavior when needed |
| **`completeExceptionally(e)`** | `CompletableFuture` API actively signals failure | Primary `Throwable` and completion semantics |
| **`Thread.currentThread().interrupt(); return;`** | Boundary cannot `throws InterruptedException` and policy is to stop | Interrupt flag and cleanup |
| **`return Result.failure(code)`** | API is designed to represent failure as a value | Structured error code, information for caller |
| **Bounded retry** | Transient error, operation is safe to retry | Budget, deadline, idempotency, and final cause |
| **`try-with-resources`** | Resource is scoped and `AutoCloseable` | Close on all exit paths, primary/suppressed |

Avoid **wrapping an exception multiple times at every layer** if the wrapper adds no value. Each wrapper makes the cause chain more complex and logs harder to read. Only wrap where the abstraction genuinely changes or the caller needs new contextual information.

If a wrapper has a cause, the caller needs to check **`getCause()`**. Simply throwing **`new RuntimeException(e.getMessage())`** loses the original error object and its stack trace/cause.

## 6. Checked and Unchecked Exceptions by API Boundary

**Checked exceptions** such as `IOException`, `SQLException`, `InterruptedException`, `ExecutionException`, and `TimeoutException` require the caller to catch or declare them per compiler rules.

**Unchecked exceptions** include `RuntimeException` and its subclasses (`IllegalArgumentException`, `IllegalStateException`, `NumberFormatException`, `CancellationException`, `CompletionException`), as well as `Error`. The compiler does not force callers to handle them, but that does not make the errors disappear.

Selection table:

| API kind | Common design | Notes |
| --- | --- | --- |
| Java Core API with interruptible blocking operations | Declare **`throws InterruptedException`** | Give caller the authority to cancel/wait |
| File read/write API | **`throws IOException`** or explicit error result | Do not disguise I/O errors as invalid arguments |
| Validation helper | **`IllegalArgumentException`** / subtype | Distinguish bad input from system errors |
| Method with mandatory invariants | **`IllegalStateException`** or custom type | Do not silently turn into an ambiguous fallback |
| Public library API with multiple implementations | Stable exception types per contract | Do not force callers to depend on vendor exceptions |
| Framework callback without checked `throws` | Exit/restore interrupt, or unchecked wrapper if contract allows | Do not add `throws` to an overridden method against its signature |
| Async API returning `CompletableFuture` | Exceptional completion/cancellation state | Consumers must observe via `get`/`join`/handler |
| Data-oriented API with `Result` | Return structured error code/info | Do not simultaneously signal success and ambiguous failure |

**Do not classify using a generic `catch(Exception)` and decide every error should be retried.** Checked vs. unchecked is only one dimension; what matters more is **the meaning of the exception in the specific contract**.

## 7. Synchronous Boundary: helper → repository → service → API

A simple call path:

~~~text
Caller / Controller
       |
       v
Application Service
       |
       v
Repository / Adapter
       |
       v
I/O, filesystem, network, database
~~~

At the repository layer, I/O errors can be propagated via `IOException` or mapped to the adapter's public infrastructure exception. At the service layer, if business logic cannot proceed, preserve the error or add necessary context. At the controller layer, it can be translated into an external error response.

Illustrative example:

~~~java
// Illustrative code in a Java context.
static String repository(String key) throws IOException {
    if (key.equals("down")) {
        throw new IOException("storage unavailable");
    }
    return "value:" + key;
}

static String service(String raw) throws IOException {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("id required");
    }
    return repository(raw.trim());
}
~~~

Here, **service** does not catch `IOException` because the example gives the caller the authority to decide. When the caller is an HTTP boundary, it can map `IllegalArgumentException` to a client error and `IOException` to an availability error.

**Warning about status codes:** HTTP statuses and payloads must be based on API rules, security, request semantics, and system policy. There is no Java Core rule that every `IOException` is 503 or every `IllegalArgumentException` is 400. In the runnable example below, the numbers merely show that *the choice sits at the boundary*.

## 8. Complete Java 17+ Example: Boundaries and Concrete Results

The following program uses Java SE to construct independently verifiable cases:

1. Request boundary illustrating mapping of invalid input and unavailable dependency.
2. Resource boundary keeping the work exception as primary and the close error as suppressed.
3. `Runnable` boundary restoring the interrupt flag and terminating.
4. `Callable` throwing `IOException` in an executor; caller reading `Future` receives `ExecutionException` with cause.
5. `CompletableFuture` completing exceptionally: **`get`** and **`join`** return different wrappers but the same cause.
6. Canceled `Future` reports `CancellationException`; a timed `get` reports `TimeoutException` without the task canceling itself.

Save the file **ErrorBoundaryDecisionDemo.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class ErrorBoundaryDecisionDemo {
    static String repository(String key) throws IOException {
        if (key.equals("down")) {
            throw new IOException("storage unavailable");
        }
        return "value:" + key;
    }

    static String service(String raw) throws IOException {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return repository(raw.trim());
    }

    static String requestBoundary(String raw) {
        try {
            return "200 " + service(raw);
        } catch (IllegalArgumentException badInput) {
            return "400 " + badInput.getMessage();
        } catch (IOException unavailable) {
            return "503 " + unavailable.getMessage();
        }
    }

    static final class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void transactionLikeWork() throws IOException {
        try (BrokenClose resource = new BrokenClose()) {
            throw new IOException("work failed");
        }
    }

    static void interruptBoundary() throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        AtomicBoolean restored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try {
                ready.countDown();
                gate.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        });
        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("runnable restored=" + restored.get());
    }

    static void futureBoundary() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> task = pool.submit(() -> {
                throw new IOException("task I/O");
            });
            try {
                task.get();
            } catch (ExecutionException failure) {
                System.out.println("future cause="
                        + failure.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdownNow();
        }
    }

    static void completionBoundary() throws InterruptedException {
        CompletableFuture<String> failed = new CompletableFuture<>();
        IOException original = new IOException("async I/O");
        failed.completeExceptionally(original);
        try {
            failed.get();
        } catch (ExecutionException wrapper) {
            System.out.println("get cause original="
                    + (wrapper.getCause() == original));
        }
        try {
            failed.join();
        } catch (CompletionException wrapper) {
            System.out.println("join cause original="
                    + (wrapper.getCause() == original));
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        canceled.cancel(false);
        try {
            canceled.join();
        } catch (CancellationException failure) {
            System.out.println("canceled=" + failure.getClass().getSimpleName());
        }

        CompletableFuture<String> pending = new CompletableFuture<>();
        try {
            pending.get(1, TimeUnit.MILLISECONDS);
        } catch (ExecutionException failure) {
            throw new AssertionError("Unexpected completion", failure);
        } catch (TimeoutException expected) {
            System.out.println("timed wait=" + expected.getClass().getSimpleName());
        }
        pending.complete("later");
        System.out.println("after timeout=" + pending.join());
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("request ok=" + requestBoundary(" 42 "));
        System.out.println("request invalid=" + requestBoundary(" "));
        System.out.println("request storage=" + requestBoundary("down"));
        try {
            transactionLikeWork();
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            System.out.println("suppressed="
                    + primary.getSuppressed()[0].getMessage());
        }
        interruptBoundary();
        futureBoundary();
        completionBoundary();
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac --release 17 ErrorBoundaryDecisionDemo.java
java ErrorBoundaryDecisionDemo
~~~

Verified stdout when compiled/run:

~~~text
request ok=200 value:42
request invalid=400 id required
request storage=503 storage unavailable
primary=work failed
suppressed=close failed
runnable restored=true
future cause=IOException
get cause original=true
join cause original=true
canceled=CancellationException
timed wait=TimeoutException
after timeout=later
~~~

**Note about the program:** There is no real HTTP server; the strings **200/400/503** are illustrative outputs showing how a boundary can map errors according to policy. **transactionLikeWork** only simulates a resource scope, not a real transaction or rollback. Both are named to evoke responsibility boundaries, not to claim that a framework handles them this way automatically.

## 9. Interpreting Results Across Boundaries

**request ok:** The service returns a normal result, and the boundary prepends an illustrative success status prefix.

**request invalid:** Blank input causes the service to throw `IllegalArgumentException`; the boundary **has enough information** to translate it into a client error status. Do not expose Java stack traces as public payloads.

**request storage:** The repository throws `IOException`. The service lets the error propagate, and the boundary illustrates a 503 response. In a real application, the mapper must check whether the error is truly temporary unavailability; the same `IOException` could be caused by an invalid path, permission error, disk failure, or an unavailable dependency.

**primary/suppressed:** TWR keeps `IOException` **work failed** as the primary error, and **close failed** as suppressed. If the controller log ultimately only records the primary message without passing the `Throwable`, the cleanup error is lost.

**runnable restored=true:** The worker waiting on `CountDownLatch` receives an interrupt. Because `Runnable.run` cannot declare checked `InterruptedException`, the catch block restores the flag and exits. `main` uses `join` to observe the result after the worker has terminated. In production, appropriate cleanup for the actual task is needed.

**future cause=IOException:** The `Callable` in the executor throws `IOException`. `ExecutorService.submit` stores the failure result in the `Future`, and the caller of `Future.get` catches `ExecutionException` to find the `IOException` in the cause.

**get/join cause original=true:** Two APIs observe the same `CompletableFuture` that was completed via `completeExceptionally` with an `IOException`. `get` reports `ExecutionException`, `join` reports `CompletionException`, but the cause is the exact same original `IOException` object.

**canceled:** The `Future` was canceled directly. `join` throws `CancellationException`; you cannot conclude from this line that any worker stopped, because the example `CompletableFuture` has no actual worker.

**timed wait/after timeout:** A timed `get` waits on an incomplete `CompletableFuture`. `TimeoutException` only ends that wait call; afterward, **`complete("later")`** still succeeds and `join` receives the result.

These scenarios are constructed deterministically: latches and `Future` states are explicit, without relying on random `Thread.sleep` calls hoping a race occurs.

## 10. Decision Table: Regular Java Methods and Library APIs

| Condition | Contract the method should express | Handling at the layer under consideration |
| --- | --- | --- |
| Invalid input | Well-defined input exception or `Result.failure` | Validate early, safe message, test the exact subtype if needed |
| Method can be interrupted while waiting | `throws InterruptedException` when appropriate | Let the caller decide to stop/cancel |
| I/O failure | `throws IOException` or infrastructure error with cause | Do not turn into `null` if `null` has a normal meaning |
| State invariant violated | `IllegalStateException` / custom domain type | Do not retry blindly |
| An optional operation may lack data | `Optional`/`Result` if missing is normal | Do not use exceptions as common control flow unnecessarily |
| Code may mutate state before failing | Exception safety/transaction contract | Prepare before publishing, roll back if guaranteed |
| Public API does not want to expose vendor exceptions | Wrapper belonging to the public abstraction | Keep original in `cause`, do not lose stack trace |

**Propagating checked exceptions** is often reasonable when an intermediate layer lacks sufficient context. Conversely, a public API needing a stable error vocabulary may wrap exceptions from underlying libraries, provided it preserves the cause and documents the meaning.

**Do not throw a generic `RuntimeException` just to avoid declaring `throws`.** That is a contract design decision, not a way to dodge the compiler. A `RuntimeException` without a cause can cause callers and logging systems to lose critical information.

## 11. Decision Table: `Throwable` Types for Error Outcomes

| Observed type | Typically describes | Handling direction |
| --- | --- | --- |
| `IllegalArgumentException` | Caller violated a precondition | Fix input, return validation error at API boundary |
| `NumberFormatException` | Invalid numeric string conversion | Report format error; do not treat as infrastructure failure |
| `IllegalStateException` | Object state does not allow the operation | Check invariant/lifecycle; fix logic or reject validly |
| `IOException` | I/O error per API contract | Classify transient/permanent based on cause and context |
| `SQLException` | Error per JDBC/database contract | Transaction, timeout, retry policy based on `SQLState`/provider |
| `InterruptedException` | Waiting caller/worker thread received an interrupt | Propagate when allowed or restore flag at boundary |
| `TimeoutException` | Wait call timed out or represented timeout failure | Check deadline and task ownership, distinguish wrappers |
| `ExecutionException` | `Future.get` reporting task failure | Inspect `getCause()` |
| `CompletionException` | `CompletionStage`/`join` propagating exceptional completion | Inspect `getCause()` |
| `CancellationException` | `Future` was canceled or completion was canceled | Distinguish cancellation from business errors |
| `Error` | Serious runtime error condition | Avoid catching as fallback; safe cleanup when appropriate |

This table does not replace an API contract. For example, a **`TimeoutException`** can be a direct exception from `get(timeout)` or the **`cause`** of an `ExecutionException` when a `CompletableFuture` completes exceptionally via **`orTimeout`**. The same class can appear at two boundaries with different handling semantics.

## 12. `Runnable` Boundary: Cannot Throw Checked Exceptions

**`Runnable.run()`** has a signature that declares no checked exceptions:

~~~java
// Conceptual signature of Runnable.
void run();
~~~

A `Runnable` lambda that wants to call a method that `throws InterruptedException` must catch the exception or translate it per contract. A common policy when interruption means a stop request:

~~~java
// Illustrative code inside a Runnable.
try {
    blockingOperation();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

**Why restore the flag?** Many blocking APIs such as `CountDownLatch.await()` clear the interrupt status when throwing `InterruptedException`. If you cannot propagate the checked exception out of `run`, restoring the flag preserves the signal for coordinating code or authorized layers to observe later.

**Do not restore the flag and continue an infinite blocking loop** unless there is a specific policy; subsequent blocking calls may throw immediately or the task may continue running against the stop request. Catching and ignoring it loses the signal and can cause shutdown to hang.

If a callback cannot return by design, you can use an adapter or an unchecked wrapper with a cause per the framework contract. However, do not use **`IllegalStateException`** as an undocumented "standard cancellation type"; the framework's cancellation mechanism may have its own types/semantics.

## 13. `Callable`, `ExecutorService`, and Task Errors

**`Callable<V>.call()`** declares **`throws Exception`**, so a `Callable` can propagate checked `IOException` or `InterruptedException` out of `call`.

~~~java
// Illustrative code with an existing ExecutorService pool.
Future<String> future = pool.submit(() -> {
    throw new IOException("remote failure");
});
~~~

When a task completes exceptionally, a caller observing it via **`future.get()`** typically receives **`ExecutionException`** containing `IOException` in **`getCause()`**. The caller does not receive `IOException` directly through the `Future.get` signature.

| Launch API | Where errors are commonly observed | Notes |
| --- | --- | --- |
| `Thread.start` with `Runnable` | Uncaught exception handler if the error escapes `run` | Does not automatically return a `Future` |
| `ExecutorService.execute(Runnable)` | Depends on executor/thread factory/uncaught handler/logging policy | Does not provide a `Future` from `execute` |
| `ExecutorService.submit(Runnable)` | `Future.get` reports `ExecutionException` when task throws | Error may be captured and not reach uncaught handler as expected |
| `ExecutorService.submit(Callable)` | `Future.get` reports `ExecutionException` with cause from `Callable` | `Callable` is allowed to `throws Exception` |
| `invokeAll` | List of `Future`s; must call `get` on each `Future` | Do not infer all tasks succeeded just because `invokeAll` returned a list |
| `invokeAny` | Returns result of one successful task; throws if contract not met | Read semantics and cancellation of remaining tasks |

**Do not rely on `Thread.UncaughtExceptionHandler` as the sole mechanism for catching errors in submitted tasks.** Executors typically record errors into the `Future`. If the caller never calls `get` or attaches an observing callback, the error can go unnoticed operationally even though the `Future` completed exceptionally.

Similarly, **`execute`** does not guarantee the same error-reporting behavior as **`submit`**. An implementation may log it, pass it to a handler, or manage threads in its own way. When choosing a policy, verify the executor implementation, thread factory, error handler, and where the caller actually observes the result.

## 14. Decision Table: `Future.get` and the Caller Thread

| Scenario | `get` / `get(timeout)` behavior | Action at caller |
| --- | --- | --- |
| Task completes normally | Returns `T` | Process result |
| Task throws a normal error | `ExecutionException` | Inspect `getCause`; decide recovery or report failure |
| `Future` was canceled | `CancellationException` | Handle canceled state, do not treat as a result |
| Caller thread interrupted while waiting | `InterruptedException` | Propagate/restore flag and exit per contract |
| `get(timeout)` expires | `TimeoutException` | Stop waiting; owner decides whether to cancel or return deadline error |
| `Future` not yet complete but caller stops waiting | Task may still be running | Do not infer side effects have stopped |

**Two directions of interruption must be kept separate:**

1. **Caller interrupted during `future.get()`** → the `get` method itself can throw `InterruptedException` directly.
2. **Worker `Callable` itself throws `InterruptedException`** → if the task is recorded as a failure and not canceled, `get` typically throws `ExecutionException` with **`InterruptedException` as its cause**.

Merely seeing the word `InterruptedException` in logs without identifying which object threw it can lead to the wrong policy. A worker error is not always a request to stop the thread waiting for the result.

If a deadline is needed, consider **`get(timeout, unit)`** and the overall budget. A series of retries with individual timeouts does not guarantee an overall deadline if the total time exceeds the request budget.

## 15. Decision Table: `CompletableFuture` and `CompletionStage`

| Usage | Represented error | Common policy |
| --- | --- | --- |
| **`completeExceptionally(failure)`** | `Future` completes exceptionally with `Throwable` | `Future` creator actively signals failure |
| **`CompletableFuture.get()`** | `ExecutionException` on normal exceptional completion | Caller checked exception; extract cause |
| **`CompletableFuture.join()`** | `CompletionException` on normal exceptional completion | Caller unchecked exception; extract cause |
| **`cancel(...)`** on root `Future` | `CancellationException` when observing canceled `Future` | Do not assert computation was definitely interrupted |
| **`exceptionally(fn)`** | Can transform failure into a fallback stage | Only recover allowed error types |
| **`handle((value,error) -> ...)`** | Runs on success or failure | Distinguish value/error, avoid accidentally swallowing cancellation |
| **`whenComplete((value,error) -> ...)`** | Observation callback, usually does not recover value | Do not let logging throw a new exception unnecessarily |
| **`orTimeout(...)`** | Can complete the `Future` itself exceptionally with `TimeoutException` | Distinguish from `get(timeout)` which only ends the wait |
| **`completeOnTimeout(value,...)`** | Can complete the `Future` itself normally with a fallback | Do not assert the underlying supplier has stopped |
| **`allOf(...)`** | Composite `Future` completes when all corresponding `Future`s complete | When partial results are needed, inspect each `Future` |

**Important:** **`CompletableFuture.cancel(true)`** does not have the same computation-interruption guarantee as `FutureTask`'s cancellation mechanism; per the `CompletableFuture` contract, the `mayInterruptIfRunning` parameter is not used to control execution. To genuinely stop a task, you need a separate cooperative cancellation mechanism or to manage the underlying `Future`/executing task.

With **`get()`**, the caller's checked exceptions can be `InterruptedException` or `ExecutionException`; with **`join()`**, there is no checked `InterruptedException` in the signature. Do not choose `join` just to avoid thinking about cancellation or failure.

### Observing Errors at the Right Stage

A dependent stage can receive an exceptional completion due to upstream cancellation and wrap `CancellationException` inside `CompletionException`. Therefore, **`catch(CancellationException)`** on the root `Future` and observing a downstream stage are two different contexts. When debugging, inspect the **right `Future`** and the cause relationship before choosing a branch.

## 16. Timeout, Interruption, and Cancellation Must Not Be Conflated

These three concepts often appear together but have different semantics:

**Timeout:** A wait call or operation exceeds a configured duration. With **`Future.get(timeout)`**, the caller stops waiting, but the `Future` is not necessarily completed or canceled. If **`CompletableFuture.orTimeout`** is applied, the `Future` itself can be completed exceptionally with `TimeoutException`; that is a different completion state.

**Interruption:** A thread has received an interrupt request. Interruptible blocking APIs can throw `InterruptedException` and clear the flag per contract. The caller/callback must decide whether to propagate or restore the flag.

**Cancellation:** A `Future` or task has been requested to cancel. A `Future` can transition to the canceled state before the worker actually stops or before side effects finish. **`cancel(true)`** can only request an interrupt in suitable implementations; it is not a rollback command.

Decision table:

| Observation | Do not infer | Direction to clarify |
| --- | --- | --- |
| `get(timeout)` throws `TimeoutException` | Task has stopped | Deadline, owner of the `Future`, whether it can be canceled |
| Waiting thread throws `InterruptedException` | `Future` was canceled | Whether the caller has authority to cancel the `Future` |
| `Future.isCancelled()` is true | Worker has definitely stopped | Whether the task cooperates with cancellation |
| `CompletableFuture` `orTimeout` completes exceptionally | Supplier was interrupted | How the underlying work is terminated |
| `Future.get` throws `ExecutionException` | Caller is being interrupted | Which worker the actual cause belongs to |

Do not use "timeout" as a default reason to retry every operation with side effects. If the server already processed the request but the caller did not receive the response, retrying can create duplicate transactions. Use an idempotency key and an appropriate at-least-once/at-most-once policy.

## 17. Choosing Where to Recover: Fallback Is Not Always Success

A valid fallback must answer: **when using the alternative result, do invariants and commitments to the caller still hold?**

Reasonable examples:
- A non-critical data-reading service may return a cached copy still within an acceptable age limit.
- An optional recommendation feature may omit recommendations while keeping core functionality intact.
- A job may be retried after a transient network error when the operation is idempotent and within deadline.

Dangerous examples:
- Returning an empty list when the database times out, leading the caller to think the user has no data.
- Returning success after a commit error, when the transaction state is uncertain.
- Ignoring `InterruptedException` and continuing processing even though the supervisor requested a stop.
- Catching `Throwable` to turn every error, including `OutOfMemoryError`, into a fallback.
- Turning an authorization error into "not found" without a clear security policy.

A fallback should have **clear semantics**: whether stale data is allowed, whether degraded mode is flagged, which metrics are recorded, and which errors must not be recovered.

With `CompletableFuture.exceptionally`, the callback receives a `Throwable`; it may be a wrapper or the cause depending on the stage. Do not check only **`failure.getMessage()`**. Classify by appropriate class/cause, preserve unrecoverable errors, and do not turn cancellation into a fallback if the application does not allow it.

## 18. Retry Rules by Error Type and Ownership

| Condition | Retry? | Reason |
| --- | --- | --- |
| Consistently invalid input | No | Retrying the same input will not fix it |
| Internal invariant violation | Not by default | Logic or state needs fixing |
| Transient connection error | Possible | Only if retry is safe and budget remains |
| Timeout after a request with side effects | Very cautiously | Remote result may already be committed |
| Deadlock/optimistic concurrency conflict | Per contract | May retry the transaction from the start with a limit |
| `InterruptedException` from canceled request | Usually stop | Do not ignore the interrupt request |
| `CancellationException` | Usually do not auto-retry | Need to know who requested cancellation |
| `SQLException` | Depends on `SQLState`/provider and transaction | Not every `SQLException` is transient |
| `Error`/JVM failure | Do not retry as business logic | May affect runtime safety |

Retries must be **owned at one clear boundary**; avoid having the repository retry three times, the service retry three times, and the HTTP gateway retry three times, causing an unintended multiplication of total attempts.

Apply an attempt limit, an overall deadline, backoff with jitter, and idempotency when needed. When retries are exhausted, report the final exception and relevant attempt context per diagnostic policy; do not just "return null" or drop the cause.

If an operation has a transaction, you may need to **start a new unit of work** instead of continuing to use a failed transaction/connection. The decision depends on the API contract and resource state.

## 19. Decision Table: HTTP/Controller or Public Interface

| State/condition | Illustrative response | What not to do |
| --- | --- | --- |
| Malformed input or validation violation | 400-series per contract | Leak stack trace/SQL/internal paths |
| Unauthorized per access control | 401/403 depending on authn/authz meaning | Arbitrarily map all errors to 404 |
| Resource does not exist | 404 if endpoint semantics fit | Use 404 for unknown storage errors |
| State conflict | 409 if contract specifies | Auto-retry and hide conflict without a policy |
| Dependency temporarily unavailable | 503 or API-defined error code | Default to treating every `IOException` as transient |
| Unexpected system processing error | 500-series, correlation ID | Return HTTP 200 with a fake success payload |
| Caller canceled/timed out | Per gateway/server contract | Claim for certain that the task rolled back |
| Allowed fallback | Success marked degraded if contract requires | Return incomplete data without the caller knowing |

This table is meant to illustrate the principle of **translating errors at the communication boundary**, not a mandatory REST specification. An application may choose custom error codes, gRPC statuses, or a `Result` object instead of HTTP. In any choice, do not force consumers to guess from the English message of an internal Java exception.

Log the **full `Throwable` internally** with non-sensitive context; return to the client a **stable error code, appropriate details, and request/correlation ID**. Do not print exception stack traces, credentials, or raw SQL in public responses.

## 20. Resource Boundary: Closing Properly Is Not Rollback

When a method **owns an `AutoCloseable`**, prefer:

~~~java
// Illustrative code in context; resource implements AutoCloseable.
try (Resource resource = openResource()) {
    process(resource);
}
~~~

If `process` throws A and `close` throws B, Java keeps **A as primary** and B as **suppressed**, when suppression is enabled. With multiple resources, they are closed in reverse declaration order, and resources that opened successfully are still cleaned up even if opening a subsequent resource fails.

By contrast:

~~~java
// Anti-pattern.
Resource resource = openResource();
try {
    process(resource);
} finally {
    resource.close();  // May mask the process error if close also throws.
}
~~~

A cleanup error can overwrite the original error. TWR preserves diagnostic information better. In the runnable example, `work failed` remains primary, and `close failed` is suppressed.

**When not to use TWR directly:** Resources borrowed from a caller, resources outliving the method, framework-managed lifecycles, an async callback that still needs the resource, or APIs that only provide `unlock`/`release` with specific semantics. Syntactically valid TWR with wrong ownership is still a bug.

**Transactions:** Closing a JDBC `Connection` does not guarantee a successful transaction rollback across all providers/pools. You need a **commit, rollback, or compensation** policy managed by the transaction owner. Calling `addSuppressed` for a rollback error preserves error information; it does not prove the rollback completed.

## 21. Logging, Metrics, and Observability by Boundary

There should be one point responsible for **recording the final outcome** of a request/job/task. Lower layers can add context if genuinely useful, but it is unnecessary to log the same `Throwable` in every `catch` and then rethrow.

When wrapping:

~~~java
// Illustrative code.
throw new IllegalStateException("Operation failed", original);
~~~

Passing `original` as the cause preserves the error's origin. At the logging boundary, the logger should receive the **`Throwable` object**, not just a string message. If you only log **`failure.getMessage()`**, **`Caused by`**, **`Suppressed`**, and source stack frames can be lost.

For async work, observing **exceptional completion** is mandatory if the system needs to know whether a task failed. An unawaited `Future` or a `CompletableFuture` without a handler/monitor can complete exceptionally without the outer boundary noticing in the way you expect.

Fields worth including in structured logs when appropriate: operation, component, stage, `Throwable` type and cause, request/job ID, retry count, deadline, cancellation state, elapsed time, and business error code. **Do not put passwords, access tokens, personal data, or sensitive raw requests into messages/causes/logs.**

A practical rule of thumb is **add context at the layer that knows the context, decide at the responsible layer, and log at the layer that actually observes the final outcome**.

## 22. Testing the Decision Table with Concrete Scenarios

A strong test suite should verify both the exception type and the boundary's consequences. Reference matrix:

| Scenario to test | Key assertion |
| --- | --- |
| Null/blank input | Correct input exception type or validation response per contract |
| Repository throws `IOException` | Service does not swallow; API maps per policy |
| Worker `Callable` throws `IOException` | `Future.get` throws `ExecutionException`, cause is `IOException` |
| Caller interrupted in `get` | `InterruptedException` per caller contract; interrupt flag policy is correct |
| `Runnable` `await` interrupted | `Runnable` does not swallow, restores flag/exits per contract |
| `CompletableFuture` `completeExceptionally` | `get`/`join` have appropriate wrappers and preserve original cause |
| `Future` canceled | `CancellationException` / `isCancelled` state is correct |
| `get(timeout)` on pending `Future` | `TimeoutException`, `Future` is not auto-canceled |
| Body and `close` both throw | Body is primary, `close` is suppressed |
| Opening second resource fails | Previously opened resource is still cleaned up |
| Retry on transient error | Bounded attempts, deadline, no duplicate side effects |
| Valid fallback | Appropriate value/mode, upstream failure still recorded if needed |
| Transaction rollback fails | Primary error and rollback error preserved; state not falsely reported as success |
| Public boundary | Error code/payload does not leak sensitive information |
| Async task not awaited directly | Mechanism exists to observe failure per contract |

Do not write a test with only **`assertThrows(Exception.class)`** and conclude all error cases are covered. **`assertThrows`** in JUnit Jupiter accepts subtypes; **`assertThrowsExactly`** requires the exact runtime class when supported by the JUnit version. When an API commits to an exception family, accepting subtypes may be right; when the contract demands an exact class, an overly broad assertion can create false positives.

For asynchronous errors, prefer deterministic coordination with `CountDownLatch`, completed `CompletableFuture`s, or a suitable test executor. Using `Thread.sleep` with guessed durations is a source of flaky tests.

## 23. Common Anti-Patterns to Avoid

**`catch(Exception)` then `return null`.** `null` can be interpreted as "no data" rather than "I/O failed", sending upper layers down the wrong branch.

**`catch(Throwable)` then recover.** Serious `Error`s are turned into normal fallbacks. Cleanup may need to run in `finally`, but you should not swallow `Error` by default.

**Log and rethrow at every layer.** The same failure generates multiple log entries, making counting hard and obscuring which boundary is responsible.

**Wrap without cause.** Keeping only the message loses the stack trace and original `Throwable`.

**Swallow `InterruptedException`.** The worker may continue waiting or processing even though the supervisor requested a stop.

**Re-interrupt then continue blocking indefinitely.** The interrupt flag is set again, but the stop policy is unclear, potentially causing error loops or hangs.

**Treat timeout as cancellation.** A timed-out `get(timeout)` does not automatically stop the `Future` or roll back side effects.

**Assume `cancel(true)` on every `Future` guarantees the task stops.** Cancellation requires cooperation and depends on the implementation; with `CompletableFuture`, `mayInterruptIfRunning` does not control the computation.

**Catch only `CompletionException` to handle `join`.** A canceled `Future` can throw `CancellationException` directly; a dependent stage may wrap cancellation differently.

**Rely on an uncaught handler to see `ExecutorService.submit` errors.** Task errors may already have been recorded into the `Future` by the executor.

**Retry at multiple layers.** Total executions and side effects can grow uncontrollably.

**Assume `close` equals rollback.** Resource cleanup and transaction/data consistency guarantees are two different contracts.

**Turn every error into HTTP 500/503.** Loses the distinction between input, conflict, permission, and dependency issues; the public contract becomes less useful.

## 24. Error Orchestration Pattern at the Appropriate Layer

A controllable design divides responsibilities:

~~~text
Request boundary
    validate and normalize input
    call application service
    map domain/infrastructure failure → error response
    log final outcome once
          |
          v
Application service
    check invariants
    manage transaction/unit of work if owner
    bounded fallback/retry if allowed
    keep/translate exception per public contract
          |
          v
Repository / adapter
    call I/O, network, database
    close resources owned by adapter
    do not decide request-wide retry policy unless delegated
          |
          v
Executor / async worker
    work per task contract
    propagate errors via Future/CompletionStage
    cooperate with interruption/cancellation
    have a boundary observing completion
~~~

This is **one typical way to divide responsibility**, not a mandatory design for single-threaded apps or small libraries. What must be preserved is that every side effect/exception has one owner for the final decision, and error information is not lost between layers.

### When Should You Use a `Result` Type Instead of `Throwable`?

If failure is a frequent business state and the caller needs to handle that branch like normal data (for example, a search with no results), a `Result`/`Optional` type may fit better than an exception. However, **`Result.failure`** still needs a clear error code and must not turn an abnormal system error into a success result.

### When Should You Create a Custom Checked Exception?

If a library has a failure mode that callers must decide on and you want an explicit compile-time contract, a custom checked exception can be appropriate. If method overrides, lambdas, or frameworks disallow checked `throws`, consider an unchecked wrapper, a callback failure channel, or a `Future`. Do not force every interface to declare generic **`throws Exception`**, as that makes errors hard to distinguish.

## 25. One-Minute Checklist Before Choosing `catch`/`throw`

1. **What kind of error is this?** Input, state, I/O, dependency, task, timeout, interrupt, cancel, or `Error`?
2. **Who owns the operation?** Helper, adapter, service, controller, executor, worker, or caller?
3. **Does the current layer have enough information to genuinely recover?** If not, propagate it.
4. **Does the contract allow checked exceptions?** Regular method, `Runnable`, `Callable`, callback, or `CompletionStage`?
5. **Does the abstraction need to change?** If wrapping, have you preserved the cause?
6. **Are you reading the error on the right thread/`Future`/stage?** Worker failure differs from caller interrupted.
7. **Does timeout only end the wait call, or does it complete the `Future` exceptionally?**
8. **Does cancellation actually interrupt the task?** Have you distinguished `Future` state from worker execution?
9. **Are there side effects needing rollback/compensation?** `close` does not do that automatically.
10. **Is there an `AutoCloseable` owned by this scope?** Prefer TWR, consider suppressed errors and close order.
11. **Is the retry idempotent, bounded, and within the deadline?**
12. **Does the fallback satisfy the contract, or does it mask invalid data?**
13. **Have cause/suppressed been preserved and logged at the appropriate boundary?**
14. **Do tests properly distinguish exception type, cause, state, and the happy path?**
15. **Does the public boundary avoid leaking sensitive information?**

**Conclusion:** Choose error handling by **ownership boundaries and contracts**, not by habit when writing `catch`. Lower layers should preserve accurate error information; intermediate layers should only wrap or recover when truly responsible; `Future` callers must distinguish worker failures from their own interruption; callbacks that disallow checked exceptions need clear stop/translation policies; resource/transaction owners must clean up and keep state consistent. A decision table is most useful when the reader uses it to identify **who decides**, **which channel carries the error**, and **what must be preserved after a failure**.
