# Message Keys to Identify the Same Send Request

In **Spring Framework Mail**, an application may send emails using `JavaMailSender` when a user registers, places an order, pays, or requests a password reset. In a real system, a send request is not guaranteed to be processed only once: an HTTP client may resend due to a timeout, an event may be replayed, a message broker may deliver the same job multiple times, or a worker may restart after the SMTP server already accepted the message.

If each processing run creates a new email, the recipient can receive two, three, or more identical notifications. To recognize which invocations belong to **the same send request in business terms**, the application can attach a stable **message key** to that request.

For example, when order `A123` is confirmed once:

~~~text
Business event: ORDER_CONFIRMED
Order:          A123
Event version:  1
Channel:        EMAIL

Message key: order-confirmed:A123:v1:email
~~~

If the system receives the same event again due to a retry, it uses **the exact same message key** instead of generating a new one. From there, the store can detect that the request has already been accepted and return the same job instead of creating another send job.

**A limitation to understand right away:** a message key helps identify and prevent duplicate intake of requests at the application layer. It does not force an SMTP server or a recipient's mailbox to process emails *exactly once*. Avoiding duplicates also depends on durable storage, unique constraints, job states, retries, providers, and handling uncertain outcomes.

## 1. What Is a Message Key?

A **message key** is an identifier attached to **a specific email send intent**, usually determined by the application service or job-creation component before sending.

A good key answers the question:

> Are these two executions trying to fulfill the exact same send request that the business previously created?

If the answer is "the same request," both executions should use the same key. If it is a genuinely new notification, a new key must be used.

Examples:

| Scenario | Message key | Desired behavior |
| --- | --- | --- |
| Client retries the same order A123 confirmation request | Keep the key from the first request | Do not create a new job |
| Broker redelivers event `OrderConfirmed(A123, v1)` | Keep the same key | Worker recognizes the existing job |
| Order A123 is confirmed in another valid state transition | New key with different version/event ID | Create a new notification if business rules allow |
| Sending payment reminder #1 and reminder #2 | Two different keys | Allow two distinct reminders |
| Sending the same notification to two independent recipients | Different key per recipient identity or job identity | Do not accidentally skip a recipient |
| Worker retries for the 3rd time after an SMTP timeout | Still uses the original job's key | Track all attempts under one request |

A message key can be an application-constructed string, a stable UUID persisted alongside the event, or a client-supplied idempotency token bound to the business context by the server.

### 1.1. Distinguishing "Same Request" From "Identical Content"

Two emails with identical content are not necessarily the same request:

- Identical payment reminder content sent across two reminder cycles represents **two valid notifications**.
- Identical order confirmation content caused by a job retry represents **one request processed repeatedly**.
- Two different people receiving the same notification represents **two independent sends**, if the system manages each recipient as its own job.

Therefore, **never use the body or subject alone as the message key**. The key must carry business identity, not merely a content fingerprint.

## 2. Distinguishing Identifiers Commonly Found in a Mail Flow

In Spring Mail codebases, several identifier names are easily confused:

| Identifier | Represents | On retry | Created/controlled by |
| --- | --- | --- | --- |
| **Message key / idempotency key** | Unique email send intent by business rules | **Unchanged** | Application/client per contract |
| **Job ID / outbox ID** | Accepted work record | Usually unchanged within the same job | Database/job service |
| **Attempt ID** | One attempt to call the transport | **Changes** on each attempt | Worker |
| **Correlation ID / trace ID** | Links logs/traces across components | May stay or create a new span | Observability system |
| **RFC 5322 Message-ID** | Email message identifier header | May stay or change per MIME/provider policy | Mail library/application |
| **Provider message ID** | Identifier issued or returned by the mail provider | Depends on provider and each submission | Provider |
| **Business event ID** | A business event that occurred | Unchanged when replaying the same event | Domain/event store |

Example for one job:

~~~text
businessEventId = evt-8f2a
messageKey      = order-confirmed:A123:evt-8f2a:alice
outboxJobId     = job-752
attemptId       = attempt-1
correlationId   = trace-204

Retry:
messageKey      = order-confirmed:A123:evt-8f2a:alice
outboxJobId     = job-752
attemptId       = attempt-2
correlationId   = trace-205
~~~

The key and job ID identify **the same request**; the attempt ID distinguishes **individual executions**.

### 2.1. Do Not Confuse Message Key With the Message-ID Header

In MIME, an email may carry the header:

~~~text
Message-ID: <a123-confirmation-752@example.com>
~~~

The `Message-ID` header is used by email systems for message identification, threading, and related processing. It is **not** an SMTP-standardized idempotency key for rejecting duplicate emails.

Even if two emails share the exact same `Message-ID`, do not assume every SMTP server or mail client will automatically merge them or drop the second copy. Conversely, a provider may rewrite `Message-ID` or return its own provider identifier. The application's deduplication store must still rely on **the message key and durable state** per the application contract.

### 2.2. Correlation IDs Do Not Guarantee Idempotency

A trace ID may be generated fresh whenever a request is retried. If you use the trace ID as the key, the same event will be treated as a brand-new job. Correlation IDs are suited for searching logs, not as the default choice for identifying a unique send request.

## 3. Rules for Designing a Message Key

A useful message key should have the following properties:

