# anyOf() Completes on One Task and Limitations of Cancelling Remaining Tasks

## 1. Goal: "Having the First Result" Does Not Mean "Everything Else Stopped"

In Java 17, `CompletableFuture.anyOf(...)` is a tool for combining multiple `CompletableFuture` instances: **the combined future completes when any one of the input futures completes**, receiving its corresponding result or exceptional status. It is useful when you want the earliest response from several independent sources, run parallel lookups, or implement a *hedged requests* strategy.

However, there are two very different events:

1. **The combined future has completed:** the caller can read the first result, or receive the error of the task that finished first.
2. **The remaining work has stopped:** worker threads, HTTP requests, DB queries, or side effects of the remaining tasks are no longer running.

`anyOf()` **only guarantees the first event**. It does not cancel, interrupt threads, or release connections of the non-winning tasks. Even if you call `cancel(true)` on a `CompletableFuture`, Java does not guarantee that the underlying work behind the future will stop.

**Example to visualize:** an application sends a data-read request to three replicas. Replica A responds in 100 ms; B and C are still processing. `anyOf(A, B, C)` lets the caller use A's result, **but B and C may continue consuming CPU, threads, JDBC/HTTP connections, and service quotas**. If the requests have side effects, all three may already have affected the system before the first result is received; "returning only one result" does not turn them into "executed only once."

This lesson moves from the API contract, timeline, standalone Java 17 example, real cancellation mechanisms, and handling patterns in Spring `@Async`.

## 2. Exact Contract of CompletableFuture.anyOf()

Declaration:

```java
public static CompletableFuture<Object> anyOf(
        CompletableFuture<?>... cfs)
```

Suppose there are three futures A, B, and C:

```text
A ---- completes successfully ("A") ----|
                                        |
B ----------- still running ------------+--> anyOf(A, B, C) = "A"
                                        |
C -------------------- still running ---|

After anyOf has completed:
- Caller can continue with result "A".
- B and C do not automatically become cancelled.
- B and C may keep running and cause side effects.
```

Rules to remember:

- **"Any future completes"** includes **normal completion, exceptional completion, and cancellation**. `anyOf` does not default to "wait for the first successful future."
- The result has type **`CompletableFuture<Object>`**, because source futures can return different types. Do not blindly cast `Object` to `String` if the inputs have heterogeneous types; use a unified result type or a wrapper/record tagged with the source.
- If an input completes exceptionally first, the `anyOf` future also completes exceptionally, typically surfaced via `CompletionException` when calling `join()`. Other inputs can still succeed afterward.
- If **no futures are passed**, `anyOf()` returns an **incomplete** `CompletableFuture<Object>`, not a future completed with `null`. Calling `join()` on it can wait indefinitely if nothing completes it manually.
- If the list contains a `null` future, the API throws `NullPointerException`; validate the input list.
- If multiple futures are already complete or finish nearly simultaneously, **do not rely on array order to deterministically pick the winner**. Race outcomes depend on the observed completion order.
- `anyOf` does not create worker threads on its own. It **combines existing futures**; whether the sources execute in parallel depends on how the futures were created, the executors, and actual dependencies.

### Comparison with Similar APIs

| API | When does the combined future complete? | Does it auto-cancel remaining work? |
| --- | --- | --- |
| `anyOf(a, b, ...)` | When any one input completes (including errors) | **No** |
| `allOf(a, b, ...)` | When all inputs complete; completes exceptionally if any fails | **No** |
| `applyToEither(other, fn)` | Applies function to a **normally** completed result per CompletionStage contract; racing errors should be tested against actual semantics | **No** |
| `thenCompose(fn)` | Chains a next step dependent on one future's result | **No** |
| `orTimeout(timeout, unit)` | Completes exceptionally at deadline if the called future is still unfinished | **Does not guarantee stopping underlying computation** |
| `completeOnTimeout(value, timeout, unit)` | Sets fallback value at deadline if unfinished | **Does not guarantee stopping underlying computation** |

Do not treat `applyToEither` as an unthinking substitute for **"first successful result, regardless of earlier failing branches."** If business logic requires ignoring individual replica failures and failing only when **all** replicas fail, write an explicit coordinator with specific result/exception rules.

