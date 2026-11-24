# @EventListener Return Values: Publishing Follow-Up Events and Building Event Chains

In Spring Framework Application Events, a method annotated with `@EventListener` does not have to return `void`. **If a synchronous listener returns an object, Spring can publish that object as a new application event.** When returning a `Collection` or an array, **each element** is published as a separate event. This allows you to express a simple processing chain: receive event A → produce event B → B's listener continues to produce C.

This is different from “returning data to the caller” in an ordinary Java method. The return value is handled by the `@EventListener` adapter (listener adapter) **when the method is invoked by Spring's event mechanism**; it is not an HTTP response, not the direct return value of `ApplicationEventPublisher.publishEvent(...)`, and not a durable event queue.

This lesson explains the exact semantics of a single object, `null`, `void`, arrays, `Collection`, the limitations of `@Async`, how to avoid event loops, and a Java 17+ test suite running with Spring Test/JUnit 5.

## 1. Mechanism: What Does a Listener Return, What Does Spring Do?

Spring registers `@EventListener` methods of managed beans and invokes them when an event matches the parameter type. In the default synchronous event publishing mode, the conceptual sequence is:

~~~text
publisher.publishEvent(StartRequested)
    |
    +-- @EventListener onStart(StartRequested)
            |
            +-- return StartChecked
                      |
                      +-- Spring publishes StartChecked
                                |
                                +-- @EventListener onChecked(StartChecked)
                                        |
                                        +-- return AuditRequested
                                                  |
                                                  +-- Spring publishes AuditRequested
                                                            |
                                                            +-- @EventListener onAudit(...)
~~~

These `return` statements allow a listener to turn the **business outcome** of the current processing step into another event. Spring looks up listeners for the new event just as when application code explicitly calls `publishEvent(new ...)`.

| `@EventListener` method return value | Typical handling | Notes |
| --- | --- | --- |
| `new NextEvent(...)` | Publishes **one** `NextEvent` | The new event continues through the listener system |
| `List.of(eventA, eventB)` | Publishes **two** separate events | Does not treat the whole `List` as a single business event |
| `new Object[] { eventA, eventB }` | Publishes each element of the array | Elements can be of different event types |
| `Collections.emptyList()` | Publishes no follow-up events | Suitable for a branch with no result |
| `null` from a method with a return type | Publishes no follow-up events | Use intentionally; avoid accidental confusion |
| `void` | No event produced from return | Listener can still call publisher explicitly |
| A scalar that is not an `ApplicationEvent` | Spring treats it as a **payload event** | Spring allows events to be any Java object |

Spring Framework allows publishing not only `ApplicationEvent` subclasses but also any plain object (payload). Therefore, a Java record that does not extend `ApplicationEvent` can still be used as an event, for example `record PaymentAccepted(String id) {}`.

**There is no “special” value to return to acknowledge that an event was consumed.** Spring does not use `true`/`false` from a method as a default ack/nack mechanism. If a listener returns `Boolean.TRUE`, it may be published as a payload event of type `Boolean` — usually not the intended design.

## 2. Returning a Single Event: The A → B Chain

Suppose an order needs validation before publishing a recording request:

~~~java
record OrderSubmitted(String orderId) {}
record OrderValidated(String orderId) {}

@Component
class OrderValidationListener {

    @EventListener
    public OrderValidated validate(OrderSubmitted event) {
        // Validate business rules, then create the result.
        return new OrderValidated(event.orderId());
    }
}
~~~

This is an **excerpt** in a Spring application: it requires importing `org.springframework.stereotype.Component` and `org.springframework.context.event.EventListener`. When `OrderSubmitted` is published and `validate` runs through the Spring listener adapter, the returned `OrderValidated` object is published as the second event. Another listener can subscribe to `OrderValidated`.

If you merely call `new OrderValidationListener().validate(event)` directly in Java, the method still returns the record, **but no automatic publishing step occurs** because the call does not go through Spring's event system.

From a domain perspective, name events after what has happened or a meaningful outcome. Do not create `OrderValidated` just to glue three methods together; if this is a mandatory step of a command, calling a service directly can be easier to test, trace, and handle errors for.

### A return value is not the result of publishEvent

~~~java
publisher.publishEvent(new OrderSubmitted("ORD-01"));
~~~

`ApplicationEventPublisher.publishEvent(...)` is the event-publishing API and has return type `void`; it does not return `OrderValidated` to the caller. Even if a listener returns `OrderValidated`, Spring handles that event via another event publication, without creating a `Future<OrderValidated>` or a value that can be received directly from the publish call.

