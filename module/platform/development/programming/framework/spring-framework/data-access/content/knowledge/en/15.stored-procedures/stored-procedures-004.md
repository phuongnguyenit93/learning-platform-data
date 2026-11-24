# `SqlParameter`, `SqlOutParameter`, and `SqlInOutParameter` in Spring JDBC

## 1. What problem do the three parameter types solve?

When calling a **stored procedure** or **stored function**, JDBC needs to know which parameters pass values in, which receive results, and which both receive an initial value and get updated by the procedure. Low-level JDBC uses `CallableStatement` with operations such as `setObject(...)`, `registerOutParameter(...)`, `execute()`, and `getObject(...)`.

Spring JDBC represents those descriptions with three classes in package `org.springframework.jdbc.core`:

| Spring class | SQL direction | Has input value? | Has output value? | Purpose |
| --- | --- | --- | --- | --- |
| `SqlParameter` | `IN` | Yes | No | Declares the name and SQL type of input data sent in |
| `SqlOutParameter` | `OUT` | No, in standard `SimpleJdbcCall` usage | Yes | Declares a result returned by the procedure |
| `SqlInOutParameter` | `INOUT` | Yes | Yes | Declares a parameter sent in and received back after modification |

These three classes are **parameter descriptors** (metadata for the call), **not containers holding business values**. Actual values are passed using a `Map` or `SqlParameterSource` when invoking `SimpleJdbcCall.execute(...)`. SQL types come from `java.sql.Types`, such as `Types.INTEGER`, `Types.VARCHAR`, `Types.DECIMAL`, `Types.DATE`.

**Important distinction:** `SqlParameter` (a *declaration* class) differs from `SqlParameterSource` (a *value-supplying* interface). A `MapSqlParameterSource` object can specify the type for an input value via `addValue(name, value, sqlType)`, but it does not replace `SqlOutParameter` for registering output parameters.

### Mechanism at the JDBC level

Compare against a procedure with three parameters in the exact order `IN`, `OUT`, `INOUT`:

```java
// Pure JDBC fragment; assumes Connection connection already exists.
try (java.sql.CallableStatement cs =
         connection.prepareCall("{call accumulate_invoice(?, ?, ?)}")) {
    cs.setBigDecimal(1, new java.math.BigDecimal("200.00")); // IN
    cs.registerOutParameter(2, java.sql.Types.DECIMAL);     // OUT
    cs.setBigDecimal(3, new java.math.BigDecimal("1000.00")); // INOUT: write input
    cs.registerOutParameter(3, java.sql.Types.DECIMAL);     // INOUT: register output

    cs.execute();

    java.math.BigDecimal tax = cs.getBigDecimal(2);
    java.math.BigDecimal total = cs.getBigDecimal(3);
}
```

`SimpleJdbcCall` performs the corresponding steps from those descriptor objects. Positional indices in `CallableStatement` start at **1**, and parameter names and declared types must match the actual procedure in the database.

## 2. Understanding each class individually

### `SqlParameter` — `IN` input

```java
new SqlParameter("in_net", Types.DECIMAL)
```

This describes the procedure's first parameter, carrying a decimal number from Java to the database. Spring reads the value for `in_net` from the input source during execution. Some constructors accept an additional `scale` for decimals or `typeName` for DBMS-defined types; you do not need them when a basic type suffices.

**Note:** declaring a `SqlParameter` does not mean Spring will automatically find a value from a Java variable of the same name. You must supply the value via a `Map` or `SqlParameterSource`.

### `SqlOutParameter` — `OUT` output

```java
new SqlOutParameter("out_tax", Types.DECIMAL)
```

The `out_tax` result is retrieved from the output parameter after the procedure executes and appears in the result map returned by `SimpleJdbcCall.execute(...)`. Do not treat `out_tax` in the input data source as a required input value: it is a parameter for the procedure to write to.

