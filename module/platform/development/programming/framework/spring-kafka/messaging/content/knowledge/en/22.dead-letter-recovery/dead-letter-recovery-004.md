# Determining the Target Partition

When Spring Kafka routes a failed record to a Dead Letter Topic (DLT), the system must decide two things: the target topic and the target partition. `DeadLetterPublishingRecoverer` performs the publishing of the recovered record; the destination resolver decides where the failed record is sent.

The target partition affects how failed records are distributed, whether alignment with the source partition is preserved, read ordering within the DLT, and the processing capacity of dedicated consumers. Choosing the partition with the same index as the source partition is a common default, but it is only safe when the DLT has enough corresponding partitions. If a DLT aggregates multiple topics or has a different partition count than the source, an explicit mapping rule must be designed.

This lesson belongs to the **Dead letter and recoverer** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-producing and consuming applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; as well as learning serialization, retry, dead-letter, transactions, exactly-once, concurrency, and testing to operate reliable messaging pipelines.

## 1. At Which Step Is the Target Partition Chosen?

When a listener fails to process a record and retries are exhausted or the error handler decides to recover, `DeadLetterPublishingRecoverer` creates a new record to send to the DLT. The new record has its own target topic and partition.

~~~mermaid
flowchart TD
    A[Record from source topic] --> B[Listener processing failed]
    B --> C[ErrorHandler retry]
    C --> D{Retries left?}
    D -->|Yes| B
    D -->|No| E[DeadLetterPublishingRecoverer]
    E --> F[Destination resolver]
    F --> G[Select DLT topic]
    F --> H[Select DLT partition]
    G --> I[Target ProducerRecord]
    H --> I
    I --> J[Kafka producer]
    J --> K[DLT partition]
~~~

The destination resolver is the component that determines the route. In Spring Kafka, the resolver can receive the source record and exception and return a `TopicPartition` containing the target topic name and target partition.

Choosing a target partition does not modify the partition or offset of the source record. The recoverer publishes a new record; the broker assigns a new offset within the DLT partition.

## 2. Default Destination Resolver

When creating `DeadLetterPublishingRecoverer` with a `KafkaTemplate` and no custom resolver, Spring Kafka uses a common default rule:

- The target topic name is the source topic plus the `.DLT` suffix.
- The target partition preserves the same index as the source partition.

Example:

~~~text
Source topic: order-events

order-events-0, offset 100  --> order-events.DLT-0
order-events-1, offset 250  --> order-events.DLT-1
order-events-2, offset 90   --> order-events.DLT-2
~~~

Configuration:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

With the default resolver, if a record came from partition 2, the recoverer sends it to partition 2 of `order-events.DLT`. The DLT must have the corresponding partition index; otherwise, publishing can fail.

The default approach is useful when each source topic has its own DLT and the DLT is created with at least as many partitions as the source topic. It keeps tracing and load distribution by source partition simple.

## 3. Why Does the DLT Partition Count Matter?

Suppose the source topic has 12 partitions, while the DLT only has 3 partitions. A record from source partition 8 cannot be published to partition 8 of the DLT because that partition does not exist.

If the resolver requests a specific partition, the partition index must lie within the actual partition range of the target topic:

\[
0 \leq p_{\text{target}} < P_{\text{DLT}}
\]

Where `P_DLT` is the partition count of the DLT topic.

| Source topic | DLT | Result when preserving partition |
| --- | --- | --- |
| 6 partitions | 6 partitions | Mapping 0→0 through 5→5 is valid. |
| 6 partitions | 10 partitions | Same-index mapping is valid; DLT partitions 6–9 are unused by this route. |
| 10 partitions | 4 partitions | Source partitions 4–9 have no matching-index target partition. |
| 1 partition | 1 partition | Mapping 0→0 is valid. |

When the DLT has fewer partitions than the source, you must pick another strategy: remap partitions, let the producer choose the partition, or split DLTs by source/error group with a matching topology.

Do not assume Kafka automatically wraps an out-of-range partition index into a valid partition. If you want remapping, implement it explicitly in the resolver.

## 4. Creating a Custom Resolver

`DeadLetterPublishingRecoverer` accepts a destination resolver. A resolver is typically a `BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>`.

