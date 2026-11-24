# Evaluating Delivery, Security, and Audit Requirements

A **Spring Framework Mail** application can send an email with just a few lines of `JavaMailSender.send(...)`. However, **being able to send** does not mean an email architecture meets product, operational, security, and audit requirements. For promotional mail, a few minutes of delay may be acceptable; for payment receipts, lost or duplicate notices can trigger complaints; for password-reset links, both content and lifetimes must be protected; for sensitive data, you must prove who requested sending, what data was permitted to leave, and what evidence exists of the delivery outcome.

Therefore, when choosing among **Spring Mail + SMTP**, an **internal SMTP relay**, an **email provider API**, a **transactional outbox**, or a dedicated email platform, the team must clarify three requirement groups:

1. **Delivery:** how reliably are emails created, queued, submitted to relays, delivered to destination mail servers, and recovered on errors?
2. **Security:** who is authorized to request sends, how are content and credentials protected, and does the system prevent spoofing and abuse?
3. **Audit:** days or months later, what events can the organization prove actually occurred, using what evidence, and who is permitted to view it?

These three groups are tightly coupled. An outbox prevents losing requests, yet does not encrypt content. STARTTLS protects transport in transit, yet does not prove Inbox placement. Retaining full email bodies aids investigations, yet expands data-leakage risk and retention policy exposure.

This lesson presents a **practical architectural evaluation framework**, from writing measurable requirements, defining responsibility boundaries, and building decision matrices to designing Spring Boot services, fault-injection testing, and acceptance criteria.

> **Overarching principle:** Claim only the guarantee level that the system can observe and prove. Specifically, a successful `JavaMailSender.send(...)` call typically reflects **SMTP submission**, not guaranteed Inbox placement or recipient reading.

## 1. Learning Objectives

After this lesson, you can:

- Gather and classify delivery requirements by email type and business impact.
- Distinguish `REQUESTED`, `QUEUED`, `SMTP_ACCEPTED`, `DELIVERED`, `BOUNCED`, `COMPLAINED`, and `UNKNOWN`.
- Define SLO/SLI targets for latency, error rates, backlogs, and incident detection time.
- Understand why generic SMTP does not offer exactly-once submission when network outcomes are uncertain.
- Choose synchronous sending, queues, transactional outboxes, or provider APIs based on risk.
- Evaluate deliverability: SPF, DKIM, DMARC, verified `From`, bounces, and suppression.
- Evaluate transport TLS security, authentication, secrets, send authorization, multi-tenant isolation, and sensitive data.
- Design audit trails from business events through messages, attempts, provider events, and manual retry decisions.
- Establish retention, redaction, access control, and rules for data-deletion requests.
- Build a decision matrix with criteria, weights, evidence, and approvers.
- Use Spring Boot, `JavaMailSender`, outboxes, callbacks, and tests to turn requirements into a verifiable architecture.
- State residual limitations after implementation rather than promising beyond technical capabilities.

## 2. Why Email Architecture Decisions Do Not Start with a Library

Two systems both using `JavaMailSender` can have completely different requirements:

| System | Email Example | Consequence of Loss | Consequence of Duplicate | Consequence of Content Leak |
|---|---|---|---|---|
| Internal app | Daily build report | Low or medium | Low | Depends on data |
| E-commerce | Payment confirmation | High | Medium/high | May expose order details |
| Authentication | Password reset link | High within short window | Causes confusion, account risk | Very high if token leaks |
| Customer support | Support ticket reply | Medium/high | Creates split threads | May contain personal data |
| Marketing | Campaign email | Delay often tolerable | High spam-complaint risk | Depends on customer list |
| Financial/legal | Critical notice | High | Can cause disputes | Can be very high |

You cannot answer "SMTP or API?" merely by line count or coding speed.

Appropriate sequence:

```text
Business outcomes
      |
      v
Risk / data classification
      |
      v
Delivery / security / audit requirements
      |
      v
Candidate architectures
      |
      v
Threat & failure analysis
      |
      v
Proof-of-concept / tests / measurements
      |
      v
Architecture decision record (ADR)
      |
      v
Implementation & operational controls
```

## 3. Defining the Boundaries of an Email Transaction

A send request can traverse multiple systems:

```text
Business service
     |
     | 1. Request created
     v
Application database / outbox
     |
     | 2. Request durably queued
     v
Dispatcher / mail worker
     |
     | 3. Submission attempted
     v
Spring JavaMailSender / Jakarta Mail
     |
     | 4. SMTP DATA accepted by relay
     v
SMTP provider / relay queue
     |
     | 5. Provider attempts delivery
     v
Recipient mail server
     |
     | 6. Receiving server accepts / rejects
     v
Mailbox / quarantine / spam filters
     |
     | 7. Human may or may not see message
     v
Recipient
```

There are multiple responsibility boundaries:
- **Application:** content, recipients, send authorization, scheduling, retries, and outbox records.
- **SMTP relay/provider:** acceptance, retries to destination servers, queues, bounces, and events if supported.
- **Recipient mail server:** receiving policies, spam filtering, quarantine, mailbox delivery.
- **Email client/user:** rendering, filtering, reading, opening links.

Never collapse everything into a single `sent = true` column and assume delivery obligations are fulfilled.

### 3.1. Distinguish Logical Message from Submission Attempt

- **Logical email:** one business notification, e.g., "receipt for order 123."
- **Submission attempt:** one instance of a worker connecting to a provider and submitting the email.
- **Delivery event:** provider feedback on delivery status to the destination server.
- **User interaction:** opening the email, clicking links, or other engagement.

One logical email can have multiple attempts due to pre-acceptance failures. Conversely, one attempt can span multiple recipients if sent as a shared MIME message, which complicates tracking.

### 3.2. Define a Clear Source of Truth

A data store may be the source of truth for **send requests**, without being the source of truth for **delivery**.

For example:
- Outbox DB: "created one logical email and executed attempts."
- SMTP reply/provider event: "the relay accepted it."
- Delivery callback: "the provider observed the destination server accept/reject it."
- No source inherently proves a human actually read the message.

## 4. Name States According to What Can Be Proven

A practical model:

| State | Usable Definition | Minimum Evidence |
|---|---|---|
| `REQUESTED` | User/system requested sending | Business command/event |
| `QUEUED` | Request is durably persisted | DB transaction commit or durable broker receipt |
| `SENDING` | Worker claimed and started an attempt | Attempt record/lease |
| `SMTP_ACCEPTED` | Relay confirmed submission acceptance | Matching final SMTP reply or provider confirmation |
| `UNKNOWN` | Insufficient evidence to prove accepted or not | Exception/timeout + attempt history |
| `RETRY_WAIT` | Proven unaccepted failure, eligible for retry | Classified outcome + retry policy |
| `DELIVERED` | Provider reported delivery per its contract | Authenticated webhook/API event |
| `DEFERRED` | Delivery to destination server delayed | Provider delivery event |
| `BOUNCED` | Delivery failed per provider semantics | Bounce/DSN/provider event |
| `CANCELLED` | Request canceled before valid submission | Conditional state transition |
| `EXPIRED` | Past the allowed sending deadline | Business deadline |

Every project does not need these exact names, yet you must **document definitions** and never mix submission states with delivery states.

### 4.1. Accepted Differs from Delivered

An SMTP relay accepting an email is often just the first hop. The provider still must attempt delivery to the destination mail server. The receiving side may defer, reject, quarantine, or filter per its own policies.

If an SLO states "99.9% of emails delivered within 5 minutes," define "delivered" by specific provider evidence, whether rejecting domains are excluded, and how missing callbacks are handled.

### 4.2. Delivered Differs from Inbox

A provider `delivered` callback usually means the destination mail server accepted the message at a given stage—it does not prove the message landed in the Inbox instead of Spam or was opened by the recipient.

### 4.3. Open Tracking Is Not Reliable Proof of Reading

Tracking pixels can be blocked, prefetched, or cached by mail clients. Never rely on "email opened" as sole proof that a legal notice was read or a transaction confirmed.

## 5. Gather Requirements by Email Type

Do not apply the same SLA, access permissions, or retention window to every email.

An initial classification table:

| Mail Type | Priority | Tolerable Latency | Duplicates Allowed? | Sensitive Content | Retention Policy |
|---|---|---|---|---|---|
| Authentication/OTP | High | Low; must remain valid | Strictly limited | Tokens and identity | Keep minimal metadata |
| Invoices/receipts | High | Per legal/business workflow | Avoid confusion | Order details, money, PII | Per records policy |
| Application alerts | Medium | Minutes depending on type | Possible, still deduplicate | Payload-dependent | Limited by need |
| Operational reports | Medium | Per schedule | Per SLA | Business content | Access-controlled + retention |
| Marketing | Usually lower than transactional | Per campaign | Avoid duplicates | Consent, lists | Per purpose/applicable law |

These values are **classification examples**, not default SLAs every company must adopt.

### 5.1. Questions to Ask the Business Owner

1. What happens if an email is never sent?
2. What happens if a recipient receives two copies?
3. When does an email become useless or dangerous if delivered late?
4. Do recipients have another channel to access the content?
5. Are there legal/regulatory duties to prove sending or notification?
6. Does content include PII, financial data, trade secrets, or tokens?
7. Is the email transactional, marketing, or another category under applicable policy?
8. Are multiple languages, timezones, attachments, or tenant-specific branding required?
9. Who is authorized to decide resending an email with an unknown outcome?
10. During a provider outage, should the system wait, fail over, or pause?

## 6. Write Testable Requirements

A requirement like "email must be fast, secure, and fully audited" cannot be accepted because the terms lack definitions.

Rewrite as:

