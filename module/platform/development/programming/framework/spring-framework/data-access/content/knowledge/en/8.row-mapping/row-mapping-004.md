# ResultSetExtractor Processes the Entire Result Set

## 1. The Problem: One SQL Row Is Not Always One Result Object

In Spring Framework, `JdbcTemplate` helps applications execute SQL over JDBC without repeating every step of creating a `Statement`, iterating results, closing resources, and translating exceptions. When mapping results, the common approach is `RowMapper<T>`: each row of the `ResultSet` becomes one `T` object.

However, many requirements need **to see all rows together**:

- Collapsing multiple rows from a `JOIN` into a single parent object with a list of children.
- Building a lookup `Map`, a tree structure, a grouped list, or a statistics object.
- Scanning the result set to decide an overall state based on multiple rows.
- Checking consistency conditions across rows, or combining related values.
- Processing sequentially without having to return a `List` containing one element per row.

That is the role of **`ResultSetExtractor<T>`**, the callback that `JdbcTemplate` invokes to turn **the entire `ResultSet` of a query** into **an arbitrary Java result `T`**.

For example, with a `LEFT JOIN`, three customers and three orders can produce **four SQL rows**, whereas the desired result is **three customer objects**, each with its own list of orders. A `RowMapper<Customer>` applied independently per row does not automatically merge rows sharing the same parent key. `ResultSetExtractor` lets you maintain a shared structure throughout iteration and finish with the grouped result.

**Core idea:** `RowMapper` asks “what object does this row become?”, whereas `ResultSetExtractor` asks “what single result does this entire set of rows become?”.

## 2. API Contract and Execution Flow

The interface belongs to `org.springframework.jdbc.core`:

```java
@FunctionalInterface
public interface ResultSetExtractor<T> {
    T extractData(ResultSet rs) throws SQLException, DataAccessException;
}
```

This is a simplified signature for learning: actual source code may include nullability annotations, generic bounds, and Javadoc depending on the Spring version. `SQLException` and `ResultSet` belong to `java.sql`, and `DataAccessException` belongs to `org.springframework.dao`.

- **`T`:** the overall result type to return, such as `List<CustomerView>`, `Map<Long, CustomerView>`, `Summary`, `Integer`, or `Optional<T>`.
- **`rs`:** the result of the executing query, owned by `JdbcTemplate`; when the callback starts, the cursor is normally **before the first row** for a standard forward-only `ResultSet`.
- **`extractData`:** calls `rs.next()` itself to move the cursor, reads columns, and returns the final value. The callback may return `null` per the contract, though you should pick a consistent convention, such as an empty list when there are no rows.
- **Exceptions:** JDBC operations may throw `SQLException`; `JdbcTemplate` handles and translates it into a `DataAccessException` when appropriate. There is no need to catch `SQLException` just to return an empty list.
- **Resources:** the callback **must not close the `ResultSet` provided by `JdbcTemplate`** and must not close the template's `Connection`. The template manages the lifecycle of query resources.

Conceptual flow:

```text
repository calls jdbcTemplate.query(sql, extractor, args...)
                        |
                        v
             acquire appropriate Connection
                        |
                        v
             create PreparedStatement
                        |
                        v
                 bind parameters
                        |
                        v
                 executeQuery()
                        |
                        v
              extractor.extractData(rs)
                        |
                        +--> rs.next() -> read row 1
                        +--> rs.next() -> read row 2
                        +--> ...
                        +--> return single result T
                        |
                        v
         JdbcTemplate closes ResultSet/Statement
         and releases Connection per context
                        |
                        v
                 caller receives T
```

Normally, **one `query` invocation corresponds to one `extractData` call** on that query's `ResultSet`; the callback iterates over 0, 1, or many rows itself. This is not a per-row callback. If the query returns no rows, `extractData` still receives the empty `ResultSet` and can return an empty list.

## 3. Comparing RowMapper, RowCallbackHandler, and ResultSetExtractor

| Criterion | `RowMapper<T>` | `RowCallbackHandler` | `ResultSetExtractor<T>` |
| --- | --- | --- | --- |
| Method | `mapRow(rs, rowNum)` | `processRow(rs)` | `extractData(rs)` |
| One callback handles | **One row** | **One row** | **Entire result set** |
| Who calls `rs.next()`? | `JdbcTemplate` | `JdbcTemplate` | **The extractor itself** |
| Callback returns | One `T` for that row | `void` | One `T` for the entire set |
| Typical use | `List<T>`, simple DTO/record | Per-row action/collection | Parent–child grouping, `Map`, tree, custom stats |
| When empty | `query(...mapper)` returns empty `List` | Handler is not called for any row | Extractor decides what to return |
| Holding state | Usually stateless | May use call-scoped state | Should create state inside `extractData` |

