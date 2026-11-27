# Defining SQL with @NamedNativeQuery

`@NamedNativeQuery` allows declaring a named native SQL statement in JPA metadata so it can be reused in multiple places across an application. Unlike JPQL, native SQL works directly with table names, column names, functions, and syntax of the database management system. JPA can map native query results to entities or use `@SqlResultSetMapping` to construct DTOs and complex result shapes.

This approach is suitable when the SQL statement needs database-specific features, queries across multiple tables in ways hard to express in JPQL, or needs a centralized definition for a reusable SQL query. In return, the query is more tightly coupled to the schema and dialect, so it must be tested against the application's actual database.

## 1. What is a named native query?

A named native query is an SQL statement preregistered with a unique name in the persistence unit. Once registered, the application invokes the query by name rather than rewriting the SQL string in every service.

Example:

```java
@Entity
@Table(name = "purchase_orders")
@NamedNativeQuery(
    name = "PurchaseOrder.findRecent",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class
)
public class PurchaseOrder {
    // Entity mapping
}
```

There are two distinct parts:

- `name` is the logical name of the named query in JPA. This name is used when calling `EntityManager.createNamedQuery(...)`.
- `query` is the actual SQL statement executed by the database. It uses physical table and column names.

`@NamedNativeQuery` belongs to Jakarta Persistence, typically in the `jakarta.persistence` package in Spring Boot 3.x. You can declare a single query on an entity using `@NamedNativeQuery`, or multiple queries using the `@NamedNativeQueries` container.

The named query name must be unique within the persistence unit. An easy-to-manage convention is `EntityName.purposeName`, such as `PurchaseOrder.findRecent` or `PurchaseOrder.findByStatus`. This is an application naming convention, not a table name or Spring bean name.

## 2. How does @NamedNativeQuery differ from @NamedQuery?

Both annotations declare named queries, but their query languages differ:

| Criterion | @NamedQuery | @NamedNativeQuery |
|---|---|---|
| Language | JPQL | Native SQL |
| Identifiers in query | Entity name and Java properties | Table name and column names |
| Database dependency | Lower, based on JPA/provider | Higher, based on dialect and schema |
| Access to DB-specific features | Limited to JPQL | Can use functions, CTEs, window functions, proprietary syntax |
| Result mapping | Entity or JPQL results | Entity, scalar, or native result mapping |
| Database portability | Generally easier | May require rewriting SQL |

JPQL example:

```java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = """
        SELECT p
        FROM PurchaseOrder p
        WHERE p.status = :status
        ORDER BY p.createdAt DESC
        """
)
```

JPQL references the `PurchaseOrder` entity and properties `status` and `createdAt`.

The same idea in native SQL:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class
)
```

Native SQL references `purchase_orders`, `order_number`, `customer_id`, and `created_at`. If the schema renames a table or column, the native query must be updated accordingly.

## 3. Declaring a @NamedNativeQuery that returns an entity

When you want the result to be an entity, use the `resultClass` attribute:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultClass = PurchaseOrder.class
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
    }
}
```

The example is a simplified mapping to focus on the named native query. In a real application, if `customer_id` is mapped as a `@ManyToOne` association, use `@JoinColumn(name = "customer_id")` and select the appropriate columns in SQL.

When using `resultClass = PurchaseOrder.class`, the provider maps each result row into an entity according to the PurchaseOrder mapping. The SQL statement must return the columns needed by the entity, with column names or aliases matching the mapping. For entities with many properties, embedded values, relationships, or inheritance, you must ensure the result contains all data required by the mapping. Returning only a few columns and asking the provider to construct a complete entity can lead to undefined results or mapping errors.

Do not use an entity as a DTO just to avoid declaring result mappings. Entities are managed by identity and the persistence context; if you only need a few columns for displaying reports, use scalar or DTO mapping.

## 4. Calling a named native query with EntityManager

JPA provides `createNamedQuery` to invoke a registered query:

