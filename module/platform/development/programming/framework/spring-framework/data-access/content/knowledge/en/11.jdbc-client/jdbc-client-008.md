# JdbcClient Builds on JdbcTemplate Infrastructure Rather Than Changing JDBC Fundamentals

## 1. Goal: Distinguishing the Convenient API from the Execution Mechanism

In Spring Framework, `JdbcClient` lets you write SQL queries in a *fluent* syntax (chaining method calls) instead of passing multiple arguments to `JdbcTemplate` overloads. For example:

```java
long count = jdbcClient
    .sql("SELECT COUNT(*) FROM customer WHERE active = ?")
    .param(true)
    .query(Long.class)
    .single();
```

The code is more concise, yet that does not mean Spring replaced JDBC with a new data engine. The query is still sent to the database through a `DataSource`, `Connection`, `PreparedStatement`, JDBC driver, and familiar SQL/transaction rules.

**Core message:** `JdbcClient` is a **unified, convenient API layer** sitting on top of `JdbcTemplate` and `NamedParameterJdbcTemplate`. It **delegates execution** to those templates rather than inventing its own connection protocol, transaction mechanism, relational mapping system, or SQL engine.

This lesson answers:

1. Where does `JdbcClient` sit among Spring JDBC classes and from which version can it be used?
2. What does a chain like `sql().param().query().list()` or `update()` actually do underneath?
3. Do the rules for parameter binding, `RowMapper`, result handling, transactions, pooling, and exceptions change?
4. When should you pick `JdbcClient`, and when should you still use `JdbcTemplate`, `NamedParameterJdbcTemplate`, or another tool?
5. How can you verify this with Java/Spring examples and a standalone Java 17 program simulating the delegation mechanism?

## 2. Layer Map: JdbcClient Is Not a JDBC Driver

Look at the responsibility diagram:

```text
Application / Service / Repository
            |
            | Fluent API:
            | .sql(...).param(...).query(...).list()
            v
org.springframework.jdbc.core.simple.JdbcClient
            |
            | Delegates common operations
            +------------------------------+
            |                              |
            v                              v
      JdbcTemplate             NamedParameterJdbcTemplate
      ("?" params)             (":name" params)
            |                              |
            |                         resolves names to
            |                         JDBC positions
            |                              |
            +-------------+----------------+
                          |
                          v
                    Spring JDBC core
            (resources, callbacks, translation)
                          |
                          v
                       DataSource
                          |
                          v
                 JDBC Connection / Driver
                          |
                          v
                    Database Server
```

Points to distinguish:

- **`JdbcClient`**: fluent API for common JDBC queries/updates; since Spring Framework **6.1**.
- **`JdbcTemplate`**: Spring JDBC component responsible for acquiring/releasing resources, executing SQL, mapping results, and translating exceptions.
- **`NamedParameterJdbcTemplate`**: supports named parameters, translates `:id` into `?` markers and corresponding bind positions, then delegates to the underlying JDBC template.
- **`DataSource`**: source of `Connection` instances, optionally backed by a connection pool such as HikariCP.
- **JDBC driver**: implements the protocol for a specific DB, handling I/O, SQL types, and data.
- **Database**: actually parses SQL, enforces keys/constraints, executes queries, and commits/rolls back transactions.

`JdbcClient` **does not** replace `DataSource`, **does not** execute SQL in Java instead of the DB, **does not** open "non-JDBC" connections, and **does not** turn into an ORM like JPA/Hibernate.

### Since Which Version?

`org.springframework.jdbc.core.simple.JdbcClient` was introduced in **Spring Framework 6.1**. If a Spring Framework 5.x or 6.0 project cannot find this class, it is not just a missing import: that library version does not support the API yet. Spring Boot uses the Spring Framework version managed by its dependency BOM; check the **actual** Spring Framework version in your application rather than guessing from tutorial syntax.

The foundational examples in this lesson use capabilities available since Spring Framework 6.1. A few *per-statement* configuration options were added in newer versions; if you need to call such APIs, check the exact version's Javadoc to avoid copying Spring 7.x methods into a Spring 6.1 application.

## 3. Why Add JdbcClient When JdbcTemplate Already Works Well?

`JdbcTemplate` already covers most common needs: `query`, `queryForObject`, `update`, `batchUpdate`, etc. `NamedParameterJdbcTemplate` handles SQL with many parameters by name.

Before `JdbcClient`, a project might mix two styles:

```java
// Positional parameter:
Long count1 = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer WHERE active = ?",
    Long.class,
    true
);

// Named parameter:
Long count2 = namedParameterJdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM customer WHERE active = :active",
    new MapSqlParameterSource("active", true),
    Long.class
);
```

When reading code, learners had to memorize the right overloads and parameter order for each template. `JdbcClient` offers one unified API surface:

```java
// One API, "?" parameter style:
Long count1 = jdbcClient.sql(
        "SELECT COUNT(*) FROM customer WHERE active = ?"
    )
    .param(true)
    .query(Long.class)
    .single();

// Still one API, ":active" named parameter:
Long count2 = jdbcClient.sql(
        "SELECT COUNT(*) FROM customer WHERE active = :active"
    )
    .param("active", true)
    .query(Long.class)
    .single();
```

Both snippets express **the exact same kind of JDBC operation**. The difference lies in how the request is expressed, not in changing the transaction manager, swapping the database driver, or switching to reactive I/O.

### What Improves

