# JDBC Parameter Indexing Starts at 1

In JDBC, when an SQL statement has question marks `?` used as **parameter markers**, `PreparedStatement.setXxx(parameterIndex, value)` assigns values using **1-based indexing**, not 0-based. The first `?` is parameter **1**, the second `?` is parameter **2**, and so on sequentially in order of appearance in the SQL statement.

This seemingly minor rule is a common source of *off-by-one* errors: developers accustomed to 0-indexed Java arrays accidentally pass 0 to `setString(0, ...)` or shift by one position when using multiple `WHERE`, `INSERT`, or `UPDATE` conditions. In Spring Framework – data-access applications, you need to understand this rule when writing plain JDBC, `PreparedStatementSetter`, dynamic queries, and when reading SQL errors.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Count the order of `?` markers in SQL accurately and create a mapping table of *parameter index → column/expression → Java value*.
2. Write `setString(1, ...)`, `setLong(2, ...)`, `setNull(3, ...)` at the right positions in `PreparedStatement`.
3. Distinguish **JDBC parameter indexing (1-based)** from **Java array/List indexing (0-based)**.
4. Recognize that `ResultSet.getXxx(int columnIndex)` and `ParameterMetaData` also use 1-based indexing, though for different concepts.
5. Fix `SQLException` errors caused by parameter index = 0, index exceeding the marker count, missing bindings, or binding in the wrong order.
6. Apply the rule with `SELECT`, `INSERT`, `UPDATE`, `CallableStatement`, `batch`, and dynamic `IN (...)` lists.
7. Understand when Spring `JdbcTemplate` handles binding order for you and when callback code still requires 1-based indexing.
8. Test with a standalone Java 17+ program and with database-backed integration tests.

## 2. Why Does JDBC Use 1-Based Indexing?

Consider the SQL statement:

~~~sql
SELECT id, email
FROM account
WHERE status = ? AND created_at >= ? AND email = ?;
~~~

Read the **actual `?` parameter markers** from left to right:

| Marker | Index passed to JDBC | SQL expression receiving the value | Example setter |
| --- | ---: | --- | --- |
| 1st `?` | **1** | `status = ?` | `ps.setString(1, "ACTIVE")` |
| 2nd `?` | **2** | `created_at >= ?` | `ps.setTimestamp(2, timestamp)` |
| 3rd `?` | **3** | `email = ?` | `ps.setString(3, email)` |

Rule in the JDBC API: **parameterIndex = 1 is the first parameter, 2 is the second parameter, ...**. JDBC designed its binding methods around a sequence of positions starting at 1; do not assume that because Java arrays are 0-indexed, the JDBC API is as well.

~~~text
Java List/array:     values[0]   values[1]   values[2]
                         |           |           |
SQL:                     ?           ?           ?
JDBC parameterIndex:     1           2           3
                         ^           ^           ^
                       setX(1)     setX(2)     setX(3)
~~~

This index is the **order of markers in the SQL**, not the table's column order, column name, schema column order, or the argument position in a service method. If you change the order of conditions in the SQL, you must revisit the binding order.

### What Counts as a Marker?

A `?` appearing in the SQL statement that is recognized by the driver as a **parameter marker** creates a bind position. A question mark inside a **string literal** like `'?'` is not a `PreparedStatement` marker:

~~~sql
SELECT id
FROM ticket
WHERE text_value = '?' AND owner_id = ?;
~~~

Here, the question mark inside `'?'` is comparison text; the question mark after `owner_id =` is marker **number 1**. For SQL dialects with operators containing `?` (such as certain JSON operators), how the parser/escaping interacts with the JDBC driver may differ; check the driver documentation instead of counting `?` characters with a naive string expression.

## 3. PreparedStatement: Right and Wrong Examples

The example code lives inside a method that already has a `java.sql.Connection connection`:

~~~java
String sql =
        "SELECT id, email FROM account WHERE status = ? AND email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "ACTIVE");
    ps.setString(2, "an@example.test");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id") + " " +
                               rs.getString("email"));
        }
    }
}
~~~

This is an **integration snippet**; it requires JDBC imports, a database, an `account` table, and a real connection to run. `try-with-resources` closes `ResultSet` and `PreparedStatement`. When a method also owns the connection, it must release the connection per its lifecycle, typically via `try-with-resources` or Spring's transaction mechanism.

**Wrong index 0:**

~~~java
ps.setString(0, "ACTIVE"); // WRONG: there is no JDBC parameter number 0.
~~~

