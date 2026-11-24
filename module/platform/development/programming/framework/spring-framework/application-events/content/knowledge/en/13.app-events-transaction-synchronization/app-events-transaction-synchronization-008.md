# REQUIRES_NEW When a Listener Needs to Write Data

## 1. Why does writing data inside a post-commit listener require care?

Suppose `OrderService` saves an order inside transaction **T1**, then publishes `OrderCreatedEvent`. The application uses `@TransactionalEventListener` to write an audit log, update a notification table, or create an integration record only when the order **has committed successfully**.

~~~text
OrderService.createOrder()
    ├─ BEGIN T1
    ├─ INSERT orders
    ├─ publishEvent(OrderCreatedEvent)
    │      └─ registers event handling with the current transaction
    └─ COMMIT T1 succeeds
           └─ @TransactionalEventListener(AFTER_COMMIT)
                  └─ needs INSERT audit_log via new transaction T2
                         ├─ BEGIN T2
                         ├─ INSERT audit_log
                         └─ COMMIT T2
~~~

**Trap:** at the moment the `AFTER_COMMIT` listener runs, transaction T1 has already committed, yet transaction resources (such as the JDBC connection or persistence context) **may still be bound to the thread** before Spring completes cleanup. A data-write command invoked directly in the callback may continue "participating" in the just-ended transaction's resource, **while there is no subsequent commit** for that resource. Thus, `save()` or `jdbcTemplate.update()` executing without error **does not guarantee the data will be committed**.

This is a direct warning in the Javadoc of `TransactionalEventListener` and `TransactionSynchronization`. When a post-commit listener needs to write data durably, you must ensure the write actually runs inside an **independent transaction with its own commit**, typically using `Propagation.REQUIRES_NEW`.

## 2. Distinguishing event handling timing from propagation

`@TransactionalEventListener` selects **when the callback runs** relative to the event-publishing transaction. `@Transactional(propagation = ...)` selects **how a transaction is established** for the method performing business work.

| Configuration | Meaning | Relation to write operations |
| --- | --- | --- |
| `@EventListener` | Handles immediately when the event is published, per standard multicaster behavior | If published inside T1 and the listener runs on the same thread, writes can join T1; if T1 rolls back, they roll back together |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Handles before T1 commits | Appropriate when data should be written **within T1** and failures must prevent T1 from committing |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Handles after T1 commits successfully; this is the **default** | To write new DB data, open T2 with `REQUIRES_NEW` |
| `@TransactionalEventListener(phase = AFTER_ROLLBACK)` | Handles after T1 rolls back | To persist a failure log that survives, a new transaction must be used |
| `@TransactionalEventListener(phase = AFTER_COMPLETION)` | Handles after T1 completes whether commit or rollback | If writing to DB, consider an independent transaction and distinguish business outcome |

**Do not confuse:** `AFTER_COMMIT` **does not automatically create a new transaction**. `REQUIRES_NEW` **does not make an event wait until after commit**. The two behaviors address two different concerns.

### REQUIRED and REQUIRES_NEW

- `Propagation.REQUIRED` (default of `@Transactional`) joins an existing transaction if Spring sees a suitable one; inside a post-commit callback, old transaction resources may still be bound to the thread. Merely wrapping the write call with default `@Transactional` **is not** a safe fix.
- `Propagation.REQUIRES_NEW` creates a new, independent physical transaction. Spring suspends the transaction context currently bound to the thread (if any), acquires resources for the new transaction, and commits/rolls back that transaction on its own.
- `Propagation.NESTED` uses a savepoint inside the current physical transaction when supported; it cannot satisfy the requirement for an **independent commit after T1 has committed**.

## 3. Recommended implementation pattern: listener calls another service

Split responsibilities into three Spring beans:

1. `OrderService` with `@Transactional`, creates the order and publishes the event.
2. `OrderEventListener` with `@TransactionalEventListener(AFTER_COMMIT)`, determines handling timing.
3. `AuditWriter` with `@Transactional(propagation = Propagation.REQUIRES_NEW)`, executes the audit INSERT inside T2.

The key is that **the listener invokes a public method on another Spring bean** so the call passes through the transactional proxy. When calling `this.persistAudit(...)` within the same bean, in normal proxy mode Spring cannot intercept self-invocation, so `@Transactional` on the internally called method may have no effect.

## 4. Runnable Java 17+ example: commit creates audit, rollback does not

The example below uses **Spring Framework 6.2.19**, Spring JDBC, and in-memory H2. Spring Boot is not needed; `AnnotationConfigApplicationContext` is used to clearly show transaction and event configuration. This is a standalone demo project; classes are placed in one file for convenience.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'transactional-listener-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-jdbc:6.2.19'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.DemoApp'
}
~~~

