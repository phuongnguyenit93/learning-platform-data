# Parameter Binding Errors, SQL Syntax Errors, and Quoted Identifiers

When using Spring Data R2DBC, query errors commonly appear in three related areas that must be diagnosed separately: **parameter binding**, **SQL syntax**, and **quoted identifiers** (delimited table, schema, column, and alias names). A SQL statement that looks valid can still fail because the placeholder does not match the driver, a null parameter is bound with the wrong type, a column name is a reserved keyword, or casing does not match the identifier in the database.

An effective approach is to separate the SQL query from input values, identify the database/driver executing it, inspect markers and data types, and check the dialect's identifier rules. Do not fix these errors by concatenating user input strings into SQL. Values must be bound; dynamic table/column names must be chosen from an allowlist and quoted according to the database.

## 1. Three Error Categories to Distinguish

| Category | Common Symptoms | Possible Causes |
|---|---|---|
| Parameter binding | Missing parameter, index out of range, type conversion error | Wrong marker, wrong bind order, missing `bindNull`, or wrong type |
| SQL syntax | Syntax error, unexpected token, missing keyword | Wrong SQL dialect, parentheses, alias, keyword, comma, or clause |
| Identifier quoting | Table/column not found, reserved word error, case mismatch | Unquoted identifier, wrong quote style, schema/case mismatch |

A single error can span multiple categories. For example, a SQL query using an unquoted column name `order` can be interpreted by the parser as a keyword; after fixing the quoting, the statement might still fail if the placeholders use another driver's syntax.

Start from the root exception, SQLState/vendor code, and generated SQL. Do not look only at the final controller message because the service layer may have wrapped the error into a generic exception.

## 2. What Do Bind Parameters Do?

Bind parameters separate SQL structure from data values. The database receives a statement with placeholders, and values are passed separately through the driver.

Example:

~~~sql
SELECT id, full_name
FROM customer
WHERE email = :email
~~~

The email value is bound separately:

~~~java
databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .one();
~~~

Benefits:

- Avoids string concatenation of values into SQL.
- Reduces SQL injection risk for bound data.
- The driver transmits values with appropriate types instead of turning everything into text.
- Separates the SQL template from request data.
- May help the database/driver reuse execution plans depending on implementation.

Bind parameters apply only to **values**, such as email, ID, dates, quantities, or statuses. They cannot replace table names, column names, SQL keywords, or arbitrary SQL fragments.

## 3. Named Parameters in Spring `DatabaseClient`

Spring `DatabaseClient` supports named parameters so code does not depend directly on each driver's native markers. With named parameters, SQL uses the `:name` form; the framework expands and converts it to the marker required by the driver.

Example:

~~~java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, full_name, email
            FROM customer
            WHERE email = :email
            """)
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            row.get("email", String.class)
        ))
        .one();
}
~~~

Here:

- `:email` is the named marker in the SQL template.
- `bind("email", email)` supplies the corresponding value.
- `DatabaseClient` converts the named marker into a marker compatible with the dialect/driver.
- `.one()` expresses a result of at most one row.

The parameter name in SQL and the name passed to `bind` must match. Do not include the colon in the name passed to `bind`.

### 3.1. Avoid Confusing Named Markers with Native Markers

R2DBC drivers can use different marker syntaxes. For example, PostgreSQL usually uses `$1`, `$2`; some drivers use `?` or custom markers.

When using Spring `DatabaseClient`, pick a consistent style: write `:name` named markers and let `DatabaseClient` convert them.

When using R2DBC SPI `Statement` directly, you must use the marker syntax supported by that driver. Do not assume every driver understands `:name`.

PostgreSQL native `Statement` example:

~~~java
connection.createStatement("""
        SELECT id, full_name
        FROM customer
        WHERE email = $1
        """)
    .bind(0, email)
    .execute();
~~~

In this native example, `$1` is PostgreSQL's first placeholder, while `bind(0, email)` uses R2DBC SPI's zero-based index. The two numbering schemes differing is not a bug: SQL placeholders start at 1 in PostgreSQL syntax, whereas the API bind index starts at 0.

Do not write SQL using `$1` and call `DatabaseClient.bind("email", ...)` as if the two mechanisms automatically combine, unless the specific API/driver is confirmed to support it properly.

### 3.2. Checking Parameter Count and Names

Common mistakes:

- SQL has `:customerId`, but code binds `"id"`.
- SQL has two placeholders, but only one value is bound.
- SQL changes in a conditional branch, but the bind list does not change accordingly.
- Parameter name has a typo or mismatched casing.
- Wrong positional index order when building a `Statement` manually.
- Using index 1 for the first parameter in the R2DBC SPI API.

With named parameters, construct the SQL and bindings together in the same structure so the two lists do not drift out of sync. With native `Statement`, document the parameter order next to the SQL and remember that indices start at 0 in the R2DBC SPI bind API.

## 4. Binding Null Correctly

Reactive Streams do not emit null values, and the R2DBC SPI likewise does not allow using `bind(index, null)` or `bind(name, null)` as a way to represent SQL `NULL`. You must call `bindNull` and provide a Java type so the driver knows the type of the null value.

Example with `DatabaseClient`:

~~~java
databaseClient.sql("""
        INSERT INTO customer (email, nickname)
        VALUES (:email, :nickname)
        """)
    .bind("email", email)
    .bindNull("nickname", String.class)
    .fetch()
    .rowsUpdated();
~~~

Example with R2DBC SPI:

~~~java
statement
    .bind(0, email)
    .bindNull(1, String.class);
~~~

The type passed to `bindNull` matters because the database needs to know the matching SQL type. For `UUID`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `BigDecimal`, or database-specific types, choose the Java type supported by the driver for that column.

### 4.1. Distinguishing `null` from Omitting a Parameter

There are three different cases:

1. Parameter has a value: bind that value.
2. Parameter has SQL `NULL`: `bindNull` with the corresponding Java type.
3. Parameter is not in the SQL: do not bind that parameter.

Omitting a parameter is not equivalent to binding SQL `NULL`. If SQL has a placeholder that is not bound, the statement usually fails on execution.

### 4.2. Null in `WHERE` Conditions

The condition:

~~~sql
WHERE nickname = :nickname
~~~

when `nickname` is bound as SQL `NULL` will not return rows with a `NULL` nickname under SQL's three-valued logic. A comparison expression against `NULL` yields `UNKNOWN`, not `TRUE`.

If you want to find rows with a null nickname, write a dedicated condition:

~~~sql
WHERE nickname IS NULL
~~~

If a request allows both behaviors, intentionally build two SQL branches or use a dialect-appropriate predicate. Do not expect `nickname = NULL` to behave like `nickname IS NULL`.

## 5. Binding Data Types That Match the Column

The driver must convert Java values into database types. Some errors occur when an incompatible type is passed:

- Passing a `String` for a `UUID` column when the driver does not support that conversion.
- Passing an `Integer` for a `BIGINT` column.
- Passing a `LocalDateTime` into a column requiring an offset/time zone.
- Passing JSON as a Java object without configuring a codec/converter.
- Passing `null` without declaring a type.
- Using a `BigDecimal` whose precision/scale exceeds column limits.

Use the right Java type and check the driver's mapping. Do not convert every value to `String` just to avoid bind errors; doing so can lose type semantics, affect index usage, or force the database to cast implicitly.

### 5.1. UUID

If the database has a `UUID` column, prefer `java.util.UUID` when supported by the driver:

~~~java
.bind("id", UUID.fromString(idText))
~~~

If binding a `String`, conversion to `UUID` depends on the driver and database. Parse/validate at the application layer and bind a typed `UUID`.

### 5.2. Decimal and Numeric

Use `BigDecimal` for monetary data or numbers requiring decimal precision. Check column precision/scale and business rounding rules.

Do not use `double` to store financial values just because the driver accepts that type. A precision error might not raise a SQL exception yet still produce wrong data.

### 5.3. Date/Time

Choose the Java temporal type matching the column's semantics:

- `LocalDate` for dates without time.
- `LocalTime` for times without date.
- `LocalDateTime` for timestamps without an offset.
- `OffsetDateTime` or `Instant` for absolute points in time when driver/database mapping supports it appropriately.

Cross-check the time zones of the database session, driver, and application. Time zone mismatch bugs do not necessarily appear as bind exceptions.

### 5.4. JSON and Database-Specific Types

`JSON`/`JSONB`, arrays, enums, geometry, and custom types may require codecs, converters, or driver-specific wrappers. Check driver documentation before binding.

If a SQL cast is needed, write the cast explicitly according to dialect:

~~~sql
INSERT INTO event_log (payload)
VALUES (CAST(:payload AS jsonb))
~~~

This example is for PostgreSQL `JSONB`. Do not reuse PostgreSQL's cast syntax across every database.

## 6. Binding Lists and `IN` Conditions

A query looking up multiple IDs often looks like:

~~~sql
SELECT id, full_name
FROM customer
WHERE id IN (:ids)
~~~

With Spring `DatabaseClient`, named parameter expansion can expand a collection into matching markers. However, collection handling depends on the API, dialect, and driver; test it on the application's real database.

If using PostgreSQL arrays, using `ANY` with an array parameter may be an option, though creating and binding arrays depends on the driver:

~~~sql
WHERE id = ANY(:ids)
~~~

Do not assume a Java `List` is always converted into a SQL array. `IN` expansion and array binding are two different mechanisms.

### 6.1. Empty Lists

`IN` with an empty list may produce invalid SQL or be unsupported depending on the expansion mechanism. Handle the empty case before running the query.

Example:

~~~java
public Flux<Customer> findByIds(Collection<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, full_name
            FROM customer
            WHERE id IN (:ids)
            """)
        .bind("ids", ids)
        .map(customerMapper)
        .all();
}
~~~

