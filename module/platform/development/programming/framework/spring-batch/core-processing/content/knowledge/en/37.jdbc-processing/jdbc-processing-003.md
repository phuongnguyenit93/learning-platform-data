# Paging When Data Changes

In Spring Batch, `JdbcPagingItemReader` reads database data page by page. The reader uses sort keys to determine order and continuation position between pages, but splitting into pages does not automatically create an immutable snapshot of the table. While the Job is running, other transactions can still insert, delete, or update rows that the reader has not yet read.

When data changes between pages, the outcome depends on the paging strategy, sort keys, filter conditions, transaction isolation, and how the Job defines the dataset to process. A Job may miss records, pick up new records appearing mid-run, or see different contents across different pages. If a consistent dataset is required, you must design a snapshot/high-watermark or a mechanism that fixes the run's membership.

## 1. Paging Does Not Equal a Snapshot

Paging addresses how data is fetched in groups. By default, it does not lock the table, hold a single transaction for the entire Job, or freeze every value in the database.

Suppose a Job reads the `orders` table with page size 3:

```text
Initially:
order_id: 10, 20, 30, 40, 50, 60

Page 1: 10, 20, 30
Page 2: 40, 50, 60
```

If another transaction modifies the table after the first page is read but before the next page is queried, page 2 may observe the new state. The final result then does not necessarily reflect the data at a single point in time.

Three concepts should be distinguished:

- **Paging:** splitting a query into pages to limit the amount of data read at once.
- **Checkpoint:** saving the position the reader has reached at a commit boundary so it can restart.
- **Snapshot consistency:** ensuring pages see the same dataset or the same data version as required by business logic.

`JdbcPagingItemReader` supports paging and checkpointing. Snapshot consistency must be provided by transaction isolation, query predicates, database snapshots/versions, or a dedicated staging design.

## 2. JdbcPagingItemReader Resumes from Sort Keys

`JdbcPagingItemReader` uses `PagingQueryProvider` to generate database-appropriate queries. Sort keys determine result order, and the last value of a page is used as the continuation point for the next page. Exact SQL depends on dialect/provider; logically, the provider must fetch rows following the already-read sort key.

Example reading orders by `order_id`:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    Map<String, org.springframework.batch.item.database.Order> sortKeys =
            new LinkedHashMap<>();
    sortKeys.put("order_id",
            org.springframework.batch.item.database.Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, status, amount")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and status = 'READY'")
            .parameterValues(Map.of("tenantId", tenantId))
            .sortKeys(sortKeys)
            .pageSize(500)
            .saveState(true)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("amount")))
            .build();
}
```

`order_id` must be unique over the result set and must not change while the Job runs. If the sort key is not unique, multiple rows can sit at the page boundary and the reader lacks a deterministic total order to continue accurately.

If using multiple columns, such as `created_at` and `order_id`, the sort key tuple must be unique:

```java
Map<String, org.springframework.batch.item.database.Order> sortKeys =
        new LinkedHashMap<>();
sortKeys.put("created_at",
        org.springframework.batch.item.database.Order.ASCENDING);
sortKeys.put("order_id",
        org.springframework.batch.item.database.Order.ASCENDING);
