# Transactional Queue Reader

In Spring Batch, a regular ItemReader typically reads data from a file or a database. When a chunk rolls back, these sources do not automatically put just-read items back the way a message queue does. Spring Batch therefore includes a mechanism to buffer already-read items so they can be reused when reprocessing a chunk.

With a **transactional queue reader**, the situation is different: receiving messages participates in the queue's transaction. If the transaction rolls back, the broker can return received messages to a ready state so a consumer can read them again. In that scenario, Spring Batch should not keep a copy of the items in its internal buffer, because that copy could duplicate the messages the queue will redeliver.

To declare this behavior, Spring Batch provides the **readerIsTransactionalQueue()** method in chunk Step configuration. This setting informs the framework that the reader consumes from a transactional source capable of replaying items on rollback. It adjusts Spring Batch's buffering mechanism; the call itself does not create a broker transaction and does not guarantee the queue is configured properly.

## 1. What Is a Transactional Queue Reader?

A transactional queue reader reads messages from a queue inside a transaction. A message is considered successfully consumed when the transaction commits. If the transaction rolls back before completion, the message can be redelivered by the broker to a consumer.

Basic processing flow:

~~~text
Queue / Broker
     |
     v
ItemReader receives message
     |
     v
ItemProcessor
     |
     v
ItemWriter writes result
     |
     v
Commit transaction
     |
     +--> Queue confirms message consumed
     +--> Target data is committed
~~~

If an operation in the chunk fails:

~~~text
Queue / Broker
     |
     v
Reader receives messages A, B, C
     |
     v
Processor / Writer encounters error
     |
     v
Rollback transaction
     |
     +--> Messages not yet acknowledged as consumed
     |
     v
Broker can redeliver A, B, C
~~~

Redelivery capability is a key characteristic of a transactional queue. It allows a message that was not processed successfully to return to the processing flow after rollback.

Not all queues share identical semantics. JMS transacted sessions, RabbitMQ channel transactions/acknowledgements, and queue services based on visibility timeouts have different mechanisms. Verify how the adapter and transaction manager in use actually support rollback/redelivery behavior.

## 2. Why Does Spring Batch Need to Know the Reader Uses a Transactional Queue?

For a non-transactional reader, Spring Batch typically buffers items read in the chunk. When the writer or processor causes the transaction to roll back, the framework can pull items back from the buffer instead of asking the reader to read from the source again.

This is useful for sources such as files or certain database readers. Re-reading from the source might not return the exact same items if the source changed, the cursor advanced, or the read cannot be rolled back.

With a transactional queue, the queue itself is responsible for replaying messages after rollback. If Spring Batch still holds already-read items in the buffer, two paths can produce duplicates:

1. The chunk rolls back and the broker puts the message back onto the queue.
2. Spring Batch keeps the old item in its buffer.
3. The next processing pass uses the buffered item and commits.
4. The message remains on the queue because the previous receive rolled back.
5. The reader reads that message once more, leading to duplicate processing.

Therefore, for a transactional queue reader, you must tell Spring Batch not to buffer already-read items. The framework will call the reader again after rollback, and the queue will supply the redelivered messages.

## 3. Configuring readerIsTransactionalQueue()

In Spring Batch 5, you can enable transactional queue mode on a chunk Step:

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

In this example:

- The reader fetches messages from a queue.
- The chunk size is 20, so one chunk can hold up to around 20 successfully read messages.
- readerIsTransactionalQueue() indicates that the reader uses a transactional queue.
- If the transaction rolls back, the framework does not keep read items in the standard buffer; the reader is called again and the queue can redeliver messages.

In XML configuration for Spring Batch versions supporting the corresponding attribute, you can declare reader-transactional-queue="true" on the chunk element. Exact Java/XML API names depend on version; use the configuration matching your project's version.

Crucially, call this setting only when the reader actually reads from a source with rollback/redelivery semantics. Do not enable it for regular file readers or database readers merely to save memory.

