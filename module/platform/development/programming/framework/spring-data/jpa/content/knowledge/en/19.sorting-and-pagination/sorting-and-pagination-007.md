# Paginating with Relationship Joins and Avoiding Duplicate Counts

## 1. Why Do JOINs Affect Pagination?

Spring Data JPA supports pagination using `Pageable`, `Page<T>`, and `Slice<T>`. When a query reads only a single table or joins to an association with at most one related record, pagination is usually straightforward. Problems arise when a query joins a to-many relationship such as `PurchaseOrder.items`: a single order can produce multiple rows in the SQL result.

Example of one order with three items:

```text
purchase_order       purchase_order_item
order_id = 10        item_id = 1, order_id = 10
                     item_id = 2, order_id = 10
                     item_id = 3, order_id = 10
```

The join produces three SQL rows for the same order. If the database applies `LIMIT/OFFSET` across the joined rows, a page may contain fewer root Entities than the requested size, or the same Entity may appear across multiple positions. The count query may also count three rows instead of one order.

What usually needs to be paginated is the **unique root Entity**, not the joined row count. Therefore, you must examine the association's cardinality and how the query selects and counts the root.

## 2. To-One and To-Many JOINs Have Different Impacts

- `ManyToOne` or `OneToOne` typically matches at most one related row per root. This type of join generally does not multiply root rows, provided the schema and mapping enforce the corresponding cardinality.
- `OneToMany` or `ManyToMany` can match multiple related rows for a single root. This type of join can multiply SQL rows and skew counts if counted directly.
- Joining multiple to-many collections in the same query can produce a Cartesian product of rows. An order with 4 items and 3 payments can produce 12 SQL rows.

Not every query with a JOIN needs `DISTINCT`. Add it only when the cardinality and actual results can produce duplicate roots. Avoid adding DISTINCT out of habit when the query cannot create duplicates, as the database may have to perform extra sorting or hashing work.

## 3. Using DISTINCT When Joining a Collection for Filtering

Example: retrieving orders that have at least one item belonging to a selected product:

```java
@Query(
    value = """
        select distinct p
        from PurchaseOrder p
        join p.items i
        where i.productCode = :productCode
        """,
    countQuery = """
        select count(distinct p.id)
        from PurchaseOrder p
        join p.items i
        where i.productCode = :productCode
        """
)
Page<PurchaseOrder> findOrdersByProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

`select distinct p` asks for each root `PurchaseOrder` to appear once in the JPQL result even if multiple items match. `countQuery` uses `count(distinct p.id)` to count unique orders rather than item rows.

The count query must preserve the filtering logic that affects the root set, though it typically does not need fetch joins, sorting, or projections unrelated to counting. For to-one joins, `count(p)` may suffice; for to-many joins, `count(distinct p.id)` is usually the safe choice when counting unique roots.

## 4. Using EXISTS to Avoid Row Multiplication

If the goal is merely to check whether at least one child matches a condition, `EXISTS` often expresses the intent better than a JOIN:

```java
@Query(
    value = """
        select p
        from PurchaseOrder p
        where exists (
            select i.id
            from PurchaseOrderItem i
            where i.purchaseOrder = p
              and i.productCode = :productCode
        )
        """,
    countQuery = """
        select count(p.id)
        from PurchaseOrder p
        where exists (
            select i.id
            from PurchaseOrderItem i
            where i.purchaseOrder = p
              and i.productCode = :productCode
        )
        """
)
Page<PurchaseOrder> findOrdersHavingProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

The subquery only checks whether a matching item exists; the outer query still selects each `PurchaseOrder` once. Thus `distinct` on the root is not needed in this example. Depending on the optimizer, the database can execute a semi-join or an equivalent plan.

Prefer `EXISTS` when the child is only used for filtering conditions. Use JOIN when you need child attributes in a projection, sorting by child fields, grouping/aggregation, or another reason that requires combining rows.

## 5. Why Is a Separate countQuery Needed?

With a `Page<T>` return type, Spring Data needs total element information to calculate total pages. The framework can derive the count query from the main query in simple cases. When a query has DISTINCT, complex joins, grouping, native SQL, or special projections, automatic derivation may not reflect the exact number of unique roots.

Declaring an explicit `countQuery` gives you control over counting:

- Count root Entities or root IDs, not joined rows, if the requirement is the root count.
- Keep WHERE/EXISTS conditions that affect the root set.
- Omit unnecessary `fetch join` and `ORDER BY` clauses from the count query.
- For queries with `GROUP BY`/`HAVING`, clarify whether the API intends to report total groups or total roots; a dedicated count subquery or native count query may be needed.

Do not mechanically copy the main query and replace `select` with `count(*)`. With a to-many join, `count(*)` typically counts post-join rows and yields a total higher than the number of unique Entities.

## 6. Paginating When Collections Must Be Fetched

Do not paginate a query that fetch-joins a collection directly:

```java
// Should not be used directly for Page when items is a to-many collection.
@Query("select p from PurchaseOrder p left join fetch p.items where p.status = :status")
Page<PurchaseOrder> findPageWithItemsByStatus(
    @Param("status") OrderStatus status, Pageable pageable
);
```