## 3. Why Completing a Future Does Not Stop the Underlying Worker

A `CompletableFuture<T>` primarily represents **the state of a future result**: incomplete, completed with a value, completed exceptionally, or cancelled. It is not necessarily an owning handle capable of controlling the running thread.

Example:

```java
CompletableFuture<String> slow =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor);

CompletableFuture<String> fast =
        CompletableFuture.supplyAsync(() -> callFastService(), executor);

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fast, slow);

Object result = first.join();
```

This is an illustrative snippet inside a method where `executor`, `callSlowService`, and `callFastService` already exist; it is not a standalone program.

After `first.join()`:

- Only **`first` has completed** under the "one input finished" condition; `slow.isDone()` may still be `false`.
- The executor may still be holding `slow`'s worker.
- The HTTP client may still keep the request open to the remote host.
- The slow branch's JDBC query may still be running.
- The slow future may finish later and update caches, write logs, emit events, or cause unintended side effects.
- `first` completing **does not call** `slow.cancel(...)` or `fast.cancel(...)` on our behalf.

There are three layers to distinguish:

```text
LAYER 1: Result/Future state
   isDone(), complete(), completeExceptionally(), cancel()
          |
          v
LAYER 2: Execution task
   Runnable/Callable, worker thread, CompletableFuture supplier
          |
          v
LAYER 3: External work
   JDBC query, HTTP request, file I/O, remote side effect

A state transition at Layer 1
  DOES NOT prove Layer 2 and Layer 3 have stopped.
```

Therefore, the policy of "take the first result and discard the other branches" must be an **explicit decision**: is it acceptable for them to keep running, do they require cooperative stopping, is there a handle allowing real cancellation, and is there idempotency for side effects?

## 4. Standalone Java 17 Example: Demonstrating Cancellation Limits

The example below runs three independent experiments in one program:

1. A slow branch **is running on an executor**, while a fast branch is completed in a controlled way. `anyOf` returns the fast result without cancelling the slow branch.
2. Calling `cancel(true)` on the slow branch's `CompletableFuture` while the supplier is still waiting. The future transitions to **cancelled**, yet the computation can still continue once unblocked.
3. One branch completes **exceptionally** first; `anyOf` completes with that error without waiting for the other branch to succeed and without cancelling the other branch.

Use `CountDownLatch` to avoid relying on `Thread.sleep` timing. Create **`AnyOfCancellationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class AnyOfCancellationDemo {
    private static void awaitOrFail(CountDownLatch latch, String stage) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timeout at " + stage);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at " + stage, ex);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        CountDownLatch slowFinished = new CountDownLatch(1);
        AtomicBoolean sideEffect = new AtomicBoolean(false);

        try {
            CompletableFuture<String> slow =
                    CompletableFuture.supplyAsync(() -> {
                        slowStarted.countDown();
                        try {
                            // The real supplier is still occupying a worker.
                            awaitOrFail(releaseSlow, "releaseSlow");
                            sideEffect.set(true);
                            return "SLOW";
                        } finally {
                            slowFinished.countDown();
                        }
                    }, pool);

            // Ensure the slow supplier has entered the worker before continuing.
            awaitOrFail(slowStarted, "slowStarted");

            // Deterministically complete another future: independent of CPU speed.
            CompletableFuture<String> quick = new CompletableFuture<>();
            CompletableFuture<Object> first =
                    CompletableFuture.anyOf(quick, slow);

            quick.complete("QUICK");
            System.out.println("winner=" + first.join());
            System.out.println("slowDoneAtWinner=" + slow.isDone());
            System.out.println(
                    "slowAutoCancelled=" + slow.isCancelled());

            // cancel() changes CompletableFuture state, without guaranteeing
            // interruption of the worker running supplyAsync.
            boolean cancelled = slow.cancel(true);
            System.out.println("manualCancel=" + cancelled);
            System.out.println("slowCancelledNow=" + slow.isCancelled());

            // Even though the future is cancelled, the supplier is still waiting on releaseSlow.
            releaseSlow.countDown();
            awaitOrFail(slowFinished, "slowFinished");
            System.out.println(
                    "sideEffectAfterCancel=" + sideEffect.get());

            // One future fails first: anyOf follows that error.
            CompletableFuture<String> failed = new CompletableFuture<>();
            CompletableFuture<String> other = new CompletableFuture<>();
            CompletableFuture<Object> firstError =
                    CompletableFuture.anyOf(failed, other);

            failed.completeExceptionally(
                    new IllegalStateException("remote failed"));
            try {
                firstError.join();
            } catch (CompletionException ex) {
                System.out.println(
                        "firstError=" + ex.getCause().getClass().getSimpleName());
            }

            System.out.println(
                    "otherAutoCancelled=" + other.isCancelled());
            other.complete("RECOVERED");
            System.out.println("otherResult=" + other.join());

            // An empty array does NOT mean a completed null result.
            CompletableFuture<Object> empty = CompletableFuture.anyOf();
            System.out.println("emptyIsDone=" + empty.isDone());
        } finally {
            // Clean up even if an assertion or another step fails.
            releaseSlow.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
```

