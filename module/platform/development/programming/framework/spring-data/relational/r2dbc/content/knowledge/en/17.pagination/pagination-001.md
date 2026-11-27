# Stable Sorting and Adding a Tie-Breaker Key for Duplicate Values

## 1. Why Does Pagination Need a Stable Order?

A query can return multiple rows that match the same condition. When an application displays data page by page, the database must determine which rows belong to the first page and which belong to the next page. Pagination is only reliable when row ordering is clearly defined.

For example, a screen that displays the newest orders first:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

If multiple orders have the same `created_at` value, the database is not obligated to keep them in a specific order. Rows with the same sort value can appear in different orders across executions, depending on the execution plan, index, data, and how the database processes the query.

When the first and second pages are fetched using two separate queries, a row may be duplicated or skipped if tied rows swap positions between the two runs. The solution is to create a **total order** by adding one or more tie-breaker keys, usually the unique primary key, to the end of the ORDER BY list.

For example:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

`created_at` remains the primary business criterion. `id` is the secondary criterion to distinguish rows with the same creation timestamp. If `id` is a unique primary key, each row has a deterministic position in the result order.

In Spring Data R2DBC, this rule applies just as it does to relational SQL in general. Whether using a repository, `R2dbcEntityTemplate`, or `DatabaseClient`, you must ensure deterministic query ordering before paginating.

## 2. What Problems Can ORDER BY Without a Tie-Breaker Cause?

Suppose the `orders` table has the following data:

| id | order_number | created_at |
|---:|---|---|
| 101 | ORD-101 | 2026-11-15 10:00:00 |
| 102 | ORD-102 | 2026-11-15 10:00:00 |
| 103 | ORD-103 | 2026-11-15 10:00:00 |
| 104 | ORD-104 | 2026-11-15 09:59:00 |
| 105 | ORD-105 | 2026-11-15 09:58:00 |

Query:

~~~sql
SELECT id, order_number, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
~~~

The first two rows both have `created_at` equal to 10:00. SQL only specifies that those two rows come before rows with older timestamps; it does not specify that id 101 must come before id 102.

The first run might return:

~~~text
101, 102
~~~

Another run might return:

~~~text
102, 101
~~~

If the second page uses OFFSET 2, row 101 or 102 might appear again or be skipped when the order changes between runs.

The issue is not with LIMIT/OFFSET itself. The issue is that the paginated row set does not have a unique, stable order to apply the offset position to.

Do not rely on:

- The physical order of rows in the table.
- The incidental ID order returned by the database when there is no ORDER BY.
- The original insertion order.
- The order currently produced by a specific execution plan.
- The fact that the current query always seems to return the same order on a development machine.

Only ORDER BY defines result ordering under the SQL contract. If values in ORDER BY are equal, those rows remain tied.

## 3. Creating a Total Order with a Tie-Breaker Key

### 3.1. Adding the Primary Key as the Final Criterion

A common approach is to append the unique primary key to the end of ORDER BY:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Ordering is evaluated from left to right:

1. Compare `created_at` descending.
2. If `created_at` is equal, compare `id` descending.
3. Because `id` is unique, no two rows remain tied after the final criterion.

You can use `id` ascending instead of descending:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Both produce a deterministic order if `id` is unique. Which direction you choose depends on how the application wants to order rows with the same timestamp.

### 3.2. The Tie-Breaker Key Must Be Truly Unique in the Result Set

A field that merely appears unique in current data is not necessarily a safe tie-breaker. For example, `order_number` might be unique per tenant rather than globally unique across the table. If a query filters by a single tenant, the pair `tenant_id` + `order_number` might be unique; if a query spans multiple tenants, all key components must be included in ORDER BY.

For example:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, order_number ASC
~~~

The final order must distinguish every row in the result set. The simplest and usually clearest approach is to use the table's unique primary key as the tie-breaker.

### 3.3. Multiple Secondary Keys May Be Needed

If the unique key is a composite primary key, all key columns must be appended to the end of ORDER BY:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, local_id ASC
~~~

Assuming the primary key is `(tenant_id, local_id)`, that pair distinguishes rows in the table. Adding only `tenant_id` or only `local_id` may not be sufficient.

### 3.4. The Tie-Breaker Key Should Be Stable

A good tie-breaker is typically:

- Non-null.
- Unique within the result set.
- Immutable over the lifecycle of the record.
- Indexed or part of the primary key where appropriate.

