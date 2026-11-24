# Publishing Events After Commit with Transaction Synchronization

In a Spring application, creating an order, updating an account, or confirming a payment typically runs inside a **database transaction**. After the data is written successfully, the application may need to send a notification email to the user. If the email is sent directly in the middle of the transaction, an undesirable situation can occur: SMTP has already accepted the message, yet the database transaction subsequently rolls back. The recipient receives a notification about a change that was never committed.

One way to handle this is to **register work to run only after the transaction commits successfully**. Spring provides the **transaction synchronization** mechanism to attach callbacks to the transaction lifecycle. With the **afterCommit()** callback, the application can send the email after the database transaction has committed. At a higher application layer, **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** lets you publish an application event inside the transaction and handle it after commit.

This topic focuses on using transaction synchronization to defer email sending until after commit, choosing between direct callbacks and transactional event listeners, the limitations regarding failures and reliability, and extending to a **transactional outbox** when critical emails require durable retries.

## 1. Why publish events after commit?

Suppose a user places an order. The application needs to:

1. Create an order record.
2. Deduct or reserve inventory.
3. Save payment details.
4. Send an order confirmation email.

Database changes must remain consistent with one another. If one step fails, the transaction can roll back so the database returns to its previous state.

### Sending email before the transaction completes

~~~text
BEGIN TRANSACTION
    |
    v
Save order
    |
    v
Send confirmation email -----> SMTP already accepted message
    |
    v
Update inventory
    |
    v
Error updating inventory
    |
    v
ROLLBACK

Result:
Database has no committed order,
yet the user already received the confirmation email.
~~~

Email is an effect outside the database. A database rollback cannot recall an email already accepted by the SMTP server. This is a form of the **dual-write problem**: a single business flow writes to two independent systems without a shared distributed transaction guaranteeing both succeed or both fail.

### Waiting for commit before sending

~~~text
BEGIN TRANSACTION
    |
    v
Save order
    |
    v
Update inventory
    |
    v
Register afterCommit callback
    |
    v
COMMIT succeeds
    |
    v
afterCommit callback
    |
    v
Send email via JavaMailSender
~~~

If the transaction rolls back, the **afterCommit()** callback does not run. Only if the commit succeeds is the callback executed. Thus, the confirmation email is only sent after the database changes have committed.

This solves the problem of **sending notifications for a rolled-back transaction**. It does not make SMTP part of the database transaction, nor does it guarantee the email reaches the Inbox. Those limitations must be handled separately.

## 2. What is transaction synchronization in Spring?

**Transaction synchronization** is a mechanism allowing application components to register actions bound to the lifecycle of the current transaction. Spring's transaction manager manages registered synchronizations and invokes callbacks at the corresponding points.

Key callbacks:

| Callback | Timing | Use case |
| --- | --- | --- |
| **beforeCommit(readOnly)** | Before the transaction commits | Prepare/validate work that must finish before commit |
| **beforeCompletion()** | Before the transaction ends, whether commit or rollback | Resource cleanup |
| **afterCommit()** | After commit succeeds | Send notifications, call external services after data is committed |
| **afterCompletion(status)** | After the transaction completes, whether commit or rollback | Cleanup or recording the final outcome |

The callbacks have distinct semantics. If you need to send an email confirming a successfully saved change, **afterCommit()** is the right point. **beforeCommit()** can still be followed by a rollback, so success emails should not be sent in that callback.

### TransactionSynchronizationManager

Spring provides **TransactionSynchronizationManager** to manage synchronizations and transaction metadata bound to the current execution context.

Commonly used methods:

| Method | Meaning |
| --- | --- |
| **isSynchronizationActive()** | Checks whether synchronization is currently active |
| **isActualTransactionActive()** | Checks whether an actual transaction is currently active |
| **registerSynchronization(...)** | Registers a TransactionSynchronization into the current transaction context |
| **getSynchronizations()** | Retrieves registered synchronizations, mainly for inspection/testing |
| **getCurrentTransactionName()** | Retrieves the current transaction name if any |
| **isCurrentTransactionReadOnly()** | Checks whether the current transaction is marked read-only |

The two methods **isSynchronizationActive()** and **isActualTransactionActive()** do not have the same meaning:

- Synchronization can be activated depending on transaction manager configuration even when no actual transaction exists.
- An actual active transaction is the business precondition that a post-commit mail flow typically requires.
- **registerSynchronization(...)** requires synchronization to be active; otherwise, Spring throws IllegalStateException.

In the email-sending example, you should check both states if the method requires execution inside a real transaction.

## 3. Registering an afterCommit callback directly

Suppose a service creates an order in a transaction. After saving data, the service registers a callback to send the email:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderMailService orderMailService;

    public OrderService(
            OrderRepository orderRepository,
            OrderMailService orderMailService
    ) {
        this.orderRepository = orderRepository;
        this.orderMailService = orderMailService;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        if (!TransactionSynchronizationManager
                .isSynchronizationActive()
                || !TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new IllegalStateException(
                    "placeOrder must run inside an active transaction"
            );
        }

        Order order = Order.create(command);
        Order savedOrder = orderRepository.save(order);

        OrderPlacedEvent event = new OrderPlacedEvent(
                savedOrder.getId(),
                savedOrder.getOrderNumber(),
                savedOrder.getCustomerEmail()
        );

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        orderMailService.sendOrderConfirmation(event);
                    }
                }
        );

        return savedOrder;
    }
}
~~~

