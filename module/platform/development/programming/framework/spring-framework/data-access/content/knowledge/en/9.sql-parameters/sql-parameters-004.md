# Specifying SQL Types When a Null Value Lacks Sufficient Inference Info

> **Module:** Spring Framework – Data Access  
> **Topic group:** SQL Parameters  
> **Focus:** SQL type of `null` in JDBC, `JdbcTemplate`, and `NamedParameterJdbcTemplate`

## 1. Why Does Java null Cause Difficulty for JDBC?

When a Java object is non-null, Spring/JDBC can usually infer how to bind it from its runtime type. For example, `String` suggests a string type, `Long` suggests a big integer, and `BigDecimal` suggests a decimal number. Conversely, a `null` value **has no runtime class** to inspect: the same Java `null` could represent an SQL NULL of type `VARCHAR`, `DATE`, `DECIMAL`, `BIGINT`, or a database-specific type.

Example table:

~~~sql
CREATE TABLE task_note (
    id BIGINT PRIMARY KEY,
    note_text VARCHAR(120) NULL,
    estimate DECIMAL(8,2) NULL,
    due_on DATE NULL
);
~~~

Statement:

~~~java
jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) VALUES (?, ?, ?, ?)",
    1L, null, null, null
);
~~~

*may* succeed if the database/driver can infer the types from the `INSERT` column context, or if Spring/JDBC has a suitable metadata/fallback mechanism. However, not every driver and SQL expression provides sufficiently reliable metadata. Some combinations may reject an untyped NULL binding or cause the application to spend time querying metadata.

The problem to solve is **explicitly stating the intended SQL type at the parameter position**. Common approaches:

1. Plain JDBC: `PreparedStatement.setNull(index, Types.DATE)`.
2. `JdbcTemplate`: an `Object[] args` array paired with `int[] argTypes`.
3. `JdbcTemplate`: wrapping a parameter with `SqlParameterValue`.
4. `NamedParameterJdbcTemplate`: using `MapSqlParameterSource` or a `SqlParameterSource` that registers the SQL type.

Always provide the true SQL type from the SQL/schema contract. Do not pick an arbitrary type just to silence an error on one driver.

## 2. Distinguishing Java Type, SQL Type, and SQL NULL

| Concept | Example | Meaning |
| --- | --- | --- |
| Java type | `String`, `Long`, `LocalDate`, `BigDecimal` | Data type on the JVM |
| Java `null` value | `String description = null;` | No object at runtime |
| Column SQL type | `VARCHAR(120)`, `DATE`, `DECIMAL(8,2)` | Data contract in the database |
| JDBC SQL type code | `Types.VARCHAR`, `Types.DATE`, `Types.DECIMAL` | Code passed to the driver for binding |
| SQL `NULL` | `note_text IS NULL` | An SQL marker, not the string `"null"` |
| Unknown SQL type | `SqlParameterSource.TYPE_UNKNOWN` | Spring sentinel, does not describe the target column type |

Three very different actions:

- **Omit the column in INSERT or use DEFAULT:** may trigger the schema's default value.
- **Bind SQL NULL:** requests writing a NULL value if constraints permit; does not automatically trigger DEFAULT.
- **Bind the string `"null"` or `""`:** this is string data, generally not equivalent to SQL NULL.

`NULL` is also not synonymous with `0` for numbers or `false` for booleans. If "the amount is unknown," replacing NULL with 0 changes business rules.

### SQL Type Is Not the Java Variable's Declared Type

Even when a variable is declared:

~~~java
String note = null;
~~~

at runtime there is no `String` object for Spring to inspect its class. The DAO knows the `note_text` column has type `VARCHAR` from the schema; therefore `Types.VARCHAR` is the appropriate metadata when passing NULL. This is knowledge **from SQL**, not "guessing" from a null object.

## 3. Situations Lacking Type Inference Information

### 3.1. PreparedStatement Does Not Know the Parameter Type

