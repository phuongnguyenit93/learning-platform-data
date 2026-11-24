# Listener Not Called in Spring Framework Application Events — Diagnostic Procedure

## 1. Identifying the Right Symptom

When calling:

```java
publisher.publishEvent(new OrderSubmitted("O-101"));
```

but the `@EventListener` method is not seen running, there are at least **four different possibilities**:

1. **No event is actually published** on the execution path under inspection: an `if` branch is not reached, an exception occurs before the call, or the code calls the wrong publisher/context.
2. **The listener is not registered by Spring**: the bean is outside component scan, is not a Spring-managed bean, is declared lazy, or the annotation-processing infrastructure has not been initialized.
3. **The event was published but does not match the listener**: wrong Java type/generic, a SpEL `condition` evaluates to `false`, or the listener resides in a context that does not receive the source event.
4. **The listener is registered but it is not time to run / conditions to run are not met**: `@TransactionalEventListener` is waiting for commit or is skipped due to no transaction, an async listener is still waiting in the executor, or an exception was handled/logged on another thread.

The first two questions should be separated:

- **Did the publisher emit the right event?** Verify that `publishEvent` is called with the exact type and payload.
- **Did the target listener receive/process the event?** Verify bean registration, event type, context, filter, transaction phase, and execution timing.

A missing log line is **not sufficient proof** that the listener was never called at all. Logs may be filtered by level, sent to a different logger, or asynchronous processing may not have finished yet.

This article focuses on Spring Framework applications using `ApplicationEventPublisher`, `ApplicationListener`, `@EventListener`, and `@TransactionalEventListener`. Spring Boot notes are covered separately because Boot startup ordering introduces very early events.

## 2. Understand the Processing Flow Before Changing Code

The path of an event in an application can be visualized as:

```text
Business code
  |
  +-- ApplicationEventPublisher.publishEvent(EventA)
          |
          +-- ApplicationContext receives event
                  |
                  +-- ApplicationEventMulticaster
                          |
                          +-- Find registered listeners
                          |
                          +-- Filter by event type / generic
                          |
                          +-- Check condition (if present)
                          |
                          +-- Standard @EventListener:
                          |       invoke handler synchronously (default)
                          |       or submit async task
                          |
                          +-- @TransactionalEventListener:
                                  register callback by transaction phase
                                  and run only when phase condition is satisfied
```

By default, Spring uses `SimpleApplicationEventMulticaster` and dispatches **synchronously on the publisher thread**. When an executor is configured on the multicaster or `@Async` is used, the path becomes asynchronous and must be inspected separately.

**`publishEvent` returns `void`**: it does not return the number of listeners invoked, does not return processing results, and does not confirm that side effects (DB, email, HTTP) succeeded. If the code has a custom multicaster or error handler, error-reporting behavior may also differ from the default.

Quick identification table:

| Evidence observed | What can be concluded | What cannot yet be concluded |
| --- | --- | --- |
| Spy/mock sees `publishEvent(OrderA)` | Business code called the publisher | Spring context dispatched to the real listener |
| `@RecordApplicationEvents` sees `OrderA` | Spring Test context recorded the published event | Async listener has finished processing |
| Breakpoint enters handler | Handler was actually called | Transaction committed or side effects completed |
| Log from `AFTER_COMMIT` listener | Post-commit callback was triggered | Async/external task is durably persisted |
| No log observed | No visual evidence yet | Not enough to assert the event was not published |

## 3. Low-Step, Verifiable Diagnostic Procedure

Instead of changing annotations randomly, follow this order:

1. **Check the publisher:** place a breakpoint right before/after `publishEvent`, log the **event class** and business ID; rule out unreached code branches.
2. **Check the listener bean:** confirm the listener class is a Spring-managed bean in the target context, and is not marked `@Lazy` preventing listener method registration.
3. **Check the event type:** compare the runtime type of the published object with the `@EventListener` parameter or `ApplicationListener<T>` generic; pay special attention to wrappers and generics.
4. **Check `condition`:** temporarily remove the filter in an isolated test or evaluate SpEL against the exact payload/arguments.
5. **Check the context:** are the event and listener in the same `ApplicationContext` or in the appropriate parent/child propagation direction?
6. **Check the transaction:** does the listener use `@TransactionalEventListener`? Is the event published **inside** an active transaction? Did the transaction end with commit or rollback?
7. **Check async:** does the listener use `@Async`/executor? Was submission rejected, was there an exception in the worker, did the test wait for completion?
8. **Verify with a test:** write a reproducible test that observes the event; only then change the design.

This approach reduces the chance of mistakenly "fixing" a listener that is working normally but **has not reached its execution phase yet**.

## 4. Cause 1: The Listener Is Not a Spring-Managed Bean

An `@EventListener` method on an object manually created with `new` **does not automatically register** with the Spring event infrastructure:

```java
public class OrderObserver {

    @EventListener
    public void onSubmitted(OrderSubmitted event) {
        System.out.println("submitted " + event.id());
    }
}

// In other code:
OrderObserver observer = new OrderObserver(); // Does not create a listener in the context.
```

This is **illustrative code**, not a standalone program. Spring only automatically detects annotated methods on **beans belonging to the ApplicationContext** configured accordingly.

Common approach in Spring Boot:

```java
@Component
public class OrderObserver {

    @EventListener
    public void onSubmitted(OrderSubmitted event) {
        // Registered if the bean is within component scan scope.
    }
}
```

Requires importing `org.springframework.stereotype.Component` and `org.springframework.context.event.EventListener`.

Or declare the bean via Java configuration:

```java
@Configuration
public class EventsConfig {

    @Bean
    OrderObserver orderObserver() {
        return new OrderObserver();
    }
}
```

This is an illustrative snippet; requires importing `Configuration` and `Bean`. Choose **one** sensible registration approach; do not mix manual bean creation and component scanning to produce multiple uncontrolled copies.

### 4.1. Wrong Component Scan Scope

`@SpringBootApplication` includes component scanning starting from the package containing the main/configuration class and its subpackages by default. If the handler lives in a sibling package or outside that scope, it will not become a bean unless you expand the configuration.

Example:

```text
com.example.app.MainApplication
com.example.app.orders.OrderService
com.example.events.OrderObserver   <- may lie outside the default scan
```

Do not fix this by scanning all packages at the system root. Place configuration in an appropriate parent package or explicitly declare `@ComponentScan`/`@Import`. In plain Spring Framework applications, ensure `@ComponentScan` or `@Import` targets the right package, or define a `@Bean`.

**Verifiable check:** if using a deterministic context, you can check `context.getBean(OrderObserver.class)` or inspect bean names via `getBeanNamesForType`, rather than merely seeing the annotation in source code. However, having the bean is **not enough** if the listener does not match the event or its method was not registered.

### 4.2. `@Lazy` Is a Specific Trap for `@EventListener`

Spring Framework notes that **you should not define `@EventListener` listener beans as lazy**: the context will honor lazy initialization and **will not register the method to listen for events** in the normal processing path.

An easily missed example:

```java
@Component
@Lazy
public class LazyOrderObserver {

    @EventListener
    public void handle(OrderSubmitted event) {
        // May not be registered as an event listener.
    }
}
```

This is illustrative code; requires importing `Lazy` and `Component`. Do not use `@Lazy` as an unchecked optimization for beans containing critical event handlers. If the application enables global lazy initialization, check its impact on listener beans and ensure eager initialization where needed.

Practical advice: test with a minimal, non-lazy listener bean instantiated by the context; if the event is received, continue investigating the real bean configuration.

### 4.3. `@EventListener` Processing Infrastructure

`@EventListener` is supported by Spring's bean post-processing mechanism, including `EventListenerMethodProcessor`. With `AnnotationConfigApplicationContext` or standard Boot configuration, the necessary annotation infrastructure is already registered.

If you manually build a very minimal `GenericApplicationContext` and register bean definitions by hand **without registering annotation configuration processors**, do not assume `@EventListener` will be scanned automatically as in Boot. Fix this by configuring Spring's annotation infrastructure properly rather than calling the listener method manually to "pretend" the event bus works.

## 5. Cause 2: Event Type or Generic Mismatch

Spring filters listeners by **event type**. Two classes with the same simple name in different packages are still two different types.

```java
public record OrderCreated(String id) {}
public record OrderConfirmed(String id) {}

@EventListener
public void onConfirmed(OrderConfirmed event) {
    // Does not receive a published OrderCreated.
}
```

Illustrative code: `publisher.publishEvent(new OrderCreated("O-1"))` does not cause `onConfirmed` to run.

### 5.1. `ApplicationEvent` Subclass vs. Payload Object

Spring supports both:

```java
public class OrderCreatedEvent extends ApplicationEvent {
    public OrderCreatedEvent(Object source) {
        super(source);
    }
}
```

and plain Java payloads:

```java
public record OrderCreated(String id) {}
```

If an object does not extend `ApplicationEvent`, Spring can wrap it in `PayloadApplicationEvent` for dispatching. Still, an `@EventListener` handler accepting **the payload type itself** remains the standard approach:

```java
@EventListener
public void onCreated(OrderCreated event) {
    // Receives the record payload.
}
```

Do not accidentally write an `@EventListener` that only accepts `OrderCreatedEvent` if the publisher emits the `OrderCreated` record. Also, do not wrap the payload in another custom wrapper and expect a listener typed for the inner payload to be unwrapped arbitrarily.

### 5.2. Generic Type Erasure

Example:

```java
public class EntityChanged<T> extends ApplicationEvent {
    public EntityChanged(T entity) {
        super(entity);
    }
}

@EventListener
public void onCustomerChanged(EntityChanged<Customer> event) {
    // Depends on generic metadata resolvable at runtime.
}
```

