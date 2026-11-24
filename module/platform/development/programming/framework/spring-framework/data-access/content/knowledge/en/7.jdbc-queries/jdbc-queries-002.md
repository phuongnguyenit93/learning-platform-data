# Querying a Single Object and Row/Column Requirements

## 1. What Problem Does This Lesson Solve?

When querying a database with **Spring JDBC**, the question "fetch a single object" can mean several different things:

- Must definitely find **exactly one row** (for example: reading an order by a validated primary key).
- May find **zero or one row** (for example: looking up a product by code; non-existence is a normal outcome).
- Need a **single scalar value** from **one row, one column** (for example: `COUNT(*)`, product name, or price).
- Need an **object with multiple properties**, mapped from **one row consisting of multiple columns**.

These needs are **not equivalent**. Specifically, `JdbcTemplate.queryForObject(...)` is an API with a row-count constraint; the `Class<T>` variant also enforces a column-count constraint.

Goals after this lesson:

1. Distinguish the two dimensions of a `ResultSet`: **row count** (cardinality) and **column count** (shape).
2. Use `queryForObject(sql, Class<T>, args...)`, `queryForObject(sql, RowMapper<T>, args...)`, and `query(sql, RowMapper<T>, args...)` properly.
3. Distinguish **no rows**, **one row containing SQL NULL**, **multiple rows**, **multiple columns**, and **Java type mapping failures**.
4. Understand and handle `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException`, and `IncorrectResultSetColumnCountException` according to the business contract.
5. Apply `Optional<T>` for queries that may return nothing; protect uniqueness with constraints rather than "blindly grabbing the first row".
6. Write, run, and test a Spring Boot/JDBC example on Java 17+ with deterministic results.

This lesson is about **JDBC querying**: the focus is on the data contract semantics of queries, mapping APIs, and exceptions. HTTP, JPA, or advanced transaction choices are mentioned only when they directly affect how results are consumed.

## 2. Two Dimensions of Results: Rows and Columns

A SQL query returns a `ResultSet` with a **number of rows** and the set of selected **columns**. For example:

```sql
SELECT id, sku, name
FROM products
WHERE id = 10;
```

If `id` is a primary key and the row exists, the result has **one row, three columns**. This represents one product object, but **not** a single-column scalar value.

```sql
SELECT name
FROM products
WHERE id = 10;
```

This result has **one row, one column**. It is suitable for mapping to `String`.

| Result Shape | Meaning | Suggested API |
| --- | --- | --- |
| 0 rows, one or more defined columns | No record matches the condition | `query(...).isEmpty()` / `Optional.empty()` if absence is valid |
| 1 row × 1 column | A single value such as name, total count, price | `queryForObject(sql, String.class, ...)` or the needed type |
| 1 row × multiple columns | An object with multiple properties | `queryForObject(sql, rowMapper, ...)` |
| Multiple rows × 1 column | A list of values of the same type | `queryForList(sql, String.class, ...)` or `query` with a mapper |
| Multiple rows × multiple columns | A list of objects | `query(sql, rowMapper, ...)` |
| 1 row × 1 SQL NULL column | **Row exists**, column value is NULL | `queryForObject(..., Class<T>, ...)` may return Java `null` |

**Important:** "one object" in a programming language does **not** mean the SQL may only return one column. `RowMapper<Product>` can read six columns of a single row to build one `Product` object.

Visualized as a matrix:

```text
SELECT name FROM products WHERE id = 10
+-------------------+
| name              |  1 row x 1 column
+-------------------+
| Java Fundamentals |
+-------------------+

SELECT id, sku, name FROM products WHERE id = 10
+----+-----------+-------------------+
| id | sku       | name              |  1 row x 3 columns
+----+-----------+-------------------+
| 10 | BOOK-JAVA | Java Fundamentals |
+----+-----------+-------------------+

SELECT id, name FROM products WHERE name = 'Java Fundamentals'
+----+-------------------+
| id | name              |  2 rows x 2 columns
+----+-------------------+
| 10 | Java Fundamentals |
| 30 | Java Fundamentals |
+----+-------------------+
```

## 3. Two queryForObject Overloads to Remember

### 3.1. queryForObject(sql, requiredType, args...): Exactly One Row, Exactly One Column

In Spring Framework 6.x, the commonly used signature is:

```java
<T> T queryForObject(String sql, Class<T> requiredType, Object... args)
```

Examples:

```java
String name = jdbcTemplate.queryForObject(
        "SELECT name FROM products WHERE id = ?",
        String.class,
        10L
);

Long total = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM products",
        Long.class
);
```

In this example, `jdbcTemplate` is a `JdbcTemplate` bean configured from a `DataSource`; the statements require the corresponding `products` table.

Actual contract:

- The result must have **exactly one row**. If there are no rows, the method throws `EmptyResultDataAccessException`, a subclass of `IncorrectResultSizeDataAccessException`.
- If there is **more than one row**, it throws `IncorrectResultSizeDataAccessException`.
- For the row being read, the query must have **exactly one column**. If there are multiple columns, it throws `IncorrectResultSetColumnCountException`.
- The value is converted to `requiredType` based on the capabilities of `SingleColumnRowMapper`/conversion and the JDBC driver. Not every SQL type can be converted to every `Class<T>`.
- If the row exists but the column contains **SQL NULL**, the returned Java value may be `null`, **not** `EmptyResultDataAccessException`.

