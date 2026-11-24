# Sending Email Directly Inside a Business Transaction

In a Spring application, operations such as confirming an order, paying an invoice, or creating an account typically run inside a **database transaction**. The application updates data and may then need to send a notification email to the user.

An easy-to-write approach is calling `JavaMailSender.send(...)` directly inside a `@Transactional` method. However, sending an email over SMTP is an **effect outside the database**. Spring's transaction manager can commit or roll back data in the database, but it cannot recall an email that an SMTP server has already accepted.

Therefore, it is important to understand when the email is sent and what the result means:

- If you send the email **before the database commits**, the recipient may receive a notification for a transaction that is later rolled back.
- If you wait until **after commit** to send, the data is already saved, but the process may stop before the email is sent.
- If you use a **transactional outbox**, the business data and the email send request are written in the same database transaction; a worker sends the email afterward and can retry.

This lesson explains how sending directly inside a transaction works, the risks of that approach, how to use post-commit events, and when to use an outbox.

## 1. The database transaction and SMTP are two independent systems

Suppose a user confirms an order. The application needs to:

1. Transition the order status to `CONFIRMED`.
2. Save the confirmation timestamp.
3. Send a confirmation email to the customer.

A database transaction can guarantee that related SQL operations are committed or rolled back together. The SMTP server is an external system and does not participate in that transaction.

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant D as Database
    participant S as SMTP Server
    A->>D: BEGIN
    A->>D: UPDATE order = CONFIRMED
    A->>S: SMTP send confirmation
    S-->>A: Accepted
    A->>D: COMMIT
~~~

If the commit succeeds, the example appears to work properly. However, if the commit step fails after SMTP has already accepted the message, the email has gone out while the order data is not saved.

This happens because:

- **Database rollback** only undoes changes managed by the transaction manager/database.
- **SMTP submission** is not part of the database transaction.
- An email already accepted by an external server cannot be recalled with `ROLLBACK`.

You should not treat an SMTP call like another SQL statement in the same transaction. The two operations have separate boundaries and confirmation mechanisms.

## 2. Calling send directly inside a @Transactional method

A common example:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orderRepository,
            JavaMailSender mailSender) {
        this.orderRepository = orderRepository;
        this.mailSender = mailSender;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(order.getCustomerEmail());
        mail.setSubject(
                "Order " + order.getOrderNumber() + " has been confirmed");
        mail.setText(
                "Your order " + order.getOrderNumber()
                + " has been confirmed.");

        mailSender.send(mail);
    }
}
~~~

This code is easy to understand and may be suitable for a small demo. However, because `confirmOrder(...)` runs inside a transaction, `mailSender.send(mail)` is called **before the transaction commits**. Spring normally commits the transaction when the method invoked through the transaction proxy completes normally.

If sending the email succeeds but a subsequent database operation or the commit process fails, the customer may still receive a confirmation email for an order that is not confirmed in the database.

### 2.1. Scenario: send succeeds but database rolls back

~~~text
T1  BEGIN database transaction
T2  UPDATE order SET status = 'CONFIRMED'
T3  SMTP accepts the email and returns an accepted response
T4  A constraint/commit operation fails
T5  Database ROLLBACK

Result:
  Database: order is not confirmed
  Email: customer already received the confirmation notification
~~~

This creates an inconsistent state between the database and the external notification. When the customer clicks the link or calls support, the application may not find the state described in the email.

### 2.2. Scenario: send fails

If `mailSender.send(mail)` throws a `MailException` and the exception escapes the `@Transactional` method, Spring by default rolls back the transaction for runtime exceptions and `Error` (unless another rollback rule is configured).

This can produce the following behavior:

~~~text
T1  BEGIN
T2  UPDATE order = CONFIRMED
T3  SMTP reports an error
T4  MailException escapes the method
T5  Database ROLLBACK
~~~

Sometimes an application wants this behavior, but you must understand its meaning: **an email failure is causing the entire order confirmation business operation to fail**. This is a strong business decision and should not happen accidentally just because the sender was called inside a transaction.

If the code catches the exception and only logs it:

~~~java
try {
    mailSender.send(mail);
} catch (MailException ex) {
    log.warn("Could not send confirmation", ex);
}
~~~

then the method can continue and the transaction commits. The order is confirmed, but the email failed. This can be a reasonable choice if the email is a secondary task, but in that case the system must have a way to record and reprocess errors if the email is important.