This is **illustrative code**, requiring `Customer` to be defined. Due to Java generic type erasure, Spring cannot always know `EntityChanged<Customer>` from a plain `new EntityChanged<>(customer)`. If filtering by generic is required, use a fixed subtype such as `CustomerChangedEvent extends EntityChanged<Customer>` or `ResolvableTypeProvider` per the official documentation.

**Diagnosis:** temporarily use a listener for a concrete event class in a test to verify dispatching; only afterward add generic filtering.

### 5.3. Method Annotation and Signature

The simplest `@EventListener` method takes **one event parameter**, or zero parameters when specifying event types on the annotation:

```java
@EventListener(OrderCreated.class)
public void createdWithoutArgument() {
    // No parameter required because the class is explicitly specified.
}
```

Illustrative code. For a single-parameter method, Spring usually infers the event type from the parameter itself. A method with multiple parameters incompatible with the `@EventListener` contract can cause configuration failure or behave differently than expected. Check actual startup errors; do not switch to multiple parameters like a controller method.

## 6. Cause 3: SpEL `condition` Filters Out the Event

A listener may be **properly registered** yet the `condition` expression evaluates to `false`:

```java
@EventListener(condition = "#a0.state() == 'READY'")
public void onReady(TicketEvent event) {
    // Receives only events with state() == "READY".
}
```

Illustrative code where `TicketEvent` is a record with a `state()` method; `#a0` refers to the first argument, avoiding reliance on parameter names stored in bytecode.

If `new TicketEvent("T-1", "REJECTED")` is published, the listener **not running is the expected behavior**.

Things to check:

- Actual value inside the event: `"READY"` differs from `"ready"` or `"READY "`.
- Does the expression invoke the right property/method on the payload type?
- Are `#a0`, `#p0`, parameter names, or `#root.event` used in the right context?
- Is the code compiled with `-parameters` if the expression depends on parameter names?
- If the event is a payload object, `#root.event` may be `PayloadApplicationEvent`, not the record directly.
- Is there an exception during expression evaluation? If so, inspect the stack trace rather than interpreting it as a simple filter.

In an isolated test, compare a listener **without condition** against the listener **with condition**. If the first runs and the second does not, you have almost certainly isolated the problem to the expression or input data.

## 7. Cause 4: Publishing to the Wrong `ApplicationContext` or Wrong Propagation Direction

Spring event infrastructure is tied to **ApplicationContext**. In systems with parent/child contexts (e.g., legacy web setups, multiple servlet contexts, or tests creating two contexts), the listener may reside in a **different** context from the publisher.

Propagation direction matters:

```text
Parent ApplicationContext
  |
  +-- Parent listeners
  |
  +-- Child ApplicationContext
         |
         +-- Child listeners
```

- Events published in **Child** are normally handled in Child and then propagate **up to Parent**.
- Events published in **Parent** **do not propagate down to Child by default**.
- Two independent contexts without a parent/child relationship **do not share a common event bus**.
- Listeners in both Parent and Child, or republished events, can cause duplicate observation; that is a different issue from "not called".

Counterexample:

```java
try (var first = new AnnotationConfigApplicationContext(FirstConfig.class);
     var second = new AnnotationConfigApplicationContext(SecondConfig.class)) {

    first.publishEvent(new OrderCreated("O-1"));
    // A listener bean registered only in second will not receive this event.
}
```

This is illustrative code; `FirstConfig` and `SecondConfig` are defined by the application. Do not create an auxiliary `new AnnotationConfigApplicationContext` inside a service to publish events and expect listeners in the main Boot application context to receive them.

**Diagnosis:** log `ApplicationContext.getId()` at both publisher and listener if possible to verify context instances and parent/child relationships. For a listener that does not run, compare bean registrations in the exact context rather than guessing from a different context.

## 8. Cause 5: `@TransactionalEventListener` Requires a Transaction and the Right Phase

This is the most common cause when code "publishes successfully yet the listener never logs anything".

```java
@TransactionalEventListener
public void afterCommit(OrderCreated event) {
    // Default phase = TransactionPhase.AFTER_COMMIT.
}
```

If the event is published **outside a transaction**, the transactional listener **does not run** by default. This behavior is intentional by design: without an active transaction, Spring cannot determine the commit/rollback phase of the event.

