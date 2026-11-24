# Listener Invoked Multiple Times in Spring Framework Application Events

## 1. Symptoms and First Diagnostic Questions

An order management system publishes `OrderAccepted` to update analytics and send notifications. In the logs, the same line `"Handling OrderAccepted"` appears two or three times, sometimes sending two emails or writing duplicate audit records. Many immediately assume "Spring is calling the listener twice by itself". In reality, you must distinguish **how many times the event was published**, **how many matching listeners/methods are registered**, **propagation across ApplicationContexts**, and **actual retries/replays**.

A single `ApplicationEventPublisher.publishEvent(event)` call can deliver the event to **multiple valid listeners**. Conversely, a listener registered once can receive **multiple publishes** of the same payload or `eventId`. Both cases increase log counts, yet their causes and fixes differ.

**There is no rule saying "only one listener per event type" or "each eventId is processed once" in Spring Application Events.** The framework is designed to dispatch events to matching listeners, not to act as an automatic message-deduplicating system.

Before editing annotations or deleting listeners, answer:

1. How many **publish calls** correspond to the event in question?
2. How many **listener beans/methods** actually subscribe to that event type?
3. How many **ApplicationContexts** exist, and are events propagating from child to parent?
4. Does a listener **publish additional events**, return an event, or trigger a new workflow branch?
5. Are there **retries, replays, re-runs, broker/outbox redeliveries**, or restarts?
6. Do two log lines prove **two independent callbacks**, or merely one callback logged across multiple layers/interceptors?

This topic belongs to **Troubleshooting** in Spring Framework Application Events. The goal is to locate the true source of "multiple invocations" rather than hiding logs or ignoring legitimate events.

## 2. One Event, Multiple Callbacks: Dispatch Diagrams

With the default synchronous multicaster:

```text
OrderService
    |
    | publishEvent(OrderAccepted(evt-100))
    v
ApplicationEventMulticaster
    |
    +--> AuditListener.onAccepted(evt-100)
    |
    +--> EmailListener.onAccepted(evt-100)
    |
    +--> ProjectionListener.onAccepted(evt-100)
```

**One publish, three distinct callbacks is expected behavior** if three listeners are registered for `OrderAccepted`. All three logging the same `eventId` does not mean the exact same listener was called three times.

Conversely:

```text
OrderService
    |
    +--> publishEvent(OrderAccepted(evt-100))
    |          |
    |          +--> AuditListener.onAccepted(evt-100)
    |
    +--> publishEvent(OrderAccepted(evt-100))
               |
               +--> AuditListener.onAccepted(evt-100)
```

**Two publishes, one listener, two callbacks.** If the same `eventId` is emitted again, Spring has no built-in mechanism to recognize and drop the second event. In retry-enabled environments, this may be completely valid delivery behavior, requiring idempotency at the business layer.

A third case:

```text
Single publish of OrderAccepted(evt-200)
    |
    v
ApplicationEventMulticaster
    |
    +--> AuditListener bean A: handle(evt-200)
    |
    +--> AuditListener bean B: handle(evt-200)
```

Here **two listener beans of the same type** are registered—for example, because configuration declared two `@Bean`s or one class was instantiated via multiple paths. One event is published once, yet the "audit" side effect may run twice if both beans perform the same business logic.

Thus **callback count** is not enough to conclude **publish count**, and **publish count** alone does not tell you how many times side effects occurred.

## 3. Quick Classification by Observed Symptoms

| Observation | Hypothesis to check | Evidence to collect |
| --- | --- | --- |
| Same `eventId`, same bean/method, multiple callbacks | Event republished, listener registered via multiple paths, or replay | Logs at publish site and listener entry |
| Same `eventId`, multiple beans/methods | Multiple legitimate subscribers or duplicate bean creation | Bean name, class, context ID, and method |
| Same event type, different `eventId` | Two distinct occurrences or `eventId` regenerated on retry | Originating task, business key, correlation ID |
| Same lifecycle event like `ContextRefreshedEvent`, different context | Parent/child contexts or multiple refreshed contexts | `event.getApplicationContext()` |
| Listener re-triggers the same event it received | Loop/chaining, returned event, or explicit publish | Causation ID and call path |
| Duplicates only when running async | Two tasks submitted, parallel execution, or retries | Task ID, thread, attempt, queue |
| Appears only after restart/deploy | Fresh startup or redelivery of unacknowledged messages | Process/instance ID, startup time, broker offset |
| Duplicate logs yet side-effect counter did not rise | Logged across different interceptors/traces or log aggregator duplication | Message ID, logger name, and callback entry |

