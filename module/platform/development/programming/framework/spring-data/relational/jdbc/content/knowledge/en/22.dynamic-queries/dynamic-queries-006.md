# count and exists from the Same Set of Conditions

In Spring Data JDBC, a search screen or business use case often needs to know two things about the same set of aggregates: how many aggregates match the conditions, and whether at least one matching aggregate exists.

For example, an order management page might display the total number of pending orders while also checking whether any orders require staff attention. If each operation builds its own conditions separately, they can gradually drift apart as business rules evolve. The count and existence results would then no longer describe the same dataset.

Spring Data JDBC provides `JdbcAggregateTemplate.count(Query, Class<T>)` and `JdbcAggregateTemplate.exists(Query, Class<T>)`. You can build one `Query` object from `Criteria`, then pass that exact object to both methods. This keeps both operations using the same condition definition.

## 1. count and exists Solve Different Needs

`count` returns the number of aggregates matching the conditions. The return type is `long`, suited for counts that may exceed the `int` range.

`exists` returns a `boolean`:

- `true` if at least one aggregate matches the conditions.
- `false` if no aggregate matches the conditions.

Both methods operate on the aggregate type passed in, rather than automatically counting every row across all member tables of the aggregate.

| Need | Method |
|---|---|
| Display total matching orders | `count(query, PurchaseOrder.class)` |
| Check if any orders need processing | `exists(query, PurchaseOrder.class)` |
| Check aggregate by ID | `existsById(id, PurchaseOrder.class)` |
| Count all aggregates of a type | `count(PurchaseOrder.class)` |

Avoid calling `count(...) > 0` when you only need to know whether data exists. `exists(...)` expresses the intent directly and returns a boolean. Similarly, if you only need the count, do not load all aggregates with `findAll(...)` just to count them in Java.

### 1.1. APIs on JdbcAggregateTemplate

`JdbcAggregateTemplate` implements `JdbcAggregateOperations`. The two dynamic query methods have the general signatures:

```java
<T> long count(Query query, Class<T> domainType);

<T> boolean exists(Query query, Class<T> domainType);
```

Both accept:

- `query`: object describing the query conditions; must not be null.
- `domainType`: aggregate root class to count or check; must not be null.

Example:

```java
long count = aggregateTemplate.count(
    query,
    PurchaseOrder.class
);

boolean hasMatch = aggregateTemplate.exists(
    query,
    PurchaseOrder.class
);
```

These two APIs were introduced in **Spring Data Relational 3.0**. If your project uses an older release train, check the Javadoc for your exact version before using them.

## 2. Query and Criteria

`Criteria` represents conditions in the WHERE clause. `Query` wraps Criteria along with other components a query may need, such as projection columns, sort, limit, and offset.

Example of a simple condition:

```java
Criteria criteria = Criteria.where("status").is("PENDING");

Query query = Query.query(criteria);
```

This condition corresponds in SQL to:

```sql
WHERE status = 'PENDING'
```

The query can then be used for both operations:

```java
long pendingCount =
    aggregateTemplate.count(query, PurchaseOrder.class);

boolean hasPending =
    aggregateTemplate.exists(query, PurchaseOrder.class);
```

Because both receive the same `Query`, filter conditions are defined in one place. If customer or creation-date conditions are added later, only the query construction needs to change.

### 2.1. Query and Criteria Are Immutable APIs

The fluent APIs of `Query` and `Criteria` create new objects when chaining conditions or options. They do not mutate the original instance.

Example:

```java
Query baseQuery = Query.query(
    Criteria.where("status").is("PENDING")
);

Query limitedQuery = baseQuery.limit(20);
```

`baseQuery` remains the original query; `limitedQuery` is a new query with the limit applied. Therefore, when adding configuration, assign the returned value:

```java
query = query.limit(20);
```

The following discards the change:

```java
query.limit(20); // Returned value is ignored.
```

For reusing the same conditions across count and exists, build a complete filter query and keep that reference to pass to both methods.

## 3. Creating a Simple Query and Reusing It

Suppose the orders table has `status` and `customer_id` columns. We want to count and check pending orders for a customer.

