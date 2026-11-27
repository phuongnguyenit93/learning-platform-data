# FlushModeType.AUTO, COMMIT, and Their Impact on Queries in Spring Data JPA

In JPA, **flush** is the process of synchronizing changes currently managed in the persistence context into SQL statements sent to the database. **Commit** is the operation that confirms the transaction. These two concepts are not the same: a transaction can flush multiple times yet remain uncommitted and still able to roll back.

`FlushModeType.AUTO` and `FlushModeType.COMMIT` control when the provider must synchronize changes before executing a query. Choosing the flush mode affects whether queries see uncommitted changes in the persistence context, how many times SQL is issued, when constraint errors surface, and performance.

This document uses Jakarta Persistence (`jakarta.persistence`) in Spring Boot 3 / Spring Framework 6 and later. For older Spring Boot 2 projects, the JPA package is typically `javax.persistence`.

## 1. Persistence context and flush

The persistence context is the scope within which JPA manages entity instances. An entity can be in one of the following states:

- **New/transient:** a new Java object, not yet managed.
- **Managed:** currently tracked by the persistence context; property changes can be detected by dirty checking.
- **Detached:** previously managed, but now separated from the persistence context.
- **Removed:** marked for deletion and will be synchronized on flush.

Example:

```java
Product product = entityManager.find(Product.class, 10L);
product.setPrice(new BigDecimal("125.00"));
```

If `product` is managed, JPA recognizes that the price property has changed. Normally there is no need to call `save()` or `merge()` just to update a managed entity. The provider will generate a SQL UPDATE on flush.

Flush can generate:

- INSERT for newly persisted entities.
- UPDATE for modified managed entities.
- DELETE for removed entities.
- Constraint checks and corresponding database errors.

Flush **does not end the transaction**. After flush, changes have been sent to the database within the current transaction but are not yet committed. The transaction can still roll back; if rollback succeeds, uncommitted changes do not become durable data.

## 2. The two standard JPA FlushModeTypes

Jakarta Persistence defines two portable values:

| Flush mode | Core meaning | Behavior during queries |
|---|---|---|
| `AUTO` | The provider must ensure query results reflect changes in the persistence context that could affect those results | The provider may flush before the query or use another means to ensure accurate results |
| `COMMIT` | The provider must flush before transaction commit | The effect of unflushed changes on query results is unspecified; do not rely on queries seeing those changes |

### 2.1. AUTO

`AUTO` is the default JPA flush mode for an EntityManager/query unless configured otherwise. When executing a query, the provider must ensure the query sees changes in the persistence context that could affect the result.

The provider can accomplish this by flushing before the query. The specification does not require every provider to send SQL before every query; what is required is that query results have semantics consistent with relevant changes in the persistence context.

Example: changing a product's status from active to inactive, then querying the list of active products. The query must reflect the change just made if that change affects the result.

### 2.2. COMMIT

`COMMIT` requires the provider to flush before committing the transaction. Before that point, the application must not assume queries will see unflushed changes.

With COMMIT:

- The provider can defer UPDATE/INSERT/DELETE closer to commit.
- Queries may read database data that does not yet reflect pending changes in the persistence context.
- The provider may still flush early for internal reasons; COMMIT is not a promise of "no flush until commit."
- Query results when unflushed changes exist are unspecified by JPA. Do not write business logic that depends on whether a query sees or does not see those changes.

Thus, COMMIT can reduce unnecessary flushes in some flows, at the cost of the application having to control explicitly when synchronization is needed.

## 3. How does AUTO affect queries?

Suppose the product table has three active products. In one transaction, the application disables one product and then counts active products:

```java
@Transactional
public long deactivateAndCount(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setActive(false);

    return entityManager.createQuery("""
        select count(p)
        from Product p
        where p.active = true
        """, Long.class)
        .getSingleResult();
}
```

With `AUTO`, because modifying `Product.active` can affect a query reading Product, the provider must ensure the query reflects that change. A common approach is flushing the UPDATE before the SELECT:

```sql
select id, name, active
from product
where id = ?;

update product
set active = false
where id = ?;

select count(p.id)
from product p
where p.active = true;
```

If there were initially three active products, the count after disabling one is two.

This is illustrative SQL. Actual SQL also depends on the dialect, mapping, how the provider hydrates entities, and query optimizations.

### 3.1. Queries unrelated to modified entities

Suppose the persistence context has a dirty Product, but the application queries an unrelated AuditLog table. The provider can tell that the Product change does not affect the AuditLog query result and does not need to flush before that query.

Hibernate typically uses the concept of query spaces to determine which tables a query depends on. If a query does not intersect tables with pending changes, Hibernate can skip flushing. This is a provider optimization; do not interpret AUTO as always flushing before every SELECT.

When a query JOINs Product or depends on Product data in a way the provider recognizes, a flush may be required.

## 4. How does COMMIT affect queries?

You can set the flush mode on the EntityManager:

```java
@Transactional
public long deactivateAndCount(Long id) {
    entityManager.setFlushMode(FlushModeType.COMMIT);

    Product product = entityManager.find(Product.class, id);
    product.setActive(false);

    return entityManager.createQuery("""
        select count(p)
        from Product p
        where p.active = true
        """, Long.class)
        .getSingleResult();
}
```

In this example, the query runs before commit. Because the flush mode is COMMIT, JPA does not guarantee the query reflects the unflushed active=false change. The provider may return results based on committed database data, or flush early for implementation reasons. The application must not rely on one specific outcome.

If business logic requires the query to see pending changes, you can call an explicit flush:

```java
entityManager.flush();

long count = entityManager.createQuery("""
    select count(p)
    from Product p
    where p.active = true
    """, Long.class)
    .getSingleResult();
```

After explicit flush, the UPDATE has been sent within the current transaction before the SELECT. The transaction is still uncommitted. If an exception later triggers rollback, the UPDATE can still be rolled back.

## 5. Setting flush mode on EntityManager and Query

### 5.1. EntityManager.setFlushMode

```java
entityManager.setFlushMode(FlushModeType.AUTO);

// Or:
entityManager.setFlushMode(FlushModeType.COMMIT);
```

This sets the mode for the current EntityManager. Queries created from that EntityManager use that mode unless individually overridden.

### 5.2. Query.setFlushMode

You can override the mode for a specific query:

```java
TypedQuery<Long> query = entityManager.createQuery("""
    select count(p)
    from Product p
    where p.active = true
    """, Long.class);

query.setFlushMode(FlushModeType.AUTO);

Long count = query.getSingleResult();
```

This is useful when the EntityManager is using COMMIT, yet a specific query requires AUTO semantics. Conversely, you can set COMMIT on a query that does not need changes synchronized before reading, if business logic accepts not seeing unflushed changes.

Do not change the EntityManager-wide flush mode arbitrarily inside a shared service. If the EntityManager is shared across the transaction, that mode can affect subsequent queries in the same persistence context. When only one query needs adjustment, prefer configuring that query.

## 6. AUTO and COMMIT in Hibernate

Hibernate implements JPA and can optimize flushing based on the tables a query uses. Several points to understand:

- With JPQL/HQL, Hibernate usually knows the query spaces and can flush if pending changes intersect tables the query needs to read.
- Queries reading only unrelated tables may not trigger a flush.
- Native SQL is harder to analyze for table dependencies than JPQL. Flush behavior can depend on the API used, synchronization/query-space metadata, and Hibernate version.
- Calling `EntityManager.flush()` is the explicit way to require synchronization before a native query that needs the latest data in the transaction.
- Do not infer from a single SQL observation that every provider or version will follow the exact same flush schedule.

Hibernate also has its own flush modes beyond JPA's two portable modes, such as `MANUAL` or `ALWAYS` depending on the API/version. These are provider extensions; code requiring portability across JPA providers should use `FlushModeType.AUTO` and `FlushModeType.COMMIT`.

