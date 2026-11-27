# Thread Naming, Uncaught Exceptions, and Shutdown

In Spring Integration, a `TaskExecutor` offloads work to worker threads to decouple message sending or poller triggering from actual processing time. When a flow runs across multiple threads, observability and lifecycle management become critical: thread names help locate the right work in logs and thread dumps; exception handling catches errors no longer on the producer's call stack; and controlled shutdown lets in-flight tasks finish within a bounded time window.

These three topics directly affect runtime reliability. A thread pool may appear healthy while logs fail to show which task is running; an exception can remain captured inside a `Future` and never reach an uncaught handler; or the application context can close while the executor still has queued tasks. Understand each task execution path before configuring it.

After this lesson, you will be able to:

- Assign meaningful thread names using `ThreadPoolTaskExecutor`.
- Propagate correlation/MDC context across thread boundaries with `TaskDecorator`.
- Distinguish exceptions from `execute()`, `submit()`, `@Async`, and scheduled tasks.
- Choose appropriate exception-handling and rejection mechanisms.
- Configure executor shutdown, wait timeouts, and handling of remaining tasks.
- Diagnose congested thread pools, rejected tasks, and prolonged shutdowns.

## 1. Thread Pools in Spring Integration

`TaskExecutor` is an abstraction for executing `Runnable` tasks. Spring provides implementations and adapters so applications can use an executor without coupling directly to a specific thread pool library. `ThreadPoolTaskExecutor` is the standard choice when you need configurable core/max pool sizes, queue capacity, thread name prefixes, and Spring-managed lifecycle.

In Spring Integration, executors can appear in several places:

- `ExecutorChannel` offloads message dispatch to worker threads.
- Pollers can use an executor to separate polling work from the scheduler thread.
- Asynchronous services or `@Async` methods can use dedicated executors.
- Certain adapters and integration components maintain internal executors or accept an application-configured executor.

Avoid lumping every kind of work into a single pool without assessing load. If slow HTTP calls occupy every worker, other tasks like status updates or notifications must wait. Splitting pools by workload isolates blast radius, though it increases the number of queues, threads, and operational metrics to monitor.

## 2. Naming Threads for Runtime Observability

Default thread names like `pool-3-thread-2` reveal nothing about which flow or executor owns a thread. Setting a distinct prefix makes threads recognizable in logs, thread dumps, profilers, and monitoring tools.

Example `ThreadPoolTaskExecutor` configuration:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("si-orders-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
```

Worker threads will be named starting with `si-orders-`; the numeric suffix is managed by the thread factory. Prefixes should reflect the role or work group, such as `si-poller-`, `si-inventory-`, or `si-notification-`. Avoid overly long names or dynamic data such as order IDs, because threads are reused across many different tasks.

Example logging the thread name:

```java
log.info("Processing order {} on thread {}",
        order.getId(), Thread.currentThread().getName());
```

A thread name answers "which worker is running this task?" It is not a message identifier or correlation ID. One worker thread sequentially handles many unrelated messages, so never infer business relationships or message ordering from thread names.

### 2.1. When You Need a Custom ThreadFactory

`setThreadNamePrefix()` suffices for most cases. If you need to install a custom `UncaughtExceptionHandler` per worker, you can supply a `ThreadFactory`. When supplying a custom factory, set thread names inside the factory yourself, because the factory replaces the executor's default thread-creation naming.

```java
AtomicInteger sequence = new AtomicInteger();

executor.setThreadFactory(task -> {
    Thread thread = new Thread(
            task,
            "si-orders-worker-" + sequence.incrementAndGet());
    thread.setUncaughtExceptionHandler((worker, error) ->
            log.error("Uncaught error on {}", worker.getName(), error));
    return thread;
});
```

This illustrates a custom factory; in real applications, preserve appropriate environment thread properties such as daemon status, thread group, and classloader context. Never create new threads manually per message when a pool-managing executor is available.

## 3. Thread Names and MDC Are Not the Same

Logging frameworks commonly support MDC (Mapped Diagnostic Context) to attach metadata to logs, such as `traceId`, `correlationId`, `tenantId`, or `messageId`. MDC typically relies on `ThreadLocal`. When a task moves to a worker thread, MDC from the sending thread is not copied automatically to the worker.

With thread naming alone, logs tell you `si-orders-2` is running, not which order or trace that task belongs to. Use MDC to store per-execution metadata and propagate context across the executor boundary in a controlled way.

`TaskDecorator` lets you wrap a `Runnable` before the executor runs it. The following example captures MDC from the sending thread, sets it on the worker during task execution, and restores the prior context afterward:

```java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }
                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Register the decorator with the executor:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

