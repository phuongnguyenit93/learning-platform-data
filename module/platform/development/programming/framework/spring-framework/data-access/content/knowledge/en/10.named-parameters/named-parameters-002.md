# :name Syntax and Positional Parameter Conversion in Spring JDBC

> **Context:** Spring Framework → data-access → **Named Parameters**. This lesson focuses on the **`:name`** syntax in `NamedParameterJdbcTemplate`, how Spring parses SQL and **converts named parameters into JDBC `?` placeholders in order of appearance**, and how values along with SQL types are bound to a `PreparedStatement`. It also explains repeated parameters, `IN (:ids)` lists, exceptions when SQL contains colons, and mistakes caused by misunderstanding the conversion process.

## 1. Why Do We Need Named Parameters?

Standard JDBC most commonly uses **positional parameters**: each `?` stands at the 1st, 2nd, 3rd, ... position in a `PreparedStatement`. Example product query:

~~~sql
SELECT id, sku, price
FROM product
WHERE category = ?
  AND price >= ?
  AND stock > ?
ORDER BY id;
~~~

Java must pass parameters in exact order:

~~~java
// Illustrative fragment: jdbc is JdbcTemplate; mapper is RowMapper<Product>.
jdbc.query(sql, mapper, "BOOK", new BigDecimal("70.00"), 0);
~~~

When there are many conditions, when SQL changes column order, or when one condition uses the same value in multiple places, remembering "what does the 2nd `?` mean?" easily leads to bugs. With **named parameters**, the SQL statement is more self-descriptive:

~~~sql
SELECT id, sku, price
FROM product
WHERE category = :category
  AND price >= :minPrice
  AND stock > :minStock
ORDER BY id;
~~~

And values are passed by name:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("category", "BOOK")
    .addValue("minPrice", new BigDecimal("70.00"))
    .addValue("minStock", 0);

namedJdbc.query(sql, params, mapper);
~~~

In the code above, `namedJdbc` has type `NamedParameterJdbcTemplate`. The names `category`, `minPrice`, and `minStock` in Java **do not have the `:` prefix**; the `:` character is only part of the placeholder syntax in the SQL string. Spring recognizes `:minPrice` and looks up the value under the key `"minPrice"`.

**Important distinction:** SQL with named parameters is a syntax supported by Spring **before sending the statement to the JDBC driver**. A typical JDBC driver does not natively recognize `:category` as a standard placeholder. Spring converts it into **SQL containing `?` and positional values** before executing.

## 2. Comparing the Two Parameter Styles

| Aspect | `JdbcTemplate` with `?` | `NamedParameterJdbcTemplate` with `:name` |
| --- | --- | --- |
| Writing SQL | `WHERE id = ? AND status = ?` | `WHERE id = :id AND status = :status` |
| Passing values | By **position** in SQL | By **name** in parameter source |
| Repeating the same value | Must supply it again at each position | Can repeat the same name |
| Long queries | Easy to mix up positions | Easier to read with meaningful names |
| `IN` lists | Must have the matching number of `?` | Built-in mechanism to expand `List` into multiple `?` |
| Underlying mechanism | JDBC PreparedStatement | Still uses JDBC PreparedStatement after conversion |
| SQL injection safety | Safe for **bound values** | Same; named parameters do not permit dynamic SQL concatenation |
| When suitable | Very short SQL, few parameters | SQL with many conditions, repeated names, or `IN` lists |

`JdbcTemplate` is not discarded: `NamedParameterJdbcTemplate` **wraps and delegates to a classic JdbcTemplate** after the parameter conversion phase. Spring retains Connection, Statement/ResultSet management, transaction support, and `SQLException` to `DataAccessException` translation.

## 3. `:name` Syntax and the Parts of an SQL Named Parameter

Consider this example:

~~~sql
UPDATE product
SET price = :newPrice
WHERE id = :productId
  AND category = :category;
~~~

- The `:` character tells Spring's parser where a named placeholder starts.
- `newPrice`, `productId`, and `category` are the parameter names the application uses to supply values.
- The name after `:` must match **exactly** with the parameter source's key/accessor (case-sensitive for `MapSqlParameterSource`).
- Colons `:` inside SQL literals, comments, or database-specific syntax are **not automatically** parameter names; Spring uses a parser rather than replacing every colon with string replacement.
- A parameter name is **not synonymous with a column name**. `:newPrice` is only a placeholder for the **data value** used for the `price` column.

Example values:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("newPrice", new BigDecimal("49.90"))
    .addValue("productId", 12L)
    .addValue("category", "BOOK");
~~~

Conceptually, Spring converts this into:

~~~sql
UPDATE product
SET price = ?
WHERE id = ?
  AND category = ?;
~~~

And JDBC binds in order:

| `?` position (1-based) | Original name | Value |
| --- | --- | --- |
| 1 | `newPrice` | `49.90` |
| 2 | `productId` | `12` |
| 3 | `category` | `"BOOK"` |

Even if you call `addValue("category", ...)` before `addValue("newPrice", ...)`, the final JDBC order is still based on **order of appearance in SQL**, not the insertion order of keys in the Map.

### `:name` Is Not String Substitution

`:name` is **not** replaced with quoted text concatenated into the SQL string like `'BOOK'`. The final SQL at the PreparedStatement level contains `?`, while data is bound separately via JDBC APIs. This is the core of parameter binding, protecting against SQL injection for **values** and preserving data type information.

