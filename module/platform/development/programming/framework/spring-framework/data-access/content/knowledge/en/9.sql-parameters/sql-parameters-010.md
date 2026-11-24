# Keeping Parameter Count and Data Types Compatible with the Statement

> **Principle:** When using JDBC or Spring `JdbcTemplate`, every input parameter must be bound at the **exact position, in exact count, and with a data type compatible with the corresponding SQL expression/column**. For `?` markers, JDBC numbers positions starting at **1** in order of appearance in the SQL statement; for `NamedParameterJdbcTemplate`, values are matched by **parameter name** before Spring translates them to JDBC positions. Matching the count while **swapping order** or using an **incompatible type** can still trigger exceptions or, worse, write wrong data.

In Spring Framework Data Access, SQL parameters are part of the **contract between the statement and Java values**. This lesson guides you through reading that contract, maintaining consistency when adding dynamic conditions, handling `NULL`, numbers/dates/times, `IN` lists, batches, testing, and diagnosing mismatches.

## 1. Three Conditions That Must All Hold Simultaneously

Consider a simple orders table:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    note VARCHAR(100) NULL
);
```

Update statement:

```sql
UPDATE orders
SET status = ?, total = ?
WHERE id = ?;
```

The statement has **three positions to bind**, in order:

| JDBC Position | SQL Expression | Expected DB Type | Appropriate Java Value |
| ---: | --- | --- | --- |
| 1 | `status = ?` | `VARCHAR` | `String`, e.g., `"PAID"` |
| 2 | `total = ?` | `DECIMAL(12,2)` | `BigDecimal`, e.g., `new BigDecimal("129.50")` |
| 3 | `id = ?` | `BIGINT` | `long`/`Long`, e.g., `10L` |

Correct Spring JDBC call:

```java
int changed = jdbc.update(
    "UPDATE orders SET status = ?, total = ? WHERE id = ?",
    "PAID",
    new java.math.BigDecimal("129.50"),
    10L
);
```

`jdbc` here is a configured `JdbcOperations`/`JdbcTemplate` variable inside a method; the snippet is not a standalone application. The `update(String sql, Object... args)` signature receives values in `?` order. `changed` is the **affected row count**, not the parameter count. If no order has `id=10`, the result can be 0 even when all parameters are bound properly.

Three dimensions to check:

1. **Count:** three `?` markers mean three values, not two or four.
2. **Order/name:** `"PAID"` belongs to the `status` column, `BigDecimal` belongs to `total`, and `10L` belongs to the `id` condition. Java variable names do not automatically locate `?` parameters.
3. **Type compatibility:** Java `String` fits `VARCHAR`, `BigDecimal` fits `DECIMAL`, `Long` fits `BIGINT`; values must also satisfy length, precision, `NOT NULL`, `CHECK`, foreign key, and domain rules.

Matching only one dimension is not enough. Passing two `String` values swapped for two `VARCHAR` columns may cause no SQL error yet **corrupt data**. Conversely, passing `"one hundred"` into `DECIMAL` may fail when the driver/DB attempts conversion. Some DBMSs implicitly cast numeric strings to numbers, but **you should never rely on implicit casts** to hide buggy binding code.

## 2. Question Marks in PreparedStatement and 1-Based Positions

`java.sql.PreparedStatement` is the JDBC API taking SQL with `?` parameter markers and setters such as `setLong`, `setString`, and `setBigDecimal`.

```java
String sql = "UPDATE orders SET status = ?, total = ? WHERE id = ?";
try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    ps.setBigDecimal(2, new java.math.BigDecimal("129.50"));
    ps.setLong(3, 10L);
    int changed = ps.executeUpdate();
}
```

This is a **code fragment inside a method** with a properly obtained `java.sql.Connection connection`; `try-with-resources` closes the statement after use. Parameter indices are **1, 2, 3**, not 0, 1, 2. This differs from Java arrays/lists which start at 0.

### When Parameters Are Missing or Excess

The SQL still has three `?` markers, yet only two are bound:

```java
ps.setString(1, "PAID");
ps.setBigDecimal(2, new java.math.BigDecimal("129.50"));
// Parameter 3 has not been bound yet.
ps.executeUpdate();
```

Typically the driver reports an error at execute time because a parameter was not set. If you try `ps.setLong(4, 10L)` when there are only three markers, the driver may throw `SQLException` immediately at the setter due to an invalid index. Error timing, SQLState, error codes, and messages **depend on the driver/DBMS**.

With `JdbcTemplate`, when Spring translates `SQLException`, the caller usually receives a subclass of `DataAccessException`, though you should not promise one fixed subclass for every parameter-count or type-conversion error. Inspect the root cause and actual SQL.

### Count Parameters by Prepared SQL, Not by Intuition

In a simple example, three `?` correspond to three values. In more complex SQL, question marks can appear inside string literals, comments, or dialect-specific operator syntax. **Do not write your own `sql.chars().filter(ch -> ch == '?')` algorithm to claim standard marker counts across all databases.** The driver/JDBC parser decides what syntax is recognized. `PreparedStatement.getParameterMetaData().getParameterCount()` can help inspect, though metadata availability and accurate type reporting also depend on the JDBC driver.

Another part of the contract: `?` only represents **SQL values**, not table/column names or entire SQL clauses. `ORDER BY ?` is not a safe way to parameterize sort columns; if column names are user-selected, the application must allow-list permitted columns/sort modes.

## 3. Matching Count with Wrong Order Is Still Dangerous

With the statement:

```sql
UPDATE orders SET status = ?, note = ? WHERE id = ?;
```

Wrong pattern:

```java
jdbc.update(
    "UPDATE orders SET status = ?, note = ? WHERE id = ?",
    "Called customer",
    "PAID",
    10L
);
```

Here Java passes three values, all matching SQL types (`VARCHAR`, `VARCHAR`, `BIGINT`), so the statement can run successfully. Yet it sets `status = "Called customer"` and `note = "PAID"`: **right in count and types, wrong in meaning and order**. If `status` has a constraint, the DB may block it; otherwise, bad data is written silently.

Fix:

```java
jdbc.update(
    "UPDATE orders SET status = ?, note = ? WHERE id = ?",
    "PAID",
    "Called customer",
    10L
);
```

Review practice: read SQL from left to right, number the `?` markers, and write a mapping table `1 → status`, `2 → note`, `3 → id`. Do not automatically rely on field order in a record/DTO if SQL column order differs. Whenever adding a column to `SET` or a predicate to `WHERE`, update SQL and the entire value list **in sync**.

### Queries with Multiple Same-Typed Question Marks

```sql
SELECT id, status, total
FROM orders
WHERE customer_id = ? AND id > ? AND total >= ?
ORDER BY id;
```

The three values should be `customerId (Long)`, `lastId (Long)`, and `minimumTotal (BigDecimal)`. The first two parameters are both `BIGINT`, so swapping them can return the wrong result set without raising an exception. This is why **testing output values** matters more than only testing that the SQL runs without error.

## 4. Java and SQL Types: Prefer Explicit Compatibility

JDBC provides typed setter methods. The table below shows only common mappings; actual conversion also depends on the driver, DBMS, precision/scale, and schema.

| Target SQL | Java Type to Consider | Explicit JDBC Binding | Notes |
| --- | --- | --- | --- |
| `BIGINT` | `Long`/`long` | `setLong`, `Types.BIGINT` | Do not arbitrarily pass String IDs; avoid overflow |
| `INTEGER` | `Integer`/`int` | `setInt`, `Types.INTEGER` | Value range must be valid |
| `SMALLINT` | `Short`/`short` | `setShort`, `Types.SMALLINT` | Do not assume DB casts every int to smallint |
| `BOOLEAN`/`BIT` | `Boolean`/`boolean` | `setBoolean`, `Types.BOOLEAN` | DBMSs may represent booleans differently |
| `VARCHAR` | `String` | `setString`, `Types.VARCHAR` | Check `NOT NULL` and length |
| `DECIMAL`/`NUMERIC` | `BigDecimal` | `setBigDecimal`, `Types.DECIMAL` | Preserve exactness and proper scale |
| `DATE` | `LocalDate` / `java.sql.Date` | `setDate` or typed `setObject` | JDBC 4.2 drivers may support `LocalDate` |
| `TIMESTAMP` | `LocalDateTime` / `Timestamp` | `setTimestamp` or typed `setObject` | Consider precision, timezone, and dialect |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` (if driver supports) | typed `setObject` | Do not confuse local time with instant |
| `BINARY`/`VARBINARY` | `byte[]` | `setBytes` | Do not pass base64 String unless schema requires it |
| `NULL` for specific column | Java `null` + SQL type | `setNull(index, Types.XXX)` | Null has no self-describing Java type |

