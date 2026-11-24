# Clearing the Persistence Context per Chunk

When using JPA in Spring Batch, each loaded or persisted entity can be managed by an `EntityManager`. Managed entities are held in the **persistence context** (first-level cache) so JPA can track changes, perform dirty checking, and synchronize data to the database. If a persistence context lives too long and retains thousands or millions of entities, memory usage can grow continuously.

In chunk-oriented processing, Spring Batch groups items into chunks and invokes the writer inside the chunk's transaction. This is a natural boundary to synchronize data and release entities that are no longer needed. With JPA, the pattern is typically **flush first, clear after**: `flush()` sends pending changes to the database within the current transaction; `clear()` detaches all entities from the persistence context to reduce the number of objects managed by JPA.

Spring Batch provides `JpaItemWriter` with a `clearPersistenceContext` option to perform this after writing a chunk. When writing a custom writer, ensure the proper flush/clear order and understand that clearing only detaches entities—it does not commit the transaction.

## 1. What is the persistence context?

An `EntityManager` manages a persistence context. The persistence context is the set of entity instances that JPA is actively tracking within a unit of work. For managed entities, JPA can:

- Track field changes to perform dirty checking.
- Guarantee that one identity in the persistence context corresponds to one managed entity instance.
- Synchronize changes via SQL on flush.
- Maintain entity relationships and state throughout the scope of the persistence context.
- Coordinate cascades, lazy loading, and lifecycle callbacks according to mappings.

Example:

```java
Customer customer = entityManager.find(Customer.class, 100L);
customer.setName("Nguyen An");
```

If `customer` is managed, no separate update call is required. When the persistence context is flushed, JPA detects the change to `name` and generates the corresponding SQL `UPDATE`.

The persistence context is often called the first-level cache because an already-managed entity can be retrieved again without querying the database within the same context. It differs from a provider's second-level cache (such as Hibernate's), which has a broader scope and separate configuration.

## 2. Why can the persistence context increase memory?

Every managed entity requires tracking state. The provider may retain the entity instance, snapshots for dirty checking, collection states, proxies, relationships, and internal metadata.

If a job reads and writes 500,000 entities within one long-lived persistence context, the context can retain references to vast numbers of objects even when business code no longer uses them directly. The garbage collector cannot reclaim entities while the persistence context still holds references to them.

Illustration:

```text
A long-lived persistence context
  entity 1
  entity 2
  entity 3
  ...
  entity 500000
       |
       v
EntityManager still retains managed state
       |
       v
Heap grows with the number of managed entities
```

In large batches, you must bound the number of concurrently managed entities. One way is ending the persistence context per transaction/chunk; another is flushing and clearing after each chunk when a context is reused longer than necessary.

Not every Spring Batch application keeps a single `EntityManager` across an entire job. With a typical transaction-scoped persistence context, the context is bound to the transaction and closed/released according to the transaction lifecycle. Nevertheless, a writer can proactively clear after writing a chunk to release managed state immediately within that transaction, especially when a context is shared or configured with a longer-than-expected lifecycle.

## 3. Distinguishing flush, clear, and commit

These three operations have distinct meanings:

| Operation | Meaning | Commits the transaction? |
|---|---|---:|
| `EntityManager.flush()` | Synchronizes pending changes in the persistence context to the database as SQL. | No. |
| `EntityManager.clear()` | Detaches all entities from the current persistence context. | No. |
| Transaction `commit` | Finalizes the database transaction via the transaction manager. | Yes. |

Example:

```java
entity.setStatus(Status.PROCESSED);
entityManager.flush(); // SQL is sent within the current transaction.
entityManager.clear(); // Entities are no longer managed.
// Transaction only commits when Spring Batch completes the chunk.
```

`flush()` does not make changes durable. If the transaction rolls back afterward, the database can still undo the flushed SQL. `clear()` neither commits nor rolls back; it only alters in-memory entity management state.

## 4. Why must you flush before clearing?

