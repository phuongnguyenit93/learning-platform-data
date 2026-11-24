# Committing Offsets Before vs. After the Listener

## 1. Why Does Offset Commit Timing Matter?

A Kafka consumer reads records from partitions and tracks progress per consumer group. When an application processes a record, two distinct actions occur:

1. Executing business work, such as updating a database, performing calculations, or calling another service.
2. Committing the offset so Kafka knows where the group will resume reading next.

These two actions normally do not share a single transaction. Therefore, the ordering between listener execution and offset commits determines how the application behaves when a process crashes, a listener throws an exception, a broker disconnects, or a consumer rebalances.

There are two fundamental choices:

- **Commit before the listener:** persist read progress before running business logic. If the application stops after committing yet before finishing processing, the record may be skipped on the next run.
- **Commit after the listener:** persist progress only after the listener completes successfully. If the application stops after side effects yet before committing, the record may be redelivered and processed again.

This is a trade-off between risking lost records and risking duplicate processing. For most business listeners, committing after successful processing is usually preferable, paired with idempotent processing to tolerate redelivery.

## 2. Understanding What a Committed Offset Is

### 2.1. Committed Offset Is the Next Position to Read

Each partition has its own offset sequence. A consumer group stores committed offsets by the combination of group ID, topic, and partition. The committed offset value is normally the next position the consumer needs to read, not the offset of the last processed record.

For example, suppose a consumer processes record offset 10 successfully and commits offset 11:

~~~text
Partition orders-0

Offset:       8    9    10   11   12   13
Record:       A    B     C    D    E    F
                         |
                         +-- processed record: 10
                              committed offset: 11
                              next read position: 11
~~~

When offset 11 is committed, Kafka understands the group has confirmed progress past record 10. If the consumer restarts, it resumes from offset 11 while that offset remains valid.

### 2.2. Consumer Position Differs from Committed Offset

A consumer may have fetched or processed several records in memory without committing yet. Distinguish among:

- **Consumer position:** the next position the consumer will read in the current session.
- **Committed offset:** the position durably stored for the group on Kafka.
- **Log end offset:** the position immediately after the partition's newest record.
- **Log start offset:** the earliest position still retained in the log.

Consumer position can advance when poll returns records even if the committed offset has not changed. If the process stops before committing, another consumer can re-read from the older committed offset.

### 2.3. Offsets Are Stored per Partition

A group can process multiple partitions, and each partition maintains its own committed offset. There is no single offset representing the entire topic.

If a listener processes in parallel or runs asynchronous tasks, the application must ensure it commits only an offset reflecting contiguously completed records in the partition's required order. You cannot commit past an unfinished record and expect Kafka to automatically know that record is still pending.

## 3. Committing Before the Listener: At-Most-Once

### 3.1. Execution Sequence

Committing before the listener means the application persists the next record's offset before executing business side effects.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant L as Listener
    participant D as Database

    C->>K: Fetch record offset 10
    K-->>C: Record 10
    C->>K: Commit offset 11
    K-->>C: Commit success
    C->>L: Invoke listener(record 10)
    L->>D: Update business data
    D-->>L: Success
    L-->>C: Listener returns
~~~

If the application crashes after committing offset 11 yet before the database update finishes, the next run starts from offset 11. Record 10 is not redelivered under that committed offset, even though business logic may never have finished.

### 3.2. Data-Loss Window

~~~text
Fetch record 10
      |
      v
Commit offset 11
      |
      |  <-- process crashes here
      v
Listener processes record 10
      |
      v
Database commit
~~~

If a crash happens between the offset commit and business processing, the group has already moved past record 10 while side effects never occurred. This is the risk of lost processing (message loss from a business perspective).

Thus, committing before the listener generally corresponds to at-most-once delivery: a record might go unprocessed if a failure happens after commit, while the consumer will not actively redeliver that record merely because the listener did not finish.

### 3.3. When Might Committing Before Be Appropriate?

Some pipelines can tolerate skipping occasional records better than duplicate processing:

- Telemetry or metrics aggregated across many sources where dropping a small sample is acceptable.
- Non-critical notifications where duplicates cause worse impact than missing one notification.
- Ephemeral data that can be reconstructed from another source.
- A downstream system that already has independent compensation or snapshotting.

This must be an intentional business decision. Never pick commit-before just to avoid duplicates when records carry payment commands, order state transitions, or events requiring complete processing.

## 4. Committing After the Listener: At-Least-Once

### 4.1. Execution Sequence

