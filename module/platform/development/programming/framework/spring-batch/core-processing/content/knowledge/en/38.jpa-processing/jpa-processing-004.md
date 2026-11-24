# Flushing Before Commit

In Spring Batch, when a writer saves entities via JPA, changes are typically held in the **persistence context** before being synchronized to the database. Calling `flush()` instructs JPA to synchronize pending changes with the database within the current transaction. Afterward, the chunk transaction continues and commits only when Spring Batch completes the chunk's steps.

Therefore, **flush is not commit**. Flushing sends the necessary SQL statements to the database and surfaces many persistence errors earlier; committing is what finishes the transaction and makes changes durable under database transaction semantics.

In Spring Batch, `JpaItemWriter` typically flushes after writing a chunk. When using a custom JPA writer or Spring Data repository, understand flush timing, the persistence context, and the transaction manager to avoid partial writes, retaining too many entities in memory, or mistakenly assuming data has already committed.

## 1. How does the persistence context hold changes?

An `EntityManager` manages a persistence context where JPA tracks entities in the managed state. When the application modifies a managed entity, the provider typically marks the change in memory. SQL might not be sent immediately when a setter is invoked.

Example:

~~~java
Order order = entityManager.find(Order.class, 1001L);
order.setStatus(OrderStatus.PAID);
~~~

If `order` is managed, JPA dirty checking detects that `status` changed. The application does not necessarily have to issue a manual SQL update. On flush, the provider generates and executes the appropriate `UPDATE`.

You can picture it as:

~~~text
EntityManager / Persistence Context
             |
             | entity loaded or persisted
             v
       Managed entity
             |
             | field mutated
             v
      Pending changes
             |
             | flush()
             v
       SQL executed
             |
             | commit transaction
             v
      Transaction completed
~~~

Before flush, changes may exist only in the persistence context. After flush, the database has executed the SQL within the current transaction, yet the transaction can still roll back.

## 2. What is flush?

`EntityManager.flush()` synchronizes persistence context state with the database. The provider inspects managed entities, detects changes, processes persist/remove operations, and sends the required SQL statements.

Flushing can produce:

- `INSERT` for newly persisted entities.
- `UPDATE` for modified managed entities.
- `DELETE` for removed entities.
- Operations triggered by cascades.
- Constraint or optimistic locking checks when the database executes the SQL.

Example:

~~~java
@Transactional
public void updateOrder(Long id) {
    Order order = entityManager.find(Order.class, id);
    order.setStatus(OrderStatus.PAID);

    entityManager.flush();

    // SQL UPDATE has been sent within the current transaction.
    // The transaction has not committed yet here.
}
~~~

If the transaction subsequently rolls back, the flushed `UPDATE` can still be undone by the database. Flushing neither creates a separate transaction nor instructs the database to commit.

Flushing applies to pending changes across the persistence context, not just the entity modified right before the flush call.

## 3. How does flush differ from commit?

This is the most critical distinction when working with JPA in chunk processing.

| Property | Flush | Commit |
|---|---|---|
| Purpose | Synchronizes persistence context with database | Completes the transaction |
| SQL executed | May send `INSERT`/`UPDATE`/`DELETE` | Executes any remaining work and finishes the transaction |
| Transaction still open | Yes | No, after successful commit |
| Can roll back afterward | Yes | Cannot roll back a committed transaction |
| Data durability | Not yet guaranteed | According to database durability semantics |
| Database locks | May be held until transaction end | Released per database rules |
| Constraint checks | Many errors appear on flush | Deferred constraints may only check at commit |

Example sequence:

~~~text
BEGIN
  |
  +--> entityManager.persist(order)
  |
  +--> entityManager.flush()
  |       |
  |       +--> INSERT sent to database
  |       +--> Constraint/SQL error may appear
  |
  +--> processor/writer or stream state continues
  |
  +--> COMMIT
          |
          +--> Transaction completed
~~~

If an error occurs after flush but before commit, the transaction can still roll back. Never notify an external system that data is finalized merely because flush succeeded.

