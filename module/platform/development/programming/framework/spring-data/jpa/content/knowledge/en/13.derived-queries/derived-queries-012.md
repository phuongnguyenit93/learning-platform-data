# existsBy, countBy, deleteBy, and removeBy

Spring Data JPA lets you derive existence-check, record-counting, and entity-deletion queries from repository method names. The four common prefixes are **existsBy**, **countBy**, **deleteBy**, and **removeBy**. They express business operations directly on the repository without writing JPQL for simple conditions.

The key point is that each group has a different purpose and cost: `existsBy` answers whether a condition is satisfied; `countBy` returns the number of matching records; `deleteBy` and `removeBy` delete entities matching the condition using Spring Data JPA's derived delete mechanism. Notably, derived delete has different lifecycle behavior from bulk JPQL `DELETE`.

This lesson uses Spring Data JPA 3.x, Jakarta Persistence, and Java 17+.

## 1. General syntax of derived queries

Spring Data parses method names to generate queries based on the entity and Java properties:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);

    long countByActiveTrue();

    long deleteByActiveFalse();

    long removeByCreatedAtBefore(Instant cutoff);
}
```

Key parts:

- **existsBy**: checks whether any entity matches the condition.
- **countBy**: counts entities matching the condition.
- **deleteBy**: deletes entities matching the condition.
- **removeBy**: synonym for `deleteBy` in derived delete queries.

The part after `By` defines conditions based on Java property names. Multiple conditions can be combined with `And`, `Or`, and operators such as `GreaterThan`, `Before`, `Between`, `In`, `IsNull`, `Containing`, or `IgnoreCase`.

For example, this method:

```java
boolean existsByEmailIgnoreCaseAndActiveTrue(String email);
```

means checking whether any Customer has an email matching the passed value case-insensitively and `active = true`.

Method names must match the entity's property paths, not database table or column names. If the property is `customer.id`, an underscore can be used to explicitly separate the path:

```java
long countByCustomer_IdAndStatus(
    Long customerId,
    OrderStatus status
);
```

## 2. existsBy: checking existence

`existsBy` returns `boolean` or `Boolean`, indicating whether at least one entity satisfies the condition.

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);

    boolean existsByEmailAndActiveTrue(String email);

    boolean existsByPhoneNumber(String phoneNumber);
}
```

Usage in a service:

```java
@Service
public class RegistrationService {

    private final CustomerRepository customerRepository;

    public RegistrationService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public boolean emailAlreadyRegistered(String email) {
        return customerRepository.existsByEmailIgnoreCase(email);
    }
}
```

Results:

- `true`: at least one matching record exists.
- `false`: no matching record exists.

You do not need to load the entire list of Customers just to check existence. Using `existsBy` expresses the exact intent and gives the provider an opportunity to generate a suitable query. Actual SQL may vary across Hibernate versions, dialects, and releases; do not assume every `existsBy` always translates into one single SQL syntax.

### 2.1. existsBy does not replace a unique constraint

A common design mistake is checking `existsByEmail` before inserting:

```java
if (repository.existsByEmail(email)) {
    throw new DuplicateEmailException();
}

repository.save(new Customer(email));
```

A race condition can occur between the two operations:

1. Transaction A checks that the email does not exist.
2. Transaction B also checks that the email does not exist.
3. A inserts.
4. B inserts the same email.

Both checks can return `false`, yet the database receives two competing inserts. Therefore, if emails must be unique, enforce a unique constraint/index in the database. `existsBy` helps perform an early check and produce a friendly error message; the unique constraint is the final safeguard.

Mapping example:

```java
@Column(name = "email", nullable = false, unique = true, length = 254)
private String email;
```

If the schema is managed with Flyway or Liquibase, create the unique constraint in the corresponding migration. In the service, still handle unique constraint violation errors because pre-checks do not eliminate concurrent races.

### 2.2. existsBy with multiple conditions

Combined keywords can be used:

```java
boolean existsByEmailIgnoreCase(String email);

boolean existsByStatusAndCreatedAtAfter(
    OrderStatus status,
    Instant createdAt
);

boolean existsByCustomer_IdAndStatus(
    Long customerId,
    OrderStatus status
);

boolean existsByActiveTrueAndDeletedAtIsNull();
```

