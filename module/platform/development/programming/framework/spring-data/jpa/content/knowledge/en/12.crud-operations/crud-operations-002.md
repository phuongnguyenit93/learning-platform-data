# Detecting New Entities via `@Version`, `@Id`, and `Persistable` in Spring Data JPA

When calling `JpaRepository.save(entity)`, Spring Data JPA must decide whether the entity is considered **new** or **existing** to choose the operation on the JPA `EntityManager`. This decision is based on the entity state that the repository infers from metadata and property values; it is **not** a query that verifies whether the record exists in the database.

After this lesson, you will be able to explain the priority order `Persistable` → object-type version → ID, predict the `persist`/`merge` branch in common cases, and properly handle entities with manually assigned IDs.

## 1. How Does `save()` Use the New-Entity Detection Result?

The core idea of `SimpleJpaRepository.save(...)` can be summarized as follows (code illustrating Spring Data JPA's internal mechanism, not a standalone runnable program):

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}
return entityManager.merge(entity);
```

- **`isNew(entity) == true`**: the repository calls `persist`. The object is placed into the persistence context for INSERT according to JPA rules; when SQL is issued may depend on the ID generation strategy and `flush`.
- **`isNew(entity) == false`**: the repository calls `merge`. JPA copies the state to a managed object and returns that managed object (which may be a different instance from the input). Therefore, use the value returned by `save(...)`.
- `saveAndFlush(...)` still uses the same detection logic as `save(...)`, and then requests a `flush`. `saveAll(...)` applies `save` sequentially to each entity.

`isNew` is a signal to select the JPA API, not synonymous with `entityManager.contains(entity)` and not an existence check in the database. An entity that has an ID but has not been INSERTed yet can still be inferred as "existing"; conversely, an ID marked as "new" can still collide with the primary key of an existing row.

## 2. Rules for Selecting the Detection Strategy

In **Spring Data JPA**, the actual order of precedence applied is:

1. **Entity implements `org.springframework.data.domain.Persistable<ID>`**: uses `entity.isNew()` directly. The developer is responsible for maintaining the new/existing state.
2. **Does not implement `Persistable` and has a `@jakarta.persistence.Version` property of a reference type** such as `Long` or `Integer`: `version == null` → new; `version != null` → not new. **This result takes precedence over the ID value.**
3. **No suitable reference-type version**: inspects `@Id`. `null` ID → new, non-`null` ID → not new. For primitive numeric IDs, a value of `0` is considered new under the basic ID check mechanism.

Common point of confusion: **`@Version long` or `@Version int` (primitive types) are not used by Spring Data JPA for newness detection.** JPA allows the initial version to have a value of `0`; therefore, `version == 0` is not enough to conclude that an entity is new. When the version is primitive, Spring Data JPA falls back to checking the ID. General Spring Data Commons documentation describes primitive version detection in some other modules; for `JpaRepository`, follow the specific rules of **Spring Data JPA**.

Decision table (assuming the entity does not implement `Persistable`, except the last row):

| Scenario | ID | `@Version` | `isNew` | `save` branch |
|---|---|---|---|---|
| Auto-generated ID, unsaved, no version | `null` | None | `true` | `persist` |
| Manually assigned ID, unsaved, no version | `"BK-01"` | None | `false` | `merge` |
| Manually assigned ID, `Long` version not set | `"BK-01"` | `null` | `true` | `persist` |
| Entity already has `Long` version | `"BK-01"` | `0L` or `1L` | `false` | `merge` |
| Manually assigned ID, `long` version equal to 0 | `"BK-01"` | `0` (primitive) | `false` | `merge` (checks ID) |
| `Long` ID set to `0L`, no version | `0L` | None | `false` | `merge` (still non-`null`) |
| `Persistable.isNew()` returns `true` | `"BK-01"` | Any | `true` | `persist` |

Here, "not new" is only **Spring Data JPA's conclusion**; it does not assert that the corresponding row actually exists. The JPA provider may need to SELECT, issue an UPDATE/INSERT, or throw an error depending on data state, version, and transaction context.

## 3. Detection via ID: Simple When IDs Are Auto-Generated

JPA example with a database-generated ID (the snippet below belongs to a Spring Boot 3+/Java 17+ project with Spring Data JPA, not runnable standalone via `javac` without dependencies):

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {} // JPA requires a no-arg constructor

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

`new Customer("An")` has `id == null`, so by default it is detected as new and `save` calls `persist`. Once the ID is assigned, if there is no reference-type version, an entity with a non-`null` ID is detected as not new. Wrapper-type IDs (`Long`) represent the unassigned state more clearly than `long`, which defaults to `0`.

**Special case – manually assigned ID:** with `@Id private String code;` and `code = "BK-01"` set upon object creation, the default ID check yields `isNew == false` even though the record has never been saved. Thus `save` takes the `merge` path. Do not equate "already has an ID" with "already has a row in the database".

## 4. Detection via Wrapper `@Version`

`@Version` is JPA metadata used for **optimistic locking**: the provider maintains a version number to detect conflicting updates. In Spring Data JPA, an object-type version also helps distinguish new entities when the ID is pre-assigned.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {
    @Id
    private String sku; // Application-assigned ID

    @Version
    private Long version; // null when newly created

    private String name;

    protected Product() {}

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public String getSku() {
        return sku;
    }

    public Long getVersion() {
        return version;
    }
}
```

