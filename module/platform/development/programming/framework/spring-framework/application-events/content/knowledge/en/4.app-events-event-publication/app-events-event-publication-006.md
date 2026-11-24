# Publishing Multiple Events in Business Order in Spring

A use case can generate multiple consecutive business events. For example, an order is validated, inventory is reserved, and the order is confirmed. When publishing multiple events, the publication order must accurately reflect the occurrences that have actually happened.

In Spring, you can call ApplicationEventPublisher.publishEvent() multiple times in the desired sequence. With the default synchronous ApplicationEventMulticaster, each publishEvent() dispatches the event and completes synchronous listeners before the next call executes. However, **calling publishEvent() in sequence does not mean all listeners always complete in the same order**: async execution, multiple threads, and transaction-bound listeners change when processing happens.

Three questions must be distinguished:

1. In what order are the events published?
2. In what order are each event's listeners invoked and completed?
3. If a step fails, how should the business flow stop, roll back, retry, or proceed?

## 1. Events Must Describe Occurrences That Have Happened

An event name should describe a fact that has occurred in the business domain, typically using the past tense:

- OrderValidated: the order has passed business validation.
- InventoryReserved: inventory has been successfully reserved.
- OrderConfirmed: the order has been confirmed.

Names like ValidateOrder, ReserveInventory, or ConfirmOrder describe commands. If the goal is to ask a service to perform an action and know its result, call that service directly. Events are suited for notifying interested components of a result or a change that has already happened.

This is crucial when publishing multiple events. Do not publish InventoryReserved before the reservation operation actually succeeds. If you publish the event first and the operation fails, listeners may receive a notification inconsistent with the business state.

A good event sequence represents completed milestones, for example:

    OrderValidated
        -> InventoryReserved
            -> OrderConfirmed

The arrows represent business order. They do not necessarily mean the listener for an earlier event must perform an action to produce the next event. Mandatory steps of a use case should still be coordinated by a service or workflow with explicit outcomes.

## 2. Publishing Events Sequentially with ApplicationEventPublisher

ApplicationEventPublisher is the API for publishing events in an ApplicationContext. Since Spring Framework 4.2, you can publish any Java object; extending ApplicationEvent is not required. With Java 17+, records are a concise way to represent immutable events.

Example defining three events:

~~~java
import java.util.UUID;

public record OrderValidatedEvent(
    UUID orderId,
    long sequence
) {}

public record InventoryReservedEvent(
    UUID orderId,
    long sequence
) {}

public record OrderConfirmedEvent(
    UUID orderId,
    long sequence
) {}
~~~

The sequence field helps observe the order of milestones for the same order. It does not by itself create an ordering mechanism or guarantee delivery; it is simply metadata for logging, verification, or enabling consumers to detect out-of-order events.

A coordinating service can publish the events after each business step completes:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflow {

    private final ApplicationEventPublisher publisher;
    private final OrderValidator validator;
    private final InventoryService inventoryService;

    public OrderWorkflow(
            ApplicationEventPublisher publisher,
            OrderValidator validator,
            InventoryService inventoryService) {
        this.publisher = publisher;
        this.validator = validator;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void confirm(Order order) {
        validator.validate(order);
        publisher.publishEvent(
            new OrderValidatedEvent(order.getId(), 1)
        );

        inventoryService.reserve(order);
        publisher.publishEvent(
            new InventoryReservedEvent(order.getId(), 2)
        );

        order.confirm();
        publisher.publishEvent(
            new OrderConfirmedEvent(order.getId(), 3)
        );
    }
}
~~~

Order, OrderValidator, and InventoryService are application domain types that need to be provided in the project. The example assumes the data operations belong to the same transaction; if inventory resides in an external system, a local database transaction cannot automatically roll back operations in that external system.

The key point of the example is that the publisher publishes each event after the corresponding step succeeds. If validation fails, no event is published. If reservation fails, OrderValidatedEvent may have already been published, while the subsequent steps and the remaining two events do not run. In that case, you must decide whether listeners of OrderValidatedEvent are allowed to observe transient state or must wait for transaction commit; transactions are covered in section 6.

## 3. Dispatch Order with the Default Multicaster

SimpleApplicationEventMulticaster is the default implementation typically used by ApplicationContext when the application does not supply another multicaster. By default, it does not use a separate executor to invoke listeners, so listeners are called synchronously on the thread publishing the event.

Suppose there are listeners for all three events:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventLogger {

    @EventListener
    public void on(OrderValidatedEvent event) {
        System.out.println("1. validated " + event.orderId());
    }

    @EventListener
    public void on(InventoryReservedEvent event) {
        System.out.println("2. inventory reserved " + event.orderId());
    }

    @EventListener
    public void on(OrderConfirmedEvent event) {
        System.out.println("3. confirmed " + event.orderId());
    }
}
~~~

If synchronous listeners complete normally, the processing order corresponds to the three publishEvent() calls in the service:

1. The publisher publishes OrderValidatedEvent; matching listeners are dispatched.
2. After the first publishEvent() call returns, the service performs the reservation and publishes InventoryReservedEvent.
3. After dispatching the second event returns, the service confirms the order and publishes OrderConfirmedEvent.

This guarantee holds for sequential calls within a single thread using a synchronous multicaster. It is not a global ordering guarantee across requests, across multiple threads, or across systems.

### @Order Orders Listeners, Not Business Workflows

If multiple listeners are interested in the same event, you can use @Order or implement Ordered to order listener invocations within the same multicaster.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    @Order(10)
    public void audit(OrderConfirmedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }
}

