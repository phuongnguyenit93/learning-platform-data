# Scheduled Task Error Handlers

Spring Integration uses a scheduler to trigger pollers and periodic tasks. Spring applications can also use `@Scheduled` or `TaskScheduler` to run background work. When a scheduled task throws an exception, it is important to determine **which layer receives the exception, whether that policy lets the next execution continue, and whether the error carries enough context for business-level handling**.

Spring TaskScheduler's `ErrorHandler` and Spring Integration's `errorChannel` are related but serve different roles. `ErrorHandler` handles exceptions escaping from a scheduled `Runnable`; `errorChannel` wraps errors in a message flow into an `ErrorMessage` so another flow can classify, persist, or alert on them. Choosing the right handling layer avoids tasks silently stopping or errors merely being logged with no recovery process.

## 1. Where Do Scheduled Tasks Run?

`TaskScheduler` is responsible for scheduling `Runnable` execution at a specific time, at a fixed rate, with a fixed delay, or via a `Trigger`. With `ThreadPoolTaskScheduler`, the scheduler uses a group of threads to execute due tasks.

In Spring Integration, a poller is an example of a scheduled task. The scheduler triggers the polling consumer; the consumer receives messages from a `PollableChannel` or calls a message source; then messages are passed into flow steps. An application may also have standalone tasks such as data synchronization, state cleanup, or connectivity checks.

```text
TaskScheduler
    |
    +-- @Scheduled method
    |
    +-- Application scheduled Runnable
    |
    +-- Spring Integration poller
            |
            +-- receive message
            +-- dispatch to endpoint
            +-- process message
```

Not every Spring Integration endpoint is a scheduled task. A `DirectChannel`, `ExecutorChannel`, or inbound message-driven adapter can dispatch messages via other mechanisms. Therefore, a scheduler's `ErrorHandler` policy applies only to tasks that actually run through that scheduler.

## 2. Spring TaskScheduler ErrorHandler

Spring provides the `org.springframework.util.ErrorHandler` interface with a single method accepting `Throwable`:

```java
public interface ErrorHandler {
    void handleError(Throwable t);
}
```

`ThreadPoolTaskScheduler` allows configuring an error handler via `setErrorHandler(...)`. The error handler is invoked when an exception escapes from a scheduled task and is not caught inside the task or an outer wrapper.

`ErrorHandler.handleError(Throwable)` receives only the exception—not directly the task name, registration ID, or message headers. If one scheduler serves multiple tasks, add context via per-task loggers/metrics or wrap each `Runnable` with a wrapper carrying a name and business key. For errors tied to a message, a poller `errorChannel` usually provides richer context.

Example configuring a scheduler with a dedicated error handler:

```java
@Configuration
@EnableScheduling
public class SchedulerConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(SchedulerConfiguration.class);

    @Bean("integrationTaskScheduler")
    public ThreadPoolTaskScheduler integrationTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setErrorHandler(error ->
            log.error("Scheduled task failed", error));
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        return scheduler;
    }
}
```

In this example, the error handler logs the exception and returns normally. For repeating scheduled tasks, this handling lets the scheduler proceed with subsequent runs. The scheduler bean can also be used by other tasks explicitly configured to use it.

If an application has multiple `TaskScheduler` beans, name the beans and choose the appropriate scheduler for each work group. Do not assume all `@Scheduled` methods and all pollers use the same scheduler if the application configures multiple pools or custom schedulers.

## 3. Default Policies: Suppress and Propagate

Spring provides `TaskUtils` to supply default error handlers for scheduled tasks. The two key policies are:

| Policy | Behavior When a Task Throws | Consequence for Repeating Tasks |
|---|---|---|
| Log and suppress | Logs the exception and does not rethrow | The schedule continues on the next run. |
| Log and propagate | Logs and rethrows the exception outward | The exception can terminate the scheduled future; subsequent runs of a repeating task may be prevented. |

`TaskUtils.getDefaultErrorHandler(true)` returns the log-and-suppress policy for repeating tasks. `TaskUtils.getDefaultErrorHandler(false)` returns the log-and-propagate policy for one-shot tasks. The constants `LOG_AND_SUPPRESS_ERROR_HANDLER` and `LOG_AND_PROPAGATE_ERROR_HANDLER` also represent these two choices.

