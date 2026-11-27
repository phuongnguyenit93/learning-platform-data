# Updating Managed Entities Without Repeatedly Calling save in Spring Data JPA

When an entity has been loaded and is in the managed state inside a persistence context, JPA automatically tracks changes to the entity. If properties are updated within an active transaction, Hibernate detects the changes and issues a SQL UPDATE upon flush or commit. Therefore, in this case, there is no need to call repository.save() after every entity modification.

That mechanism is called dirty checking. Clearly understanding the persistence context, entity states, and transaction boundaries makes code more concise, avoids unnecessary merge operations, and ensures data is written at the right time.

## 1. What Is the Persistence Context?

The persistence context is the management area for entities that EntityManager is tracking. Each entity has an identity in the context based on its entity type and primary key. When an entity is managed, JPA can detect property changes and synchronize them to the database.

Operations such as EntityManager.find(), repository.findById(), or JPQL queries can bring entities into the persistence context. When the transaction ends, a transaction-scoped persistence context is typically closed or cleared; entities returned outside may become detached.

Typical update flow:

~~~mermaid
flowchart TD
    A[Service method starts] --> B["@Transactional opens transaction"]
    B --> C[Repository findById]
    C --> D[Entity in managed state]
    D --> E[Modify properties]
    E --> F[Dirty checking]
    F --> G[Flush: Hibernate issues UPDATE]
    G --> H[Commit transaction]
    H --> I[Database saves changes]
~~~

Key point: JPA tracks entities in the persistence context. Calling save() is not a prerequisite for dirty checking to work.

## 2. Four Basic Entity States

JPA typically describes the entity lifecycle using four states:

| State | Meaning | Example |
|---|---|---|
| New / Transient | A new Java object, not yet managed by the persistence context | new Product(...) |
| Managed / Persistent | An entity currently tracked by EntityManager | An entity just fetched via findById in a transaction |
| Detached | An entity that was previously managed but is no longer in the persistence context | An entity after the transaction ends |
| Removed | An entity marked for deletion in the persistence context | An entity after entityManager.remove(...) |

State transition example:

~~~java
Product product = new Product("Keyboard"); // transient
entityManager.persist(product);            // managed
product.rename("Mechanical Keyboard");     // still managed
entityManager.detach(product);              // detached
Product managedProduct = entityManager.merge(product); // managed copy
entityManager.remove(managedProduct);        // removed
~~~

The example above illustrates direct JPA operations. In a Spring Data JPA application, repositories usually hide most EntityManager calls.

## 3. How Does Dirty Checking Work?

When an entity becomes managed, Hibernate usually keeps the initial state or a snapshot of tracked properties. During flush, Hibernate compares the current state against the snapshot. If it detects that a property has changed, the provider generates the corresponding SQL UPDATE.

Example:

~~~java
Product product = entityManager.find(Product.class, 10L);
product.setName("Mechanical Keyboard");
// No need for entityManager.merge(product).
// The entity is managed, so changes are tracked by dirty checking.
~~~

When the transaction commits, JPA requires changes to be synchronized to the database. Hibernate performs a flush before committing; SQL may be sent before the commit point, but changes still belong to the transaction and can roll back.

Dirty checking has the following characteristics:

- Applies only to entities that are currently managed.
- No need to call save() after every setter.
- If there are no changes, the provider usually does not issue an UPDATE.
- SQL is usually deferred until flush/commit.
- A flush may be needed before running a query that depends on unsynchronized changes.
- Callbacks such as @PreUpdate may be invoked when the entity is actually updated through the normal entity mechanism.

Dirty checking is not a mechanism that continuously synchronizes every time a setter is called. It is evaluated during the flush process of the persistence context.

## 4. Crucial Condition: Updating Within a Transaction

A common mistake is calling repository.findById() inside a method, returning the entity outside, and then modifying the entity after the repository's transaction has ended.

Example to avoid:

~~~java
public Product rename(Long id, String newName) {
    Product product = repository.findById(id).orElseThrow();
    product.setName(newName);
    return product;
}
~~~

Without a transaction enclosing the service method, repository.findById() may run in its own transaction. After the repository method finishes, the entity may already be detached. Subsequent modifications are no longer tracked by the persistence context and are not automatically written to the database.

The right way is to place the transaction at the service layer so that both reading and modifying take place within the same persistence context.

## 5. Example of Updating a Managed Entity Without Calling save()

Product entity:

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @Version
    private Long version;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        this.name = newName;
    }

    public void deactivate() {
        this.active = false;
    }

    public void activate() {
        this.active = true;
    }
}
~~~

