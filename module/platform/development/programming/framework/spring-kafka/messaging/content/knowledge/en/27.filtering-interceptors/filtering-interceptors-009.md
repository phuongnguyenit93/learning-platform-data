# Measuring Filtered Records

## 1. Why measure filtered records?

In a Spring Kafka consumer, not every record read needs to be forwarded to the listener. An application may skip duplicate events, expired events, out-of-scope event types, or payload versions unsupported by the consumer. `RecordFilterStrategy` lets you decide which records are excluded before invoking the listener.

If you only configure a filter without measuring metrics, the operations team does not know:

- How many records were examined and how many were filtered out?
- Were records excluded because of duplicates, expiration, or irrelevant event types?
- On which topic or listener is the filtered record rate spiking?
- Is the filter accidentally dropping valid events after a producer schema change?
- Did consumer lag drop because processing got faster or because the filter is dropping most data?
- Have discarded records had their offsets acknowledged/committed according to the intended policy?

Spring Kafka provides the `RecordFilterStrategy` hook to decide record exclusion, but does not define a built-in business counter for discarded records. The application should measure right at the filter boundary using Micrometer, then combine that with consumer lag, listener throughput, error rates, and logs to accurately understand behavior.

## 2. What does RecordFilterStrategy return?

`RecordFilterStrategy<K,V>` is invoked by the listener adapter before passing the record to the listener method. The `filter()` method returns a boolean:

- `true`: discard the record; the listener does not receive it.
- `false`: keep the record and forward it to the listener.

Example of a filter excluding expired events:

```java
@Component
public class ExpiredOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event != null && event.expired();
    }
}
```

A filter only decides whether the record is passed into the listener. It does not delete the record from the Kafka log, does not alter the payload, and does not automatically send the record to a DLT. The record remains in the partition until retention expires or it is removed per log compaction policy.

For record listeners, the filter is applied record by record. For batch listeners accepting `List<?>`, Spring Kafka has a batch adapter that filters record by record by default. Since Spring Kafka 2.8, you can override `filterBatch()` to evaluate the entire batch in one call.

## 3. Measuring examined and filtered records

A baseline metric set should include at least two counters:

| Metric | Meaning |
|---|---|
| `app.kafka.records.examined` | Number of records passing through the filter |
| `app.kafka.records.filtered` | Number of records the filter decided to exclude |

From these two counters you can calculate the filter ratio:

\[
\text{Filter ratio} = \frac{\text{filtered}}{\text{examined}} \times 100\%
\]

For example, if over a period 100,000 records pass through the filter and 8,000 records are excluded, the filter ratio is 8%. This ratio must be computed over the same time window and the same label set.

Counters should increase monotonically. Metrics systems like Prometheus can calculate growth rate with `rate()` and ratios by dividing two rates. Do not build a gauge by manually accumulating across invocations when a counter can be used.

These two counters measure **filter decisions**, not necessarily unique Kafka records. If a record is re-read after a restart, rebalance, or uncommitted offset, the same `topic-partition-offset` may pass through the filter multiple times and be counted multiple times. That is the right behavior if the goal is measuring how much work the filter performed. If you need unique record statistics, deduplicate by record identity or event ID in a separate storage system; do not turn metric counters into a deduplication state store.

## 4. Counting filtered records with Micrometer

The following example measures examined records and records excluded across a bounded set of reasons. The `topic` and `reason` tags have controlled value sets:

```java
@Component
public class OrderRecordFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Counter examined;
    private final MeterRegistry meterRegistry;

    public OrderRecordFilter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
        this.examined = Counter.builder("app.kafka.records.examined")
                .tag("topic", "orders")
                .register(meterRegistry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        examined.increment();

        String reason = discardReason(record);
        if (reason == null) {
            return false;
        }

        meterRegistry.counter(
                "app.kafka.records.filtered",
                "topic", record.topic(),
                "reason", reason).increment();

        return true;
    }

    private String discardReason(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        if (event == null) {
            return "tombstone";
        }
        if (event.expired()) {
            return "expired";
        }
        if (!event.supportedVersion()) {
            return "unsupported_version";
        }
        return null;
    }
}
```

In this example:

- `examined` increments once for every record the filter receives.
- `filtered` increments per exclusion reason.
- Kept records do not increment the `filtered` counter.
- The listener does not need to increment counters itself because the filter already measures at the exact decision point.

Do not use `eventId`, order ID, Kafka offset, correlation ID, or exception message as tags. Each distinct value creates a new time series and causes cardinality to explode. Those identifiers belong in logs or traces.

### Configuring the filter on the listener container factory

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            OrderRecordFilter orderRecordFilter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordFilterStrategy(orderRecordFilter);
        return factory;
    }
}
```

The listener only receives records that were not excluded:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

`setAckDiscarded(true)` explicitly expresses the acknowledgment policy for excluded records in supporting listener/acknowledgment adapters. Choose the value according to AckMode and redelivery requirements; offsets are explained in a dedicated section below.

Since Spring Kafka 2.8.4, an endpoint can override the factory's default strategy using the `filter` attribute on `@KafkaListener`:

```java
@KafkaListener(
        id = "orders-expired-filter",
        topics = "orders",
        groupId = "order-service",
        filter = "expiredOrderFilter")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

The value `expiredOrderFilter` is the `RecordFilterStrategy` bean name. This is useful when multiple listeners share a factory but have different filter policies.

## 5. Counting exclusion reasons without creating high cardinality

Metrics by reason help detect behavioral shifts. For example:

| Reason | Meaning |
|---|---|
| `duplicate` | Event ID was already processed previously |
| `expired` | Event is past its business expiration window |
| `unsupported_version` | Consumer does not support the event version |
| `irrelevant_type` | Event type does not belong to this listener |
| `tombstone` | Record has a null value and is filtered per policy |

Reasons must be an enum or fixed list. Do not use payload content as a reason, such as `invalid_customer_123`, because every record could generate a different tag.

If you want to measure multiple reasons, you can use an enum:

```java
enum FilterReason {
    DUPLICATE,
    EXPIRED,
    UNSUPPORTED_VERSION,
    IRRELEVANT_TYPE,
    TOMBSTONE
}
```

Then convert the enum to a stable string such as `duplicate` or `expired`. When adding a new reason, update dashboards and alerts accordingly.

Tombstones in a compacted topic usually signify deleting a key from a state store. Do not filter out tombstones generically if the consumer is building a state replica; skipping tombstones can leave stale data lingering in downstream systems.

## 6. Distinguishing filtered records, failed records, and recovered records

Do not lump every record that did not reach the listener into a single "dropped" metric. They have different causes and handling:

| State | Component typically measuring it | Meaning |
|---|---|---|
| Filtered/discarded | Counter inside `RecordFilterStrategy` | Filter proactively excluded the record before listener processing |
| Listener failed | Error handler/RetryListener | Listener was invoked but processing failed |
| Recovered/DLT | Recoverer or DLT publish metric | Failed record was moved to a recovery workflow |
| Deserialization failed | `ErrorHandlingDeserializer`/error handler | Bytes could not be converted into key/value so a regular filter never received a valid payload |
| Duplicate ignored in service | Metric in service/inbox | Listener received the record but the service decided not to repeat side effects |
| Tombstone | Filter or listener logic | Kafka record with null value, typically used in compacted topics to represent deletion |

Filters run after the consumer has deserialized the key/value. If JSON deserialization fails, `RecordFilterStrategy` is not where that error is measured; measure it separately on the error handling/deserialization path.

If the listener receives a record and then checks for duplicates in the database, that is business-layer idempotency logic, not a filter count. You need separate metrics to distinguish the two cases.

## 7. Measuring batch filtering

For batch listeners accepting `List<ConsumerRecord<K,V>>`, `RecordFilterStrategy.filterBatch()` can filter the whole batch. The default implementation calls `filter()` per record. If you override `filterBatch()`, measure the input record count and excluded record count right inside that method.

Example:

```java
@Component
public class BatchOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Counter examined;
    private final Counter filtered;

    public BatchOrderFilter(MeterRegistry registry) {
        this.examined = Counter.builder("app.kafka.records.examined")
                .tag("topic", "orders")
                .register(registry);
        this.filtered = Counter.builder("app.kafka.records.filtered")
                .tag("topic", "orders")
                .tag("reason", "expired_or_invalid")
                .register(registry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        // Used for record listeners or default filterBatch.
        boolean discard = shouldDiscard(record);
        examined.increment();
        if (discard) {
            filtered.increment();
        }
        return discard;
    }

    @Override
    public List<ConsumerRecord<String, OrderEvent>> filterBatch(
            List<ConsumerRecord<String, OrderEvent>> records) {

        List<ConsumerRecord<String, OrderEvent>> kept = new ArrayList<>();
        int discarded = 0;

        for (ConsumerRecord<String, OrderEvent> record : records) {
            examined.increment();
            if (shouldDiscard(record)) {
                discarded++;
            } else {
                kept.add(record);
            }
        }

        if (discarded > 0) {
            filtered.increment(discarded);
        }

        return kept;
    }

    private boolean shouldDiscard(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event == null || event.expired() || !event.supportedVersion();
    }
}
```

In this implementation, `filterBatch()` measures each record itself and does not call `filter()`, avoiding double counting. If you omit overriding `filterBatch()`, the default implementation calls `filter()` per record and the counters in `filter()` still work.

When a batch has multiple exclusion reasons, classify each record and increment counters per reason rather than lumping them together if dashboards require detailed breakdowns. Keep the reason set finite.

### Empty batches after filtering

Since Spring Kafka 3.3, `RecordFilterStrategy` has `ignoreEmptyBatch()`. By default it returns `false`, meaning the batch listener is still invoked with an empty list if all records were filtered out.

If you do not want to invoke the listener when the batch is empty:

```java
@Override
public boolean ignoreEmptyBatch() {
    return true;
}
```

When `ignoreEmptyBatch()` returns `true`, the listener is not invoked if all records in the batch were excluded; Spring Kafka still commits according to the container's mechanism. If it returns `false`, the listener receives an empty list and must handle that case safely.

Do not increment `batch.listener.invocations` as if the listener processed a non-empty batch when the adapter skips empty batches. You can measure `filtered_batches` separately if needed, while record count metrics must still be based on the number of excluded records.

## 8. ConsumerRecords does not support RecordFilterStrategy

`FilteringBatchMessageListenerAdapter` cannot filter a listener with a `ConsumerRecords<?, ?>` parameter because `ConsumerRecords` is immutable. If `@KafkaListener` accepts `ConsumerRecords`, the factory's strategy is ignored and Spring Kafka logs a warning.

To use filtering for batches, declare the listener accepting `List<ConsumerRecord<K,V>>` or the corresponding payload list. If you must keep `ConsumerRecords` to access `partitions()` and `records(topicPartition)`, you can filter manually in listener code, though the application must then manage metrics and processing semantics itself rather than relying on Spring Kafka's filtering adapter.

## 9. Acknowledging filtered records and offset impact

Filtering excludes records from the listener path, yet Kafka offsets still need to advance according to the consumer's commit policy. `ackDiscarded` controls whether the adapter acknowledges discarded records in acknowledgment-capable listeners.

In current Spring Kafka (4.1.x), `ackDiscarded` defaults to `false`. It can be set explicitly on the factory:

```java
factory.setAckDiscarded(true);
```

For example, if the listener uses manual acknowledgment:

```java
factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL);
factory.setAckDiscarded(true);

@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderEvent event, Acknowledgment acknowledgment) {
    orderService.process(event);
    acknowledgment.acknowledge();
}
```

For filtered records, the listener is not invoked; the adapter acknowledges those records per `ackDiscarded=true`. For kept records, the listener acknowledges after business processing succeeds. If the listener throws an exception before acknowledging, the error handler/container handles it according to configuration.

Meaning of each choice:

- For record listeners using an acknowledging adapter and manual acknowledgment, `true` lets the adapter acknowledge excluded records; `false` leaves acknowledgment to the regular listener/container flow.
- For batch listeners, when the entire batch is filtered, `true` makes the adapter acknowledge the batch without invoking the delegate; `false` passes an empty list to the delegate so the listener decides whether to acknowledge.
- `ackDiscarded` is not a counter, nor does it mean all partition offsets are immediately committed. Actual commits still depend on AckMode, transactions, and offset ordering.

