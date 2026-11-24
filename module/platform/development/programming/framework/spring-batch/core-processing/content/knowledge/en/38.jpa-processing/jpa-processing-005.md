# Lazy Relations in the Processor

When Spring Batch processes JPA entities, the processor often needs to read related data such as customer, address, order lines, or product. When associations are declared `FetchType.LAZY`, JPA loads them only upon access. This deferred loading avoids pulling a huge object graph unnecessarily, yet it can fail if the processor accesses an association after the persistence context has closed or the entity has become detached.

With `JpaPagingItemReader`, this requires special attention: the reader manages its own `EntityManager` to read page by page and by default can clear the persistence context after each page. Entities returned to the processor are therefore typically already detached. When the processor calls `order.getCustomer().getName()` or iterates over `order.getLines()`, Hibernate may throw `LazyInitializationException` because the proxy or collection no longer has an open session to load the data.

The solution should match the data the processor actually needs: fetch the relationship directly in the appropriate query, use a DTO projection, or reload the data by ID inside a transactional service. Never switch all relationships to `EAGER` or rely on Open Session in View to mask the problem.

## 1. What is lazy loading in JPA?

JPA allows an entity to reference another entity or a related collection. The fetch strategy determines when the provider loads related data:

- `FetchType.LAZY`: the association is loaded upon application access provided the persistence context is still active and capable of loading it.
- `FetchType.EAGER`: the provider ensures the association is loaded when the entity is retrieved; this does not guarantee a single SQL join query.

Example order entity:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public CustomerEntity getCustomer() {
        return customer;
    }

    public List<OrderLineEntity> getLines() {
        return lines;
    }
}
```

`customer` is an explicitly lazy many-to-one association. `lines` is a one-to-many collection, which defaults to lazy in JPA, though declaring it explicitly clarifies the mapping intent.

When querying `OrderEntity`, the provider may select only columns from the `orders` table and hold a proxy for `customer` along with an uninitialized collection for `lines`. Related data is loaded upon access as long as the proxy remains attached to an active persistence context.

## 2. Persistence context and detached entities

A persistence context is the entity-management scope of an `EntityManager`. Entities read within a context are managed. When the context is cleared, closed, or the entity is detached, that context no longer manages the entity.

| State | Meaning | Lazy relations |
|---|---|---|
| Managed | Entity is actively managed by a persistence context | Can load if the context/session is still active and supported by the provider. |
| Detached | Entity was previously managed but is no longer attached to that context | Unloaded lazy associations normally cannot load automatically. |
| Removed | Entity is marked for deletion in the context | Not an appropriate state for normal data processing. |
| New/Transient | Entity has not been persisted | Associations depend on mappings and the object graph wired in application code. |

A lazy proxy cannot open a new connection or start a transaction by itself. It depends on the persistence context that created it. Once that context is no longer active, initializing the proxy or collection fails.

With Hibernate, the common exception is `org.hibernate.LazyInitializationException`, typically with messages like "could not initialize proxy" or "failed to lazily initialize a collection". JPA does not standardize this exception class name across providers; other providers report equivalent errors in their own ways.

## 3. Why are lazy relations prone to error in ItemProcessor?

In a chunk Step, the reader reads items, the processor transforms items, and the writer persists output. However, a JPA reader may manage a persistence context separate from the chunk transaction's persistence context.

`JpaPagingItemReader` creates an `EntityManager` to execute page queries. In its default configuration, the reader manages the page-read transaction and clears the persistence context after each page to avoid holding every entity in memory. Consequently, entities passed to the processor are usually already detached, even though the processor executes inside the chunk transaction.

Conceptual diagram:

```text
JpaPagingItemReader
  |
  +--> Reader's EntityManager
  |       |
  |       +--> Query a page
  |       +--> Entities loaded
  |       +--> Clear persistence context
  |
  v
OrderEntity returned (detached)
  |
  v
