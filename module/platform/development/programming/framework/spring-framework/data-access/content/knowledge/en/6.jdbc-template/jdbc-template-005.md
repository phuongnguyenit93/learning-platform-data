# Callbacks Providing SQL, Parameters, or Result Reading in JdbcTemplate

## 1. Why Does JdbcTemplate Have Callbacks?

When using plain JDBC, each query typically repeats the same sequence of steps:

1. Obtain a `Connection` from a `DataSource`.
2. Create a `PreparedStatement` with the SQL string.
3. Bind values to `?` placeholders if any.
4. Execute the SQL statement.
5. Read rows from `ResultSet` or inspect the affected row count.
6. Close `ResultSet` and `Statement`, release `Connection`, and handle `SQLException`.

Most of those steps are identical across queries. The differences lie mainly in **which SQL runs**, **which parameters are bound**, and **how the results are read**. Spring's `JdbcTemplate` separates the repetitive plumbing from the varying parts using **callbacks**: application code passes an object or lambda describing what to do at a specific point, while the template orchestrates the JDBC flow.

```text
Application code
    |
    +-- SQL or PreparedStatementCreator    -> create PreparedStatement
    +-- PreparedStatementSetter              -> set parameters and customize statement
    +-- RowMapper / ResultSetExtractor /
    |   RowCallbackHandler                   -> process SELECT results
    +-- PreparedStatementCallback            -> perform specialized operations directly
    |
    v
JdbcTemplate
    -> obtain transaction-appropriate Connection
    -> prepare Statement
    -> invoke callback at the right time
    -> execute / iterate results
    -> release resources
    -> translate SQLException into DataAccessException
```

**A callback does not mean "close connections yourself" or "run SQL whenever you want."** Each interface has its own contract regarding what object it receives, what operations are permitted, and who controls the `ResultSet` cursor.

After this lesson, you will be able to:

- Choose the right callback to provide SQL/statements, bind parameters, or map data.
- Distinguish `PreparedStatementCreator` from `PreparedStatementSetter`, as well as `RowMapper` from `ResultSetExtractor` and `RowCallbackHandler`.
- Know which callbacks are invoked **once per query** and which are invoked **once per result row**.
- Write Spring JDBC queries with properly typed lambdas; handle `NULL`, positional parameters, exceptions, and resources.
- Recognize when to use simpler APIs or `NamedParameterJdbcTemplate` instead of implementing overly low-level callbacks.

## 2. Map of Key Callbacks

| Callback | Functional method | Receives | Primary responsibility | When is it called? |
| --- | --- | --- | --- | --- |
| `PreparedStatementCreator` | `createPreparedStatement(Connection)` | `Connection` provided by template | Creates `PreparedStatement`, selects SQL and creation options; may bind parameters | When the template prepares the statement |
| `PreparedStatementSetter` | `setValues(PreparedStatement)` | Created `PreparedStatement` | Binds `?` parameters and sets minor statement options | Before the statement executes |
| `RowMapper<T>` | `mapRow(ResultSet, int)` | Cursor at current row and row index | Turns **one row** into an object `T` | For each mapped row |
| `ResultSetExtractor<T>` | `extractData(ResultSet)` | Entire `ResultSet` | Controls iteration and builds **one overall result** `T` | Typically once per result set |
| `RowCallbackHandler` | `processRow(ResultSet)` | Cursor at current row | Performs an action per row without building a `List<T>` | For each processed row |
| `PreparedStatementCallback<T>` | `doInPreparedStatement(PreparedStatement)` | Active `PreparedStatement` | Directly runs specialized JDBC operations and returns `T` | When using matching `execute(...)` variants |

The first four interfaces and `RowCallbackHandler` commonly work together in `query(...)` calls. `PreparedStatementCallback` is used when you want direct control over operations on a single statement, such as executing a batch of commands on the same `PreparedStatement`.

Several related callbacks have specialized scopes: `ConnectionCallback<T>` works at the `Connection` level; `StatementCallback<T>` works with a plain `Statement`; `CallableStatementCreator` and `CallableStatementCallback<T>` serve stored procedures or `CallableStatement` calls. Do not use those low-level interfaces for a routine query that just has a few parameters.

## 3. A Callback Is a Contract; a Lambda Is Just Concise Syntax

Callback interfaces are usually **functional interfaces**: they have a single abstract method to implement, so they can be expressed as lambdas. For example:

```java
PreparedStatementSetter setter = ps -> ps.setString(1, "ACTIVE");
```

This is illustrative code requiring `import org.springframework.jdbc.core.PreparedStatementSetter`. The lambda is equivalent to a class implementing `setValues(PreparedStatement ps)`. It **does not execute at declaration time**: `JdbcTemplate` invokes the lambda once the statement has been created and it reaches the parameter-binding step.

