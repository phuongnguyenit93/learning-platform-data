# Seek After Error

In Spring Kafka, when a listener processes a record and throws an exception, the consumer must return to the right position to either retry that record or route it to recovery. The seek mechanism resets a partition's read position to a chosen offset. `DefaultErrorHandler` uses seek to bring the failed record and any unprocessed records from the poll back into the read stream according to the configured retry and recovery policy.

Seeking after an error is a key part of blocking retry. It allows the listener container to re-read records from Kafka after backoff finishes, rather than advancing the offset past the failed record. Understanding seek, committed offsets, and consumer position helps engineering teams prevent record loss, control processing order, and diagnose record redeliveries.

## 1. What Is Seek in a Kafka Consumer?

Each partition has a monotonically increasing sequence of offsets. A consumer maintains a **position** indicating the next offset to be read on poll. A consumer group also has a **committed offset** stored durably so that new members or restarted consumers know where to resume from.

These two concepts are different:

- **Consumer position** is the current read position in the running consumer. Calling `seek()` changes that consumer's position.
- **Committed offset** is the checkpoint saved by the group. It is used when a consumer restarts or a partition is assigned to another member.

Example of a consumer reading partition `orders-0`:

~~~text
Committed offset: 100
Consumer position: 103

Polled:
  offset 100
  offset 101
  offset 102

seek(partition, 101)
        |
        v
Consumer position: 101
        |
        v
Next poll may receive again:
  offset 101
  offset 102
  ...
~~~

Seek changes the position within the current consumer; it does not write a new committed offset to the broker. If the consumer stops before committing a new offset, the next startup resumes from the most recent committed offset. Therefore, examine position, commits, and assignment together when investigating re-read records.

### 1.1. Why Must We Seek When a Listener Fails?

Suppose a consumer polls records at offsets 100, 101, and 102. The listener processes 100 successfully but fails on 101. If the consumer simply continues from 103 without saving or recovering 101, the failed record will be skipped.

The error handler must ensure that the offset of an unprocessed record is not acknowledged as completed. With `DefaultErrorHandler`'s default seek strategy, the consumer is moved back to the position of the failed record and the remaining records that still need reprocessing. After backoff, the consumer polls again and the record is redelivered.

~~~text
Poll:          100 ----> 101 ----> 102
                 |         |
                 |         +---- Listener throws exception
                 |
                 +-------------- Success

DefaultErrorHandler
        |
        v
Seek to 101 and retain remaining unprocessed records
        |
        v
Backoff / retry
        |
        v
Re-poll:       101 ----> 102 ----> ...
~~~

Record 100, which was processed successfully, can be committed according to the ack mode and how the container manages offsets. Record 101 and subsequent unprocessed records must be re-read.

## 2. Role of DefaultErrorHandler

`DefaultErrorHandler` is Spring Kafka's common error handler for record listeners and supported batch scenarios. It combines three decisions:

1. Whether the exception is retryable.
2. If retrying, how long to wait and how many times to retry.
3. When no longer retrying, how to recover the record.

A basic configuration:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Attach the handler to the listener container factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

In this example, `FixedBackOff(1_000L, 2L)` waits one second between retries and allows two retries after the initial processing attempt. If the record fails continuously, the listener may be invoked a total of three times before the recoverer is called.

`DeadLetterPublishingRecoverer` is an example recoverer. The application can configure destination resolvers, headers, and DLT send-failure handling as required. If the recoverer finishes successfully, the container can proceed under the configured commit policy. If recovery fails, the record must not be considered safely saved.

## 3. Default Seek Behavior of DefaultErrorHandler

For a record listener, when the listener throws an exception, `DefaultErrorHandler` defaults to using seek to return the failed record and unprocessed records from the poll back to the appropriate read position. After backoff ends, the consumer re-polls those records.

This behavior has several consequences:

- A failed record can be redelivered multiple times.
- Records following the failed record in the same partition may have to wait until the failed record is processed or recovered.
- Records successfully processed before the failed record are handled according to the ack mode and current offset commit behavior.
- Seeking does not mean the committed offset moves backward on the broker immediately.
- If the consumer experiences a rebalance or restart, the committed offset still determines the group's recovery position.

With multiple partitions in a single poll, the container must manage read positions and offsets per partition. Offset 50 of partition A has no ordering relationship with offset 50 of partition B. Committing or seeking on one partition does not acknowledge records on another partition.