When the DBMS returns a custom type or a `REF CURSOR`, `SqlOutParameter` also supports a `RowMapper` or `SqlReturnType` to customize output conversion (only configure according to driver/DBMS capabilities).

### `SqlInOutParameter` — bidirectional `INOUT`

```java
new SqlInOutParameter("inout_grand_total", Types.DECIMAL)
```

Spring must **bind the initial value** for `inout_grand_total` and **register it to read back the new value**. After calling the procedure, the Java input object is not mutated by reference; the updated value must be retrieved from the output `Map`.

Example: `inout_grand_total` starts at `1000.00`, and the procedure adds `200.00` for goods plus `20.00` tax; the output is `1220.00`. If you only declare `SqlParameter`, Spring does not read the updated value back; if you only declare `SqlOutParameter` in `SimpleJdbcCall`, Spring does not bind the initial value under `INOUT` semantics.

In terms of inheritance, `SqlInOutParameter` is a subclass of `SqlOutParameter`, and `SqlOutParameter` ultimately extends `SqlParameter`. **Java inheritance does not mean all three types play the same role when binding data.** Spring's documented rule: in `SimpleJdbcCall`, `SqlParameter` and `SqlInOutParameter` declarations are used to supply inputs. The legacy `StoredProcedure` class had a backward-compatibility exception allowing `SqlOutParameter` inputs in some cases; do not rely on that exception to model `INOUT` in new code.

## 3. Complete example: one procedure using `IN`, `OUT`, and `INOUT`

The example below uses **MySQL 8.4**, **Java 17**, and **Spring JDBC 6.2.x**. The procedure only computes values (without writing to tables) to keep the distinction among the three parameter types clear. A running MySQL instance and routine creation/execution privileges are required.

### Step 1: Create the stored procedure and function

Open the MySQL CLI and run the contents of `setup.sql`:

```sql
CREATE DATABASE IF NOT EXISTS spring_parameter_demo;
USE spring_parameter_demo;

DROP PROCEDURE IF EXISTS accumulate_invoice;
DELIMITER //
CREATE PROCEDURE accumulate_invoice(
    IN in_net DECIMAL(12, 2),
    OUT out_tax DECIMAL(12, 2),
    INOUT inout_grand_total DECIMAL(12, 2)
)
BEGIN
    SET out_tax = ROUND(in_net * 0.10, 2);
    SET inout_grand_total = inout_grand_total + in_net + out_tax;
END //
DELIMITER ;

DROP FUNCTION IF EXISTS invoice_tax;
CREATE FUNCTION invoice_tax(p_net DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_net * 0.10, 2);
```

- `in_net`: net amount (input).
- `out_tax`: tax amount, computed by the procedure (output).
- `inout_grand_total`: running total, present before the call and updated by the procedure.
- `invoice_tax`: standalone function taking one value and returning a scalar value.

`DELIMITER //` is a **MySQL CLI command** to submit the entire `BEGIN ... END` block, not an SQL statement sent directly with `JdbcTemplate.execute(...)`. Use the equivalent syntax when running with a migration tool. The `INOUT` part is demonstrated **in a procedure**; a MySQL stored function only accepts input parameters and returns its result via `RETURN`.

For a net amount of `200.00`, 10% tax is `20.00`; an initial total of `1000.00` becomes `1220.00`.

### Step 2: Maven configuration (`pom.xml`)

Place the following file in the root directory of the Maven project; use Java 17 or newer. The two dependency versions below are concrete examples so the lesson can run standalone; in Spring Boot, let the project's dependency management control compatible versions.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>stored-routine-parameters</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.4.0</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### Step 3: Write `src/main/java/StoredRoutineParameterDemo.java`

