# Flushing the ORM to Catch Errors Masked by the Persistence Context

In applications using JPA/Hibernate, calling `repository.save()` or modifying a managed entity does not necessarily send SQL to the database immediately. The ORM often keeps entities in the persistence context and defers writes until an appropriate moment, such as when the transaction commits or when synchronization is needed before a query.

This deferral mechanism lets the ORM batch changes, manage dirty checking, and optimize database operations. However, it also introduces a testing risk: a test may read back the expected values from the in-memory object and conclude data was saved successfully, while no SQL was ever executed. Errors such as unique constraint violations, foreign key violations, data type mismatches, invalid SQL statements, or mapping errors may only surface when the ORM actually sends commands to the database.

In Spring Framework Testing, particularly with `@DataJpaTest` and transactional tests, understanding **flush** is essential to force the persistence context to synchronize with the database at the point the test wants to verify. Combining `flush` with `clear` prevents the first-level cache from returning the exact same object sitting in memory.

## 1. The Persistence Context and Write-Behind Mechanism

JPA manages entities through a persistence context. Inside a persistence context, each entity has an identity corresponding to its type and primary key; once an entity is managed, the `EntityManager` tracks its state.

Common entity states:

- **New / transient**: a newly created object not yet managed by any persistence context.
- **Managed**: an entity currently tracked; changes to the object can be detected by the ORM.
- **Detached**: an entity that was previously managed but has left the persistence context.
- **Removed**: an entity marked for deletion that will be deleted when the persistence context synchronizes.

Example:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
}
~~~

When `setName()` is called, Hibernate usually does not run an UPDATE immediately at that statement. The entity remains managed, and Hibernate notes that the `name` attribute changed. During flush, dirty checking detects the difference and generates the corresponding SQL UPDATE.

This mechanism is commonly called **write-behind**: changes are held in the persistence context first and synchronized down to the database later.

High-level flow:

~~~text
entityManager.find(...)
        |
        v
Entity in managed state
        |
        v
Modify property on the object
        |
        v
Persistence context records new state
        |
        | SQL not necessarily executed yet
        v
flush()
        |
        v
Hibernate checks dirty state
        |
        v
Generates and sends INSERT / UPDATE / DELETE
        |
        v
Database executes SQL and checks constraints
~~~

Therefore, an assertion on a managed object only proves the in-memory object holds the expected value. It does not prove the database accepted that change.

## 2. What Is Flush?

In JPA, flush is the operation that synchronizes the state of the persistence context with the database. With Hibernate, this process typically includes:

- Detecting new entities requiring INSERT.
- Detecting modified managed entities requiring UPDATE.
- Detecting entities marked for removal requiring DELETE.
- Executing the necessary SQL statements in an order managed by the ORM.
- Letting the database enforce constraints checked at execution time.

Flush can be invoked via `EntityManager`:

~~~java
entityManager.flush();
~~~

Or via a Spring Data JPA repository if the repository extends `JpaRepository`:

~~~java
customerRepository.flush();
~~~

Both request that the persistence context synchronize pending changes. When calling `repository.flush()`, the operation does not apply only to the entity just saved through that repository; it can flush other pending changes in the same persistence context.

Example:

~~~java
@Test
void shouldFlushPendingCustomerChanges() {
    Customer customer = new Customer("Lan", "lan@example.test");

    customerRepository.save(customer);

    entityManager.flush();

    assertNotNull(customer.getId());
}
~~~

The test explicitly instructs the ORM to send SQL before assertions proceed. If the INSERT violates a constraint or the SQL is invalid, the error can appear immediately at flush rather than waiting until the end of the transaction.

Note: flush is not equivalent to commit. It sends the necessary statements within the current transaction; the transaction can still roll back afterward.

## 3. Distinguishing `save()`, `flush()`, and `commit()`

These three operations have distinct responsibilities:

| Operation | Responsibility | Ends the Transaction? |
|---|---|---|
| `repository.save(entity)` | Requests Spring Data JPA to persist or merge an entity | No |
| `entityManager.flush()` / `repository.flush()` | Synchronizes pending changes in the persistence context down to the database | No |
| transaction commit | Completes the transaction successfully and confirms changes per transaction semantics | Yes |

### 3.1. `save()` Does Not Guarantee SQL Has Run

Spring Data JPA's `save()` typically selects `EntityManager.persist()` for a new entity or `EntityManager.merge()` for an entity deemed existing according to repository rules.

