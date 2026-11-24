# Reusing RowMapper Between JdbcTemplate and NamedParameterJdbcTemplate

> **Goal:** When the same table or SQL column set is queried with positional parameters (`?`) and named parameters (`:name`), write **a single `RowMapper<T>`** to map result rows into Java objects; reuse that mapper across both `JdbcTemplate` (the classic template) and `NamedParameterJdbcTemplate` (the named template). Understand the boundary between **parameter binding**, **SQL execution**, and **ResultSet mapping**, how to test equivalence, and when not to reuse mechanically.

**Context:** Spring Framework → Data Access → *Named Parameters*. This lesson is about **reusing data-reading logic** when moving between Spring's two JDBC query styles, not about creating JPA entities, configuring an ORM, or replacing an entire DAO with another framework.

## 1. Short Answer: Can You Share a RowMapper?

**Yes.** Both `JdbcTemplate` and `NamedParameterJdbcTemplate` provide `query(...)` and `queryForObject(...)` overloads accepting an `org.springframework.jdbc.core.RowMapper<T>`. The exact same mapper can be passed to both APIs, provided the SQL results of both queries share **matching columns, aliases, data types, and semantics** expected by the mapper.

```text
JdbcTemplate                                 NamedParameterJdbcTemplate
SQL ... WHERE category = ?                   SQL ... WHERE category = :category
               |                                         |
        Positional Java values                    Map / SqlParameterSource
               |                                         |
               +---------- Spring JDBC ------------------+
                                     |
                      PreparedStatement / ResultSet
                                     |
                             RowMapper<Book>
                                     |
                          mapRow(ResultSet, rowNum)
                                     |
                              Book / Java DTO
```

**Different on SQL input:** the classic template uses `?` placeholders and **positional** argument lists; the named template uses `:name` and `Map`/`SqlParameterSource`, which Spring converts into corresponding JDBC placeholders. **Identical on output:** once the SQL executes and produces a `ResultSet`, the mapper is invoked for each row under the exact same `RowMapper<T>` contract.

The two templates do not need two different mapper classes. **Never write `ClassicBookMapper` and `NamedBookMapper` with identical logic merely because parameter binding differs.**

## 2. Three Separate Responsibilities: SQL, Binding, and Mapping

Suppose you want to fetch books in the "Java" category.

**Positional-parameter SQL:**

```sql
SELECT id, title, category, price, in_stock
FROM books
WHERE category = ?
ORDER BY id;
```

**Named-parameter SQL:**

```sql
SELECT id, title, category, price, in_stock
FROM books
WHERE category = :category
ORDER BY id;
```

Both queries request the same column set and the same result ordering. Only the way `"Java"` is passed into the WHERE condition differs.

| Responsibility | Classic Template | Named Template | Is RowMapper Involved? |
| --- | --- | --- | --- |
| Build SQL | `WHERE category = ?` | `WHERE category = :category` | Does not need to know placeholders |
| Bind parameters | `"Java"` at position `1` | `category → "Java"` | Does not bind inputs |
| Execute | `JdbcTemplate`/JDBC | `NamedParameterJdbcTemplate` converts named SQL then uses JDBC | Does not open connections/queries |
| Iterate ResultSet | Spring JDBC | Spring JDBC | Receives **one current row** |
| Read columns | `rs.getLong("id")`… | Identical | **Yes** |
| Construct DTO | `new Book(...)` | Identical | **Yes** |
| Close resources | Spring JDBC | Spring JDBC | Never closes `ResultSet` |

`RowMapper` contains **no** logic deciding WHERE, ORDER BY, pagination, or passed-in parameters. Its contract is simply **turning the current ResultSet row into a Java object**.

## 3. The Official Contract of RowMapper<T>

`RowMapper<T>` is a functional interface with one core method:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
```

This is a **signature reference for learning**, not an interface file you create yourself: the actual interface is already part of Spring JDBC.

- `rs` is the `ResultSet` **already positioned at the row to read**. The framework has already called `rs.next()` before invoking `mapRow`.
- `rowNum` is the 0-based index of the current row being iterated. It is **not** the database record ID.
- `T` is the object type created per row: record, DTO, JavaBean, or simple scalar type.
- The method may throw `SQLException`. Spring JDBC handles and translates exceptions through its data-access mechanism; there is no need to catch and swallow errors inside the mapper.
- `mapRow` may return `null` per the API contract, though applications should usually map to meaningful objects and define null semantics explicitly.
- **Never call `rs.next()`, `rs.close()`, `statement.close()`, or `connection.close()` inside `mapRow`**. The template manages cursor movement and resource lifecycles.
- **Never cache `ResultSet` for later reading**: the mapper is invoked while the result set is open; extract values and return an independent Java object.

A good mapper is typically **stateless**: it holds no mutable state across calls, increments no shared counter to alter content, and stores no state from earlier rows. Per the Javadoc, stateless `RowMapper` implementations are effectively reusable.

### Manual Mapper Example for a Java Record

Suppose the database has columns `id` (BIGINT), `title` (VARCHAR), `category` (VARCHAR), `price` (DECIMAL), and `in_stock` (BOOLEAN), all `NOT NULL`:

```java
public record Book(
        long id,
        String title,
        String category,
        BigDecimal price,
        boolean inStock) {}