In JDBC, an SQL statement may contain `?` at a position whose type is unclear. Some drivers support `PreparedStatement.getParameterMetaData()` well; others have limitations or return incomplete information. With `null`, calling an untyped bind API can lead to varying errors depending on the driver.

**Do not assert** that every `INSERT ... VALUES (?, ?)` with null will fail; the outcome depends on the driver, expression, and metadata provided by the database.

### 3.2. Ambiguous SQL Expressions

Examples:

~~~sql
SELECT ? IS NULL
~~~

or:

~~~sql
SELECT COALESCE(?, ?)
~~~

may not tell the database/driver what type each `?` should be treated as when all values are null. Some databases support inference, while others reject it, especially when an expression is not paired with a typed column.

Options for handling: provide an explicit `Types` code from JDBC; or use `CAST(? AS VARCHAR(...))` with dialect-appropriate syntax when SQL-meaningful. `CAST` is not a portable substitute for binding the right type across all drivers.

### 3.3. Stored Procedure, JSON, UUID, ARRAY Types

Input types for procedures, enums, JSON, UUID, SQL arrays, or custom types may not map directly to a simple Java class. Sometimes `Types.OTHER`, `Types.ARRAY`, a type name, or a driver-specific API is required. Do not treat `Types.OTHER` as a "magic wand" for every unknown type.

### 3.4. Slow Metadata or Failing Drivers

Spring JDBC may query `PreparedStatement.getParameterMetaData().getParameterType(index)` in some untyped-null cases and then fall back depending on the driver. That query can be costly or unreliable. When you already know the SQL type from the schema, passing an explicit type reduces reliance on runtime inference. However, performance impact must be measured on the real driver rather than guessed.

## 4. Plain JDBC: `PreparedStatement.setNull`

This is the foundation for understanding the abstractions above:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE task_note SET due_on = ? WHERE id = ?")) {
    ps.setNull(1, Types.DATE);
    ps.setLong(2, 1L);
    int affected = ps.executeUpdate();
}
~~~

*This snippet illustrates code inside a method that already has `connection`, the table, and imports; it is not a standalone program.*

- `setNull(1, Types.DATE)` passes a DATE-typed SQL NULL to the first `?`.
- `setLong(2, 1L)` binds the ID at the second `?`.
- JDBC parameter indices **start at 1**, not 0.
- `try-with-resources` closes `PreparedStatement`. The connection must be closed/returned according to its owner's lifecycle, especially if participating in a Spring transaction.

The following line does not express the type as clearly:

~~~java
ps.setObject(1, null);
~~~

JDBC also supports `setObject` overloads with a target type, but when specifically binding NULL, `setNull(index, sqlType)` is clearer to read. Do not replace `Types.DATE` with `Types.NULL` when you know the column is `DATE`.

Some SQL types require `setNull(index, sqlType, typeName)`. The type name depends on the database and driver; use it only after checking the provider's contract.

## 5. `JdbcTemplate`: Passing `Object[]` Alongside `int[] argTypes`

`JdbcTemplate` provides an update overload with two parallel arrays:

~~~java
int affected = jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (?, ?, ?, ?)",
    new Object[] {1L, null, null, null},
    new int[] {Types.BIGINT, Types.VARCHAR, Types.DECIMAL, Types.DATE}
);
~~~

*This is illustrative code assuming `jdbcTemplate` and the schema from section 1.*

| `?` position | Java value | SQL type | Target column |
| --- | --- | --- | --- |
| 1 | `1L` | `Types.BIGINT` | `id` |
| 2 | `null` | `Types.VARCHAR` | `note_text` |
| 3 | `null` | `Types.DECIMAL` | `estimate` |
| 4 | `null` | `Types.DATE` | `due_on` |

Each `args[i]` value must match `argTypes[i]`. SQL `?` markers count from 1, while Java arrays count from 0. Adding or removing a placeholder while forgetting to update the type array can cause subtle bugs. For long SQL statements, named parameters usually reduce positional mismatch risk.

### Good Use Cases

