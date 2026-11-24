# Controlled Retries, Duplicate Prevention, and Outcome Tracking

## 1. The Email-Sending Problem in Integration Systems

A Spring Boot service receives a payment outcome, writes the order to PostgreSQL, and sends a receipt email via SMTP or an email provider's API. Business requirements typically demand: never losing critical notifications, never sending multiple emails for the same action, never slowing down the payment request, and knowing whether the email was **accepted**, **delivered to the mailbox**, or **bounced**.

Calling `JavaMailSender.send(...)` and wrapping it with a naive retry still leaves three failure windows:

1. **DB commits, app crashes before sending:** the order is paid, yet no email is sent.
2. **Provider receives the email, app times out or crashes before saving the outcome:** retrying may produce a duplicate email.
3. **SMTP returns success, yet the message bounces or lands in spam:** a "send success" log does not prove the recipient received or read the email.

In the `SPRING_BOOT_INTEGRATION` module, email is an outbound adapter with side effects much like an HTTP client or broker. You must design data contracts, transactions, idempotency, error handling, tests, and observability. Examples use **Spring Boot 3.x, Java 17+, Spring Mail, and PostgreSQL**; the same principles apply to email over HTTP APIs. SMTP does not provide cross-system exactly-once guarantees.

Lesson goals: classify errors for proper retries; persist send intent with a transactional outbox; guard against duplicate send requests; track outcomes from `PENDING` through `ACCEPTED`/`DELIVERED`/`BOUNCED`; and test crashes, timeouts, and multi-worker contention.

## 2. Milestones of an Email and How They Differ

~~~mermaid
sequenceDiagram
    participant A as Business API
    participant D as PostgreSQL
    participant W as Email worker
    participant P as SMTP/Email provider
    participant R as Recipient mailbox
    A->>D: Commit business data + email outbox
    W->>D: Claim a PENDING email
    D-->>W: Lease + payload
    W->>P: SMTP DATA or HTTP request
    P-->>W: SMTP 250 or HTTP accepted
    W->>D: Record ACCEPTED status
    P->>R: Attempt delivery to mailbox
    P-->>W: Webhook delivered/bounced if supported
    W->>D: Save delivery event
~~~

| Milestone | What Can Be Asserted | What Cannot Yet Be Asserted |
| --- | --- | --- |
| `PENDING` | Send intent is durably stored | Email has been sent over the network |
| `SENDING` | Worker claimed the job and began processing | Provider received it |
| `ACCEPTED` | SMTP relay/provider responded accepting the request | Email reached the recipient's inbox |
| `DELIVERED` | Provider reported delivery success per its definition | Recipient opened/read it, or it avoided spam |
| `BOUNCED` | Provider/destination system reported inability to deliver | That every bounce type should be retried |
| `COMPLAINED` | Provider reported recipient marked it as spam/complained | That continuing to send that mail type is permitted |
| `UNKNOWN` | Unclear whether provider accepted the request | That resending is safe without creating a duplicate |

**SMTP returning `250 OK` after `DATA`** means the SMTP relay accepted responsibility for processing the message. Afterward, the relay may still encounter a bounce. When `JavaMailSender.send(...)` returns without throwing an exception, it primarily proves the send command completed per the SMTP response, **not final delivery**.

With HTTP APIs, `202 Accepted` may likewise mean only that the provider enqueued the request. Some providers expose a provider message ID, webhooks, and dedicated idempotency keys; verify the exact contract and retention window of each feature. Standard SMTP does not deduplicate repeated sends based on an application-level idempotency key.

### Three Types of IDs to Keep Separate

| ID | Where Created | Purpose |
| --- | --- | --- |
| **Business intent key** | Application | Identifies exactly one send intent; backed by a unique constraint to block duplicate enqueues |
| **Outbox ID** | Application/database | Identifies the record, worker claim, trace, and audit trail |
| **Provider message ID / RFC 5322 Message-ID** | Provider or message | Correlates against SMTP logs, webhooks, and provider history |

The `Message-ID` header helps with correlation but is **not** a universal deduplication mechanism. Sending two copies with the same `Message-ID` can still deliver two emails to the recipient. If a provider supports API idempotency, pass the same stable key across retries within the provider's validity window; verify whether that guarantee covers ingestion or only the HTTP request itself.

## 3. Classify Errors Before Retrying

An exception from `JavaMailSender` or an HTTP timeout does not prove the provider never received the email. Retries must depend on **the provider's acceptance outcome** and the certainty of the response.

