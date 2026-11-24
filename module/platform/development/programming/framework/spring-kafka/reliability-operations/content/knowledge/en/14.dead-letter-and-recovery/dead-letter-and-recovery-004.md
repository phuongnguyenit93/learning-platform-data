# Selecting a DLT by Topic and Partition in Spring Kafka

In Spring Kafka, a **Dead Letter Topic (DLT)** is where records are stored when they cannot be processed successfully after retries or when they hit errors classified as non-retryable. When building a resilient Kafka system, you must decide not only *when* a record enters a DLT, but also **which DLT topic receives the record and which partition will hold it**.

A sound DLT routing choice must satisfy three goals at once: never lose unprocessed records, preserve enough context for investigation or replay, and avoid causing new incidents due to mismatched partition counts, serializers, ACLs, or processing order.

Spring Kafka provides DeadLetterPublishingRecoverer and a destination resolver to pick the TopicPartition for a failed record. With non-blocking retries based on @RetryableTopic or RetryTopicConfiguration, the framework also builds a retry/DLT topology and provides its own options for destination routing. These two mechanisms are related, but you should not assume they share the same naming rules or default settings.

## 1. Where does the DLT sit in the error-handling flow?

A consumer typically processes records along this path:

~~~text
Producer
   |
   v
orders.events (source topic)
   |
   v
Spring Kafka consumer
   |
   v
@KafkaListener
   |
   +--> succeeded
   |       |
   |       v
   |   Advance offset per ack mode
   |
   +--> exception
           |
           v
    DefaultErrorHandler
           |
           +--> retry with BackOff
           |        |
           |        +--> retry succeeded
           |
           +--> retries exhausted / non-retryable
                         |
                         v
             DeadLetterPublishingRecoverer
                         |
                         +--> Select destination topic
                         |
                         +--> Select destination partition
                         |
                         v
                   DLT record
~~~

When using DefaultErrorHandler, the recoverer is invoked once the error handler decides the record will no longer be retried on the source topic. If sending to the DLT succeeds and recovery is considered complete, the container can advance the offset according to its acknowledgement and error-handling policy. If sending to the DLT fails, do not treat the record as safely recovered.

**A DLT is not a sign of business success.** It is a storage point for data needing follow-up. Records in the DLT must have processes for monitoring, investigation, fixing the root cause, replay, or incident closure per operator decision.

## 2. Topic and partition serve different roles

In Kafka, a topic contains multiple partitions. A partition defines an ordered log with its own offsets. Each consumer within a consumer group is assigned partitions to read.

Example:

~~~text
orders.events
   |
   +--> partition 0: offset 100, 101, 102, ...
   +--> partition 1: offset 210, 211, 212, ...
   +--> partition 2: offset  80,  81,  82, ...

orders.events.DLT
   |
   +--> partition 0: offset  10,  11, ...
   +--> partition 1: offset   5,   6, ...
   +--> partition 2: offset  20,  21, ...
~~~

If a failed record comes from orders.events, partition 2, offset 81, we have two distinct coordinates:

- **Source:** orders.events / partition 2 / offset 81.
- **Destination:** e.g., orders.events.DLT / partition 2 / a new offset in the DLT.

The offset in the DLT **is not the source topic's offset**. Kafka assigns a new offset when appending the record to the DLT partition. When investigating, rely on source metadata in headers or an audit field; do not infer the source offset from the DLT offset.

A destination TopicPartition consists of a topic name and a partition number. This choice affects publish success, how DLT consumers are organized, ordering within the DLT, and the replay workflow.

## 3. Default behavior of DeadLetterPublishingRecoverer

In common DefaultErrorHandler setups, DeadLetterPublishingRecoverer defaults to building the destination topic name by appending **.DLT** to the source topic name, while picking the **same partition number** as the source record.

~~~text
Source topic                    Default DLT
-----------------------------   -----------------------------
orders.events / partition 0 -> orders.events.DLT / partition 0
orders.events / partition 1 -> orders.events.DLT / partition 1
orders.events / partition 2 -> orders.events.DLT / partition 2

