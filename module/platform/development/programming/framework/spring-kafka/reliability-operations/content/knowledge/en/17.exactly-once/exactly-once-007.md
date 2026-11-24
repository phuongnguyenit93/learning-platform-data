# read_committed consumer

In Kafka, a producer can write multiple records within a **transaction** and then decide to call `commitTransaction()` or `abortTransaction()`. A consumer in default mode can still observe records belonging to a transaction that ultimately aborts. For flows that must ensure consumers process only results confirmed by the producer, Kafka provides the **`isolation.level=read_committed`** configuration.

In Spring Kafka, `read_committed` is set on the **Kafka consumer**, typically via `spring.kafka.consumer.properties[isolation.level]` or `ConsumerFactory` configuration. It instructs the consumer to return only records from committed transactions, along with records written outside transactions. Records belonging to open or aborted transactions are not delivered to the listener as valid business data.

`read_committed` is an essential piece of **exactly-once processing within Kafka's scope**, yet **it does not turn the entire application into exactly-once by itself**. To achieve atomicity across consuming, processing, and producing to Kafka, the application must also use Kafka transactions and include processed offsets in the same transaction. If the listener updates a database, calls an HTTP API, or sends emails, those non-Kafka side effects still need idempotency, an outbox, or a separate reconciliation mechanism.

## 1. How do `read_uncommitted` and `read_committed` differ?

The Kafka consumer `isolation.level` property has two main values:

| Mode | Records from committed transactions | Records from aborted transactions | Records from open transactions | Records from non-transactional producers |
|---|---|---|---|---|
| `read_uncommitted` (Kafka consumer default) | Readable | Readable | Readable once present in the log and fetched | Readable |
| `read_committed` | Readable once transaction commits | Not delivered to application | Not delivered yet to application | Readable, subject to Last Stable Offset |

Note: `read_uncommitted` does not mean the consumer sees data not yet acknowledged by the broker. It still obeys Kafka's log fetch boundaries, yet **does not filter records by transaction outcome** the way `read_committed` does.

`read_committed` does not require every producer writing to the topic to use transactions. Records from non-transactional producers are still readable. Filtering only matters when the topic contains transactional records and their corresponding commit/abort markers.

## 2. Visual example of transaction visibility

Suppose a producer processes an order and needs to write two events together:

```text
Producer transaction T-42
       |
       +--> orders-events: OrderAccepted
       |
       +--> orders-events: InventoryReserved
       |
       +--> commitTransaction()
```

If the transaction commits successfully, a `read_committed` consumer can receive both events. If the producer aborts because the second step fails, a `read_committed` consumer does not see the two records as confirmed events.

```text
Partition log:
  offset 100: non-transactional record
  offset 101: T-42 / OrderAccepted
  offset 102: T-42 / InventoryReserved
  offset 103: transaction COMMIT marker
  offset 104: non-transactional record

read_committed:
  receives records 100, 101, 102, 104
  does not pass control marker 103 to business listener
```

With an aborted transaction:

```text
Partition log:
  offset 200: non-transactional record
  offset 201: T-43 / OrderAccepted
  offset 202: T-43 / InventoryReserved
  offset 203: transaction ABORT marker
  offset 204: non-transactional record

read_committed:
  receives records 200 and 204
  skips records from aborted T-43 and control marker

read_uncommitted:
  may receive records 201 and 202 even though transaction aborted
```

The offsets above are conceptual examples. Control batches are part of the Kafka log and are not delivered as ordinary business messages. Therefore, **offsets observed by the listener are not necessarily contiguous**: gaps appear due to aborted transactional records or control records. Never treat an offset gap as definitive proof that Kafka lost records.

## 3. Last Stable Offset (LSO): why can a consumer appear stalled?

Kafka must avoid delivering records from a transaction whose final outcome (commit or abort) is not yet known. With `read_committed`, the key read boundary is the **Last Stable Offset (LSO)**. Think of LSO as the safe position up to which Kafka can return transactionally stable records: it is bounded by the high watermark and the start offset of the earliest open transaction on the partition.

Example:

| Offset | State |
|---:|---|
| 50 | Non-transactional record, stably written |
| 51 | Transaction A starts, not yet committed/aborted |
| 52 | Another record belonging to transaction A |
| 53 | Non-transactional record, written after A started |
| 54 | Non-transactional record, written after A started |

