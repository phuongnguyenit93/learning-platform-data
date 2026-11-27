# Pool Size and Scheduler Limits

Spring Integration uses `TaskScheduler` to trigger polling endpoints and other scheduled tasks. The scheduler determines when a polling task runs and which thread executes it. Therefore, the scheduler's pool size affects how many tasks can run concurrently, the start delay of polls, and whether one poller can slow down others.

`poolSize` is often mistaken for the number of consumers, the number of concurrently processed messages, or queue capacity. In reality, it controls the number of threads the scheduler can use to execute scheduled tasks. To tune a flow's throughput, consider the scheduler, poller, executor, handler, and downstream systems together.

## 1. TaskScheduler in Spring Integration

`TaskScheduler` is Spring's abstraction for scheduling tasks by point in time, delay interval, fixed rate, or cron trigger. Spring Integration uses the scheduler to trigger polling endpoints. When due, a polling endpoint performs a message receive pass from a `PollableChannel` or invokes a `MessageSource`, depending on the endpoint type.

Commonly involved components:

| Component | Responsibility |
|---|---|
| `TaskScheduler` | Schedules and triggers tasks according to a trigger |
| `ThreadPoolTaskScheduler` | Implementation using a thread pool to run scheduled tasks |
| Polling endpoint | Performs a message receive pass and invokes handlers or sends messages into the flow |
| `PollerMetadata` | Describes the trigger, message limit, executor, advice, and poller properties |
| `TaskExecutor` | Executes work on worker threads when the poller is configured to separate work from scheduler threads |

A poller is typically triggered repeatedly by the scheduler. Without separating execution using a dedicated executor, polling work may run directly on a scheduler thread. If a poll includes a long-timeout receive or a handler doing slow I/O, that thread is occupied for the corresponding duration.

## 2. ThreadPoolTaskScheduler and poolSize

`ThreadPoolTaskScheduler` is the common implementation of `TaskScheduler`. It uses a `ScheduledThreadPoolExecutor` underneath. `poolSize` determines how many scheduler threads can execute scheduled tasks concurrently.

Example configuring a dedicated scheduler for Spring Integration polling tasks:

```java
@Configuration
class IntegrationSchedulerConfiguration {

    @Bean(name = "taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(8);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```

In this example, the scheduler has up to 8 threads executing scheduled tasks simultaneously. The prefix helps identify threads in logs and thread dumps. The shutdown settings instruct the scheduler to wait for running tasks within a bounded time; `removeOnCancelPolicy` removes canceled tasks from the executor's delay queue.

If you instantiate `ThreadPoolTaskScheduler` directly, Spring Framework's default is one thread. Spring Integration or Spring Boot infrastructure may provide a default scheduler depending on configuration and version. In real applications, identify which scheduler bean pollers use and configure it explicitly when load requires more than one concurrent task.

`poolSize` is the scheduler's thread count, not a queue capacity. The scheduled executor stores scheduled tasks in a delay queue; increasing pool size does not bound the number of registered tasks or the number of messages waiting in a `QueueChannel`.

## 3. What Does Pool Size Limit?

Suppose an application has 12 independent polling endpoints, each triggered periodically and each poll pass taking 2 seconds. If all share a scheduler with pool size 4, at most 4 scheduled tasks can run at once. The remaining tasks wait for a free thread, so actual execution times can lag behind their triggers.

| Configuration | Meaning |
|---|---|
| `poolSize = 1` | Only one scheduled task can execute at a time on that scheduler |
| `poolSize = 4` | Up to four scheduled tasks can execute concurrently |
| `poolSize = 8` | Up to eight scheduled tasks can execute concurrently |

Pool size does not guarantee every task starts on time. If all threads are busy, due tasks must wait. A larger pool size can reduce waits from scheduler contention, but it also increases how much work can run concurrently and puts pressure on databases, HTTP clients, brokers, or target systems.

A polling endpoint normally has its own periodic task. Increasing pool size mainly lets multiple independent endpoints run in parallel; it does not automatically cause one endpoint to process more messages per pass. To change messages per pass, adjust `maxMessagesPerPoll`; to add parallel workers, check the corresponding consumer/executor configuration.