## 4. Default Buffering Mechanism vs. Transactional Queue

Compare the two reader styles:

| Aspect | Regular Reader | Transactional Queue Reader |
| --- | --- | --- |
| Data source | File, cursor, query, or non-rollbackable source | Queue with transactional message reception |
| When chunk rolls back | Spring Batch typically reuses buffered items for reprocessing | Queue can redeliver messages |
| In-framework item buffering | Usually used to avoid re-reading source | Disabled via readerIsTransactionalQueue() |
| Key requirement | Re-read or buffered items must stay consistent | Queue receive must properly participate in the transaction |

Example with chunk size 3:

**Regular reader**

~~~text
Read A, B, C
    |
    v
Buffer A, B, C
    |
    v
Writer error -> rollback
    |
    v
Framework reuses A, B, C from buffer
~~~

**Transactional queue reader**

~~~text
Receive A, B, C in queue transaction
    |
    v
Writer error -> rollback
    |
    v
Broker puts A, B, C back
    |
    v
Reader is called again and receives A, B, C
~~~

If a transactional queue reader still uses internal buffering, items reprocessed from the buffer can diverge from the actual state of the queue. That is why proper configuration matters.

## 5. Queue Transaction and Database Transaction

A chunk often both receives messages from a queue and writes data to a database. For receiving messages and writing results to be atomic, both operations must participate in a single transaction capable of coordinating both resources.

### One Transaction Coordinating Both Queue and Database

With a transaction manager supporting resource coordination, such as JTA/XA when both broker and database support XA, you can design:

~~~text
Chunk transaction
    |
    +-- receive message from queue
    |
    +-- write data to database
    |
    +-- commit shared transaction
           |
           +--> Queue acknowledges message
           +--> Database commits data
~~~

If the shared transaction rolls back, both message reception and database writes can be undone according to the transaction protocol supported by the resources. This pattern prevents the situation where a message is acknowledged while target data failed to commit.

### Two Independent Transaction Managers

If the queue and database use two independent transaction managers, one rollback does not automatically undo both resources:

~~~text
JMS transaction              Database transaction
     |                              |
 receive message                write data
     |                              |
 commit                          rollback
     |                              |
 message acked                   no data
~~~

In this situation, a message may have been acknowledged as consumed while business data does not exist. The reverse can also occur: the database commits while queue reception was not acknowledged, so the message is redelivered and risks duplicate writes.

Merely passing one PlatformTransactionManager to the Step does not automatically coordinate every resource. Understand which resource that transaction manager governs and how the queue client participates in transactions.

If XA/JTA is not used, design around at-least-once delivery with idempotent processing, an inbox table, unique message keys, or an outbox depending on the business flow. The goal is ensuring each message is processed at least once without redelivery producing duplicate results.

## 6. Example with JMS and JmsTemplate

A custom reader can use JmsTemplate for synchronous message reception:

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
        // Convert JMS Message to application model.
        // Implementation depends on message format.
        throw new UnsupportedOperationException("Implement conversion");
    }
}
~~~

This is a skeleton example of synchronous reading. Message conversion must be implemented according to your actual payload. More importantly, JmsTemplate must participate properly in the JMS transaction managed for the chunk. Calling readerIsTransactionalQueue() does not configure JmsTemplate, ConnectionFactory, or acknowledgement mode by itself.

With JMS, JmsTransactionManager can manage local JMS transactions. If the chunk also writes to a database, clarify which transaction manager is used and how the database transaction is coordinated. If atomicity between message reception and database writes is required, use an appropriate resource-coordination solution or design idempotency/compensation.

Do not manually acknowledge messages or commit the JMS session inside the reader before the writer completes. If a message is acknowledged prematurely, errors in the processor or writer cannot cause the queue to redeliver that message.

## 7. Empty Queues and the Meaning of read() Returning null