payments.events / partition 3 -> payments.events.DLT / partition 3
~~~

Basic configuration:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

Here, FixedBackOff(1000, 2) allows two retry attempts after the initial processing attempt, spaced one second apart. Once retries are exhausted, the recoverer picks the DLT by default.

### Prerequisite when preserving the partition

If the DLT uses the **same partition number**, the DLT must have partitions matching every source partition that could be routed to it.

For example, the source topic has six partitions (0 through 5), while the DLT only has three partitions (0 through 2). When a failed record from source partition 5 is routed to partition 5, the producer cannot assume partition 5 exists on the DLT.

Some Spring Kafka versions include mechanisms to check or adjust the destination partition when the target partition does not exist, but you should not rely on implicit fallback behavior. Proactively provision the right partition count or select automatic partitioning and test on your running framework version.

Preserving the partition helps organize the DLT by source location, but it does not give the two logs shared offsets, nor does it create a transaction or an exactly-once guarantee between them.

## 4. Choosing the destination via BiFunction

DeadLetterPublishingRecoverer lets you supply a function accepting a ConsumerRecord and an Exception and returning a TopicPartition:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()
                    )
            );

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

The resolver receives two inputs:

- record: source topic, partition, offset, key, value, headers, and timestamp of the failed record.
- exception: the error passed by the error handler to the recoverer.

The resolver returns a TopicPartition representing the **destination to publish to**, not an instruction about consumer offsets. Destination selection logic should normally be pure, fast, observable, and free of HTTP/database calls on the consumer thread.

You can replace `record.topic() + ".DLT"` with a fixed name, a topic mapping table, or error-type rules. However, the destination topic must be a valid existing topic or one created through a designed administrative mechanism.

## 5. Choosing the partition: preserve it or let the producer pick?

This is a core decision when designing a DLT.

### Option A: preserve the source partition

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
)
~~~

Advantages:

- Easy to see which DLT partition corresponds to each source partition.
- Convenient for load partitioning or investigating by partition.
- Fits well when the DLT is provisioned with enough partitions and the partition layout does not change unexpectedly.

Trade-offs:

- The DLT must have at least the referenced partitions.
- When the source topic's partition count increases, the DLT configuration must be updated accordingly.
- If multiple source topics feed into one DLT, partition 2 from different topics converges into DLT partition 2; this does not establish global ordering.

### Option B: let the producer choose the partition

In DeadLetterPublishingRecoverer's destination resolver, return a **negative partition, typically -1**, to create a ProducerRecord with no specified partition; the Kafka producer chooses the destination partition using its partitioner/client logic and the key.

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        -1
)
~~~

Advantages:

- The DLT can have a different partition count from the source.
- Convenient when multiple source topics share one DLT.
- Lets Kafka distribute records based on the key or the active producer strategy.

Trade-offs:

- The DLT partition is no longer guaranteed to match the source partition.
- The DLT consumer must rely on header metadata to know the source partition.
- Distribution depends on the Kafka producer, serializer, key, and partitioning logic version; do not promise a specific partition.

**-1 does not mean writing to partition -1 on the broker.** It is a signal telling the recoverer not to force a destination partition when building the ProducerRecord. Kafka topics do not have negative partitions.

### Selection table

| Need | Typically suitable option |
|---|---|
| Dedicated DLT for one source topic with matching partitions | Preserve source partition |
| DLT has fewer partitions than source | Use -1 or design a valid mapping |
| Multiple source topics share one DLT | Usually choose -1 |
| Must recover per source partition | Preserve partition or store full metadata |
| Want DLT distributed by Kafka key | Use -1 with a stable key |
| Need exact control over destination partition numbers | Resolver returns valid partition, backed by tests |

## 6. Choosing a separate DLT per source topic

A common policy is giving each source topic its own DLT.

~~~text
orders.created  ------------> orders.created.DLT
orders.cancelled ------------> orders.cancelled.DLT
payments.events ------------> payments.events.DLT
notifications.email --------> notifications.email.DLT
~~~

Advantages:

- Separates access permissions by business domain.
- Retention and alerts can be tuned by criticality.
- Avoids mixing incompatible event payloads/serializers.
- Investigation and replay readily identify which stream produced the event.

Disadvantages:

- Increases the number of topics to administer.
- Each topic needs partitions, replication, ACLs, retention, and monitoring.
- Organizations with many small topics will need automated provisioning and ownership tracking.

Explicit resolver example:

~~~java
(record, exception) -> switch (record.topic()) {
    case "orders.created" ->
            new TopicPartition("orders.created.DLT", record.partition());

    case "payments.events" ->
            new TopicPartition("payments.events.DLT", record.partition());

    default ->
            new TopicPartition("platform.unknown.DLT", -1);
}
~~~

This example uses a Java switch expression. For older Java versions, use if/else or a Map. Unknown topic routing must be intentional: you can reject undeclared configurations or route them to a provisioned, monitored shared DLT.

Never take an arbitrary header from a record and treat it as the DLT name to publish to. Headers can be sent by untrusted producers; destination topics should come from an application-managed allowlist.

## 7. A single shared DLT for multiple source topics

In some systems, multiple flows sharing the same error-handling workflow can use a centralized DLT:

~~~text
orders.created -------+
orders.cancelled ------+--> platform.events.DLT
notifications.email ---+
~~~

Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltTemplate,
                (record, exception) -> new TopicPartition(
                        "platform.events.DLT",
                        -1
                )
        );
~~~

A shared DLT reduces topic count but introduces extra requirements:

1. The DLT consumer must identify the corresponding event type/schema.
2. The producer serializer must support multiple payload types.
3. The DLT needs sufficient partition count and throughput for the combined error volume.
4. ACLs and retention must meet the requirements of the most sensitive data routed to the DLT.
5. Monitoring must break down failures by source topic, not just the DLT topic.
6. Replay must route back to the right source topic using verified metadata.

If sharing a DLT across payloads of different Java classes, use appropriate serializers or standardize on an envelope. If deserialization failures carry raw bytes, handle `byte[]` explicitly instead of assuming every value is a domain object.

**Centralizing a topic does not mean centralizing business ownership.** Each event type still needs its own owner, SLA, and recovery workflow.

## 8. Routing by exception

You can select a DLT based not only on the source topic, but also on the error type.

Example:

~~~text
orders.events
    |
    +--> InvalidOrderEventException --> orders.invalid.DLT
    |
    +--> AuthorizationException ---> security.events.DLT
    |
    +--> Retryable error exhausted --> orders.failed.DLT
~~~

Illustrative resolver:

~~~java
@Bean
DefaultErrorHandler classifiedErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltTemplate,
                    (record, exception) -> {

                        Throwable root = exception;
                        while (root.getCause() != null
                                && root.getCause() != root) {
                            root = root.getCause();
                        }

                        if (root instanceof InvalidOrderEventException) {
                            return new TopicPartition(
                                    "orders.invalid.DLT", -1);
                        }

                        if (root instanceof UnauthorizedEventException) {
                            return new TopicPartition(
                                    "security.events.DLT", -1);
                        }

                        return new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()
                        );
                    }
            );

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(2_000L, 3L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class,
            UnauthorizedEventException.class
    );

    return handler;
}
~~~

The logic above uses the root cause to illustrate classification; in some projects, the meaningful domain exception sits in the middle of the cause chain rather than at the deepest cause. In that case, use a classifier with explicit rules rather than only comparing the root cause.

Selecting a DLT by exception is useful because:

- Stricter ACLs/retention can be placed on security errors.
- An invalid-payload DLT can be handed to the producer/schema team.
- Transient failures that exhausted retries can be tracked separately from permanent data errors.

The trade-off is more topics and operational workflows. If every exception class creates its own topic, topic counts can grow out of control. Usually it is better to group into a small finite set of error categories.

## 9. Topic mapping should be business-driven, not driven by arbitrary input

A common mistake is taking a tenantId, eventType, or producer-supplied string to construct the DLT name:

~~~java
// Avoid routing topics using an arbitrary string from the payload or header.
String target = "dlt." + tenantIdFromUntrustedEvent;
~~~

