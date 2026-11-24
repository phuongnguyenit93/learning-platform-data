# Separating Data Transactions from SMTP Transactions

In a Spring application, updating business data and sending email often occur within the same processing flow. For instance, when confirming an order, the application updates status in the database and then emails the customer. However, these two operations belong to two different systems: the database manages data transactions, whereas SMTP delivers messages to a mail server.

**A database transaction does not include the SMTP transaction.** If the SMTP server has already accepted an email and the database then rolls back, the email can still reach the recipient. Conversely, the database can commit successfully while SMTP sending fails. No single local Spring transaction automatically makes these two outcomes atomic.

Therefore, separate data boundaries from mail-sending boundaries and define how they coordinate. For simple applications, you can commit data first and then call the mail service. For emails that must run after commit, you can use AFTER_COMMIT events. For critical notifications that must survive restarts and support retries, a transactional outbox is usually the right choice.

## 1. Two transaction types with different goals

### 1.1. Data transaction

A data transaction is typically managed by Spring's transaction abstraction and a transaction manager such as DataSourceTransactionManager or JpaTransactionManager.

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    orderHistoryRepository.save(
            OrderHistory.confirmed(orderId)
    );
}
~~~

Database operations inside the same transaction can commit or roll back according to database rules. If updating the order or writing history fails, the transaction can roll back so no partial state remains.

A data transaction cares about the consistency of changes within the same transactional resource.

### 1.2. SMTP sending transaction

SMTP has a sequence of commands to transfer a message to a mail server. At a high level, the client connects, authenticates if needed, declares sender and recipients, transmits content, and receives a response from the server.

~~~text
SMTP client
    |
    +-- Connect / TLS / AUTH
    +-- MAIL FROM
    +-- RCPT TO
    +-- DATA
    +-- Message content
    +-- End of DATA
    |
    v
SMTP server response
~~~

When the SMTP server accepts the message after the DATA step, the server takes responsibility for onward handling per its protocol and policy. This does not mean the message has definitely reached the Inbox or been read by the recipient.

An SMTP session/transaction belongs to the mail protocol's own scope. It is not a JDBC transaction and is not automatically managed by Spring's database transaction manager.

### 1.3. Why are the two transactions not atomic?

An atomic transaction requires a coordination mechanism to commit or roll back all participating resources together. A database can support local transactions on its connection. Standard SMTP servers do not provide an XA resource to join a distributed two-phase commit alongside a database.

Therefore, the following code:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    // Update database
    // Send SMTP email
}
~~~

does not create a distributed transaction spanning both the database and SMTP. The annotation only manages operations supported by the transaction manager; calling JavaMailSender is external I/O.

## 2. Dual-write: database writes and email sending are two independent writes

When one use case both writes to the database and sends email, the application performs two side effects:

1. Writing business state to the database.
2. Sending a message over SMTP.

This is a form of the **dual-write problem**. The two writes do not commit atomically together, so there is always a window where one succeeds while the other has not finished.

### 2.1. Send SMTP first, then commit the database

~~~text
BEGIN database transaction
    UPDATE order -> CONFIRMED
    SMTP accepts confirmation email
COMMIT database transaction
~~~

If commit fails:

~~~text
Database: rollback
SMTP: message was accepted
~~~

The recipient may receive a confirmation email for a change that does not exist in the database.

### 2.2. Commit the database first, then send SMTP

~~~text
BEGIN database transaction
    UPDATE order -> CONFIRMED
COMMIT database transaction

SMTP sends confirmation email
~~~

If SMTP fails:

~~~text
Database: CONFIRMED
SMTP: send failed
~~~

Business state is saved, yet the email was not sent. This is usually the better direction for business correctness: notifications are sent only after changes commit. However, if the process stops between commit and the SMTP call, send intent can be lost if not persisted somewhere.

### 2.3. Failure window table

| Failure point | Database state | SMTP state | Consequence |
| --- | --- | --- | --- |
| Database fails before calling SMTP | Rollback | Not sent | No inaccurate-status email |
| SMTP accepts before database commit fails | Rollback | May have received message | Email reports uncommitted change |
| Database commits, SMTP rejects | Committed | Send failed | Business operation succeeded but notification missing |
| Database commits, process stops before send | Committed | Not sent | Send intent may be lost |
| SMTP accepts, process stops before saving result | Committed | May have received message | Retry may send duplicate |
| SMTP timeout with unknown outcome | Depends on timing | Indeterminate | Retries require caution |