1. **Stable across retries:** the same request always reuses the same key.
2. **Distinguishes valid new events:** genuinely new notifications must have different keys.
3. **Clear uniqueness scope:** system-wide, per tenant, per notification type, or per recipient.
4. **Contains no unnecessary sensitive data:** avoid personal emails, phone numbers, verification tokens, or payment details.
5. **Deterministically comparable/reconcilable:** must not depend on random system timestamps at each attempt.
6. **Durably persisted:** checking only in an in-memory cache is insufficient across multiple instances or restarts.
7. **Has a lifecycle and retention policy:** know how long to retain keys to detect repeated requests.

### 3.1. Business-Structured Key Format

One way to construct keys:

~~~text
<event-type>:<business-object-id>:<event-version>:<channel>:<recipient-id>
~~~

Examples:

~~~text
order-confirmed:order-123:event-5:email:user-88
password-reset-request:request-774:email:user-88
payment-reminder:invoice-29:round-2:email:user-88
~~~

Meaningful components:

- `event-type` separates confirmations, payment reminders, and cancellation notices.
- `business-object-id` identifies the business entity.
- `event-version` or event ID identifies a specific occurrence.
- `channel` distinguishes email from SMS/push if the same key store serves multiple channels.
- `recipient-id` separates independent send jobs for different recipients.

If one job represents **a single email with multiple To/Cc/Bcc recipients**, the key scope can be the single notification job rather than per recipient. However, if the worker splits one event into multiple independent per-recipient jobs, include recipient identity in the scope or key.

### 3.2. Do Not Use Only the Order ID

A key like:

~~~text
order-123
~~~

is usually too broad. The same order may need:

- a confirmation email;
- a shipping update email;
- a refund email;
- multiple payment reminders;
- a cancellation email.

If every notification shares the same key, the system will mistakenly suppress legitimate notifications. Include the event type and instance/version.

### 3.3. Do Not Generate a New UUID on Each Retry

Wrong:

~~~java
public String keyForRetry() {
    return UUID.randomUUID().toString();
}
~~~

If each retry generates a new UUID, the deduplication store cannot recognize the previous request.

Right when **the UUID key is generated once and persisted**:

~~~java
String messageKey = request.getMessageKey(); // Already generated at ingress.
queue.publish(new MailJob(messageKey, payload));

// On retry:
queue.publish(new MailJob(messageKey, payload));
~~~

A random UUID is a perfectly valid message key as long as it is issued once for the original request and persisted/published stably. What matters is **stability per send intent**, not necessarily being a human-readable string.

### 3.4. Timestamps and Attempts Should Not Be in the Key for Retries

Do not construct keys like:

~~~text
order-confirmed:A123:2026-11-12T15:00:00.123
order-confirmed:A123:2026-11-12T15:00:03.481
~~~

if the two timestamps merely represent two attempts of the same notification. That renders deduplication useless. If a date/time genuinely represents **two intentional sending cycles** (such as day-1 and day-7 reminders), it can be part of the business identity, normalized by cycle rather than using the worker's execution timestamp.

## 4. Client-Supplied or Server-Generated Keys?

The two common key sources have different characteristics.

| Approach | Example | When appropriate | Notes |
| --- | --- | --- | --- |
| **Client-supplied idempotency key** | Header `Idempotency-Key: 7f3c...` | HTTP API accepting a retryable command | Validate caller, tenant scope, length limits, and payload check |
| **Server-derived business key** | `order-confirmed:123:event-8` | Event-driven/internal use cases | Precisely define identity and event version |
| **Server-generated persistent UUID** | `f02e...` | Creating a new job with a durable ID | Generate once and return/persist for retries to share |

### 4.1. HTTP API Example With Idempotency-Key

The client may send:

~~~http
POST /api/orders/A123/confirm
Idempotency-Key: 6cd7e0f2-5bf1-4d3b-8bc3-02c431190c8c
Content-Type: application/json

{"notifyCustomer":true}
~~~

If the request times out, the client resends with **the same key**. The server looks up any previously accepted record:

- not found: check permissions, run business logic, and persist the key;
- found with equivalent payload: return the previous result/job;
- found with a different payload: report conflict; do not silently reuse the key for a new intent.

Example response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "jobId": "job-752",
  "status": "PENDING"
}
~~~

When the same request is resent, the server can return the same `jobId` with its latest status. The API contract should specify responses for initial and duplicate requests, key validity duration, and handling of payload mismatches.

**Note:** do not expose an "email any arbitrary address" endpoint merely because an idempotency key is present. Validation, authorization, rate limiting, and anti-abuse policies remain independent layers of protection.

### 4.2. Using the Business Event ID

A durable event:

~~~java
public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        String customerId,
        String customerEmail,
        int version) {
}
~~~

When the same event is replayed, `eventId` remains unchanged. You can use:

~~~java
String messageKey = "order-confirmation:"
        + event.eventId()
        + ":email:"
        + event.customerId();
~~~

If the requirement is to send **the same event to multiple recipients**, each recipient can have its own key. If the policy is to send a single email to multiple recipients at once, create one job with its own identity and store the recipient list as job data.

## 5. Uniqueness Scope: Where Is the Key Unique?

A key cannot be designed properly without defining its scope clearly.

For instance, in a multi-tenant system, two tenants might both use the string:

~~~text
order-confirmed:123:v1:email
~~~

If the unique key only covers the `message_key` column in a shared database, two unrelated requests can collide.

Consider scoping the constraint:

~~~sql
UNIQUE (tenant_id, message_key)
~~~

If event type or channel is not embedded in the key value, those may also belong in the scoped columns:

~~~sql
UNIQUE (tenant_id, notification_type, channel, message_key)
~~~

Scope rules must stay consistent across **the key generator**, **the unique constraint**, and **the job-lookup logic**. Do not check uniqueness only with an ad-hoc pre-insert query.

### 5.1. Avoid Putting Raw PII in the Key

Avoid:

~~~text
reset-password:nguyen.an@example.net:2026-11-12
~~~

Personal email addresses will show up in logs, metrics, URLs, or outbox tables if the key is used for tracing. Use an internal account ID or an opaque event ID instead:

~~~text
reset-password:req-7c22:email:user-88
~~~

If even business IDs must be hidden, use a durably stored UUID or an HMAC of the canonical string using a properly managed secret. Do not use an unsalted hash and assume the data is safely hidden, especially for guessable input spaces.

### 5.2. A Key Is Not a Secret or Authorization Mechanism

Knowing a message key does not grant permission to read the job, fetch email contents, view someone else's status, or trigger a resend. Every lookup API must enforce tenant and subject authorization. A key is a request-identification tool, **not a bearer token**.

## 6. Message Key Lifecycle and Send States

A key is usually paired with a durable state record.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Insert key + job
    PENDING --> PROCESSING: Worker claim
    PROCESSING --> SUBMITTED: Transport accepted
    PROCESSING --> RETRY_WAIT: Temporary/uncertain error
    RETRY_WAIT --> PROCESSING: Retry same key
    PROCESSING --> FAILED_FINAL: Permanent failure
    SUBMITTED --> [*]: Retention / archive
    FAILED_FINAL --> [*]: Retention / archive
~~~

These state names are examples:

| State | Meaning | Behavior when the same key arrives again |
| --- | --- | --- |
| `PENDING` | Request recorded, not yet sent | Return the same job, do not insert a new row |
| `PROCESSING` | Worker holds claim/lease | Return the same job; do not start a parallel attempt |
| `RETRY_WAIT` | Waiting to retry | Return existing job and retry schedule |
| `SUBMITTED` | Transport call completed without error | Do not resend merely due to a duplicate HTTP request |
| `FAILED_FINAL` | Ended in failure per policy | Return failure status; manual retry needs explicit rules |

**`SUBMITTED` does not mean the email reached the Inbox.** `JavaMailSender.send(...)` may finish submitting to the SMTP transport without guaranteeing final delivery. If the product needs `DELIVERED` or `BOUNCED`, add separate states driven by provider events/webhooks.

### 6.1. Retention and Expired Keys

An idempotency store does not necessarily retain records forever. However, deleting keys too early can cause a late retry request to be treated as a brand-new request.

Determine retention based on:

- how long clients may retry the same request;
- how long jobs can sit in the queue;
- retry/backoff schedules and dead-letter lifetimes;
- the maximum period manual retries must be supported;
- personal data retention and deletion requirements.

If a key is purged while a broker can still replay old events, deduplication can fail. For critical business flows, keep a **minimal tombstone** (scope + key + required state/identity) after scrubbing sensitive payloads, instead of erasing every trace.

### 6.2. What About the Same Key With a Different Payload?

Suppose a client sends:

~~~text
Key: confirm-order-A123
Payload 1: recipient=alice@example.net, amount=220000
~~~

And later sends:

~~~text
Key: confirm-order-A123
Payload 2: recipient=bob@example.net, amount=500000
~~~

You must neither return "accepted" while ignoring the difference, nor send a new email under the same key.

A common policy is storing a **payload fingerprint** and rejecting when the key already exists with meaningfully different data:

~~~text
Same scoped key + same canonical fingerprint -> existing job
Same scoped key + different fingerprint     -> conflict (HTTP 409)
Different scoped key                        -> new logical request
~~~

Compute the fingerprint from fields defining the request's identity and content: recipient, notification type, template/version, and meaningful business data. Exclude per-attempt values such as retry timestamps, trace IDs, or attempt counts.

## 7. Persisting Keys With a Database and Unique Constraint

A reliable approach is an outbox/job table with a unique constraint.

### 7.1. Reference Schema

~~~sql
CREATE TABLE mail_outbox (
    id                VARCHAR(64) PRIMARY KEY,
    tenant_id         VARCHAR(64) NOT NULL,
    message_key       VARCHAR(200) NOT NULL,
    request_digest    CHAR(64) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    recipient         VARCHAR(320) NOT NULL,
    template_id       VARCHAR(120) NOT NULL,
    template_version  VARCHAR(40),
    payload_json      TEXT NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP,
    claimed_until     TIMESTAMP,
    submitted_at      TIMESTAMP,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    CONSTRAINT uq_mail_message_key
        UNIQUE (tenant_id, message_key)
);
~~~

This schema illustrates:

- `tenant_id`: scope of the key.
- `message_key`: identifier of the send intent.
- `request_digest`: fingerprint to detect key reuse with altered content.
- `payload_json`: snapshot of data needed to send/render.
- `status` and `attempts`: job lifecycle, **not** part of identity.
- `claimed_until`: lease enabling multiple workers to coordinate claims.
- `submitted_at`: timestamp when the sender completed submission.

