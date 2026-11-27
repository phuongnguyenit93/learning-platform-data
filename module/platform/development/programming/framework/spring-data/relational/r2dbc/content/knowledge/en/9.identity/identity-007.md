# Relationship Between `@Version` Properties and New-Entity Detection

When calling `save()` in Spring Data Relational R2DBC, the framework must decide whether to execute an INSERT or an UPDATE operation. This decision is based on the entity's new/existing state (new state). Spring Data does not, by default, send a SELECT query to check whether the ID already exists in the database; it uses object metadata and state to determine the write direction.

Normally, Spring Data checks the ID property. However, if the entity has a property annotated with `@Version`, the version property takes precedence for detecting new entities. This creates an important connection between **new-entity detection** and **optimistic locking**:

- An unset version indicates a new entity.
- A populated version indicates an existing entity.
- For an existing entity, the version is used to check whether the record was modified by another transaction since it was read.

Therefore, `@Version` is not merely a column counting the number of updates. It also directly influences whether Spring Data chooses INSERT or UPDATE when saving an entity.

## 1. Why Does Spring Data Need to Detect New Entities?

A repository can expose the same `save()` method for both new and existing entities:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

However, the two cases require different SQL statements:

- A new entity must be added to the table with INSERT.
- An existing entity must be modified with UPDATE.

Spring Data must determine the state before executing the save operation. This mechanism is called entity state detection or new-state detection.

Example `customer` table:

| id | name | version |
|---:|---|---:|
| 10 | An | 3 |
| 11 | Binh | 5 |

A new object might not have a database-generated ID yet. Yet many systems use pre-assigned IDs, such as UUIDs or application-generated IDs. In those cases, looking at the ID alone is not enough to know whether the object needs an insert or an update.

A `@Version` property helps Spring Data detect state via another signal. A new entity may already have an ID while its version remains unset.

## 2. What Is `@Version`?

`@Version` is a Spring Data annotation used to mark the version property on an entity. In Spring Data Relational, this property is used to support **optimistic locking**.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public void assignId(Long id) {
        this.id = id;
    }
}
~~~

In this example:

- `id` is the customer's identifier.
- `version` is the version of the state stored in the database.
- `name` and `email` are business data.

Be sure to use `org.springframework.data.annotation.Version` in a Spring Data Relational model. JPA's version annotation belongs to a different API and is not the annotation to use on R2DBC entities.

Version is typically an integer type such as `Long` or `Integer`. The framework manages the version value during insert/update according to the rules of the module and version in use. The application should not manually increment the version in business code as if it were an ordinary business attribute.

## 3. Order of New-Entity Detection

Under Spring Data's default mechanism, the decision order can be understood as follows:

1. If the entity implements `Persistable`, Spring Data uses the `isNew()` method provided by the entity.
2. If the entity does not implement `Persistable` but has a `@Version` property, Spring Data checks the version first.
3. If there is no version property, Spring Data checks the ID.

Version taking precedence over ID is the central point of this lesson. When a version property is present, Spring Data does not simply ignore it and fall back to using the ID for the decision.

### When a `@Version` Property Is Present

With a nullable wrapper version property such as `Long`:

- `version == null`: the entity is treated as new.
- `version != null`: the entity is treated as existing.

With a primitive integer version property such as `long` or `int`, the default value `0` is treated as the new state; any non-`0` value is treated as the existing state.

A point to watch: when using the `Long` wrapper, the value `0L` is still a non-null value. Therefore, a new object with `version = 0L` is treated as existing under the wrapper's null check. When relying on version to detect new entities, leave the wrapper version as `null` before the first save.

### When There Is No `@Version` Property

Spring Data falls back to checking the ID:

- Wrapper ID with value `null`: new entity.
- Primitive integer ID with default value `0`: new entity.
- ID with a value other than the new-state marker: entity is treated as existing.

This matters for pre-assigned IDs. If an entity has an assigned UUID and no version property, Spring Data may by default treat the entity as existing and choose update. If you need to insert entities with pre-assigned IDs, you must use an appropriate state-detection mechanism, such as a nullable version or `Persistable`.

## 4. State Table: How Version Affects the Decision

The following table illustrates the default rules for an entity that does not implement `Persistable`:

| ID | Version | Detection Result | Save Operation |
|---|---|---|---|
| null | null (Long) | New | INSERT |
| 42 | null (Long) | New | INSERT |
| 42 | 3L (Long) | Existing | UPDATE |
| 42 | 0L (Long) | Existing because wrapper is non-null | UPDATE |
| 42 | 0 (long) | New because primitive defaults to 0 | INSERT |
| 42 | 3 (long) | Existing | UPDATE |

