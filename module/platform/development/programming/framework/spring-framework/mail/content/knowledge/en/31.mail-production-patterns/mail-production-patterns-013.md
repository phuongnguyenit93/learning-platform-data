# Designing an Audit Trail Without Over-Storing Data

In a production **Spring Framework Mail** system, operations teams need to answer questions such as: *"Why wasn't the order confirmation email sent?"*, *"Did the system try to send this notification twice?"*, *"Who requested the resend?"*, *"On which attempt did the SMTP relay accept the notification?"*, or *"What evidence shows an email bounced?"*.

A careless approach writes the full `MimeMessage`, recipient addresses, subject, HTML body, attachments, SMTP transcripts, and stack traces into a database or logs at every step. That helps quick debugging, yet builds an uncontrollable repository of sensitive data: OTPs, password-reset links, invoices, customer details, tokens, subjects, and email contents can linger inside the audit system long past their original purpose.

Conversely, recording only `sent=true` is insufficient. When SMTP times out after the server already received the data, the application may not know whether the message was accepted. When multiple workers retry, a boolean flag fails to record attempt history, causes, sending authorization, or outcome evidence.

**Designing an audit trail without over-storing** means capturing **the right events, the right identifiers, the right level of detail, the right retention period, and the right authorized viewers**. Auditing must explain actions and outcomes without turning into a shadow mailbox or a storehouse of all personal data.

This lesson walks through designing audits in a mail pipeline from domain events through SMTP/provider delivery, distinguishing audits from logs/metrics/traces, building a minimal event schema, handling correlation and idempotency, designing storage/retention/redaction, protecting integrity, sample Java/Spring and SQL implementations, testing, and incident procedures.

## 1. What questions does an audit trail answer?

An audit trail is a sequence of records that explains **when a significant action occurred, which actor or component initiated it, on which logical object, under what decision, and what outcome was observed**.

In email systems, key questions typically fall into five groups:

1. **Origin:** which business event, API call, scheduled job, or operator requested the send?
2. **Decision:** why was the notification accepted, rejected, cancelled, deferred, or rerouted?
3. **Execution:** which worker/attempt tried to submit via SMTP or provider API?
4. **Outcome:** did the provider accept, explicitly reject, or produce an uncertain outcome?
5. **Post-processing:** did the system receive bounce, deferred, delivered events, or resend/cancel requests under which policy?

An audit trail **does not have to answer** "what was the exact HTML text of the email?" by storing every byte. When template proof is needed, you can record `templateKey`, `templateVersion`, and controlled references depending on purpose and retention obligations.

### Auditing does not automatically prove Inbox delivery

Even an audit entry recording `SMTP_ACCEPTED` normally proves only that the next-hop SMTP relay accepted submission. It does not prove the message entered the Inbox, was opened, or was read. If the provider sends a `delivered` webhook, store **the source and semantics of that event** rather than renaming it to "user received."

## 2. Why is over-storing a production risk?

An email may contain:

- OTPs and verification/password-reset links.
- Names, addresses, phone numbers, invoices, and payment details.
- Subjects carrying sensitive business data.
- Recipient and sender addresses.
- Attachments containing contracts, images, or reports.
- Headers with message identifiers or routing tokens.
- HTML content with personalized URLs.
- Credentials or access tokens accidentally printed by configuration/debug logs.
- Metadata enabling inference of user activity.

If all of that is copied into the audit store:

- The number of sensitive data copies multiplies.
- Deletion under retention or valid user requests grows complex.
- Multiple teams granted audit access gain visibility into content they do not need.
- Log aggregation, backups, and analytics systems may retain data longer than the mail service.
- Storage and query costs scale up with retry attempts.
- During a security incident, the blast radius widens.

Principle: **A field should appear in an audit record only if it serves a clear audit/operational purpose, no less-sensitive alternative answers that question, and an accompanying retention policy exists.**

## 3. Audit trails, operational logs, metrics, and distributed traces differ

| Mechanism | Goal | Data shape | Example |
|---|---|---|---|
| **Audit trail** | Prove the chain of significant decisions/actions | Structured events with retention and access controls | `MAIL_SUBMISSION_ACCEPTED` |
| **Application log** | Diagnose technical errors and runtime behavior | Log lines with severity/correlation | SMTP connection timeout on route X |
| **Metric** | Observe volume, rates, latency | Counters/gauges/timers, bounded tags | `mail_send_attempt_total` |
| **Distributed trace** | Follow a request path across services | Span/trace IDs and durations | API → outbox → worker → provider |

Do not write **all logs** into the audit trail. Nor turn every health-check request, queue poll, or SQL query into an audit event.

A system can emit:

```text
Business event: OrderPaid
      |
      +-- audit: notification requested
      +-- metric: notification created +1
      +-- trace: order workflow
      |
      v
SMTP attempt
      |
      +-- audit: attempt started / accepted / rejected / unknown
      +-- metric: attempts, latency, result
      +-- log: classified technical diagnostic
```

Different purposes call for different retention policies and access controls.

## 4. Choosing the right events to audit

Not every operation deserves a durable audit event.

| Event | Audit it? | Why |
|---|---|---|
| Send request durably accepted | Yes | Proves origin of logical notification |
| Request rejected by policy/consent | Depending on requirements, usually concise | Explains why no email was sent |
| Worker claims job | Depending on investigation depth | Can live in processing/attempt state rather than long-term history |
| SMTP attempt started | Usually yes for critical mail | Distinguishes attempted vs. still-queued jobs |
| SMTP submission accepted | Yes | Submission outcome evidence |
| SMTP known rejection | Yes | Failure classification and retry decisions |
| Uncertain SMTP outcome | Yes | Investigating duplicate risk |
| Provider bounce/delivery event | Yes when business signal must be kept | Tracks downstream outcomes |
| Operator requests resend/cancel | Yes | Privileged action with real side effects |
| Sender/route policy changes | Yes, under config auditing | Explains behavior changes |
| Every scheduler wakeup tick | Usually no per-tick audit | Use metrics/logs instead |
| Every SMTP health check | Usually no | Use health/metrics; avoid event noise |
| Every header/attachment read | Usually no | Do not turn audits into message copies |
| Every retry scheduler check of `nextAttemptAt` | No | Carries no new business meaning |

**Event minimization** matters just as much as field minimization.

## 5. Three identifier tiers to keep distinct

A mail-sending design typically separates:

1. **Business occurrence/source event**: the business event triggering the need to notify.
2. **Logical notification**: the contract-bound intent to send one specific notification.
3. **Submission attempt**: one worker attempt to submit via SMTP/provider.

Example:

```text
sourceEventId   = order-paid-801
notificationId  = notif-302
attemptId       = attempt-302-02
providerRoute   = transactional-primary
```

One notification can have multiple attempts. One business event can spawn multiple notifications across multiple recipients.

Never use a single ID for all levels and conclude no retries or duplicates occurred.

### Message-ID and provider ID are not notification ID