| Outcome Category | Examples | Decision |
| --- | --- | --- |
| **Transient, definitely not received** | SMTP returns a temporary code before receiving message content; provider returns 429 guaranteeing rejection | Re-queue with backoff / `Retry-After` |
| **Permanent, definitely not received** | Invalid recipient syntax, permanently rejected address, unverified sender domain | Mark `FAILED_FINAL`; no automatic retries |
| **Uncertain whether received** | Timeout/disconnect after sending SMTP `DATA`; HTTP request timeout where provider may have created the email | Mark `UNKNOWN`; reconcile via provider ID/logs before resending |
| **Accepted, then delivery failed** | Provider reports delayed/deferred/bounced after `ACCEPTED` | Record delivery event; retry only per bounce type and policy |
| **Configuration or permission fault** | Bad SMTP credentials, TLS certificate error, suspended domain, paused organization quota | Alert, pause worker, and fix root cause |

SMTP typically uses `4xx` for transient failures and `5xx` for permanent ones, yet you must consider **which protocol step** produced the response. Multi-recipient sends can succeed partially, so never retry an entire group just because one address failed. For tracked notifications, create **one outbox record per recipient and per send intent**.

### Backoff, Jitter, and Deadlines

An example policy to tune against real SLAs:

1. Allow at most **5 send attempts**, including the initial try; stop once the business deadline passes.
2. Exponential backoff with a 30-second base delay, doubling per failure, capped at 15 minutes. Add random jitter so instances do not retry in lockstep.
3. If the provider supplies a valid `Retry-After` header, honor it within policy limits; apply a shared domain/provider rate limiter when throttled.
4. Never retry configuration errors, invalid addresses, or permanent bounces merely by raising the retry count.
5. When the outcome is **uncertain**, do not blindly reset to `PENDING`. Reconcile first or make an audited decision accepting resend duplicate risk.

Reference formula: `delay = min(30s × 2^(attempt - 1), 15m) + jitter`, where `attempt` is the number of send attempts already made starting at 1. Guard against integer overflow when computing powers and cap total wait time. Retries recover transient errors, yet **never create exactly-once guarantees**.

## 4. Transactional Outbox: Durably Persisting Send Intent

### Why Sending Inside a Database Transaction Is Insufficient

The following pattern is widely misunderstood:

~~~java
@Transactional
public void completePayment(...) {
    paymentRepository.markPaid(...);
    mailSender.send(...); // SMTP I/O sits outside the JDBC transaction
}
~~~

The email may be accepted by the provider and then the DB rolls back, leaving the user with a receipt for an unsuccessful order. Or the DB commits and the process crashes before sending. `@Transactional` on PostgreSQL **cannot enlist SMTP in the same transaction**.

A common design:

~~~text
HTTP/Kafka PaymentCompleted
          |
          v
Spring service @Transactional
  UPDATE payment/order
  INSERT email_outbox (PENDING)
          |
          v
   COMMIT database
          |
          v
Email worker claim -> SMTP/API -> persist outcome
          |
          v
Provider webhook/DSN -> update delivery/bounce
~~~

Because the business update and outbox insert share **a single database transaction**, a rollback discards both; a successful commit leaves a `PENDING` record for workers after restart. Even so, a worker can still resend an email after crashing prior to recording the result; add `UNKNOWN` tracking and idempotency controls.

### 4.1. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE email_outbox (
    id                  UUID PRIMARY KEY,
    intent_key          VARCHAR(240) NOT NULL UNIQUE,
    recipient_email     VARCHAR(320) NOT NULL,
    template_code       VARCHAR(100) NOT NULL,
    template_data       JSONB NOT NULL,
    status              VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempt_count       INT NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token         UUID,
    lease_until         TIMESTAMPTZ,
    provider_message_id TEXT,
    accepted_at         TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    last_error_kind     TEXT,
    last_error_summary  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (attempt_count >= 0),
    CHECK (status IN (
        'PENDING','SENDING','ACCEPTED','DELIVERED',
        'BOUNCED','COMPLAINED','FAILED_FINAL','UNKNOWN'
    ))
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox (next_attempt_at, created_at)
    WHERE status = 'PENDING';

