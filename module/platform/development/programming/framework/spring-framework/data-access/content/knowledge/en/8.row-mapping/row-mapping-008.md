# Choosing Nullable Java Types and Handling wasNull() When Reading Primitives

> **Rule:** SQL `NULL` represents an unknown or missing value, whereas Java primitive types such as `int`, `long`, `boolean`, and `double` **cannot hold `null`**. In JDBC, primitive getters such as `ResultSet.getInt(...)` return **`0`** if the column is SQL `NULL`, and `getBoolean(...)` returns **`false`** if it is SQL `NULL`. Therefore, if a column can be `NULL`, read it with a nullable type or call **`ResultSet.wasNull()` immediately after the primitive getter** so information is not lost.

This lesson belongs to the **result mapping** section of Spring Framework Data Access. The focus is on turning a SQL row into a Java object with `RowMapper`, preserving the semantics of SQL `NULL`, and choosing Java types according to data constraints.

## 1. Why Does SQL NULL Cause Silent Bugs During Mapping?

Consider the following table:

```sql
CREATE TABLE measurements (
    id BIGINT PRIMARY KEY,
    score INTEGER NULL,
    active BOOLEAN NULL,
    attempts BIGINT NULL,
    note VARCHAR(80) NULL
);

INSERT INTO measurements (id, score, active, attempts, note) VALUES
    (1, NULL, NULL, NULL, NULL),
    (2, 0, FALSE, 0, ''),
    (3, 42, TRUE, 123, 'ready');
```

The three rows carry distinct meanings:

- `id=1`: score, active status, attempt count, and note **have no value yet**.
- `id=2`: score **is 0**, status **is `false`**, attempts **is 0**, and note **is an empty string**. All are real values, not SQL `NULL`.
- `id=3`: score 42, status true, attempts 123, and note "ready".

If mapped with:

```java
int score = rs.getInt("score");
boolean active = rs.getBoolean("active");
long attempts = rs.getLong("attempts");
```

then rows `id=1` and `id=2` look identical in those variables: `score=0`, `active=false`, `attempts=0`. This is what causes silent business bugs: the application may misinterpret "not yet scored" as "scored 0", "activity unknown" as "inactive", or "not yet counted" as "counted 0 times".

When SQL permits `NULL` and that distinction matters, **the domain model must preserve the absent state** using types such as `Integer`, `Boolean`, `Long`, or a clear value object.

## 2. Exact Contract of ResultSet Getters

`java.sql.ResultSet` provides typed getters. They accept a **1-based column index** or a **column label** (including aliases when SQL uses `AS`).

| SQL / JDBC getter | Java return type | If SQL is `NULL` |
| --- | --- | --- |
| `getInt(...)` | `int` | `0` |
| `getLong(...)` | `long` | `0L` |
| `getShort(...)`, `getByte(...)` | `short`, `byte` | `0` |
| `getDouble(...)`, `getFloat(...)` | `double`, `float` | `0.0` |
| `getBoolean(...)` | `boolean` | `false` |
| `getString(...)` | `String` | Java `null` |
| `getBigDecimal(...)` | `BigDecimal` | Java `null` |
| `getDate(...)`, `getTimestamp(...)` | `java.sql.Date`, `Timestamp` | Java `null` |
| `getObject(...)` | `Object` | Java `null` |
| `getObject(label, Integer.class)` | `Integer` if conversion is supported | Java `null` |

**Warning:** Primitive getters do not throw an exception on SQL `NULL`. They typically return the Java type's default value and update state so `wasNull()` can inspect it. Thus, the absence of an exception **does not prove the column had a value**.

### What Does wasNull() Do?

```java
boolean wasNull = rs.wasNull();
```

`ResultSet.wasNull()` returns `true` when **the value of the column read by the most recent getter** was SQL `NULL`. It does not check "whether any row is null in the ResultSet", nor is it a null property of the whole row.

Correct sequence:

```java
int rawScore = rs.getInt("score");
boolean scoreWasNull = rs.wasNull(); // Check immediately after getInt

Integer score = scoreWasNull ? null : rawScore;
```

Result:

| SQL value of `score` | `rawScore` | `scoreWasNull` | `score` |
| --- | ---: | --- | --- |
| `NULL` | `0` | `true` | `null` |
| `0` | `0` | `false` | `Integer.valueOf(0)` |
| `42` | `42` | `false` | `Integer.valueOf(42)` |

The key point is that **both SQL `NULL` and SQL `0` yield `rawScore=0`**, while `wasNull()` distinguishes them.

## 3. wasNull() Must Be Called Immediately After the Getter Being Checked

### Correct Pattern

```java
int rawScore = rs.getInt("score");
Integer score = rs.wasNull() ? null : rawScore;

boolean rawActive = rs.getBoolean("active");
Boolean active = rs.wasNull() ? null : rawActive;

long rawAttempts = rs.getLong("attempts");
Long attempts = rs.wasNull() ? null : rawAttempts;
```

