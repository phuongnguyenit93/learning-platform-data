# Thread Pools, ExecutorService, and Pending Work

In a Java application, thread pools help limit the number of threads, reuse workers, and coordinate asynchronous work. Commonly used APIs for managing pools are Executor, ExecutorService, ThreadPoolExecutor, and ScheduledExecutorService.

When an application uses CRaC (Coordinated Restore at Checkpoint), thread pools must be treated as part of the application lifecycle. A checkpoint can save heap and process state, yet the mere fact that an ExecutorService, queue, or Future still exists after restore does not automatically prove that workers, tasks, dependencies, and business state remain ready to continue.

Before checkpointing, the application must clearly decide whether new work is accepted, how running work will finish, and where pending work is kept. After restore, the application must create or recover appropriate executors, submit still-valid tasks for processing, and accept traffic only once workers and dependencies are ready.

## 1. What are thread pools and ExecutorService?

A thread pool is a managed group of worker threads for executing multiple tasks. Instead of creating a new thread per request, the application submits tasks to an executor. The executor decides which worker runs a task and when.

Java provides the main abstractions:

- `Executor`: basic interface accepting a Runnable for execution.
- `ExecutorService`: extends Executor, supporting submit, Future, shutdown management, and awaiting termination.
- `ThreadPoolExecutor`: common implementation managing core threads, maximum threads, and a work queue.
- `ScheduledExecutorService`: executes tasks after a delay or on a schedule.
- `ForkJoinPool`: pool oriented toward splitting work and work stealing.
- Virtual-thread-creating executor: creates a virtual thread per task rather than maintaining a fixed pool of platform threads.

Simple example:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);

executor.submit(() -> {
    processOrder();
});
~~~

The application submits tasks using submit. The executor can put a task into a queue if no worker is idle or create additional workers according to configuration. A task begins running only when picked up by a worker.

### 1.1. States of a task

A task typically goes through the following states:

1. Created by the application.
2. Submitted to the executor.
3. Waiting in the queue.
4. Picked up and executed by a worker.
5. Finished successfully, failed, or canceled.

Not every task goes through all states. For example, a task may be rejected before entering the queue or canceled while still waiting.

| State | Meaning | Concerns at checkpoint |
|---|---|---|
| Created | Created but not yet submitted | Will it be submitted after restore? |
| Queued | Submitted, waiting for a worker | Where is it stored and is it still valid? |
| Running | Worker is executing | Can it finish safely before checkpoint? |
| Completed | Finished | Has the result been durably recorded? |
| Failed | Task ended with an error | Is a retry needed and is retrying safe? |
| Cancelled | Task was canceled | Are the caller and system aware of the canceled state? |
| Rejected | Executor did not accept the task | Is there backpressure or retry handling? |

### 1.2. ExecutorService is not a business queue

An executor's work queue is primarily an in-process coordination mechanism. It does not by itself provide guarantees such as durable storage, exactly-once processing, or business recovery after failures.

If a task represents critical work, such as payment processing or sending invoices, the application needs a recoverable data source to know whether that work still needs to be done or has finished. ThreadPoolExecutor's internal queue should not be the sole place storing critical business state.

## 2. Why must thread pools be coordinated with CRaC?

CRaC saves process state at a point in time. A thread pool can hold multiple concurrent states:

- A worker running a Runnable.
- A worker waiting for a task in a BlockingQueue.
- A task holding a lock or transaction.
- A Future whose result a caller is waiting on.
- A scheduler waiting for a trigger time.
- A worker using a database connection or HTTP client.
- A task waiting for a response from an external service.

During checkpointing, external resources and real wall-clock time continue to change. A database may fail over, tokens may expire, brokers may rebalance, and tasks with deadlines may become overdue. A Runnable remaining in the heap may hold references to closed clients or stale data.

Therefore, before checkpointing, the application must bring asynchronous activity into a manageable state. After restore, the application must restore executors and work according to the chosen policy.