- `notificationId`: application-generated logical key.
- `attemptId`: key for a single submission attempt.
- MIME `Message-ID`: email-standard header, potentially generated by the app/JavaMail.
- `providerMessageId`: provider-assigned identifier, possibly absent or carrying provider-specific semantics.
- `providerEventId`: webhook event identifier, if supplied by the provider.

Audit events should record IDs **only when correlation requires them**, without assuming they share identical scope or meaning.

## 6. What belongs in a minimal event schema?

A mail audit event can include:

| Field | Role | Notes |
|---|---|---|
| `auditEventId` | Audit record identifier | Server-generated UUID/ULID or unique ID |
| `schemaVersion` | Audit contract version | Aids consumers/migrations |
| `eventType` | Action category from a bounded enum | No arbitrary text |
| `occurredAt` | When the action occurred | UTC/`Instant` |
| `recordedAt` | When the event was persisted | Helps spot ingestion lag |
| `notificationId` | Logical notification reference | Contains no email/PII |
| `attemptId` | Attempt reference if applicable | Nullable by event type |
| `sourceType` | API, schedule, domain event, manual | Bounded enum |
| `actorType` | USER, SERVICE, SYSTEM, OPERATOR | Avoid free-form usernames as taxonomy |
| `actorRef` | Minimized/access-controlled identifier | Nullable or pseudonymous |
| `providerRoute` | Internal route/provider alias | Stable ID, not hostnames/credentials |
| `outcome` | ACCEPTED, REJECTED, UNKNOWN... | Accurate semantics |
| `reasonCode` | Bounded reason code | Never store raw exceptions |
| `policyVersion` | Decision/consent policy version | When rationale reproducibility is needed |
| `correlationId` | Links logs/business traces | Contains no personal information |
| `evidenceRef` | Reference to restricted evidence, if any | Not raw bodies |

Not **every event needs every field**. A `MAIL_REQUESTED` event needs no `attemptId`. A `MAIL_RESEND_AUTHORIZED` event may need `actorRef` and `authorizationContextRef`, not an SMTP response code.

Good design uses an **event-specific allowlist** rather than unbounded JSON accepting arbitrary caller-supplied fields.

## 7. Example JSON audit event containing no message content

```json
{
  "auditEventId": "ae-4d73",
  "schemaVersion": 1,
  "eventType": "MAIL_SUBMISSION_ACCEPTED",
  "occurredAt": "2026-11-12T08:05:10Z",
  "recordedAt": "2026-11-12T08:05:11Z",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-02",
  "sourceType": "DOMAIN_EVENT",
  "actorType": "SERVICE",
  "providerRoute": "transactional-primary",
  "outcome": "SMTP_ACCEPTED",
  "reasonCode": null,
  "correlationId": "corr-801",
  "templateKey": "order-confirmation",
  "templateVersion": "v7"
}
```

This record **omits** recipient email, actual subject, HTML body, attachment bytes, SMTP passwords, and raw authentication responses. To find the recipient, authorized systems can query the notification record under separate permissions and retention rather than repeating the address in every audit event.

### Never "hide" sensitive data inside correlation IDs

A `correlationId` like `john@example.com-20261112` remains personally identifiable despite being labeled an ID. Use opaque/random identifiers; never embed emails, phone numbers, guessable order numbers, or tokens.

## 8. Classify data before defining the schema

Mail pipeline data can be grouped into four tiers:

| Tier | Examples | Audit handling |
|---|---|---|
| **Operational metadata** | Event type, timestamp, outcome, route alias | Store as needed |
| **Pseudonymous reference** | Internal `userRef`/`recipientRef` | Restrict permissions, explicit retention |
| **Personal/sensitive content** | Email address, subject, body, invoice details | Keep out of audit; reference separate storage only |
| **Secrets/high-risk data** | SMTP passwords, OAuth tokens, OTPs, reset tokens | Never put into audits/logs |

A `recipientRef` can still be personal data if another system maps it back to an individual. **Pseudonymization is not anonymization**; protect lookup tables, query permissions, and backups too.

If a field serves no approved audit use case, strip it from the schema from day one.

## 9. Audit trails should not store full MimeMessage objects

An anti-pattern:

```java
// DO NOT DO THIS: recording the entire MIME in audit.
ByteArrayOutputStream buffer =
        new ByteArrayOutputStream();

mimeMessage.writeTo(buffer);

auditRepository.save(
        new AuditRecord(
                notificationId,
                buffer.toByteArray()
        )
);
```

Risks:

- Stores full bodies and attachments.
- May capture OTPs, personalized URLs, and sensitive metadata.
- Multiplies storage volume on retries.
- Exposes email contents whenever audits are exported to ops teams.
- Creates extra locations requiring deletion and retention enforcement.
- Puts memory/DB/storage pressure on large messages.

**Audits only need evidence that a message was prepared or submitted per contract**, not to turn into a second mailbox.

If a specific obligation requires retaining original messages, design a **separate evidence store** with encryption, retention, access approvals, integrity, and deletion policies; audits store only a permissioned `evidenceRef`, never raw MIME.

## 10. Does the subject truly need to be stored?

A subject looks small, yet may contain:

```text
Order #801 for Nguyen Van A
Verification code: 123456
Notice regarding loan ...
Medical test results ...
```

Storing raw subjects in audits can leak PII or sensitive details. Instead, record:

- `notificationType`: `ORDER_CONFIRMATION`.
- `templateKey`: `order-confirmation`.
- `templateVersion`: `v7`.
- `locale` when formatting explanations matter.
- Normalized `renderResult` or `renderErrorCode`.
- Access-controlled `businessRef` if an audit use case requires linkage.

Do not infer that having a template version guarantees byte-for-byte email reconstruction: dynamic variables, attachments, render timestamps, timezones, and template engine versions can change. If business requires proving **the exact sent content**, maintain dedicated evidence retention under those specific requirements.

## 11. Recipient email addresses: where should they live?

Recipient emails are needed for delivery, not necessarily repeated across audit events.

One design:

```text
mail_notification
  notification_id
  recipient_ref
  encrypted_destination_ref
  status
  retention_class

mail_audit_event
  audit_event_id
  notification_id
  event_type
  outcome
  occurred_at
```

The notification table can enforce stricter permissions than the audit table. When an operator looks up a `notificationId`, the application service checks permissions before returning details.

If an investigation requires viewing the exact address, expose it via a **just-in-time privileged lookup** with its own access audit.

Never follow a rule that "anyone allowed to view audits can also view recipient addresses."

## 12. Should email addresses be hashed for search?

Some systems want to search audits by recipient without storing raw addresses.

Unkeyed hashes like `SHA-256(email)` **do not guarantee anonymity**: common address spaces are easily guessed via dictionary attacks. If a more protected lookup index is needed, consider **secret-keyed HMAC** over policy-normalized emails.

Understand the caveats:

- HMAC still generates stable identifiers capable of linking a recipient's activity.
- Anyone holding the key/lookup capability can re-identify the target.
- Keys require KMS/secret-manager governance and rotation.
- Normalize emails carefully: domains are typically case-insensitive, while local-parts carry system-dependent semantics. Avoid arbitrarily applying provider-specific dot-stripping or alias rules.
- HMAC lookups may break if data is deleted or keys rotate.
- Even HMAC values can qualify as personal data depending on context.

