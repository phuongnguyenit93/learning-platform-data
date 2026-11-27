# Combining AND, OR Conditions, and Condition Groups

Spring Data Relational R2DBC provides `Criteria` and `Query` to build dynamic queries in a structured way. `Criteria` describes filter conditions; `Query` wraps conditions along with query options; `R2dbcEntityTemplate` or `R2dbcEntityOperations` executes the query and returns results as `Mono` or `Flux`.

When a query has multiple conditions, you must clearly define which conditions combine with `AND`, which combine with `OR`, and which belong in the same group. A query can return wrong results even if every individual condition is correct when logical grouping is misplaced. Therefore, design the expression according to business rules first, then represent groups using nested `Criteria`.

## 1. Role of `Criteria` and `Query`

`Criteria` represents a condition or a combination of conditions. Each condition typically consists of a property/column, a comparison operator, and a value to compare against. `Query` uses `Criteria` to describe the filter part, and can also hold sorting, limit, and pagination details depending on the API.

Basic flow:

```mermaid
flowchart LR
    A[Business filter inputs] --> B[Build Criteria]
    B --> C[Wrap in Query]
    C --> D[R2dbcEntityTemplate]
    D --> E[Database SQL]
    E --> F[Mono / Flux result]
```

Simple query example:

```java
import static org.springframework.data.relational.core.query.Criteria.where;
import static org.springframework.data.relational.core.query.Query.query;

import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Order> findOpenOrders() {
    Query query = query(where("status").is(OrderStatus.OPEN));

    return template.select(Order.class)
            .matching(query)
            .all();
}
```

`where("status")` starts a condition on the `status` property; `.is(...)` creates an equality comparison. `Query.query(...)` wraps the condition. `select(Order.class)` requests reading the `Order` entity; `.all()` returns `Flux<Order>`.

In these examples, `template` is an `R2dbcEntityTemplate` bean injected into the service. You can use the `R2dbcEntityOperations` interface if you want the business layer to depend on an abstraction. Property names in queries must match entity mapping metadata and the Spring Data Relational version in use; Spring Data uses the mapping context to translate them to the corresponding column names.

## 2. Combining Conditions with AND

`AND` requires all conditions in the group to be true. For example, retrieving only open orders with a total greater than 100:

```java
public Flux<Order> findOpenOrdersAbove(BigDecimal minimumTotal) {
    Criteria criteria = where("status").is(OrderStatus.OPEN)
            .and("total").greaterThan(minimumTotal);

    return template.select(Order.class)
            .matching(Query.query(criteria))
            .all();
}
```

Logically equivalent condition:

```sql
WHERE status = 'OPEN'
  AND total > 100
```

Only rows satisfying both the status and the total amount are returned. If either condition is false, that row is excluded from the results.

Multiple `AND` conditions can be added:

```java
Criteria criteria = where("tenantId").is(tenantId)
        .and("status").is(OrderStatus.OPEN)
        .and("createdAt").greaterThanOrEquals(from)
        .and("total").lessThanOrEquals(maximumTotal);
```

This corresponds to:

```sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
  AND total <= :maximumTotal
```

Combining with `AND` is generally suitable when all conditions are mandatory constraints, such as current tenant, allowed status, time range, and price cap.

## 3. Combining Conditions with OR

`OR` only requires at least one condition in the group to be true. For example, finding orders in `OPEN` or `PENDING` status:

```java
public Flux<Order> findOpenOrPendingOrders() {
    Criteria criteria = where("status").is(OrderStatus.OPEN)
            .or("status").is(OrderStatus.PENDING);

    return template.select(Order.class)
            .matching(Query.query(criteria))
            .all();
}
```

Equivalent condition:

```sql
WHERE status = 'OPEN'
   OR status = 'PENDING'
```

A row only needs to satisfy one of the two statuses. You can use `in(...)` when the goal is simply to check whether one column belongs to a set of values:

```java
Criteria criteria = where("status")
        .in(OrderStatus.OPEN, OrderStatus.PENDING);
```

Semantically, an `IN` condition is equivalent to a chain of equality comparisons joined by `OR` in simple cases. `IN` is usually more concise when the value list is long. If each branch has different conditions, use `OR` and `Criteria` groups.

## 4. Why Is Grouping Conditions Necessary?

