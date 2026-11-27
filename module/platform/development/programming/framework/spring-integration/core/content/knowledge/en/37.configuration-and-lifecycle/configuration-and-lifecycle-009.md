# TaskScheduler in Spring Integration

In the **SPRING_INTEGRATION_CORE** module, `TaskScheduler` is the infrastructure component that enables endpoints to perform work on a schedule. Understanding this component helps you design message flows with an appropriate processing cadence, prevent a slow handler from stalling other flows, and manage application startup and shutdown.

This lesson belongs to the **Configuration and Lifecycle** chapter and focuses on the relationship between scheduler, poller, channel, and endpoint. The examples use Java 17+, the Spring Integration 6.5 API, and Spring Framework 6.2; library versions should be managed consistently via a BOM or an appropriate Spring Boot version. This is the scope of the examples, not a claim about the version present in a specific project.

After this lesson, you will be able to:

- Identify which endpoints require scheduling and which operate event-driven.
- Distinguish `TaskScheduler`, `Trigger`, poller, and `TaskExecutor`.
- Configure a shared scheduler and an executor for a poller using Java DSL.
- Choose fixed delay, fixed rate, or cron according to processing requirements.
- Observe thread starvation, handle asynchronous errors, and control endpoint lifecycle.

## 1. What Problem Does TaskScheduler Solve?

Suppose an application receives orders into a `QueueChannel`. Sending a message to the channel only places the message into the queue. A consumer is needed to actively pull messages out and pass them to a handler.

With a standard polling endpoint, that process has three parts:

1. `Trigger` determines the next execution time.
2. `TaskScheduler` schedules task execution at that time.
3. The polling endpoint performs the message receive operation and invokes the handler.

The scheduler does not understand orders, routing rules, or how to transform payloads. Those responsibilities belong to the components of the integration flow.

| Component | Responsibility | Example in the Order Flow |
| --- | --- | --- |
| `Message` | Carries payload and headers | An order with a correlation ID |
| `MessageChannel` | Connects producers to consumers | `QueueChannel` holding pending orders |
| `Trigger` | Computes the next execution time | After each completion, wait 500 ms |
| `TaskScheduler` | Schedules and triggers tasks | Wakes up the polling task |
| Polling endpoint | Coordinates receiving and processing | Pulls up to 5 messages per poll |
| `TaskExecutor` | Executes assigned tasks | Runs polling tasks on a dedicated pool |
| Handler | Executes business logic | Checks quantity and accepts the order |

`TaskScheduler` belongs to Spring Framework. Spring Integration uses this abstraction in the infrastructure of endpoints that require scheduling. Basic APIs include one-shot scheduling, `Trigger`-based scheduling, fixed rate, and fixed delay; the return value is typically a `ScheduledFuture<?>` for tracking or canceling the task. See [TaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html).

## 2. Which Endpoints Need a Scheduler?

### 2.1. Consumer Pulling Messages from a PollableChannel

A service activator reading from a `QueueChannel` needs a polling endpoint because the channel does not push messages directly to the handler.

~~~text
Producer -> QueueChannel -> PollingConsumer -> Handler
                                  ^
                                  |
                         TaskScheduler + Trigger
~~~

When configuring a handler on a pollable channel, provide either an explicit poller configuration or an appropriate default poller.

### 2.2. Inbound Adapter Polling a Data Source

A data source may not emit events on its own. For example, the application must periodically call a `MessageSource` to look for new data. `SourcePollingChannelAdapter` handles invoking the source and sending results to the output channel.

~~~text
TaskScheduler -> SourcePollingChannelAdapter -> MessageSource.receive()
                              |
                              v
                        Output channel
~~~

If the source returns `null`, that poll produces no output message. The polling cycle can continue on the next trigger.

### 2.3. Consumer Receiving Events via a SubscribableChannel

With a `DirectChannel`, the handler is invoked synchronously when a message arrives. That endpoint does not need a poller just to receive messages.

With an `ExecutorChannel`, dispatching uses the channel's executor; this also does not turn the channel into a queue needing a poller.

The difference lies in how the endpoint receives messages, not whether the handler is a transformer, filter, router, or service activator. The same kind of handler can sit behind different channel types. See [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html) and [Message Endpoints](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html).

## 3. Thread Boundaries: Understand Before Tuning Pool Size

### 3.1. Poller Without a Dedicated Executor

`ThreadPoolTaskScheduler` executes tasks using the scheduler threads themselves. It does not automatically offload work to another business pool.