## 4. When does JPA flush automatically?

Applications do not need to call flush after every operation. The JPA provider may flush automatically at certain points based on `FlushModeType` and transaction lifecycle.

Two primary modes:

- `FlushModeType.AUTO`: the default mode in many configurations. The provider must ensure pending changes that could affect query results are reflected when queries execute; the provider may flush before a query.
- `FlushModeType.COMMIT`: the provider is required to flush before transaction commit. Query results when the persistence context holds unflushed changes may not reflect those changes; do not rely on query visibility in this mode.

Example:

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

With `AUTO`, a query can trigger a flush earlier than expected. Therefore, a query statement in a processor or writer may be where a constraint error surfaces, even when the code makes no explicit flush call.

Do not change the flush mode to mask errors. Choose the mode based on required semantics and test against your actual provider and database.

## 5. Why flush before commit in Spring Batch?

Explicit flushing can be useful when you want to:

- Force SQL execution during the writer phase so errors appear close to write operations.
- Detect unique constraint, foreign key, or optimistic locking conflicts early.
- Synchronize changes before a query that needs to see recently updated data.
- Release or clear the persistence context once SQL has been sent.
- Measure SQL execution time inside the writer rather than having errors surface late at commit.

However, flushing does not replace transaction commit and does not guarantee every constraint is checked immediately. Databases with deferred constraints may still report errors only at commit time.

In a chunk Step, flushing should typically occur inside the writer before the Step updates stream state and commits the transaction. This helps keep many persistence errors within the writer invocation scope, making them easier to associate with the chunk.

## 6. Chunk transactions in Spring Batch

A chunk-oriented Step gathers items, processes them, and writes them within a transaction. Example with chunk size 100:

~~~text
Chunk transaction begins
       |
       v
Read up to 100 items
       |
       v
Process items
       |
       v
Writer writes 100 items
       |
       v
JPA flush
       |
       v
Update ExecutionContext / stream state
       |
       v
Commit chunk transaction
~~~

If the writer flushes successfully, Spring Batch has not committed yet at that moment. Subsequent steps in the chunk lifecycle can still fail.

If an exception is classified as rollback-triggering, the chunk transaction rolls back. Reader state and transaction-aware metadata are managed according to Spring Batch and the transaction manager.

Do not open a separate transaction inside the writer if you want JPA data to roll back together with the chunk. The writer must participate in the transaction managed by the Step.

## 7. JpaItemWriter and automatic flush

Spring Batch provides `JpaItemWriter` to write items via an `EntityManager`. The writer uses the configured `EntityManagerFactory` and retrieves the `EntityManager` bound to the current transaction.

Example:

~~~java
@Bean
public JpaItemWriter<Order> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(true)
            .build();
}
~~~

In common Spring Batch versions, `JpaItemWriter` writes the chunk's items and then calls `flush`. Many versions also clear the persistence context after flushing to avoid retaining too many managed entities. Check the API and defaults of your exact Spring Batch version, as options such as `usePersist` and persistence context clearing may vary by version.

When using standard `JpaItemWriter`, you normally do not need an extra manual flush after the writer. Calling flush repeatedly does not make the transaction commit sooner and can degrade JDBC batching efficiency.

## 8. Persist and merge in JpaItemWriter

`JpaItemWriter` can use `persist` or `merge` depending on configuration.

- `persist(entity)` is for new entities that need to become managed in the persistence context.
- `merge(entity)` copies state from a detached/new entity into a managed instance and returns that managed instance.

Example:

~~~java
Order managed = entityManager.merge(detachedOrder);
~~~

Do not assume `detachedOrder` becomes managed after `merge`. The object returned by `merge` is the managed instance; the input object may remain detached.

Choose `persist` or `merge` based on entity lifecycle and how input data is constructed. If an item already carries an ID that does not actually exist in the database, `merge` may insert or update depending on provider semantics. If a new entity is persisted with a duplicate key, an error can surface at flush or commit.

