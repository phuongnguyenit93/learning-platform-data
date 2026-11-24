# Retrieving Results, Checking Completion, and Detecting Cancellation via Future

When submitting a task to an executor, the caller typically wants to know three things: **what is the result**, **is the work finished**, and **was a cancellation request accepted**. In Java, `java.util.concurrent.Future<V>` is the contract for accessing the status and outcome of a computation that may execute asynchronously. Spring Framework uses this exact contract through executors capable of `submit`, notably `AsyncTaskExecutor` and `ThreadPoolTaskExecutor`.

Point to remember right from the start: **a Future represents a computation; a Future does not create threads itself**. The executor decides where and how to run; Future gives the caller a *handle* to wait, read the result, check completion, or request cancellation.

## 1. From Submitting a Task to Receiving a Future

A plain `TaskExecutor` provides `execute(Runnable)` with a `void` return type. To obtain a result handle, use the JDK's `ExecutorService.submit(...)` or Spring's `AsyncTaskExecutor.submit(...)`. `ThreadPoolTaskExecutor` is an implementation of `AsyncTaskExecutor`.

```java
// Illustrative snippet assuming executor is already an ExecutorService:
Future<Integer> value = executor.submit(() -> 21 * 2);
int answer = value.get(); // 42 once calculation completes.
```

Here `submit(Callable<Integer>)` returns `Future<Integer>`. The lambda expression is executed according to the executor's policy; the caller holds the Future and decides when to wait. This is an **integration snippet**, requiring an executor, imports, and exception handling in real code.

There are common submission forms:

| Submission form | Task type | Handle returned | Meaning of result |
| --- | --- | --- | --- |
| `execute(Runnable)` | `Runnable` | No `Future` | Only hands off work |
| `submit(Runnable)` | `Runnable` | `Future<?>` | On normal completion, `get()` returns `null` |
| `submit(Callable<T>)` | `Callable<T>` | `Future<T>` | `get()` returns value `T` or reports failure/cancellation |
| `submit(Runnable, T result)` | JDK `ExecutorService` with `Runnable` | `Future<T>` | `get()` returns the provided `result` on normal completion |

The `submit(Runnable, T result)` form is a method on the **JDK `ExecutorService`**, so do not assume it belongs to Spring's `AsyncTaskExecutor` interface. Different implementations may offer extra capabilities, but code should program against the chosen interface type.

## 2. Key Methods of Future

```java
public interface Future<V> {
    boolean cancel(boolean mayInterruptIfRunning);
    boolean isCancelled();
    boolean isDone();
    V get() throws InterruptedException, java.util.concurrent.ExecutionException;
    V get(long timeout, java.util.concurrent.TimeUnit unit)
        throws InterruptedException, java.util.concurrent.ExecutionException,
               java.util.concurrent.TimeoutException;
}
```

This is an **abridged set of core Future methods for learning the Java 17 API**, not the complete interface source across all Java versions. You do not declare this interface yourself in applications.

- **`get()`**: waits for the computation to complete if necessary, then retrieves the value or throws an exception reflecting failure/cancellation. If the task is not finished, the thread **calling get** may block.
- **`get(timeout, unit)`**: waits at most the specified duration to retrieve the result; if no result arrives in time, throws `TimeoutException`. **Timing out on a wait does not automatically cancel the task**.
- **`isDone()`**: returns `true` when the computation is in a completed Future state, including **success, failure, or cancellation**. It does not indicate whether the outcome succeeded.
- **`isCancelled()`**: returns `true` if the Future was successfully cancelled before normal completion.
- **`cancel(boolean)`**: attempts to transition the Future to the cancelled state. Returning `true` means the Future cancellation request succeeded per the implementation's contract; **it is not proof that all external operations of the task have stopped or rolled back**.

Two patterns often go together: use `isDone()` for a non-blocking status check, and use `get()` at the point where you need to **confirm the final result, receive exceptions, and establish memory publication relationships**. Polling `isDone()` continuously in a busy loop wastes CPU and is no substitute for clear result communication design.

