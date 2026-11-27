# Join Queries and Assembling Results into Desired Data Structures

In Spring Data Relational R2DBC, a `JOIN` query typically returns multiple flat rows from the database. The application may need to transform those rows into another Java structure, such as a customer with a list of orders, an order with its order lines, or a composite DTO containing data from multiple tables.

The SQL join and result assembly are two separate tasks. The database is responsible for combining tables according to `ON` conditions, filtering, sorting, and computing aggregates. The R2DBC driver emits each result row; Spring Data or `DatabaseClient` maps columns into Java values. The application can then group rows and build nested structures using Reactor operators.

Spring Data Relational R2DBC does not provide a persistence context or JPA/Hibernate-style lazy loading/fetch joins. Therefore, when data from multiple tables is needed, write join queries explicitly or use an appropriate aggregate mapping model. Do not expect that merely declaring an object reference causes the framework to load relationships automatically when reading an entity.

## 1. Joins Combine Data in the Database

Suppose a system has two tables, `customer` and `orders`:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    order_number VARCHAR(40) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL
);
```

A customer can have many orders. Join query:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS customer_email,
    o.id AS order_id,
    o.order_number AS order_number,
    o.total_amount AS order_total
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id;
```

`LEFT JOIN` preserves the customer even when there are no orders yet. For a customer with three orders, the result has three rows containing repeated customer information and distinct order information. For a customer without orders, the result still has one customer row, while the `orders` columns are SQL `NULL`.

Example flat result:

| customer_id | customer_name | order_id | order_number | order_total |
| ---: | --- | ---: | --- | ---: |
| 10 | Lan | 501 | ORD-501 | 120.00 |
| 10 | Lan | 502 | ORD-502 | 80.00 |
| 10 | Lan | 503 | ORD-503 | 45.00 |
| 11 | Minh | NULL | NULL | NULL |

The application may need results shaped like:

```json
[
  {
    "id": 10,
    "name": "Lan",
    "orders": [
      { "id": 501, "number": "ORD-501", "total": 120.00 },
      { "id": 502, "number": "ORD-502", "total": 80.00 },
      { "id": 503, "number": "ORD-503", "total": 45.00 }
    ]
  },
  {
    "id": 11,
    "name": "Minh",
    "orders": []
  }
]
```

This is a nested structure built by the application from multiple result rows. A SQL join does not automatically turn multiple rows into an object with a child collection.

## 2. Choosing the Right JOIN Type

Common join types:

| Join Type | Result | Common Use Case |
| --- | --- | --- |
| `INNER JOIN` | Keeps only rows with matching pairs on both sides | Only fetch customers that have orders |
| `LEFT JOIN` | Keeps all rows on the left; right columns are NULL if no match | Fetch all customers and their orders if any |
| `RIGHT JOIN` | Keeps all rows on the right; left columns are NULL if no match | Less common; usually table order can be swapped to use `LEFT JOIN` |
| `FULL OUTER JOIN` | Keeps rows from both sides even without matches | Reconciling two datasets; support depends on database |
| `CROSS JOIN` | Produces Cartesian product of two row sets | Combining every pair when genuinely needed |

`INNER JOIN` example:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
INNER JOIN orders o ON o.customer_id = c.id;
```

Customers without orders will not appear. If the response must represent customers with an empty orders list, use `LEFT JOIN`.

### Placing Conditions in `ON` vs. `WHERE`

With `LEFT JOIN`, where a condition is placed changes its meaning:

```sql
-- Keeps all customers; joins only paid orders.
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o
    ON o.customer_id = c.id
   AND o.status = 'PAID';
