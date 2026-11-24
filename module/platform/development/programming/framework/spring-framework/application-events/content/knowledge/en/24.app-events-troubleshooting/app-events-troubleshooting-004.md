# Invalid Listener Methods in Spring Application Events: Diagnosis and Resolution

## 1. Identifying the Problem

Spring Framework allows writing an application event handling method with `@EventListener`. Normally, placing the annotation on a Spring bean method is enough for Spring to discover it, determine the event type, and register it internally as an `ApplicationListener`.

However, not **every method signature** is a valid event listener. Some configurations cause `ApplicationContext` **initialization to fail**; others allow the application to start, yet the listener **receives no events**, or throws errors only **when an event is actually published**.

Two common signature mistakes:

~~~java
// WRONG: no parameter, and no classes attribute specifying the event type.
@EventListener
public void onSomething() {}

// WRONG: listener declares two event parameters.
@EventListener
public void onOrder(OrderCreated created, PaymentCaptured captured) {}
~~~

Spring does not interpret the second method as a joiner of two events. An event listener is triggered by **one event at a time**, not as an endpoint auto-populating multiple business parameters.

This lesson belongs to the **Troubleshooting** topic of Spring Framework Application Events. The goal is to know how to read errors, classify root causes, fix signatures, inspect Spring beans/proxies, and verify with a standalone Java 17+ program.

After this lesson, you will be able to:

1. Identify valid and invalid `@EventListener` signatures.
2. Distinguish **startup/registration** errors, **runtime/invocation** errors, and **listener-not-called** cases.
3. Understand the roles of `EventListenerMethodProcessor` and `ApplicationListenerMethodAdapter`.
4. Properly use `classes`, `condition`, payload types, return values, `@Async`, and `@TransactionalEventListener`.
5. Diagnose proxy/JDK interface issues, generic events, component scanning, annotation processing, and transactions.
6. Run a Spring Framework 6.2.x demo containing both valid listeners and two cases rejected by Spring at startup.

## 2. How Spring Discovers and Registers Listeners

When using Spring Java configuration or annotation configuration, `@EventListener` processing is typically registered automatically.

~~~text
AnnotationConfigApplicationContext.refresh()
      |
      +-- read bean definitions
      +-- create/configure beans
      +-- EventListenerMethodProcessor
              |
              +-- find methods with @EventListener
              +-- read classes / event parameter
              +-- determine invocable method via bean/proxy
              +-- create ApplicationListenerMethodAdapter
              +-- register into ApplicationEventMulticaster
      |
      +-- application publishEvent(event)
              |
              +-- multicaster selects listeners matching event type
              +-- adapter evaluates condition
              +-- adapter invokes listener method
~~~

Key components:

- **`EventListenerMethodProcessor`**: scans beans for `@EventListener` methods and registers listener adapters. If a method cannot be registered, context refresh can fail with `BeanInitializationException`/nested cause.
- **`ApplicationListenerMethodAdapter`**: holds method metadata, determines supported event types, prepares arguments, evaluates SpEL conditions, and invokes the corresponding method.
- **`ApplicationEventMulticaster`**: distributes events to listeners. With the default `SimpleApplicationEventMulticaster`, regular listeners are invoked synchronously.
- **`ApplicationEventPublisher`**: API for applications to emit events via `publishEvent(...)`; does not fix listener signatures or inject multiple parameters.

A bean **not managed by Spring** or a context **lacking event listener annotation processing** can cause a method to go undetected; this differs from when the processor detects the method and reports an **invalid signature**.

## 3. `@EventListener` Signature Rules

### 3.1. One Event Type, One Parameter: The Simplest Form

