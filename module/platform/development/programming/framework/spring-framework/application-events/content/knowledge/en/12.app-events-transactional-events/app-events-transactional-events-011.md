# One Event with Multiple Phase Listeners in Spring Framework

## 1. One Event, Multiple Processing Timings by Transaction

In Spring Framework, a single call to `ApplicationEventPublisher.publishEvent(event)` can trigger multiple listeners. If listeners declare `@TransactionalEventListener`, each listener can be bound to a **transaction phase**: before commit, after successful commit, after rollback, or after the transaction completes with any outcome.

For example, a service publishes `OrderSubmitted("ORD-101")` once while saving an order. Four different listeners can observe this exact same event:

- `BEFORE_COMMIT`: final validation before the transaction commits.
- `AFTER_COMMIT`: perform tasks valid only after a successful commit.
- `AFTER_ROLLBACK`: react when the transaction is rolled back.
- `AFTER_COMPLETION`: clean up or record metrics after the transaction ends, whether committed or rolled back.

**This is still one event published once**, not four events. Each matching listener registers a callback for a transaction phase. A single transaction can only end with one outcome, so listeners in mutually exclusive phases are not invoked simultaneously.

This lesson illustrates **imperative transactions** using `PlatformTransactionManager` and thread-bound transaction context. Reactive transactions have a different context mechanism, noted in section 8.

## 2. Exact Meaning of Each TransactionPhase

| Phase | Timing | Transaction commits | Transaction rolls back |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | When preparing to commit, before physical commit | Usually runs | Does not run in the normal rollback branch |
| `AFTER_COMMIT` | When commit has succeeded | Runs | Does not run |
| `AFTER_ROLLBACK` | After rollback | Does not run | Runs |
| `AFTER_COMPLETION` | After the transaction has completed | Runs | Runs |

`@TransactionalEventListener` defaults to `phase = TransactionPhase.AFTER_COMMIT` if nothing else is declared.

Typical commit flow:

```text
transaction starts
  |
  +-- service modifies data
  +-- publishEvent(OrderSubmitted)
  |     +-- regular @EventListener runs immediately if synchronous
  |     +-- @TransactionalEventListener registers callbacks by phase
  |
  +-- business method body finishes normally
  +-- BEFORE_COMMIT listener
  +-- database commit succeeds
  +-- AFTER_COMMIT listener
  +-- AFTER_COMPLETION listener
  +-- transaction management operation returns
```

Typical rollback flow:

```text
transaction starts
  |
  +-- service modifies data
  +-- publishEvent(OrderSubmitted)
  |     +-- regular @EventListener runs immediately if synchronous
  |     +-- @TransactionalEventListener registers callbacks
  |
  +-- rollback-only or business error
  +-- database rollback
  +-- AFTER_ROLLBACK listener
  +-- AFTER_COMPLETION listener
  +-- transaction management operation returns or throws exception
```

**Common point of confusion:** In Spring Framework 6.2, `AFTER_COMMIT` is a case within the `afterCompletion` callback chain, not the `TransactionSynchronization.afterCommit()` method. `AFTER_ROLLBACK` is also a case within `afterCompletion`. This affects reasoning about the relative ordering between `AFTER_COMMIT` and `AFTER_COMPLETION`.

`BEFORE_COMMIT` does not guarantee that the subsequent commit will succeed: the database or other code can still cause the commit to fail. Irreversible side effects such as sending emails should not be triggered solely based on reaching this phase.

## 3. How Is the Same Event Registered by Multiple Listeners?

The following methods can reside in the same Spring-managed bean or in different beans:

```java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validate(OrderSubmitted event) { /* check before commit */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void notifySuccess(OrderSubmitted event) { /* after commit */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
void undoTemporaryAction(OrderSubmitted event) { /* after rollback */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void recordCompletion(OrderSubmitted event) { /* after any outcome */ }
```

This is a method excerpt, not a standalone program. The runnable version is in section 4.

