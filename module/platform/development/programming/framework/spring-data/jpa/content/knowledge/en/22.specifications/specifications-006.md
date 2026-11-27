# Association Joins, Subqueries, and Handling Duplicate Results

## 1. Why Do Specifications Need JOINs and Subqueries?

Spring Data JPA's `Specification<T>` builds on the JPA Criteria API to construct dynamic query conditions. When a filter only inspects properties of the root Entity, predicates can be created directly from `Root<T>`. When a condition depends on a related Entity, you must traverse the association with a JOIN or check existence via a subquery.

The two techniques solve different needs:

- **JOIN:** combines the root Entity with a related Entity to filter, sort, group, or retrieve related data.
- **Subquery:** creates a nested query to check existence, non-existence, membership, or comparisons against an aggregated value.

Joining a to-many relationship can produce multiple SQL rows for the same root Entity. Consequently, when using a Specification with `Page<T>` or returning a list of root Entities, you must handle duplicate results and count accurately according to the root entities required by business rules.

## 2. Example Model

Suppose a customer has many purchase orders:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
    private CustomerStatus status;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    private OrderStatus status;
    private BigDecimal totalAmount;
    private Instant createdAt;
}
```

Suppose you need to find customers with at least one paid order, or customers with an order whose total exceeds a threshold. These conditions traverse the `Customer.orders` relationship.

## 3. Basic Structure of a Specification

A Specification receives `Root<T>`, `CriteriaQuery<?>`, and `CriteriaBuilder`, and returns a `Predicate`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

```java
Specification<Customer> activeCustomers = (root, query, cb) ->
    cb.equal(root.get("status"), CustomerStatus.ACTIVE);
```

`root` represents the root Entity in FROM; `query` is the CriteriaQuery under construction; `cb` builds expressions and predicates such as `equal`, `and`, `or`, `exists`, `greaterThan`.

Property paths in the Criteria API use Java property names (`status`, `orders`, `totalAmount`), not physical column names (`order_status`, `total_amount`).

## 4. Joining To-One and To-Many Relationships

Use `root.join(...)` to create a join to an association. You can specify the join type:

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order =
        root.join("orders", JoinType.INNER);

    return cb.equal(order.get("status"), OrderStatus.PAID);
};
```

`INNER` keeps only customers with at least one matching order. For optional associations, `LEFT` keeps the root Entity even when no related Entity exists:

```java
Join<Customer, Address> address =
    root.join("address", JoinType.LEFT);
```

JPA Criteria typically uses `JoinType.INNER` and `JoinType.LEFT`. RIGHT JOIN support varies across providers/databases and is rarely needed in Entity models; prefer designing joins from the appropriate root Entity side.

For embedded properties like `address.city`, a SQL JOIN is not strictly necessary if `address` is `@Embedded`; you can follow the path directly:

```java
Path<String> city = root.get("address").get("city");
return cb.equal(city, "Da Nang");
```

Use `join()` only for mapped persistent associations; use `get()` to access simple attributes or embedded paths.

## 5. To-Many JOINs Can Duplicate Root Entities

Suppose customer A has three PAID orders. Joining `Customer.orders` generates three SQL rows for customer A. When the query selects Customer, the provider may return the same root multiple times unless the query requests distinct results.

Inside a Specification, you can request unique root results:

```java
Specification<Customer> hasPaidOrderDistinct = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order =
        root.join("orders", JoinType.INNER);

    query.distinct(true);
    return cb.equal(order.get("status"), OrderStatus.PAID);
};
```

`query.distinct(true)` marks the query as distinct. For queries selecting the root Entity, this instructs JPA semantics to deduplicate root results. However, the database may still have to process the joined rows; DISTINCT does not automatically make a to-many join cheap.

Do not enable distinct habitually on every Specification. To-one joins usually do not multiply root rows, and EXISTS subqueries do not multiply outer query rows either. Use distinct only when a join can genuinely create duplicates or when the result contract requires it.

## 6. Accurate Counting When Using Page

`Page<T>` needs the total number of elements. If a query joins a to-many association, `count(*)` over joined rows may count the same customer multiple times. For example, one customer with three matching orders contributes three joined rows, even though there is only one customer.

Logically, the total number of unique customers must be computed via `count(distinct customer.id)` or via a query that does not multiply root rows, such as EXISTS.