ItemProcessor
  |
  +--> order.getCustomer().getName()
  |       |
  |       +--> Lazy proxy needs old EntityManager
  |               |
  |               +--> Context no longer manages entity
  |                       |
  |                       +--> LazyInitializationException
  |
  v
Writer
```

Important point: the fact that the processor runs inside a Step transaction does not mean entities from `JpaPagingItemReader` automatically become managed by that transaction's `EntityManager`. The two persistence contexts can be completely distinct.

Exact lifecycle details depend on the reader, Spring Batch version, and `transacted` configuration. Never rely on entities accidentally remaining managed in one specific configuration; explicitly design how needed relational data is fetched and test with your real configuration.

## 4. Example of LazyInitializationException

Suppose the processor needs the customer's name to build a DTO:

```java
@Component
public class OrderExportProcessor
        implements ItemProcessor<OrderEntity, OrderExport> {

    @Override
    public OrderExport process(OrderEntity order) {
        String customerName = order.getCustomer().getName();

        return new OrderExport(
                order.getId(),
                customerName);
    }
}
```

If `customer` was not loaded and the entity is detached, calling `getName()` triggers lazy loading with no active session to run the query. The processor fails before returning output to the writer.

A collection has the same problem:

```java
BigDecimal total = order.getLines().stream()
        .map(line -> line.getQuantity()
                .multiply(line.getUnitPrice()))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

If `lines` was not initialized before the entity detached, iterating over the collection also throws `LazyInitializationException`.

Not every getter call fails. Scalar fields already loaded in the query, such as `id` and `orderNumber`, can still be read from a detached object. The error happens when code tries to load uninitialized relational data or access a proxy bound to the old persistence context.

## 5. Do not use Open Session in View for Batch

Open Session in View (OSIV) is a common pattern in web applications that keeps a persistence context open across an HTTP request so views can access lazy relations. Spring Batch has no HTTP request wrapping a Job or Step in that manner.

Do not enable OSIV or keep a global session open just so a processor can touch lazy relations. Doing so makes transaction and query boundaries unpredictable, can cause N+1 queries, and holds database resources open too long.

Batch jobs should define needed data in the query/reader or reload it in a service with clear transactions. When a processor needs a DTO, construct the DTO while the required data is loaded and return it from the service instead of passing lazy proxies across multiple layers.

## 6. Approach 1: Fetch the relationship directly in the JPQL query

If the processor always needs a specific association, load it alongside the root entity with `JOIN FETCH`.

Example where the processor needs `customer`:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderEntity> orderReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from OrderEntity o
                    join fetch o.customer c
                    where o.tenantId = :tenantId
                      and o.status = 'PENDING'
                    order by o.id
                    """)
            .parameterValues(Map.of("tenantId", tenantId))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

For optional associations, use `left join fetch` if you still want orders without a customer:

```sql
select o
from OrderEntity o
left join fetch o.customer
where o.status = 'PENDING'
order by o.id
```

Once the query loads `customer` with `order`, the processor can read the customer's name from the already-loaded object graph without lazy loading after detachment.

`JOIN FETCH` works best for to-one relationships like many-to-one or one-to-one. For to-many collections, pay special attention when combining with pagination.

## 7. Approach 2: Use EntityGraph

JPA `EntityGraph` lets you specify which relationships to fetch for a given query or repository operation without changing the entity's default fetch strategy.

Example with Spring Data JPA:

```java
public interface OrderRepository extends JpaRepository<OrderEntity, Long> {

    @EntityGraph(attributePaths = "customer")
    @Query("""
           select o
           from OrderEntity o
           where o.id = :id
           """)
    Optional<OrderEntity> findWithCustomerById(@Param("id") Long id);
}
```

When multiple associations are needed in one fetch:

```java
@EntityGraph(attributePaths = {"customer", "shippingAddress"})
@Query("select o from OrderEntity o where o.id = :id")
Optional<OrderEntity> findDetailedById(@Param("id") Long id);
```

An `EntityGraph` specifies what data must be fetched, while the provider decides how to execute the query. The provider may use joins or additional queries; therefore, do not assume an `EntityGraph` always produces a single SQL statement.

With `JpaPagingItemReader`, the builder accepts a JPQL query string. To apply an `EntityGraph` on the reader, configure the appropriate query hint or use a repository/custom reader that supports `EntityGraph`. You cannot simply add an annotation to the entity and expect every query to automatically use the graph.

`EntityGraph` is useful when one use case needs a specific graph while other use cases want to preserve lazy loading. Inspect generated SQL and query counts to ensure the graph does not over-fetch.

## 8. Approach 3: Use a DTO projection instead of an entity graph

If the processor needs only a few fields from the entity and its relationships, a DTO projection is often the cleanest and safest option. The query returns selected scalar values and carries no lazy proxies through the pipeline.

Example DTO:

```java
public record OrderProcessData(
        Long orderId,
        String orderNumber,
        String customerName,
        String customerRegion) {
}
```

JPQL constructor expression:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderProcessData> orderDataReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return new JpaPagingItemReaderBuilder<OrderProcessData>()
            .name("orderDataReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select new com.example.batch.OrderProcessData(
                        o.id,
                        o.orderNumber,
                        c.name,
                        c.region)
                    from OrderEntity o
                    join o.customer c
                    where o.tenantId = :tenantId
                      and o.status = 'PENDING'
                    order by o.id
                    """)
            .parameterValues(Map.of("tenantId", tenantId))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Processor receiving the DTO:

```java
@Bean
ItemProcessor<OrderProcessData, OrderExport> orderExportProcessor() {
    return data -> new OrderExport(
            data.orderId(),
            data.orderNumber(),
            data.customerName(),
            data.customerRegion());
}
```

Benefits of DTO projections:

- No lazy proxies to initialize in the processor.
- Query fetches only required fields.
- No dependency on the persistence context after reading.
- Prevents accidentally serializing or mutating managed/detached entities.
- The processor's input contract explicitly documents available data.

If the processor needs child collections, a simple constructor projection cannot automatically assemble a full nested collection. Use a dedicated aggregation query, native SQL/DTO mapping, or a custom reader that builds aggregate items.

## 9. Approach 4: Read IDs and reload inside the processor's transaction

If relational data changes frequently or the processor needs logic over the latest state, the reader can return only IDs. The processor then calls a service to load the entity and required associations within a transaction.

Reader returning IDs:

```java
@Bean
@StepScope
JpaPagingItemReader<Long> orderIdReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<Long>()
            .name("orderIdReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o.id
                    from OrderEntity o
                    where o.status = 'PENDING'
                    order by o.id
                    """)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Service loading required data:

```java
@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderProcessData loadForProcessing(Long orderId) {
        OrderEntity order = orderRepository.findDetailedById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        return new OrderProcessData(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                order.getCustomer().getRegion());
    }
}
```

Processor invoking the service:

```java
@Bean
ItemProcessor<Long, OrderProcessData> orderLoadingProcessor(
        OrderQueryService orderQueryService) {
    return orderQueryService::loadForProcessing;
}
```

Inside the service method, the repository loads a fresh entity and the `EntityGraph` fetches the customer. The service reads the associations and converts them into a DTO before the transaction ends. The processor receives a complete DTO with no lazy loading left.

### If the reader returns entities instead of IDs

You can read the already-loaded scalar ID from the detached entity and pass it to the service:

```java
return orderQueryService.loadForProcessing(detachedOrder.getId());
```

Do not touch `detachedOrder.getCustomer()` to read an ID or relational field. Use the root entity's already-loaded primary key.

### Transaction considerations

The service must be called through a Spring bean proxy for `@Transactional` to take effect. If a method calls another method on the same object, self-invocation can bypass transaction proxies depending on the proxy mechanism.

The service's transaction typically joins the current chunk transaction when using the same transaction manager and default `REQUIRED` propagation. Even so, the service loads a fresh entity into the current transaction's persistence context; it does not reattach lazy proxies belonging to the reader's old `EntityManager`.

## 10. Does @Transactional on the processor fix it?

Adding `@Transactional` to the processor does not automatically fix lazy relation errors on detached entities.

Example:

```java
@Component
public class OrderProcessor
        implements ItemProcessor<OrderEntity, OrderExport> {

    @Override
    @Transactional(readOnly = true)
    public OrderExport process(OrderEntity order) {
        return new OrderExport(
                order.getId(),
                order.getCustomer().getName());
    }
}
```

This transaction may open a fresh persistence context. However, `order` is still a detached entity returned by the reader; the `customer` proxy remains tied to the old, cleared/closed persistence context. A new `EntityManager` does not automatically take ownership of old proxies.

If you need a transaction to load relationships, reload the entity by ID in the new transaction or use a query projection/entity graph. `@Transactional` works for services issuing fresh queries, not as automatic reattachment for detached entities.

## 11. Approach 5: Merge the entity and then access associations

JPA `merge` can bring the state of a detached entity into a new persistence context and return a managed instance. However, `merge` is not the default solution for lazy relations.

Illustrative example:

```java
@Transactional
public OrderExport mapDetachedOrder(OrderEntity detached) {
    OrderEntity managed = entityManager.merge(detached);
    return new OrderExport(
            managed.getId(),
            managed.getCustomer().getName());
}
```

If you use `merge`, you must use the returned instance (`managed`), not keep accessing the input object (`detached`). Merging can trigger extra queries/state copying and still remains subject to optimistic locking on updates. Unfetched associations follow JPA provider-specific merge semantics; do not rely on `merge` to automatically load every needed collection.

If you only need to read a few fields, querying by ID with an `EntityGraph` or projection is far cleaner. If you need to update the entity, define versioning, transactions, and merge rules before merging.

## 12. Why shouldn't you switch all relations to EAGER?

A quick workaround is changing `LAZY` to `EAGER` so relationships are always loaded. This may make one use case pass while creating performance and data bloat problems for others.

Risks:

- Entity graphs become larger than the processor requires.
- Many secondary queries run while reading a single page.
- N+1 queries can still occur depending on provider and mappings.
- Pages containing many entities plus child relations inflate heap usage.
- Cyclic or multi-level `EAGER` chains make graphs hard to predict.
- A reader needing only a few fields ends up loading unused data.

`EAGER` is a mapping-level fetch requirement, not a guarantee that the provider will always issue one efficient SQL join. Keep mappings faithful to domain characteristics and define fetch plans per Step use case.

## 13. Be careful with JOIN FETCH on collections during paging

Fetch-joining to-one relations usually combines well with paging. With collections like `@OneToMany`, one root entity can produce multiple SQL rows:

```text
Order 1001 + Line A
Order 1001 + Line B
Order 1001 + Line C
Order 1002 + Line D
```

Applying `setFirstResult`/`setMaxResults` over a row-multiplied join can cause the database to slice a page right across child rows of the same order. The provider may fall back to in-memory pagination or emit warnings; actual root entity counts can differ from expectations and performance can plummet.

Example to avoid using indiscriminately:

```sql
select distinct o
from OrderEntity o
left join fetch o.lines
where o.status = 'PENDING'
order by o.id
```

`distinct` does not automatically solve all row-multiplication issues when the database applies limit/offset. With Hibernate, fetch-joining collections alongside pagination can produce warnings and in-memory pagination depending on version and settings.

Better alternatives:

- Page root IDs first, then load collections for that batch of IDs in a separate query.
- Use a DTO projection or aggregate query if only summarized fields are needed.
- Use a custom reader that builds aggregate items per page.
- Split the work into a root-reading step and a child-processing step if business rules allow.
- Use batch fetching when proxies coexist within an open persistence context and benchmark the effect.

Do not use collection fetch joins in a paging query without verifying generated SQL, root item counts, and memory behavior on realistic data.

## 14. N+1 queries when the processor loads relationships

Even without `LazyInitializationException`, loading relationships inside the processor can cause N+1 queries.

Suppose a Job reads 1,000 orders. Each time the processor calls a service to load the order with its customer in one query and then accesses `lines` in another query:

```text
1 query fetches page/root orders
1000 queries fetch customer or detail
1000 queries fetch order lines
```

Query counts scale linearly with item count, slowing down the Job and overloading the database.

Ways to reduce N+1:

- Use projections to select needed fields in the original query.
- Fetch-join required to-one relations.
- Use `EntityGraph` for explicit fetch plans.
- Batch-load associations by groups of IDs using bulk queries.
- Use batch fetching/subselect within an open persistence context where appropriate.
- Measure query counts and execution plans before increasing page or chunk size.

`@BatchSize` or `hibernate.default_batch_fetch_size` can cut down lazy queries when multiple proxies/collections coexist in an open persistence context. They do not enable a detached proxy to self-load after the `EntityManager` has closed or cleared.

## 15. Using DTO projections for one-to-many relational data

If the processor needs line counts, total quantities, or specific fields from order lines, compute aggregates in the query or create an aggregate DTO.

Aggregate query example:

```sql
select new com.example.batch.OrderSummary(
    o.id,
    o.orderNumber,
    c.name,
    coalesce(sum(l.quantity * l.unitPrice), 0))