This is a **complete Java class with `main`**. Connection details are read from environment variables instead of embedding credentials in source code.

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlInOutParameter;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class StoredRoutineParameterDemo {
    private StoredRoutineParameterDemo() {}

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
                requiredEnv("DB_URL"),
                requiredEnv("DB_USER"),
                requiredEnv("DB_PASSWORD"));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        // Declare once before execution: matching the SQL parameter order of the procedure.
        SimpleJdbcCall accumulate = new SimpleJdbcCall(jdbc)
                .withProcedureName("accumulate_invoice")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("in_net", Types.DECIMAL),
                        new SqlOutParameter("out_tax", Types.DECIMAL),
                        new SqlInOutParameter(
                                "inout_grand_total", Types.DECIMAL));

        // Only IN and INOUT require input values.
        var inputs = new MapSqlParameterSource()
                .addValue("in_net", new BigDecimal("200.00"), Types.DECIMAL)
                .addValue("inout_grand_total",
                        new BigDecimal("1000.00"), Types.DECIMAL);

        Map<String, Object> outputs = accumulate.execute(inputs);

        // OUT and INOUT are retrieved from the Map by their declared names.
        BigDecimal tax = (BigDecimal) outputs.get("out_tax");
        BigDecimal grandTotal =
                (BigDecimal) outputs.get("inout_grand_total");

        System.out.println("OUT out_tax = " + tax.toPlainString());
        System.out.println("INOUT inout_grand_total = "
                + grandTotal.toPlainString());

        // Stored function: with MySQL, Spring can look up metadata.
        SimpleJdbcCall taxFunction = new SimpleJdbcCall(jdbc)
                .withFunctionName("invoice_tax");
        BigDecimal functionTax = taxFunction.executeFunction(
                BigDecimal.class,
                new MapSqlParameterSource()
                        .addValue("p_net",
                                new BigDecimal("200.00"), Types.DECIMAL));

        System.out.println("FUNCTION invoice_tax = "
                + functionTax.toPlainString());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + name);
        }
        return value;
    }
}
```

This example uses `DriverManagerDataSource` for a short-lived learning program. In applications serving many requests, use a pooled `DataSource` and configure `SimpleJdbcCall` once at the repository/service layer instead of recreating it on every call.

### Step 4: Run and compare results

Create the two routines using `setup.sql` and grant appropriate privileges to the connection account. Set the three environment variables `DB_URL`, `DB_USER`, `DB_PASSWORD`; for example, point `DB_URL` to `jdbc:mysql://127.0.0.1:3306/spring_parameter_demo`. From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=StoredRoutineParameterDemo
```

**Expected stdout when running against the exact routines and data in this lesson:**

```text
OUT out_tax = 20.00
INOUT inout_grand_total = 1220.00
FUNCTION invoice_tax = 20.00
```

All three results depend solely on the routines' calculations, not on any table data. If the MySQL account lacks `CREATE ROUTINE` or `EXECUTE` privileges, if the schema/routine name is wrong, or if the driver cannot connect, the command will fail with an error; do not interpret a connection error as an error in the three parameter classes.

## 4. Reading the example along the execution flow

### Before execution

1. `withProcedureName("accumulate_invoice")` specifies the procedure to call; this is not an SQL `SELECT`.
2. `withoutProcedureColumnMetaDataAccess()` instructs Spring **not to probe metadata for the procedure's parameter list** and instead use the provided declarations.
3. `declareParameters(...)` defines all three parameters in **the DB signature order**, with matching directions and types.
4. `MapSqlParameterSource` supplies **two** inputs: `in_net` and `inout_grand_total`. `out_tax` is not supplied as an input.

### During execution

Spring builds the call through JDBC `CallableStatement`, binds the `IN` and `INOUT` values, registers output types for `OUT` and `INOUT`, and executes the procedure. Spring then reads the results and populates the output names in `Map<String,Object>`.

### After execution

- `outputs.get("out_tax")` is the new value computed by the procedure, even though there was no Java variable named `out_tax` before the call.
- `outputs.get("inout_grand_total")` is the **new value**; the input `BigDecimal("1000.00")` object is not modified in place. Do not inspect `inputs.getValue("inout_grand_total")` expecting to see `1220.00`.
- `executeFunction(BigDecimal.class, ...)` is for the **return value of a stored function**, rather than manually accessing an `OUT` key in a result `Map`. In MySQL, functions do not declare `OUT/INOUT` arguments; a function's `RETURN` value is a distinct concept.

A quick visual summary:

```text
Java input Map:
    in_net = 200.00                 (SqlParameter: IN)
    inout_grand_total = 1000.00     (SqlInOutParameter: INOUT)
    [no out_tax]                    (SqlOutParameter: OUT)
             |
             v
  CALL accumulate_invoice(...)
             |
             v