public static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getString("category"),
                rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
```

This is a **snippet**, requiring imports for `BigDecimal` and `RowMapper` and placing the record/field inside a valid Java class; section 7 provides a complete runnable project.

This mapper has no knowledge of whether the query used `?` or `:category`. It only requires the `ResultSet` to contain those five columns (or matching aliases). Because the mapper holds no per-query state, the **same `BOOK_MAPPER` instance** can be passed to many different calls.

## 4. Same Mapper: Calling JdbcTemplate and NamedParameterJdbcTemplate

### 4.1. JdbcTemplate: Positional Parameters

```java
List<Book> classics = jdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = ? ORDER BY id",
        BOOK_MAPPER,
        "Java");
```

This is the `query(String sql, RowMapper<T> rowMapper, Object... args)` overload: `"Java"` binds to the first `?`. With multiple `?` markers, `args` order must match question-mark order. When reading older code using `query(sql, Object[] args, mapper)`, check its signature; several older overloads are now deprecated and should not be copied into new code.

### 4.2. NamedParameterJdbcTemplate: Map or SqlParameterSource

```java
List<Book> named = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category ORDER BY id",
        Map.of("category", "Java"),
        BOOK_MAPPER);
```

`NamedParameterJdbcTemplate` takes the value by key `category`, parses the SQL with `:category`, and translates it into a JDBC statement with the matching bind parameter. **The mapper passed in is completely identical to the line above**.

When you want to declare a JDBC type (especially SQL NULL) or multiple values, use `MapSqlParameterSource`:

```java
SqlParameterSource params = new MapSqlParameterSource()
        .addValue("category", "Java", Types.VARCHAR);

List<Book> named = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category ORDER BY id",
        params,
        BOOK_MAPPER);
```

Remember to import `org.springframework.jdbc.core.namedparam.MapSqlParameterSource`, `SqlParameterSource`, and `java.sql.Types`. `SqlParameterSource` **is solely responsible for supplying input values**, while `RowMapper` remains responsible for **output result rows**.

### 4.3. Both APIs Share the Same Spring JDBC Infrastructure

`NamedParameterJdbcTemplate` **wraps/delegates to** a classic `JdbcTemplate`; it is not a subclass of it. It implements `NamedParameterJdbcOperations`, whereas the classic template implements `JdbcOperations`. Wrapping an existing instance is valid:

```java
JdbcTemplate classic = new JdbcTemplate(dataSource);
NamedParameterJdbcTemplate named =
        new NamedParameterJdbcTemplate(classic);
```

If you already injected `NamedParameterJdbcTemplate` and need a method available only on the classic template, call `named.getJdbcOperations()` to access `JdbcOperations`; `named.getJdbcTemplate()` returns the concrete implementation when needed. **You do not need two mappers or two data sources** just to use both placeholder styles.

In Spring Boot, you can inject both configured templates; the example in section 7 intentionally constructs `NamedParameterJdbcTemplate` from the injected `JdbcTemplate` to highlight the shared foundation.

## 5. Conditions for Truly Safe Reuse

Sharing a mapper is valid when the **result contract** matches, not necessarily when the SQL is character-for-character identical. You can vary filter predicates, sort order, JOINs, or paging, as long as the columns required by the mapper still exist with expected types and semantics.

**Critical requirements:**

1. **Column names/aliases:** If the mapper calls `rs.getString("title")`, the SQL must SELECT a column or alias named `title`. `SELECT title AS name` breaks the contract unless you update the mapper or restore the alias.
2. **Data types:** `rs.getLong("id")` expects a value convertible to `long`; `rs.getBigDecimal("price")` expects an appropriate decimal number.
3. **NULL semantics:** `getBoolean`/`getLong` return default primitives on SQL NULL; if a column is nullable, use `rs.wasNull()` or wrapper/nullable mapping instead of assuming non-null.
4. **Complete projection:** `SELECT id, title` cannot use a mapper that still reads `category`, `price`, and `in_stock`. Widen the projection or create a dedicated mapper for the smaller DTO.
5. **Ambiguous column names in JOINs:** `SELECT b.id, a.id` creates an ambiguous `id` column. Specify explicit aliases like `b.id AS book_id`, `a.id AS author_id` and match the mapper accordingly.
6. **Domain object type:** `RowMapper<Book>` must return `Book`; do not reuse it by casting to `RowMapper<Order>` merely because column names look similar.
7. **Purity/statelessness:** Avoid shared mutable counters, network calls, or retaining `ResultSet` outside the callback. If a mapper depends on a timezone/locale, keep that dependency immutable and explicitly configured.
8. **Conversion policies:** `BigDecimal` scale, timestamp timezones, enums, and vendor types must remain consistent across queries.

Example of two SQL queries with **different filters yet identical projections**:

```sql
-- Used with JdbcTemplate:
SELECT id, title, category, price, in_stock
FROM books WHERE category = ?
ORDER BY id;