- SQL with a fixed number of placeholders.
- Several nullable columns where the driver needs explicit SQL types.
- Wanting to declare the entire parameter contract alongside the statement.
- Code already uses `JdbcTemplate` and does not want to switch to named parameters.

The type array must describe the **actual SQL type**, even when the runtime value is null. For example, `estimate DECIMAL(8,2)` needs `Types.DECIMAL`; do not pick `Types.INTEGER` just because a feature currently displays whole numbers.

## 6. `SqlParameterValue`: Attaching the Type Directly to the Value

If only one or a few parameters need an explicit SQL type, `org.springframework.jdbc.core.SqlParameterValue` is cleaner:

~~~java
jdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (?, ?, ?, ?)",
    2L,
    new SqlParameterValue(Types.VARCHAR, null),
    new SqlParameterValue(Types.DECIMAL, new BigDecimal("12.50")),
    new SqlParameterValue(Types.DATE, null)
);
~~~

Each `SqlParameterValue` holds an SQL type together with the value. Even when the value is null, the metadata remains. `JdbcTemplate` overloads accepting ordinary argument arrays can accept this wrapper instead of inferring solely from Java values.

This approach is useful when:

- The SQL has many parameters, yet only two nullable values need explicit typing.
- An adapter wants to create a metadata-carrying value and pass it along.
- You want to avoid parallel `int[] argTypes` arrays across two large lists.

`SqlParameterValue` also supports extra metadata such as scale for decimals or type name for custom types when needed. Do not mix conflicting metadata between the wrapper and an overload declaring a separate `argTypes` array at the same position.

### With Database-Specific Types

API shape example:

~~~java
new SqlParameterValue(Types.OTHER, "vendor_type_name", null)
~~~

This is a **non-portable illustration**, not code that runs across all DBs. The type name must be supported by the driver/database; JSONB, UUID, enums, and arrays may require different bindings.

### `Types.NULL` Is Not the Right Type for Every Nullable Column

If you know the column is `DECIMAL`, `Types.DECIMAL` carries clearer meaning than `Types.NULL`. `Types.NULL` is a generic JDBC code used in certain situations, not a substitute for the column contract. Prefer the specific type from the schema.

## 7. Named Parameters: `MapSqlParameterSource` and `registerSqlType`

`NamedParameterJdbcTemplate` supports SQL by name:

~~~sql
INSERT INTO task_note(id, note_text, estimate, due_on)
VALUES (:id, :noteText, :estimate, :dueOn)
~~~

Register value and type together:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource()
        .addValue("id", 3L, Types.BIGINT)
        .addValue("noteText", null, Types.VARCHAR)
        .addValue("estimate", null, Types.DECIMAL)
        .addValue("dueOn", null, Types.DATE);

namedParameterJdbcTemplate.update(
    "INSERT INTO task_note(id, note_text, estimate, due_on) " +
    "VALUES (:id, :noteText, :estimate, :dueOn)",
    source
);
~~~

*This is a pattern inside a method with `namedParameterJdbcTemplate`, not a standalone class.* Spring maps parameter names to JDBC placeholder positions, while `MapSqlParameterSource` stores both value and SQL type per name.

You can also supply metadata in two steps:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource();
source.addValue("dueOn", null);
source.registerSqlType("dueOn", Types.DATE);
~~~

Conceptually, the outcome is the same as `addValue("dueOn", null, Types.DATE)`: the SQL type is registered for that specific name.

### With `BeanPropertySqlParameterSource`

If parameters come from a bean with properties:

~~~java
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(command);
source.registerSqlType("dueOn", Types.DATE);
~~~

*Example only illustrates the API with an existing `command` variable.* `BeanPropertySqlParameterSource` can inspect property metadata and infer types for some Java types; yet for nullable fields and special drivers/SQL types, explicit type registration remains helpful.

### Do Not Use `Map.of` with Null Values

Fails immediately in Java:

~~~java
Map<String, Object> params = Map.of("dueOn", null);
~~~

