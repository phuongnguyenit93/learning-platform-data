# Runnable, Callable, and Passing Task Results in Java

When writing concurrent Java programs, we need to separate two questions: **what work will the task perform?** and **how does the caller retrieve the result, detect errors, or wait for the task to complete?** Two functional interfaces, `Runnable` and `Callable<V>`, represent the work; tools such as `Thread.join()`, `Future<V>`, `FutureTask<V>`, and `ExecutorService` help manage execution and retrieve results. This article covers **Java in general**, focusing on the Thread API and standard Java concurrency (Java 17+); it does not cover Spring-specific mechanisms.

After this article, you will be able to:
- Distinguish between `Runnable.run()`, `Callable.call()`, return values, and checked exceptions.
- Run a task via `Thread` or submit it to `ExecutorService`; know when to use `execute` vs. `submit`.
- Retrieve results from another thread using `join` + a shared object, `FutureTask`, or `Future`.
- Handle success, failure, waiting, timeouts, task cancellation, and interrupts without losing errors.
- Recognize common mistakes: calling `run()` instead of `start()`, calling `get()` too early, assuming `shutdown()` means waiting until finished, or ignoring `Future` when a task fails.

## 1. How Do Runnable and Callable Represent Work?

### 1.1. Runnable: Execute an Action with No Return Value

`java.lang.Runnable` declares a single abstract method:

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

A `Runnable` describes executable work; the `run()` method **returns `void`** and **declares no checked exceptions**. It can be written as a class, anonymous class, method reference, or lambda:

~~~java
Runnable logTask = () -> System.out.println("Running task");
~~~

`Runnable` does not carry a direct return value channel through `run()`, though the task can still mutate a shared object, emit messages, or write data. Such sharing requires a thread-safe design when accessed concurrently.

### 1.2. Callable<V>: Execute and Return V

`java.util.concurrent.Callable<V>` declares:

~~~java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
~~~

Key differences:
- `call()` returns **a value of type `V`**; for example, `Callable<Integer>` returns `Integer`.
- `call()` is allowed to declare `throws Exception`, so the task can throw checked exceptions.
- `Callable` cannot be passed directly to the `Thread(Runnable)` constructor; to run it with `Thread`, you can wrap it in a `FutureTask`, or more commonly, pass it to `ExecutorService.submit`.

~~~java
Callable<Integer> calculate = () -> 6 * 7;
Callable<String> loadText = () -> "ready";
Callable<Void> withoutValue = () -> {
    System.out.println("Work completed");
    return null;
};
~~~

**Note:** `Callable<Void>` must still return a value compatible with type `Void` (in practice, usually `null`). If you only need to express an action with no return value, `Runnable` is usually cleaner.

| Criterion | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Abstract method | `void run()` | `V call() throws Exception` |
| Direct return value | No | Yes, of type `V` |
| Checked exceptions declared on method | No | Yes |
| Can be passed directly to `new Thread(...)` | Yes | No |
| Can be passed to `ExecutorService.submit(...)` | Yes | Yes |
| When to choose | Actions or tasks that do not need to return a value | Computations, lookups, or processing that need a return value / checked exceptions |

Both are **functional interfaces** and both represent *work to be done*; simply creating a `Runnable` or `Callable` does not make the task run asynchronously. An execution mechanism such as `Thread.start()` or an executor is required.

## 2. Running Runnable with Thread and Waiting with join()

### 2.1. Standalone Runnable Java 17+ Example

~~~java
// RunnableThreadDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger result = new AtomicInteger();

        Runnable task = () -> {
            int value = 6 * 7;
            result.set(value);
        };

        Thread worker = new Thread(task, "calculation-worker");
        worker.start(); // Create a new execution path and invoke task.run() on that thread.
        worker.join();  // Wait for worker to finish.

        System.out.println("Result: " + result.get());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac RunnableThreadDemo.java
java RunnableThreadDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Here `Runnable.run()` does not return `42`. The worker **writes** to `AtomicInteger`, while the `main` thread **reads** after `join()`. `join()` only waits for completion; the value is available because we explicitly stored it in a shared object. All actions of the worker before termination are guaranteed to *happen-before* another thread successfully returns from `join()`, so the data is properly published through this wait. Using `AtomicInteger` in this example makes the shared state explicit; if only one worker writes and `main` only reads after `join()`, another holder without concurrent mutation could also be suitable.

### 2.2. Do Not Confuse run() with start()

~~~java
worker.run();   // Calls the method like a normal method call on the current thread.
worker.start(); // Requests the JVM to start a new thread; that thread will execute run().
~~~

The two lines above **illustrate two alternatives**, not a sequence of statements to run consecutively on the same `worker`. A `Thread` can only be `start()`ed **once**; calling it again throws `IllegalThreadStateException`. `Thread.join()` waits for the thread to terminate, but **does not return the task result**. When there are multiple tasks and you need results or exceptions, `Future` is usually a more convenient model than manually managing multiple `Thread` instances and holders.

## 3. Future<V>: Representing a Result Available in the Future

`java.util.concurrent.Future<V>` is a *handle* for tracking a submitted/running task and retrieving its result upon completion. `Future` does not create threads on its own; an executor or `FutureTask` must execute the underlying work.

Important methods:

| Method | Meaning |
| --- | --- |
| `V get()` | Waits until completion and returns the result, or throws an exception if failed/cancelled/waiter interrupted |
| `V get(long timeout, TimeUnit unit)` | Waits at most the specified duration, potentially throwing `TimeoutException` |
| `boolean isDone()` | `true` if the task has terminated in some way: success, failure, or cancellation |
| `boolean isCancelled()` | `true` if the task was cancelled |
| `boolean cancel(boolean mayInterruptIfRunning)` | Attempts to cancel the task; outcome depends on state and execution mechanism |

`get()` can **block the calling thread**. If completed successfully, it returns the value; if the task failed, it throws `ExecutionException`, where `getCause()` holds the original cause. If cancelled, `get()` throws `CancellationException` (unchecked). If the waiting thread is interrupted, `get()` throws `InterruptedException`.

`isDone() == true` **does not mean success**; after it returns `true`, you must still handle failure/cancellation cases if a result is needed.

Timeline model:

~~~text
Calling thread                 Task thread
   | submit(callable)  -------> | starts working
   | receives Future<V>         | computing...
   | does other work            | ...
   | future.get()               | ...
   | [may wait]                 | return value
   | <------------------------- | completes
   | receives V                 |
~~~

Waiting for `Future.get()` to return successfully also establishes the memory visibility guarantee needed to observe side effects performed by the task before completion. However, **the returned value may be a mutable object**: after completion, subsequent concurrent accesses to that object still require their own synchronization rules.

## 4. ExecutorService: Submitting Tasks and Receiving a Future

`ExecutorService` is an abstraction that manages task execution and can reuse a thread pool. Unlike creating `new Thread(...)` each time, it decouples the task from the decision of how many threads to use.

Commonly used overloads:

| Call | Result |
| --- | --- |
| `execute(Runnable)` | Returns `void`; no `Future` is returned to wait on or read results |
| `submit(Runnable)` | `Future<?>`; upon successful completion, `get()` returns `null` |
| `submit(Runnable, T result)` | `Future<T>`; upon successful completion, `get()` returns **the pre-supplied `result` value** |
| `submit(Callable<T>)` | `Future<T>`; `get()` returns the value computed and returned by `call()` |

### 4.1. Runnable with a Future to Know When It Completes