Neither `persist()` nor `merge()` guarantees that all SQL has been sent by the time the method returns.

~~~java
Customer customer = new Customer("Lan", "lan@example.test");

Customer saved = customerRepository.save(customer);

// The entity may already be managed, yet the INSERT may still be pending.
~~~

For entities using sequences, Hibernate can fetch the primary key value early before the INSERT. Thus, a non-null ID does not prove the INSERT succeeded either.

With IDENTITY generation, the provider typically needs to INSERT earlier to obtain the database-generated primary key. Even so, do not rely on ID generation strategy differences to skip flushing when the goal is testing SQL and constraints.

### 3.2. `flush()` Does Not Commit

~~~java
entityManager.flush();

// SQL has been sent within the current transaction.
// The transaction can still roll back.
~~~

If a test uses `@Transactional` and rolls back by default, data may be INSERTed or UPDATEd at flush yet still rolled back when the test completes.

This is exactly what we want in many repository tests: catching SQL errors during the test without leaving data behind afterward.

### 3.3. Commit Can Catch Additional Errors

Flush usually surfaces errors that occur when the database executes SQL. However, some constraints or operations may be deferred by the database until commit, such as deferred constraints in certain DBMSs.

Consequently:

- Flush helps catch many persistence errors early.
- Flush does not guarantee conditions checked only at commit have been verified.
- If requirements demand testing real commit behavior, write a test with an appropriate transaction boundary instead of assuming flush equals commit.

## 4. Why Can the Persistence Context Mask Bugs?

A test may operate on the same managed object:

~~~java
@Test
void shouldUpdateCustomerName() {
    Customer customer = customerRepository.findById(1L).orElseThrow();

    customer.setName("Lan Nguyen");

    Customer loadedAgain =
            customerRepository.findById(1L).orElseThrow();

    assertEquals("Lan Nguyen", loadedAgain.getName());
}
~~~

The assertion can pass even if Hibernate never sent an UPDATE to the database. The second `findById` call can return the exact same entity instance from the persistence context's first-level cache.

Within the same persistence context, JPA guarantees an entity identity is represented by the same managed instance. Thus, re-reading through the repository does not necessarily trigger a fresh SELECT.

This can mask bugs such as:

- Invalid UPDATE due to wrong column name or mapping.
- INSERT/UPDATE violating a unique constraint.
- Nonexistent foreign key.
- Value exceeding column length.
- Incompatible data type.
- Generated SQL incompatible with the database dialect.
- Relationship or cascade mappings preventing expected statements from executing.

A test that merely re-reads a managed entity may never touch the database at assertion time. To test real persistence, force a flush and, when needed, evict the entity from the persistence context before re-reading.

## 5. Basic Test Pattern: Save Then Flush

A repository test can be written as:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldInsertCustomerIntoDatabase() {
        Customer customer =
                new Customer("Lan", "lan@example.test");

        customerRepository.save(customer);

        entityManager.flush();

        assertNotNull(customer.getId());
    }
}
~~~

Flush ensures the database executes the INSERT before the test ends. However, asserting on the ID is still not the strongest evidence of reading data back from the database. To verify a round-trip, combine `clear` with re-querying.

## 6. Combining `flush()` and `clear()` to Test a Database Round-Trip

`EntityManager.clear()` evicts all entities from the persistence context and turns managed entities into detached ones. Afterward, when querying again, the ORM cannot return the same managed instance from the old persistence context's first-level cache.

Common pattern:

~~~java
@Test
void shouldPersistAndReloadCustomer() {
    Customer customer =
            new Customer("Lan", "lan@example.test");

    customerRepository.save(customer);

    entityManager.flush();
    entityManager.clear();

    Customer reloaded = customerRepository
            .findById(customer.getId())
            .orElseThrow();

    assertEquals("Lan", reloaded.getName());
    assertEquals("lan@example.test", reloaded.getEmail());
}
~~~

Meaning of each step:

1. `save()` puts the entity through JPA's persist/merge flow.
2. `flush()` forces pending changes down to the database.
3. `clear()` removes managed entities from the persistence context.
4. `findById()` must reload the entity through the persistence layer.
5. Assertions verify the reloaded data matches expectations.

This is a stronger check than asserting only on the object just saved.

