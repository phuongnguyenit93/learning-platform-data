# Comparing Direct Calls and Event Publishing in Spring Framework Application Events

## 1. The Problem and Target Outcomes

In a sales application, after an order is accepted, the system needs to:

1. Update the order status.
2. Record an audit entry.
3. Prepare a customer notification.
4. Update analytics/metrics.

There are two familiar implementation styles:

- **Direct invocation:** the orchestrating service explicitly calls each dependency.
- **Publishing an event:** the service publishes an event describing **what happened**; registered listeners receive the event and execute their corresponding reactions.

Both are valid. The decision is not about which style is "more modern," but about the **business contract**: which steps must succeed on the main call path, which steps are supplementary reactions, how much decoupling the system needs, how errors propagate, where transactions close, and what reliability level is required.

After this guide, you will be able to:

- Diagram the call flow of direct invocation vs. local application events in Spring.
- Distinguish **compile-time dependencies**, **runtime coupling**, and **event contracts**.
- Understand the default behavior of `ApplicationEventPublisher.publishEvent(...)`: **plain listeners run synchronously on the calling thread**, not in the background by default.
- Know when to choose direct calls, `@EventListener`, `@Async`, or `@TransactionalEventListener`.
- Understand the interplay among exceptions, ordering, return values, transactions, rollbacks, and eventual consistency.
- Build a runnable Java 17 + Spring Framework 6.2 program comparing the same business flow under both patterns.
- Test the number of published events, listener side effects, and failure cases.
- Avoid mistaking in-process events for a message broker with built-in retries or exactly-once guarantees.

This topic belongs to the **Deployment Patterns** group of the **Spring Framework Application Events** module.

## 2. Comparing Two Processing Flows

### 2.1. Direct Invocation

```text
OrderController / command handler
              |
              v
       OrderApplicationService
              |
              +--> orderRepository.accept(orderId)
              |
              +--> auditService.record(orderId)
              |
              +--> notificationService.request(orderId)
              |
              +--> return result / throw exception
```

The source code names the exact components invoked. Reading the method reveals quite clearly which steps will run, in what order, and what each dependency returns or throws.

Example:

```java
public void accept(String orderId) {
    orderRepository.accept(orderId);
    auditService.record(orderId);
    notificationService.request(orderId);
}
```

This is an **illustrative snippet**: the repository and services must be defined. In the complete program in Section 7, real dependencies are declared and injected by Spring.

### 2.2. Publishing an Application Event

```text
OrderController / command handler
              |
              v
       OrderApplicationService
              |
              +--> orderRepository.accept(orderId)
              |
              +--> publisher.publishEvent(
              |       OrderAccepted(eventId, orderId))
              |
              v
   Spring ApplicationEventMulticaster
              |
              +--> AuditListener.onAccepted(...)
              |
              +--> NotificationListener.onAccepted(...)
              |
              +--> MetricsListener.onAccepted(...)
```

The event-publishing service only needs to know the **event contract** and `ApplicationEventPublisher`, not the list of all listeners. A new module can add a listener for the event without modifying the source service, provided Spring's dispatch requirements are met.

Example:

```java
public void accept(String orderId) {
    orderRepository.accept(orderId);
    publisher.publishEvent(
            new OrderAccepted("evt-" + orderId, orderId));
}
```

This is also an **illustrative snippet**; in real systems, `eventId` must be stable per event occurrence rather than simply derived from `orderId` if multiple acceptance events can occur for the same aggregate. This guide uses that formula **solely for deterministic demo output**.

### The Most Common Misconception

**Publishing an event in Spring does not mean asynchronous processing.** Spring uses `SimpleApplicationEventMulticaster` with a **synchronous default strategy**, meaning each plain listener is called on **the publisher's thread**. When a listener fails and the exception is unhandled, the exception can propagate out of `publishEvent(...)`. Thus events **reduce source-code coupling**, yet **do not automatically decouple execution timing, thread resources, or transactions**.

To switch to async, you must **explicitly configure** `@Async`/an executor or an appropriate multicaster. Doing so changes the contract regarding ordering, completion timing, and error propagation.

## 3. Technical Comparison Table

| Criterion | Direct Call | In-Process Event Publishing |
| --- | --- | --- |
| Dependency relationship | Caller injects and invokes concrete services | Publisher knows the event type and `ApplicationEventPublisher`; unaware of listeners |
| Execution path discovery | Easy via call graph | Must search for matching `@EventListener`/`ApplicationListener` beans |
| Multiple reactions | Caller invokes each or uses an orchestrator | Multiple listeners can subscribe to one event |
| Return values | Methods can return typed results | `publishEvent(...)` returns no aggregate result from listeners |
| Ordering | Call order is explicit in code | Can use `@Order` for sync listeners; no automatic async completion order |
| Synchronous by default | Yes | **Yes** with the default multicaster and plain listeners |
| Exception propagation | Dependency exceptions normally reach caller | Sync listener exceptions usually propagate to publisher |
| Transactions | Call path easy to follow; same thread shares active TX | Sync listeners can join the TX; post-commit requires dedicated annotations |
| Async | Explicitly create executor, `@Async`, or equivalent | Not automatically async; `@Async` can be added to listeners |
| Testing | Mock/stub each dependency | Unit-test publisher and integration-test event + listeners |
| Adding new behavior | Usually requires editing the orchestrator | Listeners can be added without modifying the publisher |
| Schema coupling | Service API has an explicit signature | Event schema is a contract that also needs versioning |
| Reliability across crashes | Depends on transaction and external effects | Local events are **not durable by default**; need outbox/broker if loss is unacceptable |
| Deduplication | Caller/consumer must design it | Framework **does not** deduplicate `eventId` |
| Performance | A few method calls plus internal work | Adds event dispatch, listener matching, and payload overhead; not inherently faster |
| Business transparency | Mandatory steps are obvious | Fan-out scales easily but can obscure critical side effects |