Each `wasNull()` call follows its column's getter immediately. No other column-reading call sits in between.

### Wrong Pattern: Reading a Second Column Before Checking the First

```java
int rawScore = rs.getInt("score");
String note = rs.getString("note");
boolean scoreWasNull = rs.wasNull(); // WRONG: checks NOTE, no longer SCORE
```

Here `wasNull()` reflects **the most recent `getString("note")` read**, making the variable name `scoreWasNull` misleading. If `score` is SQL `NULL` while `note` has a value, the variable becomes `false` and the application thinks the score is genuinely 0.

Fix:

```java
int rawScore = rs.getInt("score");
boolean scoreWasNull = rs.wasNull();

String note = rs.getString("note");
```

Between a getter and `wasNull()`, non-column-reading Java calculations can technically appear, yet **the safest and most reviewable rule is to call it immediately**, especially in a `RowMapper` with many columns or helper methods.

### Wrong Pattern: Guessing from the Default Value

```java
int rawScore = rs.getInt("score");
Integer score = (rawScore == 0) ? null : rawScore; // WRONG
```

The number `0` is a valid SQL `INTEGER` value; the snippet above loses the case where the score is genuinely 0.

```java
boolean rawActive = rs.getBoolean("active");
Boolean active = rawActive ? true : null; // WRONG
```

This loses the SQL `FALSE` case (a real value). Especially for three-state business flags (*true / false / unknown*), the Java `Boolean` type and checking `wasNull()` are necessary.

## 4. Choosing Java Types Based on Data Nullability

Type design rules:

- If a column is **`NOT NULL` and the contract genuinely always has a value**, an appropriate primitive can be used: `int`, `long`, `boolean`. For example, primary key `id BIGINT PRIMARY KEY` commonly maps to `long`.
- If a column allows **`NULL` and carries business meaning**, use a wrapper: `Integer`, `Long`, `Boolean`, `Double`, `Float`, etc.
- For money or exact decimals, prefer `BigDecimal` over `double` regardless of nullability. `BigDecimal` is an object and naturally holds Java `null`.
- For strings, dates/times, and objects, the appropriate getters normally already return Java `null` on SQL `NULL`, though a clear business policy on allowing null is still needed.
- If business logic needs to distinguish both *absent* and *defaulted value*, the domain model should express that clearly rather than collapsing every `NULL` into an implicit sentinel such as 0 or an empty string.

Record example:

```java
public record Measurement(
    long id,           // id is NOT NULL, primitive can be used
    Integer score,     // NULL differs from 0
    Boolean active,    // NULL differs from false
    Long attempts,     // NULL differs from 0L
    String note        // NULL differs from ""
) {}
```

This is a Java 17+ record definition independent of Spring; if placed in a public top-level file, the file name is `Measurement.java`.

| SQL Column | Schema assumption | Recommended Java type | Reason |
| --- | --- | --- | --- |
| `id BIGINT PRIMARY KEY` | Never NULL | `long` / `Long` | `long` fits when ID is guaranteed present |
| `score INTEGER NULL` | Nullable | `Integer` | Does not conflate "unscored" with 0 |
| `active BOOLEAN NULL` | Nullable | `Boolean` | Expresses true / false / unknown |
| `attempts BIGINT NULL` | Nullable | `Long` | Does not conflate "uncounted" with 0 |
| `price DECIMAL(12,2) NULL` | Nullable | `BigDecimal` | Preserves monetary precision and absence |
| `note VARCHAR NULL` | Nullable | `String` | Distinguishes Java `null` from empty string |
| `created_at TIMESTAMP NULL` | Nullable | `LocalDateTime` or appropriate temporal type | Preserves absence; consider timezone/dialect |

Choosing a wrapper does not mean a property **should always be allowed to be null**. After reading the data, a service can enforce constraints and throw an error if a value is missing against contract. However, do not let JDBC silently turn null into 0/false before checking: the information is already lost.

## 5. Two Strategies for Reading Nullable Types from ResultSet

### 5.1. Primitive Getter + wasNull(): Explicit and Well-Controlled

```java
static Integer nullableInt(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    int value = rs.getInt(label);
    return rs.wasNull() ? null : value;
}

static Boolean nullableBoolean(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    boolean value = rs.getBoolean(label);
    return rs.wasNull() ? null : value;
}

static Long nullableLong(java.sql.ResultSet rs, String label)
        throws java.sql.SQLException {
    long value = rs.getLong(label);
    return rs.wasNull() ? null : value;
}
```

These are helper methods placed **inside a Java class** with corresponding JDBC imports or fully qualified names as above. Advantage: the mechanism is explicit, relies on the standard `getInt`/`getBoolean`/`getLong`/`wasNull` contract, and does not depend on driver-specific `getObject(..., Class)` conversion support.

