# Risk of Transaction Commit Succeeding While Email Sending Fails in Spring Framework Mail

Sending email is an external side effect outside the database. When an application updates an order, saves a transaction state, or creates an account and then sends a notification email, the two operations typically happen across two independent systems: the database and the SMTP provider. The database has transactions, while SMTP does not participate in that transaction. Therefore, there is no single shared rollback command that can undo both the data write and the email send.

This creates an important risk: **the database transaction may commit successfully while the email fails to send**, or the email may already be accepted by SMTP while the database transaction subsequently rolls back. Both situations can leave business state and user notifications inconsistent.

In Spring Framework Mail, calling **JavaMailSender.send(...)** itself is usually straightforward. The hard part lies in choosing the right time to send, deciding what happens when SMTP fails, and ensuring send requests do not vanish when the application crashes. This lesson explains the failure windows, how to use transaction events, the limitations of **@TransactionalEventListener**, and how to implement a transactional outbox when high reliability is required.

## 1. The database transaction and SMTP are two independent systems

Consider the order confirmation use case:

1. Read the pending order.
2. Transition its status to CONFIRMED.
3. Save the change to the database.
4. Send a confirmation email to the customer.

The database can commit or roll back SQL statements inside a transaction. The SMTP server handles accepting messages under its own protocol. SMTP accepting an email is not part of the database transaction.

~~~text
Application
   |
   +---- Database transaction
   |         |
   |         +--> UPDATE order
   |         +--> COMMIT / ROLLBACK
   |
   +---- SMTP operation
             |
             +--> Submit MIME message
             +--> SMTP response
~~~

The two systems do not share a transaction manager. If the database rolls back, SMTP does not automatically recall an accepted email. If SMTP rejects the email, the database does not automatically know whether to roll back or preserve the business state.

This is the problem of coordinating side effects across multiple systems. It appears with email, SMS, push notifications, webhooks, payments, message publishing, and HTTP calls to external services.

## 2. Two fundamental failure windows

There are two common ways to call mail inside a transactional method, and both carry risks.

### Case A: Sending email before the transaction commits

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    mailDelivery.sendConfirmation(order);
}
~~~

Flow:

~~~text
BEGIN DB TRANSACTION
        |
        v
Update order = CONFIRMED
        |
        v
SMTP accepts email successfully
        |
        v
Database COMMIT fails
        |
        v
Database ROLLBACK
~~~

The customer may receive an email stating that the order was confirmed, while the database still records the order as PENDING. An email already sent cannot be undone by SQL rollback.

Another variant: SMTP sending succeeds, then a subsequent database statement or pre-commit step fails. The outcome is still that an email went out while the business change was not committed.

### Case B: Committing the database first, then sending email

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    order.confirm();
    orderRepository.save(order);
}

// Another step sends the email after the method returns.
mailDelivery.sendConfirmation(orderId);
~~~

Flow:

~~~text
BEGIN DB TRANSACTION
        |
        v
Update order = CONFIRMED
        |
        v
DATABASE COMMIT succeeds
        |
        v
Application calls SMTP
        |
        v
SMTP timeout / rejection / connection drop
        |
        v
Order remains CONFIRMED, email not sent
~~~

In this case, the business data is accurate, yet the customer does not receive the notification. If the email is an important part of the workflow, the system must know the send request failed and have a way to follow up.

### Comparing the two risks

| Send timing | When SMTP succeeds but DB rolls back | When DB commits but SMTP fails |
| --- | --- | --- |
| Send before commit | May send an inaccurate status notification | SMTP error may roll back the transaction depending on exception |
| Send after commit | Eliminates risk of SMTP running before commit | Business change is saved, but notification may be lost |

No ordering of two sequential commands turns the database and SMTP into a single atomic transaction. You must choose a strategy based on how critical the email is.

## 3. Why should SMTP not be sent inside a long transaction?

A database transaction should focus on data operations that must commit together. Calling SMTP inside a transaction can keep database connections and locks held while waiting on the network.

Common issues:

- A slow SMTP server prolongs the transaction.
- Database connections are held during email transmission.
- Locks on the order or related rows are held longer.
- Throughput drops when many requests send mail concurrently.
- An SMTP timeout may roll back the transaction even though the business change was valid.
- The email may be accepted while the database commit later fails.

For example, if SMTP takes 8 seconds to respond, the order confirmation transaction may hold a connection for an extra 8 seconds. Under high request volume, the connection pool can be exhausted even though the database queries themselves are very fast.

