# Runnable, Callable, Executor, and ExecutorService

## 1. The Big Picture: Work Is Different from the Execution Thread

When writing a Java program, there are two separate questions:

1. **What work needs to be done?** For example: processing a file, calling an external service, or computing a report.
2. **Who executes and manages that work?** For example: a thread you create directly or a pool of reused threads.

`Runnable` and `Callable` describe a **task**. `Executor` and `ExecutorService` describe the **task execution mechanism**. Separating these two roles avoids creating `new Thread(...)` for every piece of work, centralizes resource management, collects results, and enables controlled application shutdown.

```text
Caller code
   |
   | creates Runnable / Callable
   v
Task: "what to do?"
   |
   | execute(...) / submit(...)
   v
Executor / ExecutorService: "how to run it?"
   |
   +--> worker thread 1
   +--> worker thread 2      (if using a pool)
   +--> waiting queue
              |
              v
          Future<T>          (when using submit)
              |
              v
      result / error / cancellation
```

A task is **not synonymous with** a thread: many tasks can run sequentially on the same worker thread; conversely, many tasks can run concurrently on different workers. Moreover, an `Executor` can run a task directly on the calling thread, so the API name alone does not guarantee asynchronous execution.

In the Spring Framework concurrency module, this is the foundation for understanding higher-level mechanisms such as `TaskExecutor`, `ThreadPoolTaskExecutor`, and `@Async`. First, you must understand the exact contracts of the standard Java APIs.

### Lesson Objectives

After this lesson, you will be able to choose the right task type, submit tasks to an executor, retrieve results or exceptions via `Future`, handle interruption/cancellation, shut down an executor safely, and recognize common pitfalls when using thread pools.

## 2. The Four Core Interfaces

| Component | Role | Core Method(s) | Result and Exceptions |
|---|---|---|---|
| `Runnable` | Describes work to run without returning a value | `void run()` | Does not declare checked exceptions from `run()` |
| `Callable<V>` | Describes a computation that produces a result | `V call() throws Exception` | Returns `V`; may throw checked exceptions |
| `Executor` | Accepts a `Runnable` and decides how to execute it | `void execute(Runnable)` | Does not return a `Future`; does not require creating a new thread |
| `ExecutorService` | Extends `Executor` with lifecycle management and result-bearing tasks | `submit(...)`, `shutdown()`, `awaitTermination(...)` | Returns a `Future` from `submit`; supports cancellation, waiting, and shutdown |

Type relationships:

```text
Runnable       Callable<V>
    |               |
    +---- task -----+

Executor
   ^
   |
ExecutorService   (extends Executor)
   |
   +-- execute(Runnable)
   +-- submit(Runnable | Callable<V>)
   +-- shutdown / shutdownNow / awaitTermination
   +-- invokeAll / invokeAny
```

`ExecutorService` is an **interface**. `Executors` (plural) is a **utility/factory class** with methods for creating executors, such as `Executors.newFixedThreadPool(2)`. These two names are very easy to confuse.

## 3. Runnable: Tasks That Do Not Return a Value

`Runnable` is a functional interface with a single abstract method `run()`. It can be implemented using a regular class, an anonymous class, or a lambda. Use it when the behavior produces an intended side effect, such as logging, updating state, or sending a notification, and the caller does not need a return value from `run()`.

Standalone example runnable on Java 17:

**File `RunnableDemo.java`**

```java
public class RunnableDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable task = () ->
                System.out.println("Task running on: "
                        + Thread.currentThread().getName());

        Thread worker = new Thread(task, "worker-1");
        worker.start();
        worker.join();

        System.out.println("Main finished waiting");
    }
}
```

Compile and run:

```bash
javac RunnableDemo.java
java RunnableDemo
```

Exact output:

```text
Task running on: worker-1
Main finished waiting
```

Here:

- `task` only holds the behavior. Creating a `Runnable` object does **not** create a thread and does **not** execute it yet.
- `new Thread(task, "worker-1")` creates a `Thread` object associated with the task.
- `start()` asks the JVM to launch a new thread to invoke `run()`. Calling `task.run()` directly executes the task **synchronously on the current thread**.
- `join()` waits for the worker to finish; because of this, the last line always appears after the line printed by the worker. You should not use `Thread.sleep(...)` to guess when a task finishes.

