# Dynamic Sorting, Query Parsers, and Version-Specific Limits

Spring Data JPA lets you decide result ordering at repository call time using `Sort` or `Pageable`. This is useful when a screen allows users to sort by creation date, amount, status, or multiple columns at once. However, `Sort` does not accept arbitrary strings: sort properties must be valid for the entity or query aliases. For function expressions and native SQL, Spring Data also has to parse or rewrite the query to inject `ORDER BY` and generate a count query. That capability depends on query structure, parsers present on the classpath, and the Spring Data JPA version.

This lesson uses a `PurchaseOrder` example to cover `Sort`, `Sort.Order`, `Pageable`, aliases, `JpaSort.unsafe`, protecting API inputs, differences between the derived query parser and query enhancers, regex/JSqlParser options for native queries, `countQuery`, `QueryRewriter`, and version limits to verify when upgrading.

## 1. Static Sorting vs. Dynamic Sorting

Static sorting is defined directly in the method name:

~~~java
List<PurchaseOrder> findByStatusOrderByCreatedAtDesc(
    OrderStatus status
);
~~~

This method always sorts by `createdAt` descending. Callers cannot choose a different column or direction.

Dynamic sorting accepts `Sort` as a parameter:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Callers can pick the order at runtime:

~~~java
repository.findByStatus(
    OrderStatus.PAID,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

Dynamic sorting fits data tables with multiple sort options. The query and filter conditions remain defined by the repository; `Sort` appends the `ORDER BY` clause for that specific call.

Two concepts to distinguish:

- **OrderBy in method names**: fixed order declared in the method name.
- **Sort**: dynamic order passed when invoking the repository.

If the order is always fixed and simple, `OrderBy` is easy to read. If ordering depends on user choice or varies by use case, use `Sort`.

## 2. Building Sort With Single or Multiple Criteria

Spring Data provides `Sort` and `Sort.Order`:

~~~java
Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt")
);

Sort byAmountThenDate = Sort.by(
    Sort.Order.desc("total"),
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);

Sort ascending = Sort.by(
    Sort.Direction.ASC,
    "customerName"
);

Sort noSorting = Sort.unsorted();
~~~

Each `Order` describes a property and sort direction:

- **asc(property)**: ascending.
- **desc(property)**: descending.
- **ignoreCase()**: requests case-insensitive comparison for string properties.
- **nullsFirst()**: hints to place null values first.
- **nullsLast()**: hints to place null values last.
- **nullsNative()**: lets the database/provider use its default handling.

The declaration order of `Order` items matters. In `byAmountThenDate`, the database sorts by `total` first; ties are broken by `createdAt`; remaining ties are broken by `id`.

Always add a unique key as the final criterion for deterministic ordering. Sorting solely by `createdAt` can leave records with identical timestamps in an unspecified relative order. Deterministic ordering is especially important for pagination.

## 3. Sort.Order, String Casing, and NULL Handling

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("customerName").ignoreCase().nullsLast(),
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("id")
);
~~~

**ignoreCase()** is helpful for string names or codes. Do not apply it arbitrarily to numbers, dates, or non-String types.

`nullsFirst()`, `nullsLast()`, and `nullsNative()` express a preference for `NULL` placement. They act as hints to the query layer; how they translate to SQL and whether they are supported depend on the JPA provider, database, and dialect. Verify actual results on your target DBMS, especially if the application runs across multiple databases.

If business rules require identical `NULL` ordering across every environment, you can write a `CASE` expression in JPQL or native SQL to enforce it explicitly. In that case, check how the parser handles dynamic `Sort` injection and use controlled expressions.

## 4. Accepting Sort Directly in Repositories

Simple entity example:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    protected PurchaseOrder() {
    }

    // Constructors and getters are omitted in the repository example.
}
~~~

Repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );

    List<PurchaseOrder> findByCustomer_Id(
        Long customerId,
        Sort sort
    );
}
~~~

Invocation:

~~~java
List<PurchaseOrder> orders = repository.findByStatus(
    OrderStatus.PAID,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

`Sort` properties use the entity's Java property names, not SQL column names. Even if `createdAt` is mapped with `@Column(name = "created_at")`, `Sort` still uses `createdAt`.

For nested paths, you can use property paths like `customer.name` when valid in the mapping. Sorting across associations can cause the query to generate a `JOIN`. Inspect the generated SQL and avoid sorting along collection-valued paths where ordering semantics are unclear.

## 5. Combining Sort With Pageable

When both sorting and pagination are needed, pass `Pageable`:

~~~java
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

Creating `Pageable`:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(
    0,
    20,
    sort
);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.PAID, pageable);
~~~

