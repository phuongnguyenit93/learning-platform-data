# UnexpectedRollbackException and Handling rollback-only

In Spring Data JPA, `UnexpectedRollbackException` typically appears at the end of a transaction when the transaction has been marked `rollback-only`, yet the outer calling flow still proceeds to the commit step. Spring cannot commit a transaction marked for rollback, so it performs a rollback and notifies the caller with this exception.

The root cause usually lies earlier than when the exception appears: an inner call failed and the transaction was marked rollback-only, but the exception was caught so the outer method kept running as if everything were normal.

## 1. Understanding rollback-only and UnexpectedRollbackException

### Physical transactions and logical transaction scopes

When a method is annotated with `@Transactional`, Spring typically uses a proxy to start, join, commit, or roll back a transaction around the method call. The default propagation is `Propagation.REQUIRED`:

- If no transaction exists, Spring creates a new one.
- If a transaction already exists, the method joins the existing transaction.
- Multiple methods can have separate logical transaction scopes while sharing a single physical transaction.

When a method joining a transaction via `REQUIRED` fails with a `RuntimeException` or `Error`, Spring's interceptor applies rollback rules and marks the active transaction rollback-only. This marking applies to the shared physical transaction.

If the outer method catches the exception and continues, catching the exception only affects Java control flow. It does not clear the rollback-only flag. When the outermost method completes and Spring attempts to commit, Spring detects the transaction was marked rollback-only, rolls back, and throws `UnexpectedRollbackException`.

### Example: catching an inner exception while the transaction still rolls back

The two services below must be two separate Spring beans so the call from the parent service passes through the child service's transaction proxy.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChildService {

    @Transactional
    public void executeChild() {
        // May have already performed some database operations.
        throw new IllegalStateException("Inner operation failed");
    }
}
```

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ParentService {

    private final ChildService childService;

    public ParentService(ChildService childService) {
        this.childService = childService;
    }

    @Transactional
    public void execute() {
        try {
            childService.executeChild();
        } catch (IllegalStateException ex) {
            // Only catches the exception; the shared transaction is already marked rollback-only.
            System.out.println("Logged error: " + ex.getMessage());
        }

        // Subsequent statements may still execute.
        // However, the transaction can no longer commit.
    }
}
```

Execution sequence:

1. Caller invokes `ParentService.execute()`; Spring starts a transaction.
2. `ChildService.executeChild()` joins the existing transaction because it uses `REQUIRED`.
3. The child method throws `IllegalStateException`. The child method's transaction interceptor handles rollback and marks the shared transaction rollback-only.
4. The parent method catches the exception, continues running, and can return normally.
5. When the parent method exits, the interceptor attempts to commit. Since the transaction is rollback-only, Spring rolls back and throws `UnexpectedRollbackException`.

In this case, the final exception seen by the caller may be `UnexpectedRollbackException`, whereas the original cause was the exception caught from the child method. Look for the first exception in the logs to understand the root failure.

### When does an exception not automatically mark rollback-only?

Distinguish an exception crossing a transaction interceptor from an exception caught completely within the same method:

- If a child `@Transactional` method is called through a proxy and an exception escapes the child method, the interceptor can mark the transaction rollback-only per rollback rules.
- If code throws and catches an exception inside the same transactional method, the outer interceptor never sees that exception. Spring does not automatically mark rollback just because an exception was thrown and caught.
- However, Hibernate/JPA or the transaction manager can still mark the transaction rollback-only after a persistence-layer error. In that case, even if code caught the exception, the transaction still cannot commit.
- Under Spring's standard default rollback rules, `RuntimeException` and `Error` roll back the transaction; checked exceptions do not automatically roll back without extra configuration. You can declare `rollbackFor` or `noRollbackFor` when required by business logic.

## 2. Identifying and finding the root cause

Common symptoms:

- The exception appears when the outermost transactional method finishes, even though the method body appeared to complete.
- Logs contain an earlier caught exception, such as a business error, `DataIntegrityViolationException`, optimistic locking error, or persistence operation failure.
- Multiple `@Transactional` methods use `REQUIRED` propagation; an inner method failed while the caller kept going.
- Code called `setRollbackOnly()` or a JPA provider error marked the transaction rollback-only.

How to investigate:

1. Find the first exception occurring before `UnexpectedRollbackException`. Pinpoint the exact persistence statement or business rule that failed.
2. Trace transaction boundaries: which method started the transaction, which methods joined it, and whether the exception passed through a proxy or where it was caught.
3. Inspect `catch` blocks that log and continue. Simply logging does not return a transaction to a committable state.
4. Check rollback rules on `@Transactional`, any `setRollbackOnly()` calls, and configured propagation.
5. If you need to know which SQL operation failed, call `EntityManager.flush()` or use `saveAndFlush()` at an appropriate spot to force early persistence context synchronization. Flushing helps pinpoint error timing; it does not clear the rollback-only flag or repair a broken transaction.

You can enable logging to observe transaction boundaries and SQL statements:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.orm.jpa: DEBUG
    org.hibernate.SQL: DEBUG
```

Do not rely solely on the final exception. Cross-check transaction logs with the root exception and catch locations.

## 3. Choosing a fix based on business goals

### Approach 1: Let errors propagate when the entire operation must be atomic

If a child operation fails and the whole business operation must fail, let the exception propagate outward. Spring will roll back the transaction and the caller receives the original exception.

```java
@Service
public class ParentService {

    private final ChildService childService;

    public ParentService(ChildService childService) {
        this.childService = childService;
    }

    @Transactional
    public void execute() {
        childService.executeChild();
        // Only runs when the child operation succeeds.
        // If the child operation fails, the exception propagates and the transaction rolls back.
    }
}
```

This is usually the right choice for operations needing atomicity, such as creating an order and deducting stock in the same transaction. Do not catch an exception and keep writing data if business state is no longer consistent.

If a technical exception needs to be translated into a business exception, wrap the original exception and rethrow:

```java
try {
    childService.executeChild();
} catch (IllegalStateException ex) {
    throw new OrderProcessingException("Unable to process order", ex);
}
```

Business exceptions should be unchecked exceptions if you want them to follow the default rollback rule. If using checked exceptions, configure `rollbackFor` appropriately.

### Approach 2: Returning a failure result while still rolling back the transaction

Sometimes a method needs to return a business result instead of throwing an exception. If the error is handled within the current transaction scope and the transaction has not already been marked rollback-only by a child scope, you can explicitly mark rollback:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result execute() {
    try {
        // Perform operations requiring a transaction.
        performWork();
        return Result.success();
    } catch (RecoverableBusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return Result.failure(ex.getMessage());
    }
}
```

`setRollbackOnly()` instructs Spring to roll back when the current transaction scope finishes. This approach does not recover a transaction already marked rollback-only by a child scope. If a child method joining via `REQUIRED` already marked the shared transaction rollback-only, catching the exception outside and returning a normal result can still cause `UnexpectedRollbackException` at the outermost commit.

Therefore, use this approach only when the rollback intent is clear and callers understand the transaction may end in rollback. For new designs, prefer separating business result construction from the transaction boundary or letting exceptions propagate outward.

### Approach 3: Isolating operations needing an independent transaction with REQUIRES_NEW

