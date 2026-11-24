# JdbcClient: Binding Positional or Named Parameters

> **Topic:** Spring Framework → data-access → **JdbcClient**. This lesson explains how to use both parameter binding styles within the same fluent API: **positional parameters** written with `?` and **named parameters** written as `:name`. You will learn how to pick the right `param`/`params`/`paramSource` overload, determine binding order, declare SQL/NULL types, pass lists into `IN`, understand the role of `JdbcTemplate` and `NamedParameterJdbcTemplate` underneath, and practice with Java 21, Spring Boot, Spring JDBC, and H2.

## 1. The Problem: One SQL Statement, Two Ways to Supply Values

Suppose a book-selling system needs to query products by **category** and **minimum price**. With JDBC, SQL should separate query structure from application-supplied data to avoid dangerous string concatenation.

**Approach A — positional parameters:**

~~~sql
SELECT id, sku, category, price, stock
FROM inventory_item
WHERE category = ?
  AND price >= ?
ORDER BY id;
~~~

~~~java
// Fragment: jdbcClient is org.springframework.jdbc.core.simple.JdbcClient.
// Illustrates syntax only; a complete runnable project is in section 10.
List<Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = ? AND price >= ?
        ORDER BY id
        """)
    .param("BOOK")
    .param(new BigDecimal("80.00"))
    .query(ITEM_MAPPER)
    .list();
~~~

**Approach B — named parameters:**

~~~sql
SELECT id, sku, category, price, stock
FROM inventory_item
WHERE category = :category
  AND price >= :minPrice
ORDER BY id;
~~~

~~~java
List<Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        ORDER BY id
        """)
    .param("minPrice", new BigDecimal("80.00"))
    .param("category", "BOOK")
    .query(ITEM_MAPPER)
    .list();
~~~

Both queries express **the exact same data condition**. In Approach A, `param(value)` registers values **in the order of `?` placeholders** in the SQL. In Approach B, `param("name", value)` registers values **by name**; the order of `param` calls can differ from the order the names appear in SQL.

`JdbcClient` was introduced in **Spring Framework 6.1**. It provides a **fluent facade** for common JDBC query/update operations, unifying two parameter styles that developers previously used separately through `JdbcTemplate` and `NamedParameterJdbcTemplate`. Both underlying frameworks/templates still perform the execution; there is no third JDBC placeholder style.

### Lesson Objectives

After this lesson, you will be able to:

1. Read a SQL statement and determine whether to use `param(Object)`, `param(int, Object)`, or `param(String, Object)`.
2. Use `params(Object...)`/`params(List<?>)` for positional and `params(Map<String, ?>)` for named parameters accurately.
3. Use `paramSource(Object)`/`paramSource(SqlParameterSource)` when you have a DTO, record, or data with SQL type declarations.
4. Understand how repeated `:discount` and `IN (:categories)` lists expand into `?` markers.
5. Know why not to mix named and indexed parameters in **the same statement**.
6. Manage `NULL` types, affected row counts, SQL injection, and JDBC lifecycle.

## 2. Inside the Flow Beneath JdbcClient

~~~mermaid
flowchart TD
    A["Repository calls jdbcClient.sql(sql)"] --> B["JdbcClient.StatementSpec"]
    B --> C{"What kind of SQL and parameters?"}
    C -- "Positional ?" --> D["JdbcTemplate / JDBC indexed parameters"]
    C -- "Named :name" --> E["NamedParameterJdbcTemplate"]
    E --> F["Parse SQL, convert names to ?, expand IN if needed"]
    F --> D
    D --> G["PreparedStatement on Spring-managed Connection"]
    G --> H["Bind values + SQL types"]
    H --> I["Execute SQL via JDBC driver / DBMS"]
    I --> J["update count or ResultSet → query mapping"]
~~~

**Key point:** Named vs. positional only differs in **how parameters are expressed and prepared before JDBC execution**. Ultimately, both common paths go through `PreparedStatement` with `?` placeholders at the JDBC layer.

- **`JdbcClient.sql(sql)`** creates an operation specification; it does not run SQL immediately.
- Calling **`param`, `params`, `paramSource`** attaches values and metadata.
- **`query(...)`** chooses how to read/map results; `list()`, `single()`, `optional()` (depending on the QuerySpec) execute the operation when results are requested.
- **`update()`** executes DML and returns the **number of affected rows**.
- Spring is responsible for acquiring/releasing the Connection through the DataSource, creating and cleaning up Statements, translating `SQLException`, and participating in upper-layer-managed transactions.

Do not confuse the **binding** phase with **commit**: using `JdbcClient` does not automatically create a transaction boundary for an entire multi-query use case. Transactions still need to be organized in the application service when business logic requires them.

## 3. Key API: `JdbcClient.StatementSpec`

`jdbcClient.sql("...")` returns a `JdbcClient.StatementSpec`. Core overloads in Spring Framework 6.1/6.2:

| API | Binding style | Meaning |
| --- | --- | --- |
| `param(Object value)` | Implicit positional | Appends the next value in the order of `?` markers |
| `param(int jdbcIndex, Object value)` | Explicit positional | Places a value at a specific JDBC position, starting from **1** |
| `param(int jdbcIndex, Object value, int sqlType)` | Positional + SQL type | E.g., binding `NULL` of type `VARCHAR` at position 2 |
| `params(Object... values)` | Multiple positional | Binds positional values in order |
| `params(List<?> values)` | Multiple positional | Each List element is one value for one `?` marker |
| `param(String name, Object value)` | Named | Binds value to `:name` placeholder |
| `param(String name, Object value, int sqlType)` | Named + SQL type | Explicitly specifies JDBC type if needed |
| `params(Map<String, ?> paramMap)` | Multiple named | Adds a key-value map for named placeholders |
| `paramSource(Object namedParamObject)` | Named source | Extracts properties/record components or Map from an object |
| `paramSource(SqlParameterSource source)` | Named source + types | Uses `MapSqlParameterSource` and SQL type metadata |