~~~java
// RunnableFutureDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableFutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicInteger counter = new AtomicInteger();

        try {
            Future<?> first = pool.submit(() -> counter.addAndGet(3));
            Object noReturnValue = first.get();

            Future<String> second = pool.submit(
                () -> counter.addAndGet(2),
                "completed"
            );
            String status = second.get();

            System.out.println("First result: " + noReturnValue);
            System.out.println("Second result: " + status);
            System.out.println("Counter: " + counter.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac RunnableFutureDemo.java
java RunnableFutureDemo
~~~

Deterministic stdout:

~~~text
First result: null
Second result: completed
Counter: 5
~~~

- `first.get()` waits for the add-3 task to finish; since the task is a `Runnable`, `get()` returns `null`.
- `submit(runnable, "completed")` **does not turn `run()` into a function that returns a String**. The string `"completed"` is a value supplied in advance by the caller and is returned only after the task completes successfully.
- Both additions are safe thanks to `AtomicInteger`. `get()` is called sequentially, so the printed result is always 5. You should not infer the start order between tasks without an explicit synchronization relationship.
- `shutdown()` rejects new tasks but **does not wait** for previously submitted tasks to finish. This example calls `get()` on both before shutting down.

### 4.2. Callable: Retrieving the Actual Computed Result

~~~java
// CallableResultDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CallableResultDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<Integer> sum = () -> {
                int total = 0;
                for (int i = 1; i <= 5; i++) {
                    total += i;
                }
                return total;
            };

            Future<Integer> future = pool.submit(sum);
            System.out.println("Sum: " + future.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac CallableResultDemo.java
java CallableResultDemo
~~~

Stdout:

~~~text
Sum: 15
~~~

`submit` returns `Future<Integer>` as soon as the executor **accepts** the task, without waiting for computation to finish. `future.get()` is the point where you can wait and receive the `Integer` returned by `call()`. `Callable` can be defined as a separate class if the logic is long; a lambda works well when the code is short and readable.

**Practical choice:** If the caller needs a value from the task, prefer `Callable<T> + Future<T>`. For logic that returns no value, `Runnable` is appropriate, even if you use `Future<?>` solely to track completion and errors.

## 5. FutureTask<V>: Connecting a Callable to a Specific Thread

`FutureTask<V>` is a class that implements both `Runnable` and `Future<V>`. It can **accept a `Callable<V>` to execute** and **allow another thread to call `get()` to retrieve the value**. Because `FutureTask` is also a `Runnable`, you can pass it directly to `new Thread(...)`.

~~~java
// FutureTaskThreadDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

public class FutureTaskThreadDemo {
    public static void main(String[] args) throws Exception {
        Callable<String> work = () ->
            "calculated by " + Thread.currentThread().getName();

        FutureTask<String> task = new FutureTask<>(work);
        Thread thread = new Thread(task, "worker-1");

        thread.start();
        System.out.println(task.get());
    }
}
~~~

~~~bash
javac FutureTaskThreadDemo.java
java FutureTaskThreadDemo
~~~

Stdout:

~~~text
calculated by worker-1
~~~

The line `task.get()` may wait until the thread completes. `FutureTask` completes only once: calling `run()` again does not recompute the result of an already completed instance. For running multiple tasks, load balancing, and reusing threads, `ExecutorService` is usually more convenient than creating many `Thread` instances manually; `FutureTask` is useful when you need to connect the basic `Thread` model with a result channel.

## 6. Error Propagation, Cancellation, and Interrupt Handling

### 6.1. How Are Exceptions Inside a Task Observed?

When a task submitted via `submit` throws an exception, `Future.get()` throws `ExecutionException` and preserves the original exception in `getCause()`. This also applies to a `Runnable` run via `submit`; the difference lies in whether **checked exceptions can be declared in the method signature**, not whether the task can fail.

Java 17+ example:

~~~java
// CallableFailureDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CallableFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<Integer> work = () -> {
                throw new IllegalArgumentException("invalid input");
            };
            Future<Integer> future = pool.submit(work);

            try {
                System.out.println(future.get());
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                    cause.getClass().getSimpleName() + ": " + cause.getMessage()
                );
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac CallableFailureDemo.java
java CallableFailureDemo
~~~

Stdout:

~~~text
IllegalArgumentException: invalid input
~~~

If you use `execute(Runnable)`, the caller receives no `Future` to collect errors. Unchecked errors escaping `run()` are handled by the thread/executor uncaught-exception mechanism, depending on how threads are managed. If you use `submit` and **ignore the `Future`**, the caller may not see the error through the result channel. Therefore, actively collect/observe the `Future` or configure an appropriate error-reporting mechanism.

### 6.2. Timeout and Cancel

**Illustrative code snippet**, assuming `Future<String> future` already exists and the enclosing method handles or declares the necessary exceptions:

~~~java
String value = future.get(2, java.util.concurrent.TimeUnit.SECONDS);
~~~

If the task has not completed after 2 seconds, this call throws `TimeoutException`. **The timeout on `get` only limits the caller's wait time; it does not automatically stop the task.** The caller may decide to call `future.cancel(true)`, though whether cancellation succeeds or stops the task early depends on its state and whether it cooperates with interrupts.

~~~java
boolean cancellationRequested = future.cancel(true);
~~~

With `mayInterruptIfRunning = true`, the system can send an interrupt to the running thread; an interrupt is **not a forced stop command**. The task should respond when blocking operations throw `InterruptedException`, or check the interrupt status in long loops. Do not interpret `isDone() == true` after cancel as "the work ran to completion"; success, failure, and cancellation are distinct states.

### 6.3. Do Not Swallow InterruptedException

When a thread calling `get()` or `join()` is waiting and gets interrupted, the call can throw `InterruptedException`. If the current layer can declare `throws InterruptedException`, it is usually best to propagate it. If it must be handled locally, restore the interrupt flag so upper layers are aware:

~~~java
try {
    future.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Stop/exit caller's work according to application policy.
} catch (java.util.concurrent.ExecutionException e) {
    // Handle the cause from e.getCause().
}
~~~

This is an **illustrative handling snippet**, assuming `future` already exists. If you need timeout handling, add a `TimeoutException` branch; if cancellation is possible, consider `CancellationException`. Do not collapse everything into a single `catch (Exception ignored)` because that loses error details and the interrupt signal.

## 7. CompletableFuture: Composable Asynchronous Results

Beyond basic `Future`, Java also provides `CompletableFuture<T>`. It is useful when you want to **chain computation steps, transform results, combine multiple tasks, or handle errors** without immediately blocking on `get()`. This is part of standard Java; this section only introduces its connection to passing task results, without diving into the entire API.

~~~java
// CompletableFutureDemo.java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> future =
            CompletableFuture.supplyAsync(() -> 21)
                .thenApply(value -> value * 2);

        System.out.println("Answer: " + future.join());
    }
}
~~~

