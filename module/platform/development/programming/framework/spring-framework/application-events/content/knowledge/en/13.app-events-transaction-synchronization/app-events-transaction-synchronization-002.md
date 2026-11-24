# TransactionSynchronization and Callbacks in Spring Framework

## 1. What is transaction synchronization?

In Spring Framework, **transaction synchronization** is a mechanism that allows application code or infrastructure components to register callbacks to receive notifications at milestones in a transaction's lifecycle: before commit, before completion, after commit, and after completion (commit or rollback). The core APIs for transactions managed by `PlatformTransactionManager` are:

- `org.springframework.transaction.support.TransactionSynchronization`: the interface declaring the callbacks.
- `org.springframework.transaction.support.TransactionSynchronizationManager`: holds and manages registered synchronizations in the current transaction context.
- `PlatformTransactionManager`, such as `DataSourceTransactionManager`: executes the transaction and triggers callbacks at the corresponding moments.

This is especially important when **Spring Framework Application Events** are tied to transactional business operations. For instance, an external system should only be notified of an order after the order record commits successfully. Conversely, if the transaction rolls back, notifying as if the order had been created would leave systems out of sync.

Transaction synchronization allows placing logic at a specific **transaction stage**. However, it does not turn a task into a durably stored message, does not replace another transaction when writing data after commit, and does not mean the steps form a distributed transaction.

## 2. Distinguishing callbacks from the main transaction

A transaction generally follows this conceptual path:

```text
Start transaction
        |
Execute business logic, modify data
        |
        +---- Choose COMMIT ---------------------------+
        |                                              |
        |   beforeCommit(readOnly)                     |
        |   beforeCompletion()                         |
        |   database commit                            |
        |   afterCommit()                              |
        |   afterCompletion(COMMITTED)                 |
        |                                              |
        +----------------------------------------------+
        |
        +---- Choose ROLLBACK -------------------------+
                                                       |
            beforeCompletion()                         |
            database rollback                          |
            afterCompletion(ROLLED_BACK)               |
                                                       |
            Finish, clean up resources, return control
```

The diagram depicts the main milestones of a typical transaction coordinated by `AbstractPlatformTransactionManager`. It omits details such as suspend/resume, flush, rollback caused by an error at commit time, JTA, nested transactions, and callback ordering across multiple synchronizations.

**Key takeaway:** `beforeCommit` does not guarantee the data will definitely commit. Immediately afterward, the commit can still fail and the transaction can roll back. Conversely, `afterCommit` runs only on the successful commit branch; at that point the original DB changes are already committed.

## 3. Important callbacks of TransactionSynchronization

| Callback | When is it called? | Appropriate purpose | What to avoid |
| --- | --- | --- | --- |
| `beforeCommit(boolean readOnly)` | Before proceeding with commit | Checking/flushing data that must finish before commit | Sending email or external side effects while assuming commit is guaranteed |
| `beforeCompletion()` | Before transaction completion, including on rollback | Cleaning up temporary state, closing auxiliary resources | Treating it as a signal that "commit is about to succeed" |
| `afterCommit()` | After the transaction commits successfully | Triggering steps valid only after commit, notifications, scheduling jobs | Thinking you can roll back the original transaction if this callback fails |
| `afterCompletion(int status)` | After the transaction finishes | Cleanup regardless of outcome; knowing commit, rollback, or unknown | Treating status as `COMMITTED` when the actual status is unknown |
| `flush()` | When the transaction mechanism requests synchronous flushing | Pushing temporary resource state to the transaction resource | Assuming every transaction automatically invokes this callback at the same time |
| `suspend()` / `resume()` | When synchronization is suspended/resumed, depending on the transaction manager | Unbinding/rebinding thread-bound resources owned by the synchronization | Arbitrarily manipulating framework-owned resources |
| `getOrder()` | When the framework orders synchronizations | Determining callback priority relative to other synchronizations | Treating callback ordering as a substitute for business dependency design |

A modern `TransactionSynchronization` has default methods, so you can override only the callbacks you need. The mechanism may trigger callbacks at different times depending on the transaction manager and configuration. Do not assume every hook appears in every transaction.

**Status values of `afterCompletion(int status)`** are on the interface itself:
- `TransactionSynchronization.STATUS_COMMITTED`: the transaction committed.
- `TransactionSynchronization.STATUS_ROLLED_BACK`: the transaction rolled back.
- `TransactionSynchronization.STATUS_UNKNOWN`: the completion status could not be determined with certainty; handle cautiously.

