# SpEL Expressions in Queries and Trust Boundaries for Data

## 1. What is SpEL used for in Spring Data R2DBC queries?

Spring Data R2DBC lets you declare SQL directly on repository methods with the **@Query** annotation. Normally, input values are passed through bind parameters:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :status
    """)
Flux<Customer> findByStatus(@Param("status") String status);
~~~

This works for most queries. However, sometimes the value to bind needs to be extracted from a nested property, normalized, or computed from a parameter before being sent to the database. Spring Data supports the **Spring Expression Language (SpEL)** inside query strings to express such computations.

For example, a method receives a filter object instead of multiple individual parameters:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#filter.status}
    """)
Flux<Customer> findByFilter(@Param("filter") CustomerFilter filter);
~~~

The expression **:#{#filter.status}** reads the status property from the filter parameter. Spring Data evaluates the expression and binds the result as a value for the SQL statement.

SpEL in queries is useful when you need to compute **data values** before binding. It is not a mechanism for substituting table names, column names, or arbitrary SQL fragments. Clearly distinguishing data values from SQL structure is an essential boundary for keeping queries safe and controllable.

## 2. How to write SpEL expressions in @Query

In Spring Data query strings, a SpEL expression can be placed inside a bind marker in the form:

~~~text
:#{expression}
~~~

The part after the colon is evaluated to produce the bound value. The colon serves as the bind marker; the expression is not interpreted as a user-supplied SQL fragment.

### 2.1. Accessing parameters by position

Method parameters can be accessed using 0-based indices:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE email_address = :#{[0]}
    """)
Mono<Customer> findByEmailWithExpression(String email);
~~~

In the example, **[0]** is the first method parameter. Positional access is concise, but when a method has several parameters, readers have a harder time seeing which parameter is being referenced.

### 2.2. Accessing parameters by name

You can name a parameter with **@Param** and reference it in SpEL:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#status}
    """)
Flux<Customer> findByStatusExpression(
        @Param("status") String status
);
~~~

The expression **#status** references the method parameter named status. This style is usually easier to read than positional indices, especially in long queries.

Use **@Param** whenever a query relies on parameter names to make the link between SQL and the method signature explicit. This also avoids unnecessary dependence on whether Java parameter names are preserved in bytecode.

### 2.3. Accessing nested properties

SpEL can read properties from an object passed to the method:

~~~java
public record CustomerFilter(
        String status,
        String city
) {}
~~~

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#filter.status}
      AND city = :#{#filter.city}
    """)
Flux<Customer> search(
        @Param("filter") CustomerFilter filter
);
~~~

Here, **#filter.status** and **#filter.city** extract two values from the filter object. The SQL still has a fixed structure; only the condition values are obtained from the object.

If the parameter or nested properties can be null, clarify the business meaning. Do not assume that accessing a null property automatically turns the SQL condition into a skipped filter.

## 3. SpEL computes values before binding

SpEL expressions can perform simple computations to produce a value for a bind marker.

Example normalizing status to uppercase:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#status.toUpperCase()}
    """)
Flux<Customer> findByNormalizedStatus(
        @Param("status") String status
);
~~~

If the parameter is **"active"**, the value is evaluated to **"ACTIVE"** before binding. The database still receives a parameter value; it does not receive a SQL fragment concatenated from the status string.

You can use a conditional operator to pick a default value:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :#{#status == null ? 'ACTIVE' : #status}
    """)
Flux<Customer> findByStatusOrDefault(
        @Param("status") String status
);
~~~

The expression above chooses ACTIVE when the parameter is null. Only use a default when that is genuinely the business rule. If null means the caller does not want to filter by status, design the query to omit the condition instead of choosing a default status.

SpEL has broad expressive power. However, queries should keep expressions short, readable, and testable. If logic starts involving multiple branches, multiple method calls, or external state, compute the value in the service layer and pass a plain parameter into the repository.

## 4. Combining SpEL with bind parameters

### 4.1. Dynamic values are still data

Suppose an API searches customers by status and city. The caller supplies these values from an HTTP query string. A repository method can take a filter and use SpEL to extract each value:

~~~java
public record CustomerSearch(
        String status,
        String city
) {}
~~~

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :#{#search.status}
      AND city = :#{#search.city}
    ORDER BY id
    """)
