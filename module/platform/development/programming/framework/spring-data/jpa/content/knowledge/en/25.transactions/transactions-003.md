# Placing @Transactional on Services and Coordinating Multiple Repositories

**Module:** Spring Data JPA  
**Knowledge Area:** Transactions

## 1. Objectives

After this lesson, you will be able to:

- Explain why transaction boundaries are typically placed at the Service layer.
- Use a single service method to coordinate multiple Spring Data Repositories within the same transaction.
- Understand how Spring starts, joins, commits, and rolls back a transaction.
- Choose the basic attributes of @Transactional and recognize common pitfalls.
- Verify the atomicity of a business operation involving multiple data reads and writes.

## 2. Why place transaction boundaries at the Service layer?

A business operation often involves multiple data operations. For example, when placing an order, the system must check inventory, subtract item quantities, create the order, and save line items. These operations are business-coupled: if one step fails, prior write steps must also be undone.

The Service layer is usually where a complete use case is expressed. Therefore, it is the appropriate place to define the transaction boundary. The service calls multiple Repositories while keeping them within a single transaction.

If you rely solely on individual Repository transactions, one save operation may already commit before the next operation fails. Data can then end up in a half-finished state. For example: the order is saved, while saving order lines or updating stock fails.

Placing @Transactional on a Service method allows operations to join the same transaction:

- All write operations succeed: the transaction commits.
- An error requires the transaction to roll back: changes belonging to that transaction are reverted together.
- Repositories do not need to open separate independent transactions for each step when an outer transaction already exists.

The boundary should enclose a meaningful business operation, such as creating an order, transferring funds, or updating a profile along with related records. Do not extend transactions across unnecessary work such as waiting on users, making long remote service calls, or processing large files.

## 3. How does Spring handle @Transactional?

In a standard Spring configuration, @Transactional is enforced via an AOP proxy:

1. Another bean calls a public method on a Spring-managed Service bean.
2. The proxy intercepts the call and asks the transaction manager to start a new transaction or join an existing one.
3. The transaction manager manages the EntityManager and database connection within the transaction scope.
4. Repositories called inside the method use the same transaction if they are configured with the same transaction manager and persistence unit.
5. When the method finishes normally, Spring flushes necessary changes and commits. If an error matching the rollback rules occurs, Spring rolls back the transaction.

Spring Boot with Spring Data JPA usually auto-configures JpaTransactionManager for a single persistence unit. In applications with custom transaction configurations or multiple datasources, the right transaction manager must be chosen for the Service.

Example with multiple transaction managers:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void processOrder() {
    // Repositories belonging to this transaction manager
}
~~~

The transaction manager name in the example is illustrative; the exact bean declared in the application must be used.

**Note on SQL execution timing:** JPA has a persistence context. When a managed entity is modified, Hibernate typically tracks that change and writes it to the database on flush. Therefore, a Repository method returning does not mean the transaction has committed. Commit happens when the outer transaction boundary completes successfully.

## 4. Example: placing an order across multiple Repositories

Suppose the application has three data components:

- Inventory: product stock quantity.
- PurchaseOrder: customer order.
- OrderLine: order line items.

Business requirement: check stock, decrease quantity, create the order, and save line items. All must succeed or fail together.

### 4.1. Repository

A pessimistic write lock can be used to lock the inventory record while checking and updating, preventing two concurrent transactions from reading the same quantity and overselling stock.

