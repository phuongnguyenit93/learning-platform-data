# Stored Procedures, Native Queries, and ORM Abstraction Limits

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Spring Boot and JPA  
> **Objective:** Know when to use JPQL, native SQL, or stored procedures in Spring Boot/JPA applications; invoke Oracle procedures and packages via Spring Data JPA, `EntityManager`, and JDBC; map IN/OUT parameters, REF CURSORs, and multi-result sets; understand ORM limits for Oracle-specific SQL, bulk DML, locking, and non-entity data; manage flush, persistence context, transactions, mapping, security, and portability.

## 1. What Does ORM Abstract Away?

JPA is the Jakarta Persistence specification, providing an entity management model and persistence context. Hibernate is the standard JPA provider in Spring Boot. Spring Data JPA adds a repository abstraction to cut boilerplate data-access code.

ORM lets applications work with objects instead of hand-writing every SQL statement:

- Entities map to tables or views.
- Fields map to columns.
- Relationships are modeled as associations.
- The persistence context tracks loaded and mutated entities.
- Dirty checking emits DML on flush.
- JPQL queries over entities and properties.
- Transactions coordinate data changes.

ORM does not eliminate SQL or database characteristics. When window functions, optimizer hints, CTEs, JSON operators, packages, stored procedures, bulk updates, or plan control are needed, the abstraction may stop fitting cleanly.

**Pick the abstraction to match the query's needs and how data is consumed.** JPQL fits entity-level operations; native SQL fits full SQL control; stored procedures fit logic or operations encapsulated and governed inside the database.

## 2. Three Data Access Approaches to Distinguish

| Approach | Unit of Work | Best Fit | Trade-Offs |
|---|---|---|---|
| JPQL / Criteria API | Entities, associations, attributes | Standard CRUD and routine business queries | Cannot express every Oracle feature |
| Native SQL | Tables, views, SQL expressions | Specialized queries, analytics, hints, CTEs, Oracle tuning | Tied to schema/dialect; more manual mapping |
| Stored procedures/packages | Procedures/functions and parameter contracts | DB-shared logic, bulk operations, integration with external systems | Harder debugging/versioning/deployment and lower portability |

This is not a ranking from good to bad. One system can use all three behind clear boundaries.

### 2.1. JPQL

JPQL references Java entities and fields rather than raw table/column names:

~~~java
@Query("""
    select o
    from OrderEntity o
    where o.customerId = :customerId
      and o.status = :status
    order by o.createdAt desc
    """)
List<OrderEntity> findOrders(
    @Param("customerId") Long customerId,
    @Param("status") OrderStatus status
);
~~~

The provider translates JPQL to dialect-specific SQL. When changing databases or schema mappings, JPQL often needs fewer edits than native SQL, while remaining bounded by JPA provider and database capabilities.

### 2.2. Native Queries

A native query is raw SQL sent to the database, typically using physical table and column names:

~~~java
@Query(value = """
    select order_id, customer_id, status, created_at
    from orders
    where customer_id = :customerId
    order by created_at desc
    fetch first :rowLimit rows only
    """, nativeQuery = true)
List<Object[]> findRecentOrders(
    @Param("customerId") Long customerId,
    @Param("rowLimit") int rowLimit
);
~~~

Syntax like `FETCH FIRST` is specific to supporting Oracle releases. Parameter binding in row-limiting clauses and native pagination must be tested on your exact Hibernate/Oracle JDBC version.

Native SQL gives greater control while shifting responsibility for column mapping, data types, NULLs, paging, locking, and persistence-context synchronization onto the application.

### 2.3. Stored Procedures

Stored procedures run logic inside the database. In Oracle, procedures and functions are normally organized inside PL/SQL packages:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    );
END order_api;
/
~~~

Applications call packages via JPA `StoredProcedureQuery`, Spring Data `@Procedure`, or JDBC `CallableStatement`.

Procedures help when logic is shared across clients, performs bulk operations, or leverages PL/SQL. Moving logic into the database also introduces dependencies on schemas, package versions, `EXECUTE` privileges, and deployment workflows.

## 3. Deciding Between JPQL, Native SQL, and Stored Procedures

Ask these questions:

1. Does the query simply filter/sort ordinary entities and associations? Prefer JPQL or Criteria.
2. Are analytic/window functions, optimizer hints, Oracle SQL features, or specific access paths required? Native SQL may fit.
3. Must multiple applications share the logic, or must heavy bulk work run inside the database? Consider packages/procedures.
4. Must the query return managed entities in the persistence context? JPQL is cleaner; native entity mapping needs care.
5. Does the query mutate data outside already-loaded entities? Handle `flush`/`clear`/cache explicitly.
6. Is multi-database portability required? Avoid DB-specific SQL/PL/SQL or isolate it behind adapters.
7. Are strict privilege boundaries required? Package APIs can restrict direct table DML, provided definer/invoker rights are designed safely.
8. Must operations share an atomic transaction with other JPA writes? Verify the same DataSource, transaction manager, and connection are used.

### 3.1. Example Tool Selection

| Use Case | Common Appropriate Choice |
|---|---|
| Find orders by customer and status | JPQL |
| Top-N per group using Oracle analytic functions | Native SQL |
| Update thousands of order statuses via shared DB rules | Package procedure |
| Tax calculation function shared across systems | Function/package or service per architecture |
| Multi-table aggregate report tuned with hints | Native SQL |
| Create new entities and manage lifecycle | JPA `persist` |
| Mass delete by broad predicate | JPQL bulk DML or native SQL, with context clear |
| Orchestrate workflows with external side effects | Application service; avoid stuffing everything into procedures unnecessarily |