`Map.of` does not allow null keys or values, so constructing the map throws `NullPointerException` **before SQL is even called**. `MapSqlParameterSource` accepts null and also supports SQL type metadata, making it far better suited for nullable named parameters.

Passing an ordinary `Map<String, Object>` does not magically let Spring know the SQL type of every null; a plain map holds values without metadata equivalent to `SqlParameterSource`.

## 8. Common SQL Type Cross-Reference

| SQL Column/Expression | Common JDBC type for NULL | Common non-null Java value |
| --- | --- | --- |
| `VARCHAR` | `Types.VARCHAR` | `String` |
| `CHAR` | `Types.CHAR` | `String` |
| `INTEGER` | `Types.INTEGER` | `Integer` |
| `BIGINT` | `Types.BIGINT` | `Long` |
| `SMALLINT` | `Types.SMALLINT` | `Short` |
| `DECIMAL(p,s)` | `Types.DECIMAL` | `BigDecimal` |
| `NUMERIC(p,s)` | `Types.NUMERIC` | `BigDecimal` |
| `DATE` | `Types.DATE` | `LocalDate` / `java.sql.Date` depending on driver |
| `TIMESTAMP` | `Types.TIMESTAMP` | `LocalDateTime` / `Timestamp` depending on driver |
| `TIMESTAMP WITH TIME ZONE` | `Types.TIMESTAMP_WITH_TIMEZONE` when supported | `OffsetDateTime` or compatible type |
| `BOOLEAN` | `Types.BOOLEAN` | `Boolean` |
| `VARBINARY` | `Types.VARBINARY` | `byte[]` |
| Vendor-specific JSON/UUID/enum | Possibly `Types.OTHER` with type name/adapter | Depends on DB and driver |

This table is directional; exact types must match the real schema and driver contract. A `DATE` column's `null` should not be replaced with an empty string, and a `DECIMAL` column's `null` should not be turned into 0 if business rules distinguish the two states.

### Scale and Precision

SQL `DECIMAL(8,2)` has precision 8 and scale 2. Binding NULL with `Types.DECIMAL` states the type, but does not create a rounding policy for **non-null** values. For currency, use `BigDecimal` and explicit rounding rules. Do not use `double` just because it is convenient when printing numbers.

### SQL DATE/TIMESTAMP Differ from Strings

Declaring `Types.DATE` for null does not mean Spring will automatically parse any `String` into an accurate date when non-null. For populated values, choose a Java date/time type supported by the JDBC driver; avoid relying on locale or non-standard date strings.

## 9. Runnable Java 17+ Demo: Four Ways to Bind Typed NULL

Example using **JDK 17+**, **Maven 3.9+**, **Spring JDBC 6.1.14**, and **H2 2.2.224**. In-memory H2 retains data in-process when `DB_CLOSE_DELAY=-1`. Goal: insert four rows using four binding approaches and deterministically read back NULL state.

### 9.1. File Structure

~~~text
typed-null-parameters/
├── pom.xml
└── src/main/java/demo/
    └── TypedNullDemo.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>typed-null-parameters</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. `src/main/java/demo/TypedNullDemo.java`

~~~java
package demo;

