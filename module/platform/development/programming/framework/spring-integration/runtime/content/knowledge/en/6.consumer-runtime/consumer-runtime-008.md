# Poller Task Executors and Concurrent Polling

In Spring Integration, a poller decides when a polling endpoint retrieves messages from a source. When a flow needs to handle many messages or a single poll can take significant time, you often consider attaching a `TaskExecutor` to the poller so polls execute on worker threads. This configuration can increase throughput, but it can also cause polls to overlap, alter processing order, and put pressure on databases, brokers, or downstream services.

To choose the right configuration, separate three concepts: `TaskScheduler` schedules when polls fire, `TaskExecutor` executes the polling work, and `maxMessagesPerPoll` bounds how many messages are fetched in a single poll. They govern three distinct aspects and cannot substitute for one another.

## 1. Where Does the Poller Fit in the Consumer Runtime?

Spring Integration has two common types of polling endpoints:

- `SourcePollingChannelAdapter` actively calls `MessageSource.receive()` to pull messages from an external source and send them to a channel.
- `PollingConsumer` retrieves messages from a `PollableChannel`, such as `QueueChannel`, and passes them to a handler for processing.

Both use a poller to trigger message retrieval on a schedule. They differ in where messages come from: one reads from a `MessageSource`, while the other receives from a pollable channel.

High-level processing flow:

~~~mermaid
flowchart LR
    T[TaskScheduler] -->|Poll time arrives| P[Polling task]
    P -->|Submit work| X[TaskExecutor]
    X --> W[Worker thread]
    W --> R[Receive message]
    R --> H[Message handler]
    H --> C[Output channel / reply]
~~~

When no dedicated executor is configured for the poller, the polling task may run directly on the scheduling thread. When a `TaskExecutor` is configured, the poller hands the polling work off to the executor. A worker thread performs the message receive and any subsequent synchronous processing in the endpoint.

If the downstream channel is a `DirectChannel`, the next handler usually runs on the same worker thread. If the flow transitions to an `ExecutorChannel`, another asynchronous boundary is introduced and downstream work can run on a different pool. Map out thread boundaries clearly before increasing pool counts.

## 2. Distinguishing TaskScheduler and TaskExecutor

The two abstractions serve different purposes:

| Component | Responsibility | Question Answered |
|---|---|---|
| `TaskScheduler` | Schedules when polls trigger using fixed delay, fixed rate, or cron | When is the next poll triggered? |
| `TaskExecutor` | Runs the polling task on an execution thread | Which thread executes this poll? |
| `maxMessagesPerPoll` | Limits how many messages are processed in a single poll | How many messages can one poll fetch? |

For example, a poller can be triggered every 500 ms by the scheduler, submit tasks to an executor with 4 workers, and process at most 10 messages per poll. These three numbers respectively describe trigger cadence, parallel execution capacity, and messages per run.

Do not think of `TaskExecutor` as a timer. An executor does not decide cron or fixed delay; it simply runs tasks once triggered. Similarly, increasing `maxMessagesPerPoll` does not create additional worker threads.

## 3. Configuring Fixed Delay and TaskExecutor

The example below creates a `QueueChannel` and a polling consumer fetching up to 10 messages per poll. The poller fires on a fixed delay and executes on a dedicated pool:

~~~java
@Configuration
@EnableIntegration
public class OrderPollingConfiguration {

    @Bean
    QueueChannel ordersQueue() {
        return new QueueChannel(1_000);
    }

    @Bean
    ThreadPoolTaskExecutor orderPollerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-poller-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean
    IntegrationFlow orderPollingFlow(
            QueueChannel ordersQueue,
            TaskExecutor orderPollerExecutor,
            OrderService orderService) {

        return IntegrationFlow.from(ordersQueue, endpoint -> endpoint
                        .poller(Pollers.fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(10)
                                .taskExecutor(orderPollerExecutor)))
                .handle(orderService, "process")
                .get();
    }
}
~~~

Relevant imports in the example:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
~~~

