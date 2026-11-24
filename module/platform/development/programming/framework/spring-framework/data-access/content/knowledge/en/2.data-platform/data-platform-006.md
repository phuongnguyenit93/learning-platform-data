# Result Ordering Is Guaranteed Only When the Query Properly Requests It

> **Core principle:** Queries return rows without an inherent guaranteed order. If the application needs "newest first," "lowest price first," "alphabetical by name," or consistent pagination, the query must express the appropriate ordering requirement. In SQL, the primary mechanism is `ORDER BY` on the **final result-returning query**; when multiple rows share the same sort key, add a tie-breaker key sufficient to distinguish rows.

## 1. Why Can Results Look Ordered Yet Not Be Guaranteed?

A relation in the relational data model has no concept of "first row" or "20th row" unless an ordering criterion is specified. For a SQL statement without `ORDER BY`, the database management system (DBMS) is allowed to return matching rows in an order dictated by the execution plan.

A query may **coincidentally** produce rows ordered by ascending `id`, insertion time, index order, or physical storage position. The exact same query can change order when:

- A new index or updated statistics cause the optimizer to switch table-reading plans.
- The DBMS switches between table scans, index scans, hash/merge/nested-loop joins, or parallel execution.
- Rows are inserted, deleted, updated, or reorganized.
- The query adds `LIMIT`/`OFFSET`, changes filters, or upgrades DBMS version/configuration.

**Order must never be inferred from** primary keys, `INSERT` order, clustered indexes, `GROUP BY`, `DISTINCT`, physical location, or the fact that prior runs "always looked right." Indexes can improve sort performance, yet an index's mere existence creates no ordering contract for query results.

In a Spring application, `JdbcTemplate` and data mappers read rows in the order the DBMS emits them. They do not automatically turn a SQL query lacking `ORDER BY` into a business-ordered query. A `List` having a particular element order on the current read **does not mean** the DBMS promised that order for future queries.

## 2. Concrete Data Illustration

The examples use PostgreSQL syntax; `LIMIT`, `NULLS LAST`, and tuple comparisons in later sections may need adjustments for other databases.

```sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO orders (id, customer_id, created_at, total_amount) VALUES
    (101, 7, '2026-10-28 09:00:00', 100.00),
    (102, 7, '2026-10-29 08:00:00', 130.00),
    (103, 7, '2026-10-29 08:00:00', 150.00),
    (104, 7, '2026-10-30 12:00:00', 170.00),
    (105, 7, '2026-10-30 12:00:00', 190.00),
    (201, 8, '2026-10-30 12:00:00', 210.00);
```

### Case A: No Ordering Requested

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7;
```

The result set contains five rows with `id` 101–105, yet **there is no guarantee** that row 101 comes first or 105 comes last. An order observed in the current environment is not a condition you can encode into production code, tests, or API contracts.

### Case B: `ORDER BY` Present, Yet Tied Values Remain

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC;
```

Results are sorted descending by `created_at`, but pair 104/105 shares the same timestamp and pair 102/103 shares the same timestamp. The DBMS may return 104 before 105 or vice versa while still fully complying with `ORDER BY`. **Sorting by a non-unique key does not establish a total order.**

### Case C: Sorting with Enough Keys to Distinguish Rows

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC;
```

On the dataset above, the `id` sequence is fixed as **105, 104, 103, 102, 101**. The DBMS compares `created_at` first and compares `id` only on ties. Because `id` is a unique, non-`NULL` primary key, two distinct rows cannot tie on both criteria. This is a deterministic order **for the same data state and comparison semantics**.

When you only want the three newest orders:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 3;
```

The ordered result is **105, 104, 103**. Putting `LIMIT 3` without an appropriate `ORDER BY` merely means "return up to three arbitrary matching rows," not "the three newest rows."

## 3. What Makes an `ORDER BY` "Appropriate"?

1. **Matches business meaning.** "Newest" is usually `created_at DESC`; "lowest price" is `total_amount ASC`; "name A–Z" requires considering string comparison/collation rules. Do not blindly use `id DESC` as a synonym for "newest" if IDs are not guaranteed to reflect business time.
2. **Applied at the right result scope.** Place `ORDER BY` on the outer query producing the rows the application receives; sorting only inside a subquery/CTE does not guarantee the outer result's order.
3. **Includes a tie-breaker key when strict stability is needed.** If sorting by `created_at`, `score`, or `status` can tie, append a unique key such as `id`. The key tuple should establish a total order over returned rows.
4. **Specifies direction explicitly.** `ASC` is ascending, `DESC` is descending; directions can be mixed: `ORDER BY priority DESC, created_at ASC, id ASC`.
5. **Handles `NULL`, casing, diacritics, and collation per DBMS.** `NULL` placement and string comparison differ across DBMSs, locales, and collations. If part of an API contract, design and test it explicitly.