Principles:

- **Monetary amounts:** use `new BigDecimal("129.50")` or an equivalent exact constructor. Avoid `new BigDecimal(129.50)` because `double` is binary floating-point and may not represent decimal values exactly.
- **Dates/times:** do not arbitrarily pass locale-formatted `String`s like `"31/12/2026"` into a `DATE` column. Pass a compatible temporal type and verify how the driver handles timezones.
- **Enums:** if the schema stores a status string, convert the enum to an explicitly defined storage value, e.g., `OrderStatus.PAID.name()` when the contract guarantees enum names match DB codes. Do not expect the driver to know domain enum semantics automatically.
- **Long/Integer:** even though some DBs convert between them, use the type matching the schema and avoid relying on lucky conversions.
- **NULL:** SQL type is part of the contract. `null` cannot be passed via Java primitives. Use wrappers or explicit SQL type declarations when needed.
- **Data bounds:** Java type compatibility is not enough; `"a very long string"` can still exceed `VARCHAR(10)`, and `BigDecimal("999999999999.99")` can exceed `DECIMAL(12,2)`.

## 5. The NULL Case: Preserve SQL Type Even Without a Java Value

The `note VARCHAR(100) NULL` column allows missing notes. Plain JDBC can bind:

```java
if (note == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, note);
}
```

This fragment belongs to a method with `PreparedStatement ps` and `String note`, where parameter 1 corresponds to `note`. `setNull` requires specifying the SQL type so the driver knows which type of `NULL` this is.

