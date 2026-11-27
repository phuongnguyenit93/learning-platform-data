# Replacing Deprecated APIs like getOne, getById, and Batch Delete Methods in Spring Data JPA

Spring Data JPA added clearer APIs for obtaining an entity reference and standardized the names of batch delete methods. When upgrading a project, calls such as getOne(), getById(), and deleteInBatch() may trigger deprecation warnings. Simply renaming the method is not enough: you must preserve the intended semantics of the old operation, especially distinguishing obtaining a reference from verifying that an entity exists, and distinguishing individual entity deletion from bulk delete.

This lesson focuses on two groups of changes:

- Replacing getOne() and getById() with getReferenceById() when the code truly needs an entity reference; using findById() when you need to confirm the entity exists and handle the not-found case.
- Replacing deleteInBatch() with deleteAllInBatch(Iterable), or choosing deleteAllByIdInBatch(ids) when only IDs are available. Only use bulk delete when accepting semantics that differ from deleting individual entities: JPA cascades/lifecycle callbacks do not run and the persistence context can become out of sync.

The examples use Spring Data JPA repositories with Customer and PurchaseOrder. Exact APIs can vary by the Spring Data JPA version managed by the Spring Boot BOM; check the actual dependencies before making bulk edits.

## 1. Why were these APIs deprecated?

Older methods may still exist in some Spring Data JPA versions, but current APIs mark them deprecated and direct users to methods with clearer, more descriptive names:

| Old API | Replacement API | Meaning |
|---|---|---|
| getOne(id) | getReferenceById(id) | Obtain a reference to an entity by ID |
| getById(id) | getReferenceById(id) | Obtain a reference to an entity by ID |
| deleteInBatch(entities) | deleteAllInBatch(entities) | Bulk delete a set of entities |
| — | deleteAllByIdInBatch(ids) | Bulk delete by a set of IDs |
| — | deleteAllInBatch() | Bulk delete all entities in the repository |

Both getOne() and getById() have reference-retrieval semantics, not a query confirming the entity exists. getReferenceById() makes that intent explicit.

deleteInBatch() was renamed to deleteAllInBatch(Iterable) to align with deleteAllInBatch() and deleteAllByIdInBatch(). Changing the method name does not turn a bulk delete into per-entity deletion.

According to the current API reference, getReferenceById() has been available since Spring Data JPA 2.7; deleteAllInBatch(Iterable) and deleteAllByIdInBatch(Iterable) have been available since 2.5. Check the version in use if the project is not yet on these lines.

## 2. What semantics do getOne(), getById(), and getReferenceById() share?

These methods return a reference to an entity by primary key. The JPA provider may return a proxy/lazy reference and defer reading the database row until code accesses a property that triggers entity initialization.

Repository example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Old code:

~~~java
Customer customer = customerRepository.getOne(customerId);
~~~

Or:

~~~java
Customer customer = customerRepository.getById(customerId);
~~~

Replacement code in supported versions:

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

The new method name makes it clear the application is obtaining a reference. Do not assume this call has verified that customerId exists in the database.

If the ID does not exist, the provider may typically return a proxy first and throw EntityNotFoundException when the proxy is initialized or a property is accessed. Some providers may detect and report the error earlier. Thus, when the exception is thrown is not always at the getReferenceById() line itself.

## 3. How does getReferenceById() differ from findById()?

This is the most important decision when replacing the old API.

| Criterion | getReferenceById(id) | findById(id) |
|---|---|---|
| Return type | Entity reference | Optional<Entity> |
| Purpose | Obtain a reference to set a relationship or continue operations | Look up and confirm the entity |
| Database read | May defer until data is needed | Usually queries immediately if not already in the persistence context |
| Missing record | May throw EntityNotFoundException when the reference is initialized; provider may report earlier | Returns Optional.empty() |
| Best fit | Assigning an association by ID when related data does not need to be read | Checking existence, displaying data, returning clear business errors |

Use getReferenceById() when the code only needs a structurally valid reference to assign an association and the database enforces integrity with a foreign key:

~~~java
order.setCustomer(
        customerRepository.getReferenceById(customerId)
);
~~~

Use findById() when you need to confirm the ID exists and return a controlled business error:

~~~java
Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() ->
                new CustomerNotFoundException(customerId));
~~~

Do not replace findById() with getReferenceById() solely to save a SELECT if the business flow needs to know immediately whether the customer exists.