Flux<Customer> search(
        @Param("search") CustomerSearch search
);
~~~

The status and city strings are still passed as bound values. Callers can change the input data, but cannot alter the SQL structure simply by putting SQL characters inside those values.

### 4.2. Do not concatenate user data into query strings

Do not build queries via string concatenation:

~~~java
String sql = "SELECT * FROM customers WHERE status = '"
        + requestStatus + "'";
~~~

If requestStatus contains quote characters and SQL syntax, the query can be altered unintentionally. This is a classic SQL injection flaw.

Use bind parameters instead:

~~~java
databaseClient.sql("""
        SELECT id, name, status
        FROM customers
        WHERE status = :status
        """)
    .bind("status", requestStatus)
    .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            null,
            row.get("status", String.class)
    ))
    .all();
~~~

Or use a repository query with **:#{#status}** if you need an expression to extract or compute the value. Both approaches keep values separate from the SQL statement structure.

### 4.3. Bind parameters do not substitute identifiers

Bind markers are for **data values**, not for replacing table names, column names, or SQL keywords.

The following example does not dynamically choose a column as intended:

~~~sql
SELECT id, name
FROM customers
ORDER BY :sortColumn
~~~

When binding sortColumn = **'created_at'**, the database sees a parameter value, not a column identifier. The results may not sort by the intended column.

Likewise, do not use SpEL as a way to take a table name from a request and splice it directly into SQL. If dynamic identifier selection is truly needed, map the user's choice to a fixed set of identifiers controlled by the application.

## 5. Distinguishing data, identifiers, and SQL structure

To maintain clear trust boundaries, distinguish three categories of input:

| Category | Examples | Handling |
|---|---|---|
| Data values | email, status, customer ID, creation date | Use bind parameters; SpEL may compute the value before binding |
| Identifiers | table name, column name, schema, sort column | Use mapping metadata or pick from a fixed allowlist |
| SQL structure | JOIN, WHERE, ORDER BY, operators, clauses | Declare statically in the query or build with a controlled query API |

Example:

~~~sql
SELECT id, email_address
FROM customers
WHERE status = :status
ORDER BY created_at DESC
~~~

- **customers**, **email_address**, **status**, and **created_at** are identifiers determined by the application.
- **:status** is the bind slot for a data value.
- SELECT, FROM, WHERE, and ORDER BY are fixed SQL structure.

SpEL helps compute values at bind positions. It does not make an arbitrary string into a safe identifier.

## 6. Dynamic sorting and safe column selection

A common requirement is letting clients choose the sort column. Never place raw strings from a request into SQL:

~~~java
String sql = "SELECT id, name FROM customers ORDER BY "
        + request.getSort();
~~~

A user could send an unintended expression instead of a column name. Because identifiers cannot be bound like values, the safe approach is an allowlist.

Example:

~~~java
enum CustomerSort {
    NAME,
    CREATED_AT
}
~~~

~~~java
String orderBy = switch (sort) {
    case NAME -> "name";
    case CREATED_AT -> "created_at";
};

String sql = "SELECT id, name FROM customers ORDER BY " + orderBy;
~~~

Here, the fragment appended to SQL can only be one of two fixed identifiers decided by code. If external input is a string, parse it into an enum or look it up in an allowlist map; invalid values must be rejected or mapped to a defined default.

With Spring Data Relational's Criteria/Query API, you can build Sort from controlled choices. Whichever API you choose, never allow raw identifiers from a request to pass directly into SQL.

## 7. SpEL and tenant- or current-user-scoped data

In multi-tenant applications, many queries must restrict data to the current tenant. Crucially, **the source of the tenant ID must be trustworthy**, and the tenant predicate must be applied on every relevant data access path.

