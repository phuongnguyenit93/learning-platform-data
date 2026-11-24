# `IN`, `OUT`, and `INOUT` Parameters in Database Procedures and Functions

When a Java application calls a **stored procedure** through Spring Framework Data Access, data can flow into the procedure, out of the procedure, or in **both directions**. The three parameter modes `IN`, `OUT`, and `INOUT` describe those exact paths. Understanding parameter modes helps you declare SQL correctly, pass data properly over JDBC, retrieve results in Spring JDBC, avoid losing input values, and distinguish a procedure's results from a function's return value.

This lesson uses **MySQL 8.x** to illustrate SQL and **Java 17+ / Spring JDBC** for calling from the application. Procedure declaration syntax, function rules, how drivers handle named parameters, and data types can differ in PostgreSQL, Oracle, SQL Server, and other DBMSs.

## 1. Meaning of the three parameter modes

| Mode | Data direction | Must caller provide an initial value? | Can value be read after procedure runs? | Examples |
| --- | --- | --- | --- | --- |
| `IN` | Caller → Procedure | Yes, unless the routine/DB design has its own default mechanism | Not returned back through this parameter itself | Order ID, amount, filter |
| `OUT` | Procedure → Caller | No need to supply a business input value; JDBC must **register the output type** | Yes, after a successful call | Result code, total, status |
| `INOUT` | Caller ↔ Procedure | Yes, both pass an initial value and register output | Yes; receives the new value assigned by the procedure | Counter, running total |

A quick mnemonic:

```text
IN:     Java/SQL caller ---> [ PROCEDURE ]
OUT:    Java/SQL caller <--- [ PROCEDURE ]
INOUT:  Java/SQL caller <---> [ PROCEDURE ]
```

Example: a routine accepts `p_delta = 5` (IN), computes `p_double = 10` (OUT), and changes `p_total` from `10` to `15` (INOUT).

**Notes on semantics:**

- `IN` is a routine input. Modifying a local parameter variable inside the routine (if the DB allows it) does not turn that parameter into an output for the caller.
- `OUT` is an output slot. In MySQL, an `OUT` parameter's value starts out as `NULL` inside the procedure; therefore, the routine should assign it before the caller uses it. The value may still end up `NULL`.
- `INOUT` must be initialized by the caller; the procedure reads the initial value and can assign a new value. `INOUT` **does not persist a variable in the database across calls**: if data must be persisted long-term, the routine must execute DML or the caller must store the result.
- These modes are an **SQL parameter contract**; they are not the same as Java's argument-passing mechanism. Java still passes reference/primitive values by *pass-by-value*; JDBC sends and receives values through SQL and the driver.

## 2. Runnable SQL example: `IN`, `OUT`, and `INOUT` in one procedure

Execute the following SQL using the **MySQL command-line client** with an account that has privileges to create routines. `DELIMITER` is a `mysql` client command to read the entire body containing `;` characters, **not an SQL statement sent directly over JDBC**.

```sql
CREATE DATABASE IF NOT EXISTS procedure_lab;
USE procedure_lab;

DROP PROCEDURE IF EXISTS compute_points;

DELIMITER $$
CREATE PROCEDURE compute_points(
    IN p_delta INT,
    OUT p_double INT,
    INOUT p_total INT
)
BEGIN
    SET p_double = p_delta * 2;
    SET p_total = p_total + p_delta;
END$$
DELIMITER ;
```

Explanation of the `compute_points` signature:

1. `p_delta` is `IN`: the caller sends the number to add; here `5`.
2. `p_double` is `OUT`: the procedure sets it to `p_delta * 2`; the caller receives `10`.
3. `p_total` is `INOUT`: receives the initial total `10`, then returns the new total `15`.

Calling the procedure using `@...` session variables in MySQL:

```sql
SET @total = 10;
SET @double = 999;

CALL compute_points(5, @double, @total);

SELECT @double AS doubled, @total AS total;
```

Result of the `SELECT` statement:

```text
+---------+-------+
| doubled | total |
+---------+-------+
|      10 |    15 |
+---------+-------+
```

`@double` is overwritten with `10`. The `999` value set beforehand merely illustrates that `OUT` **does not use the old value as input**. `@total`, by contrast, requires an initial value because it is `INOUT`.

**Why use `@double`/`@total` variables?** In a direct `CALL` in MySQL, `OUT` and `INOUT` positions typically take **user-defined variables** so there is a place to hold values after completion. In JDBC, `?` placeholders and `registerOutParameter` handle this; there is no need to create `@...` variables in Java.

