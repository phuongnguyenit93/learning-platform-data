# Choosing Retries in the Application vs. in the Delivery Platform

In Spring Framework Mail, an architectural question surfaces early when building production systems: **when sending an email fails, should the application retry itself or let the SMTP relay/Email Service Provider (ESP) handle it?** The answer is neither "always use Spring Retry" nor "leave everything to the provider." Both sides control **different phases** of the email lifecycle, so retry ownership must be divided along **the message acceptance boundary**, failure type, business requirements, and observed evidence.

An application using `JavaMailSender` can submit a message to an SMTP submission server. Once the relay accepts the message, that server still has to locate and deliver it to the receiving system; along the way, the remote mailbox may return temporary errors, greylisting, timeouts, or deferred delivery. The delivery platform typically has its own queue and retry policy. If the application also keeps resending the same message merely because it has not seen a delivery event yet, the recipient may receive **multiple copies of the email**.

Conversely, if the connection from the application to the SMTP relay is rejected **before the message is accepted**, the platform probably has nothing queued to retry. In that case, the application may need to persist the send intent durably and perform controlled retries.

This lesson explains how to choose where retries live, how the two layers coordinate, common SMTP/API failure modes, how to design a transactional outbox, idempotency, timeout/AMBIGUOUS handling, webhook/status reconciliation, Spring examples, and operational decisions worth recording as ADRs (*Architecture Decision Records*). Data models/enums in examples are application designs, not built-in automatic outbox/retry features of Spring Framework Mail.

## 1. You Must Distinguish Email Lifecycle Stages

An email passes through several status milestones:

```text
Business event
      |
      v
APPLICATION REQUEST CREATED
      |
      v
Stored in local outbox / broker
      |
      v
Attempt to submit via SMTP or provider API
      |
      +--> Rejected / timeout / accepted?
      |
      v
PROVIDER ACCEPTED / QUEUED
      |
      v
Provider retries downstream delivery
      |
      +--> Deferred: recipient server says try later
      +--> Bounced: permanent or exhausted failure
      |
      v
DELIVERED (according to provider event)
      |
      v
Opened / clicked / read? (separate, imperfect signals)
```

Four milestones are very easy to confuse:

1. **Created**: the application created a send intent.
2. **Submitted/accepted**: the SMTP relay or provider API confirmed receipt for processing.
3. **Delivered**: evidence exists of delivery to the receiving system per the provider's definition.
4. **Opened/read**: user engagement; this is not a transport retry outcome.

A `JavaMailSender.send(...)` call returning normally usually reflects that the current submission completed per the SMTP protocol. **It does not guarantee Inbox placement, prove the recipient read the message, or provide delivery status.**

## 2. Application Retries and Platform Retries Solve Different Problems

```text
                    APPLICATION
                        |
                Durable mail outbox
                        |
                 APP-LEVEL RETRY
               (pre-acceptance / intent)
                        |
                        v
                SMTP / Provider API
                        |
                  ACCEPTED/QUEUED
                        |
                 PLATFORM RETRY
               (downstream delivery)
                        |
                        v
                Recipient mail system
```

The **application** typically owns decisions on:

- Should this email be created at all?
- Is the recipient verified and consented?
- Has the email expired or been canceled?
- When submission fails prior to acceptance, when to retry?
- Have max attempts or deadlines been exceeded?
- Which provider/account should be used?
- Should a new copy be sent because the user explicitly requested a resend?

The **delivery platform** typically owns decisions on:

- Queueing accepted messages.
- When a remote MX returns 4xx, how long to defer?
- How to retry connections to recipient domains?
- Allocating rates/connections per receiving domain.
- Processing bounces, deferrals, complaints, and delivery notifications.
- After its retry window expires, when to mark delivery failed?

Never run an application scheduler that resends an email every 5 minutes after the provider already returned `250 OK` and is attempting delivery itself.

## 3. "Delivery Platform" Can Mean Very Different Systems

| Platform Type | Conceptual Example | Typical Capabilities |
| --- | --- | --- |
| SMTP relay / SMTP submission service | Dedicated SMTP server or hosted SMTP service | Queues accepted mail; retries downstream |
| Email Service Provider via HTTP API | Transactional/bulk mail service | Request acceptance, queue, events, suppression, retry policy |
| Self-hosted MTA | Postfix/Exim or similar system | Manages queues and retries to recipient MX |
| Local development mail catcher | GreenMail/Mailpit | Primarily captures/tests; does not fully model production delivery |
| Mail SDK/library | Jakarta Mail client, REST SDK | May retry client connections/requests; not necessarily durable queueing |
| Internal message broker | RabbitMQ/Kafka/SQS or other tech | Stores internal requests; does not deliver mail to recipients itself |

The same phrase "provider retry" sometimes refers only to **retrying an HTTP request inside an SDK**, and other times to **retrying mail delivery after the provider accepted it**. Those two functions are completely different. Read the provider's exact API/SMTP contract and documentation.

**Never assume every SMTP server has an identical durable queue**, every provider supports webhooks, or every SDK supports idempotency keys.

## 4. The Most Important Boundary: Has the Provider Accepted It?

A branching decision:

```text
Application attempts submission
              |
              v
Did provider definitively accept?
              |
        +-----+------+
        |            |
       YES           NO
        |            |
        v            v
Do not submit       Was rejection definitely
same logical mail   pre-acceptance?
again merely              |
because delivery     +----+-----+
is pending.          |          |
                     YES       UNKNOWN
                      |          |
                      v          v
                 App retry   AMBIGUOUS:
                 if policy   reconcile before retry
                 permits
```

**YES:** if the relay returns a success code for SMTP message submission or the provider API returns a receipt indicating successful queueing, the application should record `SUBMITTED`/`PROVIDER_ACCEPTED`. From that point, delivery retries generally belong to the provider. The application tracks events rather than creating a second submission just because `DELIVERED` has not arrived yet.

**NO, definitely pre-acceptance:** for example, a TCP connection cannot be opened or the SMTP server rejects submission without accepting the message. The application can retry with backoff and deadlines.

**UNKNOWN:** timeout right at the final reply, lost HTTP response, or client crash after the provider may have accepted. This is an `AMBIGUOUS` outcome. Blind retries can cause duplicates, even if the application DB recorded `FAILED`.

## 5. SMTP Has Multiple Failure Points

A typical SMTP session:

```text
Connect
  |
  v
Greeting / EHLO
  |
  v
STARTTLS / AUTH
  |
  v
MAIL FROM
  |
  v
RCPT TO (one or more)
  |
  v
DATA
  |
  v
message bytes + DATA terminator
  |
  v
final SMTP response
```

Different points carry different meanings:

- **Connection failure before greeting:** the relay has not seen the message; generally safer for the application to retry.
- **AUTH/TLS failure:** must distinguish configuration/permanent errors from transient ones; hot retries will not fix wrong credentials.
- **`MAIL FROM`/`RCPT TO` rejection:** no complete message was accepted yet; however, watch for multi-recipient partial acceptance.
- **DATA rejected with a definite response:** do not assume the message was queued when the relay rejected it; act on the status.
- **Final 2xx response after DATA:** the relay confirmed acceptance; downstream delivery is subsequent responsibility.
- **Timeout/lost response after DATA:** the relay may have queued it while the client does not know; outcome is ambiguous.

Relying solely on the `MailException` class is sometimes insufficient to tell phases apart. You need instrumented context per library contract, provider receipts, or other evidence.