When using `JpaSpecificationExecutor`, Spring Data constructs the count query from the Specification. If the Specification sets `query.distinct(true)`, the count query needs to count distinct roots per provider/framework semantics. Verify `totalElements` with integration tests whenever to-many joins are involved; never assume joined row count equals root count.

For complex queries with `GROUP BY`, `HAVING`, multiple joins, or custom projections, the auto-generated count may not match the intended total. In those cases, use a custom repository or an explicit query to define the count accurately, and test both page content and count.

## 7. Using EXISTS to Check Related Entities

If you only need to know whether a customer has at least one PAID order—without selecting order columns or sorting by order—EXISTS expresses the intent better than JOIN:

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    subquery.select(cb.literal(1))
        .where(cb.equal(order.get("status"), OrderStatus.PAID));

    return cb.exists(subquery);
};
```

`subquery.correlate(root)` links the subquery to the current customer in the outer query. The subquery simply returns a constant literal when a matching order is found; `cb.exists(subquery)` checks whether at least one row exists. The outer query keeps one logical row per customer, so `query.distinct(true)` is not needed solely to deduplicate order joins.

Database optimizers may execute EXISTS using a semi-join or equivalent plan. Actual performance depends on indexes, data distribution, and the optimizer; inspect execution plans for critical queries.

## 8. NOT EXISTS to Find Entities Without Matching Relations

To find customers who have never had a cancelled order, use `NOT EXISTS`:

```java
Specification<Customer> hasNoCancelledOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    subquery.select(cb.literal(1))
        .where(cb.equal(order.get("status"), OrderStatus.CANCELLED));

    return cb.not(cb.exists(subquery));
};
```

Customers with zero orders also satisfy `NOT EXISTS`, because no CANCELLED order row exists. This is usually the intended semantics when the business question is "has no cancelled orders". If the requirement is "has at least one order and none are cancelled", add an EXISTS condition for any order or express the logic accordingly; those two requirements differ.

## 9. JOIN vs. EXISTS: Choose by Intent

| Need | Typically Suitable Approach |
| --- | --- |
| Filter root by a to-one association property | JOIN or appropriate path |
| Retrieve association fields in projection | JOIN |
| Sort/group by an association property | JOIN, with clearly defined cardinality |
| Only check whether at least one matching child exists | EXISTS |
| Only check that no matching child exists | NOT EXISTS |
| Avoid multiplying root rows when child is filter-only | EXISTS |

JOIN is not wrong for to-many filtering; it simply requires managing distinct and counts. EXISTS is often more natural when the condition is an existential check and the outer query only needs the root Entity.

## 10. Subqueries with IN Conditions

A subquery can also produce a value set for `IN`. For example, finding customers whose ID is in the set of customers with an order above a threshold:

```java
Specification<Customer> hasLargeOrder = (root, query, cb) -> {
    Subquery<Long> subquery = query.subquery(Long.class);
    Root<PurchaseOrder> order = subquery.from(PurchaseOrder.class);

    subquery.select(order.get("customer").get("id"))
        .where(cb.greaterThan(order.get("totalAmount"), new BigDecimal("1000")));

    return root.get("id").in(subquery);
};
```

The subquery returns customer IDs from qualifying orders. The outer query checks whether the current ID belongs to that set. If you want an explicit correlation to the root and want to avoid large ID sets, you can use correlated EXISTS as in the previous example.

Do not choose `IN`/subqueries just because the syntax looks shorter. Pick the structure that accurately captures cardinality, null semantics, and database optimization behavior.

## 11. Subqueries with Aggregate Values

Criteria subqueries can return an aggregate value for comparison. For instance, finding customers who have an order greater than the average amount across all orders:

```java
Specification<Customer> hasOrderAboveAverage = (root, query, cb) -> {
    Subquery<Double> averageQuery = query.subquery(Double.class);
    Root<PurchaseOrder> orderForAverage =
        averageQuery.from(PurchaseOrder.class);

    averageQuery.select(cb.avg(orderForAverage.get("totalAmount")));

    Subquery<Integer> existsQuery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = existsQuery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    existsQuery.select(cb.literal(1))
        .where(cb.greaterThan(order.get("totalAmount"), averageQuery));

    return cb.exists(existsQuery);
};
```

This example illustrates comparing against an aggregate subquery; the returned numeric type must align with your property type and project Criteria API signatures. For `BigDecimal`, you can use `BigDecimal` in generics and matching expressions instead of arbitrarily converting to Double. If aggregate queries become complex or need per-customer grouping, JPQL, Querydsl, or a custom repository may be easier to read and control.

## 12. LEFT JOIN: Conditions in ON vs. WHERE

LEFT JOIN retains roots without matching associations, yet placing predicates in WHERE can filter those roots back out.

Example:

```java
Join<Customer, PurchaseOrder> order =
    root.join("orders", JoinType.LEFT);
