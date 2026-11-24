# RowMapper Does Not Call ResultSet.next() — Cursor Management Rules in JDBC Mapping

## 1. The Most Important Rule

In Spring JDBC, `org.springframework.jdbc.core.RowMapper<T>` is a callback responsible for **mapping the single current row** of a `ResultSet` into a Java object. **Do not call `rs.next()` inside `mapRow(ResultSet rs, int rowNum)`.** `JdbcTemplate` (via the corresponding result-set iterator) has already called `ResultSet.next()` and positioned the cursor on the row to be read **before** invoking the mapper. **Calling `next()` again inside the mapper moves the cursor past the current row, causing skipped rows, incorrect mapping, or a `SQLException`.**

A proper `RowMapper` only needs to read the columns of the row it is currently positioned on, construct the object, and return it. Most cases can be expressed as a two-parameter lambda:

```java
RowMapper<Student> mapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

This is code **in a project using Spring JDBC**, with the `Student` record defined in the example section. There is no `rs.next()` because the mapper is not responsible for advancing the cursor.

Lesson objectives:
1. Accurately explain who controls `ResultSet.next()` when using `JdbcTemplate.query()`.
2. Distinguish a **single-row** mapper from a **full-result-set** extractor.
3. Recognize the bug of calling `rs.next()` in the wrong place and understand why it often causes **silent data loss**.
4. Correctly use `rowNum`, JDBC getters, nullability, and the JDBC resource lifecycle.
5. Run the Spring Boot/Java 17+ example yourself and test the mapping contract across 0-, 1-, and multi-row scenarios.

Context: Spring Framework 6.x, Spring Boot 3.x, and blocking JDBC. This principle is also documented in the official `RowMapper` Javadoc.

## 2. ResultSet Is a Cursor, Not an In-Memory Java List

A typical JDBC `ResultSet` represents SQL rows and a **cursor** indicating which row is currently being read. In plain JDBC, the cursor initially starts **before the first row**; the JDBC author must call `rs.next()` to advance to the first row. Each successful `next()` call advances the cursor by one row and returns `true`; when there are no more rows, it returns `false`.

### Example of SQL Returning Four Rows

```text
SELECT id, name FROM students ORDER BY id

Cursor positions:
[before first] → [1: An] → [2: Binh] → [3: Chi] → [4: Dung] → [after last]
        rs.next()    rs.next()   rs.next()   rs.next()   rs.next()
```

With plain JDBC:

```java
// Plain JDBC code inside a method with Connection connection.
// Self-created resources must be closed.
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id, name FROM students ORDER BY id");
     ResultSet rs = statement.executeQuery()) {

    while (rs.next()) {   // CORRECT in plain JDBC
        System.out.println(rs.getString("name"));
    }
}
```

In plain JDBC, the `while` loop owns the cursor-advancing logic; therefore it **must** call `next()`. Omitting this call would let getters read when the cursor is not positioned on a valid row and throw a `SQLException`.

**Fundamental difference:** in `JdbcTemplate.query(sql, rowMapper)`, *Spring already executes the equivalent loop*, so `RowMapper` must not repeat the cursor advancement.

## 3. How Does JdbcTemplate Iterate Over a ResultSet?

For an overload of `JdbcTemplate.query(sql, RowMapper<T>)`, the logical flow resembles the following conceptual snippet:

```java
// PSEUDOCODE: to understand the mechanism, not verbatim Spring source code.
List<T> result = new ArrayList<>();
int rowNum = 0;

while (rs.next()) {
    T item = rowMapper.mapRow(rs, rowNum++);
    result.add(item);
}
return result;
```

Spring's iterator is responsible for:
- Executing the SQL statement and obtaining the `ResultSet`.
- Calling `rs.next()` to advance to each row.
- Calling `mapRow(rs, rowNum)` right when the cursor is on a valid row.
- Collecting the Java objects returned by the mapper into a list for `query(...)`.
- Closing the `ResultSet`/`Statement` and releasing the connection owned by the template according to its contract and transaction context.

In Spring, `RowMapperResultSetExtractor` is a common adapter that uses a `RowMapper` to produce one object per row of the `ResultSet`. That is the **extractor class** that handles iteration, while the mapper only handles the current row. You do not need to depend on this internal/adapter class directly in normal repositories: use `JdbcTemplate.query(...)`.

### Correct Timeline

```text
SQL result: id=1,2,3,4

