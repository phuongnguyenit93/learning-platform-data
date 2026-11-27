# ResultSetExtractor and Grouping Multiple Rows into One Result

In **Spring Data Relational JDBC**, an SQL statement can return multiple rows while the application needs a Java result whose structure differs from individual rows. A common case is a JOIN between a parent table and a child table: an order has multiple product lines, so SQL returns one row per product line, whereas the screen needs a single order object containing a list of products.

Spring JDBC's **`ResultSetExtractor<T>`** solves this class of problem. Instead of mapping each row independently, the callback receives the entire `ResultSet` and decides how to iterate, group, and combine rows into a single result `T`. That result can be a nested DTO, a list of DTOs, a map, or another read structure.

This lesson focuses on using `ResultSetExtractor` to group multiple SQL rows into Java results, distinguishing it from `RowMapper` and `RowCallbackHandler`, and handling one-to-many JOINs, NULL values, duplicate rows, and pagination.

## 1. Why Group Multiple Rows into One Result?

Suppose the database has two tables:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL
);
```

An order can have multiple product lines:

```text
purchase_orders
+----+-------------+--------+
| id | order_number| status |
+----+-------------+--------+
| 42 | ORD-0042    | PAID   |
+----+-------------+--------+

order_items
+----+----------+--------------+----------+
| id | order_id | product_code | quantity |
+----+----------+--------------+----------+
| 1  | 42       | KB-01        | 2        |
| 2  | 42       | MS-02        | 1        |
| 3  | 42       | USB-03       | 3        |
+----+----------+--------------+----------+
```

JOIN query:

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
```

The SQL result has three rows:

| order_id | order_number | status | item_id | product_code | quantity |
|---:|---|---|---:|---|---:|
| 42 | ORD-0042 | PAID | 1 | KB-01 | 2 |
| 42 | ORD-0042 | PAID | 2 | MS-02 | 1 |
| 42 | ORD-0042 | PAID | 3 | USB-03 | 3 |

Yet the Java object the application wants to return may look like:

```text
OrderDetails
  id: 42
  orderNumber: ORD-0042
  status: PAID
  items:
    - OrderItem(id=1, productCode=KB-01, quantity=2)
    - OrderItem(id=2, productCode=MS-02, quantity=1)
    - OrderItem(id=3, productCode=USB-03, quantity=3)
```

This is a **multiple result rows → one parent object with a child collection** transformation. Using a simple `RowMapper` maps each row separately into its own object. `ResultSetExtractor` lets you read all rows and group them together.

## 2. Distinguishing `ResultSetExtractor`, `RowMapper`, and `RowCallbackHandler`

All three callbacks belong to Spring JDBC, but serve different purposes.

| API | Processing unit | Return value | Suitable cases |
|---|---|---|---|
| `RowMapper<T>` | Single row | One object per row | Each row corresponds to an independent DTO/entity |
| `ResultSetExtractor<T>` | Entire ResultSet | A single result `T` chosen by callback | Grouping rows, building nested objects, aggregating results |
| `RowCallbackHandler` | Single row | Nothing returned from callback | Processing each row via side effects, writing files, or streaming elsewhere |

### 2.1. `RowMapper`: One Row to One Object

```java
List<OrderItemView> items = jdbc.query(
    """
    SELECT id, product_code, quantity, unit_price
    FROM order_items
    WHERE order_id = :orderId
    ORDER BY id
    """,
    Map.of("orderId", 42L),
    (rs, rowNum) -> new OrderItemView(
        rs.getLong("id"),
        rs.getString("product_code"),
        rs.getInt("quantity"),
        rs.getBigDecimal("unit_price")
    )
);
```

Each row maps independently into an `OrderItemView`. The result of `query` is a list of objects. This is the simplest option when SQL results already have exactly one row per object the application wants to construct.

### 2.2. `ResultSetExtractor`: All Rows to One Result

`ResultSetExtractor<T>` has the general signature:

```java
@FunctionalInterface
public interface ResultSetExtractor<T> {
    T extractData(ResultSet rs) throws SQLException, DataAccessException;
}
```

