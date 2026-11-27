# SpEL and EvaluationContextExtension Within Supported Scope

## 1. How does SpEL help custom SQL queries?

Spring Data JDBC lets you declare SQL directly using `@Query`. In many cases, a query needs a value taken from method parameters or from the application context, such as the current tenant or authenticated user information.

You can pass those values as ordinary named parameters:

```java
@Query("SELECT * FROM customers WHERE status = :status")
List<Customer> findByStatus(@Param("status") String status);
```

When parameter values need to be computed by an expression, Spring Data supports **Spring Expression Language (SpEL)** in expression positions supported by query methods. For example:

```java
@Query("SELECT * FROM customers WHERE status = :#{#status}")
List<Customer> findByStatusWithExpression(
        @Param("status") String status
);
```

The expression `:#{#status}` is evaluated to a value, which is then bound as a SQL parameter. It does not mean SpEL is permitted to arbitrarily substitute table names, column names, or raw SQL fragments.

`EvaluationContextExtension` extends the evaluation context used when evaluating SpEL. This lets expressions access application-provided values, such as the current tenant or part of the authenticated principal. This mechanism is useful when the same context is needed across many query methods.

This lesson focuses on the scope of using SpEL in Spring Data JDBC query methods:

- Passing and transforming parameter values with SpEL.
- Providing a root object via `EvaluationContextExtension`.
- Using tenant or security context in a controlled way.
- Distinguishing parameter binding from dynamic SQL concatenation.
- Recognizing limitations and when to use explicit parameters, application services, or custom SQL.

## 2. SpEL in @Query: expressions produce parameter values

SpEL is Spring's expression language. In Spring Data repository queries, expressions are placed inside placeholders using `:#{...}` syntax when using named parameters, or the corresponding expression form supported by the query parser.

Example:

```java
@Query("""
    SELECT *
    FROM customers
    WHERE email = :#{#email.trim().toLowerCase()}
    """)
Optional<Customer> findByNormalizedEmail(
        @Param("email") String email
);
```

If `email` is a string with whitespace and uppercase letters, the expression computes the trimmed, lowercased value before binding. The equivalent SQL intent is:

```sql
SELECT *
FROM customers
WHERE email = ?;
```

The value computed by SpEL is passed separately to the JDBC driver. It is never concatenated directly into the SQL string.

### 2.1. Accessing method parameters

