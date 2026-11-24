# Transaction Phase AFTER_ROLLBACK

`@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)` allows handling an event after the transaction containing that event has rolled back. This is the hook for scenarios where a transaction ends in failure: releasing external resources, recording an unsuccessful attempt, raising alerts, or starting an appropriate compensating workflow.

The key point is that the event is normally **published while the transaction is still active**. Spring registers the listener with transaction synchronization, and then invokes the listener method only if the transaction actually rolls back. The listener does not cause the rollback itself and does not replace the database's rollback mechanism.

## 1. What Is AFTER_ROLLBACK?

`TransactionPhase` is an enum in the package:

~~~java
org.springframework.transaction.event
~~~

Values:

| Phase | Processing time |
|---|---|
| `BEFORE_COMMIT` | Before the transaction commits |
| `AFTER_COMMIT` | After a successful commit; default phase |
| `AFTER_ROLLBACK` | After the transaction rolls back |
| `AFTER_COMPLETION` | After the transaction completes, whether committed or rolled back |

`AFTER_ROLLBACK` is a specialization of `AFTER_COMPLETION`. It only executes when the transaction completes with a rollback status. If the transaction commits successfully, a listener with this phase does not run.

Declaration example:

~~~java
@Component
class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onOrderRolledBack(OrderPlacementAttempted event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

If `phase` is not specified, `@TransactionalEventListener` defaults to `AFTER_COMMIT`. Therefore, explicitly declare `TransactionPhase.AFTER_ROLLBACK` when the goal is post-rollback handling.

## 2. How Is the Event Registered?

In the imperative flow, when an event is published inside an active transaction:

1. The service calls `ApplicationEventPublisher.publishEvent(event)`.
2. Spring finds matching transactional listeners.
3. The listener adapter registers a callback with the current transaction synchronization.
4. The listener method does not run yet at the publish site.
5. The transaction manager performs commit or rollback.
6. If the transaction rolls back, Spring invokes listeners with the `AFTER_ROLLBACK` phase.
7. If the transaction commits, `AFTER_ROLLBACK` listeners are skipped.

~~~text
@Transactional service
        |
        | publishEvent(OrderPlacementAttempted)
        v
Spring registers transaction synchronization
        |
        v
Service continues
        |
        +---- commit ----------------> AFTER_ROLLBACK is skipped
        |
        +---- rollback --------------> AFTER_ROLLBACK listener runs
~~~

This differs from a regular `@EventListener`: a regular listener is invoked during event dispatch, whereas `@TransactionalEventListener` waits for the transaction to reach the chosen phase.

With a synchronous listener, the rollback callback is typically executed while the transaction manager completes the transaction, before the call through the transaction proxy returns a result or throws an exception to the outer caller.

## 3. Runnable Example: Transaction Rollback Triggers the Listener

The following example uses Java 17+, Spring Boot 3.5.x, JDBC, and H2. The service writes an order, publishes an event, and intentionally throws a runtime exception. The database rolls back the insert operation; the `AFTER_ROLLBACK` listener receives the previously registered event.

**Maven dependencies:**

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

**File `src/main/resources/schema.sql`:**

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY
);
~~~

**File `src/main/java/com/example/rollback/RollbackEventDemo.java`:**

~~~java
package com.example.rollback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
public class RollbackEventDemo {

    public static void main(String[] args) {
        SpringApplication.run(RollbackEventDemo.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.placeAndFail("ORD-130");
            } catch (IllegalStateException ex) {
                System.out.println("Caller caught: " + ex.getMessage());
            }

            Integer count = jdbc.queryForObject(
                    "select count(*) from orders where order_id = ?",
                    Integer.class,
                    "ORD-130"
            );
            System.out.println("Rows after rollback: " + count);
        };
    }
}

record OrderPlacementAttempted(String orderId) {}

@Service
class OrderService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    OrderService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher
    ) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void placeAndFail(String orderId) {
        jdbc.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderPlacementAttempted(orderId));
        System.out.println("Service: event published");

        throw new IllegalStateException("simulated failure");
    }
}

@Component
class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Rollback listener: " + event.orderId());
    }
}
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

Output lines produced by the application code; Spring Boot startup logs are omitted:

~~~text
Service: event published
Rollback listener: ORD-130
Caller caught: simulated failure
Rows after rollback: 0
~~~

Explanation:

1. `OrderService.placeAndFail` runs through the Spring transaction proxy.
2. The JDBC insert executes within the transaction.
3. The `OrderPlacementAttempted` event is published while the transaction is active; Spring registers the rollback callback.
4. The runtime exception rolls back the transaction by default.
5. The listener receives the event at the `AFTER_ROLLBACK` phase.
6. The exception continues to propagate to the caller and is caught in `CommandLineRunner`.
7. The post-rollback query confirms the record does not exist.