The callback receives the executed `ResultSet` and calls `rs.next()` itself to traverse all rows. It decides on a single `T` to return.

```java
OrderDetails result = jdbc.query(
    sql,
    parameters,
    rs -> {
        // Iterate through the ResultSet, group rows,
        // and return a single OrderDetails.
    }
);
```

`NamedParameterJdbcTemplate.query(...)` manages JDBC resources around the callback. Never close the template-provided `ResultSet` or `Statement` inside the extractor.

### 2.3. `RowCallbackHandler`: Processing Rows Without Returning a Value

```java
jdbc.query(
    sql,
    parameters,
    rs -> {
        String code = rs.getString("product_code");
        auditBuffer.add(code);
    }
);
```

`RowCallbackHandler` is useful when processing rows one by one without building a return value. If you want to return a parent object containing a child list, `ResultSetExtractor` usually expresses intent more clearly.

## 3. DTO Structure for Nested Results

Create two records to represent the read data:

```java
import java.math.BigDecimal;
import java.util.List;

public record OrderItemView(
    Long id,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDetails(
    Long id,
    String orderNumber,
    String status,
    List<OrderItemView> items
) {}
```

`OrderDetails` is a DTO/read model for read queries. It does not have to be the aggregate class Spring Data JDBC uses for writes. This DTO simply expresses the result shape the screen or API needs.

Separating DTOs helps select only required columns, build parent/child structures proactively from JOINs, avoid coupling to domain aggregate constructors or lifecycles, and return convenient read results to APIs.

## 4. Using `ResultSetExtractor` to Group Items of One Order

Because the query looks up a single order by ID, we can keep one accumulator for that order and append each product line while iterating the ResultSet.

### 4.1. SQL

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
ORDER BY i.id;
```

Use `LEFT JOIN` so the order still appears even when it has no product lines yet. In that case, columns from `order_items` will be SQL NULL.

### 4.2. Internal Accumulator

An accumulator is a mutable object existing only while reading the ResultSet. Once all data is collected, we convert it to an immutable DTO.

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

final class OrderAccumulator {

    private final Long id;
    private final String orderNumber;
    private final String status;
    private final List<OrderItemView> items = new ArrayList<>();

    OrderAccumulator(Long id, String orderNumber, String status) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
    }

    void addItem(ResultSet rs) throws SQLException {
        Long itemId = rs.getObject("item_id", Long.class);

        // LEFT JOIN found no child row:
        // item_id will be NULL.
        if (itemId == null) {
            return;
        }

        items.add(new OrderItemView(
            itemId,
            rs.getString("product_code"),
            rs.getInt("quantity"),
            rs.getBigDecimal("unit_price")
        ));
    }

    OrderDetails toResult() {
        return new OrderDetails(
            id,
            orderNumber,
            status,
            List.copyOf(items)
        );
    }
}
```

`OrderAccumulator` holds parent fields and the child list. `addItem` checks the child row's ID before instantiating an object. When `item_id` is NULL, the order has no child lines; we avoid creating a fake `OrderItemView` with ID 0.

### 4.3. Repository Using `ResultSetExtractor`

```java
import java.util.Map;
import java.util.Optional;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderDetailsReadRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderDetailsReadRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderDetails> findById(long orderId) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                o.status,
                i.id AS item_id,
                i.product_code,
                i.quantity,
                i.unit_price
            FROM purchase_orders o
            LEFT JOIN order_items i ON i.order_id = o.id
            WHERE o.id = :orderId
            ORDER BY i.id
            """;

        OrderDetails result = jdbc.query(
            sql,
            Map.of("orderId", orderId),
            rs -> {
                OrderAccumulator order = null;

                while (rs.next()) {
                    if (order == null) {
                        order = new OrderAccumulator(
                            rs.getLong("order_id"),
                            rs.getString("order_number"),
                            rs.getString("status")
                        );
                    }

                    order.addItem(rs);
                }

                return order == null ? null : order.toResult();
            }
        );

        return Optional.ofNullable(result);
    }
}
```

Explanation:

1. `jdbc.query` runs the SQL and passes the ResultSet into the extractor.
2. `order` starts as `null` because no rows have been read yet.
3. The first row initializes the parent `OrderAccumulator`.
4. Each row converts into a child line if `item_id` is not NULL.
5. Once the ResultSet ends, `toResult()` creates an `OrderDetails` containing the full list.
6. If there are no rows, the extractor returns `null`; the repository wraps it into `Optional.empty()`.

`LEFT JOIN` guarantees an existing order with no items still produces one row with NULL item columns. If the order does not exist, the query returns zero rows and the result is `Optional.empty()`.

**Note:** the example uses `ResultSet.getObject(column, Long.class)` to read a nullable ID. If an older driver does not support this overload, use `getLong` followed immediately by `wasNull()`:

```java
long rawId = rs.getLong("item_id");
Long itemId = rs.wasNull() ? null : rawId;
```

Do not use `getLong` alone to detect NULL, because JDBC returns 0 for SQL NULL on primitive getters and requires `wasNull()` to distinguish them.

## 5. Grouping Multiple Orders into a Result List

If a query returns multiple orders, each with multiple product lines, you need one accumulator per order ID. A `Map` maintains the association between SQL rows and parent objects.

### 5.1. SQL for Multiple Orders

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.status = :status
ORDER BY o.id, i.id;
```

### 5.2. `ResultSetExtractor` Returning `List<OrderDetails>`

```java
public List<OrderDetails> findByStatus(String status) {
    String sql = """
        SELECT
            o.id AS order_id,
            o.order_number,
            o.status,
            i.id AS item_id,
            i.product_code,
            i.quantity,
            i.unit_price
        FROM purchase_orders o
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE o.status = :status
        ORDER BY o.id, i.id
        """;

    return jdbc.query(
        sql,
        Map.of("status", status),
        rs -> {
            Map<Long, OrderAccumulator> orders = new LinkedHashMap<>();

            while (rs.next()) {
                Long orderId = rs.getObject("order_id", Long.class);

                OrderAccumulator order = orders.get(orderId);
                if (order == null) {
                    order = new OrderAccumulator(
                        orderId,
                        rs.getString("order_number"),
                        rs.getString("status")
                    );
                    orders.put(orderId, order);
                }

                order.addItem(rs);
            }

            return orders.values().stream()
                .map(OrderAccumulator::toResult)
                .toList();
        }
    );
}
```

`LinkedHashMap` preserves the order in which orders first appear in the ResultSet. With `ORDER BY o.id, i.id`, the output list keeps orders sorted by ID and items sorted by ID.

This is the general pattern: one ResultSet containing multiple parent groups, each with multiple child rows, and the extractor returning a `List<OrderDetails>`.

### 5.3. Why Not Scan a `List` to Find the Parent on Every Row?

If on every row you scan the whole list to locate the parent object, cost scales as rows times groups. Using `Map<Id, Accumulator>` looks up the accumulator by key, typically around O(1) average cost per row.

A Map also prevents creating a new parent object every time a child line of the same order is read.

## 6. Handling `LEFT JOIN` and NULL Values Properly

`LEFT JOIN` is the standard choice when preserving parent objects even without child rows.

Example order with no product lines:

```text
order_id = 42
order_number = ORD-0042
status = NEW
item_id = NULL
product_code = NULL
quantity = NULL
unit_price = NULL
```

The extractor must check the key column of the child table:

```java
Long itemId = rs.getObject("item_id", Long.class);

