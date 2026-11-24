# Choosing Named or Positional Parameters to Keep JDBC Queries Maintainable

## 1. The Problem: One SQL Statement, Two Ways to Express Parameters

In Spring Framework's data-access layer, SQL statements often need values from the application: IDs, status codes, start dates, limits, key lists, etc. Plain JDBC uses **positional placeholders** `?`. Spring JDBC adds **named placeholders** `:status`, `:customerId` via `NamedParameterJdbcTemplate`; starting in Spring Framework 6.1, `JdbcClient` also supports both styles in one fluent API.

This lesson targets a practical decision: **should each SQL query use named or positional parameters to keep code clear, safe, and maintainable?** There is no "named is always better" or "positional is always faster" rule; what matters is parameter count, readability, risk of ordering mistakes, frequency of SQL edits, and project conventions.

After this lesson, you will be able to:
- Write `JdbcTemplate` with `?` and `NamedParameterJdbcTemplate` with `:name` properly.
- Understand that named parameters are ultimately converted by Spring to positional JDBC placeholders; both still use prepared binding for **values**.
- Choose a style based on concrete criteria rather than gut feeling.
- Avoid **parameter-order swap** bugs where SQL still runs yet reads or updates the wrong data.
- Leverage repeated named parameters, `MapSqlParameterSource`, `BeanPropertySqlParameterSource`, typed SQL NULLs, `IN (:ids)`, and batch updates.
- Understand when named parameters do **not** solve the problem: dynamic identifiers, SQL injection via SQL fragments, buggy queries, SQL NULL logic, transactions, and driver limits.
- Run a deterministic Java 17 / Spring Boot / H2 example and build tests verifying both binding styles.

**Technical context:** Spring JDBC in Spring Framework 6.x, Spring Boot 3.x, Java 17+, `JdbcTemplate`/`NamedParameterJdbcTemplate` (blocking JDBC). Examples illustrate standard relational SQL; PostgreSQL/Oracle/MySQL-specific syntax should be tested separately.

## 2. Two Basic Binding Styles: Clear at First Glance

Suppose you need to find customers with status `ACTIVE` in Vietnam, returning `id` and `email`.

### 2.1. Positional with JdbcTemplate

```java
// Snippet inside a class with JdbcTemplate jdbc.
List<CustomerRow> customers = jdbc.query("""
        SELECT id, email
        FROM customers
        WHERE status = ? AND country_code = ?
        ORDER BY id
        """,
    (rs, rowNum) -> new CustomerRow(
        rs.getLong("id"),
        rs.getString("email")
    ),
    "ACTIVE", "VN");
```

Parameter 1 is `status`; parameter 2 is `country_code`. Positions follow the `?` markers from left to right; Java arguments are passed in the exact same order.

### 2.2. Named with NamedParameterJdbcTemplate

```java
// Snippet inside a class with NamedParameterJdbcTemplate namedJdbc.
Map<String, ?> params = Map.of(
    "status", "ACTIVE",
    "country", "VN"
);

List<CustomerRow> customers = namedJdbc.query("""
        SELECT id, email
        FROM customers
        WHERE status = :status AND country_code = :country
        ORDER BY id
        """,
    params,
    (rs, rowNum) -> new CustomerRow(
        rs.getLong("id"),
        rs.getString("email")
    ));
```

Key `"status"` matches placeholder `:status` and `"country"` matches `:country`, **regardless of Map entry order**. Names form part of the contract between the SQL statement and the parameter source—they do not have to match column names verbatim: `:country` can bind to column `country_code` when the meaning is clear.

### 2.3. Both Styles Return Identical Results When Bound Properly

Given the same SQL logic, same values, and same database, both methods have **equivalent query semantics**. Named parameters do not turn SQL into a different language or introduce a new transaction model. They are a convenience layer giving names to placeholders.

Here is the core of the maintainability decision:
- `?` keeps SQL concise when there are only one or two obvious parameters.
- `:name` is self-documenting when there are many parameters, conditions of the same type, or queries whose condition order changes frequently.
- Both **must** use binding instead of concatenating user values directly into SQL.

Record used in examples:

```java
// CustomerRow.java
package example.jdbc;

public record CustomerRow(long id, String email) {}
```

Opening snippets assume appropriate imports and injected JDBC beans; the full runnable project is in section 15.

## 3. Under the Hood, NamedParameterJdbcTemplate Still Uses JDBC Positional Binding

In Spring JDBC's mechanism, `NamedParameterJdbcTemplate` parses SQL containing `:name`, converts named placeholders into the `?` markers understood by JDBC `PreparedStatement`, and arranges/supplies values in matching order.

```text
Application:
  SELECT id FROM customers
  WHERE status = :status AND country_code = :country

Values:
  status -> "ACTIVE"
  country -> "VN"

Spring named-parameter adapter:
  1. Parse SQL, locate valid named placeholders.
  2. Build JDBC SQL with '?' (or expand lists when needed).
  3. Build binding order: ["ACTIVE", "VN"].

JDBC PreparedStatement:
  SELECT id FROM customers
  WHERE status = ? AND country_code = ?
                  1                    2

Database executes SQL with bound values.
```

This diagram is a **logical illustration**, not Spring's line-by-line source code. Spring also handles SQL string literals, repeated parameters, SQL type metadata, value lists, and parsed-SQL caching where appropriate. Avoid writing a naive regex to replace `:name` with `?` in production SQL; colons can appear in vendor syntax or SQL literals.

**Key point:** using named parameters preserves prepared binding for values. Just like `JdbcTemplate`, `NamedParameterJdbcTemplate` retains JDBC connection/statement/resultset lifecycle management, exception translation, and transaction participation in a proper Spring context.

### Never Assume Named Is Always Faster or Slower Than Positional

Placeholder parsing adds a small Java-side step, yet Spring caches parsed SQL and delegates to `JdbcTemplate`. Most workloads are dominated by network round trips, indexes, joins, I/O, or returned row counts rather than name translation overhead. When optimizing, measure **actual latency**, SQL plans, query counts, and connection pools instead of switching styles based on performance intuition.

