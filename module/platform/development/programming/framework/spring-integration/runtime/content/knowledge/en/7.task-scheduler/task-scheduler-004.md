# TaskScheduler Lifecycle and Shutdown

In Spring Integration, pollers and certain endpoints need to be triggered on a schedule. **TaskScheduler** provides the scheduling infrastructure: it determines when a task is invoked and returns a handle for tracking or canceling the schedule. The scheduler itself does not decide what business logic runs; the poller or component that registered the task defines the work to execute.

When operating an application, two separate lifecycles must be managed:

- **Lifecycle of the scheduled task or Integration endpoint**: the task is registered, runs according to its trigger, and is paused or canceled when the endpoint stops.
- **Lifecycle of the scheduler bean**: the thread pool and scheduling resources are initialized, continue serving tasks, and are closed when the application shuts down.

Distinguishing these two lifecycles avoids common mistakes: stopping one poller and accidentally shutting down a scheduler shared by multiple endpoints, or closing the scheduler while endpoints still need to run.

## 1. What Is TaskScheduler Responsible For?

`TaskScheduler` is a Spring Framework abstraction for scheduling `Runnable` execution. It supports common schedule forms:

| API | Purpose |
|---|---|
| `schedule(task, trigger)` | Run according to a `Trigger`, such as cron or a custom trigger |
| `schedule(task, instant)` | Run once at a specific point in time |
| `scheduleAtFixedRate(task, period)` | Run at a fixed cadence |
| `scheduleWithFixedDelay(task, delay)` | Run again after a delay measured from the previous completion |

Scheduling methods return a `ScheduledFuture<?>` when a schedule is registered successfully. This handle allows checking status, retrieving results if any, and canceling the task.

TaskScheduler handles **when execution occurs**. It does not replace `TaskExecutor`:

- `TaskScheduler` manages execution timing and schedules.
- `TaskExecutor` manages executing tasks on worker threads.
- `MessageChannel` manages how messages are delivered to consumers.

A poller can be triggered by the scheduler, then use an executor to execute the polling work. Without a separate executor, the task may run directly on a scheduler thread.

## 2. How Is TaskScheduler Used in Spring Integration?

A Spring Integration poller registers a polling task with the scheduler. The trigger determines when it fires; when the task runs, the polling endpoint calls the source or receives messages from a pollable channel and sends them into the flow.

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["TaskScheduler bean"]
    B --> C["Schedule via Trigger"]
    C --> D["Polling endpoint"]
    D --> E["MessageSource / PollableChannel"]
    E --> F["Message"]
    F --> G["Output channel"]
    G --> H["Downstream handler"]
    D -. "stop endpoint" .-> X["Cancel endpoint schedule"]
    B -. "context shutdown" .-> Y["Close scheduler resources"]
~~~

A single scheduler can serve multiple pollers. For example, an application may have a poller reading orders every second, a poller scanning files every minute, and a poller checking partner status via cron. These tasks share the pool if configured to use the same scheduler.

In typical Spring Integration configurations, the scheduler can be provided as a bean under the conventional name `taskScheduler`; the application can also configure dedicated schedulers for infrastructure or specific endpoints depending on the version and setup. When you need control over shutdown and thread counts, declare the scheduler explicitly so you know exactly which bean owns the thread pool.

Important point: the scheduler is neither a message channel nor a dedicated worker pool for all business processing. It only triggers work on schedule.

## 3. Implementations and Thread Behavior

`TaskScheduler` is an interface. The concrete implementation determines how threads, pools, errors, and shutdown are managed.

| Implementation | Characteristics | Best Suited For |
|---|---|---|
| `ThreadPoolTaskScheduler` | Uses `ScheduledThreadPoolExecutor`; tasks typically run directly on scheduler threads | Pollers and scheduled tasks needing a configurable pool |
| `ConcurrentTaskScheduler` | Adapter around an existing `ScheduledExecutorService` or scheduler | Integrating with an application-managed executor |
| `SimpleAsyncTaskScheduler` | Simpler scheduler model, supporting virtual threads in compatible Spring versions | Workloads suited to that thread model and Spring version |

