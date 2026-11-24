# Data Retention for Email Content and Metadata in Spring Framework Mail

When an application sends emails using **Spring Framework Mail**, the message does not exist solely inside the `JavaMailSender.send(...)` call. Before sending, the application may store the request in a transactional outbox, render templates, and hold HTML and attachments. After the SMTP relay accepts the message, the system continues to store statuses, response codes, provider message IDs, bounces, complaints, retry schedules, and logs. This data helps operations, but may contain **personal information, transaction data, sensitive documents, or verification codes**.

Therefore, a production system needs to design **data retention**: what data may be stored, for what purpose, how long to keep it, who has access, when to delete/anonymize it, how to handle copies in logs/backups/providers, and cleanup evidence.

> **Do not retain full email content merely for debugging convenience; nor delete necessary data before completing retries, reconciliation, or valid obligations.** Distinguish the lifecycle of content, metadata, operational traces, and records that must be kept on appropriate grounds.

`JavaMailSender` is Spring's email-sending abstraction. **Spring Mail does not automatically manage retention across databases, object storage, SMTP providers, logs, and backups.** Components such as `RetentionPolicy`, `MailCleanupWorker`, and the SQL tables below are application design patterns, not default Spring APIs.

## 1. What does data retention mean?

Data retention is a set of rules defining:

1. **Collection:** only the data necessary for the defined functionality and purpose.
2. **Duration:** how long and measured from which event.
3. **Access control:** which services and roles are permitted to process it.
4. **Disposition:** delete, anonymize, aggregate, or move to an approved archive.
5. **Exceptions:** legal holds, disputes, audits, and valid obligations.
6. **Evidence:** how to verify that cleanup has completed.

Retention differs from **backup**: backups are a recovery mechanism, not permission to retain data indefinitely. Retention also differs from **send scheduling**: `scheduledAt` determines when submission is allowed, while `purgeAfter` determines when data becomes eligible for removal.

### Questions that need answers

- Should the body be retained after the SMTP relay has accepted the message?
- Do we need the full recipient email address or an ID together with the status?
- Until when must attachments remain available so that retries do not fail?
- Can `SUBMISSION_UNKNOWN` be deleted the same way as `SUBMITTED`?
- When a data deletion request arrives, how are queues, DLQs, logs, providers, and backups handled?
- How is the suppression list retained so we do not send again to someone who unsubscribed?
- Who has the authority to place/release a legal hold, and how far does the retention scope extend?

**There is no single fixed TTL that is right for every organization.** The timeframes in the examples are illustrative only; actual retention periods must be based on purpose, data type, risk level, contracts, and applicable regulations, with input from legal/privacy owners when needed.

## 2. Content, metadata, and operational data

| Category | Examples | Characteristics |
| --- | --- | --- |
| Body content | Plain text, HTML | May contain PII, invoices, OTPs, reset links |
| Subject | Person's name, review outcome | Can itself disclose sensitive information |
| Headers | From, To, Cc, Bcc, Reply-To | Identity and communication relationships |
| SMTP envelope | MAIL FROM, RCPT TO | May differ from addresses in headers |
| Raw MIME | Entire message, multipart | Often contains body, headers, and attachments |
| Attachments | PDF, images, records, CSV | May contain confidential documents or personal data |
| Template model | Name, order code, amount, token | Can be as sensitive as or more sensitive than the body |
| Delivery metadata | Provider, attempt ID, SMTP code, timestamp | Operationally useful, yet can still link to an individual |
| Provider events | Accepted, deferred, bounce, complaint | Contains recipient address, rejection reason |
| Audit records | Who scheduled/sent/cancelled/changed permissions | Needs access control and retention |
| Logs/traces/metrics | Exceptions, correlations | Easily copies body or secrets accidentally |
| Suppression | Unsubscribe, complaint, hard bounce | Must be stored sufficiently to prevent erroneous sends |
| Queue/cache/DLQ | Serialized payload, retry data | Copies are hard to discover during deletion |
| Backups/snapshots | DB/object versions | Copies independent of active data |

**Metadata does not mean harmless data.** Recipient address, subject, and send time can reveal what type of service a person is using. Do not define retention as "only the body is personal data, while metadata is kept forever."

### Data can be copied multiple times

~~~mermaid
flowchart LR
    A["Business event"] --> B["Outbox DB"]
    B --> C["Template render"]
    C --> D["Raw MIME / attachment storage"]
    D --> E["JavaMailSender / SMTP"]
    E --> F["Provider queue / events"]
    B --> G["Logs / traces"]
    E --> G
    F --> H["Event inbox / projection"]
    B --> I["DB backups"]
    D --> J["Object versions / backups"]
    H --> I
~~~

Deleting a row in `mail_outbox` **does not automatically delete** objects storing HTML/MIME/attachments, DLQs, provider copies, logs/APM, or backups. Retention must have a **data inventory and ownership** for each storage location.

## 3. Tying retention to purpose

Common purposes include:

1. **Completing delivery:** keep payload until submission succeeds, fails permanently, or expires.
2. **Retry:** requires payload, failure category, and `nextAttemptAt`.
3. **Reconciliation:** requires provider attempt ID when the outcome is unknown.
4. **User support:** requires status, reason, and minimal metadata.
5. **Preventing unintended sends:** requires properly scoped suppression/consent, not old raw bodies.
6. **Auditing:** may require an event trail, not necessarily the entire email.
7. **Legal/contractual obligations:** may require retaining a document or record as regulated.
8. **Analytics:** usually only needs aggregated or de-identified figures.

### Examples by email type

| Type | Commonly sensitive data | Design direction |
| --- | --- | --- |
| OTP/reset | Short-lived codes/tokens | Do not keep plaintext longer than needed; purge upon expiration |
| Order confirmation | Address, products, order code | Store send status separately; business documents have their own lifecycle |
| Invoice | Document and amounts | Do not treat SMTP transcripts as the primary accounting record |
| Marketing | Email address, tracking, campaign | Respect consent/suppression; minimize raw per-recipient body |
| Security alert | Login info, anomalous events | Restrict content and viewers |
| Support mail | Free-form content, attached documents | Retention aligned with ticket and data classification |

A business document may need long-term retention on valid grounds, but that **does not imply** that SMTP transcripts, retry payloads, and HTML renders all have to be kept for the same duration.

## 4. Retention inventory and policy version

| Field | Meaning |
| --- | --- |
| `dataset` | Body, raw MIME, attachment, outbox, provider event, log |
| `purpose` | Processing purpose |
| `classification` | Sensitivity level |
| `dataOwner` | Business owner |
| `systemOwner` | Storage operations team |
| `retentionTrigger` | CreatedAt, terminalAt, caseClosedAt... |
| `retentionPeriod` | Approved duration |
| `deletionMethod` | Delete, anonymize, aggregate, cryptographic erasure |
| `exceptions` | Legal hold, dispute, audit |
| `backupHandling` | Backup TTL and restore procedure |
| `providerHandling` | Provider-side controls/commitments |
| `policyVersion` | Rule version |
| `evidence` | Cleanup evidence |

Changing a TTL in source code without updating the policy, or changing the policy without handling older records, creates inconsistencies that are hard to explain. Therefore, each record or retention decision should identify the **policy version** used.

### Illustrative retention matrix

| Dataset | Start trigger | When eligible for deletion | Minimal data that may be kept |
| --- | --- | --- | --- |
| Unsent payload | When request is created | When no longer pending/retry/unknown and required window has passed | State, stop reason |
| Rendered HTML/text | Render/submit | When no longer needed for resend or support content | Template ID/hash/version |
| Raw MIME | Upon creation/capture | After valid inspection/reconciliation purpose | Hash and necessary metadata |
| Attachment staged | Upload/stage | After all referencing jobs finish and holds/retention expire | Hash, type, ID |
| SMTP attempts | When attempt finishes | After support/reconciliation period | Aggregated metrics |
| Provider webhook | When event is received | After necessary projection/audit is stored | Event type, normalized reason |
| Detailed debug log | When written | Short log TTL per policy | Aggregated metrics |
| Suppression | Unsubscribe/bounce/complaint | Per send-prevention purpose and applicable rules | Minimal identifier/flag |
| Backup | When snapshot is created | Per approved backup policy | Evidence of snapshot expiration |

This is a **design pattern**, not a legally binding retention schedule. In particular, suppression records may need to exist long enough to honor opt-out choices, while minimizing personal data and controlling usage access.

## 5. Which event does TTL start from?

A dangerous mistake is using the same query:

~~~sql
DELETE FROM mail_outbox
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '14 days';
~~~

It can delete an email scheduled months ahead **before it is ever sent**. An email currently retrying or in `SUBMISSION_UNKNOWN` can also be deleted before reconciliation.

Distinguish the timestamps:

| Timestamp | Meaning |
| --- | --- |
| `createdAt` | Request was persisted |
| `scheduledAt` | Time when sending becomes permitted |
| `lastAttemptAt` | Most recent submission attempt |
| `submittedAt` | Relay accepted based on available evidence |
| `terminalAt` | Automated lifecycle ended |
| `reconciledAt` | Unknown-outcome reconciliation completed |
| `caseClosedAt` | Related ticket/dispute closed |
| `contentPurgeAfter` | Time when payload becomes eligible for deletion |
| `metadataPurgeAfter` | Time when metadata becomes eligible for deletion |
| `legalHold` | Exception flag/record requiring a separate decision |

A policy typically computes `contentPurgeAfter = terminalAt + period`, but **do not set `terminalAt` while the job still needs to send, retry, or reconcile**.

### Far-future scheduled email

~~~text
Created:              2026-11-12
scheduledAt:          2027-01-15
status:               PENDING
Content policy:       keep until terminal, then + 14 days
~~~

By December 2026, the payload must still exist so it can be submitted in January 2027. It must not be deleted simply because it was created more than 14 days earlier.

### Schedule cancellation

A `CANCELLED` schedule before sending may purge content earlier than a `SUBMITTED` email, while still retaining cancellation status metadata during the audit/support window if policy requires.

## 6. Separating content lifecycle from metadata

~~~text
CREATE / PENDING / SCHEDULED
          |
          v
RETRY / PROCESSING (payload needed)
          |
          v
TERMINAL / RECONCILED
    |                  |
    v                  v
Short content TTL      Separate metadata TTL
    |                  |
Delete body/MIME       Delete/anonymize
and attachments        attempt/status records
~~~

Content purge must consider multiple places:

- `plain_text_body`, `html_body`, `subject`.
- `template_data_json`, rendered preview.
- Raw MIME and `attachment_storage_key`.
- Serialized queue/DLQ payloads.
- Debug/error messages containing content.
- Caches and exports for support/analytics.

Metadata must also have a TTL; do not keep full recipient addresses and statuses forever. It can be hard deleted, pseudonymized, or aggregated, depending on rights and purpose.

