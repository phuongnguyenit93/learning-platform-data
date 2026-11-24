# @TransactionalEventListener in Spring

## Objectives

After this lesson, you will be able to:

- Explain the role of @TransactionalEventListener in handling transaction-bound events.
- Distinguish between a regular @EventListener and a transaction phase listener.
- Describe the four phases: BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION.
- Understand the default behavior when an event is published outside a transaction and use fallbackExecution properly.
- Know the impact of propagation, nested transactions, and Spring proxies on when a listener executes.
- Handle post-commit database operations using a separate transaction.
- Combine a post-commit listener with an asynchronous worker without assuming the transaction is propagated to another thread.
- Test commit, rollback, and out-of-transaction event scenarios.

## 1. Why Is @TransactionalEventListener Needed?

ApplicationEventPublisher allows a bean to publish an event without knowing which listeners will receive it. With a regular @EventListener, the listener is invoked during event dispatching.

Suppose a service creates an order within a transaction and then publishes OrderCreatedEvent:

~~~java
@Transactional
public void createOrder(String orderId) {
    orderRepository.save(new Order(orderId));
    publisher.publishEvent(new OrderCreatedEvent(orderId));
}
~~~

If a regular listener sends an email as soon as it receives the event, the email may be sent before the transaction commits. Afterward, another operation in the service fails and the transaction rolls back. As a result, an email was sent for an order that does not exist in the database.

@TransactionalEventListener allows binding a listener to a phase in the transaction lifecycle. Instead of processing immediately when the event is dispatched, Spring registers the listener to be invoked at the appropriate phase.

~~~java
@Component
public class OrderListener {

    @TransactionalEventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Committed order: " + event.orderId());
    }
}
~~~

When an event is published within an active transaction, the listener above runs at AFTER_COMMIT by default. If the transaction rolls back, this listener does not run.

The annotation does not create a transaction and does not cause a transaction to commit. It only registers when to invoke the listener based on the transaction containing the event.

## 2. Comparing @EventListener and @TransactionalEventListener

| Characteristic | @EventListener | @TransactionalEventListener |
|---|---|---|
| Invocation time | When the event is dispatched. | According to the phase of the transaction that published the event. |
| Transaction required | No. | Requires an active transaction at publish time by default. |
| Default behavior | Invoked during dispatch. | AFTER_COMMIT. |
| When transaction rolls back | The listener may have already run before rollback. | An AFTER_COMMIT listener does not run. |
| When event is outside a transaction | Still invoked. | Ignored by default; fallbackExecution can be enabled. |
| Purpose | Reacting to events in general. | Reacting based on transaction outcome. |

Use @EventListener when the listener only needs to know that an event occurred and does not depend on whether the transaction containing the event commits or not.

Use @TransactionalEventListener when the side effect must be tied to the transaction outcome. For example, only send an order confirmation after the order data has been committed.

Not every event published from a @Transactional service needs a transactional listener. Determine whether the listener needs to wait for commit/rollback before choosing the annotation.

## 3. The Four Phases of TransactionPhase

The phase attribute accepts a value from the TransactionPhase enum:

| Phase | Timing | Suitable examples |
|---|---|---|
| BEFORE_COMMIT | Right before the transaction commits. | Final validation or writing data that must be in the same transaction. |
| AFTER_COMMIT | After a successful commit; this is the default. | Sending notifications or triggering post-commit tasks. |
| AFTER_ROLLBACK | After the transaction rolls back. | Recording the rollback or starting a compensating workflow. |
| AFTER_COMPLETION | After the transaction ends, whether committed or rolled back. | Cleanup or recording a general completion outcome. |

### 3.1. BEFORE_COMMIT

A BEFORE_COMMIT listener is invoked while the transaction has not yet committed:

~~~java
@Component
public class OrderValidationListener {

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderCreatedEvent event) {
        System.out.println("Validate order: " + event.orderId());
    }
}
~~~

In this phase, the listener can read from or write to the database within the current transaction if the resource and transaction manager allow it. If the listener throws an exception, the commit process can be aborted and the transaction can roll back.