## 4. Entity and repository example

Minimal Customer entity:

~~~java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Repository:

~~~java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Spring Data JPA inherits getReferenceById(), findById(), and batch delete methods from JpaRepository. There is no need to redeclare these methods in the interface.

Business exception:

~~~java
package com.example.orders;

public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer not found: " + id);
    }
}
~~~

This example uses a constructor accepting Long to preserve the ID in the error message. The application can map the exception to HTTP 404 at the web layer.

## 5. When to use getReferenceById() to assign an association?

A common use case is creating a PurchaseOrder and assigning a Customer using an ID from the request. If the service does not need to read the Customer's name or other properties, it can obtain a reference:

~~~java
@Transactional
public PurchaseOrder createOrder(
        Long customerId,
        BigDecimal totalAmount) {

    Customer customer =
            customerRepository.getReferenceById(customerId);

    PurchaseOrder order =
            new PurchaseOrder(customer, totalAmount);

    return orderRepository.save(order);
}
~~~

This is an illustrative method in a service with CustomerRepository and PurchaseOrderRepository injected. The PurchaseOrder entity must have a ManyToOne association to Customer and a matching constructor.

The advantage is that the application avoids loading the entire Customer just to set a foreign key. However, a reference does not replace business validation. If customerId is invalid, an error may surface when the association is initialized or when the database checks the foreign key at flush/commit.

If the API must immediately throw CustomerNotFoundException before creating the order, use findById():

~~~java
@Transactional
public PurchaseOrder createOrder(
        Long customerId,
        BigDecimal totalAmount) {

    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() ->
                    new CustomerNotFoundException(customerId));

    PurchaseOrder order =
            new PurchaseOrder(customer, totalAmount);

    return orderRepository.save(order);
}
~~~

Choose based on the business contract and when validation must happen, not solely on SQL statement count.

## 6. Do not use getReferenceById() to read data immediately

Example:

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);

String name = customer.getName();
~~~

Calling getName() can trigger proxy initialization and query the database. If the goal is to display the name, findById() is usually clearer because it explicitly expresses the intent to load the entity.

If you obtain a reference inside a transaction and return the proxy outside the transaction, web-layer code accessing the association after the persistence context has closed will hit LazyInitializationException.

Read the required data and build a DTO inside the transaction:

~~~java
@Transactional(readOnly = true)
public CustomerView getCustomer(Long id) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return new CustomerView(customer.getId(), customer.getName());
}
~~~

DTO:

~~~java
package com.example.orders;

public record CustomerView(Long id, String name) {
}
~~~

Do not return a lazy proxy from a service just because the new method immediately returns an object. The reference may not be fully initialized.

## 7. Checking existence: choose the right API

If you only need to know whether an ID exists, use existsById():

~~~java
if (!customerRepository.existsById(customerId)) {
    throw new CustomerNotFoundException(customerId);
}
~~~

If you need to read the Customer afterward, call findById() to fetch the entity. Do not call existsById() followed by getReferenceById() just to read attributes: that can result in two checks/queries where a single findById() already handles it.

Options:

- Existence check only: existsById(id).
- Need entity and missing-record handling: findById(id).
- Need reference to assign an association without reading the entity: getReferenceById(id).

Checking existsById() before writing still has a race condition if another transaction deletes the entity between the check and the write. Foreign key constraints and database exception handling remain the final safeguard.

## 8. Migrating from getOne() and getById() according to intent

Do not mechanically replace every occurrence of getOne with getReferenceById. Before editing, read the lines following the call to understand what the code does.

| Old code and context | Appropriate replacement |
|---|---|
| Obtaining reference to assign ManyToOne | getReferenceById(id) |
| Reading name/email/status immediately after fetching | findById(id) |
| Need to return 404 if not found | findById(id).orElseThrow(...) |
| Only checking whether record exists | existsById(id) |
| Using reference within the same transaction | getReferenceById(id) |
| Returning entity/proxy from API | Read inside transaction and map to DTO |

Migration examples:

~~~java
// Before: only need a reference to assign the relationship.
Customer customer = customerRepository.getOne(customerId);

// After: expresses the intent to obtain a reference.
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

~~~java
// Before: code uses getById then reads the name.
String name = customerRepository.getById(customerId).getName();