~~~mermaid
sequenceDiagram
    participant S as Scheduler thread
    participant Q as QueueChannel
    participant H as Handler
    S->>Q: receive(timeout)
    Q-->>S: Message
    S->>H: handleMessage(message)
    Note over S,H: Scheduler thread runs the handler too
    H-->>S: Complete
~~~

If the handler calls a service taking three seconds, the scheduler thread can be held for those entire three seconds. If subsequent steps are connected via `DirectChannel`, they continue running on the current thread until hitting an asynchronous boundary.

Therefore, a synchronous chain of transformer, router, and service activator can occupy the same scheduler thread. Looking only at the execution time of the first handler underestimates the thread occupancy of the entire chain.

### 3.2. Poller With a taskExecutor

When a poller is configured with a `taskExecutor`, the scheduler hands the polling task off to the executor. This task encompasses receiving and processing messages per the poller configuration, not just a single handler call statement.

~~~mermaid
sequenceDiagram
    participant S as Scheduler thread
    participant E as Poll executor
    participant Q as QueueChannel
    participant H as Handler
    S->>E: submit polling task
    Note over S: Can serve other schedules
    E->>Q: receive(timeout)
    Q-->>E: Message
    E->>H: handleMessage(message)
    H-->>E: Complete
~~~

A dedicated executor isolates slow work, but introduces task queueing and concurrent execution. You must design pool size, executor queue capacity, and behavior when the executor is full.

Note a special case: if `CallerRunsPolicy` is used, the thread submitting the task may have to run the task itself when the executor is saturated. In that situation, the work falls back onto the scheduler thread.

Execution behavior on scheduler threads is described in [ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html); the [PollerSpec.taskExecutor](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html) API specifies the executor running the polling task.

## 4. Default Scheduler and Critical Bean Name

Spring Integration looks up the central scheduler by the bean name `taskScheduler`, corresponding to the constant `IntegrationContextUtils.TASK_SCHEDULER_BEAN_NAME`.

If supplying a custom scheduler, declare this bean name explicitly. Merely putting `@Primary` on a bean with a different name is no substitute for satisfying the infrastructure name Spring Integration uses.

Distinguish two default values:

| Case | Default Pool Size |
| --- | --- |
| Manually constructing `new ThreadPoolTaskScheduler()` without setting pool size | 1 thread |
| Default scheduler provided by Spring Integration infrastructure, per standard 6.5 configuration | 10 threads |

The second value can be changed via the global property `spring.integration.taskScheduler.poolSize`. This property controls Spring Integration's default scheduler; it does not automatically override `setPoolSize(...)` on a scheduler you declare yourself. Refer to [scheduler configuration](https://docs.spring.io/spring-integration/reference/6.5/configuration/namespace-taskscheduler.html) and [Global Properties](https://docs.spring.io/spring-integration/reference/6.5/configuration/global-properties.html).

In a Spring Boot environment, Boot also has its own scheduling configuration. When diagnosing, identify the actual bean in use rather than assuming every scheduling-related property affects the same pool.

`@EnableIntegration` enables Spring Integration infrastructure in this lesson's plain Java examples. `@EnableScheduling` serves the processing of `@Scheduled` methods; you do not need to add that annotation just to make a Spring Integration poller work.

## 5. Choosing Fixed Delay, Fixed Rate, or Cron

### 5.1. Fixed Delay: Rest Interval After Task Completion

~~~java
Pollers.fixedDelay(Duration.ofMillis(500))
~~~

With synchronous polling, suppose one poll takes 300 ms:

~~~text
0 ms       300 ms             800 ms      1100 ms
|--- run ---|--- wait 500 ms ---|--- run ---|
~~~

The interval between two starts is roughly 800 ms. Fixed delay suits cases where you want a pause between polls and processing duration is variable.

### 5.2. Fixed Rate: Anchoring Start Marks Periodically

~~~java
Pollers.fixedRate(Duration.ofSeconds(1))
~~~

Target timestamps are `t0`, `t0 + 1s`, `t0 + 2s`, ... If a task runs slowly or threads are scarce, actual start times may lag behind these marks.

Fixed rate does not create extra processing capacity. Nor does it implicitly turn a synchronous task into multiple concurrent runs. For a synchronous repeating schedule on `ThreadPoolTaskScheduler`, increasing pool size does not cause that same task to overlap itself.

Fixed delay and fixed rate are distinguished by completion time vs. expected start time in [PeriodicTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/PeriodicTrigger.html).