~~~mermaid
flowchart TD
    A["Application is accepting tasks"] --> B["Checkpoint requested"]
    B --> C["Stop submitting new tasks"]
    C --> D["Handle running tasks"]
    D --> E["Decide on pending tasks"]
    E --> F["Stop or close executor"]
    F --> G["CRaC creates checkpoint"]
    G --> H["Restore process"]
    H --> I["Create new executor or recover pool"]
    I --> J["Restore still-valid tasks"]
    J --> K["Reopen admission and workers"]
~~~

This is a general coordination model. Implementation details depend on the executor kind, libraries, CRaC JDK, and how the application stores work.

## 3. Distinguishing running tasks and pending tasks

These two groups need different policies.

### 3.1. Running tasks

A running task may be:

- Executing a database transaction.
- Calling a remote API.
- Writing a file.
- Sending a message.
- Holding a lock.
- Modifying business state.
- Waiting on another Future.

If checkpointing occurs mid-operation, after restore the task might continue while external dependencies have changed. A request-sending operation might already have been executed by the server even though the caller never received the response. If the task is re-executed, the result could be duplicated.

The common strategy is to stop accepting new work, wait for running tasks to complete within a bounded time, and persist results according to business rules. If a task cannot finish, the application needs a cancellation policy or must abort the checkpoint.

Do not assume every task can be safely interrupted. An interrupt is only a signal; the task must check interrupt status or use APIs that support interruption. A task waiting on I/O does not necessarily finish immediately when its thread is interrupted.

### 3.2. Tasks waiting in the queue

Pending tasks have not yet been executed by a worker. There are three common approaches:

1. **Drain the queue:** stop accepting new tasks and let workers finish all pending tasks before checkpointing.
2. **Keep work in a durable source:** stop consumers or internal producers, leaving waiting jobs in the broker or database; after restore, create the executor and resume fetching jobs.
3. **Save work descriptors:** convert pending tasks into command descriptors or job IDs that can be persisted; after restore, recreate Runnables from descriptors and submit them to a new executor.

Do not assume keeping a Runnable in a queue is enough. A Runnable may capture a connection, request context, transaction, thread-local, or mutable object. Those references may be invalid after restore.

### 3.3. Why store work descriptors instead of Runnables?

A Runnable is an execution object inside the process. It can hold many references to runtime state. A command descriptor describes work with explicit data, for example:

~~~java
public record GenerateInvoiceCommand(
        String invoiceId,
        String customerId,
        int attempt
) {}
~~~

After restore, the application can read the descriptor, load the latest state, and create a new task:

~~~java
GenerateInvoiceCommand command = jobStore.nextCommand();

executor.submit(() -> invoiceService.generate(command));
~~~

This allows tasks to be recreated using fresh dependencies, current configuration, and verified business data. A descriptor should contain enough information to identify the work, without containing secrets or references to runtime resources.

## 4. Shutdown methods of ExecutorService

ExecutorService provides shutdown methods with different semantics. Understanding these methods accurately is crucial when preparing for checkpointing.

### 4.1. shutdown()

~~~java
executor.shutdown();
~~~

shutdown() stops accepting new tasks while allowing already-submitted tasks to keep running. This method does not wait for all tasks to complete.

After calling shutdown():

- New tasks are normally rejected.
- Tasks already in the queue still execute.
- Running tasks continue until completion, unless a task finishes on its own or is affected by another mechanism.
- The executor transitions to the terminated state when all tasks have completed and the pool stops.

Important point: an ExecutorService that has been shut down cannot be restarted. After restore, if the application needs to continue processing, create a new executor or use lifecycle management supported by the framework.

### 4.2. awaitTermination()

~~~java
boolean terminated = executor.awaitTermination(
        30,
        TimeUnit.SECONDS
);
~~~

awaitTermination() waits for the executor to finish after shutdown has been requested. The method returns true if the executor terminated within the wait time, or false if a timeout occurred.

It does not call shutdown() itself and does not cancel tasks itself. Therefore, the typical sequence is:

1. Stop admission.
2. Call shutdown().
3. Call awaitTermination() with a timeout.
4. If it times out, execute the follow-up handling policy.

