# Ordering Multiple Listeners in Spring Framework Application Events

## 1. Objectives and Context

A single business event may interest multiple parts of a Spring application. When `OrderPlaced` is published, the system might write an audit log, update a projection, record metrics, and prepare a notification. All of these listeners are valid, yet **which order they are invoked in** must be properly understood, especially when a step throws an error, a listener has `@Async`, or the application uses a custom executor.

Example publish call:

```java
applicationEventPublisher.publishEvent(new OrderPlaced("O-100"));
```

This is an illustrative line; the `OrderPlaced` type and publisher must be defined by the application. In Spring Framework 6.2, the ordering options are:

- Place `@Order` on each `@EventListener` method.
- Use `Ordered.getOrder()` on an object implementing `ApplicationListener<E>`.
- Leave listeners without declared order to receive low default precedence.

**Rule:** Spring prioritizes **lower order numbers**. With the default synchronous multicaster, a listener with order 10 runs before order 20. However, `@Order` must never be mistaken for a transaction, a durable queue, a retry mechanism, or a guarantee that a listener completes before another asynchronous task starts.

This lesson is a practice summary on Spring Application Events: explaining the dispatch mechanism, runnable Java 17 code, JUnit 5 tests on a Spring context, async/transaction/error scenarios, and criteria for when not to chain work with events.

## 2. Ordering Applies Within a Single Event Publication

When `ApplicationEventPublisher.publishEvent(event)` is called, the `ApplicationEventMulticaster` in the context locates listeners that accept that event type and dispatches the event.

With the default `SimpleApplicationEventMulticaster`:

```text
OrderService
  |
  +-- publishEvent(OrderPlaced)
         |
         v
     find listeners for OrderPlaced
         |
         v
     sort by order
         |
         +-- Audit @Order(10)
         +-- Projection Ordered=20
         +-- Metrics @Order(30)
         +-- Observer without @Order
         |
         v
     publishEvent returns
```

Most listeners are invoked **directly on the publisher's thread**, in the same call stack. When everything is synchronous and error-free, `Audit` finishes, followed by `Projection`, `Metrics`, and `Observer`. A listener that takes 2 seconds can make `publishEvent` take at least 2 seconds.

### 2.1. Ordering Only Compares Listeners That Match the Event

These two listeners do not form a global order:

```java
@EventListener
@Order(10)
public void onOrderPlaced(OrderPlaced event) { /* ... */ }

@EventListener
@Order(20)
public void onPaymentCaptured(PaymentCaptured event) { /* ... */ }
```

This is an illustrative snippet inside a Spring bean, with two event classes to be declared. When `OrderPlaced` is published, `onPaymentCaptured` is not invoked just because it has order 20. Spring filters by event type/generic type and condition before dispatching.

### 2.2. Do Not Infer Ordering Between Two Publisher Threads

Two threads may publish concurrently:

```text
Thread A: OrderPlaced(O-100)
Thread B: OrderPlaced(O-101)
```

On thread A, callbacks for O-100 are prioritized by order. On thread B, callbacks for O-101 are as well. However, the two sequences can **interleave** at the application level; Spring does not use `@Order` to lock all publishing across threads.

If both events must modify the same aggregate, what matters is transaction isolation/versioning and business invariants, not just order numbers.

## 3. `@Order` on `@EventListener`

The most common and readable approach:

```java
@Component
public class OrderEventHandlers {

    @EventListener
    @Order(10)
    public void audit(OrderPlaced event) {
        // Record the fact.
    }

    @EventListener
    @Order(20)
    public void updateProjection(OrderPlaced event) {
        // Update the projection.
    }

    @EventListener
    @Order(30)
    public void collectMetrics(OrderPlaced event) {
        // Metrics.
    }
}
```

The snippet above is **illustrative**, not a standalone runnable class: it requires `@Component`, `@EventListener`, `@Order`, and `OrderPlaced`.

| Order value | Interpretation | Notes |
| --- | --- | --- |
| `@Order(-10)` | Before 0, 10, 20 | Negative numbers are valid |
| `@Order(0)` | Before 10 | Does not mean run at startup |
| `@Order(10)` | Before 20 | Higher priority |
| `@Order(20)` | After 10 | Lower priority |
| No `@Order` declared | Low default, typically corresponding to `Ordered.LOWEST_PRECEDENCE` | Do not rely on ordering among default-ordered listeners |
| `@Order(Ordered.HIGHEST_PRECEDENCE)` | Very high level | Avoid overusing as it easily causes priority contention |

