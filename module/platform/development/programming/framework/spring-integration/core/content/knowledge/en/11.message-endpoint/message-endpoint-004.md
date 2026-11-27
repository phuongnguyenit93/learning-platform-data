# PollingConsumer

## 1. Objectives and Scope

In the **Message endpoint** chapter of **SPRING_INTEGRATION_CORE**, `PollingConsumer` is the endpoint that actively retrieves messages from a `PollableChannel` and then hands them to a `MessageHandler`. It connects the queue model to processing components such as service activators, transformers, filters, and routers.

After this lesson, you will be able to:

- Distinguish between `PollingConsumer`, `EventDrivenConsumer`, and `SourcePollingChannelAdapter`.
- Build a `Message` flow through a `QueueChannel` to a handler using Java DSL.
- Choose a polling schedule, receive timeout, messages per poll, and concurrency level.
- Explain error handling, transaction boundaries, and risks of message loss or duplicate processing.
- Test asynchronous behavior with explicit wait timeouts.

This lesson focuses on Spring Integration Core. Other storage or messaging systems are mentioned only to clarify durability and transaction boundaries.

## 2. The Problem: Fast Ingestion, Independent Processing Pace

Suppose a gateway accepts orders, but the processing step must call a rate-limited service. If all business logic runs directly on the sending thread, response latency will depend on the downstream service.

You can decouple the two stages using a `QueueChannel`:

```text
Gateway or producer
         |
         | send(Message<Order>)
         v
QueueChannel
         ^
         | receive(timeout)
PollingConsumer
         |
         | handleMessage(message)
         v
Order-processing MessageHandler
```

The producer sends the message to the queue. The receiving endpoint is triggered on a schedule to call `receive(...)`. A successful send to the queue does not mean business processing has finished.

This approach absorbs short load bursts and smooths the processing pace. In return, you must manage queue capacity, latency, post-send errors, and endpoint state.

> An in-memory `QueueChannel` does not inherently provide durability. When the process stops, messages remaining in the queue can be lost.

## 3. Structure of PollingConsumer

### 3.1. Channel, Endpoint, and Handler

| Component | Responsibility | Example |
| --- | --- | --- |
| `PollableChannel` | Allows the receiver to actively pull messages | `QueueChannel`, `PriorityChannel` |
| `PollingConsumer` | Coordinates receiving and invoking the handler | Endpoint of a service activator reading a queue |
| `MessageHandler` | Performs the message-processing step | Transformer, filter, router, service activator |

The core relationship can be expressed as:

```java
PollableChannel inputChannel;
MessageHandler handler;

PollingConsumer endpoint =
        new PollingConsumer(inputChannel, handler);
```

This only illustrates the relationship between types; it is not a standalone runnable configuration. The endpoint also needs a polling schedule, a scheduler, and lifecycle management. In normal applications, let Spring create the endpoint via Java DSL or framework configuration.

### 3.2. A Handler Is Not an Endpoint

A service activator describes the business-processing role; `PollingConsumer` describes how messages are received. The same kind of handler can be wrapped by different endpoints:

- Reading from a `SubscribableChannel`: typically uses `EventDrivenConsumer`.
- Reading from a `PollableChannel`: uses `PollingConsumer` and requires a poller.

Transformers, filters, and routers can also run inside a `PollingConsumer` if that step's own input is a `PollableChannel`.

For an aggregator, the poller only controls receiving messages into the processing step. Grouping and releasing groups still depend on the aggregator's correlation strategy, release strategy, message store, and expiration policies.

### 3.3. A Single Poll Cycle

A poll cycle can be visualized as follows:

1. The trigger determines that it is time to fire.
2. The endpoint starts the poll cycle on the corresponding execution thread.
3. The endpoint calls `receive(receiveTimeout)` on the input channel.
4. If a message is received, the endpoint invokes the handler with that message.
5. If configuration allows, the endpoint continues receiving messages within the same cycle.
6. The cycle ends when the limit is reached, no message is received, or a terminating condition such as an unhandled error occurs.

