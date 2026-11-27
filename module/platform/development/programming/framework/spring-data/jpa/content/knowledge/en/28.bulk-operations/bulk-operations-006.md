# Bulk DML and Limitations of Callbacks, Cascades, and Versioning in Spring Data JPA

Bulk DML (bulk data manipulation) is an `UPDATE` or `DELETE` operation that acts directly on a set of records in the database using a single statement. In Spring Data JPA, we typically use `@Modifying` combined with `@Query`, or methods such as `deleteAllInBatch()`. This reduces loading individual entities into memory and fits bulk status updates, cleaning up old data, or maintenance tasks.

In return, bulk DML follows a direct database-level execution path. JPA does not process each entity individually as when calling `EntityManager.merge()` or `EntityManager.remove()`. Consequently, lifecycle callbacks, JPA cascades, the persistence context, and optimistic locking with `@Version` have important limitations.

This article uses Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ, and H2 in the examples. The code snippets are components of a Spring Boot project with the appropriate JPA and test dependencies.

## 1. How does bulk DML work?

A normal entity operation goes through the persistence context:

1. An entity is loaded or persisted and becomes managed.
2. The application modifies properties or calls `remove()`.
3. On flush, the JPA provider detects changes and emits SQL statements.
4. JPA can execute callbacks, cascades, version checks, and synchronize entity state according to persistence context rules.

Bulk DML takes a shorter path: a JPQL or SQL statement acts directly on matching rows in the database. JPA does not load all affected entities to process each Java object.

JPQL example:

```java
update InventoryItem i
set i.quantity = 0
where i.expired = true
```

This statement updates every matching row in a single execution. It is not equivalent to a loop that loads each `InventoryItem`, calls a setter, and flushes.

Bulk DML is typically effective when record counts are large and the business rule can be safely expressed in one statement. If each entity needs callbacks, cascades, domain events, or individual business logic, normal entity operations are usually more appropriate.

## 2. Using `@Modifying` with `@Query`

Spring Data JPA needs to know that a query method performs a data modification rather than querying results. Annotate the method with `@Modifying` when using `@Query` for JPQL `UPDATE` or `DELETE`.

Example entity:

**InventoryItem.java**

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(int quantity) {
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getVersion() {
        return version;
    }
}
```

Repository:

**InventoryItemRepository.java**

```java
package com.example.inventory;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    @Transactional
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.quantity = :newQuantity,
               i.version = i.version + 1
         where i.id = :id
           and i.version = :expectedVersion
        """)
    int updateQuantityIfVersionMatches(
        @Param("id") Long id,
        @Param("newQuantity") int newQuantity,
        @Param("expectedVersion") long expectedVersion
    );

    @Transactional
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        delete from InventoryItem i
         where i.quantity = 0
        """)
    int deleteEmptyItemsInBulk();
}
```

Points to remember:

- `@Modifying` changes how Spring Data executes the query. It does not automatically create a transaction in every case.
- Query methods declared with `@Query` do not inherently carry transactions like inherited CRUD methods. Place `@Transactional` on the repository method or, more flexibly, on the service enclosing the operation.
- A method returning `int` receives the number of affected rows/entities. For update/delete statements, this count helps determine whether the operation matched any records.
- `@Modifying` can be used with JPQL or native SQL. For native SQL, set `nativeQuery = true` in `@Query`; limitations regarding callbacks, cascades, and persistence context synchronization still apply.

In the example, `flushAutomatically = true` requests flushing the persistence context before running the query. `clearAutomatically = true` requests clearing the persistence context after the query runs. Both attributes default to `false`.

## 3. Bulk DML bypasses lifecycle callbacks

Callbacks such as `@PreUpdate`, `@PostUpdate`, `@PreRemove`, and `@PostRemove` are tied to the lifecycle of individual entities. Bulk DML does not load individual entities and does not invoke those callbacks.

Example:

```java
@Entity
public class Document {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    private Instant updatedAt;

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }

    @PreRemove
    void beforeRemove() {
        // Handle cleanup or logging before an entity is removed.
    }
}
```

If the application runs:

```java
documentRepository.markAllArchived();
```

where the repository method executes a JPQL bulk update, the `beforeUpdate()` callback is not called for each `Document`. Similarly, bulk delete does not call `@PreRemove` or `@PostRemove`.

Practical consequences:

- An `updatedAt` field updated inside `@PreUpdate` will not change automatically.
- Validation, logging, or audit record creation logic inside entity listeners does not run.
- Spring Data auditing based on entity listeners such as `@LastModifiedDate` is not automatically applied to bulk-updated rows.
- Processing dependent on entity removal callbacks is not executed.

If a timestamp column needs to be updated in a bulk query, set that value explicitly in the statement, such as `set d.updatedAt = :now`. If audit records or domain events are needed per entity, use a separate entity-processing workflow or design a database- or application-level audit/event mechanism appropriate for the requirement.

Database triggers can still run according to database rules. Triggers are a database mechanism, distinct from JPA lifecycle callbacks in the Java application.

## 4. Bulk DELETE does not execute JPA cascades

Suppose a purchase order has multiple order lines:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

When calling `entityManager.remove(order)`, JPA applies the corresponding cascade rules. With `CascadeType.REMOVE` or `CascadeType.ALL`, child entities can be marked for removal along with the parent; `orphanRemoval` handles child entities removed from the managed relationship according to JPA rules.

However, a JPQL bulk delete such as:

```java
delete from PurchaseOrder o
where o.createdAt < :cutoff
```

only deletes rows of the target entity in the database. It does not call `remove()` for each `PurchaseOrder`, does not traverse the `lines` collection, does not perform JPA cascades, and does not apply `orphanRemoval` as when modifying relationships on managed entities.

If the `order_lines` table has a foreign key referencing `purchase_orders` without database-level cascade behavior, the statement may fail due to a foreign key constraint violation. This can be handled by deleting child records first, using entity operations when JPA cascades are needed, or designing the foreign key with `ON DELETE CASCADE` if that is the desired data rule.

`ON DELETE CASCADE` is a database cascade. It can delete child rows when a parent row is deleted, yet it still does not invoke Java callbacks for child entities.

Spring Data also has two delete styles to distinguish:

| Delete style | Execution approach | Callbacks and JPA cascade |
|---|---|---|
| Derived delete such as `deleteByStatus(...)` | Spring Data finds matching entities then deletes each entity | Can apply JPA lifecycle callbacks and cascades |
| `@Modifying @Query("delete ...")` | A direct bulk delete in the database | Does not apply callbacks or JPA cascades |
| `deleteAllInBatch()` / `deleteAllInBatch(entities)` | Bulk delete via a query operation | Does not apply callbacks or JPA cascades |

Derived delete can consume more memory and operations because it loads matching entities. Bulk delete is faster for large datasets, but the author must manually ensure data constraints and required side effects.

## 5. Bulk DML and optimistic locking with `@Version`

In normal entity operations, the JPA provider uses the `@Version` property to check optimistic locking. When updating a managed entity, the provider includes the current version in the update condition and increments the version on success. If another transaction has updated the entity, the operation can fail with an optimistic locking exception.

Bulk DML bypasses that automatic mechanism:

- JPA does not automatically check the version of each affected entity.
- JPA does not automatically increment `@Version` properties for bulk-updated rows.
- A bulk update can overwrite data modified by another transaction if the statement lacks an appropriate protective condition.

If an update must be guarded by version, include the expected version in `WHERE` and manually increment the version in `SET`. The `updateQuantityIfVersionMatches` method above does this:

```sql
UPDATE inventory_items
SET quantity = ?, version = version + 1
WHERE id = ? AND version = ?
```

This is SQL illustrating the meaning of the JPQL. When a record has the matching `id` and `version`, the statement updates that row and increments the version. If the version has changed, the condition does not match so no rows are updated.

For a known record:

- Affected row count equals `1`: update succeeded under the expected version.
- Count equals `0`: update failed; the record may not exist, the version may be stale, or another business condition is no longer true. Do not conclude with certainty that version alone was the cause if the statement has multiple conditions.

For bulk updates spanning many entities, merely incrementing the version via `version = version + 1` does not create per-entity optimistic locking checks. If business logic requires conflict detection per record, design appropriate version conditions or process individual entities using standard JPA mechanisms.

After a bulk update, managed entities may still hold old versions and data. Clear or refresh before continuing to use them; otherwise the application may read stale state from the persistence context.

## 6. The persistence context can become stale

The persistence context is EntityManager's first-level cache. Within a persistence context, each entity identity is usually managed by a corresponding Java object.

For example, the application has loaded an `InventoryItem`:

```java
InventoryItem item = entityManager.find(InventoryItem.class, id);
int oldQuantity = item.getQuantity();

