# BeanPropertySqlParameterSource: Reading SQL Parameter Values from Java Objects

## 1. Lesson Objectives

In Java applications using Spring JDBC, SQL statements often need data from a DTO, command object, or search criteria object: customer ID, display name, points, status, updated timestamp, etc. With regular `JdbcTemplate`, you bind values positionally using `?`. With `NamedParameterJdbcTemplate`, you can write named parameters such as `:customerId` and `:displayName`. In that context, `BeanPropertySqlParameterSource` **reads parameter values from the readable properties of a Java object**, avoiding manual name–value pair construction.

This lesson belongs to the **Named Parameters** section of Spring Framework Data Access and focuses specifically on this mechanism; it does not replace general JDBC or ORM material.

After this lesson, you should be able to:

1. Explain the relationship between `NamedParameterJdbcTemplate`, `SqlParameterSource`, and `BeanPropertySqlParameterSource`.
2. Write a JavaBean with proper getters and pass the object into an `INSERT`, `UPDATE`, or `SELECT` using `:parameterName`.
3. Distinguish **Java property names** (`displayName`) from **SQL column names** (`display_name`); know when `MapSqlParameterSource` should be used instead.
4. Understand `hasValue`, `getValue`, `getParameterNames`, `getSqlType`, `registerSqlType`, and the semantics of `null`.
5. Use a list of objects for `batchUpdate` via `SqlParameterSourceUtils.createBatch`.
6. Avoid common mistakes: fields without proper accessors, mismatched parameter names, assuming the object is copied/snapshotted, mixing named parameters with identifiers, and handling null/enum/SQL types carelessly.
7. Run a **Java 17 + Spring Framework + H2** project to observe bound values, update counts, and query results.

## 2. From Positional Parameters to Named Parameters

### 2.1. JdbcTemplate Using Question Marks

Example:

```java
jdbcTemplate.update(
        "UPDATE customers SET display_name = ?, age = ? WHERE id = ?",
        input.getDisplayName(),
        input.getAge(),
        input.getId());
```

If the SQL changes placeholder order, the Java call must change to match. In statements with multiple columns of similar types, accidentally swapping two arguments can still succeed while writing the wrong data.

### 2.2. NamedParameterJdbcTemplate Using :name

The same operation:

```java
String sql = """
        UPDATE customers
        SET display_name = :displayName,
            age = :age
        WHERE id = :id
        """;

SqlParameterSource params = new BeanPropertySqlParameterSource(input);
int changed = namedParameterJdbcTemplate.update(sql, params);
```

Meaning:

- `:displayName`, `:age`, and `:id` are **named parameters** in the SQL statement.
- `BeanPropertySqlParameterSource(input)` supplies values for these names via readable properties of `input`.
- `NamedParameterJdbcTemplate` parses the SQL, converts named parameters into appropriate JDBC bindings, and sends values to the driver through prepared-statement infrastructure.
- **Property names** must match **named parameter names**; table/column names in SQL can follow an entirely different naming convention.
- `update(...)` returns the affected row count, not an SQL return value.

This is a snippet inside a method that already has `input`, `namedParameterJdbcTemplate`, and the proper imports. Section 8 provides a complete standalone runnable application.

### 2.3. Data Flow Diagram

```text
Java object input
 ├─ getId()           → 101L
 ├─ getDisplayName()  → "Lan"
 └─ getAge()          → 25
         │
         ▼
BeanPropertySqlParameterSource
         │ implements SqlParameterSource
         ▼
NamedParameterJdbcTemplate
         │ SQL: INSERT ... VALUES (:id, :displayName, :age)
         │ binding value/type to prepared statement
         ▼
JDBC driver → relational database
```

**Not an ORM:** `BeanPropertySqlParameterSource` does not perform entity tracking, SQL generation, schema migration, lazy loading, or automatic persistence of a bean to a table. It is solely a **source of values and type metadata for parameters that your own SQL requires**.

## 3. Essential APIs and Contracts

Spring Framework package:

```java
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
```

