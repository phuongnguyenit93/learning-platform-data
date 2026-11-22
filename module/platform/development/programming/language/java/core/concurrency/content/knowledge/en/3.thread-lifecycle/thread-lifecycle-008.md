# Starting Once and the Thread Restart Error in Java

## 1. Core rule: a Thread object can only be started once

In Java, a `java.lang.Thread` object represents **a single execution of a thread**. After creation:

~~~java
// Illustrative snippet, not a standalone program.
Thread worker = new Thread(() -> doWork(), "worker-1");
worker.start();
~~~

the `start()` call asks the JVM to begin a new thread of execution. Once scheduled, that thread runs `run()`; when `run()` finishes normally or exits due to an uncaught error, the thread moves to the terminated state.

**The same `Thread` object cannot be `start()`ed a second time**, even when the first run's work has completed, the thread has been `join()`ed, or the programmer attempts to "reset" its state. Java throws `IllegalThreadStateException` when you try to restart an already-started object. To perform the work again, **create a new `Thread` object** or submit a new task to an appropriate `ExecutorService`.

Three distinct concepts need to be distinguished:

- **Task**: the work described by `Runnable` or `Callable`; it can be invoked or submitted for execution multiple times if its logic permits.
- **Thread object**: an execution session with its own lifecycle, from unstarted to terminated; it can only be `start()`ed once.
- **Worker in a thread pool**: a thread managed by an executor, which can execute **multiple tasks sequentially** via an internal loop; this does not mean calling `start()` repeatedly on that worker.

The once-only rule applies to the **thread object**, not to reusing the task's logic.

## 2. Placement in the Thread lifecycle

`Thread.State` in Java distinguishes six observable states:

| State | Meaning | Can call `start()`? |
| --- | --- | --- |
| `NEW` | The thread object has been created but not yet started | Yes, **once**, if there is no competing `start()` call |
| `RUNNABLE` | The thread is running or ready to be scheduled by the CPU | No |
| `BLOCKED` | The thread is waiting to acquire a monitor lock | No |
| `WAITING` | The thread is waiting indefinitely for an appropriate condition/event | No |
| `TIMED_WAITING` | The thread is waiting with a timeout, e.g., `sleep` or `join` with a timeout | No |
| `TERMINATED` | The thread has finished executing | No |

A simple path:

~~~text
new Thread(...)
      |
      v
     NEW
      |
    start()  [only once]
      |
      v
  RUNNABLE <----> BLOCKED / WAITING / TIMED_WAITING
      |
   run() finishes or uncaught error
      |
      v
  TERMINATED
      |
  start() again -> IllegalThreadStateException
~~~

The table only describes observable possibilities, not a mandatory diagram that every thread must pass through all states. For example, a thread can go from `RUNNABLE` to `TERMINATED` without ever entering `WAITING`.

**A very common misconception:** `TERMINATED` is not equivalent to `NEW`. Termination only means the old execution has stopped; it does not return the object to the unstarted state. The API provides no valid operation to "reset" a terminated `Thread`.

The value of `getState()` is a **point-in-time snapshot** and can change immediately after being read. The condition `thread.getState() == Thread.State.NEW` is not a safe coordination mechanism for allowing multiple threads to compete to start the same object.

## 3. Example 1 — start, join, then start again (Java 17+)

Create the file `StartOnceDemo.java`:

~~~java
public class StartOnceDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = new Thread(() -> {
            System.out.println(
                "Running on " + Thread.currentThread().getName()
            );
        }, "report-worker-1");

        System.out.println("Before start: " + worker.getState());

        worker.start();
        worker.join();

        System.out.println("After join: " + worker.getState());

        try {
            worker.start(); // Same object: not allowed.
        } catch (IllegalThreadStateException ex) {
            System.out.println(
                "Second start failed: " + ex.getClass().getSimpleName()
            );
        }

        System.out.println("Finished");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac StartOnceDemo.java
java StartOnceDemo
~~~

Exact output:

~~~text
Before start: NEW
Running on report-worker-1
After join: TERMINATED
Second start failed: IllegalThreadStateException
Finished
~~~

Step-by-step breakdown:

1. `new Thread(...)` only creates the object, so `getState()` before calling `start()` is `NEW`.
2. `start()` initiates execution and returns to the calling thread; the JVM decides when the worker actually runs. Therefore, you should not infer that the worker has finished merely from `start()` returning.
3. `join()` on `worker` makes the `main` thread wait until the worker finishes; after `join()` returns normally, the thread is `TERMINATED`.
4. Calling `worker.start()` again is rejected with `IllegalThreadStateException` even though the previous `run()` encountered no errors.
5. `catch` illustrates how to detect the invalid operation. In production code, the design should **avoid calling `start()` a second time** rather than routinely relying on exceptions for control flow.

`IllegalThreadStateException` is an unchecked exception, so the compiler does not require declaring `throws` for it. The `throws InterruptedException` clause on `main` is because `join()` can be interrupted, **not** because of the second `start()`.

### Why doesn't `join()` help restart?

`join()` only waits for a thread to finish; it does not create another thread and does not change the object's already-started history. Calling `join()` again on a terminated thread simply returns; this still does not grant permission to `start()` again.

Conversely, calling `join()` on a thread that **has never been started** can return immediately because the thread is not alive. Therefore, do not use `join()` as a signal confirming that work actually ran successfully; you must know the lifecycle and result channel of the task.

## 4. `start()` and `run()` are two different operations

The name `run()` easily misleads learners into thinking they can "rerun a thread" by calling it directly. In reality:

- `thread.start()` requests the creation of an independent thread of execution; the JVM will invoke `run()` on that thread. It can only be started once.
- `thread.run()` is a **normal Java method call**, running on the **calling thread**; it does not create a new thread and by itself does not transition the object from `NEW` to `RUNNABLE`.
- Calling `run()` directly multiple times can repeat the work on the calling thread, but it is **not** rerunning a started thread session.

### Example 2 — comparing by the actual executing thread (Java 17+)

Create the file `RunVsStartDemo.java`:

~~~java
public class RunVsStartDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Thread caller = Thread.currentThread();

        Thread worker = new Thread(() -> {
            System.out.println(
                "Runs on caller: "
                    + (Thread.currentThread() == caller)
            );
        }, "actual-worker");

        worker.run();
        System.out.println(
            "State after direct run: " + worker.getState()
        );

        worker.start();
        worker.join();

        System.out.println(
            "State after start and join: " + worker.getState()
        );
    }
}
~~~

Compile and run:

~~~bash
javac RunVsStartDemo.java
java RunVsStartDemo
~~~

Exact output:

~~~text
Runs on caller: true
State after direct run: NEW
Runs on caller: false
State after start and join: TERMINATED
~~~

The first time, `worker.run()` is called like a regular method and runs on the `main` thread; after the call, the `worker` object is still `NEW`. The second time, `worker.start()` launches the actual thread named `actual-worker`, so the comparison with `caller` returns `false`. The two printouts are ordered deterministically thanks to the synchronous direct call and `join()`.

A simple `Runnable` example can execute multiple times if the task's content allows it, but that does not mean each execution is a new thread. For tasks with side effects (writing files, deducting balances, sending requests), repeating `run()` can also cause duplicate business processing.

## 5. The right way to run the same work again

### 5.1. Create a new Thread for each execution

You can reuse a **`Runnable` object** when it has no state that causes issues across runs:

~~~java
// Illustrates the idea; Runnable only reads and does not mutate shared state.
Runnable task = () -> System.out.println("A unit of work");

Thread first = new Thread(task, "job-1");
Thread second = new Thread(task, "job-2");

first.start();
second.start();
~~~

These are two different `Thread` objects. Each object has the right to be `start()`ed exactly once. If you want to run them **sequentially** and avoid scheduling dependence, wait for `first.join()` before `second.start()`.

### Example 3 — creating a new thread on each iteration (Java 17+)