**TransactionSynchronization** is Spring's interface for receiving callbacks. The example overrides only **afterCommit()**; other callbacks retain the default behavior of modern Spring versions.

Execution flow:

1. Spring opens a transaction when invoking the **@Transactional** method through the transaction proxy.
2. The repository saves the order inside the current transaction.
3. The service registers the callback with **TransactionSynchronizationManager**.
4. If the method completes normally and the transaction commits successfully, Spring calls **afterCommit()**.
5. The callback invokes **OrderMailService**, which builds and sends the email.
6. If the transaction rolls back, the afterCommit callback is not called.

### Why check both synchronization and actual transaction?

If the service can be called from multiple code paths, checking helps catch cases where the method is not running inside a transaction as expected. If synchronization is not active, a callback cannot be registered. If there is no actual transaction, the callback cannot guarantee the "after database commit" semantics.

Another option is treating a transaction as a mandatory precondition in design and only calling the service from a controlled transactional method. Whichever option you choose, understand the transaction manager and propagation in use.

### Using immutable event data

In the example, the callback holds an **OrderPlacedEvent** object containing the ID, order number, and email address. This is data captured inside the transaction.

It can be defined as:

~~~java
public record OrderPlacedEvent(
        Long orderId,
        String orderNumber,
        String recipientEmail
) {
}
~~~

Keep callback data small and stable. Avoid holding a JPA entity with lazy-loading relationships and accessing it after commit, because the persistence context may have closed or the session may no longer be in a suitable state. If the callback needs the latest information, keep the ID and reload it using an appropriate transaction/service.

### Do not invoke the callback manually

Do not call **afterCommit()** yourself from the service to simulate a committed transaction. Callbacks are orchestrated by the transaction manager. Only register the synchronization; Spring will invoke the callback at the right time.

## 4. Using @TransactionalEventListener with AFTER_COMMIT

Direct callback registration fits when a service needs a tightly coupled post-transaction action. If you want to decouple order creation from email delivery, you can use **Spring application events** combined with **@TransactionalEventListener**.

Service publishing the event inside the transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order savedOrder = orderRepository.save(Order.create(command));

        eventPublisher.publishEvent(
                new OrderPlacedEvent(
                        savedOrder.getId(),
                        savedOrder.getOrderNumber(),
                        savedOrder.getCustomerEmail()
                )
        );

        return savedOrder;
    }
}
~~~

Listener receiving the event after commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderMailEventListener {

    private final OrderMailService orderMailService;

    public OrderMailEventListener(OrderMailService orderMailService) {
        this.orderMailService = orderMailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        orderMailService.sendOrderConfirmation(event);
    }
}
~~~

Spring registers the listener with transaction synchronization. When the transaction commits successfully, the listener is called; if the transaction rolls back, the AFTER_COMMIT listener does not run.

### Publishing an event does not mean the listener runs immediately

**ApplicationEventPublisher.publishEvent(...)** dispatches the event inside the application. With a standard **@EventListener**, the listener is normally invoked synchronously right during publish (unless configured async). With **@TransactionalEventListener**, Spring binds listener execution to the chosen transaction phase.

Flow:

~~~text
@Transactional placeOrder()
        |
        v
repository.save(order)
        |
        v
publishEvent(OrderPlacedEvent)
        |
        v
TransactionalEventListener registers synchronization
        |
        +------ transaction rolls back
        |             |
        |             v
        |       AFTER_COMMIT does not run
        |
        '-- transaction commits
                      |
                      v
              AFTER_COMMIT listener
                      |
                      v
                  Send email
~~~

Publishing the event can happen before the transaction finishes. The listener's **phase** decides when processing occurs. Thus, an event can be published yet no AFTER_COMMIT listener will be invoked if the transaction rolls back.

### Available phases

| Phase | When does the listener run? | Example |
| --- | --- | --- |
| **BEFORE_COMMIT** | Before the transaction commits | Work that must run in the pre-commit stage |
| **AFTER_COMMIT** | After commit succeeds | Sending confirmation emails, notifying about saved changes |
| **AFTER_ROLLBACK** | After rollback | Recording or emitting notifications about a failed transaction |
| **AFTER_COMPLETION** | After the transaction finishes, commit or rollback | Cleanup or outcome-independent tasks |

If no phase is declared, **AFTER_COMMIT** is the default phase of TransactionalEventListener. For success confirmation emails, specify the phase explicitly in the annotation so the intent is immediately readable on the listener.

Do not send an "order created" email in **BEFORE_COMMIT** because commit can still fail after that callback. With **AFTER_COMPLETION**, you must inspect the completion status before sending a success notification; this callback runs on rollback as well.

