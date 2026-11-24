# RejectedExecutionHandler and TaskRejectedException: Handling When an Executor Refuses More Tasks

In concurrent Spring applications, **submitting a task to an executor does not guarantee the task will always be accepted**. When a thread pool runs out of capacity to accept work, or has stopped accepting new tasks, the submission call can be **rejected**. At the Java layer, **RejectedExecutionHandler** decides what action to take when **ThreadPoolExecutor** refuses a task. At the Spring layer, **TaskRejectedException** is the exception representing that a **TaskExecutor** did not accept a task under the Spring contract.

This topic belongs to the **Overload and Rejection** group of **Spring Framework - concurrency**. After this lesson, you will be able to identify when rejection happens, choose an appropriate policy, distinguish submission-time errors from in-task errors, integrate with **@Async**, test overload deterministically, and protect your application from silent task loss.

## 1. Why Is a Task Rejected?

A thread pool has finite processing capacity. For example, a service receives many report-generation requests, where each report occupies a worker and queries the database for several seconds. If the task submission rate exceeds the processing rate, the system must decide whether to **queue, create more workers, run on the submitting thread, or reject**.

**ThreadPoolExecutor** typically evaluates these main steps:

1. When the current number of workers is less than **corePoolSize**, try to create a new worker to execute the task.
2. When enough core workers already exist, try to place the task into **workQueue**.
3. If the task cannot be placed into the queue, try to create additional workers up to **maximumPoolSize**.
4. If the task still cannot be accepted, invoke **RejectedExecutionHandler**.
5. An executor that has **shut down** also stops accepting new tasks; in this state, rejection can occur even if the pool is not busy.

~~~text
Caller -> execute(task)
               |
        Pool below core?
          | Yes       | No
          v           v
     Create worker   Try queue.offer(task)
                      | Has space    | Not accepted
                      v              v
                    Queue      Room below max?
                                  | Yes    | No
                                  v        v
                             Create worker REJECT
                                           |
                                 RejectedExecutionHandler
~~~

This is a simplified diagram of the **task admission path** and does not depict every concurrency and shutdown check in the JDK implementation. The relationship among **corePoolSize**, **maxPoolSize**, and **queueCapacity** is crucial:

| Configuration | Behavior under load |
| --- | --- |
| Positive bounded queue | After reaching core workers, tasks are normally queued; only when the queue is full does the pool expand up to max. |
| Very large / virtually unbounded queue | Tasks keep waiting in the queue, so **maxPoolSize** may rarely take effect. |
| **queueCapacity = 0** in ThreadPoolTaskExecutor | Uses **SynchronousQueue** for direct handoff; there is no buffer holding waiting tasks. When handoff fails, it tries adding workers and then rejects. |
| Executor has shut down | Rejects new submissions according to the current policy, regardless of whether the queue appears to have space. |

**Rejected does not mean the task ran and failed.** Rejection happens at the **admission boundary**: the task may never have run at all. A business error inside a worker is a different event; the two situations require separate handling and monitoring.

## 2. RejectedExecutionHandler Is Java's Contract

In the **java.util.concurrent** package, the **RejectedExecutionHandler** interface has one abstract method:

~~~java
void rejectedExecution(Runnable task, ThreadPoolExecutor executor);
~~~

This is a **shortened signature** used to explain the API; the actual type is declared in **java.util.concurrent.RejectedExecutionHandler** with parameters **Runnable r** and **ThreadPoolExecutor executor**.

The handler is invoked by **ThreadPoolExecutor** when it does not accept a task through the **execute** path. Depending on the handler, the outcome can be:

- **Throw an exception** so the caller knows submission was refused.
- **Run the task immediately on the calling thread** to create backpressure on the sender.
- **Drop the task**, with or without evicting another task, depending on the policy.
- Execute a **custom policy** written by the application, though the policy must clearly define behavior, responsibility toward the task/future, and observability.

The **Runnable** passed to the handler may be the original task or a wrapper such as **FutureTask**, especially when the caller used **submit**. Therefore, writing a custom handler that silently drops a task can leave behind a **Future that never completes**.