### What happens with NULL?

```sql
SET @total = NULL;
CALL compute_points(5, @double, @total);
SELECT @double AS doubled, @total AS total;
```

The logical values returned are `doubled = 10` and `total = NULL`, because `NULL + 5` remains `NULL`. If business logic wants an uninitialized initial total treated as 0, that policy must be written explicitly, e.g., `SET p_total = COALESCE(p_total, 0) + p_delta;`. **Do not automatically turn `NULL` into `0` in Java without understanding the data's meaning.**

## 3. JDBC `CallableStatement`: mapping SQL to Java

In JDBC, `java.sql.CallableStatement` is the fundamental API for calling stored procedures and retrieving `OUT`/`INOUT` results. With the signature `compute_points(IN, OUT, INOUT)`:

```java
try (CallableStatement statement =
         connection.prepareCall("{call compute_points(?, ?, ?)}")) {

    statement.setInt(1, 5);                         // IN
    statement.registerOutParameter(2, Types.INTEGER); // OUT

    statement.setInt(3, 10);                        // INOUT: input
    statement.registerOutParameter(3, Types.INTEGER); // INOUT: output

    statement.execute();

    int doubled = statement.getInt(2);
    int total = statement.getInt(3);
}
```

This is a **code snippet inside a method that already has a `Connection connection` variable**, not a standalone Java program. Key differences:

| JDBC position (1-based) | SQL parameter | Preparation before `execute()` | Retrieval after `execute()` |
| --- | --- | --- | --- |
| `1` | `IN p_delta` | `setInt(1, 5)` | No output |
| `2` | `OUT p_double` | `registerOutParameter(2, Types.INTEGER)` | `getInt(2)` |
| `3` | `INOUT p_total` | **Both** `setInt(3, 10)` **and** `registerOutParameter(3, Types.INTEGER)` | `getInt(3)` |

`OUT`/`INOUT` parameters must be registered **before execution**. Positional numbers follow the **procedure signature**, not the order of `set...` calls or the order of entries in a `Map`. JDBC uses **1-based** indices; Java arrays are 0-based.

**Cases to keep in mind:**

- `execute()` returns a `boolean` indicating whether the first result is a `ResultSet`. It does **not** mean "procedure succeeded/failed". JDBC errors normally surface as `SQLException`.
- `getInt(...)` returns `0` for SQL `NULL`; call `wasNull()` right after `getInt`, or read via `getObject(...)` when you need to distinguish an actual `0` from `NULL`.
- SQL `DECIMAL`/`NUMERIC` usually maps to `BigDecimal`; register with `Types.DECIMAL` and an appropriate scale if required by the driver. Do not default to converting currency into `double`.
- For routines that also produce `ResultSet`s or update counts, for maximum portability process those results before reading `OUT` parameters; the `compute_points` example above does not emit a `ResultSet`.
- Parameter names in JDBC (`registerOutParameter("p_double", ...)`) depend on driver support. Using positional indices matching the signature is the simplest choice when portability is needed.

## 4. Complete Java 17+ program: plain JDBC

This is a **standalone runnable example after creating the database, routine, and configuring MySQL access privileges**. Directory layout:

```text
inout-demo/
├── pom.xml
└── src/main/java/example/InOutJdbcDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>inout-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.InOutJdbcDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/InOutJdbcDemo.java`:

```java
package example;

import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Types;

public final class InOutJdbcDemo {
    private InOutJdbcDemo() {
    }

    public static void main(String[] args) throws Exception {
        String url = requiredEnvironment("DB_URL");
        String username = requiredEnvironment("DB_USER");
        String password = requiredEnvironment("DB_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, username, password);
             CallableStatement call =
                     connection.prepareCall("{call compute_points(?, ?, ?)}")) {

            call.setInt(1, 5);
            call.registerOutParameter(2, Types.INTEGER);
            call.setInt(3, 10);
            call.registerOutParameter(3, Types.INTEGER);

            call.execute();

            int doubled = call.getInt(2);
            if (call.wasNull()) {
                throw new IllegalStateException("p_double is NULL");
            }

            int total = call.getInt(3);
            if (call.wasNull()) {
                throw new IllegalStateException("p_total is NULL");
            }

            System.out.println("doubled=" + doubled);
            System.out.println("total=" + total);
        }
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
```

The class has `main`, and the file name and `package` match; no additional code is needed to compile. It **does not create the routine itself**: you must run the SQL from section 2 first. Grant the `EXECUTE` privilege to the account being used.