Never pick a stored procedure merely because a query looks long. Equally, never force every operation through repository abstractions when ORM cannot cleanly express required semantics.

## 4. Declaring Procedures in Oracle

Example package with a procedure updating status and returning a result:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    )
    IS
    BEGIN
        UPDATE orders
           SET status = 'CLOSED'
         WHERE order_id = p_order_id
           AND status = 'OPEN';

        IF SQL%ROWCOUNT = 1 THEN
            p_result := 'CLOSED';
        ELSE
            p_result := 'NOT_UPDATED';
        END IF;
    END close_order;
END order_api;
/
~~~

The package specification is the public contract; the body is the implementation. Applications depend on package name, procedure name, parameter order/types, and result semantics.

### 4.1. Transactions Inside Procedures

The procedure above does not call `COMMIT` or `ROLLBACK`. The calling application owns the transaction, so the procedure joins the same transaction as surrounding JPA operations.

This is usually the more flexible design: the service layer decides commit or rollback.

If a procedure issues its own `COMMIT`, it breaks application-expected atomicity. A service calling two repository methods and a procedure may assume everything rolls back on error, yet the procedure's internal `COMMIT` makes its changes permanent.

Certain operational workflows intentionally manage transactions inside the database, but those contracts must be documented explicitly and never mixed blindly with Spring-managed transactions.

### 4.2. EXECUTE Privileges

The application schema needs `EXECUTE` privilege on the package:

~~~sql
GRANT EXECUTE ON data_owner.order_api TO app_user;
~~~

When a package runs with `AUTHID DEFINER`, the owner must hold direct privileges on referenced objects. Never rely on caller roles for SQL inside definer-rights stored code.

The application does not necessarily need direct `UPDATE` on `ORDERS` if all writes go through the package API. This creates a clean privilege boundary, provided the package validates inputs and enforces authorization.

## 5. Calling Procedures with Spring Data JPA @Procedure

Spring Data JPA supports declaring repository methods with `@Procedure`. This works cleanly for simple parameters and scalar results.

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Procedure(
        procedureName = "ORDER_API.CLOSE_ORDER"
    )
    String closeOrder(
        @Param("P_ORDER_ID") Long orderId
    );
}
~~~

Procedure and parameter name mapping depends on database, JPA provider, and Spring Data JPA version. For Oracle packages, verify how the provider passes the procedure name to JDBC and how the driver handles call syntax.

If a procedure has one `OUT` parameter and the method returns a single value, Spring Data maps it when configured appropriately. For multiple `OUT` parameters, `REF CURSOR`s, or complex results, `EntityManager` `StoredProcedureQuery` or JDBC is usually clearer.

### 5.1. Using @NamedStoredProcedureQuery

You can declare procedure mappings on an entity:

~~~java
@Entity
@Table(name = "ORDERS")
@NamedStoredProcedureQuery(
    name = "OrderEntity.closeOrder",
    procedureName = "ORDER_API.CLOSE_ORDER",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "P_ORDER_ID",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "P_RESULT",
            type = String.class
        )
    }
)
public class OrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;

    // Other mapped fields
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Procedure(name = "OrderEntity.closeOrder")
    String closeOrder(@Param("P_ORDER_ID") Long orderId);
}
~~~

For procedures with multiple `OUT` parameters, results may need to be read via `StoredProcedureQuery` instead of a single return value. Names and return mappings must match the procedure contract.

Providers vary in parameter naming, procedure naming, schema/package qualification, and cursor mapping. Test with the exact Oracle dialect and driver you deploy.

## 6. Calling Procedures with EntityManager StoredProcedureQuery

The `EntityManager` API lets you register individual parameters and retrieve outputs.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public String closeOrder(long orderId) {
    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
            "ORDER_API.CLOSE_ORDER"
        );

    query.registerStoredProcedureParameter(
        "P_ORDER_ID",
        Long.class,
        ParameterMode.IN
    );

    query.registerStoredProcedureParameter(
        "P_RESULT",
        String.class,
        ParameterMode.OUT
    );

    query.setParameter("P_ORDER_ID", orderId);
    query.execute();

    return (String) query.getOutputParameterValue("P_RESULT");
}
~~~

Imports use `jakarta.persistence` for modern Spring Boot/Jakarta stacks. Spring Boot 2/JPA 2 projects typically use `javax.persistence`. Never mix `javax` and `jakarta` in the same application; align with your Spring Boot, Hibernate, and dependency versions.

### 6.1. Positional Parameter Registration

JPA supports registering by position:

~~~java
query.registerStoredProcedureParameter(
    1,
    Long.class,
    ParameterMode.IN
);
~~~

Parameter names or positions must fit the provider and driver. With Oracle packages, named binding is easier to read, though you should inspect the call statement emitted by the provider.

### 6.2. IN, OUT, and INOUT

| Mode | Meaning | Example |
|---|---|---|
| `IN` | Application passes value in | Order ID |
| `OUT` | Procedure passes value out | Result code |
| `INOUT` | Application passes value in and receives updated value | Counter or status |
| `REF_CURSOR` | Procedure returns a cursor/result set | List of rows |

`INOUT` example:

~~~sql
PROCEDURE adjust_counter(
    p_counter IN OUT NUMBER
);
~~~

JPA registers `ParameterMode.INOUT` and sets the initial value. After `execute()`, read the output parameter via supported API/provider methods.

### 6.3. Output Parameters and Execution Order

For procedures with `OUT` parameters, execute the procedure first before reading outputs. Some procedures return both update counts and result sets; retrieval order can depend on the JDBC driver and provider.

Review JPA docs and test multi-result cases. Never assume every stored procedure returns only a single result.

## 7. Oracle REF CURSOR