```java
@Repository
public class PurchaseOrderLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public List<PurchaseOrder> findByStatus(String status) {
        return entityManager
            .createNamedQuery(
                "PurchaseOrder.findByStatusNative",
                PurchaseOrder.class
            )
            .setParameter(1, status)
            .getResultList();
    }
}
```

With native SQL, positional parameter binding is the portable option under JPA. In the SQL string declared in `@NamedNativeQuery`, use question marks `?`; when calling `setParameter`, positions start at 1. For example, `WHERE status = ?` corresponds to `.setParameter(1, status)`.

Some providers such as Hibernate also support named parameter binding for native SQL, but that may be a provider-specific extension. If you need JPA portability, use positional parameters for native queries.

Do not concatenate input values directly into SQL:

```java
// Unsafe: user input is concatenated into the SQL statement.
String sql = "SELECT * FROM purchase_orders WHERE status = '"
        + status + "'";
```

Bind parameters instead:

```java
query.setParameter(1, status);
```

Parameter binding prevents values from being interpreted as SQL syntax and helps the database/provider manage data types. Parameters cannot replace table names, column names, or SQL keywords. If you need to choose a sort column dynamically, use a controlled list of allowed identifiers in code; never take arbitrary column names from a request and concatenate them into the query.

## 5. Mapping results to a DTO with @SqlResultSetMapping

Not every query should return an entity. For example, a reporting screen might only need the order number and total amount. You can use `@SqlResultSetMapping` combined with `@ConstructorResult` to map each SQL row into a DTO constructor.

DTO:

