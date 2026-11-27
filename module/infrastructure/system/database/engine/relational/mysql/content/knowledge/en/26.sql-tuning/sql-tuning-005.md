# Optimizing Large OFFSET Pagination with Keyset Pagination

## Objectives

After this lesson, you will be able to:

- Explain why `LIMIT ... OFFSET ...` becomes increasingly expensive as OFFSET grows.
- Use keyset pagination (seek pagination) to fetch the next page based on the key of the last row on the current page.
- Design a stable sort order using one or more columns, always with a unique tie-breaker.
- Write correct continuation predicates for ASC, DESC, and mixed-direction sort orders.
- Design composite indexes aligned with filters and `ORDER BY`.
- Paginate safely with prepared statements, opaque cursors, and high-precision temporal data.
- Handle previous page, next page, filters, JOINs, and data mutations while the user browses.
- Verify effectiveness with `EXPLAIN`, `EXPLAIN ANALYZE`, and boundary test cases.
- Identify when OFFSET remains appropriate and when keyset pagination is the better choice.

## 1. The Problem with Large OFFSET

Paginating with `LIMIT` and `OFFSET` is a familiar pattern:

```sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
```

The next page can use `OFFSET 20`, and page 100 uses `OFFSET 1980`. The syntax is simple and maps easily to numbered page UIs, yet cost grows with page position.

To return 20 rows at `OFFSET 1980`, MySQL typically must locate and discard roughly 1,980 preceding rows before returning the next 20 rows. With a very large OFFSET, the engine still has to traverse many index entries or rows prior to the target position. `LIMIT` caps the number of rows returned, but does not eliminate the cost of skipping the OFFSET.

Example:

```sql
-- First page
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;

-- Very deep page
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 1000000;
```

The second query may have to traverse a huge number of entries before finding the 20 rows to return. Latency generally degrades as the user goes deeper into the list.

### 1.1. OFFSET Can Also Cause Duplicate or Skipped Rows When Data Changes

Suppose the first page returns rows 1–20. Before the user requests page two, a new row is inserted at the top of the list. With `OFFSET 20`, row positions shift; a row at the bottom of page one can reappear on page two.

Similarly, if a row is deleted or its sort position changes, OFFSET can skip a row the user never saw.

This is not a syntax bug. OFFSET specifies a relative position in the result set at the moment each statement executes; it does not remember the identity of the last row the user viewed.

## 2. What Is Keyset Pagination?

Keyset pagination (also called seek pagination or cursor pagination) fetches the next page based on the sort key values of the last row on the current page.

Instead of saying "skip 1,000,000 rows", the application says "fetch the rows after the row with this sort key". MySQL can use an index to seek directly to the cursor position and read a small number of subsequent rows.

Example order list sorted newest first:

```sql
ORDER BY created_at DESC, order_id DESC
```

If the last row on the current page has:

```text
created_at = 2026-11-18 10:30:00
order_id   = 84521
```

The next page needs rows with sort keys smaller than that pair:

```sql
WHERE created_at < '2026-11-18 10:30:00'
   OR (created_at = '2026-11-18 10:30:00' AND order_id < 84521)
```

Then apply the same `ORDER BY` and `LIMIT`:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at < '2026-11-18 10:30:00'
   OR (created_at = '2026-11-18 10:30:00' AND order_id < 84521)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

`LIMIT 21` in the example illustrates a 20-row page: fetching one extra row determines whether a next page exists. Actual cursor values must be passed via prepared statements.

## 3. Sort Order Must Be Uniquely Deterministic

Keyset pagination is reliable only when every row has a deterministic position in the result ordering.

### 3.1. ORDER BY on a Non-Unique Column Is Not Enough

Suppose you sort solely by `created_at`:

```sql
ORDER BY created_at DESC
```

Many orders can be created within the same microsecond or second. When multiple rows share the same `created_at`, their relative ordering is not fully defined. A cursor holding only a timestamp cannot distinguish how far into a tied group reading progressed.