// After: confirm existence and read the data.
String name = customerRepository.findById(customerId)
        .map(Customer::getName)
        .orElseThrow(() ->
                new CustomerNotFoundException(customerId));
~~~

Both changes eliminate deprecated APIs, but only the second clarifies handling of the not-found case.

## 9. Spring Data JPA version and compatibility

Not every project has the same API set. Spring Boot manages Spring Data JPA via its dependency BOM; do not upgrade Spring Data JPA independently without checking compatibility with Spring Framework, Hibernate, and Jakarta Persistence.

API milestones to note:

| API | Version milestone noted in API reference |
|---|---|
| getById(id) | Available since Spring Data JPA 2.5 |
| getReferenceById(id) | Available since Spring Data JPA 2.7 |
| deleteAllInBatch(Iterable) | Available since Spring Data JPA 2.5 |
| deleteAllByIdInBatch(ids) | Available since Spring Data JPA 2.5 |

If a project is on a version earlier than 2.7, getReferenceById() may not exist yet. If you need to obtain a reference on that version, you can use EntityManager.getReference() inside a transaction-managed custom repository/service, or upgrade Spring Data JPA via a compatible BOM.

Example with EntityManager:

~~~java
@PersistenceContext
private EntityManager entityManager;

@Transactional
public Customer reference(Long id) {
    return entityManager.getReference(Customer.class, id);
}
~~~

This is the standard JPA API. However, once the repository supports getReferenceById(), prefer that method for consistency with Spring Data.

Deprecated does not mean the method is already removed in the current version. It signals that the API is no longer recommended and may be removed in a future major version. Resolve warnings before upgrading major versions.

## 10. Replacing deleteInBatch() with deleteAllInBatch()

Old code:

~~~java
customerRepository.deleteInBatch(customers);
~~~

Replacement code:

~~~java
customerRepository.deleteAllInBatch(customers);
~~~

deleteInBatch(Iterable<T>) is deprecated; the API reference points to deleteAllInBatch(Iterable<T>).

Both carry bulk delete semantics. deleteAllInBatch(customers) issues a bulk query for the given entities; it does not mean Spring calls EntityManager.remove() sequentially for each Customer.

Points to remember:

- Does not execute JPA cascade semantics like per-entity deletion.
- Does not emit JPA lifecycle events such as @PreRemove.
- The persistence context may still hold the deleted entities in a managed state.
- Pending changes should be flushed before the bulk operation if they must be written first.
- After the bulk operation, consider clearing/detaching the persistence context to avoid reading stale state.

Do not replace deleteInBatch with deleteAllInBatch if code relies on @PreRemove, cascade REMOVE, orphan removal, or listeners to update related data. In that case, choose the regular entity deletion path.

## 11. Choosing deleteAllByIdInBatch() when only IDs are available

If the caller only has a list of IDs, there is no need to load entities beforehand just to pass them into deleteAllInBatch().

~~~java
customerRepository.deleteAllByIdInBatch(customerIds);
~~~

This method deletes entities identified by the IDs with a bulk query. There is no need for:

~~~java
List<Customer> customers =
        customerRepository.findAllById(customerIds);

customerRepository.deleteAllInBatch(customers);
~~~

if the goal is simply bulk deletion by ID without inspecting each entity.

Comparison:

| Method | Input | Purpose |
|---|---|---|
| deleteAllInBatch() | None | Delete all entities in the repository via a bulk operation |
| deleteAllInBatch(entities) | Entity iterable | Bulk delete the supplied entities |
| deleteAllByIdInBatch(ids) | ID iterable | Bulk delete by ID |
| deleteAll(entities) | Entity iterable | Delete each entity following repository/JPA semantics |
| deleteAllById(ids) | ID iterable | Delete via the normal deletion path, not a batch API |

If you need the count of rows actually affected, the void batch methods do not provide a count. You can write a custom @Modifying query returning int, provided you understand bulk semantics and synchronize the persistence context accordingly.

## 12. How does bulk delete differ from per-entity deletion?

This difference matters more than the method name.

~~~java
customerRepository.deleteAll(customers);
~~~

is the repository's normal entity deletion path. Spring Data processes each entity through the repository/JPA delete mechanism, so cascades and lifecycle callbacks can apply according to the mapping.

~~~java
customerRepository.deleteAllInBatch(customers);
~~~

is a bulk delete. It favors executing a query for the set of entities rather than loading/deleting each entity through the standard lifecycle.

