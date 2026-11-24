# Transaction Phase AFTER_COMPLETION

`TransactionPhase.AFTER_COMPLETION` is the `@TransactionalEventListener` phase used when a listener needs to run after a transaction ends, regardless of whether the transaction commits or rolls back. It is the phase that covers both outcomes. It is suitable for work that must be performed once a transaction has completed, such as releasing auxiliary resources, recording processing status, or cleaning up temporary data.

`AFTER_COMPLETION` differs from `AFTER_COMMIT` and `AFTER_ROLLBACK` in its triggering condition. `AFTER_COMMIT` only runs on a successful commit; `AFTER_ROLLBACK` only runs on rollback; whereas `AFTER_COMPLETION` runs after both cases. A listener in this phase does not directly receive the commit/rollback status code via method parameters. If you need to handle each outcome separately, use the two specialized phases or register a lower-level transaction synchronization.

One point requires special attention: by the time the callback runs, the original transaction has already completed. Resources such as a JDBC connection may still be bound and accessible during cleanup, but data changes made in this phase will not be committed into the original transaction. If the listener needs to write new data, open a separate transaction, typically using `Propagation.REQUIRES_NEW`.

After this lesson, you will be able to:

- Explain exactly when `AFTER_COMPLETION` is invoked.
- Distinguish `AFTER_COMPLETION` from `AFTER_COMMIT` and `AFTER_ROLLBACK`.
- Register a listener using `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)`.
- Understand the behavior when an event is published outside a transaction and the role of `fallbackExecution`.
- Avoid writing data into an already-completed transaction and know when `REQUIRES_NEW` is needed.
- Test the listener with both committed and rolled-back transactions.
- Understand considerations when using transactional events with reactive transactions.

## 1. What Is AFTER_COMPLETION?

Spring provides `@TransactionalEventListener` to bind event handling to a transaction phase. The `phase` attribute accepts a `TransactionPhase` value.

Valid phases:

| Phase | When the listener is invoked | Use cases |
|---|---|---|
| `BEFORE_COMMIT` | Before the transaction commits | Checks or supplementary work that must complete before commit. |
| `AFTER_COMMIT` | After the transaction commits successfully | Sending notifications or performing side effects valid only once data is committed. |
| `AFTER_ROLLBACK` | After the transaction rolls back | Recording or cleanup specific to the rollback case. |
| **`AFTER_COMPLETION`** | After the transaction completes, whether committed or rolled back | Cleanup or general handling for any completion outcome. |

`AFTER_COMPLETION` covers both commit and rollback. Therefore, a listener registered with this phase will be invoked after the transaction ends in either state.

Declaration example:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("Transaction completed for " + event.orderId());
    }
}
~~~

If the event is published inside an active transaction, Spring registers the listener invocation with transaction synchronization. The method is not executed immediately at the `publishEvent` line; it is invoked when the transaction reaches the selected phase.

## 2. Position of AFTER_COMPLETION in the Transaction Lifecycle

For an imperative transaction managed by `PlatformTransactionManager`, the general sequence is:

~~~mermaid
flowchart TD
    A["Start transaction"] --> B["Publisher publishes event"]
    B --> C["Spring registers transactional listener"]
    C --> D{"How does the transaction end?"}
    D -->|Commit| E["Commit resources"]
    D -->|Rollback| F["Rollback resources"]
    E --> G["AFTER_COMPLETION callback"]
    F --> G
    G --> H["Cleanup transaction resources"]
~~~

In both branches, the `AFTER_COMPLETION` callback is invoked after the transaction outcome has been decided.

Example with commit:

1. Service starts a transaction.
2. Service modifies data.
3. Service publishes an event.
4. The transactional method finishes normally.
5. The transaction manager commits.
6. The `AFTER_COMPLETION` listener is invoked.
7. Spring cleans up transaction resources.

Example with rollback:

1. Service starts a transaction.
2. Service modifies data.
3. Service publishes an event.
4. The transactional method throws an exception matching rollback rules.
5. The transaction manager rolls back.
6. The `AFTER_COMPLETION` listener is still invoked.
7. Spring cleans up transaction resources.

The important point is that an event registered inside the transaction can still be processed after a rollback. `AFTER_COMPLETION` does not mean the transaction succeeded; it only means the transaction has ended.

## 3. Comparing AFTER_COMPLETION with AFTER_COMMIT and AFTER_ROLLBACK

All three phases run after the transaction has completed, but their trigger conditions differ.

~~~java
@Component
public class OrderTransactionListeners {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderCreatedEvent event) {
        // Runs only if the transaction commits successfully.
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
    )
    public void afterRollback(OrderCreatedEvent event) {
        // Runs only if the transaction rolls back.
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        // Runs after both commit and rollback.
    }
}
~~~

