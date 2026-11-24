# Manual Commits by Use Case

Consumers read records from Kafka and must record the position from which they can resume reading after a process restart. This position is stored as a committed offset per consumer group and partition. With manual commits, the application decides when to confirm progress instead of letting the Kafka consumer commit automatically on a schedule.

Manual commits are useful when the processing boundary needs explicit control—for example, confirming only after writing to a database, after finishing a batch, or after completing an asynchronous task. However, committing too early can cause missed processing, while committing too late can cause records to be redelivered. Therefore, the choice of commit approach must come from business requirements and the handler's ability to tolerate duplicates.

In Spring Kafka, most applications should use acknowledgments managed by the listener container. With the raw Kafka Consumer API, the application can call commitSync() or commitAsync() directly. Both approaches are related, but they should not be mixed in the same processing flow without clearly defining who owns the offsets.

## Learning Objectives

After this lesson, you can:

- Explain that the committed offset is a consumer group's next position to read on a partition.
- Distinguish auto commit, container-managed acknowledgment, and manual offset commits.
- Choose commitSync() or commitAsync() based on latency and confirmation requirements.
- Commit offsets after successful processing using the Kafka Consumer API.
- Use Acknowledgment and AckMode.MANUAL or MANUAL_IMMEDIATE in Spring Kafka.
- Handle partial batches, concurrent processing, and record redelivery scenarios.
- Coordinate commits with databases, retries, dead-lettering, and Kafka transactions.
- Test the failure windows between business processing and offset commits.

## 1. Which Offset Is Committed?

Kafka assigns each record an offset within a partition. When a consumer commits progress, it saves the **offset of the next record to read**, not the offset of the last processed record.

Example where a consumer successfully processes record offset 40:

~~~text
Partition orders-0

offset 40  -> OrderCreated  (successfully processed)
offset 41  -> PaymentPaid   (next record)
offset 42  -> OrderShipped

Committed offset = 41
~~~

When the consumer restarts and the group has a valid committed offset, the consumer resumes from offset 41.

Offsets are stored per consumer group and topic-partition pair in the internal topic __consumer_offsets. Because each group tracks its own progress, the billing group can be at offset 41 while the analytics group is at offset 90 on the same partition.

Points to remember:

- Committing offset 41 means the consumer confirms it has processed up to before position 41.
- Committing does not delete records from the topic.
- Committing does not confirm that side effects in a database or HTTP API were committed together with Kafka.
- A consumer may re-read records if it finishes processing without committing before the process fails.
- If a commit happens before processing finishes, records may be skipped after a restart.

This is why commit timing directly impacts delivery semantics.

## 2. Three Ways to Manage Commits

There are three common approaches:

| Approach | Who Decides Commit Timing? | Mechanism |
|---|---|---|
| Auto commit | Kafka consumer on a configured schedule | enable.auto.commit and auto.commit.interval.ms |
| Container-managed | Spring Kafka listener container | AckMode.RECORD, BATCH, TIME, COUNT... |
| Manual commit | Application code or listener explicitly confirms | commitSync(), commitAsync(), Acknowledgment |

With Spring Kafka, the listener container normally manages commits and disables Kafka auto commit by default unless the application explicitly re-enables it. This allows the container to tie commits to listener outcomes and the error handler.

Manual commits are not always better. If a listener simply processes each record synchronously, AckMode.RECORD or BATCH is usually clear enough. Choose manual commits only when the application has a specific reason to control the exact moment of confirmation.

## 3. When Should You Commit Manually?

Some common use cases:

| Use Case | Typically Suitable Approach | Reason |
|---|---|---|
| Synchronous per-record processing | AckMode.RECORD or container-managed | Container commits after the listener processes successfully |
| Write to database before confirming | MANUAL or MANUAL_IMMEDIATE | Acknowledge only after the database transaction completes |
| Batch processing and committing after the whole batch | BATCH or MANUAL | Confirm after all required records in the batch are processed |
| Raw Consumer API needing specific position commits | commitSync(offsets) | Exact control over each partition's offset |
| High throughput, accepting replay if commit fails | commitAsync() | Does not block the consumer thread waiting for commit response |
| Consume-transform-produce in a Kafka transaction | Spring Kafka transaction | Commits Kafka output and input offsets in the same transaction |
| Independent replay/backfill | Dedicated group ID and committing job progress | Does not alter production offsets |