A collection fetch join creates multiple SQL rows per parent. The database paginates those rows rather than the deduplicated parent object graph. Hibernate may log a warning and perform pagination in memory; on large datasets, this can consume significant memory and time.

With Hibernate, you can enable fail-fast detection for this case:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

This property turns a slow-performance pitfall into an explicit error in test environments. It does not fix the query by itself; you still need to choose an appropriate loading strategy.

## 7. Two-Step Strategy: Paginate IDs Then Fetch Collections

This is a common pattern when an API needs a page of root Entities along with each root's full collection:

**Step 1 — fetch a page of unique IDs:**

```java
@Query(
    value = """
        select p.id
        from PurchaseOrder p
        where p.status = :status
          and exists (
              select i.id
              from PurchaseOrderItem i
              where i.purchaseOrder = p
                and i.productCode = :productCode
          )
        """,
    countQuery = """
        select count(p.id)
        from PurchaseOrder p
        where p.status = :status
          and exists (
              select i.id
              from PurchaseOrderItem i
              where i.purchaseOrder = p
                and i.productCode = :productCode
          )
        """
)
Page<Long> findPageOfOrderIds(
    @Param("status") OrderStatus status,
    @Param("productCode") String productCode,
    Pageable pageable
);
```

The caller passes a stable sort with a unique key as a tie-breaker:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
```

`createdAt` and `id` are Java properties of the Entity. Adding `id` makes ordering deterministic when multiple orders share the same timestamp, preventing records from jumping across pages due to indeterminate ties.

**Step 2 — load collections for the IDs on the page:**

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.items
    where p.id in :ids
    """)
List<PurchaseOrder> findAllWithItemsByIdIn(
    @Param("ids") Collection<Long> ids
);
```

The second query does not use `Pageable`; it only loads the selected roots and their collections. `LEFT JOIN FETCH` preserves orders even when they have no items.

**Step 3 — preserve the first page's order:**

```java
@Transactional(readOnly = true)
public Page<PurchaseOrder> searchWithItems(
        OrderStatus status, String productCode, Pageable pageable) {
    Page<Long> idPage = repository.findPageOfOrderIds(
        status, productCode, pageable
    );

    if (idPage.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, idPage.getTotalElements());
    }

    List<PurchaseOrder> loaded = repository.findAllWithItemsByIdIn(
        idPage.getContent()
    );
    Map<Long, PurchaseOrder> byId = loaded.stream().collect(
        Collectors.toMap(PurchaseOrder::getId, Function.identity())
    );
    List<PurchaseOrder> ordered = idPage.getContent().stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();

    return new PageImpl<>(
        ordered, pageable, idPage.getTotalElements()
    );
}
```

This is an illustrative implementation; import `Page`, `PageImpl`, `Pageable`, `List`, `Map`, `Collectors`, `Function`, and `Objects`, and inject the repository. `IN (:ids)` does not guarantee order, so the service must reorder according to the step-one ID list. Within the same transaction, the isolation level and concurrent data modifications can still affect results between the two queries; if a strictly consistent snapshot is required, choose an isolation level suited to the database and business requirements.

## 8. LEFT JOIN: Condition in ON or WHERE?

With an optional join, where you place a condition can change the root set:

```java
select p
from PurchaseOrder p
left join p.customer c
where c.city = :city
```

The condition `WHERE c.city = :city` filters out rows where customer is null, making the result behave almost like an INNER JOIN. If you want to keep every order while only matching customers in the specified city, place the condition in `ON`:

```java
select p
from PurchaseOrder p
left join p.customer c on c.city = :city
```

The count query must reflect the exact same semantics. If the condition is in ON and the root is unfiltered, the root count may be all orders, even those without a matching customer. Write tests for both cases: with and without the association.

## 9. DISTINCT Does Not Fix Every Pagination Problem

`DISTINCT` can eliminate duplicate roots at the query result level, but it is not a universal fix for collection fetch joins combined with `Pageable`:

- With a regular join selecting only the root Entity, `select distinct p` can deduplicate the root set prior to pagination depending on the generated SQL.
- With a collection fetch join, SQL must return child rows to initialize the collection. Those rows differ in child columns, so SQL DISTINCT cannot collapse them into one row while still keeping all collection data.
- The ORM can deduplicate roots in the Java result, but that does not reduce the number of rows paginated by the database.

Therefore, address cardinality and the fetch plan first; do not add DISTINCT and assume collection pagination is now safe.

## 10. Page, Slice, and OFFSET Limits

| Return Type | Information Provided | Query Consequence |
| --- | --- | --- |
| `Page<T>` | Page content, total element count, total pages | Usually requires a count query |
| `Slice<T>` | Page content and whether a next page exists | Typically fetches one extra element to detect hasNext, no total count needed |
| `List<T>` with `Pageable` | Content of a data segment | Does not provide total page counts |

If the UI does not need the total record count, `Slice<T>` can avoid an expensive count query. On very large datasets, deep OFFSETs can be slow because the database must skip many rows before returning the page.