Advice, transactions, executors, and error handling can add behavior around this process.

## 4. Distinguishing Consumption and Source-Polling Mechanisms

| Criterion | `EventDrivenConsumer` | `PollingConsumer` | `SourcePollingChannelAdapter` |
| --- | --- | --- | --- |
| Input | `SubscribableChannel` | `PollableChannel` | `MessageSource` |
| Trigger | Channel dispatches to subscriber | Endpoint actively pulls from channel | Endpoint actively reads from source |
| Polling config | Not applicable to this receive step | Consumer endpoint's poller | Inbound adapter's poller |
| Example | Service activator reading `DirectChannel` | Service activator reading `QueueChannel` | Adapter reading a directory on a schedule |
| Role | Consumes dispatched messages | Consumes messages already in a channel | Brings messages from a source into the flow |

`PollingConsumer` does not scan directories or query external sources on its own. When an inbound adapter reads a file and sends a message to a queue, reading the file and consuming from the queue are two separate stages.

Asynchronous also does not mean polling. `ExecutorChannel` hands work off via an executor, yet it is still a subscribable channel. With `DirectChannel`, the handler usually runs right on the sending thread; with `QueueChannel`, the producer puts the message into a queue for the receiver to pull later.

## 5. Java DSL: Processing Orders from QueueChannel

### 5.1. Flow Configuration

The example uses `spring-integration-core`, Spring Context, and Java 17 or later to declare `record` types. With Spring Boot, you can use the integration starter and manage versions via the project's dependency set. The snippets below are configuration examples, not a full project with all dependencies and a bootstrap entry point.

