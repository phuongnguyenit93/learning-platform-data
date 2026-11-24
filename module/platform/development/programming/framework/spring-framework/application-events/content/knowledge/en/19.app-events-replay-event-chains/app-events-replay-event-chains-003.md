# A Listener Returning Multiple Events in Spring Framework Application Events

## 1. Idea: One Input Event Produces Multiple Follow-Up Events

In Spring Framework, a method annotated with `@EventListener` **does not have to return `void`**. If the method returns a non-`null` value, Spring can **publish that value onward as a new application event**. In particular, **if the result is a `Collection` or an array, each element is published as a separate event**.

This is a concise way to express an event processing chain (event chaining) or branching (fan-out):

~~~text
ApplicationEventPublisher.publishEvent(OrderPlaced)
          |
          v
@EventListener
List<Object> classifyAndDecide(OrderPlaced)
          |
          +-- returns OrderSizeClassified
          |          |
          |          +--> @EventListener onSizeClassified(...)
          |
          +-- returns ReviewDecisionCalculated
                     |
                     +--> @EventListener onReviewDecision(...)
                                  |
                                  +-- returns ReviewPathSelected
                                             |
                                             +--> @EventListener onReviewPath(...)
~~~

Each returned element is **an independent event message**, which Spring can route to different listeners according to its object type. This differs from returning `List<Order>` in an ordinary business method: when a listener returns a `Collection`, Spring **does not treat the entire list as a single event payload** under `@EventListener`'s return-value publication mechanism.

**Scope of this lesson:** `@EventListener`'s mechanism for returning multiple events within the same `ApplicationContext`, how to build event chains, error/loop control, transaction interaction, and replay limitations. This is not a message broker mechanism and does not provide durable persistence or historical replay by itself.

## 2. Official Rules of @EventListener

Spring processes the result of a listener method as follows:

| Return value type | Typical behavior |
| --- | --- |
| `void` | Publishes no additional events via the return value. |
| A non-`null` object, e.g., `OrderChecked` | Publishes that object as **one new event**. |
| `List<?>`, `Set<?>`, or `Collection<?>` | Publishes **each element** as a separate event. |
| An array, e.g., `Object[]` or `OrderChecked[]` | Publishes **each element** as a separate event. |
| `null` | No result to publish further. |
| Empty collection/array | No elements, so no follow-up event is published from the result. |
| Listener using `@Async` | **Cannot use the return value to publish follow-up events**; must call `ApplicationEventPublisher` directly if further publication is needed. |

Short example with a single result:

~~~java
@EventListener
public OrderChecked check(OrderPlaced event) {
    return new OrderChecked(event.orderId());
}
~~~

Example returning **two events of different types**:

~~~java
@EventListener
public List<Object> route(OrderPlaced event) {
    return List.of(
        new OrderIndexed(event.orderId()),
        new OrderAuditPrepared(event.orderId()));
}
~~~

Example returning an array:

~~~java
@EventListener
public Object[] routeAsArray(OrderPlaced event) {
    return new Object[] {
        new OrderIndexed(event.orderId()),
        new OrderAuditPrepared(event.orderId())
    };
}
~~~

*The examples in this section are illustrative integration snippets: `OrderPlaced`, `OrderChecked`, `OrderIndexed`, and `OrderAuditPrepared` are hypothetical domain types; you must declare the types, import `@EventListener` and `java.util.List`, and place the methods inside a Spring bean. A complete runnable Maven/Java 17+ example is in section 4.*

Several things to keep in mind:

- Spring relies on the **actual returned value** to publish the next event, not on the method name or a variable named `result`.
- A returned event can be a custom `ApplicationEvent` or a plain **payload object** such as a Java record; for payload objects, Spring uses the `PayloadApplicationEvent` mechanism.
- `List<Object>` is useful when you need to return **different event types**. `List<OrderChecked>` makes sense when all events have the same type.
- Do not use a list containing `null` elements to express “skip an event”; only add valid elements. `List.of(...)` inherently disallows `null` elements.
- If publication order during fan-out matters, use an explicitly ordered structure such as `List.of(...)` or an array; **do not rely on the iteration order of `HashSet`**.

Spring's documentation states clearly: a listener returning an event triggers publication of that event; if multiple events are needed, return a `Collection` or array. This mechanism **does not support return-value publication for asynchronous listeners**.

## 3. What Happens After Returning?

