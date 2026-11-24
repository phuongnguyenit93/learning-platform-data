# Synchronization Registration Timing in Spring Framework Application Events

## 1. What is transaction synchronization and when does "registration" happen?

**Transaction synchronization** is a mechanism allowing a callback to participate in the lifecycle of a Spring-managed transaction. Callbacks can be invoked at milestones such as before commit, after commit, after rollback, or after transaction completion. In Spring Application Events, **@TransactionalEventListener** relies on this mechanism to bind **a single event publication** to the **active transaction at the moment the event is published**.

The core point: **the event's callback is registered when `publishEvent(...)` dispatches the event inside a suitable transaction; it is executed later at the selected transaction phase**. Declaring the annotation does not pre-register callbacks for all future transactions; starting a transaction does not yet create a callback for an event that has not been published.

For example: a Service starts a transaction, saves an order, calls **publisher.publishEvent(new OrderCreated(...))**, and returns. The **@TransactionalEventListener(phase = AFTER_COMMIT)** listener is registered with the transaction at publication time; the listener method runs only if the transaction commits successfully. If the transaction rolls back, the AFTER_COMMIT method does not run.

When registration timing is misunderstood, systems easily suffer from bugs: publishing an event before opening a transaction; publishing from an **@Async** thread without carrying the transaction context; publishing after commit expecting a callback anyway; or enabling **fallbackExecution** without realizing the listener can run immediately outside a transaction.

## 2. Distinguishing three moments often grouped together as "registration"