BEFORE_COMMIT is suitable for checks or database updates that must share the same transaction. You should not send emails or call external APIs in this phase because the commit can still fail after the listener completes.

### 3.2. AFTER_COMMIT

AFTER_COMMIT only runs when the transaction commits successfully:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("Notify order: " + event.orderId());
    }
}
~~~

Tasks commonly placed in this phase:

- Sending emails or notifications.
- Refreshing a cache based on saved data.
- Notifying other components within the same application.
- Starting a background task.
- Sending a message to an external system.

If the transaction rolls back, the AFTER_COMMIT listener is not invoked.

AFTER_COMMIT only determines the timing of the callback. It does not automatically create a new transaction and does not persist the callback in a durable queue.

### 3.3. AFTER_ROLLBACK

AFTER_ROLLBACK is invoked after the transaction rolls back:

~~~java
@Component
public class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void recordRollback(OrderCreatedEvent event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

This phase can be used to record failures, update metrics, release prepared resources, or start a compensating workflow.

A rollback listener does not automatically retry the business method. If retries are needed, build a separate retry policy with bounds and idempotency.

If the listener needs to write to the database after a rollback, it should call a service with a new transaction, usually using REQUIRES_NEW.

### 3.4. AFTER_COMPLETION

AFTER_COMPLETION is invoked when the transaction ends, regardless of commit or rollback:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void completed(OrderCreatedEvent event) {
        System.out.println("Transaction completed: " + event.orderId());
    }
}
~~~

This phase is useful for cleanup work or recording that the transaction has ended without needing to distinguish the outcome.

The event-receiving method does not automatically receive a transaction status parameter. If you need to inspect the commit/rollback status in a low-level callback, you can use TransactionSynchronization.afterCompletion(int status).

## 4. Events Published Outside a Transaction

ApplicationEventPublisher.publishEvent does not require a transaction. A scheduler, runner, or background worker can publish an event outside a transaction.

~~~java
@Component
public class ImportJob {

    private final ApplicationEventPublisher publisher;

    public ImportJob(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void finishImport(String batchId) {
        publisher.publishEvent(new ImportCompletedEvent(batchId));
    }
}
~~~

If finishImport does not run within a transaction:

- The event is still published normally.
- A regular @EventListener is still invoked.
- @TransactionalEventListener is not invoked by default because there is no transaction phase to register with.

This situation commonly occurs in CommandLineRunner, ApplicationRunner, scheduled jobs, non-transactional tests, and @Async workers that do not open their own transaction.

The listener not running does not mean the publisher failed. That is the default behavior of a transactional listener.

## 5. fallbackExecution = true

If an event can be published both inside and outside a transaction, and the business logic accepts immediate processing when no transaction exists, fallbackExecution can be enabled:

~~~java
@Component
public class ImportListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
    )
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println("Handle import: " + event.batchId());
    }
}
~~~

Behavior:

- When a transaction exists: the listener is invoked at the selected phase.
- When no transaction exists: the listener is invoked immediately via the fallback mechanism.

fallbackExecution does not open a new transaction, does not create a fake commit, does not wait for a transaction to start in the future, and does not prove that data has been committed.

With AFTER_COMMIT, an event outside a transaction will trigger the listener immediately during dispatch. Only enable fallback if the action has valid meaning in both cases. If the listener must strictly run after an actual commit, keep fallbackExecution at its default of false.

## 6. How Spring Registers Listeners via Transaction Synchronization

When an event is published inside a transaction, Spring registers the listener as a transaction synchronization. The transaction manager will invoke the callback at the corresponding phase.

High-level flow:

~~~text
@Transactional service
        |
        v
Start transaction
        |
        v
Write business data
        |
        v
publishEvent(event)
        |
        v
Register transactional listener
        |
        v
Transaction manager commits or rolls back
        |
        +---- BEFORE_COMMIT
        |
        +---- Commit succeeded ---> AFTER_COMMIT
        |
        +---- Rollback -----------> AFTER_ROLLBACK
        |
        +---- Completion ---------> AFTER_COMPLETION
~~~

