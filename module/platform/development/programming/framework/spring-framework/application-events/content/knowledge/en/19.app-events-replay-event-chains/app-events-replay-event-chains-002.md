# Publishing Follow-Up Events from Listener Return Values in Spring Framework

## 1. Concept: A Listener Result Can Become a New Event

In **Spring Framework Application Events**, a synchronous **@EventListener** method does not have to return **void**. If the method returns a non-**null** object, Spring can **publish that result as a new application event**. Listeners subscribed to the new event type are invoked in turn, allowing multiple steps to be connected into an **event chain**.

Example:

~~~text
OrderRequested
      |
      v
@EventListener validate(...) -> OrderValidated
      |
      v
@EventListener prepare(...) -> InvoiceRequested
      |
      v
@EventListener onInvoiceRequested(...)
~~~

In the diagram, the method name does not determine the next event type: **the object returned by the method** does. A listener can handle A and return B; Spring's adapter will publish B. A listener receiving B can in turn produce C. This is the **return-value event publication** mechanism, not a direct Java method call between business services.

Key rules:

- **Returning an object:** Spring publishes that object as a new event.
- **Returning a Collection or array:** Spring publishes **each element** as a separate event.
- **Returning null or void:** no further event is published from the listener's result.
- **@Async @EventListener:** publishing follow-up events via **the return value is not supported**; you need to inject **ApplicationEventPublisher** and publish manually if you want to emit a follow-up event.
- With the default synchronous **SimpleApplicationEventMulticaster**, the new event is typically dispatched on the same thread and within the same call stack as the original event.
- **An event chain does not by itself imply replay, queue, retry, transaction, or durable persistence**. It only describes how a follow-up event is published from the current handling result.

This technique fits small, clear event transitions. For steps involving transactions, external side effects, or crash recovery, boundaries and reliability must be designed separately.

## 2. How Spring Implements Return-to-Event

When a Spring-managed bean has an **@EventListener** method, Spring registers an adapter to invoke that method when a matching event type arrives. Typical execution flow:

~~~text
Caller
  |
  +-- publisher.publishEvent(EventA)
          |
          v
      ApplicationEventMulticaster
          |
          v
      @EventListener method onA(EventA)
          |
          +-- return EventB
                  |
                  v
          Spring publishes EventB
                  |
                  v
          @EventListener method onB(EventB)
                  |
                  +-- may return EventC, or stop
~~~

Important points to note:

1. **publishEvent(...)** is the publishing API and returns **void**; the caller does not receive EventB as a return value.
2. **EventB** is published by the framework **after the listener method onA(...) returns**.
3. EventB can be a **Java POJO/record**; it does not need to extend **ApplicationEvent**.
4. Listener methods are only processed automatically when events are dispatched through **ApplicationContext**. If test code calls **onA(...)** directly, that is merely a Java method call and does not automatically publish EventB.
5. Thread selection and error propagation can change if the application configures a custom multicaster/executor.

Example of a method producing a follow-up event:

~~~java
@EventListener
public ShipmentRequested afterPaymentConfirmed(PaymentConfirmed event) {
    return new ShipmentRequested(event.orderId());
}
~~~

This is an **illustrative snippet**; it requires declaring the two event types and registering the enclosing class as a Spring bean. In this case, if a listener accepts **ShipmentRequested**, Spring can invoke that listener after the method above returns the new object.

If the same method returned a **String**, Spring could likewise treat that string as a payload object published as an event. Therefore, do not return arbitrary computed data from **@EventListener** unless you genuinely want it to become the next event.

## 3. One Event, Multiple Events, or No Follow-Up Event

| Signature / result | How Spring handles it |
| --- | --- |
| **EventB onA(EventA e)** returning **new EventB(...)** | Publishes one EventB |
| **Object onA(EventA e)** returning an event object chosen conditionally | Publishes that actual object |
| **List<EventB> onA(EventA e)** | Publishes each EventB in the list |
| **Collection<Object> onA(EventA e)** | Publishes each element as an event |
| **EventB[] onA(EventA e)** | Publishes each array element as an event |
| Method returns **null** | Publishes no new event from the result |
| Method returns empty **List.of()** | No elements to publish |
| Method **void onA(EventA e)** | No automatic event from the return value |

### 3.1. Returning a Collection to Fan Out

