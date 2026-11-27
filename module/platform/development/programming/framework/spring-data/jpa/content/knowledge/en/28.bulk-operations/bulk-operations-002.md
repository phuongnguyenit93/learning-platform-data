# JPQL UPDATE, DELETE, and @Modifying in Spring Data JPA

## 1. What is bulk DML?

In JPA, updating or deleting data is typically performed through entities managed by the persistence context. The application loads an entity, modifies its properties or calls the remove method, and JPA synchronizes the changes to the database on flush or transaction commit.

With large numbers of records, that approach can consume significant memory and time because many entities must be loaded, each object's state tracked, and corresponding lifecycle steps executed.

**Bulk DML** (bulk data manipulation) allows sending a single UPDATE or DELETE statement that affects a set of entities directly in the database. JPQL supports these two statement forms. Spring Data JPA allows declaring them in a repository using **@Query** combined with **@Modifying**.

For example, instead of loading thousands of accounts and setting **active = false** on each object, the application can send one update statement for all accounts matching the condition.

Bulk DML is suitable when:

- Updating a property with the same rule across many records.
- Deleting expired data by condition.
- Transitioning statuses in bulk.
- Cleaning up old data on a schedule.
- Performing operations without needing to invoke per-entity domain logic.

In return, bulk DML bypasses many entity lifecycle mechanisms. Therefore, you must understand its effects on the persistence context, callbacks, cascades, and optimistic locking before using it.

## 2. JPQL UPDATE and DELETE syntax

JPQL uses entity names and mapped Java properties rather than SQL table and column names directly.

Update syntax:

~~~sql
UPDATE EntityName alias
SET alias.property = :value
WHERE condition
~~~

Delete syntax:

~~~sql
DELETE FROM EntityName alias
WHERE condition
~~~

Example with the **User** entity:

~~~java
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;
    private boolean active;
    private Instant lastLoginAt;
    private Instant createdAt;

    @Enumerated(EnumType.STRING)
    private UserStatus status;

    protected User() {
    }

    // Constructors, getters and domain methods omitted.
}
~~~

JPQL to update all active accounts that last logged in before a cutoff timestamp:

~~~sql
UPDATE User u
SET u.active = false
WHERE u.active = true
  AND u.lastLoginAt < :cutoff
~~~

JPQL to delete accounts in a locked status created before a cutoff timestamp:

~~~sql
DELETE FROM User u
WHERE u.status = :status
  AND u.createdAt < :cutoff
~~~

Important rules:

- **User** is the entity name, usually the entity class name or the value declared in **@Entity(name = "...")**.
- **active**, **lastLoginAt**, and **status** are entity properties, not database column names.
- **WHERE** restricts the set of affected entities. If **WHERE** is omitted, the statement can update or delete all entities of the specified type.
- The type of the value in **SET** must be compatible with the property type.
- A bulk update/delete statement specifies only one entity type in the UPDATE or FROM clause; the scope also includes subclasses according to JPA inheritance rules.
- DELETE does not automatically cascade to related entities.

JPQL bulk DML is not a SELECT statement. It is executed using **executeUpdate()** of the JPA Query API.

## 3. Why is @Modifying needed?

Spring Data JPA normally treats a method with **@Query** as a read query. When a method contains JPQL UPDATE or DELETE, it must be annotated with **@Modifying** so Spring Data executes it as a modifying query.

Example:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        update User u
        set u.active = false
        where u.active = true
          and u.lastLoginAt < :cutoff
    """)
    int deactivateInactiveUsers(
        @Param("cutoff") Instant cutoff
    );
}
~~~

When the method is called, Spring Data executes the update statement instead of attempting to read results like a select query.

**@Modifying** is meaningful when combined with query methods declared using **@Query**. It is not needed for:

- Derived delete queries such as **deleteByStatus(...)**, because Spring Data knows the method is a delete operation from the method name.
- Custom repository implementations, where the code controls **EntityManager** or the data access API directly.
- Inherited repository CRUD methods.

According to the Spring Data JPA API, query types requiring **@Modifying** include INSERT, UPDATE, DELETE, and certain DDL statements. This article focuses on JPQL UPDATE and DELETE.

## 4. Declaring JPQL UPDATE in a repository

Example updating a user's status by ID:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        update User u
        set u.status = :newStatus
        where u.id = :id
    """)
    int updateStatus(
        @Param("id") Long id,
        @Param("newStatus") UserStatus newStatus
    );
}
~~~

Calling from a service:

~~~java
@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int changeStatus(Long id, UserStatus status) {
        return userRepository.updateStatus(id, status);
    }
}
~~~

The method returns **int**, which is the number of entities updated according to the bulk operation result. If the ID does not exist, the count is usually **0**. If one record is updated, the count is **1**.

The int return value can be used to:

- Check whether any records matched the condition.
- Detect missing IDs or unmatched conditions.
- Record the number of records processed in a background task.

Do not return an entity from a bulk update method. The statement does not load and resynchronize entity objects like a read query.

## 5. Declaring JPQL DELETE in a repository

Example deleting expired accounts:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        delete from User u
        where u.status = :status
          and u.createdAt < :cutoff
    """)
    int deleteExpiredUsers(
        @Param("status") UserStatus status,
        @Param("cutoff") Instant cutoff
    );
}
~~~

Executing service:

~~~java
@Service
public class UserCleanupService {

    private final UserRepository userRepository;

    public UserCleanupService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int removeExpiredUsers(
            UserStatus status,
            Instant cutoff) {

        return userRepository.deleteExpiredUsers(status, cutoff);
    }
}
~~~

This statement sends a bulk delete to the database. It does not load each User beforehand and call **EntityManager.remove()** on each object.

Verify delete conditions very carefully. Before running a critical data deletion task, confirm the expected number of records with a corresponding read query or an application dry-run step. A DELETE statement without a condition can affect the entire set of entities.

## 6. Transactions are mandatory

Bulk update/delete requires a transaction. JPA requires modifying queries to execute within a transaction; without an active transaction, the provider may throw **TransactionRequiredException**.

A common misconception is that query methods declared directly in a repository automatically inherit default transaction configuration just because the repository extends JpaRepository. Inherited CRUD methods have their own transaction configuration, whereas declared query methods must be placed inside an explicit transaction.

The common practice is to declare the transaction boundary at the service layer:

~~~java
@Service
public class UserMaintenanceService {

    private final UserRepository repository;

    public UserMaintenanceService(UserRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return repository.deactivateInactiveUsers(cutoff);
    }
}
~~~

Default **@Transactional** uses a standard write transaction, suitable for bulk update/delete.

If the service class has class-level **@Transactional(readOnly = true)**, override it for write methods:

~~~java
@Service
@Transactional(readOnly = true)
public class UserMaintenanceService {

    private final UserRepository repository;

    public UserMaintenanceService(UserRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return repository.deactivateInactiveUsers(cutoff);
    }
}
~~~

**readOnly = true** is a transaction hint to the provider/driver and may enable optimizations. It is not an absolute enforcement check that blocks every write statement. Therefore, methods performing bulk DML should run within an appropriate write transaction.

You can place **@Transactional** directly on the repository method, but declaring transactions in the service usually helps manage a use case spanning multiple repository operations under one consistent boundary.

## 7. Persistence context does not auto-sync after bulk DML

This is the most important point when using JPQL UPDATE/DELETE.

The persistence context stores managed entities inside **EntityManager**. When bulk DML executes, the database changes directly, but JPA does not automatically update objects already in the persistence context.

Example:

~~~java
User user = entityManager.find(User.class, 10L);

repository.updateStatus(10L, UserStatus.BLOCKED);

// The managed user object may still hold the old status.
System.out.println(user.getStatus());
~~~

The bulk update statement changed the data in the database, yet the previously loaded **user** object may still hold the old status in memory.

The same happens with DELETE: a loaded entity may still exist in the persistence context even though the corresponding row has been deleted directly in the database.

Possible consequences include:

- The service reads stale values from the managed entity.
- Business logic continues using an outdated state.
- A subsequent flush could write pending changes from the managed entity.
- An entity already deleted in the database is still referenced in memory.

Jakarta Persistence specifies that the persistence context is not automatically synchronized with the results of bulk update/delete operations. Therefore, execute bulk DML within a transaction and manage affected entities carefully.

## 8. clearAutomatically and flushAutomatically

Spring Data JPA provides two attributes on **@Modifying** to control the persistence context:

| Attribute | Effect | Default |
|---|---|---|
| **flushAutomatically** | Flushes the persistence context before running the modifying query | **false** |
| **clearAutomatically** | Clears the persistence context after running the modifying query | **false** |

Example:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update User u
    set u.active = false
    where u.lastLoginAt < :cutoff
""")
int deactivateBefore(@Param("cutoff") Instant cutoff);
~~~

### flushAutomatically = true

