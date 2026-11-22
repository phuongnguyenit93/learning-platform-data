# FutureTask in Java: a Runnable that can be tracked with Future

## 1. The problem to solve

Suppose you have a `Runnable` describing background work. You can pass it to a `Thread` or `Executor.execute()`, but a plain `Runnable` has no built-in API to ask **"is it done yet?"**, wait for completion, retrieve execution errors, or request cancellation. Meanwhile, `Future<V>` represents **the result and state of an asynchronous computation**, but the `Future` interface itself is not required to be a task that can be passed directly into a `Thread`.

`java.util.concurrent.FutureTask<V>` bridges those two needs:

~~~text
                 Runnable                 Future<V>
                    |                         |
              void run()                get(), cancel(),
                    |                   isDone(), isCancelled()
                    |                         |
                    +---------+---------------+
                              |
                      RunnableFuture<V>
                              |
                         FutureTask<V>
                              |
                Can be passed to Thread,
                Executor.execute(), or run()
                while still keeping a Future<V> handle.
~~~

This lesson belongs to the **Future & Scheduling** section in **Java Advance - concurrency**. The scope focuses on standard **Java SE 17+** mechanisms, without Spring-specific content since Spring has its own chapter.

After this lesson, you can:
- Explain that `FutureTask<V>` implements `RunnableFuture<V>`, having both `run()` and `get()/cancel()/isDone()`.
- Create a FutureTask from a **`Callable<V>`** or from a **`Runnable` + result value `V`**.
- Run the same FutureTask object via `new Thread(task).start()` or `executor.execute(task)`, and keep **that exact object** as the Future handle.
- Distinguish the return value of `FutureTask(Runnable, result)` from the return value of `Callable<V>.call()`.
- Understand that `FutureTask` is a **one-shot computation**: multiple calls to `run()` do not make the task re-run from the beginning.
- Correctly interpret `isDone`, `isCancelled`, `get`, `get(timeout)`, `ExecutionException`, and `CancellationException`.
- Understand that `cancel(true)` only requests an interrupt, and does not forcibly stop the worker or roll back side effects.
- Avoid ownership bugs, wrapping a FutureTask twice via `submit`, waiting on `get` indefinitely, and races between cancellation and completion.
- Know what roles `done()` and `runAndReset()` serve as extension points and why FutureTask **is not a scheduler itself**.

## 2. Mastering the four related interfaces/classes

### 2.1. Runnable — describing an action

~~~java
Runnable work = () -> {
    System.out.println("processing");
};
~~~

`Runnable.run()` returns `void`. A `Runnable` typically only describes code to execute; it has no `get()`, defines no return value, and provides no completion state for the caller to track. If passed directly to a `Thread`, you can wait with `Thread.join()`, but `join` does not return a result by itself, does not wrap exceptions from `run` into `ExecutionException`, and is not a Future API.

**`Runnable` is not required to run on another thread.** Calling `work.run()` is a normal method call on **the current thread**. Only when using `new Thread(work).start()` or an appropriate executor is execution scheduled in another execution context.

### 2.2. Callable<V> — describing a computation that returns a result

~~~java
Callable<Integer> calculation = () -> 6 * 7;
~~~

`Callable<V>.call()` returns a value of type `V` and may declare `throws Exception`. However, `Callable` **does not implement `Runnable` itself**, so it cannot be passed directly as a `Runnable` to the `Thread(Runnable)` constructor.

FutureTask can accept a `Callable<V>` and create a task that is both runnable and observable:

~~~java
FutureTask<Integer> task = new FutureTask<>(calculation);
new Thread(task).start();
Integer result = task.get();
~~~

The three lines above are an illustrative snippet inside a method with appropriate imports and handling/declaration of `InterruptedException` and `ExecutionException`.

### 2.3. Future<V> — the contract for observing results

| Method | Purpose |
| --- | --- |
| `V get()` | Waits for and retrieves the result; may be interrupted or receive the computation's error |
| `V get(timeout, unit)` | Waits with a timeout; may throw `TimeoutException` |
| `boolean cancel(mayInterruptIfRunning)` | Requests cancellation of the result/computation |
| `boolean isDone()` | Has it completed, failed, or been cancelled? |
| `boolean isCancelled()` | Has the Future transitioned to the cancelled state? |

A Future **is not necessarily** a Runnable. You cannot assume that every implementation of Future gives you `run()` to pass directly into a Thread.

### 2.4. RunnableFuture<V> and FutureTask<V>

`RunnableFuture<V>` extends **both `Runnable` and `Future<V>`**. `FutureTask<V>` is the common concrete implementation of this interface.

~~~java
public class FutureTask<V> implements RunnableFuture<V>
~~~

The line above illustrates the meaning of the type declaration, not a redefinition of the JDK class. When you have:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
~~~

then **the same `task` object** simultaneously:
- Can be run via `task.run()`, `new Thread(task).start()`, or `executor.execute(task)`.
- Can be tracked via `task.isDone()`.
- Can retrieve the result via `task.get()`.
- Can request cancellation via `task.cancel(true)`.