Do not wait indefinitely inside a CRaC callback. A stuck task can prevent checkpointing from proceeding.

### 4.3. shutdownNow()

~~~java
List<Runnable> notStarted = executor.shutdownNow();
~~~

shutdownNow() attempts to stop the executor immediately:

- Rejects new tasks.
- Attempts to interrupt running workers.
- Returns a list of tasks that had not started executing, if the implementation can extract them from the queue.
- Does not guarantee running tasks stop immediately.

Tasks must cooperate with the interrupt mechanism. If a Runnable ignores interrupts or is performing an uninterruptible operation, the worker may keep running.

The returned list can be useful for the application to handle unstarted tasks. However, do not assume every ExecutorService provides the same visibility or recovery for its internal queue. With ThreadPoolExecutor, the queue is accessible via specific APIs; with other executors, details may differ.

### 4.4. Comparing the three methods

| Method | Stops new tasks | Pending tasks | Running tasks | Waits for completion? |
|---|---|---|---|---|
| shutdown() | Yes | Continue executing | Continue running | No |
| awaitTermination() | Not by itself | Does not alter by itself | Does not interrupt by itself | Yes, up to timeout |
| shutdownNow() | Yes | Attempts to drain and return unstarted tasks | Attempts to interrupt | No |

A typical shutdown pattern:

~~~java
executor.shutdown();

if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    List<Runnable> notStarted = executor.shutdownNow();

    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException(
            "Executor did not terminate within the deadline"
        );
    }

    // The application must decide how to handle notStarted.
}
~~~

This snippet is an illustrative pattern for the shutdown process. Inside a CRaC callback, the application must also coordinate the admission gate, task state, and saving unfinished work. Do not automatically discard elements in notStarted if they represent unprocessed business work.

## 5. Can an ExecutorService be reused after shutdown?

No. Under the ExecutorService contract, after shutdown or shutdownNow, the executor does not accept new tasks. A ThreadPoolExecutor that has been shut down cannot be restarted by calling a generic resume method.

If the application closes the executor in beforeCheckpoint(), after restore it must create a new executor:

~~~java
private ExecutorService createExecutor() {
    return new ThreadPoolExecutor(
        4,
        8,
        60,
        TimeUnit.SECONDS,
        new LinkedBlockingQueue<>(500),
        new ThreadPoolExecutor.AbortPolicy()
    );
}
~~~

After restore:

~~~java
executor = createExecutor();
~~~

This is an easy-to-understand and easy-to-control approach for an application-owned pool. If the executor is managed by a framework or library, use the framework's lifecycle integration to avoid creating duplicate pools or bypassing resource management.

## 6. Choosing a policy for pending work

No single policy fits every application. Choose according to the nature of the work.

### 6.1. Policy A: drain all work

The application stops accepting new tasks and waits for all accepted tasks to finish. Once both the queue and the running task count reach 0, the executor is shut down and checkpointing proceeds.

Suitable when:

- The number of pending tasks is not large.
- Tasks have bounded execution times.
- Tasks can complete before the checkpoint deadline.
- Waiting does not hurt the system's SLA.

The advantage is simple post-restore state: no internal tasks remain to resubmit. The disadvantage is that checkpoint duration depends on the longest remaining task.

Monitor both running task count and pending task count. Waiting only for workers to become idle is insufficient if tasks remain in the queue unexecuted.

### 6.2. Policy B: leave work in a durable queue

For systems processing jobs from Kafka, RabbitMQ, a database queue, or an external job service, the work source can exist independently of the JVM.

Before checkpoint:

1. Stop the consumer from receiving new messages.
2. Finish or handle in-flight delivered messages.
3. Commit offsets or ack according to broker semantics.
4. Close consumers and the executor.
5. Leave unreceived messages sitting in the broker.

After restore:

1. Create a new executor.
2. Reconnect to the broker.
3. Register consumers or subscriptions.
4. Start receiving messages.
5. Process messages with ack, retry, and idempotency mechanisms.

This approach usually fits systems with durable queues. However, clearly understand ack/commit timing. If acking before work completes, jobs may be lost. If acking after completion yet the ack response is lost, jobs may be redelivered.