| Behavior | deleteAll(entities) | deleteAllInBatch(entities) |
|---|---|---|
| Deletes via entity remove | Yes | Not per entity |
| JPA cascade REMOVE | Applied per mapping | Not applied |
| @PreRemove / @PostRemove | Invoked per entity lifecycle | Not invoked |
| Number of database operations | Can be multiple statements | Bulk query |
| First-level cache | Entities managed per lifecycle | Can be stale after bulk |
| Best fit | Domains needing cascades/callbacks | Large deletions without per-entity lifecycle |

Actions performed by the database, such as foreign key ON DELETE CASCADE or triggers, are separate database mechanisms. They are not JPA cascades and do not imply that JPA lifecycle callbacks are invoked.

## 13. Persistence context can become stale after bulk delete

Suppose Customer has already been loaded into the persistence context:

~~~java
Customer customer = customerRepository.findById(id)
        .orElseThrow();

customerRepository.deleteAllByIdInBatch(List.of(id));

System.out.println(customer.getName());
~~~

The bulk query deletes the row in the database without synchronizing the managed Customer object. Code can still read the name from the in-memory object even though the row has been deleted.

The Spring Data JPA API reference warns that batch deletes can cause the first-level cache and the database to fall out of sync. Therefore, if continuing to work with the same EntityManager, consider flushing before and clearing afterward.

Example:

~~~java
@Transactional
public void deleteIds(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return;
    }

    entityManager.flush();
    customerRepository.deleteAllByIdInBatch(ids);
    entityManager.clear();
}
~~~

entityManager.flush() synchronizes pending changes before running the bulk delete. entityManager.clear() detaches all currently managed entities in the persistence context.

clear() affects every managed entity in the context, not just the deleted Customers. Only call it when the service boundary and surrounding operations allow it. If other entities must stay managed, design appropriate transaction or persistence context boundaries instead of clearing indiscriminately.

There is no need to mechanically call flush/clear after every repository delete. Check whether relevant managed entities exist, whether unflushed changes exist, and whether code continues using the persistence context after the bulk operation.

## 14. Batch deleting with large ID lists

deleteAllByIdInBatch(ids) executes a bulk query with the ID set. Databases have limits on the number of bind parameters or statement size. With very large lists, a single IN clause can exceed database limits or produce a poor execution plan.

You can split the list into smaller chunks. Chunk size should be chosen based on the database/provider and workload; there is no single number that fits every system.

Illustrative service example with an application-implemented partition helper:

~~~java
@Transactional
public void deleteInChunks(List<Long> ids, int chunkSize) {
    if (ids == null || ids.isEmpty()) {
        return;
    }
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    entityManager.flush();

    for (int start = 0; start < ids.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, ids.size());
        List<Long> chunk = ids.subList(start, end);
        customerRepository.deleteAllByIdInBatch(chunk);
    }

    entityManager.clear();
}
~~~

This example uses a subList view of the original list and passes each slice to the repository. Do not modify the ids list while the loop runs.

If one transaction spans all chunks, a failure in a later chunk can roll back the entire transaction. If you want each chunk committed independently, design separate transaction boundaries and understand the atomicity trade-offs. Do not add REQUIRES_NEW solely for speed without establishing business requirements.

## 15. When cascades and lifecycle callbacks are needed, do not use bulk delete

Suppose Customer has child entities to handle upon deletion:

- Order must be retained or transitioned to another state.
- Address must be deleted via cascade REMOVE.
- An audit listener needs to record events.
- @PreRemove needs to release business resources.

Bulk delete skips per-entity lifecycle, so it cannot satisfy these requirements.

Use the normal entity deletion path:

~~~java
@Transactional
public void deleteCustomers(Collection<Long> ids) {
    List<Customer> customers = customerRepository.findAllById(ids);
    customerRepository.deleteAll(customers);
}
~~~

This approach loads the entities to delete and deletes them through the lifecycle. Database and memory costs can be higher, but JPA entity operation semantics are preserved.

If you need to process a huge number of entities while still emitting domain events/cascades, consider batching groups of entities in bounded transactions, or designing a dedicated bulk workflow that explicitly handles relationships and auditing. Do not expect a bulk DELETE to invoke @PreRemove for each row.

## 16. Batch delete and soft delete

If an entity uses Hibernate @SoftDelete or @SQLDelete, be especially careful when switching to bulk delete.