- Call chains read closely to the workflow: **pick SQL → bind params → pick result type → fetch result**.
- Positional and named parameters share one abstraction, making repository style easier to standardize.
- Clear terminal operations: `list()`, `single()`, `optional()`, `stream()`, and `update()`.
- Supports mapping via `RowMapper` or target class for common queries.
- `JdbcClient.create(existingJdbcTemplate)` can reuse existing delegate configuration.

### What Is NOT "Automatically Solved"

- SQL must still obey DB syntax and have proper indexes/query design.
- Parameters must still be bound with the right types to prevent SQL injection.
- Transactions and authorization still need to be defined explicitly.
- Network errors, dropped connections, locks, deadlocks, and constraint violations still happen.
- A 1-to-N `JOIN` can still multiply rows; `list()` does not auto-group parent–child hierarchies.
- Queries returning huge row counts still cost network, memory, and time.
- You do not automatically get batching, stored procedures, ORM entity tracking, lazy loading, or non-blocking execution.

## 4. From Fluent Chain to JDBC: Which Part Acts When?

Example:

```java
List<Customer> customers = jdbcClient
    .sql("""
         SELECT id, name
         FROM customer
         WHERE tenant_id = :tenantId
         ORDER BY id
         """)
    .param("tenantId", tenantId)
    .query(CUSTOMER_MAPPER)
    .list();
```

This is code **inside a Spring repository that already has `jdbcClient`, `tenantId`, `Customer`, and `CUSTOMER_MAPPER`**, not a standalone program.

Conceptual processing flow:

1. `sql(String)` creates/starts a statement specification with the application-supplied SQL.
2. `param("tenantId", tenantId)` registers a named parameter to bind. It is not a way to modify SQL structure dynamically.
3. `query(CUSTOMER_MAPPER)` specifies how to read one row into a `Customer`.
4. `list()` is a **terminal operation** fetching all mapped results. When the query executes, the delegate performs the work via Spring JDBC.
5. Underneath, the infrastructure acquires an appropriate `Connection`, prepares the JDBC statement, translates named parameters to positional placeholders if needed, binds values, executes the SQL, iterates the `ResultSet`, maps rows, closes resources, and releases the connection according to the transaction.

Never say that every `sql()` call immediately opens a socket or sends a query. The API builds the specification first and executes only when an appropriate terminal method is called. Also never infer that `JdbcClient` optimizes SQL better than the DB just because it uses fluent syntax.

In traditional Spring JDBC, the same work is done by `JdbcTemplate` and callbacks. `JdbcClient` mainly **reduces boilerplate and clarifies intent**, while DB behavior still follows JDBC mechanisms.

## 5. Creating JdbcClient: Reusing Existing Infrastructure

Key factory methods:

```java
JdbcClient clientA = JdbcClient.create(dataSource);

JdbcClient clientB = JdbcClient.create(jdbcTemplate);

JdbcClient clientC = JdbcClient.create(namedParameterJdbcTemplate);
```

Assume `dataSource` is a `javax.sql.DataSource`, and the two templates are already constructed with the right Spring JDBC types. What do these overloads indicate?

| Creation method | Meaning | When to choose |
| --- | --- | --- |
| `JdbcClient.create(dataSource)` | Creates a client operating on the specified data source | Standalone Spring JDBC examples or simple setups |
| `JdbcClient.create(jdbcTemplate)` | Uses the existing `JdbcOperations` delegate | When a template already configures `DataSource`, exceptions, timeouts, or custom settings |
| `JdbcClient.create(namedParameterJdbcTemplate)` | Uses the existing `NamedParameterJdbcOperations` | When an existing named template's configuration should be reused |

To ensure the same data source and settings as the rest of the application, **creating from a Spring-managed `JdbcTemplate` bean** is usually clearer than manually instantiating an extra DataSource with mismatched settings.

A concise Spring configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class JdbcClientConfig {
    @Bean
    JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
        return JdbcClient.create(jdbcTemplate);
    }
}
```

The application needs a pre-configured `JdbcTemplate` bean. In Spring Boot environments, a `JdbcClient` bean may already be auto-configured depending on version and configuration; **do not declare a duplicate bean just because the example above exists**. If multiple `DataSource`s exist, specify clearly which client connects to which DB, e.g. via qualifiers, instead of assuming "there is only one source".

Note: if the application deeply customizes its template (e.g. a custom exception translator or statement settings), creating `JdbcClient` from that configured delegate preserves the execution path. Do not create a separate template from the same URL and assume all settings match.

## 6. Sample SQL and Data Types

Consider an H2 or PostgreSQL test DB with a customer table:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO customer (id, tenant_id, name, active, balance) VALUES
    (1, 10, 'Lan',  TRUE,  120.00),
    (2, 10, 'Minh', FALSE,  70.00),
    (3, 10, 'Vy',   TRUE,   90.00),
    (4, 20, 'An',   TRUE,  150.00);
```

Suppose the repository implements these operations:

- Get a customer by ID and tenant.
- List active customers of a tenant.
- Count active customers.
- Rename a customer belonging to an authorized tenant.

The columns `tenant_id`, `active`, and `balance` are not auto-created or relationship-discovered by Spring like an ORM. **SQL itself determines which columns are read and which filter predicates apply.**

When querying `WHERE tenant_id=10 AND active=TRUE ORDER BY id`, the result includes Lan and Vy; Minh is inactive and An belongs to tenant 20.

