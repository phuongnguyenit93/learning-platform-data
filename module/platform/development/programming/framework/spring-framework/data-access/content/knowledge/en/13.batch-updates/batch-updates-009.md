# Declaring SQL Types for `NULL` to Avoid Errors and Metadata Overhead in Batch Updates

## 1. Where Does the Problem Lie?

In Spring JDBC, `JdbcTemplate.batchUpdate(...)` and `NamedParameterJdbcTemplate.batchUpdate(...)` send multiple parameter sets for the same SQL statement, typically through a `PreparedStatement`. For non-`null` values, Spring/the driver can usually infer the JDBC type from the Java object. For `null`, there is no Java value class from which to infer the corresponding SQL type.

For example, a table with two nullable (`NULL`-allowed) columns:

```sql
CREATE TABLE customer_record (
    id         BIGINT PRIMARY KEY,
    note       VARCHAR(200) NULL,
    expires_at TIMESTAMP NULL
);
```

A batch runs this statement repeatedly:

```sql
UPDATE customer_record
SET note = ?, expires_at = ?
WHERE id = ?;
```

If a row has `note = null` and `expires_at = null`, passing only `new Object[] {null, null, 101L}` can leave the parameter-binding layer unsure that parameter 1 is `VARCHAR` and parameter 2 is `TIMESTAMP`. On some code paths, Spring looks up the type via `PreparedStatement.getParameterMetaData().getParameterType(index)`. Depending on the driver, that operation can cost an extra round trip to the DBMS, may not be fully supported, or may return an unsuitable type. Repeating it across a large batch can noticeably increase execution time.

**Preferred approach:** declare each parameter's exact JDBC type from the SQL schema using `java.sql.Types` constants so that when `null` occurs, Spring/the driver can bind a typed `NULL`. Setting a global flag to ignore metadata should not be treated as the primary solution.

## 2. Matching the Right Type to the Target Column

| Common SQL Column Type | Common JDBC Type | When Binding `NULL` |
| --- | --- | --- |
| `VARCHAR`, string | `Types.VARCHAR` | `ps.setNull(i, Types.VARCHAR)` |
| `INTEGER` | `Types.INTEGER` | `ps.setNull(i, Types.INTEGER)` |
| `BIGINT` | `Types.BIGINT` | `ps.setNull(i, Types.BIGINT)` |
| `DECIMAL(p,s)`, `NUMERIC` | `Types.DECIMAL` or `Types.NUMERIC` | Per schema; scale may be needed for non-null numbers |
| `DATE` | `Types.DATE` | `ps.setNull(i, Types.DATE)` |
| `TIMESTAMP` without time zone | `Types.TIMESTAMP` | `ps.setNull(i, Types.TIMESTAMP)` |
| `BOOLEAN` | `Types.BOOLEAN` | `ps.setNull(i, Types.BOOLEAN)` |
| Binary data `VARBINARY` | `Types.VARBINARY` | `ps.setNull(i, Types.VARBINARY)` |

This is a reference guide, not an exact mapping for every database. Types such as `UUID`, `JSON/JSONB`, `ARRAY`, `TIMESTAMP WITH TIME ZONE`, and user-defined types require checking driver/DBMS documentation; `Types.OTHER` or a vendor-specific SQL type name sometimes needs additional configuration. **`Types.NULL` is not a substitute for the column's actual type.**

For the example SQL, the order of the three placeholders is `VARCHAR, TIMESTAMP, BIGINT`. Indices in `int[] argTypes` start at 0 as a Java array; parameter indices in `PreparedStatement` start at **1**.

## 3. Java 17+ Code in a Spring JDBC Project

The code below is a **complete Java class** to place into an application with the `spring-jdbc` dependency and a configured `DataSource`. It has no `main` because it needs a connection to the `customer_record` table. Save it in `CustomerRepository.java`; each method illustrates one way to provide types—there is no need to run all four approaches for the same dataset.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

public final class CustomerRepository {
    private static final String POSITIONAL_SQL =
            "UPDATE customer_record SET note = ?, expires_at = ? WHERE id = ?";
    private static final String NAMED_SQL =
            "UPDATE customer_record SET note = :note, expires_at = :expiresAt WHERE id = :id";

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerRepository(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.namedJdbc = new NamedParameterJdbcTemplate(dataSource);
    }

    public record Change(long id, String note, LocalDateTime expiresAt) {}

    private static Timestamp timestampOrNull(LocalDateTime value) {
        return value == null ? null : Timestamp.valueOf(value);
    }

