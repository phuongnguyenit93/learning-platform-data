# JpaPagingItemReader

In Spring Batch, `JpaPagingItemReader<T>` reads data from a database through JPA and divides the query results into pages. The reader executes a JPQL query, uses `setFirstResult` and `setMaxResults` to fetch each page, and maps the results into items for a chunk step.

This reader is suitable when the application already uses a JPA entity model, wants to read data with JPQL, or needs to return DTOs from constructor expressions. It helps process large datasets incrementally rather than loading the entire result set into a single `List`.

When using `JpaPagingItemReader`, distinguish three units that are often confused:

- **Page size:** the number of results the reader requests in a single query.
- **Chunk size:** the number of items Spring Batch processes within a single chunk transaction before committing.
- **JDBC fetch size:** a hint to the JDBC driver for how many rows to fetch per database round trip; this is not the page size of the JPA reader.

The page query and the chunk transaction have separate lifecycles. The reader also manages an `EntityManager` and its persistence context; entities may become detached after a page is read. Therefore, choosing the page size, query ordering, transaction strategy, and handling of lazy associations directly affects performance, consistency, and restartability.

## What is JpaPagingItemReader?

`JpaPagingItemReader<T>` belongs to the `org.springframework.batch.item.database` package. It implements a paging reader and uses `EntityManagerFactory` to create an `EntityManager` for querying.

For each page, the reader follows this general flow:

1. Compute the starting position of the current page.
2. Create the JPQL query.
3. Bind parameters and query hints if configured.
4. Call `setFirstResult(...)` and `setMaxResults(...)`.
5. Execute the query to retrieve the page of results.
6. Put the results into an internal buffer so `read()` returns one item at a time.
7. Clear the persistence context according to the reader's lifecycle to avoid retaining too many managed entities.

```text
Job / Step
    |
    v
JpaPagingItemReader.read()
    |
    +--> Page 0: JPQL + firstResult=0, maxResults=pageSize
    |       |
    |       +--> item 1, item 2, ... item N
    |
    +--> Page 1: JPQL + firstResult=N, maxResults=pageSize
    |       |
    |       +--> item N+1, ... item 2N
    |
    +--> Page 2: ...
    |
    v
Chunk processor / writer
```

This is a page-based reader, not a cursor holding a single open `ResultSet`. When moving to the next page, the reader executes a new query with the corresponding offset.

## When should you use JpaPagingItemReader?

This reader is a good fit when:

- The application uses JPA and wants to read via JPQL.
- Data is represented as entities or DTO projections.
- You want to process one page at a time to bound memory usage.
- The query requires parameters from `JobParameters` or `ExecutionContext`.
- The dataset has a deterministic order and can resume by page/offset on restart.

Consider another reader when:

- You need a continuously open JDBC cursor and the database/driver supports it well: see `JdbcCursorItemReader`.
- You need SQL-based paging, sort keys, or database-specific query providers: see `JdbcPagingItemReader`.
- The dataset mutates continuously and offset pagination cannot guarantee accurate resumption: consider keyset pagination or snapshotting/staging.
- You need to read a set of objects already loaded in memory: use an appropriate collection-based reader, keeping memory limits in mind.

No single reader is optimal for every database. Choose based on query plan, JPA provider, JDBC driver, page size, and consistency requirements.

## Basic configuration