This is the main difference between a regular Runnable and a FutureTask.

## 3. Two important constructors

| Constructor | Input | `get()` value on success | When to use |
| --- | --- | --- | --- |
| `FutureTask(Callable<V> callable)` | A computation returning `V` | Value returned by `call()` | Computing an actual result |
| `FutureTask(Runnable runnable, V result)` | A `void` action and a pre-supplied `result` value | The `result` value passed at construction | Needing to track completion of an existing Runnable |

### 3.1. When using Callable

~~~java
Callable<String> call = () -> "READY";
FutureTask<String> task = new FutureTask<>(call);
~~~

After the task executes successfully, `get()` returns `"READY"`. If `call()` throws an exception, `get()` throws an `ExecutionException` containing the underlying error.

### 3.2. When using Runnable + result

~~~java
Runnable action = () -> saveLocalState();
FutureTask<String> task = new FutureTask<>(action, "SAVED");
~~~

This is a snippet assuming `saveLocalState()` already exists. When `action.run()` **completes normally**, `task.get()` returns the exact `"SAVED"` value **provided upfront** by the caller. `Runnable` does not generate this string itself.

If `run()` throws an unchecked exception, FutureTask records the failure and `get()` throws `ExecutionException`, **not returning `"SAVED"`**. If the task is cancelled, `get()` throws `CancellationException`, regardless of the `result` passed to the constructor.

**You can pass `null` as the result** when you only need to know whether the task succeeded or failed:

~~~java
FutureTask<Void> task = new FutureTask<>(runnable, null);
~~~

After normal completion, `get()` returns `null`. To distinguish "task succeeded and returned null" from "not yet run", **do not rely on the null value**; use the Future's state and how `get()` terminates.

## 4. Standalone Java 17 example: a Runnable attached to a Future

Create the file **`RunnableFutureTaskDemo.java`**:

~~~java
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableFutureTaskDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger operations = new AtomicInteger();

        Runnable runnable = () -> operations.incrementAndGet();
        FutureTask<String> tracked =
                new FutureTask<>(runnable, "COMPLETED");

        System.out.println("doneBeforeStart=" + tracked.isDone());

        Thread worker = new Thread(tracked, "tracked-worker");
        worker.start();

        String result = tracked.get();
        worker.join();

        System.out.println("result=" + result);
        System.out.println("operations=" + operations.get());
        System.out.println("doneAfterGet=" + tracked.isDone());
        System.out.println("cancelled=" + tracked.isCancelled());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac RunnableFutureTaskDemo.java
java RunnableFutureTaskDemo
~~~

Stdout:

~~~text
doneBeforeStart=false
result=COMPLETED
operations=1
doneAfterGet=true
cancelled=false
~~~

**Explanation:**
1. `AtomicInteger operations` starts at 0. `Runnable` increments this variable exactly once when run.
2. The `FutureTask<>(runnable, "COMPLETED")` constructor uses the string as **the fixed result if the task succeeds**.
3. Before calling `Thread.start()`, `isDone()==false`: creating a FutureTask object **does not execute** the task by itself.
4. `worker.start()` runs the FutureTask on a thread. `tracked.get()` waits for the computation and returns `"COMPLETED"`.
5. `worker.join()` waits for the worker to exit `run`; `main` then reads `operations`. Do not assume the ordering between `get` and the thread actually finishing its entire lifecycle, so use `join` when you need to know the thread has exited.
6. `isDone()==true` and `isCancelled()==false` when the task completes normally.

**Note on output:** the example does not print thread names or timing because the scheduler decides when the worker gets CPU time. The printed values are deterministic when there is no unexpected interruption or error.

**Note on runnable:** `() -> operations.incrementAndGet()` is valid for a functional interface returning `void` because a method invocation can be used as a statement expression; the numeric result of `incrementAndGet()` is discarded on the `Runnable` side. FutureTask returns the `"COMPLETED"` string supplied to the constructor.

## 5. Java 17 example: Callable and an actually computed value

