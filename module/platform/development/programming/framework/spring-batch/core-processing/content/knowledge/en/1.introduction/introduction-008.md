# When to Use Chunk Processing and When to Use a Tasklet

In Spring Batch, a `Step` is the main execution unit of a Job. Each Step needs a way to organize its work: it can process data group by group using **chunk-oriented processing**, or it can perform a single task using a **Tasklet**. Both approaches can run in a Job, use transactions, and have their execution state managed by Spring Batch, but they suit two different kinds of work.

The most important decision is to look at the nature of the work:

- If the work is to read many records, validate or transform each record, and then write the results in batches, prefer chunk processing.
- If the work is an operation with independent meaning such as preparing data, calling a database procedure, cleaning up a table, or moving a file, prefer a Tasklet.

Do not choose based only on the number of lines of code or the name of the operation. Consider the unit of work, the transaction boundary, how errors are handled, and the rerun requirements when the Job is interrupted.

## 1. Two Processing Models in Spring Batch

### Chunk-Oriented Processing

Chunk processing divides the input data into groups of a defined size. For each group, Spring Batch performs a read, process, and write cycle:

1. The `ItemReader` reads items one at a time from the data source.
2. The `ItemProcessor` processes an item, for example validating, normalizing, or converting its data type.
3. The `ItemWriter` writes the processed items as a group.
4. When the group is complete, the chunk's transaction is committed. If an error causes the transaction to roll back, the changes belonging to that transaction are undone.
5. The Step continues with the next group until the reader reports that the data is exhausted.

The chunk size is usually configured with `chunk(n, transactionManager)`. The value `n` is the commit interval: the number of items gathered for one round of processing and commit. For example, `chunk(500, transactionManager)` asks Spring Batch to process data in groups of about 500 items before each commit. The last group can be smaller if the data source is exhausted.

```text
Data source
     |
     v
  ItemReader -- reads items
     |
     v
 ItemProcessor -- processes each item
     |
     v
  ItemWriter -- writes the whole chunk
     |
     v
 Commit transaction
     |
     +------> Next chunk
```

If the processor returns `null`, that item is filtered out and is not passed to the writer. This is a way to deliberately drop a record; it differs from throwing an exception to report an error. When the reader has no more items, it returns `null` to end the reading phase.

The strength of chunk processing is that Spring Batch already provides the structure for item-by-item processing, batch commits, state saving, and skip/retry configuration. Developers focus on the read, process, and write logic instead of writing their own loop that orchestrates all the records.

### Tasklet

A Tasklet suits a task described as a single unit of work. Spring Batch calls the Tasklet's `execute` method and receives a `RepeatStatus` to know whether it needs to be called again:

- `RepeatStatus.FINISHED`: the task is complete; the Step can end normally.
- `RepeatStatus.CONTINUABLE`: the Tasklet still has work to do; Spring Batch will call the Tasklet again.

Each Tasklet call is executed within the transaction configured by the Step. If the Tasklet performs just one operation, it usually returns `FINISHED`. If a task needs to be divided into multiple rounds, the Tasklet can return `CONTINUABLE` and save its progress so that it can continue later.

For example, a Step can call a service that cleans up expired records:

```java
@Bean
Step cleanupExpiredDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupService cleanupService) {

    return new StepBuilder("cleanupExpiredDataStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                cleanupService.deleteExpiredRecords();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

A Tasklet does not require an `ItemReader`, `ItemProcessor`, or `ItemWriter`. The task's logic lives in `execute` or is delegated to a service. This makes a Tasklet suitable for work that cannot naturally be expressed as a stream of items.

## 2. When Should You Use Chunk Processing?

Choose chunk processing when the data can be viewed as a collection of items and each item needs to go through a relatively consistent process.

### Processing Many Records by the Same Rule

Typical examples include:

- Reading orders from a CSV, validating the data, and saving them to the database.
- Reading transactions from a staging table, calculating fees, and writing the results to a business table.
- Synchronizing a customer list from a source system to a target system.
- Reading HR data, normalizing department codes, and then updating the system.
- Calculating balances or aggregating data for each account.

In these cases, each record can logically be read, processed, and written separately, while many records are committed together to reduce transaction cost and I/O operations.

### Needing Group-Level Transaction Control

Chunks are the right choice when you want a group of records to succeed or roll back together within the chunk's transaction. For example, with a commit interval of 100, if a write error occurs before the commit, the changes belonging to the current transaction can be rolled back. Chunks committed earlier are kept.

This boundary directly matters to business requirements. If the system accepts that 100 records are processed as one commit unit, chunk processing expresses that requirement clearly.

### Needing Item-Level Skip or Retry

Chunk processing provides fault tolerance mechanisms at the item level. Depending on the error type and configuration, the Step can skip some invalid items or retry operations that hit transient errors.

Example configuration for illustration:

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

In this example, data errors of type `InvalidOrderException` can be skipped within the set limit; transient data access errors can be retried. You need to choose the exception types, limits, and rollback policy according to the application's real behavior. Do not skip a system error or an important data error just to give the Job a successful status.

### Needing Restartability over a Large Data Set

Readers and writers that implement `ItemStream` can save and restore state through the `ExecutionContext`. When configured correctly and when the state can be restored, Spring Batch can continue processing from the appropriate position after the Job is interrupted, instead of you having to build the whole mechanism for marking each record yourself.

Restartability does not automatically solve every case. The reader must support saving state; the source data needs a stable way to determine the read position; write operations need to be designed to avoid creating duplicate data on rerun. For example, reading in a stable order with a clear key or cursor is usually safer than reading a data set with no defined order.

### Example of a Step That Processes Orders in Chunks

The code below shows the structure of a Step in Spring Batch 5.x. The reader, processor, and writer beans are configured separately according to the application's data source and model:

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
            .build();
}
```

