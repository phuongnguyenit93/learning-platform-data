# Paging Reads and Stable Sorting

When reading millions of records from a database, querying the entire result set at once can consume excessive memory, hold cursors or connections open for too long, and make failure recovery difficult. Spring Batch provides `JdbcPagingItemReader<T>` to read data page by page. The reader executes multiple bounded queries, converts each row into an item, and saves checkpoints to support restart.

Paging is only reliable when data ordering is deterministic. If pages do not use the same stable sorting rule, a record can be duplicated or skipped at page boundaries, especially when the sort column is not unique or when data changes while the job is running. Therefore, designing the sort key is the core part of using `JdbcPagingItemReader`.

## 1. Why Read Page by Page?

Suppose the `orders` table has several million rows. A simple reading approach is running a single `SELECT` query that returns the entire result set. With large data volumes, this approach can:

- Produce a large result set and put pressure on application or driver memory.
- Hold cursors, statements, and connections open for a long time.
- Prolong transactions if all data is processed in one large unit.
- Make it difficult to resume from the processed position when the job fails.

Paging splits the data into small groups:

```text
Database table
      |
      v
Page 1: rows 1-500
      |
      v
Page 2: rows 501-1000
      |
      v
Page 3: rows 1001-1500
      |
     ...
      v
No more rows
```

`JdbcPagingItemReader` queries page by page and returns items to Spring Batch on each `read()` call. The step still collects items into chunks to process/write and commit transactions. Page size and chunk size are two related settings, but they are not synonymous.

## 2. How Paging Differs from Cursor Reading

Spring Batch has multiple JDBC readers. Two commonly compared approaches are `JdbcCursorItemReader` and `JdbcPagingItemReader`.

| Criterion | `JdbcCursorItemReader` | `JdbcPagingItemReader` |
|---|---|---|
| Reading approach | Opens a single cursor/result set and iterates sequentially. | Runs multiple queries, each fetching one page. |
| Connection | Usually holds a cursor/connection open during reading. | Executes queries per page; each page fetch queries the database. |
| Restart | May need to reopen and skip the number of already-read items depending on reader/state. | Saves the last sort key to continue querying from the appropriate position. |
| Sort requirement | Needs appropriate query ordering if business logic depends on order. | Requires a stable sort key, ideally unique to avoid losing/duplicating data. |
| Best suited for | Databases/drivers with strong cursor support wanting to read one continuous result set. | Wanting to fetch data by page and continue via sort key. |

Paging is not automatically faster than a cursor across all databases. It trades one long query for many small queries; performance depends on indexes, query plans, page size, latency, and database characteristics.

## 3. Components of JdbcPagingItemReader

`JdbcPagingItemReader<T>` uses a `PagingQueryProvider` to generate SQL appropriate for the database. Main components:

| Component | Role |
|---|---|
| `DataSource` | Connects to the database. |
| `selectClause` | Columns to retrieve, including required sort keys. |
| `fromClause` | Tables and joins forming the data source. |
| `whereClause` | Fixed filter condition for the job's dataset. |
| `sortKeys` | Columns and sort directions used to paginate and resume after a checkpoint. |
| `RowMapper<T>` | Converts each `ResultSet` row into a Java item. |
| `pageSize` | Number of rows fetched in a single page query. |
| `ExecutionContext` | Stores state needed for restart. |