Remember `clear()` affects the entire persistence context, not just the entity saved last. Every managed entity becomes detached. If the test still needs those objects, save their IDs or comparison values before clearing.

## 7. How Does `clear()` Differ from `refresh()`?

Both methods help avoid relying solely on an object's current in-memory state, but their purposes differ.

**`clear()`**

- Detaches every entity in the persistence context.
- Does not reload entities by itself.
- Subsequent queries must fetch entities through an empty persistence context or the database.
- Appropriate when verifying a round-trip by re-querying.

**`refresh(entity)`**

- Instructs the `EntityManager` to reload the state of a single managed entity from the database.
- Overwrites unflushed in-memory changes on the object with database state.
- Applies only to a managed entity.
- Appropriate when re-synchronizing a specific entity with current database data.

Example using `refresh`:

~~~java
@Test
void shouldRefreshCustomerFromDatabase() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customer.setName("Unsaved name");

    entityManager.refresh(customer);

    assertNotEquals("Unsaved name", customer.getName());
}
~~~

Here, the unflushed change is discarded and state is read back from the database. If you want to verify a saved change, flush before refreshing:

~~~java
customer.setName("Lan Nguyen");

entityManager.flush();
entityManager.refresh(customer);

assertEquals("Lan Nguyen", customer.getName());
~~~

`refresh()` does not replace `clear()` in all scenarios. If you want to test the normal entity reloading path as a regular query, `flush` + `clear` + `find` usually expresses intent more clearly.

## 8. Catching Unique Constraints Only on Flush

One of the most important examples is testing duplicate data.

Suppose the `customer` table has a unique constraint on `email`:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);
~~~

Test creating two customers with the same email:

~~~java
@DataJpaTest
class CustomerConstraintTest {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldRejectDuplicateEmailWhenFlushed() {
        customerRepository.save(
                new Customer("Lan", "same@example.test")
        );

        customerRepository.save(
                new Customer("Minh", "same@example.test")
        );

        assertThrows(
                PersistenceException.class,
                entityManager::flush
        );
    }
}
~~~

If `flush` is omitted, both `save` calls may merely register the entities in the persistence context. The test method might reach the end without seeing any error; the error only appears when the transaction flushes during teardown.

With an explicit flush, the test pinpoints the exact moment the database is expected to reject duplicate data.

The exact exception type can vary across JPA providers, Spring exception translation, and databases. When writing assertions, choose the exception level matching the API being invoked. The example above calls `EntityManager` directly and uses `PersistenceException` per the JPA contract. If the test calls a repository method and relies on Spring Data's exception translation, it may need to check `DataIntegrityViolationException` or the project's corresponding exception.

Some databases support deferred unique constraints. If a constraint is configured to check only at commit, flush may not catch the error yet. Check the semantics of the database management system in use.

## 9. Catching Foreign Key Errors

Suppose an order must reference an existing customer:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

If creating an order with a nonexistent `customer_id`, the failure can surface when the INSERT executes:

~~~java
@Test
void shouldRejectOrderWithMissingCustomer() {
    Order order = new Order(999999L, new BigDecimal("250000"));

    orderRepository.save(order);

    assertThrows(
            PersistenceException.class,
            entityManager::flush
    );
}
~~~

If the relationship is mapped with `@ManyToOne` and code assigns a nonexistent customer object, the outcome also depends on reference creation, cascades, and mapping. To test database foreign keys, make sure SQL INSERT actually executes and the database enforces the corresponding constraint.

Flush forces INSERT/UPDATE to occur before assertions, ensuring the test checks more than an in-memory object graph.

## 10. Catching Column Length and Data Type Errors

Suppose the `name` column has a `VARCHAR(100)` limit, yet a test saves a string exceeding the real limit. JPA may keep holding that string in the object without sending SQL yet.

~~~java
@Test
void shouldExposeColumnLengthViolationOnFlush() {
    String longName = "A".repeat(500);

    customerRepository.save(
            new Customer(longName, "long@example.test")
    );

    assertThrows(
            PersistenceException.class,
            entityManager::flush
    );
}
~~~

Whether the database rejects long strings depends on the DBMS and SQL mode. Some systems throw an error, while others truncate data or apply different rules. Run tests on a production-compatible database if column limits represent a critical risk.

Similarly, flush can catch data type conversion errors, decimal precision/scale violations, NOT NULL violations, check constraints, and other constraints when the database executes SQL.

