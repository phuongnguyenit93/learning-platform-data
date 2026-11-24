# Starting Operations with `sql()` in Spring `JdbcClient`

`JdbcClient` is the fluent API of **Spring JDBC starting in Spring Framework 6.1**, making it easier to run common SQL operations through a readable method chain. Instead of remembering many overloads of `JdbcTemplate` or `NamedParameterJdbcTemplate`, you start with a common expression:

```java
jdbcClient.sql("SELECT title FROM task WHERE id = :id")
          .param("id", 10L)
          .query(String.class)
          .single();
```

The first call, **`sql(String)`**, is the starting point: it takes the SQL statement and returns a statement specification object so you can **declare parameters and decide how to handle results**. It is **not a standalone SQL execution command**. In the example above, execution happens when the `single()` resolver fetches the data; for write operations, `update()` is the execution point.

This lesson focuses on the meaning of `sql()`, the `StatementSpec` type it returns, the common paths after `sql()`, common mistakes, and a runnable Java 17+ program to verify them. The context is Spring Framework **data-access / JdbcClient**; database, connection, and transaction concepts are explained to the extent needed to use `sql()` properly.

## 1. What Problem Does `JdbcClient` Solve?

Spring JDBC already had two powerful tools:

- `JdbcTemplate`: SQL with positional JDBC placeholders `?`, handling connections, statements, result sets, and `SQLException` translation.
- `NamedParameterJdbcTemplate`: supports named placeholders `:id`, `:status`, `:tenantId` and delegates to the underlying JDBC mechanism.

`JdbcClient` provides a **unified** interface layer for common query and update operations; you can choose `?` or `:name` syntax within the same API style without manually opening a `Connection`/`PreparedStatement`. It still delegates to Spring JDBC templates, is not an ORM, and does not replace them for every advanced task.

Comparing the same query:

```java
// JdbcTemplate: positional parameter.
String a = jdbcTemplate.queryForObject(
    "SELECT title FROM task WHERE id = ?",
    String.class,
    10L
);

// NamedParameterJdbcTemplate: named parameter.
String b = namedJdbcTemplate.queryForObject(
    "SELECT title FROM task WHERE id = :id",
    java.util.Map.of("id", 10L),
    String.class
);

// JdbcClient: start with sql(), bind, then choose the result.
String c = jdbcClient
    .sql("SELECT title FROM task WHERE id = :id")
    .param("id", 10L)
    .query(String.class)
    .single();
```

These are **three integration snippets**, requiring initialized templates and a `task` table with data. All three put SQL in code; `JdbcClient` clarifies the sequence with a fluent chain.

**Key characteristic:** `JdbcClient` handles synchronous JDBC operations. It is not R2DBC's reactive `DatabaseClient` API, does not auto-generate SQL from entities like an ORM, and does not automatically create a transaction for an entire business flow just because methods are chained.

## 2. Creating a `JdbcClient` Before Calling `sql()`

Interface import:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
```

Common factories:

```java
// 1. From an existing DataSource.
JdbcClient client = JdbcClient.create(dataSource);

// 2. Reuse a configured JdbcTemplate/JdbcOperations.
JdbcClient fromTemplate = JdbcClient.create(jdbcTemplate);

// 3. Reuse a configured NamedParameterJdbcTemplate.
JdbcClient fromNamed = JdbcClient.create(namedJdbcTemplate);
```

The snippet above is **illustrative code**; the variables `dataSource`, `jdbcTemplate`, and `namedJdbcTemplate` must already exist. The `create` factory does not open a permanent JDBC session for all calls. `JdbcClient` references the corresponding operational components, while acquiring and releasing connections happens when an operation executes.

In a Spring-managed bean application, you can configure:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class JdbcClientConfig {
    @Bean
    JdbcClient jdbcClient(DataSource dataSource) {
        return JdbcClient.create(dataSource);
    }
}
```

This is a **Spring integration** class requiring a separately configured `DataSource`. Depending on the Spring Boot/autoconfiguration version, the application may already provide a `JdbcClient` bean; in that case use the existing bean and avoid unnecessary duplicate declarations.

A repository using constructor injection:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private final JdbcClient client;

    public TaskRepository(JdbcClient client) {
        this.client = client;
    }

    public long countAll() {
        return client.sql("SELECT COUNT(*) FROM task")
                     .query(Long.class)
                     .single();
    }
}
```

This is integration code requiring a `task` table and JDBC configuration. Once initialized, `JdbcClient` can be shared; at the start of each operation, call **`client.sql(...)` to obtain a fresh statement specification**. Do not create and share a mutable `StatementSpec` across requests as a global template.

### Version Requirement

`JdbcClient` was introduced in **Spring Framework 6.1**. If a project uses Spring 6.0 or older, the `org.springframework.jdbc.core.simple.JdbcClient` class will not exist in the corresponding artifact. Check the actual `spring-jdbc` dependency and version alignment across Spring libraries; do not merely add an import and expect the API to exist.

## 3. What Does `sql(String)` Accept, Return, and Not Yet Do?

API signature:

```java
JdbcClient.StatementSpec sql(String sql);
```

The `String` passed in is **the full SQL statement** defined by the application, for example:

```java
JdbcClient.StatementSpec spec = client.sql(
    "SELECT id, title FROM task WHERE tenant_id = :tenantId"
);
```

- The `sql` parameter is SQL text, not an entity name or a builder object representing a table.
- The returned `StatementSpec` object carries options for binding parameters, querying, or updating.
- At the moment `sql(...)` is called, the code has only **set up the operation specification**; no result has been fetched from the database yet.
- `sql()` does not return a `List`, `Optional`, `ResultSet`, `Connection`, or update count.
- `sql()` does not know on its own whether you want to read or write; subsequent steps decide how it is processed.

Example action chain:

```text
JdbcClient
    |
    | .sql("SELECT ... WHERE id = :id")
    v
