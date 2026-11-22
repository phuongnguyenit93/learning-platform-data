# Work queue: ArrayBlockingQueue and LinkedBlockingQueue in the Executor Framework

When calling `execute()` or `submit()` on a `ThreadPoolExecutor`, not every task immediately gets a thread to run on. If the existing workers are busy, the executor can place unstarted `Runnable` tasks into a **work queue**. Two important queue implementations in Java are `ArrayBlockingQueue` and `LinkedBlockingQueue`. Differences in **capacity**, **element storage**, and the task admission algorithm of `ThreadPoolExecutor` affect the number of workers created, queue latency, memory usage, and task rejection decisions under overload.

- `ArrayBlockingQueue<E>`: a FIFO queue backed by a **fixed-capacity array** specified at construction time.
- `LinkedBlockingQueue<E>`: a FIFO queue using a linked structure; it has a **bounded** constructor and a default constructor with capacity **`Integer.MAX_VALUE`**, often described as *effectively unbounded*.
- Both implement `BlockingQueue<E>`, providing blocking and non-blocking methods when inserting or retrieving elements.
- In `ThreadPoolExecutor`, **a full work queue does not mean the submitting thread will block and wait**. The executor normally uses `offer()`: if it fails, it tries to create additional workers up to `maximumPoolSize`; if it cannot, it applies the `RejectedExecutionHandler`.

This article covers Java concurrency and the JDK Executor Framework without other frameworks. Standalone examples use JDK 17+.

## 1. What does a work queue do in an executor?

A simple view:

```text
execute(task) / submit(task)
           |
           v
    ThreadPoolExecutor
       /        \
      v          v
   Workers    BlockingQueue<Runnable>
   run tasks  holds unstarted tasks
      ^          |
      +----------+
           |
           v
  Rejection if unable to accept work
```

**Running tasks** belong to workers; **waiting tasks** reside in the queue. The queue may hold `Runnable` instances submitted by the caller or wrapper tasks created by `submit()`. A task queued for a long time still holds references to the data/objects it captures; therefore, a continuously growing queue can cause **GC pressure**, increase wait times, and lead to heap exhaustion.

Pool configuration parameters typically include:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(10),
        new ThreadPoolExecutor.AbortPolicy()
);
```

This is an **illustrative snippet** and requires importing `java.util.concurrent.*`. The pool has a target minimum of `corePoolSize = 2` workers when tasks arrive, a maximum of `maximumPoolSize = 4` workers, and a queue holding at most 10 tasks not yet taken by workers. `AbortPolicy` throws `RejectedExecutionException` if the task cannot be accepted.

**Important:** the constructor does not pre-start all core threads. Workers are normally created on demand; `prestartCoreThread()` or `prestartAllCoreThreads()` are available if pre-creation is needed.

## 2. Key BlockingQueue API

`BlockingQueue<E>` clearly distinguishes behavior when the queue is **full** or **empty**:

| Operation | When possible | When not yet possible |
|---|---|---|
| `add(e)` | Inserts the element and returns `true`. | Throws `IllegalStateException` if full. |
| `offer(e)` | Inserts and returns `true`. | Returns `false` immediately if full. |
| `put(e)` | Inserts the element. | **Waits** until space is available; may be interrupted. |
| `offer(e, timeout, unit)` | Waits up to the limit, then inserts. | Returns `false` on timeout, or throws `InterruptedException`. |
| `remove()` | Retrieves and removes the head element. | Throws `NoSuchElementException` if empty. |
| `poll()` | Retrieves and removes the head element. | Returns `null` immediately if empty. |
| `take()` | Retrieves the element. | **Waits** until data is available; may be interrupted. |
| `poll(timeout, unit)` | Waits up to the limit, then retrieves. | Returns `null` on timeout, or throws if interrupted. |
| `peek()` | Views the head element without removing. | Returns `null` if empty. |

Both queues disallow `null` elements; a `null` result from `poll()` can therefore indicate that no item is available. `size()` and `remainingCapacity()` only describe the state at the **moment of reading**. Do not write `if (remainingCapacity() > 0) add(item)` assuming the operation will definitely succeed: another producer can interleave. Call `offer()` or `put()` directly according to the contract.

In producer–consumer patterns, `put()` and `take()` are often useful; in the normal task admission path of `ThreadPoolExecutor`, the executor uses `offer()` so as not to block the caller at the queue.

## 3. ArrayBlockingQueue: fixed array and explicit capacity

Creating a bounded queue:

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(100);
```