```

`order_id` serves as a tie-breaker when multiple rows share the same `created_at`. The sort key columns must be selected in the query and properly indexed.

## 3. How Does Changing Data Affect Paging?

There are four categories of changes to consider:

1. Insert: new rows are added to the result set.
2. Delete: unread rows are deleted or no longer satisfy the query condition.
3. Update sort key: a row moves to a position before or after the checkpoint.
4. Update filter/payload: a row enters/leaves the result set or its read values change.

The impact depends on how paging continues. With keyset-style continuation by sort key, ordering or filter changes can still cause missing/duplicate data. With offset pagination, inserts/deletes before the offset can also shift the positions of subsequent rows.

## 4. Inserts Between Pages

Suppose the reader uses an ascending sort key and has read the first page up to `order_id = 30`.

```text
Already read: 10, 20, 30
Checkpoint:                 30
```

Then another transaction inserts two rows:

```text
order_id = 15
order_id = 35
```

When the next page starts after key 30:

- Row 15 lies before the checkpoint so it is usually not read in the current run.
- Row 35 lies after the checkpoint so it may be read if the query does not bound the dataset at start time.

This may be right or wrong depending on business logic. If the Job means "read every record existing at start time", picking up row 35 is undesirable. If the Job means "read continuously until available data is exhausted", reading new rows may be acceptable, though a clear stopping rule is needed.

### Why an Ascending Sort Key Is Not Enough

A stable sort key prevents the reader from losing its place, but it does not automatically bound membership. Without an upper bound, each subsequent page can see new rows with keys greater than the checkpoint. If inserts have manually assigned keys or non-monotonic keys, new rows can even appear behind or ahead of the checkpoint despite having smaller values than some existing rows.

## 5. Deletes Between Pages

Suppose the initial set is `10, 20, 30, 40, 50, 60` and the first page read `10, 20, 30`. Before the next page, row 40 is deleted.

With keyset continuation, the next query after 30 returns `50, 60`; row 40 no longer exists to be read. If business logic requires processing every record that existed at start time, the reader cannot satisfy that merely by querying the live table.

With offset pagination, deleting rows before the offset can shift later rows to lower positions. Depending on how the next page's offset is calculated, a row can be read twice or skipped.

If you need to guarantee unchanged membership when the source can delete records, use a snapshot/membership table, soft deletes, or a history mechanism. A deleted row cannot be recovered solely from a sort key checkpoint.

## 6. Updating Sort Keys Can Cause Losses or Duplicates

Sort keys should remain immutable for the duration of the Job's reading. If a sort key changes, a row can move across the checkpoint position.

Example sorting ascending by `order_id`:

```text
Read up to: order_id = 30

