# Calling `send` Inside a Transaction and Assuming Email Can Be Rolled Back

A very common mistake when integrating **Spring Framework Mail** into business logic is calling `JavaMailSender.send(...)` inside a `@Transactional` method and assuming that if the database transaction rolls back, the email will also be “retracted”. That assumption stems from a false premise: **Spring's transaction manages the database (or configured transactional resources); it does not turn an external SMTP server into a transaction participant**.

The consequences can be severe: customers receive an “Order confirmed” email even though the order rolled back; the system sends an account activation email for an account that does not exist; or a database-error retry sends two emails to the recipient. Conversely, if sending is deferred until after commit without persisting send intent durably, the process can crash between commit and send, causing the email to never be sent.

This lesson belongs to the **Common Errors** chapter of *Spring Framework Mail* and focuses on **“Calling `send` inside a transaction and assuming email can be rolled back”**. We will analyze ACID boundaries, failure ordering, Spring/Java/Jakarta Mail examples, suitable solutions at different reliability tiers, tests proving rollback does not retract email, and a production operations checklist.

> **Core takeaway:** `@Transactional` does not make an SMTP send a rollbackable action. Even when `JavaMailSender.send(...)` throws no exception, that primarily reflects **transport-level SMTP submission outcome**, not a guarantee that the email reached the Inbox.

## 1. Wrong Example: Email Sent Successfully While the Order Vanishes

Consider a Spring service handling order placement:

```java
package com.example.orders;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orders,
            JavaMailSender mailSender) {
        this.orders = orders;
        this.mailSender = mailSender;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));

        SimpleMailMessage email = new SimpleMailMessage();
        email.setFrom("orders@example.test");
        email.setTo(command.customerEmail());
        email.setSubject("Order confirmed");
        email.setText("Order ID: " + order.getId());

        mailSender.send(email);

        // Example error occurring AFTER SMTP accepted the email:
        if (command.failForDemonstration()) {
            throw new IllegalStateException("Simulated DB rollback");
        }

        return order;
    }
}
```

Suppose the service is invoked through a Spring proxy and the transaction manager has started a database transaction. If the SMTP relay accepts the email and then `IllegalStateException` escapes the method, the transaction rolls back by default for unchecked exceptions. However, the SMTP relay **receives no corresponding rollback command**. The email can still be delivered to the recipient.

```mermaid
sequenceDiagram
    participant R as HTTP request
    participant S as Spring service
    participant DB as Business database
    participant SMTP as SMTP relay
    R->>S: placeOrder()
    S->>DB: BEGIN, INSERT order
    S->>SMTP: Send email over SMTP
    SMTP-->>S: 250 Accepted after DATA
    S->>S: Exception thrown
    S->>DB: ROLLBACK
    S-->>R: Request failed
    Note over DB,SMTP: Order rolled back; SMTP mail not rolled back
```

There is no “undo send” for an SMTP email once accepted by the relay. The recipient may already see the email, or the relay is actively forwarding it while the business database contains no order.

### 1.1. Where Is the Bug?

Spring `@Transactional` is not “broken”. It is honoring its contract: rolling back **database work** owned by the transaction manager. The bug lies in the **business code's assumption** that every side effect inside the lexical scope of an annotated method participates in the transaction.

### 1.2. Transaction Lifecycle Is Not the Same as Method Scope

In standard proxy-based configuration, a call through the proxy to a `@Transactional` method will:

1. Open or join the appropriate transaction.
2. Execute the method.
3. Commit if success conditions hold.
4. Roll back or mark rollback-only when required.

What happens inside the method may include database writes, logging, HTTP calls, SMTP calls, file writes, cache updates, and event publishing. **The Spring transaction manager does not automatically undo every kind of side effect.** Atomically committing two resources requires a dedicated protocol/coordination supported by both sides; standard SMTP does not participate in XA/2PC distributed transactions.

## 2. Database Transactions and SMTP Are Two Separate Systems

### 2.1. Which Transactional Resources Does ACID Protect?

A JDBC/JPA transaction coordinates a database connection and the changes executed via that connection/transaction manager. It provides ACID guarantees according to the isolation level and database capabilities:

- **Atomicity:** grouped database changes commit together or roll back together.
- **Consistency:** data constraints/rules are preserved per contract.
- **Isolation:** concurrent transactions observe one another per isolation level.
- **Durability:** committed changes survive crashes per database guarantees.

Meanwhile, SMTP is a network mail-transfer protocol between client and server. `JavaMailSenderImpl` uses Jakarta Mail to send SMTP commands and MIME content and read replies. SMTP does not accept a JDBC `ROLLBACK` as part of the same transaction.

### 2.2. “Sending Mail” Has Multiple Phases, Not One Atomic Step

A simple SMTP session may pass through:

```text
TCP connect / TLS / AUTH
EHLO
MAIL FROM
RCPT TO
DATA
[MIME content ending with SMTP terminator]
250 2.0.0 accepted by relay
```

The codes carry different meanings:

| Reply / Phase | Meaning | Guaranteed Delivered to Inbox? |
|---|---|---|
| `235` after AUTH | SMTP login succeeded | No |
| `250` after MAIL FROM | Envelope sender accepted | No |
| `250` after RCPT TO | Recipient accepted for current transaction | No |
| `354` after DATA | Server ready to receive content | No |
| `250` **after complete DATA** | Relay accepted message per SMTP submission | **Still no** |
| Delivery webhook/event | Provider reports downstream status per contract | Does not itself prove Inbox placement |

A send call returning normally can generally be understood as successful submission to the configured SMTP relay per client/transport semantics. Downstream delivery still depends on subsequent relays, destination mailbox, bounces, anti-spam policies, and other factors.

### 2.3. A Database Transaction Cannot Retract the Copy at the SMTP Relay

Once the relay has accepted the message, it may already have stored or forwarded it. Rolling back `orders`, `payments`, or `user_accounts` in the database gives no control over the provider's SMTP queue.

A trick like “send a cancellation email after rollback” **is not a rollback**: it is a new compensating action that can fail, arrive late, or be ignored by the recipient. Never turn correction emails into a substitute for atomicity guarantees.

## 3. Failure Windows That Cause Divergence

### 3.1. Send Before Commit, Then Roll Back

```text
T0  BEGIN DB transaction
T1  INSERT order
T2  SMTP returns accepted
T3  UPDATE inventory fails
T4  DB ROLLBACK
T5  Customer receives confirmation
```

This is the clearest case: **the email may exist while the business data does not**.

### 3.2. Slow SMTP Prolongs the Database Transaction

```text
BEGIN
  insert order
  read customer
  connect SMTP ...
  wait TLS/AUTH ...
  upload attachment ...
  wait server reply ...
COMMIT
```

If SMTP takes 10 seconds, the database connection and any locks may be held 10 seconds longer. Under rising traffic:

- The connection pool drains easily.
- Row locks stay held, increasing contention/deadlocks.
- Request p95/p99 latency spikes.
- The API gateway may time out.
- Users retry requests, generating duplicate events.
- An SMTP relay outage can cascade into a database/API incident.

Never use a DB transaction as a general container for long-running network I/O.

### 3.3. SMTP Throws an Exception and Rolls Back the Business Transaction

```text
T0  BEGIN
T1  INSERT order
T2  SMTP connection timeout
T3  MailSendException propagates
T4  ROLLBACK order
```

Here, an email service outage prevents orders from even being created, even though product requirements might only require creating the order and sending mail afterward. This is **coupling between SMTP availability and core business logic**.

Depending on the domain, some flows must fail the entire operation if notification acceptance cannot be guaranteed; yet that requirement should be met by **committing durable intent** or returning a clear error, not by defaulting to synchronous SMTP.

### 3.4. Send Accepted, Yet Client Never Receives Final Reply

```mermaid
sequenceDiagram
    participant App as Spring mail client
    participant Relay as SMTP relay
    App->>Relay: DATA + message content
    Relay->>Relay: Accept message
    Relay--xApp: Final 250 lost
    Note over App,Relay: Client sees timeout; relay may have accepted
```

The client may observe `MailSendException` or a nested timeout, yet **cannot be certain** whether the relay received the message if the reply was lost at that critical moment. Immediate retries can create two emails. Meanwhile, `@Transactional` may roll back the database on the exception, creating a messy state: no order, possibly an email sent, and the client thinking everything failed.

Never classify every timeout as `NOT_SENT`. Preserve an **UNKNOWN** outcome whenever evidence is insufficient.