Two rows with ID 42 but different versions can lead to different decisions. This is why you should not look at ID alone and conclude whether `save()` will insert or update.

If object state does not match actual data in the database, the operation may fail:

- An entity detected as new takes the insert branch. If the ID already exists, the database may report a primary key violation.
- An entity detected as existing takes the update branch. If no matching row exists, the operation does not automatically turn into an insert.
- If the update uses optimistic locking and no row matches both ID and version, Spring Data reports an optimistic locking error.

## 5. How `@Version` Changes the Save Flow

Consider a new entity with an application-assigned ID:

~~~java
Customer customer = new Customer("An", "an@example.com");
customer.assignId(42L);
// version is still null because it has not been set.
~~~

Because version is null, Spring Data detects the entity as new even though the ID already has a value. When calling:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

The framework selects the insert operation. With numeric versions, Spring Data initializes the version according to the module's rules (typically starting at 0) and returns the saved entity.

After the insert, the returned object has both ID and version populated. When using the saved entity to perform an update, version has a value, so Spring Data detects it as an existing entity and takes the update branch.

General flow:

~~~text
Create entity
   |
   +-- version has no value
   |
   v
Spring Data detects NEW
   |
   v
INSERT
   |
   v
Set initial ID / version
   |
   v
Return saved entity
   |
   +-- version has a value
   |
   v
Spring Data detects EXISTING
   |
   v
Conditional UPDATE by ID and version
   |
   v
Increment version and return new entity
~~~

Always use the object returned from `save()`:

~~~java
return customerRepository.save(customer)
    .flatMap(savedCustomer -> {
        // savedCustomer contains ID/version after persistence
        return Mono.just(savedCustomer);
    });
~~~

This is especially important for immutable entities or when the framework updates ID/version by creating a new instance. Do not discard the returned result and continue using the old object with an outdated version.

## 6. `@Version` and Optimistic Locking

Optimistic locking assumes write conflicts occur infrequently. Instead of locking the record for the entire duration a user reads and edits it, the application retains the version that was read. On write, the database updates only if the current version still equals the version the application read.

Initial example:

| id | name | version |
|---:|---|---:|
| 42 | An | 5 |

Two requests A and B both read the customer with version 5.

| Time | Request A | Request B | Database |
|---|---|---|---|
| T1 | Read version 5 | | version 5 |
| T2 | | Read version 5 | version 5 |
| T3 | Update name, send version 5 | | version 5 |
| T4 | Update succeeds, version becomes 6 | | version 6 |
| T5 | | Send update with stale version 5 | version 6 |
| T6 | | No row matches ID and version 5 | version 6 |

Conceptually, the update statement is equivalent to:

~~~sql
UPDATE customer
SET name = :name,
    version = :next_version
WHERE id = :id
  AND version = :previous_version;
~~~

Request A updates successfully because the database has version 5. The version advances to 6. Request B still sends version 5, but the database already has version 6; the WHERE condition does not match, so zero rows are updated.

Spring Data sees that the affected row count is not as expected and raises an optimistic locking error, typically as `OptimisticLockingFailureException`. The application can return a conflict error to the client, reload fresh data and ask the user to resolve changes, or execute a business-appropriate merge/retry strategy.

`@Version` is also used to guard version-checked delete operations where supported by Spring Data. A stale entity should not delete a record that was updated by another request without detecting the conflict.

## 7. Distinguishing Version from ID

ID and version serve different roles:

| Property | ID | Version |
|---|---|---|
| Purpose | Identifies the entity | Identifies the version of the read/saved state |
| Changes across updates | Normally no | Incremented on successful update |
| Used as primary key | Usually yes | No |
| Supports new-state detection | Yes, when no version or custom strategy exists | Takes precedence if a version property exists |
| Supports optimistic locking | Not by itself | Yes |

Do not use version as a second ID. Two different entities can both have version 0, 1, or 5; a version value is meaningful only within the scope of a single record.

Do not use version to store update timestamps or business status. If you need `updatedAt`, use a dedicated timestamp property and an appropriate auditing mechanism. Version is a concurrency-control token, not user-facing display data.

## 8. `Persistable` and Cases Requiring Manual State Control

Spring Data provides the `Persistable<ID>` interface so an entity can supply:

- `getId()` returning the identifier.
- `isNew()` indicating whether the entity is new.

When an entity implements `Persistable`, Spring Data uses `isNew()` supplied by the entity instead of the default version/ID strategy. This is useful when the application has special detection rules, such as IDs always assigned before insert.

Illustrative example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import java.util.UUID;