from OrderEntity o
join o.customer c
left join o.lines l
where o.status = :status
group by o.id, o.orderNumber, c.name
order by o.id
```

DTO:

```java
public record OrderSummary(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal lineTotal) {
}
```

An aggregate query does not instantiate a Java `lines` collection, yet supplies the exact values the processor needs. If all child records are required, query them by batch of root IDs and map them into aggregates using a custom reader or preprocessing step.

When using `GROUP BY`, test orders with zero lines, multiple lines, decimal precision, and `coalesce` semantics. Paging queries also need a unique sort key over the aggregated results.

## 16. Explicit initialization inside an open persistence context

If the application uses Hibernate, you can explicitly initialize a proxy or collection via `Hibernate.initialize(...)` while the session is still open:

```java
@Transactional(readOnly = true)
public OrderExport loadAndMap(Long orderId) {
    OrderEntity order = entityManager.find(OrderEntity.class, orderId);

    Hibernate.initialize(order.getCustomer());
    Hibernate.initialize(order.getLines());

    return mapToExport(order);
}
```

Here, the entity is loaded in the current transaction and relationships are initialized before the service returns a DTO. Never call `Hibernate.initialize(detachedOrder.getLines())` on an already-detached entity because the original session is gone.

`Hibernate.initialize` is a Hibernate-specific API rather than standard JPA. Whenever possible, JPQL fetch plans, `EntityGraph`, or DTO projections express intent more cleanly and reduce provider lock-in.

## 17. Lazy relations in a processor chain

If a Step uses `CompositeItemProcessor`, one delegate might access a lazy relation while a later delegate simply maps a DTO. Failure still hits the first delegate touching an unloaded proxy.

Example:

```text
Detached OrderEntity
      |
      v
