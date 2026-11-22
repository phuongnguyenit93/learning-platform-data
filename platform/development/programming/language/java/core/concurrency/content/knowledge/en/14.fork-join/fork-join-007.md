# Distinguishing invoke(), execute(), and submit() in the Fork/Join Framework

When using `ForkJoinPool`, the three methods **`invoke()`**, **`execute()`**, and **`submit()`** can all submit a task to the pool, but **they differ in whether the calling thread waits, the return type, and how results/errors are retrieved**. If you confuse them, the application may block unexpectedly, silently ignore exceptions, or lack a mechanism to confirm task completion.

The core focus here is the **`java.util.concurrent.ForkJoinPool`** API, along with `ForkJoinTask`, `RecursiveTask`, and `RecursiveAction` as of Java 17+. This is general Java concurrency knowledge, independent of any other framework.

**Quick summary:**

- **`pool.invoke(task)`**: submits the task and **waits for the task to complete**, then **returns the result `V`** or propagates errors according to Fork/Join rules.
- **`pool.execute(task)`**: submits the task **without waiting**, and the method returns **`void`**; to know when it finishes, you need to keep a reference to the task or use another completion mechanism.
- **`pool.submit(task)`**: submits the task **without waiting**, but **returns a `ForkJoinTask<V>`**, on which you can call `join()`, `get()`, `get(timeout)`, `isDone()`, and `cancel()`.

`invoke()` here refers to **`ForkJoinPool.invoke(ForkJoinTask)`**. Do not confuse it with `ForkJoinTask.invoke()` or `ExecutorService.invokeAll(Collection)`: their names are similar, but their invocation style, receiver object, and semantics are different.

## 1. Comparison by API Contract

| Criterion | `pool.invoke(task)` | `pool.execute(task)` | `pool.submit(task)` |
|---|---|---|---|
| Behavior on call | **Waits** for the task to complete before returning. | Submits for execution; **does not wait** for completion. | Submits for execution; **does not wait** for completion. |
| Return value | `V` of `ForkJoinTask<V>`. | `void`. | `ForkJoinTask<V>` for the overload accepting `ForkJoinTask<V>`. |
| `RecursiveAction` task | Result of type `Void` (usually `null`). | Does not receive a result from the execute call. | Has a handle that can be awaited to confirm completion. |
| How to retrieve result | Available immediately after invoke returns normally. | Must retain the task itself or use another mechanism. | Call `join()`/`get()` on the handle when needed. |
| Timed wait | `invoke()` has no timeout overload. | `execute()` does not wait; the handle can be awaited separately. | `handle.get(timeout, unit)` provides a bounded wait. |
| Computation errors | Can throw unchecked exception/Error according to task semantics. | Does not automatically return task errors to the calling thread via the asynchronous `execute()` call. | Errors can be observed via `join()` or `get()`. |
| Appropriate scenario | Caller needs the **result immediately** to proceed. | Fire-and-dispatch with a custom-designed completion/error tracking rule. | Caller wants to continue doing other work and then **wait/check/cancel** the task. |

With `execute()` and `submit()`, "without waiting" means **not waiting for the task to finish computing**; the call still performs submission/scheduling work and can throw submission errors (for example, if the executor rejects the work). Do not assume that submit is a zero-cost operation or always succeeds.

## 2. Why is ForkJoinTask used instead of a regular Runnable?

`ForkJoinTask<V>` is an object representing Fork/Join work, with built-in completion and result-retrieval mechanisms. Two commonly used classes:

- `RecursiveTask<V>`: overrides `protected V compute()` to compute and return a **result V**.
- `RecursiveAction`: overrides `protected void compute()` for work **without a return value**.

These tasks are designed for divide-and-conquer problems, where one branch can `fork()` sub-branches, compute another branch, and then `join()` to combine the results. `ForkJoinPool` uses workers and **work-stealing** to balance branches; it **does not create a new Thread for each task**.

Diagram:

```text
                 Caller thread
                      |
             +--------+--------+
             |        |        |
           invoke   execute   submit
             |        |        |
             v        v        v
           WAIT     return   return handle
             |        |        |
             v        |        +--> handle.get()/join() if needed
           result    |              
                      |
                ForkJoinPool
                      |
              work-stealing workers
                      |
               RecursiveTask/Action
```