### 6.3. Policy C: save task descriptors for resubmission

If pending work resides in memory and must continue after restore, save a reproducible representation such as a job ID, command record, or workflow state.

Before checkpoint:

- Stop new submissions.
- Convert pending tasks into descriptors.
- Save descriptors to durable storage or a state structure explicitly managed by the application.
- Ensure running tasks have completed or have their own business checkpoint.
- Shut down the executor.

After restore:

- Create a new executor.
- Read pending descriptors.
- Check whether the task has already been processed.
- Create new Runnables using current dependencies.
- Resubmit and update status.

### 6.4. Do not snapshot Runnables arbitrarily

A Runnable can capture:

- JDBC Connections or transactions.
- HTTP clients and sockets.
- Security contexts or tokens.
- Request/response objects.
- ThreadLocals.
- Locks or mutable objects.
- References to closed beans or old executors.

Keeping the Runnable object on the heap does not automatically make those dependencies valid. Save work-describing data and recreate Runnables after restore.

## 7. Tracking running and pending task counts

An application needs to know when it can safely checkpoint. Useful information includes:

- Number of accepted tasks not yet completed.
- Number of running tasks.
- Number of pending tasks.
- Number of rejected tasks.
- Number of canceled tasks.
- Duration the longest-running task has been running.
- Number of tasks with overdue deadlines.

With ThreadPoolExecutor, some metrics can be read:

~~~java
ThreadPoolExecutor pool = (ThreadPoolExecutor) executor;

int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long completed = pool.getCompletedTaskCount();
long total = pool.getTaskCount();
~~~

These values are useful for monitoring, but are not a consistent snapshot for making checkpoint decisions if tasks are still being submitted concurrently. Close admission first, and only then wait for counters and queues to meet desired conditions.

An application-layer WorkTracker can count work that has been accepted and not yet completed. When a task finishes, the tracker decrements the counter in a finally block. The checkpoint coordinator can wait for the counter to reach 0 using a Condition, CountDownLatch, or equivalent mechanism.

~~~java
public final class TrackedTask implements Runnable {

    private final Runnable delegate;
    private final WorkTracker tracker;

    public TrackedTask(Runnable delegate, WorkTracker tracker) {
        this.delegate = delegate;
        this.tracker = tracker;
    }

    @Override
    public void run() {
        try {
            delegate.run();
        } finally {
            tracker.completed();
        }
    }
}
~~~

This is only an illustrative piece. When submission fails or a task is canceled before running, the tracker must also be updated. If the counter is decremented only in run(), rejected tasks or tasks removed from the queue could prevent the counter from ever reaching 0.

## 8. Integrating an executor with a CRaC Resource

One way to organize this is to create a resource managing the executor's lifecycle. This resource coordinates with the admission gate and task tracker.

Steps:

1. Register the resource during application startup.
2. In beforeCheckpoint(), stop submitting new tasks.
3. Wait for running and pending work to meet the chosen policy.
4. Shut down the executor.
5. Confirm the executor has terminated.
6. After restore, create a new executor.
7. Attach the new executor to the dispatcher and reopen admission.

The example below assumes the application already has a WorkCoordinator to control submission and wait for all accepted tasks to finish. These interfaces are application abstractions, not CRaC APIs.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExecutorCheckpointResource implements Resource {

    private final WorkCoordinator coordinator;
    private final Supplier<ExecutorService> executorFactory;
    private final long timeoutSeconds;

    private volatile ExecutorService executor;

    public ExecutorCheckpointResource(
            WorkCoordinator coordinator,
            Supplier<ExecutorService> executorFactory,
            long timeoutSeconds) {

        this.coordinator = coordinator;
        this.executorFactory = executorFactory;
        this.timeoutSeconds = timeoutSeconds;
        this.executor = executorFactory.get();

        coordinator.attach(executor);
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        coordinator.stopAccepting();

        // Wait for both running tasks and accepted tasks to complete.
        coordinator.awaitAllWork(timeoutSeconds, TimeUnit.SECONDS);

        ExecutorService oldExecutor = executor;
        oldExecutor.shutdown();

        if (!oldExecutor.awaitTermination(
                timeoutSeconds, TimeUnit.SECONDS)) {
            oldExecutor.shutdownNow();

            if (!oldExecutor.awaitTermination(
                    timeoutSeconds, TimeUnit.SECONDS)) {
                coordinator.markUnavailable();
                throw new IllegalStateException(
                    "Executor did not terminate before checkpoint"
                );
            }
        }

        executor = null;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        ExecutorService restoredExecutor = executorFactory.get();

        executor = restoredExecutor;
        coordinator.attach(restoredExecutor);
        coordinator.resumeAccepting();
    }
}
~~~

