# Listener Exceptions and Transaction Rollback in Spring Framework Application Events

## 1. Core Question: When a Listener Throws an Error, Does the Transaction Roll Back?

Spring Framework allows publishing events via `ApplicationEventPublisher.publishEvent(...)` and handling them via `@EventListener`, `ApplicationListener`, or `@TransactionalEventListener`. However, **not every exception in a listener causes the publisher's transaction to roll back**. The outcome depends on **when the listener runs**, **whether it is synchronous with the publisher**, **whether the exception escapes to the transaction interceptor**, and **the transaction's rollback rules**.

Two contrasting cases:

~~~java
// Case A: synchronous listener, error escapes while T1 is still open.
@Transactional
public void placeOrder(long id) {
    repository.insert(id);
    events.publishEvent(new OrderPlaced(id)); // listener throws RuntimeException
    // Exception propagates out of the method -> T1 may roll back.
}
~~~

~~~java
// Case B: listener is invoked after T1 commits successfully.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    sendEmail(event.id()); // An error here cannot roll back T1's commit.
}
~~~

Both snippets above are **illustrative integration code**; `repository`, `events`, `OrderPlaced`, and `sendEmail` must be defined in the application. In Case A, a `RuntimeException` escaping the `@Transactional` call usually rolls back the original transaction under default rules. In Case B, the original transaction **has already finished committing before the listener body runs**; an exception can cause a post-processing failure but has no ability to "undo" already committed data.

Lesson objectives:

1. Understand the exception propagation path between publisher, multicaster, listener, and transaction interceptor.
2. Know when a synchronous `@EventListener` rolls back T1, and what changes if an exception is caught/swallowed.
3. Distinguish the four `@TransactionalEventListener` phases and the error semantics of each phase.
4. Know why `@Async` and `ErrorHandler` configuration alter the exception propagation path.
5. Practice with Java 17 + JDBC/H2 to observe real rollback in the database.
6. Choose an appropriate handling model for non-rollbackable side effects such as email, external APIs, and brokers.

## 2. Exception Propagation Model from Event to Transaction

In the default configuration, `SimpleApplicationEventMulticaster` has no separate asynchronous executor and synchronous listeners are invoked on the publisher's thread. When the service is inside transaction T1:

~~~text
Caller
  |
  v
Spring @Transactional proxy
  |
  +-- BEGIN T1
  |
  +-- OrderService.placeOrder()
  |       |
  |       +-- INSERT orders(...)
  |       |
  |       +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
  |                 |
  |                 +-- SimpleApplicationEventMulticaster
  |                           |
  |                           +-- @EventListener (synchronous)
  |                                   |
  |                                   +-- throw IllegalStateException
  |                           |
  |                           +-- exception returns to publisher
  |
  +-- exception escapes service
  |
  +-- TransactionInterceptor applies rollback rules
  |       |
  |       +-- ROLLBACK T1 (with default RuntimeException)
  |
  v
Caller receives exception
~~~

Distinguish three things:

- **Publishing an event** does not itself commit or roll back; `ApplicationEventPublisher` only dispatches an event.
- **Whether an exception propagates** is the result of how the listener is executed and how errors are handled.
- **Whether a transaction rolls back** is decided by the transaction manager/interceptor based on transaction status, rollback rules, and exception context.

If no transaction is active, a synchronous listener exception can still propagate back to the publisher, but **there is no T1 to roll back**. If another transaction already committed before the event was published, an exception cannot reverse that transaction.

## 3. Synchronous @EventListener: RuntimeException Usually Triggers Rollback

Suppose the service is called through a Spring proxy:

~~~java
@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(
            ApplicationEventPublisher publisher,
            OrderRepository repository) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void createOrder(long orderId) {
        repository.insert(orderId);
        publisher.publishEvent(new OrderCreated(orderId));
    }
}
~~~

Synchronous listener:

~~~java
@Component
public class OrderValidationListener {

    @EventListener
    public void onCreated(OrderCreated event) {
        if (event.orderId() <= 0) {
            throw new IllegalArgumentException("invalid order ID");
        }
    }
}
~~~

This is an **integration class pair**, requiring an appropriate repository, payload, and imports. With the default synchronous `SimpleApplicationEventMulticaster` and no custom `ErrorHandler` swallowing the error, `IllegalArgumentException` escapes the listener into `publishEvent(...)`, and then escapes `createOrder(...)`. The Spring transaction interceptor sees an unchecked exception and by default marks/rolls back T1.

**Important conditions:**

- `@Transactional` must actually be active: typically a call through a **Spring proxy** to a Spring-managed bean.
- The listener must run **synchronously on the event-publishing path**; when running on a separate worker thread, an exception in the worker does not automatically propagate back to T1.
- The exception must **escape the transactional method boundary** or the transaction must already be marked rollback-only.
- The transaction manager must actually manage the operations that need rolling back (e.g., `DataSourceTransactionManager` managing the same JDBC datasource).
- If the listener already performed an external non-transactional side effect such as sending an email, rolling back the database **cannot recall that email**.