Do not use `merge` as a cure-all for duplicate key errors. Clarify whether entities are new or existing updates and enforce appropriate business keys/unique constraints.

## 9. Configuring the transaction manager for a JPA Step

A JPA writer needs an `EntityManager` participating in the Step's transaction. Configure `JpaTransactionManager` with the matching `EntityManagerFactory`:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Step using that transaction manager:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        JpaItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Key points:

- `JpaItemWriter` and the transaction manager must use the same `EntityManagerFactory`.
- The `EntityManager` must be obtained for the current transaction.
- Do not manually create an `EntityManager` and close/commit it inside each write if rollback with the chunk is required.
- Do not call `commit` directly on the `EntityTransaction` of a Spring-managed `EntityManager`.

If the application has multiple persistence units, select the right `EntityManagerFactory` and transaction manager for the corresponding Step.

## 10. Custom ItemWriter and EntityManager

When custom write logic is needed, inject `EntityManager` via `@PersistenceContext` or a Spring-provided shared `EntityManager` proxy.

Example:

~~~java
@Component
public class OrderStatusWriter implements ItemWriter<Order> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            entityManager.persist(order);
        }

        entityManager.flush();
    }
}
~~~

The injected `EntityManager` is managed by Spring and joins the current transaction when configured properly. Do not call `entityManager.getTransaction().commit()` in the writer; transaction lifecycle belongs to Spring Batch and the transaction manager.

In a custom writer, flushing once after processing the chunk generally makes more sense than flushing per item. If you need smaller-batch flushes to bound the persistence context, consider clearing strategy and its effect on entity state.

## 11. Flush and dirty checking

JPA dirty checking tracks changes on managed entities. On flush, the provider compares current state against snapshots or internal tracking state to determine required `UPDATE` statements.

Example:

~~~java
Order order = entityManager.find(Order.class, id);
order.setStatus(OrderStatus.SHIPPED);
order.setShippedAt(Instant.now());

// No need to call merge if order is still managed.
entityManager.flush();
~~~

If an entity is detached, field changes are not automatically flushed. It must be merged or reattached appropriately.

A common mistake is instantiating a new object from reader data, modifying it, and expecting JPA to automatically `UPDATE` the row with the same ID. A newly created object is detached or transient; dirty checking applies only to managed entities.

Understand entity states:

| State | Meaning |
|---|---|
| New/Transient | Not managed by the persistence context |
| Managed | Tracked by `EntityManager`; changes can be flushed |
| Detached | Previously managed but no longer tracked |
| Removed | Marked for deletion in the persistence context |

Flushing synchronizes only state managed by the persistence context and registered persist/remove operations.

## 12. Flush and cascade

When an entity has cascaded relationships, persist/merge/remove operations can propagate to related entities per the cascade configuration.

Example:

~~~java
@OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

When persisting a new `Order`, its `OrderLine` instances can be persisted by cascade. On flush, the provider executes the SQL statements needed for the entire aggregate according to mappings.

If a relationship lacks the appropriate cascade, child entities may not be saved as expected or may raise a transient object exception. If `orphanRemoval` is enabled, removing a child from the collection can trigger a `DELETE` at flush.

Do not add `CascadeType.ALL` merely to make errors disappear. Define aggregate ownership and actual lifecycles; wrong cascades can delete or update entities unexpectedly.

## 13. Flush and constraint violations

Many database errors surface only when SQL is actually executed. Prior to flushing, the application might not know that two entities violate a unique constraint or foreign key.

Unique key example:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uk_orders_external_ref UNIQUE (external_ref);
~~~

Two items sharing the same `external_ref` can be persisted into the persistence context. On flush, the database executes `INSERT` and detects the duplicate key.

The exception may be wrapped as a `PersistenceException`, provider `ConstraintViolationException`, or translated by Spring into `DataAccessException` depending on the stack.

Explicit flushing surfaces errors directly inside the writer. Yet if the database uses deferred constraints, some checks still complete only at commit time. Do not treat a successful flush as proof that all constraints are satisfied.

## 14. Flush and optimistic locking