## 3. Reading Future Status as a State Table

| Contract state | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Newly submitted, not yet finished | `false` | `false` | May block waiting |
| Completed normally | `true` | `false` | Returns value (or `null` for Runnable) |
| Completed with exception | `true` | `false` | Throws `ExecutionException` wrapping cause |
| Successfully cancelled | `true` | `true` | Throws `CancellationException` |

State diagram at the **Future** level:

```text
       PENDING / RUNNING
         |     |      |
         |     |      +---- cancel succeeded ----> CANCELLED
         |     |
         |     +----------- error in task -------> FAILED
         |
         +----------------- normal return -------> SUCCESS

   SUCCESS, FAILED, CANCELLED all make isDone() == true.
```

Pay close attention: `isDone() == true` due to **cancellation** does not mean every thread running that task stopped immediately. `cancel(false)` may mark the Future cancelled while an already-started task keeps running; `cancel(true)` only **attempts** to interrupt the worker according to the implementation. External systems (databases, HTTP, files) do not automatically roll back because a Future was cancelled.

## 4. A Standalone Java 17+ Example with Deterministic Stdout

The following example demonstrates all branches: receiving a successful result, checking completion, timing out on a wait, cancelling a queued task, and reading an error cause. The program uses a **single-worker** executor; a `CountDownLatch` holds the worker busy so the task to be cancelled is guaranteed to still sit in the queue when `cancel(false)` is called.

Create the file **`FutureStateDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FutureStateDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch runningStarted = new CountDownLatch(1);
        CountDownLatch releaseRunning = new CountDownLatch(1);

        try {
            // 1. Receive a successful result.
            Future<Integer> success = pool.submit(() -> 21 * 2);
            System.out.println("result = " + success.get());
            System.out.println("success done = " + success.isDone());

            // 2. Occupy the worker until main explicitly releases the latch.
            Future<?> running = pool.submit(() -> {
                runningStarted.countDown();
                releaseRunning.await();
                return null;
            });
            runningStarted.await();
            System.out.println("running done = " + running.isDone());

            // Timed-out wait does not automatically stop the task.
            try {
                running.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println("wait = timeout");
            }

            // 3. Worker is busy so the next task is guaranteed to wait in the queue.
            Future<String> queued = pool.submit(() -> "unreachable");
            System.out.println("cancel accepted = " + queued.cancel(false));
            System.out.println("cancelled = " + queued.isCancelled());
            System.out.println("cancel done = " + queued.isDone());

            try {
                queued.get();
            } catch (CancellationException ex) {
                System.out.println("cancel get = CancellationException");
            }

            // 4. Release the worker and inspect the cause of a failing task.
            releaseRunning.countDown();
            running.get();
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalStateException("boom");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            releaseRunning.countDown();
            pool.shutdownNow();
        }
    }
}
```

Run in the directory containing the file:

```bash
javac FutureStateDemo.java
java FutureStateDemo
```

Expected output:

```text
result = 42
success done = true
running done = false
wait = timeout
cancel accepted = true
cancelled = true
cancel done = true
cancel get = CancellationException
failure cause = IllegalStateException
```

**Why is the output stably repeatable?**

1. `success.get()` waits for `21*2`, so the first value is `42`; after `get()`, that Future is complete.
2. `runningStarted.await()` confirms the worker has entered the lambda waiting on `releaseRunning`. At the read point, that task's Future is not done, and `get(20ms)` must time out because the latch has not been released.
3. The pool has only one occupied worker; the `queued` task cannot start yet. Therefore `queued.cancel(false)` accepts the cancellation without having to interrupt a running task.
4. A cancelled Future has `isCancelled=true`, `isDone=true`, and `get()` throws `CancellationException`, even though that task never ran.
5. After releasing the latch and completing `running.get()`, the task throwing `IllegalStateException` is submitted to the pool; `failed.get()` reports `ExecutionException` with `getCause()` equal to `IllegalStateException`.