You should not apply the same "fork every tiny piece of work" pattern to every problem. The overhead of creating tasks, splitting branches, managing deques, and joining can exceed the computation itself if the work is too small. A **base case/threshold** is needed when implementing recursive `compute()`.

## 3. invoke(): synchronous call returning a result

Core signature:

```java
public <T> T invoke(ForkJoinTask<T> task)
```

This is an **illustrative API signature**, not a method you need to define yourself. Example:

```java
long total = pool.invoke(new SumTask(data, 0, data.length));
```

`pool.invoke(...)` **does not return before the root task completes normally**, so the caller can use the total immediately on the next line. If the task throws an unchecked exception/Error, waiting/calling via the Fork/Join API can propagate the error to the caller; it does not turn an error into a default aggregated value.

Characteristics:

1. Easy to write when the result is needed before the next step, such as the sum or statistics of an array.
2. The caller must accept **being blocked** until the task finishes. If the task does not complete, the invoke call also has no built-in timeout.
3. Can be used with `RecursiveTask<V>` returning `V`, or `RecursiveAction` with `Void`.
4. No need to manually call `join()` on the **root** to get the result after `pool.invoke(root)`: invoke already waits for the root.
5. Branches inside the root must still be coordinated properly: if the result depends on children, the root needs `join()` or `invokeAll()` for them.

### Example 1: ForkJoinPool.invoke() computing a sum

Create file **`ForkJoinInvokeDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinInvokeDemo {
    static final class SumTask extends RecursiveTask<Integer> {
        private final int from;
        private final int to;

        SumTask(int from, int to) {
            this.from = from;
            this.to = to;
        }

        @Override
        protected Integer compute() {
            if (to - from <= 10) {
                int sum = 0;
                for (int i = from; i < to; i++) {
                    sum += i;
                }
                return sum;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(from, mid);
            SumTask right = new SumTask(mid, to);

            left.fork();
            int rightSum = right.compute();
            int leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            SumTask root = new SumTask(1, 101);
            int result = pool.invoke(root);

            System.out.println("Sum: " + result);
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinInvokeDemo.java
java ForkJoinInvokeDemo
```

Output:

```text
Sum: 5050
Root done: true
```

**Explanation:** the range `[1,101)` contains the numbers 1 through 100, with a sum of `100 * 101 / 2 = 5050`. Each branch with more than 10 numbers is split in half. `left.fork()` creates an opportunity for parallel execution, the current worker computes `right`, and then `left.join()` brings the left result back to the parent node. `pool.invoke(root)` returns only after the entire tree has been combined; `root.isDone()` is true at the time of printing. The execution order of the two branches may vary, but stdout does not depend on scheduling.

**Avoid misconception:** `invoke()` does not mean "runs only on the caller thread." Task execution follows ForkJoinPool's mechanism, and workers can help each other process the task tree. Conversely, the caller waiting synchronously does not guarantee that the pool used more than one worker.

## 4. execute(): submits a task without waiting and without returning a handle

Overload for ForkJoinTask:

```java
public void execute(ForkJoinTask<?> task)
```

This is an illustrative signature. The call:

```java
pool.execute(task);
```

**returns `void`**, so no new `Future` is returned from this call. However, if **the caller already holds a reference to `task`** and it is a `ForkJoinTask`, the task itself already has `join()`, `get()`, `isDone()`, and `cancel()` APIs. "Execute does not return a handle" **does not mean** you cannot track the task if you kept the task object before calling execute.

The pool also has an `execute(Runnable)` overload from the Executor interface. With a `Runnable` lambda, the caller does not receive a `Future` from `execute()`; if you need a handle from a regular `Runnable`, `submit()` is usually more appropriate.

### Example 2: execute() does not wait; task.join() confirms completion

Use two latches to create a task that is guaranteed to be **running but unable to finish** at the moment main observes it. Thus, the example does not rely on `Thread.sleep()` or scheduler luck.