An unread row initially has order_id = 45
Another transaction updates order_id to 25
```

That row now sits before checkpoint 30 and can be missed.

The reverse case:

```text
An already-read row initially has order_id = 20
Another transaction updates order_id to 55
```

If queries after the checkpoint search for rows with keys greater than 30, the already-read row can reappear on a later page and be processed twice.

Primary keys are generally better sort keys than editable business columns, but only when the key is truly immutable and unique over the query result. Do not update the key used as a checkpoint while the Job is running.

## 7. Updating Filter Columns Changes Membership

The sort key does not have to change for the dataset to change. Changing a single column in the `WHERE` clause allows a row to enter or leave the result set.

Example:

```sql
WHERE status = 'READY'
ORDER BY order_id ASC
```

If another transaction changes an unread row from `READY` to `DONE`, that row will no longer be returned. If a transaction changes a row from `PENDING` to `READY` after the Job starts and its key is greater than the checkpoint, the row may be picked up on a later page.

Therefore, clarify:

- Is status checked as of the Job's start time or at the time each page is queried?
- Does a row entering `READY` mid-run belong to the current run?
- Should a row leaving `READY` before being read still be processed per the initial snapshot?
- Do records need to be locked/claimed to prevent another Job from processing the same row?

Without clear answers, the Job may produce different results across two runs even with identical initial inputs.

## 8. Updating Payload Changes Read Contents

Even when membership and ordering are stable, selected columns can still change.

For example, the reader already read `order_id = 1001` on the first page. Another transaction updates `amount` before a later page or before a Job restart. Other rows read later may reflect the new state, while row 1001 was already processed with the old value.

The result can be an output aggregated across multiple points in time. If the requirement is to export exact data state at a single point in time, you must snapshot the values, not just the list of IDs.

Options include:

- Database snapshot/temporal query at a specific time or version.
- Copying required columns into a staging/snapshot table when creating the Job.
- Using a version column and rejecting/recording rows modified since the snapshot.
- Using change data capture if the goal is streaming changes rather than a point-in-time snapshot.

## 9. Offset Pagination vs. Keyset Paging When Data Changes

The two approaches behave differently:

| Scenario | Offset pagination | Keyset/continuation by sort key |
|---|---|---|
| Insert before next page position | Can push rows to different offsets, causing duplicates/misses. | New row before checkpoint is usually not read in later pages. |
| Insert after checkpoint | Can shift offsets of subsequent pages. | May be read if predicate matches and no upper bound is set. |
| Delete before next page | Can cause rows to shift positions. | Does not shift checkpoint keys, but the deleted row is no longer read. |
| Update sort key | Can change offset positions. | Can move a row across the checkpoint, causing misses/duplicates. |
| Deep pages | Large offsets can incur high cost skipping many rows. | Often more efficient with an index matching the sort key. |

`JdbcPagingItemReader` uses `PagingQueryProvider` and sort keys to generate dialect-specific queries; providers typically rely on the last sort key values of a page to continue. Do not assume every paging reader automatically creates a snapshot. Inspect the generated queries and the semantics of the provider in use.

Keyset paging avoids some offset-shifting issues, but it does not solve inserts/deletes/updates to membership and payload. To get a snapshot, add a data-freezing mechanism.

## 10. Choosing Immutable and Unique Sort Keys

The sort key is part of the restart contract. A suitable sort key should be:

- Unique for every row of the query result.
- Non-null, or governed by an explicit null rule.
- Unchanging while the Job runs.
- Deterministic in database comparison order.
- Supported by indexes for both queries and continuation predicates.
- Kept in the same ASC/DESC direction across restarts.

For example, if `created_at` can have duplicates, use a composite key:

```sql
ORDER BY created_at ASC, order_id ASC
```

With this tuple, the unique `order_id` acts as a tie-breaker. However, `created_at` should also be immutable. If `created_at` is modified after a row has been read, the tuple can still move across the checkpoint.

Do not use columns like `updated_at`, `status`, or `priority` as sort keys if those values change while the Job runs, unless the application has a versioning/snapshot mechanism ensuring the ordering cannot shift.

## 11. Bounding the Dataset with a High-Watermark

A simple technique to avoid reading newly inserted rows with keys larger than those present at start time is to capture a **high-watermark** before reading and add an upper bound condition to the query.

For example, during Job preparation, fetch the maximum ID for the tenant:

```sql
SELECT COALESCE(MAX(order_id), 0)
FROM orders
WHERE tenant_id = :tenantId
```

Suppose the result is `9000`. The reader uses the condition:

```sql
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id <= :maxOrderId
ORDER BY order_id ASC
```

Rows inserted after capture time with `order_id > 9000` will not enter the Job's read set.

A high-watermark is useful when:

- The sort key is monotonically increasing, or at least new rows are guaranteed to get keys larger than the watermark.
- You want to pin the ID range at the start of the Job.
- A full snapshot of all column values is not required.
- It is acceptable that deletes/updates on older rows can still affect results.

A high-watermark is not a full snapshot. It does not prevent a transaction from assigning a new ID less than or equal to the watermark, does not prevent old rows from being deleted, does not prevent status changes, and does not preserve updated payloads.

## 12. Capturing the High-Watermark Once and Preserving It Across Restarts

Do not recompute `MAX(order_id)` every time the reader reopens. If a restart grabs a new watermark, the dataset for the same `JobInstance` can expand to include rows inserted after the initial run.

You can capture the watermark in a preparation step and store it in the Job `ExecutionContext`:

```java
@Bean
Step captureOrderWatermarkStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("captureOrderWatermarkStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                Long tenantId = contribution.getStepExecution()
                        .getJobExecution()
                        .getJobParameters()
                        .getLong("tenant.id");

                Long maxId = jdbcTemplate.queryForObject(
                        """
                        SELECT COALESCE(MAX(order_id), 0)
                        FROM orders
                        WHERE tenant_id = ?
                        """,
                        Long.class,
                        tenantId);

                JobExecution jobExecution = contribution
                        .getStepExecution()
                        .getJobExecution();

                jobExecution.getExecutionContext()
                        .putLong("orders.maxOrderId", maxId);

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The reader reads back the captured value:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobExecutionContext['orders.maxOrderId']}") Long maxOrderId) {

    Map<String, org.springframework.batch.item.database.Order> sortKeys =
            new LinkedHashMap<>();
    sortKeys.put("order_id",
            org.springframework.batch.item.database.Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, status, amount")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and order_id <= :maxOrderId and status = 'READY'")
            .parameterValues(Map.of(
                    "tenantId", tenantId,
                    "maxOrderId", maxOrderId))
            .sortKeys(sortKeys)
            .pageSize(500)
            .saveState(true)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("amount")))
            .build();
}
```

This illustrates a Job with a capture step running once before the paging step. When restarting from the processing Step, the capture Step is already completed, so the watermark in `JobExecutionContext` is reused. Do not configure the capture step to re-run once completed if the goal is preserving the same input boundary.

Another option is having the launcher pass the watermark as a `JobParameter`. In that case, keep the identifying parameters unchanged across restarts of the same `JobInstance`. Whether using `JobParameters` or the Job `ExecutionContext`, the principle is capturing once and not changing it during that business run.

## 13. When High-Watermark Is Not Enough: Materialize Membership

If records can be inserted with non-monotonic IDs, deleted, or have filter columns modified, `MAX(id)` alone is insufficient to freeze the row set. You can create a membership table for the run:

```sql
INSERT INTO batch_run_order (run_id, order_id)
SELECT :runId, order_id
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY';
```

The reader pages over the pinned membership:

```sql
SELECT o.order_id, o.tenant_id, o.status, o.amount
FROM batch_run_order r
JOIN orders o ON o.order_id = r.order_id
WHERE r.run_id = :runId
ORDER BY o.order_id ASC
```

The set of `order_id`s belonging to the Job is now fixed. However, if the reader joins back to the `orders` table, a row could still be deleted or `amount` could change; stable membership does not equate to stable payloads.

If you need both fixed membership and exact start-time values, copy the required columns into a snapshot table:

```sql
INSERT INTO batch_order_snapshot
    (run_id, order_id, tenant_id, customer_id, amount, status)
