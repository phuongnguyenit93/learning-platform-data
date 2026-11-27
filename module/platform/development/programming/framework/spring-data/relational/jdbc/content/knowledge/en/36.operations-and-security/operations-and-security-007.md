# Retrying Transient Errors with Safe Operations and Clear Transaction Boundaries

In a Spring Data JDBC application, write operations can fail for short-lived reasons: the database is busy, a transaction hits a deadlock, a lock cannot be acquired, a connection drops briefly, or a resource is temporarily unavailable. When the underlying cause is likely to clear on its own, the application can retry the operation after a short wait.

Retrying does not mean re-running every error. Validation errors, malformed SQL, unique constraint violations, or rejected business rules will not disappear on their own when re-run. Retrying unconditionally only increases load and can duplicate side effects.

A safe retry mechanism needs three elements:

1. Retry only errors that are genuinely transient.
2. The operation must be safe to re-run without producing duplicate or corrupted results.
3. Each retry attempt must have a clear transaction boundary so a failed attempt rolls back before the next attempt starts.

This lesson covers classifying errors, designing idempotent operations, configuring retries in Spring Framework 7, using Spring Retry for older versions, combining retries with transactions, handling uncertain commit outcomes, and testing retry behavior.

## 1. Which Errors Does Retry Solve?

Retry fits errors likely to disappear if you wait and try again. In Spring Data JDBC applications, common scenarios include:

- The database temporarily refuses connections.
- The connection pool has no connection available for a brief window.
- A transaction is rolled back by the database due to a deadlock.
- A lock cannot be acquired because another transaction holds it.
- The database rejects a transaction due to a concurrency conflict that can be resolved by re-reading data and re-running business logic.
- An external service is temporarily unresponsive or returns an overload error.

Spring JDBC translates JDBC errors into the exception hierarchy in package `org.springframework.dao`. Certain exceptions belong to `TransientDataAccessException`, indicating data access failures that may succeed if retried after conditions change.

Examples of error groups you may encounter:

| Situation | Common exception | How to handle |
|---|---|---|
| Cannot acquire lock | `CannotAcquireLockException` | Can retry the whole transaction |
| Deadlock | `PessimisticLockingFailureException` or a matching subclass | Can retry after rollback |
| Database resource temporarily unavailable | `TransientDataAccessResourceException` | Can retry with limits |
| Timeout during data access | `QueryTimeoutException` | Retry only if transient and sufficient time remains |
| Optimistic lock conflict | `OptimisticLockingFailureException` | Must re-read and recompute business logic before retrying |
| Unique/FK/CHECK violation | `DataIntegrityViolationException` | Usually do not retry |
| Invalid SQL syntax | `BadSqlGrammarException` | Do not retry |
| Insufficient permissions | Database permission error | Do not retry |

Exact classification also depends on the JDBC driver, database, and exception translator. Rely on Spring's translated exception type and root cause, not solely on text error messages.

### 1.1. Transient Errors vs. Permanent Errors

Compare two cases:

- The database aborts a transaction due to a deadlock: another transaction happened to hold conflicting locks. After rolling back and waiting, the next attempt can succeed.
- The database rejects an insert because an order code already exists: without changing inputs or business rules, re-running still violates the unique constraint.

Retry helps only in the first case.

A practical rule of thumb is: **if you re-run the same operation with the same state and same inputs, is the error likely to go away?** If the answer is no, do not retry automatically.

### 1.2. Do Not Retry Every DataAccessException

`DataAccessException` is Spring DAO's broad root exception class. It covers both transient errors and errors that cannot resolve on their own.

For example:

- `TransientDataAccessException` represents the transient error group.
- `DataIntegrityViolationException` indicates data violating a constraint.
- `BadSqlGrammarException` indicates invalid SQL.
- `PermissionDeniedDataAccessException` indicates missing permissions.

Never configure retries for all of `DataAccessException` without a classification policy. In Spring Framework 7, `@Retryable` retries all exceptions by default; therefore you must explicitly specify which exception group is allowed to retry.

## 2. Before Retrying, Verify Whether the Operation Is Safe

An idempotent operation is one that can be executed multiple times with the same identifier/request while yielding the same final outcome as executing it once.