Example in PowerShell, entering your active MySQL account details:

```powershell
$env:DB_URL = 'jdbc:mysql://127.0.0.1:3306/procedure_lab'
$env:DB_USER = Read-Host 'MySQL user'
$env:DB_PASSWORD = Read-Host 'MySQL password'

mvn -q compile exec:java
```

With a valid connection and `compute_points` keeping the definition from section 2, the program's stdout is:

```text
doubled=10
total=15
```

In an environment with Maven, `mvn compile` runs the Maven Compiler Plugin and `exec:java` runs the class with its dependencies on the classpath. You can use `javac`/`java` directly if you configure the JDBC driver and all libraries on the classpath yourself; this example uses Maven to avoid classpath mistakes.

## 5. Calling with Spring JDBC: `SimpleJdbcCall`

`SimpleJdbcCall` belongs to the `org.springframework.jdbc.core.simple` package. It implements procedure calls on top of `DataSource`/`JdbcTemplate`, declares SQL-typed parameters, and returns results as `Map<String, Object>`. It is a good choice when the application already uses Spring Data Access and you do not want to manually close each `Connection`/`CallableStatement`.

The three declaration types in Spring map directly to the three SQL modes:

| SQL | Spring JDBC | Needs input in `execute(...)`? | Appears in result map? |
| --- | --- | --- | --- |
| `IN p_delta` | `new SqlParameter("p_delta", Types.INTEGER)` | Yes | No, unless the routine has another output with the same name |
| `OUT p_double` | `new SqlOutParameter("p_double", Types.INTEGER)` | No | Yes |
| `INOUT p_total` | `new SqlInOutParameter("p_total", Types.INTEGER)` | Yes | Yes |

**Special warning:** using `SqlOutParameter` instead of `SqlInOutParameter` on a bidirectional parameter causes `SimpleJdbcCall` **not to treat it as an input source**. The result may differ from expectations or the call may fail. Simply putting a value with the same name in a `Map` does not turn it into an `INOUT` parameter.

### Spring JDBC example against the same database

Add `src/main/java/example/InOutSpringDemo.java` to the Maven project from section 4:

```java
package example;

import java.sql.Types;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlInOutParameter;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

public final class InOutSpringDemo {
    private InOutSpringDemo() {
    }

    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                requiredEnvironment("DB_URL"),
                requiredEnvironment("DB_USER"),
                requiredEnvironment("DB_PASSWORD"));

        JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
        jdbcTemplate.setResultsMapCaseInsensitive(true);

        SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("compute_points")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_delta", Types.INTEGER),
                        new SqlOutParameter("p_double", Types.INTEGER),
                        new SqlInOutParameter("p_total", Types.INTEGER));

        MapSqlParameterSource input = new MapSqlParameterSource()
                .addValue("p_delta", 5, Types.INTEGER)
                .addValue("p_total", 10, Types.INTEGER);

        Map<String, Object> output = call.execute(input);

        Number doubled = (Number) output.get("p_double");
        Number total = (Number) output.get("p_total");
        if (doubled == null || total == null) {
            throw new IllegalStateException("Procedure returned NULL output");
        }

        System.out.println("doubled=" + doubled.intValue());
        System.out.println("total=" + total.intValue());
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
```

After setting the three environment variables from the previous section, run:

```powershell
mvn -q compile
mvn -q -Dexec.mainClass=example.InOutSpringDemo exec:java
```

Expected stdout, with the routine and inputs in the example:

```text
doubled=10
total=15
```

**Reading the configuration carefully:**

1. `withProcedureName("compute_points")` selects a **procedure**, not an ordinary `SELECT` statement.
2. `withoutProcedureColumnMetaDataAccess()` disables Spring's automatic parameter list inference from database metadata. Consequently, `declareParameters(...)` must include **every parameter in exact signature order**. This is useful when the driver does not return complete metadata or the account lacks privileges to inspect routine definitions.
3. `SqlParameter` is input; `SqlOutParameter` is output; `SqlInOutParameter` both accepts input and returns output.
4. `MapSqlParameterSource` contains only `p_delta` and `p_total`. There is no need to send an initial value for `p_double`.
5. `call.execute(input)` returns a `Map` containing output parameter values. The actual object type must be read safely: for numeric types, `Number` is typically used and converted appropriately, rather than assuming every driver always returns `Integer`.
6. `setResultsMapCaseInsensitive(true)` makes accessing keys in the result map less dependent on the database/driver's letter casing.
7. `DriverManagerDataSource` is only for simple examples, creating a new connection on every request. Real applications typically use a connection pool and a Spring Boot-managed `DataSource`.

