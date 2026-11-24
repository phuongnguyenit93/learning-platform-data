# Mail Command and Message Key

In Spring Framework Mail, calling `JavaMailSender.send(...)` lets an application submit an email to an SMTP server. However, a production system must answer more questions: which business workflow originated that email, who needs to receive it, has it been scheduled yet, which worker is sending it, how many times has it been retried, and what happens when **the same request is received twice**?

Suppose the application emits an `OrderConfirmed` event:

~~~text
OrderConfirmed(eventId=evt-123, orderId=A123)
    |
    v
Consumer creates confirmation email send request
    |
    +-- Attempt 1: INSERT mail job succeeds
    |              but consumer crashes before acking broker
    |
    +-- Attempt 2: broker redelivers the same evt-123
                   consumer runs one more time
~~~

If every handler execution creates a new mail job, the buyer may receive two confirmation emails. Conversely, using an overly broad key such as `order-A123` may cause the invoice or shipping email for the same order to be wrongly blocked as a duplicate.

**Mail command** and **message key** are two foundational components for solving those problems:

- **Mail command** describes a business *send intent*: tenant, recipient, notification type, template, payload, send time, and source identifier.
- **Message key** uniquely identifies *one logical send request* within the defined scope; every reprocessing of the same request must reuse this key.
- **Durable mail job/outbox** stores the request and its state in the database, allowing workers to send or retry independently of HTTP requests or broker consumers.

**Important limitation:** a message key prevents creating duplicate logical jobs. It **does not by itself guarantee exactly-once SMTP delivery**. The database and SMTP do not share a transaction; when SMTP has already accepted the message but the application loses the response, retrying can still send duplicates. Production design must make this boundary explicit.

## 1. Separating the command from MIME email and transport

A system can be organized as follows:

~~~mermaid
flowchart LR
    A["Business event / API"] --> B["MailCommand"]
    B --> C["Command gateway"]
    C --> D["Durable mail outbox"]
    D --> E["Mail worker"]
    E --> F["MimeMessage + JavaMailSender"]
    F --> G["SMTP / provider"]
    G --> H["Delivery events"]
~~~

| Component | Responsibility | Should not do |
| --- | --- | --- |
| Business service | Identify the event and sending need | Call SMTP inside a business transaction and assume it is safe |
| Mail command | Describe a structured send intent | Hold a live SMTP connection or stream |
| Command gateway | Validate, deduplicate, persist request | Resend when seeing a duplicate |
| Outbox/job store | Hold state, schedule, retry, audit | Delete requests on restart |
| Worker | Claim job, render MIME, call transport | Generate a new message key per attempt |
| Provider event handler | Normalize delivery/bounce/complaint | Treat every submitted email as delivered |

`MimeMessage` is a Jakarta Mail object containing headers, body, and MIME parts. It can be mutable and depends on `Session` and attachment resources. **Do not use raw `MimeMessage` as a business command** or treat `MimeMessage.getMessageID()` as the system's idempotency key.

## 2. Distinguishing identifier types

During sending, there are multiple IDs with distinct meanings:

| Identifier | Example | Scope |
| --- | --- | --- |
| Business event ID | `evt-123` | One business event |
| Message key | `order-confirmation:evt-123:recipient-9` | One logical mail intent |
| Mail job ID | `job-91b...` | One outbox record |
| Attempt ID | `attempt-4ea...` | One SMTP/API send attempt |
| RFC Message-ID | `<opaque@mailer.example>` | Header inside the MIME email |
| Provider message ID | `provider-abc...` | Submission/delivery at the ESP |
| Correlation/trace ID | `trace-8c2...` | Request/log tracing |

### 2.1. Message key differs from job ID

~~~text
messageKey = order-confirmation:evt-123:recipient-9
jobId      = 7f84f55a-...
~~~

A Job ID can be generated when inserting the row for the first time. When the broker redelivers `evt-123`, the command must carry the **same message key** so the gateway returns the existing job ID instead of creating a new job.

Do not generate a message key with `UUID.randomUUID()` inside the consumer each time an event is received. A random UUID is suitable for a **job ID**, or for an **event ID generated and persisted once at the source**.

### 2.2. Message key differs from RFC Message-ID

~~~java
MimeMessage mime = mailSender.createMimeMessage();
// Set From, To, Subject, Content...
mime.saveChanges();
String mimeId = mime.getMessageID();
~~~

`Message-ID` is a header defined by Internet Message Format. Jakarta Mail may generate it during save/serialization; when a retry builds a new MIME message, the value may differ. Providers may also handle this header according to their own policies.

**Do not use this value as the primary key of a send request before enqueuing.** Email receivers do not by default drop duplicate emails merely because two messages share the same Message-ID header.

### 2.3. Provider ID may only appear after submission

An ESP may return an ID for reconciling delivery webhooks. Plain SMTP does not always provide a message ID in a form the application can read. A job retried across two providers may receive two provider IDs.

Store the mapping as:

~~~text
tenantId + messageKey
    -> mailJobId
        -> attemptId #1 -> providerMessageId A
        -> attemptId #2 -> providerMessageId B
~~~

### 2.4. Correlation ID is for tracing

One HTTP request can create three mail commands; one job can retry across multiple traces. Therefore, a correlation ID is not by itself a logical mail key. They can be linked, but **do not replace each other**.

## 3. What should a MailCommand contain?

Example command:

~~~text
MailCommand {
  tenantId:          tenant-17
  messageKey:        order-confirmation:evt-123:recipient-9
  sourceEventId:     evt-123
  mailType:          ORDER_CONFIRMATION
  recipientId:       recipient-9
  recipientAddress:  alice@example.net
  senderProfile:     TX_PRIMARY
  templateId:        order-confirmation
  payloadRef:        order-snapshot:A123:v1
  notBefore:         2026-11-12T10:00:00Z
  expiresAt:         null
}
~~~

| Field | Meaning | Production note |
| --- | --- | --- |
| `tenantId` | Owner and data boundary | Must be authenticated/authorized |
| `messageKey` | Idempotency key | Stable across retries |
| `sourceEventId` | Source event | Helps with audit/correlation |
| `mailType` | Notification type | Bounded enum |
| `recipientId` | Recipient identifier | Can be safer than email in keys |
| `recipientAddress` | SMTP address | PII, must be protected at rest |
| `senderProfile` | Sender configuration | Must not contain SMTP passwords |
| `templateId` | Template identifier | Must belong to an allowlist |
| `payloadRef` | Reference to snapshot/render inputs | Has retention/lifetime |
| `notBefore` | Do not send before this time | Use `Instant` |
| `expiresAt` | Do not send after deadline | Important for OTP |

