# Writers and Handling Partial Failure

In Spring Batch, `ItemWriter` receives a chunk's group of items and writes the results to a destination such as a database, a file, or a message broker. One difficult situation to handle is **partial failure**: the writer has written some of the items but hits an error before completing the whole chunk.

How to recover depends on where the writer writes the data and whether a transaction covers that operation. If all write operations participate in one transaction, a rollback can undo the entire chunk. If the writer writes to a system outside the transaction, part of the data may already exist even though the Step reports an error. In that case, a retry can create duplicate data or make the result inconsistent.

Writer design needs to define clearly the transaction boundary, how exceptions are handled, retry/skip capability, and the idempotency of the write operation. Do not assume Spring Batch can automatically undo every side effect the writer has performed.

## 1. What Is Partial Failure in an ItemWriter?

In chunk-oriented processing, Spring Batch gathers items, processes them, and then calls `ItemWriter` to write the results. For example, with a commit interval of 100, the writer receives a chunk of 100 orders.

Suppose the writer writes each order sequentially:

```text
Chunk of 100 orders
       |
       +--> Write orders 1..40 successfully
       |
       +--> Write order 41 hits an error
       |
       +--> Writer throws an exception
```

The writer has done part of its work before the error occurred. The final result depends on how the write operations are managed:

- If the 40 write operations participate in the same transaction as the Step, the transaction can roll back and discard all 40 changes.
- If each operation has been committed separately, or the data was sent to a system that does not support rollback, the first 40 changes may still remain.
- If the writer catches the exception and returns normally, Spring Batch may consider the chunk write successful and commit the transaction, even though only some of the items were written.

Therefore, partial failure is not just an exception. It is a situation where the actual state of the write destination may not match the state that Spring Batch records for the chunk.

## 2. ItemWriter Is Called Within the Chunk's Transaction

With a chunk-oriented Step, Spring Batch usually performs reading, processing, and writing within the chunk's transaction boundary. When the writer throws an exception that makes the chunk fail, the transaction manager rolls back the current transaction according to the configuration.

Step configuration example:

```java
@Bean
public Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`chunk(100, transactionManager)` determines the transaction manager the Step uses for the chunk. For a rollback to take effect on the data the writer writes, the write operations must participate in that transaction. For example, a `JdbcTemplate` using the same `DataSource` that the transaction manager manages usually participates in the current transaction through Spring's transaction synchronization mechanism.

### Example of writing to a database in the same transaction

```java
public class JdbcOrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id, amount) values (?, ?)",
                    order.getId(),
                    order.getAmount()
            );
        }
    }
}
```

If the 41st insert operation throws an exception and all inserts use the same transaction, the earlier inserts in the chunk are also rolled back. In that case, rerunning the chunk does not create duplicate records from the 40 rolled-back inserts.

This is only true when the operations actually participate in the same transaction. If a repository opens a `REQUIRES_NEW` transaction for each item, the writer calls a different datasource, or it commits the connection itself, those changes may persist after the chunk's transaction rolls back.

## 3. When Rollback Cannot Undo a Partial Write

A database transaction does not automatically cover every kind of write destination. The following examples usually need their own strategy:

| Write destination | Rollback capability from the Step's transaction | Risk when the writer fails midway |
|---|---|---|
| Database with the same transaction manager | Can roll back all changes in the transaction | Lower if all operations are in the same transaction and there are no independent commits |
| File or object storage | Does not automatically roll back with the database transaction | The file may contain partial data or may already be published |
| HTTP API or external service | Does not automatically roll back a call the service has accepted | Resending can create duplicate transactions or records |
| Message broker | Depends on the broker's transaction and the integration approach | Some messages may already have been published |
| Multiple databases or multiple resources | Atomic only if there is an appropriate coordinated transaction mechanism | One resource commits while another rolls back |

For example, the writer successfully sends 40 messages to the broker and then the 41st message hits an error. The Step's database transaction rollback cannot retract the 40 messages the broker has already received, unless the writer and broker are integrated with a transaction mechanism capable of an appropriate rollback.

Similarly, the writer calls an API that creates an invoice for each item. If the API has created 40 invoices and then the 41st request fails, retrying the whole chunk may resend the first 40 requests. If the API does not support idempotency, the result can be duplicate invoices.

## 4. Do Not Swallow Exceptions After a Partial Write

A dangerous mistake is for the writer to catch an exception, log it, and then continue or end the method normally:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        try {
            externalClient.send(order);
        } catch (RuntimeException ex) {
            log.error("Could not send order {}", order.getId(), ex);
            // Return normally even though the item has not been sent.
        }
    }
}
```

Because the method ends normally, Spring Batch may consider the chunk write successful. The framework does not know which item failed if the writer does not report the error or return a separate result under a contract the application designed. The Step may complete with missing data.

