# Forwarding Events with Collections in Spring Framework Application Events

## 1. Problem Statement: One Event Leading to Multiple Follow-Up Events

In a Spring application, a single business event can trigger multiple independent actions. For example, after an order is accepted, the application wants to issue two requests: an email notification and a dashboard update. You can call `ApplicationEventPublisher.publishEvent(...)` directly multiple times; however, Spring Framework also supports a more concise approach: **returning a `Collection` or an array from a synchronous `@EventListener` method**.

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

Spring processes each element of the returned list as **a new application event**. Any listener interested in `NotificationRequested` can receive these new events and process them further. This is a mechanism for **forwarding/fanning out events from a listener's result**, not an API that turns a list into a durable processing batch.

Key points to grasp:

1. `@EventListener` identifies a method invoked when a given event type arrives.
2. A non-`void` return value can be **published by Spring as a new event**.
3. If the return value is a `Collection` or an array, Spring publishes **each element** as a separate event.
4. This mechanism applies to **synchronous** listeners; you cannot add `@Async` and expect returned values to be published automatically.
5. Each child event can trigger another listener, forming a multi-level chain. You must control loops, exceptions, transactions, and chain complexity.

> A `Collection` in the **return value** of `@EventListener` is handled specially by Spring. That differs from calling `publisher.publishEvent(list)`: a direct call publishes **the list object itself as a single payload event**, without unpacking individual elements by default.

## 2. Distinguishing a Listener's Input Event and Output Event

A listener method can accept one event type and return another type:

~~~java
@EventListener
public OrderIndexed onOrderPlaced(OrderPlaced input) {
    // Perform logic to handle OrderPlaced.
    return new OrderIndexed(input.orderId());
}
~~~

In this illustrative snippet:

- `OrderPlaced` is the **input event**; Spring uses the method parameter to decide whether the listener matches the published event.
- `OrderIndexed` is the **output event**; Spring publishes it after the method finishes and returns the object.
- If the method returns `null`, no follow-up event is published from that return value.
- `OrderIndexed` can be an `ApplicationEvent` subclass or a plain POJO/record payload, since `ApplicationEventPublisher` supports both.

When one step must produce multiple independent outcomes, use a `Collection`:

~~~java
@EventListener
public List<FollowUpRequested> onOrderPlaced(OrderPlaced input) {
    return List.of(
        new FollowUpRequested(input.orderId(), "EMAIL"),
        new FollowUpRequested(input.orderId(), "AUDIT"),
        new FollowUpRequested(input.orderId(), "SEARCH_INDEX")
    );
}
~~~

The list contains three elements, so each element becomes a separate `FollowUpRequested` event. It is not a single `List<FollowUpRequested>` event. If there is no follow-up action, you can return `List.of()`, corresponding to publishing no events from the method's result.

**The return value is not passed back to the caller of `publishEvent(...)` as an API result**; `publishEvent` remains an event-publishing API. Forwarding happens inside the event distribution system, rather than the publisher receiving the `List` back.

## 3. Execution Flow When Returning a Collection

With the default `SimpleApplicationEventMulticaster`, synchronous listeners typically run on the thread publishing the event. Assuming only the relevant listeners from the example are present, the execution flow can be visualized as:

~~~text
Publisher
    |
    +-- publishEvent(OrderAccepted("ORD-211"))
            |
            v
        @EventListener onOrderAccepted(...)
            |
            +-- return List.of(
            |      NotificationRequested("ORD-211", "EMAIL"),
            |      NotificationRequested("ORD-211", "DASHBOARD")
            |   )
            |
            v
        Spring processes the return value
            |
            +-- publishEvent(NotificationRequested(..., "EMAIL"))
            |       |
            |       +-- NotificationRequested listener handles EMAIL
            |
            +-- publishEvent(NotificationRequested(..., "DASHBOARD"))
                    |
                    +-- NotificationRequested listener handles DASHBOARD
            |
            v
        onOrderAccepted has led to the child events
            |
            v
Publisher continues after initial publishEvent
~~~

Several subtleties:

- Spring performs forwarding **after the listener method returns**; it does not emit elements individually as you add them to an `ArrayList`.
- When using a `List`, the collection has an element order; the adapter can publish elements in list iteration order. However, **system-wide completion order is not guaranteed** if executors, asynchronous listeners, multiple contexts, or brokers exist in subsequent steps.
- Each child event is a separate publication. A child event's listener can in turn return another event, creating a **multi-level chain**.
- If a child event listener throws an exception in the synchronous model, the exception can interrupt the forwarding flow and prevent later elements from being published. Changes/side effects already executed earlier are not automatically reversed.

For business workflows where every step must succeed or fail together, you should not replace a controlled workflow/transaction with an event chain lacking corresponding rollback, retry, or idempotency mechanisms.

## 4. Core Spring API

An `@EventListener` method is marked with the annotation:

~~~java
import org.springframework.context.event.EventListener;
~~~

According to `@EventListener`'s contract in Spring Framework:

- A method can return an object instead of `void`. The object is treated as a new event.
- If the **return value** is an array or a `Collection`, its elements are sent as individual events.
- The annotation is processed by the `EventListenerMethodProcessor` infrastructure when the application has appropriate annotation configuration.
- Input events can be `ApplicationEvent` instances or plain Java payloads.
- Spring can apply `@Order` to adjust the invocation order of listeners for an event.
- With `@Async` on a listener, publishing new events via the return value **is not supported**.

This is a **built-in mechanism** of Spring Framework; you do not need to write a custom wrapper for Spring to iterate over elements, as long as the listener is Spring-managed and event invocation flows through the context infrastructure.

Common return forms:

| Return type | How Spring interprets it | Appropriate when |
|---|---|---|
| `void` | Produces no next event via return | Only performing side effects or calling publisher explicitly |
| `SomeEvent` | Publishes one new event | One step has exactly one outcome |
| `List<SomeEvent>` | Publishes each element as a separate event | Fan-out with clear iteration order |
| `Set<SomeEvent>` | Publishes each element as a separate event | Order not required or an appropriate comparator exists |
| `SomeEvent[]` | Publishes each element as a separate event | Fixed-size array needed |
| `Collection<?>` | Publishes each element, possibly of different types | One step produces multiple event types |
| `null` or empty collection | Publishes no new event from the result | Condition produces no follow-up step |
| `Mono<SomeEvent>` / `Stream<SomeEvent>` | Not a Collection/array under the rule above | **Do not use** if the goal is auto-unpacking into events |

Do not assume every wrapper type will be traversed automatically. Spring documentation specifies **arrays** and **collections**; a `Stream` or `Publisher` should not be used as a substitute if you expect one event per element. With async/reactive pipelines, explicit event publishing and proper subscription/transaction boundaries are required.

## 5. Complete Java 17 + Maven Example: Two-Level Event Chain

This example uses **Spring Framework 6.2.8**, Java 17+, and Maven; no Spring Boot or database is needed. One input event `OrderAccepted` is converted into **two** `NotificationRequested` events via `List.of(...)`. Each notification is processed and returns `NotificationFinished`. Thus, we observe both **collection fan-out** and **event chaining**.

Directory structure:

~~~text
event-collection-demo/
├── pom.xml
└── src/main/java/demo/CollectionForwardingDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-collection-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/CollectionForwardingDemo.java

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class CollectionForwardingDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderAccepted("ORD-211"));
            System.out.println("publisher returned");
        }
    }

    public record OrderAccepted(String orderId) {
    }

    public record NotificationRequested(String orderId, String channel) {
    }

    public record NotificationFinished(String orderId, String channel) {
    }

    public static final class OrderEventRouter {

        @EventListener
        public List<NotificationRequested> route(OrderAccepted event) {
            System.out.println("route: " + event.orderId());
            return List.of(
                new NotificationRequested(event.orderId(), "EMAIL"),
                new NotificationRequested(event.orderId(), "DASHBOARD")
            );
        }
    }

    public static final class NotificationProcessor {

        @EventListener
        public NotificationFinished process(NotificationRequested event) {
            System.out.println("process: " + event.channel());
            return new NotificationFinished(event.orderId(), event.channel());
        }
    }

    public static final class CompletionLogger {

        @EventListener
        public void onCompleted(NotificationFinished event) {
            System.out.println("finished: " + event.channel());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderEventRouter orderEventRouter() {
            return new OrderEventRouter();
        }

        @Bean
        public NotificationProcessor notificationProcessor() {
            return new NotificationProcessor();
        }

        @Bean
        public CompletionLogger completionLogger() {
            return new CompletionLogger();
        }
    }
}
~~~