-- Used with NamedParameterJdbcTemplate:
SELECT id, title, category, price, in_stock
FROM books WHERE id IN (:ids)
ORDER BY id;
```

Even though the conditions differ, both can use `BOOK_MAPPER` because their output columns satisfy the same contract.

### Clarifying the Contract with a Projection Constant

In a DAO with many queries, one way to prevent column-name typos is defining a shared projection:

```java
private static final String BOOK_COLUMNS =
        "id, title, category, price, in_stock";

private static final RowMapper<Book> BOOK_MAPPER = (rs, n) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                rs.getString("category"), rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
```

When a query uses a JOIN, do not splice an unaliased projection into SQL; write a projection tailored to the actual tables. A constant reduces column duplication, yet **does not replace testing queries and mappers**.

## 6. Organizing RowMapper for Maintainable Code

There are three common options, all compatible with both classic and named templates:

| Organization Style | Example | When to Use |
| --- | --- | --- |
| `private static final RowMapper<Book>` lambda | `(rs,n) -> new Book(...)` | Short, stateless mapping localized to one DAO or config |
| Dedicated mapper class | `public final class BookRowMapper implements RowMapper<Book>` | Long mapping, shared across DAOs, or needing dedicated unit tests |
| Built-in Spring mapper | `BeanPropertyRowMapper` / `DataClassRowMapper` | Column/property names match conventions with no special domain logic |

### 6.1. A Dedicated Mapper Class Independent of Any Template

```java
package com.example.library;

import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public final class BookRowMapper implements RowMapper<Book> {
    @Override
    public Book mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getString("category"),
                rs.getBigDecimal("price"),
                rs.getBoolean("in_stock"));
    }
}
```

This is a **code-organization snippet**, requiring `Book` to be accessible in the same package or via import. The class stores no `JdbcTemplate`, `DataSource`, or query string. Both `JdbcTemplate.query(..., mapper, args)` and `NamedParameterJdbcTemplate.query(..., params, mapper)` accept `new BookRowMapper()`; you can also keep a singleton instance to avoid repeated allocations. No `@Component` annotation is needed just to pass a mapper to the API.

### 6.2. BeanPropertyRowMapper: Mutable JavaBeans

`BeanPropertyRowMapper<BookBean>` can map column `in_stock` to JavaBean property `inStock` when names follow conventions and the bean has a no-arg constructor and matching setters.

```java
RowMapper<BookBean> beanMapper =
        BeanPropertyRowMapper.newInstance(BookBean.class);
```

It saves writing each `rs.getXxx` call, yet requires checking setters, aliases, conversions, and nullability; it is not a universal fit for complex DTOs. If the target object is an **immutable Java record**, use a lambda/constructor mapper or a data-class-capable mapper.

### 6.3. DataClassRowMapper: Java Records and Constructor Binding

`DataClassRowMapper` supports Java records and classes whose constructor parameter names match columns:

```java
RowMapper<Book> mapperForRecord =
        DataClassRowMapper.newInstance(Book.class);