The design goal is choosing ordering and state persistence so failure windows can be detected and handled.

## 3. Do not call JavaMailSender inside the data transaction

A common example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orderRepository,
            JavaMailSender mailSender
    ) {
        this.orderRepository = orderRepository;
        this.mailSender = mailSender;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        sendConfirmation(order);
    }

    private void sendConfirmation(Order order) {
        // Create MimeMessage and call mailSender.send(...)
    }
}
~~~

The problem is not JavaMailSender syntax. The problem is that SMTP is called while the database transaction is still open.

There are three risks:

- Slow SMTP makes the transaction hold connections and locks longer.
- The email may be accepted and the transaction then rolls back.
- An SMTP error may roll back the business operation per rollback rules even though the data could have committed validly.

Do not assume moving the send call into a private method separates transactions. That method still runs on the same thread and inside the caller's transaction.

## 4. Separating the application service and mail service

A clean structure lets the business service update data only, while the mail service handles message delivery only.

~~~text
OrderApplicationService
        |
        v
OrderService
    @Transactional
        |
        +-- Validate
        +-- Update order
        +-- Build mail snapshot
        |
        v
      COMMIT
        |
        v
OrderMailService
        |
        +-- Render template
        +-- Create MimeMessage
        +-- Send via JavaMailSender
~~~

Snapshot DTO example:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount
) {}
~~~

Data service:

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

        // The transactional call has returned after a successful commit.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

Because OrderService is a separate bean invoked through a Spring proxy, the transaction can complete before the facade proceeds. If commit throws an error, the call does not return normally and the facade does not call the mail service.

### 4.1. Why return a DTO?

Do not hold a JPA entity and pass it to the mail service after the transaction. The entity may be detached from the persistence context; lazy relationships may no longer be accessible.

A DTO snapshot captures the exact data needed to build the email when the business action is confirmed. It also keeps the renderer independent of repositories or Hibernate sessions.

### 4.2. Limitations of sequential invocation

This ensures send is called only after the transactional service returns successfully. However, a gap remains:

~~~text
1. Database commit succeeds.
2. Process stops before mailService.sendConfirmation().
3. No email and no persisted work record for retries.
~~~

If the email is merely a convenience notice, this risk may be acceptable. If the notification is an important business requirement, persist send intent in the database or a durable queue.

## 5. AFTER_COMMIT: tying mail sending to successful commit

Spring supports **@TransactionalEventListener** to process events according to the transaction lifecycle.

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
        +-- Publish event
        |
        v
    COMMIT
        |
        +-- Success
        |     |
        |     v
        |  AFTER_COMMIT listener
        |     |
        |     v
        |  SMTP send
        |
        +-- Rollback
              |
              v
        Listener does not run
~~~

The event is published inside the transaction, yet the listener executes only after commit succeeds. If the transaction rolls back, the AFTER_COMMIT listener does not send the email.

### 5.1. Do not use BEFORE_COMMIT for confirmation emails

**BEFORE_COMMIT** runs before the database confirms the commit. The transaction can still fail after the listener. If the listener sends email in this phase, the risk of email sent while data rolls back still remains.

For emails asserting a change was saved successfully, use AFTER_COMMIT.

### 5.2. Events without a transaction

By default, TransactionalEventListener requires an active transaction when the event is published. Without a transaction, the listener may not run.

There is a **fallbackExecution = true** option, but enable it only if business rules allow the listener to run even when the event is not bound to a transaction. Never use this option merely to hide a bug where an event is published across the wrong boundary.

### 5.3. AFTER_COMMIT does not persist events durably

Standard application events live in process memory. If the database commits and the process then crashes before the listener handles the event, the event can be lost.

Thus, AFTER_COMMIT guarantees processing order while the application is running; it does not guarantee a worker will recover events after a restart.

## 6. Offloading SMTP sending to another thread with @Async

If you do not want HTTP requests waiting on SMTP, combine AFTER_COMMIT with **@Async**.

Executor configuration:

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

After commit, the listener hands the task off to the executor. The request-handling thread does not wait for SMTP sending to finish if the calling path does not await the async result.

### 6.1. Three concepts to distinguish