Example of a repository taking tenant ID as an explicit parameter:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE tenant_id = :#{#tenantId}
      AND id = :#{#customerId}
    """)
Mono<Customer> findForTenant(
        @Param("tenantId") UUID tenantId,
        @Param("customerId") Long customerId
);
~~~

This clearly shows the tenant condition in the query. However, binding tenantId does not itself verify whether the caller is authorized to access that tenant. The service or security layer must obtain the tenant from the authenticated identity and verify permissions, then pass the verified value to the repository.

Do not treat a tenant ID sent by a client in a request body or query string as trustworthy simply because it is safely bound. Parameter binding protects SQL structure; it is not an authorization check.

A proper workflow:

1. Authenticate the request and user identity.
2. Determine the tenant from the security context or a trusted data source.
3. Verify the user is permitted to access that tenant.
4. Pass the verified tenant ID to the service/repository.
5. Apply the tenant condition in every query that needs data isolation.
6. Test to ensure users cannot read or modify another tenant's data.

If the application uses a context mechanism or evaluation-context extension to expose principal/tenant to SpEL, clearly configure the data source, scope, and access permissions. Expose only necessary, read-only, verified values. Do not open the evaluation context to arbitrary business bean calls or secret access.

## 8. Do not use SpEL as an authorization mechanism

SpEL can help retrieve a tenant ID, user ID, or attribute from a configured context. Yet expressions do not replace permission checks.

For example:

~~~text
WHERE tenant_id = :#{#tenantId}
~~~

only limits results by the supplied tenantId value. It does not prove that the value belongs to the current user.

If a service accepts tenantId from a request without verification, a user can change tenantId and access out-of-scope data. Even though the query uses bind parameters and has no SQL injection, an authorization vulnerability still exists.

Separate three responsibilities:

- **Authentication:** identifying who the caller is.
- **Authorization:** determining what the caller is allowed to do and which data they may access.
- **Parameter binding:** passing values safely into SQL, separate from the statement structure.

A secure system requires all three. Never use one to replace the other two.

## 9. Be cautious with complex expressions and evaluation contexts

SpEL is an expression language capable of accessing properties, invoking methods, and evaluating conditions. Inside queries, expressions should be authored by developers and perform only the computations necessary for parameters.

Principles to follow:

- Write static expressions in source code or developer-controlled configuration.
- Never take raw SpEL strings from HTTP requests, messages, or user data and evaluate them.
- Never let users dictate which beans, methods, or classes are referenced in an expression.
- Limit which objects are placed into the evaluation context.
- Prefer explicit method parameters over implicit reliance on global context.
- Move complex business logic to the service or domain layer.
- Verify expression behavior on the Spring Data version in use.

If the application configures custom evaluation context extensions or beans referenced from SpEL, treat that as a managed execution surface. Provide only necessary data and functions; avoid exposing beans capable of performing writes, making network calls, or accessing sensitive resources.

## 10. Handling nulls and optional conditions

A filter field may not be provided. Distinguish the possible meanings:

- Do not filter by that field.
- Find only rows with a SQL NULL value.
- Use a default value.
- Reject the request for missing required data.

These meanings lead to different SQL.

### 10.1. Do not use = NULL to find null values

In SQL, the comparison **column = NULL** does not evaluate to true. To find null values, you must use **IS NULL**.

Fixed query example for the null case:

~~~sql
SELECT id, name
FROM customers
WHERE city IS NULL
~~~

If you want an optional condition, you can write a query with explicit logic:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE (:#{#status} IS NULL OR status = :#{#status})
    """)
Flux<Customer> findByOptionalStatus(
        @Param("status") String status
);
~~~

When status is null, the first branch is true and the status filter is skipped. When status has a value, the query filters by status. Check how null binding and driver/dialect data types behave in your version; for complex queries, you can build dynamic queries using Criteria to express conditions cleanly.

### 10.2. Null is not the same as an empty string