`ThreadPoolTaskScheduler` is the common choice in Spring applications. Its default pool size is often a single thread if left unconfigured; as a result, one blocking task can delay other tasks. Verify the actual implementation and application configuration rather than inferring behavior from the interface alone.

Example scheduler declaration:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setRemoveOnCancelPolicy(true);
    return scheduler;
}
~~~

Here, the pool has four scheduler threads and a distinct thread name prefix for easy identification in thread dumps. `setRemoveOnCancelPolicy(true)` instructs the scheduled executor to remove canceled tasks from its internal queue, avoiding retaining canceled tasks for too long in applications that frequently register and cancel schedules.

Do not increase pool size just because a poller looks slow. First determine whether the task is delayed in the source, downstream handler, or due to insufficient scheduler threads. If message processing is long, offload execution using a `TaskExecutor` or an asynchronous channel rather than letting scheduler threads perform all business logic.

## 4. Poller, Scheduler, and Executor Form an Execution Path

In a polling flow, the three components have distinct roles:

1. **Poller** describes the trigger, batch size, transaction advice, and polling policies.
2. **TaskScheduler** schedules when the polling endpoint is triggered.
3. **TaskExecutor** can execute the polling task or asynchronously dispatched work, depending on endpoint configuration.

Example:

~~~java
@Bean
IntegrationFlow pollOrders(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(1))
                                    .maxMessagesPerPoll(10)))
            .handle(orderService, "process")
            .get();
}
~~~

In this example, the poller is attached to the source's inbound endpoint. The scheduler triggers the endpoint at a fixed delay. When the endpoint runs, it fetches up to the configured number of messages in one cycle and sends them through the flow.

If the output channel is a `DirectChannel`, the downstream handler usually runs synchronously on the thread sending the message. In that case, handler processing time can prolong the polling task and occupy the scheduler thread. If the output channel is a `QueueChannel`, the adapter can place messages into the queue and finish the intake step; the consumer reading the queue is another endpoint, which may have its own poller. If an `ExecutorChannel` is used, messages are dispatched via an executor according to channel configuration.

Therefore, when a poller lags, inspect the entire execution path rather than only increasing the scheduler pool.

## 5. How Are Schedules Registered and Canceled?

When an endpoint starts, it registers a polling task with the scheduler and retains the handle of the created schedule. When the endpoint stops, it cancels its own schedule so no new triggers occur.

For code that schedules tasks manually, `ScheduledFuture` is the direct handle:

~~~java
@Component
class RefreshJob {

    private final TaskScheduler scheduler;
    private ScheduledFuture<?> future;