Oracle PL/SQL can return query results via `SYS_REFCURSOR`:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE find_orders(
        p_customer_id IN NUMBER,
        p_result      OUT SYS_REFCURSOR
    );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE find_orders(
        p_customer_id IN NUMBER,
        p_result      OUT SYS_REFCURSOR
    )
    IS
    BEGIN
        OPEN p_result FOR
            SELECT order_id,
                   customer_id,
                   status,
                   created_at
              FROM orders
             WHERE customer_id = p_customer_id
             ORDER BY created_at DESC;
    END find_orders;
END order_api;
/
~~~

A `REF CURSOR` is a database-returned cursor consumed by JDBC/providers as a result set according to driver capabilities.

### 7.1. REF_CURSOR with JPA

JPA supports `ParameterMode.REF_CURSOR` in supporting releases. Example:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "ORDER_API.FIND_ORDERS",
        "OrderSummaryMapping"
    );

query.registerStoredProcedureParameter(
    "P_CUSTOMER_ID",
    Long.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "P_RESULT",
    void.class,
    ParameterMode.REF_CURSOR
);

query.setParameter("P_CUSTOMER_ID", customerId);
query.execute();

@SuppressWarnings("unchecked")
List<OrderSummary> rows = query.getResultList();
~~~

`REF CURSOR` mapping depends on JPA provider, Hibernate version, Oracle dialect, and Oracle JDBC driver. Registering cursors positionally or using Oracle-specific JDBC types may be needed—check documentation for your exact runtime stack.

If the provider does not cleanly match the contract or multiple cursors must be handled, JDBC `CallableStatement` is often more transparent.

### 7.2. REF CURSOR Is Not Automatically an Entity

Result sets returned by procedures do not automatically map to managed entities. For projections or reports, use DTO mappings. When mapping to entities, ensure all primary key and required mapped columns are present; entities may enter the persistence context per provider rules.

Never return partial entities missing keys or required columns and expect Hibernate to manage their lifecycle properly.

## 8. Calling Oracle Packages with JDBC CallableStatement

When JDBC-specific control is needed, use `CallableStatement` on a connection managed by the transaction manager.

Scalar `OUT` example:

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public String closeOrder(long orderId) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         CallableStatement call =
             connection.prepareCall(
                 "{ call ORDER_API.CLOSE_ORDER(?, ?) }"
             )) {

        call.setLong(1, orderId);
        call.registerOutParameter(2, Types.VARCHAR);
        call.execute();

        return call.getString(2);
    }
}
~~~

This snippet illustrates fetching a connection directly from `DataSource`. In a Spring transaction-managed app, obtain the connection in a transaction-synchronized way—such as via `JdbcTemplate` or transaction-aware DataSource integration. Never grab an independent connection if the procedure must share a transaction with JPA repositories.

### 8.1. Using JdbcTemplate

Spring's `JdbcTemplate` manages JDBC resources (`PreparedStatement`/`CallableStatement`) and integrates with the transaction manager when sharing the DataSource.

~~~java
public String closeOrder(long orderId) {
    return jdbcTemplate.execute(
        "{ call ORDER_API.CLOSE_ORDER(?, ?) }",
        (CallableStatementCallback<String>) call -> {
            call.setLong(1, orderId);
            call.registerOutParameter(2, Types.VARCHAR);
            call.execute();
            return call.getString(2);
        }
    );
}
~~~

`JdbcTemplate` fits when direct JDBC control is needed while letting Spring manage resources and transactions.

### 8.2. CallableStatement Returning REF CURSOR

Oracle JDBC supports `REF CURSOR` through Oracle JDBC APIs. Example with the Oracle driver:

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Types;
import oracle.jdbc.OracleTypes;

try (CallableStatement call =
         connection.prepareCall(
             "{ call ORDER_API.FIND_ORDERS(?, ?) }")) {

    call.setLong(1, customerId);
    call.registerOutParameter(2, OracleTypes.CURSOR);
    call.execute();

    try (ResultSet resultSet = (ResultSet) call.getObject(2)) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("ORDER_ID");
            String status = resultSet.getString("STATUS");
            // Map to DTO
        }
    }
}
~~~

`OracleTypes.CURSOR` is an Oracle-specific extension. Constants/APIs can vary by JDBC driver version; check Oracle JDBC documentation. Always read and close the `ResultSet` before closing the `CallableStatement` or `Connection`.

## 9. Native Queries in Spring Data JPA

Native queries are commonly declared with `@Query(nativeQuery = true)`:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query(
        value = """
            select order_id,
                   customer_id,
                   status,
                   created_at
              from orders
             where customer_id = :customerId
               and status = :status
             order by created_at desc
            """,
        nativeQuery = true
    )
    List<Object[]> findOrderRows(
        @Param("customerId") Long customerId,
        @Param("status") String status
    );
}
~~~

`Object[]` results lack type safety. Every array index depends on `SELECT` column order; changing the projection can silently break mapping without compiler errors.

Use DTOs/projections whenever possible.

### 9.1. Interface Projections

Interface projection example:

~~~java
public interface OrderRowView {
    Long getOrderId();
    Long getCustomerId();
    String getStatus();
}
~~~

The query must alias columns to match getter properties per Spring Data/provider support:

~~~java
@Query(
    value = """
        select order_id as orderId,
               customer_id as customerId,
               status as status
          from orders
         where customer_id = :customerId
        """,
    nativeQuery = true
)
List<OrderRowView> findOrderView(
    @Param("customerId") Long customerId
);
~~~

Oracle may normalize unquoted alias casing to uppercase. Spring Data/Hibernate typically resolves aliases per its projection strategy, though integration testing is essential. Never assume every driver preserves camelCase aliases verbatim.