Java result Map:
    out_tax = 20.00                 (OUT)
    inout_grand_total = 1220.00     (INOUT)
```

## 5. Automatic metadata reading vs. manual declaration

**Default approach:** when supported by the driver and DBMS, `SimpleJdbcCall` can read metadata about parameter names, directions, and types. For example, a shorter configuration is:

```java
// Configuration fragment; works when the driver provides complete metadata.
SimpleJdbcCall procedure = new SimpleJdbcCall(jdbc)
        .withProcedureName("accumulate_invoice");
```

**Explicit approach:** use `declareParameters(...)` to declare part or all of the parameters. If you **do not** call `withoutProcedureColumnMetaDataAccess()`, Spring may still rely on metadata for undeclared parameters. When driver metadata is missing, inaccurate, or inconsistent, declare **all parameters in exact order** and disable parameter metadata lookup as shown in the main example.

This makes the call easier to control, especially when the procedure uses custom types or metadata is inconsistent. However, it does not guarantee that the DBMS/driver will never perform any other metadata operation. After changing a stored procedure's signature, **you must update the Java declarations**; Spring will not detect mismatches automatically once metadata lookup is disabled.

`useInParameterNames(...)` is an optional setting when you need to specify the exact set of input names for a signature, such as when multiple call variants exist. It does not replace accurately declaring `OUT`, `INOUT`, and SQL types.

**Result key casing may vary depending on the DBMS/driver.** You can configure `JdbcTemplate.setResultsMapCaseInsensitive(true)` and pass that `JdbcTemplate` to `SimpleJdbcCall` as shown, while still using the real SQL names inside `declareParameters(...)`.

## 6. Closely related advanced techniques

### Outputs that are `REF CURSOR` or custom types

Some databases allow returning a cursor via an output parameter. When supported by the driver and DBMS, you can declare `SqlOutParameter` with a `RowMapper`; this is a conceptual fragment, **not the MySQL routine from the example**:

```java
// Illustrative fragment for a DBMS/driver supporting REF_CURSOR.
SqlOutParameter cursorParameter = new SqlOutParameter(
        "out_items",
        Types.REF_CURSOR,
        (rs, rowNum) -> rs.getString("item_name"));