```java
public class OrderSummary {

    private final String orderNumber;
    private final BigDecimal totalAmount;

    public OrderSummary(
            String orderNumber,
            BigDecimal totalAmount
    ) {
        this.orderNumber = orderNumber;
        this.totalAmount = totalAmount;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Mapping declaration on the entity:

```java
@Entity
@Table(name = "purchase_orders")
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "order_number", type = String.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
@NamedNativeQuery(
    name = "PurchaseOrder.findSummariesByStatus",
    query = """
        SELECT order_number, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultSetMapping = "OrderSummaryMapping"
)
public class PurchaseOrder {
    // Entity mapping
}
```

Calling the query:

```java
@SuppressWarnings("unchecked")
public List<OrderSummary> findSummariesByStatus(String status) {
    return entityManager
        .createNamedQuery("PurchaseOrder.findSummariesByStatus")
        .setParameter(1, status)
        .getResultList();
}
```

Rules to follow:

- `resultSetMapping` must match the exact name of `@SqlResultSetMapping`.
- `@ConstructorResult.targetClass` is the DTO to instantiate.
- Each `@ColumnResult` is passed to the constructor in the exact order declared.
- The name in `@ColumnResult(name = ...)` must match the column name or alias returned by SQL.
- Data types must be compatible with the DTO constructor and the actual JDBC types.

You should assign explicit aliases to expressions or duplicate column names:

```sql
SELECT
    p.order_number AS order_number,
    SUM(i.quantity * i.unit_price) AS total_amount
FROM purchase_orders p
JOIN order_items i ON i.order_id = p.id
GROUP BY p.order_number
```

When using aggregates or expressions, stable aliases help `@ColumnResult` clearly identify columns. Alias names and case-sensitivity rules can be affected by the database; test against your actual database engine.

## 6. Other forms of result mapping

JPA provides several ways to map native results:

| Mapping | Purpose |
|---|---|
| `resultClass` | Maps results to an entity or compatible result class |
| `resultSetMapping` | References a mapping declared with @SqlResultSetMapping |
| `@EntityResult` | Maps an entity from result columns |
| `@FieldResult` | Explicitly specifies the SQL column corresponding to an entity field/property |
| `@ColumnResult` | Extracts a scalar column from the result set |
| `@ConstructorResult` | Instantiates a DTO via its constructor from mapped columns |

For example, a single result set can return multiple types of information:

```java
@SqlResultSetMapping(
    name = "OrderAndCustomerMapping",
    entities = {
        @EntityResult(entityClass = PurchaseOrder.class),
        @EntityResult(entityClass = Customer.class)
    }
)
```

When using `@EntityResult` for multiple entities in the same result set, ensure the SQL returns the necessary columns for each entity and column names are unambiguous. If both entities have an `id` column, alias them separately and declare corresponding `@FieldResult` entries so the provider can distinguish the columns.

If the result consists only of simple scalars, you can use `@ColumnResult`. If the result is a DTO, `@ConstructorResult` is usually clearer than returning `Object[]` and manually casting in the service.

## 7. Named native queries for UPDATE and DELETE

`@NamedNativeQuery` can also define data-modifying SQL statements. When invoking them, use `executeUpdate()`:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.expireOldDrafts",
    query = """
        UPDATE purchase_orders
        SET status = 'EXPIRED'
        WHERE status = 'DRAFT'
          AND created_at < ?
        """
)
```

Execution:

```java
@Transactional
public int expireOldDrafts(Instant cutoff) {
    return entityManager
        .createNamedQuery("PurchaseOrder.expireOldDrafts")
        .setParameter(1, Timestamp.from(cutoff))
        .executeUpdate();
}
```

This example assumes the `created_at` column is stored as a timestamp compatible with JDBC `Timestamp`; how temporal values are bound should be verified against your actual database, JDBC driver, and column type. With native SQL, do not assume every Java type is converted the same way as in JPQL.

Native UPDATE/DELETE statements act directly on the database, do not invoke setters on individual entities, and do not trigger lifecycle callbacks like updating or deleting entities individually through EntityManager. The persistence context may still hold stale entities. If you need to continue using related entities, flush before the query when pending changes need synchronization, then clear or refresh as appropriate.

This is also why you must be careful when running bulk SQL inside a transaction that holds many managed entities. An in-memory entity may no longer reflect database state after a native UPDATE statement.

## 8. Pagination and sorting with native queries

A named native query usually has a fixed ordering in SQL. You can limit results directly with the Query API:

```java
List<PurchaseOrder> page = entityManager
    .createNamedQuery(
        "PurchaseOrder.findByStatusNative",
        PurchaseOrder.class
    )
    .setParameter(1, "PAID")
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

`setFirstResult` uses a 0-based offset; `setMaxResults` sets the maximum number of rows. How the provider translates these limits into SQL depends on the dialect.

If you need a Page with a total record count, you must provide a separate count query or an appropriate way to compute the total. `@NamedNativeQuery` does not automatically derive a count query from the base SQL. With a Spring Data repository, when declaring a native query returning a Page, you must provide an explicit `countQuery` if the query is complex or Spring Data cannot infer it accurately.

Dynamic sorting also requires caution. Sort values are SQL identifiers, not ordinary bind parameters. Restrict sort options using a whitelist and build controlled SQL, or declare separate named queries for key sort orders. Never concatenate sort strings directly from a request into SQL.

## 9. Calling named queries through a Spring Data repository

Spring Data JPA can look up named queries by naming convention:

```text
EntityName.repositoryMethodName
```

Example query declaration:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findByStatusNative",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        WHERE status = ?
        ORDER BY created_at DESC, id DESC
        """,
    resultClass = PurchaseOrder.class
)
```

Repository with matching method:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatusNative(String status);
}
```

Spring Data can look up the named query by entity name and method name. Ensure the query name matches the convention exactly and test on the Spring Data JPA version you are using. If the method has an explicit `@Query`, that declaration usually takes precedence over convention-based named query lookup.

For DTO mapping via `@SqlResultSetMapping`, calling directly via EntityManager makes the JPA mapping explicit and keeps result types easy to control. If you want a Spring Data repository to return a DTO from a named native query, verify how your project's Spring Data version handles result mappings and return types; do not assume every complex mapping can be inferred automatically from the method signature.