PostgreSQL example when `created_at` may be null:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC NULLS LAST, id DESC;
```

`NULLS LAST` explicitly controls `NULL` placement in PostgreSQL; **do not copy it verbatim** to DBMSs that do not support this syntax. When comparing Vietnamese names, check the collation in use; `ORDER BY name` does not automatically yield the exact dictionary order the product expects.

Note that `ORDER BY` governs **the order of rows**. It does not guarantee element order inside an aggregated array/JSON column, nor element order inside a separately loaded ORM collection; those structures have their own ordering mechanisms.

## 4. Misleading SQL Constructs

| Construct | What Is Actually Guaranteed |
| --- | --- |
| `SELECT ... WHERE ...` without `ORDER BY` | Only filtering conditions; row order is undefined. |
| `ORDER BY created_at DESC` | Descending timestamp order; rows with identical timestamps can still swap. |
| `ORDER BY created_at DESC, id DESC` with unique `id` | Total order over the queried data state. |
| `LIMIT n` or `OFFSET m` without unambiguous sorting | Picks/slices from an unguaranteed order; does not stably represent "top n" or "page m". |
| `GROUP BY`, `DISTINCT`, `UNION` | Groups, deduplicates, or combines data; does not implicitly sort the final result by key. |
| `JOIN`, indexes, primary keys | May influence access paths, yet never replace an outermost `ORDER BY`. |
| `ORDER BY` inside a subquery | May serve local logic, while an outer query needing guaranteed order must still state its own `ORDER BY`. |
| Sorting a `List` after querying | Only sorts rows already loaded into Java; does not ensure the right top N / page N was picked from the DB. |

For aggregate queries, explicit ordering can be requested at the outer level:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC, customer_id ASC;
```

The sample data returns customer 7 (5 orders) before customer 8 (1 order). That order comes from `ORDER BY`, **not** from `GROUP BY`.

## 5. In Spring Framework JDBC: SQL Must State the Order

`JdbcTemplate` accepts SQL, executes it via JDBC, and applies `RowMapper` to each row in the `ResultSet` sequence provided by the driver. It does not inject any business sorting criterion on its own.

