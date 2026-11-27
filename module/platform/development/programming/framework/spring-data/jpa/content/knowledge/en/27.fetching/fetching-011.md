# Fetching Multiple Collections, Cartesian Products, and MultipleBagFetchException

When an entity has multiple collections, loading all of them in a single `JOIN FETCH` query can produce an unexpectedly huge amount of data. With Hibernate, if multiple collections mapped as bags are fetched together in the same query, the application may also encounter `MultipleBagFetchException`.

To handle this properly, distinguish three issues:

- **Loading multiple collections at once:** this is a fetch-plan decision.
- **Cartesian product:** SQL result row counts grow as the product of element counts across the joined collections.
- **MultipleBagFetchException:** a Hibernate-specific exception thrown when one query tries to fetch multiple bags simultaneously.

This lesson uses an order entity with a list of order lines and a list of discounts to explain the causes, diagnostics, and data-loading alternatives.

## 1. Model with Multiple Collections

Suppose an order has many order lines (`lines`) and many discounts (`discounts`):

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderDiscount> discounts = new ArrayList<>();

    // getters and domain methods
}
~~~

This is an illustrative mapping snippet assuming `OrderLine` and `OrderDiscount` have `@ManyToOne` relationships pointing back to `PurchaseOrder`. In a real project, add constructors, getters, setters, or bidirectional helper methods per your entity design.

In Hibernate, a `List` without `@OrderColumn` is typically mapped with **bag** semantics: an unordered collection with no persisted positional index distinguishing elements by order. A bag permits duplicates and does not guarantee ordering like an indexed list.

Distinguish:

- `List` without `@OrderColumn`: typically has bag semantics in Hibernate.
- `List` with `@OrderColumn`: Hibernate persists element positions; the collection has indexed list semantics.
- `Set`: a collection disallowing duplicates per `equals()`/`hashCode()` rules and not mapped with bag semantics.
- `@OrderBy`: sorts elements when read by a property; not equivalent to persisting positional indices via `@OrderColumn`.

`MultipleBagFetchException` is a Hibernate exception, not an exception defined by the JPA specification. It typically appears when Hibernate must simultaneously fetch multiple associations mapped as bags in the same query.

## 2. Why Does JOIN FETCH on Multiple Collections Create a Cartesian Product?

Suppose an order has:

- 3 lines in `lines`.
- 4 discounts in `discounts`.

A query joining both collections simultaneously produces combinations between order lines and discounts. In this example, a single order can generate:

**3 × 4 = 12 SQL result rows.**

With 10 lines and 8 discounts, the combinations can reach 80 rows for a single order. With multiple collections and many root entities, the volume of data transferred from the database to the application can explode rapidly.

JPQL example:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    left join fetch o.discounts
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithLinesAndDiscounts(@Param("id") Long id);
~~~

Join result diagram for one order:

~~~mermaid
flowchart TD
    O[PurchaseOrder]
    O --> L1[Line 1]
    O --> L2[Line 2]
    O --> L3[Line 3]
    O --> D1[Discount 1]
    O --> D2[Discount 2]
    O --> D3[Discount 3]
    O --> D4[Discount 4]
    L1 -. combined with .- D1
    L1 -. combined with .- D2
    L1 -. combined with .- D3
    L1 -. combined with .- D4
~~~

At the SQL level, each order line is paired with every discount belonging to the same order. The database returns columns for the order and both collections repeated across many rows.

### What Does DISTINCT Solve?

`select distinct o` requests eliminating duplicate root entity results per query semantics. It is useful when a JPQL result has multiple rows referencing the same entity.

However, `DISTINCT` **does not eliminate the Cartesian product at the SQL layer**: the database still has to construct and process all line × discount combinations to supply the rows needed for hydration. Therefore, `DISTINCT` is not a performance fix for fetching too many collections.

In Hibernate 6, duplicate root entities caused by collection fetch joins are typically deduplicated automatically from the entity result. Depending on Hibernate version and JPA portability goals, `DISTINCT` may still be written to express query intent clearly; it does not change the number of SQL combinations processed.

## 3. What Is MultipleBagFetchException?

Hibernate must reconstruct collections from the returned SQL rows. When a query fetches multiple bags simultaneously, distinguishing bag elements from the combined result rows becomes ambiguous. Hibernate proactively rejects such queries and throws `org.hibernate.loader.MultipleBagFetchException`.