`ThreadPoolTaskExecutor` is managed by Spring as a bean and follows bean lifecycle initialization. `corePoolSize` is the core worker count, `maxPoolSize` is the maximum worker cap, and `queueCapacity` is how many tasks can wait in the executor's queue. With `ThreadPoolExecutor`, tasks are normally queued once core threads are busy; the pool only grows past core size when the queue is full and count is below `maxPoolSize`. Therefore, `maxPoolSize=8` does not mean the application immediately runs 8 polls in parallel.

The example uses a bounded queue capacity to cap pending tasks. When the queue is full and the pool reaches its cap, the executor may reject tasks according to its rejection policy. Monitor rejected task counts and pick an appropriate policy; do not use an unbounded queue to hide the fact that the poller submits tasks faster than workers can process them.

## 4. Fixed Delay, Fixed Rate, and Cron

A poller can be triggered using different scheduling strategies:

| Trigger Type | Meaning | When Appropriate |
|---|---|---|
| Fixed delay | Schedules the next run after a delay measured from the previous scheduled execution | Periodic work prioritizing a pause between triggers |
| Fixed rate | Triggers on a steady time cadence | Need consistent clock-based polling cadence |
| Cron | Triggers according to a calendar expression | Hourly, daily, or business-schedule synchronization |

DSL examples:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(1));
Pollers.fixedRate(Duration.ofSeconds(1));
Pollers.cron("0 */5 * * * *");
~~~

Note when using a `TaskExecutor`: the scheduler can finish its dispatch step as soon as it submits the polling task to the executor, while the worker is still processing messages. Consequently, the fixed delay between trigger firings is not necessarily a pause after all previous message processing completes. If a worker runs longer than the trigger interval, a new task can be submitted while the earlier task is still running. This is one source of concurrent polling.

If the requirement is that two polls never run concurrently, you must ensure the previous poll completes before the next one may start—for example, using a single-worker executor with appropriate queueing or an explicit locking/coordination mechanism. Do not infer sequential execution merely from using `fixedDelay`.

## 5. maxMessagesPerPoll and Concurrent Polling

`maxMessagesPerPoll` bounds how many messages a single polling task retrieves in one run. Positive values set an explicit cap; `-1` indicates continuing to receive messages until the source has none left. Defaults can vary by polling endpoint type, so configure it explicitly when this behavior matters.

For example, with `maxMessagesPerPoll(10)`, one worker can receive up to 10 messages in a single poll. If the executor has multiple workers and the scheduler fires multiple runs while earlier workers are still busy, multiple poll runs can be active simultaneously. In that case, the total number of messages in flight can exceed 10.

Distinguish two ways of scaling load:

- **Increasing batch size:** raising `maxMessagesPerPoll` so one polling task processes more messages before finishing.
- **Increasing concurrency:** allowing multiple polling tasks to run concurrently across multiple workers.

The two approaches have different consequences. Larger batches can reduce scheduling overhead, but hold workers longer and include more messages in one transaction if a transaction wraps the poll. Higher concurrency can raise throughput when headroom exists, but increases in-flight message count, concurrent database connections, and contention on shared resources.

With `maxMessagesPerPoll(-1)`, a source that continuously has messages can keep a single poll running for a very long time. Without a dedicated executor, the scheduler thread can become monopolized. With an executor, a worker can keep consuming messages while subsequent triggers continue submitting tasks, growing the task queue. Using finite batches bounds how long a worker spends per run and promotes fairer scheduling across workloads.

## 6. Impact of Concurrent Polling on Ordering and Safety

When multiple polling tasks run concurrently, the order in which messages start processing can differ from the order in which they finish. For instance, message A is received first but processes slowly; message B is received later and finishes first. If business rules require ordering by key, simply increasing poller concurrency can break observed ordering.

Before enabling concurrent polling, verify:

1. **Is the `MessageSource` thread-safe?** Custom sources must tolerate multiple threads calling `receive()` concurrently or be protected with proper synchronization.
2. **Is the handler thread-safe?** Do not share unprotected mutable state across executions.
3. **Does business ordering matter?** If ordering per order/customer key is needed, use partitioning, per-key serial executors, or dedicated consumers per partition.
4. **Can downstream resources handle the load?** Database connection pools, HTTP connection pools, and external service rate limits must match the concurrency level.
5. **Can messages be processed twice?** Retries, redeliveries, and transaction rollbacks require idempotent handlers or deduplication mechanisms.

A `QueueChannel` can be polled concurrently by multiple consumers, yet removing messages from the queue does not guarantee processing completion order. With `DirectChannel`, concurrency typically comes from multiple threads sending concurrently; with `ExecutorChannel`, it comes from the downstream executor. Identify the exact point introducing concurrency rather than looking only at the poller.

## 7. Transactions and Advice Under Parallel Polling

A poller can combine an advice chain to apply transactions, retries, logging, or other cross-cutting behaviors around a poll. When concurrency is enabled, each polling task can execute on its own thread, and a transaction is typically created along that task's execution boundary depending on advice and transaction manager configuration.

Several consequences to watch for:

- Transactions do not automatically propagate from the message-sending thread to worker threads. Workers need their own transactions or a supported context-propagation mechanism.
- If a polling task pulls multiple messages in one transaction, an error on one message can affect the commit/rollback outcome of the entire run depending on configuration.
- Multiple concurrent polling tasks can open more transactions and occupy more database connections.
- Retries around the polling task may retry a unit of work larger than a single message, depending on advice placement in the chain.
- With brokers, acknowledgements and transactions must align with the adapter and broker; do not assume a database transaction automatically covers external acknowledgements.

When transactions are required, explicitly define the intended boundary: one transaction per message or per poll batch. Then verify with transaction logs and tests that fail mid-batch. If the business cannot accept rolling back multiple messages together, lower the batch size or move the transaction boundary to individual messages via an appropriate design.

## 8. Backpressure and Resource Limits

Concurrent polling helps only when downstream systems still have capacity to process. If the poller generates work faster than handlers finish, tasks accumulate in the executor queue or messages continue piling up in channels/brokers.

Set limits at multiple layers:

| Layer | Limits to Consider |
|---|---|
| Poller | Trigger interval, `maxMessagesPerPoll`, number of endpoints polling the same source |
| TaskExecutor | Core/max pool size, queue capacity, rejection policy |
| QueueChannel | Capacity, send timeout, and full-queue strategy |
| Database | Connection pool, transaction timeout, and concurrent query limits |
| Remote service | Connection pool, rate limit, timeout, and circuit breaker |
| Broker | Consumer concurrency, prefetch, acknowledgement, and partition ownership |

Do not simultaneously raise pool size, batch size, and endpoint count just because backlog is growing. Identify the bottleneck first: is the poller not fetching fast enough, does the executor lack workers, is the handler slow, is the database out of connections, or is the remote service rate-limiting? Raising concurrency when the bottleneck is downstream can accelerate backlog and error growth.

With a bounded executor queue, rejections serve as a backpressure signal. Decide how rejected tasks should report errors, retry, or slow down the source. Do not ignore exceptions from the executor because messages may fail to process as expected.

## 9. Error Handling and Shutdown

Errors on a worker thread may not propagate back to the thread that originally sent the message. For polling endpoints, configure appropriate error handling and monitor `ErrorMessage`, `errorChannel`, retry count, and logs keyed by message ID/Correlation ID. If a message repeatedly fails, enforce retry caps and a dead-letter/error flow so workers are not blocked indefinitely.

During application shutdown, endpoints normally stop creating new polling tasks per lifecycle. However, tasks already submitted to the executor may still be queued or running. Therefore:

- Block or throttle message sources before shutdown if draining is required.
- Configure the executor policy to wait for active tasks to finish within a bounded time.
- Set a bounded queue capacity and inspect rejected tasks.
- Do not shut down a shared executor when you only intend to stop a single polling endpoint.
- If zero message loss is required, rely on a durable broker/store and properly configured acknowledgements/transactions.

`setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(...)` on `ThreadPoolTaskExecutor` help wait for accepted tasks within a bounded window. This is not an unbounded guarantee: if tasks do not finish before the deadline, the application still handles shutdown according to its chosen policy.

## 10. Measuring and Diagnosing Concurrent Polling

When enabling an executor, set a distinct thread name prefix—such as `orders-poller-`—to distinguish poller logs from other workers. Structured logs should include endpoint/component name, thread name, message ID, Correlation ID, receive timestamp, and processing duration.

Track these metrics:

- Poll count and duration per poll.
- Messages received per poll and empty poll count.
- Active workers, pool size, and executor queue size.
- Rejected task count or wait time in the executor.
- `QueueChannel`/broker backlog and age of the oldest message.
- Throughput, processing latency, error rate, and retry count.
- Database connection usage, lock wait time, and downstream service latency.

Common indicators:

| Symptom | Possible Cause to Check |
|---|---|
| Executor queue grows continuously | Poller dispatches faster than workers process; handler or downstream is the bottleneck |
| Workers always busy, throughput flat | DB/remote service bottleneck, lock contention, or overly large batches |
| Multiple polling tasks overlap | Trigger period shorter than processing time; executor has multiple workers |
| Messages finish out of order | Concurrent polling or downstream executor changes completion order |
| `RejectedExecutionException` | Executor queue is full and pool has reached its cap |
| Low CPU but high backlog | Workers are waiting on I/O, connection pools, or locks |
| Errors rise after increasing pool size | Downstream is overloaded or resource limits are exceeded |

During investigation, compare poll duration, executor queue wait time, and handler processing time. Measuring only end-to-end time from trigger to completion makes it hard to tell whether delays stem from scheduling, task queueing, or business processing.

## 11. Configuration Selection Process

1. **Identify endpoint type.** Is it a `SourcePollingChannelAdapter` or `PollingConsumer`, is the source thread-safe, and does the channel buffer messages?
2. **Measure baseline.** Record throughput, latency, backlog, poll duration, and handler time before enabling concurrency.
3. **Choose batch size.** Set a finite `maxMessagesPerPoll` if poll duration and transaction size need bounds.
4. **Choose trigger cadence.** Use fixed delay, fixed rate, or cron per business needs; avoid overly frequent polling when the source is often empty.
5. **Configure executor.** Start with a small pool, bounded queue, and dedicated thread name prefix; scale only when metrics show workers are the bottleneck.
6. **Verify ordering and idempotency.** Test slow messages, mid-batch failures, retries, and redeliveries.
7. **Set backpressure.** Check capacities across channel, executor, database, and remote services.
8. **Observe post-deployment.** Watch throughput, latency, queue age, rejections, and error rates before increasing load further.

## 12. Poller and TaskExecutor Configuration Checklist

- [ ] Clearly separate the roles of `TaskScheduler` and `TaskExecutor`.
- [ ] Choose fixed delay, fixed rate, or cron based on actual requirements.
- [ ] Set `maxMessagesPerPoll` explicitly; avoid unbounded batches if the source always has messages.
- [ ] Use an executor with bounded pool size and queue capacity.
- [ ] Verify `MessageSource`, handlers, and shared resources are thread-safe.
- [ ] Define ordering requirements by message, tenant, or partition.
- [ ] Check transaction boundaries when one polling task processes multiple messages.
- [ ] Configure error handling, retries, and dead-lettering for failed tasks/messages.
- [ ] Measure backlog, active workers, executor queue, and rejected tasks.
- [ ] Verify shutdown does not lose messages or leave tasks unexpectedly abandoned.

Poller, `TaskScheduler`, `TaskExecutor`, and `maxMessagesPerPoll` govern distinct parts of the consumer runtime. By separating trigger timing, messages per poll, and parallel workers, you can scale throughput safely, protect data sources, and avoid turning backlogs into an unbounded task queue.

## References

- [Spring Integration Reference: Poller](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference: Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API: ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