**Equal order has no guaranteed stable ordering by contract.** If two methods both have `@Order(10)`, do not assume the method earlier in the file will run before the later one. When a before/after relationship matters, use distinct values and write tests.

### 3.1. Leave Gaps Between Numbers

A convention:

```text
10  audit
20  read-model projection
30  metrics
40  optional notification
```

To insert a step between audit and projection, you can pick 15. This is an application convention, not a built-in Spring enum or phase.

### 3.2. Where to Place the Annotation?

For `@EventListener` methods, placing `@Order` **directly on the method itself** is the clearest practice:

```java
@EventListener
@Order(20)
public void handle(OrderPlaced event) {
    // ...
}
```

`@Order` on a class or bean factory method also has meaning in other ordering contexts such as collection injection; do not assume it accurately describes the order of every `@EventListener` method inside the class. Prefer method-level annotations and integration tests.

Important: `@Order` **does not determine bean initialization order**. The dependency graph, constructor injection, and `@DependsOn` are separate concerns. Adding `@Order(10)` does not guarantee one bean is created before a bean with `@Order(20)`.

## 4. `Ordered` for the `ApplicationListener` Interface

When implementing `ApplicationListener<E>` directly, you can supply order via `org.springframework.core.Ordered`:

```java
public class ProjectionListener
        implements ApplicationListener<OrderPlaced>, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        // Handle the event.
    }
}
```

The snippet above illustrates a class without imports or business code. With Spring Framework 6.2, when implementing `ApplicationListener<E>`, `E` is an appropriate subtype of `ApplicationEvent`; the complete Maven example below uses `OrderPlaced extends ApplicationEvent`.

Compared to `@Order`, `Ordered.getOrder()` allows per-instance configuration:

```java
private final int configuredOrder;

@Override
public int getOrder() {
    return configuredOrder;
}
```

Even so, do not continuously mutate `getOrder()` after the context is active and expect listeners to re-sort immediately. The multicaster may cache matching listener metadata. Treat order as **stable configuration for the lifetime of the application context**.

### 4.1. `PriorityOrdered`

Spring also has `PriorityOrdered`, specifically representing a higher-priority group relative to regular `Ordered` objects. For most domain listeners, it is unnecessary. When mixing `PriorityOrdered`, `Ordered`, and annotation-based ordering, test on your exact Spring version because priority tiers and comparator rules can differ from assuming "pure numeric comparison".

Usually, `@EventListener @Order(10/20/30)` is clear enough to review. Do not turn every business callback into a highest-priority infrastructure component.

## 5. Runnable Example: Four Listeners, Two Ways of Declaring Order

The example uses:
- Java 17+ and Maven.
- Spring Framework `spring-context:6.2.12`.
- JUnit Jupiter + `spring-test` for integration tests.
- An in-memory recorder tracking callback order.

Four listeners for the same `OrderPlaced`:
1. `AuditListener`: `@EventListener @Order(10)`.
2. `ProjectionListener`: implements `ApplicationListener<OrderPlaced>, Ordered`, order 20.
3. `MetricsListener`: `@EventListener @Order(30)`.
4. `ObserverListener`: `@EventListener` without `@Order`, default precedence.

### 5.1. Structure

