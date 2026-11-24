# Controlling Sort Column Lists with Valid Selections

When building search/pagination APIs with Spring `JdbcTemplate`, users may be allowed to sort by **name**, **price**, **creation date**, and **ascending/descending** direction. However, column names and keywords in `ORDER BY` are **SQL structure**, not data values that can be bound directly via JDBC parameters.

Foundational rule:

> **Never concatenate raw column names or sort directions received from a client into SQL.** Validate selections against an **allow-list** (permitted keys) and map each key to a fixed SQL expression owned by the application. Still use `PreparedStatement`/`JdbcTemplate` to bind all data values in `WHERE` and pagination.

For example, an API receives `sort=price&direction=DESC`. The backend should translate `price` into a validated selection, map it to `p.price`, and translate the direction into the fixed keyword `DESC`. The final SQL query may look like:

```sql
SELECT p.id, p.name, p.price
FROM products p
WHERE p.active = ? AND p.price >= ?
ORDER BY p.price DESC, p.id ASC
LIMIT ? OFFSET ?;
```

Only the `p.price` and `DESC` fragments are assembled into the structure because they come from **fixed source code**; the values `active`, `minimumPrice`, `pageSize`, and `offset` remain bound parameters.

This lesson progresses from JDBC mechanics, input security, API design, Java 17 enums, a runnable Spring Boot/H2 application, to multi-column sorting, stable pagination, and testing.

## 1. Distinguishing Data Values from SQL Structure

`PreparedStatement` accepts SQL with an already-defined structure and binds values for `?` markers:

```java
String sql = """
    SELECT id, name, price
    FROM products
    WHERE price >= ? AND active = ?
    """;
List<String> names = jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    minPrice, true
);
```

This is a snippet inside a class that already has `JdbcTemplate jdbc` and `BigDecimal minPrice`. Both values are treated by the driver as **data**, even if a string value contains quotes or SQL syntax.

Unlike `WHERE`, the following are **identifiers/keywords/expressions**:

- Table name `products`, column name `price`, alias `p`.
- Structure `ORDER BY p.price`.
- Sort direction `ASC` or `DESC`.
- Comma-separated list of sort criteria.
- Expressions like `LOWER(p.name)`, `CASE WHEN ...`, `NULLS LAST`, and collation specifications.

They **cannot be replaced by a bound string**. The following example is semantically wrong:

```sql
-- Does not turn "price" into a column name.
SELECT id, name, price
FROM products
ORDER BY ?;
```

Binding `"price"` via `?` does not make the database interpret it as the `price` column: depending on the DBMS, it may be treated as a constant value or raise an error. Similarly, do not use `ORDER BY p.price ?` with `"DESC"` as a parameter. A bind position represents a **value**, and cannot insert a keyword into SQL grammar.

| Input | Nature | Safe Approach |
| --- | --- | --- |
| `minimumPrice` in `WHERE price >= ?` | Data value | Validate type/bounds; bind with `?`. |
| `tenantId` in `WHERE tenant_id = ?` | Data value | Obtain from trusted authorization context; bind. |
| `keyword` in `LIKE ?` | Data value | Bind pattern; escape wildcards if literal search is needed. |
| `size` and `offset` | Numeric values | Validate limits; bind when DBMS supports it. |
| `sort=name` | Column selection | Map `name` to fixed expression `p.name`. |
| `direction=desc` | Keyword selection | Enum/boolean produces exact `DESC`. |
| `sort=name,-price` | Structural list | Parse each part, validate all, bound item count. |
| `NULLS LAST`, `LOWER(...)` | Expression/keyword | Allow only reviewed fixed fragments. |

## 2. Vulnerability When Concatenating Raw Sort Input

**Anti-pattern:**

```java
// WRONG: user can alter the SQL structure.
String sql = "SELECT id, name FROM products ORDER BY "
           + sortColumn + " " + direction;
return jdbc.query(sql, (rs, rowNum) -> rs.getString("name"));
```

If a client supplies `sortColumn="price DESC; DROP TABLE products; --"`, the input is already inside the SQL text before JDBC receives the query. Whether multiple statements can execute depends on the driver/DBMS, yet this way of building SQL already creates injection risk or allows unintended sort expressions. For instance, a client could invoke an expensive DB function, sort on a disallowed column, or trigger query errors.

