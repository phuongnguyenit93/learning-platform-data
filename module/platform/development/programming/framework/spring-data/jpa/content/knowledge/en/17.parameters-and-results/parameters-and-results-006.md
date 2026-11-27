# Collection, List, Set, and Result Ordering Contracts

Spring Data JPA allows repositories to return multiple collection types such as Collection, List, and Set. These types have distinct Java contracts: Collection is a general abstraction, List preserves element positions and allows duplicates, while Set disallows duplicates according to equals() rules without guaranteeing iteration order. Those contracts must be distinguished from the order in which a database returns rows.

A query only has deterministic order when the query includes ORDER BY or the repository accepts a Sort/Pageable with sorting. Declaring a return type as List does not automatically sort results; declaring Set does not replace SELECT DISTINCT. This lesson explains how to choose a return type, ensure stable ordering, handle duplicate rows from JOINs, sort association collections, and manage pagination caveats.

## 1. Three collection types have different contracts

Java defines Collection as the root interface for collections. List and Set are two subtypes with distinct rules.

| Type | Allows duplicates? | Ordering contract | When appropriate |
|---|---|---|---|
| Collection<T> | Yes | No guarantee on order or position | Caller only needs to iterate over results |
| List<T> | Yes | Ordered by list index position | Needed for display, pagination, or preserving query order |
| Set<T> | No, per equals() | No guarantee on iteration order | Need a unique set of elements independent of position |

Key points to remember:

- **Collection** does not specify ordering and does not deduplicate.
- **List** is indexed, preserves insertion order into the list, and allows equal elements.
- **Set** eliminates duplicate elements according to the implementation's equality rules; Set in general does not guarantee iteration order.
- **HashSet** does not guarantee iteration order.
- **LinkedHashSet** preserves insertion order, but you should not rely on which concrete implementation Spring Data chooses to infer a repository contract.
- **TreeSet** maintains order by a comparator or natural ordering, but requires entities to have proper comparison rules and converting results to it must be explicitly configured and tested.

Choose the return type according to the data semantics required by the calling layer. If users expect ordered results, List is the clear choice. If deduplication by equality is needed, Set may fit, provided you understand the elements' equals() and hashCode().

## 2. Returning List does not guarantee database order

Repository example:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

The method returns a List, so the caller can access elements by index. However, the query has no ORDER BY, so the database is free to return rows in any order matching its execution plan.

Order can change when:

- The database picks a different execution plan.
- Indexes are created or modified.
- Data is inserted, deleted, or updated.
- The database is upgraded.
- The query runs on a different database engine.

Do not rely on physical table order, natural ID order, or insertion order. If business rules require results sorted by time, name, or priority, declare the sort criteria explicitly.

JPQL example:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
List<PurchaseOrder> findByStatusOrdered(
    @Param("status") OrderStatus status
);
~~~

ORDER BY defines result ordering by createdAt descending, then by id descending. The primary key is added as a secondary sort key to handle multiple orders sharing the same createdAt.

## 3. Sorting with derived queries

Spring Data JPA allows declaring fixed ordering directly in the method name:

~~~java
List<PurchaseOrder> findByStatusOrderByCreatedAtDescIdDesc(
    OrderStatus status
);
~~~

The method name breaks down as:

- findByStatus: filters by the status property.
- OrderByCreatedAtDesc: sorts by createdAt descending.
- IdDesc: if createdAt values are equal, sorts by id descending.

This works well when a repository method always shares the same ordering rule.

You can use First or Top to limit the number of results:

~~~java
Optional<PurchaseOrder> findFirstByStatusOrderByCreatedAtDescIdDesc(
    OrderStatus status
);
~~~

This method fetches at most one latest order according to the specified ordering. If no record matches, the Optional is empty.

Do not use First/Top without defining the business-expected order. Limiting row counts without ORDER BY can still return different records across runs.

## 4. Dynamic sorting with Sort

When the caller needs to choose the sort order at runtime, the repository accepts Sort:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Invocation:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<PurchaseOrder> orders =
    repository.findByStatus(OrderStatus.PAID, sort);
~~~

Sort can contain multiple criteria. The database applies them in declared order: createdAt first, then id.

Property names in Sort are Java entity property names, not SQL column names. If the createdAt field is mapped with @Column(name = "created_at"), Sort still uses createdAt.

