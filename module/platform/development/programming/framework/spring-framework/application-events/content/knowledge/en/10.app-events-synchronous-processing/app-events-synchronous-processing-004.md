# Synchronous Listeners Inside a Transaction — Spring Framework Application Events

## 1. Concept and Operating Conditions

In the Spring Framework, a **synchronous listener inside a transaction** is a listener invoked directly on the event-publishing thread at a point when an application transaction is still active. The classic case: a `@Transactional` service updates the database, calls `ApplicationEventPublisher.publishEvent(...)`, and an `@EventListener` handles the event right during service execution.

Core points:

- `@Transactional` manages the transaction boundary of the service method (via a Spring transaction proxy in the standard declarative model).
- `ApplicationEventPublisher` publishes the event; `ApplicationContext` forwards it to `ApplicationEventMulticaster`.
- `SimpleApplicationEventMulticaster` invokes listeners **synchronously on the same thread** as the publisher by default, unless an asynchronous executor is configured.
- An `@EventListener` typically **does not wait for commit** and **does not open a new transaction on its own**. If invoked while a thread-bound transaction is active, listener code can interact with that thread's transaction/resources.
- `@TransactionalEventListener` uses a separate mechanism: it registers handling for a transaction *phase*; by default it is `AFTER_COMMIT`, and it does not execute immediately at the `publishEvent()` call site.

Two concepts must be separated: **synchronous** answers *when/on which thread does the listener run?*, while **inside a transaction** answers *is a transaction active and which transaction do data operations belong to?*. A synchronous `@EventListener` still runs when there is **no** transaction; in that case, its operations cannot be assumed to share a common transaction.

## 2. Execution Flow and What "Same Transaction" Means

Consider a call to `orderService.createOrder(...)` going through a Spring proxy:

```text
Caller
  -> OrderService proxy
     -> BEGIN transaction
        -> OrderService.createOrder(...)
           -> INSERT order (not yet committed)
           -> publisher.publishEvent(OrderCreated)
              -> ApplicationContext
                 -> SimpleApplicationEventMulticaster
                    -> @EventListener onOrderCreated(...)
                       -> read/write DB in current transaction
                    <- listener completes
              <- publishEvent() returns
           -> continue processing in createOrder(...)
     -> COMMIT (or ROLLBACK on failure per rules)
  <- Caller
```

With imperative transactions managed by `PlatformTransactionManager`, Spring binds resources such as the JDBC `Connection` and transaction state to the current thread. If the synchronous listener uses the same `DataSource` and properly configured `JdbcTemplate`/repository, the listener's JDBC operations typically participate in **the same physical transaction** as the publisher:

- The listener can read data the publisher just wrote but has not yet committed using the same connection/transaction, even though other threads or connections might not see that data depending on isolation level.
- Writes from the publisher and listener are committed or rolled back together if they genuinely participate in the same transaction.
- If the listener throws a `RuntimeException` through `publishEvent()`, the `@Transactional` method can fail and the transaction rolls back under default rules.
- If the publisher continues after the listener finishes, the transaction has not necessarily committed yet; commit happens when the transaction interceptor finishes the outer call, or according to configured boundaries.

**This does not mean every listener shares the same transaction:** `@Async`, a multicaster using an executor, a different transaction manager/`DataSource`, or a method declared with `REQUIRES_NEW` can establish different boundaries. In reactive models, transactions propagate via the Reactor Context, so you cannot reason from thread-locals as in imperative examples.

## 3. Runnable Java 17+ Example: Commit Together, Roll Back Together on Error

This plain Spring Framework example (no Spring Boot required) uses an H2 in-memory database to demonstrate two things: a synchronous listener sees the publisher's uncommitted row, and a listener error can roll back both tables.

Create the project:

```text
transaction-event-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-event-demo'
```