When mixing `AND` and `OR`, evaluation order directly affects the result. For example, business rules require:

> Retrieve orders belonging to the current tenant and having status OPEN or PENDING.

The intended expression is:

```sql
WHERE tenant_id = :tenantId
  AND (status = 'OPEN' OR status = 'PENDING')
```

If parentheses are omitted and written as:

```sql
WHERE tenant_id = :tenantId AND status = 'OPEN'
   OR status = 'PENDING'
```

SQL typically gives `AND` higher precedence than `OR`, so the expression is interpreted as:

```sql
WHERE (tenant_id = :tenantId AND status = 'OPEN')
   OR status = 'PENDING'
```

Results may include `PENDING` orders belonging to other tenants. This is a critical bug if `tenantId` is a data isolation or access control boundary.

Practical rule: when a group contains multiple conditions, create a child `Criteria` and combine it with `and(Criteria)` or `or(Criteria)` to express parentheses explicitly. Do not rely on memory of SQL operator precedence to reason about a long builder chain.

## 5. OR Group Inside an AND Condition

For the tenant example above, create a separate status group:

```java
Criteria allowedStatuses = where("status").is(OrderStatus.OPEN)
        .or("status").is(OrderStatus.PENDING);

Criteria criteria = where("tenantId").is(tenantId)
        .and(allowedStatuses);

return template.select(Order.class)
        .matching(Query.query(criteria))
        .all();
```

The `allowedStatuses` group is combined with the tenant condition via `AND`. The logical meaning is:

\[
tenantId = T \;\land\; (status = OPEN \;\lor\; status = PENDING)
\]

Placing the tenant condition outside the OR group is critical: every status branch must belong to the queried tenant.

It can also be written inline without an intermediate variable:

```java
Criteria criteria = where("tenantId").is(tenantId)
        .and(where("status").is(OrderStatus.OPEN)
                .or("status").is(OrderStatus.PENDING));
```

Creating variables for child groups is usually easier to read when conditions are complex or reused.

## 6. AND Groups Inside an OR Condition

Another case is finding orders with status OPEN and a high total, or PENDING orders with high priority:

```sql
WHERE (status = 'OPEN' AND total > 500)
   OR (status = 'PENDING' AND priority = 'HIGH')
```

You can build two separate groups and join them with OR:

```java
Criteria expensiveOpenOrder = where("status").is(OrderStatus.OPEN)
        .and("total").greaterThan(new BigDecimal("500"));

Criteria urgentPendingOrder = where("status").is(OrderStatus.PENDING)
        .and("priority").is(Priority.HIGH);

Criteria criteria = expensiveOpenOrder.or(urgentPendingOrder);

return template.select(Order.class)
        .matching(Query.query(criteria))
        .all();
```

Each branch is an `AND` group; the two groups are combined with `OR`. When reading the code, the variable structure mirrors the logical structure, making it easier to verify than a long chain.

## 7. Multi-Level Nested Groups

A query may require multiple levels of parentheses. For example:

```sql
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND (
       (status = 'OPEN' AND total >= :minimum)
       OR
       (status = 'PENDING' AND priority = 'HIGH')
  )
```

This can be expressed with child groups:

```java
Criteria openAndExpensive = where("status").is(OrderStatus.OPEN)
        .and("total").greaterThanOrEquals(minimumTotal);

Criteria pendingAndUrgent = where("status").is(OrderStatus.PENDING)
        .and("priority").is(Priority.HIGH);

Criteria statusAndBusinessRule = openAndExpensive.or(pendingAndUrgent);

Criteria criteria = where("tenantId").is(tenantId)
        .and("deletedAt").isNull()
        .and(statusAndBusinessRule);
```

This snippet illustrates the grouping structure. Property names and enum types should match your actual entity. Null operators can be represented using the `isNull()`/`isNotNull()` API in supported Spring Data Relational versions; if your project's API differs, use the corresponding Criteria expression per that version's Javadoc.

Avoid creating overly deep nested groups just to mirror every detail of an SQL statement. Name variables according to their business meaning, such as `openAndExpensive`, `pendingAndUrgent`, `visibleOrders`, so readers understand why those conditions are grouped together.

## 8. Dynamically Combining Conditions from Search Parameters