```text
listener-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/OrderingEventsDemo.java
    └── test/java/demo/OrderingEventsDemoTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>listener-order-demo</artifactId>
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
            <artifactId>spring-test</artifactId>
            <version>6.2.12</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OrderingEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/java/demo/OrderingEventsDemo.java

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public final class OrderingEventsDemo {

    public static final class OrderPlaced extends ApplicationEvent {
        private final String orderId;

        public OrderPlaced(String orderId) {
            super("order-service");
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            if (orderId.isBlank()) {
                throw new IllegalArgumentException("blank order ID");
            }
        }

        public String orderId() {
            return orderId;
        }
    }

    // Only for synchronous, single-threaded demo use.
    public static final class CallRecorder {
        private final List<String> calls = new ArrayList<>();

        public void add(String text) {
            calls.add(text);
        }

        public void clear() {
            calls.clear();
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    public static final class AuditListener {
        private final CallRecorder recorder;

        public AuditListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        @Order(10)
        public void on(OrderPlaced event) {
            recorder.add("AUDIT:" + event.orderId());
        }
    }

    public static final class ProjectionListener
            implements ApplicationListener<OrderPlaced>, Ordered {

        private final CallRecorder recorder;

        public ProjectionListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            recorder.add("PROJECTION:" + event.orderId());
        }
    }

    public static final class MetricsListener {
        private final CallRecorder recorder;

        public MetricsListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        @Order(30)
        public void on(OrderPlaced event) {
            recorder.add("METRICS:" + event.orderId());
        }
    }

    public static final class ObserverListener {
        private final CallRecorder recorder;

        public ObserverListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        public void on(OrderPlaced event) {
            recorder.add("OBSERVER:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        CallRecorder callRecorder() {
            return new CallRecorder();
        }

        @Bean
        AuditListener auditListener(CallRecorder recorder) {
            return new AuditListener(recorder);
        }

        @Bean
        ProjectionListener projectionListener(CallRecorder recorder) {
            return new ProjectionListener(recorder);
        }

        @Bean
        MetricsListener metricsListener(CallRecorder recorder) {
            return new MetricsListener(recorder);
        }

        @Bean
        ObserverListener observerListener(CallRecorder recorder) {
            return new ObserverListener(recorder);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(new OrderPlaced("O-100"));

            List<String> actual =
                    context.getBean(CallRecorder.class).snapshot();

            List<String> expected = List.of(
                    "AUDIT:O-100",
                    "PROJECTION:O-100",
                    "METRICS:O-100",
                    "OBSERVER:O-100");

            System.out.println(
                    "CALL_ORDER=" + String.join(" > ", actual));
            System.out.println("ORDER_OK=" + actual.equals(expected));
        }
    }
}
```

### 5.4. Run Command and Output

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Two lines explicitly printed by the program, ignoring Maven/framework logs:

```text
CALL_ORDER=AUDIT:O-100 > PROJECTION:O-100 > METRICS:O-100 > OBSERVER:O-100
ORDER_OK=true
```

#### Why Is the Result Correct?

1. `AnnotationConfigApplicationContext` creates the beans declared by `Config`.
2. `AuditListener`, `MetricsListener`, and `ObserverListener` have `@EventListener`; Spring registers them via the listener-method processing infrastructure.
3. `ProjectionListener` is a real `ApplicationListener<OrderPlaced>` and provides `Ordered.getOrder() = 20`.
4. `OrderPlaced` extends `ApplicationEvent`; in this lesson its constructor accepts an order ID and sets the source to the constant string `"order-service"`.
5. The multicaster finds all matching listeners and sorts them by order: 10, 20, 30, default.
6. By default without an async executor configured, callbacks run synchronously on the publisher thread.
7. The recorder simply appends labels; once `publishEvent` returns, all four labels are present.
8. The list matches the expected order so `ORDER_OK=true`. The example includes no DB, broker, or network, so it does not prove durability.

Because the recorder uses a plain `ArrayList`, do not reuse this class as-is in multi-threaded tests. When multiple publisher threads exist, use a thread-safe recorder with event ID filtering and completion waiting.

## 6. Writing JUnit Integration Tests for Listener Order

Testing the real order must run inside a **real Spring `ApplicationContext`**, so Spring registers `@EventListener` and `ApplicationListener` itself. Simply instantiating four listeners with `new` and calling them manually does not test multicaster ordering.

### 6.1. src/test/java/demo/OrderingEventsDemoTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import demo.OrderingEventsDemo.CallRecorder;
import demo.OrderingEventsDemo.OrderPlaced;