CREATE TABLE email_delivery_event (
    provider_event_id TEXT PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES email_outbox(id),
    event_type VARCHAR(40) NOT NULL,
    provider_occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

The trace/lease and delivery-event columns illustrate the design skeleton; production systems need migrations, retention rules, read access controls, and PII protection. Never keep plaintext OTP codes, password-reset tokens, or full sensitive data longer than necessary. You can store a template reference and render content when the worker sends, provided the data contract remains stable so replays never render incorrect content.

`intent_key` represents a **logical business notification intent**. For example, `invoice-issued:invoice-123:recipient-user-42` means an issued invoice sent to one specific recipient. The same event arriving twice from Kafka yields the same key. Never use timestamps or random UUIDs as `intent_key` on retries.

If you need to send a **correction** or intentional resend, create a new business-authorized intent such as `invoice-correction:invoice-123:revision-2:recipient-user-42`. Never mint a new intent simply because a template version bumped during a deployment.

### 4.2. Recording Send Intent in the Same Business Transaction

Suppose we have an `invoice(id, status)` table and the caller already validated the invoice:

~~~java
// InvoiceNotificationService.java — Spring JDBC + PostgreSQL
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceNotificationService {
    private final JdbcTemplate jdbc;

    public InvoiceNotificationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void issueInvoice(UUID invoiceId, String recipientUserId, String to) {
        // Real applications must validate authorization and invoice state.
        int updated = jdbc.update("""
            UPDATE invoice SET status = 'ISSUED'
            WHERE id = ? AND status = 'DRAFT'
            """, invoiceId);
        if (updated == 0) {
            String current = jdbc.queryForObject(
                    "SELECT status FROM invoice WHERE id = ?",
                    String.class, invoiceId);
            if (!"ISSUED".equals(current)) {
                throw new IllegalStateException("Invoice is not issuable");
            }
        }

        String intentKey = "invoice-issued:" + invoiceId
                + ":recipient:" + recipientUserId;
        String payload = "{\"invoiceId\":\"" + invoiceId + "\"}";

        jdbc.update("""
            INSERT INTO email_outbox
              (id, intent_key, recipient_email, template_code, template_data)
            VALUES (?, ?, ?, ?, ?::jsonb)
            ON CONFLICT (intent_key) DO NOTHING
            """, UUID.randomUUID(), intentKey, to, "invoice-issued", payload);
    }
}
~~~

This code demonstrates the **JDBC transaction boundary**. For production use, check the return value of `UPDATE`: if the invoice does not exist, cannot be issued, or is in another state, follow your state machine and decide whether to enqueue. Do not assume every `UPDATE = 0` means successful issuance. Also handle concurrent updates, recipient authorization, and email address changes.

`ON CONFLICT (intent_key) DO NOTHING` relies on the unique constraint so concurrent requests or consumers create at most one outbox record. A separate "SELECT to check, then INSERT" has a race condition. Ensure `@Transactional` runs through a Spring proxy and uses the same transaction manager for both `invoice` and `email_outbox`; this does not work if the tables live in separate databases without a shared transaction.

## 5. Worker Job Claiming and Managing Send Attempts

If every instance queries `PENDING` rows and immediately sends, two instances can read the same record and send duplicates. You need **atomic claiming** in the database, persisting in-flight state before opening an SMTP connection and binding worker updates to the claim lease.

### 5.1. Claiming with FOR UPDATE SKIP LOCKED

PostgreSQL lets you pick due records and lock them in a short transaction:

~~~sql
WITH picked AS (
    SELECT id
    FROM email_outbox
    WHERE status = 'PENDING'
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at, created_at
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE email_outbox e
SET status = 'SENDING',
    lease_token = :claim_token,
    lease_until = now() + interval '2 minutes',
    attempt_count = e.attempt_count + 1,
    updated_at = now()
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.intent_key, e.recipient_email,
          e.template_code, e.template_data, e.attempt_count,
          e.lease_token;
~~~

`:claim_token` is a fresh UUID generated by the worker, and the claim transaction **commits before** sending the email. `SKIP LOCKED` keeps competing workers from blocking on or picking already locked rows. Never hold a transaction or row lock across a slow SMTP call. In multi-instance deployments, combine this with batch size limits, bounded thread pools, and provider rate limits.

Example Spring JDBC repository following these principles:

~~~java
// EmailClaimRepository.java — PostgreSQL, Spring JDBC
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class EmailClaimRepository {
    private final JdbcTemplate jdbc;

    public EmailClaimRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedEmail> claim(int maxBatchSize) {
        UUID token = UUID.randomUUID();
        return jdbc.query("""
            WITH picked AS (
                SELECT id FROM email_outbox
                WHERE status = 'PENDING' AND next_attempt_at <= now()
                ORDER BY next_attempt_at, created_at
                LIMIT ?
                FOR UPDATE SKIP LOCKED
            )
            UPDATE email_outbox e
            SET status = 'SENDING',
                lease_token = ?,
                lease_until = now() + interval '2 minutes',
                attempt_count = e.attempt_count + 1,
                updated_at = now()
            FROM picked
            WHERE e.id = picked.id
            RETURNING e.id, e.intent_key, e.recipient_email,
                e.template_code,
                e.template_data::text AS template_json,
                e.attempt_count, e.lease_token
            """, (rs, rowNum) -> new ClaimedEmail(
                    rs.getObject("id", UUID.class),
                    rs.getString("intent_key"),
                    rs.getString("recipient_email"),
                    rs.getString("template_code"),
                    rs.getString("template_json"),
                    rs.getInt("attempt_count"),
                    rs.getObject("lease_token", UUID.class)),
                maxBatchSize, token);
    }
}

record ClaimedEmail(
        UUID id, String intentKey, String recipientEmail,
        String templateCode, String templateJson,
        int attemptCount, UUID leaseToken) {}
~~~

The `record` models only the payload needed by the worker; template rendering, recipient authorization, and outcome persistence are built separately. In Spring, `@Transactional` methods must be invoked **from another bean via the proxy** so the transaction applies. Once a worker claims rows and commits before sending, other workers will not re-claim those `SENDING` rows.

### 5.2. Recording Outcomes Using the Claim Token

After receiving an acceptance response from the provider, perform a conditional update:

~~~sql
UPDATE email_outbox
SET status = 'ACCEPTED',
    accepted_at = now(),
    provider_message_id = :provider_message_id,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :outbox_id
  AND status = 'SENDING'
  AND lease_token = :claim_token;
~~~

Always verify **the updated row count equals 1**; if it is 0, another process may have transitioned the record or the claim is no longer valid. Never silently assume the result was saved. When using SMTP without a provider message ID, leave that column `NULL` and store a separate correlation header ID for investigation.

For errors confirmed transient **and definitely not yet accepted by the provider**, the worker sets `PENDING` with a new `next_attempt_at` and clears the lease, or `FAILED_FINAL` when limits/deadlines expire. Gate that update on `id + lease_token + status` as above so a stale worker never overwrites newer state. Store classified error details as `last_error_kind` and a safe summary without credentials or full email bodies.

### 5.3. An Expired Lease Does Not Mean Sending Failed

When a worker crashes and its lease expires, at least two possibilities exist: (a) the worker died before the SMTP call; (b) SMTP received the message, yet the worker died before persisting `ACCEPTED`. Automatically flipping `SENDING` back to `PENDING` and retrying creates a **duplicate email** in case (b).

A more cautious policy:

~~~sql
UPDATE email_outbox
SET status = 'UNKNOWN',
    lease_token = NULL,
    lease_until = NULL,
    last_error_kind = 'LEASE_EXPIRED',
    updated_at = now()
WHERE status = 'SENDING'
  AND lease_until < now();
~~~

`UNKNOWN` rows should be **reconciled** via the provider's API/logs/events when available. For APIs with guaranteed idempotency keys, you can retry with the same key per provider policy. With plain SMTP, some businesses choose to resend despite duplicate risk, while others require manual resolution when duplicate emails are unacceptable. Document the trade-off between **possible lost notice** and **possible duplicate** in your SLA.

A slow worker may still finish sending after the lease transitions to `UNKNOWN`. The claim token prevents that worker from silently overwriting DB state, though **it cannot recall an already sent email**. Send timeouts, lease durations, heartbeats when needed, and instance counts must be designed together; monitoring zero-row outcome updates is essential.

### 5.4. Worker Algorithm with Clear Transaction Separation

~~~text
On each scheduler tick (non-overlapping with itself):
  claimed = claim(due PENDING, batch limit) [short transaction]

  for each mail in claimed:
    1. Render and validate email from persisted business data
    2. Call SMTP or provider API (outside DB transaction)
    3. If provider accepts: mark ACCEPTED using claim token
    4. If confirmed transient error before acceptance:
       set PENDING with next_attempt_at per backoff
    5. If confirmed permanent error: mark FAILED_FINAL
    6. If unclear whether provider received it: mark UNKNOWN

Separate reconciler:
  SENDING past lease -> UNKNOWN
  UNKNOWN -> reconcile with provider / handle per SLA
~~~

With Spring Scheduling, you can use `@EnableScheduling` and `@Scheduled(fixedDelay = 2000)` to invoke the worker; across multiple instances, DB claiming remains necessary. Running every 2 seconds is only an example and should be tuned to throughput, SMTP limits, notification priority, and backlog size. Never fire-and-forget all emails inside an `@Async void` method with no state tracking.

## 6. Connecting to SMTP via Spring Mail with Timeouts and TLS

### 6.1. Basic Configuration

~~~kotlin
// build.gradle.kts — Spring Boot 3.x
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
# application.yml — SMTP submission with STARTTLS on port 587
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

`${SMTP_HOST}`, `${SMTP_USERNAME}`, and `${SMTP_PASSWORD}` are placeholders populated from environment variables or a secret store. Jakarta Mail timeouts are in **milliseconds**. For **implicit TLS on port 465**, configure `mail.smtp.ssl.enable=true` and adjust STARTTLS for the endpoint; never mix both modes blindly.

`mail.smtp.starttls.required=true` prevents transmitting data over an unupgraded plaintext connection when STARTTLS is required. `mail.smtp.ssl.checkserveridentity=true` enforces hostname verification against the certificate. Clients must trust the proper CA and never disable certificate verification ("trust all") to hide configuration mistakes. If a provider uses OAuth2, API keys, or custom SMTP relays, authentication and rotation differ; always supply credentials via a secret manager and scope sending permissions.

### 6.2. Example Single-Recipient Sender Adapter

~~~java
// SmtpEmailSender.java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SmtpEmailSender {
    private final JavaMailSender mailSender;

    public SmtpEmailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(ClaimedEmail mail) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());
        helper.setFrom("notifications@example.test");
        helper.setTo(mail.recipientEmail());
        helper.setSubject("Your invoice has been issued");
        helper.setText("Please sign in to view your invoice.", false);
        message.setHeader("X-Notification-Id", mail.id().toString());
        mailSender.send(message);
    }
}
~~~

