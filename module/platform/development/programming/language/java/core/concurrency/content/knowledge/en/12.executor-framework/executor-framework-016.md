# AbortPolicy, CallerRunsPolicy, DiscardPolicy, and DiscardOldestPolicy: Consequences Under Overload

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **ThreadPoolExecutor.RejectedExecutionHandler** and when a task is rejected by an executor, especially when **all workers are busy, the queue is full, or the executor has been shut down**.
- Accurately distinguish the four default JDK handlers: **AbortPolicy**, **CallerRunsPolicy**, **DiscardPolicy**, and **DiscardOldestPolicy**.
- Predict the **executing thread**, **lost tasks**, **exceptions at the submission site**, **changes in work ordering**, **backpressure**, and **Future state** under each policy.
- Design a **ThreadPoolExecutor with a bounded queue**, and test all four policies using controlled execution schedules so that tests do not depend on `Thread.sleep()`.
- Recognize why **submit() returning a Future does not guarantee the Future will complete** if a handler silently drops a `RunnableFuture` from the queue or drops a new task.
- Choose a rejection policy based on **acceptable data loss**, **idempotency**, **thread confinement**, **latency**, **retries**, **shutdown**, and the contract with the producer.
- Record metrics, handle errors, perform graceful shutdown, and explain the limitations of each mechanism within the scope of Java concurrency.

The scope is the **Java 17+ Executor Framework**, covering only JDK APIs. Spring-specific executor mechanisms are covered in another chapter.

## 2. Rejection Is Not Just a Technical Error: It Is a Decision About Data

In a system with finite resources, sometimes **more work cannot be accepted** in time. An executor might have only 2 workers and a queue for 10 tasks. If both workers are busy and 10 tasks are already in the queue, the 13th task will go to the **rejection handler** if no additional worker can be allocated.

~~~text
Producer submits task
        |
        v
ThreadPoolExecutor.execute(command)
        |
        +-- Can create worker per corePoolSize? ----> Execute
        |
        +-- Can queue accept command? --------------> Wait in queue
        |
        +-- Can add worker up to maximumPoolSize? --> Execute
        |
        +-- Cannot accept / already shut down ------> reject(command)
                                                         |
                                               RejectedExecutionHandler
~~~

This is a conceptual diagram: `ThreadPoolExecutor` also performs state checks and handles races during shutdown, changing worker counts, and changing queue state; actual decisions follow the JDK contract. The key point is: **the rejection handler is invoked when `execute` cannot accept a task given the current state and configuration**.

For the application, each behavior carries different consequences:

- **Throw an error** to the producer so the producer knows the task was not accepted.
- **Run the task directly on the producer thread**, shifting pressure back onto the sender.
- **Silently discard the newly submitted task**.
- **Discard the task that has been waiting the longest in the queue**, and try to insert the new task.

A task might be a debug log that can be lost, or a payment write command that must not be lost. **You cannot mechanically choose the same policy for every type of task.**

## 3. Conditions for ThreadPoolExecutor to Truly Saturate

A commonly used constructor:

~~~java
// Illustrative snippet inside a Java method; not a standalone file.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 2,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(10),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

The corresponding classes must be imported from `java.util.concurrent`.

Meaning:

| Component | Example | Meaning |
| --- | --- | --- |
| corePoolSize | 2 | Core worker threshold, typically created on demand |
| maximumPoolSize | 2 | Maximum number of workers |
| keepAliveTime | 0 | Time to keep excess workers beyond core; when core=max there are no excess workers |
| workQueue | ArrayBlockingQueue<>(10) | At most 10 tasks waiting in the queue |
| rejectedExecutionHandler | AbortPolicy | Handles cases where the executor cannot accept more tasks |

**Running workers are not in the queue.** With a pool of 2 workers and queue capacity 10, the maximum number of active/waiting tasks in this configuration is **2 running + 10 waiting**, before counting completed tasks; it is not "10 tasks total".

If you use **Executors.newFixedThreadPool(n)** or **newSingleThreadExecutor()** by default, the `LinkedBlockingQueue` has a very large capacity limit, so these executors **do not provide useful backpressure solely by limiting workers**. In practice, the queue can grow large enough to exhaust the heap. If you use **newCachedThreadPool()**, the pool typically uses a `SynchronousQueue` and a very large `maximumPoolSize`: when no worker is idle, the executor can create many platform threads, exhausting resources before any useful overload signal appears.

To observe rejection deliberately, the examples in this lesson use **one worker + a single-slot queue + a specified handler**.

### Simplified Task Acceptance Algorithm

1. If the worker count is less than **corePoolSize**, the executor tries to create a new worker for the command.
2. If core workers are already at capacity, it normally tries to **enqueue** the command while running.
3. If the queue cannot accept it, the executor tries to create another worker if still below **maximumPoolSize**.
4. If it cannot enqueue and cannot add a worker, or the executor is not accepting work due to shutdown, the command is **rejected**.

With a practically unbounded queue, step 2 almost always accepts more tasks until resources are exhausted, so setting `maximumPoolSize` higher than core **does not necessarily cause the pool to spin up additional workers**. This is why **workers, queue, and handler must be considered together**.

