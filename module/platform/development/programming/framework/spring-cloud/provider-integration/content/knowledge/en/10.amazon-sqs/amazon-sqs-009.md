# Batching, Concurrency, Backpressure, and Graceful Listener Shutdown

An Amazon Simple Queue Service (Amazon SQS) consumer must balance three factors: how many messages to receive per poll, how many messages to process concurrently, and how much load downstream dependencies can handle. Receiving too few underutilizes resources; receiving too many or running too many concurrent handlers can overload databases and downstream APIs. When an application shuts down or deploys a new version, listeners must also stop polling, finish in-flight work, and acknowledge messages within the allowed window.

Spring Cloud AWS provides `SqsMessageListenerContainer` and `@SqsListener` to coordinate these concerns. **Batch processing** groups multiple payloads into one listener invocation; **concurrency** limits the number of messages processed simultaneously; **backpressure** throttles polling based on available slots; and **container lifecycle** manages start/stop and shutdown timeouts.

This lesson uses **Spring Cloud AWS 3.4.1**, focusing on choosing batch sizes, `maxConcurrentMessages`, `maxMessagesPerPoll`, `maxDelayBetweenPolls`, the three `BackPressureMode` options, Standard/FIFO handling, thread bounds, observability, and graceful shutdown.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the differences among batch listeners, batch receives, and acknowledgment batching.
- Write `@SqsListener` methods accepting `List<T>` or `List<Message<T>>`.
- Configure `maxConcurrentMessages`, `maxMessagesPerPoll`, `pollTimeout`, and `maxDelayBetweenPolls`.
- Estimate approximate throughput and spot bottlenecks in databases, HTTP clients, or thread pools.
- Choose between `AUTO`, `ALWAYS_POLL_MAX_MESSAGES`, and `FIXED_HIGH_THROUGHPUT`.
- Tune concurrency for Standard and FIFO queues.
- Use `CompletableFuture` and appropriate executors to avoid blocking AWS SDK threads.
- Stop listener containers cleanly, waiting for active message processing and acknowledgments to finish.
- Test batching, backpressure, high load, and shutdown while messages are in-flight.

## 2. Concepts to Separate

The following terms are related but not synonymous:

| Concept | Meaning |
|---|---|
| **Receive batch** | A single `ReceiveMessage` request can return up to 10 messages from SQS |
| **Batch listener** | One method invocation receives a list of payloads/messages instead of one message |
| **`maxMessagesPerPoll`** | Maximum messages the container wants to supply per poll cycle; values above 10 combine multiple receive requests |
| **`maxConcurrentMessages`** | Maximum messages processed concurrently per queue |
| **Acknowledgment batching** | Grouping delete requests to dispatch `DeleteMessageBatch` by interval/threshold |
| **Backpressure** | Throttling polling based on available processing permits/slots |
| **Graceful shutdown** | Stopping new polls and waiting for active work and acknowledgments within allowed timeouts |

A batch listener can handle multiple messages in a single method call, which does not automatically mean elements in the list run in parallel. A listener may iterate sequentially, issue a database bulk operation, or apply bounded concurrency.

## 3. Batch Processing with @SqsListener

In Spring Cloud AWS 3.4.1, an `@SqsListener` method taking `List<Payload>` or `List<Message<Payload>>` enables batch mode:

```java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {
    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @SqsListener("${app.sqs.order-queue}")
    public void handle(List<OrderEvent> events) {
        orderService.applyBatch(events);
    }
}
```

The container passes the entire poll result to the listener. If `maxMessagesPerPoll` is 10, the method can receive up to 10 payloads per call. The SQS API never returns more than 10 messages in a single `ReceiveMessage` request.

### 3.1. Receiving Per-Message Metadata

If `MessageHeaders` are needed, accept a list of `Message<T>`:

```java
@SqsListener("${app.sqs.order-queue}")
public void handle(List<Message<OrderEvent>> messages) {
    for (Message<OrderEvent> message : messages) {
        String correlationId = message.getHeaders()
            .get("Sqs_MA_correlationId", String.class);
        orderService.apply(message.getPayload(), correlationId);
    }
}
```

A batch listener can also accept `BatchAcknowledgement` when using `MANUAL`, or `BatchVisibility` to update visibility for part or all of the batch. With `List` parameters, per-item metadata is read from `Message.getHeaders()`.