### 3.5. Commit First, Then Send Directly: The Lost-Email Window

To avoid “sending before commit”, some code flips the order:

```text
DB COMMIT order
  |
  | process crashes before SMTP send
  v
Email never submitted
```

This avoids “email for a rolled-back order” but introduces the inverse bug: **the order exists, while email intent was never persisted**. If sending only lives in RAM/call stack, a restart has no record that the email needs to be sent.

### 3.6. Send Succeeds, Then Status Write Fails

Even with a separate worker:

```text
SMTP accepted
  -> DB update status=SENT fails
  -> worker crashes
  -> recovery sees pending job
  -> SMTP send might be attempted again
```

This is a critical window in every email architecture. A transactional outbox prevents **losing intent**, yet does not by itself guarantee exactly-once SMTP submission. You still need attempt tracking, business-level idempotency, and recovery tailored to outcome certainty.

## 4. `@Transactional` Controls Rollback by Exception Type

By default in standard Spring declarative transactions, unchecked exceptions and `Error` trigger rollback, whereas checked exceptions do not always trigger rollback by default (customizable via `rollbackFor` or other rollback rules). This directly impacts mail-sending errors:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    mailSender.send(...); // MailException is an unchecked exception
    return order;
}
```

If `MailException` escapes the method through the transaction interceptor, the transaction rolls back under default rules. However, if code catches and swallows the exception:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    try {
        mailSender.send(...);
    } catch (MailException failure) {
        logger.warn("Mail failed");
    }
    return order;
}
```

the transaction can **commit** even though the mail failed or its outcome is unknown. That is not necessarily wrong when requirements allow best-effort email, yet critical emails need error recording/retry mechanisms. A `catch` block does not create durable retries on its own.

### 4.1. “Error Inside a Transaction” Does Not Always Mean It Rolled Back

It depends on:

- Whether the exception escaped through the transactional proxy.
- Rollback rules on the annotation/transaction manager.
- Whether the transaction was already marked rollback-only by another resource.
- Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`...).
- Whether the method was called via the Spring proxy or self-invocation.

Never treat “anything throwing inside a `@Transactional` method rolls everything back” as an absolute rule. The truth for this lesson is that **even when the database genuinely rolls back, SMTP never rolls back with it**.

### 4.2. Flush Is Not Commit

JPA `saveAndFlush(...)` or `EntityManager.flush()` pushes SQL to the database earlier, yet the transaction still has not committed. If you call SMTP after flush and the transaction later rolls back, the email can still be accepted by the relay while the data is discarded.

```text
INSERT/FLUSH != COMMIT
SMTP accepted != DB commit
```

Never use `flush()` as a solution to this transaction boundary problem.

### 4.3. Do Not Use `REQUIRES_NEW` as a Cure-All

Setting `propagation=REQUIRES_NEW` on a method that sends SMTP does not turn SMTP into a transactional resource. It only starts a **new database transaction** when invoked through a suitable proxy. If the outer transaction rolls back, the committed inner transaction remains; an accepted SMTP message also remains. This can leave business data even more inconsistent.

Similarly, JDBC nested transactions/savepoints cannot roll back an accepted SMTP message. Use propagation only when there is a clear transaction-isolation reason, never to solve undoing external emails.

## 5. “Quick Fixes” That Do Not Fully Solve the Problem

### 5.1. Simply Switching to `@Async`

A commonly seen pattern:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    asyncMailService.sendOrderEmail(order.id());
    return order;
}
```

```java
@Async("mailExecutor")
public void sendOrderEmail(Long orderId) {
    mailSender.send(...);
}
```

Avoiding request blocking may be achieved when asynchronous execution runs. Yet at least four risks remain:

1. The worker may start **before the caller's DB transaction commits**, causing a query on another connection to miss the order row or see stale state.
2. The caller's transaction does not automatically propagate across threads; `@Transactional` on the request does not make the worker's SMTP call part of the transaction.
3. Tasks held in an in-memory executor queue are lost if the process crashes after business commit.
4. Exceptions in `void @Async` do not return to the caller like synchronous exceptions; dedicated `AsyncUncaughtExceptionHandler`/future/error handling is required, and durable retries are still missing.

`@Async` helps move CPU/I/O off the request thread, yet does not replace **atomic persistence of intent**.

### 5.2. Relying Solely on `@TransactionalEventListener(AFTER_COMMIT)`

Spring supports listeners bound to transaction phases:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@Component
public class OrderMailListener {

    private final JavaMailSender mailSender;

    public OrderMailListener(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        mailSender.send(buildMessage(event));
    }
}
```

By default, when a listener is registered during a committing transaction, the `AFTER_COMMIT` callback runs after a successful commit. If the transaction rolls back, this listener is not invoked for that event. This improves over **sending before commit**, yet lacks durability guarantees:

```text
DB commits order
   |
   | JVM crash / OS kill
   v
AFTER_COMMIT listener never runs
```

Furthermore, in synchronous listener setups, the callback can run on the thread completing the transaction; calling SMTP there still prolongs the request. Making the listener `@Async` reduces blocking, yet queued tasks can still be lost on restart.

**Key point:** `AFTER_COMMIT` means “passed the commit point”, not “added to a durable queue”.

### 5.3. Why Be Careful When a Listener Writes to the Database After Commit?

In Spring transaction synchronization, during the `afterCommit` phase, some transactional resources may remain bound to the thread while transaction completion wraps up. If the callback needs to execute a **new database write that must commit independently**, call another service through a Spring proxy with `PROPAGATION_REQUIRES_NEW` to start a fresh transaction, following Spring's lifecycle guidance.

Example:

```java
@Service
public class MailAuditWriter {

    @Transactional(
            propagation = Propagation.REQUIRES_NEW)
    public void recordAttemptStarted(UUID notificationId) {
        auditRepository.insert(notificationId);
    }
}
```

However, starting a new transaction for auditing **does not make the email part of the transaction** and does not eliminate the crash window between business commit and callback. Production systems should still persist outbox intent inside the original transaction when zero-loss is required.

### 5.4. `TransactionSynchronization.afterCommit` Also Has Limits

A version using the direct callback:

```java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public void scheduleAfterCommit(OrderCreated event) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                mailSender.send(buildMessage(event));
            }
        });
}
```

It gives control over execution timing within the transaction lifecycle. However:

- Registration only works while transaction synchronization is active; do not call it blindly without an active transaction.
- Registering a callback does not persist it durably.
- An SMTP failure can still throw an exception from the callback after the DB already committed.
- A slow mail-sending callback prolongs the response if executed synchronously.
- Side effects inside the callback do not automatically roll back alongside the completed database commit.

Do not use this callback as a guaranteed-delivery mechanism.

### 5.5. `@TransactionalEventListener` Does Not Fall Back Outside a Transaction by Default

Per standard contract, a `@TransactionalEventListener` with `fallbackExecution=false` (the default) only handles events published inside an active matching transaction. Calling the publisher outside a transaction causes the listener to skip execution. Enabling `fallbackExecution=true` allows execution outside transactions, yet solves neither the crash window nor duplicates.

If you want the listener solely to **wake up a worker** after commit, an `AFTER_COMMIT` event can trigger an early poll, while the worker still scans the outbox periodically to recover missed events.

### 5.6. “Sending a Cancellation Email” Is Not a Rollback

Some systems attempt to compensate like this:

```text
Send "Order confirmed"
DB rollback
Send "Sorry, order cancelled"
```

The second email is a **compensating notification** rather than erasing the first email. It can be delayed, fail, or arrive before the confirmation email due to downstream systems. For sensitive items like activation codes or password resets, the harm goes well beyond confusion. Avoid sending uncommitted data in the first place.

## 6. When Is `AFTER_COMMIT` Acceptable?

Not every email demands a full outbox mechanism. For best-effort emails that can safely be skipped on process restarts, the business may accept:

```text
DB commit
  -> AFTER_COMMIT + bounded @Async
  -> SMTP best effort