**Still wrong even with binding in WHERE:**

```java
// minPrice is bound, but sortColumn is uncontrolled.
String sql = "SELECT id, name FROM products "
           + "WHERE price >= ? ORDER BY " + sortColumn;
return jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    minPrice
);
```

Using `PreparedStatement` or `NamedParameterJdbcTemplate` does not protect **parts of the SQL statement concatenated from raw input**. Checking via regex that a string only contains letters is also insufficient: `internal_cost` or `secret_token` may be syntactically valid column names yet forbidden as an API feature.

### 2.1. Escaping and Quoting Do Not Replace an Allow-List

Sometimes people suggest "adding quotes around column names," "escaping single quotes," or "stripping semicolons." Those measures do not govern **which columns** may be selected and can depend on dialect, collation, or driver configuration. Identifier quoting helps the parser recognize an identifier name; it **does not ensure that the name is allowed by business rules**.

For example, a validly quoted `"secret_token"` is still not a sort key an API should expose. Thus, what must be verified is **an exact choice from a predefined program list**, not a string that merely looks safe.

## 3. Contract Design: API Keys Differ from Physical Columns

Suppose a product screen has three sort keys:

| Client Key | UI Label | SQL Fragment from Code |
| --- | --- | --- |
| `name` | Product Name | `p.name` |
| `price` | Price | `p.price` |
| `createdAt` | Created Date | `p.created_at` |

Clients **must not** send `p.name` or `LOWER(p.name)` when the contract publishes the key `name`. Separating them brings major benefits:

1. UI/API is not coupled directly to the schema, snake_case/camelCase naming, or SQL aliases.
2. When a migration renames a column, only the internal mapping changes.
3. The endpoint can restrict allowed columns instead of automatically granting sort access to every column in the table.
4. Special expressions (e.g., `LOWER(p.name)`) are reviewed and tested before entering the mapping.
5. Code can attach index policies, resource limits, and permissions per sort key.

**Input handling:**
- Missing `sort` parameter: use an explicit server-chosen default.
- `sort` present but not in the list: reject, typically HTTP 400 in an API.
- Missing `direction`: use the documented default direction.
- Direction outside `ASC`/`DESC`: reject, never concatenate strange strings.
- If you want to allow `" desc "`, normalize intentionally before comparing; do not accept arbitrary similar text.

Rejecting unknown selections instead of silently slipping them into SQL helps detect client bugs and reduces attack surface.

## 4. Java 17: Enums for Column Names and Sort Direction

Below is a **standalone, Java 17+-compilable** `SortPolicy.java` class; it only builds the `ORDER BY` clause for a query using alias `p`.

```java
import java.util.Locale;

public final class SortPolicy {
    private SortPolicy() {}

    public enum Field {
        NAME("name", "p.name"),
        PRICE("price", "p.price"),
        CREATED_AT("createdAt", "p.created_at");

        private final String key;
        private final String expression;

        Field(String key, String expression) {
            this.key = key;
            this.expression = expression;
        }

        static Field fromClient(String raw) {
            if (raw == null) {
                return CREATED_AT; // Explicit default.
            }
            for (Field field : values()) {
                if (field.key.equals(raw)) {
                    return field;
                }
            }
            throw new IllegalArgumentException("Unsupported sort field");
        }
    }

    public enum Direction {
        ASC, DESC;

        static Direction fromClient(String raw) {
            if (raw == null) {
                return DESC;
            }
            String normalized = raw.strip().toUpperCase(Locale.ROOT);
            return switch (normalized) {
                case "ASC" -> ASC;
                case "DESC" -> DESC;
                default -> throw new IllegalArgumentException(
                    "Unsupported direction");
            };
        }
    }

    public static String orderBy(String rawField, String rawDirection) {
        Field field = Field.fromClient(rawField);
        Direction direction = Direction.fromClient(rawDirection);
        return "ORDER BY " + field.expression
             + " " + direction.name() + ", p.id ASC";
    }

    public static void main(String[] args) {
        System.out.println(orderBy("price", "desc"));
        System.out.println(orderBy(null, null));
        try {
            orderBy("price DESC; DROP TABLE products", "asc");
        } catch (IllegalArgumentException expected) {
            System.out.println("rejected=true");
        }
    }
}
```