Avoid using an editable business field such as a display name as the final tie-breaker without adding a unique key. When that value changes, the row can shift positions across pages.

## 4. How Is Multi-Column Ordering Evaluated?

SQL applies ORDER BY criteria from left to right. Subsequent criteria are only evaluated when preceding criteria are equal.

For example:

~~~sql
ORDER BY status ASC, created_at DESC, id DESC
~~~

This means:

1. Group by `status` ascending.
2. Within the same `status`, newer orders come first.
3. If both `status` and `created_at` are equal, the larger `id` comes first.

This is how you build a deterministic order for a list with multiple business rules.

The following table illustrates this:

| id | status | created_at |
|---:|---|---|
| 14 | ACTIVE | 2026-11-15 10:00 |
| 12 | ACTIVE | 2026-11-15 10:00 |
| 13 | ACTIVE | 2026-11-15 09:00 |
| 18 | INACTIVE | 2026-11-15 10:00 |
| 17 | INACTIVE | 2026-11-15 10:00 |

With `ORDER BY status ASC, created_at DESC, id DESC`, the order will be:

1. ACTIVE, 10:00, id 14
2. ACTIVE, 10:00, id 12
3. ACTIVE, 09:00, id 13
4. INACTIVE, 10:00, id 18
5. INACTIVE, 10:00, id 17

If `id` is omitted from ORDER BY, rows with the same `status` and `created_at` remain tied.

## 5. Ascending/Descending Directions of Each Key Must Match Requirements

Not all columns must share the same direction. You can mix ASC and DESC:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

For example, smaller priority numbers come first, then within the same priority level newer records come first, and finally `id` breaks ties.

When writing keyset pagination predicates, each column's direction affects the comparison operator. For an ASC criterion, subsequent rows have larger values; for DESC, subsequent rows have smaller values. When mixing directions, you must construct the corresponding lexicographic condition for each branch.

Do not change column order or sort direction between pages. The next page cursor is only meaningful when the query uses the exact same set of ORDER BY criteria as the previous page.

## 6. Stable Sorting with R2dbcEntityTemplate

`R2dbcEntityTemplate` lets you declare `Sort` in a `Query`. For an entity with Java properties `createdAt` and `id`, you can write:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(Criteria.where("status").is("ACTIVE"))
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        ))
        .limit(20)
        .offset(0);

Flux<Order> firstPage = template.select(query, Order.class);
~~~

In the mapping API, property names are typically Java field/property names; Spring Data uses metadata to map them to database columns. For example, the `createdAt` property can map to the `created_at` column via a naming strategy or `@Column`.

The key point to remember is that the `id` criterion must be added to `Sort`. If you only use:

~~~java
.sort(Sort.by(Sort.Order.desc("createdAt")))
~~~

then orders with the same `createdAt` remain tied and their order is not fully determined.

You can encapsulate the sort rule into a shared constant or method so all paginated queries for the same use case use the same order:

~~~java
private static final Sort ORDER_PAGE_SORT = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
~~~

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"))
        .sort(ORDER_PAGE_SORT)
        .limit(pageSize)
        .offset(offset);
~~~

This reduces the risk of the first page and subsequent pages accidentally using different sort criteria.

## 7. Derived Queries and Sort in Repositories

With query methods, you can declare `Sort` as a parameter:

~~~java
Flux<Order> findByStatus(String status, Sort sort);
~~~

Caller:

~~~java
Sort stableSort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

return orderRepository.findByStatus("ACTIVE", stableSort);
~~~

Property names in `Sort` are the entity's Java properties. If the entity declares:

~~~java
@Table("orders")
public record Order(
        @Id Long id,
        @Column("created_at") Instant createdAt,
        String status
) {}
~~~

then `Sort` uses `createdAt` rather than the column name `created_at` in metadata-oriented query methods.

In Spring Data R2DBC, query methods can accept a `Sort` parameter and return `Flux`. Verify exact capabilities for your project's Spring Data version, especially when using custom query methods or specific return types.

Do not allow clients to pass arbitrary property names directly into `Sort`. Map sort keys from the API to an allowlist of properties and always append the unique tie-breaker key at the end.

## 8. Sorting with @Query

When writing explicit SQL, ORDER BY must include both the primary criterion and the tie-breaker:

~~~java
@Query("""
    SELECT id, order_number, created_at, status
    FROM orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
    """)