Suppose the application has an entity:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    private String fullName;

    private BigDecimal balance;

    private boolean active;

    // Constructors, getters, and other mappings
}
```

The reader uses `JpaPagingItemReaderBuilder`:

```java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['activeOnly']}") Boolean activeOnly) {

    return new JpaPagingItemReaderBuilder<Customer>()
            .name("customerReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select c
                    from Customer c
                    where c.active = :active
                    order by c.id
                    """)
            .parameterValues(Map.of("active", activeOnly))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Key configuration options:

| Option | Meaning |
| --- | --- |
| `name` | Reader name used to key state in `ExecutionContext` |
| `entityManagerFactory` | Factory used to create the `EntityManager` |
| `queryString` | JPQL query executed for each page |
| `parameterValues` | Map of parameter names to bound values |
| `pageSize` | Maximum number of items the reader requests per page |
| `saveState` | Enables or disables saving state to support restart |

This example assumes `activeOnly` always has a value. If a parameter can be null, `Map.of` does not allow null values; create a mutable map or provide an explicit default. Parameter data types must be compatible with the entity attribute types and the JPQL provider.

### Configuring with setters instead of the builder

You can configure the reader using JavaBean style:

```java
JpaPagingItemReader<Customer> reader = new JpaPagingItemReader<>();
reader.setName("customerReader");
reader.setEntityManagerFactory(entityManagerFactory);
reader.setQueryString("select c from Customer c order by c.id");
reader.setPageSize(500);
reader.setSaveState(true);
reader.afterPropertiesSet();
```

The builder is usually easier to read and keeps configuration values in one place. Either way, the reader requires an `EntityManagerFactory`, a valid query, an appropriate page size, and a stable name if restart is needed.

## JPQL queries and parameter binding

`JpaPagingItemReader`'s `queryString` is JPQL, not raw SQL. JPQL operates on entity names and entity attributes rather than directly referencing table and column names like SQL.

SQL example:

```sql
SELECT customer_id, full_name
FROM customer
WHERE active = true
ORDER BY customer_id
```

Equivalent JPQL:

```java
select c
from Customer c
where c.active = true
order by c.id
```

`Customer` is the entity name; `active` and `id` are mapped Java properties. The persistence provider translates JPQL into SQL matching the dialect.

### Named parameters

Use named parameters to keep queries readable:

```java
.queryString("""
        select c
        from Customer c
        where c.active = :active
          and c.createdAt < :cutoff
        order by c.id
        """)
.parameterValues(Map.of(
        "active", true,
        "cutoff", cutoff))
```

Keys in `parameterValues` do not include the leading `:`. Each key must match the parameter name in the JPQL query.

### Getting parameters from JobParameters

If the query depends on a business date or state passed at launch time, you can use `@StepScope`:

```java
@Bean
@StepScope
JpaPagingItemReader<Order> orderReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate) {

    return new JpaPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from Order o
                    where o.businessDate = :businessDate
                    order by o.id
                    """)
            .parameterValues(Map.of("businessDate", businessDate))
            .pageSize(300)
            .build();
}
```

`@StepScope` defers creating the target reader until a `StepExecution` exists, allowing job parameters to be resolved for that specific run. If the value is a `String`, parse and validate it before passing it into the query.

### Parameters are not dynamic column names

JPA parameter binding is for values, not for substituting entity names, property names, or `ORDER BY` clauses.

Do not write:

```java
where c.:fieldName = :value
```

If you need dynamic sort fields, use an allowlist in code to assemble one of the known JPQL expressions. Never concatenate untrusted input directly into the query string, as it can lead to query injection or invalid queries.

## DTO projections instead of reading entities

`JpaPagingItemReader<T>` does not require `T` to be an entity. JPQL can use a constructor expression to return a DTO:

```java
public record CustomerSummary(
        Long id,
        String fullName,
        BigDecimal balance) {
}
```

Query:

```java
.queryString("""
        select new com.example.batch.CustomerSummary(
            c.id, c.fullName, c.balance)
        from Customer c
        where c.active = true
        order by c.id
        """)
