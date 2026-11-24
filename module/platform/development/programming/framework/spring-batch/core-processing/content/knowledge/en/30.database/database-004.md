# Paging Queries and Sort Keys

In Spring Batch, paging queries are a way to read data from a database page by page rather than keeping a large result set open throughout processing. `JdbcPagingItemReader` achieves this by generating SQL statements per page through a `PagingQueryProvider`. A **sort key** defines a stable ordering of rows and tells the reader where to continue on the next page or upon restart.

Sort keys are at the core of a paging reader. If the ordering is non-unique or changes while the Job is running, a row may be read twice or skipped between two pages. Therefore, choose sort keys with deterministic ordering—typically a primary key or a composite of columns ending with a unique key—and create matching indexes so the database can query efficiently.

## 1. What is a paging query?

Suppose the `orders` table has millions of records. A reader that reads all data in one pass can create a large result set, hold a cursor/connection for a long time, and put pressure on memory or the database. Paging breaks the query into smaller chunks:

```text
orders dataset
       |
       v
Page 1: rows 1 - 500
       |
       v
Page 2: rows 501 - 1000
       |
       v
Page 3: rows 1001 - 1500
       |
       v
       ...
```

`JdbcPagingItemReader` queries one page, feeds each item to the chunk pipeline, and then fetches the next page when needed. The reader does not need to hold an open JDBC cursor over the entire dataset like traditional cursor reading.

Paging is typically suitable when:

- The data source is a JDBC database.
- The dataset is large and can be queried in a deterministic order.
- You want to limit the number of rows fetched in each query.
- You need a reader capable of saving checkpoints and restarting.
- The database has indexes matching the filter conditions and sort keys.

Paging does not automatically make queries fast if the database must scan and sort the entire table on every page. Query structure, sort keys, and indexes determine most of the performance.

## 2. JdbcPagingItemReader and PagingQueryProvider

`JdbcPagingItemReader<T>` is the standard Spring Batch reader for reading JDBC data by page. It uses a `PagingQueryProvider` to generate queries tailored to the database's paging syntax.

Key components:

- `DataSource`: database connection.
- `selectClause`: columns to read.
- `fromClause`: source table or expression.
- `whereClause`: data filter conditions.
- `sortKeys`: columns defining the ordering and continuation position.
- `parameterValues`: bound values for query conditions.
- `pageSize`: number of rows in a page.
- `rowMapper`: converts each `ResultSet` row into an object.

Spring Batch can create a `PagingQueryProvider` from SQL clauses and `DataSource` metadata, or the application can supply a specific provider if database-level query control is needed.

Different databases have different paging syntaxes. A provider may use `FETCH FIRST`, `LIMIT`, `ROWNUM`, or another mechanism. Therefore, let the corresponding provider generate the query rather than assuming a single SQL syntax works across all databases.

## 3. Example JdbcPagingItemReader configuration in Spring Batch 5

Example reading orders by tenant and status, sorted by creation time and then `order_id`:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderRecord> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['order.status']}") String status) {

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("created_at", Order.ASCENDING);
    sortKeys.put("order_id", Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<OrderRecord>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, customer_id, amount, created_at")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and status = :status")
            .parameterValues(Map.of(
                    "tenantId", tenantId,
                    "status", status))
            .sortKeys(sortKeys)
            .pageSize(500)
            .fetchSize(500)
            .rowMapper((rs, rowNum) -> new OrderRecord(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount"),
                    rs.getTimestamp("created_at").toInstant()))
            .saveState(true)
            .build();
}
```

In this example, `Order` in the sort key map is the `org.springframework.batch.item.database.Order` enum; `OrderRecord` is the application's domain type. The keys `created_at` and `order_id` determine result ordering. `order_id` acts as a tie-breaker so two orders created at the exact same timestamp still have a deterministic order.

`sortKeys` should be created using `LinkedHashMap` to preserve column order in the composite sort key. Columns used for sorting must be present in the query results as required by the provider and referenced consistently in configuration.

## 4. What is a sort key?

A sort key is one or more columns used to determine row order when the reader fetches data. Example:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE status = 'READY'
ORDER BY order_id ASC
```

Here `order_id` is the sort key. The reader fetches the first page in ascending order, then uses the last sort key value to determine the next slice of data.

A good sort key should:

- Have a stable comparison order in the database.
- Not change while the Job is running.
- Uniquely distinguish each result row, or combine multiple columns into a unique tuple.
- Have index support for filter conditions and query ordering.
- Be returned in `SELECT` so the reader can save the end-of-page value.

If the sort key is not unique, multiple rows can share the same value at a page boundary. When the reader continues using a condition strictly after the last value, remaining rows with that same key may be skipped.