The reason for two policies is that periodic tasks usually need to keep retrying on subsequent runs, whereas one-shot tasks usually need the exception observed as a failed execution. These are Spring scheduler defaults; an application can override them with a custom `ErrorHandler`.

### Suppress Does Not Mean Success

When the error handler logs and returns, the scheduler only knows the exception was handled at the error handler layer. It does not know whether the business operation succeeded. If a data synchronization task fails, the next run may retry, yet the business state still needs to be recorded as failed or incomplete.

Therefore, periodic tasks should have dedicated observability: error counts, last success timestamp, last error timestamp, retry counts, and backlog status. Do not rely on the schedule continuing to run as proof that data was processed correctly.

## 4. Custom ErrorHandler: Logging, Metrics, and Alerting

A custom error handler can emit structured logs, increment counters, and trigger alerts. The handler must be fast, safe, and not introduce a new chain of errors.

```java
@Bean
public ErrorHandler scheduledTaskErrorHandler(MeterRegistry registry) {
    return error -> {
        registry.counter("app.scheduled.errors").increment();
        LoggerFactory.getLogger("scheduled-task")
            .error("Scheduled execution failed", error);
    };
}
```

Then inject the error handler into the scheduler:

```java
@Bean("integrationTaskScheduler")
public ThreadPoolTaskScheduler integrationTaskScheduler(
        ErrorHandler scheduledTaskErrorHandler) {

    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("si-scheduler-");
    scheduler.setErrorHandler(scheduledTaskErrorHandler);
    return scheduler;
}
```

This is an illustrative example using Micrometer `MeterRegistry`; the Micrometer dependency and registry bean must exist in the application. If one scheduler serves multiple tasks, an aggregate counter only indicates that an error occurred. To know which task failed, create per-task-group metrics or wrap each `Runnable` with a task name before registering it.

Do not send emails, call slow webhooks, or execute long synchronous I/O directly inside the scheduler error handler. Doing so holds the scheduler thread and can delay other tasks. If external alerting is needed, push a lightweight event to a dedicated channel/queue and let another component send the alert.

If a custom error handler itself throws an exception, the new exception can escape into the scheduler. For repeating tasks, that can stop the task's schedule. Protect the error handler itself: if auxiliary metrics or logging fail, still log a fallback and avoid losing control of the scheduled future's lifecycle.

## 5. ErrorHandler and errorChannel in Spring Integration Pollers

A poller is not just a generic `Runnable`. It executes within a message flow context and can know which message was just received, which endpoint is processing it, and which error channel is configured. Accordingly, Spring Integration supports routing poller errors to an error channel.

Example configuring a poller with an error channel:

```java
@Bean
public MessageChannel pollerErrors() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow ordersPollingFlow(
        @Qualifier("ordersQueue") PollableChannel ordersQueue,
        OrderHandler orderHandler) {

    return IntegrationFlow.from(ordersQueue, endpoint -> endpoint.poller(
            Pollers.fixedDelay(1_000)
                .maxMessagesPerPoll(10)
                .errorChannel("pollerErrors")))
        .handle(orderHandler, "handle")
        .get();
}
```

The `pollerErrors` channel needs an active subscriber. Declaring the channel bean explicitly clarifies where errors are delivered and avoids relying on the framework auto-creating channels by name.

A handler can consume `ErrorMessage` instances from that channel:

```java
@Component
public class PollerErrorHandler {

    @ServiceActivator(inputChannel = "pollerErrors")
    public void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        // Classify error, record message, and route to recovery workflow.
    }
}
```

`ErrorMessage` has a `Throwable` payload; it can carry `originalMessage` when the failure is associated with a received message. If the error occurred before any message existed, such as an error reading a polling source, the original message may not exist.

`errorChannel` is part of message-flow error handling. `TaskScheduler`'s `ErrorHandler` is the layer handling exceptions escaping from the scheduled `Runnable`. When the poller catches and publishes an error as an `ErrorMessage`, the exception may not propagate further to the scheduler error handler. Conversely, errors occurring outside poller error handling can still escape to the scheduler layer. Therefore, do not configure both mechanisms and assume both receive the exact same exception.

If no dedicated error channel is declared for a poller, verify the default error handling configuration and global `errorChannel` of your application for your Spring Integration version. A channel lacking an appropriate subscriber or an error flow that itself throws can still cause error handling to fail.

## 6. Distinguishing Receive Errors from Message-Processing Errors

