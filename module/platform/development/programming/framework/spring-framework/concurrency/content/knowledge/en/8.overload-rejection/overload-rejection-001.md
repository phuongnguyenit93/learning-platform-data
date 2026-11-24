# Scenarios Where an Executor Rejects Tasks in Spring Framework

In a Spring application, asynchronous work is commonly submitted to a `TaskExecutor` or a `ThreadPoolTaskExecutor`. Calling `execute(...)`, `submit(...)`, or an `@Async` method **does not automatically guarantee that a task is accepted, executed, or completed successfully**. When the executor is overloaded or shutting down, a new submission call can be **rejected (task rejection)**. Understanding why rejection happens helps prevent silent task loss, growing backlogs, and retries that overload the system even further.

This lesson focuses on answering: **when an executor rejects a task, where to observe it, how Spring represents the error, and how to respond according to business requirements**. The examples use Java 17+ and Spring Framework 6.x/Spring Boot 3.x. Specific properties should be verified against the framework version your application is running.

## 1. What Exactly Is "Task Rejection"?

An executor **rejects** when there is a request to submit a task, but the executor **does not accept that task for execution under its current contract**. At the Java level, `ThreadPoolExecutor.execute(Runnable)` forwards an unaccepted submission to a `RejectedExecutionHandler`. That handler decides whether to throw `RejectedExecutionException`, run immediately on the caller, or discard the task according to its policy.

Three milestones that are often confused:

```text
Producer / Caller
       |
       | submit(task)
       v
 [Executor evaluates task] -- NOT ACCEPTED --> Rejection policy
       |
       | ACCEPTED
       v
 [Wait in queue or worker runs]
       |
       +---> Success
       +---> Exception while running
       +---> Cancelled/interrupted
       +---> Not yet run before process stops/crashes
```

- **Accepted:** the pool has accepted the task for queuing or execution. It does not yet mean the task has completed.
- **Rejected:** the task was not accepted under the normal admission policy. With `AbortPolicy`, the caller receives an exception immediately at submission time.
- **Execution failure:** the task was accepted, but business code threw an error afterward. With `submit`, the error usually resides in the `Future`; with `CompletableFuture`, the error flows through the exceptional completion mechanism.
- **Cancellation, timeout, and shutdown:** these are distinct states/lifecycle events; they may relate to rejection, but not every timeout or interrupt is a rejection.
- **Discard policy:** this is still a situation where the handler decides to **drop the task** after it cannot be accepted, yet the caller may not see an exception. Therefore, "no error" does not mean "accepted and will run."

In Spring, `ThreadPoolTaskExecutor` implements `TaskExecutor`; with a throwing policy, the call may receive Spring's **`TaskRejectedException`**, a subtype of `RejectedExecutionException`. How the error surfaces when using `@Async` depends on the call path and handler; you cannot deduce it solely from whether the method has an annotation.

## 2. Scenario 1: Both Pool and Queue Are Saturated

This is a common cause when running background work under high load. A pool has limits for `corePoolSize`, `maxPoolSize`, and `queueCapacity`. With `ThreadPoolTaskExecutor` wrapping JDK `ThreadPoolExecutor`, the general algorithm when a new task arrives is:

1. If the number of existing workers is below **core**, create a new worker for the task.
2. Once core is reached, try to put the task into the **queue**.
3. If the queue has no remaining capacity, try to increase workers up to **max**.
4. If the queue cannot accept more and max has been reached, hand the task over to the **rejection handler**.

Example:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(2);
```

Assume **all running tasks are held**, with no idle worker and no task finishing in time:

| Arriving task | Pool/queue state at evaluation | Action |
| --- | --- | --- |
| Task 1 | Workers below core | Create worker 1 |
| Task 2 | Workers below core | Create worker 2 |
| Task 3 | Core reached, queue has space | Enqueue (1/2) |
| Task 4 | Core reached, queue has space | Enqueue (2/2) |
| Task 5 | Queue full, workers below max | Create worker 3 |
| Task 6 | Queue full, workers below max | Create worker 4 |
| Task 7 | Queue full, 4 workers already active | **Rejection handler** |

Diagram:

```text
core=2, max=4, queueCapacity=2

            2 core workers           queue=2          2 extra workers
