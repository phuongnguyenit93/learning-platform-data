# Joins, Result Sets, and the Risk of Row Multiplication

## 1. Objectives and Mental Model

When querying relational data, `JOIN` pairs rows based on a join condition. A business record in a parent table **does not necessarily correspond to a single result row**: if a child table has multiple matching rows, the parent table's columns repeat across each result row. In Spring's data-access layer, confusing the **SQL row count** with the **business object count** can cause wrong counts, double-counted sums, duplicate DTOs, incomplete pagination, or incorrect relationship mapping.

After this lesson, you should be able to distinguish:

- **Result row grain:** does each row represent a customer, an order, or an order line?
- **Result cardinality:** how many rows can a `JOIN` condition produce for a single parent key?
- **Legitimate repetition from a 1–N relationship** vs. actual duplicate data that needs cleanup.
- **SQL queries**, **Spring JDBC mapping**, and **ORM/JPA**: how does each layer handle repeated rows?
- How to use `EXISTS`, pre-join aggregation, key-based mapping, and two-step pagination to return the exact objects desired.

A practical rule: **before writing a `JOIN`, finish the sentence "each output row represents one …"**. If the answer is "one order line," do not expect each customer to appear only once.

## 2. Why Can a `JOIN` Multiply Rows?

Suppose we have these relationships:

```text
customer (1) ──── (N) orders (1) ──── (N) order_line
      customer            orders            order line
```

- `customer.id` is the unique key of a customer.
- `orders.customer_id` is a foreign key: one customer can have many orders.
- `order_line.order_id` is a foreign key: one order can have many lines.
- A `JOIN` from customer to orders, and then to order lines, produces **one row for every matching key combination**. `customer.id` and `orders.id` values repeat as needed; this is normal SQL behavior.

With `INNER JOIN`, parents without matching children are excluded. With `LEFT JOIN`, the parent still appears at least once, with `NULL` in columns from the unmatched side. With multiple independent child branches, the number of combinations can grow multiplicatively: a customer with 2 orders and 3 addresses can produce 2 × 3 = 6 rows when joining both child sets. This is commonly called **fan-out** or **row multiplication**.

This differs from **true duplicate data** (for example, two rows sharing the same primary key, which a primary key constraint must prevent). Even though a customer repeats across multiple `JOIN` result rows, each row can still hold a distinct `order_line.id` and be completely valid.

## 3. Runnable SQL Example

The example below uses standard SQL syntax compatible with PostgreSQL and H2. Run the statements sequentially in a test database.

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    total_amount DECIMAL(12, 2) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, name) VALUES
    (1, 'An'), (2, 'Binh'), (3, 'Chi');

INSERT INTO orders (id, customer_id, total_amount) VALUES
    (10, 1, 120.00),
    (20, 1, 20.00),
    (30, 2, 120.00);

INSERT INTO order_line (id, order_id, amount) VALUES
    (101, 10, 50.00),
    (102, 10, 70.00),
    (103, 20, 20.00),
    (104, 30, 90.00),
    (105, 30, 30.00);
