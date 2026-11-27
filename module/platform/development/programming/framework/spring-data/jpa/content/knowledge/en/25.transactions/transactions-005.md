# Propagation REQUIRED, REQUIRES_NEW, and NESTED Limitations with JPA

## 1. Objectives and context

In Spring, transaction propagation determines whether a called method joins an existing transaction, creates an independent transaction, or creates a savepoint for partial rollback. It answers the question **how the called method relates to the caller's transaction**.

Three commonly used values are:

- **REQUIRED**: joins the current transaction; creates a new transaction if none exists.
- **REQUIRES_NEW**: suspends the current transaction and always creates an independent transaction.
- **NESTED**: creates a savepoint inside the current transaction so it can roll back to the savepoint; this is a JDBC-based mechanism and has clear limitations when using JPA.

Two concepts must be distinguished:

- **Physical transaction**: the actual transaction managed by the database/resource, which has the final commit or rollback.
- **Logical transaction scope**: the method scope to which Spring applies transaction attributes. Multiple scopes can participate in a single physical transaction.

For example, a service calling two repositories inside the same `@Transactional` method typically uses only one physical transaction. Each repository call does not create its own separate commit.

To use Spring's propagation, import the following annotation and enum:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
```

Use **org.springframework.transaction.annotation.Transactional** when you need to declare **Propagation.NESTED**. The **jakarta.transaction.Transactional** annotation has standard JTA transaction types but does not include NESTED.

The application needs an appropriate transaction manager and annotation-driven transaction management enabled. Spring Boot usually auto-configures this when the appropriate starter and datasource are present; in manual Spring configuration, **@EnableTransactionManagement** can be used along with a **PlatformTransactionManager** bean.

By default, **@Transactional** uses **Propagation.REQUIRED**, isolation **DEFAULT**, and a read-write transaction. Spring typically rolls back when a method exits with a **RuntimeException** or **Error**; checked exceptions do not automatically trigger a rollback by default. You can declare **rollbackFor** or **noRollbackFor** to change the rules.

In default proxy mode, Spring only applies transactions when calls pass through the bean proxy. One method directly calling another method in the same instance (self-invocation) does not go through the proxy; the annotation on the called method therefore does not create a new propagation boundary. Placing two operations requiring different propagations in two separate Spring beans is an easily controlled implementation approach.

## 2. Comparing the three propagations

| Criterion | REQUIRED | REQUIRES_NEW | NESTED |
|---|---|---|---|
| No current transaction | Creates a new transaction | Creates a new transaction | Creates a new transaction if supported by the transaction manager |
| Existing current transaction | Joins that transaction | Suspends outer transaction, creates a new transaction | Uses outer transaction and creates a savepoint |
| Physical transaction | Shared with caller | Independent from caller | Shared with caller |
| Inner scope rollback | May mark the shared transaction rollback-only | Rolls back only the inner transaction | Rolls back to the savepoint; outer transaction may continue |
| Commit | Commits only when the shared physical transaction ends | Can commit independently before the outer transaction ends | Does not commit independently; final commit still depends on the outer transaction |
| Suitable with JPA | Yes | Yes | Should not be used to roll back EntityManager operations |

**Key distinction:** **REQUIRES_NEW** creates a second physical transaction. **NESTED** only creates a rollback point within the current physical transaction. A savepoint is not an independent transaction.

## 3. PROPAGATION_REQUIRED

### How it works

**REQUIRED** is the default propagation for **@Transactional**.

- If no transaction exists, Spring starts a physical transaction.
- If a transaction already exists, the called method joins that transaction.
- Changes from services and repositories commit or roll back together under the shared transaction.

For example, **OrderService** saves an order and then calls **StockService** to decrease inventory. Both methods use **REQUIRED**, so saving the order and updating inventory belong to the same transaction.

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final StockService stockService;

    public OrderService(
            OrderRepository orderRepository,
            StockService stockService) {
        this.orderRepository = orderRepository;
        this.stockService = stockService;
    }

    @Transactional // REQUIRED is the default
    public void placeOrder(Order order) {
        orderRepository.save(order);
        stockService.decrease(order.getProductId());
    }
}

@Service
public class StockService {

    private final ProductRepository productRepository;

    public StockService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void decrease(long productId) {
        Product product = productRepository.findById(productId)
                .orElseThrow();
        product.decreaseStock(1);
    }
}
```

This is illustrative code showing services and repositories; entities, repository interfaces, and application configuration are omitted. The two services must be separate beans so the **stockService.decrease()** call passes through the Spring proxy.

