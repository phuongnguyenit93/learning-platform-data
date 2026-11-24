# When to Use Events Instead of Direct Method Calls

In Spring, **direct method calls** are appropriate when one component needs to ask another component to perform a specific piece of work and needs to know the result. **Application events** are appropriate when one component announces that an occurrence has happened so interested components can handle their own reactions.

This decision affects how modules depend on each other, how errors propagate, processing order, and when data is committed. Events help reduce coupling between the publisher and receivers, but also make the execution flow harder to see. Therefore, only use events when the event genuinely serves as a useful communication boundary.

## 1. Distinguishing Direct Calls from Events

### Direct Method Calls

The caller knows the target object or interface, invokes a method, and can receive a result immediately.

For example, an ordering workflow needs to check a credit limit before continuing:

- OrderService calls CreditService to check the credit limit.
- CreditService returns an approval or rejection result.
- OrderService relies on that result to decide whether to create the order.

This is an intentional request. Without the result from CreditService, the caller cannot complete the workflow. An explicit interface helps express this dependency.

### Publishing an Application Event

The publisher announces a fact that has already happened. The publisher only needs to know the event's contract; it does not need to know how many listeners are registered or what the listeners will do.

For example, after an order is created, the application publishes the OrderPlaced event. Listeners can update metrics, write an audit log, or prepare a notification. OrderService does not need to call each listener.

A good event usually describes an occurrence using a past-tense name, such as OrderPlaced, PaymentCaptured, or CustomerRegistered. The event carries immutable data sufficient for listeners to understand the occurrence. Names like SendWelcomeEmail or RecalculatePrice describe a command; that is usually a sign that you are using an event to disguise an action call.

Key difference: the publisher does not receive a return value from listeners. Publishing an event is not a substitute for an API that needs to answer a question or make a business decision.

## 2. When to Use Events

### Multiple Independent Parties Need to React to the Same Occurrence

One occurrence can have multiple reactions that do not depend on one another. When OrderPlaced happens, the application can:

- Record order metrics.
- Write an audit log.
- Update an internal read model or counter.
- Instruct a notification module to prepare a receipt.

If OrderService calls each component directly, it must know the names and contracts of all of them. Whenever a new reaction is added, the event-publishing code has to change even though the order creation process has not changed.

With events, each listener subscribes to the type of occurrence it cares about. A listener can be added or removed without modifying the publisher, as long as the event contract remains suitable.

### The Reaction Is a Side Effect, Not Deciding the Main Outcome

Events fit additional work after a primary action, such as recording metrics, creating internal notifications, or updating an indicator. These tasks usually do not need to return a result to the business flow that published the event.

You need to clearly determine the criticality of the side effect. If sending a notification or synchronizing data is a mandatory obligation and must not be lost, a plain in-memory event is not a sufficient guarantee. In that case, durable storage, retries, and delivery tracking are needed; transactions and outbox are covered in section 5.

### Wanting to Reduce Coupling Between Modules

A module can publish domain events without directly referencing listening modules. This is helpful when modules have separate responsibilities, are developed independently, or may gain more listeners over time.

However, events only reduce coupling on the publisher side. Listeners still depend on the event contract and may depend on other services to process it. If the event contains an entire large entity or listeners must know too many internal details, the boundary between modules is not truly clean.

### The Occurrence Is Meaningful in the Business Model

Events like OrderPlaced, InvoiceIssued, or AccountSuspended describe what happened in the business domain. They help clearly express changes that multiple parts of the system may care about.

There is no need to create events for every function call. If an operation is merely an internal step of an algorithm or a utility call, an event usually makes the design more complex without adding value.

## 3. When to Call Methods Directly

Prefer direct calls in the following cases:

- **A return value is needed:** the caller needs data, a decision, or a status from the callee, such as checking permissions, calculating prices, or validating a credit limit.
- **The processing step is mandatory:** the workflow cannot proceed if that step has not succeeded, such as reserving inventory before confirming an order.
- **Order control is needed:** a later step must use the result of an earlier step or can only run after the earlier step completes.
- **Errors must be handled immediately in the calling flow:** the caller needs to catch errors, retry, or return an appropriate response to the user.
- **There is only one clear collaborator:** one service calling another service through an interface is a simple and easy-to-understand design.

