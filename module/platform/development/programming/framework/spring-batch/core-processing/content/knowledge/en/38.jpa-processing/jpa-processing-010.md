# Restarting with Database Items in Spring Batch JPA

When a Spring Batch job reads data via JPA, it may process thousands or millions of entities. If the process stops partway through, the next run must resume from the latest committed checkpoint. If the reader starts over from the beginning, the job can waste significant time, write duplicate records, or produce repeated side effects. If the reader skips too many items, data can be lost.

With JPA, the most common reader is `JpaPagingItemReader`. It fetches data page by page using JPQL while supporting state persistence so Spring Batch can restore the read position on restart. However, a checkpoint is meaningful only when the `JobInstance`, query, parameters, data ordering, and source dataset remain compatible with the previous run.

This lesson explains restarting with JPA database items, how the reader saves and restores state, limitations of offset pagination, `EntityManager` lifecycles, transactions, source data changes, and how to test restarts thoroughly.

## 1. What does restart mean in Spring Batch?

Restarting means resuming a stopped or failed job/step execution based on persisted metadata and checkpoints. Spring Batch does not preserve the memory of the previous process; it creates a new execution and restores the durable state required.

Example step with chunk size 3:

~~~text
Chunk 1: Customer 1, 2, 3 -> written successfully -> COMMIT
Chunk 2: Customer 4, 5, 6 -> writer error -> ROLLBACK
JobExecution 1 -> FAILED

Restart same JobInstance:
  Reader resumes after chunk 1 checkpoint
  Customer 4, 5, 6 are re-read
  Then continues with Customer 7, 8, 9, ...
~~~

Items in an uncommitted chunk can be read and processed again. Therefore, restarting does not guarantee every item is processed strictly once across every failure window. Writers and external side effects must be safe when items are redelivered.

## 2. JobInstance and JobExecution

Spring Batch distinguishes a logical run from a concrete execution attempt:

- `JobInstance` is identified by the job name and identifying `JobParameters`.
- `JobExecution` is a single execution attempt of a `JobInstance`.
- One `JobInstance` can have multiple `JobExecution`s if a prior attempt failed or stopped and was restarted.

Example:

~~~text
Job: importCustomers
Identifying parameter: businessDate=2026-11-15

JobInstance A
  |
  +-- JobExecution 1 -> FAILED
  |
  +-- JobExecution 2 -> COMPLETED
~~~

To restart the same job instance, pass the exact same identifying parameters. If you change `businessDate`, `tenantId`, or `batchId` when it is an identifying parameter, Spring Batch creates a new `JobInstance` and the reader will not use the old instance's checkpoint.

Do not generate a new `run.id` when the goal is resuming a failed execution. `RunIdIncrementer` typically creates a new identifying parameter for a new logical run; it is not a checkpoint recovery operation.

A completed `JobInstance` cannot be re-run as a normal restart with the same identifying parameters. To process a new batch, supply new business identifying parameters.

## 3. ExecutionContext stores checkpoints

`ExecutionContext` is a key/value map managed by Spring Batch and persisted via `JobRepository`. Each `StepExecution` has its own step execution context, and `JobExecution` has a job execution context.

A reader can implement `ItemStream` with the following lifecycle:

- `open(ExecutionContext)`: opens resources and restores saved checkpoints.
- `update(ExecutionContext)`: writes current state into the execution context.
- `close()`: releases reader resources.

`JpaPagingItemReader` implements `ItemStream` and persists the number of items read to determine the resume position. When the step commits a chunk, reader state is updated in the execution context. When a chunk rolls back, the uncommitted chunk's checkpoint does not become the new restart point.

Store only serializable, recoverable state—such as items read, page position, or a business key managed by a custom reader. Never store `EntityManager`, `Query`, managed entities, or JPA resources in `ExecutionContext`.

## 4. What is JpaPagingItemReader?

`JpaPagingItemReader` reads entities or projections from the database page by page using JPQL. Whenever a new page is needed, the reader runs a query with `firstResult` and `maxResults` computed from the page size.

