# Defining @NamedStoredProcedureQuery and Procedure Parameters

A stored procedure is a procedure defined and executed in the database. Spring Data JPA lets you invoke this procedure via a repository; Jakarta Persistence provides mechanisms to declare mappings with `@NamedStoredProcedureQuery` or create a `StoredProcedureQuery` directly through `EntityManager`.

When integrating, you must distinguish two easily confused names:

- **Registered JPA name:** the `name` attribute of `@NamedStoredProcedureQuery`, used to reference the configuration in the application.
- **Database procedure name:** the `procedureName` attribute, which is the actual procedure name exposed by the database.

Additionally, you must declare the proper `IN`, `OUT`, `INOUT`, or `REF_CURSOR` parameters, the right Java types, and the right result mapping. The example below uses a procedure that closes a purchase order and returns a result code.

## 1. What is a stored procedure?

A stored procedure is a program stored in the database that can be invoked by name. A procedure can accept input parameters, modify data, return output parameters, or return a result set.

Example of a MySQL procedure:

~~~sql
DELIMITER //

CREATE PROCEDURE close_purchase_order(
    IN p_order_id BIGINT,
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_status VARCHAR(30);
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    -- Call inside an active transaction; purchase_orders must use InnoDB.
    -- The caller commits or rolls back after this procedure returns.
    SELECT status
      INTO v_status
      FROM purchase_orders
     WHERE id = p_order_id
     FOR UPDATE;

    IF v_not_found THEN
        SET p_result = 'NOT_FOUND';
    ELSEIF v_status = 'CLOSED' THEN
        SET p_result = 'ALREADY_CLOSED';
    ELSE
        UPDATE purchase_orders
           SET status = 'CLOSED'
         WHERE id = p_order_id;

        SET p_result = 'CLOSED';
    END IF;
END //

DELIMITER ;
~~~

The procedure locks the order row with `SELECT ... FOR UPDATE` before reading its status. The `NOT FOUND` handler flags when no record exists; if the order exists and its status is `CLOSED`, the procedure returns `ALREADY_CLOSED`; if the status is not `CLOSED`, it updates it and returns `CLOSED`. The `purchase_orders` table must use InnoDB, and the `CALL` statement must execute inside an active transaction (for example, from a service method with `@Transactional`). The procedure does not issue `START TRANSACTION` or `COMMIT` itself so that the application-managed transaction holds the lock until completion. Procedure creation syntax varies across database management systems; the snippet above is MySQL syntax, not portable SQL for all databases.

In a Java application, we want to invoke the procedure without manually managing JDBC `CallableStatement` everywhere. JPA and Spring Data JPA provide APIs to declare parameters, pass values, and receive results.

## 2. Declaring @NamedStoredProcedureQuery

`@NamedStoredProcedureQuery` is a Jakarta Persistence annotation used to register a named stored procedure mapping in the persistence unit. The annotation is typically placed on an entity class.

Example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.closeOrder",
    procedureName = "close_purchase_order",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_order_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_result",
            type = String.class
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Other purchase order attributes
}
~~~

Meaning of each attribute:

- `name = "PurchaseOrder.closeOrder"`: the JPA name used to look up the registered configuration. This is not the procedure name in the database.
- `procedureName = "close_purchase_order"`: the actual procedure name in the database.
- `parameters`: the list of parameters registered in declaration order.
- `mode`: the direction of data flow for the parameter.
- `name`: the parameter name on the procedure side, when the provider and database support binding by name.
- `type`: the Java type corresponding to the parameter.

The JPA name in the `name` attribute must be unique within the persistence unit. You may place the annotation on another entity if it fits the model, though placing it on the related entity usually makes it easier to locate and maintain.

## 3. Stored procedure parameter types

Jakarta Persistence defines the following `ParameterMode` values:

| Mode | Meaning | Usage |
|---|---|---|
| IN | Input parameter | Application passes a value to the procedure |
| OUT | Output parameter | Procedure assigns a value for the application to read |
| INOUT | Both input and output | Application passes an initial value, procedure updates the value |
| REF_CURSOR | Result cursor | Procedure returns a result set via a cursor; depends on provider/database |

### 3.1. IN

`IN` is a parameter passed from Java to the database. For instance, `p_order_id` in the `close_purchase_order` procedure receives the order ID.

When declared:

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.IN,
    name = "p_order_id",
    type = Long.class
)
~~~

the application must supply a value before executing the procedure.

### 3.2. OUT

`OUT` is a parameter produced by the procedure. For instance, `p_result` returns `CLOSED` or `NOT_FOUND`. The application reads the value after the procedure executes successfully.

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.OUT,
    name = "p_result",
    type = String.class
)
~~~

`OUT` is not an input value; do not pass a business value into it as you would with `IN`.

### 3.3. INOUT

`INOUT` allows sending an initial value and receiving the value updated by the procedure. For example, a procedure receives an integer, increments it by one, and returns the result through the same parameter.

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
~~~

With `INOUT`, the application must set an initial value before calling. After execution, the application reads the output value from the same parameter.

### 3.4. REF_CURSOR

`REF_CURSOR` represents a cursor containing a result set. This is common in certain databases such as Oracle and PostgreSQL, though exact support and registration mechanisms depend on the database, JDBC driver, and JPA provider.

You can declare it with `ParameterMode.REF_CURSOR` when supported by the persistence stack. Do not assume all databases support `REF_CURSOR` or share the same declaration syntax.

If a procedure returns data rows, you must specify how to map the results to an entity or DTO. Jakarta Persistence provides `resultClasses` and `resultSetMappings` on `@NamedStoredProcedureQuery` to describe results. For procedures returning multiple result sets or cursors, verify support in the provider and driver in use.

## 4. Calling a named stored procedure with Spring Data JPA

After declaring `@NamedStoredProcedureQuery`, the repository can reference the JPA name using `@Procedure(name = ...)`.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Procedure(name = "PurchaseOrder.closeOrder")
    String closeOrder(@Param("p_order_id") Long orderId);
}
~~~

In this example:

- `name` on `@Procedure` points to the JPA name `PurchaseOrder.closeOrder` registered on the entity.
- `@Param("p_order_id")` maps the method parameter to the IN parameter with the corresponding name.
- The `String` return value receives the OUT parameter `p_result`.

Spring Data JPA invokes the procedure and maps the single output parameter according to the method's return type. The return type must be compatible with the Java type declared for the OUT parameter.

You can invoke the repository from a service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public String closeOrder(Long orderId) {
        return repository.closeOrder(orderId);
    }
}
~~~

A transaction at the service layer establishes the transaction boundary of the use case. Actual transaction configuration and commit behavior also depend on how the procedure is invoked, the database, and the transaction manager. If the procedure updates data, verify execute privileges, update permissions, and rollback behavior in the target database.

## 5. Distinguishing name and procedureName in @Procedure

Spring Data JPA can call a procedure directly without declaring `@NamedStoredProcedureQuery` on an entity.

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Procedure(procedureName = "close_purchase_order")
    String closeOrder(@Param("p_order_id") Long orderId);
}
~~~

The two approaches have different meanings:

- `@Procedure(name = "PurchaseOrder.closeOrder")` references a named stored procedure query registered via `@NamedStoredProcedureQuery`.
- `@Procedure(procedureName = "close_purchase_order")` specifies the procedure name in the database directly.
- The `value` attribute of `@Procedure` is an alias for `procedureName` in Spring Data JPA.

If you already use named mappings, referencing by `name` keeps parameter declarations centralized on the entity. For a single simple operation, calling `procedureName` directly can be more concise.

Do not confuse `name` with `procedureName` in `@Procedure`. One is the JPA configuration name in the application; the other is the actual procedure object name in the database.

## 6. Procedures with multiple OUT parameters