### 3.2. Batch Listeners Need Not Process Items in Parallel

The following code processes items sequentially:

```java
@SqsListener("${app.sqs.order-queue}")
public void handle(List<OrderEvent> events) {
    for (OrderEvent event : events) {
        orderService.applyIdempotently(event);
    }
}
```

Sequential processing easily preserves batch order and simplifies transactions, though total latency equals the sum of individual processing times. For a 10-message batch averaging 500 ms each, sequential time is roughly 5 seconds plus overhead.

If switching to parallel execution, bound concurrency to database/API capacity. Never spawn unbounded threads per message. With FIFO, do not run messages sharing a `MessageGroupId` concurrently if doing so can reorder side effects.

## 4. maxMessagesPerPoll and SQS's 10-Message Limit

A single SQS `ReceiveMessage` request returns at most 10 messages. Spring Cloud AWS lets you configure `maxMessagesPerPoll` above 10 for batch listeners; the framework aggregates results from multiple polls into a larger batch.

Example:

```java
@SqsListener(
    value = "${app.sqs.order-queue}",
    maxMessagesPerPoll = "25",
    maxConcurrentMessages = "25"
)
public void handle(List<OrderEvent> events) {
    orderService.applyBatch(events);
}
```

The container may issue multiple receive requests to assemble a batch of up to 25 messages. Actual batch size can still be smaller if the queue lacks enough messages or SQS returns fewer than requested.

Rules to remember in 3.4.1:

- `maxMessagesPerPoll` defaults to 10.
- The value must be less than or equal to `maxConcurrentMessages`.
- One SQS request returns at most 10 messages; values above 10 are assembled across multiple polls.
- Use large batches only when the listener genuinely benefits from bulk operations or lower per-message overhead.

Large batches increase single-invocation duration, memory footprint, and the blast radius when a batch fails. For workloads with variable latency, smaller batches are usually easier to manage.

## 5. maxConcurrentMessages and In-Flight Processing Count

`maxConcurrentMessages` caps concurrently processed messages **per queue** inside a container. The default in Spring Cloud AWS 3.4.1 is 10.

For example, a container handling two queues with `maxConcurrentMessages = 20` can process up to roughly 40 messages concurrently across both queues, depending on polling, batching, and acknowledgment state. This setting is not throughput per second; it is a cap on concurrent in-progress messages.

### 5.1. Estimating Concurrency from Processing Time

A rough estimate for theoretical throughput:

\[
\text{throughput} \approx \frac{\text{concurrency}}{\text{average processing time}}
\]

For example, 20 messages processed concurrently, averaging 0.5 seconds each:

\[
20 / 0.5 \approx 40\ \text{messages/second}
\]

This is only a theoretical estimate. Real throughput also depends on SQS latency, batch size, acknowledgment duration, database connection pools, downstream rate limits, CPU, network, and retry rates.

### 5.2. Concurrency Is Per Queue

When a container listens to multiple queues, total concurrent messages can reach the number of queues multiplied by `maxConcurrentMessages`. Account for total load on shared dependencies. If three queues update one database, each with concurrency 20, the database can see around 60 concurrent operations from that container.

When acknowledgment batching is enabled, the framework treats messages handed off to the acknowledgment queue as no longer holding a processing permit; SQS's visible in-flight count can exceed `maxConcurrentMessages` while waiting for batch deletes.

## 6. Configuring the Container Factory

You can set defaults across listeners using `SqsMessageListenerContainerFactory`:

```java
import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.BackPressureMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

import java.time.Duration;

@Configuration
public class SqsListenerConfiguration {
    @Bean
    SqsMessageListenerContainerFactory<Object> defaultSqsListenerContainerFactory(
            SqsAsyncClient sqsAsyncClient) {
        return SqsMessageListenerContainerFactory.builder()
            .sqsAsyncClient(sqsAsyncClient)
            .configure(options -> options
                .maxConcurrentMessages(20)
                .maxMessagesPerPoll(10)
                .maxDelayBetweenPolls(Duration.ofSeconds(5))
                .pollTimeout(Duration.ofSeconds(10))
                .backPressureMode(BackPressureMode.AUTO)
                .listenerShutdownTimeout(Duration.ofSeconds(30))
                .acknowledgementShutdownTimeout(Duration.ofSeconds(30))
            )
            .build();
    }
}
```

