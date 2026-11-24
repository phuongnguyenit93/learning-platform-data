# 9.6 Thread Pool Saturation, Queue Buildup, and Interdependent Tasks

> **Java Advance – runtime-diagnostics** · **9. Deadlocks and Contention**

## 1. Problem: Service Is Alive, Yet Work Does Not Complete

A Java service may still pass health checks, report no out-of-memory error, and even have low CPU, yet requests grow slower or time out. Thread dumps show many workers in *WAITING*, the executor queue grows continuously, and the completed-task rate is nearly flat.

One particularly dangerous possibility is **thread pool starvation caused by interdependent tasks**: a parent task occupies a worker, submits a child task to **that very same pool**, and then calls *Future.get()* or *CompletableFuture.join()* to wait. If all workers are busy waiting on child tasks sitting in the queue, **no worker remains to run the child tasks**. The system has pending work, yet zero execution capacity available for the work that would unblock progress.

This scenario must be separated from **ordinary saturation**, where task arrival outpaces processing rate, and from **contention**, where an external resource (database connection, monitor, lock, semaphore, network) inflates worker occupancy duration.

**This lesson focuses on three interconnected phenomena:**

1. **Pool saturation:** workers reach concurrency limits; new tasks must wait, are rejected, or follow the rejection policy.
2. **Queue buildup:** backlog grows because incoming work exceeds completion capacity, or workers are held too long.
3. **Task dependency starvation:** tasks holding workers wait on other tasks that cannot run yet, often with circular dependencies or shared dependence on the same finite execution pool.

The goal is to understand the **mechanisms**, read **runtime evidence**, distinguish **root causes**, and apply controlled **load-shedding / dependency-decoupling** measures — rather than blindly increasing thread counts or queue size.

### After this lesson, you should be able to

- Explain how *corePoolSize*, *maximumPoolSize*, *workQueue*, and *RejectedExecutionHandler* govern the order **thread creation → queueing → scaling → rejection**.
- Read *poolSize*, *activeCount*, *queue size*, *taskCount*, and *completedTaskCount* and understand their accuracy limits.
- Identify the chain “worker occupies slot → submits child → awaits child → child sits in queue.”
- Distinguish queue growth caused by high traffic, slow dependencies, retry amplification, lock contention, or self-inflicted task-dependency starvation.
- Understand why *Future.get(timeout)* does not mean the child was canceled, and why *thread dumps reporting no deadlock* do not rule out starvation.
- Choose **bounded queues, rejection/backpressure, concurrency limits, timeouts/deadlines, task composition**, and sensible pool architectures.
- Run a Java 17+ example reproducing **bounded-timeout nested-task starvation** and **rejection when pool + queue are full**, without creating an infinite hang.
- Write an incident conclusion backed by **queue/completion metrics + thread dumps + tracing**, not just a single stack line.

## 2. Core Model: Producers, Executor, Workers, and Queue

~~~text
                      +----------------------------------+
Request / message     | ThreadPoolExecutor               |
producer(s)           |                                  |
  -- submit() ------> |  [workQueue: pending tasks]       |
                      |         |                        |
                      |         v                        |
                      |  worker-1  worker-2 ... worker-N  |
                      |       |        |          |       |
                      |       +------ results ---+       |
                      +------------+---------------------+
                                   |
                       completed / failed / timeout

If neither workers nor queue can accept new work:
submit / execute --> RejectedExecutionHandler
~~~

An **active worker** means it is currently executing a task per the executor’s definition; that worker may be burning CPU, blocked on I/O, waiting on a monitor, parked on a Future, or waiting on another resource. **Active count is not CPU utilization.**

**Work queue** holds tasks that **have been accepted but have not started running**. It does not necessarily map 1:1 with HTTP request objects: one request can spawn multiple tasks, and one task can process multiple records. Thus *queue.size()* only has meaning within the scope of **the exact executor instance and task type**.

### Three Times Commonly Confused

\[
T_{\text{end-to-end}} \approx T_{\text{admission}} +
T_{\text{queue wait}} + T_{\text{execution}} +
T_{\text{downstream/response}}
\]

This is a **conceptual decomposition**, not strictly independent non-overlapping measurements. For example, *execution* may include downstream wait time, and an HTTP thread may wait on the executor result elsewhere.

- **Queue wait:** from when a task is accepted into the executor until a worker actually starts running it.
- **Task execution/occupancy:** from when the worker picks up the task until the task finishes, including periods of *get()/join()/I/O* where the worker makes no forward progress.
- **Response latency:** latency experienced by the caller; may span multiple queues, hops, retries, and deadlines.

If an endpoint’s p99 rises, determine whether the increase is in **queue wait** or **task processing**, and whether slow task processing stems from CPU, network, or dependency starvation.

## 3. When Does ThreadPoolExecutor Decide to Queue?

In a typical *ThreadPoolExecutor* on Java 17, when *execute()* receives a new task:

1. If current worker count is **less than corePoolSize**, the executor prefers starting a new worker for the task.
2. Once at least **corePoolSize** workers exist, the executor **prefers offering the task to the queue** if the queue accepts it.
3. Only if the queue **cannot accept the task** (e.g., a bounded queue is full) does the executor try expanding workers up to **maximumPoolSize**.
4. If it cannot enqueue and cannot add a worker, the executor invokes **RejectedExecutionHandler**; an executor shutting down may also reject.

**Example table:** configuration *core=2, max=5, queue capacity=3*, with all tasks occupying workers long enough; this illustrates step-by-step submission acceptance, not production measurements.

| New Task | Existing Workers | Queue Before Submit | Behavior per Algorithm |
| --- | --- | --- | --- |
| 1 | 0 | 0 | Create worker 1 |
| 2 | 1 | 0 | Create worker 2 |
| 3 | 2 | 0 | Enqueue |
| 4 | 2 | 1 | Enqueue |
| 5 | 2 | 2 | Enqueue |
| 6 | 2 | 3 (full) | Try creating worker 3 |
| 7 | 3 | 3 | Try creating worker 4 |
| 8 | 4 | 3 | Try creating worker 5 |
| 9 | 5 (max) | 3 (full) | Rejection policy |

**Common misconception:** *maxPoolSize* does not mean the executor scales up to max as soon as the two core workers are busy. While the queue has space, new tasks **are queued first**; max only kicks in when offering to the queue fails.

### 3.1 Unbounded Queues and the Nullified maximumPoolSize Effect

~~~java
// Illustrative code snippet, not a standalone program.
java.util.concurrent.ExecutorService executor =
        java.util.concurrent.Executors.newFixedThreadPool(8);
~~~

Per the Java SE 17 contract, *newFixedThreadPool(8)* uses **eight maximum workers** and a **shared unbounded queue**. If arrival rate stays above service rate, the queue can grow very large and consume memory. The executor **does not** automatically “expand to 100 threads” just because the queue grows long.

With a custom *ThreadPoolExecutor* paired with an unbounded queue, raising *maximumPoolSize* usually **never grows the pool beyond core** while the queue keeps accepting tasks. This is the classic reason behind “we raised maxPoolSize yet p99 kept climbing.”

*Unbounded* in the API means **no small cap imposed by you**, not that memory is infinite. An unbounded queue can cause **OOM/GC pressure**, caller timeouts, or extreme latency before any explicit rejection ever appears.

### 3.2 Bounded Queues and Thread Budgets

With *ArrayBlockingQueue<>(capacity)*, the queue has finite slots. When full, the executor can expand workers up to *maximumPoolSize*; once both limits are reached, the policy decides what happens to the next task.

This is a **capacity boundary**, not a silver bullet for every bug. A bounded queue surfaces overload earlier, yet if the policy rejects while callers retry infinitely, total pressure can still rise. Synchronized **admission control, rejection visibility, retry budgets, and backpressure** are needed.

### 3.3 SynchronousQueue: Direct Handoff

*SynchronousQueue* stores no backlog like a queue with capacity > 0: every handoff needs a ready consumer. With *ThreadPoolExecutor*, direct handoff makes the pool spawn workers faster (up to max) or reject when no worker is available and expansion hits max.

It can avoid certain forms of “task waiting on a child buried deep in the queue,” yet **does not eliminate circular dependencies**. If all max workers are occupied by parent tasks, children are still rejected; if max is too high, OS thread and memory costs soar. Balance handoff with concurrency limits and overload behavior.

