# QueryCreationException, JPQL Errors, and Parameter Mismatches in Spring Data JPA

When a repository method cannot create or execute a query, Spring Data JPA may report an error at application startup or only when the method is called. A common group of errors includes QueryCreationException, JPQL syntax/identifier errors, and bind parameter mismatches between the method signature and the query.

An effective approach is to find the root cause rather than looking only at the outermost exception. You need to identify whether the failure occurs during method name parsing, JPQL validation, parameter binding, type conversion, SQL execution, or result mapping. Each stage has distinct symptoms and fixes.

This lesson uses a consistent PurchaseOrder model to illustrate derived queries, @Query, named/positional parameters, Page/countQuery, DTO projections, and modifying queries. The sections below explain how to read stack traces, verify entity/property names, handle parameters, test repositories, and build a diagnostic workflow applicable to real projects.

## 1. What is QueryCreationException?

QueryCreationException belongs to Spring Data Commons and typically occurs when Spring Data cannot create a query for a repository method. It may wrap a more specific cause, such as:

- Cannot find a property referenced by a derived query.
- The method name cannot be parsed into a valid query.
- The JPQL declared in @Query is invalid or references a non-existent entity/property.
- Parameters in the query do not match the method parameters.
- The return type or method signature is incompatible with how the query is constructed.

The exception name alone does not reveal exactly where the error is. Always inspect the deepest Caused by and the provider's message.

An example stack trace may look like:

~~~text
org.springframework.data.repository.query.QueryCreationException:
Could not create query for method ...
    at ...
Caused by: org.springframework.data.mapping.PropertyReferenceException:
No property 'customerMail' found for type 'PurchaseOrder'
~~~

The root cause here is an incorrect property name: the entity has customerEmail, while the method uses customerMail.

Another case:

~~~text
org.springframework.data.repository.query.QueryCreationException:
Could not create query for method ...
Caused by: java.lang.IllegalArgumentException:
Validation failed for query for method ...
Caused by: org.hibernate.query.SemanticException:
Could not resolve attribute 'orderStatus' of 'PurchaseOrder'
~~~

This error is inside the JPQL: the entity has a status property, not orderStatus.

Do not assume every query error is a QueryCreationException. Some errors only appear at execution time and may be wrapped as DataAccessException, InvalidDataAccessApiUsageException, or a JPA provider exception. The exact exception type depends on Spring Data, Hibernate, and when the query is created/validated.

## 2. When Are Queries Created?

Spring Data JPA can create queries from multiple sources:

1. Derived query: parsing a method name like findByStatusAndCreatedAtAfter.
2. Declared query: a JPQL or native SQL statement declared with @Query.
3. Named query: a query declared via annotations or XML.
4. Custom repository: custom code building queries with EntityManager or Criteria API.

By default, Spring Data typically prioritizes declared queries if present and derives a query from the method name when no declared query exists. The query lookup strategy can be configured as CREATE, USE_DECLARED_QUERY, or CREATE_IF_NOT_FOUND.

Repositories are usually initialized when the application context starts, so errors may appear before any endpoint is invoked. However, bootstrap mode, lazy/deferred repository initialization, and provider query validation behavior can shift when errors are detected.

Some JPQL syntax errors are caught when the repository creates the query. Some bind/type errors or SQL dialect errors only surface when the query actually runs. Therefore:

- Errors right at startup usually point to repository method parsing, query validation, mapping, or bean configuration.
- Errors on the first method invocation may relate to lazy repository initialization, parameter binding, database SQL, or data.
- Errors occurring only with a specific set of arguments usually point to null, empty collections, data types, sorting, or specific conditional branches.

Do not rely solely on error timing to draw conclusions; combine the stack trace, query, and method signature.

## 3. Entity Model Used Throughout the Lesson

The examples use the PurchaseOrder entity in package com.example.orders. Entity and property names are explicitly declared to avoid confusing JPQL with table/column names.

Enum:

~~~java
package com.example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Entity:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String customerEmail;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String customerEmail,
            OrderStatus status,
            BigDecimal totalAmount,
            Instant createdAt) {
        this.customerEmail = customerEmail;
        this.status = status;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerEmail() {
        return customerEmail;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

The mapping has these Java properties:

- id
- customerEmail
- status
- totalAmount
- createdAt

The database table name is purchase_orders. JPQL must use the entity name PurchaseOrder and Java properties, not purchase_orders or physical column names.

## 4. Derived Query Error: Non-Existent Property Name

Spring Data parses a method name into subject and predicate. The part after By describes conditions using property names and keywords.

Correct examples:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);

List<PurchaseOrder> findByCustomerEmail(String customerEmail);

List<PurchaseOrder> findByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt);
~~~

