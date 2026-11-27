# Bind Parameters to Protect Input Values from SQL Injection

In Spring Data Relational R2DBC applications, data from HTTP requests, messages, imported files, or external systems is often used in SQL statements. If that data is concatenated directly into a SQL string, an attacker can alter the statement structure and perform SQL injection. The most important defense at the data access layer is parameter binding: write the SQL statement with placeholders, then bind each value using the Spring Data R2DBC or R2DBC SPI API.

Parameter binding separates the SQL statement from the data. The driver receives the statement and the values separately, treating the values as expression data rather than parsing them as SQL syntax. This prevents input from turning into operators, conditions, comments, or additional SQL statements. However, binding only applies to values; table names, column names, keywords, sort directions, and dynamic SQL clauses must still be controlled using an allowlist or safe query structure.

## 1. How Does SQL Injection Happen?

SQL injection occurs when an application concatenates untrusted data into SQL in a way that causes the data to be interpreted as syntax. For example, a login application builds a statement using string concatenation:

```java
String sql = "SELECT id, username FROM app_user "
        + "WHERE username = '" + username + "' "
        + "AND password_hash = '" + passwordHash + "'";
```

If a user submits a special value such as:

```text
' OR '1'='1' --
```

the input can close the quote, add an always-true condition, and comment out the rest of the statement. The resulting SQL may no longer carry the meaning the developer intended.

The risk is not limited to login forms. Any value concatenated into SQL can become an injection point: search keywords, IDs, emails, filters, imported content, sort values, pagination, or previously stored data.

## 2. Why Does Parameter Binding Prevent Injection?

With bind parameters, the SQL statement keeps its structure and the values are sent separately:

```java
return databaseClient.sql("""
        SELECT id, username
        FROM app_user
        WHERE username = :username
          AND password_hash = :passwordHash
        """)
        .bind("username", username)
        .bind("passwordHash", passwordHash)
        .map((row, metadata) -> new UserSummary(
                row.get("id", Long.class),
                row.get("username", String.class)))
        .one();
```

`username` and `passwordHash` are passed as values. If the username contains quotes or the string `OR 1=1`, it remains merely the content of the parameter. The driver does not concatenate that content into new SQL syntax.

Conceptually:

```text
SQL template:  SELECT ... WHERE username = :username
Parameter:     username = "' OR '1'='1' --"

The database receives the statement structure and the bound values separately.
A value cannot close its own placeholder to append a SQL clause.
```

The driver may use a prepared statement, a dedicated bind protocol, or a database-appropriate mechanism. You should not rely on whether the driver caches execution plans to assess safety; what must be ensured is that values are passed through the bind API rather than concatenated into SQL text.

## 3. Core Rule: Bind Every Input Value

Every value coming from outside must be passed through a placeholder instead of string concatenation. For example:

| Data | Safe approach |
| --- | --- |
| Username, email, name | Bind into `WHERE` conditions |
| ID or reference code | Bind into `=`, `IN`, `JOIN` conditions |
| Update values | Bind into `SET column = :value` |
| Dates, monetary amounts, statuses | Bind with the appropriate Java type |
| Search keywords | Bind into `LIKE`/`ILIKE` or full-text expressions |
| `LIMIT`/`OFFSET` | Bind if supported by the driver/database and API; also validate bounds |
| List of IDs | Use a supported collection expansion mechanism or build safe placeholders |

Do not concatenate values into SQL, even after calling `trim()`, changing case, stripping quotes, or manually escaping. String processing does not replace parameter binding.

## 4. Using `DatabaseClient` with Named Parameters

Spring Framework's `DatabaseClient` provides a reactive SQL API and supports binding named parameters. Placeholders take the form `:parameterName` in SQL:

```java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE email = :email
            """)
            .bind("email", email)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("email", String.class),
                    row.get("display_name", String.class)))
            .one();
}
```

Named parameters make code easier to read because binding is by name instead of remembering positions. `DatabaseClient` translates named parameters to the markers used by the R2DBC driver. For example, PostgreSQL typically uses `$1`, `$2` markers; some drivers use `?` or another syntax. When using `DatabaseClient`, the application usually does not need to write the driver's physical markers directly.

