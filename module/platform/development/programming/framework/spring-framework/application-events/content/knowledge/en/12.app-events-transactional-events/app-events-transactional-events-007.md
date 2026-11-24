# Events Without a Transaction in Spring Framework

A Spring application event can be published while a transaction is active or when there is no transaction at all. This distinction is especially important for **@TransactionalEventListener**.

When an event is published outside a transaction, a regular listener using **@EventListener** is still invoked by the ApplicationContext's dispatch mechanism. By contrast, **@TransactionalEventListener** does not run by default because there is no transaction synchronization to register the callback with. The **fallbackExecution=true** attribute allows the listener to process the event immediately at publish time when no matching transaction is found.

Key point: **publishEvent(...) does not automatically open a transaction**. If business logic requires the listener to run after commit, the publisher must publish the event inside an active transaction. Enable fallbackExecution only if immediate processing without a transaction is valid.

## 1. What Happens When Publishing an Event Outside a Transaction?

Suppose a service publishes OrderSubmittedEvent:

```java
publisher.publishEvent(new OrderSubmittedEvent("ORD-1001"));
```

If the call occurs outside a transaction, Spring still routes the event through ApplicationEventMulticaster. Regular listeners matching the event are still invoked.

For a transactional listener, Spring needs an active transaction synchronization to register the callback at the selected phase. If there is no synchronization:

- **fallbackExecution=false:** the listener is skipped. This is the default value.
- **fallbackExecution=true:** the listener is invoked immediately in the current event-handling flow.

The event is not deleted from the ApplicationContext. Only transactional listeners without fallback do not execute during that publish call.

## 2. Comparing @EventListener and @TransactionalEventListener

Both annotations register a method as an event listener, but they differ in invocation timing.

| Characteristic | @EventListener | @TransactionalEventListener |
|---|---|---|
| Transaction or not | Does not require a transaction | Requires transaction synchronization by default |
| When published outside a transaction | Invoked immediately | Skipped if fallbackExecution=false |
| When published outside a transaction with fallback | Does not need fallback | Runs immediately if fallbackExecution=true |
| When published inside a transaction | Usually runs immediately in the publish flow | Waits for the selected phase |
| Commit/rollback phases | None | BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION |
| Automatically creates a transaction | No | No |
| Durably persists events | No | No |

Regular listener:

```java
@EventListener
public void onOrderSubmitted(OrderSubmittedEvent event) {
    System.out.println("Received event: " + event.orderId());
}
```

This listener is invoked whether the publisher has a transaction or not. If published inside a transaction, it usually runs before the transaction commits. Therefore, side effects outside the database can happen even if the transaction later rolls back.

Transactional listener:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(OrderSubmittedEvent event) {
    System.out.println("Committed order: " + event.orderId());
}
```

This listener only runs after commit if the event is published within an active transaction synchronization. Without a transaction, the listener is skipped by default.

## 3. fallbackExecution Defaults to false

The **fallbackExecution** attribute determines how a transactional listener handles an event when no matching transaction exists.

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false
)
public void afterCommit(OrderSubmittedEvent event) {
    // Only runs when transaction synchronization exists.
}
```

This is the default behavior when fallbackExecution is not declared.

The false value is appropriate when the listener only makes sense if a source transaction actually exists. For example, sending an order confirmation email only after order data has committed. If the publisher forgets to open a transaction, skipping the listener avoids sending notifications about an uncommitted change.

When an event is published outside a transaction, Spring does not automatically create a transaction to run the listener and does not automatically move the event to another queue. The listener is not invoked during that publish call.