JdbcTemplate              RowMapper
   |
   | rs.next() → row 1
   +----------------------> mapRow(row 1, 0)
   |                         read id/name of row 1
   |<---------------------- return Student(1,...)
   |
   | rs.next() → row 2
   +----------------------> mapRow(row 2, 1)
   |<---------------------- return Student(2,...)
   |
   | rs.next() → row 3
   +----------------------> mapRow(row 3, 2)
   |<---------------------- return Student(3,...)
   |
   | rs.next() → row 4
   +----------------------> mapRow(row 4, 3)
   |<---------------------- return Student(4,...)
   |
   | rs.next() → false, finished
   +-- cleanup then return 4-element List<Student>
```

Core condition: **no line inside `mapRow` calls `next()`**. The callback is allowed to call getters such as `getString`, `getLong`, `getBigDecimal`, `getObject`, etc. on the current columns, but must not move the cursor itself.

## 4. Why Is Calling rs.next() Inside RowMapper Wrong?

### An Easy-to-Write Anti-Pattern

```java
RowMapper<Student> wrongMapper = (rs, rowNum) -> {
    rs.next();   // WRONG: Spring already moved to the current row beforehand.
    return new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
};
```

Suppose the SQL returns four rows `1,2,3,4`. While Spring is processing row 1, the mapper calls `next()` to move to row 2 and constructs a `Student` for row 2; Spring then calls `next()` to move to row 3; the mapper again moves to row 4. The returned result may only contain rows `2,4`:

| Step | Cursor positioned by Spring | Buggy mapper calls extra `next()` | Object created |
|---|---|---|---|
| 1 | row 1 (An) | moves to row 2 | Binh |
| 2 | row 3 (Chi) | moves to row 4 | Dung |
| 3 | no more rows | not called again | finished |

**The danger:** the system may throw no exception at all; it simply **loses data silently**. With an odd number of rows, the buggy mapper may call `next()` past the last row and then attempt to read a getter, receiving a `SQLException` depending on the driver. With cursors that do not support special navigation, operations like `previous()`/`absolute()` may fail immediately.

### The Correct Pattern

```java
RowMapper<Student> correctMapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

**Do not use `if (rs.next())` to “check whether there is a row” inside the mapper.** If the mapper is being invoked, Spring has already positioned a row for it. If the query returns 0 rows, the mapper **is not called**; `jdbc.query(...)` returns an empty list. Querying a required single row with `queryForObject(...)` has its own exception contract.

Do not use `rs.previous()` to “go back to the skipped row”: common forward-only `ResultSet`s do not allow moving backward, and manipulating the cursor still violates `RowMapper`'s contract. Remove cursor-movement calls from the mapper.

## 5. Exact Signature of RowMapper<T>

Core interface:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
```

This is a **simplified signature for illustration**, not copying all annotations/nullability/API metadata of a specific Spring version.

- `rs`: `ResultSet` **already positioned at a current row**. The main operation is reading the columns of this row.
- `rowNum`: row sequence number **during mapping**. With Spring JDBC's standard `RowMapperResultSetExtractor` adapter, it starts at **0** and increments for each row the mapper receives. It is **not** the `id` column in the DB, not the sequence number from SQL `ROW_NUMBER()`, and not `ResultSet.getRow()` (which in JDBC normally starts at 1 if supported).
- Return value `T`: object representing the current row. According to the API, a mapper may return Java `null`; however, non-null DTOs usually reduce confusion.
- `SQLException`: can be left for Spring to catch and translate via `DataAccessException`. Do not catch it and return a dummy object or drop the row unless business rules explicitly dictate it.

A `RowMapper` should generally be **stateless** and safely reusable. For example, a `static final` mapper that only depends on data from the `ResultSet`:

```java
private static final RowMapper<Student> STUDENT_MAPPER =
    (rs, rowNum) -> new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

Never store the `ResultSet` in an object field to read after `query()` returns: the `ResultSet`'s lifecycle has ended and it is no longer valid for that kind of access.