When `publishEvent` is called inside a transaction, Spring selects listeners matching the event type and `condition` (if any). Each transactional listener's adapter registers synchronization with the active transaction. When the transaction transitions phases, the appropriate callbacks run. A regular `@EventListener` behaves differently: with a synchronous multicaster, it runs immediately during the `publishEvent` call without waiting for the transaction to end.

Therefore, in a transaction that later rolls back, a regular listener may **already have performed side effects**, whereas `AFTER_COMMIT` does not run. When designing business logic, choose the right listener type for the guarantees required.

## 4. Complete Java 17 Example: Same Event, Two Transaction Outcomes

The example uses Spring Framework 6.2.8 and in-memory H2 for real JDBC transactions. We create two separate transactions: the first commits, and the second is marked rollback-only. In each transaction, `publishEvent` is called exactly once.

### Maven Project Structure

```text
multi-phase-event/
├── pom.xml
└── src/main/java/demo/MultiPhaseEventDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-phase-event</artifactId>
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
            <scope>runtime</scope>
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
                    <mainClass>demo.MultiPhaseEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/MultiPhaseEventDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class MultiPhaseEventDemo {

    public record OrderSubmitted(String orderId) {}

    public static class OrderListeners {
        @EventListener
        public void onPublish(OrderSubmitted event) {
            System.out.println("immediate: " + event.orderId());
        }

        @Order(10)
        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderSubmitted event) {
            System.out.println("before commit: " + event.orderId());
        }

        @Order(20)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderSubmitted event) {
            System.out.println("after commit: " + event.orderId());
        }

        @Order(30)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderSubmitted event) {
            System.out.println("after rollback: " + event.orderId());
        }

        @Order(40)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderSubmitted event) {
            System.out.println("after completion: " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:phase_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var transactions = context.getBean(TransactionTemplate.class);

            System.out.println("=== COMMIT ===");
            transactions.executeWithoutResult(status -> {
                System.out.println("business: publish C-1");
                context.publishEvent(new OrderSubmitted("C-1"));
                System.out.println("business: body done C-1");
            });
            System.out.println("caller: commit returned");

            System.out.println("=== ROLLBACK ===");
            transactions.executeWithoutResult(status -> {
                System.out.println("business: publish R-1");
                context.publishEvent(new OrderSubmitted("R-1"));
                System.out.println("business: body done R-1");
                status.setRollbackOnly();
            });
            System.out.println("caller: rollback returned");
        }
    }
}
```

Run in the `multi-phase-event` directory with JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Output printed by the application code (excluding Maven logs):

```text
=== COMMIT ===
business: publish C-1
immediate: C-1
business: body done C-1
before commit: C-1
after commit: C-1
after completion: C-1
caller: commit returned
=== ROLLBACK ===
business: publish R-1
immediate: R-1
business: body done R-1
after rollback: R-1
after completion: R-1
caller: rollback returned
```

**Why does this output occur?**

1. `TransactionTemplate` opens a JDBC transaction via `DataSourceTransactionManager`. H2 provides the connection and transaction boundary; the example creates no tables since it only aims to demonstrate phase callbacks.
2. The regular `@EventListener` runs immediately at publish time. Both `C-1` and `R-1` print `immediate`.
3. For `C-1`, the body of `executeWithoutResult` finishes normally; Spring invokes `BEFORE_COMMIT`, performs the commit, and then invokes the corresponding post-commit and completion callbacks.
4. For `R-1`, `status.setRollbackOnly()` causes the transaction to roll back after the callback body returns; `BEFORE_COMMIT` and `AFTER_COMMIT` do not run. The `AFTER_ROLLBACK` and `AFTER_COMPLETION` listeners run.
5. `@Order(20)`, `@Order(30)`, and `@Order(40)` determine the relative callback order during the completion stage. `@Order` does not change commit/rollback outcomes and does not turn one phase into another.
6. The `caller: ... returned` lines follow the `TransactionTemplate` calls. In the example's default synchronous configuration, they appear after the appropriate phase callbacks have finished.