## 6. SMTP 4xx and 5xx Must Be Interpreted by Phase

A common protocol rule:

| SMTP Reply | General Meaning | Handling Direction |
| --- | --- | --- |
| 2xx | Success for the current command/phase | Identify which command just completed |
| 4xx | Temporary negative completion | May retry per policy |
| 5xx | Permanent negative completion | Do not retry unchanged |
| No response received | Insufficient evidence | Inspect phase; may be AMBIGUOUS |

**Even with 4xx, who retries depends on where the error occurred.**

- The relay the application connects to returns `451` **before acceptance**: the application may need to retry submission.
- The relay **already accepted** and the recipient MX later returns 451: the provider normally retries delivery itself; the application must not resend.
- The provider API returns HTTP 429 before accepting the job: the application waits per `Retry-After`/cooldown and retries the request.
- The provider already queued the job and then reports `DEFERRED`: do not resend from the application while the provider handles delivery retries.

Never apply a rule like "whenever you see any 4xx anywhere, call `JavaMailSender` again."

## 7. HTTP API Codes Also Require Acceptance Classification

When using an ESP via HTTP API instead of SMTP:

| HTTP/API Outcome | Likely Interpretation | Responsibility to Check |
| --- | --- | --- |
| 2xx with accepted/queued receipt | Provider accepted intent | Monitor provider status |
| 400/422 validation | Invalid payload | Fix payload; do not retry the exact same request |
| 401/403 | Authentication/authorization | Check config and permissions; avoid hot retries |
| 429 | Rate limit | Honor `Retry-After`, backoff, quotas |
| 503/5xx | Temporary provider failure or uncertain state | Check response/idempotency contract |
| Client read timeout | Unknown whether provider queued it | AMBIGUOUS and reconcile |
| Connection failure before sending request | Likely never reached provider | Retry if classified safe |

Do not assume "HTTP 500 always means the provider did not receive the request." A system may commit to its queue and fail while writing the response, or the response may drop in transit.

If the provider supports **well-defined idempotency keys**, the application should send the same key across retries of the same logical intent. Still, verify scope, TTL, and semantics; do not assume all ESPs behave identically.

## 8. Why Should You Not Retry While the Provider Is Already Retrying Delivery?

Suppose:

```text
T=00:00 Application submits N-1001.
T=00:01 Provider returns ACCEPTED.
T=00:02 Recipient MX returns temporary 451.
T=00:02 Provider schedules its own delivery retry.
T=00:05 Application sees not yet DELIVERED.
T=00:05 Application resubmits N-1001.
T=00:06 Provider now has TWO accepted copies.
T=00:12 Recipient MX recovers.
T=00:12 Both copies may be delivered.
```

The recipient can receive more than one copy even while the application thinks it is performing "recovery." `Message-ID` is not a deduplication guarantee at the recipient MX.

For transactional emails, duplicates cause confusion; for OTPs, reset links, financial documents, or password flows, the impact can be much larger.

**Waiting for a provider delivery event is not a timeout that triggers automatic application resends.** It is a monitoring state that may have its own alerts and escalation.

## 9. When Should the Application Own Retries?

The application should own retries when:

1. Submission to the SMTP relay/API **has not been confirmed** and evidence shows a transient pre-acceptance failure.
2. The mail intent was created in a business transaction and must survive process restarts.
3. The job must wait for the network/provider to recover.
4. Template/content preparation hit a transient failure prior to submission.
5. Provider API rate limits/cooldowns require waiting.
6. Business deadlines/expirations must be checked before each attempt.
7. A fallback provider/account must be chosen when the primary is unavailable.
8. Service-to-service, DNS, connect, or TLS failures must follow policy.
9. In-memory SDK retries do not satisfy business durability requirements.

**Prerequisite:** the application must manage idempotency, durable state, retry budgets, backoff/jitter, schedulers/workers, metrics, and outcome ambiguity. Application retries are not just adding a `for` loop.

## 10. When Should the Delivery Platform Own Retries?

Delegate to the platform when:

- The provider **has accepted and queued** the message.
- The remote recipient MX is temporarily unavailable/greylisting/throttling.
- Per-domain delivery pacing, DNS/MX resolution, and server backoff are needed.
- The provider runs a well-operated, monitored queue/retry infrastructure.
- The provider emits delivery/deferred/bounced events.
- The application lacks visibility into or control over remote delivery details.
- The provider's delivery retry policy satisfies SLAs or business expectations.

At that point, the application should store the receipt/correlation, track state, and react to final bounces/complaints/expirations—**not run a second SMTP retry loop just because delivery is not complete yet**.

Some platforms let you configure retry windows or queue TTLs; the application should verify how long the provider retains queued jobs when aligning business deadlines.

## 11. Two Retry Layers Are Not Mutually Exclusive

A common and sound architecture:

```text
Application DB outbox
      |
      +--> retries BEFORE provider acceptance
      |
      v
SMTP submission / Provider API
      |
      +--> acceptance confirmed
      |
      v
Provider queue
      |
      +--> retries AFTER acceptance
      |
      v
Recipient MX / mailbox
```

This is not two teams handling the same failure. They handle **two different sets of states**.

The application ensures the intent is submitted or terminates with an appropriate error/resolution. The provider ensures delivery attempts per its policy after receipt.

**Never let two retry mechanisms look at a single generic `FAILED` status lacking phase context and automatically re-invoke SMTP.**

## 12. Separate Three State Machines to Avoid Confusion

A model can separate:

**Intent state:**

```text
CREATED -> READY -> PROCESSING
                -> CANCELLED / EXPIRED
```

**Submission state:**

```text
NOT_ATTEMPTED
     |
     v
SUBMITTING
     |
     +--> ACCEPTED
     +--> RETRY_WAIT
     +--> FAILED_PERMANENT
     +--> AMBIGUOUS
```

**Delivery state:**

```text
UNKNOWN / QUEUED
     |
     +--> DEFERRED
     +--> DELIVERED
     +--> BOUNCED
     +--> COMPLAINED
```

These can live in one table or multiple tables; the core rule is **never conflate `SUBMITTED` with `DELIVERED`**.

A worker may finish submission while delivery status remains `QUEUED`. Never let a poller query `delivery_status != DELIVERED` and resend everything.

## 13. Responsibility Matrix by Incident

| Incident | Provider Accepted? | Default Retry Owner | Notes |
| --- | --- | --- | --- |
| Business transaction rollback | No valid intent exists | Do not send | Prevent bogus emails |
| Transient template render error | Not submitted | Application | Retry preparation separately |
| SMTP connect refused | No | Application | Backoff/circuit breaker |
| Invalid SMTP credentials | No | Configuration/operator | Avoid hot retries |
| SMTP 421 before DATA acceptance | Unconfirmed | Application | By phase and policy |
| Final SMTP 250 after DATA | Yes | Provider for downstream | Application only tracks |
| Final response lost after DATA | Unknown | Reconciliation owner | No blind retry |
| ESP API 429 rejecting job | No | Application | Honor `Retry-After` |
| ESP API accepted receipt | Yes | Provider | Store receipt |
| Recipient MX 451 after provider acceptance | Yes | Provider | Do not create a new submission |
| Deferred event | Yes | Provider | Measure queue age |
| Final hard bounce | Yes | Do not auto-retry unchanged | Update suppression/policy |
| Customer requests copy after delivery | Already sent | New resend workflow | New notification, audited |
| OTP token expired before submit | Possibly not | Identity/business workflow | Do not send stale token |

