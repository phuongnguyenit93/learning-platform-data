# Automatic Metadata vs. Explicit Parameter Configuration When Calling Procedures and Functions in Spring JDBC

`SimpleJdbcCall` helps Spring Framework applications invoke **stored procedures** and **stored functions** via JDBC. The design choice is: let Spring **auto-detect the parameter signature from database metadata**, or **explicitly declare the name, direction, and SQL type of each parameter** in Java code?

Both approaches can produce identical calls and results when the procedure/function signature matches. The difference lies in **the source of information Spring relies on to construct the call**, the degree of dependence on the JDBC driver, and the amount of configuration to maintain. Choosing the right approach avoids missing `OUT` parameters, wrong `IN` order or types, routine lookup failures when switching schemas, and issues only discovered against a real database.

## 1. What does a routine's signature consist of?

A stored procedure or function has a **name**, may belong to a **schema/catalog**, and has a **parameter list**. For a procedure, a parameter can be:

| Direction | Meaning | Declaration class in Spring JDBC |
| --- | --- | --- |
| `IN` | Application passes a value into the routine | `SqlParameter` |
| `OUT` | Routine writes a value to return to the application | `SqlOutParameter` |
| `INOUT` | Application passes an initial value in and receives the modified value | `SqlInOutParameter` |

Each parameter also has a **name** and an **SQL type** such as `Types.INTEGER`, `Types.DECIMAL`, `Types.VARCHAR`, `Types.TIMESTAMP`, or a database-specific type. A **function** also has its own return value, distinct from its input parameter list; Spring supports `withFunctionName(...)` and `executeFunction(...)` for this style of call.

For example, a hypothetical procedure signature:

~~~sql
quote_total(
    IN  p_price DECIMAL(12,2),
    IN  p_qty   INTEGER,
    OUT p_total DECIMAL(14,2)
)
~~~

The application supplies `p_price` and `p_qty`, then reads `p_total`. If you mistakenly assume `p_total` is `IN`, or forget to declare `OUT` when metadata lookup is disabled, the call can fail or fail to return the expected data.

**Important distinction:** routine parameter metadata is not query result metadata (`ResultSetMetaData`); it primarily describes how to invoke the routine and its call parameters.

## 2. How does Spring's automatic metadata discovery work?

With a minimal configuration:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total");
~~~

`SimpleJdbcCall` can fetch parameter information from the connection's **JDBC `DatabaseMetaData`**, working together with Spring's per-database metadata support. When compiled (`compile()` or automatically before the first execution), Spring builds the `CallableStatement` call representation: routine name, parameter slot count, order, `IN/OUT/INOUT` directions, and required SQL types.

High-level flow:

~~~text
DataSource / JDBC Driver
       |
       v
Connection's DatabaseMetaData
       |
       v
Spring looks up procedure/function + parameter info
       |
       v
SimpleJdbcCall builds/compiles CALL
       |
       v
execute(input) -> JDBC CallableStatement -> OUT result Map
~~~

Depending on the database and driver, the relevant JDBC methods can be `getProcedures`, `getProcedureColumns`, `getFunctions`, and `getFunctionColumns`. Support is **uneven** across databases, drivers, routine types, and account privileges. Spring supports procedure metadata on a documented set of databases; function metadata is supported on an even narrower set. Therefore, **do not assume every JDBC database supports full auto-discovery**.

Key benefits:

- Concise Java configuration when DB/driver metadata is **complete and reliable**.
- Spring can infer parameter names, order, directions, and types instead of forcing you to write every `SqlParameter` from scratch.
- When the signature changes, testing on a real database reveals the new metadata; however, **this does not mean signature changes are automatically backward-compatible** with all calling code.

Key risks:

- Drivers returning incomplete/inaccurate parameters or misresolving routines (common with overloading, packages, synonyms, and multiple schemas).
- Database accounts lacking the privileges needed to read metadata.
- Differences in letter casing, catalog/schema, or driver settings causing parameter name mismatches.
- Errors only surfacing at compile/execute time in an environment with different metadata; a successful Java build does not prove the call works at runtime.

### When is metadata read?

`SimpleJdbcCall` is a **reusable** configuration object. Spring compiles the call representation once per configured instance (either via an explicit `compile()` call or automatically on the first execution). After compilation, do not continue modifying that instance's configuration. Create and configure a single instance during DAO/service initialization and reuse it across calls; avoid recreating it on every request without a specific reason.

