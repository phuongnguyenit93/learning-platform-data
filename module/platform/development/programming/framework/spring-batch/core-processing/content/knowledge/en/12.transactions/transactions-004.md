# Transaction propagation in called services

In Spring Batch, a step often calls Spring services to read, validate, or update business data. When a service has `@Transactional`, the propagation determines how the service participates in an existing transaction: sharing the step's transaction, opening an independent transaction, creating a savepoint, or running without a transaction.

This is an important decision because a chunk-oriented step already has a transaction boundary managed by Spring Batch. If the service uses the same transaction manager as the step and the default `REQUIRED` propagation, the service's operations typically join the chunk's transaction. If the service uses `REQUIRES_NEW`, the work inside can commit independently even if the outer chunk rolls back.

## 1. What is transaction propagation?

Propagation is an attribute of a transactional method call that describes how that call interacts with an existing transaction. In Spring, propagation is typically configured with `@Transactional(propagation = ...)`.

For example, a service called from a processor or writer:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void updateOrder(Order order) {
        orderRepository.save(order);
    }
}
```

By default, `@Transactional` uses `Propagation.REQUIRED`. If the call to `updateOrder` takes place within the chunk's transaction and uses the same transaction manager, the service joins that transaction. If it is called outside a transaction, Spring opens a new transaction for the method.

Propagation does not by itself determine who is allowed to call the service, nor does it replace choosing the transaction manager, rollback rules, or idempotency design. It only specifies how a transactional call participates in the transaction boundary.

## 2. The chunk's transaction and service calls

In a chunk-oriented step, Spring Batch manages the transaction for each chunk. The reader reads items, the processor processes items, and the writer writes the group of items within the scope of the chunk's transaction according to the step configuration.

```text
Chunk transaction begins
       |
       v
ItemReader.read()
       |
       v
ItemProcessor.process()
       |
       +----> OrderService.updateOrder()
       |          Propagation.REQUIRED
       |          joins the current transaction
       |
       v
ItemWriter.write(chunk)
       |
       v