This is a snippet and requires importing `BlockingQueue` and `ArrayBlockingQueue`. The capacity of 100 is fixed at creation and does not grow automatically. When all 100 slots are full: `offer()` returns `false`; `put()` waits; `offer(timeout, ...)` can wait up to the timeout.

Characteristics:

- **FIFO:** elements in the queue are taken in enqueue order; this does not guarantee that tasks are executed by multiple workers and **completed** in the exact same order.
- **Array allocated by capacity:** does not allocate a new linked node per element like a linked structure. Overall performance depends on workload and contention, so one should not conclude "array is always faster".
- **Optional fairness:** `new ArrayBlockingQueue<>(capacity, true)` requests a fair policy when threads contend for queue access, typically trading off throughput. It does **not** guarantee overall fairness of `ThreadPoolExecutor`.
- **Bounded backlog:** helps limit the number of **waiting** tasks and makes overload visible via queue full/rejection.

When using a bounded queue, you must decide how to handle cases where the pool reaches `maximumPoolSize` and the queue runs out of space. A bounded queue does **not** mean every task will be accepted.

## 4. LinkedBlockingQueue: explicit bound or very large capacity

Two constructors:

```java
BlockingQueue<Runnable> defaultCapacity =
        new LinkedBlockingQueue<>();

BlockingQueue<Runnable> bounded =
        new LinkedBlockingQueue<>(100);
```

This is a snippet and requires importing `java.util.concurrent.*`.

- Without capacity: `LinkedBlockingQueue` defaults to capacity `Integer.MAX_VALUE`. "Unbounded" is shorthand; it does not mean infinite RAM. If tasks are submitted continuously faster than they are processed, the queue can consume a large amount of heap before hitting the integer limit.
- With capacity: the queue holds at most that many elements. With `LinkedBlockingQueue<>(100)`, `offer()` returns `false` when 100 elements are already in the queue waiting to be taken.
- Uses linked nodes, incurring memory/allocation overhead per element and implementation details. There is no `fair` constructor like `ArrayBlockingQueue`.
- FIFO by enqueue order. With multiple threads submitting concurrently, acceptance order depends on scheduling, not necessarily the order of caller log lines.

**Key difference in an executor:** the default `LinkedBlockingQueue<>()` usually **accepts nearly every incoming task after core workers into the queue**, giving the executor no reason to grow workers up to `maximumPoolSize` in the normal admission path. A bounded `LinkedBlockingQueue<>(boundedCapacity)`, when full, **can also cause the pool to create additional workers**, just like a bounded `ArrayBlockingQueue`.

## 5. Example 1 — Observing bounded capacity through the queue API

Create the file **`BlockingQueueBasics.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class BlockingQueueBasics {
    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> array =
                new ArrayBlockingQueue<>(1);
        System.out.println("Array offer A: " + array.offer("A"));
        System.out.println("Array offer B: " + array.offer("B"));
        System.out.println("Array size: " + array.size());
        System.out.println("Array take: " + array.take());

        LinkedBlockingQueue<String> linked =
                new LinkedBlockingQueue<>(2);
        System.out.println("Linked offer X: " + linked.offer("X"));
        System.out.println("Linked offer Y: " + linked.offer("Y"));
        System.out.println("Linked offer Z: " + linked.offer("Z"));
        System.out.println("Linked remaining: "
                + linked.remainingCapacity());

        List<String> removed = new ArrayList<>();
        linked.drainTo(removed);
        System.out.println("Drained: " + removed);
        System.out.println("Linked size: " + linked.size());
    }
}
```

```bash
javac BlockingQueueBasics.java
java BlockingQueueBasics
```

Output:

```text
Array offer A: true
Array offer B: false
Array size: 1
Array take: A
Linked offer X: true
Linked offer Y: true
Linked offer Z: false
Linked remaining: 0
Drained: [X, Y]
Linked size: 0
```

This single-threaded example intentionally uses `offer()` when the queue is full so the program **does not hang** as `put()` would. `drainTo()` transfers currently available items into a list **without waiting** for new data. Both `ArrayBlockingQueue` and `LinkedBlockingQueue` support `BlockingQueue` operations; the takeaway here is how capacity causes `offer()` to fail.

## 6. Admission rules: core → queue → maximum → rejection

When a caller invokes `ThreadPoolExecutor.execute(command)`, the typical operating model is:

1. If the worker count is **less than `corePoolSize`**, the pool tries to create a new worker to run the task.
2. Once core is reached, the pool tries **`workQueue.offer(command)`**.
3. If `offer` succeeds, the task waits in the queue for a worker. The pool also **rechecks running/shutdown state** and worker availability to handle concurrent races.
4. If the queue rejects the task, the pool tries to create additional workers up to **`maximumPoolSize`**.
5. If no worker can be added or the executor is shut down, `RejectedExecutionHandler` is invoked.

```text
                    execute(task)
                         |
                 workers < core ?
                    /         \
                  yes         no
                   |           |
              create worker   queue.offer(task)?
                                 /           \
                               yes           no
                                |             |
                            queue waits   workers < max?
                                            /       \
                                          yes       no
                                           |         |
                                      create worker  reject
```

This is a simplified model; actual decisions must handle concurrent shutdown and worker count changes.

**An often-overlooked consequence:** `maximumPoolSize` usually **only takes effect when the queue can no longer accept tasks**. If the queue has a very large capacity, many tasks will wait in the queue while the worker count stays near `corePoolSize`. Increasing maximum from 4 to 100 **will not automatically drain** a growing queue if a default `LinkedBlockingQueue` keeps accepting tasks.

Example with `core=1`, `max=2`, queue capacity 1:

- 1st task → creates core worker.
- 2nd task → goes into queue.
- 3rd task → queue is full, creates second worker.
- 4th task → if both workers are busy and queue is still full, **rejected**.

**Do not confuse** `newFixedThreadPool(n)` with a bounded queue: the standard implementation uses an unbounded `LinkedBlockingQueue` relative to application scale, so load exceeding processing capacity can build a large backlog; choose factories/configurations suited to your goals.

## 7. Example 2 — Bounded ArrayBlockingQueue triggers extra worker creation

Use `CountDownLatch` to keep tasks #1 and #3 running while task #2 sits in the queue. This lets us verify the exact step at which the pool opens an extra worker without relying on thread scheduler luck.

Create the file **`ExecutorBoundedAdmission.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorBoundedAdmission {
    static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                firstStarted.countDown();
                awaitRelease(release);
            });
            firstStarted.await();

            executor.execute(() -> { }); // Second task waits in the queue.

            executor.execute(() -> {
                thirdStarted.countDown();
                awaitRelease(release);
            });
            thirdStarted.await();

            System.out.println("Pool size: " + executor.getPoolSize());
            System.out.println("Active workers: " + executor.getActiveCount());
            System.out.println("Queued tasks: " + executor.getQueue().size());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed tasks: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac ExecutorBoundedAdmission.java
java ExecutorBoundedAdmission
```

Output in a normal run without external interruption:

```text
Pool size: 2
Active workers: 2
Queued tasks: 1
Terminated: true
Completed tasks: 3
```

Task #1 occupies the core worker and waits on the latch; task #2 is queued because the queue has space; task #3 causes `offer()` to fail because the queue is full, so the pool creates a second worker (not exceeding max). `main` waits for both tasks #1 and #3 to reach the running state before reading metrics, so the queue still holds task #2. When `release.countDown()` runs, the executor completes all accepted tasks and shuts down as contracted.

In real applications, `getActiveCount()` and queue size are diagnostic values that can change instantaneously; in this example they are stable because the latches hold the tasks.

## 8. Example 3 — Default LinkedBlockingQueue keeps tasks in the queue