`build.gradle` — Spring Framework 6.2.12, JDK 17+, Gradle 8+:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionEventDemo'
}
```

`src/main/java/demo/TransactionEventDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionEventDemo {

    public record OrderCreated(String orderId, boolean failInListener) {}

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(String orderId, boolean failInListener) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("publisher: inserted " + orderId);

            publisher.publishEvent(new OrderCreated(orderId, failInListener));
            System.out.println("publisher: after event " + orderId);
        }
    }

    public static class AuditListener {
        private final JdbcTemplate jdbc;

        public AuditListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onOrderCreated(OrderCreated event) {
            boolean active = TransactionSynchronizationManager
                    .isActualTransactionActive();

            Integer visible = jdbc.queryForObject(
                    "select count(*) from orders where id = ?",
                    Integer.class,
                    event.orderId());

            System.out.println(
                    "listener: " + event.orderId()
                    + ", tx=" + active
                    + ", visible=" + visible);

            if (event.failInListener()) {
                throw new IllegalStateException("audit failed");
            }

            jdbc.update(
                    "insert into audit(order_id) values (?)",
                    event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_events;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        AuditListener auditListener(JdbcTemplate jdbc) {
            return new AuditListener(jdbc);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);

            jdbc.execute("create table orders (id varchar(40) primary key)");
            jdbc.execute("create table audit (order_id varchar(40) primary key)");

            service.create("ok-1", false);
            System.out.println("after commit: orders=" + count(jdbc, "orders")
                    + ", audit=" + count(jdbc, "audit"));

            try {
                service.create("bad-1", true);
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }

            System.out.println("after rollback: orders=" + count(jdbc, "orders")
                    + ", audit=" + count(jdbc, "audit"));
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName only accepts the literals "orders" or "audit" in this example.
        return jdbc.queryForObject(
                "select count(*) from " + tableName,
                Integer.class);
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle -q run
```

The application's `System.out.println` lines output in order:

```text
publisher: inserted ok-1
listener: ok-1, tx=true, visible=1
publisher: after event ok-1
after commit: orders=1, audit=1
publisher: inserted bad-1
listener: bad-1, tx=true, visible=1
caught: audit failed
after rollback: orders=1, audit=1
```

Explaining the output:

1. `service` is retrieved from the Spring context, so calling `create(...)` goes through the transaction proxy enabled by `@EnableTransactionManagement`. Do not manually instantiate `new OrderService(...)` and expect `@Transactional` to work.
2. `@EventListener` executes right inside `publishEvent()`: the `listener: ...` line appears before `publisher: after event ...` in the successful run.
3. `tx=true` shows that at the moment the listener runs, an imperative transaction is active on that thread. `visible=1` shows the listener's JDBC query sees the newly inserted row inside the same transaction.
4. For `ok-1`, both `orders` and `audit` commit, leaving one row in each table.
5. For `bad-1`, the listener throws `IllegalStateException` before writing the audit record. The error propagates back through `publishEvent()` and the service; the transaction interceptor triggers a rollback. The `bad-1` record does not remain in `orders`; the table counts stay at `1,1`.
6. The `OrderCreated` event is just a Java record; Spring supports `publishEvent` for plain objects via payload events. Extending `ApplicationEvent` is unnecessary.

The example uses JDBC with the same `DataSourceTransactionManager` to highlight atomicity. In a JPA project, writes, flushes, and lazy loading also depend on `EntityManager`, flush mode, and persistence context boundaries; do not assume every SQL statement is sent immediately upon calling `save()`.

## 4. How Listener Errors Determine Rollback

With a synchronous multicaster **without an `ErrorHandler` configured**, an error thrown by a listener can propagate to the `publishEvent()` call and abort invocation of remaining listeners. Transaction rules when a `@Transactional` method exits:

| Scenario | Typical result |
| --- | --- |
| Listener finishes normally | Publisher continues; transaction commits when the boundary actually finishes successfully. |
| Listener throws `RuntimeException` or `Error`, uncaught | By default, the transaction interceptor marks rollback when the error escapes the `@Transactional` boundary. |
| Listener throws a checked exception and the transaction lets it propagate | By default, checked exceptions do not trigger rollback automatically unless `rollbackFor` or a suitable global rollback policy is configured. |
| Publisher catches and handles the error before exiting the transaction | Cannot assume rollback by default; you must explicitly check rollback-only status or other rules. |
| Multicaster's `ErrorHandler` logs and swallows the error | Publisher can continue without seeing an exception; the transaction does not roll back merely because the handler logged it. |
| Listener calls another service annotated with `@Transactional(REQUIRES_NEW)` | The independent new transaction can commit first; rolling back the original transaction does not undo data committed in the new transaction. |

Example configuring rollback for a checked exception on a service method:

```java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performOperation() throws BusinessRuleException {
    // Perform business logic, publish event, and let error propagate outward.
}
```

This is **illustrative code for a single method**, where `BusinessRuleException` is an application-defined checked exception. It is not a standalone compilable method; the complete runnable Java example is in section 3.

**Note on rollback-only:** If a method has its own transaction proxy, joins the current transaction via `REQUIRED`, marks it rollback-only after an error, and an outer layer catches the error and tries to commit, Spring can throw `UnexpectedRollbackException`. Therefore, clearly design who owns the transaction and the error policy; catching an exception does not guarantee you can continue and commit.

**Note on `ErrorHandler`:** `SimpleApplicationEventMulticaster#setErrorHandler(...)` lets a handler log, swallow, or rethrow errors. Swallowing the error allows other listeners to proceed, but does not satisfy business requirements if that error is supposed to roll back the transaction. If rollback is truly required, let the error propagate across the transaction boundary or use a suitable rollback-marking policy.

## 5. `@EventListener` and `@TransactionalEventListener`: Two Different Schedules

These two annotations are easily confused because both receive events and in default imperative applications both often run on the transaction thread.

```java
@EventListener
public void immediately(OrderCreated event) {
    // Runs immediately when publishEvent() invokes the listener.
}

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Runs in the pre-commit callback, not immediately at publishEvent().
}

@TransactionalEventListener // defaults to AFTER_COMMIT
public void afterCommit(OrderCreated event) {
    // Runs after the transaction commits successfully.
}
```

The three methods are **illustrative snippets** that belong inside Spring-managed beans; `OrderCreated` is the application's event type. Import `EventListener`, `TransactionalEventListener`, and `TransactionPhase` from Spring accordingly.

| Listener type | When it executes | What happens when a transaction exists? |
| --- | --- | --- |
| Regular `@EventListener` | Immediately when the multicaster dispatches the event | Can use the open transaction's resources on the same thread; commit is not yet guaranteed. |
| `@TransactionalEventListener(BEFORE_COMMIT)` | When Spring invokes the pre-commit callback | Can operate during the commit phase while the transaction is still active; errors here can prevent commit. |
| `@TransactionalEventListener(AFTER_COMMIT)` | After a successful commit | Runs only if committed; cannot roll back an already committed transaction. |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | After a rollback | Useful for recording/compensation; do not assume a new transaction exists for DB writes. |
| `@TransactionalEventListener(AFTER_COMPLETION)` | After transaction completion, commit or rollback | Used for cleanup regardless of outcome, or when distinguishing outcomes via explicit design. |

With `@TransactionalEventListener`, calling `publishEvent()` inside a transaction mainly registers the listener with transaction synchronization; the listener method runs during the specified phase. By default when **no transaction is active**, this kind of listener **is not invoked**; execution can be enabled via `fallbackExecution = true` if the design allows it.

After `AFTER_COMMIT`, transaction resources may remain bound to the thread while the callback runs. If the handler needs to make **a new DB write with its own commit**, call a method on **another Spring bean** annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` when appropriate, instead of expecting writes inside the callback to be committed again by the finished transaction. Invoke the method through a proxy; self-invocation via `this.method()` in the same bean can bypass the advice.

**Do not confuse `BEFORE_COMMIT` with "right when the event is published":** if a publisher calls `publishEvent()` multiple times inside a transactional method, `BEFORE_COMMIT` listeners are scheduled for the commit stage rather than executing inline at the publish site like `@EventListener`.

## 6. When Is Synchronous Processing Inside a Transaction Appropriate?

Choose a synchronous listener inside a transaction when **the task requires atomic consistency with the primary business action**, execution time is short, and listener failure should be able to fail the original operation. Examples: updating an internal audit table or projection in the same database and under the same transaction manager, with an explicit rollback policy.

If the task involves sending emails, making HTTP requests, push notifications, or publishing to a broker from a synchronous listener, weigh the consequences:

- An external system outside the database is not rolled back just because a JDBC transaction rolls back. A sent email cannot be recalled; a successful HTTP call can still happen before the DB rolls back.
- Slow I/O holds locks and connections longer, raising the risk of timeouts or deadlocks.
- A transient network error can roll back the primary operation if the exception propagates; conversely, swallowing the error can lose the task.
- If the external action should run only **after a successful commit**, consider `@TransactionalEventListener(AFTER_COMMIT)`; if **reliable delivery** across restarts/crashes is required, use a transactional outbox + worker/broker and design for idempotency and retries.

A common split is keeping atomic data updates in a synchronous listener while sending notifications in a post-commit listener or through an outbox. The important condition is defining clearly which state must commit together and which steps are allowed to fail independently.

## 7. Testing and Diagnostics

For database-backed examples, minimal tests should verify:

1. **Successful commit:** after the service call returns, both the publisher's and listener's data exist in the database.
2. **Listener failure:** an uncaught `RuntimeException` rolls back the transaction, and data written by the publisher in the same transaction is gone.
3. **Ordering:** the synchronous listener finishes before `publishEvent()` returns; assertions should rely on controlled state/call order rather than unrelated processing order.
4. **Calling outside a transaction:** an `@EventListener` is still invoked, but without shared transaction semantics; `@TransactionalEventListener` is not invoked by default.
5. **Exception configuration:** if using `ErrorHandler`, `rollbackFor`, `REQUIRES_NEW`, or a listener with its own transaction proxy, write tests for each configuration's actual behavior.
6. **Multiple listeners:** if the first listener throws an error, verify whether later listeners run according to the configured multicaster policy and error handling.

To inspect imperative transactions inside a listener:

```java
boolean actualTx =
        TransactionSynchronizationManager.isActualTransactionActive();
```

This value tells you Spring considers a transaction active on the **current thread**, not that every operation on every datasource uses the exact same physical transaction. To prove atomicity, assert the resulting data after commit/rollback as shown in the example.

Common mistakes:

- **Assuming `publishEvent()` runs after commit by default.** With a regular `@EventListener`, a synchronous listener runs immediately while the transaction may not have completed yet.
- **Annotating `@Transactional` but invoking `this.create(...)` internally.** Under default proxy mode, self-invocation typically bypasses the transaction interceptor.
- **Using `@Async` or an executor on a listener while still expecting the same thread/connection/rollback.** Thread-bound transactions do not automatically transfer to an executor.
- **Assuming listener errors always roll back.** It depends on whether the exception escapes, rollback rules, transaction proxies, and `ErrorHandler`.
- **Calling a REST API or sending an email directly in a listener while assuming rollback cancels external effects.** JDBC transactions do not have that capability.
- **Using `@TransactionalEventListener(AFTER_COMMIT)` to write to the DB without starting a new transaction.** A post-commit callback does not trigger another commit for new writes.
- **Thinking `@Order` controls commit order.** `@Order` only affects listener order in the applicable dispatch/callback mechanism; transaction boundaries belong to the transaction manager.

## 8. Design Takeaways

A **synchronous** `@EventListener` invoked from `publishEvent()` inside a `@Transactional` service is a solid tool for short internal operations that must roll back together. In that setup, the listener participates in business execution **before commit**. `@TransactionalEventListener` is meant for work tied to transaction **outcomes or phases** such as `BEFORE_COMMIT`/`AFTER_COMMIT`. If durability and delivery to external systems are required, in-memory events should be complemented by an outbox or an appropriate messaging system.

Official Spring documentation:

- [ApplicationContext Events and synchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Transaction-bound Events and `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [`@Transactional` settings and rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Declarative transaction: rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