@Component
class OrderMetricsListener {

    @EventListener
    @Order(20)
    public void recordMetric(OrderConfirmedEvent event) {
        System.out.println("Metric order " + event.orderId());
    }
}
~~~

In this example, the audit listener is invoked before the metrics listener for the same OrderConfirmedEvent. @Order does not make InventoryReservedEvent wait for an OrderValidatedEvent listener to finish if that listener runs asynchronously. Nor does it create a workflow across different event types.

If ordering across multiple reactions is a mandatory business requirement, place them in a coordinating service or in a single listener that invokes the steps in an explicit sequence.

## 4. What Happens When a Listener Fails?

With the default multicaster and synchronous listeners, an unhandled exception can propagate back to where publishEvent() was called. With SimpleApplicationEventMulticaster without a configured ErrorHandler, a listener throwing an exception can interrupt the current dispatch and prevent the service from reaching the next publishEvent() call.

Example:

~~~java
publisher.publishEvent(new OrderValidatedEvent(orderId, 1));

// If the listener above throws an exception and it propagates out,
// the statements below may not be executed.
publisher.publishEvent(new InventoryReservedEvent(orderId, 2));
publisher.publishEvent(new OrderConfirmedEvent(orderId, 3));
~~~

This can be useful if the listener is part of the same processing flow and a failure must fail the use case. However, if the listener only records metrics or secondary audits, letting a secondary failure block the entire workflow may not be desirable.

An error policy should be defined for each listener:

- **Errors that must block the use case:** let the exception propagate to the caller or translate it into an appropriate business error.
- **Secondary errors that must not block the use case:** handle errors intentionally, record logs/metrics, and monitor. If using the multicaster's ErrorHandler, understand that exceptions handled there may no longer propagate back to the publisher.
- **Work that must be retried:** persist the work in a durable mechanism or use an outbox/broker; do not rely solely on an in-memory callback.
- **Async listeners:** configure executor error observation or AsyncUncaughtExceptionHandler; do not assume the publisher will receive listener exceptions.

Do not swallow every exception just to keep the publish sequence going. If an error is ignored, the business state must be recorded so it can be detected and recovered.

## 5. When Listeners Run Asynchronously

You can use @Async with @EventListener or configure an executor on SimpleApplicationEventMulticaster. In that case, calling publishEvent() may simply submit work to the executor and return; the listener is not guaranteed to have started or finished.

Example:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class AsyncNotificationListener {

    @Async
    @EventListener
    public void on(OrderConfirmedEvent event) {
        sendNotification(event.orderId());
    }

    private void sendNotification(java.util.UUID orderId) {
        // Send notification here.
    }
}
~~~

You need to enable async processing with @EnableAsync and configure a suitable executor. Key points to remember:

- The publisher does not wait for async listeners to finish as it does with synchronous listeners.
- Two events published in sequence do not mean their two async listeners finish in the same order.
- Multiple executor threads can process events concurrently.
- Exceptions in async listeners are not returned to the publisher like synchronous call exceptions.
- The publishing thread's transaction context does not automatically transfer to the executor thread.

For instance, a service may publish OrderValidatedEvent followed by InventoryReservedEvent. The async listener for the second event can finish before the async listener for the first event if the first task is slower. If business logic requires reaction B to run only after reaction A finishes, independent @Async on two listeners will not satisfy that requirement.