**There is no universal conclusion that "publishing events is always better."** Choose the right style based on criticality, workflow stability, and extensibility needs.

## 4. When Are Direct Calls the Right Choice?

### 4.1. A Step Is a Precondition for the Outcome

If operation A **must not be considered successful unless B succeeds**, a direct call or an explicit workflow/orchestrator is usually more appropriate.

For example, an order is confirmed only if **inventory reservation** succeeds:

```java
public Confirmation confirm(String orderId) {
    inventoryService.reserve(orderId);
    paymentService.authorize(orderId);
    return orderService.confirm(orderId);
}
```

This is **illustrative code**, not a runnable multi-service transaction. It expresses a clear dependency: `confirm` needs the outcomes of `reserve` and `authorize`. In distributed architectures where steps span multiple services, sagas/compensation or dedicated protocols are needed; direct HTTP calls do not automatically provide atomic transactions either.

### 4.2. The Caller Needs an Immediate Result or Error

Example:

```java
TaxCalculation tax = taxService.calculate(lines, region);
if (tax.total().signum() < 0) {
    throw new IllegalStateException("Invalid tax result");
}
```

The caller needs a concrete typed result to decide the next step. `publishEvent(...)` is a broadcast API, **not** a request-response API aggregating values across listeners. When the caller needs a mandatory answer, do not replace a direct service call with an event just to shrink imports.

### 4.3. Tight Transactional and Ordering Constraints

A command that must write related data inside the **same transaction** should generally keep critical operations explicit. For instance, writing an invoice and its invoice lines via repositories in one transaction. Splitting them into `@EventListener` beans merely for "modularity" can hide the fact that synchronous listeners still participate in the transaction and that throwing an exception triggers rollback.

**Design pattern:** the service directly orchestrates mandatory invariants; after establishing the business fact, it publishes an event to notify **reactions that are not preconditions**.

## 5. When Is Publishing Events the Right Choice?

### 5.1. One Event Has Multiple Independent Subscribers

For example, `OrderAccepted` can lead to:

- Audit recording an entry.
- Analytics incrementing accepted order counts.
- Notification preparing an email.
- Read model updating.
- An external module observing to add supplementary features.

If every module had to be hard-coded into `OrderService`, dependencies would multiply and changing an auxiliary feature could force editing core business logic. Events allow the emitting module to remain unaware of **how many listeners exist or their concrete identities**.

### 5.2. The Event Expresses a Past Fact

A good event describes **something that has already happened**, for example:

```java
public record OrderAccepted(
        String eventId,
        String orderId
) {}
```

Do not name an event like a mandatory command such as `PleaseChargeCreditCardNow` and publish it expecting a single listener to reliably execute and return a result. Commands/intents have a different contract than domain facts.

### 5.3. Modules Evolve on Independent Lifecycles

When marketing adds an analytics listener, the domain service does not need to change. Still, the event contract must stay stable: renaming fields, changing the event type, altering `eventId` semantics, or dropping `orderId` can break subscribers. **Coupling does not disappear; it shifts from direct compile-time dependencies to the event contract and runtime configuration.**

### 5.4. Side Reactions Tolerate Eventual Consistency

Tasks such as updating projections, sending notification emails, and search indexing fit events well—provided the business tolerates delayed completion and has retry/durability mechanisms when required. With default synchronous Spring events, they **do not run later yet**; choose async/outbox when execution timing genuinely needs to be decoupled.

## 6. How Does Spring Handle Event Publishing?

### 6.1. ApplicationEventPublisher

`ApplicationEventPublisher` has overloads accepting either `ApplicationEvent` or any object:

```java
publisher.publishEvent(new OrderAccepted("evt-100", "ORD-42"));
```

A Java record does not need to extend `ApplicationEvent`. Spring wraps it in `PayloadApplicationEvent<T>` for dispatch; `@EventListener` methods can accept **the record type directly**.

Participants:

```text
ApplicationEventPublisher
        |
        v
ApplicationContext
        |
        v
ApplicationEventMulticaster
        |
        +--> @EventListener handlers
        +--> ApplicationListener implementations
```

These are **in-process** events inside one `ApplicationContext`, not a networked message bus.

### 6.2. Event Listeners

```java
@Component
public class AuditListener {
    @EventListener
    public void onAccepted(OrderAccepted event) {
        auditService.record(event.orderId());
    }
}
```

This is an integration snippet requiring dependencies/imports. An event listener works only when the class is a **Spring-managed bean**, the matching method is detected by the infrastructure, and the event type matches. Instantiating `new AuditListener(...)` manually outside the context and expecting Spring to scan it is wrong.