For columns needing special conversions, you still must pick a getter matching the SQL type. `wasNull()` only solves absence; it **does not fix wrong-type reads or cast overflows**.

### 5.2. Typed getObject(): Shorter When the JDBC Driver Supports Conversion

With JDBC 4.1+, the API provides an overload:

```java
Integer score = rs.getObject("score", Integer.class);
Boolean active = rs.getObject("active", Boolean.class);
Long attempts = rs.getObject("attempts", Long.class);
```

Per the JDBC contract, when the column is SQL `NULL`, the returned object is Java `null`. You do not need `wasNull()` to distinguish null on these reference-typed values.

**Important condition:** the driver must support converting from the SQL type to the requested Java type. A driver may throw `SQLException` or `SQLFeatureNotSupportedException` if the conversion is unsupported. Test on the actual driver/DBMS, especially with `BOOLEAN`, `UUID`, date/time types, non-standard numbers, or older drivers. Avoid claiming every SQL type has one fixed Java conversion.

For maximum portability, the `getInt() + wasNull()` pattern remains very clear. When a team standardizes on a modern driver whose typed `getObject` has been tested, the second approach is often more concise.

### 5.3. Object-Returning Getters That Handle NULL Naturally

```java
String note = rs.getString("note");
java.math.BigDecimal amount = rs.getBigDecimal("amount");
java.sql.Timestamp created = rs.getTimestamp("created_at");
```

For the corresponding columns, if SQL is `NULL`, these getters normally return Java `null` per the JDBC contract. You do not need `wasNull()` just to tell whether a `String` is null. However, with mismatched SQL numeric/datetime types, you may still need to check conversion, timezone, precision, or `java.time` mapping.

## 6. A Plain Java Example to Understand wasNull Logic

Suppose `rs` is a `ResultSet` **already positioned on the current row** (for example inside a plain JDBC `while (rs.next())` loop, or inside a `RowMapper` callback invoked by Spring). The snippet below performs manual mapping:

```java
long id = rs.getLong("id"); // ID NOT NULL
int rawScore = rs.getInt("score");
Integer score = rs.wasNull() ? null : rawScore;

boolean rawActive = rs.getBoolean("active");
Boolean active = rs.wasNull() ? null : rawActive;

long rawAttempts = rs.getLong("attempts");
Long attempts = rs.wasNull() ? null : rawAttempts;

String note = rs.getString("note");

Measurement row = new Measurement(id, score, active, attempts, note);
```

This is a **code fragment inside a method that has `ResultSet rs`** and the `Measurement` record above; there is no standalone `main`. Note the order of each getter/`wasNull()` pair.

With the SQL data for `id=1` from the example, the record must be:

```text
Measurement[id=1, score=null, active=null, attempts=null, note=null]
```

For `id=2`:

```text
Measurement[id=2, score=0, active=false, attempts=0, note=]
```

`note=` at the end reflects the empty Java string, **not** `note=null`. Printed output alone does not visually distinguish every special whitespace character, so tests should compare explicitly using `assertEquals("")` and `assertNull(...)`.

### If You Only Need to Flag Missing Data

Sometimes an application does not need to keep the integer itself, only whether the column had a value:

```java
rs.getInt("score");
boolean missingScore = rs.wasNull();
```

This pattern is valid, though if you need to use the score afterward, store the value together with its null flag. Do not call `getInt` and then move on to another column's getter while trying to rely on the old `wasNull()` state.

## 7. Spring JDBC RowMapper: Where to Handle Nullability per Row

In Spring, `JdbcTemplate.query(sql, rowMapper)` iterates the `ResultSet` and calls `RowMapper.mapRow(rs, rowNum)` for each row. Spring **has already moved the cursor to the current row before calling the mapper**; inside `mapRow`, **do not call `rs.next()`**. `RowMapper` should be pure mapping logic and must not close `ResultSet` or `Connection`.