Entities use `@Version` to detect concurrent updates:

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

When flushing an `UPDATE`, the provider typically includes the old version in the `WHERE` clause and increments the version if the update succeeds.

Conceptual SQL example:

~~~sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
~~~

If another transaction updated the entity earlier, the updated row count may be 0 and the provider throws an optimistic locking exception at flush or commit.

This is a data-contention error, not a transient connection glitch. Retrying may require reloading the latest entity and reapplying business rules; do not merely replay the same `UPDATE` with the stale version.

## 15. Flush and generated identifiers

When an ID is generated depends on the `@GeneratedValue` strategy and database/provider.

- `SEQUENCE` may fetch sequence values before `INSERT`.
- `IDENTITY` often requires executing `INSERT` for the database to generate the ID, so SQL may execute immediately on `persist`.
- `TABLE` or custom generators have their own semantics.

Therefore, you cannot assume every generated ID appears only after flush. If logic depends on the ID value, understand the strategy in use and test against the real database.

Flushing also does not automatically guarantee that all database-generated or default columns are reflected back onto the object. You may need `refresh()` or appropriate generated-value mapping support if the application needs to read database-assigned values back.

Do not call `refresh` casually for every item, as it issues extra `SELECT` statements and reduces throughput.

## 16. Flush order is not code persist order

The application may call `persist` in a specific order, but the JPA provider does not guarantee SQL is sent in that exact order in every case. The provider can reorder actions for optimization or to satisfy dependencies and constraints.

To ensure parent-child ordering, declare mappings and owning sides properly, apply appropriate cascades, and let the provider sequence SQL from the mappings.

Do not insert `flush()` after every entity as a way to force insert ordering without understanding the root cause. Overly frequent flushing breaks batching and increases round trips.

If special SQL ordering dependencies exist, consider separating operations or designing clear mappings/transactions rather than relying on incidental execution order.

## 17. Flush and JDBC batching

Hibernate and several other JPA providers can group multiple `INSERT`/`UPDATE` statements into JDBC batches. Flush is when the provider drains its action queue and dispatches SQL statements; batching can happen during that process if configuration and SQL shapes allow it.

Influencing factors:

- JDBC batch size.
- ID generation strategy.
- Ordering of inserts/updates.
- Whether entities have `@Version`.
- Driver and database engine.
- Whether `flush()` is called too frequently.

With Hibernate, properties like `hibernate.jdbc.batch_size` and `hibernate.order_inserts` can be tuned for the workload. Benchmark performance and inspect actual SQL rather than turning on every flag blindly.

Flushing after every single item typically destroys the chance to batch statements together. In chunk processing, flushing at chunk end is usually a sensible starting point.

## 18. Flush and clear to bound memory

The persistence context retains references to managed entities for dirty checking. If a Step processes millions of entities without clearing, memory can grow with the number of managed entities.

One strategy in a custom writer is flushing and clearing in groups:

~~~java
int batchSize = 100;