## 4. Two Main Causes of Queue Buildup

### 4.1 Arrival Rate Exceeding Service Rate

Let:

- \(\lambda\) be the number of **tasks/second arriving** at an executor.
- \(\mu\) be the number of **tasks/second completed** by the executor under given conditions/load.
- \(Q\) be the number of tasks waiting in the queue.

Over a window unaffected by rejections/cancellations and with roughly uniform task sizes:

\[
\Delta Q \approx (\lambda - \mu) \cdot \Delta t
\]

If \(\lambda \gt \mu\) persists, backlog tends to grow. With a bounded queue, the eventual outcome may be **rejection** rather than unbounded queue growth.

**Illustrative example:** a pool completes roughly 20 tasks/s on average yet receives 50 tasks/s; over 10 seconds it can accumulate roughly 300 extra queued tasks (given sufficient capacity and absent other effects). This is a back-of-the-envelope estimate for reasoning, not a guaranteed model across arbitrary arrival/task distributions.

Do not confuse *request rate* with *task arrival rate*: if one request spawns 5 fan-out subtasks, \(\lambda_{\text{tasks}}\) can be much higher than \(\lambda_{\text{requests}}\).

### 4.2 Workers Held Long Waiting on I/O, Locks, or Other Tasks

Even when arrival rate **does not increase**, throughput can plummet if task duration grows:

- Downstream API/database slows down; workers hold slots during blocking calls.
- Exhausted database connections, semaphore permits, or rate-limit tokens.
- Lock contention: many tasks wait on one monitor or `ReentrantLock`.
- Retry loops: each task loops repeatedly instead of freeing the worker.
- **Nested dependency:** a parent task occupies a worker and calls *get()/join()* waiting for a child in the same queue.

The signature “low CPU yet high activeCount, rising queue, low completions/s” points to checking **blocking/park/resource waits** before adding CPU. Low CPU **does not prove** deadlock, because the service may simply be waiting on a normal but slow downstream.

## 5. Little's Law: Using It Within Proper Scope

In a **stable system** with well-defined arrivals/completions and matching measurement scope:

\[
L \approx \lambda W
\]

Where \(L\) is the average number of work items in the system, \(\lambda\) is average throughput, and \(W\) is average residence time. For the **queue alone**, \(L_q \approx \lambda W_q\) applies under steady-state conditions and matching scope.

**Never apply it mechanically while a queue is growing unboundedly.** Little's Law is a long-run steady-state relationship, not a “straight line” predicting every spike accurately.

For instance, with an average of 200 queued tasks and steady throughput of 100 tasks/s, average queue wait is roughly 2 s **if** assumptions hold. With retry amplification, highly variable task sizes, drops/rejections, chained queues, or autoscaling, re-evaluate the model before dividing two numbers.

## 6. Interdependent Tasks: Self-Inflicted Starvation Mechanism

Consider a **single-worker** pool, one queue, and two tasks:

~~~text
          SINGLE-WORKER EXECUTOR
         +----------------------+
         | worker-1             |
         |  runs Parent         |
         |    submit Child -----+--> queue: [Child]
         |    child.get()       |         |
         |    waits for Child   |         |
         |                      |         |
         +----------------------+         |
                  ^                       |
                  +--- Child needs worker -+
~~~

Parent holds the only worker and waits for Child. Child was accepted into the queue yet **cannot run** until the worker is free. The worker will not be free until Parent stops waiting or finishes. If *get()* has no timeout and nothing else frees the worker, this is **dependency starvation** that can last forever.

### 6.1 Common Sufficient Conditions

- Executor has finite concurrency \(N\).
- \(N\) parent tasks simultaneously **occupy all N workers**.
- Each parent submits a child or continuation requiring execution **by that same executor**.
- Parents use a blocking wait for children to finish.
- Child tasks sit in the queue or cannot be accepted because the pool is saturated.
- No timeout/cancellation/callback causes parents to release workers.

When these hold, **no worker slot remains to run any child**, even though CPU may be near 0%.

### 6.2 Why It Is Not Necessarily a Java Monitor Deadlock

*ThreadMXBean.findDeadlockedThreads()* detects deadlocks on **object monitors or ownable synchronizers** within its API scope. Dependencies across *Future.get()*, task queues, and executor workers may not form any monitor lock cycle recognizable by the detector.

Thus thread dumps may only show workers at *FutureTask.get()*, *CompletableFuture.join()*, or *LockSupport.park()*, while the deadlock detector reports “none found.” That **does not rule out** thread-pool starvation.

Distinguish clearly:

- **Java-level monitor deadlock:** locks A/B wait on each other in a cycle.
- **Thread-pool dependency starvation / task deadlock:** tasks wait on results of tasks that cannot be scheduled because all workers are held.
- **Livelock / retry loop:** activity or state changes occur without achieving business completion.

They can all make a service appear hung, yet their **causal mechanisms differ**.

### 6.3 Multi-Worker Variant

If a pool has 4 workers and 4 parent tasks all submit children and wait, the same outage occurs:

~~~text
worker-1: Parent A -> waits Child A
worker-2: Parent B -> waits Child B
worker-3: Parent C -> waits Child C
worker-4: Parent D -> waits Child D

queue: Child A, Child B, Child C, Child D
runnable workers available: 0
~~~

Queue length grows not from “insufficient processing speed for traffic,” but from **broken worker ownership and dependency graph**. Temporarily raising *maxThreads* might let some Child run and free a Parent, yet **that does not prove the code structure is safe**: higher load can hit the new ceiling and repeat the failure.

### 6.4 Do Not Equate Every Future.get() with a Bug

*Many* tasks waiting on a Future are completely valid when the Future is completed by an **independently progressing system**, such as an I/O callback on another event loop. The core question is:

> “Does the awaited task **require the exact resource held by the caller** in order to complete?”

If not, a blocking wait can still hurt throughput by occupying a worker, yet it is not a closed-loop dependency starvation. Inspect **executor topology, task submission paths, and completion ownership**, not just the top stack frame.

## 7. Queue Growth from Nested Fan-Out: One Request Becoming Many Tasks

If a parent request spawns 10 subtasks and awaits all of them, the system turns \(R\) requests/s into roughly \(10R\) subtasks/s on a shared executor. When downstream slows down, parents occupy workers longer while children pile up in the queue. This is **dependency + amplification**:

~~~text
incoming requests (λr)
       |
       v
parent tasks (occupy workers)
       |
       +--> child 1 \
       +--> child 2  > shared executor queue
       +--> child 3 /
       |
       +--> wait all children (workers not released)
~~~

If each parent calls *invokeAll*, *Future.get*, *join*, or synchronizes with a latch, there is no guarantee all children get scheduled in time. *invokeAll()* does not eliminate starvation risk if called inside a task of a finite pool targeting that same pool.

**Common symptoms:**

- Active workers ≈ pool size/max.
- Many worker stacks at *FutureTask.get*, *CompletableFuture.join*, or *CountDownLatch.await*.
- Queue contains tasks whose parent tasks are currently waiting.
- Completed-task count stalls; queue wait age climbs.
- HTTP latency and timeouts climb while CPU may not rise.

A key check is **what kind of task sits in the queue**. If the queue is full of database result callbacks or child computations awaited by workers, the dependency structure is highly suspect. If the queue only holds fresh incoming requests while workers are blocked on network calls, the root cause may be different.

## 8. Standalone Java 17+ Example: Nested Wait and Bounded Rejection

This lab contains **two clearly synchronized tests** and **creates no infinite hang**:

1. **Nested task dependency:** a 1-worker, 1-queue-slot pool; parent submits child to the queue and waits *150 ms* for child. Because parent occupies the worker, child cannot run yet, so parent times out. Once parent leaves the worker, child runs and increments a counter.
2. **Bounded queue saturation:** one worker is held by a latch, a second task waits in the queue, and a third task is rejected by *AbortPolicy*. Once the latch releases, the two accepted tasks finish.

The program requires no libraries outside the JDK. It uses *CountDownLatch* rather than sleeping briefly and hoping workers reached the desired state. Waits in `main` have timeouts and `finally` blocks clean up.