## 6. Each Callback Corresponds to a Cursor Control Level

A common source of confusion is that Spring JDBC has multiple callbacks taking a `ResultSet`, yet **permission to call `next()` differs**:

| Callback | Purpose | Does it call `rs.next()` itself? | How many times the framework invokes the callback |
|---|---|---|---|
| `RowMapper<T>.mapRow(rs, rowNum)` | Map **one row** to an object | **No** | Once per row received by the mapper |
| `RowCallbackHandler.processRow(rs)` | Process **one row** without returning an object | **No** | Once per row |
| `ResultSetExtractor<T>.extractData(rs)` | Process the **entire ResultSet** into one result | **May/must**, when iterating manually | Normally once for the entire result set |
| Plain JDBC `ResultSet` from code executing `executeQuery()` | Process results directly | **Yes**, must control the cursor | Decided directly by the code |
| `PreparedStatementCallback`/`ConnectionCallback` calling `executeQuery()` to get a `ResultSet` | Explicitly execute and iterate self-opened results | **Yes**, on the `ResultSet` created by the callback | Per callback logic, and must close the `ResultSet` it opened |

In other words: **“never call `ResultSet.next()`” is wrong; the accurate rule is “do not call `next()` in `RowMapper` and `RowCallbackHandler`”.** With `ResultSetExtractor` or plain JDBC, you write the loop yourself because the callback is entrusted with processing the entire result set.

### 6.1. RowMapper: Return a New Object for Each Row

```java
List<Student> students = jdbc.query("""
        SELECT id, name FROM students ORDER BY id
        """,
    (rs, rowNum) -> new Student(
        rs.getLong("id"),
        rs.getString("name")
    )
);
```

This example sits in a class with `JdbcTemplate jdbc`, and the `Student` record is defined accordingly. `JdbcTemplate` iterates over every row and builds `List<Student>`. Do not open a `ResultSet` yourself and do not close the `ResultSet` passed to the mapper by the template.

### 6.2. RowCallbackHandler: Process Rows Without Calling next()

```java
List<String> names = new ArrayList<>();

jdbc.query(
    "SELECT name FROM students ORDER BY id",
    (RowCallbackHandler) rs -> names.add(rs.getString("name"))
);
```

Use this when you only want to consume or accumulate information per row. Spring also positions the cursor and calls `processRow` with the current row. The callback has no `rowNum` parameter, and still **must not call `rs.next()`**. Be careful if the callback has side effects outside the DB: if the mapper/SQL fails midway, side effects already performed may not roll back together with the JDBC transaction.

### 6.3. ResultSetExtractor: Explicitly Iterate the Entire ResultSet

```java
List<String> names = jdbc.query("""
        SELECT name FROM students ORDER BY id
        """,
    (ResultSetExtractor<List<String>>) rs -> {
        List<String> result = new ArrayList<>();
        while (rs.next()) {  // CORRECT in ResultSetExtractor.
            result.add(rs.getString("name"));
        }
        return result;
    }
);
```

Here `extractData` receives the entire result set, so **the callback must iterate itself** to retrieve each row. Spring still manages closing the `ResultSet`/`Statement` normally after the extractor completes; the callback does not call `rs.close()` on the `ResultSet` passed in by the template.

When using `jdbc.query(...)` overloads with lambdas, use an explicit cast/interface in examples prone to **overload ambiguity**:
- A lambda `(rs, rowNum) -> ...` taking **two parameters** is a `RowMapper`.
- A lambda `rs -> { while (rs.next()) ...; return object; }` is a `ResultSetExtractor`.
- A lambda `(RowCallbackHandler) rs -> ...` with one parameter returning `void` is a `RowCallbackHandler`.

This distinction is one of the fastest ways during code review to know who should control the cursor.

## 7. Runnable Spring Boot and Java 17 Example Application

The demo below runs on Spring Boot 3.3.5 + H2 (JDBC), using 4 ordered rows to reproduce the dropped-row bug when calling `next()` inside a mapper. H2 is used for learning; when integrating into production, test against the real driver/database. Java 17, Gradle 8.x, and an environment able to download dependencies are sufficient for the sample project.

