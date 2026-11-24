# DataClassRowMapper for Types with Data Constructors

In Spring JDBC, **`DataClassRowMapper<T>`** is an implementation of `RowMapper<T>` that converts each `ResultSet` row into a Java object **using a data-accepting constructor**. It fits **Java records**, immutable DTOs, and classes whose constructor parameter names match or correspond to SQL column labels. The mapper can also combine a constructor with JavaBean setters for properties not handled by the constructor.

For example, a query returns:

| id | display_name | completed_orders |
| ---: | --- | ---: |
| 1 | Linh Tran | 3 |
| 3 | Mai Pham | 5 |

Java 17 DTO:

~~~java
public record CustomerSummary(
        long id, String displayName, int completedOrders) {
}
~~~

Query:

~~~java
List<CustomerSummary> results = jdbcTemplate.query(
        """
        SELECT id, display_name, completed_orders
        FROM customers
        WHERE completed_orders >= ?
        ORDER BY id
        """,
        DataClassRowMapper.newInstance(CustomerSummary.class),
        3);
~~~

This is an **integration snippet**: it requires `JdbcTemplate`, the `customers` table, and the record above. Column name `display_name` can match constructor parameter `displayName` under the snake_case/camelCase convention supported by Spring. Section 5 contains a complete Java 17+ program with build files and deterministic stdout.

**Core point:** `DataClassRowMapper` performs **row-to-object mapping**; it does not manage transactions, create database schemas, act as ORM/JPA, or construct parent–child relationships from multiple rows.

## 1. Lesson Objectives

After this lesson, you can:

1. Explain how `DataClassRowMapper` reads column names, identifies a constructor, converts JDBC values, and instantiates objects.
2. Choose between a Java 17 record, an immutable class, or a class combining constructor + setters.
3. Understand when `-parameters` must be enabled when compiling classes with ordinary constructors.
4. Write SQL aliases matching constructor parameter names, e.g., `full_name AS display_name` for `displayName`.
5. Read data with `JdbcTemplate.query(...)` and `queryForObject(...)`, distinguishing an empty list from cardinality errors.
6. Handle SQL `NULL`, primitives/wrappers, numeric types, date/time, conversions, and constructor validation.
7. Compare `DataClassRowMapper` with `BeanPropertyRowMapper` and hand-written `RowMapper`.
8. Recognize limitations: nested objects, one-to-many joins, performance, non-static inner classes, and missing parameter-name metadata.
9. Write integration tests verifying constructor mapping and schema mismatches on an appropriate driver.

## 2. How Does DataClassRowMapper Work?

`DataClassRowMapper<T>` lives in package `org.springframework.jdbc.core`; this class **extends `BeanPropertyRowMapper<T>`** and is a `RowMapper<T>`. Spring calls `mapRow(rs, rowNum)` for each row in the query result. The mapper looks to construct the target via a suitable constructor, maps values from SQL columns to parameters by **name**, and then assigns any remaining properties via setters if present.

~~~text
Repository / DAO
   |
   +--> JdbcTemplate.query(SQL, mapper, args...)
             |
             v
          JDBC ResultSet
             |
             +--> row 0
             |    +--> match SQL column labels to parameter names
             |    +--> read/convert values for each constructor argument
             |    +--> invoke constructor: CustomerSummary(...)
             |    +--> assign remaining writable properties if any
             |
             +--> row 1 -> another CustomerSummary(...)
             |
             +--> ...
             |
             v
        List<CustomerSummary>
~~~

### Who Is Responsible for What?

| Component | Responsibility |
| --- | --- |
| `DataSource` | Supplies `Connection`s, possibly via a pool |
| `JdbcTemplate` | Binds SQL parameters, executes query, iterates rows, manages JDBC resources, translates `SQLException` |
| `DataClassRowMapper` | Converts **one positioned row** into an instance of `T` |
| DTO/record constructor | Receives data and can enforce object invariants |
| Remaining setters | Populate properties not mapped by the constructor if the target permits |
| Repository method | Defines SQL, filter criteria, sorting, returns `List<T>`/single object |

`RowMapper` does not call `rs.next()` itself. `JdbcTemplate` controls cursor advancement; the mapper only reads the current row. Each row is mapped to one object; if the query returns no rows, `query(...)` returns an empty list and the mapper does not run.