| Code | Group | Example Requirement | Acceptance Evidence |
|---|---|---|---|
| D-01 | Delivery | Committed mail requests survive worker restarts | Crash/restart test with durable DB |
| D-02 | Delivery | Under healthy provider conditions, 99% of transactional jobs submit within X minutes | SLI from outbox committed → SMTP accepted |
| D-03 | Delivery | `UNKNOWN` attempts must not auto-resubmit | Fault injection dropping final SMTP reply |
| D-04 | Delivery | Expired jobs must not be submitted | Clock-controlled deadline test |
| S-01 | Security | SMTP mandates TLS with hostname verification | Test confirming cert mismatch is rejected |
| S-02 | Security | Secrets never appear in code or public configs | Secret inventory + access review |
| S-03 | Security | Tenant A cannot choose sender/recipient data of Tenant B | Authorization/integration test |
| A-01 | Audit | Trace business event → mail job → attempt → provider event | Query trace via correlation ID |
| A-02 | Audit | Only authorized roles can view sensitive data | RBAC test + access audit |
| A-03 | Audit | Retention/redaction matches data classification | Retention test and storage policy |

**X minutes, percentages, and retention periods** must be approved by business/operations; never treat illustrative numbers as product commitments.

### 6.1. Functional and Non-Functional Requirements

- **Functional:** HTML MIME, attachments, cc/bcc, reply-to, delayed sends, multi-provider, unsubscribes.
- **Non-functional:** uptime, throughput, latency, security, auditability, recovery time, compliance, isolation, cost.

Saying "`JavaMailSender` is enough" is meaningful only after both requirement sets are evaluated.

### 6.2. Severity and Acceptance Criteria

Each requirement should specify:
- Owner.
- Priority `MUST`, `SHOULD`, `COULD`.
- Email/tenant scope.
- Verification test or metric description.
- Constraints/exceptions.
- Risk-acceptance criteria if temporarily unmet.

## 7. SLIs, SLOs, SLAs, and Error Budgets

Three easily confused concepts:

- **SLI:** observed indicator, e.g., time from outbox commit to SMTP accepted.
- **SLO:** internal target, e.g., share of submissions accepted within a threshold.
- **SLA:** commercial/contractual commitment with explicit consequences if missed.

Never claim "99.99% delivered" when the provider lacks complete callbacks or the denominator is undefined.

### 7.1. Suggested Indicators

```text
queue_latency =
    first_attempt_started_at - outbox_committed_at

submission_latency =
    smtp_accepted_at - outbox_committed_at

provider_delivery_latency =
    provider_delivered_at - smtp_accepted_at

retry_delay =
    next_attempt_started_at - first_failed_at
```

Compute values only when timestamps and states are meaningful; never count `UNKNOWN` as definite success or definite failure merely to polish percentages.

### 7.2. The Denominator Must Be Explicit

For example, an SLI "percentage of transactional emails accepted within 2 minutes" must define:
- count only eligible, unexpired jobs;
- whether hard-bounced addresses are excluded;
- whether external outages are included;
- how canceled emails are treated;
- whether customer-supplied invalid addresses count.

An ambiguous denominator can make the exact same system report 95% or 99.9% depending on calculation.

### 7.3. Where in the Pipeline Do Failures Occur?

Dashboards should separate:
- queue backlog;
- SMTP connection/auth failures;
- acceptance outcomes;
- delivery deferrals/bounces;
- bounce processing lag;
- webhook processing failures.

A single "email failure rate" metric hides both root cause and control boundaries.

## 8. Choosing Synchronous vs. Asynchronous Architecture

Three common paths:

```text
A. Synchronous
HTTP request -> JavaMailSender -> SMTP -> HTTP response

B. Async memory queue
HTTP request -> QueueChannel -> worker -> SMTP

C. Durable outbox
HTTP request -> DB transaction + outbox -> dispatcher -> SMTP
```

| Criterion | Synchronous Send | In-Memory Queue | Transactional Outbox |
|---|---|---|---|
| Easy to demo | Very easy | Easy | More complex |
| Caller waits for SMTP | Yes | Not necessarily | No |
| Burst resilience | Limited | Buffered | Workers can scale |
| Survives restarts | No durable work item by default | No, if memory-only | Yes when DB is properly managed |
| Tied to business transaction | Easy dual-write bugs | Enqueue can still be lost | Shared DB transaction preserves request |
| Retries and audits | Must build custom | Must build custom | Explicit states/attempts |
| Operational cost | Low initially | Medium | Higher, with strong control |
| SMTP exactly-once | No | No | **Still no** |

### 8.1. When Is Synchronous Reasonable?

Can make sense when:
- an admin tool tests email config;
- volume is low;
- business actions need no atomicity with email;
- callers tolerate SMTP latency and errors;
- durability/async/retry needs are minimal.

Never make an "order checkout" request wait on an SMTP relay when email is only a secondary notification and the provider can go down.

### 8.2. When to Use a Durable Outbox?

Worth adopting when:
- emails follow committed business events;
- requests must survive restarts;
- controlled retries are needed;
- per-attempt tracking is needed;
- multiple pods/workers run;
- auditing and incident reconstruction are required;
- scheduled messages exist.

An outbox neither replaces an SMTP provider nor guarantees Inbox delivery.

### 8.3. Persistent Queues or Brokers Are Another Option

RabbitMQ, Kafka, JMS, or a persistent Spring Integration `MessageStore` can form part of the solution. Evaluate:
- atomicity between the business DB and enqueueing;
- visibility/ack semantics;
- redelivery;
- dead-letter handling;
- ordering;
- duplicate side effects;
- retention and encryption.

When the business DB and broker lack a shared atomic transaction, **transactional outbox → publisher → broker** is often the fitting pattern.

## 9. SMTP via Spring Mail or HTTP Email API?

Both can send emails, yet differ in observability and integration.

| Criterion | `JavaMailSender` + SMTP | Provider HTTP API/SDK |
|---|---|---|
| Connection standard | SMTP, ubiquitous | Vendor-specific API |
| MIME and headers | App builds/controls directly | API-dependent |
| Acceptance | SMTP reply, not delivery | HTTP status/request receipt per contract |
| Submission idempotency | No universal standard | Possible if genuinely vendor-supported |
| Status queries | Often needs provider portal/separate log API | Sometimes easier, not guaranteed |
| Webhooks/delivery events | Available alongside provider | Usually available if vendor provides |
| Port/network policy | SMTP 587/465/relay | HTTPS 443 common |
| Portability | High at transport layer | Stronger vendor lock-in |
| Quota/rate management | Depends on relay and adapter | May expose API headers/quotas |
| Audit | Must build correlation layer | Can leverage vendor IDs |
| Credentials | SMTP credentials/OAuth2 | API key/OAuth2 |
| Cost | Per provider/infrastructure | Per vendor contract |

### 9.1. Do Not Pick an API Merely Because It Returns HTTP 202

`202 Accepted` may simply mean the API queued the request. It **does not mean delivered**. Read the provider contract for idempotency, states, webhooks, and retention.

### 9.2. Do Not Pick SMTP Merely for "Zero Lock-In"

MIME and SMTP are open standards, yet:
- rate limits, provider event APIs, and authentication vary;
- suppression, templates, and bounce handling can be vendor-specific;
- switching providers requires verified senders, DNS, and warm-up procedures.

A port/adapter layer limits vendor coupling, though it cannot erase all operational differences.

### 9.3. An Abstraction Must Not Hide Capabilities

Example:

```java
public interface OutboundMailPort {
    SubmissionAttemptResult submit(MailSubmission command);
}

public record MailProviderCapabilities(
    boolean supportsIdempotentRequests,
    boolean supportsSubmissionLookup,
    boolean supportsDeliveryWebhooks,
    boolean supportsRecipientLevelEvents
) {}
```

These models are application-defined. When an SMTP provider lacks lookup/idempotency, the adapter must report those limits honestly instead of fabricating a "delivered" status.

## 10. Self-Hosted SMTP Relay or Managed Service?

This decision requires Total Cost of Ownership analysis, not just cost per thousand emails.

**Self-operating a relay** can provide:
- routing control;
- internal logs/queues;
- private infrastructure integration;
- deep policy customization.

Yet it also places responsibility on you for:
- IP/domain reputation;
- anti-spam/abuse prevention;
- MTA hardening and patching;
- IP warm-up and feedback loops;
- bounce processing;
- DNS, rDNS, TLS;
- queue monitoring;
- 24/7 incident handling;
- protecting secrets and data.

**Managed services** reduce operational burden and supply webhooks, suppression, and reputation tooling, at the cost of vendor fees, contracts, data residency, and dependency risk.

### 10.1. When Is an Internal Relay Needed?

Examples:
- network mandates centralized egress;
- organization has a dedicated MTA team;
- strict control over routes and data flows is required;
- legacy systems already rely on the relay.

Never put an unmanaged SMTP relay into production solely to avoid provider fees.

### 10.2. Vendor Due Diligence

Request evidence of:
- delivery tracking capabilities and event retention;
- data processing locations and subprocessors;
- SLAs/support/incident communications;
- security of API keys/SMTP credentials;
- DKIM/domain verification;
- suppression and complaint handling;
- audit access and exports;
- portability/export/deletion;
- quotas and rate-limit policies;
- outage and recovery history.

Verify vendor claims from current contracts and docs rather than guessing from brand reputation.

## 11. Evaluating Deliverability: SPF, DKIM, and DMARC

**Deliverability** is more than "SMTP connects." A provider may accept a message while receivers still reject or spam-folder it due to poor domain authentication/reputation.

### 11.1. SPF

SPF lets a domain publish which servers may send for the corresponding **SMTP envelope identity**. An SPF pass **does not guarantee** DMARC pass if the domain is not aligned with the `From` header.

### 11.2. DKIM

DKIM signs parts of the email with a private key; receivers look up the public key in DNS to verify the signature. Know which provider signs, which `d=` domain is used, and how rotation and canonicalization work.

### 11.3. DMARC

