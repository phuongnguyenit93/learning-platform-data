# Distinguishing Value Parameters from Table Names, Column Names, and SQL Structure

When writing custom SQL in Spring Data JDBC or Spring JDBC, you must distinguish **data passed into the statement** from **the structure forming the SQL statement**. A prepared statement can bind a value such as a customer ID, status, date, or quantity. It cannot use a placeholder to substitute a table name, column name, SQL keyword, operator, or an entire SQL clause.

This boundary is both a technical rule of JDBC and the foundation for preventing SQL injection. This lesson uses an order example to show what should be bound, what must be selected from configuration/allowlists, and how to organize dynamic queries safely using `JdbcTemplate`, `NamedParameterJdbcTemplate`, and Spring Data JDBC `@Query`.

## 1. Two kinds of elements in a SQL statement

Consider the query:

```sql
SELECT id, status, total_amount
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC;
```

There are two groups of elements:

| Category | Examples in the SQL statement | Role |
| --- | --- | --- |
| SQL structure | `SELECT`, `FROM`, `WHERE`, `ORDER BY`, `AND`, `DESC` | Defines what operation the database must perform. |
| Identifiers | `purchase_order`, `customer_id`, `created_at`, `status` | Specifies the table, schema, column, or SQL object to access. |
| Data values | `7`, `CREATED`, `2026-11-01` | Data compared, written, or processed in the statement. |
| Expressions/operators | `=`, `>`, `LIKE`, `COUNT(...)` | Defines how expressions are evaluated. |

In the statement above, the two `?` markers are placeholders for **data values**. At execution time, JDBC binds the customer ID and status into those positions.

You cannot replace `purchase_order` or `created_at` with a bound value. Table names and column names must be recognized by the SQL parser when the statement is parsed; they belong to the statement structure.

You can remember this with two questions:

- Is the user choosing **which data** to search for? Bind the value.
- Is the user choosing **which table/column/operator/order** the SQL executes? Choose from a set of structures permitted by the application, never bind directly from input.

## 2. Binding values with PreparedStatement and JdbcTemplate

Example using `JdbcTemplate`:

```java
@Repository
public class OrderSearchRepository {

    private final JdbcTemplate jdbc;

    public OrderSearchRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findByCustomerAndStatus(
            long customerId,
            String status) {

        String sql = """
            SELECT id, customer_id, status, total_amount
            FROM purchase_order
            WHERE customer_id = ?
              AND status = ?
            ORDER BY created_at DESC
            """;

        return jdbc.query(
            sql,
            (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getLong("customer_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount")
            ),
            customerId,
            status
        );
    }
}
```

The values `customerId` and `status` are bound as statement parameters. Even if status contains a single quote or a string that looks like SQL, the driver still passes it as data; it never becomes part of the statement syntax.

Example writing data:

```java
String sql = """
    UPDATE purchase_order
    SET status = ?
    WHERE id = ?
    """;

int updated = jdbc.update(sql, newStatus, orderId);
```

Do not concatenate request values into SQL using `+`:

```java
// Unsafe: data enters SQL structure.
String sql = "SELECT * FROM purchase_order WHERE status = '"
    + status + "'";
```

If `status` comes from a request, a user can supply a string that alters the syntax. Even if current input only comes from a dropdown, you should still bind it as a value. Validating whether the status is domain-valid is a separate step; parameter binding protects the SQL boundary.

## 3. NamedParameterJdbcTemplate: parameter names are not column names

`NamedParameterJdbcTemplate` lets you give readable names to **values**:

```java
String sql = """
    SELECT id, customer_id, status, total_amount
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("customerId", customerId)
    .addValue("status", status);

List<OrderSummary> result =
    namedParameterJdbcTemplate.query(sql, params, rowMapper);
```

Here `:customerId` and `:status` are placeholders for data. They are not references to the `customer_id` or `status` columns. Parameter names are chosen in code; column names stay in the SQL.

The following example does not mean selecting a column based on the passed value:

```sql
SELECT id
FROM purchase_order
WHERE :columnName = :value;
```