## 3. Returning a Collection or Array: One Input Event, Multiple Output Events

For example, when an order is accepted, two events need to be published for two separate responsibilities: updating the audit log and requesting a notification.

~~~java
record OrderAccepted(String orderId) {}
record AuditRequested(String orderId) {}
record NotificationRequested(String orderId) {}

@Component
class FanOutListener {

    @EventListener
    public List<Object> split(OrderAccepted event) {
        return List.of(
            new AuditRequested(event.orderId()),
            new NotificationRequested(event.orderId())
        );
    }
}
~~~

This is an excerpt; it requires importing `java.util.List`, `@Component`, and `@EventListener`. Spring does not send a single event whose payload is `List<Object>` when the method returns a `Collection`; it iterates over the elements and publishes **each event individually**. Using `List<Object>` here allows elements to belong to multiple event classes; if all elements have the same type, you can choose `List<AuditRequested>`.

Equivalently in terms of event count, the method can return an array:

~~~java
@EventListener
public Object[] splitAsArray(OrderAccepted event) {
    return new Object[] {
        new AuditRequested(event.orderId()),
        new NotificationRequested(event.orderId())
    };
}
~~~

This is an **alternative** to the `split` method; you should not register both listeners for `OrderAccepted` if the business logic only expects two events. Registering both would produce four events from a single input.

A `Set` is also a `Collection`, but you should not rely on element ordering across all `Set` implementations. If fan-out order matters, choose an ordered structure, while keeping in mind that other listeners, async executors, or separate transactions can make **completion order** differ from publication order.

**Do not assume `Map`, `Optional`, `CompletableFuture`, or `Mono` acts as a list of child events.** The standard return-value contract is documented for objects, arrays, and `Collection`; if you want explicit control over multiple events, use a `Collection`/array or publish manually at the appropriate execution step.

## 4. Returning null or void to Stop a Chain

Not every event has to produce a follow-up event:

~~~java
record ReviewRequested(String orderId, boolean approved) {}
record ReviewApproved(String orderId) {}

@Component
class ReviewListener {

    @EventListener
    public ReviewApproved onReview(ReviewRequested event) {
        if (!event.approved()) {
            return null; // Do not publish ReviewApproved.
        }
        return new ReviewApproved(event.orderId());
    }
}
~~~

This is an excerpt; it requires importing the annotations. If a `ReviewRequested` is not approved, Spring does not publish `ReviewApproved` from the `null` value. A `void` method also publishes no event via return. An empty `Collection` is useful when a method is designed to emit multiple events but one branch produces nothing.

Be careful to distinguish **not publishing a child event** from **not handling the input event**: Spring has still invoked the listener, and there may already be logs, queries, or side effects before returning. If you want to filter a listener so it does not run for certain events, consider `@EventListener(condition = "...")` with SpEL, which is a different mechanism from returning `null`.

## 5. Complete Integration Example with Spring Test and JUnit 5

This example only needs **Spring Context and Spring Test**; no Spring Boot or database is required. We simulate three chain patterns: one event producing one event; one event producing two events via `List` or array; and a branch returning `null`.

### 5.1. Gradle Configuration