## 5. Behavior when there is no transaction

By default, **@TransactionalEventListener** only handles an event when an active transaction exists and the listener can be bound to it. If the event is published outside a transaction, the listener is not executed by default.

The **fallbackExecution** attribute changes this behavior:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onOrderPlaced(OrderPlacedEvent event) {
    orderMailService.sendOrderConfirmation(event);
}
~~~

When there is no transaction to synchronize with, **fallbackExecution = true** allows the listener to run as normal event handling. That means the listener can run immediately when the event is published without a preceding commit.

Therefore:

- Keep the default **fallbackExecution = false** if the strict requirement is "send only after commit."
- Enable fallback only when the business logic accepts running the listener even without a transaction.
- If the publishing method sometimes has a transaction and sometimes does not, clarify the contract of each call path.

Do not enable fallback merely to prevent events from being skipped. If an important event must be tied to a transaction, ensure the publisher is called within the proper transaction.

## 6. Comparing direct callbacks and transactional event listeners

Both approaches rely on transaction synchronization, yet express intent at different layers.

| Criterion | Direct TransactionSynchronization | @TransactionalEventListener |
| --- | --- | --- |
| Registration mechanism | Call registerSynchronization(...) | Publish application event |
| Abstraction level | Low, directly coupled to transaction | Higher, business-event oriented |
| Transaction dependency | Requires active synchronization | Listener binds to transaction when event is published inside it |
| Publisher/handler decoupling | Callback is usually registered right inside the service | Publisher does not need to know about the mail listener |
| Multiple listeners | Must coordinate manually or register multiple callbacks | Multiple listeners can receive the same event |
| Business readability | Suits small tasks tightly tied to the transaction | Suits domain events like OrderPlaced, PaymentCaptured |
| Phase control | Override required callbacks | Select phase in annotation |

### When to use a direct callback?

Choose **TransactionSynchronizationManager.registerSynchronization(...)** when:

- You only need a small technical action tied to the current transaction.
- You do not need to emit a business event for multiple components.
- The registering component already understands the transaction lifecycle.
- You want control over specific callbacks such as afterCommit or afterCompletion.

For example: after commit, invalidating a local cache related to newly updated data, or invoking a small notification adapter.

### When to use @TransactionalEventListener?

Choose **@TransactionalEventListener** when:

- There is a clear business event such as OrderPlaced or AccountActivated.
- The publisher should not depend on the mail service.
- Multiple handlers may react after commit: sending email, writing external audit logs, updating a search index.
- You want to declare the transaction phase via annotation.

For example: the order service publishes OrderPlacedEvent; an email listener sends the confirmation, while another listener updates a notification system.

### Do not register both for the same email

If you both register a direct callback to send an email and publish an event whose listener sends the same email, the recipient may receive two emails. Choose one responsible sender per business event and keep track of listeners/handlers registered in the application.

## 7. Integrating with JavaMailSender

A post-commit listener can call a regular mail-sending service. This service is responsible for building the MIME message and sending it with **JavaMailSender**.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(OrderPlacedEvent event) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");

            helper.setFrom("orders@example.test");
            helper.setTo(event.recipientEmail());
            helper.setSubject(
                    "Order confirmation " + event.orderNumber()
            );
            helper.setText(
                    "Order " + event.orderNumber()
                            + " has been created successfully."
            );

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new OrderMailException(
                    "Cannot create confirmation email for order "
                            + event.orderNumber(),
                    ex
            );
        }
    }
}
~~~

Example business exception:

~~~java
public class OrderMailException extends RuntimeException {

    public OrderMailException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

In a real application, use standardized HTML/plain-text templates and mail models. The key point here is that **OrderMailService does not open the order-creation transaction itself**; it is only invoked from the listener after the order-creation transaction has committed.

### Where should the email address and content come from?

There are two common approaches:

- The event carries values resolved inside the transaction, such as order ID, order number, and recipient email at order creation time.
- The event carries only the ID; the listener calls a service to load the latest data after commit.

Choose based on business requirements. If the email must reflect the exact address at order placement time, store that snapshot in the event or order data. If it must use the account's current address, the listener can reload it. Do not pass a JPA entity with lazy relationships into an event expecting all properties to remain accessible after commit.
## 8. What happens if email sending fails after commit?

This is the most important point to understand when using afterCommit.

When the **afterCommit()** callback is invoked, the database transaction has already committed successfully. If SMTP times out, the server rejects the message, or JavaMailSender throws an exception, **the database does not automatically roll back**. An already-committed transaction cannot be undone by throwing an exception from a post-commit callback.

Example:

~~~text
Database transaction
    |
    v
COMMIT succeeds
    |
    v
afterCommit()
    |
    v
JavaMailSender.send(...)
    |
    +---- SMTP succeeds
    |          |
    |          v
    |      Email accepted by SMTP
    |
    '-- SMTP error
               |
               v
          Exception/log

Database remains in committed state.
~~~

### An exception from afterCommit does not mean the transaction rolled back

Spring allows exceptions thrown from **afterCommit()** callbacks to propagate to the caller in certain synchronous execution paths. The caller may see an error even though the database committed. That easily causes confusion if an API returns a generic error like "order placement failed."

Example:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    // Save order and register afterCommit.
    // If SMTP fails in afterCommit, the caller may receive an exception.
    // However, the committed order still exists in the database.
}
~~~

