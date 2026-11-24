# TransactionalEventPublisher in Spring Reactive

TransactionalEventPublisher is a delegate dedicated to publishing application events within a reactive transaction. This API was introduced in Spring Framework 6.1 and resides in the org.springframework.transaction.reactive package.

A distinctive trait of reactive transactions is that transaction state is held in the Reactor Context rather than relying on ThreadLocal like imperative transactions. Therefore, when publishing an event in a reactive pipeline, simply calling regular ApplicationEventPublisher.publishEvent() may not carry the transaction information that @TransactionalEventListener needs to register a callback.

TransactionalEventPublisher solves this by setting the current TransactionContext as the event source. Listeners can use @TransactionalEventListener to attach processing to a reactive transaction phase, such as running only after a successful commit.

## 1. Why do reactive transactions need TransactionalEventPublisher?

With imperative transactions using PlatformTransactionManager, Spring typically binds the transaction to the current thread. Synchronous listeners running on the same thread can see that transaction context.

Reactive transactions use ReactiveTransactionManager and the Reactor Context. A pipeline can switch across multiple threads while the transaction is still preserved along the subscriber context. Consequently, a listener cannot rely on the current thread's ThreadLocal to look up a reactive transaction.

Since Spring Framework 6.1, @TransactionalEventListener supports both:

- Imperative transactions managed by PlatformTransactionManager.
- Reactive transactions managed by ReactiveTransactionManager.

For reactive transactions, TransactionContext must be placed into the event instance as the event source. TransactionalEventPublisher is a convenient delegate that performs this step.

Conceptual processing flow:

    Reactive service
          |
          v
    Reactive transaction
    (Reactor Context)
          |
          v
    TransactionalEventPublisher
          |
          | event source = TransactionContext
          v
    ApplicationEventPublisher
          |
          v
    @TransactionalEventListener
          |
          v
    Transaction phase callback
    (BEFORE_COMMIT / AFTER_COMMIT / ...)

TransactionalEventPublisher only assists with the step of publishing an event that carries a transaction context. It does not create transactions, commit or roll back transactions, nor replace the transaction manager.

## 2. Package, version, and API

Import the class from the package:

~~~java
import org.springframework.transaction.reactive.TransactionalEventPublisher;
~~~

The class was introduced in Spring Framework 6.1 and has a constructor accepting an ApplicationEventPublisher:

~~~java
public TransactionalEventPublisher(
    ApplicationEventPublisher eventPublisher
)
~~~

There are two main overloads:

| Method | Parameter | Return value | Purpose |
|---|---|---|---|
| publishEvent(Object payload) | Business payload | Mono<Void> | Creates a PayloadApplicationEvent with TransactionContext as source |
| publishEvent(Function<TransactionContext, ApplicationEvent>) | Function creating an ApplicationEvent from TransactionContext | Mono<Void> | Creates a custom ApplicationEvent whose source is TransactionContext |

Both return Reactor Mono<Void>. Retrieving the transaction context and publishing the event occur when the Mono is subscribed to within an appropriate reactive context.

### publishEvent(Object payload)

This overload is suitable when you only need to send a plain Java payload:

~~~java
Mono<Void> publication =
    transactionalEventPublisher.publishEvent(
        new OrderConfirmedPayload(orderId)
    );
~~~

The delegate retrieves the current TransactionContext and creates a PayloadApplicationEvent with:

- Source: current TransactionContext.
- Payload: OrderConfirmedPayload.

There is no need to write a class extending ApplicationEvent just to attach the transaction context to the event.

**Important limitation:** if the passed object is already an ApplicationEvent, this overload returns a Mono failing with IllegalArgumentException. The API cannot automatically wrap an existing ApplicationEvent while preserving the transaction source this way.

### publishEvent(Function<TransactionContext, ApplicationEvent>)

Use this overload when you need to create a custom event extending ApplicationEvent:

~~~java
Mono<Void> publication =
    transactionalEventPublisher.publishEvent(
        transactionContext ->
            new OrderConfirmedEvent(transactionContext, orderId)
    );