The reader is typically configured with:

- `EntityManagerFactory`: factory used to create `EntityManager` instances.
- Query string: JPQL used to fetch data.
- Parameter values: values bound to named parameters.
- Page size: number of items per page.
- Name: stable name used to key entries in the execution context.
- Save state: enables checkpoint persistence for restarts.

Example:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['customerStatus']}") String status) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("customerJpaReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.status = :status
            order by c.id
            """)
        .parameterValues(Map.of("status", status))
        .pageSize(200)
        .saveState(true)
        .build();
}
~~~

This example uses the Spring Batch 5 builder API. Package names, builders, and some methods may differ in older Spring Batch versions; match the API of your project's dependencies.

## 5. Why does the reader need a stable name?

The reader name is used to construct keys in the execution context. Example:

~~~java
.name("customerJpaReader")
~~~

If you rename the reader between the initial run and a restart, the new reader looks up a different state key and fails to restore the checkpoint saved under the old name.

Rules:

- Give the reader a meaningful name that is unique within the step.
- Keep the name stable across restarts of the same `JobInstance`.
- Do not share the same name between two independent stateful readers in the same step.
- When changing a reader name or state structure, evaluate compatibility with older executions that may still be restarted.

Renaming a reader is akin to changing a checkpoint format. Never deploy such a change while a long-running job is `FAILED` or `STOPPED` without a plan for existing executions.

## 6. saveState and restartability

When the reader saves state, Spring Batch restores the read position based on the item count recorded at the checkpoint. In configuration, specify this explicitly:

~~~java
.saveState(true)
~~~

If `saveState` is disabled, the reader does not persist stateful checkpoints through the default mechanism. Re-runs may start from the beginning or fail to resume from the prior position.

Disable state saving only when re-reading the entire dataset is acceptable, or when a separate custom checkpointing mechanism is designed and tested. For large jobs, disabling `saveState` prolongs execution and causes duplicate side effects if the writer is not idempotent.

`saveState` does not create a database snapshot. It saves only reader state. The dataset returned by the query can still mutate between the initial run and a restart.

## 7. How does JpaPagingItemReader restore its position?

`JpaPagingItemReader` builds on Spring Batch's paging and item-counting infrastructure. The reader persists the count of items read; on restart, it computes the page containing that position and re-queries that page. Fundamentally, paging queries use offsets:

~~~text
firstResult = pageNumber * pageSize
maxResults  = pageSize
~~~

Example with page size 100 and a checkpoint recording 250 items read:

~~~text
Page 0: offset 0,   item 1-100
Page 1: offset 100, item 101-200
Page 2: offset 200, item 201-300

Checkpoint: 250 items read
Restart: load page 2, skip first 50 items in page
Resume from item 251
~~~

This avoids serializing entity objects from the previous process. It re-queries the target page and skips the already-checkpointed portion of that page.

Because restart relies on positional indexing in the query results, the query must return a compatible dataset in the exact same order. If rows are inserted or deleted before the offset, position 251 may no longer refer to the same customer.

## 8. JPQL must have deterministic ordering

Never rely on the arbitrary row order returned by a database when a query lacks `ORDER BY`. Without deterministic ordering, subsequent pages or restarts can return items in a different sequence.

Example to avoid:

~~~sql
select c from Customer c
where c.status = :status
~~~

Sort by a unique key:

~~~sql
select c from Customer c
where c.status = :status
order by c.id
~~~

If sorting by creation time where multiple rows can share the same timestamp, add the primary key as a tie-breaker:

~~~sql
select c from Customer c
where c.status = :status
order by c.createdAt, c.id
~~~

An `ORDER BY` on a non-unique column leaves relative ordering among ties undefined. Use composite ordering to establish a stable total order.

## 9. Offset paging vs. keyset pagination

`JpaPagingItemReader` paginates using `offset`/`firstResult`. It is not keyset pagination anchored on the last-seen key value.

Offset pagination:

~~~sql
select c
from Customer c
where c.status = :status
order by c.id
~~~

The reader fetches pages by starting position and item count. If a row before the offset is deleted, subsequent rows shift position.

Keyset pagination uses a predicate based on the last key:

~~~sql
select c
from Customer c
where c.status = :status
  and c.id > :lastSeenId
order by c.id
~~~

Keyset pagination is generally more stable and efficient at deep positions in large datasets, though it requires a custom reader/query managing the last key and its own checkpoint. Never describe `JpaPagingItemReader` as automatically performing keyset pagination.

If source data mutates heavily during job execution or across restarts, consider a custom keyset reader, a staging table, or an appropriate snapshot.

## 10. Impact of inserts/deletes while a job runs

Suppose a query returns customers by ID:

~~~text
Initially:
ID 10, 20, 30, 40, 50, 60

Reader committed up to item 3:
ID 10, 20, 30 [checkpoint], 40, 50, 60

While the job is stopped, ID 20 is deleted:
ID 10, 30, 40, 50, 60

Restart at offset 3:
Next position may be ID 50
ID 40 risks being skipped
~~~

Similarly, if a new row is inserted before the saved offset, the reader may re-read an already-processed row or skip an unprocessed one.

`ORDER BY` does not prevent this issue. `ORDER BY` determines the ordering of the result set at query execution time; it does not freeze set membership across two separate executions.

## 11. Stabilizing the dataset with a batch ID or cutoff

A practical approach is fixing the data scope as soon as the job begins:

- Use a `sourceBatchId` to read only rows belonging to a closed batch.
- Use `businessDate` to bound data by period.
- Use a cutoff timestamp captured once at launch.
- Use a high-water mark when the source key increases monotonically and safely.
- Use an immutable staging table for workloads requiring long-lived restartability.

Example query:

~~~java
.queryString("""
    select c
    from Customer c
    where c.importBatchId = :batchId
      and c.id <= :maxId
    order by c.id
    """)
~~~

`batchId` and `maxId` must stay unchanged in `JobParameters` or the execution context. When restarting the same `JobInstance`, do not recompute a fresh `maxId` if the goal is resuming the exact initial dataset.

A high-water mark only caps the upper bound of the key. It does not prevent deletes or updates to existing rows, nor does it solve non-monotonic ID generation. Understand how the source system creates and mutates records.

## 12. JobParameters and query parameters must stay consistent

If the query depends on status, tenant, or business date, those values directly define the result set. They must remain identical across restarts.

Example:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("tenantCustomerReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.tenantId = :tenantId
              and c.businessDate = :businessDate
            order by c.id
            """)
        .parameterValues(Map.of(
            "tenantId", tenantId,
            "businessDate", LocalDate.parse(businessDate)
        ))
        .pageSize(250)
        .saveState(true)
        .build();
}
~~~

