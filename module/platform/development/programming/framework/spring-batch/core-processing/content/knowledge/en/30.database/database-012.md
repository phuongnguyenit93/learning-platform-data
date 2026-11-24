# Restarting Database Readers in Spring Batch

Database readers in Spring Batch often read thousands or millions of records. If a process stops midway, the job needs to resume from the latest committed point rather than re-reading all data or skipping records. This mechanism is called restarting a reader.

Spring Batch supports restart via ItemStream, ExecutionContext, and JobRepository. The reader persists a checkpoint in the execution context; when an execution is restarted, the reader reopens its resources and restores its reading position from the saved checkpoint. For this mechanism to work properly, the reader must support state persistence, have a stable identifier, and read data in a reproducible order.

For database readers, distinguish how cursor readers and paging readers restart. A cursor reader typically restores its position within the query results; a paging reader typically restores based on the sort key of the last read/committed record. Both depend on stable queries and stable source data.

## 1. How does restart differ from retry?

Retry handles an operation or item that fails transiently during execution. Restart resumes a stopped or failed job/step execution, typically in a new JobExecution belonging to the same JobInstance.

| Concept | Goal | Example |
| --- | --- | --- |
| Retry | Re-attempt a failed operation per retry policy | Re-calling processor when a service transiently times out |
| Rollback | Undo changes in an uncommitted transaction | Discarding writes of a failed chunk |
| Restart | Resume from the committed checkpoint of a previous execution | Continuing to read orders after the last committed chunk |

Suppose chunk size is 3 and the reader fetches orders with IDs 1 through 9:

~~~text
Chunk 1: 1, 2, 3 -> written successfully -> COMMIT
Chunk 2: 4, 5, 6 -> writer fails -> ROLLBACK
Job: FAILED

Restart:
Next chunk starts again from checkpoint after ID 3
Reader re-reads: 4, 5, 6
Then continues: 7, 8, 9
~~~

Items in an uncommitted chunk may be read and processed again. Restart does not mean Spring Batch remembers every in-memory Java action run before the process stopped; the framework restores committed durable state.

## 2. JobInstance and JobExecution determine which run restarts

Spring Batch distinguishes JobInstance and JobExecution:

- JobInstance represents a logical job run, identified by job name and identifying JobParameters.
- JobExecution is a concrete execution attempt of a JobInstance.
- A JobInstance can have multiple JobExecutions if a previous run failed or was stopped and restarted.

Example:

~~~text
Job: importOrders
Identifying parameter: businessDate=2026-11-15

JobInstance A
  |
  +-- JobExecution 1 -> FAILED
  |
  +-- JobExecution 2 -> COMPLETED (restart)
~~~

When restarting, pass the exact same identifying parameters so Spring Batch recognizes the same JobInstance. If you change an identifying parameter, such as business date or batch ID, you are requesting a different JobInstance and the reader will start with the state of a new execution.

Do not generate a new identifying run.id when the goal is to restart a failed execution. RunIdIncrementer typically creates a new identifier for a new logical run; it does not resume the previous JobInstance's checkpoint.

A completed JobInstance normally cannot be rerun with the same identifying parameters. To process a new batch, supply new identifying parameters matching business rules.

## 3. ExecutionContext is where checkpoints live

ExecutionContext is a key/value map managed by Spring Batch and persisted via JobRepository. Each StepExecution has a step execution context; JobExecution has a job execution context.

Database readers typically store the information needed to restore the reading position. When a step runs, the ItemStream lifecycle consists of:

- open(ExecutionContext): reads the saved checkpoint and opens the reader in the appropriate state.
- update(ExecutionContext): writes current state into the execution context.
- close(): releases cursors, connections, or resources owned by the reader.

Checkpoints are updated during chunk processing and saved alongside transaction metadata per repository/transaction manager configuration. When a chunk rolls back, an uncommitted chunk's checkpoint does not become a new recovery point; restart resumes from the most recently committed checkpoint.

Do not attempt to store ResultSet, Connection, or cursor objects in ExecutionContext. Store only serializable and recoverable values, such as item sequence counts, sort keys, file offsets, or business identifiers.

## 4. Reader must support ItemStream and saveState