In a polling endpoint, exceptions can arise at several stages:

1. **Message source / receive:** errors accessing the data source or pulling a message from the channel.
2. **Message conversion:** errors converting payload or headers.
3. **Handler:** business errors when invoking a service or processing the message.
4. **Downstream send:** errors passing the message to the next channel.
5. **Error flow:** errors when the `ErrorMessage` handler itself executes.

These errors can carry different contexts. If a handler fails after a message exists, `ErrorMessage` can usually carry the related message. If the polling source fails before creating a message, there is no business payload to redrive. If a downstream send fails, determine whether the message was partially processed.

Do not record only the exception name. Record endpoint type, channel name, message ID/correlation ID if available, exception class, root cause, and failure stage. Avoid logging full payloads or sensitive data.

## 7. Error Handling Is Not Automatically Retry

An error handler can log, alert, persist the failed message, or route an `ErrorMessage` to another flow. Those actions do not automatically re-invoke the business handler.

Retries must be configured explicitly using retry advice or a retry mechanism aligned with the boundary to protect. For errors at a request handler, `RequestHandlerRetryAdvice` can wrap the handler operation. For errors during polling or message reception, choose appropriate advice and transaction boundaries for the poller/adapter.

When designing retries:

- Retry only recoverable errors, such as transient timeouts or temporary dependency outages.
- Cap attempt counts and use backoff to avoid amplifying load while a dependent system is failing.
- Do not infinitely retry malformed data errors or unrecoverable business errors.
- Ensure handlers are idempotent or have deduplication mechanisms.
- After retries are exhausted, store the message and error details where they can be investigated or redriven.

If a custom `ErrorHandler` suppresses exceptions so the schedule continues, that is a schedule-continuation policy, not a retry of the same message. With a poller, a message already received from a `QueueChannel` may no longer remain in the queue; if replay is needed, the application must persist the message or use a source that supports redelivery.

## 8. Errors in @Scheduled Methods

`@Scheduled` methods also run via the scheduler mechanism. Example:

```java
@Component
public class PartnerSyncJob {

    @Scheduled(fixedDelay = 30_000)
    public void synchronize() {
        // Synchronize a subset of data with the partner.
    }
}
```

If the method throws an exception, the scheduler's error handler policy handles the exception escaping from the scheduled invocation. With Spring's default scheduler, repeating tasks typically use log-and-suppress so the schedule continues; a custom `TaskScheduler` can be configured to control policy and pool sizing.

If one scheduled method performs multiple groups of work, split them into separate tasks with distinct names and metrics. An error in a partner sync task should not obscure observability for another cleanup task. Also set timeouts on network calls so a single run does not occupy a scheduler thread for too long.

## 9. Errors in the Scheduler Can Stop a Schedule

For repeating scheduled tasks, if an exception escapes the task and propagates to the scheduler, the scheduled executor mechanism can mark that periodic execution as failed and stop scheduling subsequent runs. This is why a custom error handler needs an explicit policy.

Example allowing a repeating task to continue after an error:

```java
scheduler.setErrorHandler(error -> {
    log.error("Periodic refresh failed; next run remains scheduled", error);
});
```

Because the handler returns normally, the scheduler sees no escaping exception. If you want a task to stop permanently after a critical error, use a propagate policy or explicitly cancel the `ScheduledFuture`. Avoid accidentally halting a schedule merely because an error handler sent an alert and threw a secondary error.

For one-shot tasks, propagate can be an appropriate choice since there is no subsequent run to preserve. However, persist failure results and status where operations tooling can inspect them.

## 10. Transactions and Shutdown for Scheduled Tasks

Transaction advice can wrap a poller's message reception and processing, depending on endpoint configuration. The scheduler error handler does not replace the transaction manager and does not decide rollbacks. If an exception is caught and suppressed before a transaction interceptor sees it, the transaction may commit along the active execution path.

In asynchronous flows, thread-bound transactions do not automatically propagate to executor threads. If a scheduled task sends a message to an `ExecutorChannel`, a transaction wrapping the send call does not inherently cover downstream work. Place transactions on the consumer that actually performs data operations and clearly define source message ack/commit semantics.

When the context closes, the scheduler must stop creating new runs and in-flight tasks must finish within the shutdown budget. If an error handler persists errors or publishes messages, it also needs to finish before dependencies like databases, message brokers, or error channels close. Configure I/O timeouts, graceful shutdown, and appropriate lifecycle ordering.