This is a generic schema; JSON types, UTC/`timestamp with time zone`, indexes, column lengths, and claim mechanisms depend on the specific database. Columns holding addresses and payloads may contain personal data requiring appropriate access control, encryption, and retention policies.

### 7.2. Why SELECT Followed by INSERT Is Insufficient

Common buggy code:

~~~java
if (!repository.existsByMessageKey(messageKey)) {
    repository.save(job);
}
~~~

Two instances can run concurrently:

~~~text
Worker A: SELECT -> key not found
Worker B: SELECT -> key not found
Worker A: INSERT job A
Worker B: INSERT job B
~~~

Without a database unique constraint, two jobs can be created. Even with a Java-level check, **the database must enforce uniqueness**.

With a unique constraint, one insert wins; the other must be treated as receiving the same request again after comparing fingerprints and loading the existing job. Do not turn every unique violation into an HTTP 500 internal error.

## 8. Safe Upsert for the Same Key

PostgreSQL allows:

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, message_key, request_digest,
    notification_type, recipient, template_id,
    template_version, payload_json, status,
    created_at, updated_at
)
VALUES (
    :id, :tenantId, :messageKey, :requestDigest,
    :notificationType, :recipient, :templateId,
    :templateVersion, :payloadJson, 'PENDING',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, message_key) DO NOTHING;
~~~

If the insert succeeds: the application created a new job.

If it conflicts: the application fetches the job by `tenant_id` and `message_key`, compares `request_digest`, and returns the existing job or raises a mismatch error.

Important conditions:

- The `UNIQUE` constraint must match the intended scope.
- Same key **must never UPDATE/overwrite the old job's payload**.
- A conflict alone does not prove payload equivalence; always compare fingerprints.
- Understand isolation levels and when rows from competing transactions become visible.
- Upsert syntax differs across PostgreSQL, MySQL, SQL Server, and other databases; this example is not directly portable verbatim.

### 8.1. Spring Service Example With NamedParameterJdbcTemplate

Suppose an application-validated command exists:

~~~java
public record MailCommand(
        String tenantId,
        String messageKey,
        String notificationType,
        String recipient,
        String templateId,
        String templateVersion,
        String canonicalPayloadJson) {
}
~~~

`canonicalPayloadJson` is a snapshot serialized under deterministic rules: the same logical data must produce the exact same canonical string. A default serializer does not guarantee fixed property ordering in JSON; configure canonicalization or compute the fingerprint from explicitly normalized fields.

Service creating or returning the job:

~~~java
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailJobSubmissionService {
    private final NamedParameterJdbcTemplate jdbc;
    private final PayloadDigests digests;

    public MailJobSubmissionService(
            NamedParameterJdbcTemplate jdbc,
            PayloadDigests digests) {
        this.jdbc = jdbc;
        this.digests = digests;
    }

    @Transactional
    public MailJobReceipt submit(MailCommand command) {
        // Validate key, recipient, authorization, and template
        // at the application boundary before calling the repository.
        String digest = digests.sha256(command);
        String newJobId = UUID.randomUUID().toString();

        String sql = """
                INSERT INTO mail_outbox (
                    id, tenant_id, message_key, request_digest,
                    notification_type, recipient, template_id,
                    template_version, payload_json, status,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenantId, :messageKey, :digest,
                    :notificationType, :recipient, :templateId,
                    :templateVersion, :payload, 'PENDING',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (tenant_id, message_key) DO NOTHING
                """;

        Map<String, ?> params = Map.ofEntries(
                Map.entry("id", newJobId),
                Map.entry("tenantId", command.tenantId()),
                Map.entry("messageKey", command.messageKey()),
                Map.entry("digest", digest),
                Map.entry("notificationType", command.notificationType()),
                Map.entry("recipient", command.recipient()),
                Map.entry("templateId", command.templateId()),
                Map.entry("templateVersion",
                        command.templateVersion() == null
                                ? "" : command.templateVersion()),
                Map.entry("payload", command.canonicalPayloadJson())
        );

        int inserted = jdbc.update(sql, params);
        if (inserted == 1) {
            return new MailJobReceipt(newJobId, "PENDING", false);
        }

        MailJobReceiptWithDigest old = jdbc.queryForObject(
                """
                SELECT id, status, request_digest
                FROM mail_outbox
                WHERE tenant_id = :tenantId
                  AND message_key = :messageKey
                """,
                Map.of(
                        "tenantId", command.tenantId(),
                        "messageKey", command.messageKey()),
                (rs, rowNum) -> new MailJobReceiptWithDigest(
                        rs.getString("id"),
                        rs.getString("status"),
                        rs.getString("request_digest"))
        );

        if (old == null || !old.requestDigest().equals(digest)) {
            throw new IdempotencyConflictException(
                    "Message key was already used with another request");
        }

        return new MailJobReceipt(old.id(), old.status(), true);
    }
}

record MailJobReceipt(String jobId, String status, boolean duplicate) {}
record MailJobReceiptWithDigest(
        String id, String status, String requestDigest) {}
~~~

This is a Spring JDBC example targeting PostgreSQL, not a complete mail worker system. `PayloadDigests` and `IdempotencyConflictException` are application components to define. In production, validate inputs before inserting, enforce tenant access control, bound key lengths, and handle database errors per contract.

Note that in the example, a `null` `templateVersion` is normalized to an empty string on insert; the fingerprint must apply the exact same normalization rule. In a real implementation, use a SQL parameter source supporting `null` instead of replacing `null` with an empty string if the two states carry different meanings.