**Not every Spring TaskExecutor is a ThreadPoolExecutor.** For example, **SimpleAsyncTaskExecutor** has its own concurrency-limiting mechanism and does not automatically turn into a pool using the JDK's four rejection policies. In this lesson, **RejectedExecutionHandler** mainly applies to **ThreadPoolExecutor** and **ThreadPoolTaskExecutor** wrapping it; **TaskRejectedException** is the broader concept on the Spring side.

## 3. Four Built-in Rejection Policies in ThreadPoolExecutor

The JDK provides four direct implementations of **RejectedExecutionHandler**:

| Policy | When a task is not accepted | Consequences to consider |
| --- | --- | --- |
| **AbortPolicy** | Throws **RejectedExecutionException** | Explicit rejection; the caller can record it and return an appropriate error/response. This is the default for ThreadPoolExecutor. |
| **CallerRunsPolicy** | If the pool has not shut down, **the thread calling execute runs the task itself** | Creates backpressure by slowing down the caller; breaks the assumption that work always runs on another worker. If shut down, the task is dropped. |
| **DiscardPolicy** | Drops the task and **throws no exception** | Can silently lose work; the **Future** of the dropped task may never complete. |
| **DiscardOldestPolicy** | If the pool is still active, drops the task waiting at the head of the queue and retries submitting the new task | Can lose an older task and leave its future incomplete; when no suitable waiting task exists, retrying may still fail. |

**AbortPolicy** is usually the easiest choice to control for tasks where the caller needs to know whether the work was accepted. The caller can report overload or decide on bounded retries.

**CallerRunsPolicy** is useful when the intent is to make the sender pay the execution cost, thereby slowing down the rate of new submissions. However, it **can force an HTTP request thread to execute a long task**, affecting latency or breaking assumptions around MDC, transactions, and thread context.

**DiscardPolicy** should only be considered when a task can truly be dropped **without anyone waiting for its result or needing confirmation of success**. For example, non-critical telemetry signals may be dropped in a controlled manner, whereas business tasks that must complete are not a good fit.

**DiscardOldestPolicy** does not guarantee fairness or safety for tasks with a Future. Dropping the task at the head of the queue can leave the corresponding Future pending unless explicitly cancelled. With an unbuffered **SynchronousQueue**, do not assume there is always an old task in the queue to evict; this policy is especially hard to reason about in direct-handoff configurations.

### Which Policy Is the Default?

When using **ThreadPoolExecutor** without specifying another handler, the JDK uses **AbortPolicy**. Spring's **ThreadPoolTaskExecutor** also relies on this configuration at the pool layer if the application does not override the handler. When the Java layer throws **RejectedExecutionException**, the Spring layer can translate it into **TaskRejectedException** per the **TaskExecutor** contract.

The policy may differ if the project **explicitly configures setRejectedExecutionHandler**, an integration framework supplies its own executor, or another wrapper class is involved. When analyzing a real failure, always inspect the actual executor configuration.

## 4. Runnable Java 17 Example: AbortPolicy and CallerRunsPolicy

To avoid relying on scheduler luck, we use **CountDownLatch** to keep a worker busy. The pool has **one worker** and **one queue slot**; the third task will be rejected. Then we switch the handler to **CallerRunsPolicy** to verify the task executes immediately on the submitting thread.

Save as **RejectionPoliciesDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class RejectionPoliciesDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        Thread submittingThread = Thread.currentThread();

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // First worker is held; the next task goes into the queue.
            pool.execute(() -> { });

            System.out.println("Queue is full: "
                    + (pool.getQueue().size() == 1));

            boolean aborted = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                aborted = true;
            }
            System.out.println("AbortPolicy rejected: " + aborted);

            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.CallerRunsPolicy());

            AtomicBoolean ranOnCaller = new AtomicBoolean(false);
            pool.execute(() -> ranOnCaller.set(
                    Thread.currentThread() == submittingThread));

            System.out.println("CallerRuns on submitting thread: "
                    + ranOnCaller.get());
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 RejectionPoliciesDemo.java
java RejectionPoliciesDemo
~~~

