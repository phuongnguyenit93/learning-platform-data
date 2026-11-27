# Default Transactions of CRUD and Custom Query Methods

Spring Data JPA provides built-in CRUD methods via `CrudRepository`, `PagingAndSortingRepository`, and `JpaRepository`. These methods have default transaction configurations in the `SimpleJpaRepository` implementation class. By contrast, application-declared query methods—such as derived query methods or methods using `@Query`—do not automatically receive a transaction configuration. Understanding this difference helps define proper transaction boundaries, avoid uncommitted writes, prevent errors during bulk updates, and avoid lazy loading issues.

## 1. Default transactions of CRUD methods

In Spring Data JPA, `SimpleJpaRepository` is configured at the class level with `@Transactional(readOnly = true)`. Inherited repository read operations, such as `findById()`, `findAll()`, `existsById()`, and `count()`, therefore run inside a read-only transaction.

Data-modifying operations such as `save()`, `saveAll()`, `deleteById()`, `delete()`, `deleteAll()`, and other write variants are annotated with `@Transactional` without `readOnly = true`. They run inside a writable transaction.

| Method group | Examples | Default configuration |
|---|---|---|
| Read | `findById`, `findAll`, `count`, `existsById` | `@Transactional(readOnly = true)` |
| Write | `save`, `saveAll`, `delete`, `deleteAll` | `@Transactional` |
| Custom query | `findByStatus`, `findRecentOrders` | No default transaction configuration |

Repository example:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

When calling `repository.findById(id)` directly, Spring Data JPA starts or joins a read-only transaction according to the CRUD method's configuration. When calling `repository.save(order)`, the method runs in a write transaction. If there is no outer transaction, the transaction created by the repository method typically ends when the method call completes.

Note: `save()` does not mean the SQL statement is necessarily sent to the database right at that line of code. JPA may defer write operations until flush or commit. If the repository method joins a larger transaction, commit only occurs when the outer transaction ends.

## 2. Custom query methods do not automatically open a transaction

Spring Data JPA does not automatically apply the transaction configuration of inherited CRUD methods to newly declared methods in a repository interface. This applies to:

- Derived queries: Spring parses the method name, e.g., `findByStatus()`, `findByCreatedAtAfter()`.
- JPQL or native queries declared with `@Query`.
- Named queries discovered by Spring Data JPA by convention.

Example:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    @Query("""
        select p
        from PurchaseOrder p
        where p.status = :status
        order by p.createdAt desc
        """)
    List<PurchaseOrder> findRecentByStatus(
            @Param("status") OrderStatus status);
}
```

The two methods above do not have their own transaction boundary simply because they reside in a repository interface. They can still run inside a transaction opened by a service or an external caller. If called standalone, the application should not rely on the assumption that Spring Data JPA will automatically create a transaction for them.

A simple read query can sometimes still return results without an explicit transaction. However, lacking a transaction boundary can cause issues when consistent reads across multiple operations are required, when lazy associations are accessed after the persistence context closes, or when APIs require an active transaction. Therefore, explicitly declare transactional intent on the service or on the repository method.

Configuration can be placed directly on the query method:

```java
@Transactional(readOnly = true)
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Or `@Transactional(readOnly = true)` can be placed at the repository interface level to apply to query methods declared there. For write methods needing a different configuration, place `@Transactional` directly on the method to make the intent explicit.

## 3. Placing transaction boundaries at the service layer

In real applications, a business operation often calls multiple repository methods. If each repository call opens and closes its own transaction, steps can commit independently. When a later step fails, data written by an earlier step may already be committed and cannot roll back together.

A common approach is placing `@Transactional` on the service method representing a business operation. By default, propagation is `REQUIRED`: if a suitable transaction already exists, join it; otherwise, create a new transaction.

The example below illustrates declarations in a Spring Boot and Spring Data JPA project. The code snippets are not a standalone Java file.

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

```java
@Service
@RequiredArgsConstructor
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    @Transactional
    public void markAsPaid(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found: " + orderId));

        order.markPaid();

        // The entity is managed in the persistence context.
        // Dirty checking can write changes on flush/commit.
        // Calling save() is still valid to make the save intent explicit.
        orders.save(order);
    }

    @Transactional(readOnly = true)
    public List<PurchaseOrder> findNewOrders() {
        return orders.findByStatus(OrderStatus.NEW);
    }
}
```

