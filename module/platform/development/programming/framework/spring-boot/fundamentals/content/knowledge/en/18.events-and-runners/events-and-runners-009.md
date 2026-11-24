# ApplicationEventPublisher and Business Events in Applications

In a Spring Boot application, a single business operation often leads to multiple reactions. When an order is created, the system may save the order, update metrics, send a notification, write an audit record, and trigger subsequent processing steps. If the order-creation service directly calls every related service, it accumulates more and more dependencies and must know details of features outside its primary responsibility.

Spring provides `ApplicationEventPublisher` so one component can **publish an event** and other components can **listen for that event**. The publishing service only describes what happened, such as `OrderPlacedEvent`; listeners decide whether and how to react.

This mechanism is very useful for decoupling side reactions from the core business flow. However, its boundaries must be understood: **application events are a notification mechanism inside the Spring ApplicationContext; they are not by default a message broker, a durable queue, or a distributed transaction**. Under standard default configuration, listeners run synchronously on the event-publishing thread. If you need post-commit handling, asynchronous execution, or guaranteed delivery across crashes, you must choose appropriate supporting mechanisms.

This lesson progresses from basic publishing and listening to transactions, concurrency, reliability, testing, and common design mistakes.

## 1. What Is a Business Event?

A **business event** describes an occurrence that happened in the application domain:

- An order was placed: `OrderPlacedEvent`.
- A payment succeeded: `PaymentSucceededEvent`.
- An account was activated: `AccountActivatedEvent`.
- A document was approved: `DocumentApprovedEvent`.
- A report was generated: `ReportGeneratedEvent`.

Event names are normally in the **past tense**, because they announce a fact that already happened. This distinguishes them from commands:

| Message Type | Example | Meaning |
|---|---|---|
| Command | `PlaceOrderCommand` | Request to execute the place-order action |
| Event | `OrderPlacedEvent` | Placing the order has occurred |
| Query | `FindOrderQuery` | Request to read information |
| Result | `PlaceOrderResult` | Outcome of a specific operation |

A command typically has one responsible handler and can fail. An event can be received by multiple listeners interested in the same occurrence.

### Before and After Using Events

Directly calling multiple dependencies:

~~~text
CheckoutService
  |-- OrderRepository
  |-- EmailService
  |-- AuditService
  |-- MetricsService
  +-- LoyaltyService
~~~

Whenever a new requirement arrives, `CheckoutService` usually has to change to invoke another service.

Publishing an event:

~~~text
                 OrderRepository
                       ^
                       |
CheckoutService ---- save order
       |
       | publishEvent(OrderPlacedEvent)
       v
 ApplicationEventPublisher
       |
       +--> OrderAuditListener
       |
       +--> OrderMetricsListener
       |
       +--> OrderNotificationListener
       |
       +--> LoyaltyListener
~~~

The ordering service knows it must save the order and publish `OrderPlacedEvent`. Listeners are registered independently to handle their respective reactions.

However, removing direct dependencies does not automatically make a system simpler: maintainers still need to understand **who is listening to the event** and which reactions are mandatory. Therefore, only use events when there is a clear reason to decouple components.

## 2. What Is ApplicationEventPublisher?

`ApplicationEventPublisher` is a Spring interface in package:

~~~java
org.springframework.context.ApplicationEventPublisher
~~~

It exposes the event-publishing operation:

~~~java
void publishEvent(Object event);
~~~

Spring supports both ordinary Java objects and classes extending `ApplicationEvent`.

Example:

~~~java
public record OrderPlacedEvent(
        Long orderId,
        String customerId,
        Instant occurredAt
) {}
~~~

Creating and publishing:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent(
                order.getId(),
                order.getCustomerId(),
                Instant.now()
        )
);
~~~

There is no need to implement an event bus yourself or maintain a listener list inside the service. The Spring ApplicationContext handles routing the event to matching listeners.

### Publishing an Event Does Not Mean Processing Succeeded

`publishEvent(event)` is the act of **handing the event off to the event-publishing mechanism**. It does not guarantee every listener has finished running in every configuration, because the multicaster might use an executor, a listener might be asynchronous, or another mechanism might apply.

In a standard configuration using `SimpleApplicationEventMulticaster` without an executor, synchronous listeners run immediately on the publishing thread. Still, do not write business logic that implicitly relies on this behavior if the system might later configure async execution.

## 3. A Basic Spring Boot Example

Suppose an application has an ordering feature. We need to save the order, then publish an event so other components know about it.

### 3.1. Defining an Immutable Event

~~~java
package com.example.shop.events;

import java.time.Instant;

public record OrderPlacedEvent(
        Long orderId,
        String customerId,
        Instant occurredAt
) {}
~~~

Java `record` types give events constructor-supplied data whose fields cannot be reassigned after creation. Objects passed into a record can still be mutable; if the payload contains collections or mutable objects, make defensive copies when true immutability is needed.

Event contents should include only the data listeners need. Prefer carrying IDs and stable values rather than attaching a managed JPA entity.

### 3.2. Service Publishing the Event

~~~java
package com.example.shop.order;

import com.example.shop.events.OrderPlacedEvent;
import java.time.Clock;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;
    private final Clock clock;

    public CheckoutService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher,
            Clock clock
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
        this.clock = clock;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Order order = Order.from(command);
        Order savedOrder = orderRepository.save(order);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(
                        savedOrder.getId(),
                        savedOrder.getCustomerId(),
                        Instant.now(clock)
                )
        );

        return savedOrder.getId();
    }
}
~~~