On restart, supply the exact same identifying `JobParameters`. If `tenantId` or `businessDate` changes, that is a different logical run and should be a distinct `JobInstance`.

`@StepScope` creates the reader within the `StepExecution` context so it can resolve `JobParameters`. It does not save checkpoints by itself; `saveState` and `ExecutionContext` handle that.

## 13. EntityManager lifecycle of JpaPagingItemReader

`JpaPagingItemReader` creates and manages an `EntityManager` for executing queries. The `EntityManager` opens during the reader's lifecycle and closes when the reader finishes. The reader fetches a page and clears the persistence context to avoid retaining all read entities in memory.

An important consequence is that returned entities are typically detached after a page is read. The reader's `EntityManager` is not a persistence context that processors or writers can rely on for automatic dirty checking and change flushing.

If the processor modifies an entity:

~~~java
@Override
public Customer process(Customer customer) {
    customer.setStatus("PROCESSED");
    return customer;
}
~~~

changes on a detached object are not automatically saved to the database just because the entity has a setter. The writer must perform an explicit persist/merge/update in its own persistence context or use an appropriate JDBC/JPA writer.

Do not hold references to entities expecting them to stay managed after the reader moves to the next page. Treat each item as a data object returned from the reader.

## 14. Lazy loading and detached entities