You can configure:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void afterCommitOrFallback(OrderCreated event) {
    // Can also handle when there is no transaction.
}
```

However, `fallbackExecution=true` **does not fabricate a fake commit**. It allows the listener to run when no transaction exists, so you must verify business semantics before enabling it. For logic like "send confirmation only if DB commits", keeping the default `false` is usually safer and ensures the publisher runs inside a proper transaction.

### 8.1. Listener Phase and Transaction Outcome

| Listener phase | When does it run? | Why might it not appear to run? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Callback before commit, transaction not yet completed | Transaction rolled back before commit |
| `AFTER_COMMIT` (**default**) | After successful commit | No transaction or transaction rolled back |
| `AFTER_ROLLBACK` | After transaction rollback | Transaction committed successfully instead |
| `AFTER_COMPLETION` | After commit or rollback | No transaction to register with or callback time not yet reached |

Distinguish between **event published** and **transaction completed**. A regular `@EventListener` can run immediately inside the transaction, whereas a transactional listener only registers a callback and waits for the appropriate phase.

### 8.2. `@Transactional` Self-Invocation Bug

```java
@Service
public class OrderService {

    public void createOrder() {
        this.saveAndPublish(); // Bypasses the proxy under the default mechanism.
    }

    @Transactional
    public void saveAndPublish() {
        publisher.publishEvent(new OrderCreated("O-1"));
    }
}
```

This is **illustrative code**, requiring an injected `publisher` and appropriate imports. In default proxy-based transaction mode, calling `this.saveAndPublish()` does not go through the proxy, so transaction advice may not be applied.

Result: the event is still published, regular listeners may receive it, but a `@TransactionalEventListener` with `fallbackExecution=false` **is skipped because there is no transaction**.

Fix: invoke the transactional method **through a Spring proxy from another bean**, or use `TransactionTemplate` to create a programmatic transaction. Do not add `@Transactional` onto the listener itself thinking it will make a previously published event transaction-bound; the transaction must exist **when the event is published**.

### 8.3. `@Async` Loses the Publisher Thread's Transaction Context

For imperative transactions managed by `PlatformTransactionManager`, the transaction context is typically held in a `ThreadLocal`. If you move `publishEvent()` onto an executor thread without a transaction, transaction-bound listeners will not see that transaction.

```text
Thread A:
  BEGIN T1
  submit async task
      |
      +-- Thread B:
              publishEvent(E)
              no thread-bound transaction T1
  COMMIT T1
```

This is an illustration, not a guarantee that every async call has no transaction. If the event must be bound to T1's commit, **publish the event inside T1** and use `@TransactionalEventListener(AFTER_COMMIT)`; if you want asynchronous post-commit processing, annotate the handler with `@Async` using proper configuration. Avoid passing mutable JPA entities or request objects to worker threads.

Spring reactive transactions use Reactor Context; since Spring 6.1, transaction-bound events support reactive flows but require propagating transaction context through the appropriate `TransactionalEventPublisher` mechanism. Do not use `ThreadLocal` as a diagnostic standard for reactive flows.

## 9. Cause 6: `@Async` Listener Has Not Run Yet, Was Rejected, or Errored in the Worker

When a handler uses:

```java
@Async("eventExecutor")
@EventListener
public void handle(OrderCreated event) {
    // Runs on an executor thread.
}
```

the publisher may return before the worker begins execution. Errors in a `void @Async` method **do not propagate back to the caller**. Additionally, if `@EnableAsync` is missing, the bean is not proxied, or the executor is misconfigured, thread/timing expectations will not match.

Cases to distinguish:

- **Not run yet:** task is still in the queue.
- **Failed to submit:** executor shut down / queue full / rejection policy triggered.
- **Ran but errored:** worker exception was handled by logging/`AsyncUncaughtExceptionHandler`.
- **Ran on another thread:** you are watching logs/debugger on the publisher thread or trace/MDC is missing.
- **Ran immediately:** `@Async` was not applied due to missing configuration or self-invocation, not necessarily "listener not called".
- **Missing context:** worker lacks `RequestContextHolder`, MDC, `SecurityContextHolder`, or JDBC transaction, causing the handler to fail when accessing resources.

Test with `CountDownLatch`/`CompletableFuture`/Awaitility with a timeout; avoid `Thread.sleep(100)` and then claiming the listener was skipped. Check executor metrics, task rejections, and uncaught exception handlers. If using a custom `applicationEventMulticaster`, inspect its configured `TaskExecutor` and `ErrorHandler`.

### 9.1. `@Async` Self-Invocation

```java
@Component
class AsyncService {

    void start() {
        this.process(); // Does not go through the Spring async proxy.
    }