**Never replace SQL NULL with the string `"null"`, empty string `""`, or `0`** just to make code run. Those values carry different semantics from SQL NULL and can break queries/filters later.

Spring usually determines SQL type from the Java value, yet inference is harder when the value is `null`, especially for particular columns/expressions or JDBC drivers. Spring lets you use `SqlParameterValue`:

```java
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameterValue;

int updated = jdbc.update(
    "UPDATE orders SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, null),
    10L
);
```

Here `jdbc` is a `JdbcOperations`/`JdbcTemplate` variable inside a method. There are **two markers**: the first carries SQL type `VARCHAR` and null value, while the second is the `BIGINT` key. `SqlParameterValue` can similarly pass non-null values with an explicit SQL type.

Spring `JdbcTemplate` also has an overload accepting an SQL type array:

```java
Object[] args = {null, 10L};
int[] argTypes = {Types.VARCHAR, Types.BIGINT};

int changed = jdbc.update(
    "UPDATE orders SET note = ? WHERE id = ?",
    args,
    argTypes
);
```

In this snippet `jdbc` must be a **`JdbcOperations` or `JdbcTemplate` with the `update(String, Object[], int[])` overload** and `Types` is `java.sql.Types`. Both `args` and `argTypes` must have **two elements**, matching the two SQL positions. You cannot declare only one SQL type and expect Spring to guess the remaining types in that overload. `changed` is still the updated row count.

Using `SqlParameterValue` is handy when only a few parameters need explicit types; an `argTypes` array shows the full type table by position.

### Null and Clause Semantics

SQL snippet:

```sql
SELECT id FROM orders WHERE note = ?;
```

If you bind `null` to `?`, `note = NULL` under standard SQL logic **matches no rows**, not even rows where `note IS NULL`. This is an **SQL semantics** issue, not a parameter-count bug. To find rows where `note` is NULL, use:

```sql
SELECT id FROM orders WHERE note IS NULL;
```

If query policy permits an optional filter, decide clearly: omit the condition, use `IS NULL`, or use an expression with explicit semantics. Never pass null expecting `= ?` to turn into `IS NULL` automatically.

## 6. Java 17+ Plain JDBC Example: Checking Three Placeholders

The following class uses only standard JDK APIs and compiles with Java 17. It requires an open `Connection` and an `inventory_events(id BIGINT, note VARCHAR, quantity INTEGER NULL)` table in a DB to execute; **it is not a standalone application with `main`**.

**`ExplicitBinder.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;

public final class ExplicitBinder {
    private ExplicitBinder() {}

    public static int insertEvent(
            Connection connection,
            long id,
            String note,
            Integer quantity) throws SQLException {

        String sql = """
            INSERT INTO inventory_events (id, note, quantity)
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, note);

            if (quantity == null) {
                statement.setNull(3, Types.INTEGER);
            } else {
                statement.setInt(3, quantity);
            }

            return statement.executeUpdate();
        }
    }
}
```

Check compilation of this plain Java piece:

```bash
javac --release 17 ExplicitBinder.java
```

When called, the method binds **exact three markers** in order `id`, `note`, `quantity`. It releases the `PreparedStatement` but **does not close the `Connection` owned by the caller**. The caller must manage the connection and transaction, or use a Spring layer to manage them.

`setString(2, null)` is defined by JDBC to send SQL NULL in some cases, yet for exact SQL type control and driver compatibility—especially with untyped nulls—use `setNull(index, Types.VARCHAR)` when needed. For the `quantity` parameter, the example handles it explicitly.

## 7. Spring JdbcTemplate: Complete Example of Parameter Count and Types

To observe real execution results, use **Java 17+, Spring Boot 3.3+**, `spring-boot-starter-jdbc`, and in-memory H2. Create a Spring Boot Gradle project with the appropriate plugins, repositories, and dependency management.

In `build.gradle`, add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

This is the **dependencies block** of an already configured build script, not a standalone Gradle file.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:sql_params_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

### 7.1. Defining Java Data

**`src/main/java/example/Product.java`:**

```java
package example;

import java.math.BigDecimal;

public record Product(
    long id,
    String sku,
    String name,
    BigDecimal price,
    int stock,
    boolean active,
    BigDecimal discount
) {}
```

`price`/`discount` use `BigDecimal` because the database columns are `DECIMAL(12,2)`. `discount` is nullable, while the other fields in the example have `NOT NULL` constraints.

### 7.2. Repository Using JdbcOperations

**`src/main/java/example/ProductRepository.java`:**