## 7. Positional and Named Parameters: Same JDBC Binding Rules

### 7.1. Positional Binding

```java
Optional<Customer> found = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = ? AND id = ?"
    )
    .param(10L)
    .param(3L)
    .query((rs, rowNum) ->
        new Customer(rs.getLong("id"), rs.getString("name"))
    )
    .optional();
```

Assuming `Customer` is `record Customer(long id, String name)`, the result is an `Optional` containing Vy. `param(value)` registers values in the **order `?` markers appear**; the pair above puts tenant first, ID second. Swapping the order may not throw an error if both are numbers, yet it will return wrong results.

JDBC numbers parameters starting from **1**, so with the `param(int jdbcIndex, Object value)` overload, pass a 1-based JDBC index rather than a 0-based Java array index.

### 7.2. Named Binding

```java
Optional<Customer> found = jdbcClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId AND id = :id"
    )
    .param("tenantId", 10L)
    .param("id", 3L)
    .query((rs, rowNum) ->
        new Customer(rs.getLong("id"), rs.getString("name"))
    )
    .optional();
```

`:tenantId` and `:id` are Spring-side names; the named-parameter layer translates them into matching JDBC positions. The JDBC driver does not need to understand `:tenantId` syntax to work.

With a large number of parameters, names are usually clearer than positions. Still, verify exact names in SQL and during binding. Do not mix both binding styles arbitrarily within one statement; keep one clear style per SQL query.

### 7.3. Separating Data from SQL Structure

Unsafe example:

```java
String unsafeSql =
    "SELECT id FROM customer WHERE name = '" + userInput + "'";
```

Concatenating user-supplied values directly into SQL risks SQL injection or syntax errors. Correct approach:

```java
List<Long> ids = jdbcClient
    .sql("SELECT id FROM customer WHERE name = :name")
    .param("name", userInput)
    .query(Long.class)
    .list();
```

The `:name` placeholder is a bound **value**, not a slot for a table name, column name, or `ORDER BY`. If a column name is chosen dynamically, validate against an allowed list of columns in code; do not expect `.param("column", userInput)` to safely insert a SQL identifier.

### 7.4. NULL and SQL Types

When binding null with an explicit column type, `JdbcClient` provides `param("name", value, sqlType)` and `param(index, value, sqlType)` overloads using constants from `java.sql.Types`.

```java
jdbcClient.sql(
        "UPDATE customer SET name = :name WHERE id = :id"
    )
    .param("name", nullableName, java.sql.Types.VARCHAR)
    .param("id", 1L)
    .update();
```

This is only an API illustration; the sample schema declares `name NOT NULL`, so passing null violates the DB constraint and throws an exception. **Specifying a SQL type does not override `NOT NULL` rules.** Also, `WHERE name = NULL` does not match rows with null names; use `IS NULL` per SQL semantics.

## 8. Result Mapping Is Still About RowMapper or Target Types

A query returns a `ResultSet`. `JdbcClient` can accept a `RowMapper<T>`:

```java
RowMapper<Customer> mapper = (rs, rowNum) ->
    new Customer(
        rs.getLong("id"),
        rs.getString("name")
    );

List<Customer> customers = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = :tenantId ORDER BY id"
    )
    .param("tenantId", 10L)
    .query(mapper)
    .list();
```

Each time `RowMapper` receives a row, it converts that row into a Java object. `rowNum` is the 0-based mapping index, **not a DB ID**; `rs.next()` is called by the template infrastructure before invoking the mapper.

`JdbcClient` also offers `query(Customer.class).list()`, allowing Spring to map by class/record structure and column names when compatible. For example, if a record has two components `id` and `name` and the query returns those matching columns:

```java
List<Customer> customers = jdbcClient.sql(
        "SELECT id, name FROM customer WHERE tenant_id = :tenantId ORDER BY id"
    )
    .param("tenantId", 10L)
    .query(Customer.class)
    .list();
```

That **does not turn `JdbcClient` into Hibernate**. Spring maps data from query results into Java objects; it does not maintain a persistence context, track entity changes, or perform automatic lazy loading or flushing like JPA.

When mapping is complex or needs handling for SQL NULL, enums, JSON, or non-trivial column aliases, an **explicit `RowMapper`** gives better control over conversions and error handling. With a 1-to-N `LEFT JOIN`, the JOIN still returns multiple rows sharing the same parent key; `.list()` does not automatically group parent–child structures. When aggregating the whole result set, `JdbcClient.StatementSpec.query(ResultSetExtractor<T>)` or `JdbcTemplate` directly is the right choice.

## 9. list, single, optional, and stream Results

| Call form | Meaning | Cases to watch |
| --- | --- | --- |
| `.query(mapper).list()` | Returns a list of mapped objects | 0 rows → empty list; can use significant RAM on large sets |
| `.query(Target.class).single()` | Requires **exactly one** result object | 0 or >1 rows → Spring result-size exception |
| `.query(Target.class).optional()` | 0 or 1 object in `Optional` | >1 row is still an error; not "take first row if many" |
| `.query(mapper).stream()` | Returns a lazily read `Stream` | **Must close the stream** after use; holds JDBC resources while consuming |
| `.query(ResultSetExtractor<T>)` | Callback processing the entire `ResultSet` | Handles `rs.next()` itself; resources belong to the template |
| `.query(RowCallbackHandler)` | Processes each row via callback | Callback does not automatically return `List<T>` |
| `.update()` | Executes `INSERT`, `UPDATE`, or `DELETE` | Returns `int` affected row count; not an auto-generated ID |