## 4. Distinguishing Scheduler Pool, Task Executor, and Queue Capacity

These three limits sit at different boundaries:

| Mechanism | Limits or Controls | Example |
|---|---|---|
| Scheduler `poolSize` | Number of scheduled tasks that can execute concurrently | Up to 8 poller tasks running on the scheduler |
| `TaskExecutor` | Number of workers executing handed-off work and the executor's queueing policy | Poller dispatches work to a bounded worker pool |
| Channel capacity | Number of messages that can wait in a bounded channel | `QueueChannel(500)` holds at most 500 messages |

`maxMessagesPerPoll` is a fourth limit: the maximum number of messages a polling task receives in one pass. It neither gives the scheduler extra threads nor increases channel capacity.

For example, a scheduler has pool size 4, an executor has 10 workers, a queue channel has capacity 500, and `maxMessagesPerPoll = 20`. These numbers do not mean the system always processes 40 messages simultaneously. Actual running work depends on the number of pollers, how pollers dispatch to the executor, thread pool state, handler duration, and downstream limits.

## 5. When Are Scheduler Threads Held for Long Periods?

A scheduler thread can be held for the entire duration a scheduled task runs. For a polling endpoint, that duration may include:

- Waiting for messages via `receiveTimeout` when the channel is empty.
- Receiving and processing up to `maxMessagesPerPoll` messages.
- Running a transformer or handler with synchronous I/O operations.
- Waiting on transactions, retries, or backoff in an advice chain.
- Waiting for external systems to respond.

If a poller spends a long time on a scheduler thread, other tasks sharing the same scheduler may start late. This is a form of scheduler starvation or contention. Increasing pool size can help in the short term, but if the cause is a handler blocking for long periods, consider offloading processing to a bounded `TaskExecutor` and reserving scheduler threads for schedule triggering.

Do not configure an unbounded executor just to prevent scheduler blocking. When an executor's worker pool and queue lack sensible bounds, the backlog can simply move from the scheduler to the executor and keep growing until resources are exhausted.

## 6. Separating Trigger Scheduling and Processing with TaskExecutor

The scheduler can handle triggering the poller while a `TaskExecutor` executes the polling work on worker threads according to poller configuration. This separation is helpful when handlers may block or require controlled parallel processing.

Example declaring an executor with bounded workers and queue:

```java
@Bean
ThreadPoolTaskExecutor pollerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("si-poller-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
```

This is an executor for dispatched work; it does not replace `TaskScheduler`. When configuring a poller to use an executor, check the API of your Spring Integration version and attach the right executor to `PollerMetadata` or the endpoint DSL. Also define the policy when the executor runs out of workers or its queue fills: reject tasks, run on the caller thread, or apply another backpressure mechanism.

When separating an executor, the processing thread can differ from the scheduler thread. Therefore, do not rely on scheduler thread-local state to carry security context, transaction context, or request data. Use appropriate context propagation mechanisms and define transaction boundaries on worker threads.

## 7. Sizing the Pool for Real Workloads

There is no fixed formula for every application. The choice depends on task characteristics and how many polling endpoints can be active simultaneously.

For short, non-blocking polling tasks that finish quickly, a small pool size can serve many endpoints. For tasks with long `receiveTimeout` values or handlers executing synchronous I/O, each task can hold a thread longer; increase the pool or offload processing to an executor. For CPU-bound tasks, increasing threads beyond available CPUs usually increases context switching rather than throughput.

A practical sizing workflow:

1. List all polling endpoints and each endpoint's trigger frequency.
2. Measure the time from task trigger to completion, including message receive wait time.
3. Identify which tasks can become due simultaneously and run in parallel.
4. Set an initial pool size sufficient for expected concurrency plus reasonable headroom.
5. Load-test with production-like backlogs and downstream behavior.
6. Tune based on poll start delay, processing duration, busy threads, and downstream load.