`PageRequest.of(page, size, sort)` uses zero-based page indices. In the example, page `0` and size `20` request the first page with up to 20 results.

`Page` provides:

- `getContent()`: list of elements for the current page.
- `getNumber()`: current page number.
- `getSize()`: requested page size.
- `getTotalElements()`: total elements from the count query.
- `getTotalPages()`: total page count.
- `hasNext()` and `hasPrevious()`: check for next/previous pages.

If total elements and total pages are not needed, `Slice<T>` can avoid the count query. `Slice` still supports `Pageable` and `Sort`, focusing only on whether a next page exists.

Never accept unbounded page sizes from clients. Validate the page index, cap the maximum page size, and restrict allowed sort properties.

## 6. Sort With JPQL @Query

`Sort` can also be passed to methods annotated with `@Query`:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.status = :status
        """)
    List<PurchaseOrder> searchByStatus(
        @Param("status") OrderStatus status,
        Sort sort
    );
}
~~~

Spring Data appends the `ORDER BY` clause corresponding to `Sort` to the declared query.

Properties used in `Sort` must be valid references within the query: typically an entity property path or an alias declared in `SELECT`. An expression that cannot be referenced validly results in an error.

Valid example:

~~~java
repository.searchByStatus(
    OrderStatus.PAID,
    Sort.by(Sort.Order.desc("createdAt"))
);
~~~

JPQL uses entity names and Java properties. Do not write table name `purchase_orders` or column `created_at` in a JPQL `Sort` when the entity property is `createdAt`.

If the query declares aliases in a projection, you can sort by those aliases as shown next.

## 7. Sorting by Projection Aliases

Suppose a query returns order IDs and reference code lengths:

~~~java
@Query("""
    select o.id as orderId,
           length(o.reference) as referenceLength
    from PurchaseOrder o
    where o.status = :status
    """)
List<Object[]> findOrderMetrics(
    @Param("status") OrderStatus status,
    Sort sort
);
~~~

You can sort by the alias `referenceLength`:

~~~java
List<Object[]> rows = repository.findOrderMetrics(
    OrderStatus.PAID,
    Sort.by(Sort.Order.desc("referenceLength"))
);
~~~

An alias is a valid reference in `ORDER BY` for eligible queries. When using DTO projections, verify that the alias or constructor expression is compatible with the result type.

`DISTINCT`, `GROUP BY`, and multi-column projections can complicate sort semantics. For instance, when selecting aggregated values, only sort by aliases present in `SELECT` or expressions permitted by JPQL. Test queries against a real provider rather than assuming all aliases are handled identically by the parser.

## 8. Function Expressions and JpaSort.unsafe

Standard `Sort` is validated to ensure the sort property resolves validly. Function expressions like `LENGTH(o.reference)` are not simple property paths:

~~~java
// Do not use Sort.by with arbitrary function expressions:
Sort.by("LENGTH(reference)");
~~~

For eligible string-based queries, Spring Data JPA provides `JpaSort.unsafe`:

~~~java
List<PurchaseOrder> orders = repository.searchByStatus(
    OrderStatus.PAID,
    JpaSort.unsafe("LENGTH(o.reference)")
);
~~~

`JpaSort.unsafe` lets you pass an expression into `ORDER BY` without standard property-path validation. This is an intentional escape hatch and must be used carefully.

Never pass user-supplied sort strings directly into `JpaSort.unsafe`. Column names, functions, operators, and sort directions are query structure, not bound parameter values. Only pick from fixed expressions reviewed by developers.

Whenever possible, prefer an alias declared in `SELECT`:

~~~java
Sort.by("referenceLength");
~~~

Using an alias is cleaner and safer than injecting arbitrary expressions into a query.

`JpaSort.unsafe` is not a tool that makes any SQL/JPQL valid. The expression must still be supported by the JPA provider or query context. Some Criteria API-based execution paths have limitations for expressions like subqueries, `TREAT`, or `CAST`; consult the documentation for your specific version.

## 9. Protecting Sort Parameters Received From APIs

A common security vulnerability is taking a sort parameter directly from an HTTP request and building `Sort` or `JpaSort.unsafe` from that raw string.

Example request:

~~~text
GET /orders?sort=createdAt,desc
~~~

Never treat arbitrary property names sent by a client as trustworthy. Map public sort keys to allowed properties:

~~~java
private static final Map<String, String> ALLOWED_SORTS = Map.of(
    "newest", "createdAt",
    "amount", "total",
    "status", "status"
);

public Sort resolveSort(String requestedField, String requestedDirection) {
    String property = ALLOWED_SORTS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction direction =
        "asc".equalsIgnoreCase(requestedDirection)
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    return Sort.by(new Sort.Order(direction, property));
}
~~~

This snippet illustrates field whitelisting; in a real application, explicitly handle invalid directions, null values, multiple sort criteria, and appropriate HTTP error responses.

Rules:

- Whitelist permitted sort fields.
- Never concatenate raw input into JPQL or SQL.
- Never pass unvalidated input to `JpaSort.unsafe`.
- Cap the number of sort criteria.
- Separate public sort keys from internal entity property names.
- Never allow sorting by confidential fields or data users are unauthorized to view.

## 10. Method Name Parsers and Query Parsers Are Two Separate Mechanisms

When discussing parsers in Spring Data JPA, distinguish between two mechanisms.

The **derived query parser** reads repository method names and splits subject, predicate, and property paths. For example, `findByStatusOrderByCreatedAtDesc` is parsed into a `status` filter and descending `createdAt` ordering. The parser checks whether those properties exist in the domain model.

The **query enhancer/parser** processes query strings declared via `@Query` or native SQL. It may need to inspect query structure to append `Sort`, derive a count query, or rewrite projections.

The two solve different problems:

| Mechanism | Input | Responsibility |
|---|---|---|
| Derived query parser | Method name | Builds a query from properties and keywords |
| JPQL query enhancer | JPQL/HQL string | Parses and augments queries with sort or count |
| Native query enhancer | SQL string | Parses SQL to rewrite sort/count when supported |
| `QueryRewriter` | Prepared query string | Allows the application to modify queries before passing to `EntityManager` |

A derived query method may work seamlessly while a complex native `@Query` still fails to rewrite properly. Never infer native parser capabilities from the fact that the derived query parser supports a property path.

## 11. Native Queries and Appending ORDER BY

With native SQL, table and column names are database names:

~~~java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.status = :status
        """,
    countQuery = """
        select count(*)
        from purchase_orders o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findNativeByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

You can pass a `Pageable` with a `Sort` to request dynamic sorting. However, Spring Data must rewrite the SQL string to append `ORDER BY`. Success depends on SQL complexity and the configured parser.

With native queries, keep in mind:

- `Sort` must reference SQL columns or aliases valid within the query.
- Java property names and SQL column names can differ.
- Aliases must be clear, unique, and collision-free.
- Vendor-specific SQL may not be recognized by the parser.
- Queries with CTEs, `UNION`, nested subqueries, or window functions require thorough checking.
- Always run integration tests against the actual production database.

If a query has a fixed `ORDER BY` and does not need dynamic sorting, declaring `ORDER BY` directly in SQL is simpler.

## 12. Regex Parser and JSqlParser

Spring Data JPA can use different parsing engines for native SQL.

The **regex-based query enhancer** relies on simpler pattern-matching rules. It handles many straightforward SQL queries well, but it is not a full SQL parser. Queries with nested structures, CTEs, `UNION`, or specialized syntax can cause sort/count injection to behave inaccurately or fail.

**JSqlParser** is a standalone SQL parsing library. When present on the classpath and selected, Spring Data JPA can use it to parse more complex native queries. However, JSqlParser also has syntax and version limits; it is not guaranteed to understand every proprietary extension of every database.

In Spring Data JPA 3.5.x documentation, native parser selection is described via this property:

~~~properties
spring.data.jpa.query.native.parser=auto
~~~

Values listed in the 3.5.13 documentation:

| Value | Behavior |
|---|---|
| `auto` | Automatically picks a suitable parser; this is the default |
| `regex` | Uses the built-in regex-based query enhancer |
| `jsqlparser` | Uses JSqlParser |

This property can be set in `spring.properties` or as a system property per the corresponding version's documentation. Do not mistake this setting for a universal option across every Spring Data JPA version.

When selecting `jsqlparser`, add a JSqlParser dependency version compatible with your Spring Data JPA release. Do not arbitrarily pin a version if your project's dependency management already manages it. Check the dependency tree and release notes during upgrades.

## 13. Count Queries and Pagination Limits

When a repository returns `Page<T>`, Spring Data needs the total element count to compute `totalElements` and `totalPages`. It may attempt to derive a count query from the main query.

Simple native queries can declare `countQuery` explicitly:

~~~java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.status = :status
        """,
    countQuery = """
        select count(*)
        from purchase_orders o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findPageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

For complex queries, declare `countQuery` explicitly instead of relying solely on automatic derivation. The count query must preserve the same filter conditions as the data query while returning the appropriate count; it generally does not need `ORDER BY`.

If the query contains a `JOIN` that multiplies rows, `countQuery` must count the proper business unit. For example, counting unique entities may require `COUNT(DISTINCT o.id)` rather than `COUNT(*)`.

An important distinction: **countQuery and dynamic sorting are separate concerns**. Declaring `countQuery` lets Spring compute the total count; it does not guarantee the parser can inject `ORDER BY` into a complex native query. If the query enhancer cannot rewrite the SQL, simplify the query, choose an appropriate parser, or move to a custom repository.

## 14. QueryRewriter and Custom Repositories

If you need to modify a query before it is sent to `EntityManager`, Spring Data JPA provides `QueryRewriter` in versions supporting that API.

Illustrative example:

~~~java
public class OrderQueryRewriter implements QueryRewriter {

    @Override
    public String rewrite(String query, Sort sort) {
        // Only perform controlled modifications.
        return query;
    }
}
~~~

A repository can declare `queryRewriter` on `@Query` in supported versions:

~~~java
@Query(
    value = "select o from PurchaseOrder o",
    queryRewriter = OrderQueryRewriter.class
)
List<PurchaseOrder> findWithCustomRewrite(Sort sort);
~~~

`QueryRewriter` is a final extension point for altering the query string. It is not a general-purpose SQL parser and does not guarantee the rewritten query is valid. If assembling `ORDER BY` yourself, enforce a whitelist, handle aliases, and preserve valid syntax for the query type.

When a query becomes too complex, a custom repository is often a better fit:

- Use `EntityManager` and the Criteria API for dynamic JPA queries.
- Use `JdbcTemplate` for dynamic SQL requiring direct control.
- Use Querydsl or a dedicated query library if already adopted by the project.
- Move queries into database views or stored procedures when architecturally appropriate.

A custom repository gives explicit control over the parser, query string, parameters, and sort order instead of relying on automatic rewriting of complex SQL strings.

## 15. Spring Data JPA Version-Specific Limits

Do not assume a `Sort`/native parser example behaves identically across all release trains. When reading documentation, consult the exact version your project uses.

| Area | Version-Specific Checks |
|---|---|
| `Sort` and `Pageable` | Repository signatures, property path support, projections, and return types |
| `JpaSort.unsafe` | API availability, expression validation rules, and query types |
| Native query enhancer | Ability to append `ORDER BY` and derive count queries |
| Native parser selection | Configuration property name and `auto`/`regex`/`jsqlparser` values |
| JSqlParser | Compatible library version and supported SQL syntax |
| `@NativeQuery` | Whether the annotation exists in the active release or `@Query(nativeQuery = true)` is needed |
| `QueryRewriter` | API, annotation attribute, and bean registration mechanism in that release |
| Scroll API | Which query methods allow scrolling and keyset/offset limits |

Practical milestones:

- **`Sort` and `Pageable`** are foundational Spring Data APIs used broadly across many releases.
- Official **Spring Data JPA 3.5.13** documentation describes the `spring.data.jpa.query.native.parser` property with options `auto`, `regex`, and `jsqlparser`.
- Current **Spring Data JPA 4.1.0** documentation continues covering `Sort`, `JpaSort`, and native query enhancement. Even on newer versions, verify compatibility across Spring Framework, the JPA provider, and the parser.
- Dedicated annotations such as **`@NativeQuery`** may not exist in older releases. **`@Query(nativeQuery = true)`** is the more widely compatible option across versions.
- **Spring Data JPA 3.5.13** documentation notes that scrolling with string-based query methods is not yet supported. If you need scrolling over large result sets, verify support in your exact version before designing the API.
- Configuration property names, default parsers, and JSqlParser dependencies can change across releases. Never copy settings from a newer version into an older project without checking.

When using Spring Boot, let Spring Boot dependency management manage a compatible Spring Data release train. Never upgrade `spring-data-jpa` or JSqlParser individually beyond the managed set without checking compatibility matrices and release notes.

## 16. Keyset Scrolling and Deterministic Ordering

With very large datasets, offset pagination can become expensive because the database must skip many rows before reaching the target page. Keyset scrolling uses the sort field values of the last element on the previous page to resume querying.

For keyset scrolling to work reliably:

- `Sort` must produce a deterministic order and include a unique key as a tie-breaker.
- Keyset properties used for comparison must be non-null as required by the API/provider.
- Sort properties must be present in the result so the framework can extract the keyset.
- Database indexes should align with filter conditions and sort ordering.
- When using projections, include the sort fields in the projection.
- Check version limits for `@Query` string-based methods.

Per the 3.5.13 documentation, the Scroll API supports query methods, Query by Example, and Querydsl; scrolling with string-based query methods was not supported in that release's documentation. Therefore, do not assume every `@Query` string can be combined with keyset scrolling.

## 17. Testing Sort and Parsers

An integration test suite should verify multiple layers of behavior:

**Basic Sort**

- Passing `ASC` and `DESC`.
- Passing multiple `Order` entries.
- Verifying tie-breaker ordering by `id`.
- Sorting by nested properties.
- Testing `ignoreCase` and null handling on the target database.

**JPQL**

- Sorting by entity properties.
- Sorting by projection aliases.
- Verifying `Sort.by` rejects invalid function expressions.
- Testing `JpaSort.unsafe` with controlled static expressions.

**Native SQL**

- Sorting simple native queries.
- Sorting by SQL column names or aliases.
- Testing both `regex` and `JSqlParser` if the project supports both configurations.
- Testing CTEs, `UNION`, subqueries, or vendor-specific SQL if used by real queries.
- Verifying `countQuery` and `Page.getTotalElements()`.

**API and Security**

- Rejecting fields outside the allowlist.
- Rejecting or normalizing invalid sort directions.
- Enforcing caps on page size and sort criteria count.
- Preventing raw input from reaching `JpaSort.unsafe`.

Do not test solely on H2 if production runs PostgreSQL, MySQL, or SQL Server. Even if the parser generates the same query, dialects, collations, `NULL` ordering, and SQL syntax on a real database can differ.

## 18. Common Pitfalls and Remedies

**1. Sort reports property not found**

Check the entity's Java property name—do not use the SQL column name. If the query uses an alias, ensure the alias is declared and validly referenced.

**2. Sort.by rejects LENGTH(...)**

Standard `Sort` only accepts valid property paths or aliases. Use a `SELECT` alias or `JpaSort.unsafe` with a controlled static expression.

**3. Native query ignores or fails on dynamic Sort**

Check the parser, SQL structure, column/alias names, and Spring Data JPA version. For complex SQL, test JSqlParser if compatible or move to a custom repository.

**4. Page returns wrong totalElements**

Inspect the count query. If a `JOIN` multiplies rows, the count query may need `COUNT(DISTINCT primaryKey)`. Ensure the count query's filter conditions match the main query.

**5. Query runs but ordering is unstable**

Add a unique key as the final sort criterion, such as `createdAt DESC, id DESC`. Without a tie-breaker, records with identical sort values can shift order between runs.

**6. NULL values sort differently across environments**

Null handling can depend on the database and provider. Use `CASE` or explicit expressions when business logic demands consistent behavior across DBMSs, and test on real databases.

**7. Parser fails on CTE or UNION**

Do not assume the regex enhancer supports full SQL. Test JSqlParser and the exact syntax; if still unsupported, declare explicit queries/counts or switch to a custom repository.

**8. Users can sort by arbitrary fields**

Whitelist public sort keys. Never concatenate request parameters directly into queries and never pass raw input to `JpaSort.unsafe`.

**9. Upgrading versions alters parser behavior**

Read release notes, inspect the dependency tree, and review documentation for the target version. Run integration tests for all native queries using dynamic sorting/counting before releasing.

## 19. Workflow for Implementing Dynamic Sorting

When adding dynamic sorting to a screen:

1. Identify which fields users genuinely need to sort by.
2. Map public sort keys to valid Java properties or query aliases.
3. Define a default order and include a unique tie-breaker.
4. Choose `Sort` if only ordering is needed; choose `Pageable` if pagination is needed.
5. For JPQL `@Query`, verify property paths and aliases.
6. For function expressions, prefer aliases; only use `JpaSort.unsafe` for static expressions.
7. For native SQL, inspect the parser, columns/aliases, and query complexity.
8. For native `Page`, declare `countQuery` explicitly whenever the query is non-trivial.
9. Verify parser configuration and JSqlParser compatibility for your release train.
10. Write integration tests against the target database.
11. Check indexes and execution plans on large datasets.
12. Re-read documentation and release notes whenever upgrading Spring Data JPA.

## 20. Self-Assessment Checklist

- [ ] I can distinguish static `OrderBy` from dynamic `Sort`.
- [ ] I know how to build `Sort` with single or multiple `Order` criteria.
- [ ] I know how to combine `Sort` with `Pageable` and `PageRequest`.
- [ ] I use Java property names rather than SQL column names in JPQL `Sort`.
- [ ] I know how to sort by projection aliases.
- [ ] I understand the limits of `Sort.by` with function expressions.
- [ ] I know when to use `JpaSort.unsafe` and how to protect inputs.
- [ ] I distinguish the derived query parser from query enhancers.
- [ ] I understand native SQL may require `regex` or `JSqlParser`.
- [ ] I know how to configure the native parser for the supported release.
- [ ] I distinguish `countQuery` from dynamic `ORDER BY`.
- [ ] I know when to reach for `QueryRewriter` or a custom repository.
- [ ] I understand tie-breakers and deterministic ordering for pagination.
- [ ] I check differences across Spring Data JPA versions and databases.
- [ ] I have integration tests covering `Sort`, native queries, parsers, and count queries.

## 21. Review Questions

**1. How does Sort differ from OrderBy in a method name?**

`OrderBy` defines a fixed order in the method name. `Sort` is an object passed when invoking the repository to choose ordering dynamically.

**2. Why can Sort.by("created_at") fail on an entity with a createdAt field?**

JPQL `Sort` typically expects Java property names. SQL column name `created_at` is only valid in a native SQL context with that matching column or alias.

**3. When should you use JpaSort.unsafe?**

When you need a sort expression like `LENGTH(property)` that a standard property path cannot represent. Only use controlled static expressions; never pass raw client input.

**4. How does a query enhancer differ from the derived query parser?**

The derived query parser translates method names into query conditions. A query enhancer parses `@Query`/native SQL strings to support sorting, counting, or rewriting.

**5. Why might complex native SQL fail to receive dynamic Sort automatically?**

Because Spring Data is not a general-purpose SQL parser. The regex enhancer only handles simple structures well; complex syntax requires a capable parser or a custom query implementation.

**6. Does JSqlParser guarantee support for every database's SQL?**

No. It handles many SQL constructs, but support still depends on library version and syntax. Proprietary database extensions must be tested.

**7. Does countQuery fix dynamic sorting errors?**

No. `countQuery` handles counting total results for `Page`. Injecting `ORDER BY` into the data query is a separate step and still depends on the query enhancer/parser.

**8. Why add id as the final sort criterion?**

If multiple rows share the primary sort value, the database does not guarantee their relative order. A unique key provides deterministic ordering, especially during pagination.

**9. When should you switch to a custom repository?**

When the query is too complex, the parser cannot rewrite it safely, you need direct SQL control, or database-specific optimizations are required. You can use `EntityManager`, the Criteria API, or `JdbcTemplate`.

By understanding `Sort`, `Pageable`, and query parser limitations, you can build flexible result ordering while keeping properties, stability, performance, security, and cross-version Spring Data JPA compatibility under control.

## References

- [Spring Data JPA 3.5 — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html)
- [Spring Data JPA — JPA Query Methods (current reference)](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [JSqlParser project](https://github.com/JSQLParser/JSqlParser)
- [Spring Data JPA project and release information](https://github.com/spring-projects/spring-data-jpa)