**Pseudonymization does not automatically equal anonymization.** An HMAC of an email address can still link events if the key or lookup table still exists. Do not claim identity has been completely erased merely because the email was replaced with a hash.

## 7. Retention by sending status

| Application status | Payload needed? | Handling |
| --- | --- | --- |
| PENDING | Yes, for future sending | Do not purge yet |
| PROCESSING | May be actively in use | Do not purge while active lease exists |
| RETRY_PENDING | Yes | Retain until retries exhaust/expire |
| SUBMISSION_UNKNOWN | May be needed for reconciliation | Retain bounded evidence and reconcile |
| SUBMITTED | Raw content may no longer be needed | Purge body after required window |
| FAILED_PERMANENT | No auto-retry with same data | Purge after support/review window |
| CANCELLED | No send needed | Purge early if no hold exists |
| EXPIRED | No longer useful | Purge token/body early |
| DEAD_LETTER | May be reviewed/replayed | Separate TTL; do not retain indefinitely |
| QUARANTINED | Content may be malicious | Isolated storage and separate retention |

These are custom application-designed states. Spring Mail does not provide `SUBMISSION_UNKNOWN` or `DEAD_LETTER` out of the box.

`JavaMailSender.send()` returning normally usually only proves **SMTP relay accepted submission**, not Inbox delivery. If the provider accepted the message and handles downstream retries, the application does not need to keep the full body forever just waiting for a `DELIVERED` event.

### Unknown outcome scenario

~~~text
Application                 SMTP relay
     |---- DATA + end ----->|
     |                       | may already accept
     |<--- response lost ----X
     |
     v
SUBMISSION_UNKNOWN
~~~

Do not delete attempt metadata immediately just because the final response was missing; that loses reconciliation capability. At the same time, do not hold payloads indefinitely: define a reconciliation deadline, escalation path, and audited record closure.

## 8. OTPs, reset links, and sensitive content

OTP/reset emails may contain short-lived secrets. You should:

- Avoid storing plaintext tokens if a safer design is possible.
- Never log tokens or include them in exception text.
- Allow only authorized dispatch workers to read payloads.
- Encrypt data at rest according to policy.
- Tie content TTL to the token's actual `expiresAt`.
- Do not send tokens that have already expired.
- Delete plaintext copies early once sending/retrying is no longer needed.

One option is generating the token close to dispatch if workflow and security permit, but do not arbitrarily generate a new token on every SMTP retry: doing so can cause users to receive multiple inconsistent codes. Removing a token field from the database does not eliminate tokens already present in rendered HTML, queues, providers, or logs.

## 9. Mail-sending metadata: keeping only what is needed

Operational metadata may include:

~~~text
notificationId
tenantKey
providerKey
messageCategory
templateVersion
attemptNumber
smtpPhase
normalizedSmtpCode
failureCategory
submittedAt
providerEventType
~~~

Avoid storing full To/Cc/Bcc, raw subjects, raw SMTP transcripts, unredacted provider error text, bodies, or attachment filenames containing PII.

### Example metadata event

~~~json
{
  "notificationId": "notif-184",
  "tenantKey": "tenant-01",
  "providerKey": "smtp-primary",
  "attempt": 1,
  "result": "SUBMITTED",
  "submittedAt": "2026-11-12T10:00:05Z",
  "smtpCode": "250",
  "templateVersion": "receipt-v3"
}
~~~

This is a sanitized event, yet `tenantKey` and `notificationId` can still re-link to an individual; apply appropriate ACLs and retention.

### Provider webhooks

Providers may send accepted, deferred, delivered, bounced, or complained events. A pipeline:

1. Verify signature and provider/account scope.
2. Store the raw event in a durable inbox for deduplication/retry.
3. Update delivery projection idempotently.
4. Delete the raw event per TTL after processing/reconciliation.
5. Retain normalized summary for the approved support duration.

A provider `DEFERRED` event is not by itself a reason to retain the full MIME or send a new SMTP copy when the provider has already accepted and is retrying.

## 10. Production flow from sending to deletion

A complete lifecycle:

~~~mermaid
flowchart TD
    A["Create notification"] --> B["Persist outbox and payload reference"]
    B --> C["Scheduled / due"]
    C --> D["Claim and send via JavaMailSender"]
    D --> E{"Submission outcome?"}
    E -- "Temporary" --> F["RETRY_PENDING"]
    F --> C
    E -- "Accepted" --> G["SUBMITTED"]
    E -- "Permanent" --> H["FAILED_PERMANENT"]
    E -- "Uncertain" --> I["SUBMISSION_UNKNOWN"]
    I --> J["Reconcile"]
    J --> G
    J --> H
    G --> K["Terminal or completed retention trigger"]
    H --> K
    K --> L{"Hold / reference / policy check"}
    L -- "Not eligible" --> M["Keep and re-evaluate"]
    L -- "Eligible" --> N["Purge content and objects"]
    N --> O["Retain minimal metadata until its deadline"]
    O --> P["Delete or anonymize metadata"]
~~~

The key point is that **the cleanup worker does not take over the dispatcher's role**. The dispatcher decides whether to send, retry, or stop; cleanup relies on confirmed states and policy to determine which data no longer needs to be kept.

### Avoiding premature cleanup

If a `PENDING` job is scheduled in the future, cleanup cannot look only at `createdAt`. If an email is `PROCESSING` with an active lease, an attachment currently being read must not be deleted. If a job is `SUBMISSION_UNKNOWN`, all correlations must not be deleted before the reconciliation deadline.

### Avoiding overdue cleanup

If an email is `CANCELLED`, `EXPIRED`, or `SUBMITTED` and there is no obligation to keep the body, raw MIME can be purged before metadata. If an organization keeps bodies for 10 years "just in case" without a specific purpose, sensitive data and breach exposure grow without commensurate benefit.

## 11. Retention policy as data

Expressions like `plusDays(30)` should not be scattered across controllers, workers, webhook consumers, and cleanup jobs. A single policy service enforces consistency:

~~~java
package com.example.mail.retention;

import java.time.Duration;

public record RetentionRules(
        String policyVersion,
        Duration contentAfterTerminal,
        Duration metadataAfterTerminal,
        Duration unknownOutcomeReviewWindow,
        Duration rawEventAfterProcessed,
        Duration quarantineAfterDecision) {
    public RetentionRules {
        if (contentAfterTerminal.isNegative()
                || metadataAfterTerminal.isNegative()
                || unknownOutcomeReviewWindow.isNegative()
                || rawEventAfterProcessed.isNegative()
                || quarantineAfterDecision.isNegative()) {
            throw new IllegalArgumentException(
                    "Negative retention period");
        }
    }
}
~~~

This is an **application type**, not an `org.springframework.mail` API. `Duration` only represents an elapsed time span; if policy is defined by **calendar months**, use proper calendar arithmetic and timezones rather than assuming `Duration.ofDays(30)` equals a month.

### Illustrative configuration example

~~~yaml
app:
  mail:
    retention:
      policy-version: example-v1
      transactional-content-after-terminal: P7D
      transactional-metadata-after-terminal: P90D
      raw-provider-event-after-processed: P14D
      unknown-outcome-review-window: P7D
      cleanup-batch-size: 100
~~~

**The numbers in the YAML are illustrative examples only, not recommended optimal durations or legal requirements.** In a real deployment, there may be multiple policies by category, tenant, classification, and retention basis. Do not allow an environment config flag to arbitrarily delete data outside approved policy scope.

### Multi-factor retention decisions

~~~text
RetentionPolicy =
    dataset
  + business category
  + data classification
  + jurisdiction/contract if applicable
  + lifecycle state
  + retention trigger
  + legal holds / special cases
  + policy version
~~~

Record which policy was used when computing `purgeAfter`. If the policy changes, use a controlled process to evaluate existing records instead of letting each worker calculate different durations on its own.

## 12. Database schema: separating payload and metadata

A relational design can separate `mail_notification`, `mail_payload`, `mail_attempt`, and `mail_retention_hold`. PostgreSQL example:

~~~sql
CREATE TABLE mail_notification (
    id                     UUID PRIMARY KEY,
    tenant_id              VARCHAR(100) NOT NULL,
    category               VARCHAR(50) NOT NULL,
    recipient_ref          VARCHAR(200),
    status                 VARCHAR(50) NOT NULL,
    scheduled_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL,
    terminal_at            TIMESTAMPTZ,
    content_purge_after    TIMESTAMPTZ,
    metadata_purge_after   TIMESTAMPTZ,
    policy_version         VARCHAR(100),
    current_generation     BIGINT NOT NULL DEFAULT 0,
    retention_hold         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE mail_payload (
    notification_id        UUID PRIMARY KEY,
    encrypted_subject      BYTEA,
    encrypted_plain_body   BYTEA,
    encrypted_html_body    BYTEA,
    encrypted_template_data BYTEA,
    object_storage_key     VARCHAR(500),
    content_sha256         VARCHAR(64),
    payload_state          VARCHAR(50) NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_mail_payload_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id)
);

CREATE TABLE mail_attempt (
    id                     UUID PRIMARY KEY,
    notification_id        UUID NOT NULL,
    provider_key           VARCHAR(100) NOT NULL,
    attempt_number         INTEGER NOT NULL,
    status                 VARCHAR(50) NOT NULL,
    normalized_error       VARCHAR(100),
    smtp_code              VARCHAR(20),
    started_at             TIMESTAMPTZ NOT NULL,
    completed_at           TIMESTAMPTZ,
    CONSTRAINT fk_mail_attempt_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id),
    CONSTRAINT unique_attempt
        UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_retention_hold (
    id                     UUID PRIMARY KEY,
    notification_id        UUID NOT NULL,
    case_reference         VARCHAR(250) NOT NULL,
    scope                  VARCHAR(100) NOT NULL,
    hold_started_at        TIMESTAMPTZ NOT NULL,
    hold_released_at       TIMESTAMPTZ,
    approved_by            VARCHAR(150) NOT NULL,
    CONSTRAINT fk_mail_hold_notification
        FOREIGN KEY (notification_id)
        REFERENCES mail_notification(id)
);

CREATE INDEX idx_mail_content_purge
    ON mail_notification(content_purge_after)
    WHERE content_purge_after IS NOT NULL;

CREATE INDEX idx_mail_metadata_purge
    ON mail_notification(metadata_purge_after)
    WHERE metadata_purge_after IS NOT NULL;
~~~

This schema is **illustrative** and does not yet include all production indexes, tenant keys, encryption metadata, event inboxes, object references, version tracking, or deletion audits. The `retention_hold` boolean helps fast reads, but should not be the sole source of truth if the system supports multiple holds with distinct scopes. Always consult the hold table or authoritative mechanism.

### Why not store everything in a single row?

Separating payload from metadata helps:

- Delete bodies early while preserving sending status.
- Restrict plaintext read access: dispatchers read payloads, support dashboards view only metadata.
- Avoid forcing every query/report to load large blobs.
- Reduce content exposure risks when exporting CSVs for customer support.
- Apply independent lifecycle/retention to attachment objects.

