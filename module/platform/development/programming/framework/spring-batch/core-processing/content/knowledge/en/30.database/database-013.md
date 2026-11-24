# Reading and Writing to the Same Database

In Spring Batch, a Job often reads data from a database, processes each item, and writes results back to the database. It may read from a source table and write to a target table, or read rows and update those very same rows. Both patterns are common, but require careful design of transactions, readers, writers, read ordering, and checkpoints to avoid duplicate reads, skipped data, or holding locks too long.

When a reader and writer share the same database, clearly determine:

- Do the reader and writer use the same DataSource?
- Which transaction manager does the Step use?
- Does the reader participate in chunk transactions or open its own connection?
- Does the writer write to a different table or update the table the reader is reading?
- Which stable key paginates the data?
- Upon rollback or restart, can the reader resume accurately?

Do not assume that sharing the same database means all read and write operations share the same connection or the same snapshot. That depends on the reader implementation, transaction manager, isolation level, and database driver.

## 1. Two patterns for reading and writing to the same database

Two patterns appear frequently:

**Reading a source table, writing a result table**

~~~text
orders_source
      |
      v
ItemReader
      |
      v
ItemProcessor
      |
      v
ItemWriter
      |
      v
orders_result
~~~

For example, reading completed transactions from the orders table, calculating fees, and writing results to order_summary. Both tables reside in the same database, yet source and target data are separate. This is usually the easier pattern to control.

**Reading and updating the same table**

~~~text
orders
  |
  v
Reader fetches rows with status = READY
  |
  v
Processor validates and computes
  |
  v
Writer updates status = PROCESSED
  |
  v
orders
~~~

The second pattern requires more care. If the writer modifies columns used in read filters or pagination keys, the dataset the reader is traversing can shift mid-Step. If multiple Jobs process the table concurrently, you must also prevent two Jobs from picking up the same row.

## 2. Configuring DataSource and transaction manager

A chunk Step typically receives a JobRepository and a PlatformTransactionManager. For JDBC, common transaction managers are DataSourceTransactionManager or JdbcTransactionManager managing a DataSource.

Example configuring a Step reading and writing to the same database:

~~~java
@Bean
public Step summarizeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderSummary> processor,
        ItemWriter<OrderSummary> summaryWriter) {

    return new StepBuilder("summarizeOrdersStep", jobRepository)
            .<Order, OrderSummary>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(summaryWriter)
            .build();
}
~~~

If the reader and writer use the same DataSource managed by the Step's transaction manager, JDBC operations join transactions per each component's support. When the writer fails before commit, uncommitted database changes in the chunk transaction can roll back.

Do not rely merely on two beans having the same JDBC URL to conclude they share a transaction. Verify they actually use the same DataSource bean and matching transaction manager. Two separate DataSource beans, even pointing to the same database/schema, still create two connection pools and two independent transactions.

### Must JobRepository share the business database?

JobRepository stores metadata such as JobExecution, StepExecution, and ExecutionContext. The business database stores data read/written by the Job. The two can share one database or be separated.

If metadata and business data participate in a single suitable transaction manager, checkpoint updates and chunk data can be coordinated within one transaction. If they reside in two databases or use two independent transaction managers, evaluate the risk of commits drifting out of sync.

For instance, business data committing while a checkpoint fails to save can cause restart to re-read items and write duplicates. Conversely, a checkpoint saving while business data rolls back can cause the reader to skip unwritten items. With two independent resources, design idempotency, unique keys, or reconciliation mechanisms.

## 3. Reading and writing with JDBC readers/writers

Spring Batch provides standard JDBC components:

| Component | Role |
| --- | --- |
| JdbcCursorItemReader | Reads query results via a JDBC cursor |
| JdbcPagingItemReader | Reads page by page using paginated queries |
| JdbcBatchItemWriter | Writes multiple items using JDBC batch updates |
| JdbcTemplate | Executes JDBC operations in services or custom components |

Choose a reader based on dataset size, database cursor capabilities, pagination, restarts, and transaction impact. Writers typically use JdbcBatchItemWriter when batched inserts/updates are needed.

## 4. Example reading one table and writing to another