Create a Java 17 project with `build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

These versions are an example for Spring Framework 6.2 / Java 17; in a Spring Boot project, prefer the synchronized BOM managed by Boot. With the project's Gradle wrapper, a system-wide Gradle installation is not required.

### 5.2. File `src/test/java/example/events/EventListenerReturnValueTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(EventListenerReturnValueTest.Config.class)
class EventListenerReturnValueTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired ChainListeners listeners;
    @Autowired Trace trace;

    @BeforeEach
    void clearTrace() {
        trace.clear();
    }

    @Test
    void oneReturnValueThenCollectionCreatesChainedEvents() {
        publisher.publishEvent(new StartRequested("A-1"));

        assertEquals(
            List.of(
                "start:A-1",
                "checked:A-1",
                "audit:A-1",
                "notify:A-1"
            ),
            trace.snapshot()
        );
    }

    @Test
    void arrayReturnCreatesIndividualEvents() {
        publisher.publishEvent(new BatchRequested("B-2"));

        assertEquals(
            List.of("batch:B-2", "first:B-2", "second:B-2"),
            trace.snapshot()
        );
    }

    @Test
    void nullReturnStopsThatBranch() {
        publisher.publishEvent(new DecisionRequested("C-3", false));
        assertEquals(
            List.of("decision:C-3:false"),
            trace.snapshot()
        );

        publisher.publishEvent(new DecisionRequested("D-4", true));
        assertEquals(
            List.of(
                "decision:C-3:false",
                "decision:D-4:true",
                "approved:D-4"
            ),
            trace.snapshot()
        );
    }

    @Test
    void directJavaCallDoesNotRepublishReturnValue() {
        CheckedEvent result = listeners.onStart(new StartRequested("E-5"));

        assertEquals("E-5", result.id());
        assertEquals(List.of("start:E-5"), trace.snapshot());
    }

    record StartRequested(String id) {}
    record CheckedEvent(String id) {}
    record AuditRequested(String id) {}
    record NotifyRequested(String id) {}

    record BatchRequested(String id) {}
    record FirstEvent(String id) {}
    record SecondEvent(String id) {}

    record DecisionRequested(String id, boolean approved) {}
    record ApprovedEvent(String id) {}

    static class Trace {
        private final List<String> lines = new ArrayList<>();

        void add(String value) {
            lines.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(lines);
        }

        void clear() {
            lines.clear();
        }
    }

    static class ChainListeners {
        private final Trace trace;

        ChainListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public CheckedEvent onStart(StartRequested event) {
            trace.add("start:" + event.id());
            return new CheckedEvent(event.id());
        }

        @EventListener
        public List<Object> onChecked(CheckedEvent event) {
            trace.add("checked:" + event.id());
            return List.of(
                new AuditRequested(event.id()),
                new NotifyRequested(event.id())
            );
        }

        @EventListener
        public void onAudit(AuditRequested event) {
            trace.add("audit:" + event.id());
        }

        @EventListener
        public void onNotify(NotifyRequested event) {
            trace.add("notify:" + event.id());
        }

        @EventListener
        public Object[] onBatch(BatchRequested event) {
            trace.add("batch:" + event.id());
            return new Object[] {
                new FirstEvent(event.id()),
                new SecondEvent(event.id())
            };
        }

        @EventListener
        public void onFirst(FirstEvent event) {
            trace.add("first:" + event.id());
        }

        @EventListener
        public void onSecond(SecondEvent event) {
            trace.add("second:" + event.id());
        }

        @EventListener
        public ApprovedEvent onDecision(DecisionRequested event) {
            trace.add(
                "decision:" + event.id() + ":" + event.approved()
            );
            if (!event.approved()) {
                return null;
            }
            return new ApprovedEvent(event.id());
        }

        @EventListener
        public void onApproved(ApprovedEvent event) {
            trace.add("approved:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        ChainListeners listeners(Trace trace) {
            return new ChainListeners(trace);
        }
    }
}
~~~

### 5.3. Running and Interpreting the Results

On a system with the Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.EventListenerReturnValueTest"
~~~

On Windows PowerShell, use `./gradlew.bat test --tests "example.events.EventListenerReturnValueTest"`.

The test does not print `start`, `checked`, `audit`, or `notify` traces to stdout; those strings are **asserted** inside `Trace`. When the tests pass, what they demonstrate is:

- **Single-event and Collection chain:** `StartRequested` → `CheckedEvent` → each element of the `List` produces `AuditRequested` and `NotifyRequested`, received in the list's emission order in the synchronous model with one listener per type.
- **Array:** `Object[]` is unpacked by Spring into individual events without needing to call `publishEvent` twice manually.
- **Null:** the `DecisionRequested(..., false)` branch does not produce `ApprovedEvent`, whereas the `true` branch does.
- **Direct method call:** `listeners.onStart(...)` returns a normal Java record without automatically publishing `CheckedEvent`; only calls through the listener system trigger follow-up event creation.

The ordering assertions in the example rely only on having **one listener per child event type** and the default synchronous mechanism. Do not infer a general guarantee on completion order across multiple independent listeners when `@Async` or an executor is involved.

## 6. Important Limitation: @Async and Asynchronous Event Listeners

Spring Framework explicitly states: **asynchronous listeners cannot publish follow-up events via their return value**. If you use `@Async` on an `@EventListener`, you must explicitly invoke `ApplicationEventPublisher` when the asynchronous work produces a result.

Illustrative example in a Spring bean with `@EnableAsync` configured:

~~~java
@Component
class AsyncValidationListener {
    private final ApplicationEventPublisher publisher;

    AsyncValidationListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void validate(StartRequested event) {
        // Asynchronous processing ...
        publisher.publishEvent(new CheckedEvent(event.id()));
    }
}
~~~

This is an **excerpt**; it requires the records and imports for `@Component`, `@Async`, `@EventListener`, and `ApplicationEventPublisher`; `@EnableAsync` configuration must also be present. `publisher.publishEvent(...)` is called **explicitly** inside the async task, instead of `return new CheckedEvent(...)`. Do not include this snippet in the same context as the synchronous test unless you intend to register an additional listener for `StartRequested`.

