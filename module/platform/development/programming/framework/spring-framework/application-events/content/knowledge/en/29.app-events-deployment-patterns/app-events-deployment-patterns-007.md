# Multiple Independent Listeners for One Event

## 1. Deployment Pattern: One Fact, Multiple Reactions

In Spring Framework Application Events, an application service can publish **a single domain event** when a business action happens, and multiple listeners can subscribe to handle separate responsibilities:

~~~text
PlaceOrder use case
    |
    +-- publishEvent(OrderPlaced #101)     [ONE publish call]
                  |
                  +--> AuditListener        [write audit]
                  |
                  +--> LoyaltyListener      [award loyalty points]
                  |
                  +--> NotificationListener [create notification request]
~~~

This is the **internal fan-out / publish–subscribe** pattern. The publisher simply states "an order was placed"; it does not need to call each listener directly. Each listener focuses on one auxiliary task and can be added or changed without forcing the application service to know the full list of post-processing steps.

An event with three listeners **is not three publications**: there is only one `ApplicationEventPublisher.publishEvent(...)` call, after which Spring locates and invokes the matching listeners.

This guide explains how to structure **responsibly independent** listeners, register them with `@EventListener`, test fan-out with a real `ApplicationContext`, and handle critical limitations: synchronous listener failures, execution ordering, `@Async`, transactions, idempotency, and event durability.

### What Does "Independent" Mean?

Understand **independence at the business design layer**:

- `AuditListener` does not need to call `LoyaltyListener`, and vice versa.
- Each handler depends on the service/repository for **its own responsibility**.
- No handler reads or mutates a shared mutable event object to steer another handler.
- The publisher does not contain an explicit list like `audit(); loyalty(); notify();`—it merely publishes the **fact**.
- A new listener can be added without modifying the publisher's contract, provided the payload already carries the necessary information.

**However, independence of responsibility does not mean infrastructure independence or fault isolation.** With Spring's default synchronous multicaster, listeners still run sequentially on one thread; an exception can prevent subsequent listeners from running. Therefore, distinguish *decoupling* from *failure isolation* and *durable delivery*.

## 2. How Does Spring Perform Fan-Out?

When the application calls:

~~~java
publisher.publishEvent(new OrderPlaced(101L));
~~~

Spring uses `ApplicationEventMulticaster` to find listeners matching the event type. For bean methods annotated with `@EventListener`, Spring registers a listener adapter based on the method signature.

Example of three distinct beans listening to `OrderPlaced`:

~~~java
@Component
class AuditListener {
    @EventListener
    public void on(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}

@Component
class LoyaltyListener {
    @EventListener
    public void on(OrderPlaced event) {
        loyaltyService.awardPoints(event.orderId());
    }
}

@Component
class NotificationListener {
    @EventListener
    public void on(OrderPlaced event) {
        notificationService.enqueue(event.orderId());
    }
}
~~~

This is **illustrative code**: to compile, it requires the service beans, `OrderPlaced` type, and matching imports. Section 5 provides a standalone runnable project registering beans via `@Bean` rather than `@Component` to distinguish every component clearly.

In Spring Framework's default configuration:

1. `SimpleApplicationEventMulticaster` is the standard multicaster.
2. Listeners matching the event and not configured as async are called **synchronously**, usually right on the thread calling `publishEvent(...)`.
3. Each listener receives matching events by type; extending `ApplicationEvent` is unnecessary when publishing plain objects via `publishEvent(Object)`.
4. Listeners can be invoked via `@EventListener` or `ApplicationListener`; avoid accidentally registering the same logic twice.
5. Returning normally from the publisher call **does not guarantee the business transaction committed** if the publisher was invoked inside an unfinished transaction.
6. Application events default to **in-process dispatch**, not a durable broker or an exactly-once mechanism.

### Distinguishing Publish, Dispatch, Execution, and Completion

| Milestone | What Has Happened? | What Has Not Necessarily Happened |
| --- | --- | --- |
| `publishEvent(...)` called | Publisher handed the event to the dispatch mechanism | DB committed; all side effects succeeded |
| Listener adapter selected | Spring matched the listener to the event type | Method body has run |
| Listener invoked | Handler started executing | Handler finished successfully |
| Handler returned | Synchronous handler completed its call | I/O durably saved after another transaction's commit |
| Async task submitted | Executor accepted work per configuration | Worker finished processing |
| Transaction committed | Data in that transaction committed | Post-commit email/broker message delivered |

Separating these milestones is the foundation for writing accurate tests and non-misleading metrics.

## 3. Separating Responsibilities So Listeners Are Truly Independent

One way to organize files/beans:

~~~text
orders/
  OrderApplicationService
  OrderPlaced             (event contract)

audit/
  OrderAuditListener
  AuditRepository

loyalty/
  OrderLoyaltyListener
  LoyaltyLedger

notifications/
  OrderNotificationListener
  NotificationGateway
~~~

Strengths of this design:

- **Single responsibility:** audit knows nothing about loyalty points; loyalty does not send emails.
- **Open/closed:** adding a search-index listener usually requires no changes to the publisher.
- **Testability:** each handler can be unit-tested individually with events and test doubles, alongside integration tests for Spring fan-out.
- **Evolvability:** notifications can later move to a queue/broker without forcing the publisher to call the gateway directly.
- **Reduced temporal coupling:** the publisher avoids accumulating a growing list of auxiliary steps.

Discipline to maintain:

- If `NotificationListener` calls `AuditListener` directly to "wait for audit," the two listeners are no longer independent.
- If one listener mutates the event for another listener to read, ordering and races become hidden dependencies.
- If one listener must run before another for business correctness, it may be an **ordered workflow** rather than independent subscribers.
- If the audit write itself is a legal requirement that must commit atomically with the order, do not casually push it into a best-effort callback out of convenience.

### Events Should Be Minimal, Immutable Facts

Example:

~~~java
public record OrderPlaced(
    java.util.UUID eventId,
    long orderId,
    java.time.Instant occurredAt
) {}
~~~

This is a standalone type definition that can live in its own file with appropriate package/imports. Events should carry data about **what already happened**, with an `eventId` to support deduplication in durable integrations. Avoid passing entire JPA entities, `HttpServletRequest`, access tokens, or mutable object graphs. Each listener can query the data it needs through its own repository/service under granted permissions.

Depending on needs, you can also add `aggregateId`, `causationId`, `correlationId`, or a schema version; not every problem needs all metadata. Do not use `eventId` as a high-cardinality metric tag; keep it in logs/traces with appropriate retention.

## 4. Matching Events and Listeners to the Business Domain

An order-placement workflow involves several kinds of information:

~~~text
Command: PlaceOrder
    |
    v
Order application/domain service
    |
    +-- validate mandatory preconditions
    +-- persist order inside transaction
    |
    +-- publish OrderPlaced (at appropriate boundary)
              |
              +-- create audit projection
              +-- update loyalty projection
              +-- request notification
~~~

Avoid two flawed designs:

**A publisher that knows too much:**

~~~java
// Illustrative anti-pattern.
public void placeOrder(PlaceOrder command) {
    orderRepository.save(...);
    auditService.record(...);
    loyaltyService.award(...);
    notificationService.enqueue(...);
}
~~~

This is not always wrong: if the business requires ordered, synchronous operations that roll back together, direct orchestration can be **more appropriate** than event-driven fan-out. It only becomes problematic when the publisher gets dragged into an ever-growing list of **independent, non-mandatory** auxiliary tasks.

**A single listener owning every responsibility:**

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    auditService.record(event.orderId());
    loyaltyService.award(event.orderId());
    notificationService.enqueue(event.orderId());
}
~~~

If audit fails, loyalty and notification never get called; responsibilities and error policies are mixed into one method. When separation is warranted, use three distinct listeners. However, if all three truly must succeed together or in strict order, keep an explicit workflow instead of splitting just because "multiple listeners sound nice."

## 5. Runnable Java 17+ Example: One Event, Three Independent Listeners

This example uses **Spring Framework 6.2.19**, Java 17+, JUnit Jupiter 5.12.2, and Gradle. No Spring Boot or database is needed.

The three stores here are **in-memory simulations**, each belonging to one responsibility: audit, loyalty, and notification. Listeners never call one another. The program publishes a single `OrderPlaced` event, then inspects each store's state to verify.

### Project Structure

~~~text
fanout-listeners-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/FanOutDemo.java
    └── test/java/demo/FanOutDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'fanout-listeners-demo'
~~~

### build.gradle

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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.FanOutDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/FanOutDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public final class FanOutDemo {

    private FanOutDemo() {}

    // In production, add eventId/occurredAt as needed.
    // This demo uses no database and only proves fan-out.
    public record OrderPlaced(long orderId) {}
    public record StockRecounted(long productId) {}

    // Each store simulates a separate storage/work destination.
    public static final class AuditTrail {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void record(OrderPlaced e) {
            items.add("audit:" + e.orderId());
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class LoyaltyLedger {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void award(OrderPlaced e) {
            items.add("points:" + e.orderId() + ":+10");
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class NotificationQueue {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void enqueue(OrderPlaced e) {
            items.add("notify:" + e.orderId());
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class PlaceOrder {
        private final ApplicationEventPublisher publisher;

        public PlaceOrder(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(long orderId) {
            // In the demo, assume order placement succeeded.
            // Real apps must define the transaction/commit boundary.
            publisher.publishEvent(new OrderPlaced(orderId));
        }
    }

    public static final class AuditListener {
        private final AuditTrail store;

        public AuditListener(AuditTrail store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.record(event);
        }
    }

    public static final class LoyaltyListener {
        private final LoyaltyLedger store;

        public LoyaltyListener(LoyaltyLedger store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.award(event);
        }
    }

    public static final class NotificationListener {
        private final NotificationQueue store;

        public NotificationListener(NotificationQueue store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.enqueue(event);
        }
    }

    // Explicitly register exactly three listener beans.
    // DO NOT enable @ComponentScan to avoid duplicate registration.
    @Configuration
    public static class FanOutConfig {

        @Bean
        AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        LoyaltyLedger loyaltyLedger() {
            return new LoyaltyLedger();
        }

        @Bean
        NotificationQueue notificationQueue() {
            return new NotificationQueue();
        }

        @Bean
        PlaceOrder placeOrder(
                ApplicationEventPublisher publisher) {
            return new PlaceOrder(publisher);
        }

        @Bean
        AuditListener auditListener(AuditTrail store) {
            return new AuditListener(store);
        }

        @Bean
        LoyaltyListener loyaltyListener(LoyaltyLedger store) {
            return new LoyaltyListener(store);
        }

        @Bean
        NotificationListener notificationListener(
                NotificationQueue store) {
            return new NotificationListener(store);
        }
    }

    // Separate bean group for failure examples in unit/integration tests.
    public static final class FailureLog {
        private final List<String> calls =
            new CopyOnWriteArrayList<>();

        public void add(String value) {
            calls.add(value);
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    public static final class FailingListener {
        private final FailureLog log;

        public FailingListener(FailureLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-10)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("first-throws");
            throw new IllegalStateException("listener failed");
        }
    }

    public static final class LaterListener {
        private final FailureLog log;

        public LaterListener(FailureLog log) {
            this.log = log;
        }

        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("later");
        }
    }

    @Configuration
    public static class FailureConfig {

        @Bean
        FailureLog failureLog() {
            return new FailureLog();
        }

        @Bean
        FailingListener failingListener(FailureLog log) {
            return new FailingListener(log);
        }

        @Bean
        LaterListener laterListener(FailureLog log) {
            return new LaterListener(log);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutConfig.class)) {

            ctx.getBean(PlaceOrder.class).place(101L);

            // Do not rely on listener order:
            // read projections only after synchronous publish finishes.
            System.out.println("published=1");
            System.out.println(
                "audit=" +
                ctx.getBean(AuditTrail.class).snapshot());
            System.out.println(
                "loyalty=" +
                ctx.getBean(LoyaltyLedger.class).snapshot());
            System.out.println(
                "notification=" +
                ctx.getBean(NotificationQueue.class).snapshot());
        }
    }
}
~~~

### Run and Verify

~~~bash
gradle run --quiet
# Linux/macOS with wrapper: ./gradlew run --quiet
# Windows with wrapper: gradlew.bat run --quiet
~~~

Lines printed by the program itself:

~~~text
published=1
audit=[audit:101]
loyalty=[points:101:+10]
notification=[notify:101]
~~~

Read the output accurately:

1. `PlaceOrder.place(101L)` calls `publishEvent(...)` **only once**.
2. Spring finds three `@EventListener` methods accepting `OrderPlaced` in `FanOutConfig`.
3. Each listener updates **its own store** and never calls another listener.
4. With the default synchronous `SimpleApplicationEventMulticaster`, by the time `place(...)` returns, all three listeners have completed their simulated work.
5. The program prints store snapshots in a fixed order because **`main` orders the `println` statements**, not because Spring guarantees listener order.
6. `CopyOnWriteArrayList` allows safe reading of collectors in the demo; this is not persistence and does not replace a database, message queue, or transaction.

**Why not annotate the three main listeners with `@Order`?** Because the simulated business logic does not require audit, loyalty, and notification to run in a specific order. Adding `@Order` just to make tests pass can hide design dependencies. Section 6 uses `@Order` in a **separate** test solely to demonstrate synchronous multicaster exception propagation unambiguously.

## 6. Testing with JUnit 5 and a Real Spring ApplicationContext

Create `src/test/java/demo/FanOutDemoTest.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FanOutDemoTest {

    @Test
    void oneEventReachesAllThreeIndependentListeners() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            ctx.getBean(FanOutDemo.PlaceOrder.class).place(101L);

            assertEquals(
                List.of("audit:101"),
                ctx.getBean(FanOutDemo.AuditTrail.class).snapshot());

            assertEquals(
                List.of("points:101:+10"),
                ctx.getBean(FanOutDemo.LoyaltyLedger.class).snapshot());

            assertEquals(
                List.of("notify:101"),
                ctx.getBean(
                    FanOutDemo.NotificationQueue.class).snapshot());
        }
    }

    @Test
    void twoPublicationsReachEachListenerOncePerEvent() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            var publisher = ctx.getBean(FanOutDemo.PlaceOrder.class);
            publisher.place(101L);
            publisher.place(102L);

            assertEquals(
                List.of("audit:101", "audit:102"),
                ctx.getBean(FanOutDemo.AuditTrail.class).snapshot());

            assertEquals(
                List.of("points:101:+10", "points:102:+10"),
                ctx.getBean(FanOutDemo.LoyaltyLedger.class).snapshot());

            assertEquals(
                List.of("notify:101", "notify:102"),
                ctx.getBean(
                    FanOutDemo.NotificationQueue.class).snapshot());
        }
    }

    @Test
    void anotherEventTypeDoesNotTriggerOrderListeners() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            ctx.publishEvent(new FanOutDemo.StockRecounted(99L));

            assertTrue(
                ctx.getBean(FanOutDemo.AuditTrail.class)
                    .snapshot().isEmpty());
            assertTrue(
                ctx.getBean(FanOutDemo.LoyaltyLedger.class)
                    .snapshot().isEmpty());
            assertTrue(
                ctx.getBean(FanOutDemo.NotificationQueue.class)
                    .snapshot().isEmpty());
        }
    }

    @Test
    void oneFailingSyncListenerCanStopLaterListener() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FailureConfig.class)) {

            assertThrows(
                IllegalStateException.class,
                () -> ctx.publishEvent(
                    new FanOutDemo.OrderPlaced(103L))
            );

            // @Order(-10) listener throws before @Order(10).
            // Default multicaster has no ErrorHandler configured.
            assertEquals(
                List.of("first-throws"),
                ctx.getBean(FanOutDemo.FailureLog.class).snapshot()
            );
        }
    }
}
~~~

Run:

~~~bash
gradle test
# Linux/macOS with wrapper: ./gradlew test
# Windows with wrapper: gradlew.bat test
~~~

Expect **four passing tests** when run with the example's dependencies and configuration:

- **Test 1:** one publication is received by all three listeners, each recording one result.
- **Test 2:** two publications cause each listener to receive two events. Do not sum the three listeners' results and call it "six events published."
- **Test 3:** listeners filter by event type. `StockRecounted` does not match `OrderPlaced`, so all three order stores remain empty.
- **Test 4:** `FailingListener` with `@Order(-10)` is called before `LaterListener` with `@Order(10)`. The first throws `IllegalStateException`; the default synchronous multicaster has no `ErrorHandler`, so the exception propagates to the publisher and the later listener **does not run**.

**Key point:** successful fan-out does not prove *fault tolerance*. The fourth test deliberately shows that three separate-bean listeners can still be affected by a single exception on the synchronous dispatch path. When changing multicaster configuration or `@Async`, adjust assertions to match the new contract.

Do not mock `ApplicationEventPublisher` and conclude fan-out works: mocking only proves `publishEvent` was called, not that listener dispatch occurs. The tests above use a real Spring `ApplicationContext` to verify registration and routing.

## 7. Handling Listener Failures

With the default synchronous `SimpleApplicationEventMulticaster`, **one listener throwing an unchecked exception can halt dispatch and propagate the error to the publisher thread**.

~~~text
publishEvent(OrderPlaced)
    |
    +--> AuditListener: OK
    |
    +--> LoyaltyListener: throws
    |
    +--> NotificationListener: may not be invoked
    |
    +--> publisher receives exception
~~~

The order in the diagram is **illustrative only**; without `@Order`, never treat that position as a contract. Inside a `@Transactional` boundary, a synchronous exception escaping the service can trigger rollback per transaction rules; external side effects outside the transaction (emails, HTTP APIs) **are not automatically undone**.

### Handling Strategies by Criticality

| Case | Design Direction |
| --- | --- |
| A listener checks a mandatory invariant required for transaction commit | Consider handling directly in the use case/domain or same transaction, not as an independent post-step |
| An audit listener must commit atomically with the order | Write in the same transaction or use domain/outbox design matching requirements |
| Notification is strictly best-effort | Can decouple via async + monitoring, with an explicit task-loss policy |
| Notification must not be lost when order commits | Transactional outbox + worker with retries/idempotency |
| One failing handler must not block others yet errors must be surfaced | Choose appropriate error handling, logs/metrics/alerts, and retries |
| Dependency "run B only after A finishes" | Use explicit orchestration/workflow, not accidental order dependencies |

You can configure an `ErrorHandler` on `SimpleApplicationEventMulticaster` to handle exceptions and let remaining listeners continue, yet **logging and suppressing does not turn a failed task into a success**:

~~~java
// Illustrative config sample; not part of the Section 5 project.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster() {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(
        TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER
    );
    return multicaster;
}
~~~

This snippet requires imports for `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `TaskUtils`, `@Bean`, and proper Spring configuration. When suppressing, the caller may not see an exception, but failures must still be monitored and recovered according to the business contract. When downstream side effects are critical, do not treat suppression as "solving" the error.

## 8. @Order Creates Neither Independence Nor Durable Business Sequencing

Spring supports `@Order` to prioritize listener **invocation**. Lower values have higher priority:

~~~java
@EventListener
@Order(-10)
void first(OrderPlaced e) { ... }

@EventListener
@Order(10)
void second(OrderPlaced e) { ... }
~~~

For the same event, synchronous dispatch, and a multicaster honoring order, `first` is called before `second`. However:

- At the same `@Order` value, do not rely on a stable order.
- `@Order` does not guarantee one listener will **commit** successfully before another.
- With `@Async` or an executor, dispatch priority **does not guarantee completion order**.
- A listener can emit nested events, producing an execution order different from "finish all listeners for A before starting B."
- Parent/child Spring contexts have separate multicasters; a single `@Order` value does not enforce global order across contexts.

If B genuinely needs A's outcome, consider an orchestrator invoking A then B with explicit contracts and transactions, or a workflow publishing the **next** event once A confirms completion. Never rely on "it usually runs first in dev."

## 9. Does Running a Listener @Async Make It More Independent?

`@Async @EventListener` (with `@EnableAsync` and a proper `TaskExecutor`) moves the listener body to a worker thread:

~~~java
// Illustration requiring configured bean and executor.
@Async("notificationExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.enqueue(event.orderId());
}
~~~

What changes:

- The publisher generally **does not wait for the handler to finish**.
- An exception thrown in the worker **does not automatically propagate back** to the `publishEvent` caller. For `void` methods, configure `AsyncUncaughtExceptionHandler` or dedicated monitoring.
- Thread-bound contexts such as request attributes, security, MDC/trace, or imperative transactions **do not automatically propagate completely**.
- Publishing can return before the worker executes, creating races with transaction commit and database visibility.
- A local thread pool is not a durable queue; a process crash/restart can lose pending tasks.

Thus `@Async` can **reduce latency impact** between listeners, but does not automatically provide complete fault isolation, exactly-once semantics, or durability. Executors can hit capacity and reject tasks; tasks can fail; thread pools can saturate.

If a callback must wait for an order to commit before running, use a transaction-bound listener or outbox instead of `@Async @EventListener` directly.

## 10. Each Listener Should Choose the Right Transaction Boundary

A service may publish an event while still inside transaction `T1`:

~~~text
BEGIN T1
    INSERT orders(...)
    publishEvent(OrderPlaced)
    ...
COMMIT / ROLLBACK T1
~~~

Three plain `@EventListener` methods run synchronously upon publish, **before knowing whether T1 will commit**. If a listener sends an email or calls an external service right then, T1 can still roll back afterward.

When reacting **only after commit** is required:

~~~java
// Illustrative snippet requiring Spring-managed bean and real transaction.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    notificationService.enqueue(event.orderId());
}
~~~

Key points to remember:

1. `@TransactionalEventListener` defaults to `AFTER_COMMIT`, which can be declared explicitly for clarity.
2. When no eligible transaction exists, `fallbackExecution=false` by default, so the callback **does not run**.
3. When the transaction rolls back, `AFTER_COMMIT` listeners do not run. Distinguish `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
4. An exception in a post-commit callback **cannot undo T1's commit**. In standard imperative Spring, exceptions from `afterCompletion` are normally logged rather than propagated to the caller.
5. A listener writing to the DB after commit should open an appropriate new transaction (e.g., a separate service `@Transactional(propagation=REQUIRES_NEW)` when fitting the use case), rather than assuming it can reuse T1 while it is cleaning up.
6. Reactive transactions use Reactor Context; when needed, use `TransactionalEventPublisher` with the proper reactive mechanism.
7. Starting after commit **does not mean unlosable**. The process can die between commit and callback/enqueue.

**Multiple listeners and transactions are not necessarily a single atomic unit:** if audit requires sharing T1 while notification only needs after-T1, those two listeners have **different consistency contracts**. Design and test per task rather than forcing every listener on "one event" into the same phase.

## 11. When Events Are Critical, Use an Outbox and Idempotency

Internal Spring application events are not a durable message queue. A use case that commits an order and relies on an after-commit listener to enqueue work in RAM still has a gap:

~~~text
BEGIN T1
  insert order
COMMIT T1
    |
    +--- process crashes right before listener enqueues
             -> order exists
             -> auxiliary work may be lost
~~~

For tasks that **must never be missed**, use a mechanism like the **transactional outbox**:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(event_id, event_type, aggregate_id, payload)
COMMIT T1

Outbox worker:
  claim pending rows
  publish to broker / invoke consumer
  retry with backoff on transient failure
  record success/ACK
  DLQ/alert for poison messages
~~~

This is an architectural model, not copy-paste production SQL. Writing domain data + outbox must share the same transaction, whereas the worker dispatching externally can fail or retry.

When one event has three consumers, each consumer may need **its own processing state**, such as a unique key `(consumer_name, event_id)`. Audit finishing does not prove loyalty finished; nor should an event be marked globally `DONE` before all mandatory tasks succeed per contract.

### Per-Listener Idempotency

~~~text
OrderPlaced eventId=E1
    |
    +--> AuditConsumer        processed E1: yes
    +--> LoyaltyConsumer      processed E1: yes
    +--> NotificationConsumer processed E1: no -> retry
~~~

On redelivery of E1, Audit and Loyalty can skip because they already processed E1; Notification processes independently. This is **at-least-once + idempotency**, not an exactly-once guarantee across every system.

**Do not rely on generating a new `eventId` on each retry** if it is still the same business event. Keep identity stable across retries. When sending emails or calling external APIs, deduplication must account for the destination's contract; timeouts can occur after the destination already succeeded.

## 12. Operational Observability for Multi-Listener Events

Do not monitor only "publisher succeeded" and assume all three handlers succeeded. Track metrics for each stage:

| Logical Metric | Meaning |
| --- | --- |
| `event.publish.attempts` | Number of publish attempts by the app |
| `event.listener.invocations` | Actual invocations per listener |
| `event.listener.results{listener,outcome}` | Success/failure completions per listener |
| `event.listener.duration` | Duration of each handler |
| `event.retry.total` | Independent retries per consumer |
| `event.pending.count` | Pending jobs / outbox backlog |
| `event.pending.oldest.age` | Latency/age of oldest unprocessed work |

These names are **Micrometer instrumentation suggestions**, not metrics Spring generates automatically.

Example of one event reaching three listeners:

~~~text
publish attempts = 1
audit invocations = 1
loyalty invocations = 1
notification invocations = 1
~~~

Do not add these up into "3 events published." If notification fails, the processing metric may show `notification error=1` even though `publish attempts=1`. Async listeners may finish later, so include correlation/event IDs in structured logs and traces to link steps.

**Avoid high-cardinality metric tags:** `eventId`, `orderId`, `correlationId`, and `userId` should not be per-event metric labels; keep them in properly access-controlled logs/traces. Tags like `listener=order_audit`, `event_type=order_placed`, and `outcome=success/error` are good bounded values.

## 13. When to Use and When Not to Use This Pattern

### Good Fit

- One business fact triggers multiple independent post-processing reactions: audit, cache invalidation, metrics, notifications.
- Most listeners can be added or removed without altering the main use case's core goal.
- Clear contracts exist for when events are published, payload contents, and error handling.
- When durability is required, a proper bridge/outbox is used rather than mistaking local application events for a broker.

### Consider Another Model

- Steps A → B → C **must run in strict order** or depend on each other's outputs.
- All steps must commit atomically as a single transaction.
- The use case needs results returned from handlers to decide the HTTP response.
- A distributed workflow with retries, compensation, or saga state is needed beyond a local event dispatcher.
- Listeners require vastly different access privileges: separate integration events with tailored contracts may be better than broadcasting a sensitive DTO.

Do not choose event-driven fan-out merely to avoid a few direct method calls. Choose it when **reducing coupling and managing independent side effects** brings real value.

## 14. Common Mistakes and Fixes

**Mistake 1 — "Three listeners mean three events."** One publication can trigger three handlers. Distinguish publication count from invocation count.

**Mistake 2 — Listeners calling one another.** If handler B needs A's outcome, use an explicit orchestrator/workflow instead of hiding dependencies among event subscribers.

**Mistake 3 — Assuming listeners cannot disrupt each other.** The default sync multicaster stops when a listener throws; test `ErrorHandler`, `@Async`, and transaction policies.

**Mistake 4 — Relying on bean registration order.** Never rely on `@Bean` placement, component-scan order, or class names for invocation order. Use `@Order` when needed, without inferring async completion order.

**Mistake 5 — Publishing too early.** `@Async @EventListener` may read the DB before commit, or send emails for a transaction that later rolls back. Consider `AFTER_COMMIT` or an outbox.

**Mistake 6 — Treating `AFTER_COMMIT` as a durable queue.** It only controls callback timing, not crash windows. Mandatory tasks require durable channels.

**Mistake 7 — Putting entities or request secrets in payloads.** Events should be immutable and minimal; do not expose raw credentials or `HttpServletRequest` to multiple listeners.

**Mistake 8 — Sharing one mutable object as state across listeners.** Causes races, order dependencies, and brittle tests. Pass immutable events and let each consumer own its projection.

**Mistake 9 — Ignoring duplicates and retries.** With brokers/outboxes, events can be redelivered; each consumer must be idempotent per event ID and use case.

**Mistake 10 — Testing by calling the three methods manually.** That does not verify annotation registration or type routing. Use a real Spring `ApplicationContext` for fan-out integration tests.

**Mistake 11 — Conflating sync and async listeners.** `publishEvent` returning may only mean a task was submitted. Verify completion via signals/futures rather than `Thread.sleep()`.

**Mistake 12 — Registering the same listener twice.** Combining `@Bean` with accidental `@ComponentScan` or adding a separate `ApplicationListener` adapter can duplicate handling. Pick one registration mechanism per handler and assert invocation counts.

## 15. Implementation and Testing Checklist

- [ ] Event represents a clear business fact with a minimal, immutable payload.
- [ ] A single publisher calls `publishEvent` at the right business/transaction boundary.
- [ ] Each listener owns a clear responsibility and does not call other listeners to create hidden dependencies.
- [ ] Sync/async/transaction-bound mode is chosen per task based on semantics rather than habit.
- [ ] Error policy is defined: propagate, suppress + alert, retry, or outbox depending on the use case.
- [ ] `@Order` is not treated as a commit or completion guarantee.
- [ ] If after-commit is required, tested with a real transaction; outside a transaction it does not run by default.
- [ ] If durable delivery is required, outbox/broker implements ACKs, retries, and per-consumer idempotency.
- [ ] Integration test publishes **one event** and asserts each listener handled it exactly once.
- [ ] Tested that unrelated event types do not trigger these handlers.
- [ ] Tested listener failure behavior under the actual multicaster configuration.
- [ ] For async, uses latches/queues with timeouts instead of sleeps.
- [ ] Metrics count publications separately from per-listener invocations/completions.
- [ ] Payloads and log tags avoid secrets, unnecessary PII, and high-cardinality identifiers.
- [ ] Behavior of nested events and parent/child contexts is verified if the topology uses them.

### Key Takeaway

~~~text
One call to publishEvent(OrderPlaced)
             |
             +--> AuditListener
             +--> LoyaltyListener
             +--> NotificationListener

Three responsibly independent handlers
DO NOT equal three publications.

Default multicaster: synchronous on caller thread.
One listener's error can block subsequent listeners.

@Order      : invocation priority, not async completion guarantee.
@Async      : switches threads, not durable delivery.
AFTER_COMMIT: runs only on commit, does not survive crash windows.
Outbox      : use when reliable recovery and retries are needed.

True independence = clear responsibility boundaries
                  + clear consistency, error, and retry contracts.
~~~

## References

- [Spring Framework — ApplicationContext Events, Asynchronous Execution, and Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