Repository:

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Service updating the entity:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.rename(newName);

        // product is managed; dirty checking will write changes on flush/commit.
        return product;
    }

    @Transactional
    public void deactivate(Long id) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.deactivate();
    }
}
~~~

In both service methods:

1. @Transactional opens a transaction.
2. findById() loads the entity and puts it into the persistence context.
3. rename() or deactivate() changes the state of the managed entity.
4. When the method finishes normally, the transaction commits and Hibernate flushes the changes.
5. The SQL UPDATE is executed inside the transaction.

There is no need to call repository.save(product) after changing the name or status. Returning the entity from the service does not automatically keep it managed after the transaction closes; if you need to return data for an API, convert it to a DTO within the transaction or load the required data before finishing.

## 6. Why Is save() Unnecessary for Managed Entities?

Spring Data JPA implements save() based on the new/existing state of the entity. In general:

- If the entity is detected as new, the repository calls EntityManager.persist().
- If the entity is detected as existing, the repository calls EntityManager.merge().

merge() copies state from the passed object into a managed instance and returns that managed instance. For an entity already managed in the same persistence context, calling save() is usually unnecessary. It can lead to an unnecessary merge and make the code flow harder to understand.

Example:

~~~java
@Transactional
public Product update(Long id, String name) {
    Product managed = repository.findById(id).orElseThrow();
    managed.rename(name);

    // Not needed:
    // managed = repository.save(managed);

    return managed;
}
~~~

If you still call save() on a managed entity, do not assume it always generates an extra SQL UPDATE immediately. SQL still depends on dirty checking, flush, and data state. However, merge provides no benefit when the entity is already managed.

For detached entities, save() may be needed because the repository must merge the state into the persistence context. In that case, use the instance returned from save(), because merge does not make the original detached object managed.

## 7. Distinguishing persist(), merge(), and save()

| Operation | Purpose | Object after operation |
|---|---|---|
| EntityManager.persist(newEntity) | Adds a new entity to the persistence context | The passed object becomes managed |
| EntityManager.merge(detachedEntity) | Copies detached entity state into the context | Return value is the managed instance |
| repository.save(entity) | Spring Data API to save a new or existing entity | Returns the persisted/merged entity |
| Modifying a managed entity | Updates an already managed entity | Remains managed, tracked by dirty checking |

Merge example:

~~~java
Product detached = obtainDetachedProduct();

Product managed = entityManager.merge(detached);

// detached remains a detached instance.
// managed is the instance managed by the persistence context.
managed.rename("Updated name");
~~~

Do not ignore the return value of merge() or repository.save() when handling a detached entity. Subsequent modifications on the old object may not be tracked.

## 8. Updating Multiple Properties in a Single Transaction

Dirty checking is especially useful when a business operation modifies multiple properties of the same entity:

~~~java
@Transactional
public void updateProduct(
        Long id,
        String name,
        boolean active) {
    Product product = repository.findById(id)
            .orElseThrow();

    product.rename(name);

    if (active) {
        product.activate();
    } else {
        product.deactivate();
    }

    // No need to call save() after each change.
}
~~~

Multiple entities can be updated in the same transaction:

~~~java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByActiveTrue();
}

@Service
public class ProductBatchService {
    private final ProductRepository repository;

    public ProductBatchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deactivateActiveProducts() {
        List<Product> products = repository.findByActiveTrue();
        for (Product product : products) {
            product.deactivate();
        }
        // Hibernate detects the changes upon flush.
    }
}
~~~

In practice, pay attention to the size of the persistence context. If processing tens of thousands of entities, keeping all of them managed at once can consume significant memory. You can process in batches with controlled flush and clear, or use a bulk update if appropriate for the business logic.

Do not call save() repeatedly for each entity just to trigger dirty checking. When entities are already managed, modifying properties is sufficient.

## 9. How Do Flush and Commit Differ?

Flush synchronizes pending changes in the persistence context to the database via SQL. Commit confirms the transaction so that changes become committed data.

| Action | Meaning |
|---|---|
| Modifying managed property | Updates state in memory |
| flush() | Sends required SQL to the database in the current transaction |
| commit | Confirms the transaction |
| rollback | Discards changes of an uncommitted transaction |

You can request a flush explicitly:

~~~java
@Transactional
public void renameAndCheck(Long id, String newName) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(newName);

    repository.flush();

    // SQL UPDATE has been sent in the transaction.
    // The transaction has not committed yet at this line.
}
~~~

Normally, you do not need to call flush() manually. Hibernate flushes automatically before commit and may flush before certain queries when flush mode is AUTO. Only call flush when you need to guarantee SQL has been sent, such as wanting to detect constraint violations early or needing to read SQL results within the same transaction.