For standard `PreparedStatement`, index 0 is invalid and the driver typically throws an `SQLException`. The error message string, exception subclass, and validation timing can vary by driver; do not depend on a fixed error message.

**Wrong order despite valid indices:**

~~~java
ps.setString(1, "an@example.test"); // SEMANTIC ERROR: marker 1 is status.
ps.setString(2, "ACTIVE");          // SEMANTIC ERROR: marker 2 is email.
~~~

Both values are `String`, so the driver may not report a syntax or type error. The query still runs but fails to find the right results. This is more dangerous than an obvious off-by-one error because **an exception is not guaranteed**.

**Index exceeds marker count:**

~~~java
ps.setString(3, "EXTRA"); // The SQL only has 2 markers.
~~~

A `PreparedStatement` for the SQL above only has indices 1 and 2. Assigning index 3 may trigger an `SQLException` because there is no matching parameter marker. Do not confuse this with the fact that a statement can return many **columns** or **rows**; the number of result rows/columns does not determine the number of parameter markers.

**Forgetting to bind a marker:**

~~~java
ps.setString(1, "ACTIVE");
ps.executeQuery(); // Marker 2 has not been assigned for this execution.
~~~

For a statement requiring both parameters, a missing binding typically causes an error at execution time or at the point where the driver checks parameters. The message usually describes an unset parameter; exact behavior depends on the driver. To avoid stale binding state, code explicitly and assign **every marker** before each execution.

## 4. Standalone Java 17+ Example Without a Database

The JDK provides `javax.sql.rowset.CachedRowSet`, a `RowSet` implementation that lets you configure an SQL command and set positional parameters. The following example demonstrates the rule **indices 1 and 2 are valid; index 0 is invalid** without needing a database connection.

Save as exact filename `RowSetParameterProbe.java`:

~~~java
import java.sql.SQLException;
import javax.sql.rowset.CachedRowSet;
import javax.sql.rowset.RowSetProvider;

