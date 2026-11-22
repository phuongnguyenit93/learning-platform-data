# Distinguishing Thread Work and Task Lifecycle in Java

> **Key takeaway:** A **thread** is a thread of execution; a **task** is a unit of work. A thread has its own lifecycle and execution states. A task has its own progression of submission, execution, completion, failure, or cancellation. The two lifecycles can be related, but they are not identical—especially when using executors, thread pools, and virtual threads.

This lesson only covers **general Java concurrency** with `Thread`, `Runnable`, `Callable`, and `java.util.concurrent`; it does not discuss the Spring framework or Spring-managed component lifecycles.

## 1. Why distinguish them?

A thread is like **the worker performing the work**; a task is like **a work ticket**. One worker can handle multiple tickets sequentially; an unclaimed ticket remains in the queue; finishing a ticket does not mean the worker leaves the system. A ticket cancelled before being picked up does not necessarily mean anyone ever executed it.

| Concept | Key question | Representation in Java |
| --- | --- | --- |
| **Thread** | Which thread is the code running on? Has the thread started, is it waiting, or has it terminated? | `Thread`, `Thread.currentThread()`, `Thread.State` |
| **Task** | What work needs to be done? Has a given execution started, succeeded, failed, or been cancelled? | `Runnable`, `Callable<V>` |
| **Task handle** | How do we wait for and inspect the result of an asynchronous job? | `Future<V>`, `FutureTask<V>`, `CompletableFuture<V>` |
| **Executor** | Who accepts, queues, and schedules tasks for execution? | `Executor`, `ExecutorService`, thread pool |

There is no rule that **each task must have its own platform thread**. In a thread pool, a single worker thread can run multiple tasks sequentially. A task sitting in a queue may not have had any thread start executing it yet. A `Runnable` object can be used across multiple runs, including concurrently on different threads; therefore, if a task holds shared mutable state, it must be properly synchronized.

## 2. `Runnable` and `Callable` describe work

`Runnable` has the method `void run()`, returns no value, and does not declare checked exceptions in the `run()` signature:

~~~java
Runnable print = () -> System.out.println("Hello from task");
~~~

This line only creates a **work description**. It has not created a thread and has not executed `print.run()`. Calling `print.run()` directly is simply a normal method call on the **current thread**.

`Callable<V>` has the method `V call() throws Exception`, making it suitable when a task produces a result or needs to propagate an exception to the receiver:

~~~java
import java.util.concurrent.Callable;

Callable<Integer> calculate = () -> 6 * 7;
~~~

`Runnable` and `Callable` do not decide on their own which thread runs them. They can be executed directly by a thread or submitted to an executor. A single task submission is typically one **execution of work**, which is not identical to the identity of the lambda object used as the task.

By contrast, a `Thread` object represents a thread of execution:

~~~java
Runnable work = () -> System.out.println("working");
Thread worker = new Thread(work, "worker");
worker.start();
~~~

`new Thread(work)` creates a thread in the `NEW` state. `start()` asks the JVM to start a separate thread of execution and then execute `work.run()` on that thread. A **`Thread` object can only be started once**; calling `start()` a second time throws `IllegalThreadStateException`. To do the work again, create a new `Thread` or submit a new task to an appropriate executor.

## 3. Example 1: Direct `run()` vs. `start()`

Create the file `RunVsStart.java` (Java 17+):

~~~java
public class RunVsStart {
    public static void main(String[] args) throws InterruptedException {
        Thread mainThread = Thread.currentThread();
        Runnable work = () -> System.out.println(
                "on main = " + (Thread.currentThread() == mainThread));

        Thread worker = new Thread(work, "worker");

        System.out.println("initial = " + worker.getState());
        worker.run(); // Called directly on main.
        System.out.println("after direct run = " + worker.getState());

        worker.start(); // Starts a new thread.
        worker.join();  // Waits for worker to finish.
        System.out.println("after join = " + worker.getState());
    }
}
~~~

Compile/run:

~~~bash
javac RunVsStart.java
java RunVsStart
~~~

Output:

~~~text
initial = NEW
on main = true
after direct run = NEW
on main = false
after join = TERMINATED
~~~

Because `worker.run()` is just a method call, the body of `work` first runs directly on `main`, and `worker` remains `NEW`. Only `worker.start()` allows the body to run on another thread. `join()` makes `main` wait for the new thread to finish, so the last line observes `TERMINATED`. Lesson: **executing the code in `run()` does not mean starting the `Thread` object**.

