# When Synchronous Is the Right Choice in Spring Framework Application Events

## 1. What Does Synchronous Mean When Publishing an Application Event?

In the Spring Framework, **ApplicationEventPublisher.publishEvent(event)** sends an event to the **ApplicationContext**'s **ApplicationEventMulticaster** dispatch mechanism. Beans receiving the event can use **@EventListener** or implement **ApplicationListener**.

With the default configuration of **SimpleApplicationEventMulticaster**, listeners run **synchronously on the exact thread calling publishEvent(...)**. This has three major consequences:

1. The event-publishing thread must wait for the current synchronous listener to finish running before continuing; when **publishEvent(...)** returns normally, synchronous listeners have been invoked and completed according to that dispatch mechanism.
2. The listener can see the publisher's thread context, including a thread-bound transaction when an active transaction exists and execution has not switched threads.
3. If a listener throws an unhandled exception, by default the exception propagates back to the publisher; the current dispatch pass can stop before invoking subsequent listeners.

**Note on the API contract:** the **ApplicationEventPublisher** interface itself does not promise that every implementation runs synchronously. The statements above apply to the **default SimpleApplicationEventMulticaster** with listeners that do not use **@Async**, have no asynchronous executor attached, and have no **ErrorHandler** altering error propagation. Whenever you customize the multicaster, you must re-evaluate actual behavior.

Synchronous execution is an *execution coordination style*: it does not create transactions automatically, does not retry automatically, does not guarantee data is committed, and does not turn an HTTP call or email send into a rollback-capable operation.

## 2. Signs You Should Choose Synchronous Processing

### 2.1. Must Determine Success or Failure Right on the Spot

This is the strongest criterion. If a listener checks a mandatory condition and its failure must cause the current operation to fail, running synchronously lets the caller receive the exception immediately.

Examples:

- An invoice approval request must be rejected if it exceeds a limit.
- An account activation request must be rejected if a mandatory legal condition is missing.
- An internal configuration change must validate all invariants before announcing it has been applied.

Desired path:

~~~text
Caller
  -> service handles request
     -> publishEvent(CheckRequested)
        -> listener checks (synchronously)
           -> valid: return
           -> invalid: throw
     -> continue or handle error directly in the same call stack
~~~

If the listener is offloaded to an executor with **@Async**, the caller can proceed before validation finishes. Exceptions in an asynchronous listener do not automatically return to the **publishEvent(...)** call, risking reporting success prematurely.

**Design boundary:** if a check is a core business precondition, it is usually better to call **validationService.validate(...)** directly before publishing an event. A synchronous listener makes more sense when you want decoupled components observing the same event while still needing immediate error feedback and an explicit failure contract.

### 2.2. Need the Same Transaction to Maintain Local Consistency

A synchronous **@EventListener** invoked while the event-publishing thread is still inside a **@Transactional** method runs within the same thread context. When the listener uses the same transaction manager, the same data resources, and compatible propagation, its DB operations can join the active transaction.

Example: a service creates a business record and a listener inserts a **mandatory audit record in the same database**. If writing the audit record fails, the business operation must not commit. A synchronous listener allows that error to propagate back to the transaction boundary.

However, merely sharing a thread is not enough to guarantee atomicity: a transaction must actually be active; repository calls must be configured to participate in the transaction; and the exception type must trigger rollback under the active rules. By default **@Transactional** rolls back on **RuntimeException** and **Error**; checked exceptions require explicit configuration such as **rollbackFor** to trigger rollback.

If the caller catches the exception and returns normally inside the transaction, the transaction may still commit. Therefore, never "swallow" errors from mandatory listeners.

### 2.3. Results Must Be Observable Before the Next Step

Certain **fast, internal, deterministic** side effects must complete before reading data or publishing a follow-up event.

Examples:

- Updating an in-memory lookup structure required by business logic before the service queries it.
- Sending an internal notification to multiple components to verify a new configuration; the caller proceeds only once all required synchronous components finish.
- Writing a mandatory audit record in the same transaction before the business method returns.

With this model, **@Order** can express the *invocation* order of listeners for the same event, yet when B truly depends on A's return value, calling services sequentially in code is usually easier to control. Events are not well suited for passing sequential outputs between listeners like a pipeline with mandatory return values.

### 2.4. Small, Time-Bounded Work with Low Dependencies