In the example:

- WorkCoordinator stops admission and waits for accepted work to complete.
- The old executor is shut down after work has drained.
- If it does not terminate within the allowed time, the application triggers an interrupt and continues waiting with a bound.
- After restore, a new executor is created and reattached to the coordinator.
- Admission reopens only after the new executor is installed.

This is an illustrative structure, not a complete implementation to copy without adjustment. In production, you need to define how to recover if the callback fails after the old executor has already shut down. Because a shut-down ExecutorService cannot be reopened, the application must create a replacement executor after the old pool has actually stopped, or keep the system in an unavailable state if old workers have not yet terminated.

If the application needs to preserve pending tasks rather than draining, replace WorkCoordinator with a mechanism that stores descriptors or leaves jobs in a durable queue source. Do not resubmit a Runnable without verifying whether the previous execution could have caused side effects.

## 9. Error and timeout handling in the executor lifecycle

### 9.1. Tasks not finishing before timeout

A task may hang due to:

- Waiting on an external service.
- Deadlock.
- Waiting on a held lock.
- I/O without a timeout.
- Ignoring interrupts.
- Waiting on another Future that never completes.

Do not checkpoint a pool that still has workers performing unsafe operations. Set timeouts on I/O and waiting operations, and design tasks to support cooperative cancellation.

If a task does not finish, you can abort the checkpoint and keep the application in an unavailable state while handling it. Do not assume shutdownNow() will forcibly stop every thread.

### 9.2. Interrupted tasks

Tasks should check for interrupts and clean up resources in finally. For example:

~~~java
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        releaseTaskResources();
    }
}
~~~

If InterruptedException is caught, usually restore the interrupt flag when you cannot propagate the exception outward. Do not swallow the interrupt and continue an infinite loop.

### 9.3. Task failure during drain

A failing task does not necessarily mean the checkpoint must fail. That depends on the kind of work and business policy.

- For auxiliary tasks that can be ignored, log the error and proceed according to policy.
- For critical tasks, record a failed or retryable status in durable storage.
- For tasks with indeterminate outcomes, query status from the target system or use an idempotency key before retrying.

### 9.4. Preparation callback fails

If beforeCheckpoint() has already stopped admission and shut down the executor and then a later step fails, the application may no longer have a pool to keep processing. A clear recovery design is needed.

You can use a coordinator with states:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> QUIESCING: checkpoint requested
    QUIESCING --> DRAINED: no pending or active work
    DRAINED --> EXECUTOR_STOPPED: shutdown completed
    EXECUTOR_STOPPED --> CHECKPOINTING: callback returns
    CHECKPOINTING --> RESTORING: process restored
    RESTORING --> RUNNING: new executor attached
    QUIESCING --> RECOVERING: drain failed
    DRAINED --> RECOVERING: shutdown failed
    RECOVERING --> RUNNING: replacement pool ready
    RECOVERING --> UNAVAILABLE: recovery failed
~~~

Note that a CRaC Resource has callbacks before checkpoint and after restore; do not assume there is an afterCheckpoint callback that automatically reverses all changes if checkpointing is aborted. If recovery is needed when a checkpoint request fails, handle the error at the coordinator layer that invoked the checkpoint request or have an independent recovery procedure. Do not reopen admission when the executor is not yet ready.

## 10. ScheduledExecutorService and tasks with deadlines

ScheduledExecutorService supports:

- schedule(): runs once after a delay.
- scheduleAtFixedRate(): runs repeatedly at a fixed period.
- scheduleWithFixedDelay(): runs repeatedly with a delay after the previous execution completes.

Scheduled tasks have additional timing issues. A task scheduled to run in 10 minutes might already be due while the process was checkpointed. A periodic schedule might miss multiple runs. Delay queues and ScheduledFutures remaining in the heap do not automatically resolve business policies for missed runs.

Decide explicitly:

- Should an overdue task run immediately after restore?
- Should missed periodic runs be coalesced into a single run?
- Should old runs be skipped and the next schedule calculated?
- Are deadlines based on wall-clock time or monotonic elapsed time?
- Could a task execute twice if schedule state is restored and the scheduler also reloads schedules from the database?

For critical business schedules, usually store the schedule and execution state in durable storage. After restore, the new scheduler reads current schedules and determines due work. Avoid relying solely on ScheduledFuture objects stored in the heap.

## 11. ForkJoinPool, common pool, and virtual threads

### 11.1. ForkJoinPool

ForkJoinPool uses work-stealing: idle workers can take tasks from another worker's queue. This mechanism fits work that can be split into subtasks.

When using CRaC, note:

- Tasks may be in the middle of fork/join.
- Workers may be waiting or taking tasks from internal queues.
- A task may depend on external resources.
- Stopping and recreating the pool must follow the implementation's lifecycle.

Do not assume you can snapshot internal queues and manually resubmit each ForkJoinTask. If using a dedicated pool, check how the JDK and libraries manage its lifecycle. For business work, keep work state at the application layer so tasks can be recreated.

### 11.2. ForkJoinPool.commonPool()

The common pool is the JVM's shared pool used by many APIs, such as some CompletableFuture operations and parallel streams.

Do not shut down the common pool just to prepare a checkpoint for one component. This pool may be in use by other code. Instead:

- Do not put long-running business work on the common pool if it requires dedicated lifecycle management.
- Use a dedicated executor for work that needs pausing, draining, or recreating.
- Audit asynchronous APIs that use an implicit default executor.
- Avoid relying on the internal state of the common pool if the application needs precise recovery control.

### 11.3. Virtual threads

Virtual threads reduce thread creation cost and suit many I/O-bound workloads. Java can create an executor with Executors.newVirtualThreadPerTaskExecutor().

However, virtual threads do not eliminate the lifecycle problem:

- Tasks can still be performing I/O.
- Tasks can still hold transactions or references to clients.
- Tasks can still be checkpointed while in a state requiring coordination.
- Work can be duplicated or expire during restore.
- The application still needs to stop admission and determine pending work state.

An executor creating virtual threads is still an ExecutorService. Manage shutdown and task completion according to the JDK API in use. Do not infer that because virtual threads are lightweight, draining or work management can be skipped.

### 11.4. Do not mix privately owned executors and shared executors

A component should not shut down an executor it does not own. For example, if a framework passes in a shared executor, calling shutdown() from the component's CRaC resource could break other components.

Establish ownership:

| Executor | Who manages the lifecycle? | Action before checkpoint |
|---|---|---|
| Service's dedicated pool | Service or lifecycle manager | Can pause/drain/shut down and recreate |
| Framework-managed pool | Framework | Use the framework's lifecycle integration |
| Common pool | JVM | Do not shut down per a single component's lifecycle |
| Temporarily request-created executor | Request scope | Close when request completes |
| Library's executor | Library or designated owner | Follow the library's documentation |

## 12. Waiting Futures and CompletableFutures

A Future represents the result of a task. A caller may be calling get() or join() to wait for the result.

When checkpointing, consider both the producer and the caller:

- The task producing the Future may be waiting in the queue.
- The task may be running and not yet finished.
- The caller may be blocked on Future.get().
- A CompletableFuture may be completed by another thread or an asynchronous callback.
- Continuation callbacks may be submitted to a default executor or shared executor.

A Future remaining on the heap does not prove the task will resume properly after restore. If the old executor has shut down, continuations may be rejected upon submission. If an external operation has completed yet the Future was not marked completed before checkpoint, the application must reconcile state from the target system.