The data flow can be understood as follows:

| Component | Responsibility in the example |
|---|---|
| `ItemReader<OrderInput>` | Reads the input order data, for example from a CSV or a staging table. |
| `ItemProcessor<OrderInput, Order>` | Validates and converts `OrderInput` into an `Order` object that fits the business. |
| `ItemWriter<Order>` | Writes a group of processed `Order` objects to the database or another data destination. |
| `chunk(500, transactionManager)` | Sets the commit interval to 500 items and uses the specified transaction manager. |

This is a suitable model if each order needs to be processed independently, can produce its own data errors, and needs to be written in groups.

## 3. When Should You Use a Tasklet?

Choose a Tasklet when the work is naturally described as a single action or a short process, without needing a read-process-write pipeline for each item.

### Preparing or Finalizing Data

Examples:

- Delete temporary data before starting an import.
- Create a staging table or prepare a data structure for a run.
- Update the status of a processing batch.
- Close a file, move a processed file to an archive directory, or create the final report file.
- Clean up resources after the data-processing Steps have completed.

These operations usually have inputs and outputs at the task level, rather than thousands of items that need to be processed individually.

### Invoking a System-Level or Database-Level Operation

A Tasklet is usually suitable to:

- Call a stored procedure that performs a business operation already encapsulated in the database.
- Execute a set-based SQL statement to update or delete a set of records.
- Call a service to initialize or close out a business batch.
- Check pre-processing conditions before allowing the next Step to run.

For example, if a stored procedure processes the whole data set and the application only needs to call it once, a Tasklet expresses the work more clearly than creating a fake reader and writer just to wrap a single call.

However, an SQL statement that affects millions of rows can still create a long transaction, lock a lot of data, or put pressure on the database. Using a Tasklet does not make that operation lighter on its own. If you need to divide the data into smaller pieces, control errors per record, or checkpoint per batch, consider chunk processing or an appropriate partitioning mechanism.

### Running a Command or a File Operation

A Tasklet also suits work such as checking whether a file exists, extracting, renaming, moving, or creating a completion marker file. These operations do not necessarily have an item structure to pass through an `ItemProcessor` and an `ItemWriter`.

When working with a file system, you need to account for the case where the operation has completed but the Job is stopped before the Step's state is saved. You can design a stable destination file name, check for existence conditions, and make the operation safe to rerun.

### Example of a Tasklet That Calls a Stored Procedure

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

This is an illustrative example of a database operation that is called once. The syntax for calling a stored procedure depends on the database management system and how the application configures JDBC. If the stored procedure manages its own transactions or performs operations outside the current transaction, you need to understand clearly the actual transaction boundary.

## 4. Comparing Chunk Processing and Tasklet

| Criterion | Chunk processing | Tasklet |
|---|---|---|
| Unit of work | A group of items that are read, processed, and written. | A task performed by the `execute` method. |
| Main structure | `ItemReader`, `ItemProcessor`, `ItemWriter`. | `Tasklet.execute`. |
| How it repeats | Spring Batch iterates over items and chunks until the data is exhausted. | Spring Batch calls the Tasklet again when the result is `CONTINUABLE`. |
| Transaction boundary | Normally one transaction per chunk. | One transaction per Tasklet call. |
| Per-record errors | Has built-in skip/retry mechanisms at the item level in a chunk step. | The application designs error handling inside the task itself. |
| State on restart | Readers/Writers that support `ItemStream` can store state in the `ExecutionContext`. | The task saves the necessary checkpoint itself into the `ExecutionContext` or another durable mechanism. |
| Typical cases | Import, export, synchronization, transformation, and bulk processing of records. | Data cleanup, calling stored procedures, preparing resources, file operations, or calling a service. |