Run with **JDK 17+** in the directory containing the file:

```bash
javac AnyOfCancellationDemo.java
java AnyOfCancellationDemo
```

**Standard output on a successful run** (excluding JVM messages if the machine is abnormally interrupted):

```text
winner=QUICK
slowDoneAtWinner=false
slowAutoCancelled=false
manualCancel=true
slowCancelledNow=true
sideEffectAfterCancel=true
firstError=IllegalStateException
otherAutoCancelled=false
otherResult=RECOVERED
emptyIsDone=false
```

### Analysis of Each Observation

- `slowStarted` confirms the supplier has started on the worker and is waiting on `releaseSlow`. Since main has not opened the latch yet, `slow.isDone()` remains `false`.
- `quick.complete("QUICK")` is the controlled first completion point, causing `first.join()` to return `QUICK`. There is no logic inside `anyOf` to cancel the slow branch.
- `slow.cancel(true)` transitions the **`CompletableFuture`'s state** to cancelled, so `slowCancelledNow=true`. Per Java 17 Javadoc, the `mayInterruptIfRunning` parameter **has no effect in the `CompletableFuture` implementation** because it does not use interrupts to control processing.
- When main opens `releaseSlow`, the supplier is still running, executes `sideEffect.set(true)`, and finishes. The `slow` future **remains cancelled**; the actual completion value `"SLOW"` does not overwrite the established cancelled state.
- `failed.completeExceptionally(...)` completes one branch first. `firstError.join()` throws `CompletionException` with cause `IllegalStateException`. The `other` future is not auto-cancelled and can still complete with `RECOVERED`.
- `anyOf()` with no arguments returns an incomplete future: `emptyIsDone=false`. Do not call `empty.join()` in the demo because it would wait forever.

**Limitation of the experiment:** `quick` is completed manually here so event ordering can be proven. In a real application, both fast and slow can be executor tasks or asynchronous HTTP requests; then the winning branch depends on actual completion order. The experiment still proves that the combined result and worker lifecycle **are not the same thing**.

## 5. What Does cancel(true) on CompletableFuture Actually Mean?

Java 17 Javadoc states clearly: for `CompletableFuture.cancel(boolean mayInterruptIfRunning)`, cancellation takes effect as a form of **exceptional completion** with `CancellationException`. The `mayInterruptIfRunning` parameter does not cause `CompletableFuture` to send an interrupt to the thread performing the computation.

| Action | What can be confirmed | What is **not** guaranteed |
| --- | --- | --- |
| `anyOf(f1, f2)` completes | One input completed and the combined future has a result/error | `f2` stopped, cancelled, or released connections |
| `combined.cancel(true)` | Combined future transitions to cancelled if not yet complete | All inputs cancelled or all source tasks stopped |
| `f2.cancel(true)` | `f2` may complete with `CancellationException`; `isCancelled()` reflects that state | The supplier started by `supplyAsync` will be interrupted/stopped |
| `future.isDone()` | Future is no longer in an incomplete state | Remote operation actually stopped |
| `future.isCompletedExceptionally()` | Future failed/cancelled/completed exceptionally | Worker never caused side effects |
| `Future<?> handle.cancel(true)` from `ExecutorService.submit` | **Requests** task cancellation, may interrupt worker if running | Task definitely stops immediately; I/O is forcefully aborted |