Add a unique key as a tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
```

If `order_id` is a unique key, the pair `(created_at, order_id)` establishes a total order for all rows with non-NULL `created_at`.

### 3.2. The Tie-Breaker Must Be Used Consistently Everywhere

Three parts must align:

1. `ORDER BY` in the SELECT statement.
2. Continuation predicate based on the cursor.
3. Columns and ordering in the supporting index.

If `ORDER BY` is `(created_at DESC, order_id DESC)`, the cursor must store both values and the predicate must evaluate both columns. You cannot use only `created_at` if duplicates can occur.

### 3.3. Choose Stable Sort Columns

Prefer columns that:

- Have deterministic values, typically `NOT NULL`.
- Rarely change after record creation.
- Have clear business ordering.
- Can be supported by an index.
- Combine with a tie-breaker to form a unique order.

If you use a frequently mutated column such as `status`, `priority`, or `updated_at`, rows can cross the cursor boundary between requests. Users may then see duplicate rows or miss rows. Use mutable columns only when the business tolerates such shifts or has a dedicated snapshot mechanism.

## 4. Basic Pattern: First Page and Next Page

Suppose an orders table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_created_id
        (tenant_id, created_at, order_id)
) ENGINE = InnoDB;
```

The index starts with `tenant_id` because queries always filter by tenant, followed by the sorting and continuation columns.

### 4.1. Fetching the First Page