## 4. When to Prefer Positional `?` Parameters

Positional binding is usually sensible when:
1. The SQL statement has **only one parameter**, such as `WHERE id = ?`.
2. There are **two parameters with obvious roles**, such as `WHERE created_at >= ? AND created_at < ?` when Java variable names are clear.
3. The SQL is short, stable, and its order is obvious.
4. You already use `JdbcTemplate` and switching to named parameters would not noticeably improve readability.
5. Low-level JDBC integration takes parameter indexes directly, such as a `PreparedStatementSetter` for vendor-specific binding.

Clear example:

```java
// Inside a repository with a JdbcTemplate jdbc field.
public int deleteExpiredSessions(java.time.Instant cutoff) {
    return jdbc.update("""
            DELETE FROM sessions WHERE expires_at < ?
            """,
        java.sql.Timestamp.from(cutoff));
}
```

Exactly one placeholder, one value. Switching to `:cutoff` is valid too, yet does not necessarily make the code more maintainable.

### Strengths and Trade-Offs of Positional Parameters

**Strengths:** minimal syntax, familiar across JDBC/drivers, no need to build a `Map`/`SqlParameterSource` for simple queries.

**Trade-off:** parameter meaning resides in **position**, so adding, removing, or reordering SQL conditions requires re-checking every corresponding argument. The more parameters share the same Java type, the easier bugs slip past the compiler.

Example:

```java
// SQL reorders the two conditions:
String sql = """
    SELECT id FROM customers
    WHERE country_code = ? AND status = ?
    """;

// WRONG: keeps argument order from when SQL was "status = ? AND country_code = ?".
var rows = jdbc.queryForList(sql, Long.class, "ACTIVE", "VN");
```

Here both arguments are `String`; the code compiles and runs, yet searches for `country_code = 'ACTIVE'` and `status = 'VN'`. Results may come back empty **with no exception**; in an `UPDATE`, swapping positions can corrupt data.

The positional fix is swapping arguments to `"VN", "ACTIVE"` and adding tests. When SQL evolves frequently or parameter counts grow, named parameters reduce this risk.

## 5. When to Prefer Named `:name` Parameters

Named binding pays off when:
1. A query has **many placeholders**, especially multiple values of the same type (`String`/`Long`).
2. Parameter names communicate meaning better than order, such as `:startDate`, `:endDate`, `:status`, `:minAmount`.
3. **The same value appears multiple times** in SQL: one name can be reused.
4. Queries have multiple `WHERE`, `JOIN`, or `UPDATE SET` clauses or change with requirements.
5. Values can come from a **form/DTO/command object** with well-named fields via `BeanPropertySqlParameterSource` when appropriate.
6. You want `IN (:ids)` with a list parameter instead of manually generating `?` markers.
7. Code reviews benefit from matching SQL directly against parameter values/types.
8. The repository layer follows a consistent named-parameter convention for readability and debugging.

Multi-parameter example:

```java
// Method inside a repository with NamedParameterJdbcTemplate namedJdbc.
public int updateSubscription(
        long subscriptionId,
        String nextStatus,
        String reason,
        java.time.Instant changedAt,
        long expectedVersion) {

    var params = new MapSqlParameterSource()
        .addValue("id", subscriptionId)
        .addValue("status", nextStatus)
        .addValue("reason", reason)
        .addValue("changedAt",
            java.sql.Timestamp.from(changedAt))
        .addValue("expectedVersion", expectedVersion);

    return namedJdbc.update("""
            UPDATE subscriptions
            SET status = :status,
                reason = :reason,
                changed_at = :changedAt,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """, params);
}
```

The updated row count is **0 or 1** when `id` is PRIMARY KEY. Returning 0 could mean either missing record or optimistic lock/version mismatch—never assume a single cause without checking the contract. Named parameters make it effortless to match each variable to its SQL column without counting `?` markers.

## 6. Quick Decision Table: Named or Positional?

| Scenario | Usually Suitable Choice | Why |
|---|---|---|
| `SELECT ... WHERE id = ?` | Positional or named | One parameter, trivial order |
| Two parameters of different types (`Long` and `Instant`) | Positional is usually enough | Compiler/tests catch certain mix-ups |
| 5–10 parameters of the same String type | Named | Prevents silent positional swaps |
| One value used at three SQL positions | Named | Bind one name instead of repeating args manually |
| Long SQL with many joins/filters | Named | Names make queries easier to review |
| Variable-length list of IDs | Named `IN (:ids)` | Spring expands list placeholders |
| Update from a JavaBean/command object | Named + `BeanPropertySqlParameterSource` when contract fits | Reduces boilerplate mapping |
| Very short, stable SQL | Keep current style | Changing solely out of preference adds churn |
| Binding a specialized JDBC vendor type | Either API; `PreparedStatementSetter`/`SqlParameterSource` | Binding capability matters more than placeholder syntax |
| Team already has a consistent convention | Follow convention while preserving clarity | Avoids style-switching overhead across modules |
| Queries built from dynamic clauses | Named is usually easier for composing conditions, with security rules | Names stay stable when clause order shifts |

**Pragmatic guideline:** use positional for short 1–2 parameter statements, and favor named when queries are long, have multiple same-type parameters, repeat values, or change often. Avoid rigid rules like "every query must be named" when there is no maintainability gain.

## 7. Swapped-Argument Bug: A Classic Maintenance Demo

Suppose a repository receives `status="ACTIVE"` and `country="VN"`.

Initial version:

```java
String sql = """
    SELECT id FROM customers
    WHERE status = ? AND country_code = ?
    """;
List<Long> ids = jdbc.queryForList(
    sql, Long.class, status, country);
```

A later edit moves the country predicate first to match an index layout:

```java
String sql = """
    SELECT id FROM customers
    WHERE country_code = ? AND status = ?
    """;

// BUG: forgot to update argument order.
List<Long> ids = jdbc.queryForList(
    sql, Long.class, status, country);
```

Wrong, yet **syntactically valid**. Because both parameters are Strings, JDBC cannot know which one the programmer meant for `country`.

