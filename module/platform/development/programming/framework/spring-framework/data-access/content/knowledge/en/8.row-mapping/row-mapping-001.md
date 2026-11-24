# RowMapper Maps One Row to an Object in Spring JDBC

## 1. From SQL Data Rows to Java Objects

Suppose the database has a table `employees` with columns `id`, `full_name`, `salary`, `manager_id`, and `hired_on`. A `SELECT` statement returns rows in a `ResultSet`, whereas the Java service wants to use an `Employee` object with clear property names and appropriate data types.

In manual JDBC, you typically have to iterate through the `ResultSet` yourself and call `rs.getLong(...)`, `rs.getString(...)`, and `rs.getBigDecimal(...)` to construct each object. Spring JDBC delegates the iteration and resource management to `JdbcTemplate`, while delegating the conversion of **one row into one object** to `RowMapper<T>`.

`RowMapper<T>` is an interface in `org.springframework.jdbc.core`. Its central contract is:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

This is a **simplified signature for learning**, not verbatim code copied from the Spring source file (the actual version has annotations/API documentation depending on the release). `T` is the object type each row will be converted into; for example, `RowMapper<Employee>` creates an `Employee`, and `RowMapper<String>` creates a `String`.

Three core principles:

1. **A single `mapRow` invocation processes one current row.** Spring has already positioned the `ResultSet` cursor at that row before calling you.
2. **`mapRow` only reads the row and creates the return value.** Do not call `rs.next()` or `rs.close()`, and do not store the `ResultSet` in a field to read later.
3. **`JdbcTemplate` is responsible for iterating over rows and closing the JDBC resources it manages.** You provide the column-to-object mapping and handle the application's conversion rules.

### 1.1. Processing Flow Diagram

```text
Repository / DAO
    |
    | query(SQL, RowMapper<Employee>, parameters...)
    v
JdbcTemplate
    |  creates/binds PreparedStatement, executes SQL
    v
ResultSet
    |  next() --> row 1 --mapRow(rs, 0)--> Employee 1
    |  next() --> row 2 --mapRow(rs, 1)--> Employee 2
    |  next() --> row 3 --mapRow(rs, 2)--> Employee 3
    |  next() --> end of data
    v
List<Employee> (for queries returning a list)
    |
    v
Service receives Java data, not ResultSet
```

The diagram above illustrates the case where `JdbcTemplate.query(sql, rowMapper, ...)` returns a list. Other overloads such as `queryForObject` have a different row-count contract, but each row is still mapped using the same idea. `RowMapper` does not itself decide whether a query must return one row or multiple rows.

### 1.2. Why Separate RowMapper?

Separating the mapper from SQL helps:

- Reuse a consistent mapping for `findAll`, `findById`, and `search`.
- Keep SQL/DAO responsible for selecting rows, filtering, sorting, and binding parameters; keep the mapper responsible for converting returned columns into the Java model.
- Control column aliases, numeric types, dates/times, `NULL` values, and how immutable objects are constructed.
- Avoid repeating `new Employee(...)` code in every query.
- Test mapping separately (especially with nullable columns or schema changes).

**Limitations:** `RowMapper` does not generate SQL on its own, does not prevent SQL injection, does not manage transactions, does not solve the N+1 query problem, and does not replace data model design. It is a narrow yet very important extension point for row-by-row reading.

## 2. Understanding `mapRow(ResultSet rs, int rowNum)` Precisely

### 2.1. `ResultSet rs` Is Already at the Right Row

The component executing the query (typically `JdbcTemplate`) controls the loop and invokes the callback while the cursor is pointing at a valid row. The mapper retrieves values from the **current row** by column name/label or column position.

```java
RowMapper<Employee> mapper = (rs, rowNum) ->
        new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

This is a **snippet**, assuming the `Employee` record is already defined and the columns/aliases exist in the SQL. Each lambda execution creates a new object from a single row.

Do not do the following:

```java
// WRONG: JdbcTemplate has already called rs.next() before running mapRow.
RowMapper<String> wrong = (rs, rowNum) -> {
    rs.next(); // Skips to the next row; may miss rows and cause an error at the end.
    return rs.getString("full_name");
};
```

At the end of the result set, `rs.next()` may return `false`, and reading columns when not positioned on a valid row will cause an error. Across different drivers, the symptoms may vary, but the rule is always **do not control the cursor inside `RowMapper`**.

### 2.2. `rowNum` Is Not the Record ID

The second parameter is the mapping sequence number provided by Spring; normally it starts at **0** for the first row of each query and increments with the number of rows processed.

```java
List<String> labels = jdbc.query(
        "SELECT id, full_name FROM employees ORDER BY id",
        (rs, rowNum) -> rowNum + ":" + rs.getString("full_name"));
