# When chunk processing is a better fit than a tasklet

In Spring Batch, both chunk-oriented processing and a Tasklet are ways to build a `Step`. What decides the choice is the nature of the work. Chunk processing is a better fit when a Step needs to process a stream of many items in a read, process, and write cycle, needs to commit in groups, track progress per item, or apply skip/retry policies at the record level.

A Tasklet suits a single, self-contained action or procedure such as calling a stored procedure, cleaning up temporary data, checking a condition, moving a file, or calling a service once. A Tasklet can still loop and manage its own checkpoint, but if you have to build the loop of reading, processing, writing, paging, retry, skip, and recovery yourself for thousands or millions of records, chunk processing usually expresses the model more accurately and takes advantage of Spring Batch's built-in mechanisms.

## 1. Recognizing work that suits chunk processing

Chunk processing divides data into groups of items. Within each chunk, Spring Batch performs these main steps:

1. `ItemReader` reads the next item from the data source.
2. `ItemProcessor` processes each item, for example validating, normalizing, calculating, or transforming data.
3. `ItemWriter` receives the processed items and writes them in a group.
4. When the chunk completes, the transaction is committed. If processing hits an error that requires rollback, the current transaction is undone according to the configured policy.
5. The Step continues with the next chunk until the reader reports no more data.

```text
Data source
     |
     v
  ItemReader
     |
     v
  ItemProcessor -- per item
     |
     v
   ItemWriter -- whole chunk
     |
     v
  Commit transaction
     |
     +------> Next chunk
```

For example, a Job imports 500,000 transactions from a CSV file. Each transaction needs its account code checked, a fee calculated, the date normalized, and to be saved to the database. This is a clear item stream: each transaction goes through the same pipeline, but many transactions are written and committed together. Chunk processing is a better fit than a Tasklet that hand-writes a loop over the whole file.

## 2. When many items need to be processed through the same pipeline

This is the most important sign for choosing chunk processing. The work usually has three responsibilities that can be separated:

- **Read:** fetch items from CSV, a database, a message source, or another data source.
- **Process:** apply rules to each item without having to orchestrate the whole Job.
- **Write:** save the valid items to a database, file, or target system.

Situations that usually fit:

- Importing thousands of CSV lines and saving them as business records.
- Reading a staging table, normalizing each row, and writing to the main table.
- Converting data from an old format to a new format.
- Synchronizing a list of customers or products between two systems.
- Calculating tax, fees, or balances for each transaction.
- Exporting data record by record to a file or target system.
- Calling a service for each item and then saving the processing result.

If each item can be described by an input, a processing step, and a result, chunk processing creates an easy-to-understand structure. `ItemReader`, `ItemProcessor`, and `ItemWriter` can be tested and changed independently.

A Tasklet can still call a service to process a list of items, but once the logic inside has become a loop-per-record pipeline, the application has to orchestrate the loop and the related mechanisms itself. That is a sign to move to chunk processing.

## 3. When you need to commit in groups

Chunk processing fits when the business accepts a group of items being processed in the same transaction. The commit interval defines the number of items in a chunk, for example:

```java
.<OrderInput, Order>chunk(500, transactionManager)
```

With a commit interval of 500, Spring Batch gathers up to 500 items in a chunk before committing. The last chunk can have fewer if the data source has run out. One commit does not definitely mean the writer receives a full 500 items: the processor can filter items by returning `null`, and the skip policy can skip failing items.

For example, when processing 10,000 transactions with a chunk size of 500, the Step usually has about 20 chunks if there is no filtering, skipping, or special condition. Each chunk is committed separately. If the 12th chunk fails and the transaction rolls back, the chunks committed earlier are retained; the current chunk is handled per the Step's error and restart policy.

This transaction boundary is useful when:

- You want to avoid a single transaction running across hundreds of thousands of records.
- You need to limit the amount of data that may have to be rolled back in a single failure.
- The writer supports batch insert/update and can write efficiently in groups.
- You need to balance commit cost against memory, database locks, and processing time.