return cb.equal(order.get("status"), OrderStatus.PAID);
```

Despite using LEFT JOIN, the WHERE predicate requires `order.status = PAID`; rows with no orders have null related values and fail the condition. The result resembles an INNER JOIN.

To keep customers even when they have no PAID order, place the condition in ON:

```java
Join<Customer, PurchaseOrder> order =
    root.join("orders", JoinType.LEFT);
order.on(cb.equal(order.get("status"), OrderStatus.PAID));
return cb.conjunction();
```

Here, the condition restricts which orders are joined while the outer predicate always evaluates to true, preserving the customer. If the goal is to find customers with a PAID order, place the predicate in WHERE or use EXISTS. If the goal is to retrieve all customers and only join PAID orders when present, ON reflects the right semantics.

## 13. Combining Multiple Specifications and Duplicate Join Issues

Spring Data lets you compose Specifications with `.and()` and `.or()`:

```java
Specification<Customer> active = (root, query, cb) ->
    cb.equal(root.get("status"), CustomerStatus.ACTIVE);

Specification<Customer> hasPaid = hasPaidOrder;

Specification<Customer> search = active.and(hasPaid);
List<Customer> result = customerRepository.findAll(search);
```

When multiple Specifications each call `root.join("orders")`, every specification may create a separate join. This can introduce redundant SQL joins and, more importantly, change the logical meaning.

For example:

- `hasPaidOrder.and(hasLargeOrder)` with two separate joins can mean the customer has one PAID order **and** possibly a different order larger than 1000.
- If business rules require a single order to be both PAID and larger than 1000, both predicates must share the same join or live inside the same EXISTS subquery.

Example grouping conditions on the same child:

```java
Specification<Customer> hasPaidLargeOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlated = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order = correlated.join("orders");

    subquery.select(cb.literal(1)).where(
        cb.equal(order.get("status"), OrderStatus.PAID),
        cb.greaterThan(order.get("totalAmount"), new BigDecimal("1000"))
    );

    return cb.exists(subquery);
};
```

Placing both predicates inside the same subquery ensures the exact same order satisfies every condition. When extracting reusable Specifications, document clearly whether they apply to the same association row or merely require some row for each condition.

## 14. Avoiding Unpredictable Side Effects in Specifications

A Specification may be used for both the data query and the count query when Spring Data processes `Page<T>`. Therefore, stay focused on building predicates and avoid altering query structure beyond what is necessary.

Guidelines:

- Do not arbitrarily call `query.orderBy(...)` in shared Specifications if the repository also accepts Sort/Pageable; ordering may be overwritten or break the count query.
- Do not set `query.multiselect(...)` or `groupBy(...)` in shared Specifications for root Entities if the same Specification will be used for a count query.
- `query.distinct(true)` may be necessary with to-many joins, but always test both page content and counts.
- Do not add collection fetch joins inside paginated Specifications without addressing collection fetch pagination limits.
- When projections, grouping, aggregates, or special query shapes are needed, a custom repository is usually a better fit than forcing one Specification to do everything.

## 15. JOIN for Filtering vs. JOIN FETCH for Loading Associations

`root.join("orders")` creates a join for query filtering. It does not mean the `Customer.orders` collection is initialized in the Entity graph.

Fetch joins or EntityGraphs are separate fetch-plan mechanisms. In the Criteria API, `root.fetch("orders", JoinType.LEFT)` can request loading a collection, but combining collection fetches with `Pageable` easily causes row multiplication and in-memory pagination. For paginated roots with large collections, consider two phases: fetch the page of IDs first, then fetch associations for that ID list; or use batch fetching or DTO projections.

Never use a filtering join and assume the association is initialized. Inspect actual SQL and fetch status when needed.

## 16. Sorting and Pagination with To-Many Joins

Sorting by a child property can be ambiguous when a customer has multiple orders. "Sort customers by order.createdAt" requires specifying whether it means the newest order, oldest order, largest order, or an order matching a filter.

Do not rely on arbitrary row order after a join. If you need to sort roots by latest order date, use `MAX(createdAt)` in an appropriate query, correlated subquery, or custom repository. When using Page, the count must count unique roots.

Include a unique root key as a tie-breaker in paginated sorts, such as `createdAt DESC, id DESC`, to prevent unstable ordering when multiple roots share the same sort value.

With collection joins and fetch pagination, avoid applying `Pageable` directly over a fetch join. Even with a regular filtering join that multiplies roots, verify that DISTINCT is applied properly before pagination on your target database, or use EXISTS / two-phase ID pagination.

## 17. Testing JOINs and Subqueries

Integration tests should cover data fixtures with varied cardinalities:

1. Customer with no orders.
2. Customer with one PAID order.
3. Customer with multiple PAID orders to test root duplication.
4. Customer with one PAID order and one CANCELLED order.
5. Customer with one small PAID order and one large PENDING order to test same-child conditions.
6. Customer with orders where none match the predicate.

Verify:

- JOIN results contain unique roots or use distinct as required.
- EXISTS/NOT EXISTS handle customers with zero children accurately.
- Combined AND conditions on the same child truly evaluate against the same row.
- LEFT JOIN ON/WHERE retains or excludes roots as required.
- `Page.getTotalElements()` counts root entities, not joined rows.
- Child sorting has clear semantics and deterministic page ordering.
- SQL and execution plans utilize appropriate indexes.

Do not solely mock the repository; run integration tests against a real JPA provider and a database compatible with your runtime environment.

## 18. Common Pitfalls and Fixes

**Same Customer appears multiple times.** To-many JOIN creates multiple rows. Use `query.distinct(true)` when unique roots are needed, or switch to EXISTS if the child is only used for filtering.

**`totalElements` exceeds the number of customers.** The count is counting joined rows. Verify distinct counting or use an EXISTS subquery so roots are not multiplied.

**Two order filters unintentionally match two different orders.** Two Specifications created two independent joins. Group predicates under the same join/subquery when a single child must satisfy all conditions.

**LEFT JOIN still drops customers without associations.** The related predicate was placed in WHERE. Move the condition into ON or adjust query semantics.

**Specification works with List, yet Page returns the wrong count.** Inspect `distinct`, grouping, joins, and the generated count query; write a custom count query if the query is complex.

**Collection stays LAZY after JOIN.** A filtering JOIN is not a fetch join. Use an EntityGraph/fetch plan or a dedicated association-loading query.

**Pagination turns slow after adding a collection fetch.** Avoid combining collection fetch joins directly with Pageable; use two-phase ID pagination, batch fetching, or DTOs.

**Sorting by child produces unpredictable order.** Define which aggregate or representative child determines order and add a unique root tie-breaker.

## 19. Checklist for Choosing JOIN, EXISTS, and DISTINCT

- Use JOIN when association attributes are needed in filters, projections, sorting, or aggregates.
- Use EXISTS when you only need to verify a matching child exists and want one logical row per root.
- Use NOT EXISTS when finding roots without a matching child; clarify whether roots with zero children qualify.
- Use `query.distinct(true)` when a to-many join can repeat roots and unique Entities are required.
- Verify the Page count query; count distinct roots or restructure the query to avoid multiplying rows.
- When combining Specifications, determine whether predicates must hold on the same child or may hold on separate children.
- Place LEFT JOIN conditions in ON or WHERE to match exact root retention/exclusion semantics.
- Do not confuse JOIN with FETCH; avoid collection fetch joins during pagination.
- For sorting across to-many relations, define the aggregate or representative child clearly and add a tie-breaker.
- Use integration tests and execution plans to confirm both correctness and performance.

JOIN, EXISTS, and subqueries are all tools for writing Specification predicates, but they express different cardinalities. JOIN combines related rows and can multiply roots; EXISTS checks existence without multiplying outer query rows; DISTINCT deduplicates roots when truly needed. Choose the construct matching your business semantics, then verify counts, pagination, and SQL on a real database.