Types `Order`, `OrderRepository`, and `PlaceOrderCommand` are application domain components. The example assumes persistence is configured along with a `Clock` bean, such as:

~~~java
@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

`CheckoutService` only needs a single Spring interface: `ApplicationEventPublisher`. It does not know how many listeners exist and does not need to import audit or notification services.

**Transaction note:** because `publishEvent` is called inside a `@Transactional` method, regular events are published **before the transaction completes**. Synchronous listeners may execute within the active transaction. This does not mean the order has committed successfully; a later section explains `@TransactionalEventListener`.

### 3.3. Listener Receiving the Event

~~~java
package com.example.shop.audit;

import com.example.shop.events.OrderPlacedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    private final OrderAuditRepository auditRepository;

    public OrderAuditListener(OrderAuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        auditRepository.record(
                event.orderId(),
                event.customerId(),
                event.occurredAt()
        );
    }
}
~~~

Spring locates `@EventListener` methods on registered beans. When an event of the matching type is published, the listener adapter invokes the corresponding method.

Basic requirements for this example to work:

- `CheckoutService` and `OrderAuditListener` must be Spring beans.
- Component scanning configuration must detect them.
- `onOrderPlaced` must have a parameter type matching the event.
- The event must be published via the matching ApplicationContext's publisher.

### 3.4. Adding Another Listener Without Modifying CheckoutService

~~~java
@Component
public class OrderMetricsListener {

    private final OrderMetrics metrics;

    public OrderMetricsListener(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        metrics.incrementPlacedOrders();
    }
}
~~~

When a new requirement to update statistics appears, we register a new listener. `CheckoutService` continues publishing the same single event as before.

This is the strength of events: **extending reactions to an occurrence without forcing the publisher to know every consumer**.

## 4. Must Events Extend ApplicationEvent?

Not required.

### Modern Approach: Using a POJO or Record

~~~java
public record AccountActivatedEvent(
        UUID accountId,
        Instant activatedAt
) {}
~~~

Publishing the event:

~~~java
publisher.publishEvent(
        new AccountActivatedEvent(accountId, Instant.now())
);
~~~

Listener receiving via `@EventListener`:

~~~java
@EventListener
public void onActivated(AccountActivatedEvent event) {
    // ...
}
~~~

Spring can wrap a POJO event inside `PayloadApplicationEvent` when interacting with traditional listener infrastructure. Application developers normally do not have to construct that wrapper themselves.

### Extending ApplicationEvent

~~~java
public class AccountActivatedSpringEvent
        extends ApplicationEvent {

    private final UUID accountId;

    public AccountActivatedSpringEvent(
            Object source,
            UUID accountId
    ) {
        super(source);
        this.accountId = accountId;
    }

    public UUID getAccountId() {
        return accountId;
    }
}
~~~

This approach requires passing `source` to the constructor. It is useful when integrating with older APIs or libraries built around `ApplicationEvent`.

### Comparison

| Representation | Advantage | Notes |
|---|---|---|
| Record/POJO | Minimal Spring coupling, concise, domain-friendly | Typically handled with `@EventListener` |
| Extending `ApplicationEvent` | Compatible with traditional listener APIs | Class depends on Spring and requires `source` |
| `PayloadApplicationEvent<T>` | Wrapper when Spring needs to represent a payload | Rarely needs manual creation |

For new business events in Spring Boot, a record or plain immutable class is a clean, straightforward choice.

## 5. How Does @EventListener Work?

`@EventListener` resides in package:

~~~java
org.springframework.context.event.EventListener
~~~

The annotation marks a method as an event receiver. Spring determines the event type from the method parameter:

~~~java
@Component
public class PaymentListeners {

    @EventListener
    public void onPaymentSucceeded(PaymentSucceededEvent event) {
        // Handle successful payment.
    }

    @EventListener
    public void onPaymentFailed(PaymentFailedEvent event) {
        // Handle failed payment.
    }
}
~~~

Each method needs a suitable contract. In typical annotation usage, a method accepts one event parameter. A listener can also specify the event class via the annotation attribute in certain cases—such as a parameterless method that simply reacts—yet for business logic, passing the event as a parameter is usually clearer.

### Listeners Match Events by Type

Spring can dispatch a single event to multiple listeners. If no matching listener exists, publishing a valid event normally does not throw an error simply because nobody is listening.

This is a double-edged sword: very convenient when a reaction is optional, yet if an action is mandatory to complete a use case, you should not rely on "surely a listener is there" without verification.

### Conditional `@EventListener`

The annotation supports a `condition` attribute using SpEL expressions. Conceptual example:

~~~java
@EventListener(condition = "#root.event.totalCents() >= 100000")
public void onLargeOrder(LargeOrderPlacedEvent event) {
    // Only handle orders meeting the threshold.
}
~~~

This example assumes `LargeOrderPlacedEvent` is a record with a `totalCents()` method. The condition expression is evaluated when the listener adapter handles the event, not when the application registers the bean.

Keep SpEL conditions short and readable. For complex business rules, calling a strongly typed policy/service inside the listener body is easier to test and maintain.

### `@Order` on Listeners

~~~java
@Component
public class OrderedOrderListeners {