Contract:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
```

This is a **minimal illustrative signature** of the Spring interface; in a project you import `org.springframework.jdbc.core.RowMapper` rather than redeclaring it.

A complete mapper:

```java
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public final class MeasurementRowMapper implements RowMapper<Measurement> {
    @Override
    public Measurement mapRow(ResultSet rs, int rowNum) throws SQLException {
        long id = rs.getLong("id");

        int rawScore = rs.getInt("score");
        Integer score = rs.wasNull() ? null : rawScore;

        boolean rawActive = rs.getBoolean("active");
        Boolean active = rs.wasNull() ? null : rawActive;

        long rawAttempts = rs.getLong("attempts");
        Long attempts = rs.wasNull() ? null : rawAttempts;

        String note = rs.getString("note");
        return new Measurement(id, score, active, attempts, note);
    }
}
```

The class requires the `Measurement` record in the same package or properly imported. It can be reused across queries that provide all five columns/aliases. If SQL omits `attempts` or changes an alias, JDBC will report a missing column; verify the column list directly in SQL.

**Why place nullability logic in the mapper?** Because the mapper is where SQL representation is translated directly into Java representation. When all queries share a consistent mapper, the repository/service layers never have to guess whether `0` was a lost SQL NULL.

### Lambda RowMapper and Helpers

You can use a concise lambda:

```java
List<Measurement> all = jdbc.query(
    "SELECT id, score, active, attempts, note FROM measurements ORDER BY id",
    (rs, rowNum) -> {
        int value = rs.getInt("score");
        Integer score = rs.wasNull() ? null : value;

        boolean flag = rs.getBoolean("active");
        Boolean active = rs.wasNull() ? null : flag;

        long attemptsValue = rs.getLong("attempts");
        Long attempts = rs.wasNull() ? null : attemptsValue;

        return new Measurement(
            rs.getLong("id"),
            score,
            active,
            attempts,
            rs.getString("note")
        );
    }
);
```

This is a **snippet inside a method** with an injected `jdbc` (`JdbcOperations` or `JdbcTemplate`) and an existing `Measurement` record. Both class-based and lambda mappers are valid; for complex mappers, a dedicated class or `nullableInt`/`nullableBoolean`/`nullableLong` helpers are usually easier to inspect.

## 8. Runnable Spring Boot/H2 Example: Preserving SQL NULL

This practical example uses Java 17+, Spring Boot 3.3+, Spring JDBC, and in-memory H2. Goal: insert real SQL `NULL`/0/false values and observe the distinct Java mappings. This is a **multi-file Spring Boot application**, runnable when placed in a Boot Gradle project configured with the corresponding plugin and dependency management.

### 8.1. Dependencies and Configuration

In a `build.gradle` already configured for Spring Boot, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

The block above is not a full build script. Use a Spring Boot plugin compatible with your JDK and dependencies. With Maven, equivalent dependencies can be used.

File **`src/main/resources/application.yml`**:

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:nullable_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

### 8.2. Record Representing Nullable Fields

File **`src/main/java/example/Measurement.java`**:

```java
package example;

public record Measurement(
    long id,
    Integer score,
    Boolean active,
    Long attempts,
    String note
) {}
```

### 8.3. Repository and RowMapper

File **`src/main/java/example/MeasurementRepository.java`**:

```java
package example;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class MeasurementRepository {
    private static final RowMapper<Measurement> MAPPER =
        (rs, rowNum) -> new Measurement(
            rs.getLong("id"),
            nullableInt(rs, "score"),
            nullableBoolean(rs, "active"),
            nullableLong(rs, "attempts"),
            rs.getString("note")
        );

    private final JdbcOperations jdbc;

    public MeasurementRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public List<Measurement> findAll() {
        return jdbc.query(
            "SELECT id, score, active, attempts, note " +
            "FROM measurements ORDER BY id",
            MAPPER
        );
    }

    private static Integer nullableInt(ResultSet rs, String col)
            throws SQLException {
        int value = rs.getInt(col);
        return rs.wasNull() ? null : value;
    }

    private static Boolean nullableBoolean(ResultSet rs, String col)
            throws SQLException {
        boolean value = rs.getBoolean(col);
        return rs.wasNull() ? null : value;
    }

    private static Long nullableLong(ResultSet rs, String col)
            throws SQLException {
        long value = rs.getLong(col);
        return rs.wasNull() ? null : value;
    }
}
```

`JdbcOperations` is the interface implemented by `JdbcTemplate`; Spring Boot auto-configures `JdbcTemplate` from the `DataSource` bean. The repository only knows the query API and mapper. The helpers never leak `ResultSet` outside the callback and each calls `wasNull()` right after its getter.

### 8.4. Seeding Data and Printing Results

File **`src/main/java/example/NullableDemoApplication.java`**:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class NullableDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(NullableDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, MeasurementRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE measurements (
                    id BIGINT PRIMARY KEY,
                    score INTEGER NULL,
                    active BOOLEAN NULL,
                    attempts BIGINT NULL,
                    note VARCHAR(80) NULL
                )
                """);

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 1L, null, null, null, null);

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 2L, 0, false, 0L, "");

            jdbc.update("""
                INSERT INTO measurements
                    (id, score, active, attempts, note)
                VALUES (?, ?, ?, ?, ?)
                """, 3L, 42, true, 123L, "ready");

            repo.findAll().forEach(System.out::println);

            Integer missing = jdbc.queryForObject(
                "SELECT score FROM measurements WHERE id = ?",
                Integer.class, 1L
            );
            System.out.println("scalarNull=" + missing);
        };
    }
}
```

Run in the Gradle Spring Boot project:

```bash
./gradlew bootRun
```

On Windows, run `gradlew.bat bootRun`. With a fresh in-memory H2 database and no extra schema/seed scripts, aside from Spring logs, **the lines printed by the program** are:

```text
Measurement[id=1, score=null, active=null, attempts=null, note=null]
Measurement[id=2, score=0, active=false, attempts=0, note=]
Measurement[id=3, score=42, active=true, attempts=123, note=ready]
scalarNull=null
```

Why is the output correct?

1. `id=1`: the three primitive getters return default values, yet `wasNull()` right after each returns true; the mapper converts them to `null` in `Integer`/`Boolean`/`Long`. `getString("note")` returns Java `null`.
2. `id=2`: `wasNull()` is false for `0`, `false`, `0L`; the mapper preserves the real values. The empty string prints as `note=`.
3. `id=3`: normal values are preserved.
4. `ORDER BY id` guarantees the order of the three rows by ID. Without `ORDER BY`, the DB does not guarantee returning them in INSERT order.
5. `queryForObject(..., Integer.class, 1L)` finds **exactly one row** whose `score` column is SQL `NULL`, so it returns Java `null`. This differs from a query returning 0 rows, where `queryForObject` throws `EmptyResultDataAccessException`.

These files form a Spring Boot application running on JDK 17+ with configured Spring dependencies; **it cannot be compiled with plain JDK `javac` alone** because Spring/H2 are missing from the classpath. Binding `null` in the example uses `JdbcTemplate` and H2; with specific drivers/SQL types, if the DB cannot infer the type from SQL, you may need to specify `java.sql.Types` or use `SqlParameterValue`.

## 9. Reading a Single Column with JdbcTemplate: SQL NULL Still Differs from No Rows

Suppose you query a single column:

```java
Integer score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

For row `id=1`: there is one row, and column `score` is SQL `NULL`, so `score == null`. If querying `id=99` and there are no rows, `queryForObject` **does not return `null` just because the row is missing**; it throws `EmptyResultDataAccessException` per its exact-one-row contract.

Comparison:

| Scenario | Result |
| --- | --- |
| One row, `score IS NULL` | `Integer score = null` |
| One row, `score = 0` | `Integer score = 0` |
| No rows | `EmptyResultDataAccessException` when using `queryForObject` |
| More than one row | `IncorrectResultSizeDataAccessException` |
| `SELECT COUNT(*)` without GROUP BY and no matching rows | One row containing `0` |

For a nullable property, **do not use a Java primitive on the receiving end of a scalar value**:

```java
int score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

Here Java has to *auto-unbox* `Integer` to `int`. If Spring returns `null` for SQL `NULL`, Java throws `NullPointerException`. This is a Java error **after retrieving the result**, different from `rs.getInt` returning 0 on SQL NULL.

Fix:

```java
Integer score = jdbc.queryForObject(
    "SELECT score FROM measurements WHERE id = ?",
    Integer.class, 1L
);
```

Or if the business API truly needs a non-null integer, choose an explicit policy: reject null, apply a defined default, or change the schema to `NOT NULL`.

## 10. Automatic Mapping: BeanPropertyRowMapper and DataClassRowMapper

Not every mapper is written by hand. Spring JDBC has `BeanPropertyRowMapper` for JavaBeans with no-arg constructors/setters and `DataClassRowMapper` for constructor-based types, including Java records.

### BeanPropertyRowMapper + Primitive Property

Example of a bean with a primitive field:

```java
public class PrimitiveScoreBean {
    private int score;

    public PrimitiveScoreBean() {}

    public int getScore() {
        return score;
    }

    public void setScore(int score) {
        this.score = score;
    }
}
```

If the database returns SQL `NULL` for `score`, Spring's `BeanPropertyRowMapper` **by default tries to assign null to the primitive property and can throw `TypeMismatchException`**, rather than always treating null safely as 0—because null cannot be accurately represented in `int`.

Spring allows:

```java
BeanPropertyRowMapper<PrimitiveScoreBean> mapper =
    new BeanPropertyRowMapper<>(PrimitiveScoreBean.class);
mapper.setPrimitivesDefaultedForNullValue(true);
```

This is a **method snippet** importing `org.springframework.jdbc.core.BeanPropertyRowMapper` with the bean class defined. That setting tells the mapper to skip setting `null` onto the primitive, keeping its current value (normally default `0`). However, **it erases the distinction between SQL NULL and 0**; if you later persist that bean back to the database, you risk accidentally writing `0` instead of NULL. Therefore, do not turn this flag on just to “make the error go away” without checking the business contract.

For nullable columns, fix the model toward:

```java
public class NullableScoreBean {
    private Integer score;

    public NullableScoreBean() {}

    public Integer getScore() {
        return score;
    }

    public void setScore(Integer score) {
        this.score = score;
    }
}
```

With `Integer`, `null` is a valid Java value and DB semantics are preserved.

### DataClassRowMapper and Java Records

Java records have constructors assigning all components. When columns are nullable, components must have nullable types to preserve SQL `NULL`:

```java
public record ScoreView(long id, Integer score, Boolean active) {}
```