## 4. Conversion to Positional Parameters: Step by Step

Suppose an SQL statement has two placeholders with the same name:

~~~sql
UPDATE product
SET stock = stock + :delta
WHERE id = :id AND stock + :delta >= 0;
~~~

Parameter source:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L)
    .addValue("delta", 4);
~~~

Even though `id` is added **before** `delta`, Spring must read placeholders in **SQL order**:

~~~text
Names encountered in order: delta, id, delta
JDBC SQL:
UPDATE product SET stock = stock + ?
WHERE id = ? AND stock + ? >= 0

Positional values (1-based): [4, 2, 4]
~~~

Because `:delta` appears **twice**, it becomes **two `?` markers**, and the same value 4 is bound at both position 1 and position 3. It does **not** send a single value 4 and ask JDBC to share it across two positions.

Conceptual processing flow:

~~~mermaid
flowchart TD
    A["SQL with :name and SqlParameterSource"] --> B["Spring parseSqlStatement: locate names and positions"]
    B --> C["Build new SQL: replace :name with ?"]
    B --> D["Identify each name in order of occurrence"]
    D --> E["Look up value/SQL type by name"]
    C --> F["JDBC PreparedStatement"]
    E --> F
    F --> G["Bind each parameter from 1 to N"]
    G --> H["JDBC driver executes on DBMS"]
~~~

**More specifically in Spring JDBC:**

1. `NamedParameterJdbcTemplate` receives the SQL string and a `Map<String, ?>` or `SqlParameterSource`.
2. Spring uses `NamedParameterUtils` and `ParsedSql` to locate valid named parameters in the SQL statement. Parsing can be **cached by SQL string** at the template level.
3. `NamedParameterUtils.substituteNamedParameters(...)` produces SQL with JDBC placeholders, including expanding `IN` lists when given a suitable `Iterable`.
4. `NamedParameterUtils.buildValueArray(...)` combines the name order with parameter values/types. For `IN` lists, the internal binding step further expands elements into corresponding JDBC positions.
5. Spring creates a `PreparedStatement` for the converted SQL, binds each position via JDBC APIs, and executes; `JdbcTemplate` handles resource lifecycle management.

Along the way, the framework may use `PreparedStatementCreatorFactory` and `PreparedStatementSetter` internally. What matters for application code is that **SQL and values are not concatenated as unsafe text**.

### Do Not Confuse Unique Name Count with Position Count

In the query repeating `:delta`, there are **2 unique names** (`delta`, `id`) but **3 bind positions**. With a 3-element list in `IN (:ids)`, one name `ids` can also generate **3 `?` positions**. Therefore, you cannot inspect `map.size()` and conclude the number of `?` markers in the converted SQL.

## 5. Verifying Directly with `NamedParameterUtils`

Spring exposes utility APIs to observe parsing and substitution. The following Java snippet fits Spring JDBC 6.x:

~~~java
import java.util.Arrays;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterUtils;
import org.springframework.jdbc.core.namedparam.ParsedSql;

String sql =
    "UPDATE product SET stock = stock + :delta " +
    "WHERE id = :id AND stock + :delta >= 0";

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L)
    .addValue("delta", 4);

ParsedSql parsed = NamedParameterUtils.parseSqlStatement(sql);
String positionalSql =
    NamedParameterUtils.substituteNamedParameters(parsed, params);

Object[] positionalValues =
    NamedParameterUtils.buildValueArray(parsed, params, null);

System.out.println("SQL = " + positionalSql);
System.out.println("Args = " + Arrays.toString(positionalValues));
~~~

This is a **fragment**; section 11 provides a complete runnable project. In this fragment, `buildValueArray` without declared SQL types returns values for the **occurrences of each name**, printing `[4, 2, 4]`. If SQL types are explicitly registered, some values may be wrapped in `SqlParameterValue`; do not assume every `Object[]` element is a raw `Integer`/`Long`.

**Important technical note:** `buildValueArray` is not an API for manually building a final flattened value array in all cases, especially with `IN (:ids)`. For lists, let `NamedParameterJdbcTemplate`/the internal factory bind each element; the utility is suited for learning the syntax, debugging, or building infrastructure when truly justified.

## 6. Supplying Values with Map, MapSqlParameterSource, and BeanPropertySqlParameterSource

### 6.1. `Map<String, ?>` — Concise for CRUD

~~~java
String sql =
    "SELECT COUNT(*) FROM product WHERE category = :category";

Integer count = namedJdbc.queryForObject(
    sql,
    Map.of("category", "BOOK"),
    Integer.class
);
~~~

`Map.of(...)` in Java 9+ does not accept `null` keys or values. When SQL NULL values or multiple data types are needed, use `MapSqlParameterSource` for clarity.

### 6.2. `MapSqlParameterSource` — Suitable for Typed NULLs

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 2L, java.sql.Types.BIGINT)
    .addValue("note", null, java.sql.Types.VARCHAR);

int changed = namedJdbc.update(
    "UPDATE product SET note = :note WHERE id = :id",
    params
);
~~~

`MapSqlParameterSource` implements `SqlParameterSource`; it tracks names, values, and optionally **JDBC type codes** (`java.sql.Types`) and type names. When SQL has NULL or a driver struggles to infer the type, explicit type declarations make binding reliable and easier to debug.

With `SqlParameterSource`, `hasValue(name)` distinguishes **missing key** from **key present with null value**. `NamedParameterJdbcTemplate` requires every needed name to exist in the parameter source; "missing name" is not the same as "SQL NULL".