Create the file `NewThreadPerRunDemo.java`:

~~~java
public class NewThreadPerRunDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Runnable task = () -> {
            System.out.println(
                "Executed by " + Thread.currentThread().getName()
            );
        };

        for (int i = 1; i <= 3; i++) {
            Thread worker = new Thread(task, "task-worker-" + i);
            worker.start();
            worker.join();
        }
    }
}
~~~

Compile and run:

~~~bash
javac NewThreadPerRunDemo.java
java NewThreadPerRunDemo
~~~

Exact output:

~~~text
Executed by task-worker-1
Executed by task-worker-2
Executed by task-worker-3
~~~

The loop creates **three new thread objects**, each started once. `join()` inside the loop forces each iteration to finish before moving to the next, making the output order deterministic. When you want true concurrency among the three tasks, you can start all three first and then `join()` all three, though the print order will no longer be fixed.

**Cost:** Creating a new platform thread for a large volume of short-lived work can be expensive in terms of time, stack memory, and scheduling overhead. Do not use "create a new thread every time" as the default strategy for a very large number of tasks.

### 5.2. Use ExecutorService for a long sequence of tasks

`ExecutorService` accepts many tasks and manages worker threads on its own. Callers submit tasks with `execute(...)` or `submit(...)`; **do not** manually call `start()` on workers held by the executor.