This example requires the classes to be in a package scanned by Spring Boot component scanning, `schema.sql` in the proper location, and the JDBC/H2 dependencies shown above. It demonstrates an actual database rollback and post-rollback callback, not merely calling a listener method directly.

## 4. What Causes a Transaction to Roll Back?

`AFTER_ROLLBACK` depends on the final outcome of the transaction. An exception appearing in code does not always mean the transaction rolled back.

With `@Transactional` under Spring's traditional default rules:

- `RuntimeException` and `Error` roll back the transaction.
- Checked exceptions do not roll back by default.
- Rules can be changed using `rollbackFor` and `noRollbackFor`.
- Code can mark a transaction rollback-only using `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` or the corresponding transaction status API.
- The transaction manager can roll back due to errors during commit or because rollback-only status was marked.

Example of a checked exception requiring rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    // Perform data operations.
    throw new IOException("invalid input");
}
~~~

Example of marking rollback-only:

~~~java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

In the second case, the method can finish without throwing an exception at the marking line. When the transaction interceptor attempts to commit, the transaction still rolls back and the `AFTER_ROLLBACK` listener is invoked.

Since Spring Framework 6.2, the global default rollback rule can be changed via `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`, so that checked exceptions also roll back unless overridden by a specific rule. Check the application's transaction management configuration before drawing conclusions from an exception type.

Therefore, the listener should reflect the final transaction state. Do not assume the listener will run just because the service logged an error or caught an exception.

## 5. Distinguishing Rollback from a Failed Processing Attempt

A transaction rollback can originate from many causes:

- Business validation failure.
- Insufficient balance or unmet conditions.
- Database access error.
- Deadlock or optimistic locking conflict.
- A downstream service throwing an exception causing the transaction to be marked rollback-only.
- Code explicitly calling `setRollbackOnly()`.

Because the event is published before the transaction ends, it usually describes an **attempt or pending request**, such as `OrderPlacementAttempted`, `PaymentRequested`, or `InventoryReservationRequested`.

An `AFTER_ROLLBACK` listener knows the transaction rolled back, but the event payload does not automatically know the specific cause. If you need to classify the cause, include an error code or appropriate diagnostic data in the event before publishing, or record the cause in the exception handling layer.

Do not name an event `OrderCommitted` and then use it for rollback handling. The event name should accurately describe what happened at the time of publishing.

## 6. When Does AFTER_ROLLBACK Run and When Is It Skipped?

| Transaction outcome | AFTER_ROLLBACK listener |
|---|---|
| Transaction commits successfully | Does not run |
| Transaction rolls back due to runtime exception | Runs |
| Transaction rolls back due to checked exception with `rollbackFor` | Runs |
| Transaction marked rollback-only and finishes rolling back | Runs |
| Transaction rolls back due to commit/transaction manager error | Runs if transaction synchronization completes with rollback status |
| No active transaction | Does not run by default |
| No transaction and `fallbackExecution=true` | Runs immediately as fallback, with no actual rollback |

An event published outside a transaction is not queued to wait for a future transaction. If you want handling when there is no transaction, you must enable fallback and accept immediate-execution semantics.

## 7. fallbackExecution and the AFTER_ROLLBACK Phase

By default, `fallbackExecution` is `false`. If there is no transaction to register synchronization with, the transactional listener is skipped.

It can be enabled:

~~~java
@Component
class RollbackObserver {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK,
            fallbackExecution = true
    )
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Observed: " + event.orderId());
    }
}
~~~

Understand the two branches clearly:

- **With a transaction:** the listener only runs when the transaction actually rolls back.
- **Without a transaction:** fallback invokes the listener immediately at publish time, regardless of the declared phase.

Therefore, with `fallbackExecution=true`, a listener named `onRollback` can run even when no rollback occurred at all. Spring treats this as fallback execution; it does not simulate a transaction rollback.

Only enable fallback if immediate execution outside a transaction is still valid business behavior. If the listener only makes sense when a database transaction fails, keep the default false.

## 8. How Do AFTER_ROLLBACK and AFTER_COMPLETION Differ?

`AFTER_COMPLETION` runs after the transaction finishes whether it committed or rolled back. `AFTER_ROLLBACK` only runs when the outcome is a rollback.

Example with two listeners:

~~~java
@Component
class TransactionOutcomeListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Rollback: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void onCompletion(OrderPlacementAttempted event) {
        System.out.println("Completed: " + event.orderId());
    }
}
~~~

If the transaction rolls back, both listeners can be invoked. If the transaction commits, only the `AFTER_COMPLETION` listener is invoked.

Choose:

- `AFTER_ROLLBACK` when you only need to react to a rollback.
- `AFTER_COMPLETION` when you need cleanup or recording for both outcomes.
- `AFTER_COMMIT` when you only process after a successful commit.

Do not use `AFTER_COMPLETION` and manually check rollback status if a simple requirement can be expressed directly using the appropriate phase.

## 9. Ordering Across Multiple Rollback Listeners

`@Order` can be used to order transactional listeners receiving the same event:

~~~java
@Component
class RollbackListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Order(10)
    public void releaseReservation(OrderPlacementAttempted event) {
        System.out.println("Release reservation");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Order(20)
    public void recordAudit(OrderPlacementAttempted event) {
        System.out.println("Record rollback audit");
    }
}
~~~

Smaller order values have higher priority. `@Order` helps order callbacks within the same dispatch mechanism; it does not create a new transaction, does not guarantee retries, and does not orchestrate a distributed workflow.

If the audit step must only run after the release step succeeds, model that dependency in an explicit coordinating service. Do not rely on listener ordering to guarantee a complex business workflow.

## 10. Writing to the Database from AFTER_ROLLBACK Requires a New Transaction

This is an important consideration when the callback needs to persist an audit record or processing state.

At the `AFTER_ROLLBACK` phase, the original transaction has already rolled back. However, transaction resources may still remain bound and accessible during the callback. A new data access operation might still participate in the old transaction's resource, with no subsequent commit to save the changes.

Therefore, if the listener needs to write to the database, open an independent transaction, usually with `REQUIRES_NEW` propagation.

~~~java
@Component
class OrderRollbackListener {
    private final RollbackAuditService auditService;

    OrderRollbackListener(RollbackAuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        auditService.record(event.orderId(), "TRANSACTION_ROLLED_BACK");
    }
}

@Service
class RollbackAuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String outcome) {
        // Write audit in an independent transaction.
    }
}
~~~

Extracting the service into a separate bean ensures the `record` call goes through the Spring proxy. Calling another `@Transactional(REQUIRES_NEW)` method in the same object via self-invocation bypasses the proxy by default.

`TransactionTemplate` with `PROPAGATION_REQUIRES_NEW` can be used if explicit control is needed. Regardless of the approach, the audit transaction is a new transaction; it cannot restore the rolled-back business transaction.

## 11. What Should AFTER_ROLLBACK Be Used For?

Suitable cases:

- Releasing a reservation or resource held in an external system.
- Recording a failed processing attempt into an independent audit store.
- Emitting operational alerts when a critical transaction rolls back.
- Triggering a compensating workflow for non-database side effects.
- Updating error observability metrics or statuses.
- Notifying another system of the failure outcome when business requirements permit.

Considerations for side effects:

- Sending emails or webhooks inside a callback does not have durable retries.
- Calling slow downstream APIs can prolong transaction completion.
- Writing an audit into the same rolled-back transaction will not be persisted.
- Sending a message directly to a broker can fail between rollback and publish.
- In-process callbacks are not guaranteed to execute if the application stops abruptly.

If rollback notifications must be delivered durably, a dedicated persistence/orchestration design is needed. An independent transaction can be used to write a failure record/outbox after rollback and relay it to a broker. An outbox written inside the rolled-back transaction will also roll back, so you must explicitly use an independent transaction to persist the failure outcome.

## 12. Transaction Propagation Affects Listener Timing

When transaction methods are nested or join an outer transaction, the listener binds to the outcome of the transaction it was registered with.

- `REQUIRED`: the method joins an existing transaction if one exists. The listener waits for the final outcome of the shared transaction; the child method returning normally does not mean the listener runs.
- `REQUIRES_NEW`: creates an independent transaction. The listener is registered in the new transaction and runs based on that transaction's outcome.
- `SUPPORTS`: joins a transaction if one exists; otherwise, there is no synchronization to register the listener unless fallback is enabled.
- `NOT_SUPPORTED`: runs outside a transaction after suspending the current transaction; transactional listeners may be skipped or run via fallback.
- `MANDATORY`: requires an existing transaction; if none exists, throws an exception before the method body runs.

For example, with `REQUIRED`: a child service may publish an event and return, but the `AFTER_ROLLBACK` listener only runs if the outermost transaction ultimately rolls back. If the outermost transaction commits, the listener does not run.

Do not infer the phase from a specific method throwing an exception. Look at propagation and the final outcome of the transaction that actually owns the synchronization.

## 13. Reactive Transactions and AFTER_ROLLBACK

Since Spring Framework 6.1, transactional event listeners also support reactive transactions managed by `ReactiveTransactionManager`.

Reactive transactions store their context in the Reactor Context instead of `ThreadLocal`. When publishing an event in a reactive transaction, the event source needs to carry the `TransactionContext`. `TransactionalEventPublisher` can be used to create events with the right source and compose the returned Mono into the same reactive pipeline.