Basic configuration example:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['status']}") String status) {

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("id", Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select id, customer_id, status, created_at, total_amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", status))
            .sortKeys(sortKeys)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getString("status"),
                    rs.getTimestamp("created_at").toInstant(),
                    rs.getBigDecimal("total_amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

In the example, `id` is a unique key sorted in ascending order. `whereClause` restricts the data by status. `parameterValues` binds values to placeholders, avoiding concatenating parameter strings directly into SQL.

`sortKeys` is used by the query provider to build the ordering and the condition for fetching the next page. Do not manually append `ORDER BY` to `selectClause` or `whereClause` when the query provider is already responsible for generating the order clause.

## 4. PagingQueryProvider and Database-Specific SQL

Different databases have different paging syntax. For example, some engines use `LIMIT`, while others use `OFFSET/FETCH`, `ROWNUM`, or other query structures. `PagingQueryProvider` abstracts those differences.

`JdbcPagingItemReader` can obtain the appropriate query provider from `DataSource` via `SqlPagingQueryProviderFactoryBean`/the factory used by Spring Batch. When using the builder with `DataSource`, `selectClause`, `fromClause`, `whereClause`, and `sortKeys`, the framework can create the provider from database metadata.

You can configure the provider explicitly if you need finer control:

```java
@Bean
SqlPagingQueryProviderFactoryBean orderQueryProvider(DataSource dataSource) {
    SqlPagingQueryProviderFactoryBean provider =
            new SqlPagingQueryProviderFactoryBean();
    provider.setDataSource(dataSource);
    provider.setSelectClause(
            "select id, customer_id, status, created_at, total_amount");
    provider.setFromClause("from orders");
    provider.setWhereClause("where status = :status");

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("id", Order.ASCENDING);
    provider.setSortKeys(sortKeys);
    return provider;
}
```

Then pass the `PagingQueryProvider` to the reader according to the API of your Spring Batch version. When using a factory bean in Spring configuration, inject the created `PagingQueryProvider` object from the factory rather than passing the factory bean directly in place of the provider.

If the query is complex, involving CTEs, joins, or database-specific syntax, inspect the SQL generated by the provider and its execution plan on the real database. A query that works on the first page might not generate the right continuation condition for the next page if sort keys or aliases are not declared appropriately.

## 5. What Does Stable Sorting Mean?

A stable sort order must determine the position of each row consistently. `ORDER BY created_at` may not be enough if multiple rows share the same timestamp.

Example:

| id | created_at | customer_id |
|---:|---|---|
| 101 | 2026-11-15 09:00:00 | 12 |
| 102 | 2026-11-15 09:00:00 | 15 |
| 103 | 2026-11-15 09:00:00 | 18 |
| 104 | 2026-11-15 09:01:00 | 20 |

If you only sort by `created_at`, the first three rows have the same sort value. The database is not obligated to return rows with equal values in a fixed order without an additional distinguishing key.

Add a unique key as a tie-breaker:

```sql
ORDER BY created_at ASC, id ASC
```

Here:

- `created_at` establishes the primary business order.
- `id` distinguishes rows that share the same timestamp.

Combining the two columns forms a total order if the pair `(created_at, id)` is unique. If `id` is a primary key, this condition is guaranteed.

## 6. Why Must the Sort Key Be Unique?

`JdbcPagingItemReader` needs to identify the last row of a page to construct the query for the next page and store restart information. If the sort key is not unique, multiple rows can share the same value across a page boundary.

For example, suppose the page size is 2 and sorting is only by `created_at`:

```text
Page 1:
  id=101, created_at=09:00
  id=102, created_at=09:00

Page 2:
  id=103, created_at=09:00
  id=104, created_at=09:01
```

If the condition for fetching the next page relies only on `created_at > 09:00`, row `id=103` has the same timestamp as the last row of the previous page and can be skipped. With sort-key paging, the continuation predicate needs to distinguish the order of every row.

Add `id` as a tie-breaker:

```text
ORDER BY created_at ASC, id ASC

Page 1:
  (09:00, 101)
  (09:00, 102)

Page 2:
  (09:00, 103)
  (09:01, 104)
```

The composite sort key `(created_at, id)` creates an unambiguous order across pages. Spring Batch documentation requires sort keys to be unique to guarantee no data loss across executions/paging.

## 7. Using a Primary Key as the Sort Key

If no other business ordering is required, an ascending primary key is usually a simple and reliable sort key:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("id", Order.ASCENDING);
```

Advantages:

- Primary keys are typically unique and non-null.
- An index already exists, helping the database locate the next page efficiently.
- It does not change during the record's lifecycle if the schema is properly designed.
- Checkpoints are easy to represent with a single value.

The disadvantage is that the order may not reflect business order. If you need to process by creation date, sequence, or priority, use that business key along with the primary key as a tie-breaker.

Do not use an incrementing column as a sort key if its value can be updated while the job is running. A mutable sort key can cause a row to move from after the checkpoint to before it, or vice versa.

## 8. Using Multiple Sort Keys

`sortKeys` can contain multiple columns. The declaration order in the map must reflect the desired sort order.

For example, if you need to read by business date, then by customer ID and order ID:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("business_date", Order.ASCENDING);
sortKeys.put("customer_id", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Semantically equivalent to:

```sql
ORDER BY business_date ASC, customer_id ASC, id ASC
```

If `id` is unique, the entire order is unique even when many rows share the same `business_date` and `customer_id`.

Use `LinkedHashMap` to preserve the declaration order of sort keys. Do not rely on the iteration order of a map that does not guarantee ordering when multiple sort keys have precedence.

## 9. Combining ASC and DESC

Sort keys can use different directions:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("priority", Order.DESCENDING);
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Meaning:

1. Higher priority is read first.
2. Within the same priority, read in ascending creation-time order.
3. If timestamps collide, use ID to distinguish.

When using mixed ASC/DESC sort keys, the query provider must generate the appropriate continuation predicate for each direction. Test on the actual database and Spring Batch version in use, especially when there are multiple columns and page boundaries fall inside duplicate-value groups.

Do not hand-write a next-page `WHERE` condition based on a simple single comparison when there are multiple sort directions. With `(priority DESC, created_at ASC, id ASC)`, the continuation condition must respect lexicographical order and each column's direction.

## 10. Sort Keys Must Appear in the Select Clause

The reader needs the sort key values to build the next-page condition and save checkpoints. Therefore, the sort key columns must be present in the selected data.

Example:

```java
.selectClause("select id, created_at, customer_id, total_amount")
.fromClause("from orders")
```

If sorting by `created_at` and `id`, both columns must be in the select list. Do not select only the fields displayed to the processor while omitting columns used for paging.

With joins, clearly identify which table each sort key belongs to and use column names/aliases compatible with the query provider. Avoid ambiguous column names when multiple tables have `id`, `created_at`, or `status`.

## 11. Sort Keys and Database Indexes

Stable sorting ensures correctness; appropriate indexes make paging run efficiently.

Example query:

```sql
SELECT id, customer_id, status, created_at, total_amount
FROM orders
WHERE status = ?
ORDER BY created_at ASC, id ASC
```

An index to consider:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders(status, created_at, id);
```

Index column order should be based on selectivity, predicates, and the database's query plan. The example index places the filter column `status` before the sort columns. On databases supporting index direction or covering indexes, you can further optimize for the workload.

Do not create indexes solely based on SQL appearance. Inspect `EXPLAIN`/execution plans, rows scanned, sort operations, logical reads, and time per page. Additional indexes also increase insert/update overhead and storage usage.

## 12. Page Size and Chunk Size Are Different

`pageSize` is the number of rows the reader requests in a single database query. `chunkSize` is the number of items Spring Batch buffers before calling the writer and committing the transaction.

Example:

```java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, status, total_amount")
        .fromClause("from orders")
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper(orderRowMapper)
        .pageSize(1000)
        .build();
```

Step:

```java
new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

The reader may load a page of 1,000 rows while the step commits after every 200 items. In this case, one page can serve multiple chunks. Page boundaries do not have to match transaction boundaries.

A common starting point to try is setting page size equal to chunk size or an appropriate multiple of chunk size, though you should benchmark. A large page can reduce query count but increases buffered data; a large chunk increases transaction duration and the number of live items held concurrently.

## 13. Choosing Page Size Based on Workload

There is no single optimal page size for every database and item type. You need to balance:

- Number of round trips to the database.
- Row size and mapped object size.
- Heap memory of the batch worker.
- Processor and writer speed.
- Commit time and lock duration.
- Network latency between application and database.
- Driver and database buffer capabilities.

Reference table for approximate page counts across one million rows:

| Page size | Approximate number of pages |
|---:|---:|
| 100 | 10,000 |
| 500 | 2,000 |
| 1,000 | 1,000 |
| 5,000 | 200 |

This is only a page-count calculation, not a runtime prediction. Larger page sizes can reduce round trips but produce heavier queries and higher memory usage. Smaller page sizes reduce data per fetch but increase the number of queries.

Measure at least throughput, query time per page, heap, GC, transaction duration, and database load. Choose a value suited to real data rather than simply increasing page size to reduce query count.

## 14. Distinguishing pageSize and fetchSize

`pageSize` is the page size that `JdbcPagingItemReader` asks the query provider to retrieve from the database. `fetchSize` is a JDBC hint to the driver for how many rows to fetch from the result set in one round trip/read.

These two properties do not mean the same thing:

| Property | Controls |
|---|---|
| `pageSize` | Number of items in one logical Spring Batch paging query page. |
| `fetchSize` | Hint to the JDBC driver on how to fetch rows from a `ResultSet`. |
| `chunkSize` | Number of items processed in a single chunk transaction. |

Example:

```java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, total_amount")
        .fromClause("from orders")
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper(orderRowMapper)
        .pageSize(1000)
        .fetchSize(500)
        .build();
```

`fetchSize` is only a hint; the driver may ignore or interpret it differently. The paging query already limits the row count at the SQL level, while fetch size controls how the driver retrieves the result set's rows.

## 15. Paging with Fixed Filter Conditions

A job often processes only a subset of data. You can use `whereClause` and `parameterValues` to restrict it:

```java
.whereClause("where status = :status and business_date = :businessDate")
.parameterValues(Map.of(
        "status", "READY",
        "businessDate", Date.valueOf(businessDate)))
```

The condition should define the `JobInstance`'s dataset. If the same job is restarted, filter parameters must stay unchanged. Changing `businessDate` or `status` on a restart can cause the reader to read a different dataset while still using the old checkpoint.

For jobs processing a time window, fix `fromTime` and `toTime` in `JobParameters` before launch. Avoid expressions like `CURRENT_TIMESTAMP` that change from page to page if the goal is a consistent logical snapshot.

## 16. Offset Paging and Keyset Paging

Paging can be implemented with different SQL strategies.

**Offset paging** uses the number of rows to skip:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at, id
OFFSET 10000 ROWS FETCH NEXT 500 ROWS ONLY
```

At large offsets, the database may have to scan/skip many rows before returning a page. If data changes between queries, offset positions can also shift.

**Keyset/seek paging** uses the sort key values from the end of the previous page to fetch subsequent rows:

```sql
SELECT id, created_at
FROM orders
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at, id
FETCH FIRST 500 ROWS ONLY
```

The keyset predicate tracks the sort key rather than the count of skipped rows. `JdbcPagingItemReader` uses `PagingQueryProvider` to generate the appropriate paging queries, including sort-key-based conditions for subsequent pages and restarts.

Do not equate all database paging with `OFFSET` syntax. A specific query provider may use a different strategy. Inspect the generated SQL for the database you are using.

## 17. Data Changing During Paging

A unique sort key solves ordering determinism, but it does not automatically create an immutable snapshot of the table.

Suppose a job reads in ascending `id` order and has checkpointed at `id=5000`:

- A new row with `id=6000` inserted before the job finishes may be read in a later page.
- A new row with `id=4500` inserted after the checkpoint may not be read in this run.
- An unread row that gets deleted will not appear.
- An unread row whose sort key is updated from 7000 down to 4000 may move ahead of the checkpoint and be skipped.
- An already-read row whose sort key is updated from 3000 up to 8000 may reappear later depending on the query and state.

Exact behavior depends on isolation level, query provider, database, and how transactions are opened. If the job needs to process an exact dataset defined at start time, you must design a snapshot/window rather than relying solely on sort keys.

Options include:

- Choosing an immutable time range or batch ID in `whereClause`.
- Using snapshot isolation or an appropriate transaction isolation level if the database supports it and transaction duration is acceptable.
- Materializing the list of keys to process into a staging/manifest table before reading.
- Using a status column and claim/locking by design to identify records belonging to the batch.
- Freezing the input set via an upstream process before launch.

Do not assume that using a `READ COMMITTED` transaction provides a consistent snapshot across all pages. Each query may see newly committed data depending on the database/isolation level.

## 18. Sort Keys Should Be Immutable During Processing

A sort key can be unique yet still unstable if its value changes while the job runs. Primary keys are usually suitable because they do not change. Columns like `status`, `priority`, or `updated_at` can be modified by other applications.

For example, do not sort solely by status:

```sql
ORDER BY status, id
```

If status changes from `READY` to `DONE` when the job or another process updates data, the row can shift position. If `whereClause` also filters on status, the row can disappear from the result set or move in/out of the dataset.

If status is a claim condition, clearly define the claim point and how checkpointing works. You can use an immutable `batch_id` column for the active batch or a staging table holding the selected IDs.

## 19. Sort Keys with Nulls

A sort key might allow `NULL` in the schema, but null ordering (first or last) varies across databases and queries. Keyset conditions also become more complex when comparing with null because SQL uses three-valued logic.

Example:

```sql
ORDER BY processed_at ASC, id ASC
```

If `processed_at` can be null, clearly define the rule:

- Exclude nulls in `whereClause` if business logic does not process them.
- Normalize nulls to a distinct sort value using a supported expression and select that exact expression.
- Use a non-null column as the primary sort key, or add a discriminator to place the null group explicitly.

The simplest approach is using a non-null and unique sort key, usually the primary key. If you must sort by a nullable column, test page boundaries across the null group on the real database.

## 20. Sort Keys in Queries with JOIN or GROUP BY

Complex queries need a sort key representing each output item. If you join an order with multiple order lines, the result can have multiple rows for the same `order.id`.

Example:

```sql
SELECT o.id, o.created_at, l.id AS line_id, l.sku
FROM orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at, o.id
```

If the reader returns each joined row as one item, `(o.created_at, o.id)` is not unique because one order has multiple lines. You must add `l.id` as a tie-breaker:

```sql
ORDER BY o.created_at, o.id, l.id
```

If the logical item is an order with a collection of lines, you may need a different query/grouping so each output row is a unique order. `GROUP BY` and aggregates also require a unique sort key per group.

Define the item boundary before choosing the sort key. The sort key must be unique over the rows the reader actually returns, not just unique on one source table.

## 21. Sort Keys and Aliases

In join queries, column names can be ambiguous. You may need aliases in the select list, and the query provider also needs to know the exact sort column names to build ordering and continuation predicates.

Example:

```sql
SELECT o.id AS order_id,
       o.created_at AS order_created_at,
       l.id AS line_id
FROM orders o
JOIN order_lines l ON l.order_id = o.id
```

When configuring sort keys, use names/aliases supported by the query provider in the generated SQL. Some providers require sort key columns to appear in the select list and may require column names unqualified by table aliases. Inspect the actual query to avoid invalid SQL or continuation predicates referencing the wrong name.

If the query provider cannot handle a specialized query shape, consider creating a view, a staging table, or a suitable custom `PagingQueryProvider` instead of forcing the builder to generate invalid SQL.

## 22. Sort Keys and String Collations

If the sort key is a `String`, ordering depends on database collation/charset. For example, uppercase/lowercase, Vietnamese diacritics, and Unicode characters can sort differently across environments.

Factors to determine:

- Column and database collation.
- Whether comparison is case-sensitive or case-insensitive.
- Diacritic rules and Unicode normalization.
- Whether duplicate values exist after collation normalization.
- Whether a numeric/ID key is present as a tie-breaker.

If business order needs to be independent of environment collation, you can use a pre-normalized, indexed sort key column. Do not normalize only inside `RowMapper` because paging is determined in SQL; the values used for sorting must be determined consistently in the database query.

## 23. Checkpoint and Restart of JdbcPagingItemReader

`JdbcPagingItemReader` implements `ItemStreamReader`. When `saveState(true)` is set, the reader saves necessary state in `ExecutionContext`, including sort key information of the last item confirmed by the chunk lifecycle.

On restart, the reader uses this state together with the query provider to fetch subsequent data in sort key order. Therefore, sort keys must be:

- Unique across the query results.
- Selected so the reader can store their values.
- Stable between the initial run and restart.
- Consistent in data type and comparison semantics in the database.
- Declared in the same order and ASC/DESC direction.

The reader name must also be stable:

```java
.name("orderReader")
.saveState(true)
```

Do not change the reader name, sort keys, directions, query filters, or resource/`JobParameters` while an old `JobInstance` can still be restarted. Such changes can render old checkpoints incompatible with the new query.

## 24. Page Boundaries and Chunk Boundaries

A page boundary is the boundary of one database query. A chunk boundary is Spring Batch's commit boundary. The two boundaries can differ.

For example, page size 1,000, chunk size 250:

```text
Page 1: item 1-1000
  Chunk 1: 1-250     -> commit
  Chunk 2: 251-500   -> commit
  Chunk 3: 501-750   -> commit
  Chunk 4: 751-1000  -> commit

Page 2: item 1001-2000
  Chunk 5: 1001-1250 -> commit
  ...
```

If page size is 500 and chunk size is 800, a single chunk may need items from multiple pages. That does not alter chunk transaction semantics.

The reader can hold the fetched page in memory while chunks are processed. Therefore, an overly large page size can still create memory pressure even when chunks are small.

## 25. Notes on Transactions and Isolation

`JdbcPagingItemReader` typically opens page queries during the step. Transactions and isolation levels affect whether pages see changes from other transactions.

Points to determine:

- Does the reader use the same or a different transaction manager as the writer?
- Should each page query see newly committed data?
- Is a consistent snapshot needed for the entire job?
- Does the writer update the very rows the reader is filtering/sorting?
- Does locking reduce throughput or cause deadlocks?

If the reader filters `status = 'READY'` and the writer changes status to `DONE`, understand the result set of subsequent pages and how restart behaves. If page queries simply continue past the sort key, status changes can remove rows from the result set. This may be intentional, but it must be designed explicitly.

A common strategy is pre-selecting the batch's list of keys into a staging table with a batch ID, and having the reader page by batch ID and primary key. That way, the dataset to process is less affected by concurrent business changes.

## 26. Using a Custom Query Provider

`PagingQueryProvider` defines the queries for the first page and subsequent pages. If a specialized database or query is not supported by the factory, you can implement a custom provider following Spring Batch's contract.

Before writing your own provider, consider:

- Using an existing database-specific provider.
- Creating a view to simplify the query.
- Loading data into a staging table.
- Replacing a complex query with a select over materialized keys.

A custom provider must generate accurate SQL for:

- First page query.
- Subsequent page queries based on the last sort key.
- Sort directions ASC/DESC.
- Multiple sort keys with tie-breakers.
- Parameter binding and column names.
- Database syntax and row-count limits.

Bugs in the next-page predicate may not show up on the first page. Test at least three pages, pages with duplicate sort values, the last page, and restarts mid-page.

## 27. Using Partitioning with a Paging Reader

A paging reader can be used in a partitioning worker step, for example with each worker processing an ID range or a tenant. Each partition needs its own query scope and its own `ExecutionContext`.

Example:

```java
.whereClause("where id >= :minId and id <= :maxId")
.parameterValues(Map.of(
        "minId", minId,
        "maxId", maxId))
.sortKeys(Map.of("id", Order.ASCENDING))
```

The partitioner creates non-overlapping ranges. Each worker reads pages within its own range.

What must be ensured:

- Ranges cover the desired dataset and do not overlap unintentionally.
- Each reader instance has state/name appropriate for its partition.
- Sort keys are unique within the worker's query scope.
- The same range is never assigned to two workers without a claim/lock mechanism.
- Writers/outputs do not conflict across partitions.

If the same mutable reader bean is shared across multiple partitions without proper scope/prototype configuration, worker state can be shared. Create reader instances per step scope/partition context according to Spring Batch configuration.

## 28. Testing Sort Keys and Page Boundaries

Tests must include data that intentionally duplicates primary sort values to prove the tie-breaker works.

Example fixture:

| id | created_at | amount |
|---:|---|---:|
| 10 | 09:00 | 10.00 |
| 11 | 09:00 | 11.00 |
| 12 | 09:00 | 12.00 |
| 13 | 09:01 | 13.00 |
| 14 | 09:01 | 14.00 |

Sort keys:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Set page size to 2 so the duplicate `created_at` group is split across a page boundary. Read everything and verify the order:

```text
10, 11 | 12, 13 | 14
```

This test can catch sorting only by timestamp, which would cause the next page to skip records with the same timestamp.

## 29. Testing for Zero Lost or Duplicate Items

Do not check only the total item count. Verify business keys:

```java
List<Long> ids = new ArrayList<>();
Order item;
while ((item = reader.read()) != null) {
    ids.add(item.id());
}

assertThat(ids).containsExactly(10L, 11L, 12L, 13L, 14L);
assertThat(ids).doesNotHaveDuplicates();
```

In integration tests, also verify:

- No ID is missing.
- No ID appears twice.
- Ordering matches all sort keys.
- A final page smaller than page size is still read completely.
- An empty dataset terminates cleanly.
- The `whereClause` condition is applied on every page.

## 30. Testing Restart Across Pages

A restart test can follow this sequence:

1. Create a fixture table spanning multiple pages with multiple rows sharing the same sort value.
2. Launch the job with fixed identifying parameters.
3. Read and commit several chunks across at least one page boundary.
4. Fail the step in a controlled manner.
5. Verify `ExecutionContext` contains the necessary reader state.
6. Restart the same `JobInstance` with the exact same query, sort keys, directions, and parameters.
7. Verify the reader resumes after the committed sort key.
8. Compare output against the expected set of IDs, ensuring no missing or duplicate items.

If page size differs from chunk size, place the failure at a point that exercises both page boundaries and chunk boundaries. A test that only fails within the first page may miss continuation query bugs.

Do not change sort keys or resource/query filters between the initial run and restart. If you want to change sorting, create a new `JobInstance` with the new rules.

## 31. Testing When Data Changes Concurrently

If other transactions insert/update/delete while the batch is running, test under the production isolation level and database.

Scenarios to simulate:

- Insert a row with a sort key greater than the checkpoint.
- Insert a row with a sort key smaller than the checkpoint.
- Delete an unread row.
- Update the sort key of an unread row.
- Update a filter column causing a row to enter/leave the result set.
- Restart after some changes have committed.

Expected results must be defined upfront: does the job process a start-time snapshot, every row matching at each page query's time, or a fixed batch manifest? There is no single semantics that fits every business requirement.

## 32. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Missing rows at page boundaries | Non-unique sort key or continuation predicate does not distinguish duplicate rows. | Add primary key as a tie-breaker. |
| Rows appear twice | Mutable sort key, unstable order, or data changes while paging. | Use an immutable key and fixed dataset/snapshot. |
| Restart reads from wrong position | Changed reader name, sort key, direction, query filter, or input parameters. | Keep configuration and identifying parameters stable for the `JobInstance`. |
| Page queries get progressively slower | Large offsets, unsuitable indexes, or poor query plans. | Check provider, indexes, and execution plan; use an appropriate keyset strategy. |
| SQL error on next page | Sort key missing from select list or provider does not support query shape. | Inspect generated SQL per page and column/alias names. |
| Ordering differs across environments | Different collation, null ordering, or map key ordering. | Define collation/null rules and use an ordered sort key map. |
| Sorting by timestamp gives unstable tie order | Timestamps are not unique. | Add a unique ID as a tie-breaker. |
| High memory usage despite paging | Page/chunk too large or `RowMapper` builds heavy objects. | Reduce page/chunk, select only needed fields, and profile heap. |
| Missing newly inserted data | Row has sort key smaller than checkpoint or dataset was already fixed. | Clarify snapshot/window semantics and batch manifest. |
| Partitions process duplicates | Overlapping ranges or workers sharing reader/state. | Create non-overlapping ranges and separate reader instances. |
| First page works, later pages fail | Incorrect continuation predicate or mixed ASC/DESC generation. | Test multiple pages and duplicate sort values on the real database. |

## 33. Process for Designing Paging with Stable Sorting

When implementing `JdbcPagingItemReader`, follow these steps:

1. **Define the item boundary:** one row, one group, or an aggregated entity?
2. **Define the dataset:** lock down `whereClause`, batch window, and identifying `JobParameters`.
3. **Choose business ordering:** date, sequence, priority, or primary key.
4. **Add a unique tie-breaker:** usually the primary key or a unique composite key.
5. **Choose sort directions:** explicitly declare ASC/DESC for each key.
6. **Include sort keys in the select list:** ensure the reader has values for paging/restart continuation.
7. **Configure the provider:** use a database-compatible provider and verify first/subsequent page queries.
8. **Design indexes:** match predicates, sort order, and execution plans.
9. **Choose page/chunk sizes:** benchmark against row width, heap, and transaction duration.
10. **Keep state stable:** reader name, sort keys, directions, parameters, and input set remain unchanged on restart.
11. **Define concurrency semantics:** snapshot, dynamic data, or batch manifest.
12. **Test page boundaries:** intentionally create multiple rows sharing the same primary sort value.
13. **Test restart:** fail across page/chunk boundaries and verify no missing or duplicate items.
14. **Measure production behavior:** query time, throughput, heap, GC, and database load.

## 34. Key Takeaways

- `JdbcPagingItemReader` reads a database page by page, returns items for chunk processing, and supports checkpoint/restart.
- `PagingQueryProvider` generates paging SQL tailored to the database and sort keys.
- `pageSize`, `chunkSize`, and `fetchSize` have different meanings: page query size, transaction chunk size, and JDBC fetch hint.
- Sorting must uniquely determine each row's order; sorting by timestamp or status alone is usually insufficient.
- Add a primary key as a tie-breaker, such as `ORDER BY created_at, id`.
- With multiple sort keys, use `LinkedHashMap` to preserve precedence order; declare ASC/DESC explicitly.
- Sort keys must be in the select list, stable, non-null if possible, and immutable during job execution.
- Join queries need a sort key that is unique over the actual result set, not just on the base table.
- Indexes should align with filters and sorting; confirm via execution plans on the real database.
- Paging does not automatically create a consistent snapshot; inserts/updates/deletes between pages can alter the dataset.
- Keep reader name, sort keys, directions, query filters, and `JobParameters` stable for restart.
- Test at least multiple pages, duplicate sort values, the final page, restarts, and concurrent data changes under chosen semantics.
- Partitioning requires separate readers/state and non-overlapping ranges when running in parallel.

Paging reads enable Spring Batch to process large JDBC datasets without materializing all results in memory. However, paging is only reliable when ordering is uniquely defined and kept stable across every page as well as restarts. Choose immutable sort keys with a unique tie-breaker, verify the query provider and indexes on the real database, pin down the dataset to process, and thoroughly test page/chunk boundaries and restarts to prevent lost or duplicated records.