Synchronous execution is reasonable when the listener does fast work with predictable runtime: inline validation, local state updates, or small writes within the same transaction.

Conversely, unpredictable I/O such as sending emails, calling external APIs, querying slow services, or generating long reports easily prolongs transaction/lock hold times and increases response latency. Use synchronous execution for those only when the caller genuinely must wait for the result and clear timeouts, retries, idempotency, and error controls are in place.

## 3. Quick Selection Table Across Three Approaches

| Need | Option to consider | Reason |
| --- | --- | --- |
| Must have validation result to decide whether to run business logic | Direct synchronous service call | Explicit control flow, return data, and exceptions |
| Multiple components react to an event; every reaction is required for the operation to succeed | Synchronous **@EventListener** with clear error contract | Publisher waits for completion and receives exceptions under default config |
| A local reaction must write within the same DB transaction | Synchronous listener or direct service call inside the transaction | Can share the transaction when properly configured |
| Must send notifications only after the transaction commits successfully | **@TransactionalEventListener(AFTER_COMMIT)** | Avoids reacting to changes that ultimately roll back |
| Notification does not need to finish before the response | AFTER_COMMIT combined with **@Async** or separate worker | Keeps secondary processing latency off the main response path |
| Work must never be lost even if the process crashes | **Transactional outbox** + worker/queue | In-memory Spring events are not a durable queue |
| Step B depends directly on return data from Step A | Call A then B in a service | **@Order** only controls listener invocation order, not exchanging results |
| Need fast responses; listener may take seconds or call external services | Consider async/saga/stateful job | Avoids holding request threads or transactions too long |

Do not apply a naive rule like "important = synchronous, unimportant = asynchronous." Work that **must complete eventually** without needing to finish before the HTTP response is still important; it needs durable storage, retries, and outcome verification rather than **@Async** alone.

## 4. Java 17+ Example: Listener Error Returned to the Publisher

This example uses **Spring Framework 6.2.9** with default configuration, no custom executor, no **@Async**, and no database transaction. The goal is to prove precisely that: listeners run before **publishEvent(...)** returns; an earlier-ordered listener throwing an error prevents subsequent listeners from running in that dispatch pass.

Project structure:

~~~text
sync-event-demo/
  build.gradle
  src/main/java/demo/SyncDecisionDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.SyncDecisionDemo'
}
~~~