Similarly:

```java
RowMapper<String> ownerMapper = (rs, rowNum) -> rs.getString("owner");
```

The template calls `mapRow` with `ResultSet` positioned at the current row. The lambda returns one name per row; `JdbcTemplate.query(..., ownerMapper)` collects them into a list. `rowNum` is a 0-based row index tracked by Spring's mapping loop, **not a primary key** and not a guaranteed stable order if SQL lacks `ORDER BY`.

Declaring a variable with an explicit callback type also avoids ambiguity across `query(...)` overloads. A single-parameter lambda can look identical whether it is a `ResultSetExtractor`, `RowCallbackHandler`, or `PreparedStatementSetter`, so always inspect the **parameter types and return type** of the method overload you are calling.

## 4. Sample Data to Align Semantics

Suppose an application has an `account` table in PostgreSQL or a test H2 database:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    owner VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO account (id, owner, status, balance) VALUES
    (1, 'Lan',  'ACTIVE',   120.00),
    (2, 'Minh', 'INACTIVE',  70.00),
    (3, 'Vy',   'ACTIVE',    90.00);
```

Query:

```sql
SELECT id, owner, balance
FROM account
WHERE status = ?
ORDER BY id;
```

Binding the first parameter to `"ACTIVE"` returns two rows:

| id | owner | balance |
| ---: | --- | ---: |
| 1 | Lan | 120.00 |
| 3 | Vy | 90.00 |

We will use this data to see how the same SQL, paired with different result-reading callbacks, can produce a `List<Account>`, an aggregate number, or a per-row action.

## 5. Providing SQL: When Do You Need PreparedStatementCreator?

### 5.1. Common Case: Pass a SQL String

For simple queries, there is no need to construct the statement manually:

```java
List<String> owners = jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("owner"),
    "ACTIVE"
);
```

This example assumes `jdbcTemplate` is already initialized in a Spring application. The `query(String, RowMapper<T>, Object...)` API creates a prepared statement and binds positional arguments automatically. The returned list is `["Lan", "Vy"]` with the sample data. The `RowMapper` lambda specifies how to read each row.

**When you already have a SQL `String`, prefer the overload taking `String` and parameters**: it is much more concise than building a `PreparedStatementCreator`.

### 5.2. PreparedStatementCreator Builds a Statement from Connection

`PreparedStatementCreator` is useful when you need control over statement creation: choosing `ResultSet` type, concurrency mode, generated keys, or `PreparedStatement` creation options not exposed directly by simpler APIs.

```java
import java.sql.PreparedStatement;
import org.springframework.jdbc.core.PreparedStatementCreator;

String sql = """
    SELECT id, owner, balance
    FROM account
    WHERE status = ?
    ORDER BY id
    """;

PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(sql);
    ps.setString(1, "ACTIVE");
    return ps;
};
```

`JdbcTemplate` supplies `connection` to the callback and **closes the statement created by the callback** when finished. The callback selects the SQL, creates the `PreparedStatement`, and may bind values itself. Do not call `connection.close()` inside the creator, as the connection is managed by the template and transaction manager.

You can pass the creator into a query:

```java
RowMapper<String> mapper = (rs, rowNum) -> rs.getString("owner");

List<String> owners = jdbcTemplate.query(creator, mapper);
```

If you only need to bind a few parameters, `PreparedStatementSetter` or the `Object... args` overload is usually clearer. Do not write a complex creator just to use a lambda.

### 5.3. Special Case: Retrieving Auto-Generated Keys

When running an `INSERT` and needing the DB-generated key, the statement-creating callback can request `RETURN_GENERATED_KEYS`:

```java
import java.sql.PreparedStatement;
import java.sql.Statement;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

int affected = jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO account(owner, status, balance) VALUES (?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, "Hoa");
    ps.setString(2, "ACTIVE");
    ps.setBigDecimal(3, new java.math.BigDecimal("50.00"));
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
```

**Conditions for this example:** the real table must have an auto-generated `id` column or equivalent key-generation mechanism; the `account` table in Section 4 declares `id BIGINT PRIMARY KEY` **without auto-generation**, so the DDL must be adjusted for the target DB before running this example. The JDBC driver must also support generated key retrieval. `getKey()` only applies when there is a single numeric key; it may not yield a value if the DB/driver does not return keys as expected. `affected` is the affected row count, not the generated ID.

This example illustrates **why you might control `PreparedStatement` creation**, not that every `INSERT` should hand-write a `PreparedStatementCreator`.

## 6. Providing Parameters: PreparedStatementSetter

`PreparedStatementSetter` receives an already-created `PreparedStatement` and binds values to `?` placeholders before execution. JDBC parameter indices are **1-based**, unlike Java array indices which are 0-based.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.PreparedStatementSetter;

String sql = """
    SELECT id, owner, balance
    FROM account
    WHERE status = ? AND balance >= ?
    ORDER BY id
    """;

PreparedStatementSetter setter = ps -> {
    ps.setString(1, "ACTIVE");
    ps.setBigDecimal(2, new BigDecimal("100.00"));
};
```