A mandatory business sequence should usually be coordinated using intentional calls. If every step is turned into an event, control flow can become scattered across many listeners; finding the root cause of errors and understanding execution order becomes harder.

Events do not automatically make a system better. If a publisher publishes an event and then has to wait for a listener to finish in order to obtain a result, that design actually needs a direct call contract.

## 4. How Application Events Work in Spring

Spring provides ApplicationEventPublisher to publish events and supports listeners with @EventListener. Since Spring Framework 4.2, you can publish any Java object; extending ApplicationEvent is not required. With Java 17+, a record is a suitable choice for events carrying immutable data.

The example below illustrates an order being created and a listener preparing a receipt after the transaction commits. Order is the application's domain type; saving the order is placed at the comment position.

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Event describes the occurrence that happened and carries immutable data.
public record OrderPlaced(UUID orderId, BigDecimal total) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void placeOrder(Order order) {
        // Validate and save order in the transaction here.
        publisher.publishEvent(
            new OrderPlaced(order.getId(), order.getTotal())
        );
    }
}

@Component
class ReceiptListener {
    private final ReceiptService receiptService;

    ReceiptListener(ReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        receiptService.prepareReceipt(event.orderId(), event.total());
    }
}
~~~

Order and ReceiptService are application types that must be provided in a real project. The example requires configuring an appropriate transaction manager for @Transactional and transactional event listeners to work.

Key components:

- ApplicationEventPublisher is the publisher API. Call publishEvent with an event object to announce the occurrence.
- @EventListener marks a method to receive events. The method can accept the event object as a parameter.
- @TransactionalEventListener runs only according to the transaction lifecycle, with the specified phase. In the example, the listener runs after the transaction commits successfully.

### Listeners Run Synchronously by Default

When using a regular @EventListener, Spring invokes the listener synchronously on the event-publishing thread by default. The publisher continues only after synchronous listeners finish. Therefore:

- A slow listener can slow down the request or task publishing the event.
- Events do not automatically move to a background thread.
- With the default configuration, exceptions from a listener can propagate back to the event-publishing site. If the event is published inside a transaction, an exception matching the transaction's rollback rules can cause the transaction to roll back.

You can use @Order to specify the order of synchronous listeners when that order is genuinely needed. Do not rely on accidental ordering or treat independent listeners as an orchestrated business process.

### When Asynchronous Processing Is Needed

If a listener performs time-consuming work and the request does not need to wait, you can combine @Async with @EventListener or a transactional event listener, while enabling async processing with @EnableAsync and configuring an appropriate executor.

When running asynchronously:

- The listener runs on an executor thread; the publisher does not wait for the listener to finish.
- Exceptions in the listener are not returned to the publisher like a synchronous call. Appropriate async error configuration and monitoring are required.
- Do not assume completion order across listeners or across multiple events.
- The transaction context of the event-publishing thread is not automatically transferred to the async-processing thread.

Async changes timing and error handling; it does not turn an in-memory event into a durable queue.

## 5. Choosing Processing Timing Within a Transaction

When a listener runs is especially important when the event is published inside a @Transactional method.

### @EventListener Runs at Publication Time

With a regular listener, Spring invokes the listener right at the publishEvent call. If the publisher publishes an event before the transaction commits, the listener runs before commit. A synchronous listener can participate in the current transaction flow; therefore, it can see uncommitted data.

This is appropriate when the listener needs to process immediately within the same workflow and the listener's processing must affect the transaction outcome. However, it is inappropriate if the listener sends an external notification or performs an irreversible action before knowing whether the transaction will commit.

### @TransactionalEventListener Runs by Phase

Use @TransactionalEventListener when the listener needs to bind to the transaction lifecycle. The default phase is AFTER_COMMIT. Available phases include:

- BEFORE_COMMIT: runs before the transaction commits.
- AFTER_COMMIT: runs after a successful commit; this is the default.
- AFTER_ROLLBACK: runs after the transaction rolls back.
- AFTER_COMPLETION: runs when the transaction completes, regardless of commit or rollback.

