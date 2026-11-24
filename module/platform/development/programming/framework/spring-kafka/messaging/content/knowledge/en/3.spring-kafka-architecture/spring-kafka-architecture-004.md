# Message Listener Container

In Spring Kafka, the **message listener container** is the component that orchestrates receiving and delivering records from Kafka to the application's listener. The container manages the poll() loop, consumer, execution threads, offsets, acknowledgements, errors, rebalances, and runtime lifecycle. As a result, the listener can focus on business processing while the container handles most of the integration work with the Kafka Consumer API.

When using @KafkaListener, Spring Kafka creates a listener endpoint and uses a container factory to create the corresponding container. Understanding the relationship between listeners, factories, and containers helps you properly configure parallelism, offset commits, error handling, and safe application shutdown.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of the listener container in Spring Kafka architecture.
- Distinguish between KafkaMessageListenerContainer and ConcurrentMessageListenerContainer.
- Describe the poll, dispatch, record processing, and offset commit flow.
- Configure a container factory for record listeners, batch listeners, and concurrency levels.
- Choose an appropriate acknowledgement mode and understand its effect on delivery.
- Manage errors, retries, dead-letter handling, lifecycle, and consumer thread behavior.
- Recognize limitations related to partition assignment, max.poll.interval.ms, and concurrent processing.

## 1. How do a listener and a container differ?

The listener is the entry point invoking business code when records arrive. The container is the component that operates the consumer and invokes the listener. The container factory defines how containers are built for listener endpoints.

| Component | Responsibility |
|---|---|
| ConsumerFactory | Creates Kafka Consumers with bootstrap servers, deserializers, and consumer properties |
| Listener | Processes a record or batch of records according to business logic |
| Listener container | Runs the consumer loop, invokes the listener, manages acknowledgements, commits, errors, and rebalances |
| Listener container factory | Creates and configures containers for endpoints, typically declared with @KafkaListener |
| KafkaListenerEndpointRegistry | Manages containers created from annotation endpoints and provides lifecycle APIs |

General flow:

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["Listener container factory"]
    B --> C["Listener container"]
    C --> D["ConsumerFactory"]
    D --> E["Kafka Consumer"]
    E --> F["poll()"]
    F --> G["Invoke listener"]
    G --> H["Business processing"]
    H --> I["Acknowledgement / commit offset"]
    I --> F
    G --> J["Exception"]
    J --> K["CommonErrorHandler / recoverer"]
    K --> L["Retry, recover, or hold offset per configuration"]
    L --> F
~~~

The container does not replace the Kafka broker or consumer group. The broker still stores records, manages partitions, and coordinates group membership. The container controls the consumer inside the Spring application process and coordinates with the broker via the Kafka Consumer API.

## 2. Two Types of Listener Containers

Spring Kafka provides two primary container types.

### KafkaMessageListenerContainer

KafkaMessageListenerContainer operates a single Kafka Consumer on a single consumer thread. It is suitable when you need a single consumer, create containers manually, or want low-level lifecycle control.

A single container can be assigned multiple partitions by the broker. The consumer reads those partitions within the same poll loop; therefore, "one container" does not mean "one partition."

### ConcurrentMessageListenerContainer

ConcurrentMessageListenerContainer coordinates multiple child KafkaMessageListenerContainer instances. Each child container has its own consumer and thread. This is the common choice when you want to increase parallelism for @KafkaListener.

For example, configuring concurrency to 3 creates up to three child consumers for the listener endpoint:

~~~text
ConcurrentMessageListenerContainer
    |
    +-- KafkaMessageListenerContainer #1 -> Consumer thread 1
    |
    +-- KafkaMessageListenerContainer #2 -> Consumer thread 2
    |
    +-- KafkaMessageListenerContainer #3 -> Consumer thread 3
~~~

The broker distributes partitions among consumers in the same group. If a topic only has two partitions while concurrency is 3, at most two consumers can be assigned partitions; the remaining consumer has no partitions to read. Increasing concurrency beyond the number of partitions does not automatically increase throughput.

A single consumer can receive multiple partitions. Thus, the actual number of active consumers and number of partitions must be considered together, rather than assuming each consumer handles only one partition.

## 3. Creating Containers from @KafkaListener

In a Spring application, the common approach is to enable annotation support and declare a ConcurrentKafkaListenerContainerFactory.

Configuration example:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

The factory above defines:

- Consumers created from the ConsumerFactory configured with key/value deserializers.
- The container uses concurrency of 3.
- For a record listener, the container commits the offset after the listener finishes processing each record under AckMode.RECORD.