These methods reference properties that actually exist on PurchaseOrder.

Incorrect example:

~~~java
List<PurchaseOrder> findByOrderStatus(OrderStatus status);
~~~

The entity has no orderStatus property. Spring Data may report PropertyReferenceException with a message similar to No property 'orderStatus' found for type 'PurchaseOrder', which is then wrapped in a repository query creation error.

The fix is to use the correct property:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Checklist when encountering PropertyReferenceException:

1. Open the entity and check the actual field/property names.
2. Check spelling and uppercase/lowercase casing.
3. Check getters/property access if the entity uses property-based access.
4. Check nested association paths.
5. Do not confuse `@Column(name = ...)` column names with Java property names.

Example:

~~~java
@Column(name = "customer_email")
private String customerEmail;
~~~

The derived query still uses findByCustomerEmail, not findByCustomer_Email simply because the column name has an underscore.

## 5. Nested Property Path Parsing Errors

Spring Data can parse paths through associations. For example, if PurchaseOrder has a customer association and Customer has an email property, the method can use findByCustomer_Email.

An underscore helps clearly delineate property path boundaries:

~~~java
List<PurchaseOrder> findByCustomer_Email(String email);
~~~

In the current lesson model, PurchaseOrder has customerEmail as a String and does not have a customer association. Therefore, findByCustomer_Email is invalid for the current entity.

When an entity has multiple similarly named properties, the parser may split the path differently from what you intended. Use an underscore to explicitly mark traversal across an association and verify the name at each step.

Another illustrative entity model:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    private String email;
}

@Entity
public class SalesOrder {
    @ManyToOne
    private Customer customer;
}
~~~

With this model, SalesOrder can use:

~~~java
List<SalesOrder> findByCustomer_Email(String email);
~~~

Do not copy that method into PurchaseOrder if the entity lacks the corresponding association.

## 6. Commonly Used Derived Query Keywords

Some common keywords:

| Keyword | Meaning | Example |
|---|---|---|
| Is, Equals | Equal to | findByStatus |
| And | Logical AND | findByStatusAndCustomerEmail |
| Or | Logical OR | findByStatusOrCustomerEmail |
| After | Greater than for date/time types | findByCreatedAtAfter |
| Before | Less than for date/time types | findByCreatedAtBefore |
| Between | Within a range | findByCreatedAtBetween |
| GreaterThan | Greater than | findByTotalAmountGreaterThan |
| LessThan | Less than | findByTotalAmountLessThan |
| In | In a set of values | findByStatusIn |
| IsNull | Null value | findByCustomerEmailIsNull |
| IsNotNull | Not null | findByCustomerEmailIsNotNull |
| Containing | Substring | findByCustomerEmailContaining |
| StartingWith | Starts with | findByCustomerEmailStartingWith |
| EndingWith | Ends with | findByCustomerEmailEndingWith |
| IgnoreCase | Case-insensitive for strings | findByCustomerEmailIgnoreCase |
| OrderBy | Sorting | findByStatusOrderByCreatedAtDesc |
| First, Top | Limit results | findFirstByStatusOrderByCreatedAtDesc |

Keywords must be compatible with the property type. For example, IgnoreCase fits String; do not apply it arbitrarily to enums or Instant.

If the method name becomes too long or conditions require complex parenthesized grouping, use @Query, Specification, or Querydsl instead of forcing all logic into the method name.

## 7. A Method Name May Be Valid Yet Mean Something Different from Intended

A method may be accepted by the parser, yet the generated query does not match the intended business logic. Example:

~~~java
List<PurchaseOrder> findByStatusOrCustomerEmailAndCreatedAtAfter(
        OrderStatus status,
        String email,
        Instant createdAt);
~~~

Operator precedence in derived queries follows its own parsing rules; do not assume expressions are grouped the way natural language reads. If you need explicit logic such as:

~~~text
(status = PAID OR customerEmail = ...)
AND createdAt > ...
~~~

write @Query with explicit parentheses or use Specification/Criteria API.

Do not merely check whether the method initializes. Check the generated SQL and results with representative data to verify the AND/OR logic.

