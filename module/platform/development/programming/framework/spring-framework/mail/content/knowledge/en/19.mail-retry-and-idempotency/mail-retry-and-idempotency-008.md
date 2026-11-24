# Preventing Duplicates After Unknown-Outcome Timeouts

When an application sends emails using **Spring Framework Mail**, a call to **JavaMailSender.send(...)** can end in a timeout. The hardest question is not simply "how do we retry?", but **"did the SMTP server already receive the previous email?"** If the server accepted the message and the success response was lost in transit, the application may record a failed send and resend the same email. The recipient can then receive two emails even though the user acted only once.

This problem is especially critical for order confirmation emails, invoices, access provisioning, verification codes, password reset links, and transactional notifications. A duplicate welcome email may be annoying; two emails containing different one-time codes or two invoices with the same transaction number can make recipients distrust the system.

This lesson focuses on **ambiguous-outcome timeouts**, designing **idempotency keys**, the **UNKNOWN** send state, **transactional outbox** queues, **reconciliation** mechanisms, and safe retry policies. Examples use Spring Mail with SMTP; when comparing with email provider HTTP APIs, clearly distinguish deduplication actually provided by the provider from metadata placed inside a MIME message.

> **Core rule:** Never treat every timeout as "unsent," never treat setting `Message-ID` as a duplicate-prevention guarantee, and never claim exactly-once email delivery merely because you added retries or an outbox.

## 1. Scenario: SMTP Accepted the Email, but the Application Timed Out

A simple sending flow:

~~~text
OrderService
    |
    v
JavaMailSender.send(...)
    |
    v
SMTP server
    |
    v
Success response
    |
    v
Application marks SENT
~~~

Yet the network can drop at the exact moment the SMTP server sends its reply:

~~~text
Spring application                   SMTP server
       |                                  |
       |-- MAIL FROM -------------------->|
       |<--------------------------- 250 -|
       |-- RCPT TO ---------------------->|
       |<--------------------------- 250 -|
       |-- DATA ------------------------->|
       |<--------------------------- 354 -|
       |-- MIME body + <CRLF>.<CRLF> ---->|
       |                                  | accepts and queues
       |              X (connection lost) |
       |<--- 250 accepted (lost) ---------|
       |                                  |
    Timeout                               |
       |                                  |
       v                                  v
  Unknown outcome                  Message was received
~~~

Here, the server **may have accepted the message**, while the client never received the final answer. If the application immediately retries the entire message, the server may accept the second copy as well.

### Two Worlds Indistinguishable From the Client Side

Given the exact same observed timeout error, two situations can exist:

| World | What happened on the server | What the application saw |
| --- | --- | --- |
| **A** | Server did not receive/accept the message | Timeout |
| **B** | Server accepted the message; response was lost | Timeout |

Without additional evidence, the application **cannot determine A vs. B with certainty from the timeout exception alone**.

Retrying when reality is B risks sending duplicates. Not retrying when reality is A risks dropping the email. This is the inherent trade-off of sending to an external system over a network.

### "Server Accepted" Does Not Mean "Inbox Delivered"

A success reply after the SMTP `DATA` command usually indicates **the SMTP server accepted responsibility for handling the message**. It does not guarantee:

- The message reached the final mailbox.
- The message will not bounce later.
- The message did not land in the spam folder.
- The recipient opened or read the message.

Therefore, separate **ACCEPTED/SUBMITTED** from **DELIVERED** if the system integrates provider delivery events. In duplicate-prevention examples, "sent successfully" means accepted by the transport/provider, not guaranteed Inbox placement.

## 2. Which Timeouts Truly Create Unknown Outcomes?

Not all connection errors carry the same ambiguity. Where the failure occurs in the protocol affects the likelihood that the server received the message.

| Failure timing | Reasonable assessment | Action |
| --- | --- | --- |
| Cannot open TCP connection and no SMTP command sent | Usually no message transmitted on that connection | May retry after confirming failure occurred before transmission |
| Did not complete SMTP authentication | Usually message not submitted | Fix credentials/config; do not retry indefinitely |
| Server returns clear error at `MAIL FROM` or `RCPT TO` | Message not completed through `DATA` for rejected recipients | Classify error and recipients per reply |
| Server returns clear error without accepting `DATA` | Evidence of rejection at that stage | Follow reply code policy |
| Connection lost while streaming `DATA` | Unknown whether server received the end-of-message marker | Handle cautiously; mark `UNKNOWN` if unprovable |
| Connection lost or read timeout waiting for final reply after `DATA` | **Server may have accepted the message** | `UNKNOWN`; prioritize reconciliation |
| Client receives final success response | Evidence SMTP server accepted the message | Mark `ACCEPTED`; do not retry on later network errors |
| App crashes after SMTP success but before saving result | Server may have accepted, database has not recorded it | `UNKNOWN` on recovery; requires reconciliation |

This table provides classification guidance. A library exception might not contain enough data to pinpoint which command the server reached. Without solid proof of the failure stage, default conservatively rather than forcing timeouts into an "unsent" state.

### Distinguishing Explicit Rejection From Missing Response

If the server sent an explicit SMTP reply, the application has evidence to classify:

- **4xx** usually indicates a temporary error; may retry per policy when conditions allow.
- **5xx** usually indicates a permanent error at that step; do not retry indefinitely.
- **2xx** indicates the corresponding SMTP operation was accepted.

Conversely, **a timeout is not an SMTP reply code**. It usually means the client did not receive a result in time, so you cannot infer "server returned 4xx" or "server rejected."

Note that a single send to multiple recipients can yield different per-recipient outcomes. To prevent per-recipient duplicates, track per-recipient state or split into individual notifications per business contract.

## 3. Three Concepts That Must Stay Separate

### Retry — Attempting Execution Again

**Retry** is repeating an operation after a failure. Retries overcome transient issues such as brief network outages or SMTP `4xx` responses, yet can cause duplicates if the prior execution already took effect.

### Idempotency — Multiple Equivalent Requests Produce One Logical Effect

An operation is idempotent within a defined scope if repeating it with the same identifier produces no extra business effect beyond the initial effect. For example, an API receiving a request to **send the invoice for order ORD-1528, version 1** can create only a single mail outbox job for that key.

However, deduplicating at **the job-creation layer** differs from deduplicating at **the SMTP message-acceptance layer**.

### Deduplication — Detecting and Suppressing Duplicate Requests

**Deduplication** uses an identifier or fingerprint to recognize two requests belonging to the same logical operation. It can be implemented at:

- The request-receiving API.
- The database outbox / job queue.
- The worker before sending.
- The email provider API, **only if the provider publishes and supports idempotency/deduplication**.

No default deduplication mechanism applies universally across all SMTP servers.

### Distinguishing Three Guarantee Levels

| Layer | What it can guarantee | What it does not guarantee on its own |
| --- | --- | --- |
| **Business API** | One equivalent business action accepted once per key | Only one send over SMTP |
| **Outbox + unique key** | One logical notification has one job record | Worker never duplicates after a crash |
| **Provider with true idempotency** | Provider may skip creating an extra submission on retries with the same key within its support window | Every mailbox receives exactly one copy, or other providers support it |

To know what level your system achieves, inspect **at which boundaries deduplication is actually enforced**.

## 4. Does Message-ID Help Prevent Duplicates?

Emails carry a **Message-ID** header, for example:

~~~text
Message-ID: <order-1528-v1@mail.example.test>
~~~

This header identifies an email message for threading, lookup, and correlation. An application can choose a stable `Message-ID` for a logical notification under a valid convention.

Yet there are two limitations:

1. **SMTP does not require servers to reject a message simply because its `Message-ID` has been seen before**.
2. Two SMTP submissions with the same `Message-ID` **can still produce two email copies** at the recipient side.

Therefore, **`Message-ID` is not an idempotency key with universal guarantees at the SMTP layer**.

### Setting Message-ID for Reconciliation

A stable, globally unique `Message-ID` can help:

- Locate the corresponding message in SMTP/provider logs.
- Link mail events back to the outbox record.
- Assist investigation when the server reports acceptance while the app logged a timeout.

If setting `Message-ID` yourself via Jakarta Mail, note that **`MimeMessage.saveChanges()`** or the send operation may generate or overwrite the header depending on the implementation. Verify the final `Message-ID` in the actual MIME output and check whether your provider preserves headers; do not assume a header set before sending survives intact.