~~~bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
~~~

Stdout:

~~~text
Answer: 42
~~~

- `supplyAsync` accepts logic with a return value, similar in spirit to `Callable`, but uses `Supplier<T>`: `Supplier`'s `get()` method does not declare checked exceptions.
- `thenApply` describes a transformation step from `Integer` to `Integer` once the result is available; the caller does not need to manually fetch and pass the result along.
- `CompletableFuture.join()` waits and returns the result like `get()`, but wraps computation errors in an unchecked exception (typically `CompletionException`); it does not declare `InterruptedException`. Do not confuse `CompletableFuture.join()` with `Thread.join()`.
- By default, `supplyAsync` without an executor argument uses `CompletableFuture`'s default executor mechanism (typically the common `ForkJoinPool`; it may use a different thread when the common pool lacks parallelism). For applications needing resource control, pass an appropriate `Executor` to the `supplyAsync` overload.

## 8. Choosing How to Pass Results by Scenario

| Need | Usually Suitable Approach | Things to Remember |
| --- | --- | --- |
| Run a simple action on a manual thread | `Runnable` + `Thread.start()` | `run()` does not create a new thread |
| Just wait for worker to finish and read written state in `main` | Shared holder + `Thread.join()` | Synchronize state access when needed; `join()` returns no value |
| Use `Thread` but want typed result/exception handling | `Callable<T>` + `FutureTask<T>` + `Thread` | `FutureTask` is both a `Runnable` and a `Future<T>` |
| Run multiple independent tasks that need return values | `ExecutorService.submit(Callable<T>)` | Receive `Future<T>` and call `get()` at an appropriate point |
| No return value needed, but need to wait/check for errors | `ExecutorService.submit(Runnable)` | `Future<?>.get()` returns `null` on success |
| `Runnable` with completion notification as a known value | `submit(Runnable, T result)` | `result` is passed in by the caller, not computed as `run()`'s return value |
| Chain and transform asynchronous results | `CompletableFuture<T>` | Handle exceptions, executors, and continuation threads properly |