| Mechanism | Responsibility |
| --- | --- |
| AFTER_COMMIT | Processes event only after commit succeeds |
| @Async | Runs processing on another executor |
| Transactional outbox | Persists processing intent durably with the data transaction |

`@Async` does not retry automatically. Tasks in an executor can also be lost when the process stops or rejected if the queue fills up. For critical emails, persist state durably and use a recovery worker.

### 6.2. Do not pass entities to async workers

The worker runs on a different thread and does not inherit the business thread's persistence context. Pass a serializable DTO snapshot, or pass a business ID and let the worker open its own transaction when querying data.

## 7. Transactional outbox: coordinating two transactions with a durable record

When emails must still be processed even after application restarts, use a **transactional outbox**.

Inside the same database transaction, the application:

1. Updates business data.
2. Creates an outbox record describing the email to send.
3. Commits both changes.

~~~text
BEGIN DATABASE TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    INSERT INTO mail_outbox (..., status = 'PENDING')
COMMIT
~~~

After commit, a worker reads the outbox and executes the SMTP transaction in a separate step:

~~~text
Database transaction
       |
       +-- Update order
       +-- Insert outbox event
       |
       v
     COMMIT
       |
       v
Outbox worker
       |
       +-- Claim event
       +-- Render email
       +-- Send SMTP
       +-- Save result
~~~

If the transaction rolls back, both the order update and the outbox row roll back. If commit succeeds, the outbox row remains in the database for the worker to process after a process restart.

### 7.1. Illustrative outbox table

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

A real schema may add template key/version, locale, correlation ID, lease owner, lease expiry, recipient reference, and categorized error type.

The payload should have an explicit DTO/event schema. Do not serialize entire JPA entities into the outbox since entities can contain circular relationships, lazy proxies, and unnecessary data.

### 7.2. Writing to the outbox alongside business data

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

JavaMailSender is not called in this method. The database transaction manages both the order update and the email send intent.

### 7.3. Worker processing the outbox

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

This illustrates the flow. A real implementation needs a claim or lease mechanism so multiple workers do not process the same event concurrently. Separate transactions are also needed for claiming and updating status.

### 7.4. Do not hold a database transaction while waiting on SMTP

The worker should claim events in a short transaction, commit the claim, and then send over SMTP outside that transaction. Once a result is obtained, the worker opens another transaction to update SENT or the retry schedule.

This keeps database locks from being held during network I/O. If the worker crashes after SMTP acceptance but before updating the outcome, the lease can expire and the event gets reprocessed; a duplicate-handling policy is needed.

## 8. SMTP acceptance and database status are two distinct milestones

An email can pass through multiple states:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted --> SENT_TO_PROVIDER
   |
   +-- Temporary error --> RETRY_WAIT
   |
   +-- Permanent error --> FAILED
~~~

State names should accurately describe what the system knows.

| State | Meaning |
| --- | --- |
| PENDING | Send intent has been persisted |
| PROCESSING | Worker has claimed the task |
| RETRY_WAIT | Temporary failure, waiting for next attempt |
| SENT_TO_PROVIDER | SMTP/provider accepted the message per response |
| FAILED | Task cannot proceed per policy |
| DELIVERY_CONFIRMED | Delivery signal received per provider definition |

Do not use SENT to imply the recipient read the email. SMTP acceptance does not prove the message reached the Inbox, avoided spam filters, or was opened by the recipient.

### 8.1. Saving results after calling SMTP

A typical flow:

1. Worker claims event.
2. Sends message.
3. If JavaMailSender returns normally, records SMTP/provider acceptance per transport acknowledgment level.
4. If send throws an error, classifies the error and schedules a retry or marks failed.

Never mark SENT before calling send. If you write SENT and the process crashes before sending, the email is lost while the database records it as sent.

### 8.2. Indeterminate outcomes

If the connection drops while the SMTP server may already have received the content, the application may not know whether the message was accepted.

Retrying may send a duplicate. Not retrying may miss the message if the server never received it. This is a fundamental limit when coordinating a database and SMTP without a shared transaction.

## 9. Outbox provides at-least-once processing, not exactly-once email

Consider the scenario:

~~~text
1. Worker reads PENDING event.
2. SMTP server returns acceptance response.
3. Worker crashes before updating outbox to SENT.
4. Lease expires.
5. Another worker reclaims the event.
6. SMTP receives the message again.
~~~

The recipient may receive two emails. A transactional outbox prevents losing send intent after commit, yet cannot make SMTP and the database commit atomically together.