A good structure is to complete the data transaction first, then handle sending in a separate step. However, merely moving the call outside the transaction still does not solve the case where the application crashes right between commit and send.

## 4. Be careful with Spring's rollback rules

Spring transactions roll back by default when a method exits with a **RuntimeException** or **Error**. Checked exceptions do not trigger rollback by default unless **rollbackFor** or a matching rule is configured.

In the email-sending flow, Spring's **MailException** is a runtime exception, whereas some Jakarta Mail APIs such as **MessagingException** are checked exceptions. Adapters may wrap checked errors into application runtime exceptions.

Example:

~~~java
@Transactional
public void confirmOrder(Long orderId) {
    Order order = loadOrder(orderId);
    order.confirm();
    orderRepository.save(order);

    mailDelivery.sendConfirmation(order);
}
~~~

If the adapter throws **MailDeliveryException extends RuntimeException**, the transaction typically rolls back by default. If a checked exception is thrown with no rollback rule, the transaction may still commit depending on how the exception is handled.

You can specify it explicitly:

~~~java
@Transactional(rollbackFor = MessagingException.class)
public void confirmOrder(Long orderId) throws MessagingException {
    // Modify data and send email.
}
~~~

However, rollback rules only govern the database transaction. They cannot recall an email already accepted by SMTP. If the email sends successfully and the transaction then hits a commit failure, the inconsistency still remains.

Do not use rollback rules as a mechanism to guarantee atomicity between the database and SMTP.

## 5. Using @TransactionalEventListener(AFTER_COMMIT)

Spring provides **@TransactionalEventListener** to process an application event according to a transaction phase. For notification emails after an order commits, you can use the **AFTER_COMMIT** phase.

Event:

~~~java
public record OrderConfirmedEvent(
    Long orderId,
    String customerEmail,
    String orderCode
) {}
~~~

Publish the event inside the transaction:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(
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
        orderRepository.save(order);

        eventPublisher.publishEvent(
            new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCode()
            )
        );
    }
}
~~~

Listener sends email after the transaction commits:

~~~java
@Component
public class OrderMailListener {

    private final OrderConfirmationMailer mailer;

    public OrderMailListener(OrderConfirmationMailer mailer) {
        this.mailer = mailer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailer.sendConfirmation(
            event.customerEmail(),
            event.orderCode()
        );
    }
}
~~~

When the transaction rolls back, the AFTER_COMMIT listener is not called. Only when the transaction commits successfully is the listener triggered. This prevents sending an email before the order state is committed.

### What does AFTER_COMMIT solve?

- Sending is only requested after the transaction succeeds.
- If the transaction rolls back, the event listener does not run.
- Mail-sending logic is separated from the data-updating method.
- The use case can publish a semantically meaningful business event, and the listener decides how to react.

### AFTER_COMMIT does not guarantee durable event persistence

Application events are in-memory process events by default. There is a gap:

~~~text
Database COMMIT succeeds
        |
        v
Process is killed / server loses power
        |
        v
Listener has not executed yet
        |
        v
No email and no durable record to retry
~~~

If the process stops after commit but before the listener sends the email, the event is lost along with process memory. The database has no record indicating that an email needs to be sent.

Additionally, the listener may run while SMTP fails. The database transaction has already committed, so an exception in the listener cannot roll back the committed changes.

Therefore, **@TransactionalEventListener(AFTER_COMMIT)** is suited for best-effort side effects or notifications whose loss in a small failure window is acceptable. For critical transactional emails, the send request must be stored durably.

## 6. Phases of transactional events

**@TransactionalEventListener** supports these phases:

| Phase | Timing | Risk / Meaning |
| --- | --- | --- |
| BEFORE_COMMIT | Before the transaction commits | Email may be sent even if commit later fails |
| AFTER_COMMIT | After the transaction commits successfully | Avoids sending before commit, but in-memory event may be lost if process crashes |
| AFTER_ROLLBACK | After the transaction rolls back | Used for rollback-dependent handling; usually not for success confirmation emails |
| AFTER_COMPLETION | After the transaction completes, commit or rollback | Must inspect completion status yourself if behavior differs |

If no phase is specified, the default is AFTER_COMMIT. A transactional listener is only invoked when an eligible transaction is active, unless **fallbackExecution** is enabled. Do not enable fallback just to make the listener run in all cases without explicitly defining the behavior when no transaction exists.