With named parameters:

```java
String sql = """
    SELECT id FROM customers
    WHERE country_code = :country AND status = :status
    """;

List<Long> ids = namedJdbc.queryForList(
    sql,
    Map.of("status", status, "country", country),
    Long.class);
```

The `WHERE` order changed, yet name-based binding remains accurate. Reviewers only match `:country` to `"country"` and `:status` to `"status"` without counting placeholders.

**Limitation:** if keys are assigned backwards, e.g. `Map.of("country", status, "status", country)`, named binding is **still wrong**. Names help spot mistakes; they do not replace tests and code reviews.

## 8. Repeated Parameters in the Same Query

A named parameter can appear multiple times while being defined once:

```java
// Method inside a class with namedJdbc.
Long count = namedJdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE points >= :threshold
          AND (points - :threshold) <= :maxGap
        """,
    Map.of("threshold", 20, "maxGap", 20),
    Long.class);
```

`:threshold` appears twice. Spring creates two `?` JDBC positions and binds 20 to both. Changing `threshold` at the call site requires editing only one entry.

Positional equivalent:

```java
Long count = jdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE points >= ?
          AND (points - ?) <= ?
        """,
    Long.class,
    threshold,
    threshold,
    maxGap);
```

If a programmer forgets the second `threshold` argument, results can silently break.

**One named key holds one value per execution**. If two positions in SQL need **two** different values, never reuse the same name—define distinct `:minPoints` and `:maxPoints`.

## 9. Named Parameter Sources: Map, MapSqlParameterSource, BeanPropertySqlParameterSource

### 9.1. Map: Good for a Few Non-Null Values

```java
Map<String, Object> params = Map.of(
    "status", "ACTIVE",
    "country", "VN",
    "limit", 100
);
```

`Map.of` is concise and immutable, yet **rejects null keys and null values**. Never write `Map.of("note", null)` for nullable fields: Java throws `NullPointerException` before JDBC runs.

A `HashMap` allows null, yet carries no direct SQL type metadata. For a handful of ordinary non-null values, `Map` is clear enough.

### 9.2. MapSqlParameterSource: Scales When Types or Nulls Are Needed

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
    .addValue("id", 2L, Types.BIGINT)
    .addValue("note", null, Types.VARCHAR);

int affected = namedJdbc.update("""
        UPDATE customers
        SET note = :note
        WHERE id = :id
        """, params);
```

`MapSqlParameterSource` implements `SqlParameterSource`. It provides named values and JDBC type metadata when needed; `Types.VARCHAR` tells JDBC that `:note` is SQL VARCHAR even though the Java value is null.

Remember: **a typed NULL is still SQL NULL**. In `SET note = :note`, it sets `note` to NULL—it does not mean "keep unchanged". In `WHERE note = :note` with null, SQL three-valued logic evaluates the comparison as non-TRUE; to filter NULLs, use `IS NULL` or appropriate null-safe semantics.

### 9.3. BeanPropertySqlParameterSource: When a DTO/JavaBean Matches SQL

```java
public final class PointChange {
    private final String email;
    private final int points;

    public PointChange(String email, int points) {
        this.email = email;
        this.points = points;
    }

    public String getEmail() {
        return email;
    }

    public int getPoints() {
        return points;
    }
}
```

In the repository:

```java
var input = new PointChange("binh@example.test", 25);

int affected = namedJdbc.update("""
        UPDATE customers
        SET points = :points
        WHERE email = :email
        """,
    new BeanPropertySqlParameterSource(input));
```

`BeanPropertySqlParameterSource` reads object properties. Property names must match (`points`, `email` here) with working accessors. For large objects with many extra fields beyond the SQL, be mindful not to bind unintended fields by name collisions; the SQL placeholders define what is actually read.

In many Java 17 projects, records may also be supported depending on Spring version/mapper APIs; a JavaBean with public getters as shown expresses the contract clearly and is easy to test. If you need SQL types for nullable properties, call `registerSqlType("note", Types.VARCHAR)` on the `SqlParameterSource` or use an explicit `MapSqlParameterSource`.

## 10. Collections and the `IN (:ids)` Clause

This is a major practical reason to pick named parameters. Suppose you want customers for a variable-length list of IDs:

```java
List<Long> ids = List.of(1L, 4L);

List<CustomerRow> customers = namedJdbc.query("""
        SELECT id, email
        FROM customers
        WHERE id IN (:ids)
        ORDER BY id
        """,
    new MapSqlParameterSource("ids", ids),
    (rs, rowNum) ->
        new CustomerRow(
            rs.getLong("id"), rs.getString("email")));