The question to answer before choosing a commit method is: if the process fails right after processing but before committing, what happens? If the record is redelivered, will the handler produce duplicate side effects?

## 4. Manual Commits with the Kafka Consumer API

When writing a Kafka Consumer loop yourself, disable auto commit and commit only after finishing the received records.

Example of processing the entire batch and then committing:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-worker");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        OrderEventDeserializer.class);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

KafkaConsumer<String, OrderEvent> consumer =
        new KafkaConsumer<>(props);

try {
    consumer.subscribe(List.of("orders"));

    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            orderService.processIdempotently(record.value());
        }

        // Commit only after every record in the batch has been processed successfully.
        consumer.commitSync();
    }
} finally {
    consumer.close();
}
~~~

In the example, commitSync() is called after the for-loop. If any processing step throws an exception and control exits before the commit, the batch remains unacknowledged and can be redelivered.

This provides at-least-once semantics: prioritizing not skipping records while accepting potential duplicate processing. The processIdempotently method must protect side effects against duplicates.

### Warning about consumer position

Kafka Consumer may have already updated its position past the records returned from poll() before the application finishes processing each record. Therefore, do not call commitSync() after processing only part of a batch if using the no-arg overload: the consumer could commit a position past unprocessed records.

If processing the entire batch in order and committing only when all records succeed, no-arg commitSync() is simple. If partial commits are needed, build an offset map containing only the next positions of contiguously processed records per partition.

## 5. Committing Specific Offsets per Partition

Kafka allows passing a map of TopicPartition to OffsetAndMetadata to commit desired positions.

Example of processing records sequentially and tracking the completed next offset:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (ConsumerRecord<String, OrderEvent> record : records) {
    orderService.processIdempotently(record.value());

    TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

    // Commit the next position, not the current record's offset.
    offsets.put(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    );
}

if (!offsets.isEmpty()) {
    consumer.commitSync(offsets);
}
~~~

This example assumes the application processes records sequentially within the batch and halts on an exception. If a partition has offsets 10, 11, and 12 and record 11 is not finished yet, you must not commit 13 merely because record 12 finished first. Commits must represent the **contiguous prefix successfully processed** for the partition.

When a batch spans multiple partitions, progress can be committed independently per partition. If processing fails on partition A while partition B completed all its records, the application can commit partition B without advancing partition A's offset.

Do not calculate offsets by adding the count of received records if the log has offset gaps. Use the record's actual offset and commit the next offset after the last record in the completed contiguous range.

## 6. commitSync(): Waiting for Broker Commit Confirmation

commitSync() sends offsets to the coordinator and waits for the result before continuing. This is the straightforward choice when you need to know the broker confirmed the commit before taking the next step.

Example:

~~~java
try {
    processBatch(records);
    consumer.commitSync();
} catch (RuntimeException ex) {
    // Do not commit the batch if processing is incomplete.
    handleProcessingFailure(ex);
    throw ex; // Do not poll the next batch before the failed batch is handled/recovered.
}
~~~

Advantages:

- The processing flow knows whether the commit succeeded or failed.
- Easy to enforce process-then-commit ordering.
- Suitable for consumers needing firm confirmation boundaries or a final commit before shutdown.

Trade-offs:

- The consumer thread blocks while waiting on the coordinator.
- Frequent commits can reduce throughput.
- Commits can fail if the consumer lost partition ownership, the group is rebalancing, or the coordinator is unavailable.

With consumer groups, handle appropriate exceptions such as CommitFailedException and rebalance scenarios. Never assume commitSync() always succeeds; decide whether to retry, halt processing, or allow records to be redelivered.

### When should you use commitSync()?

- Small or medium batches requiring commit confirmation before the next poll.
- Migration/backfill jobs needing clear progress checkpoints.
- Consumers needing to commit specific offsets after completing side effects.
- Shutdown phases needing a final commit after stopping new record intake.

If commitSync() fails after side effects have succeeded, records may be redelivered. Idempotency is still required.

## 7. commitAsync(): Sending Non-Blocking Commits