### 3.1. Immutable value object in Java 17+

~~~java
package com.example.mail.command;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record MailCommand(
        UUID tenantId,
        String messageKey,
        UUID sourceEventId,
        UUID recipientId,
        String recipientAddress,
        MailType mailType,
        SenderProfile senderProfile,
        String templateId,
        String payloadRef,
        Instant notBefore,
        Instant expiresAt) {

    public MailCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(messageKey);
        Objects.requireNonNull(recipientId);
        Objects.requireNonNull(recipientAddress);
        Objects.requireNonNull(mailType);
        Objects.requireNonNull(senderProfile);
        Objects.requireNonNull(templateId);
        Objects.requireNonNull(payloadRef);
        Objects.requireNonNull(notBefore);

        if (messageKey.isBlank() || messageKey.length() > 240) {
            throw new IllegalArgumentException(
                    "Invalid message key");
        }
        if (recipientAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }
        if (expiresAt != null && !expiresAt.isAfter(notBefore)) {
            throw new IllegalArgumentException(
                    "Expiration must be after notBefore");
        }
    }
}
~~~

Enums:

~~~java
public enum MailType {
    ORDER_CONFIRMATION,
    INVOICE,
    PASSWORD_RESET,
    OTP,
    NEWSLETTER,
    PROMOTION
}

public enum SenderProfile {
    TX_PRIMARY,
    MARKETING_PRIMARY
}
~~~

This is a data model; the gateway must still validate email syntax, tenant membership, per-sender policies, template authorization, size limits, and consent.

A `record` prevents modifying field references after creation, but **does not automatically make mutable `Map`, `List`, `byte[]`, or entity internals deeply immutable**. If a command contains collections, create immutable copies; for large payloads, use immutable snapshots/references.

### 3.2. A command is not an SMTP request

`MailCommand` only describes an intent. Building `MimeMessage`, adding `From`, `Subject`, `Content-ID`, attachments, and calling `JavaMailSender` belong to the worker/transport adapter. This lets you switch providers or change rendering without turning the command into an object tied to a live connection.

## 4. Designing business-driven message keys

A good message key has these properties:

1. **Stable:** the same business intent always produces the same key.
2. **Sufficiently distinct:** no ambiguity across mail types, recipients, or occurrences.
3. **Tenant scoped:** does not let another tenant cause unintended collisions.
4. **Retry-independent:** attempt 1 and attempt 5 share the same key.
5. **Independent of pod, processing timestamp, or fresh random values.**
6. **Does not contain OTPs, reset tokens, recipient emails, or unnecessary PII.**
7. **Has a versioned contract:** algorithm changes must handle the previous idempotency window.

Example:

~~~text
(tenantId, messageKey)

messageKey =
    mailType + ":" + businessEventId + ":" + recipientId
~~~

For fixed-format components like UUIDs and enums, `:` is easy to use. If keys are built from free-form strings that may contain the delimiter, use length-prefixing or canonical serialization so two different tuples cannot produce the same string.

### 4.1. A factory that does not use current time

~~~java
import java.util.Objects;
import java.util.UUID;

public final class MailKeys {
    private MailKeys() {}

    public static String orderConfirmed(
            UUID eventId,
            UUID recipientId) {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(recipientId);
        return "order-confirmation:"
                + eventId + ":" + recipientId;
    }

    public static String invoiceIssued(
            UUID invoiceEventId,
            UUID recipientId) {
        Objects.requireNonNull(invoiceEventId);
        Objects.requireNonNull(recipientId);
        return "invoice:"
                + invoiceEventId + ":" + recipientId;
    }
}
~~~

Caller:

~~~java
String key = MailKeys.orderConfirmed(
        event.id(),
        customer.id());
~~~

Prerequisite: `event.id()` must be generated **once and persisted durably** at the business source. If the producer assigns a new ID each time it publishes the same event, the consumer cannot tell on its own that they represent the same intent.

### 4.2. Common bad keys

~~~java
// Wrong: changes on every consumer retry.
String key1 = UUID.randomUUID().toString();

// Wrong: changes every second, even for the same event.
String key2 = "order:" + orderId + ":" + Instant.now();

// Wrong: all email types for the order collide on the same key.
String key3 = "order:" + orderId;

// Wrong: puts secrets into database indexes/logs.
String key4 = "otp:" + otpValue + ":" + emailAddress;
~~~

Do not use subject/body hashes as the primary identity. Two valid requests may have identical content; conversely, a retried intent may be rendered with a different template version depending on policy.

### 4.3. Namespace and unique scope

~~~text
Tenant A: invoice:evt-12:recipient-8
Tenant B: invoice:evt-12:recipient-8
~~~

Two identical strings can be two valid requests in different tenants. Therefore, the database usually enforces:

~~~sql
UNIQUE (tenant_id, message_key)
~~~

Tenant ID must come from a trusted context, not merely from an arbitrary request field.

### 4.4. Should template version be part of the key?

Usually you **should not** include template version in identity if the same business event/recipient should only be sent once. If template v1 is upgraded to v2 after a deployment, a new handler processing the same old event could generate a different key and send a second time.

Template version should be stored as **command/payload metadata**, while identity changes only when there is a **newly approved send intent**.

## 5. Single recipient or multiple recipients?

The definition of logical intent must be consistent.

### 5.1. One command per recipient

~~~text
OrderConfirmed event E
    -> Recipient A: key=order-confirmation:E:A
    -> Recipient B: key=order-confirmation:E:B
    -> Recipient C: key=order-confirmation:E:C
~~~

Each recipient has its own job and state. Advantages:

- check suppression/consent per recipient;
- retries do not resend to the entire group;
- track bounce/delivery individually;
- avoid leaking recipient lists via To/Cc;
- avoid ambiguity from partial SMTP acceptance.

### 5.2. One MIME message sent to multiple people

For an email containing To, Cc, and Bcc, the logical intent can be **a group of recipients**. In that case, the command must describe the list accurately, and the payload fingerprint must include recipient identities according to defined rules.