**Stdout** under normal conditions (worker starts within 5 seconds):

~~~text
Queue is full: true
AbortPolicy rejected: true
CallerRuns on submitting thread: true
~~~

**Why is the output deterministic?**

1. The first task calls **workerStarted.countDown()**, then waits on **releaseWorker**. Main waits until the task has actually started running.
2. The pool has only one worker and one queue slot. When the second task is submitted, the worker is still held, so that task takes the queue slot.
3. The third task cannot create another worker because **core=max=1** and cannot enter the queue. **AbortPolicy** throws an exception.
4. We replace the handler with **CallerRunsPolicy**. A subsequent task hits the same saturated state; the handler runs the lambda **directly on submittingThread**. Thread identity comparison returns true.
5. **finally** opens the latch, shuts down the pool, and awaits termination to avoid leaving background threads behind after the example.

The program checks **structural conditions and thread identity**, rather than relying on printing thread names that may vary. If the test times out before the worker starts, the program throws **IllegalStateException** instead of asserting an invalid stdout.

This is **plain Java ThreadPoolExecutor** so you can use javac/java. For Spring's **ThreadPoolTaskExecutor**, the underlying task admission path is similar, but rejection exceptions are represented according to the Spring contract.

## 5. Scenario When Submitting a Future: Avoiding Silent Task-Dropping Policies

Distinguish **execute** and **submit**:

- **execute(Runnable)** simply dispatches work; with AbortPolicy, rejection is usually thrown straight to the caller.
- **submit(Runnable/Callable)** creates a **Future** representing the result, then submits the wrapper task to the executor. Submission-time rejection can occur **before submit returns a Future**.
- If the handler **silently drops the task**, the submit path may still return an already-created Future, yet **no worker will ever complete it**.

Illustrative example in a **saturated pool** scenario:

~~~java
pool.setRejectedExecutionHandler(
        new ThreadPoolExecutor.DiscardPolicy());

java.util.concurrent.Future<?> future =
        pool.submit(() -> System.out.println("Important work"));
~~~

This is an **illustrative code snippet**, assuming **pool** is a running ThreadPoolExecutor that has reached both worker and queue limits; it is **not a standalone program**. In this situation, DiscardPolicy can cause submit to return an incomplete Future; **future.get() may wait indefinitely** because the task is never executed. If this happens, you need a cancel/timeout policy and actual state verification.

**Do not use DiscardPolicy just to "stop seeing rejection errors"**. Losing the exception does not mean the system processed the work. For tasks involving payments, data persistence, or guaranteed notifications, business integrity requires proper admission, response, retry, or durable queue mechanisms.

Similarly, **DiscardOldestPolicy** can evict a task already in the queue. If that task is a Future wrapper, code waiting on it can get stuck unless proper cancellation logic exists. Recent Javadocs also recommend considering cancelling the Future and recording eviction in custom policies.

## 6. TaskRejectedException: Exception of the Spring TaskExecutor Contract

Spring provides **org.springframework.core.task.TaskRejectedException**. It **extends java.util.concurrent.RejectedExecutionException**, so it can be caught specifically in Spring applications or caught by its parent type in general JDK executor integration.

~~~text
java.lang.RuntimeException
    |
    +-- RejectedExecutionException  (java.util.concurrent)
           |
           +-- TaskRejectedException  (org.springframework.core.task)
~~~

**Meaning:** a Spring **TaskExecutor** did not accept the submitted task. It is a signal about **work admission capacity**, not a business exception arising inside an executed task.

Common situations leading to this error:

- Pool workers have reached **maxPoolSize** and the queue cannot accept any more tasks.
- The executor has **shut down** or no longer permits submissions.
- Another TaskExecutor implementation has its own overload rules and expresses refusal via TaskRejectedException.
- The underlying rejection policy throws **RejectedExecutionException**, which **ThreadPoolTaskExecutor** wraps per the Spring contract.

**Note on custom handlers:** if a handler is configured to **silently drop the task** or **execute the task on the caller** and return normally, **no TaskRejectedException may be thrown**, even though the rejection path was triggered. If the handler throws a runtime exception other than RejectedExecutionException, do not assume Spring always converts every such exception into TaskRejectedException.