This example focuses on the SMTP boundary: a single recipient, a configured/verified sender address, and a correlation ID header containing no sensitive data. In real applications, `templateCode`/`templateJson` render a controlled template, escape user input in HTML, validate contents, and avoid logging secrets. With multiple email types, separate rendering from the sending adapter.

`mailSender.send(message)` can throw `MailException` (wrapping underlying SMTP/Jakarta Mail causes). Inspect actual responses—including partial acceptance—before retrying. `send` returns no delivery status; the worker may only mark `ACCEPTED` after valid submission confirmation, and final outcomes must be tracked through the provider if supported.

## 7. Tracking Delivery, Bounces, Complaints, and Unknown Outcomes

### 7.1. Where Do Final Events Come From?

| Sending Method | Information Usually Available | Limitations |
| --- | --- | --- |
| **Standard SMTP** | Server acceptance or rejection of the send call, SMTP errors | Does not natively indicate delivery to the mailbox; may require mail-system DSNs/logs |
| **Email service via API** | Request ID/provider message ID, API status | HTTP success may still mean only `ACCEPTED` |
| **Provider webhooks** | `delivered`, `deferred`, `bounced`, `complained`, `unsubscribed`, etc., per contract | May arrive late, out of order, or duplicated; source must be authenticated |
| **Email open/click tracking** | Pixel/link events per provider mechanism | Cannot reliably prove human reading due to proxies, blocking, and privacy protections |

