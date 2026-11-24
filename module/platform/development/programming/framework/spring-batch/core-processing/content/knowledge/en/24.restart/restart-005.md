# Restarting with reader state

In Spring Batch, restarting allows a Job to resume after a previous run was stopped or failed. To resume at the exact position, the reader needs to save and restore its reading state. This state is typically stored in the **Step ExecutionContext** through the **ItemStream** contract.

A restartable reader does not just know how to fetch the next item. It must also know how to save its current position before a chunk commits and restore that position when the Step runs again.

For example, a Job reading a 100,000-line file with a chunk size of 500. If the Job fails after 20 chunks have committed, a restart should resume from the checkpoint of the most recently committed chunk. The reader should neither re-read the entire file from the beginning nor skip uncommitted lines.

To achieve that, three parts must work together properly:

- The reader manages its read position and implements ItemStream.
- Spring Batch calls `open`, `update`, and `close` along the Step lifecycle.
- JobRepository persists ExecutionContext so a restart can restore the checkpoint.

## 1. What is reader state?

Reader state is the information required to determine the next item to be read. Depending on the data source, state can be:

- Number of lines read in a file.
- Byte position or record offset in a resource.
- Current page and number of items read in the page.
- Last processed ID in a database.
- Cursor position or a continuation key.
- Partition name and data range being processed.

Example of a file reader that has read up to line 2,000:

~~~text
File: customers.csv

Lines 1 - 2.000 -> already belong to committed chunks
Line 2.001      -> next item on restart
Line 2.002 ...
~~~

If the committed checkpoint saved position 2,000, the reader can reopen the file and resume from line 2,001.

Reader state is not all the data that has been read. Usually, only a small position or key sufficient to reconstruct the next item needs to be saved.

## 2. ItemStream provides the lifecycle for readers

Spring Batch uses the `ItemStream` interface to manage the state and resources of processing components.

Basic contract:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

A reader can implement `ItemStreamReader`, which combines `ItemReader` and `ItemStream`:

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

The three methods have distinct roles:

| Method | Role |
|---|---|
| `open(context)` | Initialize the reader and restore saved state |
| `update(context)` | Write current state into ExecutionContext |
| `close()` | Close resources and release handles |

Spring Batch calls `open` when the Step starts, calls `update` at checkpoints before committing chunks, and calls `close` when the Step finishes. For readers that support restarting, this is where the reading position is saved and restored.

You do not need to call these three methods manually from a processor or writer. When the reader is properly registered with the Step, Spring Batch manages the lifecycle.

## 3. Where are checkpoints stored?

Reader checkpoints are normally stored in the **StepExecution ExecutionContext**. This is the context dedicated to a single StepExecution, suitable for read state belonging only to that Step.

Distinguish the types of data:

| Data | Appropriate storage |
|---|---|
| Input file path | JobParameters |
| Business date or import batch code | JobParameters |
| Last line read/committed | Step ExecutionContext |
| Last database reader ID | Step ExecutionContext |
| Intermediate result needed by a later Step | Job ExecutionContext |
| Entire file contents | File or storage, do not store in context |

JobParameters define the run request, and identifying parameters determine the JobInstance. ExecutionContext stores state that changes during execution. Reader state is an execution checkpoint, so it typically belongs in the Step context.

ExecutionContext is stored in JobRepository. To restart after an application or JVM restart, JobRepository must persist metadata durably, typically via a database-backed repository. An in-memory-only repository cannot guarantee keeping checkpoints across process restarts.

## 4. Checkpoint lifecycle of a chunk

In a chunk-oriented Step, reader state is updated at commit boundaries.

~~~text
Step starts
    |
    v
reader.open(savedContext)
    |
    v
Read and process chunk
    |
    v
reader.update(executionContext)
    |
    v
Save ExecutionContext and metadata
    |
    v
Transaction commit
    |
    v
Chunk confirmed
    |
    v
Next chunk
~~~

Suppose chunk size equals 500:

| Chunk | Items | Status |
|---|---|---|
| 1 | 1–500 | Commit |
| 2 | 501–1.000 | Commit |
| 3 | 1.001–1.500 | Commit |
| 4 | 1.501–2.000 | Commit |
| 5 | 2.001–2.500 | Failed during processing |

If the Job fails in chunk 5 before committing, the latest saved checkpoint still corresponds to chunk 4. On restart, the reader restores the position after item 2,000 and re-reads the uncommitted chunk portion.

The core point is that a checkpoint only represents successfully saved progress. Calling `read()` on the reader or calling the writer does not mean a new checkpoint has committed.

Atomicity between business data and metadata depends on how the transaction manager, JobRepository, and resources are configured. With independent resources, do not assume a single commit covers everything.

## 5. Job restart uses the old JobInstance

Normal restarts resume the same JobInstance. Spring Batch identifies a JobInstance by Job name and identifying JobParameters.

~~~text
JobParameters
  inputFile=customers.csv
  businessDate=2026-11-15
        |
        v
JobInstance: customerImportJob
        |
        +--> JobExecution 1: FAILED
        |       |
        |       +--> StepExecution
        |               checkpoint: line 2000
        |
        +--> JobExecution 2: RESTART
                |
                +--> Same JobInstance
                |
                +--> Reader opens with checkpoint line 2000
                        |
                        v
                  Reads from line 2001
~~~

On restart:

1. JobLauncher receives the JobParameters of the JobInstance to resume.
2. JobRepository looks up the corresponding JobInstance.
3. Spring Batch creates a new JobExecution for the next attempt.
4. The restarted Step uses the saved metadata and ExecutionContext.
5. The reader reopens with the most recently committed checkpoint.

If an identifying parameter changes—for example, changing `inputFile` to another file—the request may create a new JobInstance and not use the old instance's checkpoint.

If only a non-identifying parameter changes, JobInstance identity may remain unchanged. However, non-identifying parameters must still remain stable if they alter how data is read or processed.

## 6. Enabling saveState on built-in readers

Standard Spring Batch readers typically support state persistence. Give the reader a stable name and enable `saveState` when restartability is needed.

Example with FlatFileItemReader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Key points:

- `name("customerReader")` provides a stable name for the reader and state keys.
- `resource` obtains the file from JobParameters.
- `saveState(true)` tells the reader to save read state.
- `@StepScope` allows resolving the resource when the Step actually starts.
- The reader is registered with the Step so Spring Batch manages the ItemStream lifecycle.

Do not arbitrarily rename a reader while old JobInstances still need restarting. The reader name is used to distinguish state in ExecutionContext; renaming it can prevent the reader from finding old keys and cause it to start from the default position.

## 7. What does saveState(false) mean?

Some readers allow disabling state persistence:

~~~java
.saveState(false)
~~~

With `saveState(false)`, the reader does not save a checkpoint to restore its reading position. This can be appropriate when:

- The reader has no state that needs restoring.
- The Step is designed to run again from the beginning.
- The data source can be re-read and processed idempotently.
- A parallel component does not support sharing reader state.
- The application manages checkpoints via another mechanism.

If a reader does not save state and the Job restarts, the reader may start over from the beginning. That can cause already-committed data to be read again. The writer must prevent duplicate writes, or the application must have a mechanism to identify already-processed data.

Do not disable `saveState` just to avoid errors during parallel execution without evaluating the restart impact. Disabling state is a decision about Job semantics, not merely a performance optimization.

## 8. Reader names must be stable and unique within a Step

Built-in readers typically use their name to build keys in ExecutionContext. Therefore:

- Choose clear and stable names.
- Do not reuse the same name for multiple readers holding different state in the same scope.
- Do not generate random names on each launch.
- When renaming a bean or reader, evaluate compatibility with JobInstances waiting to restart.

For example:

~~~java
.name("customerFileReader")
~~~

This name distinguishes the file reader's state. If a Step has an auxiliary reader or another delegate reader that also saves state, each component needs its own key so they do not overwrite each other's checkpoints.