If the service uses Spring Boot, the annotations and phases remain similar, though Spring Boot may auto-provide `DataSource`, `PlatformTransactionManager`, and bean configuration. Here the example uses `AnnotationConfigApplicationContext` to run independently of Boot.

## 5. Phase and @Order Do Not Replace Each Other

**Phase determines *when* a listener is allowed to run; `@Order` adjusts the relative order among listeners being invoked at the same stage.** Consider two methods:

```java
@Order(100)
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validate(OrderSubmitted e) { /* ... */ }

@Order(-100)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void notifyCustomer(OrderSubmitted e) { /* ... */ }
```

Even though `notifyCustomer` has a lower priority number, it still must wait for a successful commit; it cannot run before `validate`, which is in the pre-commit phase. `@Order` values can be used to order listeners within the same phase, and among after-commit/after-completion listeners within the appropriate synchronization chain.

If two listeners have the same `@Order`, **do not rely on method declaration order or bean names** to design a workflow with mandatory ordering. Use distinct priority levels or an explicit coordinating service.

A transaction can also publish **multiple events**. Each publish generates separate callback registrations for matching listeners; all callbacks wait for that transaction's outcome. Ordering across multiple publishes, multiple listeners, and stages can be affected by registration order/`@Order`. Do not assume all callbacks of event A always finish before all callbacks of event B unless the application actively enforces it.

## 6. Error-Prone Business Cases

### 6.1. Publishing Events Outside a Transaction

By default, if there is no active transaction, `@TransactionalEventListener` **does not run** — including `AFTER_COMPLETION`. A regular `@EventListener` can still run because it does not require a transaction.

`fallbackExecution = true` can be enabled so the listener executes immediately when there is no transaction. This is a fallback path; it is **not proof that a commit succeeded**. Enable it only when business logic genuinely accepts events being handled outside a transaction.

### 6.2. AFTER_COMMIT Does Not Automatically Open a New Transaction

According to the Javadoc of `@TransactionalEventListener`, when an `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION` callback runs, the transaction has already completed, but JDBC/JPA resources may still be bound to the thread. Accessing data at this time can sometimes still "participate" in the old context **without any subsequent commit**, leading to operations that appear to succeed but are not saved.