### 3.1. The Failed Record and Subsequent Records

A Kafka consumer poll can return multiple records from one or more partitions. When the listener processes sequentially and hits an error on one record, unprocessed records in the poll also need to be preserved.

Example:

| Partition | Offset | Listener Outcome |
|---|---:|---|
| `orders-0` | 10 | Success |
| `orders-0` | 11 | Exception |
| `orders-0` | 12 | Unprocessed |
| `orders-1` | 20 | Unprocessed in poll |

The container must preserve the ability to process incomplete records. With seek-based error handling, the consumer is seeked so unprocessed records can be polled again. Exact seek positions and commits depend on listener type, poll results, and each partition's offset state.

Do not assume without checking that only the record causing the exception will be re-read. Inspect the error handler logs and the actual records redelivered during testing.

### 3.2. A Redelivered Record Is Not Necessarily the One That Failed Last Time

If multiple records are returned in one poll and one record fails, other records that the listener had not yet processed can also be redelivered. Consequently, the consumer must be idempotent even when the listener did not throw an exception for a given record on the first pass.

This is why side effects should not be performed before establishing durable processing and offset-commit timing. A record can be redelivered after an error on another record or after a restart/rebalance.

## 4. Batch Listeners and BatchListenerFailedException

A batch listener receives multiple records in a single invocation. If the listener throws a regular exception without indicating which record failed, the container cannot reliably tell which portion of the batch succeeded.

To pinpoint the failed record's position in the batch, Spring Kafka provides `BatchListenerFailedException`. The listener throws this exception with the failing record's index:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void listen(List<OrderCreated> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            billingService.processIdempotently(events.get(i));
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Failed to process batch record",
                    ex,
                    i);
        }
    }
}
~~~

With a batch listener, `DefaultErrorHandler` can use the error index to establish boundaries:

- Records before the failing record were processed successfully and can be committed per the container's mechanism.
- The failing record is retried or recovered according to backoff and the recoverer.
- Records after the failing record must be reprocessed.

This is key to avoiding retrying the whole batch when only one record fails. Still, side effects of records before the error index require idempotency because a failure could occur before the offset commit completes.

### 4.1. If a Batch Listener Does Not Identify the Failing Record

If a batch listener throws a regular exception instead of `BatchListenerFailedException`, the container has no index to distinguish the successful part from the failed part. Spring Kafka has fallback batch error handling to retry the batch via its own mechanism; retries may happen in memory rather than seeking per record as in the indexed case.

Therefore:

- Use `BatchListenerFailedException` when the exact index of the failing record can be identified.
- Use fallback behavior when the failure cannot be attributed to a specific record.
- Test both cases to understand which batch slice gets re-invoked.
- Do not assume all batch exceptions produce the same seek pattern.

## 5. Configuring seekAfterError

Starting in Spring Kafka 2.9, `DefaultErrorHandler` supports the `seekAfterError` option. The default value is `true`, meaning the handler uses seek so the consumer re-reads unprocessed records on the next poll.

It can be configured directly:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

handler.setSeekAfterError(true);
~~~

When set to `false`, the container does not perform seeking in the default manner. Instead, unprocessed records are retained in memory and resubmitted to the listener after the error handler completes. The container performs a paused poll to keep the consumer active in the group.

~~~java
handler.setSeekAfterError(false);
~~~

### 5.1. Comparing the Two Modes

| Mode | How Processing Continues | Operational Impact |
|---|---|---|
| `seekAfterError=true` | Seeks consumer back to position to re-read; next poll fetches records from Kafka | Records are re-read from the broker; monitor seeks, polls, and commits |
| `seekAfterError=false` | Retains unprocessed records in memory and resubmits after handler completes | Avoids direct seeks but holds data in memory; container still needs a paused poll to maintain group membership |

Setting `false` does not mean skipping retries or auto-committing records. It only changes how the container retains and redelivers unprocessed records. The error handler still governs retries, backoff, and recovery.

### 5.2. When to Choose seekAfterError=false?

Consider it when:

- You want to avoid seek/re-fetch operations from the broker in the error path.
- You need to keep the poll's unprocessed record set to resubmit via container mechanics.
- You have evaluated memory requirements for the batch size and consumer concurrency.
- You have tested rebalances, shutdowns, and retries with your running Spring Kafka version.