The listener can choose a factory by name:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerContainerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();

        orderService.process(event);
    }
}
~~~

If containerFactory is not specified, Spring Kafka uses the default factory named kafkaListenerContainerFactory if the application has declared it. In a Spring Boot application, auto-configuration may provide a default factory; when custom configuration is needed, name the factory clearly and reference it accurately from the annotation.

@KafkaListener declares the endpoint and listener method. The factory determines container configuration. The container is managed by the registry at runtime. These three pieces are related, but they are not the same object.

## 4. Record Processing Lifecycle

A container typically executes the following loop:

1. Initialize the consumer from ConsumerFactory.
2. Subscribe to topics or use the configured partition assignment.
3. Call poll() to retrieve available records.
4. Dispatch records to the listener as single records or batches.
5. Track processing results, acknowledgements, and errors.
6. Commit offsets according to the acknowledgement mode and active transaction.
7. Continue polling until the container is requested to stop.

A crucial point is that the listener is normally invoked on the container's consumer thread. While the listener runs synchronously, that consumer has not yet returned to poll() to fetch the next batch. If processing takes too long, the consumer can violate max.poll.interval.ms and be considered inactive in the consumer group.

The container is responsible for invoking the listener and coordinating commits, but does not automatically make side effects outside Kafka part of a Kafka transaction. If a listener writes to a database and then fails before the offset commits, the record may be redelivered; business processing must be idempotent.

## 5. Record Listeners and Batch Listeners

The container can deliver records to the listener one by one or deliver an entire batch retrieved from a single poll.

### Record listener

A record listener receives one record per invocation:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

This style fits when each event has its own processing flow, needs per-record error classification, or requires committing after every record.

### Batch listener

To use a batch listener, configure the factory with setBatchListener(true):

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchOrdersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

The listener receives a list of records:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrdersListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    orderService.processBatch(records);
}
~~~

A batch listener can reduce method invocation overhead and leverage batch processing in databases or target services. In return, the application must define how to handle cases where only one record in the batch fails. If processing the whole batch in a single database transaction, ensure that the transaction genuinely covers the changes that need to be atomic.

max.poll.records limits the number of records returned in a single poll. It is a consumer property; it affects batch size, not partition count or container concurrency.

## 6. Acknowledgement Modes and Offset Commits

The container tracks when records have been processed to commit offsets. Spring Kafka provides acknowledgement modes in ContainerProperties.AckMode.

| Mode | When commit happens |
|---|---|
| RECORD | After the listener finishes processing each record |
| BATCH | After processing all records in the batch returned from a poll |
| TIME | After a batch when the acknowledgement interval has elapsed |
| COUNT | After a batch when the count of processed records reaches the configured threshold |
| COUNT_TIME | After a batch when either the count or time threshold is reached |
| MANUAL | Listener calls acknowledge; container commits at batch boundaries |
| MANUAL_IMMEDIATE | Commits immediately when acknowledge is called on the consumer thread; if called from another thread, the acknowledgement is handled by the container mechanism |

For record listeners, RECORD is useful when you want offsets to advance after each record. BATCH usually reduces commit frequency, but if one record in the batch fails, retry and commit behavior must be understood together with the error handler.

Example of choosing BATCH:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.BATCH
);
~~~

### Manual acknowledgement

When business logic needs to explicitly decide when to acknowledge a record, use MANUAL or MANUAL_IMMEDIATE and accept Acknowledgment in the listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service-manual",
    containerFactory = "manualOrdersListenerContainerFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    acknowledgment.acknowledge();
}
~~~

The corresponding factory must be configured with a manual acknowledgement mode:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.MANUAL
);
~~~

Acknowledge only after the required work has completed. If the database commits successfully but the process stops before the Kafka offset is committed, the record may still be redelivered. Therefore, manual acknowledgement does not eliminate the need for idempotency.

Spring Kafka manages the container's offset commits; in modern versions, the container disables Kafka auto-commit by default unless the application explicitly configures otherwise. Avoid enabling enable.auto.commit when you want the container to control acknowledgements consistently.

When Kafka transactions are configured for the listener container, offsets can be sent into the transaction alongside Kafka output. In that case, treat acknowledgement, transaction manager, and listener container as a unified configuration; do not assume acknowledge() means an external database or API has committed.

## 7. Concurrency, Partitions, and Processing Order

Concurrency determines how many consumer threads a concurrent container can run. Partition assignment determines which partitions each consumer actually receives.

For example, a topic with six partitions and listener concurrency of three:

~~~text
Topic orders: P0  P1  P2  P3  P4  P5

Consumer 1:   P0  P1
Consumer 2:   P2  P3
Consumer 3:   P4  P5
~~~

This only illustrates one possible distribution; actual assignment depends on the partition assignor, the number of consumers in the group, and active members.

Key principles to remember:

- Concurrency greater than the number of partitions does not create extra parallelism for that topic.
- One consumer can process multiple partitions.
- Within a single consumer thread, the listener is invoked in the order of records received from poll; record ordering within each partition is preserved by Kafka via offsets.
- Different partitions have no global ordering across one another.
- If a listener hands work off to an executor or processes asynchronously, the completion order of side effects may differ from the received record order.
- With a concurrent container, the same listener bean can be called simultaneously by multiple threads; the bean must be stateless or ensure thread safety.

Choose concurrency based on partition count, processing resources, and average processing time. Setting concurrency too high can create extra threads and consumers without increasing throughput if partitions are insufficient or the target system is already saturated.

## 8. Keeping the Poll Loop Healthy

A Kafka consumer must call poll() regularly. A listener running synchronously for too long can cause the time between two polls to exceed max.poll.interval.ms. When that happens, the broker may evict the consumer from the group and rebalance partitions.

Parameters commonly evaluated together:

| Property | Meaning |
|---|---|
| max.poll.interval.ms | Maximum time between polls before the consumer is considered to have stopped making progress |
| max.poll.records | Maximum number of records returned in a single poll |
| session.timeout.ms | Time the broker waits for consumer heartbeats before considering the member lost |
| heartbeat.interval.ms | Heartbeat interval in the consumer group mechanism |
| pollTimeout | Time the container waits inside the poll call |

If a batch contains many records or a single record takes very long to process, evaluate total batch processing time against max.poll.interval.ms. You can lower max.poll.records, optimize the listener, or increase the interval appropriately after understanding its impact on rebalances. Do not merely raise timeouts to mask a hanging listener.

If work must be offloaded to another thread, explicitly design how ordering is preserved, how errors are propagated back to the container, and ensure acknowledgement happens only after side effects finish. Never use Kafka Consumer from arbitrary threads because Kafka Consumer is not thread-safe. Async acknowledgement mechanisms must be properly configured and understood since offsets may have to wait for earlier records to finish.

## 9. Error Handling in the Container

When a listener throws an exception, the container delegates the error to an error handler. The error handler decides whether to retry, skip, recover, or route the record elsewhere. In modern Spring Kafka versions, CommonErrorHandler is the unified error configuration point for both record listeners and batch listeners.

Example using DefaultErrorHandler with a dead-letter publisher:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersWithErrorHandlingContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                KafkaTemplate<String, OrderEvent> kafkaTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);

    factory.setCommonErrorHandler(
        new DefaultErrorHandler(recoverer, backOff)
    );

    return factory;
}
~~~

This example illustrates retrying with backoff and sending records to dead-letter when attempts are exhausted. Producer serializers must be configured appropriately for both original records and malformed records; if the DLT needs to preserve matching partitions, the target topic must have suitable partitions and the recoverer must be configured for that topology.

Points to keep in mind:

- Blocking retries in the listener container can hold a failing record at the head of the stream and delay subsequent records.
- The error handler may seek or manage offsets so records are redelivered; exact behavior depends on handler configuration and acknowledgement mode.
- Batch listeners have different error semantics from record listeners because a single invocation contains multiple records. If partial batch retries are needed, use an appropriate batch error handler mechanism and clearly track which records have already been processed.
- A DLT is a place to store failed records for investigation or replay; publishing to a DLT does not mean business processing succeeded.
- Handlers should distinguish between transient retryable errors and data errors that cannot be resolved by retrying.

## 10. Lifecycle and Controlling Containers

Containers have their own lifecycle: start, stop, pause, and resume. For listeners declared with @KafkaListener, KafkaListenerEndpointRegistry manages the containers created from endpoints.

Example of finding a container by the id declared in the annotation:

~~~java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

pause() and resume() are container control requests; the paused state takes effect within the consumer's poll loop. They are useful when you need to temporarily halt receiving more records for maintenance or load shedding. Monitor consumer lag while paused because producers may continue writing records to the topic.

Common lifecycle properties:

- autoStartup: determines whether the container starts automatically with the application context.
- id of @KafkaListener: identifies the endpoint so the registry can look up the right container.
- start() and stop(): control the container lifecycle.
- pause() and resume(): pause or resume receiving records.
- KafkaListenerEndpointRegistry: manages containers created from annotation endpoints.