    // Approach 1: one shared type array for all rows (suits fixed SQL).
    public int[] updateWithArgTypes(List<Change> changes) {
        List<Object[]> rows = changes.stream()
                .map(c -> new Object[] {
                        c.note(), timestampOrNull(c.expiresAt()), c.id()
                })
                .toList();

        int[] sqlTypes = {Types.VARCHAR, Types.TIMESTAMP, Types.BIGINT};
        return jdbc.batchUpdate(POSITIONAL_SQL, rows, sqlTypes);
    }

    // Approach 2: explicitly call setNull(index, sqlType) for each nullable column.
    public int[] updateWithSetter(List<Change> changes) {
        return jdbc.batchUpdate(POSITIONAL_SQL, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int row) throws SQLException {
                Change c = changes.get(row);

                if (c.note() == null) {
                    ps.setNull(1, Types.VARCHAR);
                } else {
                    ps.setString(1, c.note());
                }

                if (c.expiresAt() == null) {
                    ps.setNull(2, Types.TIMESTAMP);
                } else {
                    ps.setTimestamp(2, Timestamp.valueOf(c.expiresAt()));
                }

                ps.setLong(3, c.id());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        });
    }

    // Approach 3: named parameters, declaring the type directly for each name.
    public int[] updateWithNamedParameters(List<Change> changes) {
        SqlParameterSource[] batch = changes.stream()
                .map(c -> new MapSqlParameterSource()
                        .addValue("note", c.note(), Types.VARCHAR)
                        .addValue("expiresAt", timestampOrNull(c.expiresAt()),
                                Types.TIMESTAMP)
                        .addValue("id", c.id(), Types.BIGINT))
                .toArray(SqlParameterSource[]::new);

        return namedJdbc.batchUpdate(NAMED_SQL, batch);
    }

    // Approach 4: wrap only specific values that need an explicit type.
    public int[] clearNullableFieldsWithSqlParameterValue(long id) {
        List<Object[]> rows = List.<Object[]>of(new Object[] {
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(Types.TIMESTAMP, null),
                id
        });
        return jdbc.batchUpdate(POSITIONAL_SQL, rows);
    }
}
```

**Illustrative invocation inside a service with `CustomerRepository repository`:**

```java
List<CustomerRepository.Change> changes = List.of(
        new CustomerRepository.Change(101L, null, null),
        new CustomerRepository.Change(
                102L, "In progress", LocalDateTime.of(2027, 1, 15, 9, 30))
);
int[] affected = repository.updateWithArgTypes(changes);
```

This invocation is a **method fragment**, not a standalone program; it assumes rows with `id=101` and `id=102` already exist. The `affected` result depends on data and driver; there is no fixed stdout. For row 101, both nullable columns are set to SQL `NULL`; for row 102, they receive typed values. `LocalDateTime` in the example pairs with a `TIMESTAMP` column **without time zone**; if your schema uses a time-zone-aware type, choose matching Java/JDBC types rather than copying mechanically.

### When to Choose Which Approach?

| API | How `NULL` Types Are Supplied | Best Suited For |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(sql, List<Object[]>, int[])` | `argTypes` mapped by SQL position, shared across the batch | Fixed SQL, many rows, wanting concise code |
| `JdbcTemplate.batchUpdate(sql, BatchPreparedStatementSetter)` | `ps.setNull(index, Types.X)` | Needing control over how each parameter is converted |
| `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` | `MapSqlParameterSource.addValue(name, value, sqlType)` or `registerSqlType` | Long SQL, named parameters, easy to avoid order mismatches |
| Object arrays with `SqlParameterValue` | `new SqlParameterValue(Types.X, null)` | Only a few values need explicit type specification |
| `BeanPropertySqlParameterSource` | Can infer SQL type from the declared Java property type even when value is null | DTOs/beans with clearly typed properties |

With `SqlParameterSourceUtils.createBatch(...)` over `Map`s containing `null` values, do not assume SQL types are always known: inspect the mapping path and driver, or build `MapSqlParameterSource` instances to register types. With `BeanPropertySqlParameterSource`, inference depends on the Java type of the getter/property; DBMS-specific types may still require explicit declaration.

## 4. Why Can Metadata Cause Slowdowns, and What Changed Across Versions?

General execution path for an untyped `null`:

1. Spring needs to bind a `?` parameter for a `PreparedStatement` but only sees a `null` value.
2. On some versions/drivers/code paths, Spring tries `getParameterMetaData().getParameterType(position)` to determine the type.
3. The JDBC driver may query the DBMS for metadata, perform extra processing, or fail to supply a useful type.
4. Repeating this lookup in a high-row-count batch can erase part of the round-trip savings of batching.

