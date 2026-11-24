# Risk of Email Sent When the Transaction Rolls Back

In a Spring application, business logic may update the database and then send a confirmation email within the same method. This style looks natural, but **a database transaction cannot recall an email that an SMTP server has already accepted**.

Consider an order being confirmed:

1. The application opens a transaction.
2. It updates the order to CONFIRMED.
3. It sends a confirmation notification email.
4. Another database operation fails, or an error occurs at commit time.
5. The database rolls back, yet the email has already left the application.

The recipient may receive a notification saying "Your order has been confirmed" while the database still records the order in its previous state. This is an inconsistency between **business state in the database** and an **external side effect**.

Spring manages transactions for transaction-participating resources, typically databases. SMTP is an independent system. A call to JavaMailSender.send(...) does not automatically join a database transaction and has no mechanism to roll back an email when the transaction fails.

A common approach is to **issue the send command only after the business transaction commits successfully**. For notifications that must not be lost if the application stops abruptly, store the send intent in the same transaction using a **transactional outbox**, and have a worker send it after commit. Whichever approach you use, you must clearly account for duplicate sends, retries, and the actual state of the message.

## 1. A database transaction does not include SMTP

A database transaction can group multiple changes into one atomic unit:

~~~text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO order_history (...)
  UPDATE inventory (...)
COMMIT
~~~

If one operation fails before commit, the database can roll back the changes belonging to that transaction.

Sending email, on the other hand, is an external side effect:

~~~text
Application
    |
    +----> Database transaction
    |
    +----> SMTP server
~~~

The database transaction manager cannot ask the SMTP server to delete an accepted message just because the database transaction rolled back. SMTP does not participate in the same local transaction the way a JDBC connection does.

Example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    mailService.sendConfirmation(order);
}
~~~

This method has two types of operations:

- **Database work:** reading and updating the order.
- **External side effect:** sending email over SMTP.

If SMTP accepts the email and the database transaction then fails at commit time, the email cannot be rolled back along with the database.

### 1.1. Commit occurs after the method body

In Spring's typical proxy-based transaction model, the flow can be understood as follows:

~~~text
Caller
  |
  v
Spring transaction proxy
  |
  +-- Begin transaction
  |
  +-- Invoke method body
  |     |
  |     +-- Update database
  |     +-- Call JavaMailSender.send()
  |
  +-- Method returns
  |
  +-- Commit transaction
        |
        +-- Success
        |
        +-- Failure -> rollback if possible
~~~

The key point: when code inside the method calls send, the database transaction has usually not committed yet. Reaching the last line of the method does not mean commit has succeeded; the transaction interceptor still has to complete the commit after the method returns.

Therefore, sending an email at the end of a transactional method can still send before commit.

### 1.2. An example of an inaccurate status notification

Suppose the order is currently in PENDING status:

~~~text
Before transaction:
  orders.status = PENDING

During transaction:
  orders.status = CONFIRMED
  SMTP accepts email "Order confirmed"

At commit:
  Database detects an error and rolls back

After transaction:
  orders.status = PENDING
  Confirmation email may still reach the recipient
~~~

The recipient sees information that differs from the actual state. They might proceed to pay, contact support, or act on an incorrect notification.

For emails such as payment confirmations, reservations, access grants, refunds, or password changes, this inconsistency can cause significant business consequences.

## 2. Points at which failures can occur

It is not only the case where a SQL statement throws an exception. A transaction can fail at several points.

| Point in time | What can happen | Can an already-sent email be recalled? |
| --- | --- | --- |
| Before sending | Validation or database update fails | No email yet |
| During sending | SMTP timeout or rejection | Outcome may be failure or indeterminate |
| SMTP accepted, before commit | A subsequent statement fails | No |
| During commit | Constraint, deadlock, optimistic locking, or connection error | No |
| After commit | Listener or worker sending email encounters an error | Database has already committed |
| SMTP accepted, worker crashes before recording SENT | Worker may resend | No; risk of duplicate send |

### 2.1. Failure after SMTP has already accepted

A typical scenario:

~~~text
T0  Transaction begins
T1  Update order
T2  SMTP server accepts message
T3  A database statement fails
T4  Transaction rolls back
T5  Recipient may still receive the email
~~~

This is the hardest case to handle in code that sends email directly inside a transaction. Once T2 occurs, the side effect is already beyond the database's control.

### 2.2. Commit can fail even if the method body throws no exception

Some errors are only detected when the database performs the commit, such as deferred constraints checked at commit time, connection errors, or transaction conflicts. The code inside the method may run to completion, yet the interceptor still fails to commit.

Therefore, do not infer that "calling send on the last line" means the transaction will definitely commit.

### 2.3. An SMTP timeout does not always mean the server did not receive the email