```

In this case, the name `out_items` and the JDBC type must match the DBMS's cursor protocol. Some drivers require vendor-specific constants or handling. For complex SQL types such as `STRUCT`/`ARRAY`, Spring also provides `SqlReturnType` for custom `OUT` value handling and `SqlTypeValue` for special `IN` data.

If a procedure returns a **direct result set** (for example, a `SELECT` statement inside a MySQL procedure) rather than an `OUT REF CURSOR` parameter, use `SimpleJdbcCall.returningResultSet("items", rowMapper)`. Do not arbitrarily declare a `SqlOutParameter` for a result set that has no corresponding `OUT` parameter name.

### Function returning a value vs. procedure with one `OUT`

- `withFunctionName(...)` + `executeFunction(ExpectedClass.class, inputs)`: retrieves a **function's return value**.
- `withProcedureName(...)` + `executeObject(ExpectedClass.class, inputs)`: convenient when a **procedure has a single suitable `OUT` parameter**.
- `execute(inputs)`: suitable when multiple `OUT`, `INOUT`, or result sets are needed and you want to access them by name from a `Map`.

Do not equate a function's `RETURN` value with a procedure's `OUT` parameter. If declaring a function return manually instead of relying on metadata, the position/name/type conventions for the return value depend on the JDBC driver; check the driver documentation and verify the actual call statement.

### `null` values in inputs or outputs

For nullable `IN` or `INOUT` parameters, declare the proper `Types.X` and set the input via `MapSqlParameterSource.addValue(name, null, sqlType)` when allowed by the DBMS. Note that SQL addition with `NULL` can yield `NULL`; the routine must explicitly decide whether to use `COALESCE` or preserve `NULL`. For `OUT`, the map may contain a key whose value is `null`: never cast or invoke methods on null without checking first. Types like `DECIMAL` and `NUMERIC` should use `BigDecimal` instead of `double` when decimal precision is required.

## 7. Common errors and how to diagnose them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Missing input parameter or bind error | Declared only `SqlOutParameter` for a parameter that is actually `INOUT` | Switch to `SqlInOutParameter` and supply an input value |
| `OUT` result missing from `Map` | Declared only `SqlParameter` or used the wrong name | Check the signature, declare `SqlOutParameter`, and read the exact key |
| Parameter count/order error | `declareParameters` list does not match the procedure, especially with metadata disabled | Align `IN`, `OUT`, `INOUT` order and verify types |
| SQL type conversion error | Used `Types.VARCHAR` for `DECIMAL`, vendor-specific types, or mishandled `null` | Check schema/driver and use the appropriate `Types` and converters |
| `Map.get(...)` returns `null` despite a successful call | Wrong key casing or procedure actually returned SQL `NULL` | Inspect `keySet()` in tests; consider a case-insensitive result map; inspect SQL logic |
| `INOUT` result keeps the old value | Re-reading the input map or procedure did not reassign the parameter | Read the result map; check procedure logic |
| Procedure runs but data does not match expectations | Transaction, privileges, SQL errors, or assuming the procedure auto-commits | Test on a real DB; manage transactions in the service layer when appropriate |
| Fails on another DBMS | Routine creation syntax, cursor/function return conventions, and metadata differ from MySQL | Write SQL for the target DBMS and verify how the driver registers `OUT` types |

**Checklist before going to production:**

1. Compare parameter names, order, `IN/OUT/INOUT` directions, and SQL types against the DB signature.
2. For each `IN` and `INOUT`, provide a corresponding input value; for each `OUT` and `INOUT`, read the output by name.
3. Test normal values, `null`, `DECIMAL` precision limits, rounding, and business errors; do not assume every driver returns the exact same Java class for vendor-specific types.
4. Check `EXECUTE` privileges, schema/database, transactions, and connection pool configuration; JDBC errors are normally translated by Spring into `DataAccessException`.
5. When using manual declarations to avoid metadata dependency, re-verify when upgrading the driver or changing routine signatures. Only log values compliant with security policies.
6. Prefer initializing `SimpleJdbcCall` at the data-access layer, reusing the configuration, and never mutating declarations after the call is compiled for the first time.

## 8. Summary

`SqlParameter` describes **data going in**; `SqlOutParameter` describes **data coming out**; `SqlInOutParameter` describes **data going in and coming back out with a new value**. The three classes work together with `SimpleJdbcCall.declareParameters(...)` so Spring JDBC knows how to configure `CallableStatement`. `MapSqlParameterSource` is what holds the input values, while the `Map` returned by `execute(...)` holds the procedure's outputs.

**Official documentation:**

- [Spring Framework – Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): `SimpleJdbcCall`, parameter declarations, metadata, procedures, functions, and cursors.
- [Spring Framework – SqlParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlParameter.html): name, SQL type, scale properties, and related methods.
- [Spring Framework – SqlOutParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlOutParameter.html): output declaration and result conversion mechanisms.
- [Spring Framework – SqlInOutParameter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlInOutParameter.html): bidirectional parameters.
- [MySQL 8.4 – CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html): `IN`, `OUT`, `INOUT` rules and `RETURN` values.