commitAsync() sends the commit request and immediately returns control to the application. The result is received via a callback.

Example:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.warn("Offset commit failed: {}", offsets, exception);
        metrics.incrementCommitFailure();
        return;
    }

    log.debug("Committed offsets: {}", offsets);
});
~~~

Advantages:

- Does not block the consumer thread waiting for a response.
- Can reduce overhead when committing frequently.
- Suitable for high-throughput streams that can tolerate record replay if a commit fails.

Trade-offs:

- The application does not get the result immediately at the call site.
- If a commit fails, the offset may remain unsaved.
- If the process crashes before the callback or before broker confirmation, processed records may be redelivered.
- Retrying an older commit after a newer commit has been sent can roll offsets backward if ordering is not controlled.

### Do not blindly retry an old commitAsync

Suppose the application sends a commit for offset 100, then sends a commit for offset 150. The callback for commit 100 reports an error while the commit 150 request is already in flight. If the callback resends offset 100 itself, the retry request might be processed after commit 150 and move the group backward to the old position, causing many records to be re-read.

The Kafka client preserves callback order matching the order commit requests were sent, yet the application still should not retry an old offset once a newer commit has been issued. If you need to guarantee the final commit, stop sending new async commits and execute commitSync() with the latest position during shutdown or recovery.

### When should you use commitAsync()?

- Consumers processing large volumes of records that want to reduce commit wait times.
- Replaying some records after errors is acceptable.
- The application has callback monitoring and commit order control.
- There is a final commitSync() step on consumer close if progress confirmation is needed.

Do not use commitAsync() merely to avoid handling exceptions. The callback must record failures, and the system must tolerate replay when commits fail.

## 8. Combining commitSync and commitAsync

A common pattern is using commitAsync() in the normal poll loop to reduce waiting, then using commitSync() when closing the consumer to confirm the latest position.

Illustrative flow:

~~~text
Poll batch
   |
Process records
   |
commitAsync()  ----> continue poll loop
   |
   | subsequent batches
   v
Shutdown requested
   |
Stop accepting new records
   |
Finish or handle in-flight work
   |
commitSync() with latest position
   |
close consumer
~~~

This pattern must be implemented carefully:

- Commit only contiguously processed offsets.
- Do not let an old commitAsync overwrite newer progress.
- Do not close the consumer before necessary callbacks/commits finish.
- During a rebalance, commit only partitions the consumer still owns under the group protocol.
- If processing in parallel, track which records finished before building the offset map.

Do not mix commitSync() and commitAsync() arbitrarily across multiple threads. KafkaConsumer is not thread-safe; all consumer operations must be coordinated on the consumer thread.

## 9. Manual Acknowledgment in Spring Kafka

With @KafkaListener, Spring Kafka provides Acknowledgment so the listener can explicitly confirm after processing.

Example listener using manual acknowledgment:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    // Acknowledge after business processing completes.
    acknowledgment.acknowledge();
}
~~~

The factory must use an appropriate acknowledgment mode:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        manualAckListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL
    );

    return factory;
}
~~~

When using MANUAL, the listener calls acknowledge() to place the record into the container's acknowledgment queue. The container commits offsets at the batch/poll boundary after the records returned in the poll have been processed and acknowledged according to this mode's rules.

With MANUAL_IMMEDIATE, the container attempts to commit immediately when acknowledge() is called on the consumer thread. If acknowledge is called from another thread, the acknowledgment is queued for the container to process during the consumer lifecycle. Therefore, if immediate commits are needed, call acknowledge on the listener thread and check the container's syncCommits setting.

### Choosing MANUAL or MANUAL_IMMEDIATE?

| Mode | Behavior | Use Case |
|---|---|---|
| MANUAL | Acknowledgments are queued; commits happen at batch/poll boundaries | Wanting to decide which records are done while still grouping commits |
| MANUAL_IMMEDIATE | Can commit immediately on acknowledge from the consumer thread | Needing immediate confirmation after a specific side effect or record |

Neither mode automatically makes side effects outside Kafka atomic with offsets. If the database commits but the process stops before the Kafka offset is committed, records may be redelivered.

## 10. Committing After Writing to a Database