### 7.1. Structure

```text
row-mapper-cursor-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/RowMapperCursorDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'row-mapper-cursor-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    age INTEGER
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO students (id, name, age) VALUES (1, 'An', 20);
INSERT INTO students (id, name, age) VALUES (2, 'Binh', NULL);
INSERT INTO students (id, name, age) VALUES (3, 'Chi', 21);
INSERT INTO students (id, name, age) VALUES (4, 'Dung', 22);
```

`src/main/java/example/jdbc/RowMapperCursorDemoApplication.java`:

```java
package example.jdbc;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;

@SpringBootApplication
public class RowMapperCursorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RowMapperCursorDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            String sql = "SELECT id, name, age FROM students ORDER BY id";

            RowMapper<Student> goodMapper = (rs, rowNum) ->
                new Student(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getObject("age", Integer.class)
                );

            List<Student> correct = jdbc.query(sql, goodMapper);
            System.out.println("correct=" +
                correct.stream().map(Student::name).toList());

            List<String> rowNumbers = jdbc.query(sql,
                (rs, rowNum) ->
                    rowNum + ":" + rs.getString("name"));
            System.out.println("rowNums=" + rowNumbers);

            // COUNTER-EXAMPLE: intentionally violates the RowMapper contract.
            List<String> wrong = jdbc.query(sql,
                (rs, rowNum) -> {
                    rs.next(); // Do not write this in production code.
                    return rs.getString("name");
                });
            System.out.println("wrong=" + wrong);

            List<String> viaHandler = new ArrayList<>();
            jdbc.query(sql, (RowCallbackHandler) rs ->
                viaHandler.add(rs.getString("name")));
            System.out.println("handler=" + viaHandler);

            ResultSetExtractor<List<String>> extractor = rs -> {
                List<String> result = new ArrayList<>();
                while (rs.next()) {
                    result.add(rs.getString("name"));
                }
                return result;
            };
            System.out.println("extractor=" + jdbc.query(sql, extractor));

            List<String> ageValues = jdbc.query(sql,
                (rs, rowNum) -> {
                    Integer age = rs.getObject("age", Integer.class);
                    return age == null ? "NULL" : age.toString();
                });
            System.out.println("ages=" + ageValues);
        };
    }
}

record Student(long id, String name, Integer age) {}
```

**Run:** inside the `row-mapper-cursor-demo` directory, with a compatible Gradle version installed:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, you can run `./gradlew bootRun` on Unix/macOS or `gradlew.bat bootRun` on Windows.

The six lines printed by the application **in exact order** are shown below (in addition to them, there may be startup/build logs from Spring/Gradle):

```text
correct=[An, Binh, Chi, Dung]
rowNums=[0:An, 1:Binh, 2:Chi, 3:Dung]
wrong=[Binh, Dung]
handler=[An, Binh, Chi, Dung]
extractor=[An, Binh, Chi, Dung]
ages=[20, NULL, 21, 22]
```

Explanation:
- `goodMapper` does not touch the cursor, receiving all 4 rows.
- `rowNums` shows that the callback sequence number normally starts at 0.
- `wrong` intentionally calls an extra `next()`, so only rows 2 and 4 remain. This is the **expected illustrative behavior with a forward-only ResultSet** on this H2 demo; other drivers may report an error when the cursor is pushed outside the valid region.
- `RowCallbackHandler` also reads all 4 rows accurately without calling `next()`.
- `ResultSetExtractor` iterates manually with `while(rs.next())` and receives all 4 rows.
- Binh's `age` column has SQL NULL, read via `getObject("age", Integer.class)` as Java null, and then displayed as the string "NULL".

**Specifically:** the demo intentionally includes the `wrong` anti-pattern for comparison; never copy the wrong mapper into a real repository.

## 8. How to Write a Clean RowMapper in a Repository

In application code, separate SQL from mapping and reuse stateless mappers.

Spring JDBC example, using the `students` table from the demo:

```java
// StudentRepository.java
package example.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class StudentRepository {

    private static final RowMapper<Student> STUDENT_MAPPER =
        (rs, rowNum) -> new Student(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getObject("age", Integer.class)
        );

    private final JdbcTemplate jdbc;

    public StudentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Student> findAll() {
        return jdbc.query("""
                SELECT id, name, age
                FROM students
                ORDER BY id
                """, STUDENT_MAPPER);
    }

    public Optional<Student> findById(long id) {
        try {
            Student item = jdbc.queryForObject("""
                    SELECT id, name, age
                    FROM students
                    WHERE id = ?
                    """, STUDENT_MAPPER, id);
            return Optional.of(item);
        } catch (EmptyResultDataAccessException ex) {
            return Optional.empty();
        }
    }
}
```

Remarks:
- `findAll()` returns a list: if the table is empty, Spring returns an empty `List`, and the mapper does not run at all.
- `findById()` queries at most one record by `PRIMARY KEY`. If 0 rows are returned, `queryForObject()` throws `EmptyResultDataAccessException`; because the contract here allows absence, the method specifically converts it into `Optional.empty()`.
- If the query unexpectedly returns >1 row, `IncorrectResultSizeDataAccessException` continues to propagate; do not turn it into “not found”.
- `Optional.of(item)` is appropriate for the illustrated mapper that always constructs a non-null `Student`. A mapper allowed to return `null` requires a different contract.
- With `jdbc.query(...)`, the template iterates; the same mapper is reused for `queryForObject(...)`. **Even when the query returns only one row, the mapper still does not call `next()`.**
- SQL binds ID with `?`, without concatenating input into the SQL string.

`queryForObject(sql, Student.class, id)` does not replace `RowMapper<Student>` for multi-column mapping; the `Class<T>` overload is for single-column typed results. Each API has its own contract; do not assume from the name “object” that it automatically converts arbitrary multi-column rows into a Java record.

## 9. What Does rowNum Mean and How Should It Not Be Used?

With a standard `JdbcTemplate.query(..., RowMapper<T>)`, `rowNum` starts at `0` for the first row the mapper processes and increments with each row. It is useful for logging, diagnostics, or tagging positions within the returned batch. However:

- `rowNum` is not `id`, and not a primary key.
- `rowNum` is not a global database order or a durable identifier. Two different queries can return different orders if there is no `ORDER BY`.
- When using pagination, each query execution can start at `rowNum = 0` again, regardless of whether you are on page 20.
- SQL `ROW_NUMBER() OVER (...)` results normally start at 1, independent of `rowNum` in the callback.
- `rs.getRow()` in JDBC reports the cursor's row number (normally starting at 1), and should not be confused with `rowNum`.

If a stable display order is needed:
1. Define `ORDER BY` in SQL (with a secondary tie-breaker key when necessary).
2. Use a result column or pagination metadata to derive ordering; do not mistakenly assign `rowNum` as a business ID.
3. Do not rely on the table's “inherent” order when there is no `ORDER BY`.

Example:

```java
List<String> labels = jdbc.query("""
        SELECT id, name
        FROM students
        ORDER BY id DESC
        """,
    (rs, rowNum) ->
        "index=" + rowNum + ", id=" + rs.getLong("id")
);
```

With the demo data, the strings will correspond to `index=0, id=4` then `index=1, id=3`, etc., showing that `rowNum` reflects the position within the query result, **not the ID number**.

## 10. JDBC Getters and SQL NULL in a Mapper

Another common mistake is reading a primitive type without handling SQL NULL:

```java
// Does not distinguish NULL from 0:
int age = rs.getInt("age");
```

JDBC `ResultSet.getInt(...)` returns `0` when the SQL column is NULL; to distinguish, you must call `rs.wasNull()` **immediately after the getter just read**:

```java
int rawAge = rs.getInt("age");
Integer age = rs.wasNull() ? null : rawAge;
```

If the driver/type mapping supports it, `rs.getObject("age", Integer.class)` returns a boxed `Integer` or null and reduces boilerplate. On PostgreSQL, JSON or custom enum types may need different mapper/driver handling; rely on the schema and integration tests rather than expecting all drivers to convert types identically.