```

With rows `Lan`, `Minh`, `Hoa` ordered by `id`, the result is:

```text
[0:Lan, 1:Minh, 2:Hoa]
```

Be sure to distinguish:

- `rowNum` is the row position in **the current query's result**, starting from 0.
- `rs.getLong("id")` is the key stored by the database.
- JDBC parameter positions in `PreparedStatement.setXxx(index, ...)` start from **1**.
- JDBC column positions when reading `rs.getXxx(columnIndex)` also start from **1**.
- If the SQL has no `ORDER BY`, the database does not guarantee row order; `rowNum` is not a stable identifier to use for caching, business keys, or pagination.

`rowNum` is useful for display numbering or tracking mapping errors within a query, but it should not be turned into a domain key.

### 2.3. What Does the Mapper Return?

`mapRow` can create a record, POJO, DTO, a single field, or a specialized type, depending on the generic parameter `T`.

```java
RowMapper<String> titleMapper =
        (rs, rowNum) -> rs.getString("title");

RowMapper<BigDecimal> salaryMapper =
        (rs, rowNum) -> rs.getBigDecimal("salary");
```

The snippets above use the corresponding SELECTed columns and import `RowMapper` and `BigDecimal`. The `RowMapper` API allows a mapper to return `null` in certain situations, but for business DTOs you should consistently return a valid object or clearly define nullable semantics. Do not use `null` to mask an SQL error or data violation.

### 2.4. Handling SQLException Properly

`mapRow` declares `throws SQLException`. If the driver reports an invalid column name, a conversion fails, or a JDBC error occurs, you normally let the `SQLException` propagate out of the callback. `JdbcTemplate` will translate the JDBC error via `SQLExceptionTranslator` into an appropriate unchecked `DataAccessException` subclass whenever possible.

```java
RowMapper<Employee> mapper = (rs, rowNum) ->
        new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

There is no need to wrap each `getXxx` in `try/catch(SQLException)` to return a dummy object. If logic inside the mapper explicitly throws `IllegalArgumentException` (an application error), it is not automatically translated as a `SQLException`. Consider the error contract and diagnostic information of each layer.

## 3. Mapping Accurately by Column, Alias, and Java Type

### 3.1. Column Names and Aliases Are Part of the Query Contract

Suppose the schema stores `full_name` while the Java record has a field `name`. In SQL we define an alias:

```sql
SELECT
    id,
    full_name AS display_name,
    salary,
    manager_id,
    hired_on
FROM employees
ORDER BY id
```

In the mapper, read the label `display_name`:

```java
String name = rs.getString("display_name");
```

`ResultSet.getString("display_name")` looks up the **column label** in the result (the alias if present). If the SQL statement does not select that column/alias, the mapper will encounter a column-reading error. This is especially likely when the same mapper is used for multiple queries and one query omits a required field.

When a `JOIN` query spans multiple tables that all have an `id` or `name` column, define explicit aliases such as `employee_id` and `department_name` to avoid ambiguity. Do not rely on `SELECT *` column order or implicit column names after schema changes.

### 3.2. Retrieving the Right Data Type

Common mappings:

| SQL column | Common JDBC getter | Java type | Notes |
| --- | --- | --- | --- |
| `BIGINT NOT NULL` | `getLong` | `long`/`Long` | `getLong` returns 0 on SQL `NULL`; requires `wasNull` if nullable |
| `VARCHAR` | `getString` | `String` | SQL `NULL` normally returns Java `null` |
| `DECIMAL(p,s)` | `getBigDecimal` | `BigDecimal` | Preserves monetary precision; scale follows data and DB |
| `INTEGER` | `getInt` | `int`/`Integer` | Distinguish 0 from SQL `NULL` |
| `BOOLEAN` | `getBoolean` | `boolean`/`Boolean` | For nullable columns, check `wasNull`/`getObject` |
| `DATE` | `getDate` then `toLocalDate` or `getObject(..., LocalDate.class)` | `LocalDate` | Requires JDBC 4.2 driver and dialect support |
| `TIMESTAMP` | `getTimestamp` or appropriate getter | `LocalDateTime`/`Instant` per contract | Time zone and instant interpretation must be clearly defined |
| `BINARY` / `VARBINARY` | `getBytes` | `byte[]` | Mutable array; control data size |

Do not coerce monetary values from `DECIMAL` into `double` and perform binary floating-point arithmetic when precision is required. For dates and times, clarify whether the database stores local datetime, UTC instant, or a timezone-aware type; having the mapper return the right Java type alone is not enough to guarantee temporal semantics.

### 3.3. SQL NULL and Primitive Values

This is a bug that can silently corrupt data:

```java
long managerId = rs.getLong("manager_id");
```