Selection table:

| Need | Phase to use |
|---|---|
| Only handle when data has committed | `AFTER_COMMIT` |
| Only handle when transaction failed and rolled back | `AFTER_ROLLBACK` |
| Always run cleanup after the transaction ends | `AFTER_COMPLETION` |
| Validate or supplement data before commit | `BEFORE_COMMIT` |

`AFTER_COMMIT` and `AFTER_ROLLBACK` are specialized cases of `AFTER_COMPLETION` and run within the same transaction completion chain. If registering multiple listeners for the same event, clearly define responsibilities to avoid duplicating a side effect.

### AFTER_COMPLETION Does Not Provide Transaction Status to the Method

The listener method typically receives the event payload:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderCreatedEvent event) {
    // Receives only the event; no commit/rollback status parameter.
}
~~~

The annotation does not automatically pass an `int status` or `TransactionStatus` parameter to the method. If the listener needs to know specifically whether commit or rollback occurred to branch:

- Use `AFTER_COMMIT` for the commit branch.
- Use `AFTER_ROLLBACK` for the rollback branch.
- Or use `TransactionSynchronization.afterCompletion(int status)` when a low-level callback with `STATUS_COMMITTED`, `STATUS_ROLLED_BACK`, or `STATUS_UNKNOWN` is required.

Do not guess the transaction outcome from the fact that the listener method was invoked: with `AFTER_COMPLETION`, both outcomes are valid.

## 4. Registering the Event and Listener

The publisher publishes the event inside a transaction:

~~~java
@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void create(String orderId) {
        // Save the order within the transaction.
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

The event payload can be a record:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

The listener registers with the desired phase:

~~~java
@Component
public class OrderCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        System.out.println("Completed: " + event.orderId());
    }
}
~~~

Spring registers the listener method as a transaction-bound listener. When the event is published inside a transaction, method execution is deferred until the completion phase.

`@TransactionalEventListener` has a default phase of `AFTER_COMMIT`. If you want it to run after both commit and rollback, explicitly specify `AFTER_COMPLETION` so readers of the code understand the intent.

## 5. When There Is No Active Transaction

By default, if an event is published when no transaction is active, `@TransactionalEventListener` is not invoked. Spring cannot fulfill transaction phase semantics without a transaction to bind the listener to.

Example:

~~~java
publisher.publishEvent(new OrderCreatedEvent("ORD-8001"));
~~~

If this line runs outside a transaction, the default `AFTER_COMPLETION` listener will not execute.

`fallbackExecution = true` can be enabled:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION,
    fallbackExecution = true
)
public void afterCompletion(OrderCreatedEvent event) {
    // Invoked even when the event is not inside a transaction.
}
~~~

When there is no transaction, the listener executes via fallback instead of waiting for an actual completion phase. Therefore, enabling fallback changes the listener's meaning: the method can run even when no transaction completed.

Only enable fallback when the business logic accepts handling events outside a transaction. If the requirement is "run only after a transaction ends," keep the default `fallbackExecution = false`.

## 6. Important Note: Resources May Still Be Accessible After Completion

Spring's Javadoc warns that in the `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` phases, the transaction has already committed or rolled back, but transactional resources may still be active and accessible during Spring cleanup.

This creates an easily misunderstood situation:

- The listener calls a repository or `JdbcTemplate`.
- The data access command may still use the resource bound to the old transaction.
- Because the original transaction has already completed, new changes will not be committed to that resource.

Example where you should not rely on a post-completion write to save an audit record:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderCreatedEvent event) {
    // Do not assume this save call will be committed.
    auditRepository.save(new AuditEntry(event.orderId()));
}
~~~

If new data must be written after completion, call a service that opens a separate transaction:

~~~java
@Service
public class AuditWriter {

    private final AuditRepository auditRepository;

    public AuditWriter(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordCompletion(String orderId) {
        auditRepository.save(new AuditEntry(orderId));
    }
}
~~~

The listener calls the service:

~~~java
@Component
public class OrderCompletionListener {

    private final AuditWriter auditWriter;

    public OrderCompletionListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        auditWriter.recordCompletion(event.orderId());
    }
}
~~~

`REQUIRES_NEW` requests an independent transaction for the write operation. The method must be called through another bean's Spring proxy so transaction propagation is applied properly; self-invocation within the same bean does not go through the proxy in the usual way.

If the listener only needs to clean up resources or record metrics outside a transaction, opening a new transaction is not necessarily required. Choose the mechanism based on the type of side effect.