**Never turn `ACCEPTED` into `DELIVERED`** simply because no error arrived after a few seconds. If the provider offers no delivery feedback, leave the state at `ACCEPTED` and document the observability boundary clearly. Even when requesting SMTP Delivery Status Notifications (DSNs), not every destination system sends complete or timely notifications.

### 7.2. Receiving Webhooks Idempotently

To ingest `delivered`/`bounced` events from a provider:

1. Verify HMAC/signatures or the provider's authentication scheme; check timestamps and replay windows if provided.
2. Match the exact outbox record using **provider message ID + recipient/correlation metadata** per the provider contract. One ID may cover multiple recipients depending on the API; do not match by ID alone when multi-recipient sends are possible.
3. Persist the event inside a DB transaction: `INSERT email_delivery_event` with a unique `provider_event_id`; if it already exists, treat as a redelivery and return success.
4. Transition outbox status using a **state machine** and meaningful event timestamps rather than blindly overwriting by HTTP arrival order.
5. Return HTTP `2xx` only after durable persistence; if the DB temporarily fails, let the provider retry per contract. Idempotency is mandatory because webhooks are typically delivered at least once.

Example SQL to prevent duplicate event processing:

~~~sql
INSERT INTO email_delivery_event (
    provider_event_id, outbox_id, event_type, provider_occurred_at
)
VALUES (
    :event_id, :outbox_id, :event_type, :provider_occurred_at
)
ON CONFLICT (provider_event_id) DO NOTHING;
~~~