In Spring's default synchronous flow:

1. A component calls `applicationEventPublisher.publishEvent(originalEvent)`.
2. `ApplicationEventMulticaster` delivers the event to matching listeners.
3. `@EventListener` executes; code inside can verify conditions, read data, and build results.
4. If the method returns a `Collection`/array, the listener infrastructure iterates over the elements and publishes each element as a new event.
5. Each new event is distributed by the multicaster to listeners matching its type. Another listener can in turn return an event, forming a multi-level chain.
6. Only when the entire synchronous chain finishes does the initial `publishEvent(...)` call return normally.

Timing diagram when **not using `@Async` or a multicaster executor**:

~~~text
Caller                       Spring event infrastructure
  |                                      |
  | publishEvent(OrderPlaced)            |
  |------------------------------------->|
  |                       invoke handler(OrderPlaced)
  |                       handler returns List[A, B]
  |                       publish A
  |                         invoke listener(A)
  |                       publish B
  |                         invoke listener(B)
  |                         listener(B) returns C
  |                         publish C
  |                           invoke listener(C)
  |<-------------------------------------|
  | publishEvent(...) returned           |
~~~

“Publish onward” here means **publication within the same event system**, not automatically writing events to a database or queue. If a listener receives the exact same event type that it always emits onward, the program can recurse infinitely. If a listener throws an unhandled exception, the entire synchronous chain can be interrupted before all remaining elements are published.

**Do not infer global ordering guarantees from this diagram.** In the synchronous example, a `List` is traversed in element order and child calls can run nested. However, when multiple listeners register for the same type, `@Order` is used, a custom multicaster is present, or async processing is enabled, ordering among listeners and completion timing can differ. If the system must guarantee business ordering, design explicit orchestration rather than relying solely on event fan-out side effects.

## 4. Complete Example: Java 17+ and Spring Framework 6.2

This example uses an `@EventListener` that receives `OrderPlaced` and returns **two events of different types** in `List<Object>`:

- `OrderSizeClassified`: the result of classifying order size based on item count.
- `ReviewDecisionCalculated`: the result determining whether manual review is needed.

The listener for `ReviewDecisionCalculated` also returns `ReviewPathSelected`, demonstrating a **two-level event chain**. Each event is handled by exactly one listener matching its type, making stdout lines verifiable.

No Spring Boot, database, broker, or executor is used so the core mechanism remains clear.

### 4.1. Project Structure

~~~text
event-fan-out-demo/
├── pom.xml
└── src/main/java/EventFanOutDemo.java
~~~

Requirements: JDK 17+, Maven 3.8+, and permission to download Maven libraries on the first run.

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-fan-out-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

### 4.2. Full Source Code

`src/main/java/EventFanOutDemo.java`:

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventFanOutDemo {

    public record OrderPlaced(String orderId, int itemCount) {}

    public record OrderSizeClassified(
            String orderId, String size) {}

    public record ReviewDecisionCalculated(
            String orderId, boolean required) {}

    public record ReviewPathSelected(
            String orderId, String path) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public EventHandlers eventHandlers() {
            return new EventHandlers();
        }
    }

    public static class EventHandlers {

        @EventListener
        public List<Object> classifyAndDecide(OrderPlaced event) {
            System.out.println("A: OrderPlaced " + event.orderId());

            String size = event.itemCount() >= 3
                    ? "LARGE" : "SMALL";
            boolean manualReview = event.itemCount() >= 3;

            // One listener emits TWO events of different types.
            return List.of(
                new OrderSizeClassified(event.orderId(), size),
                new ReviewDecisionCalculated(
                    event.orderId(), manualReview));
        }

        @EventListener
        public void onSize(OrderSizeClassified event) {
            System.out.println("B: Size " + event.size());
        }

        @EventListener
        public ReviewPathSelected onDecision(
                ReviewDecisionCalculated event) {
            System.out.println(
                "C: Review required=" + event.required());

            String path = event.required()
                    ? "MANUAL" : "AUTO";
            return new ReviewPathSelected(
                    event.orderId(), path);
        }

        @EventListener
        public void onPath(ReviewPathSelected event) {
            System.out.println("D: Path " + event.path());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("BEGIN");
            context.publishEvent(new OrderPlaced("ORD-7", 4));
            System.out.println("END");
        }
    }
}
~~~