In Spring Batch, ItemReader returns null to signal there are no more items in the input. For a file or bounded query, this usually means the Step has finished reading all data.

With a queue, distinguish between:

- The queue has been drained at the current moment.
- The queue has no messages temporarily, though new messages may arrive later.

If the reader uses a receive timeout and returns null when the wait expires, Spring Batch may treat that as end-of-input and finish the Step. This fits a Job whose goal is draining a queue until it is temporarily empty. It does not fit a continuously running consumer waiting indefinitely for new messages.

For continuous workflows, consider a message-driven consumer model or an explicitly designed polling/orchestration mechanism. Do not assume a standard chunk Step will wait forever after the reader returns null.

When building a queue-draining Job, clearly define the termination criterion: queue empty at check time, reaching a message count, elapsing a time window, or completing a specific batch ID. That criterion is a business rule of the Job.

## 8. Rollback and Redelivery Within a Chunk

Suppose the chunk size is 3 and the queue holds messages A, B, C, D, E:

~~~text
Initial queue: [A, B, C, D, E]

Chunk 1:
  receive A
  receive B
  receive C
  process A, B, C
  write A, B, C
  commit

Queue after commit: [D, E]

Chunk 2:
  receive D
  receive E
  writer error
  rollback

Queue after rollback can redeliver: [D, E]
~~~

When chunk 2 rolls back, messages D and E have not been acknowledged as consumed in the queue transaction. The next read can receive D and E again. Messages A, B, and C, already committed earlier, should not be redelivered from that transaction.

If a chunk holds multiple messages and only one item causes an error, rollback can cause all messages in the chunk's transaction to be redelivered, not only the failing message. Consequently, retrying or skipping one item can cause other items in the chunk to be re-read as well depending on how transactions and fault-tolerant processing operate.

Processors and writers should be idempotent or handle reprocessing safely. Do not assume only the failing item gets redelivered.

## 9. Skip and Retry with a Transactional Queue

Skip and retry can work with transactional queues, but you must understand how rollback affects all messages currently in the chunk.

### Retry

If a transient error occurs during processing or writing, Spring Batch can roll back the transaction and retry according to the retry policy. With a transactional queue, messages are redelivered by the broker when the reader is called again. Configuring readerIsTransactionalQueue() lets the framework rely on redelivery rather than old buffered items.

Example:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

This example illustrates retrying transient database errors. Verify actual exceptions and the transaction manager to ensure queue reception rolls back and messages are redelivered.

### Skip

If a message is permanently invalid, you can skip data exceptions:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderMessageException.class)
        .skipLimit(100)
        .build();
~~~

When skipping, the Step must complete the transaction per policy. The failing message must be acknowledged as consumed or routed to error handling by design; otherwise, the broker may keep redelivering the message and create an error loop.

Use a SkipListener or a quarantine/dead-letter mechanism to store failing messages and reasons. If recording rejected records occurs on a resource separate from the queue transaction, design it so the message is not acknowledged before error details are durably saved.

## 10. Poison Messages and Dead-Letter Queues

A poison message is one that always fails processing—for example, malformed payload, missing required fields, or unrecoverable rule violations. With a transactional queue, if every processing attempt rolls back, the message may be redelivered repeatedly.

~~~text
Queue
  |
  v
Receive failing message
  |
  v
Processor throws exception
  |
  v
Rollback
  |
  v
Message redelivered
  |
  +---- repeats infinitely if there is no limit
~~~

To prevent loops:

- Classify unrecoverable data errors.
- Bound retries or delivery attempts per broker capabilities.
- Use a SkipListener or error handler to record error details.
- Move messages to a dead-letter queue (DLQ) or quarantine when criteria are met.
- Retain message ID, correlation ID, delivery count, and failure reason for investigation.
- Maintain a workflow to repair and replay messages after data is fixed.