This matrix is a baseline. Cross-check against each provider and how it specifically reports acceptance, deferrals, bounces, and failed states.

## 14. Architectural Decisions by Notification Type

| Email Type | Typically Sound Strategy | Rationale |
| --- | --- | --- |
| OTP / authentication | App retries with short deadline + provider retries once accepted | Tokens have TTLs; sending stale codes is harmful |
| Order confirmation | Durable outbox + provider delivery retries | Do not lose intent after commit |
| Invoices / documents | Durable intent, snapshots/repeatable attachments | Accuracy, audit, privacy |
| Marketing newsletter | Campaign queues and pacing + provider delivery retries | High volume, consent, quotas |
| Monthly digest | App scheduling/retries within deadline + provider | Delay is tolerable |
| Security incident alert | App durability/priority + provider | Multiple fallback channels may be needed |
| Non-critical internal notification | Can be simpler per SLO | Avoid over-engineering if losing one email is tolerable |

Do not label an email "critical" and enable infinite retries. A critical notification can have a strict deadline and become invalid once business state changes.

## 15. What Does JavaMailSender Actually Do?

Spring Framework Mail provides:

- `MailSender` for sending `SimpleMailMessage`.
- `JavaMailSender` for creating/sending `MimeMessage`.
- `JavaMailSenderImpl` using Jakarta Mail transport.
- `MimeMessageHelper` for building HTML/attachments/inline parts.
- `MailException` and subtypes reflecting preparation/transport errors.

Example:

```java
MimeMessage mime = javaMailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo("buyer@example.test");
helper.setSubject("Order confirmation");
helper.setText(
    "Your order has been confirmed.",
    "<p>Your order has been confirmed.</p>"
);

javaMailSender.send(mime);
```

This snippet executes **a single submission call**. Spring Mail does not automatically provide a durable outbox, attempt tracking, retries across restarts, webhook ingestion, provider status reconciliation, or guaranteed delivery.

Jakarta Mail transport has protocol/implementation-specific behaviors; having a timeout or reconnect property does not equate to a business-level retry policy.

## 16. Spring Boot Mail Config Does Not Enable Durable Retries

Example:

```yaml
spring:
  mail:
    host: smtp.example.test
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
```

Timeouts bound how long SMTP phases wait. They do not dictate **when or how many times** the application resends after failure.

A timeout must be interpreted by phase. If a read timeout occurs after sending SMTP DATA, do not automatically assert the message was not accepted.

`spring.mail.test-connection` (if enabled) only checks connectivity at startup/config point; it does not replace a retry pipeline or delivery tracking either.

## 17. Spring Retry @Retryable: When Is It Appropriate?

Spring Retry can help with in-process retries for transient operations:

```java
@Retryable(
    retryFor = TransientPreparationException.class,
    maxAttempts = 3,
    backoff = @Backoff(
        delay = 500,
        multiplier = 2.0,
        maxDelay = 3000
    )
)
public PreparedMail prepare(EmailIntent intent) {
    return renderer.render(intent);
}
```

Ensure Spring Retry and application imports/classes are configured properly; the example uses an application-defined `TransientPreparationException`.

More appropriate when:

- The operation is idempotent/side-effect-free.
- Retries finish within a short window.
- Errors clearly happen before SMTP acceptance.
- Survival across process restarts is not required.
- Thread budget allows waiting on retries.

Avoid:

```java
@Retryable(retryFor = MailException.class)
public void sendAnything(MimeMessage mime) {
    javaMailSender.send(mime);
}
```

and treating it as a complete solution for all SMTP failures. `MailException` is too broad; a timeout after DATA can be ambiguous. Synchronous retries also tie up threads/requests and are not durable if the JVM dies.

**Spring Retry, Resilience4j retry, and provider delivery retries are not the same functional layer.** Choose based on the exact boundary and durability required.

## 18. Why a Durable Outbox Matters More Than a Retry Loop

Suppose:

```text
Database transaction:
  order = PAID
COMMIT

Application process:
  JavaMailSender.send(...)
  connection refused
  JVM crashes
```

If the send intent lived only in memory, the email might never be retried. If sent directly **before** the business commit, the email might go out even if the transaction rolls back.

Transactional outbox:

```text
BEGIN DB TRANSACTION
    update order to PAID
    insert mail_intent with status READY
COMMIT

Later:
    worker claims mail_intent
    submits to SMTP
    records outcome
```

This closes the gap between business commit and durable send-intent creation. It does **not** make SMTP and the database one atomic transaction; you still must handle crashes after SMTP acceptance but before the DB update.

## 19. Two-Phase Outbox Model

PostgreSQL example:

```sql
CREATE TABLE mail_outbox (
    id                       UUID PRIMARY KEY,
    tenant_id                UUID NOT NULL,
    notification_id          UUID NOT NULL UNIQUE,
    business_idempotency_key VARCHAR(200) NOT NULL,
    category                 VARCHAR(40) NOT NULL,
    submission_state         VARCHAR(40) NOT NULL,
    delivery_state           VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN',
    next_attempt_at          TIMESTAMPTZ,
    attempt_count            INT NOT NULL DEFAULT 0,
    max_attempts             INT NOT NULL,
    expires_at               TIMESTAMPTZ,
    provider_account         VARCHAR(100),
    provider_message_id      VARCHAR(255),
    locked_by                VARCHAR(100),
    lease_until              TIMESTAMPTZ,
    claim_version            BIGINT NOT NULL DEFAULT 0,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, business_idempotency_key)
);
```

`business_idempotency_key` must be scoped properly to event/recipient/template. Too broad a key blocks legitimate notifications; too narrow a key creates multiple intents for the same event.

These states are application models, not built-in Spring Mail enums. A record may hold content snapshots/references, recipient references, and policy metadata under proper access control; **never put raw HTML/OTPs into operational logs**.

## 20. Claiming Jobs: Prevent Multiple Workers from Sending the Same Intent

PostgreSQL example claiming jobs not yet in submission:

```sql
WITH due AS (
    SELECT id
    FROM mail_outbox
    WHERE submission_state IN ('READY', 'RETRY_WAIT')
      AND next_attempt_at <= NOW()
      AND (expires_at IS NULL OR expires_at > NOW())
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET submission_state = 'CLAIMED',
    locked_by = :worker_id,
    lease_until = NOW() + (:lease_seconds * INTERVAL '1 second'),
    claim_version = claim_version + 1,
    updated_at = NOW()
FROM due
WHERE o.id = due.id
RETURNING o.id, o.notification_id, o.claim_version;
```

The claim transaction must be short and commit before SMTP. `SKIP LOCKED` lets pollers skip rows locked by other transactions; lease/`claim_version` protects ownership after commit.

**Key point:** if a worker dies in `CLAIMED` before starting SMTP, the job can usually be reclaimed after lease expiry. If it dies in `SUBMITTING` when acceptance may have occurred, never casually treat it as "definitely unsent." Define dedicated recovery for the side-effecting phase.

## 21. Distinguish CLAIMED from SUBMITTING for Recovery

A pragmatic state machine:

```text
READY / RETRY_WAIT
       |
       v
CLAIMED (no network side effect yet)
       |
       v
SUBMITTING (provider call may have begun)
       |
       +--> ACCEPTED
       +--> RETRY_WAIT (definite pre-accept failure)
       +--> FAILED_PERMANENT
       +--> AMBIGUOUS
```