StatementSpec
    |
    | .param("id", 7)
    v
StatementSpec with registered parameter
    |
    | .query(TaskView.class)
    v
MappedQuerySpec<TaskView>
    |
    | .optional()
    v
Optional<TaskView>  <- executes query and resolves cardinality
```

For an update statement:

```text
JdbcClient
    |
    | .sql("UPDATE task SET status = :newStatus WHERE id = :id")
    | .param("newStatus", "DONE")
    | .param("id", 7)
    | .update()
    v
int affected row count  <- executes JDBC update
```

Therefore, **`sql()` is the starting point, not the endpoint**. Writing:

```java
client.sql("DELETE FROM task WHERE id = 7");
```

is **not a reliable way to delete rows**: you only created a `StatementSpec` and discarded it. To execute a DML statement and obtain the affected row count, you must call the terminal `update()`. For `SELECT`, you must follow the appropriate query path and consume the result (or use a callback/extractor that executes directly).

## 4. Steps You Can Chain Immediately After `sql()`

There are three main groups of actions.

| Step | Typical signature | Meaning |
| --- | --- | --- |
| Register positional parameter | `.param(value)` | Binds sequentially to `?` markers. |
| Register parameter by JDBC index | `.param(1, value)` | Specifies position explicitly, **1-based**, not 0-based. |
| Register named parameter | `.param("id", id)` | Binds a value to the `:id` placeholder. |
| Register multiple parameters | `.params(...)` | Positional list or `Map<String, ?>` for named parameters. |
| Register parameter source | `.paramSource(beanOrRecord)` | Reads named values from a JavaBean/record/field holder or a `SqlParameterSource`. |
| Query step with mapper | `.query(RowMapper<T>)` or `.query(Class<T>)` | Chooses how to convert each row into an object, followed by `list()`/`single()`/`optional()`/... |
| Query step without explicit mapper | `.query()` | Provides `singleRow()`, `listOfRows()`, `singleColumn()`, `rowSet()`, `singleValue()`. |
| Data modification operation | `.update()` | Executes SQL update/insert/delete and returns affected row count. |
| Write operation with generated keys | `.update(keyHolder, "id")` | Executes and attempts to retrieve generated keys when driver/database support it. |

**Typical reading order:** `sql(...) → param/params/paramSource → query(...).list()/single()/optional()` or `update()`.

Some `query(...)` overloads accepting `ResultSetExtractor<T>` or `RowCallbackHandler` **execute immediately when the callback path is invoked** and do not return a `MappedQuerySpec`; distinguish them from `query(Class)`/`query(RowMapper)`. There is no single generic terminal named `execute()` for all `JdbcClient.StatementSpec` operations in Spring 6.1.

## 5. Starting with `sql()` Without Parameters

Not every `sql()` call has to include `param()`. When the SQL needs no bound values:

```java
long total = client
    .sql("SELECT COUNT(*) FROM task")
    .query(Long.class)
    .single();

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task ORDER BY id")
    .query(TaskView.class)
    .list();
```

This is integration code; `TaskView` is an application data type with matching properties/constructor. For queries without a `WHERE` clause, consider very large row counts before calling `list()`.

Having no parameters should not be an excuse to concatenate user strings into SQL:

```java
// Unsafe: input can alter the query syntax.
String sql = "SELECT id FROM task WHERE title = '" + userTitle + "'";
List<Long> ids = client.sql(sql).query(Long.class).list();
```

The snippet above is a **counter-example**, not standalone runnable code. The right approach is to use `:title` or `?` and bind the value:

```java
List<Long> ids = client
    .sql("SELECT id FROM task WHERE title = :title")
    .param("title", userTitle)
    .query(Long.class)
    .list();
```

Underneath, Spring JDBC uses `PreparedStatement`. Binding values prevents user-supplied input from becoming part of the SQL statement.

## 6. From `sql()` to Positional Parameters `?`

The style closest to traditional JDBC:

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .param(10L)
    .param(7L)
    .query(String.class)
    .single();
```

Here:

1. `.sql(...)` defines a query with **two** `?` markers.
2. `.param(10L)` registers the first value.
3. `.param(7L)` registers the second value.
4. `.query(String.class).single()` executes and requires exactly one row with one value mappable to String.

Another style for a few parameters:

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .params(10L, 7L)
    .query(String.class)
    .single();
```

Both `params(Object...)` and `params(List<?>)` register a positional list of values. They **do not infer order from column names**; if you reorder `WHERE` conditions in SQL, re-check the binding order. With multiple fields of the same type (for example `tenantId` and `accountId` both being long), mixing up the order can silently return wrong data without a type error.

### JDBC Index Starts at 1

```java
String title = client
    .sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
    .param(2, 7L)
    .param(1, 10L)
    .query(String.class)
    .single();