In expressions, `#` references variables. Method parameters can be referenced by discovered parameter name or parameter index according to Spring Data's evaluation context mechanism:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE customer_id = :#{#customerId}
      AND status = :#{#status}
    """)
List<PurchaseOrder> findForCustomer(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

For simple queries, the following style is usually easier to read:

```java
@Query("""
    SELECT *
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    """)
List<PurchaseOrder> findForCustomer(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

Prefer plain named parameters when you only need to pass a value through. SpEL is useful when you need computation or data from the evaluation context; there is no need to wrap every parameter in an expression just because you can.

### 2.2. Accessing properties of parameters

SpEL can read properties of objects passed into the method:

```java
public record CustomerFilter(
        String status,
        String city
) {}

@Query("""
    SELECT *
    FROM customers
    WHERE status = :#{#filter.status}
      AND city = :#{#filter.city}
    """)
List<Customer> search(@Param("filter") CustomerFilter filter);
```

This can be useful when a use case passes a filter object holding multiple values. However, if a query has only two simple conditions, explicit parameters can be easier to understand and test.

## 3. EvaluationContext and EvaluationContextExtension

To evaluate SpEL, Spring needs an `EvaluationContext`. This context holds the root object, variables, property accessors, and components needed to resolve expressions.

Spring Data Commons defines the `EvaluationContextExtension` interface to add elements to the evaluation context used for repository queries. An extension can provide:

- **Extension ID:** the identifier name of the extension.
- **Root object:** the object serving as the source of properties/methods for expressions.
- **Properties or functions:** additional variables/capabilities if the implementation needs to expose them.

The interface lives in package:

```java
import org.springframework.data.spel.spi.EvaluationContextExtension;
```

An extension is typically registered as a Spring bean. Spring Data can collect extension beans to extend the context when evaluating query expressions, within the modules and versions that support that feature.

### 3.1. Why use an extension?

Suppose many queries need to filter data by the current tenant. If every repository method accepts `tenantId` from the caller, signatures repeat the parameter everywhere:

```java
List<PurchaseOrder> findByTenantIdAndStatus(
        UUID tenantId,
        String status
);
```

If the tenant is part of a security/request context already established at the application layer, an extension can supply that tenant ID to SpEL:

```text
HTTP request / authenticated principal
              |
              v
      TenantContext
              |
              v
EvaluationContextExtension
              |
              v
      SpEL expression
              |
              v
     bound SQL parameter
```

That way, query methods do not need to accept the tenant ID repeatedly in every signature. However, this is an architectural trade-off: passing tenant ID explicitly remains appropriate, especially for background jobs, batch processes, message consumers, or use cases querying across multiple tenants.

## 4. Example: providing the current tenant via EvaluationContextExtension

Suppose the orders table has a `tenant_id` column. Each request is authenticated and the security/application layer sets the current tenant in a request-scoped context. The repository needs to filter by that tenant.

### 4.1. Context holding the tenant ID

A minimal example using `ThreadLocal`:

```java
package com.example.tenancy;

import java.util.UUID;

public final class TenantContext {

    private static final ThreadLocal<UUID> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static void setTenantId(UUID tenantId) {
        CURRENT.set(tenantId);
    }

    public static UUID requireTenantId() {
        UUID tenantId = CURRENT.get();
        if (tenantId == null) {
            throw new IllegalStateException(
                    "No tenant is available in the current context");
        }
        return tenantId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

This is only an illustrative context for synchronous applications running on a thread bound to a request. In real systems, the tenant context must be set and cleared in a filter/interceptor or security integration; for reactive processing, do not rely on `ThreadLocal` because execution can switch threads. Use a context mechanism appropriate for the execution model.

### 4.2. Root object for SpEL

Create a small object that exposes only the value needed:

```java
package com.example.tenancy;

import java.util.UUID;

public record TenantExpressionRoot(UUID tenantId) {
}
```

The root object should not expose the entire security context, request object, or privileged services. Put into the evaluation context only the properties/methods needed by queries.

### 4.3. Implementing EvaluationContextExtension

```java
package com.example.tenancy;

import org.springframework.data.spel.spi.EvaluationContextExtension;

public class TenantEvaluationContextExtension
        implements EvaluationContextExtension {

    @Override
    public String getExtensionId() {
        return "tenant";
    }

    @Override
    public TenantExpressionRoot getRootObject() {
        return new TenantExpressionRoot(
                TenantContext.requireTenantId()
        );
    }
}
```

`getRootObject()` provides the root object for this evaluation context extension. The root's `tenantId` property can be referenced in SpEL via the context's root-property mechanism. `getExtensionId()` identifies the extension within the extension system; do not assume every module/version uses this ID as a prefix in expression syntax. Use the exact syntax documented by your project's Spring Data JDBC version.

### 4.4. Registering the extension as a bean

```java
package com.example.tenancy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.spel.spi.EvaluationContextExtension;

@Configuration
public class QueryExpressionConfiguration {

    @Bean
    EvaluationContextExtension tenantEvaluationContextExtension() {
        return new TenantEvaluationContextExtension();
    }
}
```

Spring Data can discover extension beans to extend query method evaluation contexts. Auto-discovery and evaluation timing depend on the module version integration; check the documentation for your Spring Data Relational version if the extension does not appear in queries.

### 4.5. Using root values in @Query

Repository example:

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT *
        FROM purchase_orders
        WHERE tenant_id = :#{tenantId}
          AND status = :status
        """)
    List<PurchaseOrder> findForCurrentTenant(
            @Param("status") String status);
}
```

In this example, `tenantId` comes from the root object provided by the extension; `status` is a method parameter. The tenant value is evaluated and then bound at the SQL parameter position. Table/column names are illustrative; they must match the actual schema and the SpEL syntax supported by the Spring Data JDBC version in use.

## 5. What can an extension provide?

Extensions are not limited to tenancy. Several useful cases include:

| Context source | Values that can be provided | Example purpose |
| --- | --- | --- |
| Security principal | User ID, username, or authenticated tenant | Filtering records owned by the current user |
| Tenant context | Current tenant ID | Isolating data per tenant |
| Application context | A partition value or business unit | Applying a default filter to queries |
| Simple policy | A well-bounded function/value | Normalizing or computing a bound value |

With Spring Security, an extension can provide a root object based on the current authentication. Expressions can then read properties exposed by that root object, such as principal or authority info, provided those properties actually exist on the object and are supported in the context.

Do not expose the entire `SecurityContext`, `HttpServletRequest`, `ApplicationContext`, or arbitrary beans into the SpEL root. The goal is to expose a small, stable, testable surface.

### Extension ID vs. root object

These two concepts have different roles:

- `getExtensionId()` names the extension within Spring Data's integration mechanism.
- `getRootObject()` supplies the object whose properties/methods expressions access.

Do not confuse `extensionId` with a root property name. When writing expressions, rely on official examples and documentation for your exact Spring Data version rather than guessing syntax from the ID name alone.

## 6. SpEL in queries should only produce bound values

A crucial rule for using SpEL in SQL is distinguishing **data values** from **SQL structure**.

### 6.1. Safe bound values

Example:

```java
@Query("""
    SELECT *
    FROM customers
    WHERE email = :#{#email}
    """)
