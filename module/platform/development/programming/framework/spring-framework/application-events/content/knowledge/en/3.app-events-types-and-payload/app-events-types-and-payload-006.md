# Nested Events and Derived Data

## Objectives

After this lesson, you can describe how a listener publishes additional events while handling another event, distinguish nested events from derived events produced by an @EventListener return value, predict execution order under synchronous dispatching, and design event chains that avoid loops or implicit dependencies.

## 1. What Is a Nested Event?

A nested event occurs when a listener currently handling an event publishes another event via ApplicationEventPublisher.

For example, when receiving OrderPlaced, a listener can publish OrderAuditRecorded to ask another listener to record history. The second event is published while the first event is still being processed.

The two events have different meanings:

- OrderPlaced notifies that an order has been created.
- OrderAuditRecorded notifies that an audit record has been created or needs to be processed.

The second event does not replace the first event. It describes a subsequent occurrence in the business chain.

The original publisher does not need to know about this chain of reactions. It only publishes OrderPlaced. A listener receiving the event can publish additional events if doing so belongs to its responsibility.

## 2. Execution Flow When a Listener Publishes a New Event

Under the default configuration, SimpleApplicationEventMulticaster invokes listeners synchronously on the event-publishing thread. When a listener calls publishEvent again, the second publish is handled immediately within the current call.

Example sequence:

~~~text
Publisher publishes OrderPlaced
        |
        v
OrderPlacedListener starts processing
        |
        | publishEvent(OrderAuditRecorded)
        v
ApplicationContext dispatches OrderAuditRecorded
        |
        v
AuditListener finishes processing
        |
        v
Return to OrderPlacedListener
        |
        v
OrderPlacedListener continues and finishes
~~~

This is a synchronous nested call flow. AuditListener is invoked before the publishEvent(OrderAuditRecorded) call returns; only afterward does OrderPlacedListener continue to its next line of code.

If another listener also receives OrderPlaced, the order among listeners accepting the same event is controlled by Ordered or @Order. With nested events, listeners of the child event can run right in the middle of processing a listener of the parent event. Therefore, do not infer global ordering solely from bean declaration order.

### Distinguishing Two Moments

- **Parent event published**: the publisher begins dispatching OrderPlaced.
- **Child event published**: the OrderPlaced listener calls publishEvent for OrderAuditRecorded.

The parent event has not necessarily finished its entire dispatch process when the child event is published. Another listener for the parent event may still run after the child event has finished processing.

## 3. What Is Derived Data?

Derived data is data computed or aggregated from a previous event's data to describe a result or a subsequent processing need.

For example, OrderPlaced contains the order ID and subtotal. A listener can compute tax and grand total and publish InvoicePreparationRequested with those calculated values:

~~~java
BigDecimal tax = subtotal.multiply(new BigDecimal("0.10"));
BigDecimal grandTotal = subtotal.add(tax);

return new InvoicePreparationRequested(
        orderId, subtotal, tax, grandTotal);
~~~

The new event's payload is a business-meaningful snapshot. The listener receiving the new event does not have to recompute the same formula or read the entire object of the old event.

A derived event should answer three questions:

1. Which occurrence just happened or which result was produced?
2. What is the minimum data required for the next listener to process?
3. Is this data a snapshot at the time the event was published or only an identifier to look up the latest state?

Choose the snapshot meaning clearly. If the event carries a grandTotal computed at order creation time, listeners should treat it as the total recorded at that moment. If a listener needs the latest state, the payload can carry only orderId and reload data through an appropriate service.

## 4. Two Ways to Publish a Follow-Up Event

Spring supports two common ways to form event chains.

### Approach 1: Calling publishEvent explicitly

The listener injects ApplicationEventPublisher and publishes a new event when needed:

~~~java
@Component
class OrderPlacedListener {

    private final ApplicationEventPublisher publisher;

    OrderPlacedListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    void handle(OrderPlaced event) {
        // Process business logic for the current event
        publisher.publishEvent(
                new OrderAuditRecorded(event.orderId()));
    }
}
~~~

This approach fits when:

- A listener needs to publish multiple events across different conditional branches.
- The new event should only be published after a specific processing step succeeds.
- An event must be published from a callback or a location that cannot be expressed via a return value.
- You need to make the exact timing of publishing the new event clear in the execution flow.

An explicit publishEvent call lets the reader see the exact line where the new event is published.

### Approach 2: Returning an event from @EventListener

An @EventListener method can return an event object. Spring automatically publishes the return value after the listener method completes:

~~~java
@EventListener
InvoicePreparationRequested prepareInvoice(OrderPlaced event) {
    BigDecimal tax = event.subtotal()
            .multiply(new BigDecimal("0.10"));

    BigDecimal total = event.subtotal().add(tax);

    return new InvoicePreparationRequested(
            event.orderId(), event.subtotal(), tax, total);
}
~~~

This approach fits when a listener processes one event and produces exactly one derived event as the direct outcome of that processing.

If the method returns an array or Collection, Spring publishes each element as a separate event. If the method returns void, Spring does not create a derived event from a return value.

**Note:** Every non-void return value from an @EventListener method is treated as a follow-up event. Do not return a String, boolean, or DTO just for convenient result checking if you do not want Spring to publish it.

### Comparison

| Criterion | Explicit publishEvent | Return value |
|---|---|---|
| Publish timing | Immediately at the publishEvent call line | After the listener method returns |
| Multiple events | Can publish multiple times, across branches | Can return a Collection or array |
| Conditionals | Written directly in the execution flow | Use if before returning |
| Clarity | Clearly shows the event publishing statement | Expresses the new event as the processing result |
| Async listener | Can inject publisher and publish explicitly | Does not support follow-up events via return value |

For asynchronous listeners, do not use return values to publish follow-up events. If an async-running listener needs to publish another event, inject ApplicationEventPublisher and call publishEvent explicitly inside the listener.

## 5. Complete Example: Publishing Nested and Derived Events

The following example illustrates both chaining styles within the same flow:

1. OrderPlacedListener receives OrderPlaced.
2. The listener publishes OrderAuditRecorded explicitly. AuditListener handles it immediately.
3. OrderPlacedListener continues calculating tax and total amount.
4. The listener returns InvoicePreparationRequested. Spring publishes the derived event after the method finishes.
5. InvoiceListener receives the calculated data.

### Project Structure

~~~text
nested-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── NestedEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-events-demo</artifactId>
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
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.NestedEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### NestedEventsDemo.java

~~~java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = NestedEventsDemo.class)
public class NestedEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             NestedEventsDemo.class)) {
            context.publishEvent(
                    new OrderPlaced("DH-4101",
                            new BigDecimal("350000.00")));
            System.out.println("Main: publishEvent returned");
        }
    }
}

record OrderPlaced(String orderId, BigDecimal subtotal) {
}

record OrderAuditRecorded(String orderId, String action) {
}

record InvoicePreparationRequested(
        String orderId,
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal grandTotal) {
}

@Component
class OrderPlacedListener {

    private final ApplicationEventPublisher publisher;

    OrderPlacedListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    InvoicePreparationRequested handle(OrderPlaced event) {
        System.out.println("1. OrderPlaced: start " + event.orderId());

        publisher.publishEvent(
                new OrderAuditRecorded(event.orderId(), "ORDER_PLACED"));

        System.out.println("3. OrderPlaced: continue after nested event");

        BigDecimal tax = event.subtotal()
                .multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal grandTotal = event.subtotal().add(tax);

        return new InvoicePreparationRequested(
                event.orderId(), event.subtotal(), tax, grandTotal);
    }
}

@Component
class AuditListener {

    @EventListener
    void record(OrderAuditRecorded event) {
        System.out.println(
                "2. Nested audit event: " + event.orderId()
                        + ", action=" + event.action());
    }
}

@Component
class InvoiceListener {

    @EventListener
    void prepare(InvoicePreparationRequested event) {
        System.out.println(
                "4. Derived invoice event: " + event.orderId()
                        + ", tax=" + event.tax().toPlainString()
                        + ", total=" + event.grandTotal().toPlainString());
    }
}
~~~

### Running the Program