Create file **`ForkJoinExecuteDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

public class ForkJoinExecuteDemo {
    static final class WaitingAction extends RecursiveAction {
        private final CountDownLatch started;
        private final CountDownLatch release;

        WaitingAction(CountDownLatch started, CountDownLatch release) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected void compute() {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted while waiting", e);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        WaitingAction task = new WaitingAction(started, release);

        try {
            pool.execute(task); // Does not wait for task completion.
            started.await();

            System.out.println("Before release, done: " + task.isDone());
            release.countDown();

            task.join(); // This is the step that waits for completion.
            System.out.println("After join, done: " + task.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("Pool terminated: "
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac ForkJoinExecuteDemo.java
java ForkJoinExecuteDemo
```

Output in a normal run without external interrupts:

```text
Before release, done: false
After join, done: true
Pool terminated: true
```

**Why?**

1. `pool.execute(task)` submits the task and returns without waiting for it to finish.
2. `started.await()` forces main to wait until `compute()` has started running.
3. `compute()` must wait on `release` before it can return; main has not opened the latch yet, so `task.isDone()` is guaranteed to be **false** before release.
4. Main opens the latch. `task.join()` waits for compute to finish, after which `task.isDone()` is **true**.
5. `shutdown()` stops accepting new tasks; `awaitTermination()` confirms that the dedicated pool has terminated within the example's five-second timeout.

This is a learning pattern illustrating the difference between **dispatch** and **completion**, not a recommendation to block Fork/Join workers with latches in production applications. ForkJoinPool prioritizes computational work; long blocking waits can reduce the number of useful workers.

## 5. submit(): submits without waiting, but returns a handle to manage the result

For the overload accepting ForkJoinTask:

```java
public <T> ForkJoinTask<T> submit(ForkJoinTask<T> task)
```

This is an illustrative signature. Example:

```java
ForkJoinTask<Integer> handle = pool.submit(rootTask);
```

The caller **is not blocked waiting for the task to finish at the submit call**, and can do other work. When the result is needed, you can call:

```java
Integer result = handle.join();
```

or:

```java
Integer result = handle.get();
```

Both snippets require the task/handle objects to be declared beforehand and, for `get()`, appropriate checked exception handling.

`ForkJoinPool.submit` also has overloads for **`Callable<T>`** and **`Runnable`**. With `Callable<T>`, the handle has a result of type `T`; with a plain `Runnable` that has no result, a `ForkJoinTask<?>` handle returns `null` from `get()` upon completion. There is also an overload `submit(Runnable, T result)` to attach a predetermined result per contract.

**Overload note:** If you pass a `RecursiveTask<V>` object, the compiler selects the specific overload accepting `ForkJoinTask<V>`. If you pass a `Callable<V>` or a `Runnable` lambda, it selects the corresponding overload based on the parameter type. For a lambda that returns a value, an explicit type (`Callable`) is needed to avoid ambiguity when multiple overloads exist.

### Example 3: submit() with RecursiveTask, Callable, and Runnable

Create file **`ForkJoinSubmitDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinSubmitDemo {
    static final class NumberTask extends RecursiveTask<Integer> {
        @Override
        protected Integer compute() {
            return 6 * 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        AtomicInteger ran = new AtomicInteger();

        try {
            ForkJoinTask<Integer> a = pool.submit(new NumberTask());
            ForkJoinTask<String> b = pool.submit(
                    (Callable<String>) () -> "callable-result"
            );
            ForkJoinTask<?> c = pool.submit(
                    (Runnable) ran::incrementAndGet
            );

            System.out.println("RecursiveTask: " + a.get());
            System.out.println("Callable: " + b.get());
            System.out.println("Runnable get: " + c.get());
            System.out.println("Runnable executed: " + ran.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinSubmitDemo.java
java ForkJoinSubmitDemo
```

Output:

```text
RecursiveTask: 42
Callable: callable-result
Runnable get: null
Runnable executed: 1
```

**Key points:**

- `a` is a `ForkJoinTask<Integer>`, and `a.get()` returns 42 after the task completes.
- `b` demonstrates the overload accepting `Callable<String>` and returning a String result.
- `c` demonstrates the overload accepting `Runnable`. Runnable does not return a business value, but `c.get()` waits for it to complete. Afterward `ran.get() == 1` because the method reference ran once.
- Although the three tasks may run in any order, `get()` on each handle ensures the corresponding print statement only proceeds once that task has completed. Because printing happens in main in a fixed order, **stdout is deterministic**.
- Using `submit` does not automatically mean "the task runs on another thread immediately"; it simply provides a **task-tracking handle** and a mechanism for the pool to execute it according to its schedule.