`compile()` surfaces metadata/configuration issues earlier, but **it is not a substitute for actually running the procedure**. Verifying that the routine works properly with real data still requires an integration test.

## 3. Explicit parameter declaration and disabling metadata

Instead of letting Spring infer parameters, the application can specify each parameter:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_price", Types.DECIMAL),
                new SqlParameter("p_qty", Types.INTEGER),
                new SqlOutParameter("p_total", Types.DECIMAL)
        );
~~~

Exact meaning of the two calls:

- `declareParameters(...)` registers known parameters. **Calling this method alone does not completely disable metadata**: if metadata remains enabled, Spring can still use metadata for undeclared parameters.
- `withoutProcedureColumnMetaDataAccess()` disables **routine column/parameter metadata lookup**. The application must then supply the full required signature with the right types, directions, and order matching the database's calling convention.

Explicit declaration fits situations where driver metadata is unsupported or unreliable, when strict signature control is required, or when handling special SQL types. In return, **the DB procedure/function definition and Java declarations must be updated in sync**; Spring will not automatically fix outdated declarations when the routine signature changes.

Example of **partial** declaration (still relying on metadata for the rest):

~~~java
SimpleJdbcCall partiallyDeclared = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("quote_total")
        .declareParameters(new SqlOutParameter("p_total", Types.DECIMAL));
~~~

Here `p_price` and `p_qty` must still be discovered from metadata. This is an intentional choice when only one parameter needs overriding; it is **not** full explicit configuration mode.

## 4. Runnable Java 17+ example with MySQL: two ways to call the same procedure

This example uses MySQL because JDBC procedure metadata is a supported case in Spring. The goal is to compare **how parameter signatures are obtained**, not to compare performance or transactions.

### 4.1. Creating the procedure in MySQL

Requirements: MySQL 8+, database `jdbc_demo`, and an account with privileges to call routines and read the necessary metadata. In the MySQL command-line client, execute the following SQL (ensure the database exists and is selected):

~~~sql
USE jdbc_demo;

DROP PROCEDURE IF EXISTS quote_total;

DELIMITER //
CREATE PROCEDURE quote_total(
    IN  p_price DECIMAL(12,2),
    IN  p_qty   INT,
    OUT p_total DECIMAL(14,2)
)
BEGIN
    SET p_total = p_price * p_qty;
END//
DELIMITER ;
~~~

`DELIMITER` is a **MySQL CLI directive** for entering a multi-statement routine body; it is not an SQL statement sent directly via `JdbcTemplate.execute(...)`. This procedure only computes a value and modifies no table data. With `p_price=12.50` and `p_qty=3`, the expected result is `p_total=37.50`.

### 4.2. Creating a minimal Maven project

Structure:

~~~text
simple-jdbc-call-demo/
├── pom.xml
└── src/main/java/example/MetadataVsExplicitDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>simple-jdbc-call-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.3.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.MetadataVsExplicitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/MetadataVsExplicitDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class MetadataVsExplicitDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("com.mysql.cj.jdbc.Driver");
        dataSource.setUrl(requiredEnv("DEMO_DB_URL"));
        dataSource.setUsername(requiredEnv("DEMO_DB_USER"));
        dataSource.setPassword(requiredEnv("DEMO_DB_PASSWORD"));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        // Normalize OUT key lookup regardless of DB letter casing.
        jdbc.setResultsMapCaseInsensitive(true);

        // Approach A: use JDBC driver/database metadata.
        SimpleJdbcCall automatic = new SimpleJdbcCall(jdbc)
                .withProcedureName("quote_total");

        // Approach B: declare explicitly in full, skipping parameter metadata lookup.
        SimpleJdbcCall explicit = new SimpleJdbcCall(jdbc)
                .withProcedureName("quote_total")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_price", Types.DECIMAL),
                        new SqlParameter("p_qty", Types.INTEGER),
                        new SqlOutParameter("p_total", Types.DECIMAL)
                );

        MapSqlParameterSource input = new MapSqlParameterSource()
                .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL)
                .addValue("p_qty", 3, Types.INTEGER);

        // Can compile eagerly; if omitted, execute compiles automatically.
        automatic.compile();
        explicit.compile();

        Map<String, Object> autoOut = automatic.execute(input);
        Map<String, Object> explicitOut = explicit.execute(input);

        System.out.println("metadata total=" + autoOut.get("p_total"));
        System.out.println("explicit total=" + explicitOut.get("p_total"));
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