### 6.3. `BeanPropertySqlParameterSource` — Reading by JavaBean Property

Example JavaBean with matching getters:

~~~java
public class ProductFilter {
    private final String category;
    private final java.math.BigDecimal minPrice;

    public ProductFilter(String category, java.math.BigDecimal minPrice) {
        this.category = category;
        this.minPrice = minPrice;
    }

    public String getCategory() {
        return category;
    }

    public java.math.BigDecimal getMinPrice() {
        return minPrice;
    }
}

// Fragment used in a Repository:
SqlParameterSource source =
    new BeanPropertySqlParameterSource(
        new ProductFilter("BOOK", new BigDecimal("70.00"))
    );

namedJdbc.query(
    "SELECT id, sku FROM product " +
    "WHERE category = :category AND price >= :minPrice",
    source,
    (rs, rowNum) -> rs.getString("sku")
);
~~~

The parameter source accesses **JavaBean properties** `category` and `minPrice` via getters. This does not mean `BeanPropertySqlParameterSource` can read arbitrary private fields or any object with matching field names. For Java records, check your Spring version and choose a record-aware source (such as `SimplePropertySqlParameterSource` in supported versions) or use a Map to avoid depending on JavaBean conventions.

**Selection mindset:** `Map` for 1–3 short parameters; `MapSqlParameterSource` when needing typed nulls/SQL types or many values; `BeanPropertySqlParameterSource` when an existing JavaBean has property names matching the SQL. None of them changes the underlying `:name` → `?` conversion.

## 7. Repeated Names: One Key, Multiple Positions

Example finding products where either of two attributes contains a keyword:

~~~sql
SELECT id, sku, category
FROM product
WHERE sku LIKE :pattern OR category LIKE :pattern
ORDER BY id;
~~~

In Java:

~~~java
String pattern = "%" + keyword + "%";

List<Product> rows = namedJdbc.query(
    sql,
    Map.of("pattern", pattern),
    mapper
);
~~~

If `keyword = "BO"`, Spring generates the equivalent SQL:

~~~sql
SELECT id, sku, category
FROM product
WHERE sku LIKE ? OR category LIKE ?
ORDER BY id;
~~~

And binds `"%BO%"` **twice**, corresponding to both `?` positions. It cannot substitute once in SQL and forget to bind the second position. Nor do you need two keys `pattern1`, `pattern2` just because the same value is used in two places.

**Note on `LIKE`:** Bind the entire `%keyword%` pattern as a value as shown above. User-supplied `%` and `_` characters can act as wildcards; if the feature requires **literal matching**, escape wildcards using the database's `ESCAPE` syntax. Parameter binding prevents SQL injection at the value level, but does not automatically "escape LIKE semantics".

## 8. Expanding `IN (:ids)` Lists into Multiple `?` Markers

JDBC does not allow a single placeholder to represent a variable number of elements inside an SQL `IN`. This is why named parameter support **adds an SQL expansion step**.

Source SQL:

~~~sql
SELECT id, sku
FROM product
WHERE id IN (:ids)
ORDER BY id;
~~~

Parameters:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("ids", List.of(1L, 2L, 3L));
~~~

Expanded SQL:

~~~sql
SELECT id, sku
FROM product
WHERE id IN (?, ?, ?)
ORDER BY id;
~~~

During binding, elements **1, 2, 3** go into JDBC positions 1, 2, 3 in order. Spring does **not** convert the list to the string `"1,2,3"` and concatenate it into SQL; doing so would be type-error-prone and an injection risk.

An example combining a list and a scalar value:

~~~sql
SELECT id, sku
FROM product
WHERE category IN (:categories)
  AND price >= :minPrice
ORDER BY id;
~~~

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("minPrice", new BigDecimal("70.00"))
    .addValue("categories", List.of("BOOK", "DEVICE"));

List<String> skuList = namedJdbc.query(
    sql,
    params,
    (rs, rowNum) -> rs.getString("sku")
);
~~~

With two categories, the JDBC SQL has **3** `?` markers: two for the list and one for `:minPrice`. Even though Java adds `minPrice` before `categories`, the JDBC order is **BOOK, DEVICE, 70.00** because SQL encounters `:categories` first.

### Why Is `IN (:ids)` Different from `= :ids`?

`IN (:ids)` uses SQL syntax for **a list of elements** after expanding to `IN (?, ?, ?)`. Conversely, `id = :ids` with a multi-element List produces invalid SQL or unintended semantics; you cannot expect a list value to behave like a scalar in an `=` operator.

### Empty List Case

If `ids` is empty, many databases reject `IN ()`; do not assume Spring automatically turns an empty list into an always-false condition across every SQL dialect. Define semantics explicitly:

~~~java
public List<Long> findIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }

    return namedJdbc.query(
        "SELECT id FROM product WHERE id IN (:ids) ORDER BY id",
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getLong("id")
    );
}
~~~

If business logic wants "no filter" when the list is empty, design a separate explicit SQL branch while protecting SQL structure. Never silently omit the `IN` condition when a user passes an empty list, as that can accidentally return **all rows**.

### Very Long Lists and DBMS Limits

JDBC/DBMS engines impose limits on placeholder counts or `IN` list sizes. Spring notes cross-database compatibility considerations, so **do not assume tens of thousands of IDs in one `IN (:ids)`** will work or perform well. Solutions include bounding inputs, chunking queries into reasonable batches, batch processing, temporary tables, joins, or database-specific array/table-valued parameters. When chunking, define ordering, duplicate-result, and transaction semantics.