If **decrease()** encounters an error causing the transaction to roll back, the order-saving transaction also rolls back. The database does not retain a half-saved order while inventory remains unupdated.

### Rollback-only and UnexpectedRollbackException

**REQUIRED** scopes participate in the same physical transaction. If the inner method exits via an exception matching rollback rules, Spring marks the shared transaction as **rollback-only**.

A commonly confusing scenario:

1. The outer method starts a transaction.
2. The inner **REQUIRED** method encounters a **RuntimeException**; the interceptor marks the shared transaction rollback-only.
3. The outer method catches the exception and continues executing.
4. The outer method finishes normally and requests a commit.
5. Spring rolls back the transaction and notifies the caller with **UnexpectedRollbackException**.

Catching the exception in the outer method does not clear the rollback-only flag set by the inner scope. This prevents the caller from mistakenly believing the transaction committed successfully.

This rule applies when the exception passes through the transaction interceptor and triggers a rollback rule. If an error is handled completely inside the method before exiting the interceptor, Spring does not automatically know a rollback is required.

### Transaction attributes when joining an outer transaction

When a **REQUIRED** scope joins an existing transaction, the outer transaction determines the actual attributes. By default, isolation, timeout, and read-only declared on the inner scope are ignored. You can enable **validateExistingTransaction** on the transaction manager to detect incompatible isolation or read-only configurations and reject joining.

**Use REQUIRED when:**

- Multiple operations must succeed or fail together.
- One service use case calls multiple repositories.
- Consistency is needed across orders, order line items, inventory, or related data.

## 4. PROPAGATION_REQUIRES_NEW

### How it works

**REQUIRES_NEW** always creates a new physical transaction. If an outer transaction is running, Spring suspends it while the inner transaction executes.

When the inner method completes:

- On success, the inner transaction commits independently.
- On failure matching rollback rules, the inner transaction rolls back independently.
- Spring resumes the outer transaction so the outer method continues.

The inner transaction does not share commit/rollback outcomes with the outer transaction. Therefore, an already-committed inner transaction is retained even if the outer transaction later rolls back.

### Example: independent failure logging

Suppose creating an order fails and the order-creation transaction must roll back, yet the system still wants to save an audit record about the failure. A separate audit bean with **REQUIRES_NEW** can be used.

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String orderCode, String reason) {
        auditRepository.save(new AuditLog(orderCode, reason));
    }
}

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditService auditService;
    private final PaymentGateway paymentGateway;

    public OrderService(
            OrderRepository orderRepository,
            AuditService auditService,
            PaymentGateway paymentGateway) {
        this.orderRepository = orderRepository;
        this.auditService = auditService;
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public void placeOrder(Order order) {
        orderRepository.save(order);

        try {
            paymentGateway.charge(order);
        } catch (PaymentRejectedException ex) {
            auditService.recordFailure(
                    order.getOrderCode(), ex.getMessage());
            throw ex;
        }
    }
}
```

**PaymentRejectedException** in the example is a business exception extending **RuntimeException**; **PaymentGateway**, domain classes, and repositories are omitted. **AuditService** is another bean so the call goes through the proxy and creates a new transaction.

When **recordFailure()** saves the audit successfully, it commits before the exception is rethrown. The exception continues exiting **placeOrder()**, causing the order-creation transaction to roll back under default rules; the audit record persists.

The example uses **orderCode** as the audit reference code. If the outer transaction just created an uncommitted order row and the new audit transaction needs to reference that row via a foreign key, the new transaction may not see the uncommitted row or may be blocked by the foreign key constraint. Design data relationships to suit the independence of the two transactions.

### Resources and risks

While the outer transaction is suspended, its resources—such as its connection—may still be held. The **REQUIRES_NEW** transaction needs its own resource, typically another database connection.

If many threads simultaneously hold an outer transaction's connection while waiting for a connection for the inner transaction, the connection pool can exhaust and cause waiting or deadlocks. Spring documentation recommends the pool capacity exceed the number of concurrent threads by at least one connection when using this model; systems with multiple nested **REQUIRES_NEW** layers must account for additional resource consumption.

The new transaction also cannot freely read uncommitted changes from the outer transaction. If it accesses a row locked by the outer transaction, it may have to wait. Therefore, do not mechanically use **REQUIRES_NEW** inside loops or on every repository operation.

**Use REQUIRES_NEW when:**

- An audit log or secondary state must persist independently of the main business outcome.
- A secondary operation needs its own isolation, timeout, or read-only setting.
- It is acceptable for the secondary transaction to commit even if the main transaction fails.

Do not use **REQUIRES_NEW** for outbox records that must synchronize atomically with business data. With transactional outbox, business records and outbox entries normally must commit in the same **REQUIRED** transaction; splitting them can lead to business data rolling back while events are still emitted, or vice versa.

## 5. PROPAGATION_NESTED and limitations with JPA

### How savepoints work

**NESTED** uses a single physical transaction but creates a savepoint at the inner scope boundary.

Suppose the outer transaction performs A, calls a nested scope performing B, and then performs C:

1. The outer transaction begins and executes A.
2. Spring creates a savepoint.
3. The nested scope executes B.
4. If the nested scope rolls back, the database reverts to the savepoint: B is undone, while A remains in the transaction.
5. The outer transaction continues and executes C.
6. When the outer transaction commits, A and C are committed together.

If the nested scope succeeds, the savepoint is released; data still awaits the outer transaction's commit. Therefore, **NESTED** cannot commit independently like **REQUIRES_NEW**.

This mechanism usually maps to JDBC savepoints. It only works when the transaction manager, resource, and JDBC driver support savepoints.

### Why NESTED is not equivalent to nested transactions in JPA

JPA does not define nested transactions. **EntityManager** manages the persistence context, including managed entities and in-memory state. Rolling back a JDBC savepoint does not automatically restore entity state in the persistence context to the point when the savepoint was created.

With **JpaTransactionManager**:

- **nestedTransactionAllowed** defaults to **false**.
- This option can be enabled to use savepoints for JDBC access sharing the same transaction, if the driver supports it.
- A savepoint only controls the JDBC connection; it does not provide full semantic partial rollback for changes managed by the JPA **EntityManager**.
- Do not assume entities modified inside a nested scope will automatically revert to their old state after rolling back a savepoint.

The last point is crucial: object state in the persistence context may become out of sync with database state after rolling back a savepoint. A subsequent flush can cause the application to write unintended state. Enabling **nestedTransactionAllowed** does not turn JPA into a system that supports nested transactions.

### Savepoint example for JDBC only

The following example illustrates the JDBC mechanism, not partial rollback of JPA operations. **BatchService** and **NestedJdbcWriter** must be two separate Spring beans. The transaction manager must support savepoints and both operations must use the same JDBC resource.

```java
@Service
public class NestedJdbcWriter {