In this `new Thread(runnable)` usage, one thread lifecycle is tied to one invocation of `run()` when `start()` is called. That is a relationship of creating a thread directly, **not a rule for all tasks**.

## 4. Thread lifecycle: six `Thread.State` values

`Thread.getState()` returns a state at the moment it is read. The states defined by Java are:

| State | Meaning |
| --- | --- |
| `NEW` | Not yet started via `start()` |
| `RUNNABLE` | Executing in the JVM or in a state eligible to be scheduled |
| `BLOCKED` | Waiting to acquire a **monitor lock** to enter/re-enter a `synchronized` block |
| `WAITING` | Waiting indefinitely for an action from another thread, e.g., `Object.wait()`, `join()` without timeout, or `LockSupport.park()` |
| `TIMED_WAITING` | Waiting with a time limit, e.g., `sleep`, `wait(timeout)`, `join(timeout)` |
| `TERMINATED` | The thread has finished because `run()` returned or exited via an uncaught exception |

Simplified diagram:

~~~text
NEW -- start() --> RUNNABLE <----> BLOCKED / WAITING / TIMED_WAITING
                         |
                         +-- run() finishes --> TERMINATED
~~~

The diagram above is only a mnemonic; waiting states can transition back and forth multiple times, and the details depend on what the thread is doing.

- `RUNNABLE` does **not** prove the thread is actively using the CPU at that exact moment; it may be waiting to be scheduled by the operating system.
- `BLOCKED` is the state of **waiting for a monitor**, not a generic name for all blocking operations such as I/O or queues.
- `WAITING` is not an error by default; a worker in a pool may legitimately be waiting for the next task.
- `getState()` is only a snapshot; checking the state and then acting on the assumption that it has not changed is a race condition bug.
- `TERMINATED` belongs to **that specific thread**. Completing a task in a pool does not require the thread pool worker to terminate.

Do not use `Thread.sleep()` or a loop polling `getState()` as a tool to coordinate the ordering of two tasks. Use primitives with synchronization contracts such as `join`, `Future.get`, `CountDownLatch`, `BlockingQueue`, or locks/conditions when needed.

## 5. Task lifecycle: a work model, not `Thread.State`

A task can go through these logical stages:

~~~text
CREATED -> SUBMITTED -> QUEUED -> RUNNING -> SUCCEEDED
                            |         \----> FAILED
                            +---------------> CANCELLED
                                      \-----> CANCELLED (cancel requested while running)
~~~

This is a **conceptual model**, not a built-in enum present on every `Runnable`/`Callable`. A task that has not been submitted has not been accepted by any executor; a task may throw `RejectedExecutionException` when the executor does not accept work; some tasks are executed directly without being queued; cancelling while running does not mean the body has stopped immediately.

Comparison table along the two axes:

| Situation | Thread | Task |
| --- | --- | --- |
| Just called `new Thread(work)` | `NEW` | `work` has not run on that thread yet |
| Task sitting in a pool queue | Worker is running another task or waiting for work | This task **has not started** |
| Task calling I/O or waiting on a lock | Thread may be `RUNNABLE`/`WAITING`/`BLOCKED`... depending on the API | Task **is executing**, not yet finished |
| Task just finished in a thread pool | Worker may remain alive to accept another task | Task **completed** |
| Task throws an exception in `submit(Callable)` | Worker may continue serving work | Task's Future is **done due to failure** |
| Task cancelled before starting | No worker needs to run the body | Future may be **done due to cancellation** |

A task waiting in an **executor queue** does not have its own `Thread.State.WAITING`, because a task is not a thread. Nor can you look at a worker in `WAITING` and conclude which task has finished. You must track the task's result directly.

## 6. Executors separate where work is submitted from where it runs

`ExecutorService` can accept `Runnable` or `Callable`:

~~~java
// API illustration, not a standalone program.
ExecutorService executor = Executors.newFixedThreadPool(2);
Future<Integer> answer = executor.submit(() -> 42);
int value = answer.get();
executor.shutdown();
~~~

With a two-worker thread pool, many tasks can be queued together; the executor proactively dispatches work onto available workers. This does not mean there is a dedicated thread for each `submit`. `Future<Integer>` tracks the **task** result, not the alive/dead status of a worker.

`execute(Runnable)` submits work without returning a `Future`. `submit(...)` returns a `Future`; this is useful for waiting for the result, detecting errors, or requesting cancellation. With `submit(Runnable)` without providing a separate result, `Future.get()` returns `null` on success.