import java.math.BigDecimal;
import java.sql.Types;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class TypedNullDemo {

    private static final String INSERT_SQL =
            "INSERT INTO task_note(id, note_text, estimate, due_on) " +
            "VALUES (?, ?, ?, ?)";

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:typed_null_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        jdbc.execute("CREATE TABLE task_note (" +
                "id BIGINT PRIMARY KEY, " +
                "note_text VARCHAR(120) NULL, " +
                "estimate DECIMAL(8,2) NULL, " +
                "due_on DATE NULL)");

        // A: Object[] with int[] SQL types.
        jdbc.update(
                INSERT_SQL,
                new Object[] {1L, null, null, null},
                new int[] {
                        Types.BIGINT, Types.VARCHAR,
                        Types.DECIMAL, Types.DATE
                });

        // B: SqlParameterValue attaches type to each argument.
        jdbc.update(
                INSERT_SQL,
                2L,
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(
                        Types.DECIMAL, new BigDecimal("12.50")),
                new SqlParameterValue(Types.DATE, null));

        // C: Named parameters with SQL type by name.
        MapSqlParameterSource source = new MapSqlParameterSource()
                .addValue("id", 3L, Types.BIGINT)
                .addValue("noteText", null, Types.VARCHAR)
                .addValue("estimate", null, Types.DECIMAL)
                .addValue("dueOn", null, Types.DATE);
        named.update(
                "INSERT INTO task_note(id, note_text, estimate, due_on) " +
                "VALUES (:id, :noteText, :estimate, :dueOn)",
                source);

        // D: PreparedStatementSetter uses JDBC setNull.
        jdbc.update(INSERT_SQL, ps -> {
            ps.setLong(1, 4L);
            ps.setNull(2, Types.VARCHAR);
            ps.setNull(3, Types.DECIMAL);
            ps.setNull(4, Types.DATE);
        });

        Integer total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note", Integer.class);

        Integer allNull = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note " +
                "WHERE note_text IS NULL " +
                "AND estimate IS NULL AND due_on IS NULL",
                Integer.class);

        Integer nullNotes = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_note WHERE note_text IS NULL",
                Integer.class);

        BigDecimal estimate2 = jdbc.queryForObject(
                "SELECT estimate FROM task_note WHERE id = ?",
                BigDecimal.class, 2L);

        System.out.println("Total rows: " + total);
        System.out.println("All nullable columns NULL: " + allNull);
        System.out.println("NULL notes: " + nullNotes);
        System.out.println("Estimate of id=2: " + estimate2);
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TypedNullDemo
~~~

**Lines printed by the program (excluding Maven logs):**

~~~text
Total rows: 4
All nullable columns NULL: 3
NULL notes: 4
Estimate of id=2: 12.50
~~~

### 9.4. Explaining the Results

Row **1** has its three nullable columns bound via an SQL type array. Row **2** receives `estimate = 12.50` and the other two nullable columns as NULL via `SqlParameterValue`. Row **3** uses named parameters with type metadata; row **4** uses JDBC setters inside `JdbcTemplate`.

All four rows have `note_text IS NULL`. Only rows 1, 3, and 4 have **all three nullable columns NULL**. In H2, `DECIMAL(8,2)` preserves scale 2, so the estimate for row 2 prints `12.50`.

The example **does not deliberately throw an error with an untyped NULL**, because whether that succeeds or fails depends on the driver. What we verify is that all four strategies for **passing explicitly typed NULLs** produce the expected data in the demo database.

`DriverManagerDataSource` is for learning only, not a pool for production. The demo does not open multi-step transactions and does not illustrate stored procedures or custom JSON types.

## 10. SQL NULL Still Follows Three-Valued Logic

Binding NULL with the right type solves **driver parameter acceptance**; it does not alter SQL semantics.

If you want to find rows where `note_text` is NULL, the following statement **does not match intent**:

~~~sql
SELECT id FROM task_note WHERE note_text = ?
~~~

Even when binding `?` with a VARCHAR-typed SQL NULL, comparing against NULL yields `UNKNOWN` under three-valued logic, not TRUE as when comparing two normal strings.

Correct when searching for NULL columns:

~~~sql
SELECT id FROM task_note WHERE note_text IS NULL
~~~

### Optional Filters and Null Placeholders

A pattern like:

~~~sql
WHERE (? IS NULL OR note_text = ?)
~~~

may not let the driver infer the placeholder's type inside `? IS NULL`, and also requires two bind positions even though they represent one filter.

Declare the type at both positions:

~~~java
List<Long> ids = jdbcTemplate.queryForList(
    "SELECT id FROM task_note " +
    "WHERE (? IS NULL OR note_text = ?) ORDER BY id",
    Long.class,
    new SqlParameterValue(Types.VARCHAR, filter),
    new SqlParameterValue(Types.VARCHAR, filter)
);
~~~