ApplicationEventPublisher does not need to know which listener selects which phase. Spring holds the event information and invokes the listener at the corresponding time.

In regular applications, @TransactionalEventListener should be used. The low-level TransactionSynchronization API is only necessary when you want to register a custom transaction callback.

## 7. Impact of Propagation

@TransactionalEventListener binds to the transaction active at the time of publishEvent. Therefore, transaction propagation can change which transaction the event is bound to.

| Propagation | Behavior | Impact |
|---|---|---|
| REQUIRED | Joins the current transaction or creates a new one if none exists. | The listener binds to the joined or created transaction. |
| REQUIRES_NEW | Suspends the current transaction and creates a new transaction. | The inner transaction's listener can run when the inner transaction commits, even while the outer transaction continues. |
| SUPPORTS | Joins a transaction if one exists; otherwise runs non-transactionally. | Without a transaction, the listener is skipped by default. |
| NOT_SUPPORTED | Suspends the current transaction and runs non-transactionally. | An event published in this block has no phase to wait for. |
| MANDATORY | Requires an active current transaction. | Throws an exception if there is no transaction. |
| NEVER | Requires no active transaction. | There is no transaction for the listener to bind to. |

For example, a REQUIRES_NEW method publishes an event and then commits its own transaction. The AFTER_COMMIT listener for that event can run right after the inner transaction commits, even though the outer transaction is still continuing and might roll back later.

Do not assume that rolling back the outer transaction will reverse data or side effects bound to a committed REQUIRES_NEW transaction.

With NESTED using a savepoint, completing a savepoint does not mean the outer physical transaction has committed. The listener typically remains bound to the outer transaction and waits for the completion outcome of that transaction.

## 8. Writing to the Database in an AFTER_COMMIT Listener

After commit, the original transaction has already completed. During the post-commit callback, some transaction resources may still be held until cleanup finishes. If the listener writes to the database synchronously, that operation might access the old resource without being committed as a new transaction.

Call a separate service with REQUIRES_NEW propagation:

~~~java
@Service
public class AuditWriter {

    private final JdbcTemplate jdbcTemplate;