~~~

The function receives TransactionContext and uses it as the event source. This is appropriate when the event has its own payload, an explicit type name, or needs to preserve a specific event contract.

If no TransactionContext is found in the Reactor subscriber context or context holder, retrieving the context fails with NoTransactionException. Therefore, call this API inside an actual reactive transaction pipeline.

## 3. Registering TransactionalEventPublisher as a Spring bean

You can create the delegate using Java configuration:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Configuration
class TransactionalEventConfiguration {

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher eventPublisher) {
        return new TransactionalEventPublisher(eventPublisher);
    }
}
~~~

ApplicationContext implements ApplicationEventPublisher, so this abstraction can be injected directly. Business services only need to inject TransactionalEventPublisher.

Avoid creating a new instance inside each business method if the application already has a shared bean. The delegate holds a reference to ApplicationEventPublisher; the transaction context is still looked up at the time the reactive Mono executes.

## 4. Example: publishing a custom event in a reactive transaction

Suppose the application has a reactive repository updating order status. After the update succeeds, the service publishes OrderConfirmedEvent and a listener processes it only after commit.

Custom event:

~~~java
import java.util.UUID;
import org.springframework.context.ApplicationEvent;
import org.springframework.transaction.reactive.TransactionContext;

public final class OrderConfirmedEvent extends ApplicationEvent {

    private final UUID orderId;

    public OrderConfirmedEvent(
            TransactionContext transactionContext,
            UUID orderId) {
        super(transactionContext);
        this.orderId = orderId;
    }

    public UUID getOrderId() {
        return orderId;
    }
}
~~~

TransactionContext is used as the source. orderId is the business data the listener actually needs for processing.

Reactive service:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactiveOrderService(
            ReactiveOrderRepository orderRepository,
            TransactionalEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Mono<Void> confirm(UUID orderId) {
        return orderRepository.markConfirmed(orderId)
            .then(
                eventPublisher.publishEvent(
                    transactionContext ->
                        new OrderConfirmedEvent(
                            transactionContext,
                            orderId
                        )
                )
            );
    }
}
~~~

ReactiveOrderRepository is an application repository; its markConfirmed(UUID) method returns Mono<Void>. The example assumes the service is managed by ReactiveTransactionManager and the repository participates in the same reactive transaction.

Steps occurring within the same reactive pipeline:

1. The transaction interceptor opens a reactive transaction.
2. The repository updates the order status.
3. After the update completes, publishEvent(Function) retrieves TransactionContext from the Reactor Context.
4. The Function creates OrderConfirmedEvent with TransactionContext as source.
5. ApplicationEventPublisher receives the event.
6. @TransactionalEventListener registers processing at the chosen phase.
7. The transaction manager finishes committing or rolling back and triggers the corresponding callback.

The key point to uphold is that calling publishEvent() must be composed into the pipeline using then(), flatMap(), or an equivalent operator. Do not split it into an independent subscription.

## 5. Receiving events with @TransactionalEventListener

A listener can declare the phase in which it wants to participate:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderConfirmationListener {

    private final OrderNotificationService notificationService;

    public OrderConfirmationListener(
            OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        notificationService.sendConfirmation(event.getOrderId());
    }
}
~~~

Because the event source is TransactionContext, Spring can associate the listener with the corresponding reactive transaction. With AFTER_COMMIT, the listener is only triggered after the transaction commits successfully.

Supported phases:

| Phase | Execution timing |
|---|---|
| BEFORE_COMMIT | Before the transaction commits |
| AFTER_COMMIT | After a successful commit; default |
| AFTER_ROLLBACK | After the transaction rolls back |
| AFTER_COMPLETION | After the transaction completes, whether commit or rollback |

If the transaction rolls back, an AFTER_COMMIT listener does not run. An AFTER_ROLLBACK or AFTER_COMPLETION listener can be triggered according to the declared phase.