| Moment | What Spring does | Result |
| --- | --- | --- |
| **ApplicationContext** initialization | Spring scans **@EventListener**/**@TransactionalEventListener** methods and builds the application listener adapter/registry | Knows which method receives which event type; **does not yet register synchronization for a specific event** |
| Transaction manager creates or joins a transaction | Activates transaction synchronization in the appropriate context and manages the callback list | Ready to accept registrations, but **has no callback for an unpublished event yet** |
| **publishEvent(event)** inside an active transaction | The transactional listener adapter receives the event and binds it to the current transaction via synchronization | The callback for that **specific publication** is registered to run at the designated phase |

With a regular **@EventListener**, the method is usually invoked immediately when the multicaster dispatches the event (in the default synchronous configuration). With **@TransactionalEventListener**, the adapter receives the event at publish time but can **defer the handler method** until commit/rollback. Therefore, logging "event published" and "listener executed" requires two distinct milestones.

Within one transaction, the same event type can be published multiple times. Each publication can create a separate callback: the annotation does not automatically deduplicate events, does not guarantee exactly-once processing, and does not persist events durably on disk.

## 3. Registration and execution timeline

Assume **PlatformTransactionManager** is used with a thread-bound transaction:

~~~text
T0  Enter @Transactional or TransactionTemplate
    -> transaction manager starts/joins transaction;
       enables corresponding synchronization mechanism
    |
T1  Service updates data
    |
T2  publisher.publishEvent(OrderCreated)
    -> @TransactionalEventListener adapter receives event
    -> checks suitable transaction/synchronization
    -> REGISTERS event callback into the current transaction
    |
T3  publishEvent(...) returns
    -> AFTER_COMMIT listener has not run yet
    |
T4  Transaction prepares to commit
    -> runs registered BEFORE_COMMIT listeners
    |
T5  Physical commit or rollback
    |                            |
    | commit succeeds            | rollback
    v                            v
T6  AFTER_COMMIT                AFTER_ROLLBACK
    |
T7  AFTER_COMPLETION (both cases)
    |
T8  Clean up transaction and return result to caller
~~~

This is a logical sequence diagram. Spring has multiple internal steps to dispatch callbacks; specifically, **AFTER_COMMIT** of a transactional event listener is triggered during the transaction completion procedure. Point to remember: **T2 is registration, whereas T4/T6/T7 are execution**, and each phase runs only if its corresponding transaction outcome condition is met.

If the service called **publishEvent(...)** inside a transaction and the transaction later rolls back, the **AFTER_COMMIT** callback will not process that event. If an event is published when no suitable transaction exists, the listener by default does not automatically "wait" for a future transaction.

### The phases of @TransactionalEventListener

| Phase | When does the listener method run? | Appropriate uses |
| --- | --- | --- |
| **BEFORE_COMMIT** | In the pre-commit phase, while preparing to commit | Work that must finish before commit; errors can affect the commit |
| **AFTER_COMMIT** *(default)* | After the transaction commits successfully | Emails/notifications that depend on committed data |
| **AFTER_ROLLBACK** | When the transaction rolls back | Failure tracking, cleanup, or controlled compensation |
| **AFTER_COMPLETION** | When the transaction finishes, whether successful or failed | Logging, metrics, releasing resources |

**BEFORE_COMMIT** runs later than **publishEvent(...)**; do not use it for validation that must finish before the publisher returns. If a condition check immediately decides whether the main operation should proceed, use a synchronous service call or a synchronous **@EventListener** with a clear exception contract.

**AFTER_COMMIT** does not roll back an already-committed transaction if the listener method fails. External side effects require their own retry and idempotency policies.

## 4. Registration conditions in a thread-bound transaction

Spring provides **org.springframework.transaction.support.TransactionSynchronizationManager**. Two states are frequently mentioned:

- **isSynchronizationActive()**: whether the current thread has transaction synchronization active.
- **isActualTransactionActive()**: whether the current thread is actually associated with a real transaction.

For the **@TransactionalEventListener** adapter paired with **PlatformTransactionManager**, Spring needs both active synchronization **and** an active actual transaction to register an event callback with the current transaction.

These two conditions are not synonymous. With certain propagation settings such as **SUPPORTS** without a physical transaction, synchronization can be active even when an actual transaction is not. Hence, being able to call `registerSynchronization` does not necessarily mean there will be a physical commit for an `AFTER_COMMIT` listener to wait on.

You can check the state in business code for diagnostics:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean sync = TransactionSynchronizationManager.isSynchronizationActive();
boolean actual = TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("sync=" + sync + ", actualTx=" + actual);
~~~

This is a **code snippet placed inside a Java method**, not a standalone class. With **TransactionTemplate** creating a real transaction as in the next example, the result inside the transaction callback is **sync=true, actualTx=true**. When running outside any transaction, the values are typically **false/false**.

**Do not manually call** **TransactionSynchronizationManager.initSynchronization()** or **setActualTransactionActive(true)** in a service to try to force listeners to run. The transaction manager must be responsible for starting, committing/rolling back, and cleaning up transactions; toggling flags manually does not create a database transaction.

## 5. Standalone runnable Java 17+ demo: outside transaction, commit, rollback

The example uses **Spring Framework 6.2.9**, **H2 2.3.232**, **Java 17+**, and **Gradle 8.x**. It uses **DataSourceTransactionManager** for a real JDBC transaction, **TransactionTemplate** to control start/end timing, and three **@TransactionalEventListener** methods to observe phases.

Structure:

~~~text
tx-sync-timing/
  build.gradle
  src/main/java/demo/TransactionTimingDemo.java
~~~

Create **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionTimingDemo'
}
~~~

Create **src/main/java/demo/TransactionTimingDemo.java**:

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionTimingDemo {

    public record WorkCreated(String id) {}

    public static class PhaseListeners {
        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(WorkCreated event) {
            System.out.println("listener BEFORE_COMMIT: " + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(WorkCreated event) {
            System.out.println("listener AFTER_COMMIT: " + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(WorkCreated event) {
            System.out.println("listener AFTER_ROLLBACK: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:sync_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(PlatformTransactionManager tm) {
            return new TransactionTemplate(tm);
        }

        @Bean
        PhaseListeners phaseListeners() {
            return new PhaseListeners();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);

            System.out.println("outside: publish");
            context.publishEvent(new WorkCreated("OUT"));
            System.out.println("outside: returned");

            tx.executeWithoutResult(status -> {
                System.out.println("commit: sync="
                        + TransactionSynchronizationManager.isSynchronizationActive()
                        + ", actualTx="
                        + TransactionSynchronizationManager.isActualTransactionActive());
                context.publishEvent(new WorkCreated("OK"));
                System.out.println("commit: publish returned");
            });
            System.out.println("commit: transaction returned");

            tx.executeWithoutResult(status -> {
                System.out.println("rollback: publish");
                context.publishEvent(new WorkCreated("FAIL"));
                System.out.println("rollback: publish returned");
                status.setRollbackOnly();
            });
            System.out.println("rollback: transaction returned");
        }
    }
}
~~~

Run from the **tx-sync-timing** directory after installing JDK 17+ and Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program**:

~~~text
outside: publish
outside: returned
commit: sync=true, actualTx=true
commit: publish returned
listener BEFORE_COMMIT: OK
listener AFTER_COMMIT: OK
commit: transaction returned
rollback: publish
rollback: publish returned
listener AFTER_ROLLBACK: FAIL
rollback: transaction returned
~~~

Explanation:

1. **OUT** is published when there is no transaction; the three listeners have the default **fallbackExecution=false**, so no listener line carries **OUT**.
2. When **TransactionTemplate** opens a transaction for **OK**, synchronization and actual transaction are both active. Spring registers the callbacks as soon as **publishEvent(...)** is called, yet **commit: publish returned** still appears **before** the callbacks.
3. When the **TransactionTemplate** lambda finishes normally, Spring runs **BEFORE_COMMIT**, commits, and runs **AFTER_COMMIT**. Only then does the **TransactionTemplate** call return and print **commit: transaction returned**.
4. For **FAIL**, **status.setRollbackOnly()** leads to rollback. **AFTER_ROLLBACK** handles that event; **BEFORE_COMMIT** and **AFTER_COMMIT** are not invoked for **FAIL**.
5. The example creates no SQL records, sends no emails, and does not prove durable message delivery; H2 simply provides a real transaction manager to observe the lifecycle. If you need to verify data commit/rollback, add JDBC operations and assertions in an integration test.

The output clearly separates **already registered at publish time** from **executed only after commit/rollback**.

## 6. Where to place the publish call?

### 6.1. Publishing before the transaction

~~~java
publisher.publishEvent(new WorkCreated("EARLY"));
tx.executeWithoutResult(status -> {
    // A new transaction starts inside this callback.
});
~~~

The **EARLY** event is not automatically moved into the transaction opened afterward. With a default **@TransactionalEventListener**, no callback is registered and the event is ignored for transactional listeners.

**Fix:** publish inside the transaction you want to bind to, after the transaction has actually opened.

### 6.2. Publishing inside the transaction

~~~java
tx.executeWithoutResult(status -> {
    // Transaction is active.
    publisher.publishEvent(new WorkCreated("IN_TX"));
    // Callback is registered; AFTER_COMMIT has not run yet.
});
~~~

This is the common placement. The callback binds to the **transaction seen by the publication context**, not a transaction guessed from a method name or event type.

If a service is called with **@Transactional** via a proxy, the transaction is usually created before entering the method body. However, in default proxy mode, **self-invocation** (one method on the same bean calling another method on `this`) usually does not trigger the **@Transactional** interceptor. In that case, a publish call that appears to be "inside an @Transactional method" actually has no active transaction.

### 6.3. Publishing after the transaction

~~~java
tx.executeWithoutResult(status -> {
    // Transaction ends when this callback returns.
});
publisher.publishEvent(new WorkCreated("LATE"));
~~~

For **LATE**, the old transaction has already ended; Spring cannot go back to a past AFTER_COMMIT phase. If you want to handle this event immediately without depending on a transaction, a regular **@EventListener** may be appropriate. If you need AFTER_COMMIT of a transaction, you must publish **inside that transaction**, or create a new properly scoped transaction.

### 6.4. fallbackExecution changes the execution path

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void on(WorkCreated event) {
    // Handled even when no suitable transaction exists.
}
~~~

This is an **illustrative method snippet** that must be placed in a Spring bean with imports added for real use. If no suitable transaction exists and **fallbackExecution=true**, Spring can invoke the listener immediately on the fallback branch; no commit is waited for. Therefore, do not enable fallback and continue claiming every execution happens "after commit".

## 7. Manual registration via TransactionSynchronizationManager

Besides **@TransactionalEventListener**, infrastructure code can register callbacks directly:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public void registerWorkAfterCommit(Runnable work) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()
            || !TransactionSynchronizationManager.isActualTransactionActive()) {
        throw new IllegalStateException("Active transaction required");
    }

    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    work.run();
                }
            });
}
~~~

**registerSynchronization(...)** only performs registration; it does not run **work.run()** at the moment of the call. The **afterCommit()** callback is invoked by the transaction manager when the transaction commits successfully. This API throws **IllegalStateException** if synchronization is not active; the example also checks actual transaction because the method's contract requires a real transaction.

Place this code in a class called when a transaction is already open; the snippet above only illustrates the method, not a standalone program. If the transaction manager needs cleanup or rollback, it retains control over lifecycle coordination; the application must not open/close synchronization manually via ThreadLocal flags.

A **TransactionSynchronization** has callbacks such as **beforeCommit**, **beforeCompletion**, **afterCommit**, and **afterCompletion**. Do not register callbacks too late, after the target phase has already passed. Registering inside a post-completion callback will not make the transaction re-execute that phase.

## 8. Cases that change the registration context

### 8.1. @Async and another thread

For transactions managed by **PlatformTransactionManager**, the context is typically held in a **ThreadLocal**. If the event-publishing method runs on an executor thread:

~~~java
@Async("executor")
public void publishLater(WorkCreated event) {
    publisher.publishEvent(event);
}
~~~

the new thread normally does not have the caller's transaction. By default, **@TransactionalEventListener** will not register onto the original thread's transaction. Do not treat passing the event object as passing the transaction context.

**Distinction:** placing **@Async** on the *publishing* method affects the **registration moment**; placing **@Async** on the transactional listener method can keep registration on the publishing thread and only offload post-phase business handling to the executor. Running asynchronously after commit still does not inherit the old transaction; if DB writes are needed, create an appropriate new transaction.

### 8.2. REQUIRES_NEW

If an outer transaction is running and a service starts a **REQUIRES_NEW** transaction and publishes an event inside the new transaction, the callback binds to the **new transaction**. An **AFTER_COMMIT** listener for that event can run as soon as the new transaction commits, **before** the outer transaction finishes. Do not assume it always waits for the outer transaction.

Logical example:

~~~text
outer transaction starts
  -> inner REQUIRES_NEW starts
       -> publishEvent(E)
       -> inner commits
       -> E.AFTER_COMMIT is invoked
  -> outer transaction continues, may roll back later
~~~

If business logic requires notifying only when **all** outer changes have committed, publish the event in the appropriate transaction scope.

### 8.3. NESTED/savepoint

**NESTED** may use a savepoint inside an outer transaction. Rolling back to a savepoint does not necessarily end the outer transaction. Do not assume **AFTER_ROLLBACK** on a transactional event listener will run for each savepoint rollback; callbacks typically bind to the main transaction's lifecycle. If precise savepoint handling is needed, choose a supporting API and test specifically for your transaction manager.

### 8.4. Reactive transactions

Since Spring Framework 6.1, **@TransactionalEventListener** supports thread-bound transactions from **PlatformTransactionManager** and reactive transactions from **ReactiveTransactionManager**. Reactive transactions use **Reactor Context**, rather than relying on ThreadLocal like the JDBC example.

With reactive publication, the transaction context must be placed into the **event's source** per Spring's supported mechanism; **TransactionalEventPublisher** helps publish events with the reactive transaction context. Do not use the ThreadLocal checks from the imperative example to conclude whether a reactive transaction exists.

## 9. What happens after registration

### 9.1. An AFTER_COMMIT callback does not roll back the prior commit

When an **AFTER_COMMIT** listener is called, the main transaction has already committed. If sending an email fails, the committed transaction does not automatically roll back. If the listener needs to write a new DB record, call a Spring-managed service with **@Transactional(propagation = Propagation.REQUIRES_NEW)** to get a new commit; do not rely on old transaction resources that might temporarily remain bound to the thread after commit.

### 9.2. In-memory registration does not guarantee eventual delivery

Registering a callback does not mean the event is durably persisted. The JVM can crash after commit but before finishing an async callback. If notifications must not be lost, use a **transactional outbox**: write an outbox record in the same DB transaction as the business operation, then have a worker/queue pick up the record, retry with backoff, process idempotently, and record completion status.

### 9.3. How ErrorHandler/transaction manager affect errors

Do not assume every exception in every phase has the same rollback capability. A **BEFORE_COMMIT** error can cause the commit to fail if propagated through the proper mechanism; an **AFTER_COMMIT** error occurs after commit and cannot reverse the committed outcome. Depending on the callback mechanism, errors may be logged during completion. Separate logging, metrics, tracing, and retry policies are required for post-transaction handling.

## 10. Checklist for testing registration timing

1. **Outside transaction:** Publish with **fallbackExecution=false** and verify the transactional listener is not called.
2. **Inside transaction before commit:** Publish and verify the AFTER_COMMIT method has not run immediately inside **publishEvent(...)**; it runs after commit.
3. **Rollback:** Publish inside a transaction then roll back; AFTER_COMMIT does not run, AFTER_ROLLBACK runs.
4. **BEFORE_COMMIT:** Verify the callback occurs in the pre-commit phase; mandatory errors can be observed at the commit boundary.
5. **Another thread:** Publish with **@Async**, observe the transaction context on that thread, and verify the desired policy.
6. **REQUIRES_NEW:** Publish the event inside a new transaction and verify the callback binds to the new transaction.
7. **SUPPORTS without real transaction:** Do not infer outcomes solely from **isSynchronizationActive()**.
8. **fallbackExecution=true:** Verify the out-of-transaction execution branch and that its timing differs from the transactional branch.
9. **Infrastructure failure scenarios:** Test executor task rejection or listener exceptions; verify error reporting and retry policy.
10. **Transaction proxy:** Verify the service is actually called through a Spring proxy or **TransactionTemplate**, avoiding self-invocation that renders **@Transactional** ineffective.

Tests should go through **ApplicationContext + publisher + transaction manager**. Calling **listener.on(event)** directly only tests the method body and **does not prove** Spring registered synchronization or dispatched the right phase.

## 11. Mental-model pitfalls and fixes

| Misconception | Consequence | What to do |
| --- | --- | --- |
| "Having the annotation means registered for all transactions" | Fails to distinguish listener registry from transaction callback | Remember registration for an event is decided **at publish time** |
| "An event published before a transaction will wait for commit" | Transactional listener skips the event by default | Publish inside an already-open transaction |
| "publishEvent returning means AFTER_COMMIT already ran" | Side effects are observed too early | Wait for the actual commit phase or redesign output |
| "An @Async thread still has the request's transaction" | Callback is not bound to the right transaction | Keep publication within the transaction's thread/context |
| "isSynchronizationActive is enough" | May confuse SUPPORTS with having a physical transaction | Also check actual transaction when needed |
| "fallbackExecution still only runs after commit" | Method can run immediately outside a transaction | Enable fallback only when business semantics allow |
| "An AFTER_COMMIT error can roll back the transaction" | Commit already happened | Handle post-commit with appropriate retry/compensation |
| "REQUIRES_NEW waits for the outer transaction" | Callback can run before outer commit | Bind events to the right transaction scope |
| "Callback registered means the event cannot be lost" | JVM/queue failure can lose work | Use a durable outbox/queue and idempotency |

**Rule to remember:** The transaction manager establishes the synchronization environment; only when an event is published inside that environment is the **@TransactionalEventListener** callback registered for the corresponding transaction; **TransactionPhase** then determines when the listener actually runs. These three milestones must be designed and tested independently.

### Official documentation

- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2.9 Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2.9 Javadoc, *TransactionSynchronizationManager*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework 6.2.9 Javadoc, *TransactionSynchronization*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework 6.2.9 Javadoc, *TransactionalApplicationListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
