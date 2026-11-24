# Auto Commit and the Risk of Incomplete Processing

## 1. What Are Offset Commits and Auto Commit?

Kafka stores records in a topic by partition. Consumers read records and track their processed position using offsets. When a consumer commits an offset, it saves the next position to read for the combination of consumer group, topic, and partition.

For example, after processing a record with offset `40`, a consumer typically commits `41`. When the consumer restarts, the group can resume reading from the committed offset if that offset is still valid.

Kafka supports two common ways to manage commits:

- **Auto commit:** The Kafka consumer client automatically commits offsets at a configured interval. The client does not know whether the listener has completed its business logic.
- **Application/container-managed commit:** The application or Spring Kafka listener container decides when to commit based on processing results, ack mode, or acknowledgment calls.

Auto commit can reduce offset management code, but it creates risk when commit progress is not tied to the completion of business processing.

## 2. How Auto Commit Works

When `enable.auto.commit=true`, the Kafka consumer automatically commits offsets at the interval `auto.commit.interval.ms`. The offset reflects the consumer's read position, which advances when `poll()` returns records; it is not a confirmation signal that the listener has finished each record. The actual commit timing is tied to the poll loop and the Kafka client's mechanism, not to business results.

A single `poll()` can return multiple records across multiple partitions. Offsets are tracked separately per partition. For example, one poll returns:

| Partition | Records Received | Corresponding Next Offset |
|---|---|---:|
| P0 | 40, 41, 42 | 43 |
| P1 | 18, 19 | 20 |

If auto commit saves these offsets, the group can resume from P0 offset 43 and P1 offset 20. If the application keeps polling while work from the previous poll is still running asynchronously, the offset can advance past records that have not finished processing. Kafka does not know the completion status of individual business tasks.

`auto.commit.interval.ms` controls the interval between auto commits. This property only applies when `enable.auto.commit=true`; increasing or decreasing the interval does not make auto commit wait for the listener to finish.

~~~mermaid
flowchart TD
    A["Consumer poll()"] --> B["Receive records from partitions"]
    B --> C["Application processes records"]
    B --> D["Poll loop continues; periodic auto commit"]
    C --> E{"Processing complete?"}
    E -->|No| F["Error may occur or process may stop"]
    D --> G["Offset has been saved"]
    F --> H["Consumer restarts"]
    G --> H
    H --> I["Resume after committed offset"]
    I --> J["Unprocessed records may be skipped"]
~~~

Key point: auto commit confirms the consumer client's read position, not that business side effects have completed.

## 3. Risk of Missed Processing When Committing Too Early

Suppose a consumer receives three consecutive records in the same partition:

| Offset | Work | Status |
|---:|---|---|
| 40 | Update projection for order A | Completed |
| 41 | Update projection for order B | In progress |
| 42 | Update projection for order C | Not processed |

If the application processes records asynchronously and continues polling, auto commit may save the next offset as `43` while work for records 41 and 42 is still incomplete. If the consumer fails after the commit, the group restarts from offset 43 and those two records are not redelivered according to the committed progress. With a synchronous poll-and-process loop, the application typically finishes the batch before the next poll; if it stops before committing, records can be re-read. Therefore, the risk of skipping records is especially pronounced when the application does not wait for processing tasks from the previous poll.

This is an at-most-once scenario for the incomplete work: the offset has advanced before business changes are durable. The consequence can be missing projection data, an un-updated order, or a business processing step that never runs.

The risk is especially notable when:

- A record in the middle of a batch throws an exception.
- The application continues polling while processing tasks from the previous poll are still running asynchronously.
- A poll contains multiple records dispatched to an executor/queue without waiting for all work to complete.
- A record in the middle of a batch throws an exception and the consumption flow continues advancing without handling the failed offset according to an appropriate policy.
- The process is killed or the server loses power while work is still running.
- The listener offloads work to a background thread and returns immediately.
- The application continues polling while processing tasks from the previous poll are still running asynchronously.
- A poll contains multiple records dispatched to an executor/queue without waiting for all work to complete.
- A record in a poll fails, yet the consumer continues advancing its read position without retrying/seeking or recovering that record properly.
- The process is killed or the server loses power after the offset has been committed but before background work completes.
- The listener offloads work to a background thread and returns immediately.

Auto commit does not distinguish between records that succeeded, are in progress, or have not started. Therefore, auto commit should not be enabled for business flows that need to guarantee processing completion before confirming offsets.

## 4. Risk of Duplicate Processing When Committing Too Late

