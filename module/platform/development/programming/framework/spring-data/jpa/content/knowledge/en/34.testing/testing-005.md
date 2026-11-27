# Using flush and clear to Verify Actual Data in the Database

## 1. Why Do JPA Tests Need flush and clear?

When testing a repository, a test can save an Entity and read it back immediately and get the exact values, even if no SQL INSERT/UPDATE statement was ever sent to the database. The reason is that JPA holds the Entity in the first-level cache, also known as the persistence context.

The persistence context tracks managed Entities. For the same Entity type and ID, a single persistence context normally holds only one managed instance. When calling `find()` or repository `findById()` again, JPA can return the already-managed instance without querying the database.

This benefits the application but can produce misleading test results when the goal is to verify that data was genuinely written to the database or to check mappings upon reloading.

Two operations to understand clearly:

- `flush()` synchronizes pending changes in the persistence context as SQL statements sent to the database.
- `clear()` detaches all managed Entities from the current persistence context, forcing the next Entity read to go through reloading.

The common sequence in integration tests is:

```text
persist/save
    -> flush()
    -> clear()
    -> find/read again
    -> assert
```

## 2. What Does flush() Do?

`EntityManager.flush()` instructs JPA to synchronize pending changes with the database inside the current transaction. Depending on Entity state, the provider may issue INSERT, UPDATE, or DELETE statements.

```java
entityManager.persist(order);
entityManager.flush();
```

Before `flush()`, a new Entity may exist only inside the persistence context. After `flush()`, the corresponding SQL has been sent and executed within the database transaction.

Important: **flush is not commit**. The transaction remains open and can roll back. Other transactions ordinarily do not yet see uncommitted changes depending on database isolation.

`flush()` can also expose database errors earlier, for example:

- Unique constraint or foreign key violations.
- NULL values in NOT NULL columns.
- Invalid data types or column lengths.
- SQL errors from mappings or generated statements.

For constraints deferred by the database until the end of the transaction, errors may still only appear at commit. Therefore, flush does not replace commit testing when business logic depends on commit outcomes.

## 3. What Does clear() Do?

`EntityManager.clear()` detaches all managed Entities from the current persistence context.

```java
entityManager.clear();
```

After clearing:

- Java objects held by your code still exist in memory.
- Those objects are no longer tracked by JPA in the cleared persistence context.
- Subsequent modifications on detached objects are not automatically written to the database.
- The next `find()` must fetch a fresh managed instance into the persistence context.

`clear()` does not delete rows from the database, nor does it clear the second-level cache. It only empties the first-level cache of the current `EntityManager`.

If you only want to detach a single Entity, use `entityManager.detach(entity)`. If you want to reload database state into an Entity that stays managed, consider `entityManager.refresh(entity)` instead of clearing the entire context.

## 4. Why Must You flush Before clear?

Order is critical. If you clear before flushing, unsynchronized changes can be lost from the persistence context and never sent to the database.

```java
// Correct: send pending changes to the database first.
entityManager.flush();
entityManager.clear();

// Reload after the persistence context has been cleared.
PurchaseOrder reloaded = entityManager.find(PurchaseOrder.class, orderId);
```

Do not use the reverse order:

```java
// Dangerous: unflushed changes can be dropped when clear detaches the Entity.
entityManager.clear();
entityManager.flush();
```

In the wrong snippet, after `clear()`, the persistence context no longer manages the modified Entity; the subsequent `flush()` no longer has those changes to synchronize. Therefore, always flush before clear if the goal is to save changes and then read them back.

## 5. Integration Test With EntityManager

