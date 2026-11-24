# Separating Required and Auxiliary Listeners in Spring Application Events

## 1. Problem and Objective

A business event can trigger multiple tasks. For example, when an order is confirmed, the system must check validity rules / update state consistently, and at the same time may send notifications, update statistics, and record analytics data. Those tasks should not share the same failure policy.

- **Required (critical/required) listener:** the task's outcome is a condition for the main operation to be considered successful. If it fails, the main flow must know and usually must stop or roll back the transaction. Example: checking missing business rules before confirming an order.
- **Auxiliary (auxiliary/best-effort) listener:** adds external side effects or serves observability, and does not determine the validity of the main operation. Example: sending emails, recording metrics, or updating a rebuildable cache. Errors must be logged and handled under a separate policy.
- **Eventual but required task:** does not need to finish before the main response, yet *must eventually execute*. This category needs a durable mechanism such as a transactional outbox and a queue with retries, rather than merely labeling it "auxiliary" and using an in-memory asynchronous thread.

The goal of this separation is to clearly establish: **who has the authority to fail the main operation, when a listener is invoked, when a task actually completes, and what happens when a transaction rolls back**.

## 2. Spring Foundations: Invocation Order Differs from Completion Order

Spring publishes events inside an application using **ApplicationEventPublisher.publishEvent(...)**. Beans with **@EventListener** methods receive matching event types. With the default **SimpleApplicationEventMulticaster**, regular listeners run **synchronously on the event-publishing thread**. If a synchronous listener throws a RuntimeException and there is no custom error-handling mechanism, the error propagates to the publisher and dispatching of remaining listeners stops there.

**@Order(n)** controls the *invocation* order of listeners for the same event in the multicaster: smaller numbers take priority first (for example, 10 before 100). You should not rely on bean registration order or on an arbitrary order among listeners with the same order. **@Order does not create a transaction, does not force all tasks to succeed, and does not manage retries on its own.**

**@Async** (when **@EnableAsync** is configured) makes a listener method run on an executor: the publisher usually only needs to schedule the task and move on. When using **@Order(10)** for a synchronous required listener and **@Order(100)** for an **@Async** auxiliary listener, the default multicaster finishes invoking the required listener before *scheduling* the auxiliary listener. This **does not** guarantee that the auxiliary task completes after all other work, or that auxiliary results appear in order across multiple events.

| Aspect | Synchronous Required | Asynchronous Auxiliary |
| --- | --- | --- |
| Role | Protects correctness of the main operation | Notifications, analytics, recoverable updates |
| Timing | Before the publisher returns, if dispatched | Can continue after the publisher returns |
| RuntimeException errors | Propagated to publisher under default configuration | Not propagated directly to publisher; requires logging, monitoring, retries |
| Transaction on publishing thread | Can participate in the open transaction | Does not automatically inherit transaction/thread context |
| @Order | Helps define synchronous listener invocation order | Only helps define dispatch/scheduling order; does not guarantee completion order |
| Durability | Depends on transaction and where side effects happen | Work is lost if the process stops or task has not been persisted durably |

If **applicationEventMulticaster** is configured with an asynchronous executor for all listeners, the assumption "required runs first, errors return to publisher" may no longer hold. For critical invariants, keep required listeners synchronous or invoke the required logic directly in the service. Do not put **@Async** on a required listener.

## 3. Processing Flow and Failure Policy

~~~text
publisher.publishEvent(OrderAccepted)
        |
        v
@EventListener @Order(10): REQUIRED, synchronous
        |-- error --> exception to publisher, stop further dispatch
        |
        | success
        v
@EventListener @Order(100) @Async: AUXILIARY
        |-- scheduled on executor --> publisher can continue
                                      |
                                      +--> auxiliary errors logged/retried separately
~~~

In the model above, the auxiliary listener is *scheduled* after the required listener returns successfully. If the auxiliary listener itself raises an error, that error must not be turned into "invalid order". If submitting the task to the executor itself is rejected (for example, queue full), that can still be an error at dispatch time; you must establish an explicit overload policy and monitor submission errors.

