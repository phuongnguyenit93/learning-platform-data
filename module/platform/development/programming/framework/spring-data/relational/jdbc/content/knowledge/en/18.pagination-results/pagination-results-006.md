# Hand-Written SQL Pagination with Dialect-Specific LIMIT/OFFSET

In **Spring Data Relational JDBC**, some queries require custom SQL to JOIN multiple tables, perform calculations, or return a dedicated projection. When writing SQL directly, the developer must explicitly specify how to fetch each page of data. A common approach is using **LIMIT/OFFSET** on database management systems that support this syntax.

Core idea:

- **LIMIT** specifies the maximum number of rows to return.
- **OFFSET** specifies how many rows to skip before fetching results.
- **ORDER BY** defines the row order before pagination is applied.

However, pagination syntax is not identical across all DBMSs. PostgreSQL and MySQL typically use `LIMIT ... OFFSET ...`, whereas modern SQL Server and Oracle use `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`. When writing SQL manually in Spring Data JDBC, you must pick the syntax matching your actual database, bind pagination values safely, and ensure a stable order.

This lesson focuses on implementing SQL pagination manually, converting page/size to limit/offset, writing dialect-specific queries, count queries, and the limitations of offset pagination.

## 1. How Does SQL Pagination Work?

Suppose the `purchase_orders` table contains these orders:

| ID | Order number | Status | Created at |
|---:|---|---|---|
| 101 | ORD-0101 | PAID | 2026-11-01 09:00 |
| 102 | ORD-0102 | NEW | 2026-11-01 10:00 |
| 103 | ORD-0103 | PAID | 2026-11-02 08:00 |
| 104 | ORD-0104 | CANCELLED | 2026-11-02 11:00 |
| 105 | ORD-0105 | PAID | 2026-11-03 14:00 |
| 106 | ORD-0106 | NEW | 2026-11-04 09:00 |

If we want to display 2 orders per page, we divide the result set into groups:

```text
Page 0: 101, 102
Page 1: 103, 104
Page 2: 105, 106
```

With zero-based page numbering:

- Page 0 skips 0 rows.
- Page 1 skips 2 rows.
- Page 2 skips 4 rows.

Formula:

`offset = page × pageSize`

With `pageSize = 2`:

| Page | Page size | Offset | Equivalent SQL action |
|---:|---:|---:|---|
| 0 | 2 | 0 | Skip 0 rows, fetch 2 |
| 1 | 2 | 2 | Skip 2 rows, fetch 2 |
| 2 | 2 | 4 | Skip 4 rows, fetch 2 |
| 3 | 2 | 6 | Skip 6 rows, may have no data left |

Example SQL in PostgreSQL syntax:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
```

The query skips the first two rows in the sorted order, then returns up to two rows.

**ORDER BY is foundational to pagination.** Without an explicit ordering, the database does not guarantee which rows appear on the first or subsequent pages. A query with LIMIT/OFFSET and no ORDER BY can return different orders across executions.

## 2. Roles of LIMIT, OFFSET, and ORDER BY

### 2.1. LIMIT

`LIMIT` restricts the maximum number of rows:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 10;
```

The query fetches up to 10 rows. If only 6 rows match, the result has 6 rows.

### 2.2. OFFSET

`OFFSET` skips a number of initial rows in the sorted result set:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 10 OFFSET 20;
```

The query skips the first 20 rows and then fetches up to the next 10 rows.

OFFSET normally starts at 0. If `offset = 0`, no rows are skipped.

### 2.3. ORDER BY

`ORDER BY` defines the order before the database applies limits:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
```

Here:

- `created_at DESC` places newer orders first.
- `id DESC` is the tie-breaker when multiple orders share the same creation timestamp.
- `LIMIT 20` takes at most the first 20 rows.
- `OFFSET 0` starts from the first row.

Do not sort solely by columns that can collide, such as status, name, or timestamp. Append a unique column, usually the primary key, so the order among rows with identical sort values is deterministic.

### 2.4. Logical Processing Sequence

You can picture it simply as:

```text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY / HAVING (if any)
    ↓
ORDER BY
    ↓
OFFSET
    ↓
LIMIT / FETCH
```