A common use case is a consumer receiving an event, updating a database, and only then acknowledging Kafka.

Flow:

~~~text
Kafka record
     |
     v
Listener executes business logic
     |
     v
Database transaction
     |
     +---- rollback / exception ----> Do not acknowledge
     |
     v
Database commit succeeds
     |
     v
Acknowledgment.acknowledge()
     |
     v
Kafka offset commit
~~~

Example:

~~~java
@KafkaListener(
    topics = "payments",
    groupId = "payment-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        PaymentRequested event,
        Acknowledgment acknowledgment) {

    paymentService.applyInDatabaseTransaction(event);

    acknowledgment.acknowledge();
}
~~~

If paymentService completes the database transaction but the process dies before acknowledge/offset commit, Kafka will redeliver the record. The consumer needs an idempotency key such as eventId and a unique constraint/inbox table so the second execution does not create a duplicate payment.

A common design writes the processed eventId and updates business data in the same database transaction:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('evt-123');

UPDATE payments
SET status = 'APPLIED'
WHERE payment_id = 'pay-456';

COMMIT;
~~~

In practice, a unique constraint on processed_events.event_id prevents two concurrent executions of the same event. If the insert hits a duplicate error, the application recognizes the event was already processed and can acknowledge the record per business rules.

Do not split recording the processed event and updating business data into two separate database transactions, because a failure between the two steps can leave business data and the inbox inconsistent.

## 11. Batch Processing and Partial Success

With a batch listener, a single invocation receives multiple records. There are two common strategies:

- Process the entire batch in one transaction, then acknowledge after the whole batch succeeds.
- Process record by record, track which records succeeded, and use partial batch/offset mechanisms compatible with your Spring Kafka version.

Using MANUAL and calling acknowledge only after every record in the batch succeeds is simpler to implement. If one record fails, do not acknowledge the batch; the error handler decides on retry or recovery.

With the raw Kafka Consumer API, offsets can be committed independently per partition if a contiguous prefix has been processed. Never commit past a failed record simply because later records finished earlier.

Example for one partition:

~~~text
P0: offset 10  -> succeeded
P0: offset 11  -> failed
P0: offset 12  -> succeeded

Safe offset to commit: 11
Do not commit: 13
~~~

Offset 11 is the next position to read because record 10 is complete while record 11 is not. Record 12 having completed still does not permit committing past the gap at 11.

If you want to continue processing records after a failed record, you need an appropriate retry/DLT and offset management strategy. Do not skip failed records and commit higher offsets if business rules prohibit data loss.

## 12. Parallel Processing and Out-of-Order Acknowledgments

Some applications offload record processing to an executor to boost throughput. When records from the same poll finish out of order, acknowledging a later record before an earlier record can cause commits to advance past unfinished work unless tracked properly.

Since version 2.8, Spring Kafka includes the asyncAcks property, allowing acknowledgments for records in a poll to arrive out of order. The container tracks missing acknowledgments and pauses the consumer until earlier offsets are fully confirmed. It can be enabled on the container factory:

~~~java
factory.getContainerProperties().setAsyncAcks(true);
~~~

Example:

~~~text
Poll returns:      offsets 20, 21, 22
Completed:         20, 22
Incomplete:        21

Container cannot commit past 21 yet.
Consumer may be paused until 21 is acked.
Once 21 completes, the container can advance commits.
~~~

This mechanism prevents committing past incomplete records, though it does not by itself ensure side effects happen only once. If the process fails before all acknowledgments finish, records can still be redelivered.

When using asyncAcks:

- Acknowledge each record exactly once after processing finishes.
- Do not acknowledge before the background task completes.
- Monitor how long an acknowledgment stays pending.
- Accept that the consumer may pause and lag may grow when one record is slow.
- Keep business processing idempotent because completed records may be redelivered after failures.

If asynchronous processing is unnecessary, keeping listeners sequential per partition is usually simpler and easier for preserving order.

## 13. Retries, Dead-Lettering, and Commit Timing

When a listener throws an exception, the Spring Kafka error handler decides whether to retry, recover, or send the record to a dead-letter topic. Offsets should advance past a record only once the handling policy has determined the record succeeded or was recovered according to configured rules.