**Important cursor rule:** do not call `rs.next()` inside `RowMapper` or `RowCallbackHandler` because Spring has already positioned the cursor on the current row. Conversely, **you must call `rs.next()` yourself inside `ResultSetExtractor`** to read data rows.

`JdbcTemplate` includes `RowMapperResultSetExtractor<T>`, an adapter that uses a `RowMapper<T>` to collect results into a `List<T>`. This shows mechanically that `ResultSetExtractor` can build a list, but if the problem is truly “one row into one object”, **`RowMapper` remains the shorter and clearer choice**.

Do not assume `ResultSetExtractor` is an “always-better upgrade over RowMapper”. Its power comes with responsibility for controlling iteration, temporary state, deduplication, and return conventions.

## 4. Sample Data: JOIN Multiplies Row Count

Consider a customer and order system. A customer may not have any orders yet.

Example SQL schema using H2/PostgreSQL with `BOOLEAN` and `DECIMAL` types:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE customer_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, name, active) VALUES
    (1, 'Lan',  TRUE),
    (2, 'Minh', TRUE),
    (3, 'Vy',   TRUE);

INSERT INTO customer_order (id, customer_id, amount) VALUES
    (101, 1, 120.00),
    (102, 1,  80.00),
    (103, 2,  50.00);
```

Query:

```sql
SELECT
    c.id     AS customer_id,
    c.name   AS customer_name,
    o.id     AS order_id,
    o.amount AS order_amount
FROM customer c
LEFT JOIN customer_order o ON o.customer_id = c.id
WHERE c.active = ?
ORDER BY c.id, o.id;
```

When binding `true` to the `?` parameter, the returned rows are:

| customer_id | customer_name | order_id | order_amount |
| ---: | --- | ---: | ---: |
| 1 | Lan | 101 | 120.00 |
| 1 | Lan | 102 | 80.00 |
| 2 | Minh | 103 | 50.00 |
| 3 | Vy | `NULL` | `NULL` |

There are **4 SQL result rows**, because customer Lan has **2 orders**. Customer Vy still has one row due to `LEFT JOIN`, with `NULL` in the order columns.

However, the mapping goal is:

```text
[
  CustomerView(id=1, name=Lan,  orders=[101, 102]),
  CustomerView(id=2, name=Minh, orders=[103]),
  CustomerView(id=3, name=Vy,   orders=[])
]
```

**Do not confuse “multiple SQL rows with the same customer_id” with duplicate customer records stored in the DB.** That is the nature of a 1–N relationship when represented as a flat table.

## 5. Whole-Set Processing Mindset: From Flat Rows to Parent–Child Groups

A straightforward algorithm:

1. Initialize a `LinkedHashMap<Long, MutableCustomer>`: key is the customer ID, value is a temporary accumulator.
2. `while (rs.next())`: read the customer key of the current row.
3. If the key is not yet in the map, create a new customer accumulator; if already present, reuse it.
4. Read `order_id`. If it is not SQL `NULL`, add the order to that accumulator's list.
5. After finishing the result set, convert the accumulators into the return objects, using `List.copyOf(...)` so internal mutable lists are not exposed.

Pseudo-code:

```text
byCustomer = ordered map
while ResultSet.next():
    customerId = get customer_id
    bucket = byCustomer.get(customerId)
    if bucket is absent:
        bucket = new bucket(customerId, customerName)
        byCustomer.put(customerId, bucket)

    orderId = get order_id
    if orderId is NOT SQL NULL:
        bucket.orders.add(orderId, orderAmount)

result = []
for bucket in byCustomer.values():
    result.add(immutable snapshot of bucket)
