# The Happens-Before Relationship When Submitting Tasks and Receiving Results

When a Spring Framework application delegates work to an executor, two questions must be answered clearly: **is the data prepared by the calling thread properly visible to the task?** And **after the task completes, can the calling thread read the result along with the changes the task made?** The Java Memory Model (JMM) answers this through the `happens-before` relationship. This is the foundation for using `Executor`, `ExecutorService`, `Future`, Spring `TaskExecutor`, and `@Async` safely.

## 1. What Does `happens-before` Mean?

`A happens-before B` (abbreviated `A hb B`) is a memory-ordering relationship: if A writes data and B reads that data, this relationship helps guarantee B sees the writes published by A under JMM rules, provided no competing write alters the value. It does not mean the two events must run on the same thread, nor does it mean all tasks in a pool run sequentially.

Three rules to remember:

1. **Same-thread program order:** an action appearing earlier in program order `hb` an action appearing later in that same thread.
2. **Synchronization edges:** cross-thread operations such as `volatile`, `synchronized` locks, submitting via an executor, or retrieving a result from a `Future` can establish an `hb` relationship.
3. **Transitivity:** if `A hb B` and `B hb C`, then `A hb C`.

The `hb` relationship addresses **memory ordering and visibility**; it does **not automatically make** an operation like `counter++` atomic and does not protect an object from other threads modifying it concurrently.

## 2. The Two Most Important Edges in a Task's Lifecycle

The `java.util.concurrent` specification states two direct guarantees:

- **Before submit → inside the task.** Actions of the calling thread **prior to** submitting a `Runnable` to an `Executor`, or a `Runnable`/`Callable` to an `ExecutorService`, `happen-before` the execution of the task. For example, the calling thread assigns `request.id = 7` and then submits a task that reads `request.id`: if no other thread modifies the value, the task receives the published data.
- **Inside the task → after `Future.get()`.** Actions of the asynchronous computation represented by a `Future` `happen-before` subsequent actions of the thread that retrieved the result via `Future.get()`. Therefore, after `get()` returns normally, the waiting thread can use the result and observe the writes performed by the task before completion.

```text
Calling thread (caller)                    Execution thread (worker)
-----------------------                    -------------------------
write input = 41
       |                                             |
       +--- submit(task) --------------------------> read input = 41
                    [happens-before edge 1]          compute output = 42
                                                     complete Future
       <-------------------- get() returns ----------+
                    [happens-before edge 2]
read output = 42
```

By transitivity: **write before submit → operations in task → operations after `get()`**. Conversely, a write by the caller **after** submit does not inherently `happen-before` the worker's read. Likewise, two independently submitted tasks have no implicit ordering relationship with each other.

Note: `submit()` usually returns before the task finishes; returning from `submit()` is **not** a signal that a result is available. `get()` is the point that waits for completion and receives the corresponding `Future`'s result.

## 3. Standalone Java 17+ Example

The example intentionally uses two plain `int` fields, without `volatile`, to demonstrate **the exact two synchronization boundaries**. No third thread concurrently accesses or modifies `SharedState`.

Create the file `HappensBeforeTask.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class HappensBeforeTask {
    private static final class SharedState {
        int input;
        int output;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        SharedState state = new SharedState();
        state.input = 41; // Action occurring before submit.

        try {
            Future<Integer> future = executor.submit(() -> {
                int observed = state.input; // Sees 41 thanks to the submit -> task edge.
                state.output = observed + 1;
                return state.output;
            });

            int result = future.get(); // Waits for task and establishes the task -> caller edge.
            System.out.println("Future: " + result);
            System.out.println("State: " + state.output);
        } finally {
            executor.shutdown();
        }
    }
}
```

Run with JDK 17 or higher:

```bash
javac HappensBeforeTask.java
java HappensBeforeTask
```

Standard output:

```text
Future: 42
State: 42
```

**Why is the result deterministic?** The assignment `state.input = 41` precedes `submit`; the task reads `input` after the submit boundary. The task writes `state.output = 42` before completing; the caller only reads `output` **after** `future.get()`. `Future` also directly returns `42`. This example demonstrates API guarantees without relying on `Thread.sleep()`, scheduling luck, or CPUs sharing caches. `shutdown()` in `finally` releases the pool; it does not replace `get()`.