**src/main/java/demo/SyncDecisionDemo.java**:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SyncDecisionDemo {

    public record InvoiceApprovalRequested(String invoiceId, int amount) {}

    public static class LimitGuard {
        @EventListener
        @Order(10)
        public void validate(InvoiceApprovalRequested event) {
            System.out.println("guard: " + event.invoiceId());
            if (event.amount() > 1_000) {
                throw new IllegalArgumentException("exceeded demo limit");
            }
        }
    }

    public static class LocalAudit {
        @EventListener
        @Order(20)
        public void record(InvoiceApprovalRequested event) {
            System.out.println("audit: " + event.invoiceId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        LimitGuard limitGuard() {
            return new LimitGuard();
        }

        @Bean
        LocalAudit localAudit() {
            return new LocalAudit();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("caller: begin INV-1");
            context.publishEvent(new InvoiceApprovalRequested("INV-1", 500));
            System.out.println("caller: completed INV-1");

            System.out.println("caller: begin INV-2");
            try {
                context.publishEvent(new InvoiceApprovalRequested("INV-2", 1_200));
                System.out.println("caller: completed INV-2");
            } catch (IllegalArgumentException ex) {
                System.out.println("caller: rejected INV-2: " + ex.getMessage());
            }
        }
    }
}
~~~

With **JDK 17+** and **Gradle 8.x**, run inside **sync-event-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program**:

~~~text
caller: begin INV-1
guard: INV-1
audit: INV-1
caller: completed INV-1
caller: begin INV-2
guard: INV-2
caller: rejected INV-2: exceeded demo limit
~~~

Analysis:

- **INV-1**: **@Order(10)** causes guard to be invoked before audit **@Order(20)**. Both return normally; only then does **caller: completed INV-1** appear.
- **INV-2**: guard throws **IllegalArgumentException**. The exception propagates back to **publishEvent(...)** and is caught in **main**. **LocalAudit** is not invoked for INV-2 under this default configuration.
- **@Order** expresses invocation order; **@Order** does not replace a transaction and does not confirm business success on its own.
- The demo program **does not use transactions**. The audit line is **System.out.println(...)**, which does not demonstrate rollback; if a listener had written to an external system before the exception occurred, that action would not be automatically undone.

The immediate sign of synchronous execution in the example is **caller: completed INV-1** appearing **after** both listener lines. If you enable **@Async** or change the multicaster to dispatch through an executor, do not keep this conclusion without testing the actual configuration.

## 5. Synchronous Inside an Active Transaction: What to Verify

A common pattern is a service publishing an event inside a transaction while a listener performs a mandatory operation on the same business data.

The following example **only illustrates integration**; the classes **Order**, **OrderRepository**, **AuditRepository**, and transaction manager configuration must be supplied in a real project, so this snippet is not a standalone program like section 4:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void approve(long id) {
        Order order = orders.loadForApproval(id);
        order.approve();
        events.publishEvent(new OrderApproved(id));
        // If a mandatory listener throws RuntimeException outward,
        // the default transaction interceptor marks rollback.
    }
}

public record OrderApproved(long orderId) {}

@Component
public class RequiredAuditListener {
    private final AuditRepository audit;

    public RequiredAuditListener(AuditRepository audit) {
        this.audit = audit;
    }

    @EventListener
    public void on(OrderApproved event) {
        audit.insertRequiredEntry(event.orderId());
    }
}
~~~

Key imports: **org.springframework.stereotype.Service**, **org.springframework.stereotype.Component**, **org.springframework.transaction.annotation.Transactional**, **org.springframework.context.ApplicationEventPublisher**, and **org.springframework.context.event.EventListener**.

### 5.1. When Is It the Same Transaction?

If **approve(...)** actually goes through the Spring transaction proxy, the transaction manager manages the right data source, and the audit repository participates in the current transaction, then Order and audit data can commit/roll back together. If the listener throws a RuntimeException and the exception crosses the **@Transactional** boundary, by default the transaction rolls back.

Cases that alter this conclusion:

- **approve(...)** is called via self-invocation on the same instance, causing the **@Transactional** proxy to be bypassed under default proxy mode.
- The service handles/swallows the exception before exiting the transaction boundary; the transaction may commit if not marked rollback-only.
- The listener opens **REQUIRES_NEW** or uses a different data source/transaction manager, so it is no longer in the same transaction.
- The listener runs on another thread via **@Async** or an executor; thread-bound transactions do not transfer automatically.
- The listener interacts with email, message brokers, or non-DB APIs without a transaction-coordination protocol; a DB rollback cannot retract side effects that already occurred.

**Transaction takeaway:** synchronous events are a mechanism *keeping callbacks in the execution thread*; atomicity must be ensured by actual transactions and storage architecture.

### 5.2. Differences Between @EventListener and @TransactionalEventListener

| Listener type | When it operates | Relationship to commit outcome |
| --- | --- | --- |
| Synchronous **@EventListener** | Typically runs immediately when **publishEvent(...)** dispatches the event | Can run *before commit* and can roll back the transaction if errors propagate |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Registers handling tied to the pre-commit stage | Used for work that must happen before commit; errors can prevent commit from succeeding |
| **@TransactionalEventListener(AFTER_COMMIT)** | Callback after a successful commit | Cannot revert an already completed commit back to uncommitted state |
| **@TransactionalEventListener(AFTER_ROLLBACK)** | Callback when the transaction rolls back | Suitable for tracking or handling failure cases |
| **@TransactionalEventListener(AFTER_COMPLETION)** | Callback after transaction completion regardless of outcome | Suitable for cleanup and observing both outcomes |

By default **@TransactionalEventListener** uses the **AFTER_COMMIT** phase. When no transaction is active, this kind of listener **does not run**, unless **fallbackExecution = true** is configured; think carefully before enabling it because it alters the "only after commit" promise.

**Important point:** a transaction-bound callback may run on the synchronous transaction thread yet *not necessarily execute right inside the publishEvent(...) call*. For example, **AFTER_COMMIT** normally waits until the transaction commits later. Thus, you cannot use **@TransactionalEventListener(AFTER_COMMIT)** as a mandatory validation step that must finish **before publishEvent(...) returns**.

If an **AFTER_COMMIT** listener needs to create a new DB record, it should normally call a Spring-managed service with **@Transactional(propagation = Propagation.REQUIRES_NEW)**; do not expect the old transaction to still be able to commit new changes after the completion phase.

## 6. Controlling Ordering and Error Behavior

### 6.1. Invocation Order Does Not Mean a Pipeline with Return Values

With multiple synchronous **@EventListener** methods handling the same event type, **@Order** sets invocation priority: **@Order(10)** runs before **@Order(20)**. If listeners share the same order or declare none, do not build business logic depending on an implicit ordering between them.

**Choose synchronous when** listeners are independent in their inputs yet the caller needs to wait for them to finish and see errors. **Choose direct method calls when** each step needs the return value of the previous step or has a strict business sequence: for example, **reserveStock(...)** must return a reservation ID before **chargePayment(...)**.

### 6.2. Exception Policy Is Part of the Business Contract

In the default **SimpleApplicationEventMulticaster** without an **ErrorHandler**, an exception from a synchronous listener propagates to the publisher and stops the current multicast loop. This fits mandatory listeners, but can be surprising if a listener only performs auxiliary work such as metrics.

You can configure an **ErrorHandler** to log/suppress errors or handle them under another policy; when suppressing exceptions, the publisher will not receive that error. You can also handle auxiliary errors directly inside the listener to avoid breaking the main operation. Before doing so, define precisely which listeners *are allowed to fail while the main operation still succeeds*.

Be cautious with both **Error** and RuntimeException: catching every **Throwable** just to keep going can mask critical failures. Catch recoverable business and infrastructure errors according to an explicit policy.

### 6.3. A Slow Listener Slows Down the Caller

Suppose three synchronous listeners run sequentially during a request, taking roughly 20 ms, 30 ms, and 50 ms each. Listener time alone adds around 100 ms to request latency, before DB, serialization, and network time. If a listener waits 10 seconds on an external API, the publisher can be blocked accordingly; transactions and locks can be held too long.

Therefore, even when synchronous execution is the right business choice, still:

- Measure p95/p99 latency of the overall publish flow and each listener.
- Bound I/O, timeouts, and synchronous retry counts.
- Avoid holding DB locks while performing long network operations.
- Limit nested event publishing to prevent deep call stacks or event loops.
- Set up logging, trace/correlation IDs, and metrics to pinpoint slow listeners.
- If latency becomes unacceptable, consider changing the reaction mechanism while preserving the original business guarantees.

## 7. Three Real-World Scenarios

### Scenario A — Pre-Save Validation: Should Be Synchronous, Usually Direct Service Call

A user submits a request to transfer resource ownership. The system must verify roles and conditions before writing to the DB.

~~~text
Controller -> ApplicationService
              -> permissionService.requireTransferAllowed(...)
              -> repository.transfer(...)
              -> publishEvent(TransferCompleted)
              -> return success
~~~

Here validation must be synchronous. However, because it is a mandatory precondition, a direct service call communicates intent much more clearly than a **TransferRequested** event whose listeners might be added or removed and silently change the decision. The **TransferCompleted** event informs other components that the change already happened.

### Scenario B — Mandatory Audit in the Same DB Transaction: Synchronous Fits Well

An operation changing an approval level must write an audit record in the same transaction. If writing the audit record fails, the entire change must roll back.

~~~text
@Transactional service
  -> update record
  -> publishEvent(LevelChanged)
     -> @EventListener DB audit (synchronous)
  -> commit Order + audit in the same DB transaction
~~~

This is where synchronous events make sense if the audit listener is explicitly managed and joins the transaction properly. For business flows with extremely strict consistency requirements or where auditing is treated as a data invariant, calling **auditService.record(...)** directly inside the transaction is also a good choice that keeps dependencies obvious when reading code.

### Scenario C — Sending Email or Updating Other Systems: Usually Should Not Stay Synchronous

Approving an invoice has committed and an email needs to be sent. A slow email server or transient error should not fail the approval process mysteriously. Use **@TransactionalEventListener(AFTER_COMMIT)** so emails are not sent for rolled-back transactions. If sending is only best-effort, offload processing to a monitored executor; if **eventual guaranteed delivery** is required, use an outbox and a worker with retries and idempotency.

Note: **@Async** does not create a durable queue. The JVM could crash right after commit before the task executes; a request that already returned success can still lose the email without an outbox or equivalent guarantee.

## 8. What to Test When Choosing Synchronous

Do not test only "did the listener run"—verify the **synchronous contract**:

1. **Thread and blocking:** use a test listener with a synchronization gate (such as CountDownLatch) to confirm the publisher does not return before the listener finishes; avoid using fixed sleeps as proof.
2. **Error behavior:** have a mandatory listener throw RuntimeException; verify the caller receives the exact error and later-ordered listeners are not called in the default setup.
3. **Ordering:** attach different **@Order** values and record an invocation list; assert the expected order rather than relying on bean declaration order.
4. **Transaction rollback:** write an integration test with a real/realistic transaction manager and database; have the listener write to the same DB and intentionally throw RuntimeException; verify both primary data and audit roll back when configured properly.
5. **Misplaced error catching:** test the case where the service catches the exception without rethrowing; verify rollback-only handling or the intended business contract.
6. **Multicaster configuration:** verify presence or absence of a global executor, **ErrorHandler**, or **@Async**; any of these changes can flip expectations.
7. **No transaction:** for **@TransactionalEventListener**, verify the listener does not run without a transaction unless fallback is intentionally enabled.
8. **Latency:** measure slow listeners, timeout bounds, and deadlock avoidance when holding locks in the same transaction.

A unit test calling **on(event)** directly only tests the method's logic; it **does not prove** dispatch behavior, **@Order**, **@Async**, transaction propagation, or exception propagation back to the publisher. Those guarantees require testing through **ApplicationContext** and an appropriate transaction environment.

## 9. Common Mistakes

- **Assuming Spring Application Events are always synchronous:** it is the common default, but can be changed by the multicaster or async annotations.
- **Moving mandatory checks to @Async:** the caller can return success before validation finishes.
- **Equating publishEvent(...) returning with a database commit:** when called inside **@Transactional**, commit typically happens after the business method finishes.
- **Assuming a transaction exists just because of running on the same thread:** there must be an actual transaction, transaction manager, and participating resources.
- **Swallowing mandatory exceptions with try/catch or ErrorHandler:** the system loses failure signals and can commit erroneously.
- **Overusing @Order instead of orchestration:** listener order does not create return values, transaction boundaries, or explicit mandatory contracts like direct service calls.
- **Running external I/O inside a synchronous transaction:** increases latency, lock duration, and hard-to-recover error risks.
- **Using @TransactionalEventListener(AFTER_COMMIT) for immediate validation:** the callback belongs to the commit phase, not when the event is published.
- **Confusing synchronous with durable:** in-memory events do not survive a JVM crash, whether before or after commit.
- **Assuming DB rollback undoes sending an email or HTTP call:** those side effects need compensation, idempotency, or an outbox.

## 10. Pre-Implementation Decision Checklist

Answer each question in sequence:

1. **Does the caller genuinely need to know the listener's result right away?** If yes, prefer synchronous. If not, determine a safe time to do it later.
2. **Must a failure in the listener fail the primary operation?** If yes, keep exception/rollback propagation clear; consider calling a service directly when it is core validation.
3. **Does the task need to share the same DB transaction?** Verify the active transaction, propagation, data source, and exception types.
4. **Is the task fast and time-bounded?** If not, assess impact on request threads and transactions/locks.
5. **Is the secondary outcome only valid after commit?** If yes, use AFTER_COMMIT instead of an immediate regular listener.
6. **Must the work finish immediately or just eventually for certain?** If it can finish later yet must never be lost, use durable storage + retries + idempotency.
7. **Is the active configuration truly synchronous?** Check **@Async**, **@EnableAsync**, **applicationEventMulticaster** configuration, executors, and **ErrorHandler**.
8. **Have you tested end-to-end from publisher to listener and transaction?** Verify order, errors, rollbacks, and timing with integration tests.

**Quick rule of thumb:** Choose synchronous listeners when reactions are fast, local, and their outcome or error must be known **before the publisher proceeds**. For core business preconditions, calling a service directly usually expresses responsibility more clearly. Use post-commit listeners for commit-dependent side effects; use an outbox/queue for work that must be durable.

### Official References

- Spring Framework Reference, *Application Events, Asynchronous Listeners and Ordering Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.2.9 Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc, *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference, *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
