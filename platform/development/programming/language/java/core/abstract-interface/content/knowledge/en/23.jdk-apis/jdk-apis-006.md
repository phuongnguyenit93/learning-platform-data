# Runnable and Callable: Contracts for Work and Results

In Java, both `Runnable` and `Callable<V>` describe a unit of work that can be executed later. The core difference lies in the contract: `Runnable` performs an action and returns no result; `Callable<V>` returns a value of type `V` and can declare checked exceptions. Choosing the right type helps an API clearly express the result to retrieve, how errors are handled, and how asynchronous work is managed.

## 1. Two Different Contracts

| Characteristic | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Abstract method | `void run()` | `V call() throws Exception` |
| Return value | None | Yes, of type `V` |
| Checked exception declaration | `run()` cannot declare checked exceptions | `call()` can declare `Exception` or a specific checked exception |
| Package | `java.lang` | `java.util.concurrent` |
| Example uses | Logging, sending a signal, updating a state | Computing a result, reading data, queries that need to return a value |
| Directly supported by `Thread` | Yes | No; can be wrapped in `FutureTask<V>` |
| Used with `ExecutorService` | `execute(Runnable)`, `submit(Runnable)` | `submit(Callable<V>)` |

Both are functional interfaces, because each type has one abstract method. Therefore, a lambda or method reference can be used when passing behavior to an API.

~~~java
Runnable notify = () -> System.out.println("Da hoan tat");
Callable<Integer> calculate = () -> 6 * 7;
~~~

The first lambda returns no result; the second lambda returns an integer. The `Callable<Integer>` line also clearly indicates the data type that the caller will receive back.

## 2. Running Runnable with Thread

`Thread` accepts a `Runnable`. When `start()` is called, the JVM starts a new execution thread and calls `run()` in that thread. Calling `run()` directly merely executes the method as a normal call on the current thread, without starting a new thread.

~~~java
public class RunnableThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> System.out.println("Work is running");

        Thread thread = new Thread(work);
        thread.start();
        thread.join();
        System.out.println("Main continues");
    }
}
~~~

Run:

~~~bash
javac RunnableThreadDemo.java
java RunnableThreadDemo
~~~

Output:

~~~text
Work is running
Main continues
~~~

`join()` causes the main thread to wait for the worker thread to finish, so the output order in this example is deterministic. If `join()` is omitted, no ordering should be assumed between main's message and the worker thread's message.

There is no need to create a separate class for every small task; a lambda is usually clear enough. However, if the work requires substantial state or multiple methods, a class implementing `Runnable` can help organize the code better.

## 3. Callable Returns a Result and Can Throw Exceptions

`Callable<V>` is suitable when work needs to produce a result. The `call()` method returns type `V` and can declare checked exceptions, such as `IOException`. However, `Callable` itself is not a thread and does not run automatically when instantiated; it needs an execution component to invoke it.

The example below illustrates calling `Callable` via `ExecutorService`:

~~~java
import java.util.concurrent.Callable;

public class CallableDefinitionDemo {
    public static void main(String[] args) throws Exception {
        Callable<Integer> calculate = () -> 6 * 7;
        System.out.println(calculate.call());
    }
}
~~~

Run:

~~~bash
javac CallableDefinitionDemo.java
java CallableDefinitionDemo
~~~

Output:

~~~text
42
~~~

This example calls `call()` directly on the current thread only to illustrate the return contract. In asynchronous applications, you should typically delegate the task to an executor and retrieve the result through `Future<V>`.

With `Runnable`, checked exceptions must be handled inside `run()` or converted into unchecked exceptions. With `Callable`, checked exceptions can be declared on `call()`; when the task runs asynchronously via an executor, the caller retrieving the result typically receives the task's exception via `ExecutionException` from `Future.get()`.

## 4. ExecutorService and Future

`ExecutorService` separates describing the work from how threads are managed. Instead of manually creating a `Thread` for each task, you submit the work to the executor so that it schedules and executes it. The `submit(...)` method returns a `Future`, representing the status and result of the task.