By default, a transactional listener is triggered only when there is an active transaction. If the event is published outside a transaction, the listener does not run. You can enable fallbackExecution = true to allow processing even without a transaction, but you should only do so if that behavior aligns with the business logic.

With AFTER_COMMIT, data has already been committed before the listener runs. If the listener fails, the already-committed transaction cannot be rolled back. Therefore, AFTER_COMMIT helps avoid reacting to a failed transaction, but does not automatically provide retries or delivery guarantees.

### When Ensuring Events Are Not Lost Is Required

An application event within a single process is an internal notification mechanism. If the application stops abruptly after the database commits but before the listener finishes, work on the listener side may be lost. An AFTER_COMMIT listener also does not automatically persist events to durable storage.

If the business requires reliable delivery, such as never losing an invoice-sending request or synchronization to another system, consider a transactional outbox combined with a message broker:

1. Within the same business transaction, save the data changes and an outbox record.
2. A process reads the outbox and sends messages to the broker.
3. The consumer processes messages, with retries and status tracking.
4. The consumer must be idempotent because messages may be redelivered.

An outbox and broker solve durability, retries, and inter-process communication. They come with their own operational overhead; there is no need to introduce them into a small application that only has a few non-critical internal reactions.

## 6. Decision Table

| Question | Direct Method Call | Use Event |
|---|---|---|
| Does the caller need a result? | Yes | No result needed from listeners |
| Is the work mandatory to complete the use case? | Usually yes | Usually an independent reaction |
| Are multiple components interested? | Caller must coordinate each component | Publisher only publishes one event |
| Is exact order control needed? | Easy to express with calls | Requires dedicated ordering/orchestration design |
| Does the caller need to receive errors immediately? | Can receive directly | Depends on whether the listener is synchronous or async |
| Need to process after commit? | Can call after the transaction completes | Use @TransactionalEventListener |
| Need delivery guarantees across process crashes? | Needs a separate durable mechanism | Needs outbox/broker; plain internal events are not enough |

## 7. Common Design Mistakes

**Using an event to replace a call requiring a result.** For example, publishing PriceCalculationRequested and then waiting for a listener to calculate the price to continue placing an order. The publisher has no natural result-return contract. Call a service or interface directly.

**Thinking events always run in the background.** @EventListener is synchronous by default. If async is needed, an executor and error handling must be configured explicitly.

**Sending an event before commit and performing an irreversible side effect.** For example, sending a confirmation email right inside a synchronous listener, and then the transaction rolls back. Determine the appropriate business timing; AFTER_COMMIT is usually more suitable for reactions that should only run once data is committed.

**Assuming AFTER_COMMIT guarantees work will not be lost.** The listener only runs after commit, yet process crashes can still lose side effects. For mandatory work, use an outbox or durable storage mechanism with retries.

**Putting mutable entities or too much data into an event.** This makes listeners depend on internal state and potentially read mutated data. Prefer immutable events containing the ID and minimal snapshot needed. Listeners can load committed data if needed.

**Creating events for every small operation.** Too many events scatter control flow and make tracing difficult. Only publish an event when there is a meaningful occurrence and another party genuinely needs to care.

**Using events to orchestrate a mandatory sequence of steps.** If step B must run after A, step C must use B's result, and the whole workflow must return a unified result, use an orchestrating service with explicit calls. Events are better suited for independent reactions after an occurrence.

## 8. Quick Selection Rule

Ask yourself three questions:

1. Does the caller need an answer or result from the other operation to decide the next step? If yes, call the method directly.
2. Is the other work a mandatory step of the same use case whose errors must be handled immediately? If yes, prefer a direct call.
3. If it only announces an occurrence that has happened and one or more components can react on their own without the publisher needing to know the result, an event is an appropriate choice.

Once you have chosen an event, continue by deciding whether listeners run synchronously or asynchronously, which transaction phase they run in, and what level of delivery guarantee is needed. These are separate decisions; only add async or outbox when actual requirements call for them.

**Takeaway:** use direct calls to request an action and receive a result; use events to announce an occurrence and allow interested parties to react independently.