**About the Runnable method reference:** `ran::incrementAndGet` has a return value, but it is used in a `Runnable` context whose method is `void run()`; the incremented return value of the atomic counter is discarded. `get()` on the Runnable handle still returns `null`, not 1.

## 6. Waiting methods on ForkJoinTask: join(), get(), invoke()

A very common point of confusion is the same word `invoke` appearing on both the **pool** and the **task**.

| Call | Receiver | Meaning |
|---|---|---|
| `pool.invoke(task)` | `ForkJoinPool` | Submits the root task to the pool and **waits for the result**. |
| `task.invoke()` | `ForkJoinTask` | Starts executing **that task itself** and waits for the result; not a direct syntactic replacement for submitting a root to a **specific pool**. |
| `task.fork()` | `ForkJoinTask` | Schedules the task asynchronously in the current Fork/Join context. |
| `task.join()` | `ForkJoinTask` | Waits for an **already executing/scheduled task** to complete and returns the result; join itself should not be treated as submitting an unscheduled root task to a pool. |
| `task.get()` | `ForkJoinTask` / `Future` | Waits for completion and returns the result, but has checked exceptions. |
| `task.get(timeout, unit)` | `ForkJoinTask` / `Future` | Bounded wait; may throw `TimeoutException`. |

Inside `RecursiveTask.compute()`, the typical pattern is:

```java
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
```

This is an illustrative snippet; `left`/`right` are tasks, and `Result`/`combine` are assumed to be declared. **`fork()` and `join()` are mechanisms for coordinating child branches**, whereas `pool.invoke/execute/submit` are typically used at the application code boundary to submit the **root task**.

If you are outside a ForkJoinPool and want the root to run **on a dedicated pool**, call `pool.invoke(root)` or `pool.submit(root)`. Calling `root.invoke()` directly is not equivalent to selecting that dedicated pool.

## 7. join() and get(): differences in exceptions and interrupts

`ForkJoinTask.join()` and `ForkJoinTask.get()` can both wait for task completion, but their exception-handling contracts differ:

- **`join()`:** returns the result or throws an unchecked exception/Error (which may be rethrown by the framework from the task); **does not declare** `InterruptedException` or `ExecutionException`.
- **`get()`:** per the `Future` contract, can throw `InterruptedException` and `ExecutionException`; if the Future was cancelled, it throws `CancellationException`.
- **`get(timeout, unit)`:** adds `TimeoutException` so the caller does not have to wait indefinitely in a single wait call.
- **`invoke()`:** synchronous form that can propagate the task's unchecked exception, and does not provide a timeout parameter itself.

Table:

| Scenario | `join()` | `get()` |
|---|---|---|
| Task succeeds | Returns `V`. | Returns `V`. |
| Task throws unchecked exception | Propagates unchecked exception per ForkJoinTask contract. | Usually throws `ExecutionException`; retrieve the original error via `getCause()`. |
| Task is cancelled | `CancellationException`. | `CancellationException`. |
| Waiting thread is interrupted | Does not declare/handle it in the `InterruptedException` style of get. | `InterruptedException` on interruptible wait paths. |
| Caller wants a timeout | No `join(timeout)` overload. | `get(timeout, unit)` allows a bounded wait. |

**Do not use `join()` on tasks that have no completion path** and expect it to time out on its own. If a time budget is needed, use timed `get` at the appropriate boundary and design cooperative cancellation.

`ForkJoinTask` APIs have their own details regarding exceptions, cancellation, and blocking. Do not mechanically apply the semantics of `Thread.join()` or `CompletableFuture.join()` to them just because the method name is the same.

## 8. Example 4: submit() + get(timeout) so the caller does not wait indefinitely

`submit()` is often useful when the caller wants to submit a root task, do other work, and then **wait for the result within a deadline**. To demonstrate a timeout without relying on `sleep()`, the example uses a latch that blocks completion until the caller explicitly opens it.

