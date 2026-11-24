# SimpleJdbcCall with Procedures or Functions

`SimpleJdbcCall` is a **Spring JDBC** API for calling existing *stored procedures* or *stored functions* in a database. This class wraps most of the work with JDBC `CallableStatement`: building the call string, binding `IN` parameters, registering `OUT`/`INOUT` parameters, executing, and converting results back to Java. It is especially useful when a system already places part of its data processing in stored routines and the Spring application needs to call them through an explicit contract.

Lesson objectives: distinguish procedures and functions; know when to use `withProcedureName(...).execute(...)` vs `withFunctionName(...).executeFunction(...)`; declare and read parameters properly; understand dependencies on JDBC metadata, transactions, SQL types, and the RDBMS.

## 1. Two types of stored routines and their results

A **stored procedure** is a database-side routine invoked as an operation. Depending on the DBMS, a procedure can read/write data, return `OUT`/`INOUT` parameters, produce `ResultSet`s, or execute multiple statements. For example: `reserve_stock(sku, quantity, OUT reserved)` reserves inventory and indicates whether a record was updated.

A **stored function** is a routine that returns a single value via the database's `RETURN` mechanism. For example: `stock_left(sku)` returns the current available stock quantity. Rules about what SQL is allowed inside a function, *determinism*, and transactional impact vary by DBMS.

| Criterion | Procedure | Function |
| --- | --- | --- |
| Configuring `SimpleJdbcCall` | `withProcedureName("reserve_stock")` | `withFunctionName("stock_left")` |
| Typical execution method | `execute(Map / SqlParameterSource / args)` | `executeFunction(Integer.class, inputs)` |
| Typical Java result | `Map<String, Object>` containing `OUT`/`INOUT` values and mapped results | Return value cast/read according to the requested `Class<T>` |
| Parameters | `IN`, `OUT`, `INOUT` as supported by the DBMS | Typically accepts `IN`; the `RETURN` value is the main result |
| When a single `OUT` value is needed | `executeObject(T.class, ...)` can be used for a suitable procedure | Use `executeFunction(T.class, ...)` |
| JDBC call style | Equivalent to `{call proc(?, ...)}` | Equivalent to `{? = call func(?, ...)}` |

This is a **difference in calling contract**, not a guarantee that procedures always write data or functions always read data. When designing, always inspect the actual routine definition in the database.

### Internal processing flow

1. Configure `SimpleJdbcCall`: datasource/`JdbcTemplate`, routine name, schema/catalog if needed, and parameter list or metadata.
2. `SimpleJdbcCall` is *compiled* upon `compile()` or automatically on the first `execute(...)`: it constructs the call string and the list of parameters to bind/register. This is **compiling the call configuration**, not compiling an SQL routine from Java.
3. Spring uses a JDBC `CallableStatement` on a `Connection` managed by `DataSource`, binds the `IN` values, and executes.
4. Spring reads `OUT`/`INOUT`, the function return, and any declared result sets to build the `Map` or single Java value.

Once configured and compiled, a `SimpleJdbcCall` instance can be reused across multiple calls/threads. Typically it is constructed once in a DAO/repository or Spring bean; **do not modify its configuration while it is in use**.

## 2. Key APIs to remember

| API | Role |
| --- | --- |
| `new SimpleJdbcCall(dataSource)` or `new SimpleJdbcCall(jdbcTemplate)` | Creates the routine caller object |
| `withProcedureName(name)` | Marks the call as a procedure |
| `withFunctionName(name)` | Marks the call as a function |
| `withSchemaName(name)` / `withCatalogName(name)` | Specifies the namespace when the routine is not found by default name; schema/catalog semantics depend on the driver |
| `declareParameters(...)` | Declares the parameter contract on the Java side |
| `withoutProcedureColumnMetaDataAccess()` | Skips automatic reading of parameter column metadata, relying only on manual declarations |
| `execute(Map)` / `execute(SqlParameterSource)` | Invokes the routine and receives a map containing `OUT`/`INOUT`/declared results |
| `executeFunction(T.class, ...)` | Invokes a function and retrieves the `RETURN` value of type `T` |
| `executeObject(T.class, ...)` | Convenience method to retrieve a single `OUT` value from a suitable procedure |
| `returningResultSet(name, rowMapper)` | Declares mapping for a result set returned by the routine |
| `withNamedBinding()` | Requests JDBC named parameter binding when supported by the driver; distinct from using a map to supply parameters |

