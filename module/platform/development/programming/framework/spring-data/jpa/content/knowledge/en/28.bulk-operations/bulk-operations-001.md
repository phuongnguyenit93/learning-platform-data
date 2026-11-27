# Distinguishing `saveAll`, JDBC batching, and bulk DML

When you need to write or update thousands of records with Spring Data JPA, three concepts are often confused: `saveAll()`, JDBC batching, and bulk DML. They solve different problems:

- `saveAll()` is a Spring Data JPA API for saving a collection of entities. On its own, it does not mean emitting only a single SQL statement.
- JDBC batching is how Hibernate groups multiple SQL statements of the same shape into a single JDBC batch to reduce database round-trips. JDBC batching can be combined with `saveAll()`.
- Bulk DML is an `UPDATE` or `DELETE` statement that operates directly on multiple rows in the database, typically without loading each entity into the persistence context.

Choosing the right approach depends on whether the business logic needs to process each entity individually, invoke lifecycle callbacks, apply cascades, and keep entity state synchronized, or simply perform a bulk change matching a condition.

## 1. What does `saveAll()` actually do?

`saveAll(Iterable<S> entities)` is a method of `JpaRepository`. In the common `SimpleJpaRepository` implementation, Spring Data JPA iterates over the entities and calls `save()` for each element.

For each entity, `save()` decides whether to call `EntityManager.persist()` or `EntityManager.merge()` based on Spring Data JPA's new-entity detection mechanism:

- Entity detected as new: calls `persist()`.
- Entity detected as already existing: calls `merge()`.

Therefore, `saveAll()` is an operation that saves multiple entities following the JPA model. It does not automatically turn the entire list into a single SQL statement.

Example:

~~~java
@Service
@RequiredArgsConstructor
public class ProductService {
    private final ProductRepository productRepository;

    @Transactional
    public List<Product> createProducts(List<Product> products) {
        return productRepository.saveAll(products);
    }
}
~~~

In this example, each entity is still managed according to JPA's persist/merge rules. SQL is typically emitted when Hibernate flushes the persistence context, such as when the transaction commits or when an operation triggers a flush.

### Notes on persist and merge

`persist()` puts a new entity into the managed state. `merge()` copies the state of the input entity into a managed instance and returns that instance. For a detached entity, the object passed to `save()` may remain detached; use the returned object if you need to continue operating on the managed instance.

Spring Data JPA detects new entities according to `EntityInformation` rules, usually based on a nullable version property or identifier. If an entity uses custom rules, it can implement `Persistable` and provide an appropriate `isNew()`.

Thus, do not look solely at the name `saveAll()` and assume every element is guaranteed to be inserted. A list can contain both new and existing entities, causing some elements to be persisted while others are merged.

## 2. What is JDBC batching?

JDBC batching is a JDBC mechanism that allows grouping multiple executions of a statement with the same shape into one batch. Instead of sending each statement across separate round-trips, the application adds multiple parameter sets to a batch and executes that batch.

Conceptually, for example, the same insert statement is used with multiple sets of values:

~~~sql
INSERT INTO product (id, name, price) VALUES (?, ?, ?)
~~~

Hibernate can group different parameter sets for this statement into one JDBC batch. The database still executes multiple insert operations, but the number of batch transmissions over JDBC can be smaller than the number of records.

JDBC batching is an optimization at the SQL execution layer. It does not change the business semantics of saving entities with JPA: Hibernate still manages entities, dirty checking, mappings, cascades, and lifecycle callbacks according to normal rules.

### Enabling JDBC batching with Hibernate

In a Spring Boot application using Hibernate, you can configure this in `application.properties`:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Meaning:

- `hibernate.jdbc.batch_size`: the maximum number of statements of the same shape that Hibernate groups into one batch before executing. A value of 50 is a starting example for benchmarking, not an optimal number for every database.
- `hibernate.order_inserts`: instructs Hibernate to sort inserts so that statements of the same shape have a better chance of sitting next to each other and batching effectively.
- `hibernate.order_updates`: similarly for updates.

You can set Hibernate properties via `spring.jpa.properties.*` in Spring Boot. If configuring Hibernate directly, use the property names `hibernate.jdbc.batch_size`, `hibernate.order_inserts`, and `hibernate.order_updates`.

JDBC batching must be supported by the provider, JDBC driver, and database. Furthermore, Hibernate cannot effectively group statements with different SQL structures into the same batch. For instance, entities inserted with different sets of columns may produce multiple SQL groups.

### Combining saveAll and JDBC batching

Here is the most important point: `saveAll()` and JDBC batching are not mutually exclusive choices. You can use `saveAll()` to save entities via JPA while configuring Hibernate to batch the SQL statements generated upon flush.