    public AuditWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOrder(String orderId) {
        jdbcTemplate.update(
                "insert into order_audit(order_id) values (?)",
                orderId
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderAuditListener {

    private final AuditWriter auditWriter;

    public OrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        auditWriter.recordOrder(event.orderId());
    }
}
~~~

AuditWriter is a separate bean, so the call goes through the Spring proxy. REQUIRES_NEW opens an independent transaction for the write operation.

Do not call a @Transactional method of the listener class itself via self-invocation and expect the proxy to apply propagation. Separate into another service or invoke through another Spring bean.

## 9. Combining AFTER_COMMIT with @Async

When a post-commit task is time-consuming, the listener can delegate the work to a separate async bean:

~~~java
@Component
public class OrderAfterCommitListener {

    private final AsyncOrderNotifier notifier;

    public OrderAfterCommitListener(AsyncOrderNotifier notifier) {
        this.notifier = notifier;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        notifier.notifyCustomer(event.orderId());
    }
}
~~~

~~~java
@Service
public class AsyncOrderNotifier {

    private final OrderQueryService queryService;

    public AsyncOrderNotifier(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @Async
    public void notifyCustomer(String orderId) {
        int count = queryService.countById(orderId);
        System.out.println("Committed order " + orderId + ", rows=" + count);
    }
}
~~~

~~~java
@Service
public class OrderQueryService {

    private final JdbcTemplate jdbcTemplate;

    public OrderQueryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public int countById(String orderId) {
        return jdbcTemplate.queryForObject(
                "select count(*) from orders where order_id = ?",
                Integer.class,
                orderId
        );
    }
}
~~~

@EnableAsync must be enabled and an appropriate TaskExecutor configured.

In this pattern:

- The listener is only invoked after a successful commit.
- The listener passes orderId to the worker.
- The worker runs on a different thread and does not inherit the publisher's transaction.
- OrderQueryService opens its own read transaction on the worker thread.
- The publisher does not wait for the worker to finish.

Separating the listener and the worker into distinct beans ensures the @Async call goes through the Spring proxy. If a method in the same class calls another @Async method directly, self-invocation usually bypasses the proxy and does not offload the call to the executor.

Do not pass a JDBC Connection, EntityManager, or a managed JPA entity to the worker. Pass an ID or an immutable DTO so the worker can re-query in its own transaction.

## 10. Exceptions and Transaction Outcomes

Exceptions have different meanings depending on the phase:

| Phase | When the listener throws an exception |
|---|---|
| BEFORE_COMMIT | Can cause the commit to fail and the transaction to roll back. |
| AFTER_COMMIT | The transaction has already committed; the exception does not reverse committed data. |
| AFTER_ROLLBACK | The transaction has already rolled back; the exception cannot turn a rollback into a commit. |
| AFTER_COMPLETION | The transaction has already completed; the exception does not change the transaction outcome. |

For a synchronous listener, an exception can propagate through the callback call path and cause the caller to see an error even though the transaction committed. Therefore, AFTER_COMMIT errors must be handled as post-commit errors, not as errors that can roll back the original transaction.

For an @Async method returning void, an exception occurs on the worker thread and does not return to the publisher. Spring logs async errors by default; an AsyncUncaughtExceptionHandler can be configured. If the method returns a Future or CompletableFuture, the caller can observe the error when holding and inspecting the future.

Do not use an exception in AFTER_COMMIT as a rollback mechanism. If a side effect fails, handle retries or persist the job state separately.

## 11. Testing Transactional Listeners

An integration test needs to pay attention to the transaction created by the test framework. If a test method has @Transactional, the transaction normally rolls back when the test finishes, so an AFTER_COMMIT listener will not run as the test expects.

Several ways to test:

- Do not open a transaction on the test method; call the @Transactional service through the Spring proxy.
- Use @Commit when you want the test's transaction to commit.
- Use TestTransaction.flagForCommit() and TestTransaction.end() to end the test transaction with a commit.
- Use a spy, counter, or audit table to observe the listener's side effects.
- For async listeners, use a latch or Awaitility with a timeout instead of arbitrary Thread.sleep.

Example:

~~~java
@SpringBootTest
class OrderEventListenerTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void orderIsCommitted() {
        orderService.placeOrder("ORD-TEST");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where order_id = ?",
                Integer.class,
                "ORD-TEST"
        );

        assertEquals(1, count);
    }
}
~~~

The test above verifies that the data has been committed. If you want to verify the listener's side effects, check the collaborator or the record created by the listener. Do not infer that the listener ran merely from the publisher returning.

## 12. Complete Example with Java 17, Spring Boot, and H2

The example demonstrates three cases:

1. Order ORD-126 commits successfully: BEFORE_COMMIT, AFTER_COMMIT, and AFTER_COMPLETION run.
2. Order ORD-127 rolls back: AFTER_ROLLBACK and AFTER_COMPLETION run; AFTER_COMMIT does not run.
3. JOB-126 is published outside a transaction: the listener with fallbackExecution=true runs immediately.

### Directory Structure

~~~text
spring-transactional-event-listener/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/events/
        │   ├── TransactionalEventApplication.java
        │   ├── OrderCreatedEvent.java
        │   ├── JobCompletedEvent.java
        │   ├── OrderService.java
        │   ├── OrderPhaseListeners.java
        │   └── JobFallbackListener.java
        └── resources/
            ├── application.properties
            └── schema.sql
~~~

### 12.1. Dependencies

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-transactional-event-listener</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
</project>
~~~

### 12.2. Database

File application.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:transactional-event-demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.main.web-application-type=none
~~~

File schema.sql:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(50) PRIMARY KEY
);
~~~

### 12.3. Event Types

File OrderCreatedEvent.java:

~~~java
package com.example.events;

public record OrderCreatedEvent(String orderId) {
}
~~~

File JobCompletedEvent.java:

~~~java
package com.example.events;

public record JobCompletedEvent(String jobId) {
}
~~~

### 12.4. Transactional Publisher