### 9.2. DTO Projections

Use constructor mappings or `@SqlResultSetMapping` depending on provider/version. DTOs fit aggregate/reporting queries that do not represent a single entity.

Never force aggregate reports into entity classes merely to use generic repository methods.

## 10. EntityResult and ConstructorResult

JPA provides `@SqlResultSetMapping` to define native query result mappings.

DTO example:

~~~java
public class OrderSummary {
    private final Long orderId;
    private final String status;
    private final java.math.BigDecimal amount;

    public OrderSummary(
            Long orderId,
            String status,
            java.math.BigDecimal amount) {
        this.orderId = orderId;
        this.status = status;
        this.amount = amount;
    }

    public Long getOrderId() { return orderId; }
    public String getStatus() { return status; }
    public java.math.BigDecimal getAmount() { return amount; }
}
~~~

Mapping declaration:

~~~java
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "ORDER_ID", type = Long.class),
            @ColumnResult(name = "STATUS", type = String.class),
            @ColumnResult(name = "TOTAL_AMOUNT", type = java.math.BigDecimal.class)
        }
    )
)
@Entity
@Table(name = "ORDERS")
public class OrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;
}
~~~

Usage:

~~~java
Query query = entityManager.createNativeQuery(
    """
    select order_id,
           status,
           total_amount
      from orders
     where customer_id = :customerId
    """,
    "OrderSummaryMapping"
);

query.setParameter("customerId", customerId);

@SuppressWarnings("unchecked")
List<OrderSummary> rows = query.getResultList();
~~~

`ColumnResult` names must match `ResultSet` aliases/labels. For Oracle `NUMBER`, precision/scale and JDBC types affect Java mapping; `BigDecimal` is safer than `double` for monetary values.

### 10.1. EntityResult

When a native query returns all mapped entity columns cleanly:

~~~java
@SqlResultSetMapping(
    name = "OrderEntityMapping",
    entities = @EntityResult(
        entityClass = OrderEntity.class,
        fields = {
            @FieldResult(name = "id", column = "ORDER_ID"),
            @FieldResult(name = "status", column = "STATUS")
        }
    )
)
~~~

In practice, `EntityResult` normally requires all mapped columns—including the identifier and required fields per entity/provider. Associations, discriminators, versions, and embedded fields add complexity.

When only a few fields are needed, DTO projections are clearer and avoid placing incomplete entities into the persistence context.

## 11. Native Queries with Oracle-Specific SQL

Native SQL shines when queries need Oracle features that JPQL cannot express directly.

### 11.1. Analytic Functions

Example ranking orders per customer:

~~~sql
SELECT order_id,
       customer_id,
       total_amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY created_at DESC, order_id DESC
       ) AS rn
FROM orders;
~~~

Run this in a native repository query and map to a DTO. JPQL supports a limited function set, whereas analytic functions and Oracle-specific syntax typically call for native SQL or provider extensions.

### 11.2. Common Table Expressions

~~~sql
WITH recent_orders AS (
    SELECT order_id,
           customer_id,
           created_at,
           total_amount
    FROM orders
    WHERE created_at >= :fromTime
)
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM recent_orders
GROUP BY customer_id;
~~~

CTEs organize multi-step queries, recursive queries, and complex logic. Syntax and optimization depend on the Oracle release.

### 11.3. Optimizer Hints

~~~sql
SELECT /*+ INDEX(o IDX_ORDERS_CUSTOMER_CREATED) */
       o.order_id,
       o.created_at
FROM orders o
WHERE o.customer_id = :customerId;
~~~

Hints are directives to the optimizer, not guarantees of a specific plan. Use hints only after inspecting execution plans and benchmarking; stale hints can hurt performance when data distributions or schemas evolve.

### 11.4. JSON and Oracle Functions

Native SQL can use `JSON_VALUE`, `JSON_TABLE`, `JSON_EXISTS`, or other Oracle functions depending on release. Verify data types, JSON validation, indexing strategies, and return types.

Isolate these queries in dedicated repositories/DAOs so services do not couple to raw SQL syntax.

## 12. Native DML and the Persistence Context

This is one of the most important ORM boundaries.

Hibernate tracks entities loaded into the persistence context. When using entity setters, dirty checking knows the entity changed. However, native SQL or JPQL bulk DML runs directly against the database without updating Java entity objects sitting in memory.

Example:

~~~java
OrderEntity order = entityManager.find(OrderEntity.class, orderId);

// Native SQL updates status in the database.
entityManager.createNativeQuery(
    "update orders set status = 'CLOSED' where order_id = :id"
).setParameter("id", orderId)
 .executeUpdate();

// The order object may still hold the old status in the persistence context.
~~~

After bulk/native DML, already-loaded entities can become stale. Re-reading the same entity in the same persistence context may return the cached managed object rather than querying the database again.

### 12.1. Flush Before Native Queries When Needed

If entity changes are pending unflushed, a native query may need to observe those changes. Call:

~~~java
entityManager.flush();
~~~

`flush()` pushes pending persistence-context changes to the database within the current transaction. Flush does not mean commit.

Hibernate has specific query flush modes and synchronization behaviors for native queries. For clarity, flush explicitly when a native query depends on recent entity changes, and test on your actual provider/version.

### 12.2. Clear After Native DML

After bulk updates/deletes, you may need:

~~~java
entityManager.clear();
~~~

`clear()` detaches all managed entities from the persistence context. Subsequent reads load fresh state from the database.

Do not call `clear()` casually if the service still holds managed changes; unflushed changes are lost from the context. The typical sequence is flush before, then clear after bulk DML when needed.

### 12.3. Refreshing a Single Entity

If only one entity was modified outside the persistence context:

~~~java
entityManager.refresh(order);
~~~

`refresh()` reloads the entity's state from the database, overwriting managed state with current database values; unflushed local changes on that entity are discarded.

Use `refresh()` only when you want to discard local state and reload database state.

### 12.4. @Modifying and clearAutomatically

Spring Data JPA uses `@Modifying` for update/delete repository queries:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(
    value = """
        update orders
           set status = :newStatus
         where customer_id = :customerId
           and status = :oldStatus
        """,
    nativeQuery = true
)
int bulkUpdateStatus(
    @Param("customerId") Long customerId,
    @Param("oldStatus") String oldStatus,
    @Param("newStatus") String newStatus
);
~~~

Invoke inside an active transaction, such as a `@Transactional` service. `flushAutomatically` flushes pending changes before the query; `clearAutomatically` clears the context afterward. Both flags have broad persistence-context impact, so enable them only when callers understand managed entities will be detached.

Never put `@Modifying` on a `SELECT` query.

## 13. Transactions Between JPA and JDBC

An application can combine JPA repositories and `JdbcTemplate` in one service transaction if they share the same DataSource and transaction manager.

Example:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void closeOrder(long orderId) {
        OrderEntity order = repository.findById(orderId)
            .orElseThrow();

        // JPA managed change.
        order.setStatus("CLOSING");

        // Native procedure call through the same transaction-managed DataSource.
        jdbcTemplate.execute(
            "{ call ORDER_API.CLOSE_ORDER(?, ?) }",
            (CallableStatementCallback<String>) call -> {
                call.setLong(1, orderId);
                call.registerOutParameter(2, Types.VARCHAR);
                call.execute();
                return call.getString(2);
            }
        );

        // Transaction commits when the Spring method completes successfully.
    }
}
~~~

This illustrates transaction boundaries; avoid mutating an entity's status and simultaneously calling a procedure that updates the same row without clearly controlling flush order and expected outcomes. If the procedure modifies an already-loaded row, the entity becomes stale and needs refresh/clear.

### 13.1. Two Separate Connections Break Atomicity

If JPA uses DataSource A while JDBC opens a connection from DataSource B, the two operations can run in separate transactions.

When the service rolls back, the second connection's transaction may already have committed or fail to roll back alongside JPA.

To share one transaction:

- Use the same DataSource.
- Use the same transaction manager or proper transaction coordination.
- Never open raw connections outside the Spring transaction.
- Never commit inside stored procedures.
- Never close connections owned by the transaction manager from JDBC code.

If multiple resource managers or databases must coordinate, design distributed transactions or integration patterns explicitly; `@Transactional` alone does not create atomicity across independent connections.

## 14. Bulk Operations: Natural Limits of ORM

JPA entity lifecycles track individual entities. Bulk operations process many rows faster by bypassing per-entity lifecycle callbacks and dirty checking.

JPQL bulk update example:

~~~java
@Modifying
@Query("""
    update OrderEntity o
       set o.status = :newStatus
     where o.createdAt < :cutoff
       and o.status = :oldStatus
    """)
int archiveOldOrders(
    @Param("cutoff") LocalDateTime cutoff,
    @Param("oldStatus") OrderStatus oldStatus,
    @Param("newStatus") OrderStatus newStatus
);
~~~

Bulk updates:

- Do not invoke setters on individual entities.
- Do not fire entity lifecycle callbacks as individual updates do.
- Do not automatically synchronize already-managed entities.
- May skip optimistic locking/version semantics applied to individual entities.
- Require clearing/refreshing context where appropriate.

### 14.1. Native Bulk DML

Native SQL can leverage Oracle features, partition operations, or hand-tuned SQL. Persistence context and caches still require handling.

When bulk DML touches many rows, check:

- Row counts.
- Trigger side effects.
- Auditing.
- Constraints.
- Version columns.
- Lock contention.
- Redo/undo generation.
- Index maintenance.
- Cache invalidation.

### 14.2. Stored Procedure Bulk DML

Procedures can encapsulate bulk updates inside the database and minimize round trips. If a procedure modifies entities already loaded in the same persistence context, Java objects still become stale.

Flush before calling if the procedure must see pending entity changes; clear or refresh afterward if the procedure modified data held by the persistence context.

## 15. Transaction Isolation and Locking

JPQL/native queries can use pessimistic locking or SQL locking. Understand database transaction semantics, not just annotations.

JPA example:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from OrderEntity o where o.id = :id")
Optional<OrderEntity> findForUpdate(@Param("id") Long id);
~~~

The provider generates dialect-appropriate locking SQL, typically equivalent to `SELECT FOR UPDATE` in Oracle.

Native SQL can be explicit:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = :orderId
FOR UPDATE;
~~~

Row locks stay held until commit/rollback. Never hold locks across external API calls or large file streams. With `SKIP LOCKED` or `NOWAIT`, syntax and behavior depend on Oracle and the use case.

### 15.1. Optimistic Locking

Entity with `@Version`:

~~~java
@Version
@Column(name = "VERSION_NO")
private Long version;
~~~

Hibernate uses the version column to detect lost updates on managed entities.

Native SQL or procedures updating the table directly must maintain the version column per contract if the application relies on optimistic locking. If a procedure skips incrementing the version, another JPA transaction may miss concurrent changes.

### 15.2. Lock Timeouts

Lock timeouts can be set via query hints/providers or Oracle SQL depending on APIs. Configure sensible timeouts and handle exceptions. Never let sessions wait indefinitely on locks when fast responses are required.

## 16. Mapping Oracle Data Types to Java

Native queries and procedures expose data-type details more directly than JPQL.