```

The base dataset has **3 customers, 3 orders, and 5 order lines**. Customer Chi has no orders yet.

Query joining all three tables:

```sql
SELECT c.id AS customer_id,
       c.name,
       o.id AS order_id,
       l.id AS line_id,
       l.amount
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l ON l.order_id = o.id
ORDER BY c.id, o.id, l.id;
```

Results in query order:

| customer_id | name | order_id | line_id | amount |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 10 | 101 | 50.00 |
| 1 | An | 10 | 102 | 70.00 |
| 1 | An | 20 | 103 | 20.00 |
| 2 | Binh | 30 | 104 | 90.00 |
| 2 | Binh | 30 | 105 | 30.00 |
| 3 | Chi | NULL | NULL | NULL |

**Exactly 6 rows**, even though there are only 3 customers. For An, the first and second rows share `customer_id=1` and `order_id=10`, yet differ in `line_id`. For Chi, `LEFT JOIN` yields one row with child columns set to `NULL`. Replacing both `LEFT JOIN`s with `INNER JOIN` drops Chi and leaves 5 rows.

If the business needs a list of *order lines accompanied by customer info*, these 6 rows are right. If the business needs a list of *customers*, this flat result must be queried or mapped differently.

## 4. Counting and Summing: Know What You Are Counting

The following query places four aggregations side by side to show the difference clearly:

```sql
SELECT c.id AS customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.id) AS order_references,
       COUNT(DISTINCT o.id) AS distinct_orders,
       COUNT(l.id) AS line_count,
       COALESCE(SUM(l.amount), 0) AS line_amount
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l ON l.order_id = o.id
GROUP BY c.id
ORDER BY c.id;
```

| customer_id | joined_rows | order_references | distinct_orders | line_count | line_amount |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 3 | 2 | 3 | 140.00 |
| 2 | 2 | 2 | 1 | 2 | 120.00 |
| 3 | 1 | 0 | 0 | 0 | 0.00 |

- `COUNT(*)` counts **post-JOIN result rows**. Because `LEFT JOIN` still yields a row for Chi, the count is 1 even though Chi has no orders.
- `COUNT(o.id)` counts only non-`NULL` values, yet order 10 is counted twice because it has two lines. It **does not** give the number of unique orders.
- `COUNT(DISTINCT o.id)` gives the count of distinct orders by order key in this query.
- `COUNT(l.id)` accurately counts the 5 order lines across the sample data because each line appears once in the current query. If another independent child table is joined causing fan-out, that number could also be multiplied.
- `SUM(l.amount)` accurately sums the order lines in the current example; `COALESCE` turns the `NULL` sum for customers with no lines into 0.

A dangerous mistake is summing order totals **after joining order lines**:

```sql
-- WRONG if the goal is the sum of each order's total once.
SELECT c.id, SUM(o.total_amount) AS wrong_total
FROM customer AS c
JOIN orders AS o ON o.customer_id = c.id
JOIN order_line AS l ON l.order_id = o.id
GROUP BY c.id
ORDER BY c.id;
```

For An, order 10 has a total of 120 but appears twice, so the sum yields **260 instead of 140** (`120 + 120 + 20`). For Binh, order 30 also appears twice, yielding **240 instead of 120**. This is a *double counting* bug, not a SQL syntax error.

When you want total amount per customer, sum at the **order grain** first:

```sql
SELECT c.id AS customer_id,
       COALESCE(SUM(o.total_amount), 0) AS correct_total
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
GROUP BY c.id
ORDER BY c.id;
```

Result: An = 140.00, Binh = 120.00, Chi = 0.00. When you simultaneously need multiple metrics at different grains, aggregate each child table separately and then join the aggregated results:

```sql
WITH order_stats AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_total
    FROM orders
    GROUP BY customer_id
),
line_stats AS (
    SELECT o.customer_id,
           COUNT(*) AS line_count
    FROM orders AS o
    JOIN order_line AS l ON l.order_id = o.id
    GROUP BY o.customer_id
)
SELECT c.id,
       COALESCE(os.order_count, 0) AS order_count,
       COALESCE(os.order_total, 0) AS order_total,
       COALESCE(ls.line_count, 0) AS line_count
FROM customer AS c
LEFT JOIN order_stats AS os ON os.customer_id = c.id
LEFT JOIN line_stats AS ls ON ls.customer_id = c.id
ORDER BY c.id;
```

Do not use `SUM(DISTINCT o.total_amount)` to patch row multiplication: two legitimate orders can have the **same total amount**, causing `DISTINCT` summation to drop one order.

## 5. Choosing Query Patterns by Desired Output

### 5.1. Only Need to Know Whether Child Records Exist: `EXISTS`

If the question is "which customers have placed at least one order?", there is no need to build joined row sets:

```sql
SELECT c.id, c.name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
)
ORDER BY c.id;
```

Returns exactly the two customers An and Binh, one row each. `EXISTS` is an existence check (logically a semi-join); it does not multiply parent rows by matching order counts.

### 5.2. Only Need Unique Parent Info: Project the Right Columns or Group by Key

`SELECT DISTINCT c.id, c.name ... JOIN ...` can yield one row per customer **if only customer columns are selected**. However, if you also select `o.id` or `l.id`, rows still differ on child columns, so `DISTINCT` does not collapse them to one row per customer.

`DISTINCT` applies to the **entire selected column tuple**, and does not mean "keep one row per parent key." Nor does it fix a multiplied `SUM`, unless you redesign the query to aggregate at the right grain.

### 5.3. `LEFT JOIN` Conditions: Distinguishing `ON` and `WHERE`

```sql
-- Still keeps customers with no line > 50;
-- lines not meeting the condition are not joined.
SELECT c.id, o.id, l.id
FROM customer AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
LEFT JOIN order_line AS l
       ON l.order_id = o.id AND l.amount > 50