Entity-level remove can go through the Hibernate-managed soft-delete mechanism. Bulk JPQL deletes and batch APIs typically issue bulk DML without running per-entity remove lifecycle. Therefore, do not assume deleteAllInBatch() or deleteAllByIdInBatch() will produce the same behavior as repository.delete(entity).

If the requirement is to mark records deleted instead of physically deleting them:

- Use entity-level remove if mapping/version/provider confirms soft delete applies to that remove path.
- Or write an explicit bulk UPDATE to set the indicator column according to policy.
- Inspect the actual SQL to verify whether the database receives UPDATE or DELETE.
- Test both deleted data and filtered queries after the operation.

Do not use bulk delete in a soft-delete domain without verifying Hibernate semantics for the running version.

## 17. Batch delete with a custom @Modifying query

If you need conditional deletion and want the count of affected entities, you can use @Modifying:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Modifying(
        clearAutomatically = true,
        flushAutomatically = true
    )
    @Query("""
           delete from Customer c
           where c.id in :ids
           """)
    int deleteBulkByIds(@Param("ids") Collection<Long> ids);
}
~~~

This is a bulk JPQL DELETE. The int return type is the number of affected entities from the provider's executeUpdate result.

The method must be called within a transaction. @Transactional can be placed on the service or repository method depending on project architecture. clearAutomatically instructs Spring Data to clear the persistence context after the query; flushAutomatically flushes pending changes before running the query.

If ids is empty, handle it before calling the repository. Do not rely on the provider to handle an empty IN clause identically across all databases.

Do not write this query if the goal is to trigger JPA cascades or @PreRemove. It is still a bulk delete even though declared with @Query.

## 18. Deciding which API to use in each situation

| Need | Recommended API | Reason |
|---|---|---|
| Obtain reference to assign association | getReferenceById(id) | No need to load entity immediately |
| Read information and handle missing record | findById(id) | Returns Optional |
| Only check whether ID exists | existsById(id) | Accurately expresses intent |
| Delete entities requiring JPA cascades/callbacks | delete(entity), deleteAll(entities) | Goes through entity lifecycle |
| Bulk delete by entity iterable | deleteAllInBatch(entities) | Bulk query |
| Bulk delete by ID | deleteAllByIdInBatch(ids) | Avoids loading entities |
| Bulk delete entire entity table | deleteAllInBatch() | Repository-wide bulk operation |
| Conditional delete needing affected count | @Modifying query returning int | Controls predicate and count |
| Soft delete | Entity-level soft-delete or bulk indicator UPDATE | Do not default to bulk DELETE |

Choose the method based on business requirements, not merely on which old API name is emitting a warning.

## 19. Testing getReferenceById() and findById()

The test below uses @DataJpaTest so the repository actually runs against the JPA provider.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void referenceCanBeUsedToReadAnExistingCustomer() {
        Customer customer = new Customer("Ada");
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();
        entityManager.clear();

        Customer reference = repository.getReferenceById(id);

        assertThat(reference.getId()).isEqualTo(id);
        assertThat(reference.getName()).isEqualTo("Ada");
    }

    @Test
    void findByIdReturnsEmptyForMissingCustomer() {
        assertThat(repository.findById(-999L)).isEmpty();
    }
}
~~~

The first test clears the persistence context before calling getReferenceById to avoid retrieving the already-managed object from setup. Accessing getName() verifies the reference can be initialized and read.

The second test confirms findById represents a missing entity with Optional.empty(). Do not write tests assuming getReferenceById always throws immediately on the method call line, since when a missing ID is detected depends on the provider.

## 20. Testing batch delete

The following test verifies deleteAllByIdInBatch removes rows from the database:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerBatchDeleteTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void deleteAllByIdInBatchRemovesRows() {
        Customer first = new Customer("Ada");
        Customer second = new Customer("Grace");

        entityManager.persist(first);
        entityManager.persist(second);
        entityManager.flush();

        Long firstId = first.getId();
        Long secondId = second.getId();

        repository.deleteAllByIdInBatch(
                List.of(firstId, secondId));

        entityManager.clear();

        assertThat(repository.findById(firstId)).isEmpty();
        assertThat(repository.findById(secondId)).isEmpty();
    }
}
~~~