These methods return `StatementSpec` for chaining. `JdbcClient` itself can be injected as a reusable bean; conversely, each `sql(...)` call should create a specification tailored to **one specific operation**—never keep a shared mutable `StatementSpec` as a global variable across requests.

**Distinguish by signature:** `param("category", "BOOK")` has **two arguments** and the first is a `String`, so it is a named parameter. `param(2, "BOOK")` also has **two arguments** but the first is an `int`, so it is the **2nd JDBC position**. Two overloads with similar shape have completely different meanings.

## 4. Positional Parameters: `?` and Sequential Binding

### 4.1. `param(value)`: For One or a Few Parameters

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = ? WHERE id = ?"
    )
    .param(9)
    .param(2L)
    .update();
~~~

The SQL has the first `?` for `stock` and the second `?` for `id`. Therefore:

| JDBC index | SQL column/condition | Value |
| --- | --- | --- |
| 1 | `SET stock = ?` | `9` |
| 2 | `WHERE id = ?` | `2L` |

If you call `.param(2L).param(9)` and the types happen to be compatible, the SQL may still run and write wrong values. The positional API **does not look at Java variable names** to fix the order automatically.

### 4.2. `params(Object...)`: Registering Multiple Values at Once

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = ? WHERE id = ?"
    )
    .params(9, 2L)
    .update();
~~~

Semantically, the two `param(value)` calls above are equivalent to one `params(9, 2L)` call. For SQL with multiple placeholders, keep them adjacent in exact order rather than scattering unannotated values across multiple places.

### 4.3. `params(List<?>)`: Still **Multiple Positions**, Not Automatic `IN`

~~~java
List<Object> values = List.of("BOOK", new BigDecimal("80.00"));

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = ? AND price >= ?
        ORDER BY id
        """)
    .params(values)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**A List with two elements binds to two `?` placeholders in order.** Do not confuse this method with `.param("ids", List.of(...))` for named parameters, as the latter can expand a list inside SQL `IN (:ids)`.

Notably, `Map.of`/`List.of` reject `null` values; when binding NULL, use a typed param API or a collection suited to your needs.

### 4.4. `param(jdbcIndex, value)`: Explicit Index Registration

In JDBC, positions **start at 1**, not 0:

~~~java
int changed = jdbcClient.sql(
        "UPDATE inventory_item SET stock = stock + ? WHERE id = ?"
    )
    .param(2, 2L)  // Position 2: id
    .param(1, 3)   // Position 1: stock increment amount
    .update();
~~~

Even though the methods are called in order **2 then 1**, the binding into `PreparedStatement` is still right: the first `?` receives 3, the second `?` receives 2L. This is the difference between **method call order** and **explicitly specified position**. Use this style only when it clarifies intent; for very short SQL, `params(3, 2L)` can be cleaner.

**Do not use `param(0, ...)`.** Index 0 is not a valid JDBC position. When using explicit indices, make sure every required `?` has a value and no non-existent position is bound.

## 5. Named Parameters: `:name`

### 5.1. How to Write Them

~~~java
List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = :category
          AND price >= :minPrice
        ORDER BY id
        """)
    .param("minPrice", new BigDecimal("80.00"))
    .param("category", "BOOK")
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

The names `category` and `minPrice` in the Java calls **do not include `:`**. Values are looked up by name, not by `param(...)` call order. This model is easier to maintain when there are many conditions or long SQL statements.

### 5.2. How Spring Converts Named Parameters to `?`

Given the SQL:

~~~sql
UPDATE inventory_item
SET price = price - :discount
WHERE id = :id AND price >= :discount;
~~~

And:

~~~java
jdbcClient.sql(sql)
    .param("id", 1L)
    .param("discount", new BigDecimal("20.00"))
    .update();
~~~

The named parameter processor replaces both occurrences of `:discount` and the one occurrence of `:id` with `?` in **order of appearance in SQL**:

~~~sql
UPDATE inventory_item
SET price = price - ?
WHERE id = ? AND price >= ?;
~~~

| JDBC position | Original name | Value |
| --- | --- | --- |
| 1 | `discount` | `20.00` |
| 2 | `id` | `1L` |
| 3 | `discount` | `20.00` |

There are **2 unique names but 3 JDBC positions**. Spring must bind `discount` to both position 1 and position 3. This is a benefit of named parameters when one value is used multiple times: the developer declares **only one key**.

### 5.3. Do Not Treat Named Binding as SQL Text Substitution

`NamedParameterJdbcTemplate` uses a parser to distinguish placeholders from SQL inside literals or comments. The framework does not take the name and splice the value into SQL—for instance, it **does not** turn `:category` into raw `'BOOK'` via `String.replace`. Instead, the final JDBC SQL contains `?`, while values and SQL types are bound separately. SQL containing colons inside literals, comments, or syntax like PostgreSQL `::` should be handled properly by the parser/driver rather than custom regex replacements.

Named parameters in Spring JDBC look similar to JPA/JPQL `:name`, but **they are not the same API or parser**. This lesson covers `JdbcClient` and Spring JDBC.

## 6. `params(Map<String, ?>)`, `paramSource(Object)`, and `SqlParameterSource`

### 6.1. Passing a Map with Multiple Names