A rough estimate is comparing total thread occupancy time of tasks becoming due within an interval against available threads. If many tasks frequently wait because all scheduler threads are busy, find tasks holding threads too long or increase scheduler capacity in a controlled way.

Do not mechanically set pool size equal to the number of polling endpoints. Many pollers with staggered schedules and short runs can share a small pool. Conversely, even a few pollers with long processing times can saturate a small pool.

## 8. Fixed Delay, Fixed Rate, and Scheduler Contention

The trigger decides when a task is scheduled; the scheduler pool decides when a thread is available to execute it.

| Trigger | Schedule Calculation | When the Scheduler Is Busy |
|---|---|---|
| `fixedDelay` | Wait the delay after the previous execution finishes | Next execution is calculated after task completion, though a thread is still needed to run |
| `fixedRate` | Maintain a fixed time cadence between triggers | Tasks may start late if threads are unavailable; the same periodic task does not overlap itself |
| `cron` | Trigger at calendar marks | If the scheduler is busy at that mark, actual execution may be delayed |

Increasing pool size does not alter trigger semantics. It only increases how many independent tasks can execute concurrently. If a poller has a 1-second fixed delay but each pass takes 5 seconds, increasing the scheduler pool does not make that poller run overlapping passes; it only prevents other pollers from waiting on its thread.

## 9. Scheduler Queue and Limit on Registered Tasks

`ThreadPoolTaskScheduler` is backed by `ScheduledThreadPoolExecutor`. The scheduled executor's delay queue holds scheduled tasks and is not a capacity-bounded queue like `QueueChannel`. `poolSize` limits executing threads, not how many scheduled futures can be registered.

This matters for dynamic flows. If an application continuously creates polling endpoints or schedules new tasks without stopping/destroying old flows, the number of scheduled tasks can grow even if pool size stays constant. Increasing pool size does not fix registration leaks or forgotten scheduled tasks.

When canceling a flow or endpoint, ensure the scheduled task is canceled according to its lifecycle. `removeOnCancelPolicy` helps the executor remove canceled tasks from the delay queue instead of retaining canceled tasks until their planned run time. Track active endpoints and scheduled tasks when the application uses `IntegrationFlowContext`.

## 10. Scheduler Shutdown and Lifecycle

The scheduler is normally a bean managed by the application context. When the context closes, bean lifecycle hooks stop new scheduling and release the executor according to shutdown settings.

Properties to consider:

| Property | Meaning |
|---|---|
| `waitForTasksToCompleteOnShutdown` | Instructs the executor to wait for accepted tasks to finish according to shutdown policy |
| `awaitTerminationSeconds` | Limits how long to wait for the executor to terminate |
| `removeOnCancelPolicy` | Removes canceled scheduled tasks from the delay queue when supported by the executor |
| `threadNamePrefix` | Sets a prefix to identify threads in logs and thread dumps |

Waiting for tasks to complete helps finish in-progress polls, but also lengthens shutdown. Set an appropriate timeout and have a policy for tasks that cannot finish. If handlers call external systems, HTTP/database timeouts must also be bounded so the scheduler is not held indefinitely.

For dynamic flows, `registration.stop()` stops the endpoint and new polls per its lifecycle; `registration.destroy()` removes the registration. Do not simply remove a handle from a registry while forgetting to stop the endpoint, because scheduled tasks and related resources may still remain active.

## 11. Multiple Schedulers in the Same Application Context

An application may have multiple work groups with different requirements: Spring Integration polling endpoints, `@Scheduled` tasks, housekeeping, or maintenance jobs. If all share a single small scheduler, one group of long-running tasks can delay the rest.

Schedulers can be separated by purpose:

- A scheduler for polling endpoints requiring stable latency.
- A scheduler for low-priority maintenance or housekeeping tasks.
- A dedicated scheduler for a group of flows with markedly different processing times and load.

Separating schedulers must be intentional. Each pool is a separate set of threads and resources; creating too many schedulers increases management overhead, thread count, and operational complexity. Name beans clearly, wire the right scheduler wherever pollers use it, and document who owns the bean's lifecycle.