Do not enable it merely because you assume it is faster. Keeping records in memory increases reliance on heap and process lifecycle. If the process stops, uncommitted records still must be recovered from the committed offset; the application needs idempotency to tolerate redelivery.

### 5.3. When to Keep seekAfterError=true?

This is the default and is usually appropriate when you want explicit retry behavior grounded in Kafka offsets. Records are re-polled from the broker, so container memory does not have to retain all remaining records outside normal polling mechanics.

Choose based on workload, record size, batch size, partition count, backoff duration, and rebalance behavior. There is no single choice that fits every application.

## 6. Seek, Retry, and Committed Offsets

Seek and offset commit are two distinct operations, yet they must coordinate to ensure no record is skipped.

For example, a partition has offsets 200, 201, and 202:

1. Consumer processes 200 successfully.
2. Listener processes 201 and throws an exception.
3. Error handler seeks back to the position needed for retry.
4. After backoff, consumer re-polls 201 and unprocessed records.
5. If 201 succeeds, the container proceeds to process 202.
6. Offsets are committed only according to ack mode and container policy.

If the consumer restarts before a new offset is committed, the group may re-read from an older committed offset. This is at-least-once behavior and is why idempotency is essential.

### 6.1. Ack Mode Affects Commits

Ack mode determines when the container considers a record or batch acknowledged:

| Ack Mode | Characteristics |
|---|---|
| `RECORD` | Commits per record after the listener processes successfully |
| `BATCH` | Commits after records in the polled batch are processed successfully |
| `MANUAL` | Listener calls acknowledge; container applies commits per the mode's semantics |
| `MANUAL_IMMEDIATE` | Requests an immediate commit when acknowledge is called on the consumer thread; if called from another thread, handling is handed back to the consumer thread |

When using an error handler, also examine settings like `ackAfterHandle` and `commitRecovered` in recovery scenarios. `ackAfterHandle` determines whether the container acknowledges/commits after the error handler handles an exception normally. `commitRecovered` allows committing the offset of a recovered record under supported ack modes, typically requiring `MANUAL_IMMEDIATE`.

Do not enable `commitRecovered` or change ack mode without testing commit order. Verify actual committed offsets in the consumer group across success, retry, and recovery cases.

### 6.2. Why You Should Not Manually Commit the Highest Offset

A custom error handler or callback might be tempted to commit the highest offset seen. This is dangerous when lower offsets remain unprocessed. Committing offset 203 on a partition tells the group to resume from 203, even if records 201 or 202 never finished.

Let `DefaultErrorHandler` coordinate seeking and commits according to container semantics. If writing a custom handler, you must track offsets per partition, determine the contiguous completed offset, and handle rebalances/restarts—a complex responsibility.

## 7. Backoff in Seek-Based Retry

Seek returns the consumer to the record needing another attempt; backoff determines when the next attempt happens.

Example:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

The wait interval increases up to ten seconds, with four retries after the initial processing attempt per `ExponentialBackOffWithMaxRetries` semantics.

In blocking retry, a failing record can hold a partition from advancing during retries. Subsequent records in the partition may be delayed to preserve ordering. Consequently, long backoffs can increase record age and consumer lag.

### 7.1. Backoff Handlers and Poll Timing

With long backoffs, consider the impact on the consumer group and `max.poll.interval.ms`. Spring Kafka supports pausing backoff handlers so the container pauses the consumer during the wait and continues polling appropriately, instead of sleeping the consumer thread for an excessively long period.

Example configuration with `ContainerPausingBackOffHandler` in supported versions:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                backOff,
                new ContainerPausingBackOffHandler());
~~~

Constructor APIs and configuration options may vary by version. Check your dependency and corresponding documentation. Distinguish pausing for backoff from pausing due to `seekAfterError=false` waiting on unprocessed records; both affect how the consumer receives new records.

## 8. When Retries Are Exhausted and the Recoverer Is Invoked

After retries are exhausted or an exception is classified as non-retryable, `DefaultErrorHandler` invokes the recoverer. With `DeadLetterPublishingRecoverer`, the record can be routed to a DLT.

~~~text
Listener fails
       |
       v