~~~java
@Transactional
public void importProducts(List<Product> products) {
    productRepository.saveAll(products);
    productRepository.flush();
}
~~~

`flush()` synchronizes pending changes in the persistence context to the database. It does not commit the transaction. As long as the transaction remains active, flushed statements can still be rolled back later.

`saveAllAndFlush()` also saves the list and then flushes. This method is convenient when you need to force SQL to be sent to the database before the method ends, but it does not enable JDBC batching on its own and does not clear entities from the persistence context.

### Notes on ID generation strategy

With Hibernate, the primary key generation strategy can directly affect batching:

- `GenerationType.IDENTITY`: Hibernate often has to execute the insert immediately to obtain the database-generated ID. This prevents Hibernate from grouping inserts into a JDBC batch in many cases.
- Sequence generator: typically allows Hibernate to pre-fetch IDs and batch inserts better, depending on the database and sequence configuration.
- Other strategies depend on the provider, database, and implementation.

If insert batching is not working as expected, check the ID generation strategy before simply increasing `batch_size`.

## 3. Why are flush and clear needed when writing large datasets?

Every managed entity is typically held in the EntityManager's persistence context. Hibernate needs to track entity state for dirty checking and related operations. When importing tens of thousands of entities within a single transaction, the persistence context can consume significant memory.

A common approach is to split the list into chunks, save each chunk, flush, and then clear:

~~~java
@Service
@RequiredArgsConstructor
public class ProductImportService {
    private static final int CHUNK_SIZE = 500;

    private final ProductRepository productRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importProducts(List<Product> products) {
        for (int start = 0; start < products.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, products.size());
            List<Product> chunk = products.subList(start, end);

            productRepository.saveAll(chunk);
            productRepository.flush();
            entityManager.clear();
        }
    }
}
~~~

Workflow of each iteration:

1. Take up to 500 entities.
2. Call `saveAll()` to put them through the persist/merge process.
3. Call `flush()` so Hibernate emits pending statements; JDBC batching can group them according to `hibernate.jdbc.batch_size`.
4. Call `clear()` to detach all managed entities in the persistence context, freeing most of the state tracked by the EntityManager.

In the example, the chunk size is 500 while the JDBC batch size is 50. The two values serve two different purposes: chunk size controls how many entities are held in the persistence context; batch size controls how many statements of the same shape are grouped into a JDBC batch.

### Flush is not commit

This is a distinction to remember:

| Operation | Meaning |
|---|---|
| `saveAll()` | Puts entities into the persist/merge process |
| `flush()` | Synchronizes pending changes to the database |
| `clear()` | Detaches all entities from the persistence context |
| Commit | Completes the transaction; changes are confirmed |
| Rollback | Cancels changes belonging to the transaction |

In the chunk example above, the entire loop remains inside a single transaction because the method has `@Transactional`. Flushing and clearing per chunk helps control memory, but does not create a separate commit for each chunk. The transaction can still span until the end of the method and hold locks for a long time.

If you want each chunk to commit independently, you must design separate transaction boundaries, such as calling another bean with an appropriate `@Transactional` method or using `TransactionTemplate`. This changes atomicity: if a later chunk fails, previously committed chunks may still be retained. Only choose this approach when the business requirements accept partial processing.

After calling `clear()`, all previous entities become detached. If you still need to modify them, you must reload or merge them appropriately. Do not keep references to old entities and assume they are still managed by the EntityManager.

## 4. What is bulk DML?

Bulk DML is a statement that operates directly on multiple database rows based on a condition, typically `UPDATE` or `DELETE`. With Spring Data JPA, a common approach is to use `@Modifying` together with `@Query`.

For example, instead of loading each expired product into Java, modifying a property, and saving it back, you can update them directly with a JPQL statement:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Product p
           set p.active = false
         where p.lastPurchasedAt < :cutoff
        """)
    int deactivateBefore(@Param("cutoff") Instant cutoff);
}
~~~

The service calls the repository within a transaction:

~~~java
@Service
@RequiredArgsConstructor
public class ProductMaintenanceService {
    private final ProductRepository productRepository;

    @Transactional
    public int deactivateExpiredProducts(Instant cutoff) {
        return productRepository.deactivateBefore(cutoff);
    }
}
~~~

The JPQL statement above instructs the database to update matching rows in a single DML operation. The return value is the number of entity instances affected according to the provider/database execution result.

Bulk delete is written similarly:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    delete from Product p
     where p.active = false
       and p.lastPurchasedAt < :cutoff
    """)
int deleteInactiveBefore(@Param("cutoff") Instant cutoff);
~~~