```

Conditions:

- Business requirements **tolerate** occasional dropped emails.
- Users suffer no severe impact if an email is lost.
- There is no audit/retry commitment across restarts.
- Error monitoring and bounded executors are in place.
- Content does not contain expired tokens or unauthorized data.
- The API never claims guaranteed/delivered without evidence.

For example, a minor cosmetic notification may be best-effort, whereas OTPs, security alerts, invoices, or workflow-critical emails generally require higher reliability. Base the choice on business SLAs rather than blindly slapping `@Async` on everything.

### 6.1. Comparing Solution Tiers

| Approach | Prevents Pre-Commit Send? | Offloads Request Thread? | Survives Crash? | Auditable Retries? |
|---|---|---|---|---|
| Direct send inside `@Transactional` | No | No | No | Not by default |
| `@Async` from transactional method | Not guaranteed | Yes, when proxied right | No | Not by default |
| Synchronous `AFTER_COMMIT` listener | Yes, for tx-bound events | No | No | Not by default |
| `AFTER_COMMIT + @Async` | Yes, for properly phased listener | Yes | No | Not by default |
| Transactional outbox + worker | Yes, when designed right | Yes | **Yes, after DB commit** | Can be built completely |
| Outbox → durable broker → worker | Yes, if relay implemented right | Yes | Yes, per broker/storage contract | Yes, consumer idempotency still needed |

No single annotation provides atomic commit between a database and an SMTP relay.

## 7. Transactional Outbox: Persist Send Intent Alongside Business Data

The most suitable solution for critical business emails is usually a **transactional outbox**. The idea:

> Inside the database transaction, do not send the email. Write **a send-intent record** alongside the business change. After commit, an independent worker reads that record and performs SMTP submission.

```mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant App as Spring service
    participant DB as Database
    participant Worker as Mail worker
    participant Relay as SMTP relay
    Client->>App: Create order request
    App->>DB: BEGIN
    App->>DB: INSERT order
    App->>DB: INSERT mail_outbox(QUEUED)
    App->>DB: COMMIT
    App-->>Client: Order created; mail QUEUED
    Worker->>DB: Claim due outbox job
    DB-->>Worker: Job + lease token
    Worker->>Relay: Send SMTP message
    Relay-->>Worker: Accepted / rejected / unknown
    Worker->>DB: Record attempt and outcome
```

In this model:

- If the business transaction rolls back, **the order and outbox intent roll back together**. The worker has no job to send.
- If the transaction commits, **the order and intent survive together durably**.
- If SMTP is down, the job waits for retry.
- If the worker crashes before sending starts, the job can be recovered.
- If SMTP accepted the message but the worker crashed before recording the result, the outcome may still be uncertain and must be handled explicitly.

An outbox solves **atomicity between business state and send intent**; it does not claim atomicity between intent and SMTP delivery.

### 7.1. Minimal Outbox Schema

An illustrative PostgreSQL table:

```sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    business_event_key VARCHAR(240) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(50) NOT NULL,
    payload_ref VARCHAR(300) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_owner VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    UNIQUE (tenant_id, business_event_key),
    CONSTRAINT ck_mail_outbox_state CHECK (
        state IN ('QUEUED', 'SENDING', 'RETRY_WAIT',
                  'SUBMISSION_ACCEPTED', 'UNKNOWN',
                  'FAILED', 'DEAD_LETTER')
    )
);

CREATE INDEX ix_mail_outbox_due
ON mail_outbox (next_attempt_at, created_at)
WHERE state IN ('QUEUED', 'RETRY_WAIT');
```

This is a sample schema, not mandatory DDL. Depending on the system, you may need `expires_at`, retry category, priority, provider ID, ack/reconciliation flags, and a separate attempts table. `recipient_ref` and `payload_ref` should point to safe/versioned data; never let a temporary URL expire while a job waits for hours.

**Unique business event key** prevents enqueueing two emails when the same request/event is replayed. It does not guarantee two SMTP attempts will be deduplicated by the relay.

### 7.2. Application Service Writes Only to the DB, Never Calling `JavaMailSender`

```java
package com.example.orders;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository mailOutbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository mailOutbox) {
        this.orders = orders;
        this.mailOutbox = mailOutbox;
    }

    @Transactional
    public OrderCreatedResponse placeOrder(
            CreateOrderCommand command) {

        Order order = orders.insertIdempotently(command);

        UUID notificationId = mailOutbox.insertIfAbsent(
                order.getTenantId(),
                "order-created:" + order.getId(),
                order.getCustomerRef(),
                "ORDER_CONFIRMED",
                "v1",
                order.getConfirmationPayloadRef());

        return new OrderCreatedResponse(
                order.getId(),
                notificationId,
                "QUEUED");
    }
}
```

`OrderRepository`, `MailOutboxRepository`, and DTOs are project-defined interfaces/classes. `insertIfAbsent` must rely on a unique constraint and **return the existing row's ID** on conflict rather than returning an unpersisted random UUID. All database writes must participate in the same transaction manager to achieve atomicity.

### 7.3. What Should Be Stored in the Payload?

For invoices, the email may need monetary totals and order details as of issuance time. If the worker reads live order state hours later, content may diverge from the committed business event.

Options:

- Store a validated, versioned immutable snapshot in the outbox.
- Store a reference to an immutable invoice copy/attachment.
- Store template key/version, locale, tenant identity, and recipient reference.
- For TTL-sensitive emails like OTPs, store expiry and check before sending.

Never serialize live JPA entities, `HttpServletRequest`, `InputStream`, or user sessions into a queue for “later use”. They lack a durable lifecycle across transactions/requests and can leak data.

### 7.4. Do Not Delete Intent as Soon as a Worker Sees It

If a worker deletes the outbox row **before sending**, a crash loses the job. If it deletes the row after sending before recording sufficient results/attempt audits, recovery cannot determine what happened.

Maintain explicit states and retention:

```text
QUEUED
  -> SENDING
  -> SUBMISSION_ACCEPTED
  -> RETRY_WAIT -> SENDING
  -> FAILED / DEAD_LETTER
  -> UNKNOWN (when outcome cannot be determined)
```

Guard state transitions conditionally so a stale worker cannot overwrite a newer worker's outcome. Accepted jobs can be compacted later under a retention policy, never deleted immediately inside an HTTP handler.

## 8. Workers Process the Outbox Using Short Transactions

The mail worker can run inside the same Spring Boot application on a dedicated thread/executor or in an independent deployment. What must hold is that **the request path only writes durable intent**, while the worker opens SMTP connections and manages attempts.

A typical cycle:

```text
1. Query due jobs from mail_outbox.
2. Claim a small batch atomically.
3. Commit claim transaction.
4. Resolve payload and compose MIME.
5. Acquire provider rate/connection permit.
6. Call JavaMailSender.send(...) outside DB transaction.
7. Classify SMTP outcome.
8. Commit attempt record and outbox state.
9. Release worker/connection capacity.
```

### 8.1. Why Claim Atomically Instead of `SELECT` Then Send?

Suppose two replicas run the same scheduled job:

```text
Worker A -> SELECT mail_outbox WHERE state='QUEUED'
Worker B -> SELECT mail_outbox WHERE state='QUEUED'
Worker A -> SMTP send mail M
Worker B -> SMTP send mail M
```

Without an atomic claim operation, both can send the same email. `synchronized` inside a single JVM is insufficient across multiple pods.

An example claim in PostgreSQL:

```sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('QUEUED', 'RETRY_WAIT')
      AND next_attempt_at <= NOW()
    ORDER BY next_attempt_at, created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_outbox AS job
SET state = 'SENDING',
    lease_owner = :workerId,
    lease_token = :leaseToken,
    lease_until = NOW() + INTERVAL '2 minutes',
    attempts = attempts + 1