If an event is published without a suitable transaction, @TransactionalEventListener is not invoked by default. The fallbackExecution = true attribute allows fallback execution when there is no transaction, but it does not replace passing TransactionContext for reactive events.

## 6. Using a payload instead of a custom ApplicationEvent

If a custom event class is not needed, you can use the publishEvent(Object) overload:

~~~java
public record OrderConfirmedPayload(UUID orderId) {}
~~~

In the service:

~~~java
return orderRepository.markConfirmed(orderId)
    .then(
        eventPublisher.publishEvent(
            new OrderConfirmedPayload(orderId)
        )
    );
~~~

TransactionalEventPublisher automatically creates a PayloadApplicationEvent with TransactionContext as source and OrderConfirmedPayload as payload.

A listener can declare the corresponding PayloadApplicationEvent type if it wants to access both the wrapper and the payload:

~~~java
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener
public void on(
        PayloadApplicationEvent<OrderConfirmedPayload> event) {
    UUID orderId = event.getPayload().orderId();
    // Process confirmed order.
}
~~~

This approach is useful when you want to clearly distinguish the event wrapper from the payload. If the application needs a dedicated event class with a business name and specific getter APIs, using the Function(TransactionContext, ApplicationEvent) overload is easier to read.

Do not pass an ApplicationEvent object into the payload overload. If you already have a custom ApplicationEvent, create the event via the function so TransactionContext is properly set as the source.

## 7. TransactionalEventPublisher does not commit the transaction

A common misconception is thinking the name TransactionalEventPublisher means this class manages commits itself. In reality:

- ReactiveTransactionManager manages the transaction.
- TransactionalOperator or @Transactional defines the transaction boundary.
- TransactionalEventPublisher retrieves TransactionContext and publishes the event.
- @TransactionalEventListener registers processing by phase.

The Mono<Void> returned from publishEvent() represents the step of retrieving the context and handing the event off to ApplicationEventPublisher. It is not a signal that the transaction has committed, nor is it confirmation that all post-commit listeners have finished.

Therefore, do not write:

~~~java
eventPublisher.publishEvent(payload).subscribe();
~~~

This call creates a subscription detached from the current pipeline. That subscription may lack the Reactor transaction context the publisher needs, and the service also loses control over completion order or errors.

Also do not call block() inside a reactive pipeline to wait for an event. Blocking can stall the event loop, break the reactive model, and lose the expected transaction context.

Compose the returned Mono instead:

~~~java
return repository.save(order)
    .then(eventPublisher.publishEvent(payload));
~~~

As a result, the publish operation executes within the same subscription and the same Reactor Context as the business steps.

## 8. Differences between imperative and reactive event publication

Not every application needs TransactionalEventPublisher.

| Topic | Imperative transaction | Reactive transaction |
|---|---|---|
| Transaction manager | PlatformTransactionManager | ReactiveTransactionManager |
| Where transaction is held | Thread-bound state | Reactor Context |
| Regular publisher | ApplicationEventPublisher is usually sufficient | Does not automatically set TransactionContext as event source |
| How transaction is attached to event | Thread context is available to listener | Use TransactionalEventPublisher or set TransactionContext as source manually |
| Phase-bound listener | @TransactionalEventListener | @TransactionalEventListener since Spring 6.1, with event source carrying TransactionContext |

With JDBC/JPA and PlatformTransactionManager, ApplicationEventPublisher together with @TransactionalEventListener is usually sufficient. The imperative TransactionSynchronizationManager can read the thread-bound transaction.

With R2DBC or other reactive transactions, do not use the static TransactionSynchronizationManager from org.springframework.transaction.support to look up the current transaction. Use reactive APIs and keep all operations participating in the transaction within the same Reactor pipeline.

## 9. Distinguishing TransactionalEventPublisher from TransactionalEventListener

The two API names are similar, but they serve opposite sides:

- **TransactionalEventPublisher:** publisher side; puts TransactionContext into the event source inside a reactive transaction.
- **@TransactionalEventListener:** listener side; selects the transaction phase for processing.

