# RecordFilterStrategy

In a Kafka consumer, not every record read from a topic needs to enter business logic. For example, a Fulfillment system only processes confirmed orders, while draft events, test events, or cancelled statuses can be skipped. Spring Kafka provides **RecordFilterStrategy** to filter records before invoking the listener.

RecordFilterStrategy receives a Kafka ConsumerRecord and decides whether the record should be excluded from the listener flow. If the `filter(record)` method returns `true`, the record is discarded and the listener does not receive it. If it returns `false`, the record continues to the listener.

Filtering happens on the consumer side after Kafka has delivered the record to the client. Therefore, it helps avoid invoking listener logic for unnecessary records, but it is not a broker-side filtering mechanism and does not itself reduce the number of bytes the consumer has to fetch. When using a filter, you also need to understand how the offset of a discarded record is acknowledged, especially when the listener uses manual acknowledgment.

This lesson belongs to the **Filtering and interceptors** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to configure RecordFilterStrategy in Spring Kafka, design safe filtering conditions, and control offsets, retries, and observability.

## Learning Outcomes

After this lesson, you will be able to:

- Explain the role of RecordFilterStrategy in the listener container.
- Distinguish between `true` and `false` return values of `filter(record)`.
- Configure a filter on ConcurrentKafkaListenerContainerFactory.
- Filter by payload, key, header, and record metadata.
- Safely handle records with null values and tombstones.
- Understand the impact of filtering on AckMode, offsets, and `ackDiscarded`.
- Distinguish filtering from RecordInterceptor, validation, and broker-side filtering.
- Apply filters to record listeners and batch listeners.
- Understand the interaction between filtering, retry, error handlers, and DLT.
- Test retained records, discarded records, and properly committed offsets.

## 1. What problem does RecordFilterStrategy solve?

Suppose the `orders.created` topic receives many types of orders. Fulfillment only needs to process orders with the `CONFIRMED` status. If every record goes into the listener before checking the condition, the listener has to execute extra conditional branches and might mistakenly invoke business services.

RecordFilterStrategy places the decision to exclude records at the listener adapter layer:

~~~text
Kafka topic
    |
    v
Consumer poll
    |
    v
RecordFilterStrategy
    |
    +---- filter(record) = true ----> Discard
    |
    +---- filter(record) = false ---> @KafkaListener
~~~

Examples:

- Keep records with status CONFIRMED.
- Skip records with status DRAFT.
- Skip events whose `event_type` header is not in the set of types the listener handles.
- Skip records belonging to a tenant outside the consumer's scope.
- Skip tombstones if the business flow does not use tombstones to delete data.

A filter should reflect the consumer's record-selection rules. Business checks that may change system state, need to query a database, or need to return an error to the producer should usually be placed in a business service instead of a filter.

## 2. The RecordFilterStrategy contract

The `RecordFilterStrategy<K, V>` interface works with `ConsumerRecord<K, V>`. The `filter` method returns a boolean:

| Result | Meaning | Behavior |
|---|---|---|
| `true` | Record is filtered out | The listener does not receive this record. |
| `false` | Record is kept | The record continues to the listener. |

Simple example:

~~~java
RecordFilterStrategy<String, OrderCreatedEvent> strategy =
        record -> record.value() != null
                && record.value().status() == OrderStatus.CANCELLED;
~~~

In this example, records with the CANCELLED status are discarded; the remaining records are forwarded. Null conditions must be designed according to the data contract: a null value may be a valid tombstone, not necessarily a corrupted payload.

Do not invert the boolean meaning. A common mistake is reading `true` as "accept"; in reality, `true` means filter/discard.

## 3. Configuring RecordFilterStrategy in the listener container factory

Spring Kafka lets you attach a strategy to `ConcurrentKafkaListenerContainerFactory` using `setRecordFilterStrategy`.

Example factory filtering out cancelled orders:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
filteredOrderFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.setRecordFilterStrategy(record -> {
        OrderCreatedEvent event = record.value();

        return event != null
                && event.status() == OrderStatus.CANCELLED;
    });

    return factory;
}
~~~