In practice, search requests often have optional fields. For example, a user may enter a status, start date, end date, and maximum total. You should not write a separate query for every parameter combination; append present conditions to `Criteria`.

```java
public Flux<Order> searchOrders(
        Long tenantId,
        OrderStatus status,
        LocalDateTime createdAfter,
        BigDecimal maximumTotal) {

    Criteria criteria = where("tenantId").is(tenantId);

    if (status != null) {
        criteria = criteria.and("status").is(status);
    }

    if (createdAfter != null) {
        criteria = criteria.and("createdAt").greaterThanOrEquals(createdAfter);
    }

    if (maximumTotal != null) {
        criteria = criteria.and("total").lessThanOrEquals(maximumTotal);
    }

    return template.select(Order.class)
            .matching(Query.query(criteria))
            .all();
}
```

`tenantId` is always a mandatory condition. Optional parameters are added only when they have a value. This avoids unintentionally generating `column = null` conditions and keeps the query aligned with input data.

If a business field can legitimately hold null values, distinguish between "filter omitted" and "find rows with a NULL column". These are two distinct requirements. Do not use a single null value to represent both meanings.

## 9. Dynamic OR Condition from a Set of Values

If a user selects multiple statuses, the status list can be passed as a collection of values:

```java
public Flux<Order> findByStatuses(Long tenantId, Collection<OrderStatus> statuses) {
    Criteria criteria = where("tenantId").is(tenantId);

    if (statuses != null && !statuses.isEmpty()) {
        criteria = criteria.and(where("status").in(statuses));
    }

    return template.select(Order.class)
            .matching(Query.query(criteria))
            .all();
}
```

`IN` is usually a concise way to express `status = A OR status = B OR ...`. You must clearly decide behavior when the list is empty: ignore the status condition, return no results, or reject the request. The example above skips the filter when the list is empty; that may not fit every API.

If an empty list must return empty results, handle it explicitly before querying:

```java
if (statuses != null && statuses.isEmpty()) {
    return Flux.empty();
}
```

Do not rely on generating `IN ()`; SQL with an empty list may be invalid or have different semantics depending on how the builder/driver handles it.

## 10. Combining Range Conditions and Multiple Comparisons

A date filter typically consists of a lower bound and an upper bound:

```java
Criteria criteria = where("createdAt").greaterThanOrEquals(from)
        .and("createdAt").lessThan(to);
```

This means `from <= createdAt < to`. Using a half-open interval is often convenient for date filters: inclusive lower bound, exclusive upper bound. For example, to find records within a single day, compute `startOfDay` and `startOfNextDay` in the business timezone and query `>= start` and `< end`.

Ranges can be combined with an OR group:

```java
Criteria customerMatch = where("customerId").is(customerId)
        .or("createdBy").is(userId);

Criteria criteria = where("tenantId").is(tenantId)
        .and("createdAt").greaterThanOrEquals(from)
        .and("createdAt").lessThan(to)
        .and(customerMatch);
```

Here, every result must belong to the tenant and time range, and must satisfy at least one of the two related-party conditions. The OR group is scoped within an overall AND condition.

## 11. Combining Criteria with Sorting and Result Limits

`Criteria` only describes the filter. `Query` can additionally combine sorting and limits to serve search screens:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")))
        .limit(50);

return template.select(Order.class)
        .matching(query)
        .all();
```

This example fetches at most the 50 newest orders matching the condition. Specific `Query` methods and overloads should be checked against your Spring Data Relational version. If multi-page pagination is needed, choose an appropriate pagination API and add a deterministic sort order, typically including a secondary key like ID to avoid arbitrary item shifting across pages.

You should not fetch all results and filter/sort in Java if the database can execute those conditions. Filtering at the database reduces network transfer and the number of objects allocated in the application.

## 12. String Search and Combined Conditions

Criteria supports string comparisons depending on API and dialect, such as `like`, `notLike`, `in`, or equality comparisons. When using `LIKE`, `%` and `_` are wildcard characters; if users enter literal search strings, escape wildcards according to the rules of your database and API.

Conceptual example searching by name or email within the same tenant:

```java
Criteria textMatch = where("name").like("%" + keyword + "%")
        .or("email").like("%" + keyword + "%");

Criteria criteria = where("tenantId").is(tenantId)
        .and(textMatch);