- `submit(Runnable)` returns `Future<?>`. When the task completes normally, `get()` returns `null`, because `Runnable` produces no value.
- `submit(Callable<V>)` returns `Future<V>`. When the task completes normally, `get()` returns a value of type `V`.
- `execute(Runnable)` only submits an action and does not return a `Future`. Use it when you do not need to retrieve a result or track completion through a `Future`.
- `submit(Runnable, result)` lets you attach a result value provided by the caller. `Future.get()` returns that value after the `Runnable` completes normally; it is not a value returned by `run()`.

### Working Example: Comparing the Two Types

File `RunnableCallableDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RunnableCallableDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> action = pool.submit(
                () -> System.out.println("Runnable: saved")
            );
            Future<Integer> calculation = pool.submit(() -> 20 + 22);
            Future<String> status = pool.submit(() -> "done");

            action.get();
            System.out.println("Callable result: " + calculation.get());
            System.out.println("Callable status: " + status.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac RunnableCallableDemo.java
java RunnableCallableDemo
~~~

Output:

~~~text
Runnable: saved
Callable result: 42
Callable status: done
~~~

The executor has only one worker thread, so tasks are executed in submission order. The `action.get()` call waits for the first task to complete before printing the subsequent results, so the example output has a consistent order. The `finally` block ensures the executor is requested to stop accepting new tasks even if an error occurs while retrieving results.

`shutdown()` allows previously submitted tasks to complete. It does not mean that main waits for the executor to finish at the line where it is called; in the example, the `get()` calls already waited for each task. For workflows that need timeout control, you can also use `awaitTermination(...)`.

## 5. Understanding Future.get() and Errors Properly

`Future.get()` typically blocks the calling thread until the task completes. There are three important scenarios:

1. **Success:** with `Callable<V>`, `get()` returns the result; with a `Runnable` submitted via `submit`, `get()` returns `null` if no separate result value was passed.
2. **Task failure:** `get()` throws `ExecutionException`; call `getCause()` to view the original exception caused by the task.
3. **Waiting thread interrupted:** `get()` can throw `InterruptedException`. This signals that the waiting thread was interrupted; it does not automatically mean the task was cancelled.

Example of handling a result with a specific type:

~~~java
Future<Integer> result = pool.submit(() -> {
    if (System.nanoTime() < 0) {
        throw new IllegalStateException("Unexpected state");
    }
    return 42;
});

try {
    int value = result.get();
    System.out.println(value);
} catch (ExecutionException e) {
    System.err.println("Task failed: " + e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting thread interrupted", e);
}
~~~

The snippet above is a fragment to illustrate error handling; it assumes the `pool` variable has been initialized and has its lifecycle managed externally. In actual code, you should not catch and ignore `InterruptedException`. If you cannot throw the exception up to the calling layer, restore the interrupt flag using `Thread.currentThread().interrupt()` so that the rest of the program can detect the interruption.

You can use `get(timeout, unit)` when you do not want to wait indefinitely; this method can also throw `TimeoutException`. Timing out does not automatically cancel the work. If you want to request cancellation, call `cancel(true)` on the Future and design the task to respond appropriately to interruption.

## 6. Task Cancellation and Executor Lifecycle

`Future` provides `isDone()`, `isCancelled()`, and `cancel(...)`. A successful cancellation means the Future is marked as cancelled; it does not guarantee that all running code stops immediately. The `true` argument requests interrupting the executing thread if the task is running, but the task must cooperate by checking its interrupt status or responding to `InterruptedException`.

An executor also requires lifecycle management:

- `shutdown()`: stops accepting new tasks and lets previously submitted tasks continue to completion.
- `shutdownNow()`: attempts to interrupt running tasks and returns a list of waiting tasks that have not yet started; this is a best-effort stop request, not a guarantee of immediate termination.
- `awaitTermination(timeout, unit)`: waits up to a maximum duration for the executor to terminate.
- After the executor has shut down, new task submissions typically fail with `RejectedExecutionException`.

You should not create a new executor for each small task without managing its shutdown. In real applications, an executor can be shared according to the lifecycle of a component or the application; the owner of the executor must be responsible for shutting it down at the right time.

## 7. Checked Exceptions: Why Callable Is Useful

Consider the file-reading API `Files.readString(Path)`, which can throw `IOException`. A `Callable<String>` can directly describe the read work and allows declaring checked exceptions:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

Callable<String> readText = () -> Files.readString(Path.of("input.txt"));
~~~

This is a fragment, not a standalone file; it needs to be placed inside an appropriate method or class. When submitting it to an executor, retrieve the result via `Future<String>`. If reading the file fails, `Future.get()` will report `ExecutionException` with the cause typically being `IOException`.

With `Runnable`, you cannot let `IOException` escape directly from `run()` as a checked exception. You can catch and handle it right inside the lambda, or wrap it into an `UncheckedIOException`, but that approach changes the exception contract visible to the caller. If the result and exceptions are a natural part of the task, `Callable<V>` is usually more suitable.

## 8. How Do Callable and Runnable Relate to Each Other?

A `Callable<V>` cannot be passed directly to `new Thread(...)`, because `Thread`'s constructor accepts a `Runnable`. If you need to retrieve a result while still using the `Runnable` mechanism, Java provides `FutureTask<V>`, which implements `RunnableFuture<V>` and can be constructed from a `Callable<V>`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

Callable<Integer> work = () -> 21 * 2;
FutureTask<Integer> task = new FutureTask<>(work);
Thread thread = new Thread(task);
thread.start();

Integer answer = task.get();
System.out.println(answer);
~~~

The fragment above needs to be placed inside a method that handles or declares `InterruptedException` and `ExecutionException`. The output is:

~~~text
42
~~~

`FutureTask` can both be executed as a `Runnable` and hold the Future result and state. In most applications, `ExecutorService` remains the more convenient choice because it provides thread management and task queuing mechanisms.

## 9. Common Misconceptions

- **Expecting a result from Runnable:** `Runnable` does not return data from `run()`. If you need a value produced by the task, use `Callable<V>` and `Future<V>`, or design an explicit way to exchange the result.
- **Thinking Callable runs by itself:** creating a lambda or `Callable` object only describes the work. You must call `call()` directly or submit it to an execution component.
- **Confusing submit with execute:** `submit` returns a `Future`; `execute` does not. If you use `submit` and do not call `get()`, task errors may go unobserved at the call site.
- **Ignoring ExecutionException:** exceptions raised inside the task are wrapped in `ExecutionException` when retrieving the result. Inspect `getCause()` to diagnose them.
- **Assuming cancel(true) stops the task immediately:** thread interruption is a cooperative request mechanism. Work that does not check its interrupt status or respond to interrupt exceptions may continue running.
- **Calling run() and expecting asynchronous execution:** `run()` is a normal method call; use `start()` to start a new thread.
- **Forgetting to shut down the executor:** an executor can still hold onto thread resources. Clearly define which component owns it and when it needs to be shut down.
- **Sharing mutable state without synchronization:** Runnable and Callable only describe work. They do not automatically make shared data thread-safe.

## 10. Quick Selection Rules

- Choose **Runnable** when you only need to describe an action that returns no result, especially with `Thread`, `Executor.execute`, or when the result is passed through another mechanism.
- Choose **Callable&lt;V&gt;** when the task produces a result of type `V`, needs to declare checked exceptions, or when an asynchronous API needs to return a result via `Future<V>`.
- Choose **`ExecutorService.submit(...)`** when you need to track status, retrieve results, cancel, or observe errors through a Future.
- Use **execute(Runnable)** when you only need to hand off work to an executor and do not need a Future. You need an appropriate error-handling strategy because there is no Future on which to call `get()`.
- Choose **FutureTask&lt;V&gt;** when you need an object that is both a Runnable and holds a Future result, such as when integrating a Callable with an API that only accepts a Runnable.

Key takeaway: `Runnable` answers the question “what action needs to be performed?”, while `Callable<V>` answers “what work needs to be performed and what is the result of type `V`?”. When running asynchronously, `Future` is the bridge for checking the status, receiving the result, and observing errors of that work.
