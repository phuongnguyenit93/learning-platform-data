# Consumer Exceptions and Container Lifecycle in Spring Kafka

In Spring Kafka, an exception thrown inside a listener directly affects how the container handles records, commits offsets, retries, and continues polling. The container manages consumer threads, listener invocations, acknowledgments, error handlers, and the broker connection lifecycle. Understanding exceptions and lifecycle together is therefore essential to avoid losing records, duplicating processing, or halting consumers unexpectedly.

A fundamental principle: **the container only knows a listener succeeded when the listener invocation returns normally or an error is handled by the error handler per configured policy**. If code catches an exception and ignores it, the container usually treats that call as successful and proceeds with committing per acknowledgment mode. If you want Kafka to redeliver a record, the error must propagate to the error handling mechanism or be handled via an intentional recovery policy.

## 1. What Responsibilities Does the Container Handle?

Spring Kafka provides two commonly used listener container types:

- **KafkaMessageListenerContainer** manages a single Kafka consumer and processes records on one consumer thread.
- **ConcurrentMessageListenerContainer** manages multiple child KafkaMessageListenerContainers to increase concurrency. Each child has its own consumer and thread.

When an application uses @KafkaListener, Spring creates endpoints and registers their corresponding containers via KafkaListenerEndpointRegistry. Containers are usually created from a configured ConcurrentKafkaListenerContainerFactory or KafkaListenerContainerFactory.

Basic processing flow:

~~~text
Spring Application
      |
      v
KafkaListenerEndpointRegistry
      |
      v
Listener Container
      |
      +--> Create KafkaConsumer
      |
      +--> Subscribe / receive partition assignment
      |
      +--> poll()
      |
      +--> Deliver record to listener adapter
      |         |
      |         v
      |     @KafkaListener method
      |         |
      |         +--> returns normally
      |         |        |
      |         |        v
      |         |     acknowledgement / commit
      |         |
      |         +--> throws exception
      |                  |
      |                  v
      |             CommonErrorHandler
      |                  |
      |                  +--> retry / seek / recover / DLT
      |
      +--> next poll
      |
      v
Consumer closes when container stops
~~~

The container coordinates the consumer and listener; the Kafka broker stores records and offsets. The container does not automatically know whether a database update or HTTP call succeeded in business terms. If a listener calls external systems, the application must handle idempotency and transaction boundaries for those systems.

## 2. Listener Container Lifecycle

A container can be viewed across the following stages:

1. **Created and configured:** the factory applies consumer factory, listener, concurrency, acknowledgment mode, error handler, and container properties.
2. **Started:** the container creates consumers, registers with brokers, and joins the group or receives partition assignments.
3. **Running:** the consumer polls records, invokes the listener, handles acknowledgments, and keeps polling.
4. **Paused:** the container or consumer can pause per application request, rebalance, or operational conditions.
5. **Stopped:** the container stops accepting new work, finishes in-flight processing within the shutdown timeout, commits if policy permits, and closes consumers.
6. **Restarted:** the container can be started again; consumers rejoin the group and resume reading from committed offsets and group state.

Conceptual lifecycle:

~~~text
CREATED
   |
   | start()
   v
STARTING
   |
   | consumer ready
   v
RUNNING <------ resume()
   |  ^
   |  |
   |  +------ PAUSED
   |             ^
   |             |
   +---------- pause()
   |
   | stop()
   v
STOPPING
   |
   | consumer closed
   v
STOPPED
~~~

This state diagram explains behavior conceptually. Exact internal states and events depend on the Spring Kafka version and container type.

### How Is the Container Started?

Containers are managed by the Spring lifecycle. Depending on configuration, a listener container can start automatically with the application context or be started manually by the application. On an endpoint declared with @KafkaListener, set autoStartup=false to control when startup occurs.

~~~java
@Component
public class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            autoStartup = "false"
    )
    public void onOrder(OrderCreated event) {
        process(event);
    }

    private void process(OrderCreated event) {
        // Business processing.
    }
}
~~~

The endpoint's container is accessed via KafkaListenerEndpointRegistry:

~~~java
@Service
public class ListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

The ID in the registry must match the @KafkaListener id attribute. Never assume an annotation-created container is a bean you can inject directly by method name. The registry is the proper access point for annotation-registered endpoints.

### Controlled Container Shutdown

Stopping a consumer is part of normal operations, such as maintenance, deploying a new release, or temporarily halting processing. Containers expose a stop method with a callback so the application knows when shutdown finishes:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.stop(() -> log.info("Orders listener stopped"));
}
~~~