Example preserving source topic plus suffix and source partition:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );

    return new DeadLetterPublishingRecoverer(dltTemplate, resolver);
}
~~~

This example reproduces the default rule while highlighting the customization hook. Given the same two inputs—record and exception—the resolver can choose a different topic or partition based on application policy.

Keep the resolver:

- Deterministic and repeatable: the same record and conditions should yield the same route.
- Fast: do not make remote service calls or database queries for every failed record.
- Topology-aware: the target partition must exist.
- Adequately logged/metered to explain routing decisions.
- Non-destructive to source metadata needed for investigation.

The resolver should not silently swallow misconfiguration errors. If a destination cannot be determined, recovery fails and the error handler must keep handling it per policy instead of committing the source record as successfully recovered.

## 5. Strategy 1: Preserve the Source Partition

This strategy fits when each source topic has its own DLT with a partition count greater than or equal to the source.

~~~text
order-events:
  P0 -> order-events.DLT P0
  P1 -> order-events.DLT P1
  P2 -> order-events.DLT P2
  P3 -> order-events.DLT P3
~~~

Pros:

- Easy to trace failed records back to the source partition.
- Easy to scale DLT consumer load across the same partition count.
- Failed records from the same source partition land in the same DLT partition.
- No separate partition-mapping calculation required.

Limitations:

- The DLT must maintain a matching topology.
- If a DLT aggregates multiple sources with different partition counts, preserving the index may not fit.
- Source partition does not imply topic-wide ordering; preserving the index does not establish ordering across different partitions.

This is usually the simplest choice for a one-DLT-per-source-topic model.

## 6. Strategy 2: Modulo Mapping to a Smaller DLT

When you want a DLT with fewer partitions than the source topic, you can map the source partition onto a target partition using modulo:

\[
p_{\text{target}} = p_{\text{source}} \bmod P_{\text{DLT}}
\]

For example, a source topic with 12 partitions and a DLT with 4 partitions:

~~~text
Source P0, P4, P8   -> DLT P0
Source P1, P5, P9   -> DLT P1
Source P2, P6, P10  -> DLT P2
Source P3, P7, P11  -> DLT P3
~~~

Illustrative resolver:

~~~java
private static final int DLT_PARTITIONS = 4;

private TopicPartition mapToSharedDlt(
        ConsumerRecord<?, ?> record) {

    int targetPartition = Math.floorMod(
        record.partition(),
        DLT_PARTITIONS
    );

    return new TopicPartition(
        "dead-letter-events",
        targetPartition
    );
}
~~~

Using `Math.floorMod` ensures a non-negative result even if an input partition index were negative due to a special code path; valid Kafka source partitions are already non-negative.

The advantage is fewer DLT partitions to operate. The drawback is that multiple source partitions funnel into one DLT partition, which can create hot partitions and increase error-processing latency.

Modulo is just a mapping rule. The DLT partition count must stay in sync with the resolver configuration; if you change the DLT partition count without updating the policy, routing can shift or become unbalanced.

## 7. Strategy 3: Let the Kafka Producer Choose the Partition

The resolver can specify the topic without pinning a specific partition. In Spring Kafka, returning a `TopicPartition` with a negative partition (commonly `-1`) indicates no partition is specified; the producer will choose the partition via its configured partitioner.

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("dead-letter-events", -1)
    );
}
~~~

When no partition is specified, the producer partitioner can use the serialized key. With a non-null key and the default partitioner, records with the same key typically go to the same partition within a fixed topology. With a null key, the producer may use sticky partitioning or the configured strategy.

Pros:

- No need to preserve source partition indices.
- Allows a centralized DLT with an independent partition count.
- Leverages the producer's partitioner and record keys.

Limitations:

- Does not guarantee the failed record lands on the same partition index as the source.
- Key-based mapping depends on the key serializer and partitioner.
- With a null key, there is no entity affinity.
- Changing the DLT partition count can alter key-to-partition mapping.

Use this strategy only when preserving the source partition is not an operational requirement. For tracing, the recoverer still adds source metadata in the DLT record's headers.

## 8. Strategy 4: Choose Partition by Error Type or Source

Because the resolver receives both the record and the exception, it can route by source topic, error type, or another controlled attribute.

