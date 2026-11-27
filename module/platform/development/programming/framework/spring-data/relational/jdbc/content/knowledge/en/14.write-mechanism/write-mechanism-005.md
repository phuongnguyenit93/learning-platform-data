# Distinguishing save from JPA's merge and Dirty Checking

## 1. Why do operations that all mean "save" behave differently?

When working with relational data, three terms frequently appear: `save`, `merge`, and `dirty checking`. All three relate to pushing changes from Java down to the database, yet **they are not three different names for the same operation**.

- In **Spring Data JDBC**, `repository.save(entity)` is an explicit persistence call. The framework determines whether the entity is new or existing, then executes an insert or update for the aggregate.
- In **JPA**, `EntityManager.persist(entity)` transitions a new entity into the managed state; `EntityManager.merge(entity)` copies the state of a passed entity into a managed instance.
- **JPA dirty checking** tracks changes on entities currently managed inside a persistence context. At flush time, the provider synchronizes those changes to the database; as a result, calling `save` after modifying each field is often unnecessary.

This is a foundational difference when learning Spring Data Relational JDBC or migrating an application from Spring Data JPA to Spring Data JDBC. If you carry the expectation from Hibernate/JPA that "loading an entity in a transaction and modifying a field automatically saves it" into JDBC, changes may stay in memory and never be written to the database.

This lesson clarifies entity lifecycles, how the APIs operate, when SQL executes, the effect of transactions, and common scenarios that cause lost updates when using the wrong mental model.

## 2. Four concepts to separate

### 2.1. Save — asking the repository to persist state

`save` is a common method name in Spring Data repositories:

```java
repository.save(entity);
```

It is a **repository-layer API**. Its concrete semantics depend on the Spring Data module:

- Spring Data JDBC: persists the aggregate using JDBC persistence mechanics.
- Spring Data JPA: `SimpleJpaRepository.save` checks whether the entity is new or existing and calls `EntityManager.persist` or `EntityManager.merge`.

Therefore, you cannot simply look at the word `save` and conclude it always calls JPA merge, or always emits a single SQL `INSERT`.

### 2.2. Persist — placing a new entity into JPA's persistence context

`EntityManager.persist(entity)` is used for new entities. After calling it, the entity becomes managed within the current persistence context. The provider writes the entity at flush time according to JPA rules and the ID/database strategy.

`persist` does not mean "update an existing record." Passing an entity whose identifier collides with an existing entity has behavior governed by state and constraints; do not use `persist` as an update API.

### 2.3. Merge — copying state into a managed entity

`EntityManager.merge(entity)` takes the state of the passed-in object and merges that state into a managed instance. Calling `merge` does not make the passed-in instance itself become managed.

A crucial rule: **you must use the object returned by `merge`**:

```java
Account managed = entityManager.merge(detachedAccount);
```

`managed` is the managed instance in the persistence context. The original `detachedAccount` remains a detached object.

### 2.4. Dirty checking — detecting changes on managed entities

Dirty checking is the mechanism by which a JPA provider monitors the state of managed entities in a persistence context. When a property changes, the provider detects the difference relative to the loaded/tracked state and generates SQL on flush.

```java
Account account = entityManager.find(Account.class, id);
account.rename("Lan Nguyen");

// No need to call entityManager.merge(account)
// No need to call repository.save(account) in this managed case.
```

As long as `account` remains managed in the transaction, the change can be written when the transaction flushes/commits.

Dirty checking **does not work on arbitrary Java objects**. It applies only to entities actively managed in a persistence context. An object created via `new` or already detached is not automatically tracked by JPA.

## 3. Quick comparison: Spring Data JDBC vs. JPA