In `markAsPaid()`, calling `findById()` and `save()` joins the same service transaction thanks to the default `REQUIRED` propagation. If an error rolls back the transaction before commit, the order status change is also rolled back. An entity loaded inside an active transaction is managed by the persistence context; when properties are modified, JPA can detect changes via dirty checking, so calling `save()` after loading the entity is usually not technically mandatory. However, calling `save()` can make the intent to persist data clearer to read.

If you simply call `save()` and then call a query method in two independent calls without an enclosing service transaction, the two operations may belong to two different transactions. When the business logic requires atomicity, wrap the entire sequence of operations in a service method annotated with `@Transactional`.

## 4. Meaning of readOnly

`@Transactional(readOnly = true)` marks the transaction as read-only. This is an optimization hint for the transaction manager, JDBC driver, and JPA provider; it is not an authorization mechanism that guarantees all write statements will be blocked.

With Hibernate, a read-only transaction can help reduce change-tracking overhead, such as skipping certain dirty-checking steps. Specific optimizations depend on the provider and configuration.

Use `readOnly = true` for query-only operations:

```java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return orders.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Order not found: " + id));
}
```

Do not modify an entity and expect the changes to be saved inside a read-only transaction. Some provider configurations may not flush changes as expected. Use a write transaction for operations that modify data.

When a service method with `@Transactional(readOnly = true)` calls a write CRUD method, the repository method typically joins the existing transaction due to `REQUIRED` propagation. The outer transaction's configuration determines the actual attributes of the running transaction. Therefore, do not call write operations inside a read-only service transaction.

## 5. Transactions for @Query update or delete methods

`@Query` is commonly used to declare queries. For JPQL `UPDATE` or `DELETE`, `@Modifying` must be added so Spring Data JPA executes the query as a data-modifying operation.

`@Modifying` does not create a transaction by itself. The method must still run inside an active transaction, usually provided by the service or by `@Transactional` placed directly on the repository method.

Example:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") OrderStatus status);
}
```

Placing the transaction boundary at the service:

```java
@Transactional
public int changeOrderStatus(Long id, OrderStatus status) {
    return orders.updateStatus(id, status);
}
```

If you want the repository method to define its own transaction boundary when called standalone, `@Transactional` can be placed directly on the method:

```java
@Modifying
@Transactional
@Query("""
    delete from PurchaseOrder p
    where p.status = :status
    """)