```

With a DTO projection, the reader returns selected data objects instead of managed entities. This is useful when the processor only needs a subset of fields, does not need lazy relationships, or does not need to update the entity.

The class name in a constructor expression generally must be a fully qualified class name. The constructor must match the argument count and types expected by the query/provider.

### When to choose entities vs. DTOs?

| Need | Choice |
| --- | --- |
| Processor needs the domain entity and intentionally fetched relationships | Entity |
| Only a few columns are needed for calculations or writing to another system | DTO projection |
| Want to reduce persistence context overhead and avoid out-of-scope lazy loading | DTO projection |
| Need to invoke domain methods on the entity | Entity, with explicit detached-state management |
| Only reporting or summarization is needed | DTO projection is usually suitable |

DTO projections do not automatically fix slow queries; you still need appropriate indexes, query plans, and page sizes.

## Page size and chunk size

Page size and chunk size serve different purposes. Page size controls how many results the JPA reader fetches in a single query; chunk size controls how many items are processed in a single chunk transaction.

For example:

```java
.pageSize(500)
```

and:

```java
.chunk(100, transactionManager)
```

The reader may load 500 results for a page into its buffer, while the step processes and commits every 100 items. One page can feed multiple chunks; a single chunk can also cross a boundary between two pages.

| Page size | Chunk size | Likely effect |
| ---: | ---: | --- |
| 100 | 100 | Each page typically corresponds to one chunk if there is no filtering and before EOF |
| 500 | 100 | One page can supply roughly 5 chunks |
| 100 | 250 | One chunk can pull items across multiple pages |
| 1000 | 50 | The reader may hold a buffer much larger than the number of items per transaction |

Page size does not have to equal chunk size. Choose page size based on query cost, memory, and provider behavior; choose chunk size based on transaction duration, writer characteristics, and commit/rollback requirements.

### Page size too small

A small page size causes the reader to execute more queries. If database latency is high, the round-trip and query setup overhead can be significant. However, small pages also limit the number of objects held in the buffer and can reduce memory consumption.

### Page size too large

A large page size reduces the number of queries but increases the number of objects loaded at once. It can increase heap usage, page generation time, and the amount of work reprocessed if a page query fails.

### How to choose page size

Start with a moderate value, such as 100–500, and benchmark on realistic data. Monitor:

- Execution time per page query.
- Total number of queries for the job.
- Heap usage and garbage collection.
- Chunk transaction duration.
- Processor and writer throughput.
- Actual row count returned per page.

Do not increase page size in an attempt to reduce transaction count. Page size does not change chunk commit boundaries.

## Persistence context and EntityManager lifecycle

A JPA `EntityManager` manages a persistence context where loaded entities can reside in the managed state. Holding too many entities in a long-lived persistence context increases memory usage and dirty-checking overhead.

`JpaPagingItemReader` manages its `EntityManager` within the `open`/`close` lifecycle. The reader clears the persistence context per page to avoid keeping all read entities in the first-level cache. As a result, returned entities may become detached after the page is read/cleared.

This has important consequences:

- Do not assume entities from the reader remain managed when used by the processor or writer.
- Mutating fields on a detached entity will not automatically flush to the database.
- Unloaded lazy associations may not be accessible after the entity is detached.
- If updates are needed, use a writer/service within a transaction to explicitly merge/update, or load required data before detachment.
- DTO projections avoid many issues related to managed/detached entity state.

### Entity states

| State | Meaning |
| --- | --- |
| New / transient | Object has not been persisted and is not managed by any persistence context |
| Managed | Entity is currently managed by an `EntityManager`; changes may be dirty-checked |
| Detached | Entity was previously managed but is no longer associated with a persistence context |
| Removed | Entity is marked for deletion in the persistence context |

Once the persistence context is cleared, loaded entities become detached. If a processor modifies an entity and expects JPA to save it automatically simply because it came from a JPA reader, that will not happen.

### Updating detached entities

If an entity needs to be updated, one approach is to use `JpaItemWriter` or a transactional service to merge the entity. However, merge semantics copy state from the detached object into a managed instance; take care not to overwrite unloaded fields or fields modified by another transaction.

Another approach is a DTO projection carrying only the ID and necessary fields, with a writer or service executing an explicit update statement. For large batch updates, `JdbcBatchItemWriter` or a JPQL bulk update may be more suitable.

## Lazy loading and relationships

An entity may have `LAZY` associations, for example:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Department department;
```

If the reader clears the persistence context after each page, the returned entity may be detached while the association remains unloaded. A processor calling `customer.getDepartment().getName()` may encounter a `LazyInitializationException` depending on the provider/proxy and access timing.

Ways to handle this:

- Use a DTO projection to select the needed fields directly in the query.
- Use `JOIN FETCH` for to-one or other suitable associations.
- Use query hints or entity graphs supported by your JPA provider/API.
- Read the association within the persistence context scope if the reader design allows it, without relying on a persistence context extending beyond the reader lifecycle.
- Split loading of needed relationships into batched queries to avoid N+1.