@SpringJUnitConfig(OrderingEventsDemo.Config.class)
class OrderingEventsDemoTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    CallRecorder recorder;

    @BeforeEach
    void clearRecorder() {
        recorder.clear();
    }

    @Test
    void usesOrderTenTwentyThirtyThenDefault() {
        publisher.publishEvent(new OrderPlaced("O-200"));

        assertEquals(List.of(
                "AUDIT:O-200",
                "PROJECTION:O-200",
                "METRICS:O-200",
                "OBSERVER:O-200"),
                recorder.snapshot());
    }

    @Test
    void repeatsOrderingForTwoSequentialPublishes() {
        publisher.publishEvent(new OrderPlaced("O-201"));
        publisher.publishEvent(new OrderPlaced("O-202"));

        assertEquals(List.of(
                "AUDIT:O-201",
                "PROJECTION:O-201",
                "METRICS:O-201",
                "OBSERVER:O-201",
                "AUDIT:O-202",
                "PROJECTION:O-202",
                "METRICS:O-202",
                "OBSERVER:O-202"),
                recorder.snapshot());
    }

    @Test
    void ignoresUnrelatedEventType() {
        publisher.publishEvent("not-an-OrderPlaced");
        assertEquals(List.of(), recorder.snapshot());
    }
}
```

Run:

```bash
mvn test
```

Once dependencies are downloaded and JDK 17+ is used, all **3 test methods** should pass. Surefire will report numbers equivalent to:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Other log lines may appear depending on Maven/environment. The main program can also be run afterward using `mvn -q compile exec:java`.

### 6.2. Why Not Use Only `@RecordApplicationEvents`?

`@RecordApplicationEvents` and `ApplicationEvents.stream(...)` are great tools for asserting **that events were published**. In this lesson we want to verify **callback execution order**, so the recorder is placed directly inside the listeners to report actual execution order.

The three tests have distinct goals:
- The first test checks all 4 callbacks for one event.
- The second test checks synchronous dispatch behavior across two sequential publications.
- The third test ensures `OrderPlaced`-typed listeners are not invoked for a `String` payload.

### 6.3. Why Clear Before Each Test?

The recorder is a Spring singleton bean in the test context. JUnit can reuse the application context across multiple test methods. Without clearing, labels from a previous test would remain, making assertions depend on test execution order. `@BeforeEach` resets the recorder before every test.

If using a recorder in a real application, do not let a singleton keep an unbounded event history in an `ArrayList`; this is strictly a test probe.

### 6.4. Checking Order Differs from Checking Side Effects

The assertions above **only prove the order in which listeners ran** under synchronous configuration. They do not prove:
- The DB committed.
- An email was sent.
- Kafka acknowledged.
- Any transaction rolled back.
- Retries/redelivery did not happen.
- Remote services received messages in order.

Those items must be tested at their respective boundaries.

## 7. `@Async` Makes Completion Order Non-Deterministic

Suppose:

```java
@Async("eventExecutor")
@EventListener
@Order(10)
public void sendEmail(OrderPlaced event) {
    emailClient.send(event);
}

@Async("eventExecutor")
@EventListener
@Order(20)
public void refreshCache(OrderPlaced event) {
    cacheClient.update(event);
}
```

This is a snippet requiring `@EnableAsync`, an executor bean, client methods, and appropriate Spring configuration; it is not part of the Maven demo.

On the publisher thread, listener proxies have priority order: `sendEmail` before `refreshCache`. However, each proxy may **only submit a task**. If email is slow and cache is fast, cache may finish before email:

```text
Publisher            Worker-1                Worker-2
--------             --------                --------
@Order(10) submit --> sendEmail starts
@Order(20) submit -------------------------> refreshCache starts
publish returns      sendEmail still busy     refreshCache finishes
                     sendEmail finishes
```

**Distinguish:**
- Listener selection order: which listeners match.
- Invocation/submission order: which callback/proxy is called first.
- Start order: which task starts first on the executor.
- Completion order: which task finishes first.
- Business effect order: which remote side effect is actually committed/acknowledged first.

`@Order` only assists the event-dispatch ordering layer. It does not place a semaphore between two executor tasks or open a shared transaction.

### 7.1. Custom Multicaster Task Executor

Spring allows replacing the default multicaster with a bean named `applicationEventMulticaster`:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") Executor executor) {
    var result = new SimpleApplicationEventMulticaster();
    result.setTaskExecutor(executor);
    return result;
}
```

This is a configuration snippet requiring Spring imports and an executor bean. With a task executor, the multicaster typically submits listeners that support asynchronous execution. Some listeners, such as transaction-synchronized listeners, report that they do not support async dispatch via `ApplicationListener.supportsAsyncExecution()` and may still run on the publisher thread.

Therefore, **never deduce** from "an executor is enabled" that all listeners run in a single thread pool, or that they complete in exact order-number sequence.

### 7.2. Why Even a Single-Thread Executor Cannot Always Guarantee Global FIFO

A single-thread executor can help if its queue is FIFO and every related task truly goes through the same queue. Still, there remain:
- Listeners running synchronously because they do not support async.
- `@Async` proxies inside a listener submitting to a different executor.
- Rejection policies such as `CallerRunsPolicy` running tasks on the caller thread.
- Nested event publications creating a new dispatch.
- Multiple application instances having separate queues.
- Retries or brokers having different redelivery orders.

Do not turn "one thread" into a global ordering guarantee when the architecture has multiple execution paths.