*This illustrates code inside a method with a nullable String `filter`, assuming the SQL dialect supports this expression.* OR-style queries can affect query plans/indexes; when there are many optional conditions, branching SQL construction explicitly can be better.

### Avoid Confusing Default with NULL

~~~sql
INSERT INTO task_note(id) VALUES (5)
~~~

and

~~~sql
INSERT INTO task_note(id, due_on) VALUES (5, NULL)
~~~

do not necessarily share the same meaning when the schema defines `DEFAULT` for `due_on`. The first may use DEFAULT, while the second requests NULL and must also satisfy any `NOT NULL` constraint. Do not bind SQL NULL expecting the database to automatically substitute the default unless the schema defines a specific mechanism for it.

## 11. Notes When Using Different Drivers

### 11.1. `Types.OTHER` and Type Names

Types like PostgreSQL JSONB, UUID, or enums and Oracle-specific types may require special APIs. A pattern like:

~~~java
new SqlParameterValue(Types.OTHER, "vendor_type_name", null)
~~~

only shows that Spring can carry a type name; that name is **illustrative** and will not run on an arbitrary database. Use the type/driver metadata confirmed by the vendor's documentation.

### 11.2. Do Not Infer Production Behavior from H2

An untyped null bind may work on H2 yet fail on Oracle/PostgreSQL, or vice versa. SQL dialect, statement metadata, and driver version all have an impact. For critical JDBC statements, run integration tests on the target database/driver, covering both null and non-null branches.

### 11.3. Property Controlling `ParameterMetaData` Queries

Spring JDBC has a property:

~~~text
spring.jdbc.getParameterType.ignore
~~~

This configuration controls whether `StatementCreatorUtils` skips looking up `PreparedStatement.getParameterMetaData().getParameterType(...)` when handling an unknown-type null. Fallbacks depend on the driver. Do not flip an application-wide property just because one query failed; prefer declaring the exact type on the offending parameter, measuring, and verifying the root cause first.

### 11.4. A Right SQL Type Does Not Fix Wrongly Typed Data

When non-null, passing the string `"2026-10-30"` with `Types.DATE` does not make every JDBC driver automatically parse the date correctly. Use an appropriate Java date/time type. SQL type metadata does not replace validation, conversion, `CHECK` constraints, `NOT NULL`, or rounding policies.

## 12. Batch Updates and Stored Procedures

Batches can mix null and non-null rows. Even if the first row allows type inference, another row still needs properly typed null binding. With `BatchPreparedStatementSetter`, write explicit branches:

~~~java
if (noteText == null) {
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(2, noteText);
}
~~~

*This is a snippet inside a callback with `ps` and `noteText`, not a complete method.* With named batches, a `SqlParameterSource` per element can carry metadata. Do not rely on the order or type of one batch row to substitute for the contract of every row.

Stored procedures have their own `IN`/`OUT` contracts and may require `SqlParameter`, `SimpleJdbcCall`, and specific type names. `ARRAY`, `STRUCT`, `CLOB`, or `BLOB` may require `SqlTypeValue` or driver APIs. Binding a VARCHAR NULL does not automatically cover how to bind those types.

## 13. Troubleshooting Table

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| Driver reports unknown SQL type for NULL | Insufficient metadata for `?` | Specify placeholder type via `Types` or `SqlParameterValue` |
| Binding works with values but fails on null | Non-null object class enables inference; null carries no type | Test and declare SQL type for the null branch |
| `args`/`argTypes` arrays misaligned | `?` markers, values, and types are out of order | Cross-check placeholders left to right |
| SQL has many parameters, hard to read | Long positional parameter list | `NamedParameterJdbcTemplate` and `MapSqlParameterSource` |
| `Map.of(..., null)` fails | Java `Map.of` rejects null | Use `MapSqlParameterSource` |
| `Types.INTEGER` used for a DATE column | Declared type violates schema | Fix `java.sql.Types` and test on target DB |
| `WHERE field = ?` fails to find NULL rows | SQL three-valued logic | Use `IS NULL` as intended |
| Inserting NULL expecting column DEFAULT | NULL differs from omitting column/DEFAULT | Fix INSERT syntax and understand schema |
| Typed null passes on H2 but fails on real driver | Vendor-specific types or differing metadata | Integration test with real driver/database |
| Typed NULL does not fix `NOT NULL` error | Constraint forbids storing NULL | Fix data or business logic, not with a fake type |
| Performance drops when binding unknown NULL | Querying parameter metadata or query plan | Measure, identify root cause, specify SQL type, inspect execution plan |