For critical workflows, persist business state or correlation IDs to recover the process, rather than relying solely on in-memory Futures.

For example, instead of holding only a Future for a report, save the report ID and PENDING/COMPLETED status in a job store. After restore, the application checks the status and recreates the task if necessary.

## 13. Backpressure and queue bounds

A thread pool with an unbounded queue can accumulate many tasks when submission rate exceeds processing rate. At checkpoint time, a large number of pending tasks prolongs drain time and increases the amount of state to manage.

Consider:

- Bounded queues.
- Appropriate rejection policies.
- Backpressure at the API or consumer.
- Limiting the number of concurrently running tasks.
- Monitoring queue depth and task age.
- Stopping acceptance of additional tasks when the instance prepares for checkpoint.

ThreadPoolExecutor has rejection policies such as AbortPolicy, CallerRunsPolicy, DiscardPolicy, and DiscardOldestPolicy. Each policy has different effects:

| Policy | Behavior | Points to watch |
|---|---|---|
| AbortPolicy | Throws RejectedExecutionException | Caller must handle task rejection |
| CallerRunsPolicy | Submitting thread runs the task | Can increase latency and change concurrency |
| DiscardPolicy | Drops the new task | Suitable only if dropping tasks is acceptable |
| DiscardOldestPolicy | Drops the oldest task in the queue and retries submit | Can lose pending work |

For business work, do not silently drop tasks without a state-saving and notification mechanism. Rejection should be treated as an explicit outcome that the caller can handle.

## 14. Practical implementation workflow

A thread pool management workflow with CRaC can be organized as follows.

### Before checkpoint

1. Switch readiness to NOT_READY.
2. Stop accepting new requests or jobs.
3. Stop consumers and schedulers from creating new tasks.
4. Wait for running tasks to finish within a bounded time.
5. Handle pending tasks according to the drain, durable queue, or descriptor policy.
6. Shut down application-owned executors.
7. Verify workers have terminated and no tasks remain to process in the pool.
8. Allow CRaC to proceed with saving the checkpoint.

### After restore

1. Initialize required dependencies such as databases, HTTP clients, and brokers.
2. Create a new executor or call supported lifecycle integration.
3. Attach the new executor to the dispatcher.
4. Read job descriptors or resume consumers from durable sources.
5. Resubmit still-valid work.
6. Start schedulers and consumers.
7. Switch readiness to READY.

Ordering between components must follow dependencies. For example, an executor should not accept tasks calling a database before the database pool is ready.

## 15. Observability and testing

Useful metrics:

| Metric | Purpose |
|---|---|
| Active thread count | Number of workers running tasks |
| Queue depth | Number of waiting tasks |
| Outstanding work | Total accepted work not yet completed |
| Task duration | Detect long-running tasks |
| Rejected task count | Track backpressure |
| Cancelled task count | Track canceled tasks |
| Executor termination time | Measure shutdown time |
| Executor recreation time | Measure pool creation time after restore |
| Pending job count | Track unprocessed work |
| Task retry count | Detect errors or duplicate processing |

Should test:

1. Checkpoint when the pool is idle.
2. Checkpoint when tasks are running.
3. Checkpoint when the queue has many pending tasks.
4. Running task times out or does not respond to interrupts.
5. Task calling the database when the database fails over.
6. Task sends a message but the response or ack is lost.
7. Task whose deadline has expired upon restore.
8. Executor shuts down successfully and is recreated after restore.
9. Callback fails after admission has stopped.
10. Task submitted during checkpoint preparation.
11. Shared executor that a component tries to shut down.
12. Restore when a durable queue source still contains pending jobs.

The goal is to prove no work is lost, no unintended duplicate execution occurs outside policy, no tasks are accepted when the executor is not ready, and checkpointing is not left waiting indefinitely.

## 16. Checklist for designing thread pools for CRaC

### Admission and task lifecycle