## 8. Reserved Method Names in Repositories

Certain method names inherited from CrudRepository/JpaRepository carry special semantics. For example, findById is defined to look up by the entity's identifier.

If an entity has a business property named id that differs from the primary key, or if you want to query by a non-primary-key property, avoid assuming a same-named method will be parsed as an ordinary derived query.

Use a different descriptive method name or an explicit @Query when colliding with inherited methods. When seeing unexpected query behavior, check whether the method overrides/matches a base repository method.

## 9. JPQL Uses Entity Names and Property Names

JPQL queries the entity model, not SQL tables directly.

Correct example:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

Components:

- PurchaseOrder is the default entity name matching the class name, unless `@Entity(name = "...")` specifies another name.
- o is the alias.
- o.status is the Java persistent property.
- :status is a named parameter.

Incorrect example:

~~~java
@Query("""
       select *
       from purchase_orders
       where order_status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

This is SQL syntax, not JPQL. SELECT * and physical table/column names are invalid in JPQL.

If you want to write SQL directly, declare nativeQuery = true and follow the appropriate dialect/schema:

~~~java
@Query(
    value = """
            select *
            from purchase_orders
            where status = :status
            """,
    nativeQuery = true
)
List<PurchaseOrder> findNativeByStatus(
        @Param("status") String status);
~~~

Native queries must use physical column names and parameter types compatible with the schema/database. If an enum is stored as STRING, the value passed to a native query typically needs to be converted to the enum name; native enum parameter mapping is not identical to JPQL entity parameters across all providers.

## 10. Common JPQL Errors

| Error | Wrong example | How to check/fix |
|---|---|---|
| Wrong entity name | from Orders o | Use PurchaseOrder or the declared entity name |
| Wrong property | o.orderStatus | Use o.status |
| Using column name | o.customer_email | Use o.customerEmail |
| Wrong alias | where p.status while alias is o | Use the declared alias |
| Missing alias | select PurchaseOrder from PurchaseOrder | Declare an alias, e.g., select o from PurchaseOrder o |
| Using SQL syntax | select * from purchase_orders | Switch to nativeQuery or write JPQL |
| Wrong literal type | o.status = 1 when status is an enum | Bind OrderStatus |
| Wrong DTO constructor | new com.example.Dto(...) with mismatched args | Check FQCN, argument order, and constructor types |
| Invalid fetch join | fetch in count query | Separate count query, do not fetch associations |
| Aggregate missing GROUP BY | selecting regular fields alongside count | Add appropriate GROUP BY |
| Invalid operator | using syntax unsupported by JPQL | Check JPQL/provider version |

JPQL is parsed by the provider against the entity mapping. When an error occurs, verify the exact entity class, fields, associations, data types, and aliases before editing SQL/database objects.

## 11. Named Parameters: Names Must Match Exactly

With named parameters, placeholders in JPQL must match the names in @Param.

Correct:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status,
        @Param("email") String customerEmail);
~~~

Incorrect:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :orderStatus
       """)
List<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status);
~~~

The query uses :orderStatus, while the method binds the name status. The provider may report parameter not found or Spring Data may report unable to bind the corresponding parameter.

Fix: align the placeholder name and @Param:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status);
~~~

Parameter names are case-sensitive according to provider handling. Keep a consistent convention and do not rename one side while forgetting the other.

## 12. Parameter Counts Must Match

If JPQL has two placeholders while the method only provides one bindable parameter, the query cannot be fully bound.

Incorrect:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status);
~~~

The query requires both status and email, but the method only has status.

Correct:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status,
        @Param("email") String email);
~~~

Also check for unused method parameters remaining after editing a query. Extra parameters can prevent Spring Data from knowing where to bind them or make the query signature confusing.

When adding/removing placeholders, update the method signature, @Param, and repository test together.

## 13. Named Parameters vs. Positional Parameters

There are two common ways to bind parameters.

Named parameters:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.createdAt >= :from
       """)
List<PurchaseOrder> findByStatusFrom(
        @Param("status") OrderStatus status,
        @Param("from") Instant from);
~~~

Positional parameters:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = ?1
         and o.createdAt >= ?2
       """)
List<PurchaseOrder> findByStatusFrom(
        OrderStatus status,
        Instant from);
~~~

With positional parameters, ?1 is the first parameter and ?2 is the second parameter. The method signature order must match.

Do not mix named and positional parameters in the same query. Pick one style per query. Named parameters are generally more readable and less error-prone when a method takes multiple parameters.