Mapping verification rules:
- Use the **column name/alias** actually present in the SQL, e.g., `SELECT display_name AS name` and then `rs.getString("name")`.
- Do not write `rs.getString("old_name")` after SQL has changed the alias; that is a mapping error, not a cursor error.
- Choose `BigDecimal` for SQL DECIMAL/NUMERIC values requiring precision; pay attention to precision/scale.
- For timestamp columns, clarify timezone and Java type (`LocalDateTime`, `OffsetDateTime`, `Instant`, etc.) per DB/driver semantics.
- When a column must be NOT NULL, it is better to enforce a DB constraint and validate data; do not silently default null to 0/empty string without a business rule.
- The mapper should only build a simple Java DTO/entity mapping; avoid making another network/DB call per row, which easily causes N+1 queries and increases latency.

**Calling a getter multiple times** on the same row is sometimes possible, but avoid repeating expensive converters; store the value in a local variable. Do not use `rs.next()` to “read the next column”: **columns** are accessed by column name or index; `next()` moves to **another row**.

## 11. JDBC Resource Ownership in RowMapper

`JdbcTemplate` typically obtains a connection according to the Spring transaction context, creates the statement/resultset, executes, iterates, and cleans up the resources it owns. `RowMapper` is only lent a `ResultSet` at the current row, and **must not close it**:

```java
RowMapper<Student> wrong = (rs, rowNum) -> {
    Student current = new Student(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getObject("age", Integer.class)
    );
    rs.close(); // WRONG: closes the ResultSet managed by JdbcTemplate.
    return current;
};
```

Nor should you do things like:

```java
// WRONG: returning ResultSet to another layer to read after the query finishes.
RowMapper<ResultSet> bad = (rs, rowNum) -> rs;
```

Both examples are **anti-patterns** and should never run in a real application. When `JdbcTemplate.query(...)` finishes, the `ResultSet` is normally closed. A service/HTTP layer must not keep a reference to the cursor to call getters later.

A well-written mapper returns **data detached from the cursor** such as a record/DTO; the template is responsible for releasing resources. If you need to read very large datasets, do not pass a `ResultSet` across layers; choose pagination, cursor streaming with a clear lifecycle, or `queryForStream`, where **the caller must close the `Stream`** with try-with-resources:

```java
// Inside a class with JdbcTemplate jdbc, RowMapper<Student> STUDENT_MAPPER.
try (java.util.stream.Stream<Student> stream = jdbc.queryForStream("""
        SELECT id, name, age FROM students ORDER BY id
        """, STUDENT_MAPPER)) {
    stream.forEach(student -> process(student));
}
```

`process(student)` is an application-defined handler. Even when invoked via `queryForStream`, `RowMapper` still only maps **one row currently positioned by the driver/template**; it has no right to call `next()` itself. `queryForStream` uses blocking JDBC, and fetch/streaming efficiency depends on the driver and transaction.

## 12. When a Mapper Throws SQLException or RuntimeException

`mapRow(...)` is allowed to declare `throws SQLException`. If a JDBC getter encounters an error, you usually do not need to wrap `try/catch(SQLException)` in every mapper; `JdbcTemplate` has a mechanism to translate `SQLException` into `DataAccessException`.

```java
RowMapper<Student> mapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("missing_column"), // SQL does not select this column.
        rs.getObject("age", Integer.class)
    );
```

When the query runs on the demo schema, reading `missing_column` can cause a `SQLException`; the template layer translates it into an appropriate data access exception. Do **not** return a fake `Student` or silently skip the row when mapping fails.

For errors from application Java code, for example:

```java
RowMapper<Student> mapper = (rs, rowNum) -> {
    if (rowNum > 1000) {
        throw new IllegalStateException("Unexpected result size");
    }
    return new Student(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getObject("age", Integer.class));
};
```

This is an illustrative policy; **you should not limit the result set inside the mapper** because the DB has already executed the query and may have loaded a large amount of data. Put `LIMIT`/pagination/query semantics in SQL. `RuntimeException` from the mapper can propagate; the template still performs lifecycle cleanup. Do not catch all errors and return an empty list: that hides data bugs and makes debugging hard.

### Do Not Try to “Fix” Accidental Row Reading with try/catch

The following code is wrong regarding both cursor handling and error handling:

```java
RowMapper<Student> wrong = (rs, rowNum) -> {
    try {
        if (rs.next()) { // WRONG: skips past the current row.
            return new Student(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getObject("age", Integer.class)
            );
        }
    } catch (SQLException ignored) {
        // WRONG: swallows real errors.
    }
    return null;
};
```

If an error occurs, the **root** fix is to remove `rs.next()`, keep the mapper pure, and let appropriate errors propagate. Do not turn cursor errors into a null row, as that creates a list with hard-to-detect null elements.

## 13. Contract Testing: Verify the Mapper Only Reads the Current Row

An integration test using Spring Boot + H2 or a real DB can compare output against a fixed seed. When SQL returns 4 rows, a correct mapper must return **all 4 records in the exact order**. For cursor bugs, merely checking “list is not empty” is insufficient: a buggy mapper can still return two elements even after losing two rows.

JUnit 5/AssertJ example in a project that already has the test starter and schema fixture:

```java
// StudentRepositoryTest.java - test class snippet in a Spring Boot project.
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class StudentRepositoryTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsAllRowsExactlyOnce() {
        List<String> names = jdbc.query("""
                SELECT name FROM students ORDER BY id
                """,
            (rs, rowNum) -> rs.getString("name")
        );

        assertThat(names).containsExactly("An", "Binh", "Chi", "Dung");
    }

    @Test
    void callbackReceivesZeroBasedRowNum() {
        List<Integer> nums = jdbc.query("""
                SELECT id FROM students ORDER BY id
                """,
            (rs, rowNum) -> rowNum
        );

        assertThat(nums).containsExactly(0, 1, 2, 3);
    }
}
```

The test requires `spring-boot-starter-test` in the **testImplementation** dependency and the datasource/schema/data fixture initialized in the test context; on `@JdbcTest`, Spring Boot normally configures an embedded DB if on the classpath and the test manages rollback. It cannot run with plain `javac` alone.

For pure unit testing of the mapper itself, you can mock `ResultSet` and verify the mapper **never calls `next()`**; for example with Mockito:

```java
@Test
void mapperNeverMovesCursor() throws SQLException {
    ResultSet rs = mock(ResultSet.class);
    when(rs.getLong("id")).thenReturn(7L);
    when(rs.getString("name")).thenReturn("An");
    when(rs.getObject("age", Integer.class)).thenReturn(20);

    Student item = STUDENT_MAPPER.mapRow(rs, 0);

    assertEquals("An", item.name());
    verify(rs, never()).next();
}
```

This snippet illustrates a **test method body** with static Mockito/JUnit imports and a defined mapper; it is not a complete file. However, testing mapper logic does not replace integration testing: you still need to verify the SQL query and actual mapping against a database.

### Matrix to Cover

| SQL data | Expected RowMapper behavior |
|---|---|
| 0 rows | Not called; `query(...)` returns an empty list |
| 1 row | Called once; does not call next |
| 4 rows | Called four times, all four DTOs according to ORDER BY |
| 1 row with nullable column | Maps null properly via boxed type/JDBC helper |
| SQL with alias differing from property name | Mapper uses the right alias or reports an error |
| Invalid SQL/column | Error propagates; no fake DTOs generated |
| Business duplicate rows | Query may return multiple DTOs; contract/business handles uniqueness, mapper does not “skip duplicates” itself |
| Very large dataset | Query is limited/paginated/stream lifecycle managed properly; mapper is not used to control row count |

Testing a single record in isolation **is not enough** to catch a `next()` bug; with one row, a buggy mapper may simply throw an error, whereas with multiple rows it can silently drop rows. Therefore, have an integration test with **at least 3–4 rows**, comparing all IDs and order.

## 14. Common Misconceptions

**Misconception 1: “JDBC requires calling next(), so RowMapper must call it too.”**

Plain JDBC indeed requires iterating yourself, but `JdbcTemplate` already iterates and passes the current row to the mapper. Writing `next()` in `RowMapper` advances the cursor twice.

**Misconception 2: “If I don't call next(), rs.getString will always read the first row.”**

No. Spring advances to each row before the mapper is called. The same mapper reads row 1, then row 2, then row N across successive invocations.