A complete flow usually includes both:

    Reactive service
        |
        | TransactionalEventPublisher
        v
    Event with TransactionContext source
        |
        v
    ApplicationEventPublisher
        |
        v
    @TransactionalEventListener
        |
        | wait for transaction phase
        v
    AFTER_COMMIT / AFTER_ROLLBACK / ...

Do not replace TransactionalEventPublisher with @TransactionalEventListener on the publisher side. The annotation is for listener methods, not an event-publishing API.

Also do not confuse TransactionalEventPublisher with TransactionalOperator. TransactionalOperator creates the reactive transaction boundary; TransactionalEventPublisher only publishes an event tied to the existing transaction context.

## 10. Handling rollback and errors

Suppose a service updates an order and publishes OrderConfirmedEvent, but a subsequent step in the pipeline fails and the transaction rolls back.

Expected outcome:

- Database data in the transaction is rolled back.
- The AFTER_COMMIT listener does not run.
- An AFTER_ROLLBACK listener can run if registered.
- An AFTER_COMPLETION listener receives the corresponding completion status.

Example testing an error after the publish step:

~~~java
return orderRepository.markConfirmed(orderId)
    .then(eventPublisher.publishEvent(
        tx -> new OrderConfirmedEvent(tx, orderId)
    ))
    .then(Mono.error(
        new IllegalStateException("Force rollback")
    ));
~~~

This snippet is only a test scenario; do not put intentional errors into real business flows. When an error escapes the reactive transaction pipeline, the transaction manager can roll back according to its rules.

An error in an AFTER_COMMIT listener occurs after the transaction has already committed. Committed data cannot be rolled back simply because a notification or callback failed. If retries are needed, build a separate recovery mechanism.

TransactionalEventPublisher also does not turn in-memory events into durable messages. If the process stops after commit but before listeners finish, there is no automatic guarantee that the event will be replayed.

## 11. When is a transactional outbox needed?

TransactionalEventPublisher combined with @TransactionalEventListener solves binding listeners to the current transaction within an application. It does not guarantee durable delivery across process restarts.

If an event must be sent to another system and cannot be lost, consider a transactional outbox:

1. Within the same reactive transaction, update the business data.
2. Write an outbox record to the database in the same transaction.
3. Commit both the business data and the outbox record.
4. A worker reads unsent outbox records.
5. The worker sends messages to the broker or target service.
6. Record delivery status, retry on errors, and handle duplicates on the consumer.

The outbox persists the intent to publish an event in the same transaction as the business change. TransactionalEventPublisher can still be used to notify internally that a transaction just created an event or to wake a processing component; however, the outbox is the durable store for crash recovery.

Do not implement an outbox for every internal event. Use it when delivery, retry, and recovery requirements exceed what an in-memory event dispatcher can provide.

## 12. Testing reactive transactional events

Tests need a real ReactiveTransactionManager or a transaction manager integrated with a test database. StepVerifier helps assert that the reactive pipeline completes or emits an error; TransactionalOperator can establish a transaction boundary in tests.

Scenarios to cover:

1. **Successful commit:** publish an event inside a transaction; verify the AFTER_COMMIT listener is called.
2. **Rollback:** publish an event then make the pipeline fail; verify the AFTER_COMMIT listener does not run and the AFTER_ROLLBACK listener runs if present.
3. **No transaction context:** call TransactionalEventPublisher outside a reactive transaction; verify the Mono errors with NoTransactionException.
4. **Event source:** verify a custom event has TransactionContext as source or a payload event is wrapped properly.
5. **Subscription:** verify the event is published only when the Mono is subscribed to within an appropriate pipeline.
6. **Duplicates:** if a publisher may emit the same business event multiple times, verify the listener or consumer handles it idempotently.