Run:

```bash
javac SortPolicy.java
java SortPolicy
```

**Stdout:**

```text
ORDER BY p.price DESC, p.id ASC
ORDER BY p.created_at DESC, p.id ASC
rejected=true
```

This snippet never takes `rawField` or `rawDirection` to insert directly into SQL. They **only select an enum**, while the text used in SQL comes from enum constants.

**One note:** `Field.fromClient(null)` applies the default; empty strings or unknown keys still fail. `Direction.fromClient` uses `Locale.ROOT` to prevent server locale-dependent uppercasing issues. Do not allow users to send `"ASC NULLS LAST"` directly because it is not one of the two enum values.

### 4.1. Invariant to Maintain Across the Application

Once parsed into `Field` and `Direction`, lower layers should accept **those validated types** rather than reverting to raw request strings. If adding mappings via `Map<String,String>`, the map must be immutable, constructed in source code, and never accept client-supplied expressions.

Prevent others from accidentally extending the API carelessly:

```java
// WRONG: "fallback" puts unapproved input back into SQL.
String sqlColumn = known.getOrDefault(rawSort, rawSort);
```

A proper fallback either throws an error or uses **a fixed default value** solely for missing input per contract; never pass an unknown input through unchanged.

## 5. Stable Sorting with Pagination

With data containing multiple rows at the same price:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC;
```

If two rows share `price=25.00`, their relative order is not guaranteed. Two separate paginated requests may return overlapping or skipped rows if page boundaries fall on tied sort keys.

When `id` is a unique key, add a tie-breaker:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC, id ASC
LIMIT 20 OFFSET 40;
```

The query now has **deterministic ordering for a given data state**. If data is inserted/deleted/updated between requests, offset pagination can still drift across pages: a tie-breaker stabilizes ordering, not a snapshot. For stricter requirements, consider transaction snapshots or keyset pagination.

### 5.1. Why Do LIMIT/OFFSET Need Separate Controls?

`page` and `size` from the client are **numeric values**, not identifiers. You should:

- Enforce `page >= 0`, `size` within bounds (e.g., `1..100`).
- Compute `offset = page × size` with overflow protection.
- Bind `size`/`offset` using `?` when the dialect supports it, never concatenating raw input.
- Consider page caps, indexes, and load; large offsets still consume DB resources.
- Do not use `JdbcTemplate.setMaxRows` to replace an entire pagination design.

With keyset pagination on `price DESC, id ASC`, the following predicate pattern is one option:

```sql
SELECT p.id, p.name, p.price
FROM products p
WHERE p.active = ?
  AND (p.price < ? OR (p.price = ? AND p.id > ?))
ORDER BY p.price DESC, p.id ASC
LIMIT ?;
```

`lastPrice` appears twice and `lastId` must all be bound. If the user changes sort field/direction, the cursor predicate must change accordingly using an **approved** query pattern, rather than reusing the old keyset formula for every sort option.

## 6. Spring JdbcTemplate: Assembling Trusted Structure, Binding Data

Standard query pattern:

```java
String safeOrderBy = SortPolicy.orderBy(sortKey, direction);
String sql = """
    SELECT p.id, p.name, p.price
    FROM products p
    WHERE p.active = ? AND p.price >= ?
    """ + safeOrderBy + " LIMIT ? OFFSET ?";

List<String> names = jdbc.query(
    sql,
    (rs, rowNum) -> rs.getString("name"),
    true, minimumPrice, pageSize, offset
);
```

This is a **snippet inside a repository that already has `JdbcTemplate jdbc`**. The only part concatenated into SQL is the output of `SortPolicy.orderBy` from fixed enums. The four filter/pagination values flow through `PreparedStatement`.

Wrong approach when switching to `NamedParameterJdbcTemplate`:

```java
// :sort is only a value, it does not become an identifier.
String sql = """
    SELECT p.id, p.name
    FROM products p
    WHERE p.active = :active
    ORDER BY :sort
    """;
```

`:active` is a bound value, yet `:sort` does not create dynamic structure. Named parameters only make naming data arguments convenient; they do not replace allow-lists for column names and SQL keywords.

## 7. Complete Spring Boot + H2 Project