SMTP may accept some recipients while rejecting others. `MailSendException` does not always mean none of the recipients were sent to. If the business requires accurate per-recipient retry/delivery, consider **per-recipient jobs** or a separate recipient-outcome table.

### 5.3. Newsletters by occurrence

Example:

~~~text
scheduleId    = weekly-newsletter
occurrenceKey = 2026-W46
recipientId   = subscriber-9
messageKey    = newsletter:2026-W46:subscriber-9
~~~

If the generator crashes and restarts, the same occurrence and subscriber still produce the same key. The next week has a new occurrence key and is validly sent.

Do not use `scheduleVersion` as the sole component distinguishing an occurrence: changing cron or template could cause the same weekly newsletter to be generated twice.

## 6. Retry, resend, and reschedule are three distinct workflows

| Scenario | Same send intent? | Message key handling |
| --- | --- | --- |
| Broker redelivery of same event | Yes | Keep unchanged |
| HTTP retry after timeout | Yes | Keep unchanged |
| Worker SMTP 4xx retry | Yes | Keep unchanged |
| Provider switch during failover | Yes | Keep unchanged |
| User edits scheduled time before job starts | Yes, if policy allows | Keep key, update versioned schedule |
| User requests resending an already sent invoice | New intent | New resend operation key |
| User requests a new OTP/challenge | New intent | New challenge ID |
| Next week's newsletter | New intent | New occurrence key |

### 6.1. Valid resend

Suppose a sent invoice has:

~~~text
messageKey=invoice:evt-issued-1:recipient-9
state=SUBMITTED
~~~

The user clicks **Resend** one week later. If the old key is reused, the gateway will return the already submitted job and will not generate a new email. Create a separate *resend intent*:

~~~text
ResendRequested(requestId=resend-789)
messageKey=invoice-resend:resend-789:recipient-9
~~~

`resend-789` must be generated and persisted **once per resend request**, so HTTP retries of that same resend operation still use this key.

### 6.2. OTP and password reset

Do not use `otp:userId` for every OTP issuance. A new challenge should have a new challenge ID and a new message key. However, retrying the same challenge must keep the old key. Do not put actual OTP codes in keys, headers, or logs.

### 6.3. Reschedule keeps the key

If an unstarted job is moved from 10:00 to 11:00, update `scheduled_at` with state/expected-version preconditions and auditing, **without creating a new job ID or message key**.

Do not treat resending `MailCommand` with the same key and a different `notBefore` as a reschedule command. Submitting a command and rescheduling a job are two separate APIs and need explicit contracts.

## 7. Duplicate with the same key but different payload

Dangerous example:

~~~text
Request A:
  key=invoice:evt-123:recipient-9
  recipient=alice@example.net
  invoiceAmount=100

Request B:
  key=invoice:evt-123:recipient-9
  recipient=bob@example.net
  invoiceAmount=900
~~~

If the repository sees an existing key and returns success **without checking the payload**, a serious bug is hidden.

Rule:

- **Same key, same intent, and equivalent immutable fields:** return the existing job, do not create a new job.
- **Same key, different immutable fields:** raise `IDEMPOTENCY_CONFLICT`, do not silently update.

### 7.1. Fingerprint is an aid, not the sole identity

You can store:

~~~text
payload_fingerprint =
    SHA-256(canonical immutable command fields)
~~~

Requirements:

- deterministic serialization with fixed field order;
- use UTF-8 and stable timezone/Instant formatting;
- exclude dynamic trace ID, attempt count, and createdAt;
- include a canonicalization version for safe upgrades;
- do not assume hashing replaces authorization/validation;
- consider HMAC or comparing protected IDs if payload is sensitive or low-entropy.

In particular, fields **intentionally allowed to change** (such as `scheduled_at` via the reschedule API) should not cause duplicate retries to report a conflict just because the current record was rescheduled. You can store the immutable **original command fingerprint** separately from **mutable job scheduling state**.

### 7.2. Do not overwrite a job on key collision

An upsert such as:

~~~sql
ON CONFLICT (tenant_id, message_key)
DO UPDATE SET
    state = 'PENDING',
    recipient_address = EXCLUDED.recipient_address;
~~~

is dangerous: a duplicate event can reset a `SUBMITTED` job back to `PENDING` and resend it, or overwrite the recipient of an existing job.

Idempotent insert should **DO NOTHING, then read and compare the existing job**. Request modification must be a separate workflow with authorization, state preconditions, and audit.

## 8. Persisting commands as a durable outbox

PostgreSQL example:

~~~sql
CREATE TABLE mail_outbox (
    id                  UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    message_key         VARCHAR(240) NOT NULL,
    source_event_id     UUID,
    mail_type           VARCHAR(80) NOT NULL,
    recipient_id        UUID NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    sender_profile      VARCHAR(80) NOT NULL,
    template_id         VARCHAR(120) NOT NULL,
    payload_ref         VARCHAR(400) NOT NULL,
    command_fingerprint VARCHAR(128) NOT NULL,
    state               VARCHAR(40) NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ,
    lease_owner         VARCHAR(120),
    lease_until         TIMESTAMPTZ,
    lease_version       BIGINT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_outbox_tenant_message
        UNIQUE (tenant_id, message_key)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (state, scheduled_at, next_attempt_at);

CREATE INDEX idx_mail_outbox_tenant_created
    ON mail_outbox (tenant_id, created_at DESC);
~~~

This is an illustrative schema and does not yet include production-grade encryption, partitioning, or retention. `recipient_address` and `payload_ref` can be sensitive data requiring access control and retention limits.

### 8.1. Unique constraint is the barrier against duplicates

The check-then-insert approach:

~~~java
if (!repository.existsByMessageKey(key)) {
    repository.save(newJob);
}
~~~

is insufficient when two threads run concurrently:

~~~text
Thread A: SELECT key -> missing
Thread B: SELECT key -> missing
Thread A: INSERT
Thread B: INSERT
~~~

The `UNIQUE (tenant_id, message_key)` database constraint enforces uniqueness under contention and across multiple application replicas.

### 8.2. Attempt table

~~~sql
CREATE TABLE mail_attempt (
    id                  UUID PRIMARY KEY,
    mail_job_id         UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_number      INTEGER NOT NULL,
    provider            VARCHAR(80) NOT NULL,
    transport_result    VARCHAR(40) NOT NULL,
    provider_message_id VARCHAR(200),
    error_class         VARCHAR(60),
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    UNIQUE (mail_job_id, attempt_number)
);
~~~

One mail job can have many attempts; do not use attempt ID in place of message key.

### 8.3. Separating job state from delivery state

Example:

~~~text
PENDING -> CLAIMED -> SUBMITTING -> SUBMITTED
                                   |
                                   +-- later via provider webhook
                                       DELIVERED / BOUNCED / COMPLAINT
~~~

If the SMTP/API adapter throws an exception:

~~~text
SUBMITTING -> RETRY_WAIT
            -> FAILED_FINAL
            -> UNKNOWN
~~~

`SUBMITTED` only represents transport acceptance under the active contract. Do not assume every accepted message has reached the Inbox.

## 9. Atomic insert and duplicate handling

With PostgreSQL:

~~~sql
INSERT INTO mail_outbox (
    id,
    tenant_id,
    message_key,
    source_event_id,
    mail_type,
    recipient_id,
    recipient_address,
    sender_profile,
    template_id,
    payload_ref,
    command_fingerprint,
    state,
    scheduled_at,
    expires_at
)
VALUES (
    :id,
    :tenant_id,
    :message_key,
    :source_event_id,
    :mail_type,
    :recipient_id,
    :recipient_address,
    :sender_profile,
    :template_id,
    :payload_ref,
    :command_fingerprint,
    'PENDING',
    :scheduled_at,
    :expires_at
)
ON CONFLICT (tenant_id, message_key)
DO NOTHING
RETURNING id;
~~~

Gateway:

1. If the insert returns `id`, return `CREATED`.
2. If no row is returned, query by `(tenant_id, message_key)`.
3. Compare the original command fingerprint/immutable fields.
4. If equivalent, return `ALREADY_EXISTS` with the **existing job ID** and current status.
5. If different, return **conflict**.

In PostgreSQL `READ COMMITTED`, a subsequent `SELECT` statement can normally see the committed row that caused the conflict. You still need to handle rare races such as concurrent row deletion with bounded retry, rather than generating a new key.

### 9.1. EnqueueResult

~~~java
import java.util.UUID;

public record EnqueueResult(
        UUID jobId,
        EnqueueOutcome outcome,
        String currentState) {
}

public enum EnqueueOutcome {
    CREATED,
    ALREADY_EXISTS
}
~~~

`IDEMPOTENCY_CONFLICT` can be a dedicated exception or application error. Returning `ALREADY_EXISTS` for a request with different content is wrong.

### 9.2. In every state, duplicates do not reset the job

| Existing state | Command with same key, same payload | Behavior |
| --- | --- | --- |
| `PENDING` | Yes | Return existing job ID |
| `RETRY_WAIT` | Yes | Do not clear retry/backoff |
| `CLAIMED` / `SUBMITTING` | Yes | Do not call SMTP again |
| `SUBMITTED` | Yes | Do not resend |
| `FAILED_FINAL` | Yes | Do not silently resurrect |
| `CANCELLED` / `SUPPRESSED` | Yes | Do not change state |
| `UNKNOWN` | Yes | Do not blindly retry |
| Any state | Different payload | Report conflict |

Manual retry, job cancellation, email resending, or schedule changes must have separate APIs and auditing.

## 10. Transactional outbox

Scenario:

~~~text
Business transaction:
  Order status = CONFIRMED
  Email confirmation request = PENDING
~~~

If the business update runs in the DB and then calls SMTP directly:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.confirm(id);
    mailSender.send(message);
}
~~~

the following can happen:

- SMTP accepted, but DB rolls back;
- DB commit succeeds, but process crashes before SMTP;
- SMTP times out without knowing whether it was accepted;
- HTTP client retry triggers two sends.

**SMTP does not participate in the DB transaction.** The `@Transactional` annotation cannot recall an email already submitted to SMTP.

### 10.1. Writing order and outbox in the same DB transaction

~~~mermaid
sequenceDiagram
    participant API as Order service
    participant DB as Business DB / outbox
    participant W as Mail worker
    participant S as SMTP relay
    API->>DB: BEGIN
    API->>DB: UPDATE order status
    API->>DB: INSERT mail_outbox by messageKey
    API->>DB: COMMIT
    W->>DB: Claim due job
    W->>S: Submit MimeMessage
    S-->>W: Accepted / error / unknown
    W->>DB: Record attempt and state
~~~

When the business entity and mail outbox share the same transactional datasource, they can commit atomically. If they live in two different databases, a simple `@Transactional` does not create an atomic commit across both; a source outbox/event relay or another consistency mechanism is needed.

### 10.2. Illustrative service

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {
    private final OrderRepository orders;
    private final MailCommandGateway gateway;

    public OrderConfirmationService(
            OrderRepository orders,
            MailCommandGateway gateway) {
        this.orders = orders;
        this.gateway = gateway;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        OrderConfirmed event =
                orders.confirmAndReturnStableEvent(orderId);

        MailCommand command =
                MailCommands.forOrderConfirmed(event);

        gateway.enqueue(command);
    }
}
~~~

`OrderConfirmed`, `OrderRepository`, `MailCommands`, and `MailCommandGateway` are illustrative application code, not built-in Spring Mail APIs. The event ID must remain stable across retries of the order confirmation command. The gateway must insert into the outbox **in the same transaction** and **without calling SMTP**.

### 10.3. Gateway differs from SMTP adapter

~~~java
public interface MailCommandGateway {
    EnqueueResult enqueue(MailCommand command);
}
~~~

A successful `enqueue` only means the command **was persisted** or **already existed**. The worker is what calls `JavaMailSender.send(...)`. The API must not return "delivered" merely because enqueue succeeded.

## 11. Worker claim and concurrency

Message keys prevent creating duplicate jobs, yet two workers can still **send the same job simultaneously** if they only SELECT and send.

### 11.1. Atomic claim with PostgreSQL

~~~sql
WITH due AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (
          next_attempt_at IS NULL
          OR next_attempt_at <= CURRENT_TIMESTAMP
      )
      AND (
          expires_at IS NULL
          OR expires_at > CURRENT_TIMESTAMP
      )
    ORDER BY scheduled_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET state = 'CLAIMED',
    lease_owner = :worker_id,
    lease_until =
        CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    lease_version = lease_version + 1,
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.*;
~~~

`SKIP LOCKED` ensures each worker claims different rows. After claiming, the transaction commits, and only then does the worker perform SMTP. Do not hold a DB row lock across a long network call.

