# Binding Parameters to Prevent SQL Injection and Controlling Dynamic SQL

Spring Data JDBC and Spring JDBC allow passing values into SQL statements using bind parameters. When used properly, the driver sends the statement and the data separately, ensuring the database treats input as a **value** rather than part of the SQL syntax. This is the fundamental defense against SQL injection.

However, bind parameters only apply to values such as IDs, emails, statuses, dates, or monetary amounts. They cannot replace table names, column names, operators, ORDER BY keywords, or ASC/DESC directions. Those dynamic parts of SQL must be built from a fixed set of choices and validated before being included in the statement.

This lesson explains how to bind parameters in repository queries, JdbcTemplate, and NamedParameterJdbcTemplate; how to build dynamic filters, sorting, and pagination safely; and which pitfalls to avoid when handling LIKE, NULL, and IN lists.

## 1. How Does SQL Injection Happen?

SQL injection occurs when untrusted input is concatenated directly into a SQL string and the database interprets part of that data as syntax.

Example finding a customer by email:

~~~java
String sql =
        "SELECT id, email FROM customers WHERE email = '"
        + email
        + "'";

Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

If email is a normal value, the SQL may run fine. But if the input contains a snippet like:

~~~text
' OR '1'='1' --
~~~

the resulting SQL string can alter the WHERE condition. An attacker can cause the query to return more rows than intended or change the statement's meaning.

The problem lies in mixing data with SQL syntax before the database parses the statement.

## 2. Using PreparedStatement and Bind Parameters

With JDBC, write SQL with placeholders and bind data through PreparedStatement:

~~~java
String sql =
        "SELECT id, email FROM customers WHERE email = ?";

try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

    statement.setString(1, email);

    try (ResultSet result = statement.executeQuery()) {
        // Read results.
    }
}
~~~

The database receives the statement structure with a placeholder. The email value is sent separately through the JDBC parameter API. Even if email contains quotes or SQL-like text, it is still treated as parameter data.

Benefits:

- No manual quote escaping in values.
- No concatenating user data into SQL strings.
- The driver can bind the proper JDBC type.
- SQL statements and values are clearly separated.
- The same statement shape can be reused with different values.

Do not add quotes around placeholders. Write WHERE email = ? rather than WHERE email = '?'. The driver handles representing the value according to the JDBC protocol.

## 3. Spring Data JDBC Repository Queries Bind Values Automatically

For derived queries, Spring Data JDBC generates the SQL from the method name and binds the parameters:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndActive(
            String status,
            boolean active
    );
}
~~~

The email, status, and active values are passed through the repository infrastructure's parameter binding mechanism. No SQL string concatenation is needed.

With @Query, write fixed SQL and use named parameters:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, display_name, email, status
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findCustomerByEmail(
            @Param("email") String email
    );
}
~~~

The parameter name :email maps to the method argument annotated with @Param("email"). The value is bound, not concatenated into the SQL.

You can use @Query for DML as needed:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

@Modifying indicates that the query modifies data. It is not a standalone injection defense; value protection comes from parameter binding.

Never construct SQL by concatenating arguments into annotations or building query strings from request data.

## 4. Binding Parameters with JdbcTemplate

JdbcTemplate uses PreparedStatement underneath. Pass values through placeholders:

~~~java
String sql = """
    SELECT id, display_name, email
    FROM customers
    WHERE email = ?
    """;

List<CustomerSummary> customers = jdbcTemplate.query(
        sql,
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        ),
        email
);
~~~

If you need control over how binding happens, use PreparedStatementSetter:

~~~java
List<CustomerSummary> customers = jdbcTemplate.query(
        sql,
        ps -> ps.setString(1, email),
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        )
);
~~~

For updates:

~~~java
int affected = jdbcTemplate.update(
        "UPDATE customers SET status = ? WHERE id = ?",
        status,
        customerId
);
~~~