The following Java 17+ example runs on Spring Boot 3.3.x with Spring JDBC and H2. It inserts four rows, two with tied prices, runs two sorts, and rejects a string containing invalid SQL **before calling JDBC**.

### 7.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

### 7.2. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:sort_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

### 7.3. src/main/java/example/ProductSortDemoApplication.java

```java
package example;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class ProductSortDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProductSortDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, ProductRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE products (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    price DECIMAL(10, 2) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    active BOOLEAN NOT NULL
                )
                """);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 1L, "Pen", new BigDecimal("10.00"),
                Timestamp.valueOf("2026-01-01 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 2L, "Notebook", new BigDecimal("25.00"),
                Timestamp.valueOf("2026-01-02 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 3L, "Clip", new BigDecimal("25.00"),
                Timestamp.valueOf("2026-01-03 08:00:00"), true);

            jdbc.update("""
                INSERT INTO products(id, name, price, created_at, active)
                VALUES (?, ?, ?, ?, ?)
                """, 4L, "Ruler", new BigDecimal("8.00"),
                Timestamp.valueOf("2026-01-04 08:00:00"), false);

            BigDecimal minPrice = new BigDecimal("10.00");

            var byPrice = repo.find("price", "DESC", minPrice, 0, 10);
            System.out.println("priceDesc=" + byPrice.stream()
                .map(ProductRepository.ProductRow::name).toList());

            var byName = repo.find("name", "asc", minPrice, 0, 10);
            System.out.println("nameAsc=" + byName.stream()
                .map(ProductRepository.ProductRow::name).toList());

            boolean rejected = false;
            try {
                repo.find(
                    "price DESC; DROP TABLE products",
                    "DESC", minPrice, 0, 10);
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }
            System.out.println("invalidRejected=" + rejected);

            Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM products", Integer.class);
            System.out.println("remaining=" + remaining);
        };
    }
}

@Repository
class ProductRepository {
    private final JdbcTemplate jdbc;

    ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ProductRow(
        long id,
        String name,
        BigDecimal price,
        LocalDateTime createdAt
    ) {}

    private enum SortField {
        NAME("name", "p.name"),
        PRICE("price", "p.price"),
        CREATED_AT("createdAt", "p.created_at");

        private final String key;
        private final String sqlExpression;

        SortField(String key, String sqlExpression) {
            this.key = key;
            this.sqlExpression = sqlExpression;
        }

        static SortField fromClient(String raw) {
            if (raw == null) return NAME;
            for (SortField field : values()) {
                if (field.key.equals(raw)) return field;
            }
            throw new IllegalArgumentException(
                "Unsupported sort field");
        }
    }

    private enum SortDirection {
        ASC, DESC;

        static SortDirection fromClient(String raw) {
            if (raw == null) return ASC;
            String value = raw.strip().toUpperCase(Locale.ROOT);
            return switch (value) {
                case "ASC" -> ASC;
                case "DESC" -> DESC;
                default -> throw new IllegalArgumentException(
                    "Unsupported sort direction");
            };
        }
    }

    public List<ProductRow> find(
        String sortKey,
        String rawDirection,
        BigDecimal minPrice,
        int page,
        int size
    ) {
        SortField field = SortField.fromClient(sortKey);
        SortDirection direction = SortDirection.fromClient(rawDirection);

        if (minPrice == null || minPrice.signum() < 0)
            throw new IllegalArgumentException("Invalid minimum price");
        if (page < 0 || page > 10_000)
            throw new IllegalArgumentException("Invalid page");
        if (size < 1 || size > 100)
            throw new IllegalArgumentException("Invalid size");

        int offset = Math.multiplyExact(page, size);

        String sql = """
            SELECT p.id, p.name, p.price, p.created_at
            FROM products p
            WHERE p.active = ? AND p.price >= ?
            ORDER BY %s %s, p.id ASC
            LIMIT ? OFFSET ?
            """.formatted(field.sqlExpression, direction.name());

        return jdbc.query(
            sql,
            (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getTimestamp("created_at").toLocalDateTime()
            ),
            true, minPrice, size, offset
        );
    }
}
```