Therefore, distinguish between:

- **Business transaction failed**: the database did not commit.
- **Post-commit action failed**: the database committed, but sending email or a follow-up task failed.

Do not return a message like "order was not created" solely because sending email failed after commit. Record the email-sending status separately, provide the created order number, and maintain a retry or reprocessing strategy.

### Handling exceptions inside the callback

If using a direct callback, you can catch the exception to log it and pass it to monitoring:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    orderMailService.sendOrderConfirmation(event);
                } catch (OrderMailException ex) {
                    log.error(
                            "Order {} committed but failed to send email",
                            event.orderNumber(),
                            ex
                    );
                    mailFailureRecorder.record(event, ex);
                }
            }
        }
);
~~~

This is an error-handling example; **mailFailureRecorder** must be designed to match status-persistence and retry requirements. If the recorder writes to the database, pay attention to the new-transaction rules in the next section. Logging alone may suffice for low-stakes emails, but is not enough if the system must guarantee resending.

With transactional event listeners, also put clear exception handling and monitoring in place. Do not let an SMTP error be mistaken for a rollback of a completed business operation.

### SMTP accept does not mean the recipient read it

When JavaMailSender.send(...) returns successfully, it usually indicates that transport completed the send/submission step per its contract. It does not prove the email landed in the Inbox, did not bounce, or was read by the recipient. Delivery/bounce tracking requires mail provider mechanisms.

## 9. Writing to the database inside afterCommit and REQUIRES_NEW

After commit, callbacks may still be invoked while transaction resources remain bound to the thread. Depending on the transaction manager, connections or persistence resources may still be reachable during the callback phase, yet the original transaction **has already finished and will not commit again**.

This creates an easy trap: an afterCommit callback calls repository.save(...), and the statement may join the still-bound resource without being committed as an independent new transaction.

