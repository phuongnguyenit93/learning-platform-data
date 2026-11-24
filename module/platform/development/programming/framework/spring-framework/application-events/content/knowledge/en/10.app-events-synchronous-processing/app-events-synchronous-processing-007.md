# Ensuring Consistency Within a Use Case Using Synchronous Spring Application Events

## 1. From a Business Flow to Consistency Requirements

Suppose an **order creation** use case consists of two steps: inserting the order into the database and reserving inventory stock. The business rule is that **no order may succeed if mandatory stock reservation is rejected**. One way to organize this is for the use case to save the order, publish an `OrderCreated` event, and let a listener handle stock reservation.

~~~text
OrderUseCase.createOrder(...)
    |
    +-- INSERT orders
    |
    +-- publishEvent(OrderCreated)
    |       |
    |       +-- InventoryListener.reserve(...)
    |               |
    |               +-- INSERT reservations / throw if insufficient stock
    |
    +-- complete use case and transaction
~~~

With synchronous processing, `publishEvent(...)` returns after regular listeners have finished. If a listener throws an error and the error is not swallowed, the use case can fail. However, **synchronous execution does not create a transaction automatically**: if individual writes already autocommitted, a later error does not automatically undo earlier records.

Three levels of guarantee must be distinguished:

1. **Ordering:** the listener task finishes before the use case returns success.
2. **Error propagation:** a mandatory listener's error reaches the use case coordinator.
3. **Data atomicity:** related data operations commit together or roll back together inside a real transaction.

The first two levels are matters of **how events are published and handled**; the third requires appropriate **transaction boundaries, resources, and rollback rules**.

## 2. How Does Spring Process Synchronous Events?

`ApplicationEventPublisher.publishEvent(Object)` publishes an event within the scope of an `ApplicationContext`. With the default configuration, `SimpleApplicationEventMulticaster` invokes regular listeners on the event-publishing thread itself. Spring discovers `@EventListener` methods on beans in the context; the payload can be a POJO or Java record, without needing to extend `ApplicationEvent`.

~~~java
public record OrderCreated(long orderId, int quantity) { }

@EventListener
public void onOrderCreated(OrderCreated event) {
    // Synchronous processing under the default multicaster configuration.
}
~~~

The snippet above illustrates a method inside a registered listener bean. For a type-compatible event, Spring invokes the listener; only after the listener returns does `publishEvent` finish. If the listener throws a `RuntimeException` and no `ErrorHandler` handles it to continue, the exception propagates out of the `publishEvent` call. Subsequent listeners in that multicast pass may not be called.

This is the **default** behavior, which must be re-evaluated if the application:

- marks the listener `@Async` or configures a `TaskExecutor` on the multicaster;
- attaches an `ErrorHandler` that logs and swallows exceptions;
- uses a transaction-phase listener such as `@TransactionalEventListener`;
- calls external services or spawns new threads inside the listener.

When switching to asynchronous execution, the listener may run after `publishEvent` has already returned; its errors no longer propagate automatically to the original call, and the transaction bound to the original thread does not automatically follow.

## 3. Why Is the Same Transaction Needed?

Local transactions in Spring typically bind resources (such as a JDBC `Connection`) to the executing thread. If the use case opens a transaction before publishing the event, and the synchronous listener uses the **same transaction manager / DataSource** through Spring's mechanisms, JDBC statements can participate in the same transaction.

~~~text
BEGIN
  INSERT orders
  publishEvent(...)
      listener: INSERT reservations
  -- all succeeded
COMMIT

BEGIN
  INSERT orders
  publishEvent(...)
      listener: throw IllegalStateException
  -- error propagates out of use case
ROLLBACK
~~~

**Conditions that must hold for a full rollback:** the transaction wraps the event-publishing operation; the listener actually runs synchronously; data operations participate in the same physical transaction; errors are not swallowed; rollback rules apply to the error. A synchronous listener writing to **another non-transactional DataSource** can still commit independently.

With Spring's default `@Transactional`, `RuntimeException` and `Error` trigger rollback; checked exceptions do not trigger rollback automatically without additional configuration. With `TransactionTemplate`, a runtime exception escaping the callback causes the transaction to roll back. Distinguish `PROPAGATION_REQUIRED` (typically joins an existing transaction) from `REQUIRES_NEW` (an independent physical transaction that can commit separately).

## 4. Runnable Java 17 Example: Commit and Rollback with a Synchronous Listener

