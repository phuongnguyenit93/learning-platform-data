# ForkJoinPool asyncMode: FIFO mode for unjoined event-style tasks

## 1. Objectives and scope

After this lesson, you can:

- Explain **ForkJoinPool.asyncMode**, the difference between the **default LIFO** and **FIFO in the local deque** of a ForkJoin worker.
- Distinguish tasks **forked from a worker**, tasks **submitted from an external thread**, the **work stealing** mechanism, and **unjoined event-style** tasks.
- Instantiate a Java 17+ ForkJoinPool with asyncMode=true using the four-parameter constructor; know how to check it with getAsyncMode().
- Recognize that **local FIFO is not global FIFO**, and does not guarantee start or completion order in a pool with multiple workers.
- Choose between the divide-and-conquer model with join and unjoined event-style tasks; organize completion, error reporting, and shutdown when the parent does not wait for each child.
- Evaluate task creation overhead, pending task count, blocking, memory visibility, cancellation, and ThreadLocal assumptions.
- Compile/run Java 17+ examples with verifiable stdout, and distinguish a controlled test from benchmark results.

The scope is **general Java concurrency**, under the parent topic **Fork/Join**. Spring-specific APIs and configurations are covered in another chapter.

## 2. ForkJoinPool and worker deques

**ForkJoinPool** is an ExecutorService with mechanisms for handling ForkJoinTask and **work stealing**. Tasks can be split from a parent task, placed where a worker can process them, or stolen by another worker when it needs work.

Key concepts:

| Component | Role |
| --- | --- |
| ForkJoinPool | Pool that manages workers and tasks |
| ForkJoinWorkerThread | Worker that executes the pool's tasks |
| ForkJoinTask<V> | Task with completion/result |
| RecursiveTask<V> | Task that returns a result |
| RecursiveAction | Task that does not return a result |
| fork() | Allows a child task to be executed asynchronously |
| join() | Waits for and receives the result of a task |
| work stealing | An idle worker takes work from another worker |
| asyncMode | Configures how unjoined event-style local tasks are prioritized |

One **task does not equal one thread**. Four workers can execute thousands of tasks through thread reuse. However, tasks also have object, queue, fork/join, and scheduling overhead; changing asyncMode does not eliminate this overhead.

~~~text
                      ForkJoinPool
                     /      |      \
                Worker 1  Worker 2  Worker 3
                 deque     deque     deque
                   |         |         |
                 local     local     local
                   +------ steal ------+

A worker forks a child -> the child can go into the local deque.
An external thread submits -> external submission path.
~~~

This is an intuitive diagram, not a fixed memory structure model guaranteed by the JDK for every version. Focus on the **local mode** contract, **stealing** capability, and **completion**.

## 3. Default LIFO and FIFO in asyncMode

Suppose a parent task is running on worker W and forks A, B, C in sequence:

~~~text
Parent on Worker W:
  fork(A);
  fork(B);
  fork(C);

Pending local tasks:
  A | B | C
~~~

In the situation where the children are still in the local deque, not yet stolen or directly joined:

- **asyncMode=false:** the worker prioritizes **LIFO**; the most recently forked child is usually taken first, for example **C, B, A**.
- **asyncMode=true:** the worker prioritizes **FIFO** for tasks forked **without joining**; the oldest child is taken first, for example **A, B, C**.
- **Other workers:** can steal tasks and run them in parallel, without having to follow the same completion order as worker W.

LIFO is useful for divide-and-conquer trees, where the parent typically forks one child, computes the remaining branch itself, and then joins. FIFO can be suitable for **event-style forked tasks that are never joined**, meaning tasks that are dispatched and monitored separately rather than combined into the parent's direct return value.

### Do not infer system-wide FIFO

There are at least three different orders: **fork order**, **execution start order**, and **completion order**. asyncMode only affects the local task-picking policy in the pool; it does not merge all three orders into one.

For example, A starts before B, but A takes 200 ms while B takes only 2 ms; in a pool with two workers, B can still complete before A.

## 4. Creating a ForkJoinPool in Java 17+

The four-parameter constructor:

~~~java
// Illustrative snippet inside a class/method with imports.
ForkJoinPool fifo = new ForkJoinPool(
        4,
        ForkJoinPool.defaultForkJoinWorkerThreadFactory,
        null,
        true
);
~~~

Parameters:

| Parameter | Description |
| --- | --- |
| parallelism=4 | Target parallelism level; not a guarantee that exactly four threads are always running |
| factory | Factory that creates ForkJoinWorkerThread; here the default is used |
| handler=null | No custom uncaught exception handler specified for workers |
| asyncMode=true | Selects the local FIFO policy for unjoined event-style tasks |

Creating the default mode:

~~~java
ForkJoinPool normal = new ForkJoinPool(4);
~~~

**new ForkJoinPool(4)** uses asyncMode=false. The **getAsyncMode()** API returns the boolean configuration of the pool, not proof that every task ran in global FIFO order.

There is no common setter to change asyncMode on an already-created pool; if you need to compare, create two separate pools with clear lifecycles. **ForkJoinPool.commonPool()** is a shared pool; do not assume you can enable FIFO on it via a setter or shut it down after finishing a request.

### Relating to the constructor's asyncMode

The name asyncMode does not mean every submit becomes nonblocking, tasks run in parallel automatically, or the entire queue is FIFO. The effect to pay attention to is the **local scheduling mode** for **forked, unjoined** tasks.

## 5. Example 1: observing LIFO/FIFO in a controlled way

To eliminate work stealing from the experiment, create a pool with **parallelism=1**. One parent is executed by the single worker, forks A, B, C, and then finishes **without joining**. The single worker then processes the children according to its local mode.

File **ForkJoinAsyncModeOrderDemo.java**:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;

public class ForkJoinAsyncModeOrderDemo {
    static String run(boolean asyncMode)
            throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(
                1,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                asyncMode
        );
        CountDownLatch done = new CountDownLatch(3);
        ConcurrentLinkedQueue<String> events =
                new ConcurrentLinkedQueue<>();

