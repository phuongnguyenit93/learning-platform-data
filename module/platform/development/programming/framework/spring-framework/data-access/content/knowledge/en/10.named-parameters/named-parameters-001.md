# NamedParameterJdbcTemplate Adds Named Parameters on Top of Spring JDBC

When using traditional `JdbcTemplate`, SQL typically marks parameters with `?` and the code must supply values in the **exact positional order**. This is completely valid for short SQL statements, but becomes error-prone to read when a query has many conditions, the same value is used multiple times, or columns are added or removed during maintenance.

Spring JDBC's `NamedParameterJdbcTemplate` lets you use **named placeholders** such as `:customerId`, `:tenantId`, or `:status`. Code passes a table of values by name, making the meaning of each argument explicit. Under the hood, Spring still uses JDBC `PreparedStatement`, converts named placeholders into positional placeholders, and binds the corresponding values. It is **not an ORM, not a free-form SQL string concatenation tool, and does not replace transaction management**.

This lesson explains the mechanism, `Map`/`SqlParameterSource` parameter sources, CRUD examples, `IN (:ids)`, SQL types/`NULL`, batch updates, security constraints, common mistakes, and how it integrates with Spring transactions. The final section includes a runnable **Java 17+ / Spring JDBC 6.1.14 / H2** program using Maven.

## 1. The Problem with Positional `?` Parameters

Suppose a query needs to find records by tenant, status, and timestamp:

```java
// Illustrates integration with a configured JdbcTemplate.
List<OrderRow> orders = jdbc.query(
    """
    SELECT id, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND state = ?
      AND created_at >= ?
    ORDER BY id
    """,
    orderMapper,
    tenantId, state, cutoff
);
```

This SQL and code use `?` markers in order **first → second → third**. If a maintainer swaps two conditions but forgets to swap the argument order, the query can return wrong data or trigger a type error that the compiler cannot catch. Having parameters that are all Strings or numbers can also make such bugs harder to spot.

Using names makes the relationship more transparent:

```java
String sql = """
    SELECT id, total_amount
    FROM orders
    WHERE tenant_id = :tenantId
      AND state = :state
      AND created_at >= :cutoff
    ORDER BY id
    """;

Map<String, Object> params = Map.of(
    "tenantId", tenantId,
    "state", state,
    "cutoff", cutoff
);

List<OrderRow> orders = namedJdbc.query(sql, params, orderMapper);
```

Both snippets are **illustrative code**, requiring existing beans, `OrderRow`, mapper, table, and variables. `Map.of` does not allow `null` keys or values; when data can be null, use `MapSqlParameterSource` as shown later.

Changing the order of SQL conditions does not force changing the order of entries in the `Map`: the `:tenantId` placeholder always reads its value from the `"tenantId"` key. If a name in the SQL has no corresponding key, Spring throws an error instead of silently using an adjacent value.

### When Should You Use It?

- SQL statements with **many parameters** or parameters easily confused due to having the same type.
- A parameter appearing **multiple times** in an SQL statement.
- Well-structured filters using a JavaBean or `MapSqlParameterSource`.
- Needing `IN` with a variable-length list of elements.
- Needing batch updates for multiple datasets with the same statement schema.
- Wanting SQL to remain explicit SQL without switching to an ORM.

Very short SQL with a single `?` can still make sense with `JdbcTemplate`. `NamedParameterJdbcTemplate` is a **way to express parameters**, not a mandatory replacement for every `JdbcTemplate` API.

## 2. Role and How It Works

`NamedParameterJdbcTemplate` resides in the package:

```java
org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
```

It implements the `NamedParameterJdbcOperations` interface, wraps a regular `JdbcTemplate`, and delegates to that template after processing named placeholders.

```text
Application / Repository
     |
     | SQL: WHERE tenant_id = :tenantId AND status = :status
     | params: {"tenantId": 10, "status": "ACTIVE"}
     v
NamedParameterJdbcTemplate
     |
     | parse SQL, locate and order named placeholders
     | replace placeholders with JDBC ? markers
     v
Prepared SQL:
WHERE tenant_id = ? AND status = ?
     |
     | bind 10 and "ACTIVE" in order of occurrence
     v
JdbcTemplate / PreparedStatement
     |
     v
JDBC driver -> Database -> ResultSet / update count
     |
     v
RowMapper, DataAccessException, transaction-aware resource handling
```

**Core point:** `:status` is not sent as a new "SQL variable" understood natively by the database. Spring processes it on the application side and then uses `PreparedStatement` to pass the data. This keeps values **separate from the SQL structure**, helping prevent SQL injection when used properly.

### One Name Repeated in the Same SQL

```sql
SELECT id, full_name
FROM account
WHERE full_name = :term
   OR status = :term;
```

You only need to pass the `term` value **once**:

```java
Map<String, Object> params = Map.of("term", "ACTIVE");
```

Spring expands this to the equivalent:

```sql
SELECT id, full_name
FROM account
WHERE full_name = ?
   OR status = ?;
```

The same value `"ACTIVE"` is bound to both positions. Repeating the same name means **repeating the same parameter**, not creating new names like `term1`, `term2`. If business logic requires two different values, use two distinct names.

### SQL Must Still Follow Database Syntax

The `:name` syntax is solely a Spring placeholder. Operators, functions, quotes, `JOIN` order, `GROUP BY`, `ORDER BY`, `LIMIT/FETCH` clauses, and data types must still comply with the database's SQL dialect. Named parameters do not automatically make invalid SQL valid.

Spring parses SQL and caches parse metadata (the template has a configurable cache limit), but you should not treat this cache as a query-result cache or a guarantee of reusing a single `PreparedStatement` forever. SQL with an `IN` list of varying element counts can generate different numbers of `?` markers.

## 3. Creating and Owning the Template in Spring

It can be instantiated from a `DataSource`:

```java
DataSource dataSource = /* application DataSource bean */;
NamedParameterJdbcTemplate namedJdbc =
    new NamedParameterJdbcTemplate(dataSource);
```

This is an illustration, not standalone runnable code. The `DataSource` must exist and be configured with the appropriate driver, URL, and credentials.

In a Spring application, the template is typically created as a shared **bean** and injected into repositories:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class JdbcConfig {
    @Bean
    NamedParameterJdbcTemplate namedParameterJdbcTemplate(DataSource ds) {
        return new NamedParameterJdbcTemplate(ds);
    }
}
```

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public AccountRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
```

These two classes are **Spring integration** examples, requiring `DataSource` configuration and actual repository operations.

Once configured, `NamedParameterJdbcTemplate` can be shared across threads; **do not store a shared mutable parameter set as a field** and keep adding values to it per request. Instead, each operation should create its own `Map` or `SqlParameterSource`. The `DataSource`/pool normally has application-wide lifecycle; the template should not be created and have its pool closed after each query.

### Accessing the Traditional `JdbcTemplate` API

If you need an API only available on `JdbcOperations`, you can call:

```java
org.springframework.jdbc.core.JdbcOperations jdbc =
    namedJdbc.getJdbcOperations();
```

This returns the underlying JDBC template interface, **without creating a new transaction manager**. You can use both approaches in the same repository when needed, as long as they share the same data source and appropriate transaction mechanism.

## 4. Supplying Values with `Map<String, ?>`

The quickest way is mapping **parameter names without the `:` prefix** to values:

```java
String sql = """
    SELECT id, full_name
    FROM account
    WHERE tenant_id = :tenantId
      AND status = :status
    ORDER BY id
    """;

Map<String, ?> params = Map.of(
    "tenantId", 10L,
    "status", "ACTIVE"
);

List<AccountView> result = namedJdbc.query(
    sql,
    params,
    (rs, rowNum) -> new AccountView(
        rs.getLong("id"),
        rs.getString("full_name")
    )
);
```

This is an integration snippet; `AccountView` is assumed to be an application record/class. Note that column names in `ResultSet` and SQL placeholder names are **two independent mechanisms**. `RowMapper` determines how result rows map to objects; `NamedParameterJdbcTemplate` only binds inputs.

**Rules for `Map`:**

1. Keys use `"tenantId"`, not `":tenantId"`.
2. Placeholder names and keys must match exactly. `:tenantId` does not automatically match `"tenant_id"`.
3. Missing key → exception; using a misspelled key is not the same as binding SQL `NULL`.
4. `Map.of(...)` since Java 9 does not accept `null` values; `Map.of("x", null)` throws `NullPointerException` immediately upon map creation.
5. Queries should use bound parameters rather than concatenating user values directly into the SQL string.

`Map` works well when there are few values, none are null, and explicit SQL types are unnecessary. When you need nulls, JDBC types, or a flexible builder, use `MapSqlParameterSource`.

## 5. `SqlParameterSource` and `MapSqlParameterSource`

`SqlParameterSource` is the common interface Spring uses to retrieve values and, when available, **JDBC SQL type** metadata for each parameter. `MapSqlParameterSource` is the practical implementation for adding parameters by name:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource args = new MapSqlParameterSource()
    .addValue("tenantId", 10L)
    .addValue("status", "ACTIVE")
    .addValue("middleName", null, Types.VARCHAR);