SELECT :runId, order_id, tenant_id, customer_id, amount, status
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY';
```

The reader then reads only `batch_order_snapshot` by `run_id` and a unique sort key. You need retention/cleanup for snapshots and an appropriate unique key, such as `(run_id, order_id)`.

## 14. Snapshot Isolation and Transaction Boundaries

Databases have different isolation levels, but you must pay attention to Spring Batch transaction boundaries. In a chunk-oriented Step, transactions are usually committed after each chunk. One page query might run inside one chunk's transaction, while the next page is read in a later transaction.

Consequently:

- `READ COMMITTED` generally allows each statement to see changes committed prior to that statement.
- `REPEATABLE READ` or snapshot isolation has database- and transaction-specific semantics; a snapshot does not automatically span across multiple chunk transactions.
- A Job running multiple chunks does not inherently share a single database snapshot from start to finish.
- Keeping one transaction open for the entire Job can impact locks, undo/version retention, connections, and recoverability; do not do this merely hoping for a snapshot.

If you need a consistent snapshot across multiple pages/chunks, check your specific database's capabilities. You can use a fixed database snapshot/version, temporal/as-of queries, snapshot export/import, a materialized staging table, or a separate data-capture workflow. Do not assume changing the isolation level on the transaction manager alone is sufficient for the entire Job.

## 15. Using Temporal/Versioned Data When Point-in-Time State Is Needed

Some systems store row version history or support querying data at a specific point in time/version. Then the Job can take `snapshotTime`, `version`, or a database-specific SCN/LSN as input and every page reads the same version.

Conceptual query:

```sql
SELECT order_id, amount, status
FROM orders_history
WHERE valid_from <= :snapshotTime
  AND (valid_to > :snapshotTime OR valid_to IS NULL)
  AND tenant_id = :tenantId