DefaultErrorHandler
       |
       +---- Retryable?
       |        |
       |        +---- Yes ---> Backoff + seek/replay
       |        |                    |
       |        |                    +---- Success -----> continue
       |        |                    |
       |        |                    +---- Fails again -> keep retrying
       |        |
       |        +---- No / retries exhausted
       |                     |
       v                     v
                 Recoverer / DLT
                         |
                   Publish succeeded?
                     /       \
                   Yes        No
                   |            |
                   v            v
              Recovery OK   Report recovery
              commit per    error and preserve
              config        reprocessability
~~~

Do not treat invoking the recoverer as proof the record was saved. If DLT publishing fails, the error handler must receive the error and must not commit the source offset in a way that loses the record.

### 8.1. DLT Destination

Under `DeadLetterPublishingRecoverer`'s common default mapping, the destination topic is typically formed by appending `.DLT` to the source topic while preserving the corresponding partition. The DLT topic must have matching partitions if using the default mapping. If you want to route to a different topic or partition, configure an appropriate destination resolver.

The DLT should retain metadata:

- Original topic, partition, and offset.
- Key and event ID.
- Exception class and error details.
- Timestamp, retry count, and correlation ID if present.

Do not log full sensitive payloads. Restrict access to the DLT and set retention long enough for investigation and replay.

### 8.2. Replaying Recovered Records

After fixing the root cause, records in the DLT can be replayed to the main topic or a dedicated handling stream. Replay must preserve the original event ID and be executed in bounded batches. Consumers must be idempotent because a record may have produced partial side effects before failing.

Do not replay the entire DLT immediately after deploying a fix without confirming the root cause and business ordering. Test a few representative records, observe results, and reconcile data.

## 9. Seek and Batch Listeners: Cases to Distinguish

Error-handling behavior depends on listener type:

| Listener | How Error Is Indicated | Handling Behavior |
|---|---|---|
| Record listener | Exception from a single listener invocation | Error handler can seek the failed record and unprocessed portion for retry |
| Batch listener with `BatchListenerFailedException` | Index of the failed record in the batch | Commits preceding portion per policy, retries/recovers failed record and remaining portion |
| Batch listener with exception not identifying a record | No error index | Fallback batch error handling may retry the entire batch via its own mechanism |

Do not use a batch listener and assume the container can always tell which record succeeded. If a batch performs multiple side effects, per-record transactions or idempotency are needed to tolerate whole-batch re-invocations.

### 9.1. Batch Listeners and the Error Index

The index in `BatchListenerFailedException` must point to the record's position in the batch list being processed by the listener, not the Kafka offset. Offsets may be non-contiguous if a batch spans multiple partitions or a poll returns records from different partitions.

~~~java
for (int index = 0; index < records.size(); index++) {
    ConsumerRecord<String, OrderCreated> record = records.get(index);
    try {
        service.process(record.value());
    }
    catch (Exception ex) {
        throw new BatchListenerFailedException(
                "Record failed",
                ex,
                index);
    }
}
~~~

Do not pass the Kafka offset as the index. Confusing the two values can cause the error handler to compute the wrong boundary of records to retry.

## 10. Seek Is Not a Retry Topic

Seek-based retry is blocking retry: the consumer goes back to the unprocessed record's position and retries within the same listener container flow. Retry topics are non-blocking retry: the record is forwarded to another topic to wait for its next attempt.

| Criterion | Seek-Based Blocking Retry | Retry Topics |
|---|---|---|
| Record location | Re-read from source topic | Forwarded to retry topic |
| Impact on subsequent records | May be blocked on source partition | Main topic consumer can proceed |
| Ordering | Easier to preserve per-partition order | Retried record may return after newer records |
| Long backoff | Can hold partition/consumer in retry | Better suited for long wait durations |
| Infrastructure management | Fewer topics | Must manage retry topics and DLT |
| Offset mechanism | Seek and commit via container | Publish to retry topic and handle source offset |

Choose based on ordering requirements, SLAs, dependency recovery times, and operational capacity for additional topics. Do not mix multiple retry layers without calculating total attempts and processing time.

## 11. Rebalances and Restarts During Retries

Seek changes the position of the current consumer. If the consumer has partitions revoked during retries, partition ownership moves to another member, and the new member relies on the committed offset to continue.

Possible scenarios:

- Consumer stops before the record is committed: the record may be redelivered.
- Listener completed the database transaction but has not yet committed the offset: the record may be redelivered; idempotency is required.
- Partition is revoked during backoff: the container must finish or handle retry state according to lifecycle and current assignment.
- New consumer receives the partition: it reads from the group's committed offset, without inheriting the old consumer's in-memory position.