This is a logical model for understanding the output, not a mandatory physical execution order of the query planner. The database may choose another optimization plan while preserving SQL semantics.

## 3. Pagination Syntax by Database Dialect

A *dialect* reflects the SQL syntax and capabilities of a specific DBMS. Spring Data Relational can use a dialect in framework-generated SQL operations, but when you **write SQL manually**, do not expect the framework to translate LIMIT/OFFSET into every database's syntax automatically.

The following table summarizes common syntaxes:

| Database | Common pagination syntax |
|---|---|
| PostgreSQL | `LIMIT :limit OFFSET :offset` |
| MySQL | `LIMIT :limit OFFSET :offset` |
| MariaDB | `LIMIT :limit OFFSET :offset` |
| SQLite | `LIMIT :limit OFFSET :offset` |
| SQL Server 2012+ | `ORDER BY ... OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |
| Oracle 12c+ | `OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |
| DB2 | `OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |

Exact syntax can vary by version, driver, and parameter binding rules. Verify the DBMS your application runs on, especially if supporting multiple databases.

### 3.1. PostgreSQL

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

PostgreSQL also supports the form:

```sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY id
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

The `LIMIT/OFFSET` form is commonly used in PostgreSQL applications.

### 3.2. MySQL and MariaDB

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

MySQL also supports a shorthand form:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 20, 10;
```

In `LIMIT offset, row_count`, the first number is the offset and the second is the row count to fetch. This shorthand is easy to misread quickly. In application code, `LIMIT row_count OFFSET offset` is usually clearer.

### 3.3. SQL Server

SQL Server uses `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` and requires `ORDER BY`:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = @status
ORDER BY created_at DESC, id DESC
OFFSET @offset ROWS
FETCH NEXT @limit ROWS ONLY;
```

When using Spring `NamedParameterJdbcTemplate`, parameter names can be written `:status`, `:offset`, and `:limit`; Spring translates them into appropriate bind parameters. The `@status` syntax in the snippet above is illustrative T-SQL parameter syntax when writing SQL directly in SQL Server tools.

### 3.4. Oracle 12c and Later

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
OFFSET :offset ROWS
FETCH NEXT :limit ROWS ONLY;
```

Oracle has supported this standard pagination syntax since Oracle Database 12c. Older versions may require nested queries and `ROWNUM`; do not use the legacy syntax if the system already runs a version supporting OFFSET/FETCH.

### 3.5. DB2

Common syntax:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = ?
ORDER BY created_at DESC, id DESC
OFFSET ? ROWS
FETCH NEXT ? ROWS ONLY;
```

With JDBC positional parameters, binding order must match the positions of the `?` placeholders. If using a named-parameter abstraction, check how Spring translates parameters for your driver.

### 3.6. Why Isn't There a Single SQL Query for Every Database?

DBMSs evolve SQL syntax across versions. A query might:

- Run on PostgreSQL yet fail with a syntax error on SQL Server.
- Run on Oracle 12c+ yet fail on older Oracle versions.
- Have similar syntax yet differ in how drivers bind LIMIT/OFFSET.
- Have different default NULL ordering.

Therefore, hand-written paginated SQL is part of the contract with the database. When switching databases or upgrading versions, re-verify the queries and integration tests.

## 4. Writing `@Query` with LIMIT/OFFSET in Spring Data JDBC

For a SQL query declared with `@Query`, you can pass limit and offset values as named parameters if the database/driver syntax supports binding at those positions.