The callback runs once the container has stopped. Applications can use it to coordinate the next step in shutdown or maintenance. Shutdown wait times should be finite; never keep an application alive indefinitely waiting on a hung listener.

If a listener is mid-record during shutdown, commit behavior and remaining work depend on acknowledgment mode, transactions, and container settings. Uncommitted records may be redelivered when the consumer group resumes. Therefore, listeners should have bounded execution times and be safe to recover upon restart.

## 3. How Do Listener Exceptions Propagate?

When a @KafkaListener method throws an exception, the exception travels from the listener adapter to the container. The container delegates the error to the configured CommonErrorHandler. The error handler decides whether to retry, seek offsets, recover the record, send to a DLT, or terminate processing per policy.

~~~text
KafkaConsumer.poll()
       |
       v
Listener adapter
       |
       v
@KafkaListener
       |
       +--> processing completes
       |       |
       |       v
       |   ack / commit per mode
       |
       +--> throw RuntimeException
               |
               v
        CommonErrorHandler
               |
               +--> retry listener
               |
               +--> seek to re-read
               |
               +--> recover / publish DLT
               |
               +--> exception continues propagating
~~~

Importantly, throwing an exception does not automatically mean the record will be re-read in every configuration. The error handler, acknowledgment mode, transactions, and recovery policy determine the final offset outcome.

### Do Not Accidentally Swallow Exceptions

The following example can forfeit retry opportunities:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Could not process order", ex);
        // Do not rethrow exception.
    }
}
~~~

The method returned normally from the container's perspective. The container may commit the offset per acknowledgment mode, even though business processing failed.

To let the container's error handler handle failures, let the exception propagate:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

If extra logging context is needed, log and rethrow the exception:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Order processing failed, orderId={}", event.id(), ex);
        throw ex;
    }
}
~~~

Catch and handle exceptions inside the listener only when the application genuinely intends to treat the record as processed or has already completed a dedicated recovery path. Merely logging an error is not recovery.

## 4. Classifying Errors to Decide Between Retry and Recovery

Not every error can be solved by retrying.

| Error Category | Examples | Typically Appropriate Action |
|---|---|---|
| Transient error | Temporary database disconnect, external service returns 503 | Retry with backoff and deadline |
| Data error | Missing required field, invalid value | Do not retry as-is; route to DLT or failed-review state |
| Configuration error | Wrong topic, wrong serializer, missing permissions | Fix configuration or permissions; alert operations |
| Time-dependent business error | Order not yet eligible because a dependency has not updated | Bounded retries or a dedicated waiting workflow |
| Programming bug | NullPointerException caused by a bug | Alert, bound retries, and retain record for investigation |

Retrying a deterministic failure will not make the error vanish. If a record carries an invalid payload, retrying hundreds of times merely inflates consumer lag and keeps the partition blocked longer.

Classify exceptions clearly and log event ID, topic, partition, offset, key, and root cause so operations can trace issues.

## 5. Configuring CommonErrorHandler and DefaultErrorHandler

Spring Kafka provides CommonErrorHandler for listener container error handling. DefaultErrorHandler is a common choice for record listeners: it supports retries, backoff, and recovery after attempts are exhausted.

Example factory configuration with two retries after the initial attempt:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    DefaultErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1000L, 2L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);

        handler.addNotRetryableExceptions(
                IllegalArgumentException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            DefaultErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.setConcurrency(3);

        return factory;
    }
}
~~~

The generic types of KafkaTemplate must match your application's actual ProducerFactory and serializers. The example uses Object to illustrate a template able to publish DLT payloads; in real projects, you can inject a template typed for your DLT payloads.

With FixedBackOff(1000L, 2L):

- The listener is called immediately on the first attempt.
- On failure, the error handler waits about one second and retries.
- Up to two additional retries occur after the initial call.
- Once retries are exhausted, the recoverer handles the record—in this example, publishing to a dead-letter topic.

Total listener invocations in this case are at most three if all attempts fail. Attempt counts and backoff must align with processing times, business deadlines, and dependency load tolerance.

### Marking Non-Retryable Errors

You can declare non-retryable exceptions via addNotRetryableExceptions. For instance, IllegalArgumentException typically represents invalid input data in this application. Classification must reflect the exception's meaning in your domain; the same exception class can mean different things across applications.

You can also classify retryable and non-retryable exceptions via DefaultErrorHandler's classification settings. Avoid overly broad rules that send transient faults straight to DLT or endlessly retry deterministic errors.

### Dead-Letter Topic

