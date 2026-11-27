# Custom RowMapper for JOIN Results and Reports

In **Spring Data Relational JDBC (Spring Data JDBC)**, repositories focus on saving and loading aggregate roots according to the domain model. Reporting screens often need data from multiple tables: orders, customers, order lines, product names, or aggregated metrics. Such results are usually not a complete aggregate and should not be forced into entities just to leverage CRUD repositories.

A suitable approach is to use **Spring JDBC** with **`RowMapper<T>`** to map each ResultSet row into a dedicated DTO/projection for read queries. Spring Data JDBC and Spring JDBC can share the same DataSource in a Spring Boot application; repositories continue to manage aggregates, while JdbcTemplate or NamedParameterJdbcTemplate executes JOIN and reporting queries.

## 1. Why Do We Need a Custom `RowMapper`?

Suppose an order report page needs to display:

- Order ID and creation timestamp.
- Order status.
- Customer code and name.
- Total number of order items and order total amount.

This information spans multiple tables. If you load each Order via OrderRepository, then load Customer and each OrderItem separately, the application may issue many queries and must assemble the data manually. If you try to cram all report results into the Order entity, the domain model gets mixed with presentation concerns.

Instead, create a reporting DTO and use SQL JOIN/aggregates so the database returns the exact columns needed:

~~~mermaid
flowchart TB
    Service["OrderReportService"]
    Query["NamedParameterJdbcTemplate<br/>SQL JOIN / GROUP BY"]
    DB[("Database<br/>orders + customers + order_items")]
    RS["ResultSet<br/>each result row"]
    Mapper["OrderReportRowMapper"]
    DTO["OrderReportRow DTO"]
    API["Controller / Export / Report"]
    Service --> Query --> DB --> RS --> Mapper --> DTO --> API
~~~

**RowMapper** is the bridge between a row in a ResultSet and a Java object. It provides explicit control over column names, data types, null values, and DTO structure.

## 2. What Is a `RowMapper`?

The RowMapper<T> interface belongs to the org.springframework.jdbc.core package:

~~~java
package org.springframework.jdbc.core;

import java.sql.ResultSet;
import java.sql.SQLException;

public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

The framework calls mapRow for each result row and uses the returned objects to build a list. Parameters:

- ResultSet rs: the current row of the query.
- int rowNum: the zero-based position of the row in the result set.
- Return value: an object of type T constructed from the current row.

Typically a RowMapper should **not maintain state across calls**. Each mapRow invocation maps only the current row and returns a new DTO. Do not store the ResultSet in a field, and do not retain data from the previous row for grouping.

### RowMapper Is Not Spring Data JDBC's Aggregate Mapper

The two mechanisms have different purposes:

| Mechanism | Purpose | Typical return type |
|---|---|---|
| CrudRepository<Order, Long> | Read/write aggregates via domain mapping | Order |
| RowMapper<OrderReportRow> | Map rows of custom SQL | DTO/report row |
| ResultSetExtractor<T> | Process an entire ResultSet into one structure | An aggregated DTO, map, or grouped list |

RowMapper belongs to Spring JDBC. It does not apply aggregate rules, does not load child collections via @MappedCollection, and does not replace Spring Data JDBC's mapping mechanism.

## 3. Setting Up the JOIN Example

Suppose we have the following tables:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE sales_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_orders(id),
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14, 2) NOT NULL
);
~~~

Each sales_orders row references one Customer; an Order can have multiple OrderItems. A reporting query can JOIN all three tables and compute totals:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.created_at AS order_created_at,
    c.customer_code AS customer_code,
    c.display_name AS customer_name,
    COUNT(i.id) AS item_count,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY
    o.id,
    o.status,
    o.created_at,
    c.customer_code,
    c.display_name
ORDER BY o.created_at DESC, o.id DESC;
~~~

LEFT JOIN preserves orders with no items yet; COUNT(i.id) returns 0 when there are no items; COALESCE converts a null sum to 0. Both timestamps use a half-open interval [from_time, to_time) to avoid double-counting boundaries across consecutive periods.

The SQL above uses common PostgreSQL and MySQL syntax. Timestamp types, precision, and time binding must match your project's schema and JDBC driver.