    @Async
    public void process() {
        // May execute on the thread calling start().
    }
}
```

This is illustrative code; the cause is proxy bypass. A standard `@Async @EventListener` invoked by the event infrastructure on a Spring-managed bean goes through the appropriate async proxy; however, calling an async method from the same instance can behave completely differently. Do not use `this.method()` as a test of asynchronous behavior.

## 10. Runnable Java 17+ Example: Distinguishing Standard Listener, Condition, and Transaction Phase

The following example uses **Spring Framework 6.2.12**, `spring-jdbc`, H2 in-memory, Gradle, and JDK 17+. No Spring Boot or web server is required. This is a console program that **can run standalone** once dependencies are downloaded.

Purpose:

1. Publish `TicketEvent("N-1", "READY")` **outside a transaction**.
2. Publish `TicketEvent("C-1", "READY")` inside a **committed** transaction.
3. Publish `TicketEvent("R-1", "REJECTED")` inside a **rollback-only** transaction.
4. Count four callback groups: standard `@EventListener`, listener with SpEL condition, `AFTER_COMMIT` listener, and `AFTER_ROLLBACK` listener.
5. Avoid relying on ordering between the two standard `@EventListener` methods; each time only compare **total counters after the step finishes**.

### 10.1. Structure

```text
spring-listener-diagnostics/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ListenerNotCalledDemo.java
    └── test/java/demo/EventDiagnosticsTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-listener-diagnostics'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.ListenerNotCalledDemo'
}

test {
    useJUnitPlatform()
}
```

`DriverManagerDataSource` is only suitable for short demos; production should use a connection pool configured with limits and timeouts. In this demo, H2 provides a real connection so `DataSourceTransactionManager` can manage transactions; no tables need to be created because this example only observes phases and does not manipulate DB data.

### 10.2. `src/main/java/demo/ListenerNotCalledDemo.java`

```java
package demo;