**Do not confuse with JPA:** Objects created by `DataClassRowMapper` are not tracked by an EntityManager and have no dirty checking, lazy loading, or cascading. `@Entity`/`@Column` do not automatically change aliases/mapping in this JDBC mapper. When mapping SQL, the query itself and the Java type form the primary contract.

## 3. Requirements on Target Types and Constructors

Spring documentation requires the target to be a **top-level class** or **static nested class**. A valid target may have:

- A data-class constructor with parameters named to match column labels;
- JavaBean-style property setters;
- Or a combination of both.

### 3.1. Java Record: The Cleanest Case

~~~java
public record OrderSummary(
        long id,
        String customerName,
        int itemCount) {
}
~~~

SQL:

~~~sql
SELECT
    o.id,
    c.name AS customer_name,
    COUNT(i.id) AS item_count
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
GROUP BY o.id, c.name
ORDER BY o.id
~~~

This is **illustrative SQL**, requiring tables `orders`, `customers`, and `order_items`. The record's canonical constructor has components `id`, `customerName`, and `itemCount`, matching columns `id`, `customer_name`, and `item_count`.

Java records expose record component names at runtime as a language feature; Spring can obtain the metadata needed to invoke the canonical constructor. Since records have no ordinary setters, the “invoke constructor then fill remaining properties” approach fits far better than `BeanPropertyRowMapper`'s no-arg constructor and setter requirement.

Immutable records help prevent accidental DTO mutation after mapping; however, that does not mean SQL data is always valid. A constructor may reject invalid data, and the application must handle errors appropriately.

### 3.2. Immutable Class with a Data Constructor

~~~java
public final class CustomerCard {
    private final long id;
    private final String displayName;

