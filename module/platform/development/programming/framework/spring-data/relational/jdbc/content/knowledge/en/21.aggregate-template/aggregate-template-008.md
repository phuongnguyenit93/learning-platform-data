# Choosing the Template vs. Direct JDBC for Operations Outside the Aggregate Model

## 1. The Problem: When Repositories and Aggregates Are No Longer the Right Fit

Spring Data JDBC organizes data writes around aggregate roots. An aggregate's repository is the natural place to create, read, update, and delete the aggregate along with its owned child objects. This model protects invariants and clarifies consistency boundaries.

However, not every data operation in an application is an aggregate operation:

- A report that aggregates data across multiple tables and multiple aggregates.
- A screen that only needs a few columns to display a list.
- An administrative job that performs bulk updates based on a SQL condition.
- A job that writes to a staging table or reads data for reconciliation.
- An analytical query that requires JOIN, GROUP BY, CTEs, or window functions.

In those cases, forcing every operation through an aggregate repository makes the model harder to understand and produces ill-fitting queries. Spring provides multiple levels of data access. With Spring Data JDBC, two choices to distinguish are:

- **JdbcAggregateTemplate:** operates at the aggregate level, using Spring Data JDBC mapping and persistence semantics.
- **JdbcTemplate or NamedParameterJdbcTemplate:** operates directly on SQL and database rows/columns.

Both names include "template," yet the two tools solve different categories of problems. `JdbcAggregateTemplate` is an aggregate-operations API without going through a repository interface. `JdbcTemplate` is a general-purpose JDBC API suited for queries and updates that do not naturally map to aggregate operations.

This lesson helps determine which tool to use, how to coordinate them in transactions, and the risks when direct SQL mutates data belonging to an aggregate.

## 2. Two Different Levels of Abstraction

### 2.1. JdbcAggregateTemplate Works with Aggregates

`JdbcAggregateTemplate` sits at a lower level than repositories while preserving Spring Data JDBC's aggregate model. It uses mapping metadata to save and load aggregate roots, handling relationships to child objects according to the declared mapping.

For example, an order consisting of a root and order lines:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines
    - PurchaseOrderLine
    - PurchaseOrderLine
~~~

When saving an order via `JdbcAggregateTemplate`, the application passes an aggregate object. Spring Data JDBC handles the root table and child tables according to the mapping. The caller does not have to write SQL for each child table or manually assign foreign keys and collection indexes.

Example:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate aggregateTemplate;

    public PurchaseOrderWriter(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public PurchaseOrder create(PurchaseOrder order) {
        return aggregateTemplate.insert(order);
    }

    @Transactional
    public PurchaseOrder change(PurchaseOrder order) {
        return aggregateTemplate.update(order);
    }

    @Transactional
    public void remove(PurchaseOrder order) {
        aggregateTemplate.delete(order);
    }
}
~~~

These methods illustrate aggregate-level operations. Exact API names and signatures should be checked against your project's Spring Data Relational version, but the principle stays the same: the template accepts an aggregate object and performs persistence according to that aggregate's mapping.

If the application already has a clear repository interface, keep using the repository for routine CRUD. `JdbcAggregateTemplate` is useful when you need direct aggregate API calls—such as inside an adapter or infrastructure component without adding a dedicated repository interface.

### 2.2. JdbcTemplate Works with SQL Statements and Data Rows

`JdbcTemplate` has no concept of aggregate roots, ownership, or domain-model invariants. It executes SQL, binds parameters, reads `ResultSet`s, and maps results to whatever Java types the application specifies.

Example querying total available stock per SKU:

~~~java
public record StockSummary(String sku, long totalAvailable) {
}

@Repository
public class StockReportDao {

    private final JdbcTemplate jdbcTemplate;

    public StockReportDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<StockSummary> summarize() {
        String sql = """
                SELECT sku, SUM(available) AS total_available
                FROM inventory
                GROUP BY sku
                ORDER BY sku
                """;

        return jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new StockSummary(
                        rs.getString("sku"),
                        rs.getLong("total_available")
                )
        );
    }
}
~~~