A procedure can have multiple OUT parameters, such as returning a status code and an affected row count. In Spring Data JPA, when receiving multiple output values, the repository method can return `Map<String, Object>` if the named procedure mapping and provider support that mapping.

Declaration example:

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.closeOrderWithDetails",
    procedureName = "close_purchase_order_details",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_order_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_result",
            type = String.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_affected_rows",
            type = Integer.class
        )
    }
)
~~~

Repository:

~~~java
@Procedure(name = "PurchaseOrder.closeOrderWithDetails")
Map<String, Object> closeOrderWithDetails(
        @Param("p_order_id") Long orderId);
~~~

The Map contains the OUT parameters mapped by the names returned by the provider. You must verify the actual key names in the database/driver environment you are using and avoid assuming all providers normalize casing the same way.

If a procedure has only a single OUT parameter, returning a specific type like `String`, `Integer`, or `Long` is usually easier to use than a `Map`. Only use a `Map` when you genuinely need multiple output values.

## 7. Calling procedures dynamically with EntityManager

When the procedure name or parameters are decided at runtime, you can use `StoredProcedureQuery` instead of declaring a fixed named mapping.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import org.springframework.stereotype.Repository;

@Repository
public class PurchaseOrderProcedureRepository {

    private final EntityManager entityManager;

    public PurchaseOrderProcedureRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public String closeOrder(Long orderId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "close_purchase_order");

        query.registerStoredProcedureParameter(
                "p_order_id", Long.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "p_result", String.class, ParameterMode.OUT);

        query.setParameter("p_order_id", orderId);
        query.execute();

        return (String) query.getOutputParameterValue("p_result");
    }
}
~~~

Execution sequence:

1. Create a `StoredProcedureQuery` with the database procedure name.
2. Register each parameter with name or position, Java type, and mode.
3. Assign values to IN or INOUT parameters.
4. Call `execute()`.
5. Read OUT or INOUT values after the procedure executes.

Some databases/drivers do not uniformly support parameter binding by name. In that case, register by position and ensure the order matches the procedure signature exactly. Support for named parameters and cursors must be verified with the actual provider/driver.

## 8. Mapping a result set returned from a procedure

A procedure can return a set of rows instead of only OUT parameters. With JPA, `@NamedStoredProcedureQuery` can declare `resultClasses` or `resultSetMappings`.

Outline declaration example when a procedure returns rows corresponding to the `PurchaseOrder` entity:

~~~java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.findOpenOrders",
    procedureName = "find_open_orders",
    resultClasses = PurchaseOrder.class
)
~~~

When the result set does not directly match an entity, you can use `@SqlResultSetMapping` to map columns to an entity, DTO constructor, or scalar results depending on provider capabilities.

For procedures returning multiple result sets, `REF_CURSOR`, or mixed result sets and OUT parameters, check the documentation for the database, JDBC driver, and Hibernate version in use. Do not assume a repository method can automatically map every complex result structure.

## 9. Important considerations when using procedures

### 9.1. Synchronizing the persistence context after a procedure updates data

Stored procedures run directly in the database and can alter data underneath JPA. If a corresponding entity has already been loaded and is managed in the persistence context, the in-memory state may become stale relative to the database.

Example: the `PurchaseOrder` entity was loaded with `status = PENDING`. The procedure updates `status` to `CLOSED`. The managed Java object may still hold the value `PENDING`.

You can handle this by:

- Calling `EntityManager.refresh(entity)` to reload a specific entity.
- Calling `EntityManager.clear()` when you need to evict all managed entities, then reloading as needed.
- Designing the flow to call the procedure before loading entities if appropriate.

Do not call `clear()` indiscriminately because this operation detaches all entities in the persistence context; unflushed changes may no longer be managed as expected. Establish a clear ordering of flushing, calling the procedure, and refreshing/clearing.

### 9.2. Data types and NULL values

The Java type declared in `@StoredProcedureParameter` must be compatible with the database parameter type. For example:

- `BIGINT` typically maps to `Long`.
- `INTEGER` typically maps to `Integer`.
- `VARCHAR` typically maps to `String`.
- `DECIMAL`/`NUMERIC` typically maps to `BigDecimal`.
- `DATE`/`TIMESTAMP` requires choosing a Java type compatible with the JDBC driver and application mappings.

Check type conversion rules, numeric precision, time zones, and NULL handling. For OUT parameters that may return NULL, wrapper types like `Integer` and `Long` are more suitable than primitive types.

### 9.3. Named parameters and positional parameters

When using named parameters, the names in `@StoredProcedureParameter` and `@Param` must match the procedure names as supported by the provider/driver. Some DBMSs or drivers have limitations on named binding; positional binding is the fallback when compatibility is needed.

Parameter registration order must be consistent with the procedure definition if invoking by position. Do not reorder `IN`, `OUT`, or `INOUT` parameters on your own.

### 9.4. Database privileges and transactions

The application's database account must have `EXECUTE` privilege on the procedure and the data privileges required by the procedure. If the procedure modifies multiple tables, verify transactions and rollback behavior against the target database.

Not every procedure is suited to running inside an application-managed transaction; some database procedures may contain their own transaction control statements or special behaviors. Design transaction boundaries according to the DBMS and business rules.

### 9.5. Avoid concatenating procedure names from untrusted data

Procedure names, parameter names, and SQL structure should be static configuration or strictly controlled. User input values must be bound via parameters rather than concatenated directly into SQL strings. This helps reduce the risk of SQL injection and syntax errors.

## 10. Common errors and troubleshooting

| Symptom | Possible cause | Check / resolution |
|---|---|---|
| Named procedure not found | Wrong `name` in `@Procedure` or JPA name not registered | Match `name` against `@NamedStoredProcedureQuery.name` |
| Procedure does not exist | Wrong `procedureName` or schema | Check name, schema, and `EXECUTE` privileges |
| Unable to bind parameters | Wrong name, wrong order, or driver lacks named binding support | Match procedure signature; try positional binding |
| Wrong parameter type | Java type incompatible with SQL type | Check metadata and JDBC types |
| Cannot read OUT parameter | Wrong mode, parameter name, or read before `execute()` | Register OUT/INOUT properly and read after `execute()` |
| Unable to map result set | Missing `resultClasses`/`resultSetMappings` or column mismatch | Verify result mapping and provider support |
| Entity shows stale data | Procedure updated data outside dirty checking | Refresh entity or intentionally clear persistence context |

## 11. Implementation and testing workflow

1. Create the procedure in the database and test it manually with a SQL tool.
2. Document the procedure signature: name, parameter order, data types, and `IN`/`OUT`/`INOUT` modes.
3. Declare `@NamedStoredProcedureQuery` on an entity or use `EntityManager` if dynamic invocation is needed.
4. Map parameters with `@StoredProcedureParameter`, choosing the correct Java types.
5. Create a repository method using `@Procedure(name = ...)` or `@Procedure(procedureName = ...)`.
6. Invoke from a service with appropriate transactions.
7. Test return values, data side effects, `NULL`, record-not-found cases, and rollback on errors.
8. If the procedure updates managed entities, check the persistence context state after the call.

An integration test should verify both the OUT result and the actual state in the database. Checking only the return value is insufficient if the procedure also performs data updates.

## Conclusion

`@NamedStoredProcedureQuery` registers a named stored procedure mapping in JPA; `procedureName` points to the actual routine in the database, while `name` is the reference key from the application. `@StoredProcedureParameter` describes the name, type, and data direction of each parameter.

Spring Data JPA can invoke a named mapping via `@Procedure(name = ...)`, invoke directly via `@Procedure(procedureName = ...)`, or use `StoredProcedureQuery` through `EntityManager` when flexibility is needed. For reliable integration, verify the procedure signature, parameter mappings, data types, transactions, result sets, and persistence context state after the procedure modifies data.