**flushAutomatically** instructs Spring Data to call **EntityManager.flush()** before executing the modifying query.

Flushing synchronizes pending changes in the persistence context to the database. This is useful when the bulk query needs to see earlier changes or when the persistence context is about to be cleared.

Flushing is not committing. The transaction can still roll back afterward.

### clearAutomatically = true

**clearAutomatically** instructs Spring Data to call **EntityManager.clear()** after executing the modifying query.

Clearing causes all managed entities in the persistence context to become detached. Subsequent queries will have to load state from the database instead of returning stale managed objects.

Note: clear() affects the entire persistence context, not only the entities modified by the bulk DML. Other entities currently used by the service also become detached.

### Why is enabling both sometimes necessary?

If you clear the persistence context while unflushed changes still exist, those changes may be discarded from the persistence context. Therefore, when a use case needs to preserve pending changes before a bulk query, you can enable both **flushAutomatically = true** and **clearAutomatically = true**.

However, flushing the entire persistence context can write many unrelated changes and trigger constraint or validation errors before the bulk statement. Only enable these attributes when you understand the persistence context state for the use case.

Another option is to call **EntityManager.flush()** manually before bulk DML and **EntityManager.clear()** afterward in the service, if explicit ordering control is needed.

## 9. Example of managing persistence context state

Repository:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update User u
        set u.status = :status
        where u.id = :id
    """)
    int updateStatusAndClear(
        @Param("id") Long id,
        @Param("status") UserStatus status
    );
}
~~~

Service:

~~~java
@Service
public class UserService {

    private final UserRepository repository;
    private final EntityManager entityManager;

    public UserService(
            UserRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public UserStatus changeStatus(Long id, UserStatus status) {
        int updated = repository.updateStatusAndClear(id, status);

        if (updated == 0) {
            throw new EntityNotFoundException("User not found");
        }

        User reloaded = entityManager.find(User.class, id);
        return reloaded.getStatus();
    }
}
~~~

After the repository method runs, the persistence context is cleared. The subsequent find() call loads the fresh entity from the database within the same transaction.

If not using **clearAutomatically**, you can call **entityManager.clear()** after the bulk query or **entityManager.refresh(user)** for a specific managed entity. Choose the approach matching the number of entities and the objects the service still needs to use.

Do not call clear() mechanically if the service still needs managed entities or has unflushed changes.

## 10. How does bulk DELETE differ from derived delete?

Spring Data JPA supports both derived delete queries and bulk deletes with **@Modifying**.

Derived delete example:

~~~java
void deleteByRoleId(Long roleId);
~~~

Bulk JPQL delete example:

~~~java
@Modifying
@Query("delete from User u where u.role.id = :roleId")
int deleteInBulkByRoleId(@Param("roleId") Long roleId);
~~~

Both methods can delete the same dataset, but their execution differs:

| Criterion | Derived delete | Bulk JPQL DELETE |
|---|---|---|
| Execution method | Queries matching entities then deletes each entity | A single DELETE statement acting directly on the database |
| Loads entities into memory | Yes | No need to load individual entities |
| Entity lifecycle callbacks | Invoked via the per-entity remove pipeline | Not invoked per entity |
| JPA cascade remove | Applied per remove mapping | Does not automatically cascade to related entities |
| Memory with large volumes | Can be high because entities are loaded and held in session | Typically lower |
| Record count | Can be returned based on method signature | Can receive affected entity count via int |

Derived delete can invoke **@PreRemove** and related lifecycle callbacks because Spring Data loads the entities and deletes each object. It fits when entity-level deletion logic, callbacks, or cascades are required.

Bulk delete fits when performance is needed and per-entity processing is unnecessary. When deleting large volumes, derived delete can consume considerable memory because entities are loaded into the persistence context before deletion.

Do not choose bulk delete if the business logic depends on **@PreRemove**, entity listeners, cascade remove, or per-object domain logic.

## 11. Bulk DML bypasses lifecycle callbacks and cascades

Bulk update/delete operates directly on the database and does not execute each entity's lifecycle pipeline.

For example, the following callbacks are not invoked for each entity affected by bulk DML:

- **@PreUpdate**
- **@PostUpdate**
- **@PreRemove**
- **@PostRemove**

Entity listeners and Spring Data auditing relying on lifecycle callbacks also do not run automatically for each record updated or deleted by bulk DML. Automatic Bean Validation tied to lifecycle events is likewise not executed as in normal entity updates.

If audit fields such as **updatedAt** or **updatedBy** need updating, include those values directly in the JPQL statement or handle them separately according to business rules.

Example:

~~~java
@Modifying
@Query("""
    update User u
    set u.status = :status,
        u.updatedAt = :updatedAt
    where u.status = :oldStatus