## 11. Diagnosing When a Scheduled Task Stops Running

When a periodic task stops running, check in order:

1. **Is the scheduler still running?** Check the scheduler bean, thread pool, and ApplicationContext state.
2. **Is the task still scheduled?** For a `ScheduledFuture`, check whether the task was canceled or completed abnormally.
3. **Did the previous run throw an exception?** Search stack traces and check whether the error handler suppressed or propagated it.
4. **Did the error handler itself fail?** Check for logging, metrics, alerting, or auxiliary operation errors inside the handler.
5. **Does the poller have an error channel?** Verify the channel exists, has a subscriber, and the error flow is active.
6. **Is the task blocked?** Inspect thread dumps, I/O timeouts, locks, and execution duration.
7. **Is another task exhausting the scheduler pool?** Compare active threads, queues, and run durations across task groups.
8. **Is the context shutting down?** Check for `RejectedExecutionException`, lifecycle phases, and bean destruction timestamps.

Useful metrics include execution count, error count, last successful run timestamp, task duration, active tasks, queue depth, and scheduler task rejections. For pollers, add received message count, empty poll count, and published `ErrorMessage` count.

## 12. Testing ErrorHandler

You can test error handler policy with a repeating task that intentionally throws on the first run and succeeds on the next. Use a latch for synchronization instead of waiting with `Thread.sleep()`:

```java
AtomicInteger attempts = new AtomicInteger();
CountDownLatch succeeded = new CountDownLatch(1);

Runnable task = () -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("temporary failure");
    }
    succeeded.countDown();
};

ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setErrorHandler(error -> log.warn("Scheduled task failed", error));
scheduler.initialize();

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
    task,
    100L
);

assertTrue(succeeded.await(2, TimeUnit.SECONDS));
future.cancel(false);
scheduler.shutdown();
```

This is an illustrative snippet; real tests should put cleanup in `finally` or teardown so the future is always canceled and the scheduler is always shut down even if assertions fail. You can write a contrasting test with a propagating error handler to verify the future does not keep running after an exception.

For pollers, create a `QueueChannel`, configure an `errorChannel`, send a message that makes the handler throw an exception, and verify the error flow receives an `ErrorMessage`. Add a test case where receive/source throws an exception to verify handling when no original message exists. Tests should control timing and timeouts rather than depending on machine execution speed.

## 13. Common Design Mistakes

- **Assuming log-and-suppress means task success.** The schedule continues, yet business work may still be failing.
- **Letting the error handler throw secondary exceptions.** An error in alerting or metrics can halt a repeating schedule.
- **Using the scheduler error handler to handle all message errors.** Errors already converted into `ErrorMessage` by a poller may not reach the scheduler.
- **Only logging without persisting state.** You cannot tell how many times a task failed or which data remains unprocessed.
- **Confusing error handling with retry.** Logging or publishing an `ErrorMessage` does not automatically re-run the original message.
- **Infinite retries.** Can cause overload, repeated side effects, and mask configuration bugs.
- **Using an overly small scheduler pool.** Slow tasks or a blocking error handler can delay other pollers.
- **Not checking error channel subscribers.** ErrorMessage instances may go unhandled.
- **Not testing repeating tasks throwing exceptions.** A single error could halt the schedule without early detection.

## 14. Design Checklist

Before putting a scheduled task or poller into operation, verify:

- Is the task one-shot or repeating?
- Which scheduler executes the task and which error handler is attached to that scheduler?
- Is the default policy suppress or propagate?
- When an error occurs, should the task continue on the next run or stop intentionally?
- If it is a poller, which error channel receives published errors and who consumes `ErrorMessage`?
- Does the error flow preserve the original message, exception cause, and correlation ID whenever possible?
- At which boundary do retries apply, and what are the retry limits and backoff?
- Which metrics indicate the last successful run and error counts?
- Can the error handler itself throw or block scheduler threads?
- During context shutdown, do the scheduler and error flow have enough time to finish?

By distinguishing scheduler-level `ErrorHandler`, poller `errorChannel`, retry advice, and transaction boundaries, scheduled tasks can both continue operating after transient failures and preserve the audit trail needed for recovery. The key is letting each layer handle its proper share: the scheduler controls the schedule, the error handler handles exceptions escaping from the task, and the error flow manages errors tied to messages and business logic.