Trade-off: greater complexity when purging references outside the database; requires a safely retryable cleanup protocol.

### Care with application-level encryption

The `encrypted_*` columns only illustrate the concept. Never use homegrown encryption or store keys alongside ciphertext. You need:

- AEAD or mechanisms approved by security specialists.
- Key management, rotation, and access policies.
- Tenant/context binding if using associated data.
- Never logging plaintext during render/decrypt.
- Retention policies for keys and key versions.

Encryption at rest **does not replace deletion**, because copies in caches/logs/providers may still exist in plaintext.

## 13. Computing purgeAfter at state transition time

A policy can compute deadlines when a job transitions to a terminal state, but only after completion evidence exists:

~~~java
package com.example.mail.retention;

import java.time.Duration;
import java.time.Instant;

public record RetentionDeadlines(
        Instant contentPurgeAfter,
        Instant metadataPurgeAfter,
        String policyVersion) {
}

public final class MailRetentionCalculator {

    public RetentionDeadlines afterTerminal(
            Instant terminalAt,
            RetentionRules rules) {

        if (terminalAt == null) {
            throw new IllegalArgumentException(
                    "Terminal timestamp required");
        }
        return new RetentionDeadlines(
                terminalAt.plus(rules.contentAfterTerminal()),
                terminalAt.plus(rules.metadataAfterTerminal()),
                rules.policyVersion());
    }
}
~~~

Do not call `afterTerminal()` when `status=PENDING`, `RETRY_PENDING`, or while an unknown attempt still exists. A privacy deletion request may also carry a **different deadline**; resolve it based on valid grounds and exceptions rather than relying solely on post-terminal periods.

### Keeping metadata longer than content?

This is appropriate if support, reconciliation, dispute, or audit purposes genuinely require it. Without a clear purpose, do not arbitrarily choose long metadata retention merely because storage size is small.

### Do not use `createdAt` in place of `terminalAt`

A message may be created long before being sent, or retried over several days. Cleanup needs to know when processing finished, rather than guessing from enqueue date.

## 14. Conditional content deletion in the database

Before purging, the worker must verify:

1. `content_purge_after <= now`.
2. The job is already in an eligible terminal state.
3. No active attempt or lease exists.
4. No unreconciled `SUBMISSION_UNKNOWN` exists.
5. No legal hold applies to the content.
6. No data/references are still used by other jobs.
7. The worker holds valid cleanup authority with transaction/fencing protection.

A PostgreSQL candidate selection query:

~~~sql
SELECT n.id
FROM mail_notification AS n
WHERE n.content_purge_after <= CURRENT_TIMESTAMP
  AND n.status IN (
      'SUBMITTED', 'FAILED_PERMANENT',
      'CANCELLED', 'EXPIRED', 'SUPPRESSED'
  )
  AND n.retention_hold = FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM mail_retention_hold AS h
      WHERE h.notification_id = n.id
        AND h.hold_released_at IS NULL
        AND h.scope IN ('CONTENT', 'ALL')
  )
ORDER BY n.content_purge_after
LIMIT 100
FOR UPDATE OF n SKIP LOCKED;
~~~

`FOR UPDATE SKIP LOCKED` prevents multiple cleanup workers from selecting the same row **within a transaction**, but it does not automatically handle object storage and does not replace active-reference checks. The terminal status list is illustrative only; `DEAD_LETTER` and `SUBMISSION_UNKNOWN` require separate policies. To guarantee data currently used by a send worker is not deleted, state transition/claim transactions must synchronize on the exact same row/version that cleanup checks.

### Critical transaction boundary

Do not keep a database transaction open while deleting 10 GB of attachments over the network. Instead:

1. Inside a short transaction, claim and record `PURGE_PENDING` or create a deletion work item.
2. Commit.
3. Delete external objects idempotently with retries.
4. Record results and clear payload references in a separate transaction.
5. Set `CONTENT_PURGED` only when all mandatory components have been processed or confirmed with evidence.

If object deletion succeeds but the DB update fails, retrying deletion must be safe. If the DB cleared references before the object was deleted, the data becomes a hard-to-trace **orphan object**; persist a deletion manifest and control ordering.

## 15. Deletion manifest and two-phase protocol

Because the database and object store do not share an ACID transaction, a **deletion manifest** can be used:

~~~text
mail_deletion_task
  id
  notificationId
  tenantId
  payloadObjectKeys[]
  requestedAt
  policyVersion
  status = READY / IN_PROGRESS / RETRY / COMPLETED / FAILED
  attemptCount
  nextAttemptAt
  lastErrorCategory
  completedAt
~~~

Flow:

~~~mermaid
flowchart TD
    A["Retention worker evaluates eligibility"] --> B["DB transaction: snapshot refs + claim deletion"]
    B --> C["Deletion task durable"]
    C --> D["Delete external objects idempotently"]
    D --> E{"All objects removed?"}
    E -- "No" --> F["Retry with backoff / alert"]
    F --> D
    E -- "Yes" --> G["DB transaction: clear content rows and refs"]
    G --> H["Mark task completed + evidence"]
~~~

### Why snapshot object keys before deleting rows?

If the `mail_payload` row is deleted first, the cleanup worker no longer knows which keys hold the raw MIME/attachments. A durable manifest enables safe retry after a restart without recovering deleted rows.

### Handling "object not found"

In an idempotent deletion workflow, `NotFound` may be treated as **the object no longer exists at that key/version**, provided you verify the request targeted the application-owned object rather than a wrong key/tenant. Do not treat every HTTP error as success: `AccessDenied`, network timeouts, or KMS errors require retry/alerting.

### Delete only owned objects

Never take a key from user payloads and issue arbitrary delete calls. Verify tenant, bucket/prefix, version, and resource ownership before purging. For objects shared across multiple notifications, maintain reliable reference counting or an ownership model so an attachment still referenced by another job is not deleted.

## 16. Batch Spring cleanup worker

Spring can use `@Scheduled` to trigger periodic cleanup, but the annotation itself **does not decide which records may be deleted**. The worker must query policy, claim a batch, and execute deletion safely.

~~~java
package com.example.mail.retention;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailRetentionPoller {

    private final MailDeletionService deletionService;

    public MailRetentionPoller(
            MailDeletionService deletionService) {
        this.deletionService = deletionService;
    }

    @Scheduled(fixedDelayString = "PT1M")
    public void scheduleDuePurges() {
        deletionService.scheduleDueBatch(100);
    }
}
~~~

`MailDeletionService` is application-implemented. Depending on the Spring version, use an appropriate duration string or dedicated configuration property; enable scheduling with `@EnableScheduling` in application configuration if not already enabled.

### Responsibility boundary

`scheduleDueBatch(100)` should stay short:

1. Check retention policy and legal holds.
2. Claim up to 100 records in a DB transaction.
3. Persist durable deletion tasks.
4. Commit and finish the poll.

One or more deletion executors process object stores outside the transaction. Do not let a single external-object deletion loop run for hours on the sole scheduler thread.

### Orchestration pseudocode

~~~java
package com.example.mail.retention;

import java.util.List;

public final class MailDeletionService {

    private final MailRetentionRepository repository;

    public MailDeletionService(MailRetentionRepository repository) {
        this.repository = repository;
    }

    public void scheduleDueBatch(int maxItems) {
        // Repository method runs a short transaction:
        // claim eligible rows, recheck hold/lease, write manifest.
        List<String> taskIds =
                repository.createDeletionTasks(maxItems);

        // Do not call object-store network delete here.
        // Independent executors will process the persisted tasks.
        if (taskIds.isEmpty()) {
            return;
        }
    }
}
~~~

`MailRetentionRepository` is an application interface, not a built-in Spring Data repository. The code uses `String` task IDs for illustration; production should use typed IDs, outcome states, and metric/error handling.

### Bounding configuration

A cleanup worker also needs:

- Bounded batch size.
- Deletion requests per second aligned with the object storage contract.
- Retry budget and backoff with jitter.
- Timeouts for network operations.
- Max concurrent deletions.
- Alerts when purge backlog grows.
- Idempotent deletes and manifest deduplication.
- Least-privilege permissions scoped solely to deleting mail-retention objects.

**Do not grant full-bucket admin permissions** if the worker only needs to delete one namespace and permitted object versions.

## 17. Send workers and deletion workers must coordinate through state

Suppose an email is scheduled for 09:00, and cleanup sees the payload's `content_purge_after` column is due under an older TTL calculation. If cleanup does not check status/lease, it could delete the body right as the mail worker opens the attachment stream.

### Required invariant

~~~text
Cannot purge content while:
  notification is dispatchable
  or active submission attempt exists
  or unknown submission outcome requires content
  or a retention hold applies
  or another live job references the same object
~~~

One way to synchronize is via **state transitions and row versions** in the database:

- The send worker claims `PENDING -> PROCESSING` in a transaction.
- The cleanup worker claims `terminal -> PURGE_PENDING` in a transaction.
- Both verify status/generation.
- Only one valid transition wins; the losing transaction must not proceed on a stale snapshot.

### Never check status once and then delete

~~~text
T0 cleanup reads status=SUBMITTED
T1 an operator authorized reopens/replays notification
T2 cleanup deletes payload based on T0 snapshot
~~~

If replay is a valid use case, it must go through a state/ownership transaction, such as creating a **new** notification or blocking reopening during `PURGE_PENDING`. Never let operators mutate status directly outside the state machine.

### Do not lock the database while calling SMTP or object storage

Database transactions cannot guarantee rollback of a submitted email or recovery of a deleted object. Use durable jobs/manifests and idempotent steps; never hold row locks across network calls.

## 18. Deletion order for content and metadata

If metadata is deleted before content, orphan objects can be created. A common order is:

1. Decide on deletion and snapshot object references.
2. Mark the payload as no longer available to dispatchers/support (logical retirement).
3. Delete external objects at specific versions.
4. Confirm external deletion or record results/exceptions.
5. Delete content columns or rows.
6. Keep minimal metadata until its separate deadline.
7. Afterward, delete/anonymize metadata and dependent relationships.

### Logical retirement

While deletion is in progress, APIs should no longer serve the body. A `payload_state=PURGE_PENDING` flag blocks new access; if the deletion task fails, operators can retry safely without "resurrecting" content for the sending pipeline.

### Relationship to auditing

An audit record stating that a deletion task completed does not need to store the deleted raw content. You can record:

~~~json
{
  "event": "mail_content_purged",
  "notificationKey": "notif-184",
  "policyVersion": "example-v1",
  "reason": "RETENTION_EXPIRED",
  "completedAt": "2027-01-20T00:00:00Z",
  "objectsDeleted": 2
}
~~~

However, audit `notificationKey` can still link to a user, so **audit logs also need retention** and access controls. Do not keep identifiable email bodies/hashes as unnecessary "deletion proof."

## 19. Hard delete, soft delete, and anonymization

Each method serves a different goal:

| Method | Data still exists? | When to use |
| --- | --- | --- |
| Soft delete | Yes; only changes status/hides in UI | Need an undo window, not final deletion |
| Hard delete | Row/object is actually removed from active storage | Purpose/retention ended, no holds |
| Pseudonymize | Can be re-linked with a key/other source | Need risk reduction in analytics |
| Anonymize | No longer reasonably identifiable in context | Used for aggregate stats not needing individuals |
| Aggregate | Keeps totals/rates instead of records | Long-term performance dashboards |
| Cryptographic erasure | Destroying key renders ciphertext undecryptable | Supporting tool dependent on architecture/key isolation |

Soft delete is **not** final data deletion. If a user requests deletion under a valid process, merely setting `deleted=true` in a table is insufficient if raw content remains readable via admin queries or backups.

### Do not hard delete while a valid retention duty remains

For records under legal hold or storage obligations, you may need to restrict access, forbid use outside purpose, and defer deletion for the covered portion. Specify **which fields, which records, and on what basis**—do not place an indefinite tenant-wide hold flag out of implementation convenience.

### Anonymization requires explicit design

Deleting the email address while keeping `customerId`, `orderId`, a template naming a hospital, or an identifying idempotency key can still make the data re-identifiable. Review all **linking keys** and auxiliary data.

## 20. Cryptographic erasure: useful, not magic

One model uses dedicated keys per tenant or dataset to encrypt payloads. When a key is destroyed via procedure, remaining ciphertext may become undecryptable:

~~~text
Per-tenant / per-data-group encryption key
               |
               v
Encrypted mail body and attachment objects
               |
               v
Key lifecycle: active -> rotated -> eligible for destruction
~~~

Watch out for caveats:

- If a single key covers both data to keep and data to delete, destroying the key destroys valid data as well.
- If plaintext already appeared in logs, caches, exports, or provider storage, destroying the database key does not address those copies.
- KMS systems have specific backup/recovery/key-rotation semantics; verify what "destroyed" actually means in the provider.
- Copies of the key may exist outside control or remain cached.
- Do not assume every crypto-shredding approach satisfies all legal deletion requirements.

**Cryptographic erasure is a supporting retention tool** that must work alongside physical deletion, key-scope management, and auditing.

## 21. Attachment object lifecycle and versioning

Attachments typically reside in S3-compatible storage, Azure Blob, GCS, or an internal object store. Services differ in **object versioning, replication, lifecycle, and delete markers**.

### When the object store enables versioning

A `DELETE objectKey` operation may only create a delete marker or hide the latest version; older object versions still exist. If the goal is genuine retention deletion, understand:

- How many versions exist?
- Are there object lock/retention policies blocking deletion?
- Is there cross-region replication?
- Should specific versions or all version sets be deleted?
- How does lifecycle expiration apply to current vs. noncurrent versions?
- Is there an inventory proving the object is no longer available?

Do not write a cleanup method that deletes only the current key and reports "all copies removed" if versioning/replication still holds the content.

### Shared references

An invoice file may be referenced by multiple notifications:

~~~text
invoice-object-v3
   |--> reminder-email-1
   |--> receipt-email-2
   |--> resend-request-3
~~~

Do not delete the object when the first notification reaches its TTL if the other two notifications still need it. You can:

- Store the object owned by the **business document** and lend mail only a reference.
- Use reference tracking for live references.
- Create immutable delivery copies with independent lifecycles when needed.

In particular, if the object actually belongs to the enterprise document system, the mail retention worker should not have permission to delete the **original business document**; delete only copies owned by the mail pipeline.

### Object keys should not reveal PII

Avoid keys like `attachments/user-email@example.org/invoice.pdf`. Use identifiers free of sensitive information, authorize by tenant/resource, and store the original filename as metadata with an appropriate TTL.

## 22. Raw MIME and troubleshooting captures

Raw MIME is helpful when debugging encoding, header, DKIM, or attachment errors, yet it is one of the heaviest forms of stored data.

### Questions before storing raw MIME

1. Is raw MIME genuinely needed for every email, or only an incident subset?
2. Can you store only a MIME hash, renderer version, and sanitized SMTP response?
3. Does raw MIME contain tokens/secrets or sensitive documents?
4. Who is permitted to view it, and is viewing audited?
5. Are there clear size limits and retention deadlines?
6. Can debug captures be deleted prior to TTL upon request?

One approach is enabling **time-bounded diagnostic capture** only for an approved incident, rather than dumping all emails into the filesystem or tracing by default.

### Content inside exceptions

`MailException` or nested Jakarta Mail exceptions may contain recipient addresses and SMTP replies. Do not log full exception objects to broadly accessible places, nor place subjects/bodies into custom application exception messages. Use normalized failure categories, SMTP codes, phases, and correlation IDs.

### Raw MIME is not necessarily the exact sent copy

If the application builds MIME with `MimeMessageHelper` or serializes `MimeMessage.writeTo(...)`, the bytes may differ from what a provider actually captures after adding headers, DKIM, and transport modifications. Do not claim to hold an "exact original copy" if you only keep the pre-submission render.

## 23. Template data and rendered content have different lifecycles

A system might skip storing rendered HTML and retain only:

~~~json
{
  "templateKey": "invoice-notice",
  "templateVersion": "v3",
  "model": {
    "invoiceId": "inv-184",
    "customerName": "Example User"
  }
}
~~~

Yet `model` still contains personal data. Deleting `htmlBody` while leaving `templateModel` intact does not meaningfully reduce stored personal data. Conversely, if only an `invoiceId` reference is kept, the worker still needs authorized access to the right version of business data at send time.

### A useful layering

- **Template definition:** shared template source code; retained on software lifecycle, not deleted when one message expires.
- **Template version reference:** message metadata; usually kept sufficiently for audit.
- **Template model snapshot:** recipient-specific data; content retention.
- **Rendered HTML/plain text:** content retention.
- **Original business record:** separate lifecycle of the order/invoice system.

Never let the mail cleanup worker delete the original business record just because the email holds an ID referencing that record.

## 24. Dead-letter queues are a data store requiring retention

An undeliverable job may be routed to a DLQ for investigation and replay. If the serialized event contains body or attachment URLs, the DLQ becomes a **sensitive copy**.

### Risks

- DLQ retained indefinitely because there is no consumer.
- Payloads containing expired OTPs/reset links.
- Support staff having permissions to download full messages.
- Replaying stale items resending invalid emails.
- DLQ exported to another bucket without a TTL.

### Recommended policies

1. TTL, quota, and owner per DLQ/topic.
2. Store only minimal payloads or references to retention-controlled objects.
3. When the raw body is purged, invalidate or delete related DLQ copies.
4. Replay must revalidate consent, recipient, token expiry, and provider policy.
5. Audit when operators replay or purge items.
6. Never resend `SUBMITTED` or `SUBMISSION_UNKNOWN` mail merely because it sits in a DLQ.

### Use event references instead of duplicating bodies

Instead of placing full MIME into the queue:

~~~json
{
  "notificationId": "notif-184",
  "attemptId": "attempt-2",
  "eventType": "RETRY_READY"
}
~~~

Workers retrieve payloads from authorized storage only when actually sending. After content is purged, stale events must be ignored or transitioned per policy; never reconstruct bodies from a queue backup.

## 25. Logs, traces, and metrics are also time-bounded data

Logs often arise outside mail tables:

~~~text
2026-11-12 ERROR send failed to alice@example.org
subject="Your verification code is 123456"
SMTP reply: ...
~~~

Even when the message body is deleted from the outbox, a log line like this still exposes the address and OTP. Therefore, retention design must cover **log pipelines, APM, distributed tracing, error monitoring, exports, support bundles, and local container files**.

### Better structured log pattern

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "att-2",
  "provider": "smtp-primary",
  "failureKind": "SMTP_AUTH",
  "smtpPhase": "AUTH",
  "smtpCode": "535",
  "retryable": false
}
~~~

`notificationId` can still re-link to a recipient internally and requires ACL/TTL. Do not put body, subject, raw recipient, reset URL, or SMTP AUTH transcripts into logs.

### Retention across systems

| Location | Retention to control |
| --- | --- |
| Application stdout/stderr | Container log rotation and log agent |
| Centralized logs | Index lifecycle, hot/warm/archive, deletion |
| Distributed tracing | Trace retention and attribute sanitization |
| Error tracking | Stored exceptions, breadcrumbs, request payloads |
| APM profiling | Heap dumps, stack traces, sampled transactions |
| Metrics | Label data and retention in monitoring backend |
| Support exports | CSV/ZIP files, shared links, expiration |
| Local temp files | MIME caches, debug dumps, crash artifacts |

For metrics, use bounded labels such as `provider`, `category`, `failureKind`, `region`. Avoid recipient, subject, notification UUID, or idempotency key as Prometheus labels, as they both leak data and cause high cardinality.

### Log TTL does not replace redaction

A log containing an OTP retained for 1 day can still be accessed without authorization during that day. **Minimizing data at the write point** is always more important than relying solely on TTL.

## 26. Provider-side retention and data processing agreements

When Spring Mail submits via an SMTP relay, the message leaves the application's direct control. The relay/provider may retain:

- Message queues before and during delivery.
- Bodies/attachments in internal retry mechanisms.
- Delivery events, SMTP logs, or bounce records.
- Diagnostic copies or backups.
- Tracking, unsubscribe, and complaint data per enabled features.

Consequently, **deleting data in the application does not mean the provider has deleted all copies**.

### Questions to clarify with the provider

1. Does the provider store full message bodies after acceptance? Under what circumstances?
2. What are the queue/retry durations and body retention periods?
3. Can message archiving or event data capture be toggled on/off?
4. Do delivery events/webhooks contain full recipients or payloads?
5. Is there an API to delete message data, recipient profiles, or event history?
6. Upon a deletion request, how does the provider handle backups and replicated data?
7. Are there independent retention obligations or contractual exceptions?
8. What is the region/data residency for mail storage and diagnostic data?
9. When switching providers, how is legacy data handled?
10. Does the provider furnish deletion proof or public retention policies?

Do not assume every provider exposes an API to delete an SMTP-accepted email. SMTP offers no universal mechanism to recall or delete a message already delivered to a recipient's mailbox. Deletion requests may need to distinguish **data within your account/provider** from **message copies inside recipient mailboxes beyond your control**.

### Limiting provider event collection

If you only need to know `DELIVERED` or `BOUNCED`, storing full webhook requests for years is unnecessary. You can:

- Verify and deduplicate events upon receipt.
- Normalize into event type, reason, and timestamp.
- Write the state projection.
- Delete raw events on a short retention period.

If provider webhooks carry raw SMTP headers or recipient addresses, treat them as protected data rather than "harmless technical events."

### Do not enable archive features without a purpose

A provider may offer message activity search or full-content archiving. While useful for investigations, it expands where copies reside. Enable it only with a clear use case, policy, access controls, and corresponding deletion workflow.