### 2.3. SMTP outcomes can be indeterminate

A trickier situation:

1. The application transmits the message to the SMTP server.
2. The SMTP server accepts the message.
3. The connection drops before the client receives the final response.

The application may receive a timeout or exception even though the server already accepted the message. If the exception rolls back the database and the application then retries, the recipient may receive duplicate emails.

Therefore, a transport error does not always mean "the server definitely did not receive the email." An email-sending system must distinguish between definite failures and indeterminate outcomes when designing retries.

## 3. Sending email inside a transaction also prolongs transaction duration

SMTP involves network latency and depends on an external system. When calling the sender directly inside a transaction:

- the transaction must wait for the SMTP connection and response;
- the database connection may be held longer;
- row locks or other transaction resources may persist longer;
- throughput drops when SMTP is slow;
- an SMTP timeout can prolong or fail the business request.

For example, updating an order usually takes a few tens of milliseconds, whereas sending over SMTP can take several seconds when the server is slow. Under concurrent requests, prolonged transactions can increase the number of connections in use and cause lock contention.

~~~text
Transaction duration

Database update only:
| DB work |

SMTP send inside transaction:
| DB work |--------- SMTP wait ---------|

                         ^ connection/locks may still be held
~~~

This is a practical reason to separate sending email from the business transaction, even without considering rollback failures.

## 4. When is sending directly inside a transaction acceptable?

Not every email needs an outbox. A direct send operation can be acceptable when:

- the application is small or a demo;
- the email is only a secondary notification, and losing one delivery causes no significant harm;
- the business accepts that the email might be sent before commit;
- transactions are short and slow SMTP calls do not noticeably affect them;
- there is a support workflow to handle failed notifications manually.

For example, an internal tool sending low-stakes reminder emails can accept sending directly after a simple data operation completes.

Conversely, for payment confirmations, invoices, ticket bookings, account creation, or emails containing verification codes, consistency guarantees and recoverability must be clearly defined. These cases should usually use at least an after-commit mechanism; if losing a notification is unacceptable, consider an outbox.

## 5. Using events to send email after the transaction commits

A simple approach in Spring is to **publish an application event inside the transaction**, then listen to it using `@TransactionalEventListener` with phase `AFTER_COMMIT`.

~~~mermaid
sequenceDiagram
    participant A as OrderService
    participant D as Database
    participant E as Spring Event
    participant L as Mail Listener
    participant S as SMTP
    A->>D: BEGIN
    A->>D: Update order
    A->>E: publish OrderConfirmedEvent
    Note over E,L: Listener waits for the transaction to complete
    A->>D: COMMIT
    D-->>A: Commit success
    E->>L: AFTER_COMMIT event
    L->>S: Send confirmation
    S-->>L: Submission result
~~~

The listener only runs after the transaction has committed successfully. If the transaction rolls back, an `AFTER_COMMIT` listener is not invoked.

### 5.1. Creating an immutable event

The event should contain enough data to handle the notification and provide a stable snapshot:

~~~java
package com.example.order.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderConfirmedEvent(
        Long orderId,
        String orderNumber,
        String customerEmail,
        String customerName,
        BigDecimal total,
        Instant confirmedAt) {
}
~~~

You do not need to pass the entire `OrderEntity` into the event. If the listener runs after commit or asynchronously, the entity may already be detached, lazy relationships may no longer be accessible, or the data may have changed before the listener reads it. An event containing captured values ensures the notification reflects the exact event that occurred.

If the event contains collections or mutable objects, make defensive copies such as `List.copyOf` and use appropriate immutable types.

### 5.2. Publishing the event inside the transaction

~~~java
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        eventPublisher.publishEvent(
                new OrderConfirmedEvent(
                        order.getId(),
                        order.getOrderNumber(),
                        order.getCustomerEmail(),
                        order.getCustomerName(),
                        order.getTotal(),
                        Instant.now()
                )
        );
    }
}
~~~

The event is published while the transaction is still active. Publishing only notifies Spring's event infrastructure; a listener bound to `AFTER_COMMIT` will be invoked after the commit succeeds.

### 5.3. Listening after commit and sending email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderMailListener {
    private final JavaMailSender mailSender;

    public OrderMailListener(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(event.customerEmail());
        mail.setSubject(
                "Order " + event.orderNumber() + " has been confirmed");
        mail.setText("""
                Hello %s,

                Order %s has been confirmed.
                Total: %s
                """.formatted(
                event.customerName(),
                event.orderNumber(),
                event.total()
        ));

        mailSender.send(mail);
    }
}
~~~