The database treats `:columnName` as a value expression. It does not substitute the `status` or `customer_id` identifier. Depending on the database, the expression may be compared as a constant, leading to meaningless results or data type errors.

**A placeholder name is the name of a data variable**, not a text-substitution mechanism in SQL.

## 4. Why cannot table names or column names be bound?

A prepared statement is parsed into a structure by the database before bound values are supplied. A placeholder represents a literal/expression value in an allowed position, not an identifier token in the SQL grammar.

Examples that do not work as expected:

```java
String sql = "SELECT * FROM ? WHERE id = ?";
jdbc.query(sql, rowMapper, tableName, id);
```

The first placeholder does not become a table name. Similarly:

```java
String sql = "SELECT ? FROM purchase_order WHERE id = ?";
jdbc.query(sql, rowMapper, columnName, id);
```

A placeholder in the SELECT list is an expression value, not a selected column. The result is usually the same constant string returned for every row, rather than the contents of the column whose name was passed.

Positions that cannot be replaced by bind parameters:

| Element you want to vary | Can it be bound directly? | Example |
| --- | --- | --- |
| Value in WHERE | Yes | `WHERE id = ?` |
| Value in INSERT/UPDATE | Yes | `SET status = ?` |
| Value in LIMIT/OFFSET | Often yes on many drivers/databases; check dialect | `LIMIT ? OFFSET ?` |
| Table name | No | `FROM ?` |
| Schema name | No | `FROM ?.purchase_order` |
| Column name | No | `ORDER BY ?` when trying to pick a dynamic column |
| ASC/DESC | No | `ORDER BY created_at ?` |
| Operator | No | `WHERE amount ? ?` |
| SQL keyword or clause | No | Inserting `DISTINCT` via a placeholder |
| Function name/JOIN syntax | No | Choosing a JOIN fragment via a placeholder |

Note: some databases allow binding values in row-limit positions or specific expressions. Check your driver and dialect. That does not turn placeholders into a tool for replacing identifiers or SQL syntax.

## 5. ORDER BY ? does not select a column from a parameter

This is a common mistake when building dynamic sorting screens:

```java
String sql = """
    SELECT id, status, created_at
    FROM purchase_order
    ORDER BY ?
    """;

jdbc.query(sql, rowMapper, sortColumn);
```

A developer might think passing `created_at` produces `ORDER BY created_at`. Instead, the database receives a parameter value inside the sort expression. It does not parse the parameter's string content as a column name. All rows may be ordered by the same constant, leaving the result unsorted by the intended column.

Similarly, `ORDER BY ? DESC` does not let users choose an identifier. Parameter binding is safe regarding data injection, yet wrong regarding query semantics.

The solution is to choose the column name from an allowlist, and then bind only the remaining values.

## 6. Safe dynamic sorting with an allowlist

Suppose the UI allows sorting orders by creation date, total amount, or status. Never concatenate `sortBy` directly from the request into SQL. Map a fixed API key to an application-controlled SQL identifier.

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "createdAt", "created_at",
    "totalAmount", "total_amount",
    "status", "status"
);