Flux<OrderSummary> findPage(
        @Param("status") String status,
        @Param("limit") int limit,
        @Param("offset") long offset
);
~~~

Here column names are database column names, so `created_at` is used. Because the SQL statement already declares an explicit ORDER BY, a caller's `Sort` parameter does not automatically alter the ordering in this query.

For paginated queries, ensure:

- ORDER BY always ends with a tie-breaker key.
- LIMIT and OFFSET are validated for valid values.
- The same filter and sort are used across consecutive pages.
- If a total record count is needed, the count query uses the same filter conditions.
- Column names and sort directions come from fixed SQL or an allowlist.

Do not concatenate client-supplied sort strings into `@Query`. Bound parameters cannot replace column names or ASC/DESC keywords. If multiple sort orders are needed, create explicit queries or build `Sort` from an allowlist.

## 9. OFFSET Pagination and Deterministic Ordering

OFFSET pagination typically takes the form:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

For example, if `pageSize` is 20:

| Page | LIMIT | OFFSET |
|---:|---:|---:|
| 0 | 20 | 0 |
| 1 | 20 | 20 |
| 2 | 20 | 40 |
| 3 | 20 | 60 |

A total order guarantees that for the same data state and the same filter criteria, positions in the result have deterministic meaning. That prevents arbitrary swapping between rows with identical sort values.

However, a total order does not guarantee that pages fetched at different times see the same data snapshot. If inserts or deletes happen between two requests, OFFSET can still shift.

For example:

1. The first page request fetches rows 1 to 20.
2. A new row is inserted at the top of the list.
3. The second page request uses OFFSET 20.
4. Because an extra row now precedes it, the last row of the first page can reappear on the second page.

Another case is a row being deleted before the offset; a row may be skipped. This is caused by data changing between reads, which is different from the tie-breaker issue.

Therefore, two levels must be distinguished:

- **Deterministic ordering:** the same dataset produces the same row order.
- **Snapshot consistency across requests:** pages see the same data state even though data may change.

ORDER BY with a tie-breaker solves the first level. To achieve a consistent snapshot across multiple queries, you need a transaction/isolation policy or a pagination mechanism suited to the application's requirements.

## 10. Keyset Pagination Also Needs a Total Order

Keyset pagination (also called seek pagination) fetches the next page based on the values of the last row from the previous page, rather than skipping a number of rows with OFFSET.

Example ordering:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

After the current page ends at a row with:

- created_at = 2026-11-15 10:00:00
- id = 120

the next page needs rows that come after that position in descending order:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The condition means:

- Fetch rows with `created_at` smaller than the last row's timestamp of the previous page; or
- If `created_at` is equal, fetch rows with `id` smaller than the last row's id of the page.

The `id` key is required. If you only write `created_at < :lastCreatedAt`, remaining rows sharing the same timestamp as the last row of the page will be skipped.

### 10.1. Why Are All Sort Key Components Needed in the Cursor?

The cursor must contain values for every ORDER BY criterion, including the final tie-breaker.

With:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

the cursor must store:

- `priority` of the last row on the page.
- `created_at` of the last row on the page.
- `id` of the last row on the page.

If only `created_at` and `id` are stored, the application cannot determine the exact position of the row in an order where `priority` comes first.

### 10.2. General Formula for Multi-Column Ordering

Suppose ORDER BY has columns K1, K2, ..., Kn. The next-page predicate takes the form:

~~~text
K1 after cursor
OR (K1 equals cursor AND K2 after cursor)
OR (K1 equals cursor AND K2 equals cursor AND K3 after cursor)
...
OR (K1 ... K(n-1) equal cursor AND Kn after cursor)
~~~

"After cursor" means greater than for ASC and smaller than for DESC. Equality branches must compare strictly according to the database's semantics.

With three keys having directions ASC, DESC, DESC:

~~~sql
WHERE
       priority > :lastPriority
    OR (priority = :lastPriority
        AND created_at < :lastCreatedAt)
    OR (priority = :lastPriority
        AND created_at = :lastCreatedAt
        AND id < :lastId)
~~~

Then use the same ORDER BY:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

This is how keyset pagination extends to multi-column sorting. You must write the conditions in the right order with the right comparison operators for each direction.

## 11. Keyset Pagination with DatabaseClient

Example repository service accepting a cursor:

~~~java
public record OrderCursor(
        Instant createdAt,
        Long id
) {}
~~~

Querying the first page when there is no cursor yet:

~~~java
public Flux<OrderSummary> firstPage(String status, int pageSize) {
    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM orders
            WHERE status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("order_number", String.class),
                row.get("created_at", Instant.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

Next page:

~~~java
public Flux<OrderSummary> nextPage(
        String status,
        OrderCursor cursor,
        int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM orders
            WHERE status = :status
              AND (
                    created_at < :lastCreatedAt
                    OR (
                        created_at = :lastCreatedAt
                        AND id < :lastId
                    )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("lastCreatedAt", cursor.createdAt())
        .bind("lastId", cursor.id())
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("order_number", String.class),
                row.get("created_at", Instant.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

The example uses `DatabaseClient` to make the predicate explicit. In production code, validate the cursor, cap `pageSize`, and handle the empty-result case. When creating the cursor for the next response, use `createdAt` and `id` from **the last row actually returned**, not the first row or unverified values from the request.

If the database returns timestamps with a different precision than the serialized cursor value, comparison mismatches can occur. The cursor must preserve the full precision used by the database/driver; avoid truncating fractional seconds when encoding and sending it back.

## 12. Handling NULL in Sort Keys

Nullable columns introduce an extra complication. In SQL, NULL does not compare like an ordinary value. NULL ordering can vary across databases or depend on `NULLS FIRST`/`NULLS LAST` syntax.

For example:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, id DESC
~~~

PostgreSQL supports `NULLS FIRST`/`LAST` syntax. Other databases may have different syntax or defaults. When portable SQL is needed, a CASE expression can be used:

~~~sql
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END ASC,
    shipped_at DESC,
    id DESC
~~~

The CASE expression places rows without `shipped_at` at the end, then sorts timestamps descending and uses `id` as the tie-breaker.

With keyset pagination, the cursor must account for both the NULL group and the actual sort value. A simple comparison condition:

~~~sql
shipped_at < :lastShippedAt
~~~

does not behave as expected when either side is NULL. Separate condition branches must be constructed for the NULL group, matching the chosen `NULLS FIRST`/`LAST` rule.

Whenever possible, pick a non-nullable sort key for the cursor, or use a generated/computed column with an appropriate default value. This keeps the predicate simpler and less error-prone.

## 13. Collation, Case Sensitivity, and Duplicate Values

Two bytewise-different strings may be treated as equal by a collation during sorting, for example when case-insensitive or accent-insensitive. This can also create tied groups.

For example:

~~~sql
ORDER BY lower(customer_name) ASC, id ASC
~~~

If multiple names have the same value after lowercasing, `id` distinguishes the rows. Similarly, an accent-insensitive collation may treat multiple strings as equivalent when sorting.

When using an expression in ORDER BY, the keyset cursor must use the exact same expression and equivalent semantics. For example, when sorting by `lower(name)`, the cursor needs to store the corresponding normalized value or the predicate must repeat that expression:

~~~sql
WHERE
    lower(customer_name) > lower(:lastName)
    OR (
        lower(customer_name) = lower(:lastName)
        AND id > :lastId
    )
ORDER BY lower(customer_name) ASC, id ASC
~~~

Collation syntax and behavior depend on the database. Determine the sort key according to the query's actual collation, not just by comparing Java strings before sending them to the database.

## 14. Data Changes During Pagination

Even when ORDER BY has a tie-breaker key, data can change between requests.

Scenarios:

- A new record is inserted before the offset position.
- A record is deleted from a previous page.
- A sort field is updated, causing a row to move.
- A status changes, causing a row to enter or leave the WHERE condition.
- A row's timestamp is updated and it moves to a different sort group.

### 14.1. OFFSET Pagination

OFFSET pagination depends on a row's positional index in the entire result set at the time the query runs. When the dataset changes, that position can shift. A tie-breaker resolves ambiguity caused by duplicate values, but does not freeze positions across two requests.

### 14.2. Keyset Pagination

Keyset pagination resumes from the last sort key values. New inserts occurring before the cursor generally do not shift subsequent rows the way OFFSET does. However:

- A new row inserted after the cursor can appear on the next page.
- A deleted row will no longer be returned.
- A row whose sort key changes can jump past the cursor or appear twice depending on the direction of change.
- Filter changes can alter the result set.

Keyset reduces the impact of additions at the top of the list, but it is not a transactional snapshot across the entire pagination journey.

### 14.3. Consistent Snapshots

If the business requires users to browse an immutable dataset across multiple pages, an explicit snapshot strategy is needed. Consider:

- Keeping a transaction with an appropriate isolation level if the read lifecycle is short and the database permits it.
- Capturing a timestamp or high-water mark on the first page and adding a condition bounding records after that mark.
- Using a snapshot/export job that materializes a fixed result set.
- Using data versions or statuses to control which changes can become visible.

Do not hold an open transaction for a long time across multiple HTTP requests if doing so holds connections, snapshots, or locks for too long. Choose a strategy based on consistency requirements and database characteristics.

## 15. Indexes Supporting Pagination Order

A common query:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

You can evaluate an index:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders (status, created_at DESC, id DESC);
~~~

This index places the filter column `status` first, followed by the sort columns `created_at` and `id`. It can support filtering and returning rows in order, depending on the query planner, cardinality, database, and workload.

For keyset pagination, an index matching the filter and sort keys can help the database seek the next range more efficiently. However, an index never replaces ORDER BY; only ORDER BY guarantees result ordering.

Do not create indexes based solely on a single example. Consider:

- Query frequency and read/write ratio.
- Selectivity of the WHERE condition.
- Number of distinct values in filter columns.
- Column order in the composite index.
- Sort directions and the database's ability to scan an index backward.
- Index storage footprint and update overhead.
- Execution plans on realistic data.

Use EXPLAIN or the equivalent tool to verify whether the database uses the index as intended.

## 16. Capping Page Size and Validating Parameters

An overly large page size can produce a heavy result set, retain lots of data in the pipeline, and increase latency. Enforce a maximum limit at the service/API layer.

For example:

~~~java
int normalizedPageSize = Math.max(1, Math.min(requestedSize, 100));
~~~

For OFFSET:

- Page index must not be negative.
- Page size must be positive.
- Offset must be calculated using a wide-enough type to avoid integer overflow at high page indexes.
- Do not let clients send arbitrary offsets exceeding business limits.

For keyset:

- Page size still needs to be capped.
- The cursor must be validated for format and version.
- The cursor must be bound to the exact filter/sort it was created for.
- The cursor must not be allowed to change the tenant or authorization scope.
- Do not trust client-modified sort key values if the cursor affects data scope.

Cursors can be serialized and signed to detect tampering if sent over a public API. Signing a cursor protects token integrity, but does not replace authorization.

## 17. Designing Stable Cursors for APIs

A keyset API might return:

~~~json
{
  "items": [
    {
      "id": 120,
      "orderNumber": "ORD-120",
      "createdAt": "2026-11-15T10:00:00Z"
    }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
~~~

A cursor should encode at least:

- Values of each sort key on the last row of the page.
- Sort direction and sort key names or a sort version identifier.
- The filter or a fingerprint of the filter if needed to ensure the cursor is used with the same query.
- A cursor format version so changes can be supported in the future.

It is not necessary to embed the entire filter in the token; you can bind the cursor to stored filters or sign it with a fingerprint. What matters is not reusing a cursor from one query for another query with a different sort/filter.

Example internal object:

~~~java
public record OrderPageCursor(
        int version,
        Instant lastCreatedAt,
        Long lastId
) {}
~~~

When returning the next page, extract the cursor from the last row:

~~~java
OrderSummary last = items.get(items.size() - 1);

OrderPageCursor next = new OrderPageCursor(
        1,
        last.createdAt(),
        last.id()
);
~~~

If the `Flux` is processed as a stream without materializing the whole page, the last element can be retained in an appropriate coordination structure. Avoid collecting a huge set into a `List` just to extract the cursor; page size must be bounded.

## 18. Common Mistakes in Sorting and Pagination

| Symptom | Common Cause | Resolution |
|---|---|---|
| Rows duplicated or skipped across pages | ORDER BY lacks a tie-breaker key or data changed | Add a unique key; consider keyset/snapshot |
| Rows with the same timestamp swap positions | Sorting only by timestamp | Add primary key as tie-breaker |
| First page and later pages have different orders | Queries use different Sort or lack ORDER BY | Use one unified sort rule |
| Keyset skips rows with the same sort value | Cursor predicate only compares the primary column | Add tie-breaker comparison branch |
| Keyset returns duplicate rows | Predicate has wrong ASC/DESC operator or cursor taken from wrong row | Write lexicographic predicate matching ORDER BY and use last row |
| Cannot retrieve rows with NULL sort key | Comparing NULL with `<` or `>` | Define NULLS FIRST/LAST and add dedicated predicate branches |
| String sort results differ from expectations | Collation or case/accent sensitivity | Check collation and use consistent expressions |
| Large OFFSET grows increasingly slow | Database must skip many rows | Consider keyset and appropriate indexes |
| Dynamic sort causes errors or SQL risk | Concatenating column names from request into SQL | Use property/identifier allowlist |
| Query has an index but remains slow | Index does not match filter/sort or planner chooses another plan | Use EXPLAIN and measure on realistic data |
| Cursor fails after changing filters | Cursor is not bound to query semantics | Bind cursor to filter/sort/version |
| Page size overloads the system | No upper bound on rows per request | Enforce a maximum page size |

## 19. Testing Ordering and Pagination

Do not check only the number of rows on a single page. Verify the correctness of the entire sequence of pages.

### 19.1. Testing Duplicate Sort Values

Create data with multiple rows sharing the same `created_at`:

| id | created_at |
|---:|---|
| 11 | 10:00 |
| 12 | 10:00 |
| 13 | 10:00 |
| 14 | 09:00 |

With `ORDER BY created_at DESC, id DESC` and page size 2:

- First page must be id 13, 12.
- Next page must be id 11, 14.

Rows with the same timestamp are still separated by `id`. With only `ORDER BY created_at`, tests should demonstrate there is no ordering guarantee among 11, 12, and 13.

### 19.2. Testing for No Duplicates and No Gaps on a Static Snapshot

With unchanging data:

1. Fetch all pages using the same filter and sort.
2. Concatenate IDs from every page.
3. Verify there are no duplicate IDs.
4. Verify the ID set equals all IDs matching the filter.
5. Verify the concatenated order matches the total ORDER BY.

### 19.3. Testing Keyset with Many Tied Rows

Create multiple rows with the same primary sort key and set the page size smaller than the number of tied rows. This verifies whether the cursor properly uses the tie-breaker.

For example, five rows with the same `created_at` and page size 2. Pages must sequentially retrieve all five rows without skipping any or returning duplicates.

### 19.4. Testing Concurrent Updates

Create scenarios with inserts/deletes/updates between two page fetches to verify behavior aligns with the application's consistency policy. With OFFSET, position shifts must be accepted or controlled; with keyset, test how sort key and filter changes can affect the cursor.

### 19.5. Testing Against a Real Database

Use Testcontainers or a test database of the same engine to verify ORDER BY semantics, NULLs, collation, timestamp precision, LIMIT/OFFSET, and keyset predicates. H2 or mocks do not necessarily reflect the exact behavior of the PostgreSQL/MySQL/SQL Server in use.

## 20. Workflow for Designing Ordering on a Paginated Endpoint

You can follow this sequence:

1. Identify the primary business criterion, e.g., `createdAt` descending.
2. Identify whether rows can share duplicate values in the primary criterion.
3. Choose a unique tie-breaker key, usually the primary key, as the final criterion.
4. Finalize ASC/DESC directions for each criterion.
5. Define NULL and collation semantics.
6. Use the same order across every page.
7. Choose OFFSET when jumping to page numbers is needed and dataset size is suitable.
8. Choose keyset when sequentially traversing large datasets or reducing shifts from inserts before the cursor.
9. For keyset, store all sort keys in the cursor and write predicates in lexicographic order.
10. Evaluate indexes via query plans and workload.
11. Cap page size and validate cursors/filters.
12. Test duplicate values, NULLs, concurrent writes, and complete page sequences.

## 21. Conclusion

Pagination requires a deterministic order. An ORDER BY on a single column can still leave multiple rows tied if values in that column repeat. Adding a unique tie-breaker key, typically the primary key, at the end of ORDER BY establishes a total order and uniquely determines each row's position in the result.

This rule applies to repository queries, `R2dbcEntityTemplate`, `@Query`, and `DatabaseClient`. With OFFSET pagination, a total order prevents tied rows from swapping places when the dataset does not change; it does not freeze data across requests made at different times. With keyset pagination, the cursor must contain all sort keys and predicates must accurately reflect ASC/DESC order, NULL handling, and collation.

When designing a paginated endpoint, lock down the sort keys, tie-breaker, data semantics, indexes, and concurrent-change policy upfront. Testing with many duplicate values against a real database helps catch row duplication or omission bugs before they surface in the user interface.