## 4. Comparison Table of the Four Default Policies

| Handler | When pool is running but saturated | Is the producer notified? | Key consequences |
| --- | --- | --- | --- |
| **AbortPolicy** | Throws `RejectedExecutionException` | **Yes**, via synchronous exception at `execute`/`submit` | Task not accepted; caller must handle failure |
| **CallerRunsPolicy** | The thread calling `execute` runs the task directly if the executor is not shut down | Does not throw for this saturation state alone | Producer may be blocked; task runs on an unexpected thread |
| **DiscardPolicy** | Drops the new task without notification | **No** | Silent task loss; `Future` may never complete |
| **DiscardOldestPolicy** | Drops the head of the work queue and retries executing the new task if not shut down | Usually no, though the retry may still be rejected depending on configuration | Waiting task is lost; breaks ordering and the dropped task's `Future` may hang |

**When the executor has been shut down**, the behavior is also important:

- **AbortPolicy** still throws `RejectedExecutionException`.
- **CallerRunsPolicy** does **not** run the task on the caller when the executor is shut down; it drops the task.
- **DiscardPolicy** drops the task without notification.
- **DiscardOldestPolicy** does not try to remove/re-submit a task when the executor is shut down, and drops the task.

This is the behavior of the **standard JDK handler implementations**. Do not infer from `execute()` returning normally that the task was enqueued, will be run, or has completed.

## 5. AbortPolicy: Fail-Fast So the Producer Can Decide Proactively

**ThreadPoolExecutor.AbortPolicy** is the default handler when creating a `ThreadPoolExecutor` without supplying another handler. When invoked, it throws **RejectedExecutionException**.

~~~java
// Illustrative snippet inside a Java method:
try {
    pool.execute(task);
} catch (RejectedExecutionException ex) {
    // Task was not accepted; handle according to business contract.
}
~~~

**Rejection happens at the submission call**, not as an exception from code inside the task. These are two distinct classes of failure:

- Task was not accepted: **RejectedExecutionException** immediately when calling `execute`/`submit`.
- Task was accepted, but its execution itself failed: exception in the worker; with `submit()` this is typically stored in the `Future` and surfaced via **Future.get() / ExecutionException**.

### When Is AbortPolicy Appropriate?

- Work **must not silently disappear**, such as data updates that must be recorded.
- The producer can **report busy**, throttle down, route to an alternative path, or write to a durable queue.
- Clear rejection metrics are needed to know when the system is overloaded.
- There is a clear contract for retries, timeouts, and task idempotency.

**AbortPolicy does not retry automatically.** It simply hands the decision back to the caller. If the caller immediately retries infinitely in a tight loop, the system can become even more overloaded. Retries need backoff, a retry limit, an overall deadline, and re-evaluation of demand.

**Do not catch the exception and pretend it succeeded**:

~~~java
// Anti-pattern: caller ignores that work was not accepted.
try {
    pool.execute(saveOrder);
} catch (RejectedExecutionException ignored) {
    // Caller still receives a "saved" response, which is wrong.
}
~~~

This is illustrative code; `pool` and `saveOrder` need to be declared. For critical tasks, failure to accept work must be reflected in the status/response or routed to a reliable storage mechanism by design.

## 6. CallerRunsPolicy: Creating Backpressure Using the Submitting Thread

**CallerRunsPolicy** has a core logic: if the executor **is not shut down**, the thread calling `execute(command)` runs **command.run()** directly.

This means that under overload, the producer no longer just enqueues work—it **must perform the just-submitted work itself right then**, slowing down its ability to keep submitting more. This is a form of **coarse backpressure**, which can be useful when both producer and worker are permitted to execute the same task.

~~~text
Normal:
Producer -> execute(task) -> Queue/worker -> execute

Saturated pool, CallerRunsPolicy:
Producer -> execute(task) -> task.run() directly on Producer thread
                            |
                            +-- Producer is held until task.run() finishes
~~~

Points to watch out for:

1. **The caller thread may be the main thread, a request thread, an event-loop thread, or a thread holding a lock**; it is not a worker managed by the executor.
2. If the task blocks for a long time, the caller is blocked for a long time; request latency and responsiveness can suffer.
3. If the task relies on `ThreadLocal`, thread name, security context, thread affinity, or worker ownership, behavior can change.
4. **There is no execution ordering guarantee between the task executed by the caller and tasks waiting in the queue**. The new task can finish before older queued tasks.
5. If the caller is a task running inside the **same executor**, `CallerRunsPolicy` can cause **nested execution** on the worker thread, increasing call depth and altering ordering assumptions.
6. **If the executor has been shut down, the handler does not run the task on the caller**, so it can silently drop the task.

### When Should It Be Used?

- The task **does not depend on a specific thread** and is safe to run on any producer thread.
- The producer can accept being blocked so the system does not accept unbounded new work.
- Latency, timeout, and thread-affinity contracts are clear.
- You have evaluated whether the caller holds locks, participates in transactions, or drives a network event loop.

### Dangerous Case: Breaking Thread Confinement