```

Spring expands `:ids` into the matching number of JDBC placeholders, e.g., `IN (?, ?)`, and binds both values. There is no need to build `"1,4"` or concatenate caller IDs into SQL.

**Handle empty sets:** if `ids = List.of()`, many SQL dialects reject `IN ()`, and there is no portable guarantee across drivers/templates. Decide business semantics upfront:

```java
// Illustrative method in a repository with namedJdbc and CUSTOMER_MAPPER.
public List<CustomerRow> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return namedJdbc.query("""
            SELECT id, email
            FROM customers
            WHERE id IN (:ids)
            ORDER BY id
            """,
        new MapSqlParameterSource("ids", ids),
        CUSTOMER_MAPPER);
}
```

This fits when **no IDs ⇒ no results**. Another API might interpret "no filter" as returning all rows: never conflate the two meanings.

When lists grow very long:
- SQL can exceed driver/database parameter limits.
- Expanded SQL text changes shape, affecting plan caches depending on the DB.
- Controlled batching, temp tables/table-valued parameters/arrays per DB, or joining an ID table may be needed.
- Never allow callers to submit unbounded lists straight into a massive SQL query.

**Named parameters do not replace pagination.** Use deterministic `ORDER BY`, `LIMIT/OFFSET`, or keyset pagination as appropriate.

## 11. Optional Conditions and Dynamic SQL: Avoid Both Kinds of Bugs

Search filters may contain `status`, `country`, `createdAfter`, `minPoints`. Named params keep conditional SQL readable.

Example appending only developer-defined clauses:

```java
// Snippet in a repository with NamedParameterJdbcTemplate namedJdbc.
public List<CustomerRow> search(
        String status,
        String country) {

    StringBuilder sql = new StringBuilder("""
        SELECT id, email
        FROM customers
        WHERE 1 = 1
        """);

    var params = new MapSqlParameterSource();

    if (status != null) {
        sql.append(" AND status = :status");
        params.addValue("status", status);
    }
    if (country != null) {
        sql.append(" AND country_code = :country");
        params.addValue("country", country);
    }

    sql.append(" ORDER BY id");

    return namedJdbc.query(
        sql.toString(), params, CUSTOMER_MAPPER);
}
```

Security point: the code only appends **fixed, source-authored SQL fragments**; user values still travel through named binding. Never insert a raw filter or sort string from a request.

**Maintainability points to watch:**
- Only add a placeholder when you also add its value. Adding `AND status = :status` while forgetting `params.addValue("status", ...)` causes Spring to throw a missing-parameter error.
- When a filter is null/empty, decide explicitly whether to omit the condition, filter for NULL, or reject with a validation error. Never let Java null guess for you.
- Avoid overusing `(:x IS NULL OR col = :x)` as a universal trick: besides NULL semantics, that pattern can degrade index plans depending on the DB. Measure and choose carefully.
- Do not let dynamic SQL combinations grow uncontrollably. If queries have too many variants, consider a controlled query builder or splitting into clear methods.

### Bugs That Can Happen with Positional Dynamic SQL

With `JdbcTemplate`, the same pattern uses a `List<Object>`:

```java
List<Object> args = new ArrayList<>();
StringBuilder sql = new StringBuilder(
    "SELECT id, email FROM customers WHERE 1 = 1");

if (status != null) {
    sql.append(" AND status = ?");
    args.add(status);
}
if (country != null) {
    sql.append(" AND country_code = ?");
    args.add(country);
}

sql.append(" ORDER BY id");
List<CustomerRow> result = jdbc.query(
    sql.toString(),
    CUSTOMER_MAPPER,
    args.toArray());
```

This satisfies the contract as long as each `?` is appended **together** with its argument. Still, later edits or reordered conditions easily desynchronize `args` if not carefully tracked. Named parameters eliminate that bug class, though they do not supply validation or business semantics.

## 12. Named Parameters Cannot Bind Table/Column Names or SQL Syntax

Both `?` and `:name` bind **values**. You cannot pass a column name as a scalar:

```sql
-- MISINTENDED: does NOT ORDER BY a user-selected column.
SELECT id, email FROM customers ORDER BY :sortColumn;
```

Depending on the database, `:sortColumn` is treated as a constant value and **does not become an SQL identifier**. Likewise, placeholders cannot replace table names, `ASC/DESC`, operators, or entire WHERE clauses.

When dynamic sorting is needed, use an **allowlist** mapping user choices to code-controlled SQL column names:

```java
// Snippet inside a repository; sortKey is validated input.
String orderBy = switch (sortKey) {
    case "email" -> "email";
    case "points" -> "points";
    default -> "id";
};

String sql = """
    SELECT id, email FROM customers
    WHERE status = :status
    ORDER BY
    """ + " " + orderBy + " ASC, id ASC";

return namedJdbc.query(
    sql,
    Map.of("status", status),
    CUSTOMER_MAPPER);
```

Here `orderBy` only ever evaluates to one of three developer-defined SQL literals; **never** substitute raw `request.getParameter("sort")`. `id ASC` keeps ordering deterministic when multiple rows tie on email/points; when sorting by `id`, repeating `id` can be omitted without changing safety.

When many options exist, build an enum or an immutable allowlist map. Never take column names from clients without validation.

## 13. SQL Injection Protection: Which Style Is Safe?

**Both are safe when using proper prepared binding for values**, and both are unsafe when raw input is concatenated into SQL.

Safe positional:

```java
jdbc.queryForList(
    "SELECT id FROM customers WHERE email = ?",
    Long.class, userEmail);
```

Safe named:

```java
namedJdbc.queryForList(
    "SELECT id FROM customers WHERE email = :email",
    Map.of("email", userEmail),
    Long.class);
```

Unsafe in both:

```java
// WRONG: concatenating raw input alters SQL structure.
String sql = "SELECT id FROM customers WHERE email = '" +
    userEmail + "'";
jdbc.queryForList(sql, Long.class);
```

Do not judge safety by `?` vs. `:` alone: trace the **actual path of untrusted data**. `NamedParameterJdbcTemplate` does not whitelist dynamic table/column names, does not escape `LIKE` wildcards, does not perform domain validation, and cannot fix flawed SQL logic.

### `LIKE` Still Has Wildcard Semantics

`LIKE` with `%` and `_` performs wildcard matching. Parameter binding stops SQL injection, **yet does not turn wildcards into literal characters**.

When requirements call for "name starts with the user's string as literal text", escape wildcards per SQL dialect:

```java
// Use ESCAPE '!' syntax when supported by the target database.
String literal = userPrefix
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String pattern = literal + "%";

List<String> emails = namedJdbc.queryForList("""
        SELECT email FROM customers
        WHERE email LIKE :pattern ESCAPE '!'
        ORDER BY email
        """,
    Map.of("pattern", pattern),
    String.class);
```

Here `!` is the escape character per SQL `ESCAPE`. When switching DBs, retest escaping, collation/case-sensitivity, and special-character behavior. Cap input length as well; a user entering `%` should not unintentionally trigger a full-table scan when literal matching is expected.

## 14. SQL NULL and Parameter Types: Names Do Not Replace Types

Named binding does not infer every SQL type from `null`. When a driver requires a typed NULL, use `MapSqlParameterSource`:

```java
var params = new MapSqlParameterSource()
    .addValue("note", null, java.sql.Types.VARCHAR)
    .addValue("id", 2L, java.sql.Types.BIGINT);

namedJdbc.update("""
        UPDATE customers
        SET note = :note
        WHERE id = :id
        """, params);