clear() is called before verifying to avoid reading stale entity state in the persistence context. This test confirms the data outcome; if you need to prove the number of SQL statements, cascades, or lifecycle callbacks, add dedicated SQL logging, datasource proxy, or entity listener tests.

Another test should compare deleteAll(entities) with deleteAllInBatch(entities) when the domain has cascades or @PreRemove, ensuring the team clearly understands the semantics the application depends on.

## 21. Codebase API upgrade checklist

When upgrading Spring Data JPA, follow this order:

1. Check the actual Spring Boot/Spring Data JPA version from the dependency tree or BOM.
2. Find all calls to getOne(), getById(), and deleteInBatch().
3. For each getOne/getById, determine whether the code needs a reference or needs to confirm existence.
4. Replace reference semantics with getReferenceById() if the version supports it.
5. Replace read/validation logic with findById().orElseThrow() or existsById().
6. Replace deleteInBatch(entities) with deleteAllInBatch(entities) only when bulk semantics are acceptable.
7. If only IDs are present, consider deleteAllByIdInBatch(ids).
8. If cascades/lifecycle are needed, keep the delete(entity)/deleteAll(entities) path.
9. Check transactions, flushing, persistence context, and caching after bulk operations.
10. Check soft-delete mappings, foreign keys, triggers, and batch sizes.
11. Run compilation, repository tests, and integration tests on the target database.
12. Review deprecation warnings to catch remaining old APIs.

Do not perform bulk edits with plain text search-and-replace. A getById call might actually be used to check existence; a deleteInBatch call might be accidentally bypassing callbacks the system relies on.

## 22. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| getReferenceById returns an object, then reading a property fails | Reference uninitialized or ID does not exist | Use findById if you need to confirm existence |
| EntityNotFoundException occurs at flush | Missing reference only detected late | Validate with findById or handle FK errors |
| LazyInitializationException after service | Proxy accessed outside persistence context | Read and build DTO inside the transaction |
| Replaced getById with getReferenceById but API still fails | Code needs Optional/not-found handling | Switch to findById().orElseThrow() |
| getReferenceById does not compile | Spring Data JPA is too old | Check version; use EntityManager.getReference or upgrade BOM |
| deleteAllInBatch does not run @PreRemove | Bulk delete skips entity lifecycle | Use deleteAll(entities) if callbacks are required |
| Children are not cascade deleted | Bulk delete does not apply JPA cascades | Delete through entity lifecycle or handle children explicitly |
| Entity is still readable after bulk delete | Persistence context holds stale state | Flush before, clear after when appropriate |
| Bulk delete violates foreign key | Database forbids deleting parent while children exist | Determine deletion order or FK actions |
| Large ID batch causes bind error | Exceeds database parameter/statement limit | Split into chunks per DBMS limits |
| Soft delete performs physical delete | Bulk DELETE does not go through entity remove mapping | Use soft-delete entity operations or bulk UPDATE |
| Test fails to catch stale entity | Test did not clear persistence context | Clear and re-query via repository |
| deleteAllByIdInBatch does not return row count | API returns void | Use a custom @Modifying query returning int if count is truly needed |

## 23. Official API documentation

- JpaRepository API: https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html
- Deprecated API list: https://docs.spring.io/spring-data/jpa/docs/current/api/deprecated-list.html
- Spring Data JPA reference: https://docs.spring.io/spring-data/jpa/reference/
- Jakarta Persistence EntityManager: https://jakarta.ee/specifications/persistence/

The JpaRepository API reference clearly documents that getOne/getById are replaced by getReferenceById, deleteInBatch is replaced by deleteAllInBatch(Iterable), and the limitations of bulk delete regarding the first-level cache, cascades, and lifecycle events. Consult the documentation for your project's exact version line when upgrading.

## 24. Conclusion

getOne() and getById() are reference-retrieval APIs; the current replacement is getReferenceById(). A reference does not mean the entity has been confirmed to exist. If you need to read data or return a clear not-found error, use findById() and handle the Optional; if you only need to check existence, use existsById().

deleteInBatch() is replaced by deleteAllInBatch(Iterable). When only IDs are available, deleteAllByIdInBatch(ids) avoids loading entities prior to bulk deletion. Batch APIs skip JPA cascades and lifecycle callbacks and can leave the persistence context stale. If the domain requires callbacks, cascades, or entity-level soft delete, use the appropriate entity deletion path. Before upgrading, verify versions, the intent of each call site, transactions, and tests on a real database.