Because entities detach after each page, accessing lazy associations later can throw `LazyInitializationException`:

~~~java
Customer customer = reader.read();
customer.getOrders().size(); // may fail if orders is LAZY
~~~

Ways to handle this:

- Use JPQL fetch joins for relationships genuinely needed in the batch.
- Use an `EntityGraph` or appropriate query to pre-fetch required data.
- Use a DTO projection carrying only required fields.
- Enrich data through a transactional service using batched lookups instead of per-item queries.
- Avoid casually touching lazy associations inside the processor.

Fetch join example:

~~~sql
select distinct c
from Customer c
left join fetch c.address
where c.status = :status
order by c.id
~~~

Do not fetch-join a large collection in a paginated query without understanding the impact. Joining collections multiplies result rows and can break pagination or degrade performance depending on the JPA provider. For collections, consider two-step queries or DTO projections.

## 15. Transactions of JpaPagingItemReader

`JpaPagingItemReader` manages page reads using its own `EntityManager`. By default, the reader runs page queries in its own read transaction and commits after fetching the page; this transaction must not be confused with the chunk transaction managed by the step.

The step still opens its own transaction per chunk, covering the processor, writer, and metadata updates configured via `JobRepository`/transaction manager. One page may be read before its items are committed across chunks.

Example with page size 200 and chunk size 50:

~~~text
JpaPagingItemReader loads page 1: 200 items
  |
  +-- Chunk 1: items 1-50 -> step transaction commits
  +-- Chunk 2: items 51-100 -> step transaction commits
  +-- Chunk 3: items 101-150 -> step transaction rolls back
  +-- Chunk 4: not yet processed
~~~

The reader may have already loaded the entire page in its read transaction, yet the step checkpoint advances only with committed chunks. On restart, the reader restores the checkpointed item count and re-queries the page containing the next position.

Do not assume the JPA reader's read transaction and the step's write transaction are always one and the same transaction. If you need a consistent snapshot across the entire job duration, design database isolation/snapshots and transaction managers appropriately; a paging reader alone does not guarantee a job-wide snapshot.

## 16. Page size and chunk size

These two parameters govern different mechanisms:

| Parameter | Meaning | Impact |
| --- | --- | --- |
| `pageSize` | Number of entities fetched in a single page query | Query count, memory usage, and paging cost |
| `chunk size` | Number of items processed before a single commit | Transaction duration, rollback scope, and checkpoint frequency |

Example:

~~~java
new JpaPagingItemReaderBuilder<Customer>()
    .name("customerJpaReader")
    .entityManagerFactory(entityManagerFactory)
    .queryString("select c from Customer c order by c.id")
    .pageSize(500)
    .saveState(true)
    .build();
~~~

~~~java
new StepBuilder("processCustomersStep", jobRepository)
    .<Customer, CustomerResult>chunk(100, transactionManager)
    .reader(customerReader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

The reader fetches 500 entities per page, while the step commits in chunks of 100 items. One page can serve multiple chunks.

A large page size reduces query count but increases memory usage and can lengthen page read transactions. A large chunk size reduces commit overhead but increases lock hold time and rollback scope. Tune both via benchmarks and database observation.

## 17. Changing page size between restarts

Item-counting reader checkpoints track the count of items read. On restart, the reader recalculates the page and intra-page offset using the current page size.

Changing page size does not inherently invalidate the item-count checkpoint, yet it alters paging boundaries, query counts, memory footprint, and restart time. It also complicates diagnosing older executions if queries or datasets changed at the same time.

For jobs requiring reliable restarts, keep `pageSize` and reader settings consistent across runs. If configuration changes are necessary, test restarting an execution created by the previous version and verify there are no duplicate or missing items.

Do not assume every page size change is safe merely because checkpoints store item counts. The essential invariants remain an identical dataset and identical ordering.

## 18. Changing query or ordering between restarts

Checkpoints store position, not the query text or a snapshot of results. The following changes can make old checkpoints incompatible:

- Changing `WHERE` predicates.
- Changing parameter values.
- Changing `ORDER BY` or tie-breaker ordering.
- Adding/removing joins that alter row counts.
- Changing fetch strategies in ways that produce duplicate rows.
- Changing mappings or filters that drop items at different phases.
- Changing the reader name or state key.

If you must change a query while an old `JobInstance` may still restart, preserve the old query version or provide a migration/reprocessing plan. One pattern is storing a query or schema version in `JobParameters` or the execution context and selecting the matching reader for that version.

Never silently alter a query and restart an old execution expecting the checkpoint to retain the same meaning.

## 19. Entity state and writer on restart

`JpaPagingItemReader` returns detached entities. If the processor modifies an entity, the writer must persist it using the writer's own transaction and persistence context.

Example JPA writer merging entities:

~~~java
public class CustomerJpaWriter implements ItemWriter<Customer> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            entityManager.merge(customer);
        }
    }
}
~~~