The `finally` block is essential. Worker threads are reused; failing to restore or clear MDC can leak metadata from a previous message into logs for the next message. `TaskDecorator` only propagates contexts explicitly captured and restored in code; it does not automatically propagate arbitrary `ThreadLocal` values, transactions, or security contexts. For tracing and security, use the respective framework's context-propagation mechanisms.

## 4. Which Path Do Exceptions Follow?

Not every exception occurring on a worker thread reaches the same handler. Where errors surface depends on how the task is executed:

| Execution mechanism | Where is the exception observed? |
|---|---|
| `execute(Runnable)` | An exception escaping `run()` can terminate the current worker and reach the thread's `UncaughtExceptionHandler`. |
| `submit(Runnable/Callable)` | The exception is captured inside the `Future`; the caller sees it as an `ExecutionException` when calling `get()`. |
| `@Async` returning `Future`/`CompletableFuture` | The caller observes the failure via the asynchronous result. |
| `@Async` returning `void` | Uses `AsyncUncaughtExceptionHandler` to handle exceptions with no returned future. |
| Scheduled task | Uses the scheduler's `ErrorHandler`; logging/propagation/suppression depends on configuration and schedule type. |
| Spring Integration message flow | Follows exception propagation and the error channel/error flow configured for the endpoint. |

Therefore, installing only an `UncaughtExceptionHandler` is not enough to catch all executor errors. In particular, tasks run via `submit()` are typically wrapped in a `FutureTask`; exceptions stay inside the future and never escape `run()` to trigger an uncaught handler.

## 5. execute(): Exceptions Escaping the Worker Thread

`execute()` submits a `Runnable` to the executor without returning a `Future`. If `Runnable.run()` throws an uncaught exception inside the task, it can escape the worker thread. With `ThreadPoolExecutor`, the worker running the failing task may terminate and the pool spawns a replacement worker as needed. The thread's `UncaughtExceptionHandler` can record this failure.

```java
integrationExecutor.execute(() -> {
    processOrder(order); // May throw RuntimeException
});
```

If you want to observe errors at the task boundary, wrap the work in a `try/catch` to log or forward the error to the application's recovery mechanism:

```java
integrationExecutor.execute(() -> {
    try {
        processOrder(order);
    }
    catch (Exception ex) {
        log.error("Order processing failed: {}", order.getId(), ex);
        throw ex;
    }
});
```

The example above logs and rethrows so the exception still follows the executor's handling path. If you only log and swallow the exception, the system may treat the task as completed even though business logic failed. Decide explicitly whether the task should be retried, routed to an error flow, or marked failed in storage.

## 6. submit(): Exceptions Captured in a Future

`submit()` returns a `Future`. The executor wraps the task in an object capable of storing both the result and any exception. Because the exception is recorded in the future, it generally does not become an uncaught exception on the worker thread.

```java
Future<?> future = integrationExecutor.submit(() -> processOrder(order));

try {
    future.get();
}
catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    log.error("Order task failed: {}", order.getId(), cause);
}
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    log.warn("Waiting for order task was interrupted", ex);
}
```

`get()` waits for the task to complete and throws `ExecutionException` if the task failed. In asynchronous flows, avoid calling `get()` immediately on the sending thread if the goal is non-blocking execution; use callbacks or `CompletableFuture` composition to handle completion.

If the caller discards the `Future`, exceptions may go unobserved. Retain and inspect the future, or use a callback API with explicit error recording.

## 7. Exceptions from @Async and Scheduled Tasks

### 7.1. @Async

For `@Async` methods returning `Future` or `CompletableFuture`, errors appear in the asynchronous result. For `@Async void` methods, there is no future for callers to inspect, so Spring invokes `AsyncUncaughtExceptionHandler`.

```java
@Configuration
@EnableAsync
class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) ->
                log.error("Async method {} failed",
                        method.toGenericString(), error);
    }
}
```

This handler targets exceptions thrown by `@Async` methods returning `void`. It is neither a global handler for every `Runnable` on `ThreadPoolTaskExecutor` nor a replacement for Spring Integration's error channel.

### 7.2. Scheduled Tasks

With `TaskScheduler`, configure an `ErrorHandler` to define how exceptions from scheduled callbacks are handled:

```java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.setThreadNamePrefix("si-scheduler-");
scheduler.setErrorHandler(error ->
        log.error("Scheduled task failed", error));
```

