# Adding Optional Filters Without Concatenating SQL Values

In applications using **Spring Data Relational JDBC**, search screens often have multiple optional filters: order status, customer, date range, order number, or keyword. Users may fill in only a few fields, so the query needs to adapt to the filters actually provided.

The safe approach is to **build the SQL statement structure from fixed clauses in code and pass values via bind parameters**. With Spring JDBC, **NamedParameterJdbcTemplate** allows named parameters such as **:status** and **:fromTime** with separately bound values. You may append or omit WHERE clauses, but you must never insert raw input data directly into the SQL string.

This lesson explains how to design optional filters, build safe dynamic queries, handle IN lists, LIKE searches, sorting and pagination, and how to choose between derived queries, @Query, and NamedParameterJdbcTemplate.

## 1. Why Do Optional Filters Need Dynamic Queries?

Suppose an order search screen has these fields:

- Order status.
- Customer ID.
- Created from date.
- Created to date.
- Partial order number.

Users may search by status, by customer, by date, or combine multiple conditions. For example:

| Search Request | Required SQL Condition |
|---|---|
| No filters entered | No extra condition |
| Only submitted orders | **o.status = :status** |
| Orders for one customer | **o.customer_id = :customerId** |
| Orders within a date range | **o.created_at >= :fromTime** and **o.created_at < :toTime** |
| Search by status and customer | Combine both conditions with AND |

Writing a separate SQL statement for every combination causes the number of queries to grow quickly. With five independent filters, there can be up to \(2^5 = 32\) combinations. As the number of conditions increases, building a single query from fixed clauses is usually much easier to manage.

Example schema:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

The order list query can start with:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.customer_id,
    o.status,
    o.created_at
FROM purchase_orders o
~~~

The application then adds conditions matching the received filters.

## 2. Distinguishing SQL Structure Concatenation from Input Value Concatenation

There are two distinct actions:

1. **Concatenating SQL structure:** appending a fixed clause written by the developer, such as **AND o.status = :status**.
2. **Concatenating data values:** inserting user-supplied content directly into the SQL string.

The first can be safe when the SQL fragments are application-controlled constants. The second introduces SQL injection risks and syntax errors.

### 2.1. Unsafe Approach

~~~java
String sql = "SELECT * FROM purchase_orders WHERE status = '"
    + requestedStatus + "'";

List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql);
~~~

If a user enters:

~~~text
' OR '1'='1
~~~

the SQL statement can be altered into an always-true condition. The user has modified the **statement structure**, rather than merely supplying a search value.

Do not try to fix this by replacing single quotes, stripping semicolons, or filtering a few dangerous characters. Exploitable character sets vary by database and SQL context; manual escaping easily misses edge cases.

### 2.2. Safe Approach with Bind Parameters

~~~java
String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status = :status
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("status", requestedStatus);

List<Map<String, Object>> rows =
    namedParameterJdbcTemplate.queryForList(sql, params);
~~~

Here the SQL keeps a fixed structure. The value requestedStatus is sent separately through the JDBC driver's bind parameter mechanism. Even if the user enters quotes or SQL keywords, they are treated strictly as data for the status parameter.

**Rule:** every data value must be bound via ? or a named parameter; never concatenate that value directly into SQL.

## 3. Using NamedParameterJdbcTemplate for Optional Filters

NamedParameterJdbcTemplate belongs to Spring JDBC. It supports named parameters instead of positional ? placeholders, making SQL and value binding easier to read.

### 3.1. Declaring the Filter Object

Search conditions can be grouped into a record:

~~~java
import java.time.LocalDateTime;

public record OrderSearchFilter(
        String status,
        Long customerId,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        String orderNumberKeyword
) {
}
~~~

Fields can be null when the user omits a condition. At the API layer, a request can be mapped into this record after validating formats and access permissions.

Result type for the search example:

~~~java
import java.time.LocalDateTime;

public record OrderSearchResult(
        Long id,
        String orderNumber,
        Long customerId,
        String status,
        LocalDateTime createdAt
) {
}
~~~

### 3.2. Building a List of Clauses and Parameters

Idea:

~~~text
Base SQL
  |
  +-- status present?       -> add "o.status = :status"
  |
  +-- customerId present?   -> add "o.customer_id = :customerId"
  |
  +-- createdFrom present?  -> add "o.created_at >= :createdFrom"
  |
  +-- createdTo present?    -> add "o.created_at < :createdTo"
  |
  +-- keyword present?      -> add "o.order_number LIKE :keyword"
  |
  v
Final SQL + bound parameters
~~~