    private final JdbcTemplate jdbcTemplate;

    public NestedJdbcWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void insertOptionalRow(String value) {
        jdbcTemplate.update(
                "insert into import_item(value) values (?)", value);
        throw new InvalidRowException("Invalid data");
    }
}

@Service
public class BatchService {

    private final JdbcTemplate jdbcTemplate;
    private final NestedJdbcWriter nestedJdbcWriter;

    public BatchService(
            JdbcTemplate jdbcTemplate,
            NestedJdbcWriter nestedJdbcWriter) {
        this.jdbcTemplate = jdbcTemplate;
        this.nestedJdbcWriter = nestedJdbcWriter;
    }

    @Transactional
    public void importBatch() {
        jdbcTemplate.update(
                "insert into import_log(message) values (?)", "Started");

        try {
            nestedJdbcWriter.insertOptionalRow("row-1");
        } catch (InvalidRowException ex) {
            // The inner JDBC work rolled back to the savepoint.
            // The outer transaction can still continue.
        }

        jdbcTemplate.update(
                "insert into import_log(message) values (?)", "Continued");
    }
}
```

This is illustrative code; tables, the **InvalidRowException** exception, datasource, and appropriate transaction manager configuration are required. With **DataSourceTransactionManager**, the driver must support JDBC savepoints. If using **JpaTransactionManager**, only enable nested for JDBC when you understand the persistence context limitations; do not extrapolate from this example that repository or **EntityManager** operations can also be safely rolled back partially.

### What should you do when using Spring Data JPA?

- Use **REQUIRED** if all entity changes in the use case must commit or roll back together.
- Use **REQUIRES_NEW** if a genuinely independent JPA transaction is needed, such as separate audit logging.
- If you only want to skip an invalid item in a batch, consider separating each item into an independent transaction using **REQUIRES_NEW**, or processing each item under its own transaction boundary. Clearly evaluate the impact of committing item by item.
- If partial rollback via savepoint is required, confine that part to JDBC and verify the transaction manager, datasource, and driver. Do not rely on JPA-managed entity state to achieve this behavior.
- If a committed business operation needs to be undone, design a compensating action or an appropriate saga workflow; a savepoint cannot reverse an independent committed transaction.

## 6. Choosing propagation based on business requirements

| Scenario | Typically appropriate choice | Reason |
|---|---|---|
| Saving an order and deducting inventory must succeed together | REQUIRED | Same physical transaction |
| Service calls multiple repositories in a single use case | REQUIRED | Keeps the transaction boundary at the service layer |
| Audit record must persist even when main operation rolls back | REQUIRES_NEW | Audit transaction commits independently |
| Writing secondary data that may fail without rolling back the outer transaction | REQUIRES_NEW or JDBC NESTED | Choose based on whether independent commit or savepoint rollback is needed |
| Wanting partial rollback of changes via JPA EntityManager | Do not rely on NESTED | JPA does not support nested transactions |
| Wanting atomic outbox writes alongside business data | REQUIRED | Both types of data must commit or roll back together |

Before choosing, answer three questions:

1. If the inner method fails, must the outer method's data roll back?
2. If the inner method succeeds, is it allowed to commit even if the outer method rolls back?
3. Does the partial rollback requirement apply to a JDBC savepoint or to JPA-managed entities?

If the answer to question 1 is "yes," usually choose **REQUIRED**. If the answer to question 2 is "yes," consider **REQUIRES_NEW**. If savepoint behavior is needed, verify that the work is JDBC and that the transaction manager supports it before using **NESTED**.

## 7. Spring Data JPA and transaction boundaries

Spring Data JPA provides default transaction configuration for CRUD methods inherited from **CrudRepository**/**JpaRepository** via **SimpleJpaRepository**:

- Read operations are typically configured with **readOnly = true**.
- Write operations use **@Transactional** with default settings.
- Custom query methods do not automatically receive transaction configuration; declare **@Transactional** if the method needs a transaction.

For business operations involving multiple repository calls, place the transaction boundary on the service. For example, a **placeOrder()** service can call order save, line-item save, and inventory deduction within the same **REQUIRED** transaction. When an outer transaction already exists, the outer transaction's attributes govern the actual transaction in which the repositories participate.

**readOnly = true** is a hint for the transaction manager/JDBC/JPA provider to optimize reads, not a mechanism guaranteeing all write statements are blocked. Some databases may reject writes in read-only transactions, but you should not rely on this attribute as a data authorization barrier.

## 8. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| **REQUIRES_NEW** annotation does not create a new transaction | Internal call within the same class, bypassing the proxy | Move the method to another bean and call through the injected bean |
| Catching exception still causes **UnexpectedRollbackException** | Inner **REQUIRED** scope marked the shared transaction rollback-only | Check exceptions passing through the interceptor and rollback rules; redesign transaction boundaries |
| Audit lost when order rolls back | Audit participated via **REQUIRED** in the outer transaction | Use **REQUIRES_NEW** if the audit must persist independently |
| Connection exhaustion when using **REQUIRES_NEW** | Outer transaction still holds a connection while inner transaction needs a new one | Evaluate pool size, concurrency, and number of nested transaction levels |
| **NESTED** does not work with JPA | Transaction manager does not support savepoints or nested is not enabled | Check transaction manager and driver; use nested only for JDBC when appropriate |
| Database rolled back but Java objects still hold modified values | Persistence context is not restored by a JDBC savepoint | Do not keep using that entity state as if it were rolled back; refresh/reload or design transactions differently |
| Query method has no transaction as expected | Custom query method has no default transaction | Place **@Transactional** on the appropriate service or repository |

Integration tests should verify database state after commit/rollback rather than merely verifying repository calls with mocks:

1. With **REQUIRED**, trigger an error in the inner scope, catch it in the outer scope, and verify the shared transaction does not commit; check for **UnexpectedRollbackException** at the commit boundary.
2. With **REQUIRES_NEW**, let the inner transaction commit the audit successfully and then force the outer transaction to roll back; verify the audit still exists.
3. With **NESTED**, test savepoints using JDBC on the actual transaction manager and driver; do not use JDBC results to conclude JPA entities are restored.
4. Ensure calls pass through the Spring proxy in propagation tests.

## 9. Key takeaways

- **REQUIRED**: joins the current transaction or creates a new one; suited for business operations requiring atomicity.
- **REQUIRES_NEW**: suspends the outer transaction and creates an independent physical transaction; commits/rolls back independently but consumes extra resources.
- **NESTED**: uses a savepoint within the same transaction; partial rollback is only meaningful when supported by the transaction manager and JDBC resource.
- **NESTED is not a JPA nested transaction**. **JpaTransactionManager** disables nested by default; even when enabled, savepoints only control the JDBC connection and do not revert the persistence context.
- **@Transactional** in proxy mode requires calls through the proxy; self-invocation does not trigger propagation as expected.

## 10. References

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — JpaTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)