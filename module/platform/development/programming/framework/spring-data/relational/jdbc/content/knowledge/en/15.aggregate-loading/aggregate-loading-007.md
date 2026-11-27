# Trade-offs Between Full Aggregate Loading and Dedicated Read Models

In **Spring Data JDBC**, repositories are designed around the aggregate root. When an application loads an aggregate, Spring Data JDBC maps the root along with components declared as owned by it, such as child collections via `@MappedCollection`. This lets the domain work with a consistent unit and avoids complex ORM-style lazy loading mechanisms.

However, not every screen or report needs the entire aggregate. An order list page might only need the order number, creation date, status, customer name, and total amount. Loading the entire order along with dozens of order lines just to display five columns creates unnecessary overhead. In such situations, a **dedicated read model** (read model/projection) using a SQL JOIN and selecting only required columns can be a better fit.

This lesson analyzes the trade-offs between two approaches: loading the full aggregate to execute business logic, and loading a dedicated read model to serve queries. We will build an order example, use repositories for domain operations, use Spring JDBC for the read model, and examine how to choose based on data volume, pagination, transactions, and consistency.

## 1. Two distinct needs: business state changes and data presentation

Suppose a sales system has these tables:

~~~text
purchase_orders
├── id
├── order_number
├── customer_id
├── created_at
└── status

order_lines
├── id
├── order_id
├── product_id
├── quantity
└── unit_price

customers
├── id
└── display_name
~~~

An order can have many order lines. In the domain, `PurchaseOrder` is the aggregate root and `OrderLine` is a child entity. Customer is an independent aggregate, and the order holds a `customerId` reference.

Two use cases have very different data requirements:

**Use case A — confirming an order:** needs to know the current status, check the order lines, apply business rules, and save changes. This is the aggregate's job.

**Use case B — displaying an order list:** only needs the order number, customer name, status, creation date, and total amount. This is a display-oriented query; there is no need to build a full object graph for modifying business state.

~~~mermaid
flowchart TB
    subgraph Write["Business operations"]
        S["OrderApplicationService"] --> R["PurchaseOrderRepository"]
        R --> A["PurchaseOrder aggregate"]
        A --> L["OrderLine collection"]
    end
    subgraph Read["Display queries"]
        C["OrderListController / QueryService"] --> Q["OrderSummaryDao"]
        Q --> SQL["SQL JOIN + aggregate"]
        SQL --> DTO["OrderSummary DTO"]
    end
    R --> DB[("Relational database")]
    SQL --> DB
~~~

The diagram illustrates two access paths with distinct purposes. Both can still share the same database and transaction manager; there is no requirement to build two databases or a full CQRS system.

## 2. Full aggregate loading in Spring Data JDBC

### 2.1. Aggregate root and child collections

Mapping example:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    // Constructor, getters, and business methods.
}
~~~

`OrderLine` maps to the `order_lines` table. The `order_id` column on the child table links order lines to the root. Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

When calling:

~~~java
PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();
~~~

Spring Data JDBC loads the root and mapped components belonging to the aggregate according to its retrieval strategy. Child collections are not JPA-style lazy associations: domain code can use the loaded lines without waiting for a later property access to trigger a lazy query.

This is an important characteristic of Spring Data JDBC. It makes retrieval behavior clearer: when a use case loads an aggregate, developers know the aggregate is loaded to work as a unit. However, if an aggregate has thousands of child elements, loading all of them can consume time, memory, and database resources.

### 2.2. When is full loading necessary?

Full loading fits when the use case needs the elements to protect invariants or change aggregate state:

- Checking whether an order has any lines before submitting.
- Calculating and validating total amounts from domain data.
- Adding or removing order lines through methods on the root.
- Checking quantity limits, status, and business rules.
- Making changes that must be saved consistently within one aggregate.

Example:

~~~java
@Transactional
public void submitOrder(long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow(() ->
            new NoSuchElementException("Order not found"));

    order.submit(); // Root checks status and lines collection.
    orders.save(order);
}
~~~

If `submit()` requires confirming the order has at least one order line, the aggregate must have information about its lines to check that rule. Reading a single flag or count might suffice in some domains, but when an operation needs properties and behaviors of individual lines, loading the aggregate is the clean approach.