### 5.3. When Using an Executor, Completion Time Must Be Reinterpreted

If the runnable executed by the scheduler merely submits a polling task to an executor and returns, the scheduler may consider that trigger complete before the handler finishes business logic.

Example:

- Fixed delay is 500 ms.
- The handler takes three seconds.
- The scheduler hands the task off to the executor almost immediately.
- Subsequent polling tasks can continue to be submitted while the previous task is still running or sitting in the executor queue.

Therefore, do not use fixed delay as proof that business executions cannot overlap once an executor is added. If strictly one task may execute at a time, design explicit concurrency and backlog limits; if running multiple instances, cross-instance coordination is also needed.

### 5.4. Cron: Tied to Wall-Clock Schedules

~~~java
Pollers.cron(
        "0 */5 * * * *",
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
~~~

This example requests polling at second 0, every five minutes, in the Vietnam time zone. The Spring cron expression here has six fields, starting with seconds.

Cron fits business schedules such as scanning data by minute or running within specific hours. It does not guarantee real-time precision, nor does it provide durable schedule storage or full catch-up for missed triggers while the process was down.

Java DSL overloads for `Duration`, initial delay, and cron with `TimeZone` are listed in [Pollers](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

## 6. Complete Configuration Example in Java DSL

The following example has the flow:

~~~text
pendingOrders
    -> polling endpoint with dedicated executor
    -> validate order quantity
    -> acceptedOrders

Polling or processing errors
    -> pollingErrors
    -> log
~~~

Both queue channels have bounded capacity. The order-receiving endpoint is set to `autoStartup(false)` so the lifecycle demonstration can call `start()` explicitly.

The application requires `org.springframework.integration:spring-integration-core` along with compatible Spring dependencies. The imports below use that library's API, not the standalone Java DSL library from older versions.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.MessagePublishingErrorHandler;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderPollingConfiguration {

    private static final System.Logger LOG =
            System.getLogger(OrderPollingConfiguration.class.getName());

    public record Order(String id, int quantity) {
    }

    @Bean
    public QueueChannel pendingOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public PublishSubscribeChannel pollingErrors() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setRequireSubscribers(true);
        return channel;
    }

    @Bean
    public MessagePublishingErrorHandler pollingErrorHandler(
            @Qualifier("pollingErrors")
            PublishSubscribeChannel errors) {

        MessagePublishingErrorHandler handler =
                new MessagePublishingErrorHandler();
        handler.setDefaultErrorChannel(errors);
        handler.setSendTimeout(1_000);
        return handler;
    }

    @Bean(name = "taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler(
            @Qualifier("pollingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {

        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setErrorHandler(errorHandler);
        scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
        scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }

    @Bean
    public ThreadPoolTaskExecutor orderPollExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("order-poll-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public IntegrationFlow orderPollingFlow(
            @Qualifier("pendingOrders") QueueChannel pending,
            @Qualifier("acceptedOrders") QueueChannel accepted,
            @Qualifier("orderPollExecutor")
            ThreadPoolTaskExecutor executor,
            @Qualifier("pollingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {

        return IntegrationFlow.from(pending)
                .handle(Order.class, (order, headers) -> {
                    if (order.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "Quantity must be greater than 0: " + order.id());
                    }

                    LOG.log(System.Logger.Level.INFO,
                            "Processing " + order.id() + " on "
                                    + Thread.currentThread().getName());
                    return "ACCEPTED:" + order.id();
                }, endpoint -> endpoint
                        .id("orderPollingEndpoint")
                        .autoStartup(false)
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(5)
                                .receiveTimeout(0)
                                .taskExecutor(executor)
                                .errorHandler(errorHandler)))
                .channel(accepted)
                .get();
    }

    @Bean
    public IntegrationFlow pollingErrorFlow(
            @Qualifier("pollingErrors")
            PublishSubscribeChannel errors) {

        return IntegrationFlow.from(errors)
                .handle(message -> {
                    Throwable failure =
                            (Throwable) message.getPayload();
                    LOG.log(System.Logger.Level.ERROR,
                            "Order polling or processing failed",
                            failure);
                })
                .get();
    }
}
~~~

### 6.1. Why Configure It This Way?