public class RowSetParameterProbe {
    public static void main(String[] args) throws Exception {
        try (CachedRowSet rowSet =
                     RowSetProvider.newFactory().createCachedRowSet()) {
            rowSet.setCommand(
                    "SELECT * FROM account WHERE id = ? AND state = ?"
            );

            rowSet.setLong(1, 42L);
            rowSet.setString(2, "ACTIVE");
            System.out.println("bound parameters 1 and 2");

            try {
                rowSet.setLong(0, 99L);
                System.out.println("unexpected success for index zero");
            } catch (SQLException error) {
                System.out.println("index 0 rejected");
            }
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 RowSetParameterProbe.java
java RowSetParameterProbe
~~~

Stdout in the Java 17 environment used for verification:

~~~text
bound parameters 1 and 2
index 0 rejected
~~~

`setCommand(...)` only stores the command on the rowset; the example **does not execute SQL** and does not require a real `account` table. It demonstrates the behavior of the JDK's `CachedRowSet` implementation for practicing the parameter-setting API, and does not replace integration tests with the JDBC driver used in your project.

Do not conclude that every `SQLException` from a driver prints the exact line `index 0 rejected`: this is a fixed message caught and printed by the program so the lesson stays independent of driver-specific messages.

## 5. Real JDBC Example with DataSource: Explicit Mapping of Each Parameter

Suppose the illustrative schema is:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL
);
~~~

The following `AccountDao.java` class uses **Java 17**, JDBC/JDK interfaces, an injected `DataSource`, and reads/binds using proper 1-based parameter positions.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountDao {
    public record Account(long id, String email) {}

    private final DataSource dataSource;

    public AccountDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Account> findByEmailAndActive(
            String email, boolean active) throws SQLException {
        String sql = """
                SELECT id, email
                FROM account
                WHERE email = ? AND active = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, email);       // first WHERE email = ?
            ps.setBoolean(2, active);     // second WHERE active = ?

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Account(
                        rs.getLong("id"),
                        rs.getString("email")
                ));
            }
        }
    }
}
~~~

This class **compiles with Java 17** but is not a standalone CLI program because it has no `main`; running it in practice requires a `DataSource`, a driver, and a matching database/schema. If the `email` column lacks a unique constraint, the query may return multiple rows and the method only takes the first row; when the business contract requires uniqueness, add an appropriate constraint or check `rs.next()` a second time to reject results with invalid cardinality.

Here there are two distinct concepts:

- `ps.setString(1, email)`: **binds marker number 1** in SQL.
- `rs.getLong("id")`: **reads a column** on the current result row; unrelated to the parameter index.

Having the method accept two Java arguments in the order `email, active` does not automatically bind them to the SQL. It is the two calls `setXxx(1, ...)` and `setXxx(2, ...)` that map them to the query positions. If you change the SQL to `WHERE active = ? AND email = ?`, you must update the binding code accordingly:

~~~java
ps.setBoolean(1, active);
ps.setString(2, email);
~~~

**Code readability tip:** Before any complex binding block, write a short table *marker 1 → email, marker 2 → active* or keep the SQL and setters close together. Avoid copying marker 2 for two columns and forgetting marker 1.

## 6. Distinguishing Three Indexing Systems: Java, Parameters, and ResultSet

The following three places look similar, but each has its own rule:

| Mechanism | Index starts at | What is indexed |
| --- | ---: | --- |
| Java array `args[i]`, `List.get(i)` | **0** | Element in collection |
| `PreparedStatement.setXxx(parameterIndex, value)` | **1** | `?` marker in SQL |
| `ResultSet.getXxx(columnIndex)` | **1** | Column in `SELECT` result set |
| `ResultSetMetaData.getColumnName(column)` | **1** | Column in result set metadata |
| `ParameterMetaData.getParameterType(param)` | **1** | Statement parameter marker |
| `CallableStatement.registerOutParameter(parameterIndex, ...)` | **1** | Parameter/return slot position in callable syntax |

Example SQL statement:

~~~sql
SELECT email, id
FROM account
WHERE id = ? AND active = ?;
~~~

Suppose you have:

~~~java
Object[] values = {42L, true}; // values[0] and values[1]
ps.setLong(1, (Long) values[0]);    // Marker 1: id
ps.setBoolean(2, (Boolean) values[1]); // Marker 2: active

try (ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        String email = rs.getString(1); // Column 1 in SELECT: email
        long id = rs.getLong(2);       // Column 2 in SELECT: id
    }
}
~~~

Look at `ps.setLong(1, ...)` and `rs.getString(1)`: **same number 1, yet pointing to two different things** (first parameter vs. first result column). Do not rely on column order in `CREATE TABLE` to assume `ResultSet` indices; `ResultSet` column positions are determined by the **SELECT list**. Using a label/column name with `rs.getString("email")` is usually easier to read, especially when queries change column order.

## 7. When Iterating Over a Java List, Use i + 1

If you have a sequence of values in a Java array/List, the loop starts at `i = 0` to get the first element. However, JDBC requires the first parameter to have index 1:

~~~java
List<Long> ids = List.of(10L, 20L, 30L);
for (int i = 0; i < ids.size(); i++) {
    ps.setLong(i + 1, ids.get(i));
}
~~~

Conversion table:

| Java `i` | `ids.get(i)` | JDBC `parameterIndex = i+1` |
| ---: | ---: | ---: |
| 0 | 10 | 1 |
| 1 | 20 | 2 |
| 2 | 30 | 3 |

This loop is only correct if the SQL genuinely has three markers and all three markers receive the IDs sequentially in that order. It does not automatically add `?` to the SQL statement. You must prepare an SQL statement with the matching number of markers:

~~~sql
SELECT id, email FROM account WHERE id IN (?, ?, ?);
~~~

### Variable-Length IN Lists

JDBC positional parameters do not mean every driver will automatically "expand" a `List` into multiple markers when you write `IN (?)`. With plain JDBC, the clear portable approach is to generate exactly one question mark per value and bind at index `i+1`:

~~~java
import java.util.Collections;
import java.util.List;

List<Long> ids = List.of(10L, 20L, 30L);
String markers = String.join(
        ", ", Collections.nCopies(ids.size(), "?")
);
String sql = "SELECT id, email FROM account WHERE id IN (" + markers + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read result rows.
        }
    }
}
~~~

The resulting `sql` has three markers `IN (?, ?, ?)`; values are never concatenated directly into the SQL. This is an integration snippet requiring `Connection connection` and appropriate JDBC imports.

**Empty list case:** `nCopies(0, "?")` produces an empty string, leading to `IN ()`, which is not portable and may be invalid SQL syntax. Decide the business behavior explicitly: if the input is empty, return an empty result list before running the query, or build an SQL statement with an always-false condition per dialect. Never run SQL with `IN ()` unchecked.

### When Markers Precede the IN List

Suppose the SQL is:

~~~sql
SELECT id
FROM account
WHERE active = ?
  AND id IN (?, ?, ?);
~~~

Marker 1 is for `active`; the IDs must start at marker **2**, not 1:

~~~java
ps.setBoolean(1, true);
for (int i = 0; i < ids.size(); i++) {
    ps.setLong(i + 2, ids.get(i));
}
~~~

This is the general rule: if `offset` markers have already been used before the list, the JDBC index for the `i`-th Java element is `offset + i + 1`. Avoid hardcoding offsets if the SQL can be composed from multiple parts; in that case, use an explicit binding management strategy or a library supporting named parameters.

## 8. INSERT: Marker Order in VALUES

Suppose the table is:

~~~sql
INSERT INTO account (id, email, active)
VALUES (?, ?, ?);
~~~

Binding:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO account (id, email, active) VALUES (?, ?, ?)")) {
    ps.setLong(1, 101L);
    ps.setString(2, "an@example.test");
    ps.setBoolean(3, true);
    int rows = ps.executeUpdate();
}
~~~

The marker order in `VALUES` matches the specified columns `id, email, active`. If you change the column order:

~~~sql
INSERT INTO account (email, active, id)
VALUES (?, ?, ?);
~~~

then marker 1 is now `email`, marker 2 is `active`, and marker 3 is `id`. The setters must also change accordingly:

~~~java
ps.setString(1, "an@example.test");
ps.setBoolean(2, true);
ps.setLong(3, 101L);
~~~

**There is no rule** that "parameter number 1 is always the primary key" or "parameter indices match schema column order." The numbers only represent marker positions of **the statement being prepared**.

## 9. UPDATE: Markers in SET Appear Before Markers in WHERE

A classic source of bugs is binding the ID first because the ID is the key, even though the SQL has markers for the updated data appearing earlier:

~~~sql
UPDATE account
SET email = ?, active = ?
WHERE id = ?;
~~~

Correct order:

~~~java
ps.setString(1, "new@example.test"); // email in SET
ps.setBoolean(2, true);             // active in SET
ps.setLong(3, 101L);                // id in WHERE
int count = ps.executeUpdate();
~~~

**Semantic error** when binding `id` to index 1 because you think of it as the account identifier, then binding email/active to 2/3. When type coercion is possible, the driver might execute the SQL with wrong values without throwing an immediate error; when coercion is impossible, you may see a type mismatch `SQLException`.

If an SQL statement uses the same value in two places, the two `?` signs are still **two separate markers**:

~~~sql
SELECT id FROM account WHERE email = ? OR recovery_email = ?;
~~~

Even though both receive the same email, you must bind it twice:

~~~java
ps.setString(1, email);
ps.setString(2, email);
~~~

JDBC positional parameters do not automatically link two markers to the same variable just because they appear to mean the same thing.

## 10. SQL NULL and Setter Methods

The index still starts at 1 when the passed value is NULL. With a `nickname VARCHAR NULL` column:

~~~sql
UPDATE account_profile
SET nickname = ?
WHERE account_id = ?;
~~~

Java code:

~~~java
if (nickname == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, nickname);
}
ps.setLong(2, accountId);
~~~

`setNull(1, Types.VARCHAR)` assigns SQL NULL at **marker 1**, explicitly specifying the expected SQL type. `setString(1, null)` can be handled by many drivers, but for typed SQL NULL, `setNull` makes intent and data type clearer, especially in queries/drivers sensitive to type inference.

Another option is `setObject(1, null, Types.VARCHAR)` using the overload that accepts `targetSqlType`, if the driver supports that type. Avoid relying on `setObject(1, null)` when the driver lacks sufficient type inference information to handle it consistently.

**NULL is not "binding nothing."** If a column is nullable and you want to pass SQL NULL, you must still invoke a setter for that position. Skipping the setter is not equivalent to passing NULL; it can lead to a missing parameter value error, or worse, reuse a stale binding if the statement is reused.

### Distinguishing Setter, Getter, and wasNull

On the **write/bind** side: `ps.setNull(1, Types.VARCHAR)` specifies that parameter number 1 is SQL NULL.

On the **read result** side: `rs.getString(1)` reads result column number 1 and returns Java `null` if it is SQL NULL. With primitive getters like `rs.getInt(1)`, you need `rs.wasNull()` to distinguish 0 from SQL NULL. The 1-based rule appears in both setters and getters, but their semantics differ.

## 11. A PreparedStatement Can Be Reused Multiple Times

When reusing a `PreparedStatement` for multiple values, **the markers keep the same indices** from the prepared SQL. Subsequent executions can change the values, rather than creating marker 0 or incrementing marker 1 to 3.

Example updating by each ID:

~~~java
String sql = "UPDATE account SET active = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long id : List.of(10L, 20L, 30L)) {
        ps.setBoolean(1, false);
        ps.setLong(2, id);
        ps.executeUpdate();
    }
}
~~~

Every iteration binds **1 → active**, **2 → id**. Do not write `setLong(i + 2, id)` with a loop counter; that confuses parameter position with iteration index.

### clearParameters and Stale Bindings

`ps.clearParameters()` removes parameter values currently assigned on the statement, **without changing the marker count or indices**. If you want to change the parameter set and avoid leftover old data, you can call `clearParameters()` before a new binding pass, then assign all markers. Depending on your needs, the simplest code always reassigns every marker on each iteration.

~~~java
ps.clearParameters();
ps.setBoolean(1, true);
ps.setLong(2, 20L);
ps.executeUpdate();
~~~

Do not call `clearParameters()` after binding everything and right before execution: it will wipe out the bound values. Remember that a statement is prepared for a specific SQL; if you want to change the marker count or SQL structure, you must create a matching statement.

### executeBatch: Indices Reset per Entry, Not to Batch Count

A `PreparedStatement` can execute multiple parameter sets using `addBatch()`:

~~~java
String sql = "UPDATE account SET active = ? WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long id : List.of(10L, 20L, 30L)) {
        ps.setBoolean(1, true);
        ps.setLong(2, id);
        ps.addBatch();
    }
    int[] affected = ps.executeBatch();
}
~~~

Each `addBatch()` call adds one set of values for the same **two markers**. The indices remain 1 and 2 in every batch item. The result of `executeBatch()` may contain update counts or JDBC-specific status codes per command; do not assume every element is necessarily a positive row count.

## 12. CallableStatement: IN, OUT Parameters, and Return Position

`CallableStatement` extends `PreparedStatement` to invoke stored procedures/functions. **Positional** parameters also start at 1:

~~~java
try (CallableStatement call =
        connection.prepareCall("{call update_balance(?, ?)}")) {
    call.setLong(1, accountId);
    call.setBigDecimal(2, delta);
    call.execute();
}
~~~

If the stored procedure has two positional IN parameters, `accountId` is index 1 and `delta` is index 2. Drivers may support named parameter binding in some cases, but named overloads should not be assumed portable across all databases.

### Function Return Sits at Position 1 in JDBC Escape Syntax

Some JDBC drivers support the function call form:

~~~sql
{? = call calculate_points(?)}
~~~

In this syntax, **the first marker represents the return value** of the function, while the first argument is marker **2**. Code pattern:

~~~java
try (CallableStatement call =
        connection.prepareCall("{? = call calculate_points(?)}")) {
    call.registerOutParameter(1, java.sql.Types.INTEGER);
    call.setLong(2, accountId);
    call.execute();
    int points = call.getInt(1);
}
~~~

This is an **illustrative pattern**: syntax, type registration, return values, and stored function support depend on the specific database/driver. Yet JDBC's positional index principle remains true: there is no parameter number 0. Do not assign `accountId` to marker 1 in `{? = call ...}` syntax, because that position is reserved for the function return.

## 13. ParameterMetaData: Checking Marker Count and Parameter Types

JDBC provides `ParameterMetaData` to inspect information about parameter markers:

~~~java
ParameterMetaData metadata = ps.getParameterMetaData();
int parameterCount = metadata.getParameterCount();
System.out.println("parameterCount=" + parameterCount);
~~~

For the SQL `WHERE email = ? AND active = ?`, the expected marker count is **2**. Metadata APIs use 1-based indexing when querying **information for a parameter**:

~~~java
int typeFirst = metadata.getParameterType(1);
int typeSecond = metadata.getParameterType(2);
~~~

However, **support for parameter metadata is uneven across drivers**, especially when the server has not yet actually prepared the statement, the SQL contains hard-to-infer types, or there are complex stored procedures. Some drivers may throw `SQLFeatureNotSupportedException` or return incomplete information. Therefore:

- `getParameterCount()` is useful when the driver supports it, but does not replace SQL testing.
- Do not require metadata to work completely just to bind a simple SQL statement.
- Do not use `getParameterType(0)` because metadata parameter indices are also 1-based.
- Do not confuse `ParameterMetaData` with `ResultSetMetaData`, which describes **result columns** and also uses 1-based indexing.

## 14. Spring JdbcTemplate: When Do You Still Need 1-Based Indexing Yourself?

Spring JDBC provides convenient APIs that reduce boilerplate around `Connection`, `PreparedStatement`, and `ResultSet`. However, there are two very different groups of situations:

### 14.1. Overloads Accepting Arguments in Order

In an application that already has `JdbcTemplate jdbc`:

~~~java
List<Long> ids = jdbc.query(
        "SELECT id FROM account WHERE active = ? AND email = ?",
        (rs, rowNum) -> rs.getLong("id"),
        true,
        "an@example.test"
);
~~~

This is an **integration Spring JDBC** example; it needs a `JdbcTemplate` bean, a `DataSource`, and a schema. You pass the Java arguments `true` then `"an@example.test"` in the order of markers in the SQL. Spring performs the JDBC binding work, so **the caller does not manually call `setBoolean(1, ...)`**.

On the Java side, when handling varargs or an argument array, `args[0]` is still the first element of the array. This does not contradict 1-based JDBC indexing: **Spring translates Java argument positions to JDBC marker positions** in its binding layer.

Do not take this `RowMapper` usage as an example of result column indexing: `rs.getLong("id")` reads by label. `rowNum` in the callback is the **row index provided by Spring** and is 0-based per the `RowMapper.mapRow(rs, rowNum)` contract, not a JDBC parameterIndex. That is another index pitfall to distinguish.

### 14.2. PreparedStatementSetter Callback: Your Code Calls JDBC Directly

When using `PreparedStatementSetter`, the callback receives the `PreparedStatement` itself. You must follow the 1-based rule:

~~~java
List<Long> ids = jdbc.query(
        "SELECT id FROM account WHERE active = ? AND email = ?",
        ps -> {
            ps.setBoolean(1, true);
            ps.setString(2, "an@example.test");
        },
        (rs, rowNum) -> rs.getLong("id")
);
~~~

This snippet uses the `JdbcTemplate.query(String sql, PreparedStatementSetter pss, RowMapper<T> rowMapper)` overload with the appropriate Spring JDBC library; it is an integration example, not a standalone program. The callback must not use `ps.setBoolean(0, ...)` just because `rowNum` starts at 0.

If you have both varargs `JdbcTemplate` overloads and `PreparedStatementSetter` callbacks, choose **one binding mechanism** matching the overload being called; do not bind again arbitrarily in multiple places.

### 14.3. NamedParameterJdbcTemplate Eliminates Counting Markers at the Call Site

When SQL has many parameters or the order is easy to mix up, you can use `NamedParameterJdbcTemplate`:

~~~java
String sql = """
        SELECT id FROM account
        WHERE email = :email AND active = :active
        """;

var params = new org.springframework.jdbc.core.namedparam
        .MapSqlParameterSource()
        .addValue("email", "an@example.test")
        .addValue("active", true);

List<Long> ids = namedJdbc.query(
        sql, params, (rs, rowNum) -> rs.getLong("id")
);
~~~

Here `namedJdbc` is a `NamedParameterJdbcTemplate` bean. The snippet uses **names** `:email` and `:active` instead of writing numbers 1 and 2 at the call site. Spring parses the SQL and maps the names to the appropriate JDBC positions at execution time. **This does not mean PreparedStatement became 0-based**; the conversion is handled by the framework.

A parameter name can appear multiple times in the SQL; the framework can bind the same value to multiple positions. With `IN (:ids)`, `NamedParameterJdbcTemplate` can expand the list into multiple placeholders via library support, which is more convenient than plain JDBC manually concatenating markers. You still need to handle empty lists according to business rules and the SQL dialect; do not assume every SQL shape is automatically supported.

## 15. Parameter Markers Only Bind **Values**, Not Table/Column Names

Correct usage:

~~~sql
SELECT id FROM account WHERE email = ?;
~~~

A `?` represents a **value** passed from Java, not an arbitrary SQL snippet.

Misintended example:

~~~sql
SELECT ? FROM account WHERE id = ?;
~~~

If you want to pass a **column name** to the first question mark, the statement will not turn it into an identifier. The driver treats that parameter as an expression value if SQL syntax allows it, leading to unexpected results. Similarly, using `FROM ?` to supply a table name is usually invalid.

If users can choose a sort column or field name, validate the selection against an **allowlist of fixed identifiers** and then build controlled SQL; values like email/id must still be bound with `?`. Never concatenate input directly into SQL just to avoid indexing. Proper `PreparedStatement` usage separates values from the statement and reduces SQL injection risk.

## 16. Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `SQLException` stating `parameter index 0` is invalid | Java index 0 passed straight into JDBC | Use 1 for the first marker; in loops use `i + 1` |
| Driver reports parameter index out of range | SQL has fewer markers than bound | Count actual markers; inspect prepared SQL for literal `'?'` |
| Reports unset parameter on `execute` | Missing setter call / `clearParameters()` was called | Bind all markers before each execute pass |
| Query runs but returns wrong data | Two values swapped marker order while types still matched | Make a marker → expression → setter table, check SQL |
| Update affects 0 rows | `WHERE` received wrong value or no matching record | Log SQL template and masked arguments; verify order |
| Conversion/type mismatch | Marker bound with wrong setter/type | Compare target SQL type and Java value |
| `CallableStatement` returns wrong slot | Function return slot and IN args confused | For `{? = call ...}`, return is 1, first IN is 2 |
| Dynamic `IN (...)` has wrong index | Loop used Java 0-index or forgot offset before list | Use `offset + i + 1`, verify marker count |
| `ParameterMetaData` unsupported | Driver lacks introspection capability | Read driver message; do not treat as an index bug |
| Spring query overload mismatch | Confused setter callback, mapper, and varargs | Pick overload with matching signature; compile integration code |

**Read stack traces at the right layer:** With `PreparedStatement.setXxx`, index errors often appear at the bind line. However, a JDBC driver can also defer validation until `executeQuery()`/`executeUpdate()`. Read the specific message and root cause rather than assuming errors always throw immediately on the setter line.

### Do Not Confuse SQL Parameters with ResultSet Columns

SQL:

~~~sql
SELECT email, id
FROM account
WHERE active = ? AND id = ?;
~~~

Parameters 1 and 2 belong to `active`/`id`; ResultSet columns 1 and 2 belong to `email`/`id`. When encountering an error like `Invalid column index: 0` while calling `rs.getString(0)`, that is a **ResultSet column index error**, not a `PreparedStatement` binding error.

### Observing Parameter Values Safely

When debugging, you can log marker numbers, business field names, and bound value types (for example `marker 1=status, marker 2=email`). Avoid logging passwords, access tokens, personal information, or sensitive data. Some drivers/frameworks support SQL logs with bind values; enable them per security policy, in test environments, and with necessary masking.

## 17. Practical Workflow for Fixing Off-by-One Bugs

Suppose a function needs to query:

~~~sql
SELECT id FROM transaction_record
WHERE account_id = ?
  AND amount >= ?
  AND created_at < ?;
~~~

Follow this sequence:

1. Write the complete SQL and number the markers from left to right: **1 = account_id, 2 = amount, 3 = created_at**.
2. Choose setters matching the data types: `setLong(1, accountId)`, `setBigDecimal(2, minAmount)`, `setTimestamp(3, cutoff)`.
3. Ensure no marker is skipped or unintentionally overwritten.
4. If parameters come from a `List`/array, double-check the `+ 1` and offset arithmetic.
5. Run tests with distinctly different input values to catch cases where swapped bindings occur without raising an `SQLException`.

Sample code:

~~~java
String sql = """
        SELECT id FROM transaction_record
        WHERE account_id = ?
          AND amount >= ?
          AND created_at < ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, accountId);
    ps.setBigDecimal(2, minimumAmount);
    ps.setTimestamp(3, cutoff);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long transactionId = rs.getLong(1);
            // Process transactionId.
        }
    }
}
~~~

