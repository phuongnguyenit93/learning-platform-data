# Rollback Rules, Checked Exceptions, and rollbackFor

In Spring Data JPA, a method may have already written or modified entities, yet the transaction still commits when the method exits with a checked exception. The reason is Spring's default rule: a transaction rolls back when a `RuntimeException` or `Error` exits the transaction boundary; checked exceptions do not trigger rollback by default. When business logic requires discarding all changes on a checked exception, declare `rollbackFor` on `@Transactional`.

## 1. How does a transaction decide whether to commit or roll back?

When a call goes through Spring's transaction proxy, the transaction interceptor starts a new transaction or joins an existing one. The business method then runs inside that transaction.

- Method returns normally: Spring instructs the transaction manager to commit.
- Method exits with an exception: Spring matches the exception against the transaction's rollback rules.
- Rule requires rollback: the transaction is marked rollback-only or rolled back according to propagation state.
- Rule does not require rollback: Spring proceeds with the commit flow, even though the exception is still propagated to the caller.

Spring's default rule for `@Transactional` is:

| Exit type | Default behavior |
|---|---|
| Normal return | Commit |
| `RuntimeException` exits the method | Rollback |
| `Error` exits the method | Rollback |
| Checked exception exits the method | Commit |

The key point is that Spring evaluates the exception type exiting the transaction-managed method, not merely whether a `throw` statement appeared inside the function body. If an exception is caught and the method returns normally, the interceptor generally treats it as a successful completion.

## 2. Distinguishing checked exceptions and unchecked exceptions

Java divides exceptions into two main groups:

~~~text
Throwable
├── Error
└── Exception
    ├── RuntimeException (unchecked)
    └── Remaining Exception subclasses (checked)
~~~

**Unchecked exceptions** are `RuntimeException` and its subclasses. The compiler does not force callers to declare or catch this group of exceptions. Examples: `IllegalArgumentException`, `NullPointerException`, and many exceptions under Spring's `DataAccessException`.

**Checked exceptions** are subclasses of `Exception` that do not extend `RuntimeException`. The compiler requires methods to catch them or declare them with `throws`. Examples: `IOException` or a custom business exception directly extending `Exception`.

`Error` is a separate branch under `Throwable`, not a checked exception. Spring rolls back by default when an `Error` exits a transaction.

In Spring Data JPA applications, many data-access errors are translated into unchecked exceptions. However, application-defined business exceptions can be checked exceptions. Therefore, do not assume that every exception thrown inside a service automatically triggers a transaction rollback.

## 3. Why can a checked exception cause data to be committed?

Consider the following illustrative method. Suppose `OrderRepository` saves an order and `InventoryUnavailableException` is a checked exception.

~~~java
@Transactional
public void createOrder(Order order) throws InventoryUnavailableException {
    orderRepository.save(order);

    if (!inventoryService.hasEnoughStock(order)) {
        throw new InventoryUnavailableException("Insufficient stock");
    }
}
~~~

If `InventoryUnavailableException` extends `Exception` and there are no additional rollback rules, Spring does not roll back solely because of this exception by default. When the exception exits the method, the transaction can commit; the saved order may still exist even though the caller receives an error.

This is an important distinction between two things:

- The caller receives an exception: the calling flow knows the business operation failed.
- Transaction rollback: database changes belonging to the transaction are discarded.

These two are not synonymous. A method can throw an exception while the transaction still commits if the rollback rules do not match.

## 4. Using rollbackFor to roll back on checked exceptions

The `rollbackFor` attribute declares exception types that must roll back the transaction. Pass the exception class directly so the rule is strongly typed.

~~~java
public class InventoryUnavailableException extends Exception {
    public InventoryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    @Transactional(rollbackFor = InventoryUnavailableException.class)
    public void createOrder(Order order)
            throws InventoryUnavailableException {
        orderRepository.save(order);

        if (!inventoryService.hasEnoughStock(order)) {
            throw new InventoryUnavailableException("Insufficient stock");
        }
    }
}
~~~

When `InventoryUnavailableException` exits `createOrder`, the rollback rule matches and Spring rolls back the transaction. Database changes made in that transaction are discarded.

Multiple exception types can be declared:

~~~java
@Transactional(
    rollbackFor = {
        InventoryUnavailableException.class,
        IOException.class
    }
)
public void processOrder(Order order)
        throws InventoryUnavailableException, IOException {
    // Operations belonging to the same transaction
}
~~~

If you want any exception under the `Exception` hierarchy to trigger rollback, you can use:

~~~java
@Transactional(rollbackFor = Exception.class)
public void executeBusinessOperation() throws Exception {
    // Includes both checked exceptions and RuntimeException
}
~~~

`Exception.class` also includes `RuntimeException` because `RuntimeException` extends `Exception`. Default rollback behavior for `Error` still applies. Only use a broad rule when that is genuinely the business policy; otherwise, declaring the exact exceptions to handle is easier to read and produces fewer unintended side effects.

Besides `rollbackFor`, the annotation also offers `rollbackForClassName` to declare rules by exception class name. This uses string matching on class names and can accidentally match similarly named classes. Prefer `rollbackFor = SomeException.class` whenever possible.

## 5. Using noRollbackFor when you want to commit despite an exception

`noRollbackFor` declares exceptions that Spring should not use as a reason to roll back. For instance, business logic might treat a post-save warning as an acceptable outcome:

~~~java
@Transactional(noRollbackFor = DuplicateNoticeException.class)
public void registerCustomer(Customer customer)
        throws DuplicateNoticeException {
    customerRepository.save(customer);

    if (customer.hasDuplicateContact()) {
        throw new DuplicateNoticeException("Contact details already exist");
    }
}
~~~

If `DuplicateNoticeException` exits the method and no stronger rollback rule demands a rollback, the transaction can commit. The caller still receives the exception.

Only use `noRollbackFor` when preserving the changes is intentional business behavior. If written data must be discarded when the exception occurs, do not list that exception in `noRollbackFor`.

Spring can evaluate multiple rollback rules at once. The rule matching the actual exception most specifically determines the outcome. Therefore, when combining `rollbackFor` and `noRollbackFor`, verify the exception inheritance hierarchy to avoid conflicting or confusing configurations.

## 6. Conditions affecting rollback

### Exceptions must cross the transaction boundary

The example below catches the exception and does not rethrow it:

~~~java
@Transactional
public void createOrder(Order order) {
    try {
        orderRepository.save(order);
        inventoryService.reserve(order);
    } catch (InventoryUnavailableException ex) {
        log.warn("Could not reserve stock: {}", ex.getMessage());
    }
}
~~~

After the `catch` block, the method ends normally. The transaction interceptor never sees an exception exit, so the transaction may commit. Logging does not automatically mark a rollback.

If the business logic requires rollback while still handling the exception locally, you can mark the transaction rollback-only:

~~~java
@Transactional
public void createOrder(Order order) {
    try {
        orderRepository.save(order);
        inventoryService.reserve(order);
    } catch (InventoryUnavailableException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        log.warn("Order will roll back: {}", ex.getMessage());
    }
}
~~~

This approach requires an active transaction. Usually, letting an appropriate exception propagate out of the service boundary and configuring `rollbackFor` is easier to understand than catching and manually marking rollback-only.

### Calls must pass through the Spring proxy

In default proxy mode, `@Transactional` is applied when the call passes through a Spring proxy. A method in the same object directly calling another `@Transactional` method (self-invocation) does not pass through the proxy; the annotation on the called method may not take effect as expected.

For example, if `methodA()` directly calls `this.methodB()`, do not assume `methodB()`'s transaction rules will activate independently. Place transaction boundaries on service methods invoked from other beans or structure beans so calls pass through the proxy.

### Methods joining an existing transaction

With the default `REQUIRED` propagation, the called method typically joins the existing transaction. If an inner transactional call marks the shared transaction rollback-only, having the outer method catch the exception and continue does not return the transaction to a committable state. When the outer method finishes and attempts to commit, the caller may receive `UnexpectedRollbackException`.

This prevents callers from assuming a transaction committed when an inner part requested a rollback. When designing multiple services joining one transaction, understand which exceptions escape each proxy and which rollback rules apply.

## 7. Where to place transaction boundaries in Spring Data JPA?

Typically, place `@Transactional` on the service method representing a complete business operation. For example, creating an order may require saving the order, updating stock, and writing related line items. These database operations should be in the same transaction if the business logic requires all of them to succeed or roll back together.