A Tasklet also runs in the transaction configured for the `execute` call, but if the Tasklet handles a long loop itself in one call, it can create a long transaction. A Tasklet can be split into multiple calls with `RepeatStatus.CONTINUABLE`, but then the application has to determine the unit of work and the checkpoint itself. Chunk processing provides a ready-made commit unit per group of items.

## 4. When you need skip and retry at the item level

Chunk processing is especially useful when the data may contain some bad records but the Job still needs to process the remaining records according to a defined policy.

For example:

- A CSV line missing a required field can be skipped and recorded in an error report.
- A transaction that hits a transient database error can be retried.
- A record with an invalid format can be dropped from the pipeline without failing the whole Job.

Spring Batch supports fault tolerance in a chunk step through skip and retry:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

In the example, data errors of type `InvalidOrderException` can be skipped up to a limit of 100 times; transient data access errors can be retried up to the configured limit. You need to choose exceptions and limits that fit the business. Do not skip serious system errors just so the Job can end with a successful status.

The processor can also deliberately filter an item by returning `null`:

```java
@Override
public Order process(OrderInput item) {
    if (item.isCancelled()) {
        return null;
    }
    return convertToOrder(item);
}
```

A filtered item is not passed to the writer and is counted in `filterCount`. This is a deliberate business decision, different from a skipped exception. Both need to be tallied separately so operators understand the number of records that were read but not written.

A Tasklet can catch exceptions itself, retry an operation, or record failing items. However, if you need a standardized skip/retry policy per item, a chunk step provides a clear structure and requires less to be built yourself.

## 5. When you need to restart from a checkpoint on a large dataset

A Job processing many items may be stopped by a lost connection, a timeout, a server restart, or a writer error. Chunk processing works with the `ExecutionContext` and `ItemStream` components to save read/write state and support restart.

For example, a file-reading reader can save its current position. When the Step is restarted, the reader restores the position from the ExecutionContext instead of having to re-read the whole file. Spring Batch readers/writers that support saving state need to be configured and used with the correct stream lifecycle.

Restartability is valuable when:

- The dataset is large and the run time is long.
- You do not want to start over from the beginning after a chunk fails.
- You need to know which part of the data has been committed.
- The data source has a stable order or has a key to continue reading precisely.
- The writer can be safely re-run or has a business key to avoid duplicate writes.

A Tasklet can also restart, but usually has to save the checkpoint itself, for example the next page, the last processed key, or the offset in a file. If the Tasklet performs only a simple operation and can be safely re-run, that is reasonable. If the Tasklet is implementing a checkpoint for each record itself, chunk processing is usually the more natural choice.

Do not take it to mean that a chunk automatically guarantees exactly-once for every side effect. A database transaction can roll back changes in the database participating in the transaction, but it cannot automatically undo an HTTP request, an email, or a file-system operation. The reader, processor, and writer still need to be designed to be safe to re-run.

## 6. When you need to track progress per item

With a chunk step, `StepExecution` records counters such as:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read successfully. |
| `writeCount` | Number of items the writer has written. |
| `filterCount` | Number of items the processor deliberately filtered. |
| `readSkipCount` | Number of items skipped during read. |
| `processSkipCount` | Number of items skipped during processing. |
| `writeSkipCount` | Number of items skipped during write. |
| `commitCount` | Number of transaction commits. |
| `rollbackCount` | Number of transaction rollbacks. |

These counters help track processing speed, the filter/skip ratio, and transaction issues. For example, if `readCount` rises steadily but `writeCount` does not, it may indicate that the processor is filtering many items, the writer is blocked, or write errors are being handled per policy. You need to look at the logs and business results to understand the cause correctly.

A Tasklet can record its own metrics and progress, but it has to determine and update those figures itself. If you need to observe per item, skip/retry, and commit interval, the chunk step has a ready-made metadata model that fits.

## 7. A full example: importing orders with chunk processing

Suppose an application receives an orders file. Each line has an order code, customer code, amount, and creation date. The requirements include:

- Read each line in the file.
- Validate the order code, customer code, and amount.
- Convert the input data into an `Order` entity.
- Write many orders to the database in a transaction per chunk.
- Skip some malformed data lines within an allowed limit.
- Be able to restart on infrastructure errors.

This is a case where chunk processing is a better fit than a Tasklet because the work revolves around an item stream and needs to manage commit, skip, statistics, and checkpoints.

### Configuring the Step

An example configuration for Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
```

The reader, processor, and writer beans are configured separately according to the data source. With Spring Batch 5, the `ItemWriter` API receives a `Chunk` of items; the framework's standard writers handle this interface. When using the example with Spring Batch 4, you need to adjust the writer API per the version.

### The processor validates and converts data

```java
@Component
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                input.createdAt());
    }
}
```

The example uses the `OrderInput` record and the `Order` constructor for illustration. A real data model can be a class or a record depending on the project. The processor does not need to manage the transaction of the whole Job; the chunk transaction is orchestrated by the Step.

### The writer writes in groups

The writer receives the processed items in the chunk. You can use `JdbcBatchItemWriter`, `JpaItemWriter`, or a custom writer that suits the database. An example writer declaration structure:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount, created_at)
                    VALUES
                        (:orderId, :customerId, :amount, :createdAt)
                    """)
            .beanMapped()
            .build();
}
```

The SQL snippet and property names need to match the application's schema and model. If the database has a unique key on `order_id`, you need to determine the behavior on restart or when the same file is sent again: ignore, update, or report an error according to business rules.

## 8. When a Tasklet is still the right choice

Chunk processing is not the default choice for every Step. A Tasklet is usually a better fit if the work is not an item pipeline:

- Calling a stored procedure to update a summary table set-wise.
- Deleting temporary data before an import.
- Checking whether the input file exists.
- Creating a directory or preparing resources.
- Moving a processed file to an archive directory.
- Sending a summary notification after the Job completes.
- Calling a service once to start or close out a business batch.

An example Tasklet calling a database procedure:

```java
@Bean
Step refreshSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("refreshSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("call refresh_daily_summary()");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

If the database can process all the data with a single set-based SQL statement or an efficient stored procedure, a Tasklet can be a better fit than reading row by row through Java just to update a dataset. Choosing a Tasklet or chunk should be based on the capabilities of the target system and the error-tracking requirements, not only on the number of rows.

## 9. Situations to weigh before choosing chunk

### A set-based operation can solve the whole job

If you only need to run an `UPDATE`, `DELETE`, or stored procedure on a dataset and the database can handle it efficiently, a Tasklet is usually simpler. Chunk fits when each item needs its own Java logic, per-item error handling, or batch checkpoints.

### Little data and a simple operation

If the Step only reads a configuration value, checks a condition, and then calls a service, a Tasklet can be clearer. Using a reader/processor/writer just to wrap an operation can create unnecessary configuration.

### Side effects that do not participate in the transaction

If the processor or writer calls an external API, the database transaction cannot roll back the HTTP call. When the chunk rolls back and retries, the external request may be sent again. You need an idempotency key, an outbox, or a reconciliation mechanism. Chunk can still be the right choice for an item pipeline, but it does not by itself solve cross-system consistency.

### A chunk size that is too large

A large chunk size can increase memory, transaction hold time, the number of items to reprocess on rollback, and the load on the target system. Measure performance with real data and choose an appropriate commit interval.

### Items without independent processing boundaries

If an operation needs the entire dataset at once to produce a result, splitting into items can complicate the logic or break the business requirement. A Tasklet or a set-based operation may be more suitable.

## 10. Choosing an appropriate chunk size

After deciding to use chunk processing, you need to choose a commit interval. There is no optimal value for every Job. Chunk size affects memory, transactions, write speed, and the amount of work to recover on error.

Factors to consider:

- **Item size:** large items make a chunk consume more memory.
- **Write cost:** a writer that supports batch insert/update can work efficiently with a sufficiently large group of items.
- **Transaction time:** a large chunk can hold locks longer and increase database contention.
- **Rollback cost:** when a chunk fails, the items in the chunk may have to be re-read/reprocessed per the policy.
- **Target system limits:** the database, API, or service may limit batch size.
- **Checkpoint frequency:** more frequent commits can reduce the amount of work done but not yet committed.

You can start with a moderate value, measure throughput, memory, transaction time, and database load, and then adjust. Do not increase the chunk size just to reduce the number of commits if the transaction becomes too long or the restart risk increases.

## 11. Transactions, retry, and idempotency

In chunk processing, each chunk is usually performed in the Step's transaction. When the writer hits an error that causes the transaction to roll back, the changes in the current transaction are undone if the resource participates in that transaction. Chunks committed earlier are retained.

However, some operations can be performed again on rollback/retry. The reader can re-read items; the processor can be called again; the writer can try to write again. Therefore:

- The processor should avoid side effects that cannot be undone.
- The writer should use a unique key or an appropriate upsert mechanism when the same item may be written again.
- External APIs should support an idempotency key if an item can trigger a request multiple times.
- Do not assume emails, HTTP calls, or file operations are rolled back along with the database transaction.
- Record failing items and skip results so they can be reconciled.

If you need to publish an event together with the database transaction, consider a transactional outbox. The writer writes the data and the outbox in the same transaction; another process publishes events from the outbox with a safe retry mechanism.

## 12. Combining Tasklet and chunk in the same Job

A Job does not need to use only one kind of Step. You can use a Tasklet for preparation and wrap-up operations, while chunk processing handles the per-item processing:

```text
Job: import-orders
  |
  v