CustomerEnrichmentProcessor
      |
      +--> order.getCustomer().getName()
      |       |
      |       +--> LazyInitializationException
      |
      v
OrderExportMappingProcessor (not executed)
```

Design the chain's input contract so every delegate receives all required data. Either use a projection/DTO from the reader, or have an early delegate call a service to load data and emit an enriched DTO. Do not leave downstream delegates implicitly depending on lazy proxies that upstream delegates never guaranteed were loaded.

If a delegate returns `null`, the chain filters the item out and downstream delegates do not run. That differs from a lazy-loading failure: a lazy exception is a processing error, not a filter signal.

## 18. Transaction boundaries and services called from processors

A processor in a chunk Step normally runs within the chunk transaction, but an `@Transactional` service joins that transaction properly only when invoked through a Spring proxy using a compatible transaction manager.

Separate service example:

```java
@Service
public class OrderEnrichmentService {

    private final OrderRepository repository;

    public OrderEnrichmentService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderExport enrich(Long orderId) {
        OrderEntity order = repository.findDetailedById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        CustomerEntity customer = order.getCustomer();
        return new OrderExport(
                order.getId(),
                order.getOrderNumber(),
                customer.getName());
    }
}
```

Processor:

```java
@Component
public class OrderEnrichmentProcessor
        implements ItemProcessor<Long, OrderExport> {

    private final OrderEnrichmentService service;

    public OrderEnrichmentProcessor(OrderEnrichmentService service) {
        this.service = service;
    }

    @Override
    public OrderExport process(Long orderId) {
        return service.enrich(orderId);
    }
}
```

The service converts the entity into a DTO while associations are still accessible. Do not return an `OrderEntity` carrying lazy relations outside the service and map it in a layer without a persistence context.

If a Step involves multiple transaction managers, specify the exact manager for both the service and Step. A service opening a transaction on a different datasource does not automatically join the chunk transaction.

## 19. Should the reader return entities or IDs/DTOs?

Choose the item type based on processing needs:

| Reader returns | Advantages | Considerations |
|---|---|---|
| JPA entity | Convenient when the processor needs already-loaded fields and domain behavior. | Entity may be detached; unloaded lazy relations can fail. |
| ID | Lightweight, carries no lazy proxies; easy to reload fresh state. | Can issue an extra query per item if not batched. |
| DTO projection | Contains only needed fields, independent of persistence context. | Requires defining projection/query; field changes require mapping updates. |
| Aggregate DTO | Carries root and aggregated child data. | More complex query/grouping; requires checking paging and duplicates. |

If the processor merely builds output from a few fields, a DTO projection is usually the clearest choice. If it must update the latest entity state, reading IDs/commands and reloading inside a transaction often fits better. Pass entities down the pipeline only when their lifecycle and fetch plan are well understood.

## 20. Configuring transacted on JpaPagingItemReader

`JpaPagingItemReader` has a `transacted` option related to how the reader manages transactions/persistence context per page. The default configuration manages page-read transactions and can clear the persistence context after each page. Specialized configurations can change how the reader handles the context, yet keeping entities managed across pages can cause the persistence context to grow and raise memory usage.

Do not toggle context-retention settings merely to avoid fixing the processor. Evaluate:

- Is the reader's `EntityManager` actually the persistence context used by the processor or service?
- How long does the context live, and when is it cleared or closed?
- Could thousands or millions of entities accumulate in managed state?
- Will lazy queries fire mid-processing and lengthen transaction/connection hold times?
- Is the reader used inside a multi-threaded Step?
- Have restart and memory behavior been tested?

In particular, changing `transacted` does not automatically turn the reader's `EntityManager` into a shared context with the Step's transaction manager. Check the documentation for your exact version and test the concrete lifecycle before relying on it. An explicit fetch plan or DTO projection is usually far easier to control.

## 21. Fetching relations and data consistency

When relations are fetched in the reader, the root entity and its associations are captured according to that query/page. If the processor reloads relations in a separate transaction or at a later point, it may observe newer state.

Decide the business semantics:

- Does the processor need the relationship's state as of when the reader read the root?
- Does the processor need the latest state at processing time?
- Must the Job observe a consistent snapshot across multiple chunks?
- If a customer changes region between read and process, which value should appear in the output?

If a snapshot is required, a single fetch join or `EntityGraph` does not guarantee all pages and relations reflect the exact same point in time. You need appropriate transaction isolation/snapshots or staging/versioned data aligned with the database and chunk boundaries.

If latest state is required, reload within a transaction and define how to handle entities that are no longer in the expected state. Do not mix the two semantics accidentally.

## 22. Handling missing or deleted relationships

Lazy relations do not fail solely because a session closed. An association may not exist, or the related row may be deleted between reading the root and reloading in the processor.

Scenarios:

- Nullable foreign key: the relation may be `null`.
- Related row deleted: a reload query may fail to find the entity.
- Referential integrity: the database may block deletion while foreign keys remain.
- Proxy pointing to a nonexistent row: the provider may throw when initializing.
- Relation modified between two transactions: the processor may see a different relation than the reader saw.

Define a clear policy: skip, reject the record, use an older snapshot, or fail the Step. Do not use `Optional` or null checks to hide inconsistent data if that represents a contract violation.

## 23. Testing failing lazy relations

Write integration tests reproducing the true lifecycle of the reader and processor. A simple test with a lazy entity:

```java
@Test
void detachedEntityCannotInitializeLazyCustomer() throws Exception {
    JpaPagingItemReader<OrderEntity> reader = createOrderReader();
    reader.open(new ExecutionContext());

    OrderEntity order;
    try {
        order = reader.read();
    } finally {
        reader.close();
    }

    assertThatThrownBy(() -> order.getCustomer().getName())
            .isInstanceOf(LazyInitializationException.class);
}
```

This illustrative test requires Hibernate and a fixture with an unfetched `customer`. The reader must mirror production settings; if the query already fetches `customer`, asserting an error no longer applies. Exact exception names and timing depend on the provider.

You can check loaded state using the JPA Persistence API:

```java
PersistenceUnitUtil util = entityManagerFactory
        .getPersistenceUnitUtil();