    @Order(10)
    @EventListener
    public void first(OrderPlacedEvent event) {
        // ...
    }

    @Order(20)
    @EventListener
    public void second(OrderPlacedEvent event) {
        // ...
    }
}
~~~

Ordering can take effect when listeners are executed sequentially by a multicaster and ordering mechanism that supports it. Do not use `@Order` to create mandatory business dependencies between listeners, especially if a listener runs asynchronously or moves to a message broker.

If step B must wait for the result of A, express that relationship through a direct call, an orchestration service, or an explicit chain of state-transition events.

## 6. ApplicationListener: Interface-Based Event Handling

Besides `@EventListener`, Spring provides the interface:

~~~java
org.springframework.context.ApplicationListener<E extends ApplicationEvent>
~~~

Example:

~~~java
@Component
public class ContextRefreshedLogger
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: "
                        + event.getApplicationContext().getId()
        );
    }
}
~~~

This approach is common in framework integrations or when you want a listener to be a class with an explicit contract.

For business events modeled as POJOs/records, `@EventListener` is usually more convenient. You cannot use `ApplicationListener<OrderPlacedEvent>` directly as above if `OrderPlacedEvent` does not extend `ApplicationEvent`, because the interface's generic bound requires a compatible event subtype.

### Bean Listeners vs. Early-Registered Listeners

Ordinary business listeners are beans and therefore become active only once bean registration is ready. Some startup events like `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` fire before the context creates beans; they require early-registered listeners via `SpringApplication.addListeners(...)` or an equivalent bootstrap mechanism.

Do not expect a `@Component` with `@EventListener` to catch all very early bootstrap events. This differs from business events published after the application is already running.

## 7. Synchronous Execution Is the Usual Default

By default, the Spring ApplicationContext typically uses `SimpleApplicationEventMulticaster` with synchronous listener invocation. When a service publishes an event, ordinary listeners run on the event-publishing thread.

Example:

~~~java
@Service
public class RegistrationService {

    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(UUID accountId) {
        System.out.println("A. Before publish");

        publisher.publishEvent(
                new AccountActivatedEvent(accountId, Instant.now())
        );

        System.out.println("C. After publish");
    }
}
~~~

Listener:

~~~java
@Component
public class RegistrationLogger {

    @EventListener
    public void onActivated(AccountActivatedEvent event) {
        System.out.println("B. In listener");
    }
}
~~~

With a synchronous listener and default multicaster, the printed order will be:

~~~text
A. Before publish
B. In listener
C. After publish
~~~

Publishing an event does not automatically spawn a new thread. If a listener makes a slow HTTP call or runs a long database query, `publishEvent` can block for that duration and affect response times.

### Impact on Errors and Transactions

Suppose a synchronous listener throws an unchecked exception and no special `ErrorHandler` is configured on the multicaster. The exception can propagate back to the `publishEvent` call. If that call sits inside a `@Transactional` method and the exception triggers Spring's rollback rules, the transaction can roll back.

This may be desirable when the listener is a mandatory part of the workflow; or it may be a design flaw if a failing email service ends up rolling back an order creation transaction.

Never assume a listener "runs isolated" merely because it is invoked through an event publisher. **Events decouple callers; they do not inherently isolate execution time, failures, or transactions.**

## 8. Common Bug Example: Sending Email Before Transaction Commit

Consider this service:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void placeOrder(PlaceOrderCommand command) {
        Order order = orderRepository.save(
                Order.from(command)
        );

        publisher.publishEvent(
                new OrderPlacedEvent(
                        order.getId(),
                        order.getCustomerId(),
                        Instant.now()
                )
        );

        // Other DB operations could still fail.
        updateInventory(order);
    }
}
~~~

Regular listener:

~~~java
@Component
public class ConfirmationEmailListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailSender.sendConfirmation(event.orderId());
    }
}
~~~

If the listener executes synchronously when `publishEvent` is called, the email may be sent **before the transaction commits**. Afterward `updateInventory` could fail, rolling back the transaction, yet the email has already gone out. The system notifies the customer about an order that does not actually exist in the database.

This is why you must distinguish:

- **An event was published** in code.
- **The database transaction committed** successfully.
- **An external side effect completed** and is verifiable.

These three states are not identical.

## 9. @TransactionalEventListener: Choosing Timing Relative to Transactions

Spring provides `@TransactionalEventListener` to bind a listener to a transaction phase. This annotation resides in package:

~~~java
org.springframework.transaction.event.TransactionalEventListener
~~~

Example sending a notification after transaction commit:

~~~java
@Component
public class ConfirmationNotificationListener {

    private final NotificationService notificationService;

    public ConfirmationNotificationListener(
            NotificationService notificationService
    ) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterOrderCommitted(OrderPlacedEvent event) {
        notificationService.sendOrderConfirmation(
                event.orderId()
        );
    }
}
~~~

`AFTER_COMMIT` is also the default phase of `@TransactionalEventListener`. The listener attaches to transaction synchronization and runs only when the associated transaction commits successfully.

Key point: `@TransactionalEventListener` solves **when processing happens relative to the transaction**; it does not by itself make the event durable or asynchronous.

### Common Phases