## 27. Suppression lists: minimal retention without erroneous resends

Someone unsubscribes from marketing emails or files a complaint. Deleting all traces immediately may cause the system to forget that choice and **resume sending unwanted messages**.

### Distinguishing suppression categories

| Reason | Applicable scope | Data to retain |
| --- | --- | --- |
| Unsubscribe marketing | A category/list/tenant per user choice | Minimal identifier and opt-out flag |
| Complaint | May block marketing or broader scope per policy | Reason, event source, timestamp |
| Hard bounce | Recipient/mailbox undeliverable per evidence | Normalized address/identity and status |
| Administrative block | Per internal policy | Owner, reason, decision version |
| Temporary bounce | Not necessarily permanent suppression | Temporary status, expiry, and retry logic |

Do not apply a single boolean `blocked` across all email types without scope distinction: newsletter unsubscribes differ from mandatory security emails. Still, for a mailbox confirmed non-existent, retrying OTPs to it is futile as well.

### Privacy and suppression can coexist

A design can minimize information down to:

~~~text
tenantKey
normalizedRecipientIdentity / controlled pseudonym
categoryScope
suppressionReason
effectiveAt
policyVersion
~~~

There is no need to retain the raw email body that triggered a complaint. If suppression uses an email HMAC, remember:

- HMAC can support matching to avoid resending.
- Keeping the key enables linkage and may still qualify as personal data depending on context.
- Read/compute access control, key rotation, and domain normalization are required.
- Never treat an unkeyed raw hash as a guarantee of anonymization.

Suppression retention decisions should be driven by send-prevention purpose, user choice, and applicable requirements—not copied from outbox body TTLs.

## 28. Consent and preference data differ from message history

A system may want to know "is this person permitted to receive marketing?" without keeping a history of every email ever sent.

Separate the models:

~~~text
mail_preference
  recipientKey
  tenant
  category
  allowed / optedOut
  source / timestamp

mail_notification
  notificationId
  recipientRef
  category
  status
  scheduledAt

mail_payload
  notificationId
  encrypted subject/body
~~~

When a notification reaches retention expiration, the preference record does not necessarily get deleted at the same time: it has its own purpose and basis. Conversely, you should not keep the full list of sent emails merely to prove current preferences.

### Consent auditing

When proof of consent/opt-out is required, retain minimal events or evidence per policy. Avoid copying raw marketing HTML or tracking pixels into every consent event. If collected via a form, track the accepted content version and timestamp rather than storing an uncontextualized boolean.

## 29. Data deletion requests: controlled execution

A privacy deletion request should not result in an immediate SQL command wiping everything without checking scope and retention bases.

Typical steps:

1. Authenticate the requester and authority over the data.
2. Identify relevant data subject/tenant/recipient identities.
3. Enumerate where data resides: outbox, payloads, attempts, provider events, logs, object storage, suppression, backups, exports.
4. Identify retention obligations/grounds or properly scoped legal holds.
5. Halt processing or restrict access as needed during handling.
6. Schedule idempotent deletion/anonymization tasks.
7. Coordinate with external providers/processors where rights and obligations require.
8. Record outcomes per dataset and exceptions.
9. Handle deferred/failed tasks, retries, and reporting.
10. Retain completion evidence **without re-including the deleted data**.

### Do not delete information needed to fulfill the request

A minimal record of the deletion request may be needed: request ID, action status, dataset completed/exception reason, and timestamp. However, this record must also have access controls and a TTL; do not keep a full copy of raw emails as "deletion proof."

### Handling pending content

If a deletion request renders the recipient ineligible to receive mail, `PENDING/RETRY_PENDING` jobs may need to become **CANCELLED/SUPPRESSED** before purging payloads. If a job is `PROCESSING`, handle races with the worker; do not simply delete the body out from under a running worker and report completion.

### Do not claim deletion inside recipient mailboxes

The application can delete its own copies and forward requests to the provider if features/contracts allow. It generally cannot delete an email that has already reached a mailbox outside its management boundary. Responses to requesters must distinguish actual deletion scope from those limitations.

## 30. Legal holds and retention exceptions

A dispute or preservation obligation may require temporarily suspending deletion for a subset of data.

### Designing scoped holds

~~~text
caseId: dispute-184
scope: EMAIL_METADATA
dataset: mail_attempt
subject: notification group X
start: 2026-11-12
owner: approved compliance role
status: ACTIVE
~~~

Do not default to holding "all emails across all tenants" when only one transaction record is required.

### Workflow

1. Only authorized roles may create/release holds.
2. Record case ID, purpose, scope, creation date, and approver.
3. Cleanup workers read holds **at deletion claim time**.
4. Apply holds per dataset: metadata may be held while unrelated raw bodies can still be deleted.
5. When a hold is released, recompute eligibility and run cleanup.
6. Audit hold creation/release and access to held data.

A `retention_hold=true` field can act as a query-optimization cache, but an **authoritative source of truth** carrying scope and rationale is needed. Releasing a hold does not automatically mean every record must be deleted immediately; still evaluate original retention and any other active holds.

### Legal holds are not a reason to broaden access

Held data still requires encryption, role-based access, auditing, and use restrictions. Retaining records for a dispute does not permit marketing teams to view or reuse the content.

## 31. Data deletion workflows and concurrency handling

A deletion request, scheduled cleanup, and SMTP worker may touch the same notification concurrently:

~~~text
T0  user requests erasure
T1  application marks recipient/job as no longer eligible
T2  cleanup claims payload deletion
T3  mail dispatcher sees stale PENDING snapshot
T4  dispatcher attempts to read payload
~~~

**If consent is checked only when creating the send request**, workers could continue sending after the user withdrew permission. You need:

- Permission/status revalidation immediately prior to dispatch.
- Atomic status transitions on cancel/purge.
- Fencing/generation checks so stale workers cannot write state from an old snapshot.
- Distinguishing SMTP-accepted jobs (cannot be reliably recalled) from unsent jobs.
- Preventing replay/restore from reviving a purged request.

### A useful state

`ERASURE_PENDING` can block new payload access while cleanup tracks components. If a legal hold exists, a job can enter `ERASURE_PARTIAL` with datasets deferred for valid reasons. This state model must be explicitly documented and not obscure remaining obligations.

## 32. Backups: keeping deleted data is not a successful recovery

Database/object backups help recover systems after outages, yet they can also hold raw emails, attachments, and suppression records.

A retention policy must specify:

- How long backups are kept.
- Whether immutable snapshots/object versions exist.
- When snapshots automatically expire by lifecycle.
- Who has restore/export privileges.
- Whether deletion can occur inside backups or must wait for controlled expiration.
- Whether restores can reintroduce previously deleted data.
- Whether evidence exists that backups expired/were securely retired.

### Restore and "resurrection"

~~~text
Day 1: Notification N is created
Day 5: Body of N is deleted under retention
Day 6: Backup from Day 2 is restored
Risk: N's body reappears in active database
~~~

Therefore, after restoring, you must **replay deletion journals/tombstones** and any suppression/cancel/erasure transitions newer than the snapshot before opening mail workers or granting support access to restored data.

### Restore-safe workflow pattern

1. Restore into an isolated environment with restricted permissions.
2. Block SMTP dispatch, analytics exports, and user-facing access initially.
3. Load the deletion journal and current policy.
4. Reapply necessary deletion/anonymization/cancellation records.
5. Reconcile active legal holds and access controls.
6. Verify purged data cannot be reopened.
7. Only then put the workload back into service.

If the deletion journal itself is rolled back alongside the snapshot, the workflow cannot distinguish data that should be deleted. Thus you need **a sufficiently durable/independent store of deletion decisions** within an approved security boundary.

## 33. Deletion tombstones and journals

A tombstone helps ensure deleted records are not re-imported, restored, or replayed back into active service.

~~~json
{
  "resourceKey": "notif-184",
  "action": "ERASE_CONTENT",
  "policyVersion": "example-v1",
  "decisionAt": "2026-11-12T10:00:00Z",
  "completedAt": "2026-11-12T10:05:00Z"
}
~~~

**Note:** tombstones can also be personal data if `resourceKey` links to a user. Clear TTLs, permissions, key management, and purpose are required; do not turn a deletion ledger into an indefinitely retained identity store. Systems can store non-trivially reversible deletion action identifiers or minimal records matching audit obligations.

### Scenarios requiring replay

- Restoring an older database snapshot.
- Recovering object versions/replication.
- Queue messages redelivered.
- Importing an old DLQ.
- Rehydrating caches.
- Recovering analytics pipelines or data lakes.

Never let `mailSender.send()` run against a restored record without verifying it was not cancelled/deleted/expired by newer events.

## 34. Caches, temp files, and in-memory copies

Some data lives outside the primary database and still requires control:

- Redis caches storing rendered HTML, recipients, or template models.
- Local `/tmp` MIME/attachment files.
- Thumbnails/previews.
- In-memory queues or long-running workers.
- HTTP request/response recordings.
- Retry serialization inside brokers.
- Heap dumps and crash reports.

### Redis TTL

Set TTLs appropriate to purpose, but do not treat Redis eviction as absolute secure deletion across all persistence/replication setups. If Redis uses RDB/AOF/backups, data can persist in snapshots; evaluate the full cache lifecycle.

### Local disk

If rendering attachments to temp files, use restricted directories, filenames free of PII, `finally` cleanup where appropriate, and a sweeper for orphaned files after crashes. Container restarts do not always guarantee wiping data on persistent volumes.

### Memory and heap dumps

Plaintext tokens in the heap can be written into diagnostic dumps. Restrict who can trigger/download heap dumps, configure retention, and avoid holding sensitive objects in caches long-term. Clearing the database cannot sanitize previously exported heap dumps.

## 35. Dataset-based deletion rather than all-or-nothing deletion

When a notification's retention expires, the system does not necessarily delete every component on the same day. You can model separate datasets:

~~~text
MAIL_CONTENT
  subject/body/template model
  raw MIME and preview
  content object references

MAIL_ATTACHMENT
  message-specific immutable objects
  scan result and temporary copies

MAIL_OPERATIONAL
  SMTP attempts / normalized errors
  provider message IDs
  notification state

MAIL_SECURITY
  suppression / opt-out
  abuse complaint indicator

MAIL_AUDIT
  allowed audit events
  legal holds and deletion evidence
~~~

Datasets carry separate retention/owners, and the deletion engine evaluates **per-part** eligibility. When a user requests content deletion while minimal suppression must be kept, the system can purge body/raw MIME while retaining only the opt-out marker on applicable grounds.

### Do not let dataset policies "leak" into business tables

For example, `invoiceId` appears in both email and accounting systems. Deciding to purge `MAIL_CONTENT` **must not delete the official invoice**. Reference data must clearly state ownership and when the mail pipeline merely borrows an immutable object from another system.

## 36. Versioned policies and controlled migrations