What happens if the JVM crashes:

- Expired `CLAIMED` lease: can be requeued if ownership flow proves the provider was not called yet.
- Expired `SUBMITTING` lease: **unknown** whether submission occurred; route to reconciliation or recovery with an explicit duplicate policy.
- `ACCEPTED`: provider queue continues delivery; do not replay submission.
- `RETRY_WAIT`: retry only once `nextAttemptAt` is due.

A system with provider-supported idempotency keys may choose to retry ambiguous requests using the same key per provider contract. With plain SMTP, that guarantee generally does not exist.

Persisting `SUBMITTING` before the network call narrows the risk window, though it does not eliminate every race. No DB transaction guarantees atomic exactly-once side effects over SMTP.

## 22. Fencing Stale Workers

If worker A holds a lease and stalls, worker B may reclaim it. A must not update state after losing ownership.

Example:

```sql
UPDATE mail_outbox
SET submission_state = 'ACCEPTED',
    locked_by = NULL,
    lease_until = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND locked_by = :worker_id
  AND claim_version = :claimed_version
  AND submission_state = 'SUBMITTING';
```

If affected rows = 0, ownership changed. Record an audit/diagnostic event for investigation; never overwrite blindly.

Fencing protects **database state**, not recall SMTP emails already sent by the stale worker. Therefore, avoid premature lease expiry, bound in-flight work/renew leases carefully, and manage ambiguous states.

## 23. An Abstraction Separating Responsibilities Clearly

In application code, avoid services returning a vague `boolean sent`. Define:

```java
public enum SubmissionOutcome {
    ACCEPTED,
    DEFINITELY_REJECTED_TRANSIENT,
    DEFINITELY_REJECTED_PERMANENT,
    AMBIGUOUS
}
```

Receipt:

```java
public record SubmissionReceipt(
    SubmissionOutcome outcome,
    String providerAccount,
    String providerMessageId,
    String normalizedFailureCode
) {}
```

Port:

```java
public interface MailSubmissionPort {
    SubmissionReceipt submit(PreparedMail mail);
}
```

`PreparedMail`, the receipt, and the enum are application-defined types. `JavaMailSender` does not return an object with these fields by default.

An SMTP adapter may not know a provider message ID; in that case leave it `null` and record the internal attempt ID. **Never fabricate IDs or map every `MailException` to DEFINITELY_REJECTED_TRANSIENT.**

## 24. Workers Handle Receipts at the Boundary

Java pseudocode:

```java
public void process(ClaimedMailJob claim) {
    if (!eligibility.canSendNow(claim.notificationId())) {
        states.markSuppressedIfOwned(claim);
        return;
    }

    PreparedMail prepared =
        content.loadPrepared(claim.notificationId());

    states.markSubmittingIfOwned(claim);

    try {
        SubmissionReceipt receipt =
            submissionPort.submit(prepared);

        switch (receipt.outcome()) {
            case ACCEPTED ->
                states.markAcceptedIfOwned(claim, receipt);

            case DEFINITELY_REJECTED_TRANSIENT ->
                states.scheduleRetryIfOwned(
                    claim, backoff.nextAttempt(claim)
                );

            case DEFINITELY_REJECTED_PERMANENT ->
                states.markFailedIfOwned(claim, receipt);

            case AMBIGUOUS ->
                states.markAmbiguousIfOwned(claim, receipt);
        }
    } catch (RuntimeException unexpected) {
        // If the provider call may have started, do not assume NOT_SENT.
        states.markNeedsReconciliationIfOwned(claim);
        throw unexpected;
    }
}
```

These services and classes are illustrative domain code. Ensure `markSubmittingIfOwned` succeeds and commits before the network call so a worker that lost its lease never sends.

Do not use a `catch (Exception)` block that always sets `RETRY_WAIT`; errors can happen after the server already accepted. For some providers/adapters, outcomes cannot be safely inferred from exception type alone; keep a conservative `AMBIGUOUS` branch.

## 25. Backoff and Jitter for Application Retries

A common policy uses capped exponential backoff:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

To avoid thundering herds, full jitter can be used:

\[
w_n \sim U(0,d_n)
\]

Example maximum wait caps:

| Next Attempt | Illustrative Cap |
| --- | ---: |
| 2 | 10 seconds |
| 3 | 20 seconds |
| 4 | 40 seconds |
| 5 | 80 seconds |
| 6 onward | Up to configured cap |

Jitter spreads out retries across jobs without increasing provider quota. If the provider gives `Retry-After` or an official cooldown, honor that guidance before scheduling.

Never run long `Thread.sleep` loops inside HTTP requests or database transactions. Persist `nextAttemptAt` and let the scheduler claim the job when due.

## 26. Max Attempts, Deadlines, and Business Expiry

A notification can carry:

- `maxAttempts`: maximum submission attempts per policy.
- `expiresAt`: after this timestamp, do not send stale content.
- `nextAttemptAt`: earliest time allowed to retry.
- `providerQueueDeadline`: if supported by the provider.
- `consentVersion`/recipient suppression status.

OTP example:

```text
Created at     10:00:00
Token expires  10:05:00
SMTP outage    10:00-10:10
```

Do not backlog and send an expired OTP at 10:10. After expiry, transition to `EXPIRED` or let another business workflow issue a new token if the user validly requests one.

Note: **application expiry before submission** does not necessarily recall messages already accepted into a provider queue. For ultra-short-lived content, check provider retry TTL/cancellation capabilities; many platforms cannot cancel every queued email.

## 27. Provider Retry Policies and Delivery Windows Must Be Known

When choosing platform-owned downstream retries, verify:

1. Does the provider have a durable queue after acceptance?
2. What is the maximum delivery retry duration?
3. How are remote 4xx/greylisting responses handled?
4. When does a message finally bounce or expire?
5. Are temporary and permanent failures distinguished?
6. Are webhook/API events emitted for deferred, delivered, bounced, and complained?
7. What are event latencies and replay semantics?
8. Are there per-recipient-domain or connection-concurrency limits?
9. Is cancellation supported when content expires?
10. Can provider message IDs and queue statuses be queried?
11. Are separate suppression and opt-out mechanisms present?
12. If the provider suffers an outage after acceptance, what are recovery/retention commitments?

Never document "provider retries automatically for 72 hours" without evidence from your actual provider's documentation/contract. Platforms differ and configurations can change.

## 28. Webhooks/Events for Downstream Delivery

If the provider offers callbacks:

```text
Provider queue
      |
      +--> deferred
      +--> delivered
      +--> bounced
      +--> complained
      |
      v
Signed webhook / authenticated event
      |
      v
Verify authenticity + parse
      |
      v
Deduplicate provider event ID
      |
      v
Correlate providerMessageId / internal notificationId
      |
      v
Update delivery state
      |
      v
Metrics / suppression / alerts
```

A webhook handler **must not** resend an email every time it receives `DEFERRED`. Deferred may simply indicate the provider is waiting to try again.

A final hard bounce may call for suppression, cleanup, or updating customer contact details; that is a business policy, not an infinite retry trigger.

## 29. Webhooks Do Not Guarantee Ordering or Exactly-Once Delivery

Provider events can:

- Be delivered repeatedly due to webhook retries.
- Arrive out of order due to queues/networks.
- Arrive after application restarts.
- Share a message ID while carrying multiple recipient statuses.
- Arrive before the internal DB update to `ACCEPTED` finishes.
- Be lost if your endpoint is down and provider retention expires.