This is a plain-text example. If HTML is needed, the listener can call an application-level `MailService` to render and send according to the application's contract.

**Key point:** the listener is only invoked when the transaction commits. If the order update is rolled back, the email is not sent.

### 5.4. Default behavior when there is no transaction

`@TransactionalEventListener` by default requires a transaction bound to the event. If the event is published outside a transaction, the listener does not run. The `fallbackExecution` attribute can change this behavior:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    // ...
}
~~~

Only enable `fallbackExecution = true` when the business logic genuinely wants the listener to run even without a transaction. Otherwise, the default configuration helps catch events accidentally published outside a transaction instead of silently sending them under different semantics.

## 6. What AFTER_COMMIT solves and what it still lacks

`AFTER_COMMIT` solves an important problem: **not sending emails for rolled-back transactions**.

However, an in-memory application event is not a durable queue. There is a window between the database commit and the listener finishing the send:

~~~text
T1  Database COMMIT succeeds
T2  Process is killed or JVM crashes
T3  Listener has not called SMTP yet

Result:
  Database: transaction is saved
  Email: not sent
~~~

No database transaction can recover an in-memory event after the process stops. Therefore:

- `AFTER_COMMIT` is suitable for simple notifications where the risk of losing an event during this window is acceptable.
- If you must guarantee that the send request is stored together with the business transaction, use a transactional outbox.

### 6.1. Synchronous listeners still make the caller wait

`@TransactionalEventListener` is invoked synchronously by default during transaction completion. Therefore, even though the listener runs **after commit**, the thread completing the transaction may still have to wait for SMTP to finish sending before the request returns.

This means:

- the database has already committed before sending;
- the request may still wait on the send operation;
- send errors can occur after the data has already committed.

If the listener method throws an exception, the exception may propagate back to the committing thread/caller depending on the call path and configuration. However, **the database has already committed and cannot roll back just because the mail listener failed**. An API can encounter a situation where the caller receives an error even though the business change was saved; this must be handled intentionally.

One approach is to catch the error, record the failed send status, and hand it off to a retry/ops workflow. However, merely logging the error and ignoring it can lose notifications if the process stops; an outbox is a better fit when high reliability is required.

### 6.2. Combining with @Async

You can instruct the listener to run on an executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.transaction.event.TransactionalEventListener;

@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    // Send email on an executor thread.
}
~~~

The application must enable async execution with the appropriate configuration, such as `@EnableAsync`. This prevents the transaction-handling thread from waiting on SMTP inside the listener.

However, `@Async` only moves the work to an in-process executor:

- tasks can be lost if the process stops;
- the executor has queue/thread limits and can reject tasks;
- exceptions are not caught by the caller in the normal synchronous way;
- there is no built-in durable retry or job status tracking.

Thus, `@Async + AFTER_COMMIT` is a way to reduce wait time, **not a durable email delivery guarantee mechanism**.

## 7. Using TransactionSynchronization when you need a post-commit callback

Spring also provides `TransactionSynchronizationManager` to register callbacks:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    mailService.send(outgoingMail);
                }
            }
    );
} else {
    // Explicitly define behavior when there is no transaction.
    mailService.send(outgoingMail);
}
~~~

The `afterCommit()` callback runs after the transaction commits. This is useful for certain infrastructure integrations, but `@TransactionalEventListener` usually expresses business intent more clearly and makes it easier to separate the listener into its own bean.

If using manual callbacks:

- you must decide the behavior when no transaction is active;
- avoid holding entities or resources that are only valid inside the transaction;
- pass snapshot data;
- handle post-commit exceptions since rollback is no longer available;
- understand that callbacks are not persisted across restarts.

Do not create a custom callback for every use case if application events already meet your needs.

## 8. Transactional Outbox: storing the send request in the same transaction

If an email is a critical part of the business workflow and must not be lost when the process stops, you can use the **Transactional Outbox Pattern**.

The idea:

1. Within the same database transaction, update the business data.
2. Within that same transaction, insert an outbox record describing the email send request.
3. Commit once so that both the business data and the outbox record succeed or roll back together.
4. A worker/relay reads the outbox after commit and sends the email.
5. The worker updates the status, retries, or moves the job to a dead-letter state when needed.