**Why it is safe:** `SortField.fromClient` and `SortDirection.fromClient` return enums or throw exceptions. Only `field.sqlExpression` and `direction.name()` from enum constants enter the two `%s` slots of `String.formatted`. This differs fundamentally from `.formatted(rawSortKey, rawDirection)`. Boolean data, price threshold, and pagination numbers **are still bound via `?`**. `p.id ASC` resolves the tie-breaker for two products with the same price.

### 7.4. Running and Checking Results

In a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

With Java 17+, Gradle, downloadable dependencies, and H2 working as configured, **the lines printed by `System.out` of the example** are:

```text
priceDesc=[Notebook, Clip, Pen]
nameAsc=[Clip, Notebook, Pen]
invalidRejected=true
remaining=4
```

Spring Boot may print additional logs. Both Notebook (id=2) and Clip (id=3) have price 25.00; `id ASC` breaks the tie so Notebook comes first. Ruler is inactive so it is excluded from both lists yet still exists in the table (remaining = 4).

Note: the example uses H2's `LIMIT ? OFFSET ?` syntax, also present in PostgreSQL. When moving to SQL Server, Oracle, or other DBMSs, pagination syntax and `NULL` handling may differ; adapt the query **using server-controlled fragments**, never by letting users send SQL.

## 8. Controller and Error-Handling Rules

API example:

```text
GET /products?sort=price&direction=DESC&page=0&size=20
```

Even if the UI only renders a safe dropdown, the endpoint must treat URL/query params as **untrusted**. Clients can call it directly with scripts or modify requests.

Separate responsibilities:

1. **Controller:** parse parameters, check types/bounds, standardize defaults and HTTP status codes.
2. **Service:** decide which user may view which dataset and sort by which fields under business rules.
3. **Repository:** use allow-lists to assemble SQL fragments and bind data.
4. **DB:** enforce row/tenant permissions, constraints, indexes, and resource limits.

Controller method example (not a standalone file; assumes Spring MVC imports and `ProductRepository repo`):

```java
@GetMapping("/products")
public List<ProductRepository.ProductRow> products(
        @RequestParam(required = false) String sort,
        @RequestParam(required = false) String direction,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return repo.find(
        sort, direction, new BigDecimal("0.00"), page, size);
}
```

For invalid inputs, define dedicated validation exceptions and `@ExceptionHandler`/`@ControllerAdvice` to respond with 400. Avoid catching **every** `IllegalArgumentException` in the application and treating it as a user error: many internal programming bugs can also throw this exception type.

Illustrative response:

```json
{
  "error": "INVALID_SORT",
  "allowed": ["name", "price", "createdAt"]
}
```

These are **public API keys**, not a full list of physical column names. Do not echo suspicious raw input or verbatim SQL with stack traces into responses/logs.

**Independent authorization:** Safe sorting does not automatically filter the query by the right tenant or user. For instance, `WHERE p.tenant_id = ?` must be bound to the tenant ID from a trusted authentication context, never trusting a client-supplied URL string. Even sorting on a column not returned in `SELECT` can leak information through result order; deciding which columns are permitted is a business decision, not just an SQL parser concern.

## 9. Multi-Column Sorting: Parsing Each Selection

An API may support a list:

```text
[("price", "DESC"), ("name", "ASC")]
```

Do not take a string `sort=price DESC,name ASC` and concatenate it straight into SQL. Instead:

- Limit the number of criteria (e.g., max three).
- Parse each field name into an allow-listed key.
- Parse each direction into `ASC` or `DESC`.
- Reject duplicate criteria, nulls, or syntax errors.
- Preserve the exact order of selected criteria.
- Append a unique tie-breaker key if not already present.
- Never allow raw fragments like `COLLATE...`, `NULLS...`, or `LOWER(...)` into the SQL statement.