A buggy or malicious producer could generate unbounded topic names, exhausting broker metadata or routing data into topics lacking proper ACLs.

Instead:

- Manage the list of destination topics in configuration.
- Use an explicit mapping from source topics to DLTs.
- For multi-tenancy, group under bounded policies rather than arbitrary per-tenant topics.
- Verify the sender's authority before trusting control metadata.
- Never write sensitive data to a DLT with looser retention or ACLs than the source topic.
- Define a clear fallback policy for unsupported topics.

When multiple tenants share a DLT, ensure DLT readers cannot view data belonging to other tenants outside their authorized scope.

## 10. Complete DefaultErrorHandler and destination resolver configuration

The following example illustrates a combined topic and partition policy.

~~~java
@Configuration
public class KafkaFailureConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltTemplate,
                        (record, exception) -> {
                            String sourceTopic = record.topic();

                            if ("orders.events".equals(sourceTopic)) {
                                return new TopicPartition(
                                        "orders.events.DLT",
                                        record.partition()
                                );
                            }

                            if ("notifications.email".equals(sourceTopic)) {
                                return new TopicPartition(
                                        "notifications.email.DLT",
                                        -1
                                );
                            }

                            return new TopicPartition(
                                    "platform.general.DLT",
                                    -1
                            );
                        }
                );

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
~~~

This configuration illustrates these choices:

- orders.events keeps the same partition on its DLT.
- notifications.email lets the producer choose the DLT partition.
- Unmapped topics go to a general DLT.
- InvalidEventException does not wait through two retries.
- DefaultErrorHandler triggers recovery once retries are exhausted or on non-retryable errors.

OrderEvent, InvalidEventException, and serializer configuration belong to the application. If multiple listeners have different payload types, organize corresponding ConsumerFactory/ContainerFactory beans; do not assume one factory typed with OrderEvent can handle every topic.

**Important:** The code above only configures the recoverer; it does not automatically create the DLT topics, ACLs, or appropriate serializers. Those must be configured separately.

## 11. Provisioning DLT topics and controlling partition counts

If you decide to preserve the source partition, provision the DLT with matching partition counts from the start.

Example using KafkaAdmin and NewTopic:

~~~java
@Configuration
public class DltTopicConfiguration {

    @Bean
    NewTopic ordersDlt() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(6)
                .replicas(3)
                .build();
    }

    @Bean
    NewTopic notificationsDlt() {
        return TopicBuilder.name("notifications.email.DLT")
                .partitions(3)
                .replicas(3)
                .build();
    }
}
~~~

The numbers are illustrative. The cluster needs enough brokers for a replication factor of three. In production, provisioning may be handled via IaC or administrative tooling rather than auto-creating topics on application startup.

Watch for partition count changes on source topics. If orders.events increases from 6 to 12 partitions while orders.events.DLT still has 6 partitions, a partition-preserving resolver can select a non-existent destination.

Options to handle this:

- Increase the DLT's partition count before or together with the source.
- Choose -1 so the Kafka producer selects the destination partition.
- Use an explicitly designed valid mapping instead of assuming matching partitions.

Do not try to shrink a Kafka topic's partition count as an easy fix; Kafka does not support reducing partitions through normal operations.

## 12. Source metadata must be preserved

When a record moves to a DLT, recovery needs to know where it originated because the DLT offset differs from the source offset.

DeadLetterPublishingRecoverer can attach DLT headers related to the record and exception, such as:

- Original topic name.
- Original partition.
- Original offset.
- Original timestamp.
- Exception class.
- Exception message and stack trace per configuration/version.
- Consumer group details or additional metadata depending on version.

Spring Kafka uses framework-standardized header names, such as the KafkaHeaders.DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_PARTITION, and DLT_ORIGINAL_OFFSET group. Verify exact header names and extraction methods against your actual dependency.

A DLT record might have:

~~~text
Destination:
  topic       = orders.events.DLT
  partition   = 2
  offset      = 55

Original metadata:
  topic       = orders.events
  partition   = 2
  offset      = 1042
  eventId     = evt-812
  exception   = InvalidEventException