In Spring applications, if manual marker counting becomes complex, consider `NamedParameterJdbcTemplate` for queries needing many named parameters. When you must write a `PreparedStatementSetter` callback, still keep the rule **first index equals 1**.

## 18. Testing Both Right and Wrong Cases

A test suite should include both **loud failures** and **silent bugs**:

| Test | How to Perform | Expected Outcome to Verify |
| --- | --- | --- |
| Valid index 1 | `setLong(1, 42L)` when SQL has a marker | Binds successfully |
| Invalid index 0 | `setLong(0, 42L)` | `SQLException` or JDBC-compliant rejection behavior |
| Index too large | `setLong(3, 42L)` with SQL having only 2 markers | Driver rejects, cannot bind non-existent marker |
| Missing binding | SQL has 2 markers but only 1 assigned | Driver does not execute validly with missing parameter |
| Swapped compatible types | Two `String` values assigned to wrong markers | Business test catches wrong result, not just asserting "no exception" |
| SQL `UPDATE` with `SET` before `WHERE` | Bind data at 1/2, id at 3 | Updates right record, expected affected count |
| 3-element List | Java loop `i = 0..2`, bind `i + 1` | Indices 1, 2, 3 receive right elements |
| List with marker offset | `active` marker at 1, list starts at 2 | Does not overwrite parameter 1 |
| Callable function | Return marker at 1, IN argument at 2 | Registers and binds at right positions |
| Spring callback | `PreparedStatementSetter` uses 1-based | Compiles and runs query properly |
| Spring varargs | `jdbc.query(..., true, email)` | Arguments map in marker order |