Long method names can make repositories hard to read. When conditions become complex, have multiple OR branches, or require special joins, consider `@Query` or `Specification`.

## 3. countBy: counting matching entities

`countBy` returns the number of records matching the condition. Prefer `long` to avoid 32-bit integer overflow on large tables.

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    long countByStatus(OrderStatus status);

    long countByCustomer_Id(Long customerId);

    long countByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt
    );

    long countByTotalAmountGreaterThan(BigDecimal amount);
}
```

Service example:

```java
@Transactional(readOnly = true)
public long countPendingOrders() {
    return orderRepository.countByStatus(OrderStatus.PENDING);
}
```

`countBy` is commonly used for:

- Counting orders by status.
- Counting active products.
- Counting records belonging to a customer.
- Counting transactions within a time window.
- Checking counts before allowing a business operation.

### 3.1. countBy does not load all entities

Unlike `findBy`, which returns a list of entities, `countBy` returns a numeric value. The provider generates a count query, typically based on SQL `COUNT`. That avoids building full entity object graphs just to obtain a count.

However, counting is not always cheap. If the filter lacks a suitable index or the table is huge, the database may still have to read many rows/index entries to compute the result. Inspect execution plans and design indexes around real query conditions.

For example, if you frequently count orders by `customer_id` and `status`:

```sql
CREATE INDEX idx_orders_customer_status
    ON purchase_orders (customer_id, status);
```

Index column order should be based on filters, selectivity, and actual queries. Do not create indexes simply because a `countBy` method exists in code.

### 3.2. Be careful with distinct

Spring Data supports method names containing `Distinct`, but understand what `distinct` is applied to. For example:

```java
long countDistinctByLastname(String lastname);
```

For a `User` entity with a unique ID, counting distinct entities is typically equivalent to counting matching Users. It does not necessarily mean counting the number of different `lastname` values.

If the requirement is to count distinct last names within a group, write explicit JPQL:

```java
@Query("""
    select count(distinct c.lastname)
    from Customer c
    where c.active = true
    """)
long countDistinctActiveLastnames();
```

Reading the method name alone is not enough to infer the desired SQL semantics. For distinct counts on a specific property, use `@Query` to express `count(distinct ...)` explicitly.

### 3.3. countBy over to-many relationships

When conditions traverse `OneToMany` or `ManyToMany` relationships, joins can produce multiple SQL rows for the same root entity. If you need to count unique root entities, specify a distinct count on ID or write explicit JPQL.

Example counting customers with confirmed orders:

```java
@Query("""
    select count(distinct c.id)
    from Customer c
    join c.orders o
    where o.status = :status
    """)
long countCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

This makes clear that unique Customers are being counted, even if one Customer has multiple matching orders.

## 4. deleteBy: deleting entities by condition

Derived delete queries begin with `deleteBy`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    long deleteByActiveFalse();

    long deleteByCreatedAtBefore(Instant cutoff);

    void deleteByEmail(String email);
}
```

The method can return `void` or the count of deleted entities, typically `long`. Example:

```java
@Transactional
public long deleteInactiveCustomers(Instant cutoff) {
    return customerRepository.deleteByCreatedAtBefore(cutoff);
}
```

Understand derived delete semantics accurately: Spring Data JPA typically fetches the matching entities and deletes them individually via `EntityManager.remove`. This allows JPA entity lifecycle hooks, callbacks, and cascades to run.

That means `deleteBy` does not necessarily issue a single SQL `DELETE` statement. The provider may `SELECT` matching entities and then emit `DELETE` per entity, or batch them depending on configuration. When record counts are very large, entity loading and persistence context overhead can be significant.

### 4.1. Why does derived delete differ from bulk DELETE?

With derived delete:

1. Spring Data executes a query to fetch matching entities.
2. Those entities become managed in the persistence context.
3. `EntityManager.remove` is called for each entity.
4. `@PreRemove` and entity lifecycle callbacks can execute.
5. `CascadeType.REMOVE` and orphan removal are applied per mapping.
6. SQL `DELETE` statements are synchronized on flush/commit.

This mechanism fits when deletion must obey entity lifecycle hooks and related domain logic.

For very large volumes, loading every entity can consume excessive memory. If the goal is simply bulk deletion by condition without per-entity JPA callbacks/cascades, you can use a bulk JPQL `DELETE` via `@Modifying`. The two approaches behave differently and should be chosen based on business requirements.

### 4.2. Deleting by status

Example deleting expired draft orders:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    long deleteByStatusAndCreatedAtBefore(
        OrderStatus status,
        Instant cutoff
    );
}
```