Progression:

1. `new Product("SKU-01", "Keyboard")` has `sku != null` but `version == null`. Spring Data JPA **prioritizes version**, detects it as **new**, and calls `persist`.
2. When the entity is successfully saved, the JPA provider manages the version. Once it has a non-`null` version value, subsequent detections evaluate to **not new**.
3. An entity loaded from the database normally has an initialized version and is considered **not new**.

Use `Long` (or an appropriate wrapper) and avoid replacing it with `long` if you rely on this strategy. **Do not manually set `version = 0L` on a new object**: `0L` is non-`null`, which can cause the repository to choose `merge`. The version should be managed by JPA; a stale version during an update can also cause optimistic locking errors at flush/commit.

If the entity has no reference-type version, or the version is primitive, Spring Data JPA uses the ID rule in section 3.

## 5. `Persistable<ID>`: Customizing Whether an Entity Is New

`Persistable` is particularly useful for **manually assigned IDs without `@Version`**. You store a flag **not mapped to the database**, initialized to `true` for a new entity and switched to `false` after inserting or after JPA loads the entity.

Complete example of the entity class (file `CatalogEntry.java`, placed in your application package):

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

import java.util.Objects;

@Entity
@Table(name = "catalog_entries")
public class CatalogEntry implements Persistable<String> {
    @Id
    private String code;

    private String displayName;

    @Transient
    private boolean newEntity = true;

    protected CatalogEntry() {} // For JPA

    public CatalogEntry(String code, String displayName) {
        this.code = Objects.requireNonNull(code, "code");
        this.displayName = Objects.requireNonNull(displayName, "displayName");
    }