List<Customer> findByEmailExpression(@Param("email") String email);
```

Email is evaluated to a value and bound as a parameter. Even if the email contains single quotes or SQL-like strings, it remains parameter data rather than becoming a SQL command.

### 6.2. Do not use SpEL to substitute arbitrary table or column names

Do not design queries that try to replace identifiers:

```text
SELECT * FROM :#{#tableName}
```

JDBC bind parameters represent **values**, not table names, column names, SQL keywords, or `ORDER BY` fragments. Likewise, never take a SQL snippet sent by a client and embed it into a query via SpEL.

If you need to select among a few tables/columns or sort directions, map input to a fixed list of choices in code and build the SQL through a controlled mechanism. For complex dynamic queries, use `JdbcTemplate`/`NamedParameterJdbcTemplate` or an appropriate query builder.

### 6.3. Do not treat SpEL as a complete access-control filter

A tenant filter in a repository can help avoid forgetting the tenant condition in a single query, but it does not by itself create a security boundary for the entire system. Consider:

- Do all data-access paths go through protected repository methods?
- Are there other custom SQL queries that omit the tenant filter?
- Do background jobs set the tenant context before running?
- Is database row-level security or separate constraints needed?
- Can users manipulate the tenant ID in requests, or is only the authenticated tenant used?

Tenant ID should come from an authenticated context or be passed through an authorized use case. Never trust a client-supplied tenant value simply because it is passed into SpEL.

## 7. When to use method parameters instead of an extension?

An extension is convenient when a context value is truly shared ambient context, such as the tenant resolved for a request. However, explicit parameters often have advantages:

- The method signature shows exactly which data the query depends on.
- Easy to call from batch jobs, scheduled tasks, and message consumers.
- Unit tests do not need to set up global/thread-local context.
- Does not depend on hidden security/request state.
- Allows the same method to operate across multiple tenants if the use case permits.

Example with explicit parameters:

```java
@Query("""
    SELECT *
    FROM purchase_orders
    WHERE tenant_id = :tenantId
      AND status = :status
    """)
List<PurchaseOrder> findByTenantAndStatus(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status
);
```

Choose an extension when the context is an ambient default for how the application executes queries and is reliably established. Choose explicit parameters when the tenant/user is true business input to the use case or when callers need explicit control.

## 8. Limitations to remember

### 8.1. SpEL does not replace SQL

SpEL evaluates expressions. It does not replace SQL capabilities such as JOINs, grouping, window functions, CTEs, or execution-plan optimization. When a query needs those capabilities, write appropriate SQL.

### 8.2. Use only in expression positions supported by the query parser

Do not assume SpEL can be placed anywhere inside a SQL statement. Supported positions depend on the module and version. The common case is an expression producing a bound parameter value. If you want an expression to replace identifiers or generate query clauses, check the documentation and consider another tool.

### 8.3. Result types must be bindable via JDBC

The value returned by SpEL must have a type that mapping/JDBC can convert into the parameter's SQL type. UUIDs, Strings, numbers, enums, or supported date/time types are generally easier to handle than custom objects. If an expression returns a complex object, extract a specific scalar property or convert it in the application service.

### 8.4. Context may not exist outside requests

An extension calling `TenantContext.requireTenantId()` may work in HTTP requests yet fail in schedulers or consumers if those flows do not set up the context. Clearly define behavior when principal/tenant is absent: reject the query, require explicit parameters, or use a bounded system context.

### 8.5. Extensions must be safe for concurrent, repeated calls

Do not store request-specific state in mutable fields of a singleton extension bean. The bean can be used concurrently by multiple requests. Read the current context at evaluation time or pass values via parameters; never cache a previous request's tenant/user on a shared instance.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| SpEL reports property not found | Property name does not exist on parameter or root object | Check parameter names, getters/record accessors, and the root object returned by the extension. |
| Expression does not pick up extension | Bean is not registered, package/configuration is not scanned, or module/version does not integrate extensions as expected | Verify the bean is created and check Spring Data Relational docs for your project version. |
| Query reports missing parameter | Placeholder name and `@Param` name mismatch, or expression is not recognized by parser | Check placeholder names, annotations, and expression syntax. |
| Failure in background jobs | Tenant/security context is not set outside HTTP requests | Pass tenant explicitly or establish controlled context before calling the repository. |
| Query returns wrong tenant's data | Context reads from wrong source, leaks across requests, or another query omits filter | Review set/clear lifecycle, audit all access paths, and consider database-level protection. |
| Invalid SQL when using expression for identifier | Parameter binding cannot replace table/column names | Select identifiers from an allowlist in code or construct SQL in a controlled way. |
| Incompatible parameter type | SpEL returns an object unmappable to a JDBC type | Return a scalar/supported type or convert before calling the repository. |

### Observing SQL

Enable Spring JDBC logging in development environments:

```properties
logging.level.org.springframework.jdbc=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
```

Logs help inspect the SQL statement and parameter-binding details. Be careful enabling TRACE in environments with sensitive data: bound values can include emails, user IDs, or personal information.

When debugging SpEL, break the problem into three questions:

1. Was the `EvaluationContextExtension` bean created?
2. Does the root object expose the property requested by the expression?
3. Was the expression value converted to the right parameter type and bound into SQL?

## 10. Example: testing an extension in isolation

You can test the root object part without a database:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class TenantEvaluationContextExtensionTest {

    @AfterEach
    void clearContext() {
        TenantContext.clear();
    }

    @Test
    void exposesCurrentTenantAsRootProperty() {
        UUID expected = UUID.randomUUID();
        TenantContext.setTenantId(expected);

        TenantEvaluationContextExtension extension =
                new TenantEvaluationContextExtension();

        assertEquals("tenant", extension.getExtensionId());
        assertEquals(
                expected,
                extension.getRootObject().tenantId()
        );
    }
}
```