**Responsibility boundaries should be defined before writing code:**

1. Validation rules, mandatory checks, and consistent state updates: handle synchronously in the business flow and corresponding transaction.
2. Sending notifications only once data has committed: handle after commit using **@TransactionalEventListener(phase = AFTER_COMMIT)**.
3. Auxiliary tasks allowed to fail temporarily: run asynchronously with monitoring, or use a queue system if long-term retries are needed.
4. Non-reversible external side effects (emails/third-party APIs): do not assume a database rollback will undo those side effects.

## 4. Standalone Runnable Java 17+ Example with Spring Framework

The example below uses **Spring Framework 6.2.9**, Java 17, and Gradle. It demonstrates **dispatch order** and exception propagation; *it does not yet use transactions or a database*. One required listener validates the order; an auxiliary listener runs on an executor. The latch is only for demo purposes to wait for the auxiliary log, not a business implementation mechanism.

Structure:

~~~text
event-demo/
  build.gradle
  src/main/java/demo/EventSplitDemo.java
~~~

Contents of **build.gradle**:

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
    mainClass = 'demo.EventSplitDemo'
}
~~~

Contents of **src/main/java/demo/EventSplitDemo.java**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventSplitDemo {
    public record OrderAccepted(String orderId, boolean reject) {}

    public static class DoneSignal {
        final CountDownLatch finished = new CountDownLatch(1);
    }

    public static class RequiredListener {
        @EventListener
        @Order(10)
        public void on(OrderAccepted event) {
            System.out.println("required: " + event.orderId());
            if (event.reject()) {
                throw new IllegalStateException("mandatory check failed");
            }
        }
    }

    public static class AuxiliaryListener {
        private final DoneSignal signal;

        public AuxiliaryListener(DoneSignal signal) {
            this.signal = signal;
        }

        @EventListener
        @Order(100)
        @Async("auxiliaryExecutor")
        public void on(OrderAccepted event) {
            try {
                System.out.println("auxiliary: " + event.orderId());
            } finally {
                signal.finished.countDown();
            }
        }
    }

    @Configuration
    @EnableAsync
    public static class DemoConfig {
        @Bean
        DoneSignal doneSignal() {
            return new DoneSignal();
        }

        @Bean
        RequiredListener requiredListener() {
            return new RequiredListener();
        }

        @Bean
        AuxiliaryListener auxiliaryListener(DoneSignal signal) {
            return new AuxiliaryListener(signal);
        }

        @Bean("auxiliaryExecutor")
        ThreadPoolTaskExecutor auxiliaryExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(100);
            executor.setThreadNamePrefix("aux-");
            executor.initialize();
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            context.publishEvent(new OrderAccepted("ORD-1", false));

            boolean completed = context.getBean(DoneSignal.class)
                    .finished.await(5, TimeUnit.SECONDS);
            if (!completed) {
                throw new IllegalStateException("auxiliary timeout");
            }
            System.out.println("optional-completed=true");

            try {
                context.publishEvent(new OrderAccepted("ORD-2", true));
            } catch (IllegalStateException ex) {
                System.out.println("publisher-caught=" + ex.getMessage());
            }
        }
    }
}
~~~

From the **event-demo** directory, run using Gradle 8.x with JDK 17+ installed:

~~~bash
gradle --console=plain -q run
~~~

Lines printed by the program when the executor processes normally:

~~~text
required: ORD-1
auxiliary: ORD-1
optional-completed=true
required: ORD-2
publisher-caught=mandatory check failed
~~~

Explanation:

- For **ORD-1**, the required listener completes; afterward, the auxiliary listener is scheduled. Main waits on the latch, so the confirmation line appears only after auxiliary has printed its message.
- For **ORD-2**, the required listener throws **IllegalStateException**; the publisher catches the exception. Auxiliary is not dispatched for **ORD-2** because the required listener failed earlier, under the default configuration and the two listeners in this example.
- If you remove the latch, the auxiliary log line may appear before or after the publisher does subsequent work; **@Order(100)** does not turn async into sync.
- If the required listener has already written data outside a transaction, the exception here **does not automatically undo** what was written. To roll back the DB, you need a real transaction and appropriate rollback rules.