```java
package example;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {
    private static final RowMapper<Product> MAPPER =
        (rs, rowNum) -> new Product(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getString("name"),
            rs.getBigDecimal("price"),
            rs.getInt("stock"),
            rs.getBoolean("active"),
            rs.getBigDecimal("discount")
        );

    private final JdbcOperations jdbc;

    public ProductRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(Product product) {
        String sql = """
            INSERT INTO products
                (id, sku, name, price, stock, active, discount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """;

        return jdbc.update(
            sql,
            product.id(),       // 1: BIGINT
            product.sku(),      // 2: VARCHAR
            product.name(),     // 3: VARCHAR
            product.price(),    // 4: DECIMAL
            product.stock(),    // 5: INTEGER
            product.active(),   // 6: BOOLEAN
            new SqlParameterValue(Types.DECIMAL, product.discount()) // 7
        );
    }

    public int renameAndStock(long id, String newName, int newStock) {
        return jdbc.update(
            "UPDATE products SET name = ?, stock = ? WHERE id = ?",
            newName,  // 1
            newStock, // 2
            id        // 3
        );
    }

    public Optional<Product> findById(long id) {
        List<Product> rows = jdbc.query(
            "SELECT id, sku, name, price, stock, active, discount " +
            "FROM products WHERE id = ?",
            MAPPER,
            id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    public List<Product> findActiveAtLeast(BigDecimal minimumPrice) {
        return jdbc.query(
            "SELECT id, sku, name, price, stock, active, discount " +
            "FROM products WHERE active = ? AND price >= ? ORDER BY id",
            MAPPER,
            true,
            minimumPrice
        );
    }

    public long countSku(String sku) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM products WHERE sku = ?",
            Long.class,
            sku
        );
        return java.util.Objects.requireNonNull(count);
    }

    public int setDiscount(long id, BigDecimal discount) {
        return jdbc.update(
            "UPDATE products SET discount = ? WHERE id = ?",
            new SqlParameterValue(Types.DECIMAL, discount),
            id
        );
    }
}
```

Key details to read closely:

- `insert` has **7 `?` markers and exact 7 values**, in column order. `SqlParameterValue` at position 7 passes SQL `DECIMAL NULL` when `discount` has no value.
- `renameAndStock` has **3 `?` markers**; even though `id` is the first parameter in the Java method, it is position **3** in SQL because `WHERE id = ?` comes after the two assignments.
- `findById` has **1 `?` marker**, passing `long id` matching `BIGINT`. `DataAccessUtils.optionalResult` has existed since Spring Framework 6.1 and turns 0 rows into `Optional.empty()`; if more than one row is returned, it throws a result-count error.
- `findActiveAtLeast` has **2 `?` markers**: boolean `true` and `BigDecimal minimumPrice`, which cannot be swapped. `ORDER BY id` guarantees output order.
- `countSku` has **1 `?` marker**. `COUNT(*)` without `GROUP BY` returns one row with the count (possibly 0), unlike a normal query returning 0 rows.
- `setDiscount` has **2 `?` markers**, able to pass either a `BigDecimal` or `null` with an explicit SQL type. Never write `0` in place of null unless business rules permit it.

### 7.3. Application Initializing Schema and Printing Output

**`src/main/java/example/SqlParameterDemoApplication.java`:**

```java
package example;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class SqlParameterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlParameterDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, ProductRepository products) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE products (
                    id BIGINT PRIMARY KEY,
                    sku VARCHAR(20) NOT NULL UNIQUE,
                    name VARCHAR(100) NOT NULL,
                    price DECIMAL(12,2) NOT NULL,
                    stock INTEGER NOT NULL,
                    active BOOLEAN NOT NULL,
                    discount DECIMAL(12,2) NULL
                )
                """);

            Product notebook = new Product(
                7L, "BK-7", "Notebook",
                new BigDecimal("49.90"),
                5, true, null
            );

            System.out.println("insert=" + products.insert(notebook));
            System.out.println("changed=" +
                products.renameAndStock(7L, "Notebook Pro", 8));
            System.out.println("active=" +
                products.findActiveAtLeast(new BigDecimal("40.00")));
            System.out.println("found=" + products.findById(7L));
            System.out.println("missing=" + products.findById(999L));
            System.out.println("countSku=" + products.countSku("BK-7"));
        };
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
```

On Windows you can run `gradlew.bat bootRun`. In a fresh in-memory H2 database with no other schema/seed scripts, the lines printed by the application (excluding Spring/Hikari logs) are:

```text
insert=1
changed=1
active=[Product[id=7, sku=BK-7, name=Notebook Pro, price=49.90, stock=8, active=true, discount=null]]
found=Optional[Product[id=7, sku=BK-7, name=Notebook Pro, price=49.90, stock=8, active=true, discount=null]]
missing=Optional.empty
countSku=1
```

Explanation:

1. `insert` binds 7 values to the 7 columns and inserts one row; affected row count is 1.
2. `renameAndStock` binds the new name, new stock, then ID; updates product `id=7` accurately.
3. `findActiveAtLeast` binds `true` for `active` and `40.00` for the `price` threshold, retrieving the inserted product.
4. `findById(7)` returns a record with `discount=null`; `BigDecimal` can hold Java null. `findById(999)` returns `Optional.empty()` because that ID does not exist.
5. `COUNT(*)` by SKU returns 1; `COUNT(*)` returning 0 if the SKU does not exist is also a valid result.

**Compilation limitation:** These Java files run inside a **Spring Boot project with matching build scripts and dependencies**; they cannot be compiled with `javac` using only the plain JDK classpath because they import Spring. The example uses Java 17+, `@SpringBootApplication`, H2 configuration, and auto-configured `JdbcTemplate` under suitable conditions. When switching to PostgreSQL/MySQL, matching JDBC drivers, schemas, and data are needed; do not conclude from H2 that all conversions behave identically.