If an inner operation needs to commit or roll back independently of the outer transaction, use `Propagation.REQUIRES_NEW`. Spring suspends the current transaction and opens a new physical transaction for that call.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String message) {
        // Save the audit record in a separate transaction.
    }
}
```

The outer method can catch errors from the independent operation and continue its own transaction:

```java
@Transactional
public void execute() {
    try {
        auditService.recordFailure("A secondary operation failed");
    } catch (RuntimeException ex) {
        // The audit's separate transaction has rolled back.
        // The outer transaction can still continue if no other error occurred.
    }

    // Operations of the outer transaction.
}
```

Use `REQUIRES_NEW` when independence is a genuine business requirement, such as saving an audit record that must exist even if the main transaction rolls back. Note:

- A `REQUIRES_NEW` method must be called through a Spring proxy; self-invocation within the same class does not trigger the transaction proxy under default proxy mode.
- The new transaction uses a separate connection resource while the outer transaction is suspended, so consider connection pool capacity and lock durations.
- If an exception from the new transaction continues propagating outward, the outer transaction can still roll back under its own rollback rules. Handle the exception intentionally if the outer transaction should continue.
- Do not use `REQUIRES_NEW` merely to hide data errors or arbitrarily split operations that ought to be atomic.

### Approach 4: Using noRollbackFor only for errors where continuing is truly safe

You can configure an exception type not to trigger Spring rollback:

```java
@Transactional(noRollbackFor = InventoryWarningException.class)
public void reserveInventory() {
    // A business warning determined not to corrupt the transaction.
}
```

This is only appropriate when the exception represents a recoverable condition and the transaction manager/JPA provider has not marked the transaction rollback-only. `noRollbackFor` only changes Spring's rollback rules; it cannot clear a rollback-only flag already set by Hibernate, JPA, or the transaction manager. Do not use this to continue a transaction after SQL errors, constraint errors, or persistence failures that invalidate the transaction.

### Caution with NESTED

`Propagation.NESTED` usually relies on physical transaction savepoints and only works when supported by the transaction manager. Support depends on the transaction manager type and configuration. With Spring Data JPA, do not assume `NESTED` creates an independent nested JPA transaction; JPA does not provide a portable nested transaction mechanism. If clear transaction independence is needed, evaluate `REQUIRES_NEW`.

## 4. Comparing common propagations

| Propagation | Behavior | Impact when child scope fails |
|---|---|---|
| `REQUIRED` | Joins current transaction or creates a new one if none exists | If the joining scope marks rollback-only, the shared physical transaction cannot commit; caller may receive `UnexpectedRollbackException` |
| `REQUIRES_NEW` | Suspends current transaction and creates a new physical transaction | Child transaction rolls back independently; outer transaction can continue if exception is handled and outer itself is not rollback-only |
| `NESTED` | Creates a savepoint in the current transaction if supported by the transaction manager | Can roll back to the savepoint; not a portable JPA nested solution |

By default `@Transactional` uses `REQUIRED`. Only change propagation when business data consistency boundaries demand it.

## 5. Testing to catch errors right at the commit boundary

An integration test should invoke the service through the Spring bean and let the service's transaction finish on its own. Do not put `@Transactional` on the test itself, because the test's transaction can change commit timing and cause exceptions to surface only when the test framework finishes.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class ParentServiceIntegrationTest {

    @Autowired
    private ParentService parentService;

    @Test
    void shouldExposeUnexpectedRollbackWhenInnerRequiredTransactionFails() {
        assertThrows(
            UnexpectedRollbackException.class,
            () -> parentService.execute()
        );
    }
}
```

This test illustrates the case where a parent service catches a child service's exception while the shared transaction is already rollback-only. In real business tests, add repository assertions to confirm changes belonging to the transaction rolled back and left no partial data.

When testing fixes:

- With exception propagation, verify the caller receives the appropriate exception and data rolled back.
- With `REQUIRES_NEW`, verify the independent transaction's data committed/rolled back per its own outcome, while the outer transaction produces the expected result.
- With `setRollbackOnly()`, verify the method returns the expected result and transaction data rolled back.
- Do not test only that the Java method ran to completion; verify state after the transaction actually ends.

## 6. Common mistakes and how to avoid them

- **Catching and ignoring exceptions:** the caller thinks the operation succeeded, yet the transaction is already rollback-only. Decide explicitly whether to propagate the error, return a failure result with intentional rollback, or isolate an independent transaction.
- **Assuming catch clears rollback-only:** `catch` only catches the exception; it does not reset transaction state. There is no safe way to turn a transaction already marked rollback-only by the persistence provider back into a committable state.
- **Continuing to use a persistence context after a JPA error:** after transaction rollback, managed entities may no longer reflect database state. End the transaction and reload data in a new transaction when needed.
- **Using `noRollbackFor` to bypass database errors:** Spring rollback rules cannot reverse a rollback-only state set by the provider or transaction manager.
- **Calling transactional methods via self-invocation:** internal calls on the same object usually bypass the proxy in default proxy mode, so annotations on the called method may not apply. Extract services or redesign bean boundaries.
- **Using `REQUIRES_NEW` everywhere:** splitting transactions can break business atomicity and increase connection demand. Use it only when data needs an independent commit/rollback lifecycle.
- **Looking only at the final exception:** `UnexpectedRollbackException` is usually a symptom. Find the first exception or where rollback-only was marked in the logs.

## 7. Quick troubleshooting workflow

1. Find the root exception that occurred before `UnexpectedRollbackException`.
2. Identify the outermost transaction and child methods joining via `REQUIRED`.
3. Check whether the exception passed through a proxy, where it was caught, and whether rollback rules or `setRollbackOnly()` applied.
4. Determine whether the business logic requires full rollback, independent partial rollback, or returning an intentional failure result.
5. Choose the right approach: propagate the exception, mark rollback-only in the right scope, or isolate a transaction with `REQUIRES_NEW`.
6. Write integration tests verifying both the exception at commit and the data state after the transaction.

The most important principle is treating rollback-only as a terminal state for the transaction: once a physical transaction is marked rollback-only, continuing to run Java code cannot make that transaction committable again. Fix transaction boundaries and error handling to match the business data consistency requirements.