In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
1. OrderPlaced: start DH-4101
2. Nested audit event: DH-4101, action=ORDER_PLACED
3. OrderPlaced: continue after nested event
4. Derived invoice event: DH-4101, tax=35000.00, total=385000.00
Main: publishEvent returned
~~~

### Output Analysis

- Line 1 appears when the listener starts handling OrderPlaced.
- Line 2 appears before line 3 because publishEvent(OrderAuditRecorded) is called synchronously inside the listener. AuditListener finishes before the call returns.
- Line 3 confirms the parent listener continues after the nested event has been handled.
- Line 4 appears after the handle method returns InvoicePreparationRequested. Spring takes the return value and publishes it as a new event.
- The final line appears once all synchronous listeners for the original event and derived events have completed.

The example uses both event-publishing approaches in one listener to clarify timing. In real applications, choose the simplest approach that fits the business flow.

## 6. Designing Payloads for Derived Events

A derived event should describe an occurrence or outcome with independent meaning. Do not merely rename an old event while keeping all unnecessary data.

### Carrying snapshot data

For example, InvoicePreparationRequested carries subtotal, tax, and grandTotal. The next listener can process the exact calculated results without re-running the formula.

This approach fits when values must be consistent with the moment the event was created. Use BigDecimal for currency and explicitly define scale and rounding mode according to business rules.

### Carrying only an identifier

Another event might carry only orderId:

~~~java
record OrderSearchIndexUpdateRequested(String orderId) {
}
~~~

The listener uses orderId to load current data through a service or repository. This avoids copying a large aggregate into the event and fits when the listener needs the latest state.

On the other hand, data may have changed since the event was published. If you need to process the exact initial snapshot, carrying only an ID is not enough.

### Carrying metadata to trace the chain

For long event chains, you can add metadata such as:

- eventId: unique identifier of the event.
- correlationId: shared identifier for an entire business flow.
- causationId: the event that directly caused the current event.
- occurredAt: the time the occurrence happened.

Metadata helps with logging, tracing, and investigation when one event triggers many others. Do not confuse correlationId with eventId: multiple events can share a correlationId, yet each event still has its own eventId.

Not every problem requires a separate EventEnvelope class. Only add metadata when there is a clear need for observability, reconciliation, or duplicate handling.

## 7. Avoiding Loops and Uncontrollable Event Chains

Nested events can create loops if listeners publish events back and forth:

~~~text
OrderPlaced
   |
   v
OrderAuditRecorded
   |
   v
OrderPlaced
   |
   v
OrderAuditRecorded
   |
   +---- infinite loop
~~~

With synchronous dispatching, a loop can cause deep recursion, repeated side effects, or eventually a StackOverflowError.

Some principles to avoid this:

1. Clearly define which event is the outcome of which event. Avoid having a derived event's listener publish back to a parent event without a termination condition.
2. Use event names that describe specific occurrences, avoiding generic names like DataChanged without context.
3. If duplicate processing protection is needed, use eventId or a business key and design idempotent listeners.
4. If step limits are needed, represent state or processing steps explicitly rather than relying on listeners stopping themselves.
5. Keep event chains short. When there are many branches, conditions, retries, or waiting states, consider an explicit workflow/orchestrator.

Idempotency is the ability to process the same request multiple times without creating unintended repeated side effects. For example, audit logging can use eventId as a unique key; invoice generation needs a business key to avoid creating two invoices for the same order.

## 8. Ordering, Transactions, and Asynchronous Processing

### Ordering when running synchronously

By default, SimpleApplicationEventMulticaster listeners run synchronously. Nested publishing therefore creates nested calls, and child events typically complete before the parent listener continues.

@Order controls order among listeners matching the same event. It does not change the position of the publishEvent line inside a listener and does not establish a global ordering across all events in a chain.

### When using @Async or an executor

If listeners run asynchronously, the publisher does not necessarily wait for listeners to finish. Nested events may be processed on different threads, and the observed log order may vary.

Some consequences:

- Do not assume child events always complete before the parent listener finishes.
- Exceptions from async listeners do not propagate back to the publisher thread synchronously.
- ThreadLocal, transaction context, and logging context are not automatically propagated to another thread.
- Error logging, retries, and appropriate executor bounds must be configured.