int deleteByStatus(@Param("status") OrderStatus status);
```

Choose a location suited to the business boundary. When the service already has a transaction, a repository method using default propagation will join that transaction.

Options in the example:

- `flushAutomatically = true`: requests flushing the persistence context before running the bulk update query, pushing pending changes to the database prior to the query.
- `clearAutomatically = true`: clears the persistence context after the query runs to avoid continuing to use entities holding stale data. Already-loaded entities may become detached after this operation.

Bulk update/delete queries act directly on the database and do not synchronize individual managed entities the way normal entity modifications do. As a result, the persistence context may contain stale data. Additionally, bulk updates do not execute the full entity lifecycle as when modifying entities individually; consider callbacks, optimistic locking, and `@Version` fields if the business logic depends on them.

## 6. Propagation and configuration precedence

The default propagation of `@Transactional` is `Propagation.REQUIRED`. When a service calls a repository, the repository transaction typically joins the active service transaction rather than opening an independent one.

Example:

```java
@Transactional
public void completeOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.markPaid();
    orders.save(order);

    auditRepository.save(
            new OrderAudit(id, "PAID")
    );
}
```

If both repositories participate in the same transaction manager and the same transaction, the order changes and audit record are committed or rolled back together.

When an outer transactional method calls an inner method using `REQUIRED`, the outer transaction's configuration governs the running transaction. For example, `@Transactional(readOnly = true)` on a service does not turn into a write transaction just because an inner repository method has a standard `@Transactional`. Design service boundaries consistently with the type of operation being performed.

Other attributes such as isolation, timeout, and rollback rules can also be declared in `@Transactional`. If unspecified, Spring uses the defaults of the transaction manager and database management system. Do not assume a specific isolation level is identical across all environments.

## 7. Default rollback rules

By default in Spring, a transaction rolls back when a transactional method exits with a `RuntimeException` or `Error`. Checked exceptions do not automatically trigger a rollback under default rules.

Example:

```java
@Transactional
public void createOrder() throws IOException {
    orders.save(new PurchaseOrder());

    throw new IOException("Cannot write audit file");
}
```

With the default rollback configuration, `IOException` is a checked exception, so the transaction does not automatically roll back solely because of this exception. If the business logic requires a rollback, declare it explicitly:

```java
@Transactional(rollbackFor = IOException.class)
public void createOrder() throws IOException {
    orders.save(new PurchaseOrder());

    throw new IOException("Cannot write audit file");
}
```

`noRollbackFor` can be used when a specific exception type is allowed to exit the method without rolling back. Choose rules according to the data consistency requirements of the business logic.

## 8. Common mistakes

**Assuming every method in a repository has a default transaction.** Inherited CRUD methods receive configuration from `SimpleJpaRepository`, whereas derived queries and custom `@Query` methods do not automatically receive that configuration. Place `@Transactional` on the service or on the query method.

**Using @Modifying and forgetting a transaction.** `@Modifying` only changes how Spring Data executes the query. Without an active transaction, the update/delete statement can fail with an error requiring a transaction.

**Unintentionally splitting one business operation into multiple transactions.** If each repository call opens its own transaction, one step may already be committed before the next step fails. Wrap steps that need atomicity inside a single service method.

**Setting readOnly on an operation that writes data.** This is an optimization hint rather than a safety barrier. The provider may skip flushing or optimize for read-only behavior. Use a write transaction when data modifications are needed.

**Reading an entity and accessing lazy associations after the transaction ends.** When the persistence context is no longer active, initializing lazy associations can throw `LazyInitializationException`. Load needed data inside the transaction, use fetch joins/entity graphs, or map results to an appropriate DTO.

**Assuming save() always sends SQL immediately.** JPA may defer writes until flush/commit. To detect constraint errors earlier in the flow, use `saveAndFlush()` or `flush()` where appropriate; flushing still does not replace committing.

**Calling a transactional method via self-invocation.** In standard proxy configurations, `this.otherMethod()` calls within the same bean do not pass through the Spring proxy, so annotations on the called method may not apply as expected. Place transaction boundaries on methods called from another bean or restructure the service.

**Relying on transactions in repository tests.** Tests using `@DataJpaTest` typically run inside a transaction and roll back afterward. That does not prove a derived query called outside tests will automatically have a transaction.

## 9. How to choose a configuration

| Scenario | Appropriate configuration |
|---|---|
| Single CRUD call | Use the CRUD method's default transaction |
| One business operation calling multiple repositories | Place `@Transactional` on the service method |
| Query-only service | Use `@Transactional(readOnly = true)` |
| Derived query or `@Query` needing its own transaction | Place `@Transactional` on the method or repository interface |
| JPQL/native UPDATE or DELETE | Use `@Modifying` and ensure a transaction exists |
| Checked exception must roll back | Declare `rollbackFor` |
| Bulk update with entities already loaded in the persistence context | Consider flushing before and clearing after the query |

## 10. Troubleshooting checklist when transactions misbehave

1. Determine whether the invoked method is an inherited CRUD method or a custom query method.
2. Check whether the call passes through a Spring bean/proxy.
3. Identify which service opens the transaction and whether propagation joins that transaction.
4. Check whether the transaction is marked read-only while the operation needs to write.
5. For UPDATE/DELETE using `@Query`, verify `@Modifying` is present and an active transaction exists.
6. Check the exception type and rollback rules.
7. For stale data after a bulk update, inspect the persistence context and consider `clearAutomatically`.
8. Check flush/commit timing rather than assuming `save()` wrote immediately to the database.

## Conclusion

Spring Data JPA preconfigures transactions for inherited CRUD methods: read operations default to read-only, while write operations use writable transactions. Custom query methods require explicit configuration when a transaction is needed. For multi-step business operations, the service is the right place to define a unified transaction boundary; `@Modifying` specifies how update/delete queries are executed and still requires an active transaction.