Run from the `event-collection-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CollectionForwardingDemo
~~~

Lines printed by the program in the default synchronous model upon a successful run:

~~~text
route: ORD-211
process: EMAIL
finished: EMAIL
process: DASHBOARD
finished: DASHBOARD
publisher returned
~~~

### Output Analysis

1. `AnnotationConfigApplicationContext` registers the three listener beans and the `@EventListener` processor.
2. `context.publishEvent(new OrderAccepted("ORD-211"))` feeds the initial payload into the event system.
3. `OrderEventRouter.route` receives `OrderAccepted`, prints the `route` line, and returns a two-element `List<NotificationRequested>`.
4. Spring publishes `NotificationRequested("ORD-211", "EMAIL")`; `NotificationProcessor.process` handles it and returns `NotificationFinished`; `CompletionLogger` receives the completion event. Because dispatch is synchronous and nested, the first `process/finished` pair finishes before the second element is published.
5. Spring forwards the `DASHBOARD` element and the corresponding chain completes.
6. Only after the synchronous listeners and nested publications finish does the initial `publishEvent` return; the program prints `publisher returned`.

**Why is there no loop?** The three event types have distinct roles:

~~~text
OrderAccepted
  -> List<NotificationRequested>
      -> NotificationFinished
          -> void
~~~

No listener emits `OrderAccepted` or `NotificationRequested` again after handling `NotificationFinished`, so the chain terminates naturally.

**Key takeaway:** the stdout order in the example comes from a single context, an ordered list, and synchronous listeners. Do not apply this ordering assumption to systems using `@Async`, multicaster executors, multi-node listeners, or message brokers.

## 6. Returning an Array Instead of a Collection

Spring also supports array return values:

~~~java
@EventListener
public NotificationRequested[] onOrderAccepted(OrderAccepted event) {
    return new NotificationRequested[] {
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    };
}
~~~

This is an **alternative** to the `route` method in the example above; do not keep both methods listening to `OrderAccepted` if you only want exactly two events produced. Spring turns each array element into a separate event.

Compared to `List.of(...)`, arrays:

- Have a fixed length, though elements can be reassigned if a reference is retained.
- Require attention to element types and returning `null` instead of an empty array.
- Fit well when existing APIs already return arrays; for ordinary business logic, `List` is usually more readable.

For an event collection used as a result, `List.of(...)` preserves order and prevents adding/removing elements after creation; note that mutable references held inside the payloads themselves can still be modified.

## 7. Collections Containing Different Event Types

A business operation may emit child events of different types:

~~~java
public record AuditRequested(String orderId) {}
public record IndexRequested(String orderId) {}

@EventListener
public Collection<?> onOrderAccepted(OrderAccepted input) {
    return List.of(
        new AuditRequested(input.orderId()),
        new IndexRequested(input.orderId())
    );
}
~~~

This is **illustrative code to place inside a Spring bean**; it requires importing `java.util.Collection` and `java.util.List`, as well as having the `OrderAccepted` type. Spring publishes each element according to its runtime type; listeners accepting `AuditRequested` and `IndexRequested` are matched to their respective event types.

However, a collection mixing multiple types can make the method contract harder to understand, easily introduce unintended side effects, and complicate schema testing:

- If all elements represent the same kind of action differing only in parameters, using `List<NotificationRequested>` expresses intent more clearly.
- If there are steps with distinct responsibilities, consider separate methods/event elements and name events after states that occurred or work requested.
- Do not return a collection containing a JPA entity, a string, and a service object expecting Spring to “figure out which ones are events”: Spring treats all of them as payload objects to publish, potentially triggering unexpected listeners.

Name event types precisely—such as `EmailRequested`, `SearchIndexRequested`, `OrderValidated`—rather than a vague `Object`.

## 8. Key Difference: Returning a Collection vs. publishEvent(Collection)

Compare these two snippets:

~~~java
// Case A: Each element is handled by Spring as a new event.
@EventListener
public List<NotificationRequested> fanOut(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

and:

~~~java
// Case B: Publishes the LIST ITSELF as a single payload object.
List<NotificationRequested> batch = List.of(
    new NotificationRequested("ORD-211", "EMAIL"),
    new NotificationRequested("ORD-211", "DASHBOARD")
);

publisher.publishEvent(batch);
~~~

In **Case B**, `ApplicationEventPublisher.publishEvent(Object)` receives an object, which here is a `List`. Spring does not apply the special rule of **`@EventListener` return values** to this direct publish call. A listener intending to receive the whole batch needs an event contract representing the batch, rather than assuming `NotificationRequested` items will be unpacked and forwarded.

A clearer design for a batch as a single event:

~~~java
public record NotificationBatchRequested(
    String orderId,
    List<NotificationRequested> notifications
) {
    public NotificationBatchRequested {
        notifications = List.copyOf(notifications);
    }
}

// A single event whose payload contains the list:
publisher.publishEvent(new NotificationBatchRequested("ORD-211", batch));
~~~

This is illustrative code (requiring imports and types from the example) and expresses a different contract:

- **Fan-out:** multiple independent events, each matched to listeners by element type.
- **Batch event:** a single event containing multiple items, where the listener decides how and how many items to process.

With a batch event, `List.copyOf` creates a structurally unmodifiable copy of the list; it does not make mutable elements themselves immutable.

## 9. Empty Collections, null, and Invalid Elements

Business branches do not always emit new events. Conditional outcomes can be expressed as:

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    if (event.orderId().startsWith("TEST-")) {
        return List.of();
    }
    return List.of(new NotificationRequested(event.orderId(), "EMAIL"));
}
~~~

When an empty list is returned, no follow-up event is created from the return value.

If the method has no result:

~~~java
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    if (event.orderId().isBlank()) {
        return null;
    }
    return List.of(new NotificationRequested(event.orderId(), "EMAIL"));
}
~~~

Spring does not publish a follow-up event when **the entire return value is `null`**. However, with a `Collection` contract, returning an empty list usually expresses intent more clearly and is easier to test than returning `null`.

Avoid collections containing **`null` elements**:

~~~java
List<NotificationRequested> wrong = new ArrayList<>();
wrong.add(new NotificationRequested("ORD-211", "EMAIL"));
wrong.add(null); // Does not create a meaningful null event.
~~~

In this code, `ArrayList` requires importing `java.util.ArrayList`. Do not assume null elements will be silently skipped. If a null element is present, publishing can fail or produce unintended results. `List.of(...)` rejects nulls automatically, helping catch bugs early.

Also, do not return a mutable collection and let another thread modify it while Spring is iterating over it. For dynamically built results, take a snapshot:

~~~java
List<NotificationRequested> pending = createRequests(event);
return List.copyOf(pending);
~~~

This is an integration pattern: `createRequests` is an application helper. Only copy after building the contents, and ensure event elements are immutable if needed.

## 10. Multi-Level Event Chains and Loop Risks

Spring does not automatically cap an event chain produced by listener return values. If event A generates event B, and event B generates event A, the system can loop:

~~~java
@EventListener
public EventB onA(EventA event) {
    return new EventB(event.id());
}

@EventListener
public EventA onB(EventB event) {
    return new EventA(event.id());
}
~~~

This is an **incorrect design example**; `EventA`/`EventB` are illustrative types. In synchronous dispatch, such a cycle can cause very deep recursion and `StackOverflowError` or hang the application; in async dispatch, it can cause an event/task storm.

Principles to avoid loops:

1. Name events after **states that occurred** or **requested actions**, avoiding reusing a single event type for every step.
2. Do not allow a listener to repeatedly emit the same event type without an explicit termination condition.
3. For multi-step workflows, enforce a state machine or orchestrator and test valid transitions.
4. If retries are required, separate retry policy from ad-hoc event chaining; add an attempt count, idempotency key, and retry limit.
5. When events repeat due to message redelivery, use `eventId`/`correlationId`/`aggregateId` according to their true meanings rather than treating them as interchangeable IDs.
6. Bound the number of child events generated from one input if fan-out can grow unusually large.

For example, a step emitting at most two actions is far safer than emitting tens of thousands of entities as events without backpressure.

## 11. Processing Order, @Order, and Dependencies

There are two distinct kinds of ordering:

- **Order of elements in a Collection:** `List` is traversed by index; `Set` may not preserve insertion order unless using a type with that contract.
- **Order of listeners receiving the same event:** Spring can sort synchronous listeners via `@Order`/`Ordered`.

~~~java
@Order(10)
@EventListener
public void audit(NotificationRequested event) {
    // One listener receiving NotificationRequested.
}

@Order(20)
@EventListener
public void metrics(NotificationRequested event) {
    // Another listener receiving the same event.
}
~~~

This is illustrative code; it requires importing `org.springframework.core.annotation.Order` and registering the methods in a bean. The two methods are two independent subscribers; the requested order does not represent a transaction or multi-step workflow.

**Important:** `@Order` does not promise *completion* order for asynchronous listeners. Even if one listener is dispatched first, another worker can finish earlier.

If B must run **only after A succeeds**, express B as a follow-up event published **after A has completed** (or orchestrate within an ordered/transactional service). Do not emit two elements in the same list assuming the second element is processed only after all side effects of the first element succeed under every threading configuration.

### Collection Fan-Out Is Not a Parallelism Mechanism

Returning two events in a `List` does not mean they run on two threads. With the default multicaster, most of the execution path is **synchronous**. When fan-out aims to increase throughput, you must design an async executor, queue, or separate broker, and handle errors, ordering, and idempotency at the new boundary.

## 12. @Async: Do Not Publish New Events via Return Values

This is a limitation explicitly stated in Spring's documentation. Do not write:

~~~java
@Async("eventExecutor")
@EventListener
public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

The snippet above is an **anti-pattern**: for asynchronous listeners, Spring **does not support** automatically publishing follow-up events via the return value. Furthermore, `@Async` methods have a restricted return-type contract (typically `void` or a supported future type), so returning a `List` directly can also violate async rules.

The proper approach when asynchronous execution is required: inject `ApplicationEventPublisher` and **call publishEvent explicitly** inside the worker body.

~~~java
@Component
public class AsyncOrderRouter {

    private final ApplicationEventPublisher publisher;

    public AsyncOrderRouter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async("eventExecutor")
    @EventListener
    public void onOrderAccepted(OrderAccepted event) {
        List<NotificationRequested> followUps = List.of(
            new NotificationRequested(event.orderId(), "EMAIL"),
            new NotificationRequested(event.orderId(), "DASHBOARD")
        );

        for (NotificationRequested followUp : followUps) {
            publisher.publishEvent(followUp);
        }
    }
}
~~~

This is **integration code**, not a full demo file: it requires `@EnableAsync`, the `eventExecutor` bean, a Spring-managed `AsyncOrderRouter`, and imports for `@Component`, `ApplicationEventPublisher`, `@Async`, `@EventListener`, and the payload types. With Spring's proxy-based async, self-invocation can prevent `@Async` from taking effect.

There is no guarantee that the async callback finishes when the original thread's `publisher.publishEvent(OrderAccepted)` returns. Exceptions in the worker also do not propagate back to the publisher automatically; `AsyncUncaughtExceptionHandler`, logging/metrics, and an appropriate retry mechanism are needed if reliability matters.

If the system uses a custom `ApplicationEventMulticaster` with an executor, even listeners **without `@Async`** can be dispatched on another thread when the listener supports async. In that case, the completion and output-order assumptions of the synchronous example no longer hold.

## 13. Transactions, AFTER_COMMIT, and Follow-Up Events

Collection fan-out **does not open or commit transactions**. In default Spring Application Events, synchronous listeners are usually invoked on the publisher's thread; if the publisher is in a transaction, listeners can execute within that transaction. However, an emitted child event is **a new publication** and does not automatically carry its own transaction or guarantee committed data.

Suppose:

~~~java
@Transactional
public void createOrder(long orderId) {
    orderRepository.insert(orderId);
    publisher.publishEvent(new OrderAccepted("ORD-" + orderId));
    // The original transaction has usually not committed at publish time.
}
~~~

If `OrderEventRouter.route` returns notification requests before commit, the child event listener could send an email **before the DB transaction commits**. If the transaction rolls back afterward, the email is not automatically “rolled back”.

### When Fan-Out Is Needed After Commit

One option is registering a listener by transaction phase:

~~~java
@Component
public class AfterCommitRouter {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public List<NotificationRequested> onOrderAccepted(OrderAccepted event) {
        return List.of(
            new NotificationRequested(event.orderId(), "EMAIL"),
            new NotificationRequested(event.orderId(), "DASHBOARD")
        );
    }
}
~~~

This is an **integration snippet** requiring real Spring transactions, imports, and payload classes. It illustrates phase-based registration timing. **Do not assume child event listeners receive a new transaction**: `AFTER_COMMIT` runs once the original transaction has committed, though resources may still be bound to the thread during completion/cleanup. Returning a Collection does not make those child events durable, nor does it provide a second commit for subsequent writes.

If database reads/writes are needed while processing child events at this point, organize the logic in another bean with an appropriate transaction, often `REQUIRES_NEW` when an independent boundary is required, invoked through a Spring proxy. If events must not be lost on a crash between commit and publication, consider a **transactional outbox** rather than relying solely on an in-process callback.

### Note When There Is No Transaction

`@TransactionalEventListener` does not execute by default if the event is published without an active matching transaction (unless `fallbackExecution=true` is declared). That is why the pure `AnnotationConfigApplicationContext` example in section 5 uses regular `@EventListener`: it requires no transaction and runs standalone.

## 14. Exception in the Middle of an Event List: What Happens?

Suppose the initial listener returns:

~~~java
return List.of(
    new NotificationRequested("ORD-211", "EMAIL"),
    new NotificationRequested("ORD-211", "DASHBOARD")
);
~~~

If the subscriber handling `EMAIL` throws an exception under default synchronous dispatch, publishing `DASHBOARD` may **not happen** because the exception escapes before Spring reaches the second element. That differs from an all-or-nothing batch transaction:

~~~text
Parent event received
    |
    +-- EMAIL event
    |      +-- partial processing
    |      +-- exception!
    |
    +-- DASHBOARD event   (may not have been published)
~~~

Distinguish these cases:

- Failure inside the **Collection-building method**: if the method throws before returning, no collection is published by Spring from that invocation.
- Failure in the **first element's listener**: the first element may already have caused side effects; later elements may not be published yet.
- Failure in an **async listener**: may surface only on the worker thread without immediately stopping the publish loop on another thread.
- Failure caught/swallowed by the multicaster's **`ErrorHandler`** as configured: can behave differently from default exception propagation.

When business rules require that all child requests be processed or retried, persist them as durable records (outbox/job queue) or use an explicit workflow with per-step state.

**Do not use an empty catch-all** just to “publish the whole collection”. At a minimum, include logging, failure metrics, correlation IDs, and the ability to determine which elements succeeded.

## 15. eventId, aggregateId, and Preventing Erroneous Replays

A list of events generated from the same parent event should clearly maintain:

- **eventId**: uniquely identifies a single event occurrence; each child event needs its own ID if deduplication/replay is required.
- **aggregateId/orderId**: the business entity referenced by all these events.
- **correlationId**: tracking ID for a business chain spanning multiple events.
- **causationId**: ID of the event or command that caused the new event.
- **version/sequence**: when consumers must process updates for the same aggregate in order.

Illustrative payload schema example:

~~~java
public record FollowUpRequested(
    UUID eventId,
    UUID orderId,
    UUID correlationId,
    UUID causationId,
    String action
) {}
~~~

For the two actions `EMAIL` and `DASHBOARD` produced from the same parent event:

- Their `eventId` values should be **different**, as they are two distinct occurrences.
- `orderId` can be the same, since both belong to the same order.
- `correlationId` can be the same to group the steps.
- `causationId` can equal the parent event's `eventId` to indicate causality.

This is an **optional application-level design**, not fields Spring populates automatically on events. Simply having a method return a `List` does not generate IDs, deduplicate, provide transactions, or trace execution.

If a listener receives the same event again from a broker, deduplicating by `orderId` could mistakenly drop valid child events. Deduplicate by `eventId` or the true business key, and keep side effects idempotent.

## 16. Collection or Batch, Orchestrator or Outbox?

No single solution fits every business flow:

| Goal | Reasonable choice | Why |
|---|---|---|
| One event spawns a few synchronous in-process events | Return `List<Event>` from `@EventListener` | Concise, no need to call publisher repeatedly |
| One event spawns one follow-up event | Return a single event object | Direct, easy-to-understand contract |
| Multiple distinct event types with complex logic | Inject `ApplicationEventPublisher` and publish explicitly | Easy control over conditions, error reporting, and timing |
| Passing an entire batch as **one** business unit | Event record containing `List<Item>` | Consumer sees one batch and handles it as a whole |
| Tightly coupled steps with shared rollback | Service/orchestrator with explicit transaction | Event fan-out does not replace transactions |
| Independent, potentially slow, or heavy tasks | Async executor / queue with error policy | Isolates resources and protects publisher thread |
| Must recover after crash or restart | Transactional outbox + broker/worker | In-process Application Events are not a durable store |
| Preserve ordering and deduplicate across nodes | Version/sequence, partitioning, and idempotency | `List` does not guarantee end-to-end ordering |

### Transactional Outbox When Durability Is Required

A single transaction updates the order and writes child requests as outbox records:

~~~text
BEGIN TRANSACTION
  UPDATE orders ...
  INSERT INTO outbox(event_id=E1, type='EmailRequested', payload=...)
  INSERT INTO outbox(event_id=E2, type='DashboardRequested', payload=...)
COMMIT
    |
    v
Worker reads outbox, sends each message, and marks status
    |
    v
Consumer handles idempotently by eventId
~~~

When the transaction rolls back, both the order change and outbox entries roll back together if they share one local transaction. If the worker crashes after sending but before marking done, a message can be resent; therefore consumers must still tolerate duplicates. This mechanism solves a different requirement than returning collections from `@EventListener`.

## 17. Testing the Collection-Forwarding Mechanism

An effective test should verify **the exact types and counts of published events**, not just inspect logs.

### Case 1 — Two-element Collection

With the `CollectionForwardingDemo` example, expected result: exactly two `NotificationRequested` handlings (EMAIL, DASHBOARD) and exactly two `NotificationFinished` handlings. Because it is synchronous by default, assertions can run immediately after `context.publishEvent(...)`.

### Case 2 — Empty Collection

Change the router to return `List.of()`. Zero child events are processed. Also check the invocation count for `OrderAccepted` to avoid confusing “no child events” with “no parent event”.

### Case 3 — Array

Replace `List<NotificationRequested>` with `NotificationRequested[]`. Verify each array element is handled individually.

### Case 4 — Returning a Single Event

Change the router to return `NotificationRequested`. Then only one new event is emitted. Avoid adding unnecessary collection wrappers.

### Case 5 — Abnormal Loop

Test a chain with a clear termination condition, such as keeping `hopsRemaining` and decrementing it each step; test the hop limit. **Do not create an infinite A → B → A loop in tests** because it can hang the entire suite or overflow the stack.

### Case 6 — Exception on the First Element

Have the EMAIL subscriber intentionally throw an error and count DASHBOARD elements. Verify the behavior of the configured multicaster/`ErrorHandler`; do not write tests assuming handlers are always invoked for every element.

### Case 7 — Async

If switching to `@Async`, tests should use a completion signal like `CountDownLatch` or an await condition with a timeout. Do not assert immediately after `publishEvent(...)` assuming all child events have completed.

An illustrative integration test snippet following these principles:

~~~java
AtomicInteger received = new AtomicInteger();

@Component
class CountingListener {
    @EventListener
    public void onNotification(NotificationRequested event) {
        received.incrementAndGet();
    }
}

// After calling publishEvent in a synchronous context:
// assertEquals(2, received.get());
~~~

This is **illustrative test code**: it requires a Spring context registering `CountingListener`, importing `AtomicInteger`, `Component`, `EventListener`, and JUnit if `assertEquals` is used. Do not paste this snippet directly into the demo class without adding test configuration and dependencies.

### Properties to Assert in Tests

1. The parent event entered the expected listener method.
2. Each collection element is a separate **publication** of the right runtime event type.
3. An empty collection produces no new events.
4. `eventId`/`correlationId` relationships are preserved when needed.
5. Exceptions/async/transactions are not misinterpreted as all-or-nothing guarantees.
6. If element selection logic exists, verify the filtered list contains no nulls, unintended duplicates, or excessive items.

## 18. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Receiving a single `List`-typed event instead of items | Calling `publisher.publishEvent(list)` directly | Have `@EventListener` **return** the collection, or loop and call publisher manually |
| Listener does not receive child events | Unregistered bean, wrong event type, missing annotation infrastructure | Check bean registration, `@EventListener`, and context setup |
| Returned collection is ignored | Listener runs with `@Async` | Use `void @Async` and explicit `ApplicationEventPublisher.publishEvent` |
| Log line after `publishEvent` appears before child events | Async executor or custom multicaster configured | Do not infer from log order; use latches/metrics |
| One failing child event leaves later items unprocessed | Synchronous dispatch hit an exception | Define an `ErrorHandler` and use workflows/outbox if needed |
| Infinite recursion/stack overflow | Listener emits an event type leading back to itself | Design type transitions/guards/hop limits |
| Duplicate events sent | Collection contains duplicates or upstream retries | `eventId`/idempotency and assert publish counts in tests |
| Unexpected ordering | `Set` does not keep insertion order, async, multiple listeners | Use `List` for iteration order, but do not rely on end-to-end ordering |
| Email sent before DB commit | Child listener runs synchronously inside original transaction | Use proper transaction phase or outbox |
| Consumer reads stale/missing data | Async runs before commit or replica lag | Design explicit transaction/read consistency |
| One event needed batch handling but got split | Returning `List<ItemEvent>` from listener | Create `BatchRequested(List<Item>)` as a single event payload |
| App slows down or exhausts threads | Unbounded fan-out, blocking side effects | Bound fan-out, executor/queues, and backpressure |
| Cannot recover after restart | In-process events are not persisted durably | Outbox/job queue/broker and idempotency |

## 19. Production Design Checklist

Before choosing to return a collection, answer:

1. **Which event triggers it?** Define the input payload class clearly.
2. **What is each element?** It must be a meaningful event, not an arbitrary data object.
3. **How many child events can be emitted?** Is fan-out bounded to avoid task/memory explosion?
4. **Is the collection ordered?** If order is needed, use a type with the right contract; still do not confuse it with async completion order.
5. **Is the listener synchronous or asynchronous?** Only expect return-value forwarding when the listener is synchronous.
6. **What happens if the k-th element fails?** Have earlier elements caused side effects, and is there retry/compensation?
7. **Can event loops happen?** Distinguish input/output event types and termination conditions.
8. **Which transaction is active?** Are child events published before or after commit, and can they access stale resources?
9. **Is durability required?** If processing must survive crashes, design an outbox or queue.
10. **Can duplicates arrive?** Use `eventId`, version, and consumer idempotency.
11. **Is an atomic batch needed?** If so, do not treat returning a collection as a transaction.
12. **Do tests verify event counts?** Including empty collections, failure on the first element, async, and multi-level chains.

## 20. Summary

In Spring Framework, an `@EventListener` method can return **a single event** for Spring to publish onward, or return a **`Collection`/array** for Spring to publish **each element as a separate event**. This is a concise way to write **synchronous event fan-out and event chaining**. The `OrderAccepted → List<NotificationRequested> → NotificationFinished` example shows Spring can form multi-level chains without each listener injecting `ApplicationEventPublisher`.

The key point is that **only returning a collection from a listener triggers the automatic element-unpacking rule**; calling `publishEvent(list)` directly is not equivalent. Do not use return-value forwarding on `@Async` listeners, do not expect elements to run in parallel or complete in strict order, and do not treat event chains as transactional workflows or durable queues. When strict error handling, ordering, idempotency, and durability are required, add an orchestrator, proper transactions, an outbox, or a message broker.

### Official References

- [Spring Framework 6.2 Reference — ApplicationContext Events and @EventListener](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — non-void returns, collection/array forwarding, async listeners, and ordering.
- [Spring Framework Javadoc 6.2 — EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html) — contract for return values.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html) — event-publishing API within a context.
- [Spring Framework Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html) — sync/async dispatch, task executor, and error handler.
- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — transaction phases and `@TransactionalEventListener`.