A common processing flow:

~~~text
Listener receives record
       |
       v
Process business logic
       |
       +---- success ----> acknowledge / commit
       |
       +---- failure
                |
                v
          Retry with backoff
                |
          +-----+------+
          |            |
       success     retries exhausted
          |            |
          v            v
       commit      publish DLT
                       |
                 recover succeeds
                       |
                 commit per error handler
~~~

Once published to the DLT successfully, the application has moved the record to the error-handling path per policy. That does not mean the original business logic succeeded; monitor the DLT and replay procedures.

Do not manually acknowledge inside a catch block just to suppress retries. If the exception indicates incomplete side effects, committing the offset will cause the record to be skipped. If the error is non-retryable, use a recoverer/DLT and commit only upon confirmed recovery.

## 14. Kafka Transactions and Offset Commits

In consume-transform-produce flows, a Kafka transaction can commit output records and input offsets as an atomic unit.

Example:

~~~text
Consume input offset 50
        |
Transform
        |
Begin Kafka transaction
        |
Produce output record(s)
        |
Add input offset 51 to transaction
        |
Commit transaction
        |
Output and input offset committed together
~~~

With Spring Kafka, the listener container can participate in a Kafka transaction via KafkaTransactionManager and a transactional producer factory. Input record offsets are sent into the transaction alongside output records according to container configuration.

When using transactions for consume-transform-produce, do not manually call commitSync() or acknowledge outside the transaction if the goal is exactly-once within Kafka. Let the transaction manager/container coordinate sending offsets into the transaction.

Consumers reading transactional output need isolation.level=read_committed to see only records from committed transactions.

Kafka transactions do not cover databases or HTTP APIs by default. If a listener writes to a database and then the Kafka transaction aborts, database side effects may still persist. Inbox/outbox, idempotency, or business coordination mechanisms are needed to handle that boundary.

## 15. Committing During Rebalances and Shutdown

When a consumer group rebalances, partitions can be revoked from the current member. The consumer needs to finish in-flight work and commit progress safely before surrendering partitions whenever possible.

With the Kafka Consumer API, you can register a ConsumerRebalanceListener to handle partition revocation:

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            // Commit contiguously processed offsets before surrendering partitions.
            commitProcessedOffsets(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            // Seek if the use case requires a specific starting position.
        }
    }
);
~~~

This is an illustrative example; commitProcessedOffsets must use an offset map of completed records and commit only partitions still owned by the consumer.

In Spring Kafka, the listener container manages rebalance callbacks and offset commits according to the acknowledgment mode. If custom logic is needed, use ConsumerAwareRebalanceListener or the corresponding mechanism for your Spring Kafka version. Avoid calling consumer APIs from threads other than the container's consumer thread.

During shutdown:

1. Stop accepting new work or request the container to stop.
2. Wait for in-flight processing within the shutdown timeout.
3. Commit completed progress.
4. Close the consumer and release resources.

If the process receives kill -9 or the server loses power, shutdown hooks do not run. Thus, the design must still tolerate record redelivery after a restart.

## 16. Commit Strategy Selection Table by Use Case

| Scenario | Choice | Notes |
|---|---|---|
| Listener processes each record synchronously | AckMode.RECORD | Container commits after each successful record |
| Listener processes batches and wants fewer commits | AckMode.BATCH | Commits only after the batch is processed |
| Write to DB then acknowledge | MANUAL or MANUAL_IMMEDIATE | DB transaction and Kafka offset are not atomic by default |
| Raw Consumer API needing explicit confirmation | commitSync() | Blocks waiting for broker response |
| High-throughput consumer | commitAsync() | May replay on commit error; monitor callbacks and ordering |
| Parallel out-of-order record processing | asyncAcks if version supports it | Consumer may pause waiting for missing acknowledgments |
| Consume-transform-produce Kafka-to-Kafka | Kafka transaction | Offsets and output must be in the same transaction |
| Replay/backfill | Dedicated group ID, separate progress commits | Avoid overwriting production offsets |

## 17. Common Mistakes

**Committing before side effects finish.** If the database/API fails after the commit, Kafka will not redeliver the record for that offset. Commit only after required work completes.

