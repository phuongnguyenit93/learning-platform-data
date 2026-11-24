# queryForList(), queryForMap(), and Untyped Domain Mapping in Spring JDBC

> **Topic group:** JDBC Queries  
> **Context:** Spring Framework – data-access

## 1. Goals and Mental Model

When using `JdbcTemplate` in Spring Framework, a program sometimes just needs a small table of data, a few reporting columns, or a configuration value. Not every query warrants creating a separate Java class and writing a `RowMapper`. Spring JDBC offers options built around `Map<String, Object>`:

- `queryForList(sql, args...)` returns **multiple rows**, where each row is a `Map<String, Object>`: overall `List<Map<String, Object>>`.
- `queryForMap(sql, args...)` returns **exactly one row** as a `Map<String, Object>`. Zero rows or more than one row are both result-size errors.
- `queryForList(sql, elementType, args...)` returns multiple values of **one column**, with `elementType` specifying each element's type, such as `List<String>` or `List<Long>`. It does not turn multiple columns into domain objects.

Example `employee` table:

~~~text
id | name | salary
---+------+-------
1  | An   | 120.50
2  | Binh | NULL
3  | Chi  | 200.00
~~~

The three calls below have **different return types**:

~~~java
List<Map<String, Object>> rows = jdbcTemplate.queryForList(
    "SELECT id, name, salary FROM employee ORDER BY id");

Map<String, Object> one = jdbcTemplate.queryForMap(
    "SELECT id, name, salary FROM employee WHERE id = ?", 1L);

List<String> names = jdbcTemplate.queryForList(
    "SELECT name FROM employee ORDER BY id", String.class);
~~~

*These are illustrative snippets inside a method with an existing `jdbcTemplate` and data table; the complete Java 17+ project is in section 9.*

Here **untyped domain mapping** means not converting each row directly into `Employee`, `EmployeeSummary`, or a concrete domain DTO. Java still has types: map keys are `String`, values are declared as `Object`, and runtime objects have Java types determined by SQL type, JDBC driver, and mapper. The main trade-off is **less upfront mapping code** in exchange for **weaker type safety and less control over the data contract**.

## 2. Choosing the Right API by Row and Column Count

| Need | Common API | Java Type | Row/Column Condition |
| --- | --- | --- | --- |
| Multi-column list for flexible use | `queryForList(sql, args...)` | `List<Map<String, Object>>` | 0..n rows, multiple columns |
| Single multi-column record | `queryForMap(sql, args...)` | `Map<String, Object>` | **Exactly 1 row** |
| Single-column scalar list | `queryForList(sql, String.class, args...)` or suitable type | `List<T>` | 0..n rows, **exactly 1 column** |
| One scalar value, e.g., `COUNT(*)` | `queryForObject(sql, Integer.class, args...)` | `T` | Exactly 1 row, exactly 1 column |
| Multi-field domain objects | `query(sql, rowMapper, args...)` | `List<T>` | 0..n rows; each row built by mapper |
| One domain object | `queryForObject(sql, rowMapper, args...)` | `T` | Exactly 1 row; mapper builds the object |

The name `queryForList` does **not** mean it always returns a list of maps: the overload with `Class<T> elementType` returns a list of a single column. In Spring Framework 6.x examples, `?` is a placeholder for **parameter values**, bound through `JdbcTemplate`.

Do not assume 0 rows is handled identically across them:

- `queryForList`: 0 rows → **empty list**.
- `queryForMap`: 0 rows → **`EmptyResultDataAccessException`**.
- `queryForMap`: multiple rows → **`IncorrectResultSizeDataAccessException`**.
- `queryForObject`: also enforces the contract's row count; a SQL NULL cell is a different case from having zero rows.

## 3. `queryForList()` Returning a List of Maps

### 3.1. Data Shape

Suppose:

~~~java
List<Map<String, Object>> employees = jdbcTemplate.queryForList(
    "SELECT id AS employee_id, name AS employee_name, salary " +
    "FROM employee WHERE id >= ? ORDER BY id",
    2L
);
~~~

Conceptually, the first row is:

~~~text
employee_id   -> 2
employee_name -> "Binh"
salary        -> null
~~~

The second row has ID 3, name `"Chi"`, and salary 200.00. `JdbcTemplate` uses `ColumnMapRowMapper` by default to create one map per row, then collects those maps into a list.

Looping to read values:

~~~java
for (Map<String, Object> row : employees) {
    long id = ((Number) row.get("employee_id")).longValue();
    String name = (String) row.get("employee_name");
    Object salary = row.get("salary");
    System.out.println(id + ": " + name + ", salary=" + salary);
}
~~~

*This is an illustrative snippet inside a method with `employees`.* Reading ID via `Number` reduces coupling to whether the driver interprets SQL numeric types as `Integer`, `Long`, or another compatible numeric type; however, converting to `long` must still fit the value range.

### 3.2. When the Result Has No Rows

~~~java
List<Map<String, Object>> rows = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE id < ?", 0L);

System.out.println(rows.isEmpty()); // true
~~~

An empty list is a valid outcome for a list query. On a search screen, 0 rows may simply mean "no data". You do not need to catch `EmptyResultDataAccessException` when using `queryForList` this way.

### 3.3. A Map Is Not a Domain Object

`Map<String, Object>` does not guarantee that `id` is always present, `name` is non-null, or `salary` is always `BigDecimal`. It performs no validation, does not express entity relationships, and puts no business invariants in a constructor.

If multiple places in a service write `(String) row.get("employee_name")`, or if renaming an alias easily breaks several parts of the codebase, consider mapping to a strongly typed record/DTO.

## 4. `queryForMap()`: One Row with Multiple Columns

~~~java
Map<String, Object> employee = jdbcTemplate.queryForMap(
    "SELECT id AS employee_id, name AS employee_name, salary " +
    "FROM employee WHERE id = ?",
    1L
);
~~~

The result is still a column → value map, but **only exactly one row** is accepted.

### 4.1. When There Are No Rows

~~~java
try {
    Map<String, Object> missing = jdbcTemplate.queryForMap(
        "SELECT id, name FROM employee WHERE id = ?", 999L);
} catch (EmptyResultDataAccessException ex) {
    // No matching row.
}
~~~

Zero rows raises `EmptyResultDataAccessException`, **not** an empty map or null. It is a subclass of `IncorrectResultSizeDataAccessException`.

### 4.2. When There Are Multiple Rows

~~~java
try {
    Map<String, Object> ambiguous = jdbcTemplate.queryForMap(
        "SELECT id, name FROM employee");
} catch (IncorrectResultSizeDataAccessException ex) {
    // More than one row found.
}
~~~

The method does not automatically pick the first row. If you want multiple rows, use `queryForList`. If you expect exactly one row, the WHERE clause should rely on a primary key or a real uniqueness constraint in the database.

Use `LIMIT 1` only when business logic **genuinely accepts any one row / one in a defined order**; do not use it to mask illegal duplicate data. If you need the latest row, the selection rule must include an explicit `ORDER BY` and handle the not-found case.

### 4.3. "Not Found" Can Be a Normal Case

If looking up a non-existent ID is valid, you can use `queryForList` and check size:

~~~java
List<Map<String, Object>> candidates = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE id = ?", requestedId);

if (candidates.isEmpty()) {
    // Return Optional.empty() or appropriate response.
} else if (candidates.size() == 1) {
    Map<String, Object> value = candidates.get(0);
    // Process the single record.
} else {
    throw new IllegalStateException("ID is not unique");
}
~~~

*This snippet assumes `requestedId` and is not a standalone program.* Querying by a sound primary key will not return multiple rows. For typed domain objects, using `query(..., RowMapper)` and `findFirst` after verifying uniqueness usually expresses business intent more clearly.

