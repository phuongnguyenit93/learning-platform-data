# EntityManager and Persistence Context

In Spring Batch, when reading or writing data with JPA, `EntityManager` is the API for working with entities while the persistence context is the scope managing tracked entities. The persistence context maintains entity identity, detects changes to write to the database, coordinates entity state, and applies `persist`, `merge`, `remove`, `flush`, or `clear` operations.

Understanding the lifecycle of `EntityManager` and the persistence context is critical in batch processing. A Step typically processes thousands or millions of items chunk by chunk. If the persistence context retains too many entities, memory usage can grow continuously. If the context is cleared too early, entities become detached and lazy associations may no longer be accessible. If `merge` is misused or `flush` is mistaken for `commit`, data can behave unexpectedly.

In JPA processing, you need to understand:

- How `EntityManager` and the persistence context differ.
- How entities transition through new, managed, detached, and removed states.
- How dirty checking and the first-level cache work.
- How chunk transactions relate to the persistence context.
- When to use `persist`, `merge`, `flush`, `clear`, `detach`, and `refresh`.
- How Spring Batch JPA readers/writers manage `EntityManager`.
- How to control memory, lazy loading, batching, restart, and concurrency.

## 1. EntityManager and persistence context

`EntityManager` is the primary interface of Jakarta Persistence (JPA). It provides operations to create, find, track, update, and remove entities.

The persistence context is the set of entity instances managed by an `EntityManager`. Within a persistence context, a given entity identity (entity type and primary key) is represented by a corresponding managed object. JPA uses this context to track changes and synchronize data with the database.

You can visualize it as:

~~~text
Application / Spring Batch component
             |
             v
        EntityManager
             |
             v
      Persistence Context
       /       |       \
      v        v        v
   Order    Customer  OrderLine
      \        |        /
       \       |       /
        v      v      v
          Database
~~~

`EntityManager` provides the API; the persistence context is the state space that API manages. Multiple `EntityManager` instances can be created from the same `EntityManagerFactory`, but each `EntityManager` has its own persistence context.

### EntityManagerFactory and EntityManager

These two objects have different lifecycles:

| Component | Role | Typical lifecycle |
| --- | --- | --- |
| EntityManagerFactory | Creates `EntityManager` instances and manages persistence unit configuration | Usually lives for the entire application lifecycle |
| EntityManager | Interacts with entities and the persistence context | Usually bound to a transaction or unit of work |
| Persistence context | Tracks managed entities and their changes | Usually exists alongside the `EntityManager`/transaction-scoped context |

`EntityManagerFactory` is designed to be shared across threads. An individual `EntityManager` is not thread-safe and must not be used concurrently by multiple threads.

In Spring, applications typically inject `EntityManager` via `@PersistenceContext` or a shared `EntityManager` proxy. This proxy looks up the `EntityManager` bound to the current transaction. You should not manually create a singleton `EntityManager` and share it across multiple workers.

## 2. Persistence context as a first-level cache

The persistence context acts as JPA's first-level cache. If an entity has already been loaded into the context, querying the same identity again within that context usually returns the same managed instance rather than creating a separate Java object.

Example:

~~~java
Order first = entityManager.find(Order.class, 1001L);
Order second = entityManager.find(Order.class, 1001L);

assert first == second;
~~~

Within the same persistence context, both variables typically reference the exact same object instance for the same entity identity.

Benefits:

- Avoids multiple objects representing the same entity within a single context.
- Reduces redundant database queries when the entity is already managed.
- Enables dirty checking because JPA knows which entities are being tracked.
- Maintains consistency among associations within the context.

The first-level cache is not an application-wide shared cache. When the `EntityManager` closes or the persistence context is cleared, entities are no longer managed in that context.

### Same identity does not guarantee latest data

If an entity has been loaded and another transaction updates the database, the currently managed entity may still hold the previously read state. The persistence context does not automatically refresh every entity whenever the database changes.

When you need to re-read current data, you can use `refresh()` or clear the context and reload. Be cautious because `refresh` can overwrite unflushed changes on the object.

## 3. Four entity lifecycle states

A JPA entity is typically in one of four states:

| State | Meaning | Tracked by persistence context? |
| --- | --- | --- |
| New / transient | Newly created object, not yet persisted | No |
| Managed / persistent | Entity currently managed by the context | Yes |
| Detached | Entity that was previously managed but is no longer managed by the context | No |
| Removed | Entity marked for deletion in the context | Yes until removal is synchronized/committed |

Lifecycle example:

~~~text
new Order()
    |
    | persist()
    v
Managed entity
    |
    | clear(), detach(), or close()
    v
Detached entity
    |
    | merge()
    v
A managed instance is returned
~~~

An entity can transition to removed when `remove()` is called on a managed instance. When the transaction commits, the corresponding `DELETE` statement is executed unless rolled back.

### New entity

~~~java
Order order = new Order();
order.setOrderId(1001L);
order.setStatus(OrderStatus.NEW);
~~~

A new object is not tracked by `EntityManager`. Modifying fields on the object does not generate SQL automatically.

### Managed entity

~~~java
Order order = entityManager.find(Order.class, 1001L);
order.setStatus(OrderStatus.PROCESSED);
~~~

An entity found in the current context is managed. JPA can detect changes and generate an `UPDATE` on flush.

### Detached entity

~~~java
entityManager.clear();
order.setStatus(OrderStatus.PROCESSED);
~~~

After `clear()`, previously managed entities become detached. Subsequent modifications on the object are not tracked by the old persistence context.

### Removed entity

~~~java
Order order = entityManager.find(Order.class, 1001L);
entityManager.remove(order);
~~~

The entity is marked removed. The SQL `DELETE` is typically synchronized at flush or commit.

## 4. persist() and merge()

These two operations are frequently confused.

### persist() for new entities

`persist()` places a new entity into the persistence context:

~~~java
Order order = new Order();
order.setOrderId(1001L);
order.setStatus(OrderStatus.NEW);

entityManager.persist(order);
~~~

After the call, the `order` object becomes managed in the current context. The `INSERT` may be sent immediately or deferred until flush/commit depending on the ID strategy and provider.

Do not use `persist()` as a way to update a detached entity. Doing so can lead to detached entity exceptions or unique key violations.

### merge() for detached entities or state synchronization

`merge()` copies the state of the passed object into a managed instance:

~~~java
Order detachedOrder = loadOrderFromPreviousStep();

Order managedOrder = entityManager.merge(detachedOrder);
managedOrder.setStatus(OrderStatus.PROCESSED);
~~~

A crucial detail: `merge()` returns the managed instance. The passed-in object itself does not become managed. Therefore, if you need to keep modifying the entity after merging, use the returned object.

Avoid writing:

~~~java
entityManager.merge(detachedOrder);
detachedOrder.setStatus(OrderStatus.PROCESSED);
~~~

Changes on `detachedOrder` after `merge` are not guaranteed to be tracked by the persistence context.

### When to choose persist vs. merge?

| Scenario | Usually appropriate operation |
| --- | --- |
| Creating a new entity | `persist()` |
| Updating a currently managed entity | Mutate directly; dirty checking will detect it |
| Synchronizing state from a detached entity | `merge()` and use the returned object |
| Deleting a managed entity | `remove()` |
| Deleting a detached entity | Load the managed entity or merge then remove according to appropriate rules |

Do not call `merge` mechanically on every entity. `merge` may have to load state and copy association graphs, issuing extra queries and adding overhead.

## 5. Dirty checking

Dirty checking is the JPA mechanism that compares a managed entity's current state against its initial snapshot to detect changes that need to be written.

Example:

~~~java
@Transactional
public void markProcessed(long orderId) {
    Order order = entityManager.find(Order.class, orderId);
    order.setStatus(OrderStatus.PROCESSED);
}
~~~

There is no need to call `save()` or `update()` after modifying a managed entity. When the transaction flushes, JPA detects the modified field and generates an `UPDATE` statement.

General flow:

~~~text
find(Order.class, id)
       |
       v
Managed entity + snapshot
       |
       v
Java code changes status
       |
       v
Dirty checking detects difference
       |
       v
flush()
       |
       v
SQL UPDATE
~~~

Dirty checking applies only to entities that remain managed. If an entity is detached, changes on the object are not automatically persisted.

### Dirty checking and batching

Within a chunk holding many entities, the persistence context may retain snapshots of every loaded or persisted entity. As the count grows, memory usage and dirty-checking overhead increase.

Therefore, batch jobs typically need to bound the number of simultaneously managed entities through appropriate chunk sizes, page sizes, and flush/clear strategies.

## 6. flush() is not commit()

`flush()` synchronizes pending changes in the persistence context to the database using SQL. It does not end the transaction.

~~~java
order.setStatus(OrderStatus.PROCESSED);
entityManager.flush();

// SQL UPDATE has been sent within the transaction,
// but the transaction can still roll back.
~~~