Create `src/main/java/demo/DemoApp.java`:

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = DemoApp.class)
public class DemoApp {

    @Bean
    DataSource dataSource() {
        var source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:txevents;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(DemoApp.class)) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");
            jdbc.execute(
                "CREATE TABLE audit_log (order_id BIGINT, detail VARCHAR(100))"
            );

            var orderService = context.getBean(OrderService.class);

            // T1 commits: AFTER_COMMIT listener creates audit record via T2.
            orderService.createOrder(101L, false);

            // T1 rolls back: AFTER_COMMIT listener is not invoked.
            try {
                orderService.createOrder(102L, true);
            } catch (IllegalStateException ex) {
                System.out.println("rolled back 102");
            }

            System.out.println("orders=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM orders", Integer.class));
            System.out.println("audit=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM audit_log", Integer.class));
        }
    }
}

// Event carries ID only: listener queries once a new transaction is active.
record OrderCreatedEvent(long orderId) {}

@Component
class OrderService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    OrderService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder(long orderId, boolean forceRollback) {
        jdbc.update("INSERT INTO orders (id) VALUES (?)", orderId);
        publisher.publishEvent(new OrderCreatedEvent(orderId));

        if (forceRollback) {
            throw new IllegalStateException("Simulated rollback");
        }
    }
}

@Component
class OrderEventListener {
    private final AuditWriter writer;

    OrderEventListener(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCommitted(OrderCreatedEvent event) {
        writer.writeAudit(event.orderId()); // Goes through another bean's proxy.
        System.out.println("audit saved for " + event.orderId());
    }
}

@Component
class AuditWriter {
    private final JdbcTemplate jdbc;

    AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        jdbc.update(
            "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
            orderId,
            "CREATED"
        );
    }
}
~~~

Run from the directory containing `build.gradle`, with JDK 17+ and Gradle installed, or using the project's Gradle Wrapper:

~~~bash
gradle run --quiet
# Or: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

Lines printed by the program itself (there may be additional runtime environment logs):

~~~text
audit saved for 101
rolled back 102
orders=1
audit=1
~~~

**Result interpretation:**

- **Order 101:** `OrderService.createOrder(101, false)` inserts into `orders` and publishes the event in T1. After T1 commits, `OrderEventListener` calls `AuditWriter`. `REQUIRES_NEW` starts T2, inserts into `audit_log`, and commits T2. The result is one order and one audit record.
- **Order 102:** the method throws `IllegalStateException` before commit; the transaction interceptor rolls back T1. Because the listener is only registered for `AFTER_COMMIT`, it does not handle this event. There is no order 102 and no audit 102.
- **What to observe:** the program verifies **committed data with a separate query after the service finishes**, rather than just looking at a "save called" message.

**Related mechanism:** Spring can publish an object that does not extend `ApplicationEvent`. In this case Spring wraps the payload to dispatch through the event infrastructure; listeners can accept a parameter of exact type `OrderCreatedEvent`.

## 5. Why is writing straight to the DB in AFTER_COMMIT wrong?

The following is a **design flaw example**, not included simultaneously in section 4's demo:

~~~java
@Component
class UnsafeAuditListener {
    private final JdbcTemplate jdbc;

    UnsafeAuditListener(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @TransactionalEventListener // defaults to AFTER_COMMIT
    public void onOrderCreated(OrderCreatedEvent event) {
        jdbc.update(
            "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
            event.orderId(), "CREATED"
        );
    }
}
~~~

This snippet **may execute past the UPDATE statement without throwing an error**, yet while T1's transaction resources are still bound to the callback, the write operation can participate in a context that has no remaining commit pass. Do not rely on a particular JDBC/JPA version or database accidentally exposing the data.

Another misleading variant:

~~~java
@TransactionalEventListener
@Transactional // defaults to Propagation.REQUIRED
public void onOrderCreated(OrderCreatedEvent event) {
    repository.save(new AuditLog(event.orderId()));
}
~~~

In modern Spring Framework, configuring a post-commit `@TransactionalEventListener` together with `@Transactional` that is **not** `REQUIRES_NEW` or `NOT_SUPPORTED` can even be rejected by Spring right at listener registration time. Even if not rejected in an older setup, `REQUIRED` is still not an independent post-commit write transaction.

**Fix:** keep `AFTER_COMMIT` on the listener, and call a service with `REQUIRES_NEW` (as in section 4's example). For JPA operations, put `repository.save(...)` inside the new service rather than relying on the `EntityManager` session just used for T1.

## 6. Conditions for REQUIRES_NEW to actually take effect

| Scenario | What to check |
| --- | --- |
| Listener calls `this.saveAudit()` on its own bean | Self-invocation can bypass the Spring proxy; extract a service or use `TransactionTemplate` |
| Write method is called on an object created with `new` outside Spring | There is no Spring proxy to open a transaction; obtain the bean from the container |
| Bean/method incompatible with the active proxy mechanism | Use a public method that can be intercepted; avoid relying on private/final methods in regular proxies |
| Annotation only on an interface or proxy config changed | Verify how Spring detects transaction metadata and the actual proxy type |
| Using multiple databases / transaction managers | Select the right `PlatformTransactionManager` managing the target datasource; transaction independence does not mean distributed transaction |
| Event published outside a transaction | By default `@TransactionalEventListener` **is not called**, since there is no transaction phase to attach to |
| Listener runs asynchronously | Thread transaction context does not automatically move to another thread; design clear transaction boundaries in the handler flow |

If you do not want to rely on proxies, you can create a transaction programmatically inside the listener/service via `TransactionTemplate`:

~~~java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_log (order_id, detail) VALUES (?, ?)",
        event.orderId(), "CREATED"
    );
});
~~~