```

Conversely:

```sql
-- WHERE filters out rows where o.status is NULL,
-- so customers without orders are excluded from the result.
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'PAID';
```

A predicate on the right-hand table inside `WHERE` can cause a `LEFT JOIN` to behave like an `INNER JOIN` for that condition. If the goal is to retain left-side rows when no matching right-side row exists, consider placing the right-table filter condition in `ON`.

## 3. Using Aliases for Clear Join Row Mapping

When joining multiple tables, tables often share column names like `id`, `name`, and `created_at`. Do not use `SELECT *` and hope the mapper always distinguishes columns. List the needed columns and assign unique aliases:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Aliases help mapping code read the right columns and avoid name collisions. When reading via `Row`, use the declared aliases:

```java
row.get("customer_id", Long.class);
row.get("customer_name", String.class);
row.get("order_id", Long.class);
```

Alias names in SQL and names passed to `row.get` must be consistent. Alias case-sensitivity rules can depend on the database; use simple, consistent names and test with the real driver.

## 4. Mapping a Join Row to a Flat DTO

`DatabaseClient` fits custom join queries well because it lets you write SQL and map each row directly. First, define a DTO representing one join row:

```java
public record CustomerOrderRow(
        Long customerId,
        String customerName,
        String customerEmail,
        Long orderId,
        String orderNumber,
        BigDecimal orderTotal
) {
}
```

Query and mapper:

```java
Flux<CustomerOrderRow> rows = databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                c.email AS customer_email,
                o.id AS order_id,
                o.order_number AS order_number,
                o.total_amount AS order_total
            FROM customer c
            LEFT JOIN orders o ON o.customer_id = c.id
            ORDER BY c.id, o.id
            """)
        .map((row, metadata) -> new CustomerOrderRow(
                row.get("customer_id", Long.class),
                row.get("customer_name", String.class),
                row.get("customer_email", String.class),
                row.get("order_id", Long.class),
                row.get("order_number", String.class),
                row.get("order_total", BigDecimal.class)
        ))
        .all();
```

Each SQL row produces one `CustomerOrderRow`. With `LEFT JOIN`, `orderId`, `orderNumber`, and `orderTotal` can be null if a customer has no orders. Therefore, the DTO must allow nullable values for these fields; never use primitive `long` for a nullable column.

At this stage, the result is still a stream of flat rows. To produce a `Customer` with a `List<Order>`, rows must be grouped by `customerId`.

## 5. Grouping Multiple Rows into an Object with a Child Collection

In a one-to-many join, parent information repeats on each row. The standard approach is to group rows by parent ID, initialize the parent object on first encounter, and append children to its collection.

Define response DTOs:

```java
public record OrderView(
        Long id,
        String number,
        BigDecimal total
) {
}

public record CustomerWithOrders(
        Long id,
        String name,
        String email,
        List<OrderView> orders
) {
}
```

To accumulate results, you can use an internal builder:

```java
private static final class CustomerBuilder {
    private final Long id;
    private final String name;
    private final String email;
    private final List<OrderView> orders = new ArrayList<>();

    private CustomerBuilder(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    private CustomerWithOrders build() {
        return new CustomerWithOrders(
                id, name, email, List.copyOf(orders)
        );
    }
}
```

Then group using `LinkedHashMap`:

```java
public Mono<List<CustomerWithOrders>> findCustomersWithOrders() {
    return queryCustomerOrderRows()
            .collect(
                    LinkedHashMap<Long, CustomerBuilder>::new,
                    (customers, row) -> {
                        CustomerBuilder customer = customers.computeIfAbsent(
                                row.customerId(),
                                id -> new CustomerBuilder(
                                        id,
                                        row.customerName(),
                                        row.customerEmail()
                                )
                        );

                        // LEFT JOIN produces a NULL child row when the customer has no orders.
                        if (row.orderId() != null) {
                            customer.orders.add(new OrderView(
                                    row.orderId(),
                                    row.orderNumber(),
                                    row.orderTotal()
                            ));
                        }
                    }
            )
            .map(customers -> customers.values().stream()
                    .map(CustomerBuilder::build)
                    .toList());
}
```

`queryCustomerOrderRows()` represents the `Flux<CustomerOrderRow>` publisher from the previous section. `collect` consumes all rows, using `customerId` as the key to ensure each customer has only one builder. Each valid order is added to the customer's list. If a customer has no orders, the builder is still created and its list remains empty.

`LinkedHashMap` preserves first-seen order, which is useful when the SQL already has an `ORDER BY`. If ordering does not need to be preserved, `HashMap` can be used. Grouping data in this example holds state in memory until all rows are consumed, so it is suited to bounded result sizes. For large datasets, paginate or group in chunks rather than collecting everything into one collection.

## 6. Why Check the Child ID After a LEFT JOIN?

With `LEFT JOIN`, all columns of the child table are null when no matching row exists. To determine whether a child exists, check the child's primary key column:

```java
if (row.orderId() != null) {
    // Order exists; add to the list.
}
```

Do not check a business property that might be nullable:

```java
// Unreliable if order_number can be NULL.
if (row.orderNumber() != null) {
    // Might skip a valid order.
}
```

The primary key of an existing row cannot be SQL NULL. Thus, the child ID alias is the reliable indicator distinguishing a real child row from a null row produced by an outer join.

If the response needs to distinguish "no child" from "child exists with some null attributes", use the child primary key as the condition for creating the object while preserving nullable properties.

## 7. Multi-Level Joins and Avoiding Child Duplication

Suppose a data structure has three levels:

```text
Customer
  └── Orders
        └── OrderLines
```

A query joining all three tables:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number,
    l.id AS line_id,
    l.product_name AS product_name,
    l.quantity AS quantity
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
LEFT JOIN order_line l ON l.order_id = o.id
ORDER BY c.id, o.id, l.id;
```

If an order has three lines, the customer and order information repeats three times. If you blindly add an `OrderView` per row, the response will contain three duplicate orders. You must group by customer ID, then group by order ID, and add new lines keyed by line ID.

A builder structure can use nested maps:

```java
private static final class OrderBuilder {
    private final Long id;
    private final String number;
    private final Map<Long, OrderLineView> lines = new LinkedHashMap<>();

    private OrderBuilder(Long id, String number) {
        this.id = id;
        this.number = number;
    }
}

private static final class CustomerBuilder {
    private final Long id;
    private final String name;
    private final Map<Long, OrderBuilder> orders = new LinkedHashMap<>();

    private CustomerBuilder(Long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

In the accumulator:

```java
CustomerBuilder customer = customers.computeIfAbsent(
        row.customerId(),
        id -> new CustomerBuilder(id, row.customerName())
);

if (row.orderId() != null) {
    OrderBuilder order = customer.orders.computeIfAbsent(
            row.orderId(),
            id -> new OrderBuilder(id, row.orderNumber())
    );

    if (row.lineId() != null) {
        order.lines.putIfAbsent(
                row.lineId(),
                new OrderLineView(
                        row.lineId(),
                        row.productName(),
                        row.quantity()
                )
        );
    }
}
```

`putIfAbsent` keyed by line ID prevents a line from being added multiple times when joining with another child table. Upon completion, iterate the maps to build immutable DTOs: each customer holds a list of orders, and each order holds a list of lines.

When multiple one-to-many relationships are joined together, the intermediate row count can grow as the product of the element counts of each relationship. For example, a customer with 4 orders of 5 lines each yields about 20 rows for that customer. Weigh data transfer costs and in-memory grouping carefully.

## 8. Joining Multiple Tables When Only a Flat DTO Is Needed

Not every join query needs to construct nested objects. For list screens or reports, a flat DTO is often simpler and more efficient:

```java
public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
```

Query:

```java
Flux<OrderSummary> summaries = databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.order_number AS order_number,
                c.name AS customer_name,
                o.total_amount AS total_amount
            FROM orders o
            INNER JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id DESC
            """)
        .bind("status", "PAID")
        .map((row, metadata) -> new OrderSummary(
                row.get("order_id", Long.class),
                row.get("order_number", String.class),
                row.get("customer_name", String.class),
                row.get("total_amount", BigDecimal.class)
        ))
        .all();