### 7.3. Async Tests Need `CountDownLatch`

An asynchronous test should not do:

```java
publisher.publishEvent(event);
Thread.sleep(100); // Flaky when CI is slow.
assertEquals(expected, recorder.snapshot());
```

Replace with synchronization primitives with a **timeout**, such as `CountDownLatch`:

```java
CountDownLatch completed = new CountDownLatch(2);

// Both async callbacks call completed.countDown()
// after finishing the operation under test.

publisher.publishEvent(event);
assertTrue(completed.await(5, TimeUnit.SECONDS));
```

This is a **test snippet** requiring `CountDownLatch`, `TimeUnit`, JUnit, publisher, event, and callback wiring with the latch; it is **not** part of the Section 5 program. A latch indicates that two tasks reached a milestone, yet by itself **does not prove** A finished before B. To assert ordering in an asynchronous pipeline, record start/finish events on a thread-safe recorder, or structure dependencies through a future chain/workflow.

### 7.4. If B Requires A to Succeed, Do Not Rely on `@Order` with Async

If `ListenerB` can only run after `ListenerA` successfully updates a DB or remote API, build an explicit dependency:

```text
OrderPlaced
    |
    v
ProjectionService updates projection successfully
    |
    +--> publishes OrderProjectionUpdated
                    |
                    v
               Notifier
```

If this step needs durability or crosses service boundaries, use an outbox/message broker and idempotent consumers—not just an in-memory nested Spring event.

## 8. An Exception Can Prevent Later Listeners from Running

A straightforward example:

```java
@EventListener
@Order(10)
public void first(OrderPlaced event) {
    throw new IllegalStateException("audit unavailable");
}

@EventListener
@Order(20)
public void second(OrderPlaced event) {
    // Cannot assume this will always be called.
}
```

This is a snippet in hypothetical beans. With the default synchronous multicaster and **no suppressing `ErrorHandler`**, the first listener's exception can propagate back to `publishEvent` and stop the dispatch chain. `@Order` sets who is called first; **it does not force every listener to run regardless of errors**.

### 8.1. How `ErrorHandler` Affects the Chain

```java
multicaster.setErrorHandler(error -> {
    logListenerFailure(error);
    // Return normally -> suppress at this boundary.
});
```

This is an illustrative snippet; `multicaster` and `logListenerFailure` are defined by the application. If `ErrorHandler` handles the error and returns normally, the multicaster can proceed to the next listener, though the first error **is not automatically repaired**.

If listener A already performed part of a side effect before failing, retrying the event may duplicate that effect. If B depends on A's state, letting B continue after suppressing A's error can create inconsistency. Error policies must therefore serve the business contract, not merely the goal of "getting all four log lines".

### 8.2. Async Exceptions Usually Do Not Reach the Publisher

With `@Async void`, errors can route to `AsyncUncaughtExceptionHandler`. With a custom multicaster executor, listener errors can be handled by `SimpleApplicationEventMulticaster.setErrorHandler(...)` or the executor boundary. Meanwhile, `Future` holds exceptions until `get()/join()`.

**Never equate** a normal return from `publishEvent` with every listener having succeeded, especially with async execution.

## 9. Transaction Phase Matters More Than `@Order`