## 5. Why must a sort key be unique?

Suppose a table has these rows:

| order_id | created_at | customer_id |
|---:|---|---|
| 101 | 09:00:00 | C001 |
| 102 | 09:00:00 | C002 |
| 103 | 09:00:00 | C003 |
| 104 | 09:01:00 | C004 |

If only `created_at` is used as the sort key and a page ends at a row with `created_at = 09:00:00`, the next page may look for rows with a timestamp greater than `09:00:00`. Other rows with the same timestamp that have not yet been read will not be selected.

To avoid this issue, add a unique key as a tie-breaker:

```sql
ORDER BY created_at ASC, order_id ASC
```

The tuple `(created_at, order_id)` establishes a deterministic total order if `order_id` is unique. When a page ends at `(09:00:00, 102)`, the next slice can start after that tuple:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
ORDER BY created_at ASC, order_id ASC
```

This condition illustrates how composite keys are compared from left to right. `PagingQueryProvider` generates the exact syntax appropriate for the database and sort key configuration.

If a join query causes an `order_id` to appear multiple times, the primary key of the `orders` table is no longer unique for the query results. In that case, add the joined table's key or adjust the query so each item has a unique sort key tuple.

## 6. Composite sort keys

When a single column is not sufficiently unique, you can use multiple columns in priority order:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("business_date", Order.ASCENDING);
sortKeys.put("tenant_id", Order.ASCENDING);
sortKeys.put("order_id", Order.ASCENDING);
```

The logical order is:

1. Sort by `business_date`.
2. If on the same date, sort by `tenant_id`.
3. If on the same date and tenant, sort by `order_id`.

This tuple must be unique across the entire result set. If `order_id` is only unique within a tenant, adding `tenant_id` to the tuple distinguishes rows across tenants.

When using composite sort keys:

- Use `LinkedHashMap` so key order is explicit.
- Pick ASC/DESC directions consistent with how you want to traverse data.
- Ensure every column is present in the query and properly understood by the database.
- Ensure the final tuple is truly unique.
- Test boundaries where the leading columns share duplicate values.

Do not pick arbitrary extra columns just to make a query appear sorted. Each additional column makes continuation predicates more complex; pick the smallest set of keys sufficient for a unique and stable order.

## 7. ASC and DESC

Sort keys can use ascending or descending order:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.DESCENDING);
sortKeys.put("order_id", Order.DESCENDING);
```

This example reads newest orders first. When using multiple columns with mixed directions, understand the exact tuple ordering and verify whether the query provider supports that direction combination for your database.

What matters is not just the sort direction, but stability. If using `created_at DESC` and `order_id DESC`, checkpoint values must continue in exact descending order. Do not change sort direction between the first run and a restart of the same JobInstance.

## 8. Paging queries and keyset continuation

To fetch the next page, the reader needs the last position from the previous page. With an ascending unique sort key, the query idea is:

```sql
-- First page
SELECT order_id, customer_id, amount
FROM orders
WHERE status = :status
ORDER BY order_id ASC
FETCH FIRST :pageSize ROWS ONLY;

-- Subsequent pages, illustrating keyset predicate
SELECT order_id, customer_id, amount
FROM orders
WHERE status = :status
  AND order_id > :lastOrderId
ORDER BY order_id ASC
FETCH FIRST :pageSize ROWS ONLY;
```

The page-limiting syntax in the example depends on the database. `JdbcPagingItemReader` does not require the application to hand-write two queries like above when using the builder; `PagingQueryProvider` generates queries based on the database and sort keys.

With a composite key `(created_at, order_id)`, the continuation predicate has the form:

```sql
WHERE status = :status
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
  )