### 6.3. Multiple Listeners, Not "One Callback per Event"

One publish call invokes **all** listeners matching the event type (subject to any filters/conditions). `@Order` can help order invocations among those listeners:

```java
@Order(10)
@EventListener
public void auditFirst(OrderAccepted event) {
    // ...
}

@Order(20)
@EventListener
public void notifyLater(OrderAccepted event) {
    // ...
}
```

This is an illustrative snippet requiring the corresponding bean class and event. With the default synchronous multicaster, this invocation order can be observed. However, **`@Order` creates neither a transaction commit ordering nor a completion ordering guarantee across async workers**.

### 6.4. Listeners Can Emit Derived Events

A **synchronous** listener can return a new event:

```java
@EventListener
public InventoryRequested onOrderAccepted(OrderAccepted event) {
    return new InventoryRequested(event.orderId());
}
```

Spring publishes the return value as a derived event; if the method returns a collection/array, each element can be published. This integration snippet requires defining `InventoryRequested`. Avoid overusing chaining when it could create infinite loops or obscure transaction ownership and orchestration.

For `@Async` listeners, **do not use return values to publish subsequent events**; call `ApplicationEventPublisher.publishEvent(...)` explicitly.

## 7. Runnable Example: Same Business Logic, Two Structural Styles

This program uses **Java 17**, **Spring Framework 6.2**, and **Maven**, without Spring Boot, a web server, or a database.

Context:

- `DirectOrderFlow` accepts an order and **directly calls** `AuditAction` and `NotificationAction`.
- `EventOrderFlow` accepts an order and only **publishes `OrderAccepted`**.
- On the event flow, there are three independent listeners: audit, notification, and metrics.
- `@Order(10/20/30)` yields deterministic output in this **default synchronous** example.
- An `ActionTrace` records step order; `InMemoryOrders` holds state for the demo.
- For simplicity, `eventId = "evt-" + orderId` in the demo is an **illustrative value**, not a production ID strategy.

### 7.1. Directory Structure

