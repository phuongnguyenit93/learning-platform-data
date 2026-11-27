# Scheduled Tasks Delayed by Long-Running Work

In Spring Integration, pollers and periodic tasks rely on a scheduler to trigger work on schedule. If a task occupies a scheduler thread for too long, subsequent runs or other tasks sharing the same scheduler can be delayed. This is an execution capacity and thread allocation issue, not necessarily a wrong trigger expression.

To resolve it properly, find what is holding the thread: the polling task, a synchronous I/O call, a downstream handler, or another periodic task. Only then decide whether to increase the scheduler pool, offload the poller to an executor, shorten the work, adjust the trigger, or bound concurrency. Adding threads without understanding the bottleneck may simply move the queue from the scheduler to the executor or overload downstream systems further.

After this lesson, you will be able to:

- Explain why long-running tasks delay their own schedules and other tasks.
- Distinguish the behavior of `fixedRate`, `fixedDelay`, and cron when tasks exceed expected duration.
- Identify scheduler threads, poller task threads, and downstream worker threads.
- Configure scheduler and executor pools to match the workload.
- Control concurrency, processing order, transactions, and shutdown when splitting threads.
- Measure and diagnose latency instead of blindly increasing thread counts.

## 1. Why Are Scheduled Tasks Delayed?

The scheduler is responsible for triggering tasks when their triggers become due. If the task body runs synchronously on the scheduler thread and takes a long time, that thread cannot simultaneously execute another scheduled task. When the scheduler has few threads, one long task can slow down an entire group of tasks sharing that scheduler.

Example of a scheduler with one worker thread:

```text
Scheduler pool: 1 thread

Thread-1:  [Poller A -------- 8s processing --------]
           B due ^               C due ^
                         but no free thread available

After A finishes:
Thread-1:                                           [Task B] [Task C]
```

Tasks B and C became due but had to wait for Thread-1 to become free. Their schedule expressions are still valid; the delay happens during execution.

Some common causes:

- The handler calls an external API or queries a database synchronously and waits a long time.
- The polling task fetches a large batch, with each message taking a long time to process.
- Multiple pollers or `@Scheduled` tasks share a single scheduler with a small pool.
- Scheduler threads are blocked by locks, I/O, transactions, or waiting for resources.
- Tasks are handed off to an executor, but the executor is full, causing work to sit in its queue.
- The system runs multiple instances and each instance executes the same business task without coordination.

Before fixing, identify whether the delay occurs at the scheduler trigger time, the task start time, or the handler completion time. Those three timestamps tell you whether to tune the scheduler, the executor, or the work itself.

## 2. Distinguishing Scheduler Threads from Message-Processing Threads

In a polling flow, at least three thread roles can appear:

```text
Trigger / TaskScheduler
        |
        v
Scheduler thread
        |
        | triggers polling task
        v
Poller task
        |
        | receives message and calls downstream
        v
Message handler
        |
        +---- may run on the same poller thread
        |
        +---- or be handed off to another executor/channel
```

**Scheduler threads** are responsible for executing scheduled callbacks. In a simple polling configuration, both the polling task and handler can run directly on this thread. In that case, a slow handler occupies the scheduler thread.

**A poller task executor** can separate the polling work from the scheduling thread. The scheduler fires according to the trigger and the work is handed off to the executor. This separation lets the scheduler return to serving schedules, though the executor still has its own thread limits and queue.

**Downstream executors** such as an `ExecutorChannel`'s executor can further separate handler processing. This introduces another asynchronous boundary. When adding multiple executor layers, track which queue a message sits in and where errors are routed.

Not every endpoint uses a poller. An event-driven consumer on a `DirectChannel` receives messages when the producer sends them; it has no polling schedule. However, a synchronous handler on the sending thread can still slow down the producer or upstream flow. Identifying the endpoint type correctly prevents tuning the scheduler for a problem unrelated to scheduling.

## 3. fixedRate and fixedDelay When Tasks Run Long

These two triggers react differently when a polling task takes a long time.

### 3.1. fixedDelay

`fixedDelay` measures the rest interval after the previous execution finishes. If a task takes 8 seconds and the delay is 2 seconds, the next execution is scheduled roughly 10 seconds after the previous execution started (ignoring scheduler jitter).

```text
Task A: [--------- 8s ---------] 2s wait [Task B]
        0s                     8s        10s
```

Thus, fixedDelay does not attempt to keep a fixed start cadence when work takes long. It preserves a pause after each run, which is useful when reducing pressure on data sources or downstream systems.

### 3.2. fixedRate