for (int i = 0; i < items.size(); i++) {
    entityManager.persist(items.get(i));

    if ((i + 1) % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
~~~

Flush before clearing so SQL is dispatched. `clear()` detaches all entities from the persistence context. Clearing before flushing can discard unsynchronized changes from the context.

Inside a chunk transaction, multiple flush/clear cycles do not commit separate groups. All SQL remains part of the chunk transaction when using the same `EntityManager`/transaction. If an error occurs before commit, the transaction can still roll back the entire chunk despite multiple flushes.

However, after clearing, entities are detached. Do not continue mutating those entities expecting dirty checking to save changes without merging or persisting them again.

## 19. Clear is not closing EntityManager

`entityManager.clear()` removes all entities from the persistence context and transitions them to detached state. It does not close the `EntityManager` and does not commit the transaction.

`entityManager.close()` terminates the `EntityManager`. With a Spring-managed `EntityManager` inside a transaction, the application should not close it manually.

These operations differ:

| Operation | Effect |
|---|---|
| `flush()` | Sends persistence context changes to the database |
| `clear()` | Detaches all entities from the persistence context |
| `detach(entity)` | Detaches a single entity |
| `refresh(entity)` | Reloads state from the database |
| `close()` | Closes an application-managed `EntityManager` |
| `commit` | Completes the transaction |

Do not call `clear` arbitrarily while processors still rely on managed associations. Clearing can alter lazy relationship or dirty-checking behavior unexpectedly.

## 20. Flushing before queries that must see changes

With `FlushModeType.AUTO`, the JPA provider may flush automatically before a query if pending changes could affect results. However, when explicit ordering is needed, you can call flush explicitly:

~~~java
entityManager.persist(new Order(...));
entityManager.flush();

Long count = entityManager.createQuery(
        "select count(o) from Order o",
        Long.class)
        .getSingleResult();
~~~

A query after flush can observe changes within the same transaction according to transaction semantics and the persistence context.

If a query runs via JDBC on a different connection, visibility depends on transaction, connection, and isolation level. Never assume every query across every API automatically sees uncommitted data.

When using JPQL bulk updates/deletes, note that they act directly on the database and do not synchronize managed entities in the persistence context. Usually you should flush pending changes before bulk operations and clear/refresh afterward to prevent the persistence context from holding stale data.

## 21. Bulk JPQL updates and flush

Bulk update example:

~~~java
entityManager.flush();

int updated = entityManager.createQuery("""
        update Order o
        set o.status = :status
        where o.businessDate = :businessDate
        """)
        .setParameter("status", OrderStatus.EXPIRED)
        .setParameter("businessDate", businessDate)
        .executeUpdate();

entityManager.clear();
~~~

Flushing before a bulk update ensures pending changes are sent before the bulk DML runs. Clearing afterward avoids continuing to use managed entities with stale state.

Bulk JPQL updates do not invoke per-entity dirty checking and do not execute full lifecycle callbacks or cascades like normal entity updates. They may also bypass optimistic locking version increments unless the query updates the version itself.

In Spring Data JPA, `@Modifying(flushAutomatically = true, clearAutomatically = true)` can express a similar policy for repository queries, depending on the Spring Data version.

## 22. Where do flush exceptions surface?

Some errors surface at `persist`/`merge`, some at `flush`, and some only at `commit`.

| Timing | Examples |
|---|---|
| On `persist`/`merge` | Mapping or lifecycle errors, invalid detached/removed state |
| On `flush` | Unique/FK constraints, SQL errors, optimistic locking conflicts |
| On `commit` | Deferred constraints, transaction manager/database commit failures |
| After commit | External system errors or downstream publishing failures |

Not all exceptions are thrown on the line calling `persist`. JPA commonly defers SQL until flush or commit.

If the writer does not flush explicitly, errors can appear during chunk transaction commit. Stack traces may then point to the transaction manager instead of the writer line.

Standard `JpaItemWriter` typically flushes inside `write()`, surfacing many SQL errors inside the writer invocation. Commit-level errors can still occur afterward.

## 23. Handling flush errors in Spring Batch

When `flush` throws an exception, the Step handles it according to transaction and fault-tolerance configuration.

Options:

- Fail the Step if the data error is unrecoverable.
- Retry transient errors that are safe to re-attempt.
- Skip the faulty record if the error maps to a specific item and business rules permit it.
- Record rejected items or audit logs consistently.

Deadlock retry example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Exact exception names and Spring exception translation depend on framework versions. Observe the actual exceptions raised in your application.

Unique constraint violations typically should not be retried if data has not changed. Optimistic locking conflicts require re-reading state and reapplying logic, not merely repeating the stale update.

## 24. Flush and write skip

If one item causes a constraint error while flushing an entire chunk, Spring Batch may need to isolate the failing item via fault-tolerant write/scan behavior. Exact behavior depends on the writer, exception type, and system transaction/rollback capabilities.

Not every flush error can be attributed to a single item. For example, deadlock errors involve multiple transactions; connection errors affect the entire chunk; cross-row constraints arise from interactions across multiple items.

Configure skip only for well-understood exceptions where faulty items can be isolated. Otherwise, skipping can mask chunk-wide errors or produce inconsistent output.

With custom writers, explicitly test mid-chunk flush failure, rollback, and writer re-invocation with subsets when the framework performs write scanning.

## 25. Retry after flush and idempotency

Suppose the writer flushes successfully, then an error occurs before commit. The chunk transaction rolls back and Spring Batch retries the chunk.

Flushed SQL statements within that transaction roll back if they belong to the same transaction. On retry, the writer re-executes the operations. This is normal behavior.

If the writer also triggers external side effects outside the transaction—such as sending an HTTP request before commit—those side effects do not automatically roll back. Retries can send duplicate requests.

For side effects outside the database:

- Use stable idempotency keys tied to the business operation.
- Use a transactional outbox so publishing occurs only after commit.
- Avoid sending notifications directly from a JPA writer.
- Maintain deduplication or reconciliation mechanisms in target systems.

A successful flush is not a safe point to publish irreversible events. Wait for transaction commit or use an outbox.

## 26. Flush and database locks

When SQL executes on flush, the database may acquire row or table locks. Those locks are typically held until commit or rollback depending on database engine and isolation level.

If you flush early and then perform slow work before commit, the transaction holds locks longer. This increases contention, deadlocks, and impact on other transactions.

Ways to reduce lock risk:

- Keep chunk sizes reasonable.
- Avoid calling slow APIs between flush and commit.
- Avoid unnecessary queries or updates within the transaction.
- Index filter predicates properly.
- Maintain consistent row-access order across Jobs.
- Never keep a transaction open waiting on human input or external systems.

Flushing does not release locks. Commit or rollback ends the transaction and releases locks according to database semantics.

## 27. Flush and transaction propagation

A service invoked by the writer may declare `@Transactional` with different propagation modes.

- `REQUIRED` normally joins the current chunk transaction if the transaction manager and resource match.
- `REQUIRES_NEW` suspends the outer transaction and starts a new one.
- `NOT_SUPPORTED` may run outside a transaction.

If a service uses `REQUIRES_NEW` and commits successfully, its changes persist even if the chunk transaction rolls back later.

Do not put `REQUIRES_NEW` on a JPA operation simply to force a flush. Flushing only synchronizes the current persistence context; the transaction manager decides commit/rollback.

If an audit operation must roll back with the chunk, use `REQUIRED` with the same persistence unit and transaction manager. If audit records must survive independently, explicitly model their semantics and reconciliation.

## 28. Flush and multiple EntityManagerFactories

An application may have multiple persistence units or databases. A `JpaTransactionManager` manages only its corresponding `EntityManagerFactory`.

If writer A uses `EntityManagerFactory` 1 and writer B uses `EntityManagerFactory` 2, flushing A does not mean B's changes are flushed or committed in the same transaction.

Even if two persistence units point to the same database, transaction coordination does not happen automatically. Atomicity across multiple resources requires an appropriate coordinating transaction manager (such as JTA/XA where supported and required) or workflow/outbox/saga patterns.

Never call flush on one `EntityManager` and assume every JPA writer in the Job is synchronized.

## 29. Spring Data JPA save, saveAndFlush, and flush

Spring Data JPA repositories expose:

- `save(entity)`: saves or merges an entity; does not necessarily flush immediately.
- `saveAll(entities)`: saves a group of entities; does not necessarily flush immediately.
- `flush()`: synchronizes pending changes in the persistence context.
- `saveAndFlush(entity)`: saves and then flushes.
- `saveAllAndFlush(entities)`: saves a group of entities and then flushes.

`saveAndFlush` still does not commit the transaction. When called inside a chunk transaction, that transaction remains open after the method returns.

Example:

~~~java
repository.save(order);
repository.flush();

// SQL has been sent; the Step transaction can still roll back.
~~~

Do not call `saveAndFlush` for every item just to "make sure it is saved." It can degrade batching and increase synchronization overhead. In a chunk writer, it is usually better to accumulate items and flush once at the chunk boundary when semantics permit.

## 30. Flush and transaction commit in Spring Batch JPA

A typical configuration:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        JpaTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        JpaItemWriter<Order> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Main flow:

1. Spring Batch starts a transaction for the chunk.
2. The reader supplies items.
3. The processor converts inputs into entities.
4. `JpaItemWriter` persists/merges entities.
5. The writer flushes the persistence context.
6. Spring Batch completes required stream/checkpoint updates.
7. The transaction manager commits the chunk.

If flush fails, the chunk transaction rolls back per policy. If commit fails, the transaction is also not considered complete; `JobRepository` and transaction coordination must handle it per Spring Batch configuration.

Do not call `entityManager.getTransaction().commit()` in a processor or writer. That breaks the Step's transaction control.

## 31. Generated columns and refresh after flush

Some databases assign default values or computed/generated columns on `INSERT`/`UPDATE`. Flushing sends SQL, but it does not guarantee the provider automatically populates every generated value back into the entity across all mappings.

For example, a `created_at` column with a database default:

~~~sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

If the application needs to read this value immediately after insert, it may need appropriate generated-property mapping or a `refresh` call:

~~~java
entityManager.persist(order);
entityManager.flush();
entityManager.refresh(order);
~~~

`refresh` executes a `SELECT` to synchronize state from the database. Do not call `refresh` for every entity unnecessarily, as it adds round trips and can hurt throughput.

For generated IDs, timestamps, or computed columns, check your provider/database behavior and mapping annotations to know which values are available after persist, flush, or refresh.

## 32. Flush and lifecycle callbacks

Certain JPA lifecycle callbacks tied to persist/update/remove may run around the time the provider executes SQL operations. For instance, `@PrePersist` and `@PreUpdate` are typically invoked before entity writes, while `@PostPersist` and `@PostUpdate` run after the corresponding operation per lifecycle semantics.

Do not use callbacks as commit hooks for external side effects. Callbacks run within the persistence lifecycle; the transaction can still roll back afterward.

If you need to emit events after commit, use transaction synchronization or a suitable outbox pattern. Never send emails or call APIs from `@PostPersist` assuming data is already committed.

## 33. Flush and bulk insert/update performance

At large scale, performance depends on multiple factors:

- Number of entities per chunk.
- Number of SQL statements executed.
- JDBC batch size.
- Persistence context size.
- Dirty-checking overhead.
- Cascade graphs.
- Indexes and constraints.
- Round trips between application and database.

Key guidelines:

- Start with a moderate chunk size.
- Use JDBC batching where supported by provider and driver.
- Flush per chunk rather than per item.
- Clear after flush when managed entities are no longer needed.
- Avoid overly large cascade graphs.
- Use projections or a JDBC writer if JPA lifecycle features are unnecessary.
- Measure heap, SQL counts, and transaction duration.

JPA is convenient for mapping and domain lifecycle, yet for very large bulk ETL jobs, `JdbcBatchItemWriter` or SQL bulk loading can be much more efficient. Choose based on business needs rather than defaulting to JPA everywhere.

## 34. Testing flush before commit

A test should prove that flushing sends SQL without committing the transaction.

You can use `TransactionTemplate` in an integration test:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    entityManager.persist(new Order(1001L, OrderStatus.NEW));

    entityManager.flush();

    // Same transaction can read flushed changes.
    Order found = entityManager.find(Order.class, 1001L);
    assertNotNull(found);

    status.setRollbackOnly();
});