However, **do not claim that every batch with `null` queries metadata**. Starting in **Spring Framework 6.1.2**, the default code path avoids calling `getParameterType` on PostgreSQL and Microsoft SQL Server drivers recognized by Spring, because the cost was often significant. On other drivers and other versions, behavior can differ; measure in practice. Skipping metadata probing can also expose `NULL`-binding errors on special types (such as `byte[]`/binary columns) if no type is supplied.

Spring provides the flag `spring.jdbc.getParameterType.ignore=true` to tell `StatementCreatorUtils` to skip metadata probing. Example passed via JVM:

```bash
java -Dspring.jdbc.getParameterType.ignore=true -jar app.jar
```

This is a **Spring Framework system property**, which can be loaded via the `SpringProperties` mechanism; do not assume every key in Spring Boot's `application.properties` automatically controls this flag. Only consider changing it after confirming the cause via profiling/logs/benchmarks on the active driver. If a special `NULL` type fails to bind properly, you may need to declare the type directly or re-check the flag; in environments where metadata probing must be restored, set `spring.jdbc.getParameterType.ignore=false` and test.

## 5. Common Mistakes and How to Test

- **Confusing Java `null` with SQL `NULL`:** `"null"` (a four-character string) and `""` (an empty string) are not equivalent to SQL `NULL`.
- **Wrong type order:** `argTypes` must contain exactly one type per `?` placeholder in order of appearance; putting `Types.TIMESTAMP` on a `VARCHAR` column parameter can cause errors.
- **Calling `ps.setObject(index, null)` and hoping the driver figures it out:** with some drivers/SQL types, this causes errors or triggers type probing; prefer `ps.setNull(index, Types.X)`.
- **Using `Types.NULL`/`Types.OTHER` for every column:** generic values are not guaranteed to match the actual column type; for JSON, UUID, array, and binary columns, read the driver documentation.
- **Misunderstanding update semantics:** `SET note = ?` with an SQL `NULL` parameter **clears the existing content** of that column. If `null` in a DTO means "do not update," you need a different update/SQL policy; merely declaring types does not solve that semantic requirement.
- **Misreading returned counts:** `int[]` stores per-entry results, but JDBC includes `Statement.SUCCESS_NO_INFO (-2)` and `Statement.EXECUTE_FAILED (-3)`. An error can make Spring throw `DataAccessException`; do not assume every element is always 0 or 1.
- **Treating batching as automatic atomic transactions:** batching does not replace transactions. If all-or-nothing is required, invoke inside an appropriate Spring transaction (such as `@Transactional` on a service with a valid transaction manager) and test rollback on the real DBMS.
- **Changing global flags before fixing mappings:** the durable fix for nullable columns is usually passing explicit SQL types; global settings can affect other JDBC operations.

### Recommended Verification Workflow

1. Create the table with the exact schema on the real database/driver; insert two test rows with keys `101`, `102`.
2. Execute each approach independently using datasets with `null`, non-null values, consecutive `null`s, and small/large batches.
3. Read the columns back via `SELECT`: rows meant to be cleared must truly contain SQL `NULL`, not the string `"null"`; non-null rows must preserve types/values.
4. Inspect `int[]`, driver errors, and rollbacks; never hard-code `-2` as failure.
5. For performance investigations, measure with the **same row count, batch size, connection pool, schema, driver, and transaction configuration** before and after declaring `Types.X`; monitor metadata lookups/round trips if the driver exposes them. If the driver does not truly batch, check batch support/fallbacks instead of blaming all latency on `null`.
6. If processing many rows requires chunking, Spring also offers `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)`, returning `int[][]`; inside that setter, still apply `setNull(index, Types.X)` as in the example above.

## 6. Takeaways for Implementation

**Rule of thumb:** determine types from the **SQL placeholder schema**, pick a suitable way to supply types (`argTypes`, `setNull`, `MapSqlParameterSource`, or `SqlParameterValue`), test on the real driver, and benchmark. This ensures `NULL` is bound with the right type and reduces reliance on costly `ParameterMetaData` queries when the code path uses metadata.

### Official Documentation

- Spring Framework – [JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): batch overloads, `NULL` types, metadata, and driver notes.
- Spring Framework – [Providing SQL Type Information for Parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `Types`, `SqlParameterValue`, `SqlParameterSource`.
- Spring Framework – [JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `batchUpdate` with `List<Object[]>` and `argTypes`.