```

Positional equivalent using `SqlParameterValue`:

```java
jdbc.update("""
        UPDATE customers
        SET note = ?
        WHERE id = ?
        """,
    new SqlParameterValue(java.sql.Types.VARCHAR, null),
    new SqlParameterValue(java.sql.Types.BIGINT, 2L));
```

**Do not** conflate "choosing named for readability" with "using typed NULL because the database needs a type": these are **two orthogonal decisions**. Both named and positional styles can supply SQL types.

Key notes:
- `Map.of` rejects null values; for typed nulls, use `MapSqlParameterSource`.
- SQL `WHERE col = :maybeNull` still does not match SQL NULL rows when the parameter is null; SQL three-valued logic requires `IS NULL` or a dialect-specific null-safe predicate.
- `NULL` differs from the string `"null"` and the number 0.
- `SqlParameterValue`/`java.sql.Types` do not override `NOT NULL` constraints or validate values.
- If a PATCH API must distinguish "field omitted" from "null sent to clear", define the domain contract explicitly; named binding cannot tell them apart once both become a Java `null`.

## 15. Complete Spring Boot + H2 + Java 17 Example

This runnable demo fits in a small project. It uses fixed seed data, executes equivalent **positional** and **named** queries, reuses a named parameter, expands `IN (:ids)`, binds a typed NULL, updates from JavaBean properties, and runs a batch update.

### 15.1. Structure

```text
parameter-style-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/ParameterStyleDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'parameter-style-demo'
```

`build.gradle` (Spring Boot 3.3.5, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:paramstyles;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    country_code VARCHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    tier VARCHAR(20) NOT NULL,
    note VARCHAR(200),
    points INTEGER NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (1, 'an@example.test', 'VN', 'ACTIVE', 'GOLD', NULL, 10);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (2, 'binh@example.test', 'VN', 'ACTIVE', 'SILVER', 'old', 20);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (3, 'chi@example.test', 'US', 'SUSPENDED', 'GOLD', NULL, 30);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (4, 'dung@example.test', 'VN', 'ACTIVE', 'GOLD', NULL, 40);
```

`src/main/java/example/jdbc/ParameterStyleDemoApplication.java`:

```java
package example.jdbc;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@SpringBootApplication
public class ParameterStyleDemoApplication {

    public record CustomerRow(long id, String email) {}

    private static final RowMapper<CustomerRow> CUSTOMER_MAPPER =
        (rs, rowNum) -> new CustomerRow(
            rs.getLong("id"), rs.getString("email"));

    public static void main(String[] args) {
        SpringApplication.run(ParameterStyleDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner compare(
            JdbcTemplate jdbc,
            NamedParameterJdbcTemplate namedJdbc) {

        return args -> {
            // 1) Two styles, identical filters and deterministic sort order.
            List<CustomerRow> positional = jdbc.query("""
                    SELECT id, email
                    FROM customers
                    WHERE status = ? AND country_code = ?
                    ORDER BY id
                    """,
                CUSTOMER_MAPPER, "ACTIVE", "VN");

            List<CustomerRow> named = namedJdbc.query("""
                    SELECT id, email
                    FROM customers
                    WHERE status = :status AND country_code = :country
                    ORDER BY id
                    """,
                Map.of("country", "VN", "status", "ACTIVE"),
                CUSTOMER_MAPPER);

            System.out.println(
                "same=" + positional.equals(named));
            System.out.println("ids=" +
                named.stream().map(CustomerRow::id).toList());

            // 2) :threshold appears twice while bound only once.
            Long repeated = namedJdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM customers
                    WHERE points >= :threshold
                      AND (points - :threshold) <= :maxGap
                    """,
                Map.of("threshold", 20, "maxGap", 20),
                Long.class);
            System.out.println("repeatedCount=" + repeated);

            // 3) List expands to IN (?, ?).
            List<Long> chosen = namedJdbc.query("""
                    SELECT id
                    FROM customers
                    WHERE id IN (:ids)
                    ORDER BY id
                    """,
                new MapSqlParameterSource(
                    "ids", List.of(1L, 4L)),
                (rs, rowNum) -> rs.getLong("id"));
            System.out.println("chosen=" + chosen);

            // 4) SQL NULL bound with explicit type.
            var nullable = new MapSqlParameterSource()
                .addValue("note", null, Types.VARCHAR)
                .addValue("id", 2L, Types.BIGINT);

            int noteUpdated = namedJdbc.update("""
                    UPDATE customers
                    SET note = :note
                    WHERE id = :id
                    """, nullable);
            System.out.println(
                "noteUpdated=" + noteUpdated);

            String note = jdbc.queryForObject(
                "SELECT note FROM customers WHERE id = ?",
                String.class, 2L);
            System.out.println("noteIsNull=" + (note == null));

            // 5) BeanPropertySqlParameterSource reads getters.
            var change = new PointChange(
                "binh@example.test", 25);
            int pointUpdated = namedJdbc.update("""
                    UPDATE customers
                    SET points = :points
                    WHERE email = :email
                    """,
                new BeanPropertySqlParameterSource(change));
            System.out.println(
                "pointUpdated=" + pointUpdated);

            Integer points = jdbc.queryForObject(
                "SELECT points FROM customers WHERE id = ?",
                Integer.class, 2L);
            System.out.println("points=" + points);

            // 6) Batch update: one parameter source per record.
            SqlParameterSource[] batch = {
                new MapSqlParameterSource("id", 1L)
                    .addValue("tier", "PLATINUM"),
                new MapSqlParameterSource("id", 4L)
                    .addValue("tier", "PLATINUM")
            };

            int[] updates = namedJdbc.batchUpdate("""
                    UPDATE customers
                    SET tier = :tier
                    WHERE id = :id
                    """, batch);
            System.out.println(
                "batch=" + Arrays.toString(updates));
        };
    }

    public static final class PointChange {
        private final String email;
        private final int points;

        public PointChange(String email, int points) {
            this.email = email;
            this.points = points;
        }

        public String getEmail() {
            return email;
        }

        public int getPoints() {
            return points;
        }
    }
}
```