`single()` differs from a SQL query with `LIMIT 1`: `single()` checks the result expectation after the DB returns rows, whereas `LIMIT 1` caps rows at the DB. If a table has two records with a non-unique business key, adding `LIMIT 1` can hide inconsistent data; enforce proper keys/constraints to guarantee a single result.

`optional()` expresses the case where a key might not exist:

```java
Optional<Customer> found = jdbcClient
    .sql("SELECT id, name FROM customer WHERE id = :id")
    .param("id", 999L)
    .query(Customer.class)
    .optional();
// When id=999 does not exist: Optional.empty().
```

If you used `single()` for ID 999 instead, Spring would throw because the required object is missing. When two rows are returned, neither `single()` nor `optional()` silently ignores the extra row.

### 9.1. Streams Must Be Closed

```java
try (var stream = jdbcClient.sql(
        "SELECT id, name FROM customer ORDER BY id"
    )
    .query(Customer.class)
    .stream()) {
    long count = stream
        .filter(c -> c.name().startsWith("L"))
        .count();
}
```

This `Stream` is not a "pre-built list returned to you": it can remain tied to open query resources and must be closed with `try-with-resources`. It also **does not guarantee** that the DB driver streams one row at a time with constant RAM; fetch size, transactions, the driver, and how the client consumes the stream determine actual behavior. Never return a JDBC-backed stream outside a transaction/request whose lifecycle you cannot control.

## 10. UPDATE Is Still a JDBC Update, Not Automatic Entity Saving

Example of renaming:

```java
int affected = jdbcClient
    .sql("""
         UPDATE customer
         SET name = :name
         WHERE tenant_id = :tenantId AND id = :id
         """)
    .param("name", "Lan Anh")
    .param("tenantId", 10L)
    .param("id", 1L)
    .update();
```

`affected` is the number of rows the DB reports as affected per JDBC. If `affected == 0`, no row may have matched the tenant/ID; do not assume "one customer was updated" just because no exception was thrown. If `affected > 1` in an operation expected to target a unique key, investigate the SQL/schema and business contract.

`JdbcClient` does not track a record created from `SELECT` and automatically emit `UPDATE` when you modify a Java field. To write data, the application still issues SQL `UPDATE`/`INSERT`/`DELETE`, or uses an ORM if entity tracking is genuinely needed.

For auto-generated keys, `JdbcClient.StatementSpec` provides `update(KeyHolder)` overloads when supported by the driver and Spring version; verify the auto-generated key schema and how the DB returns keys. An `affected` count is not a generated key. When advanced key management or batching is needed, `SimpleJdbcInsert`/`JdbcTemplate` are also solid choices.

## 11. A Practical Repository Reusing an Existing JdbcTemplate

The example below is written for **Java 17+ and a Spring Framework 6.1+ application** that already has a `JdbcTemplate` bean, a `DataSource`, and the `customer` table from section 6. This is Spring integration code requiring `spring-jdbc`, `spring-context`, and the corresponding DB driver. **It cannot compile standalone with the JDK alone.**