ORDER BY created_at ASC, order_id ASC
```

This is keyset pagination: using the last sort key value to find subsequent rows. It differs from offset pagination, where the database must skip over a number of previously read rows, such as `OFFSET 500000`. For large datasets, keyset pagination usually avoids the growing cost of offsets and offers clearer restart semantics when keys are stable.

Do not assume every database provider generates the exact same SQL. Inspect the generated queries or SQL logs in a test environment when optimizing for a specific dialect.

## 9. How does paging differ from offset pagination?

Two strategies are commonly compared:

| Aspect | Offset pagination | Keyset/sort-key paging |
|---|---|---|
| Next page position | Number of rows to skip (`OFFSET`) | Sort key value at the end of the previous page |
| Deep page cost | Can grow as the database traverses many rows | Typically more stable with appropriate indexes |
| Restart | Needs exact offset/page index; inserts/deletes can shift positions | Relies on saved key; more stable if keys are immutable |
| Requirement | Needs deterministic ORDER BY | Needs unique sort key and deterministic ordering |
| Changing data | Inserts/deletes before offset can cause duplicates or skips | Inserts/updates affecting keys can also alter remaining rows; needs snapshot/high-watermark for consistency |

`JdbcPagingItemReader` uses `PagingQueryProvider` and sort keys to generate database-specific queries. Exact query details do not always match offset syntax. The critical point at the application level is providing a unique, stable sort key so the provider can determine the next page and the reader can restart.

## 10. Page size, fetch size, and chunk size

These three concepts serve distinct roles:

- **Page size:** number of rows the reader requests in one page from the database.
- **Fetch size:** hint to the JDBC driver on how many rows to fetch per trip from the database; actual behavior depends on the driver.
- **Chunk size:** number of items processed in one chunk transaction before committing per Step configuration.

Example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRecord, OrderOutput>chunk(200, transactionManager)
        .reader(orderPagingReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

While the reader is configured with `pageSize(500)`, the Step has `chunk(200)`. The reader can load a 500-row page and supply items across multiple chunks. Page size does not directly dictate the transaction commit interval.

| Configuration | Example | Primary impact |
|---|---:|---|
| `pageSize` | 500 | Rows per paging query/page buffer. |
| `fetchSize` | 500 | Hint to the JDBC driver when fetching rows. |
| `chunk` | 200 | Items in one chunk transaction. |

### Choosing page size

A large page size can reduce query count, but increases memory for the page and single-read duration. A small page size reduces data per query, but increases round trips.

Consider:

- Object size after mapping, not only database row size.
- Latency between application and database.
- Query cost and execution plan.
- Connection pool and number of concurrent workers.
- Chunk size and commit frequency.
- Restart time and amount of data to reload.

There is no universal optimal page size for every Job. Measure throughput, heap usage, query latency, and database load with production-like data.

## 11. Filter conditions and sort keys must work together

Queries typically filter by one or more conditions and then sort results:

```sql
SELECT order_id, tenant_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at ASC, order_id ASC
```

A suitable index can start with equality filter columns followed by sort keys, for example:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at, order_id);
```

This index is only a design example. The best structure depends on the database, selectivity, cardinality, query predicates, and other workloads. Check actual execution plans; do not create indexes mechanically by formula.

If sort keys are not indexed, the database may have to sort a large dataset for every page. If filter predicates are not indexed, page queries may scan many rows before returning results.

### Sort key columns must be selected

The reader needs sort key values to track continuation positions. Ensure sort key columns are included in `selectClause` and declared names match the query provider. When using aliases or joins, verify that the provider can reference the keys in paging predicates and `ORDER BY` validly for the database.

## 12. Sort keys with NULLs or special collations

Sort keys should avoid NULL if possible. NULL ordering can differ between databases or depend on `NULLS FIRST`/`NULLS LAST`. If a page ends on a NULL value, continuation predicates can be hard to express accurately and inconsistently across dialects.

Recommendations:

- Prefer `NOT NULL` columns as sort keys.
- If a nullable column must be used, normalize via an expression/generated column with clear semantics and verify provider support.
- For strings, understand collation/case sensitivity and database comparison behavior.
- Do not change collation or data types between the initial run and restart.
- Add a non-NULL unique key as a tie-breaker.

For instance, if sorting by customer name which may be NULL or duplicated, you can sort by a normalized value plus the unique `customer_id`. However, sort expressions must be supported by the query provider and matching indexes.

## 13. Data changing while the reader is paging

Stable sort keys establish ordering, but do not guarantee an immutable dataset. While the Job reads multiple pages, other applications may insert, delete, or update rows.

For example, with ascending `order_id`:

- A new row with an ID greater than the current key may appear on a later page.
- A new row with an ID less than or equal to an already-read key may not be seen in the current run.
- A row deleted before the reader reaches its page will no longer be returned.
- If the sort key is mutable, a row can move across the checkpoint position, causing skips or duplicate reads.
- If filter attributes change, rows can enter or leave the result set between pages.

When a consistent dataset is required, define snapshot semantics:

- Use transaction isolation/snapshots suitable for the database if runtime and load permit.
- Capture a high-watermark at start time, e.g., `order_id <= :maxOrderIdAtStart`.
- Use a business date or batch membership table to fix the Job's item set.
- Pick immutable sort keys and stable filter predicates.
- Persist identifying JobParameters or ExecutionContext for the snapshot/version needed on restart.

High-watermark example:

```sql
WHERE tenant_id = :tenantId
  AND order_id <= :maxOrderIdAtStart
ORDER BY order_id ASC
```

