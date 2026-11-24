# Never Concatenate User Data Directly into SQL

When building Java/Spring applications that access databases, a foundational rule is **never insert values supplied by users or external systems directly into SQL text via string concatenation, interpolation, or formatting**. Instead, keep the **SQL structure** under application control and pass **data values** through bind parameters.

In the **Named Parameters** section of Spring Framework – data-access, a fitting solution is `NamedParameterJdbcTemplate` with `:email`, `:tenantId`, or `:status` syntax. The framework parses named parameters and uses the corresponding JDBC parameter binding mechanism. The same principle applies to `JdbcTemplate` with `?` and plain `PreparedStatement`.

This lesson focuses on establishing the **SQL code / SQL data** boundary, preventing SQL injection via parameterization, handling non-bindable structural parts like `ORDER BY`, and avoiding easy-to-miss pitfalls with `LIKE`, `IN`, `NULL`, dynamic queries, and authorization.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Recognize how concatenating user input into SQL introduces **SQL injection** risks and sometimes causes syntax or data errors.
2. Explain why bind parameters protect the boundary between **values** and **SQL syntax**.
3. Write queries using `:namedParameter` and `MapSqlParameterSource`/`Map` with Spring's `NamedParameterJdbcTemplate`.
4. Use `PreparedStatement` with `?` properly when not using named parameters.
5. Handle cases requiring variable **identifiers/structure** such as `ORDER BY` column names: select exclusively from an **allowlist** of fixed fragments.
6. Distinguish SQL injection from wildcard manipulation in `LIKE` searches; apply `ESCAPE` when literal searches are required.
7. Bind `IN (:ids)` lists cleanly; handle empty lists, data types, and database limits.
8. Design tests proving input data never enters the SQL text while ensuring database errors are not masked.
9. Combine parameterization with authorization, input validation, least-privilege database accounts, and safe logging.

## 2. Where Does SQL Injection Form?

Suppose an interface accepts an email address to look up an account:

~~~text
HTTP request: /accounts?email=an@example.test
                         |
                         v
Controller receives email: String
                         |
                         v
Repository constructs SQL statement
                         |
                         v
Database executes SQL
~~~

A **wrong** way to write this is concatenating `email` directly into SQL:

~~~java
// ANTI-EXAMPLE — never use this with untrusted input.
String sql =
        "SELECT id, email FROM account WHERE email = '" + email + "'";
List<Account> accounts = jdbcTemplate.query(sql, accountRowMapper);
~~~

If `email` is `an@example.test`, the resulting SQL may look like:

~~~sql
SELECT id, email
FROM account
WHERE email = 'an@example.test';
~~~

Yet `email` is untrusted data. A user can enter a string containing single quotes, SQL expressions, comment markers, or other syntax. When concatenated, those characters become part of the **statement text** rather than merely the contents of a value. Example test input:

~~~text
x' OR '1'='1
~~~

When concatenated with the pattern above, the condition can mutate into:

~~~sql
WHERE email = 'x' OR '1'='1'
~~~

The new condition has an entirely different meaning from finding one exact email. This is a minimal example illustrating the **data–statement boundary bug**, not a catalog of every attack technique. Syntax details, quote handling, and impact vary by database/driver and query.

**Key point:** a string containing a single quote is not inherently dangerous by itself. User names, addresses, or messages can legitimately contain apostrophes. The risk arises when **the application treats data as SQL code** by constructing SQL statements directly from that value.

### SQL Injection Does Not Come Only from Search Boxes

Untrusted data can arrive from:

- Query strings, forms, JSON bodies, HTTP headers, cookies, URL paths.
- Filter values, sort fields, sort directions, ID lists, price thresholds, and status codes.
- Filenames, uploaded contents, queue messages, third-party payloads.
- Data previously stored in the database and later used to assemble SQL (*second-order SQL injection*).
- Tenant/user-editable settings or strings read from caches and integrated systems.

A value passing through multiple Java layers or already stored in the database **does not automatically become trustworthy**. What matters is whether it is permitted to alter SQL structure or is restricted to a **parameter value**.

## 3. The Right Boundary: SQL Template + Bind Values

Instead of concatenating content directly:

~~~java
String sql = "SELECT id, email FROM account WHERE email = '" + email + "'";
~~~

keep the SQL template fixed and pass the value separately:

~~~java
String sql =
        "SELECT id, email FROM account WHERE email = :email";
MapSqlParameterSource parameters =
        new MapSqlParameterSource("email", email);

List<Account> accounts =
        namedJdbc.query(sql, parameters, accountRowMapper);
~~~

This is an **illustrative snippet inside a repository that already has `namedJdbc` and `accountRowMapper`**, not a standalone Java program. Mechanically:

1. The application controls the SQL template containing the `:email` marker.
2. `MapSqlParameterSource` carries the `email` parameter value separately from the SQL text.
3. `NamedParameterJdbcTemplate` translates the named marker into the JDBC binding mechanism handled by the driver.
4. The database is asked to execute the statement with **one data value**; quotes and email contents never turn into SQL operators or clauses.

Visualize it as:

~~~text
SQL TEMPLATE:   SELECT id, email FROM account WHERE email = :email