As long as transaction A remains open, a `read_committed` consumer can only read records before transaction A's start position, even though the broker has already received records at offsets 53 and 54. This is a **partition stability boundary**, not a case of those non-transactional records being marked aborted.

```text
Log offsets:     50  51  52  53  54 ...
                     ^
             open transaction A

read_committed:
             can read up to before offset 51

When A COMMITS or ABORTS:
             LSO can advance;
             eligible records are returned again
```

A long-open transaction can make a `read_committed` consumer look "stuck" while producer/broker metrics show the log growing. If an application enables this mode and looks only at log-end offsets, it may misdiagnose the issue as a stalled consumer thread or network fault.

### Distinguishing three common positions

| Concept | Meaning |
|---|---|
| Log End Offset (LEO) | Tail of the log on a replica; may include transactionally unstable data |
| High Watermark (HW) | Boundary of data replicated enough for the broker to serve under Kafka's read mechanism |
| Last Stable Offset (LSO) | Boundary for `read_committed` consumers; does not pass the earliest open transaction |

APIs and tools measuring `endOffsets()` or lag may reflect different boundaries depending on isolation level and tooling. For a `read_committed` Kafka consumer, `endOffsets()` reflects LSO; many broker/group monitoring tools compute lag against log-end or high watermark instead. When comparing figures, verify **which endpoint** is used as the baseline.

## 4. Enabling `read_committed` in Spring Boot

For a Spring Boot application using Spring Kafka, the simplest approach is configuring Kafka consumer properties:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.group-id=order-materializer
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.properties[isolation.level]=read_committed
```

`enable-auto-commit=false` is not a technical requirement for **reading** with `read_committed`, yet is commonly chosen deliberately in systems needing exact control over when offsets commit. For transactional consume-transform-produce flows, let the container and Kafka transaction manage offsets instead of enabling separate Kafka consumer auto-commit.

If values are JSON, also configure an appropriate deserializer and type mapping:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

The JSON settings here are illustrative; production apps need type headers or a default type and a schema contract consistent with the producer. Do not open `trusted.packages=*` indiscriminately. `read_committed` does not fix deserialization errors or guarantee schema compatibility.

### Configuring with YAML

Equivalent properties can be placed in `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-materializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[isolation.level]": read_committed
```

In Spring Boot, Kafka client keys are passed via the `consumer.properties` map; the `[isolation.level]` syntax preserves dotted keys during binding. What matters is that the final value reaches `ConsumerConfig.ISOLATION_LEVEL_CONFIG`, not merely sitting in a YAML file. When multiple profiles or custom factories exist, verify that created consumers actually use the intended isolation level.

## 5. Configuring per `ConsumerFactory` to isolate listeners

An application may have both consumers for committed processing and consumers for testing/diagnostics. If only one group of listeners needs `read_committed`, creating a dedicated `ConsumerFactory` and `ConcurrentKafkaListenerContainerFactory` avoids accidentally changing semantics for all consumers.

```java
@Bean("readCommittedConsumerFactory")
ConsumerFactory<String, OrderEvent> readCommittedConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    properties.put(
            ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
    properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    return new DefaultKafkaConsumerFactory<>(properties);
}