~~~mermaid
flowchart TD
    A["OrderApplicationService"] --> B["BEGIN DB transaction"]
    B --> C["Update order"]
    B --> D["Insert email outbox row"]
    C --> E{"COMMIT"}
    D --> E
    E -->|Success| F["Outbox relay"]
    E -->|Rollback| G["Order and outbox roll back together"]
    F --> H["Create MIME + send"]
    H --> I{"Submission result"}
    I -->|Success| J["Mark SUBMITTED"]
    I -->|Temporary failure| K["Schedule retry"]
    I -->|Permanent failure| L["Dead-letter / alert"]
~~~

### 8.1. Why is an outbox better than an in-memory event?

`ApplicationEventPublisher` only dispatches events in-process. An outbox stores the send request in the database, in the same transaction as the business data.

Example:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = 123;

INSERT INTO mail_outbox (
    id,
    event_type,
    recipient,
    template_id,
    payload,
    status,
    created_at
)
VALUES (
    'job-123',
    'ORDER_CONFIRMED',
    'alice@example.net',
    'order-confirmation',
    '{"orderNumber":"A123","totalText":"220,000 VND"}',
    'PENDING',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

If the transaction rolls back, both the order update and the outbox insert are rolled back. If the commit succeeds and the process then stops, the outbox record remains for the worker to process after the application restarts.

### 8.2. What fields can an outbox table contain?

An illustrative schema:

~~~sql
CREATE TABLE mail_outbox (
    id               VARCHAR(64) PRIMARY KEY,
    event_type       VARCHAR(100) NOT NULL,
    recipient        VARCHAR(320) NOT NULL,
    template_id      VARCHAR(150) NOT NULL,
    template_version VARCHAR(50),
    payload          TEXT NOT NULL,
    status           VARCHAR(30) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMP,
    created_at       TIMESTAMP NOT NULL,
    submitted_at     TIMESTAMP,
    last_error_code  VARCHAR(100),
    last_error_at    TIMESTAMP
);
~~~

This is a reference schema; data types, indexes, JSON types, timezone-aware timestamps, and lengths must be adjusted for your database. You can add `locked_until`, `locked_by`, `lease_token`, or `version` to coordinate multiple workers.

Key fields:

- `id`: stable job ID for tracing and deduplication.
- `event_type`: business event type.
- `recipient`: resolved recipient address.
- `template_id` and `template_version`: content template to render.
- `payload`: snapshot of presentation data.
- `status`: processing status.
- `attempts` and `next_attempt_at`: retry control.
- `submitted_at`: timestamp when transport completed submission.
- `last_error_code`: categorized failure reason, avoiding storing full sensitive content.

Do not put SMTP passwords, OAuth tokens, or secrets into the payload. Protect recipients and email content according to personal data retention policies.

### 8.3. Writing to the outbox in the same transaction

A service can do:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderConfirmationPayload payload =
                OrderConfirmationPayload.from(order);

        outbox.insert(
                MailOutboxMessage.pending(
                        "order-confirmed-" + order.getId(),
                        order.getCustomerEmail(),
                        "order-confirmation",
                        payload
                )
        );
    }
}
~~~

`orders.save(...)` may not be needed if the entity is managed by the persistence context and dirty checking persists the changes at commit. The exact approach depends on your repository/JPA mapping.

The critical point is that `outbox.insert(...)` participates in **the same transaction manager and the same database transaction** as the order update. If the outbox is written to a different database or an independent broker without a coordination mechanism, this atomicity is no longer automatically guaranteed.

### 8.4. Outbox worker processing

The worker performs:

1. Claim one or more `PENDING` records that are due for processing.
2. Save a lease/lock or update the status so other workers do not process them concurrently.
3. Commit the short claim transaction.
4. Read the payload and render the content.
5. Call `MailService`/`JavaMailSender` outside the claim transaction.
6. If the sender returns normally, update status to `SUBMITTED`.
7. On temporary failure, increment attempts and set `next_attempt_at`.
8. On permanent failure or after exhausting retry limits, transition to `FAILED_FINAL`/dead-letter.

Do not keep a database transaction and row lock open while waiting on SMTP. Claiming should be short; sending is an external network operation; updating the result happens in a separate transaction.

### 8.5. Outbox states

~~~text
PENDING
   |
   v
