# JOIN FETCH and How It Differs from Joins Used for Filtering

## 1. Two Different Purposes of JOIN

In JPQL, both `JOIN` and `JOIN FETCH` can cause SQL to perform a JOIN, yet their meanings for the Entity differ:

- `JOIN` combines an association for filtering, sorting, or selecting data from the related side. It does not require JPA to initialize the association on the resulting Entity.
- `JOIN FETCH` instructs the provider to load the specified association together with the root Entity in the current query. It is a directive specifying the fetch plan for that query.

This distinction is especially important for LAZY associations. A query using `JOIN` may still return Entities whose association has not been initialized. If subsequent code accesses that association, Hibernate may issue extra queries. To load the association at the same time, use a fetch join, an entity graph, or another fetch plan.

## 2. Example Model

Suppose an order references a customer:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
    private String city;
}
```

`PurchaseOrder.customer` is a LAZY ManyToOne association. When loading multiple orders and calling `order.getCustomer().getName()`, if the customer has not been loaded and is not present in the persistence context or cache, Hibernate may execute an additional query.

## 3. Regular JOIN: Filtering by Association

For example, fetch only orders belonging to customers in a given city:

```java
@Query("""
    select p
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findOrdersByCustomerCity(
    @Param("city") String city
);
```

`join p.customer c` lets us reference `Customer` attributes in the `where` condition. The selected result is `PurchaseOrder`. JPQL does not require `p.customer` to be fetched; when code later accesses the customer after the query, the association may still be loaded via a separate LAZY query.

Regular JOIN is appropriate when the association only participates in filtering or sorting conditions, and the returned results do not require initializing the full association.

INNER JOIN retains only orders with a matching customer. If the relationship is nullable, orders without a customer will not appear.

## 4. LEFT JOIN and Condition Placement

`LEFT JOIN` preserves left-side rows even when no matching association exists. However, placing a condition in `WHERE` can eliminate null rows:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findOrdersByCustomerCity(
    @Param("city") String city
);
```

The condition `where c.city = :city` is not true for rows where `c` is null, so the result becomes effectively equivalent to an INNER JOIN.

If you want to keep all orders and only restrict which customers are matched in the join, place the condition in `ON`:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join p.customer c on c.city = :city
    """)
List<PurchaseOrder> findAllWithCustomerMatchingCity(
    @Param("city") String city
);
```

The `ON` condition limits which customer rows participate in the join without dropping left-side orders. This is still a regular JOIN for querying; it is not an instruction to fetch the association.

## 5. JOIN FETCH: Loading Associations with the Root Entity

When a screen needs customer details for each order, fetch join tells Hibernate to load the association in the same query:

```java
@Query("""
    select p
    from PurchaseOrder p
    join fetch p.customer
    where p.status = :status
    """)
List<PurchaseOrder> findWithCustomerByStatus(
    @Param("status") OrderStatus status
);
```

`join fetch p.customer` requests loading the customer together with `PurchaseOrder`. After the query finishes, accessing `p.getCustomer().getName()` does not trigger a separate lazy query for that association.

An INNER-style fetch join returns only orders that have a customer. To keep orders without a customer as well, use `left join fetch`:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.status = :status
    """)
List<PurchaseOrder> findWithOptionalCustomerByStatus(
    @Param("status") OrderStatus status
);
```

Fetch join alters how the association is loaded only for that specific query. It does not turn a global LAZY mapping into EAGER; other queries still use their own fetch plans.

## 6. Filtering by Child While Still Loading the Full Collection

Suppose `PurchaseOrder.items` is a LAZY OneToMany collection. To find orders containing at least one item for product `P-100`, a regular JOIN can filter:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    join p.items i
    where i.productCode = :productCode
    """)
List<PurchaseOrder> findOrdersContainingProduct(
    @Param("productCode") String productCode
);
```

This query selects orders with a matching item. The `p.items` collection is not marked for fetching; when the application iterates over the collection, Hibernate may issue another query.

If you need to filter parents by a child while still loading the parent's full collection, separate the filter using `exists` and fetch-join independently:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.items
    where exists (
        select i.id
        from PurchaseOrderItem i
        where i.purchaseOrder = p
          and i.productCode = :productCode
    )
    """)