Do not move a message to a DLQ before confirming the failed message record has been durably saved. If writing to the DLQ and acknowledging the original queue are not transactionally coordinated, use idempotency or reconciliation to avoid losing messages.

## 11. Differences Between JMS, RabbitMQ, and Visibility-Timeout Queues

The concept of a transactional queue can be implemented differently across brokers:

| Technology | Common Mechanism | Points to Verify |
| --- | --- | --- |
| JMS transacted session | Receive and acknowledge are managed by the JMS transaction; rollback can redeliver | Whether JmsTransactionManager/JTA actually manages the reader's session |
| RabbitMQ | Manual acknowledgement; channel transactions or post-processing acknowledgement depending on config | Whether messages are acked after business commit; whether channels are properly transaction-managed |
| Visibility-timeout-based queue | Message is temporarily hidden after receive; reappears if not deleted/acked before expiration | Visibility timeout, delete timing, lease extension, and duplicate-delivery possibility |

Do not treat these mechanisms as identical. For example, a visibility timeout is not necessarily a database transaction rollback. A message can reappear because a consumer died or a lease expired, even without an explicit rollback command.

readerIsTransactionalQueue() only adjusts Spring Batch's buffering. Broker acknowledgement, rollback, redelivery, or visibility-timeout expiration are still governed by the client, adapter, and transaction/acknowledgement configuration.

## 12. Chunk Size and In-Flight Message Count

Chunk size determines how many messages a chunk transaction may receive before committing. Larger chunks can boost throughput, but also increase the number of in-flight messages and lengthen transactions.

Example:

| Chunk Size | Common Consequence |
| ---: | --- |
| 1 | Each transaction processes one message; frequent commits |
| 10 | One transaction processes up to around 10 messages |
| 100 | Fewer commits, but many messages roll back together if the chunk fails |
| 500 | Longer transactions and potentially higher in-flight message counts |

When choosing chunk size, consider:

- Processing time per message.
- Commit latency of the queue and database.
- Number of messages that could redeliver together on rollback.
- Memory footprint of payloads and transformed objects.
- Broker client prefetch/buffering.
- Load capacity of the writer and database.
- Retry/skip behavior and reprocessing cost.

Do not choose a huge chunk size solely to reduce commit frequency. An overly large chunk can cause many messages to be redelivered after a single error and increase reprocessing load.

## 13. Checkpoints and Queue State

With file readers, Spring Batch typically saves the read position into ExecutionContext so restarts resume from the checkpoint. With transactional queues, the broker typically tracks unacknowledged message state and can redeliver when the queue transaction rolls back.

These two mechanisms differ:

- **ExecutionContext checkpoint:** execution state persisted by the reader/Step in JobRepository.
- **Queue delivery/ack state:** message state managed by the broker and transaction/acknowledgement mechanism.

Do not manually store an offset in ExecutionContext and assume it replaces transactional message reception. Queues may have their own ordering, partitions, consumer groups, or redelivery semantics.

When a Job restarts after a process crash:

- Messages already committed/acked are typically no longer in that consumer's queue.
- Uncommitted/unacked messages can be redelivered by the broker.
- Messages written to the database but not yet acked may reappear and require idempotency to avoid duplicate writes.
- Messages acked while the database failed to commit may be lost from the queue if the two resources do not share a transaction.

Therefore, design transaction boundaries across the queue, JobRepository, and business data. JobRepository stores Job/Step state, but does not automatically manage acknowledgements for arbitrary brokers.

## 14. Idempotency and Handling Duplicate Messages

A transactional queue enables redelivery on rollback, but it does not guarantee end-to-end exactly-once semantics. Messages can be redelivered when a consumer loses connectivity, the broker misses an acknowledgement, or the process crashes during an ambiguous commit window.

A common approach is storing message IDs or business keys with a unique constraint:

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

The example above illustrates the idea; both checking and writing must be protected by appropriate transactions and unique constraints to prevent race conditions when multiple consumers process the same message.