### Multi-Column Tuple Lists

For databases supporting tuple comparison syntax like `(id, category) IN ((?, ?), (?, ?))`, Spring supports passing a list of object arrays to expand the list expression. However, **both SQL dialect and driver must support it**. This is an advanced technique, unnecessary for ordinary single-column `IN` queries.

## 9. When SQL Contains `:` That Is Not a Parameter Name

Do not do text replacement like `sql.replace(":id", "?")`. That can break valid cases such as:

~~~sql
SELECT ':id' AS sample_label
FROM product
WHERE id = :id;

-- Note :id is descriptive text, not a parameter.
SELECT id FROM product WHERE sku = :sku;

/* Comment :category is not a parameter */
SELECT sku FROM product WHERE category = :category;
~~~

Inside the quoted literal `':id'` and comments, `:id` is **not a named parameter**, whereas `id = :id` outside is a placeholder to bind. Spring's parser recognizes SQL quotes/comments to avoid false substitutions.

### PostgreSQL Cast `::`

PostgreSQL has cast syntax such as `'123'::integer`. With Spring JDBC's parser, `::` should not be treated as two named parameters. Still, vendor-specific extensions or operators can create tricky lexical cases; test actual SQL against your exact Spring/driver/database versions rather than relying on custom string replacement.

### Only Use `:name` Where a Value Is Expected

`SELECT * FROM :table` and `ORDER BY :sortColumn` cannot bind table or column names as identifiers. Placeholders represent **values**, not **SQL structure**. If a sort column must be chosen from input, use a whitelist:

~~~java
String sortColumn = switch (sortBy) {
    case "price" -> "price";
    case "sku" -> "sku";
    default -> "id";
};

String sql =
    "SELECT id, sku, price FROM product WHERE category = :category " +
    "ORDER BY " + sortColumn;
~~~

This is an illustrative fragment; `sortBy` is received by the application and must be validated against a whitelist. **Never** insert arbitrary request strings directly into identifier positions. Even with named parameters, the application must still guard any **SQL fragments it concatenates itself**.

## 10. Where Does Named Parameter Conversion Happen in an Application?

A Spring JDBC Repository typically looks like:

~~~text
Controller / Job
   -> Application Service
       -> ProductRepository
           -> NamedParameterJdbcTemplate
               -> parse SQL + substitute :name -> ?
               -> PreparedStatementCreatorFactory / binding
               -> JdbcTemplate / DataSource
                   -> JDBC Driver / Database
~~~

The Repository only needs to know how to fetch a result list, update, or insert records. The Service does not need to construct JDBC placeholders manually. Large SQL queries can use Java multiline text blocks for readability:

~~~java
String sql = """
    SELECT id, sku, price
    FROM product
    WHERE category = :category
      AND price >= :minPrice
    ORDER BY id
    """;
~~~

**Text blocks are a Java syntax feature** and do not change named parameter parsing rules. The SQL content is still parsed by Spring as needed, or retrieved from cached `ParsedSql` when the SQL string matches.

### Do Not Confuse with JPA/Hibernate Named Parameters

JPA/JPQL also uses `:name` syntax, but it is a **different API/parser** with a different query lifecycle. `NamedParameterJdbcTemplate` is Spring JDBC, handling real SQL and delegating to JdbcTemplate/PreparedStatement. Do not mix JPA Query APIs or assume collection expansion behaves identically across the two systems.

## 11. Standalone Example: Inspecting Converted SQL and Values

This example uses **Java 21**, **Spring Boot 3.3.5**, **Gradle**, **Spring JDBC**, and **H2**. The goal is to execute real queries with `NamedParameterJdbcTemplate` while **printing the `?` SQL and corresponding parameter order** using `NamedParameterUtils`.

### 11.1. Project Structure

~~~text
named-parameters-lesson/
├── build.gradle
└── src/main/
    ├── java/com/example/namedparams/
    │   ├── NamedParamsApplication.java
    │   └── ProductRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 11.2. `build.gradle`

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

The JDBC starter provides JdbcTemplate, a DataSource (typically HikariCP), and auto-configuration for `NamedParameterJdbcTemplate` when Boot conditions are met. Spring Web is not needed to run a console application.

### 11.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:named_params_lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

### 11.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    category VARCHAR(24) NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    note VARCHAR(120)
);
~~~

### 11.5. `src/main/resources/data.sql`

~~~sql
INSERT INTO product (id, sku, category, price, stock, note)
VALUES (1, 'J-BOOK', 'BOOK', 120.00, 3, NULL);

INSERT INTO product (id, sku, category, price, stock, note)
VALUES (2, 'S-BOOK', 'BOOK', 75.00, 0, NULL);

INSERT INTO product (id, sku, category, price, stock, note)
VALUES (3, 'MOUSE', 'DEVICE', 40.50, 6, NULL);
~~~

Three rows are initialized with fixed IDs so example stdout does not depend on database key generation. Product `S-BOOK` starts out of stock; the named-parameter UPDATE will increase stock to 4.

### 11.6. Repository: `ProductRepository.java`

~~~java
package com.example.namedparams;