For provider APIs supporting an **Idempotency-Key**, **client token**, or documented deduplication key, that mechanism differs from `Message-ID`: the provider can look up/store the API request outcome by key and refuse creating another equivalent submission. Verify scope, key retention duration, and payload-matching requirements.

### A Stable Key Must Not Be Reused for Different Content

For example, the same order may require:

- Initial order confirmation email.
- Order modification email.
- Requested resend of an updated invoice version.

Those three notifications must not share one key just because they share an order ID. Separate **event type**, **version**, and **recipient**.

## 5. Designing Business-Meaningful Idempotency Keys

A deduplication key should describe **one logical notification**, not one technical execution.

Example:

~~~text
tenant       = shop-7
eventType    = ORDER_CONFIRMED
aggregateId  = ORD-1528
eventVersion = 1
recipientId  = customer-392

notificationKey =
  shop-7:ORDER_CONFIRMED:ORD-1528:1:customer-392
~~~

Redelivery or reprocessing of the same event produces the same key; a new event with a different version produces a different key.

### Why Not Use a Fresh Random UUID for Every Retry?

If each retry mints a new UUID:

~~~text
Attempt 1: key = 1a2b...
Attempt 2: key = 7c8d...
~~~

the system has no way to tell both attempts belong to the same notification. A random UUID fits as the **notification's ID when created initially**; subsequent attempts must reuse the stored ID/key instead of creating a new notification.

### Key Components

| Component | Purpose |
| --- | --- |
| **tenantId** | Separates matching business IDs across tenants |
| **eventType** | Distinguishes order confirmation, cancellation, payment reminder |
| **aggregateId** | Ties the notification to the business entity |
| **eventVersion/sequence** | Separates new notifications on the same entity |
| **recipientIdentity** | Separates recipients per sending contract |

Not every system needs all five components. If the upstream event already carries a unique stable ID, combine that ID with tenant/recipient and notification type.

When building string keys, define encoding/escaping for components so delimiters cannot cause collisions. Alternatively, serialize fields with a deterministic schema and hash them. **Never use a hash of the rendered email content as the sole key**, since template edits, timestamps, or tracking parameters can cause the same event to render differently and break deduplication.

### When the User Requests a "Resend"

An intentional **resend** differs from a **retry after timeout**:

- **Retry**: trying to complete the exact same previously emitted notification; preserve the original notification ID/key.
- **Resend**: a user or staff member intentionally initiates a new send request; record a new event/notification ID linked to the original notification.

Reusing the original key for a resend would let deduplication block a valid request. Minting a new key for a retry can cause unintended duplicates. Separate the two actions in both the API and data model.

### Recipients Are Part of the Contract

If an email goes to multiple people:

~~~text
ORDER_CONFIRMED:ORD-1528:v1:recipient-A
ORDER_CONFIRMED:ORD-1528:v1:recipient-B
~~~

Two recipients may need two separate notifications. If a business notification intentionally combines `To`/`Cc`/`Bcc`, the idempotency key must accurately represent the **recipient set** per business policy. Avoid assuming every address maps to a single mailbox or normalizing emails with provider-specific rules; use stable recipient IDs or system-approved canonicalization rules.

## 6. Enforcing Deduplication Guardrails in the Database

A pure Java "check if absent, then insert" can suffer race conditions when multiple threads or instances receive the same event concurrently:

~~~text
Worker A                         Worker B
   |                                |
   v                                v
SELECT key -> not found        SELECT key -> not found
   |                                |
   v                                v
INSERT notification           INSERT notification
~~~

Without a unique constraint, both inserts can succeed and enqueue two jobs for the same email.

### A Unique Constraint Is the Final Backstop

An outbox table can look like:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    notification_key VARCHAR(300) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    template_code VARCHAR(120) NOT NULL,
    template_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    client_correlation_id VARCHAR(120) NOT NULL,
    provider_message_id VARCHAR(200),
    last_error_code VARCHAR(100),
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMPTZ,
    CONSTRAINT uq_mail_notification
        UNIQUE (tenant_id, notification_key)
);
~~~

This is illustrative PostgreSQL DDL, not a mandatory Spring Mail schema. Adjust column names and types to match your database/ORM. Key fields:

- **notification_key**: stable business identifier.
- **id**: record ID referenced by attempt logs.
- **client_correlation_id**: stable identifier generated by the app before sending for reconciliation.
- **status**: currently known submission state.
- **lease_owner/lease_token/lease_until**: coordinates multiple workers and prevents stale status overwrites.
- **provider_message_id**: ID returned by the provider, if any.

The `UNIQUE` constraint must be enforced at the database level, not solely via `existsBy...` in application code. It ensures duplicate event deliveries do not create two logical notification records.

### Idempotent Insert Within the Business Transaction

PostgreSQL SQL example:

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, notification_key, event_type,
    recipient_email, template_code, template_version,
    payload_json, status, client_correlation_id
)
VALUES (
    :id, :tenant_id, :notification_key, :event_type,
    :recipient_email, :template_code, :template_version,
    :payload_json, 'PENDING', :correlation_id
)
ON CONFLICT (tenant_id, notification_key) DO NOTHING;
~~~

If the same key already exists, the insert does not create a new notification. When handling a conflict, the service should fetch the existing record's ID/status rather than assuming a fresh insert succeeded.

**Same key must carry the same business meaning.** If a request reuses a key with a non-equivalent payload, report a conflict or flag a data issue; never silently overwrite the payload of an in-flight notification. Store a canonical payload fingerprint to detect this.

### Do Not Rely Only on synchronized or an In-Memory Set

~~~java
if (!sentKeys.contains(key)) {
    sentKeys.add(key);
    mailSender.send(message);
}
~~~

This is insufficient because:

- On restart, keys in RAM are lost.
- Multiple instances hold separate `Set` instances.
- It does not handle crashes between sending mail and updating the key.
- It provides no `UNKNOWN` state for reconciliation.

A database unique constraint or durable idempotency store is a much sounder foundation.

## 7. Transactional Outbox: One Durable Job per Notification

A **transactional outbox** persists the mail job inside the same database transaction as the business event. This avoids cases where an order commits while the mail-sending event is never recorded.

~~~text
HTTP request / event consumer
             |
             v
       BEGIN TRANSACTION
             |
             +--> Save Order
             |
             '--> INSERT mail_outbox(PENDING)
                    with UNIQUE notification key
             |
             v
           COMMIT
             |
             v
      Background mail worker
             |
             v
       Send via SMTP
~~~

If the transaction rolls back, both `Order` and `mail_outbox` roll back. If it commits, the outbox row survives restarts for a worker to recover.

### Spring Service Example Persisting Outbox in the Same Transaction

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.create(command));

        String key = String.join(
                ":",
                order.getTenantId(),
                "ORDER_CONFIRMED",
                order.getBusinessId(),
                String.valueOf(order.getVersion()),
                order.getCustomerId()
        );

        outboxRepository.insertIfAbsent(
                MailOutboxDraft.orderConfirmed(order, key)
        );

        return order;
    }
}
~~~

**MailOutboxRepository** and **MailOutboxDraft** are application-defined components, not built-in Spring APIs. **insertIfAbsent** must use a database-appropriate unique constraint/upsert. Saving `Order` and the outbox must share the same transaction manager and physical transaction for atomicity.

### Store the Snapshot Needed to Build the Email

The outbox payload can hold:

- Order ID and order version.
- Recipient ID and validated recipient address.
- Template code and template version.
- Data needed for rendering or references to readable data snapshots.

If you store only the order ID and have the worker read the latest mutable state, email content can change if the order is edited while waiting for retry. When the notification must reflect the exact moment the event occurred, store an intentional snapshot and pin a stable template version.

Never store passwords, SMTP credentials, or unnecessary secret tokens. If sending tokenized links, design token lifecycles/rotation and data protection policies for outbox storage. Outbox data may contain PII requiring access controls, retention limits, and encryption where appropriate.

## 8. A State Model That Includes UNKNOWN

If send states only include **PENDING**, **SENT**, and **FAILED**, timeouts tend to get forced into `FAILED` and immediately retried. That erases the distinction between "unsent" and "unknown whether sent."

A clearer state machine:

| State | Meaning | Auto-retry? |
| --- | --- | --- |
| **PENDING** | Job has not started sending yet | Yes, when scheduled |
| **IN_FLIGHT** | Worker claimed job and is executing an attempt | Block parallel sends by other workers |
| **ACCEPTED** | Evidence that provider/SMTP accepted it | No |
| **RETRYABLE_FAILED** | Evidence of transient error safe to retry | Yes, with backoff |
| **PERMANENT_FAILED** | Error should not be auto-retried | No; fix data/config |
| **UNKNOWN** | Unclear whether provider accepted the attempt | **No blind retry**; reconcile or apply risk policy |
| **CANCELLED** | Notification intentionally cancelled | No |

The **UNKNOWN** state carries business meaning, not just an exception message.

~~~text
PENDING
   |
   v
IN_FLIGHT
   |
   +-- receives SMTP 250 / provider accepted --> ACCEPTED
   |
   +-- confirmed temporary error --------------> RETRYABLE_FAILED
   |                                                  |
   |                                                  v (backoff)
   |                                                PENDING
   |
   +-- confirmed permanent error --------------> PERMANENT_FAILED
   |
   '-- timeout / crash / lost ACK -------------> UNKNOWN
                                                      |
                                                      +-- reconciliation found --> ACCEPTED
                                                      |
                                                      +-- definitely not sent --> PENDING
                                                      |
                                                      '-- no evidence yet ------> remain UNKNOWN
~~~

The **UNKNOWN -> PENDING** transition is only safe when there is reliable evidence the provider did not accept the message, or the provider supports true idempotency for the same key. Otherwise, it is a product-policy trade-off between losing a notification and sending a duplicate—never assume it is unconditionally safe.

## 9. How Should Each Email Send Attempt Be Recorded?

A **Notification** is the single business job. An **Attempt** is one try at sending that notification via transport. One notification can have multiple attempts due to temporary errors or intentional retries.

~~~text
Notification: ORDER_CONFIRMED / ORD-1528 / v1 / recipient-392
       |
       +-- Attempt #1: timeout after DATA => UNKNOWN
       |
       +-- Attempt #2: created only if retry permitted
       |
       '-- Final outcome: ACCEPTED / PERMANENT_FAILED / UNKNOWN
~~~

Recording separate attempts is valuable because you need **the failure point of each send**, not just the final status:

| Attempt field | Example | Purpose |
| --- | --- | --- |
| **attemptId** | UUID | Distinguishes individual executions |
| **notificationId** | Outbox UUID | Links back to original notification |
| **attemptNumber** | 1, 2, 3 | Observability and enforcing retry limits |
| **startedAt** | Start timestamp | Investigates execution duration |
| **completedAt** | Completion timestamp if any | Shows whether attempt finished or aborted |
| **outcome** | `ACCEPTED`, `REJECTED`, `UNKNOWN` | Outcome classification |
| **smtpStage** | `CONNECT`, `RCPT`, `DATA`, `FINAL_REPLY` | Investigation if instrumentation provides data |
| **smtpReplyCode** | `250`, `451`, `550` if received | Never guess a code on timeout |
| **providerRequestId** | Provider-issued ID | Lookup on provider side |
| **errorCategory** | `READ_TIMEOUT`, `WRITE_TIMEOUT`, `AUTH`, `INVALID_RECIPIENT` | Classification and monitoring |

Jakarta Mail does not automatically provide every detail such as `smtpStage` or `providerRequestId` in all exceptions. If the app lacks instrumentation for a field, record **UNKNOWN** rather than fabricating an unverified failure stage.

### Distinguishing Idempotency Key From Attempt ID

~~~text
notificationKey = shop-7:ORDER_CONFIRMED:ORD-1528:1:customer-392
notificationId  = 6b91... (stable)

attemptId #1   = c1f7... (new for first attempt)
attemptId #2   = d4a9... (new for second attempt)
~~~

The notification key must stay constant on retries. The attempt ID must differ so logs do not collide. When a provider supports an idempotency key, pass **the stable notification key or token**, never a per-attempt ID.

### Record the Attempt Before Performing External I/O

An important rule:

1. **Claim** the notification and create the attempt record in the database.
2. **Commit** the `IN_FLIGHT` state before calling SMTP.
3. Send the email outside the database transaction.
4. Persist the outcome in a new short transaction.

If you only log the attempt after SMTP succeeds, a crash mid-send leaves no trace of an uncertain attempt.

## 10. Claiming Jobs With Multiple Workers: Avoiding Parallel Duplicate Sends

In a multi-instance Spring deployment, two workers can spot the same `PENDING` notification. If both send, outbox insert-time deduplication is no longer enough.

### Why Two-Step Read-Then-Update Races

~~~text
Worker A                          Worker B
   |                                 |
SELECT PENDING                    SELECT PENDING
   |                                 |
   +-- sees notification #42         +-- also sees #42
   |                                 |
send email                        send email
~~~

You need an **atomic claim** on shared storage, such as row locks, compare-and-set updates, or a queue supporting claims/visibility timeouts.

### Claim Example Using PostgreSQL

Illustrative statement:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRYABLE_FAILED')
      AND (next_attempt_at IS NULL
           OR next_attempt_at <= CURRENT_TIMESTAMP)
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS m
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = m.lease_token + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempts = m.attempts + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE m.id = candidate.id
RETURNING
    m.id, m.notification_key, m.recipient_email,
    m.payload_json, m.attempts, m.lease_token;
~~~

This query:

- Picks only retry-eligible and due notifications.
- Skips rows already locked by other workers.
- Updates status and lease in a single statement/transaction.
- Increments **lease_token** to distinguish claims.
- Returns the data needed by the worker.

This is a PostgreSQL example, not portable SQL across all engines. Run it inside a short transaction and **commit the claim transaction before calling SMTP**.

### Why Are Leases Needed?

If a worker dies mid-send, the notification must not stay stuck `IN_FLIGHT` forever. **lease_until** identifies jobs where a worker stopped renewing ownership.

Yet **lease expiration does not prove the email was never sent**. The worker might have sent over SMTP successfully and crashed right before saving the outcome, or it might still be waiting on a network reply when the lease expires.

Consequently, for SMTP jobs:

~~~text
IN_FLIGHT + lease expired
          |
          v
        UNKNOWN
          |
          v
      Reconciliation
~~~

Never blindly flip all lease-expired jobs back to `PENDING` for immediate retry. That restores throughput at the cost of sending duplicates at the exact worst moment.

### Fencing Tokens Protect State Updates

When Worker A loses its lease and Worker B reclaims the row, A may wake up and try to write a late outcome. To block stale overwrites:

~~~sql
UPDATE mail_outbox
SET status = 'ACCEPTED',
    accepted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :notification_id
  AND lease_owner = :worker_id
  AND lease_token = :lease_token
  AND status = 'IN_FLIGHT';
~~~

If the update affects 0 rows, the worker is no longer the current owner and must not overwrite another attempt's outcome.

**Fencing tokens only protect database state**; they cannot cancel an SMTP submission already sent to the provider. If Worker A had already begun sending when its lease expired, Worker B can still send a duplicate unless safe `UNKNOWN` rules are enforced. Combining leases/heartbeats, sensible timeouts, and no blind retries is essential.

## 11. Transaction Boundaries of the Mail-Sending Worker

Never hold an open database transaction while waiting on SMTP. Doing so extends locks, ties up pool connections, and increases contention.

Recommended flow:

~~~text
Worker
  |
  v
TX #1: claim PENDING -> IN_FLIGHT
  |
  v
COMMIT
  |
  v
Render MIME message from stored payload
  |
  v
JavaMailSender.send(...)
  |
  +-- success ----> TX #2: mark ACCEPTED
  |
  +-- proven failure ----> TX #2: mark RETRYABLE/PERMANENT
  |
  '-- uncertain ----> TX #2: mark UNKNOWN
~~~

### Separate Transactional Methods

Example division of responsibilities:

~~~java
public interface MailJobStore {

    // Each method executes in a short DB transaction.
    Optional<ClaimedMailJob> claimNext(String workerId);

    boolean markAccepted(
            UUID jobId, String workerId, long leaseToken
    );

    boolean markUnknown(
            UUID jobId, String workerId,
            long leaseToken, String errorCode
    );

    boolean markRetryableFailure(
            UUID jobId, String workerId,
            long leaseToken, Instant nextAttemptAt
    );
}
~~~

This is an application-designed interface. Implementations can use `JdbcTemplate` or Spring Data JDBC/JPA with separate short transactions and compare-and-set updates; there is no built-in `MailJobStore` in Spring Framework Mail.