The `finally` block always releases the latch and requests pool shutdown, avoiding leaving a worker blocked indefinitely if another branch fails. In real Spring applications, pools are typically beans whose lifecycle is managed by the container; services **should not shut down a shared pool bean after each request**.

## 5. Distinguishing Waiting for Results from Checking Completion

There are three different needs:

### When the Result Is Strictly Needed Right Now

Call `get()` or `get(timeout, unit)` and handle all corresponding outcomes/exceptions. If the caller is an HTTP request thread, calling `get()` right after `submit()` **can still block the request**; "using a thread pool" does not mean the end-to-end processing path has become non-blocking.

### When You Only Need to Observe Status

You can use `isDone()` and `isCancelled()` to report task status to a UI or log. However, `isDone()` does not explain whether the task succeeded or failed; to determine the outcome and error cause, you need `get()` or a dedicated result-storage mechanism.

**Do not use** the following loop as a standard waiting mechanism:

```java
while (!future.isDone()) {
    // Busy-spin: repeatedly polling status and consuming CPU.
}
```

The snippet above **illustrates an anti-pattern**, assuming `future` exists. If you need to wait, use `get()`/timeout or compose async results with an API like `CompletableFuture`.

### When You Do Not Want to Wait Indefinitely

Use `get(timeout, unit)`:

```java
try {
    Integer result = future.get(500, TimeUnit.MILLISECONDS);
    useResult(result);
} catch (TimeoutException ex) {
    // Caller ran out of wait time; the task may still be running.
}
```

This is an **integration snippet**, requiring `future`, `useResult`, and handling for the remaining checked exceptions `InterruptedException` and `ExecutionException` in the enclosing method. `get(timeout)` applies a deadline only to **that specific wait call**, does not set a deadline on the task itself, and does not trigger cancellation.

## 6. Cancellation Requests: cancel(false) and cancel(true)

The `mayInterruptIfRunning` argument decides whether the implementation may **attempt to interrupt the thread currently running** the task.

| Call | Intent | What is not guaranteed |
| --- | --- | --- |
| `future.cancel(false)` | Cancel Future; do not actively interrupt a running worker | Does not guarantee an already-started task stops working |
| `future.cancel(true)` | Cancel Future; allow attempting to interrupt the executing thread | Does not force all code to stop; does not roll back side effects |
| `future.isCancelled()` | Check whether the Future was successfully marked cancelled | Does not prove an external request or DB transaction has stopped |
| `future.get()` after cancel | Throws `CancellationException` | Does not wait until all side effects of a running task have ceased |

**Cancellation is cooperative.** In Java, `Thread.interrupt()` does not kill a thread. Blocking calls that support interruption such as `Thread.sleep`, `BlockingQueue.take`, and `CountDownLatch.await` typically throw `InterruptedException`. CPU-bound code must actively check the interrupt flag and exit at a safe point. Some I/O libraries or native APIs have their own cancellation mechanisms; never assume every call responds to interrupts.

Illustrative snippet for a cooperative task:

```java
Future<?> task = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doOneSmallUnitOfWork();
    }
});
task.cancel(true); // Request interrupt if the task is still running.
```

This is an **integration snippet**, requiring `executor`, `doOneSmallUnitOfWork()`, and a work termination/recovery policy. If `doOneSmallUnitOfWork()` can block or throw `InterruptedException`, handle interruption per the operation's contract. Do not swallow interruption and loop forever.

When `cancel(false)` is called on a **running** task, many implementations may mark the Future cancelled while the worker continues; this easily causes confusion if looking only at `isDone=true`. For a task that has not started yet and whose Future cancellation succeeds, that task should not begin running.

Note especially that **`CompletableFuture.cancel(true)` differs from `FutureTask`-style thread interruption expectations**: per the `CompletableFuture` Javadoc, the `mayInterruptIfRunning` parameter has no effect in that implementation because interruption is not its execution-control mechanism. Check the actual Future type before relying on interrupt-based cancellation.