Standalone `MultiSortBuilder.java` class for Java 17:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class MultiSortBuilder {
    private MultiSortBuilder() {}

    public record RequestedSort(String field, String direction) {}

    private static String sqlColumn(String field) {
        if (field == null)
            throw new IllegalArgumentException("Missing sort field");
        return switch (field) {
            case "name" -> "p.name";
            case "price" -> "p.price";
            case "createdAt" -> "p.created_at";
            case "id" -> "p.id";
            default -> throw new IllegalArgumentException(
                "Unsupported field");
        };
    }

    private static String sqlDirection(String raw) {
        if (raw == null)
            throw new IllegalArgumentException("Missing direction");
        String value = raw.strip().toUpperCase(Locale.ROOT);
        return switch (value) {
            case "ASC", "DESC" -> value;
            default -> throw new IllegalArgumentException(
                "Unsupported direction");
        };
    }

    public static String build(List<RequestedSort> sorts) {
        if (sorts == null || sorts.isEmpty())
            return "ORDER BY p.id ASC";
        if (sorts.size() > 3)
            throw new IllegalArgumentException("Too many sorts");

        List<String> clauses = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (RequestedSort sort : sorts) {
            if (sort == null || !seen.add(sort.field()))
                throw new IllegalArgumentException(
                    "Missing or duplicate sort key");
            clauses.add(
                sqlColumn(sort.field()) + " "
                + sqlDirection(sort.direction())
            );
        }
        if (!seen.contains("id")) clauses.add("p.id ASC");
        return "ORDER BY " + String.join(", ", clauses);
    }

    public static void main(String[] args) {
        System.out.println(build(List.of(
            new RequestedSort("price", "DESC"),
            new RequestedSort("name", "ASC")
        )));
        System.out.println(build(List.of()));
    }
}
```

Commands:

```bash
javac MultiSortBuilder.java
java MultiSortBuilder
```

Stdout:

```text
ORDER BY p.price DESC, p.name ASC, p.id ASC
ORDER BY p.id ASC
```

`HashSet` is only for preventing duplicates, **not** controlling order (fragments are added sequentially to `ArrayList`). Do not assume `sort.split(",")` makes input protected: if the API accepts shorthand syntax like `name,-price`, each token after splitting must still be converted to validated types, never raw SQL.

When an API supports keyset pagination for multiple sort keys, the cursor comparison predicate must match the **exact order and direction** of the fields. Do not use a single generic cursor condition for all combinations without proving correctness and performance.

## 10. JOINs and Sort Expressions

For multi-table queries:

```sql
SELECT p.id, p.name, c.name AS category_name
FROM products p
JOIN categories c ON c.id = p.category_id
ORDER BY p.name ASC, p.id ASC;
```

Both tables have `name`, so an unaliased `ORDER BY name` can cause an ambiguous column error or unexpected semantics. Mapping should be explicit:

| API Key | Correct Fragment for JOIN Query |
| --- | --- |
| `productName` | `p.name` |
| `categoryName` | `c.name` |
| `createdAt` | `p.created_at` |

Each query can have its **own allow-list**. Do not reuse `name → p.name` across every query if aliases or business semantics differ.

### 10.1. Sorting by Fixed Expressions

For example, putting in-stock products first, then lowest price first:

```sql
ORDER BY CASE WHEN p.stock_count > 0 THEN 0 ELSE 1 END ASC,
         p.price ASC,
         p.id ASC;