Limitation: the signature of `run()` has no return value and does not declare `throws Exception`. You can still handle checked exceptions *inside* `run()`, and runtime exceptions can still occur. If you need a computed result or want to propagate checked exceptions to the caller as part of the task contract, `Callable<V>` is more appropriate.

## 4. Callable<V>: Tasks with a Result That Can Report Errors

`Callable<V>` is also a functional interface, but `call()` returns `V` and can declare `throws Exception`:

```java
import java.util.concurrent.Callable;

Callable<Integer> sum = () -> {
    int result = 0;
    for (int i = 1; i <= 5; i++) {
        result += i;
    }
    return result;
};
```

The snippet above is **a declaration to place inside an appropriate method or class**, not a standalone program. `Callable<Integer>` represents a computation that returns `15`. `Thread` has no constructor that accepts `Callable` directly; the standard way is to submit the `Callable` to `ExecutorService.submit(...)` and obtain a `Future<Integer>`.

The type parameter matters: `Callable<String>` yields `Future<String>`; `Callable<Integer>` yields `Future<Integer>`. The executor still does not know what the business work is; it only accepts the task and schedules it to run.

**Quick rule of thumb:** If you do not need a value, start with `Runnable`; if you need to receive a result or express checked exceptions from the task, choose `Callable<V>`. Even when the task is a `Runnable`, `submit(Runnable)` still provides a `Future<?>` to track completion or failure.

## 5. Executor: Decoupling Task Submission from Execution

`Executor` has a single abstract method:

```java
void execute(Runnable command);
```

The caller asks, "please execute this task"; the executor decides whether to run it immediately, create a thread, or queue it. The `Executor` contract does **not** guarantee that the task runs asynchronously or uses a thread pool.

Example of an executor that runs **immediately on the calling thread**:

**File `ExecutorDemo.java`**

```java
import java.util.concurrent.Executor;

public class ExecutorDemo {
    public static void main(String[] args) {
        Executor inlineExecutor = Runnable::run;
        inlineExecutor.execute(() ->
                System.out.println("Thread name: "
                        + Thread.currentThread().getName()));
    }
}
```

```bash
javac ExecutorDemo.java
java ExecutorDemo
```

Output:

```text
Thread name: main
```

The expression `Runnable::run` creates an `Executor` implementation that executes `command.run()` immediately on the calling thread. This is useful for demonstrating the contract or writing simple tests, though it provides no parallel execution. Another `Executor` can use a worker pool without requiring changes to the task-creation code.

Distinguishing `execute` from `submit`:

- `execute(Runnable)` is a method on `Executor`; it returns no object for tracking the work.
- `submit(...)` is added by `ExecutorService`; it returns a `Future` to retrieve results, observe errors, wait, or request cancellation.
- Both can reject new tasks, for example when the executor has already shut down; the common case is `RejectedExecutionException`. Some pool configurations also have custom rejection policies.

## 6. ExecutorService: Submitting Work, Receiving Future, and Managing Lifecycle

`ExecutorService` is typically implemented with a thread pool, allowing multiple tasks to share a set of workers. The following example uses the `Executors.newFixedThreadPool(2)` factory.

