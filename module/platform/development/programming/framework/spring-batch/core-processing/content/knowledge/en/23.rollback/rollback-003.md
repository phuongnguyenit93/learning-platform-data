# Items Already Read Before Rollback

In Spring Batch, the reader has often already fetched a group of items from the data source before the processor and writer complete the chunk. If the chunk's transaction rolls back, the reader may have already advanced to the next position even though the chunk's data has not been committed. Spring Batch needs to retain the items already read so they are not lost and can be reprocessed.

For a regular reader, the framework buffers the chunk's items in memory by default. When a rollback occurs within the same process, the already-read items can be fed back into processing without requiring the reader to immediately re-read from the source. For a reader backed by a transactional resource such as a JMS queue, transaction rollback can return messages to the queue; in that case, the reader must be configured as a transactional queue so the framework does not also buffer messages that the broker will redeliver.

You must distinguish between a rollback while the application is still running and a restart after the process stops. The in-memory buffer exists only within the current process. When the application restarts, the reader relies on the checkpoint saved at the previous commit to re-read the unfinished portion.

## 1. Why Must Already-Read Items Still Be Retained After Rollback?

In chunk-oriented processing, Spring Batch reads a group of items, processes them, and writes the results within the chunk's transaction. The reader typically updates its internal position as soon as it returns an item from `read()`.

Suppose the chunk size is 3 and the source contains items A, B, C, D:

```text
Reader reads A, B, C
        |
        v
Processor processes A, B, C
        |
        v
Writer writes results
        |
        +--> Writer encounters error
                 |
                 v
            Transaction rollback
```

At the time the writer encounters an error, the reader may have already reached item D. If the framework only rolled back the database transaction without retaining A, B, and C, the next read might start at D. In that case, A, B, and C would not have been committed yet would be skipped in the current run.

Spring Batch must ensure that items belonging to an uncommitted chunk are reprocessed according to retry/rollback policies. Therefore, for non-transactional readers, the framework by default holds the items read in the chunk so they can be replayed to the processor/writer after rollback.

Key point: rolling back a chunk transaction does not automatically return every arbitrary `ItemReader` to its previous position. The framework buffers items to recover the processing flow; it cannot automatically rewind every file stream, cursor, or external API.

## 2. Default Flow: Buffering Already-Read Items

For regular readers, read items are held for the current chunk. If the writer or a downstream processing step causes the transaction to roll back, Spring Batch can reuse those items on the next attempt.

```text
First attempt
  read A, B, C
  buffer [A, B, C]
  process A, B, C
  write -> exception
  rollback

Retry in the same process
  retrieve [A, B, C] from buffer
  process/write per fault-tolerance policy
  commit on success

After commit
  buffer of completed chunk is released
  reader continues reading D, E, F
```

The buffer helps the framework preserve the exact set of items belonging to an uncommitted chunk. The reader does not need to move its position back to A if the framework can replay the buffered items.

Exact retry behavior still depends on the exception, retry/skip policies, and processor/writer types. Some operations may be invoked again; therefore, processors and writers must be designed to be safe on replay. Buffering does not mean every method in the chunk executes only once.

## 3. Example of a Chunk Rolling Back and Being Reprocessed

Suppose a Step uses a chunk size of 3:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(3, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(2)
            .build();
}
```

Suppose the reader reads three orders `A`, `B`, `C`. The writer encounters a transient error while writing `B`:

| Point in Time | Reader / Chunk | Transaction |
|---|---|---|
| Chunk starts | No items read yet | Open transaction |
| Read | A, B, C are fetched and buffered | Active |
| Write | Writer begins writing the chunk | Active |
| Error | Writer throws exception | Rollback |
| Retry | Buffered items are reused per retry policy | Retry transaction |
| Success | A, B, C are written completely | Commit |
| Next chunk | Reader continues with D | New transaction |

If the writer uses the same transaction manager and database resource, uncommitted changes from the first write attempt are rolled back. When the writer is invoked again, the chunk can be written cleanly without leaving behind database changes from the failed attempt.

If the writer produced side effects outside the transaction—such as sending a message or calling an API—a database rollback does not retract those side effects. When the chunk is replayed, the side effect may happen again; the writer needs idempotency or a mechanism like an outbox.

## 4. In-Memory Buffer vs. Checkpoint in ExecutionContext

These two mechanisms are frequently confused:

| Mechanism | Scope of Existence | Purpose |
|---|---|---|
| Chunk item buffer | Within the current process and current chunk execution | Replay already-read items when a transaction rolls back while the process is still running |
| Step `ExecutionContext` | Persisted in `JobRepository` | Store checkpoints to restore the reader when the Step/Job is restarted |

The buffer holds item data awaiting commit. `ExecutionContext` stores lightweight state such as line position, page, offset, or last committed ID. You should not put the entire chunk into `ExecutionContext` to replace the buffer.

Example reader storing a checkpoint:

```java
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";
private long lastCommittedId;