### Cancelling the "Combined Future" Does Not Auto-Cancel Sources

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();
CompletableFuture<Object> combined = CompletableFuture.anyOf(a, b);

combined.cancel(true);

System.out.println("aggregateCancelled=" + combined.isCancelled());
System.out.println("aCancelled=" + a.isCancelled());
System.out.println("bCancelled=" + b.isCancelled());
```

This is a **standalone snippet inside a method** (requires importing `CompletableFuture`). With two incomplete inputs, the three output lines are `true`, `false`, `false` respectively. Changing the state of the **aggregate** does not automatically propagate cancellation backward to the two inputs.

### Cancelling a Losing Branch Does Not Mean Execution Stops

Suppose A has won. You manually call `b.cancel(true)`. If future B is being completed by a running supplier, B's state field may switch to cancelled, yet the supplier, DB query, or HTTP call keeps running. The supplier may later call `complete("B")` or return a value, which cannot overwrite the already-set cancelled state; real side effects may still occur.

**Consequence:** a program printing `b.isCancelled() == true` **does not prove** it saved threads, connections, or remote request costs. You must measure threads/tasks/HTTP clients or the dependency's cancellation mechanism.

## 6. When You Truly Want to Stop Work: Cancellation Must Be Cooperative

Stopping execution depends on **the kind of work** and **the handle controlling it**.

### 6.1. Runnable/Callable with ExecutorService Future

If you own the task directly from `ExecutorService.submit(Callable)`, you receive a `Future<T>` with a more direct tie to the executor's task. Calling `cancel(true)` can attempt to interrupt the worker thread if the task is running.

```java
Future<?> handle = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        performSmallChunk();  // Each unit of work should be bounded and check cancellation.
    }
});

// When the task is no longer needed:
handle.cancel(true);
```

This is an illustrative snippet with `executor`, `performSmallChunk()`, and imports present; not a standalone program. If code is blocked in an interruptible method, `InterruptedException` must be handled properly and usually the interrupt flag should be restored when it cannot be rethrown:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Note: not all I/O APIs or native libraries respond to interrupts the same way. Even `Future.cancel(true)` is a **cancellation request**, not a guarantee that "all side effects are rolled back."

### 6.2. Cooperative Stop Flag

An `AtomicBoolean stopRequested` or cancellation token can be checked by the task between steps:

```java
AtomicBoolean stopRequested = new AtomicBoolean(false);

CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> {
            while (!stopRequested.get()) {
                doBoundedStep();
            }
            return "stopped";
        }, executor);