Suppose metadata retention was initially long, and policy is later shortened. Older records hold `metadata_purge_after` computed under the old policy.

Questions:

- Does the new rule apply retroactively or only to new data?
- Are active legal holds affected?
- Should large volumes of older records be deleted immediately or batched to protect database stability?
- Do downstream analytics/exports depend on data about to be deleted?
- Were decision reports and approvals recorded prior to the change?

### Rollout approach

1. Place the new policy version under controlled configuration.
2. Dry-run how many records change deadlines per dataset.
3. Assess legal holds, active jobs, support, and backup implications.
4. Recompute deadlines via a separate idempotent migration.
5. Run cleanup with rate limits and batch sizes.
6. Observe backlog, storage cost, failures, and deletion audits.
7. Verify remaining/removed record counts post-rollout.

Do not run a single SQL `DELETE` across hundreds of millions of rows during peak hours, as it can lock tables, cause replication lag, or fill transaction logs. At large scale, choose chunked deletes, suitable partition drops, and explicit index/storage vacuum strategies.

## 37. Partitions and large datasets

At very high email volumes, `mail_attempt` or `provider_event` may hold millions of records daily. Row-by-row deletion can be resource-intensive.

### Time partitioning

For instance, an event table partitioned monthly:

~~~text
mail_provider_event_2026_09
mail_provider_event_2026_10
mail_provider_event_2026_11
~~~

When a partition is **completely** expired and contains no legal holds or records requiring retention, it can be dropped/detached per runbook to reduce cleanup cost. However, if individual records have differing TTLs or extended holds, a partition may **not be droppable as a whole**.

### Partition keys must align with retention triggers

If retention is based on `processedAt` while partitioning uses `receivedAt`, an event received in September and processed in November may need retention beyond October. Do not drop a partition merely because receipt dates are old. Partition design and retention policy must be aligned from the outset.

### Running off-peak

Data cleanup must not cause email-sending outages. Configure:

- Batch size.
- Lock wait timeout.
- Rate limits for DELETE/object operations.
- Resource isolation between cleanup and SMTP dispatch.
- Monitoring of DB replication lag, storage I/O, and query latency.

If cleanup causes impact, throttle or pause it **in a controlled way**, log backlog/deletion SLA breaches, and resolve the root cause. Never "disable cleanup permanently" without addressing retention obligations.

## 38. Access control while data is retained

Retention asks **how long to keep data**, which must go hand-in-hand with **who can read it during retention**.

| Role | Access considerations |
| --- | --- |
| Mail dispatcher | Read payload of jobs authorized to send |
| Template renderer | Read only model needed to render, not full history |
| Support agent | View sanitized status/reason; body only with permission/purpose |
| Security responder | View diagnostic data per case/audit |
| Analytics pipeline | Read aggregated or de-identified data |
| Retention worker | Delete approved objects/rows; does not need SMTP credentials |
| Provider webhook consumer | Write events/statuses; does not need raw content read access |
| Admin | Privileged access with auditing and time-bound grants |

### A practical baseline

- Encryption at rest and TLS in transit.
- Row/tenant authorization at API and database layers where appropriate.
- Separate secrets across sender, cleanup, and provider event workers.
- Never store plaintext bodies in logs or tracing.
- Raw MIME access requires specific roles and auditing.
- Stricter permissions on quarantined content than normal mail.
- Object storage access using short-lived scoped credentials where possible.

**Encryption and ACLs do not replace timely deletion**. They reduce risk during the period when data must still be retained.

## 39. Proving deletion completed

It is not enough for a cleanup method to log "success." You need to know:

- Database rows/columns were actually deleted or anonymized.
- External object versions were handled per policy.
- Whether copies remain in queues/DLQs/caches.
- Whether provider deletion requests were accepted/confirmed, if applicable.
- Under which lifecycle backup snapshots have expired or will expire.
- Whether legal holds deferred any portion.
- Deletion audit records were saved without recreating sensitive information.

### An outcome model

~~~java
public enum DeletionOutcome {
    COMPLETED,
    PARTIALLY_COMPLETED,
    DEFERRED_BY_HOLD,
    RETRY_PENDING,
    FAILED_REQUIRES_REVIEW
}

public record DeletionProgress(
        String deletionTaskId,
        DeletionOutcome outcome,
        int objectCount,
        int completedObjectCount,
        String lastFailureCategory) {
}
~~~

A DB delete that succeeds while the object store returns access denied must be **PARTIALLY_COMPLETED** or **RETRY_PENDING**, never marked completed. The same applies when a provider has not confirmed deletion within the required contractual scope.

### Minimal evidence

Do not generate a deletion report re-including full recipients, subjects, bodies, and attachments. Usually only task ID, dataset, operation type, timestamp, policy version, object count, and status are needed; fields capable of linking to individuals still require TTLs/ACLs.

## 40. Monitoring retention and deletion

Retention is background work needing clear SLOs/alerts, not something running silently for months.

| Suggested metric | Meaning |
| --- | --- |
| `mail_retention_candidates_total` | Records eligible under policy |
| `mail_retention_due_objects` | Items past deadline not yet deleted |
| `mail_retention_oldest_overdue_seconds` | Age of oldest overdue item |
| `mail_content_purged_total` | Content payloads successfully purged |
| `mail_metadata_purged_total` | Metadata rows deleted/anonymized |
| `mail_deletion_tasks_total` | Tasks created/completed/failed by status |
| `mail_deletion_retry_total` | Deletion retries due to network/permission |
| `mail_deletion_failures_total` | Failures by storage/dataset/category |
| `mail_retention_hold_active` | Currently active holds |
| `mail_retention_hold_deferred_total` | Tasks not deleted due to holds |
| `mail_retention_bytes_deleted_total` | Verified storage bytes removed |
| `mail_orphan_objects_detected` | Objects without valid references |
| `mail_deletion_manifest_pending` | Incomplete deletion manifests |
| `mail_restore_redeletion_pending` | Records needing re-deletion after restore |
| `mail_retention_policy_version` | Active policy version if representable via bounded labels |

These metric names are **custom application examples** to implement with Micrometer/Actuator or your monitoring platform; Spring Mail does not emit them.

### Avoiding cardinality and PII

Choose labels like `dataset`, `storageType`, `policyVersion`, `outcome`, `failureCategory`. Never use raw recipient email, notification UUID, object key, or case ID as Prometheus labels.

### Actionable alerts

| Alert | Potential consequence | Response direction |
| --- | --- | --- |
| Overdue content climbing steadily | Cleanup worker stopped or query wrong | Check scheduler, DB locks, and eligibility |
| Object deletions failing | AccessDenied, KMS, versioning, network | Check permissions and deletion manifests |
| Metadata deleted while object remains | Orphan/leak | Reconcile object storage and manifests |
| Retention holds growing without drop | Holds not reviewed/released | Audit owners/cases |
| Raw provider events past TTL | Event cleanup not running | Check event inbox and projections |
| Payload of PENDING job deleted | Severe bug | Isolate cleanup, protect dispatch |
| Deleted data reappears post-restore | Missing tombstone replay | Isolate restored workload, reapply deletions |
| Quarantine exceeds capacity | Scanner/retention broken or spam wave | Protect storage, inspect scanner |

Do not measure only "how much was deleted." You need to know **how much remains overdue**, because a cleanup job succeeding on 100 objects per day falls far behind 10,000 objects expiring daily.

## 41. Runbook: cleanup is slow or stalled

If `mail_retention_oldest_overdue_seconds` rises:

1. Check whether the scheduler is running and inspect normalized log categories.
2. Check batch queries, indexes, and DB locks.
3. Inspect whether deletion manifests are in READY, RETRY, or FAILED.
4. Separate records under legal hold from genuinely overdue records.
5. Check object store API quotas, permissions, versioning, and replication.
6. Check backup/lifecycle rules or data exports outside the primary system.
7. Measure expiration rate versus purge throughput.
8. Increase concurrency/batch size carefully without impacting mail dispatchers.
9. Verify state/lease and tenant scope before replaying a cleanup task.
10. Document the incident, scope of overdue retained data, and time of resolution.

### Never fix with unconditional bulk deletes

A `DELETE WHERE created_at < ...` query ignoring state and holds can wipe unsent emails, records under reconciliation, or documents required by obligation. During a large cleanup backlog, prioritize **correct data selection** over **raw deletion speed**.

## 42. Runbook: deleted content still exists in object storage

A database row may be gone while the attachment remains:

1. Identify the object key/version from deletion manifests or storage inventory.
2. Check whether the notification/payload was marked `CONTENT_PURGED`.
3. Check whether the object still has live references from other emails/documents.
4. Confirm tenant/bucket ownership and legal holds.
5. Inspect object versioning/replication/lifecycle settings.
6. Run bounded, idempotent deletion retries.
7. Record the actual outcome per object/version.
8. If deletion fails, escalate to the owner/provider.
9. Update orphan/outstanding deletion metrics.
10. Fix transaction ordering so object references are not lost before manifest creation.

Never run a command deleting all objects sharing a prefix unless you know that prefix holds no data belonging to other jobs.

## 43. Runbook: user requests deletion under a legal hold

A deletion request may only partially complete because certain records must be retained on specific grounds:

1. Authenticate the requester and data scope.
2. List datasets and active holds.
3. Verify each hold has valid grounds, owner, and correct scope.
4. Delete/anonymize portions not covered by holds.
5. Restrict access to held data and prohibit unrelated use.
6. Record per-dataset results: completed, deferred, ineligible, and reasons.
7. Report status per workflow and applicable requirements; never say "everything deleted" when untrue.
8. When a hold is released, re-evaluate eligibility automatically or via workflow.
9. Store minimal audit evidence without keeping full content as proof.

**Never treat legal holds as a blanket flag bypassing all retention indefinitely** when only certain metadata is needed for a case.

## 44. Runbook: restoring a database from an older backup

After restoring:

1. Isolate the network/SMTP sender and do not open the application to users immediately.
2. Confirm the snapshot timestamp.
3. Fetch deletion journals/tombstones and state transitions newer than the snapshot.
4. Reapply necessary cancellation/expiry/suppression/erasure decisions.
5. Evaluate restored attachment objects and caches.
6. Do not automatically replay all `PENDING` items, as some may have become `SUBMITTED` after the snapshot.
7. Reconcile provider message IDs/outcomes where available.
8. Verify active legal holds.
9. Run validation ensuring purged records/datasets do not reappear.
10. Only upon completion allow workers and UI back online per runbook.

Restoring exact backup bytes does not mean **restored data is valid for reuse**. In particular, never resend emails the user cancelled, expired tokens, or emails already accepted by the provider.

## 45. Unit test: retention deadlines must use the right trigger

One of the simplest yet most dangerous bugs is calculating deadlines from `createdAt` instead of `terminalAt`. You can test `MailRetentionCalculator` with JUnit 5:

~~~java
package com.example.mail.retention;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class MailRetentionCalculatorTest {

    private final MailRetentionCalculator calculator =
            new MailRetentionCalculator();

    private final RetentionRules exampleRules =
            new RetentionRules(
                    "example-v1",
                    Duration.ofDays(7),
                    Duration.ofDays(90),
                    Duration.ofDays(3),
                    Duration.ofDays(14),
                    Duration.ofDays(7));

    @Test
    void computesDeadlinesFromTerminalTime() {
        Instant terminal =
                Instant.parse("2026-11-20T02:00:00Z");

        RetentionDeadlines result =
                calculator.afterTerminal(terminal, exampleRules);

        assertEquals(terminal.plus(Duration.ofDays(7)),
                result.contentPurgeAfter());
        assertEquals(terminal.plus(Duration.ofDays(90)),
                result.metadataPurgeAfter());
        assertEquals("example-v1", result.policyVersion());
    }

    @Test
    void cannotScheduleCleanupWithoutTerminalTime() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.afterTerminal(null, exampleRules));
    }
}
~~~

This is an illustrative **time-logic unit test**; it does not prove a cleanup worker actually avoids deleting `PENDING` records or respects legal holds. Those constraints must be tested at the repository/state-transition layer.

### Unit tests by data category

Across mail categories:

~~~text
OTP body:
  terminalAt + approved OTP-content period

Transactional metadata:
  terminalAt + approved support/ops period

Provider raw webhook:
  processedAt + approved event period

Pending future schedule:
  no content purge deadline until valid terminal transition
~~~

Retention durations should come from organization-approved retention policies, not hardcoded single defaults across all tenants/categories in tests.

## 46. Integration test: do not delete emails still needed for sending

Test against a database with transactions/locking sufficiently close to production:

~~~text
Given:
  mail notification status = PENDING
  scheduledAt = next month
  createdAt = long ago
  mail payload exists

When:
  retention cleanup runs

Then:
  notification remains PENDING
  payload remains available to dispatcher
  no deletion task is created
~~~

Variants:

- `PROCESSING` with an active lease.
- `RETRY_PENDING` with `nextAttemptAt` in the future.
- `SUBMISSION_UNKNOWN` with an open reconciliation case.
- `SUBMITTED` before the content purge deadline arrives.
- `CANCELLED` once the content deadline has arrived.
- `EXPIRED` with tokens needing early removal.

Do not assert only `payload_state` in the DB. If external objects were deleted by mistake while the row still remains, DB-only assertions miss a critical failure.

## 47. Integration test: database and object store do not share transactions

A failure-injection test for the deletion manifest:

### Scenario A — object deletion fails

~~~text
1. DB transaction creates deletion task.
2. Object store returns transient 503.
3. Task becomes RETRY_PENDING.
4. mail_payload is not marked CONTENT_PURGED.
5. Retry occurs with backoff.
6. Object delete later succeeds.
7. Payload metadata is cleared.
8. Task becomes COMPLETED.
~~~

Verify the task survives worker restarts without creating duplicate manifests for the same decision.

### Scenario B — object deleted, DB update fails

~~~text
1. Deletion task references object version V.
2. Object V is deleted successfully.
3. DB connection drops before completion update.
4. Worker restarts.
5. It retries delete V idempotently.
6. It verifies object V is absent.
7. DB status becomes CONTENT_PURGED / COMPLETED.
~~~

Do not report `FAILED_PERMANENT` merely because a retry delete returned `NotFound` after an earlier attempt already removed it, but verify the exact object key/version and provider semantics.

### Scenario C — database deleted before manifest

This is a bug to **test against**:

~~~text
1. mail_payload row deleted.
2. Process crashes before deletion task/object key persisted.
3. External object remains without reference.
~~~

Correct design persists a durable manifest **before losing references**, or provides strong inventory/reconciliation to find orphan objects.

## 48. Integration test: legal holds, concurrency, and restore

### Legal hold

- Record passes TTL but carries `CONTENT` hold: do not delete body.
- Record holds only `METADATA`: handle content per policy and exact scope.
- Multiple holds: releasing one does not delete while another remains active.
- Hold created concurrently with cleanup claim: state transition/locking prevents unauthorized deletion.
- Hold released: record becomes eligible again if past deadline.

### Worker concurrency

- Two cleanup instances run simultaneously: only one task claims each resource.
- Cleanup runs while SMTP worker prepares to send: payload of active job cannot be deleted.
- Operator triggers replay/cancel during cleanup: status and payload cannot diverge.
- Worker with an expired lease cannot mark `CONTENT_PURGED` if generation changed.

### Restore

1. Create data N and take a snapshot.
2. Run retention to delete N and write a tombstone.
3. Restore the old snapshot into an isolated environment.
4. Run deletion replay/reconciliation.
5. Verify content of N cannot be reused.
6. Verify the SMTP dispatcher cannot resend N automatically.

This tests the **restore workflow**, not merely backup job completion.

## 49. Retention test matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| R01 | `PENDING` created long ago, scheduled in future | Do not purge payload |
| R02 | `RETRY_PENDING` within retry window | Do not purge payload |
| R03 | `PROCESSING` with active lease | Do not purge |
| R04 | `SUBMISSION_UNKNOWN` unreconciled | Keep evidence per window |
| R05 | `SUBMITTED` past content TTL | Purge designated body/subject/template model |
| R06 | Metadata TTL longer than body TTL | Keep designated minimal metadata |
| R07 | `CANCELLED` before SMTP | Eligible for early purge per policy |
| R08 | `EXPIRED` containing OTP | Do not resend; content removed on schedule |
| R09 | `DEAD_LETTER` still holds payload | Bounded TTL; never kept indefinitely |
| R10 | Legal hold CONTENT | Do not delete held body |
| R11 | Legal hold METADATA | Do not delete metadata; handle content by scope |
| R12 | Two holds on same resource | Removing one leaves the other active |
| R13 | Policy version changes | Deadlines migrated per decision |
| R14 | Object delete retry hits 503 | Manifest retained and retried with backoff |
| R15 | Object deleted, DB update fails | Idempotent retry reaches COMPLETED |
| R16 | Object missing at exact version | Do not retry forever given valid deletion evidence |
| R17 | Object delete AccessDenied | Do not mark COMPLETED |
| R18 | Object store has multiple versions | Handled per versioning/retention rules |
| R19 | Object has replication | Accurately report deleted/remaining scope |
| R20 | Shared attachment still has live refs | Do not delete object used by other jobs |
| R21 | Attachment is only a reference to business document | Do not delete documents belonging to other systems |
| R22 | Raw MIME in debug store | Independent TTL/ACL and cleanup |
| R23 | Provider webhook raw past TTL | Keep only required projection |
| R24 | DLQ stores serialized body | Retention deletes/invalidates copies |
| R25 | Log contains token due to bug | Redaction and incident handling for written logs |
| R26 | Metrics label contains recipient | Reject label design |
| R27 | Redis cache holds rendered body | Invalidation/TTL and persistence snapshot review |
| R28 | Local temp file left after crash | Sweeper and permissions handle cleanup |
| R29 | Data subject erasure request | Tasks dispatched to exact datasets |
| R30 | Provider lacks deletion API | Report limitation; do not claim provider deletion |
| R31 | Mail already in recipient mailbox | Do not claim ability to recall from recipient |
| R32 | Suppression record kept minimal | Prevent accidental resend after marketing opt-out |
| R33 | Metadata contains HMAC email | Still requires policy, key access controls, and TTL |
| R34 | Backup restored from pre-deletion snapshot | Tombstone replay protects deleted data |
| R35 | Two cleanup workers claim concurrently | No double-deletion state race |
| R36 | Purge job and send worker contend | State transitions prevent using deleted payload |
| R37 | Quarantine holds infected file | Never released via cleanup path |
| R38 | Case hold released | Cleanup re-evaluates once eligible |
| R39 | Very large batch | Causes no DB outage or SMTP SLO breach |
| R40 | Audit deletion record | Minimal evidence retained with audit's own TTL |

Test suites should distinguish **policy unit tests**, **database/object-store integration tests**, and **backup/restore/provider workflow tests**. A mock object store returning success does not prove a real provider deletes noncurrent versions or replicated data.

## 50. Common mistakes

### 50.1. Deleting only the mail body while keeping raw MIME

Raw MIME usually holds the entire body and attachments. Deleting the HTML column while keeping MIME source in a debug bucket fails data minimization goals.

### 50.2. Treating metadata as non-sensitive data

Full recipient email, subject, timestamps, and bounce reasons can link to individuals. Data minimization and separate TTLs are needed.

### 50.3. Computing TTL from `createdAt` for future jobs

Far-scheduled emails may be deleted before sending. Deadlines must follow state and proper retention triggers, not just creation dates.

### 50.4. Deleting `PROCESSING` or `RETRY_PENDING`

Workers still need the payload. Cleanup needs state/lease checks and synchronization with dispatchers.

### 50.5. Deleting `SUBMISSION_UNKNOWN` too early

Loses data needed to reconcile an attempt that may have been accepted. Needs a reconciliation window and reason.

### 50.6. Keeping all dead letters forever

DLQs are stores of message copies. They require retention, quotas, and purge/review workflows.

### 50.7. Putting OTPs into error logs

Even short log TTLs still carry exposure risk. Minimize data at write time; handle exposed historical logs via incident workflows.

### 50.8. Deleting from the database and forgetting object storage

Raw MIME/attachments persist without references. Use durable deletion manifests and object inventories.

### 50.9. Calling object delete once and marking complete

Network issues, permissions, versioning, or replication can leave objects intact. Confirmation and partial/retry states are required.

### 50.10. Deleting attachments shared by other jobs

Requires clear resource ownership or reference tracking. Mail cleanup must never delete original accounting documents.

### 50.11. Using soft delete as final deletion

A `deleted` flag only hides records from the UI; plaintext still persists in the database and backups.

### 50.12. Treating HMAC emails as completely anonymous

If still linkable via keys or external sources, the data is not necessarily anonymous.

### 50.13. Deleting suppressions to "delete all data"

Can cause the system to resume sending marketing to opted-out users. Requires policies balancing privacy with do-not-send obligations.

### 50.14. Using an unscoped boolean legal hold

Holds all data indefinitely and hinders audits. Hold records need owner, case, scope, and release workflows.

### 50.15. Omitting logs/APM from the data inventory

Raw SMTP transcripts, recipients, and bodies can linger outside databases for long periods.

### 50.16. Confusing provider data deletion with SMTP recall

Deleting metadata inside a provider does not retrieve emails already delivered to a recipient's mailbox.

### 50.17. Ignoring versioning when deleting objects

Delete markers may only hide the latest object while noncurrent versions persist.

### 50.18. Restoring backups resurrects deleted data

You need a deletion journal/tombstones and restore-safe reconciliation before reopening workers/UI.

### 50.19. Granting raw mail read access to all support agents

Long-lived access increases leak exposure. Grant permissions only per use case, time window, and audit trail.