### Checked Exceptions in Listeners

The `@EventListener` Javadoc notes that a checked exception thrown by a listener is wrapped in `UndeclaredThrowableException`, because the event publisher cannot declare checked exceptions in its corresponding API signature. The wrapper error is an unchecked exception and can trigger rollback if it escapes the transaction interceptor.

This **differs** from the default rule when a `@Transactional` method itself throws a checked exception out: barring custom rollback configuration, Spring traditionally rolls back by default for `RuntimeException` and `Error`, and **does not automatically roll back for every checked exception**.

Do not assume "checked exceptions always commit" if the error gets wrapped into a runtime exception along the way; check the **actual exception leaving the transaction boundary** and the application's rollback rules configuration.

## 4. @Transactional Rollback Rules: Which Errors Trigger Rollback?

Default rules in the typical declarative transaction model:

| Case | Default outcome when exception escapes transaction interceptor |
|---|---|
| `RuntimeException` (including `IllegalStateException`, `IllegalArgumentException`) | Rollback |
| `Error` | Rollback |
| Checked exception such as `IOException` | No default rollback under traditional rules |
| Checked exception with `rollbackFor = IOException.class` | Rollback |
| `RuntimeException` matching a specific `noRollbackFor` | Can commit despite the exception, depending on actual rules |
| Transaction already marked rollback-only | Cannot commit successfully; ends with rollback, `UnexpectedRollbackException` may occur |

Example requiring rollback for a checked exception:

~~~java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    updateDatabase();
    throw new IOException("external dependency failed");
}
~~~

Example intentionally **not** rolling back when encountering a specific exception type:

~~~java
@Transactional(noRollbackFor = BusinessWarningException.class)
public void process() {
    updateDatabase();
    throw new BusinessWarningException("business warning");
}
~~~

These are **illustrative snippets**; `IOException`, `BusinessWarningException`, and `updateDatabase` must be declared/imported. Only configure `noRollbackFor` when the exception genuinely represents a business scenario where the transaction is permitted to commit; do not use it to mask persistence errors or consistency violations.

One version note: global rollback rule options can vary by Spring configuration/version; this lesson presents the **common default rules** and does not claim that an application with a custom `RollbackRuleAttribute` or different policy will behave identically.

## 5. Catching Exceptions Inside a Transaction Can Change the Outcome

Consider:

~~~java
@Transactional
public void createOrder(long id) {
    repository.insert(id);

    try {
        events.publishEvent(new OrderCreated(id));
    } catch (IllegalStateException ex) {
        log.warn("Listener failed", ex);
    }

    // No exception escapes this method anymore.
}
~~~

If the listener throws `IllegalStateException` and `catch` swallows the error, the transaction interceptor may see the method complete **normally** and attempt to commit. Thus, **catching an exception and not rethrowing it can cause the transaction to commit**, contrary to the author's expectation.

However, do not infer that `try/catch` always saves the transaction: an inner transactional participant or resource operation may already have marked the transaction **rollback-only**. When the outer method attempts to commit, Spring may throw `UnexpectedRollbackException` or report a transaction error depending on structure and transaction manager.

Valid choices:

- Want rollback: **rethrow** the exception, or intentionally mark rollback-only.
- Want to continue while still preserving the error: use an appropriate business exception type and log/metrics, if the contract allows commit.
- Want to handle errors separately without rolling back T1: move that work to a post-commit phase or a separate transaction, understanding that the side effect can fail independently.

Example of marking the current transaction rollback-only:

~~~java
try {
    events.publishEvent(new OrderCreated(id));
} catch (RuntimeException ex) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    log.error("Event processing failed; transaction will rollback", ex);
}
~~~

This is **integration code**; `TransactionAspectSupport` belongs to `org.springframework.transaction.interceptor`. Use it only when genuinely inside a Spring AOP-managed transaction; returning normally even though the transaction rolled back can confuse callers, so throwing a meaningful business exception is usually clearer.

### Self-Invocation and @Transactional

~~~java
public void outer() {
    this.createOrder(42L); // Internal call, usually bypasses the Spring transaction proxy.
}
~~~

If `outer` is invoked on the same instance, `this.createOrder(...)` does not go through the proxy under the default AOP mode. Even if `createOrder` has `@Transactional`, the intended transaction may **not start**. In that case, a listener throwing an error cannot roll back a transaction that never existed. Call through a Spring-managed bean/proxy or separate service boundaries properly.

## 6. @TransactionalEventListener: The Phase Determines Whether Rollback Is Still Possible

`@TransactionalEventListener` registers event handling bound to a transaction phase. The phases:

| Phase | When the listener actually runs | Can an exception in the listener roll back T1? |
|---|---|---|
| `BEFORE_COMMIT` | Before transaction T1 commits | **Yes**, with an unchecked exception propagating per the callback contract |
| `AFTER_COMMIT` (default) | After T1 commits successfully | **No**, commit has already completed |
| `AFTER_ROLLBACK` | After T1 rolls back | **No**, T1 has already rolled back |
| `AFTER_COMPLETION` | After T1 commits or rolls back | **No**, the transaction has ended |

When an event is published inside a transaction, the annotation defaults to `AFTER_COMMIT`. With **no transaction**, a transactional listener by default **is not invoked**, unless `fallbackExecution = true`.

### BEFORE_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void checkBeforeCommit(OrderCreated event) {
    if (event.mustReject()) {
        throw new IllegalStateException("before commit validation failed");
    }
}
~~~

This listener executes at the pre-commit step, not immediately inside `publishEvent`. It is an opportunity to check transaction conditions before the transaction manager commits. `TransactionSynchronization.beforeCommit(...)` allows runtime exceptions to propagate and roll back the transaction. If the listener was not registered because the event was not published inside a transaction, this callback is not present to check.

**Important:** `BEFORE_COMMIT` does not mean commit is guaranteed to happen; the transaction can still roll back due to a subsequent error.

### AFTER_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendOrderNotification(OrderCreated event) {
    notifier.send(event.orderId());
}
~~~

If `notifier.send(...)` throws an error, **T1 has already committed earlier**. T1's data cannot be reversed by throwing an exception in this phase. Logging/metrics, retries, or a durable mechanism are needed if sending the notification is important.

A subtle technical distinction: `TransactionPhase.AFTER_COMMIT` of `@TransactionalEventListener` is a specialized case of **`AFTER_COMPLETION`**, processed in the same transaction completion callback chain; it is **not** a call to `TransactionSynchronization.afterCommit()`.

Spring describes `TransactionSynchronization.afterCompletion(int)` as a callback whose raised exceptions are **logged rather than propagated** under the standard callback mechanism. Meanwhile, an exception from `TransactionSynchronization.afterCommit()` can **propagate to the caller even though data has already committed**. Therefore, do not state a rule like "every after-commit exception is always thrown back to the service" or "every after-commit exception is always swallowed" without specifying **the callback type and event publishing mechanism**. Whether the error is propagated or logged, neither **can roll back an already completed commit**.

### AFTER_ROLLBACK

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderCreated event) {
    metrics.incrementRollbackCount();
}
~~~

This is a reasonable place to log, record metrics, or trigger specifically designed **compensation logic**. It does not restore T1 (because T1 has already rolled back) and does not create a new transaction by default. If you need to write a durable audit row about the failure, use a new transaction or an appropriate outbox/processing block, rather than relying on the rolled-back transaction resource.

### AFTER_COMPLETION

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void cleanup(OrderCreated event) {
    temporaryState.remove(event.orderId());
}
~~~

Runs after both commit and rollback; suited for outcome-independent cleanup tasks. If you need to distinguish success from failure, use separate phases or the appropriate transaction synchronization contract.

All of these snippets are **integration code**, requiring the corresponding event classes, collaborators, imports, and bean configurations. Do not put all of them into a program without defining the interaction policy between listeners.

## 7. Runnable Java 17 Example: Both Regular Listener and BEFORE_COMMIT Errors Roll Back

The following example uses:

- Java 17+, Maven.
- Spring Framework **6.2.8**, `spring-context`, and `spring-jdbc`.
- H2 **2.3.232** as an in-memory database.
- `DataSourceTransactionManager` to drive JDBC transactions.
- `@EnableTransactionManagement` so Spring creates transaction proxies.
- Three service calls: success, error in a synchronous `@EventListener`, error in `BEFORE_COMMIT`.

We intentionally put `@Order(0)` on the transactional listeners to **register synchronizations before** the regular listener, and `@Order(100)` on the regular listener. This ensures the `AFTER_ROLLBACK` phase has its callback registered before the regular listener throws an error.

Structure:

~~~text
event-rollback-demo/
├── pom.xml
└── src/main/java/demo/EventRollbackDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-rollback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/EventRollbackDemo.java