**Rule:** a single log line does not prove Spring called a method twice. Instrument both **publish site** and **callback entry**, then correlate by event occurrence.

## 4. Step 1 — Check Whether the Publisher Emits Duplicates

### 4.1. Two Code Paths Both Publishing One Event

Counterexample:

```java
@RestController
public class OrderController {
    private final OrderService service;
    private final ApplicationEventPublisher publisher;

    // Constructor injection omitted.
    @PostMapping("/orders/{id}/accept")
    public void accept(@PathVariable String id) {
        service.accept(id); // service already published OrderAccepted.
        publisher.publishEvent(new OrderAccepted(
                "evt-100", id)); // Published again unnecessarily.
    }
}
```

This is an **illustrative snippet**, omitting constructors and service/event definitions so it is not standalone runnable code. It illustrates an ownership bug: both controller and service publish the same fact. Only **one layer should own creating and publishing domain events** after business state genuinely changes.

### 4.2. Each Service Invocation Publishes Again

An endpoint can be called twice due to user double-clicks, HTTP client retries, network timeouts, or two messages delivered to a handler. In that case, the service runs twice; Spring dispatching twice faithfully reflects two publishes.

When operations share the same business key, distinguish:

- **Two valid business intents:** e.g., two separate payments for the same order; must not be blindly blocked by `orderId`.
- **One retried request:** should carry a stable request/idempotency key and deduplicate where business state is mutated.
- **One already-created event replayed:** preserve the original occurrence's `eventId` when replaying so consumers can detect duplicates accurately.

### 4.3. Log Immediately Before the Publish Call

Integration pattern:

```java
log.info("PUBLISH type={} eventId={} orderId={} source={}",
        OrderAccepted.class.getSimpleName(),
        event.eventId(),
        event.orderId(),
        "OrderService.accept");
publisher.publishEvent(event);
```

This snippet requires `log`, `publisher`, and `event` already declared in the service. In larger systems, include `correlationId`, `causationId`, `instanceId`, and an invocation ID. **Never put sensitive info or full entities into logs.**

Note: `publishEvent(...)` being called does not mean all async listeners have finished; a `"PUBLISH"` log only proves the publish call occurred at that point. Log listener start/end separately.

## 5. Step 2 — Find Listeners/Beans Registered Through Multiple Paths

Spring discovers listeners through common mechanisms:

- `@EventListener` on a Spring bean method.
- Class implementing `ApplicationListener<E>`.
- Listener added explicitly to a multicaster or context.
- Multiple distinct beans having methods listening for the same event type.
- Listeners registered across multiple contexts in a hierarchy.

An easy-to-spot configuration mistake is annotating a class with `@Component` while also creating **another instance** via `@Bean`:

```java
@Component
public class AuditListener {
    @EventListener
    public void onAccepted(OrderAccepted event) {
        // Same audit logic.
    }
}

@Configuration
class ExtraConfig {
    @Bean
    AuditListener auditListenerAgain() {
        return new AuditListener();
    }
}
```

**This illustrative pattern can create two listener beans**, depending on component scan scope and context configuration. If Spring genuinely registers both beans, a single event invokes both corresponding methods. Do not conclude solely from seeing two annotations; verify the actual bean list in the context.

Another variant: a single bean simultaneously implements `ApplicationListener<OrderAcceptedEvent>` and defines an `@EventListener` method handling the same `OrderAcceptedEvent`, executing similar side effects in **two separate callbacks**. Those are two handlers declared by the application itself, not Spring randomly repeating one method.

### 5.1. Check by Bean Name, Not Just Class Name

When spotting two identical log lines, add:

```java
log.info("Listener bean={} class={} eventId={}",
        beanName,
        getClass().getName(),
        event.eventId());
```

This is an integration snippet. `beanName` can be supplied from configuration or `BeanNameAware`; do not use `getClass().getSimpleName()` as a unique identifier because two distinct beans can share the same class. With Spring AOP, the runtime class may be a proxy; to inspect the actual target method, use the corresponding bean definition and target class in debugging tools.

During diagnosis, record **each bean/method** once by its `(beanName, method)` pair rather than aggregating all logs by event type. This separates "one bean called twice" from "two beans each called once".

### 5.2. Inspect Scan/Import Configuration

Cross-check `@ComponentScan` scopes, `@Import`, auto-configurations, `@Bean` methods, and modules registering listeners manually. Not every duplicate declaration produces duplicate beans: Spring may recognize repeated configurations, override bean names, or avoid re-registration depending on the case. **The decisive proof remains the actual beans and registered methods.**