Built-in Spring Batch database readers support ItemStream. To enable restarts, allow the reader to save state and assign a stable name:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("ordersCursorReader")
    .dataSource(dataSource)
    .sql("select id, customer_id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

With JdbcPagingItemReader, also set a name and enable state:

~~~java
new JdbcPagingItemReaderBuilder<OrderRow>()
    .name("ordersPagingReader")
    .dataSource(dataSource)
    .queryProvider(queryProvider)
    .pageSize(500)
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

saveState(true) lets the reader write recovery information into the execution context. If saveState is disabled, the reader does not save checkpoints and cannot rely on the reader's default stateful restart mechanism.

The reader name must be stable across runs and unique within the step scope. Spring Batch uses the reader name to build keys in the execution context. Renaming a reader across deployments can prevent old executions from matching the checkpoint keys expected by new code.

## 5. Restarting with JdbcCursorItemReader

JdbcCursorItemReader reads data through a JDBC cursor. The reader executes the query, then each read() call fetches the next row from the ResultSet and converts it into an item via RowMapper.

Example:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> ordersCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("ordersCursorReader")
        .dataSource(dataSource)
        .sql("""
            select id, customer_id, total, business_date
            from orders
            where business_date = ?
            order by id
            """)
        .preparedStatementSetter(ps ->
            ps.setDate(1, Date.valueOf(businessDate)))
        .rowMapper(new OrderRowMapper())
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

When the reader restarts, it re-executes the query and positions the cursor at the location corresponding to the checkpointed item count. Depending on driver and configuration, the reader may use ResultSet absolute positioning or advance sequentially through rows to reach the continuation point.

Consequently, cursor restart depends on the query returning the exact same result set in the exact same order. If inserts or deletes happen prior to the saved position, row positions can shift and the reader risks skipping or duplicating records.

### Conditions for stable cursor restart

- Explicit ORDER BY with deterministic ordering.
- Ordering should rely on a unique key, typically the primary key.
- WHERE conditions and job parameters must remain identical on restart.
- The dataset should remain stable during job execution and restart.
- RowMapper must never call ResultSet.next() or alter cursor position.

For instance, ORDER BY created_at may be insufficient if multiple orders share the same timestamp. Add ID as a tie-breaker:

~~~sql
select id, customer_id, created_at
from orders
where business_date = ?
order by created_at, id
~~~

If source data can change between two runs, define a snapshot or cutoff strategy. ORDER BY alone does not guarantee the result set remains unchanged.

## 6. driverSupportsAbsolute on cursor reader

JdbcCursorItemReader provides the driverSupportsAbsolute option. If the JDBC driver supports jumping the cursor to an absolute position, the reader can use that capability to restore position faster. If the driver does not support it, the reader must step through rows to reach the checkpoint.

Example configuration when the driver actually supports it:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("ordersCursorReader")
    .dataSource(dataSource)
    .sql("select id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .driverSupportsAbsolute(true)
    .saveState(true)
    .build();
~~~

Enable this option only after confirming the driver and ResultSet mode in use support absolute positioning. Do not enable it merely on a guess for speed; if unsupported by the driver, restart may fail or behave incorrectly.

With very large datasets, skipping through many rows to reach a checkpoint can take significant time. If restarts happen frequently deep into a dataset, a paging reader based on sort keys may fit better than a cursor reader.

## 7. Restarting with JdbcPagingItemReader

JdbcPagingItemReader retrieves data page by page. The reader uses PagingQueryProvider to generate queries tailored to the database and configured sort keys. On restart, the reader saves the sort key value of the processed position and continues querying rows after that key.

General configuration example:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("ordersPagingReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(Map.of(
            "businessDate", Date.valueOf(businessDate)
        ))
        .pageSize(500)
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
~~~

The query provider requires sort keys. Illustrative SQL:

~~~sql
select id, customer_id, total
from orders
where business_date = :businessDate
order by id
~~~

Once a checkpoint is saved after a chunk, the paging reader can resume strictly after the committed sort key value. This avoids reading and skipping all rows prior to the checkpoint as positional cursor recovery does.

### Sort keys must be unique and stable

If a sort key is not unique, multiple rows can share the same value at a page boundary. Upon restart, the "after last sort key" condition may skip rows sharing that key or produce non-deterministic results depending on the query provider.

If created_at is not unique, use a composite sort key:

~~~text
sort key = (created_at, id)
~~~

Sort keys must:

- Establish a total order across rows.
- Never change while the job is running.
- Have consistent comparison semantics in the database.
- Be supported by PagingQueryProvider.
- Align with queries and indexes to avoid full scans on restart.

Do not use a mutable field like status as a sort key if the writer or another process can update that field while the job runs.

## 8. Distinguishing pageSize and chunk size

The paging reader's pageSize and the step's commit interval are two distinct parameters:

| Parameter | Meaning | Impact |
| --- | --- | --- |
| pageSize | Rows the reader fetches in one page query | Affects query count, buffered data held by reader, and paging |
| chunk(size) | Items processed in one chunk transaction | Affects commit frequency, rollback scope, and checkpoint frequency |

Example:

~~~java
.chunk(100, transactionManager)
// reader:
.pageSize(500)
~~~

The reader can fetch a 500-row page while the step commits in chunks of 100 items. On restart, checkpoints reflect boundaries committed by the step, not merely that a page was loaded.

Setting page size equal to chunk size can be easy to reason about, though it is not mandatory. Choose based on database, network round trips, memory, and commit frequency.

## 9. Dataset changing between initial run and restart

Restarts are reliable only when the reader can interpret checkpoints against a compatible dataset. If the query returns a different set after the process stops, old checkpoints may no longer point to the right unprocessed data.

Example cursor reader saving row position 100:

~~~text
First run: 1, 2, 3, ... 100 [checkpoint], 101, 102, ...
After stop: a row before position 100 is deleted
New query: position 100 now corresponds to old row 101
Restart by row position may skip a row that needed processing
~~~

A paging reader using sort keys avoids some offset-shifting issues, yet still carries risks if:

- An already-processed row has its sort key updated and moves past the checkpoint.
- A new row is inserted with a sort key smaller than the checkpoint.
- Filter conditions change between two runs.
- A row is deleted or changes status such that it leaves the result set.
- The sort key is neither unique nor immutable.

Ways to mitigate risk:

1. Use a batch ID or business date to fix the input dataset.
2. Read only rows marked ready whose membership does not change throughout execution.
3. Use a cutoff timestamp or high-water mark captured at job start.
4. Use appropriate snapshots/isolation if database and job duration permit.
5. Design an immutable staging source for large batches or long-lived restartability.

Do not assume saveState(true) creates a database snapshot automatically. It persists the reader checkpoint; source data consistency still depends on transaction isolation, queries, and business workflows.

## 10. Using a high-water mark to fix the reading range

A common pattern is establishing an upper bound on data when the job starts. For example, taking the current maximum ID as a high-water mark:

~~~text
Job starts:
  minId = initial checkpoint
  maxId = 900000  <- captured once and kept in JobParameters/context

Reader:
  where id > lastCommittedId
    and id <= maxId
  order by id
~~~

Rows inserted after the job starts have IDs greater than maxId and therefore do not alter the current run's scope. The maxId value must be persisted durably with the job execution so restarts reuse the exact same bound.

If IDs are not monotonically increasing or rows can be updated/deleted, a high-water mark alone is insufficient. Combine it with batch membership, versioning, or an appropriate snapshot.

Never recompute a fresh maxId on every restart when the goal is resuming the same JobInstance. Doing so can expand the dataset mid-flight and produce results different from the initial run.

## 11. Reader state and chunk transactions

In a chunk-oriented step, the reader reads items, the processor processes them, and the writer writes inside a transaction. The reader updates execution context at chunk boundaries via ItemStream.update(). Spring Batch persists the context according to step and JobRepository lifecycles.

Example:

~~~text
BEGIN CHUNK 1
  Read 1, 2, 3
  Process 1, 2, 3
  Write 1, 2, 3
  Update reader checkpoint
COMMIT CHUNK 1

BEGIN CHUNK 2
  Read 4, 5, 6
  Process 4, 5, 6
  Write -> exception
  ROLLBACK CHUNK 2
~~~

The last committed checkpoint remains after item 3. On restart, the reader resumes from there. Items 4, 5, and 6 may be re-read because they belonged to an uncommitted chunk.

This assumes JobRepository and business data are managed with compatible transaction semantics. In setups with multiple datasources or different transaction managers, metadata checkpoints and business data may not share the same transaction. Design and test the failure window between business data commit and metadata commit to avoid duplicates or lost data.

## 12. Registering a delegate ItemStream when the reader is wrapped

If a database reader sits inside a wrapper that only implements ItemReader, Spring Batch may not realize the delegate needs open, update, and close lifecycles.

Wrapper example:

~~~java
public class LoggingOrderReader implements ItemReader<OrderRow> {

    private final ItemStreamReader<OrderRow> delegate;

    public LoggingOrderReader(ItemStreamReader<OrderRow> delegate) {
        this.delegate = delegate;
    }

    @Override
    public OrderRow read() throws Exception {
        return delegate.read();
    }
}
~~~

If the wrapper does not forward ItemStream, register the delegate with the step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderRow, OrderEntity>chunk(100, transactionManager)
    .reader(loggingReader)
    .stream(databaseReader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

Alternatively, have the wrapper implement ItemStreamReader and forward all three callbacks. If the delegate never receives open() and update(), it cannot restore checkpoints even when saveState(true) is configured.

## 13. @StepScope and database reader restart

Database readers are typically declared `@StepScope` when late binding of JobParameters or step execution context is needed:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> reader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    // Build reader for this JobExecution's input.
}
~~~

Each StepExecution gets a target reader matching that execution. On restart, Spring Batch instantiates a fresh target and passes the saved execution context to open(). In-memory runtime state stored in fields of the old reader does not survive a process restart; the durable checkpoint is the source of recovery.

Never use static fields to hold reader position. Two concurrent jobs could overwrite each other's positions. Nor should you share a mutable singleton reader across multiple step executions if the reader holds per-execution cursors or state.

`@StepScope` manages object lifecycle, while ExecutionContext stores checkpoints. The two mechanisms complement each other rather than replacing one another.

## 14. Reader name must stay stable across deployments

The reader name forms part of the state keys in execution context. Example:

~~~java
.name("ordersPagingReader")
~~~

If renamed to ordersReaderV2 while restarting an old JobInstance, the new reader may fail to read the state keys saved by the prior version. The reader might then start from scratch or fail to restore expected state depending on configuration.

When upgrading an application while jobs may be restartable:

- Preserve reader names if checkpoint structure remains compatible.
- If state storage changes, prepare a migration plan or handle legacy executions explicitly.
- Do not reuse the same reader name for two independent stateful readers in one step.
- Test restarting executions created by the previous application version against new code.

Renaming a step or reader, changing queries, altering sort keys, or changing types in context can all break restart compatibility. This is part of deployment design for long-lived batch jobs.

## 15. When is saveState(false) appropriate?

Some readers can be configured with saveState(false). In that case, the reader does not save checkpoints for restart. If the step fails and is rerun, the reader may start from the beginning or follow configured behavior, reprocessing data.

Use this only when:

- The reader is stateless and reprocessing the entire dataset is acceptable.
- The job is designed to be idempotent and does not need to resume from a checkpoint.
- The step runs once in an environment where restarts are not required.
- Another verified mechanism explicitly manages checkpoints.

Do not disable saveState merely to bypass serialization errors or simplify the reader if the job needs restarts. On large datasets, re-reading from the start can be very costly and create duplicate side effects if the writer is not idempotent.

## 16. Restarting with parameterized queries

Query parameters affecting the dataset must remain identical between the initial run and restart, such as businessDate, tenantId, status, or sourceBatchId.

If a parameter identifies the JobInstance, pass it via identifying JobParameters. If a value is computed during job execution, persist it in JobExecutionContext or StepExecutionContext as appropriate.

Example:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> reader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("tenantOrdersReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(Map.of(
            "businessDate", Date.valueOf(businessDate),
            "tenantId", tenantId
        ))
        .pageSize(300)
        .rowMapper(orderRowMapper)
        .saveState(true)
        .build();
}
~~~