```text
direct-vs-event/
├── pom.xml
└── src/
    ├── main/java/example/DirectVsEventDemo.java
    └── test/java/example/DirectVsEventDemoTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>direct-vs-event</artifactId>
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
            <artifactId>spring-test</artifactId>
            <version>6.2.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.3</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.DirectVsEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/java/example/DirectVsEventDemo.java

```java
package example;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class DirectVsEventDemo {

    public record OrderAccepted(String eventId, String orderId) {
        public OrderAccepted {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "IDs must not be blank");
            }
        }
    }

    public static final class ActionTrace {
        private final List<String> entries = new ArrayList<>();

        public void add(String entry) {
            entries.add(entry);
        }

        public List<String> snapshot() {
            return List.copyOf(entries);
        }

        public void clear() {
            entries.clear();
        }
    }

    public static final class InMemoryOrders {
        private final Map<String, String> states = new HashMap<>();
        private final ActionTrace trace;

        public InMemoryOrders(ActionTrace trace) {
            this.trace = trace;
        }

        public void accept(String orderId) {
            states.put(orderId, "ACCEPTED");
            trace.add("state:" + orderId);
        }

        public String status(String orderId) {
            return states.get(orderId);
        }
    }

    public static final class AuditAction {
        private final ActionTrace trace;

        public AuditAction(ActionTrace trace) {
            this.trace = trace;
        }

        public void record(String orderId) {
            trace.add("audit:" + orderId);
        }
    }

    public static final class NotificationAction {
        private final ActionTrace trace;

        public NotificationAction(ActionTrace trace) {
            this.trace = trace;
        }

        public void request(String orderId) {
            trace.add("notify:" + orderId);
        }
    }

    public static final class DirectOrderFlow {
        private final InMemoryOrders orders;
        private final AuditAction audit;
        private final NotificationAction notification;

        public DirectOrderFlow(
                InMemoryOrders orders,
                AuditAction audit,
                NotificationAction notification) {
            this.orders = orders;
            this.audit = audit;
            this.notification = notification;
        }

        public void accept(String orderId) {
            orders.accept(orderId);
            audit.record(orderId);
            notification.request(orderId);
        }
    }

    public static final class EventOrderFlow {
        private final InMemoryOrders orders;
        private final ApplicationEventPublisher publisher;

        public EventOrderFlow(
                InMemoryOrders orders,
                ApplicationEventPublisher publisher) {
            this.orders = orders;
            this.publisher = publisher;
        }

        public void accept(String orderId) {
            orders.accept(orderId);
            OrderAccepted event = new OrderAccepted(
                    "evt-" + orderId, orderId);
            publisher.publishEvent(event);
        }
    }

    public static class AuditEventListener {
        private final AuditAction audit;

        public AuditEventListener(AuditAction audit) {
            this.audit = audit;
        }

        @Order(10)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            audit.record(event.orderId());
        }
    }

    public static class NotificationEventListener {
        private final NotificationAction notification;

        public NotificationEventListener(
                NotificationAction notification) {
            this.notification = notification;
        }

        @Order(20)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            notification.request(event.orderId());
        }
    }

    public static class MetricsEventListener {
        private final ActionTrace trace;

        public MetricsEventListener(ActionTrace trace) {
            this.trace = trace;
        }

        @Order(30)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            trace.add("metric:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public ActionTrace trace() {
            return new ActionTrace();
        }

        @Bean
        public InMemoryOrders orders(ActionTrace trace) {
            return new InMemoryOrders(trace);
        }

        @Bean
        public AuditAction auditAction(ActionTrace trace) {
            return new AuditAction(trace);
        }

        @Bean
        public NotificationAction notificationAction(
                ActionTrace trace) {
            return new NotificationAction(trace);
        }

        @Bean
        public DirectOrderFlow directOrderFlow(
                InMemoryOrders orders,
                AuditAction audit,
                NotificationAction notification) {
            return new DirectOrderFlow(orders, audit, notification);
        }

        @Bean
        public EventOrderFlow eventOrderFlow(
                InMemoryOrders orders,
                ApplicationEventPublisher publisher) {
            return new EventOrderFlow(orders, publisher);
        }

        @Bean
        public AuditEventListener auditEventListener(
                AuditAction audit) {
            return new AuditEventListener(audit);
        }

        @Bean
        public NotificationEventListener notificationEventListener(
                NotificationAction notification) {
            return new NotificationEventListener(notification);
        }

        @Bean
        public MetricsEventListener metricsEventListener(
                ActionTrace trace) {
            return new MetricsEventListener(trace);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            DirectOrderFlow direct =
                    context.getBean(DirectOrderFlow.class);
            EventOrderFlow eventFlow =
                    context.getBean(EventOrderFlow.class);
            ActionTrace trace =
                    context.getBean(ActionTrace.class);
            InMemoryOrders orders =
                    context.getBean(InMemoryOrders.class);

            direct.accept("ORD-D");
            System.out.println("DIRECT " + trace.snapshot());

            trace.clear();

            eventFlow.accept("ORD-E");
            System.out.println("EVENT  " + trace.snapshot());

            System.out.println(
                    "STATUS ORD-D=" + orders.status("ORD-D"));
            System.out.println(
                    "STATUS ORD-E=" + orders.status("ORD-E"));
        }
    }
}
```

### 7.4. Running with Maven

In the directory containing `pom.xml`, using JDK 17+:

```bash
mvn -q compile exec:java
```

**Four lines printed directly by the program**, excluding infrastructure logs if any:

```text
DIRECT [state:ORD-D, audit:ORD-D, notify:ORD-D]
EVENT  [state:ORD-E, audit:ORD-E, notify:ORD-E, metric:ORD-E]
STATUS ORD-D=ACCEPTED
STATUS ORD-E=ACCEPTED
```

### 7.5. Why This Output Is Correct

**Direct flow:**

1. `DirectOrderFlow.accept("ORD-D")` calls `orders.accept(...)`, updates state, and adds `state:ORD-D`.
2. Calls `AuditAction.record(...)`, adding `audit:ORD-D`.
3. Calls `NotificationAction.request(...)`, adding `notify:ORD-D`.
4. There is no `publishEvent(...)` call, so the event flow's three `@EventListener` beans are not triggered by this direct flow.
5. After printing, `trace.clear()` clears the trace entries **without deleting order state**.

**Event flow:**

1. `EventOrderFlow.accept("ORD-E")` calls `orders.accept(...)`, adding `state:ORD-E`.
2. The service creates an `OrderAccepted` and calls `publisher.publishEvent(event)` **once**.
3. Spring locates three matching listeners accepting `OrderAccepted`.
4. With the default synchronous multicaster, all methods are invoked on the publisher thread. `@Order(10)` audit, `@Order(20)` notification, and `@Order(30)` metrics produce callbacks in that order.
5. Because publishing is synchronous in the demo, by the time `eventFlow.accept(...)` returns, `trace` already contains all three callbacks.
6. The event flow includes `metric:ORD-E` **without adding any dependency to `EventOrderFlow`**. This is the benefit of extensible subscriptions.
7. Both flows set the order status to `ACCEPTED`; there is no database or transaction, so the demo illustrates neither durability nor rollback.

**What must not be inferred from this output:** the event flow is not inherently faster, more thread-safe, more durable, or guaranteed post-commit. These results reflect one Spring context, one synchronous thread, and in-memory state.

## 8. Testing with Spring TestContext and JUnit 5

The test suite below directly continues the Section 7 project; it verifies:

- Direct flow executes explicit actions yet **does not publish `OrderAccepted`**.
- Event flow publishes **one** `OrderAccepted` with the right payload and triggers **three subscribers**.
- Each test resets `ActionTrace` to avoid cross-contamination across test methods in the cached context.

### 8.1. src/test/java/example/DirectVsEventDemoTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.DirectVsEventDemo.ActionTrace;
import example.DirectVsEventDemo.DirectOrderFlow;
import example.DirectVsEventDemo.EventOrderFlow;
import example.DirectVsEventDemo.OrderAccepted;

@SpringJUnitConfig(DirectVsEventDemo.Config.class)
@RecordApplicationEvents
class DirectVsEventDemoTest {

    @Autowired
    DirectOrderFlow direct;

    @Autowired
    EventOrderFlow eventFlow;

    @Autowired
    ActionTrace trace;

    @BeforeEach
    void reset() {
        trace.clear();
    }

    @Test
    void directCallsActionsWithoutPublishing(
            ApplicationEvents events) {
        events.clear();

        direct.accept("TEST-D");

        assertEquals(0,
                events.stream(OrderAccepted.class).count());
        assertEquals(
                List.of(
                        "state:TEST-D",
                        "audit:TEST-D",
                        "notify:TEST-D"),
                trace.snapshot());
    }

    @Test
    void eventPublishesOnceAndNotifiesThreeListeners(
            ApplicationEvents events) {
        events.clear();

        eventFlow.accept("TEST-E");

        List<OrderAccepted> published =
                events.stream(OrderAccepted.class).toList();
        assertEquals(1, published.size());
        assertEquals("evt-TEST-E", published.get(0).eventId());
        assertEquals("TEST-E", published.get(0).orderId());
        assertEquals(
                List.of(
                        "state:TEST-E",
                        "audit:TEST-E",
                        "notify:TEST-E",
                        "metric:TEST-E"),
                trace.snapshot());
    }
}
```