### When to Enable fallbackExecution=true?

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handleOrder(OrderSubmittedEvent event) {
    // Handle after commit if a transaction exists;
    // handle immediately if there is no transaction.
}
```

When transaction synchronization exists, the listener is still registered at the AFTER_COMMIT phase. When there is no transaction, fallback allows the listener to run immediately.

**fallbackExecution=true does not create a transaction and does not make an event become AFTER_COMMIT when there is no transaction.** There is no commit to wait for, so fallback executes the listener immediately in the current execution path.

Enable fallback only when the same action is meaningful in both cases: publishing inside a transaction and publishing outside a transaction. If the listener must guarantee committed data, keep fallbackExecution=false and fix the publishing site to have a real transaction.

## 4. Transaction Synchronization Is the Key Condition

Transactional event listeners register callbacks with transaction synchronization. In a typical Spring application, synchronization is activated when the transaction manager starts a transaction and manages its lifecycle.

Common ways to have a transaction:

- Call a method managed transactionally by Spring using **@Transactional**.
- Use **TransactionTemplate** to wrap the code block needing a transaction.
- Use the transaction manager corresponding to JDBC, JPA, or the application's persistence technology.

Example with annotations:

```java
@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;
    private final OrderRepository repository;

    public OrderService(
            ApplicationEventPublisher publisher,
            OrderRepository repository
    ) {
        this.publisher = publisher;
        this.repository = repository;
    }

    @Transactional
    public void submit(Order order) {
        repository.save(order);
        publisher.publishEvent(
                new OrderSubmittedEvent(order.getId())
        );
    }
}
```

The event is published inside the method's transaction. The AFTER_COMMIT listener is invoked after the transaction commits successfully. If the transaction rolls back, the AFTER_COMMIT listener is not invoked.

For @Transactional to take effect, the application needs transaction management and an appropriate transaction manager configured. In plain Spring Framework, @EnableTransactionManagement can be used along with a PlatformTransactionManager. In Spring Boot, configuration is usually auto-configured when the corresponding dependency and datasource are present.

### Cases That Look Like They Have a Transaction but Actually Do Not

- The method calling publishEvent does not have @Transactional and is not inside a transaction opened by the caller.
- The method has @Transactional but is called via self-invocation within the same object, causing the transaction proxy not to be triggered in default proxy mode.
- The application has not configured an appropriate transaction manager.
- The transaction was suspended or already ended before publishing the event, such as via NOT_SUPPORTED propagation.
- The event is published in a callback or another thread that does not carry the original thread's transaction synchronization.

Do not look solely at annotations to conclude a transaction exists. Determine whether the actual call crosses a transaction boundary and whether the event is published while synchronization is still active.

## 5. Complete Example: Same Event Outside and Inside a Transaction

The example uses Java 17 and Spring Framework 6.2. The program publishes the same POJO event type in two ways:

1. Outside a transaction: the regular listener runs, the default transactional listener is skipped, and the listener with fallback runs immediately.
2. Inside TransactionTemplate: the regular listener runs at publish time, while both transactional listeners are invoked after commit.

The example uses a minimal transaction manager that only simulates transaction synchronization without connecting to a database. It helps observe callbacks without needing to set up a database. In a real application, use your system's transaction manager.

### 5.1. Project Structure

```text
spring-event-without-transaction/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── notransaction/
                        └── Application.java