The interface **does not have a separate `afterRollback()`**. If you need to do work after rollback, check `STATUS_ROLLED_BACK` in `afterCompletion` or use an event listener with `TransactionPhase.AFTER_ROLLBACK`.

## 4. Registering synchronization properly

Inside a transaction **using Spring's transaction manager**, wherever you need to bind callbacks, call:

```java
if (!TransactionSynchronizationManager.isSynchronizationActive()
        || !TransactionSynchronizationManager.isActualTransactionActive()) {
    throw new IllegalStateException("Requires an active Spring transaction");
}

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Runs after the current transaction commits successfully.
        }

        @Override
        public void afterCompletion(int status) {
            // Cleanup and observe completion outcome.
        }
    }
);
```

This is an **integration snippet**, not a standalone Java file. It must be used inside a service running with an appropriate Spring transaction, such as `@Transactional` through a Spring proxy or `TransactionTemplate`.

- `isSynchronizationActive()` indicates whether there is a context for registering callbacks. If false, `registerSynchronization` throws `IllegalStateException`.
- `isActualTransactionActive()` helps distinguish cases where the framework activates synchronization without an actual transaction (possible with certain propagations and synchronization policies). If a side effect is valid only after an **actual commit**, check both conditions.
- `TransactionSynchronizationManager` in the traditional imperative model uses a **thread-bound** context. It does not automatically carry synchronization to a new thread, `@Async`, or an executor task. In reactive applications, there is a separate transaction synchronization API based on Reactor Context.

A callback registration function should be called **while the current transaction is still active**, not after the `@Transactional` service has returned. If registration is done afterward, the transaction manager has no lifecycle milestones left to notify.

## 5. Runnable Java 17+ example: commit and rollback

This example uses `TransactionTemplate`, `DataSourceTransactionManager`, `JdbcTemplate`, and an H2 in-memory database. We register **the same group of callbacks** for a transaction that will commit and one that deliberately rolls back, then verify the DB contains only the committed record.

No Spring Boot or external container is needed.

Structure:

```text
transaction-synchronization-demo/
├── build.gradle
└── src/main/java/demo/TransactionSynchronizationDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.1.21'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionSynchronizationDemo'
}
```

`spring-jdbc` brings in the necessary Spring Transaction components. H2 provides the JDBC driver at runtime.

Contents of `src/main/java/demo/TransactionSynchronizationDemo.java`:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionSynchronizationDemo {

    private static String statusName(int status) {
        return switch (status) {
            case TransactionSynchronization.STATUS_COMMITTED -> "COMMITTED";
            case TransactionSynchronization.STATUS_ROLLED_BACK -> "ROLLED_BACK";
            default -> "UNKNOWN";
        };
    }

    private static void registerCallbacks(String label) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()
                || !TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("An active transaction is required");
        }

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void beforeCommit(boolean readOnly) {
                    System.out.println(
                        label + " beforeCommit(readOnly=" + readOnly + ")"
                    );
                }

                @Override
                public void beforeCompletion() {
                    System.out.println(label + " beforeCompletion");
                }

                @Override
                public void afterCommit() {
                    System.out.println(label + " afterCommit");
                }

                @Override
                public void afterCompletion(int status) {
                    System.out.println(
                        label + " afterCompletion(" + statusName(status) + ")"
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
            "jdbc:h2:mem:transaction_sync_demo;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE demo_event " +
            "(id INT PRIMARY KEY, description VARCHAR(50))"
        );

        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        TransactionTemplate transactions = new TransactionTemplate(manager);

        System.out.println("=== COMMIT ===");
        transactions.executeWithoutResult(status -> {
            registerCallbacks("commit");
            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "committed"
            );
            System.out.println("commit business saved");
        });
        System.out.println("commit returned");

        System.out.println("=== ROLLBACK ===");
        transactions.executeWithoutResult(status -> {
            registerCallbacks("rollback");
            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                2, "rolled back"
            );
            System.out.println("rollback business saved");
            status.setRollbackOnly();
        });
        System.out.println("rollback returned");

        Integer persisted = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event", Integer.class
        );
        System.out.println("rows persisted=" + persisted);
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

**Expected stdout output from the program:**