### How Java and Spring View the Same Situation

| Layer | Types used | Result when AbortPolicy rejects |
| --- | --- | --- |
| JDK ThreadPoolExecutor | RejectedExecutionHandler, RejectedExecutionException | **RejectedExecutionException** at the submit/execute site. |
| Spring ThreadPoolTaskExecutor | setRejectedExecutionHandler, TaskRejectedException | **TaskRejectedException**, potentially carrying RejectedExecutionException as its cause. |
| Spring @Async called via proxy | Future/CompletableFuture + executor | Calling through the proxy can **throw TaskRejectedException immediately**; if accepted, worker errors can arrive via the future. |

Catching this exception has practical value when bounding pools. For instance, an API needs to distinguish "the system is too busy to accept new work" from "the work was accepted but computation failed."

## 7. Configuring ThreadPoolTaskExecutor and Rejection Policies

In Spring, **ThreadPoolTaskExecutor** supports configuring **corePoolSize**, **maxPoolSize**, **queueCapacity**, and **setRejectedExecutionHandler(...)**. The setter for the handler is inherited from Spring's executor configuration base class.

This example shows **classes inside an application with a Spring Context**, not a standalone file run with plain javac.

**ReportExecutorConfig.java**:

~~~java
package example.concurrent;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ReportExecutorConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        // Spring initializes the bean and manages the executor lifecycle.
        return executor;
    }
}
~~~

This configuration allows at most **4 workers** and a waiting queue of up to **8 tasks**. When the **2 core workers** are busy, the pool normally prefers placing tasks into the queue; only when the queue is full does the pool try to grow workers up to 4. Once all admission capacity is exhausted, **AbortPolicy** rejects and Spring signals **TaskRejectedException** to the submission site.

**Do not infer from maxPoolSize=4 alone that the pool always runs exactly four workers.** Under normal load, it may have only two workers or fewer; these parameters are thresholds, not a guarantee of the thread count present at all times.

**Operational conditions:** the numbers **2/4/8** are illustrative only. For real workloads, weigh CPU-bound vs I/O-bound characteristics, task duration, queue wait, connection pool limits, and overload policy.

### Which Task Does the Handler Receive?

The handler receives the **Runnable** the executor attempted to submit. If the task is already wrapped in a FutureTask, logging every task via **toString()** or retaining tasks in a separate collection can cause overhead or data leaks. A custom handler should do minimal work, record a counter, and make a verifiable decision.

Example **configuration snippet** to count and rethrow an exception:

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong rejectedCount = new AtomicLong();

executor.setRejectedExecutionHandler((task, pool) -> {
    rejectedCount.incrementAndGet();
    throw new RejectedExecutionException("Executor is full or stopped");
});
~~~

This is an **illustrative snippet during executor configuration** with an existing **executor** variable. Because the handler throws **RejectedExecutionException**, the caller receives an error signal; **ThreadPoolTaskExecutor** can wrap it into **TaskRejectedException**. A simple counter only measures how many times the handler was invoked **on that instance** and does not replace properly tagged/aggregated metrics in production.

## 8. Integrating with @Async: Two Different Failure Points

Suppose a bean executes reports on the executor from section 7:

**ReportService.java**:

~~~java
package example.concurrent;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        if (reportId.isBlank()) {
            throw new IllegalArgumentException("reportId must not be blank");
        }
        return CompletableFuture.completedFuture("report:" + reportId);
    }
}
~~~

Another Spring-managed bean calls this method **through the proxy**:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.core.task.TaskRejectedException;

try {
    CompletableFuture<String> future = reportService.generate("r-17");

    future.whenComplete((value, error) -> {
        if (error == null) {
            System.out.println("Done: " + value);
        } else {
            System.err.println("Task execution failed: " + error.getMessage());
        }
    });
} catch (TaskRejectedException rejected) {
    System.err.println("Unable to accept work: "
            + rejected.getMessage());
}
~~~

This is an **illustrative snippet inside a caller method** that has ReportService injected; Spring code requires appropriate dependencies and bean configuration. This example demonstrates:

**Case A — rejected at submission:** the pool is full or stopped; the call through **@Async** can throw **TaskRejectedException** immediately on the calling thread. There may not even be a **CompletableFuture** returned to attach **exceptionally()** or **whenComplete()** to.

**Case B — task accepted but logic failed:** for example, a blank reportId causes the worker to throw **IllegalArgumentException**. With a **CompletableFuture** return type, the caller observes the error through the future (such as whenComplete, exceptionally, or join). This is **not** a rejection.

**Case C — success:** the task is accepted, executed, and the future completes with value **report:r-17**. Log output ordering across multiple requests/workers is not guaranteed.

Distinguishing these three cases is essential when reporting errors to callers or deciding on retries. **Do not treat every CompletionException/ExecutionException as overload**.

**@Async does not handle overload for you.** Under the normal proxy model, calling from the same object via **this.generate(...)** bypasses the interceptor, causing unexpected thread-switching behavior. To use @Async, you must enable **@EnableAsync** or equivalent configuration and call through a Spring proxy. If **CallerRunsPolicy** is configured, an @Async method may even run on the caller's thread when the pool saturates.

### Async void and Error Handling

With **@Async void**, the caller has no Future to retrieve exceptions from inside the worker. Spring provides **AsyncUncaughtExceptionHandler** for this case. However, a rejection exception **before the task is accepted** still belongs to the submission path; do not rely solely on the worker error handler.

If the business needs to know the outcome, use **Future/CompletableFuture** with error monitoring or an appropriate durable job mechanism, rather than submitting a void task and treating the method's return as a guarantee of success.

## 9. CallerRunsPolicy: Backpressure With a Semantic Cost

**CallerRunsPolicy** is popular because it is relatively simple: when the pool is saturated and has not shut down, the **thread calling execute** runs the task itself. When the caller is an HTTP request thread, that means calling **execute** or an **@Async** proxy method can block until that unit of work finishes.

~~~text
Before saturation:
HTTP thread -> submit -> worker processes -> HTTP thread free

During saturation with CallerRunsPolicy:
HTTP thread -> submit
             -> runs entire task directly on HTTP thread
             -> submit returns after task completes
~~~

**Benefits:** slows down the sender, helping reduce the submission rate of new tasks and avoiding immediate task drops while the pool is still active.

**Trade-offs:**

- HTTP request response latency can spike sharply; it can even exhaust server request threads.
- Code expected to run in the background executes on the same thread as the caller. Assumptions around **ThreadLocal**, MDC, transactions, or tracing must be reviewed.
- If the task holds locks or synchronously depends on another task, running directly on the caller can cause subtle bottlenecks or stalls.
- **Once the executor has shut down, CallerRunsPolicy does not run the task and drops it**. Therefore, never use this policy as a guarantee that every task will execute.

**Do not choose CallerRunsPolicy merely because you want "never reject"**. It creates backpressure by blocking the caller while doing work, which may make sense for internal producer workers but has major impact when the sender is a user-facing request thread.

## 10. Writing a Responsible Custom RejectedExecutionHandler

Custom handlers are often needed for observability and overload coordination. A safe, predictable pattern is to **record the rejection and throw an explicit exception**, like the AtomicLong example above. If you want to route the task to another mechanism, you must design an admission contract.

Key principles:

1. **Be clear about whether the task was accepted.** A handler must not return normally while silently losing a job the caller believes was accepted.
2. **Do not block for long inside the handler.** The handler runs on the submitting thread; waiting indefinitely for queue space or retrying continuously can stall request threads and cause deadlocks.
3. **Avoid unbounded recursive retries inside the handler.** If the pool remains full or has shut down, repeatedly calling execute(task) can create a non-progressing loop.
4. **Keep observability operations lightweight.** Record counters, pool state, and an appropriate correlation ID; avoid logging sensitive data or serializing entire Runnable/FutureTask objects.
5. **Distinguish shutdown from saturation.** The same rejection API can be called for two different operational reasons; inspect executor state and lifecycle when handling.
6. **Account for an existing Future.** If a task is evicted from the queue, a caller waiting on its Future needs the corresponding cancel/failure state if the policy allows.
7. **Respect resource policies.** Spawning unbounded threads inside a handler to avoid rejection merely shifts the bottleneck outside the pool.