Therefore, never rely on in-memory state in a single consumer to treat a record as complete. Business state must be persisted durably and be recoverable when a record is redelivered to another instance.

### 11.1. Poll Interval and Rebalances

Long retries/backoffs can affect the time between polls. If a consumer exceeds `max.poll.interval.ms`, the group may consider the member stuck and trigger a rebalance.

When prolonged retries exist:

- Measure total processing and backoff time.
- Choose an appropriate backoff handler if wait times are long.
- Set `max.poll.interval.ms` to fit the workload, without using huge timeouts to mask hung listeners.
- Monitor rebalance counts, lag, and recovery durations.
- Test shutdowns/rebalances while records are actively retrying.

## 12. Idempotency When Records Are Seeked and Redelivered

Seek-based retry can cause the same record to be processed multiple times by the listener. Furthermore, partially completed records can be redelivered after crashes or rebalances.

For databases, a common pattern is an inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within a single database transaction:

1. Insert the event ID into `processed_events`.
2. If the event ID already exists, skip the previously completed side effect.
3. If the event ID is new, apply the business update.
4. Commit the transaction.
5. Let the listener finish and let the container handle the offset.

For HTTP APIs or external systems, use an idempotency key if supported. If a timeout leaves the outcome unknown, query status or reconcile before re-executing non-repeatable operations.

Do not generate a new event ID on retry. Keep the same identifier across retries, DLT, and replay.

## 13. Observability for Seek and Retry

When a record is redelivered, logs must make it clear which attempt it is on and why the position moved back.

Useful details:

- Consumer group and listener ID.
- Topic, partition, and offset.
- Exception class and root cause.
- Retry/attempt count if available.
- Backoff duration and timestamp of the next attempt.
- Seek position or retry state if provided by framework logs.
- Recoverer/DLT outcome.
- Event ID and correlation ID to look up business logs.

Metrics to track:

| Metric | Meaning |
|---|---|
| Listener exception rate | Frequency of listener failures |
| Retry rate/count | Number of record re-executions |
| Retry duration | Time records spend in retry/backoff |
| Recoverer/DLT rate | Number of records routed to recovery |
| DLT publish failure | Number of failed DLT sends |
| Consumer lag | Group backlog per partition |
| Oldest record age | Age of the oldest incomplete record |
| Rebalance count/duration | Impact of prolonged retries on membership |
| Listener processing duration | Execution time per invocation |

Do not use event IDs, message keys, or offsets as high-cardinality metric tags. Put detailed identifiers into structured logs to investigate specific records.

## 14. Runbook When a Record Retries Repeatedly

### 14.1. A Record Keeps Reappearing

1. Record the topic, partition, offset, and event ID.
2. Identify the exception class and root cause.
3. Check whether the exception is classified as retryable.
4. Inspect backoff, retry count, and when the recoverer is called.
5. Check whether the listener executes side effects before throwing the exception.
6. Check the group's committed offset and DLT status.
7. Fix the root cause or route the record to recovery per policy.
8. Confirm the record does not continue reappearing unexpectedly.

### 14.2. Records After a Failed Record Are Not Being Processed

1. Check blocking retry and backoff on the failing record.
2. Determine whether the consumer is paused or seeking/re-polling.
3. Check whether the exception is still within its retry window.
4. Confirm whether the recoverer completed.
5. Check consumer lag and record age per partition.
6. If the business allows skipping the failed record, verify the DLT has stored it durably before the source offset advances.

### 14.3. Entire Batch Is Reprocessed Repeatedly

1. Check whether the listener throws `BatchListenerFailedException`.
2. Verify the passed index is the batch index.
3. If throwing a generic exception, identify which fallback batch handler is active.
4. Check whether side effects of records before the error are idempotent.
5. Update the listener to pinpoint the failing record if possible.

### 14.4. Offset Appears to Have Advanced Past Unprocessed Records

1. Check ack mode and auto-commit.
2. Check `ackAfterHandle` and `commitRecovered` if configured.
3. Determine whether the listener acknowledges before business work is durable.
4. Check custom error handlers or code calling `commitSync`/`commitAsync`.
5. Compare committed offsets per partition.
6. Confirm whether unprocessed records remain in the log or have copies in DLT/outbox.