Do not fix this by deleting an `@Component` at random before knowing whether that bean is used in another context or by another feature.

## 6. Complete Example: Two Different Causes Producing Two Callbacks

The Java 17 + Spring Framework 6.2 program below reproduces both cases using **two independent ApplicationContexts**:

**Case A:** only one listener bean, yet the publisher emits `OrderAccepted` **twice**.

**Case B:** the publisher emits **once**, yet the context contains **two listener beans** of the same class, named `audit-one` and `audit-two`.

Both cases produce two callbacks. We also print **the set of handler names** to prove the causes differ.

### 6.1. Project Structure

```text
duplicate-listener-diagnosis/
├── pom.xml
└── src/main/java/example/DuplicateListenerDemo.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duplicate-listener-diagnosis</artifactId>
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
                    <mainClass>example.DuplicateListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File src/main/java/example/DuplicateListenerDemo.java

```java
package example;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class DuplicateListenerDemo {

    public record OrderAccepted(String eventId, String orderId) {}

    // Trace is used only in the synchronous contexts of this demo.
    public static final class Trace {
        private final List<String> entries = new ArrayList<>();

        public void record(String handlerName, String eventId) {
            entries.add(handlerName + ":" + eventId);
        }

        public int callbackCount() {
            return entries.size();
        }

        public List<String> handlerNames() {
            return entries.stream()
                    .map(s -> s.substring(0, s.indexOf(':')))
                    .distinct()
                    .sorted()
                    .toList();
        }
    }

    // Two instances of the same class are two distinct listeners.
    public static class AuditListener {
        private final String name;
        private final Trace trace;

        public AuditListener(String name, Trace trace) {
            this.name = name;
            this.trace = trace;
        }

        @EventListener
        public void onAccepted(OrderAccepted event) {
            trace.record(name, event.eventId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OneListenerConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public AuditListener auditOne(Trace trace) {
            return new AuditListener("audit-one", trace);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoListenersConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public AuditListener auditOne(Trace trace) {
            return new AuditListener("audit-one", trace);
        }

        @Bean
        public AuditListener auditTwo(Trace trace) {
            return new AuditListener("audit-two", trace);
        }
    }

    public static void main(String[] args) {
        // Case A: 2 publishes -> 2 callbacks from ONE listener.
        try (var context = new AnnotationConfigApplicationContext(
                OneListenerConfig.class)) {
            Trace trace = context.getBean(Trace.class);

            context.publishEvent(
                    new OrderAccepted("evt-100", "ORD-42"));
            context.publishEvent(
                    new OrderAccepted("evt-100", "ORD-42"));

            System.out.println(
                    "A publishes=2 callbacks=" + trace.callbackCount());
            System.out.println(
                    "A handlers=" + trace.handlerNames());
        }

        // Case B: 1 publish -> 2 callbacks from TWO listener beans.
        try (var context = new AnnotationConfigApplicationContext(
                TwoListenersConfig.class)) {
            Trace trace = context.getBean(Trace.class);

            context.publishEvent(
                    new OrderAccepted("evt-200", "ORD-43"));

            System.out.println(
                    "B publishes=1 callbacks=" + trace.callbackCount());
            System.out.println(
                    "B handlers=" + trace.handlerNames());
        }
    }
}
```

### 6.4. Run

Use JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Four lines printed by the program**, excluding Maven/Spring logs if any:

```text
A publishes=2 callbacks=2
A handlers=[audit-one]
B publishes=1 callbacks=2
B handlers=[audit-one, audit-two]
```

### 6.5. Explaining the Results

- `OneListenerConfig` has one `AuditListener` bean recorded in the trace as `audit-one`. `main` explicitly calls `publishEvent(...)` twice with the same `eventId=evt-100`, so `trace.callbackCount() == 2`.
- `TwoListenersConfig` has two distinct beans `auditOne` and `auditTwo`; each bean has an `@EventListener` method accepting `OrderAccepted`. `main` publishes `evt-200` only once, yet both beans match so `trace.callbackCount() == 2`.
- `handlerNames()` extracts handler names from entries, calls `distinct()` and `sorted()`, giving deterministic output order even if dispatch order between listeners varies.
- Both contexts are created and closed sequentially without sharing `Trace` beans. Thus Case A's counters never interfere with Case B.
- `OrderAccepted` is a Java record; Spring accepts records directly via `publishEvent(Object)` and passes the payload to `@EventListener`.
- The example uses the default synchronous multicaster, with no `@Async`, transactions, broker, or retries. Hence `Thread.sleep` is unnecessary and the trace can be read immediately after publish.

**Lesson learned:** the exact same `"callbacks=2"` observation can have two completely different explanations. Before fixing, always record **publish count** and **handler identity**.

### 6.6. Extending to Print Each Callback

Instead of checking only totals, you can add inside `AuditListener.onAccepted`:

```java
System.out.println(
        "listener=" + name
                + " eventId=" + event.eventId()
                + " thread=" + Thread.currentThread().getName());
```

This snippet replaces part of the method body in the program, not a standalone runnable example. With async execution, add `instanceId` and `contextId` to distinguish workers/processes rather than relying solely on thread names as unique keys.

## 7. Step 3 — Check Parent/Child ApplicationContexts

Spring can organize contexts in a hierarchy, e.g., a parent holding shared beans and children holding web/module slices. Events published in a **child context** can **propagate up to ancestor contexts** per Spring's mechanism.

```text
Parent ApplicationContext
    |
    +--> ParentListener (registered in parent)
    ^
    | event from child propagates upward
    |
Child ApplicationContext
    |
    +--> ChildListener (registered in child)
    |
    +<-- publishEvent(...)
```

A single publish in a child can invoke **both the child's listener** and **the parent's listener**. This is not Spring wrongly "duplicating tasks"; two contexts hold different subscriptions. If the same audit/email feature is installed at both levels, business side effects can execute twice.

**For lifecycle events** like `ContextRefreshedEvent` or `ContextClosedEvent`, the event carries the source context; a parent listener can see both child events and parent events. To handle only events belonging to your own context:

```java
@Component
public class LocalContextObserver {
    private final ApplicationContext ownContext;

    public LocalContextObserver(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Ignore events originating from descendant contexts.
        }

        // Logic applicable only to this bean's own context.
    }
}
```

This is an integration snippet requiring imports for `@Component`, `ApplicationContext`, `@EventListener`, and `ContextRefreshedEvent`.

**Limitation:** payload records like `OrderAccepted` do not have `getApplicationContext()`. If business events need source-context filtering, include suitable metadata in the payload or place listeners in the right context rather than attempting to cast a record to `ApplicationContextEvent`.

### Distinguish from Multiple Refreshes/Startups

An application may initialize/close multiple contexts across a test suite, reloads, or deployments. Lifecycle events emitted on each context creation/refresh are **separate occurrences**, even when logs show the same `ContextRefreshedEvent` type. Do not lump them together as "the same event firing twice" if context IDs and timestamps differ.

## 8. Step 4 — Publishing Events Inside Listeners or Returning Events

Spring supports a **synchronous** `@EventListener` returning a new event. If the method returns a `Collection` or array, each element is published as a separate event.

Example:

```java
@EventListener
public InventoryRequested onAccepted(OrderAccepted event) {
    return new InventoryRequested(event.orderId());
}
```

This is an illustrative snippet requiring the `InventoryRequested` record. When `OrderAccepted` is received, Spring automatically publishes `InventoryRequested`. If another listener receives `InventoryRequested` and emits `OrderAccepted`, the application can create an **infinite loop**.

```text
OrderAccepted
    -> InventoryRequested
        -> OrderAccepted
            -> InventoryRequested
                -> ...
```

In synchronous processing, an unbounded loop increases call depth and eventually throws `StackOverflowError`. With async, it can fan out into queues and exhaust resources.

### 8.1. Distinguish Root Events from Derived Events

Include metadata:

```java
public record EventMetadata(
        String eventId,
        String correlationId,
        String causationId
) {}
```

- `eventId`: identifies the specific occurrence.
- `correlationId`: groups a workflow.
- `causationId`: the direct parent event that caused the current event.

If logs show chains like `evt-1 -> evt-2 -> evt-1` or multiple new events sharing the same `causationId`, inspect the follow-up publishing flow. Do not infer causality from `ApplicationEvent.getSource()`, because framework sources are not business parent-event identifiers.

### 8.2. When Returning an Event Does Not Auto-Publish

For `@Async` listeners, Spring **does not support** publishing follow-up events via return values. To emit a derived event from an async listener, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly.

Both mechanisms can still produce multiple legitimate callbacks; they differ in publish point and execution thread. If a listener calls `publishEvent` twice with the same event, look for a bug in logic rather than only in annotations.

## 9. Step 5 — Overly Broad Listener Types or Overlapping Business Methods

An application might have:

```java
@EventListener
public void onAnyDomainEvent(DomainEvent event) {
    auditService.write(event);
}

@EventListener
public void onOrderAccepted(OrderAccepted event) {
    auditService.write(event);
}
```

This is an illustrative snippet; `DomainEvent` must be a supertype/interface implemented by `OrderAccepted`, and `auditService` is an injected dependency. For `OrderAccepted`, **both methods match**; if both call `auditService.write`, auditing runs twice.

Ask: "Are these two handlers designed to do two different things, or two paths executing the exact same effect?"

- If one method does general logging and one sends email, both running is right.
- If both write the same audit record with no deduplication, that is a functional design bug.
- You can use specific typed handlers or appropriate filter conditions, while preserving required behavior for other event types.

### Condition Is Not a Deduplication Tool

`@EventListener(condition = "...")` can filter events using a SpEL expression, yet it **does not store processed `eventId` history**, does not handle retries, and does not make external consumers execute exactly once.

Never treat a condition like `eventId != null` as deduplication: every duplicate publish has a valid `eventId` and passes the condition.

### @Order Does Not Change Invocation Count

`@Order` adjusts invocation order among matching listeners where supported; it **does not pick a single exclusive listener**. Adding `@Order(1)` to one handler does not suppress others and does not guarantee completion order for async tasks.

## 10. Step 6 — Transactions, Retries, and Redeliveries

### 10.1. @TransactionalEventListener Does Not Deduplicate

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` registers a transaction-bound callback. By default, it triggers after the transaction **commits**; events published outside a transaction are normally skipped due to `fallbackExecution = false`.

However, if code calls `publishEvent(event)` **twice inside the same transaction**, Spring registers two post-commit callbacks. Both callbacks run after commit; `AFTER_COMMIT` only determines **timing**, not deduplicating occurrences with the same `eventId`.

Integration example:

```java
@Transactional
public void payOrder(String orderId) {
    // Update DB for business operation.
    publisher.publishEvent(new PaymentCaptured("evt-77", orderId));
    publisher.publishEvent(new PaymentCaptured("evt-77", orderId));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPayment(PaymentCaptured event) {
    // May run twice because published twice.
}
```

This is a mock snippet requiring imports, service, real transaction manager, and `PaymentCaptured` record. Do not assume `REQUIRES_NEW` or changing phases will automatically deduplicate.

### 10.2. Retries and Transaction Rollbacks

If a service retries **the entire method**, it may publish events on each attempt. With a synchronous `@EventListener`, the listener may execute before the transaction rolls back, causing external side effects outside the DB. With `@TransactionalEventListener(AFTER_COMMIT)`, rolled-back attempts do not trigger post-commit callbacks; **yet a committed attempt can still publish duplicates if business logic emits multiple times**, or if an operation is re-invoked after a prior successful commit.

Keep in mind:

- Exceptions in synchronous listeners can propagate to the caller and affect the active transaction.
- Exceptions in `@Async void` may go to `AsyncUncaughtExceptionHandler` rather than returning to the publisher.
- `AFTER_COMMIT` does not guarantee callbacks are retried after a crash.
- Some transaction resources may still remain bound during post-commit callbacks; when performing new DB writes from a listener, use a new transaction (e.g., `REQUIRES_NEW` via proxy or `TransactionTemplate`).

### 10.3. Brokers and Transactional Outbox

If events originate from Kafka, RabbitMQ, a scheduler, an outbox poller, or a retried job, events may be redelivered when:

- The handler executed the effect yet failed to ack in time.
- The worker died after calling an external service but before marking done.
- Timeouts left upstream unaware that the receiver already processed it.
- Multiple workers claimed the same job without proper locking.
- A slice of history is replayed to rebuild a read model.

Spring Application Events itself is in-process infrastructure and **does not store events for replay**. However, an application may receive broker messages and forward them into `publishEvent(...)`, causing re-publications in the local context. Therefore, track **message ID/offset/deliveryAttempt at the ingestion boundary**.

## 11. Preventing Duplicate Processing at the Business Layer: Idempotency

If a side effect must never run twice for the same event occurrence, do not merely try to make listener logs "appear once". Design **idempotent effects**.

### 11.1. Stable Identification Keys

An event can carry:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String orderId,
        String correlationId
) {}
```

A handler's idempotency key is typically:

```text
(consumer_name, event_id)
```

For example, `(invoice-creator, evt-77)` and `(email-sender, evt-77)` are **two distinct consumers**, each processing the event once per its own policy. Do not key globally on `eventId` alone across the entire application if that would accidentally block other legitimate subscribers.

### 11.2. Database Unique Constraints

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

An `INSERT` backed by a unique constraint lets the database resolve races across multiple workers. Never rely solely on:

```text
if (!exists(eventId)) {
    performSideEffect();
    saveProcessed(eventId);
}
```

This pseudocode is **non-atomic**: two workers can both observe non-existence and execute the side effect twice.

### 11.3. Markers Must Share the Transaction with Transactional Effects

Suppose a listener needs to insert a `notification_outbox` work record. The marker and outbox record must be written **inside the same new transaction** (when running post-commit) so they commit or roll back together. If the marker commits first and the outbox write fails, future retries will be blocked and work will be lost.

For emails/HTTP calls outside the database, DB transactions cannot roll back requests that already left the application. Use a transactional outbox, worker retries, and downstream-supported idempotency keys where possible. Do not claim end-to-end exactly-once delivery merely because a listener filtered once.

### 11.4. Event-Based Keys vs. Business-Invariant Keys

Sometimes a single `orderId` has **multiple valid events**: `OrderAccepted`, `OrderPaid`, `OrderShipped`. Keying solely on `orderId` can wrongly block distinct events. Conversely, if business rules specify **at most one invoice per paymentId**, deduplicating only by `eventId` is insufficient if two different `eventId`s both ask to issue an invoice for the same payment.

Often you need both:

- Marker on `consumer + eventId` to deduplicate redeliveries.
- Unique business key (e.g., `invoiceType + paymentId`) to protect effect invariants.

**Remember:** duplicate delivery and duplicate business action are related yet not identical problems.

## 12. Gathering Evidence: Logging at Three Boundaries

### 12.1. Log at the Publish Source

```text
stage=PUBLISH eventType=OrderAccepted eventId=evt-100
source=OrderService.accept context=app-main
correlationId=flow-7
```

### 12.2. Log at Callback Entry

```text
stage=LISTENER_START eventType=OrderAccepted eventId=evt-100
listenerBean=auditListener listenerMethod=onAccepted
context=app-main thread=http-5
```

### 12.3. Log Outcome

```text
stage=LISTENER_END eventId=evt-100
listenerBean=auditListener status=SUCCESS
effectId=audit-450
```

These lines are **sample log fields**, not output from section 6's program. For a single publish, seeing two `LISTENER_START` lines from two distinct beans indicates fan-out. Seeing two `PUBLISH` lines with the same `eventId` and one `listenerBean` points to duplicate emission at the source. Seeing one `PUBLISH` from a child yet callbacks in both parent and child points to the context hierarchy.

### Which IDs Should Be Included?

| Field | Purpose | Warning |
| --- | --- | --- |
| `eventId` | Distinguish occurrences and replays | Keep identical when retrying the same occurrence |
| `correlationId` | Group workflow/request | Not an automatic deduplication key |
| `causationId` | Trace direct parent event | Not synonymous with `getSource()` |
| `publisherInvocationId` | Distinguish **each publish call** | Diagnostic ID only; does not replace `eventId` |
| `listenerBean` + `method` | Identify registration/handler | Class name alone is insufficient |
| `contextId` | Distinguish parent/child/restarts | May also need instance ID |
| `attempt`/`deliveryTag` | Distinguish retries/redeliveries | Pull from broker/job source if available |
| `thread` | Observe sync/async | Do not use as a unique key |
| `instanceId` | Distinguish replicas | Logs from multiple processes can interleave |
| `status`/`effectId` | Verify effect | Success logs do not replace data verification |

**Subtle point:** `publisherInvocationId` can change across emissions of the **same `eventId`**; it is very useful for proving Spring received **two publish calls**, whereas `eventId` shows it was the same occurrence re-emitted.

Never log entire payloads that might contain customer data, tokens, card numbers, or secrets just to hunt down duplicates.

## 13. Practical Step-by-Step Investigation Workflow

### Step 1 — Create a Minimal Reproducible Scenario

Pick a clear `orderId` and `eventId`, away from concurrent traffic. Where possible, use a local context without brokers, thread pools, or transactions to verify baseline logic.

**Do not modify production** to emit extra real events just for debugging if those events carry side effects. Use tests or a sandbox environment and mock external services.

### Step 2 — Count Publishes Near the Source

Add logging/counters right before each `publisher.publishEvent(...)`, including source method and invocation ID. If there are two publish lines, trace controller/service/scheduler/handler paths leading to them. If there is only one line in one service, remember another publisher may exist; search code/traces scoped to that event.

### Step 3 — List Listener Beans and Methods

Inspect bean registrations in the application context, `@Component`/`@Bean` configurations, `ApplicationListener`s, and `@EventListener`s. When one class has two instances, record distinct **bean names**. Only remove extra beans after proving no other business feature requires them.

### Step 4 — Inspect the Hierarchy

If the app has multiple `ApplicationContext`s, log source context and listener context. For `ApplicationContextEvent`s such as `ContextRefreshedEvent`, use `event.getApplicationContext()` to filter out unwanted context events.

### Step 5 — Inspect Event Chains

If a handler returns an event, calls `publishEvent(...)`, or emits an event with an overlapping supertype, build an `eventId / causationId` graph. Spot loops or branches producing two equivalent events.

### Step 6 — Check Retry and External Sources

Check retry policies, transaction retries, message redeliveries, dead-letter replays, outbox pollers, cron jobs, and client request retries. Capture attempt counts and source ack/commit conditions.

### Step 7 — Temporarily Investigate in Controlled Synchronous Mode

In minimal tests, use the default synchronous multicaster with **`@Async` disabled** to count dispatch invocations. This is a fault-isolation technique, **not a recommendation to disable async in production**, as doing so alters latency and behavior.

### Step 8 — Test Effects and Add Safeguards

After fixing duplicate publishing/registration, add idempotency tests for critical consumers. Even when the original bug is fixed, legitimate retries or redeliveries can still occur later.

## 14. Testing to Prevent Duplicate Listeners from Returning

A test suite should verify three distinct things:

1. **Publish count:** how many occurrences the service emits for one business command.
2. **Dispatch count:** how many beans/methods receive the event, and whether registrations overlap.
3. **Effect count:** how many times a non-repeatable action is actually persisted.

### 14.1. Using @RecordApplicationEvents to Check Event Publishing

With Spring TestContext:

```java
@SpringJUnitConfig(MyConfig.class)
@RecordApplicationEvents
class OrderEventTests {

    @Autowired
    OrderService orderService;

    @Test
    void publishesOneOrderAccepted(ApplicationEvents events) {
        events.clear();
        orderService.accept("ORD-42");

        assertEquals(1,
                events.stream(OrderAccepted.class).count());
    }
}
```

This is an **integration snippet** requiring `MyConfig`, `OrderService`, the record, and matching JUnit/Spring Test imports; it is not part of section 6's runnable Maven project.

`@RecordApplicationEvents` shows which events Spring published/recorded within the test scope, yet **is not a tool for counting callbacks across all listeners**. One event may be recorded once while two listeners both receive it. Conversely, an async listener may not have finished when the assertion runs.

### 14.2. Checking How Many Listeners Were Invoked

Inject a recorder into listeners during tests and assert bean/method names alongside recorded counts. Section 6's example has `Trace.callbackCount()` and `Trace.handlerNames()`. With async, replace `ArrayList` with a thread-safe structure and use `CountDownLatch` with a timeout; never guess that `Thread.sleep(50)` is enough.

**Do not merely assert a listener was called "once" in a test with no retries** and claim idempotency is achieved. Idempotency must be verified with **two concurrent or repeated deliveries**, asserting the effect happens only once.

### 14.3. Testing with Transactions

An `@Transactional` test normally rolls back after each test method; when listeners use `AFTER_COMMIT`, callbacks may not run. Use intentionally committed transactions via `TransactionTemplate` or `TestTransaction` to verify post-commit listeners, then add a rollback case producing zero effects.

If an event is published twice before commit, assert **two post-commit callbacks** as expected; do not expect Spring to merge them.

### 14.4. Testing Retries/Redeliveries

For a consumer keyed on `(consumer, eventId)`:

- Processing the event once: effect is created.
- Reprocessing an already succeeded event: no second effect created.
- Two workers processing concurrently: unique constraint guarantees only one claim succeeds.
- Error after writing marker but before effect: marker and effect roll back together if the transaction is designed properly.
- External API times out after receiver processed it: use idempotency keys or reconcile state with the partner.

## 15. Async: Why Logs Can Create an Illusion of Duplicates

When using:

```java
@Async("eventExecutor")
@EventListener
public void onAccepted(OrderAccepted event) {
    log.info("Processing {}", event.eventId());
}
```

the publisher may return before the callback runs. Logs from multiple requests/events can interleave, making timestamp-only inspection misleading. Common cases:

- `eventId` is regenerated on every retry: multiple eventIds sharing the same business key.
- Two workers run callbacks concurrently: the same `eventId` appears close together; check whether two tasks/attempts exist.
- Logging interceptor prints `"before"` and the method prints `"processing"`: **two log lines inside one callback**, not two callbacks.
- Log collector ingests the same log entry twice: duplication at the log-ingestion tier, not the event handler.
- A derived event is published inside an async listener, causing downstream workflow logs to appear much later.

**How to confirm:** attach a counter/trace at the exact entry of the method with `listenerBean`, `eventId`, `attempt`, and a `handlerInvocationId`, and compare against actual effects. If there is only one callback entry yet two log lines, fix logging instrumentation or log analysis.

Exceptions in `@Async void` do not propagate back to the publisher; they may be reported via `AsyncUncaughtExceptionHandler`. If the message source retries independently, it may redeliver the event after a failure; thus fixing the error handler alone without handling retries/idempotency is insufficient.

## 16. Common Mistakes When "Fixing" Duplicate Listeners

1. **Adding `@Order` hoping only one listener runs.** `@Order` changes ordering, not filtering out listeners.
2. **Adding a SpEL condition with no idempotency state.** Conditions do not remember previously processed `eventId`s.
3. **Using `synchronized` inside one instance.** Does not protect across replicas, restarts, or other bean instances.
4. **Using an in-memory `Set<String>` as the sole deduplication store.** State is lost on restart; each instance has its own set.
5. **Filtering solely by `orderId`.** Can block other legitimate events for the same order.
6. **Generating a new `eventId` when retrying the same occurrence.** Consumers cannot recognize duplicate deliveries.
7. **Catching and swallowing exceptions.** Brokers/transactions may treat failure as success or lose proper retry capability.
8. **Sending email first and marking processed afterward with no downstream idempotency.** Crashes can cause duplicate sends.
9. **Marking processed before persisting the effect.** Crashes can permanently lose the effect.
10. **Calling every event from a child context a meaningless duplicate.** Parent contexts may legitimately need those events; filter intentionally.
11. **Deleting an `@EventListener` by class name without checking bean instances.** May remove a valid subscriber.
12. **Using `getSource()` as a context identifier for POJO payload records.** POJO records lack this API.
13. **Overlooking events returned from synchronous listeners.** The framework may emit derived events without a visible publish call in the caller.
14. **Believing `@TransactionalEventListener` merges duplicates.** Commit phases do not deduplicate.
15. **Assuming one `"done"` log proves an external API was called only once.** Verify actual records/effects/provider state.
16. **Running only single-threaded tests.** Misses races when two workers claim an event concurrently.
17. **Having both a broad listener and a specialized listener perform the same effect.** Both methods can match the same event.
18. **Assuming Spring processes events once cluster-wide.** Spring Application Events are in-process per instance context; cross-process delivery belongs to external systems.
19. **Confusing one publish with one workflow-wide execution.** Fan-out across multiple handlers is a feature, not a bug.
20. **Fixing callback counts instead of investigating business effects.** If callback counts are right yet effects duplicate, the bug may live downstream.

## 17. Production Readiness Checklist

- [ ] Stable `eventId` per event occurrence, plus `correlationId` for the workflow.
- [ ] Logs at **publisher** and **listener entry** to compare publish count vs. callback count.
- [ ] Logs/metrics distinguishing bean name, method, context, instance, and retry attempt.
- [ ] Audited duplicate `publishEvent(...)` calls across controllers/services/schedulers.
- [ ] Audited `@Bean`, `@Component`, `@EventListener`, `ApplicationListener`, and manually added listeners.
- [ ] With parent/child contexts, checked event scope and filtered by source when needed.
- [ ] For listener-returned events, mapped causation chains and bounded loops.
- [ ] Broad and specific listeners do not accidentally execute the same side effect twice.
- [ ] Retries, broker redeliveries, outbox, and rollbacks have all been analyzed.
- [ ] `@Order`, `@Async`, and `@TransactionalEventListener` are not treated as deduplication mechanisms.
- [ ] Critical consumers use unique/idempotency keys in durable storage.
- [ ] Markers and data mutations commit/roll back together; external APIs have proper retry strategies.
- [ ] Tests cover one-publish/many-listeners and many-publishes/one-listener.
- [ ] Tests cover duplicates, concurrency, transactions, retries, and final effects.
- [ ] Async completion order is never inferred from log ordering.
- [ ] Confirmed the log collector itself is not duplicating logs before altering business code.

**Conclusion:** when seeing "listener invoked multiple times", determine whether it is **multiple publishes**, **multiple matching subscriptions**, **context propagation**, or **retries/replays/event chains**. Spring's event mechanism may be working properly in all four cases. To fix the bug, address the true source or guard side effects with idempotency rather than trying to force every listener to execute only once.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Boot — Application Events and Context Hierarchies](https://docs.spring.io/spring-boot/reference/features/spring-application.html)