PROCESSING
   |--------------------------|
   v                          v
SUBMITTED                  RETRY_WAIT
                              |
                              v
                          PROCESSING
                              |
                              v
                         FAILED_FINAL
~~~

State names may vary, but you need to distinguish:

- job not yet picked up by a worker;
- job currently being processed / holding a lease;
- transport has submitted the message;
- job waiting for retry;
- job ended in failure and requires intervention.

`SUBMITTED` still does not mean the email reached the Inbox. Delivery/bounce status, if needed, must be updated from separate provider events.

## 9. An outbox still needs duplicate-send handling

An outbox prevents losing the **send request** when the business transaction commits. It does not by itself guarantee that SMTP sends exactly once.

Scenario:

~~~text
T1 Worker claims job J-123
T2 SMTP server accepts the email
T3 Worker crashes before updating status = SUBMITTED
T4 Lease expires
T5 Another worker picks up J-123 again
T6 The email may be sent a second time
~~~

This is a common characteristic of **at-least-once** processing systems. To reduce risk:

- use a stable job ID and unique constraint for the business event;
- if the provider supports an idempotency key, send the key per the provider's contract;
- store the provider message ID when available;
- distinguish definite failures from indeterminate outcomes;
- design emails/CTAs to tolerate duplicate receipt when duplicates cannot be completely eliminated.

Plain SMTP does not provide a universal idempotency mechanism guaranteeing exactly-once delivery for every send. You should not claim that an outbox automatically solves duplicate sends.

### 9.1. Generating a stable job ID

Example:

~~~text
order-confirmed:123:version-1
~~~

If the same order confirmation event is processed twice, the system can use a unique key to avoid inserting two identical outbox records. Choose the key according to business semantics: if a customer genuinely needs to receive two different notifications, do not deduplicate solely by order ID.

### 9.2. Leases and multiple workers

If multiple workers read from the same outbox, you must prevent two workers from sending the same job simultaneously. You can use:

- row locking in a short transaction;
- `SELECT ... FOR UPDATE SKIP LOCKED` syntax on databases that support it;
- a lease/locked-until column and claim token;
- a queue broker with visibility timeout.

SQL and locking semantics vary by database. `SKIP LOCKED` is not portable syntax across all database engines. Whichever mechanism you use, the lease must expire if a worker dies so the job can be reprocessed.

## 10. Choosing between a payload snapshot or re-rendering after commit

If a worker sends the email after some delay, data in the database may have changed. You must decide whether the email should reflect **the state at the time of the event** or **the latest state at send time**.

For example, order A123 is confirmed at 10:00 with a total of 220,000 VND. At 10:05, the system adjusts the shipping fee. The worker sends the email at 10:10.

Two policies:

| Policy | Email data | Suitable when |
| --- | --- | --- |
| Snapshot at confirmation | Total 220,000 VND per the emitted event | The email is evidence/notification of a specific event |
| Read latest data at send time | Total per database state at 10:10 | The email's purpose is to show the current state |

If using a snapshot:

- store the recipient, order number, amount, and data needed for rendering in the outbox;
- use the appropriate template version;
- avoid depending on mutated entities.

If using the latest data:

- store only the ID and make explicit that the worker will re-query;
- check the current status before sending;
- accept that content may differ from when the event was created.

Do not let this behavior happen accidentally because a listener or worker queries the database at a different time.

## 11. Template versions and finalized content

The outbox can store:

~~~json
{
  "orderNumber": "A123",
  "customerName": "Nguyen An",
  "totalText": "220,000 VND",
  "orderUrl": "https://app.example.com/orders/A123"
}
~~~

If you only store `templateId` and the worker uses the current template, a long-queued email might be rendered with a new version after a deployment. This may be desirable, but if you need to preserve approved content, also store `templateVersion` or store an HTML/text snapshot.

There are three common approaches:

1. **Snapshot model + template version:** payload holds captured data, worker renders the exact template version.
2. **HTML/text snapshot:** store the complete rendered content; worker only builds MIME and sends.
3. **Latest data + latest template:** worker re-reads domain state and uses the current template; suitable when the email must reflect the latest state.

Payloads may contain personal data; restrict access, encrypt storage if appropriate, enforce retention, and keep logging minimal.

## 12. Comparing transaction-related sending approaches