ORDER BY order_id ASC
```

This is an application-managed temporal model example, not universal syntax across all databases. With native temporal/as-of features, use vendor-specific syntax and test with the appropriate query provider/paging dialect.

The key point is that every page and every restart must use the same snapshot version. If the snapshot version expires or becomes inaccessible, the Job must fail clearly rather than silently falling back to live data.

## 16. Processing Records by Status and Claim/Locking

Another pattern is having the Job claim records to prevent multiple workers or Jobs from processing them concurrently. For example, a transaction updates the status of a group of IDs from `READY` to `PROCESSING` and tags them with `run_id`:

```sql
UPDATE orders
SET status = 'PROCESSING', batch_run_id = :runId
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id <= :maxOrderId;
```

The reader then pages by `batch_run_id = :runId`. This establishes record ownership, but requires careful design for atomicity, concurrency, and recovery:

- Two Jobs must not accidentally claim the same records.
- Claiming needs appropriate transactions/locking.
- A Job crash needs a process to release or resume old claims.
- Do not transition status to `DONE` before output is committed.
- Handle records that were claimed but failed in the writer.

Some databases support `FOR UPDATE SKIP LOCKED` or similar mechanisms so multiple workers claim distinct rows. This feature is database-dependent; verify isolation, locking, and execution plans before adopting it.

Avoid long-lived locks over millions of rows if they block transactional applications. You can claim in small batches, use lease/owner tokens, or use a staging membership table.

## 17. Data Changing When a Job Restarts

`JdbcPagingItemReader` checkpoints store the continuation position based on reader state and sort keys. They do not store copies of all unread rows. If the database changes before restart, the same checkpoint can yield a different result set.

Example:

```text
First run:
  Read up to order_id 300
  High-watermark = 900
  Checkpoint committed

Before restart:
  Insert order_id 350
  Delete order_id 400
  Update status of order_id 450 from READY to DONE

Restart:
  Resume after 300, with the same watermark 900
```

Outcome:

- `350` may be read even though it did not exist when the Job started if only a high-watermark is used.
- `400` is no longer present to be read.
- `450` no longer satisfies the `READY` filter.

Thus, restarting at the right position does not mean restarting over the exact same dataset. If the requirement is processing the exact initially selected set, preserve membership/snapshots and payloads, or use versioned data.

### Keeping JobParameters and Query Definition Unchanged

Across restarts of the same `JobInstance`, keep unchanged:

- Tenant/business scope.
- High-watermark or snapshot version.
- Filter parameters.
- Sort keys and sort directions.
- Reader name and `saveState`.
- Compatible resource/query contract.

If you change filters or watermarks, create a new `JobInstance` or execute a controlled recovery procedure. Do not reuse an old checkpoint with a query that has different semantics.

## 18. Continuously Arriving Data: Fixing the Batch Boundary

For transactional tables continuously receiving data, the Job needs a clear definition of the "batch of data" being processed.

Ways to pin the batch boundary:

- **High-watermark ID:** process IDs no greater than the value captured at Job start.
- **Business date/window:** process records belonging to a closed date or time interval.
- **Ingestion sequence:** process up to a sequence number confirmed by upstream.
- **Manifest:** upstream delivers a list of completed files or record sets.
- **Membership table:** materialize IDs belonging to the run before paging.
- **CDC offset:** process up to a specific log position/LSN.

Do not rely solely on `created_at <= now()` if source clocks are unsynchronized or data can arrive late with older timestamps. A source-managed ingestion sequence may be more suitable if it reliably reflects commit/ingestion order.

## 19. Late-Arriving Data and Overlap Windows

Some systems receive records late that carry an older business date. If a Job captures one time range and runs once, late-arriving records can be missed.

An overlap window can be used:

```sql
WHERE business_date >= :previousWindowStart
  AND business_date < :currentWindowEnd
```

The next run overlaps a portion of the previous period and deduplicates by business key or version. This works well when upstream has bounded lateness and the target system supports upsert/deduplication.

An overlap window is not a snapshot. It is a strategy for catching late-arriving data by re-reading a portion of data with idempotent processing. You must define maximum lateness, retention, deduplication keys, and update rules for already-exported records.

## 20. Indexes and Performance When Querying by Checkpoint

When data changes, page queries still need indexes supporting both filters and sort keys. Example:

```sql
SELECT order_id, amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id > :lastOrderId
  AND order_id <= :maxOrderId
ORDER BY order_id ASC
```

Illustrative index:

```sql
CREATE INDEX idx_orders_tenant_status_id
    ON orders (tenant_id, status, order_id);