## 8. NamedParameterJdbcTemplate: Matching by Name, Still Must Have Right Types

When an SQL statement has many placeholders and positions are easy to swap, `NamedParameterJdbcTemplate` lets you write:

```sql
UPDATE orders
SET status = :status, total = :total
WHERE id = :id;
```

Use the names `:status`, `:total`, `:id` and pass a map by name:

```java
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

int changed = namedJdbc.update(
    "UPDATE orders SET status = :status, total = :total WHERE id = :id",
    Map.of(
        "status", "PAID",
        "total", new BigDecimal("129.50"),
        "id", 10L
    )
);
```

`namedJdbc` is an injected/configured `NamedParameterJdbcTemplate` instance. This snippet is code inside a method, not a standalone program.

A map lacking fixed iteration order **is not a problem**: Spring matches data by **parameter name**, then converts to JDBC positional placeholders for execution. Parameter names **must match**; if SQL has `:id` yet the map only has `"orderId"`, Spring may report a missing value for name `id`.

Notes:

- Named parameters make code easier to read, yet **do not remove the need for type matching**: `:total` still needs a `DECIMAL`-compatible value, and `:id` still needs a `BIGINT`-compatible value.
- A name `:id` appearing multiple times in SQL can reuse the same value from the map, while under the hood Spring binds it to every required marker.
- `Map.of(...)` **forbids null values**. For a nullable parameter, use `MapSqlParameterSource` or a mutable map permitting null, and declare the SQL type when needed.
- Named parameters also represent **values** only; never use `:columnName` as a dynamic column/identifier name.

### MapSqlParameterSource Both Matches Names and Specifies SQL Type

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("note", null, Types.VARCHAR)
    .addValue("id", 10L, Types.BIGINT);

int changed = namedJdbc.update(
    "UPDATE orders SET note = :note WHERE id = :id",
    params
);
```

This snippet is inside a method with a configured `namedJdbc` variable. The SQL has two names to bind, and `MapSqlParameterSource` supplies both names, values, and SQL types; `note`'s null is not coerced to the string `"null"`.

When reading only a subset of inputs, the map does not strictly have to contain only the keys appearing in the SQL; however, **every SQL-required name must be supplied**, and business code should avoid passing unused parameters because they make code harder to review.

## 9. `IN (...)` Lists: One Collection Does Not Automatically Equal Multiple Markers

Suppose you want to query three IDs `7`, `8`, `9`. The SQL has three positional placeholders:

```sql
SELECT id, name FROM products WHERE id IN (?, ?, ?);
```

The parameters must be **three separate values**:

```java
List<Long> ids = List.of(7L, 8L, 9L);
List<Product> found = jdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE id IN (?, ?, ?) ORDER BY id",
    MAPPER,
    ids.get(0), ids.get(1), ids.get(2)
);
```

`jdbc` and `MAPPER` are members inside `ProductRepository` or a method with a matching mapper. **Do not** replace the arguments with a single `List<Long>` passed to `IN (?)` assuming `JdbcTemplate` expands it into three `?` markers. In plain `JdbcTemplate`, one marker receives one value; a collection may be treated by the driver as an object/array incompatible with `BIGINT`.

When `ids` has dynamic length, two common valid approaches are:

1. Generate exact `N` `?` markers and exact `N` values when using positional JDBC; put placeholder creation in a dedicated method and keep the args list synchronized.
2. Use `NamedParameterJdbcTemplate` with `IN (:ids)`. Spring supports expanding a `List` into the matching number of placeholders, subject to DBMS/driver limits.

Example of the second approach:

```java
import java.util.List;
import java.util.Map;