**File `ExecutorServiceDemo.java`**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorServiceDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Runnable greeting =
                    () -> System.out.println("Runnable completed");

            Callable<Integer> calculation = () -> {
                int sum = 0;
                for (int i = 1; i <= 5; i++) {
                    sum += i;
                }
                return sum;
            };

            Future<?> greetingDone = executor.submit(greeting);
            Future<Integer> result = executor.submit(calculation);

            greetingDone.get();
            System.out.println("Total = " + result.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac ExecutorServiceDemo.java
java ExecutorServiceDemo
```

Output is always in this order:

```text
Runnable completed
Total = 15
```

The `calculation` task may run or finish before `greeting` because the pool has two workers. However, the "Total" line is only printed after `greetingDone.get()` returns, so the order of the **two output lines** in this example is deterministic.

Meaning of each step:

1. `newFixedThreadPool(2)` creates a pool with at most two concurrently active workers; if more tasks arrive than can be processed immediately, additional tasks wait in a queue.
2. `submit(greeting)` and `submit(calculation)` schedule execution and immediately return `Future<?>` and `Future<Integer>`, unless rejected or an error occurs during submission.
3. `greetingDone.get()` waits for the `Runnable` to complete; on success, the value returned by the `submit(Runnable)` overload is `null`.
4. `result.get()` waits for and retrieves the value `15`; if `calculation` throws an exception, `get()` throws `ExecutionException` instead of a value.
5. `shutdown()` in `finally` signals the executor to stop accepting new work while continuing to process already accepted work. In this example, both tasks have already finished before reaching `finally`.

Keep in mind that `ExecutorService` manages **multiple tasks**, not "one `submit` creates one thread." Also, do not rely on worker thread names to determine which task will run first.

### Commonly Used submit Overloads

| Call | Return Type | `Future.get()` on Normal Completion |
|---|---|---|
| `submit(Runnable task)` | `Future<?>` | `null` |
| `submit(Runnable task, T result)` | `Future<T>` | The supplied `result` value, not a return value from `run()` |
| `submit(Callable<T> task)` | `Future<T>` | The value returned by `call()` |

`submit(Runnable, result)` is useful when you need to attach a predetermined result once a non-value-returning task completes successfully. It does not replace `Callable` for computations that produce a new result.

## 7. Future: State, Errors, Waiting, and Cancellation

`Future<T>` is a **handle** representing the result of a submitted task; it is not the task itself or a thread.

- `get()` blocks the calling thread until the task completes, is cancelled, or fails. A successful result is `T`; a failed task leads to `ExecutionException` (the root cause is in `getCause()`); a cancelled task leads to `CancellationException`.
- `get(timeout, unit)` waits at most for the specified duration; timing out throws `TimeoutException`. **Timing out does not automatically cancel the task**.
- `isDone()` is true when the task completed normally, failed, **or was cancelled**. Therefore "done" does not mean "succeeded."
- `isCancelled()` reports whether the task was cancelled.
- `cancel(false)` attempts to cancel a task that has not started, without requesting interruption of a running task. `cancel(true)` may request interrupting the running thread if the task is executing on a thread and cancellation succeeds; there is no guarantee of forcing the task to stop.

Example using a timeout (a code snippet placed inside a method that handles `InterruptedException` and `ExecutionException`):

```java
try {
    Integer value = future.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException timeout) {
    future.cancel(true);
    System.out.println("Timed out, task cancellation requested");
}
```

Here `future` is an existing `Future<Integer>` and requires `import java.util.concurrent.*`. This is **not a standalone program**. The printed message only confirms that the cancellation request call was made, not that the task has stopped; in a real program you should check the boolean return value of `cancel(true)` if that status matters.

### Where Do Errors from a Task Go?

When submitting a `Runnable`/`Callable`, an exception thrown inside the task is held so that `Future.get()` reports it via `ExecutionException`. Therefore, calling `submit` and ignoring the `Future` can cause business errors to go unobserved at the call site.

**File `FailureDemo.java`**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Callable<Integer> faultyTask = () -> {
                throw new IllegalStateException("Invalid state");
            };

            Future<Integer> future = executor.submit(faultyTask);
            try {
                System.out.println(future.get());
            } catch (ExecutionException failure) {
                Throwable cause = failure.getCause();
                System.out.println(
                        cause.getClass().getSimpleName()
                                + ": " + cause.getMessage());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac FailureDemo.java
java FailureDemo
```

Output:

```text
IllegalStateException: Invalid state
```

`get()` can also throw `InterruptedException` when the **waiting** thread is interrupted; this is distinct from an exception thrown **inside the task** and wrapped in `ExecutionException`.

With `execute(Runnable)`, there is no `Future` to retrieve errors. How runtime exceptions are propagated or reported depends on how the `Executor` runs the task: an inline executor may throw the error on the calling thread, while a worker thread may terminate abnormally and go through the `UncaughtExceptionHandler` mechanism. Do not assume `execute` and `submit` report errors the same way.

### Task Cancellation Requires Cooperation

Interruption (`interrupt`) is a cooperative signal, not a thread-kill operation. Tasks blocking on interruptible APIs, such as `Thread.sleep` or `BlockingQueue.take`, typically receive `InterruptedException`. A long-running task should check for interruption periodically and stop or clean up appropriately.

Example of **the body of a Runnable**, not a standalone program:

```java
Runnable responsiveTask = () -> {
    try {
        for (int i = 0; i < 100; i++) {
            if (Thread.currentThread().isInterrupted()) {
                return;
            }
            Thread.sleep(100);
            // Perform a short unit of work here.
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        // Preserve the interrupt signal so higher layers can detect it.
    }
};
```

When `InterruptedException` is caught, the interrupted status has usually been cleared; restore it with `Thread.currentThread().interrupt()` if you cannot rethrow it and the handling policy requires preserving the signal. Do not swallow the interrupt and continue running indefinitely. Also do not misuse `Thread.stop()`, as it is not a safe way to manage cancellation.

## 8. Shutting Down ExecutorService Properly

A thread pool can keep workers alive after `main` finishes; failing to shut down a pool you own can keep the application running or leak resources.

- `shutdown()`: stops accepting new tasks and lets already submitted tasks continue running; **does not wait** until all of them finish.
- `awaitTermination(timeout, unit)`: waits after shutdown has been initiated; returns `true` if all tasks terminated within the timeout, `false` if the timeout elapsed.
- `shutdownNow()`: attempts to stop running tasks by interrupting threads and returns the list of waiting tasks that had not started. This is best-effort and **does not guarantee immediate stoppage**.
- `isShutdown()`: shutdown has started; `isTerminated()`: all tasks have finished after shutdown. These two states are not synonymous.

Example of a **utility method to place inside a Java class**, used when tasks may run for a long time:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

// Method placed inside a class:
static void stopGracefully(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("There are still unfinished tasks");
            }
        }
    } catch (InterruptedException interrupted) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