## 4. Creating the Reporting DTO

The DTO contains only the information the report needs:

~~~java
package com.example.sales.report;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderReportRow(
    Long orderId,
    String orderStatus,
    LocalDateTime orderCreatedAt,
    String customerCode,
    String customerName,
    long itemCount,
    BigDecimal totalAmount
) {}
~~~

This is a **read model**. It does not need @Id, @Table, or a Spring Data JDBC CRUD repository. The DTO can merge data from multiple aggregates without altering domain boundaries.

If the database returns timestamps with a timezone, consider OffsetDateTime or Instant instead of LocalDateTime, and establish a consistent storage/display timezone policy. The example assumes created_at is a timestamp without timezone.

## 5. Writing a Custom `RowMapper`

~~~java
package com.example.sales.report;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Component;

@Component
public class OrderReportRowMapper
        implements RowMapper<OrderReportRow> {

    @Override
    public OrderReportRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderReportRow(
            rs.getLong("order_id"),
            rs.getString("order_status"),
            rs.getTimestamp("order_created_at").toLocalDateTime(),
            rs.getString("customer_code"),
            rs.getString("customer_name"),
            rs.getLong("item_count"),
            rs.getBigDecimal("total_amount")
        );
    }
}
~~~

The mapper uses the **aliases** declared in SQL. For example, o.id AS order_id lets the mapper read order_id, avoiding ambiguity when multiple tables share id, status, or created_at columns.

If a column is guaranteed non-null by the schema, you can use the corresponding getter directly. If a column can be null, handle null explicitly rather than letting Java primitives silently turn null into 0.

### Handling Nullable Columns with Primitives

ResultSet.getLong() returns 0 when the SQL column is NULL; call wasNull() to distinguish them:

~~~java
long rawValue = rs.getLong("optional_customer_id");
Long customerId = rs.wasNull() ? null : rawValue;
~~~

Or use getObject with a wrapper type if the JDBC driver supports the conversion:

~~~java
Long customerId = rs.getObject("optional_customer_id", Long.class);
~~~

With LEFT JOINs, columns from the right-hand table can be null. The DTO should use reference types like Long, Integer, BigDecimal, String, or nullable date-time types instead of primitives when that state must be preserved.

## 6. Executing Queries with `NamedParameterJdbcTemplate`

NamedParameterJdbcTemplate lets you write named placeholders such as :fromTime instead of positional ? markers. Example query class:

~~~java
package com.example.sales.report;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReportQuery {

    private static final String SQL = """
        SELECT
            o.id AS order_id,
            o.status AS order_status,
            o.created_at AS order_created_at,
            c.customer_code AS customer_code,
            c.display_name AS customer_name,
            COUNT(i.id) AS item_count,
            COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
        FROM sales_orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE o.created_at >= :fromTime
          AND o.created_at < :toTime
        GROUP BY
            o.id, o.status, o.created_at,
            c.customer_code, c.display_name
        ORDER BY o.created_at DESC, o.id DESC
        """;

    private final NamedParameterJdbcTemplate jdbc;
    private final OrderReportRowMapper rowMapper;

    public OrderReportQuery(
            NamedParameterJdbcTemplate jdbc,
            OrderReportRowMapper rowMapper) {
        this.jdbc = jdbc;
        this.rowMapper = rowMapper;
    }

    public List<OrderReportRow> findOrders(
            LocalDateTime fromTime,
            LocalDateTime toTime) {

        var params = new MapSqlParameterSource()
            .addValue("fromTime", fromTime)
            .addValue("toTime", toTime);

        return jdbc.query(SQL, params, rowMapper);
    }
}
~~~

Spring Boot normally auto-configures NamedParameterJdbcTemplate when a JDBC starter and DataSource are present. If a project uses Spring Data JDBC, the corresponding JDBC dependencies are typically already in the dependency graph; let Spring Boot dependency management align compatible versions.

Calling the query:

~~~java
List<OrderReportRow> rows =
    orderReportQuery.findOrders(
        LocalDateTime.of(2026, 1, 1, 0, 0),
        LocalDateTime.of(2026, 2, 1, 0, 0)
    );