public List<OrderSummary> search(
        long customerId,
        String requestedSort,
        String requestedDirection,
        int limit) {

    String column = SORT_COLUMNS.get(requestedSort);
    if (column == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    String direction = switch (
            requestedDirection.toUpperCase(Locale.ROOT)) {
        case "ASC" -> "ASC";
        case "DESC" -> "DESC";
        default -> throw new IllegalArgumentException(
            "Unsupported sort direction"
        );
    };

    String sql = """
        SELECT id, customer_id, status, total_amount, created_at
        FROM purchase_order
        WHERE customer_id = ?
        ORDER BY %s %s
        LIMIT ?
        """.formatted(column, direction);

    return jdbc.query(sql, rowMapper, customerId, limit);
}
```

In this example:

- `requestedSort` is not inserted directly into SQL. It is only a lookup key in `SORT_COLUMNS`.
- The value retrieved from the map is a hardcoded SQL identifier in source code.
- `requestedDirection` is converted into one of two fixed strings: `ASC` or `DESC`.
- `customerId` and `limit` are still bound as data.
- If the user sends an unsupported key, the application rejects the request.

The structure formatted into SQL is an **allowlisted value**, not arbitrary input. This preserves flexible sorting while ensuring the SQL statement contains only identifiers/keywords defined by the application.

If the API does not need many options, using an enum is even clearer:

```java
public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    STATUS
}
```

You can `switch` on the enum to obtain the column name. Enums avoid passing free-form strings across application layers.

### Allowlist the sort direction as well

`ASC` and `DESC` are SQL syntax, not data values. Do not do this:

```java
String sql = "SELECT ... ORDER BY created_at " + request.direction();
```

Instead, accept only explicit choices. With a boolean such as `descending`, you can map:

```java
String direction = descending ? "DESC" : "ASC";
```

Do not concatenate arbitrary strings such as `NULLS FIRST`, `COLLATE ...`, or client-supplied SQL fragments unless backed by a dedicated allowlist and clear understanding of database semantics.

## 7. Dynamic table/schema: choose only from trusted configuration

Sometimes an application must query one of several tables sharing the same structure, such as a current table and an archive table:

```java
public enum OrderStore {
    CURRENT,
    ARCHIVE
}
```

Map the choice to a fixed table name:

```java
private static String tableFor(OrderStore store) {
    return switch (store) {
        case CURRENT -> "purchase_order";
        case ARCHIVE -> "purchase_order_archive";
    };
}

public List<OrderSummary> findById(OrderStore store, long id) {
    String table = tableFor(store);

    String sql = """
        SELECT id, customer_id, status, total_amount
        FROM %s
        WHERE id = ?
        """.formatted(table);

    return jdbc.query(sql, rowMapper, id);
}
```

The `store` value should be decided by application business logic/authorization. Never pass a table name directly from a query string or JSON into `tableFor`.

Unsafe:

```java
String sql = "SELECT * FROM " + request.tableName()
    + " WHERE id = ?";
```

If users control `tableName`, they can try injecting another identifier, another schema, or unexpected syntax. Even if the database account lacks privileges on sensitive tables, the application should never let a request dictate SQL structure.

### Per-tenant schemas

Some systems use a separate schema per tenant. Never concatenate an unverified tenant ID into a schema name:

```java
// Unsafe if tenantSchema comes directly from the request.
String sql = "SELECT * FROM " + tenantSchema + ".purchase_order";
```

A safer approach is mapping an authenticated tenant to a schema listed in a server-managed registry/configuration. If using datasource routing or setting schema/search path on the connection, ensure tenant context is verified and cannot leak across requests or connection pools.

An allowlist can be a map from an internal tenant key to a fixed schema identifier. Do not treat regex string validation as sufficient proof that the user is authorized to access that schema.

## 8. Dynamic WHERE: combine fixed fragments, bind every value

Search queries often have several optional filters. For example, a user filters by customer, status, and date range.

You can build the SQL from code-defined fragments:

```java
public List<OrderSummary> search(OrderFilter filter) {
    StringBuilder sql = new StringBuilder("""
        SELECT id, customer_id, status, total_amount, created_at
        FROM purchase_order
        WHERE 1 = 1
        """);

    MapSqlParameterSource params = new MapSqlParameterSource();

    if (filter.customerId() != null) {
        sql.append(" AND customer_id = :customerId");
        params.addValue("customerId", filter.customerId());
    }

    if (filter.status() != null) {
        sql.append(" AND status = :status");
        params.addValue("status", filter.status());
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
        params.addValue("createdFrom", filter.createdFrom());
    }

    if (filter.createdBefore() != null) {
        sql.append(" AND created_at < :createdBefore");
        params.addValue("createdBefore", filter.createdBefore());
    }

    return namedParameterJdbcTemplate.query(
        sql.toString(),
        params,
        rowMapper
    );
}
```

The fragments appended to SQL are fixed literals written in code. Actual data goes into `MapSqlParameterSource`. This lets the number of conditions vary without concatenating user values into the statement.

Do not do:

```java
sql.append(" AND status = '" + filter.status() + "'");
```

Also never accept a whole WHERE expression sent by the client. The client should send structured filters (e.g., `status`, `createdFrom`), while the server decides how to turn those filters into SQL.

### Dynamic operators

If multiple comparison types need to be supported, map the operator to a fixed set:

```java
String operator = switch (filter.amountComparison()) {
    case EQUALS -> "=";
    case GREATER_THAN -> ">";
    case LESS_THAN -> "<";
};