~~~java
package demo;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public final class EventRollbackDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OrderService service = ctx.getBean(OrderService.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, status VARCHAR(30) NOT NULL)"
            );

            // 1. Success path.
            service.create(1L, FailureMode.NONE);
            System.out.println("rows after success=" + count(jdbc));

            // 2. RuntimeException in regular listener.
            try {
                service.create(2L, FailureMode.IN_REGULAR_LISTENER);
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("rows after regular failure=" + count(jdbc));

            // 3. RuntimeException at BEFORE_COMMIT time.
            try {
                service.create(3L, FailureMode.BEFORE_COMMIT);
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("rows after before-commit failure=" + count(jdbc));
        }
    }

    private static long count(JdbcTemplate jdbc) {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM orders",
            Long.class
        );
        return count == null ? -1L : count;
    }

    public enum FailureMode {
        NONE,
        IN_REGULAR_LISTENER,
        BEFORE_COMMIT
    }

    public record OrderCreated(long orderId, FailureMode failureMode) {}

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:eventrollback;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc, ApplicationEventPublisher events) {
            return new OrderService(jdbc, events);
        }

        @Bean
        public OrderObservers orderObservers() {
            return new OrderObservers();
        }
    }

    // Must not be final so Spring can create a class-based proxy.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc, ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.events = events;
        }

        @Transactional
        public void create(long id, FailureMode failureMode) {
            jdbc.update(
                "INSERT INTO orders (id, status) VALUES (?, ?)",
                id, "CREATED"
            );
            events.publishEvent(new OrderCreated(id, failureMode));
        }
    }

    public static class OrderObservers {

        // Synchronizations are registered before regular listener.
        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT
        )
        public void beforeCommit(OrderCreated event) {
            System.out.println("BEFORE_COMMIT id=" + event.orderId());
            if (event.failureMode() == FailureMode.BEFORE_COMMIT) {
                throw new IllegalStateException("before commit failed");
            }
        }

        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderCreated event) {
            System.out.println("AFTER_COMMIT id=" + event.orderId());
        }

        @Order(0)
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void afterRollback(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK id=" + event.orderId());
        }

        @Order(100)
        @EventListener
        public void immediate(OrderCreated event) {
            System.out.println("REGULAR id=" + event.orderId());
            if (event.failureMode() == FailureMode.IN_REGULAR_LISTENER) {
                throw new IllegalStateException("regular listener failed");
            }
        }
    }
}
~~~