If a managed entity has unflushed changes, calling `clear()` detaches the entity and removes it from the persistence context. Unsynchronized changes may no longer be tracked by JPA for automatic persistence to the database.

The correct order to ensure all current changes reach the database before detaching:

```java
entityManager.flush();
entityManager.clear();
```

Unsafe order:

```java
entityManager.clear();
entityManager.flush(); // Just-cleared entities are no longer tracked.
```

One point to remember: flushing only sends SQL within the transaction. If a constraint violation or SQL error occurs at flush, the exception is raised right there rather than waiting for commit. That can help pinpoint write errors during the writer phase, though the transaction can still roll back.

## 5. A chunk is a natural boundary for clearing

In a chunk-oriented step, Spring Batch executes this general loop:

```text
BEGIN transaction
  read item 1
  read item 2
  ...
  read item N
  process items
  call ItemWriter.write(chunk)
  flush JPA changes
  clear persistence context
COMMIT transaction
```

One writer invocation typically corresponds to one chunk. If the writer uses `JpaItemWriter` with clearing enabled, the writer flushes and then clears after writing the chunk's items.

Benefits:

- Caps the number of entities left managed after each write.
- Reduces dirty-checking overhead on a long-lived persistence context.
- Avoids retaining snapshots and relationships of already-processed entities.
- Reduces the risk of heap growing linearly with total job items.

Clearing per chunk makes more sense than clearing after every single item. Per-item clearing can defeat batching, render lazy associations unavailable, and add entity management overhead. Chunks group a batch of changes, flush once per the writer design, and then detach the group of entities.

## 6. Configuring JpaItemWriter

`JpaItemWriter<T>` is Spring Batch's built-in writer for writing entities via JPA. It can be configured directly:

```java
@Bean
JpaItemWriter<Customer> customerWriter(EntityManagerFactory entityManagerFactory) {
    JpaItemWriter<Customer> writer = new JpaItemWriter<>();
    writer.setEntityManagerFactory(entityManagerFactory);
    writer.setUsePersist(false);
    writer.setClearPersistenceContext(true);
    return writer;
}
```

Key properties:

| Property | Meaning |
|---|---|
| `entityManagerFactory` | Factory that creates or supplies the transaction-bound `EntityManager`. |
| `usePersist` | Chooses `persist` for new entities instead of the default `merge`. |
| `clearPersistenceContext` | Instructs the writer to clear the persistence context after writing a chunk. |

Configure `clearPersistenceContext(true)` explicitly when the goal is to limit managed entity count. Defaults may depend on the version; verify against the exact API and dependency version in use rather than relying on an implicit default.

`JpaItemWriter` must execute within a transaction compatible with the `EntityManagerFactory`. In Spring Batch, you typically configure `JpaTransactionManager` using the same `EntityManagerFactory` for the step. Do not call the writer outside a transaction if it expects a transactional `EntityManager`.

## 7. Writing new vs. existing entities

`JpaItemWriter` supports two write modes:

- `persist`: creates a new entity in the persistence context.
- `merge`: synchronizes the state of a detached entity into a managed instance.

New entity example:

```java
Customer customer = new Customer("C001", "Nguyen An");
entityManager.persist(customer);
```

Detached entity requiring merge example:

```java
Customer detachedCustomer = loadFromEarlierContext();
detachedCustomer.setName("An Nguyen");

Customer managedCopy = entityManager.merge(detachedCustomer);
```

`merge()` returns the managed instance. The passed-in object may remain detached. If you need to perform further operations on the managed entity, use the object returned by `merge()`.

In `JpaItemWriter`, `usePersist(true)` fits when every item is guaranteed to be a new entity by source contract. If an item may already exist, `persist` can cause identity or constraint errors. The `merge` default is more flexible for detached entities, though it can incur extra queries and overhead.

Clearing after the writer finishes detaches all entities persisted or merged in the chunk. Do not retain references expecting them to remain managed in the next chunk.

## 8. Integrating JpaItemWriter into a chunk step