sql.append(" AND total_amount ").append(operator)
   .append(" :amount");
params.addValue("amount", filter.amount());
```

Operators cannot be bound as values. Append the operator only after mapping from an enum/allowlist to one of the fixed strings. Never concatenate a raw operator string sent from a request into SQL.

## 9. NamedParameterJdbcTemplate and IN lists

One advantage of `NamedParameterJdbcTemplate` is expanding a collection into multiple placeholders inside `IN`:

```java
String sql = """
    SELECT id, status
    FROM purchase_order
    WHERE status IN (:statuses)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("statuses", List.of("CREATED", "CONFIRMED"));

List<OrderHeader> result =
    namedParameterJdbcTemplate.query(sql, params, headerMapper);
```

The framework expands the collection into an appropriate list of bind parameters rather than concatenating values into SQL. Each status remains bound data.

Handle empty lists before running the query. Do not depend on the database accepting `IN ()`; many databases reject that syntax. Common decisions:

- An empty list means no status filter: omit the `IN` condition.
- An empty list means no results are allowed: return an empty list immediately in the service.
- An empty list is invalid per API contract: return a validation error.

Never convert a list into a comma-separated string and concatenate it into SQL. That complicates quoting and opens up SQL injection.

## 10. @Query in Spring Data JDBC also binds values

Repositories can declare custom SQL with `@Query`:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, status, total_amount, created_at, note
        FROM purchase_order
        WHERE customer_id = :customerId
          AND status = :status
        ORDER BY created_at DESC
        """)
    List<PurchaseOrder> findRecentByCustomerAndStatus(
        Long customerId,
        String status
    );
}
```

Parameter names such as `:customerId` and `:status` are placeholders for values. `purchase_order`, `customer_id`, `status`, and `created_at` remain identifiers written in the SQL.

You cannot write a `@Query` like:

```java
@Query("SELECT * FROM :tableName WHERE :columnName = :value")
List<PurchaseOrder> search(
    String tableName,
    String columnName,
    Object value
);
```

expecting Spring Data to replace `tableName` with a table name and `columnName` with a column name. Those placeholders are not a templating mechanism for identifiers. If dynamic table/column selection is needed, use a custom repository to pick allowlisted fragments and bind values.

When using `@Query`, also ensure the SQL matches the return type. Aggregate queries must return enough data for mapping per the mapping contract; reporting queries should use a DTO/projection or appropriate custom row mapper. Parameter binding does not by itself solve projection or aggregate-loading requirements.

## 11. LIKE: value binding still requires understanding wildcards

Parameter binding prevents input strings from becoming SQL syntax, but it does not change the wildcard meaning of `LIKE`.

Example:

```java
String sql = """
    SELECT id, note
    FROM purchase_order
    WHERE note LIKE ?
    """;