~~~java
// VALID: event type inferred from the first and only parameter.
@EventListener
public void onOrderCreated(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

In this example, `OrderCreated` can be an `ApplicationEvent` subclass or a Java record/POJO published via `ApplicationEventPublisher.publishEvent(Object)`.

Spring infers the event type from the parameter. You **do not need** to add `classes = OrderCreated.class` when the method already has one parameter of a concrete type.

### 3.2. No Parameters, Explicitly Specifying `classes`

~~~java
// VALID: event data not needed, only cares that the event occurred.
@EventListener(classes = OrderCreated.class)
public void onAnyOrderCreated() {
    metrics.increment("order-created");
}
~~~

Because the method has no parameter from which to infer the event type, the annotation must declare the event type via `classes` (or its alias `value`).

You can register multiple event types on **the same parameterless method**:

~~~java
// VALID in Spring Framework 6.2 samples.
@EventListener(classes = {OrderCreated.class, PaymentCaptured.class})
public void onBusinessActivity() {
    metrics.increment("business-activity");
}
~~~

Consider carefully: a parameterless method **does not know which specific event** triggered it. If behavior needs to distinguish payloads, write two methods or use a suitable event abstraction rather than trying to make Spring pass two events into a single call.

### 3.3. Two Event Parameters: Invalid

~~~java
// WRONG: Spring @EventListener is not an MVC method argument resolver.
@EventListener
public void onBusinessEvent(OrderCreated order, PaymentCaptured payment) {
    // ...
}
~~~

For regular Java methods, Spring Framework 6.2 enforces **at most one parameter** to define an event listener. When the processor handles this method, the exception cause typically contains:

~~~text
Maximum one parameter is allowed for event listener method:
~~~

To handle two separate events, create two listeners:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Handle event A.
}

@EventListener
public void onPaymentCaptured(PaymentCaptured event) {
    // Handle event B.
}
~~~

If you genuinely need combined data from A and B, use a **workflow/state machine**, repository, or aggregate accumulating state before emitting a composite event. Do not declare a two-parameter listener expecting Spring to wait for both events to arrive.

### 3.4. No Parameters and No `classes`: Invalid

~~~java
// WRONG: Spring has no information to know which event type the listener handles.
@EventListener
public void observe() {}
~~~

When the processor encounters this method, the error cause typically contains:

~~~text
Event parameter is mandatory for event listener method:
~~~

Fix in one of two ways:

~~~java
// Option 1: declare the event type with one parameter.
@EventListener
public void observe(OrderCreated event) {}

// Option 2: specify the event type on the annotation.
@EventListener(classes = OrderCreated.class)
public void observe() {}
~~~

**Version note:** examples and rules here are scoped to Spring Framework 6.2.x. Javadoc of newer Spring lines may expand or adjust how `classes` or Kotlin cases are interpreted; do not cite descriptions from other versions to bypass signature checks in a running application.

### 3.5. Signature Comparison Table

| Signature | Status | Reason |
| --- | --- | --- |
| `@EventListener void on(OrderCreated e)` | Valid | Single event parameter |
| `@EventListener(classes=OrderCreated.class) void on()` | Valid | Explicitly declared event type |
| `@EventListener(classes={A.class,B.class}) void on()` | Valid | Multiple event types, no payload parameter required |
| `@EventListener void on()` | **Invalid** | Cannot infer event type and `classes` is absent |
| `@EventListener void on(A a, B b)` | **Invalid** | More than one parameter |
| `@EventListener String on(A a)` | Valid signature | **Non-null** return value is published by Spring as another event |
| `@Async @EventListener void on(A a)` | Valid when async is configured | Runs on executor; no return value for Spring to republish |

Do not assume every configuration marked "valid" fits business needs. A method with a return value may inadvertently emit extra events, while an async listener has different semantics from a synchronous callback.

## 4. Startup Errors Differ from Errors That Only Occur on Publish

### Errors During Registration

Typically, Spring detects invalid signatures during `ApplicationContext.refresh()`. A stack trace may look like:

~~~text
BeanInitializationException:
  Failed to process @EventListener annotation on bean with name '...'
Caused by: IllegalStateException:
  Maximum one parameter is allowed for event listener method: ...
~~~

Exact messages may vary across Spring versions, proxy configurations, or actual methods; **read the deepest root cause (`Caused by`)**, not only the outermost exception line.

If the error occurs during refresh, you cannot blame the event publisher or event payload yet: **listener registration** itself did not complete.

### Errors When the Listener Is Actually Invoked

Some methods register successfully yet fail when an event is published, for example:

- `condition` is a malformed SpEL expression or references a nonexistent field.
- The method runs and its logic throws a `RuntimeException`.
- The bean is proxied in a way that prevents invoking the listener method through the existing proxy.
- The return value is a new event causing an event-publishing loop.
- The listener uses `@Async`, so exceptions do not return to the publisher thread; check the executor's error-handling mechanism.