If the callback needs to write email-sending status, use a separate transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailStatusService {

    private final MailStatusRepository repository;

    public MailStatusService(MailStatusRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSent(Long orderId) {
        repository.markMailSent(orderId);
    }
}
~~~

**REQUIRES_NEW** instructs Spring to open an independent transaction for this operation. That transaction can commit on its own, independently of the already-finished order-creation transaction.

### Must be invoked through a Spring proxy

For **REQUIRES_NEW** propagation to take effect under the standard proxy model, the method must be called through a Spring bean proxy. Calling a REQUIRES_NEW method via self-invocation inside the same object typically bypasses the proxy, so the annotation may not be applied.

Extracting **MailStatusService** into a separate bean ensures the call from the listener goes through the proxy. Other transaction mechanisms can also be used, as long as you verify propagation is actually activated.

### Do not use REQUIRES_NEW mechanically for every operation

Only use a new transaction when the callback needs an independent database write after commit. If the callback only sends email over SMTP, there is no need to open a new database transaction just to call JavaMailSender.

When recording send status, define the order clearly:

1. Send the message.
2. If transport reports success, record submitted status.
3. If sending fails, record error status and retry metadata.

This ordering still has a failure window: SMTP may have accepted the message while the application dies before writing the status. On retry, the email could be sent twice. A transactional outbox and idempotency improve control, though email over SMTP generally lacks an exactly-once guarantee.

## 10. Running post-commit tasks asynchronously

An afterCommit callback runs synchronously on the transaction execution thread unless an async mechanism is used. If sending an email takes several seconds, the order-creation request may have to wait for the callback to finish.

One approach is combining a transactional event listener with **@Async**:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderMailListener {

    private final OrderMailService orderMailService;

    public AsyncOrderMailListener(OrderMailService orderMailService) {
        this.orderMailService = orderMailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        orderMailService.sendOrderConfirmation(event);
    }
}
~~~

The application must enable async execution and configure an executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.Executor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

The transactional event listener is bound to the transaction phase; when the AFTER_COMMIT phase arrives, the listener invocation can be handed off to the executor via @Async. Real-world configurations should manage pool size, queue capacity, shutdown, and rejection policies based on application load.

### Async does not automatically guarantee retries

When using @Async:

- The transaction has already committed before the listener is processed.
- Work runs on an executor thread; the original thread's transaction context does not automatically propagate to the new thread.
- Exceptions are not returned directly to the already-completed HTTP request.
- If the queue fills up, the executor shuts down, or the process stops abruptly, tasks may fail or be lost without a durable queue.
- Logging, metrics, and exception handling must be configured for async tasks.

If the email is highly critical, an in-memory executor is no substitute for a durable queue or transactional outbox.

### Do not pass transaction-bound resources to async threads

Do not pass a JDBC Connection, a transaction-bound EntityManager, or a JPA entity with lazy relationships to an async task. Pass an immutable event containing the ID and necessary data. If the worker needs to query the database, it opens a new transaction on its own thread.

## 11. Transaction propagation and callback timing

Callback timing depends on the actual transaction to which the synchronization is bound.

### Propagation REQUIRED

**REQUIRED** is the default for @Transactional. If a transaction already exists, the method joins it; if not, Spring starts a new one.

~~~text
Outer @Transactional
    |
    +-- OrderService.placeOrder() REQUIRED
    |       |
    |       +-- save order
    |       '-- register afterCommit
    |
    +-- OtherService.updateInventory() REQUIRED
    |
    v
Outer transaction COMMIT
    |
    v
afterCommit callback runs
~~~

If multiple REQUIRED methods participate in the same transaction, the callback runs when the final physical transaction commits, not immediately when an inner method returns.

### Propagation REQUIRES_NEW

**REQUIRES_NEW** suspends the outer transaction and opens an independent transaction:

~~~text
Outer transaction
    |
    +-- invoke inner method REQUIRES_NEW
    |       |
    |       v
    |   Inner transaction
    |       |
    |       +-- register callback
    |       |
    |       v
    |   Inner COMMIT
    |       |
    |       v
    |   Inner afterCommit callback
    |
    v
Outer continues
    |
    v
Outer ROLLBACK
~~~

A callback in a REQUIRES_NEW transaction can run as soon as the inner transaction commits, even if the outer transaction later rolls back. This may be right if the inner transaction's logic is independent; if the confirmation email depends on the entire outer transaction, avoid accidentally registering the callback inside an independent inner transaction.

### Nested transactions or savepoints

With **NESTED** or savepoints, synchronization callbacks are normally bound to the outer physical transaction. A nested scope ending does not mean the whole transaction has committed. If a savepoint rolls back, do not expect afterCommit to run at that moment.

Exact behavior depends on the transaction manager and resource type. When using nested transactions, check how your transaction manager supports savepoints and actual completion timing.

### Calling transactional methods via self-invocation

In default proxy mode, Spring applies @Transactional when calls pass through the proxy. If a method in the same class directly calls another @Transactional method on `this`, the target method's annotation may not be applied.

Example:

~~~java
public void submit() {
    this.placeOrder(); // internal self-invocation, typically bypasses proxy
}

@Transactional
public void placeOrder() {
    // Do not assume the transaction proxy opened a transaction here.
}
~~~

If no transaction is opened, an AFTER_COMMIT event listener may not be registered or a direct callback has no synchronization to use. Call through a Spring bean proxy, place the transaction on a public method invoked from outside the bean, or structure beans appropriately for your application.

## 12. Limitations of in-memory callbacks and the transactional outbox

The afterCommit callback and **@TransactionalEventListener** prevent sending emails for rolled-back transactions. However, callbacks are registered in process memory. There is a window of risk:

~~~text
Database COMMIT succeeds
        |
        v
Process stops abruptly
        |
        v
Callback has not run yet
        |
        v
No email and no durable record
for a worker to know it must resend.
~~~

If the process dies after commit before the callback finishes, the in-memory event can be lost. This is a limitation of direct callbacks and transactional event listeners when used as the sole notification mechanism.

For critical emails, you can use a **transactional outbox**. The idea is to store an outbox record in the same database transaction as the business change. Because both commit or roll back together, the system has a durable trace of the work to process.

### Outbox structure

A simple outbox table might include:

| Column | Meaning |
| --- | --- |
| **id** | Unique event ID |
| **aggregate_id** | Related order/account ID |
| **event_type** | Event type, e.g., ORDER_PLACED |
| **payload** | Data required to process the event |
| **status** | PENDING, PROCESSING, SENT, or FAILED |
| **attempts** | Number of send attempts |
| **next_attempt_at** | Timestamp when next retry is allowed |
| **created_at** | Event creation timestamp |
| **sent_at** | Timestamp when transport accepted the send |
| **last_error** | Most recent recorded error |

The business transaction writes both the order and the outbox row:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.create(command));

    outboxRepository.save(
            OutboxMessage.pending(
                    "ORDER_PLACED",
                    order.getId(),
                    serializeOrderPlaced(order)
            )
    );

    return order;
}
~~~

If the transaction rolls back, both the order and the outbox row roll back. If it commits, both exist. A worker can read PENDING records to send emails afterward.

### Worker processing the outbox

~~~text
Business transaction
    |
    +--> Save Order
    |
    '--> Save OutboxMessage(PENDING)
             |
             v
           COMMIT
             |
             v
       Outbox worker polls
             |
             v
       Claim pending event
             |
             v
       Render and send email
             |
        +----+----+
        |         |
      Success    Failure
        |         |
        v         v
      SENT     Retry/backoff
                  |
                  v
               FAILED
               after limit
~~~

Workers should claim records using a mechanism that prevents multiple workers from processing concurrently, such as a PROCESSING status with a lease timeout, optimistic locking, or suitable database syntax like **FOR UPDATE SKIP LOCKED** if supported. Do not hold a database transaction open while waiting on SMTP longer than necessary.

### An outbox does not automatically create exactly-once delivery