```

For `Book(long id, String title, String category, BigDecimal price, boolean inStock)` and column/alias `in_stock` matching `inStock`, the mapper can bind via the record's canonical constructor. Still, using an auto-mapper requires testing column aliases, constructor parameter names, Java/SQL nullable types, and conversions on your actual Spring version. **In the runnable example in section 7, a manual mapper is chosen** so behavior is explicit without relying on auto-mapping conventions.

### 6.4. When Should You Not "Share Everything"?

Do not force a `RowMapper<Book>` onto a report returning only `COUNT(*)` or an aggregate DTO with different column names/types. Pick `SingleColumnRowMapper` or `queryForObject(sql, Integer.class, ...)` for single scalar values, and a dedicated mapper for report projections.

**Principle:** Reuse the *result mapping contract*, not class names at all costs.

## 7. Runnable Lab: One RowMapper, Two Parameter Styles

This project uses **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC, and in-memory H2**. Spring Boot 3.5.16 was released on 2026-06-25 and is the final OSS release of the 3.5.x line; it is chosen here to pin a fixed version for the demo. **New projects should choose a currently supported Spring Boot line** rather than copying a version solely from this example.

The lab uses one `books` table. The first two queries share the **exact same projection, filter, and sort order** so the two `List<Book>` results can be compared directly; the third query uses a named list parameter `:ids` while reusing the same mapper.

### 7.1. Directory Structure

```text
rowmapper-reuse/
├── pom.xml
└── src/main/
    ├── java/com/example/rowmapping/RowMapperReuseApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rowmapper-reuse</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/resources/schema.sql

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    category VARCHAR(60) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    in_stock BOOLEAN NOT NULL
);
```

### 7.4. src/main/resources/data.sql

```sql
INSERT INTO books (id, title, category, price, in_stock)
VALUES (1, 'Java Basics', 'Java', 12.50, TRUE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (2, 'Spring JDBC', 'Java', 29.90, TRUE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (3, 'SQL 101', 'Database', 17.00, FALSE);

INSERT INTO books (id, title, category, price, in_stock)
VALUES (4, 'Index Tuning', 'Database', 35.00, TRUE);
```

### 7.5. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

### 7.6. src/main/java/com/example/rowmapping/RowMapperReuseApplication.java

```java
package com.example.rowmapping;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class RowMapperReuseApplication {

    public record Book(
            long id,
            String title,
            String category,
            BigDecimal price,
            boolean inStock) {}

    // Single shared instance for every query with the matching projection.
    private static final RowMapper<Book> BOOK_MAPPER =
            (rs, rowNum) -> new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getString("category"),
                    rs.getBigDecimal("price"),
                    rs.getBoolean("in_stock"));

    private static final String COLUMNS =
            "SELECT id, title, category, price, in_stock FROM books ";

    public static void main(String[] args) {
        SpringApplication.run(RowMapperReuseApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            // Named wrapper reusing the injected classic JdbcTemplate.
            NamedParameterJdbcTemplate named =
                    new NamedParameterJdbcTemplate(jdbc);

            // A. Classic: WHERE category = ?.
            List<Book> classics = jdbc.query(
                    COLUMNS + "WHERE category = ? ORDER BY id",
                    BOOK_MAPPER,
                    "Java");

            // B. Named: WHERE category = :category.
            List<Book> byNames = named.query(
                    COLUMNS + "WHERE category = :category ORDER BY id",
                    Map.of("category", "Java"),
                    BOOK_MAPPER);

            System.out.println("classicIds=" + ids(classics));
            System.out.println("namedIds=" + ids(byNames));
            System.out.println("sameRows=" + classics.equals(byNames));

            // C. Named :ids expanded according to input list.
            List<Book> selected = named.query(
                    COLUMNS + "WHERE id IN (:ids) ORDER BY id",
                    new MapSqlParameterSource(
                            "ids", List.of(1L, 3L)),
                    BOOK_MAPPER);
            System.out.println("selectedIds=" + ids(selected));

            // D. Two queryForObject calls with the same mapper.
            Book singleClassic = jdbc.queryForObject(
                    COLUMNS + "WHERE id = ?",
                    BOOK_MAPPER,
                    3L);
            Book singleNamed = named.queryForObject(
                    COLUMNS + "WHERE id = :id",
                    Map.of("id", 3L),
                    BOOK_MAPPER);
            System.out.println("singleTitle=" + singleClassic.title());
            System.out.println(
                    "sameSingle=" + singleClassic.equals(singleNamed));

            // E. Multi-row query with no match returns an empty list.
            List<Book> missing = named.query(
                    COLUMNS + "WHERE category = :category",
                    Map.of("category", "Missing"),
                    BOOK_MAPPER);
            System.out.println("emptyCount=" + missing.size());
        };
    }

    private static List<Long> ids(List<Book> books) {
        return books.stream().map(Book::id).toList();
    }
}
```

**Run** in the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

**Seven lines printed by the application itself**, excluding Maven/Spring startup logs:

```text
classicIds=[1, 2]
namedIds=[1, 2]
sameRows=true
selectedIds=[1, 3]
singleTitle=SQL 101
sameSingle=true
emptyCount=0
```

**Why is this output reliable?**

1. `schema.sql` creates the table in H2; `data.sql` inserts four books with IDs 1–4.
2. Both classic and named queries filter `category='Java'` and `ORDER BY id` for deterministic results: the same two records with IDs 1 and 2.
3. A Java `record` implements `equals` by component values; with the same projection and values mapped by one `BOOK_MAPPER`, both `List<Book>` instances are element-wise equal. `sameRows=true` verifies **content**, not merely row counts.
4. `IN (:ids)` receives `[1, 3]`; Spring converts it into the matching JDBC placeholders. Results are sorted by ascending ID.
5. Both `queryForObject` calls take ID 3 and map to `SQL 101`; record equality confirms identical data semantics.
6. Querying category `Missing` matches no rows; `query(...)` returns an empty `List`, `emptyCount=0`.
7. **The mapper never had to be rewritten once.** `BOOK_MAPPER` stayed unchanged while only the SQL template and binding style varied.

*Demo limitations:* H2 suffices for foundational examples, yet production code must be tested against the real driver and DB. This is a multi-file Maven project; do not compile the Java file standalone with `javac` without Spring/H2 dependencies. The demo code is written for Spring 6.x APIs in Boot 3.5.16; the command and stdout show expected behavior rather than replacing integration tests in your environment.

## 8. Using queryForObject, query, and Stream: Same Mapper, Different Cardinality

Both templates offer:

- `query(...)` + `RowMapper<T>`: returns `List<T>`; 0 rows → empty list; many rows → one mapped object per row.
- `queryForObject(...)` + `RowMapper<T>`: **expects exactly one row**; 0 rows typically throws `EmptyResultDataAccessException`, multiple rows throws `IncorrectResultSizeDataAccessException`. A mapper may return `null` for the matched row itself, so the return type can be nullable.
- Streaming APIs such as `queryForStream(...)`: still use the mapper, yet the **Stream must be closed** with `try-with-resources` because underlying JDBC resources remain open. Never return a lazy stream across a transaction boundary without clear ownership and closing rules.

Single-record example (snippet with declared mapper and templates):

```java
Book byId = jdbcTemplate.queryForObject(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id = ?",
        BOOK_MAPPER,
        1L);

Book sameBook = namedJdbcTemplate.queryForObject(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id = :id",
        Map.of("id", 1L),
        BOOK_MAPPER);
```

**Common mistake:** `queryForObject` is not `findObject` from certain `SqlQuery` APIs in other packages. Never assume `JdbcTemplate.queryForObject` "returns null when not found". If business logic allows missing records, use `query(...)` and apply an `Optional` policy or catch the specific exception intentionally.

### Streams with the Same Mapper and Closing Responsibility

```java
// Snippet: Stream must stay scoped while resources remain open.
try (Stream<Book> rows = namedJdbcTemplate.queryForStream(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category",
        Map.of("category", "Java"),
        BOOK_MAPPER)) {
    rows.forEach(book -> System.out.println(book.title()));
}
```

Requires `import java.util.stream.Stream`. This is an illustrative snippet, not part of the fixed output in section 7. **RowMapper does not close the stream**; the caller of `queryForStream` is responsible for closing it. Stream behavior can also depend on transaction scope, fetch size, and driver.

## 9. Reusing the Mapper When Named SQL Has IN Lists or Variable Conditions

`NamedParameterJdbcTemplate` accepts a collection for `IN (:ids)`, generating matching `?` placeholders and binding each value:

```java
List<Long> ids = List.of(10L, 20L, 30L);
List<Book> books = namedJdbcTemplate.query(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE id IN (:ids) ORDER BY id",
        new MapSqlParameterSource("ids", ids),
        BOOK_MAPPER);
```

**Only the input changes; the mapper stays identical.** However:

- **Empty lists:** `IN ()` may be invalid syntax depending on the database. When "no IDs selected" means empty results, return `List.of()` before querying or take an explicit SQL branch rather than guessing how the driver behaves.
- **Element limits:** DBs limit bind parameters and `IN` expressions. For large ID sets, consider temp tables, joins, chunking, or DB-specific strategies; you can still keep the same mapper.
- **Never bind identifiers:** `:columnName` cannot substitute column names or `ORDER BY`. Dynamic SQL structure requires an allowlist of trusted column/table names.
- **Do not conflate mapper with named parameters:** The mapper runs after the SQL executes and never cares how many values `:ids` originally held.

### Pagination and Sorting

The same mapper works for SQL with `LIMIT/OFFSET` (where supported by the DB), provided the projection stays consistent. Always include a deterministic `ORDER BY` tie-breaker to avoid non-deterministic pagination. Named SQL with many filters is often easier to maintain than positional parameters, yet that is an **input-binding** benefit—it does not make `RowMapper` map differently.

## 10. Input NULL Parameters and Output NULL Column Handling Are Independent

**Input NULL (WHERE/bind):** With `NamedParameterJdbcTemplate`, you can declare an SQL type via `MapSqlParameterSource`:

```java
SqlParameterSource params = new MapSqlParameterSource()
        .addValue("name", null, Types.VARCHAR);
```

This only shows how to supply a typed NULL. **Warning:** SQL `WHERE title = NULL` does not match rows like `WHERE title IS NULL` under SQL three-valued logic. For optional filters, choose the SQL statement or `IS NULL` condition matching business intent—do not assume binding null rewrites the comparison operator.

**Output NULL (ResultSet):** Both templates send the same columns to the same mapper; for nullable columns, the mapper must preserve null meaning accurately:

```java
RowMapper<BookStatus> statusMapper = (rs, rowNum) -> {
    long id = rs.getLong("id");

    boolean raw = rs.getBoolean("available");
    Boolean available = rs.wasNull() ? null : raw;

    return new BookStatus(id, available);
};
```

Requires `record BookStatus(long id, Boolean available) {}` and an `available` column; illustrative snippet. Calling `rs.getBoolean` returns `false` on SQL NULL, and ignoring `wasNull()` silently turns SQL NULL into `false`. Integer getters like `getInt`/`getLong` share the same trap.

**Numeric formatting:** `BigDecimal` preserves decimal precision/scale better than `double` for money. Two queries may map `BigDecimal` values with different scales if the DB or SQL casts differ; `BigDecimal` equality inside records considers scale too. Thus comparing outputs across templates only makes sense when both queries apply the same expressions and columns.

**Dates and times:** When a mapper reads `LocalDateTime` or `Timestamp`, SQL/driver type selection and timezone policies remain critical, yet are unaffected by whether SQL parameters are bound positionally or by name.

## 11. How to Separate Mapping from DAOs and Services

When a DAO has two query paths—lookup by ID via `JdbcTemplate` and lookup by group via `NamedParameterJdbcTemplate`—this structure avoids duplicate mapping:

```text
BookService
    |
    v
BookDao
   |-- JdbcOperations classic
   |-- NamedParameterJdbcOperations named
   |
   +-- RowMapper<Book> BOOK_MAPPER (in one place)
   |
   |-- findById(id): classic queryForObject
   |-- findByCategories(categories): named query IN (:categories)
   '-- findInStock(): query using either template
```

The Service never sees `ResultSet`; the DAO returns mapped records/DTOs or lists. When the same mapper is shared across multiple DAOs, place a `BookRowMapper` class in a shared data-access package; avoid placing it in controllers or domain entities since it is a JDBC detail.

**A mapper does not have to be a Spring bean:** a stateless `private static final RowMapper<Book>` in the DAO is plenty. When complex mapping needs injected converters (e.g., money or timezone policies), you can create a mapper class with immutable dependencies and register it as a bean. Either way, never store per-request mutable state inside a singleton mapper.

### Anti-Duplication Example

**Before** (undesirable):

```java
List<Book> a = jdbc.query(sqlA, (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock")), "Java");

List<Book> b = named.query(sqlB, params, (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock")));
```

**After** (removes mapping duplication without altering business logic):

```java
RowMapper<Book> bookMapper = (rs, i) ->
        new Book(rs.getLong("id"), rs.getString("title"),
                 rs.getString("category"), rs.getBigDecimal("price"),
                 rs.getBoolean("in_stock"));

List<Book> a = jdbc.query(sqlA, bookMapper, "Java");
List<Book> b = named.query(sqlB, params, bookMapper);
```

These are **snippets assuming `sqlA`/`sqlB`/`jdbc`/`named`/`params` exist**, not standalone programs. The benefit is editing mapping logic in one place; still test that both queries return the promised columns.

## 12. Alongside JdbcClient, RowCallbackHandler, and ResultSetExtractor

In Spring Framework 6.1+, `JdbcClient` offers a fluent API combining positional and named binding in one facade; it also accepts `RowMapper<T>`:

```java
// Snippet: JdbcClient client created from datasource/template.
List<Book> books = client.sql(
        "SELECT id, title, category, price, in_stock " +
        "FROM books WHERE category = :category")
        .param("category", "Java")
        .query(BOOK_MAPPER)
        .list();
```

`JdbcClient` does not make `RowMapper` obsolete. You can keep your mapper when migrating from classic/named templates to the fluent API, updating call sites one by one with regression tests. Advanced cases like batching or stored procedures may still use the templates directly.

**Distinguishing callbacks:**

| Callback | Responsibility | Reusable Across Classic/Named? |
| --- | --- | --- |
| `RowMapper<T>` | Maps **each row** to a `T`; template collects list or single value | **Yes**, topic of this lesson |
| `RowCallbackHandler` | Processes each row via side effect/callback without returning a `T` | Accepted by certain overloads of both templates; different API/contract |
| `ResultSetExtractor<T>` | Processes the **entire ResultSet** and returns an arbitrary result | Uses matching overloads; not a drop-in swap for RowMapper |
| `PreparedStatementSetter` | Binds inputs and configures statement | Not a mapper; does not map results |
| `SqlParameterSource` | Supplies named input values/types | Not a mapper; does not read ResultSet |

A `RowMapper` should never loop with `while (rs.next())` or accumulate totals across rows, because each callback already receives one current row. When you must map a multi-row parent-child structure into one object or aggregate across the whole `ResultSet`, consider `ResultSetExtractor` or a suitably structured query.

## 13. Transactions and Resources: Sharing a Mapper Does Not Govern Transactions

Both `JdbcTemplate` and `NamedParameterJdbcTemplate` use Spring JDBC and manage creating/closing `PreparedStatement`/`ResultSet` for normal queries. `NamedParameterJdbcTemplate` delegates to classic operations, so changing placeholder style never gives a `RowMapper` ownership of a connection.

**When sharing the same datasource and transaction manager,** calls from a `@Transactional` service can participate in the same database transaction. Yet reusing a mapper **does not create a transaction by itself**:

```java
// Illustrative example, assuming DAO exposes two query methods.
@Service
public class BookReportService {
    private final BookDao dao;

    public BookReportService(BookDao dao) {
        this.dao = dao;
    }

    @Transactional(readOnly = true)
    public List<Book> report() {
        List<Book> a = dao.findClassic();
        List<Book> b = dao.findNamed();
        return a.size() >= b.size() ? a : b;
    }
}
```

This is an architectural snippet needing imports and a real `BookDao`. `@Transactional(readOnly=true)` is an infrastructure hint, **not a guarantee that every driver blocks writes**; isolation level and whether both queries see the same snapshot depend on DB/transaction settings. Never open long-lived transactions solely to reuse a mapper.

Likewise, never close `ResultSet`, `Statement`, or `Connection` inside a mapper. Once `query(...)` completes, data already mapped into records/DTOs can be used independently of JDBC resources.

## 14. Common Pitfalls When Reusing RowMapper

1. **Writing two identical mappers just because `?` differs from `:name`.** Both templates share `RowMapper<T>`; reuse output logic instead of duplicating code.
2. **Assuming RowMapper binds inputs.** Binding belongs to the template/`SqlParameterSource`; `mapRow` runs after the query.
3. **Calling `rs.next()` inside the mapper.** The template already advances the cursor; calling `next()` skips rows or corrupts results.
4. **Closing `ResultSet` inside the mapper.** Breaks processing of subsequent rows; the template owns the resource.
5. **Retaining `ResultSet` in an object for later reads.** The cursor may already be closed when the query returns.
6. **Mismatched SQL projections:** the second query omits `price` or aliases `title` → `name`, breaking the shared mapper.
7. **JOINs with two `id` columns:** the mapper can read the wrong one; alias explicitly before reusing.
8. **Using `rowNum` as a business ID.** It is a 0-based result row index.
9. **Storing request data in mutable fields of a singleton mapper.** Causes thread races; pass filters via SQL parameters, not the mapper.
10. **Ignoring nullable SQL columns:** primitive getters mask `NULL` as 0/false; use nullable types/`wasNull()`.
11. **Confusing empty `query` with empty `queryForObject`.** `query` returns an empty list; `queryForObject` expects one row and throws an exception.
12. **Assuming SQL queries are equivalent just because the mapper is shared.** WHERE/ORDER BY/JOIN/pagination can change the dataset.
13. **Using `BeanPropertyRowMapper` for records without setters.** Choose `DataClassRowMapper` or an explicit constructor/lambda mapper.
14. **Using named params to bind table/column names.** `:column` binds a value, not an SQL identifier. Use an allowlist for dynamic SQL.
15. **Passing empty lists carelessly to `IN (:ids)`.** Results/syntax depend on DB; handle empty lists deliberately.
16. **Forgetting to close `queryForStream`.** The stream holds JDBC resources; use try-with-resources.
17. **Refactoring without testing cardinality/null/precision.** New code may compile while changing business semantics.
18. **Treating mapper reuse as result caching.** A mapper is just a mapping function; two queries still execute separate SQL and do not cache rows.

## 15. Testing Equivalence Across Both Templates

A reliable test verifies **results and mapping**, not merely object counts. Prepare a fixed database fixture, pass the same mapper, and run queries equivalent in projection, filter, and sort order.

### Minimum Test Cases

| Test | Expected Behavior |
| --- | --- |
| Category with 2 records, classic vs. named | Both `List<Book>` are equal when ordering is deterministic |
| Category with no records | Both `query(...)` calls return empty lists |
| Query by ID with 1 record | Both `queryForObject` calls return equal records |
| Non-existent ID with `queryForObject` | Both follow the contract and throw `EmptyResultDataAccessException` |
| SQL returning >1 row for `queryForObject` | Cardinality error instead of returning first element |
| Nullable columns | Mapper preserves nulls accurately instead of coercing to 0/false |
| JOIN/aliases | Mapper reads the exact intended table/column without ambiguity |
| `IN (:ids)` with 1, many, and 0 items | List expansion works; empty case handled explicitly |
| SQL errors / schema changes | Both throw appropriate `DataAccessException` |
| Transaction with multiple queries | Shared datasource/manager; reads follow desired isolation |

You can use Spring Boot `@JdbcTest` / integration tests with H2 for core logic; test on a production-like DB whenever behavior depends on dialect, encoding, query plan, timezone, or isolation.

**Never omit `ORDER BY` and compare with `List.equals` by default:** SQL makes no row-order guarantee without `ORDER BY`. If business logic only cares about the set of IDs, sort before comparing or compare as a `Set` when elements are unique by contract.

### Illustrative Assertion

```java
List<Book> classic = jdbc.query(sqlClassic, BOOK_MAPPER, "Java");
List<Book> named = namedJdbc.query(
        sqlNamed, Map.of("category", "Java"), BOOK_MAPPER);

if (!classic.equals(named)) {
    throw new AssertionError("Classic and named mappings differ");
}
```

This snippet requires matching projections, equivalent predicates/sorts, and fixed test data; in real projects use JUnit/AssertJ assertions. Sharing one mapper instance **eliminates duplication**, not guarantee by itself that two SQL queries return the same rows.

## 16. A Safe Refactoring Path from Legacy Code

If a DAO currently holds two identical anonymous mappers:

1. **Document current behavior:** SQL, all aliases, data types, NULL handling, cardinality rules, row ordering, and exceptions.
2. **Extract one stateless `RowMapper<Book>`** from both call sites without changing SQL or parameters yet.
3. **Have both `JdbcTemplate` and `NamedParameterJdbcTemplate` use that same mapper instance**; run comparison tests.
4. **If migrating positional to named**, convert each SQL `?` → `:name` and move args into `Map`/`SqlParameterSource`, **keeping the mapper unchanged**.
5. **Check subtle differences:** `queryForObject` vs. `query`, nulls, aliases, required columns, ordering, vendor conversions, transactions.
6. **Measure and test after changes:** repository integration tests, SQL query counts, timings/connection pools, concurrent load, and DB permissions.
7. If migrating to `JdbcClient` later, **you can keep reusing the mapper** without rewriting mapping logic for the fluent API.

*Do not migrate everything for its own sake.* A working, readable DAO can keep both APIs if appropriate. The primary goal is **centralizing mapping logic** so edits happen in one place, tests stay clear, and behavior stays unchanged.

## 17. Self-Check with Answers

**Q1:** `JdbcTemplate` uses `?`, whereas `NamedParameterJdbcTemplate` uses `:category`. Do you need two different `RowMapper<Book>` instances?  
**A:** No. Use the same mapper if the SQL results have matching columns, aliases, and types. Placeholder differences only affect input binding.

**Q2:** A mapper calls `rs.next()` before `getString("title")`. Does this follow the contract?  
**A:** No. The framework already positions `rs` on the current row; calling `next()` inside the mapper skips rows.

**Q3:** The classic query selects all of `id,title,category,price,in_stock`. The named query only selects `id,title`. Can both share the current mapper?  
**A:** No, because the mapper accesses columns the named query does not return. Fix the projection/aliases or create a mapper for a smaller DTO.

**Q4:** What do `MapSqlParameterSource` and `RowMapper` each do?  
**A:** `MapSqlParameterSource` supplies **named input values and SQL types**; `RowMapper` maps **output rows**.

**Q5:** Does `queryForObject` return `null` or throw an exception when no row is found?  
**A:** Across both Spring JDBC templates, it expects exactly one row; 0 rows typically throws `EmptyResultDataAccessException`. It can return null only when one row exists and the mapper itself returns null.

**Q6:** Should you share a `static final RowMapper<Book>` across many requests?  
**A:** Yes if it is stateless and any dependencies are thread-safe; no if the mapper stores mutable request state, connections, or ResultSets.

**Q7:** What happens with `IN (:ids)` and an empty list?  
**A:** Never assume it returns an empty result cleanly; an empty list can produce invalid SQL. Handle it before calling the DB or use another tested strategy.

**Q8:** Is `BeanPropertyRowMapper` the default choice for Java records?  
**A:** No. Java records are immutable and lack JavaBean setters; prefer `DataClassRowMapper` or an explicit constructor/lambda mapper.

**Q9:** Do a named template query and a classic query share the same `@Transactional` context because they share a mapper?  
**A:** No. Transactions depend on the datasource/transaction manager and calls passing through Spring transaction advice; mappers never start transactions.

**Q10:** Can a mapper you already wrote be used with `JdbcClient`?  
**A:** Yes. `JdbcClient` accepts `RowMapper<T>` for row mapping; specialized APIs may still call the templates directly.

## 18. Code Review Checklist

- [ ] Distinguished `JdbcTemplate` (positional) from `NamedParameterJdbcTemplate` (named) on the SQL input side.
- [ ] Shared **one stateless RowMapper<T>** whenever the result contract matches.
- [ ] Mapper only reads the current row and **never calls `next()`/`close()`**.
- [ ] Both classic and named SQL return all columns, aliases, and types needed by the mapper.
- [ ] No request data or connections are stored in mutable mapper fields.
- [ ] Each method picks the right `query`/`queryForObject` overload and cardinality contract.
- [ ] Named parameter maps include all keys and types; positional arguments are in exact order.
- [ ] SQL queries may differ in WHERE clauses while keeping the mapper valid for matching projections.
- [ ] `IN (:ids)` handles empty lists and DB limits.
- [ ] Nullable SQL values, `BigDecimal`, timestamps, and booleans have explicit mapping rules.
- [ ] Spring-owned resources are never closed inside mappers; streams are closed by callers.
- [ ] Both query paths have integration tests verifying mapping, exceptions, and transactions.

## Official References

- Spring Framework — Using the JDBC Core Classes / JdbcTemplate / NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Javadoc — `RowMapper<T>`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Javadoc — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Javadoc — `NamedParameterJdbcTemplate`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Javadoc — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Spring Javadoc — `BeanPropertyRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Javadoc — `DataClassRowMapper`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — Parameter Handling / IN expression list: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html
- Spring Boot 3.5.16 release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Key takeaway:** **`RowMapper` is an *output* mapping contract, independent of *input* parameter syntax.** When SQL results share the same columns, aliases, and types, a single `RowMapper<Book>` works identically for `JdbcTemplate.query(sql, mapper, args)` and `NamedParameterJdbcTemplate.query(sql, params, mapper)`. This eliminates duplication, keeps mapping consistent, and lets you switch from `?` to `:name` without rewriting row-reading logic.