When using named parameters, explicitly declaring @Param makes the code clearer and avoids depending on compiler parameter-name retention settings.

## 14. @Param and Compiler Parameter-Name Retention

Some Spring Data versions can infer method parameter names if the application is compiled with parameter-name retention in bytecode, such as javac -parameters. However, exact behavior and requirements depend on the Spring Data version and build configuration.

Explicit, readable style:

~~~java
List<PurchaseOrder> findByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt);
~~~

For derived queries, parameters are usually bound in predicate order; @Param is unnecessary to define derived query conditions.

For @Query with named parameters, use @Param on each argument to prevent issues during parameter refactoring, compiler configuration changes, or version upgrades.

## 15. Parameters Cannot Replace Entity Names, Property Names, or Keywords

Bind parameters only substitute values, never identifiers or JPQL structure.

Do not do this:

~~~java
@Query("select o from PurchaseOrder o order by :field")
List<PurchaseOrder> sortBy(
        @Param("field") String field);
~~~

:field is a parameter value, not a property name for sorting.

If dynamic sorting is needed, accept Sort/Pageable or construct the query with a property allowlist. On repository methods with @Query, Spring Data can apply dynamic Sort in supported cases; properties must still be valid and must never come from arbitrary client-supplied raw expressions.

Do not concatenate input directly into ORDER BY:

~~~java
String jpql = "select o from PurchaseOrder o order by " + requestSort;
~~~

Instead, map allowed names:

~~~java
Map<String, String> allowedSorts = Map.of(
        "createdAt", "o.createdAt",
        "totalAmount", "o.totalAmount",
        "status", "o.status",
        "id", "o.id"
);
~~~

Only concatenate expressions looked up from the allowlist; direction must come from an enum or validated ASC/DESC values.

## 16. Parameter Types Must Be Compatible with Properties

Even with the right parameter name, an error still occurs if the data type is incompatible.

Example entity:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;

private Instant createdAt;

private BigDecimal totalAmount;
~~~

Correctly typed methods:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);

List<PurchaseOrder> findByCreatedAtAfter(Instant instant);

List<PurchaseOrder> findByTotalAmountGreaterThan(BigDecimal amount);
~~~

Common mistakes:

- Passing an arbitrary String into a JPQL query comparing against an enum.
- Passing LocalDate when the property is Instant without explicit timezone/boundary conversion.
- Passing Integer for a BigDecimal property.
- Passing an entity object when the query expects a scalar ID or vice versa.
- Passing a collection with mismatched element types for an IN predicate.

Use the proper domain types in the method signature. If the API accepts a String, convert/validate it into an enum, Instant, or BigDecimal at the service boundary before calling the repository.

## 17. IN Parameters and Empty Collections

JPQL supports collection parameters:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status in :statuses
       """)
List<PurchaseOrder> findByStatuses(
        @Param("statuses") Collection<OrderStatus> statuses);
~~~

The collection must hold values of the right type. Empty collections must be handled explicitly in the service because SQL/JPQL providers handle empty bind lists differently; some database engines reject IN ().

Example:

~~~java
public List<PurchaseOrder> findByStatusesSafe(
        Collection<OrderStatus> statuses) {
    if (statuses == null || statuses.isEmpty()) {
        return List.of();
    }
    return repository.findByStatuses(statuses);
}
~~~

This is an illustrative service method assuming the repository has findByStatuses. If business rules define an empty list as "no filter", returning all results is a different behavior; decide explicitly and test it.

Do not silently turn a null/empty collection into an unfiltered query if doing so could return large amounts of unintended data.

## 18. Null Parameters and Optional Filters

The expression:

~~~jpql
where o.status = :status
~~~

does not mean "skip the filter if status is null". Comparing with null in SQL/JPQL does not evaluate to true like normal equality.

If you want an optional filter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where (:status is null or o.status = :status)
       """)
List<PurchaseOrder> searchByOptionalStatus(
        @Param("status") OrderStatus status);
~~~

If status is null, the first branch is true and the predicate does not restrict status. If status has a value, the query filters by status.

However, OR expressions can impact index usage and execution plans depending on the database. For multiple optional filters, Specification/Criteria or dynamic JPQL can build queries containing only the needed predicates.