        try {
            pool.execute(() -> {
                for (String value : new String[] {"A", "B", "C"}) {
                    ForkJoinTask.adapt(() -> {
                        events.add(value);
                        done.countDown();
                    }).fork();
                }
                // Parent does not join the children.
            });

            done.await();
            return String.join("", events);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("default LIFO = " + run(false));
        System.out.println("async FIFO = " + run(true));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinAsyncModeOrderDemo.java
java ForkJoinAsyncModeOrderDemo
~~~

Expected stdout under the single-worker demonstration condition:

~~~text
default LIFO = CBA
async FIFO = ABC
~~~

**Why is this test meaningful?**

1. The parent performs all three forks before finishing its own work.
2. There is no second worker to steal and run a child before the parent finishes.
3. By the time the single worker picks a child, all of them are already in the local deque.
4. Default LIFO usually picks C, B, A; FIFO mode picks A, B, C.
5. CountDownLatch waits for all three children, without relying on sleep or a guessed duration.
6. ConcurrentLinkedQueue records results safely; after await, main can join the string.

**Do not promote a single-worker result into an SLA:** in a multi-worker pool, tasks can be stolen and run concurrently; completion order is not guaranteed to be ABC even with asyncMode=true.

## 6. Fork and submit are different

When a task running **inside a worker** calls **ForkJoinTask.fork()**, the child task is attached to the pool/worker's work management mechanism, specifically the local deque.

When **a main/request thread calls pool.submit()**, the work enters the **external submission** path. It cannot be assumed to be "A then B then C in a local deque of the main thread". Workers can pick up and run multiple external tasks in parallel.

| Action | Source | What can be concluded? |
| --- | --- | --- |
| Worker forks child | Pool worker | Can leverage the local queue and work stealing |
| Main submits Callable | Thread outside the pool | Future to retrieve the result; no global FIFO completion |
| Parent joins child | Task with dependency | Parent waits for/receives child's result |
| Parent forks and forgets child | Unjoined event | Must have a separate completion/error channel if important |

**Local FIFO is not FIFO across all submit calls from all producers.**

### Example 2: external submit, result independent of execution order

File **ForkJoinExternalSubmitDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class ForkJoinExternalSubmitDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                2,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        try {
            Future<Integer> a = pool.submit(() -> 20);
            Future<Integer> b = pool.submit(() -> 22);

            System.out.println("async = " + pool.getAsyncMode());
            System.out.println("sum = " + (a.get() + b.get()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinExternalSubmitDemo.java
java ForkJoinExternalSubmitDemo
~~~

Stdout:

~~~text
async = true
sum = 42
~~~

The two Callables can start on different schedules; the example only prints the **pool configuration** and **sum of results** after Future.get(), so stdout is deterministic. The caller calling a.get() then b.get() does not prove B waited for A before starting: both were already submitted.

## 7. Even without joining, you still need to know when a task completes

Classic divide-and-conquer pattern:

~~~text
parent -> fork(child) -> compute(other) -> join(child) -> combine
~~~

Event-style pattern:

~~~text
dispatcher -> fork(A), fork(B), fork(C) -> parent returns
                                      |
                         children run/complete separately
~~~

"Not joining" means **the parent does not directly wait for each child**, not that the event has already completed when fork() returns. If the business logic requires guarantees, you must have a protocol:

- **CountDownLatch** when N events are known and you only need a completion milestone.
- **Future** when you need to return a result or report an error for each task.
- **Phaser** for dynamically registered task groups and more complex phases.
- **Queue/message completion** if results need to be delivered to a consumer.
- **Ack, retry, idempotency, or persistent queue** if it must survive JVM restarts.

**Do not treat fire-and-forget as exactly-once execution.** A failed task, JVM crash, or shutdown can still lose side effects or leave partial state.

## 8. Example 3: unjoined events and a separate result channel

The parent forks three events, where event 2 intentionally fails. The parent does not join, but each child handles errors and counts completion in finally. Lesson: FIFO does not replace **completion/error reporting**.

File **UnjoinedEventsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class UnjoinedEventsDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                2,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        CountDownLatch done = new CountDownLatch(3);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        try {
            pool.execute(() -> {
                for (int eventId = 1; eventId <= 3; eventId++) {
                    final int id = eventId;

                    ForkJoinTask.adapt(() -> {
                        try {
                            if (id == 2) {
                                throw new IllegalStateException("bad event");
                            }
                            success.incrementAndGet();
                        } catch (RuntimeException ex) {
                            failures.incrementAndGet();
                        } finally {
                            done.countDown();
                        }
                    }).fork();
                }
            });

            done.await();

            System.out.println("success = " + success.get());
            System.out.println("failure = " + failures.get());
            System.out.println("all observed = " + (done.getCount() == 0));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnjoinedEventsDemo.java
java UnjoinedEventsDemo
~~~

Stdout:

~~~text
success = 2
failure = 1
all observed = true
~~~

**Analysis:**

1. The parent does not keep a reference to the children and does not join.
2. Each child always calls done.countDown() in finally.
3. Child 2 intentionally throws an exception, but records failures inside the child itself.
4. AtomicInteger provides accurate counts when multiple workers run in parallel.
5. Main uses done.await() to know all three tasks have passed the completion point.
6. The output only reflects the **aggregate**, independent of the order in which events complete.

CountDownLatch only signals **enough countDown calls**, and does not automatically distinguish success/failure. If individual results are needed, you must store the result or use a stateful Future/ack.

### What if a child throws an uncaught error?

ForkJoinTask stores exceptional completion state according to its contract. If the parent drops the reference and does not join/get, it will not automatically receive the exception, and there is no guarantee the system has observed the error. **A worker's UncaughtExceptionHandler is not the sole reliable error-reporting channel** for every error from a ForkJoinTask.

Therefore, events need a controlled error channel, especially if there are retries, DB updates, or external service calls.

## 9. asyncMode does not disable join

A pool with asyncMode=true can still run **RecursiveTask** and use join normally. asyncMode does not change the computation or data dependencies: **the parent only combines after the child completes**.

Standard pattern:

~~~java
// Illustrative snippet inside compute() of RecursiveTask<Long>.
left.fork();
long rightResult = right.compute();
long leftResult = left.join();
return leftResult + rightResult;
~~~

This snippet assumes left/right are valid RecursiveTask<Long> instances. **Fork one branch, compute one branch, join** is a useful idiom to avoid unnecessarily enqueuing every branch.

**Do not design a join algorithm assuming the deque will always be FIFO or LIFO:** join has its own dependency completion mechanism and other workers can steal.

### Example 4: join results remain correct in both modes

File **ForkJoinJoinedSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinJoinedSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] values;
        private final int from;
        private final int to;

        SumTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= 16) {
                long result = 0;
                for (int i = from; i < to; i++) {
                    result += values[i];
                }
                return result;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long r = right.compute();
            return left.join() + r;
        }
    }

    static long run(boolean asyncMode, int[] values) {
        ForkJoinPool pool = new ForkJoinPool(
                3,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                asyncMode
        );
        try {
            return pool.invoke(new SumTask(values, 0, values.length));
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) {
        int[] values = new int[100];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }

        System.out.println("LIFO sum = " + run(false, values));
        System.out.println("FIFO sum = " + run(true, values));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinJoinedSumDemo.java
java ForkJoinJoinedSumDemo
~~~

Stdout:

~~~text
LIFO sum = 5050
FIFO sum = 5050
~~~

The sum from 1 to 100 is 5050, regardless of the two pools choosing different execution schedules. The example verifies **correctness**, not that the two modes are equally fast. For divide-and-conquer algorithms with frequent joins, start with the default mode and benchmark if needed.

## 10. Event ordering requires dedicated design

If the problem requires:

- Event A to be committed before B for the same account.
- Every mutable variable of a session to be modified by only one owner.
- No duplicate processing of already-committed events after a restart.
- Every consumer to see a strictly ordered sequence.

...then **asyncMode=true does not provide those guarantees**.

Other options:

1. **Single-thread executor** to serialize a stream of tasks within a single JVM.
2. **Partition-by-key**: each key/partition has a sequential owner or queue, while different keys still run in parallel.
3. **Sequence numbers and dependencies**: a subsequent task only commits once the previous task's state is confirmed.
4. **Persistent event queue** and idempotency keys when handling multiple JVMs/restarts.
5. **BlockingQueue and an exclusive consumer** when event-driven processing with clear ownership is needed.

A single-thread executor can execute tasks in queue insertion order, but if multiple producers submit concurrently, you still need to define how business order is established. It also does not automatically provide durability across restarts.

## 11. Work stealing and the difference between start and completion

In a multi-worker pool, even if worker W picks task A before B under local FIFO, worker X can steal B and run it in parallel. If B is lighter, B finishes before A.

~~~text
Worker W: starts A ---------[runs long]----------> A done
Worker X: steals B --> B done
Completion order: B, then A.
~~~

Therefore:

- **Fork order** does not mean **start order**.
- **Start order** does not mean **completion order**.
- **Completion order** does not mean **side-effect commit order** if tasks also perform other I/O.
- **Local FIFO** does not guarantee absolute latency or fairness.

If you want output in index order while processing in parallel, you can store Futures by index, wait for all, and then **collect results by index**. But collecting in order does not mean the tasks ran sequentially.

## 12. ThreadLocal and thread affinity

A child task can run on a different worker than the thread that forked it. Therefore:

- **ThreadLocal** is bound to the executing thread, not to the parent task or ForkJoinPool.
- Do not expect the parent's ThreadLocal to automatically propagate to a stolen child.
- Do not rely on thread names or worker indices as event ordering.
- Tasks should carry the data they need, preferring **immutable payloads**.
- If using ThreadLocal in reused workers, set/clear it per scope using try/finally when appropriate.
- If tasks use a shared mutable object, proper atomic/lock/ownership mechanisms are required; asyncMode does not create thread safety.

**A forked child does not have access to the parent's thread-confined state** unless an appropriate data publication/handoff design is used.

## 13. Safe publication and the Java Memory Model

Tasks must see inputs prepared according to memory-consistency contracts; handing off tasks through Executor/ForkJoin synchronization APIs provides the necessary relationships. However, if the parent **continues modifying a mutable object concurrently with the child**, forking does not make future updates atomic.

~~~text
Parent prepares payload
       |
       +-- fork/submit child
                |
                +-- child reads published payload
                |
                +-- completion / join / Future.get / latch
                                      |
                                  reader uses result
~~~

In the examples:

- **CountDownLatch.countDown()** before **await() completes** establishes a happens-before relationship by contract.
- **AtomicInteger** allows multiple workers to record total successes/failures without lost increments.
- **ConcurrentLinkedQueue** provides a thread-safe queue.
- **join()/Future.get()** are completion points with appropriate synchronization semantics for the caller to consume results.

If each child writes to **non-overlapping** regions of an array and the parent reads after joining all children, per-element locking may not be needed. If two children modify the **same element**, a separate synchronization protocol is required.

## 14. Task count, batching, and backpressure

An event dispatcher can fork millions of small tasks:

~~~java
// Illustrative anti-pattern: do not run this loop.
for (;;) {
    ForkJoinTask.adapt(() -> processEvent()).fork();
}
~~~

This snippet assumes processEvent() is defined. If tasks are generated faster than workers can process them, outstanding tasks and memory usage can grow enormously.

**FIFO does not reduce task count or allocation.** You need:

- **Admission control** to bound the number of unprocessed events.
- **Batching** if each event is too lightweight: one task processes multiple events.
- **Resource-based quotas** (Semaphore, bounded queue, rate limit) if an external service limits concurrency.
- Clear **error/cancel/timeout** handling when the system is overloaded.
- **Metrics for task age/queue backlog**, throughput, failures, and tail latency.
- A policy for handling tasks that are **rejected** or cancelled.

A particular risk: workers holding all resources while **blocking on permits** that only other tasks can release after running can cause deadlock/starvation. Do not use unbounded waiting inside workers as a naive backpressure solution.

## 15. Blocking I/O in ForkJoinPool

ForkJoinPool has mechanisms to support ForkJoinTask and work stealing, but it has no magic to automatically compensate for workers blocked indefinitely by arbitrary I/O.

~~~java
// Illustrative snippet: network read can block.
socket.read(buffer);
~~~

If tasks frequently block for long periods:

- You can offload the workload to a resource-bounded executor dedicated to blocking I/O.
- You can consider **ForkJoinPool.managedBlock(ManagedBlocker)** when you can implement the protocol properly and genuinely need to notify the pool of blocking.
- Do not assume asyncMode=true solves the problem of running out of available workers.
- You must consider connection limits, deadlines, cancellation, throughput, and the impact on commonPool.

**ManagedBlocker** has isReleasable() and block() by contract; it does not guarantee all I/O stops waiting, does not provide transactions, and does not create infinite resources.

## 16. Lifecycle, shutdown, and cancellation

For a **custom pool** created by the application:

| API | Description |
| --- | --- |
| shutdown() | Stops accepting new tasks and proceeds to complete already-accepted tasks |
| shutdownNow() | Attempts to stop execution; does not guarantee forcibly stopping running tasks |
| awaitTermination(timeout, unit) | Waits for the pool to terminate, returns boolean |
| isShutdown() | Checks whether shutdown has been requested |
| isTerminated() | Checks whether the pool has terminated |
| ForkJoinTask.cancel(boolean) | Marks the task cancelled according to ForkJoinTask's own contract |

**ForkJoinTask.cancel(true)** is not a guarantee to interrupt a running worker. For ForkJoinTask, the boolean mayInterruptIfRunning does not carry the guarantee many infer from the parameter name. Long-running tasks need an appropriate cooperative cancellation mechanism.

If a parent forks unjoined children, you must clearly define when it is safe to shut down. **Pool shutdown is not a business success report**. For important side effects, separate acks/results are required.

### Example 5: tasks already accepted before shutdown still produce results

File **ForkJoinAsyncShutdownDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ForkJoinAsyncShutdownDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                1,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> a = pool.submit(() -> {
                started.countDown();
                release.await();
                return 20;
            });

            started.await();
            Future<Integer> b = pool.submit(() -> 22);

            pool.shutdown();
            release.countDown();

            int sum = a.get() + b.get();
            boolean terminated =
                    pool.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("sum = " + sum);
            System.out.println("terminated = " + terminated);
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
javac -encoding UTF-8 ForkJoinAsyncShutdownDemo.java
java ForkJoinAsyncShutdownDemo
~~~

Stdout if both tasks complete under normal conditions:

~~~text
sum = 42
terminated = true
~~~

Main waits for task a to actually start, submits b while a is waiting on the latch, and then calls shutdown. Both tasks were accepted before shutdown; main opens the latch, retrieves both Future results, and waits for the pool to terminate. The example does not claim external tasks started in any order beyond the defined latch points.

If a task is blocked indefinitely or the JVM is heavily overloaded, awaitTermination(5s) can still return false. Always check the boolean when lifecycle policy requires it.

## 17. Comparing three options

| Criterion | Default ForkJoinPool | ForkJoinPool asyncMode=true | Single-thread executor |
| --- | --- | --- | --- |
| Local task scheduling | Usually **LIFO** | **FIFO** for forked/unjoined tasks | Sequential through one worker |
| Divide-and-conquer with join | Natural choice | Still valid, not inherently better | Does not utilize multiple workers |
| Unjoined event-style | Can be used | Intended target of asyncMode | Can be suitable if sequential execution is needed |
| Work stealing | Yes | Yes | Not based on ForkJoin model |
| Global FIFO completion | No | **No** | Each task runs sequentially; still need to define order under concurrent submits |
| Strict per-key owner | Requires additional design | Requires additional design | Can serve as a foundation |
| Backpressure | Requires design | Requires design | Default queue can still grow large |
| Persistence across restarts | No | No | No |

Some events are completely independent and allowed to complete in any order: asyncMode is worth considering. If an account must be updated sequentially, **do not** replace locks/owners with local FIFO.

## 18. Debugging and benchmarking

### What to measure

1. Event or task processing throughput.
2. Latency from fork/submit to start and to completion.
3. Tail latency p95/p99 and long-pending tasks.
4. Actual parallelism, CPU utilization, and blocking time.
5. Allocation rate, GC, and pending task count.
6. Steal count, queued-task estimate within snapshot limitations.
7. Error, cancel, timeout rates, and pending acks.
8. Number of events requiring strict order that actually suffered ordering errors.

**getStealCount(), getQueuedTaskCount(), getActiveThreadCount()** are diagnostic/estimated metrics; do not use them to prove all work is complete or as exact business-condition checks.

### Comparison methodology

- Keep inputs, worker count, task size, and producer rate identical.
- Measure **unjoined forked events** workloads and **recursive with join** workloads separately; the two groups may benefit differently.
- Warm up the JVM/JIT, measure multiple runs; use JMH when serious microbenchmarking is needed.
- Do not treat a single faster run as proof of general superiority.
- If there are many external submissions, analyze the submission path separately; do not attribute every latency change to the local FIFO deque.
- Compare against a serial owner model or standard queue when the specification demands strict ordering.

**Both LIFO and FIFO have trade-offs**; neither mode is "always better".

## 19. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Assuming asyncMode=true = global FIFO | There are multiple deques and work stealing | Only infer local policy; design strict ordering separately |
| Using FIFO to keep mutable state single-owner | Children can run on multiple workers | Appropriate owner/lock/partition |
| Parent forks and returns, assuming all children are done | Fork does not block waiting for completion | Latch/Future/ack |
| Child fails but nobody reads the result | No error channel | Record errors and terminal status |
| External submit from main expecting local FIFO | Not the same as worker-local fork | Avoid inferring ordering |
| Relying on parent's ThreadLocal | Child can be stolen | Pass context explicitly |
| Forking too many tiny tasks | High overhead/GC/queue pressure | Batching/cutoff/admission control |
| Choosing asyncMode to handle blocking I/O | FIFO does not solve blocked workers | Appropriate blocking pool/model |
| Not bounding outstanding events | Memory exhaustion or high latency | Quota/backpressure |
| Using commonPool and shutting it down | Shared JVM-wide pool | Own a dedicated pool if lifecycle control is needed |
| Calling cancel(true) and assuming the task was interrupted/stopped | ForkJoinTask has its own cancellation contract | Cooperative cancellation and completion verification |
| Testing with 1 worker printing ABC and applying it to 4 workers | Stealing and concurrency change behavior | Test invariants; do not promise global order |
| Treating getAsyncMode() as a fairness measurement | It is only a boolean configuration | Measure actual latency/queue age |
| Calling Future.get() inside a task in the same pool while holding resources needed by the child | Can cause wait cycles/starvation | Design dependency/lock ordering |

## 20. Checklist before enabling asyncMode

- [ ] Are the tasks truly **event-style forked/unjoined**?
- [ ] Does the parent need to combine child results using join?
- [ ] Is there a strict ordering requirement by key or commit sequence?
- [ ] Do you understand the difference between worker-local fork and external submit?
- [ ] Have multiple workers, stealing, and varying task durations been accounted for?
- [ ] Is there a completion/error/ack channel when not joining?
- [ ] Are outstanding tasks and per-task overhead bounded?
- [ ] Do tasks have mutable state or ThreadLocal that is not properly published/handed off?
- [ ] Is there a clear shutdown/cancel and cleanup path?
- [ ] Have you tested with parallelism=1 to demonstrate the mode, and with multiple workers to prove business invariants?
- [ ] Have both modes been benchmarked with real workloads and an appropriate baseline?
- [ ] If durability across JVM restarts is needed, are work and idempotency persisted outside the executor?

## 21. Self-check

**1. How does asyncMode=false differ from true?**  
False favors a LIFO local deque; true favors FIFO for unjoined forked event tasks. Neither mode guarantees global ordering.

**2. Why does the example use only one worker?**  
So that all three children are guaranteed to remain in the local deque until the parent finishes, preventing other workers from stealing/running them concurrently.

**3. With four workers, does local FIFO guarantee A completes before B?**  
No. Workers can execute in parallel and tasks have different execution durations.

**4. Can asyncMode=true be used for RecursiveTask with join?**  
Yes. It does not automatically make a correct algorithm wrong, but this mode does not necessarily improve the performance of recursive join workloads.

**5. Is submit from main equivalent to forking a child into the main worker's local deque?**  
No. Main is not a ForkJoinWorkerThread of the pool; external submit has its own dispatch path.

**6. If the parent does not join children, how does it know a child succeeded?**  
It needs a Future/result, ack, latch combined with status, or an error channel. Fork only schedules execution.

**7. Does local FIFO replace a strictly ordered single-thread event loop?**  
No. An event loop/owner solves a form of ordering/ownership that a multi-worker ForkJoinPool does not provide on its own.

**8. Why can ThreadLocal be wrong with forked events?**  
A task can be stolen by another worker; ThreadLocal is bound to the thread, not to the parent-child relationship.

**9. Does asyncMode eliminate the overhead of millions of tasks?**  
No. Batching, granularity, and admission control are still needed.

**10. Does ForkJoinTask's cancel(true) guarantee interrupting the worker?**  
No. Cancellation has its own contract and does not guarantee interrupting the worker as one might guess from the boolean parameter name.

**11. When can local FIFO be experimented with?**  
With many small independent unjoined forked tasks, when you want to test the throughput/latency of the worker-local policy.

**12. What is the most important safety principle when not joining?**  
Do not neglect child completion, errors, backpressure, and lifecycle; scheduling does not replace correctness.

## 22. Conclusion

**ForkJoinPool asyncMode=true** selects a **FIFO policy for the worker's local deque**, suitable to consider for **event-style tasks forked without direct joining**. The default **asyncMode=false** favors **LIFO**, which is usually natural for divide-and-conquer trees that require joining.

However, local FIFO **is not global FIFO**: there are also work stealing, multiple workers, external submissions, task durations, and side effects. Both modes must be used with **clear completion/error protocols, safe publication, task count control, and safe shutdown and cancellation**.

If events must be processed in strict business order, build a **serial owner, per-key queue, dependency, or sequence protocol** instead of relying on a scheduler boolean. If you only need to optimize independent event tasks, test the appropriate mode and **measure on real workloads** before drawing conclusions.