## 7. Exceptions and Callback Reliability

When `AFTER_COMPLETION` is invoked, the original transaction has already finished. An exception in the listener cannot revert that transaction to an uncommitted state or automatically roll back committed data.

Per Spring's `TransactionSynchronization.afterCompletion(int)` contract, a `RuntimeException` from a completion callback is logged and not propagated back like an exception in a normal transactional method body. Therefore, the publisher should not treat `publishEvent` returning as proof that post-completion side effects succeeded.

If the post-completion task is important:

- Add separate logging and metrics for the listener.
- Design controlled retries.
- Use an idempotency key if duplicate processing is possible.
- Use an outbox or message broker when durable delivery across process crashes is needed.
- Do not swallow exceptions without leaving an operational trace.

`AFTER_COMPLETION` is a callback bound to the transaction lifecycle within the current process. It is not a durable queue and does not automatically persist events for replay after an abrupt application shutdown.

## 8. Reactive Transactions and AFTER_COMPLETION

Since Spring Framework 6.1, `@TransactionalEventListener` supports both imperative transactions managed by `PlatformTransactionManager` and reactive transactions managed by `ReactiveTransactionManager`.

The two models store transaction context differently:

- Imperative transactions use a thread-bound context.
- Reactive transactions use the Reactor Context instead of ThreadLocal.

When publishing an event in a reactive transaction, the transaction context must be attached to the event instance as the event source. Spring provides `TransactionalEventPublisher` to assist with this.

High-level example:

~~~java
@Service
public class ReactiveOrderService {

    private final OrderRepository repository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactiveOrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.eventPublisher = new TransactionalEventPublisher(publisher);
    }

    @Transactional
    public Mono<Void> create(Order order) {
        return repository.save(order)
            .then(eventPublisher.publishEvent(
                new OrderCreatedEvent(order.id())
            ));
    }
}
~~~

The listener can still choose a phase:

~~~java
@Component
public class ReactiveCompletionListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderCreatedEvent event) {
        // Bound to the completion of the reactive transaction.
    }
}
~~~

The example requires the repository to return reactive types and the application to configure an appropriate `ReactiveTransactionManager`. Do not call `ApplicationEventPublisher.publishEvent(payload)` directly and expect Spring to find a reactive transaction from ThreadLocal; use `TransactionalEventPublisher` to pass the context properly.

## 9. Complete Example: Listener Running After Both Commit and Rollback

The example uses Java 17, Spring Framework 6.2.0, Spring JDBC, and H2. The service creates an order and publishes an event inside a transaction. One call commits normally; the second publishes an event and throws an exception so the transaction rolls back. The `AFTER_COMPLETION` listener will be invoked after both calls.

Directory structure:

~~~text
after-completion-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterCompletionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>after-completion-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.AfterCompletionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/AfterCompletionDemo.java