```

Actual indexing depends on the database, selectivity, and workload. Inspect execution plans for both the first page and subsequent pages. If the query uses `OR` conditions for composite sort keys, you may need appropriate indexes or expression rewrites depending on optimizer capabilities.

Select only required columns to reduce I/O and mapping cost. Avoid functions on sort keys if they prevent the database from using the index effectively. Measure query latency, page count, lock waits, and database load with concurrent writers present.

## 21. Testing Data Changes Between Pages

Ordinary tests that simply seed data and read to EOF will not expose race conditions. You must actively mutate data between two pages.

A small fixture with page size 2:

```text
Initially: 10, 20, 30, 40, 50
Page 1: 10, 20
```

After the first page, have another transaction insert/delete/update and then let the reader continue. Scenarios that warrant dedicated tests:

| Change between pages | What to verify |
|---|---|
| Insert key smaller than checkpoint | Row does not silently appear later; late-arrival policy is explicit. |
| Insert key greater than checkpoint but below max | Verify whether inclusion/exclusion matches snapshot policy. |
| Insert key greater than high-watermark | Must not be read if the query enforces the upper bound. |
| Delete unread row | Verify semantics: skipped, failed, or read from snapshot. |
| Update sort key from after to before checkpoint | Expose risk of missing rows. |
| Update sort key from before to after checkpoint | Expose risk of duplicate reads. |
| Update filter status | Verify membership aligns with policy. |
| Update payload | Verify whether snapshot values or latest values are required. |
| Restart after changes | Same checkpoint must use the same snapshot/membership per contract. |

Tests should use a database engine close to production because query providers, isolation, and locking differ across vendors. H2 can be useful for fast tests, but it does not prove paging SQL or snapshot semantics match the production database.

## 22. Synchronizing Tests Without Arbitrary Sleeps

To reproduce changes between two pages, use a deterministic synchronization point:

1. Reader finishes the first page or a test fixture confirms the desired checkpoint has been passed.
2. Test thread executes insert/update/delete in a separate transaction.
3. Mutating transaction commits.
4. Reader continues fetching the next page.
5. Test asserts the exact items read.

You can use `CountDownLatch`, barriers, test hooks, or a mocked service to synchronize. Avoid `Thread.sleep(500)` hoping the reader finished the page; that easily becomes flaky in CI.

If testing restart, create a committed checkpoint, terminate execution in a controlled way, mutate the database, and then restart the same `JobInstance` with identical parameters. Check both outputs and `StepExecution` counters.

## 23. Testing the High-Watermark

High-watermark tests must verify the value is captured exactly once and reused on restart:

1. Seed IDs 10, 20, 30, 40.
2. Run the capture step and confirm watermark is 40.
3. Read the first page up to the checkpoint.
4. Insert ID 50.
5. Restart the same `JobInstance`.
6. Confirm ID 50 is not read because `order_id <= 40`.
7. Confirm the reader still reads the remaining IDs within the pinned range.

Add a test for data violating the monotonic assumption, such as inserting ID 25 after watermark 40 was captured. This test demonstrates that a high-watermark cannot exclude new rows whose keys fall below the upper bound. If that scenario can occur in your system, you need a membership snapshot or a more reliable ingestion sequence.

## 24. Testing the Membership Snapshot

If using a `batch_run_order` table, verify:

- Membership is created in a single consistent transaction as required.
- Each `(run_id, order_id)` appears only once.
- The reader fetches only rows for the matching `run_id`.
- New inserts into the base table after capture do not automatically enter membership.
- Deletes/updates on the base table have defined behavior.
- If the snapshot holds payloads, base-table changes do not alter the run's output.
- Restarts continue reading the same snapshot without regenerating membership.
- Snapshot cleanup runs only after the Job and its restart/reprocess window have ended.

If capturing membership uses `INSERT ... SELECT`, determine the transaction isolation of that statement. A single statement usually sees a snapshot according to database semantics at the time it executes, though exact semantics depend on the engine and isolation level.

## 25. Retry, Idempotency, and Changing Data

Paging checkpoints do not guarantee writer side effects occur exactly once. If a chunk rolls back or the process loses connection during commit, some operations may need retrying or reconciliation.

Especially for writers calling external APIs outside the transaction:

- Use a stable idempotency key per business record/run.
- Store operation IDs to query status after timeouts.
- Use an outbox if database commits and message/API delivery must coordinate.
- Do not rely on `order_id` alone if the same row can be processed across multiple business runs; you may need `(run_id, order_id)`.
- Check output unique keys to prevent duplicates on restart.

If a source row changes after being read, the writer should record the processed version/source timestamp if business logic requires auditing. That distinguishes records exported under an old snapshot from later updates.

## 26. Common Pitfalls

### Thinking Paging Automatically Creates a Snapshot

The reader splits the query into pages, but does not freeze the table. Pin a snapshot/high-watermark or membership if consistent data is needed.

### Non-Unique Sort Key

Rows with duplicate keys at page boundaries can be skipped. Use a unique key or composite key with a tie-breaker.

### Using a Mutable Sort Key

Rows can move across the checkpoint and be missed or duplicated. Prefer immutable keys.

### Not Bounding New Inserts

Keyset queries can read new rows with keys greater than the checkpoint. Use a high-watermark if the monotonic-key assumption holds.

### Assuming High-Watermark Solves All Changes

A watermark does not prevent deletes, filter/payload updates, or inserts with keys below the watermark. Use snapshot/membership when stronger guarantees are required.

### Recomputing the Watermark on Restart

The `JobInstance`'s dataset changes. Capture once and preserve it in `JobParameters`/`JobExecutionContext`.

### Changing Filters or Sort Keys Between Restarts

The old checkpoint no longer matches the old query. Keep the query contract stable or create a new `JobInstance`.

### Relying on Transaction Isolation Without Considering Chunk Boundaries

A chunk transaction's snapshot does not necessarily span the entire Job. Check database semantics and actual transaction boundaries.

### Testing Only Static Data

Race conditions only surface when mutations occur between pages. Write synchronized tests that insert/delete/update between reads.

### Using H2 to Conclude Production Database Behavior Is Identical

Paging providers, locking, and isolation differ. Run integration tests on a database engine close to production for critical semantics.

## 27. Process for Choosing a Paging Strategy When Data Changes

When designing a Job reading a table concurrently updated by other applications, answer these questions in order:

1. Does the Job need data as of start time, or is it acceptable to include new data arriving during the run?
2. Is the sort key unique, non-null, and immutable?
3. Can filter columns change while the Job runs?
4. Can rows be deleted or payloads updated before the reader reaches them?
5. Can a reliable high-watermark be captured?
6. Will the high-watermark exclude all new inserts under the ID allocation rules?
7. Do you need to snapshot membership only, or payloads as well?
8. What isolation/snapshot/temporal queries does the database support, and how do chunk transactions affect them?
9. Do checkpoints and restarts reuse the exact same query parameters, sort keys, and snapshot version?
10. Is the writer idempotent if items are re-read after rollback/restart?
11. Do integration tests simulate inserts/deletes/updates between pages and across restarts?
12. Do indexes and execution plans meet performance requirements under concurrent write workloads?

| Business Requirement | Typically Suitable Strategy |
|---|---|
| Acceptable to pick up new records with larger keys during the run | Keyset paging with stable sort key; clearly define stopping condition. |
| Process only records existing up to an ID boundary | Fixed high-watermark and `key <= watermark` predicate. |
| Pin exact set of IDs at start time | Materialize membership into a staging table. |
| Pin both IDs and payload values | Copy needed data into a snapshot table or use temporal/versioned queries. |
| Handle late-arriving records | Overlap window + deduplication/upsert or CDC. |
| Multiple Jobs concurrently pulling unprocessed records | Claim/lease/locking with clear owner and recovery. |
| Restart after source continues changing | Preserve snapshot/version/membership and checkpoints of the same `JobInstance`. |

## Conclusion

`JdbcPagingItemReader` and `PagingQueryProvider` enable reading data page by page and resuming from sort keys, but they do not automatically guarantee every page sees the same database snapshot. Inserts after the checkpoint can be picked up, inserts before the checkpoint can be skipped, deletes drop unread rows, and updates to sort keys/filters/payloads can alter order, membership, or exported values. Use unique and immutable sort keys, keep queries/parameters stable across restarts, and choose the level of data pinning required: high-watermark for monotonic key ranges, a membership table for fixed ID sets, and a snapshot table or temporal query for payloads as well. Transaction isolation must be evaluated alongside chunk boundaries because a single transaction's snapshot does not inherently span the entire Job. Test inter-page mutations, restarts, and writer idempotency on a production-like database to prove the Job never silently misses, duplicates, or mixes data from different points in time.