If `manager_id` is SQL `NULL`, `getLong` returns the default value `0`. You need to call `rs.wasNull()` **immediately after the corresponding getter**:

```java
long raw = rs.getLong("manager_id");
Long managerId = rs.wasNull() ? null : raw;
```

Or, if the driver supports JDBC 4.2 type conversion well, use:

```java
Long managerId = rs.getObject("manager_id", Long.class);
```

For `NULL`, the desired result is Java `null`, not manager ID 0. `rs.wasNull()` checks **the last column read**; if you read another column first and then call it, it checks the wrong column. Avoid primitive types for nullable fields if the application needs to distinguish a missing value from 0/false.

### 3.4. Required and Optional Are Two Different Contracts

A column defined as `NOT NULL` in the DB can be safely read with `getLong`/`getString` under the schema's non-null assumption. However, if data from a view, `LEFT JOIN`, or complex query can be `NULL`, you must evaluate **the result set's contract**, rather than inferring from the base table.

Example with `LEFT JOIN`:

```sql
SELECT
    e.id,
    d.name AS department_name
FROM employees e
LEFT JOIN departments d ON d.id = e.department_id
```

`department_name` can be `NULL` when there is no matching department, even though the `departments.name` column is declared `NOT NULL`. If the mapper needs a "no department" state, use a nullable `String departmentName` or a domain type that explicitly represents that case. Only generate a default value like `"N/A"` when that is genuinely a business rule.

## 4. Runnable Example: Java 17+, Spring JDBC, and H2

To see `RowMapper` in action clearly, let's write a **plain Spring Framework** program (without Spring Boot). One mapper for an immutable `Employee` record is used across multiple queries; the SQL selecting rows changes, while the way each row is converted into an `Employee` stays the same.

Example versions: Java 17+, Spring Framework 6.2.12, H2 2.3.232. These versions are **pinned for reproducibility**, without claiming they are the latest releases.

### 4.1. Project Structure