Attach the factory to the listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "filteredOrderFactory"
)
public void consume(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

With this configuration, the listener only receives records not excluded by the strategy. If the application has multiple listener groups with different rules, create separate factories or configure the factory per endpoint to prevent an unintended filter from applying to another listener.

A filter belongs to the listener container, not to the topic. The same topic can be read by multiple consumer groups with different filtering strategies.

## 4. Filtering by payload

When the value has been deserialized into an event object, the filter can check a simple and stable business field.

~~~java
factory.setRecordFilterStrategy(record -> {
    OrderCreatedEvent event = record.value();

    if (event == null) {
        return true;
    }

    return event.status() != OrderStatus.CONFIRMED;
});
~~~

In this example, only CONFIRMED events are kept. Ensure the field used for filtering has a stable meaning and does not depend on external state that can change while the consumer is running.

Do not place database queries or HTTP calls inside a filter to decide whether to accept a record. The filter runs on the consumer processing path; a slow call increases poll processing duration, raises lag, and can affect consumer group membership.

If the filtering condition requires external data, consider moving the decision into the listener/service so you have clear retry, timeout, logging, and error handling.

## 5. Filtering by key

A Kafka key often represents an entity identifier or partition key. A filter can use the key to skip a group of records.

~~~java
Set<String> ignoredTenants = Set.of("tenant-test", "tenant-demo");

factory.setRecordFilterStrategy(record -> {
    String key = record.key();

    return key != null && ignoredTenants.contains(key);
});
~~~

The example above assumes the key itself is the tenant ID. If the key is an orderId or a composite key, do not treat the key directly as a tenant. Use the exact key structure published in the event contract.

Filtering by key does not change partition assignment. The consumer still fetches records from the partition containing that key; the filter only decides whether the record is passed to the listener.

## 6. Filtering by Kafka header

Some streams classify records using headers such as `event_type`, `event_version`, or `source_service`.

~~~java
private String headerText(Headers headers, String name) {
    Header header = headers.lastHeader(name);

    if (header == null || header.value() == null) {
        return null;
    }

    return new String(header.value(), StandardCharsets.UTF_8);
}

factory.setRecordFilterStrategy(record -> {
    String eventType = headerText(
            record.headers(),
            "event_type"
    );

    return !"OrderCreated".equals(eventType);
});
~~~

Kafka headers have `byte[]` values, so the encoding must be agreed upon between producer and consumer. If duplicate header names exist, `lastHeader` only returns the last value; when the contract allows multiple values, read all of them using `headers(name)`.

Headers are data sent by the producer. Do not use a custom header as proof of authorization or trusted origin unless verified by the system's security mechanisms.

## 7. Filtering by record metadata

ConsumerRecord provides metadata such as topic, partition, offset, timestamp, and key. These values can be used for technical rules, such as excluding a test partition or accepting only records from a specific topic in a shared factory.

~~~java
factory.setRecordFilterStrategy(record ->
        record.topic().equals("orders.created.replay")
                || record.partition() == 7
);
~~~

This example only illustrates how to access metadata. Filtering by a fixed partition is usually a sign that subscription or topic design should be revisited; it should not be used as a substitute for ACLs, routing, or consumer groups.

Offset can be used to control replay in testing environments or planned migrations. In production, a rule filtering by offset can skip business data if there is no clear documentation and approval.

## 8. Handling null values and tombstones

Kafka allows records with a null value. In a compacted topic, a record with a key and a null value is typically used as a tombstone to indicate deleting the corresponding key according to log compaction semantics.

A filter needs to distinguish between:

- A valid tombstone according to the topic contract.
- An unexpected null record value.
- A failed deserialization payload converted to null with an exception header by ErrorHandlingDeserializer.

For example, if the listener does not handle tombstones:

~~~java
factory.setRecordFilterStrategy(record -> record.value() == null);
~~~

However, if the topic uses tombstones to delete data in a projection, filtering out all null values will prevent the listener from receiving delete commands, and downstream data may remain stale or incorrect.

If you need to distinguish a valid null from a deserialization error, inspect the deserialization exception header rather than only checking `record.value() == null`. Deserialization errors should usually go through ErrorHandlingDeserializer and an error handler; a filter should not accidentally hide a poison pill.

## 9. Filters and offset commits

Filtered records do not enter the listener, but the consumer has already polled those records from Kafka. Therefore, the application needs to understand how progress for discarded records will be acknowledged.

With container-managed AckModes such as RECORD or BATCH, the container manages commits according to the mode's semantics after the adapter processes the record/batch. With manual acknowledgment, a normal listener must acknowledge after processing; for a filtered record, the listener is not invoked to acknowledge it manually.

Spring Kafka provides the `ackDiscarded` property so the adapter acknowledges discarded records. This property defaults to false and is especially useful when using manual acknowledgment.

Example:

~~~java
factory.setRecordFilterStrategy(
        record -> record.value() == null
);
factory.setAckDiscarded(true);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
~~~

When the adapter discards a record, `ackDiscarded=true` allows acknowledging the discarded record via the acknowledgment mechanism. Verify the exact AckMode and Spring Kafka version in use; test committed offsets to ensure records are not unexpectedly redelivered.

If you use manual ack without acknowledging discarded records, the offset may not advance as expected and records may be redelivered after a restart/rebalance. Conversely, enabling ackDiscarded means the application accepts skipping that record and advancing the offset past it. Enable it only when the filter rule genuinely permits discarding the record.

## 10. RecordFilterStrategy with AckModes

| AckMode | How the container acknowledges | Notes when filtering |
|---|---|---|
| RECORD | Commits after a record is processed successfully | Discarded records are handled through the adapter; verify offsets in an integration test. |
| BATCH | Commits after successfully processing the records from a poll | Understand behavior when part or all of a batch is filtered. |
| MANUAL | Listener calls acknowledge; commits according to manual semantics | Enable ackDiscarded if discarded records need to be acknowledged. |
| MANUAL_IMMEDIATE | Acknowledge on the consumer thread can commit immediately | ackDiscarded helps the adapter acknowledge discarded records. |

Do not enable `enable.auto.commit=true` if you want the listener container to manage offsets according to AckMode. Auto commit may commit offsets on a schedule independent of processing outcomes.

With MANUAL and MANUAL_IMMEDIATE, carefully review how the application invokes acknowledgment and configures ackDiscarded. Do not assume filtering automatically shares the exact same semantics as a listener that ran successfully.

## 11. Filtering with batch listeners

A batch listener receives multiple ConsumerRecords in a single invocation. Spring Kafka can apply RecordFilterStrategy to records in the batch to exclude unsuitable records before passing the remaining list to the listener.

Example batch listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch",
        containerFactory = "filteredBatchFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        batchOrderService.handle(record.value());
    }
}
~~~