Ensure the mapper fits your project's actual `DatabaseClient` API. The main point is not sending `IN ()` when the list has no elements.

### 6.2. Limiting List Size

A list of tens of thousands of IDs can create a huge SQL statement, exceed parameter count limits, or increase parse/plan overhead.

Limit input size, batch when necessary, or use a database-appropriate array/table-valued parameter mechanism. Do not let clients send arbitrarily huge collections.

## 7. Binding Errors Due to Parameter Order

When using R2DBC SPI directly, positional binding relies on marker order in SQL.

Example:

~~~java
Statement statement = connection.createStatement("""
    UPDATE customer
    SET full_name = $1, active = $2
    WHERE id = $3
    """);

statement
    .bind(0, fullName)
    .bind(1, active)
    .bind(2, id);
~~~

If bound in the wrong order, the SQL may still execute while updating the wrong column or throwing a type conversion error.

Use meaningful variable names and bind in the documented order. If the SQL is built dynamically, construct the parameter list alongside the SQL instead of maintaining two independent arrays manually.

### 7.1. Do Not Reuse the Same Index for Different Values

Every marker position must be bound to an appropriate value. If a `Statement` has three markers and code binds only two positions, execution will fail. If a position is bound again, the last value may overwrite the previous one depending on the API/driver.

Verify marker count, indices, and types before executing.

## 8. SQL Syntax Depends on the Database Dialect

Spring Data R2DBC does not make SQL completely portable. Specific syntax still depends on the database.

Common differences:

- Identifier quotes: double quotes, backticks, or square brackets.
- Pagination: `LIMIT/OFFSET`, `OFFSET/FETCH`, or custom syntax.
- Upsert: `ON CONFLICT`, `ON DUPLICATE KEY`, or `MERGE`.
- Generated key/returning: `RETURNING` or another mechanism.
- JSON operators and casts.
- Boolean literals.
- Date/time functions.
- Sequences/identity.
- Locking syntax such as `FOR UPDATE`.
- CTEs, window functions, and recursive queries.

A query that runs on PostgreSQL may fail on MySQL or SQL Server even though both are accessed via R2DBC.

### 8.1. Checking the Active Dialect

Spring Data Relational/R2DBC has a dialect abstraction to help generate SQL for specific databases. When using repository derivation or `R2dbcEntityTemplate`, the framework can generate part of the SQL based on the dialect.

When writing native SQL via `@Query` or `DatabaseClient`, the SQL written by the application must still adhere to the database's dialect. Do not assume the dialect will rewrite every manual SQL statement.

When using a custom `ConnectionFactory` or multiple databases, confirm that repositories/templates are wired with the right dialect and `ConnectionFactory`.

### 8.2. Do Not Mix Syntax from Multiple Databases

Examples of pagination syntax:

~~~sql
-- PostgreSQL / MySQL
SELECT id, name
FROM customer
ORDER BY id
LIMIT :size OFFSET :offset
~~~