~~~

jdbc.query(sql, params, rowMapper) runs the query, invokes the mapper for each row, and returns List<OrderReportRow>. Parameters are bound separately from SQL; never concatenate timestamps or user-supplied values into the statement string.

## 7. Using `JdbcTemplate` with Positional Parameters

If you prefer ? placeholders, you can use JdbcTemplate:

~~~java
String sql = """
    SELECT id, customer_id, status, created_at
    FROM sales_orders
    WHERE status = ?
    ORDER BY created_at DESC, id DESC
    """;

List<OrderSummary> orders = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("id"),
        rs.getLong("customer_id"),
        rs.getString("status"),
        rs.getTimestamp("created_at").toLocalDateTime()
    ),
    "CONFIRMED"
);
~~~

With JdbcTemplate, parameter values match the order of ? markers. With NamedParameterJdbcTemplate, values match by name. Both use bind parameters; choose based on query clarity and parameter count.

The lambda (rs, rowNum) -> ... is a concise RowMapper. When mapping grows long or is reused, extracting a dedicated class makes code easier to read and test.

## 8. Many-to-One JOIN: One Result Row per DTO

Joining Order with Customer is a many-to-one relationship. Each Order has only one Customer, so unless the query joins another multi-row collection, each Order produces one result row:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.id AS customer_id,
    c.customer_code AS customer_code,
    c.display_name AS customer_name
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id DESC;
~~~

DTO:

~~~java
public record OrderCustomerRow(
    Long orderId,
    String orderStatus,
    Long customerId,
    String customerCode,
    String customerName
) {}
~~~

Mapper:

~~~java
RowMapper<OrderCustomerRow> mapper = (rs, rowNum) ->
    new OrderCustomerRow(
        rs.getLong("order_id"),
        rs.getString("order_status"),
        rs.getLong("customer_id"),
        rs.getString("customer_code"),
        rs.getString("customer_name")
    );
~~~

This is an ideal fit for RowMapper: **each SQL row corresponds to one independent DTO object**. Joining merely fetches display data; it does not make Customer a child object owned by Order.

## 9. One-to-Many JOIN: Avoiding Duplicate Parent DTOs

When joining Order with OrderItem, one Order can appear multiple times:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.display_name AS customer_name,
    i.id AS item_id,
    i.sku AS item_sku,
    i.quantity AS item_quantity,
    i.unit_price AS item_unit_price
FROM sales_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
~~~

If an Order has three items, the ResultSet has three rows with the same order_id. With a simple RowMapper<OrderSummary>, you receive three OrderSummary objects repeating parent fields. RowMapper does not automatically group three items into a list inside one Order.

Choose one of two designs:

1. **Flat DTO:** each row is an OrderItemReportRow, accepting Order repetition for each item. Fits CSV exports, tabular reports, or detail tables.
2. **Hierarchical DTO:** one Order contains a list of items. Use ResultSetExtractor or a grouping step to collapse rows by Order ID.

### Hierarchical DTO

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderDetailReport(
    Long orderId,
    String orderStatus,
    String customerName,
    List<OrderItemReport> items
) {}

public record OrderItemReport(
    Long itemId,
    String sku,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

### `ResultSetExtractor` to Group Multiple Rows

ResultSetExtractor<T> receives the entire ResultSet, fitting when results must be grouped into a parent-child structure:

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.ResultSetExtractor;

public class OrderDetailReportExtractor
        implements ResultSetExtractor<List<OrderDetailReport>> {

    @Override
    public List<OrderDetailReport> extractData(ResultSet rs)
            throws SQLException {

        Map<Long, OrderAccumulator> grouped = new LinkedHashMap<>();

        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            OrderAccumulator order = grouped.get(orderId);

            if (order == null) {
                order = new OrderAccumulator(
                    orderId,
                    rs.getString("order_status"),
                    rs.getString("customer_name")
                );
                grouped.put(orderId, order);
            }

            long itemId = rs.getLong("item_id");
            boolean itemIsNull = rs.wasNull();

            // LEFT JOIN without item: do not add a child row.
            if (!itemIsNull) {
                order.items.add(new OrderItemReport(
                    itemId,
                    rs.getString("item_sku"),
                    rs.getObject("item_quantity", Integer.class),
                    rs.getBigDecimal("item_unit_price")
                ));
            }
        }

        List<OrderDetailReport> result = new ArrayList<>();
        for (OrderAccumulator order : grouped.values()) {
            result.add(order.toReport());
        }
        return result;
    }

    private static final class OrderAccumulator {
        private final Long id;
        private final String status;
        private final String customerName;
        private final List<OrderItemReport> items = new ArrayList<>();

        private OrderAccumulator(
                Long id,
                String status,
                String customerName) {
            this.id = id;
            this.status = status;
            this.customerName = customerName;
        }

        private OrderDetailReport toReport() {
            return new OrderDetailReport(
                id, status, customerName, List.copyOf(items)
            );
        }
    }
}
~~~