### 4.4. A Single Value Should Use the Scalar API

If you only need one `String`, building a map adds no clarity:

~~~java
String name = jdbcTemplate.queryForObject(
    "SELECT name FROM employee WHERE id = ?",
    String.class,
    1L
);
~~~

`queryForObject` requires one row and one column in its scalar overload. Here the returned value already has the expected type instead of calling `row.get("name")` and casting manually. You still need to handle the zero-row case.

## 5. How Does `queryForList(sql, Class<T>)` Differ from `queryForList(sql)`?

The `elementType` form uses `SingleColumnRowMapper`, reading **one column** per row:

~~~java
List<String> names = jdbcTemplate.queryForList(
    "SELECT name FROM employee ORDER BY id",
    String.class
);

List<Long> ids = jdbcTemplate.queryForList(
    "SELECT id FROM employee ORDER BY id",
    Long.class
);
~~~

Conceptual data:

~~~text
names = [An, Binh, Chi]
ids   = [1, 2, 3]
~~~

Do not confuse `elementType` with a multi-property domain class. Example:

~~~java
// WRONG: SQL has two columns; elementType overload accepts only one column.
List<Employee> employees = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee", Employee.class);
~~~

`SingleColumnRowMapper` expects **exactly one column**, so a multi-column query typically raises `IncorrectResultSetColumnCountException`. It does not know how to invoke an `Employee(long, String)` constructor automatically.

**Proper domain mapping:**

~~~java
record Employee(long id, String name) {}

List<Employee> employees = jdbcTemplate.query(
    "SELECT id, name FROM employee ORDER BY id",
    (rs, rowNum) -> new Employee(
        rs.getLong("id"),
        rs.getString("name"))
);
~~~

*This is a Java 17+ illustration inside a method with `jdbcTemplate`.* The lambda is a `RowMapper<Employee>`: it knows the column order and how to convert columns into the record. The compiler can type-check usages of `Employee`; maps provide no comparable static checking.

**Note:** SQL `DECIMAL` generally fits `BigDecimal` better than `Double` when precision matters; a `NULL` column can produce a null list element. Passing `SomeClass.class` does not guarantee the driver/Spring can convert every vendor type to that class. Choose an appropriate type and test with real data.

## 6. How `ColumnMapRowMapper` Builds Keys

### 6.1. Column Name vs. Column Label

`ColumnMapRowMapper` relies on `ResultSet` JDBC metadata, preferring the **column label** when an `AS` alias is present. Example:

~~~sql
SELECT
    e.id AS employee_id,
    e.name AS employee_name,
    d.name AS department_name
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Accessing by key:

~~~java
Object id = row.get("employee_id");
Object employeeName = row.get("employee_name");
Object departmentName = row.get("department_name");
~~~

This is why you should declare explicit aliases when a map serves as a contract for reports or APIs. If you use `SELECT *`, schema changes can accidentally add or rename keys in the result.

### 6.2. Letter Case

Spring's default mapper typically uses `LinkedCaseInsensitiveMap` for keys, so lookups can be case-insensitive. However, the *original casing is preserved when iterating keys*, and how drivers report metadata can vary.

Do not rely on `map.toString()` having exact `ID` vs. `id` casing across all databases. If you need a stable JSON/CSV schema, use explicit aliases, validate keys, and normalize when exporting data.

In the runnable H2 example, the SQL uses quoted aliases such as `AS "employee_id"` so column labels stay consistently lowercase. Some databases have different identifier-quoting rules, so adjust SQL per dialect.

### 6.3. Duplicate Column Labels in JOINs

Error-prone example:

~~~sql
SELECT e.id, d.id
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Both columns may receive the label `id`. A map holds only one entry per key; it cannot cleanly represent two distinct columns with the same name. Use:

~~~sql
SELECT e.id AS employee_id, d.id AS department_id
FROM employee e
JOIN department d ON d.id = e.department_id
~~~