Create the file **`CallableFutureTaskDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class CallableFutureTaskDemo {
    public static void main(String[] args) throws Exception {
        Callable<Integer> calculation = () -> 6 * 7;
        FutureTask<Integer> task = new FutureTask<>(calculation);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.execute(task);

            System.out.println("value=" + task.get());
            System.out.println("valueAgain=" + task.get());
            System.out.println("isDone=" + task.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac CallableFutureTaskDemo.java
java CallableFutureTaskDemo
~~~

Stdout:

~~~text
value=42
valueAgain=42
isDone=true
~~~

Calling `get()` twice **does not make the Callable run twice**. `FutureTask` records the result of a single execution; subsequent `get()` calls after completion read back the published result. For a computation that has already finished, `get()` does not re-run the computation.

### Why use execute(task), without needing submit(task)?

`ExecutorService.execute(Runnable)` takes a Runnable and returns `void`. Because `FutureTask` is already **a Runnable** and **a Future**, you can do:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
pool.execute(task);
Integer value = task.get();
~~~

This snippet assumes `pool`, imports, and appropriate exception handling. You still hold the `task` handle even though `execute` does not return a Future.

Do not accidentally write:

~~~java
FutureTask<Integer> inner = new FutureTask<>(() -> 42);
Future<?> outer = pool.submit(inner);
~~~

Because `submit(Runnable)` typically **creates another Future wrapping the passed-in Runnable**, there are now two handles: `inner` created by you, and `outer` returned by the executor. `outer.get()` via the Runnable overload may return `null`, whereas `inner.get()` returns 42. Cancelling `outer` does not provide an abstract guarantee that `inner` has transitioned to the cancelled state or that all side effects inside have stopped. This pattern makes ownership and cancellation hard to reason about.

**Choose one of two clear approaches:**
- If you want the executor to manage the Future: `Future<Integer> f = pool.submit(() -> 42);`.
- If you want to **own a FutureTask yourself** and customize its state/hooks: create `FutureTask<Integer> task`, then `pool.execute(task)`, and use `task.get()/cancel()` directly.

There is no need to wrap a FutureTask inside another FutureTask just to get a Future.

## 6. FutureTask is one-shot: calling run() multiple times does not re-run the task

An important question: FutureTask has `run()`, so does calling `run()` a second time recompute it?

**No.** With regular `FutureTask.run()`, only one execution of the computation is accepted. Once the task has completed, subsequent calls to `run()` do not re-run the `Callable`/`Runnable`.

Create the file **`FutureTaskOneShotDemo.java`**:

~~~java
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureTaskOneShotDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger calls = new AtomicInteger();

        FutureTask<Integer> task = new FutureTask<>(() -> {
            return calls.incrementAndGet();
        });

        task.run(); // Executes synchronously on main.
        task.run(); // Does not execute again.
        task.run(); // Still does not execute again.

        System.out.println("result=" + task.get());
        System.out.println("calls=" + calls.get());
        System.out.println("done=" + task.isDone());
    }
}
~~~

Compile/run:

~~~bash
javac FutureTaskOneShotDemo.java
java FutureTaskOneShotDemo
~~~

Stdout:

~~~text
result=1
calls=1
done=true
~~~

**Two misconceptions to avoid:**
1. `task.run()` does not create a new thread. In this example the task runs **on the main thread** and finishes before the next line executes.
2. `FutureTask` is not a recurring schedule. If you need to perform a computation repeatedly such as `every 1s`, use `ScheduledExecutorService`/`ScheduledFuture` or create **a new FutureTask each time**, instead of re-calling `run()` on an already completed FutureTask.

If multiple threads call `run()` concurrently on an **incomplete** FutureTask, FutureTask's coordination mechanism allows only one runner to execute the body for that computation. Do not use multiple `run()` calls as a way to "speed up with multiple workers": the other callers will not get a separate computation.

### Comparison with a regular Runnable

~~~java
Runnable work = () -> System.out.println("run");
work.run();
work.run(); // Prints twice because Runnable does not prevent re-execution on its own.
~~~

The snippet above running in `main` will print two `run` lines. `Runnable` is a contract describing a body of work; `FutureTask` is a **computation with completion state** and result storage, so its semantics are different.

## 7. FutureTask states and get() outcomes

The following table describes the scenarios observed by a caller:

| Event | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Not yet run / currently running | `false` (while there is no terminal outcome) | `false` | Waits |
| Completed normally | `true` | `false` | Returns value `V` |
| Callable/Runnable threw an exception | `true` | `false` | Throws `ExecutionException` |
| Cancelled successfully | `true` | `true` | Throws `CancellationException` |

**Do not use `isDone()` to conclude success.** It is also `true` when the task fails or is cancelled. If you want to know whether the task succeeded and retrieve the data, typically call `get()` and handle exceptions.

`isCancelled()==false` also **does not** mean the task definitely succeeded; the task may not have run yet, may still be running, or may have ended with an exception.

### get() and memory visibility

Under the memory consistency contract of `Future`, actions taken by the asynchronous computation **happen-before** actions following the corresponding `Future.get()` in another thread. This ensures the caller sees data published by the computation after `get()` completes per the contract.

Even so:
- Do not treat `get()` as a transaction protecting **every shared mutable object** that other threads continue to modify.
- If the task returns an `ArrayList` and another thread still mutates the list, additional ownership/synchronization is needed.
- `Future.get()` does not automatically make multi-step database operations atomic.
- If you only have `isDone()`, do not substitute it for the memory consistency reasoning of `get()` without reading the specific contract.

### Things you cannot infer from FutureTask

- `isDone()==true` after `cancel(true)` **does not prove** the Callable has actually exited its stack or finished cleanup.
- `get(timeout)` throwing `TimeoutException` **does not automatically cancel** the FutureTask.
- `cancel(true)` does not forcibly stop all I/O or CPU code.
- Normal completion does not mean an external remote transaction was definitely committed if the Callable does not report the full business state.

## 8. Java 17 example: timeout and execution exception

When you need to bound the wait time, `get(timeout, unit)` may throw `TimeoutException`. For an error inside Callable, `get()` throws `ExecutionException` and `getCause()` reveals the original error.

Create the file **`FutureTaskOutcomeDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTaskOutcomeDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        FutureTask<Integer> slow = new FutureTask<>(() -> {
            entered.countDown();
            release.await();
            return 7;
        });

        Thread worker = new Thread(slow, "slow-worker");
        worker.start();
        entered.await();

        try {
            slow.get(20, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            System.out.println("timedGet=TimeoutException");
        }

        System.out.println("stillNotCancelled=" + !slow.isCancelled());
        release.countDown();

        System.out.println("resultAfterRelease=" + slow.get());
        worker.join();

        FutureTask<String> failed = new FutureTask<>(() -> {
            throw new IllegalArgumentException("bad input");
        });
        failed.run(); // Runs on main, FutureTask retains the exception.

        try {
            failed.get();
        } catch (ExecutionException e) {
            System.out.println("failureCause="
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("failedIsDone=" + failed.isDone());
        System.out.println("failedIsCancelled=" + failed.isCancelled());
    }
}
~~~

Run:

~~~bash
javac FutureTaskOutcomeDemo.java
java FutureTaskOutcomeDemo
~~~

Stdout when there is no unexpected interruption:

~~~text
timedGet=TimeoutException
stillNotCancelled=true
resultAfterRelease=7
failureCause=IllegalArgumentException
failedIsDone=true
failedIsCancelled=false
~~~

**Why is the output deterministic?**
- `slow` signals it has entered the Callable and then waits on `release.await()`. Because `main` has not counted down the latch yet, the timed `get(20ms)` cannot retrieve the result and throws `TimeoutException`.
- `get(timeout)` **does not call `cancel`**, so `slow.isCancelled()` remains `false`.
- When `main` releases `release`, the Callable returns 7; `slow.get()` then receives 7.
- The `failed` FutureTask executes a `Callable` that throws `IllegalArgumentException`, but FutureTask's `run()` **records the error** rather than throwing the raw exception up to `main` as calling Callable directly would.
- The error is observed via `failed.get()` as an `ExecutionException`; `getCause()` is `IllegalArgumentException`.
- `failed.isDone()==true` because it terminated with an error, while `isCancelled()==false` because no cancel request was accepted.

**Do not use a timeout as proof that a task has no side effects**: if the caller retries immediately after `TimeoutException`, the old task may still be running and performing I/O. Idempotency or a cancellation policy is needed if the business logic is sensitive.

## 9. cancel(false) and cancel(true) on FutureTask

The constructor gives FutureTask a cancellation handle, but cancellation is not an unconditional kill.

~~~java
boolean accepted = task.cancel(true);
~~~

Meaning:
- When the task has not yet run, a successful cancel prevents the computation from executing later.
- When the task is running, `FutureTask.cancel(true)` attempts to interrupt the runner thread.
- `cancel(false)` can mark the task as cancelled **without interrupting** the runner; running code may continue until it finishes on its own.
- When the task has already completed normally or failed, the terminal state cannot be "reversed" by cancel.
- When cancellation succeeds, `isCancelled()==true` and `get()` throws `CancellationException`.
- **`isDone()==true` when cancelled does not mean the worker has exited the Callable**.

### Interruption is cooperative

`Thread.interrupt()` sets the interrupt flag. APIs such as `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()`, and `CountDownLatch.await()` can throw `InterruptedException`; a self-contained CPU loop that does not check the flag may continue. Depending on the I/O, interrupting may not cause an operation to return immediately.

If you catch `InterruptedException` at a layer that cannot propagate it further, you typically restore the status with `Thread.currentThread().interrupt()` **and exit or transition state according to the cancellation policy**. Merely restoring the flag and unconditionally continuing business logic renders cancellation ineffective.

### A cancelled FutureTask can still run code

If the Callable ignores interrupts or is in cleanup, it may still do work after the Future is already cancelled. FutureTask does not automatically roll back files, databases, or HTTP requests that were already executed. For side effects, the application needs to design timeouts at the appropriate APIs, idempotency, and commit/compensation mechanisms.

## 10. Java 17 example: requesting cancellation and observing the worker actually exit

Create the file **`FutureTaskCancelDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;

public class FutureTaskCancelDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        FutureTask<String> task = new FutureTask<>(() -> {
            started.countDown();
            try {
                Thread.sleep(60_000);
                return "normal-result";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return "stopped-by-interrupt";
            } finally {
                exited.countDown();
            }
        });

        Thread worker = new Thread(task, "cancel-worker");
        worker.start();
        started.await();

        boolean accepted = task.cancel(true);
        exited.await();
        worker.join();

        System.out.println("cancelAccepted=" + accepted);
        System.out.println("cancelled=" + task.isCancelled());
        System.out.println("done=" + task.isDone());
        System.out.println("workerExited=" + (exited.getCount() == 0));

        try {
            task.get();
        } catch (CancellationException e) {
            System.out.println("get=CancellationException");
        }
    }
}
~~~

Run:

~~~bash
javac FutureTaskCancelDemo.java
java FutureTaskCancelDemo
~~~

Stdout on a normal run:

~~~text
cancelAccepted=true
cancelled=true
done=true
workerExited=true
get=CancellationException
~~~

**Explanation:**
1. `started.await()` ensures the Callable body has started; it cannot complete normally before `cancel` because it is progressing toward or waiting in `sleep(60_000)`.
2. `task.cancel(true)` accepts the cancellation and attempts to interrupt the runner. If the interrupt arrives **before** the `sleep` call, `sleep` also observes the interrupt status and throws an exception; if it arrives during sleep, it wakes up with an exception.
3. `finally` counts down the `exited` latch, and `main` uses `worker.join()` to know the worker has truly finished.
4. The outcome state of the FutureTask remains **cancelled**, so `get()` throws `CancellationException`, **not** returning the `"stopped-by-interrupt"` string that the Callable produced in the catch block.

**Limitation:** the demo waits on the latch indefinitely to illustrate the difference between Future cancelled and worker exited. With real tasks that might be uncooperative, **set a deadline** when waiting for cleanup and define a monitoring policy if the worker fails to exit.

### Cancelling before the task is scheduled

~~~java
FutureTask<String> task = new FutureTask<>(() -> "NEVER");
boolean accepted = task.cancel(false);
task.run(); // Does not execute Callable because the task is already cancelled.
~~~

This is a snippet. For a new FutureTask, a successful cancel before `run()` prevents the body from running; `get()` will throw `CancellationException`. Even though we call `run()` afterward, FutureTask is one-shot with a terminal state.

## 11. Using FutureTask properly with ExecutorService

### 11.1. Running directly with execute

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);

FutureTask<Integer> task = new FutureTask<>(() -> expensiveCompute());
pool.execute(task);

try {
    Integer answer = task.get();
    use(answer);
} finally {
    pool.shutdown();
}
~~~

This is a snippet assuming `expensiveCompute()` and `use(...)` exist and classes are imported. In production, you need exception/cancel handling, shutdown timeouts, and ownership. The key point: `execute(task)` accepts the FutureTask directly as a **Runnable**, while `get()` is called on the same FutureTask held by the caller.

### 11.2. When you do not need to create a FutureTask yourself

~~~java
Future<Integer> answer = pool.submit(() -> expensiveCompute());
Integer result = answer.get();
~~~

`ExecutorService.submit(Callable)` **already returns a Future**, so most applications do not need to construct a `FutureTask` manually. Creating a FutureTask yourself is useful when:
- You must use an API that only accepts `Runnable` but still need a Future handle.
- You need to pass **the same object** through an `execute` API and manage completion elsewhere.
- You want to subclass FutureTask to hook into `done()` or integrate with a custom queue/scheduler.
- You want to test/reason explicitly about the `run/get/cancel` lifecycle.

**Do not wrap a FutureTask via `submit(Runnable)` just out of habit of using `submit`**. That creates an extra Future and unnecessary cancellation/lifecycle layers.

### 11.3. The executor can reject tasks

`execute(task)` can throw `RejectedExecutionException`, for instance when the executor has already shut down or the pool's rejection policy triggers. If your `FutureTask` **has not been run or cancelled**, calling `task.get()` after a rejected submission can **wait forever**, because no worker will ever complete it.

Handling pattern:

~~~java
FutureTask<Integer> task = new FutureTask<>(() -> 42);
try {
    pool.execute(task);
} catch (RejectedExecutionException e) {
    task.cancel(false);
    throw e;
}
~~~

The snippet assumes `pool` and imports exist. `task.cancel(false)` in this branch ensures callers holding the handle are not stuck on an unscheduled Future. However, **do not do this automatically if the rejection handler already executed the task via a caller-runs policy or another party owns the task**; you must know the contract of the actual executor/rejection policy. A rejected `execute` alone does not prove the body never ran in every custom executor.

### 11.4. Sharing one FutureTask with two executors?

Submitting **the same FutureTask** to two places does not create two independent computations. Its one-shot nature can cause one side to do nothing; ordering is affected by the scheduler, and ownership/cancellation becomes tangled. If you want two independent runs, create **two separate FutureTasks** (or two `Callable` submissions).

### 11.5. Need results in completion order?

`FutureTask.get()` waits for **one specific Future**. If you have multiple FutureTasks, calling `get()` sequentially in submission order can cause **head-of-line blocking**: a slow first task delays processing results of later tasks that have already finished.

When you need results in **completion order**, consider `ExecutorCompletionService<V>` instead of manually polling `isDone()` across thousands of FutureTasks. `ExecutorCompletionService` combines task submission with a completion queue, though it does not change the general requirement that the caller must manage errors, timeouts, and cancellation of remaining tasks.

## 12. FutureTask.done(): hook on transition to a terminal state

`FutureTask` provides the protected method `done()` for subclasses to override. It is invoked when the FutureTask transitions to a completed state (normal, exception, or cancellation). This hook enables performing a very brief action when completion occurs.

### Java 17 example: subclassing and counting callbacks

Create the file **`FutureTaskDoneHookDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureTaskDoneHookDemo {
    static final class TrackedTask<V> extends FutureTask<V> {
        private final AtomicInteger hookCalls = new AtomicInteger();

        TrackedTask(Callable<V> callable) {
            super(callable);
        }

        @Override
        protected void done() {
            hookCalls.incrementAndGet();
        }

        int hookCalls() {
            return hookCalls.get();
        }
    }

    public static void main(String[] args) throws Exception {
        TrackedTask<String> task =
                new TrackedTask<>(() -> "OK");

        task.run();
        task.run(); // Does not complete a second time.

        System.out.println("result=" + task.get());
        System.out.println("hookCalls=" + task.hookCalls());
        System.out.println("cancelled=" + task.isCancelled());
    }
}
~~~

Run:

~~~bash
javac FutureTaskDoneHookDemo.java
java FutureTaskDoneHookDemo
~~~

Stdout:

~~~text
result=OK
hookCalls=1
cancelled=false
~~~

**Key points:**
- `done()` is **not** a callback for every `run()` invocation; FutureTask has only one completion of the computation.
- When `run()` executes synchronously on `main`, the hook also runs in that corresponding flow. If cancellation wins, `done()` may run on **the thread calling `cancel`**, not necessarily the worker.
- **Do not assume `done()` means the worker has actually exited upon cancellation.** The Future can transition to cancelled and invoke the hook while the callable has not yet left the stack.
- Avoid long I/O, blocking `get()`, or hard-to-control locks directly inside `done()`. A blocking hook can prolong the completion/cancellation path and cause contention or deadlock.
- Inside the hook, if you need to know the outcome, you must handle normal, exception, and cancelled cases rather than calling `get()` and assuming it always returns a value.
- The timing of waiter notification/wakeup may differ from when the hook is processed; do not rely on the ordering between them to establish invariants not guaranteed by the Javadoc.

### Should done() be used to publish results?

A completion callback can send a signal to another component, but if the result is used to drive transactional decisions, a clear state/commit protocol is required. `done()` can run when the computation fails or is cancelled; relying solely on "the hook was called" is not enough to prove success.

## 13. FutureTask is not a ScheduledFuture

FutureTask sits under **Future & Scheduling**, but `FutureTask` only represents **a computation that can be run and have its state observed**. By itself, it **does not** hold a start timestamp or a repeating interval.

To schedule after a delay or periodically, `ScheduledExecutorService` and `ScheduledFuture` provide the appropriate API:

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> scheduled = scheduler.schedule(
        () -> System.out.println("run once"),
        1, TimeUnit.SECONDS);
~~~

This is a snippet; imports and shutting down the scheduler at the end of its lifecycle are needed. `ScheduledFuture<?>` combines Future capabilities with `Delayed` (remaining time before execution). `scheduleAtFixedRate` and `scheduleWithFixedDelay` have periodic semantics according to their own contracts.

**Do not try to call `futureTask.run()` every second to create a periodic task.** A regular FutureTask is one-shot. `FutureTask` has a protected `runAndReset()` method for extension cases that can execute the body and reset state **without publishing a terminal result** on success, used in custom mechanisms. It is a protected API, not an external command to "reset a done FutureTask".

### Should runAndReset() be used in application code?

Usually **no**. It has narrow semantics and requires subclassing/correct state control:
- Cannot be used to "refresh" a FutureTask that has already completed normally.
- Makes no sense as a replacement for `ScheduledExecutorService` for common periodic jobs.
- If the Callable throws an exception or the task is cancelled, resetting/continuing depends on the contract and state.
- Requires deep understanding of lifecycle, concurrency, and hook overrides; prefer standard abstractions instead of writing your own scheduler with a protected method.

Scheduling and tracking completion are two distinct responsibilities: the executor/scheduler decides **when** a task runs; FutureTask manages **the result and state** of a computation.

## 14. Common mistakes when using FutureTask

1. **Creating a FutureTask and calling `get()` immediately without start/run/execute.** With no worker to complete the task, `get()` can wait forever. You must actually schedule/run it or use a timeout.
2. **Thinking the `FutureTask(Runnable, result)` constructor makes the Runnable return `result`.** Result is a fixed value supplied by the caller; it is only published when the Runnable completes successfully.
3. **Calling `task.run()` and thinking it creates a new thread.** That is just a method call on the current thread, unless invoked by a Thread/executor.
4. **Calling `run()` twice and expecting it to re-run.** FutureTask is one-shot, not a scheduler.
5. **Using `submit(futureTask)` and confusing the outer Future with the FutureTask itself.** Two handles with different return/cancel semantics can appear; prefer `execute(futureTask)`.
6. **Using `isDone()==true` to conclude the task succeeded.** The task may have failed or been cancelled.
7. **Using `isCancelled()==false` to conclude the task has completed.** It may not have started or may still be running.
8. **Calling `get(timeout)` and assuming the task was cancelled on timeout.** Timed get only ends the caller's wait.
9. **Treating `cancel(true)` like a kill command.** The worker may ignore interrupts, be blocked on I/O, or continue cleanup.
10. **Calling `task.get()` inside a callback or critical lock without a timeout or dependency graph.** This can deadlock if the task needs the very lock being held or the executor has too few workers.
11. **Using a single-worker thread pool where task A waits on `taskB.get()` and task B is queued behind A.** B never gets a chance to run: thread-starvation deadlock.
12. **Submitting the same FutureTask to multiple executors to duplicate work.** One-shot prevents two independent results; ownership becomes unclear.
13. **Not handling `ExecutionException`.** Execution errors live in `getCause()`, not necessarily at the `execute` call site.
14. **Not handling `CancellationException`.** This is a valid state of a cancelled task with no result to read.
15. **Forgetting to restore interrupt status when catching `InterruptedException` without propagating it.** Higher-level callers may lose the cancellation signal.
16. **Using `done()` to perform long blocking I/O.** The hook may run on the worker or canceller, increasing latency and risking deadlock.
17. **Not cleaning up after `cancel(true)`.** A cancelled Future does not prove locks/permits/connections have been released.
18. **Not handling `RejectedExecutionException` from the executor.** The FutureTask may stay in NEW forever with nothing running it.
19. **Giving important side effects to a task and treating a cancelled Future as a rollback.** Remote systems may already have committed; idempotency or reconciliation is needed.
20. **Not distinguishing `FutureTask` from `CompletableFuture`.** Both expose the Future API, but completion graph, cancellation, and interrupt semantics differ by implementation.

## 15. How to test FutureTask?

Focus on verifying **both the Future state and the execution behavior**.

### 15.1. Recommended tests

| Scenario | Assertion |
| --- | --- |
| Not yet run | `isDone()==false`, no side effects |
| Runnable completes | `get()` returns constructor value; body runs once |
| Callable completes | `get()` returns the computed value |
| Calling `run()` multiple times | Body still executes once |
| Callable throws exception | `get()` throws `ExecutionException` with original cause |
| Timed get expires | `TimeoutException`, Future may complete later |
| Cancel before run | Body does not run, `get()` throws `CancellationException` |
| Cancel while blocked interruptibly | Future cancelled, worker handles interrupt and cleans up |
| Cancel when task is uncooperative | Future can be cancelled while body is still running |
| Executor rejects | Do not wait on `get()` for a task never scheduled |
| `done()` hook | Called at terminal transition, does not assume success result |
| Multiple threads waiting on same Future | All waiters receive the same computation outcome |

### 15.2. Coordinating races with latches

A reliable testing technique is using `CountDownLatch`:
- `started`: confirms the worker has entered the body.
- `release`: holds the worker at a specific point until `main` checks an event.
- `exited`: confirms the worker has left the body.
- `Future.get(timeout)`: protects the test from hanging indefinitely on a bug.

`Thread.sleep(100)` only suggests a wait duration; it **does not prove** the worker has started or is blocked at the code of interest. Use latches/barriers to establish explicit ordering relationships.

### 15.3. Testing via stdout

Do not print execution times or thread ordering unless scheduling is guaranteed. If a demo has multiple competing workers, output should be based on:
- Final values after `join/get`.
- Side-effect counts tracked with appropriate synchronization primitives.
- Coordinated logical state.
- Expected exception types per the contract.
- Only print deterministic results under the stated demo conditions.

### 15.4. Thread and resource lifecycle

After using an executor, typically include:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
        pool.shutdownNow();
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This snippet assumes `pool` is already declared. `shutdown()` stops accepting new tasks while letting already submitted tasks finish; `shutdownNow()` only **attempts** to interrupt running tasks. `awaitTermination` lets the caller observe the executor actually terminating; it does not promise every task can be interrupted instantaneously.

## 16. Choosing FutureTask or another API?

| Need | Usually clear choice |
| --- | --- |
| Just run an action on another thread, caller needs no handle | `Runnable` + `Thread` or `Executor.execute` |
| Run a Callable and get a Future, no need to create the object yourself | `ExecutorService.submit(Callable)` |
| Have an existing Runnable, still want `get/cancel/isDone` on the same object passed to execute | **`FutureTask(Runnable, result)`** |
| Want to hold a Future/Runnable object yourself, customize `done()` | Subclass **`FutureTask`** with care |
| Periodic on a schedule | `ScheduledExecutorService` / `ScheduledFuture` |
| Process multiple completions in finish order | `ExecutorCompletionService` |
| Asynchronous transformation/composition pipelines | `CompletableFuture`; understand cancellation differences |
| Propagate cancellation across multiple child tasks | Ownership, Future handles, tokens/deadlines, and cleanup policy |
| Need to stop a task immediately, including uncooperative I/O | No general guarantee from `FutureTask.cancel(true)`; must design timeouts/cancellation at the resource |

**Choose by need**, not by how "advanced" a class name sounds. FutureTask fits when you need one object that is **both Runnable and Future**. If you only need to submit a Callable and call `get()`, the shortest path is usually `executor.submit(callable)`.

## 17. Self-check questions

1. Which interface does `FutureTask<V>` implement to be both runnable and trackable? **`RunnableFuture<V>`**, combining `Runnable` and `Future<V>`.
2. Where does `FutureTask<>(runnable, "OK")` get the `"OK"` value from? **From the constructor argument**, not from `Runnable.run()`.
3. When Runnable throws an exception, does `FutureTask.get()` return `"OK"`? **No**, it throws `ExecutionException`.
4. What is the difference between `new Thread(task).start()` and `task.run()`? **`start` creates/schedules a thread; `run` just invokes the method on the current thread**.
5. Does calling `task.run()` three times invoke the Callable three times? **No**, FutureTask is one-shot.
6. Why is `execute(futureTask)` sufficient when the caller still holds the object? **FutureTask is already a Runnable and a Future**, so the executor does not need to return a handle.
7. Why can `submit(futureTask)` be confusing? **`submit(Runnable)` typically returns an outer wrapping Future**, distinct from the inner FutureTask.
8. Does `isDone()==true` guarantee the task succeeded? **No**, it could have thrown an exception or been cancelled.
9. Does `isCancelled()==false` prove the task is currently running? **No**, it may not have started or may already have completed.
10. When a task throws, where do you get the original error? **`ExecutionException.getCause()`**.
11. Does a `get(timeout)` timeout automatically cancel the task? **No**.
12. Does `cancel(true)` returning `true` guarantee the thread has exited? **No**, it may still be running or cleaning up.
13. After a successful cancel, what does `get()` throw? **`CancellationException`**.
14. Should you call `get()` on a FutureTask that has never been scheduled? **Not without a mechanism that will run it or a timeout**, because it can wait forever.
15. Does a FutureTask cancelled before `run()` execute the Callable? **No**, terminal cancellation prevents the body from running.
16. Why should `done()` not perform long I/O? **The hook can run on the worker or canceller thread and slow down completion/cancellation or cause deadlock**.
17. Does `done()` being called guarantee the task has finished cleanup? **Not for cancellation**; the Future can become terminal before the body leaves the stack.
18. Does FutureTask run periodically if `run()` is called repeatedly? **No**, use `ScheduledExecutorService`.
19. To wait for results of multiple tasks in completion order, what should you consider? **`ExecutorCompletionService`**.
20. Do you need to construct a FutureTask manually when you just want `pool.submit(() -> 42)`? **Not required**; `submit` already returns a Future.
21. When `execute` is rejected, what is the risk of still calling `task.get()`? **It can wait forever because the task was never run**.
22. What memory consistency guarantee does `Future.get()` have? **Actions in the computation happen-before actions following the corresponding `get()` in another thread**.
23. If a task is cancelled after writing to a database, does FutureTask roll it back? **No**; you must have business protocols where side effects occur.
24. Do two threads calling `run()` on one FutureTask produce two independent results? **No**, it is still the same computation.
25. Can a program use FutureTask with a `Runnable` that returns no result just to know "is it done yet?" **Yes**, via `get/isDone` or `FutureTask<Void>` with a `null` result.

## Conclusion

`FutureTask<V>` is a **concrete implementation of `RunnableFuture<V>`**. It turns a `Runnable` or `Callable<V>` into **a one-shot computation that can be both executed and tracked via Future**:

~~~text
FutureTask(Runnable, result) or FutureTask(Callable)
          |
          +---> Thread.start() / Executor.execute() / run()
          |
          +---> isDone() / isCancelled()
          |
          +---> get() / get(timeout) / cancel(true|false)
~~~

With `Runnable`, the `get()` result is the value passed to the constructor **if the task completes normally**; with `Callable<V>`, it is the value returned by `call()`. Errors are wrapped in `ExecutionException`, cancellation leads to `CancellationException`, and timed `get` **does not automatically cancel the computation**.

`FutureTask` helps manage the result lifecycle of a task, but **is not a periodic scheduler itself, does not force all I/O to respond to interrupts, and does not replace cleanup/commit protocols**. When an executor already provides `submit(Callable)` and no custom lifecycle is needed, you can use the returned Future directly instead of creating an extra FutureTask.

## Java SE 17 References

- [FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): constructors, `run`, `done`, `runAndReset`, `get`, and cancellation.
- [RunnableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RunnableFuture.html): combining Runnable and Future.
- [Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): `run` contract.
- [Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): computation returning a result or exception.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, cancel, isDone, memory consistency.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): execute, submit, shutdown.
- [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): delayed and periodic scheduling.
- [ExecutorCompletionService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html): processing results in completion order.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion pipelines and cancellation differences.