This only tests that the extension supplies the expected root object. A repository integration test is still needed to prove the query parser evaluates the expression and binds the value into SQL in your application's exact Spring Data JDBC version.

In integration tests, you should:

- Set tenant A, save data for A and B.
- Call the query in context A and verify only A's data is visible.
- Switch to context B and verify only B's data is visible.
- Clear context after each test to prevent state leakage between tests.
- Attempt calling the query without a tenant context and verify fail-closed behavior per design.

## 11. Workflow for designing queries with SpEL

When a dynamic value is needed in `@Query`, proceed in order:

1. **Identify the value to bind.** Is it a status, tenant ID, user ID, or a normalized value?
2. **Check whether a plain named parameter works.** If the caller already has the value, prefer passing it directly.
3. **If shared context is needed, define a small root object.** Expose only required properties.
4. **Register the extension as a bean.** Ensure the configuration is within the Spring Data repository scope.
5. **Write the expression in a supported placeholder.** The expression should return a scalar/JDBC-bindable type.
6. **Verify SQL and bound values.** Use logging or instrumentation in a safe environment.
7. **Test across contexts.** Include requests, background jobs, and absent-context cases.
8. **Evaluate security boundaries.** Do not treat an expression filter as the sole protection mechanism.

## 12. Self-practice exercises

**Exercise 1 — SpEL with parameters.** Write a query method filtering customers by email using `:#{#email}`. Compare it with named parameter `:email`; explain when an expression brings value.

**Exercise 2 — Input normalization.** Use SpEL to call `trim()` and `toLowerCase()` on a string parameter. Inspect the value received by SQL and consider whether normalization belongs in the application service instead.

**Exercise 3 — Tenant extension.** Create `TenantEvaluationContextExtension`, register the bean, and use a root property in a query. Save data for two tenants and verify isolated results.

**Exercise 4 — Missing context.** Call the repository from a job that does not set a tenant. Define the intended behavior and fix the design using an explicit tenant parameter or controlled system context.

**Exercise 5 — No identifier concatenation.** Try designing a query whose table name comes from SpEL. Explain why parameter binding cannot replace identifiers; replace it with an allowlist or SQL builder.

**Exercise 6 — Integration testing.** Write tests verifying that the extension is actually evaluated in the query method on the project's target database. Test both the missing-tenant case and the multi-tenant coexistence case.

## 13. Key takeaways

In Spring Data JDBC, SpEL is useful when a query needs to compute parameter values from method arguments or an evaluation context. `EvaluationContextExtension` lets applications provide a root object and additional context for expression evaluation. Common examples are the current tenant ID or properties of the current principal.

Keep expressions short, return JDBC-bindable values, and use them only in positions supported by your Spring Data JDBC version's query methods. SpEL is not a replacement for SQL, does not substitute table/column names via bind parameters, and is not a complete security boundary. For values already available to the caller, explicit named parameters are usually clearer; extensions fit shared ambient context that is reliably established and managed.

### References

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Commons – EvaluationContextExtension API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/spel/spi/EvaluationContextExtension.html)
- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
