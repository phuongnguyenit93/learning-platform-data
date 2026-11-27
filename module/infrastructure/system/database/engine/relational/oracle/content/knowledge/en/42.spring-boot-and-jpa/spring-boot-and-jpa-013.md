# Pagination, Batch Inserts/Updates, and Controlling N+1 Queries

In a Spring Boot application using Spring Data JPA and Hibernate, three issues directly dominate data-access performance: pagination, batch writes, and N+1 queries.

- **Pagination** bounds the number of rows returned per read, letting APIs control payload size, memory usage, and response time.
- **Batch inserts/updates** group multiple writes to cut round trips between the application and database while bounding persistence context memory.
- **N+1** occurs when an application loads a set of entities and then fires an extra query per entity or per association, scaling SQL count with record count.

These three concerns interact closely. An API paginating orders that lazily accesses order items can trigger N+1 queries. An import job calling `save` for tens of thousands of entities inside one transaction can exhaust heap despite using `saveAll`. A query fetch-joining a collection may solve N+1 while breaking pagination or forcing Hibernate to paginate in memory.

Optimizing effectively requires inspecting actual SQL, execution plans, round trips, data volumes, persistence context size, and transaction boundaries. Adding an annotation or flipping one configuration property alone does not guarantee the problem is solved.

## 1. Pagination with Spring Data JPA

Spring Data JPA supports pagination via the `Pageable` interface and return types such as `Page`, `Slice`, or `List`. Repositories accepting `Pageable` pass page index, page size, and sort criteria to the JPA provider to generate dialect-appropriate SQL.

Example order entity:

~~~java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    private Long id;

    @Column(name = "ORDER_DATE")
    private LocalDateTime orderDate;

    @Column(name = "STATUS")
    private String status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "CUSTOMER_ID")
    private Customer customer;
}
~~~

Repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
    Page<Order> findByStatus(String status, Pageable pageable);
}
~~~

Service:

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepository;

    @Transactional(readOnly = true)
    public Page<OrderResponse> findOpenOrders(int page, int size) {
        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("orderDate"),
                Sort.Order.desc("id")
            )
        );

        return orderRepository.findByStatus("OPEN", pageable)
            .map(OrderResponse::from);
    }
}
~~~

Controller accepting `page` and `size` query parameters:

~~~java
@GetMapping("/orders")
public Page<OrderResponse> findOrders(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    return orderService.findOpenOrders(page, size);
}
~~~

`PageRequest` uses zero-based page indices: page 0 is the first page, page 1 is the second. Validate and cap `size` from requests so clients cannot demand hundreds of thousands of rows in a single call.

### How Do Page, Slice, and List Differ?

| Return Type | Contents | Typical Cost | When to Use |
|---|---|---|---|
| `Page<T>` | Page content, page number, total elements, and navigation info | Usually runs an extra count query for total | UI needs total rows or total page count |
| `Slice<T>` | Content and whether a next page exists | Usually fetches one extra row to determine `hasNext` | Infinite scroll or "Load more" without needing total count |
| `List<T>` with `Pageable` | List for the requested slice | Does not provide `Page`/`Slice` metadata | Only one page of rows is needed, no metadata required |

`Page` fits screens displaying "1–20 of 3,450 records." In return, Spring Data typically executes a data query plus a count query. Counting can be expensive on joins, `DISTINCT`, or complex predicates.

`Slice` fits UIs needing only a "Load more" button or knowing whether more rows exist. The framework requests one row more than page size; if that extra row exists, `Slice.hasNext()` is true, avoiding a full count.

Example repository returning `Slice`:

~~~java
Slice<OrderSummary> findByStatus(String status, Pageable pageable);
~~~

If the API does not need total counts, choosing `Slice` can cut cost dramatically on large tables.

### Count Queries and Joins

When using `Page` with a `@Query` containing joins, auto-generated count queries can be complex or overcount when one entity appears multiple times across joins. Declare an explicit `countQuery` when needed:

~~~java
@Query(
    value = """
        select o
        from Order o
        join o.customer c
        where o.status = :status
          and c.region = :region
        """,
    countQuery = """
        select count(o)
        from Order o
        join o.customer c
        where o.status = :status
          and c.region = :region
        """
)
Page<Order> findOrders(
    @Param("status") String status,
    @Param("region") String region,
    Pageable pageable
);
~~~

If a collection join multiplies root rows, you may need `COUNT(DISTINCT ...)` or a redesigned query. Example:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.product_id = :productId;
~~~