Once configured, `SimpleJdbcCall` can be stored as a field on a DAO bean and reused across many calls. **Do not modify the names/parameter declarations on the same instance while concurrent requests are using it**; configure it once at initialization.

### Variant using `Map` directly

You can use `Map.of` instead of `MapSqlParameterSource`:

```java
Map<String, Object> output = call.execute(
        Map.of("p_delta", 5, "p_total", 10));
```

This is an **additional snippet**, assuming the `call` variable is configured as above. `Map.of` does not allow `null` values; when an SQL parameter can be nullable, use `MapSqlParameterSource` or a map that permits nulls and explicitly declare the SQL type.

### Automatic metadata or manual declaration?

If the database and driver return reliable routine metadata, a shorter configuration is possible:

```java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("compute_points");
```

Spring will attempt to discover parameter names, modes, and order using JDBC metadata. Test against your actual setup: parameter names may differ in casing, schema/catalog, metadata privileges, overloading, or driver support. For a lesson that needs to demonstrate `INOUT` clearly, explicit declaration is easier to verify.

## 6. Procedures and functions: parameters vs. return value

A **procedure** is normally invoked with `CALL` and can return data via `OUT`/`INOUT`, one or more result sets, and can perform write operations. A **function** is used to compute and return a single value declared with `RETURNS`. **A function's return value is not synonymous with an `OUT` parameter**, even though JDBC may reserve a position for the return value in function call syntax.

In **MySQL 8.x**, `IN`, `OUT`, and `INOUT` declarations apply only to **procedures**; stored function parameters are treated as `IN`, while the function's result is returned via `RETURN`. Other DBMSs may support different function parameter modes, so do not apply MySQL rules verbatim to all databases.

MySQL function example:

```sql
DROP FUNCTION IF EXISTS add_tax;

DELIMITER $$
CREATE FUNCTION add_tax(
    p_net DECIMAL(10, 2),
    p_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(10, 2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_net * (1 + p_rate), 2);
END$$
DELIMITER ;

SELECT add_tax(100.00, 0.10) AS gross;
```

The `gross` column result is `110.00`. The two arguments `p_net` and `p_rate` are inputs, and the result is returned by `RETURN`.

In Spring JDBC, you can call a function using `JdbcTemplate`:

```java
java.math.BigDecimal gross = jdbcTemplate.queryForObject(
        "SELECT add_tax(?, ?)",
        java.math.BigDecimal.class,
        new java.math.BigDecimal("100.00"),
        new java.math.BigDecimal("0.10"));

System.out.println(gross); // 110.00
```

This is a **code snippet inside a method that already has `JdbcTemplate jdbcTemplate`**. `queryForObject` is useful for functions returning a single scalar value. `SimpleJdbcCall` also supports `withFunctionName(...)` and `executeFunction(...)` when the database/driver supports the corresponding function call.

At the JDBC level, the escape syntax for a function can place the return value at the first position:

```java
try (CallableStatement statement =
         connection.prepareCall("{? = call add_tax(?, ?)}")) {
    statement.registerOutParameter(1, Types.DECIMAL);
    statement.setBigDecimal(2, new java.math.BigDecimal("100.00"));
    statement.setBigDecimal(3, new java.math.BigDecimal("0.10"));
    statement.execute();
    java.math.BigDecimal gross = statement.getBigDecimal(1);
}
```

In this function example, the **first parameter of `CallableStatement`** is the **return** slot created by the `{? = call ...}` syntax, not the `p_net` argument. Watch out for the index shift compared to the SQL signature when using function call syntax. The snippet assumes `Connection connection` already exists.

## 7. Passing NULL, data types, and result conversion

The `IN`/`OUT`/`INOUT` modes are independent of whether a value is nullable. Distinguish the **passing mode** from the **SQL type**:

| SQL type | Common Java/JDBC types | Notes |
| --- | --- | --- |
| `INTEGER` | `int`/`Integer`, `Types.INTEGER` | `getInt` needs `wasNull` to distinguish NULL |
| `BIGINT` | `long`/`Long`, `Types.BIGINT` | Do not cast large results to `int` |
| `DECIMAL(p,s)` | `BigDecimal`, `Types.DECIMAL` | Preserves monetary precision; pay attention to scale |
| `VARCHAR` | `String`, `Types.VARCHAR` | `OUT` can be `null` |
| `DATE` | `LocalDate` or `java.sql.Date` | Verify JDBC 4.2/driver support |
| `TIMESTAMP` | `LocalDateTime` or `Timestamp` | Distinguish timestamps with/without timezone per DB |