### 8.1. Common Mistakes

1. **Calling `task.run()` and thinking it ran concurrently.** That is a call on the current thread; you need `start()` or an executor.
2. **Passing `Callable` directly to `new Thread(callable)`.** The constructor takes a `Runnable`; wrap it in `FutureTask` or use `submit`.
3. **Seeing `Future<?>` and assuming the task returns a useful result.** `submit(Runnable)` completes with `null` on success; if you want a computed value, use `Callable<T>`.
4. **Calling `get()` immediately after `submit` for each task in a loop and expecting the whole flow to be non-blocking.** Tasks still run on the executor, but the caller may wait piece by piece. Submit the tasks first and collect results later, or use appropriate async coordination tools.
5. **Discarding `Future` and forgetting task exceptions.** With `submit`, task errors are stored in the future and typically observed upon calling `get()`.
6. **Treating `shutdown()` as "all tasks have completed."** It initiates shutdown and rejects new tasks, but does not wait for completion; when needed, wait on futures or use `awaitTermination` with a timeout strategy.
7. **Using unbounded `future.get()` on a path with a deadline.** Consider `get(timeout, unit)`, cancellation, and resource management.
8. **Assuming `cancel(true)` always kills the task.** The task must respond cooperatively to interrupts; some blocking operations or libraries have different cancellation rules.
9. **Sharing a mutable result and assuming `Future.get()` handles all subsequent synchronization.** Completing `get()` establishes memory visibility for the completed work, not protection for later concurrent mutations.

## 9. Self-Check Questions

**1. A task only writes logs and returns no value.** Use `Runnable`. If you need to wait for it to finish via an executor, `submit(runnable)` and `Future<?>.get()` are appropriate.

**2. A task computes a list of results.** Use `Callable<List<T>>` with `ExecutorService.submit`; the `Future` type is `Future<List<T>>`. If you want to return a collection for multiple threads to read afterward, design it with immutability or proper synchronization.

**3. Why doesn't `new Thread(() -> 42)` express a `Callable<Integer>`-style result?** A lambda for `Thread(Runnable)` must be compatible with `void run()`; a pure expression body like `42` is not a valid statement expression for a void-compatible lambda. To return an integer, use `Callable<Integer>` with `FutureTask` or `submit`.

**4. Why can `future.isDone()` be `true` while `future.get()` still throws an exception?** Because `isDone` covers success, failure, and cancellation, not just success.

**5. The caller times out in `future.get(1, SECONDS)`; is the task guaranteed to have stopped?** No. The timeout only stops the caller from waiting. You must decide whether to request cancellation and design the task to support interrupts/timeouts itself.

**6. Between `submit(runnable, "OK")` and `submit(callableReturningOK)`, which one produces the returned string?** In the first case, the caller supplies `"OK"` upfront; in the second, `Callable.call()` computes/returns the value, and `get()` receives that result.

**Key takeaway:** `Runnable` and `Callable` define the work; `Thread` or `ExecutorService` handles execution; `Future`/`FutureTask` represents the synchronization point and channel for receiving **results or errors**. Choose the task type based on whether a return value is needed, then choose how to retrieve the result based on thread coordination, timeout, and failure-handling needs.