return result
```

`LinkedHashMap` preserves the **insertion order** of keys during iteration. The `ORDER BY c.id, o.id` clause in SQL makes that appearance order **predictable**: customers by ID, orders by ID. Do not rely on the database's natural order when SQL has no `ORDER BY`.

The output size will be three customers, not four SQL rows. If no matching customers exist, the map is empty and the result is `List.of()` / an empty list, not a “fake empty” object representing a nonexistent customer.

## 6. Complete Spring JDBC Example: A ResultSetExtractor Building a Parent–Child List

The class below is intended for **a Spring application that already has `JdbcTemplate`/`DataSource` configured and the schema from Section 4 created**. This is Spring integration code; it is not a standalone program compiled with only the JDK.

File `CustomerOrderRepository.java`:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerOrderRepository {
    private static final String SQL = """
        SELECT
            c.id     AS customer_id,
            c.name   AS customer_name,
            o.id     AS order_id,
            o.amount AS order_amount
        FROM customer c
        LEFT JOIN customer_order o ON o.customer_id = c.id
        WHERE c.active = ?
        ORDER BY c.id, o.id
        """;

    private final JdbcTemplate jdbc;

    public CustomerOrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderView(long id, BigDecimal amount) {}

    public record CustomerView(
        long id, String name, List<OrderView> orders
    ) {}

    private static final class MutableCustomer {
        final long id;
        final String name;
        final List<OrderView> orders = new ArrayList<>();

        MutableCustomer(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    public List<CustomerView> findActiveWithOrders() {
        ResultSetExtractor<List<CustomerView>> extractor = rs -> {
            Map<Long, MutableCustomer> byId = new LinkedHashMap<>();

            // With ResultSetExtractor, the callback ITSELF advances the cursor.
            while (rs.next()) {
                long customerId = rs.getLong("customer_id");

                MutableCustomer customer = byId.get(customerId);
                if (customer == null) {
                    customer = new MutableCustomer(
                        customerId,
                        rs.getString("customer_name")
                    );
                    byId.put(customerId, customer);
                }

                // LEFT JOIN: order_id may be SQL NULL.
                long orderId = rs.getLong("order_id");
                boolean orderExists = !rs.wasNull();
                if (orderExists) {
                    customer.orders.add(new OrderView(
                        orderId,
                        rs.getBigDecimal("order_amount")
                    ));
                }
            }

            // Do not expose the accumulator's mutable list externally.
            List<CustomerView> result = new ArrayList<>();
            for (MutableCustomer customer : byId.values()) {
                result.add(new CustomerView(
                    customer.id,
                    customer.name,
                    List.copyOf(customer.orders)
                ));
            }
            return result;
        };

        PreparedStatementSetter activeOnly =
            ps -> ps.setBoolean(1, true);

        return jdbc.query(SQL, activeOnly, extractor);
    }
}
```

### Analyzing Each Error-Prone Point

**a. Why is `while (rs.next())` needed?**  
Because `extractData` receives the entire set and iterates itself. Calling `rs.getLong(...)` while the cursor is still before the first row can cause JDBC to throw a `SQLException` because there is no current row yet.

**b. Why use `Map<Long, MutableCustomer>`?**  
The same `customer_id=1` appears in two rows. The map ensures the same accumulator receives both order 101 and order 102; creating a new customer each time would produce two Lan objects.

**c. Why call `wasNull()` immediately after `getLong("order_id")`?**  
`ResultSet.getLong` returns `0` when the SQL value is `NULL` and requires calling `wasNull()` to distinguish. Using `orderId != 0` to infer `NULL` is wrong in general because ID 0 can be valid in some schemas. You must check `wasNull()` **before calling another getter** that would overwrite the “whether the last read column was NULL” flag.

**d. Why not close `rs` or `Connection`?**  
`JdbcTemplate` owns them. After the callback returns or throws an exception, the template releases resources according to the transaction context. Calling `rs.close()` or `connection.close()` inside the extractor can break the JDBC flow and transaction boundaries.

**e. What if the DB returns no rows?**  
The loop does not execute; the map is empty and the result is an empty `List<CustomerView>`. This is a clearer convention and easier to work with than returning `null` for the no-data case.

**f. Result with sample data?**  
Three objects: Lan has orders 101, 102; Minh has order 103; Vy has an empty order list. Monetary amounts are read as `BigDecimal` to preserve the decimal semantics of the `DECIMAL` column.

**g. Can the callback be safely reused across requests?**  
In the example above, all accumulator maps and lists are created **inside `extractData`**, so no state from an old request is retained in the singleton repository. A stateless extractor can be reused; do not keep a shared mutable `Map` as a field of a singleton bean without explicit requirements and synchronization.

## 7. Concise Variant: Passing the Extractor Directly to JdbcTemplate

If the logic is short, you can pass an explicitly typed lambda:

```java
ResultSetExtractor<List<String>> extractor = rs -> {
    List<String> names = new ArrayList<>();
    while (rs.next()) {
        names.add(rs.getString("customer_name"));
    }
    return names;
};

List<String> names = jdbcTemplate.query(
    """
    SELECT name AS customer_name
    FROM customer
    WHERE active = ?
    ORDER BY id
    """,
    (PreparedStatementSetter) ps -> ps.setBoolean(1, true),
    extractor
);
```

This snippet illustrates the API and requires appropriate imports (`ArrayList`, `List`, `ResultSetExtractor`, `PreparedStatementSetter`). However, for the simple requirement above, **using `RowMapper` is even clearer**:

```java
List<String> names = jdbcTemplate.query(
    "SELECT name FROM customer WHERE active = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("name"),
    true
);
```

Both produce `["Lan", "Minh", "Vy"]` on the sample data. Choose `ResultSetExtractor` when the problem genuinely needs **state across multiple rows**, not just because the API can do everything.

Key overloads of `JdbcTemplate` include:

```java
<T> T query(String sql, ResultSetExtractor<T> extractor);
<T> T query(String sql, ResultSetExtractor<T> extractor,
            Object... args);
<T> T query(String sql, PreparedStatementSetter setter,
            ResultSetExtractor<T> extractor);
<T> T query(PreparedStatementCreator creator,
            ResultSetExtractor<T> extractor);
```