### 11.2. Lease and fencing token

Example:

~~~text
Worker A claims job (lease_version=8).
Worker A is paused.
Lease expires.
Worker B claims job (lease_version=9).
Worker A wakes up and tries to write SUBMITTED.
~~~

Perform conditional updates:

~~~sql
UPDATE mail_outbox
SET state = :new_state,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id
  AND lease_owner = :worker_id
  AND lease_version = :expected_lease_version
  AND state = 'SUBMITTING';
~~~

If affected rows = 0, the worker lost permission to update state. **Fencing in the DB only prevents stale updates**; it does not stop an SMTP request the old worker has already dispatched. That is why a policy for uncertain outcomes is necessary.

### 11.3. Do not hold a transaction across SMTP

~~~text
Transaction A:
  Claim job + commit.

Network phase:
  Prepare MIME, send via SMTP/API.

Transaction B:
  Record attempt and resulting state + commit.
~~~

If the worker dies between the network phase and transaction B, the DB may not know the true outcome. Use attempt history, lease expiry detection, and reconciliation; do not automatically reset every `SUBMITTING` back to `PENDING`.

## 12. Retries do not change the message key

~~~text
jobId=job-1
messageKey=invoice:evt-7:recipient-9

attempt-1 -> SMTP 451
attempt-2 -> timeout
attempt-3 -> accepted
~~~

After all three attempts:

~~~text
logical jobs = 1
SMTP attempts = 3
message key = unchanged
~~~

`attempt_number` and `provider_message_id` are metadata of the send attempt, not part of the message key.

### 12.1. Important outcomes

| Outcome | Meaning | Handling |
| --- | --- | --- |
| `ACCEPTED` | SMTP/API accepted per contract | Mark submitted |
| `RETRYABLE_FAILURE` | Error suitable for retry | Bounded backoff and retry |
| `PERMANENT_FAILURE` | Should not retry automatically | Failed final/quarantine |
| `UNKNOWN` | Unclear whether transport received it | Reconciliation or manual policy |
| `PARTIAL` | Some recipients accepted | Handle at recipient level if needed |

### 12.2. Risk of double SMTP submission

~~~text
T1 Worker sends message K.
T2 SMTP server returns 250 accepted.
T3 Worker crashes before DB records SUBMITTED.
T4 Recovery sees non-terminal state.
T5 Worker retries the same K.
~~~

There is still only one job in the DB, yet the provider may receive **two emails**. There is no universal exactly-once SMTP solely via a unique key. Risk mitigations:

- record attempt IDs and timestamps;
- recognize `UNKNOWN` instead of asserting NOT_SENT;
- query provider message ID/events if supported;
- use a provider idempotency token only when **provider documentation guarantees suitable semantics**;
- weigh deadlines and sensitivity of the mail type;
- design emails so duplicates do not directly re-execute transactions.

### 12.3. Backoff, expiry, and suppression

A production worker needs to check:

- `next_attempt_at` and max attempts;
- error class (network, auth, recipient reject, quota);
- `expires_at` (OTPs/tokens can expire);
- marketing consent/unsubscribe immediately before sending;
- suppression from hard bounces/complaints per policy;
- cancel status and sender sending permission.

When a job is no longer eligible, mark it `SUPPRESSED`, `EXPIRED`, or `FAILED_FINAL` per the application contract; do not delete the request without a trace.

## 13. Creating MimeMessage from a command

The worker fetches the command snapshot and renders:

~~~text
Durable MailRequest
    -> resolve SenderProfile
    -> load payload/template snapshot
    -> re-check recipient eligibility
    -> render text/plain + text/html
    -> optional attachment / inline resource
    -> create MimeMessage
    -> JavaMailSender.send(...)
~~~

### 13.1. Composer example

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MimeComposer {
    public MimeMessage compose(
            JavaMailSender sender,
            String from,
            String to,
            String subject,
            String plain,
            String html,
            String safeCorrelationId)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(plain, html);

        if (safeCorrelationId != null) {
            mime.setHeader(
                    "X-Correlation-Id",
                    safeCorrelationId);
        }

        return mime;
    }
}
~~~

`X-Correlation-Id` is an optional header, not an SMTP idempotency protocol. Its value must be validated, must not contain CR/LF, PII, or secrets, and must not be assumed to be preserved intact by providers.

### 13.2. Should message key be put in a header?

A system may add:

~~~text
X-Notification-Ref: notif-7e32...
~~~

to correlate raw emails with jobs. Use an **opaque correlation token** rather than a business message key containing order ID or recipient ID. Headers may be forwarded, stored, or stripped by providers. There is no universal SMTP standard that automatically deduplicates by `X-Message-Key`.

### 13.3. Render at enqueue time or send time?

| Approach | Advantage | Risk |
| --- | --- | --- |
| Snapshot content at enqueue | Immutability, easy auditing | Uses storage, tokens may expire |
| Render at send time | Uses latest state | Content may differ from preview, data may change/be deleted |

For invoices, snapshotting the issued document is usually important. For status notifications, re-checking business state may be necessary. For OTPs, ensure the token is still valid at send time.

The message key identifies the intent; the **snapshot/version policy** determines the content of that intent across retries.

## 14. Scheduling and message keys

A request can be scheduled:

~~~text
messageKey  = scheduled-notice:request-abc:recipient-9
scheduledAt = 2026-11-13T03:00:00Z
expiresAt   = 2026-11-13T04:00:00Z
~~~

If a user changes the send time from 10:00 to 11:00 while it is still **the same request**, do the following:

1. Verify owner/tenant.
2. Verify `PENDING` with no claim/attempt yet and expected version.
3. Update `scheduled_at` inside a transaction.
4. Keep the job ID and message key unchanged.
5. Record an audit entry for old/new time.

Do not construct a key using the timestamp of a job whose time can change:

~~~text
Bad:  notification:recipient-9:2026-11-13T10:00
Good: notification:request-abc:recipient-9
~~~

When the timestamp changes, the bad key risks storing two jobs for the same intent.

### 14.1. Submit command differs from reschedule command

An API receiving `MailCommand` again with the same key but a new time should not automatically modify the job. Separate:

~~~text
EnqueueMail(MailCommand)
RescheduleMail(jobId, expectedVersion, newTime)
CancelMail(jobId, expectedVersion, reason)
RequestResend(originalJobId, resendRequestId)
~~~