Do not arbitrarily fetch-join collections in a paging query. Joining a collection causes a root entity to appear across multiple SQL rows; combined with pagination, this can force the provider to paginate in memory, return unexpected root counts, or emit warnings. For large collections, consider paging root IDs first and then loading child data in a separate query or using a DTO projection.

### N+1 queries

If every item accesses a lazy relationship, the provider may execute an extra query per item. With 10,000 customers, one page query plus thousands of secondary queries can make the job extremely slow.

To detect this:

- Enable SQL logging in test environments.
- Use Hibernate statistics or datasource metrics.
- Measure query counts per page and per item.
- Inspect execution plans of both primary and secondary queries.

To reduce N+1 queries, use DTO projections, appropriate fetch joins, entity graphs, or provider-specific batch fetching. Choose the approach based on cardinality and query plans rather than blindly fetch-joining every association.

## EntityManager transaction and chunk transaction

`JpaPagingItemReader` has a `transacted` option. In common versions, it defaults to `true`: the reader executes each page query within a reader-managed JPA transaction, independent of the transaction Spring Batch uses for the chunk. After fetching a page, the persistence context is cleared according to the reader lifecycle.

This means the page query does not automatically participate in the same transaction as the chunk's writer. For example:

```text
Step
 |
 +--> Reader page transaction
 |       SELECT page 1
 |       COMMIT page read
 |
 +--> Chunk transaction 1
 |       process items 1..100
 |       writer
 |       COMMIT
 |
 +--> Chunk transaction 2
 |       process items 101..200
 |       writer
 |       COMMIT
 |
 +--> Reader page transaction
         SELECT page 2
         COMMIT page read
```

This diagram illustrates logical boundaries; the exact interleaving of reader page prefetches relative to chunks depends on buffer/page size. The core point is that the page query transaction and the chunk transaction are two distinct mechanisms.

### The transacted option

`transacted` controls whether the reader uses its own transaction for reading a page per the `JpaPagingItemReader` API. Only change this option when you understand the persistence provider, transaction manager, and how the `EntityManager` is managed. Disabling it does not automatically ensure the query joins the chunk transaction; that depends on JPA configuration and how the entity manager is shared.

If you need consistency between the read query and chunk updates, design the transaction strategy at the database/JPA level and test it against your actual provider. Do not assume that sharing the same `EntityManagerFactory` means sharing the same `EntityManager` or the same transaction.

### Transaction manager for the step

A chunk step typically uses `JpaTransactionManager` when the business writer uses JPA on the same persistence unit, or a transaction manager matching the datasource/JPA configuration. For example:

```java
@Bean
JpaTransactionManager transactionManager(EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Step:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JpaPagingItemReader<Customer> customerReader,
        ItemProcessor<Customer, CustomerSummary> processor,
        ItemWriter<CustomerSummary> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, CustomerSummary>chunk(200, transactionManager)
            .reader(customerReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

If `JobRepository` and business data use different datasources/transaction managers, understand that metadata transactions and business output may not be atomic. A local transaction manager does not automatically create a distributed transaction across multiple resources.

## Isolation and data changing between pages

Because the reader queries page by page, page 0 and page 1 may be executed at different points in time. If the reader's transaction ends after each page, another transaction can modify data between two queries.

For example:

```text
Page 0: SELECT ... ORDER BY id LIMIT/OFFSET -> rows 1..100
Another transaction INSERTs a row with an id before the next offset position
Page 1: SELECT ... OFFSET 100 -> may shift position compared to the previous query
```

With offset pagination, inserts or deletes before the offset can cause a row to be read twice or skipped. Updating a column used in `WHERE` or `ORDER BY` can also shift a row's position or remove it from the result set.

This is not a Spring Batch-specific bug; it is an inherent characteristic of offset-based pagination over a changing dataset. If a job requires a consistent input set, define an explicit snapshot or watermark.

### Ways to keep the input set stable

Common approaches include:

- Choosing an immutable cutoff at launch, such as `createdAt < :cutoff`.
- Filtering by a `batchId` or `processingGroupId` assigned before the job runs.
- Creating a staging table holding the keys of the target records.
- Using snapshot isolation if supported by the database and appropriate for the transaction duration.
- Keeping the source data immutable throughout execution and restarts.

A time cutoff only helps if older records are not modified or deleted in ways that alter the result set. If you need a stronger snapshot, use staging or an appropriate database snapshot mechanism.

## ORDER BY and deterministic pagination

A paging query must have a deterministic `ORDER BY`. Never rely on the database's default ordering.

An insufficiently stable example:

```jpql
select o from Order o
where o.status = :status
order by o.createdAt
```

If multiple orders share the same `createdAt`, the database may return them in different orders across queries. Add a unique tie-breaker:

```jpql
select o from Order o
where o.status = :status
order by o.createdAt, o.id
```

`id` establishes a total order if it is a unique key. On restart, the same offset points to the same logical position only if both the dataset and the result ordering remain unchanged.

`ORDER BY` guarantees ordering, but it does not freeze the dataset by itself. Combine it with a cutoff, batch ID, or snapshot if data can change.

## Offset pagination and performance

JPA paging typically uses `setFirstResult(offset)` and `setMaxResults(pageSize)`. At deep pages, the database may have to scan and skip many rows before returning the requested page. Cost can grow with large offsets depending on the query plan, indexes, and database engine.

Example with page size 500:

| Page | First result (offset) | Max results |
| ---: | ---: | ---: |
| 0 | 0 | 500 |
| 1 | 500 | 500 |
| 2 | 1000 | 500 |
| 100 | 50000 | 500 |

With very large datasets, page 100 can cost more than the first page because the database must process/skip many rows. Measure the query plan rather than assuming every page has the same cost.

### Keyset pagination

Keyset pagination resumes from the last key value of the previous page instead of an offset:

```jpql
select o from Order o
where o.id > :lastSeenId
order by o.id
```

This is a conceptual example. For a composite sort key such as `(createdAt, id)`, the continuation predicate must compare both components in the proper order. Standard `JpaPagingItemReader` uses page/offset; if you need keyset pagination, you can use a custom `ItemReader`, query provider, or specialized reader designed to store the last-seen key in `ExecutionContext`.

Keyset pagination can be more efficient for very large datasets and is less susceptible to offset shift from inserts before the current position, though you still need defined semantics when rows are updated/deleted or sort keys change.

## Restart and ExecutionContext

`JpaPagingItemReader` is an `ItemStream` and can persist state to support restarts. When `saveState(true)` is enabled, the reader stores reading progress in `ExecutionContext` keyed by the reader's name. On restart, it restores the item/page position and resumes querying from the corresponding offset.

For reliable restarts, keep the following stable:

- The reader's `name`.
- The JPQL query and parameter values.
- `pageSize` and item mapping logic.
- `ORDER BY` ordering.
- The dataset returned by the query.
- Identifying `JobParameters` used for the same `JobInstance`.

If you change the query, filter, page size, or dataset between the initial run and a restart, the saved checkpoint may no longer point to the right item.

### Restart example

Suppose page size is 500 and the step committed 1,200 items before failing. On restart, the reader must restore progress corresponding to 1,200 items and resume from the next position based on saved state. The reader may re-read the page containing the checkpoint and skip already-processed items in that page according to its implementation; do not calculate offsets manually or edit `ExecutionContext` by hand.

If a transaction rolls back in the final chunk, the checkpoint should reflect only committed progress. Spring Batch coordinates reader state and chunk commits under the `ItemStream` contract. Do not manually write checkpoints from a processor or writer.

### Dataset changes between restarts

Offset pagination is particularly sensitive to inserts, deletes, and updates in the result set. If the first run's query returned 10,000 rows and on restart it returns 10,001 rows due to a new record before the offset, the resume position can shift. This can cause duplicate or missing items.

The solution is to stabilize the input set with a batch ID, cutoff, staging, or snapshot, and keep parameters and query semantics identical across restarts. Do not use the current wall-clock time directly inside JPQL if restarts must process the exact same dataset.

### saveState false

Disable `saveState` when the reader is used in scenarios that do not require restart or when parallel execution does not support shared state in the desired way. When disabled, do not expect the reader to restore its position after a failure.

If a step runs multiple threads or shares a reader across workers, evaluate thread-safety and state semantics carefully. It is generally better to create a dedicated reader per partition or step execution rather than sharing a mutable reader. Only use `saveState(false)` when you accept non-restartable reads or have an alternative checkpointing mechanism.

## EntityGraph, fetch join, and N+1

A paging query may load the root entity without loading its associations. If the processor accesses a lazy association, the provider may issue an extra query per item.

Example root query:

```jpql
select o from Order o
where o.status = :status
order by o.id
```

A processor reading `o.customer.name` may trigger N+1 queries if `customer` was not fetched. You can use an entity graph or fetch-join a to-one association where appropriate.

JPQL example:

```jpql
select o from Order o
join fetch o.customer
where o.status = :status
order by o.id
```

Fetch join retrieves `customer` in the same query. However, do not fetch-join collections in an ordinary paging query because joining multiplies root rows and can cause incorrect pagination or force the provider to paginate in memory.

If you need collections:

- Page the root entity IDs first.
- Query child records by the page's list of IDs.
- Group children into a DTO or map for the processor to consume.
- Or use controlled batch fetching or entity graphs according to your provider.

Do not treat `distinct` as an automatic cure-all for collection pagination issues; inspect the generated SQL and verify actual root entity counts.

## Query hints

JPA queries can receive hints through the reader's `hintValues`. Hints depend on the JPA provider or database; some hints affect caching, timeouts, fetch plans, or read-only behavior.

Conceptual example:

```java
.hintValues(Map.of(
        "jakarta.persistence.query.timeout", 30000))