If the error must make the chunk fail, let the exception propagate out of the writer or wrap it in an appropriate exception:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        try {
            externalClient.send(order);
        } catch (ExternalServiceException ex) {
            throw new ItemWriteFailureException(
                    "Failed to send order " + order.getId(), ex
            );
        }
    }
}
```

If the business allows some items to fail while continuing, represent the success/failure result explicitly, store the list of errors, or use an appropriate skip policy. Do not turn a failure into a success by ignoring the exception.

## 5. Retry and the Risk of Duplicate Writes

Retry is useful for transient errors such as deadlock, lock contention, or an external service losing its connection for a short time. But if the writer has written part of the data before throwing the exception, a retry may call the writer again with items that were already processed the previous time.

In a database transaction that is rolled back entirely, retrying the chunk can usually write again safely because the previous attempt's changes have been discarded. For side effects that cannot be rolled back, the writer must be idempotent so that the same item sent multiple times still produces a single business result.

### Designing an idempotent writer

A write operation is idempotent when repeating it with the same business identifier does not create unintended additional effects. Some commonly used approaches:

- Use a stable business key and a unique constraint in the database.
- Use `UPSERT` or an update operation by business key instead of a blind insert where appropriate.
- Send an idempotency key to the external API if the service supports it.
- Store the send status and result per item so reconciliation is possible.
- Set a stable request ID or message ID so the consumer can detect duplicate messages.

For example, an API that receives invoice-creation commands can accept `orderId` as the idempotency key. When the writer resends the same `orderId`, the service returns the result of the previously created transaction instead of creating a new invoice. The target API must support this capability; merely sending an arbitrary header does not create idempotency on its own.

### Configuring bounded retry

For transient errors in the writer, you can configure retry on the Step:

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Retry needs a limit and should apply only to errors that can recover on their own. Do not retry indefinitely on invalid-data errors or a fixed configuration error. If the writer writes to a system outside the transaction, make sure the retry operation is safe before enabling retry.

## 6. Skip When an Item Cannot Be Written

Skip is suitable for errors that belong to a single item and that the business allows to be ignored, such as data violating a specific rule. When the writer throws an exception and the Step is configured with write-skip, Spring Batch can roll back the chunk and then perform additional processing steps to identify the item that caused the error and skip it according to the skip policy.

Configuration example:

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
```

When handling a write-skip, the framework may call the writer again with a smaller set of items or with each item individually to identify the element causing the error. The details of the path depend on the error type and the fault-tolerance mechanism of the Spring Batch version. Therefore, the writer must withstand being called again and must not create duplicate side effects.

Do not skip infrastructure errors such as the database being unavailable, running out of connections, or the broker going down. These errors usually affect many items and need bounded retry, stopping the Step, or restoring the infrastructure. Skip should only be used when ignoring the item is an accepted business decision and is recorded.

## 7. Distinguishing Retry, Skip, and Rollback

| Mechanism | Goal | Main behavior |
|---|---|---|
| Rollback | Return a transactional resource to its state before the chunk | Discards uncommitted changes in that transaction |
| Retry | Retry an operation that may succeed after a transient error | Calls processing or writing again according to the fault-tolerance mechanism |
| Skip | Ignore an allowed failing item | Continues with other items and records the skip |
| Restart | Continue a JobInstance after an execution failed/stopped | Creates a new JobExecution and restores the saved checkpoint |

The mechanisms can be combined. For example, a transient write error may cause the chunk to roll back and then retry. An unrecoverable data error may cause the chunk to roll back and then be skipped if the configuration allows. If retries exceed the limit or the error is not skippable, the Step can end `FAILED`.

Rollback only affects resources that participate in the transaction. It does not delete an HTTP request that has already been processed, does not retract an email that has been sent, and does not delete a file that has been published.

## 8. File Writing and Handling Partial Failure

A file writer can hit an error in the middle of writing a chunk due to running out of disk space, an I/O error, or the process being stopped. In that case the file may contain part of the chunk's content. The Step's database transaction cannot undo bytes already written to the file.

For file output, use Spring Batch's built-in writers when appropriate, because implementations such as `FlatFileItemWriter` support `ItemStream` and a state-saving mechanism to serve restart. You need to set a stable writer name, configure `saveState` appropriately, and keep the append/overwrite rules consistent with the restart strategy.

For a custom file writer, you need to design clearly:

- The committed position or byte offset is saved into the ExecutionContext.
- `open()` restores the position and checks whether the current file is the right file from the previous run.
- `update()` writes the checkpoint at the time the framework requests it.
- `close()` releases the stream and resources.
- On rollback or restart, the writer can truncate the uncommitted portion or recreate the file through a safe procedure.

A common strategy is to write to a temporary file per execution or business key, finalize and verify the file after the Job succeeds, and only then publish/rename it to the official file. If the target file already exists, you need to specify clearly whether to overwrite, version, or reject. Do not let a consumer read a file that is partially written.