**Run:** in the `parameter-style-demo` directory, using Java 17 and Gradle 8.x compatible with the Spring Boot plugin:

```bash
gradle bootRun
```

If the project already has a Gradle Wrapper, run `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows).

The lines printed by the application's `System.out.println` calls appear in this exact order; the console may also show build and Spring startup logs:

```text
same=true
ids=[1, 2, 4]
repeatedCount=3
chosen=[1, 4]
noteUpdated=1
noteIsNull=true
pointUpdated=1
points=25
batch=[1, 1]
```

**Line-by-line explanation:**
- Three VN/ACTIVE customers have IDs 1, 2, 4. Positional and named queries return the same 3 records via `record.equals()`, so `same=true`.
- `:threshold=20` matches points 20, 30, 40 where the difference from 20 does not exceed 20; 3 rows match.
- `IN (:ids)` with 1 and 4 returns `[1,4]` ordered by `id`.
- Updating `note` for ID 2 affects one row and sets `note` to SQL NULL; the scalar query returns Java `null`.
- JavaBean `PointChange` supplies `email`/`points` properties, updating ID 2 to 25 points.
- Batch updating `tier` for two valid IDs returns `[1, 1]` update counts on H2.

This is a **Spring Boot project runnable example**, not a standalone `javac`-compilable Java file because it requires Spring libraries. Running against H2 verifies SQL semantics; on a real DB, also test types, concurrency, and optimizer plans.

### Why Didn't the Demo Use Only NamedParameterJdbcTemplate?

The goal is **comparison**. Showing only named parameters makes it harder to see what actually changes (name mapping) versus what stays identical (prepared binding, transactions, SQL results). The demo verifies identical data, ordering, and semantics before showcasing scenarios where named syntax excels.

## 16. JdbcClient: Choosing Named or Positional in One Fluent API

From Spring Framework 6.1+, `org.springframework.jdbc.core.simple.JdbcClient` unifies calling both styles:

```java
// Method inside a class with a JdbcClient client field.
Long byPosition = client
    .sql("SELECT COUNT(*) FROM customers WHERE status = ?")
    .param("ACTIVE")
    .query(Long.class)
    .single();

Long byName = client
    .sql("SELECT COUNT(*) FROM customers WHERE status = :status")
    .param("status", "ACTIVE")
    .query(Long.class)
    .single();
```

**Both count ACTIVE customers**; `query(Long.class).single()` expects exactly one row (COUNT without GROUP BY returns one row). `JdbcClient` is a facade over `JdbcTemplate`/`NamedParameterJdbcTemplate`, not a new JDBC driver.

Distinguish clearly:
- `.param(value)`: positional binding in registration order (unless using indexed overloads).
- `.param("name", value)`: named binding.
- `.query(...).single()`: enforces single-row contract.
- `.query(...).optional()`: expresses 0..1 when needed.
- `.query(...).list()`: list of 0..N rows.

Do not mix `?` and `:name` in the same SQL statement just to "avoid converting everything"; choose one clear style **per statement**. Note that `JdbcClient` adds newer APIs in Spring 7.x; when using Spring 6.x, rely on the Javadoc matching your project version.

## 17. Batch Updates and Large Parameter Counts

When updating many rows with the same SQL, named parameters pair cleanly with command objects:

```java
SqlParameterSource[] rows = {
    new MapSqlParameterSource()
        .addValue("id", 1L)
        .addValue("tier", "GOLD"),
    new MapSqlParameterSource()
        .addValue("id", 4L)
        .addValue("tier", "GOLD")
};

int[] changed = namedJdbc.batchUpdate("""
        UPDATE customers
        SET tier = :tier
        WHERE id = :id
        """, rows);
```

Each `SqlParameterSource` corresponds to one statement execution in the batch. The source array order dictates `changed[]` order, while placeholder names match columns on each run. Batch output is an `int[]` of JDBC update counts; depending on the driver, special values like `Statement.SUCCESS_NO_INFO` may appear, so never assume every driver always returns exact row counts.

For positional batches, `JdbcTemplate.batchUpdate` with `BatchPreparedStatementSetter` is equally valid. When a batch has very few columns and clearly documented indexes, positional can be simpler. When a batch has many nullable/same-type fields or evolving schemas, named batches are easier to review.

**Never run a single 50,000-row update just because named params make the code short:** evaluate batch size, DB limits, locks, transaction duration, and test throughput/rollback. Parameter syntax does not replace data-processing strategy.

## 18. Common Mistakes with Named Parameters

### 18.1. Misspelled Name or Missing Value

```java
// SQL expects :country, yet the map only provides "countryCode".
namedJdbc.queryForList("""
        SELECT id FROM customers
        WHERE country_code = :country
        """,
    Map.of("countryCode", "VN"),
    Long.class);