This program uses **Spring Framework 6.2.8**, Spring JDBC, and H2 in-memory; **no Spring Boot required**. The transaction is created using `TransactionTemplate` directly inside the use case to keep boundaries explicit. The listener uses `JdbcTemplate` sharing the same DataSource. A valid order commits both tables; an order with insufficient stock rolls back both operations for that run.

### 4.1. Structure and Dependencies

~~~text
spring-event-consistency/
├── pom.xml
└── src/main/java/UseCaseConsistencyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>spring-event-consistency</artifactId>
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
        <version>3.3.0</version>
        <configuration>
          <mainClass>UseCaseConsistencyDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 4.2. Complete Source Code

File `src/main/java/UseCaseConsistencyDemo.java`:

~~~java
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
import org.springframework.transaction.support.TransactionTemplate;

public final class UseCaseConsistencyDemo {

    public record OrderCreated(long orderId, int quantity) { }

    public static final class OrderUseCase {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher events;

        public OrderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.events = events;
        }

        public void createOrder(long id, int quantity) {
            transactions.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (id, qty) VALUES (?, ?)",
                    id, quantity
                );

                // Listener runs before the transaction callback finishes.
                events.publishEvent(new OrderCreated(id, quantity));
            });
        }
    }

    public static final class InventoryListener {
        private final JdbcTemplate jdbc;

        public InventoryListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void reserve(OrderCreated event) {
            if (event.quantity() > 5) {
                throw new IllegalStateException("Insufficient stock");
            }

            jdbc.update(
                "INSERT INTO reservations (order_id, qty) VALUES (?, ?)",
                event.orderId(), event.quantity()
            );
            System.out.println("RESERVED order=" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:usecase;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactions(PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        OrderUseCase orderUseCase(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events
        ) {
            return new OrderUseCase(jdbc, transactions, events);
        }

        @Bean
        InventoryListener inventoryListener(JdbcTemplate jdbc) {
            return new InventoryListener(jdbc);
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // Only used with fixed table names in this demo program.
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table, Integer.class
        );
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, qty INT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE reservations (" +
                "order_id BIGINT PRIMARY KEY, qty INT NOT NULL)"
            );

            OrderUseCase useCase = context.getBean(OrderUseCase.class);

            useCase.createOrder(1L, 2);
            System.out.println(
                "AFTER OK: orders=" + count(jdbc, "orders") +
                ", reservations=" + count(jdbc, "reservations")
            );

            try {
                useCase.createOrder(2L, 8);
            } catch (IllegalStateException ex) {
                System.out.println("FAILED: reservation rejected");
            }

            System.out.println(
                "FINAL: orders=" + count(jdbc, "orders") +
                ", reservations=" + count(jdbc, "reservations")
            );
        }
    }
}
~~~

Run from the project directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

`stdout` printed by the program itself (excluding environment-specific Maven messages):

~~~text
RESERVED order=1
AFTER OK: orders=1, reservations=1
FAILED: reservation rejected
FINAL: orders=1, reservations=1
~~~

### 4.3. Tracing Each Transaction

**Order 1:** `createOrder(1, 2)` opens a transaction. `orders` gets row `id=1`, the listener receives `OrderCreated` synchronously, checks that quantity does not exceed 5, and inserts into `reservations`. `executeWithoutResult` finishes normally, so the transaction commits. Both tables have one row.

**Order 2:** `createOrder(2, 8)` opens another transaction and provisionally inserts into `orders`. The listener throws `IllegalStateException` before writing `reservations`. The exception propagates back through `publishEvent` to `TransactionTemplate` and rolls back the transaction. The second order does not exist after rollback; the first order's row remains. Therefore the final row count remains `1` in both tables.

In the demo, the `JdbcTemplate` instances for the use case and listener share the same `DataSource`. `DataSourceTransactionManager` binds the transactional JDBC Connection to the current thread, and the listener runs on that exact thread. If a developer substitutes a different DataSource or transaction manager without designing distributed transactions, "rolling back together" is no longer guaranteed by default.

**Note:** the line `RESERVED order=1` is printed before the transaction actually commits. Printing logs, sending emails, or making external HTTP calls are not operations that can be rolled back alongside the DB. The example intentionally does not simulate concurrent stock contention; a real system needs DB constraints, locks, or version checks to protect data across parallel requests.

## 5. Applying with `@Transactional` in a Spring Application

Real applications typically use annotations rather than `TransactionTemplate`:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void checkout(CheckoutCommand command) {
        Order order = orders.save(Order.from(command));
        events.publishEvent(
            new OrderCreated(order.getId(), command.quantity())
        );
    }
}
~~~

