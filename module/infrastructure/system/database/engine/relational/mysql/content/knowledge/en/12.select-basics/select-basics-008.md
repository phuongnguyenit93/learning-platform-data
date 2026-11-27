# LIMIT, OFFSET, and Pagination on Changing Datasets

## Objectives

After this lesson, you will be able to:

- Use `LIMIT` and `OFFSET` to restrict returned row counts and retrieve a page of data.
- Design a stable `ORDER BY` so pages do not shift due to rows with tied sort values.
- Explain why OFFSET pagination can become slow when paginating deeply into large datasets.
- Identify duplicate or skipped row anomalies when data changes between page requests.
- Choose between offset pagination, keyset/cursor pagination, and snapshot pagination.
- Design indexes, count queries, and pagination APIs suited for MySQL and Java applications.

## 1. Why Is Pagination Needed?

An orders table can contain millions of records. If an admin UI requests all orders in a single query, the server must read and transmit a huge amount of data, the application must hold many objects in memory, and users must wait a long time.

Pagination splits results into small chunks, typically of fixed size, such as 20 or 50 rows per page. MySQL provides `LIMIT` to cap the number of returned rows and `OFFSET` to skip a number of initial rows in the result order.

Pagination must solve three problems simultaneously:

1. **Ordering:** which rows belong to the first page, next page, and last page?
2. **Performance:** does the cost of fetching page 500 grow with the page number?
3. **Consistency:** if inserts, deletes, or updates occur while a user navigates pages, will they see duplicates or missing records?

Simply adding `LIMIT` to a query is not enough to solve all three problems.

## 2. LIMIT and OFFSET Syntax

### 2.1. LIMIT Row Count

`LIMIT` caps the maximum number of rows in the result:

```sql
SELECT order_id, customer_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

The query returns at most the 20 newest orders. If the table has only 7 matching rows, the result has 7 rows.

### 2.2. LIMIT with OFFSET

MySQL supports two ways of writing this:

```sql
-- Skip the first 20 rows, take up to the next 20 rows
SELECT order_id, customer_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;

-- Equivalent MySQL syntax
SELECT order_id, customer_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20, 20;
```

In the `LIMIT offset, row_count` syntax, the first number is the number of rows to skip and the second number is the maximum number of rows to fetch. `OFFSET` starts at 0, not 1.

| Page | page size | OFFSET | LIMIT Clause |
|---:|---:|---:|---|
| 1 | 20 | 0 | `LIMIT 20 OFFSET 0` |
| 2 | 20 | 20 | `LIMIT 20 OFFSET 20` |
| 3 | 20 | 40 | `LIMIT 20 OFFSET 40` |
| 10 | 20 | 180 | `LIMIT 20 OFFSET 180` |

### 2.3. Calculating OFFSET from Page Number

If an API accepts a 1-based `page` and a `pageSize` indicating rows per page:

\[
\text{offset} = (\text{page} - 1) \times \text{pageSize}
\]

For example, page 4 with 25 rows per page:

\[
(4 - 1) \times 25 = 75
\]

Corresponding query:

```sql
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 25 OFFSET 75;
```

Applications must validate `page >= 1`, `pageSize > 0`, and enforce a maximum page size limit. Compute offset using a sufficiently wide numeric type and check for overflow before sending the query. Never allow clients to arbitrarily request page sizes of tens of thousands or massive offsets.

## 3. ORDER BY Must Define a Stable Order

### 3.1. LIMIT Does Not Guarantee Order by Itself

Without `ORDER BY`, MySQL does not guarantee returned row order. Results can change due to execution plans, indexes, new data, or server version.

The following query is not reliable pagination:

```sql
SELECT order_id, status, created_at
FROM orders
LIMIT 20 OFFSET 20;
```

To paginate, always specify the desired order:

```sql
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 20 OFFSET 20;
```

However, sorting solely by `created_at` is still insufficient if multiple rows share the same timestamp.

### 3.2. Adding a Unique Key as a Tie-Breaker

Suppose multiple orders are created within the same microsecond. Then `created_at DESC` leaves the order among rows with equal timestamps undefined. MySQL may return tied-timestamp rows in different orders across two runs.

Append the primary key at the end of the sort order:

```sql
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
```

Because `order_id` is a unique key, every row has a deterministic position in the result order, provided the sort values do not change. This is a crucial rule: **pagination ordering must produce a total order**, usually by appending the primary key or a unique key as the final tie-breaker.

### 3.3. NULL Ordering and Collation

If a sort column allows `NULL`, explicitly determine where `NULL` rows belong. MySQL has default rules for `NULL` in `ORDER BY`, though business rules may require otherwise. You can use an expression like `ORDER BY created_at IS NULL, created_at, order_id` to group `NULL`s explicitly; however, this expression can affect direct index usage.

For string columns, order depends on collation. Strings differing in case or accents may be considered equivalent in an insensitive collation. When multiple rows tie under collation rules, append a unique key to break ties. Changing collation can alter pagination order and cursor boundaries.

## 4. How Does Offset Pagination Work?

Suppose a user requests page 100 with 20 rows per page:

\[
\text{OFFSET} = (100 - 1) \times 20 = 1980
\]

MySQL must locate and step past the preceding rows in the required order before returning the next 20 rows. Even though the output contains only 20 rows, locating the starting position may require processing around 2,000 preceding rows or index entries.

```mermaid
flowchart LR
    A[Result order] --> B[Rows 1..1980: skipped]
    B --> C[Rows 1981..2000: returned]
    C --> D[Client receives 20 rows]