A custom handler can also hand work off to a durable queue, but that requires a proper contract for persistence, acknowledgment, idempotency, retries, and errors. Do not treat `execute()` returning as proof the task was safely persisted if the write can fail.

## 11. What Should an Application Do When Receiving TaskRejectedException?

The appropriate reaction depends on the goal of the call.

| Task type | Potentially suitable option | What to avoid |
| --- | --- | --- |
| Synchronous HTTP request needing an immediate result | Return an intentional overload error, such as **HTTP 503** when the service is temporarily unable to accept work; optionally include Retry-After if you actually know when to retry. | Pretending to return success when the task was not accepted. |
| API limited by quota or rate limit | **HTTP 429** when the reason is caller rate limiting, with a clear retry policy. | Using 429 indiscriminately for every resource-exhaustion error regardless of cause. |
| Jobs that must not be lost | Admit via a durable queue/job store with idempotency and clear state. | Using DiscardPolicy or an in-memory executor as long-term storage. |
| Best-effort tasks | May drop after measuring and documenting the acceptable data-loss policy. | Letting callers mistake a drop for completion. |
| Internal processing where the producer can slow down | Backpressure or bounded retries; consider CallerRunsPolicy when the thread contract permits. | Unbounded retry loops with no deadline. |

**HTTP 503/429 are protocol- and business-layer choices**, not HTTP status codes automatically assigned by Spring to every TaskRejectedException. An application can use **@ControllerAdvice**, exception mapping, or an API gateway layer to translate overload according to its contract. Do not promise an exact retry time if the system cannot compute it.

If a job-creation request returns **202 Accepted**, return 202 only when the system has truly **accepted the work under its promised contract**. A rejected call to an in-memory executor does not qualify as accepted.

## 12. Retrying on Overload: Must Be Bounded and Intentional

Retrying is not always right. A task can be rejected due to shutdown (retrying on the same executor is futile), downstream overload, an undersized pool, or a brief burst. **Simultaneous, immediate retries** when all callers hit rejection together usually make the system busier.

A controlled retry policy needs:

- **A maximum attempt count** and an overall deadline.
- **Exponential backoff with jitter** where appropriate to avoid a thundering herd of simultaneous retries.
- **Idempotency** for operations with side effects: creating orders, writing invoices, or sending notifications must not duplicate upon retry.
- **Reason discrimination**: temporary saturation, executor shutting down, invalid request, and business errors; do not retry all of them identically.
- **System-wide load awareness**: extra retries may simply choke the DB or an external API, even if the executor accepts the task on the next attempt.

If the handler itself sleeps or blocks to retry, that time is spent on the **submitting thread**, which may be an HTTP request thread. It is usually better to place retries at the orchestration/caller layer with an explicit deadline, rather than hiding them inside RejectedExecutionHandler.

**Key takeaway:** retrying is only a resubmission strategy, not a guarantee of correctness or durability. A system that must guarantee zero job loss needs reliable persistence and admission confirmation.

## 13. Monitoring Overload Without Misreading Metrics

Metrics to observe for **ThreadPoolTaskExecutor**:

| Metric | Meaning |
| --- | --- |
| **getActiveCount()** | Number of workers currently executing tasks at observation time. |
| **getPoolSize()** | Current number of workers, not necessarily always equal to max. |
| **getCorePoolSize() / getMaxPoolSize()** | Configured thresholds to understand scaling bounds. |
| **getQueueSize()** | Number of tasks waiting in the queue, only a snapshot at read time. |
| **Rejected task count** | Must be measured directly or via proper instrumentation; increases indicate submissions were refused under a throwing policy. |
| **Task wait/run duration** | Distinguishes bottlenecks caused by queue wait vs CPU or I/O. |
| **HTTP latency, error rate, downstream saturation** | Checks impact on users and dependent services. |