```sql
SELECT order_id, customer_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

If the UI needs 20 rows, pass `LIMIT 21`. The application:

1. Checks the number of rows returned.
2. If there are 21 rows, sets `hasNextPage = true`.
3. Returns only the first 20 rows to the client.
4. Builds the cursor from the 20th row, the last row actually displayed.
5. Never builds the cursor from the 21st row because that row has not been displayed; using it as the cursor would skip it on the next page.

If the query returns at most 20 rows, `hasNextPage = false`.

### 4.2. Fetching the Next Page

Suppose the cursor holds `created_at` and `order_id` of the last row on the current page. With descending order on both columns:

```sql
SELECT order_id, customer_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND (
       created_at < ?
       OR (created_at = ? AND order_id < ?)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

The parameters in order are:

1. Current user's `tenant_id`.
2. `created_at` from cursor.
3. Same `created_at` value from cursor.
4. `order_id` from cursor.
5. `page_size + 1`.

The predicate means:

- Fetch rows with timestamp earlier than the cursor; or
- If timestamp equals the cursor, fetch rows with `order_id` smaller than the cursor.

Since both columns are ordered DESC, smaller values come after the cursor.

### 4.3. Why Use LIMIT page_size + 1?

If you fetch exactly `page_size`, the application cannot tell whether more rows follow without running an extra query. Fetching one extra row determines `hasNextPage` in the same read.

For example, `page_size = 20`:

- 0–20 rows: there is no 21st row, so you can conclude no next page exists.
- 21 rows: return the first 20 rows and set `hasNextPage = true`.

The cursor for the next request is always built from the 20th returned row, never the 21st row.

## 5. Continuation Predicates for ASC and DESC

Comparison operators depend on sort direction.

### 5.1. ASC on a Single Unique Key

With:

```sql
ORDER BY order_id ASC
```

Next page after `last_order_id`:

```sql
WHERE order_id > ?
ORDER BY order_id ASC
LIMIT ?;
```

Larger values follow the cursor.

### 5.2. DESC on a Single Unique Key

With:

```sql
ORDER BY order_id DESC
```

Next page after `last_order_id`:

```sql
WHERE order_id < ?
ORDER BY order_id DESC
LIMIT ?;
```

Smaller values follow the cursor.

### 5.3. ASC on Two Keys

With:

```sql
ORDER BY created_at ASC, order_id ASC
```

Continuation predicate:

```sql
WHERE created_at > ?
   OR (created_at = ? AND order_id > ?)
```

### 5.4. DESC on Two Keys

With:

```sql
ORDER BY created_at DESC, order_id DESC
```

Continuation predicate:

```sql
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
```

### 5.5. General Rule for Multiple Columns

With order:

```sql
ORDER BY a ASC, b DESC, c ASC, id DESC
```

The "after cursor" predicate is a chain of OR branches. Each branch pins preceding columns equal to the cursor values, then compares the current column according to its direction:

```sql
WHERE a > :a
   OR (a = :a AND b < :b)
   OR (a = :a AND b = :b AND c > :c)
   OR (a = :a AND b = :b AND c = :c AND id < :id)
```

Rule:

- `ASC` column: larger values come after the cursor, use `>`.
- `DESC` column: smaller values come after the cursor, use `<`.
- All columns preceding the compared column must equal their cursor values.
- The last column should be a unique key to distinguish all rows.

This is the general pattern to avoid logic bugs when mixing sort directions.

## 6. Handling Mixed Sort Directions

Many lists sort one column descending and another ascending. You cannot use a single comparison operator for every column.

For example, a ticket list showing high priority first, and older tickets first within the same priority:

```sql
ORDER BY priority DESC, created_at ASC, ticket_id ASC
```

Suppose the cursor is `(priority = 5, created_at = '2026-11-01 10:00:00', ticket_id = 900)`.

Continuation predicate:

```sql
WHERE priority < 5
   OR (
       priority = 5
       AND created_at > '2026-11-01 10:00:00'
   )
   OR (
       priority = 5
       AND created_at = '2026-11-01 10:00:00'
       AND ticket_id > 900
   )
```

Parameterized SQL:

```sql
SELECT ticket_id, priority, created_at, subject
FROM tickets
WHERE tenant_id = ?
  AND (
       priority < ?
       OR (priority = ? AND created_at > ?)
       OR (priority = ? AND created_at = ? AND ticket_id > ?)
  )
ORDER BY priority DESC, created_at ASC, ticket_id ASC
LIMIT ?;
```

The index can be designed in the same order:

```sql
CREATE INDEX idx_tickets_tenant_priority_created_id
ON tickets (tenant_id, priority DESC, created_at ASC, ticket_id ASC);
```

MySQL 8.0 supports descending index key parts. When columns share the same direction, InnoDB can also scan an index backward; with mixed directions, the declared direction of each key part can matter to avoid extra sorting. Confirm with `EXPLAIN` rather than relying solely on the index definition.

## 7. Composite Indexes for Keyset Pagination

Keyset pagination shines when both predicates and sort order are backed by an index.

### 7.1. Equality Filters Come Before Sort Keys

If every query filters by one tenant:

```sql
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
```

a suitable index typically begins with the equality filter column:

```sql
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at, order_id);
```

After pinning `tenant_id`, MySQL can read entries ordered by `created_at, order_id`.

### 7.2. Without an Equality Filter

If a system-wide list does not filter by tenant:

```sql
ORDER BY created_at DESC, order_id DESC
```

the index can be:

```sql
CREATE INDEX idx_orders_created_id
ON orders (created_at, order_id);
```

Do not put `tenant_id` first in the index if the query does not fix tenant yet needs global ordering by `created_at`; an unfixed leading column breaks the required sort order.

### 7.3. Status Filters Can Complicate Indexes

If the query is:

```sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
```

you can consider:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at, order_id);
```

This index works well when both `tenant_id` and `status` are equality filters. If status takes multiple values via `IN (...)`, or filtering uses a range on another column, index order needs careful evaluation because it may fail to preserve a single global stream sorted by `created_at`.

### 7.4. Do Not Create a Separate Index for Every Filter Variant

Each index adds storage and write overhead. Profile your main query shapes, frequencies, selectivity, and returned row counts. Prioritize indexes for the most critical access paths.

### 7.5. InnoDB Secondary Indexes Contain the Primary Key

In InnoDB tables, every secondary index entry includes the primary key to locate the clustered record. If `order_id` is the primary key, an index `(tenant_id, created_at)` already carries `order_id` internally as part of the secondary key. Still, explicitly declaring `(tenant_id, created_at, order_id)` can clarify intended index order and support specific plans/orderings. Check actual indexes and EXPLAIN before keeping two near-duplicate indexes.

## 8. Row Constructor Comparison vs Explicit Predicates

MySQL supports row constructor comparisons:

```sql
WHERE (created_at, order_id) < (?, ?)
```

With DESC ordering on both columns, this expression has the same lexicographic meaning as:

```sql
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
```

You can write:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

However, not every row-constructor comparison is optimized for index access as effectively as explicit predicates. With certain composite indexes, a row constructor condition may use only part of the key range. Compare:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (created_at, order_id) < ('2026-11-18 10:30:00.000000', 84521)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

against:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.000000'
       OR (created_at = '2026-11-18 10:30:00.000000' AND order_id < 84521)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

If explicit predicates produce a better access plan on your target version, use that form. Never assume shorter syntax automatically yields a better plan.

## 9. Cursors Must Preserve Exact Sort Values

A cursor is the state needed to continue a query. It must hold every value required to uniquely identify the end-of-page position.

For `ORDER BY created_at DESC, order_id DESC`, the cursor needs at least:

```json
{
  "created_at": "2026-11-18T10:30:00.123456",
  "order_id": 84521
}
```

### 9.1. Preserve Temporal Precision

If the column is `DATETIME(6)`, the cursor must retain full microsecond precision. Truncating to seconds can cause multiple rows sharing the same timestamp to collapse into one position, leading to duplicates or skipped rows.

Values passed to prepared statements must be parsed and bound with the exact type. Do not convert timestamps across timezones or formats in a way that loses precision.

### 9.2. Cursors Should Be Opaque to Clients

An API can encode the cursor as a Base64URL token containing JSON, but Base64 is not security encryption. If the cursor carries tenant IDs, filters, or sensitive metadata, protect its integrity with an HMAC signature or authenticated token mechanism.

Example internal payload:

```json
{
  "v": 1,
  "sort": "created_desc_id_desc",
  "created_at": "2026-11-18T10:30:00.123456",
  "order_id": 84521,
  "filter_hash": "..."
}
```

The server should:

- Verify the cursor signature and version.
- Verify the cursor matches the requested sort mode.
- Bind the cursor to the server-authenticated tenant/user.
- Never trust `tenant_id` inside the token as a substitute for authorization checks.
- Reject malformed, expired, or incompatible cursors.

### 9.3. Keep Filters Consistent Across Pages

A cursor is built for a specific filter set. If page one filters `status = 'PAID'` and the next request omits status or switches to `PENDING`, the cursor position no longer refers to the same result set.

The API should preserve the filter in subsequent requests or store a filter fingerprint inside the cursor to detect mid-stream filter changes from clients.

## 10. Previous Page

Keyset pagination has no natural page numbers like OFFSET. Still, you can support a "Previous page" button if you store the cursor of the current page.

Suppose display order is DESC:

```sql
ORDER BY created_at DESC, order_id DESC
```

To fetch rows preceding the current cursor, flip the predicate direction:

```sql
WHERE created_at > ?
   OR (created_at = ? AND order_id > ?)