With container-managed automatic AckModes like `RECORD` or `BATCH`, actual commits still depend on AckMode, transactions, and record progress in the partition. Do not infer that an increasing `filtered` counter means offsets have been committed.

For batch listeners, if the whole batch is excluded, behavior also involves `ackDiscarded` and `ignoreEmptyBatch()`. `ignoreEmptyBatch()` controls whether the listener is invoked with an empty batch since Spring Kafka 3.3; `ackDiscarded` controls acknowledgment of the excluded batch in the adapter. Test thoroughly with the active AckMode, especially `MANUAL`/`MANUAL_IMMEDIATE`. Do not acknowledge before ensuring the filter made the right business decision.

### When should filtered records be acknowledged?

Acknowledge when:

- The filter determined the record definitely needs no processing.
- The exclusion rule is stable and explainable.
- The record does not need to be retried after a restart or rebalance.
- If auditing is required, minimal metadata was durably recorded before the offset is committed.

Do not acknowledge if:

- The filter decision depends on an external service that is temporarily failing.
- You are unsure whether the record is a duplicate or deduplication state is simply unsynchronized.
- The system has not yet stored information needed to investigate excluded records.
- Mistakenly discarding the record could lose critical business data.

## 10. Filtering and the idempotent receiver

A common use case for filtering is excluding duplicate events. Spring Kafka does not automatically know whether an event was already processed in the database; that is the application's responsibility. `RecordFilterStrategy` can be used to implement part of the Idempotent Receiver pattern.

Simple example:

```java
@Component
public class DuplicateOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final ProcessedEventRepository processedEvents;

    public DuplicateOrderFilter(ProcessedEventRepository processedEvents) {
        this.processedEvents = processedEvents;
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event != null && processedEvents.existsByEventId(event.eventId());
    }
}
```

This example illustrates the check; querying the database for every record can hurt throughput. A cache or suitable dedupe store can be used, but a cache is only an optimization and does not replace a durable unique constraint.

Specifically, do not perform a workflow that "marks the event as processed" inside the filter and then lets the listener update business state in a separate transaction. If the application crashes between the two steps, the event may be marked processed while the side effect never happened; on the next read, the filter drops it and data is lost.

A safer design is usually inserting the inbox/processed-event record and executing the database side effect within the same DB transaction in the listener service. Filters should only skip events already confirmed completed earlier, or be used when the dedupe workflow has durable, atomic state.

## 11. Distinguishing RecordFilterStrategy and RecordInterceptor

Both extension points run around the listener, but their goals differ:

| Component | Purpose | How skipping is expressed |
|---|---|---|
| `RecordFilterStrategy` | Decide whether a record is excluded | `filter(record)` returns `true` |
| `RecordInterceptor` | Observe/modify a record before the listener and receive post-processing callbacks | `intercept()` can return `null` to skip forwarding the record to the listener |

If the primary goal is measuring filtered records and controlling acknowledgment for those records, `RecordFilterStrategy` is usually clearer. If the goal is adding context, lightweight inspection, logging, or observing the record lifecycle, `RecordInterceptor` is a better fit.

Do not count the same record as filtered in both an interceptor and a filter if the same record passes through both hooks; doing so creates double counting. Pick one point responsible for the `filtered` metric and document its definition clearly.

An interceptor also does not replace the error handler. If an interceptor throws an exception, the error must be handled by the container's error handling; it is not a normal filter decision.

## 12. Where does the filter run in the consumer flow?

For a record listener, the general flow:

```text
KafkaConsumer.poll()
        |
        v
Deserialize key/value
        |
        v
RecordFilterStrategy
       / \
      /   \
   false   true
    |       |
    v       v
Listener  Discard/ack policy
    |       |
    v       v
AckMode / container offset commit
```

This has several consequences:

- Discarded records have already been fetched from the broker, so filtering does not save full network/fetch costs.
- Deserialization already ran before the filter; a filter cannot fix malformed JSON.
- Listener timers typically do not reflect filter duration when the listener is not invoked; measure the filter separately.
- Filter logic runs on the consumer thread; slow operations like HTTP calls or DB queries can increase processing time and consumer lag.
- Discarded records are not automatically routed to a DLT. If quarantine is needed, the filter must explicitly record/publish and only acknowledge after that action completes under the chosen semantics.

## 13. Monitoring filter ratios and alerting on anomalies

Some useful charts:

| Chart | Purpose |
|---|---|
| Filtered records per second | Observe the volume of excluded records |
| Examined vs filtered | Compare total records passing through the filter against excluded records |
| Filter ratio by reason | Detect an unusual rise in one exclusion reason |
| Filter ratio by topic/listener | Identify listeners or topics with unusual policies |
| Consumer lag alongside filter rate | Distinguish lag dropping due to higher throughput vs dropping many records |
| Filter execution duration | Detect slow filter logic |

You can compute the filter ratio in Prometheus from exported counters. For example, if Micrometer metrics are exported under the corresponding names:

```promql
sum(rate(app_kafka_records_filtered_total[5m]))
/
clamp_min(sum(rate(app_kafka_records_examined_total[5m])), 1)
```

To compare by topic or reason, keep the same label set in numerator and denominator or aggregate away unnecessary labels. Actual Prometheus metric names may be normalized from Micrometer names; check `/actuator/prometheus` before authoring dashboards.

Do not alert merely because the filter ratio is non-zero. Some topics intentionally contain events a consumer does not care about. Alerts should rely on baselines, abnormal rates, specific reasons, and business impact.

## 14. Measuring filter execution duration

If a filter performs complex logic, measure duration to detect the filter becoming a bottleneck:

```java
@Component
public class TimedOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Timer filterTimer;

    public TimedOrderFilter(MeterRegistry registry) {
        this.filterTimer = Timer.builder("app.kafka.filter.duration")
                .tag("listener", "orders")
                .register(registry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        return filterTimer.record(() -> shouldDiscard(record));
    }

    private boolean shouldDiscard(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event == null || event.expired();
    }
}
```

The timer records invocation counts and execution durations. You can monitor p95/p99 to see whether the filter is slower than expected. Avoid tagging by event ID or key.

If the filter queries a database, separately measure lookup latency and dependency error rates. Do not catch a database exception and return `true` to discard the record; transient dependency errors could permanently drop valid records. Throw the exception so the error handler handles retries, or design a safe fallback.

## 15. Testing metrics for filtered records

Tests should verify filter decisions, counters, and offsets:

1. **Kept record:** filter returns `false`, `examined` increments by 1, `filtered` does not increment, and the listener is invoked.
2. **Filtered record:** filter returns `true`, `examined` and `filtered` both increment by 1, and the listener is not invoked.
3. **Different reasons:** duplicate, expired, and unsupported version increment their respective reason counters.
4. **Batch with valid and excluded records:** examined count equals input batch size; filtered equals discarded count; listener receives the exact remaining list.
5. **Fully filtered batch:** verify `ignoreEmptyBatch()` determines whether the listener receives an empty list depending on the version.
6. **ConsumerRecords listener:** verify the filter strategy is not applied and a warning is logged; do not expect filter counters to increment.
7. **Manual acknowledgment:** test `ackDiscarded` true/false and offset commits under the actual AckMode.
8. **Filter exception:** verify exceptions flow through the error handler instead of being counted as normal filtered decisions.
9. **Deserialization failure:** verify errors are measured in error handling rather than added to the filtered counter.
10. **Duplicate events:** verify deduplication does not mark an event completed before business side effects commit.
11. **Metric cardinality:** verify event ID, offset, and key do not appear in metric tags.
12. **Filter latency:** check that the Timer accurately records invocation count and duration.

Use `spring-kafka-test` or Testcontainers Kafka to verify listeners, offsets, and filter adapters end-to-end. Unit tests for `RecordFilterStrategy` only check decision logic; they do not prove the container commits offsets properly.