~~~java
@EventListener
public List<Object> afterPaymentConfirmed(PaymentConfirmed event) {
    return List.of(
            new ShipmentRequested(event.orderId()),
            new ReceiptRequested(event.orderId()));
}
~~~

**ShipmentRequested** and **ReceiptRequested** are published **individually**; the **List** as a whole is not treated as a single event. Use **List** when you want to reflect emission order in the example; **HashSet** is unsuitable when predictable iteration order is needed.

If the business logic genuinely requires **one event containing a list**, create an explicit wrapper event such as **BatchCompleted(List<String> orderIds)** and return the **BatchCompleted** object. Do not return **List<OrderId>** assuming Spring will automatically treat it as a single batch event.

### 3.2. Returning null to End a Branch

~~~java
@EventListener
public StockReserved reserve(OrderRequested event) {
    if (event.quantity() <= 0) {
        return null;
    }
    return new StockReserved(event.orderId());
}
~~~

This snippet shows that **null means do not publish a follow-up result**. In real business workflows, however, an important rejection state should usually have its own event such as **OrderRejected** rather than silently returning null; that makes system observability and error handling clearer.

### 3.3. Warning Against Accidental Return Values

An **@EventListener** where a developer only intends to log or compute metrics but returns a **String**, **Boolean**, **Integer**, or internal DTO can inadvertently produce a new event. If no event needs to be published, change the method to **void** and store results through an appropriate mechanism. **The return type is part of the publication contract**, not a way to return a response to the caller of the event publisher.

## 4. Runnable Java 17+ Example: Chaining, Branching, Fan-Out, and Null

This example uses **Spring Framework 6.2.9**, **JDK 17+**, and **Gradle 8.x**. No Spring Boot, database, or broker is needed. The flow shows events created from return values, including branches that do not continue.

Structure:

~~~text
event-return-chain/
  build.gradle
  src/main/java/demo/EventReturnChainDemo.java
~~~

Contents of **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.EventReturnChainDemo'
}
~~~