| Phase | When Is the Callback Invoked? | Use Cases to Consider |
|---|---|---|
| `BEFORE_COMMIT` | Before transaction commit | Checks or state updates that must sit inside the same transaction, if appropriate |
| `AFTER_COMMIT` | After successful commit | Reactions after data is durably confirmed |
| `AFTER_ROLLBACK` | When transaction rolls back | Cleaning temporary state or recording failures, keeping persistence caveats in mind |
| `AFTER_COMPLETION` | After transaction finishes, whether commit or rollback | Cleanup/telemetry needing to know the transaction ended |

Callback timing also depends on the transaction manager and synchronization mechanism. Do not assume all transaction management approaches in an application share the same thread boundaries.

### What If There Is No Active Transaction?

By default, a `@TransactionalEventListener` invoked when **no transaction is active** will not execute its phase-bound callback.

If you want the listener to still run without a transaction, you can use:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onPlaced(OrderPlacedEvent event) {
    // ...
}
~~~

When no transaction exists, fallback allows the listener to run immediately without waiting for a nonexistent commit. Therefore, only enable `fallbackExecution = true` when those semantics are genuinely acceptable.

### Warning About Database Access in AFTER_COMMIT

After commit, some transaction resources may still be bound to the thread while the callback executes. If the listener tries to perform new database writes using default transaction propagation, those writes may participate in the already-completed transaction's resources and fail to commit as expected.

If a post-commit callback needs to reliably persist new data, consider a separate transaction:

~~~java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAfterCommit(Long orderId) {
        auditRepository.recordCommittedOrder(orderId);
    }
}
~~~

Listener invoking another service through a Spring proxy:

~~~java
@Component
public class CommittedOrderAuditListener {

    private final AuditWriter auditWriter;

    public CommittedOrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener
    public void onPlaced(OrderPlacedEvent event) {
        auditWriter.recordAfterCommit(event.orderId());
    }
}
~~~

`REQUIRES_NEW` opens an independent transaction when the call goes properly through a proxy. Putting the annotation on a method and calling it internally within the same class can bypass the transaction proxy. Also remember that if the new write after commit fails, the original order transaction has already committed and cannot automatically roll back due to that error.

### Reactive Transactions

For reactive transactions managed by `ReactiveTransactionManager`, the transaction context normally lives in Reactor context rather than ThreadLocal. Modern Spring Framework supports transactional event listeners for reactive transactions when **the transaction context is carried along with the event source/payload via a supported mechanism**, such as `TransactionalEventPublisher`.

Do not assume a plain `publishEvent` inside a reactive pipeline can always access the same transaction context in the way imperative thread-bound transactions do. When using WebFlux/R2DBC, check your Spring version's contract and use the appropriate transactional event publishing mechanism for reactive contexts.

## 10. @Async and @EnableAsync: Asynchronous Listener Handling

A listener may be slow because it sends emails, calls APIs, or processes files. Spring supports async methods via `@Async`.

Enable async support:

~~~java
@Configuration
@EnableAsync
public class AsyncEventConfiguration {

    @Bean("businessEventExecutor")
    public Executor businessEventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("business-event-");
        executor.initialize();

        return executor;
    }
}
~~~

Using the listener:

~~~java
@Component
public class AsyncOrderNotificationListener {

    private final EmailSender emailSender;