File `CustomerJdbcClientRepository.java`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerJdbcClientRepository {
    public record Customer(long id, String name, boolean active) {}

    private static final RowMapper<Customer> MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getBoolean("active")
        );

    private final JdbcClient client;

    public CustomerJdbcClientRepository(JdbcTemplate template) {
        // Reuse the application's existing JdbcTemplate.
        this.client = JdbcClient.create(template);
    }

    public List<Customer> listActive(long tenantId) {
        return client.sql("""
                SELECT id, name, active
                FROM customer
                WHERE tenant_id = :tenantId AND active = :active
                ORDER BY id
                """)
            .param("tenantId", tenantId)
            .param("active", true)
            .query(MAPPER)
            .list();
    }

    public Optional<Customer> findById(long tenantId, long id) {
        return client.sql("""
                SELECT id, name, active
                FROM customer
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("tenantId", tenantId)
            .param("id", id)
            .query(MAPPER)
            .optional();
    }

    public long countActive(long tenantId) {
        Long count = client.sql("""
                SELECT COUNT(*)
                FROM customer
                WHERE tenant_id = :tenantId AND active = :active
                """)
            .param("tenantId", tenantId)
            .param("active", true)
            .query(Long.class)
            .single();
        return count;
    }

    public int rename(long tenantId, long id, String newName) {
        return client.sql("""
                UPDATE customer
                SET name = :newName
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("newName", newName)
            .param("tenantId", tenantId)
            .param("id", id)
            .update();
    }
}
```

### Results on Sample Data

- `listActive(10)` returns two records: Lan (ID 1) and Vy (ID 3), per `ORDER BY id`.
- `listActive(20)` returns An (ID 4).
- `findById(10, 2)` returns an `Optional` containing Minh even though `active=false`, because the SQL only filters by tenant and ID.
- `findById(10, 4)` returns `Optional.empty()`: An belongs to tenant 20 and must not appear in a tenant 10 query.
- `countActive(10)` returns `2`.
- `rename(10, 1, "Lan Anh")` returns affected row count `1` when data and DB permissions permit; the method **actually mutates data**, so run it only against a test DB or within an authorized business workflow.

Key point: the `client` field holds a shared configured `JdbcClient` instance, while **each `sql(...).param(...)` chain describes a separate call's statement**. Never store a mutable/incomplete `StatementSpec` in a singleton repository field and let concurrent requests call `param(...)` on it.

If you want to reuse a container-provided `JdbcClient` bean, you can inject that bean directly, provided it uses the intended `DataSource` and configuration. This lesson chooses `JdbcClient.create(template)` to clearly highlight the **delegation relationship** requested by the topic.

## 12. Transactions: The Fluent API Does Not Create a Business Transaction

Suppose an operation must perform **two updates** to succeed. Two separate `client.sql(...).update()` calls **do not automatically form an atomic unit just because they use the same `JdbcClient` variable**.

In Spring, transactions are coordinated by the transaction infrastructure and transaction manager. Illustrative service code:

```java
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerChangeService {
    private final JdbcClient client;

    public CustomerChangeService(JdbcClient client) {
        this.client = client;
    }

    @Transactional
    public void renameAndAudit(
            long tenantId, long customerId, String newName) {
        int count = client.sql("""
                UPDATE customer
                SET name = :name
                WHERE tenant_id = :tenantId AND id = :id
                """)
            .param("name", newName)
            .param("tenantId", tenantId)
            .param("id", customerId)
            .update();

        if (count != 1) {
            throw new IllegalStateException(
                "Expected exactly one customer update"
            );
        }

        client.sql("""
                INSERT INTO audit_log(tenant_id, customer_id, event_type)
                VALUES (:tenantId, :id, :event)
                """)
            .param("tenantId", tenantId)
            .param("id", customerId)
            .param("event", "RENAME")
            .update();
    }
}
```

**Prerequisites for this example:** an `audit_log` table with matching columns and a transaction manager linked to the exact `DataSource`. When the service bean is invoked through Spring's `@Transactional` mechanism (not an internal self-call bypassing the proxy), both SQL statements can join the same transaction. If the `INSERT` fails and throws an exception out of the method, Spring rolls back per transaction policy. Without a transaction, the first `UPDATE` could already be committed before the second `INSERT` fails.

`JdbcClient` does not make these commands atomic in place of `@Transactional`. Transactions also depend on the datasource/driver, isolation level, constraints, locks, and exception semantics. Losing connection during commit can leave the transaction outcome indeterminate; never blindly retry writes. With `@Transactional(readOnly = true)`, the read-only hint does not automatically block every write statement across all DBs/drivers.

**Underneath, execution still follows Spring `DataSourceUtils` and transaction-bound connections** just like `JdbcTemplate`. Never call `connection.close()`, `commit()`, or `rollback()` inside a `JdbcClient` mapper to "fix" a transaction.

## 13. Connections and Connection Pools: Still Through DataSource

Both `JdbcClient` and `JdbcTemplate` ultimately obtain JDBC connections from a `DataSource`. If `DataSource` is configured with HikariCP:

- The pool still controls connection counts, borrow timeouts, liveness checks, and replacing broken connections.
- Closing a connection borrowed from the pool normally **returns it to the pool**, rather than tearing down a socket every time.
- Actual queries still rely on the JDBC driver for DB protocol, TLS, timeouts, and data types.
- `JdbcClient` does not create a second pool alongside the `DataSource`'s pool.
- Pool exhaustion or DB restarts can cause `JdbcClient` queries to fail in the exact same way as `JdbcTemplate` queries.

An often-overlooked performance issue: fetching many rows with `.list()` loads the entire result set into RAM. Even if the fluent call looks clean, never write an unfiltered `SELECT *` on a multi-million-row table expecting the fluent layer to auto-paginate or stream. Filter in SQL, bound results, paginate properly, and monitor requests waiting for connections.

Choosing `JdbcClient` over `JdbcTemplate` **does not automatically reduce query count, cut DB round-trips, add indexes, or prevent N+1 queries**. All of those still depend on SQL design, call patterns, and architecture.

## 14. Exceptions: Spring DataAccessException Remains the Familiar Boundary

In raw JDBC, operations throw checked `SQLException`. `JdbcTemplate` executes them and translates many JDBC errors into the unchecked `org.springframework.dao.DataAccessException` hierarchy. `JdbcClient` **delegates through the templates**, so data errors neither "disappear" nor switch to JPA exceptions.

Situations to distinguish:

| Situation | Meaning | Approach |
| --- | --- | --- |
| Filtered query finds no rows with `.list()` | Normal empty result | Receive empty list |
| Key lookup finds no row with `.optional()` | Normal 0-or-1 result | Receive `Optional.empty()` |
| Query expecting one row returns 0 or many | Result-size contract violation | Review `.single()`/`.optional()` and unique constraints |
| SQL uses wrong table/column name | Invalid SQL/schema | Fix SQL/migration; do not retry endlessly |
| Duplicate unique key on `INSERT` | Constraint violation | Handle business and data rules |
| Dropped connection or exhausted pool | Infrastructure failure | Inspect driver/pool, transaction state, and timeouts |
| Deadlock/serialization failure | Transaction conflict | Review transaction boundaries, conditional retry |

Do not write:

```java
try {
    return client.sql(sql).query(Customer.class).list();
} catch (Exception ex) {
    return List.of(); // Wrong: masks DB failure as "no data".
}
```

This is an **illustrative anti-pattern** with `client`, `sql`, and `Customer` in an incomplete method context. A JDBC error is different from a valid empty result; swallowing exceptions can mislead callers into thinking the query succeeded.

If you already configured a custom `SQLExceptionTranslator` on `JdbcTemplate`, using `JdbcClient.create(existingJdbcTemplate)` routes queries on that delegate through the existing error-translation setup. That differs from creating a brand-new template with defaults and expecting identical behavior.

## 15. Why Is JdbcClient Still Synchronous Rather Than R2DBC?

The name `JdbcClient` might remind learners of `WebClient` or an async HTTP client. However, `JdbcClient` is a **traditional JDBC** API using blocking/synchronous calls over a JDBC driver.

```text
Request-handling thread
    -> client.sql(...).query(...).list()
    -> JdbcTemplate / JDBC Driver
    -> waits for DB/driver to execute query
    -> receives data, maps rows, returns to caller