Run after the procedure is created and connection details are valid. Example in PowerShell (substitute your own account; never hardcode real passwords in source code):

~~~powershell
$env:DEMO_DB_URL = "jdbc:mysql://localhost:3306/jdbc_demo"
$env:DEMO_DB_USER = "your_db_user"
$env:DEMO_DB_PASSWORD = "your_db_password"
mvn -q compile exec:java
~~~

Lines printed by the program, with MySQL and the routine above:

~~~text
metadata total=37.50
explicit total=37.50
~~~

Explanation:

1. `automatic` queries the driver's metadata to discover the `quote_total` signature; the application only declares the routine name.
2. `explicit` skips parameter metadata lookup; Spring uses the three `SqlParameter`/`SqlOutParameter` declarations matching the SQL signature.
3. Both accept the same `MapSqlParameterSource`. `execute(...)` returns a `Map<String,Object>` containing the `OUT` value. `setResultsMapCaseInsensitive(true)` helps read key `p_total` even if the DB returns different letter casing.
4. `BigDecimal` and `Types.DECIMAL` fit the monetary data in the example; real applications should also define scale, rounding, and precision according to business rules.

**Test conditions:** requires a running MySQL instance, the created procedure, and a user with access privileges. If the account cannot read metadata, **approach A may fail even while approach B can still call the routine** provided execute privileges and other JDBC conditions permit. The two output lines are expected results for the MySQL setup above, not universal output across all DBs/drivers.

## 5. A parameter `Map` does not mean JDBC automatically binds by name

This is a very easy distinction to confuse:

~~~java
MapSqlParameterSource in = new MapSqlParameterSource()
        .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL)
        .addValue("p_qty", 3, Types.INTEGER);

Map<String, Object> out = automatic.execute(in);
~~~

`MapSqlParameterSource` associates **logical parameter names** with input values at the Spring layer. `SimpleJdbcCall` can use names from metadata or declarations to arrange values positionally for the JDBC call. That **does not necessarily** mean `CallableStatement` is using database/driver-level named binding.

`withNamedBinding()` is a separate option:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withProcedureName("quote_total")
        .withNamedBinding();
~~~

It instructs Spring to bind by **name** in the call, but syntax and support depend on the driver/database. **Do not add `withNamedBinding()` just to use `MapSqlParameterSource`**. In most cases, a map with matching keys plus declarations/metadata is enough; test on the real setup if you decide to enable named binding.

Positional `execute(Object... args)` calls require extra care: argument order must match the established `IN` parameter order. Using an explicit map usually makes code easier to read, though names, directions, and value types must still be correct.

## 6. Configuring routine name, schema, and catalog

When multiple schemas exist, an unqualified routine name may resolve according to the connection's default schema/search path. To avoid calling the wrong routine, Spring supports:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withSchemaName("billing")
        .withProcedureName("quote_total");
~~~

If the DBMS organizes routines via catalog/package, you can use `withCatalogName(...)` according to the database and Spring dialect conventions. **Do not treat schema, catalog, and package as identical concepts across all DBs.** In MySQL, a database typically acts as a schema; in Oracle, packages can affect how Spring uses catalog; verify names and configuration against the specific database.

When overloads exist or routines share names across schemas, verify which signature gets selected. `useInParameterNames(...)` exists in the API to restrict `IN` parameter names when signatures differ, but it should not be viewed as an automatic overload resolver for every driver. The reliable approach is to test the actual SQL call and declare explicitly whenever metadata is ambiguous.

## 7. Functions, OUT/INOUT, and result sets: do not apply one single formula

### Function: returning a dedicated value

If the database has a `double_amount` function, the basic Spring call differs from a procedure in **configuration method** and **return-value retrieval API**:

~~~java
SimpleJdbcCall functionCall = new SimpleJdbcCall(jdbc)
        .withFunctionName("double_amount");

BigDecimal doubled = functionCall.executeFunction(
        BigDecimal.class,
        new MapSqlParameterSource()
                .addValue("p_amount", new BigDecimal("12.50"))
);
~~~

This snippet assumes a configured JDBC context **and a database containing a function with the matching signature**; it is not a second standalone runnable program. Function metadata depends on the database/driver and can be less complete than procedure metadata. For a function with multiple `OUT` results or special cases, read the specific contract rather than assuming `executeFunction` replaces every procedure `execute`.