```

The query temporarily reads in ASC order to fetch the rows closest to the cursor:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND (
       created_at > ?
       OR (created_at = ? AND order_id > ?)
  )
ORDER BY created_at ASC, order_id ASC
LIMIT ?;
```

The application fetches up to `page_size + 1`, drops the extra row if present, and reverses the result array before rendering so the UI still displays DESC order.

For mixed-direction sorts, flip each column's direction when seeking backward and build the matching predicate. Test carefully, as multi-column OR conditions are error-prone.

### 10.1. Storing Cursors of Visited Pages

If the UI needs to return to the exact page previously viewed, store the start/end cursors of visited pages in client or server navigation history. There is no need to store OFFSET numbers. If a user reloads or opens a fresh link, the API can require a supplied cursor.

## 11. Data Changes During Pagination

Keyset pagination reduces position shifts from inserts/deletes at the top of a list, yet it does not automatically create a consistent snapshot across multiple HTTP requests.

### 11.1. New Rows Inserted Before the Cursor

With newest-first ordering, new rows typically have `created_at` greater than the current page's cursor. The next page uses a smaller-than-cursor predicate, so positions do not shift and previously seen rows do not repeat. New rows normally appear only when the user refreshes from the beginning.

### 11.2. New Rows Inserted After the Cursor

If the application permits inserting data with timestamps older than the cursor, that row can appear on a subsequent page even though it did not exist when the user opened page one. This is not a keyset bug; it is new data falling past the cursor position.

### 11.3. Deleted Rows

Rows deleted before the next request executes will not appear. Keyset does not retain deleted records in results.

### 11.4. Updated Sort Keys

If `created_at`, `priority`, or another sort column changes after a row has been shown, the row can move across the cursor boundary. It may reappear or be skipped depending on the direction of change.