## 16. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Listener still receives records thought to be filtered | `filter()` returned `false`, factory missing strategy, or endpoint uses another factory | Inspect return value, bean, and `containerFactory` |
| Filter count is higher than expected records | Counting in both `filter()` and `filterBatch()`, or listener retries/re-reads | Measure once at one boundary and account for redeliveries |
| No filter count seen for batches | Overrode `filterBatch()` without incrementing counters, or listener uses `ConsumerRecords` | Count inside `filterBatch()` and use `List<ConsumerRecord>` if adapter filtering is desired |
| Listener receives empty batches | `ignoreEmptyBatch()` defaults to false since 3.3 | Return true to skip invocation when the whole batch is filtered |
| Offsets do not advance as expected | `ackDiscarded`, AckMode, or manual acknowledgment misconfigured | Check commit config and test against a broker |
| Filter ratio spikes suddenly | Producer changed event version, duplicates surged, or filter rule is too broad | Break down by reason and topic, cross-check producer releases |
| Consumer lag drops sharply and abnormally | Filter is excluding many records | Compare examined vs filtered and verify business behavior |
| Filter increases consumer lag | Filter logic makes slow DB/HTTP calls | Optimize lookups, use controlled caching, or move logic to an appropriate service |
| Valid records dropped on DB failure | Filter treats lookup error as duplicate/invalid | Throw exception or use a safe fallback; do not discard without certainty |
| Records lost after duplicate filtering | Marked processed before side effects committed | Use an inbox/unique constraint in the same DB transaction |

## 17. Measurement implementation workflow

1. Identify why records must be excluded and ensure it is an explainable business decision.
2. Attach `RecordFilterStrategy` to the right listener container factory or select a per-listener filter via `@KafkaListener`'s `filter` attribute.
3. Create counters for examined and filtered records; add low-cardinality reasons.
4. For batch listeners, clarify whether the filter uses the default `filter()` or custom `filterBatch()` and avoid double counting.
5. Choose `ackDiscarded` according to AckMode, transactions, and redelivery policy; configure explicitly.
6. For batches, decide `ignoreEmptyBatch()` if using Spring Kafka 3.3 or later.
7. Do not use `ConsumerRecords<?, ?>` if you want the filtering adapter to filter automatically.
8. Measure filter duration if logic accesses dependencies or performs complex checks.
9. Build dashboards for examined, filtered, ratio, reason, duration, and consumer lag.
10. Test filtering, offsets, empty batches, deserialization failures, duplicates, and cardinality before deployment.

## 18. Summary

- `RecordFilterStrategy.filter(record)` returns `true` to exclude a record and `false` to forward it to the listener.
- Filtering does not delete records from Kafka; it only prevents the listener from receiving them, and offsets remain managed per AckMode/acknowledgment.
- Spring Kafka does not provide a built-in business counter for filtered records; use Micrometer counters at the filter boundary.
- Measure both `examined` and `filtered`, then compute filter ratio per matching topic/listener/reason.
- `filterBatch()` exists since Spring Kafka 2.8; by default it calls `filter()` per record. If overridden, measure counts yourself and avoid double counting.
- `ignoreEmptyBatch()` exists since 3.3 and defaults to false; it can skip listener invocation when a batch is completely filtered out.
- The filtering adapter does not apply to listeners accepting `ConsumerRecords<?, ?>` because that object is immutable.
- `ackDiscarded` defaults to false in current versions; set it explicitly per AckMode and redelivery requirements.
- Distinguish filtered records, listener failures, DLT recoveries, deserialization failures, and duplicates ignored in the service.
- Use low-cardinality tags; put event ID, offset, and correlation ID in logs/traces.
- Do not mark events processed before business side effects commit; use durable inbox/idempotency for duplicates.

When measuring filtered records right at `RecordFilterStrategy`, operations teams can see filter ratios, exclusion reasons, and execution times. Combining those metrics with offsets, consumer lag, and business state helps catch misbehaving filters before skipping records turns into data loss.

## References

- [Spring Kafka Reference — Filtering Messages](https://docs.spring.io/spring-kafka/reference/4.1/kafka/receiving-messages/filtering.html)
- [Spring Kafka API — RecordFilterStrategy](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/adapter/RecordFilterStrategy.html)
- [Spring Kafka API — AbstractKafkaListenerContainerFactory](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/AbstractKafkaListenerContainerFactory.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
