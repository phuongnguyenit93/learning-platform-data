# Distinguishing IN, OUT, INOUT, and REF_CURSOR by Support Capabilities

A stored procedure can accept input data, return output values, or return a set of rows. When calling stored procedures from JPA, the four common parameter modes are **IN**, **OUT**, **INOUT**, and **REF_CURSOR**.

- **IN** passes a value from the application into the procedure.
- **OUT** receives a value computed and returned by the procedure.
- **INOUT** both passes an initial value and returns a value after the procedure processes it.
- **REF_CURSOR** receives a cursor opened by the database to read a set of result rows.

Jakarta Persistence defines these modes via **ParameterMode**, which does not mean every database, JDBC driver, and JPA provider supports them identically. In particular, `REF_CURSOR` depends heavily on the database and provider. During design, distinguish the standard JPA API from the actual execution capabilities of the specific database, dialect, driver, and Hibernate combination in use.

This lesson covers the meaning of each mode, how to declare them with `EntityManager` and Spring Data JPA, how to read outputs, `REF_CURSOR` mapping, differences across popular databases, transactions, the persistence context, and testing.

**Example prerequisites:** code snippets use Java 17 or higher, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. The application needs **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and the stored procedure created in the database. MySQL and Oracle SQL examples are labeled separately by dialect; they cannot be run verbatim on another database.

## 1. What do the four parameter modes mean?

| Mode | Data direction | What does the application do? | What does the procedure do? |
|---|---|---|---|
| **IN** | Application → procedure | Assigns value before execute | Reads input value |
| **OUT** | Procedure → application | Registers type and reads after execute | Assigns output value |
| **INOUT** | Bidirectional | Assigns initial value, then reads back | Reads and updates value |
| **REF_CURSOR** | Database → application, via cursor | Registers cursor and reads result set | Opens cursor containing multiple rows |

You can visualize it as:

~~~text
IN          Java value -----------------> Procedure
OUT         Java reads <----------------- Procedure value
INOUT       Java value -----------------> Procedure
            Java reads <----------------- Updated value
REF_CURSOR  Java reads rows <------------ Open database cursor
~~~

The three modes `IN`, `OUT`, and `INOUT` are commonly used for scalars such as numbers, strings, dates/times, or decimals. `REF_CURSOR` is used to return a tabular result set, typically with multiple rows and columns.

## 2. ParameterMode in Jakarta Persistence

Jakarta Persistence provides the enum **jakarta.persistence.ParameterMode**:

~~~java
public enum ParameterMode {
    IN,
    INOUT,
    OUT,
    REF_CURSOR
}
~~~

When working with **StoredProcedureQuery**, you must register parameters before setting values or executing:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("procedure_name");

query.registerStoredProcedureParameter(
    1,
    Integer.class,
    ParameterMode.IN
);
~~~

Parameters can be registered by position or by name:

~~~java
query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);
~~~

The name or position must match the procedure signature according to how the database/provider identifies parameters. With positional parameters, the order must match the procedure declaration. With named parameters, pay attention to database naming and case-sensitivity rules.

Do not register the same parameter twice. All parameters must be registered before calling **execute()**.

## 3. IN: passing data into a procedure

`IN` is the simplest mode. The application passes a value for the procedure to use during processing.

Stored procedure example in MySQL syntax:

~~~sql
CREATE PROCEDURE find_products_by_status(
    IN p_status VARCHAR(30)
)
BEGIN
    SELECT id, name, status, price
    FROM products
    WHERE status = p_status;
END;
~~~

Calling with EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "find_products_by_status",
        Product.class
    );

query.registerStoredProcedureParameter(
    "p_status",
    String.class,
    ParameterMode.IN
);

query.setParameter("p_status", "ACTIVE");

List<Product> products = query.getResultList();
~~~

In this example:

- `p_status` is registered as `IN`.
- `setParameter` assigns the value before execution.
- the procedure uses that value in the `WHERE` condition.
- the result set is mapped to `Product`.