// Once a usable result has arrived from another branch:
stopRequested.set(true);
```

This is an illustrative snippet; `doBoundedStep()` and `executor` must be defined. Use a separate flag per task/operation; do not use a global stop flag that accidentally cancels another request's work. If an inner step is stuck in an HTTP/JDBC call with no timeout, checking the flag on the next loop iteration will not stop it immediately: deadlines and cancellation are needed on the underlying client.

**Rule:** a cancel token is only useful if the computation **frequently inspects the token**, each step is short enough, resources are closed properly, and no new side effects occur after receiving the stop signal.

### 6.3. HTTP Requests, JDBC, and Remote Tasks

- For async HTTP clients, check the specific client's API for aborting requests, closing responses/connections, or cancelling subscriptions. Do not just cancel a `CompletableFuture` and assume the connection was severed.
- For JDBC, you need transaction/query timeouts, the driver's cancellation API (for instance `Statement.cancel()` if supported), and proper transaction/connection lifecycle management. Do not assume a Java interrupt automatically rolls back a database SQL statement.
- For WebClient/Reactor, `Mono`/`Flux` cancellation flows through the subscription lifecycle; if using `toFuture()`, verify the semantics of your adapter and client version rather than extrapolating from plain `CompletableFuture.cancel`.
- For gRPC calls, message listeners, or workflow engines, use their dedicated cancellation APIs. A task that has already reached the remote server can still finish even though the caller stopped waiting.
- For side-effecting data, an already-committed operation **cannot be "uncommitted"** merely by cancelling a future. You need idempotency, properly scoped transactions, or compensating actions.

## 7. When You Only Need the Fastest Result, Should You Cancel Other Branches?

There is no single answer; base it on cost and business rules.

**You can let them finish** if each branch is lightweight, will finish almost immediately, causes no dangerous side effects if it keeps running, and cancellation costs more than execution. Examples include short bounded CPU calculations where mid-flight interruption is unnecessary.

**You should try to stop/cancel** if losing branches are quota-consuming HTTP requests, long DB queries, or tasks holding many workers/connections. Use the client's real cancellation API and set timeouts; **measure** whether resources are actually returned.

**Do not race multiple replicas** for non-idempotent write operations. For example, sending a "charge payment" request to two endpoints and taking the fastest response can cause **two transactions to execute** even though only one future is surfaced. "First wins" does not protect exactly-once semantics.

A practical plan:

1. Classify whether each branch is read-only/idempotent or has side effects.
2. Cap how many replicas may run (bulkhead, executor, connection pool).
3. Set an overall **deadline** for the race and individual timeouts per dependency.
4. Once a suitable result arrives, signal losing branches to stop via a **dedicated mechanism** (cooperative flag, cancellation handle, client cancellation).
5. Wait/observe cleanup if business rules require it, without making synchronous requests wait forever just to "finish cancelling."
6. Log and measure actual cancellations, in-flight tasks, active connections, and redundant request costs.

## 8. anyOf() Takes the First Completion, Not Necessarily the First Success

Suppose there are three sources:

```text
t=50ms   A completes exceptionally: TimeoutException
t=90ms   B completes successfully: "DATA-B"
t=120ms  C completes successfully: "DATA-C"
```

`anyOf(A, B, C)` completes exceptionally from A at 50 ms. It **does not wait** for B at 90 ms and does not retry automatically. This matches the contract, yet may **fail the business requirement** of "just need one replica to succeed."

If you want "first success; fail only when all fail," you need a different coordinator. Example general Java 17 utility:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public static <T> CompletableFuture<T> firstSuccessful(
        List<? extends CompletableFuture<? extends T>> inputs) {

    if (inputs.isEmpty()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("No candidate futures"));
    }

    CompletableFuture<T> answer = new CompletableFuture<>();
    AtomicInteger failuresRemaining = new AtomicInteger(inputs.size());

    for (CompletableFuture<? extends T> candidate : inputs) {
        candidate.whenComplete((value, error) -> {
            if (error == null) {
                answer.complete(value); // One success is enough to win.
            } else if (failuresRemaining.decrementAndGet() == 0) {
                // By here every candidate has failed.
                answer.completeExceptionally(error);
            }
        });
    }
    return answer;
}
```

**This is a utility method** that must be placed inside a class with full imports; not a standalone runnable program. The code uses `whenComplete` callbacks; just like `anyOf`, it **does not auto-cancel the remaining sources**. If all fail, the example only retains the error from the last failing callback; production systems may need to aggregate causes, error codes, deadlines, and per-replica details for debugging. If multiple successes happen concurrently, the resulting future completes normally only once; callers should not infer which physical task crossed the finish line first solely from callback order.

**Important:** this method differs from `anyOf` in **success-selection semantics**, not in solving work cancellation. Cleaning up or stopping losing tasks remains a separate concern.

### Tagging Source Identity to Avoid Losing Context

Because `anyOf` returns `Object`, when multiple services share the same result type it is hard to tell "who won." You can normalize results into a record:

```java
record Result(String source, String payload) {}

CompletableFuture<Result> a =
        sourceAFuture.thenApply(value -> new Result("A", value));
CompletableFuture<Result> b =
        sourceBFuture.thenApply(value -> new Result("B", value));

CompletableFuture<Object> raced = CompletableFuture.anyOf(a, b);
Result winner = (Result) raced.join();
```

This is a snippet where `sourceAFuture` and `sourceBFuture` are already created and both return `String`. Casting to `Result` is safe only because **both inputs** were normalized to the same type; if another future returning a different type is added to `anyOf`, adjust the model.