// Transaction rolled back; query in a new transaction
// must verify the row does not exist.
~~~

This test requires a real transaction manager and properly configured `EntityManagerFactory`. When querying from the same persistence context, entities may be returned from the first-level cache; to verify actual database state, clear the context or query in a separate transaction/connection.

The key verification: after flushing, the transaction can still roll back and no data remains afterward.

## 35. Testing constraint errors at flush

Create a unique constraint in the test database, then persist two entities with duplicate business keys:

~~~java
entityManager.persist(new Order("EXT-100"));
entityManager.persist(new Order("EXT-100"));

assertThrows(
        PersistenceException.class,
        entityManager::flush);
~~~

Exact exception wrapping can vary by Hibernate or provider. In Spring, exception translation may convert it to `DataIntegrityViolationException`.

After a flush failure, the transaction is usually marked rollback-only or unsafe for continued normal execution. Never catch the exception and continue using the same transaction as if nothing happened.

Integration tests should verify chunk rollback and Step status, not merely that an exception was thrown by `EntityManager`.

## 36. Testing JpaItemWriter in a chunk

Run a Step test using `JpaItemWriter`:

- Write a valid chunk.
- Verify the writer flushes entities within the transaction.
- Intentionally trigger a constraint violation in one chunk.
- Verify the failing chunk commits no data.
- Restart the Job if the error is handled under a restart policy.
- Verify previously committed items are not written twice.
- Verify the persistence context does not accumulate unexpected entities.