Chunk transaction commits
```

If the service uses the same transaction manager as the step, the database operations in the service can commit together with the chunk. If the processor or writer throws an exception that causes the chunk to roll back, the service's changes in the same transaction are also rolled back.

An example step declaration in Spring Batch 5:

```java
@Bean
Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrders", jobRepository)
        .<OrderRow, Order>chunk(100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

In this example, a service called from the processor or writer needs to use the same `businessTransactionManager` if it wants to participate in the chunk transaction. Placing `@Transactional` on the service alone is not enough to guarantee that it participates in the right transaction; the transaction manager and datasource must correspond.

## 3. Propagation types in Spring

Six propagation modes commonly encountered describe how to handle the cases where a transaction already exists and where it does not:

| Propagation | If a transaction already exists | If no transaction exists |
|---|---|---|
| `REQUIRED` | Joins the current transaction | Creates a new transaction |
| `REQUIRES_NEW` | Suspends the current transaction, creates a new one | Creates a new transaction |
| `NESTED` | Creates a nested scope, typically based on a savepoint if the transaction manager supports it | Creates a new transaction |
| `SUPPORTS` | Joins the current transaction | Runs without a new transaction |
| `NOT_SUPPORTED` | Suspends the current transaction and runs without a transaction | Runs without a transaction |
| `MANDATORY` | Must join the current transaction | Throws an exception because there is no transaction |
| `NEVER` | Throws an exception if a transaction exists | Runs without a transaction |

For most business services called from a step, `REQUIRED` is a reasonable default choice. The other modes should be chosen according to the commit/rollback boundary the business actually requires.

## 4. REQUIRED: join the current transaction

`Propagation.REQUIRED` is the default of `@Transactional`. If the caller already has a transaction, the service joins it. If not, Spring creates a new transaction for the service call.

```java
@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(Order order) {
        // Update inventory in the current transaction
    }
}
```

When `reserve` is called within a chunk transaction using the same transaction manager, the inventory changes belong to the chunk transaction. If the writer subsequently fails and the chunk rolls back, the inventory update is also rolled back.

`REQUIRED` is appropriate when the service's operations are part of the same unit of work as the chunk: updating state, writing target data, or saving business relationships. It helps multiple services participate in one consistent transaction.

## 5. REQUIRES_NEW: open an independent transaction

`Propagation.REQUIRES_NEW` always requires an independent transaction. If the caller has a transaction, Spring suspends the outer transaction, opens a new transaction for the service, and resumes the outer transaction after the new one completes.

```java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String orderId, String message) {
        // Write the audit in an independent transaction
    }
}
```

For example, the processor calls `recordAttempt` while processing a chunk. If the audit transaction commits successfully, the audit record may still exist even if the chunk transaction later rolls back.

```text
Chunk transaction begins
       |
       v
Call AuditService.recordAttempt()
       |
       +-- suspend chunk transaction
       |
       +-- begin new audit transaction
       |       write audit
       |       commit audit transaction
       |
       +-- resume chunk transaction
       |
       v
Chunk hits an error -> roll back chunk transaction

Result: the committed audit remains
```

This is useful behavior when you need to store some information independent of the business transaction, but it also creates risk if used incorrectly. For example, recording “order processed successfully” with `REQUIRES_NEW` before the chunk commits can leave a success audit even though the business data has rolled back.

Do not use `REQUIRES_NEW` for every service call in a processor or writer. Each independent transaction can increase the number of commits, reduce performance, and consume additional connections. While the outer transaction still holds its connection, the new transaction may need a different connection; a pool that is too small can cause waiting or resource deadlock.

## 6. NESTED: nested transactions via savepoints

`Propagation.NESTED` lets the service run in a nested transaction scope inside the current transaction, typically implemented with JDBC savepoints.

```java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalDetails(Order order) {
    // These changes can be rolled back to the savepoint
}
```

Suppose a chunk transaction is active. When a `NESTED` service is called, the transaction manager creates a savepoint. If the nested part fails and the exception is handled at the caller, the transaction can roll back to the savepoint while the work before the savepoint continues. If the outer transaction rolls back, all changes in the nested scope are also rolled back.

`NESTED` is not the same as `REQUIRES_NEW`: the nested scope does not commit independently of the outer transaction. It typically only provides the ability to partially roll back to a savepoint.

Nested transaction capability depends on the transaction manager and the resource. `DataSourceTransactionManager`/`JdbcTransactionManager` may support savepoints when the driver/database supports them; not every transaction manager, especially JPA configurations, supports nested transactions in this way. Check the actual transaction manager before using it.

## 7. SUPPORTS and NOT_SUPPORTED

`SUPPORTS` joins the current transaction if there is one. If the caller has no transaction, the method runs without creating a new transaction.

```java
@Transactional(propagation = Propagation.SUPPORTS)
public OrderSummary loadSummary(String orderId) {
    return summaryRepository.findSummary(orderId);
}
```

This mode can suit read operations that can run inside or outside a transaction. However, if you need a consistent snapshot or an explicit transaction requirement, consider `REQUIRED` instead of relying on the caller.

`NOT_SUPPORTED` suspends the current transaction and runs the method without a transaction. It can be used for operations that should not keep a transaction open, but if the method writes data, those operations are not protected by the caller's transaction and may not be rolled back together with the chunk.

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void callLongRunningExternalService() {
    // Does not participate in the existing transaction
}
```

Do not use `NOT_SUPPORTED` merely to avoid locks or transaction errors without evaluating consistency. When the chunk rolls back, an operation performed outside the transaction may still exist.

## 8. MANDATORY and NEVER

`MANDATORY` requires the caller to already have a transaction. If there is no transaction, Spring throws `IllegalTransactionStateException`. It is useful when the service is only allowed to run as part of a unit of work managed by the caller.

```java
@Transactional(propagation = Propagation.MANDATORY)
public void persistWithinBatchTransaction(Order order) {
    orderRepository.save(order);
}
```

With this approach, calling the service from a controller or scheduler without a transaction will fail, helping detect calls made in the wrong context.

`NEVER` does the opposite: it requires that there be no transaction. If the caller has a transaction, Spring throws `IllegalTransactionStateException`. This mode is rarely used in batch business processing because write operations usually need a transaction, but it can be useful for an API that must, by design, be called outside a transaction.

## 9. Choosing propagation for services in a batch

The choice of mode should be based on the meaning of the operation and the rollback requirements:

| Work in the service | Typically suitable propagation | Reason |
|---|---|---|
| Update business data belonging to the current chunk | `REQUIRED` | Commits/rolls back together with the chunk |
| Write an audit that must exist independently of a business rollback | `REQUIRES_NEW` may be used | The audit transaction commits separately; the meaning of the audit must be clearly defined |
| A partial update that can roll back to a savepoint while keeping the outer part | `NESTED` if supported | Allows local rollback within the outer transaction |
| Read data that can participate in a transaction if the caller has one | `SUPPORTS` | Does not create a transaction itself when run standalone |
| Call an operation outside the current transaction | `NOT_SUPPORTED` | Temporarily suspends the caller's transaction |
| A service that must only be called within a chunk/service transaction | `MANDATORY` | Detects callers lacking a transaction |

Do not choose propagation based only on a method name or a wish to “increase safety”. Write down clearly which operations must commit together with the chunk, which are allowed to exist independently, and what happens when the chunk rolls back.

## 10. Only the same transaction manager can participate in the same transaction

Propagation is applied within the scope of the transaction manager that the transactional method uses. In an application with multiple datasources, the step may use `businessTransactionManager` while the service chooses `batchTransactionManager` or another manager.

```java
@Transactional(
    transactionManager = "businessTransactionManager",
    propagation = Propagation.REQUIRED
)
public void updateOrder(Order order) {
    orderRepository.save(order);
}
```

For the service to participate in the chunk's transaction, ensure that:

- The step uses the correct transaction manager for the business data.
- The service chooses the same transaction manager (or the same transaction resource per the corresponding configuration).
- The service's repository/JdbcTemplate uses a datasource managed by that manager.
- The call takes place on the same thread and goes through Spring's transactional proxy.

If Spring Batch's metadata resides in a separate database, the transaction manager for the JobRepository may differ from the chunk's transaction manager. Two local transaction managers do not by themselves form one atomic transaction across two databases. A situation can occur where the business data commits but the metadata does not, or vice versa; design appropriate idempotency and reconciliation.

## 11. @Transactional works through the Spring proxy

In the default proxy configuration, Spring applies `@Transactional` when the method is called through the Spring bean's proxy. If a method in the same object directly calls another method annotated with `@Transactional`, the internal call (self-invocation) typically does not go through the proxy, and the propagation declared on the called method may not be applied.

An example that is easy to misunderstand:

```java
@Service
public class OrderService {

    public void process(Order order) {
        saveAudit(order); // Internal call on the same object
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // May not open REQUIRES_NEW due to self-invocation
    }
}
```

In this example, `saveAudit` is called directly from `process` on the same instance. With the ordinary proxy mode, the annotation on `saveAudit` is not applied by the interceptor for that internal call.

A clearer approach is to split the part that needs its own propagation into a separate bean:

```java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // Write the audit independently
    }
}