List<Long> ids = List.of(7L, 8L, 9L);
List<Product> found = namedJdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE id IN (:ids) ORDER BY id",
    Map.of("ids", ids),
    MAPPER
);
```

This snippet uses an existing `NamedParameterJdbcTemplate namedJdbc` and `RowMapper<Product> MAPPER`. Spring can turn `:ids` into `?, ?, ?` and bind all three values.

**Empty list case:** SQL `IN ()` is not portable and may be invalid syntax. Applications should define policy before execution, e.g., returning `List.of()` without querying if the ID list is empty. For very long lists, DBMS/driver bind-parameter limits and query performance can become an issue; consider chunking or DB-specific techniques.

### When List Size Changes, Question-Mark Count Must Change Too

Dynamic SQL assembly bugs often happen when code builds a fixed `"IN (?, ?)"` string while passing a three-element ID set. Ensure SQL is generated from **the exact same data source** used to build the args list. Never truncate elements to avoid errors without a business rule.

## 10. Dynamic WHERE: Build SQL and Args in the Same Conditional Branch

Practical requirement: search products by `active` (nullable meaning no filter) and minimum price (also optional).

A clean Spring JDBC pattern:

```java
public List<Product> search(Boolean active, BigDecimal minimumPrice) {
    StringBuilder sql = new StringBuilder(
        "SELECT id, sku, name, price, stock, active, discount " +
        "FROM products WHERE 1=1"
    );
    List<Object> args = new java.util.ArrayList<>();

    if (active != null) {
        sql.append(" AND active = ?");
        args.add(active);
    }
    if (minimumPrice != null) {
        sql.append(" AND price >= ?");
        args.add(minimumPrice);
    }

    sql.append(" ORDER BY id");
    return jdbc.query(sql.toString(), MAPPER, args.toArray());
}
```

This is a **method placed inside `ProductRepository`** from section 7, where `List` and `BigDecimal` are imported and `jdbc`/`MAPPER` exist. Because every branch appends SQL and value together, marker count and `args` element count always stay aligned in this logic.

Four cases:

| `active` | `minimumPrice` | Markers | Args List |
| --- | --- | ---: | --- |
| null | null | 0 | empty |
| true | null | 1 | `[true]` |
| null | 40.00 | 1 | `[BigDecimal("40.00")]` |
| false | 40.00 | 2 | `[false, BigDecimal("40.00")]` |

If a branch appends `AND price >= ?` without adding the value to `args`, the statement is missing a bind. If it adds to `args` without appending `?`, the statement has an extra bind. **When refactoring dynamic SQL conditions, always edit both sides in the same code branch and test every filter combination.**

Avoid concatenating user data values directly into `StringBuilder`. The pattern above only appends **developer-controlled fixed SQL fragments**, while values still go through placeholders, helping prevent SQL injection.

### LIKE and Special Characters

```java
List<Product> found = jdbc.query(
    "SELECT id, sku, name, price, stock, active, discount " +
    "FROM products WHERE name LIKE ? ORDER BY id",
    MAPPER,
    "Note%"
);
```

There is **one marker** and one Java value `"Note%"`. If matching a prefix from input, code can construct a pattern from `prefix + "%"` and bind it. However, `%` and `_` inside user values act as `LIKE` wildcards; to search literally, escape them per SQL/dialect rules with an appropriate `ESCAPE` clause. Parameter binding stops input from altering SQL structure, yet **does not automatically escape LIKE wildcards**.

## 11. Batch Updates: Same SQL, Every Row Must Have Enough Parameters

Batching sends multiple parameter sets for one SQL statement. The fundamental requirement is that **every value set matches the same marker count and target types**.

Example inside a method that already has `JdbcOperations jdbc`:

```java
String sql = "UPDATE products SET stock = ? WHERE id = ?";

int[] counts = jdbc.batchUpdate(
    sql,
    List.of(
        new Object[] {4, 7L},
        new Object[] {9, 8L},
        new Object[] {0, 9L}
    )
);
```

Each element is a **two-value** array: `INTEGER` stock first, `BIGINT` id second. If one element only has one value, interacting with the driver may fail due to a missing bind. The `int[] counts` result contains affected row counts (or JDBC sentinel values like `Statement.SUCCESS_NO_INFO`) for each batch entry per driver rules.

When special SQL types are needed or strict index-based binding is preferred, `JdbcTemplate.batchUpdate(String, BatchPreparedStatementSetter)` lets you call setters at each position. Example with an injected `JdbcTemplate jdbcTemplate`:

```java
List<Long> ids = List.of(7L, 8L);