Parameter classes:

- `new SqlParameter("p_sku", Types.VARCHAR)` declares an `IN` input parameter.
- `new SqlOutParameter("p_done", Types.INTEGER)` declares an `OUT` output parameter.
- `new SqlInOutParameter("p_count", Types.INTEGER)` declares an `INOUT` parameter that both receives and returns a value.
- `MapSqlParameterSource` passes values by **declared application parameter name**, helping reduce ordering mistakes. With default JDBC binding, Spring still orders parameters positionally when calling the driver.
- `Types.INTEGER`, `Types.VARCHAR`, `Types.DECIMAL`, etc. are SQL types in `java.sql.Types`, **not** Java classes like `Integer`, `String`, `BigDecimal`. The declared type must match the routine and JDBC driver.

**Note:** `SqlOutParameter` must not be used as an input value source when executing `SimpleJdbcCall`; for values that are both input and output, use `SqlInOutParameter`.

## 3. Runnable Java 17+ example with MySQL: one procedure and one function

The following example has exactly **one procedure that updates inventory and returns an `OUT` parameter** and **one function that reads inventory and returns a scalar value**. MySQL 8.4 is chosen because MySQL clearly supports `IN`/`OUT` alongside stored SQL functions; procedure/function syntax varies across DBMSs.

### 3.1. Setting up data and routines

Create `schema.sql`:

```sql
DROP PROCEDURE IF EXISTS reserve_stock;
DROP FUNCTION IF EXISTS stock_left;
DROP TABLE IF EXISTS inventory;

CREATE TABLE inventory (
    sku VARCHAR(32) PRIMARY KEY,
    available INT NOT NULL
);

INSERT INTO inventory (sku, available)
VALUES ('BOOK', 5);

DELIMITER //

CREATE PROCEDURE reserve_stock(
    IN p_sku VARCHAR(32),
    IN p_amount INT,
    OUT p_done INT
)
MODIFIES SQL DATA
BEGIN
    IF p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    UPDATE inventory
       SET available = available - p_amount
     WHERE sku = p_sku
       AND available >= p_amount;

    SET p_done = ROW_COUNT();
END//

CREATE FUNCTION stock_left(p_sku VARCHAR(32))
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_available INT DEFAULT 0;

    SELECT COALESCE(MAX(available), 0)
      INTO v_available
      FROM inventory
     WHERE sku = p_sku;

    RETURN v_available;
END//

DELIMITER ;
```

Explanation: the `reserve_stock` procedure decrements quantity only when enough stock remains; `ROW_COUNT()` is read immediately after `UPDATE`. Because `p_amount` must be positive and the `UPDATE` targets a specific primary-key SKU, `p_done = 1` means stock was reserved, while `0` means no row was updated. On SQL errors, it throws an error instead of returning a fake success flag. The `stock_left` function reads inventory, returning `0` if the SKU has no record. This example does not yet model the entire ordering business flow.

`DELIMITER //` is a **command of the `mysql` command-line client** to prevent `;` inside `BEGIN ... END` from terminating the definition prematurely; it is not an SQL statement sent verbatim over JDBC. In an SQL migration tool, use that tool's own mechanism for routine definitions.

### 3.2. Project configuration

Create `settings.gradle`:

```groovy
rootProject.name = 'simple-jdbc-call-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.mysql:mysql-connector-j:9.4.0'
}

application {
    mainClass = 'SimpleJdbcCallDemo'
}
```