Use a pool with `corePoolSize=1`, `maximumPoolSize=3`, and a `LinkedBlockingQueue<>()` with default capacity. While the core worker is busy, the next two tasks **are enqueued**; the pool normally does not open extra workers.

Create the file **`ExecutorUnboundedQueue.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorUnboundedQueue {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 3, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            executor.execute(() -> { });
            executor.execute(() -> { });

            System.out.println("Pool size: " + executor.getPoolSize());
            System.out.println("Active workers: " + executor.getActiveCount());
            System.out.println("Queued tasks: " + executor.getQueue().size());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed tasks: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac ExecutorUnboundedQueue.java
java ExecutorUnboundedQueue
```

Output:

```text
Pool size: 1
Active workers: 1
Queued tasks: 2
Terminated: true
Completed tasks: 3
```

Only the core worker is created because the queue accepts the new tasks successfully. `maximumPoolSize=3` is a ceiling, **not a target to automatically scale to three workers**. If changed to `new LinkedBlockingQueue<Runnable>(1)`, the queue can fill up and the pool can then open non-core workers just like in the `ArrayBlockingQueue` example.

## 9. Saturation and RejectedExecutionHandler

When workers reach max and the queue is full, the executor uses a rejection policy:

| Policy | Behavior | Notes |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException`. | Default; caller must handle the error or bound retries. |
| `CallerRunsPolicy` | If the executor is not shut down, runs the task directly on the **thread calling `execute()`**. | Can provide backpressure but slows down the caller; once shut down, tasks may be discarded. |
| `DiscardPolicy` | Silently drops the task without throwing. | Use only when losing work is acceptable. |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries `execute`. | Can lose waiting work; not suitable for every policy/queue. |

A bounded queue limits backlog but **does not automatically provide the desired backpressure**. Choose a policy intentionally: observable errors, caller-runs where appropriate, bounded retries, or throttling the task producer.

### Example 4 — CallerRunsPolicy runs the task on the submitting thread

Create the file **`CallerRunsBackpressure.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsBackpressure {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );
        Thread caller = Thread.currentThread();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ranOnCaller = new AtomicBoolean();

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            executor.execute(() -> { }); // One task in the queue.
            executor.execute(() -> {
                ranOnCaller.set(Thread.currentThread() == caller);
            });

            System.out.println("Third ran on caller: "
                    + ranOnCaller.get());
        } finally {
            release.countDown();
            executor.shutdown();
        }

        boolean terminated = executor.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Pool completed: "
                + executor.getCompletedTaskCount());
    }
}
```

```bash
javac CallerRunsBackpressure.java
java CallerRunsBackpressure
```

Output in a normal run:

```text
Third ran on caller: true
Terminated: true
Pool completed: 2
```

The third task runs **synchronously on the caller**, not on a pool thread. Therefore `getCompletedTaskCount()` only counts the two tasks completed by workers, not the task that ran outside the pool. If the caller is a latency-sensitive request thread or an event loop, `CallerRunsPolicy` can stall request ingestion. Consider the context before choosing it.

## 10. Queue FIFO is not completion FIFO

Both queues have FIFO semantics for elements **already in the queue**. However, `ThreadPoolExecutor` does not promise that "a task submitted earlier always completes earlier":

- With multiple workers, a task that starts earlier may take longer than a task that starts later.
- If a bounded queue is full, a new task may be handed **directly to a non-core worker** even while older tasks remain in the queue. In the `core=1, max=2` pool example, task #3 can start before task #2.
- Concurrent callers submitting tasks produce an enqueue order that depends on scheduling.
- `CallerRunsPolicy` runs the task on the submitter rather than through the worker queue.

If business requirements demand strict ordering, design explicit serialization/ordering. A single-thread executor eliminates parallel worker execution, though rejection policies, cancellation, and callbacks outside the executor still need consideration; do not infer completion ordering solely from `BlockingQueue`'s FIFO nature.

## 11. When to choose ArrayBlockingQueue or LinkedBlockingQueue?

| Criterion | `ArrayBlockingQueue` | `LinkedBlockingQueue` |
|---|---|---|
| Storage | Fixed-capacity array. | Linked node per element. |
| Default capacity | Must be specified. | `Integer.MAX_VALUE` when omitted. |
| Bounded | Always bounded. | Bounded if capacity is specified. |
| FIFO | Yes. | Yes. |
| `put/take/offer/poll` | Yes. | Yes. |
| Fairness in constructor | Has `fair` option. | No equivalent option. |
| Full-queue effect on executor | Can create workers up to max, then reject. | Same **if bounded**; default is unlikely to fill before memory becomes an issue. |
| Maintenance/performance | Predictable slot memory; low node allocation overhead. | Has node overhead and unbounded growth risk if unconfigured; measure on real workloads. |

**Choose capacity before choosing implementation.** If the goal is a clear memory/latency budget, both `ArrayBlockingQueue<>(n)` and `LinkedBlockingQueue<>(n)` provide a bound. Performance/locking differences between implementations should be measured on real workloads; there is no rule that "Linked is always faster than Array".

## 12. Designing capacity, throughput, and backpressure

Suppose a system receives **500 tasks/second** while steady-state workers only process **300 tasks/second**. During overload, the backlog grows by roughly **200 tasks/second**. Increasing queue capacity only **delays** when it fills up; it does not add processing capacity, and tasks queued too long may miss their business deadlines before running.

An overly large queue typically causes:

- Increased latency before tasks start executing.
- Retaining large numbers of objects referenced by tasks, increasing memory usage and GC.
- Masking overload instead of forcing callers to slow down.
- Cancelled or obsolete tasks remaining in the queue waiting to be processed.

A queue that is too short paired with a small `maxPoolSize` may reject early; this is not necessarily wrong if the sender policy knows how to shed load. A larger bounded queue and higher max do not automatically mean better throughput: too many workers contending for CPU, database connections, or external systems can make things slower.

When tuning parameters, monitor **arrival rate**, **service rate**, task queue wait time, execution time, active workers, queue depth, rejection count, heap, and p95/p99 latency. For CPU-bound tasks, worker count should generally match CPU resources; for I/O-bound tasks, worker count may differ but is still constrained by downstream systems and memory.

## 13. Do not manipulate the work queue directly as a submit API

`executor.getQueue()` allows inspecting the queue. However, you should not call `executor.getQueue().put(task)` to submit work, because doing so can **bypass `execute()`'s mechanisms**: shutdown checks, worker creation, rejection policies, and task management logic.

Use `execute()` or `submit()` to submit tasks. Metrics such as:

```java
int queued = executor.getQueue().size();
int active = executor.getActiveCount();
long completed = executor.getCompletedTaskCount();
int capacity = executor.getQueue().remainingCapacity();
```

are snippets requiring a declared `executor`, and are **instantaneous/approximate observations**, not atomic decision-making protocols. Do not write `if (getQueue().size() < limit) executor.execute(...)` assuming space is guaranteed: state can change before `execute()` runs.

`drainTo()` does not "wait for the executor to finish all tasks"; it moves remaining elements from the queue into a target collection. Directly manipulating the queue to remove/cancel items requires great care as it can break completion/observation contracts for callers.

## 14. Shutdown, cancellation, and queued tasks

An executor does not "close" its work queue with a generic `BlockingQueue.close()` call. The owner manages lifecycle via:

- `shutdown()`: stops accepting new tasks; already accepted tasks are allowed to run to completion.
- `shutdownNow()`: attempts to interrupt running tasks, stops processing waiting tasks, and returns unstarted tasks; does not guarantee threads will stop immediately.
- `awaitTermination(timeout, unit)`: waits for the pool to actually terminate, returning a boolean indicating whether it completed before the timeout.
- `Future.cancel(true)`: requests task cancellation; for a running task it may attempt to interrupt, but does not guarantee cleanup has finished when the method returns.
- `getQueue().size()` only reports the current backlog, not tasks currently executing.

Cancelled tasks may remain held in the queue until polled or cleaned up by an appropriate mechanism. `ThreadPoolExecutor.purge()` can remove some cancelled `Future` tasks from the queue, but it is not a substitute for proper capacity and lifecycle management. Tasks holding large objects while queued must be accounted for in memory budgets.

With `submit()`, task exceptions are captured in the `Future` and typically observed via `get()`; with `execute()`, how exceptions affect workers and where errors are handled differs. Do not design systems that treat a non-full queue as proof that a task will succeed.

## 15. Java Memory Model and handoff via BlockingQueue

`BlockingQueue`'s memory consistency contract provides a **happens-before** relationship: actions in a producer **prior to placing an object into a queue** happen-before actions in a consumer **subsequent to accessing/removing that object**. This enables safe handoff of data constructed before enqueueing.

Conceptual example:

```java
// Producer:
Message message = new Message();
message.value = 42;
queue.put(message);