The values above illustrate configuration for a Standard queue. With `maxConcurrentMessages` at 20 and up to 10 messages per poll, the container can run two concurrent polls under heavy load. `maxDelayBetweenPolls` waits for slots to fill a full batch before attempting a smaller poll.

### 6.1. Overriding per Listener

Annotation attributes override the corresponding factory defaults:

```java
@SqsListener(
    value = "${app.sqs.audit-queue}",
    id = "audit-listener",
    maxConcurrentMessages = "8",
    maxMessagesPerPoll = "8",
    pollTimeoutSeconds = "10"
)
public void handle(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
```

A listener can reference a dedicated factory via the `factory` attribute. Use separate factories when queues have distinctly different load profiles or shutdown requirements; avoid proliferation of near-identical configurations that complicate operations.

### 6.2. Defaults in Spring Cloud AWS 3.4.1

| Option | Default | Notes |
|---|---:|---|
| `maxConcurrentMessages` | 10 | Maximum concurrently processed messages per queue |
| `maxMessagesPerPoll` | 10 | Single SQS receive request maxes at 10; container values over 10 combine polls |
| `pollTimeout` | 10 seconds | Listener container configurable range is 1–10 seconds |
| `maxDelayBetweenPolls` | 10 seconds | Wait for permits to form a full batch before partial polling |
| `backPressureMode` | `AUTO` | Default balanced mode |
| `listenerShutdownTimeout` | 20 seconds | Wait for active message processing tasks |
| `acknowledgementShutdownTimeout` | 20 seconds | Wait for batch acknowledgments after processing finishes |

If a setting appears in both the factory and `@SqsListener`, the annotation value takes precedence for that listener.

## 7. maxDelayBetweenPolls and Partial Polling

The container acquires permits before receiving messages so it never pulls more work than it can handle. When `maxConcurrentMessages` is nearly full, polling threads can wait for in-flight tasks to finish so enough permits free up for a full batch.

`maxDelayBetweenPolls` is the maximum wait for full permits. Once it elapses, if the backpressure mode permits partial polling, the container can poll a smaller batch using whatever permits are currently free.

Example:

```text
maxConcurrentMessages = 20
maxMessagesPerPoll    = 10

20 messages currently processing
6 messages finish after 5 seconds
maxDelayBetweenPolls = 5 seconds

Container can poll 6 messages instead of waiting for all 10 permits.
```

Partial polling utilizes freed capacity quickly, though it can issue more small receive requests. If poll request cost outweighs early slot utilization, choose a mode that polls only full batches.

## 8. Three BackPressureMode Options

Spring Cloud AWS 3.4.1 supports three modes:

| Mode | Behavior | When Suitable |
|---|---|---|
| `AUTO` | Default. Starts in low throughput, shifts to high throughput when messages arrive; allows partial polling | Balanced choice for most workloads |
| `ALWAYS_POLL_MAX_MESSAGES` | Disables partial polling; waits for full batch permits before next poll | Minimizing poll requests while accepting lower throughput on partial slot availability |
| `FIXED_HIGH_THROUGHPUT` | Stays in high throughput without reverting to low throughput; still allows partial batch polling | Sustained high-load workloads avoiding mode-switching overhead |

### 8.1. AUTO

`AUTO` starts with one poll at a time. When a poll returns at least one message, the container shifts into high throughput and runs concurrent polls up toward `maxConcurrentMessages`. When a poll returns empty, it drops back to low throughput, polling once at a time until new messages appear.

This is the default and usually a strong starting point. Do not switch modes just to chase concurrency; measure backlog, processing time, and actual poll counts first.

### 8.2. ALWAYS_POLL_MAX_MESSAGES

This mode disables partial batch polling. With `maxMessagesPerPoll = 10`, the container waits until all 10 permits are free before polling the next batch. This cuts down small poll requests, though freed slots sit idle while waiting.

Choose this mode when poll request volume is a significant cost and workloads consistently fill batches. Unsuitable for sparse arrivals or low-latency requirements.

### 8.3. FIXED_HIGH_THROUGHPUT

