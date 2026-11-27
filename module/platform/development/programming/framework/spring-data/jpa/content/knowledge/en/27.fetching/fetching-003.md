# JOIN FETCH to Load Data Based on Per-Case Needs

## 1. Fetching Data by Use Case

An entity often has multiple associations: an order references a customer, has multiple order lines, payments, and status history. Not every use case needs all of that data. A list screen might need only the order number and customer name; a detail screen needs order lines as well; a report might need only a few aggregated columns.

`JOIN FETCH` in JPQL allows instructing JPA to load an association together with the root entity in a single query. This is a way to build a fetch plan per repository method, suitable when you know clearly which associations a use case needs.

Design principles:

- Load only the associations that the use case is about to use.
- Keep default mappings LAZY for most relationships, then choose the fetch plan at the query or repository method level.
- Use `JOIN FETCH` for associations with appropriate size and cardinality.
- Use `EntityGraph`, batch fetching, or DTO projections when they express the need better.
- Verify SQL, returned row counts, query counts, and memory usage on realistic data.

A fetch plan is a data-reading decision. It does not change association ownership, cascades, or entity lifecycle.

## 2. How Do JOIN and JOIN FETCH Differ?

`JOIN` joins an association to filter, sort, or read related properties within a query. It does not instruct the provider to initialize the association in the entity graph.

`JOIN FETCH` both joins the association and instructs the provider to load that association together with the root entity. After the query, code can access the association without a separate LAZY query for the fetched association.

Example using only `JOIN` to filter orders by the customer's city:

```java
@Query("""
    select p
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findByCustomerCity(@Param("city") String city);
```

The query uses `c.city` for filtering. `p.customer` is not requested to be fetched; if the code accesses `customer` afterward and the association is not already in the persistence context, Hibernate may still issue an additional query.

For a use case that needs to display the customer along with the order:

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

`join fetch p.customer` requests loading `customer` in the same query. Choose regular `JOIN` or `JOIN FETCH` based on whether the association needs to be initialized in the result or only participates in conditions.

## 3. LAZY Mappings and Per-Query Fetch Plans

Entity example:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<PurchaseOrderItem> items = new ArrayList<>();
}
```

With the mapping above, default queries do not need to load `customer` or `items` immediately when retrieving `PurchaseOrder`. Repository methods can select associations per screen:

- Order list: fetch `customer` if the list displays the customer name.
- Order detail: fetch `customer` and `items` if the detail page displays both.
- Summary report: use a DTO/projection if only order count, total amount, or customer name is needed.
- Order processing job: fetch only the associations that the algorithm actually requires.

JPA defaults `ManyToOne` and `OneToOne` to EAGER; `OneToMany` and `ManyToMany` are LAZY. Consider declaring to-one associations as LAZY to avoid unintended loading, then specify an explicit fetch plan per use case. EAGER does not guarantee the provider will always use a single SQL JOIN; the provider may execute secondary queries.

## 4. INNER JOIN FETCH or LEFT JOIN FETCH?

A fetch join without specifying the join type defaults to an INNER JOIN. INNER JOIN returns only root entities that have a matching association. If the relationship can be null and you still want to keep the root entity, use `LEFT JOIN FETCH`.

Example where customer is optional:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.id = :id
    """)
Optional<PurchaseOrder> findDetailHeader(@Param("id") Long id);
```

The order is still returned even when `customer` is null. With `join fetch p.customer`, orders without a customer would be excluded from the results.

Choose the join type according to business semantics:

| Requirement | Approach |
| --- | --- |
| Association required and return only roots with association | `join fetch` |
| Association optional but still need to keep the root | `left join fetch` |
| Association not needed in the result | Do not fetch the association |

Do not switch INNER to LEFT merely to be "safe" without verifying semantics. The join type determines which root entities appear in the result.

## 5. Use Case 1: List Screen Needing One To-One Association