| Oracle Data Type | Common Java Mapping | Notes |
|---|---|---|
| `NUMBER` | `BigDecimal`, `Long`, `Integer` | Choose by precision/scale and value range |
| `VARCHAR2` | `String` | Length and character semantics |
| `DATE` | `LocalDateTime` or compatible mapping | Oracle `DATE` includes hours/minutes/seconds |
| `TIMESTAMP` | `LocalDateTime` | Carries no time zone |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` or provider-appropriate mapping | Verify driver/provider |
| `CLOB` | `Clob`, `String`, or `Reader` | `String` is unsuitable for large LOBs |
| `BLOB` | `Blob` or `byte[]` | `byte[]` can consume heavy heap |
| `RAW` | `byte[]` | Size bounded by data type |
| `REF CURSOR` | `ResultSet`/DTO mapping | Provider/driver-specific |

Never map Oracle `DATE` to `LocalDate` if time-of-day matters. Never map monetary `NUMBER` columns to `double` when decimal exactness is required; use `BigDecimal`.

### 16.1. Nulls and Numeric Conversions

JDBC `getLong()` returns `0` for SQL NULL; call `wasNull()` when distinction matters:

~~~java
long value = resultSet.getLong("COUNT_VALUE");
if (resultSet.wasNull()) {
    // Database value was NULL.
}
~~~

For nullable numeric projections, use `getObject` or appropriate DTO mapping.

### 16.2. Oracle DATE and Time Zones

Oracle `DATE` stores date and time down to seconds without a time zone. `TIMESTAMP` also carries no time zone. `TIMESTAMP WITH TIME ZONE` carries time zone/offset metadata.

When native queries return timestamps, establish time zone semantics before mapping to `Instant`/`OffsetDateTime`/`LocalDateTime`. Avoid implicit conversions using JVM or session default time zones.

## 17. Pagination and Count Queries for Native SQL

Spring Data JPA supports `Pageable` on certain native queries:

~~~java
@Query(
    value = """
        select order_id, customer_id, status, created_at
          from orders
         where status = :status
         order by created_at desc, order_id desc
        """,
    countQuery = """
        select count(*)
          from orders
         where status = :status
        """,
    nativeQuery = true
)
Page<Object[]> findByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

For complex native SQL, provide an explicit `countQuery`, because providers cannot always derive accurate count queries from CTEs, `GROUP BY`, `DISTINCT`, or analytic queries.

### 17.1. Deterministic Ordering

Pagination requires a deterministic `ORDER BY` with a unique tie-breaker. Ordering only by `CREATED_AT` when multiple rows share timestamps causes rows to duplicate or disappear across pages as data changes.

Example:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

### 17.2. Deep Offsets

Large `OFFSET` values force the database to read and skip many rows before returning a page. For large tables, consider keyset pagination:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :customerId
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id < :lastOrderId)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

Native SQL gives clear control over this query. Bind values and NULL ordering must follow the sort contract.

## 18. Security: Binding Values and Dynamic SQL

Native queries must still defend against SQL injection. Bind all data values:

~~~java
Query query = entityManager.createNativeQuery(
    "select order_id from orders where customer_id = :customerId"
);
query.setParameter("customerId", customerId);
~~~

Never concatenate strings:

~~~java
String sql = "select * from orders where customer_id = " + userInput;
~~~

Bind variables cannot substitute for table names, column names, sort directions, or SQL keywords. When identifiers must vary dynamically, enforce a server-side allowlist:

~~~java
String orderColumn = switch (sortKey) {
    case "created" -> "created_at";
    case "amount"  -> "total_amount";
    default -> throw new IllegalArgumentException("Unsupported sort key");
};
~~~

Only interpolate allowlisted identifiers. Never pass raw column names from requests directly into SQL.

### 18.1. Stored Procedures Are Not Automatically Immune to SQL Injection

Procedures constructing dynamic SQL can also be vulnerable to injection:

~~~sql
l_sql := 'SELECT * FROM orders WHERE status = ''' || p_status || '''';
EXECUTE IMMEDIATE l_sql;
~~~

Use bind variables:

~~~sql
l_sql := 'SELECT * FROM orders WHERE status = :b1';
OPEN p_result FOR l_sql USING p_status;
~~~

For dynamic identifiers, use allowlists and `DBMS_ASSERT` appropriately. `DBMS_ASSERT` does not replace authorization.

### 18.2. Package-Based Privileges

You can grant `EXECUTE` on a package without granting direct table DML. This works well when the package serves as a business API enforcing validation, auditing, and minimal owner privileges.

Never grant `EXECUTE` to `PUBLIC` unless required. Review `AUTHID DEFINER`/`CURRENT_USER` and direct grants of the package owner.

## 19. SQL Logging and Observability

Native queries and procedures need observability in both the application and database.

Capture:

- Repository/service operation.
- `SQL_ID` where available.
- Procedure/package name.
- Redacted bind metadata.
- Duration.
- Rows affected/returned.
- Oracle error codes.
- Transaction outcomes.
- Correlation IDs.
- Connection pool waits.
- Timeouts/retries.

Never log passwords, tokens, PII, or full sensitive LOBs/payloads.

### 19.1. Hibernate SQL Logging

Enable SQL logging in development:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Bind-parameter logger names depend on the Hibernate version. Bind logging can expose sensitive data; never enable `TRACE` in production without redaction and approval.

### 19.2. SQL_ID and Execution Plans

When a query slows down, locate its `SQL_ID` in `V$SQL` and inspect child cursors, plan hashes, elapsed time, CPU, buffer gets, and disk reads. Use `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics when collected.

Do not optimize solely from Java wall-clock timing. Separate connection acquisition, SQL execution, fetching, mapping, and serialization to pinpoint bottlenecks.