## 10. Putting named queries in annotations or orm.xml?

There are two common approaches:

- Declare directly with `@NamedNativeQuery` on the entity class.
- Declare metadata in `orm.xml`.

Use annotations when the query is tightly coupled to the entity and you want mappings and queries close together. Use orm.xml when you want to separate metadata from Java source, manage mappings centrally, or avoid modifying entity classes.

If declaring multiple named native queries via annotations, use the container:

```java
@NamedNativeQueries({
    @NamedNativeQuery(
        name = "PurchaseOrder.findRecent",
        query = "SELECT id, order_number FROM purchase_orders",
        resultSetMapping = "OrderSummaryMapping"
    ),
    @NamedNativeQuery(
        name = "PurchaseOrder.findPaid",
        query = """
            SELECT id, order_number, customer_id, status,
                   created_at, total_amount
            FROM purchase_orders
            WHERE status = 'PAID'
            """,
        resultClass = PurchaseOrder.class
    )
})
```

In a real example, the first query must reference an existing result mapping and the SQL must return all columns required by that mapping. Never let two named queries share the same name within the same persistence unit; duplicate names can prevent the application from starting or cause provider mapping errors.

## 11. Query hints and timeouts

`@NamedNativeQuery` supports declaring query hints through the `hints` attribute. For example, you can set a standard JPA timeout:

```java
@NamedNativeQuery(
    name = "PurchaseOrder.findRecent",
    query = """
        SELECT id, order_number, customer_id, status,
               created_at, total_amount
        FROM purchase_orders
        ORDER BY created_at DESC
        """,
    resultClass = PurchaseOrder.class,
    hints = {
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "5000"
        )
    }
)
```

The standard timeout hint is measured in milliseconds. Providers or databases may not support every hint or may interpret certain hints differently. A query timeout does not replace a transaction timeout, connection timeout, or request time limit. Verify behavior on your deployed provider and driver.

Do not add optimization hints arbitrarily just because a query runs slowly. First inspect the execution plan, indexes, number of rows returned, and volume of data being mapped.

## 12. Native queries and portability

Native SQL depends on the schema and database:

- Date/time functions, JSON, arrays, operators, and pagination syntax vary across database systems.
- Identifier names and quoting rules can differ.
- Data types such as UUID, JSONB, timestamp with time zone, or boolean may bind differently.
- CTEs, window functions, lateral joins, and specialized features are not supported identically across all databases.
- JDBC drivers can affect how data types are bound and how results are read.

Use native queries when the benefit is clear, such as needing window functions or optimizing a measured reporting query. If JPQL can express the requirement with adequate performance, JPQL is usually easier to maintain and migrate across databases.

A native query does not automatically make a query faster. The database still must execute joins, filters, sorts, aggregates, and data reads. Hand-written SQL can be even slower than provider-generated queries if indexes are missing or the query plan is poor.

## 13. Security and input control

Always bind values instead of concatenating strings:

```java
Query query = entityManager.createNamedQuery(
    "PurchaseOrder.findByStatusNative"
);
query.setParameter(1, status);
```

Do not do the following:

```java
String sql = "SELECT * FROM purchase_orders WHERE status = '"
        + userInput + "'";
```

Beyond SQL injection, you must enforce access control at the business layer. Just because a native query can read a table does not mean every user is allowed to read every record. Add tenant/customer/owner conditions if your security model requires them, and ensure callers cannot bypass those conditions arbitrarily.

Table names, column names, schemas, and sort directions cannot be bound as ordinary parameter values. If dynamic selection is needed, map input through a fixed whitelist and construct queries only from controlled identifiers.

## 14. Testing named native queries

Native SQL should be tested against the same type of database as production. H2 can be helpful for fast tests, but it does not guarantee compatibility with PostgreSQL, MySQL, Oracle, or SQL Server regarding dialect, data types, identifiers, functions, and pagination.