Example test skeleton for publishing inside a transaction:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TransactionalEventPublisherTest {

    private final TransactionalOperator transactionOperator;
    private final TransactionalEventPublisher eventPublisher;

    TransactionalEventPublisherTest(
            TransactionalOperator transactionOperator,
            TransactionalEventPublisher eventPublisher) {
        this.transactionOperator = transactionOperator;
        this.eventPublisher = eventPublisher;
    }

    @Test
    void publishesWithinReactiveTransaction() {
        Mono<Void> work = Mono.defer(() ->
            eventPublisher.publishEvent(
                tx -> new OrderConfirmedEvent(tx, UUID.randomUUID())
            )
        );

        StepVerifier.create(
            transactionOperator.transactional(work)
        ).verifyComplete();
    }
}
~~~

This is an integration test skeleton. The project needs to configure ReactiveTransactionManager, TransactionalOperator, a Spring context, and the reactor-test dependency. If you want to verify an actual AFTER_COMMIT callback, add a test listener that records events into a thread-safe probe and assert after StepVerifier confirms the transaction completed.

Do not use a fake transaction manager if the goal is to verify real commit/rollback behavior. With reactive databases, run tests against a database and driver compatible with the production configuration.

## 13. Common mistakes

**Using ApplicationEventPublisher directly in a reactive transaction and expecting the listener to find the transaction.** Reactor Context is not ThreadLocal. For @TransactionalEventListener, pass TransactionContext into the event source using TransactionalEventPublisher.

**Confusing packages.** TransactionalEventPublisher is in org.springframework.transaction.reactive; @TransactionalEventListener is in org.springframework.transaction.event.

**Calling publishEvent() outside a reactive transaction.** TransactionContextManager cannot find a context and the publisher returns a Mono failing with NoTransactionException.

**Calling subscribe() inside a service.** An independent subscription can lose Reactor Context and detach errors from the calling flow. Compose the returned Mono instead.

**Using block() in a reactive pipeline.** Blocking stalls threads and breaks the reactive model. Use then(), flatMap(), or an appropriate operator.

**Passing an ApplicationEvent into the Object overload.** That overload is for payloads; passing an ApplicationEvent causes an error. Use Function<TransactionContext, ApplicationEvent> for custom events.

**Assuming the publisher commits the transaction itself.** The transaction manager handles commit/rollback. The publisher only performs the event hand-off with the transaction context.

**Assuming Mono<Void> means the AFTER_COMMIT listener has finished running.** The Mono only represents the publication step. Transaction-bound listeners run at the phase when the transaction completes.

**Assuming events are durably persisted.** The internal event dispatcher does not replace an outbox or message broker.

**Using imperative APIs to read a reactive transaction.** Use reactive transaction APIs and keep operations within the same Reactor Context.

## 14. Rules to remember

- TransactionalEventPublisher has been available since Spring Framework 6.1.
- Its package is org.springframework.transaction.reactive.
- Two overloads: publishEvent(Object) and publishEvent(Function<TransactionContext, ApplicationEvent>).
- Both return Mono<Void>.
- The current TransactionContext is used as the ApplicationEvent source.
- publishEvent(Object) is for payloads and does not accept a pre-created ApplicationEvent.
- Custom ApplicationEvents must be created via the Function overload.
- Must be called inside a reactive transaction context; missing context leads to NoTransactionException.
- Compose the Mono into the pipeline; do not subscribe or block manually.
- @TransactionalEventListener chooses the handling phase; the publisher does not commit on its own.
- Imperative transactions normally do not need TransactionalEventPublisher.
- Internal events have no durability guarantees; use an outbox if loss is unacceptable.

**Takeaway:** TransactionalEventPublisher bridges event publication with the Reactor transaction context. Use it so events carry the proper source for @TransactionalEventListener, keep the Mono inside the same reactive pipeline, and let ReactiveTransactionManager decide commit or rollback. When durable delivery is required, add an outbox or message broker.

## References

- [TransactionalEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [TransactionContextManager — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [TransactionContext — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContext.html)
- [TransactionalEventListener — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Transaction-bound Events — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Reactive Transaction Management — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [ApplicationEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)