Do not concatenate customerId or status into the SQL string. Even when an ID is an integer, bind it as a parameter to maintain a consistent rule and prevent bugs if the type changes.

## 5. Using NamedParameterJdbcTemplate for Multi-Parameter Queries

When there are many conditions, positional placeholders become hard to read because you must track their order. NamedParameterJdbcTemplate lets you name parameters:

~~~java
String sql = """
    SELECT id, display_name, status
    FROM customers
    WHERE status = :status
      AND created_at >= :fromTime
      AND created_at < :toTime
    """;

var parameters = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("fromTime", fromTime)
        .addValue("toTime", toTime);

List<CustomerSummary> result =
        namedParameterJdbcTemplate.query(
                sql,
                parameters,
                customerSummaryRowMapper
        );
~~~

Named parameters help you:

- Clearly see which value belongs to each condition.
- Add or reorder conditions without counting question marks.
- Bind data types via the Spring JDBC API.
- Pass collections for certain forms of IN clauses.

Parameter names remain part of the developer-written SQL template. Supplied values are bound separately.

## 6. Bind Values Cannot Replace Table or Column Names

A common misconception is using placeholders for identifiers:

~~~sql
SELECT * FROM ? WHERE id = ?
~~~

The first placeholder cannot represent a table name. PreparedStatement binds values, not SQL structural elements such as table names, column names, operators, or keywords.

Similarly, the statement:

~~~sql
SELECT id, name
FROM customers
ORDER BY ?
~~~

does not tell the database to sort by the passed column name. A parameter in that position is an expression value, not a SQL identifier.

If users can choose a sort column, map their selection to one of the identifiers defined in code. Never concatenate strings sent from the client directly.

## 7. Whitelisting for Dynamic ORDER BY

Suppose an API allows sorting by creation date, customer name, or total amount.

Create an enum representing the valid choices:

~~~java
public enum CustomerSortField {
    CREATED_AT,
    NAME,
    TOTAL
}
~~~

Convert the enum into a SQL identifier using a fixed switch:

~~~java
private String columnFor(CustomerSortField field) {
    return switch (field) {
        case CREATED_AT -> "created_at";
        case NAME -> "display_name";
        case TOTAL -> "total";
    };
}
~~~

Validate the direction:

~~~java
private String directionFor(String direction) {
    if ("asc".equalsIgnoreCase(direction)) {
        return "ASC";
    }
    if ("desc".equalsIgnoreCase(direction)) {
        return "DESC";
    }
    throw new IllegalArgumentException("Unsupported sort direction");
}
~~~

After validation, you can build the ORDER BY clause from internal constants:

~~~java
String sql = """
    SELECT id, display_name, total, created_at
    FROM customers
    ORDER BY
    """ + columnFor(sortField) + " " + directionFor(direction)
    + " LIMIT :limit OFFSET :offset";
~~~

In this example, only strings returned by the switch and validation method are appended to SQL. No arbitrary identifier value from the request reaches the statement directly.

Even better, the API can accept the enum directly instead of a String. When parsing the request, reject values outside the allowed set before calling the persistence layer.

## 8. Sorting with Spring Data Sort

When using a repository or JdbcAggregateTemplate, you can use Sort to express ordering:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Iterable<Customer> customers = repository.findAll(sort);
~~~

If the sort field comes from a query parameter, do not pass an arbitrary string directly. Map the client's choice to an allowed domain property:

~~~java
private String allowedProperty(String requested) {
    return switch (requested) {
        case "name" -> "name";
        case "created" -> "createdAt";
        case "total" -> "total";
        default -> throw new IllegalArgumentException(
                "Unsupported sort field");
    };
}
~~~

Then:

~~~java
Sort sort = Sort.by(
        Sort.Direction.DESC,
        allowedProperty(requestedSort)
);
~~~

Spring Data handles mapping properties to columns using metadata. Whitelisting is still necessary to restrict query capabilities and avoid sorting on unexposed properties.