The core difference is that chunk processing already provides an item-processing model along with related mechanisms. With a Tasklet, the application is responsible for organizing the logic inside the task. A Tasklet can still repeat multiple times, but that repetition does not by itself provide the full set of read, process, write, and item-level fault tolerance features that a chunk step does.

## 5. How to Choose in Easily Confused Situations

### A Single SQL Statement That Updates Many Rows

If the requirement is only to call a set-based SQL statement or a stored procedure already designed to process a data set, a Tasklet is usually a reasonable choice. The database itself performs the set-based update and the Step manages that call as a single task.

If you need to read row by row, apply different Java rules to each row, write the results, and handle errors separately for each record, chunk processing is more suitable.

### Processing Large Files

If you need to read each line of a file, validate its content, and write each record to the database, use chunk processing. If you only need to move or rename a file after another Step completes, use a Tasklet.

If you need to extract a very large file, determine whether the extraction can complete as an independent task or needs to be divided into units that can be resumed. A Tasklet suits a single extraction that can be safely rerun; if you need to monitor and recover in parts, you need to design a dedicated checkpoint or an item-based processing model.

### Calling an API for Each Record

If each item needs to call an API, transform the response, and save the result, chunk processing usually helps organize the item flow, limit the amount processed per chunk, and combine with a retry policy. Pay attention to rate limits, timeouts, and the API's safety under repetition.

If you only call an API once to start or close out a processing batch, a Tasklet is usually suitable. Because an HTTP call is not inside an ordinary database transaction, a database rollback cannot undo a request that an external system has already accepted. Use an idempotency key, business state, or a reconciliation mechanism when you need to guarantee safe reruns.

### A Step That Needs Multiple Phases

You do not need to force every phase into the same kind of Step. A Job can combine Tasklets and chunk processing in the right business sequence:

```text
Job: import-orders
  |
  v
Tasklet Step: validate and prepare the data source
  |
  v
Chunk Step: read, validate, transform, and save each order
  |
  v
Tasklet Step: save the report, archive the input file, and clean up resources
```

For example, the first Tasklet can check the input file and create the staging table; the chunk Step processes each order; the final Tasklet moves the processed file to an archive directory. This combination gives each Step a clear responsibility and fits the nature of the work.

## 6. Choosing the Commit Interval for Chunk Processing

Once you have chosen chunk processing, you need to choose an appropriate chunk size. There is no single optimal number for every application. A chunk that is too small can increase the number of commits and the cost of communicating with the database. A chunk that is too large can increase memory usage, transaction hold time, and the amount of work that must be redone on rollback.

Factors to consider:

- **Item size:** large items or items that contain a lot of data can make a large chunk consume a lot of memory.
- **Read and write cost:** a writer that supports batch insert/update can be efficient with larger groups of items than with writing row by row.
- **Transaction time:** a long transaction can hold locks for a long time, increase resource contention, and affect other transactions.
- **Rollback and retry cost:** a large chunk increases the number of items that may have to be reprocessed when a transaction fails.
- **Limits of the target system:** the database, API, or write service may have limits on batch size and intake rate.
- **Business requirements:** if you need to commit frequently to reduce the amount of work that could be lost on error, choose a smaller commit interval.

You can start with a moderate value, measure run time, memory, transaction time, and the load on the target system, and then adjust using real data. Do not increase the chunk size just to reduce the number of commits if that makes transactions too long or increases the risk on rerun.

## 7. Transactions and External Side Effects

Both chunk steps and Tasklet steps can run in a transaction configured with a `PlatformTransactionManager`. However, a transaction only guarantees rollback for the resources that participate in that transaction. For example, a JDBC transaction can roll back changes in the database managed by the corresponding transaction manager; it does not automatically restore a file that has been renamed or an email that has been sent.

Therefore, when a Step combines multiple kinds of side effects, you need to design the order and rerunnability carefully. Some useful principles:

- Prefer idempotent operations: rerunning the same request does not produce a wrong result or duplicate data.
- Use a business key or a unique key to prevent duplicate writes when the Job is restarted.
- Record the processing state clearly so that you can reconcile after an error.
- For events that need to be emitted along with a database change, consider a transactional outbox or an appropriate coordination mechanism.
- Do not assume that a transaction rollback will undo every operation that has called an external system.

In chunk processing, if a writer both writes to the database and calls an external API, the database transaction cannot roll back the API call. If the chunk rolls back and Spring Batch retries, the API may be called multiple times. You may need to split event emission into a separate Step, use an outbox, or ensure that the API that receives the request is idempotent.