The result is a reporting projection. There is no need to instantiate every `Inventory` aggregate merely to sum available quantities. The DAO owns the SQL statement and row mapping; it does not become an aggregate repository.

## 3. Quick Comparison

| Criterion | JdbcAggregateTemplate | JdbcTemplate / NamedParameterJdbcTemplate |
| --- | --- | --- |
| Working level | Aggregate root | SQL, tables, rows, and columns |
| Mapping | Uses Spring Data JDBC mapping metadata | Caller supplies `RowMapper`, `ResultSetExtractor`, or other mapping |
| Child object relationships | Handled via aggregate mapping | Caller writes JOIN/INSERT/UPDATE/DELETE manually |
| Domain invariants | Can invoke aggregate behavior before calling template; template does not replace domain validation | Unaware of invariants; caller must enforce |
| SQL | Framework generates SQL from mapping | Caller writes SQL |
| Multi-table reporting | Not the primary target | Well suited |
| Bulk DML | Operates per aggregate | Well suited when bulk SQL updates are needed |
| Routine aggregate CRUD | Can be used | Usually should not be rewritten manually |
| Projection optimization | Not natural when full aggregate is unneeded | Can select only required columns |
| Depends on Spring Data mapping | Yes | Not required |

Use `JdbcAggregateTemplate` when the target of the operation is an aggregate. Use direct JDBC when the use case truly works with row-level data, reports, staging tables, or specialized SQL.

## 4. When Is a Repository the Best Choice?

Before reaching for a template, check whether a repository interface already fits. A repository clearly declares which aggregate a use case operates on and provides a stable contract for application services.

Example:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Service using the repository:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void approve(Long id) {
        PurchaseOrder order = orders.findById(id).orElseThrow();
        order.approve();
        orders.save(order);
    }
}
~~~

This is the natural flow when business logic loads an aggregate, invokes domain behavior, and persists the new state. Do not switch to `JdbcAggregateTemplate` merely to avoid declaring a repository; repositories are usually the clearer abstraction for application code.

## 5. When to Use JdbcAggregateTemplate Instead of a Repository?

`JdbcAggregateTemplate` can be a good fit when:

- An infrastructure adapter needs to operate directly on aggregates without needing a dedicated repository interface.
- A component selects the aggregate type at runtime and needs a generic aggregate API.
- Explicit aggregate-level `insert`/`update`/`delete`/`find` operations are needed in a technical component.
- You want a shared abstraction across multiple aggregates while preserving Spring Data JDBC persistence semantics.

Example of an importer creating aggregates from validated input:

~~~java
@Service
public class CatalogImporter {

    private final JdbcAggregateTemplate aggregates;

    public CatalogImporter(JdbcAggregateTemplate aggregates) {
        this.aggregates = aggregates;
    }

    @Transactional
    public Product importProduct(Product product) {
        // Product has already been normalized and validated at the application/domain layer.
        return aggregates.insert(product);
    }
}
~~~

The template does not automatically turn imported data into valid data. The importer must still validate inputs, construct aggregates through appropriate factories, and invoke domain behavior to preserve invariants. `JdbcAggregateTemplate` handles persistence according to the mapping.

### The Template Is Not a SQL Builder

Do not use `JdbcAggregateTemplate` expecting to write arbitrary SQL such as:

~~~sql
SELECT category, COUNT(*)
FROM products
GROUP BY category;
~~~

That is a table-level aggregation and projection; `JdbcTemplate` or an appropriate query abstraction is the natural tool.

## 6. When to Use JdbcTemplate or NamedParameterJdbcTemplate?

### 6.1. Reports and Projections

A report may combine multiple tables without returning aggregates:

~~~java
public record MonthlySales(
        int year,
        int month,
        BigDecimal revenue
) {
}

@Repository
public class SalesReportDao {