DMARC evaluates the `From` header and requires **SPF pass + alignment** **or** **DKIM pass + alignment** (per active policy). DMARC policies can be monitor/quarantine/reject and generate reports.

### 11.4. Why Architecture Must Account for Domain Identity

Example:

```text
Header From: billing@example.com
Envelope MAIL FROM: bounce.vendor.net
DKIM d=vendor.net
```

Even when SPF/DKIM pass for the vendor domain, DMARC alignment with `example.com` can fail. Configure the provider to use an appropriate domain/identity or aligned DKIM per contract.

### 11.5. Deliverability Checklist

- [ ] Domains/sender identities verified.
- [ ] SPF has no conflicting TXT policies; DNS lookups bounded.
- [ ] DKIM signs the right domain/selector with a rotation plan.
- [ ] DMARC alignment verified with real received test emails.
- [ ] Bounces/complaints/unsubscribes handled.
- [ ] Transactional and marketing separated when needed.
- [ ] Volume, warm-up, and reputation managed.
- [ ] Deferrals, spam complaints, and hard/soft bounces monitored.

Never claim "having SPF/DKIM/DMARC guarantees Inbox placement." Filters also evaluate behavior, content, reputation, and receiver policies.

## 12. Bounces, Complaints, and Suppression Are System Requirements

A system with only `JavaMailSender.send` and no feedback handling may keep sending to:
- nonexistent addresses;
- unsubscribed users;
- users who reported spam;
- repeatedly hard-bouncing addresses;
- mailboxes blocked by providers.

That harms domain reputation and can violate communication policies.

### 12.1. Distinguish Bounce Types per Provider

- **Hard bounce:** typically a persistent failure requiring inspection/suppression per policy.
- **Soft bounce/deferred:** potentially temporary; provider may retry itself.
- **Complaint:** recipient spam report, usually requiring strict suppression.
- **Unsubscribe:** opt-out request for the applicable email category.

Do not apply the same retry rule to every event.

### 12.2. Suppression Takes Precedence Over Routing

If a recipient is suppressed, switching from provider A to B must not re-enable sending to them. Suppression/consent is a business/security policy **across all providers**.

### 12.3. Webhooks Are Not Automatically Trusted Data

Provider callbacks require:
- signature/HMAC verification per vendor contract;
- replay/idempotency checks;
- mapping provider/account/tenant;
- out-of-order event handling;
- dead-lettering and retries;
- preventing unauthenticated events from mutating system state.

## 13. Failure Analysis: Lost Mail, Duplicates, and UNKNOWN

In SMTP, an attempt can:
1. Fail cleanly before the message is submitted.
2. Receive a final `250` after `DATA`: SMTP relay accepted.
3. Time out waiting for the final reply after DATA: **outcome unknown**.

```text
Application                  SMTP relay
    |                            |
    |------ DATA content ------->|
    |------ end-of-DATA -------->|
    |                            | queues mail
    |<--- final 250 lost --------X
    |                            |
    v                            v
 client timeout             server accepted
```

Unconditional retries can submit **twice** to the relay. Never retrying can drop a message that was genuinely not accepted.

### 13.1. Three Safe Outcome Labels

- `SMTP_ACCEPTED`: evidence proves the server accepted it.
- `PROVEN_NOT_ACCEPTED`: evidence proves it was not accepted; only then classify retryable vs. permanent.
- `UNKNOWN`: insufficient evidence to conclude either way.

`MailSendException` or `SocketTimeoutException` does not automatically prove `PROVEN_NOT_ACCEPTED` because it may not indicate the exact protocol phase.

### 13.2. RFC Message-ID Does Not Create Exactly-Once

RFC `Message-ID` is an email identifier header useful for correlation/threading, yet **generic SMTP relays do not guarantee deduplication by Message-ID**. Submitting twice with the same `Message-ID` can still deliver two copies.

### 13.3. Retry Decisions Require Business Classification

For marketing emails, duplicates may be worse than skipping once. For urgent incident alerts, missing an alert may be worse than a duplicate. Policy frameworks must specify acceptable risk rather than letting a generic `@Retryable` decide for every email type.

## 14. Resilient Architecture: Business Transaction + Outbox

Common pattern when email stems from a business event:

```text
BEGIN DB TX
  update order/payment/customer state
  insert email_outbox(
      message_key, business_event_key,
      payload_ref, status=PENDING
  )
COMMIT
         |
         v
Dispatcher claims due rows
         |
         v
Attempt record committed
         |
         v
SMTP / Email API submission
         |
         v
Persist outcome
```

Requirements:
- Business state and outbox requests live in the **same DB transaction** where applicable.
- Never send SMTP inside a long-running transaction.
- Dispatchers read committed jobs only.
- Each job has a unique business key/idempotency key.
- Each attempt has its own attempt ID.
- After acceptance, stop application submission retries.
- After `UNKNOWN`, await reconciliation/policy decision.

### 14.1. What Does an Outbox Solve?

- Prevents losing committed requests on worker restarts.
- Decouples request latency from SMTP providers.
- Provides storage for states/retries/backlogs.
- Enables auditing and correlation.
- Allows safely restarting dispatchers.

### 14.2. What Does an Outbox Not Solve?

- Does not make SMTP atomic with the database.
- Does not guarantee Inbox delivery.
- Does not automatically encrypt/protect data stored in the DB.
- Does not configure valid DKIM signing.
- Does not check consent/suppression on its own.
- Does not force providers to retain webhooks forever.

## 15. Designing Outbox and Attempt History for Auditability

PostgreSQL example:

```sql
CREATE TABLE email_outbox (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    business_event_key VARCHAR(160) NOT NULL,
    mail_type VARCHAR(48) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    template_version VARCHAR(80) NOT NULL,
    payload_reference VARCHAR(512),
    sender_profile VARCHAR(100) NOT NULL,
    recipient_reference VARCHAR(256) NOT NULL,
    status VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_email_business_event
        UNIQUE (tenant_id, business_event_key)
);

CREATE TABLE email_submit_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES email_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    provider_profile VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(48) NOT NULL,
    error_category VARCHAR(120),
    provider_reference VARCHAR(255),
    observed_smtp_phase VARCHAR(64),
    CONSTRAINT uq_submit_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_email_attempt_by_message
    ON email_submit_attempt(message_key, started_at);
```

This is a reference schema and excludes full CHECK constraints, immutable audit events, encryption, soft/hard deletion, or partitioning.

### 15.1. Unique Business Keys Must Be Scoped

An example key:

```text
tenant-42 | order-paid | order-1001 | receipt-v1
```

Never use a global `order-1001` if tenants can have colliding IDs. The key must represent exactly "one logical notification" per business semantics.

### 15.2. Never Store Plaintext Payloads Indefinitely

`payload_reference` can point to encrypted object storage or a retention-bound template snapshot. Separate:
- data required for audits;
- content needed for short-window retries;
- data that must be deleted after processing;
- things that must never be logged (OTPs, passwords, raw credentials).

## 16. Claiming Jobs Safely Across Multiple Workers

If three pods poll one outbox table, never merely:
1. `SELECT ... status=PENDING`.
2. Send email.
3. `UPDATE status=SENT`.

Two workers can pick the same row.

A PostgreSQL approach:

```sql
WITH due AS (
    SELECT message_key
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
      AND (expires_at IS NULL OR expires_at > :now)
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE email_outbox e
SET status = 'SENDING',
    attempt_count = e.attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = :now
FROM due
WHERE e.message_key = due.message_key
RETURNING
    e.message_key,
    e.attempt_count,
    e.lease_token;
```

Run in a short transaction, insert the attempt record, and commit before calling SMTP.

### 16.1. Leases Are Insufficient to Conclude "Not Sent"

If a worker is killed after relay acceptance but before the DB update, the row remains `SENDING` and the lease expires. **Never reset all stale `SENDING` rows to `PENDING`** for retries; route through the recovery classifier and `UNKNOWN` when proof is absent.

### 16.2. Fencing Protects the Database, Not Recall SMTP

When recording accepted:

```sql
UPDATE email_outbox
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

A zero row count means the worker no longer owns that state. It does not prove whether the SMTP relay accepted or rejected the message.

### 16.3. Transactional Guarantees Must Be Stated Honestly

This design can:
- preserve durable queued jobs after commit;
- prevent concurrent duplicate claims;
- persist attempt history while the DB is available.

It **does not** guarantee generic SMTP exactly-once across all failures.

## 17. Reconciliation and the Question "Can We Prove It Was Sent?"

When an outcome is `UNKNOWN`, an organization can reconcile using:
- Provider submission/queue logs.
- Provider message lookup APIs.
- Authenticated webhooks.
- Self-operated SMTP relay logs.
- Provider-specific queue IDs or correlation references.
- Delivery events mapped back to the exact attempt.

**Not every provider offers sufficient lookup APIs**, and "no record found" can result from indexing lag or short retention.

### 17.1. Reconciliation Workflow

```text
UNKNOWN attempt
       |
       v
Gather attempt ID, provider, time window
       |
       v
Lookup provider evidence
       |
       +--> Confirmed accepted
       |          |
       |          v
       |     SMTP_ACCEPTED
       |
       +--> Confirmed non-accepted
       |          |
       |          v
       |     Retry / permanent policy
       |
       +--> No reliable conclusion
                  |
                  v
           UNRESOLVED / review
```

### 17.2. Manual Resends Must Be Audited

If you ultimately must resend without proving non-acceptance:
- record the approver;
- business rationale;
- email type;
- expected duplicate impact;
- link to prior attempts;
- consent and expiry status;
- new provider/route if changed.

Never label this a "safe retry." It is an **explicit duplicate-risk acceptance decision**.

## 18. Security Design via Threat Modeling

Security reviews do more than ask "is TLS enabled?" Inspect assets and trust boundaries:

```text
Authenticated user / internal service
             |
             v