Therefore you need:

- Signature/authentication and timestamp/replay verification per provider spec.
- Persisted event IDs with a unique constraint or reliable dedup rule.
- Clear correlation keys linking provider messages to notifications.
- Monotonic state-update rules/policies so an older `DEFERRED` event never overwrites `DELIVERED`.
- Reconciliation via provider API when events go missing, if supported.
- Access/privacy controls on webhook payloads.

Never treat a webhook's HTTP response as proof the application committed status unless durability is genuinely persisted first.

## 30. Example Provider Events Table

```sql
CREATE TABLE mail_provider_event (
    id                  UUID PRIMARY KEY,
    provider_account    VARCHAR(100) NOT NULL,
    provider_event_id   VARCHAR(255),
    provider_message_id VARCHAR(255),
    notification_id     UUID,
    recipient_ref       VARCHAR(200),
    event_type          VARCHAR(50) NOT NULL,
    occurred_at         TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_mail_provider_event_dedup
ON mail_provider_event (provider_account, provider_event_id)
WHERE provider_event_id IS NOT NULL;
```

If the provider does not supply an event ID, use another dedup strategy over sufficiently reliable fields; do not add a broken unique constraint that drops valid events.

One provider message can target multiple recipients, so events may require recipient-level identity. Recipient data must be protected per privacy policy; operational logs should show only opaque IDs and event classes.

## 31. Reconciliation When Outcomes Are Ambiguous

A workflow:

```text
SUBMITTING attempt
      |
      +--> client timeout / process crash
      |
      v
AMBIGUOUS
      |
      v
Can provider query by request ID / idempotency key / queue ID?
      |
      +--> yes: find accepted evidence -> mark ACCEPTED
      |
      +--> no result: evidence still incomplete?
      |
      +--> provider contract confirms not accepted -> retry if eligible
      |
      +--> cannot determine -> hold / manual policy / bounded risk decision
```

"Not found immediately" does not always prove the provider never received the message, because indexing/APIs can be eventually consistent. The design must understand the provider's consistency window and retention.

With a plain SMTP relay lacking a lookup API, full reconciliation may be impossible. The system must pick a **duplicate-risk policy** per email type:

- For routine notifications, business may accept low duplicate odds in favor of at-least-once.
- For sensitive documents/security operations, manual review or dedicated verification workflows may be needed.
- For certain mail types, missing an email may be less severe than sending twice; state that choice explicitly too.

Never advertise exactly-once email delivery when no end-to-end contract supports it.

## 32. Are Message-ID and Idempotency Key the Same?

No.

- **Notification ID:** application-generated logical identifier.
- **Attempt ID:** identifier for each submission attempt.
- **MIME Message-ID:** standard email header, useful for correlation.
- **Provider message ID:** queue/event identifier assigned by the provider if provided.
- **HTTP API idempotency key:** request dedup key when explicitly supported by the provider.
- **Business idempotency key:** prevents creating two notification intents for the same business event.

SMTP has no general mechanism forcing a recipient MX to deduplicate two messages with the same MIME `Message-ID`. Keeping `Message-ID` identical across retries does not produce exactly-once delivery.

If a provider HTTP API supports idempotency keys, check scope (account/endpoint), TTL, whether receipts are replayed, and response-timeout handling. Reusing a key with a different payload may be rejected or handled per provider rules.

## 33. Choosing a Fallback Provider Can Also Cause Duplicates

A flow:

```text
Submit to provider A
      |
      +--> read timeout (UNKNOWN)
      |
      v
Immediately submit same mail to provider B
      |
      v
Both providers may have queued it
```

Provider failover should be automatic only when there is evidence provider A **did not accept**, or when the application explicitly accepts duplicate risk by policy. If A is ambiguous, failing over is no safer than normal retries on A.

Track:

- Shared `notificationId`.
- Distinct `attemptId`.
- `providerAccount`/`providerRequestId`.
- Acceptance evidence.
- Provider event mappings from both A and B.
- Quotas/cooldowns/suppression across both providers.
- Content snapshots and recipient eligibility.

Never invent provider-specific headers containing secrets or log full MIME for correlation.

## 34. Retaining Content for Retries: Snapshot or Re-Render?

When retrying application submissions, content policy must be explicit:

**Snapshot/Prepared mail**

- Persist safely prepared subject/plain/HTML or artifact references.
- Guarantees all attempts for the same logical intent use a consistent content version.
- Useful for invoice/transactional audits.
- Requires retention/encryption policies and artifact availability.

**Re-render before attempt**

- Uses current data/templates.
- May reflect fresher business state.
- Yet different attempts may produce different content for the same notification.
- Risks sending stale OTPs or inadvertently altering subjects/attachments.

Do not pick by accident. A sound policy can pair immutable template versions + data snapshots for audit-sensitive emails, while still rechecking current eligibility/expiry prior to submission.

For security tokens, issuing a new token belongs to the identity workflow—not an email retry arbitrarily re-rendering.

## 35. Cancellation and Delayed Provider Delivery

If a user cancels an order or revokes a link after the provider already accepted the email:

- The application can cancel unsubmitted jobs.
- However, it cannot implicitly delete an email already sitting inside an external SMTP relay's queue.
- Some providers offer APIs to cancel/expire queued messages within bounds; many do not.
- If the email holds a tokenized link, server-side tokens should be revocable/expirable independently of mail delivery.
- Business workflows must account for late-arriving emails.

Therefore, when letting providers retry over long durations, consider **whether the content remains valid if delivered late**. A 5-minute TTL OTP email should not rely on a multi-day delivery retry window for its user experience.

## 36. SLA/SLO: Measure Submission and Delivery Separately

Two recommended SLOs:

1. **Application submission SLO:** from business commit/intent due until provider acceptance.
2. **Delivery outcome SLO:** from provider acceptance to provider delivered/bounced/final status, within provider capabilities.

Example metrics:

```text
mail_intent_to_acceptance_seconds
mail_submission_attempt_duration_seconds
mail_submission_accepted_total
mail_submission_failed_total
mail_submission_ambiguous_total
mail_submission_retry_scheduled_total

mail_provider_deferred_total
mail_provider_delivered_total
mail_provider_bounced_total
mail_provider_delivery_lag_seconds
mail_provider_event_processing_lag_seconds
```

These names are suggested application metrics, not emitted automatically by Spring Mail.

An SLO like "email lands in Inbox within 2 seconds" usually cannot be controlled by Spring/SMTP clients alone. Use feasible end-to-end definitions backed by provider evidence; even a DELIVERED event may not distinguish Inbox from Spam folders.

## 37. Measure Retry Effectiveness Instead of Just Raising Attempt Counts

A useful dashboard:

| Metric | Owning Layer | Question |
| --- | --- | --- |
| Outbox READY oldest age | App | Are any jobs waiting too long to submit? |
| Submission retry rate | App | Is there a provider outage/throttling? |
| Ambiguous attempt count | App | Are there timeouts hard to reconcile? |
| Acceptance rate | App/Provider | How many did the provider accept? |
| Provider deferred count | Provider events | Is downstream temporarily deferring? |
| Delivery lag P95/P99 | Provider events | Accepted mail arriving slowly? |
| Bounce/complaint rate | Provider events | How is recipient quality/reputation? |
| Duplicate complaints | App/business | Are layered retries causing duplicates? |
| Expired before submission | App | Do SLOs and business deadlines align? |
| Provider webhook lag | App/Provider | Are events arriving delayed? |