The column shape does not automatically narrow just because you requested `String.class`. If you write:

```java
String wrong = jdbcTemplate.queryForObject(
        "SELECT name, price FROM products WHERE id = ?",
        String.class,
        10L
);
```

there is no rule to "pick the first column": when the row is mapped, Spring detects two columns and throws `IncorrectResultSetColumnCountException`.

The `queryForObject(String sql, Class<T> requiredType, Object... args)` form also binds parameters with a `PreparedStatement`, avoiding concatenating user values into SQL. You do not need to manually create a `Connection` or close a `ResultSet` when using `JdbcTemplate` via standard calls.

### 3.2. queryForObject(sql, rowMapper, args...): Exactly One Row, Multiple Columns Allowed

The second form:

```java
<T> T queryForObject(
        String sql, RowMapper<T> rowMapper, Object... args
)
```

Example mapping `Product` from six columns:

```java
Product product = jdbcTemplate.queryForObject(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE id = ?
        """,
        (rs, rowNum) -> new Product(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getString("description"),
                rs.getBoolean("active")
        ),
        10L
);
```

`RowMapper` can read as many columns as needed, provided the SQL actually returns those columns. The invariant of `queryForObject` **remains exactly one row**: 0 rows throws `EmptyResultDataAccessException`; 2 or more rows throws `IncorrectResultSizeDataAccessException`.

In JDBC, `rowNum` is the row index when the mapper is invoked, starting at 0. It is not the primary key and is usually unnecessary when mapping a single object.

**Pitfall:** returning `null` from `RowMapper` itself causes `queryForObject` to potentially return `null` even though the SQL returned one row. Design your mapper to return a valid object or throw a clear error. Do not return `null` from a mapper to implicitly signal "no rows".

### 3.3. Do Not Confuse Legacy Overloads

You may encounter older code:

```java
// The overload style with Object[] before requiredType
// has been marked deprecated in Spring 6.x releases.
jdbcTemplate.queryForObject(
        "SELECT name FROM products WHERE id = ?",
        new Object[] {10L},
        String.class
);
```

For new code, prefer placing `requiredType` or `RowMapper` before bind parameters as in the first two examples. This reduces overload ambiguity and aligns with Spring Framework 6.x documentation.

## 4. Behavior Matrix: 0, 1, Multiple Rows and 1, Multiple Columns

Assuming queries execute normally, SQL is valid, and Java types match:

| Method | 0 rows | 1 row, 1 column | 1 row, multiple columns | Multiple rows |
| --- | --- | --- | --- | --- |
| `queryForObject(sql, Class<T>, args...)` | `EmptyResultDataAccessException` | Value of type `T`, or `null` if SQL NULL | `IncorrectResultSetColumnCountException` when mapper reads the row | `IncorrectResultSizeDataAccessException` |
| `queryForObject(sql, RowMapper<T>, args...)` | `EmptyResultDataAccessException` | Mapper builds `T` | Mapper may use all columns to build `T` | `IncorrectResultSizeDataAccessException` |
| `queryForMap(sql, args...)` | `EmptyResultDataAccessException` | Map with 1 key/value pair | Map for the columns of **one** row | `IncorrectResultSizeDataAccessException` |
| `query(sql, RowMapper<T>, args...)` | `List.empty()` | List of one object | List of one object mapped from multiple columns | List of objects |
| `queryForList(sql, Class<T>, args...)` | Empty list | List of one scalar | Incompatible with single-column mapper if rows exist | List of scalars if each row has one column |

This table is an **API contract**, not a PostgreSQL-specific SQLSTATE error table. `JdbcTemplate` translates necessary JDBC errors into Spring's `DataAccessException` hierarchy; the row/column count check exceptions above are raised when processing results.

Regarding inheritance hierarchy:

```text
DataAccessException
  +-- IncorrectResultSizeDataAccessException
  |     +-- EmptyResultDataAccessException
  +-- DataRetrievalFailureException
        +-- IncorrectResultSetColumnCountException
```

Note that `IncorrectResultSetColumnCountException` is **not** a subclass of `IncorrectResultSizeDataAccessException`. If you want to log/diagnose column-count errors specifically, do not only catch `IncorrectResultSizeDataAccessException`.

## 5. Sample Data: Self-Runnable on PostgreSQL

Create the table in an **empty learning database**. The schema keeps fixed IDs to produce deterministic demonstration results:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    description VARCHAR(250),
    active BOOLEAN NOT NULL
);

INSERT INTO products (id, sku, name, price, description, active)
VALUES
    (10, 'BOOK-JAVA', 'Java Fundamentals', 125000.00, NULL, TRUE),
    (20, 'BOOK-SPRING', 'Spring JDBC', 199000.00, 'Hands-on', TRUE),
    (30, 'BOOK-ADV', 'Java Fundamentals', 155000.00, NULL, FALSE);