If business logic needs to find rows where a property IS NULL, write it explicitly:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.customerEmail is null
       """)
List<PurchaseOrder> findWithoutCustomerEmail();
~~~

Clearly distinguish null meaning "no filter criterion" from null meaning "find rows whose column value is null".

## 19. LIKE Parameters and Wildcards

JPQL LIKE takes a pattern. Use a named parameter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where lower(o.customerEmail) like lower(:pattern)
       """)
List<PurchaseOrder> findByEmailPattern(
        @Param("pattern") String pattern);
~~~

Call with %example.com% to search substrings. If using the derived query keyword Containing, Spring Data handles adding wildcards according to the keyword's semantics.

Two characters have special meaning:

- %: matches zero or more characters.
- _: matches a single character.

If a user wants to search for literal % or _ characters, you must escape them using the escape character declared in JPQL/provider. Bind parameters prevent injection but do not automatically turn wildcards into literals.

When queries use IgnoreCase or lower(), check collation/locale and indexing. Do not assume ignore case also strips Vietnamese diacritics.

## 20. Pageable and Sort Are Special Parameters

Pageable and Sort are not ordinary bind parameters in JPQL. Spring Data handles them to apply pagination/sorting.

Example:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
Page<PurchaseOrder> findPageByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable);
~~~

Only status is bound to :status. Pageable is a special parameter and does not need `@Param("pageable")`.

If a method declares:

~~~java
Page<PurchaseOrder> findPageByStatus(
        @Param("status") OrderStatus status,
        @Param("pageable") Pageable pageable);
~~~

do not treat pageable as a JPQL placeholder. Do not declare :pageable in the query expecting JPA to apply offset/limit automatically.

Sort properties must be valid against the entity model and should be restricted to allowed fields. When paginating, add a unique key as a tie-breaker for deterministic ordering.

## 21. Mismatched Page and countQuery

Page<T> needs both content and total element count. For complex queries, a separate countQuery can be declared:

~~~java
@Query(
    value = """
            select o
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :from
            order by o.createdAt desc, o.id desc
            """,
    countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :from
            """
)
Page<PurchaseOrder> findPage(
        @Param("status") OrderStatus status,
        @Param("from") Instant from,
        Pageable pageable);
~~~

The count query must keep the same filter predicates, without needing ORDER BY or fetch associations.

If the content query filters by status and from while the count query only filters by status, totalElements will be wrong. If the query joins a collection, count(o) may count joined rows; use EXISTS or count(distinct o.id) depending on query structure.

A wrong countQuery may not raise QueryCreationException. It can run successfully yet return the wrong total count. Therefore, test both content and totalElements.

## 22. DTO Constructor Expression Mismatches

JPQL can return DTOs using constructor expressions:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderSummary(
        Long id,
        String customerEmail,
        BigDecimal totalAmount
) {
}
~~~

Repository query:

~~~java
@Query("""
       select new com.example.orders.OrderSummary(
           o.id,
           o.customerEmail,
           o.totalAmount
       )
       from PurchaseOrder o
       where o.id = :id
       """)
Optional<OrderSummary> findSummaryById(
        @Param("id") Long id);
~~~

JPQL must use the fully qualified class name in the constructor expression. The order and types of expressions must match the DTO constructor.

Common mistakes:

- Misspelling the DTO package/class name.
- DTO lacks a matching constructor.
- Swapping field order.
- Incompatible types, e.g., constructor takes Integer while the query returns Long.
- Incorrect aliases or constructor expression syntax.

When using a Java record, the canonical constructor has the exact component order. When changing the DTO, update both the query and tests together.

## 23. Return Type and Cardinality Errors

A query can be created successfully yet fail at runtime because the result does not match the return type.

Example:

~~~java
Optional<PurchaseOrder> findByCustomerEmail(String email);
~~~

If multiple orders share the same email, the query can return multiple rows and the provider/Spring Data reports a non-unique result error. This is not necessarily a QueryCreationException.

Choose the return type according to cardinality:

| Return type | Expectation |
|---|---|
| PurchaseOrder | Single result; depending on the API, may return null when absent |
| Optional<PurchaseOrder> | Zero or one result |
| List<PurchaseOrder> | Zero, one, or many results |
| Page<PurchaseOrder> | Paginated results with total count |
| Slice<PurchaseOrder> | Slice of results with next-page availability |
| long | Count |
| boolean | Existence check when method/query is designed for exists |

If you need one latest result, use findFirstBy...OrderBy... or a Pageable limited to 1 instead of Optional on a non-unique condition.

## 24. @Modifying for UPDATE and DELETE Queries

@Query defaults to read queries. When declaring bulk UPDATE/DELETE statements, @Modifying is required:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("""
       update PurchaseOrder o
       set o.status = :status
       where o.id = :id
       """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") OrderStatus status);
~~~

Without @Modifying, Spring Data may try to execute the update query as a select query and fail at runtime.

Points to remember:

- Bulk updates/deletes bypass dirty checking on individual entities.
- The persistence context may still hold stale entities after a bulk update.
- clearAutomatically can clear the persistence context after the query runs.
- flushAutomatically flushes pending changes before the bulk operation.
- Transactions must be managed properly; e.g., placing @Transactional on the method.
- The return type is usually the affected row count or void, not List<PurchaseOrder>.

Do not put @Modifying on SELECT queries. If you need to modify many entities and require lifecycle callbacks/cascades, consider loading entities and updating each object or designing the business operation appropriately.

## 25. JPQL vs. Native SQL: Identifying the Right Language

A common mistake is writing SQL while forgetting nativeQuery = true.

JPQL:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

Native SQL:

~~~java
@Query(
    value = """
            select *
            from purchase_orders
            where status = :status
            """,
    nativeQuery = true
)
List<PurchaseOrder> findByStatusNative(
        @Param("status") String status);
~~~

In JPQL:
- Use entity names and property names.
- Enum parameters can be passed using the enum type.
- Associations and constructor expressions follow the entity model.

In native SQL:
- Use physical tables/columns.
- SQL must be compatible with the target database.
- Enum, timestamp, pagination, and result mapping may depend on the provider/database.
- Features like dynamic sorting or count derivation are more limited than in JPQL.

When seeing errors like "unexpected token", "table not mapped", or "could not resolve attribute", verify whether the query is being interpreted as JPQL or native SQL before editing it.

## 26. Named Queries and Query Resolution Order

JPA allows declaring @NamedQuery on entities or in XML. Spring Data can look up named queries by a naming convention combining the entity simple name and repository method name.

Illustrative example:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = "select o from PurchaseOrder o where o.status = :status"
)
@Entity
public class PurchaseOrder {
    // Entity mapping
}
~~~

If the corresponding repository method has a declared @Query, the query declared on the method is normally used according to Spring Data's query lookup rules. Otherwise, Spring Data may look for a named query or create a derived query depending on the lookup strategy.

When editing @Query and the behavior does not change as expected, verify whether the method is using a declared query, named query, or derived query. Do not assume the method name is always the sole query source.

## 27. Reading Stack Traces to Find the Root Cause

A stack-trace reading workflow:

1. Find the first Spring Data layer exception, typically QueryCreationException or InvalidDataAccessApiUsageException.
2. Walk down the Caused by blocks.
3. Locate the most specific message: missing property, unbound parameter, syntax error, type mismatch, or SQL error.
4. Identify whether the error happens at repository creation or at method execution.
5. Cross-check the message against the method signature, @Query, and entity mapping.
6. Fix one root cause and re-run the narrowest test.

Some commonly seen messages:

| Message/symptom | Investigation direction |
|---|---|
| No property ... found for type ... | Derived method uses an invalid property path |
| Could not resolve attribute ... | JPQL/Criteria references a property missing from the entity |
| Could not resolve entity ... | Wrong entity name or persistence unit mapping |
| Named parameter not bound | Query has a placeholder that was not bound |
| Could not locate named parameter | @Param and placeholder mismatch |
| Parameter value did not match expected type | Parameter type is incompatible with the property |
| Validation failed for query | Check the query string and nested cause |
| Unexpected token / syntax error | JPQL or native SQL syntax/dialect error |
| NonUniqueResultException | Single return type while query returns multiple rows |
| NoResultException | JPA Query.getSingleResult() has no row; Spring Data methods returning Optional usually yield Optional.empty() |
| SQLGrammarException | Generated SQL is invalid for the dialect/schema |
| Query did not return a unique result | Predicate or return type does not guarantee uniqueness |

Exact messages vary across Hibernate and Spring Data versions. Read the nested cause rather than matching exact strings from an old blog post.

## 28. Enabling Logging to Inspect Queries

In development/test environments, SQL logging can be enabled:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

To see bound parameters on Hibernate 6:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

On some older Hibernate versions, the bind parameter log category has a different name. Check the documentation for the version you are running.

Logs help confirm:

- Whether the query is generated and sent to the database.
- Whether SQL targets the right tables/columns.
- Whether parameters have the expected values and types.
- Whether pagination applies appropriate LIMIT/OFFSET.
- Whether the count query runs.
- Whether the query performs unexpected joins.

Bind logs can contain emails, customer data, or sensitive information. Only enable them in controlled environments and disable them after diagnosis; avoid logging sensitive parameters in production logs.

## 29. Building a Complete Repository for the Example Model

The following interface brings together the key examples. Place PurchaseOrderRepository.java in package com.example.orders:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatusAndCreatedAtAfter(
            OrderStatus status,
            Instant createdAt);

    List<PurchaseOrder> findByCustomerEmailContainingIgnoreCase(
            String fragment);

    List<PurchaseOrder> findByStatusIn(
            Collection<OrderStatus> statuses);

    Optional<PurchaseOrder> findFirstByCustomerEmailOrderByCreatedAtDesc(
            String email);

    @Query("""
           select o
           from PurchaseOrder o
           where o.status = :status
             and o.createdAt >= :from
           """)
    Page<PurchaseOrder> findPage(
            @Param("status") OrderStatus status,
            @Param("from") Instant from,
            Pageable pageable);

    @Query("""
           select new com.example.orders.OrderSummary(
               o.id,
               o.customerEmail,
               o.totalAmount
           )
           from PurchaseOrder o
           where o.id = :id
           """)
    Optional<OrderSummary> findSummaryById(
            @Param("id") Long id);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update PurchaseOrder o
           set o.status = :status
           where o.id = :id
           """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") OrderStatus status);
}
~~~