BIND DATA:      email -> "x' OR '1'='1"

DATABASE:       Condition email = [a single bound string value]
                Not the condition email = 'x' OR ...
~~~

Binding is not just for strings: integers, dates, booleans, UUIDs, and other data types must also go through parameter binding. Concatenating numeric input into SQL simply because "it's a number" remains an error-prone habit; numeric inputs must be parsed/validated and bound with the proper type.

**Scope of protection:** prepared/named parameters prevent **bound values** from altering SQL syntax at bindable value positions. They do not protect SQL fragments that are still concatenated directly—such as table names, column names, sort clauses, or entire user-supplied SQL queries. Those require dedicated design.

## 4. Sample Schema and Query Contract

Suppose a multi-tenant application has an `account` table:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(200) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

A repository needs to:

- Look up accounts by email within an authenticated tenant.
- Filter by status, search names, and sort.
- Update display name or status without letting user data alter the SQL statement.
- Prevent switching to another tenant merely by changing a request parameter.

Safe SQL for the first operation:

~~~sql
SELECT id, email, display_name, status, created_at
FROM account
WHERE tenant_id = :tenantId
  AND email = :email;
~~~

In Java:

~~~java
var parameters = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("email", requestedEmail);
~~~

In this example, `authorizedTenantId` must be resolved from the application's verified authorization context, **not taken verbatim from a user-supplied `tenantId` field without permission checks**. Parameterization prevents SQL injection but never replaces **authorization**.

## 5. Spring NamedParameterJdbcTemplate: Basic Usage

Spring Framework provides `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate`. Named parameters use `:parameterName` syntax inside the SQL template, such as `:email`, `:id`, `:status`. The value source can be `Map<String, ?>` or a `SqlParameterSource` implementation like `MapSqlParameterSource`.

### 5.1. Bean Configuration

In a Spring application context that already defines a `DataSource` bean:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class DataAccessConfig {
    @Bean
    public NamedParameterJdbcTemplate namedJdbc(DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
~~~

This is a **Spring integration configuration class**; it requires `spring-context`, `spring-jdbc`, a working `DataSource`, and a JDBC driver. It does not create a database by itself or run via `java DataAccessConfig`.

`NamedParameterJdbcTemplate` wraps regular `JdbcTemplate`; it parses SQL with named parameters and binds values at the corresponding positions. Thus safety comes from **never inserting untrusted values into SQL text**, not from the `:` character itself if SQL strings are still concatenated elsewhere.

### 5.2. SELECT with MapSqlParameterSource

A method inside a repository injected with `NamedParameterJdbcTemplate namedJdbc`:

~~~java
public List<Account> findByEmail(long tenantId, String email) {
    String sql = """
            SELECT id, email, display_name, status, created_at
            FROM account
            WHERE tenant_id = :tenantId
              AND email = :email
            """;

    var parameters = new MapSqlParameterSource()
            .addValue("tenantId", tenantId)
            .addValue("email", email);

    return namedJdbc.query(
            sql,
            parameters,
            (rs, rowNum) -> new Account(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
            )
    );
}
~~~

This example assumes record `Account(long id, String email, String displayName)` is already declared; the method is an **integration snippet** needing a database. Crucially, `tenantId` and `email` go solely into `parameters`, never into the SQL text. `RowMapper` maps results without affecting parameter binding.

If a single row is expected by unique key, use the corresponding lookup API and handle 0/many rows per contract. Avoid catching every `DataAccessException` and returning an empty list, as that masks connection or SQL errors.

### 5.3. Using a Simple Map

When all values are non-NULL, you can use `Map.of`:

~~~java
String sql = """
        SELECT id FROM account
        WHERE tenant_id = :tenantId AND status = :status
        """;

Map<String, Object> params =
        Map.of("tenantId", tenantId, "status", status);

List<Long> ids = namedJdbc.query(
        sql,
        params,
        (rs, rowNum) -> rs.getLong("id")
);
~~~

**Note:** `Map.of(...)` in Java forbids null keys and null values. When business logic involves nullable values, use `MapSqlParameterSource` to bind NULL explicitly, registering the SQL type if needed.

## 6. Safe INSERT/UPDATE/DELETE with Named Parameters

Not only `SELECT` needs parameterization. Data-modifying statements must follow the exact same rule.

### INSERT

~~~java
String sql = """
        INSERT INTO account
            (id, tenant_id, email, display_name, status, created_at)
        VALUES
            (:id, :tenantId, :email, :displayName, :status, :createdAt)
        """;

var params = new MapSqlParameterSource()
        .addValue("id", accountId)
        .addValue("tenantId", authorizedTenantId)
        .addValue("email", requestedEmail)
        .addValue("displayName", requestedDisplayName)
        .addValue("status", "ACTIVE")
        .addValue("createdAt", createdAtTimestamp);

int inserted = namedJdbc.update(sql, params);
~~~

This is an integration snippet with existing business variables, not a standalone class. It avoids manually quoting names or emails; the JDBC driver receives values with their corresponding types. `inserted` is the affected row count per the driver's contract for this update; key constraints, uniqueness, and database permissions must still be configured separately.

### UPDATE

~~~java
String sql = """
        UPDATE account
        SET display_name = :displayName,
            status = :status
        WHERE id = :id
          AND tenant_id = :tenantId
        """;

var params = new MapSqlParameterSource()
        .addValue("displayName", requestedDisplayName)
        .addValue("status", newStatus)
        .addValue("id", accountId)
        .addValue("tenantId", authorizedTenantId);

int affected = namedJdbc.update(sql, params);
~~~

Parameter names document each value's role. If the SQL reorders `SET` and `WHERE` clauses, name-based mapping reduces positional mix-ups compared to manually counting `?` markers.

**However**, binding `newStatus` does not mean any status string is valid. Service/domain logic must still check that status belongs to the allowed set—such as `ACTIVE` or `SUSPENDED`—and that the caller is authorized to change status.

### DELETE

~~~java
String sql =
        "DELETE FROM account WHERE id = :id AND tenant_id = :tenantId";

int affected = namedJdbc.update(
        sql,
        Map.of("id", accountId, "tenantId", authorizedTenantId)
);
~~~

Never let a request specify an arbitrary tenant just because parameters are safely bound. Forgetting an authorization condition or role check is an **authorization flaw**, separate from SQL injection.

## 7. JdbcTemplate with `?` Is Also Safe When Data Is Not Concatenated

When named parameters are unnecessary, use `JdbcTemplate` and positional `?` markers:

~~~java
String sql =
        "SELECT id FROM account WHERE tenant_id = ? AND email = ?";

List<Long> ids = jdbcTemplate.query(
        sql,
        (rs, rowNum) -> rs.getLong("id"),
        authorizedTenantId,
        requestedEmail
);
~~~

Values are passed separately in exact **marker order**, never concatenated into SQL text. The same holds in plain JDBC:

~~~java
String sql =
        "SELECT id FROM account WHERE tenant_id = ? AND email = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setString(2, requestedEmail);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long accountId = rs.getLong("id");
            // Process accountId.
        }
    }
}
~~~

