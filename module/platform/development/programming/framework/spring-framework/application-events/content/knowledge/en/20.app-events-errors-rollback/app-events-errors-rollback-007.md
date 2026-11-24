# Fallback and Intentional Error Handling in Spring Application Events

## 1. Why Must You Design Fallbacks Instead of Only Using try/catch?

Spring Application Events allow a component to publish information about what happened via `ApplicationEventPublisher.publishEvent(...)` and let matching listeners react. However, "the event was published" **does not mean** "every listener succeeded," "the transaction committed," or "the event can be reprocessed after an application crash."

In this lesson, a **fallback** is a **pre-designed alternative processing path** when the normal path cannot continue: proceeding despite non-essential errors, executing work on the caller when an executor rejects, handling events when no transaction exists, persisting tasks to a durable outbox/queue, or transitioning to a compensating workflow. Each approach has different trigger conditions and reliability guarantees.

An intentional error-handling design must answer:

1. **Where is the error?** Listener, executor, transaction, downstream, or transport?
2. **Who is responsible?** Publisher, multicaster, listener, transaction manager, or retry worker?
3. **Can execution continue?** Is it a mandatory step or an auxiliary side effect?
4. **How is truth preserved?** Was it committed, durably persisted, and resendable?
5. **How is it observed?** Errors must be measurable; suppression must not become "hiding errors."
6. **Is retrying safe?** Idempotency, duplicates, and ordering must be defined.

**Principle:** Choose fallbacks based on **work criticality** and **execution conditions**, rather than placing a generic `catch (Exception)` and assuming all events were handled.

## 2. Four Meanings of "Fallback" That Are Easily Confused

| Mechanism | When does it trigger? | What does Spring provide? | What is it NOT? |
| --- | --- | --- | --- |
| **Multicaster ErrorHandler** | A listener throws an error while invoked by the multicaster | Can handle/log and suppress, or rethrow | Does not automatically retry or persist events |
| **Executor rejection fallback** | `SimpleApplicationEventMulticaster`'s executor rejects scheduling | Implementations with a `RejectedExecutionException` branch invoke the listener on the caller | Not a fail-fast guarantee or durable backpressure |
| **Transactional listener fallbackExecution** | Event is published with **no matching transaction** | `@TransactionalEventListener(fallbackExecution=true)` can process immediately | Not a post-rollback fallback; does not replace `AFTER_ROLLBACK` |
| **Business/reliability fallback** | External call fails, queue is full, network drops, consumer errors… | Application designs retries, outbox, DLQ, compensation… | Spring in-process events do not automatically guarantee delivery |

The word "fallback" in `fallbackExecution` and "fallback when executor rejects" **are not directly related**. One is a choice of whether to process an event when no transaction exists; the other is how to dispatch a listener when a task is rejected by the executor.

If asked "is there a fallback?", ask back: "**fallback from which step to which step, is losing work allowed, and who knows the outcome?**"

## 3. How Does an Error Flow Through ApplicationEventPublisher?

`ApplicationEventPublisher.publishEvent(Object)` hands the event off to the context's dispatch mechanism. With the default `SimpleApplicationEventMulticaster`, listeners run **synchronously on the publisher thread**. When a `TaskExecutor` is configured, listeners supporting async can be handed off to another thread.

```text
Application service
      |
      v
publishEvent(event)
      |
      v
SimpleApplicationEventMulticaster
      |
      +---- Listener A (sync or async)
      |          |
      |          +--> succeeds
      |          |
      |          +--> throws exception
      |                   |
      |             ErrorHandler?
      |             /         \
      |          No            Yes
      |           |             |
      |   propagate along     suppress or
      |   execution path      rethrow per policy
      |
      +---- Listener B
             |
             +--> may not be called if
                  sync error blocked dispatch loop

When an async executor is present:
   execute(listenerTask)
      |
      +--> accepted: runs on worker when scheduled
      |
      +--> RejectedExecutionException:
             SimpleApplicationEventMulticaster's fallback branch
             may invoke listener directly on caller
```

Notes:

- On the **sync** path, an unhandled error can propagate back to `publishEvent(...)`, causing the publisher to receive the exception. Subsequent listeners may not have been invoked.
- On the **async** path, the publisher may return before the listener runs. Errors occurring afterward do not automatically jump back onto the publisher's stack.
- For `@Async` listeners, exception handling also involves `AsyncUncaughtExceptionHandler` (especially when returning `void`); it is not identical to the multicaster's `ErrorHandler`.
- For transactional listeners, callback registration and post-commit/post-rollback invocation timing depend on `TransactionPhase`; they should not be treated like ordinary sync listeners in every stage.

**Do not design correctness on assumptions** that every listener is invoked once or that any exception automatically rolls back a transaction.

## 4. Synchronous Listener Errors: Propagate or Suppress?

### 4.1. Default: No ErrorHandler

`SimpleApplicationEventMulticaster` by default **has no `ErrorHandler`**. When a synchronous listener throws an exception:

- The exception can propagate back to where the event was published.
- Dispatch can stop at that listener; listeners ordered after it may not be called.
- If the publish call is inside a `@Transactional` method and the exception escapes the transaction boundary, the transaction manager can decide to roll back per the applicable rules.
- If the caller catches and swallows the exception **inside** the transactional method, the transaction may still commit; rollback does not happen automatically just because an exception occurred at some point.

You should not describe this as "when an event fails, Spring always rolls back everything." Spring Application Events is a notification mechanism, not a transaction manager.

### 4.2. Setting an ErrorHandler to Intentionally Continue

For a **non-essential** audit/telemetry event, it may be acceptable if listener A fails while listener B still gets a chance to run.

```java
import org.springframework.context.event.SimpleApplicationEventMulticaster;

SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();

multicaster.setErrorHandler(error -> {
    // Simple template: replace with controlled log/metric/alert.
    System.err.println("Listener failed: " + error.getClass().getName());
    // Do not throw -> error is suppressed here.
});
```

This is an **illustrative configuration snippet**, not yet registered as a Spring bean. In an application, the bean uses the standard name `applicationEventMulticaster`; the runnable example in Section 8 illustrates this fully.

When `ErrorHandler.handleError(Throwable)` **returns normally**, the multicaster considers the listener error handled and can proceed to the next listener. When the handler **throws an exception**, the error keeps propagating along the call path; if synchronous, the publisher may receive the error.

Spring provides helper policies such as `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`. However, "log and ignore" is unsuitable for tasks like generating invoices, posting ledger entries, or sending mandatory messages that must complete.

### 4.3. When Not to Suppress

If a listener executes a **mandatory** step for the business operation to be considered successful, suppressing can cause the caller to receive a false-success result:

```text
Publisher: "Invoice approved"
  |
  +--> Legal data recording listener fails
  |
  +--> ErrorHandler suppresses
  |
  +--> Caller sees success
```

If legal data is a mandatory requirement, it is better to put that operation into a transaction/business workflow with an explicit error contract, or persist the task durably to guarantee subsequent processing. A secondary event should only be treated as best-effort when **the business permits it**.

### 4.4. ErrorHandler Is Not a Retry System

`setErrorHandler(...)` receives the error thrown by a listener. Spring does not automatically retain a durable event copy, does not implement exponential backoff, does not cap retries, and does not create a dead-letter queue. Re-invoking the listener directly inside the handler can cause recursion, infinite loops, duplicate side effects, and missing transaction boundaries.

A practical handler should record error classification, event identity, listener identity, and correlation; if retry is required, route the work into **a managed mechanism** with explicit retry budgets and idempotency.

## 5. Executor Rejection: Falling Back to Caller Thread Is Not Fail-Fast

When using `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, certain listeners are submitted as tasks to the executor. If the executor throws `RejectedExecutionException` on `execute(...)`, Spring implementations include logic to **invoke the listener directly on the publishing thread** as a fallback, rather than silently dropping the event.

Consequences to account for:

1. **Thread/queue limits do not mean total-work limits**: if multiple publishers simultaneously fall back to inline execution, total concurrent listener runs can exceed the pool size.
2. **Caller latency increases**: an HTTP request or transactional flow may end up executing a heavy listener.
3. **Thread context differs from expectations**: the listener can see the caller's transaction/ThreadLocal during fallback, yet not see them on the normal async path.
4. **Listener errors can propagate back to the caller** when executed inline and not suppressed by an ErrorHandler.
5. **Do not assume `AbortPolicy` makes `publishEvent(...)` always throw `TaskRejectedException`**: that is merely executor behavior, while the multicaster has its own handling layer.

This fallback path helps avoid losing notifications while a pool is shutting down, yet **it is not a suitable backpressure contract for every domain**. Check the exact Spring version running, as the multicaster's implementation is the final authority.

An example executor intentionally rejecting:

```java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(task -> {
    throw new RejectedExecutionException("simulated overload");
});
```

This is an illustrative snippet; importing `java.util.concurrent.RejectedExecutionException` and registering the multicaster properly in the ApplicationContext are needed to run it. The complete example in Section 8 has a `reject` mode showing the listener is still invoked directly.

**Note:** Some `ApplicationListener` implementations, even when an executor is present, declare `supportsAsyncExecution() == false`—for example, transactional listeners that must bind to the transaction. They are invoked on the publisher thread rather than submitted to the pool.

### When Real Admission Control Is Needed

If the business requirement is "under overload, reject immediately," do not rely on the multicaster executor's `AbortPolicy` as the whole mechanism. You must rate-limit/shed requests **before** publishing, or send tasks to a queue/broker with an explicit accept/reject protocol.

When the requirement is "never lose an event," falling back to the caller is still not enough: the caller can crash, the listener can throw, or the transaction can roll back.

## 6. @TransactionalEventListener: Phases and fallbackExecution

`@TransactionalEventListener` differs from a regular `@EventListener` because the callback is tied to the outcome of **an active transaction**.

The phases:

| TransactionPhase | Timing | Scenario |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before actual commit | Validate/prepare work that must be bound to the transaction |
| `AFTER_COMMIT` (default) | After successful commit | Side effects that only make sense if data committed |
| `AFTER_ROLLBACK` | After rollback | Cleanup, intentional failure notification |
| `AFTER_COMPLETION` | After the transaction ends, whether commit or rollback | General metrics/cleanup, distinguishing outcomes when needed |

### 6.1. Fallback Is Off by Default

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Only processes when event is published inside a transaction and it commits.
}
```