### 2.3. Cost of large aggregates

Suppose an order has 500 lines, each with many attributes. A list screen only needs 5 fields, yet loading the full aggregate will:

1. Instantiate many Java objects unused by the screen.
2. Read more columns and rows than necessary.
3. Consume memory when loading a page of multiple orders.
4. Increase application mapping and processing work.
5. Potentially issue multiple queries to load aggregate components, depending on mapping and framework strategy.

Do not claim every aggregate load always generates exact N+1 queries or always runs a single JOIN. Observe the actual SQL for your Spring Data JDBC version, aggregate structure, driver, and database. What is certain from a design standpoint is that the aggregate model requires loading the mapped components needed to work with the aggregate; there is no arbitrary JPA-style lazy loading.

## 3. What is a dedicated read model?

A **read model** is a data structure designed to answer a specific read question. It can be:

- A DTO containing columns joined from multiple tables.
- A projection selecting only a subset of properties.
- Aggregated results such as `COUNT`, `SUM`, `MAX`.
- A denormalized record maintained specifically to serve queries.

A read model does not have to be an entity saveable through a repository. It typically has no domain lifecycle, needs no `@Id`, and is not used as an aggregate root.

For example, an order list screen needs:

| Field | Source |
|---|---|
| `orderId` | `purchase_orders.id` |
| `orderNumber` | `purchase_orders.order_number` |
| `customerName` | `customers.display_name` |
| `status` | `purchase_orders.status` |
| `createdAt` | `purchase_orders.created_at` |
| `lineCount` | `COUNT(order_lines.id)` |
| `totalAmount` | `SUM(quantity * unit_price)` |

SQL can compute these fields directly in the database:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    c.display_name AS customer_name,
    o.status,
    o.created_at,
    COUNT(l.id) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY
    o.id,
    o.order_number,
    c.display_name,
    o.status,
    o.created_at
ORDER BY o.created_at DESC, o.id DESC;
~~~

The database returns only the columns the screen needs. The application does not have to load every `PurchaseOrder`, then iterate over every `OrderLine` to sum totals and look up customer names.

## 4. Writing a read DAO with Spring JDBC

Spring Data JDBC and Spring JDBC can coexist in one application. Repositories manage aggregates, while `JdbcTemplate` or `NamedParameterJdbcTemplate` executes custom read SQL.

### 4.1. DTO for the order list

Create a record:

~~~java
package com.example.orders.read;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        LocalDateTime createdAt,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

`OrderSummary` is a DTO/read model. It is not a `PurchaseOrder` aggregate root. Do not create an `OrderSummaryRepository` extending `CrudRepository` just to read this result.

### 4.2. DAO using `NamedParameterJdbcTemplate`

~~~java
package com.example.orders.read;