FROM candidate
WHERE job.id = candidate.id
RETURNING job.*;
```

This SQL illustrates PostgreSQL semantics; exact syntax varies by database. A short transaction performs the claim, issues a fresh `leaseToken`, and commits **before** the SMTP call starts. If precise attempt IDs/auditing are needed, insert `mail_attempt` inside the same claim transaction.

### 8.2. Recording Outcomes Guarded by Lease Token

When the worker receives SMTP acceptance, it can update:

```sql
UPDATE mail_outbox
SET state = 'SUBMISSION_ACCEPTED',
    accepted_at = NOW(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :id
  AND state = 'SENDING'
  AND lease_token = :leaseToken;
```

If the update affects 0 rows, the worker lost ownership or the job changed state; do not overwrite blindly. This is **fencing** at the DB state layer.

Still, fencing **does not prevent** an older worker's SMTP request from already having been accepted by the relay. If a lease expires while worker A is still transmitting DATA, worker B might claim and resend, even if A's DB update is later rejected. Use appropriate timeouts/leases, conditional heartbeats, and cautious recovery.

### 8.3. Never Hold a Transaction Open While Sending

Wrong:

```text
BEGIN
SELECT FOR UPDATE outbox row
mailSender.send(...)
UPDATE outbox
COMMIT
```

Better:

```text
DB transaction A: claim + attempt start -> COMMIT

SMTP network call outside DB transaction

DB transaction B: attempt outcome + job state -> COMMIT
```

This avoids holding row locks and database connections across network timeouts, though it does not eliminate uncertainty between DB commits and external side effects. Design explicitly for that limitation.

### 8.4. Attempt Modeling

Alongside the outbox row, record attempts to separate “this notification” from “this send attempt”:

```sql
CREATE TABLE mail_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    provider_id VARCHAR(120),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    category VARCHAR(64),
    smtp_code INTEGER,
    enhanced_code VARCHAR(32),
    provider_message_id VARCHAR(240),
    safe_error_code VARCHAR(100),
    UNIQUE (outbox_id, attempt_number)
);
```

Never store raw SMTP transcripts containing AUTH payloads, recipient lists/PII, or MIME bodies in the attempt table solely for debugging. Error codes/evidence must be scrubbed and kept under controlled access.

## 9. Worker Sending Email with `JavaMailSender`

The transport layer can still use standard Spring Framework Mail. Separating a worker does not force rewriting an SMTP client or adopting a reactive/nonblocking framework.

```java
package com.example.mailworker;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class OrderMailComposer {

    private final JavaMailSender sender;
    private final MailTemplateRenderer templates;

    public OrderMailComposer(
            JavaMailSender sender,
            MailTemplateRenderer templates) {
        this.sender = sender;
        this.templates = templates;
    }

    public MimeMessage compose(OrderMailPayload payload)
            throws MessagingException {
        MimeMessage mime = sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("orders@example.test");
        helper.setTo(payload.recipientEmail());
        helper.setSubject(templates.renderSubject(payload));
        helper.setText(
                templates.renderPlainText(payload),
                templates.renderHtml(payload));

        return mime;
    }
}
```

`MailTemplateRenderer` and `OrderMailPayload` are application abstractions. The worker can compose and then invoke `JavaMailSender.send(mime)` in a separate method.

Important points:

- Composition errors differ from SMTP errors; do not endlessly retry broken templates.
- Workers are authorized to use the appropriate provider's SMTP credentials; never pull secrets from incoming requests.
- If using attachments, resources/streams must remain valid when Jakarta Mail serializes them and be reopenable on retry.
- Do not hold large `MimeMessage` objects or attachment bytes for thousands of waiting jobs in an in-memory queue.
- For templates/versions or invoice snapshots, content must match the committed business intent.

### 9.1. Synchronous Sending Inside a Worker Is Valid

A worker already running on a thread isolated from HTTP can **call synchronously**:

```java
public void submit(MimeMessage mime) {
    mailSender.send(mime);
}
```

Do not nest another `@Async` layer just to make SMTP doubly asynchronous. That can trick the worker into thinking sending finished while the child task is still queued, making ownership/leases, attempt outcomes, and shutdown hard to manage. Isolating the request-thread boundary at the dispatcher/worker with bounded worker concurrency is sufficient.

### 9.2. SMTP Timeouts Must Be Set Explicitly

A Spring Boot example:

```yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${MAIL_SMTP_USER}
    password: ${MAIL_SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
```

Ports and security modes must match the real provider: STARTTLS submission typically uses 587, implicit TLS typically uses 465; never assume the two handshakes are identical. Timeout properties bound blocking on socket steps, yet do not impose a combined deadline across rendering, attachments, network, and DB updates.

### 9.3. Never Use User Request Context Inside a Worker

A worker may run minutes after the request, or even in another process. Never rely on:

- `HttpServletRequest` or HTTP sessions.
- Detached/lazy-loading JPA entities tied to the request transaction.
- `SecurityContextHolder`, which is bound to the request thread.
- Live `InputStream`s from multipart uploads or temp files.
- Stale MDC/correlation contexts without explicit propagation and cleanup.

Instead, store immutable DTOs/payload references, tenant IDs, and appropriate access scopes. The worker acts with service identity, validates tenant scope, and logs correlation IDs for auditing; never serialize long-lived authentication principals or JWTs into a queue.

## 10. Retrying After Errors: Classify Properly Before Resending

Spring `JavaMailSender` can throw common `MailException` types:

| Exception / Signal | Initial Meaning | Appropriate Decision |
|---|---|---|
| `MailParseException` | Invalid message/address | Fix input; do not retry identical payload endlessly |
| `MailPreparationException` | Error building MIME/resources | Distinguish template/config bugs from transient storage issues |
| `MailAuthenticationException` | SMTP AUTH failed | Pause provider account, inspect credentials |
| `MailSendException` | SMTP submission failed for one/some messages | Read nested SMTP details, classify by phase |
| Confirmed SMTP 4xx | Temporary rejection | Retry with backoff/quota policy |
| Clear permanent SMTP 5xx | Rejection/config/recipient error | Classify scope before suppressing |
| Timeout after DATA | Possibly accepted, reply lost | `UNKNOWN_OUTCOME`/reconciliation |

Never run `exception.getMessage().contains("550")` and hard-suppress all recipients. `550 5.1.1` at `RCPT TO` differs from `550 5.7.1` relaying/sender restriction. The same primary code can mean different things depending on provider, phase, and enhanced status code.

### 10.1. Retrying Does Not Mean Sleeping on a Worker Thread

Anti-pattern:

```java
while (true) {
    try {
        mailSender.send(mime);
        break;
    } catch (MailException failure) {
        Thread.sleep(60_000);
    }
}
```

This snippet has no retry budget, makes no distinction for permanent failures, and ties up the worker thread while waiting. If thousands of jobs hit 451 at once, the system exhausts threads and causes a retry storm.

Better worker pattern:

```text
attempt #1 -> SMTP 451 temporary
  -> record attempt
  -> state RETRY_WAIT
  -> nextAttemptAt = now + backoff + jitter
  -> free worker slot

later dispatcher -> claim when due -> attempt #2
```

Enforce `maxAttempts`, TTL/deadline, capped exponential backoff, jitter, and provider quotas. If the provider exhausted its daily quota, retrying every few seconds is futile. Once SMTP accepts, do not keep retrying just because a delivery webhook hasn't arrived yet.

### 10.2. `UNKNOWN` Does Not Mean Definitely `FAILED`

Separate:

- `NOT_STARTED`: SMTP never opened; evidence confirms no attempt occurred.
- `TEMPORARY_REJECTED`: relay temporarily rejected, with code and phase.
- `PERMANENT_REJECTED`: relay rejected per solid evidence.
- `SUBMISSION_ACCEPTED`: relay accepted at the submission boundary.
- `UNKNOWN_OUTCOME`: cannot tell whether accepted or rejected.

When outcome is `UNKNOWN`, action depends on duplicate tolerance. You can query a provider lookup API if IDs and contracts support it; otherwise mark for reconciliation/manual review or retry with explicit duplicate awareness. `Message-ID` is not an exactly-once deduplication mechanism across SMTP relays.

### 10.3. Durable Retries Differ from In-Memory Retries

`RetryTemplate` or `@Retryable` can help with brief transient errors, yet they do not survive process restarts and can repeat side-effecting operations. For longer retries, store `nextAttemptAt` in the outbox. Wrap retries only around steps with clear semantics that are safe to repeat.

### 10.4. When Providers Enforce Quotas

Limits can include messages/sec, recipients/sec, concurrent SMTP connections, daily quotas, and MIME size. Worker thread count alone does not enforce all of these limits.

Hypothetical provider example:

```text
messagesPerSecond        = 10
maxConcurrentConnections = 4
```

Even with only 4 worker threads, fast calls can exceed 10/sec. Conversely, a 10/sec rate limiter can still open more than 4 concurrent connections if calls are slow. Use **separate rate limiters and concurrency caps** when providers enforce both limits. Multiple pods sharing an account must apply quotas **cluster-wide**, not just per JVM.

## 11. Why Does a Transactional Outbox Still Need Idempotency?

The outbox pattern provides “intent persisted at least once; attempts may execute more than once”. It prevents lost intent, yet duplicates can still happen:

```text
Worker A CLAIMS outbox M
Worker A SENDS M
Relay ACCEPTS M
Worker A crashes before storing SENT
Lease expires
Worker B retries M
Recipient may receive another copy
```

From a systems perspective, SMTP sends and DB writes have no shared atomic commit, so outboxes alone cannot guarantee exactly-once delivery.

### 11.1. Separate Two Deduplication Layers

| Layer | Key | What Does It Prevent? |
|---|---|---|
| HTTP request | `(tenantId, idempotencyKey)` | Client retries creating duplicate business actions |
| Business event | `(tenantId, orderId, eventType)` | Same event enqueueing two notifications |
| Mail outbox attempt | `(notificationId, attemptNumber)` | Consistent attempt history recording |
| SMTP provider API (if supported) | Provider-defined idempotency key | May deduplicate submissions per provider contract |
| User/consumer | Email business semantics | Reduces harm if a notification appears twice |

Never use a random attempt ID as a business idempotency key: every retry gets a new ID, failing to deduplicate the event. For order confirmation emails, key off the verified order ID/event type enforced uniquely in the database.

### 11.2. Partial Recipients

One SMTP message can carry multiple `RCPT TO` recipients; a provider/client may accept some and reject others. Retrying the whole batch can duplicate mail to already-accepted recipients. When exact per-recipient retries are needed, create one notification per recipient or track recipient-level SMTP outcomes under a clear contract.

### 11.3. Business Commands Must Be Safe If a Recipient Gets Two Emails

Some emails include links that may be clicked multiple times. Order/payment activation links must not repeat side effects on every click when business rules allow only one execution. Tokens and receiving endpoints need idempotency, expiry, authorization, and replay protection. That is a separate safety layer outside mail transport.

## 12. Separating Request Threads and Bounded Worker Pools

After the application service writes to the outbox, the worker need not run on the HTTP request thread. A Spring Boot configuration often uses a dedicated executor:

```java
package com.example.mailworker;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class MailWorkerConfiguration {

    @Bean(name = "mailWorkerExecutor")
    ThreadPoolTaskExecutor mailWorkerExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("mail-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        return executor;
    }
}
```

This example uses 4 workers and 16 queue slots, **not** a universal capacity recommendation for every provider. Tasks with long retry backoffs must never sleep inside these slots. When the executor fills up, enforce a clear policy: jobs remain in the DB, and the dispatcher never drops durable intent.

### 12.1. Never Claim More Than You Can Process

Another mistake is claiming 10,000 rows from the outbox and dumping them into a 4-worker executor. Jobs sit in the JVM queue so long that leases expire before SMTP even begins, causing duplicate claims.

The dispatcher should:

1. Claim only when permits/in-flight capacity are available.
2. Use small batches matching concurrency.
3. Commit claims before submitting, or keep transactions/compensation consistent.
4. On executor rejection, release/reset the job using the lease token.
5. If the process crashes after claiming, lease/recovery ensures jobs are not lost.

A local semaphore bounds a single dispatcher's concurrency, yet does not control total concurrency across replicas. Account-level SMTP rate limiting must apply at the real scope, often cluster-wide.

### 12.2. Bounding Queue Memory

A queue of 100 tasks is not small if each task holds an 8 MB attachment—roughly 800 MB of raw bytes before MIME encoding/buffers and other heap usage. Queue **job IDs or immutable references**, never `MimeMessage`s, requests, sessions, or large attachment bytes.

### 12.3. What Should the API Response Reflect?

For an order-creation request, it can return:

```text
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": "ORDER-1042",
  "notificationId": "MAIL-8821",
  "emailStatus": "QUEUED"
}
```

If an API solely accepts an asynchronous notification request, HTTP `202 Accepted` with a tracking ID is appropriate. Never return `emailStatus=DELIVERED` right after inserting into the outbox.

A status endpoint might expose:

```text
QUEUED -> SENDING -> SUBMISSION_ACCEPTED
                  -> RETRY_WAIT -> SENDING
                  -> FAILED / DEAD_LETTER
                  -> UNKNOWN