This method protects the calling thread from waiting indefinitely and attempts cleanup when the timeout expires. `shutdownNow()` cannot force uncooperative tasks to stop; if a task ignores all interrupts, it may still be active after the timeout. The 5-second timeout is just an example and should be chosen based on business requirements. For Java 17, use `try/finally` or an explicit lifecycle management mechanism; do not assume `ExecutorService` can be used directly with `try-with-resources` as in newer JDK versions.

**Ownership matters:** The code that creates an `ExecutorService` is normally responsible for shutting it down. If a Spring application creates and manages a `ThreadPoolTaskExecutor` as a bean, let the container lifecycle manage it; do not arbitrarily call `shutdown` on a pool shared by other components.

## 9. Choosing Pool Type, Parallelism, and Queueing

Several common `Executors` factories:

| Factory | Typical Behavior | Points to Watch |
|---|---|---|
| `newSingleThreadExecutor()` | One worker running tasks sequentially | Do not submit tasks that wait on other tasks in the same pool; one hung task blocks the entire queue |
| `newFixedThreadPool(n)` | Up to `n` workers executing concurrently | Default queue has no configured capacity bound; bursts can cause memory growth |
| `newCachedThreadPool()` | Creates additional workers as needed, reuses idle workers | Worker count can grow very large under heavy load; consider resource limits |

Pool size is not "bigger is always faster." CPU-bound computations are constrained by core count and context-switching overhead. I/O-waiting tasks may benefit from higher concurrency, yet are still bounded by connection limits, external service speed, memory, and response time. Measure performance under realistic load.

`Executors.newFixedThreadPool(n)` is convenient for demonstrations, but its preconfigured unbounded queue is not safe enough for every high-traffic system. In production applications, consider `ThreadPoolExecutor` with explicit `corePoolSize`, `maximumPoolSize`, a bounded queue, and a rejection policy.

Example creating a pool **with a bounded queue** (declaration snippet inside a method, requires `import java.util.concurrent.*;`):

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
```

The pool above has at most four workers, queues at most 100 waiting tasks, and can throw `RejectedExecutionException` when it cannot accept more. It still requires `shutdown()` when no longer needed. With `ThreadPoolExecutor`, tasks first use core workers and are then placed into the queue; only when the queue is full does it consider scaling workers up to `maximumPoolSize`, so queue configuration strongly affects scaling behavior.

If you need execution after a delay or periodically, that is the job of `ScheduledExecutorService` (a specialized branch). Do not use a `Thread.sleep` loop to build a makeshift scheduler in general cases.

## 10. Coordinating Multiple Tasks

When you have a collection of `Callable<T>` tasks, in addition to calling `submit` individually, `ExecutorService` supports:

- `invokeAll(collection)`: submits the entire group and waits for all to finish, returning `List<Future<T>>` in **input order**, not completion order; each Future may hold an error or cancellation status. There is a timeout overload.
- `invokeAny(collection)`: returns the result of **one task that completes successfully**, not necessarily the first one submitted; remaining unfinished tasks are requested to cancel. If no task succeeds, the method reports an appropriate error.

Standalone example:

**File `InvokeAllDemo.java`**

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 2 * 2,
                    () -> 3 * 3
            );
            List<Future<Integer>> results = executor.invokeAll(tasks);

            int total = 0;
            for (Future<Integer> result : results) {
                total += result.get();
            }
            System.out.println("Total = " + total);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac InvokeAllDemo.java
java InvokeAllDemo
```