**Never cite hashing as proof that audits no longer hold personal data.**

### Example pseudonymous lookup

```text
normalizedDestination
        |
        v
HMAC(keyId, canonicalizedAddress)
        |
        v
recipientLookupToken
```

Audits can carry a lookup token when a concrete use case justifies it; however, the safer default remains **keeping opaque `recipientRef` values in the notification store** with access-controlled queries, because fewer identifying indexes mean lower risk.

## 13. Error codes should be normalized; never store raw exceptions

An SMTP exception can embed hostnames, recipient addresses, provider responses, usernames, or other data. Never place raw `exception.getMessage()` straight into audit events.

Design a taxonomy:

```java
public enum MailAuditReason {
    AUTHENTICATION,
    AUTHORIZATION,
    INVALID_RECIPIENT,
    INVALID_SENDER,
    INVALID_MESSAGE,
    RATE_LIMITED,
    CONNECTION,
    TLS,
    TIMEOUT,
    PROVIDER_UNAVAILABLE,
    POLICY_SUPPRESSED,
    EXPIRED,
    UNKNOWN
}
```

When persisting:

```json
{
  "eventType": "MAIL_SUBMISSION_REJECTED",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-01",
  "reasonCode": "RATE_LIMITED",
  "providerRoute": "transactional-primary"
}
```

More detailed technical debugging can reside in **short-lived operational logs**, still redacted and access-restricted. If raw provider responses are ever needed as special evidence, store them in a retention-bound, approval-gated evidence store rather than mixing them into default audits.

### SMTP 4xx/5xx codes need context

An SMTP code helps classify errors, yet audit outcomes should not rely on a simplistic rule like "4xx = always retry, 5xx = always permanent failure." Inspect the SMTP command, stage, extended status code, and cause chain when available.

## 14. State machine for notifications and attempts

Avoid storing only `sent=true/false`.

A model:

```text
NOTIFICATION
  CREATED
    |
    +--> SUPPRESSED_BY_POLICY
    +--> CANCELLED
    +--> EXPIRED
    |
    v
  PENDING
    |
    v
  PROCESSING
    |
    +--> SUBMISSION_ACCEPTED
    +--> RETRY_SCHEDULED
    +--> FAILED_FINAL
    +--> UNKNOWN_REVIEW
```

Each **attempt** has its own lifecycle:

```text
ATTEMPT_STARTED
     |
     +--> SMTP_ACCEPTED
     +--> KNOWN_REJECTED
     +--> UNKNOWN
```

An audit trail should record **meaningful state transitions** and evidence, without needing to log every database polling read.

### Uncertain outcomes are facts that must be audited

If SMTP received `DATA` yet the final reply was lost, the worker cannot be sure whether the message was accepted. The `MAIL_SUBMISSION_UNKNOWN` audit event should preserve that uncertainty rather than relabeling it `FAILED` for retry convenience.

## 15. Accepted, delivered, and read are different

| State | What is known | What remains uncertain |
|---|---|---|
| `REQUESTED` | Business intent exists | Not guaranteed durable until committed |
| `QUEUED` | Request persisted/accepted per contract | Not yet sent over SMTP |
| `SMTP_ACCEPTED` | Next-hop SMTP transport confirmed submission | Does not prove Inbox delivery |
| `DELIVERED_EVENT` | Provider reported delivered per its definition | Not necessarily Inbox placement or user read |
| `BOUNCED_EVENT` | Provider reported a bounce | Must inspect type/per-recipient detail |
| `OPEN_EVENT` | Tracking pixel or similar signal if enabled | May be blocked or triggered by proxies; does not prove a human read it |

**Audits must never rename evidence into a stronger claim.** When presenting timelines to operators or reports, preserve the exact semantics of the status source.

If the product does not use open tracking, do not add "open" fields/events merely because a provider offers them.

## 16. Audit trails with multiple recipients

A single `MimeMessage` may target multiple recipients with non-uniform outcomes: the SMTP server can accept some recipients and reject others.

If the business requires per-recipient traceability, consider:

- One logical notification per recipient; or
- A batch notification with child per-recipient submission records.

Never attach a single blanket `MAIL_ACCEPTED` event to an entire batch when transport reported partial acceptance.

Minimal per-recipient data might be:

```text
notificationId
recipientRef
attemptId
recipientOutcome
errorCategory
```

Avoid repeating raw email addresses in every event; rely on internal references and permissioned tables.

## 17. When should audits be written so they never lie?

Two common pitfalls:

1. **Writing `MAIL_REQUESTED` before the outbox commits**: if the transaction rolls back, the audit falsely claims an accepted request.
2. **Sending over SMTP before recording the attempt**: if the process crashes, no evidence remains that a send attempt happened.

The fix is not a giant transaction spanning database and SMTP. Instead, emit events along **enforceable transaction boundaries**.

One strategy:

```text
Transaction A:
  insert notification
  insert audit event NOTIFICATION_QUEUED
COMMIT

Transaction B:
  claim job
  insert attempt STARTED
COMMIT

Outside DB transaction:
  send SMTP

Transaction C:
  record outcome for attempt
  insert audit event matching outcome
COMMIT
```

If the process crashes after SMTP and before Transaction C, the attempt still exists in `STARTED` or unknown state; recovery must reconcile it rather than falsely declaring it never sent.

## 18. Transactional outbox keeps audits and event dispatch consistent

Suppose creating an order should also send an email:

```text
Transaction:
  Save order
  Insert mail notification PENDING
  Insert minimal MAIL_REQUESTED audit event
COMMIT
```

If the transaction rolls back, neither notification nor audit event is committed. Workers pick up `PENDING` records only after commit.

If audit events must also flow to a centralized audit system, use a **transactional outbox for audit publishing**:

```text
Business DB transaction
    |
    +-- notification row
    +-- audit event row
    +-- audit publication outbox row
    |
    v
COMMIT
    |
    v
Audit publisher retries until event handed off
```

Never wrap JDBC transactions around SMTP and remote audit APIs. SMTP does not participate in database transactions, and network errors create ambiguous outcomes.

### Syncing local audits with an external audit store

If the application writes audits locally and forwards them to a central store, define:

- Which store is the authoritative source of truth?
- Which event ID deduplicates deliveries?
- How long does the central store retain events?
- When the audit publisher lags, does the app block mail sending?
- How is audit lag detected?
- Who may read which event classes?
- How are the outbox and audit store reconciled?

Never report "audit persisted in central store" when an event was only enqueued for publishing.

## 19. Minimal SQL schema

Simplified example:

```sql
CREATE TABLE mail_audit_event (
    audit_event_id      VARCHAR(64) PRIMARY KEY,
    schema_version      INTEGER NOT NULL,
    event_type          VARCHAR(64) NOT NULL,
    occurred_at         TIMESTAMP NOT NULL,
    recorded_at         TIMESTAMP NOT NULL,
    notification_id     VARCHAR(64),
    attempt_id          VARCHAR(64),
    actor_type          VARCHAR(24),
    actor_ref           VARCHAR(128),
    source_type         VARCHAR(32),
    provider_route      VARCHAR(64),
    outcome_code        VARCHAR(48),
    reason_code         VARCHAR(48),
    correlation_id      VARCHAR(128),
    policy_version      VARCHAR(64)
);

CREATE INDEX ix_mail_audit_notification_time
    ON mail_audit_event (
        notification_id,
        occurred_at
    );

CREATE INDEX ix_mail_audit_attempt
    ON mail_audit_event (attempt_id);
```