~~~java
@Service
@RequiredArgsConstructor
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    @Transactional(rollbackFor = CheckoutException.class)
    public void checkout(Order order) throws CheckoutException {
        orderRepository.save(order);
        inventoryRepository.reserve(order.getItems());

        if (inventoryRepository.hasReservationFailure(order)) {
            throw new CheckoutException("Unable to reserve enough stock");
        }
    }
}
~~~

Spring Data JPA repositories have transaction configuration for inherited CRUD methods. Even so, a service transaction groups multiple repository calls into one business boundary and lets you declare rollback rules where the operation's full intent is understood.

Do not rely on individual repository transactions to replace a transaction for the entire use case. If each repository call runs in an independent transaction, one operation may already commit before the next operation fails.

## 8. Testing rollback behavior

Test using integration tests with a test database and invoke the service through the Spring context. The test should verify two things simultaneously: the caller receives the expected checked exception, and data written before the exception is no longer in the database.

~~~java
@SpringBootTest
class OrderServiceRollbackTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void rollsBackWhenCheckedExceptionIsThrown() {
        UUID orderId = UUID.randomUUID();
        Order order = new Order(orderId);

        assertThatThrownBy(() -> orderService.createOrder(order))
                .isInstanceOf(InventoryUnavailableException.class);

        assertThat(orderRepository.existsById(orderId)).isFalse();
    }
}
~~~

The example assumes an `Order(UUID)` constructor and that the service saved the entity before throwing `InventoryUnavailableException`. The test method must not be wrapped in a test transaction that hides read outcomes inside an outer transaction. Ensure test data is isolated and the database actually executes transactions.

Some testing notes:

- Call the injected service bean so calls pass through the proxy.
- Inspect the database after the service has completed and the transaction has rolled back.
- Use a unique ID per test to prevent stale data from skewing results.
- Do not assert only the exception; verify the data state.
- If checking SQL or constraints, remember JPA may defer statements until flush or commit.

## 9. Database rollback does not undo all side effects

A JPA transaction only manages resources participating in the transaction, usually the database. If a service sends an email, calls an HTTP API, writes a file, or publishes a message to an external system and then rolls back, those side effects are not automatically undone.

For example: an order is saved, a confirmation email is sent, and then a checked exception rolls back the transaction. The database no longer has the order, yet the email has already been sent. For workflows needing synchronization across such actions, consider a transactional outbox, post-commit event publishing, or an appropriate compensating workflow. Do not assume `rollbackFor` can undo calls to external systems.

## 10. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Checked exception not declared in `rollbackFor` | Transaction may commit even though caller receives exception | Declare the exact exception class |
| Catching exception and returning normally | Transaction may commit | Rethrow the exception or mark rollback-only |
| Using `noRollbackFor` for an exception that should discard data | Changes may be committed | Remove that rule or adjust policy |
| Calling transactional method via self-invocation | Proxy may not apply transaction rules | Place boundary on bean/service called through proxy |
| Checking only the exception in tests | Does not prove the database rolled back | Re-read data state after the call |
| Assuming rollback undoes emails or HTTP calls | External side effects still persist | Use outbox, after-commit, or compensating mechanisms |

## 11. Checklist when choosing rollback rules

Before finalizing a service method, ask yourself:

1. Which transaction is the method running in, and where is the transaction boundary?
2. Is the business exception checked or unchecked?
3. Does the exception exit the method managed by the Spring proxy?
4. If it is a checked exception, is `rollbackFor` declared with the right class?
5. Is there any `noRollbackFor` or other rule altering the outcome?
6. Is there any `catch` block swallowing the exception or letting the method finish normally?
7. Do the operations requiring rollback actually participate in the same transaction?
8. Do integration tests verify data is kept or discarded as the business logic requires?
9. Are there off-database side effects needing separate post-commit handling or compensation?

## Conclusion

Spring rolls back by default on `RuntimeException` and `Error`, whereas checked exceptions generally do not trigger rollback. Use `@Transactional(rollbackFor = YourCheckedException.class)` when business logic requires discarding database changes if that checked exception occurs. Also ensure the exception passes through the transaction proxy without being caught and swallowed, and test the database state after the transaction ends.