If the INSERT affects zero rows because the unique key already exists, do not run side effects for that event a second time. When both inserting an event and updating `email_outbox`, place both inside one transaction so the event log and aggregate state stay consistent.

### 7.3. State Transitions Are Not Simply Arrival Order

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SENDING: claim
    SENDING --> PENDING: transient error, definitely not received
    SENDING --> FAILED_FINAL: permanent error / attempts exhausted
    SENDING --> UNKNOWN: timeout or ambiguous crash
    SENDING --> ACCEPTED: SMTP/API confirms acceptance
    ACCEPTED --> DELIVERED: provider delivery event
    ACCEPTED --> BOUNCED: bounce event
    ACCEPTED --> COMPLAINED: complaint event
    DELIVERED --> COMPLAINED: later complaint
    UNKNOWN --> ACCEPTED: reconciliation finds email
    UNKNOWN --> FAILED_FINAL: audited business decision
~~~

This diagram shows a common flow and does not cover every provider quirk. For example, a provider might report `deferred` before `delivered` or emit a late bounce after another event. **Persist an immutable event log** and derive the current state via explicit rules rather than treating "latest webhook wins" as truth. `COMPLAINED` and hard bounces usually trigger **suppression**: halting future sends to that address or notification type until policy allows resuming.

Distinguish **hard bounces** (usually never auto-retried) from **soft bounces/deferred** (such as full mailbox or temporary destination error). If the provider automatically retries delivery, the application should not create **a brand-new email API request** upon receiving a `deferred` event. Only trigger application-level retries after understanding the final outcome and the provider's retry behavior.

### 7.4. Reconciling `UNKNOWN` Emails

With providers offering a query API, look up the email by provider message ID, idempotency key, or registered custom metadata. If an accepted request is found, mark `ACCEPTED` with reconciliation details. If the provider confirms **no request exists** and the send deadline has not passed, initiate a fresh retry. If verification is impossible, decide explicitly whether to accept duplicate risk to avoid missed notifications.

With plain SMTP, there is usually no standard query API to check whether an email arrived during a timeout window. Classify as `UNKNOWN`, inspect mail server logs if accessible, watch alerts, and follow a manual or business-approved retry workflow. Automatically flipping every `UNKNOWN` back to `PENDING` defeats the purpose of tracking the state.

## 8. Integrating with HTTP, Databases, Kafka, and Brokers

### HTTP Requests

An invoice-issuance API can return `202 Accepted` or `200 OK` once the business transaction and outbox record commit. The response must clearly state **"notification request recorded"** rather than promising inbox delivery. Returning a `notificationId`/`outboxId` for an authorized status-query endpoint is also helpful.

When a client retries an HTTP request after a timeout, an **API-layer idempotency key** or stable business key prevents re-issuing the invoice and enqueueing duplicate emails. This key may differ from the outbox key, provided mapping rules are deterministic and produce the same behavior on retries.

### Kafka/RabbitMQ Inbound Events

When a consumer receives `InvoiceIssued`, write the inbox/projection and email outbox inside a single DB transaction. Ack or commit the broker offset **only after the DB commits**; if a crash occurs between DB commit and broker ack, the message may be redelivered, yet the unique `intent_key` prevents inserting a duplicate outbox row. Writing to the outbox does not mean the email was sent, so never ack a broker message based on synchronous SMTP sending inside the consumer thread.

In architectures with two separate databases, a single standard DB transaction cannot cover both. Identify the source of truth and use inbox/outbox patterns or compatible mechanisms instead of putting `@Transactional` on a method and assuming all adapters commit atomically.

### Caches and Other Side Effects

If emails include links or tokens cached in Redis, manage TTLs and commit/expiration timing carefully. Never send an email containing a token that has not yet persisted or has already expired. Webhook callbacks may update notification dashboards, audit logs, or suppression lists; those side effects must also be idempotent on `provider_event_id`.

### Business Limits of "No Duplicates"

A unique `intent_key` guarantees **at most one outbox record per intent**, not that the provider accepts only one email. If the business demands strictly one email ever, standard SMTP plus a database cannot atomically guarantee that together; accept the trade-off or choose a provider offering reliable idempotency within its documented guarantees.