Suppose SMTP accepted the email but the process died before the worker updated the outbox to SENT. When a worker runs again, the record may still appear unsent and the email is sent a second time.

Therefore, an outbox typically provides **at-least-once processing**: events are retried until completed or transitioned to an error state per policy. To reduce duplicate emails:

- Attach a unique event ID to the outbox record.
- Pass an idempotency key to the receiving system if the provider supports it.
- Control event claiming so multiple workers do not send concurrently.
- Store status and retry counts.
- Accept and design for possible duplicates if SMTP lacks suitable idempotency.

Do not claim emails are delivered exactly-once solely because an outbox exists. SMTP acceptance and database updates do not sit inside a single atomic transaction.

### When is an afterCommit callback sufficient?

Direct callbacks or transactional event listeners are suitable when:

- The email is only a convenience notification where rare loss is acceptable.
- The system has monitoring and operators can resend manually.
- Load is low and sending immediately after commit matters more than a durable queue.
- Post-commit tasks do not require long-term retries.

An outbox is suitable when:

- The email relates to critical transactions such as payments, invoices, or account activation.
- Events must not be lost simply because a process restarts.
- Automatic retries, status observability, and send-history investigation are needed.
- Multiple workers or multiple application instances exist.

## 13. Testing post-commit behavior

Tests must prove the callback runs only after commit and does not run on rollback. You can use **TransactionTemplate** to explicitly control transactions in integration tests.

Illustrative example:

~~~java
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

class OrderMailAfterCommitTest {

    private final PlatformTransactionManager transactionManager =
            createTestTransactionManager();
    private final OrderMailService orderMailService =
            mock(OrderMailService.class);

    @Test
    void sendsMailAfterCommit() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        OrderPlacedEvent data = sampleOrderPlacedEvent();

        template.execute(status -> {
            registerAfterCommit(orderMailService, data);
            verifyNoInteractions(orderMailService);
            return null;
        });

        verify(orderMailService).sendOrderConfirmation(data);
    }

    @Test
    void doesNotSendMailAfterRollback() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        OrderPlacedEvent data = sampleOrderPlacedEvent();

        template.execute(status -> {
            registerAfterCommit(orderMailService, data);
            status.setRollbackOnly();
            return null;
        });

        verifyNoInteractions(orderMailService);
    }
}
~~~

**createTestTransactionManager()**, **sampleOrderPlacedEvent()**, and **registerAfterCommit(...)** are test helpers to be defined according to application setup. The snippet demonstrates two core expectations:

- Inside the transaction, before commit, the mail service has not been called yet.
- After TransactionTemplate completes commit, the callback is invoked.
- When marked for rollback, the afterCommit callback is not invoked.

### Testing with @TransactionalEventListener

For event listeners, you can test using a Spring integration test and a mock mail service:

1. Open a real transaction.
2. Publish the event.
3. Verify the listener has not sent email before commit.
4. Commit the transaction.
5. Verify the mail service was called.
6. Run a rollback test and verify the mail service was not called.

If the test method itself is annotated with **@Transactional**, the test framework normally rolls back the transaction at the end of the test. An AFTER_COMMIT listener will not run in that case unless the test explicitly commits. You can use **TestTransaction.flagForCommit()** and **TestTransaction.end()** in Spring TestContext, or use TransactionTemplate to explicitly control commit timing.

### Testing async listeners

With **@Async**, the listener is handed off to an executor. Tests must wait for a completion signal with a reasonable timeout, such as Awaitility or a CountDownLatch. Do not use long fixed sleeps because they slow down tests and cause flakiness.

Also test cases where the executor rejects tasks, the mail service throws exceptions, and retry/monitoring behaves as designed.

### Testing without a transaction

With **fallbackExecution = false**, publishing an event outside a transaction does not invoke the transactional listener. Write a test for this behavior if the application has call paths that could publish events outside a transaction.

## 14. Common pitfalls

### Pitfall 1: Sending email directly inside a @Transactional method

If sending succeeds while a subsequent database step rolls back, the recipient still receives an inaccurate notification.

**Remedy:** register an afterCommit callback or publish an event for an AFTER_COMMIT listener to handle.

### Pitfall 2: Using BEFORE_COMMIT for success emails

The callback runs before the transaction actually commits; a subsequent commit error can still cause a rollback.

**Remedy:** use AFTER_COMMIT for notifications confirming saved changes.

### Pitfall 3: Registering synchronization when inactive

registerSynchronization(...) requires transaction synchronization to be active. Otherwise, Spring throws IllegalStateException.

**Remedy:** check the state or ensure the method is called inside a Spring-managed transaction.

### Pitfall 4: Event published outside a transaction

By default, a transactional event listener has no transaction to bind to and does not run.

**Remedy:** publish the event inside a transactional method; enable fallbackExecution only if business rules allow running without a transaction.

### Pitfall 5: Enabling fallbackExecution while still assuming the listener always runs after commit

When there is no transaction, the listener can run immediately along the fallback path.

**Remedy:** keep the default fallbackExecution = false if post-commit execution is mandatory.