Testing checklist:

1. Application context discovers the named query and initializes mappings successfully.
2. The query name is invoked accurately and has no duplicates in the persistence unit.
3. SQL uses the exact table/column/schema names from migrations.
4. Parameters are bound at the right positions and JDBC types.
5. Entity results include all mapped columns.
6. DTO constructors receive matching column order, alias names, and data types.
7. Nulls, aggregates, duplicate column names, and empty data are handled properly.
8. Pagination, sorting, and count queries return accurate results.
9. UPDATE/DELETE returns the expected row count and the persistence context is synchronized.
10. Queries with authorization/tenant filters cannot be bypassed.

Integration test example:

```java
@DataJpaTest
class PurchaseOrderNativeQueryTest {

    @Autowired
    EntityManager entityManager;

    @Test
    void findsPaidOrdersUsingNamedNativeQuery() {
        List<PurchaseOrder> orders = entityManager
            .createNamedQuery(
                "PurchaseOrder.findByStatusNative",
                PurchaseOrder.class
            )
            .setParameter(1, "PAID")
            .getResultList();

        assertThat(orders)
            .allMatch(order -> "PAID".equals(order.getStatus()));
    }
}
```

This is an illustrative skeleton; test data must be seeded according to your actual constraints and mappings. If a test slice does not automatically pick up entities or mappings located in another configuration, import the proper persistence configuration. For database-dependent native SQL, prefer Testcontainers or an integration environment running the same database engine.

## 15. Common pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Named query not found | Called with wrong name or query not registered in persistence unit | Verify name and entity scan/orm.xml |
| SQL reports missing table/column | Used property/entity name instead of physical name or wrong schema | Check migrations and table/column mappings |
| Entity result missing fields or mapping error | SELECT does not return enough columns for the entity | Select all required columns or use DTO result mapping |
| DTO receives wrong data | Mismatched alias, constructor order, or ColumnResult type | Match SQL aliases and constructor |
| Parameters fail to bind | Wrong position or non-portable named parameter | Use `?` and positional setParameter |
| Native query works on one DB but fails on another | SQL uses dialect-specific functions | Write dialect-compatible queries or split implementations |
| Query returns stale entity after native UPDATE | Persistence context still holds old state | Flush before and clear/refresh afterward as needed |
| Page missing total | No corresponding count query | Declare a separate count query |
| Sort causes SQL errors or injection risk | Concatenating identifiers from request | Use a whitelist or fixed queries |
| Application fails at startup | Duplicate query names or invalid mapping metadata | Check all named queries and result mappings |

## 16. Practice exercises

1. Declare `PurchaseOrder.findByStatusNative` with @NamedNativeQuery and return PurchaseOrder.
2. Call the named query using EntityManager.createNamedQuery and bind status as a positional parameter.
3. Rename a column in a test migration to observe mapping/native SQL errors.
4. Write an OrderSummary DTO and map it using @SqlResultSetMapping + @ConstructorResult.
5. Use explicit aliases for aggregates and verify ColumnResult receives the right types.
6. Write a named native UPDATE, call executeUpdate inside a transaction, and check affected row count.
7. Observe the persistence context after a native UPDATE; try flush/clear/refresh in the right scenarios.
8. Add pagination using setFirstResult/setMaxResults and a separate count query.
9. Run the query against a production-equivalent database via Testcontainers.
10. Compare the same use case using JPQL vs. native SQL; measure execution plans and explain why you chose one approach.

**Core principle:** @NamedNativeQuery assigns a name to native SQL for reuse across the persistence unit. Use resultClass when mapping complete entities; use @SqlResultSetMapping when you need DTOs, scalars, or multiple entities. Bind parameters portably, use accurate physical table/column names, control dynamic identifiers, and test against the target database. Native SQL gives greater control, while demanding stricter management of schemas, dialects, and result mappings.