Do not merely mock `EntityManager` and assert `flush` was called. Mocks do not prove SQL, constraints, or transaction rollbacks actually work.

## 37. Common pitfalls

### Confusing flush with commit

Flushing only synchronizes SQL within the transaction. The transaction can still roll back. Treat data as finalized only after a successful commit.

### Calling flush after every item

This can defeat JDBC batching and increase round trips. Typically flush per chunk or in intentional batches.

### Calling clear before flush

Pending changes may be detached without being synchronized. Flush before clearing.

### Manually committing EntityManager in a writer

Breaks Spring Batch's transaction control. Let the transaction manager handle commits and rollbacks.

### Using a different EntityManagerFactory than the transaction manager

The writer may not participate in the chunk transaction. Use the matching persistence unit and `JpaTransactionManager`.

### Calling merge and continuing to mutate the input object

The object passed to `merge` may stay detached. Use the managed instance returned by `merge` for further edits.

### Assuming all constraints are checked at flush

Deferred constraints may fail only at commit. Test against a real database and understand constraint semantics.

### Assuming generated IDs appear only after flush

ID strategies such as `IDENTITY` may require an immediate `INSERT`. Verify with your provider and database.

### Catching a flush error and continuing the transaction

The transaction may already be rollback-only or unsafe to reuse. Propagate the error to Spring Batch per policy.