### 50.20. Running unbatched bulk `DELETE` on large tables

Can stall databases, cause replication lag, or degrade SMTP dispatch. Use conditional batching/partitioning.

### 50.21. Failing to check backup and replication retention

Active databases are cleared while snapshots/replicas/exports still retain content. Scope and obligations must be documented per environment.

### 50.22. Using one shared TTL for bodies, events, and audits

Each dataset has distinct purposes and states. One TTL can be far too long for OTPs yet too short for reconciliation metadata.

### 50.23. Treating "cleanup task succeeded" as "all copies deleted"

A task may only cover one dataset. Record outcomes per component and prove actual scope.

### 50.24. Having no retention owner

When cleanup fails, no one knows who is authorized to adjust policies or resolve holds. Clear owners and runbooks are mandatory.

## 51. Production checklist for data retention

### Data inventory and policy

- [ ] Inventory all places storing bodies, subjects, MIME, attachments, metadata, and provider events.
- [ ] Each dataset has a purpose, owner, classification, retention trigger, and period.
- [ ] TTL milestones are approved against applicable obligations rather than chosen arbitrarily.
- [ ] `policyVersion` and a policy-change workflow exist.
- [ ] Content retention is separated from metadata retention.
- [ ] Distinct rules exist for OTP, transactional, marketing, support, and attachments.
- [ ] Scoped legal holds/exceptions are supported.
- [ ] Provider-side retention and deletion limits are documented.

### Database and object storage

- [ ] Never purge while `PENDING`/`PROCESSING`/`RETRY_PENDING` still need payloads.
- [ ] Reconciliation window defined for `SUBMISSION_UNKNOWN`.
- [ ] `terminalAt` and purge deadlines use proper triggers.
- [ ] Indexes/queries select due records without impacting dispatchers.
- [ ] Durable deletion manifests are created before losing object references.
- [ ] External deletes are idempotent with retry/backoff and partial states.
- [ ] Object versions, replication, and object locks are handled where applicable.
- [ ] Never delete attachments still referenced by other jobs or external systems.
- [ ] Race controls exist between sending, cancellation, legal holds, and cleanup.
- [ ] Cleanup exists for dead-letter queues and quarantine.

### Security, privacy, and auxiliary data

- [ ] Bodies/template models holding tokens are minimized and appropriately encrypted.
- [ ] Logs/traces/metrics contain no raw content or secrets.
- [ ] Support access to raw MIME is restricted and audited.
- [ ] Data subject deletion workflows trace across datasets and exceptions.
- [ ] Suppressions store minimal data per scope and policy.
- [ ] Backups/lifecycle/restores do not resurrect deleted data.
- [ ] Caches, temp files, and heap dumps have TTLs/retention.
- [ ] Audit/deletion journals also have access controls and dedicated retention.

### Operations and testing

- [ ] Cleanup runs in batches with timeouts, concurrency limits, and quotas.
- [ ] Metrics exist for `oldestOverdue`, remaining candidates, and failed deletions.
- [ ] Alerts fire when overdue backlogs grow or object deletions fail.
- [ ] Tests verify pending/future/unknown/held records are not deleted.
- [ ] Tests cover external delete failures followed by retry/completion.
- [ ] Tests verify object sharing/versioning matching the active provider.
- [ ] Tests cover cleanup vs. dispatch races and legal hold creation.
- [ ] Tests cover backup restore + tombstone replay.
- [ ] Runbooks exist for overdue backlogs, orphan objects, holds, and erasure requests.

This checklist provides design and operational guidance. It **does not replace live testing, privacy reviews, or evaluation of applicable legal obligations**.

## 52. Lifecycle example: payment confirmation email

Suppose the system sends a receipt after payment:

~~~text
2026-11-12 10:00  Payment transaction commits
                  Outbox notification created
                  Payload references receipt snapshot v3

2026-11-12 10:00  Mail worker submits via SMTP
                  Relay accepted, status=SUBMITTED

2026-11-12 10:05  Provider event says DELIVERED
                  Projection updated

Later              Content retention window expires
                  Renderer data / mail-specific MIME
                  and temporary attachments are purged

Later still        Metadata retention expires
                  Attempt and recipient links are
                  deleted/anonymized as policy requires
~~~

### What to keep separate

- **Original receipt:** may belong to the accounting system with its own lifecycle.
- **Mail-specific copy:** object generated by the mail worker for delivery, separate retention.
- **SMTP attempt:** provider key, code, and timestamp, support retention.
- **Consent/suppression:** preference data with an independent lifecycle.
- **Backups/journals:** requires workflows preventing mail payload resurrection post-purge.

Never let mail retention accidentally delete official invoices by sharing the same `storageKey`.

## 53. Lifecycle example: expired OTP

~~~text
10:00  OTP created, valid until 10:05
10:00  Mail outbox queued
10:01  SMTP provider unavailable
10:03  Retry pending
10:06  Worker resumes
       OTP expired -> do not submit
       status=EXPIRED
       plaintext token/body content purge eligible
       limited operational metadata may remain
~~~

Key points:

1. Retries must not exceed token expiry.
2. Delete or protect plaintext tokens once sending is no longer required.
3. Never save tokens into exceptions/logs to debug outages.
4. Never generate new OTPs from cleanup workers; authentication logic decides new codes.
5. An `EXPIRED` record may keep a short-lived reason for support without keeping the code.

## 54. Lifecycle example: when a user unsubscribes from marketing

~~~text
Day 1: Marketing email submitted
Day 2: Recipient opts out
Day 2: Preference/suppression updated
Day 3: Old marketing body reaches purge deadline
Day 3: Body removed; minimal opt-out remains
Day 4: New campaign attempts to enqueue
Day 4: Consent/suppression gate prevents submission
~~~

If the entire suppression record were deleted on Day 3 alongside the email body, Day 4 could resend unwanted messages. This illustrates why **sent content retention** and **opt-out choice retention** must be separated within applicable purpose and rules.

## 55. Self-check questions

**1. When `JavaMailSender.send()` completes, should all email data be deleted immediately?**

There is no single rule. Bodies can be purged early if resends/reconciliation are no longer needed and no holds apply; metadata/attempt history may need a different retention window.

**2. Can email metadata be personal data?**

Yes. Recipient addresses, subjects, timestamps, and communication relationships can identify or link to a person.

**3. Why not use `createdAt + 7 days` for every payload?**

Emails may be scheduled months out or still retrying/reconciling. TTLs must rely on state and appropriate retention triggers.

**4. Why separate `mail_payload` and `mail_notification`?**

To delete content early while keeping minimal operational state, and to separate body read permissions from metadata.

**5. Should a `SUBMISSION_UNKNOWN` email be deleted immediately when the worker catches an exception?**

No. Correlation/evidence must be kept for a bounded reconciliation window, because the SMTP relay may have accepted it.

**6. Why not retain DLQs indefinitely?**

DLQs can contain payloads, OTPs, or attachments just like the outbox; they need TTLs, quotas, access controls, and purge workflows.

**7. What if the body is deleted from the DB while raw MIME remains in object storage?**

Content deletion is incomplete. Deletion manifests and proper object/version cleanup are needed.

**8. Why might object store deletion fail to remove all copies?**

Versioning, replication, delete markers, object locks, or backups may still hold copies.

**9. Does soft deletion count as final deletion?**

No. Soft delete merely hides or flags a record; plaintext can still persist.

**10. Should deletions be audited?**

Completion evidence may be needed, keeping only minimal information and applying retention to the audit itself.

**11. Should a legal hold keep all emails for a tenant indefinitely?**

Not by default. Holds need owners, cases, dataset scopes, and release mechanisms.

**12. Should suppression be deleted when marketing email bodies are deleted?**

Not automatically. Suppression prevents unwanted resends under its own policy, while still minimizing personal data.

**13. Does hashing an email address automatically make it anonymous?**

No. If still linkable or reversible via keys/other sources, it may remain personal data.

**14. Can an email be deleted from the recipient's mailbox after SMTP submission?**

Normally not via Spring Mail or SMTP. Applications only control copies within their own boundary and providers under supported contracts/features.

**15. Why include logs/APM in retention?**

Because exceptions, debug traces, or support exports can retain bodies/recipients/secrets even after DB purges.

**16. Why do backup restores need a deletion journal?**

Old snapshots can bring back deleted data. Journals/tombstones reapply deletion decisions before reopening workloads.

**17. Can cryptographic erasure replace all deletion tasks?**

No. It applies only to ciphertext protected by scoped keys; it does not eliminate plaintext copies in logs, providers, or exports.

**18. Should cleanup run in the same transaction as object store deletes?**

Avoid holding DB transactions open during network calls. Use durable manifests and idempotent steps.

**19. If object deletion times out, should it be marked complete?**

No. The outcome is uncertain; verification and safe retry are required.

**20. How do you prove a record was deleted?**

Combine database checks, object inventory/versions, deletion tasks, provider confirmations (if any), backup lifecycles, and appropriate minimal audits.

**21. If a user cancels a scheduled email, can cleanup delete its content?**

Once validly cancelled with no remaining dispatch capability or hold, it can be purged per policy. Keep cancellation status and handle worker races.

**22. If the retention policy changes, should all old records be deleted immediately?**

Not automatically. Determine retroactive rules, holds, operational impact, and execute controlled migrations.

**23. Why track "overdue data remaining" in addition to "data deleted"?**

Because a system can delete steadily while overdue backlogs still grow. Overdue counts measure actual deadline compliance.

**24. How do you stop deletion workers from deleting business documents referenced by emails?**

Separate ownership between mail-specific copies and original documents; use references/permissions and deny mail cleanup access outside its scope.

**25. Is data retention just a cron `DELETE`?**

No. It spans classification, policy versioning, access controls, state-aware deadlines, deletion orchestration, legal holds, provider/backup handling, auditing, monitoring, and restore-safe controls.

## Conclusion

**Data retention for email content and metadata in Spring Framework Mail is an end-to-end lifecycle production design, not a table-cleanup query.** `JavaMailSender` handles SMTP submission; the application must determine how long bodies, subjects, template models, raw MIME, attachments, attempts, provider events, suppressions, logs, and backups must exist and for what purpose.

**Separate content retention from metadata**, compute deadlines from appropriate states and events, and never purge payloads that remain `PENDING`, `PROCESSING`, `RETRY_PENDING`, or unresolved `SUBMISSION_UNKNOWN`. Use batched cleanup with state/lease guards, durable deletion manifests spanning databases and object storage, idempotent retries, and controls over object versions and shared references. Respect scoped legal holds, handle deletion requests based on where data actually lives, keep minimal suppression records to prevent opt-out violations, and design backup restores so purged data cannot be resurrected.

Finally, **measure overdue unpurged data as well**, test failure windows, restrict read access to retained data, and never claim deletions at providers or recipient mailboxes beyond your control. A sound retention policy ensures emails retain enough data to deliver and reconcile while minimizing sensitive data once its purpose has ended.