For example, receipt emails typically prioritize **no missed notices** and tolerate rare duplicates. OTP or password-reset emails often follow a different rule: invalidate older tokens, emit a fresh intent with clear expiration, and never replay expired tokens. Business rules determine which states are eligible for retry.

## 9. Observability, Alerting, Security, and Operations

### Valuable Metrics and Logs

| Signal | Why Needed |
| --- | --- |
| `email_outbox_pending_total`, `email_outbox_oldest_pending_age` | Reveals backlog depth and notification wait times |
| `email_send_attempts_total{result,provider}` | Separates successful accepts, definitive rejections, and unknown outcomes |
| `email_send_duration_seconds` | Detects slow providers requiring timeout/pool tuning |
| `email_retry_scheduled_total{reason}` | Shows whether retries recover or spin |
| `email_unknown_total` and `email_unknown_oldest_age` | Prioritizes reconciling ambiguous sends |
| `email_delivery_events_total{type}` | Tracks delivered, bounced, complained, deferred |
| `email_intent_duplicate_suppressed_total` | Measures how often unique keys block duplicate enqueues |

Build dashboards segmented by provider, template, environment, and recipient domain (when grouping complies with data policies), and alert when critical emails breach wait/delivery SLAs, `UNKNOWN` counts climb, or providers return persistent rate limits.

Minimum log fields include `outboxId`, sanitized `intentKey`, `attemptCount`, `providerMessageId` when present, claim/send/accept timestamps, categorized error codes, and trace/correlation IDs. **Never log SMTP passwords, API tokens, full email bodies, sensitive headers, or full email addresses unnecessarily.** Restrict access to outbox and event-log tables, encrypt protected fields, and enforce legal/internal retention limits.

### Protecting Domain Reputation and Sending Compliance

Configure SPF, DKIM, and DMARC for sending domains, verify sender identities with your provider, and handle bounces/complaints. Marketing emails require preference/opt-out handling under applicable rules and regulations; transactional emails must remain strictly on-purpose and avoid technical resend storms. Check suppression lists before creating or dispatching intents when required by business rules.

### Operating During Provider Outages

If a provider returns continuous throttling responses, do not scale workers endlessly. Bound concurrency, isolate SMTP pools with bulkheads, trip circuit breakers or pause queues when needed, retry with backoff, alert, and execute controlled provider failover plans. When failing over between providers, preserve `intent_key` and outbox IDs; resolve `UNKNOWN` rows first because the prior provider may already have accepted them.

Whenever upgrading Spring Boot, Jakarta Mail, SMTP drivers, or provider SDKs, re-verify timeouts, TLS/STARTTLS, exception classification, partial recipient handling, correlation headers, webhook schemas, and idempotency semantics. A dependency upgrade must never silently turn all exceptions into retryable failures.

## 10. Integration Testing and Fault Injection

For email, unit tests verifying `send(...)` was called once are insufficient. Test against a real PostgreSQL instance or Testcontainers, an SMTP test server (e.g., GreenMail), or a fake HTTP provider capable of controlling responses and connection drops.

| Scenario | Fault Setup | Expected Verification |
| --- | --- | --- |
| Business rollback | Invoice transaction throws before commit | No outbox row committed |
| Crash after business commit | Stop process after outbox INSERT, before worker runs | `PENDING` row persists and sends after restart |
| Duplicate business requests | Send two concurrent requests with the same `intent_key` | Only one outbox record; no duplicate intent |
| Competing worker claims | Two instances run claim concurrently | Each `PENDING` row is claimed by at most one worker at a time |
| Provider returns clear transient error | Fake SMTP/API returns response proving non-acceptance | Proper backoff, preserved intent and attempt count, no immediate retry |
| Provider returns permanent error | Invalid recipient or rejected sending rights | `FAILED_FINAL` or operational pause; no infinite loop |
| Disconnect after provider accepts | Fake provider stores request then closes socket before replying | `UNKNOWN`; no blind automatic retry |
| DB failure saving `ACCEPTED` | Provider accepted, DB UPDATE fails | Alert raised; expired lease transitions to `UNKNOWN` for reconciliation |
| Worker exceeds lease | Worker A stalls; reconciler marks `UNKNOWN` | No automatic send B; late update from A does not blindly overwrite |
| Duplicate webhook | Deliver the same `provider_event_id` twice | Only one event record and one state transition |
| Out-of-order webhooks | Receive `delivered` followed by an older `deferred` event | Valid state is not blindly overwritten by stale event |
| Spoofed webhook | Missing/invalid signature, expired timestamp | Rejected with no data modified |
| Bounce/complaint | Provider emits corresponding final event | Outcome recorded; suppression applied per policy |
| System overload | Provider continuously returns 429 or SMTP slows down | Concurrency/rate limits enforced; backlog and queue age alerted |
| Provider failover after incident | Several `UNKNOWN` records on old provider | Reconciled or business-decided before sending via new provider |