| Approach | Avoids sending on DB rollback? | Can lose request after process crash? | Durable retry? | Complexity |
| --- | --- | --- | --- | --- |
| Call SMTP directly in `@Transactional` | No | Yes | Not built-in | Low |
| Catch error and log inside transaction | No; email can still go out before commit | Yes | Not built-in | Low |
| `@TransactionalEventListener(AFTER_COMMIT)` | Yes | Yes, if crash occurs after commit before listener | Not built-in | Low to medium |
| `AFTER_COMMIT` + `@Async` | Yes | Yes; in-process executor is not durable | Not built-in | Medium |
| Transactional outbox + worker | Yes, if outbox is in the same transaction | Send request is durably stored | Can be designed | Higher |

### 12.1. Guidelines for choosing an approach

- **Demos or secondary notifications:** direct calls can be used if external side effects and wait times are acceptable.
- **Need to avoid emails for rolled-back transactions, while tolerating rare notification loss:** use `AFTER_COMMIT`.
- **Need to reduce request time waiting on SMTP:** an async listener can be used, but you must accept that the executor is not durable.
- **Email is a critical part of the workflow:** use a transactional outbox with workers, retries, monitoring, and a dead-letter policy.

None of these options turns SMTP and the database into an atomic distributed transaction. An outbox ensures the send request is stored together with database changes, then handles delivery under an eventual consistency model.

## 13. Testing transaction and email behavior

You should not merely mock `JavaMailSender` and verify the method was called. You need to verify the exact **timing** of the mail sender call relative to commit/rollback.

### 13.1. Testing direct send: email is called before commit

With a direct call inside a `@Transactional` method, you can verify that the sender is invoked before the transaction finishes. This test illustrates the ordering risk without needing a real SMTP server.

### 13.2. Testing AFTER_COMMIT: sent only after commit

An integration test can:

1. Call the application service inside a real transaction.
2. Verify that the listener has not sent while the transaction is still active.
3. Commit the transaction.
4. Confirm the listener was invoked and the sender received the message.

### 13.3. Testing rollback: not sent

Create a transaction that updates the order, publishes the event, and then forces a rollback:

~~~java
try {
    transactionTemplate.execute(status -> {
        orderService.confirmAndPublish(orderId);
        status.setRollbackOnly();
        return null;
    });
}
~~~

After the transaction ends, verify that `JavaMailSender` was not called. An `AFTER_COMMIT` listener does not run when the transaction rolls back.

### 13.4. Note on auto-rolling-back test transactions

Spring tests typically run each test in a transaction and roll it back at the end. If you test `@TransactionalEventListener(AFTER_COMMIT)` in a test whose default transaction rolls back, the listener will not run.

To test commit behavior, you must:

- use `TransactionTemplate` and let the transaction complete its commit;
- or intentionally configure the test to commit, e.g., `@Commit`;
- or invoke the service through a real transaction managed by an appropriate test setup.

Do not conclude that the listener is broken just because the test framework rolled back the transaction.

### 13.5. Testing the outbox

For an outbox, you need to verify:

- when the order commits, the outbox row also exists;
- when the order transaction rolls back, the outbox row does not exist;
- the worker claims the job and calls `MailService`;
- temporary failures increment attempts and schedule a retry time;
- permanent failures transition to a terminal state;
- worker crashes after SMTP submission are handled per the duplicate-send policy;
- expired leases allow another worker to continue.

You can use a mock SMTP server like Mailpit or GreenMail to verify the MIME message sent, but database/outbox tests still need to assert persistence state separately.

## 14. Common pitfalls

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Confirmation email sent even though order rolled back | SMTP called before commit | Use `AFTER_COMMIT` or an outbox |
| Order committed but no email sent | Process stopped after commit before sending | Durable outbox |
| API returns error yet data was saved | Listener failed after commit and exception propagated to caller | Separate business outcome from notification outcome |
| Slow requests when SMTP is slow | Synchronous send in transaction or synchronous listener after commit | Offload to worker/queue if needed |
| Duplicate emails after retry | SMTP may have accepted while worker had not recorded status | Idempotency, provider message ID, and job status |
| `@TransactionalEventListener` does not run in tests | Test transaction was rolled back | Test with a real committed transaction |
| Listener runs even without a transaction | `fallbackExecution = true` enabled | Enable only when that is the intended policy |
| Async listener loses events on restart | Executor exists only in-process | Use an outbox or durable queue |
| Worker cannot render old content accurately | Only entity ID stored and latest data read | Payload snapshot or template version |
| Outbox job sent simultaneously by two workers | Uncoordinated claim/lease | Locks/leases and concurrency handling |
| Attachment deleted before retry | Cleaned up after each attempt | Retain artifacts until terminal state |