Service:

```java
@Transactional
public long removeExpiredDrafts(Instant cutoff) {
    return orderRepository.deleteByStatusAndCreatedAtBefore(
        OrderStatus.DRAFT,
        cutoff
    );
}
```

Before deleting, verify business rules: are draft orders allowed to be deleted, are they referenced by payment or audit records, or must history be preserved? If business audit trails are required, soft delete or status transition may be more appropriate than physical deletion.

## 5. removeBy: alias for deleteBy

Spring Data JPA supports `removeBy` as an equivalent naming option to `deleteBy`:

```java
long removeByStatus(OrderStatus status);

long deleteByStatus(OrderStatus status);
```

Both methods express deleting entities by condition. Standardize on one naming convention across your project so repositories remain consistent and readable. `deleteBy` is often more immediately recognizable when readers scan for deletion behavior.

Do not think of `removeBy` as a different deletion mechanism, nor confuse it with `EntityManager.remove(entity)`. In derived queries, `removeBy` is simply a prefix Spring Data recognizes as a delete query from the method name.

## 6. Bulk delete with @Modifying and @Query

If you need to delete very large numbers of rows without invoking per-entity JPA callbacks/cascades, use bulk JPQL `DELETE`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Modifying
    @Query("""
        delete from Customer c
        where c.active = false
          and c.createdAt < :cutoff
        """)
    int bulkDeleteInactiveBefore(
        @Param("cutoff") Instant cutoff
    );
}
```

Service:

```java
@Transactional
public int bulkDeleteInactive(Instant cutoff) {
    return customerRepository.bulkDeleteInactiveBefore(cutoff);
}
```

`@Modifying` informs Spring Data that the `@Query` mutates data. It is used with query methods annotated with `@Query`; derived `deleteBy` methods do not need `@Modifying`.

Bulk JPQL `DELETE` executes directly against the database. It does not load individual entities and does not call `EntityManager.remove` per entity. Therefore:

- `@PreRemove` and entity listeners are not invoked per entity.
- JPA `CascadeType.REMOVE` is not executed as it is when removing individual entities.
- `orphanRemoval` does not automatically run as when mutating entity associations.
- The persistence context may still hold entities that have been deleted from the database.
- Database foreign keys still apply; if referencing child rows exist, the `DELETE` statement may fail.
- Database triggers and constraints still run according to the database engine's rules.

Bulk delete is typically faster for large record counts, but you must manage relationship consequences and in-memory state yourself.

### 6.1. flushAutomatically and clearAutomatically

`@Modifying` has two useful attributes:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    delete from Customer c
    where c.active = false
    """)
int bulkDeleteInactive();
```

- **flushAutomatically = true** flushes the persistence context before executing the modifying query, synchronizing pending changes.
- **clearAutomatically = true** clears the persistence context after the query runs, preventing continued use of managed entities that may now be stale.

`clear()` detaches all entities in the current persistence context, not only the deleted Customers. Existing Java object references remain in memory, but are no longer managed. If you need to keep modifying entities afterward, re-read or merge them according to your workflow.

Do not enable `clearAutomatically` blindly if the service relies on other managed entities remaining attached. Evaluate its impact on the whole persistence context.

## 7. Transactions when using deleteBy and bulk delete

Delete operations must execute within an appropriate transaction. The clearest approach is placing `@Transactional` on the service wrapping the business operation:

```java
@Service
public class CustomerCleanupService {

    private final CustomerRepository repository;

    public CustomerCleanupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long deleteExpiredCustomers(Instant cutoff) {
        return repository.deleteByCreatedAtBefore(cutoff);
    }

    @Transactional(readOnly = true)
    public long countExpiredCustomers(Instant cutoff) {
        return repository.countByCreatedAtBefore(cutoff);
    }
}
```