On restart, do not change the tenant or business date of the same JobInstance. To run a different tenant, create a distinct JobInstance with the corresponding parameters.

## 17. Testing restart with JdbcPagingItemReader

Integration tests should use a database and JobRepository with durable state across two launches. A straightforward scenario:

1. Create 10 orders with IDs 1 through 10.
2. Configure a paging reader with unique sort key id, page size 4, and chunk size 2.
3. Have the writer write the first chunk successfully.
4. Have the writer intentionally throw an exception on a later chunk, making the step FAILED.
5. Verify data from committed chunks exists and the checkpoint was saved.
6. Restart the same JobInstance with the exact identifying parameters.
7. Verify the reader resumes after the checkpoint without omitting or duplicating valid orders.

Example test writer that fails exactly once:

~~~java
public class FailOnceWriter implements ItemWriter<OrderRow> {

    private final OrderRepository repository;
    private final AtomicBoolean fail = new AtomicBoolean(true);

    @Override
    public void write(Chunk<? extends OrderRow> chunk) {
        if (fail.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated failure");
        }

        repository.saveAll(chunk.getItems().stream()
            .map(OrderEntity::from)
            .toList());
    }
}
~~~

This illustrates failure injection; adjust where the error is thrown so an earlier chunk commits first. On restart, the writer proceeds and the reader uses the saved checkpoint.