Notes when using async:

- The caller's `publishEvent()` does not wait for async work to complete; tests need an await mechanism with a timeout instead of asserting immediately after publishing.
- Exceptions in an async listener are not necessarily propagated back to the publisher; you need an error observability, logging, and retry strategy.
- `ThreadLocal`, MDC, and transaction context are not automatically propagated to the executor in all configurations.
- Do not use `@Async` merely to “fix” an event loop; it changes error boundaries, completion timing, and processing order, and does not itself provide a durable queue.

If the multicaster is configured with a `TaskExecutor` instead of the default synchronous mode, you must also re-evaluate ordering, error, and threading semantics for each listener. When requirements strictly demand chaining work whose completion must be awaited, an explicit pipeline/orchestrator may fit better than implicit chaining via events.

## 7. Ordering, Re-entrancy, and Event Loops

### 7.1. A return can create an immediate nested chain

In the default synchronous mode, the listener method handles A and returns B; Spring may publish B **right inside the call stack of publishing A**. B continues to produce C, creating a nested chain. This is convenient for short flows, but if the chain is long or has looping branches, the call stack can grow deep, exceptions can propagate backward, and debugging becomes difficult.

~~~text
A --> listener A returns B
      B --> listener B returns C
            C --> listener C returns D
                  ...
~~~

This is not a replay engine, and Spring does not automatically provide attempt counts, durable checkpoints, hop-count limits, or post-crash replay mechanisms.

### 7.2. Avoiding the A → B → A Cycle

Dangerous design example:

~~~java
@EventListener
public BEvent onA(AEvent event) {
    return new BEvent(event.id());
}

@EventListener
public AEvent onB(BEvent event) {
    return new AEvent(event.id());
}
~~~

The two methods above are an **excerpt illustrating a design flaw**, not a standalone file. If both continuously receive events and return the opposite event without a stopping condition, publishing can recurse indefinitely until `StackOverflowError` or resource exhaustion occurs.

A generally better fix is to design a **finite state flow**, distinguish commands from events, and avoid having listeners repeat the same operation; if retries are truly needed, use a bounded retry mechanism, backoff, dead-lettering, and idempotency at the appropriate layer. Tracking a `correlationId`, `eventId`, or processing count can be useful when justified by business rules, but should not be treated as the sole cure for a cyclic design.

### 7.3. @Order does not replace chain semantics

`@Order` on `@EventListener` sets invocation priority **among listeners of the same event** when the dispatch mechanism honors ordering. It does not turn an `@EventListener` returning B into a listener waiting for transaction commit, nor does it guarantee completion order when listeners run asynchronously.

A chain where **A returns B** depends on the event type and method A's result. A group of **multiple listeners receiving A** is a fan-out of the same event. These are two different structures, so do not use `@Order` to simulate complex business dependencies across many listeners.

## 8. Returning Events vs. Explicit publishEvent

Both approaches can produce follow-up events during synchronous processing:

~~~java
// Approach 1: declare the result via return.
@EventListener
public CheckedEvent onStart(StartRequested event) {
    return new CheckedEvent(event.id());
}

// Approach 2: explicitly publish inside the listener body.
@EventListener
public void onStartExplicit(StartRequested event) {
    publisher.publishEvent(new CheckedEvent(event.id()));
}
~~~

These are two **alternatives**; do not register both for the same event if you only want a single `CheckedEvent`. `publisher` in approach 2 is an injected `ApplicationEventPublisher`.

Comparison:

| Criterion | Return event | Explicit publish |
| --- | --- | --- |
| Code for a simple transition | Concise, minimal boilerplate | Slightly longer |
| Multiple output events | Return `Collection`/array | Multiple publish calls, with optional conditions in between |
| Acting at a specific decision point in the method | Published after the method completes | Can publish mid-method |
| Listener uses `@Async` | **Does not support** chaining via return | Required approach when you genuinely want to emit child events |
| Visibility of event boundaries in code | Visible only through the return type | Explicit publish calls are clearly visible |
| Durability/retry across process crash | Not built in | Also not built in; requires a separate outbox/broker/registry |

Choose returning an event when the flow is short, the result is domain-meaningful, and readers can follow it easily. Choose explicit publishing when you need to control the order of side effects inside the method, use async, or make the exact publication site obvious. When business logic requires sequential completion with strict error handling, an application service invoking steps via regular methods can be clearer than event chaining.

## 9. Transaction Interaction: Return Value Is Not After-Commit