Committing after the listener means persisting the offset only once the listener method finishes successfully according to the acknowledgment mode.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant L as Listener
    participant D as Database

    C->>K: Fetch record offset 10
    K-->>C: Record 10
    C->>L: Invoke listener(record 10)
    L->>D: Update business data
    D-->>L: Success
    L-->>C: Listener returns successfully
    C->>K: Commit offset 11
    K-->>C: Commit success
~~~

If the listener throws an exception before finishing, the offset is not committed along the normal success path. The error handler can retry, recover, or route the record to a dead-letter topic depending on configuration.

### 4.2. Duplicate-Processing Window

~~~text
Fetch record 10
      |
      v
Listener processes record 10
      |
      v
Database commit
      |
      |  <-- process crashes here
      v
Commit offset 11
~~~

If the process crashes after the database commits yet before the Kafka offset is committed, the group still holds the older committed offset. When the consumer resumes, record 10 may be redelivered. The database may receive the exact same operation a second time.

This is at-least-once delivery: the application prioritizes never skipping records, while a record can be processed more than once. Listeners need idempotency so receiving the same event again does not create duplicate side effects.

### 4.3. Why Is At-Least-Once Usually Chosen?

In many business systems, reprocessing an event can be detected and controlled using event IDs, unique constraints, or upserts. Losing an event can be far harder to detect and recover from.

Committing after the listener establishes a clear boundary: advance offsets only when the listener reports success. However, it does not merge the database and Kafka into a single transaction. Idempotency or coordination mechanisms must be designed whenever listeners write to external systems.

## 5. Comparing Committing Before vs. After the Listener

| Criterion | Commit Before Listener | Commit After Listener |
|---|---|---|
| Offset persistence timing | Before side effects | After listener completes successfully |
| Typical delivery semantics | At-most-once | At-least-once |
| Crash after commit, before processing | Record processing may be lost | Not applicable before commit |
| Crash after side effects, before commit | Usually no redelivery past advanced offset | Can redeliver and cause duplicates |
| Idempotency requirement | May still be needed for producer retries | Critical for redeliveries |
| Appropriate for | Droppable data | Business workflows requiring complete processing |
| Primary risk | Lost processing | Duplicate processing |

No single commit timing eliminates both failure windows when side effects reside outside Kafka. High reliability requires designing offsets, transactions, and business side effects together.

## 6. How Does Spring Kafka Manage Offset Commits?

### 6.1. The Listener Container Orchestrates Commits

With **@KafkaListener**, applications typically do not call **poll()** or commit offsets themselves. Spring Kafka creates a listener container that manages the consumer, polling, dispatching records to the listener, exception handling, and committing offsets per configuration.

In Spring Kafka, **enable.auto.commit** is normally set to **false** unless explicitly configured otherwise by the application. Since Spring Kafka 2.3, the framework defaults this so the container can manage commits. If auto-commit is enabled explicitly, commits are performed by the Kafka client under auto-commit mechanics and are no longer tightly bound to each listener invocation's success.

For business listeners, let the container manage commits and pick a suitable acknowledgment mode. This prevents the consumer from committing on a timer while the listener is still executing side effects.

### 6.2. Acknowledgment Modes

Spring Kafka provides these common commit modes. Names and details can vary by version; consult Javadoc when upgrading.

| AckMode | Commit Timing |
|---|---|
| **RECORD** | After each individual record is successfully processed by the listener |
| **BATCH** | After all records in a single poll are processed |
| **TIME** | When the configured duration elapses and offsets are pending commit |
| **COUNT** | When the processed record count reaches the threshold |
| **COUNT_TIME** | When either the record-count or time threshold is reached |
| **MANUAL** | Listener calls acknowledge; container commits per manual-mode rules |
| **MANUAL_IMMEDIATE** | Commits immediately when acknowledge is called on the consumer thread; calls from other threads follow container mechanics |

**BATCH** is the common default mode of the listener container. **RECORD** fits record listeners when you want commits after each successful record. For batch listeners, understand that the listener receives the entire batch; commits normally tie to batch processing outcomes.

### 6.3. How Do RECORD and BATCH Differ?

Suppose a poll returns record offsets 10, 11, and 12 from the same partition.

With **RECORD**:

~~~text
Listener processes 10 successfully -> commit offset 11
Listener processes 11 successfully -> commit offset 12
Listener processes 12 successfully -> commit offset 13
~~~

If an error occurs on record 11, offset 11 is not committed by that attempt. Record 10 may already be committed, while 11 and subsequent records are handled according to the error handler and consumer state.

With **BATCH**:

~~~text
Poll returns 10, 11, 12
        |
        v
Listener processes records
        |
        +-- All succeed
        |       |
        |       v
        |   Commit offset 13
        |
        +-- Error occurs
                |
                v
           Error handler handles