```

From this data, cases with deterministic outcomes:

| SQL | Row count | Column count | Value / key takeaway |
| --- | ---: | ---: | --- |
| `SELECT name FROM products WHERE id = 10` | 1 | 1 | `Java Fundamentals` |
| `SELECT id, sku, name FROM products WHERE id = 10` | 1 | 3 | One row mapped to an object |
| `SELECT name FROM products WHERE id = 999` | 0 | 1 | No rows; not SQL NULL |
| `SELECT description FROM products WHERE id = 10` | 1 | 1 | Column value `NULL` |
| `SELECT id FROM products WHERE name = 'Java Fundamentals'` | 2 | 1 | Two rows, because `name` is not unique |
| `SELECT COUNT(*) FROM products WHERE id = 999` | 1 | 1 | Number `0` |
| `SELECT COUNT(*) FROM products WHERE active = TRUE` | 1 | 1 | Number `2` |
| `SELECT SUM(price) FROM products WHERE id = 999` | 1 | 1 | SQL `NULL` |
| `SELECT COUNT(*) FROM products GROUP BY active` | 2 | 1 | Two groups: active and inactive |

All queries above are valid PostgreSQL SQL against the stated schema.

### 5.1. Not Finding a Row Is Completely Different from Finding NULL

The following two cases can look identical in Java if not distinguished:

```sql
-- No product with id 999: 0 rows.
SELECT description FROM products WHERE id = 999;

-- Product id 10 exists, but description is NULL: 1 row, 1 NULL column.
SELECT description FROM products WHERE id = 10;
```

For `jdbcTemplate.queryForObject(sql, String.class, id)`, the first case throws `EmptyResultDataAccessException`; the second returns `null`. Therefore, do not assume "receiving null" always means the product does not exist.

If business logic needs to represent both states, query **both ID and description** using a `RowMapper` creating an object, e.g., `ProductDescription(long id, String description)`; then `Optional<ProductDescription>` expresses presence/absence of the row, while the `description` field can be null when the row exists.

### 5.2. COUNT(*) Differs from Selecting a Record

```sql
SELECT COUNT(*) FROM products WHERE id = 999;
```

`COUNT(*)` without `GROUP BY` normally returns **one row, one column** containing `0` even when no records match. Thus:

```java
Long count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM products WHERE id = ?",
        Long.class, 999L
);
// count == 0L; does not throw EmptyResultDataAccessException.
```

In PostgreSQL, `COUNT(*)` returns `BIGINT`, so `Long.class` is usually the safe choice. If the application needs `int`, consider overflow risks when casting `long` down to `int`; do not assume the table will stay small forever.

Conversely, an aggregate query with `GROUP BY` can return **zero or many rows**. With the sample data, `SELECT COUNT(*) FROM products GROUP BY active` returns two rows, so it does not match `queryForObject(..., Long.class)`. If you need an overall total, omit `GROUP BY` or use an appropriate aggregate query.

### 5.3. SUM, AVG, MIN, MAX Can Return NULL

An aggregate row does not necessarily carry a non-null value:

```sql
SELECT SUM(price) FROM products WHERE id = 999;
```

By SQL semantics, `SUM` with no input values returns `NULL` (unlike `COUNT`, which returns 0). If you want to default to 0 per business rules:

```sql
SELECT COALESCE(SUM(price), 0) FROM products WHERE id = 999;
```

For currency, use `BigDecimal` for `NUMERIC/DECIMAL`; do not convert to `double` and risk uncontrolled rounding.

## 6. Complete Example: Spring Boot + JDBC + Java 17+

This is a minimal Spring Boot 3.3.x / Spring Framework 6.1.x application. Java code resides in package `demo.singlequery`. It requires a running PostgreSQL instance and datasource environment variables; the example is **not** a plain Java program runnable via `javac` alone without Spring/JDBC dependencies.

### 6.1. Gradle Dependencies

In a Gradle Spring Boot project with the Spring Boot plugin, dependency management, and Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dependencies use the Spring Boot BOM to select compatible versions. `spring-boot-starter-jdbc` provides `JdbcTemplate` and `DataSource` integration; the PostgreSQL driver provides real connectivity, and Flyway creates deterministic test data.

### 6.2. Migration and Seed

File `src/main/resources/db/migration/V1__create_products.sql`:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    description VARCHAR(250),
    active BOOLEAN NOT NULL
);
```

File `src/main/resources/db/migration/V2__seed_products.sql`:

```sql
INSERT INTO products (id, sku, name, price, description, active)
VALUES
    (10, 'BOOK-JAVA', 'Java Fundamentals', 125000.00, NULL, TRUE),
    (20, 'BOOK-SPRING', 'Spring JDBC', 199000.00, 'Hands-on', TRUE),
    (30, 'BOOK-ADV', 'Java Fundamentals', 155000.00, NULL, FALSE);
```

In a production application, sample seed data should usually reside separately for test environments; this lesson places it in migrations so learners can reproduce the example on a fresh database. Do not run a migration creating an existing table against a schema holding real data.

### 6.3. A Record Representing a Product Row

File `src/main/java/demo/singlequery/Product.java`:

```java
package demo.singlequery;

import java.math.BigDecimal;

public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price,
        String description,
        boolean active
) {}
```