## 7. AUTO does not mean flushing before every query

A common misconception is that every time you call a repository or run a SELECT, Hibernate always sends all pending changes to the database. That is inaccurate.

Example:

```java
@Transactional
public void updateAndRead(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.setPrice(new BigDecimal("125.00"));

    // Query reads the audit_log table, unrelated to Product.
    Long auditCount = entityManager.createQuery(
        "select count(a) from AuditLog a", Long.class
    ).getSingleResult();
}
```

Hibernate may skip flushing Product before the AuditLog query if query spaces do not overlap. However, when a query reads Product, flushing may be required to ensure accurate results under AUTO.

The core point is that AUTO guarantees query semantics, while the exact flush mechanism and timing are implementation details. Do not write logic relying on an exact SQL statement count unless you have pinned the provider/version and tested it.

## 8. Explicit flush: when is it needed?

Explicit flush is useful when you need to:

1. Detect NOT NULL, UNIQUE, FK, or optimistic locking errors early before the service method ends.
2. Ensure a subsequent query reads changes just made in the same transaction.
3. Control write ordering in a workflow that needs SQL outcomes before the next step.
4. Process batches where flush and clear are needed to bound the persistence context.

Example:

```java
@Transactional
public void createAndVerify(String sku) {
    Product product = new Product(sku);
    entityManager.persist(product);

    entityManager.flush();

    boolean exists = entityManager.createQuery("""
        select count(p) > 0
        from Product p
        where p.sku = :sku
        """, Boolean.class)
        .setParameter("sku", sku)
        .getSingleResult();

    if (!exists) {
        throw new IllegalStateException("Product was not persisted");
    }
}
```

This is an illustrative example; boolean return types in JPQL and providers should be verified for your version. In practice, you can use a query returning a count or an appropriate repository query.

Flush can throw exceptions due to constraints or optimistic locking. When an error occurs, the transaction may already be marked rollback-only. Do not continue using that transaction as if it were still valid.

Do not call flush after every `persist` or `setX` just "to be safe." Flushing typically incurs extra round trips and forfeits batching opportunities.

## 9. Flush and commit: lifecycle within a transaction

A transaction can proceed as follows:

```text
BEGIN
  |
  |-- load entity
  |
  |-- modify managed entity
  |
  |-- query (AUTO may flush if changes affect query)
  |
  |-- explicit flush (if requested by application)
  |
  |-- further modifications
  |
  |-- COMMIT
        |
        |-- provider flushes remaining changes
        |-- database commits
        |-- transaction-scoped persistence context ends
        |-- connection returned to pool
```

Key points to remember:

- Flush sends SQL; commit confirms the transaction.
- A transaction can flush multiple times.
- Rollback after flush still discards uncommitted changes.
- Constraint errors can surface at flush or commit.
- Commit typically triggers a final flush for remaining changes.
- A transaction-scoped persistence context ends with the transaction; entities retained outside become detached.

## 10. Spring Data JPA repositories and flush

Spring Data JPA repositories commonly expose methods such as:

- `save(entity)`: persists or merges depending on whether the entity is recognized as new or existing.
- `saveAndFlush(entity)`: saves and requests an immediate flush.
- `flush()`: requests flushing the persistence context.
- `delete(entity)`: marks/handles deletion via the repository and EntityManager.
- `deleteAllInBatch()`: can execute a bulk operation, with different semantics from deleting entity by entity.

`save()` does not mean SQL was sent immediately. Within a transaction, changes can be flushed later. `saveAndFlush()` provides early synchronization but does not commit the transaction.

Example:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product create(Product product) {
        return repository.saveAndFlush(product);
    }
}
```

Only use saveAndFlush when you need a specific flush point, such as catching a constraint violation right inside the method or ensuring a subsequent query sees the change. Otherwise, save is usually sufficient and lets the provider optimize.

## 11. Bulk JPQL update/delete and the persistence context

Bulk update/delete operations have special behavior: they execute directly against the database, bypassing each entity's lifecycle such as normal dirty checking. The persistence context may still hold stale entities.

Example:

```java
@Modifying
@Query("""
    update Product p
    set p.active = false
    where p.expiredAt < :now
    """)