```java
Criteria criteria = Criteria.where("status").is("PENDING")
    .and("customer_id").is(customerId);

Query query = Query.query(criteria);

long count = aggregateTemplate.count(
    query,
    PurchaseOrder.class
);

boolean exists = aggregateTemplate.exists(
    query,
    PurchaseOrder.class
);
```

Both calls share the same two conditions:

1. Status is `PENDING`.
2. `customer_id` equals the supplied customer ID.

There is no need to rewrite Criteria a second time for exists.

### 3.1. Example in an Application Service

```java
@Service
public class OrderQueryService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public OrderQueryService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    public PendingOrderSummary summarizePendingOrders(Long customerId) {
        Query query = Query.query(
            Criteria.where("status").is(OrderStatus.PENDING)
                .and("customer_id").is(customerId)
        );

        long count = aggregateTemplate.count(
            query,
            PurchaseOrder.class
        );

        boolean exists = aggregateTemplate.exists(
            query,
            PurchaseOrder.class
        );

        return new PendingOrderSummary(count, exists);
    }
}

public record PendingOrderSummary(
    long count,
    boolean exists
) {}
```

The service creates the query once and reuses it. When filter conditions change, both count and exists automatically use the updated definition.

The example assumes the entity maps `customerId` to column `customer_id` and has a `status` field. Use column/property names aligned with your actual mapping, especially when `@Column` or custom naming strategies are used.

## 4. Building Dynamic Conditions from Filters

In practice, search filters often have multiple optional fields. A user might enter only status, or combine status, customer, creation date, and minimum total.

We can build `Criteria` incrementally, adding a condition only when its corresponding filter has a value.

```java
public record OrderFilter(
    OrderStatus status,
    Long customerId,
    LocalDateTime createdFrom,
    BigDecimal minimumTotal
) {}
```

Query builder method:

```java
private Query buildQuery(OrderFilter filter) {
    Criteria criteria = Criteria.empty();

    if (filter.status() != null) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.customerId() != null) {
        criteria = criteria.and("customer_id").is(filter.customerId());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("created_at")
            .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.minimumTotal() != null) {
        criteria = criteria.and("total")
            .greaterThanOrEquals(filter.minimumTotal());
    }

    return criteria.isEmpty()
        ? Query.empty()
        : Query.query(criteria);
}
```

Once built, the service can reuse the query:

```java
public OrderSearchSummary summarize(OrderFilter filter) {
    Query query = buildQuery(filter);

    long count = aggregateTemplate.count(
        query,
        PurchaseOrder.class
    );

    boolean exists = aggregateTemplate.exists(
        query,
        PurchaseOrder.class
    );

    return new OrderSearchSummary(count, exists);
}
```

When no filter fields are provided, the method returns `Query.empty()`. An empty query has no filter conditions, so counting/existence applies to the entire aggregate type. If business rules disallow unfiltered searches, validate the filter before building the query and return an appropriate validation error.

### 4.1. Add Conditions Only When Values Are Present

Do not accidentally turn an absent filter field into a comparison against null.

For example:

```java
Criteria.where("customer_id").is(filter.customerId());
```

If `customerId` is null because the user did not select a customer, this condition no longer means "skip the customer filter". It can become a condition matching NULL values.

Instead:

```java
if (filter.customerId() != null) {
    criteria = criteria.and("customer_id").is(filter.customerId());
}
```

If a user genuinely wants rows where a column is NULL, express that intent explicitly with `isNull()`:

```java
Criteria criteria = Criteria.where("assigned_to").isNull();
```

Clearly distinguish "filter not sent" from "filter for NULL values".

### 4.2. Range Conditions

Criteria supports comparisons such as:

| Criteria | SQL Meaning |
|---|---|
| `is(value)` | `=` |
| `not(value)` | `<>` |
| `greaterThan(value)` | `>` |
| `greaterThanOrEquals(value)` | `>=` |
| `lessThan(value)` | `<` |
| `lessThanOrEquals(value)` | `<=` |
| `in(values)` | `IN (...)` |
| `notIn(values)` | `NOT IN (...)` |
| `isNull()` | `IS NULL` |
| `isNotNull()` | `IS NOT NULL` |
| `like(pattern)` | `LIKE` |