Here, the callback supplies **two values** matching the exact order of `?` placeholders: status first, minimum balance second. Swapping their positions can cause a DB type error or wrong query results.

Pairing the setter with a mapper:

```java
RowMapper<String> mapper = (rs, rowNum) -> rs.getString("owner");
List<String> owners = jdbcTemplate.query(sql, setter, mapper);
```

With the sample data, the list is `["Lan"]` because Vy has a balance of 90.00.

### 6.1. Why Still Use PreparedStatement with Callbacks?

`PreparedStatement` separates SQL structure from input values. Instead of string concatenation:

```java
// DO NOT DO THIS: user input is concatenated directly into SQL.
String unsafe = "SELECT * FROM account WHERE owner = '" + userInput + "'";
```

use:

```java
String sql = "SELECT id, owner, balance FROM account WHERE owner = ?";
List<Account> found = jdbcTemplate.query(sql, ACCOUNT_MAPPER, userInput);
```

Here `ACCOUNT_MAPPER` is a `RowMapper<Account>` defined in the repository class in Section 10. The `?` placeholder is for **values**, not for table names, column names, or `ORDER BY` keywords. If business logic allows choosing a sort column, map the choice against an **allowlist of permitted column names** rather than interpolating arbitrary strings.

### 6.2. NULL and SQL Types

For `null` values, some drivers require knowing the explicit SQL type:

```java
import java.sql.Types;

PreparedStatementSetter setter = ps -> {
    if (optionalOwner == null) {
        ps.setNull(1, Types.VARCHAR);
    } else {
        ps.setString(1, optionalOwner);
    }
};
```

This is an illustrative fragment assuming an `optionalOwner` variable exists. `setNull(1, Types.VARCHAR)` explicitly states the parameter's SQL type. Note SQL semantics: `WHERE owner = NULL` does not match rows where `owner IS NULL`; if filtering for `NULL` data is needed, explicitly design an `IS NULL` condition or DB-appropriate syntax.

For monetary amounts, use `BigDecimal` instead of `double` to avoid binary floating-point rounding errors in decimal arithmetic.

### 6.3. When a Separate Setter Callback Is Unnecessary

`JdbcTemplate` has overloads accepting arguments directly:

```java
List<String> names = jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("owner"),
    "ACTIVE"
);
```

In terms of responsibility, the template still binds parameters. However, application code does not need to define a `PreparedStatementSetter` manually when simple binding is already handled by the API. If parameter order/types become hard to read due to too many `?`s, `NamedParameterJdbcTemplate` in Section 12 may fit better.

## 7. Reading Results Part 1: RowMapper<T> for One Object per Row

`RowMapper<T>` has one method:

```java
T mapRow(ResultSet rs, int rowNum) throws SQLException;
```

Meaning: receive the **current row** and return **one value `T`**. Spring handles looping over results, invoking the mapper once per row, and collecting the values into `List<T>`.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.RowMapper;

public record Account(long id, String owner, BigDecimal balance) {}

RowMapper<Account> mapper = (rs, rowNum) ->
    new Account(
        rs.getLong("id"),
        rs.getString("owner"),
        rs.getBigDecimal("balance")
    );
```

The snippets above are standalone Java/Spring code fragments; an actual compilable file needs the record and variable placed in an appropriate class/method scope (see the complete class in Section 10). Inside `mapRow`, **never call `rs.next()`**: Spring has already positioned the cursor at the right row before running the callback. Calling `next()` skips rows or misaligns column reads.

`JdbcTemplate.query(sql, mapper)` returns an empty list when SQL produces no rows; `queryForObject(sql, mapper, ...)` requires exactly one row and throws `EmptyResultDataAccessException` or `IncorrectResultSizeDataAccessException` when the size does not match expectations.

An `Account` record makes result models easy to read. For 1-to-N `JOIN` SQL, each result row can repeat parent data, so a simple `RowMapper<Account>` can emit multiple objects with the same parent key. To aggregate one parent with multiple children, use separate queries or a `ResultSetExtractor` that groups by key.

## 8. Reading Results Part 2: ResultSetExtractor<T> for the Whole Result Set

`ResultSetExtractor<T>` has one method:

```java
T extractData(ResultSet rs) throws SQLException, DataAccessException;
```

Unlike `RowMapper`, this callback receives the **entire `ResultSet`**, controls the `while (rs.next())` loop itself, and can return any structure: a single object, a list, a `Map`, a tree, statistics, or `null` if business logic requires.

Example counting active user rows:

```java
import org.springframework.jdbc.core.ResultSetExtractor;