`@TransactionalEventListener` binds callbacks to transaction phases:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void updateReport(OrderPlaced event) {
    // Runs after successful commit, if an active transaction exists.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(20)
public void notifyPartner(OrderPlaced event) {
    // Same AFTER_COMMIT phase; callback order can be prioritized.
}
```

This is a snippet inside a Spring bean with a transaction manager, not part of the Maven demo.

`@Order` can prioritize callbacks within a phase, **it does not change the phase itself**. For example:

```text
BEFORE_COMMIT @Order(100)
AFTER_COMMIT  @Order(1)
```

This does not mean `AFTER_COMMIT @Order(1)` runs before `BEFORE_COMMIT @Order(100)`, because the transaction lifecycle governs before/after.

### 9.1. No Transaction, No Callback by Default

Transactional listeners do not normally run when an event is published outside an active transaction, unless `fallbackExecution=true` is enabled. Any test of ordering must establish a proper transaction boundary to produce comparable behavior.

### 9.2. `AFTER_COMMIT` Is Not a Durable Queue

If the process crashes after commit before the callback runs, `@TransactionalEventListener(AFTER_COMMIT)` does not guarantee reprocessing. Critical side effects should evaluate a transactional outbox or Event Publication Registry depending on your actual Spring version and configuration.

### 9.3. Writing to the Database After Commit

If an after-commit listener must write state in a new transaction, use an appropriate service boundary (such as `REQUIRES_NEW` via a Spring proxy); do not assume `@Order` creates a transaction. Resource synchronization rules should be checked against your configured Spring transaction manager.

## 10. Nested Events Interleave Logs Between Callbacks

Listener A can publish a new event while still handling the first event:

```java
@EventListener
@Order(10)
public void recordAudit(OrderPlaced event) {
    logger.info("A starts");
    publisher.publishEvent(new AuditRecorded(event.orderId()));
    logger.info("A ends");
}

@EventListener
@Order(20)
public void reportMetrics(OrderPlaced event) {
    logger.info("B starts");
}
```

This is an illustrative snippet; it requires `publisher`, `logger`, and an `AuditRecorded` type. Under synchronous dispatch:

```text
OrderPlaced:
  A starts
  AuditRecorded listeners execute
  A ends
  B starts
```

Thus, logs from `AuditRecorded` listeners can appear between A's and B's logs **without violating `@Order`**. One dispatch is simply nested inside another.

More dangerously, if an `OrderPlaced` listener republishes `OrderPlaced` without a termination condition, the application can recurse deeply, emit duplicates, and cause a stack overflow.

Distinguish:
- Callback order for a single event occurrence.
- Order in which event occurrences are published.
- Nested event order.
- Side-effect/commit order.

If a nested chain grows into a complex multi-step workflow, orchestration or a state machine will be easier to review and recover on failure.

## 11. Conditions and Multiple Listener Methods in One Bean

A method can use a condition to process only some events:

```java
@EventListener
@Order(10)
public void on(OrderPlaced event) {
    if (!event.orderId().startsWith("VIP-")) {
        return;
    }
    // Process VIP order.
}
```

This is a snippet. It is still **invoked**, though it may exit early without producing side effects. With `@EventListener(condition="...")`, Spring can filter via SpEL before invoking the method.

Hence, seeing fewer logs than expected is not necessarily an ordering bug. Check type matching, conditions, exceptions, and whether the listener is actually registered.

When multiple `@EventListener` methods live in the same bean, do not rely on method declaration order in the Java source file. Place `@Order` directly on methods with explicit ordering requirements and write integration tests if order truly matters.

### Listeners Returning a New Event

An `@EventListener` method with a non-void return type can cause Spring to publish the return value as a new event. Therefore:

```java
@EventListener
public AuditRecorded on(OrderPlaced event) {
    return new AuditRecorded(event.orderId());
}
```

This is an illustrative snippet requiring the `AuditRecorded` class. It does not merely return a plain value to the publisher. Emitting an extra event can trigger nested dispatches and interleaved logs; for async listeners, Spring has specific restrictions on return-value event publication.

For clarity, inject `ApplicationEventPublisher` and publish explicitly after business logic succeeds, with proper transaction/reliability constraints.

## 12. Do Not Use Order to Implement a Mandatory Business Workflow

Suppose the system must:

1. Reserve inventory.
2. Capture funds.
3. Confirm the order.
4. Create a shipment request.

If any step fails, subsequent steps must not proceed. This is a **dependent workflow**, not four completely independent subscribers. Writing:

```text
@Order(10) reserveStock
@Order(20) captureMoney
@Order(30) confirmOrder
@Order(40) shipOrder
```

is an error-prone design, especially if the publisher invokes listeners inside an uncommitted transaction, involves non-DB I/O, uses async, or needs compensation.

An approach with clear responsibilities:

```text
OrderApplicationService / Saga Coordinator
    |
    +-- validate authorization and business state
    +-- reserve stock -> await outcome
    +-- capture payment -> await outcome / compensate if needed
    +-- transition domain state
    +-- persist state and event/outbox
    |
    +-- emit OrderConfirmed fact
             |
             +-- independent audit consumer
             +-- independent analytics consumer
             +-- independent notification consumer
```

Event fan-out fits **independent actions reacting after a fact**. If B requires A to have succeeded, consider invoking services in explicit sequence or publishing another fact **after A succeeds** with a clear contract.

### 12.1. `@Order` Does Not Create Transactions

Work inside `@Order(10)` does not automatically commit before `@Order(20)`, especially if both join the same transaction or use separate repositories/remote APIs. `@Order` only adjusts listener invocation/scheduling.

### 12.2. `@Order` Does Not Create Delivery Guarantees

An event processed inside the JVM is not automatically persisted durably. If the application restarts midway, Spring core provides no automatic replay merely because order numbers were declared.

If side effects must be durable, design an outbox/broker/retry mechanism and idempotent consumers. Never use log order as proof of external delivery.

### 12.3. `@Order` Does Not Solve Duplicates

If a publisher emits the same fact twice, every listener can receive it twice. To avoid sending two emails, creating two shipments, or overwriting state, use event IDs or business idempotency keys along with unique constraints or external idempotency at the real boundary.

## 13. Table Distinguishing Types of Ordering

| Type of order | Example | Solved by `@Order`? |
| --- | --- | --- |
| Bean initialization order | Which bean constructor runs first | **No**, depends on dependency graph |
| Listener selection | Which event triggers which listener | **No**, uses event type/condition |
| Listener invocation priority | For one event, which callback runs first | **Yes**, this is its primary purpose |
| Synchronous completion | Listener A finishes then B runs | Usually yes if dispatch is sync and free of errors/nested dependencies |
| Async completion | Whether task A or B finishes first | **No** |
| Transaction phase | `BEFORE_COMMIT` vs `AFTER_COMMIT` | **No**, uses transaction synchronization phases |
| Database commit order | How two transactions commit | **No** |
| Global event order | Events across multiple threads/services | **No** |
| Broker delivery order | Message order on Kafka/RabbitMQ | **No**, depends on partition/consumer configuration |
| Aggregate version | Event version 5 vs 6 | **No**, requires version/sequence |
| External side effects | When email, payment, shipment finish | **No**, governed by their own contracts |

A safe rule: whenever saying "properly ordered", always specify **what is being ordered and at which boundary**.

## 14. Testing and Operations: Do Not Confuse Logs with Ordering

In production, logs can interleave due to multiple publishers/threads, nested events, async appenders, or trace propagation. Comparing **log line timestamps** to prove `@Order` can easily mislead.

Use a recorder/test probe for integration tests as in Section 6. For production debugging, use structured logs:

```text
event_type=OrderPlaced event_id=E-100 listener=audit order=10 outcome=START
event_type=OrderPlaced event_id=E-100 listener=audit order=10 outcome=SUCCESS
event_type=OrderPlaced event_id=E-100 listener=projection order=20 outcome=START
event_type=OrderPlaced event_id=E-100 listener=projection order=20 outcome=SUCCESS
```

These are illustrative log lines, **not output automatically generated by Spring**. `event_id` should identify the real occurrence, optionally alongside a workflow correlation ID. Never put raw event payloads, PII, or tokens into logs. Raw event IDs or user IDs should also not be used as high-cardinality metric tags.

### 14.1. Troubleshooting Workflow When Order Differs from Expectations

1. Check the exact published event type and which listeners match.
2. Check that `@EventListener` and `@Order` are placed on the right methods.
3. Check whether `ApplicationListener` beans implement `Ordered` and what `getOrder` returns.
4. Check for multiple listeners sharing the same order or default order.
5. Determine whether a custom `applicationEventMulticaster`/executor is configured.
6. Check for `@Async` or listeners submitting `CompletableFuture` themselves.
7. Check `@TransactionalEventListener` phase and whether an active transaction exists.
8. Check whether an earlier listener throws an exception or an `ErrorHandler` suppresses it.
9. Check for nested events and publications triggered inside other listeners.
10. Check for multiple publisher threads, contexts, or replicas.
11. Reproduce using an integration test with a recorder in the right context.
12. When final outcomes matter, assert side effects/commits rather than just callback order.

### 14.2. Testing Failure Branches

Beyond happy-path tests, verify:

| Test | What to verify |
| --- | --- |
| Order-10 listener throws sync exception | Publisher receives error per policy; later callbacks may not run |
| Multicaster with suppressing `ErrorHandler` | Metrics/alerts record failure; do not assume A succeeded |
| Two listeners with same order | Do not assert stable order if no contract guarantees it |
| Condition filters event | Listener is invoked or skipped per condition |
| Slow async listener | Do not require completion order via `@Order` |
| Nested publication | Recorder distinguishes event types/occurrences |
| Transaction rollback | `AFTER_COMMIT` callback does not run on rollback |
| No active transaction | Transactional listener is not invoked by default |
| Two publisher threads | Each dispatch has its own ordering; do not assume global serialization |
| Multiple application contexts | Listener registration scope is accurate; no duplicate dispatch via hierarchy |

## 15. Common Mistakes

1. **Reading `@Order(30)` as higher priority than `@Order(10)`.** Spring prioritizes smaller numbers.
2. **Giving two listeners the same order and expecting source-file order.** Relative order is not a contract.
3. **Assuming annotation order sorts bean initialization.** It does not.
4. **Putting `@Order` on a class and expecting all `@EventListener` methods to be ordered properly.** Method-level is clearer.
5. **Assuming every listener runs async just because the context has an executor.** Some do not support async dispatch.
6. **Assuming `@Async` order 10 always finishes before order 20.** Worker scheduling makes no such guarantee.
7. **Running async tests with an `ArrayList` recorder.** Not thread-safe.
8. **Using `Thread.sleep` to check completion.** Tests flake under CI load.
9. **Looking only at log timestamps and concluding ordering failed.** Async, nested events, and buffering exist.
10. **Forgetting the transaction phase of `@TransactionalEventListener`.** `AFTER_COMMIT` differs from invocation at publish time.
11. **Using `@Order` to execute mandatory multi-step business logic.** Lacks rollback/compensation/retry.
12. **Forgetting the first listener can throw an exception.** Later listeners are not guaranteed to run.
13. **Suppressing exceptions and reporting success.** Work may have partially failed.
14. **Treating event publishing as durable messaging.** Spring core does not create an outbox automatically.
15. **Assuming `@Order` orders events of different types.** It only applies to the listener set of one dispatch.
16. **Relying on completion order across threads.** There is no global serializer.
17. **Listener A mutating a mutable event object for listener B to read.** Creates hard-to-test coupling and races.
18. **Marking every listener `HIGHEST_PRECEDENCE`.** Destroys clear prioritization.
19. **Not checking for double listener registration.** Duplicate beans or context hierarchies may exist.
20. **Using correlation ID for idempotency.** One workflow can emit multiple facts.
21. **Assuming `@Order` controls broker ordering.** The transport has its own contract.
22. **Not testing in the real Spring context.** Direct callback calls bypass multicasting/sorting.
23. **Not clearing the recorder between tests.** Stale data causes flaky assertions.
24. **Adding an `@EventListener` return value without realizing Spring publishes another event.** Nested dispatch can change observed behavior.
25. **Treating callback invocation as a committed side effect.** There is no equivalent guarantee.

## 16. Checklist Before Using `@Order` Across Multiple Listeners

- [ ] Distinguished listener selection, invocation, and completion?
- [ ] Know whether the Spring multicaster is synchronous or asynchronous?
- [ ] Listeners for the same event have clear priorities where needed?
- [ ] Smaller numbers understood as higher priority?
- [ ] No tied order values where distinct ordering is required?
- [ ] `@Order` placed directly on important event listener methods?
- [ ] `ApplicationListener` implements `Ordered.getOrder()` properly when needed?
- [ ] Avoided `PriorityOrdered` unless there is a technical reason and test coverage?
- [ ] Avoided using `@Order` to force bean initialization order?
- [ ] Listener B is independent of listener A's side effects?
- [ ] Transaction phases modeled accurately rather than relying solely on order numbers?
- [ ] Async callbacks have dedicated completion and failure policies?
- [ ] Accounted for early exceptions preventing subsequent callbacks?
- [ ] Checked whether nested events cause recursion or interleaving?
- [ ] Tests use a real Spring context and a `CallRecorder`?
- [ ] Async tests use `CountDownLatch`/timeouts/thread-safe recorders appropriately?
- [ ] Avoided using log flush order as proof of callback order?
- [ ] Outbox/retry/idempotency in place where durable side effects are required?
- [ ] Documented ordering conventions so teammates do not accidentally break order?

**Summary:** In Spring Framework Application Events, `@Order` and `Ordered` are tools for ordering **the invocation sequence of multiple listeners for the same event**; smaller order numbers take precedence first. With the default synchronous `SimpleApplicationEventMulticaster`, this enables deterministic testing of callback lists. Once `@Async`, custom executors, transaction phases, errors, and nested events enter the picture, **callback order no longer equals completion order or business consistency**. Use ordering for genuine listener-organization needs; use dedicated workflows and transactional/reliability mechanisms for critical dependencies.

## References

- [Spring Framework — Additional Capabilities of ApplicationContext, Ordering Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Ordered Interface](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html)
- [Spring Framework — @Order Annotation](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