### Combining with @Async

You can run the listener asynchronously:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class OrderMailListener {

    private final OrderConfirmationMailer mailer;

    public OrderMailListener(OrderConfirmationMailer mailer) {
        this.mailer = mailer;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailer.sendConfirmation(
            event.customerEmail(),
            event.orderCode()
        );
    }
}
~~~

This reduces request processing time because sending runs on an executor. However, the event still lives only in memory; a process crash can lose the event. If the executor is full, shut down, or the listener fails, observability and error handling are needed. **@Async** does not automatically turn an event into a durable message.

With an asynchronous listener, exceptions do not automatically return to the completed request. Configure executor exception handling and appropriate metrics.

## 7. What is a transactional outbox?

A transactional outbox stores the **notification send intent** in the database in the same transaction as the business change. An independent worker reads committed records and sends the emails.

Instead of doing:

~~~text
UPDATE order
COMMIT
Send email
~~~

the application does:

~~~text
BEGIN TRANSACTION
    UPDATE order
    INSERT mail_outbox
COMMIT

Worker:
    SELECT mail_outbox
    Send email
    UPDATE mail_outbox status
~~~

Both the order update and the outbox row insert sit inside the same database transaction. Therefore:

- If the transaction rolls back, both the order change and the outbox row roll back.
- If the transaction commits, both the order change and the send request are persisted.
- If the process crashes after commit, the worker can still find the outbox row when the application restarts.
- If SMTP temporarily fails, the worker can retry based on the surviving record.

An outbox solves **not losing the send request between database commit and enqueueing**. It does not create an atomic transaction with SMTP and does not by itself guarantee the email is sent only once.

## 8. Creating the outbox table

A basic schema can look like this:

~~~sql
CREATE TABLE mail_outbox (
    id                  UUID PRIMARY KEY,
    idempotency_key     VARCHAR(200) NOT NULL UNIQUE,
    event_type          VARCHAR(120) NOT NULL,
    aggregate_id        VARCHAR(120) NOT NULL,
    payload             JSONB NOT NULL,
    status              VARCHAR(30) NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by           VARCHAR(120),
    locked_until        TIMESTAMPTZ,
    provider_message_id VARCHAR(255),
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at        TIMESTAMPTZ
);

CREATE INDEX idx_mail_outbox_pending
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Meaning of the fields:

| Field | Purpose |
| --- | --- |
| id | Unique identifier of the send request |
| idempotency_key | Key preventing multiple outbox records for the same business event |
| event_type | Notification type, e.g., ORDER_CONFIRMED |
| aggregate_id | Order ID or related business object ID |
| payload | Data required to construct the email |
| status | Current processing state |
| attempts | Number of send attempts by workers |
| next_attempt_at | Earliest timestamp eligible for the next attempt |
| locked_by | Worker currently holding processing ownership of the record |
| locked_until | Lease expiration time so another worker can reclaim it |
| provider_message_id | ID returned by the provider if available |
| last_error | Bounded and sanitized error details |
| created_at | Timestamp when the request was created |
| submitted_at | Timestamp when transport confirmed submission |

JSONB is a PostgreSQL data type in this example. For other databases, you can use JSON, TEXT, or separate columns. You do not need to store full HTML or attachment bytes in the outbox if the payload can reference templates and secure file storage.

The unique constraint on idempotency_key prevents creating two send requests for the same event when a business request is retried. The key must reflect the event identity, such as order ID plus event version or business event ID; do not generate a fresh random string on each retry of the same operation.

## 9. Writing to the outbox in the same transaction as business changes

Example payload DTO:

~~~java
public record OrderConfirmedMailPayload(
    Long orderId,
    String orderCode,
    String customerEmail,
    String customerName,
    String locale
) {}
~~~

Service:

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public OrderConfirmationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        OrderConfirmedMailPayload payload =
            new OrderConfirmedMailPayload(
                order.getId(),
                order.getCode(),
                order.getCustomerEmail(),
                order.getCustomerName(),
                "vi-VN"
            );

        MailOutboxMessage message = MailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED:" + order.getId(),
            "ORDER_CONFIRMED",
            order.getId().toString(),
            serialize(payload)
        );

        outboxRepository.save(message);
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                "Cannot serialize mail outbox payload",
                exception
            );
        }
    }
}
~~~

