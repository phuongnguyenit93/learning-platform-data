# Trade-offs Between At-Most-Once and At-Least-Once

When a Kafka consumer receives a record, the application must decide when to confirm that the offset has been processed. If the offset is committed before running business logic, the record can be lost if the application stops between the two steps. If business logic runs first and the offset is committed afterward, the record can be redelivered if the application stops after processing but before committing. This is the fundamental trade-off between two delivery semantics: **at-most-once** and **at-least-once**.

In Spring Kafka, commit timing is controlled by consumer configuration, the listener container's `AckMode`, how the listener acknowledges, and error-handling policies. Choosing the right semantics depends on tolerance for data loss, ability to handle duplicates, ordering requirements, and commit overhead.

## 1. How Do Offsets Represent Reading Progress?

Kafka stores offsets per partition and per consumer group. When a consumer processes a record at offset `n`, the committed offset is typically `n + 1`, the next position to read. An offset commit is neither a per-record flag nor an instruction for the broker to delete that record.

Example of a partition with records:

```text
Partition 0
  offset 0
  offset 1
  offset 2
  offset 3
  offset 4
```

If the consumer has processed through offset 2 and commits offset 3, on the next startup the group resumes from offset 3. If the application stops before committing offset 3, the group may re-read offset 2.

Two critical moments in a single processing cycle:

1. **Business processing:** the application performs work with the record, such as updating an order status or writing data to a database.
2. **Offset commit:** the consumer group saves the next position to read.

Delivery semantics are governed primarily by the order of these two moments.

## 2. At-Most-Once: Commit First, Process Second

At-most-once means a record is processed no more than once according to consumer group progress. To achieve this behavior, the consumer acknowledges the offset before performing business tasks.

```text
Poll record
    |
    v
Commit offset
    |
    v
Business processing
    |
    v
Next poll
```

If the application stops after committing but before finishing processing, the group will not re-read that record. Consequently, the business task may be missed.

| Failure Scenario | Outcome |
| --- | --- |
| Stops before commit | Record may be re-read; at-most-once was not yet reached for this attempt |
| Commit succeeds, then stops before processing | Record is not re-read; task may be lost |
| Processing completes | Record is processed once per committed progress |

At-most-once suits cases where losing some data is less severe than duplicate processing—such as non-critical telemetry metrics, regenerable measurement data, or best-effort notifications. It is unsuitable for business flows where skipping a record could cause discrepancies in money, inventory, or order states.

## 3. At-Least-Once: Process First, Commit Second

At-least-once means the consumer keeps attempting to process until progress is confirmed. The application processes the record first; only when processing succeeds does it commit the offset.

```text
Poll record
    |
    v
Business processing
    |
    v
Commit offset
    |
    v
Next poll
```

If the application stops after business work completes but before committing, the record will be re-read. Therefore, the business task may run multiple times. This is the source of duplicates in at-least-once.

| Failure Scenario | Outcome |
| --- | --- |
| Stops before processing finishes | Offset not committed; record may be re-read |
| Processing succeeds, stops before commit | Record may be redelivered and business logic may run again |
| Processing and commit succeed | Group moves to the next offset |

At-least-once fits business flows that must avoid skipping records, such as order processing, inventory updates, or payment recording. In exchange, the consumer must tolerate duplicate deliveries using idempotency or deduplication mechanisms.

## 4. Comparing the Two Semantics

| Criterion | At-Most-Once | At-Least-Once |
| --- | --- | --- |
| Commit timing | Before business processing | After successful processing |
| Risk of missed work | Yes, if stopped after commit before processing | Lower if records remain in retention and retries continue |
| Risk of duplicate processing | Reduced by committing first | Can occur when processing finishes but commit has not succeeded |
| Idempotency requirement | Lower in the consumer, though still possibly needed from other sources | Very important |
| Suitable for | Best-effort data where partial loss is acceptable | Business logic needing complete processing and duplicate protection |
| Main trade-off | Prioritizes avoiding duplicates, accepts omissions | Prioritizes avoiding omissions, accepts retries/duplicates |