`DataClassRowMapper` can map the record via its constructor if column names/aliases match and the driver supports suitable conversions. Usage snippet inside a method with `jdbc` configured:

```java
var mapper = new org.springframework.jdbc.core.DataClassRowMapper<>(
    ScoreView.class
);

var rows = jdbc.query(
    "SELECT id, score, active FROM measurements ORDER BY id",
    mapper
);
```

This is an illustrative snippet for Spring JDBC 6.x, **not a complete program**. Using `Integer` and `Boolean` instead of `int`/`boolean` lets the record receive SQL NULL cases; the constructor cannot accept null for corresponding primitives.

With automatic mappers, always verify column names/aliases, data types, driver conversion support, and nullability in integration tests. If mapping requires custom logic or intricate conversions, a custom `RowMapper` can be clearer.

## 11. SQL NULL, Filter Predicates, and Aggregates

### 11.1. SQL NULL Is Not Equal to 0 or FALSE

In SQL, comparing `score = NULL` is wrong for finding null columns because comparisons with `NULL` generally evaluate to logical `UNKNOWN`. Use:

```sql
SELECT id FROM measurements WHERE score IS NULL;
```

To find an actual 0:

```sql
SELECT id FROM measurements WHERE score = 0;
```

On the sample data, `score IS NULL` finds `id=1`; `score = 0` finds `id=2`. They are semantically distinct datasets. Likewise, `active IS NULL` differs from `active = FALSE`.

### 11.2. COUNT(*) Differs from COUNT(column)

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(score) AS scored_rows
FROM measurements;
```

With the three sample rows:

- `COUNT(*) = 3` because it counts all rows.
- `COUNT(score) = 2` because it ignores SQL NULL values in `score`.

If Java turned SQL NULL into 0 during mapping and then computed an average in Java, the result could be skewed because an unscored row was counted as 0. Establish a clear rule: skip nulls, report "insufficient data", or apply an intentional default.

### 11.3. COALESCE Is a Business Decision, Not a Default Mapping Fix

```sql
SELECT id, COALESCE(score, 0) AS score
FROM measurements;
```

`COALESCE(score, 0)` deliberately replaces SQL NULL with 0 in the **query result**. This is a valid policy **only if business rules truly treat a missing score as 0**, such as a statistic with an explicit convention. It prevents readers from distinguishing a real 0 from an original null; do not use it carelessly just to avoid `wasNull()`.

If you need both a defaulted value and the original flag, you can select:

```sql
SELECT id,
       score,
       (score IS NULL) AS score_missing
FROM measurements;
```

On DBMSs supporting boolean expressions in SELECT (such as H2/PostgreSQL), column `score_missing` exposes the state for downstream handling. Consider SQL dialect differences if another DBMS represents booleans differently.

## 12. Outer Joins Can Produce NULL Even When the Source Column Is NOT NULL

Nullability does not come solely from `NULL` in a column definition. Consider `customers` and `orders`:

```sql
SELECT c.id AS customer_id,
       o.id AS order_id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Column `orders.id` may be declared `BIGINT PRIMARY KEY NOT NULL`, yet for customers **with no matching order**, the `LEFT JOIN` result still has `order_id = NULL` in the joined row. Therefore:

```java
long rawOrderId = rs.getLong("order_id");
Long orderId = rs.wasNull() ? null : rawOrderId;
```

is what preserves the "no order" meaning. Using `long orderId = rs.getLong("order_id")` and treating `0` as a real order ID can cause the application to fabricate invalid references.

**Do not look only at the right-hand table's schema to infer projection nullability.** Inspect outer joins, `CASE` expressions, computed expressions, aggregates, and aliases. `ResultSetMetaData.isNullable(...)` can help check, though drivers may report "unknown"; always design by the SQL contract and test it.

## 13. When Should You Use Optional?

`Optional<T>` expresses the presence of a **return value** in a Java API, but you should not automatically wrap every property in a domain record with it.

There are two separate questions:

1. **No row found** when looking up by ID: the repository can return `Optional<Measurement>`.
2. **Row exists but a column is nullable**: the `Measurement` object has an `Integer score` field or a value object representing score state.

Contract example:

```java
public Optional<Measurement> findById(long id) {
    List<Measurement> rows = jdbc.query(
        "SELECT id, score, active, attempts, note " +
        "FROM measurements WHERE id = ?",
        MAPPER,
        id
    );
    return org.springframework.dao.support.DataAccessUtils.optionalResult(rows);
}
```

This is a repository method with `jdbc`, `MAPPER`, and imports for `List`/`Optional`. `DataAccessUtils.optionalResult` is available in Spring Framework 6.1+. Returning `Optional.empty()` means **no row was found**, whereas `Optional.of(measurement)` may contain `measurement.score() == null`. This avoids confusing "missing record" with "missing property value".