~~~sql
-- SQL Server (a common form)
SELECT id, name
FROM customer
ORDER BY id
OFFSET :offset ROWS
FETCH NEXT :size ROWS ONLY
~~~

These are dialect-specific examples, not universal syntax. Verify against the specific server version and driver.

## 9. What Is an Identifier and Why Quote It?

An identifier is the name of a SQL object: database, schema, table, column, index, sequence, alias, or function. An identifier is not a data value.

Example:

~~~sql
SELECT customer_id
FROM sales.customer
WHERE customer_id = :id
~~~

Here `sales` is a schema, `customer` is a table, `customer_id` is a column, and `:id` is a value parameter.

Databases have their own rules for identifiers:

- Reserved keywords cannot be used as table/column names without quoting.
- Casing may be normalized differently.
- Names containing spaces or special characters generally require quoting.
- Using the wrong quote style can cause the parser to misinterpret it or look up another object.

### 9.1. Reserved Keywords

Names like `order`, `user`, `group`, `select`, or `key` may be reserved words or special keywords in certain databases/versions.

Example:

~~~sql
SELECT id, status
FROM order
~~~

This can fail because `order` is a keyword in that specific database. The best approach is to choose names that avoid reserved words, such as `orders` or `purchase_order`.

If an existing schema cannot be changed, quote the identifier properly for the database.

### 9.2. Quote Delimiters Differ Between Databases