~~~

In the example, offset 55 is the position in the DLT; offset 1042 is the position in the source. When replaying, retrieve the source topic and event ID from verified metadata.

If using a shared DLT, preserving source metadata is operationally mandatory; without it, operators cannot easily tell which topic to route records back to.

## 13. DLT when deserialization fails

A record can fail before the listener receives a payload, such as malformed JSON or an invalid type header. When using ErrorHandlingDeserializer, Spring Kafka can store deserialization error info for the container's error handler and recoverer to process.

Example configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": com.example.events
~~~

For records that fail deserialization, the original value data may need to be emitted to the DLT as `byte[]` instead of a domain object. The DLT KafkaTemplate needs serializers capable of handling that type.

If using a single JSON template for all records, verify how it serializes `byte[]` and how the DLT consumer reads back the raw payload. You can use a type-delegating serializer or dedicated templates per key/value type.

The topic and partition resolver can still inspect ConsumerRecord metadata, but should not call domain getters on the value because the value may be null or not the expected object.

## 14. DLT and non-blocking retry topics have separate rules

Spring Kafka supports two common mechanisms:

**Blocking retry / recovery via DefaultErrorHandler**

- DeadLetterPublishingRecoverer can use a destination resolver.
- Default convention is usually sourceTopic + ".DLT" and the same partition.
- You can customize the DLT topic and partition via TopicPartition.

**Non-blocking retry via @RetryableTopic or RetryTopicConfiguration**

- The framework builds a topology of source, retry destinations, and DLT.
- Topic names may use suffixes like "-retry" or "-dlt" depending on configuration.
- DLT routing and reuse strategies are configured via the retry-topic APIs.
- Verify exception classification and DLT strategy support for your version.

Example annotation:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders.events", groupId = "orders-service")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

With this configuration, do not assume the DLT will be orders.events.DLT like DeadLetterPublishingRecoverer's default in blocking retry. Clearly distinguish the naming conventions of the two mechanisms.

In addition, non-blocking retries can alter processing order because failed records are moved to other topics; later records in the source topic may be processed first. Check batch listener or transactional container support for your Spring Kafka version.

## 15. Recovery success, DLT publish, and offset commit

When the source offset is committed determines whether a record can be redelivered after a crash. In a recovery flow, the application typically wants:

1. Listener fails.
2. Error handler retries per policy.
3. Recoverer publishes the record to the DLT.
4. Publish result is confirmed per required policy.
5. Container treats the source record as recovered and advances the offset per ack/error-handler mode.

If the producer used to publish to the DLT reports an error, the source record should not be marked recovered as though the DLT had safely stored it.

In real configurations, check:

- Whether the recoverer waits for the send result and how publish errors are propagated.
- Kafka producer properties such as acks, idempotence, and delivery.timeout.ms.
- AckMode and DefaultErrorHandler's options for committing recovered offsets.
- Behavior when the listener uses a Kafka transaction manager.
- The scenario where the source record is written to the DLT but crashes before the source offset commits.

**Duplicate DLT records can happen.** For example, DLT publishing succeeds, then the application stops before committing the source offset. When another consumer re-reads the source record, the recoverer may publish the same event again. DLT consumers or replay workflows need idempotency.

A DLT does not automatically provide end-to-end exactly-once guarantees for databases or external APIs.

## 16. Data ordering and DLT partition selection

Keeping the same partition number does not guarantee global ordering across the source topic and the DLT.

Example:

~~~text
orders.events / partition 1:
  offset 110: event A (failed -> DLT)
  offset 111: event B (succeeded)
  offset 112: event C (succeeded)

orders.events.DLT / partition 1:
  offset 20: event A

When the operator replays event A:
  B and C may already have been applied to business state.
~~~

If events A, B, and C are sequential updates to the same order, replaying A after B/C can produce corrupt state.

You need:

- Event IDs to prevent duplicate processing.
- Event versions or sequence numbers to detect stale data.
- State transition checks before applying updates.
- Reconciliation processes for critical side effects.
- Consider blocking retries when strict ordering is required and compensation is not possible.