```

In the `param(int jdbcIndex, Object value)` overload, `jdbcIndex` is the **placeholder position in the PreparedStatement**, starting at **1**, not a Java array index. Explicit indexing can help when building dynamic queries, though it requires maintaining accurate indices.

Do not write `.param(0, ...)`; and do not confuse `.param(1L)` (a single positional value) with `.param(1, 7L)` (a position plus a value).

## 7. From `sql()` to Named Parameters `:name`

A key feature of `JdbcClient` is allowing the same `sql(...)` method to start SQL statements with **named placeholders**:

```java
String title = client
    .sql("""
         SELECT title
         FROM task
         WHERE tenant_id = :tenantId AND id = :id
         """)
    .param("tenantId", 10L)
    .param("id", 7L)
    .query(String.class)
    .single();
```

In SQL you write `:tenantId`, while when binding you pass **`"tenantId"` without the colon**. Spring parses and converts named placeholders into JDBC positional placeholders in the proper order; the application does not have to replace them manually.

The advantage is that when SQL conditions are reordered, values remain tied to meaningful names. If `:tenantId` appears twice, the parameter source with that same name is used at both positions; there is no need to bind two separate variables.

You can pass multiple names using `params(Map)`:

```java
Map<String, ?> values = Map.of(
    "tenantId", 10L,
    "status", "OPEN"
);

List<TaskView> rows = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE tenant_id = :tenantId AND status = :status " +
         "ORDER BY id")
    .params(values)
    .query(TaskView.class)
    .list();
```

This is integration code; `Map` requires importing `java.util.Map`. `Map.of(...)` **does not accept null**. For null values or when specifying a SQL type explicitly, use `param("name", null, Types.XXX)` or `paramSource(MapSqlParameterSource)`.

**Choose one parameter style consistently per SQL statement.** Do not intentionally combine `?` and `:id` in the same statement; Spring's binding mechanism selection can fail or become confusing. Use positional for short queries and named for queries with many fields or long conditions.

## 8. `paramSource(...)` Continuing the Chain Started from `sql()`

If you have an input object representing a set of values, `paramSource(Object)` extracts named values from a JavaBean, record, or field holder:

```java
// Java 17 record: component names match named parameter names.
record NewTask(long id, long tenantId, String title, String status) {}

int changed = client
    .sql("""
         INSERT INTO task (id, tenant_id, title, status)
         VALUES (:id, :tenantId, :title, :status)
         """)
    .paramSource(new NewTask(1L, 10L, "Learn JDBC", "OPEN"))
    .update();
```

This is an **illustrative snippet**; the complete file later uses a record with the same idea and an extra column. In Spring 6.1, `JdbcClient` supports reading parameters from records/JavaBeans/field holders via the `SimplePropertySqlParameterSource` strategy, without requiring you to copy every component into a `Map`.

There is an overload accepting `SqlParameterSource` when JDBC type metadata is needed:

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource source = new MapSqlParameterSource()
    .addValue("id", 9L)
    .addValue("note", null, Types.VARCHAR);

int changed = client
    .sql("UPDATE task SET note = :note WHERE id = :id")
    .paramSource(source)
    .update();
```

This snippet is integration code requiring the `task` table to have a `note` column. Specifying the type for `NULL` tells the driver the SQL type. There is also a shorter overload:

```java
client.sql("UPDATE task SET note = :note WHERE id = :id")
      .param("note", null, java.sql.Types.VARCHAR)
      .param("id", 9L)
      .update();
```

`paramSource(Object)` and `paramSource(SqlParameterSource)` do not have the exact same role as `RowMapper`. A parameter source reads **input values**; `query(RowMapper)` reads the **output ResultSet**.

## 9. `sql()` Paired with `query(Class<T>)`: Simple Values and Objects

After finishing the statement setup, `query(Class<T>)` produces a `MappedQuerySpec<T>` for choosing the result shape.

### Single-Column Single Value

```java
long count = client
    .sql("SELECT COUNT(*) FROM task WHERE status = :status")
    .param("status", "OPEN")
    .query(Long.class)
    .single();
```

`COUNT(*)` without `GROUP BY` returns a single row containing the count (which may be 0). `query(Long.class)` maps a single column convertible to `Long`; `single()` requires a non-null object per the resolver's contract.

### Multi-Column Object

Spring 6.1 uses the `SimplePropertyRowMapper` strategy for JavaBean targets, records, constructor-based objects, or field holders in supported cases. For example:

```java
public record TaskView(long id, String title, String status) {}

TaskView task = client
    .sql("SELECT id, title, status FROM task WHERE id = :id")
    .param("id", 7L)
    .query(TaskView.class)
    .single();
```

A record receives data through its constructor using component names matched against column names; no setters are needed. If a column name differs from a property name, use a SQL alias, such as `db_task_name AS title`. For complex mapping logic or specialized JDBC types, prefer a hand-written `RowMapper`.

**Note:** `.query(TaskView.class)` does not turn `TaskView` into an entity in the JPA sense; it only specifies the target type for mapping **each row's** columns. It also does not fix cardinality: with multiple rows, `single()` is still the wrong choice.

## 10. `sql()` Combined with `query(RowMapper<T>)`

When you want exact control over mapping:

```java
List<TaskView> tasks = client
    .sql("""
         SELECT id, title, status
         FROM task
         WHERE tenant_id = :tenantId
         ORDER BY id
         """)
    .param("tenantId", 10L)
    .query((rs, rowNum) -> new TaskView(
        rs.getLong("id"),
        rs.getString("title"),
        rs.getString("status")
    ))
    .list();
```