Suppose mutable state is only allowed to be modified by a single worker in a single-thread executor. If you replace the executor with a one-worker `ThreadPoolExecutor` using **CallerRunsPolicy**, when the queue is full, a producer can run the state-updating task **directly on the producer thread**. Thus **one task on the worker and one task on the producer can access the state concurrently**, causing races or breaking ordering.

It is not just a performance issue: **CallerRunsPolicy can change the correctness model**. Do not choose it just because of the label "backpressure" and forget that the task is no longer guaranteed to run on the owner worker.

## 7. DiscardPolicy: Silently Dropping the New Task

**DiscardPolicy** performs **no action** on rejection. The `execute` call can return normally, yet the command **is not run**.

For tasks like debug logs that are allowed to be lost, this approach is sometimes an intentional choice to keep the main system running. However, it is dangerous for tasks that:

- Write financial or mandatory business data.
- Send notifications that require delivery guarantees.
- Release/close resources belonging to a subsequent step.
- Signal completion to another thread.
- Write mandatory audit logs.
- Cause the caller to return an "accepted" response simply because `execute()` did not throw.

**Silent loss** also hurts debugging: the producer may have no direct indication that the request never ran, and there are no metrics unless an external handler/telemetry is added.

### Subtlety When Using submit()

**ExecutorService.submit()** typically wraps the command in a **RunnableFuture** and passes it to `execute()`. If `DiscardPolicy` drops the `RunnableFuture`, the `Future` returned to the caller may **never transition to the done state**, because the task was neither run nor cancelled.

Consequences:

- **future.get()** may wait forever.
- **future.get(timeout)** may time out, which does not prove the task was ever accepted.
- **future.isDone()** may remain `false` even after the executor has terminated.
- **shutdown()** does not automatically turn a discarded `Future` into cancelled.

Therefore, if silent discard is permitted, you must design an independent way to notify/check results or **not expose a Future with an expectation of guaranteed completion**.

## 8. DiscardOldestPolicy: Dropping the Oldest Waiting Task, Trying to Accept the New Task

When the executor is still running and cannot accept a new command, **DiscardOldestPolicy** does roughly the equivalent of:

~~~java
// Pseudocode illustrating the main behavior of the default handler:
if (!executor.isShutdown()) {
    executor.getQueue().poll(); // Drop the head of the queue.
    executor.execute(newTask);  // Retry accepting the new task.
}
~~~

This is an illustrative snippet requiring `executor`/`newTask` to be declared; it is not a standalone program.

**"Oldest" here means the head element of the work queue according to the queue's mechanics**, not the task that has been running the longest, nor the "task with the smallest system-wide timestamp".

With a **FIFO ArrayBlockingQueue/LinkedBlockingQueue**, the head is usually the task that has been waiting the longest. However:

- **A currently running task is not evicted or stopped**.
- **A task dropped from the queue is not automatically cancelled**.
- If the queue has no element to poll, the retry can still reject; in some configurations without useful capacity (such as `SynchronousQueue`), a retry loop through the handler can loop without making progress. Do not use `DiscardOldestPolicy` blindly with every queue type.
- With a priority queue, the head is determined by the **queue's ordering**, not necessarily oldest by submission time; dropping the head can break priority policies.
- When the executor has been shut down, the handler does not execute the standard poll/re-execute sequence, and the new task is dropped.

### Business Consequences

Suppose commands arrive in order:

~~~text
A is executing on the worker
B is waiting in the queue (capacity=1)
C is submitted while the worker is still busy

DiscardOldestPolicy:
  B is polled from the queue and dropped
  C is retried into the queue
  When A finishes -> C runs
  Result: A, C run; B is lost
~~~

For **order-dependent state updates**, the result can be wrong: C may assume B already ran. If B is a debit command and C is a confirmation command, dropping B is a severe data bug. If you are only updating the **latest state snapshot** and older updates can be dropped, intentional coalescing logic may be more suitable, though you still need to handle `Future`/metrics and ordering correctness.

## 9. Example 1: Direct Comparison of All Four Policies with a Deterministic Schedule

This example creates **1 worker, queue capacity=1**. Task A holds the worker until `main` releases it, task B sits in the queue, and task C triggers rejection. Results are sorted alphabetically after completion so they do not depend on inter-thread log order.

File **RejectionPolicyMatrixDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionPolicyMatrixDemo {
    static String runCase(RejectedExecutionHandler policy)
            throws InterruptedException {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), policy
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        List<String> ran = Collections.synchronizedList(new ArrayList<>());
        boolean rejected = false;

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    ran.add("A");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            pool.execute(() -> ran.add("B"));

            try {
                pool.execute(() -> ran.add("C"));
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            List<String> finished = new ArrayList<>(ran);
            Collections.sort(finished);
            return "rejected=" + rejected
                    + ", ran=" + String.join("", finished);
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "AbortPolicy: "
                + runCase(new ThreadPoolExecutor.AbortPolicy())
        );
        System.out.println(
                "CallerRunsPolicy: "
                + runCase(new ThreadPoolExecutor.CallerRunsPolicy())
        );
        System.out.println(
                "DiscardPolicy: "
                + runCase(new ThreadPoolExecutor.DiscardPolicy())
        );
        System.out.println(
                "DiscardOldestPolicy: "
                + runCase(new ThreadPoolExecutor.DiscardOldestPolicy())
        );
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 RejectionPolicyMatrixDemo.java
java RejectionPolicyMatrixDemo
~~~

Stdout during a normal run without external interruption:

~~~text
AbortPolicy: rejected=true, ran=AB
CallerRunsPolicy: rejected=false, ran=ABC
DiscardPolicy: rejected=false, ran=AB
DiscardOldestPolicy: rejected=false, ran=AC
~~~

**Reasoning for each case:**

- **AbortPolicy**: A holds the worker, B takes the slot in the queue, C is not accepted and causes `execute()` to throw an exception. A and B run.
- **CallerRunsPolicy**: when C is rejected, the `main` thread directly calls `C.run()` before releasing A. Then A/B proceed. C still executes, but not on a pool worker.
- **DiscardPolicy**: C is dropped, `execute()` reports no error. A and B run.
- **DiscardOldestPolicy**: B is removed from the queue and C is enqueued; after A leaves the worker, C runs.
- **Collections.sort** is only used to print the names of tasks that ran in a stable order; it **does not assert execution order**.
- After `awaitTermination` returns `true`, all tasks have finished running and modifications to the list are complete, so reading the result is valid.

In real applications, **do not drop B or C as a default policy** if the business requires no task loss. This example intentionally simulates saturation to demonstrate each handler's semantics.

## 10. Example 2: CallerRuns Actually Runs on the Submitting Thread

The previous example showed all three tasks running with `CallerRunsPolicy`; below we verify **thread identity** by comparing `Thread` objects, without relying on JVM-assigned thread names.

File **CallerRunsThreadDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CallerRunsThreadDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread caller = Thread.currentThread();

        try {
            Future<Integer> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return 1;
            });

            started.await();
            Future<Integer> second = pool.submit(() -> 2);

            Future<Boolean> third = pool.submit(
                    () -> Thread.currentThread() == caller
            );

            System.out.println(
                    "third on caller = " + third.get()
            );

            release.countDown();
            int completed = first.get() + second.get();
            System.out.println("worker sum = " + completed);
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallerRunsThreadDemo.java
java CallerRunsThreadDemo
~~~

Stdout:

~~~text
third on caller = true
worker sum = 3
~~~

**Why is this deterministic?** The single worker is waiting on `release`, and the queue holds `second`, so `third` cannot enter the worker or queue. `CallerRunsPolicy` calls `RunnableFuture.run()` directly on `main`; the `Callable` inside returns **true** because `Thread.currentThread() == caller`. The `Future` for `third` completes right inside the `submit` call. `main` then opens the latch so `first`/`second` can finish.

**Design consequences:** If the task uses `ThreadLocal` or is only permitted to mutate state on the worker, `third` may execute with an unexpected context. If the submitting thread is a request thread, it is held for the entire duration of `third`, increasing request latency. If the submitting thread holds a lock that `third` needs, reentrancy, lock contention, or deadlock can occur depending on the protocol.

## 11. Example 3: The Future of a Task Dropped by DiscardOldest May Never Be Done

With `submit()`, the command in the queue is typically a **FutureTask**. `DiscardOldestPolicy` removes it via `queue.poll()` but **does not call cancel()**. We inspect the state after the pool has terminated; never call `get()` without a timeout on a discarded `Future`.

File **DiscardedFutureDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class DiscardedFutureDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.DiscardOldestPolicy()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return 1;
            });

            started.await();
            Future<Integer> dropped = pool.submit(() -> 2);
            Future<Integer> newest = pool.submit(() -> 3);

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            System.out.println("first = " + first.get());
            System.out.println("newest = " + newest.get());
            System.out.println("dropped done = " + dropped.isDone());
            System.out.println("dropped cancelled = " + dropped.isCancelled());
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DiscardedFutureDemo.java
java DiscardedFutureDemo
~~~

Stdout:

~~~text
first = 1
newest = 3
dropped done = false
dropped cancelled = false
~~~

**Why is this noteworthy?**

1. `first` is running and waiting on the latch; `dropped` sits in the capacity-1 queue.
2. `newest` arrives when the pool is saturated; the handler removes `dropped` from the queue, then enqueues `newest`.
3. `first` and `newest` complete and the executor terminates, yet the `Future` named `dropped` **was never run or cancelled**.
4. `dropped.isDone()` remains `false`, and `dropped.isCancelled()` is also `false`. If `dropped.get()` is called without a timeout, the caller can wait indefinitely.
5. **Pool termination does not automatically mark every previously returned Future as done** when a policy has silently discarded a task.

Similar behavior can occur with **DiscardPolicy** when it immediately drops a newly submitted `RunnableFuture`. When a result/ack is required for every request, avoid default silent-discard handlers or establish an explicit completion/cancellation protocol.

## 12. Example 4: Custom Rejection Handler That Fails and Records Metrics