Suppose there are two tables:

~~~sql
create table orders (
    order_id bigint primary key,
    customer_code varchar(40),
    total_amount decimal(18, 2),
    status varchar(20)
);

create table order_summary (
    order_id bigint primary key,
    customer_code varchar(40),
    total_amount decimal(18, 2),
    tax_amount decimal(18, 2),
    processed_at timestamp
);
~~~

Reader fetching completed orders:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount, status")
            .fromClause("from orders")
            .whereClause(
                    "where status = :status and business_date = :businessDate")
            .parameterValues(Map.of(
                    "status", "COMPLETED",
                    "businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Processor calculating tax:

~~~java
public class OrderSummaryProcessor
        implements ItemProcessor<Order, OrderSummary> {

    @Override
    public OrderSummary process(Order order) {
        BigDecimal tax = order.getTotalAmount()
                .multiply(new BigDecimal("0.10"));

        return new OrderSummary(
                order.getOrderId(),
                order.getCustomerCode(),
                order.getTotalAmount(),
                tax,
                Instant.now());
    }
}
~~~

Writer writing to the result table:

~~~java
@Bean
public JdbcBatchItemWriter<OrderSummary> summaryWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<OrderSummary>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_summary
                    (order_id, customer_code, total_amount,
                     tax_amount, processed_at)
                    values
                    (:orderId, :customerCode, :totalAmount,
                     :taxAmount, :processedAt)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

In this example, the reader queries the orders table while the writer inserts into order_summary. If both components use the Step's DataSource and transaction manager, inserts execute inside the chunk transaction. When a chunk rolls back, uncommitted inserts roll back with the database transaction.

The example assumes order_id is unique in the processed dataset and order_summary does not yet contain those rows. If the Job can restart or rerun with the same business input, define behavior when keys already exist: fail, update, database-specific upsert, or controlled skip. Do not use an arbitrary overwrite strategy to mask duplicate processing.

## 5. JdbcBatchItemWriter and batch updates

JdbcBatchItemWriter fits when each item produces an insert or update statement. The writer executes statements in batches to reduce database round trips.

Example updating order status:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderStatusWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    update orders
                    set status = :status,
                        processed_at = :processedAt
                    where order_id = :orderId
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

If an update does not affect the expected number of rows, assertUpdates(true) helps catch cases where the writer updated zero rows. However, batch update count semantics can vary across JDBC drivers and statements; test against a real database.

For conditional updates, include guard predicates in SQL:

~~~sql
update orders
set status = 'PROCESSED'
where order_id = :orderId
  and status = 'READY'
~~~

The status = READY condition detects or prevents updating a row already processed by another worker. If zero rows are updated, the application must decide whether that represents a duplicate, conflict, or data error.

## 6. Reading and updating the exact same table

Reading and then updating the same table is common when processing a database work queue:

~~~text
orders.status = READY
        |
        v
Reader selects READY rows
        |
        v
Processor processes
        |
        v
Writer changes status to PROCESSED
~~~

The problem arises when status is the filter condition. Once the writer updates a row from READY to PROCESSED, that row leaves the READY query set. If the reader paginates by offset or a query affected by the mutating result set, subsequent rows may be skipped or repeated.

For example, suppose a query returns 10 READY rows with page size 5:

~~~text
First page: 1, 2, 3, 4, 5
Writer updates status of these rows to PROCESSED

Remaining READY set: 6, 7, 8, 9, 10
If the next page query uses offset 5:
  skips the first 5 rows of the remaining set
  may return no rows at all
~~~

This is the risk of positional pagination over a mutating result set. Spring Batch paging readers can use sort keys and key-based queries depending on database dialect, so not every setup uses offsets as in the illustration. Even so, the principle remains to keep read predicates and pagination keys stable throughout the run.

### Avoid changing selection criteria while iterating

If the reader selects status = READY, do not update those rows' status while relying on unstable pagination over the same dataset. You can:

- Read a predetermined set of IDs.
- Use an immutable key column as the sort key.
- Select a fixed batch ID or cutoff.
- Use a staging/claim table to keep the work set stable.
- Split data selection and status update steps where appropriate.

## 7. Using a staging table to isolate the input set

A controllable pattern is creating a staging or batch membership table to fix the rows belonging to a run:

~~~sql
create table batch_order_item (
    batch_id varchar(80) not null,
    order_id bigint not null,
    processing_status varchar(20) not null,
    primary key (batch_id, order_id)
);
~~~

A preparation step selects the orders to process and writes their IDs into batch_order_item. The processing Step then reads only rows belonging to the current batch_id:

~~~sql
select o.order_id, o.customer_code, o.total_amount
from orders o
join batch_order_item b on b.order_id = o.order_id
where b.batch_id = :batchId
  and b.processing_status = 'READY'
order by o.order_id
~~~

When the writer updates status, it can update processing_status in the staging table or write results to another table. Batch membership does not shift merely because business status on orders changes.

Staging helps:

- Explicitly identify which rows belong to a JobInstance.
- Keep the input set stable across restarts.
- Reconcile selected, processed, and failed row counts.
- Split ranges for partitioning.
- Avoid relying on dynamic conditions on business tables.

In return, you must manage staging record lifecycles, batch IDs, cleanup, and consistency between staging and business data.

## 8. Claiming or reserving rows so multiple Jobs do not double-process

If multiple Jobs or workers read the same READY table concurrently, simply running SELECT and processing can cause two workers to pick up the same row. A claim/reserve mechanism is needed.

One approach is updating status to CLAIMED with an owner or batch ID before processing:

~~~sql
update orders
set status = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = current_timestamp
where order_id = :orderId
  and status = 'READY'
~~~

Only the worker that updates exactly one row is considered to have claimed it successfully. If update count is 0, the row was already claimed by another worker or its status changed.

However, claiming row by row after the reader has already read does not automatically make the whole workflow atomic. Define transaction boundaries, claim timeouts, and how abandoned claims are reclaimed when a worker crashes.

Some databases support SELECT ... FOR UPDATE SKIP LOCKED so multiple workers select different rows:

~~~sql
select order_id, customer_code, total_amount
from orders
where status = 'READY'
order by order_id
for update skip locked
~~~

This syntax is database-specific, not portable SQL. Locking behavior, holding locks across transactions, and compatibility with cursor/paging readers must be tested on the database in use. Do not assume every JDBC driver or database supports SKIP LOCKED.

For long-running processing, holding row locks throughout processor/writer execution can increase contention. A short claim followed by processing outside the lock transaction can reduce lock duration, though it requires leases/timeouts and claim recovery.

## 9. Transaction isolation and data visibility

Isolation levels determine how a transaction sees changes from other transactions. Common levels:

| Isolation | General meaning |
| --- | --- |
| READ_UNCOMMITTED | Can read uncommitted data if supported by the database |
| READ_COMMITTED | Reads only committed data; later queries can see new commits |
| REPEATABLE_READ | Restricts re-reading the same row from yielding different results; details depend on the database |
| SERIALIZABLE | Provides higher isolation, usually with higher locking or conflict-checking cost |

Do not pick the highest isolation level for every Job. High isolation can increase locks, deadlocks, and transaction times. Low isolation can allow datasets to change between pages or chunks.

For Jobs needing a logical snapshot, use a fixed cutoff, snapshot isolation if supported by the database, staging tables, or batch membership rather than holding a very long transaction.

### A Job does not have a single snapshot by default

Chunk-oriented Steps normally commit after each chunk. Thus, each chunk has its own transaction. If the source mutates between chunks, the Step may observe different data depending on isolation and reader.

Example:

~~~text
Chunk 1 transaction -> reads data at T1 -> commit
Chunk 2 transaction -> reads data at T2 -> commit
Chunk 3 transaction -> reads data at T3 -> commit
~~~

If business rules require a fixed input set, lock the dataset down with a batch ID, watermark, snapshot, or staging table. Never assume the entire Job automatically runs inside one single transaction.

## 10. JdbcCursorItemReader sharing a database with the writer

JdbcCursorItemReader opens a JDBC cursor to read the result set. Note that the reader typically opens a separate connection for the cursor so it can stay alive across chunk commits. Hence, the writer using the same DataSource does not mean the cursor shares the writer's transaction connection by default.

Example:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    select order_id, customer_code, total_amount
                    from orders
                    where status = 'READY'
                    order by order_id
                    """)
            .rowMapper(new OrderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

A cursor reader can fit large datasets when the database/driver supports cursors efficiently. Keep in mind:

- The cursor connection may differ from the chunk transaction connection.
- The writer may update the very rows the cursor is traversing.
- Isolation and cursor holdability depend on the database/driver.
- Cursors often hold connections for a long time, affecting the connection pool.
- Restart requires the reader to save state and reopen the query at the right position.

JdbcCursorItemReader has an option to share an extended connection in cases needing a shared wrapped connection. This setup requires ExtendedConnectionDataSourceProxy and driver support for cursor holdability over commit. Do not enable it merely because reader and writer share a database; confirm the requirement and test on a real database/driver.

## 11. JdbcPagingItemReader when reading and writing the same table

JdbcPagingItemReader fetches data page by page. It fits when you do not want to hold a cursor open long or need pagination and sort-key-based restarts.

Example:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> readyOrderReader(
        DataSource dataSource) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("readyOrderReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(200)
            .saveState(true)
            .build();
}
~~~

The sort key must define a stable and preferably unique ordering. If using multiple columns, ensure the sort key combination forms a total order.

If the writer updates status from READY to PROCESSED, the query predicate changes while the Step is reading. Check how the paging provider builds queries and ensure subsequent pages do not skip rows. A safer approach is using a batch ID/staging table or partitioning by an immutable key.

Page size and chunk size are two distinct parameters:

- Page size determines how many rows the reader fetches in one page query.
- Chunk size determines how many items are processed in one chunk transaction.

For instance, page size 500 and chunk size 100 mean the reader can load a 500-row page while the Step commits every 100 items. Balance memory, round trips, transaction duration, and restart impact.

## 12. Reading via cursor or paging?

| Criterion | JdbcCursorItemReader | JdbcPagingItemReader |
| --- | --- | --- |
| Reading approach | Keeps result set/cursor open | Queries page by page |
| Connection | Typically uses a separate connection for the cursor | Executes queries per page; can participate in transaction per DataSource config |
| Resources | Can hold a connection for a long time | Does not hold a single cursor throughout the whole Step |
| Restart | Needs to save and restore cursor position | Saves pagination/sort key state |
| Source data changes | Depends on cursor, isolation, and database | Result set can shift between pages |
| Best suited for | Long sequential reads on DBs with good cursor support | Large datasets needing pagination and restarts |

Neither option is universally best for all databases. Measure queries, fetch size, page size, cursor open duration, connection usage, and restart behavior in a production-like environment.

## 13. Avoiding re-reading already processed data

A common design uses READY and PROCESSED statuses. If the reader selects READY and the writer flips it to PROCESSED, ensure the reader is not disrupted by the shifting result set in a way that corrupts pagination positions.

One option is picking a fixed watermark for the run:

~~~sql
select order_id, customer_code, total_amount
from orders
where status = 'READY'
  and order_id <= :maxOrderId
order by order_id
~~~

In a preparation step, fetch maxOrderId or a cutoff and store it in JobParameters/JobExecutionContext. This bounds the Job's input set. However, if new READY rows are inserted with IDs below the watermark or statuses change, define explicitly whether they belong to the current batch.

Another option is saving the ID list into a staging table. This is usually clearer when the dataset must remain fixed across restarts.

Never use a current timestamp recomputed on every chunk as a cutoff. Establish the cutoff once at Job start and keep it constant throughout the JobInstance.

## 14. Idempotency and business keys

Restarts, retries, or reruns can cause the same item to be processed multiple times. If the writer inserts results, enforce a unique key or idempotent mechanism.

Example:

~~~sql
create table order_result (
    order_id bigint primary key,
    result_amount decimal(18, 2),
    processed_at timestamp
);
~~~

The order_id key prevents two runs from creating two identical result rows. When an insert hits a duplicate key, the application must decide whether that is a failing error, a valid rerun, or requires a versioned update.

For updates, include prior-status or version predicates:

~~~sql
update orders
set status = 'PROCESSED',
    version = version + 1
where order_id = :orderId
  and status = 'READY'
  and version = :expectedVersion
~~~

If updated row count is 0, another worker may have modified the data. Handle it as a conflict or duplicate per business rules.

Do not rely solely on the writer running in a transaction to conclude duplicates cannot happen. Transaction rollback does not undo side effects already sent to APIs, message brokers, or other systems. For such side effects, use idempotency keys, inbox/outbox, or reconciliation mechanisms.

## 15. Locking and deadlocks

When multiple Jobs or workers read and update the same table, the database may hold row locks or page locks depending on statements and engine. Overly large chunk transactions hold more locks for longer durations.

Common causes:

- Two Jobs select the same set of READY rows.
- The reader holds a cursor while the writer updates the same table.
- Workers update multiple rows in different orders.
- Inadequate indexes cause the database to lock a wider range than expected.
- Large chunk sizes make transactions hold locks too long.
- Writer batch updates create lock contention.

Reduce risk by:

- Dividing work into non-overlapping ranges.
- Updating rows in a consistent key order.
- Keeping transactions short.
- Creating indexes matching filter predicates and sort keys.
- Using claim/reservation or SKIP LOCKED if supported by the database.
- Capping concurrency according to database capacity.
- Configuring bounded retries for deadlocks/serialization failures.

Never retry a deadlock infinitely. If the same resource access ordering repeatedly causes deadlocks, fix the query design or update ordering.

## 16. Transaction timeouts and chunk size

Chunk size directly affects how many rows the writer updates in one transaction. Larger chunks reduce commit counts, yet can:

- Hold row locks longer.
- Increase rollback cost.
- Increase memory usage.
- Make deadlocks harder to recover from.
- Increase connection wait times or transaction timeouts.

Smaller chunks generally shorten transaction times, yet increase commits and metadata updates.

Measure reading, processing, writing, and commit durations. If the processor calls remote services, avoid holding a database transaction open across long network waits. You can separate external processing from short transactional writes, while maintaining consistency via idempotency and job state.

## 17. Restart and checkpoints when reading/writing the same database

Both reader and writer need proper state handling for restarts. With ItemStream-capable readers, checkpoints are typically persisted in StepExecutionContext at chunk boundaries. JdbcPagingItemReader and JdbcCursorItemReader can save read state when saveState is enabled.

Example:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, OrderResult>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderResultWriter)
        .build();
~~~

When a chunk commits, writer data and checkpoints must align. When a chunk rolls back, uncommitted state must not become a durable checkpoint.

For safe restarts:

- Preserve the Job name and identifying JobParameters of the JobInstance.
- Keep reader names stable.
- Keep sort keys and query filters stable.
- Never alter the input dataset or cutoff between runs and restarts.
- Ensure the writer is idempotent if items can be reprocessed.
- Never delete or mutate staging data that checkpoints depend on.

If the reader queries READY rows while the writer flips status to PROCESSED, a restart must still reproduce the same incomplete dataset. Staging tables or batch membership usually make this much clearer.

## 18. Reading and writing to the same database in one Step or multiple Steps?

You can split the workflow into multiple Steps when clearer boundaries are needed:

~~~text
prepareBatchStep
    |
    v
processBatchStep
    |
    v
finalizeBatchStep
~~~

Example:

- prepareBatchStep selects rows and writes IDs into a staging table.
- processBatchStep reads staging and writes results.
- finalizeBatchStep updates batch status, aggregates errors, and marks completion.

Splitting Steps makes progress tracking, restarts, and reconciliation clearer. However, each Step has its own transaction; intermediate data must be persisted durably and remain restartable.

If the workflow is small and needs no staging, a single chunk Step may suffice. Do not split into many Steps merely to avoid understanding transactions; base the decision on business requirements, recoverability, and observability.

## 19. Testing reading and writing to the same database

Test with a database having semantics close to production. H2 or in-memory databases may differ in cursors, locking, isolation, paging SQL, and batch update counts.

Scenarios to test:

1. Reading from a source table and inserting into a target table in the same transaction.
2. Writer failing mid-batch and verifying chunk data rolls back.
3. Restarting after several committed chunks and checking for zero dropped/duplicate rows.
4. Reading and updating the same table with page size larger than chunk size.
5. Two Jobs selecting the READY set concurrently to test claim/locking.
6. A row modified by another worker before the writer updates it.
7. Deadlocks or lock timeouts with bounded retries.
8. Source data mutating while the Job runs.
9. Job restarting while staging/batch membership remains intact.
10. Concurrent Jobs running with identical or different JobParameters.

Example rollback test:

~~~java
@Test
void rollsBackDatabaseWritesWhenChunkFails() {
    // Launch Step with reader and writer sharing the same DataSource.
    // Configure writer/test hook to fail before commit.
    // After Step fails, query target table to confirm
    // rows from the uncommitted chunk do not exist.
}
~~~

This is a test skeleton description; implement fixtures and fault injection per application. Never assert BatchStatus alone. Query the database to confirm actual data, row statuses, checkpoints, and record counts.

## 20. Common pitfalls

### Assuming same database means same transaction

Two beans may use different DataSources or transaction managers even when pointing to the same database. Verify which resources are actually managed.

### Reading and updating the same table with an unstable query

The writer alters filter predicates or sort keys while the reader is paginating. Use immutable keys, batch IDs, or staging tables.

### Using a cursor and assuming the writer shares the connection

JdbcCursorItemReader usually opens a separate connection for the cursor. Check shared extended connections and driver requirements if needed.

### Paginating without a unique order

Unstable ordering can cause duplicate reads or omissions. Use a unique sort key or composite key.

### Multiple Jobs reading READY rows concurrently

Two Jobs may pick up the same item. Use claiming, locking, batch membership, or coordination mechanisms.

### Overly long transactions

Large chunks or processors waiting on external services can hold locks too long. Optimize transaction duration and chunk size.

### Non-idempotent writers

Restarts or retries can create duplicate results. Use unique keys, controlled upserts, or version checks.

### Using skip to ignore all database errors

Connection failures or deadlocks usually need dedicated retry/fail policies rather than being treated as skippable bad data.

### Checking only Step status

A COMPLETED Step does not prove target data is accurate. Verify record counts, business keys, source statuses, and reconciliation outputs.

### Testing on a different database than production

Paging, cursor, and locking semantics can differ. Run integration tests on the same database engine when behavior depends on engine details.

## 21. Workflow for designing a Step that reads and writes the same database

Before implementing, determine:

1. Do the reader and writer share the same DataSource bean or merely the same database server?
2. Which resource does the Step's transaction manager manage?
3. Does JobRepository share a transaction boundary with business data?
4. Are data reads and writes on two tables or the same table?
5. If on the same table, does the writer mutate the reader's filter predicates or sort keys?
6. Is cursor or paging better suited to the database and dataset?
7. Is the sort key unique and stable?
8. Can the source change while the Job runs?
9. Is a batch ID, staging, or claim needed to fix the input set?
10. Can multiple Jobs/workers pick up the same row?
11. Are chunk size, page size, fetch size, and connection pools sized appropriately?
12. Can retries, rollbacks, and restarts cause duplicate processing?
13. Does the writer have suitable unique keys or idempotency?
14. Do you need to measure lock waits, deadlocks, query times, and batch update counts?

A solid design keeps the input set stable, transactions short, read ordering deterministic, and writers safely recoverable. When data must be selected once and processed across multiple restarts, staging or batch membership is usually a clear way to preserve scope.

## Conclusion

Reading and writing to the same database is a common pattern in Spring Batch, but you must distinguish reading a source table and writing a target table from reading and updating the exact table being traversed. Using the same DataSource and matching transaction manager lets the writer join chunk transactions; however, readers like JdbcCursorItemReader may use a separate connection, while paging depends on sort keys and stable result sets. When updating the same table, avoid mutating filter predicates or pagination order while reading; consider batch IDs, staging, claiming, or locking to avoid duplicate processing. Design checkpoints, unique keys, and idempotency so retries/restarts neither lose nor duplicate data, and test on a real database because cursors, isolation, and locking are engine-dependent.