```

Hint names and timeout units must match the JPA version and provider. Applications using older `javax.persistence` APIs may need the corresponding hint names for that version. Do not copy Hibernate or EclipseLink hints to another provider without verifying them.

Query hints do not replace proper indexes or JPQL tuning. Only add hints after understanding their effect and measuring the benefit.

## Entity lifecycle and writing data

An entity returned by the reader may already be detached after the page is read and the persistence context is cleared. Therefore, the processor can compute values from loaded fields, but should not assume dirty checking will automatically persist changes.

Example processor modifying an entity:

```java
@Bean
ItemProcessor<Customer, Customer> markReviewedProcessor() {
    return customer -> {
        customer.setReviewed(true);
        return customer;
    };
}
```

Modifying `reviewed` on a detached entity will not automatically be persisted just because the object came from `JpaPagingItemReader`. The writer must persist, merge, or update within an appropriate transaction.

If using `JpaItemWriter`, configure it to merge entities when updating detached instances according to the writer and provider semantics. If only a few columns need updating, consider a JDBC writer or explicit update query to avoid merging the entire entity graph.

Bulk JPQL updates can bypass the persistence context and will not automatically synchronize already-loaded entities. If you use bulk updates, understand cache/clear semantics and avoid letting stale entities overwrite newer data.

## Transactions when reading and writing the same data

A common pattern is reading entities page by page, processing them, and writing via JPA or JDBC. Determine which transaction manager governs the writer and which governs the page query.

Example:

```text
JpaPagingItemReader
   |
   +--> page query transaction (reader)
   |
   v
Chunk transaction (Spring Batch)
   |
   +--> processor
   +--> JpaItemWriter / JdbcBatchItemWriter
   +--> commit or rollback