For a nullable input, pass the type explicitly:

```java
statement.setNull(1, Types.INTEGER);
```

This is an `IN` example (at position 1) when the routine allows null values. Do not use `setInt(1, 0)` in place of `NULL`. For outputs:

```java
int value = statement.getInt(2);
Integer nullableValue = statement.wasNull() ? null : value;
```

`wasNull()` reflects the **most recent getter read**; it must be called immediately after that `getInt`. With `SimpleJdbcCall`, `output.get("p_double")` can be `null`; check before casting or calling `intValue()`.

With an `INOUT` parameter, null is a valid input **only when the routine is designed to handle null**. There is no default like "INOUT automatically becomes 0" or "OUT generates a value automatically".

## 8. Calling from a Spring service with transactions

A stored procedure can both update tables and return `OUT`/`INOUT` values. Reading output results after `CALL` is **not proof that the entire transaction has committed**. In Spring, transactions should be structured at the service layer when multiple database operations must succeed together or roll back together:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PointsService {
    private final PointsProcedureDao dao;

    public PointsService(PointsProcedureDao dao) {
        this.dao = dao;
    }

    @Transactional
    public int calculateAndPersist(int delta, int currentTotal) {
        int resultingTotal = dao.callAndReturnTotal(delta, currentTotal);
        if (resultingTotal < 0) {
            throw new IllegalStateException("Total must not be negative");
        }
        return resultingTotal;
    }
}
```

The snippet above **illustrates a service class structure**, assuming a `PointsProcedureDao` bean already exists to execute the database call and corresponding logic; it is not a standalone runnable program. For the `compute_points` routine in section 2, the name `calculateAndPersist` is only appropriate if the DAO also persists data; the current illustrative routine **does not write to any table**, it only computes parameter values.

`@Transactional` only takes effect when the method is called through Spring's transaction mechanism (typically via a Spring proxy) and uses the same matching `DataSource`/transaction manager. If instantiated via `new PointsService(...)` outside the Spring context, the annotation does not start a transaction. By default, Spring rolls back when an unchecked exception escapes the transaction boundary; handling checked exceptions requires configuring rollback rules matching the transaction contract.

**Important practices:**

- When a procedure performs DML, clearly define who manages the transaction; avoid embedding `COMMIT`/`ROLLBACK` inside the routine if the whole unit of work must be managed by Spring. Exact behavior also depends on the DB.
- When an SQL error occurs, `JdbcTemplate` translates `SQLException` into `DataAccessException`, enabling consistent handling at the Spring layer.
- An `OUT` result is data returned by the routine; it does not replace checking business invariants, commit status, or consistency.
- Do not infer from a changed `INOUT` variable that a database column was also updated. That is only true if the procedure's logic actually writes the column.
- Use a database account with least-privilege permissions for the routines that must be called; do not concatenate arbitrary procedure names from client input.

## 9. Brief comparison with JPA

Spring Data Access has two common branches for routines: Spring JDBC and JPA. Spring JDBC works close to JDBC and uses `SqlParameter`/`SqlOutParameter`/`SqlInOutParameter`. In JPA, the standard API offers `StoredProcedureQuery` and `ParameterMode.IN`, `OUT`, `INOUT`.

Example **snippet inside a JPA repository/DAO** with an `EntityManager em` and an active transaction:

```java
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

StoredProcedureQuery query = em.createStoredProcedureQuery("compute_points")
        .registerStoredProcedureParameter(1, Integer.class, ParameterMode.IN)
        .registerStoredProcedureParameter(2, Integer.class, ParameterMode.OUT)
        .registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);

query.setParameter(1, 5);
query.setParameter(3, 10);
query.execute();