This is an illustrative schema. Timezone-aware timestamps, retention partitioning, tenant scoping, uniqueness, and row-level security depend on your database and architecture.

**Notice there are no columns** for `subject`, `html_body`, `smtp_password`, `access_token`, `mime_bytes`, or `attachment_blob`. If a genuine use case demands such data, build an evidence store with its own purpose, legal basis/retention, and permissions rather than tacking columns onto the shared audit table.

### Are foreign keys needed?

A foreign key to `mail_notification` enforces integrity when both tables share the same retention. However, if notification PII is deleted earlier than audits, a hard constraint can block deletion. Consider opaque references and tombstone/mapping-removal policies where appropriate rather than retaining data solely to keep foreign keys valid.

## 20. Java domain model for audit events

An immutable type without raw body/recipient fields:

```java
import java.time.Instant;

public record MailAuditEvent(
        String auditEventId,
        int schemaVersion,
        MailAuditEventType eventType,
        Instant occurredAt,
        Instant recordedAt,
        String notificationId,
        String attemptId,
        MailActorType actorType,
        String actorRef,
        String sourceType,
        String providerRoute,
        String outcomeCode,
        MailAuditReason reasonCode,
        String correlationId,
        String policyVersion
) {
}
```

Enums:

```java
public enum MailAuditEventType {
    NOTIFICATION_QUEUED,
    NOTIFICATION_SUPPRESSED,
    NOTIFICATION_CANCELLED,
    ATTEMPT_STARTED,
    SUBMISSION_ACCEPTED,
    SUBMISSION_REJECTED,
    SUBMISSION_UNKNOWN,
    RETRY_SCHEDULED,
    NOTIFICATION_EXPIRED,
    PROVIDER_BOUNCED,
    PROVIDER_DELIVERED,
    MANUAL_RESEND_AUTHORIZED,
    MAIL_ROUTE_POLICY_CHANGED
}

public enum MailActorType {
    USER,
    SERVICE,
    SYSTEM,
    OPERATOR
}
```

This is an illustrative model. Not every enum needs the same table; configuration-change audits may live in a separate schema with distinct retention.

### Why are records/enums helpful?

- Tighter schema enforcement than an unchecked `Map<String,Object>`.
- Lowers the risk of accidentally inserting raw MIME into audit payloads.
- Event types form a bounded, index-friendly set.
- Per-event validation can be enforced cleanly.
- Supports intentional schema versioning.

Above all, never provide a generic `audit(Object payload)` method that serializes arbitrary business objects to JSON, as those objects may unexpectedly carry passwords or email bodies.

## 21. An audit service accepting structured events

```java
import java.time.Clock;
import java.util.UUID;

public final class MailAuditService {

    private final Clock clock;
    private final MailAuditRepository repository;

    public MailAuditService(
            Clock clock,
            MailAuditRepository repository
    ) {
        this.clock = clock;
        this.repository = repository;
    }

    public void submissionAccepted(
            String notificationId,
            String attemptId,
            String providerRoute,
            String correlationId
    ) {
        var now = clock.instant();

        repository.insert(
            new MailAuditEvent(
                UUID.randomUUID().toString(),
                1,
                MailAuditEventType.SUBMISSION_ACCEPTED,
                now,
                now,
                notificationId,
                attemptId,
                MailActorType.SERVICE,
                null,
                "MAIL_WORKER",
                providerRoute,
                "SMTP_ACCEPTED",
                null,
                correlationId,
                null
            )
        );
    }
}
```

`MailAuditRepository` is an application-implemented interface. Production implementations typically inject `Clock`, `IdGenerator`, and transaction services to support testing and idempotency.

Notice the code intentionally **does not pass `MimeMessage` into the audit service**. When audit needs evolve, intentionally update the event API instead of dumping full mail objects into logging.

## 22. Persisting audits alongside state in the right transaction

Example service finalizing an attempt outcome:

```java
import org.springframework.transaction.annotation.Transactional;

public class MailAttemptFinalizer {

    private final MailAttemptRepository attempts;
    private final MailAuditRepository audit;

    public MailAttemptFinalizer(
            MailAttemptRepository attempts,
            MailAuditRepository audit
    ) {
        this.attempts = attempts;
        this.audit = audit;
    }

    @Transactional
    public void markAccepted(
            String attemptId,
            String claimToken,
            AcceptedEvidence evidence
    ) {
        int updated = attempts.markAcceptedIfOwned(
                attemptId,
                claimToken,
                evidence
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Attempt ownership not valid"
            );
        }

        audit.insert(
                AuditEvents.submissionAccepted(
                        attemptId,
                        evidence
                )
        );
    }
}
```

`MailAttemptRepository`, `AcceptedEvidence`, and `AuditEvents` are illustrative abstractions.

Properties to preserve:

- State updates and audit inserts **belong to the same local transaction** whenever possible.
- `claimToken` prevents stale workers from overwriting outcomes after losing a lease.
- If 0 rows updated, never insert a phantom accepted audit event.
- If the audit insert fails, the transaction must respond consistently per policy.
- Never perform SMTP network I/O inside this transaction.
- If audits live in an external system, use a publication outbox instead of assuming distributed transactions.

### Never run SMTP inside the finalize transaction

Because SMTP is an external side effect, calling `send` between `BEGIN` and `COMMIT` creates no atomicity. A DB rollback cannot "unsend" an email.

## 23. Auditing and idempotency

An attempt's result may be written multiple times due to retry updates, duplicate webhooks, or message broker redeliveries. The audit trail must avoid **counting repeated physical deliveries as multiple business actions**.

You can use a semantic deduplication key:

```text
attemptId + auditEventType + outcomeVersion
```

or the source event's unique ID constrained in the database.

Example:

```sql
CREATE TABLE mail_audit_dedupe (
    source_system      VARCHAR(64) NOT NULL,
    source_event_id    VARCHAR(128) NOT NULL,
    audit_event_id     VARCHAR(64) NOT NULL,
    PRIMARY KEY (source_system, source_event_id)
);
```

This is one illustrative option. Contracts must define `sourceEventId` as the **event's** ID, not the notification ID; one notification can legitimately have many attempts/events.

### Do not mistakenly deduplicate valid distinct events

One attempt might record:

- `ATTEMPT_STARTED`.
- `SUBMISSION_UNKNOWN`.
- After reconciliation, a follow-up `SUBMISSION_RECONCILED` event.

Never overwrite or delete the older event as though uncertainty never existed. Emit a correction/reconciliation event linked to the prior event instead.

At the same time, never emit a second `SUBMISSION_ACCEPTED` for the same attempt merely because a webhook reported delivered.