| Database | Common Identifier Delimiter | Notes |
|---|---|---|
| PostgreSQL | `"name"` | Quoted identifiers preserve casing |
| MySQL | \`name\` | Backtick is conventional; double quotes depend on SQL mode |
| SQL Server | `[name]` or `"name"` | Double quotes depend on `QUOTED_IDENTIFIER` |
| H2 | `"name"` | Behavior close to standard SQL, though mode still needs checking |

Do not copy one database's quote delimiters to another. MySQL commonly uses backticks; PostgreSQL uses double quotes; SQL Server supports square brackets and has specific rules for double quotes.

### 9.3. Quoted Identifiers Can Be Case-Sensitive

PostgreSQL folds unquoted identifiers to lowercase. For example:

~~~sql
SELECT id FROM Customer
~~~

the unquoted identifier `Customer` is normalized to `customer`.

Meanwhile:

~~~sql
SELECT id FROM "Customer"
~~~

requires an object with the exact case-sensitive name `Customer`.

If a table was created with a quoted mixed-case identifier, queries using unquoted lowercase may report relation/table not found. This is an object naming error, not a parameter binding error.

MySQL and SQL Server rules differ from PostgreSQL, especially regarding table name case sensitivity, filesystems, and collations. Always check against the database in use.

## 10. Quoting Identifiers in Spring Data Relational

Spring Data Relational uses table and column metadata to generate SQL for repositories/templates. Mapping annotations and `NamingStrategy` determine which identifiers are used.

Example:

~~~java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Column("order_status") String status
) {}
~~~

Using explicit table/column names avoids relying on implicit naming conventions. If an object name is a reserved word or must preserve case, determine how Spring Data and the dialect render identifiers for the version in use.

Spring Data Relational provides the `SqlIdentifier` abstraction to represent identifiers with quoting metadata. In custom mapping/naming strategies, you can create quoted/unquoted identifiers per your Spring Data version's API. Check the package/API for the exact version; do not assume an annotation string is quoted identically across all databases.

### 10.1. Avoid Naming Objects with Reserved Words

When you control schema design, prefer names that do not need quoting:

- `order` → `purchase_order`
- `user` → `app_user`
- `group` → `customer_group`
- `key` → `external_key`

Simple, consistent `snake_case` names reduce errors when switching dialects, writing migrations, and reading queries.

### 10.2. When Names Must Contain Spaces or Special Characters

If a legacy schema has names like `Order Detail` or names with hyphens, quote them accurately and test against the real database.

Do not concatenate quote characters manually with strings when Spring Data/dialect identifier abstractions are available. Escaping quote characters inside an identifier also differs by database.

## 11. Table or Column Names Cannot Be Bound as Value Parameters

The following does not select a column dynamically:

~~~sql
SELECT id, name
FROM customer
ORDER BY :sortColumn
~~~

`:sortColumn` is a value parameter. The database treats it as a literal value, not a column name. Similarly, bind parameters cannot be used for table names, schema names, column names, `ASC`/`DESC`, operators, arbitrary `WHERE`/`ORDER BY` snippets, function names, or keywords.

### 11.1. Use an Allowlist for Dynamic Identifiers

If an API allows sorting by multiple fields, map input to fixed choices:

~~~java
String orderBy = switch (sortField) {
    case "name" -> "full_name";
    case "createdAt" -> "created_at";
    case "price" -> "price";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};

String direction = descending ? "DESC" : "ASC";

String sql = """
    SELECT id, full_name, created_at, price
    FROM product
    ORDER BY
    """ + orderBy + " " + direction;
~~~

This example only concatenates fragments coming from a fixed, application-controlled allowlist. Do not concatenate raw `sortField` or `direction` from the request directly.

Filter values are still bound separately:

~~~java
databaseClient.sql(sql + " WHERE category = :category")
    .bind("category", category);
~~~

Even better, use an enum or query builder structure instead of passing arbitrary strings across multiple layers.

### 11.2. Quoting Does Not Replace an Allowlist

Quoting a user-supplied identifier is not enough to protect every scenario. Verify that the identifier is in the list of allowed columns/tables first, then quote according to the dialect.

Do not let clients send raw SQL snippets like `sortExpression` or `filterExpression` and concatenate them into queries.

## 12. SQL Injection and String Concatenation

A dangerous mistake is concatenating request values directly into SQL:

~~~java
String sql = "SELECT * FROM customer WHERE email = '"
    + email
    + "'";
~~~

If `email` contains special SQL characters, the statement structure can be altered. Use bind parameters:

~~~java
databaseClient.sql("""
        SELECT *
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

Bind parameters make the database treat `email` as data, not SQL syntax.

However, bind parameters do not protect SQL parts concatenated from dynamic identifiers or fragments. Those parts require an allowlist and dialect-appropriate quoting.

## 13. Syntax Errors from Quotes, Parentheses, and Query Structure

Parentheses, single quotes, double quotes, and identifier quotes have different meanings:

- Parentheses `()` group expressions, function arguments, subqueries, or `IN` lists.
- Single quotes `'...'` create string literals.
- Double quotes `"..."` usually quote identifiers in PostgreSQL and standard SQL.
- Backticks quote identifiers in MySQL.
- Square brackets usually quote identifiers in SQL Server.

Common mistakes:

- Missing closing parenthesis in nested queries.
- Using double quotes for strings instead of single quotes.
- Using single quotes around column names, causing the database to treat them as string literals.
- Using quote delimiters from another dialect.
- Quoting an alias but referencing it with different casing.
- Extra comma before `FROM` or after `SELECT`.
- Placing `WHERE` after `ORDER BY`.
- Using `LIMIT` on a database that does not support that syntax.
- Missing schema qualification or using the wrong schema.

Incorrect example:

~~~sql
SELECT "full_name"
FROM customer
WHERE email = "alice@example.com"
~~~

On PostgreSQL, `"alice@example.com"` is a quoted identifier, not a string. Written correctly:

~~~sql
SELECT "full_name"
FROM customer
WHERE email = 'alice@example.com'
~~~

If the actual column name is unquoted lowercase `full_name`, you can write `full_name` without quotes. Use quotes consistently with the schema and dialect.

## 14. Schema Qualification and Aliases

When multiple schemas have tables with the same name, qualify the schema explicitly:

~~~sql
SELECT c.id, c.full_name
FROM sales.customer AS c
WHERE c.id = :id
~~~

Errors can occur when the default search path/schema differs between local and production, the table exists in another schema, migrations created objects in a different schema than the query expects, an alias is declared but referenced inconsistently, or columns share names across joined tables without qualification.

Use short aliases and qualify columns when joining multiple tables:

~~~sql
SELECT c.id, o.id AS order_id
FROM customer AS c
JOIN purchase_order AS o
  ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

If identifiers require quoting, quote each component according to the dialect. Do not quote the whole string `sales.customer` as a single identifier when you mean schema `sales` and table `customer`; that looks for a literal table with a dot in its name.

## 15. PostgreSQL-Specific Syntax and Named Parameters

PostgreSQL has several syntax forms that can cause confusion when writing queries through a named-parameter abstraction:

- Native bind markers `$1`, `$2`.
- Casts using `::type` or `CAST(value AS type)`.
- JSON operators such as `->`, `->>`, `@>`, and `?` depending on operator.
- Arrays and `ANY`.
- Double-quoted identifiers.

When using Spring `DatabaseClient` named parameters, use `:name` for value parameters and test how the parser/driver handles operators containing special characters. If the SQL contains colons belonging to other syntax or string literals, check how your framework version's `NamedParameterExpander` handles them; using `CAST(:value AS type)` can be clearer than cast shorthand that confuses parsers.

Do not manually replace `:name` with `$1` when `DatabaseClient` is managing named parameter expansion. If using raw R2DBC `Statement`, write the driver's native markers.

## 16. Diagnosing Exceptions and SQLState

When a query fails, preserve the root cause. Spring/driver exception classes can indicate whether the error belongs to syntax, binding, data integrity, connection, or resource issues.

Information to collect:

- SQL template with sensitive data stripped.
- Parameter names and Java types.
- Database engine/version.
- Driver and R2DBC SPI versions.
- SQLState or vendor error code.
- Root exception and cause chain.
- Repository/service method invoking the query.
- Whether a transaction is active.
- Whether running the query directly on a database client yields the same error.

Do not log passwords, tokens, personal emails, or sensitive payloads just to debug bindings. You can log parameter names and Java types, such as `customerId: Long, createdAt: OffsetDateTime`, without logging values.

### 16.1. SQLState

SQLState is a standard/driver error classification code. Many syntax or access rule errors fall into class `42`, though exact codes depend on the database.

PostgreSQL examples:

| SQLState | Common Meaning |
|---|---|
| 42601 | Syntax error |
| 42703 | Undefined column |
| 42P01 | Undefined table/relation |
| 42804 | Datatype mismatch |

Do not apply PostgreSQL codes to every database. Extract the code from the driver exception and consult vendor documentation.

### 16.2. Distinguishing SQL Errors from Connection Errors

If the connection pool cannot grant a connection, the query may never have reached the database. Do not treat a connection timeout like a syntax error.

Some indicators:

- SQLState/vendor syntax code: the database received and rejected the SQL statement.
- Authentication failure: connection failed authentication.
- Acquire timeout: pool could not grant a connection within the configured time.
- Network reset: connection was dropped mid-flight.
- Bind/type error: statement could not bind or database rejected the data type.

Correct classification prevents editing SQL when the real cause is pooling or networking.

## 17. Procedure for Isolating Errors

When a repository method fails, follow this sequence:

1. Extract the root exception and SQLState/vendor code.
2. Identify the database, server version, driver, and SPI in use.
3. Separate the SQL template from parameter values.
4. Check the marker style and parameter count.
5. Check bind names and positional index order.
6. Check that nulls are bound using `bindNull` with the right Java type.
7. Check Java types against column types.
8. Replace real values with safe test data and run the SQL directly against the same database.
9. Quote reserved identifiers per dialect, and verify casing and schema.
10. Verify that any dynamic SQL fragments come from an allowlist.
11. Create an integration test reproducing the failure through the R2DBC driver.
12. Fix only the failing part and keep a regression test for that case.

When running SQL manually, remember native markers may differ from `DatabaseClient` named markers. If copying a `:name` SQL template into a database client tool, replace markers with test literals or native markers properly rather than assuming identical syntax.

## 18. Testing Bindings and Identifiers on a Real Database

Unit tests with mocks can confirm a service calls a repository, but they do not test the SQL parser, driver markers, quoting, or type mapping.

Maintain integration tests on a production-equivalent database/driver, for example using Testcontainers.

Cases to cover:

- String, numeric, UUID, date/time, and boolean binding.
- SQL `NULL` via `bindNull`.
- Nulls in `WHERE` conditions.
- Empty lists and multi-element lists for `IN`.
- Reserved words in table/column names.
- Mixed-case identifiers.
- Schema qualification and aliases in `JOIN`.
- Names with spaces or special characters if present in legacy schemas.
- Sort fields chosen from an allowlist.
- SQL injection payloads treated as values.
- Both native queries and Spring Data derived queries.
- Mapping results back to Java types.

### 18.1. `StepVerifier` Example

~~~java
StepVerifier.create(repository.findByEmail("alice@example.com"))
    .expectNextMatches(customer ->
        customer.email().equals("alice@example.com")
    )
    .verifyComplete();
~~~

For the not-found case:

~~~java
StepVerifier.create(repository.findByEmail("missing@example.com"))
    .verifyComplete();
~~~

For SQL `NULL`, create fixtures with nullable columns and confirm `IS NULL` queries return the expected rows. Do not use real emails in logs or test reports.

### 18.2. Testing Quoted Identifiers

If the schema has reserved words or mixed-case names, write a test migration creating those exact identifiers and run queries via R2DBC. Tests must run against the same database engine and mode as production; H2 compatibility mode does not always reproduce PostgreSQL/MySQL/SQL Server quoting rules.

## 19. Using SQL Logging in a Controlled Manner

In development/test environments, you can enable appropriate logging to inspect SQL templates or driver info. Logger names and log levels depend on Spring Framework, Spring Data, and driver versions.

Do not enable verbose SQL/bind logging arbitrarily in production because bind values can contain personal data, tokens, or sensitive business data.

Useful diagnostic logs typically record query name or repository method, datasource alias, sanitized SQL template, parameter names and Java types, duration, rows updated, and SQLState/vendor code on failure.

There is no need to log every parameter value. When reproduction is needed, use synthetic data in tests.

## 20. Common Mistakes

**Using another driver's markers.** `DatabaseClient` can translate named markers; raw `Statement` needs native markers. Pick a consistent mechanism.

**Getting bind indices wrong.** R2DBC SPI uses zero-based indices in `bind(int, value)`. Do not start at 1 just because PostgreSQL placeholders show `$1`.

**Binding null with `bind`.** Use `bindNull(index/name, JavaType)`.

**Using `= NULL`.** SQL requires `IS NULL` to check for null values.

**Binding column names as parameters.** Parameters are values, not identifiers. Use an allowlist for dynamic column names.

**Concatenating input into SQL.** Easily introduces SQL injection. Bind every value and allowlist every dynamic identifier/fragment.

**Using quotes from the wrong dialect.** Double quotes, backticks, and square brackets are not interchangeable across databases.

**Overlooking quoted identifier casing.** PostgreSQL distinguishes quoted mixed-case from unquoted lowercase. Check real object names in the schema.

**Using reserved words as object names.** Prefer renaming; if impossible, quote per dialect and test mapping.

**Querying the wrong schema.** Qualify schema/table or configure the search path explicitly.

**Using `IN` with an empty list.** Handle before running the query and cap list sizes.

**Testing only with mocks/H2.** Production drivers and databases can handle markers, types, and quotes differently. Use integration tests with the real engine.

## 21. Design Principles

- Use named parameters via Spring `DatabaseClient` when appropriate and let the framework translate markers by dialect.
- With raw R2DBC `Statement`, use the driver's native markers.
- Remember that bind indices in R2DBC SPI start at 0.
- Do not bind null with `bind`; use `bindNull` with an explicit Java type.
- Distinguish SQL `NULL`, unbound parameters, and `IS NULL` predicates.
- Bind all input values; never concatenate user values into SQL.
- Do not use value parameters to replace table, schema, column names, or SQL keywords.
- Choose dynamic identifiers from an allowlist and quote per dialect.
- Avoid reserved words, mixed-case, and special characters when designing schemas if possible.
- Check schema qualification, aliases, casing, and naming strategies.
- Verify SQL syntax against the actual database server/version.
- Cross-check Java types against database column types and driver mappings.
- Handle empty collections, cap batch sizes, and test `IN` expansion.
- Preserve SQLState, vendor code, and cause chains for diagnostics.
- Do not log sensitive bind values or credentials.
- Use integration tests with the real R2DBC driver and database engine.

## 22. Takeaways

Parameter binding errors typically stem from driver-incompatible markers, mismatched names/indices, nulls not bound with `bindNull`, or Java types incompatible with columns. SQL syntax errors should be checked against the database dialect and version. Identifier errors usually relate to reserved words, quote delimiters, casing, or wrong schemas.

With Spring `DatabaseClient`, named parameters separate values from SQL and translate markers per driver. With direct R2DBC SPI, use native markers and remember zero-based indexing. Identifiers cannot be bound as values; dynamic names must be allowlisted and quoted per database. Diagnose using the root exception, SQLState, parameter types, and integration tests on a real database to fix the true cause without introducing SQL injection vulnerabilities.