### Pitfall 6: Assuming an exception in afterCommit rolls back the database

The database already committed before the callback ran. An SMTP exception cannot reverse the commit.

**Remedy:** separate business errors from post-commit errors; record and retry separately.

### Pitfall 7: Writing to the database inside afterCommit without opening a new transaction

Transaction resources may still be bound in the callback, yet the original transaction has committed and will not commit again.

**Remedy:** use a new-transaction service with Propagation.REQUIRES_NEW if status must be persisted after commit.

### Pitfall 8: Using @Async and expecting the transaction context to propagate automatically

Executor threads do not inherit the transaction context of the event-publishing thread.

**Remedy:** pass only immutable data/IDs; have the worker open a new transaction if it needs database access.

### Pitfall 9: Synchronous mail sending slowing down requests

SMTP can be slow or time out, causing synchronous callbacks to prolong post-commit response times.

**Remedy:** use an executor or outbox worker when appropriate; configure timeouts and concurrency limits.

### Pitfall 10: In-memory callbacks lost when the process stops

The database committed, but the application stopped before the callback finished; there is no durable event to recover.

**Remedy:** use a transactional outbox if losing events is unacceptable.

### Pitfall 11: Using REQUIRES_NEW in the wrong place

An inner REQUIRES_NEW transaction can commit and trigger callbacks even when the outer transaction rolls back.

**Remedy:** determine which business transaction the callback belongs to; avoid placing the listener in an independent transaction if the email depends on the outer commit.

### Pitfall 12: Holding a JPA entity in an event and accessing it after commit

The entity may be detached; lazy relationships may fail to load and data may have changed.

**Remedy:** use an immutable event containing IDs and the needed data snapshot.

### Pitfall 13: Treating SMTP accept as successful delivery

JavaMailSender returning does not prove the email reached the Inbox or was read by the recipient.

**Remedy:** track provider events, bounces, and delivery status when needed.

## 15. Thread context and transaction manager types

The direct callback examples in this article use Spring's **imperative transaction management**, typically paired with **PlatformTransactionManager**, JDBC, or JPA.

In the imperative model, transaction resources and synchronizations are bound to the current thread. Therefore:

- Registering synchronization must happen on the thread participating in the transaction.
- Publishing an event meant to bind to the transaction must also happen in that execution context.
- Switching to another thread with Executor, CompletableFuture, or @Async does not carry the transaction context along automatically.
- Another thread must open a new transaction if it needs to access the database in its own transaction.

Example of what not to do:

~~~java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.create(command));

    CompletableFuture.runAsync(() -> {
        // Another thread does not participate in placeOrder()'s transaction.
        eventPublisher.publishEvent(new OrderPlacedEvent(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomerEmail()
        ));
    });
}
~~~

An event published from another thread does not automatically bind to placeOrder's transaction. With a default transactional event listener, without a matching transaction context, the listener may not run.

Publish the event directly inside the transaction so Spring registers the listener into transaction synchronization; only the post-phase execution should be handed off to an executor if needed.

### Reactive transactions

Applications using **ReactiveTransactionManager** and Reactor have a transaction context that differs from thread-bound imperative transactions. Do not use the imperative TransactionSynchronizationManager examples above in reactive flows.

Recent Spring versions support transactional event listeners with reactive transaction contexts, but events must carry the transaction context via Spring-provided mechanisms such as **TransactionalEventPublisher**. Use the reactive transaction synchronization API corresponding to your Spring version.

If the application uses WebFlux/R2DBC, explicitly check whether the transaction manager is imperative or reactive before choosing an API. Do not convert a thread-bound callback to a reactive pipeline merely by changing the return type to Mono or Flux.

## 16. Using afterCompletion when you need to know both commit and rollback

If you need a callback that runs when the transaction finishes in either outcome, override **afterCompletion(int status)**:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == TransactionSynchronization.STATUS_COMMITTED) {
                    auditLogger.recordCommitted(orderId);
                } else if (status == TransactionSynchronization.STATUS_ROLLED_BACK) {
                    auditLogger.recordRolledBack(orderId);
                }
            }
        }
);
~~~

Common status constants:

| Constant | Meaning |
| --- | --- |
| **STATUS_COMMITTED** | Transaction committed |
| **STATUS_ROLLED_BACK** | Transaction rolled back |
| **STATUS_UNKNOWN** | Final outcome could not be determined |

For success confirmation emails, **afterCommit()** remains clearer because the callback can only run after commit. **afterCompletion()** fits when one place must handle both outcomes or clean up resources regardless of how the transaction ends.

Do not send success emails unconditionally in afterCompletion. If you choose this callback, inspect status before invoking the mail service.

## 17. Implementation choice checklist

Before deciding between a callback, transactional event listener, or outbox, answer these questions:

| Question | Recommended direction |
| --- | --- |
| Must the email be sent only if the transaction commits? | AFTER_COMMIT |
| Is there only one small technical task tied to the transaction? | Direct TransactionSynchronization |
| Is there a business event needing multiple handlers? | ApplicationEventPublisher + @TransactionalEventListener |
| Should the listener run when there is no transaction? | Keep fallbackExecution=false if post-commit is mandatory |
| Can SMTP slow down requests? | Async executor or worker |
| Must emails not be lost on process restart? | Transactional outbox or durable messaging |
| Does the callback need to write database status after commit? | Separate transactional service, usually REQUIRES_NEW |
| Might email sending need retries? | Store status, attempts, backoff, and handle duplicates |
| Does the application use reactive transactions? | Use the corresponding reactive transaction context/API |

A common implementation choice:

~~~text
Convenience notification email, rare loss acceptable
    -> @TransactionalEventListener(AFTER_COMMIT)
    -> send synchronously or via executor

Critical transactional email, needs retry and recovery
    -> write outbox row in the same business transaction
    -> worker reads and sends after commit
    -> store status, retry, monitor, and handle duplicates
~~~

## 18. Practice scenarios

### Scenario 1 — Order rolls back after sending email

The service sends an email right after repository.save, then an inventory update fails and the transaction rolls back.

**Question:** why did the user still receive the email?

**Answer:** SMTP is external to the database. Rollback only undoes database changes; it does not recall an email already accepted by SMTP. Move email sending to AFTER_COMMIT.

### Scenario 2 — Register callback, then transaction rolls back

The service calls registerSynchronization and then throws an exception causing the transaction to roll back.

**Question:** does afterCommit run?

**Answer:** no. The callback is only invoked after a successful commit.

### Scenario 3 — Sending email in BEFORE_COMMIT

**Question:** what if the transaction commit fails after the callback?

**Answer:** the sent email still remains out even though the database rolled back. Use AFTER_COMMIT for notifications confirming saved success.

### Scenario 4 — Event published outside a transaction

A service without @Transactional publishes OrderPlacedEvent; the listener uses AFTER_COMMIT and the default fallbackExecution = false.

**Question:** does the listener run?

**Answer:** there is no transaction to attach synchronization to, so the listener is not executed. Move publishing into the proper transaction, or change fallback only if business rules accept it.

### Scenario 5 — SMTP error in afterCommit

The database committed, but JavaMailSender throws an exception.

**Question:** does the order roll back?

**Answer:** no. The database already committed before the callback ran. Record the mail-sending error and retry under a separate policy.

### Scenario 6 — Callback writes status using repository.save

**Question:** is a save call in afterCommit guaranteed to commit?

**Answer:** do not assume so. Transaction resources may still be bound, yet the original transaction has already completed. If an independent write is needed, call a new-transaction service with REQUIRES_NEW.

### Scenario 7 — Event published in transaction A but handled on thread B

**Question:** does thread B automatically inherit transaction A?

**Answer:** no. Imperative transactions are bound to the current thread/context. If using async, pass only necessary data and open a new transaction in the worker when needed.

### Scenario 8 — Process stops after commit

The database committed, but the application stopped before the mail-sending callback ran.

**Question:** will the callback automatically rerun on the next startup?

**Answer:** no. In-memory callbacks are not a durable queue. If events must not be lost, write to an outbox in the same transaction and let a worker process it.

### Scenario 9 — SMTP received the mail, but worker has not marked SENT

**Question:** could a worker retry send a duplicate?

**Answer:** yes. SMTP and the database do not share an atomic commit. Idempotency is needed if the provider supports it, along with retry control and accepting possible duplicates when exactly-once cannot be guaranteed.

### Scenario 10 — Outer transaction rolls back, REQUIRES_NEW transaction committed

The callback was registered inside a REQUIRES_NEW transaction.

**Question:** can the callback run?

**Answer:** yes. The callback binds to the inner transaction and runs after that transaction commits, even if the outer transaction later rolls back. Ensure this is the intended business boundary.

## 19. Execution workflow

~~~text
1. Identify which database change the email depends on
       |
       v
2. Put that change inside an explicit transaction
       |
       v
3. Choose the post-commit mechanism
       |
       +--> Small callback
       |       -> registerSynchronization
       |       -> afterCommit()
       |
       +--> Business event
       |       -> publishEvent(...)
       |       -> @TransactionalEventListener(AFTER_COMMIT)
       |
       '--> Durability / retry requirement
               -> write outbox in same transaction
               -> worker processes after commit
       |
       v
4. Render email and call JavaMailSender
       |
       v
5. Record errors/attempts and observe delivery state
       |
       v
6. Test commit, rollback, SMTP failure, and process restart
~~~

**Publishing events after commit with transaction synchronization** ensures the application sends confirmation emails only after the database transaction has committed. For small tasks, you can register **TransactionSynchronization.afterCommit()** via **TransactionSynchronizationManager**. For business events, **@TransactionalEventListener(phase = AFTER_COMMIT)** decouples the publisher from mail handlers and lets multiple listeners react. Remember that post-commit callbacks cannot roll back the database, SMTP errors must be handled separately, imperative transaction contexts do not propagate automatically to other threads, and in-memory callbacks can be lost if the process stops. When emails must be retried and never lost, write an outbox event in the same transaction and process it with a durable worker.