This is a conceptual example; in Spring Batch, ensure the injected/delegated `EntityManager` matches the transaction scope and the writer's persistence context joins the chunk transaction. You can use a repository or transactional service instead of managing `EntityManager` manually.

`merge` returns a managed instance; the passed-in object may remain detached. If subsequent steps need a managed entity, use the object returned by `merge` or reload within the corresponding transaction.

Restart re-reads entities from the database; it does not restore Java objects mutated by a processor before the process stopped. Any state that must survive a restart must be persisted durably or recomputable from source data.

## 20. Do not use entity objects as checkpoints

Never store read entities inside `JobExecutionContext` or `StepExecutionContext` to resume processing. Entities may:

- Not be serializable.
- Contain JPA provider proxies or lazy associations.
- Carry detached state or proxies tied to a closed `EntityManager`.
- Diverge from database state after being saved.
- Bloat metadata payloads severely.

Checkpoints should be stable positions or keys, not full object graphs. With `JpaPagingItemReader`, let the reader manage item counts. With a custom keyset reader, store a serializable last-processed key or composite key.

## 21. Mutating data and isolation levels

A page-reading transaction does not necessarily hold a snapshot for the entire job. When the reader advances to a new page, the next query can see newer committed data depending on isolation level and database engine.

For example, a row with status `READY` changes to `DONE` mid-job and disappears from the query. Another row changes from `DONE` to `READY` and enters the result set on a later page. When changes occur before or after the offset, the reader can miss or duplicate items.

Options:

- Snapshot source IDs into a staging table before processing.
- Stamp batch membership and query only rows belonging to that batch.
- Use an appropriate cutoff or high-water mark.
- Use database-supported snapshot isolation if the job can safely hold the snapshot long enough.
- Use a keyset reader to avoid certain offset-shift anomalies.

Do not raise isolation levels casually. Long-running snapshots retain row versions and create database pressure. Weigh job duration, write workload, and database capabilities.

## 22. Restarting when queries involve joins

JPQL joins can alter the number of rows the reader paginates over:

~~~sql
select c
from Customer c
join c.orders o
where o.status = :orderStatus
order by c.id
~~~

If a customer has multiple matching orders, the query may return that customer multiple times. Use `distinct` when appropriate:

~~~sql
select distinct c
from Customer c
join c.orders o
where o.status = :orderStatus
order by c.id
~~~

However, `distinct` combined with collection fetch joins and pagination may not be handled as desired by the JPA provider. Some providers fall back to in-memory pagination or emit warnings. Verify generated SQL and results on your production provider and database.

A more stable approach is paginating by root entity ID first, then fetching required details for that batch of IDs. For large aggregates, a custom reader or DTO query is often cleaner.

## 23. Reader name, step name, and deployment compatibility

A restart may occur after a new application version has been deployed. In that case, new code must interpret metadata written by old executions.

Changes to review carefully:

- Reader name or step name.
- Query and parameter semantics.
- Sort order.
- Page size and fetch behavior.
- Entity mappings and database schema.
- State serialization format.
- Spring Batch or JPA provider version upgrades.

Not every change breaks checkpoints, but a change can cause the reader to query a different dataset or look up a different state key. Inventory `FAILED` and `STOPPED` executions before deploying and decide whether new code needs to restart them.