Prefer immutable sort keys. If business rules demand an exact consistent snapshot, use a dedicated snapshot/version mechanism or hold a consistent-read transaction across browsing; the latter rarely suits long-lived HTTP pagination because it keeps transactions and connections open too long.

### 11.5. Bounding with a High-Water Mark

An API can record the highest key from the first page as a high-water mark to prevent newer rows from appearing in subsequent pages. For example, when sorting by `created_at DESC`, capture the top timestamp/id and add a fixed upper bound condition to every request.

A high-water mark only stabilizes the upper boundary. It does not prevent inserts with older timestamps or updates to sort keys. Treat it as a dataset boundary rather than a complete snapshot.

## 12. Keyset Pagination with JOINs

A one-to-many JOIN can paginate at the wrong entity level.

Suppose one order has multiple line items. The query:

```sql
SELECT o.order_id, o.created_at, i.item_id, i.product_id
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
```

`LIMIT 20` applies to post-JOIN rows. One order with 10 items consumes 10 slots; a page might contain only a couple of orders and slice through the middle of an order's items.

If the goal is to paginate orders, paginate the order IDs first, then JOIN details:

```sql
WITH page_orders AS (
    SELECT order_id, created_at
    FROM orders
    WHERE tenant_id = ?
      AND (
           created_at < ?
           OR (created_at = ? AND order_id < ?)
      )
    ORDER BY created_at DESC, order_id DESC
    LIMIT ?
)
SELECT
    o.order_id,
    o.created_at,
    o.customer_id,
    i.item_id,
    i.product_id,
    i.quantity
FROM page_orders AS p
JOIN orders AS o
  ON o.order_id = p.order_id
JOIN order_items AS i
  ON i.order_id = o.order_id
ORDER BY p.created_at DESC, p.order_id DESC, i.item_id;
```

The query illustrates the next page. The first page omits the cursor predicate. The CTE limits the set of orders before expanding to line items.

If you only need to check whether child records exist, consider `EXISTS` instead of a JOIN that multiplies rows.

## 13. Keyset Pagination with DISTINCT, GROUP BY, and Aggregated Results

When a query returns groups or distinct values, the cursor must be based on the post-aggregation sort keys rather than arbitrarily taking keys from the source table.

Example paginating total revenue per customer:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE tenant_id = ?
GROUP BY customer_id
ORDER BY revenue DESC, customer_id ASC
LIMIT ?;
```

The cursor must include both `revenue` and `customer_id`. The next-page predicate must follow the mixed sort order:

```sql
HAVING SUM(total_amount) < ?
    OR (SUM(total_amount) = ? AND customer_id > ?)