    public CustomerCard(long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public long id() {
        return id;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

With a query returning columns `id` and `display_name`, `DataClassRowMapper.newInstance(CustomerCard.class)` can invoke the constructor above **if Spring knows the parameter names `id` and `displayName`** at runtime.

**Very important build note:** Java reflection does not necessarily retain the parameter names of an ordinary constructor when compiled with default `javac`. For classes like `CustomerCard`, enable **`-parameters`**:

~~~bash
javac -parameters CustomerCard.java
~~~

This `javac` command illustrates compiling Java sources independently of Spring. In real applications, the build configuration of the module containing the DTO must ensure the corresponding metadata is preserved.

Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Maven compiler plugin (snippet inside configuration):

~~~xml
<configuration>
    <release>17</release>
    <parameters>true</parameters>
</configuration>
~~~

Without `-parameters` or compatible metadata, Spring may see parameter names like `arg0`/`arg1` instead of `id`/`displayName`, and cannot match them reliably against column names. Do not look solely at source code names and assume those names survive in the production build artifact.

### 3.3. Static Nested Class vs. Non-Static Inner Class

~~~java
public class Views {
    public static record Summary(long id, String name) {}

    public static final class Card {
        private final long id;

        public Card(long id) {
            this.id = id;
        }
    }
}
~~~

`Views.Summary` and `Views.Card` are static nested types that can serve as targets when constructors/mappings match. A **non-static inner class** holds an implicit reference to the outer instance and is not among the targets recommended/supported by `DataClassRowMapper`. Use top-level DTOs or static nested DTOs, especially when placing DTOs inside a test/demo class.

### 3.4. Which Constructor Is Selected?

Spring must determine a **suitable resolvable constructor** for the target. Records normally have an unambiguous canonical constructor. For regular classes with multiple constructors (default, overloaded, or library-generated), selection can be unpredictable or mismatch the data-class contract. When designing DTOs for mapping:

- Prefer a single clear data constructor;
- Avoid overloaded constructors with the same parameter count but different meanings;
- Ensure parameter-name metadata is preserved;
- Check access modifiers/module boundaries if reflection cannot invoke the constructor;
- Write integration tests against the actual compiled build rather than relying only on the IDE.

Do not “fix” things by adding a no-arg constructor just to make a mapper run if you want an immutable DTO; doing so can break model invariants.

## 4. Rules for Matching Column Names and Parameter Names

Example:

~~~java
public record ProductSummary(
        long productId,
        String productName,
        int stockCount) {
}
~~~

SQL:

~~~sql
SELECT
    id AS product_id,
    name AS product_name,
    stock_count
FROM products
ORDER BY id
~~~

| Label in SQL result | Record component / constructor parameter |
| --- | --- |
| `product_id` | `productId` |
| `product_name` | `productName` |
| `stock_count` | `stockCount` |

Spring supports direct names and camelCase/snake_case conventions in standard forms. **Use explicit aliases** to eliminate guesswork. If the source column is `full_name` while the DTO expects `displayName`, write `full_name AS display_name`, rather than expecting the mapper to infer that both terms mean the same thing.

### 4.1. Use Column Labels Instead of Ambiguous SELECT *

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS display_name,
    COUNT(o.id) AS completed_orders
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.full_name
ORDER BY c.id
~~~

This SQL is **illustrative**, requiring the `orders` table and its relation. If the record is `record CustomerAggregate(long customerId, String displayName, long completedOrders) {}`, the aliases express the contract accurately. Do not use `SELECT *` with multi-table JOINs that share `id`: collisions/ambiguity and schema changes easily break mapping.

### 4.2. The Mapper Does Not Rely Purely on SELECT Order

The goal is to match parameter names with column names/aliases, then convert types. Reordering columns while keeping names stable normally does not change mapping semantics. However, **do not use this as an excuse to skip tests**: the driver and SQL projection still determine metadata and the actual value types read.

### 4.3. Missing a Constructor Column Is an Error, Not a Default Value

Record `CustomerSummary(long id, String displayName, int completedOrders)` requires column `completed_orders`. SQL that only does `SELECT id, display_name` supplies no value for the constructor. Spring does not guess `completedOrders` as 0; mapping can fail at runtime. Fix the query to supply the full projection or use a different DTO with only two components.

## 5. Runnable Java 17+ Example: Record and Constructor Combined with Setter

This example uses **Spring Framework 6.2.11**, H2 **2.3.232**, and Java 17. It demonstrates:

1. `DataClassRowMapper` mapping a record via its canonical constructor;
2. A regular class instantiated via a two-parameter constructor;
3. Property `city` populated via a setter after the constructor;
4. A query with no rows returning an empty list.

The project does not need Spring Boot; JDBC is wired explicitly to keep focus on mapping.

Structure:

~~~text
data-class-row-mapper-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'data-class-row-mapper-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

application {
    mainClass = 'demo.App'
}
~~~

`-parameters` is especially critical for the regular constructor of `CustomerProfile`. Gradle's `application` plugin provides the `run` task. Java source is placed properly under package `demo`.

File `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {

    public record CustomerSummary(
            long id,
            String displayName,
            int completedOrders) {
    }

    public static final class CustomerProfile {
        private final long id;
        private final String displayName;
        private String city;

        public CustomerProfile(long id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        public void setCity(String city) {
            this.city = city;
        }

        @Override
        public String toString() {
            return "CustomerProfile[id=" + id
                    + ", displayName=" + displayName
                    + ", city=" + city + "]";
        }
    }

    public static final class CustomerDao {
        private static final RowMapper<CustomerSummary> SUMMARY_MAPPER =
                DataClassRowMapper.newInstance(CustomerSummary.class);

        private static final RowMapper<CustomerProfile> PROFILE_MAPPER =
                DataClassRowMapper.newInstance(CustomerProfile.class);

        private final JdbcTemplate jdbc;

        public CustomerDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<CustomerSummary> withAtLeast(int minimum) {
            return jdbc.query(
                    """
                    SELECT id, display_name, completed_orders
                    FROM customers
                    WHERE completed_orders >= ?
                    ORDER BY id
                    """,
                    SUMMARY_MAPPER,
                    minimum);
        }

        public CustomerProfile profile(long id) {
            return jdbc.queryForObject(
                    """
                    SELECT id, display_name, city
                    FROM customers WHERE id = ?
                    """,
                    PROFILE_MAPPER,
                    id);
        }
    }

    public static void main(String[] args) {
        DataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:customer_mapping;DB_CLOSE_DELAY=-1",
                "sa",
                "");
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    display_name VARCHAR(100) NOT NULL,
                    completed_orders INT NOT NULL,
                    city VARCHAR(100)
                )
                """);

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                1L, "Linh Tran", 3, "Ha Noi");

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                2L, "Nam Le", 0, "Da Nang");

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                3L, "Mai Pham", 5, null);

        CustomerDao dao = new CustomerDao(jdbc);

        System.out.println("Record: " + dao.withAtLeast(3));
        System.out.println("Empty: " + dao.withAtLeast(99));
        System.out.println("Mixed: " + dao.profile(1L));
    }
}
~~~

Run from the project directory with JDK 17+ and a compatible Gradle installed:

~~~bash
gradle run --quiet
~~~

**Program stdout** (excluding environment logs if any):

~~~text
Record: [CustomerSummary[id=1, displayName=Linh Tran, completedOrders=3], CustomerSummary[id=3, displayName=Mai Pham, completedOrders=5]]
Empty: []
Mixed: CustomerProfile[id=1, displayName=Linh Tran, city=Ha Noi]
~~~

### 5.1. Analyzing Why It Works

1. `DriverManagerDataSource` provides JDBC connections to in-memory H2. `DB_CLOSE_DELAY=-1` keeps the in-memory DB alive inside the same JVM after closing the last connection. This is a **demo/test** setup without a connection pool like production HikariCP.
2. `JdbcTemplate` executes the DDL and parameterized INSERT statements, then reads SQL queries through both mappers.
3. `SUMMARY_MAPPER` maps `id`, `display_name`, and `completed_orders` into record `CustomerSummary`. Java records automatically generate `toString()` printing component names and values, hence stdout has the form `CustomerSummary[id=..., ...]`.
4. `withAtLeast(3)` selects IDs 1 and 3. `ORDER BY id` ensures the order of the two elements. `withAtLeast(99)` matches no rows, resulting in an empty `List`.
5. `PROFILE_MAPPER` maps ID and display name via constructor `CustomerProfile(long id, String displayName)`. `city` is not in the constructor, so `setCity(...)` is called for that remaining property.
6. `CustomerProfile.toString()` is implemented by the class itself, producing the last line as expected.
7. Both `CustomerSummary` and `CustomerProfile` are static nested types (records inside a class are implicitly static). `-parameters` enables recognition of regular constructor parameter names.
8. Mappers and `JdbcTemplate` do not cache query results; they orchestrate object creation and fetch data from SQL on each call.

The example does not configure a Spring transaction manager because the focus is mapping. In real applications, Spring Boot typically auto-configures `DataSource`/`JdbcTemplate`, and repositories receive the template via constructor injection.

## 6. Constructor Arguments Take Precedence Over Setters

By `DataClassRowMapper`'s contract, **a property already successfully mapped via a constructor argument will not be mapped again via a setter**. This differs from assuming every public setter is always called.

Example:

~~~java
public static final class DisplayCard {
    private String name;
    private String city;

    public DisplayCard(String name) {
        this.name = name.trim();
    }

    public void setName(String value) {
        this.name = "setter:" + value;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

With SQL column `name` having whitespace `"  Anh  "` and `city` being `Hue`:

- The constructor receives `name` and calls `trim()`, producing `Anh`.
- Setter `setName` does **not** run again for the property already mapped through the constructor.
- `setCity` can be used for column `city` because the constructor does not accept this property.

This is an **illustrative snippet in a static nested class**, not a complete program. Do not confuse this ordering with Bean Validation or JPA dirty checking: constructor mapping solely determines how an object is created from a row.

### Why Is This Rule Useful?

- Constructors can enforce immutable DTO invariants.
- Prevents setters from overwriting values normalized by the constructor.
- Clarifies design by putting required components in the constructor and optional components in setters.

However, if the constructor throws an exception when data is missing or invalid, mapping also fails. That can indicate the database violates the domain contract; do not catch it and silently substitute an empty object.

## 7. Comparison with BeanPropertyRowMapper and Hand-Written RowMapper

| Feature | `DataClassRowMapper<T>` | `BeanPropertyRowMapper<T>` | Custom `RowMapper<T>` |
| --- | --- | --- | --- |
| Java record target | Very suitable | Not the primary approach | Very suitable |
| Constructor with data parameters | Supported if names can be determined | Usually relies on no-arg + setters | Explicitly calls constructor |
| JavaBean-style setters | Can be combined | Supported | Up to your code |
| Constructor wins over setter | Yes | Not the usual case | Decided by your code |
| SQL column/alias naming | Matched by name/convention | Matched by name/convention | Reads columns explicitly |
| Reflection/conversion overhead | Present | Present | Usually better controlled |
| Mapper for object graphs | Does not automatically build complex nested relations | Does not automatically build complex nested relations | Can handle manually |
| Boilerplate amount | Low | Low | Higher |
| When custom conversion logic is needed | Custom converter or switch mapper | Custom converter or switch mapper | Clearest and most flexible |

### 7.1. Example with a JavaBean Having a No-Arg Constructor

~~~java
public class CustomerBean {
    private long id;
    private String displayName;

    public CustomerBean() {}

    public void setId(long id) {
        this.id = id;
    }

    public void setDisplayName(String name) {
        this.displayName = name;
    }
}
~~~

Then, the query snippet:

~~~java
List<CustomerBean> beans = jdbcTemplate.query(
        "SELECT id, display_name FROM customers ORDER BY id",
        BeanPropertyRowMapper.newInstance(CustomerBean.class));
~~~

`BeanPropertyRowMapper` fits mutable classes with setters. `DataClassRowMapper` extends it and can handle setter models too in many cases; however, using the specific mapper communicates the target's design intent.

### 7.2. Custom RowMapper Controlling Data Fields

~~~java
private static final RowMapper<CustomerSummary> SUMMARY =
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getInt("completed_orders"));
~~~

This snippet sits in a DAO importing `RowMapper` and the record type. It makes column names, getters, and argument order explicit, lets you tailor conversions as needed, and can reduce reflection overhead. If mapping is complex or performance is genuinely a bottleneck, a hand-written mapper is a sensible choice.

### 7.3. Spring Framework 6.1+ and JdbcClient

`JdbcClient` has a fluent interface:

~~~java
List<CustomerSummary> customers = jdbcClient.sql(
        """
        SELECT id, display_name, completed_orders
        FROM customers ORDER BY id
        """)
    .query(CustomerSummary.class)
    .list();
~~~

The snippet above requires a `JdbcClient` bean and the example schema. `JdbcClient.query(CustomerSummary.class)` uses that API's automatic class-mapping mechanism, and **you should not assume it necessarily uses `DataClassRowMapper` verbatim underneath**. When learning or needing strict control over which mapper processes data, you can still pass `DataClassRowMapper.newInstance(...)` directly to `JdbcTemplate.query(...)`.

## 8. NULL and Data Types in Constructors

This is the easiest group of bugs to overlook. SQL `NULL` differs from `0`, `false`, or an empty string:

~~~java
public record ProductView(
        long id,
        String name,
        Integer stockCount,
        java.math.BigDecimal price) {
}
~~~

With a schema where `stock_count` is nullable:

- `long id` should be read from a `PRIMARY KEY`/`NOT NULL` column because a primitive cannot hold null.
- `Integer stockCount` preserves the distinction between “unknown stock count” and `0`.
- `BigDecimal price` is normally better suited to currency than `double`, though scale/rounding must still be checked.
- `String name` can be null in Java; the constructor can separately enforce business constraints.

### 8.1. Passing NULL into a Primitive

When a constructor requires `int`/`long`/`boolean` while the SQL column can be NULL, the mapper cannot represent null directly as a primitive, so conversion/invocation can fail. Do not blindly default to `0`. Choose a wrapper type or `NOT NULL` constraint; if using SQL `COALESCE`, make sure turning null into 0 is business-valid.

~~~sql
SELECT
    id,
    COALESCE(stock_count, 0) AS stock_count
FROM products
ORDER BY id
~~~

The SQL above is only valid if null can be interpreted as a quantity of 0. If null means “not yet inventoried”, `Integer` represents the data accurately.

### 8.2. ConversionService, Enums, BigDecimal, Date/Time

`DataClassRowMapper` inherits conversion capabilities from Spring's mapper. You can supply a custom `ConversionService` via the overload:

~~~java
DataClassRowMapper<ProductView> mapper =
        DataClassRowMapper.newInstance(
                ProductView.class, conversionService);
~~~

This snippet assumes a `ConversionService conversionService` is defined. You do not need custom converters for every type; only create them when the driver/type/domain requires it.

Pay special attention to testing:

- `DATE` -> `LocalDate`;
- `TIMESTAMP` -> `LocalDateTime` and timezone handling;
- `TIMESTAMP WITH TIME ZONE` -> `OffsetDateTime`;
- `NUMERIC`/`DECIMAL` -> `BigDecimal`, `Integer`, `Long`;
- `VARCHAR` -> `enum` when codes/names/casing differ;
- PostgreSQL enum/JSONB/UUID/ARRAY or database-specific types.

Conversion outcomes also depend on the JDBC driver and actual data; not every dialect returns the same Java type. When conversion is intricate and business-sensitive, a manual `RowMapper` is usually easier to control.

### 8.3. Constructors with Validation

~~~java
public record PriceView(
        long id, java.math.BigDecimal amount) {

    public PriceView {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be non-negative");
        }
    }
}
~~~

If SQL returns a null or negative amount, the constructor rejects the object. The mapper must not treat invalid data as a normal row. Distinguish domain validation errors, conversion errors, and `DataAccessException` from SQL/driver failures.

## 9. One SQL Row Does Not Equal One Object Graph

`DataClassRowMapper` applies “one row -> one instance” rather than building parent–child relationships.

~~~sql
SELECT
    c.id,
    c.display_name,
    o.id AS order_id
FROM customers c
JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id
~~~

If one customer has three orders, the SQL above yields three rows for that customer, so mapping directly into a customer record produces three duplicate instances. The mapper does not collapse three orders into a `List<Order>` inside a parent object.

Better options:

1. Only need order count: use SQL aggregate `COUNT(o.id) AS order_count` with `GROUP BY`, returning one summary record per customer.
2. Only need customers with orders: use `EXISTS` instead of JOIN to avoid row multiplication.
3. Need an object graph: use `ResultSetExtractor`, a manual mapper, or two queries merged by key.
4. Need to paginate customers: paginate parents first, avoiding `LIMIT/OFFSET` directly on a one-to-many JOIN which causes pages to contain fewer customers than expected.

**Limitation of this mapper kind:** it does not replace JPA `@OneToMany`, entity graphs, or ORM hydration. Use the right abstraction so you do not build malformed DTOs.

## 10. Performance and Mapper Reuse

Spring describes `DataClassRowMapper` as convenient rather than **optimized for extreme performance**. It performs metadata/reflection/conversion work during mapping. However, do not prematurely optimize while ignoring SQL cost, indexes, network, driver, allocations, sorting, and paging.

A clean way to organize it in a DAO:

~~~java
private static final RowMapper<CustomerSummary> MAPPER =
        DataClassRowMapper.newInstance(CustomerSummary.class);
~~~

A static mapper with no request state can be reused. `JdbcTemplate` is also typically a shared bean across repositories. Mapping row by row does **not** mean opening a new connection per row: `JdbcTemplate` manages a single SQL operation on an appropriate connection.

When results are very large:

- SELECT only the columns needed for the DTO (projection).
- Paginate with a stable `ORDER BY` and `LIMIT/OFFSET` or dialect-appropriate keyset pagination.
- Do not read millions of objects into `List<T>` by default and filter in Java afterward.
- Choose fetch size/transactions/cursors per driver if streaming is needed; `setFetchSize` is a hint, not a page size.
- Use `RowCallbackHandler` or `queryForStream` when a list is not needed. With `queryForStream`, you must **close the stream** with try-with-resources.
- Benchmark/profile before switching to a manual mapper; if mapping is a hot spot, a manual mapper lets you control typed reads and allocations.

### 10.1. Do Not Attach Mutable State to a Shared Mapper

A mapper or DTO constructor must not retain a `ResultSet`, `Connection`, or buffer shared across multiple requests. Returned object data belongs to each query execution. Metadata and mapping policies can be reused, whereas a `List<CustomerSummary>` returned for request A must never become a singleton field mutated by request B.

## 11. Real-World Errors and How to Fix Them

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Constructor not found or instantiation fails | Unsuitable class, ambiguous multiple constructors, non-static inner class | Use a record or top-level/static nested class with a clear constructor |
| Mapper looks for `arg0`, `arg1` | Regular class was not compiled with `-parameters` | Enable the compiler flag and test the final artifact |
| Reports missing column `displayName` | SQL returns `full_name`, missing matching alias | Use `AS display_name` |
| Missing constructor data | Query only SELECTs a subset of fields | Select the full projection or use a different DTO |
| Null hits a primitive | SQL is nullable while constructor uses `int`/`long` | Wrapper type or schema/SQL handles null properly |
| Wrong date/time type | Incompatible JDBC driver/timezone/converter | Test on real DB; custom conversion/manual mapper |
| Setter did not run after constructor | Property already mapped via constructor so setter was skipped | Move validation into the constructor; understand precedence |
| Duplicate results due to JOIN | Each SQL row creates an instance | Fix query/aggregate, map object graphs separately |
| Record created yet JPA sees no changes | JDBC DTO is not a managed JPA entity | Use repository/SQL updates or JPA for its proper role |
| Query returns no rows | `JdbcTemplate.query` yields an empty list | Handle empty contract, do not treat as a mapper bug |
| `queryForObject` has no rows | API requires exactly one row | Handle not-found/`Optional` per business logic |
| Mapper is slow on large datasets | Reflection/conversion + many objects | Profile, paginate, custom `RowMapper` |
| IDE auto-imported same-named R2DBC class | Wrong package `org.springframework.r2dbc.core` | Use `org.springframework.jdbc.core.DataClassRowMapper` |

### 11.1. Diagnosing Parameter-Name Metadata

For a regular constructor:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

Constructor<?> ctor =
        CustomerCard.class.getDeclaredConstructors()[0];

for (Parameter p : ctor.getParameters()) {
    System.out.println(
            p.getName() + " / present=" + p.isNamePresent());
}
~~~

This is a diagnostic snippet when `CustomerCard` is in scope with one matching constructor. If built with `-parameters`, you expect `id`/`displayName` with `isNamePresent() == true`. If Java reflection sees `arg0`/`arg1` and false, metadata was not retained as reflection expects. Check each module/library containing DTOs individually.

### 11.2. Do Not Fix Bugs by Removing All Validation

If a constructor rejects `amount < 0`, do not delete the validation just to silence the mapper. Find the invalid data source, fix the migration/SQL, or choose an appropriate DTO. Mappers often expose mismatches between database data and Java contracts; that is usually a signal worth addressing.

### 11.3. Be Careful with APIs Across Different Spring Branches

`org.springframework.jdbc.core.DataClassRowMapper` has been a Spring JDBC API since Spring Framework 5.3. There is also a `DataClassRowMapper` in the R2DBC package for a different reactive interface. Check imports, API versions, and overloads of `newInstance`/`JdbcTemplate` against your actual dependencies.

## 12. Meaningful Mapping Tests

With integration tests on H2 or a real DB, verify:

1. **Record mapping:** Query includes `display_name`/`completed_orders` and returns objects with the right components.
2. **Class constructor mapping:** Class compiled with `-parameters` instantiates `id`/`displayName` properly.
3. **Constructor + setter:** `city` is assigned via setter, while properties already mapped in the constructor are not overwritten.
4. **No rows:** `query(...)` returns an empty list without throwing `EmptyResultDataAccessException`.
5. **Missing column:** Intentionally omit a component in the query and verify mapping fails; ensure malformed objects are not silently created.
6. **NULL:** Use nullable columns and wrapper/reference types, verifying primitives do not conflate NULL with 0.
7. **Conversions:** DATE/TIMESTAMP/DECIMAL/enum on the production driver.
8. **JOIN:** One parent with multiple children; verify the query returns the DTO count matching the contract.
9. **Ordering:** If the API requires an ordered list, SQL must include `ORDER BY`.
10. **Performance:** For large datasets, measure query time, mapping time, and memory when optimization is needed.

### JUnit 5 Example (Integration Snippet)

Assuming JUnit 5, the `customers` table created before the test, and `JdbcTemplate jdbc` available:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void mapsSnakeCaseIntoRecord() {
    jdbc.update(
            """
            INSERT INTO customers
            (id, display_name, completed_orders, city)
            VALUES (?, ?, ?, ?)
            """,
            10L, "An Nguyen", 4, "Hue");

    List<CustomerSummary> actual = jdbc.query(
            """
            SELECT id, display_name, completed_orders
            FROM customers WHERE id = ?
            """,
            DataClassRowMapper.newInstance(CustomerSummary.class),
            10L);

    assertEquals(
            List.of(new CustomerSummary(10L, "An Nguyen", 4)),
            actual);
}
~~~

The snippet above **does not run standalone**: the test class needs `jdbc`, `CustomerSummary`, imports for `java.util.List`/mapper, Spring test configuration, and a database fixture. Java records implement `equals()` by components so they can be compared directly with `assertEquals`. In real projects, isolate/roll back the test DB between tests to avoid duplicate keys.

### Unit Tests vs. Integration Tests Differ

Mocking `JdbcTemplate` can prove the service calls the repository properly, but **does not prove SQL aliases or reflection mapping actually work**. Automatic mappers rely on `ResultSetMetaData`, so small integration tests with a real/embedded database are usually worthwhile. When production uses PostgreSQL/MySQL/Oracle with types differing from H2, run additional tests against a compatible DB, such as via Testcontainers.

## 13. Workflow for Designing DTOs with DataClassRowMapper

1. **Choose output data:** Write a record containing only the columns the query needs to return; do not mirror the whole table if the API only needs a summary.
2. **Define nullability:** Pick primitives for genuinely `NOT NULL` columns; wrappers/references for nullable columns.
3. **Design the constructor:** A record or a single clear data constructor; preserve parameter-name metadata at runtime.
4. **Write the SQL projection:** SELECT all required columns, alias to component/parameter names, and use bind placeholders.
5. **Create the mapper:** `DataClassRowMapper.newInstance(Dto.class)`; reuse the stateless instance where appropriate.
6. **Wire into the repository:** Inject `JdbcTemplate` via constructor, use `query(sql, mapper, args...)` for multiple rows.
7. **Handle outcomes:** Empty lists, cardinality errors, and mapping/conversion errors each have distinct contracts; never swallow errors to fake “no data”.
8. **Test:** H2 for demos, real DB for dialect/special types, and test `-parameters` metadata when using regular classes.
9. **Measure when needed:** If throughput/latency is affected by reflection, test a benchmarked manual mapping.

### Review Questions

1. Why is `DataClassRowMapper` a better fit for Java records than traditional `BeanPropertyRowMapper`?
2. A class has constructor `CustomerCard(long id, String displayName)` without being a record; why can a production build fail if `-parameters` is missing?
3. A query has column `full_name` while the record expects `displayName`: what alias expresses the right contract?
4. A class has both a constructor and a setter for `name`: which one takes precedence?
5. Why should a nullable SQL column `stock_count` not use `int` if null means “not yet counted”?
6. A JOIN returns three rows for one customer: will the mapper automatically construct one `CustomerWithOrders` containing three elements?
7. When is the cost of an automatic mapper worth switching to a custom `RowMapper`?
8. Why are DTOs created by a Spring JDBC mapper not automatically tracked by a JPA persistence context?

## 14. Implementation Checklist

- [ ] Target class is top-level or static nested, with matching constructor/record components.
- [ ] Regular classes retain runtime parameter-name metadata; compiler has `-parameters` if needed.
- [ ] SQL returns **all required columns** for the constructor, with aliases matching parameter names.
- [ ] Nullable fields use wrapper/reference types; primitives do not receive ambiguous nulls.
- [ ] Understood that constructor arguments take precedence over setters.
- [ ] No careless `SELECT *` with JOINs; avoid missing or colliding column labels.
- [ ] Mapper is reused without holding mutable request state.
- [ ] `JdbcTemplate` and datasource/transaction manager are configured properly alongside the mapper.
- [ ] Do not expect `DataClassRowMapper` to merge multiple SQL rows into nested graphs.
- [ ] Queries returning no rows are handled as valid `List<T>` results.
- [ ] Tested with an appropriate JDBC driver; type/date/time/conversion paths tested in a production-like setup.
- [ ] Optimize to a manual mapper only when there is a clear need and supporting profiling.

**Conclusion:** Choose `DataClassRowMapper` when **SQL columns align cleanly with constructor parameter/record component names**. It lets Spring JDBC instantiate immutable DTOs and constructor–setter classes without writing a column-by-column `RowMapper`. Accuracy depends on constructor design, compiler metadata, SQL aliases, nullability, and type conversions; cases needing object graphs or special mappings should still use a manual mapper.

## Official Documentation

- [Spring Framework — DataClassRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html)
- [Spring Framework — BeanPropertyRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html)
- [Spring Framework — JDBC Core Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Java 17 — java.lang.reflect.Parameter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