Never use recipient email or subject as metric labels; they contain PII and cause high cardinality. Use provider, category, and normalized outcomes in aggregate.

## 38. Application-Layer Backpressure and Rate Limiting

Even when the provider handles delivery retries, the application must still bound **submission rate**:

- SMTP providers cap messages/second, recipients/minute, and concurrent connections.
- HTTP ESP APIs enforce burst/rate limits and return 429s.
- Database outboxes can accumulate large backlogs after outages.
- If workers dump the entire backlog as soon as the provider recovers, a retry storm results.
- Multiple instances sharing a provider account can exceed global quotas despite per-JVM limiters.

You need bounded workers, per-provider/account rate limiters, and batch sizes matching capacity. Application retries should update `nextAttemptAt` per job instead of sleeping inside threads.

Never use platform delivery retries as an excuse to skip admission/submission throttling.

## 39. A Retry and Circuit Breaker Diagram

```text
Outbox READY
     |
     v
Worker claims if provider circuit permits
     |
     v
Token/permit from provider budget
     |
     v
Submit once
     |
     +--> accepted --------> STOP APP SUBMISSION RETRY
     |                         |
     |                         v
     |                   Provider queue/retry
     |
     +--> definite transient -> backoff+jitter -> RETRY_WAIT
     |
     +--> permanent -> FAILED / operator action
     |
     +--> ambiguous -> RECONCILE / policy gate
```

Circuit breakers protect providers/applications during prolonged outages, yet do not guarantee an already-accepted message will not be submitted twice. Retry policies still need state machines and idempotency.

An SMTP authentication error normally needs config intervention; opening a circuit/cooldown prevents thousands of repeated attempts with bad credentials.

## 40. Choosing SMTP vs. ESP API Affects Retry Capabilities

**SMTP submission:**

Pros:

- Widely standardized; Spring `JavaMailSender` supports it directly.
- Easy to swap relays for basic sending.
- Providers can handle remote delivery retries.

Limitations:

- Clients may not receive a provider queue ID.
- Timeouts after DATA are hard-to-reconcile ambiguous cases.
- Delivery events are not built into the SMTP client.
- Idempotency-key resend APIs are generally not part of SMTP.

**ESP HTTP API:**

Potential pros:

- Receipts/provider request IDs.
- Idempotency keys where supported.
- Delivery/deferred/bounce/complaint events.
- Status lookup APIs and suppression management.

Limitations:

- Vendor-specific SDKs/schemas/quotas.
- 5xx responses/timeouts can still be ambiguous.
- Provider API idempotency is not universal.
- Requires securing webhooks, tokens, and event data.
- Migrating between providers may require adapters/canonical models.

Choose protocols based on observability/reconciliation needs and business requirements, not merely how short the send snippet looks.

## 41. When to Choose Direct Synchronous Sending?

Not every application needs a complex outbox. Direct sending can fit when:

- Emails are non-critical or losing them does not break business correctness.
- Survival across process restarts is not required.
- Volume is low.
- Request latency/SLOs are acceptable.
- Manual retries or exceptions are handled in another workflow.
- No business transaction requires atomic intent persistence.

State the risk clearly: a network error after commit loses the email without durable intent. Sending directly inside a database transaction also cannot roll back SMTP when the DB rolls back.

For invoices, confirmations, and high-reliability notifications, a durable outbox is usually worth far more than in-memory retries.

## 42. Three Architectural Options to Compare

**Option A — Application-only retries**

```text
App -> SMTP attempt
      -> retry every failure locally
```

Without separating accepted vs. downstream, duplicate risk is high. Fits only narrow cases where the platform has no queue and the app precisely knows acceptance.

**Option B — Delivery-platform-only retries**

```text
App sends once
    -> if provider accepted, provider retries
```

Simple after acceptance, yet if the app/process dies before acceptance or the API fails, the intent can be lost.

**Option C — Bounded Two-Layer Retries (usually fits production)**

```text
Durable app intent
    -> app retries definite pre-accept failures
    -> provider acceptance
    -> provider retries downstream
    -> app records delivery events
```

Option C does not double-retry the same failure. It assigns ownership by stage while still requiring AMBIGUOUS handling. Each organization tunes cost/complexity/SLO trade-offs.

## 43. Requirements-Based Decision Matrix

| Criterion | Favor App Retry | Favor Platform Retry |
| --- | --- | --- |
| Errors before reaching provider | Yes | No message exists to retry |
| Provider already accepted | Do not resubmit | Yes, downstream delivery |
| Business expiry/consent | App decides | Provider must receive limits if supported |
| Remote MX temporary 4xx | Not seen directly after acceptance | Yes |
| Process restart durability | App outbox/broker | Does not replace app intent before acceptance |
| Per-domain throttling | Admission only in app | Provider typically understands MX/domains |
| Delivery/bounce events | App consumes/acts | Provider emits events |
| Provider API 429 | App backoff | Platform may not have received job |
| Unknown acceptance | App reconciles/decides | Provider query/idempotency if supported |
| Manual customer resend | App workflow | Platform submits a new notification per app decision |
| Cost/duplicate control | App policies/IDs | Provider queue semantics |
| Vendor portability | App abstraction | Provider-specific retry behavior |

Verify specific capabilities against provider documentation/contracts rather than relying on generic assumptions.

## 44. Multi-Provider Architecture and Retry Ownership

An adapter can encapsulate provider details:

```java
public interface ProviderMailGateway {
    SubmissionReceipt submit(
        PreparedMail mail,
        String logicalIdempotencyKey
    );

    Optional<ProviderDeliveryStatus> findStatus(
        String providerMessageId
    );
}
```

`findStatus` is a **provider-dependent** capability; not every adapter can implement it for real if the platform lacks an API. Express this via feature flags/capability contracts instead of returning a misleading "not found."

An option:

```text
ProviderCapabilities:
  supportsIdempotencyKey
  supportsStatusLookup
  supportsDeliveryWebhook
  supportsCancelQueued
  retryWindowPolicy
```

Never use feature flags to pretend a provider has nonexistent capabilities. Workers must know when an ambiguous request can safely be retried using the same idempotency key.

## 45. Scenario A: Order Confirmation Email

Requirements:

- Never lose intent after order commit.
- Never send before the business transaction succeeds.
- Avoid duplicates.
- Track bounces.
- Allow customers to request a copy with valid reason.

Design:

1. In the order transaction, insert an outbox row `READY` with a business idempotency key.
2. Worker claims and checks eligibility.
3. Render/use prepared snapshot and submit.
4. If connect refused prior to acceptance, app retries with backoff.
5. If provider accepts, mark `ACCEPTED`; stop submission retries.
6. Provider handles delivery retries if recipient MX temporarily errors.
7. App ingests delivery/bounce webhooks and updates status.
8. If the customer requests a copy after delivery, create a **new resend notification**, without resetting the original.

Ambiguous outcomes after SMTP DATA need dedicated policy; never mark `NOT_SENT` and retry immediately.

## 46. Scenario B: 5-Minute TTL OTP

Requirements:

- Low latency.
- Token expires after a few minutes.
- Never send old codes after expiry.
- Anti-abuse and frequency caps.
- Do not let provider queues deliver invalidated links that confuse users.

Design:

1. Identity workflow generates the token per policy and inserts the outbox intent.
2. App checks `expiresAt` before every attempt.
3. Fast pre-acceptance retries bounded by remaining time.
4. Once accepted, provider handles delivery, and the app does not auto-resubmit merely because delivery is pending.
5. If the user clicks "Send new code," the identity service rotates/issues a token, creating a distinct notification.
6. Never use manual mail resends to copy stale raw OTP emails.
7. If the provider supports TTL/cancellation, align configuration; otherwise server-side token validation enforces validity.

For OTPs, excessive retries may be less useful than letting the user choose another verification channel, depending on threat model.

## 47. Scenario C: High-Volume Marketing Campaign

Requirements:

- Consent/suppression applied before sending.
- Provider rate budgets respected.
- Spread-out sending acceptable.
- Monitor bounces/complaints and domain reputation.
- Never send multiple copies to one recipient while the provider is deferring.

Design:

1. Campaign scheduler creates intents for verified recipients/segments.
2. Workers enforce quotas and eligibility before submission.
3. ESP accepts and queues messages.
4. Provider retries remote delivery per rate/domain policies.
5. App updates suppression on hard bounces/complaints.
6. App never uses `delivery != DELIVERED` to re-submit campaign items.
7. Restarts/campaign pauses affect only unaccepted jobs, or use cancel APIs where supported.
8. Marketing resends are separate campaign actions with their own consent/frequency policies.

For bulk jobs, batch size controls internal work distribution only; provider quotas remain an independent constraint.

## 48. Scenario D: Primary Provider Loses Connectivity

Suppose the primary returns a clear connection refused before sending data:

```text
N-1001 -> Provider A connect failed
             |
             v
         App retry policy
             |
             +--> backoff to A
             |
             +--> optional fallback to B
                  if policy and acceptance proof allow
```

If A never received the message, failover can be safer. However, if the failure is a read timeout after DATA, failing over immediately to B can create two copies. Persist acceptance confidence and provider attempts.

Fallback policy should consider:

- Does provider B share the same sender authorization/DKIM policy?
- How is recipient suppression synchronized?
- Are content and attachments repeatable?
- Does the business email deadline still allow it?
- Are there global quota or reputation constraints?
- How are event callbacks from A and B correlated?

Never use provider fallback to bypass quotas or ignore suppression.

## 49. Testing: Separate Both Layers Intentionally

**Unit tests for application retries:**

- Connect failure before acceptance → `RETRY_WAIT`.
- Permanent SMTP authentication failure → stop/circuit/config action.
- Deadline expired → `EXPIRED`, no submission.
- Rate limit → retry per cooldown.
- Exhausted attempt count → no infinite retries.
- Same business event → no duplicate intents.
- Manual resend → new notification, original untouched.
- Unknown acceptance → `AMBIGUOUS`, no normal auto-retry.

**Integration tests with SMTP capture (GreenMail/Mailpit):**

- Worker submits and captures exact MIME.
- `ACCEPTED` status after successful SMTP response.
- No resubmission while only delivery status is pending.
- Simulate server rejection before DATA per fixture/test-server capabilities.
- Simulate dropped response after DATA with a server stub/proxy to verify the ambiguous path.
- Repeated worker deliveries/restarts do not lose durable intents.
- Multiple workers atomically claiming the same job create no happy-path duplicates.

**Webhook integration tests:**

- Invalid event authenticity/signature → reject.
- Duplicate event ID → deduplicate.
- Deferred then delivered → correct final state.
- Out-of-order deferred after delivered → no state downgrade.
- Bounced/complained → update suppression properly.
- Event arriving before internal receipt update → correlation/reconciliation.
- Provider status lookup temporarily unavailable → never conclude "not accepted."

## 50. Fault Injection Matters More Than Simple Happy Paths

A fault-testing suite can exercise:

```text
Fault 1: DB transaction rolls back before outbox insert
Fault 2: JVM crashes after business commit, before worker claim
Fault 3: SMTP connect refused
Fault 4: SMTP rejects recipient before acceptance
Fault 5: SMTP DATA accepted, final response lost
Fault 6: Worker crashes after provider accepted, before DB commit
Fault 7: Provider defers downstream delivery
Fault 8: Provider webhook arrives twice and out of order
Fault 9: Provider event never arrives before reconciliation window
Fault 10: Rate limiter and provider 429 appear together
Fault 11: Recipient unsubscribes while job RETRY_WAIT
Fault 12: OTP expires while provider/worker is offline
```

For each fault, assert:

- Accurate notification state.
- Clear retry owner.
- No infinite sending.
- Durable intent preserved where policy requires.
- Never falsely marked delivered.
- No recipient/secret leakage in logs.
- Manual reconciliation steps are executable.

Simply mocking `JavaMailSender.send()` to throw an exception does not model the DATA acceptance boundary. A protocol-aware test server/proxy is needed for ambiguous scenarios.

## 51. Observability and Safe Logging

Log events by IDs:

```json
{
  "event": "mail.submission.attempt",
  "notificationId": "N-1001",
  "attemptId": "A2",
  "provider": "primary",
  "phase": "SUBMISSION",
  "outcome": "DEFINITELY_REJECTED_TRANSIENT",
  "failureClass": "SMTP_TEMPORARY",
  "nextAttemptAt": "2026-11-12T11:30:00Z"
}
```

When accepted:

```json
{
  "event": "mail.provider.accepted",
  "notificationId": "N-1001",
  "attemptId": "A3",
  "provider": "primary",
  "providerMessageId": "opaque-provider-id",
  "deliveryState": "QUEUED"
}
```

Never log full `MimeMessage`, subjects, Bcc/To recipients, raw attachments, OTPs, SMTP passwords, or nested exception messages containing recipients. `notificationId`/`attemptId` fields support investigation without raw payloads.

When recipient correlation is needed, use access-controlled database lookups instead of placing email addresses in metric labels/traces.

## 52. Match Complexity to Requirements

Not every email service needs:

- Dual providers with failover.
- Multi-tier circuit breakers.
- Sophisticated dynamic backoff.
- Reconciliation APIs.
- Dozens of state-machine states.
- Full event sourcing of email history.

However, systems requiring reliable sending need at least:

1. Durable intents or a durable work source.
2. Separation between pre-accept failures and accepted states.
3. Bounded application retries.
4. Deadline/eligibility rechecks.
5. Deliberate `AMBIGUOUS` outcome handling.
6. Provider delivery/bounce observability if business requires it.
7. Idempotency/duplicate-risk policies.
8. Minimal logging/auditing.

Added complexity should tie directly to concrete SLOs, vendor capabilities, and the cost of missed vs. duplicate messages.

## 53. A Short ADR Recording the Architectural Decision

Example:

```text
ADR: Retry ownership for transactional email

Context:
  Spring Boot app persists order confirmation intents.
  SMTP provider accepts messages into its durable queue.
  Provider exposes delivery/bounce events.

Decision:
  Application owns retry until definite provider acceptance.
  Provider owns delivery retry after acceptance.
  Application will not resubmit merely because delivery is pending.
  Ambiguous submission attempts enter reconciliation state.
  Outbox jobs expire according to business policy.
  Resend creates a new notification with explicit authorization.

Consequences:
  Need outbox, worker leases, retry budget and event dedup.
  Need provider SLA/webhook/retention monitoring.
  May still face ambiguous SMTP outcomes and duplicate risk.
  Cannot guarantee Inbox placement or exactly-once email delivery.

Review triggers:
  Provider contract change, new API idempotency support,
  repeated ambiguous incidents, tighter business deadlines.
```