ResultSetExtractor<Integer> extractor = rs -> {
    int count = 0;
    while (rs.next()) {
        count++;
    }
    return count;
};

int count = jdbcTemplate.query(
    "SELECT id FROM account WHERE status = ?",
    ps -> ps.setString(1, "ACTIVE"),
    extractor
);
```

The sample output is `2`. However, if the real goal is just counting rows in the DB, **`SELECT COUNT(*)` is more efficient** because it avoids transferring every row to Java. The example above only illustrates that the extractor controls the iteration loop.

Extractors work well for multi-level structures. For instance, one customer with many orders:

```java
ResultSetExtractor<Map<Long, List<Long>>> extractor = rs -> {
    Map<Long, List<Long>> orderIdsByCustomer = new LinkedHashMap<>();
    while (rs.next()) {
        long customerId = rs.getLong("customer_id");
        List<Long> ids = orderIdsByCustomer.computeIfAbsent(
            customerId, ignored -> new ArrayList<>()
        );
        Long orderId = rs.getObject("order_id", Long.class);
        if (orderId != null) {
            ids.add(orderId);
        }
    }
    return orderIdsByCustomer;
};
```

This snippet requires imports for `java.util.Map`, `List`, `LinkedHashMap`, `ArrayList`, and a SQL query providing `customer_id` and `order_id` columns (such as a `LEFT JOIN` between customers and orders). When there are no children, `getObject(..., Long.class)` returns `null`; unlike `getLong()`, which returns 0 for SQL NULL and requires checking `wasNull()`. If SQL joins additional child tables, one order may appear multiple times; you must explicitly deduplicate by **child key** or adjust the query design.

**Never close the `ResultSet` supplied by `JdbcTemplate.query(...)` inside `ResultSetExtractor`**. The template owns its lifecycle. If you open auxiliary resources *inside the callback*, the callback itself must manage those auxiliary resources.

An extractor can usually be written statelessly and reused. If a callback holds external mutable variables, consider concurrent usage across multiple requests.

## 9. Reading Results Part 3: RowCallbackHandler for One Action per Row

`RowCallbackHandler` differs from `RowMapper` in its return type:

```java
void processRow(ResultSet rs) throws SQLException;
```

The template calls `processRow` for each row, but the callback **does not return an individual object for Spring to collect into `List<T>`**. It is suited for updating counters, pushing records to a processor, computing local aggregations, or writing into a caller-managed structure.

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.RowCallbackHandler;

List<String> owners = new ArrayList<>();
RowCallbackHandler collectOwner = rs ->
    owners.add(rs.getString("owner"));

jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    ps -> ps.setString(1, "ACTIVE"),
    collectOwner
);
// owners contains ["Lan", "Vy"] with the sample data.
```

Inside `RowCallbackHandler`, **never call `rs.next()`**; Spring already handles advancing rows. If the goal is simply building a `List<Account>`, `RowMapper` is usually shorter and easier to read.

`RowCallbackHandler` does not automatically "stream" data in constant memory: the JDBC driver may buffer many or all rows depending on configuration, and the callback might still store every row in an external list. When processing large sets, check fetch size, transactions, driver cursor behavior, data limits, and connection hold time.

Avoid keeping a `RowCallbackHandler` with mutable state shared across multiple requests, because concurrent calls can overwrite or mix data. Create fresh state per query invocation, or use an appropriate synchronization component when sharing is genuinely required.

## 10. A Complete Spring JDBC Class Combining Callbacks

The example below is source code for a **Spring Boot application that already has a `DataSource`, `JdbcTemplate`, and the `account` table from Section 4**. It compiles in a Java 17+ project with Spring JDBC/Spring context on the classpath; **it cannot run standalone with just the JDK**.