**Committing an entire batch after partial processing.** No-arg commitSync() may commit the position advanced across the whole poll. For partial success, commit an offset map of the contiguously processed prefix.

**Confusing the last record's offset with the next offset.** Processing record 40 means committing 41. Committing 40 can cause record 40 to be re-read.

**Retrying an old commitAsync after a newer commit was sent.** Can move committed offsets backward. Observe callbacks and never blindly retry an old offset.

**Calling KafkaConsumer from multiple threads.** Consumers are not thread-safe. Coordinate poll, commit, seek, and close on the consumer thread.

**Acknowledging from a background task before completion.** Side effects may still be incomplete when the offset advances. Acknowledge only after the future/task actually finishes.

**Assuming manual ack creates exactly-once with a database.** Database commits and Kafka offset commits are two separate systems. Use inbox, unique constraints, or outbox appropriately.

**Using manual commits in a listener container without clarifying offset ownership.** Can cause duplicate commits, mistimed commits, or conflicts with the container. Inside @KafkaListener, prefer Acknowledgment and AckMode.

## 18. Testing Manual Commits

Integration tests should simulate failures right at the boundary between processing and committing:

- Process records successfully and commit; restart the consumer and verify it resumes at the next offset.
- Make the listener fail before acknowledgment; verify the record is redelivered.
- Write to the database successfully and stop the process before commit; verify redelivery does not produce a second side effect.
- Process a batch with one failing record; verify the committed offset does not advance past the failing record.
- Send commitAsync and simulate a callback error; verify metrics and recovery policies operate properly.
- Issue a lower-offset commit after a higher-offset commit in a controlled test to demonstrate rollback risk.
- Process asynchronously with asyncAcks and verify the container does not commit past missing acknowledgments.
- Rebalance during processing; verify only offsets for completed partitions are committed.
- Run consume-transform-produce inside a Kafka transaction and abort; verify output and offsets roll back together within the Kafka transaction.

Do not merely mock Acknowledgment or Consumer to assert method calls. Use an embedded broker or Testcontainers to verify committed offsets, redelivered records, and consumer group state.

## 19. Observing Commits in Production

Signals to monitor:

- Commit success/failure counts and commit duration.
- Commit count per consumer group.
- Consumer lag per partition.
- Redelivered or duplicate-processed record counts.
- Latency from poll to processing completion and acknowledgment.
- Pending acknowledgment count when using asyncAcks.
- CommitFailedException, rebalances, and coordinator errors.
- Retried, recovered, and dead-lettered record counts.

You can use the Kafka CLI to inspect committed offsets and lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

When lag increases, check both processing duration and commit duration. A fast listener committing too frequently may suffer commit overhead; conversely, batching too large can lengthen replay time if failures happen before committing.

## Commit Design Checklist

- [ ] Clearly identified who owns commits: Kafka client, Spring container, or application code.
- [ ] Auto commit is disabled if the application controls commits itself.
- [ ] Understood that the committed offset is the next position to read.
- [ ] Commit only after records prior to that offset have processed contiguously and successfully.
- [ ] Chosen commitSync or commitAsync based on latency and confirmation needs.
- [ ] commitAsync callbacks record errors and never blindly retry old offsets.
- [ ] With Spring Kafka, selected an appropriate AckMode and acknowledge after side effects.
- [ ] Database operations have idempotency/inbox to tolerate redelivered records.
- [ ] Batch/async processing never commits past unfinished records.
- [ ] Retry, DLT, rebalance, and shutdown have clear commit rules.
- [ ] Kafka transactions are used when atomicity between Kafka output and input offsets is required.
- [ ] Tested restarts, partial failures, commit failures, and duplicates.

## Conclusion

Manual commits let applications precisely control when consumers confirm progress. With the Kafka Consumer API, commitSync() waits for the result while commitAsync() is non-blocking but requires managing callbacks and offset ordering. With Spring Kafka, Acknowledgment paired with MANUAL or MANUAL_IMMEDIATE is the right integration for listeners to confirm after processing. In all cases, commit only across a contiguously completed prefix per partition, and design idempotently to tolerate failures after side effects but before commits. When atomicity between Kafka output and input offsets is required, use Kafka transactions rather than separating manual commits from the transaction.