```

If the reader queries and the writer updates the same table, a page query may run before all chunks from the previous page are committed. Changes from other transactions can affect subsequent pages. If the writer alters a column filtered by the reader, the dataset can shift and restarts become unsafe.

To avoid processing the same row multiple times or missing rows, you can:

- Claim the target rows using a `batch_id` or processing status in a separate preliminary step.
- Read from an immutable staging table.
- Use an appropriate cutoff or snapshot.
- Avoid mutating the source's sort key or filter key while the reader is paging.
- Write results to a separate target table and finalize statuses afterward.

A chunk transaction guarantees that changes participating in that transaction commit or roll back together. It does not freeze the result set across multiple page queries.

## Comparing JpaPagingItemReader, JdbcPagingItemReader, and JdbcCursorItemReader

| Criterion | `JpaPagingItemReader` | `JdbcPagingItemReader` | `JdbcCursorItemReader` |
| --- | --- | --- | --- |
| Query | JPQL | SQL via query provider | SQL with cursor/result set |
| Mapping | JPA entity or DTO projection | `RowMapper` | `RowMapper` |
| Read mechanism | Paging via first result/max results | Paging via sort key/query provider | Single cursor open for reader lifecycle |
| Dependencies | JPA provider and `EntityManagerFactory` | JDBC driver, database dialect/query provider | JDBC driver and cursor semantics |
| Persistence context | Yes, managed by the reader | No | No |
| Lazy associations | Potential concern | No JPA lazy proxies | No JPA lazy proxies |
| Restart | Page/item state and stable query | Page/sort key state | Cursor position state and stable query |
| Best suited for | JPA/JPQL domain applications | SQL paging with clear sort keys | Sequential reading over a cursor |

Choose `JpaPagingItemReader` when JPA mapping delivers real value. If you only read a few columns and write via JDBC, `JdbcPagingItemReader` can be simpler and carry less overhead. If the driver streams cursors well and the query result is stable, a cursor reader may fit better. Benchmark against a real database.

## Reader scope and thread safety

The reader holds page state, an `EntityManager`, and the current position. Do not share a single instance across multiple concurrent step executions or partitions.

When the query depends on `JobParameters` or `ExecutionContext`, declare `@StepScope` so a reader is created per step execution. With partitioning, each worker should have its own reader instance and isolated parameters/resources.

If using a multi-threaded step, check the reader's thread-safety contract in your Spring Batch version. Setting `saveState(false)` may be required in some multi-threaded models, which means the reader loses standard restart checkpointing. Do not use it as a blanket fix for race conditions; prefer partitioning with independent readers whenever possible.

Do not store an `EntityManager`, query, or entity proxy in static fields or singleton services. Let Spring Batch manage the reader lifecycle and persistence context.

## Common pitfalls

### Missing ORDER BY

Databases do not guarantee result order if a query lacks sorting. Page boundaries can shift between runs and restarts. Use `ORDER BY` on a unique key or a unique key combination.

### Non-unique ORDER BY

Multiple rows sharing the same sort value can change order. Add the primary key as a tie-breaker.

### Dataset mutating between pages

Inserts, deletes, or updates before the offset can cause duplicate or missing items. Use a batch ID, cutoff, staging table, or snapshot.

### Confusing page size with chunk size

Page size controls the query; chunk size controls the transaction. Choose them independently.

### Keeping entities managed too long

A large persistence context increases memory usage and dirty-checking overhead. The reader manages clearing per page; consider DTO projections for read-only needs.

### Mutating detached entities expecting dirty checking to save

Entities can be detached after a page. Use an explicit writer, merge, or update within a transaction.

### Accessing lazy associations after detachment

This can cause `LazyInitializationException` or unintended queries. Fetch needed data eagerly or use a DTO projection.

### Fetch-joining collections with pagination

Joining collections can multiply root rows and make pagination inaccurate or expensive. Page root IDs first, then load collections separately.

### N+1 queries

A processor accessing lazy associations per item triggers many queries. Measure SQL counts and use projections or appropriate fetch plans.

### Changing query or page size between restarts

Saved checkpoints may point to a different position. Keep the query, parameters, page size, and reader name stable.

### Assuming chunk transactions wrap page queries

The reader has its own transaction strategy for pages. Do not assume the `SELECT` and writer commit in the same transaction.

### Sharing one reader across multiple threads

`EntityManager` and page state are mutable. Create a separate reader per step/partition and verify thread-safety.

### Using JPQL parameters for field names

Parameters bind values only. Dynamic sort fields or entity names require an allowlist and controlled query construction.

## Testing JpaPagingItemReader

Include unit tests for query/mapping logic at the right level and integration tests against a real JPA provider and database. H2 is useful for fast feedback, but it does not always reproduce production pagination, isolation, and SQL dialect behavior.

### Testing paged reads

Create a fixture larger than one page, such as 12 customers with a page size of 5. Open the reader and verify:

- The reader returns all 12 items.
- Items follow the `ORDER BY` ordering.
- The final page contains fewer items than the page size.
- `read()` returns `null` after the last item.
- No items are duplicated or skipped during a normal run.

### Testing parameter binding

Launch the reader with various `JobParameters` values and verify the query returns only the matching subset. Test null/default values and date/time types. Never build parameters into the query string via concatenation.

### Testing DTO projections

Verify the constructor expression produces the expected DTOs, `BigDecimal` precision is preserved, and no unexpected lazy queries are emitted.

### Testing page size and chunk size

Run with page size smaller than, equal to, and greater than chunk size. Verify total item counts and chunk commit counts remain accurate; page queries must not be mistaken for transaction boundaries.

### Testing persistence context

After reading a page, verify that entities are detached according to the reader/provider lifecycle. If the processor needs associations, verify they are fetched before clearing or switch to a DTO projection.

### Testing restart

Have the step read and commit several chunks and then fail. Restart with the same identifying parameters, query, page size, and reader name. Verify there are no missing or duplicate items when the dataset is unchanged.

Next, modify the fixture between the initial run and restart by inserting or deleting a row before the offset. The test should demonstrate why the dataset must be stabilized or why the job should reject restarts if the manifest/version changed.

### Testing concurrent modification

In another transaction, insert, delete, or update rows located before the next page offset. Observe the outcome on a production-like database. Verify whether your cutoff or staging solution prevents changes from shifting pages.

### Testing fetch plans and N+1

Enable SQL statistics/logging in the test environment. Measure query counts while the processor accesses associations; verify that fetch joins, entity graphs, or projections actually reduce queries without breaking pagination.

### Testing transaction rollback

Have the writer throw an exception in a chunk and verify the chunk's changes roll back under the transaction manager. Check that reader restart/checkpointing resumes properly after a job restart; do not assume writer rollback re-runs the page query in the same transaction.

## Design principles

When using `JpaPagingItemReader`, clarify:

1. Should data be read as entities or DTO projections?
2. Does the JPQL query bind parameters using named parameters?
3. Does the query have a deterministic `ORDER BY` on a unique key?
4. Can the dataset change between pages or across restarts?
5. Is a cutoff, batch ID, staging table, or snapshot needed to stabilize the input?
6. Does the page size fit memory limits, query latency, and round-trip costs?
7. Does the chunk size fit transaction duration and writer behavior?
8. Will entities detach after a page, and does the processor access lazy associations?
9. Are there N+1 queries or collection fetch joins causing abnormal pagination?
10. Are page query transactions properly understood relative to chunk transactions?
11. Are the reader name, query, parameters, and page size stable across restarts?
12. Is the reader instance isolated per step/partition and concurrency-safe?
13. Do tests cover paging, mapping, restart, concurrent updates, transactions, and query counts?

For a typical JPA pipeline, start with `JpaPagingItemReaderBuilder`, JPQL with named parameters, an `ORDER BY` on a unique key, a moderate page size, and `saveState(true)`. Use a DTO projection if you only need part of the data; if using entities, understand that the persistence context is cleared and entities may be detached after a page. Treat the page query transaction as distinct from the chunk transaction according to reader configuration. Stabilize the dataset with a cutoff or staging so offset pagination does not drift across pages or restarts, and test on the actual production JPA provider and database.

## Key takeaways

`JpaPagingItemReader<T>` uses an `EntityManagerFactory` and JPQL to read results page by page via `setFirstResult`/`setMaxResults`. Page size controls the number of results per query; chunk size controls the step's transaction commits. The reader manages the `EntityManager` and clears the persistence context per page, so returned entities may be detached; DTO projections help avoid lazy loading and unnecessary dirty checking. In common configurations, page queries run in the reader's own transaction (`transacted=true`), not implicitly in the chunk writer's transaction. Use named parameters, `ORDER BY` with a unique key, keep queries and datasets stable across restarts, and enable `saveState`. Offset pagination is prone to duplicates or missing items when data changes between pages; use a cutoff, batch ID, staging/snapshot, or a keyset reader when needed. Choose page size based on memory and query cost, avoid collection fetch joins, watch for N+1 queries, and test restart, isolation, and rollback on a real JPA provider and database.