PostgreSQL example:

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, customer_id, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """)
    List<PurchaseOrder> findPageByStatus(
        @Param("status") String status,
        @Param("limit") int limit,
        @Param("offset") long offset
    );
}
```

Invocation:

```java
List<PurchaseOrder> page = repository.findPageByStatus(
    "PAID",
    20,
    40L
);
```

The query fetches up to 20 `PAID` orders after skipping the first 40 in newest-first order.

The `:status`, `:limit`, and `:offset` parameters are **bound values**, not string-concatenated SQL fragments. For another dialect, replace only the pagination clause; value binding and filtering follow the same principle.

### 4.1. Calculating Offset in the Service

Do not ask clients to calculate offset themselves if the API already receives page and size. The service can convert them:

```java
public List<PurchaseOrder> findPage(
        String status,
        int page,
        int size) {

    if (page < 0) {
        throw new IllegalArgumentException(
            "Page must be zero or greater"
        );
    }

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "Page size must be between 1 and 100"
        );
    }

    long offset = (long) page * size;

    return repository.findPageByStatus(status, size, offset);
}
```

For example, `page = 2` and `size = 20`:

`offset = 2 × 20 = 40`

Cast `page` to `long` before multiplying to prevent `int` overflow in large calculations. Even in systems with capped page/size, validation is still needed before executing queries.

### 4.2. Keeping Page Number Semantics Consistent

APIs usually number pages starting at 0 or 1. Spring Data `PageRequest` uses zero-based page numbering. If your API starts at 1, convert explicitly:

```java
int zeroBasedPage = requestedPage - 1;

if (requestedPage < 1) {
    throw new IllegalArgumentException("Page must start at 1");
}

long offset = (long) zeroBasedPage * pageSize;
```

Do not mix 1-based page numbers with an offset formula intended for 0-based page numbers. This is a common bug that skips the first page or misaligns page data.

### 4.3. Data Types for Limit and Offset

Use integer types:

- `int` is usually enough for a tightly capped page size.
- `long` is safer for offset because total row counts can be large.
- Reject negative numbers.
- Do not allow size 0 if the API expects a non-empty page capacity.
- Enforce an upper bound to avoid returning too many rows.

How large an offset a database/driver supports via parameter binding depends on the dialect. Ensure Java types, JDBC parameter types, and DBMS limits align.

## 5. Implementing Pagination Manually with NamedParameterJdbcTemplate

For complex custom SQL or DTO results, a custom repository is often more flexible than `@Query`. Example fetching an order list with customer names:

```sql
SELECT
    o.id,
    o.order_number,
    o.status,
    c.full_name AS customer_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

DTO:

```java
public record OrderSummary(
    long id,
    String orderNumber,
    String status,
    String customerName
) {}
```

Repository:

```java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSummaryRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSummaryRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findPage(
            String status,
            int limit,
            long offset) {

        String sql = """
            SELECT
                o.id,
                o.order_number,
                o.status,
                c.full_name AS customer_name
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
            """;

        Map<String, Object> params = Map.of(
            "status", status,
            "limit", limit,
            "offset", offset
        );

        return jdbc.query(
            sql,
            params,
            (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_number"),
                rs.getString("status"),
                rs.getString("customer_name")
            )
        );
    }
}
```

Here:

- The application controls the SQL.
- `NamedParameterJdbcTemplate` binds the filter, limit, and offset values.
- `RowMapper` maps each row to `OrderSummary`.
- The DTO contains only the fields needed for the screen.
- There is no need to load full aggregates if the use case only reads display data.

The SQL example uses PostgreSQL/MySQL `LIMIT/OFFSET`. For SQL Server or Oracle, replace the pagination clause with the corresponding dialect syntax.

### 5.1. Validating Parameters in the Repository or Service

Do not let arbitrary callers pass unchecked values:

```java
private void validatePageArguments(int limit, long offset) {
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid limit");
    }

    if (offset < 0) {
        throw new IllegalArgumentException("Offset cannot be negative");
    }
}
```

Validation can live at the service/API boundary while keeping the repository focused on data access. If the repository is called from many places, an extra guard helps prevent dangerous queries caused by bad caller inputs.

## 6. Count Query to Know the Total Record Count

LIMIT/OFFSET returns only a slice of data. If the UI needs to display:

- Total matching orders.
- Total pages.
- “Showing 21–40 of 135 orders”.

then an additional count query is needed.

Example:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

In a custom repository:

```java
public long countByStatus(String status) {
    String sql = """
        SELECT COUNT(*)
        FROM purchase_orders
        WHERE status = :status
        """;

    Long total = jdbc.queryForObject(
        sql,
        Map.of("status", status),
        Long.class
    );

    return total == null ? 0L : total;
}
```

Normally `COUNT(*)` returns a single row containing the count, even when no records match (value 0). Handling null in Java is defensive against the API signature and specific mapping behavior.

### 6.1. Count and Data Queries Must Have Identical Conditions

If the page-content query is:

```sql
SELECT id, order_number
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

then the count query must use the exact same filters:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId;
```

Omitting the `customer_id` condition in the count query will produce an inflated total row count and page count.

### 6.2. Counting at the Right Grain When Joining

Suppose an order has multiple line items. The query:

```sql
SELECT o.id, oi.product_id
FROM purchase_orders o
JOIN order_items oi ON oi.order_id = o.id;
```

returns one row per order/product pair. If the UI paginates **orders**, the count must count unique orders:

```sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = :status;
```

If the UI paginates **line items**, `COUNT(*)` over the JOIN result is the right number.

Identify the *grain* (what one row represents) of the page content and write the count accordingly. Counting the wrong grain is a frequent reason total page counts mismatch displayed items.

### 6.3. Total Number of Pages

Given total rows `total` and page size `size`:

`totalPages = ceil(total / size)`

It can be calculated in Java:

```java
long totalPages = (total + size - 1) / size;
```

This requires `size > 0` and risks overflow if `total` is near `Long.MAX_VALUE`. A safer arithmetic calculation:

```java
long totalPages = total / size
    + (total % size == 0 ? 0 : 1);
```

If `total = 135` and `size = 20`, total pages is 7.

### 6.4. When Is a Count Query Unnecessary?

If the UI only needs to know whether more data follows, the total page count is unnecessary. You can fetch one extra row:

```sql
SELECT id, order_number, status
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize OFFSET :offset;
```

Where `fetchSize = pageSize + 1`. If the query returns more than page size, a next page exists; discard the extra row before returning the response.

This avoids potentially expensive count queries. A custom repository must build metadata like `hasNext` itself rather than expecting declarative SQL to auto-create a `Slice`.

## 7. Paginating One-to-Many JOINs

A major mistake is applying LIMIT/OFFSET after joining a one-to-many relationship.

Suppose an order has multiple line items:

```text
Order 42
  Item A
  Item B
  Item C

Order 43
  Item D
```

Query:

```sql
SELECT o.id, o.order_number, i.product_id
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id
LIMIT 2 OFFSET 0;
```

`LIMIT 2` limits **two joined rows**, not two orders. The result may contain only Order 42 with Item A and Item B, omitting Item C from the page. If those rows are mapped into objects carelessly, aggregate detail data can be truncated.

### 7.1. Paginate Base-Table IDs First

If the goal is 20 orders per page, paginate the set of order IDs first and then fetch child rows:

```sql
WITH page_orders AS (
    SELECT id
    FROM purchase_orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    o.id,
    o.order_number,
    o.status,
    i.product_id,
    i.quantity
FROM page_orders p
JOIN purchase_orders o ON o.id = p.id
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC, i.product_id;
```

The subquery/CTE bounds the exact root set first. Then it JOINs all line items belonging to the orders on that page. The final result may have multiple rows per order, without truncating parts of an order due to a post-JOIN limit.

### 7.2. Count Query for Root Pages

Counting orders should count the base table with the matching filter:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

Do not count `order_items` rows if the response is paginated by order.

### 7.3. When a Single-Row-Per-Order DTO Is Needed

If the screen only needs total amount, aggregate line items before paginating or inside a query designed at the right grain:

```sql
SELECT
    o.id,
    o.order_number,
    o.status,
    COALESCE(t.total_amount, 0) AS total_amount
FROM purchase_orders o
LEFT JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS total_amount
    FROM order_items
    GROUP BY order_id
) t ON t.order_id = o.id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

Subquery `t` has only one row per `order_id`, so the JOIN does not multiply order rows. This makes pagination and aggregation easier to control.

## 8. Stable Ordering and Data Changes Between Pages

Even with `ORDER BY`, data can change between two API calls.

### 8.1. Add a Unique Tie-Breaker

Unstable:

```sql
ORDER BY created_at DESC
```

More stable:

```sql
ORDER BY created_at DESC, id DESC
```

If multiple rows share `created_at`, `id` determines the order among them. The primary key is usually a suitable tie-breaker.

### 8.2. New Data Inserted Between Two Requests

Suppose:

1. The user loads page 0, offset 0, limit 20.
2. A new order is inserted and lands at the top of the list.
3. The user loads page 1, offset 20, limit 20.

Because the new row shifts the positions of older rows, the next page may repeat an order seen on the previous page or skip an order. Adding a tie-breaker makes ordering deterministic per query, but does not lock row positions across requests.

### 8.3. How Can Transactions Help?

If both the content query and count query must observe the same data state, they can run inside the same transaction. Actual consistency still depends on the isolation level and DBMS. Under `READ COMMITTED`, two `SELECT` statements can observe different commits depending on the database.

For pagination across multiple HTTP requests, holding a transaction open across page loads is usually inappropriate. If traversing a consistent snapshot is required, design an explicit snapshot/version/cursor mechanism.

## 9. Performance and Limitations of OFFSET

OFFSET is easy to implement, yet the deeper it goes, the larger the cost can become.

Example:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

The database must identify the rows preceding the target position. Even with a suitable index, skipping a very large offset can still require significant work.

### 9.1. Indexes for ORDER BY and WHERE

If queries commonly filter by status and sort by created_at/id:

```sql
CREATE INDEX idx_orders_status_created_id
    ON purchase_orders(status, created_at DESC, id DESC);
```

This index is an example design for a specific workload. Appropriate indexes depend on the DBMS, selectivity, cardinality, filter/sort order, and execution plans. Do not blindly copy example indexes without measuring on real data.

### 9.2. When Is OFFSET Still Appropriate?

OFFSET is suitable when:

- The list is moderate in size.
- Users need to jump to a specific page number.
- Total page count is displayed.
- Queries are indexed and meet latency requirements.
- Data does not mutate too rapidly while users browse.

### 9.3. When Should Keyset Pagination Be Considered?

For large lists, feeds, or order histories, cursor/keyset pagination can be used. Instead of skipping 500,000 rows, the query fetches rows after the last values from the previous page.

With `created_at DESC, id DESC`:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

The cursor holds `lastCreatedAt` and `lastId` of the previous page's last row. The query avoids large OFFSETs.

Keyset suits sequential forward traversal, though it is inconvenient for jumping straight to an arbitrary page. It is a different architectural choice, not a drop-in syntax replacement for every OFFSET use case.

## 10. Dynamic Sorting in Paginated SQL

A SQL query can have a fixed ORDER BY:

```sql
ORDER BY created_at DESC, id DESC
```

If an API lets clients choose a sort field, column names cannot be bound as values:

```sql
-- Do not use this approach to substitute column names:
ORDER BY :sortColumn;
```

Named parameters only bind values. They do not substitute SQL identifiers, keywords, or syntax fragments.

Do not concatenate raw client strings directly:

```java
String sql = "SELECT ... ORDER BY " + request.sortBy();
```

Instead, map sort keys to an enum/allowlist:

```java
public enum OrderSortField {
    CREATED_AT,
    ORDER_NUMBER,
    STATUS
}

public enum Direction {
    ASC,
    DESC
}
```

```java
private String toColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "o.created_at";
        case ORDER_NUMBER -> "o.order_number";
        case STATUS -> "o.status";
    };
}

private String toDirection(Direction direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
```

When building SQL, only concatenate identifiers controlled by code. Values such as status, limit, and offset must still be bound via parameters.

Add a tie-breaker:

```sql
ORDER BY o.created_at DESC, o.id DESC
```

When the sort field changes, the tie-breaker must also be designed to produce a deterministic order.

## 11. Validation and Safety for Pagination Parameters

SQL parameter binding prevents input values from becoming SQL syntax, yet does not protect the application from nonsensical pagination values.

### 11.1. Validating Page and Size

```java
public record PageInput(int page, int size) {}

public long calculateOffset(PageInput input) {
    if (input.page() < 0) {
        throw new IllegalArgumentException("Page must be >= 0");
    }

    if (input.size() < 1 || input.size() > 100) {
        throw new IllegalArgumentException("Size must be between 1 and 100");
    }

    return (long) input.page() * input.size();
}
```

If the API uses 1-based page numbers, perform validation and conversion to zero-based before calculating the offset.

### 11.2. Avoiding Overflow

Multiplying two `int` values before widening can overflow:

```java
int page = 100_000;
int size = 100_000;

// Risk of int overflow before assigning to long:
long wrongOffset = page * size;

// Cast one operand to long before multiplying:
long offset = (long) page * size;
```

Do not just check for negatives; bound size and offset according to system requirements and database limits.

### 11.3. Parameter Binding for Data, Allowlist for Identifiers

| Component | Safe passing method |
|---|---|
| Status, customer ID, filter dates | Named/positional bind parameter |
| Limit, offset | Bind parameter if dialect/driver supports it |
| Column names in ORDER BY | Application-controlled allowlist/enum |
| ASC/DESC | Enum or fixed choice |
| Table/schema names | Trusted configuration, never raw request input |

## 12. Organizing Paginated Results in Java

If a custom repository returns `List<T>`, the service can package metadata itself.

Example response:

```java
public record PageResult<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    long totalPages
) {}
```

Service:

```java
public PageResult<OrderSummary> findOrderPage(
        String status,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page request");
    }

    long offset = (long) page * size;

    List<OrderSummary> content =
        readRepository.findPage(status, size, offset);

    long total = readRepository.countByStatus(status);

    long totalPages = total / size
        + (total % size == 0 ? 0 : 1);

    return new PageResult<>(
        content,
        page,
        size,
        total,
        totalPages
    );
}
```

`PageResult` is an application-defined API DTO. Spring Data JDBC does not generate it automatically just because SQL has LIMIT/OFFSET.

If the total row count is not needed, a lighter response can be designed:

```java
public record CursorPage<T>(
    List<T> content,
    boolean hasNext
) {}
```

In this case, the query fetches `size + 1` rows to determine `hasNext` without counting.

## 13. Testing Dialect-Specific Paginated Queries

Paginated SQL depends on the database, so it must be tested against the exact DBMS and version the application uses.

A test suite should include:

- More rows than the page size.
- Multiple rows sharing the same sort key to verify tie-breaking.
- Different statuses/filters.
- An empty set.
- First page, middle page, and page beyond available data.
- Invalid page/size values at the service layer.

Expected examples:

| Case | Page | Size | Expected |
|---|---:|---:|---|
| First page | 0 | 2 | First 2 rows per ORDER BY |
| Middle page | 1 | 2 | Next 2 rows |
| Partial last page | 2 | 2 | 1 row if total is 5 |
| Page beyond data | 3 | 2 | Empty list |
| Size equals 0 | 0 | 0 | Validation fails |
| Negative offset | — | — | Validation fails |
| No matching rows | 0 | 20 | Empty list, count equals 0 |

Do not test only with H2 if production runs PostgreSQL, SQL Server, or Oracle. H2 may not faithfully reproduce the syntax and behavior of the target database. Use Testcontainers or an integration test environment with the real database/dialect to test actual SQL.

### 13.1. Testing Order on Tied Values

Insert multiple orders with identical `created_at` and verify `id DESC` determines their order. Without a tie-breaker, tests can pass or fail intermittently depending on query plans and data.

### 13.2. Checking Count vs. Content

Cross-check:

- Total row count returned by count query.
- Total elements assembled across all pages when the dataset is static.
- No duplicate and no missing IDs across pages.
- Count query filters match data query filters.

With concurrently mutating data, test according to the application's isolation/consistency contract rather than expecting offset pagination to produce a cross-request snapshot.

## 14. Common Errors

| Symptom | Possible cause | Solution |
|---|---|---|
| SQL runs on PostgreSQL but fails on SQL Server | Wrong LIMIT/OFFSET syntax used | Use OFFSET/FETCH per dialect |
| First page is missing rows | Confusing 1-based and 0-based page numbers | Normalize page number before computing offset |
| Pages duplicate or skip rows | Missing stable ORDER BY or data changes between requests | Add a tie-breaker; consider cursor/snapshot |
| JOINed page truncates items | LIMIT applied to joined rows instead of roots | Paginate root IDs first, then JOIN |
| Total pages do not match | Count query missing filter or counting wrong grain | Sync conditions and use COUNT(DISTINCT) when needed |
| Deep pages are very slow | Large OFFSET | Use appropriate indexes or keyset pagination |
| Database rejects limit parameter | Driver/dialect does not support binding in that position | Check driver, parameter types, and specific syntax |
| SQL injection via sort | Concatenating raw identifiers from request | Allowlist sort columns and directions |
| Overly large page size | Missing input validation | Cap max size at API/service layer |
| Query has unstable order | Missing ORDER BY or duplicate sort keys | Add a unique key as tie-breaker |
| H2 tests pass while production fails | Test DB differs from production dialect | Integration test with real database/matching version |

## 15. Practice Exercises

Suppose the `purchase_orders` table has columns `id`, `order_number`, `status`, `customer_id`, and `created_at`. The application database is PostgreSQL.

### Exercise 1. Fetching the First Page

Write SQL to fetch up to the 10 newest `PAID` orders.

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Parameters: `status = 'PAID'`, `limit = 10`, `offset = 0`.

### Exercise 2. Fetching the Fourth Page

Page numbers start at 0, size is 25. What is the offset?

**Answer:** `offset = 3 × 25 = 75`. The query uses `LIMIT 25 OFFSET 75`.

### Exercise 3. Converting to SQL Server

With the same limit 25 and offset 75, SQL Server 2012+ syntax is:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = @status
ORDER BY created_at DESC, id DESC
OFFSET @offset ROWS
FETCH NEXT @limit ROWS ONLY;
```

In Spring named-parameter queries, use Spring placeholders such as `:status`, `:offset`, and `:limit`.

### Exercise 4. Writing the Count Query

The data query filters by `status` and `customer_id`. What conditions must the count query have?

**Answer:** Both conditions must be preserved:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId;
```

### Exercise 5. Paginating Orders with Line Items

An order has 5 items. Why might `LIMIT 10` on the JOIN result fail to return 10 orders?

**Answer:** LIMIT restricts joined rows, and each order can produce multiple rows. Paginate order IDs first, then JOIN the items of those orders.

### Exercise 6. Safe Sorting

An API receives `sortBy=createdAt` and `direction=desc`. Should these two strings be concatenated into SQL?

**Answer:** No. Map the sort key via an enum/allowlist and direction to fixed ASC/DESC; only concatenate code-controlled identifiers.

### Exercise 7. Large Offsets

A page requests `LIMIT 50 OFFSET 900000` and the query is slow. What approaches can be considered?

**Answer:** Check indexes and query plans; if users traverse sequentially, consider keyset pagination based on the sort key and ID instead of skipping a huge offset.

## 16. Things to Remember

1. **LIMIT** caps the row count; **OFFSET** skips initial rows; **ORDER BY** defines order before pagination.
2. Always use a stable ordering, typically adding the primary key as a tie-breaker.
3. Hand-written SQL must match the database's syntax: PostgreSQL/MySQL typically use LIMIT/OFFSET; modern SQL Server and Oracle use OFFSET/FETCH.
4. In Spring Data JDBC, bind filters, limit, and offset with named/positional parameters if supported by the driver/dialect.
5. Compute offset as `page × size`, normalize page numbers, and use `long` to prevent overflow.
6. The count query must share the same filters and count at the same grain returned by the page.
7. For one-to-many JOINs, paginate roots first and then fetch child data if the goal is a page of aggregate roots.
8. Large OFFSETs can be slow; keyset pagination suits sequential traversal of large datasets.
9. Never concatenate raw sort fields from requests into SQL; use allowlists for identifiers and directions.
10. Test paginated SQL against the exact production database/dialect.

### References

- [PostgreSQL — LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)
- [MySQL — LIMIT Query Optimization](https://dev.mysql.com/doc/refman/8.4/en/limit-optimization.html)
- [SQL Server — ORDER BY Clause (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/queries/select-order-by-clause-transact-sql)
- [Oracle — SELECT and row limiting clause](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/SELECT.html)
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)

When applying this, confirm syntax for your running database version and JDBC driver. With hand-written paginated SQL, the application is responsible for explicitly expressing the limit, offset, ordering, and count query.
