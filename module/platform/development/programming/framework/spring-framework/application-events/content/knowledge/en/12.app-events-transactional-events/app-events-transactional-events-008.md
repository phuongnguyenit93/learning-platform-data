# fallbackExecution and Fallback Behavior

`@TransactionalEventListener` binds application event handling to a transaction phase. By default, the listener only runs when Spring can register a callback with the current transaction; the default phase is `TransactionPhase.AFTER_COMMIT`. If an event is published outside a matching transaction, the listener is skipped.

The `fallbackExecution` attribute allows choosing the behavior when transaction synchronization cannot be registered. When `fallbackExecution = true` is set, Spring invokes the listener immediately during event dispatch. This is immediate execution when there is no transaction, not creating a substitute transaction and not waiting for the next transaction.

Important point: if a transaction is active and Spring succeeds in registering synchronization, fallback is not used. The listener still runs according to the declared phase. This article explains this behavior in Spring Framework 6.2, common misunderstandings, and a Java 17 example testing out-of-transaction publishing, commit, and rollback.

## 1. Default Behavior When There Is No Transaction

~~~java
@TransactionalEventListener
public void handleOrderCreated(OrderCreated event) {
    System.out.println("Order created: " + event.orderId());
}
~~~

Omitting `phase` means `AFTER_COMMIT`. Spring only invokes the method when the event is published inside a transaction that the listener can bind to. If there is no transaction, the listener is skipped.

Example:

~~~java
applicationEventPublisher.publishEvent(
        new OrderCreated("ORD-133"));
~~~

If this call takes place outside a transaction, the listener above does not run. Spring does not hold the event to process when another transaction starts, nor does it automatically open a new transaction.

According to the Spring Framework 6.2.0 Javadoc, an event published outside an active transaction is discarded for transactional listeners unless `fallbackExecution` is enabled. This behavior is specific to this listener; regular `@EventListener` or other listeners can still receive the same event.

## 2. What Does fallbackExecution Do?

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void handleOrderCreated(OrderCreated event) {
    System.out.println("Order created: " + event.orderId());
}
~~~

When Spring cannot register the listener with transaction synchronization, `fallbackExecution = true` allows processing the event immediately in the current dispatch pass.

| State at dispatch | fallbackExecution | Behavior |
|---|---:|---|
| Matching transaction exists, synchronization registered | false or true | Registers callback and waits for phase |
| No matching transaction | false | Skips listener |
| No matching transaction | true | Invokes listener immediately |

`fallbackExecution` is not an "always run immediately" flag. It only decides the execution branch when Spring cannot bind the event to a transaction.

### 2.1. Fallback Does Not Create a Transaction

If an event is published outside a transaction and fallback is enabled, the listener method runs without the publisher's transaction:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void sendNotification(OrderCreated event) {
    notificationClient.send(event.orderId());
}
~~~

Enabling fallback does not automatically create a transaction for database operations in the method. If the listener needs to write to the database in a separate transaction, call a service with an appropriate transaction. Fallback does not automatically create a new transaction for the listener.

### 2.2. Fallback Is Not a Queue

When fallback is disabled, the event is not retained to run in the next transaction. When fallback is enabled, the event is processed immediately. There is no pending state for Spring to automatically replay when the application opens a transaction.

If you need to persist events for later processing, retries, or recovery after a process restart, use a message broker or a transactional outbox.

### 2.3. Fallback Affects Only the Marked Listener

An event can have both regular listeners and transactional listeners:

~~~java
@EventListener
public void updateMetrics(OrderCreated event) {
    // Regular listener.
}

@TransactionalEventListener
public void updateAfterCommit(OrderCreated event) {
    // Transaction-bound listener.
}
~~~

When published outside a transaction, the regular listener is still invoked by the event multicaster; the default transactional listener is skipped. Enabling fallback changes only the listener with that configuration, not the semantics of the entire event multicaster.

## 3. When Does Spring Decide to Use Fallback?

A method annotated with `@TransactionalEventListener` is converted by Spring into a transactional listener adapter. When the adapter receives an event, it attempts to register transaction synchronization first.

~~~text
publishEvent(event)
       |
       v
transactional listener adapter
       |
       v
can register transaction synchronization?
       /                       \
     Yes                        No
     |                           |
     v                           v
register callback           fallbackExecution?
     |                      /             \
     v                   false             true