- `taskScheduler` matches the exact bean name of Spring Integration's central scheduler.
- The scheduler pool has two threads; polling tasks for the order flow are handed off to `orderPollExecutor`.
- `receiveTimeout(0)` lets the task return immediately if the channel is empty.
- `maxMessagesPerPoll(5)` caps the number of messages processed in one polling task.
- The executor has a bounded queue, exposing overload early rather than growing an unbounded backlog.
- The error handler is wired to both the scheduler and the poller to clearly illustrate both places where errors can arise.
- The scheduler and executor are managed by Spring as beans; there is no need to call `initialize()` manually inside `@Bean` methods.

The values 2, 4, 20, 100, and 500 ms are illustrative figures. Tune them based on processing time, order volume, and downstream limits.

`acceptedOrders` can also fill up if no consumer receives results. Then sending the output can cause the polling task to block or fail per send timeout. In a real application, connect an output consumer and set appropriate timeouts.

### 6.2. Limitations of the Example

The default in-memory `QueueChannel` does not provide message recovery after the process stops. Using a scheduler or executor does not add data durability on its own.

The error flow currently only logs. If orders must not be lost after processing fails, the application must design error persistence, retry, or routing to a place capable of reprocessing. Do not treat having logs as having a recovery mechanism.

## 7. Starting and Stopping the Right Endpoint

The class below runs directly with the configuration above. Spring Boot is not needed to observe the behavior.

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderPollingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderPollingConfiguration.class)) {

            QueueChannel pending =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);
            Lifecycle endpoint =
                    context.getBean("orderPollingEndpoint", Lifecycle.class);

            Message<?> request = MessageBuilder.withPayload(
                    new OrderPollingConfiguration.Order("ORD-101", 2))
                    .build();

            if (!pending.send(request, 1_000)) {
                throw new IllegalStateException("Input queue is full");
            }

            // Endpoint has autoStartup(false), not receiving orders yet.
            if (accepted.receive(0) != null) {
                throw new IllegalStateException("Unexpected result received");
            }

            endpoint.start();
            try {
                Message<?> reply = accepted.receive(3_000);

                if (reply == null
                        || !"ACCEPTED:ORD-101".equals(reply.getPayload())) {
                    throw new IllegalStateException("Did not receive expected result");
                }

                System.out.println(reply.getPayload());
            }
            finally {
                endpoint.stop();
            }
        }
    }
}
~~~

You can observe three points:

1. The message stays waiting while the endpoint is not running.
2. After `start()`, processing logs show the `order-poll-` thread prefix.
3. `stop()` halts the endpoint's polling schedule; closing the context handles cleaning up infrastructure beans.

Do not use `taskScheduler.stop()` as a routine operation to pause a single flow. A shared scheduler may serve multiple endpoints or other timed tasks. Controlling the right endpoint makes the scope of impact predictable.

Stopping an endpoint does not mean every task already submitted to an executor has finished or been canceled. When you need to confirm work has ended, observe execution state and business outcomes, not only `endpoint.isRunning()`.

## 8. Tuning a Poller as a Bounded System

### 8.1. receiveTimeout and Thread Occupancy

`receiveTimeout` is the wait time for pulling a message from a pollable channel, specified in milliseconds in `PollerSpec` configuration. It is not the timeout for HTTP, JDBC, or the entire processing chain.

If many pollers wait simultaneously on empty channels, the number of held threads can be large even when CPU is nearly idle. Lowering receive timeout or moving polling tasks to an appropriate executor reduces impact on the scheduler.

Setting timeout to 0 alongside a very short period can create many empty checks. Balance desired latency against polling cost.

### 8.2. maxMessagesPerPoll Is Not Concurrency

A value of 5 means one polling task can process at most five messages, stopping sooner when no message is received. It does not spawn five threads and does not guarantee five messages are always present in that poll.

Inside a typical polling task, messages are processed sequentially. Multiple distinct polling tasks can run concurrently when you configure an executor.

If each message takes 200 ms, a poll with all five messages can hold a thread for about one second, excluding receive and send time. Setting this limit too high can let one endpoint occupy resources longer than intended.

### 8.3. There Are Two Different Queues

~~~text
QueueChannel:
    holds Messages not yet received by a polling task.

Executor queue:
    holds polling task Runnables already submitted by the scheduler,
    but not yet executed by an executor thread.
~~~

A long executor queue may contain many unstarted polls, even after the source channel has run out of messages. When those polls run, they may just check an empty channel and exit.

Conversely, a short executor queue does not prove message backlog is low. Many messages may still be sitting inside `QueueChannel`.

Therefore, measure channel depth and pending tasks in the executor separately.