```

However, aggregates may have to recompute large amounts of data on every page and may not be directly index-backed. For large reports, consider a summary/materialized table or result snapshot for efficient pagination.

## 14. Counting Total Rows

Keyset pagination does not inherently provide total page count or current page number. If the UI needs a total row count:

```sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = ?;
```

COUNT can be expensive on large datasets, especially when filters are not well supported by indexes. Avoid running COUNT on every request if the UI only needs a "Next" or "Load more" button.

Options:

- Use `page_size + 1` to determine `hasNextPage`.
- Run COUNT only when the user explicitly needs the total.
- Cache the count if data does not change too rapidly and business rules tolerate staleness.
- Maintain a summary table if counts are a critical, high-frequency requirement.

## 15. Comparing OFFSET vs Keyset Pagination

| Criterion | LIMIT/OFFSET | Keyset/seek pagination |
|---|---|---|
| First page | Simple, fast on small datasets | Also simple, requires deterministic order |
| Deep pages | Must skip many rows before target position | Seeks by cursor and reads only a bounded batch |
| Jump directly to page N | Naturally supported | Not naturally supported without prior cursors |
| Sort order | Should have a stable ORDER BY | Requires total ordering and a tie-breaker |
| Inserts at top | Can shift offsets, causing duplicates/skips | Barely affected for subsequent pages after cursor |
| Deletes/sort key updates | Can shift positions | Can still alter results if sort key is mutable |
| Total page count | Easy to pair with COUNT and page numbers | Typically uses cursors and hasNextPage |
| Best-fit APIs | UIs requiring page numbers/random jumps | Feeds, timelines, logs, large lists, load-more |

You do not need to replace OFFSET everywhere. Small OFFSETs, small tables, or UIs requiring arbitrary page jumps remain valid use cases. Prefer keyset for queries that can go deep and have matching sort orders/indexes.

## 16. Cursor API Implementation Flow

A typical API flow:

1. Client calls endpoint with filters, sort, and `limit`.
2. Server authenticates the user and resolves tenant from the verified session/token.
3. If no cursor is provided, server runs the first-page query.
4. If a cursor is provided, server verifies the token, validates matching sort/filter, and decodes key values.
5. Server binds cursor values and filters into a prepared statement.
6. Query fetches `limit + 1` rows using the keyset predicate.
7. Server drops the extra row and builds the cursor from the last returned row.
8. Server returns `items`, `nextCursor`, and `hasNextPage`.

Example response:

```json
{
  "items": [
    {
      "order_id": 84521,
      "created_at": "2026-11-18T10:30:00.123456",
      "total_amount": "1250000.00"
    }
  ],
  "nextCursor": "eyJ2IjoxLCJjcmVhdGVkX2F0IjoiLi4uIn0.signature",
  "hasNextPage": true
}
```

This is an illustrative structure; production tokens need a signature or equivalent authentication. Never trust tenant data from the cursor as the source of access control.

### 16.1. Cap Page Size

The server should enforce a maximum page size, such as 100 or a bound suited to payload and database load. Do not let clients request millions of records by passing a huge `limit`.

### 16.2. Bind Parameters, Never Concatenate Strings

Cursors and filters must be bound via prepared statements. Column names and sort directions generally cannot be bound as values; if the API allows multiple sort modes, map them through a fixed server-side whitelist.

An unsafe pattern is concatenating client-supplied cursor values or sort strings directly into SQL. Parse, validate, and select from predefined query templates.

### 16.3. Versioned Cursors

Including a version in the payload lets the server reject or migrate legacy tokens when the cursor schema changes. Never silently interpret an old cursor under a new sort definition.

## 17. Measuring Performance

### 17.1. Comparing Deep OFFSET vs Keyset

OFFSET:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Keyset:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.123456'
       OR (
           created_at = '2026-11-18 10:30:00.123456'
           AND order_id < 84521
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Compare:

- Actual rows per iterator.
- Loops and timing of each iterator.
- Index chosen.
- Whether filesort occurs.
- Rows read before reaching LIMIT.
- Latency when the cursor is near the beginning, middle, and end of data.

`EXPLAIN ANALYZE` actually executes the query. Use representative data and an appropriate environment, avoiding uncontrolled heavy test runs on production.

### 17.2. Reading Traditional EXPLAIN

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.123456'
       OR (created_at = '2026-11-18 10:30:00.123456' AND order_id < 84521)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Inspect `key`, `type`, `key_len`, `rows`, `filtered`, and `Extra`. If the optimizer does not pick the expected index, review column order, OR predicates, statistics, and data. You can test row constructor comparison to compare plans, then decide based on measurements.

### 17.3. Statistics and Test Data

The optimizer may pick different plans when tables are small, statistics are stale, or data is skewed. Use near-production datasets, refresh statistics when needed with `ANALYZE TABLE`, and measure at multiple cursor positions.

## 18. Edge Cases to Test

- Multiple rows sharing the same timestamp.
- Cursor pointing to the last row of a tied timestamp group.
- First page having fewer rows than page size.
- No rows remaining after the cursor.
- Malformed or tampered cursor.
- Cursor reused with a different tenant or filter.
- Sort column containing NULLs.
- Sort key with microsecond precision.
- Rows deleted between two requests.
- New rows inserted before or after the cursor.
- Sort key updated between two requests.
- Filters using `IN`, JOIN, or low-cardinality columns.
- Queries with one-to-many JOINs.
- Mixed ASC/DESC sorts.
- Previous page requiring proper predicate inversion and result reversal.
- Cursor from an older API version submitted after a sort definition change.

## 19. NULLs in Sort Columns

NULLs complicate continuation logic because `=`, `<`, and `>` against NULL evaluate to UNKNOWN. If a sort column is nullable, ordinary keyset predicates can skip the NULL group or fail to cross the boundary between NULL and non-NULL as intended.

Prefer `NOT NULL` sort keys. If business logic requires nullable columns, standardize NULL ordering explicitly, for example by adding a NULL-classification expression to both the ordering and cursor:

```sql
ORDER BY
    (completed_at IS NULL) ASC,
    completed_at DESC,
    task_id DESC