Do not rely on `map.values().toArray()[0]` as a field-order contract. Although Spring's default maps normally preserve insertion order, application code should depend on **key names** and explicit projections.

## 7. What Types Do `Object` Values in the Map Have?

### 7.1. Common Types

| SQL type | Typical Java type from JDBC | Notes |
| --- | --- | --- |
| `CHAR` / `VARCHAR` | `String` | Value may be null |
| `INTEGER` | `Integer` or compatible `Number` type | Do not cast straight to `Long` in every environment |
| `BIGINT` | `Long` or compatible numeric type | Check range and conversion rules |
| `DECIMAL` / `NUMERIC` | `BigDecimal` | Avoid losing precision by converting to double |
| `BOOLEAN` | `Boolean` or another DB-dependent representation | Do not assume all databases behave identically |
| `DATE` / `TIMESTAMP` | Various JDBC/date-time types depending on driver | Watch timezone and mapping |
| `BLOB`, `ARRAY`, JSON, or vendor types | `Blob`, `byte[]`, `Array`, `String`, vendor types... | Do not guess types across drivers |

This table shows *typical* outcomes, not a guarantee across every driver or column type. Actual types depend on the JDBC type, driver, and how Spring reads the value.

### 7.2. Safer Numeric Reading

~~~java
Object idValue = row.get("employee_id");
if (!(idValue instanceof Number number)) {
    throw new IllegalStateException("employee_id is not a number");
}
long id = number.longValue();
~~~

This avoids hard-casting to a single numeric class, while you must still ensure the conversion does not lose precision or overflow. For currency and decimals, prefer `BigDecimal` and a tested conversion contract.

### 7.3. SQL NULL vs. Missing Key

~~~java
Object salary = row.get("salary");
boolean salaryColumnIsPresent = row.containsKey("salary");
~~~

`row.get("salary") == null` can happen because:

1. The SQL selected `salary`, and the row's value is `NULL`.
2. The result does not contain a `salary` key (e.g., SELECT omitted the column or used a different alias).

Use `containsKey` when you must distinguish the two cases. Free-form maps allow both, whereas a domain contract may require a field to always be present.

### 7.4. Do Not Turn Maps into a "Hidden Domain Model"

If logic in many places writes `(String) row.get("employee_name")`, then the string `"employee_name"` has become a contract *unchecked by the compiler*. A typo like `"employee_nmae"` still compiles. A `record EmployeeSummary(long id, String name, BigDecimal salary)` makes the type contract explicit and easier to refactor.

Maps shine in dynamic dashboards, user-selectable columns, ad hoc SQL queries, or reports with no fixed model. For stable business data, create an explicit mapping class.

## 8. Choosing Maps, Scalars, and DTOs by Scenario

| Scenario | Choice | Reason |
| --- | --- | --- |
| Dynamic, multi-column result list | `queryForList` → `List<Map<String, Object>>` | Avoids fixing a class for every projection |
| Exactly one config row by unique key | `queryForMap` | Clear single-row contract; must handle 0 rows |
| Single-column list of names/codes | `queryForList(sql, String.class)` | Typed elements with low overhead |
| Row count via `COUNT(*)` | `queryForObject(sql, Integer.class)` | Single scalar value |
| Entity/DTO list used across layers | `query(sql, RowMapper<Dto>)` | Compiler can check fields and methods |
| Single domain object | `queryForObject(sql, RowMapper<T>)` when exactly 1 row | Typed domain mapping, clear cardinality |
| Aggregating multiple rows into trees/groups | `ResultSetExtractor` or grouping algorithm | One SQL row may not equal one standalone object |

Do not force a single choice for everything. Using `queryForList` with maps is not wrong, but it should be deliberate. When result shapes vary with no stable structure, maps are convenient; when there is a stable API contract or significant business logic, DTOs are more maintainable.

## 9. Complete Runnable Demo: Spring JDBC 6.x + H2 + Java 17