```

If the provider supports webhooks, store delivery states separately—such as delivered/bounced/deferred—per provider semantics. “Delivered” from a provider still does not guarantee Inbox placement.

### 12.4. Web and Worker Can Be Deployed Separately

Initially you can run in the same Spring Boot app with a separate executor. As traffic or isolation needs grow:

```text
Web nodes:
  validate request
  commit order + mail intent
  return HTTP response
  no SMTP credentials needed when separated

Mail worker nodes:
  claim outbox jobs
  compose and submit SMTP
  persist attempt results
  monitor quotas and retries
```

A separate worker deployment lets you scale by backlog/SMTP quota, keep SMTP credentials and egress permissions off web nodes, and restart workers without impacting the API. However, **splitting services** does not change the lack of atomicity between SMTP and DB; it simply makes the boundary explicit.

## 13. Graceful Shutdown and Hard Kills

During deployments or scale-downs, workers may have:

```text
3 SMTP sends active
20 jobs in local executor queue
5000 jobs pending in database
```

A safe shutdown should:

1. Stop claiming new jobs.
2. Allow active attempts to finish within a reasonable grace period.
3. Persist results when possible; otherwise let lease/recovery handle them.
4. Never discard pending outbox jobs.
5. On restart, workers recheck status and quotas before attempting new sends.

Spring's `ThreadPoolTaskExecutor` provides settings to wait for tasks and await termination, yet **cannot** guarantee completion under OS kills, OOMs, power loss, or hard process termination. Therefore, durability lives in the outbox database, not in shutdown hooks.

### 13.1. Recovery Is Not Resetting Every `SENDING` Row to `QUEUED`

A scheduled reaper can find `SENDING` rows where `lease_until < NOW()`. Yet if a worker died after SMTP acceptance and before the DB update, blind retries can cause duplicates.

Classify based on attempt history:

| Observed State | Safe Recovery Action |
|---|---|
| Claimed with evidence SMTP never opened | Requeue after lease expiry |
| SMTP AUTH clearly rejected | Pause account, fix config |
| Temporary SMTP 451 response recorded | Backoff/retry per policy |
| SMTP 250 accepted and result committed | Do not resend |
| Final reply or DB result commit lost | `UNKNOWN`, reconciliation/duplicate policy |

Network state from an attempt is not always fully observable. When evidence is missing, preserve uncertainty rather than fabricating a false “not sent” certainty.

### 13.2. Rolling Deploys Can Change Templates and Payload Schemas

If an outbox job was created by web app version A and processed by worker version B after deployment, ensure:

- Explicit template key/version.
- Payload schema version.
- Attachment references remain valid and accessible.
- DB migrations stay backward-compatible with queued jobs.
- Old templates are not deleted while backlog remains.
- Worker rollback strategies do not trigger duplicate sends.

Never treat an outbox row as a temporary function call: it is a **data contract** across producer/consumer versions.

## 14. Alternatives and When to Choose Them

### 14.1. Message Broker with Durable Consumers

Some systems push mail jobs through RabbitMQ, Kafka, or equivalent queues. This fits high-throughput workloads or broker-centric architectures, provided two boundaries are addressed:

- **DB → broker boundary:** if the business DB commits and broker publish fails, events can be lost. Transactional outbox + relay/CDC solves this.
- **Broker → SMTP boundary:** a consumer can achieve SMTP acceptance and crash before acking the broker, triggering redelivery. Duplicate risks remain, requiring idempotency/reconciliation.

Never confuse broker durability with end-to-end exactly-once SMTP.

### 14.2. Is Synchronous Sending Ever Appropriate?

Yes, in certain internal/testing tools—for instance, an admin UI triggering a test email and wanting immediate SMTP acceptance/rejection feedback. Still:

- Never call it inside an open business database transaction.
- Enforce timeouts, rate limits, and auditing.
- Report the result accurately as SMTP submission, not delivery.
- Account for users clicking retry on timeout.

If business logic strictly requires blocking until send before returning a response, design explicit compensation between DB and SMTP divergence; never assume automatic rollback.

### 14.3. Database Outbox vs. Durable Queue?

Selection criteria:

| Criterion | DB Outbox | Durable Broker / Queue |
|---|---|---|
| Atomic with business DB writes | Natural within the same transaction | Requires outbox relay or coordination protocol |
| Retry schedule/state | Custom SQL/poller design | Depends on broker features/delay queues |
| Auditing by business key | Easy DB joins | Needs extra metadata/store |
| Throughput scaling | Bounded by DB and claim optimization | Brokers often suit high fan-out/load |
| Redelivery | Lease/reclaim | Broker ack/nack/rebalance |
| SMTP exactly-once | Not provided automatically | Not provided automatically |

No single option fits every case. Yet for the bug *sending inside a DB transaction and assuming rollback*, the invariant is **never treat SMTP as a reversible database operation**.

## 15. Testing to Prove Rollback Does Not Retract Email

This lesson becomes much clearer when testing two independent facts:

1. The database rolls back after an exception.
2. The SMTP test relay already received the message before rollback.

### 15.1. Test with an SMTP Sandbox Instead of Real Mail

Use an SMTP test server like **GreenMail** or **Mailpit**, pointing `JavaMailSenderImpl` to the local test port. Goal:

```text
BEGIN DB transaction
INSERT order
JavaMailSender.send(test email)
SMTP sandbox accepts email
throw RuntimeException
DB ROLLBACK