assertThat(util.isLoaded(order, "customer")).isFalse();
```

With Hibernate, `Hibernate.isInitialized(order.getCustomer())` or its collection equivalent checks whether a proxy/collection has been initialized. Do not invoke the association getter inside an assertion if the getter itself could trigger lazy loading.

## 24. Testing EntityGraph or fetch join

When a query fetches the relation, verify the relation is initialized and the processor maps it successfully:

```java
@Test
void entityGraphLoadsCustomerForProcessor() {
    OrderEntity order = orderRepository.findDetailedById(orderId)
            .orElseThrow();

    assertThat(entityManagerFactory
            .getPersistenceUnitUtil()
            .isLoaded(order, "customer"))
            .isTrue();

    OrderExport result = processor.process(order);

    assertThat(result.customerName()).isEqualTo("Lan");
}
```

This test assumes the processor does not require other unfetched associations. If the processor uses `lines`, add that relation to the fetch plan or switch to an appropriate projection/service query.

To verify query counts, use Hibernate Statistics or a datasource proxy in integration tests. Seed fixtures with multiple orders across distinct customers and confirm query counts do not grow linearly with item count unexpectedly.

## 25. Testing DTO projections

For projections, verify the query returns all required fields and the processor needs no persistence context:

```java
@Test
void projectionContainsFieldsRequiredByProcessor() {
    OrderProcessData data = reader.read();

    assertThat(data.orderId()).isEqualTo(orderId);
    assertThat(data.customerName()).isEqualTo("Lan");
    assertThat(data.customerRegion()).isEqualTo("VN");

    OrderExport result = processor.process(data);
    assertThat(result.customerName()).isEqualTo("Lan");
}
```

A DTO projection is a plain object with no lazy proxies. You can close the reader/`EntityManager` before invoking the processor in unit or integration tests to prove the processor has no persistence context dependency.

## 26. Testing N+1 and collection paging

A SQL/performance test should include:

- A page with multiple root entities.
- Multiple distinct customers/associations.
- Some roots with no relation.
- One root with multiple child rows.
- More than one page.
- Reader restarts mid-page if the Step must support restarts.

Verify:

- SQL `SELECT` count does not scale linearly with item count unexpectedly.
- Pagination returns the exact number of root entities without duplicates or omissions.
- The collection fetch plan does not force the provider to load the entire result set into memory.
- Query plans use appropriate indexes.
- DTOs/projections handle roots with zero children accurately.

Do not test solely with a fixture containing one order and one customer; such a tiny fixture misses N+1 queries and row multiplication.

## 27. Common pitfalls

### Accessing a lazy relation on a detached entity

The processor invokes a proxy/collection getter after the reader clears/closes the persistence context. Fetch the relation in the query, use a DTO, or reload the entity in a transaction.

### Assuming the Step transaction auto-attaches reader entities

The reader may use its own `EntityManager`. A new chunk transaction does not automatically adopt old proxies. Reload the entity in the active context.

### Adding @Transactional while still using old proxies

A new transaction does not initialize proxies bound to an old `EntityManager`. Query again by ID or fetch data before detachment.

### Switching every relation to EAGER

This can cause bloated object graphs, N+1 queries, and unnecessary data loading. Choose fetch plans per use case.

### JOIN FETCHing collections with pagination

Row multiplication breaks pagination or forces in-memory paging. Use DTOs, page IDs and batch-load children, or use an aggregate reader.

### Using EntityGraph assuming only one query runs

Providers may issue secondary queries. Inspect actual SQL and query counts.

### Merging detached entities to load all relations

`merge` is not a fetch plan mechanism and can introduce extra queries and version conflicts. Querying by ID with an `EntityGraph` or projection is clearer.

### Calling Hibernate.initialize on a detached entity

There is no active session to initialize against. Call it inside an open context or reload the entity in a service.

### Causing N+1 when reloading item by item

The processor queries each entity or association individually. Use projections, fetch plans, or bulk queries by ID batches and measure query counts.

### Relying on OSIV

Batch jobs lack a web HTTP request scope. Manage persistence contexts and transactions explicitly within the Job.

### Leaving data semantics undefined

Fetching in the reader vs. reloading in the processor can observe two different states. Pick snapshot or latest-state semantics based on business requirements.

## 28. Workflow for handling lazy relations in the processor

When a processor needs relational data, follow these steps:

1. Identify the exact associations and fields the processor needs.
2. Determine whether the reader returns detached entities or DTOs/IDs; inspect the reader's `EntityManager` lifecycle.
3. If only a few fields are needed, prefer a DTO projection in the query.
4. If a to-one relation is needed, consider `JOIN FETCH` or `EntityGraph`.
5. If a collection is needed, avoid direct collection fetch joins with paging unless pagination accuracy is proven; consider aggregates/projections or batched queries by ID.
6. If latest state is needed, have the reader emit IDs/commands and let a transactional service reload the entity.
7. Map to a DTO before leaving the transaction; never leak lazy proxies to downstream layers.
8. Do not use global `EAGER` mappings or OSIV to hide the problem.
9. Measure SQL/query counts to catch N+1 queries and inspect execution plans.
10. Test lazy exceptions, loaded associations, collection paging, restarts, and concurrent data changes.
11. Define explicit snapshot vs. latest-state semantics between reader and processor.

| Need | Appropriate approach |
|---|---|
| Processor needs fields from a to-one relation | `JOIN FETCH` or `EntityGraph` on the appropriate query |
| Processor needs only a few fields across tables | DTO projection |
| Processor needs latest entity state | Read IDs/commands and reload via `@Transactional` service |
| Processor needs child collections while paging | Aggregate DTO, separate query by batch of IDs, or custom reader; avoid arbitrary collection fetch joins |
| Entity is already detached and needs a lazy relation | Do not touch old proxies; reload the entity in a fresh persistence context |
| Want to verify a relation is loaded | `PersistenceUnitUtil.isLoaded` or provider inspection APIs |
| Want to reduce N+1 queries | Explicit fetch plans, projections, batched queries, and SQL count checks |

## Conclusion

Lazy relations in the processor commonly trigger `LazyInitializationException` when entities read by `JpaPagingItemReader` are already detached after the reader's per-page persistence context lifecycle. Neither the chunk transaction nor `@Transactional` on the processor automatically reattaches proxies tied to an old `EntityManager`. Choose a fetch plan tailored to the data required: `JOIN FETCH` or `EntityGraph` for appropriate associations, DTO projections when only selected fields are needed, or reading IDs and reloading entities inside a transactional service when latest state is required. Avoid switching all mappings to `EAGER`, avoid direct collection fetch joins with paging unless verified, and watch for N+1 issues using query counts. Map relational data into DTOs before leaving the persistence context, and test reader lifecycles, loaded state, pagination, and snapshot vs. latest-state semantics for the Job.