```

Changing the API call from `JdbcTemplate.query(...)` to `JdbcClient.sql(...).query(...)` does not turn the database into a reactive source or return `Mono`/`Flux`. Spring R2DBC uses a different abstraction/driver and access model for reactive pipelines. If you need end-to-end non-blocking I/O, choose the appropriate reactive stack instead of assuming `JdbcClient` provides it.

Similarly, `JdbcClient` is not an HTTP client, does not send REST requests to a DB, and does not manage a WebClient-style connection pool.

## 16. When Should You Still Use JdbcTemplate or NamedParameterJdbcTemplate Directly?

Per Spring's guidance, `JdbcClient` is a **flexible yet simplified** facade for common query/update operations. Do not force every case into the fluent API.

| Task | Preferred choice | Reason |
| --- | --- | --- |
| Single-row SELECT, lists, COUNT | `JdbcClient` | Clean, readable fluent syntax |
| Simple UPDATE/INSERT/DELETE | `JdbcClient` | `.update()` returns affected row count |
| SQL with many named parameters | `JdbcClient` or `NamedParameterJdbcTemplate` | Both rely on named binding |
| Complex batch inserts/updates | `JdbcTemplate.batchUpdate(...)` or dedicated batch APIs when appropriate | Direct batch control and JDBC callbacks |
| Stored procedures / CallableStatement | `SimpleJdbcCall` or `JdbcTemplate` | Dedicated support for metadata and out parameters |
| Generated keys across varied DB types | `SimpleJdbcInsert` or corresponding JDBC APIs | Needs specific driver/DB and schema support |
| Deep custom JDBC statements/callbacks | `JdbcTemplate` directly | Exposes many low-level overloads and callbacks |
| ORM entity graphs, dirty checking | JPA/Hibernate if needed | Not a built-in capability of `JdbcClient` |
| Reactive/non-blocking SQL | Spring R2DBC with a supported driver | Separate from synchronous JDBC infrastructure |

A project can comfortably use `JdbcClient` for 90% of standard queries while using `JdbcTemplate` in a specialized repository. **There is no need to rewrite all working legacy code just to change API style**; weigh benefits against migration and testing costs.

Newer Spring versions add deeper per-statement fluent options. If a project runs Spring Framework 6.1, do not adopt syntax from "current" Spring 7 Javadoc without checking the method's `@since` tag.

## 17. Performance: Shorter API Does Not Mean Faster Queries

Compare the two styles semantically:

```java
// JdbcTemplate style:
List<Long> ids1 = jdbcTemplate.query(
    "SELECT id FROM customer WHERE tenant_id = ? ORDER BY id",
    (rs, rowNum) -> rs.getLong("id"),
    10L
);

// JdbcClient style:
List<Long> ids2 = jdbcClient
    .sql("SELECT id FROM customer WHERE tenant_id = ? ORDER BY id")
    .param(10L)
    .query(Long.class)
    .list();
```

With the same `DataSource`, SQL, and parameters, both aim to execute an equivalent query on the DB. There is no reason to assume `JdbcClient` bypasses the network, query planner, or I/O just because the Java code looks shorter.

To improve real performance, measure:

1. **Number of SQL round-trips:** is a query firing per element? N+1 is a design issue, not an API choice.
2. **Execution plan:** indexes, selective predicates, JOINs, GROUP BY, sorting, and rows scanned.
3. **Rows returned:** never fetch 1 million rows just to use 10.
4. **Connection hold time:** heavy mapping, blocking on other I/O while streaming, or long transactions.
5. **Pool/driver timeouts:** connection acquisition, query timeout, and socket timeout are distinct mechanisms.
6. **SQL plan reuse:** bind parameters properly; avoid concatenating user values into continually changing SQL strings.

For large datasets, fetch size and streaming can be considered **when supported by the driver**, though verify your Spring version. Not every statement configuration option on `JdbcTemplate` is exposed identically on `JdbcClient` 6.1.

## 18. Rules for Authorization, Tenants, and Data Correctness

Whether a query is written with `JdbcClient` or `JdbcTemplate`, SQL must still enforce business data-protection predicates.

For example, in a multi-tenant application, never omit `tenant_id` just because you have an ID:

```java
// Wrong if requests may only read the current tenant:
jdbcClient.sql("SELECT id, name FROM customer WHERE id = :id")
    .param("id", id)
    .query(Customer.class)
    .optional();
```

Correct with an explicit tenant boundary:

```java
jdbcClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId AND id = :id"
    )
    .param("tenantId", tenantId)
    .param("id", id)
    .query(Customer.class)
    .optional();