Only a transaction `commit` makes changes durable according to database transaction semantics. If the transaction rolls back after a flush, statements already executed within that transaction can still be rolled back.

| Operation | Meaning |
| --- | --- |
| `flush()` | Synchronizes pending changes into SQL within the current transaction |
| `commit()` | Completes the transaction |
| `clear()` | Detaches all entities from the persistence context |
| `close()` | Closes the `EntityManager` and persistence context |

Flushing can surface constraint violations, optimistic locking exceptions, or SQL errors earlier than commit time. This is why checking errors at flush time helps identify the exact chunk causing a failure.

Do not call `commit()` directly on a Spring-managed `EntityManager`. Spring Batch's transaction manager must control commit and rollback at chunk boundaries.

## 7. clear(), detach(), and refresh()

These APIs affect entity state in different ways.

### clear()

`clear()` detaches all entities in the persistence context:

~~~java
entityManager.flush();
entityManager.clear();
~~~

Commonly used after flushing in batch jobs to release references and reduce memory consumption. After `clear()`, previously tracked entities are no longer managed.

### detach()

`detach(entity)` detaches only a single entity:

~~~java
entityManager.detach(order);
~~~

Other entities remain managed. Useful when you want to stop tracking a specific object, though pay attention to cascade detach if configured in the mapping.

### refresh()

`refresh(entity)` reloads state from the database and overwrites unsynchronized changes on the managed entity:

~~~java
entityManager.refresh(order);
~~~

Use `refresh` only when you want to discard in-memory state and fetch the current database state. Do not call it carelessly after modifying an entity, as unflushed changes may be lost.

### flush before clear

In batch processing, the typical order is:

~~~java
entityManager.flush();
entityManager.clear();
~~~

If you clear before flushing, pending changes may be dropped from the persistence context and never written. Do not use `clear` as a substitute for committing; the transaction remains active.

## 8. Transaction-scoped persistence context

In typical Spring applications, the persistence context is bound to the transaction. `JpaTransactionManager` manages transactions for an `EntityManagerFactory` and binds the corresponding `EntityManager` to the current thread.

When Spring Batch runs a chunk Step with a JPA transaction manager:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Each chunk runs in a transaction as configured on the Step. JPA operations participate in that transaction when they use the matching `EntityManagerFactory` and transaction manager.

With a transaction-scoped persistence context, the `EntityManager`/persistence context bound to the transaction opens and ends with the transaction lifecycle. Because chunks commit after every group of items, do not assume a single persistence context will retain every entity from the start to the end of the Job.

### Extended persistence context

JPA also defines an extended persistence context, which outlives a single transaction. This mode is usually unnecessary for Spring Batch chunk processing and can retain too many entities in memory if stretched across multiple chunks.

For batch processing, a transaction-scoped context combined with controlled flush/clear operations is much easier to manage. Do not hold a single shared extended `EntityManager` across an entire Job without a clear architectural reason.

## 9. EntityManager in Spring with @PersistenceContext

You can inject `EntityManager` into repositories or custom writers:

~~~java
@Component
public class OrderJpaWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            entityManager.merge(order);
        }
        entityManager.flush();
    }
}
~~~

In Spring, the injected `EntityManager` is normally a shared proxy. The proxy looks up the `EntityManager` bound to the current transaction. This allows singleton components to use the `EntityManager` API without sharing a single physical `EntityManager` across all threads.

Do not create an `EntityManager` manually inside every method and forget to close it. If you actually create one via `EntityManagerFactory`, your code becomes responsible for proper open/close and transaction management.

### Do not share a physical EntityManager across workers

`EntityManager` is not thread-safe. Do not store a manually created `EntityManager` in a static field or singleton and have multiple workers invoke it concurrently.

If a Step is multi-threaded or partitioned:

- Each transaction/worker needs an `EntityManager` tied to its own thread and transaction.
- Use Spring's shared `EntityManager` proxy or properly configured repositories.
- Do not pass a physical `EntityManager` across threads.
- Do not retain managed entities and access them concurrently across multiple workers.

## 10. JpaPagingItemReader and the persistence context

Spring Batch provides `JpaPagingItemReader` to read JPA data page by page. The reader accepts an `EntityManagerFactory` and a JPQL query:

~~~java
@Bean
@StepScope
public JpaPagingItemReader<Order> orderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from Order o
                    where o.status = :status
                    order by o.id
                    """)
            .parameterValues(Map.of(
                    "status", OrderStatus.READY))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

The reader fetches pages of results up to `pageSize` items each. Paged reading avoids holding the entire result set in one large collection.

### Returned entities may be detached

`JpaPagingItemReader` manages its own `EntityManager` with a separate lifecycle. The reader executes the page query and clears the persistence context after reading the page according to its implementation behavior. Therefore, entities passed to the processor are typically detached.

Consequences:

- The processor can read already-loaded fields.
- Mutating a detached entity is not automatically dirty-checked by the reader's persistence context.
- Lazy associations may no longer be accessible after the context is cleared.
- If updates need to be persisted, the writer must merge the entity or reload a managed entity inside the write transaction.

Do not assume an entity returned by the reader remains managed in the `EntityManager` used by the writer. Reader and writer may manage separate `EntityManager` instances.

### Reader transaction vs. chunk transaction

`JpaPagingItemReader` can execute page queries in its own transaction by design; that transaction is not necessarily the chunk's write transaction. Exact behavior depends on the Spring Batch version and reader configuration.

Consequently, do not infer from a successful read that the reader and writer share the same persistence context. If business logic requires reading and updating within a specific persistence context or transaction, design and test it explicitly rather than relying on reader defaults.

### Stable sort keys

Paging requires deterministic ordering:

~~~sql
order by o.id
~~~

The sort key should be unique, or the composite sort keys must define a total order. If the query lacks stable ordering, pages may duplicate or skip items when data changes.

If the writer updates a column used in the paging query's filter condition, the result set can shift between pages. Consider a batch ID, watermark, or staging table to stabilize the input set.

## 11. JpaItemWriter and detached entities

`JpaItemWriter` is the standard writer for persisting or updating entities via JPA:

~~~java
@Bean
public JpaItemWriter<Order> orderWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
~~~

The writer uses the transaction-bound `EntityManager` if present, then persists or merges items based on configuration. The default in many versions is `merge`; the builder provides `usePersist` to choose `persist` when writing new entities.

Because `JpaPagingItemReader` typically returns detached entities, `merge` is a common choice when updating read entities. For brand-new entities, `persist` is usually more appropriate. Check the configuration and API of the Spring Batch version you use.

### merge returns a managed entity

When writing a custom writer:

~~~java
for (Order detachedOrder : chunk) {
    Order managedOrder = entityManager.merge(detachedOrder);
    managedOrder.setStatus(OrderStatus.PROCESSED);
}

entityManager.flush();
~~~

Continue using `managedOrder` after `merge`. Do not assume `detachedOrder` itself becomes attached.

### persist for new entities

~~~java
for (Order newOrder : chunk) {
    entityManager.persist(newOrder);
}

entityManager.flush();
~~~

Do not use `persist` for detached entities solely to avoid merge overhead. If the ID already exists, you may encounter duplicate key errors or detached entity exceptions.

## 12. JpaItemWriter and clearing the persistence context

`JpaItemWriter` has options to manage clearing the persistence context after writing; in modern Spring Batch versions, the writer typically flushes and may clear the context after writing depending on its default implementation settings.

Benefits of clearing after write:

- Avoids keeping all entities from previous chunks in the context.
- Reduces memory usage for Jobs processing many items.
- Limits dirty checking on entities that are no longer needed.

However, clearing also detaches every entity currently managed in that context. If custom code relies on entities remaining managed after the writer runs, verify this behavior.

Do not assume `JpaItemWriter` clears only the items it just wrote. `EntityManager.clear()` affects the entire persistence context. Consult the documentation for your Spring Batch version and avoid holding managed entities that require further manipulation after writing.

## 13. Flushing and clearing by batch size

In a custom writer, you can proactively flush and clear after a certain number of items:

~~~java
public class ChunkedJpaWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    private final int flushInterval = 50;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        int count = 0;

        for (Order order : chunk) {
            entityManager.persist(order);
            count++;

            if (count % flushInterval == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

This illustrates a writer creating new entities. If an entity is needed after `clear`, keep the required data in a DTO or reload the entity later.

Grouped flushing pushes SQL to the database earlier and controls the number of managed entities. Clearing frees entities from the persistence context. Both still occur inside the chunk transaction if invoked within it.

If a second flush fails, all uncommitted SQL in the chunk can still roll back. Mid-chunk flushes do not create mid-chunk commits.

### Do not flush/clear arbitrarily mid-relationship

If parent and child entities are persisted via cascading, ensure the object graph is properly linked before flushing. Clearing mid-construction or before cascade operations finish can detach entities and produce obscure errors.

In custom writers, separate steps clearly:

1. Build the entity graph.
2. Persist/merge the graph.
3. Flush.
4. Clear once managed entities are no longer needed.

## 14. Persistence context and JDBC batching

JPA providers such as Hibernate can group multiple `INSERT`/`UPDATE` statements into JDBC batches when properly configured. However, enabling JDBC batching does not automatically guarantee every statement is batched.

Common Hibernate properties:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Meaning:

- `hibernate.jdbc.batch_size`: number of JDBC statements that can be grouped in a batch.
- `hibernate.order_inserts`: orders inserts to increase the chance of grouping identical statement types.
- `hibernate.order_updates`: orders updates to aid batching and potentially reduce deadlocks in some scenarios.

These properties must be placed in the application's JPA/Hibernate configuration. Exact property names and wiring may depend on Spring Boot, Hibernate, and persistence provider versions.

### Generation strategy affects batching

With Hibernate, `IDENTITY` ID generation often restricts batch `INSERT`s because the provider must execute inserts immediately to retrieve generated keys. Sequence-based ID generation is generally friendlier to batching, depending on the database and configuration.

Do not change ID strategies purely for speed without evaluating schema and business requirements.

### Chunk size, page size, and batch size

These three parameters control different things:

| Parameter | Controls |
| --- | --- |
| Chunk size | Number of items in a single Step transaction |
| Page size | Number of entities the reader fetches in one page |
| JDBC batch size | Number of SQL statements the provider groups in one JDBC batch |

Example with chunk size 100, page size 500, JDBC batch size 50:

- The reader may load a page of 500 items.
- The Step commits after every 100 items.
- The provider may dispatch SQL in batches of up to 50 eligible statements.

All values should be measured on a real database. Large page sizes can raise memory usage; large chunk sizes can lengthen transactions and hold locks; overly large JDBC batch sizes can increase driver-side memory.

## 15. Lazy loading and detached entities

JPA can defer loading associations using `FetchType.LAZY`. Example:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

If an entity becomes detached before the association is loaded, accessing it can throw `LazyInitializationException` in Hibernate or an equivalent provider error.

Risky example:

~~~java
Order order = orderReader.read(); // entity may be detached
String customerName = order.getCustomer().getName();
~~~

If `customer` was not loaded before the reader cleared the context, the processor may fail to access it.

### How to handle it

- Use JPQL `join fetch` for associations needed in the batch job.
- Use an `EntityGraph` to declare the fetch plan.
- Use a projection/DTO containing only the fields needed for processing.
- Separate loading related info into an appropriate transactional step.
- Avoid relying on Open EntityManager in View; batch jobs do not have a web request lifecycle to rely on.

Fetch join example:

~~~java
.queryString("""
        select o
        from Order o
        join fetch o.customer
        where o.status = :status
        order by o.id
        """)
~~~

Fetch-joining collections can multiply result rows and cause paging issues. When paging, be careful with one-to-many collections; projections or two-step queries may be more suitable.

Do not switch every association to `EAGER` merely to avoid lazy loading errors. Broad `EAGER` fetching can bloat queries and cause N+1 queries or excess data retrieval.

## 16. N+1 queries in batch jobs

N+1 occurs when the reader loads N primary entities and the processor accesses an association, causing each entity to trigger an extra query.

Example:

~~~text
1 query fetches 500 Orders
500 queries fetch Customer for each Order
-----------------------------------
501 queries
~~~

This is a major cost in batch jobs.

Remediation:

- Fetch-join required associations.
- Use `EntityGraph`.
- Use provider batch fetching where suitable.
- Use DTO projections to select only needed fields.
- Measure actual query counts with SQL logs or datasource metrics.

Do not simply increase page size to fix N+1. Larger pages can trigger even more secondary queries and increase memory usage.

## 17. JPQL bulk updates and the persistence context

JPQL bulk updates/deletes execute directly against the database and bypass per-entity dirty checking:

~~~java
int updated = entityManager.createQuery("""
        update Order o
        set o.status = :newStatus
        where o.status = :oldStatus
        """)
        .setParameter("newStatus", OrderStatus.PROCESSED)
        .setParameter("oldStatus", OrderStatus.READY)
        .executeUpdate();
~~~

Bulk updates can be faster for large volumes, but the current persistence context does not automatically synchronize the state of previously loaded entities.

For instance, a managed `Order` has status `READY`. The bulk query updates the database to `PROCESSED`, yet the in-memory object may still show `READY`. At flush, stale in-memory state might cause overwrites depending on mapping and provider.

A common strategy:

~~~java
entityManager.flush();

int updated = query.executeUpdate();

entityManager.clear();
~~~

Flush managed changes before the bulk operation, execute the bulk SQL, then clear to avoid retaining stale entities. If you only need to refresh a specific entity, you can use `refresh` after the bulk operation.

Bulk operations do not invoke per-entity lifecycle callbacks and may bypass standard optimistic locking/version handling. If business logic requires per-entity version checks or audit callbacks, use an entity-level update approach instead.

## 18. Optimistic locking and @Version

When multiple Jobs or transactions may update the same entity, use optimistic locking to detect conflicts:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @Version
    private long version;

    private OrderStatus status;
}
~~~

When an entity is updated, JPA checks the current version. If another transaction modified the version earlier, the update can fail with an optimistic locking exception.

In batch processing:

- Exceptions may surface at flush or commit time.
- You can retry if conflicts are transient and the operation is safe to re-execute.
- Do not skip every optimistic lock exception if skipping loses business updates.
- You may need to re-read the entity and recompute rather than merging stale state.

Calling `merge()` on a detached entity with an old version does not guarantee a successful update. Version checking can still detect stale state.

## 19. Persistence context and cascade

Entity relationships can declare cascades:

~~~java
@OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

Cascading determines whether `EntityManager` operations propagate to associations:

- `PERSIST`: persisting parent can persist children.
- `MERGE`: merging parent can merge children.
- `REMOVE`: removing parent can remove children.
- `REFRESH`: refreshing parent can refresh children.
- `DETACH`: detaching parent can detach children.
- `ALL`: applies all of the above operations.

Do not enable `CascadeType.ALL` out of habit. If a parent entity references a shared entity such as `Customer`, cascading `REMOVE` can delete data that should not be removed.

In batch jobs, large entity graphs and deep cascades can generate excessive SQL and raise memory consumption. Only cascade relationships that truly belong to the aggregate lifecycle.

### orphanRemoval

With `orphanRemoval`, removing a child from the collection can cause the child to be deleted on flush:

~~~java
order.getLines().remove(line);
~~~

Tests must verify this deletion behavior matches business rules. Do not clear a collection just to save memory if the collection is managed and `orphanRemoval` could delete child records.

## 20. Transaction propagation and EntityManager

Services called from processors/writers may declare `@Transactional`. Propagation determines whether the service joins the chunk transaction or opens a different transaction.

| Propagation | Typical impact |
| --- | --- |
| `REQUIRED` | Joins the current transaction if one exists |
| `REQUIRES_NEW` | Suspends the current transaction and opens a new one |
| `SUPPORTS` | Joins if a transaction exists; otherwise runs without one |
| `NOT_SUPPORTED` | Suspends the current transaction |

If you want entity changes to roll back with the chunk, services normally use `REQUIRED` with the same transaction manager.

If `REQUIRES_NEW` is used, the service can commit independently. When the writer later fails and the chunk rolls back, changes committed in the inner transaction will not automatically roll back with the chunk.

Calling a transactional method through a Spring proxy is required for the transaction interceptor to engage. Self-invocation within the same bean may not pass through the proxy as expected.

Do not call `EntityTransaction.begin()` or `commit()` on a Spring-managed `EntityManager`. Let `JpaTransactionManager` and Spring Batch control transactions.

## 21. Avoid keeping entities managed across multiple chunks

A Job may run for hours. If a single persistence context keeps every entity read or written since the Job started, memory will steadily grow.

Symptoms:

- Heap usage grows linearly with item count.
- Dirty checking becomes increasingly expensive.
- Flushes emit more SQL than expected.
- Garbage collection runs frequently.
- The Job slows down over time.

Solutions:

- Use a transaction-scoped persistence context.
- Bound chunk and page sizes.
- Flush and clear after appropriate groups of entities.
- Use `JpaItemWriter` with an appropriate clear policy.
- Do not store managed entities in static collections or singletons.
- Store DTOs or IDs in `ExecutionContext` instead of entity graphs.

Do not clear the context while unflushed pending changes remain. Do not hold detached association proxies and access them in a later Step.

## 22. EntityManager and Spring Batch restarts

The persistence context is not a Spring Batch checkpoint. `EntityManager` and managed entities are not serialized into `ExecutionContext` to resume a Job.

Restarts rely on:

- `JobInstance` and `JobParameters`.
- `StepExecution`/`ExecutionContext`.
- `ItemStream` reader/writer state.
- Committed data in the database.

Once a chunk commits, the transaction ends. A transaction-scoped `EntityManager`/persistence context is not reused as continuation state for the next chunk. On restart, the reader reopens and fetches data from the database or checkpoint position.

### Do not store entities in ExecutionContext

Never store managed entities directly in `ExecutionContext`. Instead, store identifiers or positions:

~~~java
executionContext.putLong("lastOrderId", 1001L);
~~~

After restart, reload the entity by ID or let the reader restore from its checkpoint. This avoids storing large object graphs, non-serializable proxies, and stale state.

### Idempotent writers

If a chunk rolls back and retries, the writer may receive the same items again. Use unique business keys, versions, or controlled upserts to avoid creating duplicate records. Do not rely on the persistence context to prevent duplicates across transactions; the first-level cache exists only within the current context.

## 23. Reading and writing the same entity in one Step

A common scenario is the reader selecting `READY` orders, the processor computing values, and the writer updating their status to `PROCESSED`.

If the reader uses `JpaPagingItemReader`, entities may be detached after the page is read. The writer uses `JpaItemWriter`/merge or loads a managed entity in the write transaction.

However, if the writer alters the `status` column that the query filters on, the `READY` dataset can change while the reader is paging. With offset-based paging, subsequent pages can skip items as the result set shrinks.

Example:

~~~text
First page fetches READY: 1, 2, 3, 4, 5
Writer changes status of 1-5 to PROCESSED

Remaining READY set: 6, 7, 8, 9, 10
If the next page uses offset 5 on the modified set,
items 6-10 may be skipped.
~~~

Solutions:

- Use a batch ID or staging table to fix the item set.
- Use a stable cutoff or watermark.
- Paginate by an immutable key with an appropriately designed query.
- Separate the input-claiming step from the processing step.
- Avoid altering predicates or sort keys used for paging unless the impact is controlled.

The persistence context does not solve the problem of a changing result set between pages. This is a query, transaction, and input-partitioning design problem.

## 24. EntityManager in multi-threaded Steps and partitioning

`EntityManager` is not thread-safe. Never share a single physical `EntityManager` across multiple threads.

In a multi-threaded Step:

- Transactions may differ between threads.
- Each thread needs a persistence context bound to its own transaction.
- Do not share managed entities across thread boundaries.
- Do not share mutable entity collections across workers.
- Readers and writers must be thread-safe or use appropriate synchronization.

In partitioning:

- Each partition normally has its own `StepExecution`.
- Use `@StepScope` for components depending on partition parameters.
- The `EntityManager` proxy will work with the worker's current transaction if configured properly.
- Each worker should process non-overlapping ID ranges or use claiming/locking.

Do not pass an `EntityManager` into an `Executor` task and use it after the caller's transaction ends. For parallel processing, each worker must have its own Spring-managed transaction and `EntityManager`.

## 25. Testing persistence context behavior independently

Use JPA integration tests to verify entity lifecycle and dirty checking. Example with a transactional test:

~~~java
@DataJpaTest
class OrderPersistenceContextTest {

    @Autowired
    private EntityManager entityManager;

    @Test
    void dirtyCheckingUpdatesManagedEntity() {
        Order order = new Order();
        order.setId(1001L);
        order.setStatus(OrderStatus.READY);
        entityManager.persist(order);
        entityManager.flush();

        order.setStatus(OrderStatus.PROCESSED);
        entityManager.flush();
        entityManager.clear();

        Order reloaded = entityManager.find(Order.class, 1001L);
        assertEquals(OrderStatus.PROCESSED, reloaded.getStatus());
    }
}
~~~

This test verifies dirty checking and confirms that clearing forces the entity to be reloaded from the database. Fixture and ID setup must match the actual entity definition.

### Testing that merge returns a managed instance

~~~java
Order detached = new Order();
detached.setId(1001L);
detached.setStatus(OrderStatus.PROCESSED);

Order managed = entityManager.merge(detached);

assertNotSame(detached, managed);
assertTrue(entityManager.contains(managed));
assertFalse(entityManager.contains(detached));
~~~

Exact identity behavior can depend on whether the entity is already managed. Tests should create a genuine detached scenario by persisting, flushing, and clearing before calling `merge`.

### Testing that flush is not commit

An integration test needs explicit transaction boundaries:

1. Persist an entity and flush.
2. Throw an exception to force transaction rollback.
3. Open a new transaction and verify the entity does not exist.

Do not rely on a test method that rolls back by default at the end of the test to conclude that `flush` committed data. `flush` only sends SQL within the transaction.

## 26. Testing JpaPagingItemReader and JpaItemWriter

Beyond entity unit tests, verify how Spring Batch readers and writers interact with the persistence context:

- The reader returns expected items in the right order.
- Reader page boundaries neither skip nor duplicate items.
- Returned entities are in the expected detached state.
- Required lazy associations are already fetched.
- The writer merges detached entities properly.
- The writer persists new entities properly.
- Flush errors roll back the chunk.
- Clear policies do not discard unflushed changes.
- Restart resumes from the correct position without duplicate writes.

You can use Spring Batch Test to run the actual Step against a test database. When testing restart, run a `JobInstance`, make the Step fail in a controlled way, and relaunch with the same identifying `JobParameters`.

Do not assert `BatchStatus` alone. Query the database and verify record counts, business keys, versions, and entity states.

## 27. Common pitfalls

### Assuming merge makes the input object managed

`merge` returns a different managed instance. Use the returned object for any further modifications.

### Calling persist on a detached entity

`persist` is for new entities. For detached entities, use `merge` or reload a managed entity and update it.

### Confusing flush with commit

`flush` only sends SQL within the transaction. The transaction can still roll back.

### Calling clear before flush

Unflushed changes may be detached and never written. Flush before clearing when changes need to be kept.

### Retaining all entities in the persistence context

Long-running jobs can suffer from rising memory and dirty-checking costs. Bound chunk/page sizes and flush/clear intentionally.

### Accessing lazy associations after the reader clears context

Detached entities may fail to load associations. Fetch required data eagerly or use DTO projections.

### Using a physical EntityManager across multiple threads

`EntityManager` is not thread-safe. Use a shared proxy/transaction-scoped context and never pass physical instances across threads.

### Using one persistence context for an entire Job

Overly long-lived contexts accumulate entities and stale state. Use a transaction-scoped context per chunk.

### Failing to understand bulk JPQL bypasses the persistence context

Managed entities can become stale after a bulk update. Flush before and clear/refresh afterward when necessary.

### Using merge for every entity in a writer

`merge` can trigger extra queries and graph copying. Choose `persist` for new entities, dirty checking for managed entities, and `merge` for detached state.

### Assuming restart restores the EntityManager

Spring Batch restores checkpoints, not the persistence context. Store IDs or offsets rather than entities.

### Testing only on H2 and assuming production behaves identically

Locking, ID generation, batching, and SQL behavior can differ by database engine. Run integration tests on the target database engine when behavior depends on it.

## 28. Design checklist for JPA processing in Spring Batch

When building a Step using JPA, clarify:

1. Which `EntityManagerFactory` manages the entities and database?
2. Does the Step use a `JpaTransactionManager` matching that `EntityManagerFactory`?
3. Is the persistence context transaction-scoped or held too long?
4. Does the reader return managed or detached entities?
5. Does the writer need to persist, merge, or simply mutate managed entities?
6. Is flush/clear needed after writes, and who owns that lifecycle?
7. Are chunk size, page size, and JDBC batch size appropriate?
8. Which lazy associations must be fetched before the context is cleared?
9. Are there N+1 queries or collection fetch joins breaking pagination?
10. Do bulk JPQL statements leave the persistence context stale?
11. Can multiple Jobs or workers update the same entity concurrently?
12. Are `@Version` and optimistic locking handling required?
13. Does restart reuse stable inputs, queries, sort keys, and checkpoints?
14. Is the writer idempotent if a chunk is retried?
15. Are there integration tests covering rollback, restart, lazy loading, and batching behavior?

A sound design keeps the persistence context short enough to bound memory while long enough for dirty checking and transactions to work properly. Readers and writers must have clear handling for detached entities; queries must have deterministic ordering; and `flush`, `clear`, and `merge` must follow true JPA semantics.

## Conclusion

`EntityManager` is the API for working with entities, while the persistence context is the first-level cache tracking managed entities and their changes. Dirty checking updates managed entities without requiring a `save` call, `persist()` handles new entities, `merge()` returns a managed instance, `flush()` sends SQL without committing, and `clear()` detaches all entities from the context. In Spring Batch, each chunk normally has its own transaction; `JpaPagingItemReader` may return detached entities after clearing the reader's context, so writers must merge or reload managed entities. Control flushing/clearing, lazy loading, JDBC batching, and sort keys to prevent memory bloat or skipped records. Never share a physical `EntityManager` across threads or treat the persistence context as a checkpoint; restarts must rely on `ExecutionContext`, stable inputs, and idempotent writes.