Example Entity with an order status:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Test using `flush()` then `clear()` before reading back:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void readsPersistedStateAfterFlushAndClear() {
        PurchaseOrder order = new PurchaseOrder();
        order.setStatus(OrderStatus.PENDING);

        PurchaseOrder saved = repository.save(order);
        entityManager.flush();
        Long id = saved.getId();

        entityManager.clear();

        PurchaseOrder reloaded = repository.findById(id).orElseThrow();
        assertEquals(OrderStatus.PENDING, reloaded.getStatus());
    }
}
```

This is an illustrative integration test; appropriate constructors or factories for the Entity, the `OrderStatus` enum, schema, and JUnit/Spring Test imports are needed. `@DataJpaTest` normally runs inside a transaction and rolls back after the test. Reading back after clear verifies the database executed the SQL and the current transaction sees its own changes, even though the test has not committed.

## 6. How save(), saveAndFlush(), and flush() Differ

`JpaRepository` provides several methods with similar names but different semantics:

| Method | Meaning |
| --- | --- |
| `save(entity)` | Persists a new Entity or merges a detached Entity depending on state; changes may still await flush |
| `flush()` | Flushes all pending changes in the persistence context |
| `saveAndFlush(entity)` | Saves the Entity and then flushes the persistence context |
| `saveAll(entities)` | Saves a group of Entities; does not guarantee immediate auto-flush at the call |
| `saveAllAndFlush(entities)` | Saves a group of Entities and then flushes |

Example:

```java
PurchaseOrder saved = repository.saveAndFlush(order);
```

`saveAndFlush()` guarantees a flush after saving, yet the Entity can still remain managed. If you immediately call `findById()` in the same persistence context, the result can still be the already-managed instance. To test a fresh read path, call `entityManager.clear()` after flushing or use a different persistence context.

`saveAndFlush()` also does not commit the transaction. When the test ends in rollback, the data is rolled back even though SQL was executed.

## 7. Flush Mode and When SQL Is Sent

JPA has `FlushModeType.AUTO` and `FlushModeType.COMMIT`. With AUTO, the provider must ensure changes that might affect query results are synchronized before a query executes; providers may also flush at other times depending on implementation.

With COMMIT, flushing is required before commit; queries inside the transaction might not see unflushed changes depending on provider/semantics.

In tests where you need to pinpoint exactly when SQL is sent, call `entityManager.flush()` explicitly instead of relying on a query accidentally triggering auto-flush.

Do not call flush after every setter or every field. Flushing incurs SQL and round-trip overhead; flush only at boundaries where you need to check constraints, reload data, or bound memory.

## 8. Verifying UPDATE as Well as INSERT

Flush/clear is also useful to confirm dirty checking produces the right UPDATE:

```java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.setStatus(OrderStatus.PAID);

entityManager.flush();
entityManager.clear();

PurchaseOrder reloaded = repository.findById(id).orElseThrow();
assertEquals(OrderStatus.PAID, reloaded.getStatus());
```

Here the Entity is loaded and managed; the field change is detected by dirty checking. `flush()` sends the UPDATE, `clear()` removes the old instance from the first-level cache, and the subsequent read reloads the persisted state.

You do not need to call `repository.save(order)` on an already-managed Entity in the same transaction just to trigger dirty checking; JPA detects changes automatically upon flush. However, calling `save()` may still be valid depending on repository abstraction conventions.

## 9. How refresh() Differs From clear()

`entityManager.refresh(entity)` reloads the state of a single managed Entity from the database and overwrites in-memory state:

```java
entityManager.flush();
entityManager.refresh(order);
```

Differences:

| Operation | Scope | Result |
| --- | --- | --- |
| `flush()` | All pending changes in the persistence context | Sends SQL to the database; Entities remain managed |
| `clear()` | Entire persistence context | Detaches all Entities; subsequent reads must reload |
| `detach(entity)` | One Entity | Detaches only that Entity |
| `refresh(entity)` | One managed Entity | Reads database state again and overwrites in-memory state |

If you call `refresh()` while the Entity has unflushed changes, unwritten changes can be overwritten. If you want to refresh after your own changes, flush first. `refresh()` is not a way to commit a transaction.

## 10. Bulk UPDATE/DELETE and Stale Persistence Contexts

JPQL bulk DML updates the database directly without updating individual managed Entities sitting in the persistence context:

```java
@Modifying
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatus(
    @Param("id") Long id,
    @Param("status") OrderStatus status
);
```

If a `PurchaseOrder` was loaded before the bulk update, that object can still hold the old status after the UPDATE runs. Bulk DML does not automatically synchronize individual Entity states in the first-level cache.

You can configure Spring Data to flush before and clear after bulk DML:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatusAndClear(
    @Param("id") Long id,
    @Param("status") OrderStatus status
);
```