Each operation has its own permissions, state machine, and audit trail.

### 14.2. Recurring schedule occurrences

For a weekly newsletter:

~~~text
scheduleId    = weekly-newsletter
occurrenceKey = 2026-W46
recipientId   = subscriber-9
messageKey    = newsletter:2026-W46:subscriber-9
~~~

If an admin moves Monday to Tuesday within the same week, a second W46 occurrence should not be created when the business contract allows only **one newsletter per week**. The unique key must be based on the occurrence identity, not on the cron execution timestamp.

## 15. HTTP API and Idempotency-Key

Example:

~~~http
POST /api/notifications
Idempotency-Key: req-9d31e...
Content-Type: application/json

{
  "mailType": "ORDER_CONFIRMATION",
  "recipientId": "recipient-9",
  "businessEventId": "evt-123",
  "templateId": "order-confirmation"
}
~~~

This is an application-designed API, not a built-in Spring Mail endpoint.

### 15.1. When keys are client-supplied

The server must:

- authenticate the principal and tenant;
- validate key format/length;
- scope the key to operation/route/tenant;
- durably store the request fingerprint and response;
- return the stored result on retry with the same key/payload;
- return conflict if the same key has a different payload;
- publish a retention window;
- rate-limit to prevent unbounded key creation.

**Idempotency-Key is not an authentication token.** Knowing or guessing a key does not grant permission to read jobs belonging to another tenant.

### 15.2. Appropriate responses

| Scenario | Suggested response |
| --- | --- |
| New job created | `202 Accepted` + job ID |
| Same key/payload | `200 OK` or `202 Accepted` with existing job ID |
| Same key/different payload | `409 Conflict` |
| Invalid data | `400 Bad Request` |
| Unauthorized sender/tenant | Appropriate authorization error response |

`202 Accepted` means the job has been accepted under the contract, **not that SMTP accepted it or that the recipient read it**. You can expose `GET /notifications/{jobId}` for status checks, with tenant authorization.

## 16. Broker consumers and two layers of idempotency

Brokers typically have at-least-once semantics:

~~~text
Broker event E
  -> consumer creates mail job K and COMMITs
  -> consumer crashes before ACKing E
  -> broker redelivers E
  -> INSERT K is blocked by unique constraint
  -> returns existing job
  -> ACKs E
~~~

Distinguish:

- **Ingestion idempotency:** event/HTTP retries do not create duplicate mail jobs.
- **Dispatch coordination:** multiple workers do not claim the same row concurrently, and SMTP retries follow clear policies.

Do not conflate these two layers. A unique key in the outbox does not completely prevent a worker from sending SMTP twice after a crash.

### 16.1. Commit before ack

The consumer should ack an event after the outbox insert/lookup has **committed**. Acking before commit can lose the request if the process crashes. If an ack after commit is lost, event redelivery is handled via the unique key.

### 16.2. Do not use broker offsets as default keys

Kafka partition/offset or RabbitMQ delivery tags are transport metadata that can change upon republishing or topic migration. Message keys should follow the stable business intent across replays.

## 17. Multi-tenant isolation and send permissions

In SaaS, a command must not be allowed to choose:

~~~text
tenantId = tenant-b
senderProfile = tenant-b-private-sender
payloadRef = tenant-b-invoice
~~~

merely because the client put those values in JSON. The gateway must verify:

- tenant from authenticated context;
- recipient belongs to the tenant or is permitted to be contacted;
- sender/From domain is authorized for the tenant;
- payload/template belongs to the tenant's scope;
- status and audit do not leak another tenant's data;
- unique scope is `(tenant_id, message_key)`.

### 17.1. Message keys do not replace rate limiting

A client can create millions of commands with different keys. Idempotency only blocks **repeating the same intent**, not spam/abuse. Production still needs quotas, max pending limits, consent, fair scheduling, payload size limits, and provider capacity management.

### 17.2. Do not put keys containing PII into metrics

Wrong:

~~~text
mail_jobs_created_total{message_key="invoice:evt-1:alice@example.net"}
~~~

Metrics should have bounded tags such as:

~~~text
mail_type=invoice|otp|newsletter
sender_profile=tx_primary|marketing_primary
result=created|duplicate|conflict
~~~

Job IDs/keys belong in detailed logs and authorized DB queries, not as per-request growing Prometheus labels.

## 18. Retention and idempotency horizon

If all mail jobs are deleted after 7 days, an old event redelivered on day 8 can create the job again because the key is no longer in the unique index.

You must define:

- how late an event or HTTP retry can return;
- how long the same business intent must be blocked;
- when a resend is considered a new intent;
- how long metadata is permitted to be retained for privacy reasons.

One option is keeping an **idempotency tombstone**:

~~~text
tenantId
messageKey
originalCommandFingerprint
finalOutcome
createdAt / retentionUntil
~~~

and deleting body/attachment/recipient snapshots earlier if policy allows.

Deduplication cannot be guaranteed beyond the **retention horizon** once all keys have been purged. Conversely, retaining personal data forever just for deduplication is also inappropriate. Retention must be designed around business requirements and applicable regulations.

### 18.1. Do not reuse the same key for a new intent

Once the idempotency window expires and an operation needs to be legitimately repeated, use a **new operation/occurrence ID** rather than trying to recycle an old key with ambiguous semantics.

### 18.2. Changing the key generation algorithm

When changing key format from v1 to v2:

~~~text
v1: ORDER:evt-123:recipient-9
v2: order-confirmation:evt-123:recipient-9
~~~

the same event can produce two different keys. Migration/version compatibility or mapping/tombstones are required so replayed old events still recognize the logical intent; do not silently deploy a new algorithm while a replay window is still open.

## 19. Metrics and audit

Distinguish units clearly:

| Suggested metric | Unit |
| --- | --- |
| `mail_command_received_total` | Commands received by gateway |
| `mail_job_created_total` | New logical jobs |
| `mail_command_duplicate_total` | Recognized duplicate commands |
| `mail_command_conflict_total` | Same key, different payload |
| `mail_outbox_pending` | Remaining pending jobs |
| `mail_oldest_eligible_age_seconds` | Age of oldest eligible unclaimed job |
| `mail_submission_attempts_total` | SMTP/API attempts |
| `mail_unknown_submission_total` | Attempts with unknown outcome |
| `mail_worker_lease_expired_total` | Jobs needing recovery |