Output:

```text
Total = 13
```

A group of independent tasks can be dispatched to run concurrently, yet result aggregation still needs to handle errors and timeouts. `Future` is suited for waiting on/retrieving a single result; if you need to chain multiple asynchronous steps, combine results, or handle flexible event chains, you can explore `CompletableFuture` in a separate lesson.

## 11. Data Synchronization and Subtle Pitfalls

### Sharing State Across Workers Is Not Automatically Safe

A pool only coordinates execution; it does not automatically protect shared variables. For example, multiple tasks executing `count++` on an `int` can lose updates because incrementing consists of multiple read–compute–write operations. Design to avoid sharing mutable data, or use appropriate mechanisms such as `AtomicInteger`, synchronization, and concurrent collections.

The JDK defines important **happens-before** relationships for `ExecutorService`: actions on the submitting thread prior to `submit` are visible to the task; actions of the task happen before the caller receives the result via `Future.get()`. This gives a clear data-publication and result-observation relationship. However, this rule **does not replace** coordination mechanisms when multiple tasks concurrently modify the same variable.

### Do Not Wait on Work Queued Behind Yourself

Suppose you use `newSingleThreadExecutor()`:

1. Task A is occupying the single worker.
2. A submits task B into the **same pool** and calls `B.get()` to wait.
3. B sits in the queue waiting for A to release the worker; A waits for B ⇒ deadlock.

Code illustrating the buggy case, **do not run this snippet as-is as a complete example**:

```java
ExecutorService single = Executors.newSingleThreadExecutor();
single.submit(() -> {
    Future<Integer> inner = single.submit(() -> 42);
    try {
        System.out.println(inner.get()); // May wait indefinitely.
    } catch (InterruptedException | ExecutionException e) {
        Thread.currentThread().interrupt(); // Minimal illustration; see note below.
    }
});
```

This snippet only illustrates the wrong wait location and assumes `import java.util.concurrent.*`; it intentionally omits a run command. In real code, only restore the interrupted status when catching `InterruptedException`; `ExecutionException` must be handled according to its specific failure cause. The design fix is to avoid blocking a worker while waiting for work that only the same pool can execute, or to restructure tasks to eliminate circular dependencies.

### Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
|---|---|---|
| Calling `run()` thinking a new thread was created | `run()` runs like a normal method | Use `Thread.start()` or submit via an appropriate executor |
| Calling `submit` then discarding `Future` with no error handling | Errors may remain hidden inside the Future | Call `get()`, log completion/errors, or use an explicit observation mechanism |
| Calling `get()` right after each `submit` in a loop | Can turn intended parallel processing into sequential execution | Submit all work first, then collect results |
| Calling `get()` inside a worker waiting on work from the same pool | Can deadlock when the pool runs out of workers | Eliminate circular waiting; redesign dependencies |
| Not calling `shutdown()` on self-created pools | Workers/resources remain alive unintentionally | Identify the owner, shut down in `finally` |
| Assuming `shutdownNow()` forces every task to stop | Interruption is only a cooperative request | Write interrupt-responsive tasks and use sensible timeouts |
| Letting multiple workers mutate a shared `HashMap`/variable unprotected | Race conditions, corrupted data, or errors | Avoid shared mutable state; use synchronization or concurrent collections |
| Creating a new pool per request | Wastes threads and resources, hard to control load | Reuse an application-managed pool |
| Assuming `execute` is always asynchronous | An `Executor` can run inline | Check the actual implementation and contract |

**Note on mixed exception handling:** If catching `InterruptedException` together with another exception, never call `interrupt()` mechanically for both types. Split the catch blocks and restore the interrupt flag only when `InterruptedException` actually occurs.

## 12. Connection to Spring Framework

Spring provides `TaskExecutor` to abstract executing `Runnable`s, and `ThreadPoolTaskExecutor` is the common implementation wrapping a thread pool whose size, queue, and lifecycle can be configured within the container. The underlying Java concepts remain unchanged:

| Java Concurrency | Meaning in Spring |
|---|---|
| `Runnable` / `Callable` | The unit of work to run; business logic should be separated from worker management |
| `Executor.execute(Runnable)` | Mirrors the model of submitting tasks to `TaskExecutor` |
| `ExecutorService` / thread pool | Basis for understanding `ThreadPoolTaskExecutor`, capacity, queues, and rejection policies |
| `Future<T>` | Understanding results or errors from asynchronously submitted work; avoid arbitrary blocking |
| `shutdown` / lifecycle | Spring-managed pools should shut down with the application context lifecycle |

`@Async` enables running configured methods through a Spring executor, though its behavior depends on the proxy mechanism and async configuration; calling an `@Async` method internally via `this` usually bypasses the proxy and does not switch threads as expected. In addition, switching to another worker does not mean values in `ThreadLocal`, request context, or transactions on the calling thread are automatically propagated. Any cases requiring context propagation must be designed explicitly.

In web applications, do not use `@Async` indiscriminately to speed up every request: the work still needs CPU, connections, queues, resource access, and error handling. If tasks need durability across restarts, an in-process thread pool does not replace a durable task queue.

## 13. Choosing the Right Tool for the Requirement

| Practical Requirement | Initial Choice | Reason |
|---|---|---|
| Describe an operation with no result | `Runnable` | Concise and clear intent |
| Computation returning a value or checked exception | `Callable<T>` | `call()` has a return type and `throws Exception` |
| Only want to submit a `Runnable`, no result/lifecycle needed | `Executor` | Minimal contract, easy to swap implementations |
| Want to retrieve results, wait for completion, or control pool shutdown | `ExecutorService` + `Future` | Provides `submit` and lifecycle management |
| Multiple independent tasks needing results | `ExecutorService.invokeAll` or multiple `Future`s | Can run concurrently, then gather results |
| Spring application needing a shared pool | Configured `ThreadPoolTaskExecutor` bean | Centralized lifecycle and resource bounds |

You can remember the chain of thought: **choose task → choose executor → submit task → observe completion/errors → shut down via the right owner**. The question "do we need a new thread?" should usually come after "what are the tasks and who is responsible for managing them?".

## 14. Self-Practice and Review Questions

1. Create a `Runnable` that prints the thread name and compare behavior when calling `run()` directly versus submitting via `ExecutorService.execute(...)`. Does every use of `Executor` switch to another thread? Explain using `ExecutorDemo`.
2. Write a `Callable<Long>` that computes the sum from 1 to 100 and submit it to `newSingleThreadExecutor()`. Verify `Future.get()` returns `5050`; always close the executor in `finally`.
3. Submit three `Callable<Integer>` tasks to a two-worker pool using `invokeAll`. Predict the order of the returned `List<Future<Integer>>` when the third task finishes fastest.
4. Replace one `Callable` with a task that throws `IllegalArgumentException`. Check `Future.isDone()` and inspect the cause via `ExecutionException.getCause()`. Why does `isDone() == true` not mean the task succeeded?
5. Write a task that sleeps in short intervals, call `cancel(true)` while it is running, and observe its state. Why must the program handle `InterruptedException` and why can it not rely on `cancel(true)` as a forced kill command?
6. Draw a timeline of a single-worker pool when A submits B and then calls `B.get()`. Explain the deadlock and propose how to decouple the dependency.

**Guiding answers:** (1) `run()` executes on the caller, `execute` depends on the implementation; (2) total equals 5050; (3) `invokeAll` returns Futures in input list order; (4) `isDone` is also true for errors/cancellation; (5) interruption is cooperative; (6) A holds the worker so B never gets a chance to run. Verify your code with `javac`/`java` instead of relying on `Thread.sleep` to guess execution order.

## 15. Key Takeaways

- **`Runnable` and `Callable` describe work**; `Executor` and `ExecutorService` coordinate execution.
- **`Callable<V>` returns a value** and can throw checked exceptions; `Runnable.run()` lacks both in its signature.
- **`execute` returns no Future**, whereas **`submit` returns a Future** to wait, receive errors, retrieve results, or cancel.
- **`Future.get()` can block**, `isDone()` does not mean success, and `cancel(true)` only requests cancellation/interruption on a best-effort basis.
- **Pools have lifecycles, queues, and resource limits**. The pool owner is responsible for shutting it down; Spring can own and manage pools on behalf of the application.
- **Concurrency is not automatically thread-safe**: data sharing, timeouts, and inter-task dependencies must be designed explicitly.