If the filter excludes part of a batch, the listener should only receive the remaining records according to the adapter's semantics. If all records in the batch are excluded, the listener may not be invoked. Specific batch behavior and offset acknowledgment should be tested with the Spring Kafka version in use.

With a batch listener, do not assume an index in the post-filter list still corresponds to the index in the original batch. If you need to audit or identify discarded records, record metadata before the list is filtered or use a separate observability mechanism.

## 12. Distinguishing RecordFilterStrategy and RecordInterceptor

Both extension points run before or around the listener, but they serve different purposes.

| Criterion | RecordFilterStrategy | RecordInterceptor |
|---|---|---|
| Purpose | Decide whether to discard or pass the record to the listener | Observe or intervene on a record before/after the listener |
| Primary result | `true` discards, `false` keeps | Can return a modified record or null per the interceptor contract |
| Use case | Exclude events outside the processing scope | Attach context, log, inspect, lightly enrich, or trace |
| Discard offset | Has the ackDiscarded property for filtered records | Need to understand semantics when an interceptor drops a record |
| Suitability | Clear record-selection rules | Cross-cutting behavior around the listener |

If the goal is to decide whether a record belongs to the dataset the listener should receive, use RecordFilterStrategy. If you need to observe, enrich context, or intervene on a record during the listener lifecycle, consider RecordInterceptor.

Do not place the same record-exclusion rule in both a filter and an interceptor without a clear reason; doing so makes it difficult to trace why a listener did not receive a record.

## 13. Filtering does not replace business validation

Filtering is typically used for records outside the consumer's scope. Validation checks whether a record is valid to execute business logic.

Examples:

- A Notification consumer only accepts OrderCreated events and ignores InventoryReserved events: filtering by event type can be used.
- OrderCreated is missing a required orderId: this is invalid data and should go through validation/error handling and potentially a DLT.
- An order has already been cancelled yet an event still arrives: business state needs to be verified; it should not always be silently filtered out.

If a filter drops invalid data, the system can lose investigation capability and the producer will not know the data is wrong. For poison pills or incompatible schemas, use ErrorHandlingDeserializer and an appropriate error handler instead of trying to filter after deserialization.

## 14. Filtering is not broker-side filtering

