# SQL Parameters Only Substitute Values, Never Table Names, Column Names, or SQL Syntax

In Spring JDBC, **question marks ?**, **named parameters :param**, and **PreparedStatement.setXxx(...)** calls are used to pass **data values** into an SQL statement whose structure is already defined. They **do not** substitute table names, column names, keywords, operators, or entire SQL clauses. This is the most important boundary when building repositories with search, sorting, reporting, or dynamic filtering parameters.

If you assume anything can be passed through a parameter, the program may fail with syntax errors, return wrong results, or tempt you into concatenating raw strings into the SQL statement. Concatenating structure from untrusted input reopens the door to **SQL injection**, even when other parts of the `WHERE` clause already use `PreparedStatement`.

This lesson belongs to **Spring Framework - data-access**, topic group **SQL Parameters**. We will separate SQL structure from values, use `JdbcTemplate`/`NamedParameterJdbcTemplate`/`JdbcClient`, build dynamic `ORDER BY` and table selection via allow-lists, handle `IN`/`LIKE`/`NULL`, and then run a Java 17+ example with H2 to prove it.

## 1. Breaking a Query into Structure and Values

Consider:

~~~sql
SELECT id, display_name, price
FROM products
WHERE product_state = ? AND price >= ?
ORDER BY price DESC, id ASC;
~~~

- **SELECT, FROM, WHERE, AND, ORDER BY, DESC, ASC** are syntax.
- **products** is a table name; **id, display_name, price, product_state** are column names, i.e., SQL identifiers.
- **=, >=** are operators.
- The two **?** symbols are where **values** are bound: product state and minimum price.

In Java:

~~~java
List<Product> rows = jdbcTemplate.query(
    """
    SELECT id, display_name, product_state, price
    FROM products
    WHERE product_state = ? AND price >= ?
    ORDER BY price DESC, id ASC
    """,
    PRODUCT_ROW_MAPPER,
    "ACTIVE",
    new java.math.BigDecimal("50.00")
);
~~~

This is an illustrative snippet inside a repository that already has `JdbcTemplate`, `RowMapper`, and the `Product` type; it is not a standalone runnable program. Spring/the driver binds `"ACTIVE"` and `50.00` in order. It does not alter the `products` table, `price` column, or `DESC` keyword.

~~~text
                 Fixed SQL of the program
            SELECT ... FROM products
               WHERE price >= ?
                        |
                        v
               Value parameter
                BigDecimal("50")
                        |
                        v
              PreparedStatement
                        |
                Database parser
            already knows SQL structure
~~~

A marker is not a macro, not raw text insertion, and not a function that constructs new SQL statements.

## 2. Decision Table: Which Components Can Be Bound?

| Component to vary | Use `?` or `:param`? | Proper approach |
| --- | --- | --- |
| `WHERE id = ?` | Yes | Bind numeric/UUID ID |
| `WHERE state = :state` | Yes | Bind state string |
| `INSERT ... VALUES (?, ?)` | Yes | Bind data being written |
| `UPDATE ... SET price = ?` | Yes | Bind new price |
| `HAVING COUNT(*) >= ?` | Yes | Bind threshold |
| `LIKE :pattern` | Yes | Bind the entire pattern |
| `LIMIT ?` / `OFFSET ?` | Yes if dialect/driver supports | Bind range-checked numbers |
| `FROM ?` | **No** | Use fixed table or allow-list |
| `SELECT ?` intending to pick column name | **No** | Choose fixed projection or allow-list |
| `ORDER BY :column` | **No** if intending to change column name | Map sort key to identifier |
| `ORDER BY price :direction` | **No** | Choose `ASC`/`DESC` from enum |
| `WHERE price :operator :threshold` | **No** for the operator | Choose allowed operator, bind threshold |
| `WHERE :rawClause` | **No** | Build predicates in code |
| `JOIN`, `GROUP BY`, `UNION`, `DISTINCT` | **No** | Use controlled SQL/DSL |
| `IN (:ids)` with collection | Yes via Spring list expansion | Bind each expanded element |
| Schema name, alias, index, or database | **No** | Choose from configuration/allow-list |
| Entire `SELECT` statement in one bind value | **No** | Write separate real SQL |

Important note: some DBMSs allow markers in `ORDER BY` as **value expressions**, but that does not turn a string like `"price"` into the `price` column name. Specifically, never use `ORDER BY ?` to select a column based on input.

## 3. Why Are `FROM ?` and `SELECT ?` Not Table/Column Names?

Wrong example:

~~~sql
SELECT id, display_name
FROM ?
WHERE id = ?;
~~~

The author may intend to bind the first parameter to `"products"`. However, `FROM` requires a **table reference in SQL grammar**. Parameters in a prepared statement do not rewrite tokens of that kind. When the database/driver parses the statement, it cannot arbitrarily interpret a string value as a new identifier.

Subtler example:

~~~sql
SELECT ? FROM products WHERE id = ?;
~~~

If the first parameter is the string `"display_name"`, on a DBMS that permits this syntax, the SQL query may return the **constant string `"display_name"`** on every row rather than reading the `display_name` column.

~~~sql
-- Read product name:
SELECT display_name FROM products WHERE id = ?;

-- Not equivalent: the first parameter is a VALUE.
SELECT ? FROM products WHERE id = ?;
~~~

Similarly, `WHERE ? = ?` compares two values; it does not substitute column names. Even when SQL is syntactically valid, the result can still be wrong.

### 3.1. JDBC PreparedStatement Operates at the Code/Data Boundary

The two logical steps are:

1. The driver receives an **SQL template with valid parameter markers**.
2. The program passes **typed values** into those marker positions before execution.

Drivers and DBMSs may use various prepare, parse, cache, or protocol mechanisms; not every `PreparedStatement` is created as a long-lived server-side prepared statement. Regardless of implementation, **bound values are not treated as new SQL structure**.

This is the basis for parameterization's safety against SQL injection: quotes, semicolons, or SQL-like fragments inside **values** remain data.

## 4. JdbcTemplate: Positional `?` Markers

In Spring JDBC, `JdbcTemplate` provides query/update APIs using `PreparedStatement` and manages JDBC resources per Spring's lifecycle.

~~~java
List<Product> findActiveByPrice(
        java.math.BigDecimal minimumPrice) {

    String sql = """
        SELECT id, display_name, product_state, price
        FROM products
        WHERE product_state = ? AND price >= ?
        ORDER BY price DESC, id ASC
        """;

    return jdbcTemplate.query(
        sql, PRODUCT_ROW_MAPPER, "ACTIVE", minimumPrice
    );
}
~~~

Binding order is left to right. The first `?` corresponds to `product_state`; the second `?` corresponds to `price`. Spring does not match Java variable names to column names for positional parameters.

~~~java
// INSERT: substitute data, do not change table/column names.
int inserted = jdbcTemplate.update(
    "INSERT INTO products (id, display_name, product_state, price) " +
    "VALUES (?, ?, ?, ?)",
    id, displayName, state, price
);

// UPDATE: price and id are fixed identifiers; values are bound.
int updated = jdbcTemplate.update(
    "UPDATE products SET price = ? WHERE id = ?",
    newPrice, id
);

// DELETE: only id is the changing value.
int deleted = jdbcTemplate.update(
    "DELETE FROM products WHERE id = ?",
    id
);
~~~

The snippets above are repository parts where variables/objects are already declared. The return value of `update(...)` is the affected row count per driver/DBMS; check it when the contract requires exactly one row.

### 4.1. Plain PreparedStatement: Parameter Positions Start at 1