Picking the same partition on the DLT aids traceability, but does not solve ordering between the source topic and the DLT.

## 17. Replaying from a DLT requires controlled reverse routing

A typical replay workflow includes:

~~~text
DLT topic
    |
    v
Operator / replay service
    |
    +--> inspect original error
    |
    +--> verify source topic and partition
    |
    +--> verify schema and payload
    |
    +--> verify replay permissions
    |
    v
Republish to source topic or recovery topic
    |
    v
Consumer processes with idempotency
~~~

If the DLT partition differs from the source partition because -1 was used, do not use the current DLT partition to decide replay routing. Read the source partition from metadata if the business case requires restoring the partition. Also verify the source topic is on an allowlist rather than blindly trusting a modified header or producer-controlled data.

Some systems replay to a separate topic and run a controlled consumer instead of writing back to the original production topic. This reduces the risk of creating a new DLT loop or disrupting ordering in the main stream.

Do not mass-replay merely because the DLT has a backlog. If the producer has not fixed the schema or the consumer has not fixed the bug, records will fail again and return to the DLT.

## 18. ACLs, retention, and separation of responsibilities

When selecting DLT topics/partitions, Kafka operations cannot be overlooked:

| Factor | Decisions needed |
|---|---|
| Topic ownership | Which team owns the DLT |
| Write ACL | Which principal the recoverer publishes as |
| Read ACL | Who may investigate and replay |
| Partition count | Based on destination mapping and throughput |
| Replication factor | Required durability level |
| Retention | Time needed for investigation and compliance rules |
| Encryption | Data protection in transit and at rest |
| Monitoring | Lag, publish errors, backlog, and oldest age |
| Serializer | Supports valid payloads and raw bytes |
| Replay | Approval, audit, idempotency, and ordering |

A DLT can contain failed payloads with sensitive data, tokens, or personal information. Do not log full payloads and do not open DLT ACLs wider than the source topic without valid justification.

A shared DLT across multiple domains can complicate retention and access control. When sensitivity varies widely, separate DLTs per domain/topic are usually easier to operate.

## 19. Common routing errors

### DLT lacks enough partitions

The source record is on partition 7 while the DLT only has partitions 0 through 3. If the resolver forces partition 7, publishing may fail or trigger version-dependent destination checks. Provision the DLT accordingly or use -1 so the producer selects the partition.

### Changing source topic partition count and forgetting the DLT

After expanding source partitions, a partition-preserving DLT configuration may become incompatible. Add partition count checks to topic-change procedures.

### Sharing one DLT with a serializer that does not support multiple schemas

The recoverer may route to the right topic while the producer fails to serialize the value. Use type-appropriate templates/serializers or standardize on an envelope while keeping type metadata.

### Selecting DLT topics from untrusted headers

A producer could control the destination topic name. Use an allowlist mapping on the consumer rather than creating arbitrary topics from payloads.

### Confusing DLT offsets with source offsets

Each topic/partition has an independent offset log. Use original-topic/partition/offset headers or audit metadata for replay and correlation.

### Confusing .DLT defaults with @RetryableTopic configuration

Retry-topic infrastructure has its own naming conventions and destination mapping. Read the configuration of the mechanism you actually use instead of applying one default rule everywhere.

### DLT publish fails yet the listener still advances the offset

Verify how the recoverer reports errors and the policy for committing recovered offsets. Recovery is only safe if the failed record was stored at the destination with the required acknowledgement.

### DLT backlog grows with no ownership

Configure alerts, assign an owning team, and define a replay workflow. Do not treat the DLT as an unmonitored dump.

## 20. System observability and troubleshooting

Measure across both source and DLT topics:

| Metric/signal | Meaning |
|---|---|
| DLT publish rate | Rate of records entering the DLT |
| DLT publish failure count | Recoverer failed while writing to DLT |
| DLT backlog/oldest age | Unprocessed record count and age of oldest record |
| Error count by exception type | Distinguishes data errors from infrastructure issues |
| Consumer retry count | Retry volume prior to recovery |
| Consumer lag by source partition | Partition stalled by failed records |
| DLT ingress by original topic | Which domain produces the most failures |
| Invalid destination partition | Detects invalid partition mapping |
| Recovery/replay duplicate count | Detects duplicate replays |
| End-to-end event age | Time from source record to completed recovery |