The critical point is that **orderRepository.save** and **outboxRepository.save** participate in the same transaction manager and the same database transaction. If the two repositories use two separate datasources/transaction managers, a standard @Transactional annotation does not automatically create an atomic commit across them.

Do not use **REQUIRES_NEW** for the outbox insert operation in this scenario. If the outbox commits independently while the order transaction rolls back, the worker may send an email for a change that was never committed.

If using JPA, the outbox entity must be persisted within the active transaction. A flush may be needed to catch constraint errors early, but flushing is not committing; the record still rolls back with the transaction.

### Storing a snapshot or only the aggregate ID?

The payload can store data captured at the time the event occurred, or store only the order ID so the worker reads the latest data.

| Storage choice | Advantages | Risks |
| --- | --- | --- |
| Snapshot payload | Email reflects exact data at event time | Payload contains personal data and requires retention management |
| Store aggregate ID only | Small outbox, less duplicated data | Worker may read newer state and produce content differing from the original event |
| Store ID + version | Can read the exact version or detect changed data | Requires version/history mechanism in the domain |

For transactional confirmation emails, snapshots are usually easier to reason about because content should match the committed event. Store only the minimum necessary data; do not put secrets, login tokens, or unnecessary sensitive data into the payload. For large attachments, store an immutable file reference instead of embedding bytes in the outbox.

## 10. Worker reading and claiming outbox records

Workers must ensure two instances do not send the same record at the same time. A common approach is claiming records in a short transaction with row locks, then committing the PROCESSING status before calling SMTP.

With PostgreSQL, you can use FOR UPDATE SKIP LOCKED:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        OR (
            status = 'PROCESSING'
            AND locked_until < CURRENT_TIMESTAMP
        )
    )
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 20
)
UPDATE mail_outbox AS outbox
SET status = 'PROCESSING',
    locked_by = :workerId,
    locked_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempts = attempts + 1
FROM candidates
WHERE outbox.id = candidates.id
RETURNING outbox.*;
~~~

This is a PostgreSQL SQL example; syntax and parameter binding must be adapted to your repository/driver. SKIP LOCKED allows other workers to skip rows already locked by another transaction, reducing contention when multiple workers run.

The processing sequence should be:

1. Open a short transaction.
2. Claim a batch of records and set leases.
3. Commit the PROCESSING status.
4. Close the database transaction.
5. Send emails via the adapter.
6. Open a new transaction to update SUBMITTED or RETRY_WAIT/FAILED.

Do not hold a transaction and row locks open throughout the SMTP call. The network may be slow or hang, causing the worker to hold database resources unnecessarily.

### Leases for handling stopped workers

If a worker dies while a record is PROCESSING, the lease will expire. Another worker can reclaim the record. The lease should be longer than the expected send duration and can be renewed for long-running tasks.

Leases recover abandoned work, but do not completely solve duplicate sends. If the first worker sent successfully and died before updating the status, the next worker will not know the email was already accepted.

## 11. Separating claim, send, and status updates

A controllable Spring structure uses separate beans for the claim transaction and result-update transaction.

Claim service:

~~~java
@Service
public class MailOutboxClaimer {

    private final MailOutboxRepository repository;

    public MailOutboxClaimer(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<MailOutboxMessage> claimBatch(
            String workerId,
            int batchSize) {
        return repository.claimAvailable(workerId, batchSize);
    }
}
~~~

Worker:

~~~java
@Component
public class MailOutboxWorker {

    private final MailOutboxClaimer claimer;
    private final MailDeliveryPort mailDelivery;
    private final MailOutboxResultService resultService;

    public MailOutboxWorker(
            MailOutboxClaimer claimer,
            MailDeliveryPort mailDelivery,
            MailOutboxResultService resultService) {
        this.claimer = claimer;
        this.mailDelivery = mailDelivery;
        this.resultService = resultService;
    }