### 9.1. Stable event IDs

Each send intent needs a stable ID to track the outbox row, log correlation, retry count, send outcome, and operational reconciliation.

Never generate a new ID on each retry of the same intent.

### 9.2. Message-ID does not guarantee deduplication

Emails carry a Message-ID header useful for lookups and reconciliation. However, SMTP servers and email clients are not required to discard duplicate messages merely because they share a Message-ID.

If the provider supports an idempotency key via a proprietary API, use it per the provider's contract. Plain SMTP has no universal exactly-once mechanism.

### 9.3. Idempotency at the business layer

Use a stable event key, for example:

~~~text
ORDER_CONFIRMED:order-1001:version-3
~~~

A unique constraint on the event key prevents creating multiple outbox rows for the same state transition. Workers can also inspect processing status before claiming.

However, database-level idempotency cannot know for sure whether SMTP received the message when a connection drops after DATA. Design content to tolerate duplicate sends and maintain reconciliation workflows.

## 10. Retries and backoff for SMTP transactions

Do not retry continuously in a tight loop. That can overload the SMTP provider, increase rate-limit risk, or create many duplicate emails.

A retry schedule can use exponential backoff:

~~~text
Attempt 1: short wait
Attempt 2: longer wait
Attempt 3: even longer wait
...
Limit reached: FAILED or dead-letter
~~~

Actual intervals depend on error type, SLAs, and provider policies. Add jitter so multiple workers do not retry simultaneously.

### 10.1. Classifying errors

| Error category | Example | Handling approach |
| --- | --- | --- |
| Temporary | SMTP 4xx, server busy, retryable timeout | Backoff and retry up to limit |
| Permanent | Invalid recipient or hard policy rejection | Mark failed, do not retry infinitely |
| Indeterminate | Connection lost after server may have received DATA | Handle cautiously due to duplicate risk |
| Message construction error | Broken template, missing attachment | Fix data/template source before retrying |

Not every MailException shares the same nature. Inspect root causes, SMTP responses, and the failed operation stage.

### 10.2. Attempt limits and dead-lettering

After maximum retries, an event can move to FAILED or dead-letter for operator review. Store the cause, timestamp, attempts, and correlation ID so it can be handled.

Never infinitely retry bad recipients or broken templates. Retries only help when the cause can resolve without changing input data.

## 11. Why not use JTA/XA to combine SMTP and database?

JTA/XA can coordinate XA-capable resource managers in a distributed transaction. For example, two databases or a database and an XA-capable message broker can join a two-phase commit in a suitable environment.

Standard SMTP servers do not expose an XAResource to participate in the application's transaction manager. Enabling JTA does not turn JavaMailSender into a participant that can prepare/commit/roll back together with a database.

Furthermore, distributed transactions carry operational overhead, resource hold times, and their own failure modes. For email, an outbox is usually a far more practical way to persist send intent with data and perform SMTP after commit.

Do not confuse an SMTP protocol transaction with an XA transaction. The word "transaction" in SMTP describes the sequence of commands delivering one message to a server, not a resource that can roll back alongside a database.

## 12. Transaction synchronization as a post-commit callback option

Besides event listeners, Spring offers **TransactionSynchronizationManager** to register callbacks aligned with the transaction lifecycle.

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

The afterCommit callback is invoked only after the transaction commits successfully. Ensure transaction synchronization is active before registering the callback.

### 12.1. Limitations of callbacks

Transaction synchronization still runs in-process. If the process stops after commit before the callback runs, the email may not be sent. It handles execution order, not durability.

If the callback needs to write a new database status, remember the original transaction has already committed. Use a separate bean with **Propagation.REQUIRES_NEW** when a genuinely new transaction is needed for post-commit status writes.

## 13. Exception handling and Spring rollback rules

Under Spring's common default rules, a transaction rolls back when a transactional method terminates with a RuntimeException or Error. Checked exceptions do not automatically trigger rollback under the same default rules unless a matching rollback rule is configured.

~~~java
@Transactional
public void confirmOrder(UUID orderId) throws MessagingException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    mailService.sendConfirmation(order);
}
~~~

If MessagingException is a checked exception and is thrown, the transaction does not necessarily roll back by default. If wrapped in a RuntimeException or configured with rollbackFor, the transaction may roll back.

