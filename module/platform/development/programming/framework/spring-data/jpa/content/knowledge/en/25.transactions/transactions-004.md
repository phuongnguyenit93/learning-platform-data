# Proxy Mechanism, Self-Invocation, and When Transactions Do Not Work in Spring Data JPA

## Objectives

After this lesson, you will be able to explain how Spring applies `@Transactional` via proxies, recognize the **self-invocation** issue when one method calls another method within the same bean, choose an appropriate way to structure transaction boundaries, and diagnose common causes of transactions not starting or not rolling back as expected.

The scope covers Spring applications using Spring Data JPA and imperative synchronous transactions with `PlatformTransactionManager`.

## 1. `@Transactional` is enforced through a proxy

`@Transactional` is primarily metadata describing a transaction policy. In the default proxy mode, Spring creates a proxy wrapping the Spring bean. When another bean calls a transactional method through the proxy, the transaction interceptor (`TransactionInterceptor`) reads the metadata, interacts with the transaction manager, and then invokes the actual method.

Typical flow:

1. Bean A calls a method on bean B through a Spring-injected reference.
2. The call enters B's proxy.
3. The proxy inspects the `@Transactional` configuration and asks the transaction manager to start a new transaction or join an existing one, depending on `propagation`.
4. The proxy invokes the method on the target object.
5. When the method completes, the proxy commits or rolls back based on the execution outcome and rollback rules.

Spring may use a JDK dynamic proxy or a class-based proxy (CGLIB). The proxy type details do not change the core principle: **the call must go through the proxy for transaction advice to be applied**.

Example of a typical transaction boundary:

```java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

When a controller or another service calls `orderService.createOrder(order)` via the injected bean, the call goes through the proxy and a transaction is opened before the method body executes.

If you directly call an object created with `new OrderService(...)`, that object is not managed by Spring and has no Spring-generated transaction proxy. Annotations on that object do not automatically start a transaction.

## 2. Self-invocation: internal calls bypass the proxy

Self-invocation occurs when a method in a bean calls another method of the same bean, such as `this.saveOne()` or directly calling `saveOne()`.

Example:

```java
@Service
public class ImportService {
    private final ImportRepository repository;

    public ImportService(ImportRepository repository) {
        this.repository = repository;
    }

    public void importAll(List<ImportRow> rows) {
        for (ImportRow row : rows) {
            saveOne(row); // Internal call on the same object
        }
    }

    @Transactional
    public void saveOne(ImportRow row) {
        repository.save(row);
    }
}
```

When an external bean calls `importAll()`, the proxy can receive that call. However, inside the body of `importAll()`, `saveOne(row)` invokes the method directly on the target object. This call does not go back through the proxy, so the annotation on `saveOne()` is not processed for that internal call.

The consequence depends on whether an outer transaction exists:

- **No outer transaction:** `saveOne()` does not open its own transaction despite having `@Transactional`. If it calls Spring Data repository CRUD methods, each repository call may still use its own transaction according to the repository's default configuration. Therefore, the entire loop does not automatically become a single atomic transaction.
- **With an outer transaction:** `saveOne()` runs within the existing transaction context if present. However, attributes declared specifically on `saveOne()` are ignored. For example, `propagation = REQUIRES_NEW` does not create a new transaction, and separate `readOnly` and `timeout` settings are not applied.

A second example illustrating a common mistake:

```java
@Service
public class OrderService {
    @Transactional
    public void placeOrder(Order order) {
        saveAudit(order); // Does not go through the proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // The author expects an independent transaction
    }
}
```

`placeOrder()` is called from another bean, so the outer transaction starts. However, `saveAudit()` is invoked internally, so `REQUIRES_NEW` has no effect. The audit write remains inside `placeOrder()`'s transaction. If the outer transaction rolls back, the audit write rolls back as well.

Note: if `placeOrder()` does not have `@Transactional`, an internal call to `saveAudit()` does not create a transaction either. Do not conclude that merely seeing an annotation on a method means that method is definitely running inside a transaction.

## 3. How to fix self-invocation

### 3.1. Extract the transaction boundary into another bean

This is usually the easiest approach to understand and test. A coordinator bean calls another business bean via a Spring-injected dependency, so the call goes through the target bean's proxy.

```java
@Service
public class ImportCoordinator {
    private final ImportItemService itemService;

    public ImportCoordinator(ImportItemService itemService) {
        this.itemService = itemService;
    }

    public void importAll(List<ImportRow> rows) {
        for (ImportRow row : rows) {
            itemService.saveOne(row); // Called through another bean's proxy
        }
    }
}

@Service
public class ImportItemService {
    private final ImportRepository repository;