An ADR should name an owner, effective date, provider capability evidence, and accepted trade-offs. Whenever the provider changes retry windows or event schemas, revisit the decision.

## 54. Anti-Patterns to Avoid

| Anti-Pattern | Why It Is Wrong | Alternative |
| --- | --- | --- |
| App retries whenever `delivery != DELIVERED` | Provider may already be retrying after acceptance | Stop after accepted; track delivery |
| Treating `JavaMailSender.send()` as delivered | Submission differs from delivery | Separate states and SLOs |
| Resending when final SMTP response is lost | Relay may have queued it | AMBIGUOUS/reconcile |
| Retrying every `MailException` as transient | AUTH, MIME, and permanent errors differ | Failure classification |
| Using only `@Retryable` to prevent lost mail | In-memory/restart loss risk | Durable outbox |
| Sending SMTP inside a DB transaction | DB rollback cannot recall email | Commit intent first, send after |
| Using Message-ID as a guaranteed dedup key | SMTP does not guarantee deduplication | Business key/provider idempotency |
| Failing over to provider B when A is ambiguous | Both may have accepted it | Acceptance-aware policy |
| App-retrying 4xx at every stage | Downstream 4xx belongs to provider | Follow acceptance boundary |
| Assuming HTTP 500 always means unreceived | Provider may queue then fail response | API idempotency/reconciliation |
| No max attempts/deadline | Infinite retries, sending stale content | Retry budget + expiry |
| Retrying immediately on provider 429 | Worsens throttling | `Retry-After`/cooldown/jitter |
| Ignoring duplicate webhook events | Corrupts delivery state | Event dedup + monotonic updates |
| Retrying hard bounces to the same address | Repeated failures/suppression risk | Address remediation |
| Copying old OTP emails on user resend | Token expired or unsafe | New identity workflow |
| Enabling provider + app retries with no owner | Both layers resend together | Clear ownership matrix |
| Logging full emails for reconciliation | Exposes recipient content | Opaque IDs and secure storage |
| Treating delayed provider events as failures | Events can arrive late | Reconciliation window |

## 55. Runbook When SMTP Submission Fails

1. Identify notification ID, attempt ID, and provider/account.
2. Inspect failure phase: connect/auth/RCPT/DATA/final response/API.
3. Check whether the provider accepted/queued it.
4. If definitely not accepted, classify transient vs. permanent.
5. If transient, determine cooldown/`Retry-After` and `nextAttemptAt`.
6. If permanent/configuration, fix root cause; avoid hot retries.
7. If ambiguous, inspect provider status/logs and idempotency support.
8. Do not resend when the provider accepted and is deferring downstream.
9. Recheck recipient eligibility/consent/expiry before a new attempt.
10. Monitor max attempts, queue age, and circuit breakers.
11. Record normalized outcomes and audits without raw MIME.
12. If manual action is needed, enforce authorization/idempotency and explicit duplicate-risk decisions.

## 56. Runbook When a Customer Says "I Never Received the Email"

1. Verify whether the app created a durable intent.
2. If not submitted: inspect outbox status and pre-acceptance errors.
3. If `SUBMITTED`: inspect provider queue/status.
4. If provider `DEFERRED`: check retry window/cooldown; no app resend needed yet.
5. If `DELIVERED`: ask the user to check Spam/filtered mailboxes per support script; the event does not prove read status.
6. If `BOUNCED`: inspect reason and suppression; do not blindly retry the same address.
7. If `AMBIGUOUS`: reconcile and follow duplicate-avoidance policy.
8. For OTPs/reset links, check expiry; if needed, guide through issuing a new token.
9. If an intentional copy is needed, create a **new resend notification** with reason and consent.
10. Update the ticket with authorized metadata only—never put raw email/tokens into logs.

## 57. Pre-Production Decision Checklist

- [ ] Is the provider acceptance boundary explicitly defined?
- [ ] Do you know which states are definitely unaccepted, accepted, and ambiguous?
- [ ] Does app retry have a durable outbox/broker if required by business?
- [ ] Do retries have max attempts, backoff, jitter, and deadlines?
- [ ] Is `nextAttemptAt` decoupled from polling intervals?
- [ ] Are ownership/leases/fencing in place for multi-worker setups?
- [ ] Are SMTP calls kept outside business/claim DB transactions?
- [ ] Are provider downstream retries and retry windows verified?
- [ ] Does the app avoid resubmitting while provider delivery is pending/deferred?
- [ ] Are provider API idempotency/lookup capabilities verified?
- [ ] Is AMBIGUOUS handling designed to avoid duplicates?
- [ ] Are events/webhooks verified, deduplicated, and handled out-of-order?
- [ ] Do provider bounce/complaint events update suppression?
- [ ] Do OTP/security emails have expiration/reissue policies?
- [ ] Are manual resends distinct from retries and properly authorized?
- [ ] Does provider failover avoid triggering blindly on unknown acceptance?
- [ ] Are submission and delivery SLOs measured separately?
- [ ] Are timeout-after-DATA and crash-after-acceptance cases tested?
- [ ] Are logs/metrics free of recipients, bodies, attachments, and secrets?
- [ ] Are the decision, owner, and review triggers recorded in an ADR?

## 58. Key Takeaways

- **The application usually retries submissions not yet confirmed accepted by the provider.**
- **The delivery platform usually retries downstream delivery after accepting/queueing.**
- Both retry layers complement each other with clear ownership, never resending an already-accepted notification together.
- `JavaMailSender` is an SMTP sending abstraction; it does not include a durable outbox or provider delivery tracking.
- SMTP `250` after DATA and provider accepted receipts are **not** proof of Inbox delivery.
- Client-side pre-acceptance SMTP 4xx differs from remote 4xx after provider acceptance.
- API 429 or definite pre-accept transient errors usually belong to application retries.
- Timeouts after DATA, lost responses, or crashes after provider acceptance can be `AMBIGUOUS`.
- `Message-ID` does not create exactly-once email delivery.
- Provider idempotency keys and status APIs must be verified against actual contracts.
- Durable intents/transactional outboxes protect business commits prior to sending.
- An outbox does not make SMTP and database commits atomic; state machines/leases/reconciliation are still needed.
- Backoff, jitter, retry budgets, and expiry prevent storms and sending stale emails.
- Consent, suppression, and recipient eligibility must be rechecked prior to submission.
- Provider deferred/queued events are not requests for the application to resend.
- Webhooks can duplicate and arrive out of order; verify, deduplicate, and update state carefully.
- User-requested resends are **new notifications**, not retries of delivered notifications.
- New OTPs/reset links must be issued by security workflows, not by copying old raw mail.
- Measure submission latency and delivery lag separately with matching evidence.
- Architecture must explicitly document trade-offs among lost mail, duplicates, latency, cost, and vendor capabilities.

**Core principle:** Do not ask "should we retry in Spring or at the provider?" as an either-or choice. Ask **"has the message been accepted by the platform yet, and which layer has enough information to retry safely at this stage?"** Let the application protect business intent and handle pre-acceptance submissions; let the provider handle post-acceptance delivery attempts; keep an `AMBIGUOUS` state for unconfirmed outcomes. That boundary makes a Spring Framework Mail system resilient without creating duplicate-send loops.