ORDER BY c.id, o.id, l.id;
```

Moving `l.amount > 50` down to `WHERE` discards rows where `l.amount IS NULL`; customers without matching lines can vanish, making `LEFT JOIN` behave like `INNER JOIN` with respect to that predicate. State the goal explicitly: **filter joined child records** vs. **keep only parents that have matching child records**. The two goals produce different results.

### 5.4. Paginate by Parent Objects, Not by JOIN Rows

For example, taking `LIMIT 2` on the 6-row result set in section 3 returns only **An's two rows**, not the two customers An and Binh. When paginating customers along with child data, a generally safe approach is:

1. Page one fetches customer IDs matching the filter in a deterministic order, using `LIMIT/OFFSET` or keyset pagination on the **customer table**.
2. Next, query the orders/lines belonging to **the IDs in that page** (using `IN`, batch queries, or an equivalent approach).
3. Group data by parent key in the application and restore the exact order of the initial page.

If data changes between the two queries, transaction isolation levels and business consistency requirements must be considered. `ORDER BY` must be deterministic, ideally including a unique key to break ties.

## 6. Spring JDBC: A `ResultSet` Row Does Not Automatically Become a Parent Object

In `JdbcTemplate`, `RowMapper<T>` maps **each row** of a `ResultSet` to one `T`. If the SQL in section 3 has 6 rows, `jdbcTemplate.query(sql, rowMapper)` returns a 6-element list (unless you transform it afterward). Writing a `RowMapper<Customer>` that only reads `customer_id`/`name` produces multiple objects with the same ID. `queryForObject(...)` is also unsuitable when a query returns multiple rows: it expects a single row and can throw `IncorrectResultSizeDataAccessException`.

When you want a `CustomerView -> orders -> lines` structure, you must **group by key**. `ResultSetExtractor<T>` fits when reading the entire `ResultSet` to build a multi-level structure. The example below is a class used in a Spring application with a configured `JdbcTemplate` and the `spring-jdbc` library; it is not a standalone Java program runnable with `javac` alone.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;

public final class CustomerReadService {
    private final JdbcTemplate jdbcTemplate;

    public CustomerReadService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<CustomerView> findAll() {
        String sql = """
            SELECT c.id AS customer_id, c.name,
                   o.id AS order_id,
                   l.id AS line_id, l.amount
            FROM customer c
            LEFT JOIN orders o ON o.customer_id = c.id
            LEFT JOIN order_line l ON l.order_id = o.id
            ORDER BY c.id, o.id, l.id
            """;

        return jdbcTemplate.query(
            sql,
            (ResultSetExtractor<List<CustomerView>>) rs -> {
                Map<Long, CustomerView> customers = new LinkedHashMap<>();
                Map<Long, Map<Long, OrderView>> ordersByCustomer =
                    new LinkedHashMap<>();

                while (rs.next()) {
                    long customerId = rs.getLong("customer_id");

                    CustomerView customer = customers.get(customerId);
                    if (customer == null) {
                        customer = new CustomerView(
                            customerId,
                            rs.getString("name"),
                            new ArrayList<>()
                        );
                        customers.put(customerId, customer);
                    }

                    Long orderId = rs.getObject("order_id", Long.class);
                    if (orderId == null) {
                        continue; // Customer has no orders.
                    }

                    Map<Long, OrderView> orders = ordersByCustomer
                        .computeIfAbsent(
                            customerId,
                            id -> new LinkedHashMap<>()
                        );

                    OrderView order = orders.get(orderId);
                    if (order == null) {
                        order = new OrderView(orderId, new ArrayList<>());
                        orders.put(orderId, order);
                        customer.orders().add(order);
                    }

                    Long lineId = rs.getObject("line_id", Long.class);
                    if (lineId != null) {
                        order.lines().add(new LineView(
                            lineId, rs.getBigDecimal("amount")
                        ));
                    }
                }

                return new ArrayList<>(customers.values());
            }
        );
    }

    public record CustomerView(
        long id, String name, List<OrderView> orders
    ) {}

    public record OrderView(
        long id, List<LineView> lines
    ) {}

    public record LineView(
        long id, BigDecimal amount
    ) {}
}
```