Tasklet Step: check the file and prepare staging
  |
  v
Chunk Step: read, validate, transform, and write orders
  |
  v
Tasklet Step: save the report and archive the file
```

For example:

- The first Tasklet checks the input file, creates a batch record, and prepares the staging table.
- The Chunk Step reads each line, validates, transforms, and writes the data.
- The last Tasklet creates a summary report, moves the processed file, and updates the batch status.

This organization keeps each Step with a clear responsibility. If the data-processing portion needs group commit, skip/retry, and checkpoints, put it in a chunk step. If an operation only needs to run once, such as preparing or archiving, a Tasklet is usually more suitable.

## 13. Decision process

When designing a Step, you can use the following questions:

1. Does the work process many items from a data source? If so, consider chunk processing.
2. Does each item need to be read, validated/transformed, and written through the same pipeline? If so, chunk usually fits.
3. Do you need to commit in groups and limit transactions? If so, chunk provides a commit interval.
4. Do you need to skip/retry some failing items while still processing the remaining items? If so, chunk has item-level fault-tolerance mechanisms.
5. Do you need checkpoints and progress tracking on a large dataset? If so, chunk together with ItemStream/ExecutionContext is the natural choice.
6. Is the work just a single independent operation or a set-based SQL statement? If so, a Tasklet is usually more suitable.
7. Does a Step have multiple phases of different natures? If so, split into separate Steps and combine Tasklet with chunk processing.

| Need | Usually suitable choice |
|---|---|
| Read a large file, validate each line, and save to the database | Chunk processing |
| Convert each record from a staging table to a target table | Chunk processing |
| Skip malformed records and retry transient write errors | Chunk processing |
| Need to commit each group of items and restart from a checkpoint | Chunk processing |
| Compute separately for each transaction and then write the results | Chunk processing |
| Call a stored procedure that aggregates all the data | Tasklet |
| Clean a temporary table or check a condition before the Job | Tasklet |
| Move a file after a successful import | Tasklet |

## Conclusion

Chunk processing is a better fit than a Tasklet when the work has a stream of many items to read, process, and write in groups; needs a clear transaction boundary, item-level skip/retry, progress statistics, or restart via checkpoints. A Tasklet suits an independent action or system-level operation that does not need an item pipeline. A Job can combine the two kinds of Step so that the data-processing portion takes advantage of chunk processing, while the preparation and completion operations are organized with a Tasklet.
