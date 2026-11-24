# Offset Commit Not Behaving as Expected

Offset commits are checkpoints Kafka stores so a consumer group knows where to resume reading after a consumer restarts or partitions are reassigned to another consumer. When offsets do not advance, advance late, skip over unprocessed records, or cause records to be redelivered, the root cause usually lies in the acknowledgment mode, how the listener completes, the error handler, transactions, or consumer group rebalances.

To diagnose accurately, separate three events: the consumer polled the record, the listener finished processing, and the broker persisted the committed offset. These three moments do not necessarily coincide. A successfully processed record can still be redelivered if the commit fails; conversely, committing too early can skip records before business work finishes.

## 1. Committed Offset Is the Next Position to Read

Kafka stores offsets using the convention of the next position the consumer group will read. If a listener successfully processes the record at offset `42`, the usual committed position is `43`.

```text
Partition orders-0:

offset:       40    41    42    43    44
              |     |     |     |     |
listener:     done  done  done  next  next
                            |
committed offset --------> 43
                            |
restart will resume from 43
```

The committed offset is not the offset of the last processed record; it is the next offset to read. Thus, if a dashboard shows `CURRENT-OFFSET=43`, record `42` already lies behind the resume position per the committed offset.

A consumer also has a `position`, which is the next offset it will fetch on poll. The position can move ahead of the committed offset when the consumer has polled or processed records without committing yet. On restart, in-memory positions are lost and the group resumes from the committed offset saved on the broker.

## 2. Spring Kafka Manages Commits via `AckMode`

With listener containers, Spring Kafka manages offsets according to `ContainerProperties.AckMode`. Since Spring Kafka 2.3, if `enable.auto.commit` is not explicitly configured, the container defaults it to `false` so the container controls commits per acknowledgment mode.

| `AckMode` | When does the container commit offsets? | Common use case |
| --- | --- | --- |
| `RECORD` | After each record listener succeeds | Commit per record |
| `BATCH` | After all records in the poll succeed | Common default; reduces commit overhead |
| `TIME` | Once the configured commit time elapses, at poll processing boundaries | Cap time between commits |
| `COUNT` | Once the configured record count is processed, at poll processing boundaries | Cap records between commits |
| `COUNT_TIME` | When either time or record count condition is met | Combine both thresholds |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; commit runs at batch/poll boundaries | Listener decides which records are complete |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledged on the consumer thread; if called from another thread, queued onto the container thread | Need offset confirmed right at acknowledge |

For a record listener, `RECORD` can commit after every listener invocation. For a batch listener, the container delivers a batch in one invocation, so commit boundaries align with the batch and batch acknowledgment. Verify the actual listener type and `AckMode` rather than guessing from annotations alone.

Example configuring `RECORD`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
```

If `AckMode` is unspecified, the container typically uses `BATCH`. Switching to `RECORD` can increase commit frequency and impact throughput; weigh it alongside redelivery requirements and broker load.

## 3. Auto-Commit vs. Container-Managed Commits

Kafka consumers have `enable.auto.commit`. When enabled, the Kafka client commits offsets periodically every `auto.commit.interval.ms`, independent of when the listener finishes work. This causes confusion if the application expects commits only after business processing.

Spring Kafka listener containers disable auto-commit by default when unconfigured. Let the container manage acknowledgments and commits via `AckMode`. Avoid setting `enable.auto.commit=true` with `@KafkaListener` unless you understand the consequences and have a specific reason.

Example explicit consumer configuration:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
```

`auto-offset-reset` does not govern regular commits. It only applies when a group lacks a valid committed offset or its offset falls outside the available log range. `earliest` starts from the earliest retained data; `latest` starts from the log end; `none` causes the consumer to throw when no valid offset exists.

## 4. Manual Acknowledgment Must Be Placed at the Right Moment