~~~java
String sql = """
    SELECT id, display_name
    FROM products
    WHERE product_state = ? AND price >= ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setString(1, "ACTIVE");
    ps.setBigDecimal(2, new java.math.BigDecimal("50.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

This is a Java JDBC snippet in an application that already has a `DataSource`; **parameter indices start at 1**. Close `Connection`, `Statement`, and `ResultSet` properly per their lifecycle. If Spring already manages transactions, use `JdbcTemplate` or `DataSourceUtils` rather than manually closing a transaction-managed connection.

### 4.2. An SQL-Shaped Payload Is Still Bound as Data

Suppose the input is:

~~~text
ACTIVE' OR 1=1 --
~~~

Using parameter binding:

~~~java
List<Long> ids = jdbcTemplate.query(
    "SELECT id FROM products WHERE product_state = ?",
    (rs, rowNum) -> rs.getLong("id"),
    input
);
~~~

The entire input string is **one value** compared against `product_state`. The `OR 1=1` and `--` parts do not become SQL operators or comments. If no product has a state equal to that exact entire payload, the result is an empty list.

Conversely:

~~~java
// WRONG: raw input participates in the parsed SQL structure.
String sql = "SELECT id FROM products WHERE product_state = '" +
             input + "'";
~~~

This pattern carries SQL injection risk. Do not manually add quotes or escape strings in place of parameter binding.

## 5. NamedParameterJdbcTemplate: `:name` Is Still a Value Parameter

`NamedParameterJdbcTemplate` replaces numbered markers with named parameters. Example:

~~~java
String sql = """
    SELECT id, display_name, product_state, price
    FROM products
    WHERE product_state = :state AND price >= :minimum
    ORDER BY price DESC
    """;

MapSqlParameterSource args = new MapSqlParameterSource()
    .addValue("state", "ACTIVE")
    .addValue("minimum", new java.math.BigDecimal("50.00"));

List<Product> result = namedJdbc.query(
    sql, args, PRODUCT_ROW_MAPPER
);
~~~

You must import `org.springframework.jdbc.core.namedparam.MapSqlParameterSource` and define `namedJdbc`/`PRODUCT_ROW_MAPPER` in the repository. The names `state`/`minimum` here only accept **values**. Spring parses and translates named parameters into corresponding JDBC markers.

Wrong example:

~~~sql
SELECT id
FROM :table
WHERE :column = :value
ORDER BY :sortColumn :direction;
~~~

Passing a Map with `table="products"`, `column="price"`, `direction="DESC"` does not produce valid SQL as intended. Those positions require identifiers/keywords, not values. Some expression positions might still parse validly yet mean the wrong thing, which must be avoided even more carefully.

### 5.1. Same Named Parameter Appearing Multiple Times

~~~sql
SELECT id, display_name
FROM products
WHERE display_name = :name OR :name = 'ALL';
~~~

If binding `name="Mouse"`, both positions are bound with the **value** `"Mouse"`. Repeating the variable name does not change the `OR` operator or the `display_name` column.

### 5.2. JdbcClient Since Spring Framework 6.1

`JdbcClient` provides a fluent API for JDBC with named/positional parameters:

~~~java
List<Product> products = jdbcClient
    .sql("""
         SELECT id, display_name, product_state, price
         FROM products WHERE product_state = :state
         ORDER BY id
         """)
    .param("state", "ACTIVE")
    .query(PRODUCT_ROW_MAPPER)
    .list();
~~~

This is a snippet assuming `JdbcClient`/`RowMapper` exist in the repository class. The `param(...)` method still binds **values**; it does not turn table or column names into new SQL. Check your Spring version and overloads when applying it.

## 6. Dynamic ORDER BY: Allow-Listing Column Names and Sort Direction

Many UIs need options like `sort=name`, `sort=price`, or `direction=desc`. Mistake:

~~~java
// DANGEROUS: userSort / userDirection from request are concatenated directly.
String sql = "SELECT id, display_name FROM products " +
             "ORDER BY " + userSort + " " + direction;
~~~

Even if other `WHERE` values are bound, the `ORDER BY` structure still comes from untrusted input, risking injection, selecting disallowed columns, or executing overly expensive expressions.

### 6.1. Only Select Program-Defined SQL Tokens

~~~java
enum SortKey {
    NAME("display_name"),
    PRICE("price"),
    ID("id");

    private final String column;

    SortKey(String column) {
        this.column = column;
    }

    String sqlColumn() {
        return column;
    }
}

enum SortDirection {
    ASC, DESC;

    String sqlToken() {
        return name();
    }
}
~~~

Then use the enums:

~~~java
List<Product> findSorted(
        String state, SortKey key, SortDirection direction) {

    String sql =
        "SELECT id, display_name, product_state, price " +
        "FROM products WHERE product_state = ? ORDER BY " +
        key.sqlColumn() + " " + direction.sqlToken() +
        ", id ASC";

    return jdbcTemplate.query(
        sql, PRODUCT_ROW_MAPPER, state
    );
}
~~~

Only tokens predefined inside `SortKey`/`SortDirection` enter the **SQL structure**. The `state` value is **still bound via `?`**. `id ASC` acts as a tie-breaker to avoid ambiguous ordering when prices or names are identical.

If the initial input is an HTTP string, **convert it to an enum via an allow-list**:

~~~java
static SortKey parseSort(String input) {
    return switch (input) {
        case "name" -> SortKey.NAME;
        case "price" -> SortKey.PRICE;
        case "id" -> SortKey.ID;
        default -> throw new IllegalArgumentException(
            "Unsupported sort field"
        );
    };
}

static SortDirection parseDirection(String input) {
    return switch (input) {
        case "asc" -> SortDirection.ASC;
        case "desc" -> SortDirection.DESC;
        default -> throw new IllegalArgumentException(
            "Unsupported sort direction"
        );
    };
}
~~~

Java 17 code; null input must be handled explicitly at the controller/service boundary if possible. Do not merely check that a string matches an identifier regex and allow it: a syntactically valid column might still be sensitive or not exposed by the API.

### 6.2. `ORDER BY ?` Does Not Change Column Names

~~~sql
SELECT id, display_name, price
FROM products
ORDER BY ?;
~~~

Binding the string `"price"` is not equivalent to `ORDER BY price`. The DBMS may treat it as a constant expression or throw an error depending on type and dialect. `ORDER BY price ?` with `"DESC"` bound also does not swap the `DESC` keyword.

Similarly:

~~~sql
SELECT id FROM products WHERE price ? ?;
~~~

You cannot bind the `>=` operator into the first marker position. `?` represents a **value operand**, not an operator token or SQL structure.

## 7. Dynamic Table Names and SELECT Columns: Fix Structure or Allow-List

Table names belong to structure:

~~~sql
-- WRONG when intending tableName to be a table name:
SELECT COUNT(*) FROM ?;
~~~

Uncontrolled input concatenation is also wrong:

~~~java
// WRONG: requestTable may contain unauthorized data.
String sql = "SELECT COUNT(*) FROM " + requestTable;
~~~

If an internal API needs to pick among a few known reports, map the report code to an **application-owned table name**:

~~~java
static String allowedReportTable(String reportType) {
    return switch (reportType) {
        case "products" -> "products";
        case "inventory" -> "inventory_snapshot";
        default -> throw new IllegalArgumentException(
            "Unsupported report type"
        );
    };
}

String sql = "SELECT COUNT(*) FROM " +
             allowedReportTable(reportType);
~~~

This is only an illustrative design; `inventory_snapshot` must exist and the DB account needs proper `SELECT` privileges. An even easier-to-audit option is writing **two separate fixed queries** for each report type.

### 7.1. Dynamic Projection Is Not a Value

If the UI sends a `fields` list containing `name` and `price`, do not `String.join` that data directly into `SELECT` fields. Map each **field key** to an allowed column, reject any other field, and ensure users cannot accidentally read sensitive columns.

SQL:

~~~sql
SELECT ? FROM products WHERE id = ?;
~~~

cannot accept `"display_name"` as a column name. If the DBMS allows it, it selects the constant value `"display_name"` on every row.

### 7.2. UPDATE Dynamic Columns

Do not do this:

~~~java
// WRONG: fieldName is raw user input.
String sql = "UPDATE products SET " + fieldName +
             " = ? WHERE id = ?";
~~~

Prefer specific business methods:

~~~java
int changePrice(long id, BigDecimal price) {
    return jdbc.update(
        "UPDATE products SET price = ? WHERE id = ?",
        price, id
    );
}
~~~

If choosing among a few columns is genuinely required, map the field key to a fixed column token and **still bind the new value**. Never let users pick arbitrary columns, especially password, owner, or tenant ID columns.

### 7.3. Schemas, Aliases, Indexes, and Multi-Tenancy

Schema names, table aliases, and index names also belong to SQL structure. Do not use `:schema.tableName` to bind a schema name. For multi-tenancy, consider binding `tenant_id` in `WHERE` or server-managed tenant → schema/DataSource mapping. Never let a raw tenant/schema name from a request become an SQL identifier.

### 7.4. Identifier Quoting Does Not Replace an Allow-List

PostgreSQL uses double quotes for certain special identifiers; other DBMSs have different quoting conventions. Quoting protects the **syntax** of an already chosen name, not whether the caller is authorized to pick that table/column. Choose identifiers from an allow-list first; if needed, quote per dialect (do not assume one syntax works across all DBMSs). DB privileges and authorization logic are separate layers of defense.

## 8. Operators, WHERE, JOIN, and Keywords: Structure Must Be Chosen

If an API allows `gt`, `gte`, `lt`, `lte` comparisons, do not bind the operator:

~~~sql
-- INVALID as a way to substitute an operator:
SELECT id FROM products WHERE price :operator :price;
~~~

Instead:

~~~java
static String allowedOperator(String key) {
    return switch (key) {
        case "gt" -> ">";
        case "gte" -> ">=";
        case "lt" -> "<";
        case "lte" -> "<=";
        default -> throw new IllegalArgumentException(
            "Unsupported operator"
        );
    };
}

String sql = "SELECT id FROM products WHERE price " +
             allowedOperator(operatorKey) + " ?";

List<Long> ids = jdbc.query(
    sql,
    (rs, index) -> rs.getLong("id"),
    threshold
);
~~~

The operator is owned by code; the threshold is a bound value.

Nor can you bind a literal clause:

~~~sql
SELECT id FROM products WHERE :whereClause;
~~~

Strings like `price > 0 AND product_state = 'ACTIVE'` are **SQL code**, not a value. If an API needs multiple filters, assemble predefined predicates.

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT id, display_name, product_state, price " +
    "FROM products WHERE tenant_id = :tenantId"
);

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", tenantId);

if (state != null) {
    sql.append(" AND product_state = :state");
    params.addValue("state", state);
}

if (minimumPrice != null) {
    sql.append(" AND price >= :minimumPrice");
    params.addValue("minimumPrice", minimumPrice);
}

List<Product> found = namedJdbc.query(
    sql.toString(), params, PRODUCT_ROW_MAPPER
);
~~~

This is a repository pattern assuming a `tenant_id` column and matching variables; it is not a standalone program. Every appended **SQL fragment** is predefined in code. Keeping the tenant filter fixed in every branch prevents a dynamic filter from accidentally widening data access to another tenant.

When clauses grow very complex, you can use a suitable DSL/query builder while still separating APIs for identifiers from APIs for values. Using raw SQL strings inside a builder can still be unsafe if their content comes from users.

## 9. `IN (:ids)`: Spring Can Expand a LIST OF VALUES

Standard SQL in simple form:

~~~sql
SELECT id FROM products WHERE id IN (?, ?, ?);
~~~

Each `?` is **one value**, not CSV text. `NamedParameterJdbcTemplate` supports collection expansion:

~~~java
List<Long> ids = List.of(1L, 3L, 5L);

List<Long> found = namedJdbc.query(
    "SELECT id FROM products WHERE id IN (:ids) ORDER BY id",
    java.util.Map.of("ids", ids),
    (rs, index) -> rs.getLong("id")
);
~~~

Spring expands `:ids` into the matching number of placeholders and binds each element. It **does not** turn table names or syntax into parameters. Never `String.join` user IDs and concatenate them into SQL instead of using this mechanism.

### 9.1. Empty Lists

SQL `IN ()` is not accepted by every DBMS. Do not assume you can pass an empty `List` to `IN (:ids)` and cleanly get an empty result. If business rules state "no IDs selected" means no results, return an empty List early:

~~~java
List<Long> findIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return namedJdbc.query(
        "SELECT id FROM products " +
        "WHERE id IN (:ids) ORDER BY id",
        java.util.Map.of("ids", ids),
        (rs, index) -> rs.getLong("id")
    );
}
~~~

Some APIs treat an empty collection as "do not apply filter"; state that contract explicitly to avoid accidentally dropping `WHERE` and returning the whole table.

### 9.2. Large IN-Lists

Overly long lists can exceed the DBMS's marker/IN-element limit or inflate parse/plan cost. Depending on the database, you may need batching, temporary tables, array binding, `JOIN`, or table-valued parameters. Never concatenate untrusted CSV into SQL to "bypass limits."

## 10. `LIKE`: Binding Patterns While Wildcards Still Have Meaning

~~~sql
SELECT id FROM products WHERE display_name LIKE ?;
~~~

`?` receives a **pattern value** such as `"Mou%"`. Binding prevents that string from becoming SQL code, yet `%` and `_` remain wildcards interpreted by the `LIKE` operator per SQL semantics.

If you want to search for literal strings containing `%` or `_`, escape wildcards according to your dialect:

~~~java
static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

String pattern = escapeLikeLiteral(userText) + "%";

List<Long> ids = jdbc.query(
    """
    SELECT id FROM products
    WHERE display_name LIKE ? ESCAPE '!'
    ORDER BY id
    """,
    (rs, index) -> rs.getLong("id"),
    pattern
);
~~~

The snippet uses `!` as the escape character and appends `%` intentionally for prefix matching. Verify the `ESCAPE` syntax and collation of your target DBMS. `userText` is bound; it is never concatenated directly into the SQL statement.

Distinguish:
- Binding protects the **code vs. data** boundary.
- Escaping LIKE controls **wildcard search semantics**.
- Indexes, collation, and full-text search affect **performance and search results**; binding does not optimize queries by itself.

## 11. NULL, SQL Types, and Numeric Limits

In SQL, comparisons with NULL follow **three-valued logic**. For example:

~~~sql
-- CORRECT when checking for null:
SELECT id FROM products WHERE deleted_at IS NULL;

-- NOT EQUIVALENT: binding NULL to ? does not make = TRUE:
SELECT id FROM products WHERE deleted_at = ?;
~~~

`deleted_at = NULL` normally evaluates to UNKNOWN, not TRUE. If a filter "show only non-deleted records" requires `IS NULL`, that is a **fixed SQL structure** the application must select. When comparing against a specific point in time, use `deleted_at = :value` and bind a non-null timestamp.

### 11.1. Null Parameters Sometimes Need Explicit Types

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("nickname", null, java.sql.Types.VARCHAR)
    .addValue("userId", 42L, java.sql.Types.BIGINT);
~~~

In plain JDBC, you can use `PreparedStatement.setNull(index, java.sql.Types.VARCHAR)`. Drivers/DBMSs differ in inferring types for NULL, UUID, JSON, ARRAY, and timestamps. Bind the right type, occasionally needing dialect casts. Binding the right type does not mean SQL syntax or type names can become parameters.

### 11.2. LIMIT/OFFSET Are Usually Values, Yet Need Validation

PostgreSQL/H2 support:

~~~sql
SELECT id, display_name
FROM products
ORDER BY id
LIMIT ? OFFSET ?;
~~~

The `?` markers are limit and offset **numbers**, not replacements for the `LIMIT`/`OFFSET` keywords. Another DBMS may use `FETCH FIRST`, `TOP`, or `OFFSET ... FETCH`; pick syntax per dialect. Even though binding is injection-safe, huge page sizes or large offsets can still consume heavy resources; bound the range and test performance.

### 11.3. Money, Dates/Times, and Timezones

Prefer `BigDecimal` for money and proper date/time types for timestamps rather than manually concatenating SQL literals. Use JDBC/driver type mappings. When handling `timestamptz`/`timestamp`, know whether the DB stores an instant or local wall-clock time; parameter binding does not resolve timezone mismatches or date comparison policies.

## 12. Controlled Dynamic SQL: Three Priority Levels

1. **Static SQL** with binding: simple, easy to read, easy to review.
2. **A few static queries selected via code branches**: suitable when there are two or three report variants.
3. **SQL assembled from fixed allow-listed fragments/identifiers**: used for multiple filters or sort options, requiring testing of each combination.

~~~text
Input from client
   |
   +--- Values: id, state, minPrice, searchText
   |         |
   |      Validate range/type
   |         |
   |      Bind via ? or :param
   |
   +--- Structure selection: sort, direction, report type
             |
          Allow-list from code
             |
         Fixed identifier/keyword/SQL branch

Trusted SQL structure + bound values -> JDBC -> Database
~~~

Do not treat column-name regexes or quote escaping as sufficient substitutes for mapping structural choices. A syntactically valid column name can still be sensitive or trigger expensive queries. Conversely, a character-validated string should still be bound as a **value**, never concatenated directly.

## 13. Security Benefits and Limits of PreparedStatement

**Safe value binding does not mean the entire SQL statement is safe.**

~~~java
// DANGEROUS: WHERE uses binding, ORDER BY concatenates raw user input.
String sql =
    "SELECT id FROM products WHERE product_state = ? " +
    "ORDER BY " + userSort;

List<Long> ids = jdbc.query(
    sql,
    (rs, index) -> rs.getLong("id"),
    state
);
~~~

`state` is properly bound, yet `userSort` (`sortFromRequest`) can still inject out-of-scope SQL fragments/identifiers if concatenated directly.

Defensive principles:

- Parameterize **every data value**: IDs, names, states, prices, dates/times.
- Allow-list **identifiers, operators, directions, report selections** and forbid raw SQL fragments from users.
- Keep tenant/access-control predicates in every SQL branch.
- Grant **least privilege** to the DB account: no DDL or access to out-of-scope tables unless needed.
- Bound `pageSize`, `LIKE` patterns, `IN`-list sizes, and query complexity.
- Never write secrets or sensitive data to raw logs.
- Do not assume stored procedures are automatically safe: dynamic SQL built by string concatenation inside a procedure can still suffer injection.
- Do not use manual escaping instead of parameter binding; escaping syntax can vary by dialect/configuration.

Safety comes from ensuring that **anything client-variable is treated as data**, or if it is a structural choice, mapped to **a finite, trusted set of tokens** before the SQL statement is constructed.

## 14. Java 17+ Demo: Practical Verification

The demo uses **Spring JDBC 6.2.7**, **H2 2.3.232**, **Java 17+**, and Gradle. The program creates a `products` table in in-memory H2 and demonstrates:

- Product names bound as values.
- An SQL-injection-like payload **does not** alter `WHERE` logic.
- `ORDER BY` uses tokens from an allowed enum, rejecting raw SQL.
- `IN (:ids)` is expanded by Spring from a collection.
- An empty `IN` list is handled in Java.
- `UPDATE` binds the new price and ID.

Structure:

~~~text
sql-value-vs-identifier/
  build.gradle
  src/main/java/demo/SqlParameterBoundaryDemo.java
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.7'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.SqlParameterBoundaryDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

File **src/main/java/demo/SqlParameterBoundaryDemo.java**:

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class SqlParameterBoundaryDemo {

    record Product(
        long id, String name, String state, BigDecimal price) {}

    enum SortKey {
        NAME("display_name"),
        PRICE("price");

        private final String column;

        SortKey(String column) {
            this.column = column;
        }

        String sqlColumn() {
            return column;
        }
    }

    enum SortDirection {
        ASC, DESC;

        String sqlToken() {
            return name();
        }
    }

    static final class ProductRepository {
        private static final RowMapper<Product> MAPPER =
            (rs, rowNum) -> new Product(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("product_state"),
                rs.getBigDecimal("price")
            );

        private final JdbcTemplate jdbc;
        private final NamedParameterJdbcTemplate named;

        ProductRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
            this.named = new NamedParameterJdbcTemplate(jdbc);
        }

        int countByName(String name) {
            Integer count = named.queryForObject(
                "SELECT COUNT(*) FROM products " +
                "WHERE display_name = :name",
                Map.of("name", name),
                Integer.class
            );
            return Objects.requireNonNull(count);
        }

        List<Product> findByState(
                String state,
                SortKey sort,
                SortDirection direction) {

            // Only concatenate structural tokens owned by the enum.
            String sql =
                "SELECT id, display_name, product_state, price " +
                "FROM products WHERE product_state = ? ORDER BY " +
                sort.sqlColumn() + " " + direction.sqlToken() +
                ", id ASC";

            // state is still a value bound via ?.
            return jdbc.query(sql, MAPPER, state);
        }

        List<Long> findIds(List<Long> ids) {
            if (ids.isEmpty()) {
                return List.of();
            }
            return named.query(
                "SELECT id FROM products " +
                "WHERE id IN (:ids) ORDER BY id",
                Map.of("ids", ids),
                (rs, rowNum) -> rs.getLong("id")
            );
        }

        int updatePrice(long id, BigDecimal price) {
            return jdbc.update(
                "UPDATE products SET price = ? WHERE id = ?",
                price, id
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:param_demo;DB_CLOSE_DELAY=-1",
            "sa",
            ""
        );
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute(
            """
            CREATE TABLE products (
                id BIGINT PRIMARY KEY,
                display_name VARCHAR(100) NOT NULL,
                product_state VARCHAR(20) NOT NULL,
                price DECIMAL(12, 2) NOT NULL
            )
            """
        );

        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            1L, "Keyboard", "ACTIVE", new BigDecimal("100.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            2L, "Mouse", "ACTIVE", new BigDecimal("40.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            3L, "Monitor", "INACTIVE", new BigDecimal("250.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            4L, "Headphones", "ACTIVE", new BigDecimal("80.00")
        );

        ProductRepository repository = new ProductRepository(jdbc);

        System.out.println(
            "safe name matches: " + repository.countByName("Mouse")
        );

        String payload = "Mouse' OR 1=1 --";
        System.out.println(
            "payload matches: " + repository.countByName(payload)
        );

        List<String> sortedNames = repository.findByState(
                "ACTIVE", SortKey.PRICE, SortDirection.DESC
            ).stream()
            .map(Product::name)
            .toList();
        System.out.println(
            "active by price DESC: " + sortedNames
        );

        System.out.println(
            "ids 1 and 3: " + repository.findIds(List.of(1L, 3L))
        );
        System.out.println(
            "empty id list: " + repository.findIds(List.of())
        );
        System.out.println(
            "updated rows: " +
            repository.updatePrice(2L, new BigDecimal("42.50"))
        );
    }
}
~~~

Run with Gradle installed:

~~~bash
gradle run
~~~

If the project has Gradle Wrapper:

~~~bash
./gradlew run
~~~

On Windows PowerShell with Wrapper:

~~~powershell
.\gradlew.bat run
~~~

The program uses Java 17 `record`, text blocks, and `Stream.toList()`; Spring JDBC and H2 libraries are managed by Gradle. Do not invoke `javac` alone without supplying these dependencies on the classpath.

**Stdout printed by the program** (excluding Gradle build/logs):

~~~text
safe name matches: 1
payload matches: 0
active by price DESC: [Keyboard, Headphones, Mouse]
ids 1 and 3: [1, 3]
empty id list: []
updated rows: 1
~~~

Explanation:

1. The name `Mouse` matches exactly one product.
2. The value containing quotes and `OR 1=1` is bound to `:name` as **a single string**, so it matches no rows and creates no `OR` condition.
3. `ORDER BY price DESC, id ASC` is assembled from **code-defined** enums; prices 100, 80, 40 correspond to Keyboard, Headphones, Mouse.
4. Spring expands the two ID values and returns `[1, 3]`.
5. The empty list returns early without generating `IN ()`.
6. `UPDATE` only affects product ID 2, so affected rows is 1.

The demo uses `DriverManagerDataSource` for learning simplicity, not a production connection pool. Real applications typically use HikariCP, schema migrations, transactions, and dedicated tenant/authorization controls.

## 15. Testing the Value/Structure Boundary Properly

| Test | Input | Expectation |
| --- | --- | --- |
| Valid name | `Mouse` | One matching row |
| String with single quote | Name containing `'` | Does not break SQL; compared as data |
| SQL-injection-like string | `Mouse' OR 1=1 --` | Does not widen `WHERE` |
| Valid sort | `price` / `desc` | `ORDER BY price DESC` |
| Unknown sort field | `secret_column` | Rejected before building SQL |
| Sort with strange syntax | `price; DROP ...` | Rejected, not concatenated raw |
| Unknown direction | `desc, nulls first; ...` | Only valid `ASC`/`DESC` tokens |
| Valid report table | `products` | Selects allowed fixed table |
| Unknown report table | `users_private` | Rejected |
| `IN` with 2 IDs | `[1,3]` | Both values bound |
| Empty `IN` | `[]` | Empty result per contract |
| `LIKE` with literal `%` | `100%` | Wildcard escaped if searching literal |
| SQL NULL | `deleted_at` null | Intentional `IS NULL` branch |
| Huge page size | `1.000.000` | Blocked/bounded |
| Tenant filter | tenant from auth context | Always preserved in query |

Do not test only "the query does not throw an exception": `ORDER BY ?` sometimes still runs yet **sorts wrongly**. Check output ordering across multiple rows; also test disallowed inputs, SQL NULL, empty lists, and DB errors.

Use integration tests on a real DBMS or Testcontainers when code relies on PostgreSQL/MySQL/Oracle-specific syntax; H2 does not accurately emulate every type, quoting rule, JSON, array, or query planner.

## 16. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| `FROM ?` accepts a table name | Markers do not replace table identifiers |
| `SELECT ?` accepts a column name | It is a value, not a column projection |
| `ORDER BY ?` accepts a column name | Does not turn `"price"` string into an identifier |
| `ORDER BY price ?` accepts `DESC` | `DESC` is an SQL keyword |
| `WHERE price ? ?` accepts operator and value | Operators cannot be bound like data |
| Using `PreparedStatement` alone makes the whole SQL safe | SQL structure concatenated from raw user input can still be injected |
| Column-name regex is safe enough | You must allow-list columns permitted for that specific query |
| Manual escaping equals binding | Dialect-dependent and error-prone, does not replace binding |
| `IN (:ids)` concatenates a CSV string | Spring expands the collection into value markers |
| Empty `IN` always runs | Can produce invalid SQL; must define behavior |
| Binding null to `= ?` finds SQL NULL | Comparing `= NULL` is not TRUE |
| `LIKE` parameter cannot match unexpectedly | `%` and `_` wildcards remain active |
| Safely bound `LIMIT` means any page size is fine | Values must be bounded to avoid heavy queries |
| Identifier quoting replaces access control | Quoting handles syntax, not authorization |

## 17. Self-Check Questions

**Question 1.** Why can't `SELECT ... FROM ?` use the parameter `"products"` as a table name?

**Answer:** `FROM` needs a table identifier in SQL structure; markers represent values and do not re-parse strings into table names.

**Question 2.** Is binding `"price"` into `ORDER BY ?` equivalent to `ORDER BY price`?

**Answer:** No. That is a value/expression, not an automatically substituted identifier. Use an allow-list to choose column names.

**Question 3.** You receive `direction=desc` from the UI; how do you safely produce `ORDER BY price DESC`?

**Answer:** Convert the input to an enum or allow-list; append the program-owned `DESC` literal to the SQL. `WHERE` values are still bound separately.

**Question 4.** A repository uses `WHERE state = ?` but concatenates `sortFromRequest` into `ORDER BY`. Has SQL injection been eliminated?

**Answer:** Not yet. Only `state` is protected; concatenating raw input into `ORDER BY` remains a risk.

**Question 5.** In `LIKE ?`, the user searches for a literal `%` character. Does parameter binding automatically escape wildcards?

**Answer:** No. Binding prevents injection, yet `%` remains a `LIKE` wildcard. Escape wildcards per dialect when searching literally.

**Question 6.** To query `id IN (1,3,5)` with a varying number of IDs, should you manually concatenate CSV into SQL?

**Answer:** No. Use collection expansion via `NamedParameterJdbcTemplate`/`JdbcClient` or generate controlled markers and bind each ID.

**Question 7.** Does binding NULL to `WHERE deleted_at = ?` find all rows with `deleted_at IS NULL`?

**Answer:** Not in standard SQL. Use `IS NULL` or a predicate designed for NULL semantics.

**Question 8.** An API picks between two report tables `products`/`inventory`. Can you use a bind parameter for the table name?

**Answer:** No. Select a static query or allow-list report code → program-owned table name.

**Question 9.** Why does a regex allowing only letters in column names still fail to guarantee safety?

**Answer:** A syntactically valid name can still point to a sensitive column or one not exposed by the API. Business allow-lists and authorization checks are needed.

**Question 10.** Does `SELECT ? FROM products` with bound string `"display_name"` read the `display_name` column?

**Answer:** No. If the DB allows this query, it treats the parameter as a value, not a column identifier.

## 18. Checklist When Implementing a Spring JDBC Repository

1. Classify every input as either a **value** or a **structural SQL choice**.
2. Bind all values via `?`/`:name`, with right types and order.
3. Never concatenate raw user input into `SELECT`/`FROM`/`WHERE`/`ORDER BY`/`JOIN` or DDL.
4. Use allow-lists/enums for column names, tables, operators, and sort directions.
5. Ensure every branch preserves mandatory tenant/authorization predicates.
6. Handle empty/large `IN`-lists, `LIKE` wildcards, `NULL`, and paging limits explicitly.
7. Do not treat identifier quoting, regexes, or manual escaping as substitutes for allow-lists/binding.
8. Set least-privilege DB permissions; avoid DDL and unnecessary data access.
9. Test actual sort order, returned data, strange payloads, and the real dialect.
10. Prefer easy-to-review static SQL; build dynamic structure only when business needs truly require it.

**Conclusion:** Parameter binding substitutes **typed values** within an SQL statement that already has structure. It does not automatically substitute table names, column names, or syntax. When structure must vary, **the application must pick from a finite set of allowed SQL tokens**, then continue binding all remaining values.

### Official References

- Spring Framework, JDBC Core Classes / NamedParameterJdbcTemplate / JdbcClient: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework, NamedParameterJdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Java SE 17, PreparedStatement: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- OWASP, SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet
- PostgreSQL, PREPARE: https://www.postgresql.org/docs/current/sql-prepare.html