    public AsyncOrderNotificationListener(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @Async("businessEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailSender.sendConfirmation(event.orderId());
    }
}
~~~

`@Async` requires execution via Spring's async/proxy mechanism. The listener can execute on a thread from the selected executor, allowing the event-publishing thread to continue without waiting for the entire task to finish.

### What Does Async Change?

| Aspect | Synchronous Listener | `@Async` Listener |
|---|---|---|
| Thread typically used | Publishing thread | Executor thread |
| Publisher waits for listener? | Typically waits | Typically does not wait for completion |
| Exceptions | Can propagate to publisher | Typically handled by executor/async error handler |
| ThreadLocal transaction | Present if same thread | Not automatically propagated to another thread |
| Completion order | Follows synchronous call behavior | May vary depending on scheduling |
| Crash after publish | Work/event can still be lost | Queued work can still be lost |

`@Async` is a tool for **concurrency and latency**, not guaranteed durable delivery.

### Beware of Errors in `@Async` void Listeners

An async `void` method does not throw exceptions directly back to the publisher. Errors must be logged, monitored, and handled via `AsyncUncaughtExceptionHandler` or another strategy. Do not ignore errors simply because the original request already returned success.

If retries, backpressure, or high reliability are required, configure a bounded executor and retry policy; for critical business workflows, a durable queue/message broker is usually better suited.

### Async and Transactions

If an `@Async @EventListener` receives an event while the service is inside a transaction, the listener may run on another thread **before the transaction commits**. It does not share the publisher's ThreadLocal transaction. The listener might miss uncommitted data or observe inconsistent state.

If you need post-commit execution followed by handing work off to an executor, you can combine `@TransactionalEventListener(phase = AFTER_COMMIT)` with `@Async`, provided the project's async and transaction setups are configured properly. Even then, this does not guarantee durable delivery if the process crashes after commit before the task finishes.

## 11. When to Use Events vs. Calling Services Directly?

Events are not always better than method calls. Distinguish **mandatory steps required to complete the use case** from **extensible reactions after the event occurs**.

For example, when creating an order:

- Validating pricing and purchase eligibility may be mandatory steps.
- Reserving inventory under strong consistency rules may belong in the main transaction or an explicitly coordinated workflow.
- Sending a confirmation email is typically a reaction after the order commits.
- Updating a stats dashboard can run independently or be eventually consistent.

If a step must finish before returning a successful outcome, calling the service directly in orchestration is usually clearer:

~~~java
@Transactional
public Long placeOrder(PlaceOrderCommand command) {
    pricingPolicy.validate(command);
    inventoryService.reserve(command.items());

    Order saved = orderRepository.save(
            Order.from(command)
    );

    publisher.publishEvent(
            new OrderPlacedEvent(
                    saved.getId(),
                    saved.getCustomerId(),
                    Instant.now()
            )
    );

    return saved.getId();
}
~~~

If `inventoryService.reserve(...)` is mandatory, keeping it visible inside the use case lets readers follow the process and handle failures intentionally. Events suit consumers that want to know "an order was placed" without needing to jointly decide the primary outcome of the call.

### Selection Table

| Need | Usually Appropriate Mechanism |
|---|---|
| Mandatory step that must succeed before returning result | Direct service call / orchestration |
| Multiple internal consumers wanting to know about an occurrence | Application event |
| Execute reaction only when transaction commits | `@TransactionalEventListener` |
| Potentially slow work that does not require durability | `@Async` or appropriate executor |
| Event must be delivered even if process crashes | Transactional outbox / message broker + relay |
| Communication across multiple services/applications | Message broker, API, or integration event |
| Long-running sequence needing retries/compensation | Stateful workflow/saga |

### Avoid Hiding Mandatory Dependencies

If `PlaceOrder` is only valid when listener A has run and created a secondary record, yet the code hides that relationship, events have obscured the business flow. Place mandatory dependencies in an orchestrating service or an explicit transactional workflow; reserve events for responsibilities that can be decoupled cleanly.

## 12. What Should an Event Payload Contain?

A good event should carry enough information for listeners to know what happened, without carrying sensitive state or objects with hard-to-control lifecycles.

Example:

~~~java
public record OrderPlacedEvent(
        UUID eventId,
        Long orderId,
        String customerId,
        Instant occurredAt,
        String correlationId
) {}
~~~

Meaning:

- `eventId`: uniquely identifies one event emission; useful for tracing or deduplication if the event leaves the process.
- `orderId`: business object ID.
- `customerId`: customer reference, if needed by listeners.
- `occurredAt`: timestamp when the occurrence was recorded.
- `correlationId`: links logs/traces belonging to the same workflow.

Not every event needs all five fields. Only include data meaningful to consumers.

### Why Avoid Carrying JPA Entities Directly?

Error-prone example:

~~~java
public record OrderPlacedEvent(Order order) {}
~~~

If a listener runs after the transaction or asynchronously, `Order` may:

- No longer be attached to a persistence context.
- Have unloaded lazy associations, leading to errors.
- Be mutated after the event was published.
- Contain sensitive fields beyond what listeners need.
- Carry ORM proxies or state that increases coupling.

Usually it is better to carry IDs and stable values. Listeners can load needed data in their own transactions or read from a normalized payload.

### Is the Event a Snapshot or a Lookup Notification?

There are two common styles:

- **Reference event:** carries IDs; the listener queries the latest state itself.
- **Fact snapshot:** carries key values as of the moment the event occurred.

If a listener needs to know **the price at order placement time**, querying current state later could be inaccurate if the order was subsequently updated. In that case, include the relevant immutable values in the event or use an appropriate historical record.

If the event merely triggers a lookup step, an ID may suffice. Decide these semantics before designing the payload.

## 13. How Listener Errors Affect the Publisher

With the default synchronous multicaster, exceptions from a listener can propagate back to the publisher. Example:

~~~java
@Component
public class FailingListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        throw new IllegalStateException("Audit unavailable");
    }
}
~~~

If `publishEvent` occurs inside `@Transactional` and the exception goes unhandled, the original transaction may roll back per Spring's rollback rules.

Another issue is **which listeners already ran before the error occurred**. If an earlier listener sent an external HTTP request and a later listener throws an exception, rolling back the database does not undo the external request.

### Can an ErrorHandler Be Configured on the Multicaster?

`SimpleApplicationEventMulticaster` allows configuring an `ErrorHandler` and an executor when you want to customize how listeners are handled. This is an infrastructure-level extension point and requires weighing application-wide impact.

Conceptual example:

~~~java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
public ApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setErrorHandler(error -> {
        // Log / measure error according to an agreed strategy.
    });

    return multicaster;
}
~~~

Registering a custom multicaster changes how events are dispatched across the context, so only do it when truly necessary. If an error handler merely logs and swallows exceptions, callers may never realize a listener failed. For mandatory work, that behavior can be inappropriate.

Choose an error strategy based on business semantics, not simply to silence exceptions in logs.

### Event Publishing Has No Built-In Retry Queue

`ApplicationEventPublisher` does not automatically persist a "pending event" into a database to replay on failure. If a listener fails, Spring does not inherently guarantee redelivery after application restart. Keep this foundational limitation in mind.

## 14. Transactional Outbox: When Events Must Be Delivered Reliably

Suppose after an order commits, the system **must** send details to a shipping service. If you only use:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendToShipping(OrderPlacedEvent event) {
    shippingClient.createShipment(event.orderId());
}
~~~