The `maxOrderIdAtStart` value must be captured once and preserved across restarts of the same JobInstance. If recalculated every time the reader opens, the dataset may shift unexpectedly.

## 14. Restart and sort keys

`JdbcPagingItemReader` supports restart when state is enabled and the reader has a stable name. The reader stores position information based on sort keys in `ExecutionContext`, then uses it to resume reading after the committed point.

Example:

```java
new JdbcPagingItemReaderBuilder<OrderRecord>()
        .name("orderPagingReader")
        .dataSource(dataSource)
        .selectClause("select order_id, amount")
        .fromClause("from orders")
        .whereClause("where status = :status")
        .parameterValues(Map.of("status", "READY"))
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(500)
        .saveState(true)
        .rowMapper(orderRowMapper)
        .build();
```

Conditions for reliable restart:

- The reader has a stable and unique name within the Step scope.
- `saveState(true)` is enabled when checkpointing is needed.
- The sort key is unique across the query results.
- Sort directions and query filters stay stable.
- JobParameters and snapshot/high-watermark remain identical for the same JobInstance.
- Source data does not change in ways that invalidate checkpoint stability.
- The writer handles item reprocessing safely in case of ambiguous commits or external side effects.

Do not change sort keys between two runs of the same JobInstance. If the new query uses a different order, the old checkpoint may no longer point to the matching position.

## 15. Sort keys and data partitioning

Paging queries normally read a dataset in a single order. When combined with partitioning, each worker needs its own range and sort keys suited to that partition's result set.

For example, the manager splits by `tenant_id`, and workers read each tenant sorted by `(created_at, order_id)`. In that setup:

- The partition key determines which worker processes which tenant.
- Sort keys determine item order within a partition.
- Each worker has its own `ExecutionContext` and checkpoint.
- The sort tuple must be unique within each worker's result set.

Do not confuse the partition key with the sort key. They may overlap partially, but serve two different purposes.

If multiple workers read the same table, ensure partition predicates do not overlap and sort keys do not change. Limit concurrency according to the database connection pool and verify indexes for both partition predicates and paging order.

## 16. Using a custom queryProvider

The builder can construct a query provider from standard clauses. For complex queries or databases needing special syntax, you can create an appropriate `PagingQueryProvider` and pass it to the reader.

Cases that may need a custom provider:

- Queries with complex joins, aliases, or expressions.
- Databases with custom paging syntax not recognized accurately by the factory.
- Optimizing next-page predicates for specialized indexes.
- Controlling the first query and subsequent page queries.
- Queries using composite sort keys with special expressions.

When configuring a provider manually, you must still uphold the sort key contract: deterministic order, key values present in results, next-page predicates neither skipping nor duplicating rows, and restarts using accurate checkpoints.

Do not hand-write paging SQL just to work around a query error without checking the database dialect. A query that works on page one can fail on page two or on restart because the continuation predicate does not match the `ORDER BY` ordering.

## 17. Testing paging queries and sort keys

Testing should focus on page boundaries, duplicate sort keys, composite keys, restarts, and changing data.

### Testing no duplicates and no omissions

Create a fixture with more rows than two pages and multiple rows sharing the same value in the first sort column. Read everything and compare the ID set:

```java
Set<Long> actualIds = new LinkedHashSet<>();
OrderRecord item;
while ((item = reader.read()) != null) {
    assertThat(actualIds.add(item.orderId()))
            .as("order_id must not be read twice")
            .isTrue();
}

assertThat(actualIds).containsExactlyElementsOf(expectedIds);
```

This test assumes `expectedIds` is already sorted in the same query order. Beyond checking count, compare exact sequences to catch skipped rows or unstable ordering.

### Testing composite sort keys

Create multiple records sharing the same `created_at` but with different `order_id` values. Set page size smaller than the number of records with the same timestamp to force a page boundary inside the duplicate group. Verify every ID appears exactly once in `(created_at, order_id)` order.

### Testing restart

1. Open the reader with a fresh `ExecutionContext`.
2. Read several items and update the context at a checkpoint.
3. Create a new reader with the same name, query, sort keys, and parameters.
4. Open the reader with the saved context.
5. Verify the reader resumes after the last committed item without duplicates or skips.

In Spring Batch integration tests, test restart through a real Job/Step and real transactions to confirm checkpoints commit with chunks as configured.

### Testing changing data

- Insert rows with a sort key smaller than the checkpoint.
- Insert rows with a sort key larger than the checkpoint.
- Delete unread rows.
- Change sort keys or filter columns.
- Restart with the same high-watermark and verify the dataset does not change unexpectedly.

