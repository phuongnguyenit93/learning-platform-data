# Transactional reader

In Spring Batch, an `ItemReader` fetches items from a data source to feed into a chunk. For many sources such as files or database queries, reading does not "consume" items from the data source in the sense of a message queue. If a chunk rolls back, Spring Batch normally holds already-read items in a buffer so they can be reprocessed without re-reading the source.

A **transactional reader** reads from a resource where receiving an item participates in the transaction and can be undone. A classic example is a reader receiving messages from a transactional queue. When a chunk rolls back, the broker can redeliver unacknowledged messages. In that case, Spring Batch needs to know the reader has transactional semantics so it avoids keeping a duplicate copy of items in an internal buffer.

In fault tolerance, this matters because retry, skip, and rollback can cause a chunk to be re-executed. How the reader interacts with the transaction determines which items are re-read, which items stay in memory, and whether there is a risk of duplicate processing or data loss.

## 1. How does the Reader fit inside a chunk transaction?

In a chunk-oriented Step, Spring Batch processes a group of items inside a transaction. Reader, processor, and writer participate in the chunk processing cycle:

~~~text
Open chunk transaction
       |
       v
ItemReader.read()
       |
       v
ItemProcessor.process()
       |
       v
ItemWriter.write()
       |
       v
Update state and checkpoint
       |
       v
Commit transaction
~~~

If an operation causes the chunk to fail, the current transaction may roll back per transaction policy. Spring Batch must then reprocess the items of the uncommitted chunk.

The key distinction is that **the reader being called inside a chunk transaction cycle** does not mean **the read source can roll back item consumption**. A `SELECT` query does not normally delete rows from a database. A file cursor does not automatically rewind to its old position simply because a database transaction rolled back. Conversely, a message queue can keep a message in an unacknowledged state and redeliver it after a rollback.

For this reason, Spring Batch has a buffering mechanism to support non-transactional readers and a separate configuration for transactional queue readers.

## 2. Non-transactional readers and the default buffering mechanism

For read sources that cannot roll back, Spring Batch needs to retain read items so that if a chunk rolls back, those items can be passed through the processor and writer again.

For example, the reader reads three records A, B, and C from a file:

~~~text
Reader reads: A, B, C
       |
       v
Spring Batch retains read items
       |
       v
Processor / Writer processes
       |
       v
Writer fails -> chunk rollback
       |
       v
Framework reuses buffered A, B, C
~~~

Buffering avoids depending on the source's ability to rewind. If the framework called the reader again directly, a file reader might have already advanced to line D, and a cursor or other data source might have moved to the next position. A, B, and C would risk being skipped.

For non-transactional readers, this behavior is necessary to ensure items in an uncommitted chunk can be reprocessed. Applications usually need no extra configuration to enable this buffering mechanism.

Buffering also has limits. Items currently in the chunk must be held in memory, and the reader must not produce unrepeatable side effects if the framework re-invokes operations in fault-tolerant scenarios. With a large chunk size, the number of retained items can increase memory usage.

## 3. Transactional readers have different semantics

A transactional reader receives items from a resource participating in the same transaction. When the transaction rolls back, the resource can restore item receipt state so the items can be read again.

With a transactional queue:

~~~text
Initial queue: [A, B, C, D]
       |
       v
Transaction receives A, B, C
       |
       v
Processor / Writer fails
       |
       v
Rollback transaction
       |
       v
Broker can redeliver A, B, C
~~~

The queue is the party maintaining unacknowledged message state. If Spring Batch simultaneously keeps copies of A, B, and C in its buffer, reprocessing may use the old buffered copies and later receive the same messages again from the queue. That can cause duplicate processing.

With a transactional queue reader, Spring Batch must disable standard item buffering so the next read fetches the message redelivered by the broker. That is why chunk configuration provides the `readerIsTransactionalQueue()` option.

Not every reader that has a transaction manager is a transactional reader in this sense. You must verify that receiving items can genuinely roll back and that the resource will redeliver or restore the corresponding items.

## 4. Configuring readerIsTransactionalQueue()

In Spring Batch 5, configure a transactional queue reader on a chunk Step using the `readerIsTransactionalQueue()` method:

~~~java
@Bean
public Step consumeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderMessage> queueReader,
        ItemProcessor<OrderMessage, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("consumeOrdersStep", jobRepository)
            .<OrderMessage, Order>chunk(20, transactionManager)
            .reader(queueReader)
            .readerIsTransactionalQueue()
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

In this example, the reader fetches messages from a queue and each chunk handles up to roughly 20 messages. The transactional queue setting informs Spring Batch that the read source can replay items after rollback, so the framework does not need to buffer items in the usual way.

This method adjusts Spring Batch's buffering behavior. It does not create a broker transaction on its own, does not configure acknowledgement mode, and does not coordinate transactions between the queue and the database. Those components must be set up separately.