Create file **PoolSaturationLab.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolSaturationLab {
    public static void main(String[] args) throws Exception {
        nestedDependency();
        boundedRejection();
    }

    private static ThreadPoolExecutor oneWorkerOneSlot() {
        return new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
    }

    private static void nestedDependency() throws Exception {
        ThreadPoolExecutor pool = oneWorkerOneSlot();
        CountDownLatch childQueued = new CountDownLatch(1);
        CountDownLatch allowWait = new CountDownLatch(1);
        AtomicInteger childRan = new AtomicInteger();
        try {
            Future<String> parent = pool.submit(() -> {
                Future<?> child = pool.submit(childRan::incrementAndGet);
                childQueued.countDown();
                if (!allowWait.await(5, TimeUnit.SECONDS)) {
                    return "GATE_TIMEOUT";
                }
                try {
                    child.get(150, TimeUnit.MILLISECONDS);
                    return "UNEXPECTED";
                } catch (TimeoutException expected) {
                    return "TIMED_OUT";
                }
            });
            if (!childQueued.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child was not queued");
            }
            System.out.println("nested.workers=" + pool.getPoolSize());
            System.out.println("nested.queued=" + pool.getQueue().size());
            System.out.println("nested.childBefore=" + childRan.get());
            allowWait.countDown();
            System.out.println("nested.parentWait=" + parent.get(5, TimeUnit.SECONDS));
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool failed to terminate");
            }
            System.out.println("nested.childAfter=" + childRan.get());
        } finally {
            allowWait.countDown();
            pool.shutdownNow();
        }
    }

    private static void boundedRejection() throws Exception {
        ThreadPoolExecutor pool = oneWorkerOneSlot();
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
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            pool.execute(completed::incrementAndGet);
            boolean rejected = false;
            try {
                pool.execute(completed::incrementAndGet);
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            System.out.println("bounded.workers=" + pool.getPoolSize());
            System.out.println("bounded.queued=" + pool.getQueue().size());
            System.out.println("bounded.rejected=" + rejected);
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool failed to terminate");
            }
            System.out.println("bounded.completed=" + completed.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run on **JDK 17+**:

~~~bash
javac -encoding UTF-8 PoolSaturationLab.java
java PoolSaturationLab
~~~

**Nine stdout lines verified by running the program on the JDK:**

~~~text
nested.workers=1
nested.queued=1
nested.childBefore=0
nested.parentWait=TIMED_OUT
nested.childAfter=1
bounded.workers=1
bounded.queued=1
bounded.rejected=true
bounded.completed=2
~~~

**Exact explanation:**

- *nested.workers=1*: the executor has exactly one worker.
- *nested.queued=1*: child was accepted into the queue but no worker ran it yet.
- *nested.childBefore=0*: child has not run because the worker belongs to parent.
- *nested.parentWait=TIMED_OUT*: waiting on child failed due to lack of executor capacity, not because child threw an exception.
- *nested.childAfter=1*: once parent finished, the worker picked up child and ran it — illustrating that **wait timeout does not mean child cancellation**.
- *bounded.queued=1*: the second task entered the single-slot queue.
- *bounded.rejected=true*: the third task was rejected by policy because both worker and queue were saturated.
- *bounded.completed=2*: both accepted tasks finished after the gate opened; the rejected task never executed.

**Accuracy note:** the program uses latches to establish deterministic lab ordering; the stdout above was verified empirically. Under severe CPU starvation, the lab’s safety timeouts could cause an exception rather than printing all nine lines; therefore this is not a blanket stdout guarantee across every OS/JVM/scheduler.

### 8.1 Why Didn’t the Example Use an Unbounded Future.get()?

If parent called untimed *child.get()* in a single-worker pool, the program could hang indefinitely. That is the bug this lesson **teaches how to recognize**, not something learners should run as a stuck demo.

The lab uses *get(150, MILLISECONDS)* to release parent and let child run afterward. The timeout lets the test finish cleanly, **without fixing the architectural cause**: under real workload, timeouts still cause request failures, retries, queue buildup, and late downstream work.

### 8.2 Why Did the Child Still Run After the Parent Timed Out?

*Future.get(timeout, unit)* only limits **the caller’s wait duration**; it does not cancel the computation. Attempting cancellation requires an explicit decision, such as *child.cancel(true)* when logic permits and proper cleanup/idempotency exists. Even then, *cancel(true)* only attempts to interrupt a running task; it does not guarantee immediate termination, especially for code that ignores interruption.

In the lab, child had already been accepted, so once parent freed the worker it completed normally. This proves why a timed-out request **can still generate delayed load** if tasks are not canceled or downstream calls are not stopped.

### 8.3 Why Not Call This a Monitor Deadlock?

The parent worker is not waiting on *synchronized* monitors in an A/B cycle. It waits on a Future while the child is never scheduled. Thus *findDeadlockedThreads()* is not expected to detect it. Fixes lie in **dependency/task architecture**, not adjusting Java monitor lock ordering.

### 8.4 Why Does Queue Capacity One Make the Failure Clear?

A bounded queue limits backlog. Once both worker and queue are full, *AbortPolicy* throws a clear **RejectedExecutionException** instead of accepting tasks endlessly and blowing up memory/timeouts. Still, rejection is **an overload signal that must be handled**, not service success. Real systems need HTTP/gRPC/message-level failure responses, budgeted retries, and rejection-rate observability.

## 9. Three Queue Types and Four Rejection Policies

### 9.1 Queue Strategy Has Direct Consequences

| Queue | Mechanism | Pros | Risks |
| --- | --- | --- | --- |
| **LinkedBlockingQueue** without capacity arg | Accepts queued items up to a huge implementation limit | Absorbs brief bursts, simple setup | Queue growth and memory pressure; `maximumPoolSize` does not expand as many expect |
| Bounded **ArrayBlockingQueue** | Finite queue | Clear backpressure/rejection, bounds pending tasks | Requires sizing capacity and handling full state; latency still high if queue is too big |
| **SynchronousQueue** | Direct handoff, holds no backlog | Forces “hand off now / spawn worker / reject” | Too-high max threads risks resource exhaustion; finite max rejects easily under bursts |
| **PriorityBlockingQueue** | Priority ordering, inherently unbounded when used as TPE `workQueue` | Prioritizes work by comparator | Starvation of low priority, queue growth, complex task wrappers |
| **Delayed work queue** of `ScheduledThreadPoolExecutor` | Holds tasks by trigger time | Timed scheduling | Not a queue for self-bounding all scheduled tasks; blocking scheduled tasks still occupy workers |

**No single queue fits every workload.** Consider CPU-bound vs. blocking I/O, task duration distribution, workload priority, deadlines, memory budget, and overload policy. Any design that fails to bound total in-flight work externally can eventually push pressure into another queue or layer.

### 9.2 Rejection Policies

| Policy | When Pool Cannot Accept Task | Considerations |
| --- | --- | --- |
| **AbortPolicy** (default) | Throws *RejectedExecutionException* | Clear fail-fast; caller must translate into proper response/metric |
| **CallerRunsPolicy** | Caller runs the task itself if executor is not shut down | Can throttle producers yet **blocks the caller**; very dangerous on event-loop/request threads or while caller holds a lock |
| **DiscardPolicy** | Silently drops the task | Very dangerous for tasks with Futures or business outcomes; can leave waiters hanging forever |
| **DiscardOldestPolicy** | Drops head task in queue and retries submitting new task | Can make older tasks vanish; requires cancellation/notification handling; rarely appropriate |

**CallerRunsPolicy** is no universal remedy. If the caller is a worker from another pool, work spills back onto that worker and can slow the whole chain. If the caller is an event-loop thread, running a synchronous task inline can stall I/O handling. If the caller holds a lock, inline execution can trigger nested lock contention. Choose it only after understanding **caller context** and desired backpressure behavior.

**DiscardPolicy** or *DiscardOldestPolicy* can break Future/task completion contracts. If code awaits a silently dropped child without knowing, the wait becomes infinite unless guarded by timeouts/cancellation. Never use silent drops for critical requests.

### 9.3 When Is Rejection a Good Sign?

Explicit rejection is **evidence that the system hit configured capacity**, controlling load instead of accumulating endlessly. However, it is “good” only when the full path has clean semantics:

- Track rejection counts by **pool and task type**.
- Return protocol-appropriate overload responses (typically 429/503 or suitable error types; never map all errors to 200).
- Retry with **backoff/jitter and an overall deadline**, never infinite immediate retries.
- Ensure idempotency or deduplication for operations with side effects.
- Never swallow *RejectedExecutionException* and leave a Future/request hanging.
- Signal clearly to callers that the task **was not accepted**, avoiding false assumptions it will run later.

## 10. What Will a Thread Dump Look Like?

A nested task dependency incident may show **illustrative** snippets like:

~~~text
"checkout-worker-1" #31
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.FutureTask.awaitDone(...)
    at java.util.concurrent.FutureTask.get(...)
    at com.example.Checkout.enrichOrder(Checkout.java:117)

"checkout-worker-2" #32
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.CompletableFuture$Signaller.block(...)
    at java.util.concurrent.CompletableFuture.join(...)
    at com.example.Checkout.fetchRecommendations(Checkout.java:88)
~~~

Frames and formatting vary by JDK/VM; these lines are not real logs. A worker in *WAITING* may be legitimately waiting for work. **Danger signs** appear when:

1. Workers have consumed nearly all pool concurrency.
2. Many workers wait on `Future`/`join` in code paths tied to child tasks.
3. Child tasks are submitted to **the very executor whose workers are full**, sitting in the queue.
4. Completions/s or business progress stops while queue age/depth climbs.
5. The pattern repeats across multiple snapshots of the same JVM instance.

Then the nested starvation hypothesis has strong evidence. If workers are `WAITING` in the pool’s *BlockingQueue.take()* while queue depth is 0, those are normally **idle workers awaiting work**, an entirely different situation.

### 10.1 Distinguishing WAITING, TIMED_WAITING, BLOCKED, and RUNNABLE

| State in Dump | Suggests | Must Not Infer |
| --- | --- | --- |
| `WAITING` | *Future.get()*, *join()*, *park()*, *queue.take()* | All `WAITING` threads are hung |
| `TIMED_WAITING` | Timed wait, sleep, backoff, `Future.get(timeout)` | Timeout already fired |
| `BLOCKED` | Waiting on an **object monitor** to enter `synchronized` | Every `ReentrantLock`/queue wait is `BLOCKED` |
| `RUNNABLE` | Java runnable or certain native/I/O paths | Thread is consuming 100% CPU |

Java `Thread.State` does not provide state duration. Two dumps 5 seconds apart showing the same top frame **do not prove** the thread waited continuously for exactly 5 seconds; it could have exited and re-entered that frame. You need JFR monitor/park events, task logs, queue wait timings, and completion counters.

### 10.2 No Deadlock Report Does Not Rule Out Starvation

`ThreadMXBean` deadlock detectors cover specific Java locks. If parent tasks wait on Futures that cannot run, there may be **no monitor cycle** for the detector to find. Analyze the **task-level dependency graph** and executor ownership rather than treating “no deadlocks found” as the sole conclusion.

## 11. Metrics to Monitor on ThreadPoolExecutor

*ThreadPoolExecutor* exposes basic statistics; several methods explicitly document **approximate** results because workers/queues change concurrently during reads. Never treat them as an atomic pool-wide snapshot.

| Java Metric | Meaning | Pitfall |
| --- | --- | --- |
| *getCorePoolSize()* | Configured core threshold | Not the guaranteed active worker count at all times |
| *getMaximumPoolSize()* | Configured worker limit | Does not prove the pool ever scaled to max |
| *getPoolSize()* | Current number of workers | Not the number consuming CPU |
| *getActiveCount()* | Approximate number of workers **processing tasks** | Active tasks may be waiting on I/O/Future |
| *getQueue().size()* | Snapshot count of queued tasks at read time | Changes dynamically; not pending HTTP requests |
| *getTaskCount()* | **Approximate** total scheduled tasks | May include waiting/running tasks; know semantics and restarts |
| *getCompletedTaskCount()* | **Approximate** total tasks that finished execution | Does not mean business success; failed tasks count as completed execution |
| *getLargestPoolSize()* | High-water mark of simultaneous workers | Not current level |
| *getRejectedExecutionHandler()* | Overload handling policy | Does not directly return rejection count |
| *isShutdown()/isTerminating()/isTerminated()* | Executor lifecycle | Queue may not be drained when shutdown starts |

**Important:** the API has no standard *getQueueWaitP99()* or *getRejectedCount()*; to obtain those metrics, instrument them yourself or use framework/infrastructure monitoring with clear contracts.

### 11.1 Formula for Reading Trends

A time series with 10-second windows might look like:

~~~text
time       active/max   queueDepth   completedTotal   rejectedTotal
12:00:00       8/8          20             1000              0
12:00:10       8/8         220             1001              0
12:00:20       8/8         420             1001              0
~~~

These **hypothetical** numbers suggest the pool is barely completing tasks even as backlog surges. However, they **are not enough** to prove nested dependency; all workers could be waiting on a slow DB, lock X, or a network call.

To differentiate, examine worker thread dumps/traces and downstream/queue metrics:

- *Completed delta ≈ 0* suggests stalled progress at the executor level.
- *Rising queue depth* suggests arrivals continue.
- *Active=max* means workers accepted tasks, not that CPU hit 100%.
- *Rejection=0* may simply mean an unbounded queue still accepts tasks; it is not proof of healthy capacity.

### 11.2 Queue Wait Age Matters More Than Queue Length Alone

A queue of 100 can drain very fast under high throughput; a queue of just 5 causes severe latency if each task waits minutes. To know actual wait duration, measure **task age in queue**:

~~~text
task accepted at t0
worker begins task at t1
queueWait = t1 - t0
~~~

Note that *System.nanoTime()* measures elapsed time **within the same JVM**, avoiding wall-clock skew; timestamps in logs/traces should use a consistent time basis and UTC. If queueing crosses a message broker, separate broker wait, network transfer, and executor wait.

Minimal instrumentation must decide clearly:
- Measure queue wait from **submit called** or **accepted into queue**?
- How are rejected tasks tracked?
- If *CallerRunsPolicy* executes inline, execution happens outside a pool worker.
- Are pre-start cancellations counted?
- Do histograms distinguish task type, priority, pool, and instance?

Avoid putting `requestId` in metric labels: high cardinality easily overloads metrics systems.

### 11.3 Monitoring Snippet (Not a Standalone Program)

~~~java
// Runs inside a service that already has a ThreadPoolExecutor pool variable.
int workers = pool.getPoolSize();
int active = pool.getActiveCount();       // approximate
int waiting = pool.getQueue().size();     // snapshot
long scheduled = pool.getTaskCount();     // approximate
long finished = pool.getCompletedTaskCount(); // approximate

// Export gauges/counters with pool ID and JVM instance.
// Do not treat finished == businessSuccess.
~~~

If you only hold a framework-provided *ExecutorService* reference, casting to `ThreadPoolExecutor` is not always valid; some wrappers intentionally hide implementations. Use the framework’s monitoring API or instrument admission/worker hooks per contract.

## 12. Finding Nested Dependency Evidence from Code and Runtime

Thread dumps show *FutureTask.get()* without saying “the parent’s child task is in the queue.” Multiple sources must be correlated.

### 12.1 From Call Stack to Child Submission Site

1. Locate the application frame directly beneath *Future.get()*, *CompletableFuture.join()*, or *CountDownLatch.await()*.
2. Read that frame’s code: where did the parent create the *Future*? Which executor runs the child?
3. Cross-check pool names/configs (HTTP, IO, CPU, async, `commonPool`).
4. Can the child complete from a callback outside the pool, or must it use the same executor?
5. If the same pool, determine how many parents hold workers and how many child tasks are pending.
6. Check timeouts/cancellation: does the parent release the worker? Does the child linger after timeout?
7. Inspect per-task traces/counters if available to establish the dependency graph.

**Pool names alone are insufficient evidence:** *CompletableFuture.supplyAsync()* with no executor uses a default executor (commonly `ForkJoinPool.commonPool` per JDK), whereas *supplyAsync(..., pool)* uses the specified executor. Verify the exact call site and JDK version rather than assuming every `CompletableFuture` runs in the application pool.

### 12.2 Task-Level Dependency Graph

~~~text
Parent A (worker A)
   |
   +-- waits Child B (queued in same executor)
                       |
                       +-- waits Child C (also queued)
                                          |
                                          +-- depends on resource R
~~~

There can be a linear dependency **with no logical cycle among task IDs** that still starves because of **finite execution resources**. The cycle appears in the graph **“task holds worker → needs child → child needs worker.”**

Therefore investigations must ask **who holds workers while waiting**, not just whether an object-lock cycle exists.

### 12.3 Request-Level Executor Topology

A request might traverse:

~~~text
HTTP worker pool
      |
      v
business executor
      |
      +-- blocking database I/O
      |
      +-- submits async enrichment to same executor
            |
            +-- dependent callback in another executor
~~~

The map should clarify:
- Which pool runs parent and child.
- How many workers and queue slots each pool has.
- Whether waits are synchronous/blocking or asynchronous.
- Which thread executes completion callbacks.
- How far deadlines and cancellation propagate.
- Admission load, retries, and fan-out multiplier.

If both the HTTP pool and business executor are held by concurrent wait chains, enlarging only the business pool may overload the downstream DB further. Inspect the **total concurrency budget**.

## 13. Timeout, Cancellation, and Completion Semantics

### 13.1 Future Wait Timeout Does Not Free All Resources

~~~java
// Illustrative code snippet, assuming future and deadline already exist.
try {
    return future.get(500, java.util.concurrent.TimeUnit.MILLISECONDS);
} catch (java.util.concurrent.TimeoutException ex) {
    future.cancel(true); // request cancellation when business logic allows
    throw ex;
}
~~~

This is **not** a copy-paste recipe for every task:

- *get(timeout)* only limits how long the caller waits.
- *cancel(true)* attempts to interrupt the task when permitted, without guaranteeing immediate stop.
- An operation whose side effects already started may still complete downstream.
- Idempotency/deduplication and compensation are needed if business semantics require them.
- If the task has not started yet, cancellation can prevent execution, though wrapper/queue cleanup depends on the executor.
- If multiple layers retry after timeouts, old tasks keep running and compound load.

Also distinguish: *Future.isDone()* covers **success, exceptional completion, and cancellation**—it does not mean business success.

### 13.2 End-to-End Deadlines vs. Per-Call Timeouts

If a request only has 1 second before its deadline, each dependency should not wait 1 second on its own and then retry another 1 second at other layers. Design a **deadline budget propagated through the chain**:

~~~text
Request budget 1000 ms
  -> validation 50 ms
  -> queue wait <= 100 ms (policy)
  -> downstream <= remaining budget
  -> response writing within remaining budget
~~~

Numbers are illustrative. When a task has not started yet and its deadline has expired, it is usually best to **reject/cancel early** rather than executing work that is already valueless. Implement this per framework and business contract.

### 13.3 Never Use shutdownNow as an Arbitrary “Pool Reset”

*shutdownNow()* tries to stop active tasks via interruption and returns unstarted tasks; it does **not** safely hard-kill arbitrary work. In production it can abort transactions mid-flight, drop queued work, and leave inconsistent state. Use it only within designed shutdown/recovery procedures with compensating actions and clear ownership.

## 14. Ways to Reduce Nested Starvation Risk

### 14.1 Prefer **Non-Blocking Composition** Over Submit-and-Wait on a Worker

With `CompletableFuture`, *thenCompose* expresses dependencies without tying up a worker just to await a child Future:

~~~java
// Illustrative code snippet; service has a managed ioExecutor.
// fetchData() and enrich() are existing business methods.
java.util.concurrent.CompletableFuture<Result> result =
    java.util.concurrent.CompletableFuture
        .supplyAsync(() -> fetchData(), ioExecutor)
        .thenCompose(data -> java.util.concurrent.CompletableFuture
            .supplyAsync(() -> enrich(data), ioExecutor));

// Inside a worker of ioExecutor itself, avoid result.join().
// Return CompletionStage to a caller that supports async.
~~~

*thenCompose* creates a **dependent stage**; it does not block a thread waiting on the child like calling *join()* inside a worker. However, the child still needs executor capacity to run, and the flow must handle **exceptions, cancellation, timeouts, and result backpressure**. If the downstream API only offers blocking I/O, leaf operations still occupy a thread during the call.

**Note:** the code above is only a snippet, not standalone because *Result/fetchData/enrich/ioExecutor* belong to a hypothetical app. Never assume “using CompletableFuture” means nonblocking if *join()* is still called at the end inside a worker of the same executor.

### 14.2 Separate Pools by Work Type, Not Intuition

Separating CPU-intensive work, blocking I/O, scheduling/coordination, and dependency callbacks **can** reduce one task group starving another’s workers. However, pool separation helps only when:

- Each pool has a **concurrency/queue budget** and admission policy.
- Dependencies do not form reverse cycles across pools.
- Total thread/heap/native-memory/OS-scheduling costs are accounted for.
- Downstream can actually sustain the allowed concurrency.
- Metrics and tests verify **starvation was not simply shifted to another pool**.

A clean approach is having the parent coordinator return a future/continuation rather than occupying a worker to wait. Children run in a capacity-managed pool, and results compose upon completion.

### 14.3 Run Leaf Work Synchronously When Appropriate, Avoiding “Fake Async”

If both parent and child are short, pure-CPU tasks needing no real concurrency, **calling child directly** inside parent is sometimes simpler and safer than submitting to the same pool and waiting. Still, weigh tail latency and modularity, and avoid turning long blocking calls into inline work on an event loop.

### 14.4 Cap Fan-Out and Outstanding Tasks

When each request spawns 100 subtasks, merely adding workers can overload downstream. Limit:
- Concurrent subtasks per request/tenant.
- Total in-flight tasks per instance.
- Outstanding downstream requests/DB connections.
- Queue capacity.
- Retry attempts and remaining time.
- Batch size/chunking and deadlines.

Limits must be enforced at **admission**, not only “after tasks are already queued.” If a request already submitted 100 tasks before you check queue length, the system may already be over budget.

## 15. Why “Adding Threads” or “Growing Queues” Often Backfires

### 15.1 Raising maximumPoolSize with an Unbounded Queue May Do Nothing

As seen in section 3, while the queue accepts tasks, `ThreadPoolExecutor` prefers queueing over spawning workers. With an unbounded queue, raising `maximumPoolSize` from 20 to 200 may never create worker #21.

**Fixes must verify actual runtime config**, not guess from a variable named *max* in config. Inspect *corePoolSize, maxPoolSize, workQueue*, and runtime `poolSize`.

### 15.2 Raising corePoolSize Can Shift the Bottleneck Downstream

If workers are held by a 10-connection DB pool, raising the Java pool from 20 to 200 can create 180 extra threads **waiting on the same 10 connections**, costing native memory and OS context switching without raising DB throughput.

Do not reflexively raise concurrency when CPU is low. Identify the **bottleneck resource** and service-time breakdown first.

### 15.3 Growing Queue Size Can Mask Faults, Raise p99, and Strain Memory

A queue of 1000 may look “smoother” than 100 for a brief burst, yet under sustained overload a 10000-slot queue simply accumulates longer before rejecting; many queued requests have already blown their deadlines before ever running.

A huge queue also pins references to payloads/contexts, increasing heap pressure, GC activity, and even OOM risk. Large queue size is not throughput capacity.

### 15.4 Scaling Out Has Limits Too

Adding instances increases aggregate throughput **when work is distributable and downstream handles the load**. Yet if every instance suffers nested dependency starvation, you are cloning the bug. If downstream is a shared DB with connection limits, unguarded scale-out can worsen shared contention.

## 16. Incident Investigation Flow: From Metrics to Root Cause

### Step 1 — Lock Down the Exact Pool and JVM Instance

Record service/version, pod/host, JVM start time/PID, pool name, core/max/queue/policy config, task types, and incident window. Never mix queue metrics from pod A with a thread dump from pod B when inferring cause.

If the service runs **multiple executors**, know what each does. HTTP worker pools, DB driver callbacks, Kafka consumers, schedulers, `ForkJoinPool.commonPool`, and custom business pools have distinct lifecycles.

### Step 2 — Verify Genuine Saturation

Inspect multi-sample series:
- Is *activeCount/poolSize* near its limit?
- Are queue size and age rising?
- Is completed delta/s falling?
- Is rejected delta/s rising?
- Did task execution time or queue wait time climb?
- What do CPU/GC/heap/DB connection pools show?

A single *activeCount=max* snapshot does not prove overload: a pool can be legitimately busy while finishing tasks quickly, keeping queues empty, and meeting SLAs.

### Step 3 — Take Controlled Thread Dumps

On HotSpot, with permissions and exact namespace:

~~~bash
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l > pool-thread-01.txt
~~~

PID *12345* is only an example; replace with the verified JVM. `-l` requests ownable synchronizer info on supporting builds; check *help Thread.print* on the target JVM.

If the incident persists and overhead permits, take a few dumps **spaced apart with UTC timestamps**. Never poll tightly or treat one dump as the entire history. Dumps can produce large outputs and impact the JVM; store them securely.

### Step 4 — Inspect Where Workers Are

Classify them:
- Truly CPU-bound code?
- Native I/O / network read?
- *FutureTask.get / CompletableFuture.join*?
- *BlockingQueue.take* (idle)?
- *ReentrantLock / Condition / monitor*?
- *CountDownLatch.await / Semaphore.acquire*?
- *Thread.sleep* (backoff/retry)?
- JVM GC/safepoint/JIT helper threads?

Do not call every `WAITING` a deadlock. Only workers showing **matching task dependencies and pending queued tasks** support pool-dependency starvation.

### Step 5 — Trace Child Work and Completion Ownership

From the worker’s business frame, find:
- Where is the child submit call?
- Is the child’s executor the same as the parent’s?
- When does the child run, and who completes the future?
- Is there a queue/future awaited by the parent itself?
- Are timeouts/cancellation and task cleanup in place?
- Could a queued item have been rejected/dropped without completing the Future?

If you cannot confirm which queue holds the child, keep the conclusion at **task dependency starvation hypothesis**, not confirmed root cause.

### Step 6 — Cross-Check Other Resources

- If workers block on JDBC connection acquisition, inspect DB pool active/pending, slow queries, connection leaks, and DB server.
- If blocked on `synchronized`, inspect lock owners and JFR monitor events.
- If `RUNNABLE` with high CPU, inspect per-thread CPU deltas/profiler.
- If long GC pauses occur, inspect GC Unified Logging/JFR.
- If the queue grew from a sudden burst, compare arrival rate against configured capacity.
- If retries coincide with the spike, check retry counts, deadlines, and downstream errors.

### Step 7 — Shed Load Before Adding Capacity

Per operational authorization:
- Throttle/reduce incoming load via controlled rate limits/admission.
- Stop retry storms and cap fan-out.
- Fail fast on overload instead of piling up expired tasks.
- Bound concurrency per dependency.
- Plan pool separation / async composition fixes at nested-wait sites.
- Never run *shutdownNow()* or kill the JVM without assessing side effects.

### Step 8 — Before–After Verification

After the change, track:
- Queue wait p95/p99 and queue depth/oldest task age.
- Completed rate, **business success rate**, and rejection/timeout rates.
- CPU, heap/GC, threads, downstream latency, and connection pools.
- Lock/parking patterns in dumps/JFR as needed.
- Load levels and change timestamps to avoid mistaking natural traffic drops for a fix.

A solid fix restores progress **beyond just one pool**, without dropping work or overloading another dependency.

## 17. Evidence-Based Root-Cause Table

| Symptom | Possibility | Additional Evidence Needed |
| --- | --- | --- |
| active=max, queue rising, low CPU; workers at `Future.get` | Nested task wait or slow downstream Future | Child executor ownership, child queue, completion source |
| active=max, queue rising, high CPU; stacks in parsing/computation | CPU bottleneck | Per-thread CPU deltas/JFR profiler, CPU limits |
| active=max, queue rising; JDBC `getConnection` waits | DB connection-pool bottleneck | DB pool active/waiters, query latency, leaked connections |
| active=max, queue rising; workers `BLOCKED` on same monitor | Lock contention | Monitor owner + JFR durations + critical section |
| active=max, queue rising; network read | Slow dependency | Trace spans, socket timeouts, remote errors |
| queue near full and rejected rising | Bounded capacity reached | Arrival/service rates, retry policy, and error handling |
| queue rising yet active below core | Worker creation/rejection/config issue, executor shutdown, submit mismatch | `ThreadFactory`, lifecycle, exact executor instance |
| queue=0 and active low, yet service slow | Bottleneck upstream/downstream of pool | HTTP acceptor, broker lag, DB, GC, downstream |
| completed task count rising yet success rate falling | Tasks finish with errors/rejections/timeouts | Business outcomes, exceptions, retry semantics |
| thread dump shows no cycle yet requests hang | Does not rule out task dependency starvation | Executor/task graph, pending queue, futures |
| max raised after deploy yet workers did not increase | Unbounded queue or pool did not need to expand | Core/max/queue config & runtime threads |
| HTTP timed out yet queue still full of old tasks | Deadline/cancellation not propagated | Task ages, cancel behavior, client retries |

## 18. Deep-Dive Analysis Scenarios

### 18.1 Checkout Hung Due to Nested Enrichment Task

**Hypothetical context:** *checkoutPool* has `core=max=8`, unbounded queue. Each checkout task submits an enrichment subtask to the same pool, then calls *Future.get()*.

**Observations:**
- Eight parent tasks occupy all eight workers.
- Child tasks queue up; queue size grows.
- Workers show frames at *FutureTask.get*.
- `CompletedTaskCount` barely rises.
- CPU is low because workers are waiting.

**Strong hypothesis:** parent–child dependency starvation. Confirm via submission code and executor identity, not stack traces alone.

**Design fix:** avoid blocking waits in the same executor; compose asynchronously or run child inline when suitable; if splitting pools, enforce an overall concurrency budget and deadline propagation. Merely bumping max from 8 to 16 may postpone but does not guarantee eliminating the bug.

### 18.2 Unbounded Queue Masks Overload Before OOM

**Hypothetical context:** 4 CPU workers, each task takes 200 ms on average at steady load (theoretical peak ~20 tasks/s under ideal distribution); arrival jumps to 100 tasks/s, and producers keep submitting into an unbounded queue.

**Observations:** queue depth grows rapidly, heap usage/GC activity climbs, and p99 latency spikes before CPU/JVM destabilizes.

**Diagnosis:** offered load exceeds sustainable capacity; no nested dependency is needed to explain it.

**Load mitigation:** bounded admission, backpressure/rejection, reduced fan-out, right-sized scaling if downstream permits, and reviewing batching/algorithms and task service time. Enlarging the queue only delays when overload becomes undeniable.

### 18.3 Large Thread Pool Facing Few DB Connections

**Context:** 80 Java workers process requests while the DB pool has only 10 connections and slow queries.

**Observations:** threads `WAITING` in connection acquisition, high executor active count, low Java CPU, growing queue. DB connection pool pending climbs.

**Likely cause:** downstream/DB capacity, connection leaks, or slow queries; **not** necessarily an undersized Java thread pool.

**Remediation to verify:** bound query concurrency, tune queries/pool policy, add timeouts/connection leak detection, isolate admission; do not raise Java workers to 500 when the DB only handles 10 concurrent queries.

### 18.4 Retry Amplification After Timeouts

**Context:** requests time out at 1 s, yet child tasks keep running for 3 s. Clients retry twice, creating three waves of tasks in the pool.

**Observations:** queue age climbs, app error rate rises, rejected count begins rising, downstream QPS exceeds client QPS.

**Issue:** caller timeout does not cancel work; unbudgeted retries let valueless tasks keep consuming capacity.

**Solution:** end-to-end deadlines, safe cancellation, idempotency, retry/backoff/jitter, capping concurrent downstream calls, and skipping tasks past deadline.

### 18.5 Scheduled Executor Delayed by a Long Task

**Context:** a small scheduled pool executes periodic jobs. One job waits 2 minutes on I/O; subsequent scheduled jobs run late.

**Observations:** scheduled task delays climb; worker stays busy; queue holds future scheduled tasks.

**Diagnosis:** a blocking task holds scheduler capacity. Do not assume nested task deadlock.

**Design:** decouple scheduling/dispatch from blocking execution or size workers appropriately for the workload, while ensuring unbounded queues do not form when downstream slows down.

### 18.6 CompletableFuture Running on an Unexpected Executor

**Context:** a developer expected *supplyAsync()* to run on *businessPool*, yet omitted the Executor argument; during an incident, tasks ran on *ForkJoinPool.commonPool*.

**Explanation:** per Java 17 API, async methods without an explicit executor use `CompletableFuture`’s default async execution facility, typically `commonPool` when parallelism suffices. Always verify the exact call site and runtime executor rather than guessing from a *businessPool* variable name.

**Action:** pass an explicit executor where isolation/bounding is needed, use non-blocking composition, and check fork/join semantics when blocking dependencies exist.

### 18.7 Java Virtual Threads on JDK 21+

Virtual threads can make I/O-bound blocking code consume far fewer OS threads in many scenarios, yet they **do not increase DB/HTTP downstream capacity** and do not fix circular dependencies between tasks/callbacks. If a task holds a semaphore, DB connection, or external rate limit while waiting for another task needing that same resource, starvation still happens.

When using virtual threads:
- Clarify where executors and resource admission impose limits.
- Do not infer in-flight request count from OS carrier thread count.
- Use virtual-thread-aware diagnostics/JFR per your JDK.
- Never hold locks/connections/semaphores while awaiting a dependent task that needs that resource.
- Enforce explicit concurrency limits instead of treating spawning many virtual threads as “unbounded capacity.”

This is an extended perspective; the Java 17 example in section 8 uses **platform threads**.

## 19. Load Testing and Failure Injection

Any pool/queue change must be tested under failure-inducing conditions, not just a single request.

### 19.1 Minimal Test Matrix

| Scenario | Stimulus | What to Measure |
| --- | --- | --- |
| Baseline | Low load, healthy dependencies | Throughput, p99, active, queue, completed |
| Burst | Short arrival spike | Peak queue, recovery time, rejections, p99 |
| Sustained overload | Arrivals > service capacity | Backpressure, memory stability, fail-fast |
| Downstream slowness | Inject 200–2000 ms latency | Worker occupancy, queue age, timeouts |
| Nested task dependency | Parent waits child on same pool | Any starvation/rejection? No infinite hang |
| Cancellation | Caller timeout, child queued/running | Does child stop? Are side effects handled? |
| Retry storm | Dependency returns errors/timeouts | Retry budget, amplification, downstream QPS |
| Worker failure | Task throws unchecked exception | Completed vs. business success, capacity recovery |
| Shutdown | Graceful shutdown with pending work | Task draining, rejection, data consistency |
| JVM restart/scale | Instance replacement | Counter resets, pool identity, pending task semantics |

**Load test stop conditions:** abort when error budgets, heap/native memory, CPU, disk, or downstream contractual limits are reached; never intentionally induce OOM just to prove bounded queues work.

### 19.2 Sound Assertions

- Bounded queues never exceed configured capacity (per queue semantics).
- Under overload, policy produces an observable outcome: rejection counts/responses, never silent drops.
- Nested-wait tests never let the process hang forever.
- After remediation, completions/business success advance and queues drain under expected load.
- Timeouts do not cause “phantom” load beyond budget from tasks running endlessly.
- Tasks are not lost on shutdown/restart outside application contracts.
- Never infer CPU/GC/latency from a single *getActiveCount()* read.

### 19.3 Watch Out for Non-Deterministic Test Timing

Do not test concurrency using *Thread.sleep(10)* and immediately asserting queue size: scheduling jitter makes tests flaky. Prefer **CountDownLatch, Phaser, barriers, or timed futures** to synchronize deterministic steps. Section 8’s example uses latches to hold the worker while `main` reads queue size, then opens the gate.

Never use long sleeps in tests to “guarantee” the scheduler finished. Tests need time-budget guards and `finally` cleanup.

## 20. Alerting and Dashboards: Alert on the Right Symptoms

### 20.1 Essential Metrics

- **active workers / pool max** per pool instance.
- **queue depth** and **oldest queued task age** if instrumented.
- **tasks accepted/s**, **tasks started/s**, **tasks completed/s** by outcome.
- **rejection rate** by policy and caller.
- **queue wait p50/p95/p99** and **execution duration p50/p95/p99**.
- **end-to-end request latency p95/p99** and error/timeout rates.
- **downstream concurrency/queue/latency**, DB pool active/waiters, rate-limit status.
- **CPU, process threads, heap/GC pauses**, to spot concurrent bottlenecks.

### 20.2 Useful Combined Signals

- **Growing queue + completed/s near 0 + active=max**: risk of stalled progress; inspect worker stacks and downstream.
- **Growing queue + high completed/s yet arrivals even higher**: arrival > capacity; need admission/scaling/optimization.
- **Empty queue + low active yet high p99**: investigate upstream/downstream of the executor rather than blaming the queue.
- **Rising rejections + abnormally low error responses**: exceptions may be swallowed or policy silently dropping.
- **Low process CPU + active=max + Future waits**: prioritize task dependencies or blocking.
- **High process CPU + active=max + computation frames**: prioritize CPU hotspots, inspect profiler.

**Never alert on a single absolute threshold** like *queueDepth > 100* across every service. Factor in throughput, service time, deadlines, queue age, saturation ratios, and error budgets per workload.

### 20.3 Separate Task Completion from Business Completion

*getCompletedTaskCount()* counts tasks that **finished executing in the executor** approximately, not business success. A task can finish by throwing an exception, logging an error, or returning a timeout result.

Dashboard example:
- *executor.completedTasks/s* rises while
- *checkout.successRequests/s* drops and
- *checkout.errors/s* rises.

That is not a healthy system. Instrument **business outcomes** separately and track child tasks still running past caller deadlines.

## 21. Recurring Reasoning Traps

| False Reasoning | Reality | How to Verify |
| --- | --- | --- |
| “maxPoolSize=100 so we’ll get 100 workers when needed” | Available queue space makes TPE enqueue first instead of scaling to max | Inspect core/max/queue and runtime `poolSize` |
| “Low CPU means the pool is idle” | Workers may be `WAITING`/`BLOCKED` holding slots | `activeCount` + thread dumps |
| “Long queue proves deadlock” | Arrival > service capacity also grows queues | Arrival/completed rates and stacks |
| “No Java deadlock means no starvation” | Future dependencies can avoid monitor cycles | Task/executor graph |
| “Increasing max threads fixes nested dependencies” | May only shift the threshold; dependency design remains broken | Load test at higher concurrency |
| “Increasing queue size fixes p99” | Queue wait and memory can both rise | Queue age, deadlines, heap/GC |
| “Future.get(timeout) cancels the child” | Only stops the caller’s wait | Child outcome/cancel state |
| “cancel(true) always stops side effects immediately” | Interruption is cooperative; downstream may still run | Idempotency, transport cancellation |
| “Completed tasks equal successful requests” | Tasks can finish with errors | Business outcome metrics |
| “CallerRunsPolicy is always safe” | Can block event loops or lock-holding callers | Caller execution context and latency |
| “DiscardPolicy prevents overload without side effects” | Can drop tasks/Futures that never complete | Rejection handler semantics |
| “Queue length 0 = no backlog anywhere” | Queues may sit in HTTP/DB/broker layers | End-to-end queues |
| “active=8 means CPU is using 8 cores” | Active workers can be blocked | OS/JFR CPU |
| “Two dumps both showing WAITING mean continuously hung” | Workers can wake/run/park between samples | Completion counters/JFR |
| “One pool recovering means the whole system recovered” | Downstream or another pool may still be overloaded | End-to-end latency/error budget |
| “Virtual threads cure database saturation” | DB concurrency remains finite | Resource budgets and downstream metrics |

## 22. Self-Check Questions and Answers

### Exercise 1 — Why Didn’t maximumPoolSize Kick In?

A TPE has *core=4, max=40* with an unbounded *LinkedBlockingQueue*. All four workers are busy and the queue holds 1,000 tasks.

**Answer:** While the queue keeps accepting tasks, the executor prioritizes queueing over growing workers beyond core. *max=40* has virtually no effect with this queue mode. Fixing it requires evaluating workload, queue capacity, concurrency, and admission policy rather than blindly tweaking one parameter.

### Exercise 2 — Single-Worker Pool Starvation

A parent running on a 1-worker pool submits a Child to the same pool, then calls untimed *child.get()*.

**Answer:** Parent occupies the sole worker while Child sits queued unable to run. Parent waits on Child, forming an execution-resource dependency cycle; it can hang forever even without a Java monitor deadlock.

### Exercise 3 — Just Add Workers?

4 workers and 4 parents all await children on the same pool. Someone proposes raising max to 8.

**Answer:** It might temporarily allow some children to run if the executor actually spawns more workers. Yet under higher load, 8 parents can wait together. Sustainable fixes break the blocking dependency / switch composition, cap fan-out, or isolate pools with proper budgets.

### Exercise 4 — Is Rejection Always a Bug?

Bounded queue capacity=100, max workers=10. The next task gets *RejectedExecutionException* during peak traffic.

**Answer:** Rejection can be an intentional design outcome when capacity is exceeded. The bug lies in **failing to handle** overload: swallowing errors, infinite retries, returning 200, or letting requests hang. Proper fail-fast responses and telemetry are required.

### Exercise 5 — Active Workers vs. CPU

Metrics show `activeCount=32/32`, CPU ~10%, queue growing.

**Answer:** Workers may be waiting on I/O, locks, Futures, or resource pools. Active does not mean consuming CPU. Inspect thread dumps, dependency spans, and downstream metrics before adding CPU.

### Exercise 6 — Does 500 Queued Tasks Mean a Specific Wait Time?

Queue has 500 tasks, current completion rate is 100 tasks/s.

**Answer:** You cannot state an exact duration from one snapshot; in a stable FIFO system with uniform tasks, queue wait might be on the order of a few seconds, yet reliable estimation requires queue age/timing, arrival variability, prioritization, and cancellation data.

### Exercise 7 — After Caller Timeout, Child Still Runs

*Future.get(100 ms)* throws `TimeoutException`. One second later, the database still receives a write from the child task.

**Answer:** Valid per semantics: timeout only caps waiting, not computation cancellation. You must design cancellation, idempotency, retry policy, and deadline propagation rather than assuming work vanished.

### Exercise 8 — DiscardPolicy with Future

A system uses `DiscardPolicy` on a saturated pool, and code calls *submit()* followed by *future.get()*.

**Answer:** Tasks can be silently dropped without completing the Future, leading to an infinite wait. Use a policy that surfaces rejection explicitly, or a custom handler reporting outcomes/cancellation per business contract.

### Exercise 9 — Same WAITING Across Two Dumps

Worker-1 is `WAITING` at *queue.take()* at t0 and t5; total service completed count rises by 200.

**Answer:** The service is making progress, yet **you cannot claim worker-1 specifically** processed those 200 tasks. Without per-worker/task evidence, conclusions remain scoped to the aggregate counter.

### Exercise 10 — CPU-Bound vs. I/O-Bound

Two executors both have 8 workers; one runs CPU computation, the other runs blocking HTTP calls.

**Answer:** Sizing strategies differ: CPU-bound work depends on cores/scheduling; blocking I/O may need different concurrency bounded by downstream capacity, memory, and deadlines. Never apply the same thread-count formula to both.

### Exercise 11 — Confirming Suspected Nested Starvation

Thread dumps show all workers in `Future.get`; queue is growing.

**Answer:** Not enough to conclude yet. Identify the Futures’ **child executor**, confirm children wait on the exact pool occupied by parents, and verify no independent completion source exists. That evidence distinguishes it from Futures slowed by downstream services.

### Exercise 12 — CallerRunsPolicy

The caller is a Netty event-loop thread. When the executor saturates, the policy runs a 2-second blocking job on the caller.

**Answer:** The event loop can be blocked for 2 seconds, stalling other connections. `CallerRunsPolicy` is appropriate only when the caller can tolerate inline execution per policy. Evaluate caller thread types first.

### Exercise 13 — Restarting the Pool to Clear the Queue

An SRE wants to call *shutdownNow()* on a production executor holding payment tasks to “clear the backlog.”

**Answer:** Dangerous: active tasks may be interrupted, unstarted queued tasks returned/abandoned, and transactions lost or left with unclear side effects. Use a designed quiesce/drain/auditable-cancel procedure with idempotency and approved recovery choices.

### Exercise 14 — Task Count Rises While Request Success Stagnates

*completedTaskCount* rises by 500/s while HTTP success/s is near 0.

**Answer:** Finishing execution in an executor does not guarantee business success. Tasks may be ending with errors, timeouts, drops, or retries. Business outcome metrics and failure logs are required.

## 23. Pre-Conclusion Incident Checklist

### 23.1 Define Scope

- [ ] Service/version, JVM PID/start time, host/pod, and exact executor pool.
- [ ] `corePoolSize`/`maxPoolSize`/queue type/capacity/rejection policy verified from runtime/config.
- [ ] Separated task arrival rate from incoming request rate, accounting for fan-out.
- [ ] Aligned timestamps/instances across metrics, dumps, and traces.

### 23.2 Confirm Saturation vs. Starvation

- [ ] Current pool active/`poolSize`, accounting for approximate accuracy.
- [ ] Queue depth **and queue wait age**, not just a single snapshot count.
- [ ] Submitted/accepted/started/completed/rejected over time.
- [ ] Business success/failed/timeouts and downstream latency.
- [ ] Worker stacks: Future/Join vs. I/O/lock vs. CPU-bound.
- [ ] Child executor and completion ownership: is there a circular capacity dependency?
- [ ] Per-pool/per-dependency concurrency limits and retry counts.
- [ ] JVM CPU, heap, GC, native thread counts, and connection pools.

### 23.3 Choose Safe Remediation

- [ ] Can admission/fan-out/retry storms be throttled first?
- [ ] Are bounded queues and overload responses aligned with semantics/idempotency?
- [ ] Can non-blocking composition replace parent workers holding slots to await children?
- [ ] Does pool isolation truly break the dependency without exceeding downstream budgets?
- [ ] Are timeout/deadline/cancellation propagation and cleanup contracts clear?
- [ ] Avoid silent discards or arbitrary `shutdownNow`.
- [ ] Have load tests / failure injection proven queue drain, task progress, and p99 recovery?

### 23.4 Write an Evidence-Based Report

Separate:
- **Observation:** “8/8 workers active, queue depth 420, completed delta≈0 over 20s.”
- **Hypothesis:** “Nested child tasks are starved because parent tasks occupy all workers.”
- **Verification:** “Locate child target executor, queue contents/traces, worker stacks, submit + get sites, JFR, and metrics.”
- **Conclusion:** only after code/runtime evidence proves the dependency path, never treating “WAITING” alone as root cause.
- **Limitations:** approximate counters, non-continuous snapshots, and cancellation/rejection effects on data.

Sample conclusion usable in an incident:

> On JVM checkout-pod-4 at 10:12–10:13 UTC, the enrichment executor has `core=max=8` and an unbounded queue. Metrics on the same instance show `active≈8`, queue depth rising `40→680`, and completed-task delta near 0. Three thread dumps show multiple workers in `FutureTask.get` inside method `enrichOrder`. Code paths confirm the awaited Futures submit children to **the same enrichment executor** while parents hold all workers. This is strong evidence of task-dependency starvation; the remediation plan removes blocking waits in the same pool, applies admission/fan-out limits, tests timeout/cancellation, and monitors queue wait and response errors post-rollout.

All numbers and identities in the sample are **hypothetical**. Never cite them as real incident data.

## 24. Official Java Documentation

- **Java SE 17 – ThreadPoolExecutor**, core/max/queue/rejection, *getQueue*, *getActiveCount*, *getCompletedTaskCount*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **Java SE 17 – Executors**, *newFixedThreadPool* and executor factories: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html
- **Java SE 17 – Future**, *get(timeout)* and cancellation semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **Java SE 17 – CompletableFuture**, *join*, *thenCompose*, and async executors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Java SE 17 – ArrayBlockingQueue**, queue capacity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **Java SE 17 – ThreadMXBean**, ThreadInfo/deadlock detection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Oracle JDK 21 – jcmd**, `Thread.print` options and diagnostic impact: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **OpenJDK JEP 444 – Virtual Threads** (JDK 21+ perspective): https://openjdk.org/jeps/444

Use JavaDoc matching the **exact version/vendor** of the running JVM; executor wrappers, framework pools, queue metrics, and thread dump tools vary by implementation.

## Takeaway

**Pool saturation** means workers/queues hit limits, **queue buildup** means work arrives faster than completion or workers are held too long, and **task dependency starvation** means pending work depends on the very workers occupied by parent tasks. All three can reinforce one another.

To diagnose accurately, never look solely at thread counts or queue depth. Combine **pool configuration → arrival/completion/queue-wait metrics → worker stacks → child executor/dependency graph → downstream CPU/I/O/lock evidence**. Sustainable fixes **break blocking dependencies, bound admission and fan-out, propagate clear deadlines/cancellation, and enforce observable backpressure and overload policies** — rather than raising `maxPoolSize` or stretching queues unconditionally.