## 9. Sending Messages or Calling APIs from the Writer

Writing messages or calling an API is usually a side effect outside the database transaction. If the writer sends multiple messages and then hits an error, the messages the broker has already received may not be retracted when the chunk rolls back.

Design directions:

**Transactional producer:** use the broker's transaction if the broker supports it, so a group of messages can commit or abort together within the scope of the broker's transaction. This does not automatically make the database transaction and the broker a single transaction.

**Idempotent consumer or API:** attach a stable ID to each message/request; the receiver stores the IDs it has processed and drops repeated requests. This is a useful option when a retry may resend items.

**Outbox pattern:** the writer writes the business data and an outbox record in the same database transaction. A separate publisher reads the outbox and sends messages; the publisher marks the send status or retries using a stable identifier. The consumer should still be idempotent because a message may be resent if the publisher encounters an error after the broker receives the message but before it updates the outbox status.

Example of the outbox model:

```text
Chunk transaction
       |
       +--> Write order to the orders table
       |
       +--> Write event to the outbox table
       |
       +--> Commit both changes

Separate publisher
       |
       +--> Read unsent events in the outbox
       +--> Publish message with a stable eventId
       +--> Update the send status
```

The outbox helps avoid the situation where the database has committed the order but the application stops before sending the event. It does not make message sending absolutely exactly-once; you need to design duplicate handling at the consumer or broker.

## 10. Listeners and Observing Write Errors

`ItemWriteListener` provides callbacks to record writer activity:

| Callback | Timing and purpose |
|---|---|
| `beforeWrite` | Before the writer writes the chunk |
| `afterWrite` | After the writer call completes normally |
| `onWriteError` | When the writer call throws an exception |

Listener example:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.info("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.info("Writer call completed for {} orders", items.size());
    }

    @Override
    public void onWriteError(Exception exception,
                             Chunk<? extends Order> items) {
        log.error("Writer failed for chunk of {} orders", items.size(), exception);
    }
}
```

`afterWrite` indicates that the writer call ended normally; it does not by itself prove that the chunk's transaction has committed. An error at a later stage in the chunk can cause the transaction to roll back even though this callback has been called. Therefore, logs or metrics in the listener should describe the event accurately, for example "writer call succeeded", rather than asserting that the data has been committed.

To observe the final result, combine the listener with the `StepExecution` state, the read/write/skip/rollback counters, and the metadata after the Step ends. Avoid sending an irrevocable success notification from `afterWrite` if the transaction has not committed.

## 11. Partial Failure Handling Strategy by Write Destination

| Write destination | Preferred strategy | What to avoid |
|---|---|---|
| Database in the same transaction | Let the exception propagate; roll back the whole chunk; bounded retry for transient errors | Committing each item separately if you want atomicity per chunk |
| Database with multiple transaction managers | Determine clearly which resources share a transaction; consider an outbox or a coordinated transaction | Assuming one manager's rollback undoes another database |
| File | Use a writer with state support, or a temporary file and publish on completion | Letting a consumer read a partially written file |
| HTTP API | Idempotency key, store the result per item, bounded retry | Resending requests without a deduplication key |
| Message broker | Broker transaction, outbox, and idempotent consumer | Assuming a database rollback retracts published messages |

Another option is to split the writer into stages: write data to staging first, verify the count and validity, and then promote to the official table or location. Staging makes it easier to investigate and rerun the incomplete portion, especially when the write destination does not support a shared transaction with Spring Batch.

## 12. Common Misconceptions

**Believing an exception always undoes every written item.** Rollback only undoes changes in resources that participate in the transaction. External side effects can still exist.

**Catching an exception and ignoring it.** Spring Batch may consider the writer successful and commit the chunk even though some items were not written. Propagate the exception or represent the failure result explicitly.

**Enabling retry without checking idempotency.** The writer may be called again after it has already created side effects. You need to ensure repeated writes do not create duplicate data.

**Using skip for infrastructure errors.** A database or broker going down is not an error of a single item. Stop or retry according to an appropriate policy instead of silently dropping data.

**Treating `afterWrite` as after-commit.** The callback confirms the writer call succeeded, not that the chunk transaction has committed.

**Splitting transactions per item but expecting atomicity per chunk.** If each item commits independently, an error in a later item cannot roll back the earlier items through the chunk transaction.

## 13. How to Design a Recoverable Writer

Before implementing a writer, determine whether the write destination participates in the Step's transaction. For a database in the same transaction, let the exception roll back the chunk and only retry transient errors. For a file, API, or broker, design checkpoints, idempotency keys, an outbox, or a staging process to handle the portion written before the error.

The writer should have clear behavior when it cannot write the whole chunk: report an appropriate exception, let Spring Batch apply rollback/retry/skip according to the configuration, and provide enough logging to identify the item or chunk that hit the error. Such a design helps the system recover after a partial failure without silently losing data or creating duplicate effects on a rerun.