```

Spring cannot find `country` in the source and throws a binding error before/at execution. **Fix by matching names exactly**. Keep camelCase or snake_case consistent within a module and test every dynamic SQL branch.

### 18.2. SQL Containing `:` in Special Syntax or Literals

Some DBs like PostgreSQL use `::type` for casts, and SQL can also contain colons in string literals, comments, operators, or vendor-specific expressions. Spring has a named-parameter SQL parser; never do manual `sql.replace(":id", "?")`, which can corrupt `::`, literals, or prefix-similar parameter names.

When portability is needed or parser/dialect conflicts arise, use standard SQL `CAST(:value AS INTEGER)` or a supported equivalent and write integration tests. Never assume every DB shares the same cast syntax.

### 18.3. Naming Parameters After Keywords or Ambiguously

`:from`, `:to` may be valid in many contexts yet hard to review; names like `:startInclusive`, `:endExclusive` are clearer. Never name parameters after data types like `:string1` or `:long2` when domain names belong there.

### 18.4. Confusing Map Entry Order with Bind Order

Using named parameters does not require `Map` entries to be sorted in placeholder order. Forcing `LinkedHashMap` just "to match SQL order" usually signals confusion between the two mechanisms.

### 18.5. Passing a Complex Structure the SQL Does Not Understand

Named binding binds **JDBC values**; it does not automatically serialize arbitrary POJOs into JSON or SQL tuples. For JSON/UUID/arrays/enums/LOBs, the driver may need `SqlParameterSource` type metadata, casts, or vendor-specific objects. `IN (:ids)` collection expansion is a specific Spring feature; never assume any collection works with every operator.

### 18.6. Failing to Handle Empty or Huge `IN` Sets

Empty lists must have an explicit business outcome; oversized lists need DB-specific or batched solutions. Named parameters do not prevent hitting SQL bind limits.

### 18.7. Assuming Named Params Prevent Wrong Results from Domain Logic

`WHERE created_at > :endDate` with `:startDate` misnamed still returns wrong results. Tests must check input–output behavior and boundary conditions, not just that SQL throws no error.

## 19. Common Mistakes with Positional Parameters

### 19.1. Forgetting to Reorder When Refactoring WHERE

Both `status` and `country` are Strings, so the compiler does not know their roles. When changing SQL order, update argument order in the same edit and use tests with distinct fixtures to catch swaps.

### 19.2. Miscounting Placeholders

A query with 8 `?` markers and 7 args throws a bind error; 8 args in the wrong order may fail silently. Keep `Object[] args` close to the query rather than building arrays far from the SQL.

### 19.3. Confusing JDBC and Java Indexes

`PreparedStatement.setString(1, value)` is **1-based**, while Java `args[0]` is **0-based**. When writing manual setters, never call `setString(0, value)`.

### 19.4. Appending a Dynamic SQL Condition While Forgetting Its Value

When building with `StringBuilder` and `List<Object>`, append `?` and add the argument inside the exact same `if` branch rather than separating them. Switch to named parameters once complexity grows.

### 19.5. Dropping Placeholders and Concatenating Input into SQL

Switching from positional to named fixes nothing if the string already contains raw input before reaching the template. Clean up the data path: keep SQL as fixed/allowlisted templates and always bind values.

## 20. Maintenance Rules When Editing a Running Query

Suppose a repository currently uses positional parameters and you want to add `country`:
1. **State the contract first:** query purpose, required vs. optional conditions, null/empty semantics, deterministic output ordering.
2. **Check the schema:** indexes, unique constraints, nullable fields, and JDBC types.
3. **Choose style:** if adding one parameter to a short query, keeping positional is fine; if SQL is already long or has same-type parameters, consider converting the whole statement to named.
4. **Update SQL and bindings in the same diff:** verify every placeholder receives the right value.
5. **Test with distinct data:** e.g., `status` and `country` values where swapping Strings visibly changes results.
6. **Test 0/1/N results:** especially `queryForObject` vs. `query` List, SQL NULLs, duplicates, and constraints.
7. **Check transactions & update counts:** changing style does not alter transaction semantics; 0 rows updated must be handled per contract.
8. **Watch query plans if SQL shape changes:** changing placeholder style alone does not alter SQL logic, yet adding filters, `IN` lists, or casts can change plans.
9. **Avoid sweeping style rewrites across repositories without cause:** prevent huge diffs that are hard to review and roll back.

**Key code-review check:** keep SQL and parameter bindings adjacent. For named SQL, match `:name` against keys/bean properties. For positional, mentally number `?1`, `?2` and verify argument order. Write query tests with asymmetric fixtures to catch swapped values.

## 21. Testing Query Equivalence and Binding Safety

### 21.1. Recommended Test Matrix

| Scenario | What the Test Must Prove |
|---|---|
| 1–2 positional parameters | Fetches the exact expected row from DB |
| 2 same-type parameters swapped | Test fails when arguments swap order |
| Named query with reordered conditions | Results stay identical when names/values match |
| Repeated named parameter | Both positions bind the same value |
| Missing named value | Throws error; never silently binds null |
| Typed nullable field | Writes and reads back SQL NULL accurately |
| `IN (:ids)` with 2–3 items | Returns matching IDs in expected order |
| Empty `IN (:ids)` | Follows chosen contract without emitting invalid SQL |
| List containing out-of-range input | Enforces validation/limits properly |
| `LIKE` with literal `%`/`_` | Escapes properly when literal search is required |
| Dynamic sort | Accepts only columns from allowlist |
| Update matching 0 rows | 0 update count handled properly |
| SQL error / DB disconnect | Propagates `DataAccessException`, never returns empty list |
| Batch update of multiple rows | Each entry receives its own mapped values; read-back confirms |

### 21.2. Spring Boot/H2 Integration Test

Example in a project with `spring-boot-starter-test` and `@JdbcTest`, using the schema/data fixture from section 15:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

```java
// NamedVsPositionalTest.java (full test class in an appropriate project)
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@JdbcTest
class NamedVsPositionalTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired NamedParameterJdbcTemplate namedJdbc;

    @Test
    void equivalentBindingsReturnTheSameIds() {
        List<Long> positional = jdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = ? AND country_code = ?
                ORDER BY id
                """, Long.class, "ACTIVE", "VN");

        List<Long> named = namedJdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = :status AND country_code = :country
                ORDER BY id
                """,
            Map.of("status", "ACTIVE", "country", "VN"),
            Long.class);

        assertThat(positional).containsExactly(1L, 2L, 4L);
        assertThat(named).isEqualTo(positional);
    }

    @Test
    void swappedPositionalArgumentsChangeTheMeaning() {
        List<Long> swapped = jdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = ? AND country_code = ?
                ORDER BY id
                """, Long.class, "VN", "ACTIVE");

        assertThat(swapped).isEmpty();
    }
}
```

This test runs only when dependencies, JDBC slice configuration, schema/data, and datasource are present. It is **not** a standalone `javac` program. `@JdbcTest` normally wraps tests in a transaction and rolls back at the end; to verify commits/updates across requests, design an integration test whose behavior is not masked by test transaction rollback.

Testing on H2 suffices for argument-swap bugs and basic behavior; when running PostgreSQL, MySQL, or Oracle in production, add a dialect-accurate Testcontainers/integration suite for large `IN` lists, JSON, timezones, locks, and query plans.

### 21.3. Do Not Only Mock NamedParameterJdbcTemplate

Mocks verify SQL strings and Map keys, not that the database returns the right rows; at least critical queries should run against a real database. Avoid brittle tests tied to `Map.of` iteration order: named binding matches by **key**, not iteration order.

## 22. Complex Scenarios: SQL Types, Indeterminate States, and Large Data

When applications have nuanced states:
- **Missing field vs. SQL NULL:** use an input contract distinguishing absent / explicit-null / value; a null named parameter does not by itself signify "field not sent".
- **No-row errors:** `queryForObject()` expects exactly one row; 0 rows throws `EmptyResultDataAccessException` regardless of named vs. positional placeholders.
- **Multiple rows:** `queryForObject()` can also throw `IncorrectResultSizeDataAccessException`. Named binding does not turn a multi-row query into a single-row one.
- **Driver errors:** JDBC type mismatches, SQL syntax errors, and connection outages are translated to `DataAccessException` by Spring's translator; never return `Optional.empty()` merely because named parameters were used.
- **Streaming:** `queryForStream` returns a stream with a resource lifecycle the caller must close; choosing named vs. positional does not waive this responsibility.
- **Transactions:** `@Transactional` and the transaction manager govern connections, commits, and rollbacks. Changing placeholder style never changes transaction boundaries.
- **Large INs:** with tens of thousands of IDs, evaluate staging tables, bulk strategies, or DB-specific arrays; never ignore DB bind limits just because `IN (:ids)` looks clean.

## 23. Self-Check Questions

**Q1.** A query has one `?` placeholder in `WHERE id = ?`. Is it mandatory to switch to a named parameter for maintainability?

No. Positional is usually sufficient since order and meaning are obvious. Codebase consistency and tests still matter.

**Q2.** In `WHERE country_code = :country AND status = :status`, does reordering entries in `Map.of` change the result?

No, provided both keys/values match the right names. Spring looks up by name and orders values to match SQL for JDBC.

**Q3.** If `:threshold` appears twice, must you create two identical keys in the Map?

No. Define one `threshold` key; Spring binds the same value to every matching parameter position.

**Q4.** Is `IN (:ids)` with `List.of()` always supported?

No—`IN ()` is not portable. Handle the empty case in the application per contract before running the query.

**Q5.** Do named parameters allow `ORDER BY :userColumn` to select a column from the request?

No. Placeholders bind **values**, not identifiers. Use an allowlist of SQL fragments for column names.

**Q6.** Does using named parameters require `@Transactional`?

Not required for a single read query. Transactions are governed by business and consistency requirements, independent of binding style.

**Q7.** Is `Map.of("note", null)` a valid way to pass SQL NULL?

No. `Map.of` throws NPE on null values. Use `MapSqlParameterSource` with `addValue("note", null, Types.VARCHAR)` when a typed null is needed.

**Q8.** Changing SQL from `status = ? AND country = ?` to `country = ? AND status = ?` requires changing arguments?

Yes, when using positional parameters. Forgetting can silently run the wrong query. With named binding, key-based lookup reduces this risk.

**Q9.** Are named parameters always better for performance?

No. Spring resolves names and delegates to JDBC binding. Benchmark on your real workload, driver, and DB before drawing conclusions.

**Q10.** When an SQL query references a wrong column name, do named params turn the error into `Optional.empty()`?

No. SQL/DB errors remain data-access exceptions; return types follow query APIs and domain contracts, not placeholder syntax.

## 24. Checklist for Choosing and Maintaining Style

- [ ] Each SQL statement uses **one consistent binding style**: `?` or `:name`.
- [ ] Short 1–2 parameter queries are not forced to switch to named without clear benefit.
- [ ] Long queries, multiple same-type parameters, or repeated values have been evaluated for named parameters.
- [ ] SQL and binding values sit close together for easy diff reviews.
- [ ] Positional args follow **exact `?` order**; tests catch swapped arguments.
- [ ] Named params match `MapSqlParameterSource`/`Map`/JavaBean property names.
- [ ] Parameter names are meaningful (`:country`, `:threshold`), not positional (`:p1`, `:p2`).
- [ ] User values are always bound, never concatenated as SQL literals.
- [ ] Identifiers, sort directions, and dynamic SQL fragments come strictly from allowlists.
- [ ] `Map.of` is never used with null; typed NULLs are used where drivers require them.
- [ ] `IN (:ids)` handles empty lists, size caps, and driver testing.
- [ ] Dynamic filters define explicit absent/null/value semantics and deterministic result ordering.
- [ ] SQL `LIKE` escapes wildcards properly when literal matching is needed.
- [ ] SQL edits verify no unintended changes to row-count or transaction contracts.
- [ ] Integration tests cover happy paths, bad bindings, special inputs, and DB errors.
- [ ] Avoid mass style rewrites out of personal preference when existing code is already clear.

## 25. Conclusion

**Choosing named or positional parameters is a design decision to reduce maintenance bugs, not a choice between two different JDBC engines.** `JdbcTemplate` with `?` is concise and well suited for short, stable queries with few parameters. `NamedParameterJdbcTemplate` with `:name` shines when SQL is complex, has multiple same-type values, repeats parameters, or uses `IN` lists; Spring translates them into JDBC placeholders before execution.

Prioritize **readability, testability, and preserving exact semantics** over enforcing a single dogmatic style. Whichever style you pick, always bind values instead of concatenating SQL, guard dynamic SQL fragments, handle NULLs and empty collections explicitly, and distinguish query errors from empty results. This lays the foundation for a Spring data-access layer that scales cleanly without silent bugs as queries evolve.

## Official References

- Spring Framework — Using JdbcTemplate and NamedParameterJdbcTemplate, named binding examples: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Choosing an Approach for JDBC Database Access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html
- Spring Framework 6.1 — NamedParameterJdbcTemplate API, List expansion and JdbcTemplate delegation: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework — SQL type information, SqlParameterSource, and typed NULLs: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JdbcClient unified facade (Spring 6.1+): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