```text
=== COMMIT ===
commit business saved
commit beforeCommit(readOnly=false)
commit beforeCompletion
commit afterCommit
commit afterCompletion(COMMITTED)
commit returned
=== ROLLBACK ===
rollback business saved
rollback beforeCompletion
rollback afterCompletion(ROLLED_BACK)
rollback returned
rows persisted=1
```

Points to verify in the output:

1. Both transactions write to the DB inside `TransactionTemplate`, but only the first record remains after completion (`rows persisted=1`).
2. The **commit** path invokes `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion(COMMITTED)`. `TransactionTemplate`'s `readOnly` attribute defaults to `false`.
3. The **rollback** path does not invoke `beforeCommit` or `afterCommit`; it invokes `beforeCompletion` and `afterCompletion(ROLLED_BACK)`.
4. The `commit returned` / `rollback returned` lines are printed **after** the callbacks because the callbacks in the example run synchronously during `TransactionTemplate`'s transaction completion loop.

The article uses `DriverManagerDataSource` for a simple demo; real systems should use a managed connection pool. Calling `JdbcTemplate` inside `DataSourceTransactionManager`'s transaction uses the transaction-bound connection per Spring's mechanism, so the insert actually rolls back.

## 6. What happens when a callback throws an error?

Errors from callbacks have different semantics depending on the timing:

| Hook | Error behavior to understand |
| --- | --- |
| `beforeCommit` | A `RuntimeException` can propagate into the commit process, and in the normal transaction manager path leads to rollback. `beforeCompletion` is still triggered when `beforeCommit` fails. |
| `beforeCompletion` | Errors are logged by the framework rather than being a reliable way to cancel commit. Reserve this hook for state cleanup and avoid error-prone side effects. |
| `afterCommit` | The main transaction **has already committed**. A runtime exception may propagate to the caller, but cannot reverse the prior commit. |
| `afterCompletion` | Primarily for cleanup; errors are logged and must not be used as a condition to alter the outcome of a finished transaction. |

For an `afterCommit` callback, the caller receiving an exception does not prove the DB data rolled back. This is a common source of business bugs:

```text
DB commit succeeds
    -> afterCommit calls notification service
       -> notification service fails
    -> caller may receive exception
    -> committed DB record still exists
```

To handle this, track the outcome of the post-commit task separately, design retry/idempotency, and avoid having the caller blindly resubmit the entire business operation. When notifications must be guaranteed even if the process crashes, use a **transactional outbox** or appropriate durable delivery infrastructure.

## 7. Relationship with Spring Application Events

In Spring Framework Application Events, two listener styles must be distinguished:

### 7.1. `@EventListener`: processed immediately when the event is published

With the default synchronous multicaster, `@EventListener` receives the event during the `publishEvent` call. If the publisher calls `publishEvent` **inside a transaction**, the listener can run before the transaction commits. Sending an email or calling an API from a regular listener risks creating side effects when the DB transaction later rolls back.

Illustrative example in a Spring-managed bean:

```java
@EventListener
public void onOrderPlaced(OrderPlacedEvent event) {
    // Dispatched immediately; the publisher's transaction may not have committed yet.
    auditService.recordEventObserved(event.orderId());
}
```

This snippet assumes `OrderPlacedEvent` and `auditService` are available; it is **not a standalone runnable program**.

### 7.2. `@TransactionalEventListener`: processed by transaction phase

`@TransactionalEventListener` provides a declarative way to bind event handling to transaction synchronization. The phases:

| `TransactionPhase` | Meaning |
| --- | --- |
| `BEFORE_COMMIT` | Process before commit |
| `AFTER_COMMIT` | Process after successful commit; this is the **default** |
| `AFTER_ROLLBACK` | Process after rollback |
| `AFTER_COMPLETION` | Process after transaction finishes, regardless of commit/rollback |

Example in a Spring-managed bean:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlacedEvent event) {
    notificationJobService.enqueue(event.orderId());
}
```

To compile this integration snippet, import `org.springframework.transaction.event.TransactionalEventListener` and `org.springframework.transaction.event.TransactionPhase`; the application must declare `OrderPlacedEvent`, `notificationJobService`, and appropriate transaction/event configuration.

Inside a transactional service, an event can be published:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.save(order);
    applicationEventPublisher.publishEvent(
        new OrderPlacedEvent(order.getId())
    );
}
```

This is also an **illustrative application snippet**, assuming the types, fields, and components are declared. The `AFTER_COMMIT` listener is bound to the **transaction outcome**, rather than running immediately at the time of `publishEvent` inside the open transaction.