For APIs accepting sort keys from clients, whitelist allowed fields. Never pass raw user strings into query expressions or JpaSort.unsafe. Sort fields are query structure, not bind parameter values.

## 5. Why is a secondary sort criterion needed?

Suppose two orders were created at the exact same timestamp 10:00. A query with only ORDER BY createdAt DESC does not specify the order between those two orders.

When data contains duplicate sort values, their relative order is not guaranteed. This can cause:

- Results shifting positions between runs.
- Pagination showing duplicate or skipped items when data changes.
- Tests depending on accidental database ordering.
- Unstable UI display.

Add a unique key as a tie-breaker:

~~~jpql
order by o.createdAt desc, o.id desc
~~~

With this ordering, two rows with identical createdAt are still distinguished by id. Apply this same rule to every paginated query or API needing deterministic results.

When sorting by names, consider collation and case-insensitivity. If NULL values are present, NULL ordering can vary across databases; when business requirements demand consistency, specify it explicitly with an appropriate expression and test on the target database.

## 6. Set is not a sorting mechanism

Repository example:

~~~java
Set<PurchaseOrder> findByStatus(OrderStatus status);
~~~

A Set result carries no iteration order contract. Even if the query includes ORDER BY or the caller passes Sort, do not rely on Set iteration order for displaying data.

If ordering is part of the requirement, return a List:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Set is appropriate when the caller only cares about membership or deduplication by equals(). Do not use Set merely to get "cleaner" results or hope the database order is preserved.

An implementation like LinkedHashSet may preserve insertion order, but a repository contract declaring Set does not guarantee which concrete implementation the caller receives. When order matters, declare List and use ORDER BY/Sort.

## 7. Set deduplicates via equals() and hashCode()

Set determines whether two elements are duplicates based on element equality rules and the Set implementation.

For JPA entities, this makes equals() and hashCode() critical. If an entity uses the default Object.equals(), two different instances representing the same database row may not be considered equal. If equals() is implemented incorrectly or hashCode() changes after an ID is assigned, Set may hold unexpected results or fail to locate added elements.

Consider:

- Should two instances of the same entity with the same ID be considered equal?
- How are new entities without IDs compared?
- Is hashCode stable after persisting?
- Are Hibernate proxies handled properly?
- Does equality accidentally depend on association collections or mutable fields?

Do not use Set as a workaround to mask entity equality problems. Design equals()/hashCode() around entity identity and lifecycle; if cross-persistence-context equality is unnecessary, keeping default object identity may be safer.

## 8. Set and DISTINCT solve two different problems

Two layers must be distinguished:

1. **DISTINCT in JPQL/SQL** eliminates duplicate rows according to query semantics.
2. **Set in Java** eliminates duplicate elements according to equals()/hashCode() of objects added to the collection.

For example, a Customer has many PurchaseOrders. The query:

~~~jpql
select c
from Customer c
join c.orders o
where o.status = :status
~~~

can produce multiple rows for the same Customer if that Customer has multiple matching orders.

If you want to query unique Customer entities, write:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
~~~

Or if you only need a unique set of scalar values, select the appropriate expression:

~~~jpql
select distinct c.city
from Customer c
where c.city is not null
~~~

Set does not replace database DISTINCT. When a query returns a List with duplicates, converting to a Set removes duplicates in Java, but this happens at the Java layer and may require loading all rows. DISTINCT lets the database handle deduplication semantics inside the query.

Also do not assume SELECT DISTINCT entity and SELECT DISTINCT field mean the same thing. Two Customers with different IDs in the same city are still two distinct entities, whereas SELECT DISTINCT c.city keeps only one city value.

## 9. DISTINCT and count queries

When using JOIN, COUNT(entity) may count joined rows instead of unique root entities.

For example, to count Customers with at least one PAID order:

~~~jpql
select count(distinct c.id)
from Customer c
join c.orders o
where o.status = :status
~~~

COUNT(DISTINCT c.id) counts unique Customers. This is the explicit approach when a one-to-many relationship multiplies rows.

Be careful with derived query names like countDistinctByStatus. In Spring Data JPA, DISTINCT may be applied to the entity ID by the query generator rather than meaning "count distinct status values". If you want to count distinct scalar values, declare an explicit JPQL query:

~~~java
@Query("""
    select count(distinct o.status)
    from PurchaseOrder o
    """)
long countDistinctStatuses();
~~~

When using Page with JOIN, the countQuery must reflect the unit being counted. If the page content consists of unique Customers, the count query typically needs COUNT(DISTINCT c.id), not COUNT(*) over joined rows.

## 10. Collection, List, and Set in a repository

Combined repository example:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Collection<PurchaseOrder> findByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatusOrderByCreatedAtDescIdDesc(
        OrderStatus status
    );

    Set<PurchaseOrder> findDistinctByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );

    Slice<PurchaseOrder> findSliceByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

These methods illustrate different contracts:

- Collection is a general choice when the caller does not require indexed access or uniqueness.
- List fits when ordering is required or duplicate results are allowed.
- Set fits when the caller needs unique elements by equality.
- Page holds a page's content along with total element and page counts.
- Slice holds a page's content and whether a next page exists, typically avoiding a total count query.
- Sort and Pageable allow choosing ordering at call time.

Do not declare multiple methods with identical parameter signatures as shown above in a single Java interface. In practice, give each method a distinct name, such as findCollectionByStatus, findSetByStatus, or use one primary repository method with the desired return type. The snippet above illustrates return types and signatures, not a ready-to-copy interface, since Java does not allow overloading solely on return type.

## 11. Page and Slice always need intentional ordering

Pageable can carry a Sort:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.PAID, pageable);
~~~

Page<T> provides getContent(), getTotalElements(), getTotalPages(), getNumber(), and navigation info. Page content is a List, but its order is only stable when the query has deterministic sorting.

Slice<T> is useful when the UI only needs to know if there is a next page. It usually fetches one extra element to determine hasNext() instead of executing a full count query.

Offset pagination can become expensive at large offsets and can shift items when rows are inserted or deleted between reads. For large or rapidly changing datasets, consider keyset/scrolling pagination if supported by your Spring Data JPA version and query type. Keyset pagination also requires stable ordering, typically sort fields plus a unique key.

## 12. Ordering association collections: @OrderBy

Repository query ordering differs from association collection ordering within an entity.

Example:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @OrderBy("createdAt DESC, id DESC")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
~~~

@OrderBy instructs JPA to sort the collection by properties of the associated entity when loading it. In this example, orders are sorted by createdAt descending and id descending when the collection is initialized.

Names inside @OrderBy are Java property names on the PurchaseOrder entity, not SQL column names. This annotation applies when loading the association collection; it does not automatically sort independent repository queries.

If a specific query needs a different order, use Sort or JPQL ORDER BY on that repository method.

## 13. How @OrderBy differs from @OrderColumn

The two annotations serve different purposes:

| Annotation | How it works | When appropriate |
|---|---|---|
| @OrderBy | Sorts elements by entity property values when loading the collection | Want the list always ordered by date, name, or data criteria |
| @OrderColumn | Stores element position in an order column on the join/collection table | Want to preserve user-defined or explicit list ordering |

@OrderColumn example:

~~~java
@OneToMany(mappedBy = "playlist")
@OrderColumn(name = "position_index")
private List<Track> tracks = new ArrayList<>();
~~~

In an appropriate mapping owning the order column, the provider maintains element positions in the database. When the list is reordered, position_index values can be updated to reflect the new positions.

@OrderBy does not persist manual positions. It computes order from property values upon reading. If two elements share the same sort value, add a secondary criterion for stable results.

Do not declare both @OrderBy and @OrderColumn on the same association as interchangeable alternatives. Choose the mechanism matching the domain's ordering semantics and verify your JPA/provider version's mapping rules.

## 14. Is a Set association appropriate when order is needed?

Set associations usually fit when a relationship represents membership: for instance, a user's roles or an article's tags. If business requirements demand display order, a plain Set cannot express a positional contract.

You can query the association via a dedicated repository with Sort when ordering is needed. Or use a List association if ordering is part of the model.

Do not switch List to Set solely to prevent duplicates if each element needs a position or can repeat in the domain. For example, a playlist can contain the same song multiple times at different positions; a Set would destroy that meaning.