If a post-commit listener needs to write a new record, open an independent transaction with `REQUIRES_NEW` propagation, such as calling through a Spring-managed service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` or using a correspondingly configured `TransactionTemplate`. Note that calling an internal `@Transactional` method via `this.method()` usually does not go through the Spring proxy.

### 6.3. BEFORE_COMMIT Can Encounter Errors

`BEFORE_COMMIT` is invoked as the transaction prepares to commit. A listener can throw an error causing the transaction not to commit; or the commit afterward can still fail at the database. Do not send permanent notifications or perform hard-to-undo side effects at this step just because you assume commit is "guaranteed."

### 6.4. AFTER_COMMIT Addresses Timing, Not Guaranteed Delivery

Moving email or message sending to `AFTER_COMMIT` avoids sending when data is rolled back, but if the process crashes right after commit or the target API fails, the side effect can be lost. For reliable delivery requirements, use a transactional outbox, retry mechanisms, idempotency, and failure monitoring. `@TransactionalEventListener` itself does not turn in-memory events into a durable queue.

### 6.5. AFTER_COMPLETION Does Not Report Commit/Rollback Outcome

This annotation only guarantees invocation after the transaction completes via the transaction manager mechanism. If the same handling needs to know whether commit or rollback occurred, the clearest way is to use `AFTER_COMMIT` and `AFTER_ROLLBACK` separately. Do not guess the outcome from an `AFTER_COMPLETION` callback that has no status parameter.

### 6.6. setRollbackOnly Differs from Throwing an Exception

Example using `status.setRollbackOnly()`: `TransactionTemplate` rolls back normally and may return to the caller without throwing an error. Conversely, if the business callback throws an unchecked exception, `TransactionTemplate` rolls back and propagates the exception to the caller. Both can lead to `AFTER_ROLLBACK` and `AFTER_COMPLETION`, but the caller's error-handling path differs.

### 6.7. Async and Transaction Context

Imperative transactions are usually bound to the current thread. Spring 6.1+ has `TransactionalApplicationListener.supportsAsyncExecution() == false` for listener synchronization, ensuring the registration step runs on the proper publisher thread. If you manually move `publishEvent` to another thread, or combine `@Async` improperly, the transaction context may not exist in the worker. Do not assume a worker inherits a transaction simply because the event was published from a `@Transactional` service.

If heavy post-commit work must be processed, explicitly design the handoff to an executor, a new transaction if needed, retries, and failure states; do not use async configuration to infer extra delivery guarantees.

## 7. Coordinating Multiple Phase Listeners by Responsibility

| Goal | Choice | Caution |
| --- | --- | --- |
| Final data check before commit | `BEFORE_COMMIT` | Can cause commit to fail; avoid non-DB side effects |
| Send notification after record is committed | `AFTER_COMMIT` | Needs reliable delivery mechanism if business-critical |
| Revert temporary state after rollback | `AFTER_ROLLBACK` | Do not write back to DB using the ended transaction |
| Record general completion metrics | `AFTER_COMPLETION` | Cannot distinguish outcome automatically |
| Process immediately when event is published | `@EventListener` | Can run even if the transaction later rolls back |

One event can carry a single business meaning while being observed by listeners at multiple points in time. However, when a later step's logic strictly depends on an earlier step's result, or tight rollback synchronization is needed, a sequential coordinating service is usually easier to control and test than a chain of callbacks spread across multiple beans.

## 8. Reactive Transactions Differ from Imperative Transactions

The examples use `PlatformTransactionManager` (JDBC/JPA) with thread-bound transactions. When using `ReactiveTransactionManager`, transaction info lives in the **Reactor Context** and does not automatically exist in `ThreadLocal`. Since Spring Framework 6.1, `@TransactionalEventListener` can work with reactive transactions when the context is passed into the event source via a supported mechanism, such as `TransactionalEventPublisher`.

Do not copy the `TransactionTemplate` example verbatim into a reactive pipeline and assume listeners will observe the same thread-bound transaction. Reactive flows require designing compatible event publishing and context propagation.

## 9. Self-Check Questions and Diagnostics

1. **Can one event have both `AFTER_COMMIT` and `AFTER_ROLLBACK` listeners?** Yes. They are registered for the same event type, but only the branch matching the transaction outcome runs.
2. **On commit, do all four phases run?** No. `AFTER_ROLLBACK` does not run.
3. **Does a normal rollback always invoke `BEFORE_COMMIT`?** No. It usually skips before-commit.
4. **Can a transaction both commit and roll back, causing `AFTER_COMPLETION` to run twice?** No. It only has one completion outcome.
5. **Can `@Order(-100)` on `AFTER_COMMIT` run before `BEFORE_COMMIT`?** No. Phase determines timing.
6. **Without a transaction, does a transactional listener run by default?** No; fallback can only be enabled with its own semantics.
7. **Can you write directly to the DB in `AFTER_COMMIT` and rely on the original transaction to commit again?** No. If writing is needed, a suitable new transaction must be created.
8. **Does publishing an event in a reactive transaction automatically put the transaction into thread-local?** No; reactive context propagation is required.

When debugging, log the event ID, publish timestamp, whether a transaction is active, callback phase, transaction outcome, and thread name. If a listener does not run, check whether the bean is Spring-managed, whether the event type/`condition` matches, whether a transaction is active, whether it rolled back, and whether `fallbackExecution` matches your requirements.

## References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionPhase API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework — TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