## 24. Auditing events from provider webhooks

When receiving a bounce/delivered webhook:

1. Authenticate the source per provider contract.
2. Verify signatures/timestamps if supported.
3. Enforce payload size, parsing, and schema limits.
4. Extract `providerEventId` or a source-event deduplication key.
5. Resolve the exact provider route, attempt, notification, and recipient.
6. Persist meaningful events and states per policy.
7. Never store raw webhook bodies as default audit records.
8. Guard against duplicate or out-of-order arrivals.

Example record:

```json
{
  "eventType": "PROVIDER_BOUNCED",
  "notificationId": "notif-302",
  "attemptId": "attempt-302-02",
  "providerRoute": "transactional-primary",
  "outcomeCode": "BOUNCED",
  "reasonCode": "INVALID_RECIPIENT",
  "occurredAt": "2026-11-12T08:10:00Z",
  "recordedAt": "2026-11-12T08:10:01Z"
}
```

There is no need to persist full bounce prose, raw recipients, or complete HTTP request headers in audits.

### Late or out-of-order events

A `DEFERRED` webhook can arrive **after** a `DELIVERED` event despite occurring earlier. The event store should separate `occurredAt` and `recordedAt`; derived state must follow state-machine rules rather than naive `last-write-wins` by arrival time.

If a provider emits events like a complaint after delivery, preserve the original semantics rather than forcing an overly simplistic linear order.

## 25. Auditing privileged manual actions

Operator actions usually demand tighter auditing than automated retries:

- Requesting a notification resend.
- Cancelling a job or campaign.
- Changing SMTP routes.
- Temporarily raising quotas/rate limits.
- Reprocessing a DLQ.
- Overriding suppression/consent under approved workflows.
- Exporting audit reports.
- Viewing sensitive evidence in restricted areas.

A `MANUAL_RESEND_AUTHORIZED` event might need:

```json
{
  "eventType": "MANUAL_RESEND_AUTHORIZED",
  "notificationId": "notif-302",
  "actorType": "OPERATOR",
  "actorRef": "staff-ref-18",
  "reasonCode": "CUSTOMER_SUPPORT_APPROVED",
  "policyVersion": "resend-policy-v3",
  "correlationId": "corr-incident-40"
}
```

`actorRef` can point to an access-controlled identity store. Avoid storing names, personal emails, full request bodies, or free-text reasons containing PII unless an approved use case requires them.

### Distinguish authorization from execution

Authorizing someone to resend does not mean the notification was actually sent again. Persist the authorization/action-request event separately from the attempt/SMTP outcome.

## 26. Audits are not SMTP debug dumps

In Jakarta Mail/Spring Mail, enabling SMTP debugging aids protocol investigation but must be treated as a **strictly controlled engineering tool**.

Never:

```text
Persist entire SMTP conversation forever
Persist AUTH transcript
Persist raw MimeMessage
Persist all recipient addresses inside audit
```

In particular, avoid authentication debug modes that expose credentials. If diagnostic logging is enabled:

- Restrict access rights.
- Keep enablement windows short.
- Apply redaction mechanisms.
- Prevent logs from shipping to unintended destinations.
- Delete per retention.
- Disable right after investigation.
- Separately audit who enabled debugging and for how long if operations policy requires.

The audit trail needs only `reasonCode=AUTHENTICATION` or `TLS` plus safe references—never AUTH strings or passwords.

## 27. Error categories and forensic detail

An investigation may need finer detail than minimal audits hold. Layer it:

```text
Standard audit event
  eventType, time, IDs, route, outcome, reasonCode
            |
            v
Privileged diagnostic reference (optional)
  error details, bounded retention, redaction
            |
            v
Restricted evidence store (rarely)
  raw artifacts, explicit approval and retention
```

Each tier defines:

- Purpose.
- Owner.
- Access conditions.
- Retention period.
- Access auditing.
- Deletion/key-management controls.

Never let "view standard audits" permission automatically grant permission to download raw MIME evidence.

## 28. Purpose-driven retention, not one number for all data

A system may require distinct retention classes:

| Data class | Goal | Illustrative policy |
|---|---|---|
| SMTP diagnostic logs | Short-term error debugging | Short, auto-expiring |
| Mail submission attempts | Investigating retries/unknowns | Aligned with SLOs and dispute windows |
| Minimal audit events | Tracing decisions/actions | Per approved legal/business requirements |
| Recipient destination mapping | Sending mail and customer support | Delete/minimize once purpose ends |
| Raw MIME/attachment evidence | Special purpose if mandatory | Separate store, strict permissions/retention |
| Aggregated metrics | Operational trends | Can often live longer if non-identifying |
| Backup copies | Disaster recovery | Needs expiration schedules and deleted-data handling |

Exact durations (7 days, 30 days, 12 months, etc.) **must never be stated as mandatory defaults**. They depend on purpose, contracts, organizational policy, and applicable laws. Define retention via approved policy and configure enforcement accordingly.

### Avoid keeping data forever "just in case"

Without a clear purpose, infinite retention inflates cost and risk. For critical transactional emails, never delete audits earlier than valid obligations require; for data no longer needed, never keep it simply because storage is cheap.

## 29. Retention policies need owners and enforcement

A production policy needs at least:

```text
dataClass
purpose
owner
retentionPeriod
startOfRetention
deletionMethod
legalHoldException
accessRoles
backupHandling
verification/alerting
```

Example:

```text
mail_audit_minimal:
  purpose: submission traceability
  owner: messaging-platform
  retention: defined by approved policy
  start: event recordedAt
  deletion: partition drop / controlled delete
  access: audited operator roles
  legalHold: explicit scoped flag
```

This is a **policy template**, not prebuilt Spring Boot YAML configuration.

Multiple clocks may exist: `occurredAt` reflects when the event happened, `recordedAt` when persisted, and `retentionUntil` when policy requires disposition. Guard against late-arriving events accidentally extending retention beyond policy bounds.

## 30. Deleting data while preserving audit integrity

One tension: audits may link to users/recipients while personal data must be removed when purpose ends or upon valid requests.

Options include:

- **Clearing identifying fields** from auxiliary records once retention expires.
- **Deleting pseudonym mapping tables** so audits hold only events unlinkable via remaining data, where appropriate.
- **Tombstoning** logical notifications with minimal IDs and statuses.
- **Deleting entire audit records** once retention expires and no legal holds apply.
- **Crypto-shredding** inside architectures with genuinely scoped keys and well-understood backup/key lifecycles.

Never call a record "anonymous" if `notificationId` plus backups/lookup tables can still trace back to the recipient.

### Append-only and the right to erasure are not architecturally contradictory

"Append-only" protects events against tampering **during their retention period**—it does not mean retaining personal data forever. Partition/segment audits by retention class, purge on schedule, and record deletion actions per policy without keeping the deleted personal data itself.

When legal holds apply, define explicit scope and authority; never turn them into a blanket flag holding all data indefinitely.

## 31. Minimize data at the event source

An effective principle:

> **Do not collect sensitive data upfront and expect downstream redaction to rescue every copy.**

Risk-prone API design:

```java
public void audit(Object event) {
    String json = objectMapper.writeValueAsString(event);
    auditRepository.insert(json);
}
```

Anything passed in gets serialized—including a `MailCommand` holding recipients, subjects, bodies, and tokens.

Better:

```java
public interface MailAuditRecorder {

    void recordSubmissionAccepted(
            String notificationId,
            String attemptId,
            String routeId
    );

    void recordSubmissionFailure(
            String notificationId,
            String attemptId,
            String routeId,
            MailAuditReason reason
    );
}
```

A narrow interface prevents callers from passing raw `MimeMessage` or `Exception` objects. For richer events, use allowlisted DTOs.

**Sink-side redaction is only an additional safeguard**, not your sole data minimization strategy.

## 32. Redaction when structured logging is required

When logging incidents:

```java
logger.warn(
        "Mail attempt failed: notificationId={}, "
      + "attemptId={}, route={}, reason={}",
        notificationId,
        attemptId,
        routeId,
        errorCategory
);
```

Avoid:

```java
logger.error(
        "Failed to send {} to {} with secret {}",
        mimeMessage,
        recipientEmail,
        smtpPassword
);
```

Never assume every `toString()` is safe. An auto-generated command/domain object `toString()` can dump full bodies and recipients.

When logging stack traces, assess what recipient addresses/hostnames/provider replies the exception cause chain may hold, and keep them inside permissioned, short-retention diagnostic logs. Never copy raw stack traces into audit events.

## 33. Audit trails and metrics must avoid high-cardinality labels

Useful metrics:

```text
mail_audit_recorded_total
mail_audit_write_failure_total
mail_submission_attempt_total
mail_submission_accepted_total
mail_submission_unknown_total
mail_provider_event_duplicate_total
```

Safer tags:

```text
event_type=SUBMISSION_ACCEPTED
route=transactional-primary
outcome=SMTP_ACCEPTED
error_category=TIMEOUT
```

Never use:

- `notificationId`, `attemptId`, `providerMessageId`.
- Recipient email or user ID.
- Subject/body.
- Raw exception messages.
- Attachment names or personalized URLs.

High cardinality harms storage/cost and increases PII leakage risk. Use permissioned log/audit databases for ID-based lookups; use metrics strictly for aggregate trends.

## 34. Integrity: append-only does not mean absolute immutability

Audits support investigations, so unauthorized modification/deletion risks must be minimized.

Controls:

- Application DB roles hold only required `INSERT` and `SELECT` rights; restrict `UPDATE`/`DELETE`.
- Partition retention runs under a separate service account.
- Maintain independent audits for permission/policy changes and deletion jobs.
- Protect backups and disaster recovery procedures.
- Isolate audit-store admin privileges from general system admins.
- Monitor sequence gaps, duplicate event IDs, and ingestion lag.

Where stronger tamper-evidence is required, consider:

- Hash chains across records or segments.
- HMAC/digital signatures with protected keys.
- WORM/immutable storage during applicable retention.
- External checkpoints/attestations.
- Periodic verification jobs.

Still, **hash chains only detect certain modifications** if checkpoints/keys are trustworthy; they do not independently prove who sent an email, SMTP acceptance, or lawful data collection.

### Never hash full MIME solely for integrity

Hashing raw messages may serve specific integrity-verification use cases, yet still creates linkability/correlation exposure requiring data-minimization review. Without a concrete purpose, keep only template versions and event outcomes.

## 35. Least-privilege audit read permissions

Not everyone on the engineering team needs access to every audit record.

One model:

| Role | Appropriate access |
|---|---|
| Application worker | Append minimal audit records |
| Support agent | Query notifications scoped to assigned tickets |
| Operations engineer | View event timelines and reason codes |
| Security auditor | View access/configuration audits per authorization |
| Compliance/data steward | Manage retention/legal holds and approved exports |
| Database retention job | Delete/maintain partitions per policy |
| Typical developer | Access test data or minimized diagnostics |

**Authorization must be checked at the service/API layer** even when audit tables hold only opaque IDs. Looking up `notificationId` to resolve recipients/addresses can cross tenant boundaries if unchecked.

Enforce tenant scoping and row-level security where appropriate; never rely merely on a frontend condition hiding a "view email" button.

## 36. Auditing access to audits themselves

A mature audit system also needs to track:

- Who inspected timelines of sensitive notifications?
- Who exported audit data to files?
- Who used privileged access to view raw MIME evidence?
- Who altered retention/policies?
- Who requested deletions or legal holds?
- Who triggered manual resends?

Record **access audits** for sensitive operations while avoiding infinite loops ("auditing the write of an audit of a write"). Isolate audit-of-audit into a dedicated channel or bounded event types with guards.

There is no need to audit routine metric dashboard refreshes unless a specific security/business reason demands it.

## 37. Multi-tenancy and data boundaries

If the system serves multiple tenants:

- Audits must always carry verifiable tenant scope.
- One tenant must never look up another tenant's `notificationId`.
- `providerRoute` and `actorRef` must not expose confidential credentials/sender profiles.
- If centralized audit storage is shared, queries/storage must enforce tenant filtering/authorization.
- Audit exports must enforce data-scope checks.
- Retention classes may differ under valid policies, while avoiding leaks from mixed data.
- Upon tenant offboarding, handle audits, mappings, attachments, backups, and legal holds per policy.

An opaque `tenantRef` can be included to enforce query scoping, while still treating it as an identifier requiring protection. Avoid defaulting to `tenantRef` as a Prometheus label if tenant counts are very high.

### Cross-tenant events

A batch provider webhook may include events for multiple recipients/tenants. The webhook handler must map each event to its verified notification/tenant before writing audits, never trusting unverified tenant IDs inside payloads.

## 38. When to use evidenceRef?

Routine audits should rely on event metadata alone. Exceptions needing detailed proof include:

- Contractual disputes over **exact delivered content**.
- Approved fraud or security investigations.
- Document preservation obligations under explicit policy.
- Rare incidents requiring raw provider responses.
- Content-signature verification where specifically mandated.

In such cases:

```text
mail_audit_event
  eventId
  notificationId
  eventType
  evidenceRef (nullable)
                |
                v
    Restricted evidence store
      - encryption at rest
      - scoped access
      - immutable object/version if required
      - explicit retention
      - access audit
      - deletion/hold policy
```

Never embed raw payloads straight into audits just because adding a BLOB column is faster. `evidenceRef` must stay secure—never a public URL or long-lived presigned URL.

## 39. Auditing sender, route, and template changes

Not only email attempts need auditing. Configuration changes can alter all outbound behavior:

- Changing SMTP providers or failover routes.
- Toggling SMTP AUTH or altering TLS policies.
- Changing verified sender profiles.
- Adjusting retry/backpressure policies.
- Publishing new template versions.
- Modifying suppression/consent rules.
- Enabling manual replays or bulk resends.

A configuration audit might record:

```json
{
  "eventType": "MAIL_ROUTE_POLICY_CHANGED",
  "actorType": "OPERATOR",
  "actorRef": "staff-ref-18",
  "policyVersion": "mail-route-v8",
  "changeCategory": "FAILOVER_PRIORITY",
  "occurredAt": "2026-11-12T08:20:00Z"
}
```