### Preserving Order During Async Processing

First define the scope of ordering that must be guaranteed:

- Per order or across the entire application?
- Do listeners only need to receive events in order, or must they finish in order?
- Must ordering be preserved across retries, restarts, and multiple instances?

For a small workflow within the same application, you can use a sequential worker or a single coordinating service. For many independent orders, you can process in parallel across orders while staying sequential within each order ID. With a message broker, you typically use a partition key by aggregate ID and a sequence number to preserve order within the same partition; duplicates and retries still need to be handled.

Simply configuring a thread executor does not solve every problem: multiple publishers, multiple executors, retries, or multiple instances can still complicate business ordering. Choose the mechanism based on the scope of ordering required.

## 6. Publishing Multiple Events Inside a Transaction

When an event-publishing method is called inside @Transactional, distinguish regular listeners from @TransactionalEventListener.

### Regular @EventListener

A synchronous @EventListener runs when the event is dispatched. If published before the transaction commits, the listener can run while the transaction is still open and observe uncommitted data.

If the transaction subsequently rolls back, side effects already performed by the listener outside the transaction may still persist. For example, an email already sent cannot be recalled just because the database rolled back.

Therefore, do not use regular listeners to perform irreversible side effects when events are published before commit, unless that behavior is intentional.

### @TransactionalEventListener

If a listener must only run after the transaction commits, use @TransactionalEventListener:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderConfirmedEvent event) {
        // Send notification after the transaction commits successfully.
    }
}
~~~

Main phases:

- BEFORE_COMMIT: runs before the transaction commits.
- AFTER_COMMIT: runs after a successful commit; this is the default phase.
- AFTER_ROLLBACK: runs after a rollback.
- AFTER_COMPLETION: runs when the transaction completes, regardless of commit or rollback.

By default, a transactional listener requires an active transaction at the time the event is published. Without a transaction, the listener is not invoked unless fallbackExecution = true is enabled.

When a transaction publishes three consecutive events, transactional listeners are bound to the transaction lifecycle and only run at the selected phase. However, do not turn multiple independent listeners into a chain of mandatory steps relying on callback order. If business logic requires confirming A finished before performing B, use a handler/orchestrator with an explicit sequence.

An AFTER_COMMIT listener failure cannot roll back an already committed transaction. Thus, AFTER_COMMIT solves the timing problem, but does not by itself provide retries or guarantee that the work will be executed.

## 7. When Durability Is Required and Events Must Not Be Lost

ApplicationEventPublisher is an internal notification mechanism within a single process. It is not a message broker and does not automatically persist events across restarts.

Suppose the database committed the OrderConfirmed state, but the process stops before the listener sends the notification. In-memory events can be lost with no record to recover the work.

If events must be delivered reliably, consider a transactional outbox:

1. In the same business transaction, update the order and write an outbox record for each event to be published.
2. After commit, a worker reads unsent outbox records.
3. The worker publishes messages to a broker or forwards them to consumers.
4. After successful delivery, record the sent status; on failure, retry according to policy.
5. Consumers process idempotently because messages may be redelivered.

An outbox eliminates the gap between committing business data and recording the intent to publish an event. Even so, the system still needs to handle duplicates, retries, ordering, and dead-letters as required. If per-order ordering is needed, record a sequence number in the outbox and ensure consumers process in order for the same aggregate ID.

You do not need to implement an outbox for every internal event. Use it when the consequence of losing an event is significant enough to require durability and recoverability.

## 8. Publishing Events in Loops and Concurrent Publishers

You can publish events for each element in a list:

~~~java
for (Order order : orders) {
    publisher.publishEvent(
        new OrderValidatedEvent(order.getId(), 1)
    );
}
~~~

With a synchronous multicaster, each event is dispatched in loop order on the current thread. However, if listeners are async, completion order across orders is not guaranteed.

If multiple threads publish events concurrently, no global business order emerges automatically. Observed order can depend on thread scheduling, executors, transactions, and system load.

If order only needs to be maintained per order, use an aggregate ID and sequence number. If processing must be sequential per aggregate, serialize work by aggregate key or use a partitioned message stream. Do not rely on timestamps alone as absolute proof of ordering when multiple machines or threads publish events concurrently.

## 9. Choosing One Consolidated Event or Multiple Events?

It is not always necessary to publish an event for every internal step.

### Use Multiple Events When Each Milestone Has Independent Meaning