The `bind(...)` methods return an execute spec for further configuration. All required parameters must be bound before calling `fetch()`, `map()`, `rowsUpdated()`, or the corresponding execution API.

## 5. Binding in `INSERT`, `UPDATE`, and `DELETE`

Parameter binding applies to all DML statements, not just `SELECT` queries.

### INSERT

```java
public Mono<Long> insertCustomer(CreateCustomerCommand command) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            """)
            .bind("email", command.email())
            .bind("displayName", command.displayName())
            .fetch()
            .rowsUpdated();
}
```

### UPDATE

```java
public Mono<Long> renameCustomer(Long customerId, String newName) {
    return databaseClient.sql("""
            UPDATE customer
            SET display_name = :displayName
            WHERE id = :id
            """)
            .bind("displayName", newName)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
}
```

### DELETE

```java
public Mono<Long> deleteCustomer(Long customerId) {
    return databaseClient.sql("DELETE FROM customer WHERE id = :id")
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
}
```

In all three examples, the SQL structure is fixed; variable values are bound separately. Do not concatenate `customerId`, name, or email into the SQL string.

## 6. Using Bind Parameters in Spring Data R2DBC Repositories

Spring Data R2DBC derived query methods generate queries from method names and bind parameters according to metadata. For example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByDisplayNameContaining(String keyword);

    Mono<Boolean> existsByEmail(String email);
}
```

With derived queries, there is no need to assemble SQL manually. Spring Data builds the query conditions and binds method argument values through its mapping mechanism.

When custom SQL is needed, use `@Query` with named parameters:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM customer WHERE email = :email")
    Mono<Customer> findExactEmail(@Param("email") String email);

    @Modifying
    @Query("UPDATE customer SET active = :active WHERE id = :id")
    Mono<Integer> updateActive(
            @Param("id") Long id,
            @Param("active") boolean active);
}
```

`@Param` specifies which method argument corresponds to which placeholder. Use the Spring Data repository query annotation package (`org.springframework.data.repository.query.Param`). Update signatures and return types must match the Spring Data R2DBC version; for operations that need to inspect the updated row count, choose a return type supported by the version or use `DatabaseClient`.

`@Query` does not automatically make SQL text safe if a developer has concatenated input into the annotation/runtime string. Placeholders and bound method arguments are what separate values from SQL.

## 7. Using `R2dbcEntityTemplate` and Criteria

When querying dynamically with multiple conditions, `R2dbcEntityTemplate` together with `Criteria` lets you express conditions via an API instead of concatenating SQL:

```java
public Flux<Customer> searchCustomers(String email, Boolean active) {
    Criteria criteria = Criteria.empty();

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email").is(email);
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    return template.select(Customer.class)
            .matching(Query.query(criteria))
            .all();
}
```

`Criteria` stores conditions and values separately; Spring Data translates them into a query with bind parameters. Property names are mapped to columns using entity metadata. Handle the case with no conditions according to business requirements, such as limiting results or rejecting full-table queries.

Do not concatenate input into a raw-SQL `Criteria`. Use the typed API and control which fields clients are allowed to filter on.

## 8. Binding Directly with R2DBC SPI `Statement`

When using the SPI directly, create a `Statement` with SQL containing driver-specific markers, then bind the values:

```java
Statement statement = connection.createStatement(
        "SELECT id, email FROM customer WHERE email = $1");

statement.bind(0, email);

Flux<CustomerSummary> customers = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerSummary(
                        row.get("id", Long.class),
                        row.get("email", String.class)))));
```

In the PostgreSQL example, the SQL marker `$1` is bound using index `0` in the SPI API. `Statement`'s `bind` index is 0-based, whereas PostgreSQL's SQL marker starts at `$1`. For drivers that use `?`, the SQL will use that driver's placeholder; do not copy PostgreSQL's marker syntax to another database engine.

The R2DBC SPI provides `bind(index, value)` and `bindNull(index, type)`. Do not pass `null` directly into `bind`. When using `DatabaseClient`, Spring manages translating named parameters to driver markers; when using the SPI directly, the application must follow the driver's markers and data types.