Assertions:
  DB has no new order
  SMTP sandbox received one email
```

Never send mail to real customer addresses to demonstrate this bug. Sandboxes/localhost make the experiment controlled and repeatable.

### 15.2. Using `TransactionTemplate` for Explicit Boundaries

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.transaction.support.TransactionTemplate;

class SendInTransactionRollbackIT {

    private final TransactionTemplate tx;
    private final OrderRepository orders;
    private final JavaMailSender sender;
    private final TestSmtpInbox smtpInbox;

    SendInTransactionRollbackIT(
            TransactionTemplate tx,
            OrderRepository orders,
            JavaMailSender sender,
            TestSmtpInbox smtpInbox) {
        this.tx = tx;
        this.orders = orders;
        this.sender = sender;
        this.smtpInbox = smtpInbox;
    }

    @Test
    void rollbackDoesNotRetractAcceptedSmtpMail() {
        assertThrows(IllegalStateException.class, () ->
                tx.executeWithoutResult(status -> {
                    orders.insertTestOrder("ORDER-1");

                    SimpleMailMessage mail = new SimpleMailMessage();
                    mail.setFrom("test@example.test");
                    mail.setTo("recipient@example.test");
                    mail.setSubject("Order created");
                    mail.setText("ORDER-1");
                    sender.send(mail);

                    throw new IllegalStateException("rollback");
                }));

        assertFalse(orders.exists("ORDER-1"));
        assertEquals(1, smtpInbox.receivedCount());
    }
}
```

This is an **illustrative integration test skeleton**: `OrderRepository` and `TestSmtpInbox` are project-implemented fixtures; run with a real Spring test context, real database transaction manager, and SMTP sandbox, using bounded waits if needed for the SMTP server to record the message. If `smtpInbox` is only a mock, the test does not verify wire-level SMTP behavior.

Do not wrap the test method itself in `@Transactional`, which obscures real commit/rollback behavior; keep setup/cleanup and transaction boundaries explicit.

### 15.3. Inverse Test: On SMTP Exception, Does the DB Commit or Roll Back?

With the original code, if `MailSendException` escapes `@Transactional`, the database rolls back under default unchecked-exception rules. If code catches and returns normally, the database commits.

Two tests should verify **your application's policy**, rather than relying on assumptions:

```text
Case A: mail exception propagates
  DB rows = 0 (when rollback rule applies)
  Email accepted? may be UNKNOWN depending on phase

Case B: mail exception caught and swallowed
  DB row = 1 (unless marked rollback-only)
  Durable mail retry? none unless implemented
```

Never turn Case B into a production solution merely by adding logging. If the email matters, you need outbox/job state, retries, and alerting.

### 15.4. Testing `AFTER_COMMIT` Still Leaves a Crash Window

An integration test can verify the listener does not run on rollback and runs after a successful commit. Yet it **does not prove** the callback survives process crashes. To test durability, terminate the process after DB commit and before callback/worker dispatch in a controlled environment, restart, and confirm the outbox job still exists.

Never equate “the listener ran in a normal test” with guaranteed delivery when a host is killed.

## 16. Testing the Transactional Outbox as an Independent System

An outbox test must prove a **fundamentally different property** from the SMTP rollback test:

> When the business transaction rolls back, no email intent is committed; when the transaction commits, intent persists for workers to process even if SMTP fails or the JVM restarts.

### 16.1. Order and Outbox Roll Back Together

Scenario:

```text
BEGIN transaction
INSERT orders(order_id=ORDER-2)
INSERT mail_outbox(business_event_key=order-created:ORDER-2)
THROW RuntimeException
ROLLBACK
```

After rollback:

```text
orders row count for ORDER-2 = 0
mail_outbox row count for event = 0
SMTP attempts = 0
```

This is how the outbox enforces “never send confirmation for uncommitted data”, provided the dispatcher only processes **committed** jobs and no legacy synchronous send path remains active.

### 16.2. Commit Intent, Then Make SMTP Unavailable

Scenario:

1. Let the business transaction commit the order and outbox row.
2. Stop the SMTP test server or make a fake transport throw connection errors.
3. Have the worker claim and attempt one send.
4. Verify the job transitions to `RETRY_WAIT` (or policy-defined state) with an attempt record and `nextAttemptAt`.
5. Restart the worker or SMTP server.
6. Only when due does the worker claim again; the order-creation API **never** needs to rerun.

An SMTP outage must never wipe out a committed order or force the API to hold request threads until mail succeeds.

### 16.3. Two-Worker Claim Test

Run two worker instances against the same PostgreSQL database:

```text
Exactly one outbox row is due.
Worker A and Worker B try claim concurrently.
Only one receives valid lease token.
Other sees no eligible row or a different row.
```

Never rely solely on `synchronized` or an in-memory fake repository to prove multi-replica safety. Test atomic claiming against a production-equivalent database with real unique constraints and transaction isolation.

### 16.4. Fault Injection by Timing

| Simulated Crash Point | What to Verify |
|---|---|
| Before business DB commit | Neither business record nor outbox intent exists |
| After business commit, before worker wakeup | Outbox job remains `QUEUED` across restart |
| After claim, before SMTP connect | Lease/recovery can retry when safe |
| During SMTP DATA | Cannot always assert `NOT_SENT` |
| After SMTP accepted, before DB result commit | `UNKNOWN` risk/attempt history; job not deleted |
| After `SUBMISSION_ACCEPTED` commit | Restart does not resend that notification |
| After downstream provider bounce | Submission history remains accepted; delivery outcome separate |
| When dispatcher executor rejects | Job remains in durable storage without loss |
| On worker hard kill | Lease recovery/alerting; no reliance on graceful shutdown |

The key measurement is **the count of business effects and notification intents**, not how many times a Java method ran. A worker may re-execute the same job, while database business keys enforce policy deduplication.

### 16.5. Do Not Confuse Testing with an Exactly-Once Guarantee

Running ten thousand test iterations without duplicates only shows your test scenarios did not expose a race. It does not erase SMTP's fundamental limits. When a socket times out after DATA and the final reply is lost, a client has no general SMTP mechanism to prove “sent” vs. “not sent”. Tests must preserve the `UNKNOWN` state in such cases.

## 17. Observability: Investigating Divergence Between DB and Email

When receiving a report like “a customer got an email for a non-existent order”, the system must trace from business key to transaction outcome and SMTP attempt:

```text
httpRequestId
  -> orderId / businessEventKey
  -> outboxNotificationId
  -> attemptId + providerId
  -> SMTP response phase/code
  -> downstream delivery events
```

If legacy code sent mail inside a transaction without an outbox, a notification ID may be missing. Logs and SMTP/provider traces must then reconstruct the timeline, never inferring “commit succeeded” just because the relay accepted.

### 17.1. Metrics to Monitor

| Group | Metric / Signal | Question Answered |
|---|---|---|
| HTTP | Request latency p50/p95/p99, 5xx | Is SMTP stalling requests? |
| DB | Transaction rollback count, lock wait, connection pool usage | Are transactions held open? |
| Outbox | `QUEUED`/`RETRY_WAIT`/`SENDING` counts | What state is the backlog in? |
| Outbox | Oldest due age | Are emails breaching SLA? |
| Dispatcher | Claims/s, conflicts, failed claims | Are workers making progress? |
| Worker | Active threads, queue depth, rejections | Is capacity saturated? |
| SMTP | Attempts/s, p95 duration, 4xx/5xx/auth/timeout | Is the relay healthy? |
| Retry | Attempts per notification, next-attempt delay | Retry storm or prolonged errors? |
| Recovery | Expired leases and `UNKNOWN` outcomes | Are crash/uncertain windows rising? |
| Downstream | Deferred/bounce/complaint per provider | Are messages failing post-submit? |
| Business | Duplicate event conflict count | Is idempotency blocking duplicate requests? |

