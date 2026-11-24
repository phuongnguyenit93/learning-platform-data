# Batching from `Object[]` Lists or `SqlParameterSource` in Spring JDBC

## 1. The Problem and Core Idea

When you need to insert, update, or delete many records with the **same SQL statement** but different parameter sets, calling `update(...)` row by row typically causes many statement dispatches to the JDBC driver. Spring JDBC provides `batchUpdate(...)` to pass an entire set of parameters, reducing application-layer iteration overhead and potentially reducing round trips to the database, depending on the driver and how it implements batching.

For example, giving raises to three employees is not three different SQL templates: the statement remains `UPDATE employee SET salary = ? WHERE id = ?`, while only the `salary` and `id` values change. Each element in the batch corresponds to **one SQL execution for one parameter set**.

Conceptual flow: create a `PreparedStatement` for the SQL → bind parameters for each row → add the row to the batch → JDBC executes the batch → return the affected row counts per element. Spring manages the statement, resources, and translating `SQLException` into `DataAccessException`. Whether the driver uses true JDBC batching or executes multiple individual updates depends on the driver's capabilities.

**Two ways to represent parameters to know:**
- **Positional:** `JdbcTemplate.batchUpdate(sql, List<Object[]>)`. One `Object[]` holds values matching `?` placeholders from left to right.
- **Named:** `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])`. Each `SqlParameterSource` supplies values by name (`:id`, `:salary`, ...); the order in which values are placed in the object does not determine their position in the SQL.

Both are **DML batches** (`INSERT`, `UPDATE`, `DELETE`), are not equivalent to a single `INSERT ... VALUES (...), (...)` statement, do not automatically create a transaction, and do not automatically guarantee that the entire batch succeeds or rolls back.

## 2. APIs and How to Choose

| Scenario | API | Parameter Shape | Result |
|---|---|---|---|
| SQL uses `?`, data is an array per column | `JdbcTemplate.batchUpdate(String, List<Object[]>)` | `List<Object[]>`: each array is one row | `int[]` |
| Explicit SQL types needed, especially with `null` | `JdbcTemplate.batchUpdate(String, List<Object[]>, int[] argTypes)` | Adds a `java.sql.Types` array matching `?` order | `int[]` |
| SQL uses named parameters, data is a map/bean | `NamedParameterJdbcTemplate.batchUpdate(String, SqlParameterSource[])` | One `SqlParameterSource` per row | `int[]` |
| Have a list of beans or maps to convert quickly | `SqlParameterSourceUtils.createBatch(Collection<?>)` | Returns `SqlParameterSource[]` for the call above | `SqlParameterSource[]` |

Choose `Object[]` when column order is short and clear and input data is already tuple-shaped. Choose `SqlParameterSource` when there are many fields, when you want to reduce the risk of swapping positions by mistake, or when working directly with JavaBeans/maps. Both use bound parameters (bind variables), avoiding concatenating user values directly into the SQL string.

**Mandatory rule:** every element in the same batch uses the same SQL structure; each `Object[]` must have the exact number of values matching the `?` placeholders, and every `SqlParameterSource` must provide all parameter names used by the SQL statement.

## 3. Standalone Runnable Example with Java 17 + Maven + H2

The following example intentionally demonstrates **all three approaches**: `List<Object[]>` to insert employees; `MapSqlParameterSource[]` to update two people; and `SqlParameterSourceUtils.createBatch(List<JavaBean>)` to update the remaining one. This is a complete runnable Java program with no need to boot Spring Boot.

Create the file structure:

~~~text
spring-jdbc-batch-demo/
├── pom.xml
└── src/main/java/demo/BatchDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-jdbc-batch-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/BatchDemo.java`**

~~~java
package demo;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;

public class BatchDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE employee (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    salary INTEGER NOT NULL,
                    note VARCHAR(100)
                )
                """);

        // 1) One Object[] matching the ? placeholders in exact SQL order.
        List<Object[]> inserts = List.of(
                new Object[] {1L, "An", 100, null},
                new Object[] {2L, "Binh", 200, "thu viec"},
                new Object[] {3L, "Chi", 300, null}
        );

        int[] inserted = jdbc.batchUpdate(
                "INSERT INTO employee (id, name, salary, note) " +
                "VALUES (?, ?, ?, ?)",
                inserts,
                new int[] {
                        Types.BIGINT, Types.VARCHAR,
                        Types.INTEGER, Types.VARCHAR
                }
        );
        System.out.println("INSERT=" + Arrays.toString(inserted));

        // 2) Each MapSqlParameterSource has keys matching :id and :salary.
        SqlParameterSource[] changes = {
                new MapSqlParameterSource()
                        .addValue("id", 1L, Types.BIGINT)
                        .addValue("salary", 120, Types.INTEGER),
                new MapSqlParameterSource()
                        .addValue("id", 3L, Types.BIGINT)
                        .addValue("salary", 330, Types.INTEGER)
        };

        int[] updatedByMap = named.batchUpdate(
                "UPDATE employee SET salary = :salary WHERE id = :id",
                changes
        );
        System.out.println("UPDATE_MAP=" + Arrays.toString(updatedByMap));

        // 3) Convert a JavaBean collection to SqlParameterSource[].
        List<SalaryChange> beanChanges = List.of(
                new SalaryChange(2L, 220)
        );
        int[] updatedByBean = named.batchUpdate(
                "UPDATE employee SET salary = :salary WHERE id = :id",
                SqlParameterSourceUtils.createBatch(beanChanges)
        );
        System.out.println("UPDATE_BEAN=" +
                Arrays.toString(updatedByBean));

        List<Integer> finalSalaries = jdbc.queryForList(
                "SELECT salary FROM employee ORDER BY id",
                Integer.class
        );
        System.out.println("FINAL=" + finalSalaries);
    }

    public static final class SalaryChange {
        private final long id;
        private final int salary;

        public SalaryChange(long id, int salary) {
            this.id = id;
            this.salary = salary;
        }

        public long getId() {
            return id;
        }

        public int getSalary() {
            return salary;
        }
    }
}
~~~

In the directory containing `pom.xml`, you need JDK 17+ and Maven; run:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.BatchDemo"
~~~

**Program output on H2:**

~~~text
INSERT=[1, 1, 1]
UPDATE_MAP=[1, 1]
UPDATE_BEAN=[1]
FINAL=[120, 220, 330]
~~~

The `INSERT` call creates three rows, the map-based update changes salaries for ids 1 and 3, and the JavaBean-based update changes the salary for id 2. The values of 1 are the row counts affected by each DML statement in this H2 example; on other drivers/DBs, count codes may be special JDBC values (Section 6).

## 4. Understanding `List<Object[]>` Accurately

For the SQL:

~~~sql
INSERT INTO employee (id, name, salary, note) VALUES (?, ?, ?, ?)
~~~

The parameter mapping of element `new Object[] {1L, "An", 100, null}` is:

| `?` Position | Column | Value | SQL type in example |
|---|---|---|---|
| 1 | `id` | `1L` | `Types.BIGINT` |
| 2 | `name` | `"An"` | `Types.VARCHAR` |
| 3 | `salary` | `100` | `Types.INTEGER` |
| 4 | `note` | `null` | `Types.VARCHAR` |

- **Exact count and order:** if you swap `id` and `salary`, data may become corrupted or be rejected by the DB; Java variable names do not help JDBC infer positions automatically.
- **`argTypes` is the type array for *the parameter positions*, shared across all rows**, not one type array per record. Use `java.sql.Types` constants instead of ad-hoc magic numbers.
- If all values/drivers infer types reliably, you can use the two-argument overload: `jdbc.batchUpdate(sql, inserts)`. With nullable columns or drivers that struggle with type inference, the three-argument overload makes SQL types explicit.
- For each SQL statement, keep the expression order and array list synchronized. Changing column structure while forgetting to update the arrays is a subtle bug when multiple columns share the same type.

The example above uses `List.of(...)` containing **non-null arrays**; an element *inside* an array can be `null`. Do not confuse this with `List.of(null)`, which rejects null elements.

## 5. Understanding `SqlParameterSource[]` and Creating It Quickly

`NamedParameterJdbcTemplate` handles SQL using names, for instance:

~~~sql
UPDATE employee SET salary = :salary WHERE id = :id
~~~

In each element of `SqlParameterSource[]`, the two parameters `salary` and `id` are looked up by **name**. Calling `addValue("id", ...)` before `addValue("salary", ...)` still works correctly, even though `:salary` precedes `:id` in the SQL.

**`MapSqlParameterSource`:** suitable when data is assembled dynamically, when explicit SQL types are needed, or when passing typed nulls:

~~~java
SqlParameterSource row = new MapSqlParameterSource()
        .addValue("id", 10L, Types.BIGINT)
        .addValue("note", null, Types.VARCHAR);

// Use row inside a SqlParameterSource[] matching the SQL
// UPDATE employee SET note = :note WHERE id = :id
~~~

The snippet above only illustrates parameter binding, not a standalone runnable program; id 10 has not been created in the H2 example.

**`BeanPropertySqlParameterSource`:** reads parameters from object properties, typically via getters `getId()`, `getSalary()`. `SqlParameterSourceUtils.createBatch(beanChanges)` creates one parameter source per bean. Property names must match parameter names in SQL; having `getEmployeeId()` when SQL uses `:id` will not match automatically.

**From existing maps or beans:** the helper `SqlParameterSourceUtils.createBatch(...)` accepts a collection/array containing String-keyed maps or beans. Example illustrating a parameter batch for salary-update SQL:

~~~java
List<java.util.Map<String, Object>> rows = List.of(
        java.util.Map.of("id", 1L, "salary", 130),
        java.util.Map.of("id", 3L, "salary", 340)
);
SqlParameterSource[] batch =
        SqlParameterSourceUtils.createBatch(rows);
int[] counts = named.batchUpdate(
        "UPDATE employee SET salary = :salary WHERE id = :id",
        batch
);
~~~

This snippet assumes `named` and rows with ids 1 and 3 already exist; it is not part of the main `BatchDemo` program. `Map.of(...)` does not support null keys or null values; when null is needed, use `MapSqlParameterSource.addValue(..., Types.XXX)` or a null-supporting map.

**Related alternatives:** `NamedParameterJdbcTemplate` also has an overload accepting `Map<String, ?>[]`. However, using `SqlParameterSource[]` is especially convenient when carrying SQL type metadata or converting from a list of beans. Neither of these arrays is `Object[][]`: `Object[]` maps by *position*, whereas `SqlParameterSource` maps by *name*.

## 6. Interpreting `int[]`, Errors, and Transactions

`batchUpdate(...)` returns `int[]`: index `i` corresponds to the `i`-th submitted element. Possible values are:

| Single-element result | Meaning |
|---|---|
| `0` | The statement affected no rows (e.g., `WHERE id` did not match), not necessarily an exception |
| `1`, `2`, ... | Driver reports the number of rows affected by the corresponding statement |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Driver reports successful execution without providing a row count |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver reports the element failed if the driver returns this status; in many cases errors cause the whole call to throw an exception |

Because negative codes exist, **do not assume `Arrays.stream(counts).sum()` gives the actual total rows**, and do not assume every element must return 1: an UPDATE statement can match 0 rows. If the API throws `DataAccessException`, you generally do not receive the result array on the success path; detailed error information depends on `SQLException`/`BatchUpdateException` and the driver.

**Batching does not mean transactions.** If one element violates a unique key or another constraint, earlier elements may already have been executed by the driver. For business logic requiring integrity, call the DAO inside a Spring transaction (e.g., a `@Transactional` service method with the transaction manager for the right `DataSource`). By default, unchecked exceptions (such as `DataAccessException`) escaping a transactional method mark it for rollback; if you catch and swallow exceptions yourself, you must handle rollback explicitly. Outside a transaction, autocommit mode and how the driver handles errors determine what gets saved. Do not treat `batchUpdate` as an all-or-nothing guarantee.

**When generated keys are needed:** do not infer auto-increment ids from `int[]`. Spring has some batch overloads using `KeyHolder`, but the ability to retrieve all keys and their ordering depends on the API/driver/DB; choose and test specifically on your deployment database.

## 7. Performance and Production Operations

- **Keep batches moderately sized:** with tens of thousands of records, there is no need to cram everything into one huge list; test sizes like a few hundred to around a thousand rows, measure on the real DB/driver, and tune according to record size, memory limits, logs, and lock duration. This is a starting point for benchmarking, not a fixed rule.
- **Preserve transactions when chunking:** splitting into multiple `batchUpdate` calls to save memory does not automatically create commit boundaries. If a business operation must be atomic, wrap the chunks that must roll back together in one transaction; if intentionally committing chunk by chunk, clearly define retry handling and how processed items are identified.
- **Note on another overload:** `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` supports chunking by size and returns `int[][]`. This is an advanced option when data is large or when binding fields manually; it differs from the `List<Object[]>` overload focused on in this lesson.
- **Driver/DB determines the gains:** some drivers optimize/rewrite batches, while others reduce fewer round trips than expected. Measure throughput, latency, transaction duration, locks, and query plans; do not assume a batch is always faster in every situation.
- **Data and security:** parameter binding protects *values*, and does not automatically protect dynamically concatenated table/column names. Restrict and validate identifiers via allowlists, validate data before writing to the DB, and avoid logging full sensitive data when a batch fails.
- **Safe retries:** a batch `INSERT` without idempotent design can produce duplicate keys or duplicate data when retried after a timeout. Design unique keys, DB-appropriate upserts, or mechanisms marking processed requests before enabling retries.

## 8. Common Mistakes and How to Check

| Symptom | Common Cause | How to Fix |
|---|---|---|
| SQL reports missing/wrong parameters | `Object[]` missing elements, swapped order, or map/bean missing `:param` name | Count `?`; check array order; match parameter names with keys/getters |
| Null insert fails with type error | Unable to infer SQL type or column disallows null | Use `argTypes`, `addValue(name, null, Types.XXX)`, and check schema |
| Results have many `0`s | `UPDATE/DELETE WHERE` did not match keys | Verify id data, WHERE condition, and whether 0 rows is allowed by business rules |
| Duplicate key mid-batch | Duplicate primary/unique key, retried or non-idempotent data | Handle duplicates, transactions, and a clear retry/upsert strategy |
| Batch is slow or RAM-heavy | Dataset too large, driver does not optimize, DB lock/index contention | Split into chunks, benchmark per driver, review indexes and transaction duration |
| Earlier rows changed despite later failure | No enclosing transaction or exception caught without rollback | Move work into a Spring transaction and verify rollback on the real DB |
| JavaBean fails to bind names | Getter/field does not match `:param` name | Check JavaBean getters, or use `MapSqlParameterSource` to be explicit |

**Pre-deployment checklist:**
1. SQL has a single statement template; parameter order/names are valid for every element.
2. Null data, SQL types, and constraints have been verified.
3. Business rules define acceptable affected row counts, including `SUCCESS_NO_INFO`.
4. Transaction scope, partial error handling, and retry rules are chosen.
5. Batch size is measured on the real DB/driver and tested with mid-batch error data.

## 9. Self-Practice

1. Change one employee in the example to a non-existent id during update; predict that the `int[]` element will be 0 and verify the result.
2. Add an `Object[]` with a duplicate primary key `id` to observe the exception; compare database state with and without a transaction.
3. Convert the `INSERT` section from `Object[]` to `SqlParameterSource[]` with names `:id`, `:name`, `:salary`, `:note`. Ensure `null` in `note` has the right SQL type.
4. Generate a few thousand test employees, measure duration across multiple batch sizes, and compare with individual `update(...)` calls under the same conditions.

## References

- Spring Framework Reference — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework Javadoc — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework Javadoc — `NamedParameterJdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework Javadoc — `SqlParameterSourceUtils`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSourceUtils.html