jdbc.query(sql, rowMapper, "%" + searchText + "%");
```

`searchText` is still safely bound. However, if the user enters `%` or `_`, those characters act as wildcards in `LIKE`; results may be broader than intended. This is a search-semantics issue, not SQL injection.

To search for a literal substring, escape wildcards according to the SQL dialect and specify an `ESCAPE` character, for example:

```sql
SELECT id, note
FROM purchase_order
WHERE note LIKE ? ESCAPE '!';
```

The application can escape `!`, `%`, and `_` in the input before wrapping with wildcards at both ends. Escape rules must be consistent with the database and chosen escape character.

Do not confuse two goals:

- Parameter binding protects the boundary between values and SQL syntax.
- Escaping wildcards protects literal search semantics inside the `LIKE` operator.

## 12. Identifier quoting does not replace an allowlist

Databases have their own identifier quoting syntax. PostgreSQL uses double quotes, MySQL commonly uses backticks (or double quotes when configured), and SQL Server uses square brackets or quoted identifier rules. Quoting helps the database parse identifiers with uppercase letters, spaces, or reserved keywords according to engine rules.

However, **quoting an arbitrary string does not prove the user is authorized to choose that identifier**. Separate two concerns:

1. Validate that the identifier belongs to the set of options permitted by the application.
2. If needed, quote the identifier according to the database's exact dialect and escaping rules.

For known sort columns, an allowlist mapping directly to canonical identifiers is usually simpler than writing a custom quoting helper. Avoid writing a homemade quote function and treating it as the sole defense against injection.

Do not replace quotes or strip special characters with regex to "sanitize" arbitrary identifiers. Regex can miss escaping rules, keywords, schema qualification, or authorization checks. An explicit allowlist makes clear which structures the application allows.

## 13. SQL injection patterns to avoid

### Concatenating values directly into conditions

```java
String sql = "SELECT * FROM purchase_order WHERE status = '"
    + request.status() + "'";
```

If input contains a quote followed by SQL, it can alter the statement logic.

Correct approach:

```java
String sql = """
    SELECT * FROM purchase_order
    WHERE status = ?
    """;

jdbc.query(sql, rowMapper, request.status());
```

### Concatenating sort columns from requests

```java
String sql = "SELECT * FROM purchase_order ORDER BY "
    + request.sortBy();
```

Correct approach: look up `sortBy` in an allowlist, reject unsupported keys, and append the selected fixed identifier. Filter values remain bound separately.

### Concatenating an entire condition clause

```java
String sql = "SELECT * FROM purchase_order WHERE "
    + request.whereClause();
```

Never accept a free-form `WHERE` fragment from the client. Accept a typed filter DTO, validate each field, and build fixed conditions on the server.

### Stored data is not automatically trustworthy either

A value read from the database might originally have been entered by a user or an external system. If you later take that value and concatenate it into dynamic SQL, it can still cause injection. Always bind all data as value parameters; dynamic identifiers must still come from server-side configuration/allowlists regardless of the string's origin.

## 14. Designing search APIs without letting clients send SQL

An API should accept a structured business request:

```json
{
  "customerId": 7,
  "statuses": ["CREATED", "CONFIRMED"],
  "sortBy": "createdAt",
  "direction": "DESC",
  "limit": 20
}
```

The server performs these steps:

1. Verify access permission for customer 7.
2. Validate that the status list contains valid domain values.
3. Look up `sortBy` in the allowlist.
4. Map direction to fixed `ASC` or `DESC`.
5. Validate limit within permitted bounds.
6. Build SQL from controlled structure.
7. Bind customer ID, each status, and limit as data.

The API does not need and should not accept:

```json
{
  "table": "purchase_order",
  "column": "created_at",
  "operator": ">",
  "where": "customer_id = 7",
  "orderBy": "created_at DESC"
}
```

If a product genuinely needs a general-purpose query builder, define a small filter language with supported fields/operators, then compile it to SQL using an allowlist. Never turn an API into an arbitrary SQL execution endpoint.

## 15. Testing parameter binding and dynamic structure

Test these two groups separately.

### Testing values

- Statuses with quotes, hyphens, or Unicode characters are still treated as values.
- Strings resembling SQL payloads do not alter query structure.
- Nulls are handled per contract and SQL types.
- Dates, decimals, and booleans are bound with proper types.
- `IN` lists with 1, many, and 0 elements are handled accurately.

### Testing structure

- Only allowlisted sort keys are accepted.
- `ASC` and `DESC` are the only valid choices; other strings are rejected.
- Table names can only be selected from allowed enums/registries.
- No API concatenates client-supplied `whereClause`, `columnName`, or `tableName` directly.
- Optional filters only append fixed fragments and bind corresponding values.
- Queries run against the production database/driver whenever dialect-dependent syntax is used.

Example test for an invalid sort field:

```java
assertThatThrownBy(() ->
    repository.search(
        7L,
        "created_at DESC; DELETE FROM customer",
        "ASC",
        20
    )
).isInstanceOf(IllegalArgumentException.class);
```

This test confirms that a key outside the allowlist is rejected. Complement it with integration tests verifying no secondary statement executes and data remains intact.

A malicious-value test should confirm it is treated as data:

```java
String input = "' OR 1=1 --";