Conversely, role or permission lists usually have set semantics; Set can work well if element equality is stably defined.

## 15. Streaming large results

Repositories can return Stream<T> for certain query methods:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.id
    """)
Stream<PurchaseOrder> streamByStatus(
    @Param("status") OrderStatus status
);
~~~

A Stream can hold JDBC resources or the persistence context open while reading. Close the stream and maintain an appropriate transaction:

~~~java
@Transactional(readOnly = true)
public void processPaidOrders() {
    try (Stream<PurchaseOrder> stream =
             repository.streamByStatus(OrderStatus.PAID)) {
        stream.forEach(this::process);
    }
}
~~~

This snippet illustrates a service method; process must avoid retaining entities beyond the transaction or triggering uncontrolled N+1 queries.

Stream does not guarantee ordering on its own. In this example, ORDER BY o.id defines read order. If a streaming query has no ORDER BY, do not rely on stream iteration order.

## 16. Choosing a return type by requirement

Common scenarios:

| Need | Suitable type | Notes |
|---|---|---|
| Return all results, no position contract needed | Collection<T> | Does not guarantee ordering or uniqueness |
| Display an ordered list | List<T> | Requires ORDER BY or Sort |
| Need a list that may contain equal elements | List<T> | Use DISTINCT if query should deduplicate |
| Need a unique set of elements by equality | Set<T> | Design stable equals/hashCode |
| Need a page and total record count | Page<T> | May issue a count query |
| Only need to know if a next page exists | Slice<T> | Typically avoids total count query |
| Process large data in a stream | Stream<T> | Close stream and manage transaction |
| Need at most one result or none | Optional<T> | More than one result can trigger a cardinality error |

If requirements call for both uniqueness and ordering, express both explicitly in the query layer and data type. Usually it is best to fetch a List with DISTINCT and ORDER BY, then return DTOs to the API. Never use Set and expect ordering.

## 17. Testing ordering and uniqueness

A repository integration test suite should prepare data including:

- Multiple orders with the same status.
- Two orders with the same createdAt but different IDs.
- Two Customers with multiple orders matching the same JOIN condition.
- Two DTOs or entities sharing several fields while having different IDs.
- An association collection whose elements were inserted in a different order from createdAt.

Assertions should verify:

1. A List without ORDER BY is not asserted against an accidental fixed order.
2. A List with ORDER BY/Sort returns results matching the sort criteria.
3. Tie-breakers produce deterministic order when primary sort values match.
4. Set is not asserted by iteration order.
5. Set only deduplicates according to element equals/hashCode.
6. SELECT DISTINCT eliminates duplicates per query semantics.
7. COUNT(DISTINCT id) counts unique entities after JOIN.
8. Page has totalElements matching the count query.
9. @OrderBy sorts the association when the collection is loaded.
10. @OrderColumn preserves saved positions after reloading.

Example test for deterministic order:

~~~java
@Test
void returnsOrdersInDeterministicOrder() {
    List<PurchaseOrder> orders =
        repository.findByStatusOrderByCreatedAtDescIdDesc(
            OrderStatus.PAID
        );

    assertEquals(
        List.of(12L, 10L, 8L),
        orders.stream().map(PurchaseOrder::getId).toList()
    );
}
~~~

This test assumes the fixture created three PAID orders with timestamps and IDs matching the expected order. When using a real database, flush data before querying. Do not write tests for a List without ORDER BY that assert an arbitrary current order.

Set tests should verify membership or size, not order:

~~~java
assertEquals(3, resultSet.size());
assertTrue(resultSet.contains(expectedOrder));
~~~

If testing entity uniqueness, make sure entity equals/hashCode implements the semantics expected by the domain.

## 18. Common mistakes and fixes

**1. List order changes between runs**

The query lacks ORDER BY or Sort. Add sort criteria and a unique key as a tie-breaker.

**2. Using Set yet results still contain business duplicates**

Check equals/hashCode on the entity or projection. Set only deduplicates by Java equality; it does not infer business equivalence between two objects.

**3. Using Set and the UI does not follow Sort**

Set does not guarantee iteration order. Switch to List if order is required.

**4. Thinking Collection deduplicates automatically**

Collection allows duplicates. Choose Set or DISTINCT depending on the layer needing uniqueness.

**5. Thinking Set equals SELECT DISTINCT**

Set deduplicates in Java; DISTINCT belongs to query semantics. For large datasets, use DISTINCT or EXISTS in the query where appropriate to avoid loading redundant rows.

**6. countDistinctByStatus counts the wrong thing**

Inspect the generated SQL/JPQL. If you need to count distinct status values, write COUNT(DISTINCT status) explicitly instead of assuming the method name counts status values.

**7. Page ordering is unstable**

Add a Sort with a tie-breaker. Inspect the count query if JOINs can multiply rows.

**8. @OrderBy does not affect other repository queries**

@OrderBy only governs how the association collection is loaded. Independent repository queries need their own ORDER BY or Sort.

**9. Changing List to Set drops valid elements**

If the domain allows the same value to appear multiple times at different positions, Set is inappropriate. Use List and identify each element separately.

**10. Using @OrderColumn for a list that only needs date sorting**

If order can be derived from a createdAt property, @OrderBy is usually better and avoids storing an extra position index.

## 19. Process for choosing collections and result ordering

When designing a repository method, follow this sequence:

1. Determine whether business rules allow duplicate results.
2. Determine whether the caller needs ordering or indexed access.
3. Pick Collection, List, or Set based on the Java contract.
4. If ordering is needed, add JPQL ORDER BY, derived OrderBy, or Sort.
5. Add a unique key as a tie-breaker when stable results are required.
6. If the query JOINs collections, decide whether SELECT DISTINCT or EXISTS is needed.
7. If using Set, verify equals/hashCode and entity proxy semantics.
8. If paginating, use Page/Slice with stable Sort and an accurate count query.
9. If sorting an association, choose @OrderBy or @OrderColumn according to domain semantics.
10. If processing large datasets, consider Stream and manage transactions/resources.
11. Write integration tests on a database matching production.

## 20. Self-assessment checklist

- [ ] I can distinguish the contracts of Collection, List, and Set.
- [ ] I know List does not guarantee database order without ORDER BY.
- [ ] I know how to use derived OrderBy and dynamic Sort.
- [ ] I add a unique tie-breaker for deterministic ordering.
- [ ] I understand Set deduplicates via equals/hashCode and does not guarantee order.
- [ ] I distinguish Set from SELECT DISTINCT.
- [ ] I know to use COUNT(DISTINCT id) when counting entities after a JOIN.
- [ ] I understand Page, Slice, Pageable, and count queries.
- [ ] I distinguish @OrderBy from @OrderColumn.
- [ ] I know association collection ordering differs from standalone repository queries.
- [ ] I know to close Streams and keep transactions active during processing.
- [ ] I test Set membership and List ordering according to the query contract.

## 21. Review questions

**1. How do Collection, List, and Set differ?**

Collection is a general abstraction allowing duplicates; List allows duplicates and preserves positional order; Set disallows duplicates per equals() without guaranteeing iteration order.

**2. Does a repository returning List guarantee results ordered by ID?**

No. You need ORDER BY, derived OrderBy, or Sort. Never rely on physical or insertion order.

**3. Why is Set unsuitable when displaying sorted results?**

Set has no iteration order contract. Use List to preserve the order returned by the query.

**4. How do Set and DISTINCT differ?**

Set deduplicates in Java using equals/hashCode. DISTINCT deduplicates by selected query expressions and is processed at the query/database layer.

**5. Why must entity hashCode be stable when using Set?**

Set relies on hashCode to store and locate elements. If hashCode changes after an entity is added, contains/remove may fail to find the element.

**6. How does @OrderBy differ from @OrderColumn?**

@OrderBy sorts the collection by property values when loading. @OrderColumn stores element positions in the database to preserve list order.

**7. When should you use Slice instead of Page?**

When the UI only needs page content and whether a next page exists, without needing total element or total page counts. Slice typically avoids the total count query.

**8. How do you achieve stable pagination?**

Use a deterministic Sort with a unique key tie-breaker. For large or frequently changing datasets, consider keyset scrolling if supported by your query and version.

Choosing the right Collection, List, or Set lets repositories express clear data contracts. Combining return types properly with DISTINCT, ORDER BY, Sort, and pagination prevents unintended duplicates, unstable ordering, and hard-to-reproduce bugs across query executions.