CRUD methods inherited from `SimpleJpaRepository` carry default transaction configuration. Custom-declared query methods do not automatically inherit write-transaction configuration by default; declare `@Transactional` on the service or repository when needed.

If derived delete is called outside an appropriate transaction, the operation can fail with `TransactionRequiredException` or transaction errors depending on context. Bulk `@Modifying` queries also require a transaction to execute `UPDATE`/`DELETE`.

Wrapping both checks and deletes in a transaction establishes a clear boundary, though it does not automatically solve every race condition. If data can be modified concurrently, determine required isolation, locking, or constraints.

## 8. Entity deletion and cascades

Suppose Customer has Orders:

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.REMOVE,
    orphanRemoval = true
)
private List<PurchaseOrder> orders = new ArrayList<>();
```

When derived `deleteBy` removes each Customer via `EntityManager.remove`, `CascadeType.REMOVE` can delete Orders per the mapping.

When bulk JPQL `DELETE` deletes Customers directly, JPA does not iterate over each Customer and does not cascade `REMOVE` across relationships the way entity removal does. The database may reject the delete due to foreign keys or execute `ON DELETE CASCADE` if configured in the schema.

Do not add `CascadeType.REMOVE` just to make `deleteBy` work. Determine which entities truly depend on another's lifecycle. For transactional records like orders, invoices, and payments, physical deletion can destroy history; dedicated archival and audit policies are usually required.

## 9. Null, boolean, and operators in method names

Derived queries support many operators in conditions:

```java
boolean existsByEmailIsNull();

boolean existsByEmailIsNotNull();

long countByStatusIn(Collection<OrderStatus> statuses);

long countByCreatedAtBetween(Instant from, Instant to);

long countByTotalAmountGreaterThanEqual(BigDecimal amount);

long deleteByStatusIn(Collection<OrderStatus> statuses);

long deleteByCreatedAtBefore(Instant cutoff);
```

Common keywords:

| Keyword | Meaning |
|---|---|
| IsNull / Is | Check for NULL or equality |
| IsNotNull / NotNull | Check for non-NULL |
| True / False | Boolean value |
| In / NotIn | Within or outside a set of values |
| Between | Within a range |
| Before / After | Before or after a timestamp/value |
| LessThan / GreaterThan | Less than / greater than comparison |
| LessThanEqual / GreaterThanEqual | Inclusive comparison |
| IgnoreCase | Case-insensitive comparison for eligible types |
| And / Or | Combine conditions |

When passing `null` to an equality predicate, Spring Data can interpret it as `IS NULL`; with `Not` and `null`, it can become `IS NOT NULL`. However, do not rely on null parameters to represent optional filters. If a condition should be skipped when a parameter is null, build dynamic queries with `Specification` or an appropriate mechanism.

## 10. countBy and existsBy on large datasets

`existsBy` and `countBy` do not load full entities, but they still execute queries on the database. Performance depends on:

- Record volume and condition selectivity.
- Whether indexes support the filtered columns.
- Whether joins traverse one-to-many or many-to-many relationships.
- Database optimizer and statistics.
- Transaction isolation and concurrent updates.

For example, checking existence by email typically needs an index:

```sql
CREATE UNIQUE INDEX uk_customers_email
    ON customers (email);
```

For case-insensitive emails, align data normalization and indexing. A regular index on `email` may not efficiently support `lower(email)` depending on the database. Consider a normalized column or a functional index if supported by the database.

`countBy` usually has to count all matching rows. If you only need to know whether at least one matching row exists, use `existsBy` instead of `countBy > 0` to express intent clearly. The provider/database can optimize existence queries in their own ways.

Do not run `existsBy` immediately followed by `countBy` for the same condition unless there is a distinct business need; two queries add a round trip, and results can still change between reads.

## 11. When should you use @Query or Specification?

Method names fit simple conditions clearly expressible via property paths. When methods grow long, nest multiple `And`/`Or` clauses, need explicit joins, subqueries, `group by`, or distinct counts on a specific property, use `@Query`.

Example counting customers with at least one confirmed order:

```java
@Query("""
    select count(c)
    from Customer c
    where exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
          and o.status = :status
    )
    """)
long countCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

If filters vary across many optional parameters, `Specification`/Criteria can be easier to maintain than proliferating dozens of repository methods. Choose the query approach based on business meaning and required SQL rather than forcing every case into derived queries.