### 8.2. What Is a SHA-256 Fingerprint?

A fingerprint detects **differences in a request when the same key is reused**. Conceptual example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class PayloadDigests {
    public String sha256(MailCommand command) {
        String canonical = String.join(
                "\n",
                command.notificationType(),
                command.recipient(),
                command.templateId(),
                command.templateVersion() == null
                        ? "" : command.templateVersion(),
                command.canonicalPayloadJson()
        );

        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

This snippet illustrates the concept. In production, canonicalization must eliminate any ambiguity caused by delimiters, normalize addresses/Unicode/locales per business rules, and omit no meaningful fields. If using a newline as a separator, ensure data cannot produce identical canonical strings via different field splits; a safer approach is serializing an explicit schema structure in a canonical format or length-prefixing each field.

SHA-256 here serves **consistent comparison**, not encryption or user authentication. Do not treat the digest as a secret or use it in place of authorization.

## 9. Combining Message Keys With Business Transactions

When an email is triggered by a database transaction, storing the message key only in an in-memory map/cache outside the transaction still leaves a gap.

Example:

~~~text
T1 Update order = CONFIRMED
T2 Database COMMIT succeeds
T3 Process crashes before writing mail job/key
T4 No email job for worker to send
~~~

To avoid losing send requests, use a **transactional outbox**: insert the outbox row containing the message key **in the same transaction** as the order update.

~~~mermaid
flowchart TD
    A["BEGIN transaction"] --> B["Update business entity"]
    B --> C["Insert outbox with stable message key"]
    C --> D{"COMMIT"}
    D -->|Rollback| E["No update, no job"]
    D -->|Success| F["Both business state and mail job are durable"]
    F --> G["Worker claim mail job"]
    G --> H["SMTP submission"]
    H --> I["Update status / schedule retry"]
~~~

A service:

~~~java
@Transactional
public void confirmOrder(Long orderId, String eventId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    String key = "order-confirmed:"
            + eventId
            + ":email:"
            + order.getCustomerId();

    mailJobSubmissionService.submit(
            new MailCommand(
                    order.getTenantId(),
                    key,
                    "ORDER_CONFIRMED",
                    order.getCustomerEmail(),
                    "order-confirmation",
                    "v1",
                    canonicalOrderMailPayload(order))
    );
}
~~~

For both operations to genuinely share a transaction, the business repository and outbox must use the same transaction manager/datasource; `submit` must not accidentally use `REQUIRES_NEW`. Also mind how `@Transactional` works via Spring proxies; self-invocation within the same bean may bypass the proxy.

If the transaction rolls back, both the order change and the outbox row roll back. If it commits and the process stops, the job remains in the database for a worker to pick up.

### 9.1. A Message Key Does Not Replace an Outbox

A well-chosen key only helps **identify the same request**. If you only hold keys in memory:

- multiple instances can create duplicates;
- restarts lose state;
- there is no durable job to retry;
- there is no atomicity with the business commit.

The outbox persists the send request and state; the key is the constraint preventing duplicate intake.

## 10. Retrying a Job: Stable Key, Changing Attempt ID

When a worker processes an outbox job, it may encounter a temporary SMTP error.

~~~text
Job:
  jobId       = job-752
  messageKey  = order-confirmed:A123:event-5:email:user-88
  status      = RETRY_WAIT
  attempts    = 2

Next attempt:
  jobId       = job-752
  messageKey  = order-confirmed:A123:event-5:email:user-88
  attemptId   = try-3
~~~

Do not insert another outbox row for each attempt. The worker should keep the job ID and message key fixed, only incrementing the attempt count or inserting a separate attempt record when auditing is needed.

### 10.1. Claim the Job Before Sending

If two workers pick up the same job at once, both can call `sender.send`. A message key in the outbox table ensures there is only one **job**, but it does not by itself stop two workers from **processing that job concurrently**.

Therefore, workers need a claim/lease mechanism:

1. Select an eligible `PENDING` or `RETRY_WAIT` job.
2. Claim it using a conditional update or row lock.
3. Record owner/lease expiry and increment attempts.
4. Commit the short claim transaction.
5. Send over SMTP outside the claim transaction.
6. Persist the outcome in a new transaction.

Some databases support `SELECT ... FOR UPDATE SKIP LOCKED`; other systems use optimistic locking, compare-and-swap updates, or a queue broker with visibility timeouts. Choose according to your infrastructure.

If a worker crashes, the lease must expire so the job can be picked up again. If a job might run longer than the lease, add lease renewal or fencing tokens to reduce two workers processing simultaneously due to premature lease expiration.

### 10.2. Backoff Does Not Change Identity

Example retry schedule:

~~~text
Attempt 1: immediately
Attempt 2: after 30 seconds
Attempt 3: after 2 minutes
Attempt 4: after 10 minutes
Then:      FAILED_FINAL / dead-letter
~~~

Timings are illustrative, not mandatory durations. Add jitter and attempt limits to prevent many workers from hammering the SMTP provider simultaneously. `messageKey` remains one constant value across every attempt.

### 10.3. Do Not Retry All Errors the Same Way

| Outcome category | Example | Consideration |
| --- | --- | --- |
| Temporary error | SMTP 4xx or temporary network error | Retry with backoff/limits |
| Permanent error | Definitively rejected address or invalid data | Fix data/policy; do not retry indefinitely |
| Authentication/config | Wrong credentials or broken TLS config | Requires operator intervention |
| Uncertain outcome | Timeout after the entire message may have been transmitted | Risk of sending duplicates on retry |
| Transport success | `JavaMailSender.send` returns without error | Mark `SUBMITTED`, do not create a new job |

You cannot conclude "SMTP error means the email never reached the provider" from a generic exception alone. Persist enough attempt state and cause information to decide properly.

## 11. Limitation: Why Doesn't a Message Key Give Exactly-Once SMTP?

Consider this scenario:

~~~text
1. Worker picks up job J-752 (key K).
2. Worker sends email.
3. SMTP server accepts message.
4. Worker crashes before writing status = SUBMITTED.
5. Job lease expires.
6. Another worker picks up J-752 and resends the same email.
~~~

The database still has only **one job and one message key**. Yet SMTP can receive **two sends** because sending and updating the database status do not belong to a single atomic transaction.

What a message key can guarantee, when backed by a proper unique constraint, is that:

- the same request is not inserted as two independent outbox jobs;
- HTTP/event retries can look up the existing job;
- a stable identity exists to track all attempts.

What it **does not guarantee on its own**:

- the SMTP server receives exactly one copy;
- no ambiguous timeouts occur;
- the provider never sends duplicates;
- the recipient sees only one email;
- final delivery succeeds.

If a provider over an API supports a **provider-side idempotency key**, pass the message key or a key derived from it per provider requirements. In that case, read the provider's scope, TTL, and semantics carefully; never assume plain SMTP offers an equivalent feature.

### 11.1. Does Message-ID Help Prevent Duplicates?

You can set a stable RFC 5322 `Message-ID` across retries, but do not rely on it as a dependable deduplication mechanism across all SMTP servers and mail clients. Some systems may use this header for conversation threading or custom duplicate handling, yet there is no universal guarantee that every submission with the same header will be rejected.

Manage idempotency at the application layer and leverage provider APIs where officially supported.

## 12. Same Message Key vs. Intentional Resends

A permanent failure or bounced email may prompt support staff to want to resend.

There are two distinct intents:

1. **Continuing the same request:** retrying the existing job due to a temporary failure or an authorized manual retry. Keep the same key, increment attempts, and audit.
2. **Creating a new notification:** e.g., the customer updated their email address, content was revised, or the user clicked "Resend confirmation" per policy. Create a new business identity and a new key.

Never automatically generate a new key on error just to "bypass" the unique constraint. Doing so disables duplicate protection.

### 12.1. Resends Must Be Explicitly Defined

Example:

~~~text
order-confirmed:A123:event-5:email:user-88
~~~

If there is genuinely an independent resend command:

~~~text
order-confirmed-resend:A123:resend-request-2:email:user-88
~~~

Resend commands should pass through authorization, rate limiting, and auditing. The system must specify whether the same link/token can be resent or a new token must be issued. For verification or password reset emails, issuing a new token is a distinct security event; changing only the message key is not enough.

### 12.2. Multi-Recipient Fan-Out

When one event must notify three people:

~~~text
invoice-issued:INV-30:event-8:email:customer-1
invoice-issued:INV-30:event-8:email:finance-2
invoice-issued:INV-30:event-8:email:admin-3
~~~

Each recipient has its own job identity if the worker sends individual emails. If you only use the key `invoice-issued:INV-30:event-8` for all three jobs in the same scope, the unique constraint will block the other two recipients.

Conversely, for a single `MimeMessage` with multiple `To`/`Cc`/`Bcc` recipients, you can define one message/job-level key and include the normalized recipient list in the payload fingerprint. There is no single scoping rule right for every app; match the unit of work you want to deduplicate.

## 13. Validating and Securing Message Keys

Message keys often appear in HTTP requests, queues, or databases. Apply input constraints accordingly:

- Enforce length limits, e.g., 1–200 characters per contract.
- Allow only valid characters matching the published format.
- Disallow CR/LF or control characters that could affect logs/headers.
- Reject empty keys.
- Bind keys to the authenticated tenant/user/use case.
- Prevent one client from using a key to access another tenant's job.
- Never use keys as permission checks or authentication tokens.
- Never place raw PII in metric labels.

### 13.1. Value Object Example

~~~java
import java.util.Objects;
import java.util.regex.Pattern;

public record MailMessageKey(String value) {
    private static final Pattern ALLOWED =
            Pattern.compile("[A-Za-z0-9:._-]{1,200}");

    public MailMessageKey {
        Objects.requireNonNull(value, "messageKey");
        if (!ALLOWED.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Invalid mail message key");
        }
    }
}
~~~

This illustrates a policy for application-generated ASCII keys. If your product lets clients supply UUIDs or other formats, adjust the regex to match the contract. If Unicode is allowed in keys, define consistent normalization and byte/character limits; never assume all backends compare Unicode identically.

### 13.2. Prevent Keys From Becoming a Denial-of-Service Vector

A user could send thousands of random keys attempting to create unbounded jobs. Idempotency keys do not prevent spam or abuse on their own. You need:

- authentication/authorization;
- per-account/tenant rate limits;
- mail-sending quota controls;
- payload and recipient limits;
- monitoring of job counts and outbox size;
- clear cleanup/retention policies;
- business validation before recording a send request.

When returning an existing duplicate request from the store, still verify the caller is authorized to read that job's details.

## 14. Observability: Tracing Keys Without Leaking Data

Message keys correlate send attempts for the same job:

~~~text
mailJobId=job-752
messageKey=order-confirmed:A123:event-5:email:user-88
attempt=1
status=RETRY_WAIT
reason=SMTP_TEMPORARY_ERROR
~~~

Later attempt:

~~~text
mailJobId=job-752
messageKey=order-confirmed:A123:event-5:email:user-88
attempt=2
status=SUBMITTED
~~~

In systems handling sensitive data, log a truncated/hashed key per policy or log only the job ID. Never log full recipient lists, subjects, bodies, reset tokens, or attachment bytes merely to debug retries.

### 14.1. Recommended Metrics

| Metric | Meaning |
| --- | --- |
| `mail_jobs_created_total` | Count of new logical jobs |
| `mail_idempotency_hits_total` | Count of matching duplicate key + request hits |
| `mail_idempotency_conflicts_total` | Count of key reuse with different payloads |
| `mail_attempts_total` | Total transport invocations |
| `mail_retry_scheduled_total` | Total retries scheduled |
| `mail_submission_failures_total` | Total transport errors |
| `mail_jobs_pending` | Count of pending jobs |
| `mail_jobs_oldest_age_seconds` | Age of oldest incomplete job |

Do not attach individual `messageKey` values as Prometheus labels because their unbounded cardinality causes high-cardinality explosions. Label by notification type, controlled small tenant groups, provider, or outcome.

### 14.2. Operational Alerts

Signals to monitor:

- unusual spike in idempotency conflicts: a client may be misusing keys;
- many jobs stuck in `PROCESSING` past lease: worker crash or deadlock;
- sharp climb in attempts: SMTP provider trouble;
- keys expiring before jobs finish: misconfigured retention;
- same business event producing multiple message keys: identity design bug;
- jobs `SUBMITTED` while provider reports bounces: distinguish submission from delivery.

## 15. Testing Message Keys and Deduplication

Good tests verify **request semantics**, not just string-formatting helper methods.

### 15.1. Unit Test: Same Event Produces Same Key

~~~java
@Test
void sameEventProducesSameMessageKey() {
    OrderConfirmedEvent event =
            new OrderConfirmedEvent(
                    "evt-8f2a", "A123", "user-88");

    String first = keys.forOrderConfirmation(event);
    String retry = keys.forOrderConfirmation(event);

    assertEquals(first, retry);
}
~~~

`keys` is an application-rule factory; `OrderConfirmedEvent` is a minimal illustrative fixture. Corresponding tests should also verify that two genuinely distinct events produce different keys.

### 15.2. Integration Test: Same Key Creates One Job

1. Create a request with key `K` and fingerprint `F`.
2. Call the submission service twice.
3. Both calls return the same job ID.
4. The database contains only one row for scope + key `K`.
5. Call `K` again with a different fingerprint `F2`.
6. The service reports a conflict; the old payload is not overwritten.

### 15.3. Concurrency Test: Two Simultaneous Requests

Have two threads/instances submit the same scoped key concurrently. Verify:

- the unique constraint prevents two outbox rows;
- one request creates the job, while the other reads the existing job;
- no false success occurs with a differing payload;
- transaction conflict handling matches the target database.

Testing "check then insert" with a mocked repository does not prove concurrency safety. Run against a real database or an integration environment with equivalent semantics.

### 15.4. Retry Test

Have a worker process the same job twice:

~~~text
Attempt 1: MailSendException
Status: RETRY_WAIT
Attempt 2: transport returns normally
Status: SUBMITTED
~~~

Verify `messageKey` and job ID stay unchanged, attempts increment, and no new outbox row is created.

### 15.5. Crash Window Test

Simulate the transport accepting the message while the worker dies before committing `SUBMITTED`. Verify the system can pick up the job again after lease expiry and surfaces observability for duplicate risk. Never write an assertion claiming "SMTP always receives only one email" when the provider lacks idempotency support.

### 15.6. Retention Test

Replay an old event at different milestones:

- key still active;
- job waiting for retry;
- job already `SUBMITTED`;
- key past retention while events can still be replayed.

If policy requires long-term deduplication, keep tombstones or business identities long enough.

## 16. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Generating a new UUID on each retry | Old requests look brand new | Generate/persist the key once |
| Using only subject/body as the key | Blocks valid emails, misses identity | Use event/job/business identity |
| Using only the order ID | Different email types for one order collide | Include event type and version |
| Missing tenant/recipient scope | Collisions across users or tenants | Scoped unique constraint |
| `SELECT` then `INSERT` without `UNIQUE` | Race creates multiple jobs | Database unique constraint + conflict handling |
| Overwriting payload on same key | Request semantics silently mutate | Store fingerprint, return conflict |
| Storing keys only in cache | Restarts lose data, instances diverge | Persist keys/jobs durably |
| Deleting keys before retry window ends | Late replays create new jobs | Proper retention/tombstones |
| Using attempt ID as the key | Every attempt becomes a new job | Keep message key, vary attempt ID |
| Treating RFC `Message-ID` as dedup guarantee | No universal SMTP/client guarantee | Application/provider idempotency |
| Holding DB transaction open during SMTP send | Long-held locks/connections | Short claim, send outside transaction |
| Infinite retries on SMTP timeout | Duplicates, provider load | Retry policy, uncertain-outcome handling |
| Printing raw emails/tokens in keys or logs | Information leakage | Opaque keys, minimal logging |
| Letting callers pick keys to view others' jobs | Exposes status/info | Authentication + authorization |
| Treating `SUBMITTED` as `DELIVERED` | Misreports email status | Track provider delivery separately |

## 17. Process for Designing a Message Key for a New Email Type

When adding a new notification email to a Spring Framework Mail module, follow these steps:

1. **Define the logical send unit:** one email to one recipient, or one message with multiple recipients?
2. **Identify the source event:** order confirmed, invoice issued, reminder round, reset request.
3. **Define identity:** event ID, business object ID, and event version sufficient to distinguish events.
4. **Define scope:** tenant, notification type, channel, and recipient if needed.
5. **Choose key generation:** stable business-derived string or once-generated, durably stored UUID.
6. **Define fingerprint:** which fields must match if the same key is reused?
7. **Add unique constraint:** the database must enforce the exact scope.
8. **Pair with an outbox for reliability:** persist the job and business changes in the same transaction.
9. **Define retries:** key/job stay fixed, attempts vary, with backoff and limits.
10. **Define retention and manual resends:** when to keep tombstones, when to mint a new identity?
11. **Test concurrency, payload mismatches, and crash windows:** do not assume exactly-once SMTP.

### 17.1. Example Contract Table

| Property | Decision for order confirmation email |
| --- | --- |
| Logical send | One confirmation email per customer |
| Event identity | `OrderConfirmedEvent.eventId` |
| Scope | `tenantId` + `messageKey` |
| Key format | `order-confirmed:<eventId>:email:<customerId>` |
| Payload fingerprint | Recipient, template/version, order snapshot |
| New request | Key does not exist yet |
| Duplicate request | Matching key, matching fingerprint: return existing job |
| Conflict | Matching key, differing fingerprint: reject |
| Retry | Same job/key, attempt incremented |
| Submission status | `SUBMITTED` after error-free transport call |
| Delivery status | Via provider events if supported |
| Retention | At least covering the committed replay/retry window |

## 18. End-to-End Scenario: Confirming an Order With One Consistent Key

Suppose a customer confirms order A123. The application emits event `evt-8f2a` and message key:

~~~text
order-confirmed:evt-8f2a:email:user-88
~~~

Flow:

~~~mermaid
sequenceDiagram
    participant U as HTTP client
    participant A as Order service
    participant D as DB + outbox
    participant W as Mail worker
    participant S as SMTP

    U->>A: Confirm order, idempotency key K
    A->>D: Update order + INSERT mail job K
    D-->>A: COMMIT, job-752
    A-->>U: 202 / job-752

    U->>A: Retry same request, key K
    A->>D: Lookup scoped key K
    D-->>A: Existing job-752
    A-->>U: Same job-752

    W->>D: Claim job-752
    W->>S: Send message, attempt-1
    S-->>W: Temporary failure
    W->>D: RETRY_WAIT
    W->>D: Claim job-752 later
    W->>S: Send message, attempt-2
    S-->>W: Accepted
    W->>D: SUBMITTED
~~~

Throughout the entire flow:

- client retries do not create new jobs;
- event replays do not create new requests for the same event identity;
- the worker preserves the same message key across all attempts;
- the database unique constraint prevents two jobs with the same scoped key;
- processing status and attempts change without changing logical identity;
- SMTP can still receive duplicate emails in a crash window, so the system does not claim exactly-once delivery.

If the customer later intentionally clicks resend because they want a fresh confirmation email, that can be **a new business event** with a different message key, accompanied by rate limits and auditing. Never "solve" deduplication by minting a new key on every retry.

## 19. Key Takeaways

- **A message key identifies a send intent**, not a transport attempt.
- Keep the same key across HTTP retries, broker redeliveries, and worker retries for the same request.
- Legitimate new notifications must have new identities; do not use email content as the sole uniqueness criterion.
- Clearly define tenant, event type, channel, and recipient scope before choosing a unique constraint.
- Use a database unique constraint to guard against races; checking first and inserting in code is insufficient.
- For the same key, compare fingerprints to detect requests with altered data.
- Message key, job ID, attempt ID, trace ID, and RFC `Message-ID` serve distinct roles.
- Pair message keys with a transactional outbox when send requests must commit alongside business transactions.
- Retain keys/tombstones long enough for retry and replay windows; purging too early breaks deduplication.
- A message key **does not itself guarantee once-only SMTP delivery**; crashing between SMTP submission and DB update can still produce duplicates.

Proper message key design helps a Spring Mail system tell **new requests** apart from **repeated executions of an existing request**. When keys are stable, cleanly scoped, and stored alongside durable jobs, the application gains a solid foundation for retries, status visibility, and reducing duplicate emails without accidentally dropping notifications that truly must be sent.

### References

- **Spring Framework Reference — Transaction Management:** `@Transactional` and transaction boundaries.
- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and mail-sending behavior.
- **Spring JDBC — NamedParameterJdbcTemplate:** parameterized SQL statements and database access.
- **Transactional Outbox Pattern:** persisting business changes and external processing requests in the same transaction.
- **RFC 5322 — Internet Message Format:** the `Message-ID` header and email message identification.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP submission, reply codes, and delivery boundaries.