## 8. Repeating Tasklets and Checkpoints

A Tasklet can return `CONTINUABLE` so that Spring Batch calls `execute` again. This is useful when a task consists of a bounded number of rounds of work, for example processing data page by page or invoking an operation segment by segment. However, a Tasklet does not know on its own which item it has processed up to. If you need an accurate restart, the application must save a checkpoint and design each round of processing to be safely rerunnable.

An example skeleton of the idea for a Tasklet that processes page by page:

```java
.tasklet((contribution, chunkContext) -> {
    ExecutionContext executionContext = contribution
            .getStepExecution()
            .getExecutionContext();

    int page = executionContext.getInt("currentPage", 0);
    boolean hasMore = migrationService.processPage(page);

    if (hasMore) {
        executionContext.putInt("currentPage", page + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
}, transactionManager)
```

This is an illustrative skeleton; you need to add error handling, termination conditions, and a stable paging mechanism suited to the real data. The checkpoint must be updated consistently with the portion of work that has completed. If the task changes data outside the current transaction, you need an additional mechanism to prevent duplicate execution when a round is rerun.

If the work is really processing a large stream of items with item-level skip/retry requirements, a stateful reader/writer, and a commit interval, use chunk processing instead of rebuilding these mechanisms yourself inside a Tasklet.

## 9. Common Design Mistakes

### Using a Tasklet for a Loop over Millions of Records

A Tasklet can contain a loop that reads and writes data, but then the application has to manage paging, checkpoints, transactions, retry, skip, logging, and recovery after errors by itself. If the business is processing item by item, chunk processing is usually simpler and easier to operate.

### Using a Chunk Just to Call a Single Operation

If a Step only calls a stored procedure or performs a preparation operation, creating a reader that returns exactly one item and a writer that calls a service can make the structure hard to understand. A Tasklet expresses the meaning of the task more directly.

### Thinking Chunk Size Is the Number of Records That Are Certain to Be Written

The commit interval describes the number of items in the chunk cycle. A processor can filter items by returning `null`, and a skip policy can also make the number of items written smaller than the number read. Therefore, the number of items the writer receives can differ from the commit interval.

### Assuming Every Error Can Be Retried Safely

Retry only suits errors that are likely to be transient and operations that can be safely redone. Retrying a non-idempotent operation can create duplicate records or repeat side effects. You need to determine the exception types, the retry limit, and the transaction behavior before enabling retry.

### Assuming a Tasklet Always Runs Only Once

A Tasklet can be called multiple times if it returns `CONTINUABLE`. In that case you need to manage progress and state. Only `FINISHED` is the signal that ends the Tasklet loop.

### Ignoring State and Rerunnability

A Job can fail after part of the work has already been performed. Whether you use a chunk or a Tasklet, you need to determine what happens on rerun: which data has been committed, which operations can be repeated, where the checkpoint is, and how reconciliation can be done.

## 10. Decision Process

You can use the following questions when designing a Step:

1. **Does the work have to process many items through the same pipeline?** If so, chunk processing is usually a suitable starting point.
2. **Does each item need to be read, validated/transformed, and written separately?** If so, use `ItemReader`, `ItemProcessor`, and `ItemWriter`.
3. **Do you need group commits and item-level skip/retry handling?** If so, chunk processing provides the appropriate mechanisms.
4. **Is the work just an independent operation or a system-level call with no item pipeline?** If so, use a Tasklet.
5. **Can the task be rerun after it has already created side effects?** If so, design idempotency, checkpoints, or reconciliation before deploying.
6. **Is a Step doing several things of different natures?** If so, split it into multiple Steps and combine Tasklets with chunk processing in the same Job.

| Main need | Choice that usually fits |
|---|---|
| Import thousands of CSV rows, validate each row, and write to the database | Chunk processing |
| Read a staging table, transform each record, and update the target table | Chunk processing |
| Skip malformed records and retry transient write errors | Chunk processing |
| Call a stored procedure to refresh a summary table | Tasklet |
| Delete temporary data before an import | Tasklet |
| Move the input file after a successful import | Tasklet |
| Call an API once to start a processing batch | Tasklet |
| Call an API for each record and store the response | Chunk processing, with an appropriate retry/idempotency design |

## Conclusion

Chunk processing suits a data flow made up of many items that need to be read, processed, and written in groups, especially when you need a commit interval, restart, and item-level fault tolerance. A Tasklet suits an independent task such as preparing data, calling a stored procedure, cleaning up, or file operations. A Job can combine both: use a Tasklet for orchestration steps or system-level operations, and use chunk processing for record-by-record data processing.