Enable this setting only when the reader truly has transactional queue semantics. Do not enable it for file readers, standard JDBC readers, or API readers just because you want the framework to re-read items after a rollback.

## 5. Choosing the right handling by source type

Not every read source has the same rollback capability:

| Source | Typical read behavior | How to think about rollback |
| --- | --- | --- |
| File | Reader advances through lines | Framework buffers items so the chunk can be reprocessed |
| JDBC query/paging | Query fetches rows in order | A database transaction does not "put back" a SELECT row like a queue message |
| JDBC cursor | Cursor advances through a result set | Understand connection, cursor, and checkpoint; do not assume cursor rewinds on rollback |
| JMS transactional receive | Message is received inside a JMS transaction | Rolling back the session/transaction can cause the message to be redelivered |
| Queue with acknowledgement/visibility timeout | Message is delivered awaiting ack or lease expiry | Redelivery depends on broker, client, and ack/delete timing |
| Remote API or stream | Reader may consume an offset or token | Requires dedicated resume/replay mechanism; do not assume DB transaction controls the source |

The crucial point is distinguishing **the Step's transaction** from **the read source's transaction**. They only coordinate when resources and the transaction manager are configured properly.

## 6. Is a database reader automatically a transactional reader?

Do not draw that conclusion just because the reader uses JDBC. A regular `SELECT` query does not consume rows the way a queue receives messages. When a transaction rolls back, the database does not automatically move the `ItemReader` cursor back to the previous item with queue semantics.

With a JDBC paging reader, each page is queried by a sort key and the reader can save state for restarts. With a cursor reader, the cursor has its own lifecycle and connection; connection, isolation, and transaction settings must be understood for the specific reader type in use.

Paging reader example:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .parameterValues(Map.of("businessDate", businessDate))
            .rowMapper(new OrderRowMapper())
            .pageSize(100)
            .saveState(true)
            .build();
}
~~~

This example illustrates a reader with a stable sort key that saves state for restarts. This reader is not a transactional queue reader. Do not call `readerIsTransactionalQueue()` on it merely because queries run inside a chunk transaction.

For database readers, focus on:

- Deterministic read order via `ORDER BY` or sort keys.
- Stable filtering criteria throughout the Job.
- Checkpoint and `saveState` mechanisms.
- Isolation level and whether source data can change while the Job runs.
- Connection/cursor lifecycle of the specific implementation.

## 7. The transaction manager must manage the right resources

For message receipt to roll back, the queue client must participate in the transaction used by the Step. If the reader opens an independent session or acknowledges messages before the chunk commits, a Step rollback cannot return messages to the queue.

For example, with JMS, a `JmsTransactionManager` can manage local JMS transactions. If the Step simultaneously writes to a database using a separate `DataSourceTransactionManager`, two independent transactions do not automatically become a single shared transaction.

~~~text
JMS transaction                  Database transaction
      |                                  |
  receive message                    write row
      |                                  |
  commit / rollback                  commit / rollback
      |                                  |
      +------ do not coordinate automatically ----+
~~~

If message receipt and database write must commit or roll back together, you need a proper resource coordination mechanism, such as JTA/XA when supported by both broker and database. Without distributed transactions, design for at-least-once delivery with idempotency, inbox/outbox, or reconciliation.

Merely passing a `PlatformTransactionManager` to the Step does not prove every resource participates in that transaction. Inspect the transaction manager, `ConnectionFactory`, session, acknowledgement mode, and how the reader invokes the client.

## 8. Example reader receiving messages via JMS

A custom `ItemReader` can receive messages synchronously via `JmsTemplate`:

~~~java
public class JmsOrderReader implements ItemReader<OrderMessage> {

    private final JmsTemplate jmsTemplate;
    private final String destination;

    public JmsOrderReader(
            JmsTemplate jmsTemplate,
            String destination) {
        this.jmsTemplate = jmsTemplate;
        this.destination = destination;
    }

    @Override
    public OrderMessage read() {
        Message message = jmsTemplate.receive(destination);
        if (message == null) {
            return null;
        }
        return convert(message);
    }

    private OrderMessage convert(Message message) {
        // Convert JMS Message to DTO according to the actual payload.
        // Handle parse errors with meaningful exceptions.
        throw new UnsupportedOperationException("Implement conversion");
    }
}
~~~

This is an illustrative skeleton; `convert` must be implemented per the message contract. Crucially, `JmsTemplate` and `ConnectionFactory` must participate in the proper JMS transaction. If `receive` runs in a non-transactional session or messages are auto-acknowledged before the writer finishes, the reader cannot support redelivery as the framework expects.

Never manually commit or acknowledge a message inside `read()` before the Step finishes the chunk. Premature acknowledgement can lose the message from the queue even if the processor or writer later fails.