`flushAutomatically = true` prevents losing pending changes before running the bulk update. `clearAutomatically = true` detaches Entities after the update so code does not continue using stale state in the persistence context.

After this method, Entity references held by the service may be detached. If you need to continue working with them, reload the Entity in the persistence context.

## 11. First-Level Cache and Second-Level Cache

`flush()` and `clear()` handle interactions with the first-level cache, but clearing does not guarantee every subsequent read hits the database directly.

If the Hibernate second-level cache is enabled, a `find()` after clear can retrieve the Entity from the shared cache. The query cache can also participate for cacheable queries.

If the goal is simply to verify mappings and JPA reloadability, flush/clear is usually sufficient. If the goal is to verify the actual value sitting in the database, you must account for the second-level cache as well.

You can instruct a read to bypass the second-level cache:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode", CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode", CacheStoreMode.BYPASS
);

PurchaseOrder reloaded = entityManager.find(
    PurchaseOrder.class, id, hints
);
```

This example uses Jakarta Persistence. `CacheRetrieveMode.BYPASS` skips the shared cache when reading; `CacheStoreMode.BYPASS` avoids storing the read result into the shared cache. These hints do not disable the first-level cache: if the Entity is already managed in the same persistence context, `find()` can still return that instance. Therefore, `clear()` before using this read approach.

In scenarios requiring verification of database state independently of JPA caches, reading via JDBC is a more direct check.

## 12. Using JdbcTemplate to Verify Database Rows

`JdbcTemplate` reads directly via JDBC, bypassing the first-level persistence context and second-level Entity cache:

```java
@DataJpaTest
class PurchaseOrderDatabaseStateTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void verifiesDatabaseColumnAfterFlush() {
        PurchaseOrder order = new PurchaseOrder();
        order.setStatus(OrderStatus.PENDING);
        PurchaseOrder saved = repository.save(order);

        entityManager.flush();

        String storedStatus = jdbcTemplate.queryForObject(
            "select order_status from purchase_order where id = ?",
            String.class,
            saved.getId()
        );

        assertEquals("PENDING", storedStatus);
    }
}
```

This example assumes the enum is stored with `EnumType.STRING`, table/column names match the mapping, and `JdbcTemplate` participates in the same transaction/DataSource as JPA. In Spring, transaction manager and DataSource configuration align so JDBC and JPA both see uncommitted changes of the current transaction.

JDBC checks physical column values and can reveal mapping/converter bugs that reading Entities might not expose easily. If database triggers or column defaults alter data, JDBC can confirm the actual value after flush.

Do not use JDBC over an independent connection expecting to see uncommitted data from another transaction. A separate transaction normally does not see uncommitted changes due to database isolation.

## 13. Verifying Database-Generated Values

Databases can generate or modify values via:

- Column DEFAULTs.
- BEFORE/AFTER INSERT or UPDATE triggers.
- Generated columns.
- Database sequences or functions.

In-memory JPA Entities do not necessarily update database-generated values automatically after flush. For example, a trigger modifies `last_modified_at`, yet the field on the Java object still holds its old value.

You can reload after flush:

```java
entityManager.flush();
entityManager.refresh(order);
```

Or use a JDBC query to inspect the column directly. If you want Hibernate to pick up generated values on the Entity automatically, configure generated property mappings appropriate to your Hibernate/JPA version and verify the actual SQL; do not assume every trigger/default syncs automatically into the object.

## 14. Flush/Clear in Batch and Memory Testing

When persisting thousands of Entities in a single test transaction or batch job, the persistence context retains managed Entities and snapshots for dirty checking. Memory can grow proportionally with the number of objects.

A common strategy is flushing and clearing in batches:

```java
int batchSize = 50;