Mail request API
    [authn, authz, tenant isolation]
             |
             v
Template renderer + business data
    [data minimization, encoding]
             |
             v
Outbox / object storage
    [encryption, access, retention]
             |
             v
Mail worker / secret store
    [least privilege, TLS, egress policy]
             |
             v
SMTP / email provider
    [vendor controls, verified domain]
             |
             v
Recipient mail ecosystem
    [untrusted destination, no full control]
```

Common threats:

| Threat | Example | Mitigation |
|---|---|---|
| Unauthorized sending | Endpoint acts as open relay | Authn/Authz, recipient rules, quotas |
| Secret exposure | SMTP password in repo/logs | Secret manager, rotation, redaction |
| Sender spoofing | Arbitrary `From` header | Verified sender registry, SPF/DKIM/DMARC |
| Tenant mixing | Tenant A uses Tenant B's template/data | Server-side context, row-level permissions |
| Content leakage | Logging full MIME/attachments | Data minimization, encryption, access controls |
| Email injection | Untrusted header containing CRLF | Validate recipients/headers, safe APIs |
| Template XSS/phishing | Unescaped untrusted fields | Context-aware escaping, approved templates |
| SSRF via attachments/URLs | Worker fetches caller-supplied URLs | Egress allowlists, fetch policies |
| Webhook replay | Adversary replays delivery event | Signatures, timestamps, event dedup |
| Denial of service | Bulk send overwhelms system | Rate/concurrency quotas, backpressure |
| Audit tampering | Operator edits/deletes history | Append-only controls, restricted writes, exports |
| Suppression bypass | Failover to another provider | Central suppression/consent |

Every risk needs an owner, control, test, and documented residual risk—not just "we picked a popular library."

## 19. Securing SMTP Transport and Authentication

A Spring Boot config for SMTP STARTTLS submission might look like:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

This is illustrative; endpoints/ports/credentials must follow your approved provider.

### 19.1. STARTTLS and Implicit TLS

- SMTP submission port **587** typically connects plain then upgrades via `STARTTLS`.
- Port **465** typically starts TLS immediately (implicit TLS); with `protocol=smtp`, `mail.smtp.ssl.enable=true` may be used.
- Port **25** usually relates to server-to-server relaying, not default app submission.

A right hostname with the wrong port/TLS mode causes handshake errors or timeouts. Never fix this by disabling TLS.

### 19.2. Hostname Verification

`mail.smtp.ssl.checkserveridentity=true` ensures the server hostname matches its certificate. Never use `mail.smtp.ssl.trust=*` in production to ignore CA/hostname problems.

### 19.3. Credentials

Depending on the provider, you may need:
- SMTP AUTH username/password;
- app passwords;
- OAuth2;
- client certificates/specific policies;
- IP allowlisting.

Never assume `spring.mail.username` must equal the `From` header; if they differ, the provider must authorize that verified sender.

### 19.4. Egress and Network Controls

Restrict outbound traffic to administrator-approved SMTP/provider endpoints. Never let callers specify arbitrary SMTP hostnames/ports, turning the service into an SSRF/tunneling vector.

## 20. Secret Management and Credential Lifecycle

Credential checklist:
- Never hardcode passwords/tokens in source code.
- Never put secrets in commits, stack traces, or metric labels.
- Fetch from a secret manager/protected config.
- Scope secret read permissions per workload.
- Rotate on schedule and after incidents.
- Support sender-profile rollover without mixing credentials.
- Separate development/staging/production environments.
- Restrict test credentials to SMTP sandboxes only.
- Consider auditing every secret access/rotation.
- Never leave protocol debug logging enabled indefinitely in production.

### 20.1. Least Privilege per Workload

A billing worker only needs secrets to send from the verified billing sender; it should not hold full provider API rights to delete audit logs, modify domain settings, or read all campaign recipients unnecessarily.

### 20.2. Rotation Must Preserve Compatibility

When rotating tokens/SMTP accounts:
1. Provision new credentials.
2. Verify sender/hostname/TLS permissions.
3. Drain in-flight attempts on the old profile if needed.
4. Switch sender routes by version.
5. Monitor AUTH errors.
6. Revoke old secrets per plan.

Never mutate a singleton `JavaMailSenderImpl` while multiple threads are sending concurrently.

## 21. Authorization: Who May Send What, to Whom?

An SMTP credential acts like "permission to send" at the provider level. If an application API lets any authenticated user call:
```text
POST /mail/send
to=<any-address>
from=<any-domain>
body=<any-content>
```
the application risks becoming a spam, phishing, or data-exfiltration tool.

### 21.1. Authenticate and Authorize on Business Actions

Instead of exposing raw SMTP primitives to clients, expose business use cases:

```text
POST /orders/{id}/send-receipt
POST /accounts/request-password-reset
POST /support/tickets/{id}/reply
```

The backend decides:
- which template is used;
- which sender profile is used;
- whether the recipient belongs to the business object;
- tenant scope;
- which data enters the template;
- rate limits/consent.

### 21.2. Never Derive Tenant from Email Headers

Incoming `From`, `Reply-To`, or custom headers are not authentication sources. Derive tenant from authenticated server-side context and data access permissions.

### 21.3. Recipient Validation Is More Than Syntax

Beyond address syntax checks:
- is the recipient authorized to receive this data?
- is the address verified where business rules require it?
- has the recipient opted out/been suppressed?
- is there risk of sending PII to a mistyped address?
- could `cc`/`bcc` leak details across customers?

Use a separate notification per recipient when isolation and granular tracking are required.

## 22. Email Content and Data Minimization

Emails cross external systems and can be forwarded, archived long-term, screenshotted, or downloaded. Never treat email as a fully controlled confidential storage channel.

### 22.1. Do Not Overstuff Bodies with Data

For an invoice alert:
- include reference code and minimal summary;
- provide an HTTPS link to an authenticated account page for full details;
- never send full financial records or sensitive info without business approval.

### 22.2. Verification Links and Tokens

For password resets:
- tokens must have strong entropy, short TTLs, and single-use semantics where required;
- never log raw URLs containing tokens;
- never generate tokens too early and send them after expiry;
- prevent scanners/prefetchers from triggering sensitive actions on HTTP GET alone;
- final business actions must enforce proper authentication/authorization.

### 22.3. Template Escaping

Untrusted HTML content can carry user-supplied input. Use a template engine with context-aware escaping; never concatenate raw input strings into HTML and pass them to `helper.setText(html, true)` unescaped.

### 22.4. Images and Tracking

Remote images can reveal IP addresses, open timestamps, and client behavior. Evaluate privacy policies, consent, and tracking reliability before embedding them.

## 23. Attachments, File Storage, and Data Classification

When sending attachments:
- decide whether bytes must be attached or an authenticated link suffices;
- bound file sizes and types;
- verify file read permissions by tenant and business object;
- scan for malware when sources are untrusted;
- never use user-supplied filenames as filesystem paths;
- never log attachment bytes;
- manage object-storage lifetimes;
- avoid sending files whose access was revoked.

### 23.1. Attachments Increase Risk and Cost

A 20 MB attachment can cause:
- substantial MIME/Base64 expansion;
- queue/backlog resource bloat;
- SMTP provider size-limit rejections;
- recipient-server rejections;
- log and backup bloat if storing raw content.

Translate "send any file" requests into concrete limits and policies.

### 23.2. Consider Signed Download Links

For access-controlled documents, a short-lived link to an authenticated page/file can be safer than attaching directly. Still, URLs risk forwarding, scanner fetches, or token leaks in logs. Design real authorization rather than assuming URL signing alone suffices.

## 24. Audit: What Must Be Provable?

An **audit trail** differs from **debug logs**. Audits answer:

- Who or which system requested sending?
- Which business event produced the logical email?
- Which data/template/version was approved?
- Which recipient and sender identity were resolved?
- Who had permission to change recipients, schedules, or templates?
- Which attempts executed, via which providers?
- Is there evidence of accepted/rejected/unknown outcomes?
- What delivery/bounce/complaint did the provider report?
- Who triggered retry/resend, and for what reason?
- How was audit data retained, deleted, or redacted?

A `logger.info("Email sent")` line lacking correlation and outcome semantics answers none of those questions.

### 24.1. Audit vs. Observability

| Property | Audit | Application Logging / Metrics |
|---|---|---|
| Purpose | Prove a decision or event | Debugging and operations |
| Unit | Business event, actor, command, attempt | Requests, exceptions, latencies |
| Immutability | Often needs append-only/tamper-evidence | Can rotate/aggregate |
| Retention | Per risk/policy/applicable law | Per operational need |
| Personal data | Minimum necessary | Redacted/aggregated |
| Access control | Restricted, access-audited | SRE/developers by role |
| Correlation | Business key, attempt ID, event ID | Trace/span IDs and labels |

### 24.2. Never Default to Raw Mail as the Audit Record

Storing complete email bodies and attachments forever in audit logs magnifies privacy risk and breach impact. Many questions only require:
- template ID/version;
- hash/snapshot reference per policy;
- message/attempt IDs;
- sender/recipient references;
- timestamps;
- verified provider responses;
- actor/reason.

If full content is genuinely mandatory for a process, enforce explicit justification, RBAC, encryption, and dedicated retention.

## 25. Append-Only Audit Event Model

You can add an audit event table decoupled from current outbox state:

```sql
CREATE TABLE email_audit_event (
    audit_id UUID PRIMARY KEY,
    message_key UUID NOT NULL,
    attempt_id UUID,
    tenant_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_reference VARCHAR(160),
    event_time TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    provider_reference VARCHAR(255),
    evidence_reference VARCHAR(512),
    reason_code VARCHAR(120),
    correlation_id VARCHAR(160),
    previous_event_hash VARCHAR(128),
    event_hash VARCHAR(128)
);

CREATE INDEX idx_email_audit_message
    ON email_audit_event(message_key, event_time);