## 9. Rollback, retry, and re-reading items

A fault-tolerant Step can retry failed operations. How items are supplied again depends on the reader:

**Non-transactional reader:** the framework normally uses buffered items for reprocessing. The reader is not necessarily called again to fetch the same items from the source.

**Transactional queue reader:** the framework does not use standard item buffering. After a rollback, the reader is called again and the broker can redeliver messages.

Example retrying transient database errors:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

This example is only valid if the actual exceptions are classified properly and transaction rollback genuinely causes the queue to redeliver messages. The retry limit does not guarantee broker redelivery on its own; that is the responsibility of transaction/acknowledgement integration.

A rollback can cause all unacknowledged messages in the chunk transaction to be redelivered, not only the message that triggered the error. Therefore, the processor and writer must tolerate reprocessing the other messages in the same chunk.

## 10. Skip and transactional readers

If a message contains permanently invalid data, a data-exception skip can be configured. However, the message must be handled in a way that terminates the redelivery loop.

Example:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderMessageException.class)
        .skipLimit(100)
        .listener(skipListener)
        .build();
~~~

If a bad message is skipped and the chunk commits, the queue must acknowledge consumption of the message per the transaction. The application should also record the failing message into a rejected store or DLQ using a durable mechanism.

If rejected records are stored in a different database from the queue's transaction, handle the case where one side commits while the other rolls back. Use an idempotency key, outbox/inbox, or a reconciliation process. Never allow a failing message to roll back and redeliver indefinitely without a limit.

## 11. Empty queues and when the Step ends

`ItemReader` returns `null` to signal there are no more items. For files or finite result sets, this signals end-of-input. For queues, the queue might simply be temporarily empty.

If the reader uses a receive timeout and returns `null`, Spring Batch may treat that as end-of-input and finish the Step. This suits Jobs aimed at draining all messages currently present at a point in time or within a bounded batch.

If you need a continuously running consumer waiting for new messages, a standard chunk-oriented Step does not continue indefinitely once `read()` returns `null`. You need a message-driven consumer model or a specifically designed polling mechanism.

Before implementing a queue reader, clearly define the termination condition:

- The queue is empty at the time of checking.
- A batch's target number of messages has been received.
- All messages for a business key or cutoff time have been processed.
- The configured polling duration has elapsed.

Never use `null` to represent a connection error or unexpected timeout. Source errors must be expressed as exceptions so the Step can apply retry/fail policies.

## 12. ItemStream and checkpoints

`ItemStream` provides `open`, `update`, and `close` callbacks so a reader or writer can save and restore state:

- `open(ExecutionContext)`: restores state when the Step starts or restarts.
- `update(ExecutionContext)`: saves a checkpoint at an appropriate processing boundary.
- `close()`: releases resources.

For file readers or paging readers, `ExecutionContext` can store line numbers, offsets, pages, or sort keys. For transactional queues, delivery and acknowledgement state is typically managed by the broker. Do not store an arbitrary offset in `ExecutionContext` and assume it replaces queue transactional receive semantics.

Distinguish two types of state:

| State | Where managed | Purpose |
| --- | --- | --- |
| Reader checkpoint | `JobRepository` / `ExecutionContext` | Restore read position for readers supporting restart |
| Queue delivery/ack state | Broker and client transaction | Determine whether a message is acknowledged or needs redelivery |

When a process stops:

- Committed/acked messages are usually considered consumed.
- Uncommitted/unacked messages may be redelivered by the broker.
- Messages written to the database but not acked may reappear and require idempotency.
- Messages acked while the database has not committed may be lost if the two resources do not share a transaction.

`JobRepository` stores Job/Step metadata, but does not automatically manage acknowledgements for every broker.

## 13. Idempotency when the reader redelivers items

Transactional receive and rollback do not guarantee end-to-end exactly-once processing. Messages can be redelivered if a consumer loses connection, an acknowledgement is lost, or the process stops when commit outcome is uncertain.

A common approach is storing the message ID with a unique constraint:

~~~java
public void process(OrderMessage message) {
    if (processedMessageRepository.existsByMessageId(
            message.getMessageId())) {
        return;
    }

    orderRepository.save(toOrder(message));
    processedMessageRepository.save(
            new ProcessedMessage(message.getMessageId()));
}
~~~

This is a conceptual example. Checking and inserting must be protected by a transaction and an appropriate unique constraint to prevent race conditions when multiple workers receive the same message.

An inbox table can be used to track processed messages:

~~~text
inbox_message
---------------------------------
message_id (UNIQUE)
received_at
processed_at
status
error_code
~~~

Writing the inbox record and business data in the same database transaction helps redelivery detect that the message was already applied. For non-database side effects such as HTTP requests, emails, or publishing messages, use an idempotency key or outbox accordingly.