### 8.4. Message Ordering and Transactions

When multiple polling tasks run concurrently, completion order does not necessarily match the order messages were pulled from the queue. Order B may finish before order A if A calls a slower downstream service.

If business logic requires ordering per customer or account, design partitioning, one consumer per group, or a corresponding serialization mechanism.

Thread-bound transactions must also be considered when adding an asynchronous boundary. A transaction on the producer does not automatically follow the message onto an executor thread. If a transaction is needed at the polling endpoint, configure transactions in the right place and verify transactional capability of the data source or message store.

## 9. Error Handling: Error Messages and Scheduling Errors

Three groups can be distinguished for diagnostics:

| Where the Error Occurs | Example | What to Check |
| --- | --- | --- |
| Receiving or processing a message | Data source failure, handler throws exception | Poller's error handler and error flow |
| Submitting a task | Executor full or already shut down | Rejection policy, error handler, and infrastructure logs |
| Sending the error message | Error channel has no subscribers or consumer fails | Intake capacity and reliability of the error flow |

In asynchronous processing, the producer may have already sent the message successfully and moved on before the handler fails. The producer cannot catch that error with a `try/catch` block around the initial send call as in a synchronous call chain.

`MessagePublishingErrorHandler` converts errors into an `ErrorMessage`. When an error has an associated message context, the message's `errorChannel` header can take precedence; otherwise, the error handler uses its configured default channel. In the example, the default channel is `pollingErrors` instead of the global `errorChannel`.

You can try an order `new Order("ORD-BAD", 0)`: an error log appears and no `ACCEPTED:ORD-BAD` result is produced. This does not automatically requeue the order into `pendingOrders`.

Some infrastructure errors occur before a message is received, so not every `ErrorMessage` has an original order to retry. Error-handling code must inspect the context rather than assuming `failedMessage` is always present.

Error routing is described in [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html); methods for configuring the default channel are in [MessagePublishingErrorHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html).

With a `PublishSubscribeChannel` lacking an executor as in the example, the downstream error handler runs synchronously on the thread publishing the error. Do not let it make a network call without a timeout; if the error flow hangs, the thread processing the error is blocked as well.

## 10. Lifecycle and Controlled Shutdown

### 10.1. Distinguishing Control Scopes

| Action | Scope |
| --- | --- |
| `endpoint.start()` or `endpoint.stop()` | One specific endpoint |
| Controlling the shared scheduler | Tasks depending on that scheduler |
| Shutting down the executor | Task acceptance and execution capability of the executor |
| Closing `ApplicationContext` | Lifecycle and destruction of beans managed by the context |

With `SmartLifecycle`, lower phases generally start first; during stop, phase order runs in reverse. Bean dependencies and executor shutdown behavior also affect the actual sequence. Setting phases is only one part of shutdown design.

### 10.2. Meaning of Options in the Example