Key points:

- LinkedHashMap preserves Order appearance order from SQL ORDER BY.
- Each order_id creates only one accumulator.
- Each row whose item_id is not SQL NULL adds one item.
- A LEFT JOIN with no items still creates an Order with an empty list.
- Finally, each accumulator converts to an immutable DTO.

For this query, ResultSetExtractor fits better than RowMapper because mapping must observe multiple rows to construct one parent object.

## 10. Choosing `RowMapper`, `ResultSetExtractor`, or a Flat DTO Query?

| Need | Choice |
|---|---|
| Each SQL row is an independent DTO | RowMapper<T> |
| Order-Customer JOIN, one row per Order | RowMapper<OrderCustomerRow> |
| Flat report, one row per OrderItem | RowMapper<OrderItemReportRow> |
| Parent-child JOIN needing one Order containing an item list | ResultSetExtractor<List<OrderDetailReport>> |
| Single aggregate value such as COUNT/SUM | queryForObject(...) or appropriate scalar mapper |
| Data requiring domain aggregate mapping | OrderRepository.findById(...) |

Do not reach for RowMapper merely because a query has a JOIN. Look at the **shape of the ResultSet** and the desired output structure. If one row corresponds to one object, RowMapper is simple. If multiple rows must combine into one object, use an extractor/grouping.

## 11. Mapping Data Types and NULLs Properly

ResultSet getters must match column types:

| SQL | Common getter | Java type |
|---|---|---|
| Non-null BIGINT | getLong() | long/Long |
| Non-null INTEGER | getInt() | int/Integer |
| VARCHAR | getString() | String |
| DECIMAL/NUMERIC | getBigDecimal() | BigDecimal |
| DATE | getDate() or getObject(..., LocalDate.class) | LocalDate |
| TIMESTAMP | getTimestamp() | Timestamp/LocalDateTime |
| BOOLEAN | getBoolean() | boolean/Boolean |

For primitive getters, getLong, getInt, and getBoolean return default values when the SQL column is NULL; call wasNull() immediately after the getter to check. wasNull() refers to the most recently read value, so never call another getter before checking it.

Safe example:

~~~java
long raw = rs.getLong("optional_quantity");
Integer quantity = rs.wasNull() ? null : Math.toIntExact(raw);
~~~

Or:

~~~java
Integer quantity = rs.getObject("optional_quantity", Integer.class);
~~~

With LEFT JOINs, checking the child table's primary key is a reliable way to know whether a child row exists. Do not infer “no item” merely from a descriptive nullable column like SKU or notes.

## 12. Separating SQL and `RowMapper` for Maintainability

For large reports, separate the components:

- **Query class/read repository:** holds SQL and calls NamedParameterJdbcTemplate.
- **RowMapper:** maps one row to a DTO.
- **DTO/projection:** represents results for the use case.
- **Service:** coordinates parameters, access permissions, and read business logic.

Example organization:

~~~text
com.example.sales
├── order/
│   ├── Order.java
│   └── OrderRepository.java
└── report/
    ├── OrderReportRow.java
    ├── OrderReportRowMapper.java
    ├── OrderReportQuery.java
    └── OrderReportService.java
~~~