### Diagnostic Workflow

1. **Identify the exact SQL and every `?`.** Which placeholder index maps to which column/expression type?
2. **Check the Java value.** Is it a true null, empty string, string `"null"`, or an object?
3. **Check the binding API.** `PreparedStatement.setNull`, `JdbcTemplate` type array, `SqlParameterValue`, or named source?
4. **Cross-check the schema.** Choose the right `Types`, including scale/type name when needed.
5. **Read the exception cause.** Distinguish metadata errors, SQL syntax, constraints, conversion, and SQL NULL logic.
6. **Reproduce on a real database.** Run both null and non-null branches with production-like driver and schema.
7. **Measure before changing global settings.** Only adjust metadata properties with evidence of failure or latency.

You do not need to log sensitive data values to investigate. Logging the parameter role, index, SQL type, and stack trace is usually enough to locate the issue.

## 14. Self-Check Questions

**1. Why can `String value = null` still cause trouble when binding?**  
Because at runtime there is no String object, and the SQL/driver cannot always infer the placeholder's type.

**2. What does JDBC use to bind a DATE-typed NULL?**  
`ps.setNull(position, Types.DATE)`, with 1-based parameter indexing.

**3. In `update(sql, Object[], int[])`, what does the SQL type attach to?**  
It attaches to the placeholder at the matching position in the `args` array; both arrays must have the same order and length.

**4. When only one parameter needs metadata, what should you choose?**  
`new SqlParameterValue(Types.VARCHAR, null)` is the concise option with overloads accepting ordinary arguments.

**5. With named parameters, where is the SQL type declared?**  
`MapSqlParameterSource.addValue(name, null, Types.DATE)` or `registerSqlType(name, Types.DATE)`.

**6. Is using `Map.of("x", null)` safe?**  
No. This Java factory throws `NullPointerException` for null keys/values.

**7. Is `Types.NULL` appropriate for every nullable column?**  
No. If a column is DATE, DECIMAL, or VARCHAR, choose the specific type when the schema is known.

**8. Does binding a VARCHAR-typed NULL make `col = ?` match SQL NULL values?**  
No. Use `IS NULL`; SQL NULL follows three-valued logic.

**9. Why test on the target DB even if the H2 demo succeeds?**  
Because JDBC drivers, vendor types, and parameter metadata differ.

**10. Does declaring the SQL type replace transactions or validation?**  
No. It describes how to bind; transactions, constraints, validation, and SQL logic belong to separate mechanisms.

## 15. Official Reading Sources

- [Spring Framework – Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): three ways to declare SQL types and handle NULL.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): using `JdbcTemplate` and SQL arguments.
- [Spring 6.1 Javadoc – SqlParameterValue](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html).
- [Spring 6.1 Javadoc – MapSqlParameterSource](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- [Spring 6.1 Javadoc – StatementCreatorUtils](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/StatementCreatorUtils.html).
- [Java SE 17 – java.sql.Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html).

**Takeaway:** Java `null` cannot tell the placeholder's SQL type. When the driver or SQL expression cannot infer enough, declare the **true SQL type from the schema** via `setNull`, `argTypes`, `SqlParameterValue`, or `SqlParameterSource`. Declaring the right type helps JDBC bind unambiguously, without changing SQL NULL semantics or transaction rules.