~~~java
package demo;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCompletionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                CREATE TABLE orders (
                    order_id VARCHAR(40) PRIMARY KEY
                )
                """);

            OrderService service = context.getBean(OrderService.class);

            service.createAndCommit("ORD-8001");

            try {
                service.createAndRollback("ORD-8002");
            } catch (IllegalStateException expected) {
                System.out.println(
                    "Publisher caught: " + expected.getMessage()
                );
            }

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders",
                Integer.class
            );

            System.out.println("Persisted orders: " + count);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    static class AppConfig {

        @Bean
        JdbcDataSource dataSource() {
            JdbcDataSource dataSource = new JdbcDataSource();
            dataSource.setURL("jdbc:h2:mem:after-completion;DB_CLOSE_DELAY=-1");
            dataSource.setUser("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        JdbcTemplate jdbcTemplate(JdbcDataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                JdbcDataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OrderCompletionListener orderCompletionListener() {
            return new OrderCompletionListener();
        }
    }

    record OrderCreatedEvent(String orderId) {}

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
            jdbc.update(
                "INSERT INTO orders(order_id) VALUES (?)",
                orderId
            );
            publisher.publishEvent(new OrderCreatedEvent(orderId));
        }

        @Transactional
        public void createAndRollback(String orderId) {
            jdbc.update(
                "INSERT INTO orders(order_id) VALUES (?)",
                orderId
            );
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            throw new IllegalStateException("simulated rollback");
        }
    }

    static class OrderCompletionListener {

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMPLETION
        )
        public void afterCompletion(OrderCreatedEvent event) {
            System.out.println(
                "AFTER_COMPLETION: " + event.orderId()
            );
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
AFTER_COMPLETION: ORD-8001
AFTER_COMPLETION: ORD-8002
Publisher caught: simulated rollback
Persisted orders: 1
~~~

Explanation:

- `ORD-8001` is inserted and the transaction commits. The listener receives the event after completion.
- `ORD-8002` is inserted and the event is published while the transaction is active. Then the exception rolls back the transaction. The listener still receives the event after completion.
- Only `ORD-8001` remains in the table because the second transaction rolled back.
- The `Publisher caught` line appears after the rollback callback because the transaction interceptor completes rollback and synchronization before returning control to the caller.

The example only logs the callback and queries the row count after the transactions finish. The listener does not attempt to write new data into the already-completed transaction's resource. If you want to write an audit or update another table in the callback, call a service using a separate transaction such as `REQUIRES_NEW`.

## 10. Testing Key Scenarios

A test suite for `AFTER_COMPLETION` should verify both commit and rollback:

| Scenario | Expected result |
|---|---|
| Event published in a committed transaction | Listener is invoked once after commit. |
| Event published in a rolled-back transaction | Listener is invoked once after rollback. |
| Event published outside a transaction, default fallback | Listener is not invoked. |
| Event published outside a transaction, fallback enabled | Listener is invoked via fallback, without waiting for completion. |
| Listener writes new data using the original transaction | Must not assume changes will commit. |
| Listener calls a `REQUIRES_NEW` service | Operation has an independent transaction. |
| Listener throws an exception after completion | Original transaction cannot be rolled back retroactively; logging and retry policy are required. |

When testing with a Spring context, use a service bean retrieved from the context so the call goes through the transaction proxy. Directly calling an object instantiated with `new` will bypass the transaction interceptor.

If testing asynchronous callbacks or a listener configured as async, use a future/latch with a timeout. Do not use `Thread.sleep` to guess when the callback finishes.

## 11. Common Pitfalls

| Error or misconception | Consequence | Solution |
|---|---|---|
| Thinking AFTER_COMPLETION only runs on commit | Misses events after rollback. | This phase runs after both commit and rollback. |
| Using AFTER_COMPLETION when only wanting post-commit notifications | Can send notifications even when data rolled back. | Use `AFTER_COMMIT`. |
| Using AFTER_COMPLETION when only handling rollbacks | Listener also runs on commit. | Use `AFTER_ROLLBACK`. |
| Assuming the method receives transaction status | Does not directly know commit/rollback outcome. | Use a specialized phase or `TransactionSynchronization`. |
| Publishing outside a transaction and expecting the listener to wait for completion | No transaction exists to register synchronization. | Keep default fallback or enable fallback only when genuinely acceptable. |
| Writing to the database in AFTER_COMPLETION using the old transaction | New changes are not committed to the original resource. | Call a service using `REQUIRES_NEW`. |
| Assuming a callback exception rolls back an already-completed transaction | Committed/rolled-back data cannot be reversed by the callback. | Log, retry, or use an outbox for critical side effects. |
| Self-invoking a REQUIRES_NEW method in the same bean | The call may bypass the transaction proxy. | Move the operation to another service bean or use an explicit transaction mechanism. |
| Using application events as a durable queue | Events can be lost if the process stops. | Use an outbox or message broker when durable delivery is needed. |

## 12. Checklist for Using AFTER_COMPLETION

Before implementing, verify:

1. Does the listener truly need to run after both commit and rollback?
2. If you only care about commit or rollback, is a specialized phase more appropriate?
3. Is the event published inside an active transaction?
4. Should `fallbackExecution` remain false by default?
5. Is the listener assuming the method receives a transaction status?
6. Does the listener write data after completion, and if so, does it use a new transaction?
7. Does the side effect need idempotency, retries, or an outbox?
8. Are post-completion exceptions logged and monitored?
9. Do reactive transactions use `TransactionalEventPublisher` to pass the Reactor context?
10. Have tests verified the callback runs on both commit and rollback?

`TransactionPhase.AFTER_COMPLETION` runs after the transaction finishes, whether committed or rolled back. It is the right choice for cleanup and general work needed on any completion outcome. If handling only one specific outcome, use `AFTER_COMMIT` or `AFTER_ROLLBACK`. Remember that the original transaction has already completed when the callback runs; any new data changes that must be committed must use an independent transaction, typically `REQUIRES_NEW`.

## References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): how to register listeners by transaction phase and behavior when there is no transaction.
- [TransactionPhase — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): exact definitions of `AFTER_COMPLETION`, `AFTER_COMMIT`, and `AFTER_ROLLBACK`.
- [TransactionalEventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): phase, fallback execution, and notes on post-completion resources.
- [TransactionSynchronization — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCompletion(int status)` callback and exception handling rules.