Example date range:

```java
Criteria criteria = Criteria.where("created_at")
    .greaterThanOrEquals(from)
    .and("created_at")
    .lessThan(to);
```

In real code, to improve readability and avoid chaining mistakes, you can create two separate Criteria instances and combine them:

```java
Criteria criteria = Criteria.where("created_at")
    .greaterThanOrEquals(from)
    .and(Criteria.where("created_at").lessThan(to));
```

Both count and exists receive the same Query created from this Criteria.

## 5. Combining AND and OR

`Criteria` supports combining multiple conditions with AND and OR. When grouping conditions, create explicit groups to avoid altering logical meaning.

Example: find orders for a customer whose status is PAID or SHIPPED.

```java
Criteria completedStatus = Criteria.where("status").is("PAID")
    .or(Criteria.where("status").is("SHIPPED"));

Criteria criteria = Criteria.where("customer_id").is(customerId)
    .and(completedStatus);

Query query = Query.query(criteria);
```

Logical meaning:

```sql
WHERE customer_id = :customerId
  AND (status = 'PAID' OR status = 'SHIPPED')
```

Then:

```java
long count = aggregateTemplate.count(query, PurchaseOrder.class);
boolean exists = aggregateTemplate.exists(query, PurchaseOrder.class);
```

### 5.1. Why Group Conditions?

Suppose the condition is:

```sql
customer_id = 42
AND (status = 'PAID' OR status = 'SHIPPED')
```

If conditions are chained without proper grouping, the logic can become:

```sql
(customer_id = 42 AND status = 'PAID')
OR status = 'SHIPPED'
```

The two expressions are not equivalent. The second permits SHIPPED orders from any customer.

When conditions mix AND and OR, split them into Criteria groups and combine them. This ensures both count and exists evaluate the exact same well-defined logical expression.

## 6. Separating Query Construction from Execution

When an application has multiple screens or use cases sharing the same conditions, put query-building logic in a dedicated method or component.

Example:

```java
@Component
public class OrderCriteriaFactory {

    public Query from(OrderFilter filter) {
        Criteria criteria = Criteria.empty();

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.customerId() != null) {
            criteria = criteria.and("customer_id").is(filter.customerId());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("created_at")
                .greaterThanOrEquals(filter.createdFrom());
        }

        if (filter.createdTo() != null) {
            criteria = criteria.and("created_at")
                .lessThan(filter.createdTo());
        }

        return criteria.isEmpty()
            ? Query.empty()
            : Query.query(criteria);
    }
}
```

Service using the factory:

```java
@Service
public class OrderQueryService {

    private final JdbcAggregateTemplate template;
    private final OrderCriteriaFactory criteriaFactory;

    public OrderQueryService(
            JdbcAggregateTemplate template,
            OrderCriteriaFactory criteriaFactory) {
        this.template = template;
        this.criteriaFactory = criteriaFactory;
    }

    public long count(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);
        return template.count(query, PurchaseOrder.class);
    }

    public boolean exists(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);
        return template.exists(query, PurchaseOrder.class);
    }

    public OrderSearchSummary summarize(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);

        return new OrderSearchSummary(
            template.count(query, PurchaseOrder.class),
            template.exists(query, PurchaseOrder.class)
        );
    }
}
```

This structure offers two benefits:

- Different use cases use the exact same condition definition.
- When business rules change, Criteria-building logic only needs to be updated in one place.

If used in only one place, a private method inside the service may suffice. Avoid adding abstractions before they reduce duplication or clarify responsibilities.

## 7. Using the Same Query for findAll, count, and exists

Besides count and exists, `JdbcAggregateTemplate` provides `findAll(Query, Class<T>)` to load matching aggregates.

One filter query can serve as the basis for all three needs:

```java
Query filterQuery = Query.query(
    Criteria.where("status").is(OrderStatus.PENDING)
        .and("customer_id").is(customerId)
);

long count = template.count(filterQuery, PurchaseOrder.class);

boolean exists = template.exists(filterQuery, PurchaseOrder.class);

List<PurchaseOrder> orders =
    template.findAll(filterQuery, PurchaseOrder.class);
```