### INOUT: must declare the right direction

For example, procedure `increase_counter(INOUT p_count INT)` can be configured as:

~~~java
SimpleJdbcCall increment = new SimpleJdbcCall(jdbc)
        .withProcedureName("increase_counter")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(new SqlInOutParameter("p_count", Types.INTEGER));
~~~

When writing this in real Java, add `import org.springframework.jdbc.core.SqlInOutParameter`. The input for `SqlInOutParameter` is supplied via `MapSqlParameterSource`; the `OUT` result appears in the returned map. **Do not replace `SqlInOutParameter` with `SqlOutParameter` expecting it to accept the input value automatically.**

### Procedure returning `ResultSet` or `REF CURSOR`

Some procedures return data rows via result sets rather than scalar `OUT` values. With `SimpleJdbcCall`, you can use `returningResultSet("items", rowMapper)`. How the database returns result sets **can vary**: direct JDBC results, or a cursor registered as an `OUT` parameter. Cursor SQL types and result set ordering rules depend on the database/driver. Do not apply `Types.VARCHAR` or blindly read `Map.get("items")` before verifying what the routine actually returns.

The automatic vs. explicit metadata consideration **still applies**: if the driver does not supply reliable cursor signatures, declare the `OUT` parameter and appropriate mapping for your target DBMS.

## 8. Which approach to choose for each situation?

| Situation | Recommended starting approach | Reason |
| --- | --- | --- |
| Simple procedure on a DB/driver where Spring supports metadata well | `withProcedureName(...)`, without full declarations | Minimal configuration, convenient when signatures are clear |
| Only one `OUT` or SQL type needs overriding; metadata for remaining parameters is good | **Partial** `declareParameters(...)`, keeping metadata enabled | Preserves auto-discovery while overriding only what needs control |
| Database/driver does not support metadata or metadata is missing/wrong | `withoutProcedureColumnMetaDataAccess()` + full declarations | Full control over the call contract |
| Overloaded routines, confusing packages/schemas | Specify appropriate schema/catalog; consider full explicit declarations | Reduces risk of selecting the wrong signature |
| `INOUT`, custom SQL types, cursors, or hard-to-infer `NULL` values | Declare appropriate SQL directions/types; register SQL types on input sources | Avoids misinferred types or directions |
| Multiple DB environments with differing drivers/privileges | Integration test on each target DB/driver and choose mode from results | Metadata working on dev does not prove it works in production |

**Rule of thumb:** the `automatic` approach saves configuration when metadata is trustworthy; the `explicit` approach buys control at the cost of maintaining the signature. Neither eliminates the need to test against the real routine.

## 9. Practical errors and how to diagnose them

| Symptom | First suspect | Action to take |
| --- | --- | --- |
| Procedure exists, yet Spring reports not found or wrong parameter count | Wrong schema/catalog, metadata privileges, unsupported driver, or name casing | Verify the routine and privileges using the actual app account; specify schema/catalog or configure explicitly |
| `Invalid column type`, `SQLException` when binding values | Mismatched `Types`, `NULL` input missing SQL type, custom DB type | Check SQL signature; register type in `MapSqlParameterSource.addValue(name, value, sqlType)` |
| `out.get("p_total")` is null even though DB computed it | `OUT` field not declared, key casing changed, or reading the wrong key | Inspect actual keys in the result map and `OUT` signature; use `setResultsMapCaseInsensitive(true)` |
| Metadata mode works, explicit mode fails | Missing `OUT`/`INOUT`, wrong declaration order, or wrong SQL type | Cross-check every parameter with the DB routine at the same migration version |
| Explicit mode works, metadata mode fails | Metadata or metadata access privileges are insufficient | Inspect `DatabaseMetaData`/logs and privileges; keep full declarations when needed |
| Fails only on another database or after deployment | Differences in driver/version, routine/schema, privileges, or SQL types across environments | Test on a production-like environment, recording actual driver and signature |
| Calling `execute` repeatedly always hits the first-run configuration issue | `SimpleJdbcCall` already compiled and cached the earlier configuration | Recreate the instance when config/routine contract changes; never modify after compile |
| Fails at runtime after adding `withNamedBinding()` | Driver/database does not support the expected binding style | Remove the option if unnecessary; test logical map binding with standard positional JDBC |