This affects handling when sending fails, yet does not solve the case where SMTP already accepted the message before another error rolled back the transaction.

### 13.1. rollbackFor does not create a distributed transaction

~~~java
@Transactional(rollbackFor = Exception.class)
public void confirmOrder(UUID orderId) {
    // ...
}
~~~

This configuration changes database transaction rollback conditions. It does not make SMTP a resource that rolls back with the database.

If SMTP already received the message, database rollback still cannot recall the message.

### 13.2. Catching SMTP errors and ignoring them

~~~java
try {
    mailService.sendConfirmation(data);
} catch (MailException ex) {
    log.warn("Cannot send confirmation", ex);
}
~~~

Catching exceptions can stop send failures from rolling back business operations, yet without persisting status and having a retry mechanism, notifications can be lost. Decide whether the email is best-effort or an obligation that must be tracked to completion.

## 14. Organizing snapshots and data for workers

When separating data from SMTP, decide whether the worker receives a snapshot or re-reads the database.

| Data passing approach | Meaning | Best suited for |
| --- | --- | --- |
| Snapshot DTO | Data at the moment the transaction created the event | Order confirmations, invoices, receipts |
| Business ID | Worker reads the latest state | Reminders or notifications needing current data |
| Snapshot + template version | Can rebuild content per chosen version | Emails requiring auditing or reproduction |

Snapshot example:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        BigDecimal total,
        Instant confirmedAt,
        String locale
) {}
~~~

Avoid storing entire entities or unnecessary fields. Outbox payloads can contain personal data, so enforce access controls, retention, and encryption matching application policies.

### 14.1. Where to render templates?

Rendering can run after the transactional service returns, inside an AFTER_COMMIT listener, inside an async worker, or inside an outbox worker.

If the template uses only a snapshot DTO and needs no database access, rendering can run outside the data transaction. If the worker must query data, open a separate read transaction and decide explicitly whether snapshots or latest state are required by business rules.

### 14.2. Do not let the SMTP service own business logic

The mail service should accept prepared data, build MIME, and send. It should not decide whether an order is confirmed unless that is an explicit part of orchestration.

Separating responsibilities allows retrying SMTP without re-executing the entire business flow.

## 15. Business state and mail-sending state should be independent

An order can already be confirmed while the email is waiting to send:

~~~text
Order:
  status = CONFIRMED

Mail delivery:
  status = PENDING
~~~

This is a valid state if business rules define committing the order as the primary outcome while email is a follow-up notification task.

Do not force order status back to PENDING merely because SMTP is temporarily down, unless the business workflow genuinely defines email delivery as a completion precondition.

Track them separately:

| Entity | Example states |
| --- | --- |
| Order | PENDING, CONFIRMED, CANCELLED |
| Mail event | PENDING, PROCESSING, RETRY_WAIT, SENT_TO_PROVIDER, FAILED |

Separating states lets the system show accurately: order confirmed, email unsent or retrying.

## 16. Testing the two transaction boundaries

Tests should verify both the data transaction and SMTP transaction across each failure window.

| Scenario | Expected outcome |
| --- | --- |
| Database rolls back before commit | No send command issued after commit |
| Database commits successfully | Listener/worker permitted to process email |
| SMTP rejects after commit | Business data remains committed |
| Process stops after commit with in-memory AFTER_COMMIT | Event may be lost; tests expose this limit |
| Outbox insert in same transaction then rollback | Neither business update nor outbox row exists |
| Outbox commits then worker restarts | Event persists and can be processed |
| SMTP accepts then worker crashes before marking SENT | Duplicate may occur on retry |
| Two workers process the same event | Claim/lease prevents concurrent processing per design |

### 16.1. Testing AFTER_COMMIT

An integration test should have a real committing transaction to verify the listener runs. A rollback test verifies the AFTER_COMMIT listener does not run.

If the test framework automatically rolls back transactions after each test, the listener may not be called because no successful commit occurred. Explicitly commit in tests that need to verify the AFTER_COMMIT phase.

### 16.2. Testing outbox atomicity

Verify two scenarios:

- Commit: both business row and outbox row exist together.
- Rollback: neither change exists.

This is the single most important property of an outbox. It ensures send intent cannot be separated from committed data changes.

### 16.3. Testing SMTP with a capture server

Use an SMTP capture server in test environments to observe messages without sending to real mailboxes. You can verify recipients, subject, body, attachments, and received message counts.