Create the file `RepeatedTasksDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RepeatedTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
            Executors.newSingleThreadExecutor(
                task -> new Thread(task, "queue-worker-1")
            );

        try {
            for (int i = 1; i <= 3; i++) {
                int taskId = i;

                Future<String> result = executor.submit(() ->
                    "Task " + taskId + " on "
                        + Thread.currentThread().getName()
                );

                System.out.println(result.get());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac RepeatedTasksDemo.java
java RepeatedTasksDemo
~~~

Exact output when tasks complete normally:

~~~text
Task 1 on queue-worker-1
Task 2 on queue-worker-1
Task 3 on queue-worker-1
~~~

With `newSingleThreadExecutor`, tasks execute sequentially on one worker as long as that worker remains healthy. The worker can receive **multiple tasks through the executor's loop**, but the worker itself was still only `start()`ed once when the executor created it.

- `submit(...)` returns a `Future` to retrieve the task's result or exception. `get()` waits for completion; the sample code uses `get()` for deterministic output ordering.
- A worker can be replaced if it dies abnormally, so **you should not rely on a thread name or worker identity as an invariant guarantee across the entire application lifecycle**.
- `shutdown()` stops accepting new tasks while letting submitted tasks continue; `awaitTermination(...)` waits with a time bound; `shutdownNow()` only requests interruption of unfinished tasks.
- After an executor is shut down, submitting new work requires another executor; submitting a task to a shut-down executor typically throws `RejectedExecutionException`. This is an **executor lifecycle rule**, distinct from `IllegalThreadStateException` caused by calling `Thread.start()` a second time.

### 5.3. Which approach to choose?

| Need | Choice | Notes |
| --- | --- | --- |
| A single operation, wanting to see the Thread mechanism | `new Thread(task)` then `start()` | Simple for learning; must manage `join`/errors |
| Rerunning specific logic | Create a **new Thread** using the same safe `Runnable` | Do not reuse the old Thread object |
| Many continuous tasks, needing control over worker count | `ExecutorService` | Bounds concurrency, queueing, and shutdown |
| A task fails and you need to know the cause | `Future.get()`, task error handling | Avoid inferring success solely from `join()` |
| Java 21+, many independent I/O-bound tasks | Consider a virtual thread per task | Each virtual thread is still started only once |

## 6. What if multiple threads try to call start twice?

A real-world bug occurs when two places both try to start the same worker:

~~~java
// Unsafe illustration: two callers operating on the same object.
if (worker.getState() == Thread.State.NEW) {
    worker.start();
}
~~~

Even if both callers observe the `NEW` state, the `if` condition and the `start()` call do not form an atomic check-then-act operation. The first caller can start it; the second caller proceeds to `start()` and receives `IllegalThreadStateException`.

Checking `!worker.isAlive()` also does not determine "can be started" because `isAlive() == false` can occur when the thread **has never been started** or **has already terminated**. Similarly, `getState() == TERMINATED` proves it has finished, **not** that it is ready to run again.

Safer designs:

1. Identify the component that **owns** the right to create/start the thread (for example, a worker manager object).
2. Ensure the startup routine is called from a single controlled point; do not let multiple callers check state on their own and all call `start()`.
3. If there is a "start if not already started" requirement, use synchronization or `AtomicBoolean` to coordinate the **right to call start once**; this solution does not make the thread object restartable.
4. If the business requirement demands "clicking Start multiple times after each Stop", each cycle must create a **new thread object**, properly reinitialize the job's state, and manage waiting for the previous cycle to finish.

For example, consider a lifecycle model for a worker that can accept multiple run sessions: a controller holds the "running/stopped" state, each start **creates a new Thread**, and on stop it sends a cooperative signal (such as an interrupt or a synchronized stop flag) and waits for completion. Do not use `Thread.stop()`: this API is deprecated and inherently unsafe because it can stop a thread while it holds invariants/locks.

## 7. Why can't a terminated thread be revived?

A started `Thread` object is bound to an execution session, including its call stack, progress state, scheduling metadata, and completion process. Java defines no valid way to recreate that execution session by calling `start()` again.

Do not confuse **keeping a `Thread` object in a variable** with keeping the thread's ability to execute:

~~~java
// Illustration: the reference still exists, but the execution session has ended.
Thread t = new Thread(() -> System.out.println("done"));
t.start();
t.join();

// t is still referenced, but t.start() cannot be called again.
~~~

The reference `t` is still useful for observing the name, ID, final state, or checking whether the thread has finished. It does not hold a "rerun button." Every rerun of task logic is a new execution session.

In particular, if `run()` exits due to an uncaught exception, the thread still terminates and still cannot be restarted. Installing an `UncaughtExceptionHandler` only helps detect/report the error; the handler **does not** reset the thread back to `NEW`, automatically fix the error, or restart the same object.

## 8. Memory ordering, state, and observation

The once-only rule of `start()` also relates to the **happens-before** relationship in the Java Memory Model:

- Actions performed by a thread **before calling `otherThread.start()`** happen-before any actions performed by that new thread.
- When another thread waits for `join()` to complete successfully, actions of the terminated thread happen-before subsequent actions of the joining thread. Thus, after a normal `join()`, appropriate updates from the worker are published and visible to the waiting thread.

Those guarantees help coordinate across execution sessions, but they do **not** make all shared state thread-safe while multiple threads are running. If two workers update a mutable variable concurrently, you still need proper synchronization design (locks, atomics, immutability, or data ownership partitioning).

`getState()`, `isAlive()`, and thread names are useful for debugging and lifecycle inspection, but should not be used as the sole synchronization protocol. State can change right after observation. In production systems, a task/worker management structure typically needs explicit protocols for startup, completion, shutdown, and error handling.

## 9. Distinguishing related errors

| Action | What happens | Proper handling |
| --- | --- | --- |
| Calling `start()` for the first time on a `NEW` Thread | Launches the execution session | Wait or coordinate with the task as needed |
| Calling `start()` a second time on the same Thread | `IllegalThreadStateException` | Create a new Thread or use an executor |
| Calling `run()` directly on a Thread object | Runs synchronously on the **caller** | Use `start()` if a new thread is needed |
| Calling `start()` on a `TERMINATED` Thread | `IllegalThreadStateException` | Do not reset the thread; create a new session |
| Calling `join()` multiple times after termination | Returns immediately, does not restart | Use `join()` to wait, not to restart |
| Submitting a task to a shut-down executor | Usually `RejectedExecutionException` | Create or keep an active executor |
| Calling `Thread.start()` from two competing callers | Only one start succeeds; the other may throw | Coordinate ownership and the startup operation |
| Worker is interrupted | Coordination signal; thread may continue or exit depending on code | Handle interrupts per contract; do not treat as reset |
| Worker dies due to an uncaught exception | Thread terminates, cannot restart the same object | Log the error; decide whether to retry with a new task/thread |

### Common mistakes when fixing `IllegalThreadStateException`

- **Changing `start()` to `run()`** to make the error go away: the code may run, but it will run on the calling thread, easily losing concurrency or blocking the main execution path.
- **Calling `join()` before the second start**: `join()` does not alter the once-only rule.
- **Checking only `isAlive()` before starting**: `false` does not distinguish `NEW` from `TERMINATED`.
- **Storing a Thread in a field and calling start on every incoming request**: every request after the first risks throwing an exception; store a task factory or an executor instead.
- **Retrying `start()` on the same object in a catch loop**: the exception will repeat because the object has already been started.
- **Forgetting to shut down the executor**: switching to an executor without shutdown, resource limits, or error handling merely replaces one lifecycle bug with another worker-management issue.

## 10. Java 21+ and virtual threads

In Java 21, virtual threads were standardized as a permanent feature. Even though they are much cheaper than platform threads in many I/O-bound scenarios, a virtual thread **is still a `Thread` and can still only be started once**.

Java 21+ API example (illustrative, does not compile on JDK 17):

~~~java
Thread virtual = Thread.ofVirtual()
    .name("fetch-1")
    .unstarted(() -> System.out.println("fetching"));

virtual.start();
virtual.join();

// virtual.start(); // Invalid: IllegalThreadStateException.
~~~

If you want to run many independent tasks, you should normally create a new virtual thread for each task, or use `Executors.newVirtualThreadPerTaskExecutor()` to dispatch work; do not reuse a terminated virtual thread object.

This rule belongs entirely to Java's Thread API; no framework is required to apply it.

## 11. Self-check exercises

**Exercise 1 — identify the error:**

~~~java
// Illustrative, not a standalone program.
Thread t = new Thread(() -> System.out.println("hello"));
t.start();
t.join();
t.start();
~~~

Question: where does the error occur? **Answer:** at the second `t.start()` with `IllegalThreadStateException`; `join()` does not reset the state.

**Exercise 2 — reason about state:** A `Thread` object has never been `start()`ed, but `run()` has been called directly on it twice. What is `getState()` on that object if no other thread has called `start()`? **Answer:** `NEW`; the two `run()` calls do not create a new thread.

**Exercise 3 — retry design:** A data-sending task fails and needs to be retried if it is business-safe to do so. Should you keep the old `Thread` and call `start()` again? **Answer:** no. You must decide on retries according to the task's contract (idempotency, retry limit, backoff, side-effect handling), then submit the **task** to an executor or create a **new thread**. Business failures and thread lifecycle are two separate concerns.

**Exercise 4 — code reading:** An application checks `!thread.isAlive()` before calling `start()`. Is that condition sufficient to guarantee `IllegalThreadStateException` will not be thrown? **Answer:** no. `isAlive()` can be `false` when the thread has not been started *or* has already terminated, and the check itself is subject to a race condition.

## 12. Implementation checklist

- Properly distinguish between a **re-executable task** and a **Thread object that can only be started once**.
- Only call `start()` on a `NEW` Thread, from the component that owns startup responsibility.
- Use `join()` or another coordination mechanism when you need to know a task has finished; handle errors through an appropriate result channel.
- Do not use `run()` as a fix for calling `start()` a second time.
- To run again, create a new Thread object or submit a new task to an active executor.
- Do not rely solely on `getState()` or `isAlive()` to coordinate multiple callers.
- Design stopping, interruption, failure, and retry handling around business logic; do not use `Thread.stop()`.
- In real applications, measure concurrency, bound resources, and shut down executors properly.

**Remember:** A `Thread` is not a "restartable" object. `start()` is only valid once over the lifetime of **that specific object**. To repeat work, manage and re-execute the **task** via a new thread session or an executor.