A connection can drop after the SMTP server has received the data but before the application receives the final response. The application sees a timeout, yet the actual outcome may be indeterminate.

If you retry immediately, the message may be accepted a second time. This is a source of duplicates independent of database rollbacks.

### 2.4. SMTP acceptance does not mean the recipient read the message

Distinguish these milestones:

- The application called send.
- The SMTP server accepted the message.
- The provider relayed the message.
- The message arrived at the mailbox.
- The email client displayed the message.
- The recipient read the content.

A successful send return from JavaMailSender usually only indicates that transport completed according to the acknowledgment level provided by the SMTP server. It does not prove the recipient read the message.

## 3. Why sending email inside @Transactional is risky

### 3.1. Database rollback does not roll back side effects

This is the core issue. The transaction manager can roll back the database, but there is no equivalent operation to recall an email already accepted by an SMTP server.

### 3.2. Transactions are prolonged by network I/O

SMTP can be slow due to DNS, connection setup, TLS handshake, authentication, rate limiting, or server response time. While waiting, the database transaction may keep holding connections, locks, and resources.

For example, a single email takes 3 seconds to send. If one request generates multiple emails sequentially, the transaction can stay open significantly longer than the necessary data updates.

### 3.3. Email send failures can needlessly roll back business operations

If send throws an exception and that exception is of a type that triggers transaction rollback, a valid order may be rolled back simply because SMTP is temporarily unavailable.

Sometimes email is a mandatory precondition of a workflow. However, in most systems, confirming an order and delivering a notification over SMTP are two tasks with different recovery strategies. That relationship should be modeled explicitly rather than letting an SMTP exception accidentally decide database state.

### 3.4. Retrying the entire transaction can repeat side effects

If the application retries the transactional method when SMTP fails, the first attempt might have sent the email while the transaction rolled back. The next attempt sends another email.

If the method also creates records, issues codes, or calls other external systems, retrying the whole transaction can repeat multiple side effects.

### 3.5. Business outcomes become confusing

A request can return an error to the client because the transaction rolled back even though the email was sent. The user retries and receives another email. Support also struggles to explain why the database has no confirmation record while the mailbox has the message.

## 4. Do not send directly before commit if the email confirms saved changes

A simple principle:

**If an email asserts that a business change has succeeded, sending should only start after the transaction recording that change commits successfully.**

There are several ways to structure this:

1. Call the transactional service from an orchestrating service, and send only after the service returns successfully.
2. Publish a Spring application event and handle it with **@TransactionalEventListener(AFTER_COMMIT)**.
3. Combine an after-commit listener with **@Async** when you do not want the request to wait for sending.
4. Use a **transactional outbox** when the send intent must be persisted durably and be recoverable after a process stop.

Each approach addresses a different part of the requirement. AFTER_COMMIT handles timing; @Async separates execution threads; an outbox persists the send intent in the same database transaction.

## 5. Simple approach: call the transactional service first, then send

If the email can be sent synchronously after the transaction finishes and a durable queue is not needed, separate the business bean and the orchestration bean.

Order update service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderMailData confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );
    }
}
~~~

DTO:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount
) {}
~~~

Orchestration service:

~~~java
@Service
public class OrderConfirmationFacade {

    private final OrderService orderService;
    private final OrderMailService mailService;

    public OrderConfirmationFacade(
            OrderService orderService,
            OrderMailService mailService
    ) {
        this.orderService = orderService;
        this.mailService = mailService;
    }