    public void dispatch(String workerId) {
        List<MailOutboxMessage> messages =
            claimer.claimBatch(workerId, 20);

        for (MailOutboxMessage message : messages) {
            try {
                OutgoingMail mail = mapToOutgoingMail(message);
                mailDelivery.send(mail);

                resultService.markSubmitted(message.id());
            } catch (TransientMailException exception) {
                resultService.scheduleRetry(
                    message.id(),
                    exception.getMessage()
                );
            } catch (PermanentMailException exception) {
                resultService.markFailed(
                    message.id(),
                    exception.getMessage()
                );
            }
        }
    }
}
~~~

MailOutboxClaimer is a separate bean so that Spring's transaction proxy applies to the claim method. Avoid calling a @Transactional method from another method on the same instance and expecting self-invocation to go through the proxy.

MailOutboxResultService should update status using separate short transactions. The worker does not annotate the entire dispatch method with @Transactional because the mail delivery call must run outside the claim transaction.

This example is an illustrative structure. Mapping exceptions to transient/permanent must be based on provider responses, error types, and application policies.

## 12. An outbox does not automatically guarantee exactly-once

An important scenario:

~~~text
Worker claims record
       |
       v
SMTP accepts email successfully
       |
       v
Worker is killed before UPDATE status = SUBMITTED
       |
       v
Lease expires
       |
       v
Another worker reclaims record
       |
       v
Email may be sent a second time
~~~

The database does not know SMTP accepted the email if the worker could not record the result in time. SMTP and the database share no transaction to commit both operations together.

A transactional outbox typically provides an **at-least-once attempt** model: the request is durably saved and can be retried, yet a side effect may occur multiple times within certain failure windows.

### Reducing the risk of duplicate sends

- Use a stable outbox ID or idempotency key for the same event.
- If the provider API supports an idempotency key, send the same key across retries of a request.
- Save the provider message ID when returned.
- Create a unique constraint for the business event to prevent duplicate outbox inserts.
- Track attempt status and send timestamps.
- Design emails to tolerate duplicate receipt when provider idempotency is unavailable.

Standard SMTP provides no uniform idempotency mechanism. The Message-ID header is useful for correlation and diagnostics, but does not guarantee that every SMTP provider or mailbox will drop duplicate messages. Never claim exactly-once just because the database has a status column.

## 13. Classifying errors and designing retries

Not every mail-sending error should be retried.

| Error category | Example | Handling approach |
| --- | --- | --- |
| Temporary | Connection timeout, server unavailable, temporary rate limit | Retry with backoff and jitter |
| Configuration | Wrong credentials, wrong host, TLS error | Stop rapid retries and alert operations |
| Content | Invalid recipient, file over size limit, template error | Mark FAILED to fix data |
| Policy | Blocked sender/domain, disallowed MIME type | Do not retry the message as-is |
| Indeterminate outcome | Timeout after SMTP DATA may have been received | Reconcile with provider or accept duplicate risk |

A simple retry schedule can grow exponentially:

~~~text
attempt 1: wait 30 seconds
attempt 2: wait 1 minute
attempt 3: wait 2 minutes
attempt 4: wait 4 minutes
attempt 5: wait 8 minutes
...
~~~

In production, add jitter so multiple workers do not retry simultaneously at the exact same instant, cap maximum wait duration, and bound total attempts. Values must be based on provider SLAs and email type.

Delay calculation example:

~~~java
public Duration retryDelay(int attempt) {
    int exponent = Math.min(Math.max(attempt - 1, 0), 8);
    long baseSeconds = 30L * (1L << exponent);
    long cappedSeconds = Math.min(baseSeconds, 3600L);

    long jitterSeconds =
        ThreadLocalRandom.current().nextLong(0, 16);

    return Duration.ofSeconds(cappedSeconds + jitterSeconds);
}
~~~

This is an illustrative policy. In large systems, prefer an existing retry framework or scheduler instead of building complex distributed mechanisms from scratch.

### Do not retry indefinitely

After the maximum number of attempts, move the record to FAILED or DEAD_LETTER for observability and manual handling. Store normalized error codes, attempt counts, and correlation IDs. Do not store passwords, HTML content, or sensitive data in last_error.

A manual requeue action should include an audit log and reason. Once configuration or data errors are fixed, operators can return the record to a reprocessable state.

## 14. SMTP accepted does not mean delivered

When JavaMailSender.send(...) returns normally, the adapter usually only knows that transport completed submission per the library contract. That does not prove:

- The email landed in the Inbox.
- The email did not bounce afterward.
- The email was not caught by a spam filter.
- The recipient opened or read the email.

Set the outbox status to SUBMITTED or ACCEPTED_BY_TRANSPORT when SMTP submission succeeds. If the provider offers webhooks/events for delivered, bounced, deferred, or complained, store those states in a separate delivery-tracking stream.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP accepted ----> SUBMITTED
   |                            |
   |                            +--> DELIVERED (provider event)
   |                            +--> BOUNCED (provider event)
   |
   +---- transient error --> RETRY_WAIT
   |
   +---- permanent error --> FAILED
~~~

SMTP does not always provide final delivery events. When using only a basic SMTP relay, SUBMITTED may be the final level of observability the application has.

## 15. Outbox payload and templates need versioning

If the worker only stores the order ID and renders the email minutes later, the order data may already have changed. The confirmation email could show a different address, total amount, or details than at confirmation time.

There are two choices:

**Snapshot payload:** store the necessary values right when the transaction commits. The worker uses that snapshot to render content consistent with the event.

**Reference payload:** store the aggregate ID and version. The worker reads the data corresponding to the version that emitted the event. This requires history/event versioning in the domain or a mechanism guaranteeing the exact snapshot is read.

For transactional confirmation emails, snapshots are usually easier to understand because content must match the committed event. For templates, record template key and version if emails must be reproducibly rendered later. If the worker uses the latest template after a deployment, an older event might render with a different layout or wording.

The payload should contain enough data for stable processing without over-collecting. Avoid storing passwords, reset tokens, or unnecessary personal data in the outbox longer than operational retention allows.

## 16. Handling attachments in the outbox

Do not store large PDFs or images as Base64 inside a JSON payload column. That bloats the database, increases backup costs, and forces workers to parse huge payloads.

Instead, store a reference to a durably stored file:

~~~json
{
  "eventId": "9c85b7d0-1234-4abc-9abc-123456789012",
  "template": "invoice-email",
  "templateVersion": 3,
  "recipient": "customer@example.com",
  "attachment": {
    "fileId": "invoice-2026-001",
    "fileName": "invoice.pdf",
    "contentType": "application/pdf"
  }
}
~~~

The worker fetches the file via a storage port, checks permissions and file state, and streams the content into the MIME message. The file must remain available until the outbox record reaches completion or retention expires. If the file is deleted too early, the outbox record exists without sufficient data to send.

With object storage, store a version or immutable key so file contents cannot change between outbox creation and sending.

## 17. When to use an event listener, when to use an outbox?

| Need | @TransactionalEventListener(AFTER_COMMIT) | Transactional outbox |
| --- | --- | --- |
| Runs only after DB commit | Yes | Yes, worker only reads committed records |
| Avoids sending on transaction rollback | Yes | Yes |
| Send request survives process crash | Not guaranteed automatically | Yes, record resides in database |
| Retry after SMTP error | Must build durable mechanism separately | Can be implemented via worker and status |
| Multiple workers processing in parallel | Not primary goal | Can claim using locks/leases |
| Operational complexity | Low | Higher; requires table, worker, and cleanup |
| Best suited for | Best-effort side effects | Critical transactional emails needing tracking and retries |

Both can be combined: the outbox row is created inside the transaction, and after commit a wake-up signal notifies the worker to reduce latency. The signal is only an optimization; the worker must still poll or have a recovery mechanism so it does not depend on in-memory events.

Do not use an event listener as the place to insert into the outbox after commit. If the listener crashes before inserting into the outbox, the send request is still lost. Inserting into the outbox must happen inside the initial business transaction.

## 18. Transactional outbox with CDC or polling

There are two common ways to detect new outbox records:

### Polling

A worker periodically queries due PENDING/RETRY_WAIT records. Advantages are ease of implementation and no need for a separate streaming platform. Disadvantages are polling-interval latency and the need to tune queries/indexes, locks, and cleanup.

Polling fits many small- and medium-sized Spring Boot applications. Batch size, worker count, and polling interval should be configured based on email generation rate and SMTP provider capacity.

### Change Data Capture (CDC)

A CDC tool reads the database transaction log and publishes outbox changes to a message broker. Workers consume events from the broker and send emails.

Advantages:

- Near real-time change detection.
- Reduces continuous polling queries.
- Integrates into an existing event-driven architecture.

Disadvantages:

- More complex infrastructure and operations.
- Requires managing offsets, replays, and duplicates.
- Consumers must still be idempotent.
- Must ensure outbox events are processed and retention is managed properly.

CDC does not turn SMTP into exactly-once. It changes how outbox records reach workers; the failure window between SMTP accepted and status update still remains.

## 19. Testing failure windows

To validate transaction and outbox strategies, simulate concrete scenarios:

| Scenario | Expected outcome |
| --- | --- |
| Business transaction rolls back before commit | No outbox row committed; worker sends nothing |
| Business transaction commits successfully | Outbox row exists and worker can claim it |
| Temporary SMTP failure | Record is scheduled into RETRY_WAIT |
| Permanent SMTP failure | Record transitions to FAILED or dead-letter |
| Worker crashes after claim but before send | Lease expires and another worker can reclaim |
| Worker crashes after SMTP accepted but before status update | Risk of duplicate send; system must have idempotency/reconciliation strategy |
| Two workers run simultaneously | One record is not claimed concurrently thanks to locking/leases |
| Template or file reference becomes invalid | Error is classified and recorded without infinite retries |
| Provider sends bounce webhook | Delivery status is updated per provider event |

### Unit/integration testing transactions with the outbox

You can verify the use case creating the record in the same transaction against a test database:

~~~java
@Test
void rollbackDoesNotLeaveOutboxMessage() {
    assertThrows(RuntimeException.class, () ->
        transactionTemplate.executeWithoutResult(status -> {
            orderService.confirm(orderId);
            throw new RuntimeException("force rollback");
        })
    );

    assertEquals(
        0,
        outboxRepository.countByAggregateId(orderId.toString())
    );
}
~~~

The test must use the same transaction manager and database for both the order repository and outbox repository. Calling the service through the Spring proxy ensures transaction annotations apply properly; avoid direct self-invocation on the same instance expecting the proxy to intercept.

### Testing the worker with a fake mail adapter

~~~java
class FakeMailDeliveryPort implements MailDeliveryPort {