Create `AccountReadRepository.java`:

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class AccountReadRepository {
    private static final String BY_STATUS = """
        SELECT id, owner, balance
        FROM account
        WHERE status = ?
        ORDER BY id
        """;

    private static final RowMapper<Account> ACCOUNT_ROW_MAPPER =
        (rs, rowNum) -> new Account(
            rs.getLong("id"),
            rs.getString("owner"),
            rs.getBigDecimal("balance")
        );

    private final JdbcTemplate jdbc;

    public AccountReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // SQL + parameters provided by PreparedStatementSetter,
    // each row mapped into an Account by RowMapper.
    public List<Account> findByStatus(String status) {
        PreparedStatementSetter setter = ps ->
            ps.setString(1, status);
        return jdbc.query(BY_STATUS, setter, ACCOUNT_ROW_MAPPER);
    }

    // PreparedStatementCreator creates the statement and binds parameters itself.
    public List<Account> findWithCreator(String status) {
        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(BY_STATUS);
            ps.setString(1, status);
            return ps;
        };
        return jdbc.query(creator, ACCOUNT_ROW_MAPPER);
    }

    // ResultSetExtractor reads the whole ResultSet and returns a sum.
    public BigDecimal totalByStatus(String status) {
        String sql = """
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM account
            WHERE status = ?
            """;
        ResultSetExtractor<BigDecimal> extractor = rs ->
            rs.next() ? rs.getBigDecimal("total_balance")
                      : BigDecimal.ZERO;

        return jdbc.query(
            sql,
            (PreparedStatementSetter) ps -> ps.setString(1, status),
            extractor
        );
    }

    // RowCallbackHandler processes each row without automatically building a List.
    public void forEachByStatus(
        String status, Consumer<Account> receiver
    ) {
        RowCallbackHandler handler = rs -> receiver.accept(
            new Account(
                rs.getLong("id"),
                rs.getString("owner"),
                rs.getBigDecimal("balance")
            )
        );
        jdbc.query(
            BY_STATUS,
            (PreparedStatementSetter) ps -> ps.setString(1, status),
            handler
        );
    }

    public record Account(long id, String owner, BigDecimal balance) {}
}
```

With the sample data in Section 4:

- `findByStatus("ACTIVE")` returns a list of two `Account`s with IDs 1 and 3 in `ORDER BY id` order.
- `findWithCreator("ACTIVE")` returns the same list, with the creator building the statement directly.
- `totalByStatus("ACTIVE")` returns **210.00** summed in the DB (`BigDecimal`, whose scale representation may vary across DBs).
- `forEachByStatus("ACTIVE", consumer)` invokes the consumer twice. If the consumer throws a runtime exception, it propagates and stops querying; Spring still cleans up resources per contract.

These are **four callback implementation forms**, not four mandatory steps for a single query. In practice, pick the shortest API that satisfies your needs; do not use `PreparedStatementCreator`, `Setter`, and extractor together unnecessarily.

## 11. PreparedStatementCallback<T>: Running Operations on a Statement Directly

Sometimes an application needs to invoke multiple JDBC operations directly on a single `PreparedStatement`. Then `PreparedStatementCallback<T>` combined with `JdbcTemplate.execute(...)` is useful.

```java
import java.util.List;
import org.springframework.jdbc.core.PreparedStatementCallback;

int[] counts = jdbcTemplate.execute(
    "UPDATE account SET status = ? WHERE id = ?",
    (PreparedStatementCallback<int[]>) ps -> {
        for (long id : List.of(1L, 3L)) {
            ps.setString(1, "INACTIVE");
            ps.setLong(2, id);
            ps.addBatch();
        }
        return ps.executeBatch();
    }
);
```

This is an integrated example, not standalone. The template creates the statement, calls the callback, handles `SQLException`, and closes the statement. The callback **binds parameters and invokes `executeBatch()` itself** in this example. The `int[]` result holds affected row counts per JDBC; an element may be `Statement.SUCCESS_NO_INFO` rather than an exact count, depending on the driver.

**Batching does not mean an atomic transaction.** If all updates must succeed together or none at all, wrap the operation in an appropriate Spring transaction and verify DB/driver behavior. The callback must not close the statement owned by the template. If the callback opens extra `ResultSet`s or auxiliary streams during processing, it must close those auxiliary resources per contract before returning.

In day-to-day work, `jdbcTemplate.update(...)` or `batchUpdate(...)` provides a higher-level, less error-prone API than using `PreparedStatementCallback` manually.

## 12. Callbacks at Another Layer: NamedParameterJdbcTemplate and JdbcClient

### 12.1. When There Are Too Many `?` Placeholders

With `JdbcTemplate`, parameters are **positional**, for example:

```sql
WHERE status = ? AND balance >= ? AND owner = ?
```

With many parameters or carefully built conditions, `NamedParameterJdbcTemplate` provides named placeholders:

```java
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(jdbcTemplate);

List<AccountReadRepository.Account> result = named.query(
    """
    SELECT id, owner, balance
    FROM account
    WHERE status = :status AND balance >= :minBalance
    ORDER BY id
    """,
    Map.of(
        "status", "ACTIVE",
        "minBalance", new BigDecimal("100.00")
    ),
    (rs, rowNum) -> new AccountReadRepository.Account(
        rs.getLong("id"),
        rs.getString("owner"),
        rs.getBigDecimal("balance")
    )
);
```

On the sample data, the query returns only Lan's account. `NamedParameterJdbcTemplate` processes named parameters and delegates to JDBC underneath; it still has overloads accepting `RowMapper`, `ResultSetExtractor`, and `RowCallbackHandler`. When parameter maps contain nulls or require explicit SQL types, consider `MapSqlParameterSource` instead of `Map.of` (which forbids null values).

### 12.2. JdbcClient in Spring Framework 6.1+

Spring Framework 6.1 introduces `JdbcClient`: a fluent facade for writing SQL, binding parameters, and specifying mappers more readably. It works with `JdbcTemplate`/`NamedParameterJdbcTemplate` underneath rather than changing `RowMapper` contracts or JDBC connection management. On Spring versions older than 6.1, do not assume this API is available.

```java
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(jdbcTemplate);
List<String> owners = client.sql(
        "SELECT owner FROM account WHERE status = :status ORDER BY id"
    )
    .param("status", "ACTIVE")
    .query((rs, rowNum) -> rs.getString("owner"))
    .list();