In Spring Data JPA, `@Modifying` tells Spring that the query declared with `@Query` is a data-modifying operation rather than a normal read query. The method must be executed within an active transaction; `@Transactional` can be placed on the service as in the example above.

Standard JPQL bulk DML focuses on `UPDATE` and `DELETE`. If you need bulk inserts such as `INSERT ... SELECT`, check the capabilities of Hibernate HQL, native SQL, or JDBC because that is not standard JPQL insert syntax.

## 5. How does bulk DML differ from saving entities individually?

Bulk DML is usually fast when changing many rows according to the same rule, but it bypasses a large part of JPA's entity management mechanisms.

When executing a bulk update/delete:

- JPA does not load each affected entity into the persistence context.
- Dirty checking on individual entities is not run to generate statements for that bulk operation.
- Entity lifecycle callbacks such as `@PreUpdate`, `@PostUpdate`, `@PreRemove`, and corresponding listeners are not invoked for each affected entity.
- Cascade remove and `orphanRemoval` are not applied as they are when deleting entities through EntityManager.
- Managed entities already in the persistence context may still contain stale values.
- `@Version` properties are not automatically incremented as in normal entity updates; if needed, version updates must be designed explicitly.

The database still enforces constraints, triggers, and database-level rules according to its configuration. What is bypassed here are JPA's entity lifecycle mechanisms, not all database logic.

### Example of a stale persistence context

Suppose a service has already loaded a product:

~~~java
Product product = productRepository.findById(10L).orElseThrow();
boolean oldActiveValue = product.isActive();
~~~

Then a bulk query updates `active = false` for that product. The `product` object sitting in the persistence context may still return the old `active` value, because bulk DML runs directly at the database and does not update each managed object.

If the application continues reading or modifying the old entity, it may work with out-of-sync state. You can use `clearAutomatically = true` so Spring Data JPA clears the persistence context after the query, or explicitly call `EntityManager.clear()` or `refresh()` depending on the situation.

### Role of flushAutomatically and clearAutomatically

The two attributes in `@Modifying` address two different moments:

- `flushAutomatically = true`: flushes the persistence context before executing the query. Pending JPA changes are sent to the database before bulk DML runs.
- `clearAutomatically = true`: clears the persistence context after the query executes to avoid continuing to use managed entities that may have become stale.

Clear affects the entire persistence context of the current EntityManager, not just the entities affected by the query. Other entities are also detached. Therefore, only enable automatic clearing when the processing flow understands that consequence.

If you do not clear automatically, you can explicitly flush, then execute the bulk DML, and afterward refresh or clear the necessary entities. Choose an explicit state synchronization strategy rather than assuming bulk queries automatically update Java objects.

## 6. Bulk DML and @Version, auditing, cascade

Bulk DML does not go through the normal entity update pipeline. Several business consequences must be handled separately.

### Optimistic locking with @Version

When updating an entity through JPA, the provider can use the version column to check and increment the version. Bulk JPQL updates do not automatically perform that full process.