If compatibility cannot be preserved, pick an explicit strategy: keep the old version for old executions, migrate metadata in a controlled manner, or mark old executions for business reprocessing under a new `JobInstance`.

## 24. @StepScope and reader instances on restart

`@StepScope` creates a target bean scoped to `StepExecution`. This is useful when query parameters come from `JobParameters`:

~~~java
@Bean
@StepScope
JpaPagingItemReader<Customer> reader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new JpaPagingItemReaderBuilder<Customer>()
        .name("tenantCustomerReader")
        .entityManagerFactory(entityManagerFactory)
        .queryString("""
            select c
            from Customer c
            where c.tenantId = :tenantId
            order by c.id
            """)
        .parameterValues(Map.of("tenantId", tenantId))
        .pageSize(200)
        .saveState(true)
        .build();
}
~~~

On restart, Spring Batch instantiates a target reader for the new `StepExecution` and calls `open` with the persisted execution context. Runtime fields from the previous reader do not survive a process restart; the checkpoint in `JobRepository` is the recovery source.

Never store page or item counts in `static` fields. Concurrent jobs would overwrite each other's state. Never share a single stateful reader instance across independent step executions.

## 25. Multi-threaded steps and JpaPagingItemReader

`JpaPagingItemReader` holds mutable page and read-position state, so a single instance should not normally be shared across threads calling `read()` concurrently. To parallelize, choose an appropriate model:

- Partitioning: each partition has its own reader with its own data range.
- Synchronized reader: guards reads, though it may limit throughput.
- Custom thread-safe reader: manages partitions/keys and checkpoints explicitly.

With partitioning, each worker should receive a distinct ID range or batch key, its own query predicate, and its own reader name/state key. On restart, each partition restores its own checkpoint.

Never merely set `saveState(false)` to dodge concurrency issues if the job still requires restarts. Disabling state forfeits default recovery; you would need an alternative checkpointing mechanism if business requirements still demand restartability.

## 26. Designing restartable partitions

Example partitioning customers by ID range:

~~~text
Partition 1: id 1 - 100000
Partition 2: id 100001 - 200000
Partition 3: id 200001 - 300000
~~~

Each partition has its own reader:

~~~sql
select c
from Customer c
where c.id between :minId and :maxId
order by c.id
~~~

`minId` and `maxId` bounds must be determined and persisted durably for that logical run. On restart, each partition reuses the exact same bounds and its own checkpoint.

Never allow overlapping partition ranges when each customer must be processed only once. When using hash partitioning, keep the hash function and partition count fixed across the `JobInstance`'s restart lifecycle.

## 27. Testing restarts with JpaPagingItemReader

Test restarts against a real database and `JobRepository` whose state persists between two launches. A basic test scenario:

1. Seed 10 customers with ascending IDs and status `READY`.
2. Configure `JpaPagingItemReader` with `ORDER BY id`, page size 4, and chunk size 2.
3. Have the writer commit the first chunk successfully.
4. Intentionally fail the writer on a later chunk so the step transitions to `FAILED`.
5. Verify the committed chunk's checkpoint is persisted.
6. Restart the same `JobInstance` with the exact same identifying parameters.
7. Verify the reader resumes after the checkpoint and ultimately processes all customers.

Key assertions:

- The first `JobExecution` has status `FAILED`.
- The restarted `JobExecution` belongs to the same `JobInstance`.
- The new execution finishes `COMPLETED`.
- Every expected business key appears in the destination.
- No duplicates exist when the destination enforces a unique constraint on source keys.
- Items from the rolled-back chunk are reprocessed.

Do not assert job status alone. Query the target table and compare its business keys against the expected source set.

## 28. Example fail-once writer in a restart test

You can create a test writer that throws an exception on a specific invocation:

~~~java
public class FailOnceCustomerWriter implements ItemWriter<Customer> {

    private final CustomerRepository repository;
    private final AtomicBoolean shouldFail = new AtomicBoolean(true);