Do not assume Hibernate always checks every constraint in Java before sending SQL. Some validations may run earlier, but the database remains where actual constraints are enforced.

## 11. Testing Dirty Checking with Flush and Clear

Dirty checking is the ORM mechanism that detects changes on a managed entity without calling `save()` again.

Example:

~~~java
@Test
void shouldPersistManagedEntityChanges() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customer.setName("Updated name");

    entityManager.flush();
    entityManager.clear();

    Customer reloaded =
            customerRepository.findById(1L).orElseThrow();

    assertEquals("Updated name", reloaded.getName());
}
~~~

This test verifies:

- The entity is loaded in a managed state.
- The attribute change is detected by Hibernate.
- Flush generates and sends the UPDATE.
- Clear evicts the old object from the persistence context.
- The fresh query reads the saved state.

In JPA, if an entity is already managed, calling `repository.save()` after modifying properties is normally unnecessary. Dirty checking records changes on flush.

Tests can use this pattern to test updates without calling `save()`, thereby verifying managed entity behavior.

## 12. Flushing Before Queries to Verify Consistent State

JPA defines `FlushModeType.AUTO` and `FlushModeType.COMMIT`. With `AUTO`, the provider must ensure changes that could affect query results are synchronized before the query executes per JPA rules. Hibernate may automatically flush before certain queries.

However, do not rely on auto-flush as a substitute for explicit test intent when the goal is catching SQL errors at a specific line.

Example:

~~~java
@Test
void shouldFindNewCustomerWithQuery() {
    customerRepository.save(
            new Customer("Lan", "lan@example.test")
    );

    entityManager.flush();

    List<Customer> results = entityManager.createQuery(
            "select c from Customer c where c.email = :email",
            Customer.class
    )
    .setParameter("email", "lan@example.test")
    .getResultList();

    assertEquals(1, results.size());
}
~~~

An explicit flush tells readers the test requires the INSERT to be sent before the query.

If the query runs in the same persistence context and returns an already-managed entity, it may still reference the managed object. If the goal is testing a database round-trip, call `clear` before the query or before `find` to bypass the first-level cache.

## 13. Flush Modes and Their Effect in Tests

JPA defines two main flush modes:

| Flush Mode | General Behavior |
|---|---|
| `AUTO` | Provider must synchronize changes that could affect query results before executing a query |
| `COMMIT` | Provider is allowed to defer synchronization until transaction commit; queries may not see all pending changes |

The mode can be set on `EntityManager`:

~~~java
entityManager.setFlushMode(FlushModeType.COMMIT);
~~~

Or on a query:

~~~java
query.setFlushMode(FlushModeType.COMMIT);
~~~

Hibernate also provides proprietary modes such as `MANUAL`, `ALWAYS`, and other custom flush modes. These are not part of the standard JPA enum and must be distinguished when code depends on Hibernate.

In regular tests, keep the default unless testing flush policies specifically. If a test sets `COMMIT` or a custom mode, recognize that queries may not auto-flush pending changes.

An explicit `entityManager.flush()` remains the direct way to request persistence context synchronization within the transaction scope.

## 14. Spring Data JPA's `saveAndFlush()`

Spring Data JPA provides `saveAndFlush()` on `JpaRepository`:

~~~java
Customer saved = customerRepository.saveAndFlush(customer);
~~~

This method performs `save` followed by `flush`. It is handy for concise operations in tests or code that must force immediate synchronization.

Compare:

~~~java
customerRepository.save(customer);
entityManager.flush();
~~~

and:

~~~java
customerRepository.saveAndFlush(customer);
~~~

Both can be used to save an entity and flush the persistence context. The difference lies in how API dependencies are expressed:

- `save()` plus `EntityManager.flush()` makes the JPA boundary explicit.
- `saveAndFlush()` is concise when already working through `JpaRepository`.
- `saveAndFlush()` may also flush other pending changes in the persistence context, not just the passed entity.
- Neither method commits the active transaction by itself.

If a repository extends only `CrudRepository` or an interface without `flush()`, use `EntityManager` or extend `JpaRepository` as appropriate.

## 15. Flush and Clear in `@DataJpaTest`

`@DataJpaTest` typically creates a test slice for JPA, configures the `DataSource` and repositories, and runs each test method in a transaction that rolls back after completion.