In particular, you cannot simulate "provider received the email but the response was lost" with a mock that always throws **before** the send executes. You need a fake server that actually accepts the request and drops the response, or a suitable provider test harness. Passing tests must verify **outbox rows, event logs, actual requests received by the provider, and retry timing**—not merely Java log output.

Never send test emails to real customers or intentionally break shared services in production for drills. Use sandbox/test addresses, synthetic data, and controlled environments. Before replaying after an incident, assess the `UNKNOWN` count, duplicate risk, and who approves state overrides.

## 11. Analysis Scenarios and Self-Check Questions

### Scenario A: Retrying After Timeout Sends Customers Two Emails

A worker picks up invoice `INV-814` and sends over SMTP. The server replies accepting it, yet the connection drops before the client reads the reply. The worker treats every `MailException` as transient and immediately resends. The customer receives two copies.

The root cause is **the first send outcome was indeterminate**, not proven unreceived. Fix with an `UNKNOWN` state, reconciliation where possible, sensible timeouts, provider idempotency keys if supported, and resend policies tailored to notification criticality.

### Scenario B: Avoiding Duplicates Causes Lost Emails

An application sets `sent = true` before calling SMTP to prevent duplicates. The process crashes right after setting that flag, before opening a connection. The scheduler skips the row because `sent = true`. The order completed, yet the customer received no email.

Never equate **scheduled** with **accepted**. Use outbox `PENDING`, claim `SENDING`, complete `ACCEPTED` after confirmation, and classify interrupted claims as `UNKNOWN`. Put the business change and enqueue inside a single DB transaction.

### Scenario C: Same Email Enqueued Twice by Two Consumers

Kafka redelivers `InvoiceIssued(invoiceId=INV-814)` twice. Both consumers `SELECT`, find no outbox row, and `INSERT`. Without a unique constraint, two copies are created. Fix with a stable `intent_key` for `invoiceId + recipient`, a unique index, and `INSERT ... ON CONFLICT DO NOTHING`; the DB transaction ensures only one intent exists.

### Self-Check Questions

1. **Does SMTP `250 OK` mean the message is in the recipient's inbox?** No. The relay only accepted it for processing; final delivery depends on downstream providers and mailboxes.
2. **Does wrapping `mailSender.send` with `@Retryable` prevent duplicate emails?** No. Timeouts after acceptance can still produce extra emails even with bounded retries.
3. **What does a unique `intent_key` solve?** It blocks creating multiple outbox rows for one business intent; it does not eliminate duplicate SMTP sends under ambiguous responses.
4. **Why use `FOR UPDATE SKIP LOCKED`?** So competing workers claim distinct rows without blocking on rows already locked by others.
5. **Why should expired leases not automatically retry right away?** The worker may have sent successfully before crashing prior to saving `ACCEPTED`; retrying increases duplicate risk.
6. **How should duplicate `delivered` webhooks be handled?** Authenticate the source, enforce a unique `provider_event_id`, and update state idempotently within a transaction.
7. **If the provider lacks delivery webhooks, what status should be reported?** Report `ACCEPTED` per SMTP/API response; never claim `DELIVERED` without evidence.
8. **When the database commits yet the email has not been sent, what enables recovery?** The `PENDING` outbox row committed alongside business data, allowing workers to pick it up after restart.
9. **Why avoid sending financial notifications to multiple recipients in one SMTP command?** Responses may partially accept; tracking and retrying per recipient becomes inaccurate.
10. **Why must retries check business expiration?** An expired token or link can become useless, confusing, or risky if delivered too late.

To send email reliably in Spring Boot Integration, protect **send intent** with transactions and unique keys, protect **execution** with controlled claims, backoff, and timeouts, and protect **outcome interpretation** with states distinguishing `ACCEPTED`, `DELIVERED`, `BOUNCED`, and `UNKNOWN`. That separation reveals failure boundaries and supports evidence-based retry decisions rather than assuming "no response means unsent."