```

The API can publish a key `availabilityThenPrice`, and the server maps it directly to a **fixed complete fragment** like above. Clients are not allowed to pass arbitrary `CASE WHEN ...`.

### 10.2. NULLS FIRST/LAST and Collation

Some dialects allow:

```sql
ORDER BY p.created_at DESC NULLS LAST, p.id ASC;
```

However, support and default `NULL` ordering differ across DBMSs. Collation affects how accented strings, letter case, and Unicode are sorted. If you need case-insensitive sorting or always placing NULLs last, the mapping must choose fixed expressions/keywords tested for your dialect and index, rather than letting users inject collation names or `NULLS ...` into the query.

## 11. Performance and Limiting Valid Selections

Allow-lists do not only prevent injection; they also restrict expensive sort expressions:

- Sorting by a matching index (`created_at`, `id`) can yield good plans.
- `LOWER(p.name)` may need a functional index or specific collation/index.
- Sorting on a column from a JOINed table can cause a large sort operation.
- Sorting after an unindexed filter may scan many rows.
- Large `OFFSET` can force the DB to discard many rows before returning a small page.
- Multi-field `ORDER BY` combinations require evaluating appropriate indexes and plans.

Optimize with `EXPLAIN` and representative data. Do not allow clients to sort on every column merely because it exists or the parser can build a valid query. Weigh **data permissions**, **UI meaning**, and **query cost**.

Some ORMs/frameworks provide `Sort`/sort descriptor types: they help represent structure, yet do not automatically enforce a business allow-list. You must still define **which properties an endpoint may accept** and prevent user-controlled unsafe expressions.

## 12. Use Fully Fixed SQL Variants When Options Are Few

When an API has only two modes, you may not need to build the `ORDER BY` part with separate fragments; instead choose the entire SQL query via an enum:

```java
String sql = switch (mode) {
    case NAME_A_TO_Z -> """
        SELECT p.id, p.name
        FROM products p
        WHERE p.active = ?
        ORDER BY p.name ASC, p.id ASC
        """;
    case PRICE_HIGH_FIRST -> """
        SELECT p.id, p.name
        FROM products p
        WHERE p.active = ?
        ORDER BY p.price DESC, p.id ASC
        """;
};
```

This is a snippet inside a method with enum `mode`; not a standalone file. This method is easy to audit because every query text is fixed. When there are many fields/directions, an enum fragment mapper scales better. Pick the simplest approach **that keeps raw input out of syntax**.

You may see another approach using `ORDER BY CASE WHEN ? = 'price' THEN price ...` to bind a choice inside a single query; be cautious because data types differ across branches, affecting ordering and index/plan usage. Do not use it as a default replacement for an allow-list without analyzing the query.

## 13. Testing Safety and Correctness

Verify both the mapper and returned data:

| Input / Condition | Expected Result |
| --- | --- |
| `sort=price&direction=DESC` | `ORDER BY p.price DESC, p.id ASC` |
| `sort=name&direction=asc` | `ORDER BY p.name ASC, p.id ASC` |
| `sort=createdAt` | Selects `p.created_at`, default direction per contract. |
| `sort` missing | Uses default sort. |
| `sort=unknown` | Validation error, no dynamic query executed. |
| `sort=p.price` | Rejected if contract only permits `price` key. |
| `sort=price DESC; DROP TABLE products` | Rejected, payload not inserted into SQL. |
| `sort=LOWER(name)` | Rejected unless a dedicated server-defined key exists. |
| `direction=ASC NULLS LAST` | Rejected because direction is not in the two enums. |
| `sort=name,price` on single-sort API | Rejected; multi-sort must be parsed separately. |
| `size=1000000` or `page=-1` | Rejected per bounds. |
| Two rows with tied price | `id ASC` order breaks ties deterministically. |
| Results belonging to another tenant | Not returned: tenant/permission predicate in `WHERE`. |

### 13.1. JUnit Unit Test for SortPolicy

The Java 17 test snippet below requires `junit-jupiter` on the test classpath and the `SortPolicy` class from section 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class SortPolicyTest {
    @Test
    void acceptsKnownSort() {
        assertEquals(
            "ORDER BY p.price DESC, p.id ASC",
            SortPolicy.orderBy("price", "desc"));
    }

    @Test
    void rejectsUnknownSyntax() {
        assertThrows(IllegalArgumentException.class,
            () -> SortPolicy.orderBy(
                "price DESC; DROP TABLE products", "ASC"));
        assertThrows(IllegalArgumentException.class,
            () -> SortPolicy.orderBy(
                "name", "ASC NULLS LAST"));
    }
}
```

Unit tests only check the mapper. Integration tests on a real DBMS/H2 are needed for valid SQL, ordering, pagination, duplicate values, access permissions, and limits. You can fuzz inputs with Unicode, quotes, semicolons, whitespace, parentheses, and very long strings, without logging unbounded payloads.

Security invariant to preserve:

> **No unapproved input can ever appear in the final SQL statement as an identifier, keyword, or expression.**