Task 1,2 -> [W1][W2]    Task 3,4 -> [Q3][Q4]   Task 5,6 -> [W3][W4]
Task 7  --------------------------------------------------> REJECT
```

**The timing condition is crucial:** this is the case where **all six accepted tasks have not completed yet**. If a worker finishes a job and takes a task off the queue before task 7 arrives, task 7 can be accepted. Do not calculate rejection rate simply from the number of requests over an entire minute; you must look at **concurrency level and queue state at the moment of submission**.

### 2.1. Why Is Setting a Large `maxPoolSize` Alone Not Enough?

If `core=2, max=20, queueCapacity=10_000`, once core is reached, new tasks normally wait in the queue. The pool **does not scale beyond core just because many tasks are waiting**; it tries the queue before creating workers beyond core. When the queue is large, the system can become terribly slow without ever triggering a capacity-based rejection.

With a virtually unbounded queue, if the submission rate remains consistently higher than the processing rate, the backlog grows and can lead to `OutOfMemoryError`. This is an **out-of-memory failure**, and should not be described as a normal rejection that can be handled gracefully.

### 2.2. Saturation Scenario Caused by Blocking I/O

A thread pool can fill up even when CPU usage is very low. For example, 8 workers are all waiting on a database connection or a slow HTTP API; new tasks sit in the queue until it is full. Adding more threads at that point may overload the DB/API even further.

Diagnosis must examine **active workers, queue size, queue wait, downstream latency, connection pools**, and rejection counts, not just CPU.

## 3. Scenario 2: Executor Has Shut Down or Is Transitioning to Closing State

JDK `ThreadPoolExecutor` rejects new tasks after `shutdown()` or `shutdownNow()`. `shutdown()` initiates an orderly shutdown: it may continue processing already-accepted tasks, but **does not accept new tasks**. `shutdownNow()` attempts to stop running tasks via interruption and drains waiting tasks from the queue on a best-effort basis; it cannot force every task blocked on I/O to stop immediately.

Java example:

```java
ExecutorService pool = Executors.newFixedThreadPool(2);
pool.shutdown();
pool.execute(() -> System.out.println("work")); // Usually throws RejectedExecutionException
```

This is an illustrative **fragment** with the JDK executor's default `AbortPolicy`. When using a custom rejection handler such as `CallerRunsPolicy` or `DiscardPolicy`, a task submitted after shutdown may be **dropped without throwing an exception**. Do not claim that every policy throws the same error.

In Spring, this scenario can happen when:

- The application context is closing, yet an HTTP request, listener, or scheduler still attempts to submit new work.
- A bean inside `@PreDestroy` calls an `@Async` service while the executor has already entered the shutdown phase.
- A background callback holds a reference to the executor and submits after the context stops.
- The application explicitly calls `shutdown()` on a shared executor too early.
- There is a race between checking `isShutdown()` and submitting: seeing that it is not shut down **does not guarantee** another thread will not close the executor right afterward.

**How to handle:** first distinguish whether this is a valid shutdown or a lifecycle ordering bug. Do not retry continuously against a closed executor; stop the producer/ingress, coordinate graceful shutdown, or hand unprocessed work off to a durable system if required by the business.

## 4. Scenario 3: `queueCapacity=0` and No Worker Available to Accept Work

`ThreadPoolTaskExecutor#setQueueCapacity(0)` uses a `SynchronousQueue`, a **direct handoff** mechanism instead of storing tasks in a queue with positive capacity.

Example:

```java
executor.setCorePoolSize(1);
executor.setMaxPoolSize(3);
executor.setQueueCapacity(0);
```

If all three workers are executing unfinished tasks, the fourth task **has nowhere to wait** and the pool cannot expand past max: rejection occurs according to the handler.

```text
queueCapacity = 0
Task A -> Worker 1 busy
Task B -> Worker 2 busy
Task C -> Worker 3 busy
Task D -> No worker for direct handoff -> REJECT
```