    private final JdbcTemplate jdbc;

    public SalesReportDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<MonthlySales> byMonth(int year) {
        String sql = """
                SELECT EXTRACT(YEAR FROM paid_at) AS sales_year,
                       EXTRACT(MONTH FROM paid_at) AS sales_month,
                       SUM(total_amount) AS revenue
                FROM payments
                WHERE EXTRACT(YEAR FROM paid_at) = ?
                  AND status = ?
                GROUP BY EXTRACT(YEAR FROM paid_at),
                         EXTRACT(MONTH FROM paid_at)
                ORDER BY sales_month
                """;

        return jdbc.query(
                sql,
                (rs, rowNum) -> new MonthlySales(
                        rs.getInt("sales_year"),
                        rs.getInt("sales_month"),
                        rs.getBigDecimal("revenue")
                ),
                year,
                "PAID"
        );
    }
}
~~~

The `EXTRACT` function illustrates a dialect supporting that syntax. When implementing, verify date/time functions and result types on the target database. The key point is that the DAO fetches only the data needed for the report instead of loading full `Payment` aggregates.

### 6.2. Bulk Updates

When marking many rows based on a condition, direct JDBC can be simpler than loading every aggregate and saving:

~~~java
@Repository
public class CustomerMaintenanceDao {

    private final JdbcTemplate jdbc;

    public CustomerMaintenanceDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int deactivateInactiveCustomers(LocalDate cutoff) {
        return jdbc.update("""
                UPDATE customers
                SET active = false
                WHERE last_seen < ?
                  AND active = true
                """, cutoff);
    }
}
~~~

This is a row-oriented operation. It does not invoke behavior on each `Customer` aggregate and does not automatically check optimistic-locking versions. Use it only when business rules allow direct updates and required invariants are protected by SQL predicates, constraints, or application workflows.

### 6.3. NamedParameterJdbcTemplate for Multi-Parameter SQL

When there are many parameters, named parameters make SQL easier to read:

~~~java
@Repository
public class InventorySearchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventorySearchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<InventoryRow> findBelowThreshold(
            String warehouse,
            int threshold
    ) {
        String sql = """
                SELECT id, sku, available
                FROM inventory
                WHERE warehouse_code = :warehouse
                  AND available < :threshold
                ORDER BY id
                """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("warehouse", warehouse)
                .addValue("threshold", threshold);

        return jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new InventoryRow(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("available")
                )
        );
    }
}
~~~

Named parameters clarify where each value is bound. Both `JdbcTemplate` and `NamedParameterJdbcTemplate` bind values via JDBC; never concatenate input into SQL using string concatenation.

## 7. Aggregate Boundaries Do Not Disappear When Using Direct JDBC

An aggregate root protects the invariants of its owned data group. If a child table is part of an aggregate, mutating that child table directly can break states expected by the domain model.

Example:

~~~text
PurchaseOrder
  status = DRAFT
  lines
    - sku = BOOK-01, quantity = 2
    - sku = PEN-02, quantity = 5
~~~

Suppose the aggregate enforces rules:

- Only draft orders may modify order lines.
- Total quantity must be greater than 0.
- Each SKU may appear only once per order.
- Once an order is submitted, submission timestamp must be recorded and lines can no longer be edited.

A direct SQL statement updating `purchase_order_lines.quantity` bypasses those rules. Data could be altered even after order submission or leave the aggregate in an invalid domain state.

For aggregate-owned mutations, prefer:

1. Load the aggregate root.
2. Invoke domain behavior.
3. Save the aggregate via repository or `JdbcAggregateTemplate`.

Use direct SQL to modify rows belonging to an aggregate only with a clear justification—such as a specifically designed maintenance or bulk operation with explicit invariant guards, version handling, and real-database tests.

## 8. Transactions When Combining the Template and Direct JDBC

`JdbcAggregateTemplate`, `JdbcTemplate`, and `NamedParameterJdbcTemplate` can participate in the same transaction if they share the same `DataSource` and corresponding transaction manager.