**NULL**, **''**, and whitespace-only strings are distinct values. Do not automatically use SpEL to collapse all cases into the same value if business rules need to distinguish them.

You can normalize in the service before calling the repository:

~~~java
String normalizedStatus =
        status == null || status.isBlank()
                ? null
                : status.trim().toUpperCase(Locale.ROOT);
~~~

Then pass the normalized value as a bind parameter. This makes the logic easy to unit test and avoids cluttering query expressions.

## 11. LIKE, wildcards, and the meaning of input data

Bind parameters prevent input strings from becoming SQL syntax, but do not strip the wildcard meaning of LIKE.

Example:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE name LIKE :pattern
    """)
Flux<Customer> searchByNamePattern(
        @Param("pattern") String pattern
);
~~~

If pattern is **%an%**, the database finds strings containing an. The characters **%** and **_** are LIKE wildcards. This is not SQL injection, though it can yield broader results than the user intended.

If business logic needs literal string matching, escape wildcards according to the database's rules and declare an appropriate ESCAPE clause. You can construct the escaped pattern in the service and bind it. Test inputs containing %, _, and the escape character.

## 12. SpEL in queries vs. computation in the service layer

Not every parameter calculation belongs in SpEL. Choose where to place it based on complexity and responsibility:

| Need | Usually appropriate approach |
|---|---|
| Passing a method parameter directly | Standard bind parameter |
| Reading properties from a filter object | Short SpEL in a bind marker or separate parameters |
| Simple string normalization | Service layer or short SpEL, per convention |
| Multi-branch logic needing dedicated unit tests | Service/domain layer |
| Obtaining authenticated tenant/user | Security/service layer, passed as an explicit parameter |
| Selecting table/column names | Mapping metadata or identifier allowlist |
| Building complex JOIN/WHERE from many conditions | Criteria/Query or controlled query builder |
| Running different SQL per database | Separate dialect-specific repositories/queries |

SpEL is meant to reduce query boilerplate, not become the primary business logic language. When an expression grows longer than the SQL statement or becomes hard to explain, compute the value beforehand and pass it to the repository via a clearly named parameter.

## 13. Complete example: tenant-scoped filter query

Suppose an application has a customers table with columns tenant_id, id, name, city, and status. The filter is declared as:

~~~java
public record CustomerFilter(
        UUID tenantId,
        String status,
        String city
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, tenant_id, name, city, status
        FROM customers
        WHERE tenant_id = :#{#filter.tenantId}
          AND (:#{#filter.status} IS NULL
               OR status = :#{#filter.status})
          AND (:#{#filter.city} IS NULL
               OR city = :#{#filter.city})
        ORDER BY id
        """)
    Flux<Customer> search(
            @Param("filter") CustomerFilter filter
    );
}
~~~

The service is responsible for obtaining the tenant from the authenticated identity and building the filter:

~~~java
public Flux<Customer> search(
        AuthenticatedUser user,
        CustomerSearchRequest request) {

    UUID authorizedTenantId = tenantAccess.requireTenant(user);

    CustomerFilter filter = new CustomerFilter(
            authorizedTenantId,
            normalizeStatus(request.status()),
            normalizeCity(request.city())
    );

    return customerRepository.search(filter);
}
~~~

**tenantAccess.requireTenant(user)** represents the application's authorization logic. It is not a built-in Spring API; it illustrates the responsibility that must be fulfilled before calling the repository.

In this example:

- The SQL structure is written statically.
- tenantId, status, and city are bound as values.
- SpEL only extracts properties from the filter object.
- The tenant ID comes from the security/service layer after verification.
- The client cannot choose a tenant merely by sending tenantId in the request.
- The query returns **Flux<Customer>** since multiple results are possible.

For more complex filters, you can use the Criteria API to add conditions only when values exist. This is often easier to read than a query full of null branches.

## 14. Testing SpEL and data boundaries

Tests should verify both that expressions read the right values and that input data cannot alter SQL structure.

### 14.1. Verifying parameters are read properly