```

In this example, `middleName` is intentionally SQL `NULL` with type `VARCHAR`. Each `addValue` returns the `MapSqlParameterSource` instance itself, allowing method chaining in a single expression.

Applied to a write statement:

```java
String sql = """
    INSERT INTO customer(tenant_id, full_name, middle_name)
    VALUES (:tenantId, :fullName, :middleName)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", tenantId)
    .addValue("fullName", fullName)
    .addValue("middleName", middleName, java.sql.Types.VARCHAR);

int inserted = namedJdbc.update(sql, params);
```

This integration snippet requires the `customer` table and input variables, and is not a standalone runnable program. `update` returns the **number of affected rows** (typically 1 if one row is inserted successfully), not the created entity, and does not automatically return generated keys.

### Why Specify the SQL Type of `null`?

A JDBC driver may be unable to determine the type of a bound `null` value, especially with parameters having specialized semantics or complex SQL. `MapSqlParameterSource.addValue(name, null, Types.VARCHAR)` provides the type so the driver can bind more reliably. For non-null values, Spring and the driver can usually infer it, though some vendor-specific types still require an explicit type.

Another option is `registerSqlType("middleName", Types.VARCHAR)` on an appropriate `SqlParameterSource`; using `addValue` with a type is usually more direct when building a fresh parameter set.

### Parameter Source Lifecycle

`MapSqlParameterSource` has mutable state. You should construct it **per repository call**, rather than sharing a single instance across all requests. This prevents race conditions or values from an earlier request leaking into a later one. For immutable parameters, `Map.of` or an immutable bean wrapped in an appropriate parameter source is also an option.

## 6. `BeanPropertySqlParameterSource`: Reading Values from a JavaBean

When placeholders correspond to properties of a JavaBean, you do not need to call `addValue` manually for each field. `BeanPropertySqlParameterSource` accesses **readable properties** via getters.

Example class:

```java
public class AccountFilter {
    private final long tenantId;
    private final String status;

    public AccountFilter(long tenantId, String status) {
        this.tenantId = tenantId;
        this.status = status;
    }

    public long getTenantId() {
        return tenantId;
    }

    public String getStatus() {
        return status;
    }
}
```

This is a standalone class declaration in Java; when saved separately, name the file `AccountFilter.java`.

Using it as a parameter source:

```java
String sql = """
    SELECT COUNT(*)
    FROM account
    WHERE tenant_id = :tenantId
      AND status = :status
    """;

SqlParameterSource params =
    new BeanPropertySqlParameterSource(
        new AccountFilter(10L, "ACTIVE")
    );

Long count = namedJdbc.queryForObject(sql, params, Long.class);
```

This is an integration snippet; it requires importing `SqlParameterSource`, the `namedJdbc` bean, and the `account` table. The name `:tenantId` matches the **JavaBeans property name** from `getTenantId()`, not the column name `tenant_id`. The SQL column `tenant_id` and the parameter `:tenantId` can follow different naming conventions.

Comparison:

| Form | Best suited when | Notes |
| --- | --- | --- |
| `Map.of("id", id)` | Few non-null parameters. | Concise, no explicit JDBC type metadata. |
| `MapSqlParameterSource` | Needing nullable values, SQL types, conditional building. | Mutable; create a new instance per operation. |
| `BeanPropertySqlParameterSource(bean)` | DTO/filter with readable JavaBean properties. | Depends on property/getter names; not a result mapper. |
| `SqlParameterSourceUtils.createBatch(...)` | Batching multiple beans or maps. | Creates an array of parameter sources for each batch item. |

Do not confuse `BeanPropertySqlParameterSource` with `BeanPropertyRowMapper`:

- **BeanPropertySqlParameterSource:** reads **JavaBean → input SQL parameters**.
- **BeanPropertyRowMapper:** reads **a ResultSet row → output JavaBean**.

They handle opposite data directions. A repository may use both, but the two classes are not required to be used together.

## 7. `query`, `queryForObject`, and `update` with Named Parameters

`NamedParameterJdbcTemplate` provides APIs analogous to `JdbcTemplate`:

### Returning Multiple Rows: `query`

```java
List<AccountView> accounts = namedJdbc.query(
    "SELECT id, full_name FROM account " +
    "WHERE tenant_id = :tenantId ORDER BY id",
    Map.of("tenantId", 10L),
    (rs, rowNum) -> new AccountView(
        rs.getLong("id"),
        rs.getString("full_name")
    )
);
```

`query` returns a list, which may be empty or contain multiple rows. `RowMapper` still runs per row; named placeholders do not cause rows to be grouped.

### Expecting Exactly One Row: `queryForObject`

```java
String fullName = namedJdbc.queryForObject(
    "SELECT full_name FROM account WHERE id = :id",
    Map.of("id", 1L),
    String.class
);
```

`queryForObject` expects **one row**. If there are no rows, Spring typically throws `EmptyResultDataAccessException`; if there is more than one row, `IncorrectResultSizeDataAccessException`. Do not use this API to "fetch the first row"; if business logic allows multiple rows, use `query`, or add a selection rule with `ORDER BY` and an appropriate limit.

With `queryForObject(..., Class<T>)`, the query usually must return **a single column**; if you need multiple columns to construct a DTO, pass a `RowMapper<T>`.

### Writing Data: `update`

```java
int changed = namedJdbc.update(
    """
    UPDATE account
    SET status = :newStatus
    WHERE tenant_id = :tenantId AND id = :id
    """,
    new MapSqlParameterSource()
        .addValue("newStatus", "SUSPENDED")
        .addValue("tenantId", 10L)
        .addValue("id", 1L)
);
```

The `changed` value is the number of SQL rows affected according to the driver/DB. An update matching 0 rows is not automatically treated as a Java exception; if business logic requires the record to exist, the service/repository should check `changed == 1` and decide how to report the error.

Named parameters apply to **query inputs**. They do not automatically turn `ResultSet` results into complex objects or provide optimistic locking unless the SQL statement includes an appropriate version condition.

## 8. List Parameters `IN (:ids)`

This is a useful difference compared to plain JDBC placeholders. Example finding three accounts:

```java
String sql = """
    SELECT id, full_name
    FROM account
    WHERE id IN (:ids)
    ORDER BY id
    """;

MapSqlParameterSource params =
    new MapSqlParameterSource("ids", List.of(1L, 3L, 5L));

List<AccountView> accounts = namedJdbc.query(sql, params, mapper);
```

In a JDBC context, `mapper` is an existing `RowMapper<AccountView>`, not a standalone program. Spring replaces `:ids` with the **number of `?` markers matching** the elements:

```sql
SELECT id, full_name
FROM account
WHERE id IN (?, ?, ?)
ORDER BY id;
```

Spring then binds `1L`, `3L`, `5L`. Do not concatenate `"1,3,5"` into SQL, and **do not** bind the entire list to a single `?` as a string.

### Empty List Case

`IN ()` is not portable syntax across database engines; an empty list can produce invalid SQL or unintended semantics. Define the business behavior clearly upfront:

```java
// Illustrative snippet in a repository that has namedJdbc and mapper.
public List<AccountView> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }

    return namedJdbc.query(
        "SELECT id, full_name FROM account " +
        "WHERE id IN (:ids) ORDER BY id",
        Map.of("ids", ids),
        mapper
    );
}
```

This method is **integration code**; it lacks external classes/fields to compile on its own. This implements the policy "finding by an empty ID set returns an empty list." In a delete or update workflow, an empty set might mean **do nothing** or be an invalid input to reject. Never turn an empty ID list into a query **without a WHERE clause**, as it could accidentally affect the entire table.

### Very Large Sets and DB Limits

Each `IN` element is a placeholder. With thousands of IDs, SQL length, bound parameter count, database `IN` limits, and parse/plan cost can become problematic. Some databases enforce limits on the number of expressions in `IN` (for example, Oracle often limits a simple `IN` list to 1,000 items); JDBC does not guarantee unlimited lists.

Options for very large sets include controlled batching, temporary tables, table-valued parameters, array binding, or joining with an intermediate data table **depending on DB capabilities**. Do not force every large set into a single `IN (:ids)` regardless of size.

### Tuple Lists

Spring also supports certain tuple-list forms to generate grouped placeholders, such as `(col_a, col_b) IN ((?, ?), (?, ?))` when passing appropriate value pairs. This depends on the SQL dialect and must be tested against the target database; not all DBs support row-value expressions in `IN` identically.

## 9. `LIKE`, Wildcards, and Named Parameters

A common mistake is writing wildcards directly around a placeholder:

```sql
-- Not a portable, reliable binding approach:
SELECT id FROM account WHERE full_name LIKE %:keyword%;
```

`%` in SQL is a pattern symbol, but writing `%:keyword%` is not a valid parameter placed inside an expression as intended. The clearest approach is building the **pattern value in Java** and binding it:

```java
String pattern = "%" + keyword + "%";

List<AccountView> matches = namedJdbc.query(
    "SELECT id, full_name FROM account " +
    "WHERE LOWER(full_name) LIKE LOWER(:pattern) ORDER BY id",
    Map.of("pattern", pattern),
    mapper
);
```

This is an integration snippet with `keyword`/`mapper` provided. An SQL dialect might support string concatenation (such as `CONCAT`), but binding the whole pattern is usually easier to control.

If `keyword` comes from a user and `%` or `_` characters must be treated as literal text rather than wildcards, you must **escape LIKE metacharacters** according to the dialect and specify an appropriate escape clause. Parameter binding still prevents SQL syntax injection, but does not by itself stop wildcards from making results overly broad.

Similarly, when a user enters a string containing an apostrophe `'`, you do not need to add quotes into the SQL yourself or replace quotes with string concatenation; the driver will bind it as a value.

## 10. Security: Parameters Only Bind **Values**, Not **SQL Structure**

Correct:

```java
String sql = "SELECT id, full_name FROM account WHERE full_name = :name";
namedJdbc.query(sql, Map.of("name", userSuppliedName), mapper);
```

The name `:name` represents a **value**; Spring uses `PreparedStatement`. Input containing `' OR 1=1 --` is still bound as a literal value and will not become part of the `WHERE` clause.

Incorrect:

```java
// Unsafe: userSuppliedName is concatenated directly into SQL.
String sql = "SELECT id FROM account WHERE full_name = '" +
             userSuppliedName + "'";
```

**You cannot bind table names, column names, or sort directions with `:parameter`.** For example:

```sql
-- :sortColumn is only a value, not converted to a column name for ORDER BY:
SELECT id, full_name FROM account ORDER BY :sortColumn;
```

If the application allows choosing a sort field, **whitelist** the valid columns and concatenate the selected identifier from a fixed list. Filter values must still be bound separately:

```java
// Illustrative snippet: sortKey and tenantId are already provided inputs.
String sortColumn = switch (sortKey) {
    case "name" -> "full_name";
    case "id" -> "id";
    default -> throw new IllegalArgumentException("Unsupported sort key");
};

String sql =
    "SELECT id, full_name FROM account " +
    "WHERE tenant_id = :tenantId ORDER BY " + sortColumn;

List<AccountView> rows = namedJdbc.query(
    sql, Map.of("tenantId", tenantId), mapper
);
```

Only `"full_name"` or `"id"` controlled by the code enters the SQL. Never use `sortKey` directly as an identifier. If pagination is used, validate limit/offset and use an appropriate binding mechanism for your DB; named parameters do not by themselves restrict malicious or oversized queries.

**Do not confuse two separate concerns:** safe binding prevents SQL syntax injection; access/tenant authorization checks remain the application's responsibility. A safely bound query missing `tenant_id` can still expose another tenant's data.

## 11. Batch Updates with Multiple Parameter Sets

When the same SQL statement needs to run repeatedly with different value sets, `batchUpdate` accepts an array of `SqlParameterSource[]` or `Map<String, ?>[]`.

```java
// Illustrative: each ScoreChange is a JavaBean with getId/getPoints.
List<ScoreChange> changes = List.of(
    new ScoreChange(1L, 10),
    new ScoreChange(2L, 20)
);

int[] counts = namedJdbc.batchUpdate(
    "UPDATE account SET points = :points WHERE id = :id",
    SqlParameterSourceUtils.createBatch(changes)
);
```

This is an integration snippet; `ScoreChange` needs its definition and corresponding imports. `SqlParameterSourceUtils.createBatch(...)` creates one parameter source for **each element**; Spring feeds these sets into the corresponding JDBC batch. A complete `ScoreChange` is included in the standalone example below.

Notes:

- `int[]` holds the results from the JDBC driver for each item. A driver may report actual row counts or codes such as `Statement.SUCCESS_NO_INFO`; do not always assume every element equals 1 across all DBs.
- A batch does not automatically guarantee **all-or-nothing commit or rollback**. If atomicity is needed, wrap it in a Spring transaction with the appropriate transaction manager/DataSource.
- Do not batch millions of elements in one go if it causes memory pressure, excessive logs, or overly long transactions.
- If a batch includes a statement affecting 0 rows, business code should decide whether that is an error (missing record) or a valid state.

Regarding generated keys, `NamedParameterJdbcTemplate` provides `update(sql, SqlParameterSource, KeyHolder, ...)` overloads and some batch overloads supporting `KeyHolder` in Spring 6.1; key availability and format depend on the JDBC driver/database. Do not assume every auto-increment insert returns keys via `update(sql, Map)`.

## 12. Relationship with Spring Transactions and Data Sources

Because `NamedParameterJdbcTemplate` delegates to `JdbcTemplate`, it participates in the Spring JDBC connection lifecycle. If a repository runs inside a Spring transaction configured for the **same `DataSource`**, `namedJdbc.query`/`update` calls can use the connection bound to the current transaction.

Example:

```java
// Illustrates a service running through a Spring proxy with the same transaction manager.
@Transactional
public void renameAndAudit(long id, String name) {
    namedJdbc.update(
        "UPDATE account SET full_name = :name WHERE id = :id",
        Map.of("id", id, "name", name)
    );
    namedJdbc.update(
        "INSERT INTO account_audit(account_id, event) " +
        "VALUES (:id, :event)",
        Map.of("id", id, "event", "RENAMED")
    );
}
```

This is an integration snippet; it requires properly configured schema, beans, imports, and transaction management.

If the second operation throws an unchecked exception out of the interceptor, `@Transactional` with default rollback rules typically rolls back both operations. However, if there is no Spring-managed transaction active, each statement may auto-commit independently. **Named parameters do not alter commit/rollback rules**.

Common pitfalls:

- The same `@Transactional` does not automatically span two different `DataSource`s.
- Direct self-invocation within the same Spring bean (proxy mode) normally bypasses the transaction interceptor.
- Calling `DataSource.getConnection()` directly outside transaction-aware mechanisms may obtain a different connection; prefer Spring templates.
- `NamedParameterJdbcTemplate` does not determine transaction propagation, isolation, or timeout.
- Do not create a template per SQL statement with a new `DataSource`; manage the `DataSource`/pool at the application level.

## 13. Standalone Java 17+: Map, Bean, IN, NULL, Batch, and Rollback

This example uses **Spring JDBC 6.1.14**, **H2 2.2.224**, and Maven. It creates in-memory H2 data and verifies the key points:

1. Use `MapSqlParameterSource` to insert 3 rows with `:id`, `:tenantId`, `:fullName`, `:status`, `:points`.
2. Use `Map.of` to query a single value by two named conditions.
3. Repeat the `:term` placeholder twice while binding only one value.
4. Use `IN (:ids)` to query a list of IDs.
5. Use `BeanPropertySqlParameterSource` to read values from bean getters.
6. Bind `null` with `Types.INTEGER` and observe SQL `NULL`.
7. Use `batchUpdate` with two score-change beans.
8. Use `TransactionTemplate` to roll back an update with named parameters when an exception occurs.

**This is a complete standalone Java program in a single source file**, requiring no Spring Boot or application server.

### Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>named-parameter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### Create `src/main/java/NamedParameterDemo.java`

```java
import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class NamedParameterDemo {
    public record Account(
            long id, String fullName, String status, Integer points) {}

    public static final class Filter {
        private final long tenantId;
        private final String status;

        public Filter(long tenantId, String status) {
            this.tenantId = tenantId;
            this.status = status;
        }

        public long getTenantId() {
            return tenantId;
        }

        public String getStatus() {
            return status;
        }
    }

    public static final class ScoreChange {
        private final long id;
        private final Integer points;

        public ScoreChange(long id, Integer points) {
            this.id = id;
            this.points = points;
        }

        public long getId() {
            return id;
        }

        public Integer getPoints() {
            return points;
        }
    }

    private static void insert(
            NamedParameterJdbcTemplate jdbc,
            long id,
            long tenantId,
            String name,
            String status,
            Integer points) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("tenantId", tenantId)
                .addValue("fullName", name)
                .addValue("status", status)
                .addValue("points", points, Types.INTEGER);

        jdbc.update(
            "INSERT INTO account " +
            "(id, tenant_id, full_name, status, points) " +
            "VALUES (:id, :tenantId, :fullName, :status, :points)",
            params
        );
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:named_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);

        named.getJdbcOperations().execute(
            "CREATE TABLE account (" +
            "id BIGINT PRIMARY KEY, " +
            "tenant_id BIGINT NOT NULL, " +
            "full_name VARCHAR(80) NOT NULL, " +
            "status VARCHAR(16) NOT NULL, " +
            "points INTEGER)"
        );

        insert(named, 1L, 10L, "An", "ACTIVE", null);
        insert(named, 2L, 10L, "Binh", "ACTIVE", 20);
        insert(named, 3L, 20L, "Chi", "PAUSED", 30);

        String single = named.queryForObject(
            "SELECT full_name FROM account " +
            "WHERE tenant_id = :tenantId AND id = :id",
            Map.of("tenantId", 10L, "id", 1L),
            String.class
        );
        System.out.println("Single: " + single);

        Long repeated = named.queryForObject(
            "SELECT COUNT(*) FROM account " +
            "WHERE status = :term OR full_name = :term",
            Map.of("term", "ACTIVE"),
            Long.class
        );
        System.out.println("Repeated parameter: " + repeated);

        List<Long> ids = named.query(
            "SELECT id FROM account WHERE id IN (:ids) ORDER BY id",
            Map.of("ids", List.of(1L, 3L)),
            (rs, rowNum) -> rs.getLong("id")
        );
        System.out.println("IN list: " + ids);

        SqlParameterSource filter =
            new BeanPropertySqlParameterSource(
                new Filter(10L, "ACTIVE")
            );

        List<Account> selected = named.query(
            "SELECT id, full_name, status, points " +
            "FROM account " +
            "WHERE tenant_id = :tenantId AND status = :status " +
            "ORDER BY id",
            filter,
            (rs, rowNum) -> new Account(
                rs.getLong("id"),
                rs.getString("full_name"),
                rs.getString("status"),
                rs.getObject("points", Integer.class)
            )
        );
        List<String> names = selected.stream()
                .map(Account::fullName)
                .toList();
        System.out.println("Bean filter: " + names);

        int updatedNull = named.update(
            "UPDATE account SET points = :points WHERE id = :id",
            new MapSqlParameterSource()
                .addValue("id", 1L)
                .addValue("points", null, Types.INTEGER)
        );
        Integer maybePoints = named.queryForObject(
            "SELECT points FROM account WHERE id = :id",
            Map.of("id", 1L),
            Integer.class
        );
        System.out.println(
            "Typed NULL: updated=" + updatedNull +
            ", isNull=" + (maybePoints == null)
        );

        List<ScoreChange> changes = List.of(
            new ScoreChange(1L, 11),
            new ScoreChange(2L, 22)
        );
        int[] batchCounts = named.batchUpdate(
            "UPDATE account SET points = :points WHERE id = :id",
            SqlParameterSourceUtils.createBatch(changes)
        );
        System.out.println(
            "Batch counts: " + Arrays.toString(batchCounts)
        );

        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );
        try {
            tx.executeWithoutResult(status -> {
                named.update(
                    "UPDATE account SET status = :nextStatus " +
                    "WHERE id = :id",
                    Map.of("nextStatus", "PAUSED", "id", 1L)
                );
                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback triggered");
        }

        String afterRollback = named.queryForObject(
            "SELECT status FROM account WHERE id = :id",
            Map.of("id", 1L),
            String.class
        );
        System.out.println("Status after rollback: " + afterRollback);
    }
}
```

### Running the Program

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=NamedParameterDemo
```

Expected **`System.out` lines from the application**:

```text
Single: An
Repeated parameter: 2
IN list: [1, 3]
Bean filter: [An, Binh]
Typed NULL: updated=1, isNull=true
Batch counts: [1, 1]
Rollback triggered
Status after rollback: ACTIVE
```

Maven or library logging may output additional messages outside these lines; those are not produced by the program's `System.out.println` statements.

### Step-by-Step Explanation

1. `Single: An`: The SQL uses two names `:tenantId` and `:id`; `Map.of` can list keys in a different order than the SQL and still bind correctly.
2. `Repeated parameter: 2`: `:term` appears twice but receives the same `"ACTIVE"` value; two rows have status ACTIVE.
3. `IN list: [1, 3]`: The list of two IDs becomes two JDBC placeholders; `ORDER BY id` makes the order deterministic.
4. `Bean filter: [An, Binh]`: `BeanPropertySqlParameterSource` reads `getTenantId()` and `getStatus()` from `Filter`; results map each row to an `Account` record via an explicit RowMapper.
5. `Typed NULL`: The update uses `MapSqlParameterSource` and `Types.INTEGER`, matching one row; querying the `points` column again returns `null`.
6. `Batch counts: [1, 1]`: Two `ScoreChange` beans create two named-parameter sets; on H2 each `UPDATE` matches one row.
7. `Rollback triggered` and `Status after rollback: ACTIVE`: `TransactionTemplate` keeps the two steps within a Spring transaction; the unchecked exception causes the status change to PAUSED to roll back.

`DriverManagerDataSource` here is a simple connection source for demonstration, **not a connection pool**. In production, use a pool and proper transaction configurations. The goal of the example is to verify named-parameter binding and Spring JDBC delegation.

## 14. Common Mistakes

| Mistake | Symptom/Consequence | Fix |
| --- | --- | --- |
| Key includes `:`, e.g., `Map.of(":id", 1)` | Value for `:id` is not found. | Key must be `"id"`. |
| Confusing `:tenantId` with key `"tenant_id"` | Missing parameter. | Match placeholder name to key/getter name; the SQL column can have a different name. |
| Using `Map.of` with `null` | `NullPointerException` before running SQL. | Use `MapSqlParameterSource` and an SQL type when needed. |
| Passing an ID list as a single string `"1,2,3"` | Does not expand into multiple `IN` placeholders. | Pass `List<Long>` to `:ids`. |
| Using an empty list with `IN (:ids)` | SQL `IN ()` may be invalid. | Handle empty lists according to business logic before running SQL. |
| Using an unbounded `IN` with thousands of items | Hits SQL/driver/DB limits or degrades performance. | Split into batches or use an intermediate table/solution suitable for the DB. |
| Using `:sortColumn` for a column name | Bound as a value, not as an identifier. | Whitelist allowed columns, then concatenate the verified identifier. |
| Concatenating user strings into SQL | SQL injection risk. | Bind literals via named parameters; whitelist all dynamic structural parts. |
| Catching `DataAccessException` and returning an empty list for every error | Hides connection/SQL/missing-parameter errors. | Catch specific business errors; log and handle at the proper layer. |
| Assuming `queryForObject` returns null when no row exists | May receive `EmptyResultDataAccessException`. | Use an Optional/try-catch policy per contract, or `query` if a list is needed. |
| Confusing `BeanPropertySqlParameterSource` with `BeanPropertyRowMapper` | Mixes up data direction. | Source reads a bean as input; mapper creates a bean from ResultSet. |
| Assuming named parameters automatically open a transaction | Multiple updates auto-commit separately, causing partial rollback. | Use `@Transactional`/`TransactionTemplate` appropriately. |
| Sharing a mutable `MapSqlParameterSource` across requests | Race conditions, value leakage between requests. | Create a parameter source per call. |
| Assuming `batchUpdate` always returns `1` per item | Some drivers return unknown-count codes. | Account for JDBC constant `Statement.SUCCESS_NO_INFO` and driver semantics. |

## 15. How to Test and Review Code Using Named Parameters

Tests should verify **both the SQL contract and data behavior**, not just confirm that a Java method was called:

1. **Exact names:** Every `:parameter` has a matching key/getter. A casing or snake_case mistake in a key must be caught.
2. **Order independence:** Reordering map entries or SQL conditions still yields correct results.
3. **Repeated names:** SQL using the same `:name` in multiple places receives the same value in each position.
4. **Special values:** Single quotes and SQL-like strings are bound as literals without altering the SQL statement structure.
5. **NULL and JDBC types:** Test nullable columns, appropriate `Types`, and driver compatibility.
6. **IN-lists:** 1 item, multiple items, 0 items, and large counts; define policies and limits clearly.
7. **Query cardinality:** 0/1/n rows when the repository uses `queryForObject`; do not blame named parameters for invalid row counts.
8. **Batch updates:** Check operation counts, affected rows, handling of special JDBC codes, and rollback when an error occurs mid-batch.
9. **Transactions:** Two `namedJdbc.update` calls in one transaction roll back together when an exception matches rollback rules.
10. **Authorization scope:** Tenant, soft-delete, and data-access conditions remain present in the SQL.
11. **Dynamic structure:** Sort fields/table names come only from a whitelist; prevent SQL injection from concatenated user strings.
12. **SQL dialect:** Use integration tests with a real DB when dealing with large `IN` lists, tuple INs, generated keys, or specialized types.

A good error should preserve useful diagnostic context: query/repository name, exception type, business code, expected row count (if relevant). Do not log passwords, sensitive data, or raw SQL strings containing user values into uncontrolled logs.

## 16. Comparing `JdbcTemplate`, `NamedParameterJdbcTemplate`, and `JdbcClient`

| Criterion | `JdbcTemplate` | `NamedParameterJdbcTemplate` | `JdbcClient` (Spring 6.1+) |
| --- | --- | --- | --- |
| Primary placeholder | `?` | `:name` | Both positional and named. |
| Invocation style | `query`/`update`/callbacks | Similar methods accepting a map/parameter source | Fluent API `sql(...).param(...).query(...)`. |
| Strengths | Direct, widely used, rich callback APIs | Clear parameter meaning, supports `IN` lists and named batching | Concise fluent syntax for common operations. |
| Transactions | Spring JDBC | Still uses Spring JDBC underneath | Also delegates to Spring's JDBC mechanism. |
| When to choose | Short SQL, specialized APIs needing JdbcOperations | Many named filters, long queries, batches | Wanting fluent style on a supported Spring version. |

`JdbcClient` does not make `NamedParameterJdbcTemplate` immediately obsolete. Certain advanced APIs remain more convenient with `JdbcTemplate` or `NamedParameterJdbcTemplate`; choose based on Spring version, operation style, and codebase consistency.

## 17. Checklist for Using `NamedParameterJdbcTemplate` Correctly

Before reviewing a repository, ask yourself:

- **Are `:name` placeholders written consistently in SQL?** Do all parameter source keys/getters match?
- **Are nullable values handled?** Not using `Map.of` with null; is a JDBC type declaration needed?
- **Is SQL structure built from unverified input?** Are identifiers/sort fields whitelisted?
- **Can `IN` receive an empty or overly large set?** Are the empty policy and DB limits clear?
- **Are input binding and output mapping kept distinct?** `BeanPropertySqlParameterSource` differs from `RowMapper`.
- **Does the method match the row-count contract?** `queryForObject` is for exactly one, `query` for many.
- **Does the transaction use the right DataSource/manager and rollback rules?** The template does not automatically create an atomic transaction for the entire use case.
- **Is batching appropriate for the item count and driver?** Do not rely blindly on update counts as a transaction-level guarantee.
- **Is a mutable parameter source shared across requests?** Configure the template once, but create a map/parameter source per call.
- **Are there integration tests for the real SQL dialect?** Especially `IN`, typed NULLs, and generated keys.

### Key Takeaways

1. `NamedParameterJdbcTemplate` adds **`:name`** syntax on top of Spring JDBC and delegates to `JdbcTemplate` after converting placeholders to `?`.
2. Values are bound by **name** via `Map` or `SqlParameterSource`; repeated names are bound repeatedly at their positions.
3. `MapSqlParameterSource` is convenient for nullable values and declaring `java.sql.Types`; `BeanPropertySqlParameterSource` reads values from JavaBean getters.
4. `IN (:ids)` can expand a list into multiple placeholders, but you must handle **empty lists** and **database limits**.
5. Named parameters are safe for **values**, not for passing dynamic table/column names or SQL keywords.
6. `query`, `queryForObject`, `update`, and `batchUpdate` still follow Spring JDBC's cardinality and affected-row contracts.
7. Transactions, connections, rollbacks, and tenant security still require proper design; `NamedParameterJdbcTemplate` does not replace those responsibilities.

### References

- Spring Framework — JDBC core / Using NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC parameter handling and `IN` list: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JDBC batch operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework 6.1 — `NamedParameterJdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework 6.1 — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Spring Framework 6.1 — `BeanPropertySqlParameterSource`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/namedparam/BeanPropertySqlParameterSource.html