RecordFilterStrategy runs on the consumer side after records are polled and deserialized. The Kafka broker does not execute the application's Java predicate to send only matching records.

This means:

- Filtered records still consume network and fetch capacity.
- The consumer still has to deserialize the key/value before the filter runs.
- Filtering reduces the number of times the listener and business service are called, not the amount of data stored in the topic.
- If multiple consumer groups need different subsets of records, each group can fetch the same stream and apply its own filter.
- If you need to reduce traffic or separate data ownership, consider separate topics, producer-side routing, or stream processing.

Do not use RecordFilterStrategy as a security mechanism to prevent a consumer from reading unauthorized data. Use ACLs, topic separation, and proper access permissions.

## 15. How filtering interacts with retry and DLT

Filtered records do not enter the listener, so the listener does not throw an exception for them. Therefore, listener retries and error handlers are not the mechanism for handling a record discarded by a filter.

If a filter strategy itself throws an exception, that is an error during filter processing, not a normal discard result. Keep filters simple, deterministic, and free of external dependency calls. If a filter fails due to a system error, allow the error to be observed and handled through the appropriate error path rather than returning true to silently discard the record.

Retry/DLT fits records that were delivered to the listener but failed processing, or deserialization errors recognized by the error handler. Filtering fits valid records that are outside the listener's scope.

An overly broad filter rule can drop important records without creating a DLT entry. Therefore, you should have metrics counting discarded records and log enough metadata for auditing.

## 16. Designing deterministic and safe filters

A good filter should be a simple decision function that repeats the same result for the same record.

Principles:

- Do not call a database, HTTP endpoint, or external service inside a filter.
- Do not mutate business state or produce side effects.
- Do not rely on the current time unless there is an explicit requirement.
- Handle null keys/values and missing headers.
- Use enums/constants instead of scattered string literals.
- Document filter rules and the reasons for discarding records.
- Emit metrics by reason category, avoiding labels with excessive cardinality.
- Version the header/payload contract that the filter relies on.

If a filter depends on runtime configuration, ensure all replicas receive the same configuration and that you can observe the active rule version. Changing a filter can change which records are processed and how the group's offset advances through data.

## 17. Observing filtered records

Because the listener is not invoked for discarded records, logging inside the listener cannot fully count excluded records. You should add metrics or logging inside the filter strategy or a controlled wrapper.

Useful information:

- Topic, partition, and offset.
- Event type or enum value used to make the decision.
- Filter reason.
- Consumer group or listener ID.
- Count of discarded records over time.
- Count of kept records.
- Discard ratio relative to total polled records.

Example:

~~~java
factory.setRecordFilterStrategy(record -> {
    OrderCreatedEvent event = record.value();

    boolean discard = event == null
            || event.status() == OrderStatus.CANCELLED;

    if (discard) {
        filteredCounter.increment();
        log.debug(
                "Discarding record topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset()
        );
    }

    return discard;
});
~~~

In production, avoid logging entire payloads or keys containing sensitive information. Use metrics with bounded labels; do not include individual orderId or customerId values as metric labels.

If the number of filtered records spikes suddenly, the producer may have changed the event contract, the filter configuration may be wrong, or a new event type may be getting dropped. Alert on abnormal discard rates rather than only absolute counts.

## 18. Testing RecordFilterStrategy

Testing should verify both listener behavior and group offsets after filtering.

| Scenario | What to verify |
|---|---|
| Kept record | Listener receives the record once according to delivery semantics. |
| Filtered record | Listener is not invoked for that record. |
| Null value/tombstone | Kept or discarded according to the topic contract. |
| Missing header | Filter applies the defined fallback without throwing unexpected errors. |
| Null key | Does not cause a NullPointerException. |
| Duplicate header names | Picks lastHeader or processes the entire list as intended. |
| Manual ack + ackDiscarded | Offset of discarded records advances according to the chosen policy. |
| Record listener | Filtering and commits work properly with AckMode.RECORD. |
| Batch listener | Verify partially filtered batches, empty batches, and offsets. |
| Retry/DLT | Kept records where the listener fails go to the error handler; filtered records are not mistaken for retries. |
| Multiple consumer groups | Each group applies its own filter without affecting other groups. |

For example, an integration test can send two records, one CONFIRMED and one CANCELLED. Verify that the listener receives only CONFIRMED; then use AdminClient to read committed offsets to check that the consumer group has advanced past the discarded record according to the configured AckMode and ackDiscarded.