Containers declared directly as beans and containers created from annotations have different lifecycle management. For annotation endpoints, use the registry to access the container rather than assuming it is always a standalone bean injectable by name.

During application shutdown, the container needs a chance to stop consumers and complete in-flight processing according to shutdown settings. Listeners should have bounded processing times, clear error handling, and never hold threads indefinitely.

## 11. Monitoring Container Status and Events

Containers can publish useful application events for operations, such as listener idle events when no records arrive within a configured duration. With a concurrent container, events may be emitted from each child container; when handling events, identify the exact listener/container that emitted the event.

Signals worth observing:

- Consumer lag by group and partition.
- Rebalance count and rebalance completion time.
- Counts of successfully processed records, failures, retries, and dead-letter records.
- Listener processing duration and time between polls.
- Number of active consumers compared to assigned partitions.
- Pause/resume state and periods when the container receives no records.

Idle does not necessarily indicate an error: the topic might simply have no new events. Conversely, a running container does not prove records are being processed successfully. Combine container status with lag, listener errors, and outcomes in the target system.

## 12. Choosing Configurations by Scenario

| Requirement | Configuration or mechanism | Notes |
|---|---|---|
| Process record-by-record and commit after each | Record listener + AckMode.RECORD | Fits when clear per-record processing boundaries are required |
| Process multiple records in batches | Batch listener + setBatchListener(true) | Requires designing error handling within batches |
| Increase consumers for an endpoint | Concurrent container + setConcurrency(n) | Bounded by the number of assigned partitions |
| Explicitly acknowledge after side effects | Manual acknowledgement | Handlers still need to be idempotent |
| Retry and send failed records to DLT | CommonErrorHandler, DefaultErrorHandler, recoverer | Configure serializers and DLT topology |
| Pause listener during maintenance | Look up container via registry then call pause()/resume() | Monitor lag while paused |
| Long-running listener | Tune batch size, poll interval, optimize handler | Avoid exceeding max.poll.interval.ms |

No single container configuration suits every listener. Choose according to requirements for ordering, latency, throughput, durability, listener style, and business processing time.

## 13. Common Design Pitfalls

**Setting concurrency higher than the partition count and expecting linear throughput gains.** Excess consumers receive no partition assignments. Check actual partition counts and consumer members before increasing concurrency.

**Running long work on the consumer thread.** The listener consumes time between polls, potentially exceeding max.poll.interval.ms and triggering rebalances. Keep processing duration bounded and tune batch/poll settings for real load.

**Using a listener bean with mutable state without synchronization.** A concurrent container may invoke the same bean from multiple threads. Use local variables, stateless services, or proper synchronization.

**Acknowledging before side effects finish.** If the offset is committed before a database write succeeds, records can be skipped after a failure. Acknowledge only after required work completes and make side effects idempotent.

**Assuming retries or DLT automatically guarantee zero data loss.** Retries can fail, DLT publishing can fail, or replay can re-apply stale events. Monitor, record event trails, and test recovery workflows.

**Offloading processing to an executor while committing offsets immediately.** Background work may not have finished when the offset commits. Acknowledge only after completion or use a controlled async acknowledgement design.

## 14. Pre-Production Listener Checklist

- [ ] Listener endpoints use the right container factory and consumer group.
- [ ] Record listener or batch listener is chosen to match business processing.
- [ ] Concurrency aligns with partition count and downstream system capacity.
- [ ] Acknowledgement mode reflects when side effects actually complete.
- [ ] max.poll.records and max.poll.interval.ms fit the processing time.
- [ ] Listener beans are safe when called concurrently by multiple consumer threads.
- [ ] Error handler, retry, backoff, and DLT behaviors have been tested.
- [ ] Containers have appropriate lifecycle settings and can be paused/resumed in operations.
- [ ] Metrics or alerts exist for lag, rebalances, errors, retries, and DLT.
- [ ] Side effects outside Kafka are idempotent to tolerate record redelivery.

## Conclusion

The message listener container is the runtime layer connecting Kafka Consumer with Spring listeners. The container orchestrates the poll loop, consumer threads, partition assignment, acknowledgements, offset commits, error handling, and lifecycle. KafkaMessageListenerContainer fits a single consumer; ConcurrentMessageListenerContainer creates multiple child consumers for parallel processing across partitions. When configuring containers, align concurrency, batch/record listener mode, acknowledgement mode, error handler, and poll intervals with business requirements. Listeners must still tolerate retries and duplicate processing, especially when side effects occur outside Kafka.