Renaming a reader can prevent it from finding old state. In that situation, the reader might read from the beginning or initialize fresh state depending on the implementation. Treat configuration and reader name changes as changes affecting restartability.

## 9. Example custom reader saving checkpoints by ID

Custom readers must implement `ItemStreamReader` and define how state is saved and restored.

Example reader reading customers sequentially by ascending ID:

~~~java
public class CustomerReader
        implements ItemStreamReader<Customer> {

    private static final String LAST_ID_KEY =
            "customerReader.lastId";

    private final CustomerRepository repository;

    private long lastId;
    private boolean opened;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong(
                LAST_ID_KEY,
                Long.MIN_VALUE);
        opened = true;
    }

    @Override
    public Customer read() {
        if (!opened) {
            throw new IllegalStateException(
                    "Reader has not been opened");
        }

        Customer customer =
                repository.findFirstAfterId(lastId);

        if (customer == null) {
            return null;
        }

        lastId = customer.getId();
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastId);
    }

    @Override
    public void close() {
        opened = false;
    }
}
~~~

The repository must query in a stable order, for example:

~~~sql
SELECT id, name, email
FROM customer
WHERE id > :lastId
ORDER BY id
FETCH FIRST 1 ROW ONLY
~~~

Row-limiting syntax varies by database. The idea is that on each read, the reader fetches the first record with an ID greater than `lastId`.

In this example, the ID must have a stable and sufficiently unique order to serve as a checkpoint. If IDs can be negative, the default `Long.MIN_VALUE` is only appropriate if every valid ID is greater than that value. If using another key, design a dedicated sentinel or initialization state.

In real-world applications, querying one item at a time can be inefficient. You can use a built-in cursor or paging reader, or a custom reader that fetches in batches while still saving accurate checkpoints.

## 10. Readers must update state at the right time

Custom readers usually update an internal field whenever returning an item. The `update` method writes the current position into ExecutionContext.

Crucially, the saved position must accurately represent the next item after the committed checkpoint.

Example reader reading IDs 100, 101, 102 in one chunk:

~~~text
read() -> 100
read() -> 101
read() -> 102
        |
        v
update(context)
        |
        v
context["lastId"] = 102
        |
        v
Commit chunk
~~~

If the transaction commits successfully, checkpoint 102 is persisted. On restart, the reader continues with IDs greater than 102.

If the chunk rolls back before the checkpoint is saved, JobRepository still retains the checkpoint from the previously committed chunk. The reader must restore from that context when the Step restarts.

Do not save checkpoints immediately after every read to an independent store if the writer and checkpoint lack the required consistency. If the reader advances while output has not committed, a restart may skip unwritten items.

## 11. FlatFileItemReader restoring file position

FlatFileItemReader is the standard reader for text files. When `saveState` is enabled, the reader can save its read position to resume on restart.

For example:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") Resource resource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(resource)
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

On the first run, the reader opens the file and reads sequentially. At checkpoints, the reader saves the required state. When restarting the same JobInstance with the same file source, the reader can restore the corresponding position.

An important condition is that the source must keep its exact content and order. If the file is replaced or edited while the Job waits to restart, the old line position may point to a different record.

For example, the old file had 10,000 lines, but a new file was overwritten with different content. A checkpoint at line 5,000 no longer guarantees the reader resumes at the same business record processed previously.

## 12. Ensuring input files do not change between restarts

Storing just a file path is not enough to identify source contents. A file with the same name can be replaced.

Ways to manage sources:

- Place files in an immutable archive directory keyed by batch ID.
- Use unique filenames by date or import ID.
- Store a file checksum or version.
- Record size, creation time, and fingerprint to verify the source.
- Prevent other systems from overwriting the file while the Job is running or awaiting restart.

You can pass the checksum as an identifying JobParameter if the checksum identifies an independent unit of input:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", archivedPath, true)
        .addString("fileChecksum", checksum, true)
        .toJobParameters();
~~~