On the sample dataset, `findAll()` returns **3 `CustomerView`s**, containing 2, 1, and 0 orders respectively. Order 10 contains 2 lines; order 20 contains 1 line; order 30 contains 2 lines. In this example, `LinkedHashMap` preserves key discovery order, while the SQL `ORDER BY` dictates the input row order.

Three key mapping details:

1. **Keys must uniquely identify entities.** Group orders by `order_id` and lines by `line_id`, not by customer name or monetary amount. If a key is unique only within a parent, use a composite key (such as `(orderId, lineNumber)`).
2. **Right-side foreign keys can be `NULL` in a `LEFT JOIN`.** `getLong()` returns `0` on SQL `NULL` and requires calling `wasNull()` to distinguish; here `getObject("order_id", Long.class)` allows checking `null`. Check before constructing child objects.
3. **When joining additional independent child sets**, a `line_id` can repeat across multiple combination rows. In that case, the example above needs a set of seen `line_id`s per order—or better yet, separate queries so no fan-out occurs. Never deduplicate arbitrarily across all field values.

The example uses mutable `List`s inside `record`s to keep grouping clear. For DTOs returned by an API, create immutable copies after grouping to avoid accidental mutation.

### 6.1. Standalone Java 17: Simulating the Difference Between Row Count and Order Count

The following snippet needs neither Spring nor a database; it simulates the joined rows from section 3 to demonstrate counting by key.

Create `FanOutDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class FanOutDemo {
    record Row(int customerId, Integer orderId) {}

    public static void main(String[] args) {
        List<Row> resultRows = List.of(
            new Row(1, 10), new Row(1, 10), new Row(1, 20),
            new Row(2, 30), new Row(2, 30), new Row(3, null)
        );

        Map<Integer, Integer> joinedRows = new LinkedHashMap<>();
        Map<Integer, Set<Integer>> uniqueOrders = new LinkedHashMap<>();

        for (Row row : resultRows) {
            joinedRows.merge(row.customerId(), 1, Integer::sum);
            Set<Integer> ids = uniqueOrders.computeIfAbsent(
                row.customerId(), ignored -> new LinkedHashSet<>()
            );
            if (row.orderId() != null) {
                ids.add(row.orderId());
            }
        }

        for (int customerId : joinedRows.keySet()) {
            System.out.printf(
                "customer=%d rows=%d orders=%d%n",
                customerId,
                joinedRows.get(customerId),
                uniqueOrders.get(customerId).size()
            );
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac FanOutDemo.java
java FanOutDemo
```

Expected output:

```text
customer=1 rows=3 orders=2
customer=2 rows=2 orders=1
customer=3 rows=1 orders=0
```

This example explains why **raw row counting** and **unique order key counting** yield different results. It only simulates post-query data; in real systems, always push appropriate filtering, counting, or aggregation down into SQL when possible to avoid fetching excessive data.

## 7. JPA/Hibernate: One Entity Can Appear in Multiple SQL Rows

In JPA, a query with `JOIN FETCH` on a collection association can generate multiple SQL rows for the same parent entity. For example:

```jpql
SELECT o
FROM OrderEntity o
LEFT JOIN FETCH o.lines
WHERE o.customer.id = :customerId
```

If an order has two lines, SQL normally needs two rows to load them. The **persistence context** guarantees that a JPA entity with a given identity is managed as one consistent object in that context; yet that does not mean SQL row count, result list reference count, and distinct entity count are identical across all versions and providers.

Points to check in real applications:

- With **Hibernate 6**, duplicate parent references caused by `join fetch` are typically deduplicated automatically in memory after materializing results. Older providers or versions may have different list-return rules; verify exact behavior.
- `SELECT DISTINCT o` in JPQL can affect the returned entity list or generated SQL, yet **it does not eliminate the SQL row combinations required to fetch child data**. Do not use it as a substitute for proper query design and aggregation.
- Collection `JOIN FETCH` combined with pagination (`setFirstResult`/`setMaxResults`, `Pageable`) can force Hibernate to paginate in memory or emit warnings/errors depending on configuration. Paginate parent IDs first and load related data in a follow-up step when reliable pagination is needed.
- Fetching multiple one-to-many collections simultaneously can create a large Cartesian product. With Hibernate, fetching multiple **bags** simultaneously can also trigger `MultipleBagFetchException`. Consider batch fetching, `@BatchSize`, two independent queries, or explicitly grouped DTO projections.
- `JOIN FETCH` can resolve some **N+1 query** cases, though that does not mean it is always cheaper. Measure query count, returned row count, network payload, and mapping time.