| Criterion | Spring Data JDBC | JPA/Hibernate |
| --- | --- | --- |
| Entity tracking model | No JPA-style persistence context/identity map | Has a persistence context managing entities |
| Modifying a newly loaded object | Must call `repository.save(...)` or an explicit write command | Managed entities undergo dirty checking on flush |
| Meaning of `save` | Requests saving the aggregate; framework picks insert/update | Spring Data JPA picks `persist` or `merge` based on newness |
| `merge` | Not a Spring Data JDBC lifecycle mechanism | JPA API to copy state into a managed instance |
| Returned object | Use the returned object because ID/version or persistence state may change | For JPA merge, must use returned instance because that is the managed one |
| Transaction | Wraps JDBC SQL statements; does not create dirty checking | Manages persistence context and flush; dirty checking occurs in context |
| Relationships/collections | Focused on aggregates and ownership | ORM manages entity associations, cascades, fetching, persistence context |
| Saving child entities | Can re-synchronize child entities belonging to aggregate on root save | Depends on managed state, cascade, owning side, and mapping |

Bottom line: **Spring Data JDBC uses an explicit save call to request a write; JPA can persist changes to managed entities without a new save call.**

## 4. Spring Data JDBC: save is an explicit write operation

Suppose there is an `accounts` table and an `Account` aggregate.

### 4.1. Model and repository

Java 21 example:

```java
package com.example.accounts;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("accounts")
public record Account(
        @Id Long id,
        String owner,
        BigDecimal balance
) {
    public Account rename(String newOwner) {
        return new Account(id, newOwner, balance);
    }
}
```

Repository:

```java
package com.example.accounts;

import org.springframework.data.repository.CrudRepository;

public interface AccountRepository
        extends CrudRepository<Account, Long> {
}
```

A record is used to illustrate an immutable object. The `rename` method returns a new instance preserving the ID and balance.

### 4.2. Modifying the object and calling save

```java
package com.example.accounts;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void rename(Long id, String newOwner) {
        Account current = accounts.findById(id)
                .orElseThrow();

        Account changed = current.rename(newOwner);

        // This is an explicit write operation.
        Account saved = accounts.save(changed);
    }
}
```

In Spring Data JDBC:

1. `findById` executes a query and constructs a Java object.
2. There is no persistence context tracking the loaded object.
3. `rename` creates a new object in the record example.
4. `accounts.save(changed)` instructs the framework to persist the aggregate.
5. SQL executes within the active transaction; the transaction commits only when the transaction boundary finishes successfully.

If the save call is omitted:

```java
@Transactional
public void renameWithoutSave(Long id, String newOwner) {
    Account current = accounts.findById(id)
            .orElseThrow();

    Account changed = current.rename(newOwner);

    // No repository.save(changed).
    // The database is not instructed to update owner.
}
```

The database keeps the old account owner name. Having `@Transactional` does not turn Spring Data JDBC into JPA and does not introduce dirty checking.

### 4.3. Illustrative SQL

When ID is `null` and the entity is detected as new, `save` follows the insert path:

```sql
INSERT INTO accounts (owner, balance)
VALUES (?, ?);
```

When the entity already exists and is detected as existing, `save` follows the update path:

```sql
UPDATE accounts
SET owner = ?, balance = ?
WHERE id = ?;
```

These shapes are illustrative; column names, bind parameter order, and exact SQL depend on mapping and dialect. For aggregates with child collections, saving the root can also emit SQL statements to synchronize child elements.

**Save is not upsert.** If an entity is identified as existing, Spring Data JDBC does not fall back to insert if the row is missing. If upsert is needed, explicitly design the statement/constraints and database semantics.

## 5. JPA: managed entities undergo dirty checking

JPA defines an entity lifecycle with main states:

```text
NEW
  |
  | EntityManager.persist(...)
  v
MANAGED
  |
  | detach / clear / close
  v
DETACHED
  |
  | EntityManager.merge(...)
  v
MANAGED COPY
  |
  | remove(...)
  v
REMOVED
```

A managed entity is bound to a persistence context. Within a persistence context, the JPA provider manages the entity's identity and state. When properties are modified, dirty checking enables the provider to detect changes and synchronize them to the database on flush.

### 5.1. JPA entity example

```java
package com.example.jpa;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class JpaAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String owner;

    @Column(nullable = false)
    private BigDecimal balance;

    protected JpaAccount() {
    }

    public JpaAccount(String owner, BigDecimal balance) {
        this.owner = owner;
        this.balance = balance;
    }

    public void rename(String newOwner) {
        this.owner = newOwner;
    }

    public Long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}
```

### 5.2. Modifying a managed entity without calling save

