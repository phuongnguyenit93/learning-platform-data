# Errors mid-chunk and rollback

In Spring Batch, a chunk-processing Step gathers many items into a group, writes that group, and then commits the transaction. If an error occurs before the chunk's transaction is committed and that error is configured to cause a rollback, all changes belonging to the current chunk's transaction are undone. Chunks that were committed earlier are retained.

For example, a Step processes 9 orders with a commit interval of 3:

```text
Chunk 1: orders 1-3  --> WRITE --> COMMIT
Chunk 2: orders 4-6  --> WRITE --> ERROR --> ROLLBACK
Chunk 3: orders 7-9  --> not yet executed
```

When the error occurs in chunk 2, the database changes belonging to chunk 2's transaction are rolled back. The committed result of chunk 1 still exists. Spring Batch records the Step as failed and can support restart from the saved state, depending on the reader's restart capability, the Step configuration, and how the application manages its data.

## 1. The transaction boundary of a chunk

Chunk-oriented processing usually consists of three parts:

1. `ItemReader` reads items from the data source.
2. `ItemProcessor` processes or filters each item.
3. `ItemWriter` writes a group of processed items.

When you configure `chunk(3, transactionManager)`, Spring Batch processes up to three items in a chunk before writing and committing that chunk's transaction. The number 3 is the commit interval in the example; an application can choose another value according to the data size, processing time, and resource limits.

The general flow:

```text
             Begin transaction
                     |
                     v
              ItemReader.read()
                     |
                     v
           ItemProcessor.process()
                     |
           enough items / no more data
                     |
                     v
              ItemWriter.write()
                     |
               +-----+-----+
               |           |
            success    error requiring rollback
               |           |
               v           v
             COMMIT     ROLLBACK
               |           |
               v           v
          Next chunk   Current chunk
```

In a normal chunk step, reading, processing, and writing take place within a transaction managed by the Step's transaction manager. Written data is considered durable only after the transaction commits successfully. When an exception causes the transaction to roll back, the operations participating in that same transaction are undone.

## 2. What happens when an error appears mid-chunk?

Suppose the commit interval is 3 and `ItemWriter` writes three orders to the same database. The writer writes the first order, writes the second order, and then hits an error while writing the third order.

```text
Chunk 2 (orders 4, 5, 6)
       |
       v
Transaction begins
       |
       +--> INSERT order 4
       |
       +--> INSERT order 5
       |
       +--> INSERT order 6 --> exception
                              |
                              v
                         ROLLBACK
                              |
                              v
             The INSERTs in the transaction are undone
```

If all three write operations use the same transaction manager and the same database transaction, records 4 and 5 are also rolled back even though they were performed before the error occurred. After the rollback, they have not been committed to the database.

Rollback applies to the transaction of the running chunk. It does not automatically delete the changes belonging to earlier committed chunks, and it also does not automatically undo side effects that lie outside the transaction.

### Example per chunk

| Chunk | Items | Write result | Transaction status |
|---|---|---|---|
| 1 | 1, 2, 3 | Written successfully | `COMMIT` |
| 2 | 4, 5, 6 | Error when writing item 6 | `ROLLBACK` |
| 3 | 7, 8, 9 | Not yet run | No transaction yet |

After the error, chunk 1's data is still retained. The write operations belonging to chunk 2 are undone. Chunk 3 has not been processed because the Step stopped at the error.

## 3. Configuring the commit interval