Example setting an order's status to PAID:

```sql
UPDATE purchase_orders
SET status = 'PAID'
WHERE id = :orderId;
```

If this statement runs again, the status remains PAID. This is generally easier to make idempotent.

By contrast, this statement:

```sql
UPDATE customer_wallets
SET balance = balance - :amount
WHERE customer_id = :customerId;
```

deducts money again on every run. If the first attempt committed but the application lost the connection before receiving the response, a retry could deduct money a second time.

### 2.1. Comparing Operations

| Operation | Safe to retry? | Reason |
|---|---|---|
| Setting status to a deterministic value | Usually yes | Repeating produces the same state |
| Creating a record with a unique idempotency key | Potentially yes | The database can recognize an already-processed request |
| Incrementing a counter by 1 | Not automatically | Each attempt increments again |
| Deducting an account balance | Not automatically | May apply multiple times |
| Appending a new audit row | Not automatically | May create duplicate rows |
| Sending an email | Not automatically | Recipient may receive multiple emails |
| Calling a payment API | Not automatically | Provider may have processed the previous call |
| Reading data | Usually safe | Causes no side effects, though results may change over time |

Do not conclude an operation is safe merely because it uses HTTP GET, SQL UPDATE, or repository save. Examine actual side effects and the case where the previous call's result never reached the caller.

## 3. Idempotency Keys Protect Write Operations

For business flows that may be retried, assign a unique identifier to the business request. For example, each order creation request carries a `requestId` or `idempotencyKey`.

Schema:

```sql
CREATE TABLE processed_commands (
    command_id VARCHAR(80) PRIMARY KEY,
    result_reference BIGINT NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

When processing a command:

1. Check whether the command ID has already been recorded.
2. If it already exists, return the stored result.
3. If not, apply the business changes.
4. Record the command ID and result within the same transaction.
5. Commit both the business data and the idempotency record.

Service skeleton example:

```java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    return processedCommandRepository
        .findResultReference(command.commandId())
        .orElseGet(() -> {
            PurchaseOrder order = orderRepository.save(
                PurchaseOrder.from(command)
            );

            processedCommandRepository.save(
                new ProcessedCommand(
                    command.commandId(),
                    order.getId(),
                    Instant.now()
                )
            );

            return order.getId();
        });
}
```

This example assumes `processed_commands` has a primary key/unique constraint on `command_id`. Under concurrency, checking first with SELECT alone is insufficient: two requests could both observe the command missing. A unique constraint is still essential, and the application must handle conflicts when inserting the command ID.

If creating the order and writing the idempotency record occur inside the same transaction, a rollback reverts both. If the transaction committed yet the response was lost, a subsequent call can look up the command ID and return the prior result.

### 3.1. Idempotency Keys Must Remain Stable Across Retries

Never generate a new UUID on each retry attempt. The key must represent the exact same business request and stay unchanged across every attempt.

Example:

```java
public record CreateOrderCommand(
    String commandId,
    Long customerId,
    List<OrderLineRequest> lines
) {}
```

If each attempt generates a new command ID, the database cannot tell it is the same request and may create multiple orders.

### 3.2. Unique Constraints Are the Final Safeguard

Checking existence before inserting does not guarantee safety under concurrent requests:

```java
if (!repository.existsByCommandId(commandId)) {
    repository.save(command);
}
```

Two threads can pass the check simultaneously. The database needs a unique constraint on the command ID to enforce uniqueness. The service can handle a duplicate-key conflict by reloading the result already written by the winning request.

## 4. Retry the Entire Transaction, Not One Statement Inside a Broken Transaction

When a SQL statement fails due to a deadlock or serialization conflict, the database may have already rolled back the transaction or marked it unable to continue.

If the application catches the exception and keeps running inside the same transaction, subsequent statements may continue failing. Specifically, some databases put the transaction into an aborted error state after any failed SQL statement.

Proper flow:

```text
Attempt 1
  Start transaction A
  Load aggregate
  Apply changes
  Database reports deadlock
  Roll back transaction A

Wait per backoff

Attempt 2
  Start transaction B
  Reload aggregate
  Re-run business logic
  Commit transaction B