## 9. Parameter Binding Does Not Apply to Table Names or Column Names

A placeholder represents a value in a SQL expression. It cannot replace a table name, column name, keyword, or entire SQL clause.

Incorrect example:

```java
databaseClient.sql("SELECT * FROM :tableName WHERE id = :id")
        .bind("tableName", tableName)
        .bind("id", id);
```

The database does not interpret `:tableName` as an identifier. It is a value position, whereas `FROM` requires a table name that has already been parsed before binding.

Similarly, the following examples do not work as intended:

```sql
SELECT * FROM customer ORDER BY :columnName
SELECT * FROM customer ORDER BY created_at :direction
SELECT * FROM :schemaName.customer
```

Binding `:columnName` in `ORDER BY` usually just produces a constant value expression rather than selecting a column to sort by. Do not use binding to pass `ASC`, `DESC`, schema names, table names, column names, operators, or keywords.

## 10. Allowlists for Dynamic Identifiers

If the business logic truly requires choosing a sort column, map the input to an application-defined set of identifiers. Never put a client-sent string directly into SQL.

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "createdAt", "created_at",
        "displayName", "display_name",
        "email", "email"
);

public Flux<Customer> findCustomers(String sortField, Sort.Direction direction) {
    String column = SORT_COLUMNS.get(sortField);
    if (column == null) {
        return Flux.error(new IllegalArgumentException("Unsupported sort field"));
    }

    String sqlDirection = direction == Sort.Direction.DESC ? "DESC" : "ASC";
    String sql = "SELECT id, email, display_name, created_at "
            + "FROM customer ORDER BY " + column + " " + sqlDirection;

    return databaseClient.sql(sql)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

In this example, `column` can only take one of the three fixed SQL strings from the map; `sqlDirection` can only be `ASC` or `DESC` as determined by the enum. No raw identifier string from the request is concatenated directly into SQL.

You can use a `switch` instead of a map. The key point is that the allowlist is defined in code and any value not on the list is rejected or mapped to a documented safe default.

Do not rely on a simple regex like `^[a-zA-Z_]+$` as the sole safeguard. A syntactically valid identifier can still be a sensitive column or one that is not permitted for sorting. An allowlist enforces both syntax and application-level access control.

## 11. Distinguishing Identifiers, Keywords, and Values

| SQL component | Can it be bound as a value? | How to control it |
| --- | --- | --- |
| `WHERE email = :email` | Yes | Bind the email value |
| `SET display_name = :name` | Yes | Bind the name value |
| `LIMIT :limit` | Usually yes, depending on driver/database | Bind and validate range |
| `ORDER BY :column` | Does not select an identifier | Allowlist column names and append a fixed identifier |
| `ASC`/`DESC` | No | Enum/allowlist |
| Table/schema name | No | Internal configuration or allowlist |
| Operators like `=`, `LIKE`, `>` | No | Select from an enum/fixed code branch |
| Arbitrary `WHERE` clause | No | Build using `Criteria` or fixed fragments |

Rule: bind values; control identifiers and syntax with trusted code.

## 12. Building Dynamic WHERE Clauses While Still Binding All Values

A search screen may have many optional filters. You can assemble fixed SQL fragments and bind the corresponding values:

```java
StringBuilder sql = new StringBuilder(
        "SELECT id, email, display_name, active FROM customer WHERE 1 = 1");

if (filter.email() != null) {
    sql.append(" AND email = :email");
}
if (filter.active() != null) {
    sql.append(" AND active = :active");
}

DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql.toString());
if (filter.email() != null) {
    spec = spec.bind("email", filter.email());
}
if (filter.active() != null) {
    spec = spec.bind("active", filter.active());
}

return spec.map((row, metadata) -> mapCustomer(row)).all();
```

When conditions become complex, using `Criteria` or a typed query builder is usually easier to maintain than building strings manually. Either way, never concatenate raw input into a SQL fragment.

## 13. Searching with `LIKE` and Wildcard Characters

Parameter binding prevents SQL injection, but it does not automatically remove the wildcard meaning of `LIKE`. In SQL, `%` matches any sequence of characters and `_` matches a single character. If a user wants to search literally for a string containing `%` or `_`, you need to escape the wildcards according to database semantics.

Example using `!` as the escape character:

```java
private String escapeLikeLiteral(String value) {
    return value.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

public Flux<Customer> searchName(String keyword) {
    String pattern = "%" + escapeLikeLiteral(keyword) + "%";

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE display_name LIKE :pattern ESCAPE '!'
            """)
            .bind("pattern", pattern)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

The value is still bound. Escaping here only changes the search semantics so `%` and `_` are treated as literal characters; it is not an anti-SQL-injection measure. `ESCAPE` syntax and collation/case-sensitivity behavior can vary across database engines. For PostgreSQL, you may consider `ILIKE` for case-insensitive search; verify syntax and indexes suitable for the target database.

## 14. Binding Collections in an `IN` Clause

When looking up multiple IDs, do not concatenate the list by building a SQL string from input:

```java
// Unsafe: the ID list is concatenated into SQL text.
String sql = "SELECT * FROM customer WHERE id IN (" + ids + ")";
```

`DatabaseClient` supports named parameter expansion for collections in corresponding Spring Framework versions:

```java
public Flux<Customer> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id IN (:ids)
            """)
            .bind("ids", ids)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Spring's `DatabaseClient` can expand a collection into the corresponding number of bind markers. This is behavior of Spring's named parameter expansion layer; do not assume raw R2DBC SPI `Statement.bind` accepts a `List` and that every driver expands it automatically.

Empty lists must be handled before building the query because `IN ()` is invalid in many database engines and the business meaning may be to return no results. For very large lists, split into batches or use temporary tables/array binding as supported by the database and driver; avoid generating SQL statements with tens of thousands of markers.

## 15. Pagination and Limiting Results

`LIMIT` and `OFFSET` values are usually bindable parameters, depending on the driver and database:

```java
public Flux<Customer> findPage(int pageSize, long offset) {
    int safeSize = Math.max(1, Math.min(pageSize, 200));
    long safeOffset = Math.max(0, offset);

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            ORDER BY id
            LIMIT :limit OFFSET :offset
            """)
            .bind("limit", safeSize)
            .bind("offset", safeOffset)
            .map((row, metadata) -> mapCustomer(row))
            .all();
}
```

Binding prevents input from altering SQL syntax, but validation is still required. If a client sends a huge page size, the query can still consume excessive CPU, memory, and connections even without injection. Bound the range and choose a deterministic ordering.

For large tables, consider keyset pagination instead of deep offsets so the database does not have to skip many rows. Cursor/keyset values such as `lastId` or `lastCreatedAt` still must be bound.

## 16. Binding Null Values Properly

`DatabaseClient.bind(name, value)` is not used to pass Java `null`. When SQL `NULL` is needed, use `bindNull(name, type)`:

```java
public Mono<Long> updatePhone(Long customerId, String phone) {
    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
            UPDATE customer
            SET phone_number = :phone
            WHERE id = :id
            """)
            .bind("id", customerId);

    if (phone == null) {
        spec = spec.bindNull("phone", String.class);
    } else {
        spec = spec.bind("phone", phone);
    }

    return spec.fetch().rowsUpdated();
}
```

With the R2DBC SPI directly, use `Statement.bindNull(index, type)`. The Java type must be compatible with the SQL type and the driver's codec. Do not pass `null` into regular `bind`.

Parameter binding also does not decide PATCH semantics on its own. In a PATCH API, a missing field may mean keep unchanged, whereas a field present with `null` may mean clear the value. DTOs must represent presence explicitly before deciding whether to bind `null` or omit the column from the statement.

## 17. Never Use String Concatenation to Build SQL Literals

The following patterns remain dangerous even if input has been lightly checked:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email.trim() + "'";

String escaped = email.replace("'", "''");
String sql2 = "SELECT * FROM customer WHERE email = '" + escaped + "'";
```

Manual escaping is error-prone due to encoding, quotes, data types, database dialects, and SQL context. A string escaped correctly for a string literal may be unsafe in an identifier, JSON expression, `LIKE` pattern, or another SQL clause.

Let the driver bind values. If a library expects a SQL string and separate parameters, use that library's parameter API. Do not write a generic `sanitizeSql()` function and treat sanitized strings as safe to concatenate into any SQL position.

## 18. Avoiding Second-Order SQL Injection

Second-order injection occurs when data is stored safely initially, then later retrieved and concatenated into a dynamic SQL statement without binding. For example, a user-configured report name is stored in a table, and later a background job uses it to build a SQL statement:

```java
String configuredFilter = report.getFilterExpression();
String sql = "SELECT * FROM customer WHERE " + configuredFilter;
```

The data may be harmless at insert time, but becomes SQL syntax when reused in a dynamic position. Every use of untrusted data in SQL must be controlled, including data already stored in the database.

Do not store a raw user-submitted SQL fragment and execute it later unless the product genuinely provides its own query language that is strictly parsed, bounded, and permission-checked. For report filters, store a typed structure such as field/operator/value, then map field/operator through an allowlist and bind the value.

## 19. Safe Dynamic Queries with Enums and Allowlists

For example, a filter allows comparing values for equality, greater-than, or less-than. Do not accept raw SQL operators from the client:

```java
enum Comparison {
    EQUALS,
    GREATER_THAN,
    LESS_THAN
}

private String sqlOperator(Comparison comparison) {
    return switch (comparison) {
        case EQUALS -> "=";
        case GREATER_THAN -> ">";
        case LESS_THAN -> "<";
    };
}
```

Then concatenate only the operator returned by the switch and bind the value:

```java
public Flux<Order> findByTotal(
        Comparison comparison,
        BigDecimal amount) {

    String operator = sqlOperator(comparison);
    String sql = "SELECT id, total FROM orders WHERE total "
            + operator + " :amount";

    return databaseClient.sql(sql)
            .bind("amount", amount)
            .map((row, metadata) -> new Order(
                    row.get("id", Long.class),
                    row.get("total", BigDecimal.class)))
            .all();
}
```

`operator` can only take the three constant strings controlled by the application. The `amount` value is always bound. If the field is also dynamic, use a separate allowlist for column names.

## 20. Using `Sort` and `Pageable` Safely

Spring Data provides `Sort` and `Pageable` abstractions. When using repository/template APIs that support them, the framework constructs sorting/paging from metadata and identifiers via its own mechanism. However, sort input coming from requests must still be restricted to permitted properties.

Example creating `Sort` from input through an allowlist:

```java
private static final Map<String, String> SORT_PROPERTY = Map.of(
        "name", "displayName",
        "created", "createdAt"
);

public Flux<Customer> findSorted(String requestedSort, boolean descending) {
    String property = SORT_PROPERTY.get(requestedSort);
    if (property == null) {
        return Flux.error(new IllegalArgumentException("Unsupported sort"));
    }

    Sort.Direction direction = descending
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    return template.select(Customer.class)
            .matching(Query.query(Criteria.empty())
                    .sort(Sort.by(direction, property)))
            .all();
}
```

Do not pass an arbitrary sort string from the client directly into SQL. Use valid entity properties and bound page size and depth. If using `DatabaseClient` with custom SQL, apply an identifier allowlist as shown earlier.

## 21. Stored Procedures and Functions Also Need Binding

When calling stored procedures or functions, input values must still be passed via parameter binding. Do not concatenate input into a `CALL` statement or function expression:

```java
return databaseClient.sql("SELECT * FROM search_customers(:keyword)")
        .bind("keyword", keyword)
        .map((row, metadata) -> mapCustomer(row))
        .all();
```

Parameter binding protects the boundary between the value and the call statement. However, the stored procedure itself must also avoid unsafe dynamic SQL internally. If the procedure uses `EXECUTE`/dynamic SQL by concatenating input, injection can still happen on the database side.

Inspect procedure code, execution privileges, and database role permissions. Do not treat calling a stored procedure as automatic immunity against SQL injection.

## 22. Parameter Binding Does Not Replace Authorization

A SQL statement with bound parameters can still allow a user to read or modify data they are not authorized to access if ownership/tenant conditions are missing. For example:

```java
return databaseClient.sql("DELETE FROM orders WHERE id = :id")
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
```

The statement has no SQL injection, but without checking that the user owns the order, they can delete someone else's order simply by changing the ID.

Include the authorization scope in the query:

```java
return databaseClient.sql("""
        DELETE FROM orders
        WHERE id = :id
          AND tenant_id = :tenantId
        """)
        .bind("id", orderId)
        .bind("tenantId", authenticatedTenantId)
        .fetch()
        .rowsUpdated();
```

`authenticatedTenantId` must come from a server-verified principal/context; never trust a tenant ID declared by the client. Binding prevents injection; authorization and tenant isolation protect access rights. You need both.

## 23. Checking Data Types and Input Limits

Parameter binding does not automatically validate business data. Overly long strings, negative numbers, out-of-range dates, or huge page sizes can still cause errors or excessive load.

Validate before binding:

- Strings: maximum length, format, and normalization rules.
- Numbers: min/max, precision/scale, and overflow.
- IDs: range and ownership.
- Dates/times: timezone and allowed time range.
- Lists: maximum element count, deduplication if appropriate.
- Pagination: bounded page size and offset.
- LIKE patterns: bounded length and wildcard semantics.

Binding prevents values from being parsed as SQL, but does not stop a valid query from consuming excessive resources. Validation, authorization, rate limiting, and query limits remain necessary.

## 24. Safe Logging and Error Handling

Do not log SQL parameters containing passwords, tokens, payment details, or personal data in full. SQL logs can be useful for debugging, but you must:

- Mask or omit sensitive values.
- Use a query name/operation label instead of recording the entire payload.
- Never return stack traces or internal SQL to HTTP clients.
- Log a correlation ID to link requests with database errors.
- Distinguish syntax, constraint, timeout, and connection errors.
- Control log access permissions and retention period.

When binding values, the driver or instrumentation may still record parameters depending on configuration. Check logs in real environments; never assume parameter binding automatically redacts sensitive data.

## 25. Testing SQL Injection Prevention

Tests should prove that malicious input is treated as literal data and does not alter query scope. For a search method:

```java
@Test
void treatsSqlInjectionPayloadAsLiteralValue() {
    String payload = "' OR '1'='1' --";

    StepVerifier.create(customerRepository.findByEmail(payload))
            .verifyComplete();
}
```

This test assumes the database has no email equal to the payload. An empty result proves the payload did not turn into an always-true condition. A complementary test should save that string into a text column (if the schema allows), read it back, and confirm it was stored verbatim.

Integration tests should use the same database/driver as production, such as PostgreSQL via Testcontainers if the application deploys on PostgreSQL. Mocking a repository does not prove that the driver and SQL binding actually behave as expected.

Test cases should include:

1. Strings containing single quotes and double quotes.
2. Payloads containing `OR 1=1`, comment markers `--`, or semicolons.
3. Unicode strings and Vietnamese characters.
4. Null values via `bindNull`.
5. `IN` lists that are empty, small, and at the maximum limit.
6. Valid and invalid sort fields and directions.
7. `LIKE` queries containing `%`, `_`, and the escape character.
8. A valid ID belonging to another tenant to verify authorization.
9. Stored data reused in dynamic queries to detect second-order injection.

## 26. Testing with `DatabaseClient` and `StepVerifier`

Example test verifying a payload does not widen results:

```java
@Test
void searchDoesNotInterpretKeywordAsSql() {
    String malicious = "' OR '1'='1' --";

    StepVerifier.create(customerSearchService.findByEmail(malicious))
            .verifyComplete();
}
```

With fixture data containing one valid customer:

```java
@Test
void exactSearchReturnsOnlyMatchingCustomer() {
    StepVerifier.create(customerSearchService.findByEmail("an@example.com"))
            .assertNext(customer ->
                    assertThat(customer.email()).isEqualTo("an@example.com"))
            .verifyComplete();
}
```

To test a sort allowlist, pass an invalid identifier such as `email; DROP TABLE customer` and verify the service rejects it before the query executes. Do not just inspect the final SQL string in unit tests; integration tests verify behavior against a real database.

## 27. Common Mistakes

| Mistake | Risk | Remedy |
| --- | --- | --- |
| Concatenating input into SQL with `+` or `StringBuilder` | Input can become SQL syntax | Use placeholders and binding |
| Manually escaping quotes | Wrong escaping for dialect/context | Let the driver bind values |
| Using placeholders for table/column names | Invalid SQL or uncontrolled identifiers | Use an identifier allowlist |
| Binding `ASC`/`DESC` strings | Does not select sort direction as expected | Use an enum/allowlist and fixed SQL fragments |
| Letting clients send arbitrary SQL operators | Can inject syntax into dynamic queries | Map enums to fixed operators |
| Building `IN` by concatenating lists | Injection and formatting bugs | Use collection expansion or safe bind markers |
| Not handling empty lists | `IN ()` SQL can fail | Return empty or handle as a separate branch |
| Using `bind(name, null)` | Binding error | Use `bindNull(name, type)` |
| Assuming binding strips `LIKE` wildcards | Search results broader than expected | Escape `%`/`_` when literal matching is needed |
| Binding without validating page size | Valid queries can still cause heavy load | Limit size and duration |
| Binding at insert, concatenating stored data later | Second-order SQL injection | Bind every time data is used in SQL |
| Thinking binding replaces authorization | Users can still access unauthorized data | Add ownership/tenant conditions and permission checks |
| Logging all bind values | Exposure of sensitive data | Mask/redact and restrict log access |
| Testing only with mocks | Fails to verify real driver/database behavior | Run integration tests with a production-compatible database |

## 28. Workflow for Building Safe Queries

When writing a query that takes input data, follow this order:

1. Write the fixed SQL structure first, marking every value position with a placeholder.
2. Identify which inputs are values and which are identifiers/keywords.
3. Bind every value using `DatabaseClient`, repository `@Query`, or `Statement.bind`.
4. For dynamic identifiers, map input through an allowlist and concatenate only application-controlled fragments.
5. For dynamic conditions, use `Criteria`/query builders or fixed fragments; never concatenate raw input.
6. Handle `IN` collections, empty lists, and element count limits.
7. Use `bindNull` for SQL `NULL` with the appropriate Java type.
8. Validate format, length, range, and access permissions before querying.
9. Check `LIKE` wildcards, sorting, pagination, and second-order injection.
10. Do not log sensitive bind values; handle database errors with safe responses.
11. Write unit tests for allowlists and integration tests with injection payloads against a real database/driver.

## 29. Practical Guidelines

- Never concatenate input values into SQL text.
- Use `DatabaseClient.bind`, repository derived queries/`@Query`, or R2DBC SPI `Statement.bind` for every value.
- Use `bindNull` when sending SQL `NULL`; never pass `null` to regular `bind`.
- Remember that `DatabaseClient` named parameters are translated to driver markers; direct SPI usage must use the driver's native markers.
- Bind values; never bind table names, column names, keywords, operators, or SQL clauses.
- Use allowlists for sort fields, directions, identifiers, and dynamic operators.
- Use `Criteria` or typed query builders for dynamic filters.
- Use Spring-supported collection expansion for `IN`, handle empty lists, and limit collection size.
- Escape `LIKE` wildcards when literal matching is needed; binding remains the SQL injection defense.
- Validate data and access rights; parameter binding does not replace authorization or rate limiting.
- Treat previously stored data as untrusted when used in dynamic SQL.
- Do not write custom string escape/sanitize functions to replace bind parameters.
- Do not log passwords, tokens, or sensitive values inside bind parameters.
- Test malicious payloads, identifier allowlists, nulls, collections, and tenant isolation on a production-compatible database.

## 30. Conclusion

Parameter binding is the foundational defense against SQL injection in Spring Data Relational R2DBC. Write SQL with placeholders and pass data through `DatabaseClient.bind`, repository `@Query` parameters, or R2DBC SPI `Statement.bind`. The driver receives values separately from the SQL structure, so quotes, comment markers, or SQL-like strings cannot turn into part of the command.

Binding protects value positions only. Table names, column names, sort directions, operators, and dynamic SQL fragments must be controlled via allowlists or typed query builders. Combining binding with validation, authorization, query limits, safe logging, and integration tests on real drivers/databases builds strong protection for reactive data operations.