These are simplified signatures for comparison, not declarations to copy directly into application code. For SQL containing `?`, provide arguments via the corresponding overload. In some contexts, **explicitly typing the extractor variable** helps Java pick the right overload and avoid lambda ambiguity.

## 8. What Can ResultSetExtractor Return?

Since `T` is **the result of the whole set**, the return structure depends on the requirement:

| Type `T` | Usage example | Watch out for |
| --- | --- | --- |
| `List<CustomerView>` | Grouping parent–child by primary key | Avoid creating duplicate parents and distinguish `NULL` children |
| `Map<Long, CustomerView>` | Looking up objects by ID | Choose how to handle duplicate keys and map ordering |
| `Map<String, List<Item>>` | Grouping by status/label | Normalize keys if needed; avoid global state |
| `Summary` (record) | Computing multiple aggregate metrics at once | Avoid double-counting caused by SQL `JOIN` row multiplication |
| `Optional<Account>` | Returning 0 or 1 result per application contract | Decide how to handle SQL returning multiple rows |
| `Integer` / `Long` | Counter or whole-set condition | If only `COUNT(*)` is needed, letting the DB aggregate is usually better |
| `null` | Special result per contract | Forces callers to handle null; prefer an explicit return type |

`ResultSetExtractor` **does not force the callback to return a list**, does not force iterating every row if the goal is already satisfied, and does not force treating each row as a separate object. However, if a “whole-set” result is required, you must deliberately iterate all relevant rows; returning early can skip necessary data and fail the requirement.

### Example Returning a Status-Count Map

With the `customer` table, to map rows into a counter map (illustrative code inside a Spring application):

```java
ResultSetExtractor<Map<String, Integer>> extractor = rs -> {
    Map<String, Integer> counts = new LinkedHashMap<>();
    while (rs.next()) {
        String status = rs.getBoolean("active")
            ? "ACTIVE" : "INACTIVE";
        counts.merge(status, 1, Integer::sum);
    }
    return counts;
};

Map<String, Integer> counts = jdbcTemplate.query(
    "SELECT active FROM customer ORDER BY id",
    extractor
);
```

In the sample data all three customers are active, so the map is `{ACTIVE=3}`. However, when you only need counts by status, **`SELECT active, COUNT(*) ... GROUP BY active`** is usually more optimal: the DB can aggregate before sending data over the network. The Java example illustrates callback capability, not a recommendation to always process aggregations client-side.

## 9. SQL NULL: An Extremely Common Bug with Outer JOINs

A `LEFT JOIN` preserves parents without children while populating the right-hand columns with SQL `NULL`. If you read:

```java
long orderId = rs.getLong("order_id");
```

then `orderId` will be `0` when SQL `NULL`. To distinguish:

```java
long orderId = rs.getLong("order_id");
if (!rs.wasNull()) {
    // A real order record exists.
}
```

Or if the JDBC driver supports typed conversion via Java class:

```java
Long orderId = rs.getObject("order_id", Long.class);
if (orderId != null) {
    // An order exists.
}
```

The second approach is convenient, though driver support for typed conversion varies; when high compatibility is needed, test the driver and specific `NULL` cases. For the parent primary key, `customer_id` is `NOT NULL` per the sample DDL, so reading directly with `getLong` is reasonable.

Do not write `if (rs.getString("customer_name") == null)` to check for no order: that column belongs to the **parent table**, not an indicator of whether a child record exists. Check a **NOT NULL** key or identifying column of the child table.

If there are multiple consecutive `LEFT JOIN` tables, each nullable column group needs its own identity check. Do not reuse `wasNull()` after calling other getters, because it reflects **only the most recent getter**.

## 10. Choosing the Right Grouping Key Preserves Data Integrity

**Group by ID, not by display name.** Two different customers can share the name “Lan”; one customer may change their name while their primary key remains stable. The map key should be `customer_id` or a composite key accurately representing the entity.

Suppose the data is:

```text
customer_id | customer_name
------------+--------------
1           | Lan
4           | Lan
```

Using `Map<String, Customer>` keyed by name would mistakenly merge two people. Using `Map<Long, Customer>` keyed by `customer_id` preserves both customers.

**Also do not confuse multiple rows with duplicates to be deleted.** Two rows:

```text
customer=1, order=101
customer=1, order=102
```

are two valid orders for the same customer. Calling `DISTINCT customer_id, customer_name` too broadly would discard order information. Conversely, if you also join `order_item`, one order can repeat across multiple line items; when grouping orders, store them in a map keyed by **`order_id`** to avoid duplicating orders.

When you need a three-level tree `Customer → Order → Item`, you typically need:

- A map of customers by `customer_id`.
- Inside each customer, a map of orders by `order_id`.
- Inside each order, a list or map of items by the appropriate item key.
- Only create a new node when its corresponding key first appears.
- Check `NULL` at each `LEFT JOIN` level.
- Convert mutable accumulators into final DTOs after iteration.

Do not just use a `List<Order>` and add an `Order` on **every SQL row** when an order has multiple items, as that duplicates orders.

## 11. Row Ordering, Duplicate Data, and Grouping Correctness

The SQL `ORDER BY c.id, o.id` in the example makes the result order stable by keys. `LinkedHashMap` preserves the order in which keys are **first encountered**, yet `LinkedHashMap` itself **does not make the DB return rows in order**. If the application requires deterministic ordering, always instruct the DB to sort by enough keys to break ties.

For logic that only needs grouping by key, `HashMap` can still be correct in content, though iteration order when returning results will not be guaranteed. `LinkedHashMap` combined with `ORDER BY` makes learning and test outputs deterministically verifiable.

If results may contain duplicate child rows due to joining multiple tables or data sources, do not blindly use a `Set` to deduplicate “for neatness”. First clarify the business rule: do two rows with the same `order_id` truly represent the same entity? If yes, you can use `LinkedHashMap<Long, OrderAccumulator>`. If not, keep every child record. Deduplicating by all columns or by display name can mask join bugs and drop data.

## 12. Whole Set Does Not Mean Loading Everything into RAM

Suppose a query returns one million rows:

- If the extractor puts every row into an `ArrayList`, Java memory grows with the row count.
- If the extractor builds a customer map and order lists, memory grows with the number of entities/relationships retained in the result.
- If the extractor only increments a counter without retaining rows, Java memory used for the result may be small, **but the JDBC driver may still buffer rows** depending on the DB, driver, fetch size, and transaction.
- Holding a connection open for a long time while calling external network APIs, sleeping, or doing heavy work can starve the connection pool.

Consider the complexity of the sample grouping algorithm: for `R` returned rows, iteration is typically **O(R)** expected when map lookup averages O(1). Memory for the returned structure is roughly **O(P + O)** for `P` customers and `O` retained orders, excluding JDBC-side buffers and Java object overhead.