Example customer processing step:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        JpaTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JpaItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(300, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

In this example, each chunk has at most 300 items. `JpaItemWriter` writes the chunk's items, flushes, and clears the persistence context as configured. The transaction manager commits when the chunk finishes.

If using `PlatformTransactionManager` as the parameter type instead of `JpaTransactionManager`, make sure the actual bean instance is a transaction manager compatible with the `EntityManagerFactory` in use. Using a plain JDBC transaction manager does not automatically guarantee that the JPA `EntityManager` joins the same transaction.

## 9. Writing a custom ItemWriter with flush and clear

When custom write logic is needed, you can implement `ItemWriter` and manage a Spring-injected `EntityManager`:

```java
@Component
public class ClearingCustomerWriter implements ItemWriter<Customer> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            entityManager.merge(customer);
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

`@PersistenceContext` typically injects a shared `EntityManager` proxy bound to the current transaction in a Spring environment. Ensure a compatible transaction manager is configured so the proxy resolves the right `EntityManager`.

This example uses `merge` for every item. If all items are new entities, you can use `persist`; if data mixes new and existing entities, establish a clear rule to avoid errors or unnecessary queries.

Do not write a custom writer solely to call `clear()` if `JpaItemWriter` already meets your requirements. A custom writer assumes full responsibility for mapping, merge/persist logic, exception handling, lifecycle, and transaction semantics.

## 10. Clearing in the writer vs. using a listener

You might consider clearing the persistence context in a `ChunkListener` or `ItemWriteListener`. However, understand callback timing and transaction boundaries.

| Location | Notes |
|---|---|
| Inside `JpaItemWriter` after flush | Makes it explicit that the writer finishes writing the chunk and then clears; the most direct and controllable option. |
| Custom writer after `flush()` | Appropriate when the writer has custom write logic. |
| `afterWrite` listener | Can run after the writer and before transaction commit; must verify flush already occurred and the right context is cleared. |
| `afterChunk` listener | Callback in the chunk lifecycle; the transaction may already have finished depending on the callback contract. Should not be used as the default substitute for writer-managed persistence context clearing. |

If you simply want to clear after the JPA writer finishes, configuring `JpaItemWriter.setClearPersistenceContext(true)` is simpler. If you have a specialized listener, verify when the callback runs in your Spring Batch version and check whether the transaction is still active.

## 11. Clearing the persistence context detaches all entities

`EntityManager.clear()` does not detach only the entities just written. It detaches **all** entities currently managed in that persistence context.

This can affect:

- Entities previously loaded by the reader or processor in the same context.
- Related entities across `@OneToMany`, `@ManyToOne`, `@OneToOne`, or `@ManyToMany` associations.
- Other entities loaded by services within the same transaction.
- Unflushed changes on an entity not included in the chunk.
- Lazy collections or proxies requiring the persistence context to load data.

Example:

```java
Customer customer = entityManager.find(Customer.class, 1L);
Order order = entityManager.find(Order.class, 10L);

entityManager.flush();
entityManager.clear();

// customer and order are now detached.
```

After clearing, changes to detached objects are no longer automatically dirty-checked. To update them further, merge them back or load fresh entities in an appropriate persistence context.

Do not call `clear` inside a shared service if that service still relies on other managed entities. `clear` operates on the entire persistence context, not just a single entity type.

## 12. Lazy loading after clear

A detached entity cannot rely on the old persistence context to initialize lazy associations.

Example:

```java
Customer customer = entityManager.find(Customer.class, 1L);
entityManager.clear();

customer.getOrders().size(); // May throw LazyInitializationException.
```

With Hibernate, the typical error is `LazyInitializationException` when accessing a proxy or collection that requires an open session or managed entity.

If the processor or writer needs an association, load it within an active transaction/persistence context using fetch joins, entity graphs, projections, or a suitable dedicated query. Do not rely on keeping entities managed across multiple chunks.

A better strategy is often reading projections/DTOs containing only the fields needed for the batch, then writing entities with an explicit writer. This reduces unnecessary entities and lazy associations in the persistence context.

## 13. Reader and writer may use different persistence contexts

Within a step, the reader and writer do not necessarily share the same `EntityManager` or persistence context.

For example, `JpaPagingItemReader` may manage its own entity manager for reading and return entities under the reader's semantics. The writer may obtain a transactional entity manager bound to the chunk transaction. Clearing in the writer only clears the context the writer uses; it does not necessarily clear the reader's internal entity manager.

Therefore, when diagnosing memory growth:

- Identify whether the reader uses `JpaPagingItemReader`, `HibernateCursorItemReader`, JDBC projections, or a custom reader.
- Identify which entities remain managed in the reader context.
- Identify whether the writer uses `JpaItemWriter` or an injected `EntityManager`.
- Determine which contexts span across pages/chunks and which close at transaction end.
- Do not assume `entityManager.clear()` in the writer frees every entity created by a separate reader.

If the reader is retaining entities, configure an appropriate page size/lifecycle or switch to projections/DTOs to avoid materializing unnecessary managed entities.

## 14. JpaPagingItemReader and page lifecycle

`JpaPagingItemReader` reads JPA data page by page. The reader has its own persistence context lifecycle for querying and managing a page's entities. Depending on version and configuration, the reader flushes/clears or detaches entities when moving between pages to prevent unbounded context growth.

Points to remember:

- Page size is the number of entities the reader fetches in one query.
- Chunk size is the number of items the step processes before committing.
- Page boundaries and chunk boundaries may differ.
- Entities returned by the reader may already be detached when the processor handles them.
- Do not rely on lazy loading from the reader's context if that context has already been cleared or closed.

If page size is larger than chunk size, the reader may load an entire page before the step consumes all of it. This affects heap usage. Choose page size based on entity size and workload.

## 15. Does clearing the persistence context replace committing?

No. This is a dangerous misconception.

Example:

```java
entityManager.persist(customer);
entityManager.flush();
entityManager.clear();
```

The SQL `INSERT` may have been sent to the database, but the transaction is not necessarily committed yet. If the writer or step fails later, the transaction manager can roll back the change.

Do not call `EntityTransaction.commit()` directly from a writer managed by Spring Batch. Doing so breaks the transaction boundaries orchestrated by the step. Let the step's `PlatformTransactionManager` handle commit and rollback.

## 16. Clearing and rollback when the writer fails

If `flush()` throws an exception, the writer should not proceed to clear as if the write succeeded. The exception must propagate so the transaction rolls back or fault-tolerance policies apply.

Safer custom writer example:

```java
@Override
public void write(Chunk<? extends Customer> chunk) {
    for (Customer customer : chunk) {
        entityManager.merge(customer);
    }

    entityManager.flush(); // On error, the exception propagates to the step.
    entityManager.clear(); // Runs only when flush succeeds.
}
```

Even if `flush()` succeeds and `clear()` is called, the transaction can still roll back if another component in the chunk fails. Clearing does not alter the rollback capability of SQL executed inside the transaction.

After a rollback, the transaction-scoped entity manager may be marked rollback-only or closed by the transaction manager. Do not continue using managed or detached entities from a failed transaction as if they were synchronized with the database. On retry, rely on Spring Batch and JPA writer lifecycles and semantics.

## 17. Bulk updates/deletes and stale persistence contexts

JPQL bulk updates/deletes or native SQL typically update the database directly without synchronizing individual managed entities in the persistence context.

Example:

```java
entityManager.createQuery("""
        update Customer c
           set c.status = :status
         where c.lastLogin < :cutoff
        """)
        .setParameter("status", Status.INACTIVE)
        .setParameter("cutoff", cutoff)
        .executeUpdate();
```

Previously loaded `Customer` instances may still hold the old status in the persistence context. Consider flushing pending changes before the bulk operation and clearing or refreshing entities afterward:

```java
entityManager.flush();
int updated = query.executeUpdate();
entityManager.clear();
```

Here, clearing also prevents reading stale state later. If only a single entity needs updating, `refresh()` or `detach()` may be used appropriately instead of clearing the entire context.

## 18. Clearing the entire context vs. detaching individual entities

JPA provides several entity management operations:

| API | Effect |
|---|---|
| `clear()` | Detaches all entities in the persistence context. |
| `detach(entity)` | Detaches one specific entity. |
| `refresh(entity)` | Reloads a managed entity's state from the database, overwriting unflushed local changes per JPA semantics. |
| `merge(entity)` | Copies detached entity state into a managed entity and returns the managed instance. |
| `flush()` | Synchronizes pending changes to the database. |

Clearing the whole context fits when all entities in the context are finished and no longer need dirty checking. Detaching individual entities fits when you only want to evict one object while keeping other entities managed.

In a batch writer, clearing per chunk is usually simple and effective if the writer owns that persistence context scope. If the context is shared with other operations in the same transaction, be careful because clearing affects everything in it.

## 19. Impact of cascades and entity relationships

When persisting or merging an entity with cascaded relationships, JPA may manage additional related entities in the same persistence context.

Example:

```java
@Entity
class Customer {
    @OneToMany(mappedBy = "customer", cascade = CascadeType.PERSIST)
    private List<Order> orders = new ArrayList<>();
}
```

Writing one customer with many orders can bring many entities under management within a single chunk. Therefore, the actual number of entities in the persistence context can exceed the chunk item count.

If a chunk has 300 customers and each customer has hundreds of child entities, clearing after the chunk still needs to be evaluated alongside object graph size. You may need to reduce chunk size, write children in separate batches, or load only genuinely needed relationships.

Clearing neither deletes relationship data in the database nor clears collections on Java objects. It only detaches the entities. The object graph can still remain on the heap if processors, writers, or caches hold references.

## 20. How chunk size affects managed entity counts

A larger chunk size generally increases the number of entities coexisting in the transaction/persistence context. However, the entity count does not necessarily equal chunk size because:

- One item may create or load multiple related entities.
- The processor may query additional entities.
- The writer may merge and create managed copies.
- The reader may load a page larger than the chunk.
- Listeners or caches may retain references across multiple chunks.

Example:

| Chunk size | Max items per write | Notes |
|---:|---:|---|
| 50 | 50 | Short transactions, more frequent clears, higher commit overhead. |
| 300 | 300 | Starting point for benchmarking with moderate-sized entities. |
| 2,000 | 2,000 | Can increase heap usage, dirty checking cost, and transaction duration. |

These are illustrative examples, not fixed recommendations. Benchmark using realistic object graph sizes and a production-like database.

## 21. Clearing and JDBC batch inserts/updates

Clearing the persistence context does not automatically enable JDBC batching. The two mechanisms solve different problems:

- `clear()` reduces the number of entities managed by JPA in memory.
- JDBC batching groups compatible SQL statements into batches sent to the database.

With Hibernate, batching can be configured via properties such as `hibernate.jdbc.batch_size`, though effectiveness depends on ID generation strategy, statement shape, driver, and mappings. Some ID generation strategies limit insert batching.

Example Hibernate configuration in Spring Boot:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Do not set JDBC batch size overly large merely because chunk size is large. Measure statement counts, batch execution, heap usage, and commit duration. Clearing after flush does not replace batching; the writer flushes statements according to the configured provider mechanism and then clears the context.

## 22. Do not clear before finishing logic requiring managed entities

A processor might update an entity and let the writer save it. If clearing happens too early, downstream steps receive a detached entity and lose automatic dirty checking.

Example to avoid:

```java
Customer customer = entityManager.find(Customer.class, id);
customer.setStatus(Status.READY);
entityManager.clear();

return customer; // Detached; changes must be merged again to persist.
```

If the writer subsequently uses `JpaItemWriter` with merge, changes can still be synchronized, but this incurs a merge and potential extra queries. If the writer assumes items remain managed, changes may not be persisted.

Place the clear at the boundary after the writer completes its work with the entities. Do not clear in the reader or processor purely to shrink heap if the pipeline still expects managed state.

## 23. When should you not clear?

Clearing is not always appropriate. Manual clearing may be unnecessary if:

- The persistence context already closes after each transaction/chunk and the memory profile is stable.
- The writer needs to keep using managed entities within the same transaction after writing.
- Unflushed changes on other entities in the context still rely on dirty checking.
- A shared service uses the same context and continues operating on managed entities after the writer.
- Clearing would break lazy loading or cascade logic within the same chunk.

In such cases, clarify the persistence context lifecycle and consider a transaction-scoped context, DTOs/projections, or selective detachment rather than clearing everything.

## 24. Clearing the persistence context per chunk with a listener or wrapper

If `JpaItemWriter` cannot be used, a listener or wrapper writer can sometimes perform clearing after writing. A wrapper keeps operation order explicit inside the writer:

```java
public class ClearingItemWriter<T> implements ItemWriter<T> {

    private final ItemWriter<T> delegate;
    private final EntityManager entityManager;

    public ClearingItemWriter(
            ItemWriter<T> delegate,
            EntityManager entityManager) {
        this.delegate = delegate;
        this.entityManager = entityManager;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
        entityManager.flush();
        entityManager.clear();
    }
}
```

This is an illustrative pattern; use it only when `delegate` and `entityManager` participate in the same transaction/persistence context and clearing does not disrupt a context `delegate` still needs after returning. If `delegate` is a `JpaItemWriter` that already flushes/clears, this wrapper is redundant.

Do not inject an arbitrary `EntityManager` created outside the Spring transaction and expect it to clear the context used by the writer. Ensure both use the same `EntityManagerFactory` and transactional context.

## 25. Handling detached entities across chunks

After clearing, the Java object still exists if the application holds a reference, but its state is detached. If an item is cached and reused in a later chunk, JPA will not automatically track changes on that object.

Example:

```java
Customer customer = entityManager.merge(detachedCustomer);
entityManager.flush();
entityManager.clear();

customer.setName("Updated later"); // No longer dirty-checked.
```

To update it in a later chunk:

```java
Customer managed = entityManager.merge(customer);
managed.setName("Updated later");
```

Or reload the entity by ID in the new transaction's persistence context:

```java
Customer managed = entityManager.find(Customer.class, customerId);
managed.setName("Updated later");
```

In batch processing, it is best not to cache detached entities long-term when only an identifier is needed. Store IDs or small DTOs, and load fresh data in the corresponding chunk.

## 26. The transaction manager must be JPA-compatible

For `JpaItemWriter` to participate in the chunk transaction, configure the step with a transaction manager using the same `EntityManagerFactory`:

```java
@Bean
JpaTransactionManager transactionManager(EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}
```

In applications combining JDBC and JPA, understand how both resources join transactions. `JpaTransactionManager` can coordinate with a JDBC connection from the same datasource under proper configuration, but multi-datasource setups are not automatically atomic.

Do not create an `EntityManager` via `entityManagerFactory.createEntityManager()` inside a writer and open/close it manually if the goal is to join Spring's transaction. An `EntityManager` created that way may not be managed by the transaction manager as expected.

## 27. Testing flush and clear

Tests should verify two separate things:

1. Chunk changes were flushed to the transaction/database as expected.
2. Entities were detached after the writer finished when clearing is enabled.

Example with `EntityManager` in an integration test:

```java
@Test
void writerFlushesAndClearsPersistenceContext() {
    Customer customer = new Customer("C001", "Nguyen An");

    TransactionTemplate transaction = new TransactionTemplate(transactionManager);
    transaction.executeWithoutResult(status -> {
        customerWriter.write(new Chunk<>(List.of(customer)));

        assertThat(entityManager.contains(customer)).isFalse();
    });

    Customer persisted = entityManager.find(Customer.class, customer.getId());
    assertThat(persisted.getName()).isEqualTo("Nguyen An");
}
```

Real tests must use the exact persistence context the writer uses. If the writer merges detached input, the input object may already be detached even before clearing; therefore `contains(input)` alone is not sufficient proof of clearing. You can check another entity loaded/managed in the same context or spy/mock `EntityManager.clear()` in a unit test.

In database tests, flush and clear before re-reading to avoid the first-level cache returning stale in-memory objects and skewing test results. Use explicit transaction boundaries and inspect data after commit when tests need to verify real persistence.

## 28. Testing clearing across multiple chunks

A step integration test should process multiple chunks and verify the writer clears after every write, not just once at the end of the job.

Example test strategy:

1. Create input exceeding twice the chunk size.
2. Use a writer wrapper or spy to count `flush`/`clear` invocations.
3. Run the step with a small chunk size to trigger multiple `write()` calls.
4. Verify `clear` is called after each successful write.
5. Verify the total record count in the database is accurate.
6. Cause one chunk to fail and verify the transaction rolls back.
7. Restart the job and verify no data is lost or duplicated.

Do not assert only the `clear` invocation count. Verify data and transaction semantics as well, because `clear` might be called while the writer flushes incorrectly, uses the wrong `EntityManager`, or drops unsynchronized changes.

## 29. Testing rollback after flush

An important test proves that flushing is not committing:

1. Within a transaction, persist or merge an entity.
2. Call `flush()`.
3. Throw an exception before the transaction commits.
4. Roll back the transaction.
5. Open a new transaction and verify the entity was not saved.

Conceptual example:

```java
assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
    entityManager.persist(new Customer("C999", "Temporary"));
    entityManager.flush();
    throw new IllegalStateException("Force rollback");
}));