## 9. Safe Dynamic WHERE Clauses

You can build optional filters from fixed SQL fragments and separate parameters. Example:

~~~java
StringBuilder sql = new StringBuilder("""
    SELECT id, display_name, status
    FROM customers
    WHERE 1 = 1
    """);

MapSqlParameterSource params = new MapSqlParameterSource();

if (status != null) {
    sql.append(" AND status = :status");
    params.addValue("status", status);
}

if (createdFrom != null) {
    sql.append(" AND created_at >= :createdFrom");
    params.addValue("createdFrom", createdFrom);
}

if (createdTo != null) {
    sql.append(" AND created_at < :createdTo");
    params.addValue("createdTo", createdTo);
}

List<CustomerSummary> result =
        namedParameterJdbcTemplate.query(
                sql.toString(),
                params,
                customerSummaryRowMapper
        );
~~~

Every appended fragment is a literal controlled by code. Values from the request are only added to MapSqlParameterSource.

Rules:

- SQL fragments must come from code or a whitelist.
- Values must be bound as parameters.
- Never append user strings directly into WHERE.
- Never let clients send SQL snippets as filter expressions.
- Limit the number of filters and clearly define AND/OR combinations.

For complex queries, create a query object or specification to validate inputs before building SQL.

## 10. Dynamic Filters in MyBatis

If the application also uses MyBatis, dynamic SQL elements such as if, choose, where, set, and foreach help construct parameterized conditions.

XML example:

~~~xml
<select id="search" resultType="CustomerSummary">
  SELECT id, display_name, status
  FROM customers
  <where>
    <if test="status != null and status != ''">
      AND status = #{status}
    </if>
    <if test="createdFrom != null">
      AND created_at >= #{createdFrom}
    </if>
    <if test="createdTo != null">
      AND created_at < #{createdTo}
    </if>
  </where>
  ORDER BY created_at DESC, id ASC
</select>
~~~

The #{status} syntax generates parameter binding. Never use direct string substitution in mappers with untrusted data. If dynamic identifiers are needed, use a whitelist and fixed branches in the mapper.

Although MyBatis is not the main focus of JDBC repositories, the security principle is identical: values are bound; SQL structure is chosen only from application-controlled parts.

## 11. LIKE Searches and Wildcards

Bind parameters prevent a search string from altering SQL structure, but % and _ remain wildcards under LIKE semantics.

Example:

~~~sql
WHERE display_name LIKE :pattern
~~~

If the pattern is %an%, the query can match many names containing an. This is not SQL injection, yet it can be broader than the user's intended search.

If you want literal text matching, escape wildcards before binding. You can choose ! as the escape character:

~~~java
private String literalContainsPattern(String input) {
    String escaped = input
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

    return "%" + escaped + "%";
}
~~~

SQL:

~~~sql
SELECT id, display_name
FROM customers
WHERE display_name LIKE :pattern ESCAPE '!'
~~~

Bind pattern:

~~~java
params.addValue("pattern", literalContainsPattern(searchText));
~~~

Escaping order matters: escape the ! character itself first, then escape % and _. Otherwise, the newly inserted escape characters would be escaped again.

If the application intentionally supports wildcard search, document that semantics in the API instead of letting users control patterns accidentally.

## 12. NULL Requires Separate SQL Branches

In SQL, comparing to NULL with the = operator does not yield TRUE. Example:

~~~sql
WHERE deleted_at = :deletedAt
~~~

if deletedAt is bound as NULL, the condition will not match rows where deleted_at is NULL.

To filter rows with null values, use:

~~~sql
WHERE deleted_at IS NULL
~~~

If you want an optional filter:

~~~java
if (deletedAtIsNull) {
    sql.append(" AND deleted_at IS NULL");
} else if (deletedAt != null) {
    sql.append(" AND deleted_at = :deletedAt");
    params.addValue("deletedAt", deletedAt);
}
~~~