## 7. Four Exception Groups When Retrieving Results

When calling `get()`/`get(timeout)`, distinguish:

| Exception | Origin | Appropriate handling |
| --- | --- | --- |
| `ExecutionException` | Task ran and threw an exception | Inspect `getCause()`; report business error or log root cause |
| `InterruptedException` | **The thread waiting** on `get` was interrupted | Respect stop request; if caught to handle, usually restore interrupt flag |
| `CancellationException` | The Future was cancelled | Mark result cancelled, avoid treating as success |
| `TimeoutException` | `get(timeout, unit)` did not receive a result within the limit | Handle deadline; decide separately whether to cancel the task |

Handling pattern at a timed service boundary:

```java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    future.cancel(true); // Policy depends on business logic, not guaranteed to stop immediately.
    throw new IllegalStateException("Task timed out", ex);
} catch (CancellationException ex) {
    throw new IllegalStateException("Task cancelled", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Task failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Restore interrupted state.
    throw new IllegalStateException("Wait interrupted", ex);
}
```

This is an **illustrative method snippet**, assuming `future` is of type `Future<T>`, the method returns `T`, and `java.util.concurrent.*` is imported. Choosing `cancel(true)` on timeout must be based on task stopability, idempotency, and side effects; it is not a universal rule for every application.

When `get()` throws `ExecutionException`, do not just log the wrapper and ignore the cause. Inside `getCause()` lies the actual exception the task threw. Conversely, `InterruptedException` on the caller is not a worker business failure and **does not by itself mean the task was cancelled**.

## 8. Memory Boundaries Guaranteed by Future

With `ExecutorService` and JDK-compliant executor mechanisms, actions in the caller **before submitting a task** have a *happens-before* relationship with actions inside the task. More importantly, actions of the asynchronous computation **happen-before** subsequent actions in another thread after retrieving the result via **`Future.get()`**.

```text
caller:  prepare input --> submit(task) .......... get() --> read result
                             |                        ^
worker:                      +--> read input --> write output --> complete
```

Thus, a valid pattern is preparing data before submit, letting the task compute, and only reading the output after `get()` returns normally. For example, shared state with no other competing writer can be safely published through this relationship, even if the field is not declared `volatile`.

However, `get()` **does not make `counter++` atomic**, does not eliminate races among multiple tasks, and does not allow reading state arbitrarily while the task is still running. `isDone()` is used to query status; when reasoning rigorously about data publication and result retrieval, rely on `get()` or synchronization mechanisms with clear contracts.

## 9. In Spring: AsyncTaskExecutor, ThreadPoolTaskExecutor, and @Async

Spring `TaskExecutor` only has `execute(Runnable)`. `AsyncTaskExecutor` extends the contract and adds submission capabilities. `ThreadPoolTaskExecutor` is the commonly used implementation when configuring core/max/queue and obtaining Futures.