- `setRemoveOnCancelPolicy(true)`: helps remove canceled tasks from the scheduler queue, useful when many schedules are created and canceled.
- `setContinueExistingPeriodicTasksAfterShutdownPolicy(false)`: does not continue repeating schedules after scheduler shutdown.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(false)`: does not continue executing unrun delayed tasks after shutdown.
- `setWaitForTasksToCompleteOnShutdown(true)`: requests shutdown to allow existing work to finish per the corresponding policy.
- `setAwaitTerminationSeconds(10)`: bounds how long shutdown blocks waiting for the executor to terminate at the relevant shutdown step.

The ten-second wait is not a forced timeout for individual handlers. Reaching that limit also does not mean Java has forcibly stopped a hung I/O operation. HTTP clients, JDBC, and external connections still need their own timeouts.

Wait options also affect how the executor participates in context closing; verify the exact version in [ExecutorConfigurationSupport](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html).

### 10.3. Business Sequence to Achieve

For a system required to finish work before shutting down, design so that:

1. New work intake or generation stops.
2. Additional polls stop being created at a point aligned with the backlog handling strategy.
3. Already-accepted tasks are allowed to finish within a time limit.
4. Required downstream resources stay available until those tasks finish.
5. Remaining work is persisted or handed off per the chosen recovery mechanism.

Calling `stop()` on an endpoint alone does not drain messages from channels. If the goal is to drain the queue before shutting down, a dedicated drain procedure is needed before stopping consumers, along with a time limit and handling for leftovers.

## 11. Choosing Pool Size Based on Load

An initial estimate for the number of threads executing blocking work is:

~~~text
Average concurrent tasks ≈
    task arrival rate per second × duration per task in seconds
~~~

This is a steady-state average load estimate, not an automatic formula for pool size.

For example, 40 messages/second with an average processing time of 0.2 seconds needs about eight concurrent executions just to keep up with average load. However, a synchronous poller running only one poll at a time will not achieve eight concurrent messages merely because the scheduler has eight threads.

Distinguish actual execution concurrency from the number of available threads. In a design using an executor for polling, task submission cadence, messages per poll, and duration per poll jointly determine concurrency.

Beyond averages, inspect:

- p95/p99 processing times and traffic bursts.
- Database or HTTP client connection pool limits.
- Connections and concurrency permitted by downstream systems.
- Ordering or per-business-key concurrency requirements.
- Queue capacity and maximum acceptable latency.

Increasing a pool from 4 to 40 can overload downstream systems if only eight connections are available. Thread count rises without a corresponding increase in throughput.

## 12. Observability and Incident Diagnostics

Giving distinct thread name prefixes to the scheduler and executor makes logs and thread dumps easier to read. In the example, slow work appears on `order-poll-` rather than repeatedly holding `si-scheduler-`.

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| Multiple pollers lag together, low CPU | Scheduler threads waiting on I/O or message receive | Inspect thread dumps, timeouts, and dedicated executor |
| `QueueChannel` grows steadily | Processing rate lower than arrival rate | Measure processing time, concurrency, and downstream health |
| Executor queue grows, channel has little data | Submitting polls faster than execution capacity | Reduce polling cadence, bound backlog, check receive timeout |
| `TaskRejectedException` appears | Executor full or shutting down | Check pool, queue, rejection policy, and lifecycle |
| Handler still runs after endpoint stops | Previously submitted task has not finished | Track in-flight work and design drain procedure |
| Cron runs at wrong business hour | Incorrectly configured time zone | Specify timezone and check system clock |
| Results finish out of order | Multiple tasks processing concurrently | Design serialization according to business requirements |

Useful metrics include time from scheduled mark to task start, duration per polling task, messages per poll, active count, queue depth, and error or rejection counts.

Do not assume all these metrics are exported automatically. Some require adding instrumentation at the endpoint, executor, or appropriate monitoring layer.

## 13. Verifying Behavior in Practice

To verify the example without relying on an arbitrary `Thread.sleep`, write a JUnit 5 test using a message receive timeout. The test below verifies starting the endpoint explicitly and observing the outcome.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderPollingConfigurationTest {

    @Test
    void processesOrderAfterEndpointStarts() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderPollingConfiguration.class)) {

            QueueChannel pending =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);
            Lifecycle endpoint =
                    context.getBean("orderPollingEndpoint", Lifecycle.class);

            assertFalse(endpoint.isRunning());
            assertTrue(pending.send(MessageBuilder.withPayload(
                    new OrderPollingConfiguration.Order("ORD-TEST", 3))
                    .build(), 1_000));
            assertNull(accepted.receive(0));

            endpoint.start();
            try {
                Message<?> result = accepted.receive(3_000);

                assertNotNull(result);
                assertEquals("ACCEPTED:ORD-TEST", result.getPayload());
            }
            finally {
                endpoint.stop();
            }
        }
    }
}
~~~

The three-second timeout is a wait bound so the test does not hang indefinitely, not a requirement that the scheduler be accurate to the millisecond. If your CI environment has heavy load, set bounds fitting your test budget.

When extending verification, use latches, a result channel, or bounded await utilities to observe errors and running tasks. To verify that stopping prevents receiving additional orders, also account for tasks already submitted to the executor; do not infer from a single instantaneous empty receive.

If you need to test a transformer or business rule in isolation, call and test that unit directly. Schedule tests should only cover scheduling-dependent behavior so timing jitter does not obscure simple business checks.

## 14. Design Principles to Keep in Mind

A flow using `TaskScheduler` is easy to operate when you can clearly answer four questions: what determines when it runs, which thread receives messages, which thread executes business logic, and where errors go.

From there, pick polling cadence based on target latency; use a bounded executor if work needs isolation; measure message backlog and task backlog separately; and control lifecycle on the right endpoint. When adding transformers, filters, routers, or aggregators downstream, continue checking thread boundaries and resource occupancy across the whole chain.

The scheduler provides time-based coordination. Message durability, error recovery, ordering, and multi-instance coordination must be designed alongside the corresponding channels, endpoints, and integration infrastructure.