    public FailOnceCustomerWriter(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        if (shouldFail.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated writer failure");
        }

        repository.saveAll(chunk.getItems());
    }
}
~~~

This is an illustrative fixture. Position the failure after at least one chunk has committed; otherwise the test only demonstrates restarting from the start. To test across a real process restart, the fail-once trigger must also live outside process memory or in durable data, not just an in-memory `AtomicBoolean`.

Within a single-process test, `AtomicBoolean` simulates a one-time failure between two launches. It does not simulate a JVM kill-and-restart because the boolean state is recreated on startup.

## 29. JobRepository must persist state durably

Restarting across process restarts requires a durable `JobRepository`. If metadata lives only in memory, `JobExecution` and `ExecutionContext` are lost when the JVM stops.

For integration tests:

- Use the Spring Batch database schema or an appropriate persistent repository.
- Retain `JobRepository` data between the failed launch and the restart.
- Do not wipe metadata between the two launches.
- Supply the exact same identifying parameters.
- Verify `JobExplorer` can read the previous job and step executions.

In-memory repositories can work for unit tests or same-process tests, but they do not prove restartability after an actual process shutdown.

## 30. Do not wrap restart tests in an outer transaction

If a test method is annotated with `@Transactional` and the test transaction rolls back at the end, it can mask chunk transaction boundaries or prevent fixtures and metadata from persisting between the two launches.

An easily observable test sequence:

1. Seed fixtures and commit before launching the job.
2. Launch the job and let the step manage its own chunk transactions.
3. Inspect `JobExecution`/`StepExecution` after the first run.
4. Restart the same `JobInstance`.
5. Inspect target tables and execution metadata.
6. Clean up fixture data in a dedicated teardown step.

If tests need rollback for data isolation, design separate transaction cleanup and ensure metadata/checkpoints are never rolled back before the restart launch.

## 31. Inspecting execution metadata

`JobExplorer` lets you inspect `JobExecution` and `StepExecution`:

~~~java
JobExecution previousExecution =
    jobExplorer.getJobExecution(previousExecutionId);

assertThat(previousExecution).isNotNull();
assertThat(previousExecution.getStatus())
    .isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = previousExecution.getStepExecutions()
    .stream()
    .filter(step -> step.getStepName().equals("processCustomersStep"))
    .findFirst()
    .orElseThrow();
~~~

You can verify that the execution context exists and reader state was stored. However, internal key names used by `JpaPagingItemReader` may change across versions; never write production logic coupled to those internal key names.

Data behavior is the most important assertion: the reader resumes from the checkpoint without skipping items or duplicating processing outside designed semantics.

## 32. Multiple datasources and transaction managers

A batch job may read entities from a source database, write output to a target database, and store metadata in yet another datasource. Clarify which transaction manager governs each resource.

If business data commits while checkpoint metadata fails to commit, a restart can re-read already-written items. If checkpoint metadata commits while business writes fail to commit, the reader can skip unwritten items.

Options:

- Share the same transaction manager/database for business writes and batch metadata when feasible.
- Use distributed transactions when true atomic commits are mandatory and operational complexity is acceptable.
- Design idempotent writers with unique keys or upserts.
- Use outbox/inbox or staging tables to reconcile state.
- Persist operation IDs to recognize already-applied operations.

`JpaPagingItemReader` does not solve cross-datasource consistency. It only saves and restores the read position.

## 33. Idempotency on restart

Because items from an uncommitted chunk can be re-read, writers must handle reprocessing the same item without corrupting state.

Example idempotent status update:

~~~sql
update customer
set status = 'PROCESSED'
where customer_id = :customerId
~~~

This is normally idempotent when free of secondary side effects.

Conversely, an additive balance update:

~~~sql
update account
set balance = balance + :amount
where account_id = :accountId
~~~

is not idempotent if re-executed. It requires an operation ID, deduplication table, or ledger recording applied transactions.

If the processor emits events or calls APIs, attach a stable idempotency key derived from the batch/item. Never generate a fresh random key on each retry or restart.

## 34. Skip, retry, and restart with JPA readers