This is a convenient environment for testing persistence:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldPersistAndReloadProduct() {
        Product product = new Product("BOOK-1", "Spring Testing");

        productRepository.save(product);

        entityManager.flush();
        entityManager.clear();

        Product reloaded = productRepository
                .findBySku("BOOK-1")
                .orElseThrow();

        assertEquals("Spring Testing", reloaded.getName());
    }
}
~~~

The test transaction remains active after `flush` and `clear`. The query after `clear` reads data from the database within the same transaction, so it can see uncommitted changes written by that same transaction.

When the test ends, Spring rolls back the transaction by `@DataJpaTest` default. Thus, the test verifies SQL without leaving data behind afterward.

If a test needs to verify real commit behavior, `@DataJpaTest`'s default rollback does not provide that evidence. Design a dedicated transaction test or test it in an integration/system test with an appropriate transaction boundary.

## 16. Why Can `@DataJpaTest` Pass While Production Still Fails?

Some embedded databases differ from production databases in:

- SQL dialect.
- Constraints and data types.
- Identity/sequence behavior.
- Precision and scale.
- Timestamp/timezone handling.
- Locking and isolation.
- Transaction semantics.
- Deferred constraints.
- Native SQL statements.

Flush helps catch errors when SQL is sent, but it does not eliminate differences across databases. If production runs PostgreSQL, MySQL, or Oracle, consider Testcontainers with that exact DBMS for tests with dialect or constraint risk.

For example, with a PostgreSQL container, the test's `DataSource` can be configured via `@DynamicPropertySource`. Then flush sends SQL to real PostgreSQL inside the container rather than an embedded database.

This is especially important when testing:

- Conditional unique constraints.
- JSON or array columns.
- Sequences and generated identities.
- Native queries.
- Stored procedures.
- Locking or transaction isolation.
- DDL and migrations.

Do not conclude that a passing H2 test proves production SQL is definitely valid.

## 17. Flush When Testing Relationships and Cascades

JPA can cascade operations from parent entities to child entities depending on mappings.

Example:

~~~java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
            mappedBy = "purchaseOrder",
            cascade = CascadeType.PERSIST
    )
    private List<OrderItem> items = new ArrayList<>();

    void addItem(OrderItem item) {
        items.add(item);
        item.setPurchaseOrder(this);
    }
}
~~~

Test:

~~~java
@Test
void shouldPersistOrderAndItemsThroughCascade() {
    PurchaseOrder order = new PurchaseOrder();
    order.addItem(new OrderItem("BOOK-1", 2));
    order.addItem(new OrderItem("PEN-1", 5));

    entityManager.persist(order);
    entityManager.flush();
    entityManager.clear();

    PurchaseOrder reloaded =
            entityManager.find(PurchaseOrder.class, order.getId());

    assertEquals(2, reloaded.getItems().size());
}
~~~

Flush forces the ORM to process INSERTs for the parent entity and cascaded child entities. If relationship mappings, foreign keys, or cascades are wrong, errors can appear during flush.

Clear followed by find forces the test to reload the object graph instead of checking only the in-memory collection.

However, collection loading may be lazy. If assertions access the collection after the persistence context closes, a `LazyInitializationException` can occur. In this test the context is still active, but at real service boundaries it must be clear which data is fetched before the transaction ends.

## 18. Flushing Before Verifying Entity Deletion

When `delete()` is called, the entity may be marked removed in the persistence context. The SQL DELETE might not execute immediately.

~~~java
@Test
void shouldDeleteCustomerFromDatabase() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customerRepository.delete(customer);

    entityManager.flush();
    entityManager.clear();

    assertFalse(customerRepository.findById(1L).isPresent());
}
~~~

If checking the entity immediately after calling `delete`, the test might observe persistence context state only. Flush pushes the DELETE to the database; clear ensures the next `find` does not return the stale object from the first-level cache.

If the entity has foreign key relationships or cascade delete, flush helps surface deletion-order bugs or remaining constraint references to the record.

## 19. Bulk Update/Delete and a Stale Persistence Context

JPQL bulk updates or deletes execute directly against the database without updating individual managed entities in the persistence context.

Example:

~~~java
@Modifying
@Query("""
       update Customer c
       set c.active = false
       where c.lastLogin < :cutoff
       """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

After running a bulk update, previously loaded `Customer` entities may still hold the old `active` value in the persistence context.

A test should make the order explicit:

~~~java
@Test
void shouldDeactivateInactiveCustomers() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    int updated = customerRepository
            .deactivateInactiveCustomers(cutoff());

    entityManager.clear();

    Customer reloaded =
            customerRepository.findById(customer.getId()).orElseThrow();

    assertEquals(1, updated);
    assertFalse(reloaded.isActive());
}
~~~

With bulk queries, you can configure `@Modifying(flushAutomatically = true, clearAutomatically = true)` so Spring Data JPA flushes before running and clears the persistence context afterward.

~~~java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
@Query("""
       update Customer c
       set c.active = false
       where c.lastLogin < :cutoff
       """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

These two options have distinct meanings:

- `flushAutomatically` requests flushing pending changes before executing the bulk query.
- `clearAutomatically` clears the persistence context after the query to avoid using stale entity state.

Do not enable `clearAutomatically` without understanding that every managed entity will become detached. If callers still hold references to those objects, they will not automatically sync with the database.

## 20. When Do Flush and Errors Occur?

A persistence error can appear at several points:

- When calling `persist` or `merge`, if the provider must process a condition immediately.
- On an explicit flush.
- When a query triggers an auto-flush.
- When the transaction commits and the provider flushes remaining pending changes.
- When the database checks deferred constraints at commit.

Therefore, if a test fails at the end of a method or when the transaction ends, do not assume the final assertion caused the failure. SQL might only have been sent during cleanup/commit.

An explicit flush ties the failure directly to the block under test:

~~~java
repository.save(entity);

assertThatThrownBy(entityManager::flush)
        .isInstanceOf(PersistenceException.class);
~~~

When testing constraint errors, place the assertion around `flush` so the test expresses the exact moment the database rejects the operation.

If the exception is translated by Spring, the outer exception type may be `DataIntegrityViolationException`. When calling `EntityManager` directly, exceptions usually come from the JPA provider. Avoid coupling tests to a specific Hibernate exception class unless the test is intentionally tied to Hibernate.

## 21. Flush Does Not Guarantee All SQL Matches Java Call Order

Hibernate manages pending operations in an action queue and can reorder statements based on dependencies and execution strategies. Thus, the order of `save()` calls in Java is not necessarily the order SQL is sent.

Example:

~~~java
repository.save(orderItem);
repository.save(order);
entityManager.flush();
~~~

If `OrderItem` has a foreign key to `Order`, Hibernate may need to process them in an order compatible with mappings and dependencies. Still, if the object graph or cascade is poorly designed, the database can reject the statements.

Do not write tests solely to assert a fixed internal SQL sequence unless that sequence is a business contract. Verify outcomes, constraints, and final state. If an operation order truly matters, design mappings and transactions to make it explicit.

## 22. Cases Where Flush May Not Be Enough

Flush is a critical tool, but not the only testing boundary.

**Deferred constraints**

Some constraints are configured to be checked at commit. Flush may send SQL while the database has not raised an error yet. A test with an actual transaction commit is needed to test this type of constraint.

**Side effects outside the database**

Flush does not send emails, guarantee a message broker received an event, or roll back external APIs. Those side effects require dedicated integration tests.

**Database differing from production**

Flushing on H2 does not prove SQL is compatible with PostgreSQL. Use a compatible database when dialect testing is required.

**Bulk SQL and the persistence context**

Bulk queries can leave managed objects stale. Clear or refresh before assertions.

**Different transactions or threads**

Requests through a real HTTP server have their own transactions. Flushing the test transaction does not synchronize a server thread's transaction.

**Constraints enforced at the application layer**

If validation runs only in a service or Bean Validation, database flushing does not replace validation tests. Test both validation layers and database constraints according to your goals.

## 23. Common Mistakes When Writing Tests with Flush

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Test passes yet data is not saved properly | Asserting only on managed entities | Call `flush`, `clear`, and re-query |
| Unique constraint error only appears after test finishes | SQL did not run before assertion | Flush immediately inside the test |
| ID is present yet INSERT still fails | ID was allocated before INSERT ran | Flush to force SQL execution |
| `findById` returns edited object even without flush | First-level cache returns managed instance | Flush then clear before re-querying |
| Test still misses deferred constraints | Database checks constraints only at commit | Use a test with an appropriate commit boundary |
| Data disappears after test | `@DataJpaTest` rolls back the transaction | Default behavior; verify within the transaction or design a dedicated commit test |
| Bulk update runs yet entity keeps old value | Persistence context was not synchronized | Clear or refresh the entity |
| Flush fails on an unrelated entity | Flush syncs all pending changes in the context | Isolate setup or flush at clear boundaries |
| H2 test passes yet production fails | Different dialect or constraint semantics | Use Testcontainers with a compatible database |
| Exception type differs from expected | Different JPA provider or Spring exception translation | Assert at the abstraction matching the called API |

## 24. Practicing Repository Tests with Clear Evidence

A good test clearly communicates what it verifies. These patterns can be applied:

### Testing INSERT and Reload

~~~java
repository.save(entity);
entityManager.flush();
entityManager.clear();

Entity reloaded = repository.findById(entity.getId()).orElseThrow();
assertEquals(expected, reloaded.getValue());
~~~

### Testing UPDATE via Dirty Checking

~~~java
Entity entity = repository.findById(id).orElseThrow();
entity.setValue(expected);

entityManager.flush();
entityManager.clear();

Entity reloaded = repository.findById(id).orElseThrow();
assertEquals(expected, reloaded.getValue());
~~~

### Testing DELETE

~~~java
Entity entity = repository.findById(id).orElseThrow();
repository.delete(entity);

entityManager.flush();
entityManager.clear();

assertFalse(repository.findById(id).isPresent());
~~~

### Testing Constraints

~~~java
repository.save(invalidEntity);

assertThrows(
        PersistenceException.class,
        entityManager::flush
);
~~~

### Testing Bulk Update

~~~java
int affected = repository.bulkUpdate(...);

entityManager.clear();

assertEquals(expectedCount, affected);
assertEquals(expectedState, repository.findById(id).orElseThrow().getState());
~~~

Not every test needs both `flush` and `clear`. Pick the right step for the question:

- Only need to catch SQL/constraint errors: `flush`.
- Need to reload state from the database, bypassing the first-level cache: `flush` then `clear`.
- Need to reload one specific managed entity: `flush` then `refresh`.
- Need to verify commit/deferred constraints: design a transactional test with an actual commit.

## 25. Strategy for Using Flush in Spring Framework Testing

When writing data-layer tests, clearly define the required evidence:

| Goal | Appropriate Action |
|---|---|
| Testing logic on a managed object | Direct assertions may suffice |
| Catching INSERT/UPDATE/DELETE errors | Call `flush` |
| Verifying data went through the database and reloaded | `flush` + `clear` + query/find |
| Refreshing a specific entity from the database | `flush` + `refresh` |
| Testing unique/foreign key/NOT NULL constraints | Flush inside the exception assertion |
| Testing deferred constraints at commit | Commit transaction in a controlled test |
| Testing bulk updates/deletes | Flush beforehand if needed, clear afterward, then re-read |
| Testing production dialect | Run test against a compatible database |
| Testing data rollback | Use test transaction and verify rollback boundaries |

A practical workflow:

1. Create test data with deterministic keys.
2. Perform operations through the repository or entity manager.
3. Call `flush` at the point where the database should execute SQL.
4. If verifying a round-trip, call `clear` and re-query.
5. Assert on the reloaded state or verify exceptions on flush.
6. Let the test transaction roll back if that is the data-isolation strategy.
7. If verifying commits or deferred constraints, use a separate deliberate transaction boundary.
8. Run on a production-compatible database for dialect- and constraint-related risks.

## 26. Conclusion

The persistence context allows JPA/Hibernate to manage entities and defer SQL until an opportune moment. This mechanism is efficient in applications, but can cause tests to inspect only in-memory objects without checking the database.

Remember three points:

- **`save()`** puts an entity into the persist/merge flow; it does not guarantee SQL has executed.
- **`flush()`** synchronizes pending changes down to the database within the current transaction, catching many SQL and constraint errors early; it does not commit the transaction.
- **`clear()`** evicts entities from the persistence context. Combining `flush` + `clear` + query verifies data is reloaded through the database rather than returned from the first-level cache.

Use `flush` when needing to catch persistence errors at a clear point. Use `clear` when testing round-trips. Use `refresh` when reloading only one specific entity. For deferred constraints, transaction commits, database dialects, or external side effects, add the appropriate complementary tests.

When tests produce evidence that SQL executed and data reloaded from the database, they catch many bugs that assertions on managed entities cannot see.

