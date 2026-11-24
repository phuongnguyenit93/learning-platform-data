# Reading One or Multiple Records

## 1. Two ways to receive data in Spring Kafka

A Kafka consumer retrieves data by polling. A single poll can return multiple records across the partitions owned by that consumer. The Spring Kafka listener container receives the poll result, converts the data to the type requested by the listener, and invokes the method annotated with `@KafkaListener`.

At the application layer, Spring Kafka supports two primary processing styles:

- **Record listener:** each listener invocation receives one record. The container calls the method multiple times to process the records from a poll.
- **Batch listener:** each listener invocation receives a list of records fetched in one poll. The application processes the entire group of records in a single call.

~~~mermaid
flowchart TD
    A["Kafka broker"] --> B["Consumer poll"]
    B --> C["Spring Kafka listener container"]
    C --> D{"Listener mode"}
    D -->|Record| E["Invoke listener for each record"]
    D -->|Batch| F["Invoke listener with a batch"]
    E --> G["Business processing"]
    F --> G
    G --> H["Acknowledge / commit offset per ack mode"]
~~~

Both styles use Kafka's consumer groups, partition assignments, and offsets. The difference lies in how the container delivers data to the listener method and how the application organizes processing.

## 2. Reading one record at a time with a record listener

This is the simplest approach and typically fits when each event needs independent handling. A listener can receive the deserialized payload directly:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void handle(OrderCreatedEvent event) {
        orderService.createOrderProjection(event);
    }
}
~~~

In this example, the Kafka deserializer converts the value into `OrderCreatedEvent`; a message converter can also participate when the application uses the Spring Message model. The `handle` method focuses purely on business logic.

If record metadata is needed, accept `ConsumerRecord<K, V>` instead of only the payload:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-audit"
    )
    public void handle(ConsumerRecord<String, OrderCreatedEvent> record) {
        String key = record.key();
        OrderCreatedEvent event = record.value();

        log.info(
            "Received topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            key
        );

        auditService.record(event);
    }
}
~~~

`ConsumerRecord` provides both data and metadata:

| Member | Meaning |
|---|---|
| `topic()` | Name of the topic containing the record |
| `partition()` | Partition containing the record |
| `offset()` | Position of the record within the partition |
| `key()` | Key used for routing or identifying the record |
| `value()` | Payload after deserialization |
| `timestamp()` | Timestamp attached to the record |
| `headers()` | Headers accompanying the record |

Offsets are only meaningful within the scope of a single partition. Do not use an offset as a global business identifier; if you need to identify an event across deliveries and retries, include an `eventId` in the payload or metadata according to your application's convention.

### When to receive only the payload vs. ConsumerRecord?

Receive only the payload when the business logic needs event data and does not need Kafka metadata. This keeps the listener signature concise and easy to test.

Receive `ConsumerRecord` when you need to log topic, partition, and offset; read the key or headers; or investigate failures based on record position. Avoid passing `ConsumerRecord` deep into the domain model if business logic does not need to know Kafka details.

## 3. Reading multiple records with a batch listener

A batch listener receives a group of records per method invocation. This approach is useful when multiple events can be processed together, such as inserting multiple rows into a database, calling a bulk-capable API, or aggregating data to reduce repetitive processing overhead.

There are two ways to enable a batch listener in a Spring Boot application.

### Configuring batch mode via application.yml

With Spring Boot supporting the listener type property, you can set:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-batch-processor
      max-poll-records: 100
      enable-auto-commit: false
    listener:
      type: batch
~~~

`spring.kafka.listener.type: batch` instructs listener containers to auto-configure in batch mode. The `max-poll-records` property maps to the Kafka consumer `max.poll.records` setting, capping the maximum number of records returned in a single poll.

The listener can accept a list of payloads:

~~~java
import java.util.List;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-batch-processor"
    )
    public void handleBatch(
            @Payload List<OrderCreatedEvent> events) {

        orderService.createOrderProjections(events);
    }
}
~~~

Spring Kafka converts the payloads of the records in the batch into a list of `OrderCreatedEvent`. This is convenient when business logic only needs the event data.

### Using ConsumerRecord in a batch

If per-record metadata is needed, use a list of `ConsumerRecord`:

~~~java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchAuditListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-batch-audit"
    )
    public void handleBatch(
            List<ConsumerRecord<String, OrderCreatedEvent>> records) {

        for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
            log.info(
                "topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
            );

            auditService.record(record.value());
        }
    }
}
~~~

Use `List<ConsumerRecord<K, V>>` when each element needs its key, partition, offset, or headers. Use `List<V>` when you only need payloads and want a simpler method signature.