List<PurchaseOrder> findOrdersAndAllItemsContainingProduct(
    @Param("productCode") String productCode
);
```

`exists` determines which orders are selected; fetch join loads the `items` collection for those orders. Separating them avoids using the same join alias to filter children and inadvertently treating the partially loaded collection in memory as complete.

Collection joins can produce multiple SQL rows per root entity, one row per matching child. `distinct` expresses the intent to receive unique root Entities at the JPQL result level. Hibernate 6 automatically deduplicates root Entity copies produced by fetch joins in entity results; other providers or versions may behave differently. Even when the ORM deduplicates, SQL still processes multiple rows across different children.

## 7. N+1 and When Fetch Join Helps

N+1 occurs when fetching N parents and then accessing a LAZY association on each parent, triggering roughly N additional queries:

```text
Query 1: fetch 30 PurchaseOrders
Query 2: fetch Customer of order 1
Query 3: fetch Customer of order 2
...
Query 31: fetch Customer of order 30
```

A ManyToOne fetch join retrieves orders and customers in a single query, reducing round-trips. Collection fetch joins can also reduce N+1, though you must consider child counts, SQL row counts, memory usage, and pagination.

Do not add fetch joins to every query. If an association is never accessed, loading extra data only increases transfer and processing overhead.

## 8. Collection Fetch Joins and Pagination

Collection fetch joins combined with `Pageable` require extra care. One parent with multiple children generates multiple SQL rows; the database paginates over joined rows while the application expects pagination over parents. This can produce wrong page sizes or force Hibernate to paginate in memory.

With Hibernate, you can enable fail-fast detection for collection fetch joins combined with pagination:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

A common solution uses two steps:

1. Query a page of IDs or root Entities matching filters and sort order, without fetching the collection.
2. Fetch-join the collection for that specific batch of IDs.
3. Reorder the detailed results to match the ID order from the first page, since `IN (:ids)` does not guarantee ordering.

```java
@Query("""
    select p.id
    from PurchaseOrder p
    where p.status = :status
    order by p.createdAt desc, p.id desc
    """)
Page<Long> findPageIds(
    @Param("status") OrderStatus status, Pageable pageable
);

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

If the page is empty, skip the second query to avoid `IN` with an empty collection. Batch fetching or DTO queries may also be used when more suitable.

## 9. Avoid Fetching Multiple Large Collections

Fetch-joining two large collections simultaneously can create a Cartesian product. If an order has 5 items and 4 payments, joining both collections can generate 20 SQL rows for a single order. Repeated data inflates network transfer, memory usage, and deduplication work.

Hibernate may also throw `MultipleBagFetchException` when fetching multiple bag collections together—typically `List` fields without an appropriate order/index mapping. Do not switch `List` to `Set` merely to bypass the error if doing so alters collection semantics or equality. Usually it is better to load large collections with separate queries, batch fetching, DTO projections, or separate endpoints.

## 10. JOIN FETCH and DTO Projections

When an API only needs a few fields, a DTO projection can be cleaner and lighter than loading an Entity graph:

```java
public record OrderCustomerView(
    Long orderId, String orderNumber, String customerName
) {
}
```

```java
@Query("""
    select new com.example.api.OrderCustomerView(
        p.id, p.orderNumber, c.name
    )
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<OrderCustomerView> findOrderViewsByCustomerCity(
    @Param("city") String city
);
```

The query uses a regular JOIN to filter and select fields for the DTO. Fetch join is unnecessary because the result is not a `PurchaseOrder` Entity requiring initialized associations. DTOs limit returned columns and avoid serializing bidirectional Entity graphs.

## 11. JPQL Limitations to Keep in Mind

- Fetch join must specify an association path, such as `join fetch p.customer` or `left join fetch p.items`.
- In standard JPQL, fetch joins do not declare an identification variable/alias like regular JOINs. Some Hibernate extensions permit aliases in specific cases, but avoid relying on them when portable JPQL is needed.
- Fetch joins cannot be used inside subqueries in standard JPQL.
- Fetch join is designed to load associations of the owner Entity; do not use it as a substitute for DTO projections.
- Do not combine collection fetch joins directly with pagination without evaluating row counts and provider behavior.

## 12. Common Errors

**Using JOIN but still encountering N+1.** A filtering JOIN does not guarantee the association is fetched. Inspect SQL when accessing associations and consider fetch join or EntityGraph.

**Fetch join increases result count.** Collection joins generate multiple SQL rows per root. Check `distinct`, child counts, and how the provider handles duplicate entities.

**Parents without an association disappear from results.** `join fetch` is an inner join; use `left join fetch` when parents without associations must be preserved.

**Collection contains only children matching the filter.** Separate filtering with `exists` and fetch the complete collection using an independent join fetch.

**Slow pagination or in-memory pagination warnings.** Use the two-step ID-then-fetch pattern, batch fetching, or DTOs.

**MultipleBagFetchException.** Avoid fetching multiple bag collections in one query; consider separate queries or batch fetching.

**DTO query errors when using fetch join.** Use a regular JOIN to select projection fields; fetch join is meant for associations on loaded Entities.

## 13. Selection Checklist

- Need to filter by association attributes: use `JOIN` or `EXISTS`.
- Need to load an Entity together with its association: use `JOIN FETCH` or EntityGraph.
- Need to keep parents without an association: use `LEFT JOIN` or `LEFT JOIN FETCH`.
- Only need a few fields for an API: use DTO projection and regular JOIN.
- Need to paginate parents together with a collection: query the page of IDs first, then fetch collections by ID, or use batch fetching.
- Avoid fetching multiple large collections simultaneously.
- Inspect SQL, returned row counts, round-trips, and execution plans on an actual database.

`JOIN` combines and filters data; `JOIN FETCH` controls loading associations into the Entity graph. Separating these two intents reduces N+1 queries without over-fetching data, breaking pagination, or producing queries with excessive row multiplication.