The key point is that all three operations share the same filter conditions. `findAll` loads aggregates, `count` returns the count, and `exists` returns a yes/no answer.

### 7.1. Creating a Separate Paginated Query from the Same Criteria

If a paginated list is needed, keep Criteria as the source of conditions and create another Query with sort, limit, and offset:

```java
Criteria criteria = Criteria.where("status").is("PENDING")
    .and("customer_id").is(customerId);

Query filterQuery = Query.query(criteria);

Query pageQuery = Query.query(criteria)
    .sort(Sort.by(Sort.Order.desc("created_at")))
    .limit(20)
    .offset(40);

long count = template.count(filterQuery, PurchaseOrder.class);
boolean exists = template.exists(filterQuery, PurchaseOrder.class);

List<PurchaseOrder> page =
    template.findAll(pageQuery, PurchaseOrder.class);
```

`filterQuery` represents the full result set for counting/existence checks. `pageQuery` adds ordering and limits for the displayed page.

Do not accidentally pass a query with `limit` or `offset` as the definition of total records on a screen when the goal is the total across all matches. Separate the filter query from the page query to keep intent clear.

### 7.2. Immutable Query and Reassignment

The `sort`, `limit`, and `offset` methods return a new Query. Therefore:

```java
Query pageQuery = filterQuery
    .sort(Sort.by("created_at"))
    .limit(20)
    .offset(40);
```

Do not call these methods and ignore the return value. The original Query stays unchanged, consistent with the API's immutable design.

## 8. count and exists Do Not Load Full Aggregates

When you need a count, `count` returns a number rather than forcing the application to load all aggregates and call `size()`.

When checking existence, `exists` returns a boolean rather than loading a list and checking whether it is empty.

Pattern to avoid:

```java
List<PurchaseOrder> orders =
    template.findAll(query, PurchaseOrder.class);

boolean exists = !orders.isEmpty();
long count = orders.size();
```

This approach can load far more data than necessary, including aggregate members, before computing the answer in memory.

Use the dedicated APIs:

```java
long count = template.count(query, PurchaseOrder.class);
boolean exists = template.exists(query, PurchaseOrder.class);
```

Specific SQL generation is handled by Spring Data JDBC and the dialect. Do not assume every database generates identical internal SQL; rely on the API contract and inspect logs/plans when tuning performance.

### 8.1. Do Not Call Both When the Use Case Needs Only One

If a page only displays a count, call `count`.

If a rule only needs to know whether any record exists, call `exists`.

Call both only when the UI or business logic genuinely requires both the count and a presence flag. Reusing a Query avoids duplicating conditions, not every use case needs to execute two queries.

## 9. count and exists with Repository Query Methods