Production-like testing requires a real driver/database, because the standalone `CachedRowSet` in section 4 does not prove every driver behavior. For `INSERT/UPDATE`, run tests inside a transaction and roll back when appropriate to avoid polluting data. For a specific database/driver, assert stable exception types per the library contract rather than exact message text that may change across versions.

## 19. Self-Check Exercises

**Question 1.** How many markers does `SELECT * FROM product WHERE category = ? AND price >= ?` have, and what index is the first marker?  
**Answer:** Two markers; the first marker has index **1**, the second marker has index **2**.

**Question 2.** Why is `ps.setString(0, "BOOK")` wrong even though `String[] filters` has its first element at index 0?  
**Answer:** Java arrays/Lists are 0-indexed, whereas `PreparedStatement` parameter indices start at 1; you must use `ps.setString(1, filters[0])`.

**Question 3.** In `UPDATE product SET name = ? WHERE id = ?`, is marker 1 the id?  
**Answer:** No. Marker 1 is `name` in `SET`; marker 2 is `id` in `WHERE`.

**Question 4.** If `List<Long> ids` has three elements and the SQL is `IN (?, ?, ?)`, which indices does the loop `i=0..2` bind to?  
**Answer:** `i + 1` → 1, 2, 3.

**Question 5.** SQL `WHERE active = ? AND id IN (?, ?)`: where are the two IDs bound?  
**Answer:** `active` at 1; first ID at 2, second ID at 3.