### 17.2. Logs Must Avoid Sensitive Data

```text
event=mail_attempt_finished
notificationId=MAIL-8821
attemptId=ATT-3
businessEventType=ORDER_CREATED
providerId=primary
smtpPhase=AFTER_DATA
outcome=UNKNOWN
safeReasonCode=SMTP_REPLY_TIMEOUT
```

Never log raw MIME bodies, Bcc lists, OTPs, reset links, attachment bytes, or SMTP AUTH exchanges. SMTP debug flags can print protocol data outside the logging framework; enable them only with strict scope, duration, access controls, and data scrubbing.

`notificationId` and `attemptId` belong in logs/traces, generally not as Prometheus metric labels due to high cardinality.

### 17.3. Business-Meaningful Alerts

A single SMTP 451 error rarely warrants paging. However:

- Rising SMTP 451s with oldest due age breaching SLA.
- Many requests rolling back after synchronous SMTP calls.
- Many `SENDING` leases expiring and `UNKNOWN` attempts.
- Provider auth failures across the whole account.
- Workers stopping claims while the outbox holds due jobs.
- Rising executor rejections with fallback running SMTP on request threads.

all warrant investigation. Scope alerts by account/provider/tenant and prioritize real impact.

## 18. Runbook: Customer Received an Email for a Rolled-Back Order

### Step 1 — Verify the Two Independent Facts

Gather evidence:

- Did the business record commit or roll back? Are there transaction rollback logs/DB audits?
- Did the SMTP relay accept submission or only begin DATA?
- Are there downstream provider events and correlation IDs?
- Was the email from an earlier request, another retry, or a legacy code path?

Never assume an email proves an order exists, or a rollback log proves no email was sent.

### Step 2 — Locate the Code Path Actually Calling `send`

Inspect the application-layer call graph:

```text
Controller
 -> Service @Transactional
 -> Repository writes
 -> JavaMailSender.send
 -> more DB writes / commit
```

If `send(...)` occurs before commit, that is the core failure mode. If sending occurs in an `AFTER_COMMIT` listener, the bug may be missing durability or a post-commit client timeout; analyze accordingly.

### Step 3 — Construct a Timeline Using IDs

Order the events:

```text
request_received
db_transaction_started
smtp_attempt_started
smtp_accepted
db_transaction_rolled_back
request_failed
```

With multiple replicas, synchronize clocks operationally and use trace/transaction IDs where available; log timestamps alone are unreliable for ordering under clock skew.

### Step 4 — Stop Ongoing Impact

Depending on severity:

- Disable the in-transaction sending path via a controlled feature flag.
- Temporarily pause flows sending sensitive/misleading content.
- Avoid blindly retrying failed requests when idempotency is not yet guaranteed.
- Add monitoring for business-state/email mismatches.
- If customer outreach is required, send approved communications rather than blasting an unverified “apology” template.

### Step 5 — Fix the Architecture

Transition to:

```text
Business transaction:
  apply business changes
  insert outbox intent
  commit

Worker:
  claim after commit
  compose/send SMTP
  track outcomes
```

Write tests covering rollback, commit, crashes, retries, and unknown outcomes before rollout. During migration, ensure **two routes (legacy synchronous + new worker) never send for the same event**.

### Step 6 — Postmortem

Verify business event counts, outbox intents, and SMTP attempts align per policy; review duplicate/unknown cases and customer-support outcomes. Document root cause, blast radius, and new guardrails.

## 19. Specific Case Studies

### Case A — Account Registration Fails After Sending Email

```text
User registration BEGIN
INSERT pending user
Send verification link -> relay accepts
Unique constraint violation in later DB update
ROLLBACK
```

The user receives a link to a non-existent account. Clicking the link must never accidentally create the account; the verification endpoint must validate business state and token per policy. Fix by committing user + email intent atomically and sending from a worker after commit.

### Case B — Invoice Sent, Then Transaction Hits Deadlock

```text
BEGIN
INSERT invoice
SMTP accepted invoice PDF
Database deadlock -> rollback
Request retry -> new send attempt
```

The customer may receive two invoices while the first invoice rolled back. Do not fix this merely by increasing DB retry counts; pull SMTP out of the transaction and add a unique business key and outbox.

### Case C — Order Commits Successfully, Yet Response Fails

```text
BEGIN
INSERT order + outbox intent
COMMIT succeeds
HTTP connection closes before client receives response
Client retries POST
```

The outbox preserves intent, yet request retries still need an idempotency key to avoid creating a second order/event. This boundary is **HTTP ↔ DB**, distinct from SMTP ↔ DB, and is solved by application idempotency.

### Case D — `AFTER_COMMIT` Listener Throws `MailSendException`

```text
Business transaction COMMIT successful
AFTER_COMMIT listener calls SMTP
SMTP failure -> exception
Caller sees error, may retry request
```

The business transaction **already committed**; an exception inside the callback does not turn the prior commit into a rollback. Report status accurately so callers do not assume “the order wasn't created”. For reliable mail, write to an outbox inside the transaction and retry via workers instead of relying solely on synchronous callbacks.

### Case E — `@Async` Runs Before Caller Commits

```text
Request: INSERT order within transaction
Request: schedule async send(orderId)
Worker: SELECT order by ID -> not found
Request: COMMIT order
```

The worker may miss the uncommitted row due to isolation. Adding a 500 ms sleep to the worker only masks the race condition without guaranteeing commit completion. `AFTER_COMMIT` avoids this race yet lacks durability; an outbox solves both timing and crash loss per contract.

### Case F — Sending an OTP After It Already Expired

```text
DB commits OTP + email outbox
SMTP provider throttled for 10 minutes
OTP TTL = 5 minutes
```

The worker must check expiry before submission; if expired, mark `EXPIRED` and let the user request a fresh code safely. An outbox does not mean sending **everything** regardless of staleness.

### Case G — SMTP Accepted, Yet DB Status Update Fails

```text
Worker sends mail
Relay returns 250 accepted
DB unavailable before update accepted_at
Worker terminates
```

Recovery cannot tell the status for sure. Resending risks duplicates; skipping risks drops if replies were misinterpreted. You need attempt state, reconciliation/duplicate-risk policies, and auditing; there is no one-size-fits-all decision across every domain.

## 20. Common Misconceptions

**“Anything called inside `@Transactional` can be rolled back.”** False. The transaction manager manages enlisted resources; an SMTP relay does not automatically join a JDBC/JPA transaction.

**“If SMTP returns 250 and the DB rolls back, an email-retract command is sent.”** There is no SMTP email rollback equivalent to JDBC `ROLLBACK` once the relay accepts.

**“Send mail before commit to make sure the email arrives before saving the order.”** That creates a state where the email was sent yet the order does not exist. If the DB fails to commit, SMTP cannot erase its result.

**“If `MailSendException` occurs, the email was definitely not sent.”** After DATA, the reply may be lost even though the relay accepted; the outcome may be `UNKNOWN`.

**“If `send` throws no exception, the recipient definitely sees it in their Inbox.”** Accepted submission does not guarantee downstream delivery or Inbox placement.

**“Flushing the database before `send` means the DB is committed.”** JPA flush does not replace commit. The transaction can still roll back after flush.

**“Switch propagation to `REQUIRES_NEW` so SMTP joins the transaction.”** Propagation only coordinates database transactions per contract; it does not give SMTP rollback semantics.

**“Catching `MailException` and returning is enough.”** That lets the DB commit while email intent remains non-durable; you lose retries and auditing on process restarts.

**“`@Async` always runs after commit.”** A worker may be scheduled and execute before the caller's transaction commits, depending on executor timing.

**“`@Async` passes the transaction to the worker thread.”** Spring's thread-bound transactions do not automatically cross threads; external SMTP still does not join the DB transaction.

**“`@TransactionalEventListener(AFTER_COMMIT)` guarantees mail cannot be lost.”** It prevents pre-commit sending, yet still leaves a crash window between commit and callback. Synchronous sending in the listener also prolongs responses.

**“An `AFTER_COMMIT` callback throwing an error rolls back the just-completed commit.”** The transaction already committed; the caller may see an error, yet the database does not revert.

**“An in-memory queue alone is durable.”** Tasks vanish on JVM crashes, restarts, or hard kills.

**“A message broker automatically makes DB+SMTP exactly-once.”** Both DB→broker and broker→SMTP have failure boundaries to handle; broker redelivery is normal.