When mapping to an entity, the `SELECT` must return all required columns for the `Product` mapping. If the procedure only returns partial data, use DTO/scalar mapping rather than assuming a full entity can be constructed.

## 4. OUT: receiving a value from a procedure

`OUT` is a parameter that only returns data from the procedure to the application. The application registers the parameter type, does not assign an input value to it, and reads it with **getOutputParameterValue()** after the procedure executes.

MySQL example:

~~~sql
CREATE PROCEDURE calculate_discount(
    IN p_amount DECIMAL(12,2),
    OUT p_discount DECIMAL(12,2)
)
BEGIN
    SET p_discount = ROUND(p_amount * 0.10, 2);
END;
~~~

Calling with EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("calculate_discount");

query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "p_discount",
    BigDecimal.class,
    ParameterMode.OUT
);

query.setParameter("p_amount", new BigDecimal("500000.00"));

query.execute();

BigDecimal discount = (BigDecimal)
    query.getOutputParameterValue("p_discount");
~~~

If the input is `500000.00` and the procedure calculates 10%, the output value in the example is `50000.00`. Actual results depend on database precision, scale, and rounding rules.

Do not call `getOutputParameterValue` before `execute`. OUT values are only meaningful after the procedure has executed successfully and the driver/provider has retrieved the output.

## 5. INOUT: passing in and receiving an updated value

`INOUT` combines both directions:

1. The application assigns an initial value.
2. The procedure reads that value.
3. The procedure modifies the value.
4. The application reads the value back after `execute`.

MySQL example:

~~~sql
CREATE PROCEDURE add_tax(
    IN p_amount DECIMAL(12,2),
    INOUT p_tax DECIMAL(12,2)
)
BEGIN
    SET p_tax = p_tax + ROUND(p_amount * 0.05, 2);
END;
~~~

Calling with EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("add_tax");

query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "p_tax",
    BigDecimal.class,
    ParameterMode.INOUT
);

query.setParameter("p_amount", new BigDecimal("100000.00"));
query.setParameter("p_tax", new BigDecimal("2000.00"));

query.execute();

BigDecimal updatedTax = (BigDecimal)
    query.getOutputParameterValue("p_tax");
~~~

By the procedure logic, initial `p_tax` is `2000.00`, the added amount is `5000.00`, so the output is `7000.00`.

Differences between `OUT` and `INOUT`:

| OUT | INOUT |
|---|---|
| Needs no input value | Must have an initial value |
| Procedure generates the output value | Procedure processes the passed-in value |
| Application only reads after execute | Application assigns before and reads back after execute |

## 6. Combining IN, OUT, and INOUT in a single procedure

A procedure can declare multiple modes simultaneously. For example, `calculate_price` receives an amount, returns a discount, and updates tax:

~~~sql
CREATE PROCEDURE calculate_price(
    IN p_amount DECIMAL(12,2),
    OUT p_discount DECIMAL(12,2),
    INOUT p_tax DECIMAL(12,2)
)
BEGIN
    SET p_discount = ROUND(p_amount * 0.10, 2);
    SET p_tax = p_tax + ROUND(p_amount * 0.05, 2);
END;
~~~

Invocation:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("calculate_price");

query.registerStoredProcedureParameter(
    "p_amount", BigDecimal.class, ParameterMode.IN);
query.registerStoredProcedureParameter(
    "p_discount", BigDecimal.class, ParameterMode.OUT);
query.registerStoredProcedureParameter(
    "p_tax", BigDecimal.class, ParameterMode.INOUT);

query.setParameter("p_amount", new BigDecimal("500000.00"));
query.setParameter("p_tax", new BigDecimal("10000.00"));

query.execute();

BigDecimal discount = (BigDecimal)
    query.getOutputParameterValue("p_discount");

BigDecimal tax = (BigDecimal)
    query.getOutputParameterValue("p_tax");
~~~

With the values above, `discount` is `50000.00` and the new `tax` is `35000.00`. This follows the formula of the illustrative procedure.