import java.util.List;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSummaryDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSummaryDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findAllSummaries() {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.display_name AS customer_name,
                o.status,
                o.created_at,
                COUNT(l.id) AS line_count,
                COALESCE(
                    SUM(l.quantity * l.unit_price),
                    0
                ) AS total_amount
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN order_lines l ON l.order_id = o.id
            GROUP BY
                o.id,
                o.order_number,
                c.display_name,
                o.status,
                o.created_at
            ORDER BY o.created_at DESC, o.id DESC
            """;

        return jdbc.query(sql, (rs, rowNum) ->
            new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
            )
        );
    }
}
~~~

This snippet assumes the schema has a timestamp `created_at` column and a `customers` table with `display_name`. Adjust time types according to your database/driver if using `TIMESTAMP WITH TIME ZONE` or another temporal type.

### 4.3. Why `LEFT JOIN` with `order_lines`?

If you use a regular `JOIN`, orders without order lines are excluded from the results. `LEFT JOIN` retains orders even when they have no child lines yet; `COUNT(l.id)` returns `0`, while `SUM(...)` returns `NULL`, so `COALESCE(..., 0)` converts the total amount to `0`.

For the customers table, the example uses `JOIN` because it assumes every order must have a valid customer. If the system allows customer data to be deleted or references to become absent, you may need `LEFT JOIN` and an appropriate display rule.

### 4.4. Query service layer

You can create a read-only service:

~~~java
@Service
public class OrderQueryService {

    private final OrderSummaryDao summaries;

    public OrderQueryService(OrderSummaryDao summaries) {
        this.summaries = summaries;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> listOrders() {
        return summaries.findAllSummaries();
    }
}
~~~

`readOnly = true` is a transaction hint/configuration for Spring's query layer; it does not by itself guarantee the database forbids all writes. Its main purpose is to express read intent and give the transaction manager/database an opportunity to optimize appropriately.

## 5. Use projections or write a separate DAO?

Spring Data JDBC supports repository queries and result mapping. For simple queries, you can declare `@Query` or derived query methods. For DTO results and multi-table JOINs, you can use `@Query` with projection/DTO types within the mapping capabilities of your Spring Data JDBC version.

Choose the implementation based on complexity and the degree of control needed:

| Approach | Best when | Considerations |
|---|---|---|
| `CrudRepository` returning aggregate | Business logic requires domain operations | Loads aggregate according to mapping |
| Derived query | Simple read conditions on properties | Expressiveness is limited by method names |
| `@Query` on repository | Custom SQL tightly tied to the repository/root | Requires managing result mapping and clarity |
| `JdbcTemplate`/`NamedParameterJdbcTemplate` | JOINs, aggregate functions, reports, custom DTOs | Manage SQL and row mapping manually |
| View/materialized view | Complex queries reused widely or needing snapshots | Requires managing refreshes, migrations, and data lag |

A separate DAO does not mean creating another database or violating Spring Data JDBC. It is a way to separate display queries from the aggregate persistence API.

## 6. Key trade-offs between the two loading approaches

### 6.1. Comparison by purpose

| Criterion | Full aggregate loading | Dedicated read model |
|---|---|---|
| Purpose | Executing behavior and protecting invariants | Answering a specific read question |
| Returned data | Root and mapped components belonging to aggregate | Only needed columns/values |
| Object type | Domain aggregate | DTO/projection/read model |
| Can call `save()`? | Yes, via root repository | Usually no |
| Business consistency | Suited for changes within an aggregate | Does not protect aggregate invariants itself |
| Multi-table JOINs | Not the primary goal | Very well suited |
| Aggregations `COUNT`, `SUM` | Can be computed in Java if already loaded | Database usually performs more efficiently |
| List pagination | Must account for aggregate loading cost | Usually simpler and lighter |
| Mapping cost | Can be high when aggregates have many children | Usually lower when DTOs are small |
| Reusability | Domain behaviors | Tailored to each read need |

### 6.2. When full aggregate loading is the right choice

Choose the aggregate when:

- The use case changes state or data.
- Multiple invariants within the same aggregate must be checked.
- Domain methods should be used instead of manually issuing SQL per table.
- Aggregate scope is reasonably sized.
- Loading child elements is necessary to perform the behavior.

For example, submitting an order requires verifying the list of order lines and total amount before changing status. If you only read `status` and `line_count` without loading the aggregate, the domain method may lack enough data to verify other rules such as quantity limits or per-line conditions.

### 6.3. When a dedicated read model fits better

Choose a read model when:

- The screen only needs a few fields.
- Multiple aggregates need to be joined for display.
- Statistics, counts, sums, or sorting by computed values are needed.
- The list has many records and needs pagination.
- The query is for a report or dashboard, and its result is not used to mutate aggregates.

For example, a dashboard needs daily total revenue, order counts by status, and customer names. Loading every aggregate and summing in Java can waste resources; SQL `GROUP BY` is usually a better fit.

### 6.4. Do not turn every query into a read model

If you only need to load one order by ID to call `submit()`, writing one DAO to read status, another DAO to read lines, and manually stitching a domain object together complicates the business flow and bypasses aggregate boundaries. Separate out a read model only when it serves a clear reading need.

## 7. Pagination: avoid loading thousands of aggregates just to display one page

A list of 100,000 orders should not load all aggregates into memory and then slice the first 20 orders. Paginate at the database.

### 7.1. Paginating a read model with `LIMIT` and `OFFSET`

Example SQL for one page:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    c.display_name AS customer_name,
    o.status,
    o.created_at
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
ORDER BY o.created_at DESC, o.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

The ordering includes `o.id` as a tie-breaker so results remain stable when multiple orders share the same `created_at`. Without deterministic ordering, a record can appear on different pages across queries.

For screens needing line counts and total amounts, you can use a subquery or CTE to aggregate order lines first, then paginate the orders. This avoids multiplying root rows in JOIN results when each order has many lines:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS total_amount
    FROM order_lines
    GROUP BY order_id
)
SELECT
    o.id,
    o.order_number,
    o.status,
    COALESCE(t.line_count, 0) AS line_count,
    COALESCE(t.total_amount, 0) AS total_amount
FROM purchase_orders o
LEFT JOIN line_totals t ON t.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

A CTE separates the aggregation step from the order-fetching step. Depending on the database and data, the query optimizer may handle CTEs differently; inspect the execution plan when optimizing.

### 7.2. Limitations of OFFSET on deep pages

When `OFFSET` is very large, the database may have to scan and discard many rows before returning the page. For large lists or infinite scrolling, consider **keyset pagination** (seek pagination):

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The client sends back the `lastCreatedAt` and `lastId` pair from the last record of the previous page. A suitable index on `(created_at, id)` helps the database locate the next page without skipping a large offset. Ensure timezones and timestamp precision are handled consistently between the cursor and database.

### 7.3. When should aggregates be paginated?

If a UI displays a list of orders and each row needs domain operations right after selection, you still do not necessarily need to load full aggregates for all rows. You can:

1. Query the list page using a lightweight read model.
2. Let the user select an order.
3. Load the full aggregate by ID when viewing details or executing behavior.

This keeps the list page lightweight while still routing business operations through the aggregate root.

## 8. Avoiding row duplication in one-to-many JOINs

Joining a root table directly with a child table can produce multiple rows for the same order:

~~~sql
SELECT o.id, o.order_number, l.product_id
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id;
~~~

If order `1001` has three lines, the result has three rows carrying `o.id = 1001`. This is the expected behavior of a one-to-many relationship, but if mapped directly into an `OrderSummary` list, you may see the same order repeated three times.

To get one row per order, use:

- `GROUP BY` and aggregate functions.
- A subquery/CTE aggregating the child table before joining.
- `EXISTS` if you only need to check whether child rows exist.
- An appropriate projection if results need multiple levels of data.

Example fetching only orders that have at least one order line:

~~~sql
SELECT o.id, o.order_number, o.status
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
)
ORDER BY o.id;
~~~

Avoid joining when you do not need columns from the child table. `EXISTS` usually expresses the intent cleanly and avoids duplicating roots in the result.

## 9. Consistency between read models and aggregates

If the read model and repository access the same database, data can be read from the same source, yet read timing and transaction isolation still matter.

### 9.1. Same transaction when a consistent snapshot is needed

Suppose a screen reads order information and totals from multiple tables. If queries run in different transactions or at different times, an order can change between reads. Results might mix a new status with an old total.

If a use case needs a consistent snapshot, establish appropriate transaction boundaries and isolation levels. Do not add transactions purely out of habit; base it on consistency requirements and database behavior.

### 9.2. On-the-fly vs. precomputed read models

There are two options:

**Computed on query:** SQL JOIN/aggregation reads from source tables each time. Data is up to date per transaction isolation, though queries can be heavy.

**Stored denormalized read model:** updates a separate summary table, materialized view, or projection when source data changes. Reads are faster, but there can be lag and you must handle synchronization, rebuilds, and retries.

If storing precomputed summaries, clarify:

- How often is the summary updated?
- Is eventual consistency acceptable?
- What happens when a consumer processes an event multiple times?
- Can the projection be rebuilt from source data?
- When an aggregate write fails, could the summary be updated erroneously?

There is no need to adopt full CQRS for a simple order list page. Switch to stored read models only when measurements show direct queries cannot meet requirements.

### 9.3. A read model is not the final source of business decisions

A list showing status `DRAFT` may already be stale by the time the user clicks submit. The service still needs to load the latest aggregate and re-check conditions before modifying it. Do not use a screen DTO as the sole basis for writing data.

Safe flow:

~~~text
List (read model)
       |
       v
User selects order
       |
       v
Load latest PurchaseOrder
       |
       v
Check invariants
       |
       v
Mutate domain + repository.save()
~~~

This separates display data from domain state at write time.

## 10. Should you split an aggregate just because loading is heavy?

A large aggregate can be a sign of poorly chosen boundaries, but **do not split an aggregate just to make one screen read faster**. First determine why the aggregate loads so much data:

- Do the child entities genuinely share the same lifecycle and need consistent updates together?
- Does a collection grow unboundedly over time?
- Is history or logging attached to the root even though it can be managed independently?
- Does the business use case actually need the entire collection or just an aggregate metric?
- Can a read-model query serve the screen instead?

For example, `OrderLine` usually belongs to `PurchaseOrder` because order lines make up the order's contents. However, `OrderStatusHistory` can grow continuously and serve only auditing. If history can be managed independently, keeping all history inside the aggregate can make loading the order progressively heavier.

An alternative design could be:

~~~text
PurchaseOrder aggregate
├── id
├── status
└── OrderLine collection

OrderStatusHistory aggregate (or separate audit data)
├── id
├── orderId
├── oldStatus
├── newStatus
└── changedAt
~~~

`OrderStatusHistory` references `orderId`, but can have its own repository/queries if its lifecycle and audit requirements are independent. In that case, decide how to ensure audit entries are written alongside status change events, such as within the same transaction or via an outbox.

## 11. A service example combining write model and read model

Example service using a repository to change status and a DAO to display lists:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OrderSummaryDao summaries;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OrderSummaryDao summaries) {
        this.orders = orders;
        this.summaries = summaries;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> listOrders() {
        return summaries.findAllSummaries();
    }

    @Transactional
    public void submit(long orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() ->
                new NoSuchElementException("Order not found"));

        order.submit();
        orders.save(order);
    }
}
~~~

This example shows an application service coordinating both a read DAO and a repository. In larger projects, these can be split into `OrderQueryService` and `OrderCommandService` for clearer separation of responsibilities. There is no strict rule requiring every query and command to live in separate classes.

Key points:

- `listOrders()` returns DTOs for the screen.
- `submit()` loads the aggregate root to validate and apply business logic.
- DTOs are never passed back into `repository.save()`.
- The repository is not turned into a dumping ground for every reporting query.

## 12. Performance: measure before optimizing

There is no rule that read models are always faster or aggregate loading is always slow. Outcomes depend on data, indexes, query counts, network round-trips, the database, and mapping overhead.

When comparing the two approaches, measure at least:

| Metric | Question |
|---|---|
| Rows read | How many children does the aggregate load? How many rows does the read query return? |
| Columns read | Are many unused columns being fetched? |
| SQL statements | How many queries does aggregate mapping execute? |
| Database time | Do JOINs/aggregations have proper indexes? |
| Mapping time | Is a large object graph being constructed? |
| Memory | How many objects does a result page hold in heap? |
| Page size | Is the record count bounded? |
| Data freshness | How much lag does a precomputed projection have? |

Indexes to consider for the example:

~~~sql
CREATE INDEX idx_purchase_orders_created_id
    ON purchase_orders(created_at, id);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);

CREATE INDEX idx_purchase_orders_customer_id
    ON purchase_orders(customer_id);
~~~

Specific indexes should be based on real queries and your DBMS. Every index adds write overhead and storage cost; do not mechanically index every column.

Use the database's execution plan to verify whether JOINs, sorts, and aggregations leverage indexes. Fewer lines of SQL does not automatically mean faster execution.

## 13. Common design mistakes

| Mistake | Consequence | How to address |
|---|---|---|
| Loading full aggregates to display a small list | Reading and mapping unnecessary data | Use DTOs/projections with only needed columns |
| Using DTOs to update aggregates | Bypasses invariants and latest state | Load root, call domain methods, save via repository |
| Treating child collections as lazy | Subsequent access does not trigger JPA-style lazy queries | Load aggregates intentionally or use read queries |
| Joining root with child and returning one DTO per row | Same order appears multiple times | `GROUP BY`, subqueries, or `EXISTS` |
| Paginating after loading the entire object graph | Wastes memory and time | Paginate in the database via a read model |
| Building precomputed read models without defining lag | Users see unexplained stale data | Define consistency, rebuilds, and event handling |
| Splitting aggregates just to optimize one screen | Weakens business boundaries | Separate read queries first; split roots only if lifecycle/invariants require it |
| Using list data to make write decisions | State may already have changed | Load fresh aggregate and re-validate on command |
| Writing SQL JOINs without FK indexes | Queries degrade as data grows | Check execution plans and add suitable indexes |

## 14. Selection workflow for a new use case

When designing a query in Spring Data JDBC, answer these in order:

1. **Is this a command or a query?** If changing business state, start from the aggregate root. If only displaying/aggregating, consider a read model.
2. **Are aggregate invariants needed?** If yes, load the root and the components needed for domain checks.
3. **Which fields are needed?** If only a few columns across multiple tables are needed, write a projection/DTO.
4. **What is the data volume?** For large lists, paginate in the database.
5. **What level of consistency is needed?** Compute directly from source tables, use a transactional snapshot, or use a precomputed projection.
6. **Can you measure a bottleneck?** Inspect SQL, query plans, row counts, and memory before splitting aggregates or adding complex mechanisms.

### Quick decision matrix

| Need | Starting point |
|---|---|
| Read one order to confirm | `PurchaseOrderRepository.findById()` |
| Change order status | Load aggregate, call domain method, `save()` |
| Order list with customer names | Read DAO with JOIN and DTO |
| Daily total revenue | SQL `GROUP BY` |
| Large list page | Projection + database pagination |
| Order details with all order lines | Load aggregate if domain behavior is needed; DTO JOIN if read-only |
| Long audit history | Separate query or independent audit model |
| Dashboard needing very fast aggregations | Consider views/materialized views/projections after measuring |

## 15. Practice exercises

### Exercise 1 — Comparing aggregates and DTOs

1. Create a `PurchaseOrder` with 20 `OrderLine` items.
2. Read the order via `findById()` and record SQL statement count, rows read, and time.
3. Write an `OrderSummaryDao` query returning order number, status, and total amount.
4. Compare data loaded and objects instantiated.
5. Explain why the DTO does not replace the aggregate when calling `submit()`.

### Exercise 2 — Paginating a list

1. Create several thousand orders.
2. Write a paginated query returning 20 rows ordered by `created_at DESC, id DESC`.
3. Test `OFFSET` on the first page and on a deep page.
4. Write a keyset pagination version using `created_at` and `id`.
5. Compare execution plans and timings.

### Exercise 3 — One-to-many JOINs

1. JOIN `purchase_orders` and `order_lines`.
2. Observe how an order with multiple lines duplicates rows in the result.
3. Rewrite using `GROUP BY` or a pre-aggregating CTE.
4. Check whether orders with no order lines still appear.

### Exercise 4 — Boundary decisions

Suppose an order has 10,000 status history records. Determine:

- Do history records need to be modified consistently with the aggregate?
- Can they be separate audit data?
- Does the detail screen need to load all of them or just the latest 10 records?
- Should a paginated read DAO be used for history?
- If the model is split, how do you ensure audit records are written alongside status changes?

## 16. Conclusion

**Full aggregate loading** fits when a use case requires domain behavior and the aggregate root's invariants. In Spring Data JDBC, mapped components belonging to an aggregate are loaded according to the framework's strategy, without relying on access-time lazy loading like JPA. This makes behavior clear, though large aggregates can increase rows read, object counts, and memory usage.

**Dedicated read models** fit when screens need a small set of columns, multi-table JOINs, statistics, or pagination. `JdbcTemplate`, `NamedParameterJdbcTemplate`, `@Query`, projections, or views can deliver lightweight DTOs without creating CRUD repositories for every table.

The two approaches complement each other: use repositories to modify aggregates, and use read models to answer read questions. When users trigger a command, load the latest aggregate and re-verify business rules. Split an aggregate only when lifecycles and invariants indicate a new boundary makes sense; do not reshape your domain just because a screen needs fewer columns.