~~~

**BATCH** reduces commit count and can improve efficiency at high throughput. In return, if a batch fails, the range of records requiring retry or recovery may be larger depending on the error handler.

## 7. Spring Boot Configuration for Committing After the Listener

A basic configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

Each property plays a distinct role:

- **enable-auto-commit: false** lets the container coordinate commits.
- **ack-mode: record** commits after each successful record listener invocation.
- **auto-offset-reset** is used only when the group has no valid offset; it does not determine committing before or after the listener.
- Serializers/deserializers must match what producers emit.

Synchronous listener example:

~~~java
@Component
@RequiredArgsConstructor
public class OrderListener {

    private final OrderService orderService;

    @KafkaListener(
        topics = "orders",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.applyIdempotently(event);
    }
}
~~~

When the method returns normally, the container treats the invocation as successful and commits per the acknowledgment mode. If the method throws an exception, the container passes the error to the error handler; the offset is not considered succeeded merely because the listener was invoked.

## 8. Manual Acknowledgment: Listener Explicitly Signals Completion

### 8.1. MANUAL

When acknowledgment timing needs explicit control, the listener can accept an **Acknowledgment** parameter and call **acknowledge()** after completing required work.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

With **MANUAL**, calling acknowledge marks the record as processed; the container manages commits per manual-mode semantics, generally tied to finishing records from the current poll. It does not mean every acknowledge call immediately dispatches a commit request.

### 8.2. MANUAL_IMMEDIATE

If you need immediate commits when acknowledging on the consumer thread, use **MANUAL_IMMEDIATE**:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Crucially, call acknowledge only after side effects finish. Acknowledging before the database commits recreates the same data-loss window as committing before the listener.

**MANUAL_IMMEDIATE** has thread-dependent semantics. When called on the consumer thread, the container can commit immediately; when called from another thread, the acknowledgment is queued for container handling. Never call acknowledge arbitrarily from background threads without understanding your Spring Kafka version's contract.

### 8.3. Do Not Swallow Exceptions and Still Acknowledge

Example to avoid:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    try {
        orderService.apply(event);
    } catch (Exception ex) {
        log.error("Cannot process order", ex);
    }

    acknowledgment.acknowledge();
}
~~~

This code catches the error, logs it, and still acknowledges. The container is told the record finished, so the offset can advance even though business logic failed. If you want retries or DLT routing, let the exception propagate to the error handler or call acknowledge only after an intentional recovery decision.

## 9. Exception Handling and Offset Commits

### 9.1. Listener Throws an Exception

When a listener throws an exception, the container transfers control to the error handler. With **DefaultErrorHandler**, the application can configure retry counts, backoff, and a recoverer.

Key practices:

- Retry transient errors such as database timeouts or temporarily unavailable services.
- Do not infinitely retry unrecoverable data errors.
- Route records to a dead-letter topic after exhausting retries.
- Record original metadata such as topic, partition, offset, and exception for investigation.
- Consider a record recovered only once the recoverer policy finishes per configuration.

If a listener catches an exception and returns normally, the container usually treats the listener call as successful. This is a common cause of offsets committing despite failed business logic.

### 9.2. Committing When the Error Handler Recovers

When the error handler handles an error, commit behavior depends on the acknowledgment mode and error-handler properties—such as committing after handler completion and recovered-record commit policies. Some scenarios require enabling settings such as **ackAfterHandle** or **commitRecovered**; exact capabilities and requirements depend on the version and ack mode.

Do not assume routing a record to a DLT automatically means the source offset committed the way you expect. Verify both outcomes: the record was published to the DLT and consumer group progress was saved.

### 9.3. Blocking Retries vs. Retry Topics

Blocking retries execute retry attempts inside the partition processing thread. This can hold up the partition during long backoffs and delay subsequent records.

Retry topics move failed records to another topic for later reprocessing. This lets the main partition continue, though it can alter processing order: newer records with the same key may finish ahead of the retrying record.

Whichever strategy is used, offset commits must accurately reflect that the record was processed or recovered per policy. If strict per-key ordering is required, evaluate the impact of retry topics.

## 10. Database Side Effects and Kafka Offsets Are Not One Transaction

A listener typically updates a database before committing the Kafka offset:

~~~text
Kafka record
    |
    v
Listener
    |
    v
Database transaction commit
    |
    v
Kafka offset commit
~~~

If the database commit succeeds yet the offset commit fails, the record is redelivered. If the offset commits before the database commit, the application can lose processing when the database fails.

A Kafka offset commit and a database transaction are two separate operations. Choosing commit-after-listener favors at-least-once delivery, yet does not create cross-system atomicity.