```

Results must belong to the current tenant and have a name or email matching the keyword. Wrapping wildcards around the search value does not mean concatenating data into the SQL statement; Criteria still binds the value as a parameter. Nevertheless, escape `%` and `_` if they must be treated as ordinary characters, and limit keyword length to avoid overly expensive queries.

If case-insensitive search is needed, semantics depend on collation, database, and supported operators. Do not assume `like` is always case-insensitive. You can normalize data, use an appropriate collation, or use a database-specific API as required.

## 13. Never Concatenate User Input Directly into SQL

`Criteria` is designed to represent conditions and values structurally. Pass values through Criteria comparison methods rather than concatenating SQL strings:

```java
// Use Criteria and bound values
Criteria criteria = where("email").is(request.email());
```

Avoid building SQL by directly concatenating input:

```java
// Avoid: user data is concatenated into the SQL statement
String sql = "SELECT * FROM customer WHERE email = '" + request.email() + "'";
```

When `DatabaseClient` and hand-written SQL are needed, use bind parameters. For client-supplied column names or sort directions, bind parameters cannot substitute identifiers; map input through a whitelist of allowed properties. Never allow users to pass arbitrary table names, column names, or SQL fragments.

## 14. Null, Absent Conditions, and SQL Three-Valued Logic

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. Standard comparisons with `NULL`, such as `column = NULL`, do not yield `TRUE`; you must use `IS NULL` or `IS NOT NULL`. Therefore, an omitted filter condition and a condition searching for a null column cannot be treated as identical.

SQL illustration:

```sql
-- Not equivalent to IS NULL
WHERE deleted_at = NULL

-- Properly checks for a missing column value
WHERE deleted_at IS NULL
```

In Criteria, use the null operators provided by your Spring Data version, such as `isNull()` and `isNotNull()` if available in the API. If a request parameter is null because the client omitted the filter, that condition should usually be skipped. If the client asks for rows with a null column, express it explicitly using the `IS NULL` operator.

Conditions involving null also affect `NOT`, `NOT IN`, and comparisons. For instance, `NOT IN` with a value set containing `NULL` may evaluate to `UNKNOWN` for non-matching rows. Cleanse filter sets and define semantics before passing them into a query.

## 15. Separating Criteria Construction from Execution

For complex queries, extract the condition-building method so the service remains readable and testable:

```java
private Criteria buildOrderCriteria(OrderSearchRequest request) {
    Criteria criteria = where("tenantId").is(request.tenantId());

    if (request.from() != null) {
        criteria = criteria.and("createdAt").greaterThanOrEquals(request.from());
    }

    if (request.to() != null) {
        criteria = criteria.and("createdAt").lessThan(request.to());
    }

    if (request.statuses() != null && !request.statuses().isEmpty()) {
        criteria = criteria.and(where("status").in(request.statuses()));
    }

    if (request.minimumTotal() != null) {
        criteria = criteria.and("total").greaterThanOrEquals(request.minimumTotal());
    }

    return criteria;
}

public Flux<Order> search(OrderSearchRequest request) {
    Query query = Query.query(buildOrderCriteria(request));

    return template.select(Order.class)
            .matching(query)
            .all();
}
```

Extracting a builder has several benefits:

- Composition rules can be unit-tested independently of database connectivity.
- Method and variable names express the purpose of each filter.
- Optional conditions are easy to add without turning the service into an overly long builder chain.
- Common condition groups like tenant, active status, or time range can be reused.

Do not place authorization solely in client-controlled filters. Tenant conditions or permission scopes must come from the server-side authenticated context and always be applied regardless of which filters the request sends.

## 16. Testing AND, OR Logic, and Condition Groups

Unit tests for builders should focus on business rules for combinations. Cases you can verify:

1. When only tenant is specified, the query stays scoped to that tenant.
2. When status is OPEN or PENDING, both statuses are accepted.
3. When combining tenant AND a status OR group, data from other tenants never leaks into results.
4. When two AND branches are joined by OR, each branch must satisfy all of its own conditions.
5. When an optional filter is absent, the corresponding condition is omitted per the API contract.
6. When a filter list is empty, behavior is well-defined and does not produce `IN ()`.
7. When a filter requests SQL NULL, null checks are used instead of equality comparison with null.

For integration tests, intentionally seed data to catch parenthesis bugs. For example, create a PENDING row belonging to another tenant. If the query accidentally becomes `(tenant = A AND status = OPEN) OR status = PENDING`, the wrong-tenant row will appear and the test will catch the bug.

Service-level test example with `StepVerifier`:

```java
StepVerifier.create(orderService.searchOrders(tenantA))
        .expectNextMatches(order ->
                order.getTenantId().equals(tenantA)
                        && (order.getStatus() == OrderStatus.OPEN
                        || order.getStatus() == OrderStatus.PENDING))
        .verifyComplete();