int deactivateExpired(@Param("now") Instant now);
```

After the query runs, a Product already managed in the persistence context may still hold `active = true` even though the database updated it to false. You must synchronize/clear the persistence context when appropriate.

Spring Data JPA supports:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Product p
    set p.active = false
    where p.expiredAt < :now
    """)
int deactivateExpired(@Param("now") Instant now);
```

- `flushAutomatically = true`: flushes the persistence context before executing the modifying query so pending changes are not missed.
- `clearAutomatically = true`: clears the persistence context after the query so stale managed entities are not used with outdated state.

Understand that clearing detaches all entities in the current persistence context. Unflushed changes can be lost from the context, so flush before clearing if those changes need to be kept.

Bulk updates also do not automatically execute full cascades, entity callbacks, and dirty checking as individual entity updates do. If there is a version field, pay attention to optimistic locking/versioning because bulk queries may have to update the version explicitly by design.

## 12. Read-only transactions and flush mode

In Spring, `@Transactional(readOnly = true)` expresses a read-only transaction as a hint to the transaction manager/provider. With Hibernate, Spring can optimize flush behavior, such as setting an appropriate flush mode or marking entities read-only depending on configuration/version.

Do not treat readOnly=true as a security mechanism or an absolute database barrier preventing all writes. It is also not synonymous with JPA `FlushModeType.COMMIT` in every configuration. Check logs and actual transaction manager/provider settings if flush behavior changes.

Do not put readOnly=true on a service method and then write data expecting dirty checking to always flush like a normal write transaction. Separate read and write transactions clearly.

## 13. Performance: choosing AUTO or COMMIT?

Neither mode is universally faster. AUTO may flush early before relevant queries, creating extra round trips mid-flow. COMMIT may defer flushes and coalesce changes, but queries before commit have no guarantee of seeing pending changes under JPA semantics.

| Scenario | Typically suitable mode/action | Notes |
|---|---|---|
| Modifying entities then running a query affected by changes | AUTO | Ensures the query reflects relevant changes |
| Only performing many writes and committing, no intermediate queries | COMMIT may be suitable | Use only when not relying on queries reading pending changes |
| One specific query must see just-modified changes | AUTO for the query or explicit flush | Explicit flush synchronizes all pending changes in the context |
| Large-volume batch writes | Control flush/clear per batch | Do not flush too frequently; configure batching |
| Bulk JPQL update/delete | Flush before and clear after if needed | Avoids persistence context holding stale entities |
| Query reading unrelated tables | Provider may skip flush in AUTO | Depends on query spaces and provider |

A better optimization than changing the flush mode globally is often reducing unnecessary managed entities, using projections, grouping changes sensibly, and flushing only at meaningful boundaries.

## 14. Configuring logging to observe flushes

With Hibernate in Spring Boot, you can configure in development environments:

```properties
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.level.org.hibernate.orm.transaction=DEBUG
```

Logger names may differ across Hibernate versions. Bind logging can expose personal data, tokens, emails, or payment information; enable it only in safe environments and turn it off once diagnosis is complete.

When reading logs, distinguish:

- Query SQL SELECTs.
- SQL INSERT/UPDATE/DELETE issued by flushes before queries.
- End-of-transaction SQL.
- COMMIT/ROLLBACK.
- Connection acquisition/release.

Do not rely solely on `show-sql` console output to conclude a transaction committed. SQL appearing in logs may still belong to an uncommitted transaction.

## 15. Testing flush semantics

Test with a database compatible with production, especially when behavior depends on Hibernate, native queries, constraints, and transactions.

Example testing AUTO with a related JPQL query:

```java
@DataJpaTest
class FlushModeTest {
    @Autowired
    private TestEntityManager testEntityManager;

    @Test
    void autoFlushMakesPendingChangesVisibleToRelatedQuery() {
        Product product = new Product("SKU-1", true);
        testEntityManager.persistAndFlush(product);

        product.setActive(false);

        Long activeCount = testEntityManager.getEntityManager()
            .createQuery("""
                select count(p)
                from Product p
                where p.active = true
                """, Long.class)
            .getSingleResult();

        assertThat(activeCount).isZero();
    }
}
```

This example assumes the Product constructor and getters/setters match the project. Spring Boot test's TestEntityManager helps manipulate the persistence context. The JPQL query reads the same entity space, so AUTO must ensure the result reflects the relevant change.

With COMMIT, do not write tests asserting that a query always returns old values or always returns new values when pending changes are unflushed; JPA leaves that result unspecified. If the application needs fresh results, call flush explicitly or use AUTO for the query.

Additional tests to include:

- Constraint violations surface at flush/commit as expected.
- Rollback after flush leaves no committed data.
- Queries on unrelated tables do not cause unnecessary flushes if the provider optimizes as expected.
- Bulk updates do not leave the persistence context stale after clearing.
- Repository `save()` and `saveAndFlush()` differ in when SQL is sent, yet neither commits an enclosing transaction by itself.

## 16. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Query returns results not reflecting unflushed changes | Using COMMIT and query runs before commit | Use AUTO or explicit flush before the query |
| SQL UPDATE appears before SELECT | AUTO needs to ensure the query sees relevant changes | This can be correct behavior; inspect query spaces |
| AUTO flushes more often than expected | Queries depend on tables with pending changes | Use projections/different queries if suitable; measure SQL before changing mode |
| Constraint error surfaces at a query | AUTO triggered a flush before the query | Check entity state, validation, and database constraints |
| Assuming save() wrote SQL immediately | Save only places the entity into the appropriate lifecycle; flush can be deferred | Use saveAndFlush/flush when truly needed |
| Thinking flush is commit | Confusing SQL synchronization with transaction confirmation | Understand transaction boundaries; rollback can still occur after flush |
| Stale entities after bulk update | Bulk JPQL bypasses synchronizing entities in the persistence context | Flush before and clear after when appropriate |
| Data read in readOnly transaction differs from expectations | Provider optimizes flush per read-only hint | Do not write in read-only transactions; check Hibernate settings |
| SQL bind logs leak data | TRACE enabled in an unsafe environment | Restrict log access and disable bind logging |

## 17. Selection and review checklist

- [ ] Does the query need to see unflushed changes in the persistence context?
- [ ] Does the query depend on tables where entities are dirty?
- [ ] Does AUTO cause unnecessary early flushes in a measured workload?
- [ ] Is COMMIT safe for business flows that do not query pending changes?
- [ ] Can Query.setFlushMode be used instead of changing the entire EntityManager's mode?
- [ ] Does an explicit flush have a clear reason and transaction control?
- [ ] Is anyone confusing flush with commit or SQL logs with committed data?
- [ ] Do bulk JPQL updates/deletes flush/clear at the right time?
- [ ] Are read-only transactions genuinely read-only?
- [ ] Do integration tests verify semantics on the production provider/database?
- [ ] Are SQL, bind parameter, and transaction logs enabled safely and only when needed?

## 18. Conclusion

`AUTO` requires the provider to ensure queries reflect unflushed changes that could affect results; the provider may flush before a query or use another mechanism. `COMMIT` requires flushing before commit, while the effect of unflushed changes on query results is unspecified by JPA.

Use AUTO when queries need consistent semantics with the persistence context. Use COMMIT when write flows do not rely on intermediate queries seeing unflushed changes and have been tested. When explicit synchronization is needed before an operation, explicit flush is the direct choice, though it does not commit the transaction. Optimizing flush mode must be based on SQL logs, transaction boundaries, and real benchmarks, not on the assumption that COMMIT is always faster than AUTO.