When a worker is idle and ready to receive, new tasks can still be accepted. `queueCapacity=0` does not mean the executor stops working; it defines **no backlog accumulation in a queue**. If max is set too high, burst traffic can create many platform threads and put pressure on memory/CPU; an explicit bound is needed.

## 5. Scenario 4: Bursts, Slow Tasks, and Starvation Create Compounding Pressure

Capacity that looks sufficient under normal conditions can still saturate due to:

- **Burst traffic:** thousands of tasks arriving within a short window.
- **Slow downstream:** all workers waiting on JDBC, HTTP, files, or locks instead of finishing.
- **Very long-running or infinitely stuck tasks:** workers never return to the queue to pick up other tasks.
- **One shared pool for multiple workload types:** slow email-sending tasks occupy all workers needed by reports with tight SLAs.
- **Interdependent tasks:** task A holds a worker and waits on task B's Future, while B sits in the same queue of an already full pool. Starvation deadlock can happen without immediate rejection at the start.
- **Too many unbounded retries:** resubmitting straight back into the overloaded pool on error, increasing both queue depth and arrival rate.

For example, a producer generates 200 tasks/sec while the system can steadily process only 100 tasks/sec. If all are still accepted, the backlog grows by roughly 100 tasks/sec in a simplified model. A 1,000-task queue can mask the problem for about 10 seconds before filling up; latency for tasks at the tail of the queue has already risen sharply before rejections begin.

**Rejection signals are a consequence of load pressure**, not necessarily the root cause. You need to identify the bottleneck: CPU quota, threads, locks, DB pool, network timeouts, downstream quota, or producer design.

## 6. Situations That Should Not Be Mistaken for Rejection

| Symptom | Is it executor rejection? | Explanation |
| --- | --- | --- |
| Task ran and threw `IllegalStateException` | No | Business/execution error; usually observed via Future/callback |
| Caller calls `Future.get(1, SECONDS)` and times out | Not automatically | Caller timed out waiting; the task may still be running |
| Task is cancelled with `cancel(true)` | Not automatically | Cancellation/interruption request differs from submission-time rejection |
| Thread pool is very slow due to a long queue | Not necessarily | The queue may not be full yet; tasks are still being accepted |
| Unbounded queue leads to out of memory | Not a normal rejection scenario | Memory exhaustion requires addressing capacity and admission earlier |
| Setting `core > max` and bean fails to initialize | No | Configuration error when creating the pool, not task rejection |
| Internal `@Async` call via `this.method()` | No | Self-invocation usually bypasses the Spring proxy; the method may run directly |
| Task submitted after `shutdown()`, default `AbortPolicy` throws | Yes | Executor is closed and no longer accepts new tasks |
| Pool max is busy, queue full, default `AbortPolicy` throws | Yes | Executor is saturated |
| `CallerRunsPolicy` runs task on caller | It is overload handling | Handler chooses to execute on the caller instead of throwing |

A custom `ThreadFactory` unable to create workers can also prevent an executor from progressing properly; this is an abnormal resource/configuration case and should not be equated with standard saturation rules. Distinguish `OutOfMemoryError`, timeout, interruption, and rejection to avoid incorrect retries.

## 7. Policies for Handling Rejection

The JDK provides four common `RejectedExecutionHandler` implementations. Spring's `ThreadPoolTaskExecutor` can receive a handler via `setRejectedExecutionHandler(...)`.

| Handler | If the pool cannot accept the task | Meaning/risk |
| --- | --- | --- |
| `ThreadPoolExecutor.AbortPolicy` | Throws `RejectedExecutionException` (Spring adapter usually converts to `TaskRejectedException`) | Caller clearly sees overload and can return an error or retry in a controlled way |
| `ThreadPoolExecutor.CallerRunsPolicy` | If not shut down, **the submitting thread runs the task immediately** | Creates backpressure, but can block HTTP request threads or scheduler threads |
| `ThreadPoolExecutor.DiscardPolicy` | Drops the task with no notification | Only suitable for tasks that truly tolerate loss; risk of silent task loss |
| `ThreadPoolExecutor.DiscardOldestPolicy` | If not shut down, drops the head of the queue and retries submission | Can drop older work and break ordering; very hard to guarantee completion |