When using `MANUAL` or `MANUAL_IMMEDIATE`, the listener accepts `Acknowledgment` and explicitly acknowledges the record after work completes:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "manualAckListenerFactory")
    public void onOrder(OrderCreated event, Acknowledgment acknowledgment) {
        orderService.handleAndPersist(event);
        acknowledgment.acknowledge();
    }
}
```

The factory must be configured with `AckMode.MANUAL` or `MANUAL_IMMEDIATE`. In the example, the service must finish durable side effects before acknowledging. Calling `acknowledge()` right after putting the event onto an in-memory queue can commit the offset before a worker finishes; if the application crashes, the event can be lost from the business flow.

With `MANUAL_IMMEDIATE`, calling acknowledge on the consumer thread triggers an immediate commit. If called from another thread, the container must hand the request off to the consumer thread, so the commit is no longer immediate on the caller thread. Avoid sharing `Acknowledgment` arbitrarily across threads.

## 5. Why Does the Offset Stay Unchanged Even When the Listener Succeeds?

This can be normal behavior under `AckMode`:

- With `BATCH`, the first record in a poll finished, yet the container waits for the remaining records in the poll to finish.
- With `TIME`, `COUNT`, or `COUNT_TIME`, the commit threshold may not have been reached yet.
- With `MANUAL`, the listener has not called `acknowledge()` or the poll's acknowledgments have not met commit conditions.
- With transactions, offsets take effect only when the transaction commits.
- Consumer `position` advanced while the committed offset still reflects the previous commit checkpoint.

Do not treat a committed offset standing still for a few milliseconds as an immediate bug. Inspect `AckMode`, poll processing time, commit intervals, and transaction state before concluding.

If offsets stay stuck longer than operational thresholds, check whether the listener is blocked, whether `acknowledge()` is called, whether commits fail, and whether the consumer group is rebalancing.

## 6. When the Listener Throws an Exception

If a listener throws an exception, the container does not treat that invocation as successful. `CommonErrorHandler` or `DefaultErrorHandler` decides retries, seeks, recovery, and when offsets may be acknowledged.

Common flow with `DefaultErrorHandler`:

1. Listener processes a record and throws an exception.
2. Error handler applies retries/backoff for exceptions classified as retryable.
3. If a retry succeeds, the container proceeds per `AckMode` and commit policy.
4. Once retries are exhausted or the exception is non-retryable, the recoverer handles the record, e.g., publishing to a DLT.
5. If recovery succeeds and the error handler returns normally, the recovered record's offset can be committed per error handler/container config.

`DefaultErrorHandler` has `ackAfterHandle` (enabled by default in modern versions) so the container acknowledges the record's offset once the error handler handles the failure and returns normally. `commitRecovered` requests committing the offset of recovered records under `MANUAL_IMMEDIATE`; configure `AckMode` appropriately per your Spring Kafka version's docs.

If `ackAfterHandle=false`, the container does not automatically acknowledge offsets merely because the error handler returned normally. Choose that setting only when you have a custom acknowledgment flow and test thoroughly so recovered records are not unexpectedly redelivered.

If the recoverer throws because it cannot publish to the DLT or persist the record, recovery is incomplete. Never catch and swallow recovery exceptions, or the container may mistakenly treat the record as handled.

## 7. Listener Error Handlers Can Trigger Offset Commits

`KafkaListenerErrorHandler` runs at the `@KafkaListener` adapter layer. If that handler catches an exception and returns normally, the container may treat the listener invocation as completed successfully. Offsets can then be committed under `AckMode` even though the original business work failed.

Example to avoid if you want container retries:

```java
@Bean
KafkaListenerErrorHandler unsafeSwallowingHandler() {
    return (message, exception) -> {
        System.getLogger("listener-error").log(
                System.Logger.Level.ERROR, "Listener failed", exception);
        return null; // Adapter treats the error as handled
    };
}
```

If you want `DefaultErrorHandler` to retry or recover, the listener error handler must rethrow the exception rather than returning normally. Return normally only when the handler has performed durable recovery and intentionally opts out of retries.

## 8. Commits Inside Kafka Transactions

When a listener container uses Kafka transactions, output records sent via `KafkaTemplate` and input offsets can be enrolled in the same transaction. Offsets are persisted alongside output results only when the transaction commits successfully.

```text
Begin Kafka transaction
        |
        v
Listener processes input record
        |
        v
KafkaTemplate.send(output record)
        |
        v
Send input offset into transaction
        |
        v