Never construct SQL syntax by concatenating a NULL keyword sent by the client. Use a boolean/enum representing the business choice and map it to fixed SQL branches.

## 13. IN Clauses and Empty Lists

NamedParameterJdbcTemplate supports collection expansion for named parameters in an IN clause:

~~~java
String sql = """
    SELECT id, display_name
    FROM customers
    WHERE id IN (:ids)
    """;

var params = new MapSqlParameterSource()
        .addValue("ids", customerIds);

List<CustomerSummary> customers =
        namedParameterJdbcTemplate.query(
                sql,
                params,
                customerSummaryRowMapper
        );
~~~

Spring JDBC generates the matching number of placeholders for the collection. Never concatenate individual IDs into the SQL string.

Empty lists must be handled before execution. Some databases reject IN () and business semantics can vary:

- If an empty list means no customers selected, return an empty list immediately.
- If an empty list means no filter applied, omit the IN condition entirely.
- If an empty list is invalid, reject the request.

Example:

~~~java
if (customerIds == null || customerIds.isEmpty()) {
    return List.of();
}
~~~

Do not assume dropping the IN condition when the list is empty is safe. It could turn a query for selected IDs into a query returning all customers.

With positional parameters in JdbcTemplate, if a dynamic IN list is required, generate the exact number of question marks from the validated item count and bind each ID; never concatenate ID values into SQL.

## 14. Dynamic Pagination: Binding Limit and Offset

LIMIT, OFFSET, or equivalent pagination syntax usually take numeric values. You can bind them:

~~~sql
SELECT id, display_name
FROM customers
ORDER BY id
LIMIT :limit OFFSET :offset
~~~

Before querying, validate:

- limit is greater than 0.
- limit does not exceed the API's maximum allowed size.
- offset is non-negative.
- Compute offset with a sufficiently wide numeric type to prevent overflow.
- Sort fields are in the allowlist.
- ORDER BY is deterministic, usually adding a unique key as a tie-breaker.

Example:

~~~java
int pageSize = Math.min(requestedSize, 100);

if (pageSize < 1 || pageNumber < 0) {
    throw new IllegalArgumentException("Invalid page request");
}

long offset = Math.multiplyExact((long) pageNumber, pageSize);
~~~

LIMIT/OFFSET syntax varies across databases. With Spring Data repositories or the Query API, prefer Pageable so the dialect handles pagination. With custom SQL, use the syntax suited to your DBMS and bind numeric values.

## 15. Never Allow Clients to Send Raw SQL Snippets

An API must never accept a filter or sort parameter containing a SQL snippet and splice it verbatim into a query. Stripping semicolons or blacklisting certain keywords does not make a safe SQL parser.

Design the API with structured data:

~~~json
{
  "status": "ACTIVE",
  "createdFrom": "2026-01-01T00:00:00Z",
  "sortBy": "created",
  "direction": "desc",
  "page": 0,
  "size": 20
}
~~~

The application validates every field against its type and contract:

- status belongs to the valid status set.
- createdFrom parses into a valid timestamp.
- sortBy belongs to an enum/allowlist.
- direction is only ASC or DESC.
- page and size fall within bounds.
- Filters match the current user's access permissions.

Only after validation does code build the query from fixed fragments and bind the values.

## 16. Distinguishing SQL Injection from Authorization

A parameterized query can still return data a user is not allowed to see if authorization conditions are missing.

Example:

~~~sql
SELECT id, total
FROM purchase_orders
WHERE id = :orderId
~~~

The orderId parameter is safely bound, yet a user can try another person's order ID.

If view permissions depend on ownership or tenant, the query must also restrict by identity obtained from the security context:

~~~sql
SELECT id, total
FROM purchase_orders
WHERE id = :orderId
  AND tenant_id = :tenantId
~~~

