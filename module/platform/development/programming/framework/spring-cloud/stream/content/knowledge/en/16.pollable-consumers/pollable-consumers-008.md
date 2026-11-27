# Managing Poll Schedules, Execution Threads, and Safe Loop Shutdown

With a Spring Cloud Stream proactive consumer, the application calls `PollableMessageSource` to fetch messages when ready to process them. This approach gives control over reading schedules, wait times, execution threads, and stopping behavior. In return, the application must manage the polling lifecycle intentionally.

A message-reading loop must answer four questions: when to poll, on which thread to poll, how long message processing takes, and what happens when the application shuts down. Calling poll continuously without a wait interval can burn CPU when the queue is empty. Running an infinite loop on Spring's startup thread can prevent the application from completing startup. Stopping the process without waiting for an in-flight handler can cause messages to be redelivered or leave processing status unclear depending on the binder.

## 1. PollableMessageSource and Consumer Autonomy

Spring Cloud Stream provides `PollableMessageSource` for the proactive consumer model. Instead of the framework continuously pushing messages into a function, the application calls `poll()` to request a message and supplies a `MessageHandler` to process it.

Minimal example:

```java
@Component
public class OrderPoller {

    private final PollableMessageSource source;
    private final OrderService orderService;

    public OrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    public boolean pollOnce() {
        return source.poll(message -> {
            OrderPlaced event =
                (OrderPlaced) message.getPayload();

            orderService.handle(event);
        }, 500L);
    }
}
```

In the example, the application requests a poll with a 500-millisecond timeout. If a message is received, the handler is invoked. If no message arrives within the wait window, `poll()` returns `false`. If the handler processes successfully, the call finishes and `poll()` returns `true`.

`PollableMessageSource` is a synchronous API: calling `poll()` performs retrieval and invokes the handler on the poller's execution thread. Consequently, the handler's processing duration directly impacts how long a single poll takes to complete. This forms the basis for designing reading schedules and concurrency limits.

## 2. Distinguishing Timeouts, Empty Polls, and Error Handling

Poll outcomes must be interpreted accurately:

| Situation | Typical Result | Application Action |
|---|---|---|
| Message received and handler completes | `poll()` returns `true` | Continue the reading loop per schedule |
| No message within timeout | `poll()` returns `false` | Wait an interval before polling again |
| Handler throws an exception | Error propagates out of the poll after configured retry mechanisms | Record the error and let the binder/error policy handle it |
| Broker or connection failure | May throw an exception | Apply backoff, observe state, and recover the connection |

Do not use `false` to represent a business processing error. This value only indicates that no message was received during that poll within the timeout. Handler or broker errors must be handled via exceptions and error-handling mechanisms.

You can use the `poll(handler, timeout)` overload to avoid continuous polling loops when no messages exist. If your binder version provides its own timeout or different semantics, verify against that version's API. Do not assume all binders share identical behavior on timeouts or connection failures.

## 3. Scheduling Polling and Avoiding Busy Loops

The following loop is problematic:

```java
while (running) {
    source.poll(this::handle);
}
```

If `poll()` returns immediately when no messages are available, the loop keeps calling it continuously and consumes CPU. This is a busy loop. It can be fixed using a poll timeout, an idle sleep interval when no messages arrive, or a scheduler controlling the reading frequency.

A proactive consumer typically needs three separate intervals:

- **Poll timeout**: maximum time a single poll waits for a message.
- **Idle delay**: wait time before the next poll when no message was available.
- **Error backoff**: wait time when the broker or handler raises repeated errors.

Do not collapse these three values into a single setting. When the queue is empty, idle delay reduces load. When the broker fails, error backoff should increase progressively to avoid putting extra pressure on the broker. When messages are present, the consumer can poll again promptly or at a capped pace.

Configuration example:

```yaml
app:
  orders:
    polling:
      poll-timeout-ms: 500
      idle-delay-ms: 100
      initial-error-backoff-ms: 500
      max-error-backoff-ms: 30000
      shutdown-wait-seconds: 30
```

These are custom application properties, not standard Spring Cloud Stream properties. Values should be tuned according to acceptable latency, throughput, business service timeouts, and broker capacity.

## 4. Choosing an Execution Thread for the Polling Loop

Because `poll()` and the handler are synchronous, do not run an infinite loop on the startup thread or an HTTP request thread. You can use a dedicated thread for polling:

```java
ExecutorService executor =
    Executors.newSingleThreadExecutor();

executor.submit(() -> {
    while (running) {
        boolean received = source.poll(this::handle, 500L);

        if (!received) {
            Thread.sleep(100L);
        }
    }
});
```