Metric names are instrumentation suggestions, not all emitted automatically by Spring Mail.

### 19.1. Do not count retries as new emails

~~~text
1 logical job
3 SMTP attempts
1 submitted outcome
~~~

Dashboards should show jobs created = 1, attempts = 3. If the broker redelivers the event once more, commands received may increase and duplicate count increases, while jobs created remains = 1.

### 19.2. Log safe metadata

~~~text
event=mail_command_duplicate
mailType=ORDER_CONFIRMATION
senderProfile=tx_primary
jobRef=job-752
result=ALREADY_EXISTS
~~~

Do not log passwords, OTPs, tokens, raw bodies, attachments, or unnecessary recipients. Message keys can carry business IDs; use opaque job references in broadly accessible logs.

### 19.3. Alerts

- Message-key conflict rate spikes after a deployment.
- Duplicate events rise abnormally due to broker redelivery.
- Backlog grows even though SMTP attempt rate is low.
- UNKNOWN submissions and expired leases increase.
- Abnormally high number of attempts per logical job.
- Tombstones/idempotency metadata purged too early.

When drilling down by tenant or message key, the backend must still enforce access control.

## 20. Unit tests for key generation

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class MailKeysTest {

    @Test
    void sameIntentProducesSameKey() {
        UUID eventId = UUID.randomUUID();
        UUID recipientId = UUID.randomUUID();

        assertEquals(
                MailKeys.orderConfirmed(eventId, recipientId),
                MailKeys.orderConfirmed(eventId, recipientId));
    }

    @Test
    void differentRecipientsProduceDifferentKeys() {
        UUID eventId = UUID.randomUUID();
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();

        assertNotEquals(
                MailKeys.orderConfirmed(eventId, first),
                MailKeys.orderConfirmed(eventId, second));
    }

    @Test
    void mailTypesDoNotShareKey() {
        UUID eventId = UUID.randomUUID();
        UUID recipientId = UUID.randomUUID();

        assertNotEquals(
                MailKeys.orderConfirmed(eventId, recipientId),
                MailKeys.invoiceIssued(eventId, recipientId));
    }
}
~~~

These tests verify the factory, not whether real event IDs are durable or whether database uniqueness works under concurrency.

### 20.1. Command validation tests

Test:

- null/blank/overlong key → reject;
- missing tenant, recipient, type, template → reject;
- deadline not after notBefore → reject;
- recipient not belonging to tenant → reject at gateway;
- sender not permitted for mail type → reject;
- cross-tenant payloadRef → reject;
- input containing invalid CR/LF in header values → do not pass directly into `MimeMessage`.

## 21. Integration tests with database and mock SMTP

### 21.1. Enqueuing the same command twice

~~~text
enqueue(K, payload P) -> CREATED, job-1
enqueue(K, payload P) -> ALREADY_EXISTS, job-1

Assert:
  mail_outbox has exactly one row (tenant,K).
  no SMTP call on enqueue.
~~~

### 21.2. Two concurrent transactions

With PostgreSQL/Testcontainers, have two threads enqueue K concurrently (using a barrier/latch):

~~~text
Thread A: INSERT K
Thread B: INSERT K

Expected:
  one insert CREATED
  the other caller ALREADY_EXISTS
  only one row exists
~~~

A mock repository cannot prove real unique constraints and transaction isolation. When testing concurrency, avoid relying purely on `Thread.sleep(...)`.

### 21.3. Same key, different payload

~~~text
enqueue(K, recipient=A) -> CREATED
enqueue(K, recipient=B) -> CONFLICT
~~~

Assert the existing row keeps the original recipient, payload, and state; do not reset `SUBMITTED` to `PENDING`.

### 21.4. Broker redelivery after commit

1. Consumer inserts outbox K and commits.
2. Simulate crash before broker ack.
3. Broker redelivers the original event.
4. Consumer constructs the same K.
5. DB returns the existing job without creating another request.

### 21.5. Worker contention and lease recovery

- Two workers do not claim the same job simultaneously.
- `lease_version` prevents stale workers from writing state.
- Jobs scheduled in the future are not sent early.
- `CANCELLED` or `SUPPRESSED` jobs are not sent.
- Crash after SMTP accepted but before DB commit is classified as uncertain, not blindly retried.

### 21.6. SMTP outcomes

Test with GreenMail/Mailpit or a fake SMTP server:

- accepted;
- connection failure before send;
- temporary 4xx;
- permanent 5xx per provider policy;
- timeout after the server may have received data;
- partial recipient rejection if the application supports multi-recipient messages.

Do not assert exactly-once SMTP when there is no provider contract. Tests must prove **the system handles uncertain states according to the chosen policy**.

### 21.7. Cleanup

Tests must clean up fixture outbox rows, attempts, mailboxes, broker events, worker tasks, and attachment files. Do not purge shared resources when tests run in parallel.

## 22. A complete production scenario

Event:

~~~text
OrderConfirmed:
  eventId    = evt-123
  tenantId   = tenant-17
  orderId    = order-456
  customerId = recipient-9
~~~

Command:

~~~text
messageKey    = order-confirmation:evt-123:recipient-9
mailType      = ORDER_CONFIRMATION
senderProfile = TX_PRIMARY
templateId    = order-confirmation
payloadRef    = order-snapshot:order-456:v2
~~~

### 22.1. Normal flow

~~~text
T1 Business event committed.
T2 Consumer creates command K.
T3 Gateway INSERTs outbox K -> job-1 PENDING.
T4 Worker claims job-1.
T5 Worker renders MIME, submits to SMTP.
T6 SMTP accepted.
T7 DB records attempt and job-1 SUBMITTED.
T8 Provider delivery event may arrive later.
~~~

### 22.2. Broker redelivery

~~~text
T9 Broker redelivers evt-123.
T10 Consumer recreates the same K.
T11 Unique constraint finds job-1.
T12 Gateway returns ALREADY_EXISTS.
T13 No job-2 is created.
~~~

### 22.3. SMTP timeout after DATA

~~~text
T5 Worker submits SMTP.
T6 Server may have received the message.
T7 Client times out before seeing the result.
T8 Worker records UNKNOWN and attempt metadata.
T9 Reconciliation or retry policy decides the next step.
~~~

The message key still guarantees only one **logical job**. It cannot tell whether the provider has already received the email.

### 22.4. User requests resend

~~~text
ResendRequested(requestId=resend-789)
messageKey=order-confirmation-resend:resend-789:recipient-9
~~~