int doubled = ((Number) query.getOutputParameterValue(2)).intValue();
int total = ((Number) query.getOutputParameterValue(3)).intValue();
```

This requires an actual JPA dependency/provider (such as Spring Data JPA + Hibernate), an injected `EntityManager`, and compatible driver support; **do not run this snippet standalone**. Notice the same rule: `IN` is set, `OUT` is registered then read, and `INOUT` is both set **and** read. When a provider/DB has limitations with named parameters, using positional indices can be simpler; the order must match the routine. Spring Data JPA `@Procedure` is another way to map a routine onto a repository method, without changing the meaning of the three modes.

## 10. Common errors and how to diagnose them

| Symptom | Possible cause | How to inspect/fix |
| --- | --- | --- |
| Output is always `null`/`0` | Procedure did not assign `OUT`, SQL null, or Java used `getInt` without checking `wasNull` | Read routine code, inspect inputs, use a NULL-aware getter |
| `SQLException` when calling `CALL` | Wrong routine name, missing `EXECUTE` privilege, wrong parameter count/positions | Check schema, routine signature, account, and original error message |
| `INOUT` does not receive input | Only called `registerOutParameter` and forgot `set...`; declared in Spring as `SqlOutParameter` | Set the input value **and** register output/`SqlInOutParameter` |
| Wrong output type / cast exception | Wrong `Types` or assuming the object is always `Integer` | Check SQL column type, use `Number`/`BigDecimal` appropriately |
| Values swapped between two `OUT` parameters | JDBC parameter order diverges from the SQL signature | Match 1-based indices to definition order |
| Spring cannot find metadata | Unsupported driver, metadata privileges, wrong schema/catalog | Declare everything via `declareParameters(...)` and `withoutProcedureColumnMetaDataAccess()` |
| Reading output before execution | `execute` has not been called yet | `set/register` first, `execute`, then `get` |
| Confusing a function's return value with an `OUT` parameter | Wrong syntax or wrong index in `{? = call ...}` | Distinguish `RETURNS/RETURN` from `OUT` parameters |
| `OUT` is correct but table changes rolled back | Routine ran inside a transaction that failed in a later step | Check transaction boundaries and root error |
| `INOUT` unexpectedly remains `NULL` | Initial value was `NULL` or arithmetic with `NULL` | Define a `NULL` policy using `COALESCE`/validation |
| Code works on DB A but fails on DB B | Different `CREATE PROCEDURE` syntax, function modes, SQL types, metadata | Check version-specific DB/driver docs and write integration tests |

**Avoid:**

- Mistakenly assigning `SqlOutParameter` to a parameter that needs to send an input value.
- Using `statement.getInt(...) == 0` to conclude the routine returned 0 without checking `wasNull()`.
- Assuming the iteration order of a `Map` equals the SQL parameter order.
- Treating `execute() == false` as routine failure.
- Using `@Transactional` as if it guarantees all operations are already committed at the moment `OUT` is received.
- Assuming MySQL, PostgreSQL, SQL Server, and Oracle share identical syntax and function modes.

## 11. Self-check exercise and expected results

Given `compute_points` as defined in section 2, predict and verify using `CALL` statements on a test database:

| Input `p_delta` | Initial input `p_total` | OUT `p_double` | INOUT `p_total` after call |
| ---: | ---: | ---: | ---: |
| `5` | `10` | `10` | `15` |
| `-3` | `10` | `-6` | `7` |
| `0` | `10` | `0` | `10` |
| `5` | `NULL` | `10` | `NULL` |

You can verify with SQL:

```sql
SET @total = 10;
CALL compute_points(-3, @double, @total);
SELECT @double AS doubled, @total AS total;
```

The `SELECT` statement should show `doubled = -6` and `total = 7`. There is no cumulative effect between separate calls, because the example routine only computes using parameters and does not write to any table.

**Checklist for real implementation:**

1. Read the routine signature and write down every `IN`, `OUT`, `INOUT` parameter and its SQL type.
2. With JDBC, index starting from **1**: only `set` for `IN`, only `register` for `OUT`, **set + register** for `INOUT`.
3. With Spring, use the right `SqlParameter`, `SqlOutParameter`, `SqlInOutParameter` and supply all required inputs.
4. Execute the routine before reading results; handle `NULL` and type conversion carefully.
5. Distinguish a procedure's `OUT`, a function's `RETURN`, and any accompanying `ResultSet`s.
6. Test against the real target DB/driver, including `NULL`, boundary values, exceptions, transactions, and routine execution privileges.

## References

- Spring Framework – Simple JDBC Classes, `SimpleJdbcCall` and parameter declarations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework – `SqlInOutParameter` Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlInOutParameter.html
- Java JDBC – `CallableStatement` and `registerOutParameter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- MySQL 8.4 – `CREATE PROCEDURE`/`CREATE FUNCTION`, parameter modes: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 – `CALL` and OUT/INOUT variables: https://dev.mysql.com/doc/refman/8.4/en/call.html