```

Here each order row produces one `OrderSummary`. There is no need to group by customer if the desired response is a list of orders with customer names. Choose the DTO shape based on what the API or business layer needs, not the shape of individual table entities.

## 9. Aggregating Data Directly in SQL When Child Collections Are Not Needed

If the goal is to summarize metrics, let the database perform `COUNT`, `SUM`, `MIN`, `MAX`, or `GROUP BY` rather than loading every row and computing in Java.

Example total order count and total amount per customer:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
```

DTO:

```java
public record CustomerOrderStats(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpent
) {
}
```

Mapping:

```java
Flux<CustomerOrderStats> stats = databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderStats(
                row.get("customer_id", Long.class),
                row.get("customer_name", String.class),
                row.get("order_count", Long.class),
                row.get("total_spent", BigDecimal.class)
        ))
        .all();
```

`COUNT(o.id)` returns `0` for customers without orders in a `LEFT JOIN`; `COUNT(*)` would return `1` because the customer row still exists after the outer join. That is why you should count a child table key column when counting children.

`COALESCE` replaces the SQL NULL from `SUM` with `0` when there are no orders. Aggregate return types depend on the database and column type; the mapper must use a compatible Java type. If the database returns numeric values with different precision, verify the actual type conversion.

## 10. Using `@Query` in Repositories for Joins