Error handling for repeating schedules can differ from one-shot tasks depending on the scheduler and trigger. Some default configurations log and continue the schedule; others allow exceptions to propagate and halt subsequent executions according to scheduler semantics. If continuing or stopping a schedule carries business meaning, configure an explicit `ErrorHandler` and test it.

### 7.3. Spring Integration Error Channel

Within a message flow, handler exceptions can route through an error channel or error flow according to endpoint configuration and message headers. This is message-level error handling. It does not automatically replace `Future.get()`, `AsyncUncaughtExceptionHandler`, or `TaskScheduler.ErrorHandler`; identify which mechanism runs the task before looking for its errors.

## 8. RejectedExecutionHandler When the Pool Overloads

An executor has bounded worker counts and queue capacity. When it cannot accept additional tasks, `ThreadPoolExecutor` invokes `RejectedExecutionHandler`.

| Policy | Behavior | Notes |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException`. | Explicit failure; caller must handle or report it. |
| `CallerRunsPolicy` | Sending thread runs the task itself if the executor has not shut down. | Creates natural backpressure but can slow down producers or scheduler threads. |
| `DiscardPolicy` | Drops the new task without an error. | Risks silent loss of work. |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries submitting the new task. | Can lose older work; consider ordering and integrity impacts. |

For business messages, silent discard policies are usually hazardous. `AbortPolicy` makes failures visible but requires recovery in the producer or error flow. `CallerRunsPolicy` can provide useful backpressure when callers tolerate synchronous execution; however, if the caller is a scheduler thread, it can push long-running work back onto the scheduler and delay schedules.

Monitor active threads, queue depth, and rejection counts. An overly large queue does not make the executor process faster; it only allows backlog and wait times to grow.

## 9. Configuring an Observable Executor with Shutdown Support

An example configuration combining naming prefixes, MDC propagation, a bounded queue, explicit rejection, and graceful shutdown:

```java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("si-runtime-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

These numbers are illustrative, not universal sizing recommendations. Base core/max pool sizes on task type (CPU-bound vs. I/O-bound), processing durations, database/API limits, and target concurrency. Queue capacity should absorb brief fluctuations without hiding sustained overload.

`ThreadPoolTaskExecutor` is managed by Spring when declared as a bean. Avoid calling `initialize()` or `shutdown()` arbitrarily from business services; let the `ApplicationContext` lifecycle manage the executor unless your application explicitly designs a separate management flow.

## 10. Graceful Shutdown: Stopping Intake and Draining Tasks

When the application closes its `ApplicationContext`, the executor must know how to handle running tasks and queued tasks. `ThreadPoolTaskExecutor` inherits lifecycle options from `ExecutorConfigurationSupport`.

Two commonly used properties:

- `setWaitForTasksToCompleteOnShutdown(true)`: instructs the executor to shut down gracefully so accepted tasks—both running and queued—can finish rather than being canceled immediately.
- `setAwaitTerminationSeconds(30)`: caps how long shutdown waits for the executor to terminate.

When not waiting for tasks to complete, the executor can perform an immediate shutdown that interrupts running tasks and skips queued tasks. Interruption is only a cooperative signal; tasks must respond by handling `InterruptedException` or checking interrupt status. An I/O call without a timeout or code ignoring interrupts can still keep running.

### 10.1. Shutdown Ordering in a Message Flow

Stop sources of new work first, then close the executors used by endpoints:

```text
1. Stop producer / inbound adapter / poller
                    |
                    v
2. Stop submitting new messages/tasks
                    |
                    v
3. Wait for workers to finish running and accepted tasks
                    |
                    v
4. Close the executor after dependent components have stopped
                    |
                    v
5. Complete ApplicationContext shutdown
```

Exact ordering also depends on lifecycle phases and components. If an executor shuts down while endpoints are still submitting tasks, subsequent submissions can be rejected. Conversely, waiting indefinitely on queued tasks that cannot finish because downstream systems have already closed can stall shutdown until the timeout expires.

### 10.2. Tasks Remaining After Timeout

If the timeout expires before workers finish, the application needs an explicit policy for unfinished tasks. Never assume tasks completed simply because context shutdown started. For critical work, design idempotency, persist state, or use a durable broker to enable recovery after restart.

`ThreadPoolTaskExecutor`'s queue is normally an in-memory queue. Tasks remaining in the queue when the process exits are not automatically persisted to rerun on startup. If work must survive restarts, use a message broker or durable store rather than relying on an executor queue.

## 11. Observing the Executor at Runtime

`ThreadPoolTaskExecutor` exposes access to the underlying `ThreadPoolExecutor` after initialization. Operational metrics can be inspected:

```java
ThreadPoolExecutor pool = integrationExecutor.getThreadPoolExecutor();

log.info("poolSize={}, active={}, queued={}, completed={}",
        pool.getPoolSize(),
        pool.getActiveCount(),
        pool.getQueue().size(),
        pool.getCompletedTaskCount());
```

Track these metrics over time rather than as a single snapshot:

- Pool size and active count show worker utilization.
- Queue size and queue wait time indicate accumulating backlog.
- Completed task count measures completed work over time.
- Rejected execution counts should be tracked separately via a rejection handler or dedicated metrics.
- Task duration and error counts by task type reveal what is occupying workers.

If active count frequently equals max pool size while the queue climbs steadily, either the executor lacks capacity or downstream dependencies are slow. If active count stays low while tasks still lag, the bottleneck may lie in a scheduler, upstream source, or a different queue.

## 12. Common Pitfalls and How to Handle Them

| Symptom | Cause | Resolution |
|---|---|---|
| Logs only show `pool-1-thread-1` | No thread name prefix configured. | Set a prefix reflecting the executor's role. |
| Worker logs lack trace/correlation IDs | MDC does not propagate automatically across threads. | Use `TaskDecorator` or proper context propagation. |
| Uncaught handler misses `submit()` exceptions | Exceptions are stored inside the `Future`. | Read `Future.get()` or attach completion callbacks. |
| `@Async void` fails without caller awareness | No `Future` exists to return outcomes. | Configure an `AsyncUncaughtExceptionHandler`. |
| Scheduled task stops or fails silently | No `ErrorHandler` configured and periodic vs. one-shot behavior unverified. | Configure an explicit error policy on the scheduler. |
| Tasks vanish under executor overload | A discard rejection policy is configured. | Choose explicit rejection and design backpressure/recovery. |
| Producer slows down unexpectedly | `CallerRunsPolicy` runs tasks on the calling thread. | Identify whether the caller is a scheduler, request thread, or producer. |
| Shutdown drags on | Tasks blocked on I/O, deep queue backlog, or ignoring interrupts. | Enforce timeouts, stop producers before executors, and monitor termination wait. |
| Tasks do not resume after restart | Executor queue resides only in memory. | Use a broker or persistent store when durability is needed. |

## 13. Diagnostic Workflow

When asynchronous tasks fail or executor shutdown misbehaves, investigate in sequence:

1. **Identify the executor.** Find the bean name, thread prefix, and components using that executor.
2. **Identify the submission method.** Was the task invoked via `execute`, `submit`, `@Async`, a scheduler, or a Spring Integration endpoint?
3. **Locate the error receiver.** Inspect the uncaught handler, `Future`, async exception handler, scheduler `ErrorHandler`, or error channel.
4. **Inspect thread dumps and metrics.** Check which workers are active, whether the queue is growing, and whether the pool hits max size.
5. **Check rejections.** Verify whether tasks are rejected or discarded under pool overload.
6. **Inspect shutdown policy.** Verify that producers stop before the executor and that wait flags and timeouts are properly set.
7. **Verify recoverability.** Confirm whether critical tasks are persisted durably or can safely retry idempotently after a restart.

## 14. Self-Check

**Scenario:** An `ExecutorChannel` uses a `ThreadPoolTaskExecutor`. Logs show thread `si-runtime-2` processing several different messages. One task throws an exception, yet `UncaughtExceptionHandler` records nothing. During application shutdown, 40 tasks remain in the queue.

1. Why cannot thread names be used to identify specific messages?
2. If a task was submitted via `submit()`, where does its exception go?
3. What configuration makes a trace ID from the sending thread appear in worker logs?
4. How do you wait for accepted tasks to complete during shutdown?
5. Will remaining tasks in the executor queue automatically recover after a process restart?

**Answer hints:** (1) Worker threads are reused across many tasks; put message ID/correlation ID in MDC. (2) The exception is held in the `Future` and must be retrieved by the caller. (3) Use a `TaskDecorator` to capture/set/restore MDC or a context propagation mechanism. (4) Configure `waitForTasksToCompleteOnShutdown` and an appropriate wait timeout, while stopping producers before the executor. (5) No; executor queues are typically in-memory, so a broker or persistent store is needed for recovery.

**Practice exercise:** Create two executors with distinct prefixes for two work groups. Submit one task with `execute()` and one with `submit()`; intentionally throw exceptions to observe both handling paths. Add an MDC `correlationId`, configure a `TaskDecorator`, and verify worker logs. Finally, build up a backlog and shut down with both wait and no-wait policies to observe termination time and remaining tasks.

## References

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Javadoc — TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [Java Javadoc — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