```text
row-mapper-demo/
├── pom.xml
└── src/main/java/example/RowMapperDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>row-mapper-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
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
                <version>3.13.0</version>
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

`src/main/java/example/RowMapperDemo.java`:

```java
package example;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class RowMapperDemo {
    // Immutable record: a suitable case for mapping via constructor.
    record Employee(
            long id,
            String name,
            BigDecimal salary,
            Long managerId,
            LocalDate hiredOn) {}

    // Same set of columns/aliases for all queries returning Employee.
    private static final String SELECT_EMPLOYEE = """
            SELECT
                id,
                full_name AS display_name,
                salary,
                manager_id,
                hired_on
            FROM employees
            """;

    // Stateless and reusable mapper.
    private static final RowMapper<Employee> EMPLOYEE_MAPPER =
            (rs, rowNum) -> new Employee(
                    rs.getLong("id"),
                    rs.getString("display_name"),
                    rs.getBigDecimal("salary"),
                    rs.getObject("manager_id", Long.class),
                    rs.getObject("hired_on", LocalDate.class));

    static final class EmployeeDao {
        private final JdbcTemplate jdbc;

        EmployeeDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        List<Employee> findAll() {
            return jdbc.query(
                    SELECT_EMPLOYEE + " ORDER BY id",
                    EMPLOYEE_MAPPER);
        }

        List<Employee> findAtLeast(long minId) {
            return jdbc.query(
                    SELECT_EMPLOYEE + " WHERE id >= ? ORDER BY id",
                    EMPLOYEE_MAPPER,
                    minId);
        }

        Optional<Employee> findOptional(long id) {
            List<Employee> rows = jdbc.query(
                    SELECT_EMPLOYEE + " WHERE id = ?",
                    EMPLOYEE_MAPPER,
                    id);
            return rows.stream().findFirst();
        }

        Employee requireOne(long id) {
            return jdbc.queryForObject(
                    SELECT_EMPLOYEE + " WHERE id = ?",
                    EMPLOYEE_MAPPER,
                    id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        EmployeeDao employeeDao(JdbcTemplate jdbc) {
            return new EmployeeDao(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            EmployeeDao dao = context.getBean(EmployeeDao.class);

            jdbc.execute("""
                    CREATE TABLE employees (
                        id BIGINT PRIMARY KEY,
                        full_name VARCHAR(80) NOT NULL,
                        salary DECIMAL(12,2) NOT NULL,
                        manager_id BIGINT,
                        hired_on DATE NOT NULL
                    )
                    """);

            String insert = """
                    INSERT INTO employees (
                        id, full_name, salary, manager_id, hired_on
                    ) VALUES (?, ?, ?, ?, ?)
                    """;

            jdbc.update(insert, 1L, "Lan",
                    new BigDecimal("1000.50"), null,
                    Date.valueOf(LocalDate.of(2024, 1, 15)));
            jdbc.update(insert, 2L, "Minh",
                    new BigDecimal("1200.00"), 1L,
                    Date.valueOf(LocalDate.of(2024, 2, 2)));
            jdbc.update(insert, 3L, "Hoa",
                    new BigDecimal("900.25"), 1L,
                    Date.valueOf(LocalDate.of(2024, 3, 10)));

            System.out.println("All: " + dao.findAll());
            System.out.println("One: " + dao.requireOne(2L));
            System.out.println("Missing optional: " + dao.findOptional(99L));
            System.out.println("From id 2: " +
                    dao.findAtLeast(2L).stream()
                            .map(Employee::name)
                            .toList());

            List<String> rowNumbers = jdbc.query(
                    "SELECT full_name FROM employees ORDER BY id",
                    (rs, rowNum) ->
                            rowNum + ":" + rs.getString("full_name"));
            System.out.println("rowNum: " + rowNumbers);

            try {
                dao.requireOne(99L);
            } catch (EmptyResultDataAccessException ex) {
                System.out.println("Missing required: " +
                        ex.getClass().getSimpleName());
            }
        }
    }
}
```

Run with Maven in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.RowMapperDemo
```

Lines printed by the program's `System.out.println` (excluding any logs produced by the build tool):

```text
All: [Employee[id=1, name=Lan, salary=1000.50, managerId=null, hiredOn=2024-01-15], Employee[id=2, name=Minh, salary=1200.00, managerId=1, hiredOn=2024-02-02], Employee[id=3, name=Hoa, salary=900.25, managerId=1, hiredOn=2024-03-10]]
One: Employee[id=2, name=Minh, salary=1200.00, managerId=1, hiredOn=2024-02-02]
Missing optional: Optional.empty
From id 2: [Minh, Hoa]
rowNum: [0:Lan, 1:Minh, 2:Hoa]
Missing required: EmptyResultDataAccessException
```

### 4.2. What Does Each Output Line Prove?

- `All`: `findAll()` receives a `List<Employee>` with three records; the mapper runs three times, each time creating a new record from the current row. `ORDER BY id` determines the presentation order.
- `One`: `queryForObject` calls the same mapper, but the method's contract is **exactly one row**; `Employee[id=2,...]` is created from the row with `id = 2`.
- `Missing optional`: `query(...)` finds no rows and therefore returns an empty list; `findOptional(...)` converts it to `Optional.empty`. The mapper **is not called** when there are no rows.
- `From id 2`: changing the SQL condition does not require changing the mapper because the column/alias set is still sufficient. `Employee::name` only extracts names after the Java results are already obtained.
- `rowNum`: the lambda reads the sequence numbers 0, 1, 2 supplied by `JdbcTemplate`, independent of the `id` values in the database.
- `Missing required`: calling `queryForObject` with the same mapper when there are no rows throws `EmptyResultDataAccessException`, differing from the `Optional` contract.
- `Lan`'s `managerId=null`: the typed getter `getObject("manager_id", Long.class)` preserves the SQL `NULL` meaning. `BigDecimal` keeps monetary amounts in decimal form; `LocalDate` represents the `DATE` column.

**Regarding resources:** `DriverManagerDataSource` does not have a connection pool; it is used because it makes the demo easy to run. Server applications should use an appropriate `DataSource`/pool (for example HikariCP), and should not infer from the demo that opening a new connection per request is optimal. `DB_CLOSE_DELAY=-1` is an H2 option so in-memory data persists across connections within the same process.

### 4.3. Why Can the Mapper Be Shared?

`EMPLOYEE_MAPPER` is declared `static final` to be shared across all queries. What makes it safe is **holding no mutable state**: the lambda only reads the current `ResultSet`, creates a new `Employee`, and returns it. `final` only fixes the reference; it does not automatically make a mapper with mutable fields thread-safe.

If a mapper holds a shared `ArrayList` or counter and mutates it on each call, two concurrent requests could mix their data. Any accumulator needed for a query should belong to **each invocation** or be owned by `JdbcTemplate` via the result list.

## 5. How Does RowMapper Combine with Query Methods?

### 5.1. `query`: 0 to Many Rows

```java
List<Employee> employees = jdbc.query(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id >= ? ORDER BY id",
        EMPLOYEE_MAPPER,
        2L);
```

This is a **snippet**, requiring the declarations from the main example. `query` executes the SQL, binds parameters, and calls the mapper for each row. It returns a list; if there are no rows, it normally returns an empty list, **without throwing an “expected one result” error**. If the SQL returns 100 rows and has no limit, the mapper runs 100 times; the list can consume memory accordingly.

### 5.2. `queryForObject`: Exactly One Row

```java
Employee employee = jdbc.queryForObject(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id = ?",
        EMPLOYEE_MAPPER,
        2L);
```

`queryForObject` expects **exactly one row**. If there are no rows, Spring normally throws `EmptyResultDataAccessException`. If there is more than one row, it throws `IncorrectResultSizeDataAccessException` (or an appropriate subclass). These are **cardinality contracts of the `queryForObject` method**, not an “error” feature of `RowMapper`.

Even if a mapper may return `null` for a single row, having one row is still different from the SQL returning **0 rows**. Avoid using `queryForObject` for a “may be missing” scenario and swallowing exceptions on every path; when the problem naturally allows no result, use `query` and convert to `Optional` or an appropriate abstraction.

### 5.3. `queryForList` Does Not Automatically Generate Arbitrary DTOs

`JdbcTemplate.queryForList(sql)` normally returns `List<Map<String, Object>>` where each row is a column-to-value map, whereas `queryForList(sql, SomeClass.class)` serves single-column results convertible to the target type. It does not mean automatically mapping multi-column rows into `Employee`.

To obtain domain types, use `RowMapper<Employee>` via `query`/`queryForObject` or an appropriate mapper/converter. Clearly separating “reading data” from “mapping data” helps avoid manual map casting in services.

### 5.4. The Mapper Can Be Used with `NamedParameterJdbcTemplate`

`NamedParameterJdbcTemplate` only changes how SQL parameters are written and bound, without changing the nature of row mapping:

```java
NamedParameterJdbcTemplate named =
        new NamedParameterJdbcTemplate(jdbc.getDataSource());

List<Employee> employees = named.query(
        "SELECT id, full_name AS display_name, salary, manager_id, hired_on " +
        "FROM employees WHERE id >= :minId ORDER BY id",
        Map.of("minId", 2L),
        EMPLOYEE_MAPPER);
```

This is an illustrative snippet, requiring `Map`, `NamedParameterJdbcTemplate`, and a configured `jdbc` with a `DataSource`. The `:minId` parameter is translated into a JDBC prepared statement; the mapper still reads the same columns as before. Do not concatenate user input into SQL. The value of `RowMapper` lies in the column-to-object contract, so it can be reused across different query styles.

## 6. RowMapper vs. RowCallbackHandler and ResultSetExtractor

These three APIs are often confused because all three involve `ResultSet`.

| Interface | Processing level | Who calls `rs.next()`? | Expected output |
| --- | --- | --- | --- |
| `RowMapper<T>` | One row → one value `T` | `JdbcTemplate` | One `T` per row; template typically collects into `List<T>` |
| `RowCallbackHandler` | Operates on each current row; not required to return `T` | `JdbcTemplate` | Can update a custom accumulator/sink |
| `ResultSetExtractor<T>` | Entire `ResultSet` → one value `T` | **You iterate inside the extractor** | Aggregating, grouping multiple rows, building complex aggregates |

### 6.1. When Is RowMapper the Natural Choice?

Use `RowMapper` when the relationship is genuinely **one row can produce one independent object**, for example:

- `employees` row → `Employee`.
- `products` row → `ProductSummary`.
- `orders` row → `OrderRow` or display DTO.
- A single SQL aggregate row such as `COUNT(*)` → one number (in many cases `queryForObject(sql, Long.class)` is even simpler).

If SQL returns multiple JOINed rows for the same order with multiple line items, building a complete `Order` with **a row mapper per row** can produce duplicate order copies. When you need to **collapse multiple rows into one aggregate**, consider `ResultSetExtractor` or mapping to flat row DTOs and grouping in the service/DAO.

### 6.2. How Does RowCallbackHandler Differ from RowMapper?

```java
List<Long> ids = new ArrayList<>();

jdbc.query(
        "SELECT id FROM employees ORDER BY id",
        (RowCallbackHandler) rs -> ids.add(rs.getLong("id")));
```

This snippet is illustrative, requiring `ArrayList`, `RowCallbackHandler`, and the `jdbc` bean. `RowCallbackHandler` processes each row without returning an object via `mapRow`. `ids` must be newly created per invocation when concurrency is present; do not store the result list as a shared field in a singleton DAO. If the goal is simply to fetch a list of IDs, using `RowMapper<Long>` is still cleaner:

```java
List<Long> ids = jdbc.query(
        "SELECT id FROM employees ORDER BY id",
        (rs, rowNum) -> rs.getLong("id"));
```

### 6.3. ResultSetExtractor Iterates Over All Rows Itself

```java
ResultSetExtractor<BigDecimal> sumExtractor = rs -> {
    BigDecimal sum = BigDecimal.ZERO;
    while (rs.next()) {
        sum = sum.add(rs.getBigDecimal("salary"));
    }
    return sum;
};
BigDecimal total = jdbc.query(
        "SELECT salary FROM employees",
        sumExtractor);
```

This is also an illustrative snippet, requiring the relevant imports and bean. `ResultSetExtractor` is allowed to call `rs.next()` because its contract requires processing the entire result set. However, for computing a sum, SQL `SELECT SUM(salary)` is more efficient and shorter in many cases; the example is just to distinguish the callback loop.

## 7. Built-in Mapper Styles: Hand-Written or Automatic Mapping?

### 7.1. Hand-Written RowMapper

```java
RowMapper<Employee> explicit =
        (rs, rowNum) -> new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
```

Pros: transparent aliases, types, and null rules; well suited for DTOs/records, custom domain types, complex conversions, and performance tuning when profiling shows it is needed.

Cons: requires updating the mapper when the DTO/schema contract changes; can duplicate code if multiple DAOs write the same mapping without extracting it to a shared place.

### 7.2. BeanPropertyRowMapper

`BeanPropertyRowMapper<T>` is convenient when the target is a JavaBean with a no-argument constructor and matching setters, for example:

```java
public class EmployeeBean {
    private long id;
    private String fullName;

    public EmployeeBean() {}

    public void setId(long id) { this.id = id; }
    public void setFullName(String fullName) { this.fullName = fullName; }
    // Getters can be added as needed.
}
```

This is a bean-style illustrative snippet, not a standalone application. With a query selecting `id` and `full_name`, the mapper can match underscore column names to the corresponding camelCase properties:

```java
RowMapper<EmployeeBean> mapper =
        BeanPropertyRowMapper.newInstance(EmployeeBean.class);
```

Import `org.springframework.jdbc.core.BeanPropertyRowMapper`. Requires matching columns, public setters, and compatible type conversions. It does not automatically handle arbitrary DB-specific types, arbitrary constructors, or custom business logic.

### 7.3. DataClassRowMapper for Records and Constructors

`DataClassRowMapper<T>` supports Java records, Kotlin data classes, and classes whose constructor parameter names match column names. For example:

```java
record ProductView(long id, String productName) {}

RowMapper<ProductView> mapper =
        DataClassRowMapper.newInstance(ProductView.class);

// SELECT id, product_name FROM products ...
```

This is an illustrative snippet; it requires importing `DataClassRowMapper` and having the corresponding table/SQL. The mapper selects an appropriate constructor; aliases/column names must match parameters/properties according to the mapper's naming rules. For mappings with special logic or performance sensitivity, Spring recommends considering a custom `RowMapper`.

### 7.4. Choosing a Solution by Complexity

| Criterion | Custom RowMapper | BeanPropertyRowMapper | DataClassRowMapper |
| --- | --- | --- | --- |
| Constructing immutable records | Explicit | Not the preferred choice for record constructors | Suitable when column/constructor names are compatible |
| JavaBean setters | Fully capable | Convenient, minimal code | Can also be used |
| Complex type conversion logic | Good control | Depends on default/configured conversion | Depends on conversion and constructor |
| Subtle nullable/alias columns | Direct control | Need to check whether automatic mapper behaves as desired | Need to check constructor/nullability |
| Very performance-sensitive | Easy to optimize intentionally | Convenience-first, needs actual measurement | Convenience-first, needs actual measurement |

Do not turn automatic mapping into a “no tests needed” assumption. Renamed columns, missing setters, SQL `NULL` into primitives, wrong scale, or constructor parameter order can lead to errors or unexpected data. In critical DTO layers, explicit mapping is often easier to review and debug.

## 8. Common Mistakes When Writing a RowMapper

### 8.1. Calling `rs.next()` Inside `mapRow`

Error: missing rows, skipping the first row, or advancing the cursor out of bounds. Fix: let `JdbcTemplate` iterate; the mapper only reads the current row.

### 8.2. Reading the Wrong Alias or an Unselected Column

SQL:

```sql
SELECT id, full_name AS employee_name FROM employees
```

But the mapper:

```java
rs.getString("display_name"); // This alias does not exist in the SELECT above.
```

The result is usually a `SQLException` from the driver, which Spring then translates into a data access exception. Fix consistently: either the query must provide the alias the mapper reads, or the mapper must read the exact column label.

### 8.3. Confusing SQL NULL with 0/false

`rs.getLong("manager_id")` returns 0 on SQL NULL. Fix with `wasNull()` after the getter or `getObject("manager_id", Long.class)` as supported by the driver; avoid injecting fake 0 values into the domain model.

### 8.4. Using `rowNum` as a Data Key

`rowNum = 0` does not mean id 0. When the SQL changes sort/page/filter, the mapping order changes. Always retrieve the real key from the ID column.

### 8.5. Mapper Holding Shared Mutable State

```java
// Anti-pattern example: mapper is reused across multiple queries/threads.
class UnsafeMapper implements RowMapper<Employee> {
    private final List<String> seen = new ArrayList<>();

    @Override
    public Employee mapRow(ResultSet rs, int rowNum) throws SQLException {
        seen.add(rs.getString("display_name"));
        return new Employee(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getBigDecimal("salary"),
                rs.getObject("manager_id", Long.class),
                rs.getObject("hired_on", LocalDate.class));
    }
}
```

This is an erroneous illustrative snippet, requiring imports for the corresponding types. The shared `ArrayList` can be written to concurrently; even with synchronization, there is still a risk of mixing data across requests. Keep the mapper stateless or create a local accumulator per query. A thread-safe template **does not automatically make every callback thread-safe**.

### 8.6. Making Network Calls or N+1 SQL Queries Inside the Mapper

A mapper that calls an HTTP API or runs a second query per row prolongs how long the connection/statement stays open and can create N+1 round trips. For example, querying 100 employees and then fetching each employee's department with a new SQL query is usually expensive. Consider a JOIN, separate batch fetching, or post-mapping processing; measure latency and choose appropriately rather than placing heavy I/O inside `mapRow`.

### 8.7. Saving ResultSet to Read After the Query

```java
ResultSet leaked = jdbc.query(
        "SELECT id FROM employees",
        (ResultSetExtractor<ResultSet>) rs -> rs);
```

This is an **anti-pattern**: after `JdbcTemplate.query(...)` finishes, the `ResultSet` may already be closed and the resource is no longer valid. `RowMapper` should not keep `rs` inside a DTO either. Construct complete Java objects inside the callback.

### 8.8. Ignoring Result Cardinality Contracts

When the SQL finds no employee, `query(...)` returns an empty list; `queryForObject(...)` reports a missing-row error. When the SQL returns multiple rows but `queryForObject` is called, that is a cardinality error. Do not work around this by making the mapper ignore extra rows: it is the query API contract and SQL condition that need fixing.

### 8.9. Relying on SELECT * and Column Order

`SELECT *` couples the mapper to an unspecified schema. Reading `rs.getString(2)` easily breaks when column order changes. Use an explicit column list with stable aliases, especially when reusing a mapper across multiple queries.

### 8.10. Catching SQLException and Returning Fake Values

If a column is missing or conversion fails, returning `new Employee(0, "", BigDecimal.ZERO, null, ...)` disguises an infrastructure failure as valid data. Let JDBC errors propagate upward and handle them at a layer that can decide to log, retry, or return an appropriate error code.

## 9. Designing Mapping in a Repository/DAO

A typical repository can hold the mapper as a reusable field:

```java
@Repository
public class EmployeeRepository {
    private static final RowMapper<Employee> EMPLOYEE_MAPPER =
            (rs, rowNum) -> new Employee(
                    rs.getLong("id"),
                    rs.getString("display_name"),
                    rs.getBigDecimal("salary"),
                    rs.getObject("manager_id", Long.class),
                    rs.getObject("hired_on", LocalDate.class));

    private final JdbcTemplate jdbc;

    public EmployeeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Employee> findAll() {
        return jdbc.query(
                "SELECT id, full_name AS display_name, salary, manager_id, " +
                "hired_on FROM employees ORDER BY id",
                EMPLOYEE_MAPPER);
    }
}
```

This is an **illustrative snippet within a Spring application**, requiring imports for `@Repository`, `RowMapper`, `JdbcTemplate`, `List`, and the `Employee` type; it is not a standalone runnable file. `RowMapper` takes responsibility for mapping; the repository chooses the SQL and return contract; the service consumes `List<Employee>` without needing to see `ResultSet`. The mapper must be updated when the schema/DTO changes, but the service does not have to repeat JDBC code.

If multiple queries return different sets of columns, do not force all of them to use a single mapper that reads nonexistent columns. You can create a smaller DTO/mapper for a projection that only needs id/name:

```java
record EmployeeSummary(long id, String name) {}
RowMapper<EmployeeSummary> summaryMapper =
        (rs, rowNum) -> new EmployeeSummary(
                rs.getLong("id"),
                rs.getString("display_name"));
```

Creating narrower projections reduces data transferred from the DB and accurately reflects the use case's needs. Avoid fetching large unused columns only to ignore them in the mapper.

## 10. Testing RowMapper Semantically

### 10.1. Scenarios to Test

| Scenario | What to verify |
| --- | --- |
| Single normal row | All fields have the right values and types |
| No rows | `query` returns empty list, `queryForObject` throws missing-result error |
| Multiple rows | Mapper runs properly per row, order matches `ORDER BY` |
| SQL `NULL` in optional column | Java wrapper/nullable field receives `null`, not turned into 0 |
| DECIMAL and DATE | Monetary/date semantics preserved, avoiding loss of precision or timezone issues |
| Alias changes | Query and mapper match column names; mismatches are caught |
| JOIN with duplicate column names | Distinct aliases and DTO receives the right data |
| Added/removed columns | Mapper only requires columns needed by the contract; updated when projection changes |
| Shared mapper used concurrently | Does not retain mutable state from other requests |
| Multiple records with non-sequential keys | Uses actual `id`, not `rowNum` as the key |
| Query with user parameters | Bound via prepared statement, no unvalidated SQL concatenation |
| Large result sets | Check paging/streaming capability, measure memory and pool usage |

### 10.2. Illustrative JUnit 5 Test Example

Assuming `EmployeeDao` and the schema/data from the `RowMapperDemo` example have been initialized in the test fixture:

```java
// JUnit 5 snippet, not a standalone test file.
@Test
void mapsSqlNullAndDate() {
    Employee lan = dao.requireOne(1L);
    assertEquals("Lan", lan.name());
    assertNull(lan.managerId());
    assertEquals(new BigDecimal("1000.50"), lan.salary());
    assertEquals(LocalDate.of(2024, 1, 15), lan.hiredOn());
}

@Test
void optionalAndRequiredHaveDifferentCardinalityContracts() {
    assertTrue(dao.findOptional(999L).isEmpty());
    assertThrows(EmptyResultDataAccessException.class,
            () -> dao.requireOne(999L));
}
```

This snippet requires the JUnit Jupiter dependency, static imports from `org.junit.jupiter.api.Assertions`, `@Test`, the `dao` fixture, and the record/DAO types from the demo. It is not part of the Maven main program in Section 4. Integration tests with a real DB or Testcontainers are appropriate when SQL depends on PostgreSQL/MySQL/Oracle, especially for driver conversion, timezone, or alias behavior.

### 10.3. When Should a Mapper Be Tested Separately?

If mapping contains non-trivial logic (decoding JSON/enums, nullable relationships, fallbacks based on multiple columns, using domain constructors with validation), you can test the mapper with a mocked `ResultSet` or an integration query against the DB. For simple mappers, a DAO integration test verifying SQL + mapping is usually more valuable than a mock test that merely repeats `rs.getString(...)` without checking real columns.

## 11. Checklist When Writing a New RowMapper

1. **Determine what one row represents?** A DTO, entity summary, aggregate row, or scalar?
2. **List the exact columns/aliases** in SQL and which field each maps to; avoid assuming `SELECT *`.
3. **Choose the right Java types** for BIGINT, DECIMAL, DATE, and TIMESTAMP; define conversion rules.
4. **Handle SQL NULL explicitly**, especially for primitive getters, `LEFT JOIN`, and nullable values.
5. **Maintain one-row-one-object**; do not call `rs.next()`, and do not let `ResultSet` escape the callback.
6. **Separate the mapper from query logic** and reuse it only when the queries return the full required projection.
7. **Keep the mapper stateless**, especially if the bean/template is used across multiple requests.
8. **Choose the query API with the right cardinality:** `query` for lists/possibly empty, `queryForObject` for exactly one row.
9. **Put filtering/sorting conditions and parameters in SQL**, rather than letting the mapper filter or replace query logic.
10. **Test with 0/1/many rows, nulls, aliases, and concurrency** against real database data.

### Self-Check Questions

1. Why must `RowMapper.mapRow` not call `rs.next()`?
2. What number does `rowNum` start at, and how does it differ from the table's `id` key?
3. When `manager_id` is SQL `NULL`, what does `rs.getLong("manager_id")` return? How do you distinguish it from 0?
4. How do `query` and `queryForObject` differ when no rows are found?
5. Why can a mapper that reads `display_name` not be reused as-is for a query that does not SELECT that alias?
6. When should you use `DataClassRowMapper` instead of a hand-written mapper, and when is hand-written still better?
7. If a JOIN returns multiple child rows for one parent, why might a one-row-one-object `RowMapper<Order>` be insufficient to build the aggregate?
8. Why does a thread-safe `JdbcTemplate` not guarantee that a `RowMapper` with a shared `ArrayList` field is thread-safe?

**Key takeaway:** `RowMapper<T>` maps **the single current row** of a `ResultSet` into **one object `T`**. `JdbcTemplate` owns the lifecycle and result iteration; the mapper focuses on aliases, data types, `NULL`, and constructors. When this abstraction is used properly, DAOs are cleaner, services receive DTOs/records instead of the JDBC API, and the same mapping can be safely reused across multiple queries.

### Official References

- Spring Framework — JDBC Core (querying with RowMapper): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — RowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — JdbcTemplate JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — BeanPropertyRowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — DataClassRowMapper JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