**Question 6.** Do `ps.setString(1, email)` and `rs.getString(1)` mean the same thing?  
**Answer:** No. The first binds marker 1; the second reads result column 1 on the current row.

**Question 7.** How many markers does `WHERE message = '?' AND id = ?` have?  
**Answer:** One bind marker at `id = ?`; `'?'` is a string literal, not a marker.

**Question 8.** Does `{? = call calculate_points(?)}` take `accountId` at parameter 1 or 2?  
**Answer:** 2. Marker 1 is reserved for the function return.

**Question 9.** If `jdbc.queryForObject(sql, Long.class, email, true)` is being used, do you still need to call `setString(1, email)` in the service?  
**Answer:** No; Spring's convenience overload performs binding from the arguments in order. Only when using a `PreparedStatementSetter` callback does callback code call 1-based setters.

**Question 10.** When encountering an exception "parameter has no value," should you call `setNull(0, Types.VARCHAR)` to "fill it in"?  
**Answer:** No. Find which marker in **1..N** was not assigned; if you want SQL NULL at that marker, use `setNull(validIndex, sqlType)`.

## 20. Conclusion

Remember one sentence: **JDBC positional parameters start at 1; Java arrays/Lists start at 0.** The first `?` is bound with `setXxx(1, ...)`, the second with `setXxx(2, ...)`, regardless of column order, primary keys, or Java variable names. When looping over a collection, use `i + 1` (plus any offset if earlier markers precede it). When working via a Spring `PreparedStatementSetter` callback, the rule still holds; whereas argument-taking `JdbcTemplate` overloads or `NamedParameterJdbcTemplate` handle positional mapping for you.

Index 0 or out-of-range marker errors are usually easy to spot. **Swapped-order binding bugs** are what deserve extra care because code may run without exceptions yet return wrong results; therefore build a marker → value table, read SQL from left to right, and test with distinguishing data.

### References

- [Oracle Java SE 17 — PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): `setString`, `setInt`, `setNull`, parameter binding, and `execute`.
- [Oracle Java SE 17 — ParameterMetaData API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ParameterMetaData.html): parameter count and metadata queries by index.
- [Oracle Java SE 17 — CallableStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html): OUT parameter registration and positional JDBC escape syntax.
- [Oracle Java SE 17 — ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): 1-based ResultSet column indices.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `PreparedStatementSetter`, and named parameters.
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): named SQL parameters and list expansion.