You can declare a join SQL query directly in a repository with `@Query` if the query is stable and belongs to the repository:

```java
public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    @Query("""
           SELECT
               c.id AS customer_id,
               c.name AS customer_name,
               o.id AS order_id,
               o.order_number AS order_number
           FROM customer c
           LEFT JOIN orders o ON o.customer_id = c.id
           WHERE c.id = :customerId
           ORDER BY o.id
           """)
    Flux<CustomerOrderRow> findCustomerOrders(
            @Param("customerId") Long customerId
    );
}
```

Projection/interface or DTO mapping capabilities of `@Query` depend on the Spring Data R2DBC version and supported projection types. If you need explicit control over reading aliases and converting column types, `DatabaseClient` with `.map((row, metadata) -> ...)` is often easier to inspect.

Another option is for the repository to return a flat `Flux<CustomerOrderRow>` and let the service group it into `CustomerWithOrders`. Do not expect a derived query method to infer multi-table joins solely from property names; query derivation is suited to predicates on mapped entities, while custom joins generally require explicit SQL.

## 11. `R2dbcEntityTemplate` and Aggregate Relationships

Spring Data Relational models relationships around aggregates, with an aggregate root and members belonging to the aggregate. Annotations such as `@MappedCollection` can describe certain aggregate-owned relationships so Spring Data loads and saves them according to supported mappings.

Example model of an aggregate with a list of order lines:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<PurchaseOrderLine> lines;
}
```

`@MappedCollection` describes elements belonging to the aggregate and the column referencing the root. This is Spring Data Relational's aggregate mapping, not a lazy relationship/fetch join mechanism like JPA. When you need a custom join DTO, multiple independent tables, reporting projections, or exact SQL control, `DatabaseClient`/`@Query` remain the right choices.

Do not add `@MappedCollection` merely to perform arbitrary joins. Use it when the data model genuinely represents an aggregate root and its owned members under Spring Data Relational rules.

## 12. Avoiding N+1 Queries When Combining Data

An easy-to-write but costly pattern is fetching a list of customers and calling a repository per customer to fetch orders:

```java
return customerRepository.findAll()
        .flatMap(customer -> orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders -> new CustomerWithOrders(
                        customer.getId(),
                        customer.getName(),
                        customer.getEmail(),
                        orders
                )));