Use **JDK 17 or later** and a Java 17-compatible Gradle version. The JDBC driver is downloaded by Gradle, so you can run via `gradle run` without manually listing every JAR on the classpath. On systems with Gradle Wrapper, use `./gradlew run` or `gradlew.bat run` accordingly.

### 3.3. Complete Java code

Create `src/main/java/SimpleJdbcCallDemo.java`:

```java
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class SimpleJdbcCallDemo {
    private SimpleJdbcCallDemo() {
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("com.mysql.cj.jdbc.Driver");
        dataSource.setUrl(
            "jdbc:mysql://127.0.0.1:3307/simple_call_demo" +
            "?sslMode=DISABLED&allowPublicKeyRetrieval=true"
        );
        dataSource.setUsername("root");
        dataSource.setPassword("demo");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        SimpleJdbcCall reserveStock = new SimpleJdbcCall(jdbc)
            .withProcedureName("reserve_stock")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("p_sku", Types.VARCHAR),
                new SqlParameter("p_amount", Types.INTEGER),
                new SqlOutParameter("p_done", Types.INTEGER)
            );

        SimpleJdbcCall stockLeft = new SimpleJdbcCall(jdbc)
            .withFunctionName("stock_left")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlOutParameter("return_value", Types.INTEGER),
                new SqlParameter("p_sku", Types.VARCHAR)
            );

        System.out.println("Before: " + remaining(stockLeft, "BOOK"));

        int success = reserve(reserveStock, "BOOK", 2);
        System.out.println("Reserve 2: " + success);
        System.out.println("After reserve: " + remaining(stockLeft, "BOOK"));

        int insufficient = reserve(reserveStock, "BOOK", 10);
        System.out.println("Reserve 10: " + insufficient);
        System.out.println("After insufficient: " + remaining(stockLeft, "BOOK"));
    }

    private static int reserve(
        SimpleJdbcCall procedure,
        String sku,
        int quantity
    ) {
        MapSqlParameterSource input = new MapSqlParameterSource()
            .addValue("p_sku", sku)
            .addValue("p_amount", quantity);

        Map<String, Object> output = procedure.execute(input);
        Object raw = output.get("p_done");
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                "Expected numeric OUT parameter p_done, got: " + raw
            );
        }
        return number.intValue();
    }

    private static int remaining(SimpleJdbcCall function, String sku) {
        Integer value = function.executeFunction(
            Integer.class,
            new MapSqlParameterSource().addValue("p_sku", sku)
        );
        if (value == null) {
            throw new IllegalStateException(
                "Function stock_left unexpectedly returned NULL"
            );
        }
        return value;
    }
}
```

In this lesson, `DriverManagerDataSource` is for a small demo: it is not a connection pool meant for high-load production systems. The `root/demo` credentials and `sslMode=DISABLED` are only for **local MySQL used for learning**, not as a real deployment configuration.

Most important points in the code:

1. The procedure takes two `IN` parameters and one `OUT` parameter; `execute(input)` returns a map, from which `p_done` is read as a number. **Do not** call `executeFunction` for this procedure.
2. The function has one input and one return slot. In manual declaration mode, `SqlOutParameter("return_value", Types.INTEGER)` must come **before** the input parameters to map the JDBC `{? = call stock_left(?)}` positions. `executeFunction(Integer.class, input)` returns the value directly without needing to access a map.
3. `withoutProcedureColumnMetaDataAccess()` makes Spring use the exact declared list. Thus, parameter names/types/positions become a contract that must stay synchronized with the SQL definition.
4. `setResultsMapCaseInsensitive(true)` reduces errors caused by drivers/databases altering the letter casing of `OUT` parameter names. Using a map for inputs **does not** mean the driver is using named binding; Spring may still bind positionally.
5. Both `SimpleJdbcCall` objects are created once and then invoked repeatedly. In a real Spring application, place them in a bean/DAO with a framework-managed `DataSource`.

### 3.4. Running and comparing results

Use a test MySQL 8.4 instance. For example with Docker, create a container with database `simple_call_demo`:

```bash
docker run --rm --name simplejdbc-mysql -d \
  -e MYSQL_ROOT_PASSWORD=demo \
  -e MYSQL_DATABASE=simple_call_demo \
  -p 3307:3306 mysql:8.4
```

Once MySQL reports ready, run the script **once before running Java**:

```bash
docker exec -i simplejdbc-mysql \
  mysql -uroot -pdemo simple_call_demo < schema.sql

gradle run --quiet
```

On Windows PowerShell, you can pipe the SQL file content instead of using Bash's `<` syntax:

```powershell
Get-Content -Raw schema.sql |
    docker exec -i simplejdbc-mysql mysql -uroot -pdemo simple_call_demo

gradle run --quiet
```

When running with the freshly created schema, **the Java program's stdout** is:

```text
Before: 5
Reserve 2: 1
After reserve: 3
Reserve 10: 0
After insufficient: 3
```

Initially there are 5 items; reserving 2 succeeds so 3 remain. The second attempt requests 10 items, `UPDATE` affects no rows so `OUT p_done = 0` and available stock stays at 3. This is the routine's result on the sample data; in real business logic, you should decide how to represent "insufficient stock" (result 0, a domain exception, or a dedicated status).

If you run Java again **without re-running `schema.sql`**, the inventory has already been modified, so subsequent stdout will no longer match the example. If the MySQL script fails due to function-creation privileges (especially when binary logging is enabled), check `CREATE ROUTINE` privileges/MySQL configuration in the test environment rather than arbitrarily changing the `SimpleJdbcCall` contract.

## 4. Letting Spring read parameters automatically from metadata

With drivers/databases that support full metadata, the code is shorter:

```java
// Placed inside a DAO that has been injected with JdbcTemplate jdbc.
SimpleJdbcCall readStock = new SimpleJdbcCall(jdbc)
    .withFunctionName("stock_left");

Integer available = readStock.executeFunction(
    Integer.class,
    new MapSqlParameterSource().addValue("p_sku", "BOOK")
);
```

This is an **illustrative snippet placed inside a DAO**, not a standalone Java file. Spring queries `DatabaseMetaData` provided by the JDBC driver to try to locate the routine and the order/names/types of its parameters. This automatic approach is convenient when metadata is reliable, metadata query permissions are sufficient, and routines are unambiguous.

When metadata is inaccurate or inaccessible:

- Use `withoutProcedureColumnMetaDataAccess().declareParameters(...)` to explicitly declare all parameters in database order.
- If you declare only a **subset** of parameters without disabling metadata, Spring may pull the rest from the driver. Therefore, choose a clear strategy and test against the actual deployment DB/driver.
- For routines sharing names or across multiple schemas/catalogs, specify `withSchemaName`/`withCatalogName` when needed. Do not assume all DBs interpret these two names identically: in MySQL, for example, the database name is typically exposed by the driver as a *catalog*.
- Errors such as `Unable to determine the correct call signature`, wrong `OUT` positions, wrong names, or JDBC `SQLException`s usually require inspecting **the routine DDL + actual metadata + name/type info**, rather than guessing solely from Java lines.
- `withNamedBinding()` requires driver support for named binding. Only use it once verified on the target driver/database; passing a `MapSqlParameterSource` does not require enabling this option.

## 5. Reading `OUT`, `INOUT`, and `ResultSet` results

### Procedures with multiple `OUT` parameters

Suppose the database defines the routine `read_profile(IN p_id, OUT p_name, OUT p_status)`; it can be declared as:

```java
// Illustrative code in a DAO; requires the corresponding read_profile routine in the DB.
SimpleJdbcCall readProfile = new SimpleJdbcCall(jdbc)
    .withProcedureName("read_profile")
    .withoutProcedureColumnMetaDataAccess()
    .declareParameters(
        new SqlParameter("p_id", Types.BIGINT),
        new SqlOutParameter("p_name", Types.VARCHAR),
        new SqlOutParameter("p_status", Types.VARCHAR)
    );

Map<String, Object> out = readProfile.execute(
    new MapSqlParameterSource().addValue("p_id", 42L)
);
String name = (String) out.get("p_name");
String status = (String) out.get("p_status");
```