```

`JdbcClient` does not infer data-access permissions from fields of a Java record. It simply executes the SQL with the parameters you provide. Authorization checks must be designed across controller/service/repository/DB layers per architecture.

Likewise, `UPDATE customer SET ... WHERE id=:id` does not automatically apply optimistic locking. When optimistic locking is needed, include a version column and `WHERE id=:id AND version=:version`, then inspect `affected` to detect concurrent edits. When pessimistic locking is needed, use valid SQL and transactions for your dialect. Changing APIs does not change concurrency semantics.

## 19. Unit Tests and Integration Tests: What Should Be Verified?

When migrating a repository method from `JdbcTemplate` to `JdbcClient`, the goal is not merely verifying that the fluent chain compiles. Verify that observable behavior remains intact:

| Test | What to verify |
| --- | --- |
| 0 rows | `list()` returns empty, `optional()` is empty, `single()` enforces contract |
| 1 row | Mapper/record populates exact columns and types |
| >1 row | `single()`/`optional()` do not silently drop extra rows |
| Positional parameters | `?` positions and `param(...)` order match |
| Named parameters | `:x` names match `param("x", ...)` |
| SQL NULL | Primitive getters and `rs.wasNull()` behave as intended |
| Update 0/1/n rows | Inspect `affected`; do not equate "no error" with "updated" |
| 2-statement transaction | Transaction rolls back or commits per actual configuration |
| Another tenant | No cross-tenant data leakage |
| JDBC exceptions | Handled by Spring; never turned into fake empty lists |
| Query count, latency | No extra SQL calls, round-trips, or pool saturation |
| Large results/streams | Stream resources close properly and memory stays bounded |

**Unit tests** are great for mappers, parameter validation, and result-handling rules. **Integration tests** against a compatible DB are what prove SQL execution, mapping accuracy, the transaction manager, and connection error handling work as intended.

Never rely on a mocked `JdbcClient.sql()` unit test to claim a transaction actually rolls back: run against Spring's transaction infrastructure and a test DB. If the project has a custom exception translator, test that the client is created from the right template so it inherits that configuration.

## 20. Standalone Java 17: Simulating the Delegating Facade Without Spring

The example below uses only JDK 17. It creates:

- `MiniFluentClient`: a fluent class simulating `JdbcClient`.
- `SqlExecutor`: a common execution contract representing `JdbcTemplate`.
- `FakeJdbcExecutor`: simulates the JDBC and data layer, **without connecting to a real DB**.

It does not try to implement a SQL parser or JDBC driver; the goal is to distinguish the **expressive API** from the **execution delegate**. In a real Spring application, `JdbcClient` and `JdbcTemplate` take the place of those two simulated components, while SQL goes to the JDBC driver/DB.

Create `JdbcFacadeMentalModelDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;

public final class JdbcFacadeMentalModelDemo {
    record Customer(long id, String name) {}

    interface SqlExecutor {
        Customer queryOne(String sql, List<Object> bind);
    }

    static final class FakeJdbcExecutor implements SqlExecutor {
        @Override
        public Customer queryOne(String sql, List<Object> bind) {
            System.out.println("delegate: JDBC executor");
            System.out.println("sql: " + sql);
            System.out.println("bind: " + bind);
            long id = ((Number) bind.get(0)).longValue();
            if (id == 1L) {
                return new Customer(1L, "Lan");
            }
            if (id == 2L) {
                return new Customer(2L, "Minh");
            }
            throw new NoSuchElementException("No customer: " + id);
        }
    }

    static final class MiniFluentClient {
        private final SqlExecutor delegate;

        MiniFluentClient(SqlExecutor delegate) {
            this.delegate = delegate;
        }

        Statement sql(String text) {
            return new Statement(delegate, text);
        }
    }

    static final class Statement {
        private final SqlExecutor delegate;
        private final String sql;
        private final List<Object> params = new ArrayList<>();

        Statement(SqlExecutor delegate, String sql) {
            this.delegate = delegate;
            this.sql = sql;
        }

        Statement param(Object value) {
            params.add(value);
            return this;
        }

        Customer single() {
            return delegate.queryOne(sql, List.copyOf(params));
        }
    }