This mode never reverts to low throughput when the queue goes empty. The container keeps running parallel polls and performs partial polling as permits open.

This benefits sustained high traffic, but can generate many empty receive requests whenever the queue temporarily drains. Monitor `NumberOfEmptyReceives`, request cost, and backlog before choosing it.

Example:

```java
@Bean
SqsMessageListenerContainerFactory<Object> highThroughputFactory(
        SqsAsyncClient sqsAsyncClient) {
    return SqsMessageListenerContainerFactory.builder()
        .sqsAsyncClient(sqsAsyncClient)
        .configure(options -> options
            .maxConcurrentMessages(100)
            .maxMessagesPerPoll(10)
            .backPressureMode(BackPressureMode.FIXED_HIGH_THROUGHPUT)
        )
        .build();
}
```

Benchmark this configuration in a production-like environment. A concurrency of 100 does not mean your database or target API can sustain 100 concurrent requests.

## 9. Backpressure Does Not Replace Downstream Limits

Container backpressure throttles polling based on permits and active message count. It does not automatically detect a slow database, rate-limited API, or exhausted connection pool while listeners hold those slots.

Combine it with business-layer safeguards:

- Size connection pools to match total concurrency across all queues.
- Use bulk APIs or batch inserts where databases support them.
- Use semaphores/bounded executors to cap calls to downstream APIs.
- Apply timeouts, circuit breakers, and backoff retries for dependencies.
- Lower `maxConcurrentMessages` when downstream cannot absorb current load.
- Never create unbounded executors or unbounded in-memory queues.

If a listener receives a message, pushes it onto an unbounded internal queue, and returns normally, SQS may delete the message while the work is still sitting in RAM. If the process dies, that work is lost. If using an internal queue, persist durably or acknowledge only after work is safely recorded.

## 10. Batch Failures and Acknowledgment

With `ON_SUCCESS`, if a batch listener throws an exception, the batch invocation fails and none of the batch's messages are auto-acknowledged. Once visibility timeout expires, they can be redelivered—which may re-run items in the batch that had already succeeded.

To acknowledge items individually, use `MANUAL` and `BatchAcknowledgement`:

```java
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.BatchAcknowledgement;
import org.springframework.messaging.Message;

@SqsListener(
    value = "${app.sqs.order-queue}",
    acknowledgementMode = "MANUAL"
)
public void handleBatch(
        List<Message<OrderEvent>> messages,
        BatchAcknowledgement<OrderEvent> acknowledgement) {

    List<Message<OrderEvent>> succeeded = new ArrayList<>();

    for (Message<OrderEvent> message : messages) {
        try {
            orderService.applyIdempotently(message.getPayload());
            succeeded.add(message);
        } catch (RecoverableProcessingException ex) {
            log.warn("Will retry eventId={}", message.getPayload().eventId(), ex);
        }
    }

    if (!succeeded.isEmpty()) {
        acknowledgement.acknowledge(succeeded);
    }
}
```

Acknowledge only messages whose processing is durable. Remaining messages will be redelivered when the visibility timeout expires. Consumers must still be idempotent because a message can be redelivered if the database commits but acknowledgment fails.

### 10.1. Acknowledgment Batching Is a Separate Layer

Batch listeners group payloads into one method call. Acknowledgment batching groups delete requests by interval/threshold. You can enable batch listeners with immediate acknowledgment, or process messages one by one while batching acknowledgments at the container level. The two settings serve different purposes.

When acknowledgment batching is enabled, messages can remain in-flight in SQS even after the container releases the processing permit upon enqueuing the acknowledgment. Factor ack wait time into visibility timeout and watch not-visible counts on CloudWatch.

## 11. FIFO Batches and Message Groups

For FIFO queues, the container partitions messages by `MessageGroupId`. Messages within the same group execute sequentially; different groups can execute concurrently.

In batch mode, `fifoBatchGroupingStrategy` defaults to `PROCESS_MESSAGE_GROUPS_IN_PARALLEL_BATCHES`: groups are split into separate batches and processed in parallel while preserving order within each group.

You can select `PROCESS_MULTIPLE_GROUPS_IN_SAME_BATCH` to combine messages from multiple groups into a single batch. In that case, the listener must inspect `MessageGroupId` metadata and preserve per-group ordering in business logic.