Fragments appended to the list are fixed SQL strings defined in code. Actual values go into MapSqlParameterSource.

### 3.3. Complete Example

~~~java
package com.example.orders.read;

import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSearchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSearchResult> search(OrderSearchFilter filter) {
        List<String> predicates = new ArrayList<>();
        MapSqlParameterSource params = new MapSqlParameterSource();

        if (filter.status() != null && !filter.status().isBlank()) {
            predicates.add("o.status = :status");
            params.addValue("status", filter.status().trim());
        }

        if (filter.customerId() != null) {
            predicates.add("o.customer_id = :customerId");
            params.addValue("customerId", filter.customerId());
        }

        if (filter.createdFrom() != null) {
            predicates.add("o.created_at >= :createdFrom");
            params.addValue(
                "createdFrom",
                Timestamp.valueOf(filter.createdFrom())
            );
        }

        if (filter.createdTo() != null) {
            predicates.add("o.created_at < :createdTo");
            params.addValue(
                "createdTo",
                Timestamp.valueOf(filter.createdTo())
            );
        }

        if (filter.orderNumberKeyword() != null
                && !filter.orderNumberKeyword().isBlank()) {
            predicates.add("o.order_number LIKE :keyword ESCAPE '!'");
            params.addValue(
                "keyword",
                "%" + escapeLike(filter.orderNumberKeyword().trim()) + "%"
            );
        }

        StringBuilder sql = new StringBuilder("""
            SELECT
                o.id,
                o.order_number,
                o.customer_id,
                o.status,
                o.created_at
            FROM purchase_orders o
            """);

        if (!predicates.isEmpty()) {
            sql.append(" WHERE ")
               .append(String.join(" AND ", predicates));
        }

        sql.append(" ORDER BY o.created_at DESC, o.id DESC");

        return jdbc.query(sql.toString(), params, (rs, rowNum) ->
            new OrderSearchResult(
                rs.getLong("id"),
                rs.getString("order_number"),
                rs.getLong("customer_id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            )
        );
    }

    private static String escapeLike(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }
}
~~~

In the example SQL, **ESCAPE '!'** uses ! as the escape character for LIKE. The escapeLike method escapes the escape character first, then escapes % and _. If a product intends to allow user-entered wildcards, do not escape those two characters; define search semantics explicitly.

OrderSearchResult and OrderSearchFilter are example DTOs. The SQL can be adjusted to fit a specific schema, timestamp type, and database. In real code, LocalDateTime can be bound directly if the driver and mapping configuration support it; the example uses Timestamp.valueOf to show the explicit JDBC type for a TIMESTAMP column.

### 3.4. Why Is This Approach Safe?

- Column names and operators in predicates are fixed strings defined in code.
- status, customerId, timestamps, and keyword are passed through named parameters.
- User values cannot become part of SQL syntax.
- Each condition appears only when its corresponding filter is provided.
- If no filters are provided, the query remains valid because the WHERE clause is omitted.

Concatenating **trusted SQL clauses** to form dynamic structure is acceptable. What must be avoided is concatenating input data into those clauses.

## 4. Alternative: Fixed SQL with NULL Parameter Conditions

With a small, fixed number of filters, you can keep a single static SQL query:

~~~sql
SELECT id, order_number, customer_id, status, created_at
FROM purchase_orders
WHERE (:status IS NULL OR status = :status)
  AND (:customerId IS NULL OR customer_id = :customerId)
  AND (:createdFrom IS NULL OR created_at >= :createdFrom)
  AND (:createdTo IS NULL OR created_at < :createdTo)
ORDER BY created_at DESC, id DESC;
~~~

When a parameter is NULL, the first branch of the condition is true and that filter is skipped. When the parameter has a value, the equality/range comparison applies.

Example binding with MapSqlParameterSource:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("status", status, java.sql.Types.VARCHAR)
    .addValue("customerId", customerId, java.sql.Types.BIGINT)
    .addValue("createdFrom", createdFrom, java.sql.Types.TIMESTAMP)
    .addValue("createdTo", createdTo, java.sql.Types.TIMESTAMP);
~~~

Declaring explicit SQL types helps drivers/databases handle typed NULL parameters. Because Map.of cannot hold null values, use MapSqlParameterSource or a map implementation that supports nulls.

### 4.1. Advantages and Limitations

| Advantages | Limitations |
|---|---|
| Single static SQL statement | Every condition has an OR expression even when unused |
| No predicate list assembly | The optimizer may struggle to use indexes with certain OR patterns |
| Easy to read for a few simple filters | Binding NULL requires driver-compatible SQL types |
| Easy to keep in @Query annotation | Does not scale well when there are many optional conditions or filter types |

This is a reasonable option for a small query with few filters. For search screens with many conditions and strict performance requirements, assembling fixed predicates dynamically is usually more flexible.

## 5. Using @Query in a Repository for Simple Filter Sets

If a query belongs to an aggregate root and has few optional conditions, SQL can be declared with @Query:

~~~java
public interface OrderHeaderProjection {
    Long getId();
    String getOrderNumber();
    Long getCustomerId();
    String getStatus();
    LocalDateTime getCreatedAt();
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, order_number, status, created_at
        FROM purchase_orders
        WHERE (:status IS NULL OR status = :status)
          AND (:customerId IS NULL OR customer_id = :customerId)
        ORDER BY created_at DESC, id DESC
        """)
    List<OrderHeaderProjection> searchHeaders(
        @Param("status") String status,
        @Param("customerId") Long customerId
    );
}
~~~

This illustrates a query with optional conditions and bound parameters. The projection declares only the header columns returned by SELECT. A SELECT fetching only header columns should not be treated as a way to load a full aggregate with child collections. For search screen results, a projection or DTO usually expresses intent better.

If a query needs many filters, dynamic IN lists, optional sorting, or reporting calculations, NamedParameterJdbcTemplate usually organizes SQL and result mapping more cleanly.

## 6. List Filters with IN

A common filter allows status to accept multiple values:

~~~sql
WHERE o.status IN (:statuses)
~~~

NamedParameterJdbcTemplate supports expanding named parameters whose value is a collection:

~~~java
Set<String> statuses = Set.of("DRAFT", "SUBMITTED");

String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status IN (:statuses)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("statuses", statuses);

List<OrderHeader> rows = jdbc.query(sql, params, orderHeaderMapper);
~~~

The template generates one placeholder per element. Values remain individually bound; there is no need to build a string like 'DRAFT','SUBMITTED'.

### 6.1. Deciding the Meaning of an Empty Collection

Three cases must be distinguished:

| Input | Meaning to Define |
|---|---|
| statuses == null | User did not apply a status filter |
| statuses has elements | Include only selected statuses |
| statuses.isEmpty() | Could mean no status selected, or skip filter; must decide explicitly |

Do not pass an empty collection into IN (:statuses) and expect every database to behave identically. Some dialects reject IN (); empty collection expansion behavior also varies by framework/version.

If the convention is that an empty collection yields no results, return List.of() before running SQL. If the convention is to skip the filter, omit the predicate. The two choices have different meanings and must align with the UI.

## 7. LIKE Searches and Wildcards

Bind parameters prevent SQL injection, but do not alter the meaning of wildcards in LIKE.

~~~sql
WHERE order_number LIKE :keyword
~~~

If you bind %2026%, the database interprets % as "zero or more characters". If users need to match literal % or _ characters in data, escape wildcards using database syntax:

~~~sql
WHERE order_number LIKE :keyword ESCAPE '!'
~~~

In Java:

~~~java
private static String toContainsPattern(String input) {
    String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
    return "%" + escaped + "%";
}
~~~

This is escaping for **LIKE search semantics**, not a substitute for bind parameters. The resulting string must still be bound via :keyword.

Points to standardize:

- Exact match: order_number = :orderNumber.
- Prefix match: order_number LIKE :pattern where pattern ends with %.
- Substring match: pattern has % on both ends.
- Case-insensitivity: depends on collation or using LOWER(column) = LOWER(:value); consider index impact.

LIKE with a leading wildcard such as %abc% usually cannot leverage a standard B-tree index. For large datasets, consider full-text search or a database-appropriate index type.

## 8. Dynamic Sorting Without Concatenating Input into SQL

Bind parameters are only for **values**; they cannot substitute column names or SQL keywords:

~~~sql
ORDER BY :sortColumn
~~~

does not tell the database to sort by the column named in the parameter value. It is usually interpreted as sorting by a constant value or lacks the intended semantics.

Never do this:

~~~java
String sql = "SELECT id, order_number FROM purchase_orders ORDER BY "
    + request.sortBy();
~~~

A user could send an arbitrary SQL expression in sortBy.

### 8.1. Using a Whitelist for Identifiers and Directions

Map public sort names to code-controlled identifiers:

~~~java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "createdAt", "o.created_at",
    "orderNumber", "o.order_number",
    "status", "o.status"
);

private static String resolveSortColumn(String requestedSort) {
    return SORT_COLUMNS.getOrDefault(requestedSort, "o.created_at");
}

private static String resolveDirection(String requestedDirection) {
    if (requestedDirection == null) {
        return "DESC";
    }

    return switch (requestedDirection.toUpperCase(Locale.ROOT)) {
        case "ASC" -> "ASC";
        case "DESC" -> "DESC";
        default -> throw new IllegalArgumentException(
            "Sort direction must be ASC or DESC");
    };
}
~~~

After validation:

~~~java
String sql = """
    SELECT o.id, o.order_number, o.status, o.created_at
    FROM purchase_orders o
    ORDER BY
    """ + resolveSortColumn(requestedSort)
        + " " + resolveDirection(requestedDirection)
        + ", o.id DESC";
~~~

This string concatenation is safe because identifiers and directions can come only from fixed whitelists. Never place raw request values into SQL.

Always append a unique tie-breaker key such as id so pagination order remains stable when multiple rows share the same sort value.

## 9. Pagination with Bound Parameters

For databases supporting LIMIT and OFFSET syntax:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

pageSize and offset are numeric values and can be bound like other parameters. Still, validate limits at the application layer:

~~~java
if (page < 0) {
    throw new IllegalArgumentException("page must not be negative");
}
if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("pageSize must be between 1 and 100");
}

long offset = Math.multiplyExact((long) page, pageSize);
params.addValue("pageSize", pageSize);
params.addValue("offset", offset);
~~~

Never allow clients to request an unbounded page size, which can cause resource-intensive queries. Pagination syntax varies across databases; the example above uses a LIMIT/OFFSET dialect.

For very deep pages, large OFFSET values can be costly. Consider keyset pagination:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The cursor consists of the timestamp and ID from the end of the previous page. Cursor values remain bound; column ordering in ORDER BY is an application-defined constant.

## 10. Combining AND and OR Conditions Intentionally

When there are multiple alternatives, use parentheses to preserve logic. For example, finding orders with status DRAFT or SUBMITTED belonging to a specific customer:

~~~sql
WHERE o.customer_id = :customerId
  AND (o.status = :statusA OR o.status = :statusB)
~~~

Or using IN:

~~~sql
WHERE o.customer_id = :customerId
  AND o.status IN (:statuses)
~~~

Do not append conditions in arbitrary order without parentheses. In SQL, AND has higher precedence than OR; missing parentheses can cause a filter condition to apply incorrectly.

Unintended example:

~~~sql
WHERE customer_id = :customerId
  AND status = 'DRAFT'
   OR status = 'SUBMITTED'
~~~

The SQL above can return every SUBMITTED order from other customers. Use parentheses or IN to express intent accurately.

## 11. Distinguishing Null, Empty Strings, and Omitted Filters

Search APIs usually need clear input conventions:

| Input | Common Handling |
|---|---|
| Field omitted | Skip filter |
| Field has value | Apply condition |
| Whitespace-only string | Normalize to no filter, or reject |
| Explicit null value | Decide whether it means skip filter or match NULL column |
| Want rows where column is NULL | Use an explicit column IS NULL condition |

A single null parameter cannot simultaneously represent "do not apply filter" and "only return rows where column is NULL". If matching NULL is required, add a separate filter option or explicit predicate:

~~~sql
o.optional_note IS NULL
~~~

When a filter may request NULL values, consider an enum/flag such as NoteFilter.ANY, NULL_ONLY, VALUE_ONLY to distinguish states rather than relying on a null String.

## 12. When to Use Derived Queries, @Query, or NamedParameterJdbcTemplate?

| Approach | Suitable When | Limitations |
|---|---|---|
| Derived query | A few common condition combinations easily expressed in method names | Many optional combinations cause method count to explode |
| @Query | Fixed SQL statement, few filters, tied to repository | Awkward when assembling many optional predicates |
| NamedParameterJdbcTemplate | Many optional filters, IN lists, dynamic sorting and pagination | Must manage SQL structure and DTO mapping manually |
| Specialized SQL or query builder | Complex queries with many condition types | Requires extra abstraction and strict control of SQL sources |

Spring Data JDBC does not provide Spring Data JPA's Criteria/Specification suite. For complex dynamic queries, do not assume you can take JpaSpecificationExecutor or JPA Criteria and use them directly with Spring Data JDBC.

A few derived query methods may suffice:

~~~java
List<PurchaseOrder> findByStatus(String status);

List<PurchaseOrder> findByCustomerIdAndStatus(
    Long customerId,
    String status
);
~~~

But with a large set of independent filters, NamedParameterJdbcTemplate usually expresses them more cleanly without declaring every method combination.

## 13. Optimizing Performance of Dynamic Queries

Safe dynamic queries still need optimization for the workload. Notes:

- Add predicates only when filters have valid values.
- Use direct column comparisons where possible, such as created_at >= :fromTime.
- Avoid wrapping columns in functions like DATE(created_at) if you want standard index usage; use appropriate time ranges instead.
- Create indexes matching actual WHERE and ORDER BY conditions.
- Cap page sizes.
- Avoid SELECT * when only a subset of columns is needed.
- Inspect execution plans for common filter combinations.

For example, searching by status and time can be supported by an index:

~~~sql
CREATE INDEX idx_orders_status_created
    ON purchase_orders(status, created_at, id);
~~~

This is one illustrative option. Column order in a composite index should reflect filter selectivity, sort order, and the specific database. Every index also adds write overhead and storage cost.

### 13.1. OR with NULL Parameters Can Affect Execution Plans

A static query:

~~~sql
WHERE (:status IS NULL OR status = :status)
~~~

is simple in code, but the OR expression can make it harder for the optimizer to use indexes effectively in some databases or data distributions. A dynamic query that adds:

~~~sql
WHERE status = :status
~~~

only when the filter is provided can give the optimizer clearer conditions. Measure both approaches with execution plans and representative data; there is no single performance rule that holds for all databases.

## 14. Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| SQL injection via status or keyword | Concatenating user values into SQL | Use named parameters |
| Empty string fails to filter | Checking only for null | Normalize empty/blank strings per convention |
| Query errors on IN () | Passing an empty collection | Define semantics and handle before running SQL |
| Sort allows SQL injection | Concatenating column name directly from request | Whitelist identifiers and directions |
| LIKE matches unintended wildcards | % and _ have special meaning | Escape wildcards when literal matching is needed |
| Cannot bind column names as parameters | Parameters represent values only | Whitelist column names in code |
| Unstable pagination results | ORDER BY lacks unique tie-breaker | Add ID to ordering |
| Slow queries when filters are skipped | Using OR with null parameters or missing indexes | Compare dynamic vs. static queries with execution plans |
| Type error when binding null | Driver needs explicit SQL type | Use MapSqlParameterSource.addValue with appropriate Types |
| Date filter misses end-of-day rows | Using inclusive endpoints with unclear precision | Use half-open intervals >= from and < to |
| OR conditions leak out-of-scope rows | Missing parentheses | Group expressions in parentheses or use IN |

## 15. Practice Exercises

### Exercise 1 — Basic Filters

1. Create OrderSearchFilter with status, customerId, createdFrom, and createdTo.
2. Use NamedParameterJdbcTemplate.
3. Add predicates only when the corresponding field has a value.
4. Bind all values via MapSqlParameterSource.
5. Test searching by status only, customer only, and both combined.

### Exercise 2 — List Filter

1. Add a multi-status filter using IN (:statuses).
2. Test null input, an empty collection, and a populated collection.
3. Define clear semantics for each case.
4. Verify IN () is never generated.

### Exercise 3 — LIKE Search

1. Add substring search on order number.
2. Bind values containing %, _, and the escape character.
3. Add ESCAPE and a literal-escaping function.
4. Distinguish literal search from wildcard search.

### Exercise 4 — Sorting and Pagination

1. Support sorting by date, order number, or status.
2. Map sort choices through a whitelist.
3. Accept only ASC or DESC.
4. Bind page size and offset.
5. Add ID as a tie-breaker key to keep ordering stable.

### Exercise 5 — Comparing Two Implementations

1. Write a static query using (:status IS NULL OR status = :status).
2. Write a dynamic query adding status = :status only when the filter is present.
3. Run both on the same data and conditions.
4. Inspect execution plans and compare timings.
5. Document trade-offs in simplicity and index utilization.

## 16. Conclusion

To add optional filters safely, **assemble fixed SQL clauses in code and bind all values using parameters**. NamedParameterJdbcTemplate is a flexible choice when you have many filters, IN lists, date ranges, dynamic sorting, and pagination. For a few simple conditions, a static SQL statement using (:parameter IS NULL OR column = :parameter) or a repository @Query can also work well.

Only column names, sort directions, or SQL structural clauses should be selected from whitelists; they cannot be bound like ordinary values. Explicitly handle nulls, empty strings, empty collections, and LIKE wildcards. Finally, inspect execution plans to decide between static queries and dynamically assembled predicates.

The core principle is that search values are always sent separately from the SQL statement. The application controls query structure, while input data determines only the values of declared parameters.