Contents of **src/main/java/demo/EventReturnChainDemo.java**:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventReturnChainDemo {

    public record OrderRequested(String id, int quantity) {}
    public record OrderValidated(String id, int quantity) {}
    public record OrderRejected(String id) {}
    public record InvoiceRequested(String id) {}
    public record AuditRequested(String id) {}

    public static class ChainListeners {

        @EventListener
        public Object evaluate(OrderRequested event) {
            System.out.println("requested: " + event.id());

            if (event.quantity() < 0) {
                return null; // Stop: no follow-up event.
            }
            if (event.quantity() == 0) {
                return new OrderRejected(event.id());
            }
            return new OrderValidated(event.id(), event.quantity());
        }

        @EventListener
        public List<Object> validated(OrderValidated event) {
            System.out.println("validated: " + event.id());
            return List.of(
                    new InvoiceRequested(event.id()),
                    new AuditRequested(event.id()));
        }

        @EventListener
        public void onInvoiceRequested(InvoiceRequested event) {
            System.out.println("invoice: " + event.id());
        }

        @EventListener
        public void onAuditRequested(AuditRequested event) {
            System.out.println("audit: " + event.id());
        }

        @EventListener
        public void onRejected(OrderRejected event) {
            System.out.println("rejected: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ChainListeners chainListeners() {
            return new ChainListeners();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("caller: publish A");
            context.publishEvent(new OrderRequested("A", 2));
            System.out.println("caller: returned A");

            System.out.println("caller: publish B");
            context.publishEvent(new OrderRequested("B", 0));
            System.out.println("caller: returned B");

            System.out.println("caller: publish C");
            context.publishEvent(new OrderRequested("C", -1));
            System.out.println("caller: returned C");
        }
    }
}
~~~

In the **event-return-chain** directory:

~~~bash
gradle --console=plain -q run
~~~

Lines printed to **stdout by the code itself**:

~~~text
caller: publish A
requested: A
validated: A
invoice: A
audit: A
caller: returned A
caller: publish B
requested: B
rejected: B
caller: returned B
caller: publish C
requested: C
caller: returned C
~~~

**Output explanation:**

1. **OrderRequested("A", 2)** is published. Listener **evaluate(A)** prints **requested: A** and returns **OrderValidated(A, 2)**. Spring publishes that event, invokes **validated(A)**, and receives **List.of(InvoiceRequested(A), AuditRequested(A))**. Each child event is published; listeners print **invoice: A** then **audit: A**. Because the default multicaster is synchronous, the caller prints **returned A** after the chain completes.
2. **OrderRequested("B", 0)** branches to **OrderRejected(B)**. There is no OrderValidated, InvoiceRequested, or AuditRequested for B; listener **onRejected** prints **rejected: B**.
3. **OrderRequested("C", -1)** returns **null**. There is no follow-up event from the return value, so the program prints **returned C** right after **requested: C**.
4. The event types are **Java records** and do not extend ApplicationEvent. Spring accepts object payload events and matches listeners by their corresponding types.
5. There is no **@Async**, custom task executor, or transaction manager in this program; that is important for predicting stdout.

**Example scope:** Names like InvoiceRequested and AuditRequested are purely illustrative; the code does not create real invoices, write to a database, send emails, or guarantee message delivery. This is an example to understand the return-to-event mechanism, not a production financial workflow.

## 5. Nested Chains and Execution Order

When Spring uses the default synchronous **SimpleApplicationEventMulticaster**, returning an event causes the new event to be published **right inside the processing of the current listener**:

~~~text
Caller publishes A
  -> Listener A runs
       -> return B
       -> Spring publishes B
            -> Listener B runs
                 -> return [C, D]
                 -> Spring publishes C
                      -> Listener C
                 -> Spring publishes D
                      -> Listener D
  <- publish A completes
Caller continues
~~~

Consequences:

- Slow downstream processing can slow down the initial **publishEvent(A)** call.
- An exception in a downstream listener can affect the original caller under the default synchronous configuration.
- A listener for the root event can return a child event; the child chain is dispatched **before** the multicaster returns to other not-yet-run listeners of the root event.
- Completion order is not guaranteed when using a custom multicaster with an executor or asynchronous listeners.

### 5.1. @Order Is Not a Workflow Engine

Spring allows prioritizing multiple listeners subscribed to the same event type:

~~~java
@EventListener
@Order(10)
public FollowUpEvent first(OriginalEvent event) {
    return new FollowUpEvent(event.id());
}

@EventListener
@Order(20)
public void second(OriginalEvent event) {
    // Another listener for the original event.
}
~~~

This is an **illustrative snippet**; it requires appropriate event types and imports. In a synchronous chain, **first(...)** may publish and process **FollowUpEvent** before **second(...)** processes **OriginalEvent**. **@Order** does not express dependency relationships across all event types, nor does it guarantee the entire workflow completes in order in an async environment.

When multiple mandatory sequential steps need explicit error propagation and rollback, **direct application service calls** may fit better than an event chain.

### 5.2. Fan-Out Differs from a Competing-Consumers Queue

If an event of type **InvoiceRequested** has three listeners, Spring can invoke all three. It does not mean the event is delivered to only one consumer like a competing queue. Returning a Collection only produces **multiple events**, while each event can still be processed by multiple listeners.

## 6. Avoiding Event Loops

A potentially very dangerous bug:

~~~text
@EventListener(A) -> return B
@EventListener(B) -> return A
@EventListener(A) -> return B
...
~~~

With nested synchronous dispatch, a non-terminating chain can cause deep recursion, **StackOverflowError**, CPU spikes, or an unresponsive application. Spring does not automatically verify that your event graph is acyclic.

**Countermeasures:**

- Design event types that represent state transitions with clear terminal states: **Requested → Validated → Completed/Rejected**.
- Use **void** or **null** when no further step is needed; do not return an event just to keep the chain alive.
- If chains can be generated dynamically, enforce a **hopCount** limit or workflow state; increment hopCount when creating the next event and reject beyond the threshold.
- Attach a **correlation ID**, **event ID**, and business key to trace multiple independent chains.
- Design for **idempotency**: redelivering the same event must not cause duplicate payments or emails.
- Test cases where events are replayed, listeners fail, and invalid state transitions occur.

Example of an event with metadata:

~~~java
public record WorkflowAdvanced(
        String workflowId,
        String correlationId,
        int hopCount) {
}
~~~

This is an illustrative Java record; code checking the hopCount limit must live in the appropriate use case/listener. Do not use a global static variable to mark “already processed”, because it can mistakenly block independent requests.

## 7. Return Value vs. ApplicationEventPublisher: Two Ways to Continue a Chain

### 7.1. Returning an Event from a Synchronous Listener

~~~java
@EventListener
public ShippingRequested afterInvoiceCreated(InvoiceCreated event) {
    return new ShippingRequested(event.orderId());
}
~~~

This approach is concise when each execution yields a single clear event outcome. Spring publishes the new event when the method returns.

### 7.2. Explicit Publishing

~~~java
private final ApplicationEventPublisher publisher;

@EventListener
public void afterInvoiceCreated(InvoiceCreated event) {
    // Evaluate conditions and choose the exact moment to publish.
    publisher.publishEvent(new ShippingRequested(event.orderId()));
}
~~~

These two excerpts are **snippets**; they require beans, imports, and event definitions. Explicit publishing fits when you need control over publication timing or need to publish from code that is not an @EventListener. Avoid using both **return event** and **publishEvent** simultaneously for the same event, as that can create duplicates.

| Situation | Return event | Explicit publisher |
| --- | --- | --- |
| A synchronous listener transforms A into B | Very concise | Works |
| A listener emits multiple events | Return Collection/array | Call multiple times |
| No follow-up step | Return null/void | Do not call publish |
| @Async @EventListener | **Return-based chaining not supported** | **Use publisher** |
| Need to publish in the middle of multiple operations | Publishes only when method returns | Can choose exact timing |
| Need mapping between domain event and infrastructure | Listener/adapter at outer layer | Also place publisher in adapter |
| Need delivery to a durable queue | Not built in | Not built in; must design adapter/outbox |

## 8. Important Limitation of @Async @EventListener

Spring Framework documentation confirms: **async event listeners cannot publish follow-up events via their return value**. Therefore, do not use the return value of an **@Async @EventListener** method as a promise that Spring will automatically publish the next event.

**Anti-pattern for the return-to-event contract:**

~~~java
@Async
@EventListener
public NextEvent process(PreviousEvent event) {
    return new NextEvent(event.id());
}
~~~

When you need to publish follow-up events from an async handler, invoke the publisher explicitly:

~~~java
@Component
public class AsyncFollowUpHandler {
    private final ApplicationEventPublisher publisher;

    public AsyncFollowUpHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void on(PreviousEvent event) {
        // Processing complete; inspect outcome and continuation condition.
        publisher.publishEvent(new NextEvent(event.id()));
    }
}
~~~

The examples in this section are **not standalone files**; they require **@EnableAsync**, an executor, event types, and corresponding imports. In production, you must configure queue bounds, timeouts, error handling, and shutdown policies for the executor.

Differences when running asynchronously:

- The original publisher **does not necessarily wait** for async processing to finish.
- Exceptions from **void @Async** do not automatically propagate to the caller; an appropriate error handler such as **AsyncUncaughtExceptionHandler** or separate observability is required.
- **ThreadLocal** transaction context and logging MDC are usually **not propagated automatically** to executor threads.
- A new event chain may execute after the original request has already responded.
- In-memory async tasks can be lost if the process is killed; calling the publisher from async does not turn it into a durable queue.

If a workflow genuinely needs to wait for an async step and resume after a service restart, consider orchestration/state machines and a persistent queue rather than relying on return values.

## 9. Exceptions in Downstream Steps

Suppose listener A returns B, but listener B throws **IllegalStateException**. With the default synchronous multicaster and no special **ErrorHandler**, the exception can propagate from listener B back through publishing B, to event handler A, and ultimately to the caller that published A.

~~~text
Caller publishes A
 -> ListenerA returns B
 -> Spring publishes B
 -> ListenerB throws IllegalStateException
 -> exception propagates toward original publisher
~~~

As a result, other listeners may not be called, the chain stops midway, and side effects prior to the error may have already occurred. Configuring **SimpleApplicationEventMulticaster.setErrorHandler(...)**, a custom executor, @Async, or transaction-aware listeners can alter how errors are handled. Do not design around a single propagation rule if the configuration has changed.

**Need mandatory handling before proceeding?** If a step requires a direct return value, strict validation, and specific error handling, an application service call may express the contract better:

~~~text
validateOrder()
    -> reserveStock()
    -> chargePayment()
    -> saveResult()
~~~

The diagram above is a **pseudo-flow**, not runnable Java code. Event chains are better suited for independent reactions or clearly defined event-driven state transitions. They do not replace transaction orchestration.

## 10. Transactions: The Follow-Up Event May Still Run Before Commit

Suppose an application service has **@Transactional**:

~~~text
BEGIN TRANSACTION
  save order
  publish OrderCreated
     -> @EventListener returns InvoiceRequested
     -> @EventListener(InvoiceRequested) runs
  application method returns
COMMIT or ROLLBACK
~~~

In the default synchronous case, both the initial listener and the listener receiving the follow-up event normally run **inside the uncommitted transaction**. If the child listener sends an email or makes an HTTP call before commit, and then the transaction rolls back, the external side effect is not automatically undone.

**Do not interpret “return event B” as “event B only runs after commit”.** These are two completely different concepts: **event chaining** describes how publication continues, while **transaction phase** describes when a callback is executed.

If post-commit reaction is needed, the infrastructure can use **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)**:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // Executes after the associated transaction commits successfully.
}
~~~