**A queue size of 0 does not mean the system is healthy.** With a **SynchronousQueue** selected via queueCapacity=0, the queue **holds no tasks**, while all workers can still be busy and the handler rejects new tasks.

**Rejection counts must be interpreted by policy.** With CallerRunsPolicy, the handler may be invoked yet the task still runs on the caller; with DiscardPolicy, the task is dropped without an exception. Therefore, separate metrics for **submission attempts, accepted, caller-runs, rejected-with-error, and discarded** if the application needs accurate measurement.

**Do not rely solely on exception messages to distinguish causes.** Check the underlying executor's **isShutdown()** state when needed, but keep in mind a state snapshot is a point-in-time observation, not absolute proof of causation across racing threads.

### Observing via the Underlying JDK Executor

The following Spring snippet assumes an **initialized ThreadPoolTaskExecutor**:

~~~java
java.util.concurrent.ThreadPoolExecutor delegate =
        executor.getThreadPoolExecutor();

System.out.println("shutdown=" + delegate.isShutdown());
System.out.println("active=" + executor.getActiveCount());
System.out.println("pool=" + executor.getPoolSize());
System.out.println("queue=" + executor.getQueueSize());
~~~

This is an **illustrative snippet inside a method with a valid executor variable**, not a standalone program. Measurements can change immediately after being read; use them only to guide investigation alongside relevant logs and metrics.

## 14. Testing Rejection Reliably

To test a handler, do not fire off a few random tasks and rely on **Thread.sleep()** hoping they happen to saturate the pool. You can build a deterministic scenario with **CountDownLatch**:

1. Configure **corePoolSize=1, maxPoolSize=1, queueCapacity=1** and AbortPolicy.
2. Submit task A; use a latch to wait until A has started, then hold A from finishing.
3. Submit task B into the queue; verify the queue accepted B.
4. Submit task C; assert the caller receives **TaskRejectedException** in Spring or **RejectedExecutionException** in JDK.
5. Intentionally switch the policy to CallerRunsPolicy in a separate test; assert the Runnable executed on the **exact thread submitting the task**.
6. If testing shutdown, call shutdown before submitting further tasks; assert behavior according to the handler rather than inferring from queue state.
7. In **finally**, release latches and close the executor to avoid hanging the test suite or leaking worker threads.

**Test the Future as well** when the handler can drop tasks: if a drop policy is intentionally used, verify there is a cancel/fail mechanism for the Future or that the caller does not wait on that Future. A test that only asserts "execute did not throw an exception" has not proven the work ran.

**Edge cases**: a task failing after being accepted, the application closing its context mid-submission, a full pool where one worker just became free, and a request thread pulled into CallerRuns. Each scenario verifies a different behavior.

## 15. Common Misconceptions

**"TaskRejectedException means the task ran and threw an exception."** False. It usually indicates **the task was not accepted for execution**.

**"RejectedExecutionHandler always throws an exception."** False. Only handlers like AbortPolicy throw; CallerRunsPolicy can run the task, and DiscardPolicy can drop the task silently.

**"Increasing maxPoolSize guarantees no rejections."** False. If the queue/pool still saturates or the executor has shut down, rejection still happens; an overly large max also carries resource risks.

**"A large queueCapacity makes maxPoolSize scale up whenever busy."** False. Pools normally enqueue after reaching core, and only try to create additional workers when the queue can no longer accept tasks.

**"CallerRunsPolicy is still async."** Not guaranteed. When saturated, the task can run synchronously on the submitting thread.

**"If the executor has shut down, CallerRunsPolicy still runs the task to save the work."** False. Per the JDK, it drops the task when the executor has shut down.

**"Use DiscardPolicy so the system stops having errors."** False. You only lose the rejection signal, risking Futures that wait forever or lost data.

**"TaskRejectedException extends RuntimeException directly and is unrelated to JDK exceptions."** False. It **extends RejectedExecutionException** and can be caught via the parent type.

**"Catching errors only in CompletableFuture.exceptionally() handles rejection."** False. Rejection right at the `@Async` call site can occur **before any future exists to attach a handler to**.