CREATE INDEX idx_email_audit_attempt
    ON email_audit_event(attempt_id, event_time);
```

Example events:
- `MAIL_REQUESTED`.
- `OUTBOX_COMMITTED`.
- `MAIL_CLAIMED`.
- `SUBMISSION_STARTED`.
- `SMTP_ACCEPTED`.
- `SUBMISSION_OUTCOME_UNKNOWN`.
- `PROVIDER_DELIVERED`.
- `PROVIDER_BOUNCED`.
- `MANUAL_RESEND_APPROVED`.
- `MAIL_CANCELLED`.
- `AUDIT_ACCESS_GRANTED` or access events in a separate audit control system.

### 25.1. Audit Events Do Not Replace Business Transactions

To avoid missing audits after business commits, consider inserting audit events in the same local transaction as the outbox/business state. For external provider events, persist raw signed metadata/normalized events via a controlled pipeline.

### 25.2. Hash Chains Do Not Automatically Make a Database Immutable

`previous_event_hash` and `event_hash` columns only add value if the implementation actually:
- defines canonical serialization;
- enforces event ordering;
- hashes and verifies consistently;
- protects signing keys if used;
- writes anchors/checkpoints outside the local trust boundary;
- restricts update/delete privileges.

If a DBA can edit every row and recompute hashes without external anchors, a plain hash chain provides weak tamper evidence.

### 25.3. Audits May Require WORM or Immutable Storage

For strict audit mandates, evaluate append-only event stores, object storage versioning/Object Lock per policy, signed exports, or equivalent immutability controls. Never claim a regular database table is WORM just because the app lacks a DELETE endpoint.

## 26. Audit Events Need Explicit Timestamps and Provenance

Each event should record:
- `occurredAt`: when the source says the event happened.
- `observedAt`/`ingestedAt`: when the application received/recorded it.
- Source: application/provider/webhook/operator.
- Evidence reference.
- Provider/account/tenant correlation.
- Trust/verification status.

Example where a provider webhook arrives 30 minutes late:

```text
Provider deliveredAt: 09:01Z
App webhook ingestedAt: 09:31Z
```

Never overwrite both timestamps into a single `deliveredAt 09:31` if measuring delivery latency.

### 26.1. Clock Skew

Systems can suffer clock drift. Use UTC `Instant`s, time synchronization, and record timestamp sources. In disputes, audits must distinguish "source-reported time" from "absolute ground truth."

### 26.2. Event Ordering

Webhooks can arrive out of order. Never let a late `DEFERRED` event overwrite an already-confirmed `DELIVERED` state without enforcing state-transition rules.

### 26.3. Correlation IDs

Use:
- business event key;
- `messageKey`;
- `attemptId`;
- provider reference;
- webhook `eventId`;
- `traceId`.

Never collapse them all into a single ID because each has a distinct scope.

## 27. Privacy and Retention Must Be Architectural

"Keep audits for 7 years" cannot be answered uniformly across every organization and jurisdiction. Proper retention depends on:
- data category;
- processing purpose;
- contracts;
- applicable laws/regulations;
- legal obligations;
- records-governance policies.

**Legal/privacy/security teams must approve real retention schedules.** This article provides an engineering framework, not legal advice.

### 27.1. Separate Retention Across Layers

| Data | Purpose | Strategy |
|---|---|---|
| Raw MIME/attachments | Short-term retries, specialized investigations | Restricted, encrypted, deleted per policy |
| Outbox jobs | Execution state | Retained through retry/recovery windows |
| Attempt history | Debugging and submission audits | Retain metadata by risk tier |
| Provider delivery events | Delivery and complaints | Minimal data and provenance |
| Consent/suppression | Avoid emailing opted-out users | Per rights and purpose policies |
| Aggregate metrics | SLOs/capacity planning | Aggregated, minimizing PII |
| Immutable audit | Mandatory evidence | Approved retention/access controls |

### 27.2. Right to Erasure vs. Obligation to Retain Evidence

A data-deletion request can conflict with record-keeping obligations. Build mechanisms to evaluate each data type and legal basis—neither blindly wiping all logs/consent nor keeping everything forever.

### 27.3. Distinguish Suppression from Marketing Profiles

When a user unsubscribes, the system may need a minimal suppression record to avoid mailing them again. It does not necessarily need to keep their full profile or campaign content.

### 27.4. Encryption and Access Controls

- Encryption at rest matched to sensitivity.
- Access controls on DB/object stores.
- KMS/key rotation.
- Backups aligned with retention.
- Audits on sensitive-data access.
- Redaction/pseudonymization in logs.
- Never export production dumps to laptops or test environments.

## 28. Data Residency, Vendors, and Contractual Responsibilities

If emails carry classified data:
- Does the provider store MIME/bodies and attachments?
- In which region and for how long?
- Is data transferred to subprocessors?
- Can provider support staff access content?
- Is a Data Processing Agreement required?
- Within what window are deletion/export rights fulfilled?
- What PII can appear in provider logs/webhooks?
- Does international email routing traverse uncontrolled relays?

You cannot guarantee "data never leaves the country" solely because the app and DB live in one region; outbound email enters an external ecosystem spanning multiple servers. Document boundaries explicitly and evaluate against real policy.

### 28.1. Data Processing Agreements and Compliance Evidence

For selected vendors, have legal/security review official documentation, certifications, scopes, and validity dates. Never treat marketing-page compliance badges as proof that every deployed config is compliant.

### 28.2. Shared Responsibility

Even when a provider offers TLS and audit logs, the application still owns:
- picking authorized recipients;
- protecting API keys;
- excluding prohibited data;
- handling unsubscribes;
- verifying webhooks;
- enforcing audit RBAC;
- deleting internal data per policy.

## 29. Spring Boot Design: Layering Responsibilities

A controllable architecture:

```text
Application use case
  └─ MailRequestService
       ├─ authorization / consent / templates
       ├─ outbox transaction
       └─ audit MAIL_REQUESTED

DueMailDispatcher
  ├─ atomic claim / lease / attempt
  ├─ MailContentRenderer
  ├─ OutboundMailPort
  │    ├─ SpringSmtpAdapter(JavaMailSender)
  │    └─ ProviderHttpApiAdapter(optional)
  ├─ outcome classifier
  └─ audit outcome events

ProviderEventEndpoint
  ├─ signature verification
  ├─ event idempotency
  └─ delivery status projection

Operations
  ├─ metrics / alerts
  ├─ reconciliation
  ├─ admin audit
  └─ maintenance pause/drain
```

### 29.1. Application Layer Stays Independent of SMTP Details

Example port:

```java
package com.example.mail.domain;

import java.util.UUID;

public interface OutboundMailPort {
    SubmissionResult submit(MailSubmission submission);
}

public record MailSubmission(
    UUID messageKey,
    UUID attemptId,
    String senderProfile,
    String recipient,
    String subject,
    String plainText,
    String htmlText
) {}

public enum SubmissionStatus {
    SMTP_ACCEPTED,
    PROVEN_NOT_ACCEPTED_RETRYABLE,
    PROVEN_NOT_ACCEPTED_PERMANENT,
    UNKNOWN
}

public record SubmissionResult(
    UUID attemptId,
    SubmissionStatus status,
    String providerReference,
    String safeReasonCode
) {}
```

These types are application models, not built-in Spring Mail APIs.

### 29.2. SMTP Adapter Using JavaMailSender

```java
package com.example.mail.adapters;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringSmtpAdapter
        implements OutboundMailPort {

    private final JavaMailSender sender;

    public SpringSmtpAdapter(JavaMailSender sender) {
        this.sender = sender;
    }

    @Override
    public SubmissionResult submit(MailSubmission command) {
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(
                command.plainText(),
                command.htmlText()
            );

            message.setHeader(
                "X-Application-Message-Key",
                command.messageKey().toString()
            );

        } catch (MessagingException ex) {
            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.PROVEN_NOT_ACCEPTED_PERMANENT,
                null,
                "MIME_PREPARATION_ERROR"
            );
        }

        try {
            sender.send(message);

            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.SMTP_ACCEPTED,
                null,
                null
            );
        } catch (MailException ex) {
            // JavaMailSender abstraction does not always expose
            // exact SMTP phase evidence.
            // Never assume every exception = safe retry.
            return new SubmissionResult(
                command.attemptId(),
                SubmissionStatus.UNKNOWN,
                null,
                "SUBMISSION_RESULT_NOT_CONFIRMED"
            );
        }
    }
}
```

This example is intentionally **conservative**: lacking reliable SMTP phase evidence, exceptions from `send` map to `UNKNOWN`. In production:
- never hardcode `From`; resolve verified identity from the sender profile;
- never let arbitrary recipients bypass authorization;
- use a vetted template renderer;
- distinguish pre-network message build errors from submission errors;
- capture provider references where the adapter truly receives them;
- persist states/audits transactionally in the orchestration layer.

Do not cram every decision into the adapter; the mail worker must persist outcomes and manage retries/`UNKNOWN`.

## 30. Application-Layer Auditing: Illustrative Service

An audit interface separating concerns:

```java
public interface MailAuditSink {
    void append(MailAuditEvent event);
}