flush() does not mean commit. If an error occurs after flush and the transaction rolls back, the database still discards the changes belonging to that transaction.

## 10. Transaction Boundaries and Spring Considerations

@Transactional is typically placed on public service methods. Spring creates a proxy to start, commit, or roll back the transaction around calls from outside the bean.

~~~java
@Service
public class ProductService {

    @Transactional
    public void rename(Long id, String name) {
        // Read and update entity within the same transaction.
    }
}
~~~

Key considerations:

- The transaction must encompass both loading the entity and modifying the entity.
- Calling a @Transactional method from another method in the same instance (self-invocation) typically does not go through the proxy, so the inner annotation may not be applied as expected.
- A repository method with its own transaction does not automatically keep the entity managed after the method ends.
- Do not mark an update method as @Transactional(readOnly = true).
- By default, Spring rolls back on unchecked exceptions and Errors; checked exceptions do not automatically roll back unless rollbackFor is configured.
- Keep transactions short; avoid calling external APIs or waiting on user input while a transaction is open.
- If an outer transaction already exists, the repository typically joins that transaction under the default REQUIRED propagation.

Example of a proper structure: Controller calls Service; Service has @Transactional; Service calls repository to load and modify entities. The Controller should not open transactions itself and perform persistence operations directly.

## 11. When Do You Still Need to Call save()?

Not every operation omits save().

| Scenario | Need save()? | Reason |
|---|---|---|
| Creating a new entity | Yes, usually repository.save() | Entity needs to be persisted |
| Loading an entity in a transaction and modifying it | No | Dirty checking writes changes automatically |
| Loading an entity for read-only | No | No changes need saving |
| Updating a detached entity | May be needed | save() performs merge; must use returned instance |
| Creating an entity with a manually assigned ID | Depends on new/existing detection | Spring Data needs to determine persist or merge |
| Bulk JPQL UPDATE | Do not call save per entity | Query updates the database directly via @Modifying |
| Modifying an entity after the transaction ends | Cannot rely on dirty checking | Entity is detached; must reload in a transaction or merge |

For a new entity:

~~~java
@Transactional
public Product create(String name) {
    Product product = new Product(name);
    return repository.save(product);
}
~~~

For a managed entity:

~~~java
@Transactional
public void rename(Long id, String name) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(name);
}
~~~

The two cases have different purposes: a new entity needs to be persisted; a managed entity is already in the persistence context and being tracked.

## 12. Avoid Blindly Updating Entities with Request Data

A common anti-pattern is accepting an entire entity from JSON, where the client also sends the ID, and then calling save() to overwrite the data:

~~~java
// Should not be used as a general update approach.
public Product update(Product requestEntity) {
    return repository.save(requestEntity);
}
~~~

This approach can overwrite fields the client is not allowed to edit, and cause issues with lazy relationships, audit fields, or optimistic locking.

Instead, accept a DTO, load the managed entity, and update only allowed fields:

~~~java
public record RenameProductRequest(String name) {
}

@Transactional
public Product rename(Long id, RenameProductRequest request) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(request.name());
    return product;
}
~~~

This keeps domain rules inside the entity and explicitly controls which fields can be modified. For APIs, DTOs are usually returned instead of returning entities directly to avoid lazy loading issues and accidentally exposing internal relationships.

## 13. Optimistic Locking with @Version

When multiple users update the same record concurrently, dirty checking alone does not resolve business conflicts. @Version can be used to detect concurrent updates.

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;

    protected Product() {
    }

    public void rename(String name) {
        this.name = name;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Hibernate includes the current version in the UPDATE condition and increments the version upon a successful update. If another transaction has already updated the same record, the number of updated rows is not as expected and JPA reports an optimistic locking failure, which Spring typically translates into ObjectOptimisticLockingFailureException.

Example scenario:

1. Transaction A reads Product version 3.
2. Transaction B also reads version 3.
3. B updates and commits; version becomes 4.
4. A updates with condition version = 3.
5. A's UPDATE no longer matches; A receives an optimistic locking error.

Handle conflicts according to business rules: notify the user to reload the data, perform bounded retries, or ask to merge changes. Avoid infinite automatic retries.

## 14. Bulk Update Differs from Dirty Checking

A JPQL bulk update directly updates multiple rows in the database:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Product p set p.active = false where p.active = true")
    int deactivateAll();
}
~~~

Called inside a transaction:

~~~java
@Transactional
public int deactivateAllProducts() {
    return repository.deactivateAll();
}
~~~