**Note two important points:**

- By default, `@TransactionalEventListener` **does not execute if there is no suitable transaction**. You can set `fallbackExecution = true` to allow execution when no transaction exists, but that alters the "only after commit" semantics, so it must be weighed carefully.
- `TransactionPhase.AFTER_COMMIT` carries post-commit semantics, yet the internal callback mechanism of transactional event listeners is executed during the synchronization's after-completion stage. Do not rely on relative ordering between an `AFTER_COMMIT` event listener and a manual `afterCommit()` callback to build business dependencies. If there is a real dependency, coordinate it explicitly.

### 7.3. When to use manual callbacks?

Use `TransactionSynchronizationManager.registerSynchronization(...)` when you want direct control over the lifecycle of a resource or unit of work registered in the current transaction: cleanup, flush, restoring resource state, or a technical callback based on transaction outcome.

Use `@TransactionalEventListener` when the primary goal is **handling a business event** bound to a transaction phase. The annotation makes intent clear in an event-driven architecture and makes organizing independent consumers easier.

Both still require considering exceptions, transaction boundaries, callback ordering, and side-effect durability. Choosing the API does not automatically provide guaranteed exactly-once delivery.

## 8. The issue of resources still bound after commit

After the physical transaction commits, Spring may still be in the cleanup process, with resources/connections still bound to the thread during part of the callback lifecycle. Therefore, DB code inside `afterCommit` or an `AFTER_COMMIT` listener may still "see" the old resource, while new changes **are not guaranteed to commit as a new transaction**.

If you must create a new DB record **after** the original transaction commits, call another Spring service that opens a new transaction, for example:

```java
@Service
public class NotificationJobService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void createJob(long orderId) {
        jobRepository.insertPendingJob(orderId);
    }
}
```

This is an **illustrative integration snippet**, requiring `@Service`, `@Transactional`, `Propagation`, `jobRepository`, and corresponding types in the application. `REQUIRES_NEW` creates a separate transaction per the transaction manager's policy. The method must be called through the appropriate Spring proxy; **self-invocation within the same bean** normally bypasses the `@Transactional` interceptor in default proxy mode.

Even with `REQUIRES_NEW`, a post-commit error still does not roll back the original transaction. If the new job is data that **must exist simultaneously with the order**, a stronger design is to save the **outbox/job record inside the order-creation transaction itself**, then process delivery afterward.

## 9. Advanced scenarios

### 9.1. `REQUIRES_NEW` propagation, `NESTED`, and suspend/resume

If a transaction calls a method with `REQUIRES_NEW`, the outer transaction may be suspended; a new transaction begins and has its own synchronization. After the new transaction completes, the outer transaction is resumed. Therefore, callbacks registered in each transaction are bound to their **respective transaction scope**.

With JDBC savepoint-based `NESTED`, rolling back to a savepoint is not the same as rolling back the entire outer transaction. If an application builds logic that needs to know savepoints precisely, Spring Framework **6.2+** adds `savepoint(Object savepoint)` and `savepointRollback(Object savepoint)` callbacks to `TransactionSynchronization`. Those callbacks do not exist in the 6.1.x interface used in the main example. Do not rely on `afterCompletion(ROLLED_BACK)` to represent every rollback to a savepoint: the outer transaction may still continue and commit.

### 9.2. Ordering

`TransactionSynchronization` supports the `Ordered` contract, and a synchronization can provide `getOrder()`. The framework also registers internal synchronizations for its resources. Callback priority can matter for cleanup/infrastructure, but **implicit ordering should not be used** to force business steps to depend on one another.

`@Order` on a regular `@EventListener` controls **listener dispatch** ordering; a synchronization's `getOrder()` controls **callback ordering within the transaction lifecycle**. The two concepts are not equivalent.

### 9.3. Reactive transactions and async

The examples above apply to the **imperative** model with `PlatformTransactionManager` and ThreadLocal-based `TransactionSynchronizationManager`. Spring's reactive transactions use the `org.springframework.transaction.reactive.TransactionSynchronizationManager` API and a Reactor-based transaction context; you must not read ThreadLocal `isActualTransactionActive()` and draw conclusions about reactive transaction state.

Similarly, if an event is published onto another thread, callbacks registered on that thread do not automatically bind to the event-creating thread's transaction. For reactive event listeners from Spring 6.1+, the reactive transaction context must be carried in a way compatible with the API and event context. Do not treat `@Async` as a way to inherit transaction context.