Do not place every reporting SQL statement onto the aggregate entity. A separate structure lets reports evolve with display needs without complicating the domain model.

## 13. Transactions and `@Transactional(readOnly = true)`

A reporting query is typically read-only. You can annotate the service:

~~~java
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReportService {

    private final OrderReportQuery query;

    public OrderReportService(OrderReportQuery query) {
        this.query = query;
    }

    @Transactional(readOnly = true)
    public List<OrderReportRow> report(
            LocalDateTime from,
            LocalDateTime to) {
        return query.findOrders(from, to);
    }
}
~~~

readOnly = true is metadata/a hint to the transaction manager and provider/driver; exact optimizations or behavior depend on configuration. It is **not a security mechanism** guaranteeing the database rejects every write statement. When writes must be prevented, enforce database privileges or connection policies.

When the same use case reads data using both a Spring Data JDBC repository and NamedParameterJdbcTemplate, both components can participate in the same transaction when sharing the same DataSource and appropriately configured transaction manager. This helps provide a consistent view within a transaction boundary.

## 14. Performance of JOINs and Reports

RowMapper assists with result conversion; it does not make SQL faster on its own. Performance depends primarily on the query, indexes, row count returned, and data read.

Some principles:

1. SELECT only needed columns; avoid SELECT * in multi-table reports.
2. Use unique aliases for shared column names like id, status, created_at.
3. Index frequently used JOIN/filter columns, such as sales_orders.customer_id, order_items.order_id, and date columns matching your workload.
4. Inspect execution plans before guessing at optimizations.
5. Paginate or limit results for large reports.
6. Avoid uncontrolled many-to-many or multi-collection JOINs that inflate row counts.
7. For summary reports, compute COUNT, SUM, AVG in SQL when the database handles it efficiently; map scalar results to DTOs.

Illustrative indexes:

~~~sql
CREATE INDEX idx_sales_orders_created_at
    ON sales_orders(created_at);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
~~~

Specific indexes must be grounded in WHERE, JOIN, ORDER BY predicates and real data. Adding indexes increases storage and INSERT/UPDATE overhead; do not add indexes just because a column appears in one query.

## 15. Pagination for Custom Reporting Queries

With custom SQL via NamedParameterJdbcTemplate, you can manage limit and offset manually:

~~~java
String sql = """
    SELECT
        o.id AS order_id,
        o.status AS order_status,
        c.display_name AS customer_name
    FROM sales_orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.status = :status
    ORDER BY o.created_at DESC, o.id DESC
    LIMIT :limit OFFSET :offset
    """;

var params = new MapSqlParameterSource()
    .addValue("status", "CONFIRMED")
    .addValue("limit", pageSize)
    .addValue("offset", (long) pageNumber * pageSize);

List<OrderCustomerRow> rows =
    namedParameterJdbcTemplate.query(sql, params, rowMapper);
~~~

The LIMIT/OFFSET syntax in the example fits PostgreSQL/MySQL; other databases may use different syntax. Validate pageNumber >= 0, pageSize > 0, and cap maximum page size before computing offset. Use long multiplication to avoid 32-bit integer overflow.

If total pages are needed, run a matching count query with the same filter criteria. If you only need to know “is there more data”, fetch one extra row (pageSize + 1) and drop the extra row from content. This logic is managed by the custom query class/service; NamedParameterJdbcTemplate does not automatically produce Page/Slice metadata like repository query methods.

## 16. Query Safety and Input Handling

Always bind values:

~~~java
var params = new MapSqlParameterSource()
    .addValue("status", requestedStatus)
    .addValue("fromTime", fromTime)
    .addValue("toTime", toTime);
~~~

Never concatenate strings directly:

~~~java
// Unsafe
String sql = "SELECT * FROM sales_orders WHERE status = '"
    + requestedStatus + "'";
~~~

Bind parameters protect input values from being interpreted as SQL syntax. However, placeholders cannot bind table names, column names, or ORDER BY keywords. If sorting is chosen from a request, map that choice through an allowlist of properties/identifiers before constructing SQL.

Additionally:

- Limit start/end date ranges and page sizes according to business policy.
- Avoid returning unnecessary personal data in reports.
- Check access permissions before querying customer/order data.
- Never log sensitive SQL parameters into production logs.

## 17. Testing `RowMapper` and Reporting Queries

You can unit-test a mapper with a mocked ResultSet, yet integration tests against a real database are usually far more valuable for verifying column names, data types, nulls, and dialect behavior.

Cases to test:

| Scenario | What to verify |
|---|---|
| Order with one Customer and multiple items | DTO holds accurate joined data |
| Order without items using LEFT JOIN | itemCount = 0, total amount equals 0 |
| Nullable column from right-hand table | DTO receives null instead of unintended 0 |
| Multiple Orders for the same Customer | Each Order produces the right report row |
| One Order with multiple items | Flat DTO has multiple rows or extractor groups into one Order |
| Empty time range | Empty list returned |
| Parameter containing quotes | Bind parameter remains literal data |
| Large totals or fractional amounts | Uses BigDecimal, never converted to double |

For monetary calculations, use BigDecimal/DECIMAL rather than double to avoid binary floating-point rounding errors. For date-times, check timezone and precision on your target database.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using RowMapper to build collections from one-to-many JOINs | Parent repeats per child row | Use flat DTOs or ResultSetExtractor to group |
| Failing to alias JOIN columns | id/status names collide, reading the wrong column | Assign clear aliases like order_id, customer_id |
| Calling getLong() on nullable column without wasNull() | SQL NULL turns into 0 | Check wasNull() or use wrappers via getObject |
| Using INNER JOIN when wanting to keep childless parents | Parents without items vanish from report | Use LEFT JOIN and handle null child columns |
| Using COUNT(*) after LEFT JOIN | Childless parent still yields one joined row, count becomes 1 | Use COUNT(child.id) |
| Summing after joining multiple independent collections | Rows multiply and sums get inflated | Aggregate each collection before joining or use subquery/CTE |
| Using SELECT * for DTOs | Mapping depends on column order/names and risks collisions | Select needed columns and alias clearly |
| Concatenating inputs into SQL | SQL injection | Use bind parameters |
| Returning reporting DTO as aggregate root | Mixing read model with domain model | Create dedicated DTOs for read use cases |
| Thinking `@Transactional(readOnly = true)` enforces DB read-only security | Other write paths can still execute | Use database privileges when protection is needed |
| Using double for money | Arithmetic rounding errors | Use DECIMAL/BigDecimal |

## 19. Practice Exercises

1. Create the three tables customers, sales_orders, and order_items with sample data for two customers, three orders, and multiple items.
2. Write an SQL JOIN of Order with Customer; map each row into OrderCustomerRow using RowMapper.
3. Write a report summarizing item count and total amount per Order using COUNT, SUM, COALESCE, and GROUP BY.
4. Create OrderReportRowMapper and invoke the query with NamedParameterJdbcTemplate.
5. Add an Order with no items; verify LEFT JOIN preserves the Order and yields total amount 0.
6. Write an Order-OrderItem JOIN query. First map into a flat DTO; then use ResultSetExtractor to group items into a list inside one Order DTO.
7. Introduce a nullable column from LEFT JOIN; try getLong() with wasNull() and compare against getObject(..., Long.class).
8. Add LIMIT/OFFSET pagination and verify page number, page size, and offset are bounded.
9. Run EXPLAIN to inspect which indexes support JOIN and WHERE conditions.
10. Test parameterized queries with input containing single quotes; confirm values cannot alter SQL structure.

## 20. Key Takeaways

**Spring JDBC's `RowMapper<T>` maps each ResultSet row into one object.** It is well suited for building DTOs/projections for JOIN results and reports without forcing presentation data into domain aggregates.

When one SQL row corresponds to one DTO, use RowMapper. When a one-to-many JOIN repeats parents and multiple rows must be grouped into a parent-child structure, use ResultSetExtractor or explicit grouping. Always alias columns, handle SQL NULLs, bind parameters, pick compatible Java types, and let the database execute JOINs/aggregations. Spring Data JDBC continues managing aggregates through repositories; custom reporting queries can use Spring JDBC with dedicated DTOs.