This is an **illustrative snippet dependent on application code**, requiring types `OrderRepository`, `Order`, `CheckoutCommand`, and imports for `Service`, `Transactional`, and `ApplicationEventPublisher`. To ensure the listener is part of the transaction, confirm that:

- Transaction management is configured and calls to `checkout` pass through the Spring transaction proxy; calls like `this.checkout(...)` inside the same bean can bypass the proxy.
- Data operations in the listener use a compatible transaction manager/resource. `Propagation.REQUIRED` is the default and usually fits; `REQUIRES_NEW` always opens a separate physical transaction.
- The listener completes synchronously and critical errors are not caught and ignored.
- Rollback rules match: default rollback occurs on `RuntimeException`/`Error`; if checked exceptions should also trigger rollback, use `rollbackFor` or an equivalent policy.
- The event is published **inside** the transactional method before the transaction boundary ends. If published after the `@Transactional` method has returned, the transaction may already have committed.

For a mandatory step preserving a core invariant, **calling `InventoryService.reserve(...)` directly from the use case** is also a good design and often easier to trace. Synchronous events are helpful when the event expresses a business fact and the listener is an allowed participant in the workflow; avoid hiding a critical step behind an event where readers of the use case cannot notice it.

## 6. Multiple Listeners, Ordering, and Error Rules

One event can have multiple listeners: reserving stock, writing audit logs, updating metrics, and sending notifications. Categorize them by consistency boundary:

| Action | Organization |
| --- | --- |
| Writing order and reserving stock in the same DB, both mandatory | Same transaction in the use case, synchronous handling or direct service call |
| Mandatory audit write in the same DB | Join the same transaction if missing audit must roll back the use case |
| Sending email, HTTP, webhook | After commit, with retry/idempotency or outbox if durability is required |
| Updating recoverable caches/metrics | Can be after commit or eventual consistency |
| Sending messages to external systems | Transactional outbox if preventing message loss between commit and send is needed |

### `@Order` Does Not Create Atomicity

`@Order` can control listener invocation order according to multicaster rules, yet Listener A running before B does not mean A rolls back if B fails. Only operations sharing the transaction are coordinated by the transaction manager for commit/rollback. If B calls an external service before failing, the DB transaction cannot automatically reverse that call.

### Be Careful When Catching Exceptions

If a listener catches a stock reservation error, merely logs it, and returns normally, the use case may commit the order. If you customize `SimpleApplicationEventMulticaster.setErrorHandler(...)` with a handler that swallows errors, exceptions from listeners may likewise fail to reach the use case. For **mandatory** steps, propagate failures or mark rollback appropriately. Listeners ordered after an unhandled exception may not be invoked; do not use listener execution counts as a delivery/retry guarantee.

### JPA and Flush Timing

With JPA, `save(...)` does not guarantee SQL has executed before publishing the event; the EntityManager may flush later. A synchronous listener in the same transaction can still see the shared persistence context, yet SQL queries, constraint checks, or other listeners can depend on flush timing. Understand flush modes and data boundaries; do not assume "event runs after save" means "all changes have committed to the DB."

## 7. `@TransactionalEventListener` Is a Different Contract

Synchronous `@EventListener` and `@TransactionalEventListener` have different execution timings:

| Annotation | Timing | Impact on consistency |
| --- | --- | --- |
| Default synchronous `@EventListener` | Immediately inside `publishEvent` | Can participate in the active transaction; exceptions can cause rollback |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Pre-commit phase | Runs right around commit, not identical to running immediately upon publish |
| `@TransactionalEventListener` default `AFTER_COMMIT` | After successful commit | Suitable for post-processing; errors cannot roll back an already committed transaction |
| `@TransactionalEventListener(phase = AFTER_ROLLBACK)` | After rollback | Can observe failures or perform compensation |
| `@Async` listener | Potentially on a separate thread | Does not automatically share thread-bound transactions or exceptions with the publisher |

Example post-commit notification listener:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyAfterCommit(OrderCreated event) {
        // Runs only after the event-publishing transaction commits successfully.
    }
}
~~~