The returned map contains output parameters under the declared names or names supplied by the database. Check types and handle `null`; do not assume the procedure always returns every value if no record is found. With **only a single OUT**, `executeObject(String.class, input)` may be suitable for retrieving the value directly.

### `INOUT` as both an input and output value

If a routine has an `INOUT p_counter INT` parameter, use:

```java
// Illustrative code; the DB must actually define INOUT p_counter.
SimpleJdbcCall increment = new SimpleJdbcCall(jdbc)
    .withProcedureName("increment_counter")
    .withoutProcedureColumnMetaDataAccess()
    .declareParameters(
        new SqlInOutParameter("p_counter", Types.INTEGER)
    );

Map<String, Object> out = increment.execute(
    new MapSqlParameterSource().addValue("p_counter", 3)
);
Number updated = (Number) out.get("p_counter");
```

This snippet requires importing `org.springframework.jdbc.core.SqlInOutParameter` and a corresponding `increment_counter` routine. The returned value depends on the SQL definition; do not assume it is always 4 without knowing how the routine processes it.

### Routines returning data rows

A procedure can return one or more `ResultSet`s. `returningResultSet(name, RowMapper)` lets Spring map each row:

```java
// Suppose procedure list_orders() produces a ResultSet containing id, status.
record OrderRow(long id, String status) {}

SimpleJdbcCall listOrders = new SimpleJdbcCall(jdbc)
    .withProcedureName("list_orders")
    .returningResultSet(
        "orders",
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getString("status")
        )
    );

Map<String, Object> out = listOrders.execute(Map.of());
@SuppressWarnings("unchecked")
List<OrderRow> rows = (List<OrderRow>) out.get("orders");
```

This snippet requires importing `java.util.List`, `java.util.Map`, and a `list_orders` routine returning the matching columns. How result sets are received **varies by DBMS**:

- For result sets returned directly during JDBC result processing, `"orders"` is a Java-chosen map key; with multiple result sets, the declaration order of `returningResultSet` must match the return order.
- For **REF CURSOR** on databases that support it, you may need to declare an `OUT` parameter with the exact cursor parameter name and appropriate SQL type, such as `Types.REF_CURSOR` when supported by the driver. The parameter name is not an arbitrary label.
- Mapping with `RowMapper` only defines how rows are converted into objects; it does not create the routine or manage transaction lifecycles on behalf of the application.

## 6. Transactions, errors, and success boundaries

`SimpleJdbcCall` simplifies JDBC operations, **without magically extending transaction scope**. When invoked via the same `DataSource` inside an active Spring `@Transactional` method, the routine normally uses the connection belonging to that transaction. However, some routines/DBMSs contain auto-commit statements, DDL, or separate transaction rules; you must check the specific definition and DBMS.

Spring service example:

```java
// Illustrative service method; reserveStock is a SimpleJdbcCall
// configured in the DAO and invoked through a Spring-managed bean.
@Transactional
public void reserveOrFail(String sku, int quantity) {
    int affected = repository.reserve(sku, quantity);
    if (affected != 1) {
        throw new IllegalStateException("OUT_OF_STOCK");
    }
}
```

If a `DataAccessException` or runtime exception escapes the `@Transactional` method and the call goes **through the Spring proxy**, Spring normally marks the transaction for rollback under default rules. If the routine itself executes `COMMIT`, the outcome and the application's rollback capability must be evaluated separately. `OUT p_done=1` is only a signal defined by the SQL routine; it does not prove that external steps such as payment or event publishing have completed.

Do not take a procedure name directly from user input: the routine name is assembled into the call statement, whereas **parameter values** are what JDBC binds safely. Restrict database privileges to only the routines that must be called, consider `SQL SECURITY DEFINER/INVOKER` according to your access-control design, and avoid logging sensitive data from inputs/outputs.