Use EmbeddedKafka or Testcontainers to test a real listener container. Use Awaitility/latches with timeouts instead of a fixed Thread.sleep. When testing manual acknowledgment, test both ackDiscarded enabled and disabled separately.

## 19. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Inverting the filter boolean | Drops records that need processing or keeps unwanted ones | Remember true = discard, false = keep. |
| Not handling null values | NullPointerException or accidentally dropping tombstones | Define null behavior explicitly per contract. |
| Using a filter to query a database | Slows polling and dependency failures destabilize the filter | Move checks into the listener/service. |
| Assuming a filter reduces broker/network traffic | Consumer still fetches records | Use topics/routing/stream processing if traffic reduction is needed. |
| Using a filter to drop malformed payloads | Loses visibility of poison pills and leaves no DLT record | Use ErrorHandlingDeserializer and an error handler. |
| Manual ack while forgetting ackDiscarded | Offset of discarded records may not advance as expected | Configure and test ackDiscarded. |
| Filtering by header without checking encoding | Parse errors or wrong decisions | Standardize on UTF-8 and handle missing/duplicate headers. |
| Configuring a filter on a shared factory unintentionally | Other listeners lose records | Use separate factories per policy group. |
| Not measuring discarded record counts | Hard to detect bad filters or contract changes | Add counters and discard-rate alerts. |
| Using a filter instead of business validation | Skips data errors that need investigation | Distinguish out-of-scope events from invalid events. |

## 20. Comprehensive exercise: filtering OrderCreatedEvent

Build a Fulfillment consumer for the `orders.created` topic.

Requirements:

1. Create a dedicated `ConcurrentKafkaListenerContainerFactory` for Fulfillment.
2. Configure RecordFilterStrategy to keep only events with status CONFIRMED.
3. Skip CANCELLED and DRAFT events according to the described rules.
4. Handle null values and tombstones according to the topic contract.
5. Add filtering by the `event_type` header and test missing-header cases.
6. Create a listener using the configured factory.
7. Try both `AckMode.RECORD` and `AckMode.MANUAL_IMMEDIATE`.
8. Toggle `ackDiscarded` on/off and observe committed offsets.
9. Send records with null keys and duplicate header names.
10. Test a batch listener with part of a batch discarded and an entire batch discarded.
11. Send a kept record where the listener throws an exception to verify retry/DLT.
12. Count filtered records with a metric and log topic/partition/offset.
13. Run two consumer groups with different filters on the same topic.
14. Write an integration test verifying listener invocations, filter counts, and committed offsets.

The exercise is complete when you can prove which records are discarded, which records are delivered to the listener, that offsets advance properly according to AckMode, and that business errors still flow through retry/DLT instead of being hidden by the filter.

## 21. Learning order and completion criteria

| Stage | Core content | Self-check criteria |
|---|---|---|
| 1. Filter contract | RecordFilterStrategy boolean | Correctly explain true = discard, false = keep. |
| 2. Factory | setRecordFilterStrategy | Attach the filter to the right listener container. |
| 3. Predicate | Payload, key, header, metadata | Write conditions safe against nulls and encoding issues. |
| 4. Tombstone | Null value and compacted topic | Avoid accidentally dropping valid delete markers. |
| 5. Offset | AckMode and ackDiscarded | Verify offsets of discarded records are handled properly. |
| 6. Listener modes | Record and batch listeners | Test partial/empty batches. |
| 7. Extension points | Filter and interceptor | Pick the right mechanism for the goal. |
| 8. Error handling | Retry, DLT, and deserialization failure | Do not hide poison pills or business errors. |
| 9. Operations | Metrics and filter audit | Track discard rate and reasons. |
| 10. Testing | Integration tests and committed offsets | Prove filter behavior alongside offset progression. |

This lesson is complete when you can configure RecordFilterStrategy, write safe predicates, explain the effect of ackDiscarded on manual acknowledgment, and test offsets after records are discarded. You should also clearly distinguish filters from interceptors, validation, and broker-side filtering mechanisms.

RecordFilterStrategy helps ensure listeners only receive records within their processing scope. Because filtering runs after the consumer fetches and deserializes records, it primarily reduces work in the listener. Keep predicates simple, define offset semantics clearly, and monitor filtered record counts to ensure the filter does not silently drop important data.