### 10.1. Idempotency via Event ID

Every event should carry a stable ID, such as **eventId**. The database can store processed IDs under a unique constraint. When an event is redelivered, recording the ID detects the duplicate and prevents repeating side effects.

Conceptual example:

~~~java
@Transactional
public void applyIdempotently(OrderCreated event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Both the inbox insert and the business update must reside in the same database transaction. If the business update fails, the inbox record must also roll back so redeliveries can retry. Exact implementation depends on the database and how insert-if-absent is supported.

### 10.2. Inbox Pattern

An inbox table stores received event IDs. When the consumer receives an event:

1. Begin a database transaction.
2. Insert the event ID into the inbox with a unique constraint.
3. If the ID already exists, treat it as a redelivery and skip repeating side effects.
4. If the insert succeeds, execute the business updates.
5. Commit the database transaction.
6. The listener returns normally so the container commits the Kafka offset.

If the process crashes after step 5 but before step 6, the record is redelivered. On the next attempt, the inbox detects the existing event ID and the listener can return normally without re-running side effects.

### 10.3. Transactional Outbox

If a listener updates a database and must emit a subsequent Kafka event, a transactional outbox writes business changes and an outbox record in the same database transaction. A separate publisher reads the outbox and sends to Kafka.

Outbox does not turn Kafka offsets and databases into a distributed transaction. It creates a durable source of truth so the publisher can retry on failures. Both publishers and consumers still need idempotency because retries can produce duplicates.

## 11. Exactly-Once and Kafka Transactions

In Kafka-to-Kafka pipelines, Kafka transactions can combine sending output records with committing input offsets inside the same transaction. If the transaction commits, outputs and offsets are accepted together; if it aborts, neither is treated as partially committed.

Spring Kafka can coordinate a transactional producer factory and listener container to execute consume-process-produce within one Kafka transaction. Downstream consumers use isolation level **read_committed** to read only records from committed transactions.

This achieves exactly-once semantics within Kafka transaction boundaries. It does not cover database updates, sending emails, or HTTP calls. If the listener has side effects outside Kafka, inbox/outbox or idempotency is still required.

Never describe an at-least-once listener with database side effects as exactly-once merely because offsets are committed after the listener returns. The gap between the database commit and the offset commit still exists.

## 12. Sync vs. Async Commits

A Kafka consumer can commit offsets synchronously or asynchronously:

- **commitSync()** waits for the broker's commit response. This makes commit success or failure clear, though it can increase latency.
- **commitAsync()** sends the commit request asynchronously and receives a callback with the outcome. This cuts waiting on the calling thread, though errors and commit ordering must be handled carefully.

The Spring listener container can control commit style via container settings such as **syncCommits**. Defaults and behavior vary by version; verify the active configuration.

Low-level Kafka API example:

~~~java
consumer.commitSync(
    Map.of(
        new TopicPartition("orders", 0),
        new OffsetAndMetadata(11)
    )
);
~~~

The offset committed in this example is 11—the next position to read. When using `KafkaConsumer` directly, note that **KafkaConsumer** is not thread-safe; consumer calls must stick to the consumer-owning thread.

In Spring Kafka, let the listener container manage commits via ack modes or **Acknowledgment**. Avoid calling commit directly inside a listener without a clear offset-ownership design, as it can conflict with container-managed commits.

## 13. Rebalances and Offset Commits

When partitions are revoked, a consumer may hold processed-but-uncommitted records. Listener containers typically commit pending offsets per acknowledgment mode and rebalance callbacks before releasing partitions.

Applications can use **ConsumerAwareRebalanceListener** or equivalent rebalance callbacks to finish local work before partition handoff. Keep callbacks brief and avoid unbounded waits.

Under cooperative rebalancing, revoke callbacks may receive only the partitions being transferred. Do not assume the entire assignment is revoked. For partitions whose ownership was lost, do not attempt to commit as though the consumer still holds control.

If a listener runs asynchronous tasks, track tasks per partition. Never let stale tasks keep updating the database after the partition was assigned to another consumer; otherwise, two consumers could concurrently produce side effects for the same record.

## 14. Illustrative Configurations for Commit Choices

### 14.1. Commit After Each Successful Record

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

With a record listener, the container commits after each record is processed successfully. This is a straightforward option when minimizing the window of uncommitted records after failures.

### 14.2. Commit After an Entire Poll Batch

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

The container commits after successfully processing all records in a single poll. This reduces commit count, though a failed batch may require reprocessing a wider range depending on the error handler.

### 14.3. Manual Immediate

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

The listener calls **acknowledge()** after required side effects complete. It must be called on the consumer thread for clean immediate semantics.

Do not use **auto.offset.reset** to control commit timing. The reset policy only selects a starting point when no valid committed offset exists; ack modes and acknowledgments control persisting progress during processing.

## 15. Common Mistakes

**Committing before the database transaction completes:** offsets advance while side effects are not durable. If the process stops, records can be skipped.

**Acknowledging before processing:** the listener signals success prematurely. If downstream work fails, the container may already have committed the offset.

**Catching exceptions and returning normally:** the container does not know business logic failed and may commit per ack mode.

**Assuming commit-after-listener eliminates duplicates:** crashes after database commit yet before offset commit still cause redelivery.

**Using auto-commit for listeners needing strict control:** timer-based commits do not accurately reflect individual business execution outcomes.

**Committing offsets past unfinished records:** especially dangerous with parallel processing within the same partition; restarts can skip unfinished records.

**Committing manually inside the listener while the container also commits:** creates two offset-control paths, making progress unpredictable and error-prone.

**Assuming a successful DLT publish means the source offset committed:** inspect recoverer configuration and error-handler commit behavior.

**Confusing offset commits with deleting records:** commits only persist group progress. Records remain governed by topic retention or cleanup policies and can still be read by other groups.

## 16. Investigation Workflow for Missing or Duplicate Records

When a record is missed or processed multiple times, trace the timeline:

1. Identify the record's topic, partition, offset, and event ID.
2. Confirm whether the consumer group fetched the record.
3. Check whether the listener began processing and whether side effects committed.
4. Check committed offsets before and after processing.
5. Read exception and error-handler logs to see whether the record was retried, recovered, or skipped under policy.
6. Check whether a rebalance or restart happened between side effects and offset commit.
7. Verify whether the listener has an idempotency key, inbox, or unique constraint.
8. If the offset advanced past the record without side effects, investigate auto-commit or commit-before-listener behavior.
9. If side effects exist while the offset did not advance, check whether redelivery occurred and whether side effects are idempotency-protected.

Log event ID, group ID, topic, partition, offset, and correlation ID. Avoid logging full payloads containing sensitive data. Comparing database transaction timestamps with offset commits helps pinpoint the failure window.

## 17. Testing Commit Timing

Use test topics and dedicated consumer groups to test failure windows without affecting production data.

### Commit-After-Listener Scenario

1. Publish a record with an easily identifiable event ID.
2. Have the listener write the event ID to the database.
3. Create a controlled pause after the database commit yet before the container commits the offset.
4. Stop the process at that point.
5. Restart the consumer with the same group ID.
6. Confirm the record is redelivered from the older committed offset.
7. Confirm the inbox/unique constraint prevents side effects from running twice.

### Commit-Before-Listener Scenario

1. Use a test consumer able to commit offsets explicitly before processing.
2. Publish a new record.
3. Commit the next offset prior to side effects.
4. Stop the process before the listener completes.
5. Restart with the same group ID.
6. Confirm the consumer resumes from the committed offset and the old record is not redelivered.

### Exception Scenario

1. Have the listener throw an exception before side effects.
2. Verify the error handler retries or routes to DLT per configuration.
3. Have the listener throw an exception after side effects commit.
4. Verify the record can be redelivered and idempotent operations prevent duplicates.
5. Inspect committed offsets and DLT records after each scenario.

Tests must observe both Kafka state and database state. Checking only listener invocation logs is insufficient to prove commit timing.

## 18. Production Selection Principles

- Prefer committing after the listener completes successfully for workflows requiring complete processing.
- Use **enable.auto.commit=false** so the Spring listener container coordinates commits.
- Choose **RECORD** or **BATCH** according to processing boundaries and throughput.
- Use **MANUAL** or **MANUAL_IMMEDIATE** when explicit acknowledgment control is required.
- Acknowledge only after required side effects are durable.
- Let exceptions reach the error handler when retries or recovery are desired.
- Design idempotent listeners using event IDs, inboxes, unique constraints, or upserts.
- Never assume Kafka offsets and database transactions commit atomically together.
- Use Kafka transactions for Kafka-to-Kafka pipelines requiring atomicity; use outbox/inbox at database boundaries.
- Monitor committed offsets, consumer lag, retries, DLT, rebalances, and listener processing duration.

Committing before the listener prioritizes avoiding redelivery at the risk of lost processing if the process stops after committing. Committing after the listener prioritizes not skipping records while accepting redelivery if offsets are not yet saved. Spring Kafka provides acknowledgment modes and listener containers to coordinate commits; applications must pair them with appropriate idempotency and transactions to protect business side effects.