## 7. When to use `SimpleJdbcCall`, and when to consider alternatives?

Use `SimpleJdbcCall` when the database already provides stable procedures/functions, when you need to handle `IN`/`OUT`/`INOUT`, or when you want to reuse a controlled call configuration. It is also useful when working directly with JDBC without needing ORM/JPA for that feature.

If you only need to call a simple SQL scalar function and do not need a `CallableStatement` contract, some DBMSs also allow:

```java
// MySQL-style example, when only reading a single value.
Integer available = jdbc.queryForObject(
    "SELECT stock_left(?)",
    Integer.class,
    "BOOK"
);
```

This approach can be simpler, though it depends on DBMS SQL syntax. Procedures with `OUT` parameters or multiple `ResultSet`s are usually better suited to `SimpleJdbcCall`/`CallableStatement`. For logic that fits naturally in Java, there is no need to push it onto the DB just to have a reason to call stored routines; weigh portability, observability, versioning, and testability before placing business logic in the DB.

## 8. Common errors and how to diagnose them

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Routine not found | Wrong name, schema/catalog, letter casing, `EXECUTE` privilege | Check DDL, driver-specific namespace semantics, and connection user privileges |
| `OUT` is always `null` or wrong key | Different `OUT` name, function return not registered, routine did not assign a value | Read the exact map key, inspect DDL; enable case-insensitive map if needed |
| Missing/invalid parameter error | Mismatched JDBC metadata, wrong SQL type, or wrong order | Declare parameters explicitly and disable metadata; prioritize checking the actual routine |
| Calling a function like a procedure | Using `withProcedureName` and expecting `RETURN` like a function | Choose `withFunctionName` + `executeFunction` |
| Calling a procedure like a function | Procedure has `OUT` parameters but `executeFunction` was used | Use `execute`, or `executeObject` if there is exactly one `OUT` |
| Returned map has confusing multiple results | Procedure returns multiple `OUT` parameters/result sets/update counts | Declare `returningResultSet`, align result order and names |
| Different results across consecutive runs | Routine mutates data; input data has changed | Reset test fixtures before each integration test, clearly separate stateful vs read-only tests |
| Transaction does not roll back as expected | Bypassed proxy, different `DataSource`, swallowed exception, or routine/DB committed on its own | Check transaction boundaries, DDL, rollback rules, and connections |
| High call latency | Slow routine, lock contention, expensive internal queries | Use DB-side EXPLAIN/monitoring, transaction timeouts, and appropriate latency logging |

A solid integration test checklist should use the **actual target DB/driver** and verify: `IN`/`OUT` order, `null` values, parameter name casing, sufficient/insufficient data, concurrent calls, modified row counts, commit/rollback, routine errors, and permissions. Unit tests mocking `SimpleJdbcCall` cannot replace testing the JDBC driver together with real stored routines.

## 9. Takeaways when applying in practice

- **Procedure:** `withProcedureName(...)` → declare `IN/OUT/INOUT` matching the DDL → `execute(...)` → read the output map or mapped result sets.
- **Function:** `withFunctionName(...)` → declare inputs/return (if metadata is disabled) → `executeFunction(ReturnType.class, ...)` → receive the value.
- **Metadata:** convenient when the driver reflects it accurately; if unreliable, `withoutProcedureColumnMetaDataAccess().declareParameters(...)` forces Java to fully describe the exact order/types.
- **Results:** SQL outputs must be interpreted according to the business contract; `OUT = 1` or a function return value does not by itself prove that external systems succeeded.
- **Deployment:** keep routines versioned/migrated, use a consistent `DataSource` with transactions, apply least-privilege DB permissions, test with the exact target DBMS/driver, and reuse configured `SimpleJdbcCall` instances.

### References

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html)
- [Spring Framework — SimpleJdbcCall API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [MySQL 8.4 — CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL Connector/J — Using CallableStatements](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