if (itemId != null) {
    // Real child row exists, proceed with mapping.
}
```

Do not check `product_code != null` to decide whether an item exists, because a business column might be nullable in the schema. The child table's primary key is a much more reliable indicator.

### 6.1. SQL NULL and Java Primitives

Primitive getters such as `getInt` and `getLong` return default values when the SQL column is NULL. For example, `getInt` may return 0. If 0 is a valid value, call `wasNull()` to distinguish them:

```java
int quantityValue = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : quantityValue;
```

Or use `getObject` with a wrapper type if supported by the driver:

```java
Integer quantity = rs.getObject("quantity", Integer.class);
```

For `BigDecimal`, `getBigDecimal` returns `null` when the column is SQL NULL. Never silently turn NULL into 0 if the domain distinguishes those two states.

### 6.2. Do Not Create Fake Children from `LEFT JOIN` Rows

A common bug:

```java
// Wrong if item_id can be NULL:
items.add(new OrderItemView(
    rs.getLong("item_id"),
    rs.getString("product_code"),
    rs.getInt("quantity"),
    rs.getBigDecimal("unit_price")
));
```

When there is no item, this code creates an object with ID 0, quantity 0, and null fields. The result displays a phantom product line.

Always check the child primary key before mapping, as shown in the accumulator example.

## 7. Avoiding Duplicate Children When Joining Multiple Tables

A ResultSet can repeat the same child across multiple rows if the query JOINs another child table.

For instance, an order has 2 product lines and 3 notes. If you JOIN both `order_items` and `order_notes` simultaneously, the result can produce 2 × 3 = 6 rows for that order. Each product line appears repeated once per note.

```sql
SELECT
    o.id AS order_id,
    i.id AS item_id,
    i.product_code,
    n.id AS note_id,
    n.note_text
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
LEFT JOIN order_notes n ON n.order_id = o.id
WHERE o.id = :orderId;
```

Calling `items.add(...)` on every row will leave duplicates in the item list.

### 7.1. Use a Map Keyed by Child ID

You can replace the accumulator's list with a map:

```java
private final Map<Long, OrderItemView> items = new LinkedHashMap<>();

void addItem(ResultSet rs) throws SQLException {
    Long itemId = rs.getObject("item_id", Long.class);

    if (itemId == null) {
        return;
    }

    items.putIfAbsent(
        itemId,
        new OrderItemView(
            itemId,
            rs.getString("product_code"),
            rs.getInt("quantity"),
            rs.getBigDecimal("unit_price")
        )
    );
}
```

`putIfAbsent` guarantees the same item ID is added only once.

Similarly, if collecting notes, use a map keyed by `note_id`. When finalizing the DTO, convert `items.values()` and `notes.values()` into immutable lists.

### 7.2. Aggregate Child Tables Before Joining

If you only need total amounts and note counts, it is usually cleaner to aggregate each child table in a subquery/CTE prior to joining:

```sql
WITH item_summary AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount,
        COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
),
note_summary AS (
    SELECT
        order_id,
        COUNT(*) AS note_count
    FROM order_notes
    GROUP BY order_id
)
SELECT
    o.id,
    o.order_number,
    COALESCE(i.total_amount, 0) AS total_amount,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(n.note_count, 0) AS note_count
FROM purchase_orders o
LEFT JOIN item_summary i ON i.order_id = o.id
LEFT JOIN note_summary n ON n.order_id = o.id;
```

Each subquery returns one row per order, so the JOIN does not multiply items or notes. This approach is usually easier to read and prevents double-counting bugs.

## 8. Step-by-Step Mapping of a `ResultSet` into Nested DTOs

A well-structured extractor cleanly separates three tasks:

1. Identify the parent object corresponding to the current row.
2. Check whether the row contains a real child object.
3. Add or update the child object in the accumulator.

Logic template:

```java
ResultSetExtractor<List<OrderDetails>> extractor = rs -> {
    Map<Long, OrderAccumulator> groups = new LinkedHashMap<>();

    while (rs.next()) {
        Long orderId = rs.getObject("order_id", Long.class);

        OrderAccumulator parent = groups.get(orderId);
        if (parent == null) {
            parent = new OrderAccumulator(
                orderId,
                rs.getString("order_number"),
                rs.getString("status")
            );
            groups.put(orderId, parent);
        }

        parent.addItem(rs);
    }

    return groups.values().stream()
        .map(OrderAccumulator::toResult)
        .toList();
};
```

Explicit structure makes handling checked exceptions from ResultSet straightforward and clarifies when the parent object is initialized.

### 8.1. Preserving Data Order

If item order is meaningful, SQL needs an appropriate `ORDER BY`:

```sql
ORDER BY o.id, i.position, i.id;
```

`LinkedHashMap` and `List` preserve the order received from the ResultSet. They do not invent business ordering if the query lacks ORDER BY. Never rely on the physical order of rows in a table.

### 8.2. Avoid `SELECT *` in Complex Mappings

With multiple tables sharing `id`, `status`, or `created_at` columns, `SELECT *` creates ambiguous column names. Select columns explicitly with aliases:

```sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    i.id AS item_id,
    i.status AS item_status