If you need to increment the version in a bulk update, you can include the increment in the query:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update Product p
       set p.active = false,
           p.version = p.version + 1
     where p.lastPurchasedAt < :cutoff
    """)
int deactivateBefore(@Param("cutoff") Instant cutoff);
~~~

This is only an illustrative example. If optimistic locking needs to be guaranteed per record, the query must also include an appropriate version condition and the application must handle the affected row count. Incrementing versions in bulk should not be treated as fully equivalent to per-entity version checking.

### Auditing and lifecycle callbacks

Fields updated through entity listeners, such as `@LastModifiedDate`, are not automatically populated just because a bulk query changes data in bulk. If the business logic needs to update modification timestamps or modifiers, include those values directly in the query or handle them at the database layer according to your chosen policy.

Similarly, `@PreUpdate` and `@PreRemove` listeners do not run for each entity in bulk DML. If a listener holds mandatory logic, switching to a bulk query can lose that behavior.

### Cascade and bulk deletion

Normal entity deletion via `EntityManager.remove()` can trigger cascade remove and orphan removal according to the mapping. Bulk JPQL delete does not call `remove()` on each entity, so those mechanisms are not applied. Ensure relationships are handled appropriately using separate statements, foreign key constraints, or normal entity deletion.

## 7. Derived delete queries vs. bulk delete

Spring Data JPA can derive a delete method from the method name, for example:

~~~java
void deleteByActiveFalseAndLastPurchasedAtBefore(Instant cutoff);
~~~

A derived delete query like this can query the matching entities and then delete each entity individually so that lifecycle callbacks can be invoked. That approach can consume more memory and operations when the record count is large.

Meanwhile, a method using `@Modifying` and JPQL `delete` is bulk DML, executing a direct delete statement by condition without calling lifecycle callbacks for each entity.

In addition, `JpaRepository` provides batch delete methods such as `deleteAllInBatch()` or `deleteAllByIdInBatch()`. They also perform bulk deletion at the database and carry similar persistence context synchronization caveats as bulk operations. Read the method contract carefully before using them in place of normal entity deletion.

## 8. Comparing the three approaches

| Criterion | `saveAll()` | JDBC batching | Bulk DML |
|---|---|---|---|
| Operating layer | Spring Data JPA API | JDBC/provider layer | Direct JPQL or SQL |
| Target processed | Entities | Multiple SQL statements of the same shape | Multiple rows by condition |
| Requires loading entities | Yes, via persist/merge pipeline | Usually yes when combined with JPA | No need to load each entity |
| Number of SQL statements | Can be many statements | Multiple statements grouped into batches | Usually one DML statement per query |
| Lifecycle callbacks | Yes, per JPA pipeline | Yes when using JPA entities | Not invoked per entity |
| JPA cascade | Per mapping | Per mapping when using JPA | Does not run like entity operations |
| Persistence context sync | JPA manages entities | JPA manages entities | Must handle stale state manually |
| Best suited for | Saving multiple entities needing JPA semantics | Optimizing entity saves/updates in batches | Updating/deleting datasets by condition |

The key point: JDBC batching can be used together with `saveAll()`. Bulk DML is a different strategy, trading off some entity semantics to perform direct and efficient changes at the database.

## 9. Which option to choose in practice?

**Choose `saveAll()` when:**

- You have a list of entities to save according to JPA mappings.
- You need cascade persist/merge or lifecycle callbacks.
- You need to use entity values and relationships within the business flow.
- The number of entities is moderate or can be chunked to manage memory.

**Combine `saveAll()` with JDBC batching when:**

- You still need JPA semantics but want to reduce SQL round-trips.
- Many entities produce SQL statements of the same shape.
- The provider, JDBC driver, and ID strategy support batching.
- You have measured and confirmed that batch configuration improves processing time.

**Choose bulk DML when:**

- You need to update or delete many rows according to a simple condition.
- You do not need to load individual entities and do not need per-entity lifecycle callbacks.
- Version, auditing, cascades, and persistence context state have been explicitly handled.
- You can thoroughly test the impact of the direct query on data.

For example, importing 20,000 new products is usually a good fit for `saveAll()` combined with JDBC batching and chunked flush/clear. Conversely, deactivating all products not purchased in 2 years may fit a JPQL bulk update, provided the business logic does not depend on per-product callbacks.

## 10. Verifying batching and performance

Do not conclude that batching is active just because you configured `hibernate.jdbc.batch_size`. Verify it in practice using Hibernate logs appropriate for your version, Hibernate statistics, or JDBC observation tools like datasource-proxy/P6Spy.

Metrics to measure:

1. Actual number of SQL insert/update/delete statements.
2. Number of batch executions and statements per batch.
3. Overall duration and database wait time.
4. Heap usage during large data imports.
5. Transaction duration and lock hold time.
6. Correctness of data, callbacks, cascades, versions, and auditing.

You can enable Hibernate statistics in test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics help observe Hibernate's activity, but do not replace measuring at the JDBC driver or database level. Disable statistics if not needed in production because collecting metrics also carries overhead.

Do not increase the batch size indefinitely. Excessively large batches can increase memory usage, flush time, or pressure on the driver/database. Test a few values, measure on data and a database close to the real environment, and choose based on the results.

## 11. Checklist before deploying bulk operations

- Determine whether you need to save entities with JPA semantics or simply update/delete rows by condition.
- If using `saveAll()`, verify new/existing entities and persist/merge behavior.
- If using JDBC batching, check Hibernate version, JDBC driver, database, and ID generation strategy.
- Set batch size and chunk size for their two separate purposes.
- For large datasets, consider flush/clear to bound the persistence context.
- Remember that flush/clear does not commit; a transaction can still be very long.
- For bulk DML, verify callbacks, cascades, orphan removal, auditing, and `@Version`.
- Handle stale persistence context after bulk update/delete.
- Verify affected row counts and data constraints.
- Write integration tests and measure performance before applying at production scale.

## Conclusion

`saveAll()` is Spring Data JPA's API for saving multiple entities; it typically invokes persist or merge for each entity. JDBC batching is a JDBC-layer optimization that can be combined with `saveAll()` to group SQL statements of the same shape. Bulk DML performs updates/deletes directly on a set of database rows, which is faster and uses less memory in many cases but bypasses lifecycle callbacks, cascades, and entity synchronization in the persistence context. Choose based on the business semantics you need to preserve, then verify batching and performance with real measurements.