Restart, retry, and skip address different problems:

| Mechanism | Goal | Example |
| --- | --- | --- |
| Retry | Re-attempt transient errors within the current execution | Deadlock during writer update |
| Skip | Bypass invalid items per business policy | Customer missing required code |
| Restart | Resume a `JobInstance` after an execution stops or fails | JVM shutdown after committed chunks |

JPQL syntax errors, entity mapping bugs, or database schema mismatches are configuration/deployment defects and should not be broadly skipped. Single-item data errors can be handled in the processor and skipped if business rules allow.

If a reader query fails due to a transient datasource issue, retrying may fit depending on the actual exception. If the query has a syntax error, retrying will not fix the root cause.

## 35. Common pitfalls when restarting JPA database items

**Query without ORDER BY:** the database does not guarantee result order. Use deterministic sorting on a unique key.

**Non-unique ORDER BY:** rows sharing the same sort value can reorder. Add the primary key as a tie-breaker.

**Source mutating between runs:** offsets can shift and cause duplicates or skipped items. Freeze batch membership or use an appropriate snapshot/keyset.

**Changing identifying JobParameters:** creates a new `JobInstance` instead of reusing the old checkpoint. Reuse the exact parameters on restart.

**Generating a new run.id on restart:** creates a new instance instead of resuming the failed execution. Increment run IDs only for new logical runs.

**Failing to enable saveState:** the reader saves no checkpoint. Enable state saving when restartability is required.

**Renaming the reader:** execution context keys may change. Keep names stable and check deployment compatibility.

**Assuming JpaPagingItemReader uses keyset pagination:** the reader paginates by offset/item count. If keyset is needed, implement a dedicated reader and checkpoint the last key.

**Assuming entities stay managed after a page is cleared:** entities may be detached. Merge or update via the writer's persistence context when persisting changes.

**Accessing lazy associations after detachment:** can throw `LazyInitializationException`. Pre-fetch, use projections, or enrich in a controlled service.

**Confusing the page-read transaction with the chunk transaction:** reader and step can use different transactions. Understand resources and transaction managers explicitly.

**Assuming page size equals chunk size:** the two settings control different boundaries. Choose and benchmark them independently.

**Sharing a stateful reader across multiple threads:** pages and item counts can corrupt each other. Use separate partitions or a thread-safe reader model.

**Assuming restart guarantees exactly-once:** failure windows and multiple datasources can still cause repeated side effects. Enforce idempotency.

**Testing only in-memory:** does not verify restart across process restarts. Use a durable `JobRepository` in integration tests.

## 36. Production workflow for designing restarts with JPA

First, define the target entity set and make it reproducible. Use `JpaPagingItemReader` with JPQL containing `ORDER BY` on a unique key; stabilize `JobParameters` and batch membership. If rows can be inserted or deleted before the offset during execution or restarts, consider a staging snapshot or custom keyset reader.

Next, assign a stable reader name, enable `saveState`, and back `JobRepository` with a durable database. Use `@StepScope` when the query binds parameters from `JobParameters`. Understand that the reader restores via item count/page offset and returned entities may be detached after the reader clears its persistence context. The writer must merge or update within an appropriate transaction to save changes.

Finally, test by committing at least one chunk, intentionally failing a subsequent chunk, and restarting the same `JobInstance`. Verify target data is complete with no duplicates, the reader resumes past the checkpoint, query/order stayed unchanged, and the transaction manager covers the right datasource. Also test source data mutations, version conflicts, lazy loading, and post-deployment restarts if the job must support them.

Restarting with database items in Spring Batch JPA relies on durable checkpoints and a reproducible query. `JpaPagingItemReader` saves read positions by item count and paginates by offset, so query ordering and the source dataset must remain stable. When `JobInstance` parameters, reader identity, queries, `EntityManager` lifecycles, and transaction boundaries are cleanly designed, a job can resume after failure without reprocessing the entire dataset. Idempotent writers and integration tests backed by a durable `JobRepository` protect data whenever items are re-read during retries or restarts.