Specific metric names depend on the Kafka client, Spring Kafka, Micrometer, and exporter. Some signals must be emitted by the application, especially breakdowns by source topic, error code, and DLT destination.

Structured logs should include eventId, original topic, original partition, original offset, destination topic, destination partition, exception class, recovery status, and publish error if any. Avoid using eventId as an unbounded-cardinality metric label.

### Scenario: producer writing to DLT times out

A timeout does not necessarily prove the broker did not persist the record. Recovery may be retried and create duplicates. You need idempotency and correlation via event ID.

### Scenario: DLT reader cannot read JSON

Check class/type mapping, trusted packages, the serializer used to publish to the DLT, and raw `byte[]` data from deserialization failures.

### Scenario: same-partition DLT but replay is out of order

Preserving partitions only preserves traceability and distribution, not ordering relative to records already processed on the source topic. Use sequence/versioning or a controlled sequential replay workflow.

## 21. Workflow for choosing DLT topics and partitions

You can design your policy from these questions:

1. **Which domain owns the source topic?** Does the domain have specific data and retention requirements?
2. **Is a separate DLT needed per topic?** If different permissions or serializers are needed, split the DLT.
3. **Do errors need grouping?** Security violations, invalid payloads, and transient failures can have separate workflows.
4. **How many partitions does the DLT need?** If keeping the source partition, provision accordingly; if a shared DLT has a different size, use -1.
5. **Do you need to trace the original partition?** Store original-topic/partition/offset headers.
6. **Who can publish to and read from the DLT?** Grant least-privilege ACLs.
7. **How long is the DLT retained?** Set retention according to investigation SLAs and data sensitivity.
8. **Does the serializer accept raw bytes?** Check ErrorHandlingDeserializer and the template used for recovery.
9. **When is the source offset committed?** Verify behavior on both DLT publish success and failure.
10. **Where will replay go?** Source topic or dedicated recovery topic, with idempotency and audit?
11. **Will source partitions expand in the future?** Add topic topology checks to deployment pipelines.
12. **Is monitoring configured?** You need metrics for DLT destination, recovery failures, and backlog.

A practical policy for a service with few topics is typically **one DLT per source topic, preserving partitions if partition counts are managed in sync**. When using a shared DLT for multiple sources or differing partition counts, **letting the producer pick the partition via -1** is more flexible, paired with preserving source metadata and designing replay carefully.

## 22. Production readiness checklist

- DLT routing has an owner and clear rules per source topic.
- The resolver only returns topics from a provisioned allowlist.
- Every destination topic has a partition count compatible with the mapping.
- If preserving partitions, DLTs are updated whenever source partitions increase.
- If using -1, the system does not assume the DLT partition equals the source partition.
- DLT offsets are never confused with original offsets.
- DefaultErrorHandler and recoverer are registered on the right listener factory.
- KafkaTemplate has appropriate serializers, ACLs, and acks.
- Deserialization errors have a path to publish raw bytes to the DLT.
- Retryable/non-retryable exception classification is bounded.
- Failed DLT publishes are never treated as successful recovery.
- DLTs have suitable retention, replication, and quotas.
- Security-sensitive records are never routed to an unprotected DLT.
- DLT consumers/replay services run with least privilege.
- Replay checks schema, original topic, event ID, and idempotency.
- Ordering between source topic and DLT is handled via versioning or a dedicated workflow.
- Monitoring covers destination, publish failures, backlog, and record age.
- Tested with failed records on partitions higher than DLT, broker outages, crashes before commit, serializer errors, and duplicate replays.

Choosing a DLT by topic and partition is part of reliability design, not merely appending a suffix to a topic name. DeadLetterPublishingRecoverer lets you explicitly decide where to write; the rest of the system must ensure the destination exists, records are published safely, source metadata is preserved, and the DLT can be investigated and replayed properly.