Never record **old/new SMTP passwords**, API tokens, or private keys inside audit diffs. To prove secrets rotated, record `secretVersionRef` or `rotationEventId` containing no secret values.

### Should template changes store content?

When template versions live in a repository/artifact store, audits can store `templateKey` and approved version/hash references. There is no need to copy full template HTML into every email audit event.

## 40. Auditing and law: never assume one universal retention period

Data protection, recordkeeping, industry rules, and jurisdictional requirements vary and evolve. Never state "all email audits must be kept for 7 years" or "all email addresses must be deleted after 30 days" without confirming actual scope and grounds.

A proper workflow:

1. Identify processing purposes and data classes.
2. Identify data controllers/processors and involved systems.
3. Identify applicable legal/contractual policies.
4. Approve retention periods and access controls.
5. Configure deletion and backup handling.
6. Revisit whenever providers, industries, or jurisdictions change.
7. Record authorized exceptions/legal holds.

This represents technical design guidance; legal conclusions must be verified against actual regulations with designated owners.

## 41. Operating retention and backups

A deletion job must not wipe only the primary table while data persists indefinitely in:

- Application logs.
- Log aggregation/SIEM.
- Database replicas.
- Backups/snapshots.
- Data warehouse exports.
- Developer debug dumps.
- Queues/DLQs.
- Temporary object storage.
- Incident attachments.

Maintain a **data inventory and deletion coverage**. For backups that cannot be edited in place, enforce expiration windows, safe restore workflows, and policies reapplying deletions upon recovery.

### Storing events too long gets expensive

Each logical notification can span multiple attempts, each emitting multiple events. At millions of notifications daily, audit tables grow fast.

Techniques include:

- Partitioning by time and retention class.
- Indexing solely for real queries.
- Event-type allowlists.
- Controlled archiving/compaction where policy permits.
- Avoiding repeating templates/bodies/recipients across events.
- Bounding custom JSON payloads.

Never "save storage" by randomly purging critical events early, nor log every routine worker poll tick.

## 42. Monitoring the health of the audit pipeline itself

A reliable audit trail must detect when events go missing.

Suggested metrics:

| Signal | Purpose |
|---|---|
| `mail_audit_append_success_total` | Events written successfully |
| `mail_audit_append_failure_total` | Audit write failures |
| `mail_audit_publish_pending` | Events awaiting export to external audit store |
| `mail_audit_publish_oldest_age_seconds` | Age of oldest pending export event |
| `mail_audit_dedupe_total` | Duplicate source events dropped |
| `mail_audit_retention_delete_total` | Records deleted per policy |
| `mail_audit_retention_overdue` | Overdue records not yet deleted |
| `mail_audit_schema_rejected_total` | Invalid events rejected |
| `mail_audit_integrity_failure_total` | Integrity check failures if enabled |

These names are illustrative examples, not built-in Spring Mail meters.

Alert on error rates, ingestion lag, overdue retention, and discrepancies between notification/attempt transitions and audit event counts. Never treat "audit service is UP" as proof every event was recorded.

## 43. Testing data minimization

Some tests need no real SMTP server—just schema validation:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void auditEventHasNoMailContentFields() {
    MailAuditEvent event =
            auditFactory.submissionAccepted(
                    "notif-302",
                    "attempt-302-01",
                    "transactional-primary"
            );

    String serialized = objectMapper.writeValueAsString(
            event
    );

    assertThat(serialized)
            .doesNotContain("smtpPassword")
            .doesNotContain("accessToken")
            .doesNotContain("htmlBody")
            .doesNotContain("attachmentBytes")
            .doesNotContain("customer@example.net");
}
```

`auditFactory` and `objectMapper` are test fixtures configured by the app; checking field names is only one defense layer. Stronger tests assert an **allowlist of permitted fields** rather than merely scanning for a few forbidden strings, since sensitive content might appear under an unexpected field name.

### Testing event schema contracts

- `eventType` belongs to a valid enum.
- `schemaVersion` is explicit.
- `occurredAt`/`recordedAt` use `Instant`.
- `attemptId` is required only on attempt events.
- No raw subject/body/recipient appears in standard audits.
- `reasonCode` belongs to a finite taxonomy.
- Arbitrary objects are rejected from serialization.
- `correlationId` contains no PII.
- Optional JSON extension payloads enforce maximum sizes per policy.

## 44. Testing transactional consistency

Test cases:

1. Create notification and audit event in one transaction; rollback removes both.
2. Finalize accepted attempt and write audit in one transaction.
3. Attempt update fails due to invalid claim token; no accepted audit is written.
4. Audit write fails; transaction handles failure consistently per policy.
5. External audit publisher crashes; local outbox event remains for retry.
6. External audit consumer receives duplicates; deduplicates by source event ID.
7. Crash after SMTP acceptance before DB finalization; attempt does not silently turn into known rejected.
8. Audit event arrives after current state; timeline still records both timestamps accurately.

Transaction/locking tests should run against a production-compatible database when verifying isolation, rather than relying solely on mocked repositories.

### How to handle audit write failures?

This is an SLO/compliance decision:

- For actions requiring mandatory pre-execution auditing, block/rollback whatever can be rolled back if audit persistence fails.
- For an already-executed SMTP attempt, the network side effect cannot be rolled back; trigger state recovery and incident alerts if finalization auditing fails.
- Never confuse best-effort metrics/logs with mandatory audits.
- Use a local durable event outbox to avoid making the send path synchronously dependent on a remote audit service.

**Never silently swallow audit exceptions and still tell the business auditing was guaranteed.**

## 45. Testing redaction and access controls

A matrix:

| Test | Expected |
|---|---|
| Support agent queries notification on assigned ticket | Sees only permitted fields |
| Support agent queries another tenant | Denied |
| Operator views timeline | Sees IDs, outcome, and `reasonCode` |
| Operator lacks evidence permission | Cannot access raw MIME |
| Approved privileged evidence access | Emits dedicated access audit |
| Webhook carries email/raw payload | Audit persists normalized event only |
| SMTP exception embeds username | Audit omits raw message |
| Token appears in command `toString()` | Command never serialized into audit |
| Audit export | Scope, retention, and access verified |
| Recipient mapping deleted | Audit linkability reduced per policy |
| Retention overdue | Triggers alerts and remediation |
| Backup restore | Deletion policy reapplied post-restore |

Do not assert HTTP status codes alone; verify **response bodies and exports** contain zero unauthorized fields.

## 46. Testing tamper resistance, deduplication, and event ordering

When systems enforce append-only or integrity checks:

- Test standard app roles cannot `UPDATE`/`DELETE` audit events.
- Test retention jobs delete strictly within authorized scope.
- Test duplicate event IDs are deduplicated or explicitly rejected.
- Test integrity mismatches are detected/alerted.
- Test correction events link to prior events without silently rewriting history.
- Test events occurring earlier yet persisted later retain distinct timestamps.
- Test manual resend authorization events remain separate from SMTP accepted events.
- Test delivered/bounced webhooks are not counted as new submission attempts.
- Test partial multi-recipient outcomes when transport supports them.

Never treat hash chains as absolute proof if keys/checkpoints reside inside the same modifiable system.

## 47. Case study: order confirmation email

Suppose a customer completes payment and the app must send a confirmation email.

### Before sending

```text
Business event:
  ORDER_PAID