### NULL and SQL types

`NULL` can be a case where the driver cannot infer the SQL type:

~~~java
MapSqlParameterSource input = new MapSqlParameterSource()
        .addValue("p_note", null, Types.VARCHAR)
        .addValue("p_price", new BigDecimal("12.50"), Types.DECIMAL);
~~~

This snippet illustrates how to specify input types for a routine **that has a matching `p_note` parameter**, not as input to `quote_total` in the earlier runnable example. Sending an extra `p_note` to a procedure that does not declare it violates the contract. For `OUT`/`INOUT` values and DB-specific types, you may need `SqlReturnType`, `SqlTypeValue`, or a driver-specific type name.

### Logging and privileges

You can enable controlled logging for Spring JDBC to inspect routine names, compiled signatures, and driver errors. Do not log passwords or full sensitive input values. Verify metadata using **the exact JDBC URL, user, and driver** of the application; admin privileges in an SQL client do not prove the service account can read metadata.

## 10. Testing functionality and the Java–database contract

A useful integration test suite for both approaches should cover:

1. **Real schema:** run migrations creating the procedure/function and verify actual names/schemas and parameter lists.
2. **Happy path:** with deterministic inputs like `12.50 × 3`, both metadata and explicit configurations receive `37.50` in `p_total` (on the MySQL demo).
3. **Types/NULL:** test boundary values and `NULL` where the routine allows them; verify SQL types are registered properly.
4. **Signature changes:** modify/roll back migrations in the test environment and verify Java does not silently mis-call or drop `OUT` parameters.
5. **Privileges and environment:** test with the DB account used in production, comparing driver versions across dev/test/production.
6. **Functions/cursors if applicable:** verify function return values and result sets with proper `RowMapper`s.
7. **Controlled failures:** observe exceptions and underlying SQL errors, not merely that Java compiles.

When appropriate, call `compile()` at startup to expose metadata errors early; you must still run at least one **real** call to verify the SQL signature, parameter types, and result mapping.

Mistakes to avoid:

- Thinking `declareParameters` automatically disables metadata: **no**, you must call `withoutProcedureColumnMetaDataAccess()` to skip parameter lookup.
- Thinking named parameters in a `Map` mean the driver is binding by name: **not necessarily**, `withNamedBinding()` is a separate setting.
- Declaring every parameter as `SqlParameter`: `OUT`/`INOUT` parameters require their corresponding classes.
- Relying on exact spelling of `OUT` names in Java without considering DB letter-casing rules.
- Creating a new `SimpleJdbcCall` per request or modifying an already-compiled configuration.
- Assuming metadata working on one DB means every dialect/driver supports it identically.
- Conflating binding/metadata choices with transaction decisions: they are independent concerns. Parameter declarations **do not start transactions or guarantee rollback** for updates inside a procedure.

## 11. Self-check questions

**Question 1.** You called `declareParameters(new SqlOutParameter("result", Types.INTEGER))` without calling `withoutProcedureColumnMetaDataAccess()`. Can Spring still use metadata?

**Answer:** Yes. Spring can still use metadata to fill in undeclared parameters. If you want everything declared from Java code, disable parameter metadata lookup and declare all parameters completely.

**Question 2.** You pass a `MapSqlParameterSource` containing key `p_id`. Must the driver use named binding?

**Answer:** No. Keys in the map are a Spring-level input interface. `withNamedBinding()` is a separate option and must be supported by the driver/database.

**Question 3.** A procedure has `IN p_id INTEGER, OUT p_name VARCHAR(100)`, but the explicit configuration only declares `SqlParameter("p_id", Types.INTEGER)`. What is wrong?

**Answer:** `SqlOutParameter("p_name", Types.VARCHAR)` is missing. With metadata disabled, Spring does not automatically add that `OUT` parameter; the call signature becomes incomplete.

**Question 4.** Why might an auto-discovery configuration work on MySQL yet fail when switching to another JDBC driver or database?

**Answer:** Metadata and how Spring processes it do not have identical support across DBs/drivers; access privileges, schema/catalog semantics, and routine types can also differ. Integration testing against the target environment is required; when needed, use explicit declarations.

## References

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html)
- [Spring Framework — Common Problems with Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html)
- [Spring Framework API — SimpleJdbcCall](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html)
- [MySQL Connector/J documentation](https://dev.mysql.com/doc/connector-j/en/)