To simulate the duplicate window, stop the worker after the SMTP capture server receives the message but before the outbox status is updated. When the worker runs again, the test demonstrates why duplicates can still happen.

## 17. Choosing coordination based on requirements

| Requirement | Suitable implementation | Limitation |
| --- | --- | --- |
| Convenience email, occasional loss acceptable | Call mail service after transactional service returns | Process may stop before send |
| Only need to send after commit | AFTER_COMMIT event or transaction callback | In-memory events are not durable |
| Request should not wait on SMTP | AFTER_COMMIT combined with @Async | Tasks may be lost if process stops |
| Critical email needing recovery after restart | Transactional outbox | Possible duplicate sends in failure window |
| Need retries and per-attempt history | Outbox/queue with state and backoff | Requires worker, leases, and operations |
| Email must reflect data at transaction time | Snapshot DTO inside transaction | Requires payload protection and retention |
| Email needs latest state | Worker reloads by business ID | Content may differ from event emission time |

Not every email needs an outbox. Base your choice on the impact of lost emails, required response times, send volume, and worker operational readiness.

## 18. Common mistakes

| Mistake | Why it fails to solve the problem | Remedy |
| --- | --- | --- |
| Sending on the last line of @Transactional | Commit still occurs after method body returns | Send after commit |
| Using @Async directly inside transaction | Task may start before commit | Combine with AFTER_COMMIT or outbox |
| Using BEFORE_COMMIT | Commit can still fail after callback | Use AFTER_COMMIT |
| Using REQUIRES_NEW for mail service | Only opens a new DB transaction; SMTP stays external | Decouple send timing from business transaction |
| Catching exceptions and ignoring | No retry or tracking mechanism | Save error state and retry per policy |
| Assuming outbox guarantees exactly-once | Worker can crash after SMTP accept | Design duplicate handling |
| Passing JPA entities to workers | Entities can be detached/lazy | Pass DTO snapshots |
| Holding transaction while waiting on SMTP | Increases connection/lock hold time | Claim briefly, send outside transaction |
| Marking SENT before send | May record sent even if message never went out | Record outcome after SMTP response |
| Treating SMTP accept as delivery/read | These are distinct milestones | Use states describing actual observed facts |

## 19. Complete architecture example with an outbox

A service structure can look like this:

~~~text
HTTP request / application command
              |
              v
OrderApplicationService
       @Transactional
              |
              +-- Validate command
              +-- Update order
              +-- Build immutable mail snapshot
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
              +-- Save result or retry schedule
              |
              v
         SMTP provider
~~~

Components:

- **OrderApplicationService** manages the business transaction.
- **Mail snapshot** preserves required email data at event time.
- **Outbox repository** stores send intent and status.
- **Outbox worker** claims, retries, and coordinates delivery.
- **Template renderer** generates content.
- **Mail delivery service** builds MimeMessage and invokes JavaMailSender.
- **Monitoring** tracks backlogs, errors, retries, and processing times.

In small applications, you can start by calling a mail service after commit. As reliability needs grow, you can migrate to an outbox without pushing SMTP logic into domain services.

## 20. Key takeaways for separating data transactions from SMTP transactions

**Data transactions** and **SMTP transactions** are two independent scopes. Spring's transaction manager can commit or roll back the database, yet cannot recall an email already accepted by an SMTP server. Sending SMTP inside a `@Transactional` method can dispatch emails before database commit, keep transactions open during network waits, and cause business retries to produce duplicate emails.

Let the business transaction update data and create the snapshot needed for the email, then send after commit. You can invoke the mail service after the transactional service returns, use **@TransactionalEventListener(AFTER_COMMIT)**, or combine AFTER_COMMIT with **@Async**. These separate timing and execution threads, though in-memory events can be lost if the process stops after commit.

For critical emails, persist send intent into a **transactional outbox within the same database transaction**. Workers process the outbox outside the data transaction, record status, retry with backoff, and track stable event IDs. An outbox supports recovery after restarts without guaranteeing SMTP exactly-once; workers can crash after the server accepts the message and before recording SENT, leading to duplicate sends.

Track three outcomes separately: **business data committed**, **SMTP/provider accepted message**, and **email delivered to or read by recipient**. They are not the same state. With clear boundaries, business data maintains consistency while email delivery can be recovered, retried, and reconciled independently.