`description` can be Java `null` because the SQL column allows NULL. `id` and `active` are safe to map to primitives in this schema because of `PRIMARY KEY` and `NOT NULL`. If a column is nullable and you use `rs.getLong(...)`, JDBC can return a default `0` for SQL NULL; you must check `rs.wasNull()` if you need to distinguish them. For nullable numeric columns, use `rs.getObject("column", Long.class)` or a suitable boxed type when supported by the driver.

### 6.4. Repository Choosing APIs Based on Query Semantics

File `src/main/java/demo/singlequery/ProductJdbcRepository.java`:

```java
package demo.singlequery;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    private static final RowMapper<Product> PRODUCT_ROW =
            (rs, rowNum) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("name"),
                    rs.getBigDecimal("price"),
                    rs.getString("description"),
                    rs.getBoolean("active")
            );

    private final JdbcTemplate jdbc;

    public ProductJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Contract: must have exactly 1 row; id is PRIMARY KEY.
    public Product requireById(long id) {
        return jdbc.queryForObject(
                """
                SELECT id, sku, name, price, description, active
                FROM products
                WHERE id = ?
                """,
                PRODUCT_ROW,
                id
        );
    }

    // Contract: not found is normal; multiple rows is an error.
    public Optional<Product> findById(long id) {
        List<Product> rows = jdbc.query(
                """
                SELECT id, sku, name, price, description, active
                FROM products
                WHERE id = ?
                """,
                PRODUCT_ROW,
                id
        );
        return DataAccessUtils.optionalResult(rows);
    }

    // Contract: exactly 1 row x 1 column and name NOT NULL.
    public String requireNameBySku(String sku) {
        return jdbc.queryForObject(
                "SELECT name FROM products WHERE sku = ?",
                String.class,
                sku
        );
    }

    // Contract: row may exist with description = SQL NULL.
    // Return value may be Java null; 0 rows still throws an exception.
    public String descriptionById(long id) {
        return jdbc.queryForObject(
                "SELECT description FROM products WHERE id = ?",
                String.class,
                id
        );
    }

    // COUNT(*) without GROUP BY: always 1 row x 1 column, non-NULL value.
    public long countActive() {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products WHERE active = ?",
                Long.class,
                true
        );
        return Objects.requireNonNull(count, "COUNT(*) unexpectedly NULL");
    }

    public long countByName(String name) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products WHERE name = ?",
                Long.class,
                name
        );
        return Objects.requireNonNull(count, "COUNT(*) unexpectedly NULL");
    }
}
```

All input parameters are bound via `?` and arguments. Mapper queries explicitly select the required columns; avoid `SELECT *`, which can unintentionally alter mapping when migrations add or remove columns.

`findById(...)` uses `DataAccessUtils.optionalResult(Collection)` (Spring Framework 6.1+): an empty list becomes `Optional.empty()`, a single-element list becomes `Optional.of(...)`, and two or more elements throw `IncorrectResultSizeDataAccessException`. The `RowMapper` in this example never returns null, so a valid row always produces a `Product`.

Because `sku` is `UNIQUE` in the database, `requireNameBySku(...)` has a sound basis for expecting at most one row. If called with a non-existent SKU, the method still throws `EmptyResultDataAccessException`; the caller must decide whether "not found" is an error or a valid case.

### 6.5. Runnable Program and Deterministic Stdout

File `src/main/java/demo/singlequery/SingleQueryApplication.java`:

```java
package demo.singlequery;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SingleQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SingleQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner showExamples(ProductJdbcRepository repository) {
        return args -> {
            System.out.println("active=" + repository.countActive());
            System.out.println("sku(10)=" + repository.requireById(10).sku());
            System.out.println(
                    "present(999)=" + repository.findById(999).isPresent()
            );
            System.out.println(
                    "description(10) is null="
                    + (repository.descriptionById(10) == null)
            );
        };
    }
}
```