This JDBC snippet requires imports and an existing `DataSource`, not a complete CLI app. JDBC parameter indexes **start at 1**. Spring's `NamedParameterJdbcTemplate` saves you from manual counting, yet is not "inherently safer" than a properly used `PreparedStatement`: both rely on code **separating values from SQL**.

### Never Replace Prepared Statements with `Statement` for Dynamic Data

Anti-example:

~~~java
String sql =
        "SELECT id FROM account WHERE email = '" + requestedEmail + "'";

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(sql)) {
    // The SQL statement has been altered by requestedEmail.
}
~~~

Even if character checks were applied earlier, concatenation remains fragile as requirements change or with Unicode, quotes, and dialect differences. Never use `Statement` to interpolate data manually when binding is available.

## 8. Standalone Java 17 Example: Separating SQL Templates from Data

The program below requires no Spring or database. It demonstrates two things:

1. **Email always stays in the bind data map**, never appearing inside the SQL template.
2. **The `ORDER BY` column name must be a fixed allowlisted fragment**; invalid strings are rejected.

Save **`SafeSqlPlanDemo.java`**:

~~~java
import java.util.Map;

public class SafeSqlPlanDemo {
    record SqlPlan(String sql, Map<String, Object> parameters) {}

    static String sortColumn(String requested) {
        return switch (requested) {
            case "created" -> "created_at";
            case "email" -> "email";
            default -> throw new IllegalArgumentException("Unsupported sort field");
        };
    }

    static SqlPlan build(String userEmail, String sort, boolean ascending) {
        String sql = "SELECT id, email FROM account WHERE email = :email ORDER BY "
                + sortColumn(sort)
                + (ascending ? " ASC" : " DESC");
        return new SqlPlan(sql, Map.of("email", userEmail));
    }