## 20. Testing Stored Procedures and Native Queries

Tests must run against an Oracle version and driver compatible with production, because H2 and mocks do not faithfully emulate PL/SQL, `REF CURSOR`, Oracle data types, or optimizer behavior.

### 20.1. Integration Tests

Use Testcontainers Oracle if images/licensing/runtime fit organizational policy, or a managed Oracle test database. Never assume H2 can validate Oracle packages.

Test:

- Package existence and valid compilation.
- Runtime user `EXECUTE` privileges.
- `IN`/`OUT` parameter mapping.
- `REF CURSOR` mapping.
- Numeric/date/LOB data types.
- Transaction commit/rollback.
- Native query aliases and DTO mappings.
- Flush/clear behavior.
- Pessimistic locks and timeouts.
- SQL injection defenses.
- Pagination and count queries.

### 20.2. Transaction Rollback Tests

Spring test example:

~~~java
@SpringBootTest
@Transactional
class OrderProcedureIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void procedureRunsWithinTransaction() {
        orderService.closeOrder(1001L);

        // Assert expected state using a fresh/cleared persistence context.
    }
}
~~~

`@Transactional` tests roll back by default when the test ends. However, if a procedure issues its own `COMMIT`, the test rollback cannot undo that commit—which helps catch broken transaction contracts.

### 20.3. Testing Stale Persistence Contexts

1. Load an entity via `EntityManager`.
2. Call a native update or stored procedure modifying the same row.
3. Re-read the entity in the same persistence context.
4. Observe stale state.
5. Call `refresh` or `clear` and re-read.
6. Document the synchronization strategy explicitly in service code.

This test prevents bugs where applications observe stale state after procedures run.

## 21. Version Compatibility: Spring Boot, JPA, and Oracle JDBC

An application must align versions across layers:

- Spring Boot release.
- Spring Data JPA release.
- Hibernate ORM release.
- Jakarta Persistence vs. `javax.persistence`.
- Oracle JDBC driver (`ojdbc`).
- Oracle Database release/RU.
- Oracle dialect/provider configuration.

Spring Boot 3 uses the Jakarta namespace for JPA; Spring Boot 2 typically uses the `javax` namespace. Never copy annotation imports across major versions without checking.

The Oracle JDBC driver version must be compatible with your JDK and database deployment. `REF CURSOR`, LOB, `TIMESTAMP WITH TIME ZONE`, arrays/structs, JSON, and procedure parameter behaviors vary across driver releases.

Do not force legacy dialect classes if your Hibernate version ships an updated dialect. Use supported Spring Boot/Hibernate configurations and verify generated SQL in integration tests.

## 22. Troubleshooting Runbook for Procedures and Native Queries

### Step 1 — Identify the Failing Layer

- Spring Data repository query parsing.
- JPA provider parameter registration.
- JDBC call syntax.
- Oracle package/schema resolution.
- Database privileges.
- Data type/parameter conversion.
- SQL execution/constraints.
- `ResultSet`/`REF CURSOR` mapping.
- Transaction/persistence context state.

### Step 2 — Verify the Procedure Contract

~~~sql
SELECT owner,
       object_name,
       procedure_name,
       object_type
FROM all_procedures
WHERE object_name = 'ORDER_API'
ORDER BY owner, procedure_name;
~~~

Inspect argument metadata:

~~~sql
SELECT owner,
       package_name,
       object_name,
       argument_name,
       position,
       sequence,
       data_type,
       in_out,
       data_level
FROM all_arguments
WHERE package_name = 'ORDER_API'
  AND object_name = 'CLOSE_ORDER'
ORDER BY sequence;
~~~

`ALL_ARGUMENTS` exposes package procedures/functions and overloads; check overloads, positions, data types, `IN_OUT`, and cursor types.

### Step 3 — Check Privileges

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE table_name = 'ORDER_API'
ORDER BY grantee, privilege;
~~~

Verify executing schema, package owner, `AUTHID`, and privileges on underlying tables.

### Step 4 — Inspect the Error Stack

Record `SQLState`, vendor error code, message, and full cause chain. In Oracle, `ORA-06550`/`PLS` errors indicate compilation or call-signature mismatches; `ORA-01031` is insufficient privileges; `ORA-01403` is no data found in PL/SQL; `ORA-00904` often signals a bad column/alias name.

Never log only Spring's outer wrapper message. Preserve the `SQLException` chain and Oracle error codes.

### Step 5 — Verify Transactions and Context

- Does the connection share the transaction manager?
- Does the procedure issue `COMMIT`?
- Have entity changes been flushed?
- Does the persistence context hold stale entities?
- Does native DML clear/refresh afterward?
- Is the connection returned to the pool in a clean state?

## 23. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using native SQL for every query | Loses entity mapping benefits and portability | Use JPQL for routine entity queries |
| Forcing JPQL for Oracle analytics/hints | Unreadable or inexpressible queries | Isolate native SQL in repositories |
| Calling procedures without understanding `OUT` mapping | Null or wrong return values | Register mode/type/name/position explicitly |
| Assuming `REF CURSOR` auto-maps to entities | Mapping errors or incomplete entity state | Use DTOs/`SqlResultSetMapping` or JDBC |
| Procedure executes `COMMIT` | Breaks Spring transaction atomicity | Let the transaction owner control commits |
| JPA and JDBC use separate connections | Inconsistent rollbacks | Share DataSource and transaction manager |
| Running native DML without clearing context | Managed entities turn stale | Flush/clear/refresh deliberately |
| Calling `clear` before `flush` | Discards pending entity changes | Flush first when needed |
| Expecting bulk DML to run lifecycle callbacks | Callbacks/audits skipped unlike entity updates | Handle audits/side effects explicitly |
| Mapping `NUMBER` to `double` | Decimal rounding errors | Use `BigDecimal` |
| Mapping Oracle `DATE` to `LocalDate` | Drops time-of-day portion | Use `LocalDateTime` or suitable mapping |
| Binding dynamic identifiers | Invalid SQL or injection vulnerability | Allowlist identifiers |
| Using H2 to test Oracle procedures | False passes or unsupported syntax | Run Oracle integration tests |
| Enabling bind logging in production | Leaks sensitive data | Redact and restrict logging |
| Ignoring driver versions | Different `REF CURSOR`/LOB/type behavior | Pin and test compatible drivers |