Key assertions:

- First execution ends with BatchStatus.FAILED.
- Restart execution belongs to the same JobInstance.
- New execution ends COMPLETED.
- Final target record count equals valid source record count.
- Each business ID appears once in output if business rules require uniqueness.
- Items from the rolled-back chunk are reprocessed.

## 18. Testing restart with JdbcCursorItemReader

For a cursor reader, use data with an explicit, fixed order in tests. Force the writer to fail after at least one committed chunk, then restart the same JobInstance.

Verify:

- The query is re-executed on restart.
- The reader repositions after the checkpointed item count.
- No inserts/deletes shift row positions between the two runs.
- RowMapper returns the same business ID for the same record.
- The cursor is closed on the failed execution and a fresh cursor is opened on the restart execution.
- Final output has no omissions or duplicates.

If the test enables driverSupportsAbsolute(true), use a driver/database supporting absolute cursors and verify actual behavior. Test the default mode as well to confirm the reader works with your target driver.

## 19. Do not wrap the entire test launch in an outer transaction

When testing restarts, let chunks and metadata commit under Spring Batch's actual transactions. Marking the test method `@Transactional` so all data rolls back at test end can distort how per-chunk commits are observed or mask transaction bugs.

A clean structure:

1. Create fixture data and commit before launching the job.
2. Launch the job using JobLauncherTestUtils or JobLauncher.
3. Let the step manage per-chunk transactions.
4. Inspect JobExecution, StepExecution, and target tables after the job finishes.
5. Restart with the same identifying parameters.
6. Clean up fixtures in a separate teardown step.