~~~java
Map<String, ?> values = Map.of(
    "category", "BOOK",
    "minPrice", new BigDecimal("80.00")
);

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        ORDER BY id
        """)
    .params(values)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Regardless of the order in which the Map stores keys, Spring binds according to the placeholder positions appearing in the SQL. `params(Map)` is for **named** parameters, whereas `params(List)` or `params(Object...)` are for **positional** parameters.

### 6.2. `paramSource(Object)` from a Record

Suppose a record represents filter criteria:

~~~java
public record PriceFilter(String category, BigDecimal minPrice) {}
~~~

You can write:

~~~java
PriceFilter filter = new PriceFilter(
    "BOOK", new BigDecimal("80.00")
);

long count = jdbcClient.sql("""
        SELECT COUNT(*) FROM inventory_item
        WHERE category = :category AND price >= :minPrice
        """)
    .paramSource(filter)
    .query(Long.class)
    .single();
~~~

In Spring JDBC 6.1+, `JdbcClient`'s property source mechanism can extract **record components** such as `category` and `minPrice`. This is a helpful option when the application already has an input object whose property names match the named placeholders. Record component names must match; an arbitrary object will not automatically supply parameters if its fields/properties are inaccessible.

`paramSource(Object)` only **reads values**; it does not force you to use entities/JPA or push domain objects down to the SQL layer. Keep SQL responsibility in the Repository/DAO and use DTOs/query objects when needed.

### 6.3. `paramSource(SqlParameterSource)` with SQL Types

`MapSqlParameterSource` implements `SqlParameterSource`, allowing you to attach `java.sql.Types` alongside values:

~~~java
MapSqlParameterSource source = new MapSqlParameterSource()
    .addValue("id", 2L, Types.BIGINT)
    .addValue("note", null, Types.VARCHAR);

int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = :note WHERE id = :id"
    )
    .paramSource(source)
    .update();
~~~

This is explicit when multiple named parameters need specific SQL types or hold SQL `NULL` values. For a single NULL, `param("note", null, Types.VARCHAR)` is usually shorter.

**Do not do:** `Map.of("note", null)`, because `Map.of` throws an exception on null values. Also do not equate "missing key `note`" with "key `note` exists with null value": those two states differ when Spring prepares the binding.

## 7. `IN (:categories)` Lists and a Crucial Distinction

Named parameters support passing a `Collection` to a placeholder in an `IN` condition:

~~~java
List<String> categories = List.of("BOOK", "DEVICE");

List<String> skus = jdbcClient.sql("""
        SELECT sku FROM inventory_item
        WHERE category IN (:categories)
          AND price >= :minPrice
        ORDER BY id
        """)
    .param("categories", categories)
    .param("minPrice", new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

Because `categories` has two elements, the condition expands to JDBC SQL equivalent to:

~~~sql
WHERE category IN (?, ?)
  AND price >= ?
~~~

The final three positions receive `"BOOK"`, `"DEVICE"`, and `80.00` in order. A **named placeholder** holding a list can generate **multiple `?` markers**. This differs from `.params(List.of("BOOK", "DEVICE"))` used for positional SQL that already has two `?` markers; `params(List)` does not rewrite the SQL string.

### Empty Lists Are a Business Decision

`IN ()` is invalid in many SQL dialects. If an empty categories filter means "no category selected", return an empty list immediately:

~~~java
public List<String> findByCategories(List<String> categories) {
    if (categories.isEmpty()) {
        return List.of();
    }
    return jdbcClient.sql(
            "SELECT sku FROM inventory_item " +
            "WHERE category IN (:categories) ORDER BY id"
        )
        .param("categories", categories)
        .query((rs, rowNum) -> rs.getString("sku"))
        .list();
}
~~~

Do not silently drop the `WHERE category IN (...)` condition when the list is empty, as that could return **the entire table** contrary to requirements. For very large lists, watch out for driver/DBMS limits on bind variables/SQL length, query performance, and `IN` element limits; consider chunking, temporary tables, or vendor-specific solutions if needed.

### A Named List Is Not a SQL Array

A `List` in `IN (:categories)` is expanded by Spring into multiple placeholders; it does not mean passing a single SQL ARRAY like PostgreSQL `ANY(?)`. If you truly need a JDBC array, use the appropriate driver API and SQL type. Do not conflate the two concepts.

## 8. One SQL Statement: Choose **One** Binding Style, Do Not Mix

`JdbcClient` is a facade supporting **both styles**, but that does not mean a single SQL statement should mix both. Counter-example:

~~~java
// COUNTER-EXAMPLE: do not mix ? with :category in the same SQL.
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = :category AND price >= ?"
    )
    .param("category", "BOOK")
    .param(new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

This style lacks a consistent named-to-indexed mapping for the same `StatementSpec`; depending on the processing path, Spring rejects mixing named parameters and traditional `?`. Choose one clear version:

**Positional only:**

~~~java
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = ? AND price >= ?"
    )
    .params("BOOK", new BigDecimal("80.00"))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**Named only:**

~~~java
jdbcClient.sql(
        "SELECT sku FROM inventory_item " +
        "WHERE category = :category AND price >= :minPrice"
    )
    .params(Map.of(
        "category", "BOOK",
        "minPrice", new BigDecimal("80.00")
    ))
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

**Rule of thumb:** For a single `jdbcClient.sql(...)`, choose `?`-style SQL **or** `:name`-style SQL, and use the matching bind methods. Different calls inside **the same Repository** can choose different styles; the restriction applies only **within a single statement/query**.

## 9. Binding SQL Types, NULL, BigDecimal, and Input Data

### 9.1. Typed `NULL` for Positional Parameters

~~~java
int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = ? WHERE id = ?"
    )
    .param(1, null, Types.VARCHAR)
    .param(2, 1L, Types.BIGINT)
    .update();
~~~

Here `Types.VARCHAR` guides JDBC on the SQL type of NULL. Although some drivers can infer the type, explicit declaration is often helpful for nullable columns, special procedures/drivers, or ambiguous expressions.

### 9.2. Typed `NULL` for Named Parameters

~~~java
int updated = jdbcClient.sql(
        "UPDATE inventory_item SET note = :note WHERE id = :id"
    )
    .param("note", null, Types.VARCHAR)
    .param("id", 1L, Types.BIGINT)
    .update();
~~~

The two examples have the same purpose but select different overloads. Do not pass `param("note", "null")` if you want SQL NULL: the string `"null"` is text data, not a NULL value.

### 9.3. Prices and Monetary Amounts

Product prices are typically modeled with `BigDecimal` and SQL column `DECIMAL(12,2)`:

~~~java
BigDecimal price = new BigDecimal("89.50");

jdbcClient.sql(
        "UPDATE inventory_item SET price = :price WHERE id = :id"
    )
    .param("price", price)
    .param("id", 2L)
    .update();
~~~

Avoid `double` when calculations require exact decimal monetary precision. For `LocalDate`, `Instant`, `OffsetDateTime`, or SQL ARRAY/JSON/UUID, check the driver's mapping and actual SQL type; named parameters do not automatically solve timezones or vendor-specific data types.

### 9.4. Values Are Not Identifiers

Placeholders represent **data values**; they cannot bind table/column names or `ORDER BY` syntax:

~~~sql
-- DO NOT use :tableName to represent a SQL identifier:
SELECT * FROM :tableName;

-- :column is just a value, not a column name to sort by:
SELECT sku FROM inventory_item ORDER BY :column;
~~~

If the user can choose a sort column, use a whitelist in code to build the SQL identifier part safely while still binding filter values:

~~~java
String column = switch (sortBy) {
    case "price" -> "price";
    case "sku" -> "sku";
    default -> "id";
};

String sql =
    "SELECT id, sku FROM inventory_item " +
    "WHERE category = :category ORDER BY " + column;
~~~

This is a fragment; `sortBy` comes from input controlled by the switch, **not** arbitrary concatenation from a request. Binding `:category` still prevents SQL injection for the **value**, not for any un-whitelisted SQL you concatenate yourself.

## 10. Complete Runnable Example: Java 21, Spring Boot 3.3.5, JdbcClient, H2

The example below includes both styles inside **one Repository** to show that each statement can pick the fitting binding style. All classes/files are provided to build a standalone project. The console application needs no HTTP server, Docker, or PostgreSQL. With Spring Boot 3.3.5 and a configured `DataSource`, `JdbcClient` can be auto-configured and injected directly.

### 10.1. File Layout

~~~text
jdbc-client-binding/
├── build.gradle
└── src/main/
    ├── java/com/example/jdbcclient/
    │   ├── JdbcClientBindingApplication.java
    │   └── InventoryRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 10.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

`spring-boot-starter-jdbc` brings Spring JDBC and the required connection pool; H2 provides the in-memory database/driver. `JdbcClient` is in the `org.springframework.jdbc.core.simple` package. The example pins versions for reproducibility; when building new systems, choose a supported Spring Boot version line and verify compatibility.

### 10.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:client_binding;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

### 10.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    category VARCHAR(30) NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    note VARCHAR(100)
);
~~~

### 10.5. `src/main/resources/data.sql`

~~~sql
INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (1, 'JAVA-17', 'BOOK', 120.00, 5, 'first');

INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (2, 'SPRING-CORE', 'BOOK', 89.50, 3, 'second');

INSERT INTO inventory_item (id, sku, category, price, stock, note)
VALUES (3, 'MOUSE', 'DEVICE', 40.00, 8, NULL);
~~~

### 10.6. Repository: `InventoryRepository.java`

~~~java
package com.example.jdbcclient;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {

    public record Item(
        long id, String sku, String category,
        BigDecimal price, int stock
    ) {}

    public record PriceFilter(String category, BigDecimal minPrice) {}

    private static final RowMapper<Item> ITEM_MAPPER =
        (rs, rowNum) -> new Item(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getString("category"),
            rs.getBigDecimal("price"),
            rs.getInt("stock")
        );

    private final JdbcClient jdbc;

    public InventoryRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    // Positional implicit binding: two ? markers, two values in SQL order.
    public List<Item> booksAtLeast(BigDecimal minPrice) {
        return jdbc.sql("""
                SELECT id, sku, category, price, stock
                FROM inventory_item
                WHERE category = ? AND price >= ?
                ORDER BY id
                """)
            .params("BOOK", minPrice)
            .query(ITEM_MAPPER)
            .list();
    }

    // Positional explicit binding: specify 1-based JDBC indices.
    public int addStockIndexed(long id, int delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        return jdbc.sql("""
                UPDATE inventory_item
                SET stock = stock + ?
                WHERE id = ?
                """)
            .param(2, id)
            .param(1, delta)
            .update();
    }

    // Named binding: :discount appears twice but is declared only once.
    public int discountNamed(long id, BigDecimal discount) {
        if (discount.signum() <= 0) {
            throw new IllegalArgumentException("discount must be positive");
        }

        return jdbc.sql("""
                UPDATE inventory_item
                SET price = price - :discount
                WHERE id = :id AND price >= :discount
                """)
            .param("id", id)
            .param("discount", discount)
            .update();
    }

    // Named list expansion for IN (:categories).
    public List<String> availableSkus(
            List<String> categories, BigDecimal minPrice) {

        if (categories.isEmpty()) {
            return List.of();
        }

        return jdbc.sql("""
                SELECT sku FROM inventory_item
                WHERE category IN (:categories)
                  AND price >= :minPrice AND stock > 0
                ORDER BY id
                """)
            .params(Map.of(
                "minPrice", minPrice,
                "categories", categories
            ))
            .query((rs, rowNum) -> rs.getString("sku"))
            .list();
    }

    // A record as a named parameter source.
    public long countWithFilter(PriceFilter filter) {
        return jdbc.sql("""
                SELECT COUNT(*) FROM inventory_item
                WHERE category = :category AND price >= :minPrice
                """)
            .paramSource(filter)
            .query(Long.class)
            .single();
    }

    // Named NULL with explicit SQL type.
    public int clearNote(long id) {
        return jdbc.sql(
                "UPDATE inventory_item " +
                "SET note = :note WHERE id = :id"
            )
            .param("note", null, Types.VARCHAR)
            .param("id", id)
            .update();
    }

    public int stockBySku(String sku) {
        return jdbc.sql(
                "SELECT stock FROM inventory_item WHERE sku = :sku"
            )
            .param("sku", sku)
            .query(Integer.class)
            .single();
    }

    public BigDecimal priceBySku(String sku) {
        return jdbc.sql(
                "SELECT price FROM inventory_item WHERE sku = :sku"
            )
            .param("sku", sku)
            .query(BigDecimal.class)
            .single();
    }
}
~~~

### 10.7. Application: `JdbcClientBindingApplication.java`

~~~java
package com.example.jdbcclient;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JdbcClientBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcClientBindingApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstration(InventoryRepository repository) {
        return args -> {
            List<String> bookSkus = repository
                .booksAtLeast(new BigDecimal("80.00"))
                .stream()
                .map(InventoryRepository.Item::sku)
                .toList();
            System.out.println("Positional books = " + bookSkus);

            int indexedUpdated = repository.addStockIndexed(2L, 2);
            System.out.println("Indexed updated = " + indexedUpdated);
            System.out.println(
                "SPRING-CORE stock = " +
                repository.stockBySku("SPRING-CORE")
            );

            int namedUpdated = repository.discountNamed(
                1L, new BigDecimal("20.00")
            );
            System.out.println("Named updated = " + namedUpdated);
            System.out.println(
                "JAVA-17 price = " +
                repository.priceBySku("JAVA-17")
            );

            List<String> available = repository.availableSkus(
                List.of("BOOK", "DEVICE"), new BigDecimal("80.00")
            );
            System.out.println("Named IN SKUs = " + available);

            long count = repository.countWithFilter(
                new InventoryRepository.PriceFilter(
                    "BOOK", new BigDecimal("80.00")
                )
            );
            System.out.println("Record filter count = " + count);

            int cleared = repository.clearNote(1L);
            System.out.println("Typed null updated = " + cleared);
        };
    }
}
~~~

### 10.8. Running the Example

In the project directory containing `build.gradle`, use the Gradle Wrapper if present:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell: `.\gradlew.bat bootRun`. If there is no wrapper yet and a compatible Gradle version is installed: `gradle bootRun`. Java 21 must be installed or a Gradle toolchain configured to download/provide the JDK. The program runs on a fresh in-memory H2 database and prints the following lines (excluding Spring, HikariCP, and Gradle logs):

~~~text
Positional books = [JAVA-17, SPRING-CORE]
Indexed updated = 1
SPRING-CORE stock = 5
Named updated = 1
JAVA-17 price = 100.00
Named IN SKUs = [JAVA-17, SPRING-CORE]
Record filter count = 2
Typed null updated = 1
~~~

**Explanation of each result:**

1. The positional query `category = ?`, `price >= ?` with `"BOOK"` and `80.00` selects the two matching books: 120.00 and 89.50.
2. `addStockIndexed(2, 2)` binds `id` to JDBC index 2 and `delta` to index 1. Stock of SPRING-CORE increases from 3 to 5; exactly one row is affected.
3. `discountNamed(1, 20.00)` uses the same `:discount` name in two places: reduces JAVA-17 price from 120.00 to 100.00; the `price >= :discount` condition passes.
4. The categories list `["BOOK", "DEVICE"]` expands into two placeholders. The minimum price 80.00 excludes MOUSE at 40.00, leaving JAVA-17 and SPRING-CORE.
5. `PriceFilter` is a record with `category` and `minPrice`, so `paramSource(filter)` supplies those exact two named parameters. COUNT = 2.
6. `clearNote(1L)` uses typed SQL NULL for `note` and updates exactly one row.

Note: This demo explains binding and does not build a full Service layer, authorization, concurrency control, or complete discount business logic. In a real application, enforce idempotency, affected row checks, transaction boundaries, and caller authorization. **The code snippets have been statically checked for API/signatures; the output above is the expected result from the stated data and SQL, not the output of a test run recorded in this document.**

## 11. Direct Breakdown of Conversion: Positional and Named

| Case | SQL written in Java | Values supplied by app | Final JDBC SQL | Binding order |
| --- | --- | --- | --- | --- |
| Two positional | `category = ? AND price >= ?` | `params("BOOK", 80.00)` | Unchanged | `BOOK, 80.00` |
| Explicit index | `stock = stock + ? WHERE id = ?` | `param(2, 2L), param(1, 3)` | Unchanged | `3, 2L` |
| Two named | `category = :category AND price >= :min` | `param("min", 80), param("category","BOOK")` | `category = ? AND price >= ?` | `BOOK, 80` |
| Repeated name | `price = price - :d WHERE price >= :d` | `param("d", 5)` | `price = price - ? WHERE price >= ?` | `5, 5` |
| Named list | `category IN (:cats) AND price > :min` | `cats=[BOOK,DEVICE], min=80` | `category IN (?, ?) AND price > ?` | `BOOK, DEVICE, 80` |

The rows in the table describe **logical values and ordering**, not literal SQL strings spliced directly by Spring. The notation `80.00` represents a numeric value matching the SQL type, not necessarily requiring a JDBC driver to accept a Java `double`.

### Why Must a Repeated Named Condition Bind Multiple Positions?

JDBC `PreparedStatement` only understands **`?` positions**. When Spring turns `:d` appearing in two places into two `?` markers, the binder must supply the value of `d` to **both indices**. Likewise, a Map having only two keys does not mean the expanded SQL has only two placeholders.

### Ordering Matters in Practice

In positional code, if you reverse `params(80.00, "BOOK")`, the driver may throw a type error or the query may return no rows. In named code, `params(Map.of("min", 80.00, "category", "BOOK"))` is unaffected by the Map's key order. Therefore, for SQL with many parameters, consider named binding for readability.

## 12. Query Results and Mapping Choices

After binding, you must decide on the result shape. Common terminal syntax:

### Single Value Guaranteed to Return One Row

~~~java
long count = jdbcClient.sql(
        "SELECT COUNT(*) FROM inventory_item WHERE category = :category"
    )
    .param("category", "BOOK")
    .query(Long.class)
    .single();
~~~

`COUNT(*)` always returns one row in a query like this, so `single()` is the clearest choice. The underlying value may be `Long`/`Integer` depending on the requested mapping/class; `query(Long.class)` produces a `Long` via Spring's supported mapping.

### Not Found as a Normal Case

~~~java
Optional<String> sku = jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE id = ?"
    )
    .param(999L)
    .query(String.class)
    .optional();
~~~

If there is no row, `optional()` returns `Optional.empty()`; if there is more than one row, that violates the "0 or 1 row" expectation and can throw a result-size error. `single()` normally requires exactly one row; distinguish clearly between "not found" and "database error".

### List of Objects

~~~java
List<InventoryRepository.Item> items = jdbcClient.sql("""
        SELECT id, sku, category, price, stock
        FROM inventory_item
        WHERE category = :category ORDER BY id
        """)
    .param("category", "BOOK")
    .query((rs, rowNum) -> new InventoryRepository.Item(
        rs.getLong("id"),
        rs.getString("sku"),
        rs.getString("category"),
        rs.getBigDecimal("price"),
        rs.getInt("stock")
    ))
    .list();
~~~

Here `RowMapper<T>` separates `ResultSet` mapping logic from parameter binding logic. If the application wants automatic mapping into a record/class by column name, `query(Item.class)` can be used under Spring's supported mapping rules; with an explicit mapper, results and type conversions depend less on conventions.

### DML and Updated Row Count

~~~java
int affected = jdbcClient.sql(
        "UPDATE inventory_item SET stock = stock + :delta WHERE id = :id"
    )
    .param("delta", 1)
    .param("id", 2L)
    .update();

if (affected != 1) {
    throw new IllegalStateException(
        "Expected one item updated, found " + affected
    );
}
~~~

`update()` returns **the number of rows** affected by SQL INSERT/UPDATE/DELETE per JDBC semantics; it does not return a new record or ID. If generated keys are needed, `JdbcClient` also supports `update(KeyHolder)` and `update(KeyHolder, String... keyColumnNames)` in Spring 6.1; how keys are read must match the driver and number of generated keys.

## 13. Comparing JdbcClient with the Two Base Templates

| Need | JdbcTemplate | NamedParameterJdbcTemplate | JdbcClient |
| --- | --- | --- | --- |
| Bind `?` in order | Yes | Not primary focus | Yes: `param(value)`/`params(Object...)` |
| Bind `:name` | Not directly | Yes | Yes: `param("name", value)` |
| SQL type/typed NULL | Via `argTypes`, setter, or `SqlParameterValue` | Via `MapSqlParameterSource` | Via `param(..., sqlType)`/`paramSource` overloads |
| `IN` list parameter | Must generate matching number of `?` | Named Collection expansion | Yes via named path |
| Query and mapping | `query(sql, mapper, args...)` | `query(sql, source, mapper)` | `sql(sql).param(...).query(...).list()` |
| Update | `update(sql, args...)` | `update(sql, source)` | `sql(sql).param(...).update()` |
| Very specialized JDBC work | Broad callback API | Inherits delegation | Simple facade for common tasks |

`JdbcClient` does not replace every low-level capability. For instance, complex batch APIs, custom JDBC callbacks, and stored procedures may fit better with `JdbcTemplate`, `SimpleJdbcInsert`, or `SimpleJdbcCall`. Features in newer Spring versions may evolve; when using Spring Boot 3.3.x (Framework 6.1), rely on the exact Javadoc of your installed version.

### How to Create JdbcClient

A plain Spring Framework application can create it from a DataSource:

~~~java
JdbcClient jdbcClient = JdbcClient.create(dataSource);
~~~

Or create it from `JdbcOperations`/configured templates via the appropriate `create(...)` overload. With **Spring Boot 3.3** and a matching auto-configured `NamedParameterJdbcTemplate`, `JdbcClient` is normally auto-configured so it can be constructor-injected as in section 10's project. Do not create a separate `new DataSource` inside each Repository just to get a `JdbcClient`, as that loses the configured pool and active transactions.

## 14. Spring Transactions Do Not Depend on Parameter Style

These two calls:

~~~java
jdbcClient.sql("UPDATE inventory_item SET stock = ? WHERE id = ?")
    .params(4, 1L)
    .update();

jdbcClient.sql("UPDATE inventory_item SET stock = :stock WHERE id = :id")
    .param("stock", 5)
    .param("id", 2L)
    .update();
~~~

are both JDBC operations; choosing `?` or `:name` **does not determine transactions**. If both must commit or roll back together, the application service should define the transaction boundary:

~~~java
// Architectural fragment, requires importing @Service and @Transactional.
// InventoryRepository is a real Spring bean; not a standalone file.
@Service
public class InventoryService {
    private final InventoryRepository items;

    public InventoryService(InventoryRepository items) {
        this.items = items;
    }

    @Transactional
    public void adjustTwoItems(long firstId, long secondId) {
        int first = items.addStockIndexed(firstId, 2);
        int second = items.addStockIndexed(secondId, 3);

        if (first != 1 || second != 1) {
            throw new IllegalStateException("Inventory adjustment failed");
        }
    }
}
~~~

When the public method is called through a Spring proxy, a transaction manager matching the DataSource can coordinate both operations. An unchecked exception rolls back the transaction by default. In real applications, guard against non-proxied self-invocation, concurrent updates, transaction isolation, and validation/authorization.

**Do not call `connection.commit()` or `dataSource.close()` inside parameter-binding code.** `JdbcClient`/`JdbcTemplate` together with `DataSource`/the transaction manager own resource lifecycles; the Service owns use-case consistency.

## 15. Common Errors and How to Debug Them

| Issue | Cause | Solution |
| --- | --- | --- |
| SQL has two `?` markers but only one `param` is passed | Missing positional parameter | Count placeholders and bind all of them |
| Calling `param(0, value)` | JDBC index is 1-based | Start from index 1 |
| `params(minPrice, category)` when SQL is `category = ? AND price >= ?` | Wrong order | Bind in SQL order or switch to named |
| Using `param(":id", 5)` | Name in Java includes the colon | Use `param("id", 5)` |
| SQL uses `:minPrice`, map contains `minprice` | Name/case mismatch | Match SQL name and map key exactly |
| Mixing `?` and `:id` in one statement | Two inconsistent binding mechanisms | Choose one style per SQL statement |
| Confusing `params(List)` with `IN (:ids)` | Positional list and named expansion differ | Use `param("ids", ids)` for named IN |
| `IN (:ids)` with an empty List | May generate invalid SQL | Define an explicit empty branch |
| `Map.of("note", null)` | Java `Map.of` forbids NULL | Use `param(..., null, Types.X)` or `MapSqlParameterSource` |
| `WHERE note = :note` with SQL NULL | In SQL, `= NULL` is not true | Use `IS NULL` when matching NULL values |
| Binding a column name via `ORDER BY :column` | Param only represents a data value | Whitelist identifiers |
| SQL breaks in literals/comments containing `:` | Custom regex replacement or special syntax | Let Spring parse and check the specific SQL/dialect |
| Expecting `update()` to return the new ID | Confusing affected rows with generated keys | Use `KeyHolder` and the matching overload |
| An update affects 0 rows yet is treated as success | WHERE matched nothing or condition blocked it | Check row count and classify not-found/conflict |
| Multi-step statements not atomic | No transaction boundary | Use `@Transactional` on the application service |
| Creating a new JdbcClient/DataSource per request | Incorrect lifecycle/pooling | Use singleton beans and dependency injection |
| Too many elements in `IN` | Driver/DB has placeholder limits | Limit/chunk/use temp table or appropriate join |

### Three-Layer Debugging

1. **SQL shape:** Does it have the right number of `?` positions or `:name` placeholders? Are you trying to bind a column/table name?
2. **Values/types:** Are values in the right order (positional) or under the right keys (named)? Are there `NULL`s, `BigDecimal`s, or special SQL types?
3. **DB/transaction:** Which database does the SQL run against? How many rows were affected? Are constraints, permissions, timeouts, and transactions configured properly?

SQL/parameter logs must avoid printing passwords, auth tokens, payment data, and PII. Do not build a custom logger that splices literal values directly into SQL and then executes that SQL string.

## 16. SQL Injection and What Binding Actually Protects

Never concatenate user input into SQL:

~~~java
// COUNTER-EXAMPLE: vulnerable to SQL injection.
String sql =
    "SELECT sku FROM inventory_item WHERE category = '" +
    userCategory + "'";
~~~

Replace with:

~~~java
List<String> result = jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE category = :category"
    )
    .param("category", userCategory)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

In the correct version, `userCategory` is sent as a **PreparedStatement data value**. It is never concatenated into SQL grammar. Even if `userCategory` contains quotes, SQL keywords, or comment markers, it is still treated as a **value**, without altering query structure.

However, binding **does not solve every form of injection**. Dynamic SQL parts like table names, column names, sort directions, or `WHERE` fragments must still come from a whitelist or trusted DSL. Whether positional or named, placeholders only protect data that is actually bound.

With `LIKE`, put `%` in the pattern value when performing wildcard searches:

~~~java
String pattern = "%" + keyword + "%";

jdbcClient.sql(
        "SELECT sku FROM inventory_item WHERE sku LIKE :pattern"
    )
    .param("pattern", pattern)
    .query((rs, rowNum) -> rs.getString("sku"))
    .list();
~~~

If you need to match literal `%` or `_` characters entered by a user, escape wildcards according to your SQL dialect. Binding values prevents injection, but does not automatically change `LIKE` wildcard semantics.

## 17. Readability, Maintainability, and Performance

When choosing between positional and named parameters, prioritize **SQL clarity**, not just fewer Java characters:

- SQL with one or two `?` markers: `params(...)` is usually short and readable.
- SQL with many conditions or the same value repeated: named `:name` prevents ordering mistakes and duplicate value bindings.
- Input already in a record/filter object: `paramSource(filter)` can cut down boilerplate map code.
- `IN` conditions taking a variable-length List: named parameter expansion is convenient, though empty lists and DB limits must be guarded.
- Specialized JDBC statement/method options needed: use the corresponding lower-level API instead of forcing everything into the fluent client.

**Never conclude in absolute terms that named is slower or faster than positional.** Named parameters require parsing/rewriting SQL in the framework, though Spring caches parsed SQL; real-world performance is usually dominated by network round-trips, SQL query plans, indexes, returned data volume, transactions, and the JDBC driver. With `IN` lists of varying sizes, the resulting JDBC SQL has different numbers of `?` markers, so driver/DB plan caching can vary.

In code reviews, check that SQL and its params sit close together, parameter names are meaningful, values are not bound by guesswork ordering, and a single SQL query is not split across confusing helper methods.

## 18. Testing Binding: What Unit Tests Prove vs. What Needs a Database

A Repository unit test can mock `JdbcClient`, though mocking a long fluent chain sometimes makes tests brittle. For JDBC binding, an **integration test using H2** or a real database is usually far more valuable because it verifies SQL, bound values/types, and mapping.

### Scenarios to Cover

| Scenario | Test input | Expected outcome |
| --- | --- | --- |
| Positional in order | `category=BOOK, minPrice=80` | Returns two books |
| Positional explicit index | Bind index 2 before index 1 | Updates the right id and delta |
| Named in reversed registration order | `param("minPrice", ...).param("category", ...)` | Still returns the right results |
| Named repeated value | `:discount` in two places | Both positions receive the same value |
| Named List in IN | 2 categories | SQL executes and returns matching rows |
| Named empty List | `List.of()` | Per policy, no query / returns empty list |
| Typed NULL | `note = :note` with VARCHAR null | DB stores SQL NULL |
| Missing key | SQL requires `:id` but none supplied | Clear binding error |
| Case sensitivity | `:minPrice` vs key `minprice` | Does not silently bind wrong data |
| Injection-like input | String containing `' OR 1=1 --` | Treated as data value, query structure unchanged |
| SQL UPDATE 0 rows | Non-existent id | Returns 0, caller handles it |
| Transaction with two updates | Second update throws exception | Both roll back when in the same transaction |

### Additional Testing Checks You Can Add

In the section 10 project, you can add `testImplementation 'org.springframework.boot:spring-boot-starter-test'` and use `@SpringBootTest` (real context), creating proper fixtures/rollbacks per test. Separate test logic from the demo's `CommandLineRunner` data seeding/writes if tests run repeatedly. A test checking only `RowMapper` does not prove parameter binding; integration tests should invoke actual Repository methods and read back database rows to verify.

**Important for transaction tests:** If a test opens its own transaction and rolls it back at the end, ensure that does not mask missing transaction boundaries in application services. For concurrent updates or production databases, test with the real driver/database rather than inferring everything from H2.

## 19. Self-Check Exercises

**Question 1.** Is calling `WHERE category = ? AND price >= ?` with `params(new BigDecimal("80"), "BOOK")` correct?  
**Answer:** Wrong order. The first `?` corresponds to category and the second `?` corresponds to price. You must call `params("BOOK", new BigDecimal("80"))`.

**Question 2.** With `.param(2, id).param(1, stock)`, what does the JDBC index start from?  
**Answer:** From **1**; values bind by explicit index number, not by method invocation order.

**Question 3.** For `WHERE category = :category AND price >= :minPrice`, can `minPrice` be registered before `category`?  
**Answer:** Yes. Spring looks up parameters by **name**, then binds them to SQL in the order placeholders were parsed.

**Question 4.** Given `price = price - :d WHERE price >= :d`, how many unique names and how many JDBC positions are there?  
**Answer:** One unique name `d`, appearing twice, so there are **two `?` positions**.

**Question 5.** Does `params(List.of("BOOK", "DEVICE"))` automatically turn `IN (?)` into `IN (?, ?)`?  
**Answer:** No; the `params(List)` overload is for **a list of positional parameters**. For named list expansion, use `IN (:categories)` and `param("categories", List.of("BOOK", "DEVICE"))`.

**Question 6.** Can `Map.of("note", null)` bind NULL in named SQL?  
**Answer:** No. Java `Map.of` does not allow null. Use `param("note", null, Types.VARCHAR)` or `MapSqlParameterSource`.

**Question 7.** Does `ORDER BY :sortColumn` make SQL sort by a column name chosen by the user?  
**Answer:** No. A placeholder binds a **value**, not an identifier. Select the identifier via a whitelist in code.

**Question 8.** Can you use positional binding in one Repository method and named binding in another?  
**Answer:** Yes. You should not mix the two binding styles within **a single SQL statement/`StatementSpec`**, but independent operations can choose whichever style fits best.

**Hands-on exercise:** Add `updatePricePositional(long id, BigDecimal price)` using `params(price, id)`, and `updatePriceNamed(long id, BigDecimal price)` using `:price`/`:id`. Write integration tests verifying both methods produce the same result. Then add `findByCategoriesAndMinStock(List<String> categories, int minStock)` with `IN (:categories)`, an empty-list guard, and typed SQL NULL for the note column. Test a special SKU string containing single quotes to verify binding still treats it as a data value.

## 20. Official Documentation

- [Spring Framework 6.1 — JdbcClient](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): fluent facade concept for positional/named JDBC.
- [Spring Framework 6.1 — JdbcClient.StatementSpec](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html): `param`, `params`, `paramSource`, `query`, `update` overloads.
- [Spring Framework — JDBC Core & JdbcClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): `JdbcClient.create(dataSource)` examples, positional and named binding, map/record parameter sources.
- [Spring Framework — Named Parameters and IN clauses](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): SQL types, parameter lists, and limits.
- [Spring Boot — JdbcClient auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/data.html): context for using JdbcClient in Boot apps with DataSource/NamedParameterJdbcTemplate.

## 21. Conclusion

**JdbcClient unifies the fluent API without eliminating the two binding models:**

- **Positional:** SQL uses `?`; `param(value)`/`params(values...)` in order, or `param(jdbcIndex, value)` with **1-based** indices.
- **Named:** SQL uses `:name`; `param("name", value)`, `params(Map)`, or `paramSource(...)`; Spring parses, expands lists when needed, and binds the corresponding JDBC positions.
- **Do not mix** both styles within the same statement. Depending on the task, each Repository method can pick whichever style is clearest.
- **Safe binding** applies to data values, not to table/column names or manually concatenated SQL fragments.
- **SQL types, transactions, resource lifecycles, and result semantics** still must be understood properly—even when the Java syntax is cleaner.

Practical rule of thumb: **"Is my SQL describing data by position or by name?"** From there, pick the matching binding API and let JdbcClient/JdbcTemplate execute via `PreparedStatement` as configured in Spring.