    public void confirmAndNotify(UUID orderId) {
        OrderMailData snapshot = orderService.confirm(orderId);

        // The transaction in OrderService has already committed successfully
        // before the proxy call returns here.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

When the caller invokes **OrderService** through the Spring proxy, the transaction begins, updates are executed, and it commits before the transactional call returns normally. If the commit fails, the facade does not proceed to sendConfirmation.

### 5.1. Why use two beans?

Spring typically manages @Transactional through proxies. If a method calls another transactional method on the same object via a self-invocation, that call may bypass the proxy; the transaction annotation may not be applied as expected.

Separating the transactional service and the facade into two beans makes the call boundary explicit.

### 5.2. Why return a DTO instead of an entity?

After the transaction ends, the entity may be detached from the persistence context. If the mail service accesses lazy relationships, a LazyInitializationException or unintended queries can occur.

A DTO snapshot contains only the data needed for the email:

- Resolved recipient.
- Recipient name.
- Order number.
- Amount.
- Status or timestamp to notify.

The renderer and mail service do not need to know about JPA entities or lazy relations.

### 5.3. Limitations of this approach

The sequential call approach has the advantage of simplicity, but it still leaves a gap:

~~~text
1. Database commit succeeds.
2. Process stops before the facade calls mailService.
3. No email is sent.
~~~

It prevents an email from being sent before a failed commit, but does not durably persist the send intent. If the email can be retried manually or is not critical, this may be acceptable. If losing a notification is unacceptable, a more durable mechanism is needed.

## 6. Using @TransactionalEventListener(AFTER_COMMIT)

Spring provides **@TransactionalEventListener** to handle application events bound to a transaction phase.

Event:

~~~java
public record OrderConfirmedEvent(
        OrderMailData mailData
) {}
~~~

Business service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher
    ) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderMailData snapshot = new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );

        publisher.publishEvent(
                new OrderConfirmedEvent(snapshot)
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Flow:

~~~text
@Transactional confirm()
       |
       +-- Update database
       +-- Publish OrderConfirmedEvent
       |
       v
Commit transaction
       |
       +-- Commit succeeds
       |       |
       |       v
       |   AFTER_COMMIT listener
       |       |
       |       v
       |   Send email
       |
       +-- Rollback
               |
               v
           AFTER_COMMIT does not run
~~~

If the transaction rolls back, the AFTER_COMMIT listener is not invoked. Only if the commit succeeds does the listener process the email.

### 6.1. Why is publishing an event inside the transaction still safer than sending directly?

Publishing an event here only registers an event for a transaction-bound listener. The AFTER_COMMIT listener is called after the transaction commits successfully. When the transaction rolls back, the listener does not process the event in this phase.

The critical difference is that **publishing an event is not sending an email**. Sending only happens inside the listener after commit.

### 6.2. Other phases of TransactionalEventListener

Spring supports these phases:

| Phase | Timing |
| --- | --- |
| **BEFORE_COMMIT** | Before the transaction commits |
| **AFTER_COMMIT** | After commit succeeds |
| **AFTER_ROLLBACK** | After rollback |
| **AFTER_COMPLETION** | After the transaction completes, whether commit or rollback |

For emails confirming successfully saved changes, **AFTER_COMMIT** is usually the appropriate choice.

**BEFORE_COMMIT** does not solve the risk discussed here. The listener still runs before commit; the transaction can still fail after the email has been sent.

### 6.3. Without a transaction, the listener may not run by default

A transactional event listener by default requires an active transaction at the time the event is published. If the event is published outside a transaction, the listener may not be invoked.

The **fallbackExecution = true** option allows the listener to run even without a transaction, but it must be used intentionally. If enabled, the listener can send emails even when the event is not tied to a business transaction.

Do not enable fallback just to mask a design bug where an event is published in the wrong place.

### 6.4. AFTER_COMMIT does not automatically make events durable

Standard Spring application events are dispatched in-process. A scenario can still occur:

~~~text
1. Database commit succeeds.
2. Process crashes immediately after commit.
3. Listener has not processed the event yet.
4. In-memory event is lost when the process stops.
5. Email is not sent.
~~~

AFTER_COMMIT guarantees when the listener is called within the transaction lifecycle; it does not persist the event to the database, create a durable queue, or automatically retry after a restart.

## 7. Combining AFTER_COMMIT with @Async

If you do not want the user's request to wait for SMTP, you can process the listener asynchronously.

Enable async:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-worker-");
        return executor;
    }
}
~~~

The values above are only examples. Configure them according to email volume, SMTP provider limits, and application resources.

Listener:

~~~java
@Component
public class AsyncOrderMailListener {

    private final OrderMailService mailService;

    public AsyncOrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Flow:

~~~text
Request
   |
   v
@Transactional service
   |
   +-- Update database
   +-- Publish event
   +-- Commit
   |
   v
AFTER_COMMIT listener
   |
   v
Submit task to executor
   |
   v
Worker thread
   |
   +-- Render template
   +-- Build MimeMessage
   +-- Send SMTP
   |
   v
End
~~~

### 7.1. What does @Async solve?

- Decouples template rendering and sending time from the request-handling thread.
- Avoids holding the business transaction open while waiting on SMTP.
- Allows bounding concurrent send tasks via the executor.
- Errors in the async task cannot roll back the already-committed transaction.

### 7.2. @Async does not automatically retry or guarantee against task loss

An in-process executor has a bounded queue. If the queue is full, tasks may be rejected according to the executor's policy. If the application stops abruptly, queued or running tasks may not complete.

Therefore:

- **AFTER_COMMIT** handles timing.
- **@Async** handles execution style.
- **Transactional outbox** handles durable persistence of the send intent.

These three mechanisms do not replace one another.

### 7.3. Handling exceptions in an async listener

An async method returning void cannot propagate exceptions back to a request that has already ended. Errors must be recorded in the listener or via an appropriate async error handler:

~~~java
@Async("mailExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    try {
        mailService.sendConfirmation(event.mailData());
    } catch (Exception ex) {
        log.error(
                "Cannot send confirmation for order {}",
                event.mailData().orderNumber(),
                ex
        );
        // Record failure status or hand off to a retry mechanism.
    }
}
~~~