```

### 5.2. Maven Dependencies

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>spring-event-without-transaction</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.6</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.example.notransaction.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Source Code

Create src/main/java/dev/example/notransaction/Application.java:

```java
package dev.example.notransaction;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.EnableTransactionManagement;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderPublisher publisher = context.getBean(OrderPublisher.class);

            System.out.println("=== OUTSIDE TRANSACTION ===");
            publisher.publishOutsideTransaction("ORD-1001");

            System.out.println("=== INSIDE TRANSACTION ===");
            publisher.publishInsideTransaction("ORD-1002");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        public PlatformTransactionManager transactionManager() {
            return new DemoTransactionManager();
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager
        ) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public OrderPublisher orderPublisher(
                ApplicationEventPublisher publisher,
                TransactionTemplate transactionTemplate
        ) {
            return new OrderPublisher(publisher, transactionTemplate);
        }

        @Bean
        public EveryPublicationListener everyPublicationListener() {
            return new EveryPublicationListener();
        }

        @Bean
        public AfterCommitListener afterCommitListener() {
            return new AfterCommitListener();
        }

        @Bean
        public FallbackListener fallbackListener() {
            return new FallbackListener();
        }
    }

    public record OrderSubmittedEvent(String orderId) {}

    public static class OrderPublisher {
        private final ApplicationEventPublisher publisher;
        private final TransactionTemplate transactionTemplate;

        public OrderPublisher(
                ApplicationEventPublisher publisher,
                TransactionTemplate transactionTemplate
        ) {
            this.publisher = publisher;
            this.transactionTemplate = transactionTemplate;
        }

        public void publishOutsideTransaction(String orderId) {
            System.out.println("Publisher: publish " + orderId);
            publisher.publishEvent(new OrderSubmittedEvent(orderId));
            System.out.println("Publisher: publishEvent returned");
        }

        public void publishInsideTransaction(String orderId) {
            transactionTemplate.executeWithoutResult(status -> {
                System.out.println("Publisher: publish " + orderId);
                publisher.publishEvent(new OrderSubmittedEvent(orderId));
                System.out.println(
                        "Publisher: publishEvent returned inside transaction"
                );
            });

            System.out.println("Publisher: transaction completed");
        }
    }

    @Order(1)
    public static class EveryPublicationListener {

        @EventListener
        public void onOrderSubmitted(OrderSubmittedEvent event) {
            System.out.println(
                    "EventListener: " + event.orderId()
            );
        }
    }

    @Order(2)
    public static class AfterCommitListener {

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT
        )
        public void afterCommit(OrderSubmittedEvent event) {
            System.out.println(
                    "After-commit listener: " + event.orderId()
            );
        }
    }

    @Order(3)
    public static class FallbackListener {

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true
        )
        public void withFallback(OrderSubmittedEvent event) {
            System.out.println(
                    "Fallback listener: " + event.orderId()
            );
        }
    }

    // Only activates transaction synchronization to demonstrate callbacks.
    // Does not perform database commit/rollback.
    public static class DemoTransactionManager
            extends AbstractPlatformTransactionManager {

        @Override
        protected Object doGetTransaction() {
            return new Object();
        }

        @Override
        protected void doBegin(
                Object transaction,
                TransactionDefinition definition
        ) {
            // No database resource in this example.
        }

        @Override
        protected void doCommit(DefaultTransactionStatus status) {
            // AbstractPlatformTransactionManager invokes afterCommit
            // and afterCompletion after this step.
        }

        @Override
        protected void doRollback(DefaultTransactionStatus status) {
            // Demonstrates rollback synchronization, without database writes.
        }
    }
}
```

### 5.4. Running the Program

In the directory containing pom.xml, run:

```bash
mvn -q compile exec:java
```

Expected stdout:

```text
=== OUTSIDE TRANSACTION ===
Publisher: publish ORD-1001
EventListener: ORD-1001
Fallback listener: ORD-1001
Publisher: publishEvent returned
=== INSIDE TRANSACTION ===
Publisher: publish ORD-1002
EventListener: ORD-1002
Publisher: publishEvent returned inside transaction
After-commit listener: ORD-1002
Fallback listener: ORD-1002
Publisher: transaction completed
```

The output shows:

- For ORD-1001, there is no transaction. EventListener runs immediately. AfterCommitListener is skipped because fallbackExecution defaults to false. FallbackListener runs immediately during publish.
- For ORD-1002, the event is published inside TransactionTemplate. EventListener runs immediately inside the transaction. Both transactional listeners are registered and run only after the transaction commits.
- fallbackExecution=true does not make the listener run early when a transaction is active; it is only a fallback path when no transaction exists.

The transaction manager in the example only simulates transaction synchronization. It does not write data and does not demonstrate database atomicity. In real usage, replace it with DataSourceTransactionManager, JpaTransactionManager, or the appropriate transaction manager.

## 6. Which Approach Should You Choose Without a Transaction?

### Simply Handle Events Regardless of Transaction

Use **@EventListener**:

```java
@EventListener
public void recordActivity(UserLoggedInEvent event) {
    activityLog.record(event.userId());
}
```

This is the clear choice when the listener always needs to run and does not depend on whether a transaction commits or not.

### Handle Only When a Transaction Commits

Use **@TransactionalEventListener** with the default fallback of false:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderSubmittedEvent event) {
    notificationService.send(event.orderId());
}
```

If an event is published outside a transaction, the listener is skipped. If this is a mandatory business requirement, fix the publisher to publish the event inside a transaction instead of enabling fallback to mask a missing transaction.

### Handle Both Inside and Outside a Transaction