### 8.2. Running Tests

```bash
mvn test
```

Assuming dependencies resolve and the code runs cleanly, the Surefire report for `DirectVsEventDemoTest` is expected to show:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

These are the **expected summary fields**, not the entirety of Maven's stdout; plugin versions, CI settings, and environment logs may add lines. The report file is at `target/surefire-reports/example.DirectVsEventDemoTest.txt`.

### 8.3. Why Do Both Assertions Matter?

The direct test verifies the method calls actions in order with zero events recorded. With Spring TestContext, `@RecordApplicationEvents` records events emitted during the test, and `ApplicationEvents.stream(OrderAccepted.class)` filters by exact event type.

The event test does not merely count events—it **asserts the payload** and **listener trace**. This prevents confusing "the service published an event" with "handlers definitely produced the right effects": those are two separate assertions.

**Limitation:** the test uses a synchronous/in-memory context. With `@Async` listeners, do not assert traces right after publish; use latches/futures with timeouts and thread-safe result collectors. With post-commit transactions, perform an actual commit before asserting callbacks.

## 9. Exceptions: How Do Direct Calls and Synchronous Events Differ?

### 9.1. Direct Calls: Exceptions at Explicit Call Sites

Example:

```java
orderRepository.accept(orderId);
auditService.record(orderId);
notificationService.request(orderId); // May throw
```

If `auditService.record(...)` throws an exception, the notification line normally does not run. The caller sees the exception on the call stack unless caught/translated. If the DB operations share a transaction, an appropriate exception can trigger transaction rollback. **Already-completed external side effects cannot roll back automatically.**

### 9.2. Synchronous `@EventListener`: Exceptions Still Reach the Publisher

```java
@Order(10)
@EventListener
public void audit(OrderAccepted event) {
    throw new IllegalStateException("Audit failed");
}
```

This is an illustrative snippet. With the default synchronous `SimpleApplicationEventMulticaster` **without a custom `ErrorHandler`**, an exception from a listener can propagate out of `publishEvent(...)`, failing the publisher. Subsequent listeners may never be called. If earlier subscribers caused non-rollbackable external effects before the exception occurred, business state may become inconsistent.

**Practical difference:** direct calls make clear which dependencies can fail the caller. With events, the caller may not visibly list every dependent listener in source code, yet can still fail from them when executed synchronously.

### 9.3. Multicaster `ErrorHandler`

You can configure an `ApplicationEventMulticaster` with an `ErrorHandler` to handle exceptions differently from the default contract. However, if the error handler **swallows errors**, the publisher may return success even though a listener failed. This can be valid for best-effort monitoring, but must not be used to mask failures in workflows with mandatory effects.

Never adopt "catch every exception and continue" as a blanket solution. Decide **business-critical effects**, retries, and compensation upfront.

## 10. What Does `@Async` Change?

Annotate a listener:

```java
@EnableAsync
@Configuration
class AsyncConfig {
    // Declare a Spring-managed TaskExecutor.
}

@Async("eventExecutor")
@EventListener
public void onAccepted(OrderAccepted event) {
    notificationService.request(event.orderId());
}
```

This is an **integration snippet**; the method must live on a suitable bean, `@EnableAsync` must be processed by Spring config, and the `eventExecutor` bean must exist and be configured. The snippet above is not a standalone runnable program.

When `@Async` is active via Spring proxy:

- The listener may execute on a worker thread **after `publishEvent(...)` returns**.
- The caller generally does not receive exceptions from an `@Async void` listener; handle them via `AsyncUncaughtExceptionHandler` or an appropriate outcome mechanism.
- You cannot rely on `@Order` to guarantee **completion order** across multiple threads.
- `ThreadLocal`, MDC, and the publisher's transaction **do not automatically travel to the worker**.
- A failing listener may need its own retries; local in-RAM `@Async` **is not durable across crashes**.
- An async listener's return value must not be used to publish derived events; publish explicitly instead.

**This makes the contract different from direct calls:** you cannot enforce "email must finish before order confirmation" inside an async listener without explicit synchronization, error handling, and compensation.

### `TaskDecorator` for Logging Context