A console example running with **Java 17+**, **Maven 3.9+**, **Spring JDBC 6.1.14**, and **H2 2.2.224**. The purpose is to observe exact return shapes and result-size exceptions without Spring Boot configuration.

### 9.1. Structure

~~~text
jdbc-map-demo/
├── pom.xml
└── src/main/java/demo/
    └── JdbcMapDemo.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jdbc-map-demo</artifactId>
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

### 9.3. `src/main/java/demo/JdbcMapDemo.java`

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcMapDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:jdbc_map_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("CREATE TABLE employee (" +
                "id BIGINT PRIMARY KEY, " +
                "name VARCHAR(60) NOT NULL, " +
                "salary DECIMAL(10,2) NULL)");

        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                1L, "An", new BigDecimal("120.50"));
        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                2L, "Binh", (BigDecimal) null);
        jdbc.update(
                "INSERT INTO employee(id, name, salary) VALUES (?, ?, ?)",
                3L, "Chi", new BigDecimal("200.00"));

        String projection =
                "SELECT id AS \"employee_id\", " +
                "name AS \"employee_name\", " +
                "salary AS \"salary\" FROM employee";

        // Multiple rows, each row is Map<String, Object>.
        List<Map<String, Object>> rows =
                jdbc.queryForList(projection + " ORDER BY id");
        System.out.println("Rows: " + rows.size());
        System.out.println("First: " + rows.get(0).get("employee_name"));

        long firstId =
                ((Number) rows.get(0).get("employee_id")).longValue();
        System.out.println("First id: " + firstId);

        // Multiple rows, single column: List<String>.
        List<String> names = jdbc.queryForList(
                "SELECT name FROM employee ORDER BY id", String.class);
        System.out.println("Names: " + names);

        // Exactly one row as a Map.
        Map<String, Object> one = jdbc.queryForMap(
                projection + " WHERE id = ?", 2L);
        System.out.println("One row: " + one.get("employee_name"));
        System.out.println("Null salary: " +
                (one.containsKey("salary") && one.get("salary") == null));

        // List with zero rows returns size = 0.
        List<Map<String, Object>> empty =
                jdbc.queryForList("SELECT id FROM employee WHERE id < ?", 0L);
        System.out.println("No rows: " + empty.size());

        // queryForMap not found: exception.
        try {
            jdbc.queryForMap("SELECT id FROM employee WHERE id = ?", 999L);
        } catch (EmptyResultDataAccessException expected) {
            System.out.println("Missing: " +
                    expected.getClass().getSimpleName());
        }

        // queryForMap with multiple rows: exception.
        try {
            jdbc.queryForMap("SELECT id FROM employee ORDER BY id");
        } catch (IncorrectResultSizeDataAccessException expected) {
            System.out.println("Multiple: " +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Run inside `jdbc-map-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JdbcMapDemo
~~~

**Lines printed by the program** (excluding build tool logs, if any):

~~~text
Rows: 3
First: An
First id: 1
Names: [An, Binh, Chi]
One row: Binh
Null salary: true
No rows: 0
Missing: EmptyResultDataAccessException
Multiple: IncorrectResultSizeDataAccessException
~~~

### 9.4. Why Does Stdout Match This?

1. `JdbcTemplate` creates the in-memory H2 table and writes three rows with IDs 1, 2, and 3. `DriverManagerDataSource` opens a new connection each time, suitable for demos, without production connection pooling.
2. `queryForList(projection + " ORDER BY id")` returns three maps. Aliases are quoted in H2; accessing `employee_name` on the first row yields `"An"`. `employee_id` is a numeric value, so it converts via `Number.longValue()` and prints 1.
3. `queryForList(..., String.class)` selects only `name`, with ordering guaranteed by `ORDER BY id`, so the list prints `[An, Binh, Chi]`.
4. `queryForMap(... WHERE id = 2)` finds exactly one row. Key `employee_name` has value `"Binh"`; key `salary` is present with value null due to SQL NULL.
5. `queryForList` with `id < 0` matches 0 rows, giving an empty list.
6. `queryForMap` with `id = 999` finds no rows and throws `EmptyResultDataAccessException`.
7. `queryForMap` without `WHERE` returns three rows, violating the one-row contract and throwing `IncorrectResultSizeDataAccessException`.

The example intentionally **does not print `Map.toString()` directly** to avoid depending on exact numeric types or key casing/order supplied by JDBC/driver metadata.

### 9.5. Experiments to Deepen Understanding

**Experiment A:** Replace `queryForList("SELECT name ...", String.class)` with a two-column query `SELECT id, name` while still passing `String.class`. The single-column mapper will report an invalid column count.

**Experiment B:** Change `SELECT id AS "employee_id"` to `SELECT id AS "id"` while still calling `get("employee_id")`. Without the matching key, you may receive null. This is why aliases should be treated as part of the data contract.

**Experiment C:** Remove `ORDER BY` while still treating `rows.get(0)` as "the employee with the smallest ID". Databases do not guarantee row order without ordering; restore `ORDER BY` whenever order matters.

**Experiment D:** Change the single-row lookup from `WHERE id = 2` to `WHERE salary IS NULL`. If the table has multiple rows with null salary, `queryForMap` will throw a cardinality error. Queries must reflect truly unique business conditions.

**Experiment E:** Query without the `salary` column and check `containsKey("salary")`. The outcome differs from a row having the `salary` column with SQL NULL; the two cases should not be collapsed into a single error.

## 10. Performance and Safety When Using Maps

### 10.1. Do Not Read Unbounded Rows into Memory

`queryForList` materializes every row into a list and every row into a map. If SQL returns 500,000 rows with many columns, memory and allocation overhead can be huge. Use `WHERE`, project only needed columns, and apply database-appropriate pagination/`LIMIT`.

For large data processing or streaming, consider `RowCallbackHandler`, `ResultSetExtractor`, batch reading, or cursors matching connection and transaction lifecycles. Do not treat `queryForList` as a streaming API merely by iterating over the returned list: the data has already been eagerly loaded.

### 10.2. SQL Injection and Parameter Binding

Correct:

~~~java
List<Map<String, Object>> found = jdbcTemplate.queryForList(
    "SELECT id, name FROM employee WHERE name = ?", suppliedName);
~~~

Wrong:

~~~java
// Never concatenate user data directly into SQL.
String sql = "SELECT id FROM employee WHERE name = '" +
        suppliedName + "'";
~~~

`?` is for **values**; never use it to bind table/column names or `ORDER BY` direction. For user-chosen column names, use an allowlist in code instead of interpolating arbitrary strings.

### 10.3. Choose Transactions per Business Need

`queryForList` and `queryForMap` are query APIs and do not automatically open transactions spanning multiple business steps. If a service must read and then update under concurrency constraints, configure appropriate transaction boundaries, isolation, and locking. Mapping to a Map or DTO does not change database commit/rollback semantics.

### 10.4. Do Not Pass Maps Straight Through All Layers for Fixed Schemas

When maps are used to build JSON/CSV or DTOs, standardize key names, nullability, date-time/currency types, conversions, and validation. Maps fit dynamic projections well; for stable structures, creating DTOs/records and `RowMapper`s makes code easier to refactor and test.

### 10.5. Returning the Right Row Count Matters More Than "Making It Run"

With `queryForMap`, throwing a multi-row error can reveal incomplete SQL conditions or a missing uniqueness constraint in the database. Using `LIMIT 1` to hide a uniqueness violation can silently corrupt business data. Decide the right row count for the use case and pick the matching API.

## 11. Common Errors and Diagnostic Approach

| Symptom | Cause | Fix |
| --- | --- | --- |
| `EmptyResultDataAccessException` from `queryForMap` | 0 rows | Check condition, decide if not-found is acceptable |
| `IncorrectResultSizeDataAccessException` from `queryForMap` | Multiple rows | Fix uniqueness/WHERE or switch to `queryForList` |
| `IncorrectResultSetColumnCountException` | `queryForList(sql, Class<T>)` received multi-column SQL | SELECT only one column, or switch to `RowMapper` |
| `ClassCastException` when reading a map | JDBC value has a different runtime type than assumed | Check actual type, convert explicitly |
| `row.get("name")` is null | Wrong alias name, column not selected, or SQL NULL | Check `containsKey` and projection |
| JOIN loses an `id` column | Two columns share the same label | Assign distinct aliases |
| First row is unstable | Missing `ORDER BY` | Choose deterministic ordering with a tie-breaker when needed |
| Query uses excessive RAM | Map list is too large | Filter, paginate, select fewer columns, or stream |
| Query fails with `DataAccessException` | SQL, schema, connection, or conversion error | Inspect root cause and SQL/parameters; do not blame maps blindly |

**Practical debugging workflow:**

1. Run the SQL with the same parameters in a test environment to verify **row count and column count**.
2. Check the API: `queryForMap` requires one row; `queryForList(sql, Class<T>)` requires one column.
3. Inspect alias names and runtime types in test environments without logging sensitive data in production logs.
4. Distinguish SQL NULL from a missing key.
5. Check `ORDER BY`, pagination, and data scale.
6. If multiple layers depend on fixed map keys, migrate to a DTO/`RowMapper` and test the mapping.

## 12. Knowledge Check

**Question 1:** What Java return type does `queryForList("SELECT id, name FROM employee")` produce?  
**Answer:** `List<Map<String, Object>>`: each row is a map from column label to value.

**Question 2:** What return type does `queryForList("SELECT name FROM employee", String.class)` produce?  
**Answer:** `List<String>`, because the `Class<T>` overload uses a single-column mapper.

**Question 3:** Does `queryForMap` return an empty map when there are no rows?  
**Answer:** No, it throws `EmptyResultDataAccessException`.

**Question 4:** Does `queryForMap` pick the first row when there are three rows?  
**Answer:** No, it throws `IncorrectResultSizeDataAccessException`.

**Question 5:** Why does `row.get("salary") == null` not prove `salary` is SQL NULL?  
**Answer:** The `salary` key might be absent. Use `containsKey` to distinguish the two cases.

**Question 6:** Can `queryForList(sql, Employee.class)` map two columns `id` and `name` into an `Employee` record?  
**Answer:** No. That form requires a single scalar column; you need `RowMapper<Employee>`.

**Question 7:** Two joined tables both have an `id` column; how do you avoid losing data in the map?  
**Answer:** Choose distinct aliases such as `employee_id` and `department_id`.

**Question 8:** Why does map mapping lack domain type safety compared to DTOs?  
**Answer:** The compiler cannot check string keys or `Object` runtime types, making alias/null/cast errors easier.

**Question 9:** When using `queryForList` with hundreds of thousands of results, what must you watch out for?  
**Answer:** Memory usage, pagination/projection, streaming needs, and resource lifecycles.

**Question 10:** Does `queryForMap` automatically manage business transactions?  
**Answer:** No. It selects and maps results; transactions belong to separate configuration and transaction boundaries.

## 13. References

- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, parameter binding, map and typed queries.
- [JdbcTemplate Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `queryForList`/`queryForMap` overloads.
- [ColumnMapRowMapper Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/ColumnMapRowMapper.html): mapping each `ResultSet` row into a map.
- [SingleColumnRowMapper Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/SingleColumnRowMapper.html): mapping one column to a Java scalar value.

**Key takeaway:** `queryForList` returns a list of maps when `elementType` is omitted; `queryForMap` requires exactly one row; `queryForList` with `elementType` returns a list of single-column scalars. Use maps for flexible projections, and use `RowMapper`/DTOs when data represents a stable domain contract.