File OrderService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            ApplicationEventPublisher publisher
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.publisher = publisher;
    }

    @Transactional
    public void placeOrder(String orderId) {
        jdbcTemplate.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println(
                "OrderService: event published for " + orderId
        );
    }

    @Transactional
    public void placeOrderAndRollback(String orderId) {
        jdbcTemplate.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println(
                "OrderService: event published for " + orderId
        );

        throw new IllegalStateException("Simulate transaction rollback");
    }
}
~~~

Both methods publish events while a transaction is active. The second method intentionally throws an exception so the transaction rolls back.

### 12.5. Listeners for Each Phase

File OrderPhaseListeners.java:

~~~java
package com.example.events;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPhaseListeners {

    @Order(10)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderCreatedEvent event) {
        System.out.println("BEFORE_COMMIT: validate " + event.orderId());
    }

    @Order(20)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        System.out.println("AFTER_COMMIT: send receipt " + event.orderId());
    }

    @Order(30)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderCreatedEvent event) {
        System.out.println("AFTER_ROLLBACK: rollback " + event.orderId());
    }

    @Order(40)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("AFTER_COMPLETION: completed " + event.orderId());
    }
}
~~~

Each method is registered for a separate phase. On commit, Spring invokes BEFORE_COMMIT, AFTER_COMMIT, and then AFTER_COMPLETION. On rollback, AFTER_ROLLBACK and AFTER_COMPLETION are invoked.

### 12.6. Fallback Listener

File JobFallbackListener.java:

~~~java
package com.example.events;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class JobFallbackListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            fallbackExecution = true
    )
    public void onJobCompleted(JobCompletedEvent event) {
        System.out.println(
                "FALLBACK: handled " + event.jobId()
                        + " without transaction"
        );
    }
}
~~~

The listener receives JobCompletedEvent whether the event is published inside or outside a transaction. For an event outside a transaction, fallback runs immediately and does not create a transaction.

### 12.7. Running the Application

File TransactionalEventApplication.java:

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransactionalEventApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionalEventApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            OrderService orderService,
            ApplicationEventPublisher publisher,
            JdbcTemplate jdbcTemplate
    ) {
        return args -> {
            orderService.placeOrder("ORD-126");

            try {
                orderService.placeOrderAndRollback("ORD-127");
            } catch (IllegalStateException expected) {
                System.out.println("Runner: caught rollback for ORD-127");
            }

            publisher.publishEvent(new JobCompletedEvent("JOB-126"));

            Integer committedOrders = jdbcTemplate.queryForObject(
                    "select count(*) from orders",
                    Integer.class
            );

            System.out.println("Committed orders: " + committedOrders);
        };
    }
}
~~~

ApplicationRunner executes after ApplicationContext refreshes and before ApplicationReadyEvent. Calls to OrderService go through the Spring bean, so @Transactional is applied.

Run from the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Excluding Spring Boot startup logs, the output printed by the application is:

~~~text
OrderService: event published for ORD-126
BEFORE_COMMIT: validate ORD-126
AFTER_COMMIT: send receipt ORD-126
AFTER_COMPLETION: completed ORD-126
OrderService: event published for ORD-127
AFTER_ROLLBACK: rollback ORD-127
AFTER_COMPLETION: completed ORD-127
Runner: caught rollback for ORD-127
FALLBACK: handled JOB-126 without transaction
Committed orders: 1
~~~

Result:

- ORD-126 commits, so BEFORE_COMMIT, AFTER_COMMIT, and AFTER_COMPLETION run.
- ORD-127 rolls back, so AFTER_COMMIT does not run; AFTER_ROLLBACK and AFTER_COMPLETION run.
- JOB-126 is published outside a transaction, so the fallback listener runs immediately.
- The database retains only one committed order.

## 13. Reliability Limitations and Transactional Outbox

@TransactionalEventListener binds callbacks to the transaction, but the callbacks remain in process memory. If the database commits and the process stops before the listener or worker finishes, the event is not automatically recovered when the application restarts.

If the requirement is that every business change must be reliably delivered, consider the transactional outbox pattern:

1. In the same transaction, write the business data.
2. Also in that transaction, write an outbox record with the event ID and payload.
3. A worker reads unsent records and publishes messages.
4. Update the delivery status; if an error occurs, retry according to policy.
5. Consumers use idempotency to process safely when messages are redelivered.

The outbox guarantees that the intent to publish an event is persisted together with the business transaction. It does not by itself guarantee that side effects in external systems occur strictly once.

## 14. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| Listener does not run | Event published outside a transaction and fallbackExecution is false by default. | Publish the event inside a transaction or enable fallback if appropriate. |
| Listener runs before commit | Regular @EventListener was used. | Use AFTER_COMMIT when the side effect requires committed data. |
| AFTER_COMMIT does not run on rollback | This is the correct behavior of the phase. | Use AFTER_ROLLBACK if you need to react to a rollback. |
| Assuming fallback creates a transaction | Misunderstanding fallbackExecution. | Fallback invokes the listener immediately outside any transaction. |
| DB write in AFTER_COMMIT is not committed | Old resources may still be accessible after the transaction finishes. | Call a REQUIRES_NEW service. |
| @Transactional has no effect | Self-invocation bypasses the proxy or propagation does not create a transaction. | Call through another Spring bean and check propagation. |
| Worker does not see the original transaction | @Async runs on a different thread. | Open a separate transaction on the worker if database access is needed. |
| AFTER_COMMIT exception causes caller to see an error | The transaction already committed before the callback. | Handle post-commit errors and retry separately. |
| Test does not trigger AFTER_COMMIT | Test transactions roll back by default. | Use @Commit, TestTransaction, or a test without an enclosing transaction. |
| Task lost on restart | Callbacks reside only in memory. | Use a transactional outbox or a durable broker. |

## 15. Best Practices

- Use AFTER_COMMIT for side effects that must only start after a successful commit.
- Use BEFORE_COMMIT for checks or database operations that must share the same transaction.
- Use AFTER_ROLLBACK to react to a rollback, not as an automatic retry.
- Use AFTER_COMPLETION when processing is needed after both commit and rollback.
- Keep fallbackExecution=false if the listener requires a real transaction.
- Enable fallbackExecution=true only when immediate non-transactional processing is valid.
- Place business logic in separate service beans with appropriate transactions.
- Use REQUIRES_NEW when a post-commit callback needs to write to the database in a new transaction.
- Do not assume @Async inherits the publisher's transaction.
- Pass IDs or immutable DTOs instead of entities/JPA proxies across threads.
- Design idempotency and retries for critical side effects.
- Use an outbox or message broker when durable delivery across restarts is needed.
- Test commit, rollback, and out-of-transaction event scenarios.

## 16. Self-Check

1. Which phase does @TransactionalEventListener run in by default?
2. Why can @EventListener run before the publisher's transaction commits?
3. How do BEFORE_COMMIT and AFTER_COMMIT differ in timing?
4. Does an AFTER_COMMIT listener run when the transaction rolls back?
5. How do AFTER_ROLLBACK and AFTER_COMPLETION differ?
6. What does fallbackExecution=true do when an event is published outside a transaction?
7. Why does fallbackExecution not guarantee that data has been committed?
8. When should REQUIRES_NEW be used in a listener?
9. How can REQUIRES_NEW cause an inner transaction's listener to run before the outer transaction?
10. Why does @Async not inherit the publisher's imperative transaction?
11. Why can an AFTER_COMMIT exception not roll back already-committed data?
12. Why can a test transaction that rolls back by default prevent an AFTER_COMMIT listener from running?
13. What gap between database commit and publishing does transactional outbox solve?

**Key Takeaway:** @TransactionalEventListener binds a listener to a transaction phase. By default, the listener runs after a successful commit; you can choose BEFORE_COMMIT, AFTER_ROLLBACK, or AFTER_COMPLETION. If an event is published outside a transaction, the listener is skipped by default; fallbackExecution=true allows immediate execution without creating a transaction. Choose the phase according to business requirements, open a separate transaction when writing to the database after commit, and use an outbox when durable delivery is needed.

## References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework 6.2 — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html)