### Emitting external events after flush

Flushing is not committing; the transaction can roll back. Use an outbox or publish after commit.

### Changing flush mode arbitrarily

`AUTO` and `COMMIT` have different semantics for queries. Choose the mode based on requirements and test it.

### Leaving persistence context size unbounded

Accumulated managed entities increase heap usage and dirty-checking costs. Use an intentional flush/clear strategy.

## 38. Design workflow for flushing in a JPA writer

Before configuring the writer, determine:

1. Are entities persisted or merged?
2. Are entities managed or detached when they reach the writer?
3. Does `JpaItemWriter` already flush automatically in your version?
4. Does the Step's transaction manager use the matching `EntityManagerFactory`?
5. Is `AUTO` or `COMMIT` flush mode appropriate for queries in the Step?
6. Can constraints and optimistic locking fail at flush or at commit?
7. Are chunk size and JDBC batch size appropriate?
8. Should the persistence context be cleared after flush?
9. Are there bulk JPQL operations needing flush/clear before and after?
10. Are there generated fields requiring `refresh`?
11. Does the writer invoke `REQUIRES_NEW` services or commit manually?
12. Do external side effects wait for commit or use an outbox?
13. Do tests verify rollback after flush and constraint failures?
14. Do restarts keep inputs, reader state, and writer behavior consistent?

Flushing before commit lets JPA synchronize changes and catch many SQL errors within chunk processing. However, flushing does not end the transaction, guarantee durability, or release locks. In Spring Batch, let `JpaItemWriter` or a custom writer flush inside the Step-managed transaction, choose persist/merge according to entity state, bound the persistence context via flush/clear when needed, and test both flush-time and commit-time failures. Treat a chunk as complete only after the transaction commits successfully.