@Service
public class OrderService {

    private final AuditService auditService;

    public OrderService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void process(Order order) {
        auditService.saveAudit(order); // Through the Spring proxy
    }
}
```

Calling through another Spring bean makes the call go through the proxy. When using `@Transactional`, check that the called method can be proxied/intercepted in the configuration in use and that the bean is managed by Spring.

## 12. Rollback rules and propagation are two different configurations

Propagation determines how a transaction is joined or newly created. A rollback rule determines which exception types cause the transaction to roll back. These two concepts are independent.

By default, Spring marks a transaction for rollback when a transactional method throws `RuntimeException` or `Error`. Checked exceptions do not automatically trigger rollback by default. You can declare `rollbackFor` if you need rollback for a checked exception:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = IOException.class
)
public void importFile(Path path) throws IOException {
    // Read and update data
}
```

In Spring Batch, a step also has mechanisms for handling exceptions, skip, and retry. An exception being skipped does not mean all changes in the transaction are automatically kept; the framework may roll back the chunk for recovery and then reprocess the items according to the policy. Check both the service's rollback rule and the step's fault-tolerance policy.

## 13. The effect of REQUIRES_NEW on the connection pool

When the outer transaction is suspended, its connection may still be held while the `REQUIRES_NEW` transaction needs a different connection. If many workers each hold an outer transaction and then wait for the new transaction to obtain a connection, a pool that is too small can cause connection exhaustion or prolonged waiting.