there is a window of risk: the database transaction committed, yet the process might crash before or while the callback calls the shipping service. Because the event only existed in memory, there is no durable record to automatically reprocess it.

A common solution is the **transactional outbox**.

### Outbox Flow

~~~text
PlaceOrder transaction
        |
        +--> INSERT order
        |
        +--> INSERT outbox_event
        |
        +--> COMMIT same transaction
                    |
                    v
              Outbox table
                    |
                    v
              Relay / Worker
                    |
              publish to broker
                    |
                    v
             Consumer processes
                    |
              acknowledge / retry
~~~

The order data and the outbox record are saved **within the same database transaction**. If the transaction rolls back, both roll back. If it commits, the outbox record persists so a worker can forward it even after a process restart.

### Example Saving an Outbox Record Inside a Transaction

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final Clock clock;

    public CheckoutService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            Clock clock
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.clock = clock;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Order saved = orderRepository.save(
                Order.from(command)
        );

        OutboxMessage message = OutboxMessage.orderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                Instant.now(clock)
        );

        outboxRepository.save(message);

        return saved.getId();
    }
}
~~~

Types `OutboxRepository` and `OutboxMessage` are illustrative abstractions; the project needs to define tables, schema, serialization, retries, and delivery status.

A separate worker reads unsent records, sends them to the broker, and updates their status. If sending succeeds yet the worker crashes before marking the record sent, the record may be re-published. Therefore **consumers must be idempotent or deduplicate by eventId**.

Outbox typically enables **at-least-once delivery** when the relay, broker, and consumer are properly designed; it does not magically guarantee system-wide exactly-once semantics.

### Can Application Events Be Combined with Outbox?

Yes. An application event can notify internal components that a new outbox record arrived, waking up the relay faster. However, **the outbox record remains the durable source of truth**. If an in-memory event is lost, a periodic worker must still scan the outbox to process remaining records.

## 15. Internal Events vs. Integration Events

Do not equate events inside an ApplicationContext with messages exchanged between microservices.

| Criterion | Application event | Integration event |
|---|---|---|
| Scope | Local to one Spring ApplicationContext/JVM | Across process/service boundaries |
| Default transport | In-memory event multicaster | Broker, HTTP, or chosen transport |
| Serialization | Usually unnecessary | Usually requires schema/serialization |
| Delivery across crashes | Not durable by default | Depends on broker/producer/consumer and persistence |
| Transaction coordination | Can use local transactional listeners | Needs outbox or consistency mechanism |
| Coupling | Via Java class/type within the same app | Via message contract and versioning |

An application event can be translated into an integration event, but that is an explicit design step. Do not send entities or objects containing Spring proxies straight across the network.

### Versioning External Events

When an event is sent to external systems, its payload becomes an integration contract. Consider:

- Event name and schema version.
- Ability to add fields without breaking older consumers.
- Event ID and idempotency key.
- Timestamps and timezone conventions.
- Correlation/causation IDs where applicable.
- Sensitive data policies.
- Dead-letter queues or error-handling strategies for poisoned messages.

These concerns are typically unnecessary for simple local listeners, yet critical once events cross beyond a single Spring context.

## 16. ApplicationEventPublisher in Relation to Transactions and Threads

Options can be summarized as:

| Design | Typical Timing | Thread | Crash Guarantee |
|---|---|---|---|
| Default `@EventListener` | Immediately upon publish | Publisher thread | No |
| `@Async @EventListener` | May run after submission | Executor thread | No |
| `@TransactionalEventListener(AFTER_COMMIT)` | After successful commit | Usually transaction callback thread | No |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Work submitted after commit | Executor thread | No |
| Outbox + relay | After outbox commits and relay runs | Separate worker/process | Durable record exists for retries |

This table reflects common setups; with custom `ApplicationEventMulticaster` or special transaction managers, actual semantics may vary. Verify how events are dispatched in your running application.

### Do Not Implicitly Rely on ThreadLocal

An async listener does not automatically inherit the transaction or request context from the publisher thread. If values like user ID or correlation ID are needed, include them in the event payload or configure appropriate context propagation.

Do not expect `SecurityContextHolder`, MDC, or transaction context to appear automatically on a new thread. Spring offers executor decorators and propagation utilities, but they must be configured explicitly.

### Thread Safety of Event Payloads

An event passed to another thread should have a payload safe to share. A Java record only makes field references immutable; if a field holds a mutable `List`, byte array, or mutable entity, a listener may see state change mid-processing.

Prefer immutable value objects, IDs, primitives/value types, and immutable copies when needed.

## 17. Event Ordering and Multiple ApplicationContexts

Multiple listeners may receive the same event, yet you should not rely on an undeclared "natural" order.

In synchronous mode, `@Order` can specify invocation order when the multicaster uses an order comparator. However, when listeners use `@Async`, task completion order is no longer guaranteed by submission order. When events traverse a broker, order further depends on partitions, consumer groups, and delivery rules.

### Events Are Not a Workflow Engine

Suppose three listeners must sequentially:

1. Create an invoice.
2. Then create a shipment.
3. Then notify the customer.

If B needs the output of A and C needs the output of B, do not register all three on the same event hoping `@Order` resolves the workflow. Use an orchestration service or events clearly modeling each step's state transition:

~~~text
OrderPlaced
     |
     v
InvoiceCreated
     |
     v
ShipmentCreated
     |
     v
CustomerNotified
~~~