@Override
public void open(ExecutionContext context) {
    lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    openSourceAfter(lastCommittedId);
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
}
```

A restartable reader must implement `ItemStream` or use a built-in reader with state persistence support. The framework calls `update()` at Step state-saving points; a durable checkpoint must reflect committed progress, not merely the position the reader reached before the chunk completed.

## 5. In-Process Rollback vs. Restart After Process Failure

Rollback and restart are two distinct situations.

### Rollback While the Process Is Still Running

When the chunk transaction rolls back while the application remains running, the chunk's buffer can still exist in memory. The framework reuses already-read items to perform retries or continue according to policy. The reader does not necessarily have to re-read the data source for the same items.

### Process Stops and the Job Is Restarted

If the JVM or server stops, the in-memory buffer disappears. When the Job is restarted, Spring Batch creates a new execution for the same `JobInstance` if identifying `JobParameters` are preserved and the state permits restarting.

The reader is reopened with the `ExecutionContext` saved at the previous checkpoint. Data belonging to the uncommitted chunk will be re-read from the source based on the most recently saved checkpoint.

```text
Old process
  Chunk 1 -> commit, checkpoint 1
  Chunk 2 -> commit, checkpoint 2
  Chunk 3 -> read A, B, C; error before commit
  Process stops; buffer is lost

New process / restart
  Restore checkpoint 2
  Reader re-reads A, B, C
  Process and commit chunk 3