For example, if 10 threads process chunks and each thread holds an outer connection, and then each thread calls a `REQUIRES_NEW` service, a pool of only 10 connections may have no free connections left for the new transactions.

When using `REQUIRES_NEW` in a parallel batch flow, evaluate the pool size, the number of concurrent workers, the connection hold time, and the number of independent service calls. Reducing the number of independent calls, grouping audits per chunk, or using an outbox may be more appropriate.

## 14. Transaction propagation does not automatically cross threads

The transaction context in Spring is typically bound to a thread. If a service creates a task with `@Async`, an executor, or sends work to another thread, the chunk's current transaction is not automatically propagated to the new thread.

```text
Chunk processing thread
   transaction A
       |
       +---- calls executor.submit(...)
                     |
                     v
              New worker thread
              has no transaction A
              may open its own transaction
```

The worker thread needs its own transaction manager and transaction boundary if it writes data. If an asynchronous task must only begin after the chunk commits, use an after-commit event publishing mechanism, an outbox, or a queue. Do not assume a service call on another thread still participates in the chunk transaction.

With partitioning or a multi-threaded step, each worker thread may have its own transaction for its chunk. Design propagation based on the transaction of the current executing thread, not on the transaction of the coordinating thread.

## 15. Common mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using `REQUIRES_NEW` for every write operation | Separates the commit from the chunk, increases connections and overhead | Use `REQUIRED` for data that must commit together with the chunk |
| Using a different transaction manager from the step | The service does not participate in the chunk transaction as expected | Specify the correct `transactionManager` for both the step and the service |
| Calling a transactional method via self-invocation | The propagation on the called method may have no effect | Move the method to another bean or call through the proxy |
| Using `NESTED` when the manager does not support savepoints | A runtime error or no local rollback as expected | Confirm support from the transaction manager/driver |
| Assuming `REQUIRES_NEW` rolls back together with the chunk | Data in the new transaction may have already committed independently | Design audits and side effects around independent semantics |
| Assuming the transaction propagates through `@Async` | The worker thread runs outside the caller's transaction | Create a separate transaction or dispatch the task after commit |
| Confusing propagation with a rollback rule | A checked exception may not roll back as desired | Configure `rollbackFor`/`noRollbackFor` appropriately |
| Separating the metadata and business databases but expecting an atomic commit | The two databases may end up in inconsistent states | Use idempotency, an outbox, or a deliberately designed distributed transaction solution |

## 16. Procedure for choosing propagation for a service

When a service is called from a processor, writer, or tasklet, answer the following questions:

1. Does the service need to commit together with the current chunk/tasklet? If so, typically use `REQUIRED` and the same transaction manager.
2. Does the work need to exist even if the outer transaction rolls back? If so, consider `REQUIRES_NEW` and document the meaning of the independent data.
3. Do you only need to roll back part of the work while keeping the outer transaction? Consider `NESTED` if the transaction manager supports savepoints.
4. Can the service run both inside and outside a transaction? Consider `SUPPORTS`.
5. Must the service run outside a transaction? Consider `NOT_SUPPORTED` or `NEVER`, depending on whether you want to reject a caller that has a transaction.
6. Must the caller provide a transaction? Use `MANDATORY` to detect calls in the wrong context.
7. Does the call go through the Spring proxy, on the same thread, with the same transaction manager and the same datasource?
8. Which exceptions cause rollback, and will the step retry/skip or stop when that exception occurs?

## Conclusion

Transaction propagation controls how a service participates in an existing transaction. In a chunk-oriented step, `REQUIRED` is typically the appropriate choice for business updates that need to commit or roll back together with the chunk, as long as the service uses the same transaction manager and transaction resource as the step.

`REQUIRES_NEW` creates an independent transaction, `NESTED` uses savepoints when supported, and the other modes control joining or avoiding a transaction. Take into account the Spring proxy, self-invocation, rollback rules, the connection pool, and thread/datasource boundaries before choosing a propagation. What matters is that each operation has commit/rollback behavior that matches its business meaning.