DeadLetterPublishingRecoverer sends unrecoverable records to a DLT. By default, the topic name is typically formed by appending .DLT to the source topic name; you can configure a custom destination resolver to override topic name or partition.

Example:

~~~text
orders
   |
   +--> listener fails
           |
           +--> retry with backoff
                    |
                    +--> succeeds: continue
                    |
                    +--> retries exhausted: orders.DLT
~~~

When routing DLT records to the same partition number as the source topic, the DLT topic needs at least as many partitions. Configure serializers properly for both the original record and exception/headers. Monitor the DLT and maintain processes for bug fixes, replays, or manual handling; publishing to a DLT does not mean business processing succeeded.

## 6. Blocking Retry, Retry Topics, and Partition Ordering

Spring Kafka supports multiple retry strategies.

### Blocking Retry with DefaultErrorHandler

Blocking retry keeps execution on the consumer thread until retries or recovery finish. Using seek mechanics, the failing record is re-read by offset; subsequent records in the partition must wait. This helps preserve strict ordering but can stall the partition during backoff intervals.

Use blocking retry when errors are brief, retry counts are small, and preserving order is a priority.

### Non-Blocking Retry with @RetryableTopic

@RetryableTopic routes failing records to dedicated retry topics with separate wait durations, then forwards them to the listener after the delay. This lets the consumer keep processing other records in the main topic, though it can alter business-observed ordering.

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1000,
                multiplier = 2.0,
                maxDelay = 10000
        ),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

This example illustrates four total attempts per retry-topic configuration. Verify the exact semantics of attempts and options for your Spring Kafka version. Non-blocking retry has limitations with container transactions and certain listener types; check version documentation before combining them.

Never configure multiple retry mechanisms simultaneously without accounting for total attempts. For example, if a listener has four retry-topic attempts and each attempt also triggers three blocking retries, total executions can be much larger than expected.

### Choosing by Ordering Requirements

| Requirement | Approach |
|---|---|
| Strict ordering within a partition | Blocking retry with short, bounded backoff |
| Allow subsequent records to proceed while failed record waits | Retry topics, accepting possible reordering |
| Deterministic data errors | Early recovery/DLT |
| Dependency typically recovers in seconds | Short blocking retry or retry topics within deadline |
| Dependency may be down for hours | Persist state durably and use a long-term retry workflow; never block consumer threads |

## 7. Acknowledgment Mode and Offset Commits on Listener Errors

Acknowledgment mode determines when the container commits offsets. It directly affects whether records are re-read after exceptions.

| Ack mode | High-Level Behavior | Impact When Listener Fails |
|---|---|---|
| RECORD | Commits after the listener successfully processes each record | Failing record is handled by error handler; offset depends on recovery |
| BATCH | Commits after processing the entire batch returned from poll | Failure inside batch affects commit and remaining records per handler |
| MANUAL | Listener calls acknowledge; container commits per batch semantics | Application must explicitly coordinate acknowledge timing and error handling |
| MANUAL_IMMEDIATE | Acknowledge on consumer thread can commit immediately | Committing before business work finishes can lose redelivery |

For record listeners, RECORD is straightforward when committing after every record. BATCH can be more efficient, though multiple records from a poll share one commit unit.

If a listener throws an exception before acknowledging, the error handler can retry or recover. If the listener acknowledges first and throws afterward, the offset may already be committed depending on mode and execution thread. Therefore, never acknowledge before protected work has completed.

Example configuration in record mode:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
      concurrency: 3
~~~

Spring Kafka listener containers typically manage commits and disable auto commit via container defaults. Confirm effective consumer configuration, especially when creating custom ConsumerFactory beans or modifying listener container factories.

### Batch Listeners

With a batch listener, the method receives multiple records at once. One exception can mark the entire batch failed. When identifying which record failed is needed, use BatchListenerFailedException to pinpoint the failing record so DefaultErrorHandler can process preceding and subsequent records per batch policy.

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            orderService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Could not process order",
                    ex,
                    i
            );
        }
    }
}
~~~

Use this pattern only when the factory is configured for batch listeners. If a batch listener does not identify the failing record, the error handler may have to retry the whole batch or apply another policy, re-executing previously processed records. Business logic must still be idempotent.

## 8. Exceptions Inside Kafka Transactions

When a listener container uses a Kafka transaction manager, the container starts a transaction before invoking the listener. If the listener completes normally, the container adds offsets to the transaction and commits. If the listener throws an exception, the transaction rolls back/aborts and records can be re-read via recovery mechanics.