`fixedRate` sets planned start marks at fixed intervals. If the period is 2 seconds but one run takes 8 seconds, the task cannot overlap with itself when scheduled as a standard periodic task on `ScheduledExecutorService`. The next run is delayed and may start immediately after the previous one ends to catch up with the schedule.

```text
Planned marks: 0s  2s  4s  6s  8s  10s
Actual task:   [--------- 8s ---------][--------- ...
               0s                    ~8s
```

This can cause the task to run nearly continuously with no rest interval. If work consistently exceeds the period, increasing the scheduler pool does not make the same periodic task run concurrently with itself; a larger pool mainly gives other independent scheduled tasks threads to run on.

### 3.3. Cron

Cron expresses marks on a calendar clock, such as every minute or at 02:00 daily. If one execution stretches past the next mark, the next trigger may be delayed or skipped depending on the semantics of the trigger and scheduler in use. Do not assume missed cron marks are automatically caught up.

With Spring's `CronTrigger`, understand the chosen execution mode and Spring version. Some versions offer lenient execution (computing the next run from completion time, potentially skipping missed marks) and fixed execution (sticking to planned schedule marks so marks are not skipped). Choose according to business requirements and verify exact behavior before relying on catch-up.

| Trigger | When a Task Exceeds Its Period/Mark |
|---|---|
| `fixedDelay` | Waits the full delay after the task ends; start cadence stretches naturally. |
| `fixedRate` | Does not overlap the same periodic task; the next run may lag or start immediately after the prior one. |
| `cron` | Missed-mark handling depends on trigger mode; it may skip or continue tracking the schedule. |

## 4. Scheduler Pool Size and Blast Radius

`ThreadPoolTaskScheduler` uses a thread pool to run scheduled tasks. When the pool has only one thread, one blocking task can delay all other tasks on the same scheduler. Increasing `poolSize` lets multiple independent tasks run in parallel, provided they are not constrained by the same external resource.

Example declaring a scheduler with four workers:

```java
@Configuration
class SchedulingConfiguration {

    @Bean(name = "taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("integration-scheduler-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        return scheduler;
    }
}
```

The scheduler bean name must match your application's configuration and discovery mechanism. Spring Integration typically looks up the scheduler by the integration context's conventional bean name; Spring Boot or custom setups may provide a different scheduler. Verify which scheduler the poller actually uses before changing pool size.

Increasing pool size helps when multiple independent tasks are waiting on each other due to a lack of scheduler threads. However, it cannot fix a single task that takes too long. One specific periodic task still will not overlap with itself merely because the pool is larger.

Additionally, increasing pool size can send more concurrent requests to databases or APIs. If downstream systems have connection limits or rate limits, adding threads can turn latency into timeouts, lock contention, or rejection errors. Increase gradually and monitor both the scheduler and downstream systems.

## 5. Offloading Poller Work to a TaskExecutor

For polling endpoints, you can configure an executor on the poller so the scheduled callback does not have to perform all message reception and processing directly. Java DSL example:

```java
@Bean
ThreadPoolTaskExecutor pollerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("poller-worker-");
    return executor;
}

@Bean
IntegrationFlow pollOrders(OrderHandler handler,
                            ThreadPoolTaskExecutor pollerExecutor) {
    return IntegrationFlow.from(
            "ordersQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(1_000)
                            .taskExecutor(pollerExecutor)
                            .maxMessagesPerPoll(10)))
            .handle(handler, "handle")
            .get();
}
```

This is how you separate threads for a polling endpoint when the builder API of your Spring Integration version supports `taskExecutor` on the poller. The scheduler triggers work on the trigger mark; the executor accepts the polling work. Measure both submission time and actual processing time, since tasks can wait in the executor queue after the trigger fires.

When a poller task is dispatched asynchronously, the schedule can keep firing while the previous task is still queued or running, depending on implementation and configuration. With a multi-threaded executor, check the risk of multiple poll passes for the same endpoint running concurrently. This can alter message order, increase downstream load, and affect transactions. If business logic requires sequential execution, cap concurrency appropriately, use a single-threaded executor, or use explicit locking/serialization.

Separating an executor does not create infinite capacity. When the executor queue is full, tasks may wait a long time or be rejected under the rejection policy. At that point, the scheduler is no longer the primary bottleneck; the backlog sits in the executor.

## 6. Limiting Work Per Poll

`maxMessagesPerPoll` bounds how many messages a polling task can fetch in one cycle. If each message takes 500 ms and a poll takes 100 messages, one task can hold a thread for roughly 50 seconds, excluding I/O and overhead. Large batches raise throughput in some cases, but also lengthen thread occupancy.