**“A transactional outbox guarantees each person receives exactly one email.”** It guarantees intent is committed with business state; SMTP outcome uncertainty can still cause duplicate attempts.

**“Leases and fencing make duplicate sends impossible.”** Leases/fencing cannot retract SMTP DATA already accepted by the relay from an older worker.

**“Just increase retries to infinity.”** Permanent errors, invalid recipients, AUTH failures, and expired OTPs need different actions. Retry storms also worsen provider throttling.

**“A queue holding hundreds of thousands of `MimeMessage`s is good because it buffers a lot.”** In-RAM tasks hold huge attachment bytes and vanish on crash; durable backlogs belong in a DB or broker.

**“Using `CallerRuns` when the executor fills prevents losing mail.”** `CallerRuns` can execute SMTP right on the HTTP thread, bringing back the original blocking issue. With a durable outbox, use proper backpressure and capacity planning.

**“Every SMTP provider shares the same quota and 550 semantics.”** Rates, connections, enhanced statuses, and policies vary; build provider-aware classification.

**“Once SMTP accepts, the outbox row should be deleted immediately.”** Keep retention/attempt audits and downstream lifecycle tracking per business contract.

**“A unit test mocking `JavaMailSender` proves rollback retracts email.”** Mocks only verify method calls; they do not simulate relay acceptance or protocol boundaries. Use an SMTP sandbox for integration tests.

## 21. Practice Exercises

### Exercise 1 — Proving the Rollback Boundary

Create a Spring Boot application with an `orders` table, `@Transactional OrderService`, and `JavaMailSenderImpl` pointing to an SMTP sandbox. Inside the method, insert an order, call send, then throw an unchecked exception. Assert:

```text
DB order count = 0
SMTP sandbox received messages = 1
```

Explain why these two outcomes do not contradict each other.

### Exercise 2 — Comparing Rollback Rules

Test three variants:

1. `MailException` escapes the transactional method.
2. `MailException` is caught and swallowed.
3. The method throws a checked exception, with and without a matching `rollbackFor`.

Record the DB outcome under each configuration and note that the SMTP side effect is independent of each outcome.

### Exercise 3 — Testing JPA `flush`

Call `saveAndFlush(...)`, then send an email, then roll back the transaction. Verify the order still rolls back while the sandbox receives the message. Write an explanation of the difference between flush and commit.

### Exercise 4 — `AFTER_COMMIT`

Move sending into `@TransactionalEventListener(AFTER_COMMIT)`. Test that transaction rollback does not trigger the listener while successful commit does. Then simulate a crash window after commit and explain why the callback is still not guaranteed.

### Exercise 5 — Building a Transactional Outbox

Design a `mail_outbox` table with a business event unique key, state, attempts, and `nextAttemptAt`. Write the business order and outbox row in the same transaction. Test that rollback deletes both and commit keeps both.

### Exercise 6 — Idempotency on HTTP Retry

A client sends two requests with the same idempotency key after the first loses its HTTP response. Use a unique key and payload comparison to create only one order and one mail intent.

### Exercise 7 — Concurrent Worker Claims

Run two worker instances claiming the same job against PostgreSQL. Only one worker receives a valid lease token. Explain why Java's `synchronized` is insufficient across multiple pods.

### Exercise 8 — Temporary Retries

The SMTP test server returns 451. The worker records `RETRY_WAIT`/`nextAttemptAt` and releases the slot instead of calling `Thread.sleep`. Test `maxAttempts`, backoff, jitter, and job expiry.

### Exercise 9 — SMTP Accepted, Then DB Result Fails

Let the SMTP sandbox accept the email, then intentionally fail the DB result update. Describe the `UNKNOWN` state and reconciliation options. Do not claim the next send cannot create a duplicate.

### Exercise 10 — Worker Shutdown

Enqueue 100 jobs, let 4 attempts run concurrently, then stop the worker. Verify unclaimed jobs remain in the DB and unresolved-outcome jobs are recovered via lease/reconciliation on restart.

### Exercise 11 — Provider Quotas

Suppose an SMTP account allows at most 4 concurrent connections and 10 attempts/sec, while running 3 pods with 5 workers each. Design an account-wide concurrency cap/rate limiter so neither quota is breached.

### Exercise 12 — Splitting Web/Worker Deployments

Create two Spring profiles:

```text
web:
  HTTP + business DB + outbox writer

mail-worker:
  outbox dispatcher + composer + JavaMailSender
```

Verify that when the worker is stopped, web still commits orders and outbox rows; when the worker comes back up, the backlog drains.

### Exercise 13 — Distinguishing Submission from Delivery

Send an email to an SMTP sandbox and assert relay acceptance. Add a provider webhook event model representing later delivered/bounced states. Explain why you cannot set `DELIVERED_TO_INBOX` immediately just because `send` threw no exception.

### Exercise 14 — Incident Runbook

Build a timeline for a case where a customer received an email about a rolled-back invoice. List the data to trace, code changes to make, and regression tests to prevent recurrence.

## 22. Checklist Before Using Spring Mail in a Business Transaction

### Transaction Boundary

- Is `JavaMailSender.send(...)` called inside a `@Transactional` method or code it invokes?
- Which databases/resources does the transaction manager protect?
- Do external SMTP/HTTP/file side effects occur before commit?
- Are default rollback rules, catch/throw behavior, self-invocation, and propagation understood?
- Is `flush()` being confused with commit?
- Could an exception after SMTP acceptance roll back the database and leave inconsistent email state?
- Are SMTP timeouts classified as `UNKNOWN` when evidence is insufficient?

### Preserving Send Intent

- Does the business transaction insert an outbox intent alongside the business change?
- Does the outbox have a unique business event key and request idempotency policy?
- When the DB rolls back, are workers guaranteed never to pick up uncommitted intents?
- When the DB commits, does intent survive process crashes/deployments?
- Are payloads/attachments/templates versioned and still retrievable after delays?
- Is submission acceptance separated from downstream delivery status?
- Do you avoid claiming exactly-once SMTP without a supporting contract?

### Workers and Retries

- Do workers use atomic claims, lease tokens, and conditional state updates?
- Are claims committed before SMTP calls, never holding DB transactions open during network I/O?
- Is there an attempt history separating the notification from each send attempt?
- Are retry backoff, jitter, max attempts, and TTL enforced?
- Are permanent recipient/config errors classified differently from temporary provider errors?
- Does recovery handle expired `SENDING` leases without blindly requeueing `UNKNOWN` outcomes?
- Are executors/queues bounded without accidentally falling back onto request threads?
- Are provider quotas enforced across the whole account/multiple replicas?

### Testing and Operations

- Is there a test proving DB rollback does not retract mail already accepted by an SMTP sandbox?
- Is there a test verifying business + outbox roll back and commit together?
- Are concurrent claims, DB result failures, SMTP timeouts, and restarts tested?
- Are HTTP latency, DB lock waits, oldest outbox age, and SMTP attempt duration measured?
- Are request/business/notification/attempt IDs logged without leaking PII/secrets?
- Are pause/replay/dead-letter/incident response procedures defined?
- Are customers protected from misleading emails for uncommitted business records?
- Is there a plan to remove the legacy synchronous send path completely after migrating to workers?

## 23. Summary

**Calling `JavaMailSender.send(...)` inside a Spring transaction and believing database rollback will retract the email is a design flaw.** JDBC/JPA transactions do not control SMTP relays. If the relay accepts before the database rolls back, the recipient can still receive the email; if SMTP is slow, the database transaction and HTTP request are also held open unnecessarily.

Moving `send` to `@Async` changes threads, yet guarantees neither post-commit execution nor crash survival. `@TransactionalEventListener(AFTER_COMMIT)` avoids sending before a successful commit, yet still leaves a crash window between commit and callback; it is not a durable queue. For important emails, a better architecture is **persisting business state and outbox intent in the same database transaction**, then letting an independent worker claim, compose MIME, submit via SMTP, and record attempt outcomes.

A transactional outbox solves **never losing send intent after commit** and avoids sending for rolled-back data, yet **does not by itself guarantee exactly-once submission**. SMTP outcomes can be `UNKNOWN` when replies are lost after DATA or workers fail to persist accepted status. Systems therefore need business-key idempotency, attempt history, leases/fencing, backoff, reconciliation, and clear duplicate policies.

When designed properly, database rollback governs only the business changes and outbox row in the same transaction; SMTP is treated as an independent external side effect. **That is the exact boundary you must understand for Spring Framework Mail to operate reliably in production.**