repository.updateQuantityIfVersionMatches(
    id, oldQuantity - 1, item.getVersion()
);
```

The bulk query updates the database directly, yet the managed `item` object may still hold the old `quantity` and `version`. A subsequent `find()` in the same persistence context may return the exact same managed object instead of reading from the database again.

There are two commonly used options:

- Flush before the query to push pending changes in the persistence context to the database.
- Clear after the query to detach all managed entities; when data is needed, reload from the database.

`flushAutomatically = true` and `clearAutomatically = true` on `@Modifying` support these two steps. You can call `entityManager.flush()` and `entityManager.clear()` explicitly if control is needed in the service.

Understand the scope of impact:

- Flushing can write all pending changes in the persistence context, not just entities belonging to the query.
- Clearing detaches all managed entities in the current persistence context, not just entities affected by bulk DML.
- Clearing without flushing first can lose unflushed changes residing in memory.
- After clearing, old Java references still exist but are detached. Do not continue assuming they automatically reflect database state.

If only a single entity needs refreshing, consider `entityManager.refresh(entity)` after ensuring the entity is still managed. `refresh` reloads state from the database and overwrites unflushed changes on that entity, so use it intentionally.

## 7. Testing versioned updates

An integration test can verify the updated row count, the incremented version, and that an update with an old version fails.

**InventoryItemRepositoryTest.java**

```java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class InventoryItemRepositoryTest {

    @Autowired
    private InventoryItemRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void bulkUpdateChecksAndIncrementsVersion() {
        InventoryItem item = new InventoryItem(10);
        entityManager.persistAndFlush(item);

        Long id = item.getId();
        long originalVersion = item.getVersion();

        int updated = repository.updateQuantityIfVersionMatches(
            id, 7, originalVersion
        );

        assertThat(updated).isEqualTo(1);

        // The repository query cleared the persistence context.
        InventoryItem reloaded =
            entityManager.find(InventoryItem.class, id);

        assertThat(reloaded.getQuantity()).isEqualTo(7);
        assertThat(reloaded.getVersion()).isEqualTo(originalVersion + 1);

        // The old version no longer matches, so the statement updates zero rows.
        int staleUpdate = repository.updateQuantityIfVersionMatches(
            id, 5, originalVersion
        );

        assertThat(staleUpdate).isZero();
    }
}
```

`@DataJpaTest` provides a transaction for the test and usually uses an embedded database when the appropriate dependency is present. This example verifies the database result by reloading the entity after the bulk query. This is an integration test; do not mock the repository because the goal is to test the JPA query and its effects.

The test does not need to print to stdout. The proof is in the assertions: the first call affects one row, quantity is updated, version increases by one, and the call with the stale version affects zero rows.

## 8. Choosing bulk DML or entity operations?

| Requirement | Appropriate direction |
|---|---|
| Update thousands of records with the same simple rule | Bulk JPQL or native DML |
| Need `@PreUpdate`, `@PostUpdate`, entity listeners, or Spring Data auditing | Load and update managed entities |
| Need JPA `CascadeType.REMOVE` or `orphanRemoval` | Invoke delete operations on managed entities |
| Need automatic per-entity optimistic locking | Update managed entities with `@Version` |
| Need bulk update while still guarding a single row by version | Put version in `WHERE`, increment version explicitly, and check affected count |
| Need fast deletion when appropriate foreign key/database cascade rules already exist | Bulk delete while managing the persistence context |
| Need to group many entity INSERT/UPDATE statements into a JDBC batch | Consider Hibernate JDBC batching |

Bulk DML and JDBC batching are two different concepts. Bulk DML is a set-based statement affecting multiple rows, such as `UPDATE ... WHERE ...`. JDBC batching groups multiple individual INSERT/UPDATE statements to send together. With JDBC batching, the application can still persist or update individual entities via JPA; lifecycles, cascades, and versions continue to be handled through the provider's entity path.

For example, `saveAll(entities)` does not mean Spring Data always generates a single bulk SQL statement. The method usually invokes the save pipeline for each entity; Hibernate can group the corresponding SQL statements via settings such as `hibernate.jdbc.batch_size`. Distinguish the round-trip reduction goal of JDBC batching from the set-based update goal of bulk DML.

## 9. Checklist before putting bulk DML into production

1. **Transaction:** the statement runs inside an appropriate transaction; transaction boundaries are clearly defined in the service or repository.
2. **Callbacks:** check whether any logic inside `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove`, or entity listeners needs to be replaced.
3. **Cascades and foreign keys:** confirm how child records, orphans, and foreign keys are handled. Do not rely on `CascadeType.REMOVE` for bulk deletes.
4. **Version:** if optimistic locking is needed, put the expected version in the condition and increment the version explicitly; check the affected count.
5. **Persistence context:** decide when to flush and clear/refresh. Note that `clearAutomatically` detaches all managed entities in the context.
6. **Auditing and events:** update audit columns in the query or design another audit/event mechanism if callbacks do not run.
7. **Testing:** verify database data, affected row counts, versions, child relationships, and post-query entity state.

Bulk DML is an effective tool for bulk operations when acting directly on the database fits the business requirements. Before using it, explicitly handle the responsibilities JPA usually performs per entity: callbacks, cascades, versions, auditing, and persistence context synchronization.