```

This is why offset pagination works well for early and shallow pages, but can slow down at large offsets. If the query also has to fetch many columns from the table after scanning the index, costs rise further.

### 4.1. Why Are Large OFFSETs Slow?

Suppose an index supports `ORDER BY created_at, order_id`. To fetch `LIMIT 20 OFFSET 500000`, the server still must traverse a large number of index entries before reaching the 20 rows to return. An index speeds up lookup and ordering, but does not make skipping half a million entries a constant-time operation.

If the query selects columns not contained in the index, MySQL may have to access the corresponding table records during processing. In that case, reading skipped rows can also generate substantial I/O overhead.

### 4.2. Inspecting the Execution Plan

Run `EXPLAIN` on the actual query:

```sql
EXPLAIN
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 500000;
```

Inspect the access `type`, chosen `key`, estimated `rows`, and whether filesort is used. On MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual timings and rows; run it only on safe queries and appropriate environments since it actually runs the `SELECT`.

Do not rely solely on `EXPLAIN` to draw conclusions. Measure latency across multiple offsets on production-scale data and monitor I/O and CPU load.

## 5. Designing Indexes for Offset Pagination

Suppose a query frequently fetches orders from newest to oldest:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
```

An appropriate index might be:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, order_id DESC);
```

The index column order reflects:

1. `customer_id` for the equality predicate in `WHERE`.
2. `created_at` and `order_id` supporting the sort order after filtering by customer.

MySQL 8.0 supports descending indexes. On certain versions or when directions are uniformly reversed, the optimizer may scan an index backward; verify actual behavior with `EXPLAIN`. Do not create an index solely because a query uses `LIMIT`.

If the query returns many columns, you might consider a covering index while balancing storage size and write costs. Overly wide indexes inflate storage, buffer pool usage, and `INSERT`/`UPDATE`/`DELETE` overhead.

### 5.1. Deferred Join for Deep Offsets

A technique to reduce wide-row reads is locating the page's keys via an index first, and only then joining to fetch full columns:

```sql
SELECT o.order_id, o.customer_id, o.status, o.created_at, o.total_amount
FROM (
    SELECT order_id, created_at
    FROM orders
    WHERE customer_id = 1001
    ORDER BY created_at DESC, order_id DESC
    LIMIT 20 OFFSET 50000
) AS page_keys
JOIN orders AS o
  ON o.order_id = page_keys.order_id