This is integration code, assuming `TaskView` and `client` already exist. `RowMapper` runs once per row; `list()` returns the mapped list.

To avoid confusion among `query(...)` overloads accepting callbacks, a two-parameter lambda `(rs, rowNum) -> ...` matches `RowMapper`; a `RowCallbackHandler` callback has a different signature, while `ResultSetExtractor` works over the entire `ResultSet`. If type inference struggles in a complex expression, declare `RowMapper<TaskView> mapper` first and call `query(mapper)`.

You do not need `try-with-resources` around a `Connection` managed by `JdbcClient`/Spring when reading data with the template. `JdbcClient` uses Spring's JDBC mechanism to close resources within the proper scope.

## 11. Choosing the Result After `query(...)`

Common resolvers of `MappedQuerySpec<T>`:

| Resolver | Row count expectation | Result |
| --- | --- | --- |
| `list()` | 0 to many | `List<T>`, possibly empty; preserves SQL result order. |
| `single()` | Exactly 1 non-null object | Returns `T`; 0 or more than 1 typically throws the matching exception. |
| `optional()` | 0 or 1 | `Optional<T>`; if >1, it is a cardinality error. |
| `set()` | 0 to many | `Set<T>` preserving query encounter order while deduplicating by equality. |
| `stream()` | 0 to many, sequential/lazy processing | `Stream<T>` that must be closed after use. |

Example with a possibly absent ID:

```java
Optional<TaskView> found = client
    .sql("SELECT id, title, status FROM task WHERE id = :id")
    .param("id", id)
    .query(TaskView.class)
    .optional();
```

The code needs `java.util.Optional` imported and existing data. If SQL returns **two rows** because the filter is not unique, `optional()` does not mean "take an arbitrary row"; that still violates the expectation.

List example:

```java
List<TaskView> open = client
    .sql("SELECT id, title, status " +
         "FROM task WHERE status = :status ORDER BY id")
    .param("status", "OPEN")
    .query(TaskView.class)
    .list();
```

`list()` is suitable for 0/n rows, though for large tables you must intentionally limit or paginate. `ORDER BY` provides deterministic ordering; without `ORDER BY`, the database does not guarantee a stable row order.

### Using `stream()` with Proper Lifecycle Management

```java
try (Stream<TaskView> stream = client
        .sql("SELECT id, title, status FROM task ORDER BY id")
        .query(TaskView.class)
        .stream()) {
    stream.forEach(task -> consume(task));
}
```

This is **integration** code requiring `Stream` imported and a `consume` method. `stream()` returns a resource-backed stream, so it should be **consumed and closed** within the same appropriate transaction/connection scope. Do not return a cursor-holding stream out of a `@Transactional` method and let callers consume it after the transaction has ended.

## 12. `query()` Without a Mapper: Direct Result Return Forms

Unlike `query(Class<T>)`, calling `query()` with no arguments returns a `ResultQuerySpec` with built-in ways to fetch values:

```java
// List of maps for multiple rows.
List<Map<String, Object>> rows = client
    .sql("SELECT id, title FROM task ORDER BY id")
    .query()
    .listOfRows();

// A single map representing one row.
Map<String, Object> row = client
    .sql("SELECT id, title FROM task WHERE id = :id")
    .param("id", 7L)
    .query()
    .singleRow();

// A single value (not mapped to a DTO).
Object value = client
    .sql("SELECT COUNT(*) FROM task")
    .query()
    .singleValue();
```

This is an integration illustration requiring `List` and `Map` imported. Additionally, `singleColumn()` returns a list of values for a single column, and `rowSet()` returns a `SqlRowSet` detached from the underlying JDBC result.

Key differences:

- `query(Class<T>).single()`: the **mapped** and typed path.
- `query().singleRow()`: one row represented as `Map<String,Object>`.
- `query().listOfRows()`: multiple rows as a list of maps.
- `query().singleValue()`: a single `Object` value from one row/one column; not typed mapping like `String.class`/`Long.class`.

Do not write `query().single()`: that is not a resolver name on `ResultQuerySpec` in the 6.1 API. In contrast, `query(String.class).single()` is valid.

## 13. From `sql()` to `update()`: INSERT, UPDATE, DELETE

Fluent pattern for write operations:

```java
int inserted = client
    .sql("""
         INSERT INTO task(id, tenant_id, title, status)
         VALUES (:id, :tenantId, :title, :status)
         """)
    .param("id", 7L)
    .param("tenantId", 10L)
    .param("title", "Write tests")
    .param("status", "OPEN")
    .update();
```

`update()` is a **terminal operation** returning the affected row count. A normal `INSERT` returns 1; `UPDATE` or `DELETE` may return 0, 1, or more depending on the `WHERE` clause, driver/database, and business rules.

```java
int changed = client
    .sql("""
         UPDATE task
         SET status = :newStatus
         WHERE id = :id AND tenant_id = :tenantId
         """)
    .param("newStatus", "DONE")
    .param("id", taskId)
    .param("tenantId", tenantId)
    .update();

if (changed != 1) {
    throw new IllegalStateException(
        "Expected to update exactly one task, actual=" + changed
    );
}
```

This snippet integrates into a repository/service with existing IDs. If `changed==0`, the SQL did not necessarily fail; the ID may not be found, the tenant may not match, or a version may no longer match. If a broad update returns `changed > 1`, that may be valid or a domain error depending on the contract.

For `DELETE`:

```java
int removed = client
    .sql("DELETE FROM task WHERE tenant_id = :tenantId AND id = :id")
    .params(Map.of("tenantId", tenantId, "id", taskId))
    .update();
```

Here `params(Map)` binds names to values without relying on map entry iteration order. Always check `tenant_id` scoping and access permissions; safe parameter binding does not add authorization checks automatically.

### Generated Keys

`StatementSpec` provides `update(KeyHolder)` and `update(KeyHolder, String... keyColumnNames)` overloads when the JDBC driver supports retrieving generated keys:

```java
GeneratedKeyHolder holder = new GeneratedKeyHolder();

int inserted = client
    .sql("INSERT INTO task(title, status) VALUES (:title, :status)")
    .param("title", "Example")
    .param("status", "OPEN")
    .update(holder, "id");
```

This is **illustrative**, requiring a table with an auto-generated key and importing `org.springframework.jdbc.support.GeneratedKeyHolder`. It cannot run if the schema requires NOT NULL columns without defaults. Whether keys are returned, which column names are supported, and how `holder.getKey()` behaves depend on the DB/driver; test against a real database.

## 14. Do Not Confuse `sql()` with Manually Creating/Preparing Connections

A `JdbcClient` chain typically has this lifecycle:

```text
Repository calls JdbcClient.sql(...)
         |
StatementSpec + param bindings
         |
terminal query/update
         |
Spring JDBC acquires transaction-appropriate Connection
         |
PreparedStatement executes
         |
RowMapper/ResultSetExtractor or update count
         |
Spring JDBC cleans up statement/result set and releases connection appropriately
```

You do not need:

```java
// Do not do this to "supplement" JdbcClient:
Connection connection = dataSource.getConnection();
// ... manually calling commit/close alongside an independent JdbcClient chain ...
```

Manual JDBC code may obtain a **different** connection from the transaction-bound connection used by Spring; therefore it does not automatically participate in the same transaction as `JdbcClient`. When low-level JDBC is needed, use appropriate Spring APIs such as `JdbcTemplate.execute(...)`, `DataSourceUtils`, or the transaction manager following proper ownership.

In a Spring application with active `@Transactional`, multiple `client.sql(...).update()` calls within the same transaction for the same `DataSource` can share the transaction-bound connection. `sql()` itself does not commit/rollback; the transaction ends according to the interceptor/`TransactionTemplate` and configured policy.

## 15. What Happens When SQL Is Missing Parameters or Returns the Wrong Row Count?

### Missing Binding for a Placeholder

```java
// Missing .param("id", ...) for :id.
client.sql("SELECT title FROM task WHERE id = :id")
      .query(String.class)
      .single();
```

At execution time, Spring has no value to bind `:id`, so the operation fails, typically within Spring's data-access/parameter exception hierarchy. `sql()` does not invent values for placeholders, nor does it treat unbound parameters as NULL.

### Binding the Wrong Type or Wrong Index

```java
// Here the second parameter is missing.
client.sql("SELECT title FROM task WHERE tenant_id = ? AND id = ?")
      .param(10L)
      .query(String.class)
      .single();
```

An unassigned `?` placeholder usually causes a runtime failure. Using `.param(0, ...)` is an invalid JDBC index because indexing starts at 1. Calling `.params("OPEN", 10L)` on SQL expecting `tenant_id` first and `status` second can fail semantically even if types are convertible.

### Results with 0, 1, or Many Rows

```java
TaskView one = client.sql("SELECT id, title, status FROM task WHERE id = :id")
                     .param("id", taskId)
                     .query(TaskView.class)
                     .single();
```

`single()` requires exactly one non-null object. With 0 rows, you typically get `EmptyResultDataAccessException`; with more than one row, `IncorrectResultSizeDataAccessException`. If business logic allows no rows, use `optional()`; if multiple rows are normal, use `list()`.

Do not blindly fix row counts with `LIMIT 1`: that means **pick one record** rather than fixing a broken "must be unique" invariant. If you need the latest record, specify `ORDER BY created_at DESC, id DESC` and limit according to your dialect intentionally.

### Invalid SQL or Missing Table

`JdbcClient` still runs through the JDBC driver and database. If `task` does not exist, a column name is wrong, permissions are missing, or SQL violates the dialect, the exception goes through Spring's `SQLException` translation mechanism (typically an appropriate `DataAccessException`). Replacing `JdbcTemplate` with `JdbcClient` cannot make invalid SQL valid.

## 16. `sql()` Protects Values, Not Dynamic SQL Structure

Because `sql()` accepts an **already constructed SQL String**, you must clearly separate fixed SQL structure from bound values.

**Correct:**

```java
client.sql("SELECT id, title FROM task WHERE title = :title")
      .param("title", userInput)
      .query(TaskView.class)
      .list();
```

This snippet requires the SQL projection to have columns matching `TaskView`; if `TaskView` also requires `status`, include that column in `SELECT`. The snippet illustrates safe binding, not a standalone runnable program.

**Wrong:**

```java
String sql = "SELECT id FROM task WHERE title = '" + userInput + "'";
client.sql(sql).query(Long.class).list();
```

Because `userInput` was concatenated into SQL before `sql()`, quotes and SQL tokens inside the input can alter the statement. The fluent API cannot fix unsafe string concatenation performed beforehand.

Nor can you pass **table/column names or `ORDER BY` direction** via `:columnName` expecting the DB to treat them as identifiers. Bound placeholders represent values, not SQL syntax:

```java
String orderColumn = switch (sortKey) {
    case "id" -> "id";
    case "title" -> "title";
    default -> throw new IllegalArgumentException("Invalid sort field");
};

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE tenant_id = :tenantId ORDER BY " + orderColumn)
    .param("tenantId", tenantId)
    .query(TaskView.class)
    .list();
```

This is integration code with `sortKey`/`tenantId` provided; **only the two whitelisted literals** are inserted into the SQL. Data is still bound via `:tenantId`. If dynamic ascending/descending direction is needed, whitelist the direction as well rather than using raw user strings.

## 17. `IN` Lists When Starting with `sql()`

With named placeholders, Spring JDBC supports expanding a collection into multiple `?` markers for standard SQL `IN`:

```java
List<Long> ids = List.of(1L, 3L, 5L);

List<TaskView> tasks = client
    .sql("SELECT id, title, status FROM task " +
         "WHERE id IN (:ids) ORDER BY id")
    .param("ids", ids)
    .query(TaskView.class)
    .list();
```

The SQL statement is prepared according to the number of elements; the database still receives each value via JDBC binding. There is no need to concatenate `"1,3,5"` into the SQL string.

If `ids` is empty, `IN ()` is not portable SQL syntax and can fail. At the repository layer, define an explicit policy:

```java
public List<TaskView> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return client.sql(
            "SELECT id, title, status FROM task " +
            "WHERE id IN (:ids) ORDER BY id")
        .param("ids", ids)
        .query(TaskView.class)
        .list();
}
```

This is an illustrative method requiring a `client` field and `TaskView` record; returning an empty list fits **searching within an empty set**. For `DELETE` or `UPDATE` operations, never turn an empty ID set into a delete/update statement **without a `WHERE` clause**.

Very large collections may hit database limits on placeholder count or `IN` clause size; consider batching, temporary tables, or database-specific capabilities. `sql()` does not automatically guarantee performance or allow unlimited binding.

## 18. Transactions: `sql()` Is Not a Commit Boundary

Example of a service running two SQL statements:

```java
@Transactional
public void markAndAudit(long taskId) {
    client.sql("UPDATE task SET status = :status WHERE id = :id")
          .param("status", "DONE")
          .param("id", taskId)
          .update();

    client.sql(
          "INSERT INTO task_audit(task_id, action) VALUES (:id, :action)")
          .param("id", taskId)
          .param("action", "MARK_DONE")
          .update();
}
```

This is integration code requiring `task_audit`, a Spring-managed service bean, and a properly configured transaction manager. Each `sql()` builds a separate JDBC operation; atomicity across the two operations must come from an **actually intercepted `@Transactional`** or a `TransactionTemplate` using the same DataSource/transaction manager.

If the second operation throws an unchecked exception out of the boundary, Spring rolls back the matching transaction by default. Without a transaction, each statement may auto-commit independently. `sql()` does not create an implicit transaction around every command in the same Java method.

**Be careful:** calling a `@Transactional` method on the same bean in proxy mode can bypass the interceptor; and with multiple distinct `DataSource`s, a local JDBC transaction manager does not automatically create a distributed transaction across all of them.

## 19. Runnable Java 17+ Example: Seeing the Starting Point and Execution Point Clearly

The example uses **Spring JDBC 6.1.14**, **H2 2.2.224**, and JDK 17+. Spring Boot is not required. It verifies:

1. `JdbcClient.create(DataSource)` created once.
2. `sql(...)` + `paramSource(record)` + `update()` insert.
3. `sql(...)` + `param("name", value)` insert and binding `NULL` with a SQL type.
4. `sql(...)` + positional `params(...)` + `query(Long.class).single()`.
5. `sql(...)` + named `param(...)` + `query(String.class).single()`.
6. `sql(...)` + named `params(Map)` + `query(TaskView.class).list()`.
7. `sql(...)` + `optional()` for a non-existent ID.
8. `sql(...)` + list parameter `IN (:ids)`.
9. `sql(...)` + `update()` returning affected row count.
10. `TransactionTemplate` rolling back an update on the same DataSource.

### 19.1. Creating `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>jdbcclient-sql-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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

### 19.2. Creating `src/main/java/JdbcClientSqlDemo.java`