Use integration tests with a compatible database to invoke the repository with various filters:

- Non-null status.
- Null status to skip the condition.
- Filters with nested properties.
- Strings with Vietnamese diacritics or special characters.
- No matching rows.

This confirms Spring Data evaluates SpEL and binds values using types supported by the driver.

### 14.2. Verifying SQL-injection-like strings are treated as data

Example input:

~~~text
' OR 1=1 --
~~~

When passed via a bind parameter, this string must be treated as an ordinary search value rather than altering the WHERE clause. You can write an integration test with controlled data to confirm the query does not return the entire table just because the string contains SQL syntax.

### 14.3. Verifying authorization independently

Test the following cases:

- A user in tenant A can only read tenant A's data.
- Changing the tenant ID in a request does not allow accessing tenant B.
- Update/delete queries also enforce the tenant predicate.
- Another repository method does not accidentally omit the tenant condition.
- Unauthorized users are rejected before the query runs or receive no out-of-scope data.

Do not test only one search query. Tenant boundaries must be enforced consistently across all operations that read or modify data.

### 14.4. Testing nulls, wildcards, and identifiers

In addition to normal values, test:

- NULL versus empty string.
- **%** and **_** characters in LIKE.
- Unicode values and quotation marks.
- Sort keys outside the allowlist.
- Invalid column/table names rejected before generating SQL.

## 15. Common errors when using SpEL in queries

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot resolve parameter name | Name in expression does not match method parameter | Use **@Param** and reference **#parameterName** |
| Property access error | Object or nested property is null/missing | Validate input; use null-safe logic or normalize in the service |
| Cannot convert bound type | Expression returns a type incompatible with column/driver | Check target type and convert before binding |
| Query gives wrong results on null input | Used **column = NULL** under SQL semantics | Use **IS NULL** or explicit optional conditions |
| ORDER BY does not change with parameter | Attempted to bind a column name as a value | Use an identifier allowlist or Criteria Sort |
| SQL injection despite SpEL | Spliced expression result into SQL structure or concatenated input | Use expressions only inside bind markers; never build raw SQL from input |
| User reads another tenant's data | Client-controlled tenant ID or missing predicate | Get tenant from verified identity and enforce authorization |
| Query becomes hard to maintain | Expression contains too much business logic | Move computation to the service/domain layer |
| Query behaves differently across environments | Different driver/dialect or Spring Data version | Integration test with a real database/driver |

## 16. Pre-production checklist for SpEL queries

1. Decide whether an expression is truly necessary or standard bind parameters suffice.
2. Keep expressions short and developer-controlled.
3. Use **@Param** to name parameters clearly.
4. Place SpEL inside bind markers so results are used as data values.
5. Never use bind markers or SpEL as a way to substitute table/column names.
6. Never concatenate raw input into SQL or expression text.
7. Use an allowlist when selecting dynamic identifiers or sort keys.
8. Obtain user/tenant identity from a verified source and check authorization separately.
9. Define explicit semantics for null, empty strings, and wildcards.
10. Move complex logic to the service layer or Criteria API.
11. Test with the real database and R2DBC driver.
12. Test both the SQL injection boundary and the authorization boundary.

## 17. Conclusion

SpEL in Spring Data R2DBC queries helps extract or compute values from method parameters and filter objects directly within the query string. When using expressions like **:#{...}**, Spring Data evaluates the expression and uses the result as a bound value. This is helpful for nested parameters or minor computations while keeping the SQL structure statically declared.

A trustworthy data boundary rests on separating values from SQL structure. Bind parameters protect values from being interpreted as SQL syntax, but cannot substitute table/column names and do not perform authorization. Dynamic identifiers require allowlists; tenant/user identities must come from verified sources and undergo authorization checks before querying.

Keep SpEL short, never evaluate user-supplied expressions, avoid exposing overly broad evaluation contexts, and test nulls, wildcards, tenant isolation, and real databases. These practices keep declared queries flexible while maintaining clear security boundaries.