## 5. With Transactions: Separating Mandatory Steps from Post-Commit Side Effects

In systems with **@Transactional**, a common risk is publishing an event right while saving the order, and having an auxiliary listener send an email before the transaction commits. If the DB save rolls back, the user may have already received a confirmation email for an order that does not exist.

Preferred design: the service performs the mandatory task within the same transaction; the event announces what occurred and the auxiliary listener runs **AFTER_COMMIT**. The following example is an **architectural illustration snippet**, assuming **OrderRepository**, **OrderRequest**, **OrderPlaced**, **ValidationService**, and appropriate transaction/executor configurations already exist; it is not a standalone program like Section 4.

~~~java
@Service
class OrderService {
    private final ValidationService validation;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderService(ValidationService validation,
                 OrderRepository orders,
                 ApplicationEventPublisher events) {
        this.validation = validation;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void place(OrderRequest request) {
        validation.checkAndReserve(request);   // required, synchronous
        Order saved = orders.save(new Order(request));
        events.publishEvent(new OrderPlaced(saved.getId()));
    }
}

@Component
class OrderNotificationListener {
    @Async("auxiliaryExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        // Send notification; has its own logging, error tracking, and retry policy.
    }
}
~~~

Corresponding imports for the illustrative snippet: **org.springframework.stereotype.Service**, **org.springframework.stereotype.Component**, **org.springframework.context.ApplicationEventPublisher**, **org.springframework.transaction.annotation.Transactional**, **org.springframework.transaction.event.TransactionalEventListener**, **org.springframework.transaction.event.TransactionPhase**, and **org.springframework.scheduling.annotation.Async**.

Milestones to understand accurately:

| Milestone | Meaning for required and auxiliary |
| --- | --- |
| **Inside @Transactional** | Mandatory steps modifying the DB participate in the transaction if using the same transaction manager and an appropriate execution thread. Uncaught RuntimeExceptions normally lead to rollback under Spring's default rules. |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Callback runs before commit; use only when truly needing to bind to this phase. Callback errors can cause the commit to fail. Do not use for hard-to-undo actions like sending emails. |
| **@TransactionalEventListener(AFTER_COMMIT)** | Invoked only after a successful commit. If the transaction rolls back, this listener does not run. This is the common choice for auxiliary side effects. |
| **AFTER_ROLLBACK / AFTER_COMPLETION** | Suitable for cleanup, metrics, or controlled compensation; do not treat as a successful commit. |

**Important note:** **@TransactionalEventListener** defaults to **AFTER_COMMIT** and by default **is not invoked if there is no active transaction**, unless **fallbackExecution = true** is enabled. Do not arbitrarily enable fallback just so "the listener always runs"; doing so can violate the requirement to execute only after commit.

Inside an **AFTER_COMMIT** callback, the main transaction has already committed. If the callback needs to **write to the DB in a new transaction**, call a service through a Spring proxy with **@Transactional(propagation = Propagation.REQUIRES_NEW)** (or an equivalent design), because old transactional resources may still be bound to the thread without another commit occurring. With **@Async**, the secondary thread also does not automatically inherit the event-publishing thread's transaction; you must clearly define the transaction for write operations on that thread.

**No absolute guarantee:** Internal Spring events are not stored durably. Even with AFTER_COMMIT + @Async, the process can crash right after commit yet before the listener handles it. If "must send notification at least once" is a real requirement, write an **outbox record in the same DB transaction** as the order, then have a worker/queue read the outbox, retry, record processing status, and use idempotency keys to avoid duplicate processing.

## 6. Choosing Policies Based on Criticality

| Real Requirement | Appropriate Organization | Error Handling |
| --- | --- | --- |
| Order must not succeed if inventory check fails | Call service synchronously inside transaction; or synchronous required listener with explicit order | Throw error to publisher; roll back when transaction is properly configured |
| Auxiliary statistics/logging without affecting outcome | Independent auxiliary listener, optionally @Async | Log errors, metrics, alerts; retry depending on criticality |
| Send email only when order commits successfully | AFTER_COMMIT; optionally combined with @Async | Email failure does not reverse commit; monitor and retry |
| Must deliver work to another system even if JVM stops | Transactional outbox + queue/worker | Persist durably, retry with backoff, idempotency, dead-letter handling |
| B needs to use A's result immediately | Call A then B sequentially in service; or synchronous ordered listeners when justified | Do not use @Async relying only on @Order |

With multiple required listeners, **@Order(10), @Order(20), ...** expresses invocation order. However, if step B's output depends tightly on A or requires a return value, direct orchestration in a service is usually easier to read, test, and guarantee than event listeners. **@EventListener** is best suited for decoupled reactions, not replacing every business method call.

## 7. Common Design Mistakes

1. **Putting @Async on a required listener:** errors happen on the executor, the publisher assumes success; consistency is broken.
2. **Assuming @Order guarantees completion order:** true for dispatch in a synchronous multicaster, false for when two async tasks finish.
3. **Configuring a global executor on applicationEventMulticaster while forgetting the impact:** regular listeners may stop running on the event-publishing thread and stop sharing transaction context.
4. **Swallowing exceptions in a required listener:** if every error is caught and only logged, the publisher gets no signal to abort the operation.
5. **Letting an optional listener throw synchronous errors before other listeners:** by default, errors can block subsequent listeners; split into separate listeners, assign sensible orders, and handle errors per business requirements.
6. **Sending notifications before commit:** the transaction may roll back after the external email/API has already succeeded.
7. **Using AFTER_COMMIT and expecting further DB writes in the old transaction:** a new transaction must be created when a new commit is genuinely needed.
8. **Treating @Async as a guaranteed delivery system:** an in-memory executor is insufficient during process crashes, overload, or restarts.
9. **Ignoring retries/idempotency:** reprocessing can send duplicate emails or double-count metrics; event keys and deduplication rules are required.
10. **Relying on ThreadLocal in async tasks:** security context, transaction context, MDC, and correlation IDs do not propagate automatically by default; pass needed data in the event or configure controlled context propagation.

## 8. How to Properly Test Ordering and Error Boundaries

- **Required succeeds:** verify required is invoked before dispatching auxiliary; publisher reports no error. Do not use blind sleeps to assert async order.
- **Required fails:** with the default multicaster and required having an earlier order, verify the publisher receives the exception and auxiliary for that event was not dispatched.
- **Auxiliary fails:** verify main business operation still succeeds under the chosen policy, while appropriate logs/metrics and retries occur.
- **Transaction rollback:** publish an event inside a transaction and deliberately roll back; confirm **AFTER_COMMIT** does not run.
- **Transaction commit:** confirm the AFTER_COMMIT listener processes only when the transaction completes successfully.
- **Executor overload / shutdown:** test rejection behavior, observable errors, and recovery mechanisms; do not assume every task is accepted.
- **Retries and duplicate events:** test idempotency with the same **eventId** published twice.

When testing with **@Async**, use **CountDownLatch**, Future, or bounded synchronization mechanisms. When testing transactions, run with a real transaction manager/DB or an appropriate integration test; do not draw conclusions from a unit test that simply calls the listener method directly.

## 9. Guiding Principle

**Required = sits on the success-determining path and must propagate errors explicitly. Auxiliary = isolated from the main outcome yet still has an error-handling policy.** Use **@Order** to express *invocation* order; use **@Async** when delayed completion is acceptable; use **@TransactionalEventListener** to express transaction phases; use **outbox/queue** if durable delivery is required. Do not confuse these four tools with one another.

### Official Documentation

- Spring Framework, *Application Events, Asynchronous Listeners, Ordering Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc, *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