Neither option automatically guarantees business work executes "exactly once" across all systems. At-most-once prioritizes not reprocessing after committing; at-least-once prioritizes re-reading when unconfirmed. For reliable outcomes, combine delivery semantics with transactions, idempotency, and proper storage design.

## 5. Configuring Commits in Spring Kafka

The Spring Kafka listener container manages the poll loop and offset commits. Since Spring Kafka 2.3, if `enable.auto.commit` is not declared, the framework sets it to `false` so the container controls commits. The common default `AckMode` is `BATCH`.

Example of a typical at-least-once configuration:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-service
    listener:
      ack-mode: record
```

With `AckMode.RECORD`, the container commits after the listener successfully processes each record. If using `BATCH`, the container commits after successfully processing all records received in a single poll. Both follow process-then-commit, so records can be redelivered if the process stops between the two steps.

Common `AckMode` options:

| AckMode | Commit Timing |
| --- | --- |
| `RECORD` | After the listener successfully processes each record |
| `BATCH` | After all records in the poll are processed successfully |
| `TIME` | When the configured commit interval elapses, after records are processed |
| `COUNT` | When the configured processed record count is reached |
| `COUNT_TIME` | When either the time or count condition is met |
| `MANUAL` | Listener calls `acknowledge()`; commits are handled per container cycle after the related batch finishes |
| `MANUAL_IMMEDIATE` | Commits immediately when the listener calls `acknowledge()` on the consumer thread |

Manual modes still require setting `enable.auto.commit=false`. Exact behavior for batches, partial batches, and commits depends on listener type and Spring Kafka version; check the documentation for your version when using manual acknowledgments.

## 6. At-Least-Once with @KafkaListener

This is the straightforward pattern commonly used for business consumers: only when the listener finishes normally does the container commit according to `AckMode`.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-service")
    public void onMessage(String eventJson) {
        orderService.createOrderProjection(eventJson);
    }
}
```

With `AckMode.RECORD`, if `createOrderProjection` throws an exception, the listener container does not commit that record's offset as a successful processing. The error handler can retry, recover, or forward the record to a DLT per configuration. If processing wrote to a database yet the process stopped before commit, the record may be redelivered; `OrderService` must be capable of preventing duplicate processing.

If the listener returns normally while business logic merely logs an error and ignores it, the container may treat the record as succeeded and commit the offset. Never swallow exceptions if you want the container to retry.

## 7. At-Most-Once with Manual Immediate Acknowledgment

To achieve at-most-once, a listener can commit the offset before invoking business logic using `MANUAL_IMMEDIATE`:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: telemetry-processor
    listener:
      ack-mode: manual_immediate
```

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class TelemetryListener {

    private final TelemetryService telemetryService;

    public TelemetryListener(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @KafkaListener(topics = "telemetry.samples")
    public void onMessage(String payload, Acknowledgment acknowledgment) {
        acknowledgment.acknowledge(); // Commit before processing.
        telemetryService.recordBestEffort(payload);
    }
}
```

In `MANUAL_IMMEDIATE`, when `acknowledge()` is called on the consumer thread, the container commits immediately according to sync/async commit settings. If the process stops after acknowledgment but before `recordBestEffort` completes, the record will not be replayed for the group. This is the missed-work risk of at-most-once.

Use this approach only when business rules tolerate omissions. If controlled pre-commit is needed, account for commit failures, rebalances, and shutdown; never assume calling `acknowledge()` always means the broker persisted the offset if the commit fails.

## 8. Why Is Auto Commit Not a Safe Default?

The Kafka consumer client has the `enable.auto.commit` property. When enabled, the client automatically commits offsets on the `auto.commit.interval.ms` schedule, without tightly coupling commit timing to whether the listener has finished business processing.