### Example 2: two tasks, one worker stays alive after tasks complete

Create `TwoTasksOneWorker.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TwoTasksOneWorker {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Thread> first =
                    executor.submit(() -> Thread.currentThread());
            Future<Thread> second =
                    executor.submit(() -> Thread.currentThread());

            Thread firstWorker = first.get();
            Thread secondWorker = second.get();

            System.out.println("same worker = "
                    + (firstWorker == secondWorker));
            System.out.println("first done = " + first.isDone());
            System.out.println("second done = " + second.isDone());
            System.out.println("worker alive = " + secondWorker.isAlive());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac TwoTasksOneWorker.java
java TwoTasksOneWorker
~~~

Output under normal worker operation in this example:

~~~text
same worker = true
first done = true
second done = true
worker alive = true
~~~

The two tasks are processed sequentially on the same worker of `newSingleThreadExecutor()`. The `get()` calls confirm **both tasks are done**, while the worker is still alive because `shutdown()` is only called afterward in `finally`. If a worker encounters an abnormal failure, the executor may create a replacement worker; this example is not a guarantee of permanent worker identity.

This is a practical difference: a worker thread can outlive many task executions that it takes on.

### Example 3: a task not yet running because it is queued

Create `QueuedTask.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class QueuedTask {
    public static void main(String[] args) throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> first = executor.submit(() -> {
                gate.await();
                return "first finished";
            });
            Future<String> second =
                    executor.submit(() -> "second finished");

            System.out.println("second done before release = "
                    + second.isDone());

            gate.countDown();
            System.out.println(first.get());
            System.out.println(second.get());
        } finally {
            gate.countDown();
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac QueuedTask.java
java QueuedTask
~~~

Output:

~~~text
second done before release = false
first finished
second finished
~~~

In a single-worker executor, the first task must wait on `gate`, so the second task cannot be executed by the worker before `main` signals it. `second.isDone()` is guaranteed to be `false` at the first check. No other thread is running the body of the second task at that moment. After `countDown()`, the two `Future.get()` calls wait in turn and retrieve the results.

`CountDownLatch` here provides a clear coordination relationship; using `Thread.sleep` to create coincidental timing would make the example dependent on machine/load.

## 7. How does `Future` track task completion?

`Future<V>` represents the result of an asynchronous computation. In Java 17:

| API | Main meaning |
| --- | --- |
| `get()` | Waits if necessary, then returns the result; or throws `ExecutionException`/`CancellationException`, or `InterruptedException` if the waiter is interrupted |
| `get(timeout, unit)` | Waits at most for a duration; may throw `TimeoutException`, **does not automatically cancel the task** |
| `isDone()` | `true` when the computation has succeeded, failed, **or been cancelled** |
| `isCancelled()` | `true` when the task handle was cancelled before completion |
| `cancel(false)` | Requests cancellation without requesting interruption of running work |
| `cancel(true)` | Requests cancellation and attempts to interrupt the executing thread if possible |

**`isDone() == true` does not mean "succeeded"**. A task that threw an exception is still done. A task cancelled before starting is also done. With `get()`, the caller distinguishes a normal result, an `ExecutionException` wrapping the cause from the task, and a `CancellationException`.

Since Java 19, `Future` has additional APIs such as `state()` with states `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`. In the context of `Future.State`, `RUNNING` can include a computation that is **not yet complete but still queued**; do not read that state name as "currently occupying CPU". Java 17 examples should use `get/isDone/isCancelled` if they are meant to run on a Java 17 baseline.

### Example 4: task fails, Future is still done

Create `TaskFailure.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskFailure {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(() -> {
                throw new IllegalStateException("failed");
            });

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run `javac TaskFailure.java` and `java TaskFailure`:

~~~text
cause = IllegalStateException
done = true
cancelled = false
~~~

`Future.get()` reports that the task failed and provides the cause. When running a `Runnable` with a directly created `Thread`, `Thread.join()` **only waits for the thread to finish**—it does not return a value or rethrow exceptions from the other thread. If you need to track uncaught exceptions of a raw thread, use `Thread.UncaughtExceptionHandler` or design an appropriate error-reporting channel. `submit(Callable)` is usually more convenient for tasks that need a result/failure.

### Example 5: cancelling a task that never ran

Create `CancelBeforeRun.java`:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.FutureTask;

public class CancelBeforeRun {
    public static void main(String[] args) throws Exception {
        FutureTask<Integer> task = new FutureTask<>(() -> 42);

        System.out.println("cancel accepted = " + task.cancel(false));
        System.out.println("done = " + task.isDone());
        System.out.println("cancelled = " + task.isCancelled());

        try {
            task.get();
        } catch (CancellationException expected) {
            System.out.println("result unavailable");
        }
    }
}
~~~

Run `javac CancelBeforeRun.java` and `java CancelBeforeRun`:

~~~text
cancel accepted = true
done = true
cancelled = true
result unavailable
~~~

In this example, no thread ever executed the body `() -> 42`. A successful `FutureTask.cancel(false)` still causes the task handle's `isDone()` to return `true`. A computation being marked complete due to **cancellation** is very different from "a thread finished the work".

## 8. Task cancellation is cooperative; it does not mean terminating the thread

If a task has already started, `future.cancel(true)` may attempt to interrupt the executing thread. Keep in mind:

1. `cancel(true)` signals a **request**, not a guarantee that the code will stop immediately.
2. The task may ignore the interrupt flag, be performing I/O that does not respond to interruption, or deliberately finish in its own way.
3. The `Future` may already report cancelled/done **before the task body actually exits**.
4. A thread in a pool **should not be thought of as belonging to one task**; after the task ends, the worker can serve the next task.
5. Avoid `Thread.stop()`: it is a dangerous legacy API. Long-running tasks need a cooperative cancellation mechanism and resource cleanup in `finally`.

Example of handling interruption for a task that may wait:

~~~java
// Illustrates only the task body; not a standalone program.
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Return decision-making to the outer layer and exit the task.
} finally {
    releaseOwnedResources();
}
~~~

In real code, `doOneUnitOfWork` and `releaseOwnedResources` must be implemented; the snippet above illustrates **interruption semantics**. If the body calls methods that throw `InterruptedException`, it can exit, perform cleanup, or restore the interrupt flag depending on the contract. Do not swallow the interrupt and continue an unintended infinite loop.

## 9. `Thread.join()`, `Future.get()`, and `awaitTermination()` are different

| API | What is waited on | Result and errors |
| --- | --- | --- |
| `Thread.join()` | **A thread** finishing | Does not return a task value; does not propagate exceptions inside the thread to the caller |
| `Future.get()` | **A computation** finishing/producing a result | Returns the result or corresponding failure/cancellation |
| `ExecutorService.awaitTermination(...)` | **An executor** stopping after shutdown | Boolean indicating whether the executor terminated within the timeout |

Both `join()` and `Future.get()` have memory visibility contracts: actions in the terminating thread happen-before actions following a successful `join()`; actions in an asynchronous computation happen-before actions following the corresponding `Future.get()` on another thread. Therefore, receiving results after these mechanisms is safer than polling thread state or waiting for a guessed duration.

`CompletableFuture.join()` is also named `join`, but it is **not** `Thread.join()`: it waits for and retrieves the result of a completion stage, with its own exception semantics. You must identify the exact target before saying "join waits for a thread".

## 10. Executor lifecycle is the third axis

Alongside threads and tasks, an executor has its own operational state:

- `shutdown()` initiates an orderly shutdown; it stops accepting new tasks, continues processing already-accepted tasks, and **returns immediately** (it does not wait for completion).
- `awaitTermination(timeout, unit)` waits for the executor to finish after a shutdown request; returns a boolean and does not provide individual task results.
- `shutdownNow()` attempts to stop running tasks via interruption and returns the queued tasks that had not started. This is **best effort**: tasks may not respond to interruption immediately.
- `isShutdown()` indicates that shutdown was requested, while `isTerminated()` indicates that the executor has finished after shutdown. A single `Future` completing does not by itself transition the executor to terminated.

Java 17 executor shutdown pattern:

~~~java
// Illustrated with a previously created executor variable.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, java.util.concurrent.TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

The 5-second timeout is the caller's wait time, **not a guarantee** that all tasks stop within 5 seconds. Production designs need to consider timeouts, backpressure, queue capacity, worker count, failure reporting, and dedicated shutdown policies.

## 11. Virtual threads in Java 21+ make the distinction even clearer

A virtual thread is still a `Thread` object, but it is scheduled by the JVM onto carrier platform threads rather than corresponding to a new OS thread for each task. Java 21 provides an executor that creates **one virtual thread per task**:

~~~java
// VirtualPerTask.java — Java 21+ only
import java.util.concurrent.Executors;

public class VirtualPerTask {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var future = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            System.out.println(future.get());
        }
    }
}
~~~

Run:

~~~bash
javac VirtualPerTask.java
java VirtualPerTask
~~~

Output:

~~~text
true
~~~

Here each task is assigned a **new virtual thread**; the carrier platform threads can be reused by the runtime. Virtual threads do not eliminate the concepts of task lifecycle and `Future`: a task can still complete, fail, or be cancelled; a thread still has its own identity and state. `ExecutorService.close()` / try-with-resources requires JDK 19+; the example explicitly notes Java 21, **so do not apply this syntax to Java 17**.

The difference between "one virtual thread per task" and "one platform thread per task" is crucial when considering resources, scheduling, and scalability.

## 12. Choosing an API based on the question you need to answer

| Question | Appropriate tool | Mistake to avoid |
| --- | --- | --- |
| What is the work's logic? | `Runnable`/`Callable` | Mixing work logic with thread identity |
| Want to start a raw thread? | `new Thread(work).start()` | Calling `run()` and thinking you have concurrency |
| Did the task succeed or fail? | `Future.get()` / completion-specific API | Looking only at `isDone()` or `Thread.State` |
| Which tasks are waiting in the queue? | Executor/queue metrics, task ID | Reading `Thread.State.WAITING` and attributing it to a task |
| Must two things happen in order? | `join`, `Future.get`, `CountDownLatch`, `BlockingQueue` | `sleep()`, priority, guessing scheduling |
| Need to request stopping a task? | `cancel(...)`, `interrupt()`, cooperative stop logic | Assuming cancel forcibly terminated the code |
| Want to know if the executor accepts more work? | Check shutdown policy, handle rejection | Looking at whether a worker is still `RUNNABLE` |
| Need to wait for the executor to stop? | `shutdown` + `awaitTermination` | Waiting only on one task's Future |
| Want to debug what a thread is waiting on? | Thread dump, stack, `Thread.getState()` | Equating thread state with business task state |

### Three scenarios to analyze yourself

**Scenario A:** A pool has 4 workers and 1000 accepted tasks. Are there 1000 threads? **No.** Many tasks may be queued, with only a few being executed by workers. Depending on the executor policy, tasks may wait for a long time.

**Scenario B:** `Future.isDone() == true`, but the task was cancelled before running. Did any thread necessarily execute the task body? **No.** The done flag reflects the task handle state, including cancellation.

**Scenario C:** A worker is `WAITING`, while the `Future` of the previous task has succeeded. Is that a contradiction? **No.** The worker can wait for the next job after the previous task finishes.

## 13. Common misconceptions

1. **"Creating a task means it is running."** False: creating a work object is distinct from submitting, accepting, scheduling, and executing it.
2. **"`run()` and `start()` are equivalent."** False: calling `run()` directly does not create a new thread.
3. **"When a task finishes, its thread is destroyed."** False for thread pools: workers are typically reused.
4. **"`Thread.State.TERMINATED` indicates the Future succeeded."** No: a thread terminating does not convey the success state of a corresponding task, especially when multiple tasks are managed.
5. **"`isDone()` means the result succeeded."** No: failures and cancellations are also done.
6. **"`cancel(true)` guarantees killing the task immediately."** No: it is a cooperative effort via interruption.
7. **"`Future.get(timeout)` automatically cancels the work on timeout."** No: it only stops waiting and throws `TimeoutException`.
8. **"Once `shutdown()` returns, all workers/tasks have stopped."** No: `shutdown()` initiates closing, while termination is a later stage.
9. **"`RUNNABLE` definitely means currently using the CPU."** No: the JVM state does not prove the OS scheduler has assigned a CPU at the moment of observation.
10. **"Virtual-thread-per-task means one OS thread per task."** No: virtual threads are scheduled by the JVM onto carrier threads.

## Official API References

- [Java SE 21 — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html), [`Thread.State`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).
- [Java SE 21 — `Runnable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html), [`Callable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html).
- [Java SE 21 — `Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html), [`FutureTask`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html).
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html).
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): synchronization fundamentals and *happens-before*.

**Remember:** When asking **who is running/waiting**, observe the thread. When asking **how far the work has progressed, or whether it succeeded or failed**, observe the task and its result. When asking **whether the system will accept or dispatch more work**, observe the executor.