    @Override
    public String getId() {
        return code;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Repository (file `CatalogEntryRepository.java`, same package):

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogEntryRepository
        extends JpaRepository<CatalogEntry, String> {
}
```

Role of each part:

- `getId()` provides the identifier for `Persistable<String>`; `isNew()` is the signal Spring Data JPA trusts, **taking precedence over both ID and version**.
- `newEntity = true` applies to objects newly created by application code; thus `new CatalogEntry("BK-01", "Java")` with a non-`null` ID still enters `persist`.
- `@jakarta.persistence.Transient` prevents the `newEntity` flag from becoming a persisted column. With JPA property access, you must also ensure `isNew` is not accidentally mapped as a persistent property.
- `@PostPersist` sets the flag to `false` **after it has actually been persisted**; `@PostLoad` sets the flag to `false` when JPA instantiates the entity from stored data. If `save` is called and the INSERT has not flushed yet, the `@PostPersist` callback may not have fired immediately.
- `Persistable` does not check the database on its own. Setting `isNew() == true` for an already existing key can lead to primary key collisions or entity state errors on `persist`.

This pattern relies on official JPA lifecycle callbacks; the flag and callbacks can be placed in a shared `@MappedSuperclass` if multiple entities use manually assigned IDs.

### An Integration Test for the State Flag

The following test assumes `spring-boot-starter-data-jpa`, `spring-boot-starter-test`, a test database (e.g., H2), and classes placed in packages scanned by Spring Boot. This is a project test, not plain Java runnable via `java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class CatalogEntryRepositoryTest {
    @Autowired
    CatalogEntryRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void assignedIdIsNewUntilPersisted() {
        CatalogEntry candidate =
                new CatalogEntry("BK-01", "Practical Java");

        assertTrue(candidate.isNew());

        CatalogEntry saved = repository.saveAndFlush(candidate);
        assertFalse(saved.isNew()); // @PostPersist has run

        entityManager.clear(); // Force reload from the database
        CatalogEntry loaded =
                repository.findById("BK-01").orElseThrow();

        assertFalse(loaded.isNew()); // @PostLoad has run
    }
}
```

Expected result: all three assertions pass. `clear()` forces the subsequent `findById` to go through the load process, thereby verifying the `@PostLoad` callback as well.

## 6. Comparing Options in Real Projects

| Identifier/entity type | Recommended detection approach | Why |
|---|---|---|
| Auto-generated ID (`@GeneratedValue`), no version needed | Default `@Id` check with wrapper type | New objects usually have a `null` ID |
| Entity with optimistic locking | `@Version Long`/wrapper | `null` represents new and JPA manages the version |
| Manually assigned ID, no version | `Persistable<ID>` with transient flag and callbacks | ID is non-`null` before INSERT |
| Manually assigned ID, with wrapper version | Usually default `@Version` | `null` version is enough to signal a new entity |
| Rules don't fit the three approaches above | Customize `EntityInformation`/`JpaRepositoryFactory` | Advanced scenario, rarely needed and must be thoroughly tested |

Do not implement `Persistable` just to force every `save` call into an INSERT. Use it when **the entity lifecycle allows you to determine the new state accurately**, and remember to synchronize the flag when reading entities.

## 7. Common Pitfalls and How to Self-Check

1. **Assuming `save` always means INSERT or UPDATE based on whether the database already has the key.** In reality, Spring Data JPA chooses `persist`/`merge` from `isNew` first; trace the detection strategy rather than guessing from the method name.
2. **Manually assigning an ID and being surprised by `merge` or an extra SELECT.** With a non-`null` ID and no wrapper version/Persistable, that is the default behavior. Consider `@Version Long` or the `Persistable` pattern if the semantics fit.
3. **Using `@Version long` and treating `0` as "new".** In Spring Data **JPA**, primitive versions are not used for newness detection; switch to `Long` if you need a `null` indicator.
4. **Pre-assigning a version on a new entity.** A non-`null` wrapper version makes Spring Data JPA classify it as not new, potentially entering `merge` unintentionally.
5. **Forgetting `@Transient` or callbacks for the `isNew` flag.** The flag may be persisted as an unwanted column, or entities loaded from the database may still report as new, leading to an erroneous `persist` on a subsequent save.
6. **Ignoring the object returned from `merge`.** Continue operating on `saved = repository.save(entity)` because JPA may return a managed instance different from the passed object.
7. **Expecting `@PostPersist` to run immediately after an unflushed `save`.** INSERT timing and callbacks depend on flush/transaction; use `saveAndFlush` in tests where immediate observation is needed and verify transaction state.
8. **Treating `isNew` as a deduplication mechanism.** It does not replace primary key/unique constraints, concurrency control, optimistic locking, or an explicit upsert workflow.

When diagnosing, ask in order: Does the entity implement `Persistable` and what does `isNew()` return? If not, does it have a wrapper `@Version` and is it `null`? If not, is the ID currently `null` or another value? Then inspect the JPA/provider version, `flush` timing, and actual SQL via an integration test if needed. These questions explain the behavior far more accurately than guessing "it has an ID so it's saved".

## 8. Decision Summary

- **`Persistable`:** uses the entity's `isNew()`.
- **Default with reference-type `@Version`:** `null` → `persist`; non-`null` → `merge`.
- **Otherwise:** `null` ID (or primitive number equal to `0`) → `persist`; non-empty ID → `merge`.
- **Specific to Spring Data JPA:** primitive `@Version` does not determine newness.
- **Core principle:** the repository's decision routes the JPA operation; actual database existence and SQL timing are governed by JPA/provider, transactions, and data constraints.

## References

- Spring Data JPA – Persisting Entities, Entity State-detection Strategies: https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html
- `SimpleJpaRepository.save` source code (`isNew` detection and `persist`/`merge` calls): https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java
- Spring Data Commons – Entity State Detection Strategies (for comparing differences across modules): https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html