- [ ] Mechanism exists to stop submitting new tasks.
- [ ] Running and pending task counts can be tracked.
- [ ] Tasks have timeouts and proper interrupt handling.
- [ ] Clear policy exists for pending tasks.
- [ ] Critical work has durable state or reproducible descriptors.

### Executor lifecycle

- [ ] Executor ownership is clearly defined.
- [ ] Shared framework executors or the common pool are not shut down.
- [ ] shutdown and awaitTermination are used with timeouts.
- [ ] shutdownNow is used only with a policy for interrupted running tasks and unstarted tasks.
- [ ] Do not attempt to reuse a shut-down ExecutorService.
- [ ] Create a new executor after restore or use supported integration.

### Restore and consistency

- [ ] Dependencies are ready before the executor accepts tasks.
- [ ] Pending jobs are restored from a reliable source.
- [ ] Task retries have idempotency mechanisms when needed.
- [ ] Futures and continuations are explicitly managed.
- [ ] Schedulers recalculate deadlines and schedules after restore.
- [ ] Readiness switches to READY only after workers and dependencies are ready.

### Observability and operations

- [ ] Metrics exist for active count, queue depth, and outstanding work.
- [ ] Logs exist for each checkpoint and restore step.
- [ ] Timeouts exist for drain and shutdown.
- [ ] A procedure exists for handling callback failures.
- [ ] Tested hung tasks, large pending queues, and connection errors after restore.

## 17. Frequently asked questions

### Can a ThreadPoolExecutor be kept across a checkpoint?

That depends on the JDK, checkpoint/restore mechanism, worker state, and libraries. Do not assume every executor can be kept safely. For an application-owned pool, an easily controllable strategy is to stop admission, drain work, shut down the pool before checkpoint, and create a new pool after restore.

### Does shutdown() remove pending tasks?

No. shutdown() stops accepting new tasks but lets already-submitted tasks continue executing. To know when the pool finishes, call awaitTermination() with a timeout.

### Does shutdownNow() guarantee stopping all tasks immediately?

No. This method attempts to interrupt workers and returns unstarted tasks. Tasks must cooperate with interrupts; I/O or code that does not check interrupts may keep running.

### Can an ExecutorService be restarted after shutdown?

No. A shut-down executor does not accept new tasks. Create a new executor instance or use a framework lifecycle API that supports reinitialization.

### Are tasks waiting in the queue saved along with the checkpoint?

If the queue object and tasks belong to checkpointed heap state, they may appear in the restored state. However, that does not prove the tasks are still valid or that the executor can resume processing safely. Design an explicit pending-work policy and do not rely on arbitrary Runnables to guarantee business work.

### Should shutdownNow() be used in beforeCheckpoint()?

Only when the application has an explicit policy for interrupted running tasks and returned unstarted tasks. If possible, stop admission and drain work in an orderly way first. shutdownNow() does not replace job persistence or recovery procedures.

### Do virtual threads need handling before checkpointing?

Yes. Virtual threads reduce thread creation overhead, yet tasks can still hold transactions, wait on I/O, or perform business operations. You still need to stop admission, handle running tasks, and recover pending work according to policy.

### Should the common pool be used for CRaC-managed work?

Usually not if the application needs tight control over pausing, draining, and recreating. The common pool is shared across the JVM. Consider a dedicated executor for workloads requiring an independent lifecycle.

### How do we avoid duplicate task processing after restore?

Persist work state in a durable source, use job IDs or idempotency keys, update completion status consistently, and clearly define ack/commit timing. Do not retry an operation with an indeterminate outcome without checking status or having a deduplication mechanism.

## Conclusion

Thread pools and ExecutorService are components for coordinating work within a process. When using CRaC, the application must manage running workers, pending tasks, Futures, schedulers, and external work sources. The mere fact that an executor object or queue remains after restore does not guarantee tasks can continue properly.

An easily controllable workflow is to stop admission, drain work or keep pending jobs in a durable source, shut down dedicated executors before checkpoint, then create new executors and recover still-valid tasks after restore. Combining timeouts, idempotency, backpressure, readiness, and metrics helps applications avoid losing or duplicating work across checkpoint and restore.