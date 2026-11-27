# Controlling New State with Persistable

Spring Data needs to determine whether an entity represents a new record or an existing record in order to choose the appropriate write operation. When calling repository `save`, a new entity normally takes the insert branch; an existing entity takes the update branch.

Spring Data Relational has a default new-state detection mechanism based on the version or ID property. When that rule does not fit the application's identity model, you can implement **Persistable** to determine the result yourself via the **isNew()** method.

Persistable is especially useful when the application assigns IDs before inserting, such as UUIDs, or when an entity's new state cannot be inferred from the ID alone. Because isNew() decides the write branch, the state flag must be initialized, updated, and excluded from persistent mapping consistently.

## 1. Why Does Spring Data Need to Know Whether an Entity Is New?

Repositories in Spring Data provide the `save` method to persist entities. At the moment `save` is called, the framework must select the right operation:

- New entity: execute insert to create a record.
- Existing entity: execute update to modify an existing record.

Spring Data cannot always infer this state by querying the database before every save. Instead, it applies new-state detection rules directly on the entity.

This matters for entities with application-generated IDs. For example, an order might receive a UUID as soon as it is constructed, before the record is inserted. Looking only at the ID, the framework could mistakenly assume the entity already exists because the ID is non-null.

Persistable lets the domain model provide an explicit answer to the question: "Is this entity currently new or already persisted?"

## 2. Default New-State Detection Mechanism

When an entity does not implement Persistable, Spring Data Relational typically uses persistent properties to determine new state.

### 2.1. Prioritizing the @Version Property

If the entity has a non-primitive version property, Spring Data uses the version value to detect state:

- Version is null: entity is considered new.
- Version has a value: entity is considered existing.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id String id,
    String description,
    @Version Long version
) {}
~~~

The application can assign the ID before saving while leaving version null:

~~~java
PurchaseOrder order =
    new PurchaseOrder("PO-2026-001", "Office supplies", null);
~~~

Even though the ID already has a value, the null version still indicates that the entity is new under version-based detection.

When insert succeeds, Spring Data manages the version via optimistic locking and the returned entity carries the appropriate version. Subsequent saves can then be detected as updates.

Using a wrapper type like Long or Integer for version allows representing the unassigned state with null. If version is a primitive type, it cannot be null; in that case default version-based detection does not carry the same semantics and Spring Data has to fall back on its rules for ID or primitive defaults.

### 2.2. Checking ID When There Is No @Version

If the entity has no suitable version property, Spring Data checks the ID:

- ID is null: entity is considered new.
- ID has a value: entity is considered existing.

Example:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    String fullName
) {}
~~~

A newly created entity usually has a null ID:

~~~java
Customer customer = new Customer(null, "Nguyen An");
~~~

This mechanism works well when the database generates IDs automatically, such as an identity or sequence supported by the driver and database during insert.

### 2.3. Limitations When IDs Are Pre-Assigned

Suppose the application creates a UUID before writing:

~~~java
import java.util.UUID;

Customer customer =
    new Customer(UUID.randomUUID(), "Nguyen An");
~~~

If the entity has no suitable version property, the non-null ID causes the default mechanism to treat the entity as existing. The repository may select update even though that record does not exist in the database yet.

This is the exact scenario Persistable solves: new state can be independent of whether an ID has already been assigned.

## 3. What Is Persistable?

Persistable is an interface from Spring Data Commons that allows an entity to supply its own ID and new state.

~~~java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
~~~

When an entity implements Persistable, Spring Data delegates the new-state decision to the entity's isNew() method.

The two methods mean:

- getId(): returns the identifier Spring Data uses for the entity.
- isNew(): returns true if the entity needs to be inserted; returns false if the entity already exists and needs to be updated.

Persistable does not generate SQL, does not query the database, and does not generate IDs itself. It only controls whether an entity takes the insert or update branch during save.

## 4. Implementing Persistable with Application-Assigned IDs

A common pattern is using a boolean flag that is not persisted to the database. The flag starts as true when the application constructs a new entity; after the entity is inserted or loaded from the database, the flag transitions to false.

Order entity example:

~~~java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder implements Persistable<UUID> {

    @Id
    private UUID id;

    private String description;

    @Transient
    private boolean newEntity = true;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(UUID id, String description) {
        this.id = id;
        this.description = description;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Several important points:

- The ID is assigned right when creating the entity.
- newEntity initializes to true so the first save chooses insert.
- Spring Data's @Transient excludes the newEntity flag from database mapping.
- After insert succeeds, the flag must switch to false.
- When the entity is loaded from the database, the flag must also be false so the next save chooses update.

Never leave this flag permanently true. If an already saved entity still returns true from isNew(), the next save may keep taking the insert branch and trigger duplicate primary key errors.

## 5. Updating State After Insert and When Reading Data

A Persistable implementation is only correct when the lifecycle of the state flag is managed completely.

There are two moments that must be handled:

1. After a successful save: the entity is no longer new.
2. After loading an entity from the database: the entity already exists.

Spring Data Relational provides entity callbacks to hook into save and read lifecycles. You can use an after-save callback to mark an entity as saved, and an after-convert callback on read data to mark loaded entities as existing.

With the mutable entity in the example above, the callback can call markNotNew(). Illustrative after-save handling body:

~~~java
entity.markNotNew();
return entity;
~~~

With the callback after converting a Row into an entity, the same operation applies:

~~~java
entity.markNotNew();
return entity;
~~~

The two snippets above illustrate the action inside each corresponding callback; when implementing, use the exact callback interface and method signatures of the Spring Data Relational version in your project.

If the application does not use callbacks, it can update the flag in the service after the save publisher emits a successful result. However, that approach requires every write path to pass through that service and every read path to ensure the entity state is marked properly. Callbacks usually centralize the rule better.

### 5.1. Why Must Both After-Save and After-Load Be Handled?

Marking only after save is not enough.

For example:

1. An entity is inserted successfully.
2. The application restarts.
3. The entity is loaded from the database.
4. If the transient flag always initializes to true and is never reset, isNew() will return true.
5. When saving the freshly loaded entity, Spring Data may choose insert instead of update.

A transient flag is not restored from the database because it is not a persistent column. Therefore, a callback after reading data must set the new state to false.

### 5.2. Callbacks Must Run at the Right Time

Marking an entity as existing before the insert succeeds can leave in-memory state out of sync with persistence results. If the insert fails after the flag has been flipped to false, a retry might wrongly choose update.

Update the state after the save operation succeeds. When using transactions, understand at which stage in the persistence lifecycle the callback is invoked and how the application handles rollbacks; do not treat callback execution alone as proof that the overall transaction is guaranteed to commit.

## 6. Using Persistable with Spring Data R2DBC Repositories

The repository still uses ReactiveCrudRepository as usual:

~~~java
import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, UUID> {
}
~~~

When calling save, Spring Data queries the entity's new state:

~~~java
import java.util.UUID;

import reactor.core.publisher.Mono;

public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> create(String description) {
        PurchaseOrder order =
            new PurchaseOrder(UUID.randomUUID(), description);

        return repository.save(order);
    }
}
~~~

Because the new entity's isNew() returns true, the repository selects insert even though the ID was pre-assigned.

After the insert succeeds, the callback must mark the entity as no longer new. If using a mutable entity and the callback returns the entity after updating the flag, the caller can continue using the save result.

~~~java
return repository.save(order)
    .map(saved -> {
        // Continue processing the saved entity.
        return saved;
    });
~~~

Do not call subscribe() yourself in the service to force saving. Return the Mono or Flux to the upper caller to preserve the reactive flow and ensure errors propagate through the publisher.

## 7. Persistable and Immutable Entities

Persistable does not force entities to be mutable. However, the state flag in the earlier example is mutated in place, making it suited to mutable classes.

With immutable entities, the new state must also be represented immutably. You can design the entity so callbacks construct a new instance with isNew=false after saving or after reading.

Conceptual model example:

~~~java
public final class PurchaseOrder implements Persistable<UUID> {

    private final UUID id;
    private final String description;
    private final boolean newEntity;

    public PurchaseOrder(
            UUID id,
            String description,
            boolean newEntity) {
        this.id = id;
        this.description = description;
        this.newEntity = newEntity;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public PurchaseOrder markNotNew() {
        return new PurchaseOrder(id, description, false);
    }
}
~~~

The after-save or after-convert callback must return the new instance from markNotNew(). You cannot just invoke a setter on an immutable entity because there are no setters and the fields cannot be mutated.

With an immutable entity that has a wrapper version property, consider using the default version-based mechanism before adding a separate Persistable flag. If a null version accurately represents a new entity, the default approach is usually simpler with less state to keep in sync.

## 8. Comparing New-State Detection Approaches

| Detection Approach | Rule | Suitable When |
|---|---|---|
| @Version | Null wrapper version means new; populated value means existing | Optimistic locking is used or version is a suitable state indicator |
| @Id | Null ID means new; populated value means existing | Database generates ID and new entities lack an ID |
| Persistable.isNew() | Entity itself answers true/false | ID is pre-assigned or custom new-state rules are required |

Prefer the default mechanism whenever it accurately reflects your data model. Use Persistable when the application needs explicit control over new state.

## 9. Common Mistakes When Using Persistable

### 9.1. Always Returning True

If isNew() is always true, every save may choose insert. When the record already exists, the database may report a primary key or unique constraint violation.

Fix: flip the flag to false after successful insert and when loading the entity from the database.

### 9.2. Always Returning False

New entities will take the update branch. If the record does not exist, the operation may fail to create data as expected or raise an optimistic locking error depending on configuration.

Fix: initialize new state properly across the entity lifecycle.

### 9.3. Marking as Saved Immediately on Object Creation

Having an assigned ID does not mean the entity has been inserted. If the application generates a UUID and immediately sets isNew=false, Spring Data may select update for a nonexistent record.

Fix: keep "has an ID" separate from "exists in the database."

### 9.4. Forgetting to Mark the Entity After Reading

The @Transient flag is not saved to the database. An entity newly reconstructed from a Row initializes the flag to the class's default value, which is often true if using the earlier example.

Fix: use an after-convert/load callback to set the flag to false.

### 9.5. Persisting the State Flag as a Column

If you forget @Transient, Spring Data may treat the newEntity flag as a persistent property and attempt to map it to a column.

Fix: use org.springframework.data.annotation.Transient on properties intended only for in-memory persistence logic.

### 9.6. Updating the Flag Before Save Completes

If the flag turns false before the insert succeeds, a retry after an error might mistakenly choose update.

Fix: transition the flag at the post-save success stage or use an appropriate lifecycle callback.

### 9.7. Sharing a Mutable Entity Across Multiple Requests

An instance with an isNew flag and mutable properties could be modified concurrently by multiple execution paths. This creates a race condition: one path might flip the flag while another is still saving.

Fix: do not share mutable instances being saved across requests; each business unit of work should own its own entity.

## 10. Persistable Does Not Replace ID Generation

Persistable only controls the insert/update choice. It does not create IDs, configure sequences, generate UUIDs, or guarantee the database can store that ID.

If the application uses self-assigned UUIDs:

- Generate the UUID before inserting.
- Ensure the database column type is compatible.
- Implement getId() to return the UUID.
- isNew() must return true for new instances.
- After saving and upon reading back, the state must become false.

If the database generates IDs automatically:

- Leave the ID null when constructing a new entity.
- Use the default ID-based mechanism if appropriate.
- Or use a null wrapper version if version-based detection is already designed in.
- Only use Persistable when there is a clear reason to alter state detection.

## 11. Notes on Optimistic Locking

Persistable and @Version solve two related yet distinct problems:

- Persistable.isNew() decides whether the entity takes insert or update.
- @Version checks whether the update is based on the data version that the entity read.

Do not use an isNew flag as a substitute for version. An entity may already exist while its data was modified by another transaction; @Version detects that conflict.

If an entity implements Persistable and also has @Version, make sure the two signals do not contradict each other. For example, an entity with a null version where isNew() returns false will be governed by Persistable. Persistable takes precedence for new state, so a bug in isNew() can pick the wrong save branch even when version shows the entity has not been saved yet.

## 12. When Should You Use Persistable?

Use Persistable when:

- The ID is assigned by the application before insert, such as a UUID, and there is no suitable version property to determine new state.
- Rules for determining whether an entity is new depend on domain information other than the ID.
- You need active control over insert vs. update in a specific persistence model.
- You can ensure the state flag is properly initialized and transitioned across entity creation, save, and read lifecycles.

You do not need to implement Persistable merely because an entity uses UUIDs. If the entity has a wrapper @Version that is null when new and updated by Spring Data after insert, the default mechanism may already be sufficient.

## 13. Workflow for Using Persistable in an Application

A typical workflow with application-assigned IDs:

1. Create a new entity and assign an ID.
2. Initialize the transient flag so isNew() returns true.
3. Call repository.save(entity).
4. Spring Data sees a new entity and executes insert.
5. After saving succeeds, a callback transitions entity state to existing.
6. When the entity is read from the database, an after-convert callback also sets state to existing.
7. Subsequent saves take the update branch.

~~~mermaid
flowchart TD
    A["Create entity, assign ID"]
    B["isNew() = true"]
    C["repository.save(entity)"]
    D["INSERT"]
    E["After successful save: isNew = false"]
    F["Read entity from database"]
    G["After convert/load: isNew = false"]
    H["Subsequent save"]
    I["UPDATE"]

    A --> B
    B --> C
    C --> D
    D --> E
    F --> G
    E --> H
    G --> H
    H --> I
~~~

If the insert fails, the entity must not be considered saved simply because its ID already has a value. Keep the new state so errors can be handled or retried according to application policy.

## 14. Key Takeaways

Spring Data needs to know whether an entity is new or existing to choose insert or update. By default, the framework can rely on @Version or @Id. When IDs are pre-assigned or default rules do not match the data lifecycle, an entity can implement Persistable and provide isNew().

A reliable Persistable implementation must manage state across the entire entity lifecycle: true on creation, false after successful save, and false when read back from the database. The state flag must be annotated with @Transient so it does not become a database column. Persistable only controls new-state detection; it does not generate IDs, replace @Version, or verify record existence.

When using Spring Data R2DBC, keep publishers reactive throughout the service and handle insert/update errors explicitly. If the default ID or version mechanism already fits, use it; only add Persistable when the application genuinely needs to control new state directly.