// Consumer in another thread:
Message result = queue.take();
System.out.println(result.value);
```

This is a **snippet** requiring a `Message` class and an appropriate queue, not a standalone program. You do not need `volatile` on every payload field just for **proper one-way** handoff through a queue. However, if the producer continues mutating the same object after enqueueing while the consumer reads it, the queue's happens-before edge does not protect against those concurrent mutations; prefer immutable payloads or clear ownership transfer rules.

For an executor, submitted tasks typically carry references to the data they need. Data safety across workers still relies on the Java Memory Model and proper synchronization protocols; the queue does not make every captured mutable object thread-safe.

## 16. Checklist and self-check

Checklist before deploying an executor to production:

1. Determine `corePoolSize`, `maximumPoolSize`, arrival rate, and task execution time.
2. Choose a bounded or effectively unbounded queue **intentionally**, not by default out of convenience.
3. Estimate memory and wait latency based on queued task count and the object graphs they retain.
4. Understand admission: **core → offer queue → maximum → rejection**.
5. Choose `RejectedExecutionHandler` explicitly; handle overload according to business contracts.
6. Do not rely on FIFO queues as a promise of execution/completion order.
7. Do not submit tasks via `getQueue().add()`/`put()`.
8. Manage shutdown, cancellation, timeouts, and cleanup.
9. Monitor queue depth, active workers, rejections, task duration, and GC.
10. Stress-test blocked tasks, full queues, and concurrent executor shutdown.

Self-check questions:

1. **Does ArrayBlockingQueue have a no-argument constructor without capacity?** No, capacity must be specified at creation.
2. **What is the capacity of a no-argument LinkedBlockingQueue?** `Integer.MAX_VALUE` — not infinite RAM.
3. **Can LinkedBlockingQueue be bounded?** Yes, using the constructor that accepts a capacity.
4. **Why might `maximumPoolSize=20` still only use 2 workers?** Because the queue continues accepting tasks after the 2 core workers are busy, so there is no reason to open non-core workers in the normal admission path.
5. **Does the executor call `queue.put(task)` and block the caller when the queue is full?** The normal admission path uses `offer()`; a full queue causes the pool to try creating additional workers or reject.
6. **Does a FIFO queue guarantee task completion order?** No, because multiple workers, varying task durations, and new tasks handed directly to workers can reorder completion.
7. **How can CallerRunsPolicy create backpressure?** Rejected tasks can run directly on the caller, preventing the caller from submitting more tasks until the task finishes.
8. **When `shutdown()` is called, are all tasks already in the queue automatically discarded?** No. `shutdown()` allows already accepted tasks to run until the executor terminates; `shutdownNow()` is the mechanism that attempts to stop them.
9. **Is reading `remainingCapacity()` and then calling `add()` safe under contention?** No; use `offer()` or `put()` according to the contract.
10. **Why can a very large queue slow down a system and exhaust the heap?** Backlog retains objects in RAM and increases queue wait time without increasing the service rate.

**Key takeaway:** `ArrayBlockingQueue` is always bounded; `LinkedBlockingQueue` can be bounded but defaults to a very large capacity. In `ThreadPoolExecutor`, understand **core → queue.offer → maximum → rejection** to choose the queue, capacity, and policy that fit your resource and latency budgets.