If you need to preserve `traceId` in logs, a `TaskDecorator` can capture and restore MDC when the executor runs the task. However, **logging context is neither transaction context nor security authorization**. If an event needs `orderId`, `tenantId`, and `correlationId` for reliable processing, put the required verified data in the payload.

## 11. Transactions: More Important Than Call Syntax

### 11.1. Synchronous Events Do Not Automatically Run After Commit

Consider:

```java
@Transactional
public void acceptOrder(String orderId) {
    orderRepository.accept(orderId);
    publisher.publishEvent(
            new OrderAccepted("evt-100", orderId));
}
```

With a default synchronous `@EventListener`, the callback typically runs **while the transaction is still open**, before successful commit. If the listener immediately sends an email or HTTP call, the email goes out while the transaction may still roll back, creating a "ghost notification." Calling the email service directly in the same method carries the exact same risk.

**The difference is not direct vs. event:** the issue is **transaction boundaries** and when external side effects are triggered.

### 11.2. `@TransactionalEventListener(AFTER_COMMIT)`

If a reaction should run only after successful commit:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onAcceptedAfterCommit(OrderAccepted event) {
    externalGateway.publish(event);
}
```

This is an integration snippet requiring a real transaction manager and listener bean. `@TransactionalEventListener` defaults to `AFTER_COMMIT`. When published outside a transaction, the listener normally **does not run** because `fallbackExecution = false`; on rollback, the post-commit callback does not run either.

**Crucial limitation:** an `AFTER_COMMIT` callback is strictly an in-process callback. If the database committed and the process crashes **before the callback or before broker ACK**, the event can be lost; the annotation provides no durability.

### 11.3. Writing to the DB After Commit and `REQUIRES_NEW`

Spring notes that during post-completion callbacks, some transaction resources may remain bound to the thread. If a callback needs to perform new DB writes, use a genuinely new transaction—for example, a separate service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` invoked via Spring proxy, or a `TransactionTemplate` configured with `PROPAGATION_REQUIRES_NEW`.

Writing to the DB after commit **cannot close** the crash window between the business commit and the callback. That is why the transactional outbox pattern is valuable.

### 11.4. Outbox for Reliable Outbound Delivery

```text
BUSINESS TRANSACTION
    +--> UPDATE order
    +--> INSERT event_outbox(eventId, payload, PENDING)
    +--> COMMIT both

RELAY WORKER
    +--> poll committed outbox
    +--> send to broker/HTTP with retry
    +--> mark SENT after acknowledgment
```

A transactional outbox persists the **intent to publish** alongside business state. If the process dies after commit, the row remains for a worker to resume. A relay can still send duplicates if it crashes after broker ACK before marking `SENT`, so consumers need idempotency.

Do not put a `@TransactionalEventListener` writing to the outbox **after commit** and treat it as an atomic outbox with business state; that is **two transactions** and still leaves a task-loss window.

## 12. When Should You Use a Hybrid Pattern?

A balanced structure:

```text
OrderApplicationService
    |
    +--> direct: validate order
    +--> direct: reserve inventory (if mandatory)
    +--> direct: persist order + outbox in same transaction
    |
    +--> local event/hint (optional) to wake relay
             |
             +--> notification projection
             +--> analytics
             +--> best-effort audit
```

Operations belonging to **invariants** that require immediate outcomes are written clearly as direct calls. Events express a past fact for supplementary subscribers. When durable outbound delivery is needed, the outbox is persisted in the same transaction regardless of whether an in-process Spring listener runs.

**The hybrid pattern does not mean** firing an event after every line of code. Events need domain meaning, clear boundaries, versioned schemas, and managed impact.

### One Event or Multiple Events?

For example, `OrderAccepted` and `PaymentCaptured` are two distinct facts. Do not cram every change into a `GenericEvent(type, payload)` just to have one generic publish API, because consumers lose type safety and testing gets harder.

If a business flow produces multiple facts, each occurrence needs its own `eventId`, may share a `correlationId`, and derived events carry a `causationId` pointing to their source. This makes tracing fan-out and retries accurate.

## 13. Decisions to Make Before Refactoring Direct Calls to Events

### 13.1. What Does Caller Success Mean?

A direct service may return only after all dependencies finish. Switching to async listeners lets the caller return "success" before notifications or projections are ready. If the API contract promises "receipt is ready as soon as ordering succeeds," refactoring carelessly breaks the contract.

Define the **reaction SLA**: synchronous within the request, eventual within seconds, or immediately committed/acked.

### 13.2. Who Owns Errors?

When a direct dependency fails, the caller usually handles it. With synchronous local events, listener errors can still propagate to the publisher. With async events, errors belong to listeners and separate retry/monitoring infrastructure. Never shift error ownership without adding dead-letter queues, retries, or status tracking.

### 13.3. Who Owns Data?

Event payloads should contain immutable snapshots of required data. Never pass attached/lazy JPA entities, `HttpServletRequest`, transaction objects, or shared mutable lists to async handlers assuming data stays valid. For long-lived events, use stable IDs/metadata, enforce tenant permissions, and version schemas properly.

### 13.4. Who Handles Duplicates?