Configuration file `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Assuming PostgreSQL is running at `localhost:5432`, a fresh learning database named `jdbc_single_query`, and a user/password created in your environment. In a terminal supporting shell environment variables, provide the JDBC URL and credentials and run:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `$env:DB_JDBC_URL = "jdbc:postgresql://localhost:5432/jdbc_single_query"`, similarly for `DB_USER` and `DB_PASSWORD`, then `.\gradlew.bat bootRun`. Never put passwords in source code or commit files containing secrets.

After Flyway runs V1/V2 on the fresh database, in addition to Spring Boot startup logs, the program prints exactly four lines:

```text
active=2
sku(10)=BOOK-JAVA
present(999)=false
description(10) is null=true
```

Meaning of the four lines: `COUNT(*)` returns 2, the PK query for id=10 returns an object, the optional query for id=999 returns empty, and id=10 exists with a NULL description column.

## 7. When Not to Use queryForObject?

### 7.1. Result May Be Missing: Use Optional or Return a List

If the `findById` API needs to report "not found" without treating it as an exception, there are two options:

**Option A: query + check row count with DataAccessUtils**

```java
List<Product> rows = jdbcTemplate.query(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE id = ?
        """,
        productRowMapper,
        id
);
Optional<Product> product = DataAccessUtils.optionalResult(rows);
```

`productRowMapper` is a `RowMapper<Product>` defined in the repository. This option enforces a **0..1 row** contract while still throwing an error if >1 row actually exists, guarding against buggy conditions or row-multiplying joins.

**Option B: queryForObject then catch exactly one exception**

```java
try {
    return Optional.ofNullable(
            jdbcTemplate.queryForObject(sql, productRowMapper, id)
    );
} catch (EmptyResultDataAccessException notFound) {
    return Optional.empty();
}
```

This is a fragment inside a method returning `Optional<Product>`, with `sql` and `productRowMapper` already defined. Option B is valid when handling zero rows, but you must not catch generic `DataAccessException` and treat every error as "not found": DB errors, invalid SQL, or multiple rows must still surface.

In Spring 6.1+ code, Option A is often clearer when zero rows is a normal scenario. If you are using `JdbcClient`, you can use `optional()` directly (see section 10).

### 7.2. Need Multiple Objects: Use query Instead of queryForObject

```java
List<Product> products = jdbcTemplate.query(
        """
        SELECT id, sku, name, price, description, active
        FROM products
        WHERE active = ?
        ORDER BY id
        """,
        productRowMapper,
        true
);
```

The result can have 0, 1, or many elements. `query(...)` does not enforce exactly one row; `RowMapper` converts each row into an object. If the business need truly calls for a list, using `query(...)` is the right approach rather than catching `IncorrectResultSizeDataAccessException` and treating it as a list.

### 7.3. Need One Value per Row: Use queryForList

```java
List<String> skus = jdbcTemplate.queryForList(
        "SELECT sku FROM products WHERE active = ? ORDER BY id",
        String.class,
        true
);
```

In the sample data, `skus` contains `BOOK-JAVA` and `BOOK-SPRING` ordered by `id`. Each row of the SQL has only one column, but **the total number of rows can be many**. `queryForList(sql, Class<T>, ...)` has a different contract from `queryForObject(...)`.

### 7.4. queryForMap Also Requires Exactly One Row

```java
Map<String, Object> row = jdbcTemplate.queryForMap(
        "SELECT sku, name FROM products WHERE id = ?",
        10L
);
```

This returns **one map from one multi-column row**. Do not confuse it with `queryForList` returning multiple rows; if the SQL returns 0 or multiple rows, `queryForMap(...)` still reports a cardinality error. Returning a `Map` directly from a repository to a public HTTP API can expose column names or sensitive values; explicit DTO/domain types are generally safer.

## 8. Where Does Uniqueness Really Live?

`queryForObject(...)` checks **the query result at runtime**; it does not create a unique constraint in the database. It neither prevents inserting multiple rows with the same business key nor makes a `WHERE` clause unique.

Example with the sample data:

```sql
SELECT id, sku, name, price, description, active
FROM products
WHERE name = 'Java Fundamentals';
```

There are two rows: id=10 and id=30. Calling `queryForObject(sql, productRowMapper, "Java Fundamentals")` will throw `IncorrectResultSizeDataAccessException` because `name` is not unique. Do not fix this with:

```sql
SELECT id, sku, name, price, description, active
FROM products
WHERE name = 'Java Fundamentals'
LIMIT 1;
```

`LIMIT 1` merely **hides** the fact that two rows exist. Without `ORDER BY`, the DB makes no guarantee about which record is chosen; even with `ORDER BY`, picking the first record is only valid when the business genuinely wants "one prioritized record", not "exactly one record".

When business rules require SKU to be unique, use `UNIQUE (sku)` in the schema. If `name` truly must be unique, add the corresponding constraint; if duplicate names are allowed, the repository must return a list or add criteria to select a specific record as required.

### 8.1. JOIN Can Multiply Rows Even When Querying by PK

```sql
SELECT p.id, p.name, t.tag_name
FROM products p
JOIN product_tags t ON t.product_id = p.id
WHERE p.id = 10;
```

This is a hypothetical SQL example assuming a `product_tags` table with a one-to-many relationship. A product with three tags will produce **three result rows**. Even though `products.id` is unique, the JOIN does not preserve a single row.

If you only need the product, query the product table alone; if you need the list of tags, map the one-to-many structure with `query(...)` and appropriate grouping/`ResultSetExtractor`, or design a proper aggregate SQL query. Do not blindly sprinkle `DISTINCT` into every SQL query assuming it solves the issue: `DISTINCT` considers the combination of all selected columns, and three distinct tags still produce three rows.

### 8.2. "Fetching the Latest Record" Is a Different Problem

If the requirement is "a customer's latest order", a 0..1 result can use:

```sql
SELECT id, customer_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

In this situation, `ORDER BY ... LIMIT 1` is **intentional**: selecting the prioritized record, not assuming the database only has one order. If there are no orders, `queryForObject` still throws `EmptyResultDataAccessException`; an optional API remains appropriate.

Distinguish three requirements before writing SQL: **unique by constraint**, **may be missing but at most one**, and **pick one representative by ordering**.

## 9. Handling Exceptions Semantically

### 9.1. EmptyResultDataAccessException

Occurs when a method **requires exactly one row** but the SQL returns 0 rows. This is typically the "not found" situation when querying by ID or business key.

```java
try {
    Product product = repository.requireById(id);
    return product;
} catch (EmptyResultDataAccessException absent) {
    throw new ProductNotFoundException(id);
}
```

This example is a fragment in an application service, and `ProductNotFoundException` is a business exception to define. If not found is completely normal, returning `Optional<Product>` from the repository is clearer and avoids control flow via exceptions.

Do not catch `IncorrectResultSizeDataAccessException` first and assume every case means "not found": that class also includes the **multiple rows** case.

### 9.2. IncorrectResultSizeDataAccessException

`queryForObject(...)` overloads throw this class when the row count is wrong; the zero-row case is specifically the subclass `EmptyResultDataAccessException`. When there are multiple rows while the application expects exactly one, the cause may be:

- SQL missing a `WHERE` condition.
- Filtering on an attribute without a UNIQUE constraint.
- A JOIN multiplying row count.
- Bad data written before a migration added the constraint.
- Modeling error: the use case genuinely has multiple results, yet a single-result method was called.

This is usually an **error in data assumptions or query logic**, and you should not arbitrarily return one row to the UI. Inspect the SQL, schema, and business requirements. For diagnosis, the exception exposes expected/actual sizes per the API contract.

### 9.3. IncorrectResultSetColumnCountException

Occurs in the single-column mapping path when the SQL column count is wrong. For example:

```java
// One-row SQL but two columns => wrong shape for String.class.
jdbcTemplate.queryForObject(
        "SELECT name, price FROM products WHERE id = ?",
        String.class,
        10L
);
```

This is a **query/mapping structural error**. The fix is to select only `name` if you need a `String`, or use `RowMapper<ProductNameAndPrice>` if you need both fields. Do not hide the error by discarding the second column or coercing the entire map into `String`.

### 9.4. SQL NULL and Invalid Type Conversions

`SELECT description ... WHERE id=10` has one row containing NULL; Spring may return Java `null`. If your code writes:

```java
int length = jdbcTemplate.queryForObject(
        "SELECT description FROM products WHERE id = ?",
        String.class,
        10L
).length();
```

it will cause a `NullPointerException` due to the SQL NULL value. The solution is to use a nullable Java type, `Optional` as semantically appropriate, or a query returning an object carrying both row and column info; if business rules forbid NULL, place `NOT NULL` in the DB and clean up existing data.

If you request `Integer.class` for an unconvertible text column, you may encounter a conversion error or another `DataAccessException`. Choose a Java type matching the JDBC type and avoid arbitrary casts. `COUNT(*)` in PostgreSQL fits `Long.class` better than assuming `Integer.class`.

## 10. Related APIs in Spring 6.1+

### 10.1. NamedParameterJdbcTemplate

When there are many parameters, named parameters can improve clarity:

```java
String sql = """
        SELECT name
        FROM products
        WHERE sku = :sku
        """;

String name = namedJdbc.queryForObject(
        sql,
        java.util.Map.of("sku", "BOOK-JAVA"),
        String.class
);
```

`namedJdbc` is a configured `NamedParameterJdbcTemplate`. The **one row, one column** contract remains unchanged; named parameters only change how values are bound. For mapping a multi-column object, use the overload accepting `RowMapper<T>`.

### 10.2. JdbcClient: Expressive optional and single

Spring Framework 6.1 introduced `org.springframework.jdbc.core.simple.JdbcClient`, a fluent facade over `JdbcTemplate`/`NamedParameterJdbcTemplate`:

```java
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(jdbcTemplate);

Optional<String> maybeName = client.sql(
        "SELECT name FROM products WHERE id = :id"
    )
    .param("id", 999L)
    .query(String.class)
    .optional();

String requiredName = client.sql(
        "SELECT name FROM products WHERE id = :id"
    )
    .param("id", 10L)
    .query(String.class)
    .single();
```

This is a fragment in a scope where `jdbcTemplate` is available. `optional()` expresses **0..1 results** and errors when >1; `single()` requires exactly one non-null result. `query(String.class)` still represents single-column mapping, while multi-column objects can use `query(RowMapper<T>)`.

The shorter syntax does not alter the query's invariants: you still need valid SQL, unique constraints when business requires uniqueness, and the right column count for the result type.

### 10.3. DataAccessUtils: singleResult, optionalResult, requiredSingleResult

When you already have a `List<T>` from `query(...)`, Spring provides utilities:

| Method | Zero elements | Exactly one element | Multiple elements |
| --- | --- | --- | --- |
| `DataAccessUtils.singleResult(results)` | Returns `null` | Returns element | Throws `IncorrectResultSizeDataAccessException` |
| `DataAccessUtils.optionalResult(results)` | Returns `Optional.empty()` | Returns `Optional` containing element if non-null | Throws `IncorrectResultSizeDataAccessException` |
| `DataAccessUtils.requiredSingleResult(results)` | Throws `EmptyResultDataAccessException` | Returns element | Throws `IncorrectResultSizeDataAccessException` |

Do not confuse `uniqueResult(...)` with checking for **one row**. That method checks the uniqueness of **objects in a collection** according to the utility's own rules; it is not a reliable way to verify a SQL query actually returned only one row. For cardinality requirements, prefer `singleResult`, `optionalResult`, or `requiredSingleResult`.

### 10.4. BeanPropertyRowMapper and Custom RowMapper

`BeanPropertyRowMapper` maps columns to JavaBean properties by naming conventions; `DataClassRowMapper` supports data classes/records in suitable cases. However, when you need explicit control over columns, nullable values, conversions, domain invariants, or mapping optimization, an explicit `RowMapper` like in the examples is usually clearest.

No mapper choice turns two rows into a valid single row for `queryForObject`. The mapper is responsible for **one row → one Java object**, while `JdbcTemplate` is responsible for enforcing cardinality for the chosen overload.

## 11. Testing Row Count and Column Count with JUnit 5

The tests below require the Spring Boot project from section 6, a test PostgreSQL database with Flyway V1/V2, and a datasource pointing to that database. Do not run directly against production. File `src/test/java/demo/singlequery/ProductJdbcRepositoryTest.java`:

```java
package demo.singlequery;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.IncorrectResultSetColumnCountException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ProductJdbcRepositoryTest {
    @Autowired
    ProductJdbcRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void exactlyOneRowWithMultipleColumnsMapsToProduct() {
        Product product = repository.requireById(10L);
        assertEquals(10L, product.id());
        assertEquals("BOOK-JAVA", product.sku());
        assertEquals("Java Fundamentals", product.name());
    }

    @Test
    void zeroRowsDistinguishesRequiredAndOptional() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> repository.requireById(999L)
        );
        assertEquals(Optional.empty(), repository.findById(999L));
    }

    @Test
    void scalarCountAndSqlNullHaveDifferentMeanings() {
        assertEquals(2L, repository.countActive());
        assertEquals(0L, repository.countByName("Does Not Exist"));
        assertNull(repository.descriptionById(10L));
        assertEquals("Hands-on", repository.descriptionById(20L));
    }

    @Test
    void twoColumnsCannotBeMappedAsOneString() {
        assertThrows(
                IncorrectResultSetColumnCountException.class,
                () -> jdbc.queryForObject(
                        "SELECT name, price FROM products WHERE id = ?",
                        String.class,
                        10L
                )
        );
    }

    @Test
    void twoRowsViolateQueryForObjectCardinality() {
        assertThrows(
                IncorrectResultSizeDataAccessException.class,
                () -> jdbc.queryForObject(
                        "SELECT id, name FROM products WHERE name = ?",
                        (rs, rowNum) -> rs.getLong("id"),
                        "Java Fundamentals"
                )
        );
    }

    @Test
    void rowMapperMayReadManyColumns() {
        String name = jdbc.queryForObject(
                "SELECT id, name FROM products WHERE id = ?",
                (rs, rowNum) -> rs.getString("name"),
                10L
        );
        assertEquals("Java Fundamentals", name);
    }
}
```

This is an integration test using **real PostgreSQL**, because the Spring context obtains its datasource from the environment and runs migrations. You can replace the test datasource with Testcontainers PostgreSQL in CI pipelines for reproducibility. Running the tests requires configuring the driver and DB as described in section 6.

Command:

```bash
./gradlew test
```

On Windows, use `gradlew.bat test`. If the migrations, datasource, and example match, all six tests should succeed; if any fail, inspect the actual assertion and exception. Never assume "tests pass" without running them in the target environment.

**Why is the fifth test important?** The SQL has two columns while the `RowMapper` reads only the `id` column, which is valid for column mapping. However, the SQL matches two rows, so `queryForObject` still throws `IncorrectResultSizeDataAccessException`. The sixth test verifies the opposite: one row with two columns can still be mapped to a String with a `RowMapper` intentionally selecting `name`, though in practice you should usually simplify the SQL to one column when the ID is not needed.

## 12. Choosing an API as a Business Contract

Before choosing `queryForObject`, answer these questions:

1. **What if no row is found?** If that is an error, use a required query and translate it into an appropriate business error. If that is a normal outcome, prefer `Optional<T>`.
2. **What if two rows are found?** If disallowed, preserve the cardinality error for investigation, backed by a UNIQUE constraint and tests. If multiple rows are valid, return `List<T>`.
3. **Is the output a single scalar or an object with multiple properties?** One scalar uses `Class<T>`/`SingleColumnRowMapper`; a multi-column object uses `RowMapper<T>`.
4. **Does the SQL truly guarantee at most one row?** Primary keys/UNIQUE guarantee this on the base table, but JOIN/GROUP BY can alter cardinality.
5. **Can the column be NULL?** Use a boxed/reference type, nullable DTO, or an intentional default value; avoid unboxing null.
6. **Is the result ordered?** When picking the "first" row among many, you must have `ORDER BY` and a business rule; do not confuse this with a uniqueness check.

A quick decision table:

| Requirement | Method | Reason |
| --- | --- | --- |
| Get total product count | `queryForObject(..., Long.class)` | `COUNT(*)` is one row, one column |
| Get name from required SKU | `queryForObject(..., String.class, sku)` | One scalar, SKU is unique |
| Get Product by required ID | `queryForObject(..., productMapper, id)` | One object, multiple columns, ID is PK |
| Find Product that may not exist | `query(..., productMapper, id)` + `optionalResult` | 0..1, absence is normal |
| List products by group | `query(..., productMapper, groupId)` | 0..N objects |
| List of SKUs in a group | `queryForList(..., String.class, groupId)` | N rows, each row one column |
| Pick latest order | `ORDER BY ... LIMIT 1`, return optional | Pick by ordering, do not assume unique |

Do not decide based solely on the name `queryForObject`. Write the cardinality contract clearly in your repository methods and test it.

## 13. Common Mistakes When Learning JDBC

| Mistake | Cause | Fix |
| --- | --- | --- |
| `queryForObject("SELECT * ...", String.class)` | One row has multiple columns | Select exactly one column or use RowMapper |
| `queryForObject(..., RowMapper)` with non-unique WHERE | Multiple rows exist | Add conditions/constraints or return a list |
| Treating `NULL` as not found | Confusing column value with row count | Separate 0 rows and 1 NULL row |
| Treating `COUNT(*) = 0` as a zero-row exception | COUNT without GROUP BY still yields one row | Read value 0 as Long |
| Using `Integer.class` for every `COUNT(*)` | COUNT can be BIGINT and exceed int | Use Long, cast with overflow checks |
| `LIMIT 1` to ignore duplicate data | Hides cardinality bugs; can be non-deterministic | Define uniqueness properly; only use LIMIT when business wants to pick one row |
| Returning null when catching any `DataAccessException` | Hides SQL/connection/schema errors | Only handle zero rows explicitly if allowed |
| Ignoring one-to-many JOINs | Joins can multiply PK rows | Redesign mapping/aggregates or return a list |
| Using primitives for nullable columns | JDBC getter can return defaults or unbox NPE | Boxed types, `wasNull()`, nullable domain fields |
| Not binding parameters | Concatenating user data into SQL, injection risk | Use `?` or named parameters |
| `RowMapper` casually returning null | Row exists yet object is null | Mapper returns valid object, explicit exceptions |
| Catching multiple rows and taking the first element | Masks bad data or broken queries | Keep the error, check DB constraints |
| Confusing `queryForMap` with a list of maps | `queryForMap` also requires one row | Use `queryForList`/`query` when multiple rows are needed |

## 14. Practice Exercises

**Exercise 1 — Predict the outcome.** Based on the `products` table in section 5, for each SQL statement below determine the row/column count and the result or exception when calling `queryForObject(sql, String.class)`:

```sql
SELECT name FROM products WHERE id = 20;
SELECT name FROM products WHERE id = 999;
SELECT description FROM products WHERE id = 10;
SELECT name, price FROM products WHERE id = 10;
SELECT name FROM products WHERE name = 'Java Fundamentals';
```

**Exercise 2 — Choose the overload.** Write a `Product requireBySku(String sku)` method; use `RowMapper<Product>` since multiple properties are needed. Then write `Optional<Product> findBySku(String sku)` without turning zero rows into an infrastructure error.

**Exercise 3 — Aggregates.** Write two count queries: total active rows, and rows with `name = 'Does Not Exist'`. Explain why both return one row yet can return 2 and 0. Check what happens if you add `GROUP BY active`.

**Exercise 4 — Spot the design violation.** A repository uses `SELECT id FROM products WHERE name = ? LIMIT 1` to "guarantee only one product has that name". Point out the modeling flaw and propose the right contract if duplicate names are allowed vs. if names must be unique.

**Exercise 5 — Test shape errors.** Add a test for `queryForObject("SELECT sku, name FROM products WHERE id = ?", String.class, 20L)` and verify `IncorrectResultSetColumnCountException`. Try the same SQL using a `RowMapper` creating a record containing `sku` and `name`.

**Exercise 1 answer key:** in order, (1) `Spring JDBC`; (2) `EmptyResultDataAccessException`; (3) Java `null`; (4) `IncorrectResultSetColumnCountException`; (5) `IncorrectResultSizeDataAccessException`. These errors cannot be fixed by catching everything and always returning an empty string.

## 15. End-of-Lesson Checklist

- Does the SQL return **the exact number of rows** advertised by the repository method?
- For `Class<T>`, does the SQL return **exactly one column** on the mapped row?
- For multi-column objects, did you use `RowMapper<T>` instead of trying to map via `String.class`?
- Is "not found" represented via `Optional.empty()` or an intentional business exception?
- Did you distinguish zero rows from SQL NULL and `COUNT(*) = 0`?
- If the query requires uniqueness, do DB PK/UNIQUE constraints actually enforce it? Could JOIN/GROUP BY change the row count?
- If picking the first row of a multi-row set, is there an explicit `ORDER BY` rule?
- Do `BigDecimal`, `Long`, nullable types, and JDBC mappings match the schema?
- Do tests cover 0, 1, >1 rows; 1, >1 columns; and NULL?

**Key point to remember:** `queryForObject` does not mean "grab any single row". It is an **assertion** about the result. With `Class<T>`, the assertion is **exactly one row and one column**; with `RowMapper<T>`, the assertion is **exactly one row**, and the mapper may read multiple columns to create an object. If the real need is 0..1, use optional; if 0..N, use a list. Design the right contract first and let Spring raise errors when data violates it.

## References

- Spring Framework — JDBC Core, Querying section: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework 6.1 — JdbcTemplate.queryForObject Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework 6.1 — DataAccessUtils and optionalResult: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- Spring Framework 6.1 — JdbcClient fluent API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.1 — JdbcClient.MappedQuerySpec: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.1 — IncorrectResultSetColumnCountException: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/IncorrectResultSetColumnCountException.html