If processing a message in a group fails, later messages in that same group are dropped from the current processing pass and can be redelivered after visibility timeout expires. Earlier messages already processed and acknowledged are not redelivered merely because a later message failed.

Do not share one listener container across both Standard and FIFO queues. If your application needs both queue types, define separate listeners/containers/factories.

## 12. FIFO Concurrency Is Bounded by Active Groups

Raising `maxConcurrentMessages` never makes a single FIFO group run in parallel. If all messages share one `MessageGroupId`, the container still advances only one sequential chain at a time.

Example:

```text
orders.fifo

Group order-101: Created → Paid → Shipped
Group order-202: Created → Cancelled
Group order-303: Created → Paid
```

All three groups can process concurrently, while each group preserves order internally. If only `order-101` has messages, raising concurrency from 10 to 100 yields no 99 extra useful processing streams.

Choose `MessageGroupId` by the aggregate needing ordering. Never pick random groups when events for the same order or account must apply sequentially.

## 13. Blocking and Non-Blocking Listeners

Spring Cloud AWS's SQS integration builds on `CompletableFuture` and the AWS SDK 2.x async client. Polling, visibility changes, and acknowledgments execute asynchronously. Listeners can be synchronous methods or return `CompletableFuture<Void>`.

Synchronous listener:

```java
@SqsListener("${app.sqs.inventory-queue}")
public void handle(InventoryAdjusted event) {
    inventoryService.apply(event);
}
```

Asynchronous listener offloading blocking work to a dedicated executor:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.stereotype.Component;

@Component
public class AsyncInventoryListener {
    private final InventoryService inventoryService;
    private final Executor inventoryExecutor;

    public AsyncInventoryListener(
            InventoryService inventoryService,
            Executor inventoryExecutor) {
        this.inventoryService = inventoryService;
        this.inventoryExecutor = inventoryExecutor;
    }

    @SqsListener("${app.sqs.inventory-queue}")
    public CompletableFuture<Void> handle(InventoryAdjusted event) {
        return CompletableFuture.runAsync(
            () -> inventoryService.apply(event),
            inventoryExecutor
        );
    }
}
```

The container awaits the returned future to determine the processing outcome. Never call `.join()` or `.get()` on AWS SDK async event-loop threads. If business logic is blocking, use a synchronous listener or offload blocking work to a bounded executor.

### 13.1. Sizing the Executor

By default, Spring Cloud AWS uses a `ThreadPoolTaskExecutor` for components needing worker threads. When supplying a custom `componentsTaskExecutor`, ensure enough threads for peak load—typically sized around `maxConcurrentMessages × total queues` in the container, plus appropriate headroom for blocking components.

Avoid sharing one small executor across multiple high-volume queues without measuring queue wait time. Thread-pool starvation keeps received messages waiting in memory, increasing the chance visibility timeouts expire before processing completes.

## 14. Poll Backoff When SQS Requests Fail

`pollBackOffPolicy` controls how long polling threads wait after encountering exceptions such as throttling or connection errors. In Spring Cloud AWS 3.4.1, the default is exponential backoff with an initial 1-second delay, multiplier 2, and 10-second maximum.

This backs off poll errors, distinct from message-processing retries in `ErrorHandler`. One throttles receive requests; the other handles messages already received whose processing failed.

If polling fails repeatedly, check credentials, IAM, Region, queue URL, networking, and quotas. Never raise concurrency to work around permission or connectivity errors.

## 15. Graceful Shutdown of Listener Containers

`MessageListenerContainer` implements `SmartLifecycle`. For listeners created via `@SqsListener`, Spring Cloud AWS registers containers in `MessageListenerContainerRegistry`; the registry coordinates start/stop with the Spring `ApplicationContext` lifecycle. Annotation-created containers are not standalone Spring beans.

During shutdown, the container waits by default for active polling, processing, and acknowledgments to finish within configured timeouts. Once timeouts expire, remaining operations are cancelled and the container attempts a forced stop.

Two key timeouts in 3.4.1:

| Option | Default | Meaning |
|---|---:|---|
| `listenerShutdownTimeout` | 20 seconds | Time to wait for active message-processing tasks to finish |
| `acknowledgementShutdownTimeout` | 20 seconds | Time to wait for batch acknowledgments to complete after listener processing finishes or times out |

These can be configured individually:

```java
.configure(options -> options
    .listenerShutdownTimeout(Duration.ofSeconds(45))
    .acknowledgementShutdownTimeout(Duration.ofSeconds(20))
)
```

These are two sequential waiting phases. `acknowledgementShutdownTimeout` starts counting after listener processing finishes or times out. Size them based on real processing times and the time delete calls need to complete.

### 15.1. Stopping a Listener by ID

You can look up a container from the registry using the ID declared on `@SqsListener`:

```java
@SqsListener(
    value = "${app.sqs.order-queue}",
    id = "order-listener"
)
public void handle(OrderEvent event) {
    orderService.applyIdempotently(event);
}
```

```java
import io.awspring.cloud.sqs.listener.MessageListenerContainer;
import io.awspring.cloud.sqs.listener.MessageListenerContainerRegistry;
import org.springframework.stereotype.Service;