List<OrderSummary> result =
    repository.findByStatus(input);
```

The proper outcome is querying for a status matching that literal string; it must not return all orders as unsafe SQL concatenation would.

## 16. Decision table: bind or allowlist?

| Input element | Handling | Example |
| --- | --- | --- |
| Customer ID | Bind value | `WHERE customer_id = :id` |
| Status | Bind value and domain-validate | `status = :status` |
| Start/end dates | Bind value | `created_at >= :from` |
| Search keyword | Bind value; escape wildcards if literal LIKE needed | `note LIKE :pattern` |
| Status list | Bind collection via named parameter | `status IN (:statuses)` |
| Sort column name | Allowlist/enum to fixed identifier | `created_at`, `total_amount` |
| Sort direction | Allowlist enum/boolean | `ASC`, `DESC` |
| Table name | Server-side allowlist/configuration | `purchase_order`, `purchase_order_archive` |
| Schema/tenant name | Authenticated registry or datasource/schema routing | tenant key → fixed schema |
| Operator | Allowlist enum | `=`, `>`, `<` |
| SQL fragment/WHERE/JOIN | Do not accept from client; assemble from fixed fragments in code | `AND status = :status` |
| Vendor-specific function/syntax | Choose from controlled code/configuration | dialect-appropriate function |

## 17. Principles for organizing a custom repository

When dynamic queries have many options, consolidate SQL construction in a dedicated adapter/repository. Separate three steps:

- **Validate request:** check filters, authorization, sort key, direction, and limits.
- **Build statement:** pick fragments/identifiers from allowlists and assemble fixed structure.
- **Bind parameters:** pass all values via `JdbcTemplate` or `NamedParameterJdbcTemplate`.

Example of a simple design:

```java
public record OrderSearch(
    Long customerId,
    String status,
    OrderSort sort,
    SortDirection direction,
    int limit
) {}

public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    STATUS
}

public enum SortDirection {
    ASC,
    DESC
}
```

The sort enum can be mapped using `switch`:

```java
private static String columnFor(OrderSort sort) {
    return switch (sort) {
        case CREATED_AT -> "created_at";
        case TOTAL_AMOUNT -> "total_amount";
        case STATUS -> "status";
    };
}
```

The direction enum can map directly to fixed SQL strings:

```java
private static String directionFor(SortDirection direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
```

Thus, the SQL-building code never has to guess which request string might be safe to concatenate. It receives only validated choices and translates them into valid SQL structure.

When supporting multiple databases, identifiers and syntax may differ by dialect. Keep those differences inside the corresponding adapter/implementation rather than scattering vendor-specific branches across services.

## 18. Self-check questions

- For what kind of elements in a SQL statement does PreparedStatement use placeholders?
- Why doesn't `FROM ?` replace `?` with a table name?
- How does `ORDER BY ?` differ from `ORDER BY created_at`?
- Why is parameter name `:customerId` not a column name?
- When can `NamedParameterJdbcTemplate` be used to bind a list in `IN`?
- If a user chooses a sort column, what must the application do before placing the column name into SQL?
- Why must both `ASC`/`DESC` and operators be allowlisted?
- Can you accept an entire `WHERE` fragment from the client and bind part of the values? Why or why not?
- Does identifier quoting replace an allowlist?
- How do you keep per-tenant schema selection safe?
- Why must data read from a database still be bound if reused in another SQL query?
- Does `LIKE` parameter binding automatically turn `%` and `_` into literal characters?

When writing custom SQL, **bind all data values** and **select all dynamic identifiers/structures from application-controlled choices**. Prepared statements are not text-substitution engines for SQL; they keep data separate from syntax. For table names, column names, sort directions, and operators, use enums/allowlists or server-side configuration, and test both input data and generated statement structure.