Run from the `event-rollback-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventRollbackDemo
~~~

Lines printed by **the program** on a successful run, in the expected order with the default synchronous dispatcher and configuration above (ignoring auxiliary Maven/Spring logs):

~~~text
REGULAR id=1
BEFORE_COMMIT id=1
AFTER_COMMIT id=1
rows after success=1
REGULAR id=2
AFTER_ROLLBACK id=2
caught=regular listener failed
rows after regular failure=1
REGULAR id=3
BEFORE_COMMIT id=3
AFTER_ROLLBACK id=3
caught=before commit failed
rows after before-commit failure=1
~~~

### Why Is the Output Like This?

**Run 1 — success:**

1. The transaction proxy starts T1 and inserts ID 1.
2. `publishEvent` invokes the regular listener, printing `REGULAR id=1`. The three transactional listeners have already registered phase callbacks.
3. The service method finishes normally; the transaction manager invokes `BEFORE_COMMIT`, printing mark 1.
4. The database commits successfully.
5. The `AFTER_COMMIT` listener runs, printing mark 1.
6. `count(jdbc)` running outside T1 returns one row.

**Run 2 — error in regular listener:**

1. Transaction T2 inserts ID 2 and publishes the event.
2. Because the `@Order(0)` transactional listeners were registered first, `AFTER_ROLLBACK` already has a synchronization on T2.
3. The `@Order(100)` regular listener prints `REGULAR id=2`, then throws `IllegalStateException`.
4. The exception escapes `publishEvent` and the service method; the transaction interceptor rolls back T2.
5. `AFTER_ROLLBACK` prints ID 2, and the caller receives the message `regular listener failed`. Row ID 2 does not exist in the database.

**Run 3 — error in BEFORE_COMMIT:**

1. Transaction T3 inserts ID 3; the regular listener runs normally.
2. The service method returns, and Spring prepares to commit T3.
3. The `BEFORE_COMMIT` callback prints ID 3 and throws `IllegalStateException`.
4. The transaction manager rolls back T3; the `AFTER_ROLLBACK` listener is called; the caller receives the `before commit failed` exception.
5. Row ID 3 does not exist. The total row count remains one.

The example uses a real database transaction, so it differs from demos that merely mutate an in-memory `Map`. All transaction logic goes through the Spring proxy, rather than calling `new OrderService(...).create(...)` outside the container.

### What Has Not Been Demonstrated by This Example?

- It does not send emails or call REST APIs; those side effects **do not automatically roll back** with the SQL transaction.
- It does not demonstrate behavior when configuring an async executor or custom `ErrorHandler`.
- It does not throw an error inside `AFTER_COMMIT`, so as to keep stdout deterministic and avoid conflating "the call throws an exception" with the DB commit outcome.
- It has no JPA persistence context or reactive transaction; those topics have additional boundaries requiring separate analysis.

## 8. AFTER_COMMIT Throws an Exception: How to Handle When the DB Already Committed?

A common scenario:

~~~text
T1: BEGIN
  UPDATE orders SET status = 'PAID' ...
  publish OrderPaid
T1: COMMIT succeeded
  -> @TransactionalEventListener(AFTER_COMMIT)
       -> call Email API
       -> Email API timeout/throw
T1: DB data remains in PAID state
~~~

Do not call `throw new RuntimeException(...)` inside a post-commit callback and expect the original transaction to roll back. If additional DB writes are needed from the callback, the original transaction resources may still be temporarily bound to the thread until cleanup. Spring recommends opening **a new transaction** for DB work that truly needs to commit after completion.

Architectural example:

~~~java
@Component
public class PaymentListener {
    private final AuditWriter auditWriter;

    public PaymentListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPaid(OrderPaid event) {
        auditWriter.record(event.paymentId());
    }
}

@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(long paymentId) {
        repository.insertAudit(paymentId);
    }
}
~~~

This is **integration code**: types `OrderPaid`, `AuditRepository`, and imports must be defined. `REQUIRES_NEW` opens an independent physical transaction via the corresponding transaction manager, invoked through the `AuditWriter` bean's Spring proxy. If the new transaction fails, **the original transaction is not rolled back**. If audit and payment must be recorded **atomically**, both records should be created in the same initial transaction or use a transactional outbox as required.

Do not put `@Transactional(propagation = Propagation.REQUIRES_NEW)` on a method invoked via `this.record(...)` within the same bean under the default proxy mode: self-invocation bypasses the proxy and does not guarantee opening a new transaction.

### Does an Email-Sending API Roll Back with the DB?

No. Even if you invoke the email call inside `@Transactional` before commit, a database rollback **does not automatically recall the email**. Sending in `AFTER_COMMIT` ensures the email is only sent after the DB commits, reducing the risk of emailing about rolled-back changes, though there is still a window for lost work if the process crashes after commit and before sending. For guaranteed delivery requirements, a durable outbox/queue, retry, and idempotency are needed.

## 9. @Async and Exceptions: Why Rollback Does Not Cross Threads

Putting `@Async` on an `@EventListener`:

~~~java
@Async("eventsExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    sendNotification(event.orderId());
    // RuntimeException if any occurs on the executor worker.
}
~~~

This snippet is **integration code**, requiring `@EnableAsync`, an `eventsExecutor` bean, and the listener bean to go through an async proxy. When functioning properly, the listener body runs on an executor worker. An exception thrown in the worker **usually does not propagate back to the `publishEvent(...)` caller**; it does not automatically trigger rollback of the publisher's transaction T1.

Consequences:

- The worker may run **before T1 commits**, so a `SELECT` by ID might not yet see T1's data.
- T1 can commit even though sending the notification failed; an exception in the worker is not a condition to roll back T1.
- For `@Async void` methods, you can configure `AsyncUncaughtExceptionHandler` to log/record exceptions. For methods returning a supported future, observe the exceptional result from the future.
- Errors during **task submission** or executor rejection can occur on the publish call path and have different semantics from exceptions in the worker body. Do not claim "every async-related error can never affect T1".
- ThreadLocal transaction, security context, and logging MDC from the publisher are not guaranteed to carry over automatically to the worker without configuring corresponding propagation.

### @Async Combined with AFTER_COMMIT

~~~java
@Async("eventsExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaid(OrderPaid event) {
    notificationService.send(event.paymentId());
}
~~~

The goal is to trigger async processing **after T1 commits**. Transaction binding/synchronization registration must still take place within the publisher's transaction context; the work body can run on a worker thread after completion. An error occurring in the worker cannot roll back T1. If the worker needs a DB transaction, explicitly open a new transaction inside the worker.

Starting from Spring Framework 6.1, transactional listeners have a different execution contract from regular listeners regarding `SimpleApplicationEventMulticaster`'s executor: you must not assume every transactional listener is arbitrarily handed off to an executor before registering transaction synchronization. Nonetheless, annotating the listener handler itself with `@Async` can make the body run separately when proxies are configured properly.

**For durable retry handling**, `@Async` is not enough. The process can die after commit before the task finishes. Use an outbox, queue, or job store when the business workflow requires certainty.

## 10. How Does SimpleApplicationEventMulticaster's ErrorHandler Affect Rollback?

`@Async` is not the only thing that prevents exceptions from reaching the transaction proxy. An application can define a custom `ApplicationEventMulticaster` with an `ErrorHandler`.

Illustrative configuration pattern:

~~~java
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster m =
        new SimpleApplicationEventMulticaster();

    m.setErrorHandler(ex -> {
        logger.error("Event listener failed", ex);
        // Do not rethrow -> error is handled according to handler policy.
    });

    return m;
}
~~~

This is a **configuration snippet**, requiring `logger`, imports, and appropriate bean setup. `SimpleApplicationEventMulticaster` does not have a built-in error-swallowing `ErrorHandler` by default. When callbacks are executed synchronously but the `ErrorHandler` swallows the exception, the `publishEvent(...)` call path can complete normally and transaction T1 can commit.

If the error handler chooses to **rethrow** the exception, the error can still return to the publisher and lead to rollback as in the normal model. With an asynchronous executor, the error may be handled inside the worker rather than the publisher thread.

Therefore, when debugging "the listener threw an error yet the database still committed", check:

1. Is the listener running synchronously?
2. Does the Spring event multicaster have a custom `TaskExecutor`/`ErrorHandler`?
3. Was the exception caught inside the listener or service?
4. Does the transaction interceptor actually wrap the publish call?
5. Was the transaction marked rollback-only or configured with `noRollbackFor`?
6. Was the event processed **after commit** instead of while T1 was still open?

### A Design Hazard

Swallowing every listener exception allows the publisher to continue, but can also lose a mandatory business signal. If a listener performs a check that decides whether the transaction is allowed to commit, do not rely on a dispatch mechanism designed to be configurable as "log and continue". Core validation checks should live directly in service/domain validation, with clear transaction boundaries.

## 11. Transaction Propagation and Exceptions Across Multiple Services

A model involving an outer service T1 and an inner service T2 can make rollback more complex.

### REQUIRED (Default) — Same Physical Transaction

~~~java
@Service
class InnerService {
    @Transactional // PROPAGATION_REQUIRED
    public void validateAndStore() {
        throw new IllegalStateException("inner failure");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    @Transactional
    public void placeOrder() {
        try {
            inner.validateAndStore();
        } catch (IllegalStateException ex) {
            // Exception caught, yet T1 may be marked rollback-only.
        }
    }
}
~~~

This is an **integration pattern** requiring bean injection through proxies. When an inner transactional proxy joins the same physical transaction and encounters a runtime exception, Spring may mark the shared transaction rollback-only. An outer catch does not clear this flag; when the outer method commits, `UnexpectedRollbackException` may be thrown. The exact behavior depends on the transaction manager and `globalRollbackOnParticipationFailure` configuration, but you should not rely on catching to force a commit.

### REQUIRES_NEW — Independent Transaction

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(long orderId) {
    auditRepository.insert(orderId);
}
~~~

When the call goes through a proxy with a suitable transaction manager, Spring suspends the outer transaction and opens a new transaction for the audit part. If the new transaction rolls back due to a listener error, **it does not automatically force the outer transaction to roll back**, unless the exception continues escaping to the outer interceptor or the outer logic decides to roll back.

Conversely, if T2 commits and then T1 rolls back, T2's committed data can remain. That is a business trade-off that requires careful thought, especially for auditing, compensation, and notifications.

### NESTED — Savepoint Instead of a Separate Physical Transaction

`Propagation.NESTED` can use a savepoint on the same resource/transaction when supported by the transaction manager, particularly in JDBC. Rolling back to a savepoint does not mean a completely independent transaction was opened; if the outer transaction subsequently rolls back, all changes logically committed in the savepoint are still rolled back along with the outer transaction. Do not use `NESTED` as a way to ensure audit records survive a rollback of the original transaction.

## 12. What Can Exceptions in AFTER_ROLLBACK/AFTER_COMPLETION Not Do?

After a rollback, there is no original commit left to undo. An error inside an `AFTER_ROLLBACK` or `AFTER_COMPLETION` callback is merely a **post-processing error**, unable to create a new rollback for T1. With standard Spring transaction synchronization, exceptions in `afterCompletion` are logged and not propagated via the callback mechanism like `beforeCommit`.

A counter-example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void recordFailure(OrderCreated event) {
    auditRepository.save(new AuditRecord(event.orderId()));
    // Do not assume this save() is committed by T1.
}
~~~

Transaction resources may still remain temporarily bound to the thread during the callback; Spring's Javadoc warns that data operations might "participate" in the old transaction resource even though **no further commit will happen**. The explicit way to record a failure audit is to call another bean with `@Transactional(propagation = REQUIRES_NEW)`, or send the error to a durable processing system with an appropriate transaction.

If the recovery process must **never lose track of errors**, logging in the callback is not enough: a durable audit, event failure store, or outbox/job store with corresponding guarantees is required.

## 13. Reactive Transactions: Exception Regarding Where Transaction Context Is Stored

The examples above use thread-bound transactions with `PlatformTransactionManager`, suitable for imperative JDBC/JPA.

In reactive Spring (R2DBC, `ReactiveTransactionManager`), transaction state is attached to the **Reactor Context**, not ThreadLocal. Starting from Spring 6.1, `@TransactionalEventListener` supports reactive transactions when **the event source contains the transaction context**, typically via `TransactionalEventPublisher`. A listener invoked on a separate subscription does not automatically inherit the publisher's transaction.

Conceptual example:

~~~java
return database.sql("INSERT INTO orders(id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(
        new OrderCreated(orderId, FailureMode.NONE)))
    .as(transactionalOperator::transactional);
~~~

This is an **integration pattern**, requiring `DatabaseClient`, `TransactionalEventPublisher`, and `TransactionalOperator`. In a reactive pipeline, an exception from the publisher (an `onError` signal) inside the transaction can trigger rollback via the operator; an async listener or work detached from the subscription does not automatically carry the same transaction context.

Do not copy the Java JDBC demo above and expect R2DBC interactions to behave like ThreadLocal. Test with `StepVerifier` or reactive integration tests along the proper subscription boundaries.

## 14. Testing Listener Rollback Properly

A test should verify both **database state** and **listener events** simultaneously, rather than only verifying that an exception was thrown.

### Test Case Checklist

| Case | Method causing error | Database expectation | Listener expectation |
|---|---|---|---|
| Success | No error | Row committed | `AFTER_COMMIT` runs |
| Synchronous throws `RuntimeException` | `@EventListener` | Row rolled back | `AFTER_ROLLBACK` runs if registered |
| `BEFORE_COMMIT` throws `RuntimeException` | `@TransactionalEventListener` | Row rolled back | `AFTER_ROLLBACK` runs |
| `AFTER_COMMIT` fails | Post-commit | T1 row remains committed | Error recorded and retried independently |
| Async worker fails | `@Async @EventListener` | T1 does not auto-rollback on worker error | Error handler/log in worker |
| Exception caught and swallowed | Service/listener | May commit | Must check actual rollback-only status |
| `noRollbackFor` applied | Transaction interceptor | May commit per rule | Exception can still reach caller |
| No transaction | Plain publish | No T1 to roll back | Transactional listener does not run by default |

### Trap: @Transactional Tests Roll Back by Default

In Spring Test, a test method annotated with `@Transactional` is normally rolled back by the framework when the test ends. If you want to test an `AFTER_COMMIT` listener, do not simply call the service and assert immediately inside an uncommitted test transaction:

~~~java
@Test
@Transactional
void verifiesAfterCommit() {
    service.create(10L, FailureMode.NONE);

    TestTransaction.flagForCommit();
    TestTransaction.end(); // The test's transaction actually commits.

    // Assert AFTER_COMMIT here for synchronous listener.
}
~~~

This is **illustrative test code**, requiring `spring-test`, JUnit, data, and test transaction configuration; it is not part of `EventRollbackDemo.java`. Another simpler approach is **not** putting `@Transactional` on the test method itself, and instead calling a Spring service proxy that has its own `@Transactional`, as in the demo.

Testing must ensure:

- The beans/transaction manager live in the same test context.
- Transactional calls actually go through the proxy.
- Exceptions are not inadvertently swallowed by a multicaster/error handler.
- When using `@Async`, use await/latch with timeouts; do not assert immediately after publication.
- With `BEFORE_COMMIT`, compare DB changes **after the service call finishes/throws**, not just in-memory entity values.
- When events send emails or HTTP requests, use fakes/mocks that can simulate failures; do not assume a DB rollback restores external side effects.

## 15. Ensuring Business Guarantees When Post-Processing Fails: Outbox and Idempotency

If you need "once an order commits successfully, an email request must definitely happen", a plain `AFTER_COMMIT` listener is not enough to guarantee durability. There is a window:

~~~text
T1 COMMIT order
      |
      | JVM crash or process is terminated
      v
AFTER_COMMIT listener has not yet sent the email
      |
      v
No durable event exists to replay
~~~

One option is a **transactional outbox**:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox_events(event_id, order_id, event_type, payload, status='PENDING')
COMMIT T1
       |
       v
Worker reads PENDING
       |
       +-- send email / publish to broker
       +-- update status, log error, bounded retry
       |
       v
Consumer uses eventId/idempotency key to avoid duplicate processing
~~~

The outbox row and order changes are written in **the same local transaction**. If T1 rolls back, both roll back. If the process dies after commit, the outbox record remains for the worker to process later. However, an outbox typically supports **at-least-once delivery** and does not by itself guarantee end-to-end exactly-once: a worker could send successfully and die before marking completion, creating a duplicate.

Important policies:

- **eventId** unique per occurrence; retries keep the same eventId.
- **aggregateId/orderId** identifies the business entity; do not use it to deduplicate all events.
- **Retry count, backoff, timeout:** avoid flooding downstream systems during prolonged failures.
- **Idempotency:** send requests with an idempotency key if the API supports it, or store `processed_events` per consumer.
- **DLQ/job store:** isolate permanent errors requiring human intervention.
- **Observability:** measure pending counts, failures, and latency from commit to completion.
- **Transaction boundary:** audits/downstream processing results need their own transactions; do not assume they are committed by T1.

This is the solution for **never losing events after a crash**, which is distinct from the question "does an exception roll back the current transaction".

## 16. Practical Error-Diagnostic Checklist

### Scenario A — Listener throws yet the database still commits

1. Check whether the listener uses `@TransactionalEventListener(AFTER_COMMIT)` or a regular `@EventListener`.
2. Check for `@Async`, custom executors, and custom `ErrorHandler`s.
3. Look for `try/catch` swallowing exceptions in the listener, publisher, or service.
4. Check `@Transactional(noRollbackFor = ...)` and global rollback rules.
5. Confirm the transactional method is called through a proxy and the transaction manager covers the right datasource.
6. Verify `COMMIT/ROLLBACK` status from DB/transaction logs, not just by looking at Java object mutations.
7. Check whether any resource was already committed by another transaction before the error occurred.

### Scenario B — Service catches exception yet still rolls back

1. Check whether an inner `@Transactional(REQUIRED)` already set rollback-only.
2. Watch for `UnexpectedRollbackException` at commit time.
3. Check whether a DB error left the transaction unable to commit.
4. If isolation is needed, consider `REQUIRES_NEW` with proper bean/proxy boundaries; understand that side effects of the new transaction can survive an outer rollback.
5. Do not use `noRollbackFor` to make a transaction already failed by the DB appear valid.

### Scenario C — AFTER_ROLLBACK does not run

1. Was the event published while a transaction was active?
2. Was the listener registered by Spring before publishing?
3. Did another `@EventListener` throw an error **before** the transactional listener could register synchronization?
4. On which thread was the event published? Was it dispatched to an executor before registration?
5. Did the transaction manager actually roll back, or did it just return an error from a non-transactional operation?
6. Are there `fallbackExecution` settings or custom configurations causing behavior to differ from the default?

### Scenario D — AFTER_COMMIT throws an error, client reports failure yet data persists

Do not automatically retry the entire order-creation command just because the client saw an error: the transaction may **have already committed successfully**. For transaction completion callbacks, exception behavior can depend on the callback type, but the DB does not automatically roll back. Design commands with idempotency keys, APIs that return results matching the transaction outcome, and post-processing logic driven by explicit state.

### Scenario E — Error occurs yet rollback cannot recall an email

This is not a bug in the transaction manager: the email/API call sits outside the local DB transaction. Move side effects to post-commit processing or a transactional outbox, and define retry/compensation/idempotency per business requirements.

## 17. Cheat Sheet on Exceptions and Transaction Phases

| Listener / callback type | Timing | Typical exception path | Can roll back T1? |
|---|---|---|---|
| Synchronous `@EventListener` | Inside `publishEvent` | Propagates to publisher if uncaught | **Yes**, if not yet committed and rollback rules match |
| `@EventListener` with `@Async` | Separate worker thread | Worker's error handler/future | **Not automatically** |
| Custom multicaster `ErrorHandler` swallowing errors | Any dispatch controlled by handler | Logged/handled by handler | **May not roll back** since exception does not escape |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Before commit | Callback exception reaches transaction manager | **Yes** |
| `@TransactionalEventListener(AFTER_COMMIT)` | After commit | Post-completion, logged/post-processing error | **No** |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | After rollback | Post-completion | **No** |
| `@TransactionalEventListener(AFTER_COMPLETION)` | After commit or rollback | Post-completion | **No** |
| Direct `TransactionSynchronization.afterCommit()` | After commit | Exception can propagate to caller | **No** |
| Listener in its own `REQUIRES_NEW` | Inside transaction T2 | T2 per its own rollback rules | Can roll back **T2**; T1 depends on error path/timing |

**Two most important principles:**

1. **Rollback requires a transaction still capable of rolling back** and an error/rollback decision at the right transaction boundary.
2. **Post-commit exceptions are post-processing errors**, not a way to reverse already committed data.

## 18. Conclusion

Exceptions from a **synchronous** `@EventListener` inside a `@Transactional` call typically propagate through `ApplicationEventPublisher` and roll back the original transaction if unintercepted and matching rollback rules. Meanwhile, `@TransactionalEventListener(BEFORE_COMMIT)` can prevent a successful commit via an exception in its pre-commit callback; `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` execute **after the transaction has ended**, so they cannot roll back the original transaction even if errors occur.

Do not equate "an exception occurred" with "the database rolled back". Identify the **thread, phase, proxy, propagation, ErrorHandler, rollback rules, and actual transaction state**. Use an explicit workflow/transaction for critical business invariants; use an outbox/queue and idempotency when post-commit side effects must be executed reliably.

### Official Documentation

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — `@EventListener`, error handling, async, and ordering.
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener` and phases.
- [Spring Framework Javadoc 6.2.8 — EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html) — checked exception wrapping and async listeners.
- [Spring Framework Javadoc 6.2.8 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — behavior when no transaction is present and resources after completion.
- [Spring Framework Javadoc 6.2.8 — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — exceptions in `beforeCommit`, `afterCommit`, and `afterCompletion`.
- [Spring Framework 6.2 — Transaction Rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html) — rollback rules and checked/unchecked exceptions.
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html) — `REQUIRED`, `REQUIRES_NEW`, and `NESTED`.