This illustrates exception handling. Logs must avoid recording personal data, attachment contents, or credentials. For important emails, simply logging the error is not enough; durable status is needed to continue processing.

### 7.4. Do not pass JPA entities to an async worker

The worker runs on a different thread and does not inherit the caller transaction's persistence context. Pass a DTO snapshot or a serializable event payload.

If you pass only the order ID, the worker must open its own transaction to read the data. In that case, you must decide whether the email needs a snapshot at confirmation time or the latest state when the worker runs.

## 8. Transactional outbox: storing send intent in the same transaction

When losing the send intent after database commit is unacceptable, a **transactional outbox** is a common solution.

Instead of only publishing an in-memory event, the application writes an outbox record in the same transaction as the business change.

Example:

~~~text
orders
  id = 1001
  status = CONFIRMED

mail_outbox
  id = 9001
  event_type = ORDER_CONFIRMED
  payload = { ...mail snapshot... }
  status = PENDING
~~~

Both changes are committed atomically:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = 1001;

INSERT INTO mail_outbox (
    id,
    event_type,
    payload,
    status,
    created_at
)
VALUES (
    '9001',
    'ORDER_CONFIRMED',
    '{...}',
    'PENDING',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

If the transaction rolls back, both the order change and the outbox record roll back. If the commit succeeds, a worker can find the PENDING record after the application restarts.

### 8.1. Why does an outbox solve the post-commit gap?

Comparison:

~~~text
AFTER_COMMIT event in memory:
  Database commit
       |
       +-- Process crash
       |
       +-- Event may be lost
~~~

~~~text
Transactional outbox:
  Database transaction
       |
       +-- Update business data
       +-- Insert outbox row
       |
       v
     COMMIT
       |
       v
  Outbox row remains in the database
       |
       v
  Worker processes when ready
~~~

The send intent is saved in the same transaction. The worker does not have to rely on an event that exists only in the process's memory.

### 8.2. Illustrative outbox schema

~~~sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

A real-world schema may add:

- Recipient or reference to the recipient.
- Template key and template version.
- Locale.
- Correlation ID.
- Lease owner and lease expiry.
- Last processing timestamp.
- Categorized error type.
- Maximum retry attempts.

If the payload contains personal data, you need read-access policies, encryption at rest if appropriate, retention periods, and data deletion policies.

### 8.3. Writing to the outbox in a transactional service

Example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    OrderMailData snapshot = new OrderMailData(
            order.getCustomerEmail(),
            order.getCustomerName(),
            order.getNumber(),
            order.getTotal().toPlainString()
    );

    outboxRepository.save(
            MailOutboxEvent.pending(
                    UUID.randomUUID(),
                    "ORDER_CONFIRMED",
                    serialize(snapshot)
            )
    );
}
~~~

SMTP is not called inside this transaction. If the commit succeeds, both the order and the outbox row exist. If it rolls back, neither is committed.

### 8.4. Worker reading and sending

Pseudo-code:

~~~java
public void processPendingBatch() {
    List<MailOutboxEvent> events =
            outboxRepository.claimPendingBatch(50);

    for (MailOutboxEvent event : events) {
        try {
            OrderMailData data = deserialize(event.payload());

            mailService.sendConfirmation(data);

            outboxRepository.markSent(event.id());
        } catch (Exception ex) {
            outboxRepository.scheduleRetry(
                    event.id(),
                    calculateNextAttempt(event.attempts()),
                    classify(ex)
            );
        }
    }
}
~~~

This is a conceptual flow, not a complete implementation. In a real application, **claimPendingBatch** needs a locking or lease mechanism so multiple workers do not process the same event concurrently. Claiming and updating status must be managed with appropriate transactions.

### 8.5. Do not hold a database transaction while sending over SMTP

A worker can:

1. Open a short transaction to claim events and record a lease.
2. Commit the claim.
3. Read the claimed payload.
4. Render and send over SMTP outside the claim transaction.
5. Open another transaction to mark the outcome.

This avoids holding database locks during network I/O. If the worker dies between sending and updating the status, the event can be reclaimed after the lease expires; that is why idempotency and duplicate-send handling must be designed.

## 9. An outbox does not guarantee exactly-once email

A transactional outbox durably stores the send intent and allows workers to retry. However, SMTP does not participate in the same database transaction, so a gap still exists:

~~~text
1. Worker picks up a PENDING event.
2. SMTP server accepts the email.
3. Worker crashes before marking the event SENT.
4. Lease expires.
5. Another worker picks up the event again.
6. The email is sent a second time.
~~~

The result can be that the recipient receives two emails.

This is an important limitation: an outbox typically provides **at-least-once processing** for the send task, rather than guaranteeing an email appears exactly once in a mailbox.

### 9.1. Stable event IDs

Each send intent should have a stable ID. This ID is used in:

- The outbox record.
- Logs.
- Correlation IDs.
- Retry history.
- Reconciliation metadata.

Do not generate a new ID on every retry of the same send intent. A stable ID helps identify processing attempts belonging to the same task.

### 9.2. Message-ID is not an idempotency guarantee

An email has a Message-ID header. Using a stable Message-ID can be useful for lookup or reconciliation, but it does not force every SMTP server or email client to deduplicate messages.

If an SMTP provider supports an idempotency key via its proprietary API, it can be used according to the provider's contract. Plain SMTP does not provide a general-purpose exactly-once mechanism.

### 9.3. Designing content to tolerate duplicate sends

For confirmation emails, you can reduce the impact of duplicate sends by:

- Using a stable order number or event ID.
- Avoiding generating a new confirmation code on every retry.
- Not making the recipient interpret each repeated email as a new transaction.
- Storing send status and history to assist support handling.
- Distinguishing a retry of the same event from a new business event.

For emails with one-time links or verification codes, special care is required: retries must not issue inconsistent tokens or accidentally invalidate an active token.

## 10. Data snapshot or storing only an ID in the outbox?

The worker can receive the full email data or receive only an ID to reload the data.

| Storage approach | Advantages | Limitations |
| --- | --- | --- |
| **Snapshot DTO** | Content reflects the business event moment; no lazy entities needed | Larger payload and may contain personal data |
| **Store business ID only** | Small payload; worker reads the latest state | Data may change or be deleted before the worker runs |
| **Snapshot + template version** | Can reproduce content per the chosen version | Requires template version and retention management |

### 10.1. Snapshots suit event-confirmation emails

For example, an order is confirmed at 10:00 with a total of 500,000 VND. At 10:05, customer or order data changes.

If the email describes the confirmation event at 10:00, a snapshot preserves the amount, name, and details at that time.

### 10.2. Reloading suits cases needing the latest state

For reminder or digest emails, data at the time the worker runs may be needed. In that case, the worker reloads by ID, but you must clearly define how the task is handled if the record no longer exists or its status has changed.

### 10.3. Do not store JPA entities in the payload

Do not directly serialize an entire JPA entity into an event/outbox. Entities can contain circular references, lazy proxies, and unnecessary data. Create a DTO with a clear schema containing only the information permitted for the email.

## 11. Case where email sends successfully but database rolls back due to an exception

You need to understand Spring's rollback rules.

By default, in common transaction configurations, Spring rolls back when a transactional method exits via a **RuntimeException** or **Error**. Checked exceptions do not automatically trigger rollback under the same default rule unless an appropriate rollback rule is configured.

Example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) throws MessagingException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    mailService.sendConfirmation(order);
}
~~~

If **MessagingException** is a checked exception and is thrown, the transaction does not necessarily roll back by default. If the exception is wrapped in a RuntimeException or has a matching rollbackFor, the transaction may roll back.

This affects the **email send failure** scenario. However, the risk of an email being sent followed by a transaction rollback still exists if a runtime error or commit error occurs after SMTP has already accepted the message.

### 11.1. Do not use rollback rules to solve side effects

You can configure:

~~~java
@Transactional(rollbackFor = Exception.class)
~~~

This changes the rollback rule for exceptions, but does not make SMTP part of the database transaction. If the email has already been sent and an exception causes a rollback, the email still cannot be recalled.

Rollback rules only decide whether the database transaction rolls back; they do not create the ability to roll back external side effects.

### 11.2. Catching SMTP exceptions and continuing does not solve lost notifications

Example:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    log.warn("Email failed", ex);
}
~~~

This may allow the business transaction to continue, but without saving status or creating a retry task, the failed email may be permanently lost.

If the email is optional, recording an error status may suffice. If the email is a business obligation, the send intent must be persisted durably.

## 12. Transaction synchronization and TransactionSynchronizationManager

Besides **@TransactionalEventListener**, Spring has a transaction synchronization API to register callbacks along the transaction lifecycle.

Illustrative example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    OrderMailData snapshot = toMailData(order);

    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    mailService.sendConfirmation(snapshot);
                }
            }
    );
}
~~~

The **afterCommit()** callback is invoked after the transaction commits successfully. If the transaction rolls back, the post-commit callback is not executed.

This allows registering an action directly against the transaction, though it is usually less expressive semantically than an event listener. You must ensure transaction synchronization is active before registering; otherwise, the code may need to handle the no-transaction case.

### 12.1. Same limitations as AFTER_COMMIT events

Transaction synchronization callbacks still live in-process. If the process crashes after commit before the callback runs, the email may not be sent. It does not replace an outbox when durability is required.

### 12.2. Do not call SMTP inside beforeCommit