```

This is only an example checking returned elements. A thorough integration test should seed both valid and invalid rows to ensure the query properly excludes invalid cases, not merely confirming that a valid row shows up.

## 17. Performance and Index Usage

Combining multiple conditions can affect the query plan. The database may use a single index, composite index, bitmap scan, or other strategy depending on the engine and data statistics. There is no rule that every AND/OR condition will always use a separate index.

Some notes:

- Tenant conditions typically have high selectivity and appear in many queries; composite indexes may need to lead with `tenant_id` depending on query patterns.
- `OR` across different columns can complicate the query plan; inspect `EXPLAIN` on realistic data.
- `LIKE '%keyword%'` rarely leverages standard B-tree indexes; full-text search, trigram indexes, or database-specific solutions may be needed.
- Transformations on columns inside conditions can reduce index usability unless a matching functional index exists.
- Overly broad or unbounded filters can return large volumes of data; combine with limits/pagination and deterministic ordering.

Never optimize by altering AND/OR logic. Ensure the expression matches business requirements first, then use query plans and metrics to tune indexes or query patterns.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting to group OR inside an AND condition | Data outside tenant/scope may leak into results | Create a child `Criteria` and combine with `and(group)` |
| Using OR instead of AND | Results broader than business rules allow | Write out the logical expression first, then convert to Criteria |
| Chaining overly long builder expressions | Hard to understand precedence and error-prone to edit | Extract groups into meaningfully named variables |
| Null parameters added as comparisons | Query lacks intended semantics | Only add filters when requested; handle null explicitly |
| Empty `IN` list | Invalid SQL or unexpected behavior | Clearly define whether to return empty, omit filter, or error |
| Letting clients pass arbitrary column names | Out-of-scope queries or identifier injection risk | Use a whitelist of allowed properties |
| Using `LIKE` without handling wildcards | Broader results than literal keyword | Escape `%` and `_` according to proper rules |
| Testing only one valid row | Misses OR conditions leaking wrong data | Seed counterexample data for each logical branch |
| Unbounded filters | Increased database and memory load | Add pagination/limit and monitor query plans |

## 19. Best Practices

- Use `Criteria` to represent individual conditions and `Query` to encapsulate the query.
- Use `and(...)` when all conditions are mandatory; use `or(...)` when only one branch needs to be true.
- Create nested `Criteria` for groups needing parentheses, especially when mixing AND with OR.
- Place tenant, access control, and data scope conditions in the mandatory outer group outside OR branches.
- Name group variables after their business meaning to keep code readable.
- Add optional conditions only when the parameter is actually provided; distinguish omitting a filter from searching for SQL NULL.
- Use `IN` for one column matching any of several values; define empty-list behavior.
- Use bind parameters via Criteria or DatabaseClient; never concatenate user input into SQL.
- Whitelist client-selected property names, sort columns, and identifiers.
- Test both valid data and counterexamples that could leak when grouping is wrong.
- Review query plans and indexes after logic is verified; do not assume OR or AND always uses indexes in a fixed way.
- Verify Criteria/Query APIs against your project's Spring Data Relational version.

## 20. Conclusion

`Criteria` and `Query` help build dynamic queries in Spring Data Relational R2DBC. `AND` combines mandatory conditions; `OR` allows one of several branches to hold. When mixing both operators, group conditions using nested `Criteria` to express parentheses accurately and prevent unintended scope expansion.

Start from the business expression, extract meaningful groups, attach optional filters based on parameter state, and keep security constraints like tenant in the mandatory outer group. Combining counterexample testing, parameter binding, and query plan review keeps queries logically sound and maintainable as search requirements evolve.