    public static void main(String[] args) {
        String supplied = "x' OR '1'='1";
        SqlPlan plan = build(supplied, "created", false);
        System.out.println("SQL: " + plan.sql());
        System.out.println("Bound email: " + plan.parameters().get("email"));
        System.out.println("Input inside SQL: " + plan.sql().contains(supplied));
        try {
            build("a@example.test", "email; DROP TABLE account", true);
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid sort rejected");
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 SafeSqlPlanDemo.java
java SafeSqlPlanDemo
~~~

Exact stdout of the example:

~~~text
SQL: SELECT id, email FROM account WHERE email = :email ORDER BY created_at DESC
Bound email: x' OR '1'='1
Input inside SQL: false
Invalid sort rejected
~~~

**Transparent scope:** `SqlPlan` here is solely a Java record representing the **intent** of pairing a trusted template with bound values; the program **does not call JDBC or Spring**, opens no connection, and does not prove the SQL runs against a specific database. In a real application, pass `plan.sql()` and `plan.parameters()` to a parameterized API such as `NamedParameterJdbcTemplate.query(...)`. The program verifies **keeping input out of SQL text** and **rejecting arbitrary column names** right at the statement-building layer.

Do not treat `plan.sql().contains(input) == false` as a general proof of system security: data may be concatenated from other sources, other queries may still be vulnerable, and authorization remains independent.

## 9. Identifiers and SQL Structure: Parameters Do Not Replace Table/Column Names

This is the easiest point to misunderstand when learning named parameters. `:value` represents a **data value**, not a slot to inject arbitrary SQL fragments.

**Right:**

~~~sql
SELECT id, email FROM account WHERE email = :email;
~~~

**Misintended:**

~~~sql
SELECT id, email FROM account ORDER BY :sortColumn;
~~~

In the second statement, `:sortColumn` is a **bound value**, not interpreted by the database as a column identifier. On some dialects it may be syntactically valid yet sort by a constant expression, giving unintended results; on others it is rejected. It is not a portable way to choose columns dynamically.

Likewise, never bind table names in `FROM :tableName`, column names in `SELECT :columnName` expecting identifiers, or an entire `WHERE :filterSql` clause. Binding is built for **data values**, not SQL code.

### Right Approach: Mapping Business Keys to Fixed Fragments

Suppose a request sends `sort=created` or `sort=email`. Accept only these two names:

~~~java
private static String sortColumn(String requested) {
    return switch (requested) {
        case "created" -> "created_at";
        case "email" -> "email";
        default -> throw new IllegalArgumentException("Invalid sort field");
    };
}
~~~

Then:

~~~java
String orderColumn = sortColumn(requestedSort);
String direction = ascending ? "ASC" : "DESC";

String sql =
        "SELECT id, email FROM account WHERE tenant_id = :tenantId "
      + "ORDER BY " + orderColumn + " " + direction + ", id ASC";
~~~

Here there is **SQL string concatenation**, yet both concatenated fragments are **fixed values chosen by the application** from an allowlist—not untrusted raw text. This covers cases where SQL structure must vary flexibly while keeping the source and range of every fragment strictly controlled. The criterion is not "ban every `+` on strings", but **never concatenate untrusted data where it can alter SQL syntax**.

When there are many options, use an enum with a fixed mapping. Never assume checking `sort.matches("[a-zA-Z_]+")` is enough: an alphabetic string can still name a sensitive column that must not be exposed, or alter query behavior. A **business allowlist** controls both security and the API contract.

### Sort Direction, LIMIT, and OFFSET

- Direction is also an **SQL keyword**, so select from fixed `"ASC"` or `"DESC"` via a parsed boolean/enum rather than inserting raw `direction` from a request.
- `LIMIT`/`OFFSET` vary in syntax and parameter-binding support across databases/drivers; in dialects supporting `LIMIT :limit OFFSET :offset`, parse numeric values, enforce reasonable bounds, and bind them.
- Regardless of whether SQL supports binding paging values, always cap `pageSize` to prevent resource-exhausting requests. Preventing SQL injection does not replace load control.

## 10. Safe Spring Repository Example with Filter + Sort

The pattern below combines bound values and identifier allowlists. It assumes the `account` schema above, an environment supporting `LIKE ... ESCAPE '!'`, and a configured `NamedParameterJdbcTemplate` bean.

~~~java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountSearchRepository {
    public record AccountView(long id, String email, Instant createdAt) {}

    private final NamedParameterJdbcTemplate jdbc;

    public AccountSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String sortColumn(String requested) {
        return switch (requested) {
            case "created" -> "created_at";
            case "email" -> "email";
            default -> throw new IllegalArgumentException("Unknown sort field");
        };
    }

    private static String escapeLikeLiteral(String raw) {
        Objects.requireNonNull(raw);
        return raw.replace("!", "!!")
                  .replace("%", "!%")
                  .replace("_", "!_");
    }

    public List<AccountView> search(
            long authorizedTenantId,
            String requestedEmailPart,
            String requestedSort,
            boolean ascending) {

        String column = sortColumn(requestedSort);
        String direction = ascending ? "ASC" : "DESC";

        String sql = """
                SELECT id, email, created_at
                FROM account
                WHERE tenant_id = :tenantId
                  AND LOWER(email) LIKE LOWER(:pattern) ESCAPE '!'
                ORDER BY """ + column + " " + direction + ", id ASC";

        var params = new MapSqlParameterSource()
                .addValue("tenantId", authorizedTenantId)
                .addValue("pattern", "%" +
                        escapeLikeLiteral(requestedEmailPart) + "%");

        return jdbc.query(sql, params, (rs, rowNum) ->
                new AccountView(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getTimestamp("created_at").toInstant()
                )
        );
    }
}
~~~

This is a **Spring integration class**, not a standalone runnable program. Running it requires Spring JDBC, the matching schema/database, and a `NamedParameterJdbcTemplate` bean. `Timestamp.toInstant()` assumes `created_at NOT NULL`. SQL `ESCAPE '!'` uses common SQL syntax, though it must be tested against your target dialect.

Why does this avoid concatenating user data into SQL?

- `authorizedTenantId` goes into `:tenantId` as a data value.
- Search text goes into `:pattern`, transformed beforehand into a literal search pattern.
- `requestedSort` is only used **after mapping** to the two fixed identifiers `created_at` or `email`.
- `ascending` picks solely between two fixed keywords.
- No path puts raw email, search text, or sort field verbatim into SQL structure.

Even so, the repository does not authenticate tenant permissions by itself: callers must pass `authorizedTenantId` from a real authentication/authorization context. Furthermore, `requestedEmailPart` could be huge; the API layer should cap length, normalize search behavior, and protect the database from expensive queries.

## 11. LIKE: Parameter Binding Prevents Injection, Not Wildcard Meaning

An easily overlooked pitfall is:

~~~sql
SELECT id FROM account WHERE display_name LIKE :pattern;
~~~

If code binds:

~~~java
params.addValue("pattern", "%" + userSearch + "%");
~~~

SQL injection is prevented **at the bind position**, yet `%` and `_` inside `userSearch` still act as **`LIKE` wildcards**:

- `%` typically matches any character sequence, including empty.
- `_` typically matches any single character.
- Escape syntax depends on the database dialect.

If the UI **intentionally supports wildcards**, this behavior may be desired. If users expect to match **literal** `a_b` or `50%`, escape LIKE metacharacters using database syntax.

Example choosing `!` as the escape character:

~~~sql
SELECT id FROM account
WHERE display_name LIKE :pattern ESCAPE '!';
~~~

Java:

~~~java
private static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

String pattern = "%" + escapeLikeLiteral(userSearch) + "%";
var params = new MapSqlParameterSource("pattern", pattern);
~~~

With `userSearch = "50%"`, `pattern` becomes `%50!%%`: the outer two `%` act as substring wildcards, while `!%` inside represents **a literal percent sign**. `!` itself is escaped to `!!` first. Calling `replace` handles **LIKE pattern semantics**, not parameter binding. The final pattern must still be bound via `:pattern`.

**Never "strip all special characters" to prevent injection.** Names with apostrophes, text with percent signs, or Unicode characters are valid data. Parameterization protects the code/data boundary, while validation and LIKE escaping enforce distinct business rules.

## 12. IN (:ids): A List of Values Is Not an SQL String

With Spring's `NamedParameterJdbcTemplate`, you can bind a collection to generate positional placeholders for an `IN` list:

~~~java
String sql = """
        SELECT id, email
        FROM account
        WHERE tenant_id = :tenantId
          AND id IN (:ids)
        """;

List<Long> ids = List.of(10L, 20L, 30L);

var params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("ids", ids);

List<Long> selected = namedJdbc.query(
        sql, params, (rs, rowNum) -> rs.getLong("id")
);
~~~

Spring expands the collection into matching bind markers and binds **each element as data**. Never build `"10,20,30"` and concatenate it into `IN (...)`. Never trust a user-supplied CSV string as an SQL fragment. When receiving `ids` over HTTP, parse into `List<Long>` with count limits, value-range checks, and per-record access checks.

### Empty Lists

An empty list must not be treated like a one-element list. SQL `IN ()` can be invalid or behave differently across dialects. Define business semantics upfront:

~~~java
if (ids.isEmpty()) {
    return List.of();  // When "no IDs" means "no rows".
}
~~~

This snippet belongs to a method returning `List<?>`, illustrating a business branch. In real systems, also bound list sizes: databases/drivers impose limits on bind parameters or SQL length; tens of thousands of IDs may require batching, temporary tables, or another DB-appropriate approach.

### Never Insert a User-Supplied SQL List

Anti-example:

~~~java
String sql = "SELECT id FROM account WHERE id IN (" + rawIdsCsv + ")";
~~~

Even when the input usually contains only digits, it is still injected into SQL text. The right way is parsing into typed values and binding each element or using Spring's collection binding support.

## 13. SQL NULL and Parameter Types

When an input value is Java `null`, you cannot use `Map.of("note", null)` because Java `Map.of` rejects null. `MapSqlParameterSource` can represent NULL and register its SQL type:

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
        .addValue("id", accountId)
        .addValue("note", optionalNote, Types.VARCHAR);

String sql =
        "UPDATE account_note SET note = :note WHERE account_id = :id";

int affected = namedJdbc.update(sql, params);
~~~

Assumes table `account_note` and the variables already exist. `Types.VARCHAR` declares the SQL type of `note`; providing the type can matter for certain JDBC drivers or SQL statements with NULL parameters.

**NULL is also a bound value** in the SQL contract. Never drop the marker and concatenate `"NULL"` as text to handle one case unless intentionally switching to a separate trusted SQL template. For filtering, `column = NULL` never matches SQL NULL rows under standard SQL logic; use `IS NULL` or design conditions properly:

~~~sql
-- Find rows where note is actually SQL NULL:
SELECT account_id FROM account_note WHERE note IS NULL;
~~~

Not every nullable filter can be written as `column = :value` with `value = null`. That is an **SQL semantics issue**, not unsafe binding.

## 14. Dynamic Queries: Combine Trusted Fragments Instead of Raw Input

Applications sometimes need to add or omit search filters. The wrong approach is letting the client pass SQL snippets:

~~~java
// ANTI-EXAMPLE:
String sql = "SELECT id FROM account WHERE " + userSuppliedWhereClause;
~~~

With that design, user input directly controls SQL syntax. Instead, toggle **application-defined fragments** and bind values:

~~~java
StringBuilder sql = new StringBuilder(
        "SELECT id FROM account WHERE tenant_id = :tenantId");

var params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId);

if (requestedStatus != null) {
    sql.append(" AND status = :status");
    params.addValue("status", requestedStatus);
}

if (minimumId != null) {
    sql.append(" AND id >= :minimumId");
    params.addValue("minimumId", minimumId);
}

List<Long> ids = namedJdbc.query(
        sql.toString(), params,
        (rs, rowNum) -> rs.getLong("id")
);
~~~

This is an integration snippet requiring `requestedStatus`, `minimumId`, and related beans/data to be declared beforehand. Only **developer-controlled SQL literals** are appended. Data stays inside `params`. When adding conditions, ensure every marker has a matching value and critical fixed filters like `tenant_id` are never bypassed.

### Never Use "Alphanumeric-Only" as a Substitute for Binding

An input validation rule such as `[a-zA-Z0-9]+` may fit a business code with a restricted format. Yet it is **not** a replacement for SQL parameters because:

- Many valid inputs contain characters outside that pattern.
- Schema/dialect changes or SQL assembly changes can invalidate the assumption.
- It does not solve authorization, cardinality limits, or column identifiers.

Use validation to define **domain-valid data** (length, format, allowed statuses, quantity bounds). Use parameterization to control **how data enters SQL**.

## 15. Query Builders, JPA, and ORMs: Keep the Same Rule

This lesson focuses on Spring JDBC, yet the principle carries over to other abstractions:

- With JPQL/HQL or native queries in JPA, use the query API's **parameter binding**, never string concatenation from input.
- With Spring Data repositories containing `:email` queries or derived query methods, verify parameters are bound and no raw SQL/JPQL fragments are built from user input.
- With query DSLs or ORMs offering expression trees, use APIs for **parameter values**, avoiding "raw SQL"/"literal fragment" escape hatches fed by untrusted input.
- Dynamic identifiers must still come from controlled configuration; an ORM does not automatically sanitize functions that inject raw SQL fragments.

JPA example (integration snippet; `entityManager` and `AccountEntity` are configured):

~~~java
var query = entityManager.createQuery(
        "SELECT a FROM AccountEntity a WHERE a.email = :email",
        AccountEntity.class
);
query.setParameter("email", requestedEmail);
List<AccountEntity> result = query.getResultList();
~~~

Never change it to:

~~~java
// ANTI-EXAMPLE:
String jpql = "SELECT a FROM AccountEntity a WHERE a.email = '"
              + requestedEmail + "'";
~~~

An ORM cannot fix the flaw if a developer injects untrusted input into the query string before it is parsed.

## 16. JdbcClient with Named Parameters (Spring Framework 6.1+)

Spring Framework 6.1 introduced `JdbcClient` as a fluent interface supporting both positional and named parameters. Illustrative snippet in an app with a `JdbcClient jdbcClient` bean:

~~~java
List<Long> ids = jdbcClient.sql("""
        SELECT id
        FROM account
        WHERE tenant_id = :tenantId
          AND email = :email
        """)
        .param("tenantId", authorizedTenantId)
        .param("email", requestedEmail)
        .query((rs, rowNum) -> rs.getLong("id"))
        .list();
~~~

This is an **alternative API style** for binding values, not a change to the SQL injection threat model. SQL must remain a trusted template; `param("email", requestedEmail)` keeps the email strictly in the data slot. Across projects on different Spring versions, you will see either `NamedParameterJdbcTemplate` or `JdbcClient`; check your dependency version before applying snippets.

## 17. Avoid "Roll-Your-Own Escaping" Approaches

### Concatenating After Doubling Quotes Is Fragile

Anti-example:

~~~java
// ANTI-EXAMPLE: never treat manual quote replacement as general protection.
String escaped = requestedEmail.replace("'", "''");
String sql = "SELECT id FROM account WHERE email = '" + escaped + "'";
~~~

Even if doubling single quotes fits one narrow SQL scenario, this approach forces the application to account for all escaping, character encodings, dialects, type conversions, literal rules, and SQL contexts. Rules for a **string literal** do not work for **identifiers**, **numbers**, **JSON paths**, **ORDER BY**, or other SQL fragments.

**Durable solution:** keep SQL templates fixed and bind values through the driver/framework. Never invent an "anti-SQL-injection function" that concatenates after replacing a few characters. Nor should you mistake HTML escaping, URL encoding, or JSON escaping for SQL escaping: every layer has its own grammar.

### Be Careful Claiming "We Used PreparedStatement"

A program can use `PreparedStatement` yet **still construct SQL via string concatenation before preparing**:

~~~java
// ANTI-EXAMPLE: PreparedStatement cannot fix SQL already concatenated unsafely.
String sql =
        "SELECT id FROM account WHERE email = '" + requestedEmail + "'";
PreparedStatement ps = connection.prepareStatement(sql);
~~~

Using the right Java class is not enough; the real question is: **did input enter the SQL text or only the setter/bind map?** Once input is concatenated into the SQL string, calling `prepareStatement(sql)` does not magically turn it into a parameter.

### Be Careful Claiming "We Used Named Parameters"

Still vulnerable example:

~~~java
// ANTI-EXAMPLE: status is bound, yet email is still concatenated.
String sql = "SELECT id FROM account WHERE email = '"
           + requestedEmail + "' AND status = :status";
namedJdbc.query(sql, Map.of("status", requestedStatus), rowMapper);
~~~

Protecting **one parameter** does not automatically protect **the entire SQL statement**. Every input reaching the query must be checked along its own data path.

## 18. Why Parameterization Doesn't Solve Every Security Problem

**SQL injection prevention** is a critical boundary, yet should not be confused with an endpoint being "completely secure":

| Risk | What Parameterization Helps With | What Else Is Needed |
| --- | --- | --- |
| Input alters SQL syntax at value slot | Prevents values from becoming SQL code | Never concatenate raw input elsewhere |
| User reads another tenant's data | Does not decide read permissions | Authorization and trusted tenant constraints |
| User asks to sort by sensitive column | Cannot bind identifiers | Application-level field/column allowlist |
| Query loads too many rows | Does not bound cardinality | Pagination, quotas, query/timeouts, indexes |
| LIKE wildcard triggers broad scan | Wildcards keep LIKE semantics | Escape literals, cap patterns, design search |
| User picks dynamic table name | Binding never turns text into identifier | Fixed mapping or separate query templates |
| DB account has excessive privileges | Does not reduce DB privileges | Least-privilege roles and secret management |
| Sensitive data in logs | Does not redact logs | Redaction/masking, log access control, retention |
| Business logic updates wrong rows | Does not fix business conditions | Tests, authorization, exact WHERE/transactions |

For example, `SELECT * FROM account WHERE tenant_id = :tenantId` is SQL-injection-safe at the value slot. Yet if `tenantId` is taken straight from the request body of a user lacking access to that tenant, the endpoint still **leaks data due to missing authorization**. That is an authorization bug, not SQL injection, and must be handled separately.

## 19. Logging and Error Handling Without Leaking Data

When diagnosing queries, log the **SQL template** and necessary technical context (service, trace ID, statement type, duration, row count, statement name) as permitted by policy. Avoid logging raw bound values, especially passwords, tokens, emails, phone numbers, or customer records.

Instead of logging full SQL with interpolated user inputs, log in this style:

~~~text
statement=account.findByEmail
sql_template=SELECT id FROM account WHERE tenant_id = :tenantId AND email = :email
parameters={tenantId:[authorized], email:[redacted]}
duration_ms=14
rows=1
~~~

This is a **simulated log**, not a required Spring format. Never mask a value in one log field while accidentally including the plaintext value inside exception messages or tracing tags.

If the database returns a syntax or binding error, never "fix" it by temporarily concatenating input directly into SQL to test in production. Inspect parameter names, map keys, SQL dialect, data types, and the query in a test environment. Database errors should be handled by layer; never catch all exceptions and return "not found" to hide failures.

## 20. An Immediately Actionable Code Review Method

When reviewing a Spring JDBC repository, look for these signs:

1. **Is SQL text concatenated from request variables?** Watch especially for `"... WHERE " + userFilter`, `"... ORDER BY " + sort`, `String.format("... %s ...", input)`.
2. **Do all value conditions pass input through `:name` or `?`?**
3. **Are dynamic identifiers/keywords mapped via a fixed allowlist?**
4. **Do `IN` lists use collection binding rather than CSV concatenation?** Are empty lists and size caps handled?
5. **Do `LIKE` queries distinguish intentional wildcards from literal search?**
6. **Are nullable values bound with proper types?** Never silently replaced with hand-built SQL strings.
7. **Do all access-control filters (tenant, owner, role) come from trusted sources and appear in the query?**
8. **Does logging expose sensitive bound values?**
9. **Do tests verify behavior with quotes, wildcards, Unicode, and long strings?**
10. **Are there raw SQL escape hatches in ORMs, stored procedures, or query builders receiving user input?**

If you spot direct data concatenation, inspect the **position** where it occurs. For value positions, switch to bind parameters. For genuinely dynamic structural parts, design an allowlist or discrete query variants and bind all remaining values. Never just drop in a generic escape helper.

## 21. Testing Against SQL Concatenation Bugs

A useful test suite verifies both **SQL/data separation** and **correct functional behavior**.

| Case | What to Assert |
| --- | --- |
| Normal email | Exact row matching email and tenant |
| Email containing single quote | Does not break syntax; matched as a literal value |
| Email resembling an SQL condition | Does not cause the query to return extra rows |
| Unicode email | Bound and compared per DB encoding/collation |
| `%` and `_` in literal search | Not treated as wildcards when business requires literal match |
| Valid sort field | Picks exact allowlisted column and fixed sort direction |
| Invalid sort field | Rejected before building SQL with an identifier |
| Empty ID list | Returns empty or follows contract, never emits invalid `IN ()` |
| Large ID list | Enforces cap or handles per DB strategy |
| Nullable value | Uses `MapSqlParameterSource`/SQL type if needed |
| Spoofed tenant ID from request | Cannot switch to an unauthorized tenant |
| UPDATE/DELETE with cross-tenant ID | Does not modify another tenant's data |
| SQL exception | Not swallowed and turned into fake business results |

### Integration Tests with a Database

Tests should run the repository against an appropriate database/driver (such as Testcontainers or a project-managed test DB) with at least two clearly distinguishable records. Pass an SQL-like payload into `:email` and assert the query **returns no rows beyond an exact literal match**—do not merely check "no exception thrown". Also confirm the schema stays intact, no unexpected updates occur, and authorization holds.

A test can use real email data containing an apostrophe to prove binding preserves syntax. For columns constrained by email format rules, use `display_name` or `search_term` for exotic test payloads so tests do not accidentally fail unrelated validation constraints.

### Unit Tests for Query Planners

For code like `SafeSqlPlanDemo`, check:

- With the same `sort=created`, SQL text stays identical regardless of email value.
- `parameters.get("email")` preserves input verbatim.
- Invalid sort arguments are rejected.
- Direction only produces fixed `ASC` or `DESC`.
- No path concatenates raw user input into SQL text.

Unit tests do not replace integration tests: they prove the query **was assembled as intended**, not that Spring/driver/database binding succeeds at runtime or that permissions are enforced.

## 22. Self-Check Questions and Answers

**Q1.** Why is concatenating `requestedEmail` into `WHERE email = '...'` more dangerous than binding `:email`?  
**A:** Because string concatenation turns data into part of the SQL syntax. Binding keeps the email in a value slot so its contents cannot become SQL clauses or operators.

**Q2.** Can you pass `sortColumn = "created_at"` into `ORDER BY :sortColumn` to pick a column?  
**A:** No. Bind parameters represent values, not identifiers. Pick SQL column names via an allowlist of fixed fragments, and concatenate only trusted fragments.

**Q3.** If `:email` appears twice in an SQL template, do you need to concatenate strings twice?  
**A:** No. Supply the value once in the parameter source; `NamedParameterJdbcTemplate` maps that value to each corresponding JDBC position at execution time.

**Q4.** Once `LIKE :pattern` uses parameter binding, does `%` typed by the user automatically act as a literal character?  
**A:** No. Binding stops SQL injection at the value slot, yet `%` and `_` remain LIKE wildcards. If the UI needs literal search, escape according to dialect rules and bind the processed pattern.

**Q5.** How should an API-supplied list of IDs be handled with `IN (...)`?  
**A:** Parse into a typed list with validation, authorization, and size caps; use `IN (:ids)` with Spring collection binding, handling empty lists per contract. Never concatenate raw CSV into SQL.

**Q6.** Is calling `connection.prepareStatement(sql)` safe if `sql` was built beforehand via `"..." + userInput`?  
**A:** No. `PreparedStatement` cannot restore the value boundary once input is already concatenated into the SQL text. You must use markers and setters or a parameter source.

**Q7.** If a user sends `tenantId=999` and `tenantId` is safely bound, can the application skip authorization checks?  
**A:** No. Binding prevents SQL injection, not unauthorized access to tenant 999. The `tenantId` used in queries should come from a verified authorization context.

**Q8.** Why is `Map.of("note", null)` unsuitable for a nullable SQL column?  
**A:** Because Java's `Map.of` rejects null. Use `MapSqlParameterSource` and, when needed, register an SQL type like `Types.VARCHAR`.

**Q9.** A query binds `:status` while still concatenating `requestedEmail` into SQL. Is the query fully protected against injection?  
**A:** No. Every user-input path that can affect SQL must be handled properly; binding one parameter does not protect parts of the query built by direct concatenation.

**Q10.** Should you strip all apostrophes, percent signs, or Unicode characters from data to prevent SQL injection?  
**A:** No. Use parameter binding for values, domain validation for business rules, and dedicated escaping for semantics like literal `LIKE` searches. Never treat input sanitization as an excuse to build SQL by concatenation.

## 23. Principle Summary

**Never concatenate user data directly into SQL.** With Spring JDBC, use `NamedParameterJdbcTemplate` and `:namedParameter` with `MapSqlParameterSource` or `Map` for values; or use `JdbcTemplate`/`PreparedStatement` with `?`. The SQL template stays under application control; input values flow through binding.

When structural parts genuinely vary, such as `ORDER BY`, select fixed SQL fragments solely from an **allowlist**; never accept raw column names, table names, or whole `WHERE` clauses from clients. For `LIKE`, `IN`, `NULL`, and paging, combine proper binding with correct SQL semantics and database limits. Finally, enforce authorization, least-privilege DB accounts, resource caps, safe logging, and testing on a real database.

### Official References

- [Spring Framework — JDBC Core: NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): using SQL with named parameters, `MapSqlParameterSource`, `Map`, and `JdbcClient`.
- [Spring Framework — Common Problems with Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): declaring SQL types, handling NULL parameters, and data binding.
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): query/update contracts using named parameters.
- [Spring Framework — MapSqlParameterSource API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html): attaching values and SQL types per parameter.
- [Java SE 17 — PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): positional JDBC setters.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries, identifier allowlists, least privilege, and anti-patterns to avoid.