Registering a **beforeCommit()** callback and sending email still creates the same risk: the commit can fail after the callback. If the goal is not to send before the transaction succeeds, use afterCommit or a worker reading an outbox after commit.

## 13. Be careful with database operations inside an AFTER_COMMIT listener

After a transaction commits, Spring may still keep certain transaction resources bound to the thread while completion callbacks run. Spring documentation notes that data access operations in the AFTER_COMMIT phase may still see those resources, while new changes are not committed into the already-completed transaction.

If a listener needs to write a separate status record after commit, intentionally use a new transaction, such as **Propagation.REQUIRES_NEW** on a separate bean.

Example:

~~~java
@Service
public class MailStatusService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(UUID eventId, String reason) {
        // Save error status in a new transaction.
    }
}
~~~

The method must be invoked through a Spring proxy for propagation to take effect in the standard proxy model. Do not use REQUIRES_NEW mechanically; it is only needed when the listener actually writes data after the original transaction and wants an independent commit.

With an outbox, the worker typically manages the claim transaction and status-update transaction separately, making this boundary clearer.

## 14. Distinguishing business errors from email-sending errors

Not every email carries the same level of criticality.

| Email type | Example | Potentially suitable handling |
| --- | --- | --- |
| Convenience notification | New article alert | Can send best-effort after commit |
| Transactional confirmation email | Order or payment confirmation | Needs persisted and tracked send intent |
| Security email | Login alert, password change | Needs tight control over timing, content, and retries |
| Document-bearing email | Invoice or receipt | Needs snapshot/version and send history |
| Bulk newsletter | Newsletter | Queue, rate limiting, and unsubscribe handling |

For convenience emails, an AFTER_COMMIT listener may be sufficient. For transactional confirmations or documents, a transactional outbox is usually more suitable because it can recover after an application stop.

### 14.1. Emails should not unwittingly dictate business state in reverse

For example, temporary SMTP downtime does not necessarily mean an order is unconfirmed. The order can be committed while the notification status is PENDING.

If the business genuinely requires completing only with confirmation from an external system, model that workflow explicitly with states and coordination steps. Do not rely on calling SMTP inside a transaction to simulate an atomic distributed transaction.

## 15. Retries need state and backoff

If sending fails, the worker can retry. Do not retry continuously in a tight loop, as it can overload the SMTP provider or generate many duplicate messages.

A state model:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted --> SENT_TO_PROVIDER
   |
   +-- temporary error --> RETRY_WAIT
   |                         |
   |                         v
   |                      PROCESSING
   |
   +-- permanent error --> FAILED
~~~

Exponential backoff can be used:

~~~text
Attempt 1: short wait
Attempt 2: longer wait
Attempt 3: even longer wait
...
Limit reached: transition to FAILED or dead-letter
~~~

Jitter should be added so multiple workers do not retry simultaneously at the exact same instant. Specific timings depend on error type, provider policies, and the email's SLA.

### 15.1. Classifying errors before retrying

| Error category | Example | Action |
| --- | --- | --- |
| Temporary | SMTP 4xx, retryable timeout | Backoff and retry up to limit |
| Permanent | Invalid recipient, hard policy rejection | Mark failed, do not retry indefinitely |
| Indeterminate | Connection lost after SMTP may have received DATA | Handle cautiously due to possible duplicate send |
| Message construction error | Broken template, missing attachment | Fix data or template before retrying |

Not every MailException has the same nature. Inspect the root cause and SMTP response when available.

### 15.2. Do not mark SENT before sending

If the worker writes SENT before calling SMTP and the process crashes, the email may never be sent while the database records it as sent.

If it sends first and writes SENT afterward, a crash in between can cause duplicate sends.

No ordering of database writes and SMTP calls completely eliminates this gap when the two systems do not share a distributed transaction. Choose appropriate semantics, store explicit states, and design duplicate handling.

## 16. Idempotency at the business layer

**Idempotency** means that processing the same intent repeatedly does not produce unintended new business effects.

For example, an order confirmation event has a stable ID:

~~~text
eventId = 8d...
type = ORDER_CONFIRMED
orderId = 1001
~~~

The worker can store the event ID in the outbox and processing history. If it receives the same event again, it can check how far the task has been processed.

However, if SMTP has accepted the email while the worker has not yet recorded it, the database cannot know for sure whether the server received it. Thus, database-level idempotency helps control claiming and event processing, but does not by itself turn SMTP into exactly-once.

### 16.1. Generating a unique event per state transition

Do not emit an ORDER_CONFIRMED event every time a retried request runs if the order was already confirmed earlier. You can use valid state transitions or a unique constraint on an event key to prevent creating multiple outbox rows for the same state transition.

Example business key:

~~~text
ORDER_CONFIRMED:order-1001:version-3
~~~

The key must accurately reflect a single state transition. If an order can be re-confirmed under a new workflow, a different version or event ID is needed.