**Especially during shutdown:** `CallerRunsPolicy` and `DiscardOldestPolicy` may **drop the task** instead of running it or throwing an error. Do not use these policies and assume that every call that does not throw an error has completed.

With `DiscardPolicy` or `DiscardOldestPolicy`, a `Future` returned by `submit(...)` may never transition to a completed state if the task is dropped without cancelling the Future. In that case, `get()` without a timeout can wait forever. Therefore, **only use task-dropping policies when the design accepts task loss and accounts for completion/cancellation signaling**.

### 7.1. When to Consider `CallerRunsPolicy`?

If the producer is faster than the consumer, pushing excess tasks back onto the caller slows down the caller and reduces the submission rate. It acts as a simple backpressure mechanism:

```text
Caller submit -> pool has space -> returns quickly
Caller submit -> pool saturated -> CallerRunsPolicy runs immediately on caller
Caller busy running task -> stops submitting further tasks for now
```

However, if the caller is an HTTP request thread, responses can unexpectedly become slow and time out. If the caller is a scheduler thread, the next scheduled trigger can be delayed. For workloads requiring low latency and clear SLA rules, **`AbortPolicy` + overload feedback** is usually easier to control.

### 7.2. Which Policy Should You Use?

No single policy fits every business requirement. You can start with the default **`AbortPolicy`** so overload is not hidden, then choose behavior based on tolerance for task loss, priority, resource limits, and calling protocol. Systems that need execution guaranteed after a restart must use a **persistent queue/job store** rather than merely changing the rejection policy.

## 8. Runnable Java 17+: Reproducing Saturation, Shutdown, and CallerRuns

This plain JDK example uses `CountDownLatch` to **hold a running task**, creating deterministic saturation conditions. It requires no Spring and does not rely on `Thread.sleep(...)` to guess CPU scheduling.