An inbox table can be used:

~~~text
inbox_message
---------------------------------
message_id (UNIQUE)
received_at
processed_at
status
error_code
~~~

When processing a message, the application records the message ID and updates business data within the same database transaction. If the message is redelivered, the unique key helps detect that the message was already processed.

Idempotency is especially important for remote APIs, emails, payments, or message publishing. A local queue transaction cannot undo side effects already completed in another system.

## 15. Common Mistakes

### Enabling readerIsTransactionalQueue for a Non-Transactional Reader

The framework stops buffering items, yet the source does not guarantee redelivery. After rollback, items may be lost or the reader may advance to another position. Enable only when the queue/client genuinely supports appropriate rollback or redelivery.

### Thinking readerIsTransactionalQueue Creates a Broker Transaction

This method only configures Spring Batch's buffering behavior. You must separately configure the transaction manager, connection factory, session, or acknowledgements.

### Queue Committing Independently from Database Commit

Messages can be acked while the database rolls back, or vice versa. Use XA/JTA if atomicity is required and supported by resources; otherwise, design at-least-once processing with idempotency/outbox/inbox.

### Acking Messages Before the Writer Completes

If a message is acknowledged before target data commits, a writer error can lose the message. Acknowledgements must be tied to the transaction or executed only after durable processing.

### Not Handling Poison Messages

Failing messages can be redelivered infinitely. Use retry limits, skip policies, DLQs, and quarantine workflows.

### Returning null When a Queue Is Temporarily Empty

Spring Batch interprets null as end-of-input. If a Job must wait for new messages, use an appropriate polling/consumer model rather than ending the Step unexpectedly.

### Assuming Rollback Redelivers Only the Failing Item

A chunk transaction can hold multiple messages. Rollback may cause all unacknowledged messages in the chunk to be redelivered.

### Neglecting Duplicate-Processing Protection

Redelivery can occur after crashes or ambiguous acknowledgement states. Use message IDs, business keys, unique constraints, and idempotent operations.

### Ignoring Broker Prefetch and In-Flight Limits

Brokers may pre-deliver more messages than the current chunk. Control prefetch, concurrency, and in-flight message counts to avoid memory growth or overloading the broker.

## 16. Workflow for Configuring a Transactional Queue Reader

When building a queue-reading Step, determine in order:

1. Which transactional receive/ack or redelivery mechanism do the broker and client support?
2. Does the reader actually participate in the chunk transaction, or is it auto-acking?
3. Does the Step's transaction manager govern JMS, AMQP, the database, or JTA?
4. Do queue reception and database writes require atomicity within the same transaction?
5. Without a shared transaction, how will idempotency/inbox/outbox handle split commits?
6. Should readerIsTransactionalQueue() be called to disable Spring Batch buffering?
7. Does an empty queue mean ending the Job, or should the consumer keep waiting?
8. How are retry, skip, redelivery count, and DLQ configured?
9. Do chunk size and broker prefetch fit memory, throughput, and in-flight message limits?
10. Are the reader, processor, and writer safe when messages are redelivered?
11. Which messages or partitions could be re-run on Job restart?
12. Do logs record message ID, delivery count, and Job/Step execution for reconciliation?

Test at least these scenarios: writer failure before commit, database connection loss, broker connection loss, process kill mid-chunk, invalid messages, redelivered messages, and temporarily empty queues. Observe both database data and broker message state to verify actual behavior.

## Conclusion

readerIsTransactionalQueue() tells Spring Batch that the reader fetches items from a transactional queue capable of redelivering messages when a chunk rolls back. When enabled, the framework skips normal item buffering and calls the reader again so the queue supplies redelivered messages. This setting is valid only when receive/ack genuinely participates in the transaction or broker redelivery is properly configured. Distinguish queue transactions from database transactions, handle empty queues per ItemReader semantics, control poison messages, and design idempotency to tolerate redelivery.