""")
int changeStatusAndAudit(
    @Param("oldStatus") UserStatus oldStatus,
    @Param("status") UserStatus status,
    @Param("updatedAt") Instant updatedAt
);
~~~

Bulk DELETE also does not automatically apply **CascadeType.REMOVE** or **orphanRemoval** as when deleting a managed entity. If child tables still reference parent records, foreign keys may cause DELETE to fail.

Relationships can be handled by:

1. Deleting child records first with an appropriate bulk statement.
2. Deleting parent records after constraints are satisfied.
3. Using database-level cascade mechanisms if architecture and data policies allow.
4. Using normal entity removal when JPA cascades and lifecycle callbacks are required.

Database triggers still execute according to the database engine's rules, even though JPA entity callbacks do not run.

## 12. Bulk UPDATE and optimistic locking with @Version

Normal optimistic locking uses a **@Version** property. When updating a managed entity, JPA checks the version to detect concurrent changes.

Bulk updates bypass automatic optimistic locking. If the statement does not check the version, it can overwrite changes from another transaction without detecting conflicts in the usual way.

Example entity:

~~~java
@Entity
public class Inventory {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;

    protected Inventory() {
    }
}
~~~

If version checking is needed in a bulk update, add the version condition and explicitly increment the version:

~~~java
@Modifying
@Query("""
    update Inventory i
    set i.quantity = :quantity,
        i.version = i.version + 1
    where i.id = :id
      and i.version = :expectedVersion
""")
int updateQuantity(
    @Param("id") Long id,
    @Param("quantity") int quantity,
    @Param("expectedVersion") long expectedVersion
);
~~~

The service checks the number of updated records:

~~~java
@Transactional
public void changeQuantity(
        Long id,
        int quantity,
        long expectedVersion) {

    int updated = repository.updateQuantity(
        id,
        quantity,
        expectedVersion
    );

    if (updated == 0) {
        throw new OptimisticLockingFailureException(
            "Inventory does not exist or its version has changed"
        );
    }
}
~~~

When **updated == 0**, the ID may not exist or the version may no longer match. If you need to distinguish those two cases, perform an additional query according to business policy.

Manual version incrementing must be tested against the actual provider and database. If optimistic concurrency is not needed for the bulk operation, document the overwrite-acceptance policy and limit the scope of impact.

## 13. Combining multiple conditions in UPDATE

JPQL allows updating multiple properties in the same statement, provided the values are type-compatible:

~~~java
@Modifying
@Query("""
    update Product p
    set p.price = :price,
        p.active = :active,
        p.updatedAt = :updatedAt
    where p.category.id = :categoryId