Not every application needs the same snapshot isolation, but tests must clarify the semantics of whether new data is processed in the current run or the next.

## 18. Monitoring and performance tuning

When a paging reader is slow, measure these metrics:

- Execution time per page query.
- Number of pages/queries for one Step.
- Rows read and items/second throughput.
- Heap usage and page buffer size.
- Connection wait time and database CPU/I/O.
- Sort spills or full table scans in execution plans.
- Chunk transaction and commit duration.
- Contention wait times when multiple workers query concurrently.

Common tuning directions:

- Create indexes matching filters and sort keys.
- Select only genuinely needed columns.
- Use short, stable, indexed sort keys.
- Choose page size based on measurements rather than guesses.
- Set fetch size sensibly for the JDBC driver.
- Avoid expressions on sort keys if they prevent index usage.
- Keep query filters sargable where possible.
- Avoid excessive concurrency causing contention.
- Inspect execution plans for both the first page and subsequent pages.

A query can run fast on the first page yet slow down on deep pages if the provider or index does not support the continuation predicate. Inspect the SQL generated for subsequent pages, not only the first query.

## 19. Common pitfalls

### Using a non-unique sort key

Multiple rows sharing a key at a page boundary can be skipped when the reader continues after the last value. Add a unique tie-breaker, typically the primary key.

### ORDER BY differing from sortKeys

If the ordering in a custom query does not match provider configuration, next-page predicates may not reflect the same order. Keep sort definitions consistent.

### Not selecting sort key columns

The reader/provider needs sort key values to build continuation positions and checkpoints. Include all sort keys in select results as required by the provider.

### Using mutable sort keys

A row can move across the checkpoint while the Job is running. Prefer immutable keys and explicit snapshots.

### Treating page size as chunk size

Page size controls data volume per query; chunk size controls the transaction commit interval. Choose both independently based on memory and transaction needs.

### Missing supporting indexes

The database may perform large scans/sorts for each page. Check execution plans and indexes for filters/sorts.

### Changing parameters or sort keys on restart

Old checkpoints may no longer align with the new query. Keep inputs, filters, high-watermarks, and sort order identical for the same JobInstance.

### Source data changing while expecting automatic snapshots

Paging does not automatically provide business snapshots across all databases. Define isolation, high-watermarks, or batch membership tables.

### Testing only the first page

Predicate bugs typically appear starting on page two or during restart. Test multiple pages and duplicate key boundaries.

### Too many workers paging the same table

High concurrency can increase contention and slow down the database. Measure throughput and cap according to connection pool/database capacity.

## 20. Paging query and sort key design workflow

When creating a paging reader, you can follow this sequence:

1. Define the dataset to read and filter conditions.
2. Choose immutable sort keys with deterministic ordering.
3. Ensure a single key or composite tuple is unique across query results.
4. Add a tie-breaker if the primary sort column has duplicate values.
5. Include all sort keys in the select clause and declare them in exact order in `sortKeys`.
6. Configure `JdbcPagingItemReader` and a database-appropriate `PagingQueryProvider`.
7. Choose `pageSize`, `fetchSize`, and chunk size independently.
8. Create indexes for filters/sorts and inspect execution plans across pages.
9. Enable `saveState` and keep the reader name stable to support restart.
10. Lock in a snapshot/high-watermark if the source can change while reading.
11. Test page boundaries, duplicate keys, composite keys, and restart.
12. Measure query latency, heap, throughput, and database load before increasing concurrency.

| Need | Suitable choice |
|---|---|
| Reading database in batches of rows | `JdbcPagingItemReader` |
| Generating paging SQL per database dialect | `PagingQueryProvider` |
| Ordering by unique primary key | Single ASC or DESC sort key |
| Primary sort column has duplicates | Composite sort key with unique tie-breaker |
| Restarting after committed chunks | `saveState(true)`, stable reader name, and stable sort key |
| Dataset changing while Job runs | Snapshot, high-watermark, or batch membership table |
| Optimizing deep pages | Keyset predicate and suitable index; inspect actual query provider SQL |

## Conclusion

`JdbcPagingItemReader` reads a database page by page using queries generated by `PagingQueryProvider`. `sortKeys` define row ordering, the next page, and restart positions; therefore, sort keys must be stable and unique across each result row. If a column can contain duplicates, use a composite sort key with a unique key as a tie-breaker. Distinguish `pageSize`, JDBC `fetchSize`, and chunk size; create indexes matching filters/sorts; enable state when restart is needed; and define a snapshot or high-watermark when data can change during Job execution. Test multiple pages, duplicate key boundaries, and restarts to ensure no data is missed or duplicated.