**"An empty queue means the executor is still healthy."** False. With a zero-capacity direct handoff queue, the pool can be saturated and rejecting even though queueSize is always 0.

**"Task submit returning means the job was durably saved."** False. An in-memory executor is not a transactional/durable job queue.

**"Every TaskExecutor supports the four standard ThreadPoolExecutor handlers."** False. That handler API belongs to JDK ThreadPoolExecutor; each Spring implementation has its own mechanism.

## 16. Self-Check Exercises

**Question 1.** With pool core=2, max=4, queueCapacity=2, all four workers are busy and the queue holds two tasks. Another task is submitted with AbortPolicy. What happens?

**Answer:** It cannot enter the queue and cannot create a worker, so the task is rejected. Under JDK that is **RejectedExecutionException**; under **ThreadPoolTaskExecutor** it is typically **TaskRejectedException**.

**Question 2.** The pool has plenty of room, but it has shut down. Will a newly submitted task be accepted?

**Answer:** No. Shutdown is a rejection cause independent of saturation.

**Question 3.** How does AbortPolicy differ from CallerRunsPolicy?

**Answer:** AbortPolicy **throws an error** when it cannot accept a task; CallerRunsPolicy **runs the task on the caller if the executor has not shut down**, which can slow down the caller and cross thread boundaries.

**Question 4.** If the handler uses DiscardPolicy and the caller receives a Future, can calling get() block forever?

**Answer:** Yes, when the wrapper task is dropped without the Future being completed or cancelled. Do not use this policy for work whose result the caller needs to know.

**Question 5.** Is an error inside an @Async method after the task was accepted a TaskRejectedException?

**Answer:** Normally no. That is a task execution error, delivered via Future/CompletableFuture according to the return type. TaskRejectedException belongs to the task-admission failure path.

**Question 6.** Are QueueSize=0 and a rising rejection count contradictory?

**Answer:** No, especially with a SynchronousQueue where queueCapacity=0.

**Question 7.** A service returns 202 Accepted after the executor throws TaskRejectedException. Is that reasonable?

**Answer:** No, if 202 is meant to indicate the job was accepted, because the task was not actually accepted. Either the admission contract or the work-persistence mechanism must be fixed.

**Question 8.** Can TaskRejectedException be caught with catch(RejectedExecutionException e)?

**Answer:** Yes, because TaskRejectedException extends RejectedExecutionException. In Spring, catching the specific type usually communicates intent more clearly.

## 17. Operational Checklist

- [ ] Identify the exact executor used at each submission point and `@Async` bean.
- [ ] Know the actual **corePoolSize**, **maxPoolSize**, **queueCapacity**, and rejection handler.
- [ ] Account for **shutdown** as a cause of rejection.
- [ ] Explicitly decide between **Abort**, **CallerRuns**, or another policy before going to production.
- [ ] If Futures are used, ensure tasks cannot be silently lost and leave callers waiting indefinitely.
- [ ] At `@Async` sites, handle **submission-time TaskRejectedException** separately from **exceptional completion of the future**.
- [ ] Keep retries bounded, with a deadline, idempotency, and appropriate backoff.
- [ ] Choose semantically accurate overload/API status codes (e.g., 503 or 429 depending on cause).
- [ ] Monitor pool/queue saturation, rejections, task duration, and downstream resources.
- [ ] Test with latches, covering both busy-worker and executor-shutdown cases.
- [ ] Clearly identify which tasks **must be durably persisted** before acknowledging acceptance.

## Conclusion

**RejectedExecutionHandler** is where **ThreadPoolExecutor decides what to do when it cannot accept another task**; the choice can be to throw an error, run the task on the caller, or drop the task. **TaskRejectedException** is Spring's way of reporting that a **TaskExecutor did not accept a task**, and it extends Java's **RejectedExecutionException**. With **ThreadPoolTaskExecutor**, **AbortPolicy** paired with bounded pools/queues and overload observability is an easy-to-control starting point. When combining with **@Async**, always separate **submission-time errors** from **in-flight execution errors**, and design response/retry policies that neither drop work silently nor mask overload.

**API References:** [Java 17 ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html), [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html), [Spring TaskRejectedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html).