Auto commit can also create the opposite scenario. The application has processed a record successfully and written data to the database, but the consumer stops before the new offset is committed.

For example:

1. The consumer receives record offset 40.
2. The application updates the database successfully.
3. The process stops before the next auto commit.
4. The consumer restarts from the old offset.
5. Record offset 40 is received and processed again.

In that case, the side effect can occur twice. This is an at-least-once risk: the record is redelivered to avoid data loss, so the application must tolerate duplicates.

| Time of Stop | Offset State | Possible Consequence |
|---|---|---|
| After commit, before processing finishes | Offset has advanced | Incomplete processing may be skipped |
| After processing finishes, before commit | Offset has not advanced | Record is received again, possible duplicate processing |
| After successful processing and commit | Offset has advanced | Group resumes from the next record |

Therefore, auto commit does not guarantee exactly-once. Depending on when a failure occurs, the application can lose incomplete processing or repeat a completed side effect.

## 5. Auto Commit in Raw Kafka Client vs. Spring Kafka

It is important to distinguish the raw Kafka consumer client's default from how the Spring Kafka listener container manages offsets.

With a directly created `KafkaConsumer`, the Kafka client's `enable.auto.commit` property defaults to `true`. When using the Spring Kafka listener container, starting from Spring Kafka 2.3, the container automatically sets auto commit to `false` if the application does not explicitly declare this property. The container uses its own commit mechanism based on `AckMode`.

If the application actively configures `enable.auto.commit=true`, the Kafka client still commits according to its own mechanism and poll rhythm; committing is not based on the listener's processing result. In particular, if the listener dispatches work to an executor and returns, or the application continues polling before prior tasks finish, the consumer position can advance ahead of business progress. This conflicts with the goal of having the container acknowledge offsets based on listener outcomes.

Example of a risky configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: true
      properties:
        auto.commit.interval.ms: 1000
~~~

With the configuration above, the client is allowed to auto commit on a one-second interval. A short interval does not increase safety. The risk of missed records becomes clear when the application keeps polling or advancing the read position while work for earlier records is still incomplete; a synchronous listener that blocks the consumer thread until processing completes behaves differently from a listener that offloads tasks to the background and returns.

With a listener container, let the container manage commits:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
~~~

In this configuration:

- `enable-auto-commit: false` disables the Kafka client's auto commit.
- `ack-mode: record` instructs the container to commit after each record listener processes successfully.
- `auto-offset-reset: earliest` only determines the starting position when the group has no valid offset; it does not overwrite committed offsets.

If you want to process and acknowledge per poll, you can use `ack-mode: batch`. This is the common default mode of the Spring Kafka listener container. Choose `record` when you need commits close to each individual record; choose `batch` when you accept acknowledging after all records from a poll have been processed successfully.

## 6. Safe Commit Configuration with AckMode

When `enable.auto.commit=false`, the Spring Kafka listener container manages commit timing. Common modes:

| AckMode | When Does the Container Acknowledge Offsets? | Notes |
|---|---|---|
| `RECORD` | After each record listener processes successfully | For record listeners |
| `BATCH` | After successfully processing all records from a poll | Suitable for poll-level processing; common default |
| `TIME` | When the configured time interval elapses and there are offsets to commit | Batches commits by time |
| `COUNT` | When the configured record count is reached | Batches commits by count |
| `COUNT_TIME` | When either the record count or time threshold is reached | Combines both conditions |
| `MANUAL` | After the listener calls `acknowledge()`; the container commits periodically | Application explicitly acknowledges |
| `MANUAL_IMMEDIATE` | Commits immediately when `acknowledge()` is called on the consumer thread | Requires controlling which thread calls acknowledgment |

With `RECORD`, the listener must complete its work synchronously before returning. If the listener throws an exception, the error handler handles retry or recovery; the container does not treat that invocation as successful.

Listener example:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService orderProjectionService;

    public OrderProjectionListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreatedEvent event) {
        // Return only after the business operation completes.
        orderProjectionService.apply(event);
    }
}
~~~

If business logic needs to decide when to acknowledge, manual acknowledgment can be used:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "manual-order-processor"
    )
    public void handle(
            OrderCreatedEvent event,
            Acknowledgment acknowledgment) {

        orderService.apply(event);
        acknowledgment.acknowledge();
    }
}
~~~

A manual listener needs a container factory configured with ack mode `MANUAL` or `MANUAL_IMMEDIATE`, while keeping `enable.auto.commit=false`. Only call `acknowledge()` after the required work has completed.

## 7. Asynchronous Listeners Can Commit Too Early