ORDER BY page_keys.created_at DESC, page_keys.order_id DESC;
```

The subquery reads only the required key/sort columns, allowing it to use a narrower index. The outer query performs full-row lookups only for the 20 selected keys. This technique can reduce random row lookups for skipped rows, though it still traverses the `OFFSET` index entries. It does not eliminate the linear cost growth of deep offsets.

## 6. What Happens When Data Changes Between Pages?

Offset pagination typically runs each page as a separate `SELECT` statement. If data changes between two requests, row positions can shift.

### 6.1. INSERT Before the Next Page Position Can Cause Duplicates

Assume order `created_at DESC, order_id DESC`, with a page size of 3.

<text weight="semibold">Fetching Page 1</text>

| Position | order_id | created_at |
|---:|---:|---|
| 1 | 105 | 10:05 |
| 2 | 104 | 10:04 |
| 3 | 103 | 10:03 |
| 4 | 102 | 10:02 |
| 5 | 101 | 10:01 |
| 6 | 100 | 10:00 |

The client receives `105, 104, 103`. Before fetching page 2, a new order `106` is inserted with a newer timestamp and lands at the top of the list.

<text weight="semibold">Order After INSERT</text>

| Position | order_id |
|---:|---:|
| 1 | 106 |
| 2 | 105 |
| 3 | 104 |
| 4 | 103 |
| 5 | 102 |
| 6 | 101 |

Page 2 using `OFFSET 3 LIMIT 3` returns `103, 102, 101`. Row `103` appears again even though it was already on page 1. This is the duplicate anomaly caused by position shifting after an insert.

### 6.2. DELETE Before the Position Can Skip Rows

If a row preceding the offset is deleted, subsequent rows shift up by one position. The next page skips the same numeric count and can jump over an unread row.

### 6.3. UPDATE on Sort Columns Can Also Cause Duplicates or Skips

If `created_at`, `status`, ranking score, or any column in `ORDER BY` is modified between pages, a row can move from the unread portion to the already-read portion or vice versa. Ordering with a unique key guarantees determinism only while sort values remain unchanged; it does not freeze the dataset.

### 6.4. OFFSET Is Not a Cursor

`OFFSET` merely specifies how many rows to skip in the current result set. It does not remember the last row the client received. When the dataset changes, a numeric offset can point to a different group of rows.

If business logic tolerates newly appearing data or minor shifts between pages, offset pagination may still be suitable. To prevent position shifts when new rows are inserted, consider keyset pagination. To guarantee a completely consistent dataset throughout reading, you need a snapshot or a data-versioning mechanism.

## 7. Keyset Pagination (Cursor Pagination)

Keyset pagination fetches the next page based on the values of the last row from the previous page, rather than counting rows to skip.

Assume the ordering:

```sql
ORDER BY created_at DESC, order_id DESC
```

After fetching the first page, the client records the value pair of the last row, for example:

```text
last_created_at = 2026-11-18 09:30:00.123456
last_order_id   = 8120
```

The next page fetches rows whose sort keys are smaller than that cursor pair:

```sql
SELECT order_id, customer_id, status, created_at
FROM orders
WHERE customer_id = 1001
  AND (created_at, order_id) < ('2026-11-18 09:30:00.123456', 8120)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Because both columns are sorted descending, the tuple comparison `<` selects rows appearing after the cursor in that order. You can write the equivalent condition explicitly:

```sql
WHERE customer_id = 1001
  AND (
      created_at < '2026-11-18 09:30:00.123456'
      OR (
          created_at = '2026-11-18 09:30:00.123456'
          AND order_id < 8120
      )
  )
```

Tuple comparison requires columns and sort directions compatible with the cursor logic. For mixed `ASC`/`DESC` ordering, the condition must be written out explicitly by branch; do not mechanically apply a tuple comparison.

### 7.1. First Page and Subsequent Pages

The first page has no cursor:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Subsequent pages pass the cursor taken from the last row of the previous page:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 1001
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Cursor values must come from the actual last row returned, not a 20th row counted differently. Preserve full timestamp precision, including microseconds if the column is `DATETIME(6)` or `TIMESTAMP(6)`.

### 7.2. Indexes for Keyset Pagination