```

Every attempt must begin with a clean transaction. If the first attempt read data and failed, the next attempt should re-read data and re-evaluate business rules against the fresh state.

### 4.1. Do Not Retry Only repository.save()

Suppose a business operation must:

1. Read inventory.
2. Check sufficient stock.
3. Decrement inventory.
4. Create a reservation.
5. Write an audit record.

If you retry only the final save step, earlier reads and calculations may rely on stale data. Retry the entire relevant use-case transaction so the fresh attempt re-reads database state.

### 4.2. Transactions Must Roll Back Before Retrying

An exception must escape the transactional method so the transaction interceptor can apply rollback. If code catches the exception and returns normally, the transaction may commit or fail to be marked rollback-only as intended.

Example to avoid:

```java
@Transactional
public void reserveStock(Long productId, int quantity) {
    try {
        repository.reserve(productId, quantity);
    } catch (TransientDataAccessException exception) {
        log.warn("Temporary failure", exception);
        // Returning normally may keep the transaction from rolling back.
    }
}
```

Allow the exception to propagate out of the transaction boundary or mark rollback-only per an explicit policy. The retry interceptor needs to receive the exception to decide whether to retry.

### 4.3. Checked Exceptions and Rollback

By default, Spring rolls back on `RuntimeException` and `Error`. Checked exceptions do not trigger rollback by default.

If an operation can throw a checked exception that is a retry condition, configure `rollbackFor` appropriately:

```java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    // Persistence operations.
}
```

Most Spring-translated data access exceptions are unchecked. Still, verify rollback rules for all actual exceptions thrown in your application.

## 5. Retries in Spring Framework 7

Starting with **Spring Framework 7.0**, the core framework includes resilience features such as `@Retryable`, `@ConcurrencyLimit`, and `RetryTemplate`.

In applications using Spring Framework 7, enable annotation processing with `@EnableResilientMethods`:

```java
@Configuration
@EnableResilientMethods
public class ResilienceConfiguration {
}
```

Imports:

```java
import org.springframework.resilience.annotation.EnableResilientMethods;
import org.springframework.resilience.annotation.Retryable;
```

### 5.1. Specifying Retryable Exceptions

Example service updating order status:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Retryable(
        includes = TransientDataAccessException.class,
        excludes = OptimisticLockingFailureException.class,
        maxRetries = 3,
        delay = 100,
        multiplier = 2,
        jitter = 25,
        maxDelay = 1000
    )
    @Transactional
    public void markPaid(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        order.markPaid();
        repository.save(order);
    }
}
```

In this example:

- `includes` restricts retries to transient exceptions.
- `excludes` excludes optimistic locking failures from automatic retry.
- `maxRetries = 3` allows up to three retries after the initial execution, meaning up to four total invocations.
- `delay = 100` sets the initial wait to 100 ms.
- `multiplier = 2` increases wait time exponentially.
- `jitter = 25` adds randomness to the wait duration.
- `maxDelay = 1000` caps wait time at 1,000 ms.

This example assumes marking an order paid can safely be re-executed and makes no external payment provider calls inside the transaction. If there are external side effects, use idempotency keys or an outbox as described later.

### 5.2. Do Not Keep Default Settings in Production

Spring Framework 7's `@Retryable` can retry every exception by default. The default configuration also allows three retries after the initial call with a one-second delay.

Retrying every exception is far too broad for most database operations. A unique constraint, validation error, or invalid SQL statement will not be fixed by re-running the same request.

Explicitly specify `includes` and `excludes` to express the use case's retry policy.

### 5.3. Understanding maxRetries

In Spring Framework 7:

```text
Total invocations = 1 initial call + maxRetries
```

Example:

| maxRetries | Maximum total invocations |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 2 | 3 |
| 3 | 4 |
| 4 | 5 |

Do not confuse `maxRetries` with Spring Retry's `maxAttempts`. The two frameworks use different names and counting conventions.

### 5.4. Retry and Transaction Advice Ordering

Spring Framework 7 defines default advice ordering:

```text
Retry (OUTER)
    |
Transaction (INNER)
    |
Method
```

When a method has both `@Retryable` and `@Transactional`:

1. The retry interceptor calls the transaction interceptor.
2. The transaction interceptor opens a transaction for the attempt.
3. The method executes business logic.
4. If the method throws an exception, the transaction rolls back.
5. The retry interceptor catches the exception after rollback and decides whether to retry.
6. The next attempt goes through the transaction interceptor and opens a fresh transaction.

This is the desired order for transient errors such as deadlocks.

However, if the caller already has an active outer transaction, a method with `REQUIRED` propagation will join that outer transaction. When a use case requires a fresh transaction per attempt, place the retry boundary where no outer transaction is active or separate the retry coordinator from the transactional worker.

### 5.5. Proxies and Self-Invocation

`@Retryable` and `@Transactional` rely on Spring proxies in standard configurations. Only calls passing through the proxy are intercepted.

Self-invocation example:

```java
public void process() {
    retryableOperation(); // Internal call within the same object.
}

@Retryable
@Transactional
public void retryableOperation() {
    // ...
}
```

Internal calls bypass the proxy, so annotations do not take effect as expected.

Call the method from another Spring bean or split retry and transaction logic into beans with distinct responsibilities.

## 6. Separating the Retry Coordinator and Transactional Worker

For critical use cases, separating these two responsibilities into two beans makes transaction boundaries much clearer.

Retry coordinator:

```java
@Service
public class OrderRetryFacade {

    private final OrderTransactionalWorker worker;

    public OrderRetryFacade(OrderTransactionalWorker worker) {
        this.worker = worker;
    }

    @Retryable(
        includes = TransientDataAccessException.class,
        excludes = OptimisticLockingFailureException.class,
        maxRetries = 3,
        delay = 100,
        multiplier = 2,
        jitter = 25,
        maxDelay = 1000
    )
    public ReservationResult reserve(ReserveCommand command) {
        return worker.reserve(command);
    }
}
```

Transactional worker:

```java
@Service
public class OrderTransactionalWorker {

    private final InventoryRepository inventoryRepository;
    private final ReservationRepository reservationRepository;

    public OrderTransactionalWorker(
            InventoryRepository inventoryRepository,
            ReservationRepository reservationRepository) {
        this.inventoryRepository = inventoryRepository;
        this.reservationRepository = reservationRepository;
    }

    @Transactional
    public ReservationResult reserve(ReserveCommand command) {
        Inventory inventory = inventoryRepository
            .findByProductId(command.productId())
            .orElseThrow();

        inventory.reserve(command.quantity());

        inventoryRepository.save(inventory);

        Reservation reservation =
            Reservation.from(command);

        reservationRepository.save(reservation);

        return ReservationResult.from(reservation);
    }
}
```

The coordinator calls the worker through a separate bean, so calls pass through the transaction proxy. When no outer transaction exists, each coordinator retry calls the worker and opens a brand-new transaction.

If the coordinator might be called from an active outer transaction, decide deliberately whether to suspend that transaction during retries. You can use an orchestration boundary with `NOT_SUPPORTED` propagation so the worker does not join the caller's transaction, though note the outer transaction remains suspended throughout the retry cycle.

Do not blindly add `REQUIRES_NEW`. It lets the worker transaction commit independently of the outer transaction, potentially leaving partial business changes persisted even if the caller's transaction rolls back.

## 7. RetryTemplate for Programmatic Control

Spring Framework 7 provides `org.springframework.core.retry.RetryTemplate` when you need to build retry policies in Java code.

Example configuration:

```java
@Bean
RetryTemplate orderRetryTemplate() {
    RetryPolicy policy = RetryPolicy.builder()
        .includes(TransientDataAccessException.class)
        .excludes(OptimisticLockingFailureException.class)
        .maxRetries(3)
        .delay(Duration.ofMillis(100))
        .jitter(Duration.ofMillis(25))
        .multiplier(2)
        .maxDelay(Duration.ofSeconds(1))
        .build();

    return new RetryTemplate(policy);
}
```

Using the template outside the transactional worker:

```java
@Service
public class OrderRetryCoordinator {

    private final RetryTemplate retryTemplate;
    private final OrderTransactionalWorker worker;

    public OrderRetryCoordinator(
            RetryTemplate retryTemplate,
            OrderTransactionalWorker worker) {
        this.retryTemplate = retryTemplate;
        this.worker = worker;
    }

    public ReservationResult reserve(ReserveCommand command) {
        return retryTemplate.invoke(
            () -> worker.reserve(command)
        );
    }
}
```

In this example, the coordinator does not open a transaction. Each `invoke` call invokes the worker, passes through its transaction proxy, and runs in its own transaction.

`RetryTemplate` is useful when:

- Retry policies vary per use case.
- You need to wrap a code block rather than a method annotation.
- You want to combine retries with custom result handling or logging.
- You want to test the retry policy independently of method proxies.

Do not wrap `retryTemplate.invoke` in a transaction if your goal is giving each worker call its own transaction. If an outer transaction exists, a worker with REQUIRED propagation may join it.

## 8. Spring Retry for Projects Not Yet on Spring Framework 7

For projects on Spring Framework 6.x or older release trains, you can use the Spring Retry library if dependency versions are compatible with your stack.

Spring Retry uses its own annotation package:

```java
import org.springframework.retry.annotation.EnableRetry;
import org.springframework.retry.annotation.Retryable;
import org.springframework.retry.annotation.Backoff;
```

Enable annotation processing:

```java
@Configuration
@EnableRetry
public class RetryConfiguration {
}
```

Example:

```java
@Service
public class LegacyOrderService {

    @Retryable(
        retryFor = TransientDataAccessException.class,
        noRetryFor = OptimisticLockingFailureException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 100,
            multiplier = 2,
            maxDelay = 1000
        )
    )
    @Transactional
    public void markPaid(Long orderId) {
        // Reload aggregate, validate rules, and save.
    }
}
```

In Spring Retry:

- `maxAttempts = 4` includes the initial call, meaning four total invocations maximum.
- `retryFor` specifies retryable exceptions.
- `noRetryFor` excludes exceptions from retry.
- `@Backoff` configures wait intervals.

Do not confuse `org.springframework.retry.annotation.Retryable` with Spring Framework 7's `org.springframework.resilience.annotation.Retryable`. Both share the annotation name, but their APIs and attempt-counting rules differ.

When combining Spring Retry with transactions, verify advice ordering for your actual version and configuration. To avoid relying on annotation order, use a retry template on the outside calling a transactional bean through its proxy.

## 9. Optimistic Locking Requires Different Handling than Deadlock Retries

Spring Data JDBC supports optimistic locking via `@Version`. If two transactions read an aggregate at version 5, the first updates it to version 6. When the second saves with version 5, it is rejected.

This failure is normally surfaced as `OptimisticLockingFailureException`.

Do not simply re-save the same stale object multiple times. Its version remains outdated, so subsequent attempts will keep failing.

Reasonable approach:

1. Catch the conflict at the use-case layer if business rules permit retrying.
2. Reload the latest aggregate.
3. Re-evaluate business conditions against the fresh state.
4. Recompute the changes.
5. Attempt saving with the new version in a new transaction.

Illustrative example:

```java
@Transactional
public void reserve(Long productId, int quantity) {
    Inventory inventory = inventoryRepository
        .findByProductId(productId)
        .orElseThrow();

    if (inventory.availableQuantity() < quantity) {
        throw new InsufficientInventoryException(productId);
    }

    inventory.reserve(quantity);
    inventoryRepository.save(inventory);
}
```

If saving triggers an optimistic locking conflict, retrying must re-invoke the entire method to load fresh inventory and re-check available quantity. Never re-pass the stale object carrying the outdated version.

You can retry a use case on optimistic conflict if reloading and re-evaluating business logic is valid. However, do not treat every optimistic locking failure as a transient error solvable by repeating the same statement.

## 10. External Side Effects and the Transactional Outbox

A JDBC transaction cannot automatically roll back emails, HTTP requests, message broker publications, or payment transactions already completed in another system.

Unsafe example:

```java
@Transactional
@Retryable
public void payOrder(Long orderId) {
    paymentGateway.charge(orderId);
    orderRepository.markPaid(orderId);
}
```