If a property needs three or more business states (such as "not measured", "not applicable", "measured"), Java `null` is sometimes not expressive enough; consider an enum or an explicit state result type instead of inventing numeric sentinels.

## 14. Binding Nullable Parameters When WRITING Data

This lesson focuses on **reading `ResultSet`**, yet when writing data back you must preserve the same semantic boundary:

- `PreparedStatement.setInt(index, 0)` writes the number 0, **not SQL NULL**.
- To write SQL NULL, use `setNull(index, java.sql.Types.INTEGER)`.
- In Spring JDBC, for nullable parameters where the driver needs the SQL type, use `SqlParameterValue` or an overload accepting `argTypes`, rather than assuming every driver infers the type of Java `null`.

Plain JDBC example with an already-created statement and column `score INTEGER NULL`:

```java
if (score == null) {
    statement.setNull(1, java.sql.Types.INTEGER);
} else {
    statement.setInt(1, score);
}
```

This is a **snippet inside a method**, given `PreparedStatement statement` and `Integer score`. The goal is to preserve the distinction between "no score" and "score 0" on write, mirroring how `wasNull()` preserves it on read.

`JdbcTemplate.update` with bound arguments can handle many null cases automatically, yet if a driver cannot infer the SQL type, specify the type explicitly instead of turning null into 0 to dodge the error.

## 15. Testing All Three States: NULL / 0 / Regular Value

Test with **at least three rows** like the opening example. Testing only a value like 42 cannot catch a bug that reads SQL NULL as 0. An integration test using the exact DB driver your application runs in production is the strongest proof.

Suppose the Spring Boot/H2 project in Section 8 also adds:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

In a Spring Boot 3.3 project with `@JdbcTest`, you can write a repository test. File **`src/test/java/example/MeasurementRepositoryTest.java`**:

```java
package example;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(MeasurementRepository.class)
class MeasurementRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    MeasurementRepository repository;

    @BeforeEach
    void seed() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id BIGINT PRIMARY KEY,
                score INTEGER NULL,
                active BOOLEAN NULL,
                attempts BIGINT NULL,
                note VARCHAR(80) NULL
            )
            """);
        jdbc.update("DELETE FROM measurements");
        jdbc.update("""
            INSERT INTO measurements
                (id, score, active, attempts, note)
            VALUES
                (1, NULL, NULL, NULL, NULL),
                (2, 0, FALSE, 0, ''),
                (3, 42, TRUE, 123, 'ready')
            """);
    }

    @Test
    void nullAndRealZeroRemainDifferent() {
        List<Measurement> rows = repository.findAll();
        assertEquals(3, rows.size());

        Measurement unknown = rows.get(0);
        Measurement zero = rows.get(1);
        Measurement regular = rows.get(2);

        assertNull(unknown.score());
        assertNull(unknown.active());
        assertNull(unknown.attempts());
        assertNull(unknown.note());

        assertEquals(Integer.valueOf(0), zero.score());
        assertEquals(Boolean.FALSE, zero.active());
        assertEquals(Long.valueOf(0), zero.attempts());
        assertEquals("", zero.note());

        assertEquals(Integer.valueOf(42), regular.score());
        assertEquals(Boolean.TRUE, regular.active());
        assertEquals(Long.valueOf(123), regular.attempts());
        assertEquals("ready", regular.note());
    }

    @Test
    void singleColumnNullableResultIsNotMissingRow() {
        Integer score = jdbc.queryForObject(
            "SELECT score FROM measurements WHERE id = ?",
            Integer.class, 1L
        );
        assertNull(score);
    }
}
```

Run:

```bash
./gradlew test
```

With matching Spring Boot 3.3/JUnit 5/H2 and no schema conflicts, **2 tests** are expected to pass. `@JdbcTest` normally configures an embedded database and rolls back transactions after each test. To conclude that the mapper works on PostgreSQL or a production DBMS, add integration tests with the real JDBC driver/DB or Testcontainers; H2 does not reproduce every conversion and dialect quirk.

Another very important check is **testing failure behavior**: if you replace `nullableInt` with `rs.getInt` and assign to `Integer` via autoboxing, `assertNull(unknown.score())` will fail because it receives `0`. That way the test verifies not only normal data, but also protects null semantics.

### If Using a Mock ResultSet

In unit tests for helpers, the call sequence must be:

```text
getInt("score") -> wasNull()
getBoolean("active") -> wasNull()
getLong("attempts") -> wasNull()
```

Do not stub `wasNull()` to return a single fixed value across all columns and conclude the mapper works. Because `wasNull()` depends on **the immediately preceding getter**, a mock must simulate the corresponding state—or better yet, use an integration test with a real driver to catch out-of-order calls.

## 16. Common Mistakes