Use fallbackExecution=true when the same action is valid in both cases:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void updateExternalIndex(OrderSubmittedEvent event) {
    searchIndex.update(event.orderId());
}
```

When there is a transaction, the listener runs after commit. When there is no transaction, the listener runs immediately. Check whether immediate execution could observe unsaved or inconsistent data.

### Need to Write to the Database from an Out-of-Transaction Listener

If the listener needs to write data and requires an explicit commit, call a service with its own transaction:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAudit(OrderSubmittedEvent event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
```

REQUIRES_NEW only takes effect when the call goes through a Spring transaction proxy and an appropriate transaction manager is present. If the listener is invoked outside a transaction, Spring opens a new transaction for this service.

## 7. Common Reasons a Transactional Listener Does Not Run

| Symptom | Cause | Solution |
|---|---|---|
| @TransactionalEventListener is not invoked | Event published outside transaction synchronization | Publish inside a transaction or enable fallback if appropriate |
| @EventListener runs but transactional listener does not | The two annotations have different activation rules | Check the transaction and fallbackExecution |
| Has @Transactional but still skipped | Call does not go through proxy, self-invocation, or transaction is not actually active | Check proxy and transaction manager |
| Listener runs immediately even though phase is AFTER_COMMIT | fallbackExecution=true and no transaction exists | Understand fallback means immediate execution, not waiting for commit |
| Listener runs while data is not yet committed | Regular @EventListener used inside a transaction | Switch to AFTER_COMMIT if committed data is required |
| Enabled fallback and still no transaction exists | fallback does not create a transaction | Open a transaction in the publisher or service needing a transaction |
| Listener runs twice | Same logic registered by multiple listeners or duplicate publish | Check registration and ensure idempotency |
| Event lost after process stops | Application events reside only in memory | Use a transactional outbox or message broker when durability is needed |

## 8. Transactional Events Are Not a Message Queue

Spring application events are a notification mechanism within an ApplicationContext. Transactional event listeners tie execution timing to transaction synchronization, but do not automatically persist events to a database.

If an event is published outside a transaction and the transactional listener is skipped, Spring does not retain the event to reprocess when a transaction appears later.

Even when published inside a transaction and the AFTER_COMMIT listener is invoked, the process can still stop after the database commits but before the listener finishes. If business logic requires durable delivery, a mechanism like a transactional outbox or message broker is needed.

Also design listeners to be idempotent if the system has retries at another layer. Do not rely on @TransactionalEventListener to provide exactly-once delivery.

## 9. Notes on Asynchronous and Reactive Transactions

Spring's regular transactions are normally bound to the current thread. If an event is published from a thread without transaction synchronization, transactional listeners treat it as having no transaction and apply fallbackExecution.

With reactive transactions, the transaction context is propagated via the Reactor Context instead of relying entirely on ThreadLocal. Do not offload event publishing to another callback or thread and expect the transaction context to appear automatically. Spring provides **TransactionalEventPublisher** to publish events carrying the reactive transaction context when transactional events need to be handled in a reactive flow.

## 10. Checklist When Publishing Events Without a Transaction

- Determine whether the publisher is inside a transaction synchronization.
- Distinguish regular listeners from transactional listeners.
- Remember that fallbackExecution defaults to false.
- If enabling fallbackExecution=true, understand the listener will run immediately when there is no transaction.
- Do not assume publishEvent automatically creates a transaction.
- If AFTER_COMMIT is needed, publish the event inside a real transaction.
- Verify @Transactional goes through a proxy and the transaction manager is active.
- Do not use fallback to mask a missing required transaction.
- If the listener writes to the database, open a separate transaction when a commit is needed.
- Do not treat application events as a durable queue or retry mechanism.
- Use an outbox or broker if events must survive restarts.
- Design idempotency if work can be retried or published repeatedly.

## 11. References

- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring/reference/6.2/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)

When publishing an event outside a transaction, **@EventListener** still processes the event normally. **@TransactionalEventListener** skips the event by default because there is no transaction synchronization; enabling **fallbackExecution=true** allows immediate processing during that publish call. Choose fallback when out-of-transaction processing is valid, and create a real transaction at the publisher when business logic requires a post-commit callback.