int[] counts = jdbcTemplate.batchUpdate(
    "UPDATE products SET active = ? WHERE id = ?",
    new org.springframework.jdbc.core.BatchPreparedStatementSetter() {
        @Override
        public void setValues(java.sql.PreparedStatement ps, int i)
                throws java.sql.SQLException {
            ps.setBoolean(1, true);
            ps.setLong(2, ids.get(i));
        }

        @Override
        public int getBatchSize() {
            return ids.size();
        }
    }
);
```

This snippet is inside a method with variable `jdbcTemplate` of type **`JdbcTemplate`** (not only the `JdbcOperations` interface if using a specific overload), and `List` imported. The Java list index **`i` starts at 0**, whereas the JDBC **parameter index in `PreparedStatement` starts at 1**.

**Batching does not automatically guarantee an atomic transaction.** If all updates must commit or roll back together, configure a Spring transaction manager and an appropriate `@Transactional` boundary; driver and auto-commit settings govern behavior when no active transaction exists.

## 12. Common Failure Scenarios and Distinguishing Errors

| Scenario | Observable Symptom | Fix |
| --- | --- | --- |
| SQL has 3 `?` but 2 values passed | Driver reports unbound parameter on execute | Count markers and label positions 1..N |
| SQL has 2 `?` but 3 values passed | Driver reports out-of-bounds index/parameter | Remove extra value or intentionally update SQL |
| `status` and `note` values swapped, both `VARCHAR` | May throw no exception, wrong data written | Review mapping in SQL order, test persisted data |
| Passing invalid `String` to `DECIMAL` | Conversion or constraint error depending on DB | Use `BigDecimal` and validation |
| Passing `null` when driver cannot infer SQL type | SQL type inference/driver exception | `SqlParameterValue` or `setNull(index, Types.XXX)` |
| `id = ?` assigned, yet Java passes ID elsewhere | Query returns 0 rows or updates wrong record | Inspect both SQL and args, log carefully |
| `IN (?)` receives a `List` | Conversion error or unexpected query | Expand placeholders or use named list |
| `LIKE ?` receives unintended `%`/`_` | Broader results than intended | Escape wildcards when literal search is needed |
| Using `?` for table/column names | SQL does not act as dynamic identifier | Allow-list permitted column names/options |
| `queryForObject` has right params yet 0 rows | `EmptyResultDataAccessException` | Handle "not found" contract separately |
| `update` has right params yet 0 rows affected | `update` returns 0 | Check key/`WHERE` and business rules |
| Java value has right type yet exceeds `VARCHAR`/`DECIMAL` | Constraint/truncation error or driver behavior | Check length, precision, scale, DB constraints |

**Distinguish three categories:** *binding errors*, *data errors*, and *valid business outcomes*. A query returning an empty list does not by itself prove a missing bind parameter; all parameters may be bound properly while the filter matches no rows. Conversely, an update returning 1 does not prove semantically right writes if two same-typed columns had their values swapped.

### Do Not Over-Predict Specific Exception Subclasses

JDBC drivers typically throw `SQLException` with an SQLState and vendor error code. `JdbcTemplate` translates many errors into `DataAccessException`. Depending on the database and root cause, you may get `BadSqlGrammarException`, `DataIntegrityViolationException`, or another subclass/`UncategorizedSQLException`. **Do not encode business logic around a guessed error message or subclass for "missing parameter."** Better diagnostics compare the SQL statement, bind count, value order, SQL types, and underlying exception.

Avoid logging passwords, tokens, card numbers, or sensitive info inside parameters directly. For debugging, record operation name, parameter count, field names (when using named params), expected types, and SQLState where appropriate; log values only when security policy permits.

## 13. Testing Parameter Contracts with JDBC Integration Tests

Tests with mocks can catch a method calling `update` with the wrong argument count via verify/captor, yet **only DB integration tests** prove that SQL, driver, and schema accept the actual conversions. H2 is useful for fast checks; if production uses PostgreSQL/MySQL, add tests with the matching driver and DB (e.g., Testcontainers).

For the Spring Boot project in section 7, add the test dependency in `build.gradle`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Tests use `@JdbcTest` and `@Import(ProductRepository.class)` to include the repository and Spring JDBC in the slice test.

**`src/test/java/example/ProductRepositoryTest.java`:**

```java
package example;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcOperations;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(ProductRepository.class)
class ProductRepositoryTest {
    @Autowired
    JdbcOperations jdbc;

    @Autowired
    ProductRepository repo;