The worker handles only orchestration:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class MailOutboxWorker {

    private final MailJobStore jobStore;
    private final MailSubmitter submitter;

    public MailOutboxWorker(
            MailJobStore jobStore,
            MailSubmitter submitter
    ) {
        this.jobStore = jobStore;
        this.submitter = submitter;
    }

    public void runOne(String workerId) {
        Optional<ClaimedMailJob> found = jobStore.claimNext(workerId);
        if (found.isEmpty()) {
            return;
        }

        ClaimedMailJob job = found.get();
        try {
            submitter.submit(job);
            jobStore.markAccepted(
                    job.id(), workerId, job.leaseToken()
            );
        } catch (ProvenRetryableMailException ex) {
            jobStore.markRetryableFailure(
                    job.id(), workerId, job.leaseToken(),
                    backoffFor(job.attemptNumber())
            );
        } catch (Exception ex) {
            // No evidence that SMTP definitively rejected it.
            jobStore.markUnknown(
                    job.id(), workerId, job.leaseToken(),
                    classifyForAudit(ex)
            );
        }
    }
}
~~~

`ClaimedMailJob`, `MailSubmitter`, `ProvenRetryableMailException`, and the backoff/classify helpers are illustrative components, not built-in Spring APIs. In particular, throw **ProvenRetryableMailException** only when the sending layer has reliable evidence the prior attempt was not accepted. Never convert every `MailSendException` into a retryable error.

**Another failure to account for:** after `submitter.submit(job)` succeeds, the process may crash before `markAccepted` commits. That case still needs reconciliation; there is no shared atomic transaction spanning the SMTP server and database.

### Do Not Swallow Errors If Writing UNKNOWN Also Fails

In the example, if the database loses connectivity during `markUnknown`, the attempt may remain `IN_FLIGHT` until its lease expires. A recovery process must transition expired-lease rows to `UNKNOWN` and emit metrics/alerts. Never consider exception handling complete merely because `markUnknown` was invoked.

## 12. Controlled Retries Instead of Infinite Loops

Retries make sense for errors **known not to have been accepted by the provider** and likely to recover:

- Clear SMTP `4xx` before submission completes.
- Connection not established or failed before transmitting the message, with supporting evidence.
- Provider API returning a documented retryable error.
- Provider supporting idempotency and confirming safe retries with the same key.

Retries are dangerous when:

- Timeout occurs after sending all `DATA`.
- Connection drops while waiting for the final `250`.
- App crashes after server acceptance but before committing status.
- Errors are collapsed into a generic exception hiding whether the server received the message.

### Exponential Backoff With Jitter

A typical retry policy:

~~~text
delay = min(maxDelay, baseDelay * 2^(attemptNumber - 1))
actualDelay = delay * randomFactor
~~~

Example with `baseDelay = 10s`, `maxDelay = 10m`, jitter factor `0.5` to `1.5`:

| Attempt | Base delay before jitter |
| --- | --- |
| 1 | 10 seconds |
| 2 | 20 seconds |
| 3 | 40 seconds |
| 4 | 80 seconds |
| 5 | 160 seconds |
| 6 | 320 seconds |
| 7 onward | Up to 10 minutes |

Jitter prevents workers from retrying simultaneously after a network glitch or provider outage. Cap attempt count, total retry window, and send rate to avoid spamming or breaching rate limits.

**Backoff does not resolve timeout ambiguity.** Waiting 10 minutes before resending an already-accepted message still produces a duplicate. For `UNKNOWN`, retry decisions must depend on reconciliation results or an explicit risk-acceptance policy.

### Dead-Letter or Manual Handling

Once retry limits or notification deadlines expire:

- Transition to `PERMANENT_FAILED` or `NEEDS_REVIEW` per design.
- Preserve the full attempt history.
- Trigger an alert carrying the notification/correlation ID.
- Provide operators with a controlled retry/resend action.

Do not delete the outbox row immediately upon exhausting retries if reconciliation, investigation, or future deduplication is needed.

## 13. Reconciliation: Determining the Outcome of an UNKNOWN Attempt

**Reconciliation** is the process of cross-checking application-side records against traces at the provider/SMTP server. Its goal is to move `UNKNOWN` to an evidence-backed conclusion.

~~~text
Outbox notification #42
     |
     v
Attempt #1 => UNKNOWN
     |
     v
Query provider / server logs / delivery events
     |
     +-- Evidence of acceptance
     |        |
     |        v
     |     ACCEPTED
     |
     +-- Evidence of non-acceptance
     |        |
     |        v
     |     Eligible to retry per policy
     |
     '-- Insufficient evidence
              |
              v
        Keep UNKNOWN / move to review
~~~

### Sources of Evidence

| Source | What it can provide | Limitations |
| --- | --- | --- |
| **Email provider API** | Look up request by key/correlation ID, inspect accepted status | Usable only if the provider genuinely supports lookup with clear semantics |
| **Provider webhook** | Accepted/delivered/bounced events with IDs | Events may arrive late, duplicated, or out of order |
| **SMTP server logs** | Submission logs, queue ID, recipient, and message correlation | Not all SMTP services grant customers log access |
| **Queue ID in SMTP 250** | Trace of message queued on server | Client lacks the ID if the `250` reply itself was lost |
| **`Message-ID` / `X-Correlation-ID` headers** | Aids locating messages at the provider if indexed | Does not prove acceptance; provides no default dedup |
| **Recipient feedback** | Recipient confirms receipt | Manual and cannot verify all cases |

A provider lookup returning **"message not found"** is not guaranteed proof the message was never accepted. Search indexes may lag, retention windows vary, or failed attempts may not be indexed. Rely on the provider's documented contract to know when "not found" is trustworthy.

### Plain SMTP Has an Important Limitation

SMTP is a mail submission and transfer protocol; it offers no standard API for a client to ask: **"Did you previously receive my send request with key K?"**

When using `JavaMailSender` over plain SMTP:

- You can save `Message-ID` and correlation headers to assist log searches.
- You can use a provider/service offering a message-lookup UI or API if available.
- You can track bounces or delivery events if the provider supports them.
- Yet you cannot assume "reconciled" just by issuing a standard SMTP command.

In environments lacking provider lookup, `UNKNOWN` rows may require human review or a product risk policy. Never write a worker that calls `JavaMailSender` again and label that action "reconciliation"—that is a **retry**, not reconciliation.

### Using a Dedicated Correlation ID Header

The application can generate a durable identifier when inserting the outbox row:

~~~text
notificationId    = 6b91...
correlationId     = mail-job-6b91...
messageId         = <mail-job-6b91@mail.example.test>
~~~

Then attach the lookup header:

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, false, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo(job.recipientEmail());
helper.setSubject(job.subject());
helper.setText(job.body());

mimeMessage.setHeader(
        "X-Notification-Correlation-ID",
        job.correlationId()
);

mailSender.send(mimeMessage);
~~~

This custom header **does not make the server deduplicate**, yet it assists reconciliation when the provider retains and indexes custom headers. Never place auth tokens, sensitive internal addresses, or unnecessary personal info inside correlation IDs.

**Verify provider behavior:** some systems strip custom headers or only index specific fields. If the provider offers an official idempotency key in its API, use the documented API parameter instead of hoping custom headers act as deduplication.

### Webhooks Also Need Idempotency

Providers may deliver the same delivery event multiple times or send events out of chronological order. Your webhook handler should:

- Verify webhooks using the provider's signature/authentication mechanism.
- Persist **providerEventId** with a unique constraint to block duplicate processing.
- Map events back to notification ID / correlation ID.
- Enforce valid state transitions so an older incomplete event never overwrites `ACCEPTED`/`DELIVERED`.
- Handle late events and reconcile missing-event cases.

A `DELIVERED` webhook is stronger delivery evidence than `ACCEPTED`, though it still does not prove the recipient read the email.

## 14. How Provider APIs With Idempotency Differ From SMTP

Some email services over HTTP APIs support idempotent requests. When supported, the client passes a stable key:

~~~text
POST /messages
Idempotency-Key: mail-job-6b91...

{
  "to": "customer@example.test",
  "template": "order-confirmed-v1",
  "data": {
    "orderNumber": "ORD-1528"
  }
}
~~~