In a real application, you can encapsulate procedure invocation logic in a service so controllers do not need to know details like parameter ordering or JDBC types.

## 7. Calling procedures via Spring Data JPA @Procedure

Spring Data JPA provides the **@Procedure** annotation on repository methods.

Example of a procedure with only one scalar output:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Procedure(
        procedureName = "calculate_discount",
        outputParameterName = "p_discount"
    )
    BigDecimal calculateDiscount(
        @Param("p_amount") BigDecimal amount
    );
}
~~~

**procedureName** is the procedure name in the database. **outputParameterName** identifies the OUT parameter used as the method's return value.

You can declare metadata via **@NamedStoredProcedureQuery** on the entity and reference it by JPA name:

~~~java
@Entity
@Table(name = "products")
@NamedStoredProcedureQuery(
    name = "Product.calculateDiscount",
    procedureName = "calculate_discount",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_amount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_discount",
            type = BigDecimal.class
        )
    }
)
public class Product {
    // Entity mapping
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Procedure(name = "Product.calculateDiscount")
    BigDecimal calculateDiscount(
        @Param("p_amount") BigDecimal amount
    );
}
~~~

Distinguish the following:

- **procedureName**: physical procedure name in the database.
- **name**: name of the named stored procedure query declared in JPA metadata.
- **value**: alias of the `procedureName` attribute in the `@Procedure` annotation.

If a method has a single scalar output, you can use the corresponding return type. With multiple output parameters, Spring Data JPA supports returning **Map<String, Object>** in cases properly declared with named stored procedure metadata. Map keys correspond to output parameter names per framework/provider mapping.

For `INOUT`, `REF_CURSOR`, or procedures returning both multiple result sets and output parameters, check how the Spring Data JPA version and provider in use handle results. If detailed control is needed, `EntityManager` `StoredProcedureQuery` is usually clearer.

## 8. Reading multiple output parameters with Map

Suppose the entity declares metadata for `calculate_price`:

~~~java
@NamedStoredProcedureQuery(
    name = "Product.calculatePrice",
    procedureName = "calculate_price",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_amount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_discount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.INOUT,
            name = "p_tax",
            type = BigDecimal.class
        )
    }
)
~~~

The repository can declare a method returning a `Map`:

~~~java
@Procedure(name = "Product.calculatePrice")
Map<String, Object> calculatePrice(
    @Param("p_amount") BigDecimal amount,
    @Param("p_tax") BigDecimal initialTax
);
~~~

Invocation:

~~~java
Map<String, Object> outputs =
    productRepository.calculatePrice(
        new BigDecimal("500000.00"),
        new BigDecimal("10000.00")
    );

BigDecimal discount =
    (BigDecimal) outputs.get("p_discount");

BigDecimal updatedTax =
    (BigDecimal) outputs.get("p_tax");
~~~

A `Map` lets you receive multiple outputs in a single call. Key names depend on parameter name metadata and how the provider/framework returns results; verify them with an integration test against a real database. Do not assume the `Map` contains all result sets or every kind of output if the procedure has a complex structure.

## 9. What is REF_CURSOR?

`REF_CURSOR` is a parameter representing a cursor opened by the database. The cursor points to a set of result rows that the application can read after the procedure executes.

Unlike scalar `OUT`:

- `OUT` typically returns a single value such as `BigDecimal` or `String`.
- `REF_CURSOR` returns multiple rows and multiple columns.
- The application must read the result set and map each row to an entity, DTO, or scalar.

Some DBMSs use dedicated cursor outputs, such as Oracle's **SYS_REFCURSOR**. PostgreSQL has a `refcursor` type whose cursor lifecycle is tied to the transaction. Other databases may return result sets directly from a procedure without using `REF_CURSOR` under the same semantics.

`REF_CURSOR` exists in Jakarta Persistence's **ParameterMode**, but actual execution capability depends on the provider, dialect, JDBC driver, and database. You cannot assume that a procedure using `REF_CURSOR` on Oracle will run as-is on MySQL or SQL Server.