Example use case writing an aggregate and an audit record:

~~~java
@Service
public class OrderRegistrationService {

    private final JdbcAggregateTemplate aggregates;
    private final JdbcTemplate jdbc;

    public OrderRegistrationService(
            JdbcAggregateTemplate aggregates,
            JdbcTemplate jdbc
    ) {
        this.aggregates = aggregates;
        this.jdbc = jdbc;
    }

    @Transactional
    public PurchaseOrder register(PurchaseOrder order) {
        PurchaseOrder saved = aggregates.insert(order);

        jdbc.update("""
                INSERT INTO order_audit(order_id, action)
                VALUES (?, ?)
                """,
                saved.id(),
                "CREATED"
        );

        return saved;
    }
}
~~~

When both templates use the same transaction-bound `DataSource`, inserting the aggregate and inserting the audit row run inside the same transaction. If the audit insert fails and an exception rolls back the transaction, the aggregate insert rolls back as well.

Do not assume this holds if the templates are configured against two different `DataSource`s. When an application spans multiple databases, configure an appropriate transaction manager per resource or design a dedicated coordination mechanism. A plain `@Transactional` annotation does not automatically create distributed transactions.

## 9. Do Not Mix Direct Updates with a Stale In-Memory Aggregate

One risk of combining both access levels is that an in-memory aggregate object becomes stale after a direct SQL statement.

Example:

1. A service loads `PurchaseOrder` with status `DRAFT`.
2. A DAO uses `JdbcTemplate` to update the database status to `CANCELLED`.
3. The service continues modifying the old `PurchaseOrder` object and calls `repository.save(order)`.

The in-memory object still carries status `DRAFT`. When saved, it may overwrite with the stale state or produce unexpected results depending on mapping and version strategy.

If direct SQL modifies aggregate data:

- Avoid continuing to save a stale aggregate instance without resynchronizing it.
- Reload the aggregate after the direct operation if further aggregate processing is needed.
- Consider optimistic locking/versioning to catch concurrent writes.
- Ideally, avoid having two independent write paths for the same aggregate unless coordination rules are clear.

Spring Data JDBC does not have a JPA-style persistence context/identity map, yet that does not cause already-loaded Java objects to refresh automatically when another `JdbcTemplate` modifies the database.

## 10. Optimistic Locking and Direct SQL

If an aggregate uses `@Version`, the aggregate save path checks and increments the version via Spring Data JDBC's mechanism. An `UPDATE` written via `JdbcTemplate` does not automatically apply that logic.

If a direct update must respect optimistic locking, include the expected version in the predicate and increment the version in the same statement:

~~~sql
UPDATE purchase_orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

After executing, inspect the affected row count:

- 1 row: update succeeded against the version that was read.
- 0 rows: aggregate does not exist or version no longer matches.

This SQL is illustrative. The version type, column name, and increment expression must match your schema. If multiple write paths exist, all of them must follow the same versioning convention; otherwise optimistic locking becomes unreliable.

## 11. Lifecycle Callbacks and Domain Events

Spring Data JDBC aggregate operations can participate in Spring Data lifecycle callbacks and events. When switching to `JdbcTemplate`, the application executes SQL and maps results directly; it does not invoke the aggregate persistence pipeline.

If your application relies on callbacks to:

- Normalize data before saving.
- Populate metadata or audit fields.
- Detect when an aggregate is saved.
- Emit outbox events.

then direct SQL bypasses those steps. Never assume `jdbc.update(...)` emits the same lifecycle events as `JdbcAggregateTemplate.insert(...)` or repository `save`.

For business requirements that publish events after commit, consider writing an outbox row in the same transaction. Do not send messages or call external APIs before the database transaction completes if data and messages must remain consistent.

## 12. Batch Operations and SimpleJdbcInsert

Direct JDBC also fits staging, import, or batch maintenance tasks where operations do not represent full aggregates.