### Configuring batch mode via a listener container factory

In an application needing multiple listeners with different modes, you can create a dedicated `ConcurrentKafkaListenerContainerFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(
            new DefaultErrorHandler(new FixedBackOff(1000L, 2L))
        );
        return factory;
    }
}
~~~

Specify the factory on the listener that should consume in batches:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-processor",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(List<OrderCreatedEvent> events) {
    orderService.createOrderProjections(events);
}
~~~

This allows the same application to have both record-level listeners and batch listeners. Each listener must use a container factory matching its method parameter type.

Do not configure a listener as batch while declaring a method that accepts only a single payload, or vice versa. The listener parameter type and container mode must match.

## 4. How is batch size determined?

The batch received by a listener is typically the set of records returned from one poll of a single consumer. A batch can contain records from multiple partitions assigned to that consumer.

`max.poll.records` caps the maximum number of records a consumer returns in a single poll. For example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
~~~

This value does not mean the listener always receives a full 200 records every time. Actual batch size may be smaller due to available data volume, producer rate, number of assigned partitions, fetch limits, or poll timing.

Related settings:

| Property | Role |
|---|---|
| `max.poll.records` | Caps the number of records returned in a single poll |
| `max.poll.interval.ms` | Time limit between polls before the consumer is considered inactive in the group |
| `max.partition.fetch.bytes` | Caps fetched data for a single partition in one fetch |
| `fetch.max.bytes` | Caps total fetched data for a single request |
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate before returning a fetch |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy `fetch.min.bytes` |

Fetch size limits and record count limits are distinct mechanisms. `max.poll.records` limits the number of items the application receives from poll; fetch properties govern the byte volume returned by the broker. Large records can also make the actual batch smaller than expected.

When processing batches, ensure the time to process one poll does not exceed `max.poll.interval.ms`. If the listener takes too long to process a batch, the consumer may be evicted from the group and Kafka triggers a rebalance. You can lower `max.poll.records`, optimize bulk processing, increase the timeout appropriately, or tune consumer and partition counts.

Batch size and concurrency are two separate concepts. A batch is the number of records one consumer receives in a single poll; concurrency is the number of consumers the listener container creates to process in parallel. Each consumer has its own polls and batches, while the number of consumers with partitions to read remains bounded by the partitions assigned in the group.

## 5. Batches do not create global ordering across partitions

A batch can contain records coming from multiple partitions. Kafka guarantees ordering within each partition, but does not create a global order across partitions.

For example, a batch might contain:

| Position in illustrative list | Partition | Offset |
|---:|---|---:|
| 1 | P0 | 10 |
| 2 | P1 | 7 |
| 3 | P0 | 11 |
| 4 | P1 | 8 |

You can rely on the ordering of records within the same partition to process sequentially per key or business entity. Do not infer that a record on P0 always occurred before a record on P1 simply because it appeared earlier in the batch list.

If business logic requires preserving order for events of the same order, the producer should use `orderId` as the key so that order's events go into the same partition. The batch listener must still respect that ordering during processing.

## 6. Confirming offsets when reading single records or batches

Reading records and committing offsets are two separate steps. The Spring Kafka listener container manages commits based on `AckMode` and consumer configuration.

With a record listener, the container can confirm progress after each record if using `AckMode.RECORD`, or after processing all records from a poll if using `AckMode.BATCH`. `BATCH` is the common default for listener containers.

With a batch listener, the container treats the entire list as a single invocation. When the listener completes normally, the container confirms the batch's offsets according to the configured ack mode. `AckMode.RECORD` is not suitable for a batch listener because the method receives the whole batch as a single unit of work.

If manual acknowledgment is enabled, the listener accepts an `Acknowledgment` parameter and calls `acknowledge()` only after the application completes work according to the chosen policy:

~~~java
import java.util.List;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderBatchListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-manual-batch",
        containerFactory = "manualBatchFactory"
    )
    public void handle(
            List<OrderCreatedEvent> events,
            Acknowledgment acknowledgment) {

        orderService.createOrderProjections(events);
        acknowledgment.acknowledge();
    }
}
~~~

The `manualBatchFactory` factory must be configured with batch mode and ack mode `MANUAL` or `MANUAL_IMMEDIATE`. Acknowledge only after business operations have completed. If offsets are committed before saving data or finishing processing, errors can cause records to be skipped when the consumer continues.
You can declare a dedicated factory for this listener (placing it with the imports and beans in the configuration class from the previous example):

~~~java
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        manualBatchFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
    return factory;
}
~~~

Manual acknowledgment does not automatically create a distributed transaction with the database. If you need to synchronize database writes and Kafka progress, design appropriate transactions or use the outbox/inbox pattern depending on data direction.

## 7. Error handling in a batch listener

With a record listener, a failure is typically tied to processing a single record. With a batch listener, a single invocation can process many records, so you must define how to handle cases where one element in the batch fails.

The simplest approach is letting the exception propagate out of the listener. The container's error handler applies the configured error policy. Depending on the error handler and ack mode, the batch may be retried as a unit, causing previously succeeded records to be redelivered.

If you need to pinpoint the failing record's position, Spring Kafka supports `BatchListenerFailedException`. Combined with `DefaultErrorHandler`, the application can indicate the index of the failed record so the error handler handles the succeeded portion and remaining portion according to policy:

~~~java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-processor",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(
        List<ConsumerRecord<String, OrderCreatedEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.createOrderProjection(records.get(index).value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Failed to process record in batch",
                ex,
                index
            );
        }
    }
}
~~~

Exact behavior depends on `DefaultErrorHandler`, backoff, recoverer, and ack mode configuration. Test failure cases at the beginning, middle, and end of a batch to verify which records are retried, which are committed, and which are routed to recovery.

Because batches can be re-executed, business operations should be idempotent. If several records in a batch already wrote to the database successfully and then the batch fails, the next invocation may receive them again. Use an event ID and unique constraints in the database to prevent applying the same event multiple times.

## 8. Choosing a record listener or a batch listener?

| Criterion | Record listener | Batch listener |
|---|---|---|
| Invocation | Once per record | Once per list from a poll |
| Complexity | Simple, easy error isolation | Requires batch-level error and offset handling |
| Bulk optimization | Must collect manually or process per record | Can call bulk APIs or batch database writes |
| Metadata | Receives one `ConsumerRecord` | Receives a list of `ConsumerRecord` |
| Independent event handling | Well suited | May require iterating over the list manually |
| Processing time | Easy to bound per record | Must monitor total time for the whole batch |
| Partial failure handling | Error handler processes per record | Must identify failure index in batch for partial handling |

Choose a record listener when:

- Each event has its own logic and needs independent handling.
- You want per-record retry configuration or error observability.
- Processing a single record is fast enough and batching offers no clear benefit.

Choose a batch listener when:

- The target database or service supports batch writes/calls.
- Connection or round-trip overhead can be reduced via bulk operations.
- The application can process a list of records within the bounded time limit.
- Retry, commit, and duplicate-processing protection are clearly designed.

Batching does not automatically make a system faster. If business logic still has to process each record sequentially, the overhead of managing batches and partial errors can outweigh the gains. Measure throughput, latency, and resource usage before deciding.

## 9. Testing single-record and batch listeners

For a record listener, tests should verify that each record produces the right business effect and that metadata is read properly if the listener uses `ConsumerRecord`.

For a batch listener, tests should verify:

- The listener receives a list of records and processes all elements.
- Batches smaller than `max.poll.records` are still processed normally.
- Batches containing records from multiple partitions do not break per-key logic.
- An error at a given index exhibits the configured retry/commit behavior.
- The consumer does not exceed `max.poll.interval.ms` with the expected batch size.

Embedded Kafka or Testcontainers can be used for integration testing. Send several records to a topic, use a dedicated consumer group for the test, and wait until the listener processes the expected count. Use Awaitility or a timeout-based wait instead of fixed `Thread.sleep()`.

Do not assert that a batch will always have the exact configured record count. The producer may have flushed only part of the data, the consumer may poll before remaining records arrive, and the broker also enforces fetch limits. Tests should verify behavior across varying batch sizes.

## 10. Implementation checklist

- [ ] Choose record listener or batch listener based on business processing style.
- [ ] Listener parameter type matches the container mode.
- [ ] Serializers/deserializers are compatible with the payload.
- [ ] Use `ConsumerRecord` when Kafka metadata is needed; accept only the payload when metadata is unnecessary.
- [ ] Set `max.poll.records` based on actual throughput and processing time.
- [ ] Ensure batch processing stays within `max.poll.interval.ms`.
- [ ] Understand that a batch may span multiple partitions and has no global ordering.
- [ ] Choose an appropriate ack mode and commit policy.
- [ ] Configure an error handler and partial-failure handling when using batches.
- [ ] Design idempotency to tolerate redelivered records.
- [ ] Test varying batch sizes and failures at different positions.

In Spring Kafka, record listeners make per-event processing straightforward, while batch listeners let the application process a group of records in one call to leverage bulk operations. Understanding how polling forms batches, how offsets are confirmed, and how error handlers process failures will help you choose the right consumption model for each messaging stream.