The count query must count the unit being paginated—usually distinct root entities rather than post-join rows.

### Sorting Must Be Deterministic

When paginating, always enforce a deterministic order. Sorting solely by a non-unique column lets tied rows shift positions across requests. Add a unique tie-breaker, typically the primary key.

~~~java
Pageable pageable = PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Never concatenate user-supplied sort column strings directly into native SQL. With Spring Data `Sort`, allow only fields on an API allowlist. Sorting by nonexistent fields or arbitrary expressions causes errors and security risks in dynamic queries.

### Offset Pagination and Deep-Page Limits

Traditional pagination uses offset and limit/fetch-first. Conceptually, page 1000 with page size 20 skips 19,980 rows before returning the next 20.

Illustrative SQL:

~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE status = 'OPEN'
ORDER BY order_date DESC, order_id DESC
OFFSET 19980 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Oracle supports `OFFSET`/`FETCH` starting in 12c. Hibernate/Spring Data emits syntax matching the dialect and database version; do not hand-write one pagination syntax assuming it fits every database version.

With large offsets, the database must scan, sort, or skip many rows before returning the page. Performance degrades with page depth, especially without indexes covering filter and sort columns.

Offset pagination can also produce duplicate or skipped rows when data changes between requests. For example, if a client reads page 1 and a new row is inserted at the top before page 2 is fetched, page 2's offset shifts and repeats a previously seen row.

### Keyset/Seek Pagination

Keyset pagination uses the last row's values from the previous page as a cursor for the next page. It fits large, forward-scrolling lists with stable sort keys.

Suppose results are ordered by `createdAt` descending then `id` descending. After page 1, the client retains `lastCreatedAt` and `lastId` of the last row. Next-page query:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id < :lastId)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

This can be implemented as a repository query depending on database and JPA provider:

~~~java
@Query("""
    select o
    from Order o
    where o.status = :status
      and (
        o.createdAt < :lastCreatedAt
        or (
          o.createdAt = :lastCreatedAt
          and o.id < :lastId
        )
      )
    order by o.createdAt desc, o.id desc
    """)
List<Order> findNextOrders(
    @Param("status") String status,
    @Param("lastCreatedAt") LocalDateTime lastCreatedAt,
    @Param("lastId") Long lastId,
    Pageable limit
);
~~~

Keyset pagination must explicitly handle the first page (no cursor yet), NULLs in sort columns, sort directions, and composite sort keys. Pick non-NULL sort columns or enforce consistent NULL ordering. Cursors sent to clients can encode `lastCreatedAt` and `lastId`, serialized safely so clients cannot tamper with them.

Keyset pagination usually outperforms offset pagination on large datasets with proper indexes, though it does not naturally support jumping directly to arbitrary page numbers. This is a UX-driven trade-off, not a mandatory replacement for every API.

## 2. Pagination with JPA Associations

A critical trap is paginating entities with collection associations. If a query fetches `Order` and fetch-joins `orderItems`, SQL row counts equal `Order × OrderItem` combinations, no longer mapping 1-to-1 to `Order` rows.

Example:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.status = :status
    """)
Page<Order> findOrdersWithItems(
    @Param("status") String status,
    Pageable pageable
);
~~~

This looks like it solves N+1 by loading items at once, yet database-level pagination cannot reliably apply to collection fetch joins. Hibernate may have to load the entire joined result set and paginate in memory, spiking memory and latency. Some versions/configs warn when this happens.

Never fetch-join a large collection in the main paginated query. Enable fail-fast detection to catch this early:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

### Two-Query Strategy

A common pattern is:

1. Paginate root entity IDs.
2. Fetch required associations for those IDs in a second query.
3. Restore original ID order if the second query does not preserve ordering.

Repository:

~~~java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findOrderIds(
    @Param("status") String status,
    Pageable pageable
);

@Query("""
    select distinct o
    from Order o
    left join fetch o.customer
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithDetailsByIdIn(
    @Param("ids") Collection<Long> ids
);
~~~

Service:

~~~java
@Transactional(readOnly = true)
public Page<OrderResponse> findOrderPage(
        String status, Pageable pageable) {

    Page<Long> idPage = repository.findOrderIds(status, pageable);

    if (idPage.isEmpty()) {
        return new PageImpl<>(
            List.of(),
            pageable,
            idPage.getTotalElements()
        );
    }

    List<Long> ids = idPage.getContent();
    List<Order> loaded = repository.findWithDetailsByIdIn(ids);

    Map<Long, Order> byId = loaded.stream()
        .collect(Collectors.toMap(Order::getId, Function.identity()));

    List<OrderResponse> content = ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .map(OrderResponse::from)
        .toList();

    return new PageImpl<>(
        content,
        pageable,
        idPage.getTotalElements()
    );
}
~~~