    public static void main(String[] args) {
        MiniFluentClient client = new MiniFluentClient(
            new FakeJdbcExecutor()
        );

        Customer value = client
            .sql("SELECT id, name FROM customer WHERE id = ?")
            .param(2L)
            .single();

        System.out.println("result: " + value);
    }
}
```

Compile and run:

```bash
javac --release 17 JdbcFacadeMentalModelDemo.java
java JdbcFacadeMentalModelDemo
```

Exact output:

```text
delegate: JDBC executor
sql: SELECT id, name FROM customer WHERE id = ?
bind: [2]
result: Customer[id=2, name=Minh]
```

Here, `client.sql(...).param(...).single()` merely configures the request. The `single()` method **delegates** to `SqlExecutor.queryOne(...)`; the executor simulates the underlying work. What stdout proves: the fluent syntax does not fetch data by itself—it needs a delegate to perform execution.

**Do not treat `MiniFluentClient` as Spring's real API.** It does not manage resources, translate `SQLException`, handle transactions, map columns, or perform JDBC I/O; it only illustrates the delegation architecture to prevent confusing "new API = new DB protocol".

## 21. Typical Misconceptions

**Misconception 1 — "JdbcClient completely replaces JdbcTemplate".**  
No. `JdbcClient` **delegates** to `JdbcTemplate` and `NamedParameterJdbcTemplate`. For advanced operations, direct templates remain valuable.

**Misconception 2 — "Switching to JdbcClient eliminates SQL injection".**  
Not automatically. You still must bind values via `param(...)`, avoid concatenating user input into SQL, and never use parameters in place of identifiers.

**Misconception 3 — "JdbcClient understands entity relationships like JPA".**  
No. Data comes from SQL and mappers/records. There is no built-in persistence context or dirty checking.

**Misconception 4 — "A fluent chain creates a transaction on its own".**  
No. Transactions are coordinated by Spring's transaction manager; multiple `update()` calls need `@Transactional` if they must form an atomic unit.

**Misconception 5 — "JdbcClient is non-blocking".**  
No. It still runs on synchronous JDBC drivers; R2DBC is a separate infrastructure.

**Misconception 6 — "Calling query(...).single() picks the first row".**  
No. It is a single-result contract; 0 or >1 rows are error conditions enforced by Spring, not a SQL command to pick one row.

**Misconception 7 — "You don't need to close streams because Spring manages them".**  
No. `stream()` must be closed once consumed to release the underlying resources.

**Misconception 8 — "JdbcClient reduces DB round-trips".**  
Not automatically. The same SQL and parameters still go to the DB; optimizing queries and connections is separate work.

**Misconception 9 — "query(Customer.class) always maps every schema cleanly".**  
No. Columns, aliases, field/record component names, and data types must align; complex logic calls for an explicit mapper.

**Misconception 10 — "With JdbcClient you no longer need a DataSource/pool".**  
No. `DataSource` still supplies connections; the pool/driver handles physical connections and timeouts.

**Misconception 11 — "JdbcClient exists in all Spring 6.x releases".**  
No. It started in **6.1**, not 6.0. Newer per-statement options may only exist in Spring 7; always verify your version.

**Misconception 12 — "JdbcClient.create(dataSource) always reuses all customizations from an old JdbcTemplate".**  
Not necessarily. To reuse an already configured delegate, use the factory method accepting that template itself.

## 22. Self-Check Exercises

**1. Does `JdbcClient` sit above or below `JdbcTemplate`?**  
It sits at the API layer above and **delegates** execution. `JdbcTemplate` still performs the JDBC handling.

**2. Does the JDBC driver natively understand `:tenantId`?**  
Not as a general rule. Spring supports named parameters and converts them into positional JDBC bindings.

**3. Do two consecutive `update()` calls on the same client automatically share a transaction?**  
No. You need a transaction manager and a matching `@Transactional` boundary to guarantee DB-level atomicity.

**4. What does `query(Customer.class).list()` return if SQL matches 0 rows?**  
An empty list. If you need to distinguish 0 vs. 1, use `optional()` with SQL that fits the contract.

**5. With one million rows, does simply switching to `JdbcClient` cut memory and query time?**  
Not automatically. You still must filter/paginate/optimize SQL, use streaming properly, and measure connections/memory.

**6. When batch inserts and stored procedures are needed, should all `JdbcTemplate` usage be removed?**  
No. Spring still provides templates and specialized helpers for advanced operations.

**7. Can `param("name", value)` substitute a table name in `FROM :name`?**  
No. Binding is only for SQL values, not identifier structure; table names must be controlled via trusted code.

**8. When is `JdbcClient.create(existingJdbcTemplate)` useful?**  
When the application wants to reuse an existing delegate with its DataSource and custom settings instead of creating another independent template.

**9. Why must you still understand `RowMapper` and JDBC NULL?**  
Because `JdbcClient` still reads from a JDBC `ResultSet`; primitive getters can lose null distinction, and mapping can mismatch types or names.

**10. Can `JdbcClient` be considered JPA, R2DBC, or a NoSQL driver?**  
No. It is a facade over traditional **Spring JDBC**.

## 23. Key Takeaways

- **`JdbcClient` is a unified fluent facade for common JDBC operations, introduced in Spring Framework 6.1.**
- **Execution still relies on `JdbcTemplate`/`NamedParameterJdbcTemplate`**, passing through `DataSource`, `Connection`, the JDBC driver, and the DB.
- `sql(...).param(...).query(...).list()` makes code easier to read **without altering SQL/JDBC fundamentals**.
- Parameter binding remains mandatory, `RowMapper` and data types must still be accurate; `single()`, `optional()`, and `list()` enforce different result contracts.
- Transactions remain coordinated by Spring's transaction manager, JDBC errors still flow through `DataAccessException`, and connection pooling still belongs to `DataSource`.
- `JdbcClient` **is not an ORM, does not provide reactive I/O, does not fix slow SQL or N+1 queries**, and does not enforce authorization automatically.
- **Use `JdbcClient` for standard queries/updates; use templates/helpers directly for advanced JDBC work**. There is no need to rewrite stable existing code just to swap APIs.
- Create the client from **an already configured template** when you want to reuse the application's exact delegate and handling policies.

### Official References

- [Spring Framework Reference — Unified JDBC Query/Update Operations: JdbcClient](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework Javadoc — JdbcClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html)
- [Spring Framework Javadoc — JdbcClient.StatementSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html)
- [Spring Framework Javadoc — JdbcClient.MappedQuerySpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html)
- [Spring Framework Reference — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework Reference — Choosing an Approach for JDBC Database Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html)