    private int attempts;
    private boolean fail;

    @Override
    public void send(OutgoingMail mail) {
        attempts++;

        if (fail) {
            throw new TransientMailException("SMTP unavailable");
        }
    }

    int attempts() {
        return attempts;
    }
}
~~~

Use the fake to verify the worker updates SUBMITTED on successful send and RETRY_WAIT on temporary errors. Separate integration tests can use a test SMTP server to inspect actual MIME output. Production SMTP should not be used in tests.

## 20. Observing and operating the outbox

An outbox is a durable queue inside the database, so its health must be monitored:

- Count of PENDING records.
- Count of PROCESSING records and lease ages.
- Count of RETRY_WAIT records.
- Count of FAILED/dead-letter records.
- Age of the oldest PENDING record.
- Average and p95 attempt counts.
- Latency from created_at to submitted_at.
- SMTP error rate per provider.
- Duplicate rate or indeterminate send outcomes where observable.

Useful alerts:

- PENDING age exceeds SLA.
- PROCESSING records with expired leases spike abnormally.
- RETRY_WAIT grows continuously.
- FAILED exceeds threshold.
- Zero records processed while traffic continues arriving.
- Provider repeatedly refuses connections or rate-limits.

### Cleanup and retention

Do not keep outbox rows indefinitely unless audit requirements demand it. Completed records can be archived or purged after a period defined by operational policy. Before cleanup, ensure provider event/bounce reconciliation has completed if the system tracks delivery status.

Payloads may contain emails, customer names, addresses, or order details. Apply database access controls, retention limits, log masking, and appropriate data deletion processes.

## 21. Common anti-patterns

| Anti-pattern | Consequence | Remedy |
| --- | --- | --- |
| Sending SMTP before commit | Email may notify for a rolled-back transaction | Move to post-commit handling or outbox |
| Sending after commit via sequential call in controller | Process crash between commit and send loses request | Persist outbox inside the transaction |
| Assuming AFTER_COMMIT guarantees no lost events | Default events live only in memory | Use an outbox for durable requirements |
| Using @Async as an outbox replacement | Executor is not a durable queue | Use worker/outbox or durable broker |
| Inserting outbox via REQUIRES_NEW | Outbox may commit even if business logic rolls back | Share the same database transaction |
| Holding DB transaction while sending SMTP | Holds connections/locks during network wait | Claim record and commit before sending |
| Marking SUBMITTED before calling SMTP | Worker crash loses the send request | Update only after send result |
| Assuming retries are always safe | Can send duplicates after ambiguous timeout | Idempotency and reconciliation |
| Treating SMTP accepted as delivered | Reports inaccurate recipient status | Separate submission from delivery events |
| Infinite retries | Queue bloats and repeats permanent errors | Backoff, max attempts, and dead-letter |
| Storing large attachments in JSON payload | Bloats database and backups | Store immutable file references |
| Polling only PENDING, ignoring expired PROCESSING leases | Records get stuck when a worker dies | Lease expiration and reclaim |
| Deleting outbox immediately after submission | Loses investigation/reconciliation ability | Controlled retention and archiving |

## 22. Choosing a strategy by email criticality

Not every email requires an outbox. Decide based on the consequences of a lost or duplicate notification.

| Notification type | Typically suitable strategy | Reason |
| --- | --- | --- |
| Debug/dev email | Local capture or logging | Not a business transaction notification |
| Non-critical report email | AFTER_COMMIT or scheduled job | Can be regenerated or loss is acceptable |
| Order confirmation email | Transactional outbox | Users need to know the transaction was recorded |
| Invoice/document email | Outbox + immutable file reference | Needs content reconciliation and retries |
| Newsletter | Dedicated queue/campaign system | Requires batching, rate limits, and unsubscribe policy |

For security emails such as password resets, retries must check token expiration and account status. Do not resend expired or revoked tokens. An outbox persists the request, but business logic must still verify the content remains valid when the worker processes it.

## 23. Implementation roadmap in a Spring application

A practical roadmap:

1. **Classify email criticality** and the impact of lost or duplicate emails.
2. **Locate existing JavaMailSender calls** inside current transactions.
3. **Separate the mail-sending port** from use cases so adapters and test fakes can be swapped.
4. **For best-effort emails**, consider @TransactionalEventListener(AFTER_COMMIT) with explicit exception handling.
5. **For high-reliability emails**, create an outbox table and write records in the same transaction as business changes.
6. **Build a worker** that claims records in a short transaction, sends outside the transaction, and updates results in a new transaction.
7. **Add leases, retries, backoff, max attempts, and dead-letter handling**.
8. **Use stable idempotency keys** and define how indeterminate SMTP outcomes are handled.
9. **Track SUBMITTED and provider delivery events** if final delivery status is needed.
10. **Test rollbacks, process crashes, SMTP failures, duplicates, and concurrency** in an appropriate environment.

Overall diagram:

~~~text
Business request
      |
      v
BEGIN DATABASE TRANSACTION
      |
      +--> Update business aggregate
      |
      +--> Insert mail_outbox row
      |
      v
COMMIT
      |
      v
Outbox worker claims row
      |
      v
Commit claim / lease
      |
      v
Build email + call MailDeliveryPort
      |
      +---- success ----> Mark SUBMITTED
      |
      +---- transient --> Schedule RETRY_WAIT
      |
      +---- permanent --> Mark FAILED
      |
      v
Provider events (if available)
      |
      +--> DELIVERED / BOUNCED / DEFERRED
~~~

The core principle is that the database transaction records only business state and send intent. The worker performs the side effect after the data has committed.

## 24. Key takeaways

When a transaction commits but email sending fails, the application is coordinating two systems without a shared transaction:

- Sending SMTP before commit can produce an email for a change that later rolls back.
- Sending after commit avoids notifying before data is confirmed, but a process crash can lose the send call.
- **@TransactionalEventListener(AFTER_COMMIT)** suits best-effort side effects; in-memory events are not guaranteed to survive a process crash.
- **@Async** only runs work on an executor; it does not replace a durable queue.
- A transactional outbox writes the send request in the same transaction as business changes so a worker can resume after application restart.
- The outbox row and business data must use the same database transaction manager; avoid **REQUIRES_NEW** for outbox inserts.
- Workers claim in a short transaction, send outside the transaction, and update status in a new transaction.
- Leases recover records when workers die, but a failure window causing duplicate sends still remains.
- An outbox typically provides at-least-once processing; SMTP has no universal idempotency to guarantee exactly-once.
- Use idempotency keys if the provider supports them, record attempts, and reconcile outcomes on ambiguous SMTP timeouts.
- Classify transient/permanent errors, use backoff with jitter, cap attempts, and use dead-letter states.
- SMTP accepted only confirms transport submission; delivered requires provider events or reliable delivery signals.
- Store just enough payload, consider snapshot/versioning, immutable file references, access controls, and retention.
- Monitor outbox age, retries, provider errors, and stuck records for proactive operations.

For critical transactional emails, a transactional outbox is a practical way to keep send requests synchronized with database changes and resume processing after process or SMTP failures. It does not eliminate every possibility of duplicates, yet it provides a durable, stateful record that can be retried and reconciled instead of letting notifications depend on a single network call right after transaction commit.