Example batch update:

~~~java
public int[] markProcessed(List<Long> ids) {
    String sql = """
            UPDATE import_staging
            SET processed = true
            WHERE id = ?
            """;

    return jdbcTemplate.batchUpdate(
            sql,
            ids,
            500,
            (ps, id) -> ps.setLong(1, id)
    );
}
~~~

Batch size and statements sent depend on the JDBC driver. For large batches, consider splitting transactions into chunks if business rules permit partial commits, along with checkpointing and idempotent retries.

For simple inserts needing generated key support, Spring JDBC also offers utilities such as `SimpleJdbcInsert`. These remain table/row-level operations; they do not replace aggregate mapping or protect domain invariants.

## 13. SQL Safety and Identifier Management

With `JdbcTemplate`, input values must be passed as bind parameters:

~~~java
jdbcTemplate.update(
        "UPDATE customers SET active = ? WHERE id = ?",
        false,
        customerId
);
~~~

Never concatenate request data into SQL:

~~~java
// Unsafe: input becomes part of the SQL statement.
String sql = "SELECT * FROM customers WHERE name = '" + name + "'";
~~~

Bind parameters protect values, but cannot substitute table names, column names, or SQL keywords. When choosing a sort column dynamically, map input against a fixed whitelist:

~~~java
String orderColumn = switch (sortField) {
    case "name" -> "name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String sql = "SELECT id, name FROM customers ORDER BY " + orderColumn;
~~~

The identifier comes from a code-controlled whitelist, while filter values remain bound separately.

## 14. Where Does Direct JDBC Belong in the Architecture?

Do not let controllers call `JdbcTemplate` directly. Create an adapter/DAO with clear responsibilities:

~~~text
Controller
    |
    v
Application service
    |                 \
    v                  v
Aggregate repository  Report DAO
    |                  |
    v                  v
JdbcAggregateTemplate JdbcTemplate
    |                  |
    +--------+---------+
             |
             v
          Database
~~~

Example:

- `PurchaseOrderRepository`: `PurchaseOrder` aggregate operations.
- `PurchaseOrderReportDao`: JOIN SQL and projections for reporting.
- `InventoryMaintenanceDao`: purpose-built bulk updates.
- `OrderApplicationService`: coordinates transactions and use-case rules.

DAO names should describe their data purpose; avoid creating a catch-all `DatabaseHelper` holding every SQL statement in the system.

## 15. Decision Table

| Question | Choice to Consider |
| --- | --- |
| Am I creating, modifying, or deleting an aggregate root? | Repository first; `JdbcAggregateTemplate` when direct aggregate API is needed |
| Do I need to persist both the aggregate and mapped child objects? | Repository or `JdbcAggregateTemplate` |
| Do I only need a few columns for a report? | `JdbcTemplate` / `NamedParameterJdbcTemplate` |
| Do I need JOIN / GROUP BY / CTE / specialized SQL? | `JdbcTemplate` or an appropriate SQL tool |
| Do I need conditional bulk updates? | Direct JDBC with transactions, row-count checks, and invariant protection |
| Do I need non-aggregate staging or import operations? | Direct JDBC |
| Do I need to protect domain behavior and versions? | Load aggregate, invoke behavior, and save via repository/template |
| Do I need one transaction combining aggregate writes and an audit row? | Application service with `@Transactional` and a shared transaction manager |

## 16. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Direct SQL violates aggregate invariants | Bypassed domain behavior and business rules | Use aggregate operations or enforce required predicates/constraints in SQL |
| Child data out of sync with root | Wrote directly to child table without updating relationships/positions | Let aggregate mapping manage children or design explicit bulk rules |
| Audit and aggregate only partially commit | Two operations do not share the same transaction manager/resource | Place `@Transactional` on service and verify shared `DataSource` |
| Saving stale aggregate overwrites direct update | In-memory object is not refreshed after direct SQL | Reload aggregate or avoid mixing write paths |
| Optimistic locking misses conflicts | Direct SQL did not check/increment version | Put expected version in `WHERE` and increment atomically |
| Callbacks fail to run | Used `JdbcTemplate` instead of aggregate persistence | Invoke needed logic explicitly or use aggregate API |
| Report loads too many objects | Used aggregate repository for projection needing a few columns | Use SQL projection / `RowMapper` |
| SQL injection via sort field | Concatenated client-supplied identifier | Whitelist identifiers and bind values |
| Batch holds transaction too long | Stuffed too many rows into one transaction | Chunk if business allows, with checkpoints and retries |

## 17. Tool Selection Workflow

Before writing a new data operation, answer:

1. Does the data being modified belong to a specific aggregate root?
2. Does the use case need to enforce aggregate invariants?
3. Is mapping for owned child objects and relationships needed?
4. Does the result need to be a full aggregate or only a projection?
5. Are JOINs, GROUP BY, bulk DML, or specialized SQL required?
6. If direct SQL is used, which invariants, versions, or callbacks will stop running automatically?
7. Do the operations need to share a transaction, and which `DataSource`/transaction manager do they share?
8. Are row-count checks, checkpoints, or idempotency required?

If the target is an aggregate and requires domain behavior, use a repository or `JdbcAggregateTemplate`. If the use case works with relational data at row level, reports, or staging tables, use `JdbcTemplate`/`NamedParameterJdbcTemplate` inside a dedicated DAO.

## 18. Practice Exercises

**Exercise 1 — One aggregate, two APIs.** Create a `PurchaseOrder` and save it via a repository. Next, insert a new aggregate using `JdbcAggregateTemplate`. Compare how they are called and identify which mapping responsibilities the framework handles.

**Exercise 2 — Report projection.** Write a DAO using `JdbcTemplate` to sum monthly revenue. Return only the required columns in a report record without loading `Payment` aggregates.

**Exercise 3 — Bulk update.** Write a conditional update across multiple inventory rows. Inspect the affected row count and explain which invariants must be enforced in SQL or database constraints.

**Exercise 4 — Coordinated transaction.** Inside a `@Transactional` service, write an aggregate via `JdbcAggregateTemplate` and an audit row via `JdbcTemplate`. Deliberately fail the audit insert and verify that the aggregate insert also rolls back.

**Exercise 5 — Stale object.** Load an aggregate, update the same row using `JdbcTemplate`, and then save the stale in-memory object. Observe the outcome and propose how to prevent overwriting.

**Exercise 6 — Versioning.** Add `@Version` to the aggregate. Write a direct update with expected version and version increment. Run two concurrent transactions and observe one failing to update.

**Exercise 7 — Architectural choice.** For reporting, importing, bulk maintenance, and order status transitions, choose between repository, `JdbcAggregateTemplate`, or `JdbcTemplate`. Explain each choice in terms of aggregate boundaries and transactions.

## 19. Key Takeaways

`JdbcAggregateTemplate` and `JdbcTemplate` are not interchangeable ways to write SQL. `JdbcAggregateTemplate` works at the aggregate level using Spring Data JDBC's mapping; `JdbcTemplate`/`NamedParameterJdbcTemplate` works directly with SQL, rows, and columns.

Use repositories for standard CRUD and routine aggregate use cases. Use `JdbcAggregateTemplate` when you need a direct aggregate API without creating a repository interface. Use direct JDBC for reports, projections, staging, bulk DML, or specialized queries outside the aggregate model.

Whenever direct SQL modifies data belonging to an aggregate, the application must explicitly protect the invariants, versions, auditing, and lifecycle behavior that aggregate persistence normally handles. Place transactions on the application service when multiple operations must commit or roll back together, confirm they share the same transaction manager, and test the outcome against the target database.

### References

- [Spring Data Relational – JDBC Aggregate Operations](https://docs.spring.io/spring-data/relational/reference/jdbc/aggregate-operations.html)
- [Spring Data Relational – JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html)
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