## 24. Selection and Implementation Checklist

### Choosing the Abstraction

- [ ] Can the query be expressed cleanly in JPQL/Criteria?
- [ ] Are Oracle SQL features, hints, or analytic functions needed?
- [ ] Must logic be shared across multiple clients?
- [ ] Does a stored procedure offer clear bulk or privilege-boundary benefits?
- [ ] Is cross-database portability required?
- [ ] Are procedure contracts and ownership documented?

### Procedures

- [ ] Package/procedure signatures are under version control.
- [ ] `IN`/`OUT`/`INOUT`/`REF CURSOR` parameters are declared accurately.
- [ ] Least-privilege `EXECUTE` grants are applied.
- [ ] `AUTHID` and direct owner grants are reviewed.
- [ ] Procedures never `COMMIT` outside their contract.
- [ ] Error codes and business results are defined.
- [ ] Tested against a real Oracle database/driver.

### Native SQL

- [ ] All data values use bind parameters.
- [ ] Dynamic identifiers use allowlists.
- [ ] Result mappings use explicit projections/DTOs.
- [ ] Count queries and pagination are tested.
- [ ] Paginated SQL uses deterministic `ORDER BY`.
- [ ] Execution plans and indexes are measured.
- [ ] Native DML synchronizes the persistence context.

### Transactions and ORM State

- [ ] JPA and JDBC share the same transaction context when atomicity is required.
- [ ] Pending changes flush before dependent queries.
- [ ] `clear`/`refresh` run at the right points.
- [ ] Procedures never commit unexpectedly.
- [ ] Optimistic versions and lock semantics are preserved.
- [ ] Connections return cleanly to the pool after transactions/resources close.

## 25. Key Takeaways

- JPQL operates at the entity level; native SQL operates directly on SQL/tables; stored procedures invoke database-encapsulated logic.
- Use JPQL for routine entity queries; native SQL for Oracle-specific features or full SQL control; procedures for shared database APIs, bulk work, or database-resident logic.
- Spring Data JPA `@Procedure` suits simple procedures; `EntityManager` `StoredProcedureQuery` handles complex `IN`/`OUT`/`INOUT` and `REF CURSOR`s flexibly; JDBC `CallableStatement` fits Oracle-specific control.
- Oracle package procedures require `EXECUTE` privilege; package owner and `AUTHID` govern runtime permissions.
- Procedures must not `COMMIT` independently when services expect atomic transactions with JPA operations.
- `REF CURSOR` returns a cursor result; mapping depends on JPA provider, Hibernate, and Oracle JDBC driver; DTOs usually fit projections best.
- Native queries require explicit mappings; `Object[]` couples tightly to column positions and breaks easily when projections change.
- `@SqlResultSetMapping` supports `EntityResult` and `ConstructorResult` for native results.
- Native DML and stored procedures can alter database rows without updating already-managed entities.
- `flush` sends pending changes to the database without committing; `clear` detaches all managed entities; `refresh` reloads one entity and discards unflushed local changes.
- Spring Data `@Modifying` supports `flushAutomatically`/`clearAutomatically`, provided callers understand persistence-context side effects.
- JPA and `JdbcTemplate` share transactions when backed by the same DataSource/transaction manager; independent connections break atomicity.
- Bulk DML skips per-entity lifecycle hooks; account for callbacks, audits, version columns, and caches explicitly.
- Map Oracle `NUMBER` to `BigDecimal` when decimal precision matters; Oracle `DATE` includes time-of-day; time-zoned data types require explicit semantics.
- Native SQL must bind values and allowlist dynamic identifiers; dynamic SQL inside stored procedures is also vulnerable to SQL injection.
- Test procedures, `REF CURSOR`s, data types, and Oracle-specific SQL on your real Oracle version and driver; H2 does not replace Oracle integration tests.
- ORM is a helpful abstraction, not a shield that hides transactions, SQL execution, database privileges, or persistence-context lifecycles.

### Spring, JPA, and Oracle Documentation to Consult

- [Spring Data JPA Reference — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html) — `@Procedure`, `@NamedStoredProcedureQuery`, and `OUT` parameters.
- [Spring Data JPA Reference — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — `@Query`, native queries, projections, and modifying queries.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — `StoredProcedureQuery`, native SQL, result mappings, entity lifecycle, and persistence context.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — Native SQL, stored procedures, flush modes, bulk operations, and JDBC integration.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — `@Transactional`, transaction managers, and JDBC/JPA integration.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — `CallableStatement`, `REF CURSOR`, Oracle JDBC data types, and driver behavior.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/) — PL/SQL packages, procedure signatures, and `REF CURSOR`.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — Oracle SQL syntax, analytic functions, row limiting, and native features.

Spring Boot, Spring Data JPA, Hibernate, Jakarta Persistence and Oracle JDBC versions must be compatible. Verify imports (javax versus jakarta), procedure name/parameter binding, REF CURSOR support, native pagination and transaction behavior with the exact stack deployed; keep database-specific code behind a clear repository or adapter boundary.