## 14. Poison messages and repeated redelivery

A poison message is a message that always fails, such as a malformed payload or an unrecoverable condition violation. If every processing attempt rolls back, the broker may redeliver the message continuously.

~~~text
Queue
  |
  v
Receive bad message
  |
  v
Processor throws exception
  |
  v
Rollback
  |
  v
Broker redelivers
  |
  +---- repeats if there is no stop policy
~~~

To avoid infinite loops:

- Distinguish permanent data errors from transient errors.
- Retry with a cap and backoff for recoverable errors.
- Use a skip policy when business rules allow skipping.
- Record rejected items via `SkipListener` or an error handler.
- Move messages to a dead-letter queue when conditions are met.
- Store message ID, delivery count, and failure cause for investigation.

Writing to the DLQ and acknowledging the source queue also require appropriate transactions or idempotency. If a message is acknowledged before the error is durably stored, data can be lost.

## 15. Chunk size, prefetch, and in-flight messages

Chunk size affects how many messages are received within a single transaction. A large chunk can reduce commits but increases the number of messages redelivered upon rollback.

Beyond chunk size, brokers often have prefetch or in-flight message limits. A broker may deliver messages ahead of time to the consumer before Spring Batch asks for them.

When choosing configuration, consider:

- Average and high-percentile processing time per message.
- Number of messages in a chunk.
- Number of messages prefetched by the broker.
- Memory required to hold payloads.
- Queue and database commit latency.
- Number of concurrent workers.
- Number of messages that could be redelivered after a rollback.
- Retry/skip and reprocessing cost.

Do not blindly increase chunk size to boost throughput. A large chunk can hold transactions open too long and force many messages back onto the queue when a single operation fails.

## 16. Common mistakes

### Calling readerIsTransactionalQueue for a regular reader

The framework stops buffering items, yet the source lacks redelivery capability. After a rollback, items can be lost from the processing stream. Enable it only when the reader genuinely uses a transactional queue.

### Thinking readerIsTransactionalQueue creates a transaction by itself

This method only adjusts buffering. You must separately configure the transaction manager, queue client, session, and acknowledgement.

### Confusing the Step's transaction with the source's transaction

The reader being called during the chunk cycle does not prove item receipt can roll back. Check the actual resource and transaction manager.

### Queue and database committing independently

A message may be acked while the database rolls back, or the database commits while the message is redelivered. Use XA/JTA when needed and supported by resources, or design idempotency/inbox/outbox.

### Acknowledging too early

If a message is acknowledged before the writer completes, subsequent failures can lose the message. Tie acknowledgement to the transaction or acknowledge only after data is durably persisted.

### Not guarding against duplicate processing

Redelivery can occur after a rollback or crash. Use message IDs, business keys, unique constraints, and idempotent operations.

### Returning null when the queue is only temporarily empty

Spring Batch may end the Step because `null` signals end-of-input. Clarify whether the Job drains a queue or acts as a continuous consumer.

### Failing to handle poison messages

Failing messages can be redelivered endlessly. Use retry limits, skip policies, quarantine, or DLQ.

### Assuming rollback only returns the single failing message

Rolling back a chunk transaction can cause all unacknowledged messages in the chunk to be redelivered. Design the processor and writer to tolerate re-execution.

## 17. Workflow for designing a transactional reader

When configuring a reader, determine:

1. Is the read source a file, database, queue, or API?
2. Does reading consume items from the source or only query data?
3. Does the resource support rollback and redelivery?
4. Does the reader participate properly in the chunk's transaction manager?
5. Should default buffering be used or `readerIsTransactionalQueue()`?
6. On rollback, which items are re-supplied and by what mechanism?
7. Do retry/skip cause the reader to be called again?
8. Are checkpoints stored in `ExecutionContext` or managed by the broker?
9. Do the queue and database need a shared transaction?
10. Does each message have a stable ID and idempotent processing?
11. Does an empty queue mean ending the Step or continuing to wait?
12. How are poison messages retried, skipped, or routed to a DLQ?

Test by intentionally failing the writer before commit, then observe whether the reader is called again, whether items are buffered or redelivered, queue acknowledgement, and database records. Also test stopping the process mid-chunk to verify real recovery behavior.

## Conclusion

A transactional reader fetches items from a resource capable of undoing item receipt within a transaction, typically a transactional message queue. For non-transactional readers, Spring Batch normally buffers already-read items to reprocess after a rollback. For transactional queue readers, configuring `readerIsTransactionalQueue()` disables buffering so the next read receives the message redelivered by the broker. This setting is only valid when queue receive/ack genuinely participates in an appropriate transaction. Distinguish the Step transaction from the read source transaction, coordinate queues and databases properly, understand empty-queue semantics, and design idempotency to handle redelivery safely.