wait for phase              |                |
     |                      v                v
     v                    skip          invoke immediately
invoke at right phase
~~~

With imperative transactions, Spring checks whether synchronization is active and an actual transaction is active on the current thread:

~~~java
TransactionSynchronizationManager.isSynchronizationActive()
        && TransactionSynchronizationManager.isActualTransactionActive()
~~~

Merely having synchronization active does not necessarily mean an actual transaction exists. Some propagations can activate synchronization without a backing resource transaction. Transactional event listeners require an actual transaction to uphold phase semantics.

With reactive transactions, Spring uses the Reactor Context instead of ThreadLocal. The event needs to carry the transaction context as its source, typically via `TransactionalEventPublisher`. If no matching context is found, the adapter cannot register synchronization and the fallback branch may be applied.

### 3.1. When a Transaction Exists, Phase Always Takes Precedence

Spring registers synchronization first. If registration succeeds, fallback is not used; the listener still obeys the declared `phase`:

- `BEFORE_COMMIT`: before commit.
- `AFTER_COMMIT`: after successful commit.
- `AFTER_ROLLBACK`: after rollback.
- `AFTER_COMPLETION`: after commit or rollback.

Fallback is only considered when registration fails. Therefore, do not use `fallbackExecution = true` to change the phase or make the listener run immediately inside a transaction.

### 3.2. AFTER_ROLLBACK with fallback=true

This is a case prone to business logic bugs:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void compensate(OrderFailed event) {
    paymentGateway.refund(event.paymentId());
}
~~~

If the event is published outside a transaction, no rollback has occurred. However, because fallback is enabled, the listener is still invoked immediately during event dispatch. Spring 6.2 logs a warning when handling fallback with the `AFTER_ROLLBACK` phase.

Similarly, `BEFORE_COMMIT` with fallback can run even when no commit exists. Without a transaction, phases cannot be fulfilled in the transaction lifecycle sense; fallback is just an immediate invocation.

If business logic requires "only after commit" or "only after rollback," keep fallback at its default of false.

## 4. Fallback Does Not Handle Every Kind of Error

`fallbackExecution` only handles the case where the listener cannot register transaction synchronization. It is not a general fallback mechanism:

| Situation | Fallback applies? | Reason |
|---|---|---|
| Published outside a transaction | Yes | Synchronization cannot be registered |
| Event on a thread not carrying the current transaction | Possibly | Adapter does not see the transaction |
| Reactive event missing TransactionContext in source | Possibly | Adapter does not find the reactive transaction |
| Synchronization registered and then transaction rolls back | No | Listener follows the phase |
| Listener throws an exception | No | This is a listener execution error |
| Executor rejects the task | No | This is a dispatch/executor error |
| SpEL condition is not satisfied | No | Event is filtered out |
| Event does not match listener type | No | Listener is not selected |

Do not enable fallback to mask transaction manager misconfiguration, lost thread context, or event publishing bugs. First determine why registration failed.

## 5. Fallback and the Four Transaction Phases

| Phase | When a transaction exists | When no transaction exists and fallback=true |
|---|---|---|
| `BEFORE_COMMIT` | Invoked before commit | Invoked immediately; no commit |
| `AFTER_COMMIT` | Invoked after successful commit | Invoked immediately; no commit |
| `AFTER_ROLLBACK` | Invoked after rollback | Invoked immediately; no rollback, warning logged |
| `AFTER_COMPLETION` | Invoked after commit or rollback | Invoked immediately; no completion |

The default phase is `AFTER_COMMIT`. Therefore, if fallback is enabled without declaring a phase, the listener still processes immediately when the event is published outside a transaction.

If strict semantics are needed, keep `fallbackExecution = false`. If you need a single handler usable both inside and outside a transaction, you can enable fallback, but you must accept two execution timings: after the transaction phase when a transaction exists, and immediately at publish time when there is no transaction.

## 6. Complete Example with Java 17 and Spring Framework 6.2

The example uses Spring Context, Spring JDBC, Spring TX, and H2. The same event is published in three scenarios:

1. Outside a transaction: the default listener is skipped, and the listener with fallback runs immediately.
2. In a successfully committed transaction: both listeners run after commit.
3. In a rolled-back transaction: AFTER_COMMIT listeners do not run; the AFTER_ROLLBACK listener runs.

**Project Structure**