If the payment gateway charges the card and the subsequent database step hits a deadlock, the database transaction rolls back. Retrying can invoke the payment gateway again and double-charge the customer.

### 10.1. Using Idempotency Keys with External Providers

If a payment provider supports idempotency keys, pass the exact same key on every attempt for that payment request:

```java
paymentGateway.charge(
    command.paymentRequestId(),
    command.amount()
);
```

The provider must guarantee that repeating the key does not create a second transaction. The application still needs to persist and reconcile outcomes in case responses are lost.

### 10.2. Using a Transactional Outbox

For events that must be sent after business data commits:

1. Update the aggregate inside the transaction.
2. Write an outbox event inside the same transaction.
3. Commit both the aggregate and the outbox row.
4. A worker reads the outbox and dispatches the message.
5. If publishing fails transiently, the worker retries publishing.
6. Consumers process idempotently because messages may be delivered more than once.

Example:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

An outbox records the database change and the intent to emit an event atomically in one transaction. It does not by itself guarantee exactly-once broker delivery; the worker may re-send after a crash, so consumers still need idempotency.

### 10.3. Do Not Hold Transactions Open While Waiting on External Services

Calling HTTP endpoints, email servers, or payment providers inside a long database transaction holds connections and locks throughout network waits.

Keep transactions scoped to database operations needing atomicity, then handle external side effects via an outbox or an appropriately idempotent workflow.

## 11. Backoff, Jitter, and Retry Limits

Retrying immediately without waiting can prevent an overloaded database or service from recovering.

Three commonly used mechanisms:

- **Backoff:** increases wait time between attempts.
- **Jitter:** adds randomness so clients do not all retry at the exact same instant.
- **Maximum delay:** caps the longest wait duration.

Example exponential backoff:

```text
Retry 1: around 100 ms
Retry 2: around 200 ms
Retry 3: around 400 ms
Retry 4: around 800 ms
```

With jitter, actual delays vary around these targets within configured bounds.

### 11.1. Choosing Limits Based on Business Deadlines

Do not pick a retry count just because an example showed four attempts. Consider:

- API request timeouts.
- Job or message consumer deadlines.
- Transaction and lock durations.
- Connection pool wait times.
- Level of database saturation.
- How long users can wait for a response.

If a request has a two-second deadline, a retry policy totaling five seconds of waits is unsuitable.

### 11.2. Avoiding Retry Amplification

If an API gateway, service A, service B, and a database client each retry three times independently, one incoming request can fan out into many downstream calls.

Assign retry responsibility for each error class to a single layer. Other layers should honor deadlines and propagate meaningful errors rather than multiplying attempts.

### 11.3. Do Not Retry Once a Request Is Cancelled

If the caller cancelled the request or the deadline expired, continuing to retry wastes connections and resources with no value. Integrate retry policies with system timeouts and cancellation.

## 12. Monitoring and Logging Retries

A solid retry setup should tell you:

- Which use case is retrying.
- Which exception triggered the retry.
- Current attempt number and maximum attempts.
- Wait duration between attempts.
- Whether the final retry succeeded or failed.
- Total time spent retrying.

Do not log full payloads, payment details, or personal data on every retry. Use command IDs or correlation IDs to link attempts together.

Spring Framework 7 publishes `MethodRetryEvent` on each exception from a retried method. You can use an event listener to gather structured metrics and logs.

With `RetryTemplate`, register a `RetryListener` to observe pre/post-attempt hooks and retry exhaustion.

Useful metrics:

| Metric | Purpose |
|---|---|
| Retry attempts by exception type | Identify common transient failures |
| Retry success rate | Measure how often retries actually recover |
| Retry exhausted count | Detect non-self-healing outages |
| Backoff duration | Track time overhead |
| Transaction rollback count | Monitor database impact |
| Idempotency duplicate count | Detect re-submitted requests |

If retry rates spike sharply, fix the root cause such as pool sizing, lock contention, database capacity, or slow queries. Retries are not a substitute for fixing infrastructure issues.

## 13. Testing Retries and Transaction Boundaries

Do not merely check that a method was called multiple times. Prove that failed attempts roll back and subsequent attempts start in a new transaction.