```

Therefore, the reader needs a stable data source and the ability to restore checkpoints. If the reader does not save state or the input source has changed, a restart may start from the beginning or read the wrong range of data.

## 6. Transactional Reader: The JMS Queue Case

Some readers consume data from a transactional resource. For example, when receiving a message from a JMS queue inside a transaction, the receive operation can participate in the transaction. If the transaction rolls back, the broker can return the message to the queue to be received again.

In that case, if Spring Batch both buffers the message and lets transaction rollback return the message to the queue, the same message could appear twice: once from the buffer and once redelivered by the broker.

This is why there is a transactional queue reader option in a fault-tolerant Step. This option informs the framework that the reader takes items from a transactional queue and that rollback returns items to the source; the framework does not need to apply normal buffering for those items.

Example configuration using the Java API of supporting Spring Batch versions:

```java
@Bean
public Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Message> messageReader,
        ItemProcessor<Message, ProcessedMessage> processor,
        ItemWriter<ProcessedMessage> writer) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<Message, ProcessedMessage>chunk(10, transactionManager)
            .reader(messageReader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .readerIsTransactionalQueue()
            .build();
}
```

The exact option name and configuration style may vary across Spring Batch versions. Use the API matching your project's dependency version. Enable this option only when the reader genuinely reads from a transactional queue and transaction rollback guarantees messages are returned to the source.

Do not enable the transactional queue option for regular file or database readers just to avoid buffering. Those readers generally do not return items to their previous positions when a transaction rolls back.

## 7. The Queue Transaction Must Actually Cover Message Reception

The transactional queue reader option is only valid when message reception actually participates in the transaction that the Step rolls back. If the reader receives messages with auto-acknowledge or a non-transactional session, rolling back a database transaction will not put messages back onto the queue.

When integrating with JMS, verify:

- Whether the JMS session/consumer uses transactions.
- Whether the Step's transaction manager manages message reception.
- When messages are acknowledged.
- If the writer writes to a database, whether the database and JMS share a coordinated transaction.
- How the broker handles redelivery and delivery counts after rollback.

If there is only a JMS transaction and a separate database transaction, rolling back one resource does not necessarily roll back the other. Atomicity across multiple resources requires an appropriate transaction coordination mechanism, or designing processing around idempotency/outbox/inbox patterns.

Do not assume that calling `readerIsTransactionalQueue()` creates a queue transaction by itself. The reader, connection factory, session, and transaction manager must be configured consistently.

## 8. How Retry and Skip Affect Already-Read Items

When an exception occurs in the processor or writer, the chunk transaction may roll back. Already-read items must still be handled according to retry/skip policies.

- **Retry:** the framework retries the operation or chunk per policy. For regular readers, buffered items can be reused.
- **Skip:** if the exception matches the skip policy and is within the limit, the failing item is excluded from the output; remaining items continue processing.
- **Retries exhausted:** if the exception is not skipped, the Step fails. On a subsequent restart, the reader relies on the committed checkpoint to re-read unfinished data.

Specifically with write-skip, the writer may be invoked again with smaller subsets of items to isolate the failing item. Do not assume an item passes through the writer only once.

If the reader is a transactional queue, messages may be redelivered by the broker after rollback. If the reader is non-transactional, the framework typically uses the buffer. Understanding the reader type correctly prevents both item loss and duplicate processing.

## 9. An Item Read by the Reader Is Not Necessarily Processed Successfully

An item may have been returned by `read()` without yet being written successfully. Distinguish these milestones:

| Milestone | Meaning |
|---|---|
| Read | Reader has returned the item to the framework |
| Processed | Processor has returned output or filtered the item |
| Written | Writer has completed the write call for the item/chunk |
| Committed | Chunk transaction has committed successfully |
| Checkpointed | Corresponding reader/stream state has been saved for restart |

`read()` returning an item does not mean the data has been committed. Similarly, the writer returning normally does not necessarily mean all non-transactional side effects have been durably confirmed alongside the Step's transaction.

When observing `StepExecution` counters, do not treat `readCount` as the number of completed business records. Also examine `writeCount`, filter/skip counts, commit/rollback counts, and the Step's final status.

## 10. Processor and Writer May Be Called Again

Buffering protects input items from being lost after rollback, but it does not make processing components idempotent. The processor or writer may be called again during retries/recovery depending on the fault-tolerant configuration.

Stateless processors are generally easier to replay because the same input and rules yield the same output. Processors with mutable state depending on item history must handle rollback and concurrency carefully.

A writer writing to a database in the same transaction can be rolled back with the chunk. A writer calling APIs, sending emails, writing files, or publishing messages needs idempotency keys, an outbox, or staging mechanisms because side effects may survive rollback.

Do not place unsafe-to-repeat side effects inside `ItemReader.read()`. The reader should focus on fetching items and managing read position; if reading also consumes a transactional resource such as a queue, configure transactions properly rather than creating non-transactional side effects.

## 11. Notes on Stateful Readers and saveState

For file readers or paging readers supporting `ItemStream`, enable state saving when restartability is required. Reader names and keys in `ExecutionContext` must remain stable:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("ordersFileReader")
        .resource(resource)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

`saveState(true)` supports recovery across restarts, whereas buffering supports rollback within the current process. The two mechanisms complement each other:

- The buffer holds items of the active chunk on rollback.
- `ExecutionContext` saves checkpoints so a new process opens the reader at the committed position.

If `saveState(false)` is set, the reader does not persist its own checkpoint. When the process stops, the reader may not resume at the exact committed position and may have to re-read from the start or rely on source-specific tracking.

With a changing data source, an old checkpoint is valid only if the file, query, sort order, or snapshot remains compatible. For instance, replacing a file after a Job fails can cause an old line offset to point to a different record.

## 12. Common Misconceptions

**Assuming rollback automatically rewinds every reader.** Transaction rollback cannot automatically rewind arbitrary files, cursors, or APIs. For non-transactional readers, the framework buffers items for replay.

**Assuming an item read is an item committed.** The reader may have advanced while the chunk has not yet been written successfully. Only transaction commit confirms changes belonging to the chunk.

**Confusing the buffer with ExecutionContext.** The buffer holds in-memory items for the chunk; `ExecutionContext` is checkpoint metadata persisted for restarts.

**Enabling transactional queue for every reader.** This option is only appropriate when transaction rollback truly returns items to a queue. For files or regular readers, disabling buffering can lose items after rollback.

**Assuming restart after process crash still uses the old buffer.** The buffer is lost when the process ends. The reader must restore from the saved checkpoint and re-read uncommitted items.

**Assuming a transactional queue reader automatically creates a JMS transaction.** Queue sessions and transaction managers must be configured properly. The option only describes reader behavior to the framework.

**Assuming the writer is called only once.** Retries and skips can cause the writer to be called again. Non-transactional side effects require idempotency.

## 13. Testing Rollback and Item Replay Behavior

To verify that the reader handles items already read before rollback properly, simulate both regular readers and transactional readers:

1. Use a reader returning A, B, C, D with chunk size 3.
2. Make the writer fail on the first write attempt.
3. Verify the chunk transaction rolls back.
4. Verify A, B, and C are reprocessed and not skipped; after commit, the reader continues with D.
5. Verify the processor/writer does not produce duplicate side effects when re-invoked.
6. Stop the process after one committed chunk and one uncommitted chunk; restart the same `JobInstance` to verify the reader restores from the latest checkpoint.
7. For a transactional queue, roll back message reception and verify the broker redelivers messages; check that the framework does not simultaneously replay the same messages from a buffer.

Tests must use a transaction manager and resources with real rollback behavior. For JMS, test against an actual broker or appropriate test container; simple mocks may not accurately simulate redelivery and acknowledgement.

## 14. How to Design Safely for Items Read Before Rollback

First, determine whether the reader is transactional. For files, database cursors/paging, or regular readers, keep the default buffering mechanism so the framework replays chunk items on rollback. Enable `saveState` and use `ExecutionContext` if recovery after process termination is needed. For JMS or transactional queues, ensure message reception participates in the rollback transaction and configure the transactional queue reader appropriately for your Spring Batch version.

Next, design processors and writers to tolerate reprocessing. Use a shared transaction for database data when possible; use idempotency keys, outboxes, or staging for non-transactional side effects. Finally, test both in-process rollback and restart after process failure. When you clearly distinguish buffering, checkpoints, and source-reading transactions, items read before a rollback will neither be lost nor unintentionally duplicated.