## 4. What Happens If You Read Too Early?

Consider the following illustrative snippet (assuming `executor` is an active `ExecutorService` and `state` is an object containing only an `int output` field):

```java
executor.execute(() -> state.output = 42);
System.out.println(state.output); // May see stale value: task not awaited yet.
```

`execute()` only submits the work and returns no `Future` for the caller to await. The caller may read before the worker runs, and with unsynchronized shared data there is also a **data race**. Running it a few times and seeing `42` every time still does not prove the code is correct.

When you need to confirm that the task has completed, you can use:

```java
Future<?> finished = executor.submit(() -> state.output = 42);
finished.get();
System.out.println(state.output); // 42 if no other thread writes concurrently.
```

This is an **illustrative snippet**, not a standalone runnable Java file. If shared state is not needed, a cleaner design is to return the value from a `Callable` and read it directly via `Future<Integer>.get()`.

## 5. Applying This to Spring Framework

Spring `TaskExecutor` is an abstraction implementing `java.util.concurrent.Executor`: `execute(Runnable)` has the same task-submission semantics. `AsyncTaskExecutor` adds `submit(...)` to obtain a `Future`; `ThreadPoolTaskExecutor` is the common implementation and uses a JDK pool underneath. Consequently, the data-publication rules on submit and result-waiting remain Java's JMM rules. Note that some executors (such as `SyncTaskExecutor`) run directly on the calling thread: the name `TaskExecutor` alone does not promise another thread is always used.

In a Spring application, if you need to retrieve a result, retain the `Future` returned by `AsyncTaskExecutor.submit` and call `get()` where the value is needed. Example logic inside a Spring bean injected with `AsyncTaskExecutor executor`:

```java
int input = 21;
Future<Integer> future = executor.submit(() -> input * 2);
int value = future.get(); // value = 42
```

This snippet requires an `executor` bean and `InterruptedException`/`ExecutionException` handling in the application context; it is an **integration snippet**, not a standalone Java program.

### With `@Async`

When `@EnableAsync` is enabled, a call **going through a Spring proxy** to an `@Async` method is dispatched to the configured executor. The method can return `Future<T>` or `CompletableFuture<T>`. Example method in a Spring-managed service:

```java
@Async("workExecutor")
public CompletableFuture<Integer> twice(int number) {
    return CompletableFuture.completedFuture(number * 2);
}
```

Suppose `workExecutor` is a configured executor bean, and **another bean** receives this service via injection:

```java
CompletableFuture<Integer> future = asyncCalculationService.twice(21);
int result = future.get(); // result = 42
```

Both snippets above are **Spring fragments**, requiring appropriate imports, beans/services, `@EnableAsync`, executor, and wiring to run in a real application. Even though the method body returns `completedFuture` once finished, **the Future that the proxy returns to the caller** represents the async execution; the caller only uses the result after that Future completes. If a method calls `this.twice(...)` inside the same bean under default proxy mode, the call can bypass the proxy and thus **have no intended asynchronous hand-off**.

With an `@Async void` method, the caller has no `Future` to wait on or receive errors/results from. If completion confirmation is needed, prefer an appropriate Future return type or use an explicit synchronization mechanism; never read a shared variable directly and treat it as the task result.

### `CompletableFuture` and Callbacks

`CompletableFuture` is a `Future`: `get()` waits for the result; `join()` also retrieves the result after completion but differs in exception reporting (typically wrapping errors in `CompletionException` instead of checked `ExecutionException`). Stages such as `thenApply` only run once the source stage produces a result; however, the `Async` suffix and specified executor determine stage scheduling, so **do not infer thread names merely from a callback's existence**.

When interpreting JDK documentation guarantees precisely, use **`Future.get()`** as the clearest reference point for the *task → consumer* edge. When working with `CompletableFuture` chains, design stages to depend on the proper Future rather than relying on two tasks happening to share the same pool.

## 6. Connecting Multiple Tasks via Transitivity

Suppose task A writes a value and task B must read it. Simply submitting A and then B back-to-back is **not enough** to ensure A finishes before B; a multi-threaded pool can run them in parallel.