If the initial event is published **inside a transaction**, synchronous listeners normally run on the same thread, and the new event produced from a return value may also be published **before the original transaction commits**.

~~~text
BEGIN DB TRANSACTION
  UPDATE orders ...
  publish OrderSubmitted
      @EventListener onSubmitted -> return OrderValidated
          @EventListener onValidated -> send email  [not yet committed]
  business error
ROLLBACK
=> email may have been sent even though the database rolled back.
~~~

Therefore, **switching to returning events does not fix transaction boundary bugs**. If a side effect must execute only when the transaction commits successfully, consider `@TransactionalEventListener(phase = AFTER_COMMIT)` with an appropriate contract. If reliable message delivery is required even if the JVM dies after commit, `AFTER_COMMIT` alone is still insufficient; a transactional outbox or event publication registry with persistence/recovery is a better fit.

Do not assume the return value of a `@TransactionalEventListener` starts a pipeline with a new transaction or guaranteed delivery: handle post-commit requirements with dedicated transactional/durability mechanisms. For reactive/async pipelines, always examine context, subscription behavior, and error propagation.

## 10. Common Mistakes and Checklist

| Mistake | Why it causes issues | Appropriate practice |
| --- | --- | --- |
| Returning a `String` just for logging and forgetting the return will be published | It can become an unintended payload event | Use `void` to emit no event, or return an explicit event type |
| Returning a `List` and expecting a listener to receive the whole list | Spring splits a `Collection` into individual events | If the list is a single business payload, wrap it in another record |
| Returning `null` while expecting the downstream listener to run | No event is published from `null` | Return a concrete event object if the branch should continue |
| Calling `listener.method()` directly and expecting follow-up publishing | Direct Java calls bypass the listener adapter | Publish the initial event via `ApplicationEventPublisher` in a real context |
| Using return-event inside `@Async @EventListener` | Spring does not support that mechanism | Inject the publisher and publish child events manually |
| Creating A → B → A with no stopping condition | Can cause infinite recursion | Design terminal states, idempotency, and avoid hidden cycles |
| Using `@Order` to guarantee transaction commit | Listener order does not mean transaction outcome | Use transactional listeners or an outbox |
| Asserting immediately after publish when async is enabled | Async work may not be finished yet | Await with a timeout and inspect errors |
| Treating return-event as a durable event log | Spring Application Events are in-memory by default | Use a suitable persistence/replay system if durability is needed |

Checklist before using return values to build chains:

1. Have you defined the **new event type** and registered a corresponding listener?
2. Does the method return `void`, `null`, a single object, a `Collection`, or an array — does that match the expected number of events?
3. Does the listener run synchronously? Does `@Async` or a multicaster executor alter the semantics?
4. Are there looping branches, listeners sharing data types, duplicate events, or circular dependencies?
5. Does the new event trigger external side effects outside the database while the transaction is still uncommitted?
6. Is there an integration test publishing through a real Spring context to verify that child events are produced?

## 11. Self-Check Questions

**Question 1:** What happens if an `@EventListener` method returns an `OrderValidated`?

When the method is invoked by Spring as a synchronous listener, the returned value is published as a new `OrderValidated` event. It does not become the return value of `ApplicationEventPublisher.publishEvent(...)`.

**Question 2:** Does returning `List.of(new A(), new B())` create a single event containing the list?

Not under `@EventListener`'s return-value mechanism. Spring publishes `A` and `B` as separate events. To pass the entire list as one payload, wrap it in a dedicated event object.

**Question 3:** When are `null` or `void` appropriate?

When the listener has handled the input and there is no requirement to publish a follow-up event. `null` stops the return-event branch; `void` indicates the method provides no event output.

**Question 4:** Why shouldn't an `@Async @EventListener` return `NextEvent` to build a chain?

Because Spring does not support publishing follow-up events from the return value of an async listener. To emit a new event when async processing completes, call `ApplicationEventPublisher.publishEvent(...)` explicitly.

**Question 5:** Does returning an event from a synchronous listener guarantee the DB commits before a child listener sends an email?

No. If the initial event was published inside an uncommitted transaction, the chain can run before commit. You must use transaction-phase semantics or an outbox depending on business requirements.

**Key takeaway:** `@EventListener` can return **a single event, a Collection, or an array for Spring to publish follow-up events**. This is a convenience for building in-application event chains, not a mechanism for returning results from `publishEvent`, not suitable for return-based async chaining, and does not guarantee durable storage or delivery.

## References

- [Spring Framework – ApplicationContext: Annotation-based Event Listeners, return values, asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework – ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