An `OrderAccepted(eventId)` can be republished by retries or redelivered from an outbox/broker. Spring does not deduplicate by `eventId`. For effects that must not repeat, handlers need idempotency, such as a unique key `(consumer_name, event_id)` plus business unique constraints where needed.

### 13.5. Could Fan-Out Create Loops?

Listener A might publish a derived event, and another listener might publish the original event again. Without transition/causation rules, a chain can loop indefinitely. Direct workflows make execution order obvious, whereas event chains need trace graphs and clear bounds.

## 14. Testing Strategy: Two Patterns Need Different Evidence

| Question | Direct Call | Event Publishing |
| --- | --- | --- |
| Was a mandatory method invoked? | Mocks/spies/fixtures for dependency | If mandatory, consider direct orchestration |
| Was the right event type emitted? | N/A if no event emitted | Use `@RecordApplicationEvents` or mock publisher |
| Is the payload accurate? | Assert inputs passed to service | Assert `eventId`, `aggregateId`, timestamp, schema, metadata |
| Which listeners handled it? | Read call graph; test each service's effect | Integration-test Spring listener beans, conditions, and type matching |
| Were there duplicate callbacks? | Assert invocation count per dependency | Compare publish count, listener count, duplicate deliveries |
| Do exceptions reach the caller? | Test dependency throwing | Test sync listeners, `ErrorHandler`, or async behavior separately |
| Commit/rollback? | Test business transaction and effects | Test `AFTER_COMMIT` with real transaction commits and rollbacks |
| Did async finish? | When using async directly, use Future/latch | Never assert right after publish; use latch/timeout |
| Crash/restart & durable delivery? | Requires workflow persistence/retries | Requires outbox/broker/recovery; plain Spring events are not enough |

### Why Not Just Mock the Publisher?

A unit test:

```java
verify(publisher).publishEvent(captor.capture());
assertEquals("ORD-42", captor.getValue().orderId());
```

This is a **Mockito snippet** requiring declared mock publisher and captor. It proves the service called publish with a specific payload; it does **not** prove Spring registered the listener, conditions matched, or the listener produced the right effect.

You need at least one Spring integration test for critical publish/subscribe paths. Section 8 provided a test suite using `@SpringJUnitConfig` and `@RecordApplicationEvents`.

### Why Not Just Assert That the Listener Logged Something?

Loggers can filter, batch, or be duplicated by log collectors; a log line is not sufficient proof of a business effect. Tests should inspect state, outbox rows, or thread-safe recorder contents when needed.

## 15. Performance and Complexity

Within a single JVM, publishing events still incurs payload creation, listener lookup, and handler invocation. With a synchronous multicaster, total request latency reflects **all listeners combined**. Adding one listener that makes a slow network request slows down the publisher even though the source service does not inject that dependency.

Direct calls have low method-call overhead and are easier to predict, though **overall cost is still governed by the business work inside**, not a single call instruction.

### Don't Optimize on Gut Feeling

Measure:

- Request latency with 1 / 5 / 20 synchronous listeners.
- CPU and allocations when publishing events at high rates.
- Task queue depth and backpressure when async is enabled.
- Exception rates, callback timeouts, retries, and duplicates.
- Lag from business commit to side-effect completion.
- Impact of one slow subscriber on other subscribers.

If fan-out is large and effects must run independently, moving to an outbox + broker or job queue is often better than forcing everything through local application events.

## 16. Differences in Observability and Debugging

Direct calls are usually easy to trace via call stacks and line numbers. With events, "who receives this event?" becomes a runtime subscriber lookup question. Logs should include:

```text
eventType
eventId
aggregateId
correlationId
causationId
publisherMethod
listenerBean
listenerMethod
transactionPhase
threadName
processingAttempt
processingStatus
```

An event published once can produce three `LISTENER_START` lines because of three beans; that is normal fan-out. However, the same bean receiving the same `eventId` multiple times indicates repeated publishing/retries or duplicate registration. Never just count log lines and blame the framework for double-calling.

With async listeners, MDC/trace context usually does not propagate automatically; `TaskDecorator` or Micrometer Context Propagation helps observability without replacing transaction/security context.

### Practical Debugging Tips

1. Log at the **`publishEvent(...)` source** with an invocation ID.
2. Log at the **listener entry** with bean name, `eventId`, and thread.
3. Distinguish publish time, listener start, and listener finish.
4. Inspect errors and transaction phases, not just final outputs.
5. Check how many listener beans actually exist per module in the context.
6. With parent/child contexts, check the context source; child events can propagate up to parent contexts.
7. With brokers/outboxes, include delivery attempt and message offset/claim ID.
8. Verify actual effects in the DB or external system, not just log lines.

## 17. Common Mistakes