## 14. Common Mistakes Found in Code Reviews

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| `"ORDER BY " + request.sort` | Turns input into SQL structure. | Map API keys through an allow-list. |
| `ORDER BY ?` binding `"price"` | `?` represents a value, not an identifier. | Pick fixed fragment, bind WHERE. |
| Regex `[A-Za-z_]+` instead of allow-list | Sensitive columns can still match. | Enum/switch per endpoint. |
| Escaping quotes in sort key | Value escaping does not solve grammar/permission. | Map to constants. |
| Allow-listing field but concatenating raw direction | `ASC/DESC` keywords also need validation. | Direction enum/boolean. |
| Fallback `map.getOrDefault(key,key)` | Invalid input goes straight into SQL. | Throw error or use fixed default for missing input. |
| Exposing DB keys like `p.price` in API | Leaks implementation and couples schema. | Public key `price` → `p.price`. |
| Sorting tied prices without `id` | Pages can become unstable. | Add unique tie-breaker key. |
| Not validating LIMIT/OFFSET | Heavy load, negative/overflow values. | Bound and bind numbers. |
| Omitting tenant filter | Safe sorting does not mean authorized query. | Trusted `WHERE` tenant/user filter. |
| Reusing same name mapping across all JOINs | Wrong/ambiguous aliases. | Per-query/endpoint mapping. |
| Allowing arbitrary DB metadata column sorts | May leak data / exhaust resources. | Choose columns per business rules. |

## 15. Self-Check Q&A

**1.** Why is `ORDER BY ?` with bound `"p.price"` not equivalent to `ORDER BY p.price`?

**Answer:** A placeholder represents a data value, and does not turn a string into an identifier reference. The DB may treat it as a constant or reject it.

**2.** If using `JdbcTemplate.query(sql, rowMapper, args...)`, is concatenating `sort` from HTTP into SQL automatically safe?

**Answer:** No. Only values passed in `args` are bound. The SQL text built beforehand still contains uncontrolled input if you concatenate raw sort.

**3.** Can a letters-only regex replace an allow-list?

**Answer:** No. It does not know which columns are permitted by business logic, authorization, and query cost.

**4.** How should sort direction be handled?

**Answer:** Parse into an enum/boolean with exact `ASC` and `DESC`; unknown values must be rejected. Never concatenate raw direction.

**5.** Why add `id` as a secondary sort key?

**Answer:** When rows tie on the primary sort key, a unique tie-breaker provides deterministic order and more stable pagination.

**6.** For a JOIN query with `p.name` and `c.name`, if a client sends `sort=name`, can you use raw `ORDER BY name`?

**Answer:** You should not. Define explicit key names `productName`/`categoryName` and map them to `p.name`/`c.name` for that context.

**7.** How do you support case-insensitive sorting or `NULLS LAST`?

**Answer:** Provide a dedicated option and map it to a fixed fragment tested for your DBMS. Never accept arbitrary SQL expressions from clients.

**8.** When `page=0` and `size=20`, should `LIMIT` and `OFFSET` be bound?

**Answer:** When supported by the dialect/driver, validate numeric types/bounds and bind them. Also manage query plans, page limits, and data permissions.

## 16. Pre-Deployment Checklist

- [ ] API sort keys are explicitly published, decoupled from SQL/schema.
- [ ] Every sort key maps to a **fixed server-authored** fragment.
- [ ] Direction is strictly `ASC`/`DESC` after validation.
- [ ] Unknown values never fall back to raw input.
- [ ] Data values continue to be bound via `JdbcTemplate`.
- [ ] JOIN queries use proper aliases and per-query allow-lists.
- [ ] Multi-sort limits item count, prevents duplicates, and validates every criterion.
- [ ] Sorting includes a unique tie-breaker; pagination handles changing data per requirements.
- [ ] Page/size and filters have types/bounds; overflow and overload are prevented.
- [ ] Row, tenant, and column authorization is handled independently.
- [ ] Malicious inputs, SQL expressions, tied values, paginated results, and error cases are tested.
- [ ] `EXPLAIN`, indexes, collation, and NULL ordering are evaluated on the target DBMS.

## 17. References

- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet): parameterized data values and allow-list validation for identifiers/`ASC`/`DESC`.
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `query(String, RowMapper<T>, Object...)` and bind parameters.
- [Java SE — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): JDBC parameters represent data.
- [PostgreSQL — SELECT and ORDER BY](https://www.postgresql.org/docs/current/sql-select.html): `ORDER BY` syntax, multiple criteria, `ASC/DESC`, and `NULLS FIRST/LAST`.
- [H2 — SQL Commands](https://h2database.com/html/commands.html): query syntax used for the sample program.

**Conclusion:** Let clients choose **one of the sorting options supported by the application**, never let clients send SQL. Enums/allow-lists determine column names and keywords; JDBC binding handles values; tie-breakers, authorization, and DBMS testing guarantee accurate and stable results.