Create file **`ForkJoinTimedGetDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ForkJoinTimedGetDemo {
    static final class DelayedTask extends RecursiveTask<Integer> {
        private final CountDownLatch started;
        private final CountDownLatch release;

        DelayedTask(CountDownLatch started, CountDownLatch release) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected Integer compute() {
            started.countDown();
            try {
                release.await();
                return 99;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Task interrupted", e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ForkJoinTask<Integer> handle =
                    pool.submit(new DelayedTask(started, release));
            started.await();

            try {
                handle.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("Timed out");
            }

            System.out.println("Cancelled by timeout: "
                    + handle.isCancelled());

            release.countDown();

            System.out.println("Result after release: "
                    + handle.get(5, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("Pool terminated: "
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac ForkJoinTimedGetDemo.java
java ForkJoinTimedGetDemo
```

Output in a normal run:

```text
Timed out
Cancelled by timeout: false
Result after release: 99
Pool terminated: true
```

**Explanation:** `started.await()` confirms that the root task has entered `compute()`, but it cannot finish while `release` remains closed. Therefore, the first `get(20, MILLISECONDS)` throws `TimeoutException`. A timeout **does not automatically cancel** the `ForkJoinTask`; `isCancelled()` remains false. After release is opened, the task completes and the subsequent `get` receives 99. Finally, main shuts down the dedicated pool and awaits termination.

This is an educational example illustrating the timeout API, **not a recommendation to insert long blocking waits into production Fork/Join compute methods**. ForkJoinPool is geared toward short computational branches and work-stealing. If the work mainly waits on I/O or blocking operations, evaluate another executor or API.

## 9. The asynchronous error issue: execute() can leave the caller unaware of task failure

`execute()` returns `void`, so this code:

```java
pool.execute(new FailingTask());
System.out.println("Submitted");
```

**does not prove that FailingTask completed successfully**. This snippet is illustrative: `FailingTask` must be a defined ForkJoinTask. If an error occurs after the execute call, it does not automatically become a synchronous exception on the calling thread at the `execute` line.

If the application needs confirmation:

- Keep the task: `ForkJoinTask<?> task = new FailingTask(); pool.execute(task); task.join();` and handle unchecked errors.
- Use `pool.submit(task)` and observe `handle.get()`, `get(timeout)`, or `join()`.
- Design a dedicated error-reporting/metrics channel when truly using "fire-and-forget"; do not silently lose errors.

With `submit()` on executors, exceptions may be held inside the Future rather than appearing immediately on the caller. **Do not discard the handle if the task is required to succeed or needs auditing.** The executor remaining alive or `submit()` returning normally only means the task submission request was accepted, not that the business outcome succeeded.

## 10. Interacting with RecursiveAction and Void results

`RecursiveAction` is a task type that does not return a value. Therefore:

```java
ForkJoinTask<Void> task = new MyRecursiveAction();
Void result = pool.invoke(task);
```

This is an illustrative snippet; `MyRecursiveAction` must extend `RecursiveAction` and define `compute()`. `result` is normally `null`: what is useful about invoke here is **waiting for the action to complete**, not receiving a result object.

This can be replaced with:

```java
pool.execute(task);
// Do other work...
task.join(); // Wait for the action if completion confirmation is needed.
```

or:

```java
ForkJoinTask<Void> handle = pool.submit(task);
handle.get(); // Wait and handle exceptions per Future.
```

All these snippets assume the task exists and checked exceptions are declared/handled appropriately. If the goal is to transform an array across independent regions, `RecursiveAction` is convenient when the data has been partitioned into clear write regions and the caller only needs to know when the task tree has finished. If an aggregated value needs to be computed, `RecursiveTask<V>` usually expresses the result more directly.

Do not confuse `void` from **`pool.execute`** (a call that returns no handle) with **`Void`** of `RecursiveAction` (the result type of a task, which can yield `null` upon completion).

## 11. Difference between pool.invoke() and ExecutorService.invokeAll()

`ForkJoinPool` implements `ExecutorService`, so it also has the APIs of this interface. **`invokeAll(Collection<? extends Callable<T>> tasks)`** is not a simple "plural" variant of `pool.invoke(ForkJoinTask<T>)`.