Keep the distinction clear: **SQL determines the row set**, **JDBC reads each row**, and **ORM decides how to construct and link entities** from those rows. Bugs can occur at any layer.

## 8. How to Diagnose "Duplicate" Data

When a screen reports "duplicated customers" or "inflated totals," inspect in this order:

1. **Identify the desired grain:** one customer, one order, one order line, or a key pair? Check the actual primary keys, foreign keys, and unique constraints.
2. **Check row counts at each JOIN step:** start from the parent table, join one child table at a time, and compare `COUNT(*)`, `COUNT(DISTINCT parent.id)`, and `COUNT(DISTINCT child.id)`. Do not look only at display-name columns.
3. **Inspect sample rows with keys included:** add `customer.id`, `orders.id`, and `order_line.id` to a temporary query to see which rows create which combinations.
4. **Check `ON`, `WHERE`, and JOIN type:** especially conditions placed in `WHERE` on tables on the right side of a `LEFT JOIN`.
5. **Check aggregations:** is an order-level monetary value being summed across each order line? Was another child table joined before `SUM`/`COUNT`?
6. **Check mapping:** does `RowMapper` instantiate a parent object per row? Does `ResultSetExtractor`/ORM group by the right key? Are childless parents dropped because of wrong `NULL` handling?
7. **Check pagination and performance:** is `LIMIT` applied to JOIN rows or parent objects? Inspect `EXPLAIN`/`EXPLAIN ANALYZE` in an appropriate environment; a crucial metric is the actual number of rows flowing through joins, not just runtime on a tiny dataset.

In database design, `PRIMARY KEY`, `FOREIGN KEY`, and `UNIQUE` constraints (where business rules require) keep relationships sound. Indexes on `orders.customer_id` and `order_line.order_id` typically assist join queries, though effectiveness depends on dataset and execution plan; **an index cannot fix semantic fan-out**.

## 9. Self-Check Exercises

**Scenario A.** On the sample tables, what does `SELECT COUNT(*)` across all three tables with `LEFT JOIN` return? What does `COUNT(DISTINCT c.id)` return?

**Answer:** 6 and 3. Counting rows is not the same as counting customers.

**Scenario B.** Why does `SUM(o.total_amount)` after joining `order_line` equal 260 for An? What is the reliable fix?

**Answer:** Order 10 has two lines, so its total of 120 is added twice; aggregate at the order level first, or sum from `orders` without joining `order_line`.

**Scenario C.** To find customers who have placed orders, appearing once per customer, is `JOIN` followed by `DISTINCT` required?

**Answer:** Not required. `WHERE EXISTS` directly expresses the existence check without multiplying parent rows.

**Scenario D.** An API returns 20 customers per page along with their order lists. Why might `LIMIT 20` after `LEFT JOIN orders` return fewer than 20 customers?

**Answer:** The limit applies to 20 **SQL rows**, and multiple rows may belong to the same customer. Paginate customer keys first, then load the orders for that page.

## 10. Key Takeaways

- `JOIN` produces rows for **matching combinations**, not according to how many objects you want to return to the application.
- A repeated parent key across rows can be valid 1–N data; inspect **child keys** before concluding data is duplicated.
- `COUNT(*)`, `COUNT(child.id)`, `COUNT(DISTINCT child.id)`, and `SUM(...)` have different meanings after a JOIN. Aggregate at the right **data grain**.
- `EXISTS` checks existence; pre-join aggregation prevents double counting; key-based mapping builds nested DTOs; and parent-key pagination avoids missing items.
- In Spring JDBC, `RowMapper` works row by row; when you need one parent object with child collections, use a key-grouping strategy such as `ResultSetExtractor` or an appropriate query design. In JPA/Hibernate, you still must account for SQL fan-out, fetch behavior, and pagination.