Risk example:

1. The consumer polls a batch of 100 records.
2. The application has finished processing only 20 records.
3. Auto commit writes the offset of the polled batch.
4. The application stops before processing the remaining 80 records.

On restart, the group may start after the committed offset; unprocessed records are skipped. Conversely, if processing completes but the process stops before the next auto commit, records may be redelivered.

Therefore, enabling auto commit does not automatically deliver at-most-once or at-least-once for business processing. With Spring Kafka listener containers, keep `enable.auto.commit=false` and use `AckMode`/transactions to bind commits to the processing cycle.

## 9. How Retries Affect Delivery Semantics

Retries are part of at-least-once. When a listener throws an exception, the container can retry the record via the error handler. If retries still fail, the application can:

- Continue retrying with backoff.
- Stop or pause partition processing depending on strategy.
- Move the record to a dead-letter topic (DLT) after exhausting attempts.
- Record error state for manual handling.

During retries, the same record can pass through the listener multiple times. If an earlier attempt created a side effect without committing the offset, the next attempt may repeat that side effect. Thus, retries are safe only when operations are idempotent or protected against duplicates.

Routing a record to a DLT is a form of recovery. Once recovery succeeds and the source offset is committed, the group moves forward. Monitor the DLT and maintain a handling/replay procedure; a DLT does not automatically roll back partially executed business effects.

## 10. Idempotency: Making At-Least-Once Safer

Idempotency means executing the same request multiple times produces the same business outcome as executing it once. For Kafka events, a common approach is assigning a unique `eventId` to each event and recording the processed marker in the same database transaction as the business update.

Example inbox table:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Pseudo-code processing within one database transaction:

```java
@Transactional
public void handle(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return; // Event has already been processed previously.
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` must be implemented with a unique constraint or an atomic insert/upsert statement—not merely a `SELECT` followed by `INSERT`, because two consumers can run concurrently. Marking the event and updating business data must belong to the same database transaction; splitting the two operations risks marking success while the business update fails, or vice versa.

When the listener completes, the container commits the Kafka offset. If the application stops after the database commit but before the Kafka offset commit, the record is redelivered; next time `eventId` already exists, so the business update does not execute again.

Other idempotency strategies include:

- Upserting by aggregate ID and version.
- Conditional state transitions, e.g., moving an order from `CREATED` to `PAID` only if the current state matches.
- Using event IDs as unique keys for creation commands.
- Using inbox/outbox when coordinating databases with Kafka.

## 11. Distinguishing Offset Commits from Producer Durability

At-most-once and at-least-once on the consumer describe the relationship between business processing and offset commits. They do not replace producer and broker durability settings.

If a producer sends records with `acks=0`, the producer does not wait for broker acknowledgment. If the broker never received the record, the consumer cannot process that record. For critical data, consider `acks=all`, an appropriate replication factor, and `min.insync.replicas` to increase write durability.

Retention also affects at-least-once capability. If a consumer is down longer than the retention period and unread records are deleted, the group cannot retry those records. Thus, at-least-once assumes data still exists and the consumer can resume reading.

## 12. Does Exactly-Once Replace At-Least-Once?

Kafka transactions and Spring Kafka support EOS for read-process-write flows between Kafka topics: output records and input offsets are committed in the same transaction. Downstream consumers should use `isolation.level=read_committed` to read only committed output.

EOS does not mean the listener method is invoked only once. A listener can still re-run after rollbacks or errors. It also does not automatically encompass databases, HTTP services, emails, or external side effects outside Kafka. With databases, transactional outbox/inbox or idempotency is usually still needed to ensure consistency.

You can view the relationship as follows:

| Mechanism | Primary Guarantee |
| --- | --- |
| At-most-once | No reprocessing after offset is acknowledged; tasks may be missed |
| At-least-once | Can re-read until committed; duplicate handling needed |
| Kafka EOS | Kafka output and input offsets commit atomically in a transaction; code may still re-run |
| Business idempotency | Multiple deliveries of the same event do not create multiple business effects |