public record MailAuditEvent(
    String messageKey,
    String attemptId,
    String tenantId,
    String eventType,
    String actorReference,
    java.time.Instant eventTime,
    String reasonCode
) {}
```

Inside a business transaction:

```java
@Transactional
public MailRequestReceipt requestReceipt(
        PaymentCompletedEvent event) {

    authorization.checkCanNotify(event);
    String businessKey = businessKeys.forPayment(event);

    EmailOutboxRow row =
        outbox.insertIfAbsent(businessKey, event);

    audit.append(new MailAuditEvent(
        row.messageKey(),
        null,
        event.tenantId(),
        "MAIL_REQUESTED",
        "payment-service",
        clock.instant(),
        null
    ));

    return new MailRequestReceipt(row.messageKey());
}
```

`PaymentCompletedEvent`, repositories, and `MailRequestReceipt` are application-defined types. Implement `insertIfAbsent` via a unique constraint/transaction, not an unlocked `SELECT`-then-`INSERT`.

### 30.1. Avoid "Audit Calls" Outside Transactions That Can Drop

If the outbox insert commits while an audit call to an external network service fails, audit events go missing. Depending on requirements:
- insert the audit event inside the same transaction;
- or write an audit outbox event for durable publishing;
- or design reconciliation.

### 30.2. Audit Appends Must Match "What Actually Happened"

Never record `SMTP_ACCEPTED` before evidence arrives. Never record `DELIVERED` merely because the worker threw no exception.

## 31. Evaluating Schedules, Timezones, and Deadlines

If the product needs scheduled emails, additional requirements apply:

- `sendAt` represents an absolute instant.
- `ZoneId` for local-time or recurring schedules.
- DST gap/overlap policy.
- Cancellation/rescheduling.
- Expiration of OTPs/reset links/promotions.
- Catch-up after downtime.
- Durable schedule definitions and occurrences.
- Unique keys per recurrence.
- Quotas/rates when backlogs build up after maintenance.

### 31.1. Never Use Thread.sleep for Long Schedules

```java
Thread.sleep(millisUntilSend);
mailSender.send(message);
```

cannot survive restarts and ties up threads uselessly. Persist scheduled jobs and use a due-job dispatcher.

### 31.2. Never Equate "Due" with "Delivered"

Scheduling SLOs must distinguish:
- `sendAt`: must not send before this time;
- `claimedAt`: worker started processing;
- `smtpAcceptedAt`: relay accepted;
- `deliveredAt`: provider/recipient confirmed per their semantics.

### 31.3. Time Across Multiple Systems

Use `Instant`/UTC for technical timestamps, `ZoneId` for user intent, and an injected `Clock` for testing. Never rely on `ZoneId.systemDefault()` when schedules belong to a recipient's timezone.

## 32. Designing Queues, Backpressure, and Capacity

A requirement to "send 1 million emails in one hour" cannot be met by raising `maxMessagesPerPoll` without checking provider quotas.

Parameters:
- average/peak requests per second;
- MIME/attachment sizes;
- max concurrent SMTP connections;
- provider accepted rate;
- per-domain throttling;
- queue capacity;
- retry budget;
- consumer count;
- email category priorities;
- tenant isolation.

### 32.1. Calculate Throughput from the Bottleneck

For example, if the provider allows only 20 submissions/second, one million emails need at least ~50,000 seconds at that ceiling, excluding retries and overhead. You cannot guarantee finishing in one hour by spawning 100 more workers while upstream quota stays fixed.

### 32.2. In-Memory QueueChannel Is Not Durable

In Spring Integration, a default `QueueChannel` can be an in-memory queue. For durability, pair it with a persistent `MessageStore`/broker or an outbox. When the queue fills, producers must receive backpressure rather than silently dropping jobs.

### 32.3. Concurrency and Rate Are Different Limits

- Concurrency: how many sends run simultaneously?
- Rate: how many sends per second/minute?
- Capacity: how many waiting jobs can be stored?
- Retry budget: how many times may one job retry?

A single poller interval cannot replace all four.

## 33. Multi-Tenant Architecture and Blast Radius

An organization with multiple tenants/campaigns must address:
- verified sender domains per tenant;
- credential/SMTP account isolation;
- quota and reputation isolation;
- outbox tenant keys;
- template/data isolation;
- webhook correlation per provider account;
- audit access controls;
- retention by data class;
- route failover policies.

### 33.1. Is One Shared Credential Enough?

A shared provider account can work if all sender identities are verified and access is controlled. However, shared accounts carry risks:
- one tenant sending spam hurts reputation for many tenants;
- shared quotas get monopolized;
- logs and provider events are harder to separate;
- compromise has a wider blast radius.

Balance isolation against account/domain costs and operational overhead.

### 33.2. Never Let Failover Cross Authorization Boundaries

If provider A fails, switching to provider B is valid only when:
- the domain is verified on B;
- data is permitted to process through B;
- suppression still applies;
- B has sufficient quota;
- no `UNKNOWN` on A is blindly resent;
- routing decisions are audited.

## 34. Monitoring and Alerts Serving All Three Requirement Groups

Suggested metrics table:

| Metric | Group | What It Reveals |
|---|---|---|
| `mail_outbox_pending_count` | Delivery | How many requests are still waiting? |
| `mail_oldest_due_age_seconds` | Delivery | How overdue is the oldest email? |
| `mail_smtp_submission_latency_seconds` | Delivery | How slow is relay acceptance? |
| `mail_smtp_outcomes_total{status}` | Delivery | Accepted, rejected, unknown? |
| `mail_provider_delivery_events_total{type}` | Delivery | Delivered, bounced, complained? |
| `mail_unknown_attempt_count` | Delivery/Audit | Uncertain attempts? |
| `mail_reconciliation_lag_seconds` | Audit | How long have `UNKNOWN`s remained unresolved? |
| `mail_webhook_signature_failures_total` | Security | Invalid callbacks arriving? |
| `mail_unauthorized_send_attempts_total` | Security | Unauthorized send attempts occurring? |
| `mail_suppression_blocked_total` | Security/Delivery | Blocking sends against consent? |
| `mail_audit_append_failures_total` | Audit | Risk of missing evidence? |
| `mail_provider_rate_limited_total` | Delivery | Quota/provider throttling? |

### 34.1. Metric Labels Must Control Cardinality

Never put email addresses, `messageKey`, `attemptId`, or arbitrary raw tenant IDs in labels. Keep `provider`/`profile`/`category`/`outcome` within controlled sets; detailed IDs belong in access-controlled logs and audit stores.

### 34.2. Alerts Must Be Actionable

Examples:
- Sudden `UNKNOWN` spike → pause auto-retries and inspect relay/network.
- Backlog exceeds SLA → inspect workers/quotas.
- Rising DMARC failure rate → inspect provider/domain alignment.
- Audit append errors → trigger evidence-protection/incident procedure.
- Rising complaints → pause campaign, check consent/suppression.

### 34.3. Avoid Long-Term Full SMTP Transcript Logging

Protocol debug logs can expose headers, recipient metadata, or credentials in some environments. Enable only inside controlled windows, with redaction and strict access controls.

## 35. Evaluating RTO, RPO, and Continuity

A critical email solution needs plans for:
- database unavailability;
- SMTP provider outages;
- failed secret rotations;
- delayed webhook delivery;
- worker cluster restarts;
- regional unavailability.

### 35.1. RPO and What Data Is Protected

**RPO** sets the maximum tolerable data loss in a disaster. Even if the outbox persists to a DB, long backup/replication RPOs still risk losing email jobs during a regional failure.

Evaluate the whole chain:
- business transactions;
- outbox;
- attempt/audit events;
- queues;
- provider references;
- backups and cross-region replication where permitted.

### 35.2. RTO and Post-Recovery Handling

**RTO** is the service recovery target. Once the system returns:
- unexpired jobs drain within quotas;
- stale `SENDING` jobs go to reconciliation;
- `UNKNOWN` jobs are not bulk-resent;
- recurring schedules materialize catch-up runs per policy;
- expired tokens are not sent.

Application RTO does not equate to recipient delivery SLA.

### 35.3. Failover Is Not Always Safe

Provider A timing out after DATA may have accepted the message. Switching straight to provider B creates duplicates. Failover policies require evidence, permissions, domain auth, and route-level audits.

## 36. Testing Around Delivery Requirements

Tests should verify **evidence and boundaries**, not just "send threw no exception."

### 36.1. Unit Tests

- Unique business event produces one outbox row.
- Scheduler skips jobs prior to `sendAt`.
- `EXPIRED` jobs never submit.
- Provider route is selected accurately.
- Suppressed recipients are never emailed.
- `UNKNOWN` outcomes never auto-retry.
- Status transitions never jump from `REQUESTED` straight to `DELIVERED` merely because a worker ran.
- Audit events record only evidenced outcomes.

### 36.2. Integration Tests with an SMTP Sandbox

- STARTTLS/implicit TLS modes match config.
- Valid sender and recipients.
- Plain+HTML+attachment MIME correctness.
- Permanent SMTP rejections.
- Temporary SMTP rejections.
- Authentication failures.
- Socket timeouts.
- Certificate hostname mismatches.
- Provider returns accepted; outbox updates properly.
- Provider accepts then worker DB update fails.

### 36.3. Fault Injection After DATA

This test is especially critical:

```text
Fake relay receives full DATA
        |
        v
Fake relay stores message
        |
        v
Final 250 response is dropped
        |
        v
JavaMailSender throws timeout
        |
        v
Application marks UNKNOWN
        |
        v