```java
import java.sql.Types;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class JdbcClientSqlDemo {
    public record TaskInput(
            long id, long tenantId, String title,
            String status, Integer priority) {}

    public record TaskView(long id, String title, String status) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:sql_start;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        // DDL is executed separately with JdbcTemplate.
        // JdbcClient focuses on business queries and updates.
        JdbcTemplate schema = new JdbcTemplate(ds);
        schema.execute(
            "CREATE TABLE task (" +
            "id BIGINT PRIMARY KEY, " +
            "tenant_id BIGINT NOT NULL, " +
            "title VARCHAR(100) NOT NULL, " +
            "status VARCHAR(20) NOT NULL, " +
            "priority INTEGER)"
        );

        JdbcClient client = JdbcClient.create(ds);

        // 1) sql() -> paramSource(record) -> update(): insert first row.
        int inserted = client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .paramSource(new TaskInput(
                1L, 10L, "Learn JDBC", "OPEN", 1))
            .update();
        System.out.println("Inserted via record: " + inserted);

        // 2) Named parameters individually by name.
        client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .param("id", 2L)
            .param("tenantId", 10L)
            .param("title", "Review SQL")
            .param("status", "OPEN")
            .param("priority", 2)
            .update();

        // 3) NULL can be bound with a JDBC SQL type.
        client.sql(
                "INSERT INTO task(id, tenant_id, title, status, priority) " +
                "VALUES (:id, :tenantId, :title, :status, :priority)")
            .param("id", 3L)
            .param("tenantId", 20L)
            .param("title", "Ship")
            .param("status", "DONE")
            .param("priority", null, Types.INTEGER)
            .update();

        // 4) Positional ? + params(...) + typed result.
        long count = client
            .sql("SELECT COUNT(*) FROM task WHERE tenant_id = ?")
            .params(10L)
            .query(Long.class)
            .single();
        System.out.println("Tenant 10 count: " + count);

        // 5) Named parameter + single value.
        String firstTitle = client
            .sql("SELECT title FROM task WHERE id = :id")
            .param("id", 1L)
            .query(String.class)
            .single();
        System.out.println("Title #1: " + firstTitle);

        // 6) Named params Map + record mapping for multiple rows.
        List<TaskView> open = client
            .sql(
                "SELECT id, title, status FROM task " +
                "WHERE tenant_id = :tenantId AND status = :status " +
                "ORDER BY id")
            .params(Map.of("tenantId", 10L, "status", "OPEN"))
            .query(TaskView.class)
            .list();
        List<String> titles = open.stream()
            .map(TaskView::title)
            .toList();
        System.out.println("Open tasks: " + titles);

        // 7) Optional distinguishes missing row.
        Optional<String> missing = client
            .sql("SELECT title FROM task WHERE id = :id")
            .param("id", 999L)
            .query(String.class)
            .optional();
        System.out.println("Missing is empty: " + missing.isEmpty());

        // 8) Collection expanded in IN clause.
        List<Long> matching = client
            .sql(
                "SELECT id FROM task " +
                "WHERE tenant_id = :tenantId AND id IN (:ids) " +
                "ORDER BY id")
            .param("tenantId", 10L)
            .param("ids", List.of(1L, 3L))
            .query(Long.class)
            .list();
        System.out.println("IN result: " + matching);

        // 9) update() returns the affected row count.
        int changed = client
            .sql("UPDATE task SET status = :status WHERE id = :id")
            .param("status", "DONE")
            .param("id", 2L)
            .update();
        System.out.println("Updated: " + changed);

        long stillOpen = client
            .sql("SELECT COUNT(*) FROM task WHERE status = :status")
            .param("status", "OPEN")
            .query(Long.class)
            .single();
        System.out.println("Still open: " + stillOpen);

        // 10) sql() does not control transactions on its own.
        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(ds));
        try {
            tx.executeWithoutResult(status -> {
                client.sql(
                        "UPDATE task SET status = :status WHERE id = :id")
                    .param("status", "CANCELLED")
                    .param("id", 1L)
                    .update();

                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Transaction rolled back");
        }

        String statusAfter = client
            .sql("SELECT status FROM task WHERE id = :id")
            .param("id", 1L)
            .query(String.class)
            .single();
        System.out.println("Task #1 after rollback: " + statusAfter);
    }
}
```

### 19.3. Running the Program

Place the two files in this structure:

```text
jdbcclient-sql-demo/
├── pom.xml
└── src/main/java/JdbcClientSqlDemo.java
```

JDK 17+ and Apache Maven are required. In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=JdbcClientSqlDemo
```

Lines produced by `System.out.println` in the example itself:

```text
Inserted via record: 1
Tenant 10 count: 2
Title #1: Learn JDBC
Open tasks: [Learn JDBC, Review SQL]
Missing is empty: true
IN result: [1]
Updated: 1
Still open: 1
Transaction rolled back
Task #1 after rollback: OPEN
```

Plugins, loggers, or Maven may print additional messages. The stdout listing above only shows lines printed by the program itself.

### 19.4. Why Does the Output Have Those Values?

- `Inserted via record: 1`: `sql(...)` receives `INSERT`, `paramSource(TaskInput)` supplies the exact five names, and `update()` executes one successful insert.
- `Tenant 10 count: 2`: there are two tasks belonging to tenant 10, counted with one `?` placeholder and `params(10L)`.
- `Title #1`: the `:id` named placeholder receives 1 and `query(String.class).single()` returns `Learn JDBC`.
- `Open tasks`: combining `:tenantId`/`:status` fetches the two OPEN tasks ordered by id, mapped into `TaskView` records.
- `Missing is empty: true`: querying ID 999 returns no rows, and `optional()` represents the absent result.
- `IN result: [1]`: the ID set `[1,3]` is bound, but `tenant_id = 10` only matches ID 1.
- `Updated: 1`: changes task 2's status to DONE, affecting only one row.
- `Still open: 1`: out of the three tasks, only task 1 remains with status OPEN.
- `Transaction rolled back` and `Task #1 after rollback: OPEN`: `TransactionTemplate` rolls back changing task 1 to CANCELLED because of the unchecked exception. Even though each command started with `sql()`, transaction decisions belong to the Spring transaction manager.

`DriverManagerDataSource` in the demo is a simple connection source **without a connection pool**. Production applications typically use a Spring-managed DataSource/pool and appropriate transaction configuration. The example demonstrates Spring JDBC functionality, not a full production operational setup.