```java
@Service
public class JpaAccountService {

    private final EntityManager entityManager;

    public JpaAccountService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void rename(Long id, String newOwner) {
        JpaAccount account =
                entityManager.find(JpaAccount.class, id);

        if (account == null) {
            throw new IllegalArgumentException("Account not found");
        }

        account.rename(newOwner);

        // account is MANAGED.
        // JPA dirty checking will detect that owner changed.
        // No need to call merge(account) or repository.save(account).
    }
}
```

When the transaction flushes/commits, the provider detects that `owner` changed and synchronizes it to the database. Illustrative SQL:

```sql
UPDATE accounts
SET owner = ?
WHERE id = ?;
```

Some providers or configurations may generate different update SQL, such as updating multiple columns or adding a version condition in `WHERE`. Exact SQL depends on mapping and provider strategy.

### 5.3. Flush is not the same as commit

Dirty checking does not mean SQL always runs immediately on the Java line where a field is mutated. The provider normally synchronizes changes when:

- The transaction commits and the persistence context flushes.
- The application explicitly calls `EntityManager.flush()`.
- The provider needs to flush before executing a query per flush mode rules.

`flush` sends changes to the database within the active transaction. **Commit** ends the transaction and makes changes durable according to database transaction semantics. If the transaction rolls back, already-flushed SQL statements can still be rolled back.

## 6. JPA merge: copies state, does not "re-attach" the old object

When an entity leaves the persistence context, it becomes detached. Modifications on a detached object are not tracked by dirty checking.

```java
JpaAccount detached = ...; // Entity was loaded in a previous transaction
detached.rename("Lan Nguyen");

// Changes on detached are not automatically written.
```

To merge detached state into the current persistence context, call `merge`:

```java
@Transactional
public void updateDetached(JpaAccount detached) {
    JpaAccount managed = entityManager.merge(detached);

    // Continue working with managed.
    managed.rename("Lan Nguyen");
}
```

`EntityManager.merge(detached)`:

1. Finds or creates a matching managed instance in the persistence context.
2. Copies state from the passed-in object to the managed instance per JPA rules and cascade mappings.
3. Returns that managed instance.
4. Does not turn the original detached object itself into a managed instance.

After merge, dirty checking applies to the managed instance. When SQL executes still follows flush/transaction rules.

### You must use the object returned from merge

Do not write:

```java
entityManager.merge(detached);
detached.rename("New name"); // detached is still not a managed instance
```

Instead:

```java
JpaAccount managed = entityManager.merge(detached);
managed.rename("New name");
```

If you keep modifying the old detached object after merge, those changes are not automatically tracked.

### Does merge always issue SELECT then UPDATE?

Do not attach a fixed SQL sequence to `merge`. The provider must merge state into a managed entity; it may need to load current state or reuse data already in the persistence context. Exact SQL depends on the provider, ID strategy, cache, entity state, and mappings. For an existing entity, merge normally results in synchronizing the final state with an update at flush time, but the count of `SELECT`/`UPDATE` statements is not a fixed JPA contract.

## 7. Does Spring Data JPA save perform persist or merge?

This is a frequent source of confusion because both Spring Data JDBC and Spring Data JPA define a method named `save`.

In Spring Data JPA, the standard repository implementation checks the entity's new state:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
} else {
    return entityManager.merge(entity);
}
```

The snippet above illustrates the core logic of `SimpleJpaRepository.save`; it is not code an application writes manually. The strategy for determining newness can use version, ID, or `Persistable.isNew()`.

Consequently:

- Calling `jpaRepository.save(newEntity)` can lead to `persist`.
- Calling `jpaRepository.save(existingOrDetachedEntity)` normally leads to `merge`.
- Calling `jpaRepository.save(managedEntity)` may also pass through the merge branch if the entity is no longer identified as new; merging an already managed entity returns the corresponding managed instance. Calling `save` in that case is usually redundant.

If you are using Spring Data JDBC, there is no `EntityManager.merge` branch underneath. `CrudRepository.save` performs persistence under the JDBC model.

## 8. Comparing a single use case across both technologies

Suppose we need to rename the owner of account ID 10.

### Spring Data JDBC

```java
@Transactional
public void rename(Long id, String newName) {
    Account current = jdbcAccounts.findById(id).orElseThrow();
    Account changed = current.rename(newName);
    jdbcAccounts.save(changed);
}
```

Flow:

```text
findById
  -> SELECT and create object