An index matching the filter and ordering above:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, order_id DESC);
```

After filtering by `customer_id`, MySQL can seek directly to the cursor position in the sorted index slice and read roughly the page size of entries. With a matching index, cost does not grow linearly with page number like deep `OFFSET` does.

Still verify with `EXPLAIN` and benchmark in practice. If extra filter predicates are added, the index may need redesigning in the order of equality predicates, range/cursor columns, and ordering. No single index fits all query variants.

### 7.3. How Do New INSERTs Affect Keyset Pagination?

With descending order and a saved cursor, a new row inserted at the top of the list (greater than the cursor) will not appear in subsequent pages of the same cursor stream. Older rows behind the cursor are not pushed across page boundaries by offset counting.

However, keyset pagination does not freeze the data:

- Newly inserted rows behind the cursor can appear in subsequent pages.
- Deleted rows will no longer appear.
- If sort columns of already-read or unread rows are updated, rows can cross the cursor boundary and be duplicated or skipped.
- If filter criteria change between requests, the result set also changes.

For keyset pagination to behave predictably, prefer immutable sort keys that are `NOT NULL` (or follow explicit `NULL` rules), and include a unique tie-breaker key.

## 8. Cursors with Ascending Order, Multiple Columns, and NULLs

### 8.1. Ascending Order

With:

```sql
ORDER BY created_at ASC, order_id ASC
```

The next page retrieves rows greater than the last cursor:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE (created_at, order_id) > (?, ?)
ORDER BY created_at ASC, order_id ASC
LIMIT 20;
```

### 8.2. Multiple Sort Columns

With descending order on `priority`, followed by ascending order on `order_id`:

```sql
ORDER BY priority DESC, order_id ASC
```

A single tuple `<` cannot be used across all columns because the sort directions differ. The "after cursor" condition must be written branch by branch:

```sql
WHERE priority < ?
   OR (priority = ? AND order_id > ?)
ORDER BY priority DESC, order_id ASC
LIMIT 20;
```

The index should match the ordering and filters, such as `(priority DESC, order_id ASC)` on versions supporting descending indexes. Inspect the execution plan to confirm.

### 8.3. Cursors and NULL Columns

Tuple comparisons containing `NULL` components can evaluate to `UNKNOWN`, so do not use a tuple cursor directly when sort columns can be `NULL` without defining handling rules.

Options:

- Design sort keys as `NOT NULL` if business rules allow.
- Add an explicit `NULL`-grouping expression and include both the `NULL` flag and key values in the cursor.
- Split queries to process the `NULL` group and non-`NULL` group separately.

Example placing non-`NULL` values first and `NULL` values last in ascending order:

```sql
ORDER BY (created_at IS NULL), created_at, order_id
```

The cursor must include both the `(created_at IS NULL)` flag and the subsequent values. Because sort expressions may require functional indexes or alternative index support, evaluate with `EXPLAIN` before using on large tables.

## 9. Snapshot Pagination When a Consistent Dataset Is Needed

Offset or keyset pagination across multiple HTTP requests usually runs in separate transactions. If business requirements demand that all pages reflect the exact same data snapshot, you need a mechanism to hold a snapshot or version the dataset.

### 9.1. Snapshot Within a Single InnoDB Transaction

For consistent reads on InnoDB at an appropriate isolation level (typically `REPEATABLE READ`), you can establish a consistent snapshot and read multiple pages within the same transaction and connection:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;

-- Continue reading another page on the same connection/transaction
SELECT order_id, status, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;

