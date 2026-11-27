# Optimistic Locking with `@Version`

In a Spring Data JPA application, multiple transactions may read and modify the same record concurrently. If two transactions read the same stale value and then write one after another, the later write can overwrite the result of the earlier write. This phenomenon is called a *lost update*.

Optimistic locking detects conflicts at the time data is updated or deleted. Transactions can still read the same row without holding a database lock throughout processing. On write, JPA checks the version that the transaction originally read. If the version has changed, the operation fails so the application can handle the conflict.

## 1. When do you need optimistic locking?

Suppose inventory has 10 items and two requests both read the record with `quantity = 10`, `version = 4`:

1. Transaction A reads quantity 10, version 4.
2. Transaction B also reads quantity 10, version 4.
3. A sets quantity to 9 and commits. The database stores version 5.
4. B tries to write quantity 8 based on version 4. The version condition is no longer true, so B is not allowed to write.

Without a version check, B could overwrite A's result. With optimistic locking, the system detects the conflict instead of silently losing an update.

This approach fits well when write conflicts are relatively rare while reads occur frequently. If many transactions continuously contend for the same row and operations must be serialized, consider pessimistic locking such as `PESSIMISTIC_WRITE`. Pessimistic locking typically holds database locks during the transaction and increases wait times.

## 2. Declaring the version field with @Version

`@Version` is a Jakarta Persistence annotation, imported from `jakarta.persistence.Version` in Spring Boot 3 and later. Place the annotation on an entity field or getter according to the access type the entity uses. Each entity has one version attribute managed by JPA.

Standard version data types include `int`, `Integer`, `short`, `Short`, `long`, `Long`, and `java.sql.Timestamp`. The example below uses `Long`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory")
public class Inventory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    @Column(name = "version_no", nullable = false)
    private Long version;

    protected Inventory() {
        // JPA requires a no-arg constructor.
    }

    public Inventory(int quantity) {
        this.quantity = quantity;
    }

    public void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be greater than 0");
        }
        if (quantity < amount) {
            throw new IllegalStateException("Insufficient inventory in stock");
        }
        quantity -= amount;
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }
}
```

`@Column(name = "version_no")` sets the version column name in the table. If `@Column` is omitted, the column name is derived from the provider's naming strategy and application configuration. The version column must exist in the database schema. When upgrading a system that already has data, a migration is needed to create the column and initialize the version for existing rows; the following SQL example must be adjusted for your database management system:

```sql
ALTER TABLE inventory
ADD COLUMN version_no BIGINT NOT NULL DEFAULT 0;
```

The JPA provider, such as Hibernate, initializes and increments the version value. Do not manually assign or increment this field in business logic. Using a wrapper type such as `Long` also helps distinguish a new entity with a `null` version from an already persisted entity in some of Spring Data JPA's new-entity detection mechanisms.

## 3. How does JPA check the version?

For a managed entity in the persistence context, when the application modifies state and the transaction flushes, the provider executes an update with a version condition. Illustrative SQL looks like:

```sql
UPDATE inventory
SET quantity = ?, version_no = ?
WHERE id = ? AND version_no = ?;
```

Suppose the entity currently has version 4. The provider writes the new data with version 5 and updates only the row with the matching `id` and version 4. If another transaction has already updated that row to version 5, the statement finds no matching row and the affected row count is 0. The provider recognizes that the data is stale and reports an optimistic locking error.

This is illustrative SQL for the mechanism, not a fixed SQL string that every provider is required to emit. The provider may also perform checks at flush or commit time. Therefore, the error can appear when `flush()` is called or when the transaction ends, even though the statement modifying the entity ran earlier.

Typical lifecycle:

- **Create:** the application persists the entity; the provider sets the initial version value.
- **Read:** the entity receives the current version value from the database.
- **Modify:** the provider uses the read version in the update condition and increments the version if the update succeeds.
- **Delete:** the provider also checks the version to avoid deleting state that has already been modified by another transaction.
- **Conflict:** an update or delete whose version does not match raises an optimistic locking error and rolls back the transaction.

There is no need to lock the row at read time. The check is performed at write time, so two transactions can still read the same version concurrently.

## 4. Using with Spring Data JPA

The repository can be declared as usual:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {
}
```

In the service, load the entity inside a transaction and modify the managed entity:

```java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long id, int amount) {
        Inventory inventory = repository.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Inventory not found: " + id));

        inventory.reserve(amount);
        // Dirty checking persists changes when the transaction flushes/commits.
        // No need to call save() for an entity that is still managed.
    }
}
```

`@Transactional` creates the transaction boundary for reading and modifying. Because the entity is loaded in the transaction's persistence context, Hibernate can detect changes via dirty checking and issue the update statement on flush. Calling `repository.save(inventory)` after modifying a managed entity is usually unnecessary, though it may appear in some codebase conventions.

If the application receives a detached entity from a request or from a previous transaction, Spring Data JPA's `save()` operation may go through `merge()`. The provider still checks the version when synchronizing that state. Therefore, do not strip the version field from the update flow if the client needs to detect stale data.