### 13.1. Unit Testing Retry Policies

Test exception classification or policy configuration with unit tests. Verify:

- Transient exceptions are allowed to retry.
- Validation exceptions are not retried.
- Optimistic locks are not retried with stale objects.
- Maximum invocation counts are accurate.
- Backoff delays are capped.

### 13.2. Integration Testing Transaction Retries

An integration scenario can simulate a transient failure on the first attempt and success on the second:

1. The first transaction writes a temporary change, then throws an exception.
2. The first transaction rolls back.
3. Retry calls the service again.
4. The new transaction sees rolled-back state.
5. The second attempt saves successfully.
6. The database contains only the single final business outcome.

Conceptual test example:

```java
@SpringBootTest
class RetryTransactionIntegrationTest {

    @Autowired
    OrderRetryFacade retryFacade;

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void retriesAfterTheFailedTransactionRollsBack() {
        retryFacade.processWithOneTransientFailure(42L);

        PurchaseOrder order = repository.findById(42L)
            .orElseThrow();

        assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);
    }
}
```

For the test to be meaningful, the dependency invoked on the first attempt must trigger a controlled transient error. Then verify that any side effects from the first attempt are gone and only the successful attempt's outcome committed.

### 13.3. Do Not Wrap Tests in an Outer Transaction When Testing Real Commits

A `@Transactional` annotation at the test level can alter how service transactions behave. When you need to verify that a service's own transactions commit or roll back, run the test without an outer transaction or use appropriate propagation.