This only illustrates separating the loop from the calling thread. A production implementation must manage the executor and handle interruption, errors, backoff, and shutdown. Do not create a new executor for each poll or each message.

A single thread prevents polls from overlapping and preserves handler invocation order on the poller thread. If the handler performs blocking JDBC or HTTP calls, its execution time holds the polling thread. This is a simple, predictable choice when sequential processing is required.

If higher throughput is needed, you can design a handoff to a bounded worker pool. However, do not submit work to an executor and return from the handler immediately if the binder marks the message processed before the worker finishes. Doing so can acknowledge messages too early. Clearly define completion boundaries, acknowledgment, and retries before decoupling into asynchronous processing.

## 5. Lifecycle Management with SmartLifecycle

A polling loop needs to start and stop along with the Spring ApplicationContext lifecycle. `SmartLifecycle` fits when a component must launch background tasks after the context is ready and shut down gracefully when the context closes.

The following example uses a single-threaded scheduled executor. Only one polling task runs at a time; if a message is received it polls again immediately, if the queue is empty it waits the idle delay, and on errors it increases backoff:

```java
@Component
public class ManagedOrderPoller implements SmartLifecycle {

    private static final Logger log =
        LoggerFactory.getLogger(ManagedOrderPoller.class);

    private static final long POLL_TIMEOUT_MS = 500;
    private static final long IDLE_DELAY_MS = 100;
    private static final long MAX_BACKOFF_MS = 30_000;

    private final PollableMessageSource source;
    private final OrderService orderService;

    private final AtomicBoolean running = new AtomicBoolean(false);

    private volatile ScheduledExecutorService executor;
    private volatile ScheduledFuture<?> scheduledTask;
    private int consecutiveFailures;

    public ManagedOrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    @Override
    public synchronized void start() {
        if (!running.compareAndSet(false, true)) {
            return;
        }

        consecutiveFailures = 0;
        executor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "orders-poller");
            thread.setDaemon(true);
            return thread;
        });

        scheduleNext(0);
        log.info("Order poller started");
    }

    private void scheduleNext(long delayMs) {
        if (!running.get()) {
            return;
        }

        ScheduledExecutorService current = executor;
        if (current == null) {
            return;
        }

        try {
            ScheduledFuture<?> next = current.schedule(
                this::pollOnce,
                delayMs,
                TimeUnit.MILLISECONDS
            );
            scheduledTask = next;

            // stop() may run concurrently with scheduling.
            if (!running.get()) {
                next.cancel(false);
            }
        } catch (RejectedExecutionException ex) {
            // The executor may have already shut down while the application is stopping.
            if (running.get()) {
                log.warn("Polling task was rejected while the poller is running", ex);
            }
        }
    }

    private void pollOnce() {
        if (!running.get()) {
            return;
        }

        long nextDelay = IDLE_DELAY_MS;

        try {
            boolean received = source.poll(message -> {
                OrderPlaced event =
                    (OrderPlaced) message.getPayload();

                orderService.handle(event);
            }, POLL_TIMEOUT_MS);

            consecutiveFailures = 0;
            if (received) {
                nextDelay = 0;
            }
        } catch (Exception ex) {
            consecutiveFailures =
                Math.min(consecutiveFailures + 1, 10);

            long multiplier =
                1L << Math.min(consecutiveFailures - 1, 10);

            nextDelay = Math.min(
                MAX_BACKOFF_MS,
                500L * multiplier
            );

            log.warn(
                "Polling failed; retrying after {} ms",
                nextDelay,
                ex
            );
        }

        scheduleNext(nextDelay);
    }

    @Override
    public synchronized void stop() {
        running.set(false);

        ScheduledFuture<?> task = scheduledTask;
        if (task != null) {
            task.cancel(false);
        }

        ScheduledExecutorService current = executor;
        if (current != null) {
            current.shutdown();

            try {
                if (!current.awaitTermination(30, TimeUnit.SECONDS)) {
                    current.shutdownNow();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                current.shutdownNow();
            }
        }

        log.info("Order poller stopped");
    }

    @Override
    public void stop(Runnable callback) {
        stop();
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
```

This is an illustrative implementation skeleton. In a real project, externalize poll timeout, idle delay, backoff, and shutdown timeout into application configuration; add null/type checks for payloads and metrics. Ensure only a single poller bean instance exists for the corresponding binding, preventing two components from accidentally reading the same source.

Key points in the example:

- `start()` creates the executor once and starts the reading schedule.
- A single-threaded executor ensures two polls never run concurrently.
- `scheduleNext()` schedules the next task only after the current poll completes.
- When no message exists, the poller waits the idle delay instead of spinning continuously.
- On errors, backoff grows progressively and is capped.
- `stop()` sets the stop flag, cancels the pending task, and waits for any running task to finish within the allowed window.
- `shutdownNow()` is used only when the wait times out or the thread is interrupted.

If the component needs to restart after `stop()` was called, the example above creates a new executor on the next `start()`. In production systems, check lifecycle restart policies and avoid calling `start()` while the old executor is still terminating.

## 6. Safe Shutdown and Handling In-Flight Messages

Safe shutdown is more than setting `running = false`. You must define what happens to a waiting poll or an in-flight handler.

A graceful shutdown sequence should include:

1. Stop scheduling new polls.
2. Let the current poll finish or time out.
3. Wait for the running handler to complete within the allowed shutdown window.
4. Close the executor and related resources.
5. Let the binder close consumers and connections according to Spring's lifecycle.

In the example, `cancel(false)` cancels a scheduled task without interrupting an already-running one. `executor.shutdown()` rejects new tasks and allows the active task to finish. `awaitTermination()` waits up to 30 seconds. If the handler exceeds that time, `shutdownNow()` sends an interrupt; blocking libraries may not respond immediately if they do not support interruption.

To keep shutdown realistically bounded:

- Set connect/read/request timeouts on business clients.
- Avoid unbounded waits inside handlers.
- Set the shutdown timeout longer than normal processing duration while staying within the orchestrator's grace period.
- Log the in-flight message ID if possible to assist post-shutdown investigation.
- Design idempotent handlers because messages may be redelivered if processing was not acknowledged.

Do not mark a message complete merely because the loop exited. Message acknowledgment depends on the binder and broker. If the process is killed abruptly, the broker may redeliver unacknowledged messages or the consumer may re-read from the last uncommitted offset.

## 7. Exceptions, Retries, and Backoff

When a handler throws an exception, do not catch and ignore it so the poller proceeds as if the message succeeded. The exception must propagate out of the handler so the binder's retry/error-handling mechanism has a chance to act.

Example:

```java
private void handle(Message<?> message) {
    OrderPlaced event =
        (OrderPlaced) message.getPayload();

    // If processing fails, let the exception propagate.
    orderService.handle(event);
}
```

Distinguish two types of retries:

- **In-poll retry**: retry mechanisms configured for the pollable consumer can re-invoke the handler according to Spring Cloud Stream/binder policy.
- **Polling-loop retry**: after a poll fails or the broker errors out, the loop waits for backoff before attempting the next poll.

The two mechanisms do not replace each other. Handler retries do not necessarily fix broker connection failures; the polling loop should not immediately re-poll a poison message causing a permanent failure.

A retry policy should specify attempt limits, backoff, retryable exception types, and how failed messages move to a DLQ if supported by the binder. Requeue, acknowledgment, and DLQ behavior vary among Kafka, RabbitMQ, and Pulsar. Do not infer that a pollable source shares identical delivery semantics across all binders.

## 8. Concurrency Limits and Execution Threads

A single-threaded poller is easy to control when processing order or acknowledgment must be clear. If higher throughput is needed, you can increase poller count or offload processing to a worker pool, but weigh these factors:

- Multiple pollers reading the same binding can compete for messages and alter processing order.
- With Kafka, partitions and consumer groups govern parallelism; arbitrarily adding threads cannot exceed the number of partitions assignable to the group.
- With RabbitMQ, consumer count, prefetch, and acknowledgment affect the number of in-flight messages.
- With Pulsar, subscription type and partition count affect message distribution.
- If the handler returns before the worker finishes, the binder may record processing as successful too early depending on how the handoff is built.

If parallel processing is required, use a bounded executor and explicitly define who waits for results and how errors propagate back to the poller. One safe option is having the handler await the worker result within a bounded timeout; another is building a handoff architecture with explicit state persistence and acknowledgment control. Never fire messages onto a background thread and ignore the outcome.

## 9. Processing State, Idempotency, and Acknowledgment

A message may be received, processed by business logic, persisted to the database, and only afterward recorded by the broker as consumed. If the application fails between steps, the message may be redelivered. Therefore, handlers must handle repeated execution safely.

Example using an event ID:

```java
@Service
public class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderPlaced event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        orders.apply(event);
        processedEvents.save(
            new ProcessedEvent(event.eventId())
        );
    }
}
```

The example assumes updating the order and recording the processed event ID occur in the same database transaction, with a unique constraint on the event ID. If two instances can process the same event concurrently, rely on the unique constraint and handle conflicts explicitly rather than relying solely on a check-then-insert operation.