## 9. Timeout and Cancellation: Two Distinct Lifecycles

`CompletableFuture.orTimeout(...)` and `completeOnTimeout(...)` are often misunderstood when combined with `anyOf`.

```java
CompletableFuture<Object> first =
        CompletableFuture.anyOf(remoteA, remoteB)
                .orTimeout(800, TimeUnit.MILLISECONDS);
```

This is a snippet in an environment with `remoteA`, `remoteB`, and `TimeUnit` imported. If 800 ms elapses before any branch finishes, the combined future completes exceptionally with a timeout per the API. **That does not automatically stop** the source tasks, HTTP calls, or DB queries. Note also that `orTimeout` acts on **the exact future it is called on** (here the aggregate), rather than creating a separate cancellation layer spanning every source.

Similarly, `completeOnTimeout(defaultValue, ...)` can return a fallback value when the deadline hits without freeing background tasks. Do not configure timeouts at three different layers and assume the result only takes one timeout interval: executor queuing time, connection acquisition, HTTP connect, response, and retries can add up.

**Reasonable deadline design:**

- Overall request deadline (e.g., 1 second).
- Pool and client acquire timeouts/limits.
- Per-remote-call timeout.
- Stop conditions for losing branches.
- Concurrency and retry caps.
- Procedures to release connections/permits/transactions when a task fails or is cancelled.

If a branch does not support cancellation, **do not advertise cancellation as a guarantee**; you may choose to return the early result and still track that branch to clean up when it actually finishes.

## 10. Spring @Async Integration Example: Right Executor, Right Proxy, Right Bounds

In Spring Boot/Spring Framework, `@Async` can return `CompletableFuture<T>`. The Spring proxy submits the method body to an executor; the caller combines the futures with `anyOf`.

The following configuration is **Spring integration code**, not a JDK-only `javac` program:

**`AsyncConfig.java`:**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean("lookupExecutor")
    public ThreadPoolTaskExecutor lookupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("lookup-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

**`LookupService.java`:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LookupService {
    @Async("lookupExecutor")
    public CompletableFuture<String> lookupPrimary(String key) {
        // Simplified example: replace with real I/O with timeout/cancellation.
        return CompletableFuture.completedFuture("primary:" + key);
    }

    @Async("lookupExecutor")
    public CompletableFuture<String> lookupReplica(String key) {
        return CompletableFuture.completedFuture("replica:" + key);
    }
}
```

**`LookupCoordinator.java`:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LookupCoordinator {
    private final LookupService lookupService;

    public LookupCoordinator(LookupService lookupService) {
        this.lookupService = lookupService;
    }

    public CompletableFuture<Object> fastest(String key) {
        CompletableFuture<String> first =
                lookupService.lookupPrimary(key);
        CompletableFuture<String> second =
                lookupService.lookupReplica(key);

        // Return first completion; DOES NOT auto-cancel the other call.
        return CompletableFuture.anyOf(first, second);
    }
}
```

These classes illustrate the flow:

```text
Controller / caller
       |
       v
LookupCoordinator (Spring bean)
       |
       +-- calls LookupService proxy.lookupPrimary() --> lookupExecutor task #1
       |
       +-- calls LookupService proxy.lookupReplica() --> lookupExecutor task #2
       |
       +-- CompletableFuture.anyOf(task #1, task #2)
                           |
                           v
                    first result/error
                           |
                           +--> remaining task may still be running
```

**Integration notes:**

- `@EnableAsync` must be enabled; `@Async` methods must be invoked through a **Spring-managed proxy**. `this.lookupPrimary(...)` inside the same bean under default proxy mode can **bypass** the interceptor and run directly on the current thread.
- `@Async("lookupExecutor")` selects the exact executor. If omitted, executor selection depends on Framework/Boot configuration and existing beans.
- Both methods return immediately in the example, so do not use this code to claim one branch definitely wins or to benchmark real load. In a real system, completion order depends on the scheduler, connection pools, and remote latency.
- `ThreadPoolTaskExecutor` has its own core/max/queue and rejection policy. If the pool/queue is full, submitting a branch can throw `TaskRejectedException` **directly in the caller**, before the coordinator returns the aggregate; handle this if overload is expected.
- Replacing `CompletableFuture.completedFuture(...)` in the target with real HTTP/JDBC requires dependency timeouts and cancellation policies. `@Async` does not turn external operations into guaranteed-cancellable ones.
- `@Transactional` is bound to proxy/transaction boundaries on the executing thread; the caller's transaction is not transferred to the worker when `@Async` is actually used.
- One executor bean per JVM only bounds load **locally**, not cluster-wide quotas across multiple pods.

### Be Careful When Returning Early from a Controller

If a REST endpoint takes the future from `fastest()` and responds based on the first branch, losing tasks may keep running after the response has been sent. Measure active tasks, response times, and downstream costs. If you need "stop working once the client disconnects," wire cancellation from the web layer down to the HTTP client/executor using mechanisms that actually support it, not just `anyOf`.

## 11. Controlling Cost and Resources When Racing Multiple Tasks

An `anyOf` call can improve perceived latency for **a single request**, while also increasing load on downstream sources.

For example, one request simultaneously calls three replicas, each consuming 1 connection and 1 quota unit:

```text
One request:
   1 aggregate future
   3 remote calls submitted
   1 result used
   up to 2 losing calls may still be running

100 concurrent requests:
   up to 300 remote calls submitted,
   not just 100, unless admission control limits them.
```

Do not equate "number of waiting aggregates" with "actual number of tasks/HTTP calls." Consider:

| Risk | Appropriate control |
| --- | --- |
| Spawning many replicas per request | Hedge only when needed; use a latency threshold before launching secondary replicas |
| Executor saturation | Bounded `ThreadPoolTaskExecutor`, bounded queues, rejection handling |
| Exhausting JDBC/HTTP connection pools | Appropriate connection/active-call limits, client-side deadlines |
| Partner APIs with rate/concurrency quotas | Per-dependency rate limiters and bulkheads |
| Losing tasks continuing to cause side effects | Use only for reads/idempotent ops, cancellation/compensation, and idempotency keys |
| Caller leaves while work still runs | Lifecycle tracking, cancellation propagation, cleanup in `finally` |
| Retry storms when one branch fails | Backoff/jitter, retry budgets, and circuit breakers |
| Multiple replicas slow at once | Overall deadline; do not spawn unbounded extra replicas when already overloaded |

**Mental formula:** if each request has at most `k` branches, maximum *submission* load can approach `k × request count`. Actual in-flight concurrency also depends on completion speed, queues, client pools, executor bounds, and hedge timing. Measure in practice instead of assuming losing branches are cut off when `anyOf` completes.

## 12. Testing Both Results and Task Lifecycle

A test like "`assertEquals("A", anyOf.join())`" **does not** prove branch B was stopped. Test across two groups:

**Result group:**

1. One branch succeeds first: aggregate returns the right value, possibly `Object` needing normalization.
2. One branch fails first: aggregate completes exceptionally without waiting for a later branch to succeed.
3. One branch is cancelled first: aggregate completes with that branch's exceptional/cancelled status.
4. Branches finish nearly simultaneously: do not depend on a fixed outcome without controlling ordering.
5. No inputs: aggregate is incomplete; do not accidentally call `join()` and hang forever.

**Lifecycle group:**

1. Right when the aggregate finishes, had a slow supplier actually started? Use `CountDownLatch`.
2. Is the slow supplier still holding a worker/thread/connection?
3. After calling `CompletableFuture.cancel(true)`, can the supplier keep running? The section 4 example proves it can.
4. When applying a cooperative flag or client cancellation, does the task observe the signal, close resources, and stop new side effects?
5. Are there unhandled exceptions or orphaned tasks from losing branches? Are there metrics/logs for their outcomes?
6. For cancellation during DB/remote writes, is business state kept consistent and are retries idempotent?
7. On executor shutdown, are all tasks/connections cleaned up in time?

**Testing technique:** use latches or barriers for deterministic ordering; never rely solely on `Thread.sleep(100)` to assert "A is always faster than B." Put timeouts on `await`, `Future.get(timeout)`, and shutdown to avoid hanging tests. Distinguish exceptions **thrown inside the task** from `TaskRejectedException` **at submission**.

### Visualizing States When Debugging

```text
anyOf result          : DONE (QUICK)
slow CompletableFuture: CANCELLED
slow supplier/worker  : STILL RUNNING
remote side effect    : POSSIBLY ALREADY COMMITTED

All of these lines CAN be true at the same moment.
Do not use isCancelled() to conclude "the worker stopped".
```

## 13. Common Misconceptions

### "anyOf already returned, so the remaining tasks are automatically cancelled"

**False.** `anyOf` only completes the combined future; non-winning sources can keep running and finish. To stop them, actively use task/client-specific mechanisms.

### "Calling cancel(true) definitely interrupts the thread running supplyAsync"

**False for `CompletableFuture.cancel`.** Java 17 Javadoc states the `mayInterruptIfRunning` parameter is not used to control processing in this implementation. The supplier task can still keep running, as shown in the latch example.

### "isDone=true means the work has finished executing"

**Not necessarily.** A cancelled or timed-out future can have `isDone=true` while the underlying computation has not stopped. Check metrics/task handles or verify actual cleanup.

### "anyOf only completes on the first success"

**False.** Exceptional completion or cancellation can also end `anyOf` before another branch returns success. If you need "first successful," build a coordinator with an explicit error-ignoring policy.

### "anyOf with no arguments returns null immediately"

**False.** It returns an **incomplete** future. By contrast, `allOf()` with no arguments produces a future completed with `null`; the two APIs are asymmetric for empty inputs.

### "Calling future.cancel rolls back the payment request already sent"

**False.** Transactions or HTTP side effects that already reached another system are not reversed by changing future state. You need idempotency, transactions, business state machines, or designed compensation.

### "The more branches racing, the better"

Not necessarily. More replicas multiply total CPU, sockets, threads, and quota usage and can slow down the downstream service itself. Use bounded concurrency and balance tail latency against resources.

### "@Async always guarantees tasks run in parallel"

Not completely. You must invoke via a Spring proxy, configure an executor with capacity, handle rejections, and check scheduling order. A single-worker executor still executes `@Async` methods sequentially.

### "Setting orTimeout is enough to complete cleanup"

No. Timeout changes future state; it does not verify that the supplier or HTTP request stopped. Client timeouts, cancellation propagation, and resource release are separate concerns.

## 14. Design Checklist and Reference Links

Before using `anyOf` for a Spring feature:

1. **Is the goal fastest-completion or first-success?** If first-success, define how individual errors are handled.
2. **Can all branches run concurrently?** Verify executors, queues, and HTTP connection pools.
3. **Does any branch have side effects?** Avoid hedging non-idempotent writes.
4. **Who owns cancellation?** `CompletableFuture`, executor `Future`, HTTP client, reactive subscription, DB statement, or workflow controller?
5. **Does cancelling actually stop underlying work?** Don't just check `isCancelled()`; test it.
6. **When are resources released?** Use `finally`, timeouts, closing responses/statements, and releasing permits.
7. **Does first-error termination match business rules?** `anyOf` does not ignore exceptions from losing/early-failing branches.
8. **Are max branch counts and quotas enforced?** Control the cost of task duplication.
9. **Are overall deadlines and retry policies right?** Prevent infinite waits and retry storms.
10. **Are losing branches logged/metered separately?** Measure completed/cancelled/actually-stopped, active tasks, remote calls, and side effects.

**Official documentation:**

- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `anyOf`, `allOf`, `cancel`, `orTimeout`, `join`, `whenComplete`.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): meaning of `cancel(boolean)` at the interface level and differences across implementations.
- [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `Future`, and shutdown.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic synchronization in tests.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor`, proxy calls, and task scheduling.
- [Spring Framework – Asynchronous Return Types](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async-return-types): returning `CompletableFuture` from `@Async` methods.

**Final takeaway:** `anyOf` is a **selector for one completion state**, not a **lifecycle manager for the remaining tasks**. If you want to save resources or stop losing branches, you need cancellation handles, cooperative stopping, or client timeouts at the right layer, and you must verify that actual execution stopped—not merely that a future has `isCancelled() == true`.