public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    protected Customer() {
        // An entity reconstructed by Spring Data from the database is an existing entity.
        this.newEntity = false;
    }

    public static Customer newCustomer(UUID id) {
        Customer customer = new Customer();
        customer.id = id;
        customer.newEntity = true;
        return customer;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

This is an illustrative skeleton for a custom strategy; the application must manage when `newEntity` transitions to false consistently with persistence outcomes, such as via an appropriate lifecycle callback or factory/domain flow. Never mark an entity as existing before insert succeeds.

If `@Version` is already present, you should normally leverage the default strategy before adding manual `Persistable` state. Both mechanisms can coexist, but `Persistable.isNew()` will govern the new-state decision; if implemented incorrectly, it can defeat version-based detection.

## 9. Scenarios to Watch Out For

### Entities with Pre-Assigned IDs

If a new entity has a UUID or application-assigned ID, leaving `@Version Long` as null lets Spring Data detect the entity as new and insert it. If there is no version property, a non-null ID can cause the default strategy to choose update. In that case, consider `Persistable` or an appropriate ID strategy.

### New Entity with Wrapper Version Initialized to 0

With a `Long` version, `0L` is non-null. Under version-based detection, it signifies existing. If you want new entities detected via a wrapper version, leave the version field null before the first save. With a primitive `long`, the default value `0` is treated as new.

### Existing Entity Whose Version Was Reset to Null

If you load an existing entity and accidentally set its version back to null, Spring Data may treat that object as new and choose insert. If the ID already exists, the insert may fail with a duplicate key. Do not edit version values manually.

### Entity with a Version That Does Not Match the Database

If the object's version is older than the database's, the update fails the optimistic locking condition and triggers a conflict error. If the object's version is higher or missing in the database, the operation still does not automatically switch to insert.

### Immutable Entities

With immutable entities, the framework may create a new instance when setting ID or version. Therefore, always continue the pipeline with the entity returned from `save()` instead of assuming the original object was modified in place.

### Multiple Repositories or Multiple ConnectionFactories

Optimistic locking can only protect operations executed through mappings and databases that honor the version. If another write path updates data columns directly without incrementing the version, conflict detection can be bypassed. All write paths to the table should follow the same version convention.

## 10. Handling Optimistic Locking Errors in a Reactive Pipeline

With R2DBC, `save` is reactive and errors are emitted when the publisher is subscribed to. You can translate optimistic locking failures into business responses at the service layer:

~~~java
public Mono<Customer> update(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new CustomerConflictException(
                "Customer was changed by another request",
                error
            )
        );
}
~~~

The business exception name in the example is an application-defined type. The web layer can map this error to HTTP 409 Conflict if appropriate for the API contract.

Do not automatically retry an update with the exact same entity and stale version. Such a retry keeps sending a version condition that is no longer valid. If business logic permits retrying, reload the fresh state, reapply changes according to clear rules, and then save the entity with the new version.

For multi-step operations, reactive transactions can ensure related database steps commit or roll back together. However, transactions do not replace optimistic locking: transactions control atomicity of a group of operations, while version detects concurrent modifications to an entity.

## 11. Designing the Version Column and Save Workflow

The schema must have a version column matching the `@Version`-annotated property. Example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Exact data type and default details must match the database and how Spring Data manages versions. If the framework sets the version on insert, do not let a trigger or other logic increment the version outside the convention your application uses.

A typical save workflow:

1. Create a new entity with an unset version (if using a nullable wrapper).
2. Call `save()` and continue with the returned entity.
3. When reading an existing entity, preserve the loaded version.
4. When updating, pass back the entity with the old version the application read.
5. If the update succeeds, use the new version returned.
6. If optimistic locking fails, reload data and resolve the conflict per business rules.

Do not accept version values from clients without validation. If an API lets clients send version as a concurrency token, validate and map it explicitly; never allow a client to supply an arbitrary version to bypass concurrency control.

## 12. Key Takeaways

- `save()` needs to know whether an entity is new or existing to select INSERT or UPDATE.
- If an entity has `@Version`, Spring Data prioritizes the version property for new-state detection ahead of ID.
- With a wrapper version like `Long`, `null` indicates a new entity; a non-null value indicates an existing entity.
- With a primitive integer version like `int` or `long`, the default value `0` is treated as new.
- Without `@Version`, Spring Data typically relies on ID; an already-assigned ID can cause the entity to be treated as existing.
- `Persistable.isNew()` lets an entity control new-state detection itself and takes precedence over the default strategy.
- After insert, version is initialized; after a successful update, version is incremented. Always use the entity returned by `save()`.
- Optimistic locking compares the current version with the version read; if they do not match, Spring Data reports an error instead of silently overwriting another request's changes.
- ID identifies the entity; version identifies the state revision of the entity. The two properties do not replace each other.