If the caller needs B to see A's writes, one direct way is to await A before submitting B:

```java
Future<?> writer = executor.submit(() -> state.output = 99);
writer.get();
Future<Integer> reader = executor.submit(() -> state.output);
System.out.println(reader.get()); // 99, if no other concurrent write occurs.
```

The chain of reasoning is: **A's write → `writer.get()` returns → caller submits B → B reads**. Edges combine via transitivity. This is also why multi-stage workflows should express dependencies via Future/CompletionStage or explicit synchronization mechanisms.

Conversely, awaiting **all** Futures after submitting tasks does not by itself fix races **among the tasks themselves**. For instance, two tasks both performing `counter++` on a plain `int` can lose updates; you need `AtomicInteger`, `synchronized`, locks, or proper data partitioning. `Future.get()` lets the caller receive **a completed result**, without making concurrent operations inside the tasks atomic.

## 7. Boundaries to Distinguish

| Scenario | Guarantee You Can Rely On | What You Must Not Infer |
| --- | --- | --- |
| Caller writes data, then `submit(task)` | Writes before submit `hb` actions inside the task | Submit creates an immutable copy of every object; writes after submit will appear automatically |
| `Executor.execute(task)` returns | Task was submitted for execution per the executor contract | Task has finished or caller already sees its writes |
| `Future.get()` returns normally | Task is done, returns result, and publishes its writes to caller | Other tasks are also done or all operations on shared objects are thread-safe |
| `get(timeout, unit)` throws `TimeoutException` | No completed result was obtained within the timeout | Task has stopped or result state can be read immediately |
| `future.isDone()` | Can check the completion status of a Future | Can arbitrarily replace the protocol for retrieving results and handling errors |
| `shutdown()` on `ExecutorService` | Accepts no new tasks and lets submitted tasks proceed per contract | This method waits for all tasks or serves as a result-retrieval point |
| Two tasks on the same pool | Share the same execution mechanism | One task always `hb` the other merely due to submission order |

If `get()` throws `ExecutionException`, the task terminated with an error and the caller has **no successful result** to use; inspect the cause. `InterruptedException` indicates the waiting thread was interrupted; when catching it rather than propagating it, you generally need to restore the interrupt flag via `Thread.currentThread().interrupt()`. `CancellationException` indicates the Future was cancelled. Cancelling a Future or timing out is not a promise that all task code has stopped immediately.

## 8. Common Mistakes and Fixes

1. **Writing data after submit and expecting the task to see it.** Prepare complete inputs **before** submit; if inputs change while the task runs, use immutable structures, `volatile`, locks, or an appropriate synchronization protocol.
2. **Using `Thread.sleep()` to "wait long enough."** Sleeping creates no result edge like `Future.get()`; it depends on machine speed and CPU scheduling. Wait on the proper Future or defined synchronization signal.
3. **Reading shared fields right after `execute()` returns.** Use `submit()+get()`, `CompletableFuture`, or another synchronization protocol if results are needed.
4. **Assuming `get()` fixes every race.** It resolves result publication from one task to the caller; concurrent reads/writes across multiple tasks still require their own protection.
5. **Calling `get()` right after every submit in a loop.** That is synchronization-correct, yet can serialize the calling thread and lose parallelism benefits. When tasks are independent, submit them first and collect results from the Futures afterward.
6. **Assuming `@Async` always runs asynchronously when called inside the same bean.** Check Spring proxy traversal and return types; invoke from another injected bean so the interceptor engages.
7. **Treating `Future.get()` as successful despite timeouts, cancellation, or errors.** Separate normal results from exception branches; only process success data when an actual result was obtained.

## 9. How to Self-Check Your Design

Before sharing an object between a caller and a worker, trace four points: **(1)** whether input writes happen before the submit call, **(2)** whether anyone else is still mutating the input, **(3)** which exact Future/completion signal the consumer waits on, and **(4)** whether multiple tasks concurrently read-write that state. If you cannot trace a `happens-before` path from write to read, do not conclude the code is safe simply because test runs look right.

**Standard references:**
- [Java SE 17 — `java.util.concurrent`, Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)
- [Java SE 17 — `ExecutorService`, Memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