## 10. Oracle REF_CURSOR example with EntityManager

Example of an Oracle procedure opening a `SYS_REFCURSOR`:

~~~sql
CREATE OR REPLACE PROCEDURE find_products (
    p_status IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_result FOR
        SELECT id, name, status, price
        FROM products
        WHERE status = p_status;
END;
/
~~~

Calling with Jakarta Persistence and Hibernate:

~~~java
@Transactional(readOnly = true)
public List<Product> findProductsByStatus(String status) {
    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
            "find_products",
            Product.class
        );

    query.registerStoredProcedureParameter(
        1,
        String.class,
        ParameterMode.IN
    );

    query.registerStoredProcedureParameter(
        2,
        Class.class,
        ParameterMode.REF_CURSOR
    );

    query.setParameter(1, status);
    query.execute();

    @SuppressWarnings("unchecked")
    List<Product> products = query.getResultList();

    return products;
}
~~~

In this example:

- Parameter 1 is `p_status`, mode `IN`.
- Parameter 2 is the cursor output, mode `REF_CURSOR`.
- `Product.class` instructs the provider to map cursor rows to the `Product` entity.
- The SQL inside the procedure must return all columns required by the `Product` mapping.

This example reflects `REF_CURSOR` support in Hibernate and Oracle JDBC. Cursor parameter type, registration order, and how the result set is fetched must be verified for your Hibernate version, dialect, and driver. Some combinations differ in how cursors are registered or retrieved; do not treat this code as guaranteed portable across all JPA providers.

## 11. REF_CURSOR and transactions

A cursor may depend on a transaction to keep database resources open while the application reads the results.

In PostgreSQL, a `refcursor` is typically a cursor name opened within a transaction; the cursor is no longer usable once the transaction ends. Therefore, read the result set inside an appropriate transaction and do not return a cursor/handle outside the service for a controller to read later.

A safe rule of thumb:

1. Start the transaction.
2. Call the procedure and obtain the cursor.
3. Read all needed data.
4. Convert results to DTOs if necessary.
5. End the transaction after reading is complete.

Do not open a cursor in a transaction and close the transaction before a serializer or client reads the cursor. If you need to paginate across a large dataset, consider a dedicated query/pagination design rather than holding a cursor open across multiple HTTP requests.

## 12. Mapping REF_CURSOR to a DTO or scalar

If the cursor returns columns that do not correspond completely to an entity, use a result-set mapping or DTO.

DTO example:

~~~java
public record ProductRow(
    Long id,
    String name,
    BigDecimal price
) {
}
~~~

You can declare **@SqlResultSetMapping** with **@ConstructorResult** and then create a `StoredProcedureQuery` using the mapping name:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "find_product_rows",
        "ProductRowMapping"
    );
~~~

Then register the `IN` and `REF_CURSOR` parameters according to the procedure signature, set inputs, execute, and retrieve the result list. Column data types and constructor order must match the mapping.

If using an entity result mapping, the cursor must return all columns required by the entity mapping. Do not map a reduced set of columns to a full entity merely because the result set includes the ID.

## 13. Support capabilities by database

The table below is a practical guide, not a guarantee matrix for every version:

| Database | IN | OUT | INOUT | REF_CURSOR |
|---|---|---|---|---|
| Oracle | Widely supported | Widely supported | Supported | `SYS_REFCURSOR` widely used; requires compatible driver/provider |
| PostgreSQL | Supported by procedure/function signature | Supported depending on routine type and version | Supported by signature | `refcursor` has specific transaction semantics; check Hibernate/driver |
| MySQL | Supported | Supported | Supported | Typically returns result sets via SELECT from the procedure; not identical to Oracle `SYS_REFCURSOR` |
| SQL Server | Supported | Supported via `OUTPUT` parameter | Usable depending on routine syntax | Typically returns result sets via SELECT; cursor parameters have SQL Server-specific semantics |