This example is a **hypothetical interface illustrating the principle**, not a universal endpoint or capability across providers. When genuinely supported by a provider:

1. First send with key **K**.
2. Timeout, response unknown.
3. Resend with **the same key K** and an equivalent payload.
4. The provider checks the key and avoids creating another submission if the first request was already processed, within its documented guarantee/retention window.

This reduces ambiguity **right at the provider boundary**. Conversely, if a provider merely accepts an arbitrary header without enforcing deduplication, its duplicate risk is no different from a standard SMTP retry.

### What to Verify in Provider Documentation

- Does the provider support idempotency for **creating/sending emails**, or only other APIs?
- Is the key passed in a header or a payload field?
- Is the key scoped by account, workspace, endpoint, or tenant?
- How long is the key retained?
- What is returned if the same key is sent with a different payload?
- If the first request is still processing, does a retry wait, error, or return the prior result?
- After the key retention period expires, can a retry create a new submission?
- Can webhooks and lookup APIs be correlated via the same key?

There is no single answer across providers. Implement strictly according to the actual capabilities of your provider.

### Difference Between API Idempotency and Email Threading

Two emails sharing the same `Message-ID` may be grouped into one thread by a mail client or displayed differently. That is not proof the provider dropped the duplicate send. **Mailbox threading** and **send-API deduplication** are separate features.

## 15. Timeouts and Exceptions in JavaMailSender

Spring Mail provides **JavaMailSender** to submit emails over Jakarta Mail; failures can be translated into Spring's **MailException** types.

A common snippet:

~~~java
try {
    mailSender.send(mimeMessage);
    // Evidence that the send call completed without throwing.
    jobStore.markAccepted(job.id(), owner, leaseToken);
} catch (MailException ex) {
    // Do not assume SMTP did not receive it from MailException alone.
    jobStore.markUnknown(
            job.id(), owner, leaseToken,
            ex.getClass().getSimpleName()
    );
}
~~~

This shows a **conservative policy**: any error not classified by specific evidence goes to `UNKNOWN`. In production, distinguish errors proven retryable/permanent instead of treating all failures as ambiguous. Never write:

~~~java
catch (MailException ex) {
    mailSender.send(mimeMessage); // immediate, unconditional retry
}
~~~

because the previous attempt may already have been accepted by the server.

### Timeout Configurations

Illustrative configuration for Spring Boot using `JavaMailSender` SMTP:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Timeout values are in milliseconds and serve as examples:

- **connectiontimeout**: limit for establishing the socket connection.
- **timeout**: limit for reading from the socket.
- **writetimeout**: limit for writing to the socket.

Proper timeouts prevent workers from hanging forever, **but they do not make the outcome certain**. A read timeout while waiting for the final reply can still occur after the SMTP server accepted the message.

### Do Not Rely on Exception Text to Conclude Sent Status

A message like:

~~~text
java.net.SocketTimeoutException: Read timed out
~~~

only indicates a read did not receive data in time. It does not tell you whether the server queued the message.

To classify strictly, use evidence from a confirmed SMTP stage or provider metadata. If the sending tool only surfaces a generic exception, keep the outcome `UNKNOWN` until reconciled.

### Recipient Addresses and Partial Outcomes

When sending a single message to multiple recipients, SMTP can accept some addresses and reject others per server and library rules. If `JavaMailSender`/Jakarta Mail reports a partial send or exposes succeeded/failed addresses, store outcomes **per recipient** if accurate retries are required.

A simpler strategy for transactional emails is **one logical notification per recipient**, avoiding ambiguity about who received a multi-recipient attempt. When emails genuinely require `To`/`Cc`/`Bcc` recipient groups, design explicit group/per-recipient idempotency and reconciliation.

## 16. Do Not Unconditionally Annotate SMTP Sends With @Retryable

Spring Retry can repeat failed operations, yet should only be used when the operation is **safely repeatable** or backed by explicit classification.

A dangerous example:

~~~java
@Retryable(maxAttempts = 3)
public void sendInvoiceEmail(MimeMessage message) {
    mailSender.send(message);
}
~~~

If the first call was accepted by the SMTP server while `JavaMailSender` threw a timeout due to a lost final reply, the interceptor will invoke the method a second and third time. The recipient may receive multiple copies.

**Having `@Retryable` does not make email sending idempotent.** Retry is an execution mechanism; idempotency is a contract enforced at the message creation or delivery boundary.

### Better Places for Retries

Retries can apply to:

- Transient database query failures **before sending**.
- Temporary errors claiming a job before any external side effect occurs.
- Provider APIs with guaranteed idempotency preserving the same key.
- SMTP errors definitively classified as not accepted by the server, when the transport layer supplies evidence.

For timeouts with unknown outcomes, **record `UNKNOWN` and reconcile**; do not simply call `mailSender.send(...)` again.

### Event-Consumer Retries Can Also Create Duplicates

Suppose a message broker delivers the same `ORDER_CONFIRMED` event twice. If the consumer sends emails directly each time:

~~~text
Event #42 -> Consumer -> send email
Event #42 -> Consumer -> send email
~~~

duplicates occur even without any SMTP timeout. Using a stable notification key and a database unique constraint ensures only one outbox row is created for the same event. Then the worker manages attempts and `UNKNOWN` separately.

You do not have to disable retries system-wide; **place retries where safety and outcomes can be determined**.

## 17. Decision Rules for the UNKNOWN State

No single `UNKNOWN` retry policy fits every email. The choice depends on **duplicate cost** versus **missed-notification cost**.

| Email type / scenario | Primary risk | Handling for `UNKNOWN` |
| --- | --- | --- |
| Marketing / low-priority notifications | Duplicates annoy users and hurt reputation | Usually prioritize avoiding duplicates; reconcile or accept rare drops |
| Order confirmations | Both duplicates and misses confuse users | Reconcile with provider; display order details in-app as source of truth |
| Invoices or receipts | Duplicates make users suspect double charges | Keep immutable transaction/invoice IDs, reconcile, controlled resends |
| Security emails / OTP codes | Multiple differing codes confuse users | Do not mint a new token when retrying the same notification; manage expiry and explicit resends |
| Must-not-miss notifications | Missing is severe | Use a provider with idempotency and lookup APIs, or verify operationally before retrying |

A policy can be expressed as:

~~~text
UNKNOWN
   |
   v
Does provider support lookup?
   |
   +-- Yes --> Query by stable correlation/provider key
   |              |
   |              +--> Accepted => ACCEPTED
   |              |
   |              '--> Definitively not accepted => Retryable
   |
   '-- No
          |
          v
     Does provider support idempotent retry with same key?
          |
          +-- Yes --> Retry with exact same key and payload
          |
          '-- No
                  |
                  v
           Business decision:
           HOLD / MANUAL_REVIEW / RISK_ACCEPTED_RETRY
~~~

### If You Are Forced to Retry UNKNOWN

Some systems prioritize ensuring the recipient gets the notification over avoiding duplicates. In that case, retrying `UNKNOWN` can be an **intentional** choice, provided you:

- Document clearly in the design that duplicates can occur.
- Bound attempt counts and frequency.
- Preserve the same notification key and logical content.
- Trigger no extra business side effects (e.g., never record payment again).
- Include a unique transaction reference in the email so recipients see both refer to one event.
- Monitor duplicate rates and user feedback.

Never describe this policy as "completely preventing duplicates."

### Keep Content Stable Across Retries

To aid reconciliation and reduce confusion, retries of the same notification should rely on the same business-meaningful data:

- Unchanged order and invoice numbers.
- Clearly fixed recipient.
- Reproducible template version or message snapshot.
- Never generate a new OTP or link token on every retry, unless initiating a new business resend workflow.

If a token already expired, resending the old message may be useless. Transition the old notification to an appropriate terminal state and emit a **new intentional resend event**, instead of mutating the payload under the same key and calling it a retry.

## 18. Retention of Idempotency Keys and States

Idempotency only works **for as long as the system remembers the key**.

Example:

~~~text
Day 1: ORDER_CONFIRMED:ORD-1528:v1 created and sent
Day 2: duplicate event arrives -> unique constraint blocks
Day 10: event arrives again after dedup record purged
       -> risk of creating a new notification
~~~

Therefore, key retention must cover:

- How long upstream events can replay.
- How long retry/outbox jobs are held.
- How long `UNKNOWN` jobs may need reconciliation.
- Resend eligibility windows and audit requirements.
- Personal data retention and deletion obligations.