- `pool.invoke(root)`: takes **a single root `ForkJoinTask<T>`**, waits for the root to complete, and returns **`T`**.
- `executor.invokeAll(callables)`: takes **a collection of Callables**, waits for all Futures to reach a completed state per contract, and returns a **list of `Future<T>`** in the order of the input collection. You must call get on each Future to retrieve its result or error.
- `invokeAll(callables, timeout, unit)`: sets a single deadline for the group per API; may cancel incomplete tasks when the deadline expires per contract.

Simplified signature example:

```java
T result = pool.invoke(rootTask);

List<Future<T>> handles = pool.invokeAll(tasks);
```

This is a snippet requiring appropriate variables/generic imports; `tasks` is a collection of Callables, not two typical child ForkJoinTasks. Inside `RecursiveTask.compute()`, there is also **`ForkJoinTask.invokeAll(left, right)`** to coordinate **child ForkJoinTasks**. Three APIs share the word `invoke` in their names, yet differ in receiver and contract.

## 12. Memory visibility: when can the result be used?

According to Java concurrency memory consistency guarantees, actions prior to submitting a task to an executor **happen-before** actions inside the task; actions performed during the asynchronous computation **happen-before** actions in another thread after retrieving the result via the corresponding `Future.get()`.

The completion primitives of `ForkJoinTask` (`join()`, `invoke()`) provide coordination mechanisms for the caller or parent to use the completed results of children per the Fork/Join contract.

Consequently:

- After `pool.invoke(root)` succeeds, the caller can safely use the return value of the root.
- After `pool.submit(task)` followed by a successful `handle.get()`, the caller has a completion point and result publication per the Future contract.
- After `pool.execute(task)` returns, there is **not yet** a confirmation point that the task has finished. If you need to read state updated by the task, you must wait for `task.join()`/`get()` or use another synchronization mechanism.
- `isDone()` is a task-status observation, not a substitute for handling results, errors, and any improperly synchronized shared state.

Completion synchronization **does not** make every shared mutable object thread-safe. If multiple ForkJoinTasks concurrently modify an `ArrayList`, a plain counter, or the same array index, data races can still occur. Avoid sharing mutable accumulators; prefer local results via `RecursiveTask` or clear data partitioning in `RecursiveAction`.

## 13. Timeout, cancellation, and actual completion

No single method solves all lifecycle issues:

- `pool.invoke(task)` can block for a long time if the task does not complete; it has no timeout parameter.
- `pool.execute(task)` returns immediately, but **the task can still run for a very long time**; not waiting does not mean the task needs no owner.
- `pool.submit(task)` returns a handle; use `handle.get(timeout, unit)` for a bounded wait on the caller.
- When `get(timeout)` throws `TimeoutException`, **the task is not automatically cancelled**.
- With `ForkJoinTask.cancel(true)`, the `mayInterruptIfRunning` parameter **has no effect in the default ForkJoinTask implementation**: interrupts are not used to control cancellation the way many expect from `FutureTask`. A running task may continue executing.
- `isDone()` or `isCancelled()` does not by itself prove that external side effects were rolled back or resource cleanup has completed.
- Tasks performing blocking I/O or not checking cancellation requests need their own handling protocol, timeouts directly on the I/O API, and an appropriate cleanup policy.

**Do not confuse `ForkJoinTask.cancel(true)` with `FutureTask.cancel(true)` used in some other executors.** They share the Future interface, but the ability to interrupt a specific worker belongs to the implementation contract. If a task must stop at a deadline, you need to design cooperative cancellation inside the work itself, rather than relying solely on the handle's cancelled flag.

## 14. Shutdown, common pool, and ownership