Example splitting DLTs by error category:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) -> {
            String destination;

            if (exception instanceof InvalidEventException) {
                destination = "invalid-events.DLT";
            }
            else {
                destination = "processing-errors.DLT";
            }

            return new TopicPartition(destination, -1);
        }
    );
}
~~~

In this example, the negative partition instructs the producer to pick the target topic's partition. You can replace it with a specific partition index if DLT topologies are managed in lockstep.

You can also classify by source:

~~~java
private TopicPartition resolveDestination(
        ConsumerRecord<?, ?> record,
        Exception exception) {

    String destination = switch (record.topic()) {
        case "order-events" -> "order-errors.DLT";
        case "payment-events" -> "payment-errors.DLT";
        default -> "unclassified-errors.DLT";
    };

    return new TopicPartition(destination, -1);
}
~~~

Do not funnel every exception into a single topic if retention, access permissions, owners, or replay procedures differ across domains. Conversely, creating too many tiny DLTs adds topic management overhead. Choose boundaries around real ownership and recovery workflows.

The exception passed to the resolver may be a wrapper forwarded by the error handler, containing a cause chain with the deeper root cause. Do not rely solely on exception message strings because messages can change across versions or languages.

You can walk the cause chain:

~~~java
private boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
~~~

Then use the normalized exception type to select the destination:

~~~java
if (hasCause(exception, InvalidEventException.class)) {
    return new TopicPartition("invalid-events.DLT", -1);
}
return new TopicPartition("processing-errors.DLT", -1);
~~~

Do not classify errors by arbitrary class names from producer-controlled payloads or headers. Routing should rely on reviewed internal exception types and rules.

If multiple exceptions are wrapped by framework layers, test the actual cause chain. You may also need to distinguish `DeserializationException`, validation exceptions, or transient errors so infrastructure failures do not get mixed into a bad-data DLT.

## 10. Target Partition and Record Key

`DeadLetterPublishingRecoverer` normally preserves the source record's key and value when creating the DLT record, while adding headers describing the origin and exception. Consequently, the key can still participate in partition selection if the resolver leaves partition selection to the producer.

Distinguish the two mechanisms:

- Resolver specifies a concrete partition: the producer sends directly to that chosen partition.
- Resolver leaves the partition unspecified: the producer partitioner decides based on key/configuration.

If key deserialization fails, the key object value in the handled record may be null; raw key bytes are preserved in `ErrorHandlingDeserializer` error metadata. The DLT producer must have a serializer supporting raw `byte[]` to preserve the failed key upon publishing.

If the key is genuinely null, the partitioner cannot use the key for affinity. In that case, the producer distributes records via sticky partitioning or a custom partitioner.

Do not manually compute partitions using `record.key().hashCode()` in the resolver if you want to match Kafka's partitioner. Java object hash codes do not necessarily match hashes over serialized key bytes or the active partitioner algorithm.

## 11. Target Partition Is Not the Source Offset

When a record is published to a DLT, the Kafka broker assigns a new offset in the target partition. The new offset does not necessarily equal the source offset.

~~~text
Source:
  order-events-2, offset 1050

DLT:
  order-events.DLT-2, offset 87
~~~

The recoverer can add source headers such as topic, partition, offset, and consumer group for investigation. Therefore:

- `record.partition()` when a consumer reads the DLT is the target partition.
- The original partition header describes the source partition.
- `record.offset()` when reading the DLT is the new offset in the DLT.
- The original offset header describes the record's position in the source topic.

Do not use the DLT offset to infer the source offset. If exact replay is needed, read and preserve source metadata, and also check whether the source record was committed after recovery.

## 12. Centralized DLTs and Multiple Source Topics

A centralized DLT can receive failures from multiple topics:

~~~text
order-events-0 ─────┐
payment-events-3 ───┼──> dead-letter-events
inventory-events-1 ─┘
~~~

When multiple topics have different partition counts, you cannot blindly use the source partition index for every record if the DLT has fewer partitions than the largest source.

Options:

1. Give the DLT enough partitions to cover the highest source partition index across all sources.
2. Have the resolver map source partitions onto a smaller set of DLT partitions.
3. Have the resolver return an unspecified partition so the producer chooses by key/partitioner.
4. Separate DLTs by domain or source topic so each DLT has a fitting topology.