**Misconception 3: “rowNum is the JDBC ResultSet row number.”**

`rowNum` is a callback parameter provided by Spring; in the standard extractor it starts at 0. JDBC `ResultSet.getRow()` is normally 1-based, while the primary key does not depend on row position. Do not mix up the three values.

**Misconception 4: “RowCallbackHandler can call next() because it doesn't return an object.”**

`RowCallbackHandler.processRow(rs)` also only receives **an already-positioned row** and must not call `next`. To control the entire result set, choose `ResultSetExtractor`.

**Misconception 5: “ResultSetExtractor cannot call next() either.”**

On the contrary: `ResultSetExtractor` receives the entire `ResultSet` to process, typically using `while(rs.next())`. The difference is **the unit of work assigned**: a single row versus the entire set.

**Misconception 6: “If a mapper is buggy and causes an exception, I'll always know immediately.”**

No. With an even number of rows, calling an extra `next()` can drop half the data while still returning a `List` normally. You must verify size, IDs, and order in tests.

**Misconception 7: “I can return ResultSet from RowMapper for lazy processing in the service.”**

`ResultSet` belongs to the JDBC resource scope; the template may close it when the query returns. The mapper must materialize the needed data into a DTO, not retain the cursor.

**Misconception 8: “@Transactional changes permission to call next() inside the mapper.”**

Transactions coordinate the connection, commit/rollback; they **do not transfer ownership of `ResultSet.next()`** to `RowMapper`. Cursor rules do not change.

**Misconception 9: “The mapper uses rowNum=0 so JDBC starts from row 0.”**

A JDBC `ResultSet` is positioned by its cursor, whereas `rowNum` is a 0-based callback index supplied by the standard extractor. These are two different concepts.

**Misconception 10: “To skip a row that doesn't meet a condition, call next() inside the mapper.”**

No. If filtering is needed, prefer `WHERE` in SQL. If post-query Java filtering logic is needed, map all rows and then filter the `List`/`Stream`, considering the cost and result set size. `RowMapper` is not an iterator that lets you skip rows arbitrarily.

## 15. Code Review Checklist

- [ ] `RowMapper.mapRow(...)` only reads values from the **current row**.
- [ ] No `rs.next()`, `rs.previous()`, `rs.absolute()`, `rs.beforeFirst()`, or `rs.last()` inside the mapper.
- [ ] Does not close `ResultSet`/`Statement`/`Connection` provided by `JdbcTemplate` from within the mapper.
- [ ] Returns a DTO/record detached from `ResultSet` with matching column types/aliases.
- [ ] Nullability is handled: `getObject(..., Integer.class)` or `wasNull()` when using primitive getters.
- [ ] Does not use `rowNum` as a business ID; SQL includes `ORDER BY` when order matters.
- [ ] Does not make DB/API/network calls per row when JOIN/batch/projection can be used.
- [ ] If manual full-set iteration is needed, uses `ResultSetExtractor`/low-level JDBC with proper ownership.
- [ ] If using `RowCallbackHandler`, does not call `next()` either.
- [ ] Has tests covering at least 0, 1, and multiple rows, checking full IDs/order rather than only non-empty.
- [ ] Applies limits/pagination for large results; streams must be closed when the API returns a `Stream`.
- [ ] Mapper does not swallow SQL errors and does not return fake data when a column/driver fails.

## 16. Summary and References

**`RowMapper` is “one row in, one object out”, while `JdbcTemplate` is the side walking through the rows.** A single `mapRow(rs, rowNum)` call already receives `rs` at the row to be mapped, so **never call `ResultSet.next()` inside a RowMapper**. If you want to write a `while(rs.next())` loop yourself, put it in a `ResultSetExtractor` or a JDBC block where you manage the cursor directly, not in a mapper.

Official Spring documentation:
- Spring Framework `RowMapper` Javadoc, describing the “do not call next()” contract: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- `RowCallbackHandler` Javadoc, contract of `processRow`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- `ResultSetExtractor` Javadoc, processing the entire `ResultSet`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- `RowMapperResultSetExtractor` Javadoc, mapper adapter for multiple rows: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapperResultSetExtractor.html
- Spring Framework JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