## 15. Testing Seek Behavior

Integration tests should verify read positions, committed offsets, and business outcomes. Merely checking that the listener is invoked again is insufficient.

Scenarios:

1. Record listener fails once then succeeds; verify the record is redelivered.
2. Record listener fails through all retries; verify the recoverer receives the right record.
3. Recoverer/DLT publish fails; verify the source offset is not committed and the record is not lost.
4. Multiple records in one poll; a middle record fails; verify unprocessed records are re-read.
5. Batch listener throws `BatchListenerFailedException` with a specific index; verify preceding and subsequent portions are handled per policy.
6. Batch listener throws a generic exception; verify fallback batch behavior.
7. Run with `seekAfterError=true` and `false`; observe pause, re-poll, and record delivery.
8. Restart consumer during retries; verify committed offset determines recovery position.
9. Trigger a rebalance during retries; verify no records are lost when partition ownership changes.
10. Test idempotency when database commit succeeds but offset commit has not happened yet.

Kafka Testcontainers or an embedded broker matching your version can be used for integration tests. Use data volumes and partition counts close to real configurations to test poll batch behavior.

## 16. Common Design Mistakes

**Confusing seek with commit:** Seek only changes the current consumer's position; it does not update the group's committed offset.

**Assuming only the failed record is re-read:** Unprocessed records from the poll may also be redelivered.

**Committing the highest offset:** Can skip lower incomplete offsets in the same partition.

**Not being idempotent:** Redelivered records can duplicate side effects.

**Using generic exceptions for batches:** The container does not know the failed record's index and may have to retry the whole batch.

**Mistakenly using offset as batch index:** `BatchListenerFailedException` expects the index in the batch list, not the Kafka offset.

**Setting overly long backoff without watching polls:** Consumers may exceed `max.poll.interval.ms` or drive up lag.

**Acknowledging when DLT publish failed:** Source records can be lost if recovery is not durable.

**Assuming seekAfterError=false removes retries:** This mode retains records in memory and resubmits them, still requiring proper error handling and acknowledgment.

**Using seek-based retry for errors needing long waits:** Partitions can become blocked; consider retry topics if ordering requirements allow.

## 17. Configuration and Operations Checklist

### Error Handler

- [ ] Listener container uses `DefaultErrorHandler` or an appropriate handler.
- [ ] Exceptions are clearly classified as retryable/non-retryable.
- [ ] Backoff is bounded and aligns with SLAs.
- [ ] Recoverer/DLT is configured for records exhausting retries.
- [ ] DLT publish failures do not falsely acknowledge the source record.

### Seek and Offsets

- [ ] Distinction between consumer position and committed offset is understood.
- [ ] Record listener seek behavior has been tested.
- [ ] Batch listeners use `BatchListenerFailedException` when the error index is known.
- [ ] Fallback behavior for generic batch exceptions is understood.
- [ ] Ack mode, `ackAfterHandle`, and `commitRecovered` are appropriate.
- [ ] `seekAfterError` is set intentionally if changing the default.

### Reliability

- [ ] Consumer is idempotent when records are redelivered.
- [ ] Side effects are acknowledged only after durable persistence.
- [ ] Backoff does not cause retry storms or violate SLAs.
- [ ] Long retries do not unexpectedly drop consumers from the group.
- [ ] Metrics exist for retries, lag, record age, and DLT.
- [ ] Runbook documents how to handle repeatedly seeked/retried records.

### Testing

- [ ] Tested record retry success and retry exhaustion.
- [ ] Tested recoverer/DLT failures.
- [ ] Tested batch failures both with and without an index.
- [ ] Tested `seekAfterError` true/false if either is used.
- [ ] Tested restarts/rebalances during retries.
- [ ] Tested duplicate deliveries and idempotency.

## Conclusion

Seeking after an error allows `DefaultErrorHandler` to return the consumer to unprocessed records so the listener can retry without prematurely acknowledging offsets. For record listeners, the handler defaults to seeking the failed record and remaining unprocessed items; for batch listeners, `BatchListenerFailedException` helps pinpoint the error index to process preceding and following items per policy. `seekAfterError=true` uses seek/re-poll, whereas `false` retains unprocessed records in memory and resubmits them after the handler finishes. Whichever approach is chosen, coordinate backoff, acknowledgment, recovery, and idempotency, and verify actual committed offsets to ensure no records are skipped.