Do not manually acknowledge messages if the binder is managing acknowledgment. For certain binders, specific acknowledgment modes and ack APIs can be configured, but always follow the binder documentation. PollableMessageSource does not create a uniform ack mechanism across every broker.

## 10. Monitoring Polling Schedules and Lifecycle

A production poller needs metrics to show whether it is active, waiting, or failing. Track:

| Metric/Log | Purpose |
|---|---|
| Poll count | Confirm the reading loop is still running |
| Non-empty poll count | Measure incoming data activity |
| Empty poll count | Understand load and tune idle delay |
| Single poll duration | Detect slow handlers or broker latency |
| Error count and backoff duration | Detect broker/service instability |
| Succeeded/failed message counts | Track business outcomes |
| In-flight message count at shutdown | Evaluate draining and timeouts |
| Consumer lag/queue depth/backlog | Assess ability to keep up with incoming data |

Logs should include event ID, correlation ID, and binding name when metadata is available. Avoid logging full payloads containing sensitive data. Metrics should separate broker errors, conversion errors, and business errors when possible so operations knows where to intervene.

## 11. Testing Poll Schedules and Shutdown

Testing can be divided into multiple layers:

1. **Handler unit tests**: test valid payloads, business errors, and idempotency.
2. **Poller unit tests**: mock `PollableMessageSource` to verify timeouts, `true/false` outcomes, backoff, and that no new polls are scheduled after stopping.
3. **Lifecycle tests**: start the context, verify the poller runs; close the context and verify the executor stops within bounds.
4. **Broker integration tests**: send messages, pause the consumer, send more messages, and restart with the same group to verify backlog and redelivery.
5. **Failure tests**: make the handler throw exceptions, disconnect the broker, or slow down downstream services to verify retries, timeouts, and shutdown.
6. **Load tests**: increase message emission rate to evaluate queuing, concurrency, processing duration, and catch-up capacity.

The Test Binder is useful for verifying wiring and in-memory message logic, but does not fully simulate durability, offsets, acknowledgments, redelivery, or shutdown behavior of a real broker. Those properties require integration tests with Kafka, RabbitMQ, or Pulsar respectively.

## 12. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Polling in a loop without timeout or delay | Busy loop, CPU spikes when queue is empty | Use poll timeout, idle delay, or a scheduler |
| Running an infinite loop inside ApplicationRunner | Blocks startup completion and complicates lifecycle management | Use a background component with an explicit lifecycle |
| Creating a new executor on every poll | Thread leaks and unbounded resource usage | Use an executor managed by the component lifecycle |
| Allowing unintended concurrent polls | Competing reads, hard-to-control ordering and acks | Use a single-threaded scheduler or coordination lock |
| Catching exceptions and ignoring them | Messages may be treated as processed successfully | Let errors propagate to binder/error handling |
| Stopping immediately via interrupt | Handlers or blocking libraries may be cut off mid-flight | Stop accepting new work, await current task, set timeout |
| Offloading to worker and returning immediately | Ack may happen before business logic completes | Wait for results or design a stateful handoff |
| Omitting idempotency | Redelivered messages can cause duplicate updates | Use event IDs and transactions/unique constraints |

## 13. Implementation Checklist

- Use `PollableMessageSource` when the application needs to proactively decide when to fetch messages and the binder supports this model.
- Configure poll timeout, idle delay, and error backoff separately.
- Run the poller on a managed thread/executor without blocking startup or request threads.
- Ensure polls do not overlap if the design requires sequential processing.
- Keep the handler synchronous until the processing outcome is determined, or design a handoff with explicit ack control.
- Let exceptions flow through configured retry/error-handling mechanisms.
- Set timeouts on blocking operations and bound shutdown duration.
- Stop scheduling new polls first, then wait for in-flight handlers to finish.
- Design idempotency to withstand redelivery.
- Monitor poll rate, errors, processing time, backlog, and consumer lag.
- Test pause, restart, handler failures, and shutdown against a real broker.

## 14. References

- [Spring Cloud Stream Reference — Pollable Message Source](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-pollable-consumers.html), section on pollable consumers and `PollableMessageSource`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), section on background task management and schedulers.
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html), start/stop lifecycle and shutdown callbacks.

Managing a proactive consumer requires the application to control poll schedules, execution threads, and shutdown. Use timeouts to prevent busy loops, a single-threaded executor to prevent overlapping polls, backoff on errors, and lifecycle hooks for controlled shutdown. Most importantly, consider a message complete only after the handler finishes according to the binder's semantics; idempotent design and testing with a real broker allow the system to recover safely from pauses, restarts, or sudden failures.