## 15. Notes on transaction propagation

Do not try to solve email-sending issues by arbitrarily adding `REQUIRES_NEW` or changing method propagation.

Example:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void sendMail(...) {
    mailSender.send(...);
}
~~~

`REQUIRES_NEW` creates a separate database transaction when an outer transaction exists. However, SMTP still does not participate in that transaction. It cannot recall the email if the business transaction rolls back, nor can it guarantee the email is sent if the process stops.

Similarly, setting `NOT_SUPPORTED` to suspend the transaction while sending can avoid holding the database transaction while waiting on SMTP, but **does not automatically guarantee correct business ordering**. If the data has not committed yet, the email can still be sent before the transaction finishes.

Choose the solution based on your goal:

- want to avoid sending on rollback: execute after commit;
- want to avoid losing requests after commit: outbox;
- want to avoid holding connections while SMTP is slow: worker sending outside the transaction;
- want to reduce duplicate sends: idempotency and state management.

## 16. End-to-end scenario: order confirmation

Suppose the system needs to send a confirmation email after an order transitions to `CONFIRMED`.

### 16.1. Direct version

~~~text
@Transactional confirmOrder()
  -> load order
  -> update order
  -> create SimpleMailMessage
  -> JavaMailSender.send()
  -> method returns
  -> DB commit
~~~

Simple, but the email can go out before commit; slow SMTP prolongs the transaction.

### 16.2. AFTER_COMMIT version

~~~text
@Transactional confirmOrder()
  -> update order
  -> publish OrderConfirmedEvent
  -> DB commit
  -> listener receives event
  -> JavaMailSender.send()
~~~

Does not send on rollback. There is still a gap after commit before the listener completes; in-memory events can be lost if the process stops.

### 16.3. Transactional outbox version

~~~text
@Transactional confirmOrder()
  -> update order
  -> insert mail_outbox snapshot
  -> DB commit

Mail worker
  -> claim outbox row
  -> render template
  -> send through MailService
  -> update SUBMITTED or RETRY_WAIT
  -> cleanup artifact when terminal
~~~

The order and the send request are saved in the same transaction. The worker can resume after an application restart, retry temporary failures, and route permanent failures to a handling workflow. Duplicate-send protection must be designed because SMTP submission and updating the outbox status are not an atomic transaction.

## 17. Key takeaways

- SMTP does not participate in Spring's database transaction.
- Calling `JavaMailSender.send` inside `@Transactional` can send the email before the database commits.
- If the transaction rolls back after SMTP accepts the message, the email cannot be recalled via rollback.
- If sending fails and the exception escapes the method, Spring may roll back the transaction; this is a business decision that must be weighed carefully.
- Sending after commit avoids notifying on rolled-back transactions, but in-memory events can still be lost if the process stops.
- `@Async` reduces wait time but does not create a durable queue.
- A transactional outbox stores the send request in the same business transaction, and a worker sends and retries after commit.
- An outbox usually provides at-least-once processing; duplicate sends and indeterminate SMTP outcomes still require handling.
- Record the `SUBMITTED` status instead of asserting `DELIVERED` when you only know the sender submitted the message.

When designing email delivery around a business transaction, first decide what must be guaranteed: no sending on rollback, no lost requests after commit, response latency, or retry capability. Sending directly in a transaction can work for simple, low-stakes tasks, but for notifications tightly coupled to business state, `AFTER_COMMIT` or a transactional outbox establishes a clearer boundary between **committing data** and **sending notifications**.

### References

- **Spring Framework Reference — Transaction Management:** transaction boundaries, rollback rules, and transaction synchronization.
- **Spring Framework Reference — Transaction-bound Events:** `@TransactionalEventListener` and the phases `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
- **Spring Framework Reference — Application Events:** `ApplicationEventPublisher` and listeners.
- **Spring Framework Reference — Task Execution and Scheduling:** `@Async` and executors.
- **Spring Framework API — `TransactionSynchronizationManager`:** registering callbacks aligned with the transaction lifecycle.
- **Transactional Outbox Pattern:** storing events/jobs in the same data transaction and relaying after commit.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP responses and the message acceptance process.