rename
  -> create new object
save
  -> explicit UPDATE
commit
```

### JPA with a managed entity

```java
@Transactional
public void rename(Long id, String newName) {
    JpaAccount account = entityManager.find(JpaAccount.class, id);
    account.rename(newName);
    // Do not call save/merge.
}
```

Flow:

```text
find
  -> SELECT and place entity into persistence context
rename
  -> modify managed entity
flush
  -> dirty checking detects changes and issues UPDATE
commit
```

### JPA with a detached object

```java
@Transactional
public void rename(JpaAccount detached, String newName) {
    JpaAccount managed = entityManager.merge(detached);
    managed.rename(newName);
}
```

Flow:

```text
detached entity
  -> merge
  -> copy state into managed instance
rename managed
  -> dirty checking
flush
  -> SQL if needed
commit
```

All three flows can produce similar final SQL, yet **their object state management mechanisms are completely different**.

## 9. Risks when using merge with detached objects

Merge is often convenient when receiving a detached entity from another layer, but it is error-prone if the object only contains partial data.

Suppose the database currently holds:

```text
id       = 10
owner    = "Lan"
balance  = 500000
currency = "VND"
```

The client sends a detached object with only:

```text
id       = 10
owner    = "Lan Nguyen"
balance  = null
currency = null
```

If that object is merged as though it held the full entity state, the null values can be copied into the managed instance. On flush, the application risks overwriting existing data or hitting constraint errors if columns are non-nullable.

Therefore:

- Do not arbitrarily use JPA entities as request DTOs.
- Do not merge a "partial update" object without clearly defining the semantics of omitted/null fields.
- For PATCH, use a command/DTO explicitly representing which fields are requested to change, load the managed entity, and invoke appropriate domain behavior.
- Check merge cascades on associations; avoid merging an entity graph's state unintentionally.
- After merge, continue operating only on the returned instance.

Safer update example by loading a managed entity:

```java
@Transactional
public void changeOwner(Long id, String newOwner) {
    JpaAccount account = entityManager.find(JpaAccount.class, id);
    if (account == null) {
        throw new IllegalArgumentException("Account not found");
    }

    account.rename(newOwner);
    // balance and other fields are preserved.
}
```

In Spring Data JDBC, the analogous pattern is loading the aggregate, applying changes via domain behavior, and calling `save`. Using DTOs containing only updatable fields prevents services from accidentally overwriting unrelated properties.

## 10. Aggregates and collections: an important difference in Spring Data JDBC

Spring Data JDBC centers on the aggregate root. When saving an existing root, the framework synchronizes child entities belonging to the aggregate. For child collections, the typical mechanism can delete current child rows and re-insert elements based on the new collection state.

Example:

```text
PurchaseOrder #42
  lines:
    BOOK-01 x 2
    PEN-02  x 5