### 9.4. Avoid heavy work in callbacks

Callbacks are triggered on the transaction-finishing thread in the typical imperative model. Making a 10-second HTTP call in `afterCommit` can keep the request/worker waiting for `commit()` to return even though the database has already committed. Consider offloading post-commit work to a monitored job/queue, while weighing the risk of job loss if handed only to an in-memory executor.

## 10. Testing callbacks and phase-bound events

A good test suite does not only check a single successful commit path:

| Scenario | Test design | What to verify |
| --- | --- | --- |
| Commit | Use `TransactionTemplate`, register callbacks, write DB then commit | `beforeCommit`, `beforeCompletion`, `afterCommit`, `afterCompletion(COMMITTED)` at expected milestones; data persists |
| Explicit rollback | Call `status.setRollbackOnly()` | No `afterCommit`; `afterCompletion(ROLLED_BACK)` received; DB changes reverted |
| Pre-commit exception | Throw `RuntimeException` in business logic | Transaction rolls back; callbacks follow rollback branch; error is not swallowed |
| Exception in `beforeCommit` | Have callback throw an error and observe transaction | Do not assume committed; verify rollback, `beforeCompletion`, and actual outcome |
| Exception in `afterCommit` | Have callback throw an error after commit | Business data remains committed; post-commit task error must be observed |
| Event outside transaction | Publish event with no transaction | `@TransactionalEventListener` ignores by default; if `fallbackExecution` is enabled, test the new semantics |
| `REQUIRES_NEW` | Open a new transaction inside an outer transaction | Callbacks in each scope run according to their own transaction outcome |

With `@Transactional` in integration tests, be careful: some test frameworks automatically open a transaction and roll it back at the end, causing `AFTER_COMMIT` listeners **not to run**. If the goal is to test an actual commit, you can use `TransactionTemplate` or the transaction-ending mechanism supported by the test framework, then inspect side effects at the right moment.

In tests, avoid only asserting a list of callbacks in order when multiple framework synchronizations or multiple different listeners exist. Focus on the **right phase, final state, invocation counts, actual rollback, and idempotency**.

## 11. Common mistakes

1. **Putting email/API calls in `beforeCommit` thinking commit is guaranteed.** The transaction can still roll back; external side effects do not roll back with the DB.
2. **Treating `beforeCompletion` as equivalent to commit.** It is also called on the rollback path.
3. **Handling only success in `afterCommit` without retries.** A post-commit error cannot undo the old commit.
4. **Performing extra DB writes in `afterCommit` without opening a new transaction.** Resources may still be bound, causing commit state to be misunderstood.
5. **Registering callbacks when no synchronization is active.** `registerSynchronization` may throw `IllegalStateException`.
6. **Registering callbacks on an `@Async` thread expecting them to follow the original transaction.** ThreadLocal transaction context does not propagate across threads automatically.
7. **Assuming `@TransactionalEventListener` runs even without a transaction.** By default it does not; `fallbackExecution` must be understood clearly.
8. **Using callbacks to orchestrate a complex business chain in implicit order.** A workflow or explicit subsequent event step is easier to trace and retry.
9. **Treating `AFTER_COMMIT` as durable delivery.** If the process stops at the wrong moment, there is no proof the event was persisted for continued processing.
10. **Treating a savepoint rollback as a full transaction rollback.** With nested transactions, callback state must be understood per actual transaction and savepoint.

## 12. Adoption checklist

- Is the transaction imperative or reactive? Is the transaction manager managing synchronization?
- Are callbacks registered **inside** an actual transaction and on the proper thread/context?
- Does the task need to run before commit, after commit, after rollback, or as cleanup regardless of outcome?
- Are `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion` properly distinguished?
- If a post-commit callback fails, does the system understand the DB is already committed and have a retry/idempotency plan?
- If the post-commit operation must write to the DB, is a new transaction created properly?
- If notifications/side effects cannot be lost, is there an outbox or durable delivery mechanism?
- Do tests verify commit, rollback, exceptions, and the no-transaction case?

**Remember:** `TransactionSynchronization` provides transaction-lifecycle callbacks. `@TransactionalEventListener` is the declarative way to handle events by phase. Both require proper commit boundaries and recovery mechanisms when side effects live outside the transaction.

## References

- [Spring Framework API — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework API — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework API — DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