Keyset/seek pagination uses the values of the last row on the previous page as the starting point for the next page, such as `(createdAt, id) < (:lastCreatedAt, :lastId)` when sorting descending. This suits stable sorts with indexes and a unique tie-breaker key. Spring Data supports scrolling/keyset in appropriate APIs depending on version; check the limitations of the repository method and query before applying.

## 11. Sort Must Be Stable and Valid

Pagination requires deterministic ordering. If you sort only by `createdAt` and multiple rows share the same timestamp, the database may return different orders across requests. Add a unique key such as `id` as a tie-breaker.

Sort from `Pageable` must use valid Entity properties/paths or aliases supported by Spring Data in the declared query. Do not concatenate client-supplied sort strings directly into JPQL or native SQL. If the API only permits sorting on certain fields, use an allow-list and map safely to `Sort`.

With native queries, Spring Data's ability to apply dynamic sorting depends on version and SQL form. If a query has CTEs, unions, functions, or complex aliases, declare explicit sort/count logic or handle it in a custom repository.

## 12. Count Queries with Projections, GROUP BY, and Native SQL

With projections or aggregate queries, define clearly what unit is being counted:

- Counting root Entities: `count(distinct p.id)` when a to-many join can multiply rows.
- Counting groups: count the number of groups after `GROUP BY`, not source record counts.
- Counting projection rows: count result rows according to the projection's exact semantics.

For JPQL with group/having or complex native SQL, declare a separate `countQuery`. The count query does not have to mirror the content query; it must return the exact total count promised by the `Page` contract.

Example native query with a to-many join:

```java
@Query(
    value = """
        select distinct p.*
        from purchase_order p
        join purchase_order_item i on i.purchase_order_id = p.id
        where i.product_code = :productCode
        """,
    countQuery = """
        select count(distinct p.id)
        from purchase_order p
        join purchase_order_item i on i.purchase_order_id = p.id
        where i.product_code = :productCode
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findNativeOrdersByProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

Native queries use physical table/column names and database-dependent syntax. An explicit `countQuery` is especially useful because Spring Data cannot always infer an accurate count from arbitrary native SQL.

## 13. Testing Pagination with Joins

Tests should create data with varying cardinalities:

1. A parent with multiple children all matching the filter.
2. A parent with multiple children where only one child matches.
3. A parent with no children.
4. Multiple parents sharing the same sort value.
5. First page, middle page, last page, and empty page.
6. Concurrent data modifications if business logic requires cross-page consistency.

For each case, verify:

- No duplicate root IDs in the page content.
- Page size matches expectations, except on the last page.
- `totalElements` equals the contracted root/group count, not joined row count.
- Ordering is stable with no missing/duplicate records across pages within the same data snapshot.
- The count query has appropriate SQL and execution plans.
- Collection-fetching queries do not trigger in-memory pagination or load excessive rows.

Run integration tests on the target database or a database closely matching the deployment environment. In-memory databases may differ in optimizer behavior, data types, and native SQL syntax.

## 14. Common Pitfalls and Fixes

**`totalElements` is larger than the number of unique Entities.** The count query is counting post-join rows. Use `count(distinct root.id)` or EXISTS if children are only used for filtering.

**Page has fewer Entities than page size.** A to-many join is multiplying rows before LIMIT/OFFSET. Select root IDs first, then load associations in a second query.

**Duplicate Entities in results.** Check cardinality, `select distinct root`, and whether the query returns a projection/tuple instead of the root Entity.

**Hibernate warns about pagination over collection fetch.** Do not use `Pageable` directly with a collection fetch join; use the two-step approach, batch fetching, or DTOs.

**Count query returns wrong total after adding LEFT JOIN.** Check conditions in ON/WHERE and clarify which roots must be preserved.

**Pages duplicate or miss items when sorting.** Add a unique tie-breaker to the sort and account for data changes between requests.

**Native Page query fails to paginate/count properly.** Check `countQuery`, SQL dialect, aliases, sorting, and Spring Data version support.

**DISTINCT slows down the query.** Inspect the execution plan; if only checking whether a child exists, try EXISTS to avoid row multiplication.

## 15. Strategy Selection Checklist

- Identify whether an association is to-one or to-many before adding a JOIN.
- If children are only for filtering, consider EXISTS.
- If joining to-many and selecting roots, use DISTINCT when needed and count distinct root IDs.
- With `Page<T>`, declare `countQuery` when the query is complex or accurate counting must be guaranteed.
- Do not paginate a collection fetch join directly.
- Use two steps: paginate IDs/roots first, fetch collections afterward; restore the initial ID order.
- Use `Slice<T>` when total count is unneeded; consider keyset when OFFSET is deep.
- Use a stable sort with a unique tie-breaker.
- Test parents with multiple children, parents with zero children, counts, and empty pages on the real database.

Accurate pagination with joins starts by identifying the unit to paginate: root Entity, group, or projection row. When joining to-many relationships, control generated rows, count unique roots, and separate collection fetching from the paginated query when necessary. This keeps page content, totals, and ordering consistent with business requirements.