In many systems, at-least-once combined with idempotency is the simpler and more practical choice. EOS fits when atomicity between offsets and Kafka output is needed, yet it does not eliminate the need for idempotency on external side effects.

## 13. Choosing AckMode by Requirement

| Requirement | Suggested Approach |
| --- | --- |
| Simple at-least-once for a record listener | `enable.auto.commit=false`, `AckMode.RECORD` |
| Commit by poll batch to reduce commit frequency | `enable.auto.commit=false`, `AckMode.BATCH` |
| Listener decides when to acknowledge after processing | `MANUAL` or `MANUAL_IMMEDIATE`, call acknowledge after business logic succeeds |
| Accept record loss to reduce reprocessing risk | Commit before processing with `MANUAL_IMMEDIATE`, understanding the risk |
| Read, process, and write to Kafka with atomic offsets/output | Container transactions and EOS V2 |

With `TIME`, `COUNT`, and `COUNT_TIME`, the container batches commits by time/count conditions after processing. They still follow the process-before-commit model; the larger the uncommitted interval or record count, the wider the potential re-read window when the process fails.

## 14. Testing Delivery Semantics

Do not test only that a listener is called once under normal conditions. Simulate stop points between business processing and offset commits.

### Testing at-least-once

1. Send an event with a fixed `eventId`.
2. Have the listener write the business outcome to the database.
3. Make the listener fail or stop the process before the offset is committed.
4. Restart the consumer and verify the record is redelivered.
5. Verify the unique event ID ensures the business update takes effect only once.

### Testing at-most-once

1. Send an event to a topic.
2. Have the listener commit the offset before calling the business service.
3. Make the business service fail after commit.
4. Restart the consumer.
5. Verify the group does not re-read the committed record and the task is skipped per the trade-off.

### Testing EOS

1. Send a record to an input topic.
2. Have the listener send output inside a Kafka transaction.
3. Verify a `read_committed` consumer sees the output when the transaction commits.
4. Force the listener to throw an exception after sending output.
5. Verify output from the aborted transaction is not visible to the `read_committed` consumer.

These tests should await assignments, commits, and redeliveries using bounded-timeout conditions. Avoid short fixed `Thread.sleep` calls to draw conclusions about offsets or transactions.

## 15. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Committing before business processing yet expecting no record loss | Records can be skipped after a crash | Use process-before-commit if loss is unacceptable |
| Processing before committing without idempotency | Side effects may repeat | Use event IDs, unique constraints, or upserts |
| Enabling auto commit on a slow listener | Offsets can advance before business completion | Let the Spring container manage commits |
| Catching exceptions and returning normally | Container may commit the failed record | Rethrow exceptions or use intentional recovery |
| Assuming DLT means the error is resolved | Failed records may be forgotten | Monitor DLT and build a replay process |
| Assuming Kafka EOS covers databases | DB and Kafka can still diverge | Use outbox/inbox or idempotency |
| Retention is too short | Unread records may be deleted before the consumer returns | Set retention longer than outage and backlog drain duration |

## 16. Conclusion

At-most-once commits offsets before processing: it lowers the risk of duplicate processing but can skip tasks if the application stops after committing. At-least-once processes first and commits second: it lowers the risk of omissions while records remain in retention and retries run, though records may be redelivered if the process stops before committing.

With Spring Kafka, `AckMode.RECORD` or `BATCH` alongside `enable.auto.commit=false` is normally the foundation for at-least-once. Use pre-processing commits only when the business genuinely tolerates data loss. For flows requiring complete processing, combine retries with idempotency/deduplication; when atomic Kafka output and input offsets are required, consider container transactions with EOS V2. Delivery semantics, producer/broker durability, and database consistency must be designed together.

## References

- [Spring Kafka — Message Listener Container: Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