COMMIT;
```

Consistent reads inside the transaction share the same snapshot under InnoDB rules. Do not use `FOR UPDATE` when your goal is consistent nonlocking reads; locking reads have different semantics.

The drawback is that long-running transactions hold old snapshots, which can prevent undo history from being purged in time and raise operational overhead. Never keep a transaction open for minutes or across multiple user interactions just for page clicks.

### 9.2. Snapshots Cannot Automatically Span Arbitrary Connections

If each HTTP request checks out a different connection from a pool, each request typically runs in its own transaction/snapshot. Opening a transaction in the first request and returning the connection to the pool does not guarantee the next request continues the same transaction. Holding a connection and transaction open while a user reads pages ties up resources and creates long-transaction risks.

When exporting a long-lived consistent report, consider:

- Materializing a data snapshot into a dedicated table or export artifact and paginating over that snapshot.
- Capturing a watermark such as `MAX(id)` at the start, if keys are monotonically increasing and the target data is append-only or other mutations are acceptable.
- Using a versioning system or effective timestamp (`as_of`) if business rules require historical queries.
- Using a short snapshot transaction inside a dedicated export job rather than holding a transaction open across UI interactions.

A watermark `id <= max_id` only prevents records with IDs above the cutoff from entering the stream. It does not prevent updates or deletes on older rows, does not guarantee snapshots across related tables, and does not fit if issued IDs do not reflect commit order. Document these limitations clearly in the design.

## 10. Counting Total Rows and Determining Whether a Next Page Exists

### 10.1. COUNT(*) to Display Total Pages

An offset API may need the total number of matching rows:

```sql
SELECT COUNT(*) AS total_rows
FROM orders
WHERE customer_id = 1001;
```

The page count is calculated as:

\[
\text{totalPages} = \left\lceil \frac{\text{totalRows}}{\text{pageSize}} \right\rceil
\]

On large tables with complex filters, `COUNT(*)` can be expensive. In InnoDB, table-wide row counts are not maintained as a free exact figure for arbitrary queries. If the UI only needs a "Next" button, counting all rows is unnecessary.

### 10.2. Fetching One Extra Row to Determine hasNext

If the page size is 20, query 21 rows:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC, order_id DESC
LIMIT 21 OFFSET 0;
```

If 21 rows are returned, return the first 20 rows and set `hasNext = true`. If at most 20 rows are returned, set `hasNext = false`. With keyset pagination, the same pattern applies: use `LIMIT pageSize + 1`, drop the extra row from the response, and build the cursor from the actual last row returned to the client.

### 10.3. COUNT and the Data Page May See Different Timestamps

If `COUNT(*)` and the page query execute in two separate transactions, data can change between the two statements. In that case, `totalRows` may not exactly match the row set the page is displaying. If the UI tolerates an approximate point-in-time total, this is usually minor. If strict consistency is required, use the same snapshot or a snapshot dataset mechanism.

## 11. Pagination in APIs and Java JDBC

### 11.1. Offset API

A request may receive:

```json
{
  "page": 2,
  "pageSize": 20,
  "sort": "newest"
}
```

The server must:

- Validate that `page` and `pageSize` are valid integers.
- Enforce a page size limit, such as a maximum of 100 depending on the endpoint.
- Compute offset with a wide enough numeric type, checking for overflow.
- Choose the sort order from a server-defined allowlist.
- Bind `LIMIT`/`OFFSET` values via prepared statement parameters if the driver supports parameter markers in those positions.
- Never concatenate untrusted input directly into SQL.

### 11.2. Prepared Statements with LIMIT/OFFSET

Java JDBC example:

```java
String sql = "SELECT order_id, status, created_at "
           + "FROM orders "
           + "WHERE customer_id = ? "
           + "ORDER BY created_at DESC, order_id DESC "
           + "LIMIT ? OFFSET ?";

long page = 2;
int pageSize = 20;
long offset = Math.multiplyExact(page - 1, (long) pageSize);

try (var statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setInt(2, pageSize);
    statement.setLong(3, offset);

    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long orderId = result.getLong("order_id");
            String status = result.getString("status");
            // Map remaining columns as needed
        }
    }
}
```

This example assumes `page >= 1` has been validated, `pageSize` is within limits, and the MySQL driver supports bind markers for `LIMIT`/`OFFSET`. If a specific driver or library does not, check that version's documentation and insert only validated integers safely into the SQL.

### 11.3. Dynamic ORDER BY Must Use an Allowlist

Column names cannot be bound using placeholders:

```sql
-- Does not work as identifier binding
SELECT order_id, status
FROM orders
ORDER BY ?
LIMIT ?;
```

`ORDER BY ?` sorts by a constant parameter value rather than substituting an identifier. In Java, map the sort option to a fixed SQL fragment:

```java
String orderBy = switch (sort) {
    case "newest" -> "created_at DESC, order_id DESC";
    case "oldest" -> "created_at ASC, order_id ASC";
    case "amount" -> "total_amount DESC, order_id DESC";
    default -> throw new IllegalArgumentException("Unsupported sort option");
};

String sql = "SELECT order_id, status, created_at, total_amount "
           + "FROM orders WHERE customer_id = ? "
           + "ORDER BY " + orderBy + " LIMIT ?";
```

Only concatenate server-generated `orderBy` strings from an allowlist—never concatenate raw client-supplied sort strings. Each sort option needs a unique tie-breaker and may require its own index.

### 11.4. Cursor API

Keyset APIs typically return an opaque cursor instead of a page number:

```json
{
  "items": [
    { "orderId": 8121, "status": "PAID" },
    { "orderId": 8120, "status": "PENDING" }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi...",
  "hasNext": true
}
```

The cursor can encode sort keys, filters, or query version. The server should sign or validate the cursor if clients are not permitted to alter its values; a cursor is not an authorization mechanism. Every request must still authenticate the user and enforce tenant/customer conditions server-side.

## 12. Choosing a Pagination Strategy

| Criterion | Offset pagination | Keyset/cursor pagination | Snapshot pagination |
|---|---|---|---|
| Jumping to an arbitrary page | Convenient | Harder; usually next/previous via cursor | Possible, depending on snapshot storage |
| Performance on deep pages | Can degrade sharply due to skipping many rows | Usually much steadier with matching indexes | Depends on snapshot mechanism and indexes |
| New INSERTs before current position | Can cause duplicates or skips | Usually does not shift existing cursors | Does not alter the captured snapshot |
| UPDATE/DELETE on existing data | Can shift positions | Can move rows across the cursor or remove them | Snapshot retains old view per storage mechanism |
| Counting total pages | Easy to pair with COUNT, though COUNT has cost | Usually no total page count needed | Can count on the snapshot |
| Application complexity | Low | Requires building, encoding, and validating cursors | Higher, requires snapshot lifecycle management |
| Best-fit use cases | Medium tables, shallow pages, page-jumping UI | Feeds, transaction history, large stably ordered lists | Exports, reconciliation, or reports needing a consistent dataset |

There is no single best strategy for every endpoint. Choose based on navigation requirements, data scale, mutation rate, and the consistency users need.

## 13. Pagination Design and Testing Workflow

1. **Define business ordering:** choose sort columns and a unique tie-breaker.
2. **Assess mutation rate:** is data inserted, updated, or deleted while users navigate pages?
3. **Choose the mechanism:** offset for shallow pages and direct page jumping; keyset for large lists; snapshot for consistent exports.
4. **Design indexes:** place equality filter columns before cursor/sort columns matching the query.
5. **Constrain inputs:** max page size, valid page numbers, overflow-safe offset, and sort allowlist.
6. **Measure across depths:** compare first page, middle pages, and very deep pages on production-scale data.
7. **Test concurrency:** insert at the top, delete before the cursor, update sort keys, and change filters between page fetches.
8. **Verify correctness:** no duplicates or missing items outside business-accepted behavior; cursors always advance forward.
9. **Monitor:** track latency, rows examined, filesort usage, deep-page requests, and page-navigation depth.

A minimal test suite should include multiple rows sharing the same timestamp, ascending/descending keys, `NULL` values if permitted, a short final page, a page beyond available data, interleaved inserts/deletes, and rows with changing sort keys.

## 14. Conclusion

`LIMIT` and `OFFSET` offer a simple way to split results into pages, but they must be paired with a deterministic `ORDER BY`. Large offsets can become expensive because MySQL still has to traverse skipped rows or index entries. When data changes between requests, numeric row positions can shift and cause duplicates or gaps.

For large lists, keyset pagination uses the last row's values as a cursor along with a suitable index to advance efficiently. When a consistent dataset across the entire read is required, use a snapshot or data-versioning mechanism. Regardless of which approach you choose, test against realistic changing data, validate inputs, and verify execution plans before deploying.