```java
import java.math.BigDecimal;

public record Order(String id, BigDecimal amount) {
}
```

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public QueueChannel ordersQueue() {
        return new QueueChannel(200);
    }

    @Bean
    public IntegrationFlow processOrders() {
        return IntegrationFlow
                .from(ordersQueue())
                .handle(Order.class, (order, headers) -> {
                    System.out.println("Processing order " + order.id());
                    // Perform business logic here.
                    return null;
                }, endpoint -> endpoint
                        .id("orderPollingConsumer")
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(500))
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(10)))
                .get();
    }
}
```

Meaning of each part:

- `ordersQueue()` creates a queue with a capacity of 200 messages.
- `.from(ordersQueue())` selects the input channel.
- `.handle(...)` declares the handler processing `Order` payloads.
- `.poller(...)` configures polling on that handler's own endpoint.
- `.id("orderPollingConsumer")` names the endpoint for identification during management or monitoring.
- `receiveTimeout(0)` returns immediately if there is no message in the queue.
- `maxMessagesPerPoll(10)` caps the batch at most 10 messages per poll cycle.
- The handler returns `null` because the flow ends at the order-processing step without producing a reply.

Cross-calling `ordersQueue()` in the class above relies on `@Configuration`'s default proxy behavior. If you use `@Configuration(proxyBeanMethods = false)`, inject the channel bean as a parameter instead of calling the bean-factory method directly.

### 5.2. Sending Messages with a Timeout

```java
import java.math.BigDecimal;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderPublisher {

    private final QueueChannel ordersQueue;

    public OrderPublisher(QueueChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    public void publish() {
        Message<Order> message = MessageBuilder
                .withPayload(new Order("ORD-1001", new BigDecimal("250000")))
                .setHeader("traceId", "trace-1001")
                .build();

        boolean accepted = ordersQueue.send(message, 200);
        if (!accepted) {
            throw new IllegalStateException("Orders queue is full");
        }
    }
}
```

The 200 ms timeout in `send(...)` is the wait time for placing the message into the queue when the queue is full. It is neither a business-processing timeout nor the consumer's `receiveTimeout`.

The `traceId` header travels with the message to the handler. Data stored only in the producer's `ThreadLocal` does not automatically appear on the consumer thread, so tracing information must be propagated via an appropriate mechanism.

### 5.3. Placing the Poller on the Right Step

Consider the flow:

```text
QueueChannel -> transformer -> DirectChannel -> service activator
```

The transformer is the first step reading from the queue, so the transformer's endpoint needs the poller. The service activator receives via `DirectChannel` and does not need a poller for that receive step.

If another `QueueChannel` is placed before the service activator, the endpoint reading the second queue needs its own poller. Do not attach a poller to every step just because the start of the flow has a queue.

## 6. Configuring the Polling Pace

### 6.1. fixedDelay

When the poller executes work directly on the scheduler without handing the poll cycle off to a separate executor, fixed delay is the pause interval from when the previous cycle finishes until the next cycle begins.

Example `fixedDelay = 500 ms`:

```text
T0         start polling
T0+300 ms  current poll completes
T0+800 ms  next poll can start
```

If a cycle processes many messages or calls a slow service, the actual period is longer than 500 ms. The configuration above does not mean 10 messages are guaranteed to be processed every 500 ms.

When a `taskExecutor` is present, the scheduler may only submit work to the executor. The moment work submission finishes and the moment the worker finishes are no longer the same timestamp; you must also account for overlap and executor backlog.

### 6.2. fixedRate and cron

- **Fixed rate:** Suitable when the schedule should follow a periodic cadence; does not guarantee business work finishes at every tick if resources are busy.
- **Cron:** Suitable for calendar/time-of-day schedules, such as specific windows during the day; you must specify the trigger's time zone.
- **Fixed delay:** Easy to reason about when you want a rest interval after each round of work.

Fixed rate does not by itself guarantee handlers run in parallel. Concurrency depends on the scheduler, executor, and endpoint structure.

### 6.3. receiveTimeout

`receiveTimeout` controls how long a receive call can wait when the channel does not yet have a message. With `QueueChannel`, `0` returns immediately when the queue is empty.

If the receive timeout is 1,000 ms, a cycle can spend nearly one second waiting for a message. After receiving a message, the handler can still run longer than one second.

- A large timeout can catch messages that arrive while waiting, but holds the thread during the wait.
- A small or zero timeout is easier to control when multiple endpoints share a scheduler.
- Timeouts for HTTP, databases, or business calls must be set on the component making those calls.

### 6.4. maxMessagesPerPoll

| Choice | Meaning and Trade-offs |
| --- | --- |
| `1` | At most one message per cycle; easy to observe, though it may increase scheduling overhead |
| Positive number greater than `1` | Multiple messages per cycle; reduces trigger overhead but holds the thread longer |
| Negative value per poller semantics | Not capped by count; a cycle typically stops when no message is received or a stop condition occurs |

Explicitly declare a positive initial value instead of relying on defaults across different polling endpoint types. With an unbounded configuration and a producer continuously adding messages, a single cycle can stretch on and monopolize shared resources.

`maxMessagesPerPoll(10)` does not mean:

- The handler receives a list of 10 elements.
- There are 10 concurrent workers running.
- The entire system can only process 10 messages per second.
- All 10 messages automatically belong to the same transaction.

A standard handler is still invoked one message at a time. If you need a batch payload, you must design an aggregation step or a batch-capable source.

### 6.5. Estimating Throughput

For a queue that always has data, a single sequential worker, fixed delay, and no separate executor:

```text
Duration of one poll ≈ N × T_process + D

Throughput ≈ N / (N × T_process + D)
```

Where `N` is the actual number of messages in the poll, `T_process` is the average processing time per message, and `D` is the fixed delay; time is measured in seconds.

If `N = 10`, each message takes `0.05 s`, and delay is `0.5 s`, ideal throughput is roughly `10 messages/s`. This calculation excludes receive time, logging, resource contention, errors, or retries.

If the average arrival rate is 15 messages/s over a sustained period, the backlog will continue to grow. Increasing queue capacity only delays when it fills up; you must increase processing capacity, throttle input rates, or change how work is distributed.

## 7. Scheduler, Executor, and Concurrency

### 7.1. Two Distinct Roles

The task scheduler decides when to trigger. The task executor supplies execution threads when the poller is configured to hand work off to a separate executor.

Not declaring a custom executor does not mean the entire application has only one thread. Multiple endpoints can still use different scheduler threads, but a long-blocking receive or a slow handler holds the thread executing it.

### 7.2. Adding a Bounded Executor

You can add the following bean to the main configuration class:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor orderPollExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("order-poll-");
    return executor;
}
```

Update the handler's poller configuration to:

```java
.poller(Pollers
        .fixedDelay(Duration.ofMillis(500))
        .receiveTimeout(0)
        .maxMessagesPerPoll(10)
        .taskExecutor(orderPollExecutor()))
```

Spring manages initializing and shutting down the executor when it is a bean. Poll cycles can execute concurrently when the schedule continues submitting work and the executor has capacity to accept it.

Each cycle still processes its own messages sequentially. An executor enables multiple cycles to run concurrently; it does not automatically split a single 10-message cycle into 10 independent tasks.

### 7.3. Conditions to Consider When Increasing Concurrency

1. **Thread safety:** Handlers must not mutate shared state unsafely.
2. **Ordering:** FIFO applies to message retrieval order; multiple workers can finish out of retrieval order.
3. **Downstream resources:** Worker count must align with connection pools and external service limits.
4. **Executor backlog:** Understand rejection or caller-blocking policies when the work queue fills up.
5. **Thread context:** Transactions, security context, and logging context do not automatically cross asynchronous boundaries.

If the business requires strict ordering per customer, design key-based partitioning or serialization. Merely adding workers to a single queue will not satisfy that requirement.

## 8. Default Poller and Local Poller

You can use a default poller for endpoints with similar characteristics:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.scheduling.PollerMetadata;

@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    return Pollers
            .fixedDelay(Duration.ofSeconds(1))
            .receiveTimeout(0)
            .maxMessagesPerPoll(5)
            .getObject();
}
```

An endpoint requiring polling can use the default poller when no local poller is declared. If an endpoint specifies `.poller(...)`, that local policy is used for that endpoint.

If both a local poller and a default poller are missing, an endpoint reading a `PollableChannel` typically causes application context creation to fail. Conversely, attaching a poller to an endpoint reading a `DirectChannel` indicates selecting the wrong receiving mechanism.

Flows with different SLAs or processing costs should declare explicit local configurations directly on the endpoint.

## 9. Error Handling After a Message Enters the Queue

### 9.1. The Sender Is No Longer on the Same Call Stack

```text
Producer: send(message) -> succeeds -> continues other work