    RefreshJob(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    void start() {
        if (future == null || future.isCancelled()) {
            future = scheduler.scheduleAtFixedRate(
                    this::refresh,
                    Duration.ofSeconds(30));
        }
    }

    void stop() {
        if (future != null) {
            future.cancel(false);
            future = null;
        }
    }

    private void refresh() {
        // Perform state update work.
    }
}
~~~

This example illustrates schedule ownership: the component creating the schedule keeps the handle and cancels that exact schedule when it is no longer needed. In Spring Integration flows, let the endpoint lifecycle manage the poller schedule. Do not manually register a second schedule for the same source if the endpoint already polls it.

`cancel(false)` requests canceling subsequent executions without interrupting a currently running task. For a task already in progress, canceling the schedule does not mean the business operation has finished or rolled back. If a task must stop early, the code needs its own cooperative cancellation mechanism and timeout.

## 6. TaskScheduler and Spring Bean Lifecycle

`TaskScheduler` only defines the scheduling contract; the interface does not prescribe the full lifecycle or resource closing behavior of every implementation.

For Spring-managed schedulers like `ThreadPoolTaskScheduler`, Spring can initialize the pool when the bean is created and close resources via lifecycle/destroy hooks when the application context shuts down. A custom scheduler wrapping an external executor might not close that executor automatically unless explicitly configured or managed.

Identify who owns the scheduler:

- If the scheduler is a shared singleton bean in the application context, the context typically manages its lifecycle.
- If a component creates its own `ScheduledExecutorService`, that component must shut down the executor when destroyed.
- If the scheduler is shared across multiple application contexts or injected externally, do not let a single endpoint shut down the shared resource arbitrarily.
- If the scheduler is provisioned by another platform, follow that platform's ownership contract.

Do not call `shutdown()` on a shared scheduler just because one flow or one tenant becomes inactive. Stop the endpoint or cancel only the scheduled tasks owned by that component.

## 7. SmartLifecycle, autoStartup, and phase

Spring manages many Integration endpoints through bean lifecycles. Endpoints typically support `start()`, `stop()`, and `isRunning()`. Components implementing `SmartLifecycle` also expose `autoStartup`, `phase`, and a stop callback.

- `autoStartup` determines whether the endpoint starts automatically once the application context finishes starting.
- `phase` defines relative start/stop ordering among lifecycle beans.
- On startup, lower phases are usually processed first.
- On stop, the order is reversed so higher-phase components stop first.

This is helpful when ensuring consumers are ready before sources begin polling. On shutdown, inbound sources should stop receiving new messages first, followed by stopping consumers and downstream resources in an appropriate order.

Do not assign `phase` values by guesswork. Map dependencies across sources, channels, consumers, connections, and schedulers, then choose a start/stop order that satisfies those dependencies. For endpoints with `autoStartup=false`, the application needs a clear owner responsible for starting the endpoint once dependencies are ready.

## 8. Stopping an Endpoint vs. Shutting Down a Scheduler

This is the most important operational distinction:

| Action | Impact |
|---|---|
| Stop a polling endpoint | Cancels that endpoint's schedule; the shared scheduler can still serve other endpoints |
| Cancel a `ScheduledFuture` | Cancels the specific schedule represented by the handle |
| Stop a `SmartLifecycle` scheduler | Requests the scheduler to stop according to the lifecycle supported by the implementation |
| Shutdown scheduler executor | Closes the thread pool; other tasks using that pool are also affected |
| Close application context | Triggers bean stop and destroy sequence per context lifecycle |

Stopping an endpoint does not guarantee an in-progress poll pass is halted mid-flight. If the source is executing a query or API call, that operation may continue until completion or timeout. If downstream is processing messages synchronously, stop duration may depend on the handler.

Conversely, shutting down a shared scheduler can prevent all endpoints relying on it from being triggered. Therefore, shutting down the scheduler normally belongs to the final stages of stopping the application.

## 9. Graceful Shutdown and Immediate Shutdown

**Graceful shutdown** lets the system stop accepting new work, wait for in-flight work to finish within a time limit, and then close resources. **Immediate shutdown** prioritizes stopping fast and may leave incomplete work requiring recovery.

A graceful shutdown sequence should include these steps:

1. Stop or quiesce inbound endpoints so no new messages are accepted.
2. Wait for running polling tasks to finish or hit a timeout.
3. Wait for consumers to complete in-flight messages.
4. Drain queues according to application policy if needed.
5. Shut down schedulers and executors once no components need them.
6. Close databases, broker connections, and dependencies at the appropriate time.

Graceful shutdown does not mean every message has been committed. The system still needs well-defined source states, transactions, and idempotency to recover after crashes or timeouts.

### Configuring ThreadPoolTaskScheduler for Shutdown

Example configuring a scheduler with a task-completion wait time:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");

    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(30);
    scheduler.setRemoveOnCancelPolicy(true);

    return scheduler;
}
~~~

`setWaitForTasksToCompleteOnShutdown(true)` instructs the executor to wait for accepted tasks according to the implementation's shutdown policy. `setAwaitTerminationSeconds(30)` sets the maximum wait limit when closing the pool. `setRemoveOnCancelPolicy(true)` removes canceled tasks from the scheduled executor's queue.

These properties do not automatically drain business queues, acknowledge messages on brokers, or guarantee downstream transactions have committed. For periodic tasks, also check how your Spring version handles delayed/periodic tasks during shutdown. Test shutdown behavior in a production-like environment, especially when tasks can run longer than the timeout.

## 10. How Triggers and Execution Policies Affect Shutdown