import javax.sql.DataSource;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class ListenerNotCalledDemo {

    public record TicketEvent(String id, String state) {}

    public static class IssuerService {
        private final ApplicationEventPublisher publisher;

        public IssuerService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void issue(String id, String state) {
            publisher.publishEvent(new TicketEvent(id, state));
        }
    }

    public static class ListenerProbe {
        private final AtomicInteger any = new AtomicInteger();
        private final AtomicInteger ready = new AtomicInteger();
        private final AtomicInteger afterCommit = new AtomicInteger();
        private final AtomicInteger afterRollback = new AtomicInteger();

        @EventListener
        public void anyTicket(TicketEvent event) {
            any.incrementAndGet();
        }

        @EventListener(condition = "#a0.state() == 'READY'")
        public void readyTicket(TicketEvent event) {
            ready.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void committedTicket(TicketEvent event) {
            afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBackTicket(TicketEvent event) {
            afterRollback.incrementAndGet();
        }

        public int any() { return any.get(); }
        public int ready() { return ready.get(); }
        public int committed() { return afterCommit.get(); }
        public int rolledBack() { return afterRollback.get(); }

        public String report() {
            return "any=" + any() + ", ready=" + ready()
                    + ", commit=" + committed()
                    + ", rollback=" + rolledBack();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:listener_diag;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        IssuerService issuerService(ApplicationEventPublisher publisher) {
            return new IssuerService(publisher);
        }

        @Bean
        ListenerProbe listenerProbe() {
            return new ListenerProbe();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            IssuerService issuer = context.getBean(IssuerService.class);
            ListenerProbe probe = context.getBean(ListenerProbe.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);

            // 1. Without a transaction: regular listeners still receive.
            issuer.issue("N-1", "READY");
            System.out.println("no tx: " + probe.report());

            // 2. Transaction commits: AFTER_COMMIT is invoked.
            tx.executeWithoutResult(status ->
                    issuer.issue("C-1", "READY"));
            System.out.println("commit: " + probe.report());

            // 3. Transaction rolls back: AFTER_ROLLBACK is invoked.
            tx.executeWithoutResult(status -> {
                issuer.issue("R-1", "REJECTED");
                status.setRollbackOnly();
            });
            System.out.println("rollback: " + probe.report());
        }
    }
}
```

### 10.3. Run Command and Expected stdout

```bash
gradle -q run
```

The lines **printed by the program itself via `System.out.println`**:

```text
no tx: any=1, ready=1, commit=0, rollback=0
commit: any=2, ready=2, commit=1, rollback=0
rollback: any=3, ready=2, commit=1, rollback=1
```

This is the output of the code and configuration shown. Gradle/logging may print additional lines depending on the environment.

### 10.4. Explaining Each Case

**Case N-1 (outside a transaction):**

- `IssuerService.issue(...)` calls the context's real publisher and emits `TicketEvent`.
- The standard `@EventListener` receives the event; counter `any` increments from 0 to 1.
- `state="READY"` satisfies `condition`, so counter `ready` increments to 1.
- `@TransactionalEventListener` defaults to `fallbackExecution=false`; with no transaction to register against, `commit` and `rollback` remain 0.
- This is **correct behavior**, not a broken listener.

**Case C-1 (transaction commit):**

- `TransactionTemplate.executeWithoutResult(...)` opens a JDBC transaction managed by `DataSourceTransactionManager`.
- The event is published **inside the callback while the transaction is active**. Both standard listeners run immediately, bringing `any=2`, `ready=2`.
- The `AFTER_COMMIT` listener is registered with the transaction; only after the callback completes and the transaction commits does it run, bringing `commit=1`.
- The `AFTER_ROLLBACK` listener does not run because the transaction committed.

**Case R-1 (transaction rollback):**

- In a new transaction, the publisher emits `TicketEvent("R-1", "REJECTED")`.
- `any` increments to 3, but the SpEL condition does not match so `ready` stays at 2.
- `status.setRollbackOnly()` causes the transaction to roll back even without throwing an exception.
- The `AFTER_COMMIT` listener does not run, while `AFTER_ROLLBACK` runs and increments counter `rollback=1`.

The example does **not** use `@Async` in order to keep stdout deterministic and isolate event type, condition, and phase issues. With async listeners, tests must wait for completion rather than asserting counters immediately after publishing. If results differ from expectations, check dependency configuration, Spring bean registration, and versions before assuming a framework bug.

## 11. Testing Whether an Event Was Published in `ApplicationContext`

Spring TestContext Framework supports `@RecordApplicationEvents` and `ApplicationEvents` to distinguish:

- event **was published** but the transactional listener did not run;
- event **was published** but was filtered out by `condition`;
- event **was never published**.

`@RecordApplicationEvents` must be placed on the test class; `ApplicationEvents` can be injected into test methods when using `@SpringJUnitConfig`.

### 11.1. `src/test/java/demo/EventDiagnosticsTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ListenerNotCalledDemo.AppConfig.class)
@RecordApplicationEvents
class EventDiagnosticsTest {

    @Autowired
    ListenerNotCalledDemo.IssuerService issuer;

    @Autowired
    ListenerNotCalledDemo.ListenerProbe probe;

    @Autowired
    TransactionTemplate tx;

    @Test
    void publishedEventsAreNotTheSameAsPhaseCallbacks(
            ApplicationEvents events) {

        issuer.issue("N-1", "READY");
        assertEquals(1, probe.any());
        assertEquals(1, probe.ready());
        assertEquals(0, probe.committed());
        assertEquals(0, probe.rolledBack());

        tx.executeWithoutResult(status ->
                issuer.issue("C-1", "READY"));
        assertEquals(1, probe.committed());

        tx.executeWithoutResult(status -> {
            issuer.issue("R-1", "REJECTED");
            status.setRollbackOnly();
        });

        // All three events were published; phase listeners have different counts.
        assertEquals(3L,
                events.stream(ListenerNotCalledDemo.TicketEvent.class)
                        .count());

        assertEquals(3, probe.any());
        assertEquals(2, probe.ready());
        assertEquals(1, probe.committed());
        assertEquals(1, probe.rolledBack());
    }
}
```

Run:

```bash
gradle -q test
```

This test has **one `@Test` method** and expects JUnit Platform to complete successfully. Terminal output may vary by Gradle setup, so do not treat a fixed stdout line as a test contract.

**Why is this test diagnostically valuable?**

`ApplicationEvents.stream(TicketEvent.class).count() == 3` proves that **three events of type `TicketEvent` were recorded by Spring Test as published**. Within the same test:

- The standard listener received all three.
- The listener with a condition received only the two `READY` events.
- The post-commit listener received only the event inside the committed transaction.
- The post-rollback listener received only the event inside the rolled-back transaction.

Thus, **"not called" must always be tied to a specific listener kind and condition**. An event may have been published successfully yet skipped by the listener's own rules.

**Test scope:** `ApplicationEvents` is a Spring Test recorder, not a production event store. Do not pass this object to foreign threads or reuse it across multiple test methods; Spring manages it per test lifecycle. If a test uses custom `@TestExecutionListeners` replacing defaults, ensure `ApplicationEventsTestExecutionListener` is retained/registered.

## 12. Spring Boot: Too-Early Events Occur Before Listener Beans Exist

Another case is using a listener bean to listen for `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` **from Spring Boot**.

These events fire **before `ApplicationContext` can create `@Component` beans**, so:

```java
@Component
public class TooLateStartingListener {

    @EventListener
    public void handle(ApplicationStartingEvent event) {
        // Cannot receive an event published before the bean was created.
    }
}
```

This is a **counterexample**. `ApplicationStartingEvent` belongs to `org.springframework.boot.context.event`, not Spring Framework's `ContextStartedEvent`.

If you need a listener for early Spring Boot events, register it before `SpringApplication.run(...)`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyStartingListener());
app.run(args);
```

This is illustrative code; `MyApplication` and `MyStartingListener` are defined by the application. Listeners can also be registered in `META-INF/spring.factories` under the `org.springframework.context.ApplicationListener` key when developing libraries/bootstrapping. Distinguish this mechanism from Spring Boot 3 auto-configuration which uses `AutoConfiguration.imports`.

**An easily confused pair of names:**

- `ApplicationStartedEvent` (**Spring Boot**) fires after the context refreshes, before runners.
- `ContextStartedEvent` (**Spring Framework**) fires when `ConfigurableApplicationContext.start()` is explicitly called; starting a typical Boot application does not mean it occurs automatically.

If a listener listens for `ContextStartedEvent` while the application only calls `refresh()` and never calls `start()`, the handler not running is also expected behavior.

## 13. Checking Logs, Metrics, and Breakpoints Properly

### 13.1. Logging at the Publisher with Minimal Data

```java
log.debug("publish {} id={}",
        event.getClass().getName(), event.orderId());
publisher.publishEvent(event);
```

This is **illustrative code**, assuming the event has `orderId()` and a logging dependency. Logging the full class name helps detect package/type mistakes. Do not log entire entities, requests, tokens, or sensitive payloads.

Consider adding an `eventId`/correlation ID to the event DTO, especially for async processing. This lets you correlate publisher and listener logs without relying on `ThreadLocal` MDC auto-propagation.

### 13.2. Placing Breakpoints in the Right Places

In a local test/application:

1. Breakpoint before the `publishEvent` call.
2. Breakpoint inside a minimal `@EventListener` handler without a condition.
3. If step 1 hits but step 2 does not, check registration/type/context.
4. If the standard handler runs but the transactional handler does not, check transaction synchronization and phase.
5. If the listener is `@Async`, use the debugger to inspect the **worker thread** and verify the executor accepted the task.

There is no need to step into `SimpleApplicationEventMulticaster` internals as the very first step in every scenario; small tests usually isolate the fault faster. If it remains unclear, set breakpoints in the multicaster's `multicastEvent(...)` and listener adapter, or enable selective Spring logging.

With Spring Boot, you can configure logging as needed for diagnostics:

```properties
logging.level.org.springframework.context.event=DEBUG
logging.level.org.springframework.transaction=DEBUG
```

This is **illustrative configuration**, not a guarantee that the framework will log every event and every listener invocation. Debug loggers are supporting evidence; **they do not replace tests that observe events/counters directly**. Avoid leaving system-wide debug logging enabled long-term under high traffic.

### 13.3. Checking a Custom Multicaster

A bean with the standard name `applicationEventMulticaster` can replace the default multicaster:

```java
@Bean
ApplicationEventMulticaster applicationEventMulticaster(
        TaskExecutor executor) {

    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(executor);
    return m;
}
```

This is **illustrative code**, requiring imports for `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, and `TaskExecutor`. With a custom executor, some listeners may run asynchronously and ordering/exception reporting changes. Depending on version/listener type, not all listeners permit async execution via the multicaster; in particular, transaction-bound listeners must be invoked in the proper transaction context to register callbacks.

When suspecting an issue, compare against a minimal context using the default multicaster and a conditionless listener like the main example. Do not switch all listeners to async just to "fix" missing logs.

## 14. Symptom-Based Diagnostic Table

| Symptom | Primary possibility | How to prove and fix |
| --- | --- | --- |
| `publishEvent` not observed | Service branch did not reach publish call; exception before call | Breakpoint/test business branch and event contract |
| `@Component` listener does not receive event | Bean not in component scan or not in context | Check bean registration, `@ComponentScan`/`@Import`/`@Bean` |
| Bean exists but `@EventListener` does not receive | `@Lazy` bean, missing annotation infrastructure, or invalid method signature | Try a minimal eager bean, inspect startup logs |
| `ApplicationListener<T>` does not run | Wrong generic event type or listener not registered | Compare runtime type and bean registrations |
| Listener expects `OrderPaid` but publisher emits `OrderCreated` | Different event class | Check FQCN and parameter type |
| Generic handler only receives some subtypes | Type erasure / unresolved generic | Concrete subtype or `ResolvableTypeProvider` |
| Listener with `condition` does not run | Expression evaluates false or wrong argument | Test without condition, try `#a0` and valid data |
| Published from context A, listener in B | Independent contexts or unsuitable parent/child direction | Compare context IDs, configure hierarchy |
| `AFTER_COMMIT` does not run outside transaction | Default `fallbackExecution=false` | Publish inside proper transaction or consider fallback per business rules |
| `AFTER_COMMIT` does not run on rollback | Commit did not succeed | This is expected semantics; use `AFTER_ROLLBACK` if needed |
| `AFTER_ROLLBACK` does not run on commit | No rollback occurred | This is expected semantics, not a registration bug |
| `@Transactional` on method yet event not transaction-bound | Self-invocation or transaction proxy inactive | Call via Spring bean proxy or `TransactionTemplate` |
| Async listener result not visible immediately | Task not finished or queue busy | Wait on latch/future with timeout and check executor |
| `@Async` listener error not propagated to request thread | Worker exception handled separately | `AsyncUncaughtExceptionHandler` and metrics |
| `@RequestScope`/MDC missing in worker | `ThreadLocal` does not auto-propagate | Put needed data in immutable event, configure context propagation where appropriate |
| Spring Boot early startup event does not reach `@Component` | Listener registered too late | `SpringApplication.addListeners` or `spring.factories` |
| Listening for `ContextStartedEvent` when only refreshing context | `ConfigurableApplicationContext.start()` not called | Listen for `ContextRefreshedEvent` or call start when lifecycle requires it |
| `@Transactional` test does not receive `AFTER_COMMIT` | Test rolls back by default or assertion runs before commit | `TestTransaction.flagForCommit(); end()` or test without wrapping transaction |
| Event published but side effect missing | Listener is async, errored, or commit phase not reached | Test consumer/completion separately, do not infer from publisher |
| No events after JVM restart | Spring Application Events are not durably persisted | Transactional outbox, broker, or persisted queue |

## 15. Test Traps That Make You Think Listeners Are Lost

### 15.1. Test Does Not Build Enough of the Spring Context

If a unit test simply does `new OrderService(mockPublisher)`, you are testing that business code calls the publisher, **without Spring's listener infrastructure**. To verify that real listeners are invoked, use Spring Test `@SpringJUnitConfig` or initialize a proper `AnnotationConfigApplicationContext`.

### 15.2. Default Test Transaction Rollback

A Spring Test method annotated with `@Transactional` is typically rolled back when the test finishes. If the test publishes an event and asserts `AFTER_COMMIT` **before the transaction ends**, the callback has not run yet. If the test ends with a rollback, the `AFTER_COMMIT` callback will never be called.

For tests with transactions managed by Spring Test:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Only now check the AFTER_COMMIT listener.
```

This is **illustrative code**, requiring `spring-test` and an appropriate transaction manager. If the test method itself does not need a transaction, letting the real transactional service commit on its own and asserting after the service call is simpler.

### 15.3. Event Filtered Out in Test Environment Unlike Production

A test uses a configuration that imports only `OrderService` and forgets to import the listener, whereas production has a different component scan. Or `@MockBean`/other mocking replaces the listener bean. Always verify **the test's actual context** and event types rather than extrapolating from the production application class.

### 15.4. Recorder Sees the Publish, Does Not Guarantee Listener Success

`@RecordApplicationEvents` records published events. It does not force all async listeners to complete and does not alter transaction phases. Tests should use a self-managed observer/counter/latch to prove a specific callback occurred.

If events can originate from another thread or an auxiliary context, do not assume the recorder observes every path outside the TestContext thread. Design tests around proper context and thread boundaries.

## 16. How to Fix After Finding the Root Cause

Do not enable `fallbackExecution=true` or remove `@Async` just to "make the test green" if doing so breaks business semantics.

Some sound decisions:

- **Missing bean registration:** fix component scan, `@Bean`, `@Import`, and remove inappropriate lazy initialization.
- **Type mismatch:** fix the event type and payload contract rather than forcing casts.
- **Wrong SpEL filter:** fix the expression and add negative-path tests.
- **Wrong context:** inject the right `ApplicationEventPublisher` from the context owning the flow, or intentionally design a bridge between contexts.
- **Missing transaction:** move `publishEvent` into a transactional service or use `TransactionTemplate`; do not use fallback as a simulated commit.
- **Transaction rollback:** if business logic should only run on commit, not receiving the event is right; if failure handling is needed, use the rollback phase.
- **Async/exceptions:** add executor diagnostics, retry/error handling, latches in tests, and correlation IDs in events.
- **Startup events:** register early listeners before the context creates beans.
- **Crash durability:** use an outbox/persistent queue instead of expecting Spring to replay automatically.

## 17. Final Checklist

Before concluding that Spring "is not calling the listener", confirm:

- [ ] Is the event created and `publishEvent` actually called?
- [ ] Do the runtime event class and payload match the handler?
- [ ] Does the listener belong to a Spring-managed bean and the appropriate context?
- [ ] Was the bean accidentally marked `@Lazy` or placed outside component scan?
- [ ] Has the `@EventListener` annotation infrastructure been registered?
- [ ] Does the SpEL `condition` actually return `true`?
- [ ] Is there a parent/child context or an unintended auxiliary context?
- [ ] If using `@TransactionalEventListener`, is a transaction active at publish time?
- [ ] Does the listener phase match commit/rollback, and has the callback point been reached?
- [ ] If async, did the test wait for the worker and check error logs on the right thread?
- [ ] Is a Spring Boot early event being published before beans are created?
- [ ] Does the test distinguish **event published** from **listener processed**?

**Conclusion:** The "listener not called" symptom must be broken down into **not published**, **not registered**, **not matched**, or **not yet / not eligible to process**. A `@RecordApplicationEvents` test combined with a minimal standard listener, a `condition` check, and transaction phase checks like the example above will quickly pinpoint the fault boundary. Once the root cause is identified, fix the specific registration/type/context/transaction/async issue rather than overhauling the entire event architecture.

## Official Documentation

- [Spring Framework 6.2 — ApplicationContext Events: listener registration, `@Lazy`, SpEL, generics, and async](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events, `fallbackExecution`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Testing Application Events and `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)