for (int i = 0; i < orders.size(); i++) {
    entityManager.persist(orders.get(i));

    if ((i + 1) % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
```

Flush writes the current batch's changes; clear frees Entities from the persistence context to reduce memory usage. When using `IDENTITY`, Hibernate may have to execute INSERTs immediately to obtain IDs, and JDBC batching can be constrained depending on strategy. Batch sizes and insert/update ordering should be measured on the target database.

Do not clear mid-batch if you still need to modify older managed Entities or rely on their dirty checking. After clear, updating such objects requires merging or reloading appropriately.

## 15. Transactions and Data Visibility

Flush only sends SQL within the current transaction. Visibility of changes depends on transaction boundaries:

| Reader | Sees Data After Flush Before Commit? |
| --- | --- |
| Same transaction/persistence context after clear | Usually yes, because a transaction sees its own writes |
| Another transaction | Ordinarily no, until the writing transaction commits successfully |
| JDBC connection in the same Spring transaction | Can see the current transaction's writes if sharing the transaction/DataSource |
| Asynchronous read replica | May not see immediately after commit due to replication lag |

In `@DataJpaTest`, tests are normally wrapped in a transaction and rolled back on completion. That does not stop a test from flushing and reading back data within the same transaction. However, if you want to verify another transaction or an asynchronous service sees the data, commit the transaction first and then read from another transaction.

Do not use `entityManager.flush()` to prove data was committed or received by a replica. Those are distinct milestones in the data lifecycle.

## 16. Common Pitfalls

**Save then find returns data even though no SQL INSERT ran.** The persistence context is holding the managed Entity. Enable SQL logging and use flush/clear when verifying the database.

**Clear then data disappears.** Clear may have been called before flush, detaching unsynchronized changes. Perform flush before clear.

**After clear, modifying an old object does not change the database.** The object is detached. Reload the Entity or merge properly inside a transaction.

**After bulk update, getters still return old state.** Bulk DML bypasses managed Entities. Clear or refresh the persistence context after bulk updates.

**Flush does not make another transaction see the data.** Flush is not commit. Commit successfully before reading in another transaction.

**Even after clear, reads still miss new database values.** Check second-level/query caches, transaction isolation, replica lag, and read sources. Use cache bypass or JDBC to cross-check.

**Trigger updates a column, yet Entity keeps old value.** Refresh the Entity after flush or read the column via JDBC; configure generated properties if auto-sync is needed.

**Unique/FK constraint only fails on commit.** Some constraints are deferred to commit. Flush does not guarantee catching every transaction error.

**Batch test grows memory.** Flush and clear in batches, and avoid reusing detached objects as managed Entities.

## 17. Checklist for Verifying Real Data

- Clarify whether the test verifies the persistence context, flushed SQL, or committed data.
- Call `flush()` before reading back if SQL must be forced out.
- Call `clear()` after flush to prevent the first-level cache from returning the old instance.
- Do not clear before flush if pending changes still need to be persisted.
- If you need to keep an Entity managed and reload database state, consider `refresh()`.
- For bulk JPQL DML, consider `flushAutomatically` and `clearAutomatically`.
- Account for second-level/query caches if the goal is direct database verification.
- Use `JdbcTemplate` sharing the transaction/DataSource to verify physical column values when needed.
- Distinguish flush from commit; rolled-back tests can still flush and read back inside the same transaction.
- Verify trigger/default/generated columns after flush using refresh or JDBC.
- Use batched flush/clear when the persistence context grows too large.
- Enable SQL logging or Hibernate statistics when diagnosing actual behavior.

`flush()` forces JPA to send pending changes to the database; `clear()` evicts managed Entities from the first-level cache so the next read is not masked by an old instance. Combining them in the right order helps integration tests verify mappings and SQL reliably. When you need to verify physical values, triggers, or non-JPA updates, check with JDBC as well and always distinguish flush from commit.