import java.math.BigDecimal;
import java.sql.Types;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    public static final String RESTOCK_SQL =
        "UPDATE product SET stock = stock + :delta " +
        "WHERE id = :id AND stock + :delta >= 0";

    private final NamedParameterJdbcTemplate jdbc;

    public ProductRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ':delta' appears twice in SQL, with only one key.
    public int restock(long id, int delta) {
        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("id", id)
            .addValue("delta", delta);

        return jdbc.update(RESTOCK_SQL, params);
    }

    // One :categories name can expand into multiple '?' markers.
    public List<String> availableSkus(
            List<String> categories, BigDecimal minPrice) {

        if (categories.isEmpty()) {
            return List.of();
        }

        String sql = """
            SELECT sku FROM product
            WHERE category IN (:categories)
              AND price >= :minPrice
              AND stock > 0
            ORDER BY id
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("minPrice", minPrice)
            .addValue("categories", categories);

        return jdbc.query(
            sql,
            params,
            (rs, rowNum) -> rs.getString("sku")
        );
    }

    // Parameter name is in SQL; the 'sku' key in Map has no ':'.
    public int stockBySku(String sku) {
        Integer stock = jdbc.queryForObject(
            "SELECT stock FROM product WHERE sku = :sku",
            Map.of("sku", sku),
            Integer.class
        );
        if (stock == null) {
            throw new IllegalStateException("Stock is SQL NULL");
        }
        return stock;
    }

    // NULL is declared with an explicit JDBC type.
    public int clearNote(long id) {
        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("id", id, Types.BIGINT)
            .addValue("note", null, Types.VARCHAR);

        return jdbc.update(
            "UPDATE product SET note = :note WHERE id = :id",
            params
        );
    }
}
~~~

Here the Repository does not call `PreparedStatement.setInt` directly, yet **Spring still uses PreparedStatement underneath**. The `restock` method deliberately adds `id` **before** `delta` to demonstrate that Map order does not dictate bind order.

`stockBySku` demonstrates the `queryForObject(String, Map, Class)` overload. If no row exists, Spring may throw `EmptyResultDataAccessException`; the example queries an SKU guaranteed to exist. Checking `stock == null` represents the case where a column returns SQL NULL, even though the example schema defines `stock NOT NULL`.

In a real system, check the updated row count returned by `restock`, because 0 rows could mean the ID does not exist or `stock + delta >= 0` is not satisfied. Do not treat 0 rows as success merely because no exception was thrown.

### 11.7. Application: `NamedParamsApplication.java`

~~~java
package com.example.namedparams;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterUtils;
import org.springframework.jdbc.core.namedparam.ParsedSql;

@SpringBootApplication
public class NamedParamsApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedParamsApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(ProductRepository products) {
        return args -> {
            MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", 2L)
                .addValue("delta", 4);

            ParsedSql parsed = NamedParameterUtils
                .parseSqlStatement(ProductRepository.RESTOCK_SQL);

            String sqlWithQuestions = NamedParameterUtils
                .substituteNamedParameters(parsed, params);

            Object[] argsByPosition = NamedParameterUtils
                .buildValueArray(parsed, params, null);

            System.out.println("SQL = " + sqlWithQuestions);
            System.out.println(
                "Args = " + Arrays.toString(argsByPosition)
            );

            int updated = products.restock(2L, 4);
            System.out.println("Updated rows = " + updated);
            System.out.println(
                "S-BOOK stock = " + products.stockBySku("S-BOOK")
            );

            List<String> skus = products.availableSkus(
                List.of("BOOK", "DEVICE"), new BigDecimal("70.00")
            );
            System.out.println("Available SKUs = " + skus);

            // Expand :categories list into two '?' markers.
            String inSql =
                "SELECT sku FROM product " +
                "WHERE category IN (:categories) AND price >= :minPrice";

            MapSqlParameterSource inParams = new MapSqlParameterSource()
                .addValue("minPrice", new BigDecimal("70.00"))
                .addValue("categories", List.of("BOOK", "DEVICE"));

            System.out.println("IN SQL = " +
                NamedParameterUtils.substituteNamedParameters(
                    inSql, inParams
                )
            );
        };
    }
}
~~~

There is **no need** to import JdbcTemplate in the Application class because Boot injects Repository and NamedParameterJdbcTemplate via the Spring context. `NamedParameterUtils` is used in the demo solely to **observe the transformed SQL**; a real Repository does not need to parse and build value arrays manually, since `NamedParameterJdbcTemplate` already does that.

### 11.8. Running the Program

In the directory containing `build.gradle`:

~~~bash
# If the project already has a Gradle wrapper:
./gradlew bootRun

# If there is no wrapper yet, with a compatible Gradle installed:
gradle bootRun
~~~

On Windows PowerShell, run the wrapper with `.\gradlew.bat bootRun`. Java 21 must be installed, or the Gradle toolchain configured to provision Java 21.

With a fresh in-memory H2 database, the lines **intentionally printed by the application** (excluding Spring/HikariCP and Gradle logs) are:

~~~text
SQL = UPDATE product SET stock = stock + ? WHERE id = ? AND stock + ? >= 0
Args = [4, 2, 4]
Updated rows = 1
S-BOOK stock = 4
Available SKUs = [J-BOOK, S-BOOK]
IN SQL = SELECT sku FROM product WHERE category IN (?, ?) AND price >= ?
~~~

**Step-by-step stdout explanation:**

1. `:delta` appears first and last, `:id` in the middle ⇒ SQL has three `?` markers and values in order `[4, 2, 4]`.
2. `products.restock(2, 4)` updates record ID=2 from stock 0 to 4; the non-negative check passes ⇒ 1 row updated.
3. Querying by SKU for `S-BOOK` returns stock 4.
4. `categories` includes BOOK and DEVICE, but with minimum price 70.00 and positive stock required, only `J-BOOK` (120.00, 3) and `S-BOOK` (75.00, 4) match; `MOUSE` at 40.50 is excluded.
5. When converting `IN (:categories)` with two items, Spring creates two placeholders in `IN (?, ?)` plus one more placeholder for `:minPrice`.

The program can be rerun in a **new JVM** to get the same results; the same database is reinitialized from `schema.sql` and `data.sql`. If you intentionally run the logic twice within the same context without resetting data, stock numbers will differ because UPDATE runs an additional time.

## 12. SQL NULL Parameters, JDBC Types, and Temporal Data

Calling `addValue("name", null)` represents SQL NULL, yet the **driver/database may need to know the JDBC type**. For example:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("id", 1L, java.sql.Types.BIGINT)
    .addValue("description", null, java.sql.Types.VARCHAR);

namedJdbc.update(
    "UPDATE product SET note = :description WHERE id = :id",
    params
);
~~~

`NamedParameterJdbcTemplate` must convert parameter names to `?` while preserving **SQL type metadata** during binding. For SQL `DECIMAL(12,2)`, use `BigDecimal` instead of `double` to avoid binary floating-point rounding errors with currency. For `LocalDate`, `Instant`, or `OffsetDateTime`, mapping and timezones should be tested against the driver/schema rather than assuming parameter names alone dictate the right type.

You can use `MapSqlParameterSource.registerSqlType(...)` or `addValue(name, value, sqlType)` to declare types. For normal SQL, many drivers infer the type from the Java value, though NULLs, arrays, and vendor-specific types may require explicit declarations.

### Do Not Write `WHERE col = :value` When the Value Can Be NULL

When `value = null`, SQL `col = NULL` does not evaluate to true under SQL three-valued logic. If business logic seeks rows missing a value, use `IS NULL`:

~~~sql
SELECT id FROM product WHERE note IS NULL;
~~~

Or construct explicit SQL branches suited to optional conditions. Binding an SQL NULL does not automatically transform `=` into `IS NULL`.

## 13. Missing Names, Typos, and Parameter Ordering

Example SQL:

~~~sql
SELECT id, sku FROM product
WHERE category = :category AND price >= :minPrice;
~~~

If the source provides `category` but **lacks `minPrice`**, Spring does not have enough values to bind and throws an error when preparing the operation. It does not silently substitute `null` for a missing name. Distinguish clearly:

- **Missing name:** `hasValue("minPrice") == false`; the source supplies no value.
- **Name present with null value:** `hasValue("minPrice") == true`; handle SQL NULL semantics and corresponding type.
- **Typo/case mismatch:** `"minprice"` does not match `:minPrice` in a case-sensitive `MapSqlParameterSource`.
- **Extra unused name in SQL:** The Map has a key beyond those used in SQL. Normally that key does not become a placeholder; it is often a sign of an incomplete refactor or leftover data to clean up.

**Do not work around missing parameters by concatenating SQL strings from input.** If a condition is optional, design explicit SQL by whitelisting allowed condition fragments or using an appropriate builder/query layer; **values** must still be bound.

### Can Named and Positional Parameters Be Mixed in the Same SQL?

Avoid mixing `:id` with `?` in the same `NamedParameterJdbcTemplate` query. The mechanism is designed to translate names into consistent JDBC positions; mixed named and unnamed combinations may be rejected when building the value array or lead to unclear mappings. Choose **one consistent parameter style per SQL statement**.

## 14. Spring's Parser Is Not a `String.replace`

Cases the parser must distinguish:

| SQL Text | How Should It Be Handled? | Explanation |
| --- | --- | --- |
| `WHERE id = :id` | Replace `:id` with `?` | Valid named placeholder |
| `WHERE x = :x AND y = :x` | Two `?` markers, same `x` value | Two occurrences |
| `IN (:ids)` with 3 IDs | `IN (?, ?, ?)` | List expansion |
| `SELECT ':id' AS label` | Keep `':id'` | SQL string literal |
| `-- :id` | Keep comment intact | Not a placeholder |
| `/* :id */` | Keep comment intact | Not a placeholder |
| PostgreSQL `'42'::integer` | Keep `::` cast intact | Database-specific syntax |
| `ORDER BY :sortBy` | Do not turn value into column name | SQL identifiers cannot be bound via `?` |

Writing a safe SQL parser is **harder than** replacing every `:name` with `?` via regex. For vendor-specific syntax (JSON operators, casts, quoted identifiers, escaped syntax), test against the exact SQL, Spring version, and driver. If vendor syntax cannot be safely expressed through the abstraction, consider `JdbcTemplate` for a dedicated query or adjust the SQL explicitly; never silently concatenate raw values.

## 15. Performance and SQL Parse Caching

`NamedParameterJdbcTemplate` can cache **SQL structure parsing** results to avoid re-parsing the same SQL string on every execution. Relevant configuration methods are `setCacheLimit(int)` and `getCacheLimit()`. Distinguish the different types of caches accurately:

- **Parsed SQL cache:** Stores named parameter positions/metadata for an SQL string. Does not hold SELECT results.
- **JDBC PreparedStatement/plan cache:** Managed by the driver/database/pool under its own configuration; not synonymous with the parsed SQL cache.
- **Application business data cache:** A completely separate concern; `NamedParameterJdbcTemplate` does not cache query results.

If the same SQL receives `:ids` lists with varying element counts, the expanded JDBC SQL may contain **different numbers of `?` markers**, affecting how the driver/DBMS caches statements/plans even though the source SQL string for the parser cache stays unchanged.

**Do not abuse literal concatenation into SQL to "optimize cache".** Concatenating `WHERE id = 123` into SQL per request creates many distinct SQL strings and introduces injection risk. Keeping SQL templates stable and binding data improves both readability and security.

## 16. Placing Transaction Boundaries and Error Handling at the Right Layer

SQL statements with named parameters still execute through the same DataSource and transaction manager as classic `JdbcTemplate`. A Service with a multi-step use case can use `@Transactional`:

~~~java
// Architectural fragment — classes and beans must be fully declared in the application.
@Service
public class InventoryService {
    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void addStockForTwoItems(long firstId, long secondId) {
        int first = products.restock(firstId, 3);
        int second = products.restock(secondId, 5);
        if (first != 1 || second != 1) {
            throw new IllegalStateException("Restock not applied");
        }
    }
}
~~~

This snippet requires importing `@Service` and `@Transactional` from Spring. Both UPDATEs participate in the same transaction when the public method is invoked through a Spring proxy, the transaction manager coordinates the same DataSource, and no conflicting configuration overrides it.

**Named parameters do not create a new transaction.** If two `update` calls are not enclosed in an outer transaction, each UPDATE may operate under database autocommit. The `:name` → `?` conversion is an **SQL preparation** step, not a commit/rollback policy.

### Errors Can Occur in Three Stages

1. **Parse/bind:** Missing key, misspelled name, incompatible SQL type, empty `IN`, or unparseable SQL.
2. **JDBC execute/DBMS:** Invalid column/table, constraint violation, deadlock, lock timeout, network failure.
3. **Result mapping:** Code reading columns or data types incorrectly (`RowMapper`/`ResultSetExtractor`).

Spring typically translates `SQLException` at the `JdbcTemplate` layer into the `DataAccessException` hierarchy. Do not catch every `DataAccessException` broadly and return "not found", because query errors, conflicts, and lost connections are fundamentally different.

## 17. Common Error Reference Table

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `No value supplied for SQL parameter 'x'` | Missing key `x` | Check `:x` spelling and parameter source |
| Values bound in wrong positions despite valid Map | SQL order differs from manual assumption | Let the template handle it; use utility to inspect order |
| Calling `addValue(":id", 2)` | Key includes `:`, SQL expects name `id` | Pass key `"id"` |
| `WHERE id IN (:ids)` fails when ids is empty | `IN ()` is invalid in many DBs | Guard empty list before querying |
| Using a large list of tens of thousands of items | Placeholder/vendor limits, parse/bind overhead | Bound size, split batches, temp table, or DB-specific technique |
| Using `ORDER BY :column` | Placeholders only bind values | Whitelist identifiers and build controlled SQL fragment |
| `:foo` inside a text literal replaced by regex | Naive custom parser | Use `NamedParameterJdbcTemplate`/`NamedParameterUtils` |
| Assuming repeated `:delta` binds only one position | Confusing unique names with position count | Bind value at every occurrence |
| `col = :value` with NULL does not match | SQL uses 3-valued logic | Use `IS NULL` when semantically intended |
| Calling `Map.of("note", null)` | `Map.of` does not accept null | Use `MapSqlParameterSource` |
| Mixing `?` and `:id` | Ambiguous parameter mapping | Pick one parameter style per SQL statement |
| Writing literal input directly into SQL | Injection / quoting bugs and plan cache pollution | Bind values with `:name` |
| Confusing Spring named parameters with JPA `Query` | Different parsers/APIs and rules | Identify the data-access technology in use |
| Expecting converted SQL to contain interpolated values | Confusing prepared statements with string substitution | SQL contains `?`; values are sent separately via JDBC |

## 18. Testing the Conversion Mechanism Properly

**Utility-level tests** verify parsing repeated names and converting SQL into standard placeholders. Example:

~~~java
// Illustrative JUnit 5 fragment; requires spring-boot-starter-test
// dependency in the test project and JUnit imports.
@Test
void repeatedNameExpandsToThreePositions() {
    String sql =
        "UPDATE product SET stock = stock + :delta " +
        "WHERE id = :id AND stock + :delta >= 0";

    MapSqlParameterSource source = new MapSqlParameterSource()
        .addValue("id", 2L)
        .addValue("delta", 4);

    ParsedSql parsed = NamedParameterUtils.parseSqlStatement(sql);

    assertEquals(
        "UPDATE product SET stock = stock + ? " +
        "WHERE id = ? AND stock + ? >= 0",
        NamedParameterUtils.substituteNamedParameters(parsed, source)
    );

    assertArrayEquals(
        new Object[] { 4, 2L, 4 },
        NamedParameterUtils.buildValueArray(parsed, source, null)
    );
}
~~~

This test **proves SQL shape and value ordering**, but does not prove the DB accepts the syntax or that transactions work. To verify those, an integration test against H2 or a production-compatible database must run real `NamedParameterJdbcTemplate.update/query` calls and read back the data.

**Tests for `IN`** can verify that `IN (:ids)` with 1, 2, and 3 items produces SQL with the matching number of `?` markers. Add an empty-list test matching your **chosen business semantics**; test against PostgreSQL/MySQL/Oracle if special limits or operators apply.

**Security tests** should pass strings with quotes, backslashes, Unicode, and SQL-injection-like payloads such as `"BOOK' OR 1=1 --"` as values, verifying they are handled strictly as **data** without breaking the query. Avoid logging sensitive values.

## 19. How Do `JdbcClient` and `NamedParameterJdbcTemplate` Differ?

Spring Framework 6.1 introduced `JdbcClient` with a fluent API style; underneath, it uses `JdbcOperations` and `NamedParameterJdbcOperations` to run queries and updates. Example:

~~~java
// Illustrative fragment: client is a JdbcClient created from DataSource.
long count = client.sql(
        "SELECT COUNT(*) FROM product WHERE category = :category"
    )
    .param("category", "BOOK")
    .query(Long.class)
    .single();
~~~

This is still **named parameter binding**; the fluent style only changes the outer API. You still need to understand the `:category` to `?` conversion to debug SQL and avoid confusing names with positions. Classic `JdbcTemplate` also remains useful for specialized operations; `NamedParameterJdbcTemplate.getJdbcOperations()` provides access to classic `JdbcOperations` when needed.

There is no need to rewrite an entire project to `JdbcClient` just to use named parameters; both approaches can coexist if the codebase stays consistent.

## 20. Practice Exercises

**Exercise 1 — Fill in the bind order.** Given the SQL:

~~~sql
SELECT id FROM product
WHERE price >= :minPrice
  AND category = :category
  AND price <= :maxPrice
  AND category <> :blockedCategory;
~~~

Suppose `params` are added in the order `blockedCategory`, `maxPrice`, `category`, `minPrice`. Write out the JDBC SQL and positional value sequence.

**Answer hint:** The SQL has four `?` markers in order `minPrice`, `category`, `maxPrice`, `blockedCategory`. Key insertion order in the Map does not decide JDBC order.

**Exercise 2 — Repeated parameter.** How many `?` markers does `WHERE sku = :term OR category = :term` have?  
**Answer:** Two; the same `term` value is bound at both positions.

**Exercise 3 — List.** How many placeholders does `WHERE id IN (:ids) AND stock > :minStock` have when `ids=[2,5,9]`?  
**Answer:** Four; three for the list and one for `minStock`.

**Exercise 4 — Empty list.** When a user filters by an empty list of IDs, should you automatically drop `WHERE id IN (...)`?  
**Answer:** Not by default. If business logic treats an empty ID set as matching nothing, return an empty list without querying; dropping the condition can expose every row.

**Exercise 5 — NULL.** Using `WHERE note = :note`, will `note=null` match rows where `note IS NULL`?  
**Answer:** No. SQL NULL uses three-valued logic; write `IS NULL` when that is the intent.

**Exercise 6 — SQL identifier.** Can `ORDER BY :field` substitute a user-selected column name?  
**Answer:** No. Bind parameters represent values; column names must be chosen via a code whitelist.

**Extended exercise:** Write a `discountPrices(List<Long> ids, BigDecimal discount)` method to discount selected products while ensuring new prices remain non-negative. Use `IN (:ids)`, bind `:discount` repeatedly in `SET price = price - :discount` and `WHERE price >= :discount`. Guard empty lists, check updated rows, and use a `@Transactional` Service if part of a multi-step use case. Call `NamedParameterUtils` yourself to predict the bind positions for a 2-ID list, then verify with an H2 integration test.

## 21. Official Documentation

- [Spring Framework — Using NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): differences between named parameters and `?`, using `MapSqlParameterSource`, JavaBean sources, and delegating to `JdbcTemplate`.
- [NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): contract, `query`/`update` overloads, parse caching, and `getJdbcOperations()`.
- [NamedParameterUtils API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterUtils.html): `parseSqlStatement`, `substituteNamedParameters`, `buildValueArray`, and list expansion.
- [Spring Framework — Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): how lists expand into multiple placeholders and DBMS limit notes.
- [SqlParameterSource API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html): contract for looking up values and SQL types by name.
- [Spring Framework — JdbcClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): fluent API combining named and indexed parameter operations.

## 22. Final Takeaways

1. **`:name` is Spring JDBC syntax**, not a standard JDBC driver placeholder. Spring converts SQL to **`?`** markers before `PreparedStatement` executes.
2. Each **occurrence** of `:name` typically creates its own bind position, even when multiple occurrences share one key.
3. **SQL order** determines JDBC order; **Map key insertion order does not determine** bind order.
4. `IN (:ids)` with a list expands to the matching number of `?` markers; empty lists and item-count limits must be handled.
5. **Parameter names only substitute data**, never table/column names or SQL fragments. Always bind values to prevent injection.
6. `MapSqlParameterSource` adds SQL type/typed null metadata; `BeanPropertySqlParameterSource` reads JavaBean properties when appropriate.
7. `NamedParameterJdbcTemplate` offers more readable syntax while still relying on `JdbcTemplate`, the JDBC driver, DataSource, and Spring transactions.

**Conclusion:** Read `:name` as "**bind the matching value into each corresponding PreparedStatement position**", not "replace text to build new SQL containing literals". Once you understand the pipeline **parse → substitute placeholders → determine order/types → bind → execute**, you will write, test, and debug Spring JDBC queries with named parameters accurately and safely.