    public ImportItemService(ImportRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOne(ImportRow row) {
        repository.save(row);
    }
}
```

In this example, each call to `saveOne()` can open a new transaction. If you want the entire batch to succeed or fail together, place `@Transactional` on the coordinator method and use an appropriate propagation, typically `REQUIRED` on the called methods. Choose the policy based on data consistency requirements, since `REQUIRES_NEW` intentionally separates commit/rollback for each item.

### 3.2. Call via a self-reference or current proxy

You can inject a reference to the bean itself, or use `AopContext.currentProxy()` when `exposeProxy` is enabled. This makes the bean depend directly on the AOP mechanism, making it harder to understand and test. Only consider this when responsibilities cannot be split into another bean and you clearly understand how Spring resolves self-references.

### 3.3. Use AspectJ weaving when genuinely needed

AspectJ weaving mode can apply advice even to self-invocation because it modifies bytecode rather than relying solely on proxies. This requires appropriate weaving configuration and build/runtime setup, which is more complex than standard proxy mode. Most Spring Data JPA applications do not need to switch to AspectJ just to fix an internal call.

## 4. Common situations where transactions do not work

| Cause | Symptom | How to check or handle |
|---|---|---|
| Self-invocation | Internal method has `@Transactional` but does not open a transaction or apply its own propagation | Extract to another bean and call through an injected dependency |
| Object not managed by Spring | Annotation has no effect on objects instantiated with `new` | Register the bean via component scanning or bean configuration, then inject it |
| Transaction management not enabled or missing manager | No transaction advice or no suitable transaction manager | With Spring Boot and Data JPA starter, check auto-configuration; manual configuration requires enabling transaction management and declaring `PlatformTransactionManager` |
| Method cannot be intercepted by proxy | Call does not go through an overridable proxy method or method is not on the proxied interface | Prefer public methods; check proxy type, `final` class/method, `private` methods, and proxied interfaces |
| Wrong transaction manager selected | Some operations run under a different manager than expected | Check transaction manager beans and specify the qualifier in `@Transactional("...")` when multiple managers exist |
| Propagation does not create a transaction | Method runs without an active transaction | Check `SUPPORTS`, `NOT_SUPPORTED`, `NEVER`, and the caller's context |
| Exception does not trigger rollback | Data still commits despite an exception | Check exception type, `rollbackFor`, exception catching, and rollback-only status |
| Switching to another thread | Calling thread's transaction is not present on the new thread | Open a transaction inside a bean running on the target thread; do not rely on imperative transaction propagation across `@Async` or `new Thread` |
| Read-only operations or not flushed yet | SQL or constraint errors do not appear at the expected time | Understand JPA flush mechanics; use `flush()` when early SQL execution is needed to detect errors |

### 4.1. Proxy limitations and visibility

With JDK dynamic proxies, calls must go through methods declared on the proxied interface. With class-based proxies, proxies rely on inheritance; `final` methods cannot be overridden to add advice, and `private` methods cannot be intercepted by standard proxying.

Spring Framework 6 supports `protected` and package-visible methods for class-based proxies under the corresponding default transaction annotation configuration; with interface-based proxies, transactional methods must be public and on the interface. To avoid differences across proxy types and configurations, place transaction boundaries on public methods of service beans.

### 4.2. Exceptions and rollback rules

By default, Spring rolls back when a transactional method throws a `RuntimeException` or `Error`. Checked exceptions do not automatically trigger a rollback under default rules.

```java
@Transactional(rollbackFor = Exception.class)
public void importFile() throws Exception {
    repository.save(...);
    validateFile(); // Checked exception also requires rollback
}
```

If the business logic needs rollback on a checked exception, declare `rollbackFor` accordingly. `noRollbackFor` can be used when an exception should still allow commit, but consider carefully because data may be saved even though the method reports an error.

If a method catches an exception and returns normally, the transaction interceptor sees a successful execution and may commit. If you catch an error but still need a rollback, rethrow the exception or explicitly mark the transaction rollback-only using the appropriate API. Do not swallow exceptions and expect Spring to know a rollback is needed.

### 4.3. Transactions do not automatically propagate across threads

Spring's imperative transactions are usually bound to the current thread. When a method with an active transaction calls `@Async`, creates a `new Thread`, or submits work to an executor, the new thread does not automatically inherit the caller's transaction.

If background work needs a transaction, ensure the method invoked on the background thread belongs to a Spring bean and place the `@Transactional` boundary there. In reactive applications, transactions are managed via the Reactor context and require a reactive transaction manager; do not apply imperative JPA thread-local assumptions to reactive flows.

## 5. Understanding propagation to read behavior accurately

`Propagation` determines how a method behaves when a transaction already exists or does not exist. The default value for `@Transactional` is `REQUIRED`.

| Propagation | When a transaction exists | When no transaction exists |
|---|---|---|
| `REQUIRED` | Joins the existing transaction | Starts a new transaction |
| `REQUIRES_NEW` | Suspends the existing transaction and starts a new one | Starts a new transaction |
| `SUPPORTS` | Joins the existing transaction | Executes without a transaction |
| `NOT_SUPPORTED` | Suspends the existing transaction | Executes without a transaction |
| `MANDATORY` | Joins the existing transaction | Throws an error because no transaction exists |
| `NEVER` | Throws an error if a transaction exists | Executes without a transaction |
| `NESTED` | May use a savepoint if supported by the transaction manager | Starts a new transaction |

Some notes when applying this with JPA:

- `REQUIRES_NEW` may require another connection while the outer transaction is suspended. If repeated many times with a small connection pool, consider the risk of connection exhaustion.
- `NESTED` depends on the transaction manager and underlying savepoint support; do not assume every `JpaTransactionManager` configuration provides nested transactions the way you expect.
- Propagation is only applied when the call passes through a proxy. If `REQUIRES_NEW` is on a self-invoked method, that configuration is not executed.
- `readOnly = true` is a hint/optimization for the transaction manager and persistence provider, not an authorization mechanism guaranteeing all writes are blocked.

## 6. Transaction boundaries with Spring Data JPA repositories

Inherited CRUD methods from `CrudRepository`/`JpaRepository` have Spring Data JPA's default transaction configuration: write operations generally have `@Transactional`, while read operations generally use `readOnly = true`. However, custom query methods declared by the application do not automatically have their own transaction configuration by default.

For business operations comprising multiple repository calls, place the transaction boundary on the service:

```java
@Service
public class TransferService {
    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(Long fromId, Long toId, BigDecimal amount) {
        Account from = accountRepository.findById(fromId).orElseThrow();
        Account to = accountRepository.findById(toId).orElseThrow();

        from.withdraw(amount);
        to.deposit(amount);

        accountRepository.save(from);
        accountRepository.save(to);
    }
}
```

When the service is called through the proxy, read and write operations share the service's transaction. If updating the second account fails and the exception triggers a rollback, the change to the first account also rolls back within the same transaction.

Do not mistake a `repository.save()` call succeeding for the entire use case being protected by a single transaction. Without a service transaction, multiple repository calls can commit independently.

## 7. How to inspect transactions while debugging

You can use `TransactionSynchronizationManager` to observe transaction status at runtime:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

System.out.println("transactionActive=" + active);
System.out.println("transactionReadOnly=" + readOnly);
```

Place the check at the beginning of the method being diagnosed and compare calling from another bean versus calling internally. A `false` result at the start of the method is a useful sign that no actual transaction is active at that point; it does not by itself pinpoint the cause.

Diagnostic workflow:

1. Confirm the service is a Spring bean and the caller uses the injected bean.
2. Confirm the call passes through the proxy, not self-invocation.
3. Confirm transaction management and the appropriate transaction manager are configured.
4. Check the proxy type, visibility, and method modifiers.
5. Check propagation, especially `SUPPORTS`, `NOT_SUPPORTED`, `NEVER`, and `REQUIRES_NEW` calls.
6. Check whether exceptions escape the method or are caught; cross-check with `rollbackFor`/`noRollbackFor`.
7. Check whether the operation runs on a different thread.
8. If SQL or constraint errors appear late, check JPA flush and commit timing.

You can enable DEBUG logging for Spring's transaction infrastructure when you need to see when transactions are opened, joined, committed, or rolled back. When debugging, avoid relying solely on seeing the annotation in source code; inspect transaction status at the actual execution point.

## 8. Pre-production checklist

- [ ] Service is Spring-managed and injected from the container.
- [ ] Callers invoke transactional methods through the proxy.
- [ ] Do not rely on self-invocation to trigger `@Transactional`.
- [ ] Transaction boundaries accurately enclose the entire business operation that must be atomic.
- [ ] Propagation matches commit/rollback requirements.
- [ ] Checked exceptions have `rollbackFor` if business logic requires rollback.
- [ ] Do not swallow exceptions when rollback is needed.
- [ ] Do not assume imperative transactions automatically propagate to background threads.
- [ ] Custom query methods have transactions when needed.
- [ ] Verified commit/rollback results and data state with integration tests.

## Conclusion

In Spring Data JPA, `@Transactional` works via transaction advice attached to a Spring bean's proxy. Calls from other beans can pass through the proxy, whereas internal calls within the same object bypass the proxy and do not apply the called method's transaction configuration. When transactions do not behave as expected, systematically check beans/proxies, self-invocation, transaction manager configuration, propagation, rollback rules, and execution threads. Placing transaction boundaries on service beans and extracting operations needing distinct policies into separate beans generally makes behavior clearer, easier to test, and easier to maintain.