Next poll MUST NOT automatically resubmit
```

This directly proves the workflow does not turn an unconfirmed timeout into a duplicate.

### 36.4. Multi-Instance Tests

Two workers claim due jobs concurrently:
- only one claim transaction wins;
- stale worker cannot overwrite state after lease token changes;
- restarts do not create a second logical job;
- stale-lease recovery never resends `UNKNOWN`.

## 37. Security and Privacy Testing

Minimum test cases:

| Test | Expected Result |
|---|---|
| SMTP certificate hostname mismatch | Connection rejected |
| Missing secret at startup | Never falls back to empty/unsafe credentials |
| Tenant A tries to send Tenant B's data | Denied and audited |
| User injects CRLF into header-like input | No header injection occurs |
| Template receives user-entered HTML | Escaped properly for context |
| Disallowed attachment | Rejected |
| Unsubscribed recipient | No marketing email submitted |
| Missing/expired webhook signature | Rejected |
| Replayed webhook with same `eventId` | No duplicate state transition |
| SMTP incident logs | Contain no passwords/tokens/raw MIME |
| Unauthorized user reads audit | Denied and access-logged |
| Mail creation exceeds quota | Throttled/backpressured |
| Provider failover | Never bypasses consent/tenant/`UNKNOWN` |

### 37.1. SAST/DAST Do Not Replace Business Authorization Tests

Static analysis catches hardcoded secrets or common flaws, yet struggles to verify whether a recipient belongs to the right order/tenant. Write tests aligned with real use cases and trust boundaries.

### 37.2. Evaluating Third-Party Dependencies

Spring Mail relies on Jakarta Mail providers and other libraries. Per organizational policy, manage SBOMs, vulnerability scans, licenses, patch cadence, and behavioral changes across upgrades.

## 38. Testing Audit Completeness and Reliability

Audits must be tested under failure modes:

1. Business transaction commits and audit event is created.
2. Business transaction rolls back → no "successfully requested" audit evidence exists.
3. SMTP accepted yet outcome DB update fails → record flagged for reconciliation.
4. Duplicate provider webhooks → only one normalized event effect per policy.
5. Out-of-order provider webhooks → never overwrite valid newer states.
6. Audit store temporarily down → buffered/recovered or fail-closed per risk tier.
7. Operator manual resend → actor, reason, approval, and attempt link recorded.
8. Template version changes → exact version used remains traceable.
9. Data retention job runs → deletes/redacts per policy without deleting records under legal hold.
10. Backup restore → audit sequences/correlations remain usable.

### 38.1. Tamper-Evidence Tests

When using hash chains/signed exports:
- modify an older event in a test store;
- verify detection tooling catches the integrity mismatch;
- verify independent anchors;
- verify no single actor can alter both evidence and anchor.

### 38.2. Do Not Equate Log Retention with Compliance

30-day log rotation neither satisfies a 1-year or 7-year evidentiary duty nor justifies keeping all PII in logs that long. Maintain an approved data classification and retention matrix.

## 39. Scoring Architectural Options

A decision matrix makes trade-offs explicit rather than choosing by gut feel. Example 1–5 scores and weights are purely illustrative.

| Criterion | Example Weight | Direct SMTP | SMTP + Outbox | Provider API + Outbox |
|---|---:|---:|---:|---:|
| Zero lost requests after restart | 5 | 1 | 4 | 4 |
| Submission/delivery observability | 5 | 2 | 3 | 4 |
| `UNKNOWN` handling and attempt audits | 5 | 1 | 4 | 4 |
| Low initial implementation cost | 2 | 5 | 3 | 2 |
| Provider portability | 3 | 4 | 3 | 2 |
| Self-built security/tenant controls | 5 | 2 | 4 | 4 |
| Low operational burden | 3 | 3 | 3 | 4 |
| Data/content control | 4 | 3 | 3 | 3 |

**These scores are neither vendor ratings nor empirical benchmarks.** They illustrate how a team fills out scores after gathering evidence on concrete options.

### 39.1. Scoring Process

1. Derive criteria from business requirements.
2. Separate **hard gates** from soft trade-offs.
3. Assign weights jointly with business/security/operations.
4. Score using PoCs, contracts, and tests.
5. Cite evidence sources.
6. Compute weighted totals where helpful.
7. Document risk acceptances and unknowns.
8. Sign off the ADR with approvers.

### 39.2. High Scores Cannot Compensate for Failing a Hard Gate

If mandatory policy requires processing data within an approved boundary, an option violating that rule cannot win merely for being cheap or having a pleasant API.

Example hard gates:
- Mandatory TLS with hostname verification.
- Tenant isolation.
- Policy-compliant retention/deletion.
- Domain ownership/verified senders.
- Ability to export mandatory audit evidence.
- Prohibition on storing unauthorized sensitive tokens.

### 39.3. Total Cost of Ownership

Beyond provider fees:
- developer implementation effort;
- monitoring/on-call burden;
- domain warm-up and reputation;
- compliance/security reviews;
- integration testing;
- incident response;
- backups/audit retention;
- provider migrations;
- training/documentation.

Low PoC cost can quickly turn into high operational cost.

## 40. Sample Architecture Decision Record (ADR)

An ADR should explain **why one option was chosen** and **why others were rejected**.

```markdown
# ADR-001: Transactional email architecture

## Status
Accepted / Proposed / Superseded

## Context
- Payment events must trigger email receipts after DB commit.
- API must not wait on SMTP.
- Must not auto-retry if submission outcome is UNKNOWN.
- Audit chain required from order -> message -> attempt.

## Options
A. Direct send via JavaMailSender inside HTTP request.
B. JavaMailSender via transactional outbox.
C. Provider HTTP API via transactional outbox.

## Decision
Select B for the current phase because ...
Keep OutboundMailPort abstraction to support C if needed.

## Guarantees
- Outbox preserves committed requests within DB durability bounds.
- Attempt history and retry policies in place.
- Does not claim exactly-once SMTP or delivery.

## Residual Risks
- UNKNOWN when final SMTP reply is lost.
- Provider outages and delivery deferrals.
- Dependency on DNS/reputation.

## Evidence
- Integration tests: ...
- Threat review: ...
- Provider documentation: ...
- SLO dashboard: ...

## Approvers
Business owner / Security / Engineering / Operations

## Review Date
...
```

Replace `...` placeholders with real details; an ADR must never stop at "using Spring Mail because it is easy."

## 41. Pre-Production Approval Workflow

<escape>**</escape>Phase 1 — Discovery:
- identify email types, volumes, PII, deadlines;
- interview owners;
- assign requirement IDs and draw data-flow diagrams.

Phase 2 — Architecture:
- pick SMTP/API, providers, queues/outboxes;
- run threat modeling and failure analysis;
- design state machines and audits;
- define trust boundaries.

Phase 3 — Evidence:
- measure PoC throughput;
- test TLS and DNS/auth;
- fault-inject `UNKNOWN`;
- verify webhook signatures;
- test restarts/DB failures;
- verify retention.

Phase 4 — Approval:
- business SLOs and error budgets;
- security/privacy sign-off;
- operations runbooks;
- vendor/compliance review;
- ADR/risk register.

Phase 5 — Rollout:
- canary provider/profile;
- bound concurrency;
- monitoring/alerts;
- incident rehearsals;
- rollback/failover policies;
- post-cycle operational review.

**Never treat "one test email succeeded" as an architecture safety certification.**

## 42. Applied Example: Payment Receipts

### 42.1. Requirements

- Payment state is the source of truth, independent of email.
- Once payment commits, the email request persists in the same transaction.
- Idempotency key per tenant/payment/receipt type.
- Never auto-duplicate if SMTP outcome is `UNKNOWN`.
- Content excludes unnecessary payment-card data.
- Template version, recipient, and submission attempts remain traceable.
- If the provider rejects/times out, operators have evidence to act.
- Retention complies with approved records and privacy policies.

### 42.2. Suggested Architecture

```text
Payment DB transaction
  ├─ settle payment
  ├─ insert email_outbox
  └─ append MAIL_REQUESTED audit
             |
             v
Due dispatcher + claim
             |
             v
Renderer + verified sender profile
             |
             v
Spring JavaMailSender / provider
             |
             v
Submit outcome / UNKNOWN handling
             |
             v