```

With N customers, the code issues one query for customers and N queries for orders. This is the N+1 query problem. At scale, round trips multiply and latency compounds.

### Approach 1: Join in a Single Query

Use `LEFT JOIN` to fetch customers and orders in the same result set, then group by ID as in earlier examples. This reduces round trips, though it repeats parent data on each child row.

### Approach 2: Two Batched Queries

If you want to avoid repeating rows in a join, you can:

1. Fetch one set of customers (typically one page).
2. Fetch all orders whose `customer_id` is in that ID set via one `IN` query.
3. Group orders by `customer_id` in Java.
4. Attach the order lists to each customer.

Example second query:

```java
Flux<Order> findByCustomerIdIn(Collection<Long> customerIds);
```

The service can collect IDs for the page of customers, run one batch query, and group results into a `Map<Long, List<Order>>`. This keeps round trips constant by relationship type rather than issuing one query per customer.

If the ID list is large, watch database/driver bind-parameter limits. You can split into smaller batches or use database-specific array/table parameters.

### Approach 3: Keep N+1 Only When the Dataset Is Truly Small

For a known small handful of customers, N+1 can be simple enough and acceptable. If running `flatMap` concurrently, bound concurrency so you do not fire too many simultaneous queries. Do not assume higher concurrency always makes queries faster; it can pressure the connection pool and database.

## 13. Pagination When Joining One-to-Many

Paginating directly over a one-to-many join result can break page semantics. For example, one customer with 10 orders produces 10 join rows. Applying `LIMIT 10` may return 10 rows of a single customer instead of 10 customers.

If the goal is to paginate customers, paginate the root set first and then fetch children:

```sql
SELECT c.id, c.name, c.email
FROM customer c
WHERE c.status = :status
ORDER BY c.id
LIMIT :pageSize OFFSET :offset;
```

Then fetch orders for the page's customer IDs:

```sql
SELECT o.id, o.customer_id, o.order_number, o.total_amount
FROM orders o
WHERE o.customer_id IN (:customerIds)
ORDER BY o.customer_id, o.id;
```

`IN (:customerIds)` is illustrative at the query API level; how a collection expands into SQL parameters depends on `DatabaseClient`, Spring Data, and the driver. With derived repository methods like `findByCustomerIdIn`, the framework handles the collection according to supported query derivation.

Attach orders to customers in memory by `customer_id`. Total customer count for pagination should be counted on the root set:

```sql
SELECT COUNT(*)
FROM customer c
WHERE c.status = :status;
```

If counting over a one-to-many join, use `COUNT(DISTINCT c.id)` to avoid counting a customer multiple times. Keep ordering and filter conditions consistent across the root page query, child query, and count query.

If data changes between the two queries, the root page and child rows may reflect two different points in time. When snapshot consistency is required, consider executing both queries inside the same transaction with a suitable database isolation level.

## 14. Nulls, Data Types, and Column Mapping in Joins

Join results can contain SQL NULL even when the underlying column is declared `NOT NULL`, because an outer join produces null values for the unmatched side. Therefore:

- Use wrapper types like `Long`, `Integer`, `Boolean` for potentially null columns; never use primitives if SQL NULL must be represented.
- Check the child primary key before instantiating a child object.
- Read Java types compatible with driver codecs and SQL types.
- Assign unique aliases to identically named columns.
- Never assume column order in `SELECT *` stays stable across schema changes.

For instance, a join row may have `order_id = null` while `customer_id` always has a value. The mapper still builds `CustomerOrderRow`, while the grouping step only builds an order when `orderId` is non-null.

When SQL uses `COALESCE`, `CASE`, `COUNT`, or expressions, the returned type may differ from the base column type. Check actual types in `RowMetadata`/the driver and use matching Java types.

## 15. Mapping Joins with `Row` and `RowMetadata`

In `DatabaseClient`, the mapping callback receives `Row` and `RowMetadata`:

```java
.map((row, metadata) -> {
    Long customerId = row.get("customer_id", Long.class);
    String customerName = row.get("customer_name", String.class);
    Long orderId = row.get("order_id", Long.class);

    return new CustomerOrderRow(
            customerId,
            customerName,
            row.get("customer_email", String.class),
            orderId,
            row.get("order_number", String.class),
            row.get("order_total", BigDecimal.class)
    );
})
```

`RowMetadata` provides metadata about the result set's columns, which is useful for dynamic mapping or inspecting column names/types. For fixed DTOs, reading columns by explicit alias is usually easier to maintain.

Do not retain `Row` for use after the mapping callback completes. Extract the needed data into a DTO or value object within the mapping scope; the `Row` lifecycle belongs to driver result consumption.

## 16. Using JSON Aggregation When Supported by the Database

Some databases provide JSON aggregate functions to turn multiple child rows into a JSON array directly in SQL. For example, PostgreSQL offers `json_agg`/`jsonb_agg` and `json_build_object`/`jsonb_build_object`:

```sql
SELECT
    c.id,
    c.name,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', o.id,
                'number', o.order_number,
                'total', o.total_amount
            )
        ) FILTER (WHERE o.id IS NOT NULL),
        '[]'::jsonb
    ) AS orders_json
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
```

This query returns one row per customer where `orders_json` is a JSON array. `FILTER (WHERE o.id IS NOT NULL)` avoids creating a fake JSON element filled with null fields from the outer join. `COALESCE` returns an empty array when there are no orders.

In the application, you can read the JSON column using a driver-supported type, such as `Json` from the PostgreSQL R2DBC driver, and use Jackson to deserialize it into `List<OrderView>`. This reduces row-grouping logic in Java but increases coupling to database-specific JSON functions and requires appropriate converters/codecs.

Only use JSON aggregation when the database supports it, the response shape fits, and the team accepts database-specific SQL. For queries that must stay portable across databases, grouping DTOs from result rows is easier to port.

## 17. Transactions When Assembling Results Across Multiple Queries

If data is fetched via a single join query, the database returns rows from a single statement. If using multiple queries (e.g., a customer page followed by orders), those queries may observe data at different points in time.

When business logic requires consistent data, wrap the publishers in a reactive transaction:

```java
@Transactional(readOnly = true)
public Mono<List<CustomerWithOrders>> findPageWithOrders(...) {
    // 1. Read customer page.
    // 2. Collect customer IDs.
    // 3. Read orders for the ID set.
    // 4. Group and assemble DTOs.
}
```

`readOnly = true` is a transaction hint/metadata honored according to the transaction manager and driver capabilities; do not treat it as a guarantee that the database blocks all writes. If a consistent snapshot across multiple statements is required, choose an appropriate database isolation level. Reactive transactions require publishers to be chained within the same transaction context; calling `subscribe()` manually breaks this coordination.

## 18. Common Mistakes

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Wrong column read after join | Multiple tables share column names like `id` or `name` | List columns explicitly and assign unique aliases |
| Customers without orders disappear | Used `INNER JOIN` when customers should be kept | Use `LEFT JOIN` |
| Customers without orders dropped despite LEFT JOIN | Child table condition placed in `WHERE` | Move the appropriate condition into `ON` |
| Fake child created with all nulls | Did not check child ID before creating object | Check that child primary key is non-null |
| Parent appears multiple times | Each join row mapped as an independent parent | Group by parent ID |
| Orders repeated multiple times when joining lines | Joining multiple one-to-many relationships causes row multiplication | Group at each level and deduplicate by child ID |
| Page contains only one parent despite large page size | `LIMIT` applied to join rows rather than parents | Paginate root first, then fetch children by ID set |
| Parent count is inflated | `COUNT(*)` over a one-to-many join | Count root rows or use `COUNT(DISTINCT root.id)` |
| Queries slow down linearly with parent count | N+1 queries from calling child repository per parent | Use a join or `IN` batch query |
| Mapper type conversion error | SQL expression/aggregate returns a different type than expected | Check `RowMetadata` and driver types |
| Held object does not reflect recent join/update | Entities are not synchronized automatically | Build a new DTO or re-query data |

When investigating, inspect the SQL first: join type, `ON`/`WHERE` predicates, aliases, and ordering. Next, inspect row counts, per-row mapping, grouping logic, and final cardinality. Most nested-structure assembly bugs come from one of these steps.

## 19. Join Query Design Workflow

A systematic approach:

1. Define the desired output structure: flat DTO, parent-child, statistics, or JSON document.
2. Identify table relationships and cardinality: one-to-one, one-to-many, or many-to-many.
3. Choose `INNER JOIN` or an outer join depending on whether unmatched rows must be retained.
4. List needed columns and assign unique aliases.
5. Apply filtering, ordering, and limits at the right data level.
6. Map each row to a flat DTO with appropriate nullable types.
7. If a nested structure is needed, group by ID at each level and ignore null children from outer joins.
8. With multiple one-to-many relationships, watch for row multiplication and deduplicate by child ID.
9. If pagination is needed, paginate the root first and then fetch children, or use a suitable SQL strategy.
10. Test with parents having no children, one child, many children, nullable child fields, and multi-level relationships.
11. Measure query count and returned row count to catch N+1 issues or bloated join results.

## 20. Key Takeaways

- SQL `JOIN` combines tables and returns a flat result set; nested object assembly is typically done by the application after mapping each row.
- R2DBC has no JPA persistence context or lazy relationship loading; write joins or batch queries explicitly when related data is needed.
- Assign unique aliases to identically named columns and read by alias from `Row`.
- `LEFT JOIN` retains parents without children; check the child primary key to avoid constructing fake child objects from NULL columns.
- For one-to-many, group by parent ID to collect children; for multiple levels, group by each ID and deduplicate children.
- Flat DTOs fit lists/reports; SQL aggregates fit summary metrics; nested DTOs fit parent-child structured responses.
- `COUNT(child.id)` is usually more accurate than `COUNT(*)` when counting children across a `LEFT JOIN`; counting parents across a join requires `COUNT(DISTINCT parent.id)`.
- Avoid N+1 using joins or `IN` batch queries; bound batch sizes when ID lists are large.
- Paginate parents before attaching children so a single parent is not split across pages by join rows.
- `@Query`, `DatabaseClient`, and `R2dbcEntityTemplate` offer varying levels of SQL/mapping control; `@MappedCollection` describes aggregate mapping, not lazy fetch joins.
- Test against the real database and driver to verify aliases, data types, nulls, cardinality, and performance.

When assembling data from multiple tables in Spring Data R2DBC, decide the target result shape first and design the SQL and mapping steps accordingly. Let the database handle joins, filtering, and aggregation where it excels; let the application group rows into DTOs or aggregates shaped for the caller.