assertThat(customerRepository.existsByCustomerId("C999")).isFalse();
```

This test confirms `flush()` sent SQL yet the transaction could still roll back. Depending on the database/provider, ensure the exception is thrown inside the transaction and the assertion runs after the transaction has ended.

## 30. Monitoring memory and the persistence context

When suspecting a JPA-related memory leak, observe multiple metrics:

- Heap used and old generation size after each chunk.
- Allocation rate and GC pauses.
- Items per chunk and object graph size.
- Flush and commit durations.
- Counts of SQL `SELECT`/`INSERT`/`UPDATE` statements executed.
- Numbers of entities/collections retained in heap dumps.
- Reference paths showing which `EntityManager`, Hibernate `Session`, collection, or cache holds entities.

With Hibernate, you can enable statistics in benchmark environments to observe entity loads, fetches, inserts, updates, and query counts. Avoid overly verbose SQL logging in production if it increases I/O or exposes sensitive data.

If heap grows steadily chunk after chunk despite writer clearing, check:

- Whether a cache or list in a processor or listener retains entities.
- Whether the reader has its own persistence context that is not being cleared or closed.
- Whether large entity graphs or lazy collections are being initialized.
- Whether a listener accumulates every item for summary reporting.
- Whether a transaction or extended `EntityManager` lives longer than expected.
- Whether multiple concurrent workers each hold separate chunks/contexts.

Clearing only releases references held by the persistence context. It does not release objects referenced elsewhere by the application.

## 31. Common pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Heap grows with total item count | Persistence context holds managed entities too long. | Flush/clear per chunk or end context at proper transaction scope. |
| Changes are not saved | Clearing before flushing detached entities with pending changes. | Always flush first, then clear. |
| Entities can no longer lazy-load | Clearing detached entities before associations were accessed. | Fetch needed data before clearing or use DTOs/projections. |
| Changes after clear are not saved | Code keeps mutating detached entities expecting dirty checking. | Merge or reload in a fresh context. |
| Flushed data is still lost | Transaction rolled back after flush. | Remember flush does not commit; inspect transaction manager behavior. |
| `LazyInitializationException` | Accessing lazy proxy after context is cleared/closed. | Fetch associations inside context scope or avoid passing lazy entities across boundaries. |
| Clearing affects unrelated entities | `clear()` detaches every entity in the context. | Narrow context scope or use selective `detach(entity)`. |
| Writer does not join transaction | Incompatible `EntityManagerFactory`/transaction manager or manually created EM outside Spring. | Use an appropriate `JpaTransactionManager` and transactional `EntityManager`. |
| Reader still retains many entities | Reader uses its own persistence context; writer clears a different context. | Inspect reader lifecycle/page size and use projections where appropriate. |
| SQL is not batched | Clearing confused with JDBC batching or flushing per item. | Configure Hibernate JDBC batching and measure real execution. |
| Entities written twice after retry | Non-idempotent side effects or transaction doesn't cover the right resource. | Use unique keys/upserts and test rollback/restart. |
| Clearing in listener has no effect | Callback runs at the wrong time or uses the wrong `EntityManager`. | Prefer configuring `JpaItemWriter` or clearing in the writer after flush. |

## 32. Design workflow for chunk-based persistence context clearing

When building a high-volume JPA step, determine:

1. **Identify the `EntityManager`:** Which persistence context do the reader, processor, and writer use?
2. **Define the lifecycle:** Is the context transaction-scoped or extended, and where does it open/close?
3. **Choose chunk size:** Base it on entity counts and object graph size, not item count alone.
4. **Select the writer:** Prefer `JpaItemWriter` if its persist/merge semantics fit requirements.
5. **Enable clearing:** Configure `clearPersistenceContext(true)` when entities must be detached after writing a chunk.
6. **Preserve order:** Flush successfully before clearing; let Spring Batch manage commits.
7. **Check lazy relationships:** Ensure all needed data is fetched prior to clearing.
8. **Handle detached entities:** Merge or reload if further updates are needed in a new context.
9. **Configure transactions:** Use a transaction manager compatible with the `EntityManagerFactory`.
10. **Tune JDBC batching:** Evaluate separately from clearing and measure effectiveness.
11. **Inspect bulk operations:** Flush/clear or refresh to prevent stale persistence contexts.
12. **Measure memory:** Monitor heap, GC, object graphs, and reference paths across many chunks.
13. **Test thoroughly:** Cover multiple chunks, clearing, flush failures, rollbacks, restarts, and final persisted data.

## 33. Key takeaways

- The persistence context is a first-level cache managed by `EntityManager`; it tracks managed entities and their changes.
- A context that lives too long can accumulate entities and snapshots, causing heap usage to grow with item count.
- `flush()` sends changes as SQL within the current transaction; it does not commit.
- `clear()` detaches all entities from the persistence context; it neither commits nor rolls back.
- When synchronizing before detaching, always flush successfully first, then clear.
- `JpaItemWriter` supports `clearPersistenceContext`; configure it explicitly when clearing after each chunk write is required.
- `persist` suits new entities; `merge` copies detached state into a managed instance and returns that managed instance.
- Clearing affects every entity in the context, not just the chunk's items; exercise caution with shared services and contexts.
- Detached entities lose dirty checking and may be unable to lazy-load associations.
- Readers and writers may use separate persistence contexts; clearing in the writer does not automatically free the reader's context.
- Page size, chunk size, and entity count in object graphs jointly affect memory.
- Clearing does not replace JDBC batching, transaction commits, or idempotency.
- The transaction manager must coordinate properly with `EntityManagerFactory`; let Spring Batch control commits and rollbacks.
- Test multi-chunk clearing, rollback after flush, detached behavior, and post-commit database state.

Clearing the persistence context per chunk limits the number of entities JPA continues managing during large batches. Understand your `EntityManager` scope, place the clear after a successful writer flush, and let Spring Batch's transaction manager govern commit and rollback. Combined with an appropriate chunk size, selective data fetching, proper writer lifecycles, and restart/rollback tests, your application can process large entity volumes without letting the first-level cache grow unchecked.