Bulk update is useful when changing many rows without loading each entity. However, it bypasses per-entity dirty checking, typically does not trigger entity lifecycle callbacks, and can leave managed entities in the persistence context holding stale values. clearAutomatically clears the context after the query; flushAutomatically synchronizes pending changes before running the bulk query.

If the entity uses @Version, bulk updates must be explicitly designed to update the version if business logic requires optimistic locking protection. A bulk query is not automatically equivalent to modifying each managed entity.

## 15. Testing Dirty Checking

@DataJpaTest can be used to verify that an entity is updated when modified within a transaction without calling save() a second time.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.transaction.annotation.Transactional;

@DataJpaTest
class ProductDirtyCheckingTest {

    @Autowired
    private ProductRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    @Transactional
    void updatesManagedEntityWithoutCallingSaveAgain() {
        Product product = repository.save(new Product("Keyboard"));
        Long id = product.getId();

        Product managed = repository.findById(id).orElseThrow();
        managed.rename("Mechanical Keyboard");

        // Flush SQL then clear the persistence context so the next read fetches from the database.
        entityManager.flush();
        entityManager.clear();

        Product reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getName()).isEqualTo("Mechanical Keyboard");
    }
}
~~~

In this test, the first repository.save() is used to create a new entity. Then the entity is loaded and updated while managed. flush() synchronizes changes for verification; the test transaction is typically rolled back at the end according to @DataJpaTest configuration.

If you want to verify data after a real commit, you need an integration test that manages separate transactions, commits in one, and reads back in another. Do not confuse re-reading within the same persistence context with verifying committed data.

## 16. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Entity modified but database unchanged | Entity is detached or lacks an enclosing transaction | Load and modify the entity in the same @Transactional service method |
| Calling save() multiple times doesn't help | Entity was already managed | Use dirty checking; only save new or detached entities when needed |
| Updates after repository method finishes have no effect | Repository transaction already closed | Put the transaction at the service layer enclosing read and modify |
| merge() returns a different object | merge copies state into a managed instance | Continue using the object returned from merge/save |
| No SQL UPDATE seen right after setter | SQL is deferred until flush/commit | Check after flush or commit |
| flush followed by rollback still loses changes | flush only sends SQL within the transaction | Only commit confirms the transaction |
| Entity overwritten by request | Directly binding client data to the entity | Use DTOs and update allowed fields |
| Optimistic locking failure | Another transaction updated first | Reload and handle the conflict per business rules |
| Entity in context is stale after bulk update | Bulk query does not synchronize managed objects | Flush/clear or reload entities |
| @Transactional does not work | Self-invocation or called outside Spring proxy | Extract method to a Spring-managed bean/service |

## 17. Guidelines for Real-World Applications

- Place transaction boundaries on service methods representing a business operation.
- Load entities using repositories inside a transaction, then modify them via domain-meaningful methods.
- Use dirty checking for managed entities; do not repeatedly call save() after every setter.
- Call save() for new entities and intentionally use merge/save for detached entities.
- Use @Version when concurrent update detection is needed.
- Use bulk updates when processing many rows and you understand the impact on the persistence context, callbacks, and version.
- Keep transactions short and avoid calling external services inside a transaction.
- Use DTOs to accept API data and control which fields can be updated.
- Use flush() only when early SQL synchronization is needed; remember flush is not commit.
- Test against the target database if logic depends on specific Hibernate or SQL behavior.

## 18. Self-Assessment Checklist

- [ ] Can explain the persistence context and the managed state.
- [ ] Can distinguish transient, managed, detached, and removed.
- [ ] Can describe dirty checking and flush timing.
- [ ] Can update an entity in a @Transactional service method without calling save() a second time.
- [ ] Can explain why a standalone repository.findById() may return a detached entity after the method finishes.
- [ ] Can distinguish persist(), merge(), and repository.save().
- [ ] Properly use the instance returned from merge/save when handling detached entities.
- [ ] Can distinguish flush from commit.
- [ ] Know how to use @Version to detect concurrent updates.
- [ ] Can distinguish dirty checking from JPQL bulk update.
- [ ] Avoid overwriting entities directly with request bodies.
- [ ] Can write a test confirming managed entity changes are saved upon flush/commit.

## 19. Conclusion

An entity that is managed in the persistence context is tracked by JPA. When properties are modified within a transaction, dirty checking detects the changes and Hibernate writes SQL upon flush or commit. Therefore, a service method annotated with @Transactional usually only needs to load the entity, call update methods, and finish the transaction.

save() remains useful when creating new entities or when merging detached entities. Properly understanding entity states, transactions, and flush helps avoid unnecessary save() calls, reduces redundant persistence operations, and protects data under concurrent transactions.