## 5. Handling conflict errors

At the JPA layer, the error is typically `jakarta.persistence.OptimisticLockException`. When passing through Spring's exception translation mechanism, the application usually receives an exception under `OptimisticLockingFailureException`, such as `ObjectOptimisticLockingFailureException`.

The error can occur at flush or commit. If you need to detect it earlier inside the transaction, you can call `repository.flush()` or `EntityManager.flush()`; this forces the provider to synchronize pending changes. It does not commit the transaction early.

Handling should match the business logic:

- Inform the user that the data was changed by someone else, reload the latest data, and ask them to confirm or reapply the operation.
- For client update APIs, you can return HTTP 409 Conflict so the client knows the submitted state is stale.
- Only auto-retry when the operation can be safely re-executed. Each retry must use a new transaction, read the latest data again, and recompute the business change.
- Do not catch the error and continue using the failed transaction. The transaction may already be marked rollback-only; let the transaction finish and handle it at an outer boundary.

Do not automatically overwrite with stale data. For example, if two people edit a quantity or balance at the same time, the application needs to make a business decision based on the latest value rather than simply resending the entire old object.

## 6. Cases requiring attention

### Bulk updates with JPQL

Bulk update/delete statements using `@Modifying` run directly against the database and bypass dirty checking for managed entities. JPA does not automatically perform optimistic locking checks for these bulk updates, and the persistence context does not automatically synchronize with the statement's result.

If you still need a bulk update with version checking, you must include the expected version in the condition and increment the version yourself. For example:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Inventory i
       set i.quantity = :quantity,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
    """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") Long expectedVersion,
        @Param("quantity") int quantity);
```

If the method returns 0 updated rows, either the record does not exist or the version no longer matches; the application needs to distinguish the two cases if required by business logic. With native SQL, you must follow the same principle manually. After a bulk update, keep in mind that the persistence context may hold stale entities; clear or refresh appropriately.

### Do not manually update the version in normal entity flows

Do not write `version++` in business methods and do not accept a client-chosen new version to write into the entity. The provider is responsible for incrementing the version. Clients should only send the version they read as an expected value so the server can detect conflicts.

### Updates through multiple write paths

Optimistic locking only protects write paths that perform the version check. If another process modifies the same table using direct SQL, a batch job, or a bulk update without checking and incrementing the version, the mechanism may fail to detect that conflict. Every relevant write path must follow the same versioning convention.

### Version does not replace data constraints

`@Version` resolves conflicts between entity updates. It does not replace foreign keys, unique constraints, check constraints, or business rules. For example, if negative quantities are disallowed, you still need business validation and should consider database constraints to protect data across all write paths.

## 7. Testing concurrent update scenarios

An integration test needs to use two independent transactions:

1. Create an inventory row and commit.
2. Transaction A reads that row; transaction B also reads the same row before A updates.
3. A changes the quantity and commits. The version in the database is incremented.
4. B modifies the object it read earlier and attempts to flush or commit.
5. Verify that B receives an optimistic locking error, transaction B rolls back, and the data committed by A is preserved.

The key point is that both reads must retain the same initial version, and the second write must run in a different transaction. Testing everything inside a single persistence context fails to reproduce conflicts between two independent reads.

Test examples can use `TransactionTemplate` to create clear transaction boundaries, or `@Transactional` combined with two threads and two separate transaction manager contexts. When checking for errors, flush inside the second write transaction so the error surfaces right at the assertion point rather than only when the framework commits the transaction.

## 8. Common errors and troubleshooting

| Symptom | Common cause | How to check or handle |
|---|---|---|
| Conflicts are not detected | Entity lacks `@Version` or a write path bypasses version | Check the mapping and all write flows into the table |
| Error only appears at commit | Provider defers SQL until flush/commit | Flush within the scope under test or handle exceptions outside the transaction |
| Bulk update does not increment version | Bulk JPQL/native SQL does not auto-apply optimistic locking | Add a version condition and explicitly increment version |
| New entity has an invalid version | Application sets version manually or schema was not migrated properly | Let the provider manage version and verify the database column |
| Retries keep failing repeatedly | Retry reuses a stale entity or version | Open a new transaction, read the latest state, and recompute the business logic |
| Transaction continues after catching error | Transaction has already been marked rollback-only | Let the transaction roll back and handle it in the outer caller layer |

## 9. Deployment checklist

- The entity has exactly one attribute annotated with `@Version` using a JPA-supported type.
- The version column exists, has valid values for existing data, and is mapped with the right name.
- No business code manually increments or overwrites the version.
- Entity modification operations run inside appropriate transactions.
- Bulk updates, native SQL, and batch jobs have their own version-checking/incrementing rules.
- The application handles conflict errors according to business logic without silently overwriting newer data.
- Integration tests simulate two transactions reading the same version and verify that the later write is rejected.

Optimistic locking with `@Version` is a clean choice for entities that are read frequently and updated concurrently only rarely. The mechanism reaches its full effectiveness only when every write path respects the version and the application has explicit conflict handling.