Later:
PollingConsumer: receive() -> handler -> throws exception
```

A `try/catch` around `send(...)` only catches synchronous errors from the send operation and processing that actually occurs within that call. It does not catch business errors occurring later on the polling consumer thread.

With gateways, distinguish between:

- One-way gateway: completion of the send operation does not indicate business outcome.
- Request-reply gateway: the caller may be waiting for a reply; you must design `replyChannel`, `errorChannel`, timeouts, and error-response handling suited to an asynchronous flow.

Do not assume that using a gateway automatically turns every post-queue error back into an exception at the caller.

### 9.2. ErrorMessage and errorChannel

In standard asynchronous error handling, Spring Integration wraps the error in an `ErrorMessage` and sends it to the configured error channel. For errors associated with a message, the `errorChannel` header can participate in selecting the destination; when none is specified, the default error channel is the usual handling point.

The payload of an `ErrorMessage` is a `Throwable`. The failed message can usually be obtained from a `MessagingException`. However, errors when receiving from a store can occur before a business message exists.

Example adding an error flow to a configuration that already has `@EnableIntegration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

@Bean
public IntegrationFlow logIntegrationErrors() {
    return IntegrationFlow
            .from("errorChannel")
            .handle(Throwable.class, (failure, headers) -> {
                Message<?> failedMessage = null;

                if (failure instanceof MessagingException messagingException) {
                    failedMessage = messagingException.getFailedMessage();
                }

                Object traceId = failedMessage == null
                        ? null
                        : failedMessage.getHeaders().get("traceId");

                System.err.println("Integration failure, traceId=" + traceId);
                failure.printStackTrace();
                return null;
            })
            .get();
}
```

This is an example for observing the mechanism. In production, use structured logging and avoid logging sensitive data. If an exception is wrapped across multiple layers, you may need to walk the cause chain to find the failed message.

If you configure a custom `ErrorHandler` on the poller, verify that configuration's behavior; do not infer error routing solely from the bean name `errorChannel`.

### 9.3. An Error Channel Does Not Automatically Recover Messages

Having a subscriber receiving `ErrorMessage` does not automatically provide any of the following behaviors:

- Re-queuing the message into the original queue.
- Rolling back an in-memory queue.
- Retrying with backoff.
- Persisting data durably for replay after restart.

Categorize errors before deciding how to handle them:

| Error Type | Handling Direction |
| --- | --- |
| Invalid data | Route to a rejection flow, preserving the reason and business key |
| External service temporarily unavailable | Bounded retry with backoff |
| Retries exhausted | Route to a dead-letter channel or failed-message store |
| Channel store failure | Alert infrastructure, evaluate endpoint resilience |

If recovery after a process crash is required, the final error destination also needs appropriate durability. A second in-memory `QueueChannel` does not meet that requirement.

### 9.4. Retry Scope

Distinguish poller advice, which can wrap both the receive operation and the handler invocation, from advice on the business handler itself.

If you only want to retry a service call, handler-level advice is usually easier to control. Retrying around the polling step can lead to a retry pulling a different message after the previous message has already been removed from the queue.

If a handler already caused side effects before failing, retrying can repeat those side effects. You need a business key or idempotency key and clear rules for which errors are retryable.

## 10. Transactions and Reliability

### 10.1. Transactional Poller

A poller can be configured with a transaction manager:

```java
// transactionManager is the PlatformTransactionManager for the relevant resource.
.poller(Pollers
        .fixedDelay(Duration.ofMillis(500))
        .receiveTimeout(0)
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
```

This is a configuration snippet to attach to an endpoint; it does not declare the transaction manager or specific store.

A transaction only protects resources that actually participate in that same transaction boundary. Adding `.transactional(...)` does not make every operation inside the handler rollback-capable.

`maxMessagesPerPoll` is also not an API for defining transaction batches. Do not infer that a cap of 10 messages per cycle means all 10 run in the same transaction; check actual polling execution and advice behavior.

### 10.2. In-Memory Queues Do Not Automatically Undo Receive

With a standard in-memory queue:

```text
1. receive() removes the message from the queue.
2. Handler writes to the database.
3. Handler throws an exception.
4. Database transaction rolls back.
5. The message does not automatically return to the queue from that rollback alone.
```

A queue backed by a transaction-aware message store, such as a JDBC channel message store design, can allow message retrieval to participate in a transaction. You must choose the right transaction manager, connection resource, and store configuration. Merely having any store is not enough to conclude that message retrieval will roll back as required.

### 10.3. Synchronous Boundaries

A transaction bound to the processing flow can cover subsequent synchronous steps if the resources support it. If work is sent over an `ExecutorChannel` or another queue, the downstream section has its own execution boundary and does not automatically inherit the current transaction.

HTTP requests or emails are not automatically undone when a database rolls back. Workflows that both write data and emit events may need a transactional outbox or a business-appropriate coordination mechanism.

### 10.4. Exactly-Once Does Not Come from the Endpoint Alone

`PollingConsumer` coordinates receiving and processing; it does not by itself guarantee business logic runs exactly once.

For example, a payment request succeeds, but the application crashes before recording the result. If the message is replayed, the payment request could be sent again. A key such as `orderId` or `paymentRequestId` must be enforced where the side effect happens, not merely written to logs.

End-to-end reliability depends on message durability, rollback or replay, idempotency, and reconciliation capabilities.

## 11. Testing PollingConsumer

### 11.1. Testing Input and Output

Tests should prove that a message travels through the queue, is processed, and appears on the output. An output queue lets you wait for results with an explicit timeout.

The configuration below is independent of the order example. It requires JUnit Jupiter alongside the project's Spring Integration and Spring Context dependencies.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PollingConsumerTest {

    @Configuration
    @EnableIntegration
    static class TestConfiguration {

        @Bean
        QueueChannel testInput() {
            return new QueueChannel(10);
        }

        @Bean
        QueueChannel testOutput() {
            return new QueueChannel(10);
        }

        @Bean
        IntegrationFlow testFlow() {
            return IntegrationFlow
                    .from(testInput())
                    .handle(String.class, (payload, headers) ->
                                    payload.toUpperCase(Locale.ROOT),
                            endpoint -> endpoint.poller(Pollers
                                    .fixedDelay(Duration.ofMillis(20))
                                    .receiveTimeout(0)
                                    .maxMessagesPerPoll(1)))
                    .channel(testOutput())
                    .get();
        }
    }

    @Test
    void shouldProcessMessageFromQueue() {
        try (var context = new AnnotationConfigApplicationContext(
                TestConfiguration.class)) {
            QueueChannel input = context.getBean("testInput", QueueChannel.class);
            QueueChannel output = context.getBean("testOutput", QueueChannel.class);

            boolean sent = input.send(MessageBuilder
                    .withPayload("spring integration")
                    .setHeader("traceId", "test-001")
                    .build(), 100);

            assertTrue(sent);

            Message<?> result = output.receive(2_000);

            assertNotNull(result);
            assertEquals("SPRING INTEGRATION", result.getPayload());
            assertEquals("test-001", result.getHeaders().get("traceId"));
        }
    }
}
```

The input is a queue and the handler has a poller, so the test truly exercises the polling mechanism. The output is also a queue so the test can receive the result; no extra consumer is needed just to capture the test message.

Two seconds is a wait limit, not a fixed processing time. `receive(...)` returns early as soon as a message arrives. This is better than calling `Thread.sleep(...)` and assuming processing has completed.

### 11.2. Additional Scenarios

| Scenario | What to Observe |
| --- | --- |
| Empty queue | No phantom results, no resource exhaustion while waiting |
| Multiple messages | All results arrive, ordering matches concurrency level |
| Full queue | Producer times out or receives an error per policy |
| Handler failure | Error reaches the right channel with tracing details |
| Retry | Exact retry count and expected side effects |
| Stopped endpoint | Does not keep pulling new messages as when running |
| Rollback with transactional store | Message and business data recover according to design |
| Restart | Only assert recovery when backed by a verified durable store |

To test `maxMessagesPerPoll` specifically, you need to control the trigger and endpoint lifecycle. Sending 10 messages and waiting a few seconds does not prove each cycle pulled only one message, because the poller may have run multiple cycles.

## 12. Lifecycle and Operations

### 12.1. Checking Whether the Endpoint Is Running

A queue can accept messages even when the consumer is not running. When backlog grows, check lifecycle, auto-startup, polling schedule, scheduler, and executor rather than checking only the handler.

Naming the endpoint `.id("orderPollingConsumer")` helps locate the component to manage. Stopping an endpoint and completing in-flight work is not an instantaneous operation; shutdown policies must account for handlers currently calling services and executors holding queued work.

### 12.2. Signals to Monitor

- Number of waiting messages and backlog trend.
- Oldest message age or queue wait time before processing.
- Handler processing duration and actual throughput.
- Error counts, retries, and messages routed to a dead-letter store.
- Busy scheduler threads, busy executor workers, and queued tasks.
- Producer timeout rate when sending to the queue.

Not all of these metrics appear automatically with the same names in every application; Micrometer, observations, or additional business instrumentation may be required.

If you need to measure message age from initial ingestion, use an explicit ingestion timestamp header. Do not assume the current message's timestamp always represents when data first entered the system, because downstream steps creating new messages can alter metadata.

### 12.3. Symptom-Based Diagnostics

| Symptom | Possibilities to Check | Initial Action |
| --- | --- | --- |
| Startup fails when handler reads queue | Missing poller | Check local and default pollers |
| Backlog grows with no processing | Endpoint stopped, schedule not due, or threads occupied | Check lifecycle and thread dumps |
| Slower than configured period | Slow handler, blocking receive, or long cycle | Measure receive and processing times separately |
| Multiple endpoints slow down together | Shared scheduler or downstream resource saturated | Inspect pools and blocking calls |
| Out-of-order completion | Multiple concurrent cycles/workers | Review ordering requirements and partitioning |
| Messages lost after error | In-memory queue lacks rollback/replay | Review error policy and store |
| High CPU when queue is empty | Polling too aggressively or too many polling endpoints | Tune cadence to SLA and measurements |
| Executor accumulates large queue | Submitting work faster than workers finish | Bound queues, concurrency, and trigger pace |

## 13. Hands-On Exercise: Order Notification Processor

Flow design:

```text
Producer
   |
   v
notificationQueue (capacity = 100)
   |
   | PollingConsumer
   v
Validate data -> Select notification type -> Send notification
                                      |
                                      v
                               Error handling flow
```

Carry out step by step:

1. Create a queue with capacity 100; messages include `notificationId` and `traceId`.
2. Set fixed delay to 200 ms, `receiveTimeout(0)`, and at most 5 messages per poll.
3. Start with sequential processing; record ingestion, start, and completion timestamps.
4. In the practice environment, simulate a handler taking about 100 ms per message.
5. Create one invalid-data case and one transient-service-failure case.
6. Design an error destination so failed requests can be reprocessed when appropriate.
7. Add a bounded executor and observe throughput and completion order.
8. Write tests for both the success path and error path with finite timeouts.

Analysis questions:

- Roughly how long does one 5-message cycle take before adding fixed delay?
- Is an arrival rate of 20 messages/s sustainable with the sequential setup?
- Does increasing `maxMessagesPerPoll` reduce the service-call time per message?
- Do two workers guarantee completion in send order?
- If the process stops after pulling a message but before sending the notification, how do you recover?
- How do you use `notificationId` to avoid duplicate notifications on retry?

At 100 ms per message, 5 messages take about 500 ms. Adding the 200 ms fixed delay, ideal sequential capacity is roughly `5 / 0.7 ≈ 7.14 messages/s`, excluding other overhead. An arrival rate of 20 messages/s will cause the backlog to grow steadily.

## 14. Knowledge Self-Check

1. **Where does `PollingConsumer` receive from?** From a `PollableChannel`; a polling inbound adapter reads from a `MessageSource`.
2. **Why does a handler reading `QueueChannel` need a poller?** A queue does not push to subscribers when a producer sends; a receiver must actively pull.
3. **Does `receiveTimeout` bound handler execution?** No, it bounds the receive wait time.
4. **Does `maxMessagesPerPoll(10)` create 10 workers?** No, it limits the number of messages per poll cycle.
5. **Does a successful send mean processing succeeded?** No, especially when a queue introduces an asynchronous boundary.
6. **Does an error channel automatically retry?** No, separate retry or replay policies are required.
7. **Does a transaction manager automatically roll back an in-memory queue?** No, the channel resource itself must support and participate in the transaction.
8. **Why is idempotency needed?** A message may be retried after side effects have already occurred.
9. **When is a second poller needed?** When another endpoint also receives from a separate `PollableChannel`.
10. **What determines a good configuration?** Latency, throughput, ordering, resource usage, and reliability verified through actual behavior.

When designing a `PollingConsumer`, you must simultaneously define the receiving policy, execution resources, error destination, and message recovery strategy. A sensible polling period is only one part of a reliable integration flow.