## 12. Testing repository methods

Verify both return values and the resulting database state after operations. In Spring Boot, `@DataJpaTest` is well-suited for testing mappings and repository queries.

Example:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void existsCountAndDeleteUseTheExpectedPredicate() {
        repository.save(new Customer("a@example.com", true));
        repository.save(new Customer("b@example.com", false));
        repository.flush();

        assertThat(repository.existsByEmail("a@example.com")).isTrue();
        assertThat(repository.existsByEmail("missing@example.com")).isFalse();
        assertThat(repository.countByActiveTrue()).isEqualTo(1);

        long deleted = repository.deleteByActiveFalse();

        assertThat(deleted).isEqualTo(1);
        assertThat(repository.count()).isEqualTo(1);
    }
}
```

This is an illustrative outline; constructors, getters, and required fields must match your actual entity. When testing entities with relationships, create valid fixture data satisfying constraints first.

For derived delete, you can test `@PreRemove` or cascades to confirm lifecycle callbacks fire. For bulk delete, write dedicated tests verifying callbacks do not run and the persistence context is cleared/refreshed as configured.

`@DataJpaTest` tests typically run in a transaction and roll back at the end. When verifying commit behavior or cross-transaction interactions, write integration tests with real transaction boundaries and a production-equivalent database engine.

## 13. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Method fails creation at startup | Wrong property name or ambiguous property path | Check entity fields/getters and use underscores when needed |
| existsBy returns false despite existing data | Wrong condition, case mismatch, or different normalization | Inspect SQL, parameters, and collation |
| Two requests register the same email | existsBy check-then-insert race condition | Add database unique constraint and handle duplicate key errors |
| countBy is too slow | Missing index, large join, or full match count | Check execution plan, indexes, and consider alternative queries |
| countDistinctBy counts unexpectedly | Distinct applied to entity ID instead of target property | Write JPQL `count(distinct property)` |
| deleteBy is slow for many records | Derived delete loads and removes entities one by one | Consider bulk JPQL DELETE if lifecycle hooks are unnecessary |
| Bulk delete does not trigger @PreRemove | Bulk queries bypass entity lifecycle | Use derived delete if callbacks are required |
| Bulk delete violates FK | Referencing child records exist or delete order missing | Delete children in order, use intentional DB cascade, or revise domain logic |
| In-memory entity still exists after bulk delete | Persistence context was not cleared | Use `clearAutomatically` or intentionally clear/refresh |
| TransactionRequiredException | Delete/write executed outside a transaction | Add `@Transactional` on service or repository |
| removeBy assumed to be a different API from deleteBy | Confused the two prefixes | They are two naming aliases for derived delete |

## 14. Practice exercises

1. Write `existsByEmail` and `existsByEmailIgnoreCase`; test with mixed-case data.
2. Write `existsByCustomer_IdAndStatus` to check if a customer has orders in a given status.
3. Write `countByStatus` and `countByCreatedAtBetween`; verify results against sample data.
4. Write `countDistinctByLastname` and compare it with JPQL `count(distinct c.lastname)`.
5. Write `deleteByActiveFalse` returning `long` and assert the count of deleted entities.
6. Write `removeByCreatedAtBefore` and compare behavior with the equivalent `deleteBy`.
7. Add a `@PreRemove` callback; confirm derived delete invokes it.
8. Create a bulk JPQL `DELETE` with `@Modifying`; confirm the callback is not invoked.
9. Inspect the persistence context after a bulk delete and try `clearAutomatically`.
10. Simulate two transactions registering the same email concurrently; demonstrate how a unique constraint protects data integrity.
11. Benchmark a `countBy` query on a large table before and after adding an index.
12. Write an integration test verifying transaction rollback when a delete query fails.

**Core principle:** `existsBy` answers yes/no; `countBy` returns a count; `deleteBy` and `removeBy` delete matching entities. Derived delete typically loads entities and removes them individually, preserving JPA lifecycle hooks and cascades at the cost of memory. Bulk JPQL `DELETE` is faster for large sets, but bypasses entity lifecycle/cascades and can leave the persistence context stale. Choose based on business rules, transaction boundaries, and data size.