This is an **illustrative snippet embedded in a method**; it requires appropriate `transactionManager`, `jdbcTemplate`, and `event` variables along with imports for `org.springframework.transaction.support.TransactionTemplate` and `org.springframework.transaction.TransactionDefinition`. It is not a standalone runnable Java file. This approach is especially useful when you need precise programmatic transaction boundary control right inside the callback.

## 7. When should you NOT use AFTER_COMMIT + REQUIRES_NEW?

**Business requirement to succeed or fail together:** if the audit record is a mandatory part of the same order-saving operation and both should roll back on failure, write the audit **inside T1** (for example directly from the service or via a `BEFORE_COMMIT` listener with the proper transaction). `AFTER_COMMIT + REQUIRES_NEW` does not guarantee atomicity across two commits.

**Wanting to record errors after rollback:** use `AFTER_ROLLBACK` and open a separate transaction to save a failure log, while being careful not to let a logging failure mask the root cause.

**Wanting guaranteed integration processing even if the process dies:** the `AFTER_COMMIT` callback is an in-memory in-process mechanism. T1 may commit and the application may crash before T2 finishes; the event and audit/integration task can be lost. For reliable delivery to external systems, consider a **transactional outbox**: write an outbox record **in T1**, then have an independent worker read, deliver, and retry. `REQUIRES_NEW` does not turn a local event into a durable queue.

**Concerned about duplicate processing:** listeners or retry jobs may be re-invoked; design audit/inbox/outbox persistence with unique business keys or idempotent operations if needed. `REQUIRES_NEW` only guarantees a new transaction, **not exactly-once**.

**Constrained by connection pool:** `REQUIRES_NEW` needs an independent resource. When an outer transaction holds a connection and an inner transaction must acquire another, a pool that is too small can run out of connections or cause mutual waiting. Spring documentation recommends a pool with at least one more connection than the number of concurrent threads in that pattern. The demo uses simple `DriverManagerDataSource` without a connection pool for easy observation.

## 8. Debug checklist when the listener reports saved but the DB has no row

1. Confirm the listener method actually ran after a **successful commit**: check `phase` and whether the event-publishing transaction rolled back.
2. Check whether the event was published from a **Spring-managed transaction**. Without a transaction, the listener is skipped by default; `fallbackExecution = true` changes behavior and must be weighed explicitly.
3. Inspect transaction logs (DEBUG for `org.springframework.transaction`) to see if a **new transaction** opened and committed separately in the write method. Logs depend on the transaction manager and logging setup.
4. Confirm the `REQUIRES_NEW` method was called **through a Spring proxy**, choosing the right transaction manager, without self-invocation.
5. Read the DB using a different transaction/connection **after the callback completes**. Do not take a "repository.save() returned" log as proof of commit.
6. If exceptions or missing audits appear in a subset of requests, remember that once T1 commits, a T2 failure **cannot revert T1**. Decide retries/error logging/alerts per business rules.
7. With JPA, verify actual `flush` and commit; `save` and `flush` are not synonymous with an independent commit.

### Behavior summary

~~~text
@Transactional publisher
    + @TransactionalEventListener(AFTER_COMMIT)
    + @Transactional service(REQUIRES_NEW)
    = Runs listener after T1 commits;
      the listener's write has an independent T2 to commit.

AFTER_COMMIT does not automatically open T2.
REQUIRES_NEW does not change when the listener triggers.
T2's commit cannot roll back or "merge back into" T1's commit.
~~~

### Official documentation

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Transaction Propagation, REQUIRES_NEW](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Javadoc – TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc – TransactionSynchronization.afterCompletion](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