When conditions are fixed and simple, a Spring Data JDBC repository can provide query methods such as:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    long countByStatus(OrderStatus status);

    boolean existsByStatus(OrderStatus status);

    long countByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );

    boolean existsByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );
}
```

This is concise when the set of conditions is known upfront in the method name.

However, when filters have many optional fields, declaring many pairs of `countBy...` and `existsBy...` can bloat the repository. `Query` and `Criteria` allow building dynamic conditions at runtime and sharing them across operations.

| Case | Suitable Approach |
|---|---|
| Fixed conditions, few fields | Derived repository query method |
| Optional filters varying by request | `Query` + `Criteria` |
| Need count and exists with same dynamic predicate | One `Query` used for both |
| Need custom SQL or complex aggregations | `@Query` or dedicated JDBC query |
| Check a single specific ID only | `existsById(id, domainType)` or repository `existsById(id)` |

## 10. Data Consistency Considerations

Reusing one `Query` guarantees both operations share the same filter definition. It does not guarantee both queries observe the exact same database state.

For example:

1. `count(query, PurchaseOrder.class)` returns 5.
2. Another transaction inserts a matching order.
3. `exists(query, PurchaseOrder.class)` runs afterward and returns true.

In this example, the two results remain compatible. Under concurrent deletes or updates, however, the results of two calls can reflect database state at two different points in time.

If business rules require both results to be observed within a consistent snapshot, examine transaction boundaries and database-supported isolation levels. Merely reusing the same Query object does not create a snapshot transaction.

### 10.1. Same Query Does Not Mean Same Transaction

You can invoke count and exists in the same service method. If a transaction is needed, place `@Transactional` on the application service according to business requirements:

```java
@Transactional(readOnly = true)
public OrderSearchSummary summarize(OrderFilter filter) {
    Query query = criteriaFactory.from(filter);

    return new OrderSearchSummary(
        template.count(query, PurchaseOrder.class),
        template.exists(query, PurchaseOrder.class)
    );
}
```

`readOnly = true` is a hint to transaction infrastructure; how it is enforced depends on the database/driver. It does not automatically make every database use snapshot isolation.

## 11. Testing Reuse of the Same Condition Set

At least three scenarios should be tested:

1. Multiple matching aggregates: count returns the exact count and exists is true.
2. No matching aggregates: count is 0 and exists is false.
3. Optional filters: each field is added to Criteria when present and omitted when absent.

Example repository/integration test against a database:

```java
@DataJdbcTest
class OrderCountAndExistsTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Test
    void countAndExistsUseTheSameCriteria() {
        insertOrder("ORD-1", "PENDING", 42L);
        insertOrder("ORD-2", "PENDING", 42L);
        insertOrder("ORD-3", "PAID", 42L);
        insertOrder("ORD-4", "PENDING", 99L);

        Query query = Query.query(
            Criteria.where("status").is("PENDING")
                .and("customer_id").is(42L)
        );

        long count = template.count(query, PurchaseOrder.class);
        boolean exists = template.exists(query, PurchaseOrder.class);

        assertThat(count).isEqualTo(2L);
        assertThat(exists).isTrue();
    }

    @Test
    void returnsZeroAndFalseWhenNoAggregateMatches() {
        Query query = Query.query(
            Criteria.where("status").is("CANCELLED")
        );

        assertThat(template.count(query, PurchaseOrder.class))
            .isZero();

        assertThat(template.exists(query, PurchaseOrder.class))
            .isFalse();
    }
}
```

The example assumes helper `insertOrder` inserts rows matching the test schema and entity `PurchaseOrder` maps the columns accurately. With `@DataJdbcTest`, test data typically runs inside a test transaction and rolls back after each test.

### 11.1. Testing Dynamic Filters

For builders, integration tests can verify:

- Passing only status does not restrict by customer.
- Passing customer ID matches only that customer's orders.
- Passing start/end dates applies time boundaries properly.
- Omitting optional fields does not accidentally generate `IS NULL` conditions.
- Empty filters are handled according to the chosen business policy.

### 11.2. Test Predicate Equivalence, Not Internal SQL Details

The goal of tests is verifying that count and exists apply the same filters and return accurate results from the database. Avoid coupling tests to internal SQL strings unless that is an application contract; generated SQL can vary by dialect or Spring Data version.

## 12. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Count and exists return inconsistent results | Two places build conditions separately or data changes between calls | Build one shared Query; use transaction/isolation if a snapshot is required |
| Optional filter matches NULL values | Always adding condition even when filter is absent | Add Criteria only when filter is supplied |
| Paginated query skews displayed total | Mistakenly using a query with limit/offset for the full dataset count | Create a separate filter Query and page Query |
| Calling limit() has no effect | Ignoring the newly returned Query | Reassign the fluent API return value |
| Loading many aggregates just for a boolean | Calling findAll then checking the list | Use exists(query, type) |
| Loading all aggregates just for a count | Calling findAll then taking size | Use count(query, type) |
| Criteria AND/OR leaks wrong customers | Not grouping OR expressions | Create explicit Criteria groups |
| Condition fails to match mapped column | Column/property name does not match mapping | Check naming strategy and @Column |
| Count overflows int range | Storing count in an int | Use long |
| Query overloads for count/exists fail to compile | Spring Data Relational version is too old | Check version; APIs were added in 3.0 |
| Empty filter returns entire dataset unexpectedly | No policy defined for unfiltered queries | Validate filters or explicitly allow Query.empty() |

## 13. Application Workflow

When needing both count and exists from the same conditions, follow this sequence:

1. Identify the aggregate root to query.
2. Identify filter fields and which ones are optional.
3. Build `Criteria` from the conditions actually supplied.
4. Create a `Query` from that Criteria.
5. Pass the same Query to `count(query, DomainType.class)` and `exists(query, DomainType.class)`.
6. If a paginated list is needed, build a new Query from the same Criteria and attach sort/limit/offset.
7. Write tests for matching data, no matching data, and optional filters.
8. If consistent results across multiple SQL statements are required, configure the necessary transaction and isolation level.

## 14. Exercises

**Exercise 1.** What type does `count(Query, Class<T>)` return?

*Answer:* `long`, representing the number of aggregates matching the query.

**Exercise 2.** What type does `exists(Query, Class<T>)` return?

*Answer:* `boolean`, true when at least one aggregate matches the query and false otherwise.

**Exercise 3.** Can both count and exists take the same Query object?

*Answer:* Yes. This lets you reuse the same filter conditions so both operations do not have to construct predicates separately.

**Exercise 4.** Do `Query` and `Criteria` mutate in place when calling and, limit, or sort?

*Answer:* No. These are immutable fluent APIs; methods return new objects. You must capture the returned value.

**Exercise 5.** If the `customerId` filter is null because the user did not select a customer, should we add `customer_id IS NULL`?

*Answer:* No, unless the user explicitly requested rows with a NULL customer ID. When a filter is absent, skip that condition.

**Exercise 6.** When you only need to know whether any orders exist, should you call `count(...) > 0` or `exists(...)`?

*Answer:* Use `exists(...)` because its return type and API intent match the requirement directly.

**Exercise 7.** Can a Query with limit 20 be used to count total search results?

*Answer:* Create a filter Query without pagination to represent the full result set, and a separate page Query for the list.

**Exercise 8.** Does reusing the same Query guarantee that count and exists see the same database snapshot?

*Answer:* No. Sharing the Query guarantees the same condition definition; snapshot consistency depends on database transactions and isolation levels.

**Exercise 9.** How should PAID or SHIPPED status conditions be combined with a customer ID?

*Answer:* Build an OR Criteria group for the two statuses, then AND that group with the customer ID condition.

**Exercise 10.** Since which version have `count(Query, Class<T>)` and `exists(Query, Class<T>)` been available?

*Answer:* Spring Data Relational 3.0.

## 15. Things to Remember

- `JdbcAggregateTemplate.count(Query, Class<T>)` returns `long`; `exists(Query, Class<T>)` returns `boolean`.
- Both methods accept the same `Query`, allowing count and exists to share dynamic conditions.
- `Query.query(criteria)` creates a Query from `Criteria`; both fluent APIs are immutable.
- Add Criteria only for supplied filters; distinguish absent filters from matching NULL.
- Use explicit AND/OR groups to prevent altering logical meaning.
- Keep the filter Query separate; create a new Query with sort/limit/offset for paginated lists.
- Use `exists` when only a yes/no answer is needed; use `count` when a count is needed.
- Query with `domainType` counts or checks aggregates of that type.
- Reusing a Query keeps the same predicates but does not automatically create a shared database snapshot across two calls.
- If consistency under concurrent writes is required, configure transaction boundaries and isolation levels.
- Both Query-based count/exists methods were introduced in Spring Data Relational 3.0.

### Official References

- [Spring Data Relational — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): signatures, return types, and Since 3.0 marker for count(Query, Class<T>) and exists(Query, Class<T>).
- [Spring Data Relational — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): implementation of aggregate operations.
- [Spring Data Relational — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): Query, Criteria, sort, limit, and offset; immutable fluent API.
- [Spring Data Relational — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html): creating and combining AND/OR conditions.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): persistence operations and querying via JdbcAggregateTemplate.

When you need to count and check existence for the same filter set, build Criteria once, create Query once, and pass that same Query to both APIs. This keeps condition definitions centralized, easy to update, and easy to test.