Points to verify:

- Whether the database version supports procedures and the mode in use.
- Whether the JDBC driver supports `CallableStatement` and the corresponding output parameters.
- Whether the Hibernate dialect properly handles parameter modes and cursors.
- Whether the provider requires registering `REF_CURSOR` with a specific type.
- The order in which the procedure returns result sets, update counts, and OUT parameters.
- Whether an open transaction is required for the entire duration of cursor reading.

For databases that do not offer `REF_CURSOR` with the desired semantics, you can use directly returned result sets, separate queries, temporary tables, or another database-specific mechanism. Choose a solution based on actual capabilities rather than forcing every database into the same procedure signature.

## 14. Handling multiple result sets and update counts

A stored procedure can return multiple result sets or update counts before returning output parameters. In such cases, calling **getResultList()** once may not be enough.

Jakarta Persistence provides APIs such as:

- **execute()** to initiate execution.
- **getResultList()** to read the current result set.
- **hasMoreResults()** to check for the next result set.
- **getUpdateCount()** to retrieve the current update count.
- **getOutputParameterValue()** to read OUT/INOUT parameters.

The sequence of result sets and update counts depends on the procedure, JDBC driver, and provider. For procedures with multiple results, test the actual order. Do not assume all OUT parameters can always be read before consuming all result sets if the driver requires sequential result processing.

## 15. Bulk procedures and the persistence context

A stored procedure can update or delete data directly in the database. If the procedure modifies rows that JPA is managing, the persistence context may retain old values.

Example:

1. Application loads `Product` id 10 as a managed entity.
2. Stored procedure updates `price` in the database.
3. The `Product` object in the persistence context still holds the old price.
4. Subsequent code reads the object and sees stale data.

Before calling a procedure, consider flushing if the procedure needs to see pending JPA changes. After a procedure that writes data, consider refreshing related entities or clearing the persistence context.

~~~java
@Transactional
public void recalculatePrice(Long productId) {
    entityManager.flush();

    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery("recalculate_price");

    query.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN);
    query.setParameter(1, productId);
    query.execute();

    entityManager.clear();
}
~~~

**clear()** detaches all managed entities in the current persistence context. Use it only after handling changes you want to keep and with the understanding that referenced objects will become detached.

Procedures performing direct DML bypass the normal entity lifecycle. Therefore, they do not automatically invoke Spring Data JPA Auditing listeners or create Envers revisions as happens when modifying entities through Hibernate. If auditing is needed, record audit metadata/history explicitly within the same transaction or design an appropriate database-level mechanism.

## 16. Transactions, errors, and security

Calling a stored procedure should generally reside inside a service method with explicit transaction boundaries:

~~~java
@Service
public class ProductProcedureService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public BigDecimal calculateDiscount(BigDecimal amount) {
        StoredProcedureQuery query =
            entityManager.createStoredProcedureQuery("calculate_discount");

        query.registerStoredProcedureParameter(
            "p_amount", BigDecimal.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
            "p_discount", BigDecimal.class, ParameterMode.OUT);

        query.setParameter("p_amount", amount);
        query.execute();

        return (BigDecimal)
            query.getOutputParameterValue("p_discount");
    }
}
~~~

Things to watch out for:

- Commit/rollback rules and whether a procedure can control transactions itself depend on the database. Avoid letting a procedure self-commit if it must participate in a Spring-managed transaction.
- Catch and translate database errors at the service boundary; do not return raw SQL errors to clients.
- Use parameter binding; do not concatenate input into procedure names or SQL content.
- Control `EXECUTE` privileges on procedures per database user.
- Manage procedures via versioned migrations, such as Flyway or Liquibase.
- Monitor timeouts, locks, deadlocks, and execution plans just as with other SQL queries.

Procedure names, schemas, and identifiers cannot be bound like ordinary parameter values. If you must select a procedure based on input, use an allowlist of valid names instead of arbitrary string concatenation.

## 17. Testing each mode against a real database