A centralized DLT lets one operations team handle errors in one place, but it can mix retention, ACLs, ownership, and consumption rates across domains. Evaluate whether one DLT truly needs identical storage and replay policies for all sources.

If the DLT consumer needs to know which source a record belongs to, use the metadata headers added by the recoverer and verify them in integration tests. Do not rely solely on the DLT name when multiple sources publish into one topic.

## 13. Creating and Managing DLT Topology

The DLT must be pre-created or managed via an environment-appropriate topic management mechanism. When designing topology, define:

- Partition count and replication factor.
- Retention time/size.
- Cleanup policy.
- ACLs for producers, consumers, and operations teams.
- Key/value schema/wire format.
- Header and record-size policies.
- Consumer groups processing the DLT.
- Replay or transformation procedures for failed records.

If preserving source partitions, the DLT partition count must cover every partition index the resolver may return. If the resolver returns partition `-1`, the DLT partition count still needs sufficient throughput and partitioner alignment; the producer chooses a valid partition, it does not create extra capacity.

Do not create a single-partition DLT purely for convenience when sources have many partitions and high error volume. A single DLT partition can become a bottleneck, especially if multiple topics send errors to it.

## 14. What Happens When Changing the DLT Partition Count?

If the resolver uses modulo mapping or the producer partitioner selects by key, changing the DLT partition count can alter routing for new records.

For example, scaling a DLT from 4 partitions to 8:

- With modulo, `sourcePartition % 4` and `sourcePartition % 8` can yield different results.
- With a key-based partitioner, hashing the key modulo the partition count can pick a different partition.
- Older records remain in their old partitions; new records may land in different partitions.

This does not alter previously stored data, but it can cause the same key to appear in multiple DLT partitions over time. If recovery relies on per-key ordering, evaluate the impact before expanding partitions.

Treat the DLT partition count as part of the operational contract. If it must change, record the timestamp of the change, verify the new mapping, and ensure recovery consumers do not assume a single fixed partition across all historical data.

## 15. Ordering in the DLT

Kafka guarantees ordering within each DLT partition by appended offset. However, routing failed records to a DLT does not create global ordering with the source topic.

Key points to keep in mind:

- Failed records from the same source partition may land in the same DLT partition if the resolver preserves partitions.
- Retry/backoff can cause an earlier failed record to be published to the DLT later than a subsequent failure.
- Multiple consumers or multiple source partitions can write into the same DLT partition.
- Resolvers that let the producer choose partitions by key can shift mappings if the partition count changes.
- DLT ordering reflects DLT publish order, not necessarily the original event order in the source topic.

If you need to replay in business order, use source metadata such as original topic/partition/offset along with an event ID or business sequence number. Do not rely on DLT offsets alone to reconstruct source ordering.

## 16. Customizing the Resolver and Logging Routes

The resolver should log routing decisions with sufficient metadata. For example:

~~~java
private TopicPartition resolve(
        ConsumerRecord<?, ?> record,
        Exception exception) {

    String targetTopic = record.topic() + ".DLT";
    int targetPartition = record.partition();

    log.warn(
        "Route failed record sourceTopic={} sourcePartition={} sourceOffset={} targetTopic={} targetPartition={} exception={}",
        record.topic(),
        record.partition(),
        record.offset(),
        targetTopic,
        targetPartition,
        exception.getClass().getSimpleName()
    );

    return new TopicPartition(targetTopic, targetPartition);
}
~~~

Do not log full payloads or sensitive keys. Route logging helps explain why a record went to a specific DLT and aids correlation with header metadata after publishing.

Resolvers should not perform side effects like writing to databases or making HTTP calls. If auditing is required, handle it in a component with explicit transaction/error handling; the resolver should focus on determining the destination.

If routing depends on runtime configuration, validate the configuration on application startup. Do not let a typo in a DLT name go unnoticed until the first failed record arrives.

## 17. Configuring the Recoverer with a Partition-Based Resolver

Complete example preserving the source partition:

~~~java
@Configuration
public class DeadLetterConfiguration {