Commit transaction
   /             \
commit           abort
  |                |
output + offset   neither output nor offset is committed
both take effect  input may be read again
```

If the listener throws, the transaction aborts, outputs stay invisible to `read_committed` consumers, and input offsets remain uncommitted for that transaction. If a transaction times out or the producer is fenced, commit can fail even after the listener finishes running. Check the transaction coordinator, transaction ID prefix, timeouts, and rebalances.

Kafka transactions only cover Kafka resources. If a listener updates a database and then the Kafka transaction aborts, the database does not roll back automatically. Side effects outside Kafka still need idempotency or Outbox/separate transaction coordination.

## 9. Commit Failures and Record Redelivery

A commit can fail due to:

- Consumer losing partition assignments during a rebalance.
- `CommitFailedException` or `RebalanceInProgressException` when group generation changes or a rebalance is underway.
- Temporary broker/coordinator unavailability or commit request timeout.
- Transaction abort, timeout, or producer fencing.
- Application stopping before the commit is sent or acknowledged.

If the listener completed business work yet the broker never persisted the commit, the record can be redelivered after a restart or rebalance. That is why consumers must be idempotent: the same event ID can arrive multiple times without repeating side effects.

Never assume records are lost just because offsets did not advance. First confirm whether records were redelivered, routed to retry/DLT, or skipped by an offset reset. When commits fail, logs should capture group ID, topic, partition, offset, consumer ID, and commit failure reason for tracing.

## 10. Rebalances and Listener Processing Duration

A consumer group rebalances when a new consumer joins, an existing consumer leaves, subscriptions change, or a consumer misses poll deadlines. If a listener takes too long and exceeds `max.poll.interval.ms`, the broker can treat the consumer as unresponsive to the poll loop and reassign its partitions to another member.

Once partitions are revoked, offset commits can fail if the consumer lost ownership or group generation changed. This causes commit failures and record redelivery.

Inspect:

- Processing duration per record/batch vs. `max.poll.interval.ms`.
- Whether the consumer blocks on REST, databases, locks, or `Thread.sleep()`.
- Record count per poll and whether `max.poll.records` is too high.
- `session.timeout.ms`, heartbeats, and rebalance rates.
- `onPartitionsRevoked`/`onPartitionsAssigned` logs or corresponding listener/container events.

Raising `max.poll.interval.ms` does not fix a hung listener. Optimize processing, cap batch size, use controlled pause/backpressure, or offload slow work asynchronously with safe acknowledgment.

## 11. Asynchronous Acknowledgment and Ack Ordering

If a listener processes records asynchronously or multiple records from the same poll finish out of order, offset commits need careful design. Kafka stores only a single contiguous committed offset per partition. You cannot commit past an unfinished record and still expect Kafka to redeliver that earlier record reliably.

Spring Kafka supports `asyncAcks` in modern versions to allow out-of-order acknowledgments for records from the same poll. The container buffers acknowledgments until gaps close and may pause the consumer while waiting. This enables concurrent processing while potentially increasing redelivery scope after crashes; test thoroughly with your exact version.

With async return types supported by Spring Kafka, the container can tie acknowledgment to future/result completion. Acknowledge only when the task genuinely finishes. Never return normally before a future completes while hoping the container magically tracks background workers.

## 12. Distinguishing `auto.offset.reset` from Commits

`auto.offset.reset` only decides where to start when a group lacks a valid committed offset. It does not perform ongoing commits and does not repair a failing commit.

| Value | Behavior when no valid offset exists |
| --- | --- |
| `earliest` | Reads from the earliest offset still retained in the log |
| `latest` | Starts from the end of the log, skipping older records |
| `none` | Throws an error if no valid committed offset is found |

If a committed offset falls behind the log start offset because retention deleted old segments, the consumer can hit `OffsetOutOfRangeException`; the reset policy may then apply. Do not change `auto.offset.reset` to mask commit failures. Determine whether the group lacks an offset, hit an out-of-range offset, or failed to commit.

## 13. Diagnosing with `kafka-consumer-groups`

Inspect committed offsets and lag by group:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group order-service
```

Columns to check:

| Column | Meaning |
| --- | --- |
| `CURRENT-OFFSET` | Group's committed offset; next position to read |
| `LOG-END-OFFSET` | End offset used by the tool to calculate lag |
| `LAG` | Offset gap between log end and committed offset |
| `CONSUMER-ID` | Consumer currently assigned the partition |
| `CLIENT-ID` | Client ID identifying the consumer |

If `CURRENT-OFFSET` stays flat, compare it with consumer position/record rates and commit logs. If no consumer ID appears, the group may have no active members or partitions may be unassigned. Check group state:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group order-service `
  --state
```

Option names and output columns can vary across Kafka CLI versions. Combine CLI output with Spring Kafka container logs and commit metrics to pinpoint the cause.

## 14. Offset Commit Investigation Checklist

Follow these steps in order to avoid changing settings blindly:

1. Confirm the exact `group.id`, topic, and partition; check whether the group is stable or rebalancing.
2. Inspect the listener container's `AckMode`; determine whether commits happen per record, batch, time/count, or manually.
3. Check `enable.auto.commit`; with standard Spring Kafka containers, let the container manage commits.
4. Determine whether the listener completed normally, threw an exception, or had a listener error handler swallow the exception.
5. For manual ack, locate where `acknowledge()` is called and confirm it runs after durable side effects complete.
6. With an error handler, check retries, recoverer, `ackAfterHandle`, and `commitRecovered`.
7. With transactions, check transaction commit/abort, timeouts, and fencing.
8. Check commit exceptions, rebalances, `max.poll.interval.ms`, and listener execution times.
9. Compare committed offsets against consumer position and end offsets; do not confuse position progress with committed lag.
10. When records are redelivered, check idempotency and event IDs to prevent duplicate side effects.

## 15. Common Misconfigurations and Errors

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Listener finishes yet offset stays unchanged | `AckMode` `BATCH`, `TIME`, `COUNT`; unacknowledged; uncommitted transaction | Check commit boundaries and transaction status |
| Offset advances before business work finishes | Auto-commit enabled or listener returns after merely enqueueing work | Disable auto-commit; acknowledge after durable completion |
| Records reprocessed after restart | Commit failed or crash after side effect before commit | Make consumers idempotent and check commit logs |
| Offset skips over failing records | Listener error handler returns normally or recoverer marks handled | Check exception propagation and recovery policy |
| Offset fails to commit after rebalance | Consumer lost partition ownership or group generation changed | Investigate rebalances, poll intervals, and commit failures |
| Manual ack has no effect | `MANUAL`/`MANUAL_IMMEDIATE` not configured or ack called on wrong thread/timing | Check factory `AckMode` and acknowledgment call path |
| `commitRecovered` does not work | `AckMode` is not `MANUAL_IMMEDIATE` or error handler config is wrong | Verify `DefaultErrorHandler` requirements for your version |
| High lag while listener keeps receiving records | Position advances while committed offset lags behind | Compare position, committed offset, and commit cadence |

## 16. Safe Implementation Checklist

- [ ] `enable.auto.commit` is disabled so the listener container manages offsets.
- [ ] `AckMode` matches record/batch listener type and redelivery requirements.
- [ ] Manual acknowledgment is called only after durable processing completes.
- [ ] Listener error handlers do not accidentally swallow exceptions meant for retry.
- [ ] Error handler/recoverer post-recovery commit behavior is well understood.
- [ ] Transactional listeners commit outputs and input offsets in the same Kafka transaction when EOS is required.
- [ ] Consumers are idempotent to handle redeliveries after commit failures.
- [ ] Processing time fits within `max.poll.interval.ms` and rebalance settings.
- [ ] Commit rate, commit latency, rebalances, retries, DLT, and per-partition lag are monitored.
- [ ] Tested listener success, exceptions, recovery success/failure, restarts, and rebalances.

Unexpected offset commit behavior usually stems from misunderstood acknowledgment boundaries, error handling, or transactions. Identify how far the listener processed, when `AckMode` triggers commits, and whether the broker persisted the committed offset. When acknowledgments occur only after durable work, exceptions propagate properly to error handlers, and consumers are idempotent, the system safely handles both delayed commits and record redeliveries.