| Mistake | Consequence and fix |
| --- | --- |
| Mapping `NULL` with `rs.getInt` and assigning directly to `Integer` | Autoboxing turns `0` into `Integer.valueOf(0)`, losing NULL; use `wasNull` or typed `getObject`. |
| Calling `wasNull` after reading another column | State reflects the most recently read column; call immediately after the getter being checked. |
| Assuming `getBoolean` returning false means DB stored FALSE | SQL NULL also returns false; check `wasNull`. |
| Turning SQL NULL into 0/false for all columns | Can corrupt status classification, reports, and updates; default only when business rules explicitly specify it. |
| Using primitive fields for nullable columns | Cannot hold null; choose wrappers or a domain design with explicit states. |
| Unboxing nullable `Integer` to `int` without checking | Can throw `NullPointerException`; handle null before unboxing. |
| Thinking SQL NULL is equivalent to no row | A row with a NULL column is still a row; distinguish from `EmptyResultDataAccessException`. |
| Enabling `primitivesDefaultedForNullValue(true)` to silence errors without understanding it | Null values stay at primitive defaults and may be written back to DB erroneously. |
| Using `score = NULL` to find missing values | SQL NULL comparisons use `IS NULL`, not `= NULL`. |
| Treating `ResultSetMetaData.isNullable` as an absolute guarantee for all projections | Outer joins and expressions can produce NULL; drivers can report unknown. |
| Assuming typed `getObject(label, Integer.class)` is supported by all drivers for all types | Conversion depends on driver/DB; test or fall back to getter + `wasNull`. |
| Detecting null via `score == 0` or `active == false` | Conflates real values with absence; read null state explicitly. |
| Testing only non-zero values | Misses null-to-zero bugs; test NULL, 0/false, and normal values. |
| Using `SUM`/`AVG` after coercing null to 0 without checking business rules | Can skew denominators/averages; preserve SQL NULL or state calculation rules explicitly. |

## 17. Self-Check

**Question 1.** A SQL row has `score = NULL`. After `int score = rs.getInt("score")`, what does `score` usually equal?

**Answer:** `0` per the JDBC contract, though that is merely the primitive getter's return value. Calling `rs.wasNull()` **immediately afterward** returns `true` and tells you the SQL value was actually NULL.

**Question 2.** A SQL row has `score = 0`. Why can you not use `score == 0` to conclude data is missing?

**Answer:** Because `0` is a real value and `getInt` also returns 0 for SQL NULL. Only `wasNull()` or a nullable object getter distinguishes them.

**Question 3.** If you call `getInt("score")`, then `getString("note")`, and finally `wasNull()`, which column does `wasNull()` check?

**Answer:** `note`, because that was the most recent getter.

**Question 4.** For column `active BOOLEAN NULL`, should you use Java `boolean` or `Boolean` if an undetermined state is meaningful?

**Answer:** `Boolean`. It represents true, false, and null. If using `getBoolean`, you must call `wasNull()` to know when to map to Java null.

**Question 5.** `JdbcTemplate.queryForObject(sql, Integer.class)` gets exactly one row whose SQL column is NULL. What is the result?

**Answer:** It can be Java `null`. If the query had no rows, it would throw `EmptyResultDataAccessException`. Distinguish row count from column value.

**Question 6.** Why does `Integer x = rs.getInt("score")` still have a bug?

**Answer:** Because Java autoboxes the `int` to `Integer` **after the getter has already turned SQL NULL into 0**. The receiving wrapper cannot recover lost information.

**Question 7.** Can a `LEFT JOIN` produce `NULL` in a `NOT NULL` primary-key column of the right-hand table?

**Answer:** Yes. When no matching row exists, the joined result has NULL in the right-hand columns. Projection `order_id` must be mapped as nullable.

**Question 8.** When using `BeanPropertyRowMapper` and a SQL NULL column maps to an `int` property, how should you fix it?

**Answer:** Prefer changing the property to `Integer` if null is meaningful. The `primitivesDefaultedForNullValue` flag is only valid when losing the distinction between SQL NULL and the primitive default value is acceptable.

## References

- [Java SE 21 — `ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html): contract for `getInt`, `getBoolean`, `getObject`, and `wasNull()`.
- [Spring Framework 6.2 — `RowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/RowMapper.html): row-by-row mapping principles, `SQLException`, and `ResultSet` cursor position.
- [Spring Framework — `JdbcTemplate`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): query mechanics, callbacks, and JDBC resources.
- [Spring Framework — `BeanPropertyRowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html): primitive/nullable types, `primitivesDefaultedForNullValue`.
- [Spring Framework — `DataClassRowMapper`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html): constructor/Java record mapping.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `RowMapper` callbacks, using `JdbcTemplate`, and declaring queries.

**Remember:** SQL `NULL` differs from `0`, `false`, and an empty string. When a column can be NULL, **choose a Java type that preserves null** and **call `wasNull()` immediately after primitive getters** when using `getInt`/`getLong`/`getBoolean`/etc. Test missing rows, NULL values, and real 0 values in your tests so you never corrupt information in the data access layer.