A common mistake is having a listener merely submit the event to an executor or queue and return:

~~~java
@KafkaListener(topics = "orders", groupId = "order-processor")
public void handle(OrderCreatedEvent event) {
    executor.submit(() -> orderService.apply(event));
    // The listener has returned even though background work is not yet complete.
}
~~~

With container-managed acknowledgment, a normal return from the listener method can cause the container to acknowledge the offset according to the ack mode. The background task may fail later while the record has already been committed.

If asynchronous processing is required, the acknowledgment lifecycle must be designed explicitly. One option is to use manual acknowledgment and acknowledge only after the task completes; however, you must satisfy the thread requirements of `MANUAL_IMMEDIATE`, configure `asyncAcks` if using out-of-order acknowledgments, and handle cases where the consumer is stopped while background tasks are still running. Do not block the consumer thread indefinitely or commit offsets arbitrarily from callbacks.

In many applications, a simpler and more controllable approach is to complete business processing inside the listener before returning. If higher throughput is needed, scale concurrency/partitions or move to a durable worker model with persisted state.

## 8. Offset Commits Are Not Database Transactions

`AckMode` only controls Kafka progress. It does not automatically create an atomic transaction between committing offsets and updating a database.

Two scenarios must be handled:

- Database commit succeeds, but the consumer stops before committing the offset: the record may be redelivered.
- Offset is committed before the database completes: the record may be skipped even though business changes were not saved.

For consumers that write to a database, design them to be idempotent. A common approach is to include a unique `eventId` in the payload and store the processed ID alongside the business change in the same database transaction. If the event ID already exists, the consumer skips the duplicate effect.

~~~java
@Transactional
public void applyOnce(OrderCreatedEvent event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderProjectionRepository.apply(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId())
    );
}
~~~

In practice, uniqueness must be enforced with a database unique constraint rather than relying solely on an `exists` check, because multiple consumers or retries can run concurrently.

If you need to guarantee that database changes and Kafka event publishing are recorded together, explore the Transactional Outbox pattern. If the consumer needs to coordinate Kafka processing and database writes, an Inbox pattern or appropriate transaction design can be used. Never treat auto commit as a transaction mechanism for business data.

## 9. Testing and Observing Auto Commit Risks

You should test failure windows instead of only verifying that the listener is invoked:

| Scenario | What to Observe |
|---|---|
| Consumer continues polling while tasks from the previous poll are incomplete | Offsets may advance before business logic completes |
| Listener throws an exception mid-poll | Verify whether the failed record is skipped due to an already committed offset |
| Process stops after writing to database but before commit | Whether the record is redelivered and whether business logic handles duplicates safely |
| Manual acknowledgment called only after processing completes | Offsets do not advance before acknowledgment is called |
| Error handler retries and succeeds | Offsets are acknowledged after processing/recovery per configuration |

You can use Embedded Kafka or Testcontainers, send records with distinct `eventId`s, and intentionally make the listener slow or throw exceptions. Stop and restart the consumer, then inspect:

- Committed offsets per partition.
- Which records are redelivered.
- How many times side effects are executed.
- Consumer lag and error handler logs.

Use the Kafka CLI to check group progress:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
~~~

In production, monitor consumer lag, listener processing duration, commit latency, retry counts, and listener errors. If auto commit is enabled unexpectedly, it should be detected via effective configuration and consumer startup logs.

## 10. Checklist to Prevent Committing Incomplete Processing

- [ ] Understand the difference between the raw Kafka client and the Spring Kafka listener container.
- [ ] For listener containers, keep `enable.auto.commit=false`.
- [ ] Choose `AckMode.RECORD`, `BATCH`, or manual acknowledgment based on your processing model.
- [ ] Only acknowledge offsets after required business logic has completed.
- [ ] Do not submit background tasks and return without managing acknowledgment.
- [ ] Distinguish missed processing from early commits vs. duplicates from completing processing before committing.
- [ ] Design idempotency using event IDs and unique constraints when writing to a database.
- [ ] Do not confuse offset commits with database transactions or exactly-once processing.
- [ ] Test slow listeners, exceptions, restarts, and recovery.
- [ ] Monitor committed offsets, consumer lag, and processing duration.

Auto commit is convenient for simple consumers, but it does not know whether business work has completed. For Spring Kafka applications using `@KafkaListener`, disable auto commit and let the listener container manage offsets via `AckMode`. Combining synchronous processing or controlled acknowledgment with an error handler and idempotent business logic reduces the risk of skipping unfinished work and duplicate processing on consumer restarts.