JobRepository must persist metadata long enough for the second launch to read the previous execution context. Using an in-memory repository in tests cannot prove restart across an actual process restart; it only suits testing restarts within the same test process if the implementation retains state accordingly.

## 20. Inspecting metadata and checkpoints

You can use JobExplorer to inspect executions before and after restart:

~~~java
JobExecution previous = jobExplorer.getJobExecution(previousExecutionId);

assertThat(previous).isNotNull();
assertThat(previous.getStatus()).isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = previous.getStepExecutions()
    .stream()
    .filter(step -> step.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(failedStep.getExecutionContext())
    .containsKey("ordersPagingReader.start.after");
~~~

Specific keys inside execution context are implementation details of the reader and can change across versions. Production application code should never depend on internal keys. In illustrative tests, prefer verifying reader recovery through data behavior; inspect internal keys only when testing a specific implementation/version.

After restart, JobExplorer can query the new JobExecution and its StepExecutions. Verify they share the same JobInstance to confirm it was a restart rather than a new job instance.

## 21. Multiple datasources and transaction managers

A job may read from a source database, write to a target database, and store metadata in another datasource. In that case, clearly determine which transaction manager manages each resource.

If business data commits while the metadata checkpoint does not, restart may re-read already-written items. If the metadata checkpoint commits while business writes do not, restart may skip unwritten items. With multiple uncoordinated resources, two commits cannot be assumed atomic.

Strategies to consider:

- Use the same transaction manager/database for business writes and batch metadata if architecture permits.
- Use XA/JTA only when distributed transactions are genuinely required and operational complexity is accepted.
- Design idempotent writers with unique keys/upserts so reprocessing items is safe.
- Use outbox/inbox or staging tables to reconcile states across source, target, and batch metadata.
- Record operation IDs and durable status to recover across failure windows.

Restarting a reader alone does not solve consistency across two databases. It only restores the read position from the saved checkpoint.

## 22. Writers need to be idempotent when items may be re-read

Even when reader checkpoints are accurate, certain failure windows can still cause items to be reprocessed, especially when business writes and metadata do not share a transaction. Therefore, writers should have an appropriate duplicate-prevention strategy.

For example, the target table has a unique constraint on source order ID:

~~~sql
create unique index uk_imported_order_source
    on imported_order(source_order_id);
~~~

The writer can use upsert or insert-if-absent depending on the database. If updates are permitted, explicitly define whether a new import overwrites an earlier version.

An idempotency key should represent a business operation, such as sourceBatchId + orderId. Do not use order ID alone if the same order can legitimately be imported across multiple distinct batches.

## 23. Changes that can break restart compatibility

A job may restart after a new application version has been deployed. The following changes can affect checkpoints:

- Renaming the reader, which changes execution context keys.
- Changing sort keys or ORDER BY ordering.
- Changing WHERE conditions or job parameter semantics.
- Changing checkpoint data types.
- Changing queries in ways that alter result sets or ordering.
- Changing RowMapper/domain mapping so old items are no longer readable.
- Changing page size or paging provider in ways that alter semantics.
- Deleting or modifying source data that checkpoints depend on.

Not every page size change invalidates checkpoints, yet you must check against the specific implementation and query provider in use. For in-flight executions, maintain compatibility or have an explicit migration/abandon/reprocess plan.

Before deploying a new version, identify any FAILED/STOPPED jobs that may be restarted. Test restarting executions created by the previous version with the new code if mid-flight upgrades must be supported.

## 24. Common pitfalls when restarting database readers

**Not enabling saveState:** the reader does not save checkpoints and cannot resume from default state. Enable save state if the job needs restarts.

**Not setting a stable reader name:** execution context keys may change or collide. Assign a unique name and keep it stable.

**Restarting with new identifying parameters:** Spring Batch creates a new JobInstance and the reader ignores the old instance's checkpoint. Reuse exact parameters on restart.

**Cursor query without ORDER BY:** row order is not guaranteed, so checkpoint positions can point to different records. Use deterministic ordering with a unique tie-breaker.

**Source data changing before the checkpoint:** cursor positions can shift; paging sort keys may change or new rows may appear before the checkpoint. Fix inputs or use snapshots/cutoffs.

**Non-unique paging sort key:** multiple rows sharing a key may be skipped or processed twice. Use an immutable unique/composite sort key.

**Confusing page size with chunk size:** page boundaries are not commit boundaries. Understand checkpoints are saved per chunk transaction.

**Wrapper not registering delegate ItemStream:** the delegate misses open/update/close and fails to restore state. Forward lifecycle callbacks or register stream(delegate).

**Changing reader/query between runs without checking:** old execution context may become incompatible. Keep compatibility or handle old executions intentionally.

**Assuming reader restart makes writers exactly-once:** multi-resource transactions and failure windows can still produce duplicate writes. Design idempotent writers.

## 25. Checklist for designing database reader restart

Before promoting a job to production, verify:

- The reader implements ItemStream or is a framework reader supporting lifecycle callbacks.
- saveState(true) is enabled when restart is needed.
- The reader has a stable and unique name within the step.
- The query has deterministic filters and ordering.
- Cursor readers use a unique sort order; paging readers have unique/immutable sort keys.
- Job restarts use exact identifying JobParameters.
- Query parameters and data scope remain unchanged between initial run and restart.
- ExecutionContext is persisted in a durable JobRepository.
- Delegate streams are registered with the step.
- Writers can reprocess items safely or are idempotent.
- Integration tests prove resumption after committed chunks.
- A strategy exists for when source data mutates or a new application version deploys.

## 26. Design and testing workflow in production

First, define the dataset the job reads and ensure it is reproducible upon restart. Choose a cursor reader when continuous cursor streaming with stable ordering is needed; choose a paging reader when pagination and sort-key recovery are preferred. Use deterministic ORDER BY, unique/composite sort keys, and cutoffs/batch membership if the source can mutate.

Next, configure the reader with a stable name and saveState(true). Let the reader participate in the ItemStream lifecycle, persist checkpoints in ExecutionContext, and use a durable JobRepository. When restarting, rerun the same JobInstance with identical identifying parameters; do not generate a new run.id when resuming a previous execution.

Finally, test against a real database: commit a chunk, fail the next chunk, then restart and verify the reader resumes from the checkpoint. Confirm no missing/duplicate business keys, old resources are closed, queries/sort keys remain unchanged, and writers are idempotent across failure windows. If multiple datasources exist, explicitly design how business commits stay synchronized with metadata checkpoints.

Database reader restart relies on committed checkpoints and a reproducible query. JdbcCursorItemReader restores position within results; JdbcPagingItemReader restores based on sort keys. When reader names, queries, parameters, and source data are stable, Spring Batch can resume processing after failure without restarting the entire batch from scratch. Idempotent writers and thorough restart integration tests protect data when processes stop or transactions fail.