Example bean configuration in Spring Framework (snippets require the `spring-context` dependency and container registration, not standalone JDK programs):

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }
}
```

Assuming a bean receives `AsyncTaskExecutor` via constructor/qualifier:

```java
Future<Integer> future = executor.submit(() -> expensiveCalculation());
try {
    Integer value = future.get(300, TimeUnit.MILLISECONDS);
    useValue(value);
} catch (TimeoutException ex) {
    // Task may still be running. Decide separately whether to cancel or return an in-progress status.
}
```

The snippet above requires imports for `AsyncTaskExecutor`, `Future`, `TimeUnit`, `TimeoutException` and handling the remaining exceptions. The wait duration should be based on SLOs and business needs; 300 ms is just an example.

With `@Async` methods, once `@EnableAsync` is enabled and calls pass through the Spring proxy, a method can return `Future<T>` or `CompletableFuture<T>` so the caller gets a handle:

```java
@Async("workerPool")
public CompletableFuture<Integer> calculate(int x) {
    return CompletableFuture.completedFuture(x * 2);
}
```

In this context, the code above is a **method snippet inside a Spring-managed bean**, requiring imports, `@EnableAsync`, the executor bean, and invocations **from outside through the proxy**. Self-invocations like `this.calculate(...)` within the same object in default proxy mode usually bypass the async mechanism. A `void` method annotated with `@Async` brings no `Future` back to the caller; observing status/errors/results requires a different protocol.

**Do not call `get()` inside the same executor with few workers if the result depends on another task waiting in the same pool**: this can block all workers while the needed task has no free worker, leading to starvation/deadlock. Design dependencies with `CompletableFuture`/completion stages, separate pools, or non-blocking structures whenever possible.

## 10. Where Are Future and CompletableFuture Similar and Different?

`CompletableFuture<T>` **implements `Future<T>`**, so it also has `get()`, `get(timeout)`, `isDone()`, `isCancelled()`, and `cancel(...)`. However, it adds explicit completion, stage composition, and callback programming.

| Need | Basic `Future<T>` | `CompletableFuture<T>` |
| --- | --- | --- |
| Wait/read result | `get()` | `get()`, `join()` |
| Check status | `isDone()`, `isCancelled()` | Future methods, plus stage APIs |
| Retrieve exception | `ExecutionException` via `get()` | `get()`, or `join()` typically throws `CompletionException` on failure |
| Compose computations | No stage API in Java 17 `Future` contract | `thenApply`, `thenCompose`, `handle`, `exceptionally`... |
| Request interrupt cancellation | Depends on implementation and `cancel(true)` | `cancel(true)` does not use interrupts to stop computation in this implementation |

Result composition example, purely an **API snippet** with an existing `CompletableFuture<Integer> first`:

```java
CompletableFuture<String> label = first.thenApply(x -> "Result = " + x);
String text = label.join();
```

`join()` can also block; it reports errors via unchecked exceptions such as `CompletionException`, whereas `get()` declares checked `ExecutionException` and `InterruptedException`. Regardless of which you choose, understand terminal states and timeout/cancellation policies. `CompletableFuture` does not automatically guarantee which thread runs a callback: using `Async` variants and specifying an executor affects scheduling.

## 11. Observing Multiple Tasks? Do Not Confuse One Future with the Whole Batch

Each Future normally represents **one submission**. If three separate tasks are submitted, `futureA.isDone()` does not say `futureB` has finished. To wait for all, store each Future and call `get()` on each one or use an aggregation mechanism like `CompletableFuture.allOf` when tasks have suitable types.

Example with an already-created JDK `ExecutorService`:

```java
List<Future<Integer>> tasks = new ArrayList<>();
for (int i = 1; i <= 3; i++) {
    final int input = i;
    tasks.add(executor.submit(() -> input * 10));
}
for (Future<Integer> task : tasks) {
    System.out.println(task.get());
}
```

This is an **illustrative snippet**, requiring imports and an executor, not a standalone Java file. Results are printed in **list traversal and `get()` waiting order**, which does not prove execution or completion order in the pool was the same. With multiple tasks, consider an overall deadline instead of giving each `get(timeout)` a long individual budget that pushes total time over the request limit.

Another architectural mistake: calling `cancel()` on one Future does not automatically cancel all dependent tasks, an out-of-process HTTP request, or a transaction on another worker. Group cancellation must be designed explicitly, with task tracking and partial-completion handling.

## 12. Cancelling a Task Does Not Mean Rolling Back Business Effects

Suppose a task has:

1. Written a record to the database.
2. Sent a payment request over HTTP.
3. Been called with `cancel(true)` by the caller before receiving the response.

The Future may transition to the cancelled state, yet the side effects in steps 1–2 may already have occurred. Therefore, a design that genuinely requires cancellation should distinguish:

- **Cancelling the handle/wait**: the caller no longer wants to retrieve the result.
- **Requesting the worker to stop**: the worker checks the interrupt flag or an application cancellation flag, then stops at a safe point.
- **Cancelling at an external service**: may require a dedicated API to stop work already dispatched.
- **Business compensation/recovery**: if data was written or external services were called, transactions, idempotency keys, or compensating workflows are needed per business rules; Future does not do this for you.

Additionally, **a caller timeout does not guarantee a worker or downstream timeout**. A system might time out an HTTP wait in 500 ms while the task keeps running for many seconds. You must coordinate deadlines, HTTP/DB client timeouts, job lifecycles, and duplicate-prevention mechanisms.

## 13. Common Pitfalls

1. **Confusing `submit` with `get`.** `submit` creates a Future, not a guarantee that the result exists when it returns; `get` is the waiting/retrieval operation.
2. **Seeing `isDone=true` and concluding success.** A Future also completes on error or cancellation; you must classify the state.
3. **Seeing `cancel(true)` return true and assuming the thread is dead.** Interruption is a cooperative request, not forced termination and not a side-effect rollback.
4. **Using `get(timeout)` and assuming the task cancels automatically.** `TimeoutException` only states the wait expired; cancellation policy is a separate decision.
5. **Swallowing `InterruptedException` and keeping an infinite wait loop.** When catching an interrupt on the caller, typically restore the interrupt flag and exit the flow cleanly.
6. **Reading `ExecutionException` without checking `getCause()`.** The real cause sits in the exception thrown by the task.
7. **Reading shared state before the Future completes.** Data races or stale values can occur; use the returned result or explicit synchronization.
8. **Calling `get()` right after every submit while thinking it runs in parallel.** That can serialize the caller; submit independent tasks first, then collect results appropriately.
9. **Blocking a pool worker to wait for another task in the same pool.** Can lead to starvation/deadlock; model dependencies with completion stages or separate executors.
10. **Confusing `@Async` with direct Java calls.** Under Spring's proxy model, calling `this.method()` bypasses the async interceptor.
11. **Holding Futures only in memory and treating them as durable job state.** On JVM restart, handles and in-memory state are lost; long-running work needs a durable state store/broker if required by the business.
12. **Ignoring rejection at submit time.** When the executor is overloaded or shut down, `submit` may throw immediately; at that point there is no valid Future to track.

## 14. Self-Check Questions

**Question 1.** `Future.isDone()` returns `true`. Can you confirm a successful result was received?  
**Answer:** No. It is also true on failure or cancellation; you must read the result/exception or check additional status.

**Question 2.** `future.get(200, MILLISECONDS)` throws `TimeoutException`. Was the task stopped?  
**Answer:** Not automatically. The Future may still be queued or running; to cancel, call `cancel` per an appropriate policy and ensure the task supports safe stopping.

**Question 3.** A task is making an HTTP call; `cancel(true)` returns `true`. Is the HTTP request guaranteed to be cancelled on the remote server?  
**Answer:** No. Side effects may already have occurred; you need timeouts/cancellation in the HTTP client and dedicated mechanisms on the target system.

**Question 4.** `get()` throws `ExecutionException`. Where is the original business exception?  
**Answer:** In `ExecutionException`'s `getCause()`.

**Question 5.** You need an integer value from a Spring task. Should you choose `TaskExecutor.execute` or `AsyncTaskExecutor.submit(Callable<Integer>)`?  
**Answer:** `submit(Callable<Integer>)` provides a `Future<Integer>` suited to receiving a result.

**Question 6.** Why does a cancelled Future still have `isDone=true` even though the worker might not have stopped yet?  
**Answer:** `isDone` reflects the terminal state **of the Future**, not confirmation that all side effects or execution threads have physically terminated.

In summary, use **`get` to retrieve results**, **`isDone` to check whether the Future has reached a terminal state**, **`isCancelled` to detect the cancelled state**, and **`cancel` to request cancellation within the implementation's cooperative capability**. For reliable operation, account for timeouts, interruption, task errors, and side effects already produced.

### References

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Spring Framework — AsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