Example:

```java
Pollers.fixedDelay(1_000)
        .maxMessagesPerPoll(5)
```

If the queue is always full, the task can process at most 5 messages and then finish. Reducing batch size gives the scheduler more frequent opportunities to run other tasks, while increasing poll count and overhead. Choose the value based on actual processing time, message size, and downstream capacity.

If each poll should take only one message to keep transactions small or minimize thread occupancy, set `maxMessagesPerPoll(1)`. If you want to drain a queue in batches, you can raise the limit, but pair it with time bounds or appropriate backpressure. Avoid unbounded values when the source can return messages continuously.

## 7. Concurrency, Ordering, and Duplicate Processing

When moving a poller to an executor or increasing pool size, the number of tasks that can wait or run concurrently increases. This changes the sequential assumptions some handlers rely on.

Common risks:

- Two poll tasks process the same type of data simultaneously and update the same record.
- Messages sharing the same business key complete out of order.
- A non-idempotent handler causes duplicate side effects on retry or redelivery.
- The database connection pool or downstream API gets overloaded.
- One instance runs multiple concurrent tasks while another instance also runs the same schedule.

If business logic requires ordering, define the scope of ordering: across the entire endpoint, per tenant, per order ID, or per partition. You can use a single-threaded executor for the endpoint, partition by key, lock at the data tier, or use a distributed lock if coordinating across multiple instances. Only use a distributed lock when single execution across the cluster is genuinely required; locks need leases/timeouts and crash handling.

If messages come from a broker, verify acknowledgment/transaction semantics match the concurrency level. With an in-memory `QueueChannel`, multiple pollers can take different messages; that does not guarantee completion order matches send time.

## 8. Transactions and Context Across Thread Boundaries

Transactions are typically bound to a thread. When a polling task and handler run synchronously on the same thread, transaction advice configured around the poller can cover the corresponding processing. When work moves to an executor, a thread-bound transaction on the scheduler thread does not automatically propagate to the worker thread.

Therefore:

- Place transaction boundaries where data operations actually execute.
- Do not assume a producer's transaction covers asynchronous tasks.
- Clarify whether a transaction wraps a single message or an entire batch.
- Verify rollback behavior and whether messages are redelivered.
- With an executor, check error handling on worker threads and how exceptions are reported back to the flow.

Switching threads can also affect `ThreadLocal` context such as security context, MDC logging, or custom context. If context propagation is needed, use supported propagation mechanisms rather than assuming it is automatically present on the new thread.

## 9. Timeouts, I/O, and Backpressure

A slow task is more often caused by waiting on resources than by CPU computation. If a handler makes HTTP calls without connect/read timeouts, a single request can hold a thread for a very long time. Similarly, database queries without timeouts or long lock waits can occupy poller workers and grow the backlog.

Set appropriate timeouts for:

- HTTP clients, database queries, and RPC calls.
- Waiting for messages or waiting for responses from other services.
- Locks and semaphores.
- Shutdown/await termination of schedulers and executors.

Backpressure must be handled at the work-intake boundary. You can bound batch sizes, queue capacity, concurrency, or producer rate. If producers continuously emit faster than consumers can handle, adding scheduler threads only causes more tasks to contend for resources. Monitor queue depth and wait times to decide whether to slow intake, add real processing capacity, or buffer load in a broker.

## 10. Graceful Shutdown While Tasks Are Running

When the ApplicationContext shuts down, schedulers and executors need policies for running and queued tasks. `ThreadPoolTaskScheduler` and `ThreadPoolTaskExecutor` provide options to wait for tasks to finish and set termination wait limits; balance these against maximum processing time and the deployment environment's shutdown timeout.

A sensible shutdown sequence typically follows:

1. Stop producers or endpoints from creating new work.
2. Stop pollers in the appropriate lifecycle order and phase.
3. Allow in-flight tasks to finish within a bounded time window.
4. Handle remaining queued tasks by policy: continue, keep in a durable queue, or return to the source.
5. Shut down executors and schedulers after dependent components have stopped.

`waitForTasksToCompleteOnShutdown` is not a guarantee that every task finishes unconditionally. `awaitTerminationSeconds` or the corresponding timeout caps the wait duration. If a task is stuck on I/O with no timeout, shutdown can still drag on or end unexpectedly.

## 11. Measuring and Diagnosing Latency

Do not merely log "task started" and "task finished." To distinguish scheduler delay from processing time, record at least these timestamps:

| Timestamp | Meaning |
|---|---|
| Scheduled/due time | Time the task was expected to fire according to its trigger. |
| Actual start time | Time the task actually began executing. |
| Poll receive time | Time the message was retrieved from the channel/source. |
| Handler completion time | Time message processing finished. |
| Queue wait time | Time the task/message waited in a queue before running. |

From these, you can break down:

- **Scheduler lag** = actual start time minus scheduled/due time.
- **Task duration** = task completion time minus actual start time.
- **Executor queue wait** = worker start time minus task submission time.
- **Message processing duration** = handler completion minus handler start.

Also monitor:

- Scheduler pool size, active threads, and queued tasks.
- Executor active count, queue depth, completed tasks, and rejected tasks.
- Queue/channel depth and message ingress/egress rates.
- Handler duration, timeouts, retries, and downstream errors.
- Actual poll count versus expected poll count.

Thread name prefixes help identify threads in logs and thread dumps. When a task hangs, a thread dump reveals what code the scheduler is executing, which monitor/lock it is waiting on, or where it is blocked on I/O. Use metrics and tracing to pinpoint persistent bottlenecks instead of looking only at CPU.

## 12. Workflow for Troubleshooting a Delayed Scheduled Task

Suppose a poller is configured to run every 2 seconds, yet logs show occasional 15-second gaps. Follow this order:

1. **Confirm the planned schedule.** Check the trigger, `initialDelay`, time zone if cron, and when the task should have run.
2. **Measure scheduler lag.** Compare due time with actual start time to see whether the task was delayed before starting or ran long after starting.
3. **Identify the executing thread.** Check thread names and thread dumps to see if scheduler threads are running handlers/I/O or waiting on locks.
4. **Inspect shared schedulers.** Identify which pollers and scheduled tasks share the `TaskScheduler`; check pool size and task durations.
5. **Inspect the executor if used.** Measure queue wait, active workers, queue capacity, and rejected tasks.
6. **Reduce thread occupancy time.** Set timeouts, lower `maxMessagesPerPoll`, optimize I/O, or offload processing to an appropriate executor.
7. **Control concurrency.** If using a separate executor, decide whether overlapping polls are allowed; protect ordering, transactions, and idempotency.
8. **Re-measure after changes.** Compare scheduler lag, throughput, queue depth, and downstream errors before and after.

| Symptom | Likely Bottleneck | First Action |
|---|---|---|
| Multiple scheduled tasks lag together | Scheduler pool lacks threads or a shared task is blocking. | Take a thread dump, identify the blocking task; consider pool size or separate scheduler. |
| Only one poller lags while others stay on schedule | That specific poller or its data source is slow. | Measure receive/handler duration, timeouts, and batch size. |
| Trigger fires on time but workers start late | Executor queue backlog. | Check queue wait, pool size, and rejections. |
| fixedRate runs continuously after a long task | Task frequently exceeds its period. | Increase period, reduce duration/batch, or choose fixedDelay. |
| Queue grows despite many threads | Downstream is the bottleneck or producer is too fast. | Measure true throughput, timeouts, and concurrency limits. |
| Out-of-order processing after increasing pool | Multiple tasks running concurrently. | Serialize by key or limit concurrency. |

## 13. Self-Check

**Scenario:** An application has three pollers sharing a `ThreadPoolTaskScheduler` with one thread. Poller A calls an external API and takes 12 seconds; poller B runs every 2 seconds, but logs show B often starts 10 seconds late. After increasing the scheduler pool to 4, B stays closer to schedule, but the database begins overloading.

1. Why did poller A delay poller B?
2. Why did increasing the scheduler pool help B yet potentially overload the database?
3. When should you use a dedicated executor for a poller?
4. If an executor allows multiple poll tasks to run concurrently, what risks must be checked?

**Suggested answers:** (1) A occupied the single scheduler thread, forcing B to wait. (2) Multiple independent tasks could run simultaneously and issue many concurrent requests to the database. (3) When you want to decouple trigger timing from polling/handler work that may block, while defining concurrency and queue limits. (4) Processing order, concurrent updates to the same data, thread-bound transactions, idempotency, connection pools, and downstream load.

**Hands-on exercise:** Create two scheduled/polling tasks sharing one scheduler. Have task A sleep for 5 seconds and task B run every second; log due time, actual start, and completion. Try pool size 1 and then 2. Next, move task A to a dedicated executor with bounded queue and concurrency. Compare scheduler lag, queue wait, throughput, and processing order.

## References

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Java DSL — Poller Configuration](https://docs.spring.io/spring-integration/reference/dsl.html)