Save the entire program to **RejectionCasesDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class RejectionCasesDemo {
    private static ThreadPoolExecutor newPool(
            RejectedExecutionHandler handler) {
        return new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), handler);
    }

    private static Runnable heldTask(
            CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor abort =
                newPool(new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running =
                    abort.submit(heldTask(started, release));
            started.await();                 // Worker is busy
            Future<?> queued = abort.submit(() -> {});

            try {
                abort.execute(() -> {});
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected: saturated");
            }

            release.countDown();
            running.get();
            queued.get();
            System.out.println("accepted completed: 2");

            abort.shutdown();
            try {
                abort.execute(() -> {});
                System.out.println("unexpected after shutdown");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected: shutdown");
            }
        } finally {
            release.countDown();
            abort.shutdownNow();
        }

        ThreadPoolExecutor caller =
                newPool(new ThreadPoolExecutor.CallerRunsPolicy());
        CountDownLatch started2 = new CountDownLatch(1);
        CountDownLatch release2 = new CountDownLatch(1);

        try {
            Future<?> running =
                    caller.submit(heldTask(started2, release2));
            started2.await();                // Worker is busy
            Future<?> queued = caller.submit(() -> {});

            Thread submittingThread = Thread.currentThread();
            AtomicBoolean onCaller = new AtomicBoolean(false);
            caller.execute(() -> onCaller.set(
                    Thread.currentThread() == submittingThread));
            System.out.println("caller ran: " + onCaller.get());

            release2.countDown();
            running.get();
            queued.get();
        } finally {
            release2.countDown();
            caller.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac RejectionCasesDemo.java
java RejectionCasesDemo
```

**Deterministic stdout on a normal program run:**

```text
rejected: saturated
accepted completed: 2
rejected: shutdown
caller ran: true
```

**Why is this output deterministic?**

1. `abort` has only **one worker** and **one queue slot**. `started.await()` guarantees the worker has started `heldTask` and is waiting on `release`.
2. `queued` occupies the queue slot; the third task has no worker or queue slot left, so `AbortPolicy` throws `RejectedExecutionException` **right at `execute`**.
3. After `release.countDown()`, the worker finishes both accepted tasks. `Future.get()` waits for completion before printing `accepted completed: 2`.
4. `abort.shutdown()` stops accepting new tasks; the subsequent `execute` call is rejected even though no tasks are running.
5. With `caller`, the worker is held and the queue is full; `CallerRunsPolicy` executes the third task directly on the **submitting main thread**, so `caller ran: true`.
6. `finally` always releases the latch and requests pool shutdown to prevent the process from hanging if an error occurs before cleanup.

This example illustrates the exact mechanics of **JDK `ThreadPoolExecutor`**. Spring's `ThreadPoolTaskExecutor` uses a JDK pool underneath, while adding lifecycle management and exception types according to the Spring contract.

## 9. Spring Boot: Catching Rejection at the `@Async` Submission Point

In Spring Framework 6.x, you can create a `ThreadPoolTaskExecutor` with a bounded queue and an explicit handler, then use `@Async("notificationExecutor")`. The example below uses **Spring Boot 3.x, Java 17+**, the `spring-boot-starter-web` dependency, and a single application class.

Put all code into **src/main/java/com/example/demo/RejectionApplication.java**:

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class RejectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RejectionApplication.class, args);
    }

    @Bean("notificationExecutor")
    ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(2);
        executor.setThreadNamePrefix("notify-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

@Service
class NotificationService {
    @Async("notificationExecutor")
    public CompletableFuture<String> sendAsync(String id) {
        try {
            Thread.sleep(500); // Only simulating blocking I/O
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", e);
        }
        return CompletableFuture.completedFuture("sent:" + id);
    }
}

@RestController
class NotificationController {
    private final NotificationService service;

    NotificationController(NotificationService service) {
        this.service = service;
    }

    @PostMapping("/notifications/{id}")
    public ResponseEntity<String> submit(@PathVariable String id) {
        try {
            CompletableFuture<String> future = service.sendAsync(id);

            future.whenComplete((value, error) -> {
                if (error != null) {
                    System.err.println("Failed " + id + ": " + error);
                } else {
                    System.out.println(value);
                }
            });

            return ResponseEntity.accepted().body("accepted:" + id);
        } catch (TaskRejectedException rejected) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("executor overloaded");
        }
    }
}
```

Run using the Spring Boot plugin in the project, for example `./gradlew bootRun` (on Windows: `gradlew.bat bootRun`), then try:

```bash
curl -i -X POST http://localhost:8080/notifications/N1
```

**When the task is accepted successfully**, the response has HTTP **202 Accepted**, body:

```text
accepted:N1
```

**When the executor throws `TaskRejectedException` at submission time**, the controller responds with HTTP **503 Service Unavailable** and body:

```text
executor overloaded
```

Which outcome occurs depends on load, thread ordering, and submission timing. **A single request when the pool is idle is usually accepted**; there is no way to reliably induce a 503 from a single `curl` command example alone. To reproduce rejection consistently, use a latch/load test or send enough concurrent requests so both workers and queue are busy; the JDK example in section 8 is a deterministic test.

### 9.1. Key Points in the Spring Example

- `@EnableAsync` enables proxy-based async processing; the controller calls **another bean**, `NotificationService`, so the `@Async` method goes through the proxy.
- `@Async("notificationExecutor")` selects the exact pool bean, avoiding accidentally using a different default executor.
- `AbortPolicy` allows submission to fail **with a clear signal**; the Spring adapter emits `TaskRejectedException` per its contract.
- Errors **at submission** are caught by the `catch` block around `service.sendAsync(id)`; errors **during execution** must be observed via `future.whenComplete(...)` or another Future mechanism. These are two separate error paths.
- HTTP 202 in this example **only confirms handoff to the in-memory executor**. It **does not guarantee the notification was sent**, has no durable job status, and does not survive a crash. Real business systems need a job ID, persisted state, idempotency, and an appropriate result-retrieval/retry mechanism.
- `Thread.sleep` here simulates blocking I/O; the worker is occupied while waiting. `@Async` offloads the waiting to a pool, **it does not turn blocking JDBC/HTTP into non-blocking I/O**.
- Calling `this.sendAsync(...)` from inside the service itself bypasses the proxy under the default proxy mode, so it should not be used to test `@Async` rejection behavior.

### 9.2. Direct Execution Using `TaskExecutor`

Without `@Async`, you can inject a `ThreadPoolTaskExecutor` or `TaskExecutor` bean and submit directly. Fragment:

```java
try {
    notificationExecutor.execute(task);
} catch (TaskRejectedException ex) {
    // Handle ONLY work that has NOT been accepted by the executor.
    // For example: record rejection metric and respond with overload.
}
```

This is a fragment, not a standalone Java class: `notificationExecutor` and `task` must be injected/created beforehand. For an execution path using only JDK `ThreadPoolExecutor`, the exception type is usually `RejectedExecutionException`; for Spring `TaskExecutor`, check for `TaskRejectedException`.

Do not lump every exception into a single `catch (Exception e)` and retry: business exceptions, timeouts, and rejections have different root causes.

## 10. Operational Signals and How to Diagnose

When `TaskRejectedException` occurs, check that **the right executor was selected**, since applications often have multiple pools for notifications, reports, schedulers, or request handling. Useful getters on `ThreadPoolTaskExecutor`:

| Metric / Info | Diagnostic question |
| --- | --- |
| `getCorePoolSize()` | What is the configured core size? |
| `getMaxPoolSize()` | Is there an explicit max limit? |
| `getPoolSize()` | How many workers has the pool scaled to? |
| `getActiveCount()` | How many workers are busy? |
| `getThreadPoolExecutor().getQueue().size()` | How many tasks are waiting? |
| Queue remaining capacity | Does the queue still have space? |
| `getThreadPoolExecutor().isShutdown()` | Has the executor begun shutting down? |
| Rejection count | How many submissions have failed? |
| Queue wait / task duration | Are tasks slow due to queuing or due to execution? |

Pool/queue getters are **snapshots** that can change immediately after each read. Do not make a business decision like "there is space, so it will definitely be accepted" just because you saw the queue wasn't full; between the check and the submission, more tasks or a shutdown may happen.

### Symptom-Based Analysis

| Observation | Cause to investigate |
| --- | --- |
| Active near max, queue full, rejections rising | Capacity saturation; slow workload; burst |
| Low CPU, high active, large queue | Workers waiting on DB/HTTP/locks; check downstream |
| High CPU, high active, dropping throughput | CPU contention, too many workers, CPU-bound tasks |
| Sudden rejections right during deploy/shutdown | Producers still submitting to an executor that is closing |
| No rejections seen, but queue wait keeps climbing | Queue too large or a discard policy is hiding dropped work |
| Requests suddenly take many seconds, no exception | `CallerRunsPolicy` may be running tasks on the caller |
| Future waits forever while no worker is running it | Task may have been discarded or hit starvation; check policy and queue |

When Micrometer/Actuator is available, record metrics for active workers, queue depth, tasks accepted/completed/failed/rejected, queue wait time, and execution time. Add a correlation ID and executor name to distinguish workloads; a log saying only "thread pool full" is rarely enough to pinpoint the cause.

## 11. Responding Properly When Tasks Are Rejected

### 11.1. Do Not Retry Unboundedly Immediately in the Caller

Suppose the queue is already full because downstream is slow. If 100 requests all retry continuously without bounds, they keep contending for CPU and RAM and make recovery harder.

Better strategies depending on the goal:

1. **Limit ingress:** rate limiting, bulkhead/semaphore, per-user or per-job-type quotas, or reducing producer count.
2. **Return meaningful errors:** APIs can return HTTP 503 when infrastructure is temporarily overloaded; HTTP 429 when client rate-limit policies are exceeded. Consider `Retry-After` when there is a well-defined retry schedule.
3. **Bounded retries:** exponential backoff, jitter, overall timeout, and max retry count; do not retry if the operation is not idempotent and has no deduplication mechanism.
4. **Persist critical jobs:** write to a database/job store or message broker with acknowledgment and reprocessing; the worker pool is just one consumer.
5. **Isolate workload groups:** use separate pools for high-priority workloads and slow workloads to avoid starvation.
6. **Reduce task count/batch load:** if 1,000 tiny tasks create excessive overhead, batch them when business logic permits.

**Retrying does not increase capacity by itself.** If a dependency is down or the pool has already shut down, retrying repeatedly to the same target will not improve processing capability.

### 11.2. Define What "Accepted" Means in the API Contract

An endpoint returning 202 right after the executor accepts a task only guarantees **it was handed off to an in-memory pool**. If the process crashes before the worker runs, the task can be lost. For critical work, decide what is required:

- Only **best effort** needed: task loss under overload may be acceptable, but you must record metrics and expose status.
- **At-least-once** needed: persist the job to durable storage before acknowledging, have the consumer ack after processing, and support retries.
- **No duplicate side effects** needed: use an idempotency key, deduplication, or appropriate transaction/outbox pattern. End-to-end "exactly once" does not come automatically from using an executor.
- **Completion within a deadline** needed: explicit admission control and deadlines; a long queue can cause tasks to expire before they even start.

### 11.3. Do Not Forget Tasks Already Accepted That Have Not Run Yet

Configuring graceful shutdown can allow running tasks and queued tasks to finish when the context closes in an orderly way. However, shutdown timeouts, kill signals, or crashes can still lose in-memory tasks. Therefore, evaluate both **accepted-but-pending** and **rejected-before-acceptance** instead of counting only submission-time exceptions.

## 12. Spring `@Scheduled`, `@Async`, and Related Lifecycles

A `@Scheduled` method can submit work to an `@Async` executor:

```java
@Scheduled(fixedDelay = 5_000)
public void scheduleBatch() {
    notificationService.sendAsync("daily");
}
```

This is a fragment and assumes `notificationService` is **another bean** that is injected. When the scheduler triggers at a moment when the executor is already full, `sendAsync(...)` can be rejected. Without catching and observing the rejection, that scheduled trigger may **fail to dispatch any work**. If `CallerRunsPolicy` is used, the scheduler thread may run the task itself and delay other scheduled executions.

Important points:

- **The scheduler decides when to trigger**, while the executor decides which worker/queue processes the task.
- `fixedDelay` measures the delay after the **scheduled method returns**, and does not automatically wait for the `@Async` background task to finish if the method only submits and returns.
- During shutdown, the scheduler may still fire while the executor has already begun closing if lifecycles are not coordinated; prevent producers from continuing to submit work to a stopped pool.
- If a job must run exactly once across multiple replicas, `@Scheduled` and `ThreadPoolTaskExecutor` alone **do not provide distributed guarantees**. You must use a separate coordination mechanism.

Do not handle overload by raising `maxPoolSize` toward infinity: reducing immediate rejections can exhaust threads or bring down downstream systems faster.

## 13. Common Mistakes

**Mistake 1 — Assuming a task that did not throw an exception has already finished.** A successful `execute` call only means accepted. The task may still be waiting in the queue, still running, or fail later.

**Mistake 2 — Configuring only `maxPoolSize` while ignoring the queue.** `ThreadPoolExecutor` prefers queuing once core is reached; a large max does not increase workers if the queue is not full.

**Mistake 3 — Using an unbounded queue to "avoid rejection."** This shifts pressure to RAM and queue wait time; it can cause OOM rather than giving infinite capacity.

**Mistake 4 — Confusing business errors with `TaskRejectedException`.** Exceptions from task code after execution begins must be handled via Future/callback; do not retry blindly on a generic exception.

**Mistake 5 — Using `DiscardPolicy` for work that must complete.** Tasks can be lost silently. A Future may wait forever if a task is dropped without being cancelled.

**Mistake 6 — Using `CallerRunsPolicy` without accepting a slower caller.** Under overload, HTTP/scheduler threads can be held up; clients experience sudden latency spikes.

**Mistake 7 — Retrying immediately without bounds into a full pool.** Causes a retry storm and worsens the backlog.

**Mistake 8 — Running blocking tasks on a few workers while watching only CPU.** Low CPU does not mean the pool still has capacity; workers may be waiting on I/O.

**Mistake 9 — Submitting inside `@PreDestroy` after the executor has closed.** Uncoordinated lifecycles cause tasks to be rejected right during shutdown.

**Mistake 10 — Seeing `@Async` and assuming self-invocation also runs in the background.** `this.method()` usually bypasses the proxy. You cannot rely on self-invocation tests to evaluate executor behavior.

**Mistake 11 — Catching rejection and still returning 202 "accepted."** When `AbortPolicy` rejects, you must reflect the failure status or persist the work to another mechanism before acknowledging.

**Mistake 12 — Treating a rejection policy as a data durability solution.** All overload-handling policies only operate on the in-process submission path. Recovering after a crash requires persisted state/a persistent queue.

## 14. Practical Troubleshooting Checklist

When you detect that an executor is rejecting tasks, you can follow this sequence:

1. **Identify the right executor and timing:** pool name, task name, caller, shutdown vs normal runtime.
2. **Read the actual configuration:** `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection handler, shutdown timeout.
3. **Measure state:** active/pool size, queue depth/remaining capacity, queue wait, task run time, rejection count.
4. **Identify the bottleneck:** CPU, DB connection pool, HTTP timeout, locks, I/O, burst traffic, or starvation.
5. **Classify the impact:** unaccepted tasks, queued tasks, tasks failing after acceptance, tasks at risk of loss on restart.
6. **Apply a policy aligned with business needs:** 503/429 where appropriate, retries with backoff and idempotency, rate limits, admission control, or a durable job store.
7. **Verify shutdown behavior:** no producer still submitting while the pool is closing, a bounded graceful shutdown timeout, and a recovery plan.
8. **Load test again:** use controlled latches/benchmarks to reproduce saturation and verify accepted, rejected, and completed task counts.

Do not run `Thread.sleep(...)` a few times and conclude the queue is definitely full; thread scheduling is non-deterministic. When you need proof, hold workers with `CountDownLatch` to guarantee saturation conditions like in the Java example above.

## 15. Self-Check Questions

**Question 1.** A pool has core=2, max=4, queue=2. Six tasks have been accepted and none have finished yet. Is the seventh task guaranteed to be accepted?

**Answer:** Under the condition that all four workers are busy, the queue holds two tasks, and no worker is idle, the seventh task **has no remaining capacity** and goes to the rejection handler. The handler may throw, run on the caller, or drop the task depending on configuration.

**Question 2.** Why does `maxPoolSize=100` not help increase workers if `queueCapacity` is extremely large?

**Answer:** After reaching core, the executor prioritizes placing tasks into the queue; it only scales workers beyond core when the queue can no longer accept tasks.

**Question 3.** Is a new task submitted after `shutdown()` automatically queued to run after a restart?

**Answer:** No. A shut-down executor does not accept new tasks under its normal mechanism. There is no automatic persistence/restart queue.

**Question 4.** Does `CallerRunsPolicy` throw `RejectedExecutionException` when the pool is saturated?

**Answer:** Usually it runs the task on the caller itself if the executor has not shut down. The caller may be blocked, which provides backpressure. If the executor has already shut down, the policy may drop the task.

**Question 5.** A task is submitted successfully, then throws an exception after 2 seconds. Is this a rejection?

**Answer:** No. The task was accepted and then **failed during execution**; you need to observe the `Future`/`CompletableFuture` or the handler for the corresponding task type.

**Question 6.** Can overload be solved simply by retrying immediately in an infinite loop?

**Answer:** No. A retry storm increases load. You need backoff, limits, jitter, idempotency, and admission control or a durable queue when required by the business.

**Question 7.** Does `queueCapacity=0` mean the executor always rejects?

**Answer:** No. It uses direct handoff; a task is accepted when a worker can take it or the pool can still expand. Only when max workers are all busy does it go to the handler.

**Question 8.** Why does HTTP 202 right after `@Async` submission not guarantee the work will complete?

**Answer:** It only reflects successful handoff to an in-memory executor; the task can still fail later, be interrupted, or be lost if the process crashes. You need persistent job tracking if execution must be guaranteed.

## References

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Javadoc — TaskRejectedException: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskRejectedException.html
- Java SE 17 API — ThreadPoolExecutor, Rejected Tasks section: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 API — RejectedExecutionHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html