## 20. Typical Mistakes When Learning `sql()`

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Writing `client.sql("UPDATE ...")` and discarding the result | Only creates a statement spec, does not run the write. | End with `update()`. |
| Writing `client.sql("SELECT ...").list()` | `StatementSpec` does not have `list()` directly. | Call `query(Class/RowMapper).list()`. |
| Writing `client.sql("SELECT ...").query().single()` | `ResultQuerySpec` has no resolver named `single()`. | `query(Type.class).single()` or `query().singleValue()/singleRow()`. |
| Using `.param(0, value)` | Explicit JDBC index starts at 1. | Use `.param(1, value)` or positional `.param(value)`. |
| Changing `?` order in SQL without updating `params(...)` order | Binds wrong values. | Keep the order aligned or use `:name`. |
| Using `.param(":id", id)` | The binding name does not include `:`; only the placeholder has `:`. | `.param("id", id)`. |
| Using `Map.of("note", null)` | `Map.of` throws `NullPointerException`. | `.param("note", null, Types.VARCHAR)` or `MapSqlParameterSource`. |
| Passing a column name through a placeholder | Placeholders are **values**, not SQL identifiers. | Whitelist identifiers and concatenate safe literals. |
| Concatenating raw user input into the String passed to `sql()` | Fluent API does not prevent injection in already-concatenated SQL. | Use `:name` or `?`; do not concatenate values into SQL. |
| Using `single()` for multi-row queries | Multiple results throw a cardinality exception. | Use `list()` or fix SQL to be unique. |
| Using `optional()` to hide duplicates | `optional()` accepts only 0 or 1, never picks the first row. | Fix SQL/invariants or use a list. |
| Forgetting `close()` on `stream()` | Can leak cursors/statements. | `try-with-resources` around the stream. |
| Thinking `JdbcClient` auto-generates repositories/JPA entities | `JdbcClient` still requires SQL and appropriate mappers. | Explicitly write SQL, aliases, and result types. |
| Thinking all `sql()` calls in the same method form a transaction | There is no implicit transaction boundary. | Configured `@Transactional`/`TransactionTemplate`. |
| Reusing a `StatementSpec` across requests | Holds binding state unsuitable for sharing. | Build a new chain from `client.sql(...)` per operation. |
| Using `JdbcClient` for complex batch/stored procedures | The fluent facade focuses on common operations. | Use `JdbcTemplate`, `NamedParameterJdbcTemplate`, or `SimpleJdbcInsert/Call` when needed. |

## 21. Checklist When Reviewing a Chain Starting with `sql()`

1. **Is the SQL kind clear?** `SELECT` goes through a query resolver, `INSERT/UPDATE/DELETE` through `update()`.
2. **Is the SQL String structurally fixed?** All user data must be bound; dynamic identifiers must be whitelisted.
3. **Is the parameter style consistent?** Choose positional `?` or named `:name` per query; do not mix arbitrarily.
4. **Are all parameters supplied?** Enough `?` positions, all `:name` keys/getters present with matching case.
5. **Is the explicit index of `param(index,value)` 1-based?**
6. **Are there nullable inputs?** `Map.of` rejects null; is an explicit `Types` needed?
7. **Is there an `IN (:ids)` clause?** Handle empty collections and database parameter count limits.
8. **Is the right mapping chosen?** `query(String.class)` for one column, `query(TaskView.class)` or `query(mapper)` for multiple columns.
9. **Is the right cardinality chosen?** `single()`, `optional()`, and `list()` represent different contracts.
10. **Are ordering and pagination present for multi-row queries?** Avoid unstable results and loading too many records.
11. **Is the right terminal called?** `sql()` alone does not execute writes; `query(Class)` prepares mapping while the resolver fetches results.
12. **Is the affected row count from `update()` checked when business logic requires exactly one?**
13. **Is the transaction configured outside the chain?** Do not confuse fluent syntax with a transaction boundary.
14. **Has it been tested on the actual database dialect?** Data types, generated keys, column/alias names, and SQL syntax may differ.
15. **Are features outside the facade's scope needed?** Use lower-level JDBC templates for advanced batch/callback/procedure cases.

### Key Points to Remember

- **`JdbcClient.sql(String)` is the starting point of every fluent JDBC operation** on the client and returns `JdbcClient.StatementSpec`.
- `sql()` only **declares the SQL statement**; it does not return data or execute writes on its own.
- After `sql()`, bind via `.param(...)`, `.params(...)`, or `.paramSource(...)`, then choose an execution path.
- `query(Class/RowMapper).single()/optional()/list()` are for mapped read contracts; `query().singleRow()/singleValue()/listOfRows()` are for results not pre-mapped to a class.
- **`update()`** executes INSERT/UPDATE/DELETE and returns the affected row count; generated keys require the appropriate API/driver.
- `JdbcClient` uses Spring JDBC underneath and **does not replace SQL, transactions, authorization checks, cursor management, or result contracts**.
- Build a new chain from `sql(...)` each time; never share stateful `StatementSpec` instances across concurrent operations.

### References

- Spring Framework 6.1.14 — `JdbcClient` (interface, `create`, `sql`): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework 6.1.14 — `JdbcClient.StatementSpec` (bind, query, update): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html
- Spring Framework 6.1.14 — `JdbcClient.MappedQuerySpec` (`single`, `list`, `optional`, `stream`): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
- Spring Framework 6.1.14 — `JdbcClient.ResultQuerySpec`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html
- Spring Framework Reference — Unified JDBC Query/Update Operations: `JdbcClient`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