When creating `new ForkJoinPool(parallelism)`, the application owns a dedicated pool and should manage its lifecycle:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    // invoke / execute / submit tasks...
} finally {
    pool.shutdown();
}
```

This is an illustrative snippet. `shutdown()` stops accepting new tasks, but does not prove all tasks have finished. If confirmation is needed, call `awaitTermination(timeout, unit)` at the appropriate place and check the boolean return value. For tasks already submitted but not awaited, normal shutdown still lets accepted tasks complete per contract; however, the caller should not treat "having called shutdown" as the successful result of each task.

`ForkJoinPool.commonPool()` is the shared pool in the JVM. Do not arbitrarily shut it down as a resource owned by a single method: `shutdown()` on the common pool does not have the same termination effect as on a dedicated pool. If you need isolation, dedicated parallelism, and a separate lifecycle, create/retain a dedicated pool scoped to the component's lifecycle—**do not create a new pool for each branch**.

For library code, pool selection should be consistent: submit the root to a specific pool, and child forks follow the execution context within that pool. Do not arbitrarily mix a task that has already run with another submit call; a `ForkJoinTask` is normally designed for one-time execution—**do not reuse a completed instance as a new task** without a clearly understood and controlled reset mechanism.

## 15. When to use which method?

| Caller's need | Choice | Reason |
|---|---|---|
| Need sum/min/max before the next step, and the caller is allowed to wait. | `pool.invoke(root)`. | Returns the value directly after the root completes. |
| Submit work and continue other processing, but need the result later. | `pool.submit(root)`. | Returns a tracking handle; retrieve the result when needed. |
| Want to wait for the result with a deadline. | `pool.submit(root)` + `get(timeout)`. | Bounds the caller's wait time. |
| Fire-and-dispatch and the application already has its own completion/error tracking channel. | `pool.execute(task)`. | Does not wait and returns no new handle; clean API. |
| Already have a `ForkJoinTask`, still want to submit without waiting and wait later. | `pool.execute(task)` then `task.join()`. | The handle is the retained task itself. |
| Have many independent Callables and need to wait for the whole group. | `ExecutorService.invokeAll(...)`. | Returns a list of Futures; distinct from a root ForkJoinTask. |
| Inside `compute()`, split two branches and combine results. | `left.fork(); right.compute(); left.join();`. | Coordinates child tasks; does not resubmit root to the pool. |

No option is "always fastest." In terms of computation, all three calls can lead to the exact same work being executed; the prominent difference lies in **caller control and completion observation**.

## 16. Common mistakes when using invoke/execute/submit

| Mistake | Consequence | Correct approach |
|---|---|---|
| Using `pool.invoke(root)` on a path that must not block. | Caller waits until root finishes, potentially increasing latency. | Submit and handle the result asynchronously or with a deadline. |
| Thinking `execute()` means the task is finished when the call returns. | Reading data still being updated; incomplete results. | Wait for `task.join()/get()` or a completion signal. |
| Using `submit()` and discarding the handle of a task that must succeed. | Task errors may go unobserved by the caller. | Keep the Future and provide an error/completion handling path. |
| Using `task.join()` like `Thread.join()`. | Misunderstanding the wait target and exception contract. | Distinguish task completion from thread termination. |
| Calling `task.invoke()` outside a pool and thinking it runs on a dedicated pool. | No guarantee the task runs on the intended pool. | Call `pool.invoke(root)` / `pool.submit(root)` on the specific pool. |
| Forking a child and immediately joining before doing the other branch. | Limits parallelism opportunities. | Fork one branch, compute the other yourself, then join. |
| Catching `ExecutionException` around `join()` without understanding the signature. | Wrong handling/compilation error or missed unchecked errors. | `get()` has checked exceptions; `join()` has an unchecked path. |
| Assuming `get` timeout automatically cancels the task. | Worker keeps running after caller times out. | Handle cancellation/lifecycle explicitly. |
| Assuming `ForkJoinTask.cancel(true)` guarantees worker interruption. | Worker may continue, causing unintended side effects. | Cooperative cancellation per the actual contract. |
| Sharing a single mutable accumulator across RecursiveTasks. | Data races and lost results. | Return local results or partition writes into disjoint regions. |
| Creating a `new ForkJoinPool()` inside every child compute. | Pool/thread explosion, high overhead. | Use the same pool and fork children. |
| Using Fork/Join mostly for blocking I/O. | Workers get blocked, reducing throughput or causing deadlock. | Consider an I/O-appropriate executor, timeouts, and managed blocking when suitable. |
| Forgetting to shut down a dedicated pool. | Pool resources are not properly managed. | Owner shuts down and awaits termination with a bound. |
| Treating `isDone()` as proof that the task succeeded. | Done includes failed/cancelled. | Retrieve the result or check error/cancellation status. |

## 17. Operations: CPU-bound, blocking, and work-stealing

ForkJoinPool is optimized for **branching CPU-bound** work, especially when some workers can steal pending tasks from other workers. Summing, tree recursion, and sensible array splitting are usually good fits if leaves are large enough.

Choosing invoke/execute/submit **does not change the nature of the problem**: if tasks are too small or perform blocking I/O, all three submission methods can perform poorly. Long blocking calls such as sockets, databases, or `CountDownLatch.await()` inside a worker reduce the ability to process other tasks. The framework provides `ForkJoinPool.managedBlock(ManagedBlocker)` for some cases where the pool needs to be notified of blocking, but this API **does not turn I/O into non-blocking and does not automatically prevent deadlocks**.

For long-running computations, you can consider `parallelStream()` or higher-level APIs when appropriate, while still paying attention to shared mutable state and resource management. For tasks with a deadline schedule, `get`'s timeout only bounds the caller; the worker must also have a policy for checking deadlines and cooperative cancellation.

## 18. Pre-project checklist

1. **Is the caller allowed to block?** If not, do not call `pool.invoke()` on a latency-sensitive thread.
2. **Is a return value needed?** If yes and needed immediately, invoke; if needed later, submit and keep the handle.
3. **Do errors/cancellations need to be observed?** Always keep a handle or an appropriate completion channel, even when using execute.
4. **Is there a deadline?** Use `get(timeout)` and design worker cancellation/cleanup as well.
5. **Is the task truly divide-and-conquer?** Design a threshold and base case; avoid forking tasks that are too small.
6. **Are branches independent?** Return local results, keep data immutable, or write to separate regions.
7. **Are children joined in the right place?** The parent must wait for every child on which its result depends.
8. **Where are task errors propagated?** Understand `join()`'s unchecked path and `get()`'s checked path.
9. **Which pool owns the task?** Use the chosen pool explicitly; do not confuse direct `task.invoke()` with `pool.invoke(task)`.
10. **Is there blocking I/O?** Re-evaluate ForkJoinPool; consider another executor and explicit timeout APIs.
11. **Lifecycle management?** Dedicated pools must be shut down by their owner and awaited when appropriate.
12. **Testing without relying on sleep:** use latches to orchestrate execution order and verify results and completion deterministically.

## 19. Self-check questions

1. **Does `pool.invoke(root)` return immediately after putting the task in the queue?** No. It waits for the root to complete and then returns the result or throws an error.
2. **What type does `pool.execute(task)` return?** `void`; it does not return a new handle to the caller.
3. **What type does `pool.submit(task)` return when task is a ForkJoinTask?** `ForkJoinTask<V>` (which is also a Future).
4. **If you use execute and already have a task reference, how do you wait?** `task.join()` or `task.get()` per contract.
5. **Does `submit()` block until the task completes?** No; it submits the task and returns a handle.
6. **Does `join()` declare `InterruptedException` like `get()`?** No; their exception contracts differ.
7. **Why is `get(timeout)` not enough to cancel a long-running task?** The timeout only ends the caller's wait.
8. **Does `ForkJoinTask.cancel(true)` guarantee interrupting the worker?** No; the default implementation does not use interrupts to control cancellation.
9. **Are `pool.invoke(root)` and `root.invoke()` always the same?** No; calling it on the root cannot be treated as selecting a dedicated pool.
10. **What does `ExecutorService.invokeAll(callables)` return?** A list of Futures for the Callables, not a single root result V.
11. **After `pool.execute(root)`, can you read data being modified by root as if it were complete?** No; a completion/synchronization point is required.
12. **Why fork one branch, compute the other yourself, and then join?** Increases opportunities for useful parallel work and avoids waiting too early.
13. **Why does `submit` not guarantee the task runs on a separate thread immediately?** The pool decides worker/scheduling based on state and work-stealing.
14. **When should you use RecursiveTask instead of RecursiveAction?** When branches must return values to be combined, rather than only performing side effects on disjoint regions.
15. **For a dedicated pool, is calling `shutdown()` enough to prove all tasks have finished?** No; you must manage completion/`awaitTermination` and check results.

**Remember:** **`invoke` = submit and wait for the result; `execute` = submit without waiting, no handle returned; `submit` = submit without waiting, but returns a handle.** Within a Fork/Join tree, use `fork()`/`join()` to coordinate child branches; at the application boundary, choose how to submit the root based on your needs for waiting, retrieving results, handling errors, and timeouts.