This is an **illustrative snippet**; it requires a bean/transaction manager and an event published within a compatible transaction. By default **fallbackExecution=false**, so the transactional listener method does not run when no matching transaction is active.

After **AFTER_COMMIT**, the primary transaction has already committed; operations that need to write new data with their own commit typically need a new transaction such as **Propagation.REQUIRES_NEW** through a Spring-managed service. Do not assume publishing a follow-up event inside a post-commit callback still participates in an open transaction.

### 10.1. When Events Must Not Be Lost: Transactional Outbox

**@EventListener return value** is an **in-memory** mechanism. If the JVM crashes between two steps, Spring does not automatically replay the chain. In systems requiring durable delivery, use a **transactional outbox**:

~~~text
BEGIN TRANSACTION
  save domain state
  save outbox event record
COMMIT
  -> worker reads outbox
  -> publishes to broker / executes next step
  -> retries on failure
  -> persists processed status
~~~

The outbox record is committed in **the same database transaction** as the business state, reducing the risk of losing the intent to publish. Workers and consumers must still be **idempotent** because duplicate processing can occur if a message is sent successfully but completion acknowledgment fails. Outbox alone does not automatically guarantee end-to-end exactly-once delivery.

## 11. Replay Is Not the Same as Building an Event Chain

This knowledge group is **“Replay and Event Chains”**. What needs to be distinguished:

- **Event chain:** receives A, handles A, and produces event B immediately via return value or publisher. Requires no event history.
- **Replay:** re-reads **stored** events to build projections, recover state, or reprocess; requires an event log/outbox/event store and a replay policy.
- **Retry:** retries a failed step according to a policy; does not appear automatically just because a method returns an event.
- **Redelivery:** a message broker redelivers an event; a listener may be invoked multiple times and produce duplicate child events.

Example: When replaying historical **OrderValidated** events to rebuild a report, a listener must not accidentally emit **SendInvoiceEmailRequested** and send emails again. Separate idempotent projections from side effects, detect replay mode, and use event IDs/correlation IDs.

**ApplicationEventPublisher** is not an event store and has no built-in historical replay. Returning a new event does not persist that event either.

## 12. Designing Event Types with Clear Contracts

An understandable chain should reflect clear steps:

~~~text
OrderRequested
    -> OrderValidated / OrderRejected
    -> InvoiceRequested
    -> InvoiceCreated / InvoiceFailed
~~~

Name events meaningfully: requests, states that occurred, and failures. Do not use a generic event like **ProcessingEvent(status)** for all branches if it forces listeners to inspect lots of status strings and construct an unclear implicit graph.

Each event should carry the minimal data needed for reaction: aggregate/business ID, correlation ID, event ID, and state/version info when appropriate. Example:

~~~java
public record InvoiceRequested(
        String orderId,
        String correlationId,
        int hopCount) {
}
~~~

This is a standalone Java record with no Spring dependency. Avoid stuffing **EntityManager**, mutable JPA entities, or HTTP request objects into events. For brokers, you can map domain events to versioned integration messages without forcing domain events to extend framework types.

## 13. Testing the Return-to-Event Mechanism