If the process is long-running and can fail mid-way, persist state, handle retries, and implement compensation appropriately.

### Parent/Child ApplicationContext

In complex applications with multiple ApplicationContexts arranged in a parent-child hierarchy, events from a child can propagate up to the parent per Spring's mechanism. A listener in the parent may receive events published from a child. This occasionally causes listeners to execute multiple times if the same listener or configuration is registered in multiple contexts.

When investigating duplicate event handling, check both the number of contexts and where listener beans are registered, in addition to how many times the publisher calls `publishEvent`.

## 18. Events During Startup: Connection to Runners

This chapter covers "Events and Runners," so it is important to distinguish business events from startup events and runners.

`ApplicationRunner` and `CommandLineRunner` are invoked by Spring Boot after the ApplicationContext refreshes successfully, before `ApplicationReadyEvent` is published in the normal startup flow. You can publish business events from a runner if the runner genuinely performs a task worth announcing:

~~~java
@Component
public class DemoSeedRunner implements ApplicationRunner {

    private final SeedService seedService;

    public DemoSeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seedDemoData();
    }
}
~~~

If `seedDemoData()` successfully creates a business object and needs to notify others, it can publish an event inside the service. The runner itself does not need to know every listener.

### ApplicationReadyEvent Is a Lifecycle Event

~~~java
@Component
public class ReadinessListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Perform appropriate work once the application is ready.
    }
}
~~~

`ApplicationReadyEvent` indicates startup reached the ready milestone. It differs from `OrderPlacedEvent` because it does not describe a specific domain action.

If work takes a long time or can fail, consider whether it belongs to mandatory startup, a post-start task, a scheduler, or a durable workflow. Do not turn every background job into an `ApplicationReadyEvent` listener merely to "run once."

### Very Early Startup Events

Events like `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` occur before regular bean listeners can be registered. When handling them, register listeners early with `SpringApplication` or an appropriate bootstrap mechanism.

Business events published after the ApplicationContext is ready do not face this limitation.

## 19. Testing Event Publishing and Listeners

You can test at multiple levels:

- **Service unit test:** verify the service publishes the right event.
- **Listener unit test:** call the listener method with a mock event and check behavior.
- **Spring context test:** verify events are delivered to listeners.
- **Transaction integration test:** verify `AFTER_COMMIT` runs only after a real commit.
- **Outbox integration test:** verify business data and outbox records are saved in the same transaction.

### Unit Testing the Publisher with Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    ApplicationEventPublisher publisher;

    @Mock
    Clock clock;

    @Test
    void publishesEventAfterSavingOrder() {
        // Arrange orderRepository and Clock.
        // Call CheckoutService.placeOrder(...).
        // Verify publisher.publishEvent(...) using ArgumentCaptor.
    }
}
~~~

This example is an illustrative skeleton; exact mocks, fixtures, and assertions depend on your project's APIs. This unit test does not verify Spring listener dispatch or transaction commit by itself.

### Recording Events in Spring Tests

Spring Test provides `@RecordApplicationEvents` along with the `ApplicationEvents` interface. Example:

~~~java
@SpringBootTest
@RecordApplicationEvents
class CheckoutEventsIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderPlacedEvent() {
        Long orderId = checkoutService.placeOrder(
                new PlaceOrderCommand(/* valid data */)
        );

        boolean found = applicationEvents
                .stream(OrderPlacedEvent.class)
                .anyMatch(event ->
                        event.orderId().equals(orderId)
                );

        assertTrue(found);
    }
}
~~~

`@RecordApplicationEvents` is part of Spring Test's context event support. This example assumes repositories, persistence, and a valid command are configured in the test.

Note: if a test method is annotated with `@Transactional` and Spring Test rolls back the transaction at the end of the test, `AFTER_COMMIT` listeners will not run because no commit occurs. To verify post-commit callbacks, use a test that explicitly manages and commits transactions, or an integration test that does not wrap the whole method in a rolled-back transaction.

### Testing AFTER_COMMIT Timing

A scenario worth verifying:

1. Start a transaction, save the order, publish the event.
2. Before commit: the `AFTER_COMMIT` callback has not been called yet.
3. Commit: the callback is invoked.
4. Repeat with rollback: the `AFTER_COMMIT` callback is not invoked.

You can use `TransactionTemplate` with a real transaction manager to explicitly control transactions and assertions. This kind of test is valuable when side effects must only run after a database commit.

### Testing Async Listeners

Do not rely on a fixed `Thread.sleep(...)` assuming the listener has finished. Use test synchronization mechanisms such as latches, futures, Awaitility, or timeout-controlled state polling. If a test only needs to verify listener logic, calling the method directly as a unit test is simpler.

## 20. Common Mistakes with ApplicationEventPublisher