The snippet above is an illustrative method inside a Spring bean with a transaction manager. **If no transaction is active at publish time**, Spring by default **skips this transactional callback**. The event is not deleted from the ApplicationContext; only the transaction-conditioned listener does not execute.

Skipping it is a **semantics-preserving decision**: you cannot promise "after commit" when there was no transaction to commit.

### 6.2. fallbackExecution=true: Running When There Is No Transaction

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void afterCommitOrNoTransaction(OrderPlaced event) {
    // With transaction: after commit succeeds.
    // Without transaction: processes when event is published.
}
```

Two cases must be clearly distinguished:

- **With transaction:** the listener attaches to the `AFTER_COMMIT` phase and only runs when the transaction commits successfully.
- **Without transaction:** the listener is invoked immediately via the fallback path; **no commit ever happened**.

When a transaction exists and **rolls back**, `fallbackExecution=true` **does not make the AFTER_COMMIT listener run anyway**. Fallback only handles the **no-transaction** situation, not "after commit failed."

### 6.3. Avoid fallbackExecution=true with AFTER_ROLLBACK Unless Intended

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void ambiguousRollbackListener(OrderPlaced event) {
    // May still be called via fallback even without a transaction.
}
```

This is a pattern **requiring careful thought**, because without a transaction the listener can execute immediately even though **no rollback ever occurred**. Do not use method/metric names like "rollbackConfirmed" for every invocation if a no-transaction fallback path exists.

If the genuine requirement is to act only after a rollback, `fallbackExecution=false` is usually right.

### 6.4. Reactive Transactions Differ from Thread-Bound Transactions

For transactions using `PlatformTransactionManager` in the standard model, transaction synchronization is bound to the thread. Starting from Spring Framework 6.1, transactional listeners can also work with reactive transactions when **the Reactor context is carried into the event** via the appropriate `TransactionalEventPublisher` mechanism. You cannot obtain reactive transaction state from `ThreadLocal` like standard servlet transactions.

An event published on another thread that loses transaction context can prevent a transactional listener from registering for the right phase. Do not "fix" that issue by blindly setting `fallbackExecution=true`; doing so can make callbacks run before data commits.

## 7. Rollback Is Not One Simple Type of Listener Error

Distinguish the milestones:

```text
@Transactional service
    |
    +--> DB changes in transaction
    |
    +--> publishEvent(OrderPlaced)
    |        |
    |        +--> @EventListener sync:
    |        |      runs immediately on publish
    |        |
    |        +--> @TransactionalEventListener AFTER_COMMIT:
    |        |      registers callback
    |        |
    |        +--> @TransactionalEventListener AFTER_ROLLBACK:
    |               registers callback
    |
    +--> transaction manager decides
             /                   \
            /                     \
          COMMIT                 ROLLBACK
            |                       |
            v                       v
       AFTER_COMMIT             AFTER_ROLLBACK
       callbacks                callbacks
```

Key points:

- A synchronous `@EventListener` is invoked **before the transaction ends**, so exceptions can propagate back into the service.
- If an exception escapes the transaction boundary, Spring rolls back per applicable transaction rules; for example, runtime exceptions roll back by default with declarative transactions, though rules can be customized.
- If the exception was caught/suppressed and the service still finishes normally, the transaction **can commit**.
- A failing `AFTER_COMMIT` listener **cannot turn back time to undo an already completed DB commit**.
- `AFTER_ROLLBACK` is a hook to observe a rollback outcome, not a way to "make any listener exception trigger a rollback."

**Post-completion resource warning:** In `AFTER_COMMIT`/`AFTER_ROLLBACK` phases, the transaction has ended yet some transaction resources remain bound to the thread during the callback. A DB write may appear to run without being committed as a new transaction. If post-completion results must be persisted, design a clear new transaction (e.g., a separate service with `REQUIRES_NEW` via an appropriate proxy) or a queue/outbox.

### Where Do @Transactional and No-Transaction Differ?

If `@TransactionalEventListener(fallbackExecution = true)` is invoked without a transaction, the listener runs immediately with no commit guarantee. Do not use it as a "safe fallback" for operations that must be durable. To guarantee an event always accompanies a DB commit, the right approach is **enforcing a transaction at the producer** or using a transactional outbox.

## 8. Runnable Maven/Java 17 Example: Four Error and Fallback Modes

This example uses **Java 17+**, **Spring Framework 6.2.12**, Maven, and in-memory H2 to illustrate two layers of mechanisms:

1. **`default`**: the first listener throws an error, no ErrorHandler; the publisher receives the exception.
2. **`suppress`**: ErrorHandler logs/suppresses; the second listener is still called.
3. **`reject`**: the executor always rejects; the multicaster attempts to run the listener on the caller.
4. **`tx`**: uses a real JDBC transaction to illustrate `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `fallbackExecution=true` when there is no transaction.

The transaction part uses H2 only to drive and manage a real transaction; no tables are needed to demonstrate phase callbacks. The result **demonstrates mechanics**, not a production transaction architecture.

### 8.1. Project Structure

```text
spring-event-fallback/
├── pom.xml
└── src/main/java/demo/EventFallbackDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-fallback</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.EventFallbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/EventFallbackDemo.java`:

```java
package demo;

import java.util.concurrent.RejectedExecutionException;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class EventFallbackDemo {

    public record FailureEvent(String id) {}
    public record RejectedEvent(String id) {}
    public record PhaseEvent(String id) {}

    public static final class Handlers {

        @Order(1)
        @EventListener
        public void first(FailureEvent event) {
            System.out.println("FIRST " + event.id());
            throw new IllegalStateException("simulated failure");
        }

        @Order(2)
        @EventListener
        public void second(FailureEvent event) {
            System.out.println("SECOND " + event.id());
        }

        @EventListener
        public void onRejected(RejectedEvent event) {
            System.out.println("REJECTED_EXECUTOR_FALLBACK " + event.id());
        }

        @Order(1)
        @EventListener
        public void immediate(PhaseEvent event) {
            System.out.println("IMMEDIATE " + event.id());
        }

        @Order(2)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(PhaseEvent event) {
            System.out.println("AFTER_COMMIT " + event.id());
        }

        @Order(3)
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true)
        public void afterCommitOrNoTx(PhaseEvent event) {
            System.out.println("COMMIT_OR_NO_TX " + event.id());
        }

        @Order(4)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(PhaseEvent event) {
            System.out.println("AFTER_ROLLBACK " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        Handlers handlers() {
            return new Handlers();
        }

        @Bean
        DataSource dataSource() {
            JdbcDataSource dataSource = new JdbcDataSource();
            dataSource.setURL("jdbc:h2:mem:eventfallback;DB_CLOSE_DELAY=-1");
            dataSource.setUser("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }
    }

    private static AnnotationConfigApplicationContext createContext(
            String mode) {
        var context = new AnnotationConfigApplicationContext();

        // Register before refresh so context uses this multicaster.
        context.registerBean(
                "applicationEventMulticaster",
                SimpleApplicationEventMulticaster.class,
                () -> {
                    var multicaster = new SimpleApplicationEventMulticaster();
                    if ("suppress".equals(mode)) {
                        multicaster.setErrorHandler(error ->
                                System.out.println("HANDLED "
                                        + error.getClass().getSimpleName()));
                    }
                    if ("reject".equals(mode)) {
                        multicaster.setTaskExecutor(task -> {
                            throw new RejectedExecutionException(
                                    "simulated pool saturation");
                        });
                    }
                    return multicaster;
                });

        context.register(Config.class);
        context.refresh();
        return context;
    }

    private static void runFailure(
            AnnotationConfigApplicationContext context) {
        try {
            context.publishEvent(new FailureEvent("F1"));
            System.out.println("PUBLISH_RETURNED");
        } catch (RuntimeException error) {
            System.out.println(
                    "PUBLISH_FAILED " + error.getClass().getSimpleName());
        }
    }

    private static void runReject(
            AnnotationConfigApplicationContext context) {
        System.out.println("BEFORE_REJECT");
        context.publishEvent(new RejectedEvent("R1"));
        System.out.println("AFTER_REJECT");
    }

    private static void runTransactions(
            AnnotationConfigApplicationContext context) {
        var template = new TransactionTemplate(
                context.getBean(PlatformTransactionManager.class));

        template.execute(status -> {
            context.publishEvent(new PhaseEvent("C1"));
            return null; // TransactionTemplate commits when callback succeeds.
        });

        template.execute(status -> {
            context.publishEvent(new PhaseEvent("R1"));
            status.setRollbackOnly();
            return null; // TransactionTemplate rolls back due to rollback-only.
        });

        context.publishEvent(new PhaseEvent("N1")); // No transaction.
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "default" : args[0];

        try (var context = createContext(mode)) {
            switch (mode) {
                case "default", "suppress" -> runFailure(context);
                case "reject" -> runReject(context);
                case "tx" -> runTransactions(context);
                default -> throw new IllegalArgumentException(
                        "mode must be default, suppress, reject or tx");
            }
        }
    }
}
```

Note: `import org.springframework.transaction.annotation.Propagation;` in the snippet is unused; that import line can be removed without changing behavior or output. Java permits unused imports syntactically, though some projects' static analysis will warn.

### 8.2. Running and Understanding Each Mode

Run default:

```bash
mvn -q compile exec:java -Dexec.args=default
```

Lines printed by the program (excluding library logs):

```text
FIRST F1
PUBLISH_FAILED IllegalStateException
```

**Why is there no SECOND?** The `@Order(1)` listener throws `IllegalStateException`; the synchronous multicaster has no ErrorHandler, so the exception stops the active dispatch pass and reaches the publisher.

Run suppress:

```bash
mvn -q compile exec:java -Dexec.args=suppress
```

Application output lines:

```text
FIRST F1
HANDLED IllegalStateException
SECOND F1
PUBLISH_RETURNED
```

The ErrorHandler installed on the multicaster received the error and **did not rethrow**. The other listener is still called; from the publisher's side, `publishEvent` returns normally. This is **best effort** and does not prove the first listener succeeded.

Run reject:

```bash
mvn -q compile exec:java -Dexec.args=reject
```

Application output lines:

```text
BEFORE_REJECT
REJECTED_EXECUTOR_FALLBACK R1
AFTER_REJECT
```

The executor intentionally throws `RejectedExecutionException` for every task. The multicaster per the demonstrated implementation catches the rejection and invokes the listener directly. The output appears **between** the publisher's two print lines, so the event cannot be considered to have run asynchronously in this case.

Run transaction:

```bash
mvn -q compile exec:java -Dexec.args=tx
```

Application output lines in callback registration and `@Order` order in the example:

```text
IMMEDIATE C1
AFTER_COMMIT C1
COMMIT_OR_NO_TX C1
IMMEDIATE R1
AFTER_ROLLBACK R1
IMMEDIATE N1
COMMIT_OR_NO_TX N1
```

Meaning:

1. `C1` published **inside a transaction** that then commits: the regular listener runs immediately, and both `AFTER_COMMIT` listeners run after commit.
2. `R1` published **inside a transaction** that then rolls back: the regular listener still ran before rollback; the `AFTER_ROLLBACK` listener is called, while neither `AFTER_COMMIT` listener is called.
3. `N1` published **without a transaction**: the regular listener runs immediately; the default `AFTER_COMMIT` listener is skipped; the listener with `fallbackExecution=true` runs immediately despite no commit; `AFTER_ROLLBACK` also does not run.

The H2 path uses a real transaction manager without a "business table." Hence this only illustrates listener timing, **not an atomicity test of a DB-writing business operation**.

### 8.3. Limitations of the Example

- Mode `reject` simulates an executor rejecting tasks rather than measuring real throughput of a bounded thread pool.
- Mode `suppress` only prints the error instead of emitting metrics/tracing/alerts; production requires sufficient observability to surface hidden failures.
- Mode `tx` uses `TransactionTemplate` instead of a `@Transactional` proxy so transaction boundaries are unambiguous.
- The program does not perform HTTP calls, send emails, or queue messages; those are tasks requiring dedicated retry/fallback designs.
- All events are in-memory objects within a single JVM. A `publishEvent` call creates no durable outbox records.
- When configuring an asynchronous multicaster or `@Async`, stdout ordering and error paths no longer resemble the sync example.

## 9. Error-Handling Strategies by Criticality Level

You should not choose a global ErrorHandler without classifying listeners. They can be split by criticality:

### 9.1. Mandatory Business Step: Fail Fast or Explicit Transaction

If payment cannot finish successfully without updating the ledger, keep the mandatory logic inside the application/domain service or required transaction. Do not let a best-effort `@EventListener` decide core correctness through hidden side effects.

One way to think about it:

```text
Command CapturePayment
        |
        v
Validate + Authorize
        |
        v
Write canonical payment state + ledger (transaction boundary)
        |
        +--> fail -> command returns error / rolls back per rule
        |
        +--> commit succeeded -> can publish PaymentCaptured
```

If the system must publish externally without losing events between commit and publish, write an **outbox record in the same transaction** and relay to the broker. Calling `ApplicationEventPublisher` right after commit does not by itself eliminate the crash window.

### 9.2. Non-Essential Side Effect: Observable Best Effort

For example, updating a rebuildable cache:

- A listener failure does not necessarily fail the core business operation.
- You can suppress so other consumers proceed, **provided** you emit contextual metrics/logs and have an appropriate repair channel.
- Do not log a blanket "success" spanning the whole pipeline when a listener actually failed.

Example policy sketch:

```text
CacheWarmupEvent
  ├── cache refresh succeeded -> done
  └── cache error -> metric + structured log
                  -> cache has TTL/rebuilds when needed
                  -> does not roll back order
```

### 9.3. Important Work That Can Complete Later: Durable Retry

For example, sending an electronic invoice to an external gateway that may be slow or intermittently down. If eventual completion must be guaranteed:

1. Write the work item/outbox to durable storage.
2. A worker picks up the task with a stable idempotency key.
3. Distinguish transient errors from permanent errors.
4. Retry with bounded attempts and backoff/jitter, no busy-looping.
5. Beyond the limit, transition to manual handling/quarantine/DLQ.
6. Provide replay tools with auditing; avoid sending duplicate invoices on retry.
7. Ensure work status is observable and alerted.

No `ErrorHandler` class in Spring Application Events performs that lifecycle automatically.

### 9.4. Distributed Workflows Requiring Compensation

If a business transaction spans multiple systems, rolling back database A cannot undo a sent email or a captured charge at a provider. When needed, design a **compensating action** with explicit rules, such as issuing a refund after an order is canceled.

Compensation is a **new business action** that can itself fail and needs its own retry/idempotency, not "reversing everything" by throwing an exception.

## 10. Choose Retry, Ignore, Compensate, or Fail?

| Error type | Example | Suggested policy |
| --- | --- | --- |
| Invalid input/domain | Invalid order | Return error/fail fast; no automatic retry |
| Authorization failure | Actor lacks tenant permission | Reject; do not use a fallback that bypasses permissions |
| Transient network error | HTTP 503, temporary timeout | Bounded retry, backoff/jitter, idempotency |
| Permanent downstream rejection | Payload rejected due to bad schema | Quarantine/DLQ or fix data; do not retry forever |
| Executor saturation | Out of workers/queue | Admission control, appropriate scaling, or durable queue |
| Listener bug | `NullPointerException` from code | Log/alert, fix bug; retrying does not fix bugs |
| Transaction rollback | DB constraint, business validation | Do not emit "committed" claims; `AFTER_ROLLBACK` if needed |
| No transaction context | Published outside transaction | Use explicit policy: skip transactional listener or `fallbackExecution=true` when valid |
| Worker/process crash | Event living only in RAM | Require durable outbox/broker/storage if loss is unacceptable |
| Duplicate delivery | Broker retry/redelivery | Idempotent consumer keyed by event/business key |

**Do not retry forever** on unrecoverable errors. **Do not ignore** errors that the business contract requires handling. Every policy should have an owner, time bounds, attempt limits, final outcome, and monitoring.

## 11. Intentional Patterns

### Pattern A — ErrorHandler Solely to Observe Non-Essential Errors

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(error -> {
        // Record contextual error metric/log, with redaction policy.
        // Do not throw: other listeners can continue.
        errorMetrics.increment("spring_event_listener_failure");
        eventLogger.warn("Noncritical event listener failed", error);
    });
    return multicaster;
}
```

This is an **illustrative design snippet**, not standalone runnable code: `errorMetrics` and `eventLogger` are application dependencies not defined in the snippet, and appropriate Spring Configuration/Bean imports are required. Do not apply blindly to all events if critical listeners exist.

### Pattern B — Managing Errors Inside the Listener With Explicit Outcome

```java
@EventListener
public void onNotificationRequested(NotificationRequested event) {
    try {
        notificationSender.send(event.recipientId(), event.messageId());
    } catch (TemporaryTransportException ex) {
        retryQueue.enqueue(event); // Must be a queue with a durable contract.
    }
}
```

This snippet is **pseudocode**: service/exception types must be defined by the application. If writing to the retry queue fails, you must not suppress the error and claim the work was preserved. Be explicit about whether `enqueue` confirms durability before the listener returns.

Also, avoid retrying when the send actually succeeded yet the response was lost; use a stable idempotency key downstream when supported.

### Pattern C — Transactional Outbox

```text
@Transactional
  update business row
  insert outbox event (same database transaction)
  COMMIT
       |
       v
outbox relay polls/CDC
       |
       +--> broker success -> mark published
       |
       +--> failure -> retain + retry
       |
       v
consumer processes with deduplication
```

An outbox prevents the "DB committed yet process died before publishing" window, provided the business update and outbox insert genuinely share **the same transaction**. It can still produce duplicates when the relay crashes between sending and marking published, requiring idempotent consumers.

### Pattern D — After-Rollback Observability

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onOrderRolledBack(OrderAttempted event) {
    // Metrics/log/cleanup for an event published in the transaction
    // that just rolled back; do not assume a committed record exists.
}
```

This is an illustrative snippet requiring a Spring bean/transaction manager and `OrderAttempted` type. Do not use this callback to write a new record on the old transaction; if a durable failure audit is needed, explicitly create a new transaction or durable channel independent of the rolled-back transaction.

## 12. Do Not Confuse Suppression With Rollback and Consistency

Common error sequences:

**Case 1 — Sync listener fails, transaction rolls back**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
    listener throws RuntimeException
  -> exception propagates out of transaction boundary
  -> rolls back per transaction rule
```

This path only happens if the exception actually escapes in accordance with rollback rules. If the listener throws yet the publisher catches and treats it as success, the outcome differs.

**Case 2 — ErrorHandler suppresses, transaction commits**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
    listener throws
    ErrorHandler suppresses
  method returns normally
  -> transaction may commit
```

In this case, you must not claim "all event processing succeeded." Only the fact that **the publisher did not receive that exception** is true.

**Case 3 — AFTER_COMMIT listener fails**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
  DB COMMIT succeeded
  AFTER_COMMIT callback throws
  -> DB already committed; cannot roll back the commit that just happened
```

The exception may be logged or have propagation behavior depending on the phase/transaction integration; do not infer a rollback outcome. For mandatory post-commit work, a durable work queue/outbox is more reliable than an in-memory callback without replay.

**Case 4 — No transaction + fallbackExecution=true**

```text
publishEvent(OrderPlaced) (no transaction)
  transactional listener with fallbackExecution=true
  -> handler runs immediately
  -> no commit occurred
```

The name `AFTER_COMMIT` in the annotation does not turn the fallback path into a commit guarantee.

## 13. Identity and Idempotency for Fallback/Retry

If a fallback routes work to a retry queue, it must carry enough data to replay **the exact work**:

- `eventId`: occurrence identifier, used for deduplication.
- `eventType`/schema version: so consumers parse the payload properly.
- `aggregateId` and version: to check ordering/state if needed.
- `tenantId`: multi-tenant data isolation (never use as authorization proof).
- `correlationId` and `causationId`: tracing a processing flow.
- `occurredAt`: when the fact happened, distinct from retry time.
- `attempt`/retry metadata: belongs on the work item/transport as a delivery detail, without distorting domain facts.

When retrying, usually **keep the original fact's eventId**. Do not mint a new event ID on each delivery attempt and trick consumers into thinking it is a new fact. If an entirely new business fact arises, that is a separate event with its own ID.

Distinguish **at-least-once delivery** from **exactly-once side effects**: brokers can redeliver the same message, and consumers must guard against duplicate side effects. A common approach is storing processed `(consumerName, eventId)` in the same transaction as the business update.

If a listener calls a payment gateway, in addition to consumer deduplication you also need an idempotency key at the provider; timeouts can happen **after** the provider already succeeded.

## 14. What Should You Observe When Using Fallbacks?

A system whose ErrorHandler only logs a single line cannot claim to have "handled errors." Key signals:

| Metric/signal | What does it answer? |
| --- | --- |
| `listener_attempt_total` | How many processing attempts were made? |
| `listener_failure_total` by event/error type | What is the actual failure rate? |
| `listener_suppressed_total` | How many errors were ignored by a best-effort policy? |
| `executor_rejected_total` | How often did the pool reject tasks? |
| `caller_fallback_total` | How many listeners had to run on the publisher thread? |
| `transaction_phase_callbacks_total` | How many AFTER_COMMIT / AFTER_ROLLBACK / no-TX fallback invocations? |
| `outbox_pending_count` and oldest record age | Is durable work piling up? |
| `retry_attempt_total` and job age | Are there continuous retry loops or excessive delays? |
| `dead_letter_count` / quarantine count | How many tasks require manual intervention? |
| `idempotency_duplicate_total` | Are there frequent redeliveries/duplicate runs? |

These are **suggested application-instrumented metric names**, not metrics automatically provided by Spring. Avoid using arbitrary `eventId`, `userId`, or `tenantId` as ultra-high-cardinality labels; put them in controlled structured logs/traces instead of exploding metric series.

When logging errors, include minimal context while avoiding credentials, access tokens, full events containing PII, or sensitive payment data.

## 15. Essential Test Scenarios

| Scenario | Setup | Expected outcome |
| --- | --- | --- |
| Sync listener fails, no ErrorHandler | Listener A throws; B after A | Publisher receives error; B may not be called |
| ErrorHandler suppresses | A fails; ErrorHandler does not throw | Failure is observed; B proceeds |
| ErrorHandler propagates | Handler logs and throws | Sync publisher receives error |
| Executor rejects | Executor `execute` throws `RejectedExecutionException` | Verify version-specific multicaster fallback and latency impact |
| Executor accepts task but listener throws | Async worker exception | Do not assume sync caller sees the error |
| `@Async void` listener throws | With `@EnableAsync` | Observe `AsyncUncaughtExceptionHandler` or equivalent config |
| Transaction commits | Publish inside real transaction, commit | `AFTER_COMMIT` called, `AFTER_ROLLBACK` not |
| Transaction rolls back | Publish then roll back | `AFTER_ROLLBACK` called, `AFTER_COMMIT` not |
| Publish without transaction | Transactional listener `fallback=false` | Callback skipped |
| Publish without transaction | Transactional listener `fallback=true` | Callback runs **without a commit** |
| Transaction rolls back + `fallback=true` | `AFTER_COMMIT` listener | Does not invoke fallback as if no transaction existed |
| `AFTER_COMMIT` listener writes DB | Without new transaction | Verify actual commit behavior, do not trust a "saved" log |
| Post-commit side effect fails | Crash/timeout after commit | Critical work can be replayed from outbox |
| Retry same event | Same `eventId` sent multiple times | Consumer does not duplicate side effects |
| Cross-tenant | Fallback/retry carries `tenantId` | Must not read/write wrong tenant |
| Shutdown with backlog | Executor stopping | Verify tasks are completed, run on caller, rejected, or dropped per policy |
| Permanent failure | Invalid payload/schema | No infinite retries; quarantine/alert |
| Partial success | Listener A succeeds, B fails | Proper status/compensation, never label whole flow "success" |
| Multiple instances | Two nodes publishing or consuming | Scope-appropriate idempotency/routing |

Do not rely solely on `Thread.sleep(...)` to simulate overload. Use `CountDownLatch`/bounded executors with reproducible conditions, or a mock executor actively throwing rejections as in Section 8.

## 16. Common Design Mistakes

1. **Calling every catch a fallback.** Catching and logging does not complete work or persist it for retry.
2. **Suppressing errors from essential listeners.** Callers see success even though a mandatory step was lost.
3. **Thinking `ErrorHandler` automatically retries.** It only receives errors, with no durable work or retry budget.
4. **Setting a global ErrorHandler without classifying business criticality.** One policy does not fit all events.
5. **Confusing executor rejection with default fail-fast.** The multicaster can fall back to running inline on the caller.
6. **Assuming a bounded queue prevents all overload.** Caller fallback can increase total active work and prolong requests.
7. **Assuming an async listener throwing an error rolls back the publisher's transaction.** Different thread/stack and no shared default transaction.
8. **Using `fallbackExecution=true` to handle post-rollback.** It applies when **there is no transaction**, not on rollback.
9. **Enabling fallback for `AFTER_ROLLBACK` and logging "rollback happened" without a transaction.** Recorded facts are wrong.
10. **Using `AFTER_COMMIT` as a message-delivery guarantee.** The process can crash after commit before running the callback.
11. **Writing to the DB in an `AFTER_COMMIT` callback without creating a new transaction.** Changes may fail to commit.
12. **Publishing facts before commit and letting external listeners act.** Transaction rollback can leave downstream acting on an un-durable fact.
13. **Retrying the entire workflow even though some side effects succeeded.** Can duplicate payments/emails/invoices.
14. **Lacking a stable idempotency key.** Retries minting new event IDs break deduplication.
15. **Not distinguishing transient from permanent errors.** Infinite retries on invalid schema or unauthorized requests.
16. **Using fallbacks to bypass permission checks.** Security is not optional depending on circumstances.
17. **Hiding errors in unmonitored logs.** Metrics, alerts, final statuses, and runbooks are needed.
18. **Confusing Spring application events with a message queue.** In-memory publishing has no automatic persistence/replay.
19. **Not testing phases with real transactions.** Mocked `@Transactional` on private methods or self-invocation may not create transactions as expected.
20. **Ignoring shutdown and executor saturation.** "No errors in dev" does not guarantee the app handles load and shuts down safely.

## 17. Fallback Design Process Before Implementation

**Step 1 — Identify the business fact.** What does the event represent; is processing mandatory or purely observational?

**Step 2 — Define failure points.** Sync listener, task scheduling, business transaction, external call, broker publish, or consumer commit?

**Step 3 — Decide valid outcomes.** Fail-fast/rollback, best-effort, pending-for-retry, compensating, or quarantine? Who owns the decision?

**Step 4 — Choose mechanisms per layer.** `ErrorHandler` for multicaster-invoked listener errors, `fallbackExecution` for absence of transaction, admission control for overload, outbox/broker for durability, transaction rules for rollback.

**Step 5 — Design metadata propagation and storage.** Event ID, tenant, aggregate, correlation, occurrence time, and contract-compliant schema, not runtime objects.

**Step 6 — Ensure retry safety.** Idempotency, retry budget, exponential backoff, timeouts, DLQ/quarantine, version compatibility.

**Step 7 — Test actual outcomes.** Sync/async, commit/rollback/no transaction, executor rejection, crash between commit and publish, duplicates, and shutdown.

**Step 8 — Operate with observability.** Metrics/errors/alerts, replay runbooks, final ownership, data retention, and security.

### Quick Decision Checklist

- [ ] Every listener is classified as **critical** or **best effort**.
- [ ] Clear understanding of which exceptions reach the publisher and which only appear on workers.
- [ ] Suppressing `ErrorHandler` is used only when the task is allowed to fail and is monitored.
- [ ] Executor rejection and caller fallback path are tested.
- [ ] Explicitly understood that `fallbackExecution=true` only handles **no transaction**.
- [ ] `AFTER_COMMIT`/`AFTER_ROLLBACK` callbacks are not mistaken for commit undo mechanisms.
- [ ] Critical side effects have durable storage/outbox or replay paths.
- [ ] Retries and compensation have idempotency, timeouts, and limits.
- [ ] Fallbacks never bypass authorization or alter tenant scope.
- [ ] Metrics and alerts exist for suppressed errors, backlogs, and stale failed tasks.

**Conclusion:** "Fallback and intentional error handling" is not a single annotation. `ErrorHandler` decides the response to exceptions when listeners run; the multicaster may fall back to running listeners on the caller when the executor rejects; `fallbackExecution=true` only opens processing **without a transaction**; while requirements for retry, replay, rollback, or zero lost events must be engineered at the business and infrastructure levels. Ensure every error path has **clear outcomes, limits, and observability**.

## References

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2.6 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — Multicaster source code](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/event/SimpleApplicationEventMulticaster.java)