**A unit test calling a listener method directly does not prove Spring automatically publishes the result.** To verify return-to-event, you must dispatch through a real **ApplicationContext** with registered **@EventListener** beans.

Important tests:

1. Publish **OrderRequested(A, 2)** and verify the chain produces **OrderValidated**, **InvoiceRequested**, **AuditRequested**.
2. Publish **OrderRequested(B, 0)** and verify only **OrderRejected** is produced.
3. Publish **OrderRequested(C, -1)** and verify no follow-up event is produced from **null**.
4. Method returns **List.of(B, C)**: both types are published individually.
5. Method returns **Event[]**: each element is dispatched.
6. Listener returns **void**: no new event is generated.
7. Multiple listeners for the root event and **@Order**: verify nested dispatch and configured ordering.
8. Downstream listener throws an exception: verify propagation behavior according to multicaster/error policy.
9. **@Async**: verify return values are not relied upon; test explicit publishing and executor behavior.
10. Transaction rollback: verify whether side effects actually happen before or after commit.
11. Replay/redelivery: verify idempotency, stopping conditions, and duplicate handling.

With a synchronous multicaster, you can record received events in a test-managed **List** and assert immediately after **publishEvent(...)**. With async, use **CountDownLatch** or test utilities like Awaitility; avoid arbitrary **Thread.sleep(...)** calls to guess completion timing.

Expected example for the demo in section 4:

~~~text
input A -> OrderValidated(A), InvoiceRequested(A), AuditRequested(A)
input B -> OrderRejected(B)
input C -> no follow-up events
~~~

This is a **test scenario**, not a standalone JUnit class. When writing JUnit tests, count only the next events—not the initial input event published by the caller—when the goal is to verify return-to-event.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming **publishEvent(A)** returns B | API returns void; caller does not receive B | Understand return event is a new publication |
| Returning String/boolean as a processing result | Object is treated as an unintended event | Change method to void or return an explicit event type |
| Returning List thinking List is a single event | Spring publishes each element | Create a **BatchXxx** wrapper if you want one event containing a list |
| **@Async @EventListener** returning an event | Does not chain via return value | Inject **ApplicationEventPublisher**, publish explicitly |
| Listener A returns B, B returns A | Infinite recursion/loop | Stopping conditions, hop-count, state machine |
| Relying on @Order to coordinate an async pipeline | Does not guarantee completion order | Orchestrator/queue and concurrency tests |
| Thinking return B means B runs after commit | Side effects may happen before commit | Use transactional listener/outbox with proper scope |
| Thinking event chains persist durably | JVM crash loses work | Outbox/queue, retry, idempotency |
| Replaying historical events while emitting new side effects | Sends duplicate notifications or commands | Separate projections from side effects |
| Calling listener method directly in unit test and expecting Spring to publish | Bypasses the event adapter | Integration test through ApplicationContext |
| Fanning out multiple events without correlation ID | Hard to trace, deduplicate, and troubleshoot | Event ID + correlation ID and metrics |
| Using event chains for complex mandatory rules | Hard to observe exceptions/rollbacks | Explicit service calls in the application layer |

## 15. Checklist Before Using Return Values

- **Is the new event represented by a clearly named class/record?**
- **Is the listener synchronous or async?** If **@Async**, do not use return values to publish.
- **Returning one event, an array/Collection, or null?** Do you understand the exact semantics of each?
- **Are stopping conditions and loop limits in place?**
- **Are there multiple listeners for the root event?** Have **@Order** and nested dispatch been evaluated?
- **If a child listener fails, how are the caller and other listeners affected?**
- **Does the chain execute before or after transaction commit?** Are there non-rollbackable side effects?
- **If processing must survive crashes, is there an outbox/queue and idempotency?**
- **If replayed or retried, are duplicate side effects prevented?**
- **Is there an integration test proving Spring automatically publishes from the return value?**

**Conclusion:** With **synchronous @EventListener**, **returning an object** makes Spring publish a follow-up event, **returning a Collection/array** publishes each element, while **null/void** stops automatic chaining. **@Async listeners do not support return-value publication**. Use this mechanism for small, easy-to-test event chains; do not confuse it with transaction orchestration, replay, or durable messaging.

### Official Documentation

- Spring Framework 6.2 — *Annotation-based Event Listeners / Additional Capabilities of the ApplicationContext*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.9 Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2.9 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.9 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