```

If you only change the quantity of one line and call `repository.save(order)`, persistence on the child table may involve deleting and re-inserting owned lines. That is Spring Data JDBC's aggregate persistence strategy, not Hibernate-style per-element dirty checking.

In JPA, if `PurchaseOrder` and its `OrderLine` instances are managed, modifying a property on a managed child can be detected by dirty checking without calling merge on the whole aggregate. However, the outcome depends on the owning side, cascades, orphan removal, fetching, and mappings.

Do not conclude that JPA always updates only one row or that JDBC is always slower. Inspect actual SQL and measure on real data. The essential difference is the state management model:

- JDBC: aggregates are written explicitly via repositories.
- JPA: managed entities are tracked inside a persistence context.

If a child element needs frequent modification and has an independent identity and lifecycle, that is a sign to re-evaluate the aggregate boundary rather than trying to force a large collection.

## 11. Transactions do not mean dirty checking

Both Spring Data JDBC and JPA can use Spring's `@Transactional`, but transactions and dirty checking are two separate concepts.

| Component | Responsibility |
| --- | --- |
| Transaction | Defines commit/rollback scope and atomicity of database operations. |
| JPA persistence context | Manages managed entities and identity within a scope. |
| Dirty checking | Detects changes on managed entities to generate write statements on flush. |
| JDBC repository save | Instructs Spring Data JDBC to execute persistence operations for an aggregate. |

A Spring Data JDBC method annotated with `@Transactional` that never calls `save` still will not write in-memory object changes automatically. Conversely, in JPA, a managed entity can be persisted even if the method never calls repository `save`.

### Where do transactions belong?

For a use case involving multiple operations:

```java
@Transactional
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    Account from = accounts.findById(fromId).orElseThrow();
    Account to = accounts.findById(toId).orElseThrow();

    // Validate business rules, update both aggregates.
    Account updatedFrom = from.debit(amount);
    Account updatedTo = to.credit(amount);

    accounts.save(updatedFrom);
    accounts.save(updatedTo);
}
```

In Spring Data JDBC, both `save` calls run inside the use case's transaction. If one fails and the exception triggers transaction rollback per configuration, both database changes are rolled back.

In JPA, if both entities are loaded and managed, modifying both can be persisted by dirty checking on flush/commit. Calling merge on each managed entity is unnecessary.

Do not confuse "not calling save" in JPA with "not needing a transaction." Dirty checking and flushing still occur within an appropriate persistence context and transaction.

## 12. Optimistic locking is not dirty checking

`@Version` can be used in both Spring Data JDBC and JPA to detect concurrent updates, but it does not replace the write mechanism:

- Dirty checking answers: which properties of a managed entity changed?
- Optimistic locking answers: is the entity still at the version read by this transaction?
- Save/merge answers: which state should be synchronized via the persistence API?

Example versioned SQL update:

```sql
UPDATE accounts
SET owner = ?, version = 4
WHERE id = ? AND version = 3;
```

If another transaction already incremented version to 4, the statement requiring version 3 updates zero rows. The framework can throw an optimistic locking failure. Exact SQL and version increment rules depend on the module/provider.

Do not treat `@Version` as a reason to skip `save` in Spring Data JDBC. It adds concurrency control to write operations; it does not automatically track object mutations.

## 13. Decision table: which API should you call?

| Scenario | Spring Data JDBC | JPA |
| --- | --- | --- |
| Create a new aggregate | `repository.save(newAggregate)` | `persist(newEntity)` or `jpaRepository.save(newEntity)` if detected as new |
| Read then modify aggregate | Load, invoke behavior, call `repository.save(changed)` | Load managed entity, modify it; dirty checking writes on flush |
| Modify detached object | Reload, apply command, then save; no JPA merge | `merge(detached)`, continue with returned object; or load managed and apply changes |
| Modify newly created in-memory object | Must call save to write | `persist` to make managed; then dirty checking |
| Need SQL written immediately in transaction | Call repository save / corresponding SQL | Call flush when truly needed; commit will flush per rules |
| Only `@Transactional` and modifying fields | Does not auto-write without a save operation | If entity is managed, dirty checking may write |
| Has child collection in aggregate | Save root to synchronize aggregate; weigh child rewrite cost | Track managed associations, cascade/orphan removal per mapping |

## 14. Common misconceptions

### Misconception 1: "Spring Data JDBC's save calls merge"

Incorrect. JDBC's `save` is a Spring Data JDBC repository API. It does not call `EntityManager.merge` and does not need a JPA persistence context.

### Misconception 2: "With @Transactional, objects are saved automatically"

Incorrect for Spring Data JDBC. A transaction merely wraps database operations; it does not track object fields. You must call `save` or a write statement.

### Misconception 3: "Merge turns the passed-in object into a managed instance"

Incorrect. `merge` copies state into a managed instance and returns that instance. The passed-in object remains detached.

### Misconception 4: "JPA requires calling save after modifying an entity"

Unnecessary if the entity remains managed in the persistence context. Dirty checking synchronizes changes on flush. Calling save/merge again is usually redundant in that case.

### Misconception 5: "Merge always emits one immediate UPDATE"

Incorrect. Merge is an operation to consolidate state into the persistence context; SQL may be deferred until flush. The provider may need a query to load current state, and exact SQL depends on many factors.

### Misconception 6: "save is automatically an upsert"

Incorrect. Save chooses insert/update based on entity state; it is not implicitly a database upsert statement. A missing row on the update branch does not automatically become an insert.

### Misconception 7: "Both JDBC and JPA only write modified fields"

You cannot conclude this. JPA dirty checking identifies changes on managed entities, though actual update SQL depends on provider/configuration. Spring Data JDBC saves aggregates according to its persistence strategy, including synchronizing child collections. Observe actual SQL and understand your mappings.

## 15. Notes when migrating from Spring Data JPA to Spring Data JDBC

During migration, look for code like:

```java
Account account = repository.findById(id).orElseThrow();
account.setOwner(newOwner);
// No repository.save(account)
```

In JPA, this can be valid if the entity is managed inside a transaction. In Spring Data JDBC, this code is insufficient to instruct the database to persist the change.

Review the following:

1. **Managed entity assumptions:** everywhere relying on dirty checking must be converted to explicit `save` operations or explicit update SQL.
2. **Merge assumptions:** places using `merge` with detached objects should be converted to loading the aggregate and applying an appropriate command/business behavior.
3. **Cascade/fetch assumptions:** JPA's `CascadeType.MERGE`, lazy loading, and persistence context do not translate verbatim to Spring Data JDBC.
4. **Collection updates:** evaluate the cost of re-synchronizing child entities on aggregate save.
5. **Entity identity:** do not assume reading the same ID twice returns the exact same Java object instance like JPA's identity map.
6. **Transaction boundaries:** maintain proper business boundaries and ensure related `save` calls participate in the same transaction.
7. **Optimistic locking:** design versioning and conflict handling explicitly rather than confusing them with dirty checking.

A safe migration path is to rewrite each use case in the flow: load aggregate → invoke behavior → save aggregate, then verify SQL and database results.

## 16. Hands-on exercises

**Exercise 1 — Omitting save in Spring Data JDBC.** Load an `Account` record, create a new record with a different owner, and do not call `save`. Read it back in another transaction and confirm the data did not change. Then add `save` and compare.

**Exercise 2 — JPA dirty checking.** Use `EntityManager` to find a `JpaAccount` inside a transaction, change its owner, and do not call save/merge. After commit, read it back to observe that the change was persisted.

**Exercise 3 — JPA detached.** Load an entity in a first transaction, let it detach, modify a field, and finish. Verify the change has not been written. In a new transaction call `merge`, use the returned object, and inspect the database.

**Exercise 4 — Mixing up objects after merge.** Call `merge(detached)` but keep modifying the original `detached` object. Compare with modifying the returned `managed` object. Explain why the outcomes differ.

**Exercise 5 — Spring Data JPA save.** Use `JpaRepository.save` with a new entity and an existing entity. Enable SQL logging to observe the persist/merge branches; remember that actual SQL may be deferred until flush.

**Exercise 6 — Aggregate collections.** In Spring Data JDBC, create an order with multiple lines, edit one line, and save the root. Observe SQL on the child table. Compare with JPA when child entities are managed.

**Exercise 7 — Transactions and flush.** In JPA, call `flush` before commit and then intentionally roll back. Observe that SQL was sent yet changes were not committed. Explain why flush is not commit.

## 17. Key takeaways

Spring Data JDBC and JPA manage entity state differently. With Spring Data JDBC, `save` is an explicit write operation on an aggregate; in-memory object changes are not automatically detected just because the object was loaded inside `@Transactional`. With JPA, managed entities reside in a persistence context and dirty checking can write changes on flush without calling save.

`merge` is a JPA API for copying the state of a detached object into a managed instance; always use the returned object. Spring Data JPA's `save` can invoke `persist` or `merge` depending on the entity's new state, but that does not mean Spring Data JDBC's `save` uses merge either.

When reading or migrating code, ask three things: what state is the object in, what mechanism detects changes, and what operation actually requests writing to the database. Answering these three questions correctly prevents common bugs such as modifying objects without saving, merging partial entities by mistake, or calling save unnecessarily.

### References

- [Spring Data Relational – Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data JPA – Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Jakarta Persistence – EntityManager API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Hibernate ORM – Persistence Context and Dirty Checking](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