    @BeforeEach
    void setup() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(12,2) NOT NULL,
                stock INTEGER NOT NULL,
                active BOOLEAN NOT NULL,
                discount DECIMAL(12,2) NULL
            )
            """);
        jdbc.update("DELETE FROM products");
    }

    @Test
    void positionalArgumentsKeepValuesInCorrectColumns() {
        Product original = new Product(
            7L, "BK-7", "Notebook", new BigDecimal("49.90"),
            5, true, null
        );

        assertEquals(1, repo.insert(original));
        assertEquals(1, repo.renameAndStock(7L, "Notebook Pro", 8));

        Product after = repo.findById(7L).orElseThrow();
        assertEquals("BK-7", after.sku());
        assertEquals("Notebook Pro", after.name());
        assertEquals(new BigDecimal("49.90"), after.price());
        assertEquals(8, after.stock());
        assertTrue(after.active());
        assertNull(after.discount());
    }

    @Test
    void nullableDecimalUsesAnExplicitSqlType() {
        Product original = new Product(
            8L, "BK-8", "Draft", new BigDecimal("30.00"),
            1, false, null
        );
        assertEquals(1, repo.insert(original));
        assertEquals(1,
            repo.setDiscount(8L, new BigDecimal("5.00")));
        assertEquals(new BigDecimal("5.00"),
            repo.findById(8L).orElseThrow().discount());
        assertEquals(1, repo.setDiscount(8L, null));
        assertNull(repo.findById(8L).orElseThrow().discount());
    }

    @Test
    void multipleQueryParametersKeepExpectedOrder() {
        repo.insert(new Product(
            9L, "BK-9", "Blue Pen", new BigDecimal("10.00"),
            3, true, null
        ));
        repo.insert(new Product(
            10L, "BK-10", "Notebook", new BigDecimal("50.00"),
            3, true, null
        ));
        repo.insert(new Product(
            11L, "BK-11", "Notebook Black", new BigDecimal("60.00"),
            3, false, null
        ));

        var found = repo.findActiveAtLeast(new BigDecimal("40.00"));
        assertEquals(1, found.size());
        assertEquals(10L, found.get(0).id());
    }
}
```

Run:

```bash
./gradlew test
```

On Windows use `gradlew.bat test`. With Spring Boot 3.3+, JUnit 5, and H2 configured, **3 tests are expected to pass** provided no conflicting schema/test configurations exist. `@JdbcTest` typically uses an embedded database and transaction rollback per test; `@Import` provides the repository bean for Spring to inject.

The tests verify **values stored in columns after execution**, not merely asserting that code throws no exceptions. The third test specifically uses sufficiently distinct data to detect swapping `active` and `minimumPrice` if SQL could coerce types. To test missing/excess markers, you can add negative tests against the real production JDBC driver asserting an exception, without hardcoding a specific subclass unless guaranteed by the driver.

### Checklist Before Merging an SQL Change

1. Number all parameter markers in order of appearance, or list all `:param` names.
2. Verify value count matches required marker/name count with nothing omitted.
3. Verify the `i`-th value belongs to the `i`-th SQL expression/column.
4. Check SQL types, nullability, precision, scale, length, and constraints.
5. For dynamic SQL, inspect every toggled condition combination; SQL and args must be built in the same logic.
6. For `IN`, verify empty lists and long lists, actual placeholder counts, and DBMS limits.
7. For SQL with dynamic identifiers, pull names solely from an allowlist, never raw input into the SQL statement.
8. For batches, every item must follow the same marker/type contract.
9. Have integration tests verifying **actual values after write/query**, including same-typed parameters that are easy to swap.
10. Check errors at the appropriate layer; do not confuse "0 rows" / "0 rows updated" with binding errors.
11. Never use logs containing sensitive data to debug parameter bugs.
12. Review SQL/drivers when changing environments; a statement running on H2 may not run on another DBMS.

## 14. Self-Check Questions

**Question 1.** How many Java values does `UPDATE orders SET status = ?, total = ? WHERE id = ?` require, and in what order?

**Answer:** Three values: `status` (String/VARCHAR), `total` (BigDecimal/DECIMAL), `id` (Long/BIGINT). `id` is position 3 even if it is the first parameter in the business method signature.

**Question 2.** An SQL statement has three `?` markers, yet Java passes only two values. Does `JdbcTemplate` automatically treat the missing parameter as SQL NULL?

**Answer:** No. All positions must be bound. A missing value usually makes the driver fail before or on execute; to pass SQL NULL, you must still bind **a parameter** with null value and an appropriate SQL type.

**Question 3.** If you pass `"129.50"` (String) instead of `BigDecimal("129.50")` for a `DECIMAL` column, is it guaranteed to fail every time?

**Answer:** No. Some DBMSs/drivers may implicitly cast and succeed, while others throw an error. Relying on implicit casts lacks portability; choose `BigDecimal` for clarity and exactness.

**Question 4.** Why is swapping `status` and `note`, both `String`s, dangerous?

**Answer:** The statement can execute successfully because count and SQL types are valid, yet data is written into the wrong columns. Test actual persisted values, not only absence of exceptions.

**Question 5.** In `IN (?)`, does passing `List.of(1L, 2L, 3L)` as a single `JdbcTemplate` parameter automatically turn into three markers?

**Answer:** No. With positional `JdbcTemplate`, three separate markers/values are needed; `NamedParameterJdbcTemplate` provides list expansion for `IN (:ids)`.

**Question 6.** When the `active` filter is not provided, how can a dynamic SQL query omit that condition?

**Answer:** Do not append `AND active = ?` and do not add `active` to `args`. When the condition is present, add **both the SQL fragment and the value** in the same branch.

**Question 7.** What else might a Java `null` passed for a `DECIMAL` column need besides supplying a null value?

**Answer:** An explicit SQL type, such as `new SqlParameterValue(Types.DECIMAL, null)` or `ps.setNull(index, Types.DECIMAL)`. This tells the driver the target type when it cannot infer it from the Java value.

**Question 8.** Why does `jdbc.update(...)` returning 0 not by itself prove a missing parameter?

**Answer:** Because 0 is the affected row count. The SQL may be bound completely correctly while `WHERE` matches no rows; binding errors surface distinctly at the driver/SQL layer.

**Question 9.** In `BatchPreparedStatementSetter.setValues(PreparedStatement ps, int i)`, do `i=0` and `ps.setLong(1, value)` contradict each other?

**Answer:** No. `i` is the 0-based Java list index; JDBC parameter indexing starts at 1.

**Question 10.** With named params, is `Map.of("note", null)` a valid way to pass SQL NULL?

**Answer:** No. `Map.of` forbids null. Use `MapSqlParameterSource` with `addValue("note", null, Types.VARCHAR)`, or another parameter source supporting nulls and the proper SQL type.

## References

- [Java SE 21 — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): 1-based parameter indices, typed setters, `setNull`, and `getParameterMetaData`.
- [Java SE 21 — Types](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Types.html): SQL type codes such as `BIGINT`, `VARCHAR`, `DECIMAL`, `BOOLEAN`, and `NULL`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, positional/named params, queries/updates, and callback handling.
- [Spring Framework — Parameter Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): specifying SQL types via `argTypes` arrays, `SqlParameterValue`, and `SqlParameterSource`, especially for null values.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `update`, `query`, `batchUpdate` overloads.
- [Spring Framework — NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): replacing named params with positional markers and `List` expansion.

**Takeaway:** Every placeholder must have **exactly one value at the right position or name, with a compatible SQL type**. When code changes SQL conditions, update the args list at the same time. When encountering `NULL`, specify the SQL type where needed. For dynamic SQL or multiple same-typed values, write integration tests verifying real data rather than only checking that the statement runs without error.