For transactional listeners, AfterRollbackProcessor handles records after rollback. Understand this mechanism when using transactions; never assume DefaultErrorHandler replaces every rollback/recovery behavior of a transactional container.

~~~text
Container starts Kafka transaction
          |
          v
       Listener
          |
          +--> success
          |       |
          |       v
          |   Send offset to transaction
          |       |
          |       v
          |   Commit transaction
          |
          +--> exception
                  |
                  v
              Abort transaction
                  |
                  v
          AfterRollbackProcessor
                  |
                  +--> redelivery
                  |
                  +--> recover / DLT
~~~

If the listener updates a database while a Kafka transaction is active, the database does not automatically join the Kafka transaction. Use an appropriate transaction manager or an inbox/outbox pattern with idempotency to avoid state divergence between the two systems.

## 9. Errors Occurring Before the Listener Is Invoked

Not every exception originates inside the @KafkaListener method. Some occur during polling, deserialization, message conversion, or consumer-broker interaction.

### Deserialization Exceptions

If a deserializer throws an exception, the listener may never receive a payload to process. Spring Kafka provides ErrorHandlingDeserializer to catch deserialization errors and place error details into record headers, allowing the container's error handler or recoverer to handle them.

Example configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Specific delegate settings depend on key/value types and producer serializers. For JSON, configure trusted packages/type mapping per security policy and data model. Never allow arbitrary class deserialization from untrusted data.

### Poll and Consumer Exceptions

Broker connection failures, coordinator errors, or rebalances can arise during polling or while the container manages consumers. Not all of these errors are handled identically to listener exceptions. The container has dedicated mechanisms for consumer and lifecycle errors; monitor logs, events, and metrics to separate poll errors, listener errors, and commit errors.

If a consumer stays unresponsive for a long time, inspect listener processing duration, poll interval, heartbeats, and rebalances. Mechanically raising timeouts can mask a hung listener and delay incident detection.

## 10. How Do KafkaListenerErrorHandler and CommonErrorHandler Differ?

Spring Kafka supports declaring error handlers at both the annotation level and container level. Both mechanisms serve different scopes.

**KafkaListenerErrorHandler** is attached to @KafkaListener via the errorHandler attribute. It handles exceptions at the listener endpoint level and can return a response or add logic for a specific listener.

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        errorHandler = "ordersListenerErrorHandler"
)
public OrderResult onOrder(OrderCreated event) {
    return orderService.process(event);
}

@Bean
KafkaListenerErrorHandler ordersListenerErrorHandler() {
    return (message, exception) -> {
        log.error("Listener endpoint failed: {}", message, exception);
        throw exception;
    };
}
~~~

In this example, the handler logs the error and rethrows it so the container continues processing via container error handling. If the handler returns normally and swallows the exception, the container may consider the listener call handled at the endpoint layer.

**CommonErrorHandler** is configured on the container and governs container-level error handling such as retry, seek, recovery, and DLT. This is where DefaultErrorHandler is typically placed for record/batch listeners.

Never use a listener error handler as a complete replacement for a container error handler when the goal is managing offsets and redelivery. Clarify where exceptions are handled and whether they still propagate to the container.

## 11. Managing Concurrency, Pause, and Resume

ConcurrentMessageListenerContainer can spawn multiple child containers to process multiple partitions simultaneously. Concurrency does not automatically equal useful thread count: the number of partitions assigned to the consumer group bounds achievable parallelism.

Example:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

If a topic has six partitions and concurrency is three, each consumer can receive roughly two partitions depending on assignment strategy. With only one partition, setting concurrency to ten will not create ten parallel processing streams for that partition.

Containers can pause and resume to throttle load:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.pause();
}

// After the dependency or system recovers:
if (container != null && container.isRunning()) {
    container.resume();
}
~~~

Pausing stops delivering new records to the listener via container mechanics while the consumer continues polling to keep group membership alive. This differs from stop, which closes the consumer and exits the running lifecycle. Use pause/resume for backpressure or brief maintenance; use stop when shutting down the container completely.

When pausing programmatically, define clear resume conditions and metrics to catch containers paused too long. Never pause indefinitely without alerting.

## 12. Monitoring Lifecycle via Container Events

Spring Kafka publishes application events to observe consumer and container lifecycles. Useful events include:

| Event | Meaning |
|---|---|
| ConsumerStartingEvent | Consumer is about to be created/started |
| ConsumerStartedEvent | Consumer has started |
| ConsumerFailedToStartEvent | Consumer failed to start |
| ConsumerStoppingEvent | Consumer is stopping |
| ConsumerStoppedEvent | Consumer has stopped; event includes stop reason |
| ListenerContainerIdleEvent | Container received no records during configured idle interval |
| NonResponsiveConsumerEvent | Consumer shows signs of unresponsiveness within monitoring window |
| ConsumerPausedEvent | Consumer/container paused |
| ConsumerResumedEvent | Consumer/container resumed |