tenantId must come from an authenticated/authorized context; never trust a client-supplied value just because it is safely bound.

Parameter binding protects SQL structure; authorization protects data access. Both requirements must be verified separately.

## 17. Binding the Right Data Types

Parameter binding is not just about injection prevention. It also informs the driver of the data type.

Example with NamedParameterJdbcTemplate:

~~~java
var params = new MapSqlParameterSource()
        .addValue("customerId", customerId, Types.BIGINT)
        .addValue("createdAt", createdAt, Types.TIMESTAMP)
        .addValue("total", total, Types.DECIMAL);
~~~

When values are null or have special types, specifying the JDBC type may be necessary so the driver/database handles them accurately.

Do not convert every value to String before binding. Keep Java types aligned with columns such as Long, BigDecimal, LocalDate, Instant, or UUID according to mapping and driver support.

For custom types, converters or JDBC type handlers must be tested against the target database.

## 18. Batch Updates Still Require Bound Parameters

When performing batch updates, every row must still use PreparedStatement parameters:

~~~java
String sql = """
    UPDATE customers
    SET status = ?
    WHERE id = ?
    """;

jdbcTemplate.batchUpdate(
        sql,
        customersToUpdate,
        100,
        (ps, customer) -> {
            ps.setString(1, customer.status());
            ps.setLong(2, customer.id());
        }
);
~~~

Do not build separate UPDATE statements by concatenating each item's ID and status. Batch parameter binding keeps queries safe and lets the driver optimize execution.

If a batch processes data from imported files or message brokers, still treat all values as untrusted. An internal source does not mean the data has been validated.

## 19. Practices to Avoid

| Practice | Problem | Alternative |
|---|---|---|
| Concatenating email into SQL string | SQL injection | Placeholders and bind parameters |
| Concatenating ID into WHERE | Mixes values with syntax | Bind ID with appropriate JDBC type |
| Using request string in ORDER BY | Identifiers cannot be bound; injection risk | Whitelist columns and directions |
| Using parameter for table name | Placeholders cannot represent identifiers | Pick table from fixed map/enum |
| Using direct string substitution in mappers | Injects uncontrolled SQL fragments | Bind values; whitelist structure |
| Using IN with an empty list | Can produce invalid SQL or change semantics | Handle empty lists beforehand |
| Using = NULL | Does not match SQL NULL | IS NULL/IS NOT NULL |
| Unintended wildcard concatenation | LIKE results overly broad | Escape %/_ or document wildcard semantics |
| Trusting client-supplied tenantId | Cross-tenant data exposure | Take tenant from authenticated security context |
| Filtering only dangerous keywords | Blacklists cannot parse full SQL grammar | Parameterize and whitelist |

## 20. Testing Against SQL Injection

An integration test should verify that SQL-like payloads are stored and queried as ordinary values.

Example:

~~~java
@Test
void treatsSqlLikeInputAsPlainValue() {
    String payload = "' OR '1'='1' --";

    jdbcTemplate.update(
            "INSERT INTO customers(email, display_name) VALUES (?, ?)",
            "safe@example.com",
            payload
    );

    List<CustomerSummary> result = customerRepository
            .findByDisplayName(payload);

    assertEquals(1, result.size());
    assertEquals(payload, result.get(0).displayName());
}
~~~

Adjust property/DTO names to match your repository methods and schema. The goal is to prove the payload string is bound as a value and does not alter the query condition.

Tests should cover:

- Single quotes and double quotes.
- Comment markers and semicolons.
- Long strings and Unicode characters.
- Null values.
- Empty IN lists.
- Disallowed sort fields.
- Invalid directions.
- Wildcards % and _ in LIKE.
- Tenants/users without permission to access records.
- Dynamic filters combining multiple conditions.

Do not test only a single payload. Review every place where dynamic SQL is built and verify values are bound and identifiers are whitelisted.

## 21. Safe Query Logging and Observability