| Symptom | Common Cause | How to Handle |
|---|---|---|
| `@EventListener` does not run | Listener is not a Spring bean or is outside component scan | Check bean registration and package scanning |
| Publishing throws no error yet nothing reacts | No matching listener type or listener condition fails | Check event type and `@EventListener(condition)` |
| Email sent even though transaction rolled back | Regular listener ran before commit | Use `@TransactionalEventListener(AFTER_COMMIT)` or outbox |
| Transaction rolls back when listener fails | Synchronous listener threw an exception in transaction flow | Revisit responsibility and error boundaries |
| `@TransactionalEventListener` does not run | Event published outside a transaction, `fallbackExecution` defaults to false | Check transaction boundaries and proxies |
| Async listener misses new data | Task ran before commit or on a thread without transaction | Handle after commit, load data in a new transaction |
| Listener runs twice | Published twice, context hierarchy, retry, or duplicate delivery | Use event ID/logs and inspect emission source |
| Events lost after restart | Events existed only in memory | Outbox and durable delivery mechanism |
| Post-commit DB write fails to persist | Used completed transaction resources or wrong boundary | Use a new service transaction such as `REQUIRES_NEW` when appropriate |
| Listener order mismatches expectations | Async, ordering, or custom multicaster | Do not use ordering to replace workflows |
| LazyInitializationException in listener | Accessing JPA entity after transaction closed | Switch payload to ID/immutable snapshot |
| Listener error disappears silently | Async void method does not propagate error to publisher | Logging, monitoring, error handling, and retries |

### Avoiding Infinite Event Loops

A listener can publish another event. If a listener for `AEvent` re-publishes `AEvent` without a stopping condition, the system can recurse or create an endless loop of tasks.

~~~text
AEvent --> Listener A
  ^            |
  |            |
  +-- publish AEvent
~~~

When chaining events, clearly define input events, output events, and transition states. Name events after distinct business steps and build guards against infinite loops or retries.

### Do Not Attach Critical Side Effects to "Fire-and-Forget" Without Tracking

If requirements demand sending notifications or updating another system, provide retries, monitoring, and persisted status. `@Async` reduces publisher latency, yet offers no guarantee that the task completes.

## 21. Workflow for Designing Business Events

A pragmatic workflow when introducing a new event:

1. **Identify what happened.** Name the event in the past tense, such as `OrderPlacedEvent`.
2. **Specify the publisher.** Which service has authority to conclude the occurrence happened, and at what exact moment?
3. **Define transaction boundaries.** Publish inside the transaction or after commit? Do any side effects need to wait for commit?
4. **Design the payload.** Use immutable data, IDs, and strictly needed fields.
5. **Classify consumers.** Mandatory synchronous, after commit, async, or requiring durable delivery?
6. **Separate listeners by responsibility.** Audit, metrics, notifications, and integration adapters should have clear boundaries.
7. **Define error handling.** Should listener failure fail the primary use case? Who retries and records status?
8. **Control concurrency.** Can the event be handled multiple times or in parallel?
9. **Add observability.** Event ID, correlation ID, proper logs, and metrics make investigation possible.
10. **Test the true semantics.** Include commit/rollback, duplicate delivery, and consumer failures where relevant.

### Example Choices for Orders

| Reaction After Placing an Order | Criticality | Suggested Design |
|---|---|---|
| Save order | Core | Repository call inside transaction |
| Validate and reserve mandatory stock | Core | Service/orchestration with explicit transaction strategy |
| Audit in same database and same transaction | Depends on invariant | Direct call or intentional synchronous listener |
| Update best-effort metrics | Non-blocking | Independent listener; explicit error handling |
| Send post-commit email | Can be deferred | Transactional listener; outbox if guaranteed delivery needed |
| Sync with shipping service | Usually needs retries | Outbox + broker/worker + idempotent consumer |
| Update search dashboard | Eventual consistency acceptable | Listener/queue matching required reliability |

## 22. Principles to Remember

- **`ApplicationEventPublisher.publishEvent` announces events inside a Spring context.** It is not a message broker or outbox.
- **Business events should describe what happened.** Use past-tense names and payloads meaningful to consumers.
- **`@EventListener` is the common way to receive POJO/record events.** Listeners must be Spring-managed beans.
- **Listeners are typically synchronous by default.** Listener errors and latency can affect the publisher thread.
- **`@TransactionalEventListener` lets you select a transaction phase.** `AFTER_COMMIT` is the default, though it does not guarantee durable delivery.
- **Without a transaction, transactional listeners normally do not run**, unless fallback execution is enabled appropriately.
- **`@Async` offloads processing to an executor.** It does not guarantee commits, retries, or persistence.
- **Outbox fits when events must not be lost after commit.** Consumers need idempotency because duplicates can occur.
- **Do not use events to hide mandatory steps of a use case.** Call services directly if that step's result determines the operation's success.
- **Avoid passing mutable JPA entities to async/post-commit listeners.** Use IDs and immutable snapshots.
- **Listener ordering does not replace orchestration.** For workflows with dependencies, use explicit stateful steps.
- **Test both event delivery and transaction semantics.** Event recording tests alone do not verify post-commit listeners.
- **Attach observability to important events.** Event IDs, correlation IDs, metrics, and logs identify which consumer failed.

## Conclusion

`ApplicationEventPublisher` allows a Spring Boot service to publish events without knowing every component that will react. `@EventListener` registers consumers by event type, while `@TransactionalEventListener` provides a mechanism to bind reactions to transaction phases. When latency reduction is needed, `@Async` can offload listeners to a dedicated executor.

The key design consideration is **how mandatory and reliable each reaction must be**. Application events suit internal coordination and extending reactions around business occurrences. If a step is mandatory before returning a result, express it in orchestration. If an event must still be processed after a process crash, use an outbox, broker, and retry/idempotency mechanisms. When you understand transaction, thread, and delivery semantics, an event system keeps code clean and extensible without introducing hidden operational dependencies.