1. **Assuming publishing an event runs async automatically.** Spring invokes plain listeners synchronously by default.
2. **Replacing direct calls with events for steps requiring return values.** `publishEvent(...)` is not a request-response API.
3. **Thinking events isolate transactions automatically.** Synchronous listeners can join the source transaction.
4. **Calling email/HTTP in a pre-commit synchronous listener.** Rollbacks can leave ghost effects behind.
5. **Choosing `AFTER_COMMIT` and assuming events cannot be lost.** In-RAM callbacks still have a crash window.
6. **Assuming `@Order` guarantees completion order for async listeners.** It does not.
7. **Assuming newly added listeners cannot affect the caller.** Slow or failing synchronous listeners still impact the publisher.
8. **Ignoring exception paths when refactoring direct calls to events.** Callers may experience completely different errors.
9. **Using `@Async void` and expecting errors to reach the controller.** Separate error handling/monitoring is required.
10. **Catching and swallowing listener exceptions to "reduce coupling."** Can hide critical failures.
11. **Holding mutable/lazy entities in events.** Async handlers may see stale state or closed persistence contexts.
12. **Passing `SecurityContext`/MDC as authoritative business data.** Not durable across tasks/processes.
13. **Publishing the same `eventId` twice and expecting Spring to deduplicate.** The framework does not do this.
14. **Creating derived-event loops.** Fan-out can cause infinite recursion or unbounded backlogs.
15. **Lacking Spring integration tests for event types.** Mocking the publisher is not enough.
16. **Counting every `ApplicationEvent` in tests.** Context lifecycle events can skew counts; filter by class.
17. **Failing to separate mandatory effects from supplementary reactions.** Events make success contracts ambiguous.
18. **Treating in-process events as a durable broker.** Restarts can drop pending tasks/callbacks.
19. **Putting too many unstable fields in event schemas.** Consumers become implicitly coupled.
20. **Benchmarking direct vs. event with unequal workloads.** Produces invalid conclusions.
21. **Building one mega-listener for all events.** Loses module independence and tangles types/conditions.
22. **Using events as a command bus without routing/ACKs.** Provides no guarantee of exactly-one consumer.
23. **Ignoring context hierarchy effects.** Parent and child contexts can both receive related events.
24. **Reusing an old `eventId` when creating a new occurrence.** Consumer idempotency may wrongly block valid business operations.

## 18. Practical Decision Matrix

| Scenario | Preference | Reason |
| --- | --- | --- |
| Validate input/permissions before writing | **Direct** | Must return explicit errors, not a past-fact event |
| Mandatory inventory reservation before confirming order | **Direct / orchestrator** | Caller needs to know success |
| Compute tax for API response | **Direct** | Needs return value |
| Add supplementary audit in same app | **Event**, if failure policy fits | Decouples subscriber from source |
| Analytics/metrics that are not success preconditions | **Event** | Easy fan-out extensibility |
| Multiple modules react to `OrderAccepted` | **Event** | Publisher stays unaware of listener list |
| Send email after commit, best-effort acceptable | `@TransactionalEventListener(AFTER_COMMIT)` | Aligns timing with commit, though crash loss is possible |
| Mandatory broker delivery after commit | **Transactional outbox + relay** | Eliminates dual write, durably persists job |
| Caller needs synchronous response to decide next step | **Direct request-response** | Event bus does not aggregate return values |
| Multi-service workflow needing compensation | **Saga/orchestrator + events** | Needs explicit state machine and compensation |
| Replay events to rebuild projections | **Event + durable store** | Plain local events do not retain history |
| Tiny, ultra-high-frequency CPU work | **Measure first; direct is usually simpler** | Avoid dispatch overhead if decoupling is unneeded |

### Quick Selection Rule

If **A must not succeed without step B**, make the relationship to B **explicit** (direct/orchestration). If A has already completed a fact and other modules **are allowed to react independently** under their own SLAs, events help. If events must cross processes or survive crashes, **never rely solely on Spring in-process events**.

## 19. Pre-Refactor Checklist

- [ ] Identified which steps are **business invariants** vs. secondary subscribers.
- [ ] Defined the API's success contract and where exceptions are handled.
- [ ] Checked whether the current Spring multicaster runs synchronously or uses custom async.
- [ ] Not assuming `publishEvent(...)` is a durable queue.
- [ ] Listeners are Spring beans registered for the exact event type.
- [ ] If using `@Order`, limitations with async and failures are understood.
- [ ] If listeners return derived events, loop prevention is in place.
- [ ] Events are named as facts with immutable IDs/metadata in payloads.
- [ ] Listeners read only needed data without retaining mutable entities/requests.
- [ ] Transaction semantics considered: sync pre-commit, `AFTER_COMMIT`, or outbox.
- [ ] External effects are not emitted before business commit when ghost events are forbidden.
- [ ] Events requiring durability have an appropriate outbox/broker/retry/idempotency setup.
- [ ] Tests cover direct actions, publish counts, payloads, listener effects, exceptions, and transaction outcomes.
- [ ] Async tests use latches/futures with timeouts instead of sleeping.
- [ ] No duplicate listeners cause uncontrolled double effects.
- [ ] Metrics and logs include `eventId`, listener name, attempt, and effect ID.
- [ ] Latency and backlog measured when multiple subscribers exist.
- [ ] Security/tenant ID rules enforced at both creation and effect-handling boundaries.

**Conclusion:** **Direct calls** clarify responsibilities and dependencies when a step needs a **mandatory outcome**; **publishing events** broadcasts a fact to multiple subscribers with looser source-code coupling. However, in Spring Framework, **events are still handled synchronously by default** and do not automatically include transaction isolation, retries, or durability. Strong designs typically combine direct orchestration for core workflows, events for supplementary reactions, and a **transactional outbox** when outbound post-commit delivery must be reliable.

## References

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — EventListener API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