With Spring Batch 5 and later, you can configure a chunk step with `StepBuilder` and pass in a `PlatformTransactionManager`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportStepConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, Order> orderProcessor,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(3, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

In the example:

- `chunk(3, transactionManager)` sets the commit interval to 3 and specifies the transaction manager for the Step.
- `orderReader` supplies the input data.
- `orderProcessor` transforms or validates each order.
- `orderWriter` writes the processed items in the chunk.

If the writer writes to a database managed by the same transaction manager, the chunk's write operations will participate in the same transaction. When an exception causes a rollback, the changes in that transaction are undone.

The commit interval affects the rollback scope. A small interval makes transactions shorter and limits the number of items in a single rollback, but increases the number of commits and the metadata overhead. A large interval reduces the number of commits but holds the transaction longer, uses more memory, and may have to reprocess more items when a chunk fails.

## 4. What is retained after a rollback?

You need to distinguish business data, execution metadata, and the reader's state:

| Component | When the chunk rolls back |
|---|---|
| Database changes in the same transaction | Undone. |
| Data from earlier committed chunks | Still retained. |
| The next chunk that has not started | No changes yet. |
| Metadata and checkpoint | Saved per the transaction and repository mechanism; restart state is based on the most recent committed checkpoint. |
| Side effects outside the transaction | Not automatically undone. |

For example, if chunk 1 has committed and chunk 2 rolls back, the durable checkpoint usually corresponds to the last successfully committed position. On restart, a reader that supports saving state can continue from an appropriate position. If the reader does not save state or is configured not to save state, the application may have to read again from the beginning or manage the continuation position itself.

Within a single execution that has retry or skip, Spring Batch can also buffer the items already read and orchestrate re-reading/re-processing according to the fault-tolerant policy. The specific behavior depends on whether the reader is transactional, the retry/skip configuration, and the type of error. Therefore, do not assume an item after a rollback is always re-read from the source in the same way for every type of reader.

## 5. Errors in the Reader, Processor, and Writer

Errors can arise at any phase of the chunk. With the default transaction and rollback policy of a normal chunk step, an exception that requires rollback will cause the current chunk's transaction to be undone.

### Errors in ItemReader

The reader can hit errors when querying the database, reading files, parsing data, or calling the input source. If the exception causes the transaction to roll back, the current chunk is not committed. The reader needs appropriate behavior when it is called again or when the Step restarts.

### Errors in ItemProcessor

The processor can detect bad data, data that cannot be converted, or business errors. Depending on the policy, the error can cause the chunk to roll back, be retried, or be skipped. If the processor calls an external service or creates side effects, the database transaction does not automatically undo those side effects.

### Errors in ItemWriter

The writer usually writes the whole group of items in the chunk. If the writer throws an exception before commit, the transaction can roll back all the chunk's write operations if the operations participate in the same transaction. The writer needs to avoid letting part of the result be committed independently before the chunk ends.

## 6. How do retry and skip affect rollback?

Spring Batch supports handling recoverable errors with retry and skip. The two mechanisms serve different purposes:

- **Retry:** retry the failing operation, usually suited to transient errors such as timeouts or deadlocks.
- **Skip:** skip the item that caused the error if the error belongs to the group allowed to be skipped and the number of skips has not exceeded the limit.

In a fault-tolerant chunk step, an error can cause the chunk to roll back before Spring Batch retries or determines which item to skip. Therefore, the same item may be processed multiple times. The processor and writer should be designed to tolerate being retried.

An example retry and skip configuration:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

In this configuration, a transient data access error is retried up to the retry limit; an invalid order can be skipped within the allowed limit. When retries are exhausted or the error is not allowed to be skipped, the Step can end `FAILED`.

Retry and skip do not mean that not every error rolls back. With chunk processing, rollback is part of how Spring Batch restores the transaction before carrying out the error-handling strategy. You need to read the logs and the retry/skip metrics to know which items were retried or skipped.

## 7. noRollback: exceptions that do not roll back the transaction

In some situations, an application wants a certain type of exception not to cause the transaction to roll back. Spring Batch supports declaring `noRollback` for specific exceptions in a fault-tolerant step.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(3, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .noRollback(NonCriticalValidationException.class)
        .build();
```

`noRollback` changes how the transaction reacts to the specified exception. It is not the same as `skip`: `skip` decides whether the failing item is ignored, while `noRollback` decides whether the exception causes the transaction to roll back.

Use `noRollback` only when the application guarantees the data state remains consistent if the transaction continues to commit. If the exception occurs after part of the write operations has been performed, allowing commit can save incomplete data. Clearly determine at which phase the exception arises and its impact on the other items in the chunk.

## 8. Rollback does not undo every side effect

A transaction can only roll back the resources participating in that transaction. If the writer or processor calls an external service, sends an email, writes a plain file, or updates another system that does not participate in the same transaction, a database rollback cannot automatically undo that action.

For example:

```text
Chunk transaction
      |
      +--> INSERT order into Database A
      |
      +--> Call HTTP to send the order to system B
      |
      +--> Error while processing the next item
      |
      +--> ROLLBACK Database A

System B may still have received the order.
```

If system B has received the request, rolling back Database A does not automatically send a recall command to B. When the chunk is retried, the HTTP request may be sent again.

Design approaches commonly used to handle this situation:

1. **Idempotency key:** send a unique business code so the target system recognizes it and does not perform the same request multiple times.
2. **Transactional outbox:** write the event to be sent into an outbox table in the same transaction as the business data; a separate process sends the event after commit.
3. **Compensation:** if the external system has performed an action that cannot be rolled back, create a compensating business operation to correct the state.
4. **Separating Steps:** write the business data in one Step and send the messages in another Step, with an appropriate retry and duplicate-prevention mechanism.

If multiple databases or resources need to commit atomically together, you must configure appropriate transaction coordination. Do not assume that just because operations are in the same `ItemWriter` method, they automatically belong to the same transaction.

## 9. Restart after a chunk fails

When a chunk fails and the Job ends `FAILED`, Spring Batch stores metadata so that the JobInstance can be restarted if the Job and Step allow restart.

For example:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #1: FAILED
         |
         +--> Chunk 1: COMMITTED
         +--> Chunk 2: ROLLED BACK
         +--> Chunk 3: not yet run

Restart with the same identifying JobParameters
  |
  +--> JobExecution #2
         |
         +--> Restore from the saved checkpoint
         +--> Continue processing the remainder
```

With a reader that supports restart and is configured to save state, the `ExecutionContext` can hold the read position at the commit boundary. A restart can continue from the nearest checkpoint instead of reprocessing all the data. The rolled-back chunk will be processed again in the way the reader and Step support.

Some conditions to note:

- The Job must not be configured with `preventRestart` if you want to restart.
- The reader needs to support saving and restoring state if you want to continue from the committed position.
- The writing components must tolerate the possibility that items are retried.
- Operations outside the transaction need a duplicate-prevention or compensation mechanism.
- You must use the same identifying JobParameters to restart the correct JobInstance.

If the reader does not save state, a restart may begin reading again from the start. In that case, the writer must be designed not to create duplicate records or must have an appropriate strategy for deleting/replacing data.

## 10. How to investigate an error mid-chunk

When a Step fails, you can use metadata and logs to determine the rollback scope:

1. **Identify the JobInstance and JobExecution.** Check the Job name, the identifying parameters, and the failing execution.
2. **Find the failing StepExecution.** Look at the `BatchStatus`, `ExitStatus`, and the recorded exception.
3. **Check the counters.** Cross-check `readCount`, `writeCount`, `filterCount`, the skip counts, `commitCount`, and `rollbackCount`.
4. **Identify the last committed chunk.** Read the checkpoint in the `ExecutionContext` if the reader supports restart.
5. **Cross-check the business data.** Check the records that exist after the earlier committed transactions.
6. **Check external side effects.** Determine which emails, messages, files, or API calls may have completed even though the database transaction rolled back.
7. **Choose how to restart or compensate.** Ensure no duplicate writes and no missed data before re-running.

The counters help guide the investigation but do not replace checking the actual data. For example, the `writeCount` in the metadata needs to be read together with the transaction outcome, the exception, and the repository state; do not rely on a single number to conclude that every record has been committed.

## 11. Common misconceptions

| Misconception | The correct understanding |
|---|---|
| If one item fails, only that item is rolled back | The transaction usually covers the whole chunk; the changes in the current chunk can roll back together. |
| A chunk rollback loses the data of all earlier chunks | Chunks that have committed are retained. |
| Once the writer has run some SQL statements, they are definitely saved | If they participate in the same transaction and the transaction rolls back, the changes are undone. |
| A database rollback also recalls an HTTP call or an email | Side effects outside the transaction are not automatically rolled back. |
| Restart always begins exactly at the failing item | Restart is usually based on the committed checkpoint; the ability to continue depends on the reader and the ExecutionContext. |
| Retry means there is no rollback | Retry can happen after a rollback to retry the operation in a new transaction. |
| Skip and noRollback are the same mechanism | Skip decides whether to skip an item; noRollback decides whether an exception causes a rollback. |
| The larger the commit interval, the faster it always is | A large chunk can hold the transaction longer, increase memory, and increase the reprocessing scope on errors. |

## Conclusion

In chunk processing, a transaction usually covers one chunk. If an error occurs before commit and is of a type that requires rollback, Spring Batch undoes the changes in the current chunk's transaction. Chunks committed earlier still exist; the next chunk has not been executed. Retry, skip, and noRollback can change how errors are handled but need to be configured with data consistency in mind. Rollback also only affects the resources participating in the transaction, so external side effects need an idempotency, outbox, or compensation mechanism. When the reader saves a checkpoint and the Step supports restart, the Job can continue from the most recent committed state after the error is dealt with.