The scheduler can run tasks on fixed delay, fixed rate, or cron. The trigger type affects when tasks are scheduled, but does not by itself decide how in-progress business work is stopped.

| Schedule | Next Execution Calculation | Things to Note |
|---|---|---|
| Fixed delay | After the previous pass finishes, wait the delay and run again | Long-running tasks push the next execution time back |
| Fixed rate | Fixed cadence based on start times | If a task runs long, subsequent runs may lag; the same periodic task does not overlap itself in `ScheduledThreadPoolExecutor` |
| Cron | At times matching the expression | Shutdown can occur near a trigger mark; already-started tasks must be treated as in-flight work |

Do not treat fixed rate as a mechanism that automatically creates concurrency. To run different tasks in parallel, you need enough scheduler threads or must offload processing to an appropriate executor. If a fixed-rate task runs long, measure its duration and consider fixed delay or offloading heavy work.

## 11. Sizing the Pool and Avoiding Scheduler Starvation

A scheduler pool that is too small can cause independent tasks to wait on each other. A pool that is too large creates excessive threads, increases context switching, and can put concurrent load on databases or external services.

Practical guidelines:

- Count the number of scheduled tasks that can run concurrently, not just the number of pollers.
- Measure execution duration and the proportion of tasks blocked on I/O.
- Separate task groups with different latency and criticality profiles onto dedicated schedulers when needed.
- Move heavy business processing to a `TaskExecutor` or asynchronous endpoint if the execution model permits.
- Set timeouts on sources and dependencies so tasks do not hold scheduler threads indefinitely.
- Monitor active task counts, delay relative to planned triggers, and executor queues.

`ThreadPoolTaskScheduler` typically executes `Runnable` instances on threads from the scheduler pool itself. For a poller using a `DirectChannel`, if the downstream handler runs synchronously, that handler can also occupy the scheduler thread. This is a common cause of other schedules falling behind despite short trigger intervals.

## 12. Handling Exceptions in Scheduled Tasks

Exceptions in scheduled tasks must be handled deliberately. If a periodic task throws an exception, whether the schedule continues or stops depends on the scheduler, trigger, and how the task was registered. With `ThreadPoolTaskScheduler`, you can configure an `ErrorHandler` to log, increment metrics, or route errors to an appropriate monitoring mechanism.

Example:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setErrorHandler(error ->
            LoggerFactory.getLogger("integration.scheduler")
                    .error("Scheduled task failed", error));
    return scheduler;
}
~~~

This snippet only illustrates where to attach an error handler. In a real application, use your project's standard logger and telemetry while avoiding logging sensitive payloads or credentials.

With Spring Integration pollers, distinguish exceptions from the source, exceptions while sending messages, and exceptions from downstream handlers. Some errors are handled by poller advice or the endpoint's error channel; errors in scheduling infrastructure may go through the scheduler's ErrorHandler. Do not assume every exception automatically appears in the same error channel.

Retries should have limits, backoff, and error classification. If a scheduled task fails repeatedly, metrics and alerts are needed so the schedule does not remain active while producing no useful work.

## 13. Shutdown Order for Endpoints and Dependencies

The stop sequence must reflect the message path. Consider an application with an inbound polling source, channel, service activator, outbound adapter, and shared scheduler:

~~~mermaid
flowchart TD
    A["1. Stop inbound source"] --> B["2. Wait for running polling tasks"]
    B --> C["3. Drain / finish consumers"]
    C --> D["4. Stop downstream endpoints"]
    D --> E["5. Shutdown scheduler and executor"]
    E --> F["6. Close database / broker connections"]
~~~

This diagram is a reference sequence. An application may need to stop an outbound adapter after consumers have drained, or keep database connections open until the final transaction completes. The key is never closing a dependency while an endpoint might still use it.

With `SmartLifecycle`, `phase` helps coordinate stop ordering. The `stop(Runnable callback)` callback must be invoked only when the component has truly finished stopping; components managing asynchronous work must not signal completion prematurely. When using a platform context shutdown timeout, set a limit large enough for in-flight work while fitting within container termination windows.

## 14. Observing State and Diagnostics

When a scheduled task misbehaves, determine which stage it stopped at:

1. Was the scheduler bean created and initialized successfully?
2. Has the endpoint started? What does `isRunning()` return?
3. Does the trigger produce the expected schedule and firing times?
4. Does the scheduler pool have free threads, or are all threads blocked?
5. Did the task start but hang because of a stalled source or handler?
6. Was the task canceled when the endpoint stopped or the context shut down?
7. Are exceptions handled by poller advice, an endpoint error flow, or the scheduler's `ErrorHandler`?
8. Was the scheduler shut down by another component sharing the same pool?

Thread name prefixes help identify which scheduler a thread belongs to in thread dumps. You can also add metrics for active threads, pool size, queue size, execution duration, poll count, last poll timestamp, and error count. If using Micrometer Observation, attach appropriate trace/correlation metadata to link scheduled invocations with the messages they produce.

### Symptoms and Troubleshooting Actions

| Symptom | Causes to Check | Resolution |
|---|---|---|
| Poller lags behind schedule | Scheduler pool lacks threads or previous task runs too long | Measure task duration, offload blocking tasks, increase pool with evidence |
| Multiple pollers lag together | Shared scheduler experiencing starvation | Separate schedulers by workload group and control blocking |
| Endpoint reports stopped but task still runs | In-flight task has not finished | Use timeouts, cooperative cancellation, and track in-flight work |
| Stopping one endpoint stops all schedules | Component shut down the shared scheduler | Cancel only owned schedules/stop owned endpoints; context manages the scheduler |
| Shutdown takes too long | Blocking tasks or overly long await termination | Set dependency timeouts and reasonable drain deadlines |
| Scheduled task fails repeatedly | Unclassified or unrecovered exceptions | Configure ErrorHandler, bounded retries, and alerts |
| Queue grows while scheduler looks healthy | Scheduler only handles intake; downstream consumer is the bottleneck | Measure producer/consumer rates, bound queues, and tune concurrency |

## 15. Testing Lifecycle and Shutdown

Scheduler tests should verify behavior rather than relying on long wait times.

- Register a task and verify it is invoked according to the trigger.
- Cancel the `ScheduledFuture` and verify no further executions occur.
- Stop the endpoint and verify the poller stops triggering.
- Verify a shared scheduler continues serving other endpoints after one endpoint stops.
- Close the application context and verify the scheduler-owned thread pool is released.
- Test tasks in progress during shutdown to verify timeouts and in-flight behavior.
- Test exceptions to verify ErrorHandler/advice receives the failure.
- Test the scheduler with a blocking task to detect starvation.

Use latches or test schedulers to control execution timing. Avoid long `Thread.sleep()` calls and fragile timing-based assertions. In Spring context tests, close the context explicitly to verify destroy hooks and avoid leaving live threads after tests complete.

## 16. Operational Checklist

Before deploying a scheduler to production, check:

- Which scheduler bean are pollers and scheduled components using?
- Who owns the scheduler and who has authority to shut it down?
- Are pool size and thread name prefix configured and observed?
- Which scheduled tasks can block or call slow downstream dependencies?
- Do pollers use a separate executor when execution needs to be offloaded?
- Do endpoints have appropriate `autoStartup` and `phase` settings?
- Does stopping an endpoint cancel only its schedule without affecting shared schedulers?
- Does shutdown stop intake first, wait for in-flight work, and only then close dependencies?
- Are `waitForTasksToCompleteOnShutdown` and `awaitTerminationSeconds` set appropriately?
- Do delayed/periodic tasks have a clear shutdown policy?
- Do ErrorHandler, retries, and metrics detect failing scheduled tasks?
- Do tests cover endpoint stop, context close, and in-progress tasks?

TaskScheduler operates reliably when schedules are registered by their proper owners, tasks do not hold threads indefinitely, endpoints stop within their proper scope, and the scheduler is shut down only after dependent components have finished their necessary work.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Configuration and Lifecycle](https://docs.spring.io/spring-integration/reference/configuration.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)

The documents above belong to the Spring Framework and Spring Integration Reference Guides. Cross-check your application's dependency versions, as lifecycle hooks and shutdown properties can change across versions.