This two-query pattern bounds root entities before loading collections. For a 20-order page, the second query loads details for only those 20 orders. Watch database bind-parameter limits when page sizes are large, and never pass oversized ID collections.

In the example, `Page<Long>` executes a count query for totals. When totals aren't needed, use `Slice<Long>` or fetch `pageSize + 1` IDs.

### EntityGraph for Required Associations

When only to-one associations such as `customer` are needed, `EntityGraph` can be cleaner:

~~~java
@EntityGraph(attributePaths = {"customer"})
Page<Order> findByStatus(String status, Pageable pageable);
~~~

`EntityGraph` specifies which associations to fetch for the query. It does not guarantee every provider generates a single simple SQL query in all cases; inspect generated SQL. With large collections, test `EntityGraph` carefully alongside pagination.

## 3. Batch Inserts with Hibernate and Spring Data JPA

Batch inserting groups multiple `INSERT` statements into a JDBC batch to cut round trips between application and database. Inserting 1,000 rows one by one causes 1,000 network exchanges. JDBC batching lets the driver ship statements in groups.

Distinguish clearly:

- Spring Data JPA's `saveAll()` saves an iterable of entities; it does not automatically guarantee Hibernate uses JDBC batching.
- Hibernate JDBC batching must be configured, and the identifier generator must support batching.
- The persistence context still retains managed entities until `flush`/`clear` or transaction end.
- The database still executes each row insert/update; batching primarily cuts round-trip overhead and improves throughput.

### Configuring Hibernate Batching