Example query that can trigger the exception when both `lines` and `discounts` are bags:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    left join fetch o.lines
    left join fetch o.discounts
    where o.id = :id
    """)
Optional<PurchaseOrder> findAllDetails(@Param("id") Long id);
~~~

Conditions to remember:

- The exception relates to simultaneously fetching multiple bags, not merely having two collections on an entity.
- Two collections can be loaded in separate queries without triggering this error.
- One bag and one `Set` may not trigger this specific exception, yet the query still risks creating a large Cartesian product.
- Replacing `List` with `Set` solely to dodge the exception can alter data semantics and fails to solve the underlying row-multiplication issue.

When encountering this error, inspect the query's fetch plan, collection mappings, and Hibernate-generated SQL. Do not look only at the number of root entities in the Java result; check the actual number of rows returned by the database.

## 4. Recommended Approach: Split into Multiple Queries

A common pattern is fetching only one bag per query. For example, the first query loads the order with `lines`; the second query loads the same order with `discounts`.

**Repository:**

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.lines
        where o.id = :id
        """)
    Optional<PurchaseOrder> findWithLines(@Param("id") Long id);

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.discounts
        where o.id = :id
        """)
    Optional<PurchaseOrder> findWithDiscounts(@Param("id") Long id);
}
~~~

**Service:**

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrderDetails(Long id) {
        PurchaseOrder order = repository.findWithLines(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order not found"));

        // Second query fetches the discounts collection.
        // Same persistence context, so the entity with the same ID is managed
        // by the same PurchaseOrder instance.
        repository.findWithDiscounts(id);

        return order;
    }
}
~~~

These are illustrative snippets assuming entities and repositories are configured with Spring Data JPA. You will need to import `EntityNotFoundException`, `Entity`, `FetchType`, `JpaRepository`, `Query`, `Param`, `Service`, `Transactional`, and related types in your project.

The key point is that both queries run within the **same transaction and persistence context**. The persistence context maintains an identity map: the same entity with the same primary key is managed by the same instance. The first query initializes `lines`; the second query initializes `discounts` on that same managed entity. When `order` is returned, both collections have been loaded.

Advantages:

- Each query joins only one bag collection.
- Avoids a Cartesian product between two collections in a single SQL statement.
- Repository code explicitly reflects each fetch plan needed.
- Transactions can be managed in the service while keeping required associations in the same persistence context.

In return, the application executes more SQL statements. For one order and two collections, it typically needs two fetch-join queries; weigh collection counts, root entity counts, and actual round-trip costs.

## 5. Other Data-Loading Strategies

No single fetch strategy suits every screen or use case. Choose based on entity counts, collection sizes, and the data that actually needs to be returned.

### 5.1. Lazy Loading Combined with Batch Fetching

Keeping collections LAZY, Hibernate can batch loading multiple collections of the same type into an `IN` query instead of issuing a separate query per entity.

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
~~~

`@BatchSize` is a Hibernate-specific annotation. You can configure an application-wide default using:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

When multiple collections of the same type are accessed within one persistence context, Hibernate can load them in groups up to the configured batch size. This reduces N+1 in many cases without joining all collections into one query.

Batch fetching does not mean every query always uses the exact configured batch count; Hibernate decides based on pending associations and the runtime context.

### 5.2. Subselect Fetching

Hibernate provides `@Fetch(FetchMode.SUBSELECT)` to load collections for a group of parent entities using a secondary query based on the query that loaded the parents:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
~~~

This is a Hibernate-specific feature. It can be helpful when a query retrieves many orders and the application needs to access the same collection across many of those orders within the persistence context.

Inspect actual SQL and the scope of affected entities, because subselect can load more collections than a specific code path needs.

### 5.3. EntityGraph

Spring Data JPA supports `@EntityGraph` to declare associations to load for a repository method:

~~~java
@EntityGraph(attributePaths = "lines")
@Query("select o from PurchaseOrder o where o.id = :id")
Optional<PurchaseOrder> findWithLinesById(@Param("id") Long id);
~~~

You can declare another method loading only `discounts`, and invoke them within the same transaction just like the split-query approach above.

`EntityGraph` describes a fetch plan; it does not guarantee the provider uses a particular SQL strategy. Putting multiple collections in the same graph can still cause the provider to build large joins or hit the same limits. Inspect actual SQL.

### 5.4. DTO Projection

If a screen only needs a few fields, consider returning a DTO instead of loading the entire entity graph. DTO projections fetch exactly the required data, reduce column counts, and avoid initializing unneeded collections.

Simple projection example:

~~~java
public record OrderSummary(
        Long id,
        OrderStatus status,
        BigDecimal totalAmount) {
}
~~~

The repository can select the corresponding fields directly:

~~~java
@Query("""
    select new com.example.dto.OrderSummary(
        o.id, o.status, o.totalAmount)
    from PurchaseOrder o
    where o.id = :id
    """)
Optional<OrderSummary> findSummaryById(@Param("id") Long id);
~~~

Package names and types in the example must match your project. If a DTO needs data from multiple collections, query each part or run one query per data group and assemble the results in the service. This keeps row counts and result shapes predictable.

### 5.5. Using Set or Indexed List When Semantically Appropriate

If business rules genuinely require a duplicate-free set, `Set` can be a good fit. When using entities as `Set` elements, design `equals()` and `hashCode()` carefully, especially when IDs are generated upon persistence.

If business logic requires an ordered list whose positions are persisted in the database, you can use `@OrderColumn`:

~~~java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines = new ArrayList<>();
~~~

Note: actual `@OrderColumn` mapping must match owning relationships, bidirectional management, and the project's JPA/Hibernate version. Inspect the schema and position-update SQL before adopting it.

`Set` or `@OrderColumn` can change how Hibernate classifies collections and avoid the bag exception in some cases. Still, joining multiple collections simultaneously can produce a Cartesian product. Choose `Set` or `@OrderColumn` only when data semantics genuinely require it.

## 6. Pagination Considerations

Fetch joining even one collection in a paginated query can cause Hibernate to paginate in memory or emit performance warnings, because a single root entity can span multiple SQL rows. Joining a second collection compounds the data volume dramatically.

A safer pattern:

1. Query a page of root entity IDs using filter conditions and `Pageable`, without fetching collections.
2. Load the entities and one collection via a `where id in :ids` query.
3. Load the next collection in a separate query within the same transaction.
4. Re-sort results to match the original page's ID order because an `IN` query does not guarantee ordering.

ID query example:

~~~java
@Query(
    value = "select o.id from PurchaseOrder o order by o.createdAt desc",
    countQuery = "select count(o) from PurchaseOrder o"
)
Page<Long> findOrderIds(Pageable pageable);
~~~

Once the ID list is retrieved, the service calls the batched fetch queries. Keep transactions and persistence contexts consistent if you want Hibernate to merge fetched collections onto the same entity instances. With real filters, `value` and `countQuery` must share equivalent predicates so total page counts are accurate.

## 7. Approaches That Lead to Misconceptions

**Adding DISTINCT and assuming the Cartesian product is gone.** `DISTINCT` deduplicates entity results; it does not eliminate the row combinations required at the SQL layer.

**Converting all Lists to Sets just to avoid the exception.** This can alter data meaning, ordering, duplicate allowance, and `equals()`/`hashCode()` behavior. Meanwhile, SQL row counts can still be huge.

**Setting every relationship to FetchType.EAGER.** `EAGER` requests associations to load per JPA fetch semantics, but does not guarantee a single efficient SQL query. Providers may use joins or secondary queries; over-fetching still degrades performance.

**Simultaneously fetching multiple collections in an EntityGraph without checking SQL.** `EntityGraph` defines associations to load, but does not remove join overhead or Hibernate's multi-bag limitations.

**Using collection fetch joins directly with Pageable.** Paginating over multiplied rows can return unexpected results or force Hibernate to paginate in memory. Paginate IDs first and load collections in batches.

**Returning entities with LAZY collections outside transactions.** Serializers or controllers may access collections after the persistence context closes and trigger `LazyInitializationException`. Load needed data inside transactions or return DTOs.

## 8. Testing and Diagnostics

A helpful integration test seeds varying element counts across collections—for example, an order with 3 order lines and 4 discounts.

For the split-query strategy:

- Invoke the service inside a transaction.
- Verify the result has exactly 3 order lines.
- Verify there are exactly 4 discounts.
- Verify both collections are initialized before the transaction ends.
- Verify data is not duplicated and element attributes match the database.

For batch or subselect strategies, inspect SQL statement counts across multiple orders to confirm N+1 is reduced. For pagination, check total record counts, page ordering, and cases where an entity has many collection elements.

When investigating performance, enable SQL logging in development and inspect:

- Number of SQL statements executed.
- Number of rows returned by each query.
- Repeated queries per entity.
- Whether selected columns are actually needed.
- Database time, entity hydration time, and memory usage.

You can use Hibernate statistics or database query-monitoring tools to measure executions and timing. Do not judge solely by fewer SQL statements: one join returning thousands of combinations can cost more than a few small queries.

## 9. Process for Choosing a Fetch Strategy

1. Identify exactly which collections the use case requires.
2. Inspect mappings to see which collections are bags, `Set`s, or indexed `List`s.
3. If only one collection is needed, consider fetch join or `EntityGraph` for that collection.
4. If multiple bags are needed, prefer splitting into multiple queries within the same transaction or using batch fetching.
5. If a page of data is needed, paginate root entities first and load collections in batches.
6. If only display data is needed, consider DTO projections.
7. Measure SQL and test with data of realistic cardinality.

## Conclusion

`MultipleBagFetchException` typically indicates a fetch plan is trying to load multiple bags simultaneously in a single Hibernate query. Cartesian products are a separate performance issue: joining multiple collections multiplies SQL row counts by the product of element counts, even when no exception is thrown.

The sustainable solution is to fetch data per use case: split queries per collection within the same persistence context, use batch/subselect fetching when appropriate, paginate IDs before loading collections, or return DTOs when a full entity graph is unnecessary. Choose `Set` or `@OrderColumn` only when data semantics genuinely call for it.