Exact event names and payload details depend on the Spring Kafka version. Events are typically published from consumer/container threads; if an event listener runs slow work, it can impact the consumer thread. Keep handlers fast or offload heavy work to a separate executor.

You can listen to events with @EventListener:

~~~java
@Component
public class KafkaContainerMonitor {

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: reason={}",
                event.getReason()
        );
    }

    @EventListener
    public void onConsumerStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: {}", event.getSource());
    }
}
~~~

Event types and getters can vary across versions. Use the exact API of your deployed dependency. Lifecycle events complement monitoring; they do not replace consumer lag metrics, exception logs, and application health checks.

## 13. Common Operational Scenarios

### Listener Continuously Throws Exceptions

Inspect the root exception and determine whether it is a transient fault or a data error. For deterministic errors, classify as non-retryable or route to DLT early. For temporary dependency outages, apply bounded backoff and monitor consumer lag.

### Consumer Group Lag Spikes Rapidly

A single record stuck in long blocking retries can hold a partition and stall subsequent records. Check listener duration, backoff, retry counts, and dependency health. If reordering is acceptable, consider retry topics; if ordering is required, optimize processing and bound total retry time.

### Container Stops After an Exception

Check logs and ConsumerStoppedEvent for the stop reason. Distinguish listener exceptions from consumer initialization errors, authorization failures, deserialization faults, or lifecycle application errors. Verify whether the container is configured to auto-restart or requires operator/application intervention to start again.

### Records Appear Multiple Times

Check offset commit timing, acknowledgment mode, shutdown/rebalances, and failures occurring after business work completed. If the database committed before the offset committed, the record can be redelivered. Use event IDs and inbox/unique constraints to prevent duplicate effects.

### Consumer Fails to Stop During Deployment

Check listeners waiting on dependencies or blocking futures, shutdown timeouts, stop callbacks, and transaction timeouts. Never wait indefinitely; enforce deadlines and let uncommitted records be reprocessed after restart.

### Poison Pill Blocks Partition Progress

An undeserializable record or one that always fails can force consumers to retry the same position endlessly. Use ErrorHandlingDeserializer, error classification, and DLT to quarantine failing records while letting the partition advance per policy. Retain necessary payloads/headers for investigation.

## 14. Listener Container Operations Checklist

When deploying a Spring Kafka consumer, verify:

- Is the container started automatically or controlled via KafkaListenerEndpointRegistry?
- Does the listener let exceptions propagate to the error handler when retries are needed?
- Which exceptions are retryable and which route to recovery/DLT?
- Does DefaultErrorHandler have finite retry counts and backoff?
- Does the DLT have matching serializers, partitions, and a reprocessing workflow?
- Does Ack mode match record listener or batch listener semantics?
- Are offsets committed only after business work completes?
- Is the listener idempotent to tolerate redelivery after crashes or rebalances?
- If using transactions, are AfterRollbackProcessor and the transaction manager configured properly?
- Are deserialization exceptions handled via ErrorHandlingDeserializer?
- Does concurrency fit partition count and dependency capacity?
- Do pause/resume operations have clear conditions and alerts?
- Does shutdown have deadlines, callbacks, and safe handling for uncommitted records?
- Are lifecycle events, consumer lag, retry rates, DLT counts, and listener errors monitored?

## 15. Basic Consumer Configuration Template

The following example combines record acknowledgment, concurrency, and an error handler with finite retries:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      group-id: order-service
      auto-offset-reset: earliest
    listener:
      ack-mode: record
      concurrency: 3
      auto-startup: true
~~~

The factory and error handler can be configured in Java as shown earlier. Ensure the actual factory is wired to the endpoint. When using multiple factories, explicitly specify containerFactory on @KafkaListener.

A simple listener:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

If orderService.process throws an exception, the container delegates the error to DefaultErrorHandler. The handler retries per configured backoff; once retries are exhausted, the recoverer sends the record to the DLT. If DLT publishing succeeds and recovery is considered complete, the container may advance the offset per error handler policy. If recovery fails, the error may keep propagating and the record can be reprocessed.

In practice, pair container policies with database transactions, idempotency, and monitoring. The container manages Kafka consumption and consumer lifecycles; the application remains responsible for protecting business side effects across retries, redeliveries, shutdowns, and restarts.