`BeanPropertySqlParameterSource` implements `SqlParameterSource` and extends `AbstractSqlParameterSource`. It uses property access (Spring's `BeanWrapper`) to read an object passed to its constructor.

### 3.1. Creating the Parameter Source

```java
CustomerInput input = new CustomerInput(101L, "Lan", null, true);
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(input);
```

The source object does not need to implement any special interface. Typically, you write standard JavaBeans getters (`getId()`, `getDisplayName()`, `getAge()`, `isActive()`). Spring Framework 6.2 also supports record components with matching accessors; still verify behavior in your exact version, especially with generated DTOs or proxy tools.

### 3.2. hasValue(String paramName)

`hasValue("displayName")` indicates whether the object provides a readable property with that name. **A property that exists with a null value still counts as "having a defined value" under the parameter source contract**:

```java
source.hasValue("id");           // true
source.hasValue("age");          // true, even though getAge() returns null
source.hasValue("display_name"); // false, because the getter is getDisplayName()
```

`hasValue` is not a "non-null" or "business-valid" check. Use validation for required fields; do not rely on `hasValue` to validate input.

### 3.3. getValue(String paramName)

`getValue` reads the property's value:

```java
Object id = source.getValue("id");                 // 101L
Object name = source.getValue("displayName");      // "Lan"
Object age = source.getValue("age");               // null
```

If the property name does not exist or is unreadable, the call may throw `IllegalArgumentException` or cause a parameter error when executing the SQL. **Do not catch this error and bind null**, because a wrong name like `:display_name` is completely different from a valid `age=null` value.

### 3.4. getSqlType(String paramName) and SQL Types

`BeanPropertySqlParameterSource` can infer a default SQL type from the property's declared type; for example, `Integer` typically maps to `java.sql.Types.INTEGER`. If a type is specialized or the database driver handles null ambiguously, you can register it explicitly:

```java
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(input);
source.registerSqlType("age", java.sql.Types.INTEGER);
```

`registerSqlType` comes from `AbstractSqlParameterSource`. You can also call `registerTypeName` when a database requires a specific type name. Do not assume Java type inference handles enums, JSON, UUIDs, arrays, proprietary types, or SQL NULL perfectly across every driver.

### 3.5. getParameterNames()

`getParameterNames()` returns the parameter names the source can enumerate; useful for inspection or integration with `SimpleJdbcInsert`/`SimpleJdbcCall` in certain scenarios. Avoid printing all name–value pairs (`source.toString()`) into production logs because objects may contain tokens, emails, personal data, or secrets.

**Contract summary:**

| Method | Return / Role | Notes |
| --- | --- | --- |
| `hasValue("name")` | Whether a readable property exists by that name | Can still be true for null |
| `getValue("name")` | Current value from the object | A wrong name must not be treated as a valid null |
| `getSqlType("name")` | SQL type from declaration or registration | May be `TYPE_UNKNOWN` |
| `getTypeName("name")` | SQL type name if registered | Not the Java class name |
| `getParameterNames()` | List of parameter names the source can supply | Not all of them are necessarily used in the SQL |
| `registerSqlType(name, type)` | Attaches an explicit JDBC SQL type | Needed for certain drivers/nulls/special types |
| `registerTypeName(name, typeName)` | Database-specific type name | Only when required by DB/driver |

## 4. JavaBean Properties Differ from Java Fields and SQL Columns

Simple class example:

```java
public class CustomerInput {
    private long id;
    private String displayName;
    private Integer age;
    private boolean active;

    public long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Integer getAge() { return age; }
    public boolean isActive() { return active; }
}
```

Readable names by JavaBean convention are `id`, `displayName`, `age`, and `active`. They are **not** `getId`, `getDisplayName`, or `display_name`.

### 4.1. Naming SQL Columns and Parameter Names Independently

```sql
INSERT INTO customers (id, display_name, age, active)
VALUES (:id, :displayName, :age, :active);
```

| Element | Actual Name | Meaning |
| --- | --- | --- |
| Database column | `display_name` | Column name in the schema |
| Java property | `displayName` | Accessed via `getDisplayName()` |
| Named parameter in SQL | `:displayName` | Looks up `source.getValue("displayName")` |
| `ResultSet` when querying | `getString("display_name")` | Reads SELECT column label, **unrelated** to BeanPropertySqlParameterSource |

**Common mistake:**

```sql
-- WRONG if the object only has property displayName:
INSERT INTO customers (display_name) VALUES (:display_name);
```

`BeanPropertySqlParameterSource` does not apply **`BeanPropertyRowMapper`**'s `snake_case` conversion automatically to named parameters. Choose `:displayName`, or use `MapSqlParameterSource("display_name", input.getDisplayName())` if the SQL must keep that name.

### 4.2. Only a Field Without a Getter?

A class with `private String displayName` and no proper accessor may not expose `displayName` as a readable JavaBean property. Even when the field exists, `BeanPropertySqlParameterSource` is not a tool for reading arbitrary private fields.

If you need different access semantics for raw fields/records/beans, Spring 6.2 provides `SimplePropertySqlParameterSource` with its own support scope. Do not switch to it just to bypass validation or mask a poorly designed DTO; prefer proper getters, records, or an appropriate Map source first.

### 4.3. Beans Do Not Necessarily Need Setters

To **read** parameters, a JavaBean only needs getters; an immutable input with `final` fields and public getters works fine. This differs from output mappers mapping **results** into a JavaBean, where writing through setters or constructors matters.

### 4.4. Booleans, Acronyms, Nested Properties

- `isActive()` normally creates property `active` of type `boolean`.
- `getEnabled()` creates `enabled` when following getter conventions.
- Names with acronyms like `getURL()` may yield a JavaBeans property name other than `url` as expected; verify names against JavaBeans rules and `getParameterNames()`.
- For nested objects, paths like `customer.address.city` should only be used when the property accessor and SQL parser handle them cleanly and every intermediate level is non-null; in foundational code, **prefer flat DTOs** with clear parameter names.

## 5. Comparing BeanPropertySqlParameterSource, MapSqlParameterSource, and Direct Maps

### 5.1. From an Object: BeanPropertySqlParameterSource

```java
SqlParameterSource args =
        new BeanPropertySqlParameterSource(customerInput);
namedParameterJdbcTemplate.update("""
        UPDATE customers SET display_name = :displayName
        WHERE id = :id
        """, args);
```

Suitable when SQL uses many names matching the object's readable properties; reduces boilerplate and is convenient for object batches.

### 5.2. From Explicit Values: MapSqlParameterSource

```java
SqlParameterSource args = new MapSqlParameterSource()
        .addValue("customer_id", customerInput.getId())
        .addValue("display_name", customerInput.getDisplayName());

namedParameterJdbcTemplate.update("""
        UPDATE customers SET display_name = :display_name
        WHERE id = :customer_id
        """, args);
```

Suitable when:

- SQL parameter names intentionally differ from Java property names;
- You only want to bind an explicitly chosen subset;
- You need computed values or intentional defaults;
- There are dynamic parameters or types needing explicit registration.

`MapSqlParameterSource.addValue` also has overloads accepting SQL types, letting you bind `NULL` with a specific type right where parameters are built. With only one or two parameters, `MapSqlParameterSource` can be clearer than creating a temporary bean.

### 5.3. Using Map<String, ?> Directly

Many overloads of `NamedParameterJdbcTemplate` accept `Map<String, ?>`:

```java
Map<String, Object> values = Map.of(
        "id", customerInput.getId(),
        "displayName", customerInput.getDisplayName());

namedParameterJdbcTemplate.update(
        "UPDATE customers SET display_name = :displayName WHERE id = :id",
        values);
```

Note **`Map.of` does not accept null keys or values**; when binding `null`, use `MapSqlParameterSource` or a null-permitting Map implementation. For specialized SQL types, `SqlParameterSource` expresses type metadata more clearly.

### 5.4. Do Not Confuse with BeanPropertyRowMapper

| Tool | Data Direction | Input | Output |
| --- | --- | --- | --- |
| `BeanPropertySqlParameterSource` | Java object → SQL parameter | JavaBean/record property | `SqlParameterSource` values to bind |
| `MapSqlParameterSource` | Map/explicit values → SQL parameter | Named key/value | `SqlParameterSource` |
| `BeanPropertyRowMapper<T>` | JDBC ResultSet → Java object | ResultSet column label | JavaBean properties |
| `DataClassRowMapper<T>` | JDBC ResultSet → class/record | Row + column label | Object with constructor/record support |
| `NamedParameterJdbcTemplate` | SQL + parameter source → JDBC statement | Named SQL + parameter source | Row count / row / result object |

`BeanPropertySqlParameterSource` **does not create a `RowMapper` and does not dictate how results are read**. Within one method, you can use it to bind `WHERE` parameters and use a separate `RowMapper` to map returned columns.

## 6. Practical SQL Patterns

### 6.1. INSERT from an Input Object

```java
String sql = """
        INSERT INTO customers (id, display_name, age, active)
        VALUES (:id, :displayName, :age, :active)
        """;
int affected = named.update(
        sql, new BeanPropertySqlParameterSource(input));
```

Validate schema constraints, IDs, and input data; successful binding does not mean the data is business-valid.

### 6.2. UPDATE from a Command Object

```java
String sql = """
        UPDATE customers
        SET display_name = :displayName, age = :age
        WHERE id = :id
        """;
int changed = named.update(
        sql, new BeanPropertySqlParameterSource(change));
```

**Always check `changed`** when business rules require exactly one record. If 0, the ID may not exist; if greater than 1, the `WHERE` condition or schema may be wrong. A parameter name repeated in SQL is bound from the same property name—no need to duplicate values into an array.

### 6.3. Conditional SELECT from an Object

```java
String sql = """
        SELECT id, display_name, age, active
        FROM customers
        WHERE active = :active
          AND age >= :minimumAge
        ORDER BY id
        """;

List<CustomerView> result = named.query(
        sql,
        new BeanPropertySqlParameterSource(filter),
        (rs, rowNum) -> new CustomerView(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getObject("age", Integer.class),
                rs.getBoolean("active")));
```

This is an illustrative snippet, requiring a `CustomerView` class/record and `filter` with getters `isActive()` and `getMinimumAge()`. SQL `display_name` is a **column label** for the output mapper, whereas `:minimumAge` is an **input property name**. The two mapping directions are independent.

### 6.4. Same Parameter Appearing Multiple Times

```sql
SELECT id, display_name
FROM customers
WHERE display_name = :keyword
   OR nickname = :keyword;
```

The object only needs one `getKeyword()` getter. `NamedParameterJdbcTemplate` parses both occurrences and binds the same value. Never write string concatenation `"WHERE name = '" + keyword + "'"` due to SQL injection and escaping bugs.

### 6.5. IN (:ids) and Lists

Example:

```java
String sql = "SELECT id, display_name FROM customers WHERE id IN (:ids)";
SqlParameterSource parameters =
        new MapSqlParameterSource("ids", List.of(1L, 2L, 3L));
List<Long> ids = named.query(
        sql, parameters,
        (rs, rowNum) -> rs.getLong("id"));
```

`NamedParameterJdbcTemplate` supports expanding a list of values for `IN` in documented cases; an input JavaBean can also expose a readable property holding a collection. However:

- **Empty lists** can produce invalid or database-dependent `IN ()` SQL. Handle empty lists proactively in the service/DAO, e.g., returning an empty list before querying when business rules allow.
- For very large lists, databases may limit bind variables, SQL length, or query plan efficiency; consider chunking, temp tables, or an alternative query.
- **`?`/`:name` only binds values**, never table names, column names, SQL keywords, `ORDER BY` directions, or aliases. For dynamic identifiers, use a strict allowlist.

## 7. NULL, SQL Types, and Object Lifecycle

### 7.1. Property Exists with a Null Value

A JavaBean:

```java
public Integer getAge() {
    return null;
}
```

still has property `age`; `BeanPropertySqlParameterSource.hasValue("age")` is true. If SQL allows `age=NULL`, the driver can bind null; if the column is `NOT NULL`, the database will reject it. **Do not confuse a missing property with a null property**:

| Case | `hasValue("age")` | `getValue("age")` | Conclusion |
| --- | --- | --- | --- |
| Has `getAge()`, returns 25 | true | 25 | Normal value binding |
| Has `getAge()`, returns null | true | null | Binds SQL NULL if driver/type/schema permits |
| No readable property `age` | false | Access error | SQL ↔ object name contract mismatch |

### 7.2. SQL Type of NULL

Some drivers/databases need an explicit SQL type when binding null. `BeanPropertySqlParameterSource` can infer it from the declared property type, or you can register it:

```java
BeanPropertySqlParameterSource params =
        new BeanPropertySqlParameterSource(input);
params.registerSqlType("age", java.sql.Types.INTEGER);

named.update("""
        UPDATE customers SET age = :age WHERE id = :id
        """, params);
```

Do not pick `Types.VARCHAR` for an `INTEGER` column merely so a query "happens to run on H2". For `UUID`, JSON, SQL ARRAY, or enums determined by the driver, you may need an SQL type/typeName or explicit conversion. Integration tests should run on a database/driver close to production.

### 7.3. The Object Is Not an Immutable Snapshot

`BeanPropertySqlParameterSource` **wraps the object** and reads properties via accessors when requested. It does not make an immutable copy of all fields at construction time. If the object is mutated between parameter source creation and SQL execution (or modified by another thread), getters may return inconsistent values.

Best practices:

- Use immutable DTOs or avoid mutating them during a database operation.
- Give each operation/batch item its own scoped input rather than reusing a mutable object across requests.
- Do not pass the same mutable input bean into multiple threads for concurrent binding.
- Do not perform network/API calls or side-effecting business logic inside getters; getters should be fast, deterministic, and side-effect-free.

### 7.4. Avoid Binding Complex Objects Directly

`getValue("address")` may return a Java `Address` object, but the JDBC driver does not know how to split it into multiple columns automatically. If the database has `street` and `city` columns, flatten the input into readable properties `getStreet()`/`getCity()` or use `MapSqlParameterSource` to pick the values to bind. Do not confuse **reading a property value** with **serializing arbitrary objects to SQL**.

## 8. Standalone Java 17 Project: Demonstrating Binding and Batching

Uses **Java 17+**, **Spring Framework 6.2.14**, **H2 2.3.232**, and Gradle. The example runs with a simple Spring IoC container, **requiring no Spring Boot, HTTP server, or separately installed database**.

### 8.1. File Structure

```text
bean-property-params-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanPropertyParamsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-property-params-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.BeanPropertyParamsDemo'
}
```

`src/main/java/demo/BeanPropertyParamsDemo.java`:

```java
package demo;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class BeanPropertyParamsDemo {

    // Immutable input with public getters: no public setters needed.
    public static class CustomerInput {
        private final long id;
        private final String displayName;
        private final Integer age;
        private final boolean active;

        public CustomerInput(long id, String displayName,
                             Integer age, boolean active) {
            this.id = id;
            this.displayName = displayName;
            this.age = age;
            this.active = active;
        }

        public long getId() {
            return id;
        }

        public String getDisplayName() {
            return displayName;
        }

        public Integer getAge() {
            return age;
        }

        public boolean isActive() {
            return active;
        }
    }

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:bean_params;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        NamedParameterJdbcTemplate namedParameterJdbcTemplate(
                DataSource dataSource) {
            return new NamedParameterJdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            NamedParameterJdbcTemplate named =
                    context.getBean(NamedParameterJdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE customers (
                        id BIGINT PRIMARY KEY,
                        display_name VARCHAR(100) NOT NULL,
                        age INTEGER NULL,
                        active BOOLEAN NOT NULL
                    )
                    """);

            CustomerInput lan = new CustomerInput(
                    1L, "Lan", null, true);
            CustomerInput minh = new CustomerInput(
                    2L, "Minh", 23, false);

            BeanPropertySqlParameterSource source =
                    new BeanPropertySqlParameterSource(lan);

            // Read properties by JavaBean name, not SQL column name.
            System.out.println("name=" +
                    source.getValue("displayName"));
            System.out.println("hasAge=" +
                    source.hasValue("age"));
            System.out.println("hasSnakeCase=" +
                    source.hasValue("display_name"));
            System.out.println("ageType=" +
                    (source.getSqlType("age") == Types.INTEGER));

            // Bind two objects using the same SQL statement.
            String insertSql = """
                    INSERT INTO customers (id, display_name, age, active)
                    VALUES (:id, :displayName, :age, :active)
                    """;
            SqlParameterSource[] batch =
                    SqlParameterSourceUtils.createBatch(List.of(lan, minh));
            int[] inserted = named.batchUpdate(insertSql, batch);
            System.out.println("batch=" + Arrays.toString(inserted));

            // Lan's age getter returns null => SQL NULL, not a missing
            // age parameter name.
            Integer ageBefore = named.queryForObject(
                    "SELECT age FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    Integer.class);
            System.out.println("initialAgeNull=" + (ageBefore == null));

            // Use an updated object for UPDATE: id, displayName, age.
            CustomerInput edited = new CustomerInput(
                    1L, "Lan Anh", 25, true);
            int updated = named.update("""
                    UPDATE customers
                    SET display_name = :displayName, age = :age
                    WHERE id = :id
                    """, new BeanPropertySqlParameterSource(edited));
            System.out.println("updated=" + updated);

            String nameAfter = named.queryForObject(
                    "SELECT display_name FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    String.class);
            Integer ageAfter = named.queryForObject(
                    "SELECT age FROM customers WHERE id = :id",
                    new MapSqlParameterSource("id", 1L),
                    Integer.class);
            System.out.println("after=" + nameAfter + ":" + ageAfter);

            // Named parameter used in SELECT. All columns are mapped
            // to Java objects by RowMapper before returning results.
            List<String> adults = named.query("""
                    SELECT display_name FROM customers
                    WHERE age >= :minimumAge
                    ORDER BY id
                    """, new MapSqlParameterSource("minimumAge", 18),
                    (rs, rowNum) -> rs.getString("display_name"));
            System.out.println("adults=" + adults);

            int activeAdults = named.queryForObject("""
                    SELECT COUNT(*) FROM customers
                    WHERE age >= :minimumAge AND active = :active
                    """,
                    new MapSqlParameterSource()
                            .addValue("minimumAge", 18)
                            .addValue("active", true),
                    Integer.class);
            System.out.println("activeAdults=" + activeAdults);
        }
    }
}
```

### 8.2. Running the Application

From the directory containing `build.gradle`, using a Java 17–compatible Gradle:

```bash
gradle run
```

If the project already has a Gradle Wrapper: on Linux/macOS run `./gradlew run`; on Windows run `gradlew.bat run`. The lines printed by the program's `System.out.println` calls (excluding Gradle logs) are:

```text
name=Lan
hasAge=true
hasSnakeCase=false
ageType=true
batch=[1, 1]
initialAgeNull=true
updated=1
after=Lan Anh:25
adults=[Lan Anh, Minh]
activeAdults=1
```

### 8.3. Matching Each Output Line

1. `name=Lan`: `getValue("displayName")` invokes the matching accessor on `lan`, returning `"Lan"`.
2. `hasAge=true`: the bean has getter `getAge()`, even though Lan's value is null.
3. `hasSnakeCase=false`: no readable property `display_name` exists; the SQL column `display_name` does not create a new Java property.
4. `ageType=true`: property `Integer age` is inferred as `Types.INTEGER`.
5. `batch=[1, 1]`: H2 returns one affected row per insert. JDBC in general may return special codes such as `Statement.SUCCESS_NO_INFO` in batches; this is the expected output on the H2 demo environment.
6. `initialAgeNull=true`: the first row holds `age = NULL`, because input `getAge()` returned null.
7. `updated=1`: UPDATE matched `id = 1` and changed the name to `Lan Anh` and age to 25.
8. `after=Lan Anh:25`: the query reads back data to verify the bound values.
9. `adults=[Lan Anh, Minh]`: both have age >= 18 after UPDATE; the query orders by `id`.
10. `activeAdults=1`: Lan Anh has active=true; Minh has active=false.

**What the demo proves:** a Java object with getters can serve as a binding source for multiple named parameters, including null values and batches; `JdbcTemplate`/`NamedParameterJdbcTemplate` remains responsible for acquiring and releasing JDBC resources. In the example, non-pooling `DriverManagerDataSource` is strictly for learning. Production should configure a proper pool, keep credentials outside source code, and use transactions whenever a business operation spans multiple writes that must commit/roll back together.

### 8.4. Controlled Modifications for Deeper Learning

- Change `:displayName` in SQL to `:display_name` while keeping the JavaBean: observe the error due to property mismatch; fix the SQL or switch to `MapSqlParameterSource`.
- Remove `getAge()`: `hasValue("age")` no longer satisfies the contract; named SQL `:age` can no longer obtain a value from that property.
- Try setting Lan's `age` to null in UPDATE: with a nullable column, H2 stores NULL; inspect `getSqlType` or call `registerSqlType("age", Types.INTEGER)` before updating.
- Try passing an empty list to `IN (:ids)` and guard it in the DAO before letting the driver process invalid SQL.
- Put two records with duplicate `id` keys in a batch and observe the constraint violation; to get atomic rollback across multiple changes, use a Spring transaction and test on a real database.

## 9. Object Batches: Mechanics and Limits

A production-friendly batch snippet:

```java
// inputs is a validated Collection<CustomerInput>.
SqlParameterSource[] batch =
        SqlParameterSourceUtils.createBatch(inputs);
int[] rowCounts = namedParameterJdbcTemplate.batchUpdate("""
        INSERT INTO customers (id, display_name, age, active)
        VALUES (:id, :displayName, :age, :active)
        """, batch);
```

`SqlParameterSourceUtils.createBatch(Collection<?>)` creates one `SqlParameterSource` per element; for bean objects, it uses the property-source mechanism, and for Maps it uses the corresponding Map source. This is convenient for inputs sharing a consistent property contract.

Points to remember:

- Every item must provide all parameters required by the SQL; one item missing a property can fail the entire batch.
- `batchUpdate` returns `int[]` per execution. JDBC permits special codes like `SUCCESS_NO_INFO`/`EXECUTE_FAILED` depending on the driver; never assume every element is always a positive count.
- A JDBC batch does not by default mean an application-defined atomic transaction. If all-or-nothing is required, wrap the operation in `@Transactional`/`TransactionTemplate` and test rollback.
- Never mutate a single mutable JavaBean in a loop while creating multiple parameter sources all pointing to **that same instance**. When the batch binds, elements may all read the object's final state. Create a separate object or valid snapshot per item.
- For very large datasets, consider batch sizes, driver/database limits, transaction duration, and memory instead of sending millions of items in a single batch.

A handy API: `SqlParameterSourceUtils.createBatch(Object...)` also accepts an array/varargs, while the Collection overload takes a collection. There is no need to write your own loop creating `BeanPropertySqlParameterSource` per item when the helper satisfies the contract.

## 10. Usage in Repositories and Spring Transactions

Place parameter sources in the data-access layer or repository adapter:

```java
@Repository
public class CustomerRepository {
    private final NamedParameterJdbcTemplate named;

    public CustomerRepository(NamedParameterJdbcTemplate named) {
        this.named = named;
    }

    public int update(CustomerChange change) {
        return named.update("""
                UPDATE customers
                SET display_name = :displayName, age = :age
                WHERE id = :id
                """, new BeanPropertySqlParameterSource(change));
    }
}
```

This snippet illustrates a repository; it requires defining `CustomerChange` with readable properties, importing `@Repository`, and enabling component scanning/bean registration; it is not part of the runnable demo in section 8. With Spring Boot, `NamedParameterJdbcTemplate` is typically auto-configured when conditions are met; with plain Spring Framework, declare the bean explicitly as in the demo.

**Transactions at the service layer:** if a business operation updates multiple tables, the transaction manager must use the same `DataSource` as the template. `BeanPropertySqlParameterSource` only supplies bind values—it does not begin, commit, or roll back transactions. Do not confuse it with an entity manager.

**Validation at the boundary:** before calling the DAO, verify valid IDs, non-empty/within-length `displayName`, `age` within business bounds, authorization to edit data, etc. An object having getters does not guarantee the database will accept its values.

## 11. Common Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Parameter `display_name` not found | SQL uses `:display_name`, bean only has `displayName` | Change to `:displayName` or use `MapSqlParameterSource` with the desired SQL key |
| `hasValue("age")` is false | Missing readable getter/accessor | Write standard getters, use a compatible record, or use another parameter source |
| `hasValue("age")` is true, DB fails NOT NULL | Getter returns null | Validate input or update schema/logic if null is valid |
| Query writes wrong values | Getter returns mutated value or mapper mixes fields | Use immutable inputs, check SQL properties, and test |
| SQL column `display_name` treated as property | Confusing schema column with `:namedParameter` | Name JavaBean parameters explicitly |
| Error binding enum/UUID/JSON/ARRAY | Driver does not understand object or SQL type | Convert/register SQL type/typeName, test on real driver |
| `Map.of` throws exception | Null values are disallowed in `Map.of` | Use `MapSqlParameterSource` or a null-permitting Map |
| Multiple batch items update the same final values | Reused one mutable bean across parameter sources | Create a separate object per item |
| Batch returns unexpected results | Driver returned special count or constraint failure | Check `int[]`, exceptions, and transactions |
| Spring reports missing `NamedParameterJdbcTemplate` bean | Not configured or auto-config inactive | Declare bean properly, check DataSource and dependencies |
| SQL injection despite parameters in WHERE | Concatenating identifiers, ORDER BY, or SQL fragments from input | Parameters only bind values; use an allowlist for identifiers |
| Query returns fewer rows than expected | Wrong WHERE condition or wrong input property | Inspect bound values, SQL, affected row counts, and DB tests |

### Distinguishing Three Key Error Types

1. **Wrong property name**: `:display_name` when the object only has `displayName`; caught immediately at the named-parameter/property-access layer.
2. **Valid null property**: `:age` exists but its value is null; what happens next depends on the schema and JDBC type.
3. **Right property name, invalid business value**: `age=-10` or `displayName=" "`; this is a validation/domain rule, not a `BeanPropertySqlParameterSource` bug.

## 12. Recommended Testing

Do not test `getValue` in isolation only; tests must prove SQL actually receives the right properties.

### 12.1. Unit Tests for Property Names

```java
CustomerInput sample = new CustomerInput(1L, "Lan", null, true);
BeanPropertySqlParameterSource source =
        new BeanPropertySqlParameterSource(sample);

assert source.hasValue("displayName");
assert !source.hasValue("display_name");
assert source.hasValue("age");
assert source.getValue("age") == null;
```

This illustrates assertion logic. Java `assert` can be disabled when `-ea` is omitted; in real test projects use JUnit/AssertJ and follow your test configuration.

### 12.2. Integration Tests for INSERT/UPDATE

- Create a table with SQL column `display_name`, input with `getDisplayName()`; run `INSERT ... :displayName` then `SELECT` to verify.
- Test `Integer age=null` on a nullable column; verify the database stores `NULL`, not 0.
- Test `UPDATE ... WHERE id=:id` returns 1; a non-existent ID must return 0 and be handled per repository contract.
- Test multi-item batches, verifying each item carries its own values rather than sharing one mutable object.
- Test rollback when two updates run in one service transaction and the second fails.
- Test on a production-like database/driver if using enums, UUIDs, JSON, ARRAYs, or special SQL NULLs.

### 12.3. Verifying the Right SQL Type

Where driver-supported, check that `getSqlType("age")` returns the expected type; for specialized properties, call `registerSqlType` and run an integration test against the actual column. Never assume Java `String` or `Object` is always the right SQL type for every piece of data.

### 12.4. Fail-Fast Tests for Missing Parameters

Create an input lacking `getDisplayName()` or intentionally place `:missingProperty` in SQL. The test must **fail with a clear message**, never silently bind null and write incomplete data. If catching exceptions, catch only at the appropriate boundary to report errors to logging/monitoring without exposing personal data.

## 13. Practice Exercises

**Exercise 1 — Convert positional parameters to named parameters.** Given:

```java
jdbcTemplate.update(
        "UPDATE customers SET display_name=?, active=? WHERE id=?",
        input.getDisplayName(), input.isActive(), input.getId());
```

Rewrite using `NamedParameterJdbcTemplate` and a `BeanPropertySqlParameterSource(input)`. Suggested SQL:

```sql
UPDATE customers
SET display_name = :displayName,
    active = :active
WHERE id = :id;
```

**Exercise 2 — Wrong property name.** SQL has `:display_name` while the object has `getDisplayName()`. Give two fixes: change the parameter to `:displayName` or supply `MapSqlParameterSource.addValue("display_name", ...)`.

**Exercise 3 — Distinguishing null and missing.** With `getAge()` returning null, explain why `hasValue("age")` is true while `hasValue("unknown")` is false. Bind SQL NULL into a nullable INTEGER column and verify with a query.

**Exercise 4 — Proper batch with two objects.** Write `createBatch(List.of(item1, item2))` then `batchUpdate` for SQL with `:id, :displayName, :age, :active`. Each item must have distinct data; inspect affected counts and DB rows.

**Exercise 5 — Avoiding shared mutable objects.** Create one mutable bean object, mutate its name in sequence, and construct two `BeanPropertySqlParameterSource` instances pointing to it. Explain why both sources may read the same final state and fix it with separate objects.

**Exercise 6 — When to use a Map?** A stored procedure or SQL statement requires parameter name `:p_customer_id` while the Java object only has `getId()`. Choose a Map source with matching keys or create an adapter DTO instead of forcing `BeanPropertySqlParameterSource` to guess naming conventions.

## 14. Code Review Checklist

1. Does SQL use `:name` or `?`; does the invoked template support named parameters?
2. Does every `:name` match a **readable JavaBean property/record component**, not just a private field/variable?
3. Are `display_name` (SQL column) and `displayName` (Java property) being confused?
4. Is null semantically valid; do the column and driver accept the right SQL type?
5. Is the input object immutable, or at least never mutated during binding?
6. Does SQL concatenate untrusted data/identifiers instead of binding values?
7. Does the batch create a separate source per input and run inside an appropriate transaction?
8. Do getters have side effects, slow operations, or unexpected exceptions?
9. Are affected row counts from `update` checked where business rules require exactly one row?
10. Do tests run against a real/compatible DB and driver rather than only mocking `SqlParameterSource`?
11. Is sensitive data printed via `toString()` or parameter logging?
12. Is output mapping handled by a proper `RowMapper` without confusing it with input parameter sources?

## 15. Summary

- `BeanPropertySqlParameterSource` turns **readable properties of a Java object** into value sources for **named SQL parameters**.
- Used with `NamedParameterJdbcTemplate`; SQL must still be written explicitly and `:propertyName` must match the property.
- `display_name` is a column name, `displayName` is a Java property, and `:displayName` is a named parameter: three distinct roles.
- A null property **does not mean the property is missing**. Check SQL types and DB constraints when binding NULL.
- Use `SqlParameterSourceUtils.createBatch` to create multiple sources from an input list; beware of mutable objects and transaction boundaries.
- Use `MapSqlParameterSource` when names/values need manual control; do not force bean property mapping onto every SQL statement.
- This is **data binding into SQL**, not an ORM—it does not perform validation, manage transactions, or map ResultSets to entities.

## 16. References

- Spring Framework 6.2 — NamedParameterJdbcTemplate and SqlParameterSource: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework 6.2 — BeanPropertySqlParameterSource API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/BeanPropertySqlParameterSource.html
- Spring Framework 6.2 — NamedParameterJdbcOperations API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcOperations.html
- Spring Framework 6.2 — SqlParameterSource and AbstractSqlParameterSource: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html
- Spring Framework 6.2 — SqlParameterSourceUtils: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSourceUtils.html
- Spring Framework — Providing SQL type information for parameters: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html

**Practical takeaway:** if your application has an input object with clear properties and SQL using named parameters matching those names, pass `new BeanPropertySqlParameterSource(input)` to `NamedParameterJdbcTemplate`. If renaming, conversion, or special value handling is needed, choose an explicit adapter/Map; never assume a bean source understands the database schema on its own.