Do not assume every `@Scheduled` task and Spring Integration poller necessarily share the same scheduler. How schedulers are resolved depends on Spring, Spring Boot, and Spring Integration configuration. Verify the actual bean injected or resolved for each mechanism before diagnosing contention.

## 12. Observing and Diagnosing Scheduler Saturation

When pollers run late, determine whether tasks are not being triggered, are waiting for threads, or have handlers running too long. Useful metrics include:

- Pool size and active thread count.
- Number of waiting scheduled tasks and completed tasks.
- Time from trigger mark to actual task start.
- Execution duration of each polling task.
- Delayed poll count, channel queue depth, and messages processed per pass.
- Retry count, error count, and downstream wait time.
- Active workers, queue depth, and rejected tasks of `TaskExecutor` if used.

With `ThreadPoolTaskScheduler`, you can inspect the underlying `ScheduledThreadPoolExecutor` via the scheduler's accessor APIs to collect relevant metrics. In a Spring Boot environment, combine Actuator/Micrometer if the required metrics are enabled. Thread dumps also help find scheduler threads blocked in `receive()`, databases, HTTP clients, or handlers.

| Symptom | Possible Cause | Inspection Approach |
|---|---|---|
| Multiple pollers start late at the same time | Scheduler pool saturated | Active threads, task duration, pool size |
| Only one flow is slow | That flow's handler or downstream is blocked | Thread dump, I/O latency, retries |
| Low CPU yet poller is late | Threads waiting on I/O or receive timeout | Stack traces and wait times |
| Raising pool increases downstream errors | Too many tasks calling the target system concurrently | Connection pools, rate limits, concurrency |
| Scheduled tasks grow steadily over time | Dynamic flows/endpoints not destroyed or tasks not canceled | Registration count, endpoint lifecycle, canceled futures |
| Shutdown does not finish | Blocked tasks or overly long await termination | Await termination, downstream timeouts, thread dump |

## 13. Common Configuration Mistakes

- **Pool size too small:** many pollers share one thread; one slow task delays all others.
- **Pool size too large:** too much concurrent work causes CPU, connection pool, or downstream rate-limit contention.
- **Using the scheduler as a worker executor:** heavy handlers run directly on scheduler threads and stall other pollers' schedules.
- **Confusing pool size with queue capacity:** increasing the scheduler pool does not allow `QueueChannel` to hold more messages.
- **Unbounded work:** `maxMessagesPerPoll = -1`, long receive timeouts, and slow handlers can create a prolonged poll pass.
- **Unmonitored shared scheduler:** `@Scheduled` tasks, pollers, and housekeeping contend for the same pool with no metrics.
- **No cleanup for dynamic flows:** endpoints are no longer needed, yet scheduled tasks and runtime beans remain.
- **Shutdown without timeouts:** indefinitely blocked tasks cause context closing to stall or fail to complete.

## 14. Sizing and Operational Principles

- **Identify the actual scheduler:** check the bean and configuration pollers use; do not rely on assumptions about defaults.
- **Measure before growing the pool:** use task duration, trigger lag, and thread dumps to confirm contention.
- **Keep scheduler tasks short:** offload I/O or long processing to a bounded executor when appropriate.
- **Separate schedule groups with different requirements:** only create separate schedulers when latency or resource isolation is needed.
- **Distinguish different limits:** pool size, executor capacity, channel capacity, and `maxMessagesPerPoll` control different things.
- **Protect downstream systems:** combined scheduler and executor concurrency must fit within database, broker, and target API capacity.
- **Manage lifecycles:** cancel tasks, stop/destroy endpoints, and wait for shutdown within bounded time.
- **Track dynamic tasks:** limit runtime-created flows and registrations, and clean them up when no longer needed.

Before changing `poolSize`, identify which pollers use that scheduler, which tasks hold threads for long periods, and how many tasks genuinely need to run concurrently. A suitably sized scheduler pool helps tasks trigger more reliably on cadence, while overall throughput still depends on executors, handlers, channels, and downstream capacity.