This is illustrative code requiring imports for `Component`, `TransactionalEventListener`, `TransactionPhase`, and the event type. By default, `@TransactionalEventListener` binds callbacks only when a transaction is active; events published outside a transaction can be skipped unless `fallbackExecution` is configured.

**Do not use `AFTER_COMMIT` to replace a mandatory step that must roll back with the order**: by that point, the order data has already committed. If a post-commit callback needs to make a new DB write, note that old transaction resources may still be bound to the thread with no further commit planned for them; establish a new transaction intentionally. Post-commit notifications are also not a durable queue: the process can crash right after commit before the notification is sent.

For reliable communication with external systems, one solution is a **transactional outbox**: write an outbox record in the same transaction as the business data, then have a separate worker read and retry sending on failure. Combine with idempotency on the receiver side to prevent duplicate effects on retries.

## 8. Verifying Use Case Consistency

Check **state after the transaction has ended**, rather than merely asserting that a listener was invoked. Important cases:

| Test case | Expected confirmation |
| --- | --- |
| All steps succeed | Both tables hold data after commit |
| Listener throws `RuntimeException` | No partial data remains from the failed use case |
| Listener catches and swallows error | Test catches the risk of unintended commit |
| Listener uses `REQUIRES_NEW` | Separate transaction can commit or roll back independently of parent transaction |
| Listener annotated with `@Async` | Different timing and transaction; exceptions do not propagate directly |
| Sending email before rollback | Email is not rolled back by the DB; requires redesign |
| Two orders contending for stock | DB constraints/locking/versioning still protect inventory balances |

If a `@Transactional` annotation wraps the entire test method, that test can obscure the use case's true commit outcome. Create test cases without an outer test transaction, or end the transaction before querying data. In the example program, the line `FINAL: orders=1, reservations=1` proves order `2` rolled back while order `1` committed.

You can use `TransactionSynchronizationManager.isActualTransactionActive()` to observe whether a transaction is present on the thread at the publish point and inside the listener. However, `true` alone does not prove **all resources** share the same physical transaction; you must inspect the transaction manager, DataSource, propagation settings, and actual persisted data.

## 9. Common Mistakes and How to Avoid Them

1. **Assuming synchronous means atomic:** add transactions at the use case level and verify rollback via persisted data.
2. **Publishing events after the transaction has finished:** publish inside the transaction boundary if listeners must participate.
3. **Swallowing errors in mandatory steps:** exceptions must affect the use case result or transaction.
4. **Putting `@Async` on a listener that must roll back with the use case:** the new thread normally does not share the old transaction.
5. **Using `REQUIRES_NEW` casually:** an independent transaction can commit before the main use case rolls back.
6. **Calling external systems while a transaction is open:** emails, HTTP calls, and messages may already occur even if the database rolls back; consider after-commit, outbox, and compensation.
7. **Confusing listener order with a reliable business workflow:** use an orchestrator/service when steps are tightly coupled and cannot be skipped.
8. **Ignoring concurrency across requests:** a single use case's transaction does not eliminate race conditions between concurrent use cases.
9. **Using `AFTER_COMMIT` to check mandatory commit preconditions:** by the time the callback runs, commit has already finished.
10. **Confusing internal events with message queues:** Spring does not store and replay every event if a listener fails.

## 10. Practice Questions

1. If you remove `TransactionTemplate` from the example and let `JdbcTemplate.update` autocommit, could order `2` remain in the DB after the listener fails? Why?
2. If you put `@Async` on `InventoryListener.reserve`, is `try/catch` in `main` still guaranteed to catch errors from the listener?
3. When does a synchronous `@EventListener` share the same transaction as the use case, and why is "same thread" still insufficient if the listener uses a different DataSource?
4. Why is `@TransactionalEventListener(AFTER_COMMIT)` suitable for sending notifications yet unsuitable for a mandatory stock-reservation step that must roll back with the order?
5. If an external payment REST API is called mid-transaction, does a DB rollback cancel the external transaction? If not, would you choose idempotency, an outbox, saga/compensation, or another design?

**Hints:** (1) already autocommitted rows do not roll back automatically; (2) async does not propagate exceptions directly back to the publisher; (3) requires the same transaction manager/resource and compatible propagation; (4) data has already committed before the callback; (5) DB rollback affects only transactional resources; external calls require separate reliability contracts.

## References

- Spring Framework Reference, *Application Events and Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc, *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