```

Here the example illustrates the API for a Spring Framework 6.1+ project that already has `jdbcTemplate` and the test table. The goal of this lesson remains **understanding callbacks and responsibility boundaries**, because the newer syntax still requires specifying how rows become objects.

## 13. Rules for Controlling ResultSet and Resources

This is the most common source of bugs when starting with callbacks:

| Responsibility | Who owns it | What not to do |
| --- | --- | --- |
| Obtain `Connection` and bind to transaction | `JdbcTemplate`/Spring transaction infrastructure | Creators/mappers must not call `close()` on the template's connection |
| Create `PreparedStatement` | Template or `PreparedStatementCreator` called by template | Do not create statements from another connection outside the template |
| Bind parameters | Template from `Object...`, `PreparedStatementSetter`, or creator per overload | Never concatenate raw input strings into SQL |
| Iterate rows for mapper | `JdbcTemplate` | `RowMapper` must not call `rs.next()` |
| Iterate rows for handler | `JdbcTemplate` | `RowCallbackHandler` must not call `rs.next()` |
| Iterate entire set for extractor | `ResultSetExtractor` | Do not expect the template to loop inside the extractor |
| Close `ResultSet` and statement of normal queries | `JdbcTemplate` | Do not close the `ResultSet` passed into the extractor by the template |
| Clean up auxiliary resources opened inside callback | The callback that opened them | Do not leave auxiliary `ResultSet`s/streams opened by callback unclosed |
| Translate `SQLException` from JDBC operations | `JdbcTemplate` via `SQLExceptionTranslator` | Do not catch and swallow all `SQLException`s in callbacks |
| Manage commit/rollback in Spring transactions | Transaction manager matching `DataSource` | Do not manually `commit` or `rollback` on a transaction-bound connection |

When a callback throws a JDBC `SQLException`, Spring typically translates it into `DataAccessException` (unchecked) so the application layer handles errors uniformly. Runtime business exceptions intentionally thrown by a callback are not turned into JDBC errors by default. Do not wrap everything in `catch (Exception)` and return an empty list: that destroys the distinction between "no records found" and "DB failure."

When streaming results via `JdbcTemplate.queryForStream(...)`, **close the `Stream`** after reading, usually with `try-with-resources`. Having a stream does not guarantee the driver actually fetches rows one by one over the network in constant memory; behavior depends on the DB, driver, fetch size, and transaction.

## 14. Standalone Java 17 Example to Visualize Callbacks

The following example uses **only JDK 17**, with no Spring and no DB access. It simulates three extension points: a callback supplying SQL, a callback supplying parameters, and a callback reading queried rows. The interfaces `SqlCallback`, `ParameterCallback`, and `ResultCallback` are **illustrative interfaces in this article**, not Spring APIs; they clarify how a template invokes externally supplied logic at the right stages.

Create `CallbackFlowDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public final class CallbackFlowDemo {
    record Account(long id, String owner, int points) {}

    @FunctionalInterface
    interface SqlCallback {
        String sql();
    }

    @FunctionalInterface
    interface ParameterCallback {
        Object[] values();
    }

    @FunctionalInterface
    interface ResultCallback<T> {
        T read(List<Account> rows);
    }

    static <T> T execute(
            SqlCallback sqlCallback,
            ParameterCallback parameterCallback,
            ResultCallback<T> resultCallback) {
        String sql = sqlCallback.sql();
        Object[] parameters = parameterCallback.values();
        System.out.println("SQL: " + sql);
        System.out.println("params: " + Arrays.toString(parameters));

        // Simulate DB having executed WHERE points >= ? ORDER BY id.
        int minimum = (Integer) parameters[0];
        List<Account> resultRows = List.of(
            new Account(1, "Lan", 120),
            new Account(2, "Minh", 70),
            new Account(3, "Vy", 90)
        ).stream().filter(a -> a.points() >= minimum).toList();
        return resultCallback.read(resultRows);
    }

    public static void main(String[] args) {
        List<String> names = execute(
            () -> "SELECT owner FROM account WHERE points >= ? ORDER BY id",
            () -> new Object[] { 80 },
            rows -> rows.stream().map(Account::owner).toList()
        );
        System.out.println("owners: " + names);
    }
}
```

Compile and run:

```bash
javac --release 17 CallbackFlowDemo.java
java CallbackFlowDemo
```

Exact output (ordered deterministically in the simulated data):

```text
SQL: SELECT owner FROM account WHERE points >= ? ORDER BY id
params: [80]
owners: [Lan, Vy]
```

The simulation does not parse the SQL string; it intentionally filters an in-memory list. When replaced with a real `JdbcTemplate`, SQL is executed by the DB via `PreparedStatement`, and the result callback receives a `ResultSet` instead of a simulated `List<Account>`. The similarity is the **shared workflow calling injected functions at the right stages**.

## 15. Choosing Callbacks Through Concrete Scenarios

### Scenario A: Fetch a List of Accounts from Multiple Rows

Task: "Return a `List<Account>` for accounts with `status = ACTIVE`."

Choose `jdbcTemplate.query(sql, mapper, args...)` or `query(sql, setter, mapper)`. `RowMapper` does one clear job: turns one row into one `Account`. No manual `ResultSet` iteration needed.

### Scenario B: Group Customer and Order IDs by Parent Key

Task: "Return each customer once along with their list of order IDs."

If SQL returns multiple rows per customer due to a 1-to-N join, consider `ResultSetExtractor<Map<Id, ...>>` grouping by primary key and checking child columns for `NULL`. You can also split queries or use DTO projections to avoid row multiplication. A simple `RowMapper<Customer>` will not automatically merge SQL rows that repeat the parent key.

### Scenario C: Compute a Statistic Requiring Only One Value

Task: "Count active accounts."

Prefer:

```java
Integer count = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM account WHERE status = ?",
    Integer.class,
    "ACTIVE"
);
```

The result is `2` with sample data. Aggregating SQL in the DB is usually far better than pulling every row into Java for a `RowCallbackHandler` to increment a counter. In domains expecting large counts, consider `Long.class`/`COUNT` and appropriate numeric bounds.

### Scenario D: Forward Result Rows to a Processor Without Returning a List

Use `RowCallbackHandler` if you need an action per row. Do not assume the callback automatically eliminates memory overhead; fetch behavior depends on driver and application state.

### Scenario E: Need to Create a Statement with `RETURN_GENERATED_KEYS`

Use the `update(PreparedStatementCreator, KeyHolder)` overload as in Section 5.3. Ensure the schema column auto-generates keys and the driver supports it.

### Scenario F: Need to Call `executeBatch()` Yourself on the Same Statement

`PreparedStatementCallback<int[]>` can handle this. If simply updating multiple records with the same SQL, check `batchUpdate(...)` first as the higher-level API is usually sufficient.

### Scenario G: Having 8 Parameters That Are Confusing by Position

`PreparedStatementSetter` separates binding from SQL but remains positional. When field names convey meaning better than positions, switch to `NamedParameterJdbcTemplate` or `JdbcClient` if supported by your Spring version.

## 16. Common Mistakes and How to Fix Them

**Mistake 1 – Calling `rs.next()` inside `RowMapper`:** skips rows because Spring already advances the cursor. Only read columns of the current row.

**Mistake 2 – Accessing columns in `ResultSetExtractor` without calling `rs.next()`:** the cursor is normally not positioned on a valid row yet. The extractor must iterate itself, e.g., `if (rs.next())` or `while (rs.next())`.

**Mistake 3 – Calling `rs.next()` inside `RowCallbackHandler`:** also skips the cursor and loses data. Spring iterates row by row for the handler.

**Mistake 4 – Passing parameters in the wrong order:** `ps.setString(1, ...)` and `ps.setBigDecimal(2, ...)` must match `?` positions in SQL. Clear variable names and tests with distinct column values help catch mistakes.

**Mistake 5 – Trying to use `?` for table or column names:** JDBC placeholders substitute values, not SQL syntax structure. For dynamic column names, use an allowlist; for user values, always bind.

**Mistake 6 – Turning all errors into an empty list:** a query returning zero rows differs from a connection error, SQL error, permission error, or timeout. Let appropriate exceptions propagate so callers can handle them.

**Mistake 7 – Using `RowMapper` and assuming SQL rows are unique per parent object:** 1-to-N `JOIN` queries can still return multiple rows for the same parent key. Identify the row grain and group by key when needed.

**Mistake 8 – Reusing a callback holding global mutable state:** a handler writing into a shared `ArrayList` across requests can mix data or cause concurrency failures. Allocate collections within the query scope.

**Mistake 9 – Holding a connection too long in a callback:** network I/O, external API calls, or sleeping inside a callback holds the `Connection`, starving the pool and lengthening transactions. Separate heavy work from the connection-holding phase when business semantics permit.

**Mistake 10 – Manually closing Spring-owned resources:** do not close `Connection` inside `PreparedStatementCreator`, and do not close the `ResultSet` supplied to an extractor by the template. Only close auxiliary resources opened by the callback itself.

**Mistake 11 – Confusing `queryForObject` with `query`:** `query` with a mapper returns `List<T>`, which may be empty; `queryForObject` requires exactly one row. Multiple rows throw a size error; do not call it hoping it automatically takes the first row.

**Mistake 12 – Assuming `RowCallbackHandler` guarantees streaming:** the driver may have buffered large amounts of data before invoking the callback. For large sets, examine fetch size, transaction duration, memory, and driver cursor management; ensure streams are closed when using streaming APIs.

## 17. Knowledge Check Exercises

**Exercise 1.** You need to convert each SQL row into an `Account` and return `List<Account>`. Which callback should you use?

**Answer:** `RowMapper<Account>` in `JdbcTemplate.query(...)`. Spring iterates the result set and builds the list.

**Exercise 2.** You need to bind two parameters for `WHERE status = ? AND balance >= ?`. Which callback is solely responsible for binding?

**Answer:** `PreparedStatementSetter`, using `ps.setString(1, status)` and `ps.setBigDecimal(2, minBalance)`. For simple cases, passing `Object... args` directly also works.

**Exercise 3.** You need to iterate over the entire `ResultSet` yourself to return `Map<Long, List<Long>>` grouped by parent key. What should you use?

**Answer:** `ResultSetExtractor<Map<Long, List<Long>>>`, because the extractor controls the `rs.next()` loop and builds a single overall result structure.

**Exercise 4.** Why must `processRow(ResultSet rs)` not call `rs.next()`?

**Answer:** `JdbcTemplate` has already positioned the cursor on the current row before calling `RowCallbackHandler`. Advancing the cursor yourself skips rows or breaks iteration order.

**Exercise 5.** To retrieve keys generated by `INSERT`, which callback helps prepare a statement with `RETURN_GENERATED_KEYS`?

**Answer:** `PreparedStatementCreator`, used with the `jdbcTemplate.update(creator, keyHolder)` overload and a supporting DB/driver.

**Exercise 6.** A callback throws `SQLException`. Do you need to close the connection owned by `JdbcTemplate` yourself?

**Answer:** No. `JdbcTemplate` catches and translates JDBC exceptions while managing statements, result sets, and connections according to the transaction. Only clean up auxiliary resources created by the callback itself.

**Exercise 7.** A query returns 0 rows. How do `query(sql, mapper)` and `queryForObject(sql, mapper)` differ?

**Answer:** `query` returns an empty list, whereas `queryForObject` requires exactly one row and therefore throws `EmptyResultDataAccessException`.

**Exercise 8.** With the sample SQL in Section 4, how many objects does `RowMapper` create when querying `status = ACTIVE`?

**Answer:** Two: Lan's and Vy's accounts. `ResultSetExtractor` could return the number 2, a list, or a `Map` depending on its implementation; the callback type does not change the number of SQL rows returned by the DB.

## 18. Key Takeaways

- `JdbcTemplate` handles the **shared workflow**; callbacks describe the varying parts: **SQL**, **parameters**, and **how results are read**.
- `PreparedStatementCreator` creates a statement from a connection; `PreparedStatementSetter` binds parameters on an existing statement.
- `RowMapper` returns one object **per row**; `RowCallbackHandler` executes an action per row; `ResultSetExtractor` iterates **the whole set** and returns one overall result.
- `RowMapper` and `RowCallbackHandler` **must not call `rs.next()`**; `ResultSetExtractor` must advance the cursor itself to read rows.
- `PreparedStatementCallback` enables direct operations on a `PreparedStatement` when high-level APIs are insufficient; the template still manages resources and translates JDBC errors.
- Prefer `query(sql, mapper, args...)`, `update(...)`, or `batchUpdate(...)` whenever they express the requirement cleanly. Write low-level callbacks only when genuine control is needed.
- Use bound parameters instead of concatenating input into SQL; handle `NULL` and `?` ordering carefully; never share callbacks containing unsafe mutable state across requests.
- On Spring 6.1+, `JdbcClient` expresses the same work with a fluent API; understanding callback contracts remains essential to avoid mapping and resource bugs.

### Reference Documentation

- [Spring Framework 6.1: `JdbcTemplate` API](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework 6.1: `PreparedStatementCreator`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreator.html)
- [Spring Framework 6.1: `RowCallbackHandler`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html)
- [Spring Framework 6.1: `ResultSetExtractor`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html)
- [Spring Framework: Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