Provider events / audit
```

### 42.3. What Must Not Be Promised

- Cannot guarantee the recipient read the receipt.
- Cannot promise generic SMTP exactly-once across all network failures.
- Cannot dump full payment records into email bodies.
- Cannot claim success based solely on in-memory enqueueing.

## 43. Applied Example: Verification and Password-Reset Emails

Requirements differ from receipts:

- Short TTLs.
- Single-use tokens.
- Never log tokens/links.
- Rate limits per account/IP/tenant.
- API responses never reveal whether an email exists.
- Never send expired emails when draining backlogs after downtime.
- Links never trigger sensitive actions on prefetch alone.
- On `UNKNOWN`, prefer prompting the user to start a fresh flow rather than resending an old token.
- Audits log appropriate metadata only, never long-lived plaintext tokens.

### 43.1. Fast Submission Differs from Guaranteed Inbox Arrival

A provider with low SMTP latency still does not control recipient mailbox filters. Product UX may need rate-limited token re-request UIs rather than assuming absolute deliverability.

### 43.2. Prevent Unintended Parallel Valid Tokens

If a user retries repeatedly, token rotation/invalidation rules must be explicit. Duplicate emails must never weaken authentication-layer protections.

## 44. Applied Example: Marketing Campaigns

This involves a distinct requirement set:
- Consent and unsubscribes.
- Suppression/hard bounces/complaints.
- Quotas/rate limits and reputation.
- Separate senders/domains/profiles.
- Respect quiet hours/timezones.
- Guard against duplicate campaigns.
- Never backfill expired campaigns after downtime.
- Privacy/tracking policies.
- Ability to halt campaigns and drain active attempts.

### 44.1. Stopping Marketing Must Not Disrupt Transactional Mail

A shared provider account can let marketing complaint spikes harm receipts. Use route isolation and separate quotas per policy.

### 44.2. Marketing Metrics Differ from Transactional Email

Marketing typically tracks suppression, complaints, bounces, and conversions—yet open tracking must never be treated as proof a human actually read the email.

## 45. RACI and Operational Ownership

Well-governed systems have clear ownership:

| Stakeholder | Typical Role |
|---|---|
| Business owner | Accepts loss/duplicate risk levels, deadlines, SLAs |
| Engineering | Designs state machines, outboxes, adapters, tests |
| Security | Threat models, secrets, TLS, RBAC, hardening |
| Privacy/Legal | Data classification, retention, vendor obligations |
| SRE/Operations | Monitoring, backups, incidents, provider routing |
| Marketing/Customer Ops | Consent, suppression, complaint workflows |
| Provider/Vendor | SMTP/API service, logs/webhooks per contract |
| Audit/Compliance | Evidence criteria and audit procedures |

No single role should unilaterally decide requirements affecting personal data, legal obligations, or organizational sending authority.

## 46. Dangerous Misconceptions

| Misconception | Accurate Explanation |
|---|---|
| "Spring Mail can send, so we're done" | Delivery, security, audit requirements, and operations are still needed |
| "`send()` threw no error, so it's in the Inbox" | Usually reflects submission success only |
| "SMTP timeout means unsent" | The relay may have accepted before the reply dropped |
| "Adding `RetryTemplate` prevents loss" | Can cause duplicates without `UNKNOWN` handling |
| "Outbox guarantees exactly-once" | Outboxes do not make SMTP atomic |
| "SPF/DKIM/DMARC guarantees delivery" | They are important authentication signals, not guarantees |
| "TLS is all the security we need" | Authorization, secrets, content, privacy, and logs still matter |
| "Provider webhooks are 100% trustworthy" | Must verify, deduplicate, and handle out-of-order delivery |
| "`Message-ID` makes relays deduplicate" | Generic SMTP makes no such promise |
| "Keeping raw emails forever is good auditing" | Increases data exposure and unnecessary retention risk |
| "A hash column in the DB means immutable" | Needs chaining/external anchors/access restrictions |
| "Provider has compliance badge, so app is compliant" | Shared responsibility; config and data flows still apply |
| "Failover always raises reliability" | `UNKNOWN` + failover can double submissions |
| "Delivered means the recipient read it" | Delivery events do not prove reading |
| "No need to split transactional and marketing" | Consent, reputation, deadlines, and policies differ |
| "System runs UTC so `ZoneId` is unnecessary" | Local-time schedules still require timezone rules |

## 47. Pre-Decision Assessment Checklist

### 47.1. Delivery

- [ ] Email types classified with loss/duplicate impacts defined.
- [ ] Clear state machine separating accepted from delivered.
- [ ] Measurable SLIs/SLOs with approved denominators.
- [ ] Durable outbox/queue where business requires.
- [ ] Unique business keys/idempotency enforced.
- [ ] SMTP `UNKNOWN` never auto-retried.
- [ ] Retry budgets/backoff/deadlines configured.
- [ ] Provider events and reconciliation in place.
- [ ] Concurrency/rate/queue capacity bounded.
- [ ] Restart/region outage/catch-up plans documented.
- [ ] Per-recipient outcomes handled where needed.

### 47.2. Security

- [ ] SMTP/API connects with proper TLS mode and hostname verification.
- [ ] Credentials/secrets stored outside source with least privilege.
- [ ] Senders/domains verified with SPF/DKIM/DMARC aligned.
- [ ] Recipient/tenant authorization explicit.
- [ ] No open relay or arbitrary SMTP destination allowed.
- [ ] Template escaping/HTML and CRLF header defenses verified.
- [ ] PII/tokens/attachments minimized and protected.
- [ ] Suppression and consent checked prior to sending.
- [ ] Webhooks authenticated and replay-protected.
- [ ] Multi-provider failover never bypasses authorization.
- [ ] Threat model and security tests completed.

### 47.3. Audit

- [ ] Traceable from business event → job → attempt → provider event.
- [ ] Every audit event carries actor/source/time/provenance.
- [ ] `UNKNOWN` states and manual action audits implemented.
- [ ] Template/version or content references preserved properly.
- [ ] Immutability/tamper-evidence policies implemented if required.
- [ ] Retention/deletion/backups approved.
- [ ] Unnecessary bodies/secrets omitted from storage/logs.
- [ ] Audit access restricted and logged.
- [ ] Evidence exportable under authorization.
- [ ] Audit pipeline failure modes tested.

### 47.4. Architectural Decision

- [ ] Evaluated SMTP, provider API, and internal relay options.
- [ ] Recorded hard gates and trade-offs.
- [ ] Executed PoCs/integration tests for major risks.
- [ ] Evaluated TCO and vendor dependencies.
- [ ] Completed ADR and risk acceptances.
- [ ] Assigned owners and incident runbooks.
- [ ] Prepared canary/rollback plans.
- [ ] Explicitly documented what the system **does not guarantee**.

## 48. Practice Exercises

### Exercise 1 — Write Measurable Requirements

A team states "invoice emails must be reliable." Write at least 6 requirements with IDs, owners, acceptance tests, and separation between request durability and delivery.

### Exercise 2 — Classify Emails

Categorize OTPs, invoices, weekly reports, and marketing emails by: deadline, sensitivity, omission risk, duplicate risk, and retention.

### Exercise 3 — Draw Delivery Boundaries

Diagram Spring service → outbox → worker → SMTP relay → recipient server. Mark where `SMTP_ACCEPTED` and `DELIVERED` are observable, and where Inbox placement cannot be confirmed.

### Exercise 4 — State Machine

Design a state machine with `PENDING`, `SENDING`, `SMTP_ACCEPTED`, `RETRY_WAIT`, `UNKNOWN`, and `BOUNCED`. Write transition rules preventing `UNKNOWN` from reverting directly to `PENDING`.

### Exercise 5 — SLIs and Denominators

Define the SLI "99% of transactional emails accepted within 2 minutes." Clarify the denominator, canceled/expired jobs, missing timestamps, and provider outages.

### Exercise 6 — Choose an Architecture

Compare direct `JavaMailSender`, an in-memory queue, and a transactional outbox for an e-commerce platform. State hard gates and an explained decision.

### Exercise 7 — SMTP vs. HTTP API

Build a comparison matrix between two hypothetical providers: SMTP-only vs. HTTP API with idempotency + webhooks. Identify contract items to verify before scoring.

### Exercise 8 — Design an Outbox

Write schemas for `email_outbox` and `email_submit_attempt` with unique business keys, leases/fencing, retries, and provider references.

### Exercise 9 — UNKNOWN After DATA

Simulate a relay receiving complete DATA and dropping the final 250. Test that the client times out, marks `UNKNOWN`, and does not auto-resubmit.

### Exercise 10 — Crash After Acceptance

A worker receives 250 yet fails to update the DB. Design recovery that avoids resetting stale `SENDING` to `PENDING` and includes reconciliation.

### Exercise 11 — Domain Authentication

Given `From` header `billing@example.com`, vendor-domain `Return-Path`, and DKIM `d=vendor.net`, analyze whether SPF/DKIM passes guarantee DMARC alignment.

### Exercise 12 — Threat Model

An endpoint lets users enter arbitrary `From`/`To`/HTML. Build a threat table covering open relay, phishing, CRLF injection, cross-tenant leaks, and XSS/phishing content.

### Exercise 13 — Secret Rotation

Design an SMTP credential rotation procedure with 50 active workers, ensuring no secret logging and no mutable shared sender across tenants.

### Exercise 14 — Webhook Security

A provider sends out-of-order and duplicate delivered/bounce events. Design signature verification, event deduplication, and state transitions.

### Exercise 15 — Audit Trail

Starting from business event `order-paid`, design audit events for outbox commit, attempt, SMTP accepted, webhook delivered, and manual resend. Specify required evidence per event.

### Exercise 16 — Retention Matrix

Differentiate retention for raw MIME, attachments, outbox rows, attempt metadata, provider events, and consent/suppression. Explain which fields need privacy/legal approval.

### Exercise 17 — Tamper-Evident Audits

Design hash-chained events with an independent anchor. Describe a history-tampering test to verify change detection.

### Exercise 18 — Multi-Tenant Failover

Provider A times out after DATA; Tenant A wants immediate failover to provider B. Analyze `UNKNOWN`, domain verification, permissions, consent, and audits before deciding.

### Exercise 19 — Disaster Recovery

After a 2-hour outage, 10,000 jobs are backlogged and 500 are stale `SENDING`. Design recovery, backpressure, expired-job handling, reconciliation, and canary resume.

### Exercise 20 — Architecture Decision Record

Draft an ADR choosing between SMTP + outbox and provider API + outbox. Include requirements, hard gates, costs, risks, test evidence, owner, and review date.

## 49. Summary

**Evaluating delivery, security, and audit requirements** is mandatory before finalizing an email architecture for Spring Framework Mail applications carrying real business risk.

Key conclusions:

1. **Start from business consequences**, not Maven/Gradle dependencies or lines of code.
2. **Define delivery boundaries**: queued, SMTP accepted, delivered, and opened are distinct events with distinct evidence.
3. **Write measurable, testable requirements** for latency, error rates, retries, deadlines, privacy, and traceability.
4. **Transactional outboxes** preserve requests across restarts and tie emails to business transactions, yet do not make SMTP exactly-once.
5. **`UNKNOWN` must be a first-class state** when the server may have accepted while the client lost the response; blind retries create duplicates.
6. **Deliverability** requires verified `From`, SPF/DKIM/DMARC alignment, reputation, bounce/complaint handling, and suppression.
7. **Security** covers proper TLS, secret management, authorization, tenant isolation, content controls, and attachment safety—not merely enabling STARTTLS.
8. **Auditing** requires events with actors, correlation, provenance, and evidence—not keeping raw MIME or debug logs forever.
9. **Privacy, retention, and vendor obligations** must be evaluated against real data and regulations rather than inferred from vendor badges.
10. **SMTP relays, provider APIs, and outboxes** each carry trade-offs; choose using hard gates, PoCs, tests, TCO, and ADRs.
11. **Operations require owners, SLOs/metrics, reconciliation, incident runbooks, and disaster recovery**, not stopping at one successful test email.
12. **Unprovable guarantees must be documented explicitly as residual risks** rather than promising "guaranteed delivery, zero duplicates, always Inbox."

A mature email architecture is not the one with the most components, but the one that **meets its required commitments, protects data, preserves evidence, and explains honestly what happened when networks or providers fail**.