Audit:
  NOTIFICATION_QUEUED
  notificationId=notif-302
  sourceType=DOMAIN_EVENT
  templateKey=order-confirmation
  templateVersion=v7
```

Customer name, email address, and order total do not belong in the audit if already governed inside permissioned domain/notification stores.

### First attempt hits rate limiting

```text
Audit:
  ATTEMPT_STARTED
  notificationId=notif-302
  attemptId=attempt-302-01

Audit:
  SUBMISSION_REJECTED
  attemptId=attempt-302-01
  reasonCode=RATE_LIMITED

Audit:
  RETRY_SCHEDULED
  notificationId=notif-302
  nextAttemptRef=retry-policy-v2
```

Do not retain raw SMTP replies needlessly; technical logs can hold safe short-term detail.

### Second attempt succeeds

```text
Audit:
  ATTEMPT_STARTED
  attemptId=attempt-302-02

Audit:
  SUBMISSION_ACCEPTED
  attemptId=attempt-302-02
  outcome=SMTP_ACCEPTED
  providerRoute=transactional-primary
```

### Provider sends delivered webhook

```text
Audit:
  PROVIDER_DELIVERED
  attemptId=attempt-302-02
  providerRoute=transactional-primary
  eventSource=PROVIDER_WEBHOOK
```

If a customer opens a complaint, the system can display this entire timeline without letting operators view full email content, tokens, or attachments.

## 48. Common anti-patterns

| Anti-pattern | Risk | Solution |
|---|---|---|
| Storing full `MimeMessage` in audits | Copies bodies/attachments and PII | Minimal metadata; separate evidence store if needed |
| Storing subjects on every event | Subjects may contain PII/OTPs | Template key/version |
| Storing raw recipients on every attempt | Duplicates personal data | `recipientRef` and privileged lookup |
| Unkeyed email hash claimed anonymous | Vulnerable to dictionary attacks/linking | Data minimization; governed HMAC if needed |
| Serializing arbitrary event objects | Accidentally stores secrets/bodies | Typed DTOs and allowlists |
| Auditing full SMTP debug logs | Leaks credentials/provider details | Reason taxonomy, short-lived debug |
| Single `sent=true` flag | Loses attempts/unknown states | Event timelines/state machines |
| Recording `DELIVERED` on `send` success | False evidence | `SMTP_ACCEPTED` |
| Writing `QUEUED` audit before commit | Phantom event on rollback | Local transaction |
| Synchronous remote audit on every HTTP request | Dependency outage breaks or drops events | Local durable outbox + publisher |
| Swallowing audit errors | Silent loss of traceability | Failure policies and alerts |
| Using email/token as audit IDs | PII leaks via indexes/URLs/logs | Opaque identifiers |
| Letting every operator read raw MIME | Violates least privilege | Restricted evidence access |
| Indefinite append-only | Fails retention/deletion obligations | Controlled policies, partitions, exceptions |
| Putting recipients in log/metric tags | Cardinality and privacy | Bounded enum tags |
| Using raw webhook bodies as audit payloads | PII/token/schema drift | Verify, normalize, deduplicate |
| Not auditing manual resends | Unknown who caused duplicates | Authorized action events |
| Preserving integrity with no deletion plan | Collides with retention/privacy | Segmentation and scoped deletion |

## 49. Production design checklist

1. Define **audit objectives** before choosing fields.
2. Separate audits, diagnostic logs, metrics, and traces.
3. Limit event types to significant decisions/actions.
4. Separate business occurrence, notification, attempt, and provider event IDs.
5. Use allowlisted, versioned event DTOs.
6. Never pass raw `MimeMessage`/`Exception`/`MailCommand` to an audit serializer.
7. Never store OTPs, reset tokens, SMTP secrets, or attachment bytes.
8. Avoid raw subjects and raw recipients whenever less-sensitive references work.
9. If using HMAC pseudonyms, manage keys properly and never label them anonymous.
10. Distinguish SMTP accepted, known rejected, unknown, and downstream delivered.
11. Write audits at sound transaction boundaries; never record false evidence.
12. Separate SMTP network I/O from database transactions.
13. Enforce idempotent event IDs and webhook deduplication.
14. Preserve enough correlation and attempt history to investigate retries.
15. Audit actors and authorization on manual resends/cancels/route changes.
16. Approve retention policies with owners, start triggers, and deletion jobs.
17. Maintain inventories for logs, exports, backups, queues, and evidence stores.
18. Separate audit-viewing permissions from raw email/evidence access.
19. Audit access to sensitive queries and exports.
20. Enforce multi-tenancy and ID-lookup authorization.
21. Add integrity/tamper-evidence if mandated while understanding its limits.
22. Alert on audit write failures, publication lag, and overdue retention.
23. Unit-test field allowlists, redaction, and secret-free logs.
24. Integration-test transactions, replays, crashes, and unknown outcomes.
25. Maintain runbooks for slow or broken audit pipelines.

## 50. Takeaways

- **A good audit trail is not the one storing the most data**—it captures enough meaningful events with the least sensitive data.
- Events like `NOTIFICATION_QUEUED`, `ATTEMPT_STARTED`, `SUBMISSION_ACCEPTED`, `SUBMISSION_REJECTED`, `SUBMISSION_UNKNOWN`, and provider events are far more useful than full MIME dumps.
- Never confuse SMTP accepted with delivered, inbox placement, or user read.
- Notification IDs, attempt IDs, and provider IDs carry different scopes.
- Subjects, recipient addresses, bodies, and attachments can be sensitive; never repeat them in default audits.
- Typed audit events and field allowlists stop accidental data collection at the source.
- Pseudonyms are not automatically anonymous; lookup tables/keys still need protection.
- Event types and reason codes should stay bounded; never copy raw exceptions or SMTP transcripts.
- Write audits inside proper local transactions and use an outbox when forwarding to central stores.
- SMTP does not join database transactions, so accepted emails cannot be rolled back.
- Append-only protects integrity during retention while still requiring a retention/deletion policy.
- Viewing audit timelines does not grant rights to download raw MIME evidence.
- Always record actor and rationale for manual resends, policy overrides, or evidence access.
- Monitoring must detect audit write failures/lag, not just count sent emails.
- Tests must verify field allowlists, rollbacks, deduplication, access controls, and deletion coverage.

**Conclusion:** In production Spring Framework Mail systems, a valuable audit trail is **a structured sequence of events describing who or what requested a send, which notification was queued for processing, which attempt SMTP accepted or rejected, and what downstream evidence arrived**. Store identifiers and states minimally, place raw content inside separate permissioned stores only when genuinely required, and apply consistent retention, integrity, and testing. That way the system can investigate delivery incidents thoroughly without building an excessive personal-data warehouse disguised as "auditing."