The methods above use the same declared entity and properties. The Page method takes Pageable as a special parameter, not bound as a JPQL placeholder. The DTO query uses OrderSummary defined earlier. The bulk update has @Modifying and @Transactional.

In real projects, read and write queries can be separated by service/use case. This combined interface illustrates different signature forms in one repository; projects are not required to put all methods into a single file.

## 30. Testing the Repository with @DataJpaTest

A small test can verify derived queries, JPQL named parameters, Page/count, and DTO constructor mapping.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAll(List.of(
                new PurchaseOrder(
                        "an@example.com",
                        OrderStatus.PAID,
                        new BigDecimal("100.00"),
                        Instant.parse("2026-01-03T10:00:00Z")),
                new PurchaseOrder(
                        "anna@example.com",
                        OrderStatus.PAID,
                        new BigDecimal("200.00"),
                        Instant.parse("2026-01-02T10:00:00Z")),
                new PurchaseOrder(
                        "binh@example.com",
                        OrderStatus.NEW,
                        new BigDecimal("50.00"),
                        Instant.parse("2026-01-01T10:00:00Z"))
        ));
    }

    @Test
    void derivedQueryFindsOrdersByStatus() {
        List<PurchaseOrder> result =
                repository.findByStatus(OrderStatus.PAID);

        assertThat(result).hasSize(2);
    }

    @Test
    void jpqlNamedParametersAndCountMatch() {
        Page<PurchaseOrder> page = repository.findPage(
                OrderStatus.PAID,
                Instant.parse("2026-01-01T00:00:00Z"),
                PageRequest.of(0, 1));

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void dtoConstructorExpressionMapsExpectedFields() {
        PurchaseOrder order = repository.findByStatus(OrderStatus.NEW)
                .get(0);

        OrderSummary summary = repository.findSummaryById(order.getId())
                .orElseThrow();

        assertThat(summary.customerEmail()).isEqualTo("binh@example.com");
        assertThat(summary.totalAmount())
                .isEqualByComparingTo("50.00");
    }
}
~~~

Full imports for the test are at the top of the file. The test assumes a Spring Boot test slice with appropriate JPA configuration and test database. @DataJpaTest typically runs in a transaction and rolls back after each test.

If a query method fails during repository initialization, slice tests usually catch it early. If errors only appear with specific parameters, add tests for nulls, empty collections, enums, boundary timestamps, and each query branch.

To test JPQL errors, do not simply mock the repository. Let the JPA provider actually initialize and validate the query in tests.

## 31. Step-by-Step Diagnostic Workflow

When encountering QueryCreationException or a query error, follow this order:

1. **Identify the query source.** Derived method, @Query, named query, native query, or custom EntityManager?
2. **Read the root cause.** Look for PropertyReferenceException, parser error, parameter error, type mismatch, or SQL exception.
3. **Cross-check entity mapping.** Entity name, property names, association paths, and Java types.
4. **Cross-check method signature.** Parameter count, @Param names, parameter types, special Pageable/Sort parameters, and return type.
5. **Verify the query language.** JPQL uses entities/properties; native SQL uses tables/columns.
6. **Check cardinality.** Optional/entity can accept at most one row; Page requires an accurate count.
7. **Run a repository test.** Reproduce the error with small, deterministic data.
8. **Enable SQL/bind logs when needed.** Inspect actual SQL statements and bound values.
9. **Re-run relevant tests after fixing.** Do not change multiple things at once without knowing the cause.
10. **Disable sensitive bind logging.** Do not leave parameter tracing on in production outside controlled needs.

Fixing the root cause is better than renaming methods or adding annotations by trial and error.

## 32. Common Mistakes and How to Fix Them

| Symptom | Common cause | Resolution |
|---|---|---|
| Repository fails to start | Wrong derived property | Check entity property/path |
| QueryCreationException with validation failed | JPQL uses wrong entity/property/alias | Check JPQL against entity model |
| Named parameter not bound | :name and @Param differ | Align the names |
| Query missing parameter | More placeholders than bindable args | Add missing method parameter |
| Method has extra parameter | No matching placeholder | Remove unused parameter or use in query |
| Positional query filters wrongly | ?1/?2 out of order with method args | Match positional indices |
| Type mismatch | Incompatible String/enum/date/number | Use proper domain types and convert in service |
| Empty IN causes SQL error | Provider/database rejects IN () | Guard collection before calling repository |
| JPQL reports table not found | SQL table name used in JPQL | Use entity name or nativeQuery |
| JPQL reports attribute not found | Column name used instead of property | Use Java property |
| Optional query reports multiple results | Condition is not unique | Use List or limit to a single result |
| Page totalElements is wrong | countQuery missing predicates or counting join rows | Align filters, use EXISTS/count distinct |
| DTO query constructor error | Wrong FQCN/order/constructor types | Align record/constructor with SELECT |
| UPDATE query reports select error | Missing @Modifying | Add @Modifying and transaction |
| Dynamic sort causes error | Invalid property or raw expression | Allowlist sort fields |
| Error only happens on certain inputs | Null, blank, wildcard, or empty collection | Test boundary values |
| Query only fails on production DB | Different dialect/native SQL/collation | Test on the same database engine |
| SQL bind logs missing | Wrong logger category/version enabled | Check logger name for Hibernate version |

## 33. Checklist Before Finalizing a Repository Query

- [ ] Identify whether the method uses a derived query, JPQL, native SQL, or custom EntityManager.
- [ ] Verify entity name and Java property names.
- [ ] Check association paths and use underscore when disambiguating nested paths.
- [ ] Verify derived query keywords are compatible with property types.
- [ ] Align named parameter placeholders and @Param names.
- [ ] Verify parameter count and positional parameter order.
- [ ] Do not mix named and positional parameters.
- [ ] Use proper types for enums, date/time, numbers, and collections.
- [ ] Handle null, blank, and empty collections per the business contract.
- [ ] Do not bind parameters to substitute identifiers or ORDER BY fields.
- [ ] Allowlist sort properties and sort directions.
- [ ] Verify Page/countQuery share the same predicates.
- [ ] Verify DTO constructor expression and return type.
- [ ] Use @Modifying for bulk UPDATE/DELETE.
- [ ] Check transactions and persistence context state after bulk queries.
- [ ] Write @DataJpaTest so the provider actually creates/executes the query.
- [ ] Inspect root cause and SQL/bind logs when errors are unclear.
- [ ] Disable sensitive bind parameter logging after diagnosis.

## 34. Conclusion

QueryCreationException indicates that Spring Data could not create a query for a repository method, while the actual cause may be a wrong property path, invalid JPQL, mismatched parameters, or incompatible data types. Other errors only appear when the query runs, such as wrong cardinality, invalid SQL dialect, or a miscounting count query.

Start from the root cause in the stack trace, cross-check the entity mapping against the query and method signature, and verify with repository tests. In JPQL, use Java entity/property names; with named parameters, keep placeholders and @Param consistent; with positional parameters, keep exact order. Handle Pageable, empty collections, nulls, DTO constructors, and modifying queries explicitly. When needed, enable SQL/bind logs in a controlled environment to verify the actual query executed.