""")
int updateProductsInCategory(
    @Param("categoryId") Long categoryId,
    @Param("price") BigDecimal price,
    @Param("active") boolean active,
    @Param("updatedAt") Instant updatedAt
);
~~~

This statement updates the properties of all Products with the matching category ID.

Arithmetic expressions can be used:

~~~sql
UPDATE Product p
SET p.stock = p.stock - :amount
WHERE p.id = :id
  AND p.stock >= :amount
~~~

The condition **p.stock >= :amount** prevents reducing stock below 0 in this update statement. However, if multiple concurrent transactions operate on the same record, evaluate transaction isolation, locking, and an appropriate retry policy.

Do not pass JPQL strings concatenated from user input into **@Query**. Use named parameters to bind values. Entity names, properties, and statement structure should be fixed in source code.

## 14. Bulk DML with native SQL

**@Modifying** can also be used with **@Query(nativeQuery = true)** when database-specific SQL is required:

~~~java
@Modifying
@Query(
    value = """
        update users
        set active = false
        where last_login_at < :cutoff
    """,
    nativeQuery = true
)
int deactivateWithNativeSql(
    @Param("cutoff") Instant cutoff
);
~~~

Native SQL uses the database engine's table names, column names, and syntax. It can leverage vendor-specific features, though it reduces repository portability.

With native queries, verify:

- Parameter types and JDBC driver binding behavior.
- Actual table/column names and schema.
- Database-specific syntax.
- Return type and record count.
- Impact of the statement on the persistence context and caches.

Native DML also does not synchronize managed entities in the persistence context. Handle flush/clear or refresh similarly to bulk JPQL when managed entities may be affected.

## 15. When should CriteriaUpdate and CriteriaDelete be used?

If update/delete conditions are built dynamically with the Criteria API, JPA provides **CriteriaUpdate** and **CriteriaDelete**.

CriteriaUpdate example:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<User> update =
    cb.createCriteriaUpdate(User.class);

Root<User> user = update.from(User.class);

update.set(user.get("active"), false);
update.where(
    cb.lessThan(user.get("lastLoginAt"), cutoff)
);

int affected = entityManager
    .createQuery(update)
    .executeUpdate();
~~~

CriteriaDelete example:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaDelete<User> delete =
    cb.createCriteriaDelete(User.class);

Root<User> user = delete.from(User.class);

delete.where(
    cb.equal(user.get("status"), UserStatus.EXPIRED)
);

int affected = entityManager
    .createQuery(delete)
    .executeUpdate();
~~~

Criteria bulk DML shares the same key characteristics as JPQL bulk DML: executes directly against the database, does not automatically sync the persistence context, and bypasses automatic optimistic locking.

Use **@Modifying** when the statement is static and easy to declare in a repository with **@Query**. Use CriteriaUpdate/CriteriaDelete when conditions must be constructed programmatically or when the Criteria API is required.

The Criteria examples above are snippets inside a service/repository with an EntityManager and an appropriate transaction; you need to import **jakarta.persistence.criteria.CriteriaBuilder**, **CriteriaUpdate**, **CriteriaDelete**, and related types.

## 16. Performance and limitations of bulk DML

Bulk DML is typically more efficient than loading thousands of entities and updating or deleting each object, because the database receives a single statement for the entire dataset.

Benefits:

- No need to materialize all entities into the persistence context.
- Fewer round-trips between the application and the database.
- No need to call save() on each entity after updating properties.
- Allows the database to optimize the statement using indexes and execution plans.

However, bulk DML is not automatically fast in every situation. Performance also depends on:

- Number of affected records.
- Indexes on columns in the WHERE clause.
- Transaction log write and index update costs.
- Database foreign keys, triggers, and constraints.
- Lock contention and transaction hold duration.
- Transaction size and rollback overhead.

A single statement updating millions of records can hold locks for a long time and generate huge transaction logs. For very large tasks, consider splitting into multiple batches by ID or timestamp, committing each batch, and tracking progress. Standard JPQL bulk DML does not provide direct LIMIT syntax for UPDATE/DELETE; batching strategies must be designed using appropriate conditions or ID-fetching queries.

Bulk DML also differs from JDBC batching. JDBC batching usually sends multiple individual update statements for entities; bulk DML sends one statement affecting a set of records matching a condition.

## 17. Common mistakes

### 17.1. Forgetting @Modifying

A method with **@Query** containing UPDATE/DELETE without **@Modifying** may be treated by Spring Data as a read query and fail at execution. Add **@Modifying** to modifying query methods.

### 17.2. Missing transaction

JPA requires a transaction for bulk DML. Place **@Transactional** at an appropriate service or repository boundary. Do not rely on **@Modifying** to open a transaction on its own.

### 17.3. Using table names instead of entity names

JPQL uses entity names and Java properties. For example, **update User u set u.active = false**, not table name **users** or column **is_active**. Table/column names are only used in native SQL.

### 17.4. Managed entities still hold stale data

Bulk DML does not sync the persistence context. Clear the persistence context, refresh specific entities, or use a fresh persistence context before reading data again.

### 17.5. clearAutomatically discards unflushed changes

**clearAutomatically = true** detaches all entities. If pending changes exist and need to be saved, consider **flushAutomatically = true** or an explicit flush before clearing.

### 17.6. Expecting callbacks and cascades to run

Bulk DML bypasses per-entity lifecycle callbacks and JPA cascades. If **@PreRemove**, auditing listeners, or cascade remove are needed, use derived delete or normal entity deletion.

### 17.7. Not checking version

Bulk updates bypass automatic optimistic locking. If conflict detection is needed, include the version in the WHERE clause, manually increment the version when appropriate, and check the updated row count.

### 17.8. Deleting parent entities while child entities still exist

Bulk DELETE does not cascade. Foreign keys may reject the statement. Handle child data first or choose an entity deletion flow with appropriate cascades.

### 17.9. Using a read-only transaction for write statements

Do not run bulk DML inside a transaction designed as read-only. Use a write transaction for service methods performing updates/deletes.

### 17.10. Deleting or updating too many records in one transaction

A single large transaction can hold locks for a long time and inflate logs. Batch when necessary, bound conditions, and monitor affected counts.

## 18. Testing bulk UPDATE and DELETE

Use integration tests with **@DataJpaTest** or a full test context to test actual queries against the target JPA provider and database.

Example testing an update and clearing the persistence context:

~~~java
@DataJpaTest
class UserBulkDmlRepositoryTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void bulkUpdateChangesDatabaseAndClearsManagedEntities() {
        User user = userRepository.saveAndFlush(
            new User("user@example.com", true)
        );

        Long id = user.getId();
        User managed = entityManager.find(User.class, id);

        int updated = userRepository.deactivateById(id);

        assertThat(updated).isEqualTo(1);
        assertThat(entityManager.contains(managed)).isFalse();

        User reloaded = entityManager.find(User.class, id);
        assertThat(reloaded.isActive()).isFalse();
    }
}
~~~

The example assumes the repository method **deactivateById** has **@Modifying(clearAutomatically = true)** and the entity has corresponding constructors/getters. **@DataJpaTest** usually runs in a test transaction and rolls back after the test.

Cases to test:

1. UPDATE affects the exact expected number of records.
2. DELETE only removes entities matching the condition.
3. Non-matching conditions return a count of **0**.
4. Omitting WHERE is used only when intending to affect the entire entity set.
5. The persistence context is cleared or refreshed properly.
6. Pending changes before the bulk query are flushed when configured.
7. Callbacks and cascades are not assumed to run in bulk DML.
8. Version checks detect version mismatch cases.
9. Foreign keys and database constraints behave as expected.
10. Queries run inside a write transaction.
11. Native queries, if any, run on the actual production database engine.
12. Large record counts do not cause locks or transaction durations exceeding operational limits.

For native queries or dialect-dependent behavior, test with Testcontainers or a production-equivalent database rather than relying solely on H2.

## 19. Decision process for choosing an update/delete approach

When multiple records need to be modified:

1. Determine whether the operation needs to run domain logic, lifecycle callbacks, cascades, or auditing for each entity.
2. If per-entity processing is needed, load the entities and use appropriate domain/remove methods or derived delete.
3. If the same change applies to a large set, consider JPQL bulk UPDATE/DELETE.
4. Declare the statement in **@Query** and add **@Modifying**.
5. Place a write transaction at the service boundary.
6. Determine whether the persistence context holds affected entities; choose appropriate flush, clear, or refresh behavior.
7. If **@Version** is present, decide how to check and increment the version manually.
8. Check relationships, foreign keys, callbacks, auditing, and caches.
9. Return and check the affected record count.
10. Test against the target database, including zero-match cases, large datasets, and transaction errors.

## 20. Key takeaways

- JPQL UPDATE/DELETE executes bulk DML directly on a set of entities.
- JPQL uses entity names and property names, not SQL table/column names.
- **@Modifying** is required for modifying queries declared with **@Query**; derived deletes and custom implementations do not need this annotation.
- Bulk DML requires a transaction; declaring a write transaction at the service boundary is the common approach.
- Methods can return **int** to receive the number of updated or deleted entities.
- **flushAutomatically** flushes the persistence context before the statement; **clearAutomatically** clears the persistence context after the statement. Both default to false.
- The persistence context does not auto-sync with bulk DML; already-managed entities may hold stale state.
- Bulk DELETE does not cascade to related entities and does not invoke per-entity lifecycle callbacks.
- Bulk UPDATE/DELETE bypasses automatic optimistic locking; manage versions explicitly if business logic requires it.
- Derived delete removes each entity individually and can trigger lifecycle callbacks; bulk delete sends one statement directly to the database.
- Bulk DML typically reduces entity loading overhead, but indexes, transaction logs, locks, and record counts must still be considered.
- Test persistence context, transactions, affected counts, and constraints against the target database.

JPQL bulk UPDATE, DELETE, and **@Modifying** are effective tools for bulk operations when the same rule applies to many records. Manage transactions explicitly, handle the persistence context after the statement, and only use bulk DML when per-entity lifecycle behavior is not required.

## References

- [Spring Data JPA — JPA Query Methods: Modifying Queries and Derived Deletes](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Transactionality and Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data JPA — @Modifying API](https://docs.spring.io/spring-data/jpa/reference/4.0/api/java/org/springframework/data/jpa/repository/Modifying.html)
- [Jakarta Persistence 3.2 — Section 4.11: Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