### 16.2. Idempotency does not mean ignoring every email with identical content

Two emails with the same subject and body can still be two valid distinct events. Idempotency identifiers should be tied to **business intent**, not merely a hash of the email content.

## 17. Options that do not solve the problem

### 17.1. Placing the send call on the last line of the method

Even if send is the final statement, the transaction still commits after the method body ends. The commit can fail.

### 17.2. Catching exceptions and rolling back manually

Database rollback does not recall an email already accepted by SMTP. Nor should you try sending a second "correction" email for every technical exception; determine the actual business state first.

### 17.3. Using @Async directly inside the transaction

If you merely annotate a mail-sending method with @Async and call it inside a transaction, the task can start before the transaction commits. The worker might send the email while the transaction later rolls back.

**@Async does not automatically wait for transaction commit.** If using async for post-commit notifications, combine it with AFTER_COMMIT or have a worker read from an outbox.

### 17.4. Using @Transactional(propagation = REQUIRES_NEW) for the mail service

REQUIRES_NEW creates or uses a separate database transaction for the method's database operations. It does not make SMTP participate in that transaction and cannot roll back the email.

Putting the mail service in REQUIRES_NEW does not solve the case where the email was sent while the outer business transaction rolled back. The boundary that matters is when sending occurs relative to the business commit.

### 17.5. Using @TransactionalEventListener(BEFORE_COMMIT)

BEFORE_COMMIT still runs before the database confirms the commit. If the listener sends an email, a subsequent commit failure can still leave the email reporting an unsaved change.

### 17.6. Assuming SMTP is exactly-once

SMTP does not provide a shared atomic transaction with your application's database. Design to tolerate retries and indeterminate outcomes.

## 18. Testing rollback risks and handling strategies

Important test scenarios:

| Scenario | Expected outcome |
| --- | --- |
| Transaction commits successfully | Email is permitted to be processed after commit |
| Transaction rolls back before commit | AFTER_COMMIT listener does not send email |
| SMTP fails after commit | Database retains committed business state; send error is recorded |
| Process stops after commit before in-memory listener | Event may be lost if not using an outbox |
| Outbox row committed, worker stops | Row remains for worker to process after restart |
| SMTP accepts then worker crashes before marking SENT | May retry and send duplicate; reconciliation needed |
| Worker retry hits permanent failure | Event transitions to FAILED/dead-letter per policy |
| Two workers run concurrently | Claim/lease mechanism prevents concurrent processing of the same event |

### 18.1. Testing AFTER_COMMIT

An integration test can:

1. Start a transaction.
2. Perform business updates and publish the event.
3. Commit.
4. Confirm the listener was invoked.

Another test rolls back the transaction and confirms the AFTER_COMMIT listener was not invoked.

Use appropriate test transactions; if the test framework automatically rolls back the transaction after the test, the AFTER_COMMIT phase may not run as in a real committed transaction. Explicitly commit in test scenarios that need to verify the listener.

### 18.2. Testing the outbox

You can verify:

- Business updates and outbox insert commit together.
- Rollback leaves neither change present.
- Worker claims only PENDING state properly.
- Retries update attempts and next_attempt_at.
- Worker restart resumes processing remaining pending events.
- Events already marked SENT are not claimed as new tasks.

### 18.3. Using an SMTP capture server

An SMTP capture server in the test environment lets you observe messages without sending to real users. You can verify message count, recipients, subject, body, and attachments.

To test the duplicate window, you can simulate a worker crash after SMTP accepts the message but before updating the outbox. This test clearly demonstrates why an outbox does not guarantee exactly-once delivery.

## 19. Recommended architecture for transactional emails

For critical confirmation emails, a flow can be structured as:

~~~text
HTTP request / command
          |
          v
OrderApplicationService
    @Transactional
          |
          +-- Validate command
          +-- Update order
          +-- Create immutable mail snapshot
          +-- Insert mail_outbox row
          |
          v
        COMMIT
          |
          v
Outbox polling worker
          |
          +-- Claim pending event
          +-- Resolve template and locale
          +-- Render plain text / HTML
          +-- Build MimeMessage
          +-- JavaMailSender.send(...)
          +-- Update status or retry schedule
          |
          v
       SMTP provider
~~~

Responsibilities:

- **OrderApplicationService:** manages business changes.
- **Mail snapshot:** preserves data at the time of the event.
- **Outbox repository:** stores send intent and status.
- **Worker:** claims, retries, and orchestrates sending.
- **Template renderer:** generates subject and body.
- **Mail delivery service:** builds MimeMessage and invokes JavaMailSender.
- **Monitoring:** tracks pending, retry, failed counts, and processing latency.

For small applications, you can start with a post-commit service call or an AFTER_COMMIT listener. As durability requirements grow, an outbox lets workers resume processing after application restarts.