@Bean("readCommittedKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
readCommittedKafkaListenerContainerFactory(
        @Qualifier("readCommittedConsumerFactory")
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener example:

```java
@KafkaListener(
        id = "orderMaterializer",
        topics = "orders-events",
        groupId = "order-materializer",
        containerFactory = "readCommittedKafkaListenerContainerFactory")
public void materialize(OrderEvent event) {
    orderProjectionService.applyIdempotently(event);
}
```

Classes `OrderEvent` and `OrderProjectionService` are illustrative application types. `DefaultKafkaConsumerFactory` needs a deserializer that can actually instantiate `OrderEvent`; shared JSON/schema settings from `KafkaProperties` can be used. Spring Boot's `buildConsumerProperties()` API may have different overloads across versions; use the method supported by your actual dependency and preserve all TLS/SASL, bootstrap, and client settings.

In the example, `AckMode.RECORD` is an option for a listener writing to a database using at-least-once + idempotency. **It does not turn the database update and Kafka offset commit into an atomic transaction.** Achieving that requires dedicated transactional/reconciliation design; `read_committed` governs only whether records from Kafka producers are visible.

When multiple factories coexist, do not just set a global property and assume every listener inherits it. Verify the `ConsumerFactory` bean wired into the right factory and that the `containerFactory` annotation points to the exact bean name.

## 6. `read_committed` does not enable Kafka transactions on producers

A consumer can enable `read_committed` while producers still send non-transactional records. In that case, the consumer still reads records, yet **has no atomicity across a group of operations** because the producer never created a transaction.

For a producer to emit transactional data, you need a transaction-capable `ProducerFactory`, a unique transaction ID prefix scoped per instance, and transaction begin/commit/abort management.

Illustrative Spring Boot example:

```properties
# Concurrently running producer instances must have distinct transactional.id values.
spring.kafka.producer.transaction-id-prefix=order-writer-instance-01-
```

`transaction-id-prefix` must avoid collisions across concurrently running application instances. If two producers operate with the same `transactional.id`, the broker can fence the older producer and cause transaction errors. An ID can be intentionally reused in producer instance recovery, but two concurrently running instances must never share the same ID arbitrarily.

When `KafkaTemplate` is backed by a transactional producer factory, Spring Kafka can execute multiple sends in a single Kafka transaction. Example:

```java
public void publishOrderEvents(OrderEvent accepted, OrderEvent reserved) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders-events", accepted.orderId(), accepted);
        operations.send("orders-events", reserved.orderId(), reserved);
        return null;
    });
}
```

If the transaction commits, `read_committed` consumers can read the written records. If the transaction aborts, those records are not delivered to `read_committed` consumers. This snippet illustrates **atomicity across Kafka publishes only**; it does not yet include reading from Kafka and writing consumed offsets into the same transaction.

Producers also need proper durability settings such as `acks=all`, idempotence, replication factor, and `min.insync.replicas` on topics. Enabling `read_committed` on consumers alone cannot compensate for unsafe broker/producer settings.

## 7. Exactly-once in a Kafka → Kafka pipeline

A typical scenario is a consumer reading `orders-input`, transforming data, and a producer writing `orders-output`. The goal is for **output records and input record offsets to commit together** in one Kafka transaction.

```text
orders-input
     |
     v
Spring Kafka listener
     |
     +--> compute / transform
     |
     +--> KafkaTemplate sends to orders-output
     |
     +--> consumed offset added to transaction
     |
     v
Kafka transaction COMMIT
     |
     +--> output record read by read_committed consumer
     |
     +--> consumer group records processed offset
```

If the listener fails or the transaction aborts, outputs sent in the transaction are invisible to `read_committed` consumers; the source offset is also not committed as completed. When the listener re-runs after rollback, the application can re-read the source record without producing unintended **committed outputs** when Kafka transactions are used properly.

In Spring Kafka, this design typically requires:

1. A transaction-capable `ProducerFactory` with `transactionIdPrefix`.
2. `KafkaTransactionManager` or an equivalent transaction manager attached to the right listener container.
3. `KafkaTemplate` participating in the transaction created by the container when the listener is invoked.
4. Consumer `enable.auto.commit=false` so offsets do not auto-commit outside the transaction.
5. The container placing processed offsets into the Kafka transaction (`sendOffsetsToTransaction` managed by Spring Kafka).
6. **Downstream consumers** reading `orders-output` with `isolation.level=read_committed` if they must see only committed outputs.

You do not need to manually call `sendOffsetsToTransaction` inside a listener when the container already properly manages transactions and offsets. Committing offsets manually outside the transaction while the container manages transactional offsets can break the desired atomicity. How a transaction manager is attached to `ContainerProperties` varies across Spring Kafka versions; use your version's actual API and test transaction aborts before relying on this guarantee.

### Why are both producer transactions and `read_committed` needed?

A producer transaction can abort outputs, yet a downstream consumer on `read_uncommitted` can still read output records that were written and later aborted. Therefore, downstream wanting only confirmed results must use `read_committed`. Conversely, downstream `read_committed` without upstream transactions cannot manufacture an atomic boundary across multiple records.

## 8. Limitations: databases, REST APIs, and non-Kafka side effects

Suppose a listener reads a `PaymentCaptured` record and then:

1. Writes payment state to PostgreSQL.
2. Publishes an `InvoiceRequested` event to Kafka.
3. Commits the source offset.

Even when steps 2 and 3 belong to a Kafka transaction, step 1 does **not automatically** participate in that same transaction. If the database commits while the Kafka transaction aborts, the listener can re-read the record and write to the database a second time.

To avoid duplicate side effects, use a **transactional inbox / idempotent consumer**: record the event ID in a table with a unique constraint inside the same database transaction as the business update. When the record is redelivered, a duplicate-ID inbox insert indicates the operation already ran and can finish safely.

```text
BEGIN DB TRANSACTION
       |
       v
INSERT INTO processed_event(event_id)
       |
       +---- ID already exists ----> skip duplicate side effect
       |
       v
Update business state
       |
       v
COMMIT DB TRANSACTION
```

If you must atomically save state and the intent to emit a Kafka event from a database, the outbox pattern writes both domain state and an outbox row in one DB transaction and publishes asynchronously. Downstream consumers must still handle duplicates because outbox publishers/relays usually have at-least-once semantics.

For emails, API payments, or other HTTP requests, you need target-system idempotency keys, orchestration state, or compensating workflows. `isolation.level=read_committed` does not govern those systems.

## 9. Consumer committed offsets differ from producer transaction commits

Kafka uses the word "commit" in two contexts:

| Term | What is confirmed | Who controls it? |
|---|---|---|
| Producer transaction commit | A group of records and/or offsets atomically recorded within a Kafka transaction | Transactional producer / transaction manager |
| Consumer committed offset | Next position the consumer group will read after restart or rebalance | Kafka consumer/container or transactional offset commit |

`read_committed` only determines **which records are visible to the consumer**. It does not decide when the consumer group's committed offset advances. Whether the container uses `AckMode.RECORD`, `AckMode.BATCH`, manual acknowledgment, or Kafka transactions, offset commit progression still depends on that specific mechanism.

For instance, a record at offset 104 is committed by the producer and received by a `read_committed` consumer. If the listener crashes before the group's committed offset advances to 105, Kafka can redeliver offset 104 upon restart. A record being **committed on the producer side** does not mean it is **finished on the consumer side**.

In a Kafka→Kafka EOS pipeline, producer transactions typically include both outputs and source offsets. In a Kafka→database pipeline, protect database side effects with idempotency even when reading the source topic with `read_committed`.

## 10. Impact on retries, DLT, and recovery

Spring Kafka can use `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, or `@RetryableTopic` to retry/recover failing records. `read_committed` operates below the listener layer at the Kafka consumer fetch level. It does not classify exceptions, configure backoff, or send records to a DLT.

If a **committed record on the source topic** cannot be deserialized by the listener, `read_committed` will still receive it and the error handler must handle the format error. If a record belongs to an **aborted transaction**, it is not delivered to the listener, so the business error handler never receives it to route to a DLT. That is the intended behavior of isolation, not data loss.

In transactional recovery flows, publishing to a DLT and committing the source offset can be placed in a suitable Kafka transaction, often via `DefaultAfterRollbackProcessor` and a transactional template. Downstream consumers wishing to see only committed DLT records should use `read_committed` if the DLT publisher is transactional.

Do not assume every DLT publisher uses transactions. When a DLT record is published outside a transaction, `read_committed` still receives it as a non-transactional record. If publishing to the DLT succeeds while committing the source offset fails in a non-transactional model, duplicate DLT records can appear after restart; use original topic-partition-offset or a stable event ID to deduplicate during replay.

## 11. `read_committed` and per-partition record ordering

Kafka preserves log order per partition. However, when a consumer reads with `read_committed`, records from aborted transactions and control markers are withheld from the listener, so the offset sequence observed by the listener may be non-contiguous:

```text
Partition log:
  300 -> committed transaction A
  301 -> aborted transaction B
  302 -> aborted transaction B
  303 -> committed transaction C

read_committed listener:
  processes offset 300, then 303
```

This does not mean Kafka reorders delivered records. Relative order among **visible** records on the same partition still matches log position. However, skipped records must not be modeled as business events that occurred.

Across multiple partitions, `read_committed` creates no total order across partitions. If a business invariant requires events with the same key to be processed in order, producers must partition consistently and consumers/state machines must control state. If a producer changes its partitioner or partition count, merely enabling `read_committed` does not solve ordering.

## 12. When does `read_committed` increase latency?

Unlike `read_uncommitted` consumers that can see transactional records immediately upon write, `read_committed` consumers must wait until a transaction reaches a terminal state. Latency typically comes from:

- Producers keeping transactions open too long before committing.
- Hung transactions due to application bugs or network interruptions.
- Brokers waiting for timeouts or transaction coordinators processing aborts.
- An early open transaction on a partition holding LSO back, preventing later records from being returned yet.
- High transaction counts/throughput increasing operational load on the transaction coordinator.

If `transaction.timeout.ms` is too long, an abandoned transaction can stall a partition's LSO for a long period. If the timeout is too short for actual work, producers may abort and have to re-run. Pick timeouts based on actual transaction durations, broker-allowed limits, and downstream consumer SLOs.

Avoid stretching a Kafka transaction to wait on a slow HTTP or database operation whenever avoidable. Keep transactions short to reduce visibility stalls, crash recovery times, and broker load.

## 13. Observing and diagnosing `read_committed` consumers

Consumer dashboards should distinguish **no new records**, **LSO-bounded**, and **slow listener processing**. All three look like low throughput yet have different causes and remedies.

| Signal | Meaning to investigate |
|---|---|
| Consumer group committed offset | Group's recorded progress after processing |
| Last Stable Offset (LSO) | Stable record boundary readable when isolation is enabled |
| High watermark / log end | How far the broker has data, including transactionally unstable data |
| Consumer lag | Can differ across dashboards, CLI, and consumer `endOffsets()` because different endpoints are used |
| Transaction abort rate | Are producers generating many aborted records? |
| Transaction duration / timeout | Is a long-open transaction pinning LSO? |
| Rebalance and poll latency | Is the consumer losing assignments or stalling in processing? |
| Listener error / DLT rate | Are delivered records failing at the application layer? |

Suppose log-end offset is 20,000, LSO is 19,500, and the consumer group's committed offset is 19,500. A tool using log-end may report lag of 500, while the `read_committed` consumer has zero stable records available past 19,500. Diagnostics should focus on the open transaction at the LSO boundary rather than simply adding consumer threads.

Startup logs should show consumer group, listener ID, topic, isolation level, and factory used. If only one group of listeners must read committed data, monitor that group separately. Do not use individual event IDs, keys, or offsets as high-cardinality metric labels; put them in structured logs or traces when investigating.

## 14. Configuration errors and common scenarios

| Symptom | Possible cause | Resolution |
|---|---|---|
| Downstream consumer processes records from aborted transactions | Consumer still uses default `read_uncommitted` | Configure `isolation.level=read_committed` on the right consumer/factory |
| `read_committed` enabled yet "half-transaction" data still appears | Producer does not use Kafka transactions or side effects sit outside Kafka | Verify producer transactional ID, transaction boundaries, and involved systems |
| Group lag is high while listener receives no more records | LSO is pinned by an open transaction | Compare LSO/HW/LEO, transaction duration, and timeouts |
| Listener offsets show gaps | Aborted records/control markers are withheld | Understand offset semantics; do not jump to assuming message loss |
| Listener still processes duplicate records after restart | Consumer offset did not commit or non-Kafka side effect is not idempotent | Check transactional offset commit, inbox, and idempotency |
| `read_committed` set yet Kafka→Kafka still produces duplicate output | Output producer and source offset do not share a Kafka transaction | Use container transaction manager and in-transaction offset commits |
| Producer gets fenced when deploying multiple replicas | Colliding transactional IDs across concurrently live producers | Design unique per-instance prefixes/IDs, inspect rolling deployments |
| Multiple duplicate DLT records | DLT publish and source offset are non-atomic; recovery retries after crash | Use provenance, deduplication, or proper transactional recovery |
| Config change has no effect | Listener uses a different `ConsumerFactory` | Verify bean names, profiles, and actual runtime Kafka client configs |

To confirm a consumer truly runs in `read_committed`, inspect the actual client configuration in startup logs or runtime config collected by monitoring tools—not just one line in `application.properties` when profiles or custom factories may override it.

## 15. Integration test scenarios

Tests should use a transaction-capable Kafka broker, transactional producer, and `read_committed` consumer (e.g., Kafka Testcontainers or a test cluster). Key scenarios:

1. **Transaction commit:** producer writes two records in one transaction and commits; `read_committed` listener receives both.
2. **Transaction abort:** producer writes records and aborts; `read_committed` listener does not receive them.
3. **`read_uncommitted` control group:** another consumer group in default mode can see the aborted records, demonstrating the isolation difference.
4. **Non-transactional records:** a regular producer writes records; `read_committed` still receives non-transactional records properly.
5. **Open transaction:** producer leaves a transaction uncommitted; verify the consumer does not advance past the partition's LSO.
6. **Commit after waiting:** producer commits; verify LSO advances and new records become deliverable.
7. **Producer crash/timeout:** abandon a transaction and verify abort/recovery behavior; consumer never sees aborted output.
8. **Consume-transform-produce rollback:** intentionally throw an exception in a transactional listener; verify the transaction's output aborts and the input offset is not committed as complete.
9. **Crash after database update:** verify the consumer can re-receive the record while inbox/idempotency blocks duplicate side effects.
10. **Multiple listener factories:** verify only listeners bound to the corresponding `ConsumerFactory` receive the selected isolation level.

In tests, inspect **actual records**, **producer transaction results**, **consumer group offsets**, and **business state**. Simply checking total record counts in a Kafka topic does not prove `read_committed` filters aborted records properly. When testing Kafka→Kafka EOS, downstream must read with `read_committed` to distinguish committed outputs from aborted ones.

## 16. Runbook when a `read_committed` consumer stalls

If consumer lag grows while the listener stops being invoked, investigate in order:

1. Confirm listener ID, `group.id`, topic, partition, and actual consumer `isolation.level`.
2. Confirm whether the topic has transactional producers, and which producer is writing.
3. Compare group committed offset, LSO, and log-end/high-watermark using metrics/tools if available.
4. If LSO is stuck, inspect long-open transactions, transaction coordinator, timeouts, and producer errors.
5. If LSO has advanced yet the listener still receives nothing, check partition assignments, pause/resume state, poll thread, deserializer, and error handler.
6. Check transaction abort rates and producer fencing after rolling deployments.
7. Never manually reset offsets or switch to `read_uncommitted` in production to "get data moving" without understanding the impact of aborted data.
8. Adjust producer/transaction timeouts or consumer config cleanly; then observe LSO, lag, and throughput recovery.
9. Document the root cause and add alerts on transaction duration or LSO lag.

Switching a critical consumer to `read_uncommitted` to relieve lag can cause the system to process events the producer explicitly aborted. That changes data correctness, not merely performance. If you must read raw logs for investigation, use a separate consumer/group with proper permissions and procedures instead of altering business consumer semantics.

## 17. Production design principles

When using `read_committed` in a Spring Kafka Reliability Operations system, uphold these principles:

1. Verify producers actually use Kafka transactions, and know which records are transactional.
2. Configure `isolation.level=read_committed` on the **exact consumer** that must see committed data, not just on an unused factory.
3. Choose `enable.auto.commit=false` and transactional offset commits for Kafka→Kafka flows requiring EOS within Kafka.
4. Ensure the producer transaction and source offsets share the same Kafka transaction if atomicity between input progress and output is required.
5. Do not equate producer transaction commits with consumer committed offsets; they are two separate responsibilities.
6. Design idempotency/inbox/outbox for databases, HTTP calls, and non-Kafka side effects.
7. Monitor LSO, transaction duration, abort rate, group lag, and processing latency; understand the difference between LSO and log-end.
8. Avoid long-running Kafka transactions or colliding transactional IDs across concurrent instances.
9. Do not treat offset gaps caused by aborted/control records as data loss.
10. Test commit, abort, open transactions, timeouts, restarts, rebalances, and transaction rollbacks before relying on processing guarantees.

**Conclusion:** `read_committed consumer` is the configuration governing **record visibility based on Kafka transaction outcomes**. It prevents listeners from processing records from aborted transactions and is a prerequisite on the read side for many Kafka→Kafka pipelines needing exactly-once semantics. However, end-to-end reliability still depends on producer transactions, in-transaction offset commits, idempotency, and operational observability. Understanding Last Stable Offset and transaction boundaries prevents both mistakes: accidentally reading aborted data, and falsely assuming setting one property creates exactly-once guarantees for all side effects.