...
```

Clear aliases reduce Java mapping mistakes and avoid relying on column positions.

## 9. `ResultSetExtractor` in `NamedParameterJdbcTemplate`

`NamedParameterJdbcTemplate` provides an overload taking `ResultSetExtractor<T>`:

```java
<T> T query(
    String sql,
    SqlParameterSource paramSource,
    ResultSetExtractor<T> rse
);
```

Example:

```java
MapSqlParameterSource parameters =
    new MapSqlParameterSource("orderId", 42L);

OrderDetails details = jdbc.query(
    sql,
    parameters,
    extractor
);
```

Named parameters such as `:orderId` bind to appropriate JDBC parameters. Never concatenate IDs or request values directly into SQL strings.

If using `JdbcTemplate` positional parameters, pass values matching the order of `?` markers:

```java
OrderDetails details = jdbcTemplate.query(
    sql,
    new Object[] { 42L },
    extractor
);
```

Exact overload signatures on `JdbcTemplate` can evolve or be deprecated across Spring Framework versions. For new code, use the overload recommended by your version; the key principle is that the extractor receives a template-managed ResultSet.

### 9.1. Lambdas Can Replace Separate Classes

Because `ResultSetExtractor<T>` is a functional interface, a lambda is often clear enough:

```java
ResultSetExtractor<OrderDetails> extractor = rs -> {
    // Iterate through the ResultSet and return a single OrderDetails.
};
```

If mapping logic grows long, extract a dedicated class implementing `ResultSetExtractor<T>` or split mapper/accumulator helpers into small classes. Avoid letting one repository method balloon with unrelated mapping branches.

## 10. `ResultSetExtractor` Does Not Manage Aggregate Lifecycles

`ResultSetExtractor` is a **Spring JDBC** callback, not Spring Data JDBC's aggregate-saving API.

It runs read SQL, traverses the entire ResultSet, groups rows, and builds an application-defined DTO/read model or result object.

It does not automatically:

- Apply `JdbcAggregateTemplate` lifecycle callbacks.
- Check aggregate newness or version.
- Save aggregates and child entities under Spring Data JDBC rules.
- Track object mutations after returning.
- Create a persistence context or lazy-loading proxies.

When results are read-only, DTOs from `ResultSetExtractor` are a natural fit. When domain updates are needed, load the aggregate using repository/aggregate operations under proper mapping and perform explicit write operations.

## 11. Pagination When Grouping Multiple Rows

When a JOIN query returns multiple rows per parent object, do not apply `LIMIT/OFFSET` directly to the joined rows if the goal is paginating by parent object.

Suppose an order has 5 items. If the JOIN query limits to 10 rows, those 10 rows might represent only 2 orders or part of the second order's items. The grouped output will not contain two complete aggregates.

### 11.1. Paginate Parent IDs First

```sql
WITH page_orders AS (
    SELECT id
    FROM purchase_orders
    WHERE status = :status
    ORDER BY id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    i.id AS item_id,
    i.product_code,
    i.quantity,
    i.unit_price
FROM page_orders p
JOIN purchase_orders o ON o.id = p.id
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id DESC, i.id;
```

The `page_orders` CTE selects the exact set of orders for the page. Then the outer query fetches all items for those orders. The extractor can group rows into parent/child DTOs without truncating child items at page boundaries.

CTE and LIMIT/OFFSET syntax depend on the database dialect; use the form appropriate for your RDBMS.

### 11.2. Counting Parent Objects

If the UI needs total order count, the count query must count matching orders:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

If filtering on a child table causes JOINs to duplicate orders, use `COUNT(DISTINCT o.id)` or `EXISTS` to count unique roots.

### 11.3. Total Pages

Given `totalElements` and `pageSize`:

```java
long totalPages = totalElements / pageSize
    + (totalElements % pageSize == 0 ? 0 : 1);
```

Ensure `pageSize > 0` before computing. If total count is unnecessary, fetch one extra parent ID to determine whether a next page exists instead of running a count query.

## 12. Memory Management and Large Result Sets

`ResultSetExtractor` typically accumulates results into in-memory collections. If a query returns hundreds of thousands of objects, memory consumption can become substantial.

Before using an extractor to build a massive list, consider:

- Adding filters to narrow the result set.
- Paginating by root.
- Selecting only required columns.
- Using batch processing when work can be chunked.
- Using `RowCallbackHandler` if processing row-by-row without keeping all results in memory.
- Using Spring JDBC streaming when truly needed, closing the stream properly while keeping the connection/transaction open across stream consumption.

Do not treat `ResultSetExtractor` as an automatic streaming mechanism. The callback typically maintains an accumulator/collection to return the final result; memory footprint depends on the structure the application constructs.

## 13. Error Handling and JDBC Resources

`ResultSetExtractor` executes under Spring JDBC template resource management. The template manages JDBC resources created for the query, including statements and result sets.

Inside the extractor:

- Do not close `ResultSet` yourself.
- Do not store ResultSet in a field for use after the callback finishes.
- Do not return `ResultSet` or cursor-dependent objects.
- Extract needed values into Java objects right inside the callback.
- Let SQL exceptions be translated by Spring into its data access exception hierarchy.

Example to avoid:

```java
ResultSet savedResultSet = jdbc.query(
    sql,
    parameters,
    rs -> rs
);
```

Once the template finishes the query, ResultSet is no longer a valid resource for the service to use.

Instead, return mapped DTOs/lists. If mapping throws an error, the exception propagates through Spring JDBC's handling while query resources remain safely managed by the template.

## 14. Testing `ResultSetExtractor`

A test suite should verify both the parent structure and child collections.

| SQL data | Expected result |
|---|---|
| Order does not exist | `Optional.empty()` |
| Order has one item | One parent DTO, one item |
| Order has multiple items | One parent DTO, complete item list |
| Order has no items with LEFT JOIN | Parent DTO exists, empty list |
| Multiple orders in query | Exactly one DTO per parent ID |
| JOIN repeats item rows | Each item ID appears once when using a dedup map |
| Nullable child column | No fake child created from NULL |
| Rows sharing sort key | ORDER BY includes tie-breaker for deterministic order |

### 14.1. Example Test for an Order with Multiple Items

```java
@DataJdbcTest
class OrderDetailsReadRepositoryTest {

    @Autowired
    OrderDetailsReadRepository repository;

    @Test
    void groupsRowsIntoOneOrderWithItsItems() {
        // Arrange: insert order 42 and two order_items in the test database.

        Optional<OrderDetails> result = repository.findById(42L);

        assertThat(result).isPresent();
        assertThat(result.get().items()).hasSize(2);
        assertThat(result.get().items())
            .extracting(OrderItemView::productCode)
            .containsExactly("KB-01", "MS-02");
    }
}
```

This test is an illustrative skeleton; add SQL fixtures or repository setup matching your project's test schema. For custom JDBC queries, use a database/dialect matching production whenever queries rely on vendor-specific syntax.

### 14.2. Testing an Order Without Items

Because the query uses `LEFT JOIN`, an order without child lines is still read:

```java
Optional<OrderDetails> result = repository.findById(orderWithoutItems);

assertThat(result).isPresent();
assertThat(result.get().items()).isEmpty();
```

This test is especially important for catching bugs that fabricate fake children from NULL columns.

## 15. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| One order turns into multiple parent objects | Each JOIN row mapped independently | Group by parent ID using a Map |
| Item list contains a fake item with ID 0 | Calling `getLong` without checking SQL NULL | Use `getObject` wrapper or `wasNull()` |
| Duplicate items | Joining multiple child tables multiplies rows | Deduplicate by child ID or pre-aggregate before JOIN |
| Childless order disappears | Using INNER JOIN | Use LEFT JOIN when parents must be preserved |
| Item list in wrong order | SQL lacks proper ORDER BY | Sort by position/ID |
| Extractor leaks invalid resource | Returning ResultSet outside callback | Map to DTOs before callback returns |
| High memory usage | Collecting huge dataset in memory | Filter, paginate root, or batch process |
| Last page missing items | LIMIT/OFFSET applied to JOIN rows | Paginate parent IDs first, then JOIN children |
| Order count inflated | COUNT on one-to-many JOIN | COUNT(DISTINCT parent.id) or EXISTS |
| Read DTO missing columns | SQL omits columns required by mapper | Explicitly select and alias all needed columns |
| SQL breaks across databases | Dialect-dependent query | Use RDBMS-appropriate syntax and integration tests |
| Using ResultSetExtractor to update aggregates | Confusing read mapping with aggregate persistence | Use repository/aggregate operations for writes |

## 16. Practice Exercises

Suppose an order has multiple product lines and the application wants to return an `OrderDetails` containing a list of `OrderItemView`.

**Exercise 1.** When using `RowMapper` on a JOIN query, how many objects does one SQL row normally produce?

*Answer:* One object per row. If an order has three items, the JOIN query produces three separate row objects.

**Exercise 2.** How does `ResultSetExtractor<T>` differ from `RowMapper<T>`?

*Answer:* `RowMapper` processes each row and returns one object for that row; `ResultSetExtractor` receives the entire ResultSet and builds a single combined result `T`.

**Exercise 3.** Why use `LEFT JOIN` when reading an order that may have no items yet?

*Answer:* So the order still appears. Child table columns are NULL; the extractor checks the child primary key and returns an empty list.

**Exercise 4.** Why is a Map keyed by parent ID needed?

*Answer:* To recognize consecutive rows belonging to the same order and create only one parent accumulator/object per ID.

**Exercise 5.** What can joining two independent child tables do to the item list?

*Answer:* Produce intermediate rows repeating items for each row of the other child table. Use a deduplicating map by ID or pre-aggregate child tables before joining.

**Exercise 6.** Why not apply LIMIT directly to JOIN rows when requesting 20 orders?

*Answer:* One order can span multiple rows. LIMIT 20 limits JOIN rows, not 20 orders. Paginate order IDs first.

**Exercise 7.** Should a ResultSet be returned from an extractor to a controller?

*Answer:* No. A ResultSet depends on a statement/connection and is valid only within the JDBC resource scope. Map into DTOs before the callback completes.

## 17. Key Takeaways

- **`ResultSetExtractor<T>`** receives the entire ResultSet and returns an application-defined result.
- Use it when multiple SQL rows must be grouped into a parent DTO with child collections or an aggregated structure.
- **`RowMapper`** fits when each row is an independent object; **`RowCallbackHandler`** fits row-by-row processing via side effects.
- Use a Map keyed by parent ID to instantiate only one parent object per group of rows.
- With `LEFT JOIN`, check the child primary key so fake child objects are never built from SQL NULLs.
- When joining multiple child tables, deduplicate by ID or pre-aggregate each table before joining to avoid row multiplication.
- SQL needs an explicit ORDER BY when collection order matters.
- Paginate by the parent root before joining children when pages must contain complete parent objects.
- ResultSetExtractor is a Spring JDBC read mechanism; it does not replace Spring Data JDBC's aggregate lifecycle or write APIs.
- Never retain ResultSet/Statement/Connection after the callback finishes; map data into Java objects within template resource management.

### References

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): using JdbcTemplate, NamedParameterJdbcTemplate, and mapping callbacks.
- [Spring Framework — ResultSetExtractor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html): callback contract for processing the entire ResultSet.
- [Spring Framework — RowMapper API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/RowMapper.html): mapping each row to an object.
- [Spring Framework — RowCallbackHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html): processing rows without returning objects from the callback.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories, aggregate mapping, and Spring Data JDBC infrastructure.

When implementing, choose the callback matching the result shape you need. If SQL returns multiple rows for one parent object, group by parent key and check child keys; if you only need independent rows, RowMapper is simpler.