Example:

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class RetryCommitIntegrationTest {
    // Call the service so each attempt manages its own transaction.
}
```

### 13.4. Testing Idempotency

Send the same command ID twice and assert:

- Only one order is created.
- Only one idempotency record exists.
- Both calls return the same result reference.
- No audit/payment side effects are duplicated.

Run tests against a production-compatible database when relying on unique constraints or transaction isolation.

## 14. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Retries repeat validation errors | Retrying every exception | Specify includes/excludes |
| Deadlock triggers retry yet retry still fails | Retrying inside a rollback-only transaction | Retry the whole operation in a new transaction |
| Every retry creates another record | Non-idempotent operation | Use idempotency keys and unique constraints |
| Money deducted multiple times | Retrying unprotected balance updates | Use command IDs, ledgers, or provider idempotency |
| Subsequent attempt still uses stale data | Re-saving the same stale aggregate | Reload and recompute business rules |
| Annotations have no effect | Self-invocation or unproxied bean | Invoke through a Spring bean proxy |
| Retry does not open a new transaction | Caller already opened an outer transaction | Place retry boundary outside transactions or split coordinator/worker |
| Database becomes even more overloaded after enabling retries | Missing backoff, jitter, or cap | Use exponential backoff and max delay |
| Requests exceed deadlines | Total retry duration exceeds business timeout | Cap attempts, delays, and timeouts |
| Messages delivered twice | Retrying publish after broker received it but ACK was lost | Idempotent consumers or outbox event IDs |
| Retry fails to resolve optimistic locks | Re-saving the same stale object/version | Reload, re-check invariants, and recompute |
| Multi-layer nested retries multiply calls | Every layer retries independently | Assign retry policy ownership to a single layer |
| Tests pass even though transactions do not roll back | Test wrapped in outer transaction or repositories mocked | Integration test against a database and inspect state after rollback |

## 15. Retry Design Workflow for a Spring Data JDBC Use Case

Before adding annotations or RetryTemplate, answer these questions in order:

1. Which errors can be transient and resolve on their own?
2. Which Spring DAO exceptions represent those errors?
3. Is the operation idempotent?
4. If commit outcome is ambiguous, how is an already-processed request identified?
5. Does the retry encompass all database operations requiring atomicity?
6. Does each attempt get a fresh transaction?
7. Could an outer transaction cause attempts to share the same transaction?
8. Are attempt counts, backoff, jitter, and deadlines appropriate?
9. Do external side effects use idempotency keys or an outbox?
10. Do integration tests prove rollback and final database state?

If safe repeatability cannot be guaranteed, add idempotency or redesign side-effect boundaries before enabling automatic retries.

## 16. Practice Exercises

**Exercise 1.** The database returns a deadlock while saving an aggregate. Should you retry?

*Answer:* Yes, provided you retry the entire transaction after rollback and the business operation is safe to re-run.

**Exercise 2.** A unique constraint rejects an existing order code. Should you retry with the same data?

*Answer:* No. This is a permanent data/logic error; handle the conflict or return a business error.

**Exercise 3.** Since which version does Spring Framework 7 include built-in retry support?

*Answer:* Since Spring Framework 7.0, via `@Retryable` and `RetryTemplate` in the core framework.

**Exercise 4.** Does `maxRetries = 3` in Spring Framework 7 mean three total invocations?

*Answer:* No. There is one initial invocation plus up to three retries, for up to four total invocations.

**Exercise 5.** Why must retryable exceptions be restricted?

*Answer:* Because validation, SQL errors, constraint violations, or permission errors do not resolve when retried. Retrying them only adds load.

**Exercise 6.** When using `@Retryable` together with `@Transactional` in Spring Framework 7, what is the default advice order?

*Answer:* Retry on the outside and transaction on the inside. Each attempt passes through the transaction interceptor and can use a new transaction when no outer transaction is active.

**Exercise 7.** Why shouldn't you retry the exact same object after an optimistic locking conflict?

*Answer:* The object still holds the outdated version. You must reload the latest aggregate and re-evaluate business rules before saving again.

**Exercise 8.** Can retries cause emails or payments to be sent twice?

*Answer:* Yes. External side effects outside the database require idempotency keys, an outbox, or idempotent consumers.

**Exercise 9.** Why is jitter needed?

*Answer:* Jitter spreads retry attempts across clients so they do not all hit the database again after the exact same delay.

**Exercise 10.** If a caller already opened an outer transaction and invokes a retryable method, is each attempt guaranteed to run in its own transaction?

*Answer:* No. REQUIRED propagation can join the outer transaction. Place the retry boundary properly or separate the coordinator from the transactional worker.

**Exercise 11.** Can a project on Spring Framework 6.x use native `org.springframework.resilience.annotation.Retryable`?

*Answer:* No. Native resilience annotations were introduced in Spring Framework 7.0. Older projects can use Spring Retry if dependency versions are compatible, or implement explicit retry boundaries.

## 17. Key Takeaways

- Retries target transient errors; never retry every exception.
- Classify errors using the Spring DAO hierarchy and explicitly list retryable groups.
- Safe retryable operations require idempotency or a way to recognize already-processed requests.
- Retry the whole transaction so failed attempts roll back before the next attempt begins.
- Spring Framework 7.0 includes `@Retryable` and `RetryTemplate` in core.
- In Spring Framework 7, `maxRetries` counts retries after the initial call; total calls equal one plus maxRetries.
- Default retry advice wraps outside transaction advice, giving each attempt its own transaction when no outer transaction exists.
- Never re-save stale aggregates after optimistic locking conflicts; reload and recompute business logic.
- Use backoff, jitter, max delay, and deadlines to prevent retry storms.
- Never retry external side effects without idempotency keys, an outbox, or deduplication.
- For Spring Framework versions prior to 7.0, Spring Retry may be used; distinguish packages and how maxAttempts is counted.
- Integration tests must prove transaction rollback, fresh attempts, and final database state.

### Official References

- [Spring Framework — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): `@Retryable`, `@EnableResilientMethods`, `RetryTemplate`, backoff, and retry/transaction ordering.
- [Spring Framework — Retryable API 7.0](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/resilience/annotation/Retryable.html): exception includes/excludes, maxRetries, delay, jitter, multiplier, and maxDelay.
- [Spring Framework — RetryTemplate API 7.0](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/core/retry/RetryTemplate.html): retry policies and programmatic retry execution.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): default repository transactions and service transaction boundaries.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxies, propagation, and rollback rules.
- [Spring Retry — Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html): annotations and attributes of the Spring Retry library for stacks not using Framework 7's resilience features.

When adding retries, start from operation safety and transaction boundaries. Only when you know clearly which failures may be retried, how each attempt rolls back or commits, and how requests are deduplicated will retries help your system recover without duplicating side effects.