```

In that case, the cursor must store the NULL flag, `completed_at`, and `task_id`; the continuation predicate must follow each sort direction. You can consider a generated column or functional index if expression indexing is needed, while verifying syntax and plans on your target MySQL version.

Never arbitrarily use `COALESCE(completed_at, 'a dummy date')`. Sentinel values can collide with valid data or break business ordering.

## 20. Common Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| ORDER BY without a tie-breaker | Rows sharing the sort key lack a stable position | Append primary/unique key to ORDER BY |
| Cursor holding only non-unique columns | Can skip rows within tied groups | Store full sort key and tie-breaker |
| Using `>` for DESC ordering | Next page goes the wrong way | Use `<` for DESC; `>` for ASC |
| Mixed-direction sort using one operator for all columns | Predicate does not match display order | Build OR branches per column and sort direction |
| Building cursor from the `page_size + 1` extra row | Extra row gets skipped on next request | Build cursor from the last row actually returned to client |
| Index does not match filter/order | MySQL scans many rows or sorts additionally | Design composite index with equality prefix then sort keys |
| Using row constructor without checking the plan | Optimizer may use only part of a composite index | Compare against explicit lexicographic predicates |
| Mutable sort keys | Rows move across cursor, causing duplicates/skips | Prefer immutable sort keys or use snapshots/versions |
| Cursor loses microseconds | Comparisons lose precision | Preserve full precision of DATETIME/TIMESTAMP |
| Nullable sort column | Comparison predicates mishandle NULLs | Use NOT NULL or explicit NULL ordering |
| One-to-many JOIN before LIMIT | Paginates JOIN rows instead of root entities | Paginate IDs first, then JOIN details |
| Expecting direct jump to page 500 | Keyset has no native offset/page numbers | Use stored cursors, or OFFSET when random page jumps are mandatory |
| Trusting client-supplied cursors | Keys, tenant, or filters can be tampered with | Signed opaque tokens with server-side authorization |

## 21. Pre-Production Checklist

- [ ] Defined explicit sort order and unique tie-breaker.
- [ ] Sort keys prefer `NOT NULL` and immutability.
- [ ] Cursor contains all columns in the sort order.
- [ ] Continuation predicate matches ASC/DESC direction of each column.
- [ ] Index begins with equality filters followed by matching sort keys.
- [ ] Evaluated index cost and write workload.
- [ ] Queries use prepared statements and capped page sizes.
- [ ] Server validates cursor, sort mode, filters, and tenant.
- [ ] Cursor preserves exact data types and precision of sort keys.
- [ ] `LIMIT page_size + 1` is used properly and cursor comes from the last returned row.
- [ ] Defined behavior when rows are inserted, deleted, or updated between requests.
- [ ] One-to-many JOINs are handled after selecting the root entity page.
- [ ] Tested previous page, next page, mixed-direction sorts, and NULLs.
- [ ] Compared deep OFFSET vs keyset using EXPLAIN/EXPLAIN ANALYZE.
- [ ] Appropriate fallback exists if the UI strictly requires jumping to arbitrary pages.

## 22. Conclusion

Large OFFSET forces MySQL to skip many rows before the target position, so cost scales with page depth. Keyset pagination replaces OFFSET positions with the key of the last row on the current page. With a deterministic order, continuation predicates allow MySQL to seek via a composite index and read only a number of rows close to the page size.

A sound design requires a unique tie-breaker, predicates matching ASC/DESC directions, indexes aligned with equality filters and sort keys, cursors preserving exact values, and clear rules for mutating data. Keyset fits feeds, timelines, and large lists well; OFFSET remains useful for shallow pages or UIs requiring arbitrary page jumps. Verify with execution plans and measure on near-production data before deploying.

## References

- [MySQL 8.4 Reference Manual: LIMIT Query Optimization](https://dev.mysql.com/doc/refman/8.4/en/limit-optimization.html)
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
- [MySQL 8.4 Reference Manual: Row Constructor Expression Optimization](https://dev.mysql.com/doc/refman/8.4/en/row-constructor-optimization.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