@Service
public class ListenerControlService {
    private final MessageListenerContainerRegistry registry;

    public ListenerControlService(MessageListenerContainerRegistry registry) {
        this.registry = registry;
    }

    public void stopOrderListener() {
        MessageListenerContainer<?> container =
            registry.getContainerById("order-listener");
        if (container != null) {
            container.stop();
        }
    }

    public void startOrderListener() {
        MessageListenerContainer<?> container =
            registry.getContainerById("order-listener");
        if (container != null) {
            container.start();
        }
    }
}
```

`stop()` prevents the container from receiving more messages and coordinates stopping through its lifecycle. Use this to pause consumers during maintenance or when a downstream system needs load shed. If exposing an admin endpoint, restrict access and record audit logs.

### 15.2. autoStartup=false

You can set `autoStartup(false)` so a container does not start automatically with the application context. The application must call `start()` once dependencies are ready or operational conditions are met. This helps with ordered startup, provided you ensure the listener eventually starts and monitor its state.

## 16. Shutdown in Kubernetes and Containerized Environments

Spring timeouts are only part of the shutdown budget. Kubernetes or your container orchestrator has its own termination grace period. If `terminationGracePeriodSeconds` is shorter than the combined time listeners need for processing and acknowledgment, the process can receive `SIGKILL` before containers finish.

A safe shutdown sequence:

1. Mark the instance unready for new HTTP traffic if the app also serves HTTP.
2. Stop listener containers or trigger Spring context shutdown to halt polling.
3. Wait for active messages to finish within `listenerShutdownTimeout`.
4. Wait for acknowledgments to finish within `acknowledgementShutdownTimeout`.
5. Complete remaining cleanup and exit the process before the platform forces termination.

For example, if listeners can take up to 45 seconds and acknowledgments up to 20 seconds, the termination grace period must exceed their sum plus headroom for Spring context and application cleanup. Base concrete numbers on SLAs and observed durations.

If a process is forcibly killed before acknowledging a message, SQS can redeliver that message once the visibility timeout expires. This is SQS's normal recovery mechanism; consumers must be idempotent so redelivery never repeats side effects.

## 17. Visibility Timeout Must Cover Batching and Shutdown

When a container receives a batch, the visibility timeout starts when SQS returns the messages—not when the listener starts each individual item. If a listener processes items sequentially, the last message in the batch waits while earlier items execute.

Account for:

```text
Required message visibility duration
  >= wait time inside batch
   + item processing time
   + business commit time
   + acknowledgment time
   + network/scheduling buffer