    @Bean
    public DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> dltTemplate) {

        return new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> {
                String dltTopic = record.topic() + ".DLT";
                int dltPartition = record.partition();

                return new TopicPartition(
                    dltTopic,
                    dltPartition
                );
            }
        );
    }

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer deadLetterRecoverer) {

        return new DefaultErrorHandler(
            deadLetterRecoverer,
            new FixedBackOff(1_000L, 2L)
        );
    }
}
~~~

Attaching the error handler to the factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

This is an illustrative configuration for a record listener. For deserialization failures, the DLT template must also support raw bytes per `ErrorHandlingDeserializer` configuration. For batch listeners or transactions, test recovery semantics separately.

## 18. Testing the Destination Resolver

Do not merely test that the recoverer was invoked. Verify the exact target topic and partition.

Cases to test:

1. Source partition 0 routes to DLT partition 0 when preserving partitions.
2. The highest source partition still has a matching partition in the DLT.
3. Source partitions beyond the DLT range remap correctly when using modulo.
4. The resolver returns a negative partition so the producer chooses when policy allows.
5. Different exception types route to the right topics.
6. Multiple source topics route to their proper DLTs.
7. Failed keys and failed values retain raw bytes in the DLT.
8. Original topic/partition/offset headers reflect the source.
9. DLT publish failures do not mark the source record as recovered.
10. The DLT consumer reads records by partition and can trace back to the source.

Unit test example for the modulo rule:

~~~java
@Test
void shouldMapSourcePartitionToDltPartition() {
    ConsumerRecord<String, OrderEvent> record =
        new ConsumerRecord<>(
            "order-events",
            10,
            123L,
            "order-100",
            new OrderEvent("order-100")
        );

    int dltPartition = Math.floorMod(record.partition(), 4);

    assertThat(dltPartition).isEqualTo(2);
}
~~~

This test checks the pure mapping calculation. Integration tests should create source and DLT topics, send a real failing record, let the error handler recover, then read the DLT and verify the record actually landed in the expected target partition.

## 19. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| DLT publish reports non-existent partition | DLT has fewer partitions than source while resolver preserves index | Increase DLT partitions, remap, or let producer choose |
| All records pile into one DLT partition | Resolver hardcodes partition 0 or DLT only has one partition | Distribute by source partition/key and scale capacity |
| Records from multiple sources are mixed | Using a single centralized DLT | Use original topic metadata or split DLTs by domain |
| Same partition index is not preserved | Resolver uses negative partition or remaps | Review routing strategy and source metadata |
| Failed key is missing in DLT | DLT serializer does not support raw `byte[]` | Configure serializer for raw key/value bytes |
| Records with same key land in multiple DLT partitions | Partition count or partitioner changed | Stabilize topology and key serializer; check mapping history |
| Out-of-order replay | Relying on DLT offset instead of source metadata/sequence | Use original offset and business sequence |
| DLT publish fails yet source is skipped | Misconfigured recovery/commit semantics | Check recoverer result, error handler, and transactions |
| Routed to wrong topic | Incomplete resolver rules or config typo | Validate routes at startup and test each source |
| Slow resolver slows down recovery | Remote/database lookup inside resolver | Use local, deterministic rules and cached configuration |

## 20. Target Partition Selection Checklist

Before deploying a DLT, confirm:

1. Is the DLT dedicated per source topic or centralized across multiple sources?
2. Is the default resolver appropriate?
3. Does the DLT have enough partitions if preserving the source partition?
4. If the DLT has fewer partitions, use modulo or let the producer choose?
5. Are the mapping rules deterministic and tested?
6. Are the key serializer and partitioner compatible with key-based routing?
7. Are raw key/value bytes preserved on deserialization failures?
8. Are original topic/partition/offset headers kept for investigation?
9. Are DLT partition count, retention, replication, and ACLs provisioned?
10. Are hot partitions and DLT consumer lag monitored?
11. Will changing partition counts affect mapping and ordering?
12. Are there integration tests for publish success, publish failure, and replay?

The target partition is decided by `DeadLetterPublishingRecoverer`'s destination resolver. Preserving the source partition is easy to trace when the DLT has enough partitions; modulo packs many source partitions into a smaller DLT; a negative partition lets the producer choose via its partitioner and key. Understand that the new DLT partition/offset differs from source partition/offset metadata, and test topology and recovery before going to production.