## 20. Choosing a solution based on email criticality

| Requirement | Potentially suitable solution | Limitation to remember |
| --- | --- | --- |
| Convenience email, occasional loss acceptable | Send after transactional service returns | Process may stop before sending |
| Only need not to send before commit | AFTER_COMMIT listener | In-memory event is not durable |
| Do not want request waiting on SMTP | AFTER_COMMIT + @Async | Tasks may be lost if process stops |
| Need task recovery after restart | Transactional outbox | Possible duplicate sends in failure window |
| Need retries and per-attempt tracking | Outbox/queue with status | Requires lease, backoff, and dead-letter management |
| Content must reflect data at transaction time | Snapshot DTO inside transaction | Payload must be protected and retention managed |
| Email can use latest data | Worker reloads by ID | Content may change after event time |

Not every email needs an outbox. However, if an email is an important part of the business workflow and losing the send intent is unacceptable, in-memory events alone are usually insufficient.

## 21. Frequently asked questions

**1. Why is an email still sent when the transaction rolls back?**

Because SMTP is an external system and does not participate in the database transaction. Once the SMTP server has accepted the message, a database rollback cannot recall that message.

**2. Is placing send at the end of a @Transactional method safe?**

Not guaranteed. The transaction typically commits after the method body returns through the Spring proxy. Commit can still fail after the send call.

**3. Does @TransactionalEventListener(AFTER_COMMIT) prevent sending before commit?**

Yes, for events published inside a transaction with a listener operating in the AFTER_COMMIT phase. If the transaction rolls back, the listener does not run in that phase.

**4. Does AFTER_COMMIT guarantee the email is always sent?**

No. The process can stop after commit before the listener handles it. In-memory listeners do not durably persist events.

**5. Does @Async automatically wait for transaction commit?**

No. @Async only offloads work to an executor. To run after commit, combine it with the AFTER_COMMIT phase or use a worker reading from an outbox.

**6. What does a transactional outbox solve?**

It saves a send-intent record in the same transaction as the business changes. If the commit succeeds, a worker can resume processing after the application restarts.

**7. Does an outbox guarantee sending exactly one email?**

No. A worker can crash after SMTP accepts the email but before recording the SENT status. Retries can cause duplicate sends.

**8. Can an already-sent email be rolled back?**

An email cannot be recalled from an SMTP server or mailbox via database rollback. If information must be corrected, the application can send a new corrective notice after confirming the actual business state.

**9. Does REQUIRES_NEW solve the problem?**

No. REQUIRES_NEW creates a separate database transaction for database operations. SMTP remains an external side effect and cannot be rolled back with that transaction.

**10. If SMTP fails, should the order roll back?**

It depends on the business logic. Usually order status and notification delivery are managed separately; the email can remain PENDING or FAILED for retry. If email is genuinely a workflow precondition, model that step explicitly rather than relying accidentally on an SMTP exception.

**11. Should a JPA entity be passed to an AFTER_COMMIT listener?**

Pass a DTO snapshot or a serializable event payload. Entities can become detached and lazy relationships may no longer be accessible.

**12. Does an SMTP timeout guarantee the email was not sent?**

No. The server may have accepted the message while the response never reached the application. Retrying can create duplicates.

**13. Can BEFORE_COMMIT be used to send email?**

Unsuitable when the email asserts the transaction succeeded. Commit can still fail after the callback.

**14. How can duplicate emails be reduced?**

Use stable event IDs, control event creation, outbox state, leases, and business-layer idempotency. If the provider supports an idempotency key, use it per the provider's contract. Plain SMTP does not guarantee exactly-once.

## 22. Remembering the risk of email sent when a transaction rolls back

**A database transaction can only roll back changes belonging to resources it manages.** Email sent via SMTP is an external side effect. If the SMTP server has already accepted the message before the transaction commit fails, the email can still reach the recipient even though the database reverts to its previous state.

Do not send success-confirmation emails directly inside a business transaction if the message is only valid after commit. You can call the mail service after the transactional service returns, use **@TransactionalEventListener(AFTER_COMMIT)**, or combine AFTER_COMMIT with **@Async** when you need to decouple sending time from the request. These approaches handle timing and execution, yet in-memory events can still be lost if the process stops after commit.

For critical emails, store the send intent in the same transaction using a **transactional outbox**, and have a worker render and send after commit. An outbox enables task recovery after restarts and supports retries, but does not guarantee exactly-once because a worker can stop after SMTP accepts the message and before recording SENT. You need stable event IDs, explicit states, backoff, duplicate handling, and failure monitoring.

Separate three outcomes: **business state committed**, **SMTP accepted the message**, and **recipient received or read the email**. These are distinct milestones. Designing proper transaction boundaries ensures notifications reflect accurate business state and helps the system recover predictably when SMTP or the process encounters failures.