Conceptual example:

~~~java
return repository.save(entity)
        .flatMap(saved ->
                transactionalEventPublisher
                        .publishEvent(new OrderPlacementAttempted(saved.id()))
                        .thenReturn(saved)
        )
        .as(transactionalOperator::transactional);
~~~

The listener can still be declared as:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderPlacementAttempted event) {
    // Handle after the reactive transaction rolls back.
}
~~~

Do not call a detached `.subscribe()` inside the service. If the event does not carry the transaction context or the subscription falls outside the transaction pipeline, Spring cannot bind the listener to the right reactive transaction. For imperative applications using `PlatformTransactionManager`, the event source does not need to manually carry `TransactionContext` in this reactive manner.

## 14. Testing AFTER_ROLLBACK

Tests should use a real transaction manager or appropriate test transactions. Directly invoking the listener method alone does not prove Spring registers and invokes the callback at the right phase.

Cases that should be tested:

1. Publish an event inside a transaction and then roll back: the listener is invoked exactly once.
2. Publish an event inside a transaction and then commit: the `AFTER_ROLLBACK` listener is not invoked.
3. Mark rollback-only: the listener runs when the transaction actually finishes with a rollback.
4. Checked exception without `rollbackFor`: verify the transaction can commit and the listener does not run under default rules.
5. Checked exception with `rollbackFor`: verify rollback and that the listener runs.
6. Publish outside a transaction with fallback false: the listener is skipped.
7. Publish outside a transaction with fallback true: the listener runs immediately, even without a rollback.
8. Listener writes to the database via `REQUIRES_NEW`: the audit record exists after the original transaction rolls back.

Testing with a Spring Boot integration test can invoke the real service and verify audit/rollback state after the proxied call completes. To verify no callback occurs on the commit branch, use a recording listener that counts received events and assert 0.

Do not use `Thread.sleep` to wait for synchronous callbacks. For async listeners, use a latch/future or Awaitility with a finite timeout and test the executor's error policy separately.

## 15. Common Pitfalls

- **Publishing an event after the transaction has already rolled back and expecting AFTER_ROLLBACK to receive it.** The listener must be registered within the transaction before the transaction ends.
- **Assuming a method with an exception definitely rolls back.** Checked exceptions do not roll back by default; check rollback rules and the final state.
- **Using AFTER_ROLLBACK to reverse database changes.** The database has already rolled back the original transaction's changes; the listener primarily handles external side effects or records the outcome.
- **Writing audits using the default transaction inside the callback.** Old resources may still be bound without further commits; use REQUIRES_NEW for an independent write.
- **Calling a REQUIRES_NEW method inside the same bean.** Self-invocation can bypass the proxy.
- **Enabling fallbackExecution and treating the callback as proof of rollback.** Without a transaction, fallback runs immediately without an actual rollback.
- **Using AFTER_COMPLETION when only rollback is needed.** Choose AFTER_ROLLBACK to avoid running on commit as well.
- **Assuming listener callbacks have retries or durable delivery.** In-process transactional event listeners do not automatically provide durable retries.
- **Using listener order as workflow orchestration.** @Order only sorts callback ordering; it does not create business dependencies.
- **Ignoring propagation.** The listener binds to the transaction that actually owns the synchronization, not necessarily the nearest method that published.

## 16. Implementation Checklist

- [ ] Is the event published in the transaction whose rollback outcome needs to be observed?
- [ ] Does the listener explicitly declare `phase = TransactionPhase.AFTER_ROLLBACK`?
- [ ] Does the transaction manager actually roll back according to the exception/rollback rules?
- [ ] Have runtime exceptions, checked exceptions, and rollback-only been distinguished?
- [ ] Does the event payload contain enough data for post-rollback handling?
- [ ] Is fallback true avoided if an actual rollback needs to be confirmed?
- [ ] If writing to the database in the callback, is an independent `REQUIRES_NEW` transaction used?
- [ ] Does the REQUIRES_NEW call go through a Spring proxy?
- [ ] Do external system side effects have timeouts, idempotency, and error handling?
- [ ] Have commit, rollback, fallback, and propagation all been tested?
- [ ] If durable delivery is required, is a separate failure record/outbox/broker designed?

`AFTER_ROLLBACK` allows Spring to invoke a listener when the transaction containing the event ends in a rollback. Publish the event inside the transaction, choose the phase explicitly, and let the listener handle effects appropriate for the failed state. If the callback needs to write to the database, open a new transaction with `REQUIRES_NEW`; if durable delivery is needed, add separate persistence and retry mechanisms.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionSynchronization.afterCompletion Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