In particular, an asynchronous @EventListener method does not support publishing follow-up events via its return value. If an async listener needs to publish an event, inject ApplicationEventPublisher and call publishEvent explicitly in the listener.

### When transactions are involved

An event published inside a transaction and handled by a regular synchronous listener may be processed before the transaction commits. Nested events also do not automatically defer until after commit.

If a listener must only run after the transaction commits, use @TransactionalEventListener with the appropriate phase, typically AFTER_COMMIT:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void afterOrderCommitted(OrderPlaced event) {
    // Handle after the transaction commits
}
~~~

If there is no active transaction, this listener is not invoked by default. Only enable fallbackExecution once the desired behavior is clearly established.

If you need guarantees that events are durably persisted alongside data changes and can be re-sent after a crash, design a transactional outbox or equivalent solution. Application Events by themselves do not provide durable delivery guarantees.

## 9. Error Handling in Event Chains

With default synchronous listeners, a runtime exception from a child event listener can propagate back through the publishEvent call inside the parent listener. When that happens, the parent listener may not proceed to compute or return the derived event.

Error boundaries must be decided clearly:

- If audit logging is mandatory to complete the business operation, an audit failure may need to fail the parent flow.
- If sending an email is merely a secondary task, you may need separate error handling, retries, or offloading the task to a separate queue.
- Do not catch and ignore exceptions if doing so leaves system state inconsistent without logs or a compensation mechanism.

If an ErrorHandler is configured on the multicaster, error behavior may differ from the default. Check the actual configuration before relying on whether exceptions propagate back or are handled locally.

A listener should not publish an event reporting success before the operation described by that event has actually succeeded. For example, only publish InvoiceCreated after the invoice has been created according to business rules.

## 10. When to Use Derived Events vs. Direct Orchestration

Use derived events when:

- The result of the current processing is an independent occurrence that multiple components may care about.
- Subsequent listeners do not need to return a mandatory result to the preceding listener.
- Independent listener reactions under the event contract are acceptable.
- You want to add a new reaction without modifying the original publisher.

Use direct service calls or a workflow when:

- A subsequent step must succeed for the preceding step to be considered complete.
- A result from a later step must be returned to decide subsequent business logic.
- An atomic transaction spanning multiple steps is required.
- The processing chain has many branches, waiting states, retries, or compensations.
- The ordering between steps is a core part of the business logic.

Events help decouple reactions; they do not replace all forms of orchestration. If readers must trace through too many listeners just to understand a mandatory business flow, an explicit orchestrating service can be easier to maintain.

## 11. Common Pitfalls

### Publishing a new event before the parent business operation succeeds

If a listener publishes InvoiceCreated before saving the invoice completes, the event name no longer reflects the truth. Only publish an event once the business success condition has been met.

### Accidentally publishing a return value

An @EventListener method returning a DTO or String also causes Spring to treat that value as an event. Use void if you do not want to publish a derived event.

### Using return values in async listeners

The return value of an async listener is not used to publish a follow-up event. Publish explicitly using ApplicationEventPublisher.

### Sharing mutable objects across events

If a parent event and a child event hold the same mutable object, listeners may observe mutated data. Prefer records and immutable payloads.

### Relying on implicit ordering between listeners

@Order only controls listener order for the same event. Do not use it as a workflow engine or transaction synchronization mechanism.

### Lacking deduplication mechanisms

If an event can be published multiple times or a listener can retry, side effects such as creating invoices or sending notifications need a deduplication key or an idempotent mechanism.

## 12. Key Takeaways

Nested events occur when a listener publishes another event while processing an existing event. With the default synchronous multicaster, the child event's listeners run immediately within the nested call; only after they finish does the parent listener continue.

Derived events can be published explicitly via ApplicationEventPublisher or produced from the return value of @EventListener. Return values are suitable only when the new event is the direct outcome of the listener; async listeners must publish explicitly.

Event payloads should clearly express either a snapshot or an identifier, avoid sharing mutable data, and include tracking metadata when chains grow long. Prevent loops, design for idempotency, understand transaction and async boundaries, and use a service or workflow when mandatory business orchestration is needed.

## Official References

- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [ApplicationEventPublisher — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [SimpleApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [TransactionalEventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)