If PII-containing payloads must be purged, consider keeping a **tombstone idempotency record** with an opaque key or non-reversible digest, terminal status, and expiry timestamp. Assess re-identification risks and product data policies rather than holding data forever solely for deduplication.

### Provider TTL Is Also a Constraint

Suppose a provider HTTP API retains idempotency keys only for a fixed duration. Retrying the same key **after that window expires** can create a new submission. Thus:

- Record the timestamp of the first attempt.
- Know the provider's published idempotency retention period.
- Never assume "same key" is safe indefinitely.
- After TTL expiry, move to reconciliation or review instead of blind retries.

Exact TTLs depend on the provider and must be verified against current documentation.

## 19. Observability: How to Know Deduplication Is Working

The system must track **notification** state and **attempt** state separately.

### Structured Logs

Each state transition should record minimal metadata:

~~~text
event=mail_attempt_finished
notification_id=6b91...
attempt_id=c1f7...
event_type=ORDER_CONFIRMED
status=UNKNOWN
error_category=READ_TIMEOUT
provider=primary-smtp
duration_ms=10021
~~~

Avoid writing raw email bodies, OTPs, reset tokens, SMTP credentials, or full recipient lists into broadly accessible logs. Correlation IDs should be opaque identifiers, not personal data.

### Useful Metrics

| Metric | Meaning |
| --- | --- |
| **mail_outbox_pending_total** | Notifications awaiting send |
| **mail_outbox_unknown_total** | Notifications with unknown outcome |
| **mail_outbox_oldest_pending_age** | Longest pending wait time |
| **mail_unknown_oldest_age** | Longest stalled `UNKNOWN` job |
| **mail_attempt_total{outcome}** | Attempts by `ACCEPTED`/`FAILED`/`UNKNOWN` |
| **mail_submit_duration_seconds** | Transport call duration |
| **mail_retry_total** | Retry count |
| **mail_dedup_conflict_total** | Duplicate events blocked by unique constraint |
| **mail_lease_expired_total** | `IN_FLIGHT` rows exceeding lease |
| **mail_provider_reconciliation_total{result}** | Provider reconciliation outcomes |

These names are illustrative custom metrics, not built-in Spring Mail metrics. Use low-cardinality labels; never put notification IDs or email addresses into metric labels.

### Important Alerts

Conditions that may warrant alerts:

- Sudden spike in `UNKNOWN` after provider slowdowns.
- `UNKNOWN` age exceeding allowed threshold.
- Rising SMTP submission error rate.
- Growing pending queue with idle or stalled workers.
- Frequent lease expirations indicating slow workers or mismatched timeout/lease settings.
- Multiple requests sharing a notification key with non-equivalent payloads.
- Provider webhooks stopping unexpectedly for an unusual interval.

The goal is knowing **which notifications are awaiting evidence**, rather than staring solely at HTTP requests or exception logs.

## 20. Data Safety and Security During Reconciliation

Emails often carry personal data and actionable links. Retry and idempotency mechanisms must protect data just like any other business flow.

### Never Store Secrets Inside Keys

Do not build keys from raw OTPs or reset tokens:

~~~text
DO NOT:
RESET_PASSWORD:user-392:token-secret-abc123
~~~

Instead, use random/opaque event IDs, non-sensitive user IDs within protected storage, and the notification type:

~~~text
DO:
RESET_PASSWORD:reset-event-6b91...
~~~

If a key appears in logs, headers, or metrics, it must never expose a usable token.

### Never Treat Client-Supplied Metadata as Send Authorization

An email-sending API may accept an **Idempotency-Key** from a client, yet must still:

- Authenticate the caller and verify business authorization.
- Scope the key appropriately by user/tenant/endpoint.
- Verify payload equivalence when reusing a key.
- Rate-limit to prevent spam.
- Prevent clients from using someone else's key to read notification status.

Idempotency does not replace authentication, authorization, and rate limiting.

### Protecting Outbox Payloads

If the outbox stores email addresses, invoice details, or confirmation links:

- Restrict table read/write permissions.
- Use storage-level or field-level encryption where required.
- Never leak secrets into exceptions or logs.
- Purge or redact payloads after policy retention limits.
- Keep enough audit data for reconciliation without holding sensitive content too long.

A worker should never pull unvalidated sender or recipient info from an untrusted payload to send arbitrary emails; the notification-preparing service must enforce business policies before writing to the outbox.

## 21. Testing the "Server Accepted, Client Timed Out" Scenario

To verify duplicate prevention, testing `mailSender.send(...)` succeeding or throwing a pre-connect exception is not enough.

**The most important scenario** to simulate:

1. The provider records/accepts the submission.
2. The client receives no success confirmation.
3. The application records `UNKNOWN`.
4. The worker restarts or the retry schedule runs.
5. The same notification **is not automatically resent** under a hold-on-unknown policy.

### A Fake Transport Simulating Unknown Outcomes

The Java example below illustrates fault injection at the provider boundary:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class FakeAmbiguousMailTransport {

    private final AtomicInteger acceptedCount = new AtomicInteger();

    public void sendAndLoseAcknowledgement(String notificationId) {
        // Simulate server having accepted submission.
        acceptedCount.incrementAndGet();

        // Client does not receive success outcome.
        throw new AmbiguousMailSubmissionException(
                "Server accepted but final acknowledgement was lost"
        );
    }

    public int acceptedCount() {
        return acceptedCount.get();
    }
}
~~~

~~~java
public class AmbiguousMailSubmissionException
        extends RuntimeException {

    public AmbiguousMailSubmissionException(String message) {
        super(message);
    }
}
~~~

This is a **test fake transport**, not a real `JavaMailSender`. It simulates a world where the external effect succeeded while the app-side response failed. Tests should verify the worker moves the notification to `UNKNOWN` and **does not invoke the transport again** under a no-retry-on-unknown policy.

Test expectations:

~~~text
Accepted count after attempt #1 = 1
Outbox status                   = UNKNOWN
Job eligible for auto-retry     = false

After running worker schedule again:
Accepted count                  = 1
Outbox status                   = UNKNOWN
~~~

### Scenarios to Simulate

| Scenario | Simulation condition | Expectation |
| --- | --- | --- |
| **Error before transmitting message** | Zero message bytes reached server, with proof | Retryable per policy |
| **Timeout after DATA** | Server received it, final ACK lost | `UNKNOWN`, no blind resend |
| **SMTP 250 received** | Client receives success acknowledgement | `ACCEPTED` |
| **Crash before markAccepted** | Server received it; DB still `IN_FLIGHT` | Lease expired -> `UNKNOWN` |
| **Two duplicate events** | Same tenant + notification key | One outbox row via unique constraint |
| **Two claiming workers** | Both polling simultaneously | Only one worker claims a row at a time |
| **Lease expired** | Worker slow or dead | Do not assume unsent |
| **Stale worker update** | Lease token changed | `UPDATE` rejected, newer state preserved |
| **Duplicate provider webhook** | Same `providerEventId` twice | Processed once in event store |
| **Late provider webhook** | `ACCEPTED` recorded, `DELIVERED` arrives later | Valid forward transition, no reset |
| **Key reused with different payload** | Same idempotency key, different data | Conflict error / investigate |
| **Intentional resend** | User requests fresh send | New notification linked to original |

### Do Not Just Mock send() Throwing Timeout Immediately

If a test only mocks:

~~~java
doThrow(new RuntimeException("timeout"))
        .when(mailSender).send(any(MimeMessage.class));
~~~

the test only proves the program catches exceptions. It does not prove safety when **an external side effect already occurred**. Use a fake transport / state-machine test capable of recording provider acceptance before the client loses the acknowledgement.

### Testing Real DB Transactions and Unique Constraints

Unit-testing an `existsByKey(...)` method does not replace integration tests on `UNIQUE` constraints. When multiple instances receive events concurrently, only database transactions and unique constraints provide a duplicate-insert barrier under concurrency.

Run integration tests on a database with production-equivalent semantics, especially when using PostgreSQL `ON CONFLICT` and `FOR UPDATE SKIP LOCKED`. Never assume an in-memory map or H2 faithfully reproduces PostgreSQL row locking.

### Testing Worker Crashes and Recovery

A test can:

1. Claim a notification into `IN_FLIGHT`.
2. Skip calling `markAccepted` or `markUnknown` (simulating process death).
3. Expire the lease using a fake clock or test database timestamp.
4. Run the recovery job.
5. Assert the job transitions to `UNKNOWN`.
6. Assert the SMTP transport is not called again solely due to lease expiration.

Do not use long `Thread.sleep(...)` calls to wait for real leases to expire. Inject a `Clock` or insert a past `lease_until` for fast, deterministic tests.

## 22. Recovery Job Handling Expired IN_FLIGHT Rows

A production system needs to detect `IN_FLIGHT` jobs whose workers stopped responding.

SQL example:

~~~sql
UPDATE mail_outbox
SET status = 'UNKNOWN',
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = 'LEASE_EXPIRED',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND lease_until < CURRENT_TIMESTAMP
RETURNING id, notification_key;
~~~

Do not reset to `PENDING` here. `LEASE_EXPIRED` only tells you the worker's lease timed out, not that the SMTP server never received the message.

### Recovery When the Old Worker Is Still Alive

A worker might block on network I/O longer than the lease, or pause during GC. The recovery job marks `UNKNOWN` while the worker is still trying to send.

To reduce this:

- Configure sensible SMTP timeouts.
- Size leases above worst-case task duration plus a safety margin.
- Renew leases with heartbeats for tasks designed to run long.
- Use lease tokens to stop stale workers from overwriting DB results.
- Never immediately grant a new send attempt upon transitioning to `UNKNOWN`.

Fencing/leases coordinate workers; **they cannot abort an email already sent to an SMTP server**. An evicted worker stripped of DB write permissions can still complete an external send.

### When an Old Worker Reports Success After the Job Became UNKNOWN

If the worker has clear evidence from its earlier send and still holds its attempt identity, the system can record a separate **late outcome** for reconciliation to review. Never blindly force `ACCEPTED` if doing so bypasses token checks or erases attempt history. A reconciler can use that evidence to transition `UNKNOWN -> ACCEPTED` under controlled rules.

## 23. Two Layers of Idempotency Across the Whole Business Flow

When a user clicks "Place Order," timeouts can occur **at multiple boundaries**, not only during SMTP sending.

### Timeout on the Order-Creation HTTP Request

~~~text
Browser                  Spring API                  Database
   |                         |                          |
   |--- POST /orders ------->|                          |
   |                         |--- INSERT order -------->|
   |                         |<---------- commit -------|
   |      X timeout          |                          |
   |                         |                          |
   |--- POST /orders retry ->|                          |
~~~

Without API idempotency, retrying the request can create **two distinct orders**, each with its own confirmation email. In that case, the mail outbox cannot tell the two orders are business duplicates because they have different order IDs.

Hence there are two layers:

1. **Business command idempotency**: repeating order creation or payment does not create a duplicate business entity when the client retries.
2. **Notification idempotency**: repeating the same business event does not create extra email jobs or blindly replay after an SMTP timeout.

Both are required for end-to-end duplicate prevention.

### One Key Should Not Serve Every Endpoint

The idempotency key passed by the client to `POST /orders` does not have to be the exact identifier used for sending the email:

~~~text
Business operation key:
  order-create-request-uuid

Email notification key:
  ORDER_CONFIRMED:ORD-1528:v1:recipient-392
~~~

The business key protects Order creation; the notification key protects the notification. They can link via Order ID and event ID while keeping separate scopes and retention windows.

### Never Generate a New Verification Code When Only Retrying Mail

An important example:

~~~text
OTP send #1 -> code 123456 -> SMTP timeout UNKNOWN
Retry          -> generates code 654321 -> sends again
~~~

If the recipient receives both emails, they will not know which code is valid. Retrying the same notification must use **the same generated code/event** as long as it remains valid and meets security policy. If the old code expired or must be rotated, that is a **new OTP generation request** requiring a new event and clear invalidation of old codes.

Never let an email retry re-execute token-generation side effects unless business rules explicitly define that boundary.

## 24. Runbook for Handling UNKNOWN Notifications

An operational dashboard should display per-notification details:

~~~text
Notification ID       6b91...
Business event        ORDER_CONFIRMED
Order ID              ORD-1528
Recipient             (partially masked)
Status                UNKNOWN
Attempt               #1
Error                 SMTP_READ_TIMEOUT
First attempted at    ...
Correlation ID        mail-job-6b91...
Provider evidence     NOT_YET_AVAILABLE
Action                RECONCILE / ESCALATE
~~~

Handling procedure:

1. Identify **notification key, event ID, recipient, and attempt timestamp**.
2. Inspect application logs to see which stage has evidence of failing.
3. Query provider APIs, webhooks, or SMTP logs by correlation ID / `Message-ID` if supported.
4. If evidence shows the provider accepted it, transition to `ACCEPTED` without retrying.
5. If evidence shows the provider never received it, transition to `RETRYABLE_FAILED`/`PENDING` per policy.
6. If still unclear, keep `UNKNOWN` and alert if exceeding time thresholds.
7. If the business forces a resend, explicitly record **the decision accepting duplicate risk** and create a new attempt with an audit trail.
8. Never delete attempt history or silently change `UNKNOWN` to `PENDING`.

### Restricting Manual Actions

The **Retry** button in an admin console should not always be enabled for `UNKNOWN`. Require:

- Appropriate staff permissions.
- Reason for retry/resend.
- Warning prompt: "the previous email may already have been received."
- Audit record of actor, timestamp, and notification ID.
- Explicit choice between adding an attempt to the old notification or creating a new resend notification.

In particular, never let staff click retry repeatedly on the same payment/OTP event without seeing its full state and attempt history.

## 25. Common Mistakes

### Mistake 1 — Immediately Resending on Every Timeout

The application may send duplicates if the server received the first copy and the `250` reply was lost.

**Fix:** separate failures proven not accepted from `UNKNOWN` outcomes; auto-retry only when safe conditions or an explicit risk policy applies.

### Mistake 2 — Treating Message-ID as an SMTP Deduplication Key

The `Message-ID` header aids identification/tracing, yet SMTP does not compel servers to drop messages with identical IDs.

**Fix:** use `Message-ID` for correlation, never as sole proof of idempotency.

### Mistake 3 — Minting a New Idempotency Key on Each Retry

Every attempt looks like a brand-new notification, making duplicate detection impossible.

**Fix:** create the notification ID/key once when inserting into the outbox; only the attempt ID changes.

### Mistake 4 — Deduplicating Only With an exists Check in Java

Two processes can both see "not found" and create two jobs.

**Fix:** enforce a `UNIQUE` constraint in the database and use atomic insert/upsert.

### Mistake 5 — Outbox With Only PENDING/SENT/FAILED

Timeouts get forced into `FAILED` and retried by the scheduler, hiding the possibility that the message was accepted.

**Fix:** include an `UNKNOWN` state and dedicated reconciliation workflow.

### Mistake 6 — Immediately Moving Expired Leases Back to PENDING

The worker may have succeeded over SMTP before dying without persisting the result.

**Fix:** transition expired leases to `UNKNOWN` when the outcome is unknown, instead of auto-replaying.

### Mistake 7 — Holding a Transaction Open During SMTP Sends

Connections and row locks stay held during slow network calls, bottlenecking the database.

**Fix:** commit the claim, perform SMTP outside the DB transaction, and commit the outcome in a short transaction.

### Mistake 8 — Thinking Fencing Tokens Prevent External Duplicates

Fencing only stops stale workers from writing wrong DB states; it cannot block messages already sent to SMTP.

**Fix:** combine leases, timeouts, `UNKNOWN`, and provider idempotency/reconciliation.

### Mistake 9 — Enabling @Retryable Across All of JavaMailSender.send(...)

An interceptor can repeat a call whose external side effect already occurred.

**Fix:** restrict retries to proven failure types and idempotent boundaries.

### Mistake 10 — Assuming @Async or AFTER_COMMIT Is Durable Enough

In-memory callbacks and executors are lost on process shutdown. Moreover, post-commit SMTP errors cannot roll back the database.

**Fix:** use an outbox/durable queue for notifications needing retries and recovery.

### Mistake 11 — Believing JavaMailSender Returning Means Delivered

The transport may accept submission while the message bounces or gets blocked later.

**Fix:** distinguish `ACCEPTED` from `DELIVERED` and track provider events when needed.

### Mistake 12 — Assuming "Message Not Found" at Provider Means Unsent