For example, InventoryReserved and OrderConfirmed may interest different modules because each occurrence has its own meaning. Publishing each event after its corresponding occurrence lets modules react within their exact scope.

### Use One Consolidated Event When Only the Final Outcome Needs Notification

If validation, reservation, and confirmation are purely internal details of a use case, and no module needs to know each milestone, a single OrderConfirmed event with a payload describing the final outcome can be simpler.

### Use Orchestration When Actions Have Mandatory Ordering

If step B must run only when step A succeeds and step C needs B's result, a coordinating service should call the services sequentially, check results, and handle errors. Events can be published after each milestone to notify interested parties, but loosely coupled listeners should not be used as the primary workflow controller.

## 10. Verifying Event Ordering

A useful check is logging dispatch order and completion order separately. Do not merely log a line in the publisher and infer that listeners have finished.

You can log the following fields:

- eventType: type of event.
- aggregateId: order ID or business entity ID.
- sequence: business sequence within the aggregate.
- eventId: unique ID to detect duplicates.
- publishedAt: timestamp when the publisher published the event.
- listenerName: listener handling the event.
- startedAt and completedAt: listener processing timestamps.
- outcome: success, failure, or retry.

When verifying, confirm:

1. Business steps are invoked in the right order.
2. Each event is published only after the corresponding occurrence happens.
3. With a synchronous multicaster, listeners finish before the corresponding publishEvent() call returns.
4. If async is enabled, check start order and completion order separately.
5. If using transaction-bound listeners, confirm listeners run only at the desired phase.
6. If the transaction rolls back, confirm AFTER_COMMIT listeners do not run.
7. If a listener fails, confirm the workflow stops or continues according to the designed policy.
8. With concurrent publishers, confirm ordering is preserved within the required aggregate scope.

## 11. Common Design Mistakes

**Publishing an event before the occurrence happens.** Publishing InventoryReserved before calling reserve() can cause listeners to believe inventory was reserved even if the operation fails. Publish after confirming success.

**Assuming multiple publishEvent calls always mean listeners finish sequentially.** This only holds for synchronous dispatch on the same calling thread. Async and executors can cause listeners to overlap.

**Using @Order to sequence multiple event types.** @Order orders listeners within one multicaster dispatch; it does not coordinate a business chain across separate publish calls.

**Using event listeners to replace mandatory business steps.** If the use case needs a result or must stop immediately when a step fails, call the service directly and orchestrate explicitly.

**Publishing events in a transaction and immediately sending emails with a synchronous listener.** The transaction may roll back after the email has been sent. Consider AFTER_COMMIT or an outbox depending on required guarantees.

**Assuming AFTER_COMMIT guarantees no lost events.** The listener can fail or the process can stop after commit. Critical work requires durable storage and retries.

**Not handling duplicates.** Outboxes, brokers, and retries can deliver the same message multiple times. Consumers should be idempotent and identify events by unique ID.

**Ignoring ordering across publishers.** Two requests updating the same aggregate can publish events concurrently. Transaction/concurrency control and per-aggregate sequences are needed if ordering is a business condition.

**Bundling too many occurrences into a generic event.** Events named ProcessFinished or DataChanged with vague payloads make it hard for listeners to understand their meaning. Use names and data that clearly express domain events.

## 12. Quick Selection Rules

- Need to perform a mandatory step and know its result: call the service directly.
- Need to announce multiple business milestones that have happened: publish multiple events sequentially after each milestone.
- Need synchronous listeners to finish before the next step: use synchronous dispatch and let exceptions follow the chosen error policy.
- Need to react only after commit: use @TransactionalEventListener with AFTER_COMMIT.
- Need async processing: explicitly design the executor, error handling, ordering, and transactions.
- Need zero event loss on process crash: use an outbox or durable storage mechanism.
- Need ordering within each aggregate: use aggregate ID, sequence, and sequential processing per aggregate.
- Only need to announce the final outcome: consider one consolidated event instead of multiple events with no separate consumers.

**Remember:** publishEvent() order reflects the order in which the publisher emits events. With a synchronous multicaster, each event's listeners are dispatched before the next call runs. When using async, multiple threads, or transaction-bound listeners, completion order and durability must be designed separately. Events announce what has happened; service orchestration controls mandatory steps.

## References

- [ApplicationEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [ApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [SimpleApplicationEventMulticaster — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [TransactionalEventListener — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Application Events — Reference](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)