```

If batches are large and processing durations vary, shrink batch size, use efficient bulk operations, or use `BatchVisibility` to extend in-flight messages. Never set visibility too short and rely on retries to regulate throughput; that easily causes duplicate side effects.

Shutdown timeouts should also align with visibility. If applications are frequently terminated before processing/ack completes, messages will be redelivered. Increasing shutdown timeouts alone never guarantees once-only processing; you still need idempotency and properly ordered transactions.

## 18. Observability and Metrics to Watch

To tune batching and concurrency, observe both the queue and the application:

| Metric | Symptom | Where to Investigate |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Backlog rising steadily | Slow consumer polling or insufficient processing capacity |
| `ApproximateNumberOfMessagesNotVisible` | High in-flight count | High concurrency, slow processing, slow acks, or long visibility |
| `ApproximateAgeOfOldestMessage` | Rising message latency | Backlog, retries, or blocked FIFO group |
| `NumberOfMessagesReceived` vs. `NumberOfMessagesDeleted` | Large gap | Redeliveries, processing errors, or acknowledgment failures |
| `NumberOfEmptyReceives` | Spiking high | Empty queue, overly frequent polling, or suboptimal throughput mode |
| Listener processing duration p95/p99 | Rising | Slow DB/API, oversized batches, or starved thread pool |
| Active threads and executor queue size | Thread pool near saturation | Blocking work or undersized executor |
| Acknowledgment failures | Delete requests failing | IAM, receipt handles, throttling, or networking |

Spring Cloud AWS supports Micrometer Observation for SQS. The `spring.aws.sqs.listener` observation tracks processing inside listener containers. Enable observability and wire up an appropriate registry/exporter to monitor latency, errors, and throughput.

In logs, record queue, listener ID, `eventId`, message ID, and processing duration. Never log receipt handles or sensitive payloads.

## 19. Testing Batching, Backpressure, and Shutdown

| Test | Method | What to Verify |
|---|---|---|
| Batch receive | Send 25 messages with `maxMessagesPerPoll = 25` | Listener can receive a batch combined across multiple polls |
| Partial batch | Send only 4 messages with max batch 10 | Listener receives a batch smaller than 10 without waiting forever |
| Concurrency cap | Set `maxConcurrentMessages = 5`, increase load | Concurrent processing per queue stays within configured bounds per ack semantics |
| AUTO backpressure | Send a burst then let queue drain | Container switches between low and high throughput based on poll results |
| ALWAYS_POLL_MAX_MESSAGES | Deliberately free only partial permits | Container waits for full batch permits before polling again |
| FIXED_HIGH_THROUGHPUT | Keep queue empty then send burst | Container maintains parallel polling; observe empty receives |
| Batch failure | One item throws under `ON_SUCCESS` | Entire batch invocation can be redelivered |
| Partial manual ack | Use `BatchAcknowledgement` to ack succeeded items | Unacknowledged messages can be redelivered |
| FIFO batch | Send messages across multiple groups | Order preserved within groups; different groups run in parallel |
| Graceful stop | Call `container.stop()` while listener is active | Container halts new polls and awaits processing/ack within timeouts |
| Forced shutdown | Set timeout shorter than processing duration | Remaining work cancels; unacknowledged messages can be redelivered |
| Kubernetes termination | Terminate pod with configured grace period | Process exits before `SIGKILL` without dropping pending acknowledgments |

LocalStack works well for testing core SQS flows. Also test in an AWS test environment when verifying quotas, IAM, visibility, and realistic load behavior.

## 20. Common Issues and Fixes

| Symptom | Possible Causes | Resolution |
|---|---|---|
| Batches always smaller than expected | Queue lacks enough messages or SQS returned fewer than requested | Never assume full batches; inspect backlog and poll timeout |
| Large batches cause timeouts | Sequential listener processing, insufficient visibility, or slow downstream | Shrink batch size, use bulk operations, or extend visibility |
| Raising concurrency does not boost throughput | Saturated database/API or too few active FIFO groups | Measure dependency latency and active group count |
| Queue backlog grows while listener is running | Poll errors, starved thread pool, slow listener, or IAM/network errors | Check poll logs, executor, visible/in-flight metrics, and CloudWatch |
| Excessive empty receives | `FIXED_HIGH_THROUGHPUT` on an empty queue or unsuitable poll mode | Try `AUTO` and monitor empty receive cost |
| Executor queue grows continuously | Listener offloads to an unbounded executor or undersized pool | Use a bounded queue, cap concurrency, and return the work future |
| Messages reprocessed during shutdown | Process killed before acknowledgment or listener exceeded timeout | Set realistic shutdown budgets, visibility, and idempotency |
| Low FIFO throughput despite high concurrency | All messages share one group ID | Partition group IDs by independent aggregates needing concurrency |
| In-flight count exceeds `maxConcurrentMessages` | Acknowledgment batching released permits before SQS delete completed | Monitor ack queue and tune interval/threshold/visibility |

## 21. Hands-On Exercises

**Exercise 1 — Basic batching:** Create a listener taking `List<OrderEvent>`, send 25 messages, and set `maxMessagesPerPoll = 10`. Observe listener invocation counts and items per batch.

**Exercise 2 — Larger batch:** Set `maxMessagesPerPoll = 25` and send 25 messages rapidly. Verify the container combines results across multiple polls into the batch listener.

**Exercise 3 — Concurrency:** Test `maxConcurrentMessages` values of 5, 10, and 20. Record throughput, p95 processing duration, and database load.

**Exercise 4 — Backpressure:** Compare `AUTO`, `ALWAYS_POLL_MAX_MESSAGES`, and `FIXED_HIGH_THROUGHPUT` under burst traffic followed by an empty queue. Measure empty receives and backlog drain time.

**Exercise 5 — Partial acknowledgment:** Build a batch listener with `MANUAL`, fail one item, and acknowledge only succeeded items. Observe the failed message being redelivered.

**Exercise 6 — FIFO grouping:** Send events across three `MessageGroupId`s, observing in-group ordering and cross-group concurrency. Test both `fifoBatchGroupingStrategy` options.

**Exercise 7 — Graceful shutdown:** Make a listener take 10 seconds and call stop while a message is running. Verify the container stops polling and completes acknowledgment within the timeout.

**Exercise 8 — Forced shutdown:** Lower `listenerShutdownTimeout` below processing duration. Observe the message redelivering after visibility timeout and verify idempotency.

**Exercise 9 — Kubernetes:** Configure a termination grace period longer than the sum of listener shutdown, acknowledgment shutdown, and cleanup budgets. Run a rolling update while the queue has a backlog.

## 22. Self-Check Questions

1. How is a batch listener enabled? **By an `@SqsListener` method accepting `List<Payload>` or `List<Message<Payload>>`.**
2. How many messages can a single SQS `ReceiveMessage` request return at most? **10 messages.**
3. What does `maxMessagesPerPoll` above 10 do? **Spring Cloud AWS combines results from multiple polls into a larger batch.**
4. What scope does `maxConcurrentMessages` apply to? **Per queue within a container.**
5. How does `AUTO` work? **Automatically switches between low and high throughput and allows partial polling based on available permits.**
6. What does `ALWAYS_POLL_MAX_MESSAGES` trade off? **Reduces small poll batches, at the cost of leaving freed slots idle while waiting for full permits.**
7. Why doesn't raising concurrency always increase FIFO throughput? **Messages in the same group must still process sequentially; only independent groups add parallelism.**
8. What is the default `listenerShutdownTimeout`? **20 seconds in Spring Cloud AWS 3.4.1.**
9. When does `acknowledgementShutdownTimeout` begin counting? **After listener processing finishes or times out.**
10. What can happen if a process is killed before acknowledgment? **The message can be redelivered after the visibility timeout; consumers must be idempotent.**

## 23. References

- [Spring Cloud AWS 3.4.1 — Batch Processing](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): batch listeners, `List<T>`, `maxMessagesPerPoll`, and multiple polls.
- [Spring Cloud AWS 3.4.1 — Message Processing Throughput](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): concurrency, polling, backpressure, and modes.
- [Spring Cloud AWS 3.4.1 — Container Lifecycle](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): start/stop, registry, and shutdown behavior.
- [Spring Cloud AWS 3.4.1 — SqsContainerOptionsBuilder API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/listener/SqsContainerOptionsBuilder.html): configuring queue/container options.
- [Spring Cloud AWS 3.4.1 — ContainerOptionsBuilder API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/listener/ContainerOptionsBuilder.html): concurrency, max messages, backpressure, and shutdown timeouts.
- [Spring Cloud AWS 3.4.1 — SqsListener API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/annotation/SqsListener.html): annotation properties, batch listeners, and concurrency.
- [Amazon SQS — ReceiveMessage API](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ReceiveMessage.html): per-request message limits and receive behavior.

**Key takeaway:** Batching lowers per-message overhead; concurrency caps simultaneous execution; backpressure paces polling to match available capacity; graceful shutdown lets in-flight work and acknowledgments finish before exit. Tune these four levers alongside visibility timeout, downstream limits, and consumer idempotency.