In Spring Boot, configure in `application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.jdbc.batch_versioned_data=true
~~~

Meaning:

| Property | Effect |
|---|---|
| `hibernate.jdbc.batch_size` | Max statements grouped into one JDBC batch |
| `hibernate.order_inserts` | Sorts inserts by entity type and keys to maximize batching |
| `hibernate.order_updates` | Sorts updates for batching and to reduce certain deadlocks |
| `hibernate.jdbc.batch_versioned_data` | Enables batching on versioned entities when driver returns accurate update counts |

`50` is only a starting point for measurement. Optimal batch size depends on row width, column count, driver, network, database, memory, and concurrency. Oversized batches raise memory usage, transaction hold time, and Oracle redo/undo pressure.

You can configure fetch size separately for large reads, but fetch size is not write batch size. The two properties solve different problems.

### Identifier Generation Affects Batching

A major Hibernate limitation is that `IDENTITY` generation generally disables JDBC insert batching for that entity, because Hibernate must execute each `INSERT` immediately to obtain its generated key. On Oracle, sequence generators are usually a better fit when batching is desired.

Example:

~~~java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    @SequenceGenerator(
        name = "order_seq_gen",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_gen"
    )
    private Long id;

    // Other attributes.
}
~~~

`allocationSize` lets Hibernate allocate IDs in blocks via a matching sequence optimizer, cutting sequence calls. Ensure sequence DDL/migrations align with the optimizer and Hibernate version. Never switch `IDENTITY` to `SEQUENCE` on a live system without evaluating data, DDL, and compatibility.

### Inserting Many Entities with EntityManager

For large import jobs, call `persist()` and `flush()`/`clear()` in batches:

~~~java
@Service
@RequiredArgsConstructor
public class OrderImportService {
    private static final int BATCH_SIZE = 50;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importOrders(List<Order> orders) {
        for (int i = 0; i < orders.size(); i++) {
            entityManager.persist(orders.get(i));

            if ((i + 1) % BATCH_SIZE == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

`flush()` pushes pending changes from the persistence context to the database. When Hibernate batching is enabled, eligible `INSERT`s are grouped into JDBC batches.

`clear()` evicts all managed entities from the persistence context. This prevents keeping tens of thousands of objects on the heap, while turning persisted entities detached. Never mutate an old entity after `clear()` expecting Hibernate to track it.

Verify cascades, entity graphs, and callbacks before batch-flushing/clearing. If child entities reference detached parent entities, keep IDs or redesign insertion steps.

### saveAll Does Not Equal JDBC Batching

Example:

~~~java
orderRepository.saveAll(orders);
~~~

This is concise for saving a list, though repository implementations may loop calling `save`. Hibernate only emits JDBC batches when batching is enabled and execution conditions allow.

For very large lists, `saveAll()` inside one transaction keeps all entities in the persistence context until the transaction ends. Split into chunks with per-chunk transactions, or use `EntityManager` with periodic `flush()`/`clear()`.

When splitting transactions per chunk, define failure semantics clearly: earlier chunks may have committed when a later chunk fails. If an import must be all-or-nothing, use a staging strategy and validate before publishing data.

## 4. Batch Updates

Two common approaches exist for batch updates:

1. Load entities, mutate properties, and flush so Hibernate emits batched `UPDATE`s.
2. Run bulk JPQL `UPDATE` to update many rows directly in one SQL statement.

Their semantics differ significantly.

### Batch Updating via Entity State

~~~java
@Transactional
public void markOrdersAsArchived(List<Long> orderIds) {
    List<Order> orders = entityManager.createQuery(
        "select o from Order o where o.id in :ids",
        Order.class
    )
    .setParameter("ids", orderIds)
    .getResultList();

    for (Order order : orders) {
        order.setStatus("ARCHIVED");
    }

    entityManager.flush();
}
~~~

Hibernate dirty checking detects mutated entities and emits `UPDATE`s. With `hibernate.jdbc.batch_size` and `hibernate.order_updates=true`, updates can be batched.

This suits cases needing domain logic, validation, lifecycle callbacks, or entity-level optimistic locking. However, it loads entities into the persistence context and consumes memory. For large sets, process in chunks with `flush`/`clear`.

### Bulk JPQL UPDATE

When updating one column by condition, a bulk update can be far more efficient:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Order o
        set o.status = :newStatus
        where o.status = :oldStatus
        """)
    int updateStatus(
        @Param("oldStatus") String oldStatus,
        @Param("newStatus") String newStatus
    );
}
~~~

Service:

~~~java
@Transactional
public int archiveClosedOrders() {
    return orderRepository.updateStatus("CLOSED", "ARCHIVED");
}
~~~

Bulk JPQL translates into a single SQL `UPDATE` affecting matching rows directly. It avoids loading entities into the persistence context, reducing memory and round trips.

However, bulk updates have important consequences:

- They bypass dirty checking on currently managed entities.
- They do not trigger full entity lifecycle callbacks as individual entity updates do.
- They do not apply cascades as entity updates do.
- The persistence context may retain stale entities, so flush before and clear/refresh after.
- Optimistic locking with `@Version` is not applied automatically; include explicit version predicates and version increments when business rules require it.

Never use bulk updates if business logic depends on callbacks, cascades, or per-entity checks without moving that logic to an appropriate mechanism.

### Updating Version During Bulk Updates

If an entity has `@Version`, bulk JPQL updates do not automatically increment versions via dirty checking. Update the version explicitly:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update Order o
    set o.status = :status,
        o.version = o.version + 1
    where o.id = :id
      and o.version = :expectedVersion
    """)
int updateStatusWithVersion(
    @Param("id") Long id,
    @Param("status") String status,
    @Param("expectedVersion") long expectedVersion
);
~~~

If the returned update count is 0, either the entity does not exist or the version changed. Decide how to distinguish both cases if callers need distinct responses.

### JPQL Bulk Update vs. Native SQL

Native SQL can leverage database-specific syntax, at the cost of tight coupling to schema and dialect. Use JPQL bulk updates when expressible in the entity model; use native SQL when database-specific features or benchmarked query tuning genuinely require it.

On Oracle, inspect execution plans, indexes, redo/undo, and affected row counts. A single-statement `UPDATE` beats thousands of separate `UPDATE`s, yet can still generate heavy redo/undo and lock many rows in one transaction.

## 5. Chunking Batches and Managing Transactions

Hibernate batch size, business chunk size, and transaction row count are three separate concepts.

- **JDBC batch size**: statements Hibernate groups into a single `executeBatch`.
- **Chunk size**: entities the application processes before flushing/clearing or moving to the next chunk.
- **Transaction size**: operations committed or rolled back together.

For example, batch size 50 with chunk size 500 produces roughly 10 JDBC batches per chunk. If each chunk commits independently, transaction size is also 500 entities. If you flush/clear every 500 entities inside one giant transaction, transaction size remains the entire import file.

### Chunk Transactions in Spring

A common pattern is a coordinator service driving chunks and a separate bean running each chunk in its own transaction:

~~~java
@Service
@RequiredArgsConstructor
public class ImportCoordinator {
    private final ImportChunkWriter chunkWriter;

    public void importAll(List<OrderInput> inputs) {
        int chunkSize = 500;

        for (int start = 0; start < inputs.size(); start += chunkSize) {
            int end = Math.min(start + chunkSize, inputs.size());
            chunkWriter.writeChunk(inputs.subList(start, end));
        }
    }
}

@Service
@RequiredArgsConstructor
public class ImportChunkWriter {
    private final OrderRepository orderRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeChunk(List<OrderInput> chunk) {
        List<Order> entities = chunk.stream()
            .map(Order::from)
            .toList();

        orderRepository.saveAll(entities);
        orderRepository.flush();
    }
}
~~~

Put the writer in a separate bean so calls pass through the Spring proxy. Calling another `@Transactional` method on the same object via self-invocation bypasses the transaction interceptor.

`REQUIRES_NEW` creates an independent transaction per chunk. If a later chunk fails, earlier committed chunks persist. Use this only when partial imports are acceptable or paired with resume/reconciliation workflows. When all-or-nothing atomicity is mandatory, use a larger transaction or staging workflow while evaluating undo, redo, lock duration, and rollback time.

### Oracle and Large Transactions

In Oracle, huge write transactions generate heavy redo/undo, hold row locks long-term, pressure the buffer cache, and impact concurrent workloads. Oversized transactions also cause lengthy rollbacks and painful recovery if interrupted.

Measure:

- Duration per chunk.
- Rows written and update counts.
- CPU, logical reads, and physical I/O.
- Redo/undo generation and commit time.
- Lock contention and deadlocks.
- Persistence context size and JVM heap.

No single chunk size fits every table. Start moderately, benchmark on production-like data, and tune within system limits.

## 6. What Is N+1?

N+1 is a query pattern where an application runs one query to fetch N root entities and then fires N additional queries to fetch related data for each entity.

Example fetching 50 orders:

~~~java
List<Order> orders = orderRepository.findTop50ByStatus("OPEN");

for (Order order : orders) {
    String customerName = order.getCustomer().getName();
    // Use customerName.
}
~~~

If `Order.customer` is `LAZY` and unfetched, Hibernate may run:

1. One `SELECT` fetching 50 `Order` rows.
2. One `SELECT Customer` per `Order` if each order references a different customer.

Total queries can reach `1 + N`. If each order also has an `items` collection accessed in the loop, another query fires per order.

Illustrative SQL log:

~~~sql
SELECT ... FROM orders WHERE status = 'OPEN';

SELECT ... FROM customers WHERE customer_id = 101;
SELECT ... FROM customers WHERE customer_id = 102;
SELECT ... FROM customers WHERE customer_id = 103;
-- Repeats for each accessed customer.
~~~

N+1 does not always mean literally N extra queries: Hibernate's persistence context cache avoids re-querying entities already loaded, yet query counts still scale with distinct associations.

### Why Is N+1 Dangerous?

- Every query pays a JDBC and network round trip.
- The database must parse/execute many statements or manage many cursors.
- Connections stay checked out longer.
- Latency accumulates even when each individual query is fast.
- Load scales linearly with page size or traversed entities.
- Issues stay hidden on tiny test datasets and erupt in production with hundreds or thousands of rows.

A join query returns slightly wider rows while saving round trips. Still, joining multiple collections simultaneously causes Cartesian products and duplicate rows, so pick fetch strategies matching actual relationships.

## 7. How to Detect N+1

### Enable SQL Logging in Development

In Spring Boot, configure:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Bind-parameter logger names vary across Hibernate versions. Bind logs can expose sensitive data, so never enable them in production without log-protection policies.

Inspect one request and count executed SQL statements. If you see one `SELECT` fetching a list followed by repeated `SELECT`s with `WHERE id = ?`, you likely have N+1.

### Hibernate Statistics

Enable Hibernate statistics in development or test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Hibernate `Statistics` exposes query counts, entity loads, collection fetches, flushes, and related counters via `SessionFactory`:

~~~java
SessionFactory sessionFactory = entityManagerFactory
    .unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

// Invoke the service under measurement.

long queryCount = statistics.getPrepareStatementCount();
long entityFetchCount = statistics.getEntityFetchCount();
long collectionFetchCount = statistics.getCollectionFetchCount();
~~~

`Statistics` aggregates across the `SessionFactory`, not per request by default. Under concurrent tests, isolate or reset carefully; never rely on global stats to measure individual production requests.

### Asserting Query Counts in Tests

Write integration tests verifying query counts do not grow linearly with entity counts. Seed data, clear the persistence context, reset statistics, invoke the service, and assert statement counts.

~~~java
@Test
@Transactional
void loadsOrdersWithoutNPlusOne() {
    entityManager.flush();
    entityManager.clear();

    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    orderService.findOrderSummaries();

    long statements = statistics.getPrepareStatementCount();

    assertThat(statements).isLessThanOrEqualTo(3);
}
~~~

The number `3` is an example threshold representing one main query plus known secondary queries. Tests must reflect actual repository design rather than arbitrary magic numbers when schemas or seed data change.

## 8. Fixing N+1 with JOIN FETCH

For to-one associations or small collections needed immediately, JPQL `JOIN FETCH` loads related data in the same query:

~~~java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    """)
List<Order> findOrdersWithCustomer(
    @Param("status") String status
);
~~~

Hibernate fetches `customer` alongside `order`. Calling `order.getCustomer().getName()` triggers no extra query once fetched.

For collections:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id = :id
    """)
Optional<Order> findOrderWithItems(@Param("id") Long id);
~~~

`distinct` deduplicates root entities in the JPQL result when joining collections. It does not force the SQL result set down to one row per order, as the database still emits one row per order-item combination.

### Limitations of JOIN FETCH

- Fetch-joining multiple collections simultaneously creates Cartesian products, exploding SQL row counts.
- Collection fetch joins do not mix directly with root-entity pagination.
- To-many joins generate duplicate rows and inflate data transfer.
- Overly broad fetch joins load unnecessary columns and objects.
- Never add fetch joins merely to silence N+1 logs if doing so makes the query heavier overall.

For to-one relationships, `JOIN FETCH` carries lower risk than collections. For large collections or pagination, consider two-step queries, batch fetching, or DTO projections.

## 9. Fixing N+1 with EntityGraph

`EntityGraph` specifies which associations to fetch for a query without writing JPQL fetch joins directly.

~~~java
@EntityGraph(attributePaths = {"customer"})
Optional<Order> findWithCustomerById(Long id);
~~~

Or on a query:

~~~java
@EntityGraph(attributePaths = {"customer", "shippingAddress"})
Page<Order> findByStatus(String status, Pageable pageable);
~~~

`EntityGraph` defines a fetch plan for the query. It does not guarantee every provider emits one simple SQL statement in all cases; inspect generated SQL. With large collections, test `EntityGraph` carefully with pagination.

`EntityGraph` is helpful when one repository method needs a custom fetch plan without altering global entity mappings.

## 10. Fixing N+1 with Batch Fetching

Batch fetching does not collapse all relationships into one `JOIN`. Instead, Hibernate groups multiple uninitialized entities or collections into a single `SELECT` with an `IN` clause.

Configure globally:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Or on specific entities/collections:

~~~java
@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
~~~

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
~~~

When the application accesses multiple proxies or collections within the same persistence context, Hibernate loads them in batches, for example:

~~~sql
SELECT ...
FROM customers
WHERE customer_id IN (?, ?, ..., ?);
~~~

With 100 customers and batch size 32, query count drops from roughly 100 down to around 4 batches, depending on caching, access order, and data.

Batch fetching helps when:
- You do not want to join collections into the main query.
- Many entities reference `LAZY` associations.
- Pagination queries must stay simple.
- You want to curb N+1 while still loading lazily on demand.

It does not guarantee a single query and does not replace thoughtful fetch planning. Size batches according to association counts, row width, and bind-parameter limits.

## 11. Fixing N+1 with DTO Projections

When an API needs only a subset of fields, loading entire entities and associations is unnecessary. DTO projections select only required columns:

~~~java
public record OrderSummary(
    Long id,
    LocalDateTime orderDate,
    String status,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

Repository:

~~~java
@Query("""
    select new com.example.orders.OrderSummary(
        o.id,
        o.orderDate,
        o.status,
        c.name,
        o.totalAmount
    )
    from Order o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummary> findSummaries(
    @Param("status") String status,
    Pageable pageable
);
~~~

The query selects only needed columns. Since DTOs carry no lazy associations, response serialization triggers zero additional queries.

Projections fit list/search APIs, reporting screens, result pages spanning multiple related tables, and read-only paths that do not mutate entities.

DTO projections are usually the best default for paginated read-only endpoints. When entities must be updated, load entities in dedicated write use cases.

## 12. FetchType LAZY/EAGER and Open Session in View

JPA provides two standard fetch modes:

- `LAZY`: association loads when accessed, provided the persistence context is still open.
- `EAGER`: association must load immediately per mapping, though the provider may use joins or secondary selects.

Making everything `EAGER` is not a cure for N+1. Entities with multiple `EAGER` relationships trigger unnecessary queries, redundant data transfers, or extra secondary selects. Keep default mappings clean—generally favoring `LAZY` on both to-one and to-many relationships—and define fetch plans per query.

Note that JPA defaults many to-one mappings such as `@ManyToOne` and `@OneToOne` to `EAGER` unless `LAZY` is specified. Declare `LAZY` explicitly:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "CUSTOMER_ID")
private Customer customer;
~~~

Open Session in View (OSIV) keeps the persistence context open for the entire HTTP request, allowing lazy loading during response serialization. This hides N+1 issues because queries fire outside services and repositories.

Disable OSIV to force loading all needed data inside service/transaction boundaries:

~~~properties
spring.jpa.open-in-view=false
~~~

When disabling OSIV, return DTOs or eagerly fetch required associations before the transaction ends. Never rely on JSON serializers to fetch database relationships.

## 13. Combining Pagination and N+1 Control

An order list API showing customer name and item count can use a DTO projection:

~~~java
public record OrderListRow(
    Long id,
    LocalDateTime createdAt,
    String status,
    String customerName,
    Long itemCount
) {}
~~~

~~~java
@Query(
    value = """
        select new com.example.orders.OrderListRow(
            o.id,
            o.createdAt,
            o.status,
            c.name,
            count(i.id)
        )
        from Order o
        join o.customer c
        left join o.items i
        where o.status = :status
        group by o.id, o.createdAt, o.status, c.name
        """,
    countQuery = """
        select count(o)
        from Order o
        where o.status = :status
        """
)
Page<OrderListRow> findOrderRows(
    @Param("status") String status,
    Pageable pageable
);
~~~

The projection returns exact API fields directly, with no lazy getters invoked after the page returns. The count query must match the paginated unit. If filter criteria involve collections, the count query must count distinct root entities using appropriate joins or `EXISTS`.

When full item lists per order must be displayed, evaluate collection sizes. Use the two-step approach: paginate IDs first, then fetch items for that page's IDs. Never fetch-join multiple collections in the main `Page` query.

## 14. Indexes and Execution Plans for Pagination

Pagination performs well only when filter predicates and sort orders are supported by indexes. Example query:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

Consider a composite index matching filter and sort:

~~~sql
CREATE INDEX ix_orders_status_created_id
ON orders(status, created_at DESC, order_id DESC);
~~~

This is illustrative only. Evaluate status selectivity, data skew, distinct value counts, clustering, and write overhead. Indexes speed up reads while adding cost to inserts/updates/deletes and consuming storage.

On Oracle, inspect actual SQL execution plans, checking predicates, sorts, access paths, and estimated vs. actual rows. When using bind variables, test multiple representative bind values. Never decide indexes from JPQL shape alone.

Count queries may need different indexes or remain costly on huge datasets. When UX does not require total page counts, switch to `Slice` or keyset pagination to avoid full counts.

## 15. Sample Spring Boot Configuration

A development configuration can enable SQL logging and statistics for observation:

~~~properties
spring.jpa.open-in-view=false

spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.default_batch_fetch_size=32

spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Never leave all verbose logging enabled by default in production. Bind logging can leak PII, tokens, or business data. Hibernate statistics add overhead and accumulate globally; restrict them to appropriate environments.

Exact property names and behaviors may vary across Hibernate versions bundled with Spring Boot. Check your project's resolved dependencies before relying on version-specific properties or APIs.

## 16. Investigation and Optimization Workflow

When an endpoint slows down or an import job drags on, measure before changing anything.

1. **Reproduce with realistic data volume.** Test with production-like row counts and distributions; tiny datasets mask N+1 and deep-offset slowdowns.
2. **Capture SQL counts.** Enable SQL logs or statistics in test environments to inspect statement counts and repeated queries.
3. **Classify the bottleneck.** Determine whether time goes to count queries, page queries, lazy loading, inserts/updates, flushes, or commits.
4. **Pick the right strategy.** `Page`/`Slice`/keyset for reads; JDBC batching and chunking for writes; fetch joins, `EntityGraph`, batch fetching, or projections for associations.
5. **Audit the persistence context.** Check if entities stay managed too long, `clear()` runs at the right intervals, or bulk updates leave stale state.
6. **Inspect SQL and indexes.** Review execution plans, row counts, sorts, joins, indexes, and bind values.
7. **Re-measure under identical conditions.** Compare query counts, elapsed time, CPU, memory, I/O, and business correctness.
8. **Test concurrency and failures.** Verify optimistic locking, rollbacks, retries, duplicate requests, and concurrent mutations during pagination.

A change is only worthwhile if it improves target metrics while preserving correctness and transaction semantics.

## 17. Common Mistakes

- **Using `Page` for every API.** `Page` often triggers costly count queries; use `Slice` or keyset when totals aren't needed.
- **Missing deterministic sorting.** Rows with identical sort keys can shift across pages; add a unique tie-breaker.
- **Combining collection fetch joins with pagination.** Causes row multiplication or in-memory pagination; use two-step queries or projections.
- **Assuming `saveAll` batches automatically.** You must enable Hibernate batching and verify ID strategies, flushing, and actual SQL.
- **Using `IDENTITY` while expecting insert batching.** Hibernate usually inserts row by row to fetch generated keys; consider Oracle sequences where appropriate.
- **Enabling `batch_size` without `flush`/`clear`.** The persistence context still retains all entities and swells heap usage.
- **Calling `clear` too early.** Entities become detached and subsequent mutations miss dirty checking.
- **Running bulk JPQL and forgetting the persistence context.** Managed entities stay stale; flush/clear/refresh appropriately.
- **Assuming bulk updates handle `@Version` and callbacks.** Bulk DML bypasses entity lifecycle hooks; handle versions and side effects explicitly.
- **Setting `EAGER` to avoid lazy exceptions.** `EAGER` over-fetches data and still generates extra queries.
- **Checking query counts only on tiny test data.** N+1 only stands out with sufficient entity counts.
- **Raising batch size without bounds.** Huge batches inflate memory, lock durations, redo/undo, and rollback times.

## 18. Technique Selection Checklist

| Scenario | Approach to Consider |
|---|---|
| List page needing total row count | `Page` with tailored `countQuery` |
| Infinite scroll without total count | `Slice` |
| Very large dataset, forward-only | Keyset/seek pagination |
| List API needing only selected columns | DTO projection |
| Loading to-one association | `JOIN FETCH` or `EntityGraph` |
| Loading collection for a single entity | Bounded `JOIN FETCH` |
| Loading collections for a page of entities | Two queries: paginate IDs, then fetch details |
| Many `LAZY` proxies/collections accessed | Hibernate batch fetching |
| Inserting thousands of entities | JDBC batching, suitable sequence, chunked `flush`/`clear` |
| Updating by shared predicate | Bulk JPQL/native `UPDATE` |
| Updating needing callbacks/domain logic/versions | Load entities and dirty-check in batches |
| Import allowing partial commits | Chunked transactions with resume handling |
| Import requiring full atomicity | Staging or bounded transaction per business rules |

## 19. Operational Principles

- Cap API page sizes and enforce deterministic sort ordering.
- Choose `Page` when total counts are needed; use `Slice` or keyset otherwise.
- Verify count queries separately, especially with joins and `DISTINCT`.
- Never paginate directly over collection fetch joins; use projections or two-step queries.
- Enable Hibernate JDBC batching and measure batch sizes; `saveAll` alone does not guarantee batching.
- On Oracle, consider sequence generation when JDBC insert batching is needed.
- `flush`/`clear` in chunks to bound the persistence context, remembering `clear` detaches all entities.
- Use bulk JPQL for simple mass updates while handling stale persistence contexts and `@Version` explicitly.
- Catch N+1 using SQL logs, Hibernate statistics, and integration tests with realistic data volumes.
- Choose fetch joins, `EntityGraph`, batch fetching, or DTO projections based on association cardinality and endpoint purpose.
- Disable OSIV to enforce fetch plans inside service transactions and return fully populated DTOs.
- Measure query counts, elapsed time, memory, CPU, I/O, and transaction durations before and after tuning.

Pagination, batch writes, and N+1 control are three facets of the same data-access design problem. Selecting the right pagination model, bounding batch writes, and defining explicit fetch plans per use case reduce round trips, stabilize memory, and keep Spring Boot/JPA applications fast as data scales.