Pinpoint the exact **failure time**: context refresh vs. `publishEvent`/callback. Those two points lead to completely different fixes.

### No Exception, Yet the Listener Does Not Run

Common causes:

- The class is not registered as a **Spring bean**.
- The method was called on a manually `new`'d object rather than through a Spring bean.
- Missing annotation processing in legacy/XML configuration.
- Event type does not match what the listener expects.
- Valid `condition` evaluates to `false`.
- `@TransactionalEventListener` is waiting for commit, or skips events published outside a transaction.
- Event is published in another `ApplicationContext`, or at an unsuitable lifecycle moment.
- Async listener is still running or failed on the executor.

Do not rush to alter the method signature when the context starts cleanly with no exceptions. Prove bean registration, event type, and conditions first.

## 5. Runnable Example with Java 17+ and Spring Framework 6.2.12

The demo's goal is to verify **both valid configuration and two invalid signature cases**. The program creates three separate `AnnotationConfigApplicationContext` instances:

1. A context with a valid listener: one method receiving `Ping`, one parameterless method receiving both `Ping` and `Pong`.
2. A context with a parameterless `@EventListener` method declaring no `classes` — must be rejected on `refresh()`.
3. A context with a two-parameter method — must be rejected on `refresh()`.

To avoid depending on the entire Spring-generated stack trace, the program **checks the exception cause message string**, then prints three deterministic summary lines. If Spring unexpectedly accepts an invalid configuration or throws a different cause, the program fails instead of printing fake results.

Directory structure:

~~~text
invalid-event-listener-demo/
├── pom.xml
└── src/main/java/demo/InvalidEventListenerDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>invalid-event-listener-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/InvalidEventListenerDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class InvalidEventListenerDemo {

    public record Ping(String id) {}
    public record Pong(String id) {}

    public static class GoodListener {
        private int typed;
        private int multi;

        @EventListener
        public void onPing(Ping event) {
            typed++;
        }

        @EventListener(classes = {Ping.class, Pong.class})
        public void onPingOrPong() {
            multi++;
        }

        public String summary() {
            return "typed=" + typed + ", multi=" + multi;
        }
    }

    // Wrong: no parameter and no event classes specified.
    public static class NoEventTypeListener {
        @EventListener
        public void onAnything() {
        }
    }

    // Wrong: two parameters, a Spring listener accepts at most one event at a time.
    public static class TwoArgumentsListener {
        @EventListener
        public void onBoth(Ping ping, Pong pong) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class GoodConfig {
        @Bean
        public GoodListener goodListener() {
            return new GoodListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class NoEventTypeConfig {
        @Bean
        public NoEventTypeListener badListener() {
            return new NoEventTypeListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoArgumentsConfig {
        @Bean
        public TwoArgumentsListener badListener() {
            return new TwoArgumentsListener();
        }
    }

    // Accept an invalid config failure only when the cause matches the expected message.
    private static boolean hasCauseMessage(
            Throwable exception, String expected) {
        for (Throwable t = exception; t != null; t = t.getCause()) {
            if (t.getMessage() != null
                    && t.getMessage().contains(expected)) {
                return true;
            }
        }
        return false;
    }

    private static void assertRejected(
            String label, Class<?> configuration, String expectedCause) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.register(configuration);
            context.refresh();

            // If reached here, the invalid config was not rejected as expected.
            throw new AssertionError(
                    "Expected context startup to fail: " + label);
        } catch (RuntimeException exception) {
            if (!hasCauseMessage(exception, expectedCause)) {
                throw exception;
            }
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(GoodConfig.class)) {
            GoodListener listener = context.getBean(GoodListener.class);

            context.publishEvent(new Ping("ping-1"));
            context.publishEvent(new Pong("pong-1"));

            String result = listener.summary();
            if (!"typed=1, multi=2".equals(result)) {
                throw new AssertionError(
                        "Unexpected event listener result: " + result);
            }
            System.out.println("good=" + result);
        }

        assertRejected(
                "zero-arg-no-classes",
                NoEventTypeConfig.class,
                "Event parameter is mandatory for event listener method");

        assertRejected(
                "two-event-args",
                TwoArgumentsConfig.class,
                "Maximum one parameter is allowed for event listener method");
    }
}
~~~

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InvalidEventListenerDemo
~~~

Three lines printed by the program itself when all checks pass:

~~~text
good=typed=1, multi=2
zero-arg-no-classes=REJECTED
two-event-args=REJECTED
~~~

Maven and Spring may print additional logs/error metadata (especially when a context intentionally fails startup). **The three lines above are the stdout printed by the example code itself**, not a guarantee that the terminal shows only three lines.

### 5.3. Explaining Why the Example Works

- `GoodConfig` creates a single `GoodListener` Spring bean. `onPing(Ping)` receives only `Ping` events, while `onPingOrPong()` uses `classes={Ping.class,Pong.class}` and thus receives both types.
- `ApplicationContext.publishEvent(new Ping(...))` and `publishEvent(new Pong(...))` send POJOs/records; Spring may wrap them in `PayloadApplicationEvent`, and the adapter selects the right listener by payload type.
- With default synchronous dispatch, after two publishes the counters are deterministic: `typed=1`, `multi=2`. The example does not depend on ordering between the two listener methods because it only checks totals.
- `NoEventTypeConfig` registers a parameterless `@EventListener` method with no `classes`. During processing, Spring cannot determine the event type and rejects it.
- `TwoArgumentsConfig` has a two-parameter method; the adapter enforces the parameter limit and rejects it.
- `assertRejected` does not treat **every startup failure** as success. It walks the cause chain requiring the expected message substring. If the context fails for any other reason, the exception is rethrown.
- Each context is closed via `try-with-resources`; a failing context does not alter the configuration of the valid context, and the example requires no database or web server.

**QA limitation:** the example is designed against Spring 6.2.12 APIs and verified for signatures/exception messages against Spring docs/source. Output is expected from the code, not measured on a machine without actually running Maven.

## 6. `classes` / `value`: When to Use and When Not To

`@EventListener` provides `classes` and its alias `value`:

~~~java
// Two equivalent ways to specify a single event class.
@EventListener(classes = OrderCreated.class)
public void observeCreated() {}

@EventListener(OrderCreated.class)
public void observeCreatedAnotherWay() {}
~~~

If the method already has one `OrderCreated event` parameter, there is no need to repeat that type in `classes`. Adding an incompatible `classes` set alongside a typed parameter or listing multiple event classes on a method needing a payload can lead to unexpected dispatch behavior.

Safe guidelines for Spring 6.2:

- Need to **receive the payload**: one method with **one parameter of the concrete event type**.
- Need to handle an event **without needing the payload**: parameterless method, `classes=SomeEvent.class`.
- Need one callback reacting to **multiple event types** without distinguishing them: parameterless method, `classes={A.class,B.class}`.
- Need different reactions to A vs. B: **two separate listener methods** or an appropriate common data abstraction.

Do not use `@EventListener` like `@RequestMapping` or `@MessageMapping` with arbitrary annotated parameters injected. Event methods follow Spring Context's own rules, not web controller argument resolvers.

## 7. SpEL `condition`: Syntax Errors Are Not Signature Errors

A method with a valid signature may still not run due to a condition:

~~~java
// Illustration: OrderCreated has an amount() method.
@EventListener(condition = "#a0.amount() > 100")
public void onLargeOrder(OrderCreated event) {
    // Runs only when amount > 100.
}
~~~

Variables supported in conditions include:

- `#root.event`: Spring's `ApplicationEvent`-level event; for POJO payloads, this may be the wrapper.
- `#root.args` or `args`: list of method arguments.
- `#a0`, `#p0`, `args[0]`: first argument.
- Parameter name, e.g. `#event`, if parameter names are retained in bytecode and compilation settings support it.

If using `#event.amount()` when parameter names are not retained, evaluation can fail; `#a0.amount()` is usually more reliable for single-parameter methods.

**Diagnostic distinction:**

- `condition` returns `false`: the listener is **validly skipped**, with no error.
- `condition` references a nonexistent property or has invalid expression syntax: may throw a SpEL exception **when the event is evaluated**.
- Method has no parameter and no `classes`: rejected at **listener registration** before any event exists.

Choose fixes matching the error group; do not change parameter counts when the real issue is SpEL.

## 8. POJO Events, Wrappers, and Type Mismatch

Since Spring 4.2, applications can publish any object:

~~~java
// Example: Java 17 record.
public record InvoiceIssued(long invoiceId) {}

publisher.publishEvent(new InvoiceIssued(17L));
~~~

Spring can represent it via `PayloadApplicationEvent`, and the adapter extracts the payload matching the listener parameter:

~~~java
@EventListener
public void onInvoiceIssued(InvoiceIssued event) {
    // Receives the record without manual casting from a wrapper.
}
~~~

Common confusions:

- Listener accepts `OrderCreated` while the publisher actually sends `InvoiceIssued`, so the method is not invoked.
- Using `ApplicationEvent` as the parameter when wanting a specific payload; the listener can end up receiving many framework lifecycle events, making it overly broad.
- Listener accepts `PayloadApplicationEvent<InvoiceIssued>` expecting all generic setups to resolve just like a direct record parameter; test with the real payload type and generic metadata.
- Event is published by another context or child/parent context, so only a subset of listeners see it.

When debugging, print **the actual type of the published event**, the listener parameter type, the source context, and whether a payload wrapper is present. Do not force-cast `PayloadApplicationEvent` directly into the original record.

## 9. Return Value: Valid Signature That Can Cause Logic Bugs

A listener can return a non-`void` object:

~~~java
// Illustration: emit a downstream event when OrderCreated arrives.
@EventListener
public OrderIndexed onCreated(OrderCreated event) {
    return new OrderIndexed(event.orderId());
}
~~~

Spring publishes any non-null return value as **a new event**. If an array/collection is returned, individual elements may be published separately. This is valid in signature yet easily causes:

- Unbounded A -> B -> A cycles.
- A listener accidentally returning its own input event, causing recursion.
- The new event being processed in the same transaction/thread under synchronous multicasting, causing unexpected errors and latency.
- Mistaking the return value as a return to the caller of `publishEvent` (the publisher still receives `void`, not the callback's return value).

If you do not intend to emit follow-up events, declare the return type as **`void`** and do not return data merely for logging/debugging.

### `@Async @EventListener`: Returning Events Is Not a Valid Publish Mechanism

By Spring's contract, asynchronous listeners **do not support publishing subsequent events via return values**. If you need to publish an event from an async callback, inject `ApplicationEventPublisher` and publish explicitly:

~~~java
// Illustration inside a Spring bean, with @EnableAsync and a valid executor.
@Async("listenerExecutor")
@EventListener
public void processAsync(OrderCreated event) {
    OrderIndexed next = index(event);
    publisher.publishEvent(next);
}
~~~

This snippet only illustrates explicit publishing; it requires declaring `publisher`, `index`, and the actual executor. Do not treat a method returning `CompletableFuture<OrderIndexed>` as a mechanism where Spring automatically publishes `OrderIndexed` once the Future completes.

## 10. Proxies, `@Transactional`, and Uninvocable Methods

There are cases where **the parameter-count signature is valid**, yet AOP proxying prevents Spring from invoking the listener method on the actual bean.

A common scenario: the bean is created as a **JDK dynamic proxy** implementing only interfaces, while the `@EventListener` method exists solely on the implementation class and not on the interface exposed by the proxy. If the adapter cannot find an invocable method on the proxy, `IllegalStateException` or a registration/invocation error can occur.

Several fixes, depending on design:

1. Prefer **class-based proxies** if listener methods must be invoked on the concrete bean.
2. Ensure the method is declared on the public API/interface exposed by the proxy when using interface-based proxies, if appropriate.
3. Extract the listener into a dedicated bean **requiring no complex proxy**, delegating to another service that performs `@Transactional` work.
4. Check `proxyTargetClass`, method visibility, `final` classes/methods, and AOP limitations before altering the whole system.
5. Avoid self-invocation when expecting `@Transactional`/`@Async` to run through a proxy: calling `this.someMethod()` inside the same bean generally bypasses proxy advice.

**Do not assert that "every private method cannot be an EventListener"**. Reflection/annotation detection can handle non-public methods in certain contexts; however, when Spring AOP advice or JDK proxies are involved, visibility/invocability becomes a separate concern. When diagnosing, start with a **public, single-parameter method on a simple Spring bean** as a baseline; then add proxies incrementally.

Low-coupling design example:

~~~java
@Component
public class OrderEventsHandler {
    private final OrderAuditService auditService;

    public OrderEventsHandler(OrderAuditService auditService) {
        this.auditService = auditService;
    }

    @EventListener
    public void onCreated(OrderCreated event) {
        auditService.record(event.orderId());
    }
}
~~~

This is an illustrative snippet, not a standalone program. `OrderAuditService` is another bean that can apply `@Transactional` as needed.

## 11. `@TransactionalEventListener`: Not Running Does Not Mean Invalid Signature

`@TransactionalEventListener` binds a listener to a transaction phase:

~~~java
// Illustration: receive event after successful commit.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
~~~

Defaults:

- Phase is `AFTER_COMMIT`.
- Events published **outside a transaction** are skipped unless `fallbackExecution=true` is enabled.
- Events published **inside a transaction that rolls back** do not trigger `AFTER_COMMIT` callbacks.
- An event may have already been emitted and received by a synchronous `@EventListener`, while the transactional listener has not run yet because it is waiting for the completion phase.

If `@TransactionalEventListener` does not run, inspect the actual transaction boundary instead of blindly changing the method signature. With `@Async`, workers generally do not carry the old transaction context; do not try to copy all of `TransactionSynchronizationManager` to workers via `ThreadLocal`.

## 12. Symptom-Based Diagnostic Checklist

| Symptom | Likely cause | First step |
| --- | --- | --- |
| Startup reports “Maximum one parameter...” | Method has at least two parameters | Keep only one event parameter or split methods |
| Startup reports “Event parameter is mandatory...” | Method has no parameters and no `classes` | Add an event param or declare `classes` |
| Startup reports “Failed to process @EventListener annotation...” | Processor cannot register method/bean | Open deepest `Caused by` to pinpoint signature/proxy |
| Context starts yet listener is never called | Bean not in context, wrong event type, condition false | Check bean registration, published payload, SpEL |
| Listener fails only when event is published | SpEL condition, callback exception, proxy invocation | Debug stack trace at `publishEvent` |
| Listener does not run after transaction | `AFTER_COMMIT` waiting for commit or skipping non-tx events | Check active transaction and phase |
| Async callback errors not visible at publisher | Exception happens on executor | Check async handler, logs, and task completion |
| Method return causes looping events | Spring publishes return value | Change return type to `void` or design terminating workflow |
| Generic listener misses matching events | Type erasure / generic type metadata | Specify concrete type and test dispatch |
| Only one context receives the event | Event propagation / context hierarchy | Check publisher and listener contexts |

## 13. Step-by-Step Debugging Procedure

### Step 1 — Determine the Failure Time

Start the context **without publishing business events**. If startup already fails, focus on bean registration, proxies, and listener signatures. If startup succeeds and failure occurs on publish, focus on the callback body, `condition`, return-value event chains, and executor.

### Step 2 — Read the Deepest Root Cause

Record:

- Class/method named by Spring in the stack trace.
- Method parameter count and declared `@EventListener(classes=...)`.
- Bean name and actual class of the bean/proxy.
- `IllegalStateException`/SpEL exception message in `Caused by`.
- Context starting up and annotation processor configuration.

Do not look solely at the outermost `BeanCreationException` and edit every listener; the error chain usually points to the exact offending method.

### Step 3 — Reduce to a Baseline Listener

Simplify the suspect method to an easily verifiable form:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Temporarily just log or increment a test counter.
}
~~~

Place it in a simple bean declared via `@Component` or `@Bean`, ensuring Spring annotation support is active. Once the baseline works, re-introduce `condition`, `@Async`, transactions, and proxies **one factor at a time** to isolate the fault.

### Step 4 — Verify Event Type and Conditions

Print/observe at the publisher:

- Class of the published object.
- Event ID, aggregate ID/correlation ID if present.
- Which context publishes.
- Whether it is a POJO wrapper or `ApplicationEvent` subclass.
- If `condition` exists, temporarily test with `condition = "true"` to separate signature from SpEL.

Do not leave debugging changes in production when they disable critical business conditions.

### Step 5 — Verify Threads, Transactions, and Completion

If the listener is `@Async`, wait on tasks using `CountDownLatch`/`CompletableFuture` in tests rather than arbitrary `Thread.sleep`. If the callback uses a transaction phase, test both commit and rollback. If the bean uses a JDK proxy, verify the method is genuinely invocable via the proxy.

### Step 6 — Write Regression Tests

Test at least three cases:

1. A context with a valid listener refreshes cleanly and receives the expected event.
2. A listener with zero parameters and no `classes` is rejected at startup.
3. A listener with more than one event argument is rejected at startup.

When fixing production code, also test SpEL conditions, proxy configurations, and startup under real dependency injection wiring.

## 14. Advanced Testing with JUnit

You can adapt the example to JUnit 5:

~~~java
// Illustrative snippet; requires spring-test/JUnit dependencies and demo classes.
@Test
void invalidListenerShouldFailAtRefresh() {
    try (var context = new AnnotationConfigApplicationContext()) {
        context.register(NoEventTypeConfig.class);

        Exception exception = assertThrows(
                RuntimeException.class,
                context::refresh);

        assertTrue(hasCauseMessage(
                exception,
                "Event parameter is mandatory for event listener method"));
    }
}
~~~

For valid listeners, you can use `@SpringJUnitConfig` and `@RecordApplicationEvents` to inject `ApplicationEvents`, call the service, and assert the number of events actually published via `events.stream(OrderCreated.class)`. Remember that **a recorded event does not prove an async listener finished or a transaction committed**.

### What Needs Checking?

- Does component scanning include the listener bean's package?
- Is the bean truly a managed singleton/prototype Spring bean?
- Does the annotated method have exactly one parameter, or zero parameters with `classes`?
- Does the parameter type match the actual event object?
- Is a non-void return value accidentally publishing extra events?
- Does the SpEL condition use `#a0`/metadata properly?
- Does `@Async` have `@EnableAsync` and a suitable executor?
- If using a JDK proxy, is the method invocable on the proxy?
- If `@TransactionalEventListener`, are the phase and transaction boundary right?
- Do tests assert **event dispatch** and **side effects** separately?

## 15. Misconceptions to Avoid

**"Method has two parameters because it needs two pieces of data"** — Spring resolves only the event parameter; it does not inject repositories, security contexts, or services as extra callback parameters. Inject dependencies into the bean via constructor; put required business data in the event payload or look it up cleanly.

**"A parameterless method is always invalid"** — false. Zero parameters is **valid if `classes` specifies the event type**.

**"A method never being called definitely means an invalid method signature"** — false. It may simply be an event type mismatch, false condition, out-of-transaction publish, or incomplete async work.

**"A non-void return type is a compiler error"** — incorrect. Return values are normally published by Spring as new events; this is valid behavior but can cause loops if misunderstood.

**"`@Async` with a return value makes Spring publish after the Future resolves"** — false under the async event listener contract. To publish follow-up events from async logic, publish explicitly.

**"All private/final methods behave the same"** — proxy type, AOP interception, visibility, and annotation introspection are separate aspects. Use public APIs and simple beans for baseline diagnosis and rely on actual stack traces.

**"Just retry when startup fails"** — false. An invalid listener signature is a deterministic code/configuration error; restarting will not change the method. Fix the code/config and add a regression test.

## 16. Final Checklist

1. Identify the running Spring Framework version and annotation listener registration context.
2. Read the deepest error: startup registration or runtime invocation?
3. Confirm `@EventListener` methods have **0 or 1 parameter**, and 0-parameter methods explicitly specify `classes`.
4. Do not use two-parameter listeners to join two independent events.
5. Verify actual `classes`/event payload types, especially wrapped POJOs.
6. Test SpEL `condition` separately; use `#a0` when unsure whether parameter names are retained.
7. Verify the bean belongs to the Spring context, annotation processors are active, and the method is invocable through proxies.
8. Confirm the return type does not accidentally publish extra events.
9. For `@Async` and `@TransactionalEventListener`, check executor, transaction phase, and callback completion.
10. Add one startup test and one event dispatch test to prevent regressions.

**Remember:** In Spring Framework 6.2, `@EventListener` does not support arbitrary multiple parameters like controller methods. The safest signature is **one parameter of the exact event type**, or **zero parameters with `classes`**. When errors occur, classify first: listener registration failed, listener invocation failed, or listener was never selected. Proper classification fixes the root cause without unnecessarily warping lifecycle or business logic.

## Official Documentation

- Spring Framework 6.2 — ApplicationContext events, @EventListener, return values, and async: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — @EventListener Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2 — ApplicationListenerMethodAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationListenerMethodAdapter.html
- Spring Framework 6.2 — EventListenerMethodProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html