This is a valid new intent with a new key. HTTP retries of the resend operation itself must still use `resend-789`, without creating yet another key.

## 23. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using a new random UUID as key on every handler run | Broker redelivery creates duplicate jobs | Stable business event ID |
| Using order ID for all email types | Confirmation blocks invoice | Key includes mail type/intent |
| Putting OTP/recipient email in key | Secret/PII leakage | Opaque IDs |
| Using RFC Message-ID instead of business key | Generated late, unstable | Separate MIME ID and message key |
| Check-then-insert without DB unique constraint | Race between workers | Atomic unique constraint |
| Duplicate upsert resets PENDING | Already-sent email is sent again | DO NOTHING + compare |
| Not checking payload conflict | Hidden bugs, wrong recipient | Fingerprint + 409 conflict |
| Using attempt number in key | Retries create new logical jobs | One key across all attempts |
| Using timestamp in key of reschedulable job | Rescheduling creates duplicates | Stable request ID |
| Calling SMTP inside business transaction | DB rollback cannot recall email | Transactional outbox |
| Treating `@Transactional` as exactly-once SMTP | False guarantee | UNKNOWN/reconciliation |
| Two workers SELECT then send without locking | Same row sent twice | Atomic claim + lease |
| Blindly retrying after losing lease | Possible duplicate send | Fencing + uncertainty policy |
| Single MIME with multiple recipients without partial tracking | Retry resends to already-delivered recipients | Per-recipient outcome |
| Purging tombstones too early | Old event creates new job | Horizon-aligned retention |
| Using key as a metric label | High cardinality, data leak | Bounded labels |
| Accepting tenantId without authorization | Cross-tenant access | Trusted tenant context |
| Enqueue API reporting Delivered | Misleading state meaning | Separate Accepted/Submitted/Delivered |
| Intentional resend reusing old key | Does not create resend email | New resend operation ID |

## 24. Implementation checklist

### Business command

- [ ] MailCommand has a clear contract and immutable send intent.
- [ ] Message key is based on a durably persisted business event/request ID.
- [ ] Key distinguishes mail type, recipient, occurrence, and tenant scope properly.
- [ ] Retries/redeliveries keep the key; new resend intents get new keys.
- [ ] Key does not contain OTPs, passwords, tokens, or unnecessary PII.

### Persistence

- [ ] `UNIQUE (tenant_id, message_key)` or equivalent atomic mechanism exists.
- [ ] Duplicate with same command returns existing job; different command reports conflict.
- [ ] Job state is not reset on duplicate upsert.
- [ ] Business DB/outbox transaction has proper atomicity.
- [ ] Appropriate retention/idempotency tombstones are in place.

### Worker and SMTP

- [ ] Atomic claim and lease/fencing tokens for multi-replica workers.
- [ ] Retry attempts separated from logical jobs.
- [ ] SMTP send happens outside long DB transactions.
- [ ] Backoff, deadline, suppression, and cancel policies are implemented.
- [ ] UNKNOWN/reconciliation exists; exactly-once SMTP is not promised.
- [ ] Recipient-level handling exists when messages have multiple recipients.

### Security and operations

- [ ] Tenant, sender, recipient, template, and payload are authorized.
- [ ] SMTP credentials reside only in secret configuration, never in commands.
- [ ] Metrics separate commands, jobs, attempts, and provider events.
- [ ] Message keys/job IDs are not used as high-cardinality metric labels.
- [ ] Auditing, tracing, backlog/error dashboards, and retention are configured.

### Testing

- [ ] Unit tests verify key stability and separation across business intents.
- [ ] Integration tests verify DB uniqueness under concurrency.
- [ ] Tests cover duplicates vs payload conflicts.
- [ ] Tests cover broker redelivery after commit.
- [ ] Tests cover worker claim/lease and crash recovery.
- [ ] Tests cover SMTP timeout/UNKNOWN without assuming exactly-once.
- [ ] Tests verify reschedule preserves identity while resend creates a new intent.

## 25. Key takeaways

- **Mail Command** models a business send intent; **message key** is the idempotency identifier of that intent.
- Message keys must be created where the **business event/request** is understood, not where MIME is built or SMTP is called.
- **Retries of the same intent must reuse the same key; a new resend gets a new key.**
- Tenant, mail type, event/occurrence, and recipient usually participate in scoping.
- Job ID, attempt ID, RFC Message-ID, and provider message ID each serve a distinct purpose.
- **Unique database constraints** prevent duplicate jobs more safely than simple check-then-insert.
- Same key/payload returns the existing job; same key with different payload must report a conflict.
- **Transactional outbox** persists the send request alongside business data; workers send after commit.
- Atomic claim and leases reduce duplicate processing across workers but do not eliminate all risk of double SMTP submission.
- `JavaMailSender.send(...)` returning normally indicates submission under the transport contract, **not guaranteed inbox delivery**.
- When SMTP outcomes are unclear, **UNKNOWN** state, reconciliation, and controlled retry policies are required.
- Retention/tombstones, multi-tenant authorization, data protection, and bounded-cardinality metrics are integral parts of the design.

In a reliable Spring Framework Mail system, **the message key is the business idempotency contract**, not merely a UUID string placed in an email header. When combining clear commands, stable keys, unique DB constraints, transactional outbox, worker claiming, and transparent retry handling, an application can safely re-ingest the same request without inflating the queue, while keeping clear expectations about the practical limits of deduplication at the SMTP layer.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and transport exceptions.
- **Spring Framework Reference — Transaction Management:** `@Transactional` and transaction boundaries.
- **Spring Integration Reference:** message channels, broker integration, and error handling where applicable.
- **Spring Data JPA Reference:** optimistic locking, `@Version`, and persistence.
- **Jakarta Mail API — MimeMessage:** `Message-ID`, MIME headers, `saveChanges()`, and serialization.
- **RFC 5322 — Internet Message Format:** `Message-ID` and header syntax.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP submission, recipient acceptance, and errors.
- **PostgreSQL Documentation:** unique constraints, `ON CONFLICT`, `FOR UPDATE SKIP LOCKED`, transaction isolation.
- **Micrometer/Prometheus Documentation:** Counter, Timer, Gauge, and tag cardinality limits.
- **Actual ESP documentation in use:** provider message IDs, webhook events, partial recipient results, and idempotency APIs if available.