Even though `classifyAndDecide(...)` returns `List<Object>`, the elements retain their distinct runtime types. Spring publishes `OrderSizeClassified` and `ReviewDecisionCalculated` as two independent events, so the typed listeners `onSize(...)` and `onDecision(...)` are invoked. `onDecision(...)` in turn returns a `ReviewPathSelected`, which is delivered to `onPath(...)`.

### 4.3. Compiling and Running

In the `event-fan-out-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventFanOutDemo
~~~

Output printed by the program itself with the default synchronous multicaster (excluding Maven logs):

~~~text
BEGIN
A: OrderPlaced ORD-7
B: Size LARGE
C: Review required=true
D: Path MANUAL
END
~~~

### 4.4. Why Is That Order Deterministic in This Example?

- `BEGIN` is printed before calling `context.publishEvent(...)`.
- `A` is printed by the sole listener `classifyAndDecide` subscribed to `OrderPlaced`.
- The listener returns `List.of(sizeEvent, decisionEvent)`: Spring publishes the first element, so `onSize` prints `B`.
- Spring proceeds to publish the second element. `onDecision` prints `C` and returns `ReviewPathSelected`; Spring publishes that second-level event, causing `onPath` to print `D`.
- After the synchronous listeners finish, `publishEvent(...)` returns and `main` prints `END`.

**Limitations of the example:** no database transactions, no `@Async`, no competing listeners of the same type, and no custom multicaster registered. If you add async or change the dispatch mechanism, do not treat this stdout order as a system-wide guarantee for your application.

## 5. Collection and Array: Same Publication Behavior, Different Representation

To return multiple events, the two forms directly supported by Spring are `Collection` and arrays. Choose based on expressiveness:

### 5.1. Returning a List

~~~java
@EventListener
public List<Object> handle(PaymentConfirmed event) {
    return List.of(
        new ReceiptReady(event.paymentId()),
        new LoyaltyPointsReady(event.paymentId()));
}
~~~

*Illustrative snippet inside a Spring bean; `PaymentConfirmed`, `ReceiptReady`, and `LoyaltyPointsReady` are hypothetical types that must be defined before use.*

`List` preserves positional order of elements, makes it easy to construct dynamic event counts using `ArrayList`, and is easy to test. A method can return `List<ReceiptReady>` if it only emits events of the same type; `List<Object>` can hold multiple types.

### 5.2. Returning an Array

~~~java
@EventListener
public Object[] handleBatch(BatchAccepted event) {
    return new Object[] {
        new BatchIndexed(event.batchId()),
        new BatchAuditCreated(event.batchId())
    };
}
~~~

*Illustrative integration snippet; `BatchAccepted` and the produced events are application-defined business classes/records.*

Arrays also preserve index order and have a fixed length at return time. If elements have multiple types, use `Object[]`; if they share the same type, you can use `EventType[]`.

### 5.3. Returning No Events

~~~java
@EventListener
public List<Object> onOrderPlaced(OrderPlaced event) {
    if (event.itemCount() == 0) {
        return List.of();
    }
    return List.of(new OrderSizeClassified(
        event.orderId(), "NON_EMPTY"));
}
~~~

*Illustrative snippet above; it does not replace the method in the runnable example in section 4. A zero-item order should be treated as invalid at the business layer if that is a system constraint.*

An empty list means there are no follow-up events. Returning `null` can also suppress event emission, but using an empty collection is usually clearer and cleaner when the method's contract works with collections. Do not use `List.of(null)` because it throws `NullPointerException`.

### 5.4. Do Not Confuse a Collection Payload with a Collection Return Value

~~~java
// Case A: Returning a collection from a listener => multiple events.
@EventListener
public List<ReportReady> onBatch(BatchCreated event) {
    return List.of(
        new ReportReady("R-1"),
        new ReportReady("R-2"));
}
~~~

*The classes in the snippet above are illustrative types.*

In Case A, Spring publishes **two `ReportReady` events**. If the requirement is a single event containing a list of reports, design a **wrapper event**:

~~~java
public record ReportsReady(List<String> reportIds) {
    public ReportsReady {
        reportIds = List.copyOf(reportIds);
    }
}

@EventListener
public ReportsReady onBatch(BatchCreated event) {
    return new ReportsReady(List.of("R-1", "R-2"));
}
~~~

This is **one `ReportsReady` event** with a collection property, rather than two separate events. This distinction directly affects how many times downstream listeners are invoked.

## 6. Event Chaining, Fan-Out, and Ordering Concerns

### Fan-out

**One input event → multiple output events**. For example, `OrderPlaced` produces two independent derived facts: order classification and whether review is needed. This allows separating consumers by responsibility:

~~~text
OrderPlaced
   |
   v
Producer listener
   |---> OrderSizeClassified ---> MetricsListener
   |
   +---> ReviewDecisionCalculated ---> ReviewListener
~~~

### Chaining

**One output event → another listener → another new event**. For example, `ReviewDecisionCalculated` leads to `ReviewPathSelected`. This can form a multi-level event pipeline:

~~~text
OrderPlaced
  -> ReviewDecisionCalculated
       -> ReviewPathSelected
            -> ReviewQueueEntryCreated
~~~

A name like `ReviewQueueEntryCreated` in an example is only valid if a step actually created the queue entry successfully before publishing the event; **do not use past-tense fact names when only an intention to act exists**.

### Differences from Imperative Sequential Processing

Calling `eventPublisher.publishEvent(...)` creates **implicit coupling** between beans: the publisher does not directly invoke a specific business method. The benefit is easy extensibility, while the cost is harder traceability of execution paths, error handling, and testing if there are too many layers.

If the business process **must** execute steps in strict order, where a prior step's result determines the next step and complex rollback/compensation is needed, a directly coordinating application service (or workflow engine when appropriate) can be clearer than a recursive listener chain.

**`@Order` only helps order listeners subscribed to the same event** under Spring's contract; it does not turn a complex fan-out chain into a durable sequential transaction. With executors or async processing, ordering guarantees must be designed into the processing system itself.

## 7. Loop Pitfall: Re-Emitting the Same Input Event Type

A dangerous bug:

~~~java
@EventListener
public OrderPlaced onOrderPlaced(OrderPlaced event) {
    return event; // Re-publishes the exact OrderPlaced event type.
}
~~~

*This code illustrates an anti-pattern, not an example to run.*

With the default synchronous event mechanism, upon receiving `OrderPlaced`, the listener returns `OrderPlaced`, Spring publishes `OrderPlaced` again and invokes **the same listener**; this loop can continue until recursion/stack overflow occurs or an application-built safeguard trips.

Similarly, a two-event chain can form a cycle:

~~~text
A --> listener(A) returns B
B --> listener(B) returns A
A --> ...
~~~

How to prevent this:

1. Build a directed graph of event types, distinguishing source events from derived events.
2. Do not let a listener's output event trigger the same listener unless a verified stopping condition is enforced.
3. If multiple processing rounds are needed, use an explicit state machine/workflow with forward transitions and a step limit.
4. Include `eventId`, correlation/causation IDs, and appropriate processing state to trace chains.
5. For broker-based systems or retried jobs, apply idempotency, dead-letter queues, retry limits, and loop detection.

**Do not try to “solve” a loop by switching to `@Async`.** That merely turns the cycle into a storm of tasks/threads instead of fixing the root loop condition.

## 8. Special Limitation of @Async

`@EventListener` documentation specifies that **asynchronous listener methods cannot publish follow-up events simply via their return value**. If a listener has `@Async` and needs to create a follow-up event, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly.

Proper pattern:

~~~java
@Component
class AsyncOrderListener {

    private final ApplicationEventPublisher publisher;

    AsyncOrderListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void afterOrderPlaced(OrderPlaced event) {
        OrderSizeClassified size = new OrderSizeClassified(
                event.orderId(), "LARGE");
        publisher.publishEvent(size);
    }
}
~~~

*This is an illustrative Spring bean snippet: it requires importing `@Component`, `@Async`, `@EventListener`, and `ApplicationEventPublisher`; `OrderPlaced`/`OrderSizeClassified` must be defined, and the application must enable `@EnableAsync` with a suitable executor. This is not standalone runnable code.*

Do not expect that:

~~~java
@Async
@EventListener
public List<Object> afterOrderPlaced(OrderPlaced event) {
    return List.of(new OrderSizeClassified(event.orderId(), "LARGE"));
}
~~~

will automatically republish `OrderSizeClassified`. Async configuration changes how the method is invoked and how its result is handled. Spring explicitly documents that **return-value publication is not supported for asynchronous listeners**. The `return List` sample above is shown only to explain what **not to rely on**, not as a recommended design.

Differences related to async:

| Aspect | Default synchronous listener | `@Async` listener |
| --- | --- | --- |
| Execution context | Usually on the event-publishing thread. | On an executor thread. |
| Returning event / collection to publish | **Supported**. | **Not supported**. |
| How to publish the next event | Return a result or call publisher. | Call `ApplicationEventPublisher.publishEvent(...)` directly. |
| Exceptions | Can propagate back to publisher if uncaught. | Do not return to caller thread automatically; must configure exception handling. |
| ThreadLocal transaction / logging | Current thread context is visible during synchronous execution. | Not automatically transferred in full to another thread. |
| Completion order | Follows synchronous call stack in simple examples. | Should not expect completion order without coordination. |

Even just configuring the multicaster with an executor can change dispatch timing. Therefore, the deterministic stdout example in section 4 applies to the default multicaster, not to every listener configuration in production systems.

## 9. Transaction Interaction: Multiple Events Do Not Equal Multiple Commits

Suppose an `@Transactional` service publishes `OrderPlaced` and a synchronous listener returns two events `A` and `B`. If all of them run **on the same thread and within the active transaction**, downstream listeners can participate in that transaction according to the transaction manager configuration.

~~~text
@Transactional service
   |
   | DB changes (not yet committed)
   | publishEvent(OrderPlaced)
   |    -> fanOut returns [A, B]
   |       -> listener(A) (may be inside the active transaction)
   |       -> listener(B) (may be inside the active transaction)
   |
   | service finishes
   v
Transaction manager commits or rolls back
~~~

However, “returning two events” **does not automatically open two new transactions**, does not commit after each event, and does not guarantee that listeners with side effects will roll back uniformly across all configurations (e.g., external systems, async, or different propagation settings).

### BEFORE_COMMIT and AFTER_COMMIT

If an event must be published **only after the original transaction has committed successfully**, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for reactive logic. However:

- At `AFTER_COMMIT`, the original commit is already finished. Additional database writes need an explicit new transaction, typically `REQUIRES_NEW` in an imperative model when appropriate.
- Separate **choosing when** to run from **emitting multiple events**. Do not treat a post-commit event chain as a continuation of the old commit.
- Do not use `@Async` to fake transaction boundaries; async switches threads and does not automatically inherit the publisher's transaction.
- `@TransactionalEventListener` by default runs only when a matching transaction is present, unless `fallbackExecution = true` is set.

You should test commit/rollback paths on a real system when combining `@TransactionalEventListener` with fan-out; do not infer durability guarantees from the annotation name alone.

## 10. “Re-publishing” Derived Events Differs from Historical “Replay”

Under the topic “Replay and Event Chains”, two concepts are easily confused:

**Re-publish / publish derived event:** a listener returns one or more objects so Spring **publishes new events right while the application is running**. For example, `OrderPlaced` → `OrderSizeClassified` + `ReviewDecisionCalculated`. That is the mechanism being studied here.

**Replay:** re-reading **previously stored** events (from an event store, log, outbox, or broker) and re-applying them to consumers to rebuild projections or recover state. Spring Application Events by default **does not persist event history, has no offsets, and provides no API to replay old events**.

The two behaviors can interact: when a system outside Spring pulls historical `OrderPlaced` events and calls `publisher.publishEvent(...)`, a fan-out listener will regenerate derived events unless logic is designed differently for replay mode. That can:

- Re-trigger old side effects such as sending emails, awarding loyalty points, or calling payment APIs.
- Create duplicate records if the database/repository lacks idempotency keys.
- Emit new events with different IDs/timestamps, making the audit trail hard to trace back to the original cause.
- Cause discrepancies if the fan-out algorithm changed between the historical version and the current one.

**Do not replay an event assuming all listeners are “safe to re-run”.** With an event store or broker, explicitly define the replay policy, idempotency keys, whether external side effects should run, and the contract/algorithm version used to reconstruct data.

### Example Idempotency Rule

If the `PaymentCaptured` handler saves an audit row keyed by `eventId`, you can place a unique constraint on `(consumerName, eventId)` and handle duplicates within the appropriate transaction. If the same event is redelivered, the consumer checks/records processing so side effects are not produced twice.

However, “check if exists, then insert” without an appropriate constraint/transaction still suffers from race conditions. For external side effects like sending email, you usually need an outbox/inbox, a partner-side idempotency key, or a delivery mechanism designed to tolerate retries.

## 11. Exceptions and “Partial Fan-Out”

Suppose a listener returns two events `A` and `B`, each with its own handler.

With the default synchronous multicaster, if `A`'s handler throws an unhandled exception:

~~~text
OriginalEvent
    |
    +--> returns [A, B]
                |
                +--> publish A
                         |
                         +--> handler(A) throws exception
                |
                +--> publish B  [may NOT occur]
~~~

Because publishing the list sequentially happens on the synchronous call path, an exception can halt processing before Spring publishes `B`. This causes **partial fan-out**: one event was published/processed, while the remaining event was not.

How to handle this depends on requirements:

- If both steps must succeed or roll back together, consider handling them inside an appropriate application service/transaction instead of treating event fan-out as a distributed transaction.
- If each step is independent and needs retries, consider delivering via a durable queue/outbox with idempotent consumers.
- If you want to continue even when one listener fails, configure the multicaster's `ErrorHandler` intentionally and monitor errors; do not merely swallow exceptions silently.
- If the input event is later replayed, ensure steps that already ran do not produce duplicate side effects.

**There is no atomic publication guarantee** for multiple returned elements in default Spring Application Events: returning a `List` does not turn it into a transactional message batch.

## 12. When to Return a Collection vs. Call publishEvent Manually

| Need | Appropriate approach |
| --- | --- |
| A synchronous listener produces a few concise derived events | Return `List<?>` or an array from `@EventListener`. |
| A listener returns a single derived event | Return a single event object. |
| No event when a condition is not met | Return empty `List.of()`/array, or `null` when the return type allows and conventions are clear. |
| Multiple events of the same type | `List<SomeEvent>` or `SomeEvent[]`. |
| Multiple events of different types | `List<Object>` or `Object[]`. |
| Listener runs with `@Async` | Inject `ApplicationEventPublisher` and publish each event via explicit calls. |
| Need to publish events at different points inside the same method | Use explicit `publishEvent(...)` at the exact spots, which a single end-of-method return value cannot achieve. |
| Need strict business orchestration or atomic state changes | Application service/transaction/workflow; events are secondary signals. |
| Need guaranteed cross-process delivery or historical replay | Broker/outbox/event store with contracts, retries, and idempotency. |

### Comparing the Two Styles

**Returning a collection:**

~~~java
@EventListener
public List<Object> onSource(SourceEvent e) {
    return List.of(new EventA(e.id()), new EventB(e.id()));
}
~~~

**Explicit publishing:**

~~~java
@EventListener
public void onSource(SourceEvent e) {
    publisher.publishEvent(new EventA(e.id()));
    publisher.publishEvent(new EventB(e.id()));
}
~~~

*Both snippets are illustrative; the event types and `publisher` bean must be defined. In the second style, inject `ApplicationEventPublisher` into the Spring bean.*

Both styles can achieve similar results in a simple application with synchronous listeners, but **publication timing differs**: return-value publication happens only after the listener method returns; manual publish calls happen immediately at that point inside the method. This affects error handling, transactions, state changes, and observed ordering.

Do not treat return-value callbacks as a result-returning API for the publisher. `publishEvent(...)` returns `void`; new events are published by Spring through the multicaster rather than becoming the original caller's return value.

## 13. Testing Event Chains and Diagnosing in Practice

A sound test suite for listeners returning multiple events should verify:

1. Correctly typed input invokes only the corresponding listener.
2. A two-element `List` leads to **two publications** of the exact event types, not one event with a list payload.
3. A downstream event element can produce a next-level event when needed.
4. `List.of()` emits no additional events.
5. Business conditions for each event type match the input payload.
6. No infinite A → B → A loops exist.
7. If transactions are involved, rollback and commit paths behave according to expected semantics.
8. If async is used, tests wait via synchronization/await rather than asserting arbitrary thread ordering.
9. If retry/replay is used, consumers do not create duplicate side effects for the same `eventId`.
10. A failure in the first handler does not falsely record all derived events as completed.

You can write a Spring integration test creating an `AnnotationConfigApplicationContext` as in section 4 and replace `System.out.println(...)` with a collector/test probe (for example, a synchronized `List`, or a `BlockingQueue` if async is needed). After calling `publishEvent(...)` in a **synchronous** setup, assert the count/types of received events and updated states. To test re-entrancy/re-execution, publish the same input twice and assert duplicate-handling logic according to business rules.

### Logging and Tracing

To understand long event chains, log at a minimum:

- `eventType` and `eventId` of each occurrence, avoiding confusion with the aggregate ID.
- `correlationId` to link events belonging to the same business flow.
- `causationId` of the parent event when derived chains exist.
- `handler`, transaction phase (if any), start/end timestamps, and outcome.
- Warnings when a chain reaches an unusual depth or event count.

Do not log full payloads containing sensitive data. When calling external services, add explicit timeouts, metrics, and retry/idempotency rather than expecting internal events to manage failures on their own.

## 14. Common Mistakes to Avoid

1. **Assuming `List<Event>` is a single event.** Returning a `Collection` in `@EventListener` makes Spring publish each element. If you need one event containing a list, put the list inside a wrapper payload.
2. **Adding `@Async` and still expecting Spring to publish the return value.** Not supported; call the publisher manually.
3. **Creating cycles of event types.** A listener returns the same input type or creates A → B → A with no stopping condition.
4. **Failing to distinguish new events from replayed events.** Return-value publication provides neither event history nor retry mechanisms.
5. **Depending on the ordering of multiple listeners in an async setup.** Dedicated coordination/ordering must be designed.
6. **Passing mutable JPA entities as payloads to multiple listeners.** Handlers can see unexpectedly mutated data or hit expired transactions/sessions.
7. **Believing successful publication means the business operation committed.** Sync events may run before transaction commit; async runs in a different transaction context.
8. **Ignoring child listener exceptions.** If a downstream listener throws, publishing subsequent elements can be interrupted; an error policy is required.
9. **Returning a `HashSet` and expecting fixed publication order.** Use `List` or an array if element order matters.
10. **Assuming all derived events are durably delivered.** In-JVM event multicasting is not a durable broker; an outbox/queue is required when events must not be lost.
11. **Letting multiple listeners quietly mutate the same state.** Fan-out separates concerns; it does not replace transaction coordination when strict invariants are required.
12. **Confusing `@EventListener`'s return value with `ApplicationEventPublisher.publishEvent(...)`'s return value.** The publisher does not return the event chain result to the caller; the return value is used by the framework to emit new events.

## 15. Self-Check Exercises

**Question 1.** An `@EventListener` returns `List.of(new A(), new B())`. How many events does Spring publish?

**Answer:** Two separate events, one for object `A` and one for object `B`. Listeners registered for each type are invoked if configured appropriately.

**Question 2.** If you want to publish **one event** carrying a list of 10 IDs, should you return `List<String>` directly from the listener?

**Answer:** No. Under return-value publication, collection elements are published individually. Define a wrapper such as `IdsReady(List<String> ids)` and return a single `IdsReady` object.

**Question 3.** Why does the runnable example in section 4 print `D: Path MANUAL` before `END`?

**Answer:** The synchronous listener `onDecision(...)` returns `ReviewPathSelected`; the framework publishes that event and runs `onPath(...)` before the initial `publishEvent(OrderPlaced)` call returns.

**Question 4.** Can an `@Async @EventListener` return `List<Object>` so Spring automatically publishes the events in the list?

**Answer:** No. Spring documentation specifies that publishing follow-up events via the return value of an asynchronous listener is not supported. `ApplicationEventPublisher` must be used explicitly.

**Question 5.** If the listener for event `A` throws an exception before the publisher emits `B`, is `B` guaranteed to still be published?

**Answer:** No. Under the default synchronous mechanism, an unhandled exception can interrupt publication of the remaining elements. Proper error handling must be built.

**Question 6.** Does returning a collection from a listener mean Spring saved the collection to an event store for replay after a JVM restart?

**Answer:** No. It only publishes derived events to the current multicaster; if durable replay is needed, the system must persist, distribute, and manage IDs/versions separately.

**Question 7.** With `List.of(new A(), new B())`, how can a listener receiving `B` produce an additional `C`?

**Answer:** A bean with an `@EventListener` receives `B` and returns object `C`; Spring continues publishing `C` to matching listeners, creating a multi-level event chain.

## References

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `@EventListener`, returning events, collection/array support, ordering, and async limitations.
- [Spring Framework Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): return-value handling rules and the asynchronous listener exception.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)` and payload event mechanism.
- [Spring Framework Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): default synchronous dispatch and executor/error-handling configuration.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and commit/rollback phases.