Indexing and event pipelines can lag; search retention may differ from submission retention.

**Fix:** understand provider lookup semantics; do not treat temporary absence as absolute proof.

### Mistake 13 — One Sent Flag for a Multi-Recipient Email

Per-recipient outcomes can differ. Retrying the whole group sends duplicates to accepted recipients.

**Fix:** track per-recipient state or split into individual notifications if business rules permit.

### Mistake 14 — Minting a New Token When Retrying an Old Email

Recipients can receive multiple emails with different codes and not know which is valid.

**Fix:** retries of the same logical notification reuse the generated snapshot; issuing a new token is an intentional new event.

### Mistake 15 — Purging Dedupe Keys Too Early

An event replayed after the retention period can create a new mail job.

**Fix:** choose retention covering replay, retry, reconciliation windows, and data-retention obligations.

### Mistake 16 — Ignoring Duplicate Provider Webhooks

Delivery events may be delivered multiple times, causing repeated status updates or side effects.

**Fix:** enforce a unique provider event ID, verify webhooks, and make state transitions idempotent.

## 26. Scenario Exercises

### Scenario A — Read Timeout After DATA

The SMTP client finished transmitting the MIME body; the application hit a read timeout waiting for the final response.

**Question:** should `JavaMailSender` be called again immediately?

**Answer:** no, if it is unknown whether the provider accepted it. Record `UNKNOWN` and reconcile via provider/logs if available. If reconciliation is impossible, any retry decision must explicitly acknowledge duplicate risk.

### Scenario B — Server Returned 250, Database Update Failed

`JavaMailSender` completed, yet transitioning the outbox to `ACCEPTED` failed due to a database timeout.

**Question:** the outbox stays `IN_FLIGHT`; should a new worker resend?

**Answer:** it should not auto-resend when the lease expires. Worker/provider evidence exists even though DB state was not saved; recovery transitions to `UNKNOWN` and the reconciler uses that evidence to mark `ACCEPTED`.

### Scenario C — Two Instances Receive OrderConfirmedEvent Simultaneously

Both application instances process the same event ID.

**Question:** is checking `existsByKey` then inserting enough?

**Answer:** no, due to race conditions. Use `UNIQUE (tenant_id, notification_key)` in the database and atomic insert/upsert.

### Scenario D — Two Workers Claim One Job

Workers A and B poll the outbox table concurrently.

**Question:** how do we stop both from sending the same job?

**Answer:** atomic claims via row locking / compare-and-set or appropriate queue semantics. Never run `SELECT` and send directly without claiming.

### Scenario E — A Worker Stalls Past Lease Expiry

The job becomes `UNKNOWN`, yet the stale worker later receives SMTP `250`.

**Question:** what does the lease token solve?

**Answer:** it blocks the stale worker from overwriting DB state after losing ownership. It does not cancel the email SMTP already accepted; late outcomes should be recorded/reconciled per design.

### Scenario F — Same Message-ID Across Two SMTP Submissions

Two emails share the same `Message-ID` header, yet the server accepts both.

**Question:** did the server violate SMTP?

**Answer:** no universal SMTP rule forces servers to deduplicate by `Message-ID`. The header is identifying metadata; provider-side duplicate prevention requires a true idempotency contract.

### Scenario G — Provider Offers an Idempotency API

The first request timed out after the provider accepted it. The API documents retaining idempotency keys for a fixed period.

**Question:** which key should the retry send?

**Answer:** reuse **the stable notification key** and equivalent payload within the provider's documented semantics and TTL. Never pass a fresh attempt ID as the idempotency key.

### Scenario H — Message Not Found Immediately When Querying Provider

After a read timeout, querying the search API returns "not found" in the first few seconds.

**Question:** can we conclude it was not sent?

**Answer:** no, if the provider has indexing delays or eventual consistency. Keep `UNKNOWN` and re-reconcile per the provider's SLAs/semantics.

### Scenario I — User Clicks "Resend Invoice"

An invoice was sent successfully yesterday, and the user explicitly asks for another copy.

**Question:** should the old unique key block this?

**Answer:** no, if business rules permit resends. Create a new notification with a distinct resend event ID linked to the original notification and enforce rate limits.

### Scenario J — Multiple Recipients, One Fails

A message is sent to A and B; the provider confirms A succeeded while B was rejected.

**Question:** is retrying the entire message safe?

**Answer:** it can send a duplicate to A. Track per-recipient outcomes and retry only what was genuinely not accepted, or design one notification per recipient.

### Scenario K — OTP Expires While Outbox Is UNKNOWN

The first SMTP call had an unknown outcome; after some time, the OTP expired.

**Question:** should the old OTP content be retried?

**Answer:** it is likely no longer meaningful. Close the old notification per policy, and if requested by the user, emit a new OTP event with a new token while properly managing token validity.

### Scenario L — Order-Creation API Also Timed Out

The client retries `POST /orders`, creating a second Order ID and a second confirmation email.

**Question:** is a mail outbox unique key on Order ID enough?

**Answer:** no. Two different Order IDs validly generate two notifications under that key. You also need business command idempotency on the order-creation endpoint.

## 27. Reference Architecture: From Business Event to Safer Email Delivery

~~~text
                    API / Business Event
                             |
                             v
                 Validate business operation
                             |
                             v
                   BEGIN TRANSACTION
                             |
                 +-----------+-----------+
                 |                       |
                 v                       v
            Save business          Insert Outbox
            state once             UNIQUE logical key
                 |                       |
                 +-----------+-----------+
                             |
                             v
                           COMMIT
                             |
                             v
                    Outbox dispatcher
                             |
                             v
                   Atomic claim + lease
                             |
                             v
                   Durable attempt record
                             |
                             v
                         DB COMMIT
                             |
                             v
                    Submit email via SMTP
                             |
           +-----------------+-----------------+
           |                 |                 |
           v                 v                 v
      ACK accepted     Proven rejection     No reliable ACK
           |                 |                 |
           v                 v                 v
       ACCEPTED          RETRYABLE/          UNKNOWN
                         PERMANENT             |
                                              v
                                       Reconciliation
                                              |
                        +---------------------+------------------+
                        |                     |                  |
                        v                     v                  v
                   ACCEPTED            Safe to retry      Needs review
~~~

### Practical Guarantees of This Design

| Mechanism | What it improves | Remaining limitation |
| --- | --- | --- |
| **Business idempotency** | Prevents duplicate business operations on client retries | Does not directly prevent SMTP duplicates |
| **Outbox + UNIQUE key** | Prevents multiple logical notifications from one event | Does not prevent duplicate external submissions after crashes |
| **Atomic claim + lease** | Reduces parallel worker sends of one job | Lease expiry does not prove outcome |
| **Attempt log** | Provides history for investigation and recovery | Logs are not proof of server acceptance |
| **UNKNOWN state** | Prevents auto-retrying when outcome is unknown | May delay unsent notifications |
| **Provider reconciliation** | Can determine accepted vs. not accepted | Depends on provider APIs/logs and consistency |
| **Provider idempotency** | Can reduce duplicates at the send boundary | Depends on provider capability, scope, and TTL |
| **Backoff + retry limits** | Prevents overload on temporary errors | Does not turn an ambiguous outcome into a safe retry |
| **Idempotent webhooks** | Prevents duplicate processing of delivery events | Does not prove the recipient read the email |

### Rules to Remember

~~~text
Timeout != not sent
Message-ID != SMTP idempotency guarantee
Outbox UNIQUE != exactly-once external send
Lease expired != definitely not accepted
SMTP 250 != Inbox delivered
Retry != reconciliation

One logical notification -> one stable key
One send attempt -> one new attempt ID
Unknown outcome -> UNKNOWN
UNKNOWN -> reconciliation or explicit risk policy
~~~

**Preventing duplicates after unknown-outcome timeouts** cannot rely on a `catch` block and a few retries of `JavaMailSender`. You must design from **the business identity of a notification**, prevent duplicate job creation with unique keys, log attempts prior to external I/O, claim jobs atomically, represent missing evidence with `UNKNOWN`, and reconcile with the provider before retrying when possible. Plain SMTP offers no universal idempotency mechanism; `Message-ID` does not replace provider deduplication. When the outcome cannot be determined, the system must make an explicit choice between risking **a duplicate send** and risking **a missed notification**—a limit managed through policy, durable state, observability, and operational runbooks rather than hidden behind automatic retries.