If the file changes while the Job still uses the same identifying parameters, Spring Batch may treat it as the same JobInstance. The reader will restore the old position on new content, leading to incorrect results.

Verify the source fingerprint when the Step reopens. If the fingerprint differs, fail explicitly and require creating a new JobInstance or restoring the original file.

## 13. JdbcPagingItemReader and page-based checkpoints

JdbcPagingItemReader reads data page by page instead of loading all results into memory.

Conceptual configuration example:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Customer> customerPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("customerPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
~~~

The reader requires a stable order. The sort key should be a unique key or a set of keys that produces a unique order. If the sort key is not unique, records with identical values may be duplicated or skipped when the reader switches pages and restarts.

Page size and chunk size are two separate settings:

| Setting | Controls |
|---|---|
| `pageSize` | Number of items the reader fetches in a single page query |
| `chunk size` | Number of items in a Step transaction unit |
| `saveState` | Whether the reader saves checkpoints |

Page size can equal or differ from chunk size. Measure memory, query count, and database performance. Regardless of page size, the reader must still save sufficient state to restore the exact position after restart.

## 14. JdbcCursorItemReader and restarts

JdbcCursorItemReader reads results through a cursor. When `saveState` is enabled, the reader can save its read position to reopen and continue after the checkpoint.

For example:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, name, email
                FROM customer
                ORDER BY id
                """)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
~~~

On restart, the cursor usually must be reopened; old connections and ResultSets cannot be stored as live objects across process restarts. The reader uses the checkpoint to reposition within the query results.

Points to watch:

- The query must have a stable `ORDER BY`.
- The dataset needs appropriate consistency between the run and the restart.
- Drivers/databases can differ in fetch and cursor behavior.
- Cursors and connections may remain held for the duration of the Step.
- With mutable data, a row position in the result set may no longer correspond to the same record.

If source data can change, keyset paging based on a unique key or a snapshot/watermark may be easier to control than relying solely on row position.

## 15. Database data changing while the Job is stopped

Suppose the reader committed up to ID 5,000. The Job stops. Before restarting, another system:

- Deletes record ID 4,500.
- Inserts record ID 4,800.
- Changes the order or values used in the query.
- Updates statuses so records no longer match the WHERE clause.

A checkpoint only indicates the position the reader saved. It does not automatically snapshot the entire table.

For consistent restarts, define the Job's dataset explicitly:

- Capture an upper bound or watermark at the start.
- Filter by an immutable business date/period.
- Use snapshot isolation if consistent reads are required and supported by the database.
- Use a staging table or snapshot ID.
- Use a unique sort key and stable continuation conditions.

For example, a reader can filter for IDs greater than `lastId` and not exceeding a fixed `maxId`:

~~~sql
SELECT id, status
FROM orders
WHERE id > :lastId
  AND id <= :upperBound
ORDER BY id
~~~

`upperBound` should remain stable across restarts, such as in JobParameters or Job ExecutionContext depending on its semantics. Do not recompute `upperBound` from fresh data if you intend to resume the same dataset.

## 16. Reader state must be registered with the Step

Spring Batch needs to know the reader is an ItemStream in order to invoke `open`, `update`, and `close`.

When a reader is passed directly to the builder via `reader(...)`, ItemStream components are usually registered automatically by the Step. With delegates or nested streams inside custom composites, ensure the delegates are registered as well.

Configuration example:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer,
        ItemStream auditStream) {

    return new StepBuilder("importStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(auditStream)
            .build();
}
~~~

If a custom delegate implements ItemStream without being registered, Spring Batch may skip calling its lifecycle methods. Checkpoints will then fail to update or resources will not open/close properly.

With composite readers/writers, check whether the implementation manages delegate streams itself or requires registering each stream individually. Avoid registering the same stream twice if the framework or wrapper already manages it.

## 17. Reader state and StepScope

In partitioning, each worker has its own StepExecution and ExecutionContext. Readers need to receive the checkpoint and partition parameters of their respective worker.

For example:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return buildOrderReader(dataSource, fromId, toId);
}
~~~

StepScope creates a reader scoped to the StepExecution, giving each partition its own state. A reader should not be a mutable singleton shared across multiple workers if its state changes per item.

When restarting partitions:

- Partition names and data ranges must stay stable.
- Workers reuse their corresponding StepExecution contexts.
- Readers reopen with that partition's checkpoint.
- Already-completed partitions are normally skipped under Step restart semantics.

Do not share a stateful reader across multiple threads unless the reader is designed to be thread-safe. If concurrent processing is needed, use partitioning with separate readers per worker or a reader mechanism explicitly designed for concurrency.

## 18. Stateless readers and restarting from the beginning

Not every reader needs a checkpoint. A reader scanning a small configuration list, an immutable source, or regenerable data can be designed to run from the beginning again.

However, restarting from the beginning may re-read items already written in previously committed chunks. If the writer is not idempotent, duplicate data can occur.

Options:

- Enable `saveState` and restore checkpoints.
- Use an upsert writer keyed by business key.
- Record processing state separately in the database.
- Partition data or use stable watermarks.
- Design the Step to re-run completely idempotently.

Do not confuse "reader does not save state" with "Job cannot restart." The Job can still restart, but the reader may start from the beginning and the application must ensure correct outcomes itself.

## 19. JobRepository must persist metadata durably

Reader state is only useful if ExecutionContext is saved and read back.

A database-backed JobRepository persists:

- JobInstance and JobExecution.
- StepExecution.
- Job ExecutionContext.
- Step ExecutionContext.
- Execution counters and statuses.

If the application uses an in-memory repository, checkpoints can disappear when the process stops. You cannot rely on old metadata to restart across fresh application startups.

Also check transaction configuration between JobRepository and business data. If checkpoints and output reside in two independent transactional resources, one side may commit while the other does not. In such cases, idempotency, outboxes, or appropriate reconciliation are required.

## 20. Restarting completed Steps vs. failed Steps

When restarting a JobInstance:

- Failed or stopped Steps can continue from saved state.
- Completed Steps are normally skipped.
- A Step configured with `allowStartIfComplete(true)` can run again even if completed, per Job flow and semantics.

For example:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .allowStartIfComplete(false)
            .build();
}
~~~

With `allowStartIfComplete(false)`, a completed Step will not automatically run again merely because the Job restarted. If you want to intentionally reprocess all data, consider creating a new JobInstance with an appropriate identifying parameter or configuring the Step to re-run per business requirements.

Do not use `allowStartIfComplete(true)` merely to work around a broken reader checkpoint. It can cause the Step to re-run and create duplicate effects if the writer is not idempotent.

## 21. Common pitfalls with reader state

### Reader does not implement ItemStream

If a reader holds state without providing the ItemStream lifecycle, the framework does not know how to save and restore position. Use a standard restartable reader or implement ItemStreamReader.

### Forgetting to enable saveState

The reader may work on the initial run without saving a checkpoint. On restart, it may start over from the beginning.

### Reader lacks a stable name

State keys may not be found after renaming the reader. Keep reader names stable for JobInstances that need restarting.

### Saving state after reading an item but before output commits

If the checkpoint advances while output has not committed, a restart may skip unwritten items. Let ItemStream updates and Step transactions manage checkpoints at the proper lifecycle points.

### File replaced between runs

Old line checkpoints no longer match the new file's content. Use immutable files, checksums, or versions.

### Database query lacks a stable ORDER BY

Result ordering may change between the run and the restart, causing missing or duplicate items. Use a unique sort key and clear continuation conditions.

### Non-unique sort key

If paging relies on duplicate keys, the reader may fail to determine accurate page boundaries. Add a unique tie-breaker.

### Singleton reader shared across multiple partitions

Workers can overwrite each other's read positions. Use StepScope and dedicated state per worker.

### ExecutionContext holds large or non-serializable objects

Metadata bloats or fails to persist. Store only small checkpoints such as IDs, line numbers, pages, or fingerprints.

### Non-durable JobRepository

Process restarts lose metadata and reader state. Use a durable repository if restarts across application startups are required.

## 22. Testing reader restarts

A meaningful restart test should run the same JobInstance across two JobExecutions.

Example scenario:

~~~text
Input: 10 items
Chunk size: 3

Run 1:
  Chunk 1: items 1-3 -> COMMIT
  Chunk 2: items 4-6 -> COMMIT
  Chunk 3: items 7-9 -> FAIL before commit

Restart:
  Reader opens with checkpoint item 6
  Re-reads items 7-9
  Last chunk: item 10 -> COMMIT

Result:
  Each item is written exactly once
~~~

The test should verify:

- The first run ends with the expected FAILED or STOPPED status.
- Step ExecutionContext contains the checkpoint of the most recently committed chunk.
- The restart uses the same identifying JobParameters.
- The reader starts at the next item after the checkpoint.
- Items in the uncommitted chunk are reprocessed.
- Items in already-committed chunks are not written twice.
- The final result contains complete target data.

Do not check only `readCount`. Inspect the set of business keys in the target table to detect missing or duplicate items.

## 23. Example unit test for custom reader state

You can test a custom reader's lifecycle in isolation:

~~~java
@Test
void restoresLastIdFromExecutionContext() throws Exception {
    CustomerRepository repository = mock(CustomerRepository.class);

    ExecutionContext saved = new ExecutionContext();
    saved.putLong("customerReader.lastId", 100L);

    Customer next = new Customer(101L, "Alice", "alice@example.com");
    when(repository.findFirstAfterId(100L)).thenReturn(next);

    CustomerReader reader = new CustomerReader(repository);

    reader.open(saved);

    assertEquals(next, reader.read());

    ExecutionContext updated = new ExecutionContext();
    reader.update(updated);

    assertEquals(
            101L,
            updated.getLong("customerReader.lastId"));

    reader.close();
}
~~~

This test verifies the reader restores `lastId` and saves state after reading the next item. This is only a unit test for the reader lifecycle.

You also need Step integration tests with JobRepository and a transaction manager to verify that checkpoints are saved properly when chunks commit and do not advance when chunks roll back.

## 24. Testing changing data sources

Restart tests should also verify the application detects when input sources have changed.

For example:

1. Run the Job with file A and record its checksum.
2. Make the Step fail after a few chunks.
3. Replace the file content while keeping the same path.
4. Restart the same JobInstance.
5. The reader or validation step detects the checksum mismatch.
6. The Job stops with a clear error instead of continuing on a different file.

With databases, test when records are inserted or updated after the watermark. Verify the Job processes only the dataset defined for that run or detects changes according to policy.

## 25. Checklist for designing a restartable reader

When building a Step that needs restarting, verify in order:

1. Does the reader have state that needs restoring?
2. Does the reader implement ItemStream or use an ItemStream-capable implementation?
3. Does `open()` restore state from ExecutionContext?
4. Does `update()` save the exact read position at checkpoints?
5. Does `close()` release resources safely?
6. Is `saveState` enabled?
7. Does the reader have a stable and unique name within the appropriate scope?
8. Does the Step register the reader and all ItemStream delegates?
9. Does JobRepository persist metadata durably?
10. Do file/database sources keep the same content or snapshot across restarts?
11. Does the query have stable ordering and a unique continuation key?
12. Does the reader have isolated state for each partition/worker?
13. Does the Job restart use the exact identifying JobParameters?
14. Do tests verify committed chunks are not re-read/re-written and uncommitted chunks are reprocessed?

Reader state is the foundation for Spring Batch to know where to resume reading after a Step stops or fails. ItemStream defines how to open, update, and close the reader; Step ExecutionContext stores the checkpoint; JobRepository retains checkpoints across executions. When readers hold stable state, data sources do not change unexpectedly, and transactions save checkpoints at proper commit boundaries, Jobs can restart without missing or duplicating data.