During debugging, SQL logs can confirm query structure and parameter binding. However, parameters may include emails, phone numbers, tokens, addresses, or payment data.

Safe practices:

- Do not log full sensitive parameters in production.
- Mask or redact identifying data when needed.
- Limit how long detailed SQL logs remain enabled.
- Protect log access permissions and retention periods.
- Never include tokens/session secrets in exception messages.
- Use metrics/tracing to monitor latency and row counts without exposing full values.

Logging does not replace parameter binding. A safe query can still leak data if logs record all parameters.

## 22. Defense in Depth

Parameter binding is the primary defense for SQL values, and should be combined with:

1. Using a database account with least privilege.
2. Never running the application under a database admin account.
3. Validating types, lengths, and value ranges at application boundaries.
4. Whitelisting identifiers, sort fields, and dynamic SQL structures.
5. Enforcing authorization and tenant isolation.
6. Using database constraints to protect data integrity.
7. Keeping JDBC drivers and frameworks on supported versions.
8. Testing repository queries and custom SQL.
9. Never returning sensitive schema/SQL details in client exceptions.
10. Monitoring for anomalous query behavior.

Stored procedures can also suffer from SQL injection if they concatenate strings into dynamic SQL internally. Moving a query into a stored procedure does not automatically make it safe.

## 23. Safe Workflow for Building Dynamic Queries

When a use case needs optional filters, sorting, and pagination:

1. Define a request DTO with explicit types.
2. Validate values and bound input sizes.
3. Map sort fields/directions to enums or allowlists.
4. Select a SQL template or fixed fragments.
5. Bind all values via repository parameters, PreparedStatement, or NamedParameterJdbcTemplate.
6. Handle nulls and empty collections according to business semantics.
7. Escape LIKE wildcards if literal text search is intended.
8. Add authorization/tenant conditions from a trusted context.
9. Check update counts or returned results.
10. Write integration tests for payloads, filter combinations, and the target database.

~~~mermaid
flowchart TD
    A[Request filter / sort / page] --> B[Parse and validate types]
    B --> C{Sort in allowlist?}
    C -->|No| D[Reject request]
    C -->|Yes| E[Select fixed SQL fragments]
    E --> F[Bind all values]
    F --> G[Execute query]
    G --> H[Check permissions and results]
    H --> I[Return response]
~~~

## 24. Key Principles to Remember

- SQL injection occurs when untrusted data is concatenated into SQL structure.
- Use PreparedStatement, repository parameter binding, JdbcTemplate, or NamedParameterJdbcTemplate to bind every value.
- In Spring Data JDBC, derived queries and @Query bind method arguments; never concatenate arguments into SQL strings.
- Bind parameters replace values, never table names, column names, operators, or ORDER BY directions.
- Dynamic identifiers must be selected from a fixed whitelist/enum/map.
- Dynamic WHERE clauses only append code-controlled fragments; values are always bound.
- With LIKE, % and _ remain wildcards; escape them when literal text matching is required.
- Handle NULL with IS NULL/IS NOT NULL and define optional filter semantics clearly.
- For IN lists, handle empty collections before running the query.
- Bound page sizes, offsets, and sort fields; prefer Pageable when the framework can generate dialect-specific pagination.
- Bind proper JDBC types, especially for nulls and specialized types.
- Parameter binding does not replace authorization, tenant isolation, or database least privilege.
- SQL inside stored procedures and batch jobs still requires strict control.
- Test SQL-like payloads, dynamic sorting, LIKE, NULL, empty lists, and data access permissions.

Parameter binding draws a clear boundary between SQL structure and input data. In Spring Data JDBC, prefer derived queries, Criteria, or @Query with parameter binding; when dynamic SQL is necessary, construct structure solely from fixed fragments and whitelists. Combine these practices with authorization, least-privilege database accounts, and integration tests to keep queries both flexible and secure.

## References

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