If you only need aggregation:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM customer_order
GROUP BY customer_id;
```

it is usually better to let the DB do the aggregation. If you only need the first ten customers, do not query the entire set and call `subList(0, 10)`: paginate in the DB and consider paginating by **parent keys**, because `LIMIT 10` on a `JOIN` result can cut right through the tenth customer's order list.

For large datasets, consider splitting into a paginated parent query and a child query by the set of parent IDs, or using appropriate streaming/fetch size/transactions. `ResultSetExtractor` allows sequential processing but **does not automatically guarantee network streaming or constant RAM**.

## 13. Interaction with Transactions and Spring Resource Management

`JdbcTemplate` acquires connections through Spring's resource infrastructure and participates in the existing transaction when configured properly. When using:

```java
@Transactional(readOnly = true)
public List<CustomerOrderRepository.CustomerView> load() {
    return repository.findActiveWithOrders();
}
```

this illustrative code is only valid when the method belongs to a Spring-managed service, the annotation is actually applied by Spring AOP/transaction infrastructure, and the repository is injected. `readOnly=true` is a read-only hint that can enable optimizations across layers, **not a universal hard lock against all writes** across all DBs/drivers. A single query fetching parent–child data allows mapping from one consistent result set per statement semantics; it does not mean every system always provides a fixed “snapshot” across multiple consecutive SQL statements under different isolation levels.

What not to do:

```java
ResultSetExtractor<List<String>> wrong = rs -> {
    // Wrong: ResultSet is owned by JdbcTemplate.
    rs.close();
    return List.of();
};
```

If an extractor opens its own file, socket, or stream during processing, it must close the resources **it opened itself**. However, the `ResultSet` and statement supplied by the template must be left for the template to finish and clean up.

Avoid “running another query on the same JdbcTemplate inside each row” to fetch children: that is the N+1 query problem, which can generate hundreds of DB round-trips. Query the right dataset and group by key, or use an appropriate batch-query strategy.

### Exceptions in the Callback

`extractData` is permitted to throw `SQLException` when reading columns or moving the cursor. Spring translates many SQL errors into `DataAccessException`; runtime errors thrown by application logic normally continue propagating to the caller. Do not do this:

```java
ResultSetExtractor<List<String>> unsafe = rs -> {
    try {
        // read data
        return List.of();
    } catch (SQLException ex) {
        return List.of(); // Wrong: hides DB errors as "no data".
    }
};
```

This snippet only illustrates an anti-pattern and has no actual read operations in the comment. A DB error is completely different from a query returning 0 rows. In real applications, let exceptions propagate out of the callback so the framework can clean up resources and the caller can safely handle error responses/rollbacks/retries.

## 14. Practical Scenarios: Choose ResultSetExtractor or Not?

### Scenario A: Querying a single table, one DTO per row

```java
List<String> names = jdbcTemplate.query(
    "SELECT name FROM customer ORDER BY id",
    (rs, rowNum) -> rs.getString("name")
);
```

**Choose `RowMapper`**, because each row is one name; `ResultSetExtractor` only makes the code longer.

### Scenario B: Parent–child JOIN returning multiple rows per parent

```text
Lan - 101
Lan - 102
Minh - 103
Vy - NULL
```

**Choose `ResultSetExtractor`** if you need exactly one object per customer containing their list of orders. Group by `customer_id` and check `NULL` for `order_id`.

### Scenario C: Only needing COUNT/SUM statistics

**Prefer SQL aggregation and `queryForObject`** when the DB can return a scalar:

```java
Long count = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer_order",
    Long.class
);
```

With the sample schema, `count` is `3`. There is no need to pull every row and use an extractor to increment a `count` variable. If you need a custom aggregate structure across multiple rows/fields that SQL cannot express conveniently, an extractor is an option.

### Scenario D: Only processing each row without returning a structure

`RowCallbackHandler` has `processRow(ResultSet rs)` suited for per-row side effects/processing. Spring calls `rs.next()` before each invocation; the handler does not return an overall `T`. If you need to return a `Map` or data tree, an extractor usually expresses the intent more clearly.

### Scenario E: Returning one object when SQL has at most one row

`queryForObject(sql, rowMapper, args...)` already has an **exact-one-row** contract and throws an exception if the row count is not 1. If the business requirement is “0 or 1” with `Optional<T>`, you can use `query` and inspect the list, or an extractor that explicitly checks for a second row; the key is not silently ignoring extra rows.

### Scenario F: Loading a large tree with multiple child tables

An extractor can build multi-level maps, but watch out for **fan-out**: joining a parent with two independent 1–N child tables can multiply row counts (e.g., 3 orders × 4 addresses = 12 rows). When the Cartesian product grows large, splitting queries by key batches and assembling in Java can be more efficient and less prone to data duplication. Do not assume one giant JOIN query is always optimal.

## 15. Empty Data, Row Count Checks, and Return Conventions

The `while (rs.next())` condition handles an empty `ResultSet` naturally:

```java
ResultSetExtractor<List<Long>> extractor = rs -> {
    List<Long> ids = new ArrayList<>();
    while (rs.next()) {
        ids.add(rs.getLong("customer_id"));
    }
    return ids;
};
```

If there are no rows, it returns `[]`. `extractData` is not restricted to returning lists; you can return a record with zero totals or an empty `Map` per the application contract.

When the requirement says “SQL must return exactly one group”, write explicit checks:

- Zero rows: empty list, `Optional.empty()`, or exception? Depends on business rules.
- One row: process normally.
- Unexpected multiple rows: should an error be raised? Do not just take the first row and stay silent.
- Multiple SQL rows for **the same parent entity**: do not automatically treat as multiple entities; distinguish SQL grain from output object grain.

`ResultSetExtractor` lets you define the rules, though getting them right depends on the author's code. A query with `ORDER BY` and clear grouping keys makes testing easier.

## 16. Standalone Java 17: Simulating the Whole-Set Folding Step

To understand the algorithm without downloading Spring or opening a DB, the example below uses **plain JDK 17**. It simulates four rows after a `LEFT JOIN` with a `List<JoinedRow>`, then iterates **the entire list** to group by customer key. The records and `fold` method are for learning, **not a real `ResultSetExtractor`**; in a JDBC application, the `for` loop corresponds to `while (rs.next())`.

Create file `ExtractorFoldDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ExtractorFoldDemo {
    record JoinedRow(long customerId, String customerName, Long orderId) {}
    record CustomerSummary(long id, String name, List<Long> orderIds) {}

    private static final class Bucket {
        final long id;
        final String name;
        final List<Long> orderIds = new ArrayList<>();

        Bucket(long id, String name) {
            this.id = id;
            this.name = name;
        }

        CustomerSummary snapshot() {
            return new CustomerSummary(id, name, List.copyOf(orderIds));
        }
    }

    static List<CustomerSummary> fold(List<JoinedRow> rows) {
        Map<Long, Bucket> byId = new LinkedHashMap<>();
        for (JoinedRow row : rows) {
            Bucket bucket = byId.get(row.customerId());
            if (bucket == null) {
                bucket = new Bucket(row.customerId(), row.customerName());
                byId.put(row.customerId(), bucket);
            }
            if (row.orderId() != null) {
                bucket.orderIds.add(row.orderId());
            }
        }

        List<CustomerSummary> result = new ArrayList<>();
        for (Bucket bucket : byId.values()) {
            result.add(bucket.snapshot());
        }
        return result;
    }

    public static void main(String[] args) {
        List<JoinedRow> rows = List.of(
            new JoinedRow(1, "Lan", 101L),
            new JoinedRow(1, "Lan", 102L),
            new JoinedRow(2, "Minh", 103L),
            new JoinedRow(3, "Vy", null)
        );

        List<CustomerSummary> customers = fold(rows);
        System.out.println("raw rows=" + rows.size());
        for (CustomerSummary customer : customers) {
            System.out.println(customer.name() + " -> " + customer.orderIds());
        }
        System.out.println("customers=" + customers.size());
    }
}
```

Run with JDK 17 or higher:

```bash
javac --release 17 ExtractorFoldDemo.java
java ExtractorFoldDemo
```

Exact output:

```text
raw rows=4
Lan -> [101, 102]
Minh -> [103]
Vy -> []
customers=3
```

**Explanation:** `rows.size()` is still 4 because that is the number of **JOIN rows**. `customers.size()` is 3 because Lan's two rows are grouped into one customer. For Vy, `orderId == null` is skipped, keeping `orderIds=[]` rather than creating an “order with null ID”.

The example also highlights a common pitfall: `List.of(null)` is disallowed in Java, so `NULL` data is represented via a nullable `orderId` field inside a non-null `JoinedRow`; do not try to build a list with null elements using `List.of(...)`.

## 17. How to Test ResultSetExtractor?

Test the **result contract**, not merely that the SQL runs:

| Case | Input data | Expected result |
| --- | --- | --- |
| No rows | Empty `ResultSet` | Empty list/map, not `null` if that convention was chosen |
| One parent, one child | 1 row | One parent with one child |
| One parent, many children | 2+ rows with same parent key | One parent containing all valid children |
| Parent with no children | `LEFT JOIN` row with `order_id=NULL` | Parent with empty children list |
| Two parents with same name | Two distinct primary keys | Two separate parent objects |
| Two child tables JOINed together | Child repeated due to fan-out | No duplicate children when identifying key matches |
| Multiple rows in different orders | DB returns sorted by keys | Result preserves expected order |
| SQL/driver error | `SQLException` during iteration | Exception is not swallowed or turned into empty data |

There are two testing layers:

1. **Unit test the grouping algorithm:** pass a flat list of rows (like `ExtractorFoldDemo`) and verify the output by key, `NULL`, and ordering. To test the callback itself, you can supply a mocked `ResultSet` with a suitable mocking library; avoid building mocks that are overly complex relative to their value.
2. **Integration test against a real DB or compatible test DB:** create the schema, insert data, call the repository, and verify the exact `List<CustomerView>`. This test is valuable for catching wrong column aliases, data types, SQL syntax, how the driver handles `NULL`, and cross-database differences.

When testing error cases, do not accept `catch(SQLException) { return List.of(); }` as “success” because it corrupts business results. Also consider tracking query counts to catch N+1 if a callback accidentally triggers extra DB calls per row.

## 18. Common Mistakes and How to Avoid Them

**Mistake 1: Forgetting `rs.next()`.**  
Calling `getLong` when the cursor is not yet on a valid row. Fix: use `while (rs.next())` or `if (rs.next())` inside the extractor.

**Mistake 2: Using `RowMapper` but calling `rs.next()` yourself.**  
With `RowMapper` and `RowCallbackHandler`, Spring already moves the cursor. Do not carry habits across callbacks while forgetting their different contracts.

**Mistake 3: Creating one parent per JOIN row.**  
A 1–N join produces multiple rows for the same key. Fix: map parents by ID and instantiate only on first encounter.

**Mistake 4: Reading a nullable child key with `getLong()` and checking `!= 0`.**  
Cannot distinguish SQL `NULL` from 0. Fix: `wasNull()` right after the getter, or a driver-compatible nullable wrapper getter.

**Mistake 5: Grouping by name instead of primary key.**  
Two people with the same name get merged into one. Fix: use the identifying key at the right grain.

**Mistake 6: Adding duplicate orders when joining an extra child table.**  
An `Order` with multiple `OrderItem`s can appear multiple times. Fix: group each level by its own key or change the querying strategy.

**Mistake 7: Assuming `LinkedHashMap` creates SQL order.**  
The map only remembers insertion order. Fix: explicit `ORDER BY` and test the order.

**Mistake 8: Calling `rs.close()` inside the extractor.**  
Violates `JdbcTemplate`'s ownership. Fix: let the template clean up resources; only close resources you opened yourself.

**Mistake 9: Catching every `SQLException` and returning an empty list.**  
Masks DB failures as empty results. Fix: let exceptions be translated by Spring and handled by the caller.

**Mistake 10: Keeping a mutable map/list as a singleton field.**  
Can mix results across concurrent requests. Fix: create state inside `extractData`; if reusing an extractor, keep it stateless.

**Mistake 11: Querying too broadly and discarding most results.**  
Pulling an entire table from the DB into Java wastes I/O, CPU, and RAM. Fix: filter, aggregate, and paginate appropriately in the DB.

**Mistake 12: Putting `LIMIT` directly on a JOIN to paginate parents.**  
Can cut a parent's child list in half. Fix: paginate parent IDs first, then fetch all children for the selected parents.

**Mistake 13: Assuming an extractor automatically streams with constant RAM.**  
The driver may buffer many rows, and maps still hold returned objects. Fix: measure with the real DB, configure appropriate fetch size/transactions, and bound dataset sizes.

**Mistake 14: Issuing extra queries inside each `rs.next()` step.**  
Causes N+1 queries, holds connections too long, and makes consistency hard to manage. Fix: design an aggregate query or batch-query the children.

## 19. Self-Check Exercises

**Question 1.** Does `ResultSetExtractor<T>` process one row or the entire result set? Who calls `rs.next()`?

**Answer:** It processes the entire `ResultSet`; the extractor calls `rs.next()` **itself**. `JdbcTemplate` does not iterate rows for an extractor the way it does for `RowMapper`.

**Question 2.** SQL returns four rows: Lan–101, Lan–102, Minh–103, Vy–NULL. After grouping by customer key, how many parents and how many orders are there?

**Answer:** 3 parents and 3 orders. Vy has an empty order list.

**Question 3.** Why is `rs.getLong("order_id") == 0` not sufficient to tell that no child exists?

**Answer:** JDBC returns 0 for SQL `NULL` when using primitive getters; you must check `rs.wasNull()`. A key with value 0 can also be valid data depending on the schema.

**Question 4.** If you want `List<Account>`, exactly one Account per row, what should you use?

**Answer:** Usually `RowMapper<Account>` with `JdbcTemplate.query(...)`, since the template already performs the loop.

**Question 5.** What if you want `Map<Long, CustomerView>` grouped by ID combining multiple JOIN rows?

**Answer:** `ResultSetExtractor<Map<Long, CustomerView>>` is appropriate; use a keyed map, iterate the whole set, and build the desired structure.

**Question 6.** Does the callback need to close the `ResultSet` passed in by the template?

**Answer:** No. `JdbcTemplate` owns and closes it. The callback only closes secondary resources it opened itself.

**Question 7.** There are three orders, each with two items. A customer–order–item JOIN returns six rows. What happens if you append an `Order` to a list on every row?

**Answer:** Each order would be duplicated twice. You need to group by `order_id` before adding items, or split the fetching strategy.

**Question 8.** If you only need `COUNT(*)` of orders, should you iterate all rows with an extractor?

**Answer:** Usually no. Letting the DB aggregate and calling `queryForObject(..., Long.class)` is simpler and transfers less data.

**Question 9.** With the extractor in Section 6, what happens if the query returns no customers?

**Answer:** The `while` loop does not run; `byId` is empty and the method returns an empty list, without creating any fake customers.

**Question 10.** Why is `ORDER BY` needed in the example using `LinkedHashMap`?

**Answer:** `LinkedHashMap` only preserves the encounter order in the `ResultSet`. Without DB sorting, encounter order is not guaranteed; adding `ORDER BY` ensures predictable output ordering.

## 20. Summary

- **`ResultSetExtractor<T>` = one callback, one result `T` for the entire `ResultSet`.**
- Unlike `RowMapper`, **the extractor calls `rs.next()` itself** and can maintain state across multiple rows.
- Most effective usage pattern: 1–N `JOIN` → `LinkedHashMap` by primary key → collect children → snapshot to DTOs/records.
- Always check `NULL` on the child side in a `LEFT JOIN`; with primitive getters like `getLong`, call `wasNull()` immediately afterward.
- `ResultSetExtractor` does not automatically solve JOIN duplication, pagination, ordering, memory consumption, or concurrency. Choosing the right grouping key, SQL, and result design remains the application's responsibility.
- `JdbcTemplate` is responsible for resource cleanup and JDBC exception handling. Do not close the template's `ResultSet` or `Connection` inside an extractor.
- When you just need one DTO per row, use `RowMapper`; when you just need `COUNT/SUM`, prefer SQL aggregation; when you need per-row processing without returning a structure, consider `RowCallbackHandler`.
- **Start from the desired output shape** and the actual SQL row grain, then pick the matching callback; do not choose a callback just because it is the most general.

### References

- [Spring Framework Javadoc — ResultSetExtractor](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html)
- [Spring Framework Javadoc — JdbcTemplate](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework Javadoc — RowMapper](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jdbc/core/RowMapper.html)
- [Spring Framework Javadoc — RowMapperResultSetExtractor](https://docs.spring.io/spring-framework/docs/6.0.x/javadoc-api/org/springframework/jdbc/core/RowMapperResultSetExtractor.html)
- [Spring Framework Reference — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