The example below is `OrderReader.java` for **a Java 17+ project that already has Spring JDBC and a configured `JdbcTemplate`** (for instance, a Spring Boot app with the JDBC starter and a `DataSource`). It is a data-access class for project integration, not a standalone `main` program runnable with plain `javac`.

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReader {
    private final JdbcTemplate jdbcTemplate;

    public OrderReader(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderRow> newestForCustomer(long customerId, int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }

        String sql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        return jdbcTemplate.query(
            sql,
            (rs, rowNum) -> new OrderRow(
                rs.getLong("id"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getBigDecimal("total_amount")
            ),
            customerId,
            limit
        );
    }
}

record OrderRow(long id, LocalDateTime createdAt, BigDecimal totalAmount) {}
```

Points to read accurately:

- `WHERE customer_id = ?` and `LIMIT ?` use bound parameters rather than concatenating user values into SQL; `LIMIT ?` is supported by PostgreSQL in this context.
- `ORDER BY created_at DESC, id DESC` is what requests the ordering. `RowMapper` merely turns each row into an `OrderRow`; the returned list preserves the `ResultSet` read order.
- Calling `newestForCustomer(7, 3)` on the sample data with no concurrent changes yields a list with IDs **105, 104, 103** in exact order. This is derived from the given data and SQL, not stdout from a standalone program.
- For DBMSs other than PostgreSQL, adapt row-limiting syntax to the dialect. Even when only one row is wanted, you still must define what "first" means before selecting it.

`NamedParameterJdbcTemplate` or `JdbcClient` can make writing queries more convenient, while the rule stays unchanged: **the SQL sent to the DB must specify the required order**. If reading with a `ResultSetExtractor` that constructs an unordered collection (such as `HashSet`), order can still be lost in Java despite valid SQL.

## 6. With Spring Data JPA: Requesting Sorting in Repository/Query

Spring Data JPA belongs to the Spring Data ecosystem and is **not a built-in API of Spring JDBC**. When a project uses JPA repositories, ordering can be declared via query methods, `Sort`, `Pageable`, or JPQL `ORDER BY`.

Illustrative integration snippet in an app that already has an `OrderEntity` with `customerId`, `createdAt`, and `id` properties:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    Page<OrderEntity> findByCustomerId(long customerId, Pageable pageable);
}

// Inside a service that has a repository variable of type OrderRepository:
Sort ordering = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Page<OrderEntity> page0 = repository.findByCustomerId(
    7L,
    PageRequest.of(0, 20, ordering)
);
```

The `PageRequest` snippet is usage code **inside a service method** (not free-standing statements outside a Java class); compiling requires an actual `OrderEntity` and Spring Data JPA. `createdAt` is the **Java entity property name**, not necessarily the SQL column name `created_at`.

Similarly, you can define a method with static ordering if the business contract is fixed:

```java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    List<OrderEntity> findByCustomerIdOrderByCreatedAtDescIdDesc(
        long customerId
    );
}
```

When writing queries with `@Query`/JPQL, check clearly whether `ORDER BY` is statically provided or combined with a dynamic `Sort`; do not assume every native SQL or custom query supports attaching `Sort` identically. When letting clients choose sort order, accept only an allowlisted set of properties—such as `createdAt` or `totalAmount`—and still append a tie-breaking identifier key. Never interpolate raw user `sort` parameters into an `ORDER BY` string.

**Important distinction:** `findAll()` or `findByCustomerId(...)` without a sort definition does not allow the application to assume any order. `PageRequest.of(page, size)` specifies only pagination; meaningful ordering requires supplying an appropriate `Sort`.

## 7. Pagination: Stable Ordering Is Not Immutability Across Calls

### 7.1. Offset Pagination

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 0;
```

The first page on the sample data is 105, 104. The next page:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
```

Returns 103, 102 **if data does not change between the two queries**. Even with a total order, if a new order is inserted or an earlier row is deleted between two requests, `OFFSET` positions can shift: users see duplicate or skipped records. This does not contradict `ORDER BY`; each query only guarantees order over the rows visible at execution time under its transaction isolation level.

### 7.2. Keyset/Cursor Pagination for "Load More" Flows

With `created_at DESC, id DESC`, to fetch the page after the last row of the previous page, use that last row's keys as a cursor. Suppose the last row of page one is `(created_at='2026-10-30 12:00:00', id=104)`:

```sql
SELECT id, created_at
FROM orders
WHERE customer_id = 7
  AND (created_at, id) < (TIMESTAMP '2026-10-30 12:00:00', 104)
ORDER BY created_at DESC, id DESC
LIMIT 2;
```

In PostgreSQL, tuple comparison proceeds left to right; with both keys `DESC` and non-`NULL`, this `<` condition advances to records **after the cursor**. The result on the sample data is **103, 102**. On DBMSs without tuple comparisons, you can write the equivalent condition:

```sql
AND (
    created_at < :cursorTime
    OR (created_at = :cursorTime AND id < :cursorId)
)
```

The `AND (...)` snippet above is only a **WHERE condition fragment to insert into a full query**, with `:cursorTime` and `:cursorId` bound via `NamedParameterJdbcTemplate` or an equivalent mechanism; it is not a standalone SQL statement.

A cursor built on total, non-null, relatively immutable keys reduces the impact of new rows inserted *before* the cursor and avoids scanning across large offsets. Still, a cursor **does not create a fixed snapshot**: if an unread row is deleted or its sort key changes, subsequent pages can still vary. When business rules require an exact point-in-time snapshot across multiple pages, add transactions/snapshots or versioning depending on the DBMS.

### 7.3. Choosing a Strategy

- **Offset/page number:** suits small lists, "jump to page 5" requirements, and slowly changing data; still requires full-key sorting.
- **Keyset/cursor:** makes sense for "load more," large feeds, and repeated paging in a fixed order; cursor must carry all sort keys with comparison operators matching sort directions.
- **Snapshot/data versioning:** required when business rules demand an unchanging dataset across multiple reads (e.g., reconciliation report exports).

Never fetch a slice from the DB with `LIMIT/OFFSET` **and then** call `list.sort(...)` to "fix" global order: by then, the DB has already picked the wrong rows for the page or top N before Java sorts locally.

## 8. Interaction Between Ordering, Performance, and Java Processing

`ORDER BY` may require the DBMS to sort many rows; an appropriate index can sometimes let the DBMS read directly in order or reduce sort cost. PostgreSQL example:

```sql
CREATE INDEX idx_orders_customer_newest
    ON orders (customer_id, created_at DESC, id DESC);
```

This index can assist queries filtering by `customer_id` and fetching newest orders first. However, concrete gains depend on table size, selectivity, statistics, and execution plans. Use `EXPLAIN (ANALYZE, BUFFERS)` in a suitable test environment to evaluate; **never remove `ORDER BY` because an index already looks "ordered"**.

After receiving results, Java transformation steps must also preserve the intended order:

- A `List` and a sequential stream over an ordered source preserve encounter order when operations do not disturb it.
- Collecting into `HashSet`/`HashMap` or using unordered structures/algorithms can destroy ordering.
- Re-sorting in the UI is a different requirement from ensuring **the right rows are selected** from the DB. The UI can only sort what it received and cannot recover rows belonging to a page that the DB already cut off.

State the contract clearly at the API layer, for example: "Orders are returned by `createdAt` descending, then `id` descending." When an API allows changing sort order, field names, sort direction, tie-breaking, and pagination stability are all part of the contract to test.

## 9. How to Test Ordering Properly

Do not write tests like "ran the query without `ORDER BY` ten times and got the right order, so it's fine": those runs may simply have hit the same execution plan by coincidence.

Instead:

1. Seed data **inserted out of ID/timestamp order**, including at least two rows sharing the same primary sort key value.
2. Execute the real query and assert the ordered list of IDs, not merely the count or set membership.
3. Test `LIMIT`, first page, last page, and tied rows straddling page boundaries.
4. Test `NULL`/collation conventions if used by the domain.
5. For multi-call pagination, explicitly test expected behavior when inserts/deletes/updates happen between pages; do not confuse single-query ordering with an immutable snapshot.

Example assertions on the section 2 dataset when queried without concurrent updates:

| Query | Expected `id` List |
| --- | --- |
| `ORDER BY created_at DESC, id DESC` | `[105, 104, 103, 102, 101]` |
| Same order with `LIMIT 3` | `[105, 104, 103]` |
| Same order with `LIMIT 2 OFFSET 2` | `[103, 102]` |
| Without `ORDER BY` | **Do not assert a fixed expected order** |

## 10. Mistakes to Avoid and Fixes

- **"There is a primary key, so `findAll()` returns ascending by ID."** False: request `ORDER BY id ASC` or `Sort.by("id")`.
- **"Already used `ORDER BY created_at`, so records with the same timestamp stay in a fixed order."** False: add a unique key such as `id`.
- **"`GROUP BY` or `DISTINCT` already grouped/sorted the rows."** False: add `ORDER BY` to the result-returning query.
- **"`LIMIT 10` means get the 10 newest records."** False: define "newest" and sort before limiting.
- **"`Pageable` automatically guarantees stable pagination."** False: supply a `Sort` with enough keys, and account for data changes between requests.
- **"Sorting the `List` after fetching one page is enough."** False: the DB must choose rows in global order before slicing a page.
- **"A matching index exists, so drop `ORDER BY` for speed."** False: an index is an execution optimization, not an ordering contract.
- **"Every DB handles `NULL` and collation identically."** False: verify per DBMS/locale and test it.

## 11. Self-Check

**Question 1.** Does `SELECT id FROM orders WHERE customer_id = 7 LIMIT 2` guarantee returning the two smallest IDs?

**Answer:** No. Without `ORDER BY`, nothing defines "smallest." To achieve that, use `ORDER BY id ASC LIMIT 2`.

**Question 2.** Is `ORDER BY created_at DESC` sufficient for stable pagination when multiple orders are created in the same second?

**Answer:** Not enough. Orders with identical timestamps can swap places; append a unique key such as `id DESC`. With offset pagination, you must still account for inserts/deletes between pages.

**Question 3.** When paging by `created_at DESC, id DESC` and the last cursor is `(t, 104)`, what is the PostgreSQL condition for the next page if both columns are non-null?

**Answer:** `(created_at, id) < (t, 104)`, keeping the same `ORDER BY created_at DESC, id DESC`; `t` must be bound to the last record's actual timestamp value. For different sort directions, redesign the comparison accordingly.

**Question 4.** Why does a test comparing only a `Set` of IDs fail to prove ordering?

**Answer:** A `Set` discards order. You must assert the exact sequence of IDs in the `List` returned by the query, especially when sort keys contain ties.

## References

- [PostgreSQL — Sorting Rows (`ORDER BY`)](https://www.postgresql.org/docs/current/queries-order.html): unspecified order, multi-key sorting, and tie handling.
- [PostgreSQL — `LIMIT` and `OFFSET`](https://www.postgresql.org/docs/current/queries-limit.html): limits/pagination and predictable ordering requirements.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): using `Sort`, `PageRequest`, limits, and query method notes.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): SQL queries with `JdbcTemplate` and `RowMapper` mapping.

**Takeaway:** A DBMS is only obligated to return results in the order the query asked for; for predictable results, you need the right business criterion, `ORDER BY` at the result-returning query level, and tie-breaker keys sufficient to distinguish rows when needed. For pagination, you must also decide how to handle data changing between calls.