An order list screen often displays order number, creation date, status, and customer name. Loading a list of `PurchaseOrder`s and then calling `getCustomer().getName()` for each order can trigger N+1.

The repository can fetch the to-one association:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.status = :status
    order by p.createdAt desc, p.id desc
    """)
List<PurchaseOrder> findListRowsWithCustomer(
    @Param("status") OrderStatus status
);
```

This is a suitable option when the number of root entities is reasonably bounded and the list truly needs `customer`. For paginated screens, fetch joining a to-one association generally works much better than fetch joining a collection because each root pairs with at most one customer.

If you only need `customer.name` for the response, a DTO projection can be even lighter because it avoids materializing the full entity graph.

## 6. Use Case 2: Detail Page Needing a Bounded Collection

A single order's detail page typically needs customer information and all line items for that single order. You can fetch both a to-one and one collection:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.customer
    left join fetch p.items
    where p.id = :id
    """)
Optional<PurchaseOrder> findDetailById(@Param("id") Long id);
```

The query is constrained by ID, so the root count is small. `items` can still be numerous, so ensure a single order cannot hold an unexpectedly huge collection. If a collection contains tens of thousands of elements, do not load them all just because the endpoint is displaying a header.

`distinct` expresses the intent to receive unique root entities in the JPQL result when the collection join creates multiple rows for the same order. SQL still needs to return the distinct child rows so Hibernate can initialize the collection. Hibernate 6 automatically removes duplicate root entities caused by fetch joins from the entity result; behavior may differ in other providers/versions.

## 7. Use Case 3: Loading Only Partial Related Data

Fetch join loads associations according to the association mapping. It is not a mechanism for projecting individual columns inside a collection. If the page only needs product code, quantity, and price of line items, you can use a DTO projection:

```java
public record OrderItemRow(
    Long orderId,
    String orderNumber,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {
}
```

```java
@Query("""
    select new com.example.order.OrderItemRow(
        p.id, p.orderNumber, i.productCode, i.quantity, i.unitPrice
    )
    from PurchaseOrder p
    join p.items i
    where p.id = :id
    order by i.id
    """)
List<OrderItemRow> findItemRows(@Param("id") Long id);
```

This is a JPQL constructor projection; the fully qualified class name and constructor must match the expression. The query uses a regular `JOIN` because it constructs DTOs from the required columns without needing to initialize `PurchaseOrder.items` in the persistence context.

Use DTOs when you need read-only data with a fixed structure and do not need entity operations, cascading, or dirty checking. Use fetch join when the caller genuinely needs the entity with initialized associations.

## 8. Use Case 4: Filtering by Child While Loading the Entire Collection

Suppose you need to find orders that have at least one item belonging to product `P-100`, and then the detail page needs all items of each order.

Do not use a fetch join alias both to filter children and expect the full collection to be loaded. If the collection is fetched only through children matching the condition, the application may see an incomplete collection.

Separate the filter condition with `EXISTS` and fetch the collection separately:

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
List<PurchaseOrder> findOrdersWithAllItemsForProduct(
    @Param("productCode") String productCode
);
```

`exists` determines which roots satisfy the condition. `left join fetch p.items` loads the complete `items` collection for the selected roots. This query may return multiple SQL rows per order; do not combine it directly with collection-fetch pagination without a separate strategy.

## 9. Avoiding N+1 with Fetch Join

N+1 commonly appears when a query retrieves N root entities, and then the code accesses a LAZY association on each entity:

```text
Query 1: fetch 30 orders
Query 2: fetch customer for order 1
Query 3: fetch customer for order 2
...
Query 31: fetch customer for order 30
```

Fetch joining a to-one association can load the customer in the same query, reducing round-trips. For collections, fetch join can also reduce N+1, though it increases SQL row count according to the number of children.

To confirm a real N+1:

- Enable SQL logging in development/test environments.
- Count the SELECT statements while processing a page of data.
- Check which associations are accessed after the main query.
- Use data with multiple roots to see query counts scale with N.
- Measure total row counts and execution time, not just the number of SQL statements.

Do not fetch every association just to avoid an extra query if the use case does not use that data. Fewer queries are not necessarily cheaper if each query returns far too many columns and rows.

## 10. Fetch Joining Multiple Associations

You can fetch multiple to-one associations in the same query if they have suitable cardinality:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    left join fetch p.createdBy
    where p.id = :id
    """)
Optional<PurchaseOrder> findHeaderWithPeople(@Param("id") Long id);
```

Fetching multiple to-many collections requires caution. If an order has 5 items and 4 payments, joining both collections can produce 20 SQL rows for the same root. This is a Cartesian product between the two child sets.

Hibernate may throw `MultipleBagFetchException` when simultaneously fetching multiple bag collections, typically `List`s without an appropriate order/index mapping. Changing `List` to `Set` solely to avoid the exception can alter semantics and equality; nor does it eliminate the SQL row multiplication.

For multiple large collections, prefer:

- Fetching one primary collection in the first query and loading remaining collections via separate queries.
- Batch fetching to group association-loading queries.
- DTO projections fetching only the needed data.
- Splitting endpoints/use cases if the data has independent lifecycles or sizes.

## 11. Fetch Join and Pagination

Fetch joining a to-one association can usually be combined with `Pageable`, because the join does not multiply root rows when cardinality is right. Fetch joining a collection is different: each root can produce multiple SQL rows, while database `LIMIT`/`OFFSET` applies to the joined rows.

Therefore, do not directly paginate a `Page<PurchaseOrder>` query that has `left join fetch p.items`. Hibernate may emit a warning or paginate in memory; with large datasets, this loads excessive rows and consumes significant memory.

A common solution is two steps:

1. Fetch a page of root IDs using filters and a stable sort, without fetching collections.
2. Fetch collections for that ID list in a second query.
3. Re-sort the results according to the first page's ID order because `IN (:ids)` does not guarantee order.

Repository example:

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

If the first page is empty, skip the second query to avoid `IN` with an empty collection. Include the ID as a tie-breaker for stable sorting. If you need a consistent snapshot across both queries while data changes concurrently, consider transaction isolation according to business and database requirements.

## 12. EntityGraph: Declarative Fetch Plan Alternative

You do not always need to write JPQL fetch joins. Spring Data JPA supports `@EntityGraph` to specify associations to load for a repository method:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    Optional<PurchaseOrder> findWithCustomerAndItemsById(Long id);
}
```

`attributePaths` uses the entity's Java property names. `EntityGraph` separates query conditions from the fetch plan and is easy to reuse across methods. The provider decides how to translate the graph into SQL; check actual SQL to see whether joins or additional queries are used.

You can declare a named entity graph on the entity when a graph is reused repeatedly. Dynamic `EntityGraph` fits well when repository methods need different fetch plans per use case.

`EntityGraph` also does not automatically solve collection pagination issues. If a graph loads a collection in a paginated query, you must still evaluate cardinality and provider behavior.

## 13. Batch Fetching and Other Options

When you need to access a LAZY association across many roots without joining all rows into one query, batch fetching can load multiple associations in a few grouped queries.

Hibernate example:

```java
@BatchSize(size = 50)
@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Or global default configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 50
```

`@BatchSize` is a Hibernate-specific annotation. Batch fetching keeps the association LAZY until accessed, and then can load multiple collections/proxies in one query using multiple IDs. The batch size should be tuned against workload and database bind parameter limits.

For reports or read-only responses, DTO projections are often better than loading a large entity graph. For a collection accessed across many roots, batch fetching can balance query counts and row counts. Choose based on real data and behavior, not merely annotation count.

## 14. Fetch Plans Do Not Alter Mapping or Lifecycle

`JOIN FETCH` does not make an association EAGER across all queries. It only requests loading the association for the current query.

A fetch plan also does not:

- Change the owning side or `mappedBy`.
- Automatically synchronize both sides of a relationship in memory.
- Enable cascade persist/merge/remove.
- Enable orphan removal.
- Decide which data an API is allowed to return.

For example, fetching `p.items` only loads the collection. It does not mean adding an item to the collection will automatically persist it if cascade is not configured or the owning side is not updated.

## 15. Transaction Boundaries and Serialization

A LAZY association may trigger queries when accessed. If the persistence context is closed, accessing an unloaded association can throw `LazyInitializationException` in Hibernate.

Do not rely on Open Session in View so that all associations remain accessible during response serialization. Doing so can let JSON serialization silently trigger N+1 and hold database sessions longer than expected.

Instead:

- Load required associations inside the service transaction using fetch join or `EntityGraph`.
- Map results to DTOs before the transaction ends.
- Do not return bidirectional entity graphs directly if they could cause JSON cycles or leak internal data.
- Use projections when only a specific set of fields is needed.

## 16. How to Verify a Fetch Plan Matches Requirements

For each use case, list the data actually used:

| Use Case | Data Needed | Fetch Approach to Consider |
| --- | --- | --- |
| Order list | Header + customer name | To-one fetch join or DTO |
| Order detail | Header + customer + bounded items | Collection fetch join for single root or EntityGraph |
| Summary report | ID, total amount, counts | DTO projection/aggregate query |
| Processing multiple orders | One collection needed per root | Batch fetching or grouped queries |
| Paginated orders and items | Page of roots + collection | Two-step ID pagination then fetch collection |

Verify using SQL logs, Hibernate statistics, or database observability tools:

- Number of SELECT statements per request.
- Number of SQL rows returned after joins.
- Selected columns and payload size.
- Which associations are actually accessed.
- Query duration and execution plan.
- Memory usage when processing large collections.

Tests should include multiple roots and multiple children; a test with only one order and one item often fails to reveal N+1 or row multiplication.

## 17. Common Mistakes

**Using regular JOIN and still hitting N+1.** Regular `JOIN` is for filtering/joining; use `JOIN FETCH` or `EntityGraph` if the association needs to be initialized.

**Using INNER FETCH and losing roots without the association.** Switch to `LEFT JOIN FETCH` if business logic requires retaining those roots.

**Fetching a collection causes the query to return many rows.** Multiple rows per root is natural join behavior. Use `distinct` when unique roots are desired and evaluate SQL row counts.

**Fetching multiple collections causes huge queries or MultipleBagFetchException.** Split queries, batch fetch, or use DTOs; do not change collection types mechanically.

**Fetching a collection with Page causes in-memory pagination.** Paginate IDs first and fetch collections afterward, or choose batch/DTO.

**Collection contains only children matching a condition.** Do not filter on a fetch join alias and assume the full collection is loaded; isolate the filter with `EXISTS` and fetch the collection separately.

**LazyInitializationException while building a response.** Load needed data inside the transaction and map to a DTO before closing the persistence context.

**Over-fetching unused data.** Review each use case, remove unneeded associations, and consider DTO projections.

## 18. JOIN FETCH Checklist

- Does the use case actually need the association in the result?
- Is the association to-one or to-many? Is the child count reasonably bounded?
- Choose INNER vs. LEFT based on whether roots without the association must be kept.
- Can a DTO projection be used if only certain fields are needed?
- Are multiple collections fetched together causing row multiplication or a bag exception?
- Is collection fetch combined with pagination? If so, switch to a two-step strategy or batch fetching.
- Are child filter conditions separated from collection fetching so collections are not partially loaded?
- Is the fetch plan scoped to the query/use case instead of globally changing mappings to EAGER?
- Have SQL, row counts, query counts, memory, and transactions been verified?

`JOIN FETCH` works best when chosen for the data a use case genuinely needs. Fetch to-one associations for lists, fetch bounded collections for detail pages, and use `EntityGraph`, batch fetching, or DTOs when data shapes differ. Controlling cardinality and pagination reduces N+1 without turning a small request into an oversized data load.