~~~java
import java.util.Optional;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i
        from Inventory i
        where i.productId = :productId
        """)
    Optional<Inventory> findForUpdateByProductId(
            @Param("productId") Long productId);
}
~~~

The other two Repositories can use inherited CRUD methods:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}

public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {
}
~~~

The example assumes entities have appropriate JPA mappings, Inventory has productId and available fields, and OrderLine references PurchaseOrder.

### 4.2. Placing @Transactional on the Service

~~~java
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class OrderService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Inventory inventory = inventoryRepository
                .findForUpdateByProductId(command.productId())
                .orElseThrow(() ->
                        new EntityNotFoundException("Inventory not found"));

        inventory.reserve(command.quantity());

        PurchaseOrder order = orderRepository.save(
                PurchaseOrder.create(command.customerId()));

        OrderLine line = OrderLine.create(
                order,
                command.productId(),
                command.quantity());

        orderLineRepository.save(line);

        return order.getId();
    }
}
~~~

PlaceOrderCommand can be a Java record:

~~~java
public record PlaceOrderCommand(
        Long customerId,
        Long productId,
        int quantity
) {
}
~~~

The reserve method on Inventory should validate the quantity and available stock before subtracting:

~~~java
public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "Quantity must be greater than 0");
    }

    if (available < quantity) {
        throw new InsufficientStockException(
                "Insufficient stock");
    }

    available -= quantity;
}
~~~

InsufficientStockException should extend RuntimeException if you want Spring to roll back by default.

In the example:

- @Transactional creates a transaction boundary for the entire placeOrder operation.
- findForUpdateByProductId reads and locks the inventory record within the transaction.
- inventory is an entity managed by the persistence context. The change to available is detected by JPA dirty checking; calling inventoryRepository.save(inventory) again is not required.
- orderRepository.save saves the order and returns the saved entity. You should use the entity returned by save, especially when working with new or detached entities.
- orderLineRepository.save saves the order line item.
- If a step throws an error that rolls back the transaction, the inventory change, order, and order line items are reverted together, provided they share the same transaction manager and database transaction.

These are code snippets inside a Spring Boot application with corresponding entities, relationship mappings, constructors/factories, and repositories; they are not a standalone Java program runnable with only `javac`.

## 5. Commit and rollback rules

By default, Spring rolls back when a transactional method exits with:

- RuntimeException or a subclass of RuntimeException.
- Error or a subclass of Error.

For checked exceptions, Spring does not roll back by default. If the business logic requires rollback when a checked exception occurs, declare it explicitly:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void confirmPayment() throws PaymentRejectedException {
    // Update multiple records
}
~~~

Multiple exception types can be declared in rollbackFor. Only use noRollbackFor when you genuinely want a specific error type not to trigger a rollback.

Do not catch and ignore errors inside a transactional method:

~~~java
@Transactional
public void createOrder() {
    try {
        orderRepository.save(...);
        orderLineRepository.save(...);
    } catch (RuntimeException ex) {
        // Logging and continuing may prevent the transaction from rolling back
        log.error("Could not create order", ex);
    }
}
~~~

If the error is swallowed and the transaction has not been marked rollback-only, Spring may commit the changes already made. The usual pattern is to let an appropriate exception propagate outward. If error translation is needed, rethrow an exception with clear semantics that falls under the rollback rules.

Another case: an inner transactional method joins an outer transaction via REQUIRED, throws a RuntimeException causing the transaction to be marked rollback-only, and then the outer method catches the error and continues. When the outer transaction finishes, Spring still rolls back and may throw UnexpectedRollbackException. Catching an exception does not clear a transaction already marked rollback-only.

**Flush is not commit.** saveAndFlush or EntityManager.flush forces JPA to synchronize changes to the database earlier to catch constraint errors. However, the transaction can still roll back after flushing; only when the transaction manager commits successfully is the transaction finalized.

## 6. Commonly used attributes of @Transactional

| Attribute | Default | Meaning |
|---|---|---|
| propagation | REQUIRED | Joins the current transaction; creates a new transaction if none exists |
| isolation | DEFAULT | Uses the default isolation level of the transaction manager/database |
| readOnly | false | Transaction allows reads and writes |
| timeout | Per transaction manager | Transaction time limit if configured |
| rollbackFor | RuntimeException and Error | Specifies additional exception types that must trigger rollback |

### 6.1. Propagation REQUIRED

REQUIRED is the default and is usually suitable for business operations coordinating multiple Repositories:

~~~java
@Transactional
public void placeOrder() {
    inventoryService.reserve();
    paymentRecordService.createRecord();
}
~~~

If inner calls use the same transaction manager, they share the active transaction. When there is no outer transaction, the Service call opens a new transaction.

### 6.2. Propagation REQUIRES_NEW

REQUIRES_NEW suspends the outer transaction and opens an independent transaction. The inner transaction can commit even if the outer transaction rolls back. Therefore, do not use it indiscriminately for operations that must be atomic with the business operation. Choose it only when an independent result is genuinely required, such as certain business logs that must persist even if the main operation fails.

### 6.3. readOnly

For query-only methods:

~~~java
@Transactional(readOnly = true)
public Optional<PurchaseOrder> findOrder(Long id) {
    return orderRepository.findById(id);
}
~~~

readOnly is a hint to the transaction manager and JPA provider to optimize read operations. It is not a security mechanism or absolute guarantee that data writes are impossible. Do not use readOnly = true on methods that need to update entities.

You can place @Transactional(readOnly = true) at the class level and declare @Transactional on write methods to override the class-level default.

## 7. Common mistakes

### 7.1. Self-invocation within the same bean

In default proxy mode, internal calls via `this` do not go through the proxy:

~~~java
@Service
public class OrderService {

    public void process() {
        saveDetails(); // Self-invocation within the same bean
    }

    @Transactional
    public void saveDetails() {
        // Do not rely on this annotation when only called internally
    }
}
~~~

If process calls saveDetails via `this`, the proxy does not intercept that call, so @Transactional on saveDetails may not be applied as expected. Place the transaction boundary on a method called from another bean or extract the processing into a separate Spring bean.

### 7.2. Instantiating a Service with new

An object created with `new` instead of being managed by Spring will not have a transaction proxy. Inject the Service via constructor or Spring's dependency injection mechanism.

### 7.3. Placing transactions only on individual Repositories

Each Repository may have its own transaction configuration for inherited CRUD methods. However, that does not automatically create an atomic boundary for an entire business flow calling multiple Repositories. Custom query methods also do not receive transaction configuration by default unless configured at the call site or on the method. Placing transactions on the Service gives the entire business flow a clear shared boundary.

### 7.4. Assuming every error automatically rolls back

Checked exceptions do not roll back by default. Errors that are caught and not propagated outward can also allow the transaction to continue. Explicitly identify exception types and business rollback policies.

### 7.5. Calling external APIs inside a long transaction

A database rollback cannot automatically undo a sent email, a succeeded HTTP call, or an operation on an independent system. Avoid keeping a transaction open while waiting on network calls. For events that need to be published after commit, you can use @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT). If high reliability between data and events is required, consider Transactional Outbox.

### 7.6. Assuming @Transactional solves all concurrency problems

A transaction ensures operations within it commit or roll back together, but it does not automatically prevent all data contention. For inventory or balances, consider:

- Pessimistic locking when records must be locked during processing.
- Optimistic locking with a @Version field when conflicts are rare and can be detected at update time.
- Conditional SQL updates checking the affected row count.
- Unique constraints and integrity constraints in the database.

The default isolation level depends on the transaction manager and database configuration. Only raise isolation after identifying the specific anomaly to prevent and understanding the impact on locks and throughput.

### 7.7. Using multiple databases while assuming a single local transaction exists

A standard JpaTransactionManager manages a single persistence unit. If Repositories use different datasources or transaction managers, a simple @Transactional does not automatically turn them into a single atomic distributed transaction. An appropriate distributed transaction solution such as JTA/XA is needed if supported, or a compensating/outbox/saga workflow when eventual consistency is acceptable.

## 8. Testing transactions coordinating multiple Repositories

Have integration tests with the corresponding transaction manager and test database. An important scenario:

1. Prepare valid inventory and input data.
2. Call a Service method that performs writes across at least two Repositories.
3. Cause a step after prior writes to throw a RuntimeException or database constraint error.
4. After the Service call ends with an error, re-query the data in an independent verification transaction.
5. Confirm there are no half-created orders/line items and inventory quantities remain as before.

When testing Service transaction boundaries, avoid letting the test method itself run inside an enclosing transaction by default if that alters how commit/rollback is observed. For example, @DataJpaTest typically runs tests inside a transaction and rolls back at the end; this is useful for repository testing but requires care when verifying Service commit behavior. You can use a Spring Boot test without @Transactional on the test method and verify state after the call.

In addition to rollback, verify:

- Both Repositories actually use the same transaction manager in operations requiring atomicity.
- Checked exceptions follow the proper rollbackFor policy.
- Caught exceptions mark the transaction rollback-only when required.
- Two concurrent requests updating the same inventory cannot exceed the allowed quantity.
- Transactions are not held too long due to external service calls or unrelated processing.

## 9. Implementation checklist

- [ ] Place @Transactional on the Service method representing a complete business operation.
- [ ] Repositories requiring atomicity use the same transaction manager and persistence unit.
- [ ] Choose appropriate propagation; prefer REQUIRED for standard coordinated flows.
- [ ] Identify which exceptions must trigger rollback, especially checked exceptions.
- [ ] Do not swallow exceptions when rollback is still required.
- [ ] Do not rely on self-invocation to trigger the transaction proxy.
- [ ] Use readOnly = true for read-only flows and do not use it as a write-blocking mechanism.
- [ ] Have a locking or concurrency-control strategy for contended data.
- [ ] Do not keep transactions open during network calls or long processing.
- [ ] Have integration tests proving changes across multiple Repositories commit or roll back together.

## 10. Conclusion

@Transactional at the Service layer defines the boundary of a business operation. When Repositories join the same transaction and share the same transaction manager, the application can coordinate multiple read/write operations while maintaining atomicity: either all changes commit, or all changes in the transaction roll back. For correct behavior in practice, you need to understand Spring proxies, rollback rules, propagation, transaction manager configuration, and database concurrency issues.