In operations, you need to know how many requests the system rejects and why. A custom handler can increment a counter and then throw `RejectedExecutionException`, giving the producer a clear signal.

File **MeasuredRejectionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MeasuredRejectionDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger rejections = new AtomicInteger();

        RejectedExecutionHandler handler = (task, executor) -> {
            rejections.incrementAndGet();
            throw new RejectedExecutionException("capacity exceeded");
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), handler
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            pool.execute(completed::incrementAndGet);

            boolean rejected = false;
            try {
                pool.execute(completed::incrementAndGet);
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            System.out.println("caller saw rejection = " + rejected);
            System.out.println("rejections = " + rejections.get());
            System.out.println("completed = " + completed.get());
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MeasuredRejectionDemo.java
java MeasuredRejectionDemo
~~~

Stdout:

~~~text
caller saw rejection = true
rejections = 1
completed = 2
~~~

**Meaning:** the first task held the worker, the second task sat in the queue, and the third task triggered the handler. The handler both incremented the metric and threw an error. The caller knew the task was not accepted and could report overload or route the work elsewhere. After releasing the latch, the two accepted tasks completed.

For production, metrics should distinguish **rejected due to pool saturation** from **rejected due to executor shutdown**, if that distinction is needed operationally. Do not overuse slow metrics/logging or blocking I/O inside a rejection handler: it runs on the submission path and can slow down the producer further or cause contention.

## 13. Be Careful with submit(), execute(), and Future

### execute(Runnable)

`execute()` takes a `Runnable`. If **AbortPolicy** throws, the caller catches the submission failure. If **CallerRunsPolicy** runs the `Runnable` immediately, `execute` only returns once `Runnable.run()` has finished on the caller. If **DiscardPolicy** or **DiscardOldestPolicy** silently drops the task, `execute` can return normally even though the task was never executed.

### submit(Runnable/Callable)

`submit()` typically creates a **RunnableFuture**, then calls `execute(RunnableFuture)`:

~~~text
submit(callable)
    |
    v
new RunnableFuture
    |
    v
execute(runnableFuture)
    |
    +-- worker/queue accepts -> Future can complete
    |
    +-- CallerRunsPolicy -> FutureTask.run on caller -> Future done
    |
    +-- AbortPolicy -> throws RejectedExecutionException,
    |                  no successful Future returned
    |
    +-- DiscardPolicy -> drops FutureTask -> Future may never be done
    |
    +-- DiscardOldestPolicy -> older FutureTask removed from queue
                               -> older Future may never be done
~~~

**Future.get() only has a contract to wait for the Future's result**, not a contract to detect that a task was silently discarded by an arbitrary handler. For lossy policies, the caller needs a protocol confirming the task **was accepted and will reach a terminal state** if that is a business requirement.

### Task Exceptions Differ from Rejection

A task that was accepted, ran, and then threw `IllegalArgumentException` is a **task failure**. With `submit()`, `Future.get()` will throw `ExecutionException` wrapping the cause, not a `RejectedExecutionException` from the submission step.

A system should distinguish at minimum:

- **Rejected**: not accepted into the executor.
- **Queued**: accepted, not necessarily started yet.
- **Running**: currently executing.
- **Succeeded / Failed**: task finished with a result or failure.
- **Cancelled / Timed out while waiting**: the `Future` state and business state may differ.

If a task is silently discarded while its `Future` is not done, it does not automatically belong to any of the terminal states above. This is why silent policies are hard to use for workflows that require tracking.

## 14. Rejection Due to Shutdown: Not Always Caused by High Load

Once **shutdown()** has been called, the executor **does not accept new tasks**, even if the queue is empty and no workers are busy. Subsequent submissions can go to the rejection handler.

- With `AbortPolicy`, the caller typically receives `RejectedExecutionException`.
- With `CallerRunsPolicy`, the task is dropped when the executor is shut down: **it does not run on the caller**.
- With `DiscardPolicy`, the task is dropped.
- With `DiscardOldestPolicy`, the task is dropped without attempting to re-enqueue.

**This is an important distinction between "out of capacity" and "closed to new work"**. If a handler only increments an "overloaded" counter, metrics will be wrong during shutdown. A custom handler can check `executor.isShutdown()` to classify the cause, though that snapshot can change due to races; counting failure categories accurately may require a stricter lifecycle/telemetry protocol.

### Do Not Choose CallerRunsPolicy to Force Execution After Shutdown

Some people use `CallerRunsPolicy` expecting "the task will always run even if the pool is closed". **That is incorrect.** The standard handler only runs the task on the caller if the executor **is not shut down**. An `execute()` call returning normally after shutdown under `CallerRunsPolicy` is not proof that the task executed.

### Submitting After Shutdown with DiscardPolicy

A `Future` returned from `submit` after shutdown under `DiscardPolicy` can be dropped without becoming done, just like in the saturation scenario. Therefore, manage the lifecycle of producers and executors: **stop producers before shutting down the executor**, or define a clear error-reporting behavior when submitting to a closed executor.

## 15. CallerRunsPolicy Is Backpressure, Not Perfect Throttling

When the producer runs the task itself, the submission rate usually drops, reducing pressure on the queue. However, the degree depends on task characteristics:

- If the task is very fast, the caller finishes it quickly and can immediately resume flooding.
- If the producer has multiple threads, **multiple callers can run tasks concurrently**, causing the total number of executing tasks to **exceed the pool's worker count**. Thus **maximumPoolSize is no longer a bound on total concurrency** when caller-run tasks are counted.
- If the caller is an event-loop thread, a request thread, or a thread holding a lock, running the task can heavily impact latency and progress elsewhere in the system.
- If the task expects a specific thread name, `ThreadLocal`, transaction context, or security context, running on the caller breaks those assumptions.
- If the task can block on a resource held by the producer, waiting can cause deadlock.

### When You Need a Hard Cap on Total Concurrency

If the requirement is "no more than K concurrent calls to an external service from **all threads**", **CallerRunsPolicy does not guarantee K by itself**. Consider an independent `Semaphore`/quota around the service call, or an explicit rejection policy on saturation with valid permit boundaries.

An executor only bounds **its own workers**; it does not manage tasks running directly on arbitrary producers.

## 16. When Is Dropping Tasks Acceptable?

A loss-tolerant strategy must be based on the specification, not just the policy name:

| Workload Type | Can Task Loss Be Considered? | Required Conditions |
| --- | --- | --- |
| High-frequency debug telemetry | Possibly | Missing samples acceptable; dropped metric tracked |
| Continuously updated metrics | Possibly | Next snapshot supersedes the previous snapshot |
| Cache warm-up | Possibly | Cache miss still has a correct fallback path |
| Stale UI preview frames | Possibly | Only the latest state matters, with clear coalescing |
| Recording invoices / money transfers | Usually not | Needs confirmation or durable handoff, idempotent retry |
| Returning task results where caller calls `Future.get()` | Should not silently discard | `Future` must reach a terminal state or fail explicitly |
| Resource cleanup tasks | Usually not | Dropping tasks can leak resources |
| Command processing with ordering dependencies | Cannot drop arbitrarily | Dropping B can invalidate C's preconditions |

**DiscardOldestPolicy is not automatically equivalent to "keep only the latest value per key".** It drops the head of the **entire queue**, does not coalesce by key, ignores dependencies, and knows nothing about payload substitutability. If business logic needs latest-per-key, implement a per-key queue/coalescing structure and an explicit completion contract.

## 17. Choosing a Policy by Specification: Decision Matrix

| Primary Requirement | Starting Policy | Why |
| --- | --- | --- |
| Task must be accepted or fail explicitly | **AbortPolicy** / custom throwing handler | Producer avoids silent loss |
| Producer can execute the task and accept being blocked | **CallerRunsPolicy** | Provides backpressure, but thread affinity and concurrency must be verified |
| New tasks can be safely dropped, nobody awaits `Future` | **DiscardPolicy**, with telemetry | Silent drop is only valid under a loss-tolerant contract |
| Older queued snapshots can be replaced by newer tasks | **DiscardOldestPolicy** after analyzing FIFO/order/dependencies | Can reduce staleness, but drops waiting tasks and strands `Future`s |
| Business cannot lose work across restarts | No policy alone is sufficient | Needs a durable queue/transaction/outbox or persistence protocol |
| Need a hard cap on resource concurrency | Bounded executor + appropriate quota/permit | `CallerRuns` can execute outside the worker pool |
| Task must run on a single owner thread | **Do not use CallerRunsPolicy** | Caller execution breaks confinement |
| Want controlled producer throttling | Explicit custom backpressure, deadline, or bounded handoff | Not synonymous with silently dropping tasks |

**The safe default for developing applications that must not lose work** is usually **AbortPolicy** or a custom handler that both records metrics and throws an error. `CallerRunsPolicy` is a useful tool, but you must evaluate **latency and execution context**. `Discard` and `DiscardOldest` are only appropriate when loss semantics are explicitly approved.

## 18. Consequences When the Queue Is Full and Why Policies Do Not Change Real Resources

A common mistake is thinking that picking a good handler will "solve overload". A handler only decides **what happens at the point a task cannot be accepted**; it does not make CPU, RAM, the DB pool, or a remote service faster.

Suppose:

~~~text
Input rate: 1,000 tasks/second
Service capacity: 200 tasks/second
Backlog growth: ~800 tasks/second if all are accepted
~~~

Behaviors:

- **AbortPolicy**: exposes the overload; the producer must slow down or route work elsewhere.
- **CallerRunsPolicy**: the producer does part of the work itself and usually slows down; however, it can push load onto request threads or elsewhere.
- **DiscardPolicy**: prevents some new tasks from piling up, at the cost of data loss.
- **DiscardOldestPolicy**: favors newer arrivals by evicting earlier waiting tasks; freshness may improve, but task loss still occurs.

Long-term stability requires **capacity planning, admission control, rate limiting, bounded queues, deadlines, appropriate autoscaling, throughput measurement**, or workload redesign. Choosing a handler is only one part of an overload strategy.

## 19. Common Real-World Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Creating a fixed pool and assuming the queue is bounded | Memory/backlog grows before rejection | Use a bounded queue when explicit backpressure is needed |
| Checking only worker count while ignoring the queue | Misjudging remaining capacity | Inspect workers, queue, active count, and submit rate together |
| Catching `RejectedExecutionException` and returning success | Task was not accepted, yet business reports completion | Propagate/report/retry in a controlled way |
| Using `CallerRunsPolicy` for tasks that must run on an owner worker | Races and ordering bugs | Do not use caller-run for thread-affine tasks |
| Using `CallerRunsPolicy` on request threads with strict SLAs | Tail latency spikes | Use admission limits or explicit busy responses |
| Using `CallerRunsPolicy` to cap total concurrency | Caller tasks add on top of workers | Enforce quota/permits at the resource boundary |
| Using `DiscardPolicy` for mandatory tasks | Silent task loss | `Abort`/custom handler/durable handoff |
| Calling `submit` with `DiscardPolicy` then `Future.get()` indefinitely | `Future` may never be done | Avoid silent discard or use a terminal-state protocol |
| Using `DiscardOldestPolicy` with dependent FIFO commands | Old commands are lost, breaking workflows | Do not drop arbitrarily; preserve order or coalesce intentionally |
| Using `DiscardOldestPolicy` with a queue lacking a suitable head | Retries reject without progress | Match handler to queue; avoid this policy with `SynchronousQueue` |
| Assuming "oldest" means the longest-running task | Wrong task evicted | Only the head of the work queue is polled |
| Using `isShutdown()` as an independent sync check before `submit` | Race between check and submit | Handle rejection and lifecycle properly |
| Assuming `shutdown` completes discarded `Future`s | `Future`s can remain pending | Provide a separate cancellation/reporting mechanism |
| Unbounded retries after rejection | Amplifies overload | Use deadlines, backoff, idempotency, and retry limits |
| Calling blocking APIs in a custom handler while holding other locks | Increased contention/deadlock | Keep handlers short, non-blocking, or provably safe |
| Switching from `Abort` to `Discard` just to stop exceptions | Hides overload and loses data | Fix capacity and backpressure strategy |

## 20. Observability and Verification in Real Systems

To verify that a rejection policy behaves as expected, monitor:

- **Submitted task count** by workload group.
- **Accepted task count** into queue/worker or executed on caller.
- **Rejected/dropped task count**, split by capacity vs. shutdown if distinguishable.
- **Queue size** and **queue age** (time from submit to start).
- **Active worker count**, pool size, and completed task count.
- **CallerRuns invocations** and time spent by producers executing tasks.
- **DiscardOldest evictions** if using custom telemetry.
- **p95/p99 latency**, memory, thread count, and error/timeout/retry counts.
- **Completed, pending, and cancelled Futures**; do not count submitted tasks alone.

**Note on metrics:** `ThreadPoolExecutor.getTaskCount()`, `getCompletedTaskCount()`, `getQueue().size()`, and `getActiveCount()` are approximate/snapshot measurements that can change between reads. Do not build business logic like "exactly one slot left" by checking `size` and then calling `execute`, because another thread can submit right after the check.

If you need exact acceptance status, design **acknowledgement** at the ingress boundary rather than inferring it from diagnostic counters.

### What Should Policy Tests Verify?

1. Hold the worker with a **CountDownLatch**, fill the queue, then submit the task that triggers rejection.
2. Verify **which tasks actually ran** and which exception path occurred.
3. For `CallerRunsPolicy`, verify the **Thread identity** of the third task.
4. For `Discard`/`DiscardOldest`, verify the **returned Future can remain pending**, without calling `get()` indefinitely.
5. Test submitting after `shutdown`; evaluate each handler's specific behavior.
6. Simulate task failure and distinguish **ExecutionException** from **RejectedExecutionException**.
7. Verify **shutdown/cleanup** so tests do not hang with workers waiting on latches.
8. Reason from API contracts and invariants; a passing stress test does not prove all schedules are correct.

## 21. Shutdown, Cancellation, Interruption, and Final Responsibility

**ThreadPoolExecutor.shutdown()** rejects new tasks while still processing previously accepted tasks per the contract. **shutdownNow()** attempts to interrupt running tasks and returns the list of tasks that had not started, but does not guarantee running tasks stop immediately.

**Future.cancel(true)** is a cancellation request that may interrupt the worker; it does not force rollback of side effects that already occurred. For a task dropped by `DiscardPolicy`/`DiscardOldestPolicy` whose `Future` is not done, the caller can call **cancel()** if it still holds the reference, but knowing **when the task was lost** is the problem. Default silent handlers do not provide a callback to inform the caller.

If the work involves payments, files, or database state:

- Rejection does **not** necessarily mean no side effects occurred in steps before submission.
- Retries can create duplicate operations without an idempotency key.
- `CallerRunsPolicy` can execute side effects **right inside the submit call**, without waiting for a worker.
- `DiscardOldestPolicy` can drop a step that later steps depended on.
- Shutting down while producers are still submitting requires a clear protocol so work is not lost.

Therefore, a policy only guards **the boundary of submitting tasks into an executor within the JVM**; it does not guarantee transactions or exactly-once semantics across multiple services.

## 22. Pre-Selection Checklist

**Task specification:**

- [ ] Is the task allowed to be lost? If yes, is dropping new or dropping old appropriate?
- [ ] Does the task have ordering dependencies or state that must not be skipped?
- [ ] Does the caller need exact "accepted" and "completed" status?
- [ ] Is `Future.get()` waiting for every task to eventually be done?
- [ ] Does the task have side effects requiring idempotency, retries, or durable storage?

**Threads and resources:**

- [ ] Are workers and queue bounded appropriately for real-world capacity?
- [ ] Can the task run safely on the caller thread?
- [ ] If using `CallerRuns`, is total actual concurrency at the resource still bounded?
- [ ] Are locks, thread affinity, or `ThreadLocal` values altered when the caller runs the task directly?
- [ ] Are there separate measures for bursts, long blocking I/O, and sustained overload?

**Operations and testing:**

- [ ] Are metrics tracked for rejected, discarded, queue size/age, and caller-run latency?
- [ ] Are there deterministic tests for saturation and post-shutdown submission?
- [ ] Are there safeguards against `Future`s staying pending due to silent discard?
- [ ] Is there a feedback path or bounded retry/backoff when `AbortPolicy` throws?
- [ ] Does shutdown stop producers or report rejection status clearly?
- [ ] Are exceptions from accepted tasks collected properly via `Future`/handlers?

## 23. Self-Check Questions

**Q1.** All workers are busy and the queue is full; what does `AbortPolicy` do?  
**Answer:** It throws `RejectedExecutionException` immediately on the `execute`/`submit` path; the caller must handle the task not being accepted.

**Q2.** Does `CallerRunsPolicy` always run tasks on the worker pool?  
**Answer:** No. When saturated and not shut down, it calls `task.run()` directly on the thread calling `execute`, which is usually the producer.

**Q3.** If the executor has been shut down, does `CallerRunsPolicy` run a new task on the caller to "save" it?  
**Answer:** No. The standard handler does not run tasks when the executor is shut down and may drop them without throwing.

**Q4.** Is `DiscardPolicy` suitable if the caller always calls `Future.get()` without a timeout?  
**Answer:** No. A dropped `RunnableFuture` may never become done or cancelled, causing `get()` to wait forever.

**Q5.** Which task does `DiscardOldestPolicy` drop?  
**Answer:** The head of the work queue, not the currently running task. With a FIFO queue, this is usually the task that has been waiting the longest.

**Q6.** Why might `CallerRunsPolicy` fail to enforce a hard cap of 4 concurrent task executions?  
**Answer:** In addition to the 4 workers, multiple producer threads can execute rejected tasks themselves, pushing total concurrency above 4.

**Q7.** Does using `DiscardOldestPolicy` with `PriorityBlockingQueue` guarantee dropping the earliest-submitted task?  
**Answer:** No. The queue head is determined by the queue's ordering, not necessarily submission time.

**Q8.** When handling critical tasks that must not be lost, which policy should you evaluate first?  
**Answer:** `AbortPolicy` or a custom fail-fast handler paired with appropriate retries, backpressure, or durable handoff. No handler alone provides durability.

**Q9.** Does replacing exceptions with `DiscardPolicy` make the executor stronger?  
**Answer:** No. It only hides rejections and drops work. You must address capacity, queue sizing, producer rate, and load measurement.

**Q10.** Is `Future.isDone()` being `false` after `pool.awaitTermination(...)` returns `true` a contradiction?  
**Answer:** No, if the `FutureTask` was silently discarded from the queue without running or being cancelled. The pool has no remaining managed tasks, yet the external `Future` remains pending.

**Q11.** Why can a new submission after `shutdown()` be rejected even when the queue is empty?  
**Answer:** Because the executor has stopped accepting new work; rejection is not caused solely by a full queue.

**Q12.** When a task in the pool fails after being accepted, what kind of error does the caller receive?  
**Answer:** With `submit()`, `Future.get()` typically throws `ExecutionException` wrapping the cause, which is distinct from `RejectedExecutionException` at submission time when a task is not accepted.

## 24. Summary

The four standard **RejectedExecutionHandler** implementations of `ThreadPoolExecutor` make **four very different decisions** when an executor cannot accept a task:

- **AbortPolicy:** reports an error explicitly, suitable when the producer must take responsibility for handling unaccepted work.
- **CallerRunsPolicy:** runs the task on the submitting thread while the pool is active; creates a form of backpressure but affects latency, execution context, and concurrency caps.
- **DiscardPolicy:** silently drops the new task; only appropriate when loss is an explicitly accepted part of the specification.
- **DiscardOldestPolicy:** removes the queue head and retries accepting the new task; can lose waiting tasks and leave the evicted task's `Future` hanging forever.

To apply them correctly, always consider **queue type, core/max workers, shutdown state, Futures, ordering/dependencies, thread confinement, metrics, and business responsibility for lost tasks**. A rejection policy does not fix overload or guarantee data durability by itself; it only determines how the system reacts at the point of overload or when it stops accepting work.