~~~text
fallback-execution-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FallbackExecutionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>fallback-execution-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.0</version>
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
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FallbackExecutionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/FallbackExecutionDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class FallbackExecutionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    create table orders (
                        id varchar(40) primary key
                    )
                    """);

            ApplicationEventPublisher publisher = context;
            OrderService service = context.getBean(OrderService.class);

            publisher.publishEvent(new OrderCreated("ORD-OUTSIDE"));
            service.createAndCommit("ORD-COMMIT");

            try {
                service.createAndRollback("ORD-ROLLBACK");
            }
            catch (IllegalStateException expected) {
                System.out.println("Rollback requested");
            }

            Integer committedRows =
                    jdbc.queryForObject(
                            "select count(*) from orders",
                            Integer.class);
            System.out.println("Committed rows: " + committedRows);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        public DriverManagerDataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:fallback;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DriverManagerDataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DriverManagerDataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public record OrderCreated(String orderId) {
    }

    public static class OrderService {

        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void createAndCommit(String orderId) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("published: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
        }

        @Transactional
        public void createAndRollback(String orderId) {
            jdbc.update("insert into orders(id) values (?)", orderId);
            System.out.println("published: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
            throw new IllegalStateException("Simulate rollback");
        }
    }

    public static class OrderListeners {

        @Order(10)
        @TransactionalEventListener
        public void afterCommitDefault(OrderCreated event) {
            System.out.println("default AFTER_COMMIT: " + event.orderId());
        }

        @Order(20)
        @TransactionalEventListener(fallbackExecution = true)
        public void afterCommitWithFallback(OrderCreated event) {
            System.out.println("fallback AFTER_COMMIT: " + event.orderId());
        }

        @Order(30)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK: " + event.orderId());
        }
    }
}
~~~

**Running the Program**

From the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
fallback AFTER_COMMIT: ORD-OUTSIDE
published: ORD-COMMIT
default AFTER_COMMIT: ORD-COMMIT
fallback AFTER_COMMIT: ORD-COMMIT
published: ORD-ROLLBACK
AFTER_ROLLBACK: ORD-ROLLBACK
Rollback requested
Committed rows: 1
~~~

**Result Explanation**

1. `ORD-OUTSIDE` is published outside a transaction. The default listener does not run. The listener with `fallbackExecution=true` is invoked immediately, even though its phase is still `AFTER_COMMIT`.
2. `ORD-COMMIT` is published inside a transaction. Spring registers both AFTER_COMMIT listeners with synchronization. Fallback is not used; both run after commit.
3. `ORD-ROLLBACK` is published inside a transaction and then the service throws a RuntimeException. The transaction rolls back. Neither AFTER_COMMIT listener runs; the AFTER_ROLLBACK listener is invoked.
4. The final query sees only one committed row.

The example uses a regular Java record as the event payload. Spring 4.2+ supports publishing POJOs via `ApplicationEventPublisher.publishEvent(Object)`; events do not need to extend `ApplicationEvent`.

## 7. Is Using Fallback with AFTER_ROLLBACK Dangerous?

It can be dangerous if fallback is misunderstood as "runs only on rollback." When an event is published inside a real transaction, the method runs after rollback. But if the publisher publishes the event outside a transaction, the method runs immediately due to fallback. In that case, a refund might be issued even though no transaction rolled back.

For handlers with side effects such as issuing refunds, canceling bookings, or sending failure notifications, keep fallback disabled or separate the two use cases into two distinct listeners/commands. Do not use fallback as a substitute for the business condition "has rolled back."

## 8. Imperative and Reactive Transactions

With imperative transactions, Spring keeps transaction state and synchronization on the current thread. A listener may fail to find a transaction when the event is published before/after the transaction, from another thread, through a call that bypasses the `@Transactional` proxy, or when synchronization is active without an actual transaction.

If fallback is enabled, the situations above can cause the listener to run immediately. Fallback can mask an architectural bug: code that was supposed to publish inside a transaction actually ran outside a transaction.

Since Spring 6.1, `@TransactionalEventListener` also supports reactive transactions. Reactive transactions use the Reactor Context instead of ThreadLocal. Events need to carry the transaction context as their source, typically via `TransactionalEventPublisher`:

~~~java
return databaseOperation
        .then(transactionalEventPublisher.publishEvent(
                new OrderCreated("ORD-REACTIVE")))
        .as(transactionalOperator::transactional);
~~~

If `applicationEventPublisher.publishEvent(new OrderCreated(...))` is used directly, the event does not automatically carry the reactive transaction context. Then the adapter cannot register reactive synchronization; fallback may invoke the listener immediately and hide the missing context bug.

With reactive transactions, compose the Mono returned by `TransactionalEventPublisher` into the same pipeline. Do not use fallback as a substitute for propagating the proper Reactor Context.

## 9. Annotation Attributes, Exceptions, and Resources

`@TransactionalEventListener` also supports `condition` (SpEL), `id`, and `classes`/`value`. Fallback does not bypass SpEL conditions. In Spring 6.2, `fallbackExecution` is an alias for `EventListener.defaultExecution`.

With the default synchronous multicaster, fallback invokes the method immediately during dispatch; exceptions can propagate back to the publisher. There is no publisher transaction to roll back side effects performed before the error.

When transaction registration succeeds, the listener runs according to its phase. Exceptions in `BEFORE_COMMIT` can affect the commit; exceptions in post-completion phases cannot roll back an already-committed transaction.

In `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`, resources may still be bound during cleanup. If the listener needs to write new data, call a service that opens an independent transaction, usually using `Propagation.REQUIRES_NEW`. Out-of-transaction fallback also needs its own transaction if the write operation requires atomicity.

## 10. When Should fallbackExecution Be Enabled?

| Need | Recommendation |
|---|---|
| Process only after transaction commits | Keep `false` |
| Process only when transaction rolls back | Keep `false` |
| Event is valid both inside and outside a transaction; outside a transaction needs immediate processing | Can enable `true` |
| Want to automatically open a transaction when none exists | Fallback does not do this; configure a separate transaction |
| Want to retry events after commit | Use an outbox or message broker |
| Want to hide lost transaction context | Fix transaction boundaries/context |
| Using `AFTER_ROLLBACK` for refunds where events might be published outside a transaction | Keep fallback disabled or split execution paths |

Enable fallback only when the handler has clear business meaning in both cases—an event bound to a transaction and an event published outside a transaction.

## 11. Testing and Common Pitfalls

Integration tests should verify three paths:

1. No transaction, fallback=false: listener is not invoked.
2. No transaction, fallback=true: listener is invoked immediately.
3. With transaction: fallback is not used; listener runs according to phase after commit or rollback.

Do not only invoke the listener method directly in tests, because that bypasses the adapter, transaction synchronization, and fallback branch. With Spring Test, note that test methods may be wrapped in a transaction by the framework and rolled back at the end; to test outside a transaction, publish from code that truly runs outside the test transaction.

Common pitfalls:

- Assuming fallback=true always invokes the listener immediately; when registration succeeds, the listener still waits for the phase.
- Assuming fallback opens a new transaction or saves the event to run later.
- Enabling fallback for AFTER_ROLLBACK and accidentally running compensation when no rollback occurred.
- Using fallback to mask proxy, thread, or Reactor Context issues.
- Assuming regular listeners are also skipped when a transactional listener is skipped.
- Relying on fallback to guarantee retries or delivery after a process crash.
- Writing to the database in fallback and thinking the publisher's transaction protects that operation.

## 12. Key Takeaways

`fallbackExecution` defaults to `false`. When Spring cannot register a transactional listener with transaction synchronization, false skips the listener; true invokes the listener immediately during event dispatch.

If a transaction is active and registration succeeds, the listener still runs according to the declared `phase` even if fallback is enabled. When there is no transaction, phases are not executed in the transaction lifecycle sense: `AFTER_COMMIT` does not wait for commit, `AFTER_ROLLBACK` does not wait for rollback, and `BEFORE_COMMIT` has no subsequent commit.

Fallback does not open a transaction, does not store events for later processing, does not retry, and does not guarantee delivery after a process crash. Enable it only when immediate execution outside a transaction is intentional business behavior.

## References — Spring Framework 6.2

- [Transaction-bound Events — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionalApplicationListenerMethodAdapter source — Spring Framework 6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerMethodAdapter.java)
- [TransactionalApplicationListenerSynchronization source — Spring Framework 6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/event/TransactionalApplicationListenerSynchronization.java)
- [TransactionSynchronizationManager Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [TransactionPhase Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionalEventPublisher Javadoc — Spring Framework 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