Tests with H2 can be helpful for basic JPA flows, but they do not prove that procedures or `REF_CURSOR` are compatible with Oracle/PostgreSQL/MySQL/SQL Server. Procedure syntax, output binding, cursors, and driver behavior must be verified against the target database.

An integration test suite should cover:

- `IN` receiving the right value and filtering the right data.
- `OUT` returning the right type, precision, and scale.
- `INOUT` receiving the initial value and returning the updated value.
- `REF_CURSOR` returning the expected row count, columns, and mapped types.
- Procedures returning an empty result set.
- Procedures raising errors or constraint violations.
- Transaction rollback leaving no unexpected changes.
- Procedures updating data without leaving managed entities in stale state.
- Multiple output parameters or multiple result sets being read in the proper order.

You can use Testcontainers with the appropriate database image to run integration tests close to production. If the CI environment cannot run the production database, you still need a periodic test suite running against the exact deployed engine and driver.

## 18. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Wrong parameter index | Registration order differs from procedure signature | Cross-check database parameter order |
| Cannot read OUT | Not yet executed or wrong name/position | Execute successfully before calling `getOutputParameterValue` |
| INOUT returns old value | Wrong parameter assigned or procedure did not update it | Verify mode, input, and procedure logic |
| REF_CURSOR unsupported | Driver/provider/dialect combination does not support it | Check version matrix and use an appropriate API |
| Cursor invalidated | Transaction ended before reading completed | Read cursor inside the transaction |
| Returned entity missing fields | Cursor result set lacks full entity columns | Use complete entity mapping or a DTO |
| Spring Data method fails to map multiple outputs | Incompatible return type signature/metadata | Use named stored procedure and `Map` or `EntityManager` |
| Procedure runs but in-memory entity is stale | Direct DML bypasses persistence context sync | Flush beforehand, refresh/clear afterward |
| Auditing/Envers does not record history | Procedure modifies data outside entity lifecycle | Write audit explicitly or use DB auditing |
| Passes in dev but fails in production | Different database, driver, dialect, or schema | Integration test on the production engine |
| Wrongly calling function/procedure | Database distinguishes how routines are invoked | Check routine type and dialect invocation syntax |

## 19. Checklist for choosing and using ParameterMode

- [ ] Use **IN** when only passing data into a procedure.
- [ ] Use **OUT** when a procedure returns a scalar value.
- [ ] Use **INOUT** when a procedure needs an initial value and returns a processed value.
- [ ] Use **REF_CURSOR** when the database/provider supports cursor output and multiple rows need to be read.
- [ ] Register all parameters before `execute`.
- [ ] Match names or positions, data types, and modes exactly to the procedure signature.
- [ ] Read `OUT`/`INOUT` after `execute` succeeds.
- [ ] Use `EntityManager` `StoredProcedureQuery` when detailed control is needed.
- [ ] Use Spring Data `@Procedure` for simple, well-tested signatures.
- [ ] Verify `REF_CURSOR` with your specific database, dialect, JDBC driver, and transaction setup.
- [ ] Map a cursor to an entity only when the result set has all required columns; otherwise, use a DTO.
- [ ] Flush/refresh/clear the persistence context when a procedure modifies managed data.
- [ ] Do not assume procedure DML automatically triggers Spring Data Auditing or Envers.
- [ ] Write integration tests against the exact production database engine.

## 20. Conclusion

**IN** passes data in; **OUT** returns data out; **INOUT** accepts an initial value and returns a processed value; **REF_CURSOR** provides a set of result rows via a cursor. Jakarta Persistence defines these modes via `ParameterMode` and allows registration via `StoredProcedureQuery`.

Actual support varies across databases, JDBC drivers, Hibernate dialects, and Spring Data JPA versions. In particular, `REF_CURSOR` is not a portable contract that runs unmodified on every database. Use `@Procedure` for simple cases, `EntityManager` when you need control over multiple outputs/cursors, read cursors within a transaction, and test against the exact database you will deploy to.