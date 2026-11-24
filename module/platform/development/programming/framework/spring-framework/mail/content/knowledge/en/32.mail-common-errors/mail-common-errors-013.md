# Retrying After a Timeout Without Considering Whether the Server Already Accepted

In **Spring Framework Mail**, a dangerous operational mistake is catching every exception from `JavaMailSender.send(...)` and immediately resending the email under the assumption: **“No success result observed means the SMTP server has not received the message.”** That assumption is false in distributed networks.

For example, an application is sending an invoice email to a customer. It has already transmitted the entire SMTP `DATA` payload, the SMTP relay has queued the email and prepared to return `250 OK`, yet the network connection breaks right before the application receives the reply. `JavaMailSender` may report a timeout or connection error; thinking it failed, the application immediately retries. Result: **the relay can accept two identical emails**, even though the application generated only one business request.

The issue is not “whether to retry” in general, but **knowing whether the previous attempt’s outcome is certain enough**. If there is proof the SMTP server rejected the message before accepting it, retrying may be appropriate. If the server already accepted it, do not submit again. If the outcome is undetermined, record **UNKNOWN**, reconcile when possible, and apply a controlled decision based on the email type.

This lesson analyzes the exact moments duplicates can arise in SMTP, how Spring Mail/Jakarta Mail reports errors, limitations of `Message-ID` and idempotency keys, transactional outbox design, attempt history, lease/recovery, reconciliation options, testing “server accepted but client timed out” failures, and an operations runbook.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why a timeout does not prove the SMTP server has not accepted the email.
2. Describe the stages `CONNECT → EHLO/TLS/AUTH → MAIL FROM → RCPT TO → DATA → final 250`.
3. Distinguish **SMTP submission accepted**, **delivery deferred**, **delivered**, and **landed in Inbox**.
4. Identify evidence for `ACCEPTED`, `PROVEN_NOT_ACCEPTED`, and `UNKNOWN` outcomes.
5. Classify connect/read/write timeouts by **protocol stage**, rather than looking solely at exception classes.
6. Understand the limitations of `MailSendException`, `MailAuthenticationException`, and nested Jakarta Mail exceptions.
7. Avoid the mistake `catch (MailException) { retry(); }`.
8. Design message keys, attempt IDs, outboxes, and unique business idempotency keys.
9. Handle crashes after SMTP acceptance but before database commit.
10. Avoid automatically retrying a job whose lease expired when the network outcome is unclear.
11. Know when provider logs/APIs/webhooks can be used for reconciliation.
12. Understand why RFC `Message-ID` or custom headers do not provide exactly-once SMTP.
13. Handle partial success when sending to multiple recipients or multiple messages.
14. Configure retry budgets, exponential backoff, and dead-letter states.
15. Write unit/integration tests with fault injection after `DATA`.
16. Operate `UNKNOWN` jobs without increasing spam, duplicates, or data leaks.

## 2. Real-world scenario: the same email sent twice

Suppose the system sends a payment notification:

```text
Business event:
Payment #P-1001 completed
             |
             v
Email job msg-1001
             |
             v
Spring JavaMailSender
             |
             v
SMTP relay
             |
             v
Recipient mailbox
```

On the first attempt:

```text
Application                         SMTP relay
     |                                   |
     |---- TCP/TLS/AUTH ---------------->|
     |---- MAIL FROM ------------------->|
     |---- RCPT TO --------------------->|
     |---- DATA ------------------------>|
     |<--- 354 Start mail input --------|
     |---- headers + body ------------->|
     |---- end-of-DATA <CRLF>.<CRLF> -->|
     |                                   |
     |                                   | queue message
     |                                   | prepare 250 OK
     |<---------- network breaks --------X
     |                                   |
     | java.net.SocketTimeoutException   |
     |                                   |
     v                                   v
Application thinks "failed"       Relay has accepted mail
     |
     | retry same email immediately
     v
SMTP relay accepts second copy
```

The outcome can be two emails:
- Same subject.
- Same content.
- Same recipient.
- Even the same RFC `Message-ID` if the application tries to reuse it.
- Yet still **two independent SMTP submissions**.

If it is a newsletter, the recipient is annoyed. If it is a payment confirmation email, they may mistakenly think the transaction ran twice. For emails with action links, duplicates also cause confusion at the business layer.

**Core conclusion:** A client-side error only proves **the client did not finish observing success**; it does not prove the server did not execute the side effect.

## 3. Distinguishing three types of email “success”

A mail application must separate:

| State | Evidence | Does NOT prove |
|---|---|---|
| **QUEUED** | App stored outbox/job or queue accepted request | SMTP server received it |
| **SMTP_ACCEPTED** | SMTP server/relay accepted submission per appropriate final reply | Delivered to recipient mailbox |
| **DELIVERED** | Provider/receiver emitted delivery event per their definition | User saw it or it definitely landed in Inbox |
| **OPENED/ENGAGED** | Appropriate tracking/interaction signal | Every recipient read it; tracking is always reliable |

Calling:

```java
javaMailSender.send(mimeMessage);
```

without throwing usually indicates submission completed according to the transport API in use, **not** that the email was opened by the recipient or guaranteed to reach the Inbox.

### 3.1. Even after provider acceptance, delivery can still be deferred

The SMTP relay queues the email, yet the destination server temporarily returns an error. The provider may continue retrying delivery for hours per its policy.

```text
Application -> Provider: SMTP_ACCEPTED
Provider -> Receiver: 451 temporary failure
Provider -> Receiver later: retry
```

**Do not submit a new email copy** via Spring Mail simply because delivery status is temporarily `DEFERRED`. Those are two different retry layers:
- Application retries **submission**.
- Provider retries **delivery** after taking responsibility.

### 3.2. Provider retries are not application retries

If the provider is retrying delivery, the application should not intervene with a new email unless there is a controlled backup delivery design that explicitly accepts duplicate risk.

## 4. Walking through each stage of an SMTP transaction

A typical SMTP submission session:

```text
1. TCP connect
2. (Implicit TLS or EHLO + STARTTLS)
3. EHLO / authentication
4. MAIL FROM:<sender>
5. RCPT TO:<recipient>
6. DATA
7. Server: 354
8. Client: headers + body + end-of-DATA
9. Server: 250 (if accepted)
10. QUIT / connection close
```

Replies at each stage carry different meanings.

### 4.1. Connect, TLS, and AUTH

If the client **has not established a connection** or **has not sent any message-sending command**, the relay could not have received the message from that attempt. For instance, a TCP connection refused before establishing an SMTP session can be evidence of non-submission.

However, this information must come from **actual protocol/timing evidence**, not merely from a generic outer exception class.

### 4.2. MAIL FROM and RCPT TO

`MAIL FROM` declares the envelope sender; `RCPT TO` declares a requested recipient. The server may accept a recipient at this stage, yet **that is not yet acceptance of the entire message body**.

With multiple recipients, some recipients may be accepted while others are rejected. Such exceptions/partial successes must be handled separately.

### 4.3. DATA and the 354 reply

When the client sends `DATA`, the relay typically replies `354`, meaning the client may transmit content. `354` **does not mean the message has been accepted into the queue for delivery**.

### 4.4. End of DATA

Once the client finishes sending content and the terminator `<CRLF>.<CRLF>` (per SMTP DATA framing), the server processes it and returns the final reply.

- **Final 2xx after DATA:** the message was accepted by the server at the submission stage.
- **Final 4xx/5xx after DATA:** the server reported non-acceptance per protocol semantics; handle by code type and policy.
- **No observed reply:** you cannot reliably infer accepted vs rejected from a timeout alone.

A `250` returned for `EHLO` or `RCPT TO` does not substitute for the final `250` after DATA.

### 4.5. QUIT and disconnect

A connection drop after the server already returned the final `250` can still surface an error or unclear state to the caller, depending on how the library manages shutdown. An already-accepted message is not rolled back simply because `QUIT`/TCP close did not finish cleanly.

## 5. Evidence matrix at each phase

| Verified failure point | Might server already have accepted the email? | Conservative classification |
|---|---|---|
| Validation error, SMTP not called | No | `PERMANENT_INPUT_FAILURE` |
| DNS resolution failed before TCP connect | Not for this attempt | `PROVEN_NOT_ACCEPTED` |
| TCP connect refused before SMTP session | Not for this attempt | `PROVEN_NOT_ACCEPTED` |
| TLS handshake failed before content transfer | Not for this attempt | `PROVEN_NOT_ACCEPTED` / config error |
| AUTH rejected before sending message | Not for this attempt | `PROVEN_NOT_ACCEPTED` / auth error |
| MAIL FROM explicitly rejected | Message not accepted | `PROVEN_NOT_ACCEPTED` |
| RCPT TO explicitly rejected before DATA | Message not accepted for that recipient | Handle per recipient |
| Server returned final 4xx/5xx after DATA and client clearly received reply | Server reported non-acceptance per protocol | `PROVEN_NOT_ACCEPTED` per evidence |
| Timeout while transferring DATA | Not conclusively proven | `UNKNOWN` unless negative proof exists |
| Timeout waiting for reply after end-of-DATA | **May already have accepted** | `UNKNOWN` |
| Client received final 250 after DATA | Acceptance evidence present | `SMTP_ACCEPTED` |
| Client received 250 but DB update failed | Accepted, DB not recorded | Needs reconciliation / do not resend blindly |
| Provider reports deferred after SMTP_ACCEPTED | Already accepted; delivery pending | Do not retry submission |
| Consumer/queue failure after message was sent | May already have accepted | `UNKNOWN` without durable receipt |

**Note:** Error codes from transport wrappers sometimes do not expose the exact phase. Whenever non-acceptance cannot be proven, choose **UNKNOWN** instead of “definitely retryable”.

## 6. Timeouts are not a single error type

In Spring Mail/Jakarta Mail, common timeouts include:

| Setting | Purpose | What a timeout suggests |
|---|---|---|
| `mail.smtp.connectiontimeout` | TCP connect wait limit | Connection not established within allowed time |
| `mail.smtp.timeout` | Socket read limit | Waiting on an SMTP/TLS reply in some phase |
| `mail.smtp.writetimeout` | Socket write limit | Data write did not finish within allowed time |
| Worker/job deadline | Overall attempt limit at application layer | Attempt expired; need to know if side effects happened |
| Queue receive timeout | Waiting to pull a job from queue | Says nothing about whether SMTP occurred |

### 6.1. Connect timeout

If you verify the connection never succeeded and no SMTP protocol exchange ran, retrying after backoff can be safe with respect to duplicate submission. Still account for provider outages, quotas, and routing permissions.

### 6.2. Read timeout

`SocketTimeoutException: Read timed out` **does not tell you whether it was waiting for the greeting, EHLO, AUTH, 354, or final 250**. The exact same exception class can occur:
- before sending the message;
- after finishing DATA transfer;
- after the server may already have accepted.

Therefore **never classify read timeout = definitely unsent**.

### 6.3. Write timeout

If a socket write times out while transmitting data, the client may not know exactly how far the server read. Data written to the socket may sit in network buffers, and the server may have read part or all of it.

Do not assume “write did not complete so the server did not receive the message” without solid proof that end-of-DATA never reached the server.

### 6.4. Total deadline

An attempt may span multiple SMTP commands, MIME processing, and database writes. An individual socket timeout **is not** the total deadline. If a worker is killed for exceeding its deadline, the chance of an undetermined outcome rises further.

## 7. Spring Boot configuration: reasonable timeouts without altering semantics

SMTP submission port 587 with STARTTLS example:

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

Ports/hostnames are illustrative only. Actual values depend on provider, infrastructure, and empirical measurements.

### 7.1. Too short timeouts can increase UNKNOWN

Reducing `mail.smtp.timeout` from 30 seconds to 1 second does not automatically make the system more reliable. If the provider responds slowly at final DATA acceptance, an overly short timeout can increase `UNKNOWN` attempts and create harder retry decisions.

### 7.2. Too long timeouts are also risky

Excessively long timeouts tie up worker threads, delay shutdown, grow backlogs, and can cause outbox leases to expire before the SMTP attempt finishes.

Choose timeouts based on:
- SLA/provider latency;
- concurrency budget;
- worker lease duration;
- network path;
- throughput;
- reconciliation capability;
- how long the business accepts waiting.

### 7.3. TLS mode must be right

587 commonly uses `smtp` + STARTTLS required. 465 commonly uses implicit TLS, e.g., `mail.smtp.ssl.enable=true`. The wrong TLS mode can cause connection/handshake errors, yet **when endpoint details are clear**, never mask errors by disabling certificate hostname verification.

## 8. How does a catch block cause duplicates?

Very common anti-pattern:

```java
public void sendWithRetry(MimeMessage message) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            mailSender.send(message);
            return;
        } catch (MailException ex) {
            // Wrong: unknown whether the server already accepted it.
            log.warn("Send failed; retrying", ex);
        }
    }
}
```

Problems:
1. `MailException` does not carry within its exception type a guarantee that the server has not received the message.
2. Immediate retries can send duplicates after a final-DATA timeout.
3. No backoff/rate limit.
4. No persisted attempt history.
5. No `UNKNOWN` state.
6. No distinction between permanent and transient failures.
7. Reusing the same mutable `MimeMessage` can bring additional state/header issues.
8. No idempotency at the business layer.
9. If the process crashes between attempts, there is no basis to decide whether to continue.
10. Does not track whether the provider is already retrying delivery.

**Never infer “safe to retry” merely because an exception was thrown from `send()`.**

## 9. How can Spring JavaMailSender report failures?

Spring Mail commonly provides:
- `MailException`: base exception hierarchy.
- `MailSendException`: failure during sending.
- `MailAuthenticationException`: authentication-related failure.
- `MailPreparationException`: failure creating the message in preparation.
- `MailParseException`: failure parsing message/address.
- Nested Jakarta Mail `MessagingException`, `SendFailedException`, and various network causes.

The class name reflects **the area where the library detected the failure**, not proof of relay non-acceptance.

### 9.1. MailSendException and failed messages

`MailSendException` exposes APIs to inspect messages reported as failed in a multi-message send call. Yet “failed” in client exception handling does not mean the SMTP server definitely **never accepted** the corresponding message.

In particular:
- The connection may have dropped after final DATA.
- A multi-message batch may have partially submitted.
- Exception causes may be wrapped through several layers.
- Providers may return proprietary responses or partial recipient results.

Never write resend logic relying solely on `MailSendException.getFailedMessages()` as if it were the set “definitely not accepted by the relay”.

### 9.2. MailAuthenticationException

If you confirm AUTH was rejected before message content, you can conclude that attempt was not accepted. However, the right policy is usually fixing the secret, scope, or provider configuration, **not retrying continuously** every few milliseconds.

### 9.3. MessagingException.getNextException()

Jakarta Mail allows chaining detailed exceptions. During diagnosis, you may need to inspect:
- chained `MessagingException`;
- underlying socket exception;
- SMTP reply/command;
- provider-specific exception;
- phase the wrapper was executing.

Do not print the entire exception chain to public logs if it can contain recipients or sensitive SMTP metadata.

### 9.4. MIME build failures before networking

If validation explicitly fails **before calling `send(...)`**, such as a rejected recipient format while constructing the message, that is an input/configuration error, not an UNKNOWN SMTP submission outcome.

However, if code builds MIME while also triggering I/O through provider-specific operations, separate boundaries to know when network side effects begin.

## 10. Defining a shared outcome: not just a boolean

A safer model:

```java
public enum SubmissionOutcome {
    SMTP_ACCEPTED,
    PROVEN_NOT_ACCEPTED_RETRYABLE,
    PROVEN_NOT_ACCEPTED_PERMANENT,
    UNKNOWN
}
```

Meaning:

| Outcome | Auto-retry allowed? | Notes |
|---|---|---|
| `SMTP_ACCEPTED` | **No** | Provider accepted the submission |
| `PROVEN_NOT_ACCEPTED_RETRYABLE` | Possible | Only after policy/backoff/quota checks |
| `PROVEN_NOT_ACCEPTED_PERMANENT` | No | Fix data/credentials/configuration |
| `UNKNOWN` | **No blind retry** | Reconciliation or controlled policy decision |

### 10.1. UNKNOWN is useful information

`UNKNOWN` does not mean a low-quality system; it is the accurate representation of missing information. A state machine lacking `UNKNOWN` is often forced to **lie** using one of two labels:
- FAILED, then retries create duplicates.
- SUCCESS, then it may drop an email that was never accepted.

### 10.2. Do not lump UNKNOWN into RETRY_WAIT

If the scheduler only queries `status IN ('PENDING','RETRY_WAIT')`, keep `UNKNOWN` in a separate state that is never auto-claimed. Only after investigation completes does the system transition to the appropriate action per policy.

### 10.3. Where can ACCEPTED come from?

Clear sources include:
- the client receives final SMTP 250 for that exact message;
- provider APIs/logs furnish acceptance evidence reliably linkable to the attempt;
- a verified delivery event sufficiently proves upstream received the email.

Never treat an ambiguous `250` log for EHLO/RCPT as proof of acceptance; phase/correlation must match.

## 11. Distinguishing logical email, attempt, and provider submission

One business email can have multiple attempts, yet **that is no justification for multiple successful submissions**.

```text
Business event: order-1001-paid
    |
    v
Logical email:
messageKey = msg-1001
    |
    +--> attempt att-1
    |      provider A
    |      status = PROVEN_NOT_ACCEPTED_RETRYABLE
    |
    +--> attempt att-2
           provider A
           status = SMTP_ACCEPTED
           |
           +--> delivery deferred
           +--> delivered
```

Once the second attempt is `SMTP_ACCEPTED`, the application does not submit a third attempt simply because no delivery event has arrived yet.

### 11.1. Message key

`messageKey` is an application-generated key for one **logical email**. It stays constant across retries and reconciliation.

### 11.2. Attempt ID

`attemptId` is the key for one **provider interaction attempt**. Each attempt has:
- provider/route;
- start time;
- completion/outcome;
- safe error code;
- optional provider reference;
- correlation metadata.

### 11.3. Provider message ID

If the provider returns a message ID/queue ID via SMTP response/API/webhook, store it separately. Do not assume generic SMTP always exposes a standardized ID for lookup.

### 11.4. RFC Message-ID

The `Message-ID` header is RFC email metadata, **not** an idempotency protocol enforced by SMTP servers. Two submissions sharing a Message-ID can still produce two messages in the mailbox.

## 12. Business-layer idempotency differs from exactly-once SMTP

A system can prevent a business event from creating two jobs:

```text
PaymentCompleted(orderId=1001)
     |
     v
Unique business key:
tenantId + eventType + orderId + notificationType
     |
     v
One email outbox row
```

Yet once the job exists, SMTP submission itself can be ambiguous.

### 12.1. What can idempotency protect against?

- HTTP client retries do not create two outbox rows for the same request.
- Event bus redelivery does not create two logical emails.
- Multi-replica schedulers do not create two duplicate occurrences.
- Worker claims can use unique constraints to prevent two concurrent attempts per policy.

### 12.2. What can idempotency NOT protect against?

- SMTP transport does not natively understand business keys.
- SMTP relays are not required to deduplicate by `X-Idempotency-Key`.
- RFC Message-ID is not a mailbox uniqueness key.
- A client retry after UNKNOWN can still produce two accepted submissions.

### 12.3. Three guarantees to separate

| Claim | Can it be built? |
|---|---|
| One business event creates one logical email | Yes, with a unique business key |
| Only one worker claims a job at any moment | Yes, with atomic claim/lease |
| Exactly-once SMTP submission across arbitrary network failures | **Cannot be guaranteed by default with generic SMTP** |

Do not advertise “exactly once email delivery” just because you added database transactions or a queue idempotency key.

## 13. Transactional outbox to preserve logical emails across failures

A resilient design:

```text
Business transaction
    |
    +-- update business state
    +-- insert email_outbox(messageKey, PENDING)
    |
    v
Commit
    |
    v
Outbox dispatcher
    |
    v
Claim job + attempt record
    |
    v
JavaMailSender.submit outside DB transaction
    |
    +--> accepted
    +--> proven rejected/transient
    +--> unknown
    |
    v
Persist outcome
```

Why is an outbox needed?
- No lost requests when a process crashes.
- Preserves send attempt history.
- Prevents producers from creating duplicate jobs via unique keys.
- Enables controlled retry/backoff.
- Provides a place to store `UNKNOWN` to prevent dangerous replays.
- Supports manual intervention and reconciliation.

### 13.1. Do not hold a database transaction across an SMTP call

An anti-pattern:

```java
@Transactional
public void createAndSendEmail(...) {
    businessRepository.save(...);
    mailSender.send(...);
    outboxRepository.markAccepted(...);
}
```

If the SMTP server accepted the message while the DB commit failed, database rollback **cannot recall the email**. When the business event is reprocessed, the email may be submitted again.

The right design commits the business event + outbox **first**, submits outside any DB transaction, and records the outcome in a separate transaction.

## 14. Reference outbox and attempt history schema

PostgreSQL example:

```sql
CREATE TABLE email_outbox (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    business_event_key VARCHAR(160) NOT NULL,
    category VARCHAR(40) NOT NULL,
    recipient_ref VARCHAR(256) NOT NULL,
    payload_ref VARCHAR(512) NOT NULL,
    status VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_email_business_event
        UNIQUE (tenant_id, business_event_key),
    CONSTRAINT ck_email_attempt_count
        CHECK (attempt_count >= 0)
);

CREATE TABLE email_submit_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES email_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    provider_key VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(48) NOT NULL,
    safe_error_code VARCHAR(120),
    smtp_phase VARCHAR(48),
    provider_reference VARCHAR(255),
    correlation_key VARCHAR(160),
    CONSTRAINT uq_email_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_email_outbox_unknown
    ON email_outbox(updated_at)
    WHERE status = 'UNKNOWN';
```

This is an illustrative schema, omitting full CHECK constraints, retention, access controls, or delivery statuses; production must expand it per requirements.

### 14.1. Why have both outbox and attempt tables?

The outbox describes **one logical email**. An attempt describes **one actual send attempt**. If the first attempt timed out and an operator needs to investigate, attempt history is essential to know:
- which provider was used;
- when it started;
- which phase failed, if known;
- whether SMTP acceptance was received;
- which correlation key can query the provider.

### 14.2. Content snapshots and access permissions

If email content changes between retries, the recipient may receive different versions. Store:
- template ID/version or rendered snapshot;
- recipient/sender identity;
- attachment references with explicit lifetimes;
- non-sensitive business parameters;
- appropriate data retention/encryption.

Do not retain plaintext password reset tokens, OTPs, or customer data longer than necessary solely to support retries.

## 15. State machine for submissions with UNKNOWN outcomes

An example:

```text
           PENDING
              |
              v
          CLAIMED
              |
              v
           SENDING
         /    |     \
        /     |      \
       v      v       v
 SMTP_ACCEPTED  RETRY_WAIT  UNKNOWN
                    |         |
                    v         v
                 PENDING   RECONCILING
                              |
               +--------------+-------------+
               |              |             |
               v              v             v
         CONFIRMED_       CONFIRMED_     UNRESOLVED
          ACCEPTED        NOT_ACCEPTED
               |              |             |
               v              v             v
         STOP SUBMIT      SAFE RETRY     POLICY/REVIEW
```

The names are suggested domain states; they are not built-in Spring Mail enums.

### 15.1. ACCEPTED terminates submission retries

After `SMTP_ACCEPTED`, subsequent states such as `DEFERRED`, `DELIVERED`, and `BOUNCED` belong to separate **delivery tracking**.

### 15.2. Retry wait is strictly for retryable outcomes

`RETRY_WAIT` should be entered when:
- there is evidence the attempt was not accepted;
- the error is classified as transient;
- retry budget has not been exhausted;
- the message has not expired;
- the route remains permitted.

### 15.3. UNKNOWN has no automatic “retry now” deadline

You can set a deadline for reconciliation or manual review, yet hitting that timeout is not proof of non-delivery. If the system chooses to resend after the deadline while still UNKNOWN, that is a **duplicate-risk-accepting policy**, which must be distinguished from a “safe retry”.

## 16. Atomic claim and lease do not solve SMTP ambiguity

A dispatcher using PostgreSQL:

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

A short transaction can claim the job and insert an attempt record. After committing, the worker invokes SMTP.

### 16.1. Atomic claims prevent two workers from sending simultaneously

When two workers poll together, `FOR UPDATE SKIP LOCKED` distributes work via DB row locking so the same row is not claimed twice at the same moment. This is an important safeguard.

### 16.2. Yet a worker can still crash after SMTP acceptance

```text
TX1: claim job; commit
      |
      v
SMTP: server accepted DATA
      |
      v
worker process crashes
      |
      v
TX2: mark accepted never executes
```

After a restart, the DB may still show `SENDING` with an expired lease. If worker recovery resets all stale `SENDING` rows back to `PENDING`, it will **duplicate** emails that were actually accepted.

### 16.3. Lease expiry is not proof of non-submission

Lease expiry only shows the worker failed to update/renew ownership on time. It does not say whether SMTP received the message.

Thus stale `SENDING` requires:
- checking attempt history;
- classifying by phase evidence if present;
- transitioning to `UNKNOWN` when evidence is missing;
- reconciling before deciding to resubmit.

### 16.4. Fencing tokens only protect DB state

Example outcome update:

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

If 0 rows match, the worker no longer holds a valid lease. Do not overwrite newer state. However, fencing **cannot stop an SMTP server from having accepted a message from a stale worker**.

## 17. Database and SMTP cannot commit atomically together

The difference between a local transaction and a network side effect:

```text
Database transaction             SMTP relay
        |                            |
        | BEGIN                      |
        | UPDATE status=SENDING      |
        | COMMIT                     |
        |                            |
        |---- send email ----------->|
        |<--- SMTP 250 OK -----------|
        |                            |
        | BEGIN                      |
        | UPDATE accepted            |
        | COMMIT (may fail!)         |
```

No standard database transaction can include a provider’s SMTP server as a participant supporting 2-phase commit.

### 17.1. Trying to send inside a transaction does not solve it either

Putting `@Transactional` around `send()` does not make SMTP a rollbackable resource. The DB rolls back, while an accepted email cannot be recalled.

### 17.2. Outbox gives at-least-once execution, not automatic exactly-once effect

An outbox ensures work is not lost in the application. Yet if an UNKNOWN attempt must be retried, the **external effect** can happen more than once.

A well-designed system must decide:
- Which emails prioritize **no loss** over **no duplicate**?
- Which emails prioritize avoiding duplicates?
- Does the provider support genuine request idempotency?
- Can we reconcile before retrying?
- Is manual review acceptable?

This is a business and operational decision, not merely a Java annotation.

## 18. Creating message keys and idempotency keys

Example of a payment event:

```text
tenantId: tenant-7
businessEvent: payment-settled
paymentId: pay-1001
notificationType: receipt-v1

business key:
tenant-7|payment-settled|pay-1001|receipt-v1

messageKey:
msg-4a3... (opaque UUID)
```

Upon event bus redelivery, the unique business key prevents creating a second logical email. However, if the first SMTP attempt is UNKNOWN, the same message key **does not guarantee the relay deduplicates it**.

### 18.1. Do not reuse HTTP idempotency keys carelessly

Client-supplied idempotency keys must be scoped by tenant/operation, validated, and given retention bounds. Never let tenant A guess tenant B’s key and read its result.

### 18.2. Tracking headers are not duplicate-prevention commands

You can attach:

```java
mimeMessage.setHeader(
    "X-Application-Message-Key",
    messageKey
);
mimeMessage.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

These headers can assist reconciliation if the provider preserves them, yet:
- not every provider supports querying by custom headers;
- recipients may be able to see the headers;
- SMTP does not automatically deduplicate by header;
- do not embed secrets or sensitive customer IDs.

### 18.3. RFC Message-ID is separate metadata

`Message-ID` commonly helps mail clients thread emails, yet the same value can appear in two SMTP submissions. Do not treat it as a guarantee that the recipient will receive only one copy.

### 18.4. “Recipient-side deduplication” is unreliable

Some mail clients may fold threads or make duplicates less obvious, but that behavior varies by system. Never rely on UI grouping as protocol-level duplicate prevention.

## 19. Designing a Spring Mail adapter with conservative outcomes

An outcome-normalizing adapter must especially avoid the mistake “exception == NOT_ACCEPTED”.

Illustrative code example:

```java
package com.example.mail;

import java.time.Instant;

public enum SubmitStatus {
    ACCEPTED,
    UNKNOWN
}

public record SubmitReceipt(
    String messageKey,
    String attemptId,
    SubmitStatus status,
    Instant observedAt
) {}
```

Adapter:

```java
package com.example.mail;

import java.time.Clock;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class ConservativeSmtpGateway {

    private final JavaMailSender mailSender;
    private final Clock clock;

    public ConservativeSmtpGateway(
            JavaMailSender mailSender,
            Clock clock) {
        this.mailSender = mailSender;
        this.clock = clock;
    }

    public SubmitReceipt submit(
            MailDraft draft,
            String attemptId) {

        MimeMessage mime = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(draft.from());
            helper.setTo(draft.to());
            helper.setSubject(draft.subject());
            helper.setText(
                draft.plainText(),
                draft.htmlText()
            );

            mime.setHeader(
                "X-Application-Message-Key",
                draft.messageKey()
            );
            mime.setHeader(
                "X-Mail-Attempt-ID",
                attemptId
            );

        } catch (MessagingException ex) {
            // Input/preparation error before calling SMTP.
            throw new MailPreparationFailure(
                "MIME_PREPARATION_FAILED", ex
            );
        }

        try {
            mailSender.send(mime);

            return new SubmitReceipt(
                draft.messageKey(),
                attemptId,
                SubmitStatus.ACCEPTED,
                clock.instant()
            );
        } catch (MailException ex) {
            // No phase evidence: conservative = UNKNOWN.
            throw new SubmissionOutcomeUnknown(
                draft.messageKey(),
                attemptId,
                ex
            );
        }
    }
}
```

`MailDraft`, `MailPreparationFailure`, and `SubmissionOutcomeUnknown` are application-defined models/exceptions. The example intentionally avoids classifying every Spring Mail error as safe to retry solely by exception class.

### 19.1. Why is the conservative default UNKNOWN?

Through the `JavaMailSender` abstraction, the adapter does not necessarily observe individual SMTP commands and replies. If send throws an exception, it may not know whether the relay accepted the content.

Defaulting to `UNKNOWN` prevents duplicates until stronger evidence is obtained.

### 19.2. When can PROVEN_NOT_ACCEPTED be assigned?

When the system has **reliable evidence** that an attempt was not accepted, such as:
- validation failed before making any network call;
- TCP connect failure verified before an SMTP session existed;
- SMTP server returned a refusal at a verified phase;
- provider API returned an error with an explicit non-acceptance contract.

Do not “guess phase” from generic exception wording. You can build a classifier backed by transport instrumentation or a specialized SMTP adapter, provided it is tested against your actual implementation.

### 19.3. Try/catch alone is not enough; outcome must be persisted

A gateway can throw `SubmissionOutcomeUnknown`. The application service must persist that outcome to durable state and halt automatic resubmission. Simply throwing the exception out to a queue consumer so the broker immediately redelivers brings back the exact original bug.

## 20. Worker orchestration: save UNKNOWN instead of retrying blindly

A sound processing flow:

```text
Claim due job
      |
      v
Create attempt record
      |
      v
Build validated MIME
      |
      v
SMTP submit
      |
      +--> returned successfully
      |       |
      |       v
      |    save SMTP_ACCEPTED
      |
      +--> explicit, proven non-acceptance
      |       |
      |       +--> transient -> RETRY_WAIT
      |       |
      |       +--> permanent -> DEAD_LETTER
      |
      +--> cannot determine acceptance
              |
              v
           save UNKNOWN
              |
              v
        reconciliation queue
```

### 20.1. Pseudocode

```java
ClaimedMail claim = repository.claimDueJob();

Attempt attempt = repository.startAttempt(claim);

try {
    SubmitReceipt receipt =
        smtpGateway.submit(claim.toMailDraft(), attempt.id());

    repository.markSmtpAccepted(
        claim.messageKey(),
        attempt.id(),
        receipt.observedAt(),
        claim.leaseToken()
    );

} catch (SubmissionOutcomeUnknown ex) {
    repository.markUnknown(
        claim.messageKey(),
        attempt.id(),
        "SMTP_ACCEPTANCE_NOT_OBSERVED",
        claim.leaseToken()
    );

    reconciliationQueue.requestReview(
        claim.messageKey(), attempt.id()
    );

} catch (MailPreparationFailure ex) {
    repository.markPermanentFailure(
        claim.messageKey(),
        attempt.id(),
        "MIME_PREPARATION_FAILED",
        claim.leaseToken()
    );
}
```

This pseudocode highlights the workflow, not standalone runnable source; repository, claim, lease, and failure mapping are components the project must implement. If DB persistence of `UNKNOWN` also fails, recovery must treat stale `SENDING` rows as potentially unknown after restart.

### 20.2. Watch transaction boundaries

- Claim/insert-attempt transaction: commit before SMTP.
- SMTP call: outside any DB transaction.
- Persist-outcome transaction: commit after SMTP.
- If outcome commit fails: do not auto-resend.
- Fencing tokens protect state writes from stale workers.

### 20.3. Do not unconditionally retry the send call itself in @Retryable

`@Retryable` or `RetryTemplate` can be helpful for transient operations, yet wrapping `JavaMailSender.send(...)` directly and catching every `MailException` can automatically resubmit an UNKNOWN message.

Retry frameworks **do not natively understand SMTP acceptance semantics**. Only retry when the classifier and state machine prove eligibility.

## 21. What is reconciliation and where do you start?

**Reconciliation** is the process of cross-checking an application attempt against provider/SMTP relay evidence to determine whether the message was accepted.

Possible sources:
- Provider dashboard or submission logs.
- Organization-managed SMTP relay queue logs.
- Provider API for looking up messages/submissions.
- Webhooks/event streams.
- Provider-supported message IDs/queue IDs/correlation keys.
- Logs from an organization-controlled intermediate gateway.
- Downstream confirmation signals when appropriate and authorized.

Not every SMTP provider supplies enough information to conclude, especially generic SMTP.

### 21.1. Usable correlation keys are required

Each attempt should capture:
- application messageKey/attemptId;
- provider route;
- connection/submission timestamps;
- appropriate envelope sender/recipient references;
- optional provider queue ID;
- optional opaque custom header;
- redacted SMTP transcript metadata if available.

Never log passwords, tokens, or full email content just to support searching.

### 21.2. Three reconciliation outcomes

**A. Confirmed accepted:**
- Record `SMTP_ACCEPTED`.
- Stop submission retries.
- Continue tracking delivery if the provider supports it.

**B. Confirmed not accepted:**
- Transition to retryable/permanent per evidence.
- Apply retry budget, deadline, and route policy.
- Do not auto-retry if recipient/consent changed.

**C. Inconclusive:**
- Keep `UNKNOWN/UNRESOLVED`.
- Route to manual review or dedicated policy.
- Never claim “failed” with certainty.

### 21.3. Do not treat “not visible in dashboard” as definitely unsent

Provider logs/APIs may:
- have indexing lag;
- have short retention;
- lack query permissions;
- suffer wrong time/recipient filters;
- omit certain SMTP paths.

**Absence of evidence is not automatically evidence of absence.** Conclude non-acceptance only when the tool/provider has a strong contract supporting that negative claim.

## 22. Do delivery webhook signals help?

Yes, within their scope.

A `delivered` webhook reliably linked to an attempt is strong evidence that the provider accepted and processed the message. However, **not receiving a webhook** does not prove the provider never accepted it.

Risks:
- webhook arrives late;
- webhook is dropped;
- provider retries callbacks;
- duplicate or out-of-order events;
- mis-mapped message IDs;
- provider ID differs from RFC Message-ID;
- missing signature verification;
- short data retention.

### 22.1. Webhooks must be authenticated

- Verify signatures per provider specification.
- Protect endpoints against replays.
- Deduplicate event IDs.
- Map events to the right tenant/provider/attempt.
- Prevent provider A events from overwriting provider B attempts.
- Store event history per retention policy.

### 22.2. Delivered does not necessarily mean Inbox

Some providers define delivered as “recipient server accepted”. That does not prove the message landed in Inbox rather than Spam, nor that the user read it.

## 23. When the provider lacks a reconciliation API

Generic SMTP sometimes offers no way to query a submission whose response vanished on the client side.

When inconclusive:
1. Record `UNKNOWN`.
2. Check deadline/email type.
3. Weigh the risk of **not sending** vs **sending a duplicate**.
4. Identify who holds authority to decide on resending.
5. If policy permits resending, explicitly record it as **resend with accepted duplicate risk**, not “safe retry”.
6. Reflect message key/attempt history and rationale in audit records.
7. Avoid triggering mass duplicates during widespread outages.

### 23.1. Emails carry different risk profiles

| Email type | Omission risk | Duplicate risk | Possible policy direction |
|---|---|---|---|
| Invoice/receipt | High | High UX/traceability impact | Reconcile/manual review, possibly send clear replacement |
| Password reset/OTP | Has deadline | Duplicate links/tokens cause confusion | Never blindly resend old tokens |
| Marketing/newsletter | Usually tolerates delay/skip | Spam complaints/reputation | Prioritize avoiding duplicates |
| Urgent alert | High | Some duplication may be tolerable | Escalate via another channel, approved policy |
| Scheduled report | Time-dependent | Duplicate reports create noise | Restrict retries past deadline |
| Internal notification | Depends on workflow | Often less severe | Define explicit tolerance thresholds |

This is an example decision framework, not an absolute rule. Business/legal owners must approve the actual policy.

### 23.2. A “replacement” notification can beat a speculative retry

When initial receipt delivery cannot be verified, the application can let users view the invoice inside their account and send a transparent follow-up notification per policy, rather than silently resending the same payload. Follow policy and avoid exposing payment data over insecure channels.

## 24. Can an HTTP email API with idempotency replace SMTP?

Some providers expose an **HTTP API** for email sending with an `idempotency key` or request reference. Where the provider genuinely enforces a deduplication contract, API retries can be safer than generic SMTP on certain timeouts.

Still, verify:
- Is the key scoped per account/endpoint or globally?
- How long is the deduplication window?
- Will a different payload with the same key be rejected or treated as the same request?
- Does an API retry return the prior result or create a new submission?
- Is the key persisted if the request was accepted but the response dropped?
- Do webhook/status lookups map by that key?
- Does the feature apply strictly to the **HTTP API**, not SMTP login on the same vendor?

Never assume a vendor supports idempotency over **SMTP** simply because its HTTP API has that feature.

### 24.1. Shared port design, distinct adapters

```text
OutboundMailPort
    |
    +--> SMTP JavaMailSender adapter
    |       generic SMTP: no standard idempotency
    |
    +--> HTTP Email API adapter
            idempotency only when vendor contract supports it
```

The domain service can use a unified message key, while each adapter exposes its real capabilities. Never hide UNKNOWN just so every provider returns the same boolean.

### 24.2. HTTP APIs still require observing outcomes

If a provider API returns 202 Accepted, that is acceptance of the API request, not proof the mailbox received the mail. Delivery events and suppressions still need separate tracking.

## 25. Retry budgets, backoff, and rate limits

Once **proven not accepted** and transient, retries must still be bounded.

Example policy:
- Maximum 4 attempts.
- Exponential backoff with jitter.
- Respect `Retry-After` or provider throttle guidance if available.
- Stop when the email expires.
- Cap concurrent submissions.
- Stay within account/provider quotas.
- Do not retry permanent errors without data/config changes.

### 25.1. Backoff calculation example

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryBackoff {

    public static Duration delayFor(int attemptNumber) {
        if (attemptNumber < 1) {
            throw new IllegalArgumentException(
                "attemptNumber must be positive"
            );
        }

        int exponent = Math.min(attemptNumber - 1, 5);
        long maxSeconds = Math.min(60L * (1L << exponent), 1800L);

        long delay = ThreadLocalRandom.current()
            .nextLong(1L, maxSeconds + 1L);

        return Duration.ofSeconds(delay);
    }
}
```

This is an illustrative jitter variant, not a mandatory formula. Backoff **applies only to retry-eligible attempts**; it does not turn UNKNOWN into retryable.

### 25.2. Circuit breakers do not alter individual email states

During an SMTP provider outage, a circuit breaker can block new submissions and protect the system. Yet a circuit breaker **cannot determine** whether existing UNKNOWN attempts made before opening were accepted.

### 25.3. Quotas per provider

With multiple providers:
- quotas may differ;
- credentials/verified From domains differ;
- failover must be authorized;
- provider B must not be used to bypass A’s suppressions or auth failures;
- an A timeout after DATA is unsafe to try on B immediately.

## 26. Queues and broker redelivery can create similar duplicates

Retry loops are not the only culprit. A system might use:
- RabbitMQ.
- Kafka.
- Spring Integration `QueueChannel`.
- JMS.
- Database scheduled jobs.

Example:

```text
Broker delivers mail job
       |
       v
Consumer calls JavaMailSender
       |
       v
SMTP accepts message
       |
       v
Consumer crashes before broker ACK
       |
       v
Broker redelivers same job
       |
       v
Consumer calls JavaMailSender again
       |
       v
DUPLICATE
```

### 26.1. Broker at-least-once does not mean SMTP exactly-once

The broker guarantees redelivery when a consumer fails to ACK, yet cannot roll back an SMTP relay side effect. It is the same dual-write problem as with databases.

### 26.2. Committing offsets after SMTP does not solve it automatically

With Kafka, if a consumer sends via SMTP and then fails to commit its offset, the record can be re-read. Kafka exactly-once processing for internal Kafka transactions does not make SMTP transport idempotent by default.

### 26.3. ACKing before SMTP is unsafe too

If the job is ACKed before sending, a worker crash can cause **lost emails**. Hence no single ACK position simultaneously guarantees no-loss and no-duplicate over arbitrary SMTP.

### 26.4. Durable attempt state and recovery are required

A consumer should:
1. Load logical email/outbox state.
2. Refuse to auto-send if already accepted/unknown.
3. Claim with an appropriate transaction/lock.
4. Create an attempt record.
5. Call SMTP.
6. Persist the outcome.
7. ACK the broker under an idempotency/recovery workflow.

On redelivery, the message key lets you look up state, while recognizing the DB might lack the receipt even if the provider accepted; hence reconciliation is still necessary.

## 27. Multi-recipient emails and partial success

Multi-recipient emails are a distinct case:

```text
MAIL FROM:<sender>
RCPT TO:<alice@example.net> -> 250
RCPT TO:<bob@example.net>   -> 550
RCPT TO:<carol@example.net> -> 250
DATA -> ...
```

Depending on the SMTP provider and Jakarta Mail configuration, the message may be submitted for a subset of recipients while others are rejected. A `MailSendException` or `SendFailedException` can represent a situation that is not purely “the whole email went unsent”.

### 27.1. Do not resend the entire recipient list

If Alice and Carol were included in a successful submission while Bob was rejected, resending the whole list can send Alice and Carol a second copy.

### 27.2. Track recipient outcomes when needed

For business emails needing per-recipient handling, one option is **one separate logical email per recipient**, enabling:
- independent retries;
- independent suppression;
- avoiding exposing recipient lists;
- individual tracking;
- reducing partial-recipient ambiguity.

If multi-recipient/batch sending is required, store accepted/refused recipients and verify how accurately the library reports partial sends. Retry only recipients **verified as not accepted**, rather than guessing from the outer exception.

### 27.3. sendPartial is a behavior to understand clearly

Some Jakarta Mail SMTP configurations control sending to valid recipients even when others are rejected (e.g., `mail.smtp.sendpartial`). Never enable or disable it casually without designing per-recipient result persistence.

### 27.4. Sending a MimeMessage array also has partial outcomes

`JavaMailSender.send(MimeMessage...)` can execute multiple submissions. If an error occurs mid-batch, do not assume the entire batch remained unaccepted by the relay. Per-message attempt tracking is much safer for retries.

## 28. SMTP provider accepted, yet delivery is slow

An easily confused scenario:

```text
09:00 JavaMailSender.send returns success
09:00 Provider status: accepted/queued
09:05 Provider attempts delivery; receiver temp rejects
09:20 Provider retries delivery
09:21 Provider reports delivered
```

If an application has a watchdog saying:
> “Not delivered within 10 minutes, retry submission.”

it can produce duplicates because the provider is already retrying delivery. Delivery SLAs must be managed differently:
- track deferred status;
- alert when thresholds are exceeded;
- do not create new submissions by default;
- review provider-specific cancellation/retry policies;
- potentially contact the recipient via another channel when business rules permit.

**Application SMTP submission timeout** and **provider delivery duration** are two independent variables.

## 29. Tokens, invoices, and deadlines when deciding resends

Some emails lose value after a cutoff:
- OTPs.
- Password resets.
- Verification links.
- Event reminders.
- Expiring promotions.
- Temporary approval requests.

If an attempt is UNKNOWN, retrying an hour later may deliver stale content even if no duplicate happens.

### 29.1. Three timestamps to record

- `sendAt`: earliest time eligible for submission.
- `nextAttemptAt`: time when a retry may be evaluated.
- `expiresAt`: final business cutoff after which sending is disallowed.

### 29.2. OTP/reset tokens must not be reused blindly

If a token has expired, do not retry the old email as if the token were still valid. Ask the user to restart the verification flow and create a fresh request with a new key, per security policy.

### 29.3. Business completion does not depend on email

Payment/order status must rest on transactions in the payment/order system, not on whether the client received an email. Email is a notification, not the transaction’s source of truth.

### 29.4. Duplicate action links must be guarded

Even if an email is sent twice, the system should protect business actions from executing twice: unique transaction IDs, one-time tokens, idempotent command handlers, and validation. That is defense-in-depth, not an excuse to spam duplicate emails.

## 30. Operational observability: separate attempts, accepted, and unknown

Useful metrics:

| Metric | Meaning |
|---|---|
| `mail_submit_attempts_total{provider,outcome}` | Attempts broken down by outcome |
| `mail_submit_unknown_total{provider}` | Count where acceptance is unknown |
| `mail_submit_accepted_total{provider}` | Submissions observed as accepted |
| `mail_submit_proven_rejected_total{provider,category}` | Failures proven not accepted |
| `mail_outbox_unknown_count` | Jobs awaiting reconciliation |
| `mail_outbox_stale_sending_count` | Lease-expired jobs needing inspection |
| `mail_reconciliation_duration_seconds` | Time taken to resolve outcome |
| `mail_reconciliation_resolved_total{result}` | How many UNKNOWNs were resolved |
| `mail_duplicate_suspected_total` | Suspected duplicate cases |
| `mail_provider_deferred_total{provider}` | Delivery deferred events if available |
| `mail_outbox_oldest_due_age_seconds` | Backlog lag |
| `mail_retry_attempts_total{reason}` | Retries permitted by policy |

Never use recipient, messageKey, or attemptId as Prometheus labels due to high cardinality and privacy risks.

### 30.1. Structured log per attempt

```json
{
  "event": "mail.submit.attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-2",
  "providerKey": "transactional",
  "outcome": "UNKNOWN",
  "reasonCode": "RESPONSE_NOT_OBSERVED_AFTER_DATA",
  "smtpPhase": "WAITING_FINAL_DATA_REPLY",
  "durationMs": 10015,
  "retryAutomatically": false
}
```

**Only record a specific `smtpPhase` when genuinely observed** via gateway/transport instrumentation. If using plain `JavaMailSender` without phase visibility, log `UNDETERMINED`; never fabricate evidence.

### 30.2. Trace security

An opaque correlation key may be placed in MIME headers per policy, but remember:
- recipients can inspect headers;
- providers may alter/strip headers;
- it is not a security credential;
- it must never carry tenant secrets, payment tokens, or sensitive data.

### 30.3. Alerts should be actionable

- UNKNOWN spiking after a deploy/JDK/provider change.
- SMTP read timeouts rising on a profile.
- Retry counts spiking unusually after connection drops.
- `UNKNOWN` jobs being re-claimed (state machine violation).
- Multiple SMTP provider accepted events appearing for the same message key.
- Reconciliation failing or provider logs expiring before cross-check.
- Stale sending attempts rising while worker leases fail to renew.

## 31. Runbook during widespread timeouts

### Step 1 — Contain and scope

Identify:
- Which provider/profile is affected.
- Failure timeframe.
- Whether failures are TCP connect, TLS, AUTH, or read timeouts after DATA.
- How many attempts carry acceptance risk.
- Job categories and deadlines.
- Any recent changes to deployments, networks, quotas, or certificates.

### Step 2 — Prevent dangerous automatic resends

- Temporarily pause the route or open the circuit breaker if needed.
- Protect UNKNOWN jobs from retry workers.
- Never bulk-reset all statuses to PENDING.
- Preserve attempt history and event logs.
- Ensure in-flight jobs drain and record their outcomes.

### Step 3 — Gather evidence

- App attempt IDs.
- SMTP provider account/route.
- Start/end timestamps.
- Safe exception class/code.
- SMTP phase if reliably recorded.
- Provider queue/submission IDs.
- Verified webhooks.
- Relay logs if under organization control.

Never extract plaintext credentials or raw bodies into incident tickets.

### Step 4 — Reconcile each group

| Group | Action |
|---|---|
| Proven accepted | Mark SMTP_ACCEPTED, do not resend |
| Proven non-accepted, transient | Backoff/retry within policy |
| Proven permanent reject | Dead-letter or fix input/config |
| Unclear | UNKNOWN + review/policy |
| Expired/cancelled | Do not submit |
| Provider accepted but deferred | Monitor delivery, do not resend from app |

### Step 5 — Controlled recovery

Once the network/timeout issue is resolved:
- test connect/TLS/AUTH against the right endpoint;
- smoke-test with an authorized mailbox;
- cap concurrency/quota when resuming;
- do not bulk-resend UNKNOWNs;
- track delivery/bounces and suspected duplicates.

### Step 6 — Postmortem

Document clearly:
- Why did timeouts occur?
- Which phase failed?
- How many were proven accepted?
- How many UNKNOWNs remain?
- Were any resends authorized with duplicate risk?
- Was sufficient evidence retained from providers/logs?
- Do timeouts, retry classifiers, outbox logic, or monitoring need changes?

## 32. Unit test: exceptions must not automatically turn a job into RETRY_WAIT

Orchestration test example:

```java
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class UnknownSubmissionPolicyTest {

    @Test
    void unknownOutcomeMustNotRetryAutomatically() {
        OutboxRepository repository =
            mock(OutboxRepository.class);
        SmtpGateway gateway =
            mock(SmtpGateway.class);

        MailWorker worker =
            new MailWorker(repository, gateway);

        MailJob job = TestJobs.pending("msg-1001");

        when(repository.claimOne()).thenReturn(job);

        doThrow(new SubmissionOutcomeUnknown(
            "msg-1001",
            "att-1",
            new java.net.SocketTimeoutException(
                "No SMTP final response"
            )
        )).when(gateway).send(job);

        worker.processOne();

        verify(repository).markUnknown(
            eq("msg-1001"), anyString()
        );

        verify(repository, never()).scheduleRetry(
            eq("msg-1001"), any()
        );

        verify(gateway, times(1)).send(job);
    }
}
```

`OutboxRepository`, `SmtpGateway`, `MailWorker`, and `TestJobs` are application/test-fixture types, not built-in Spring classes. The goal is asserting **one exception never spawns a second attempt** when the outcome is unclear.

### 32.1. Test the classifier with evidence

A unit test suite should cover:
- Pre-send validation failure → permanent.
- DNS/connect failure verified before SMTP → non-accepted.
- AUTH rejected before DATA → non-accepted, fix config.
- Timeout with unknown phase → UNKNOWN.
- Timeout waiting for final DATA reply → UNKNOWN.
- Proven final 250 → accepted.
- Clear final 4xx/5xx → rejected per SMTP semantics.
- Provider delivery deferred → do not resubmit.
- Receipt DB persist failure → stale/UNKNOWN recovery, no auto retry.

### 32.2. Do not test solely via exception message substrings

A check like:

```java
if (ex.getMessage().contains("timeout")) {
    retry();
}
```

is insufficient. The same string can appear across multiple phases. Tests should rely on structured evidence/state rather than provider/JDK message wording.

## 33. The most important integration test: accepted, yet the client missed 250

This is the test that catches “blind retry after timeout” bugs.

### 33.1. Fault-injecting SMTP server

Design an SMTP test server that can:

1. Accept TCP/TLS/AUTH in tests.
2. Receive `MAIL FROM` and `RCPT TO`.
3. Reply `354` to `DATA`.
4. Read the entire message through end-of-DATA.
5. Store the message into a test mailbox/queue.
6. **Withhold the final 250 from the client**, or drop the connection at that exact moment.
7. Once the client reports timeout, the test verifies the server stored one copy.

```text
JUnit worker                    Fake SMTP relay
      |                               |
      |--- DATA content -------------->|
      |--- end-of-DATA --------------->|
      |                                | stores message #1
      |<--- final 250 deliberately lost|
      |                                |
      | timeout                       |
      |                                |
      v                                v
outbox = UNKNOWN               accepted count = 1
      |
      v
next polling cycle
      |
      v
must NOT send again           accepted count remains 1
```

### 33.2. Core assertions

- Worker records `UNKNOWN`.
- No second automatic attempt is created.
- Outbox does not transition directly to `RETRY_WAIT`.
- The SMTP test server holds exactly one accepted message from the first attempt.
- When the job/worker restarts, it still does not resend.
- When provider evidence arrives, it reconciles to `SMTP_ACCEPTED`.
- Retry worker queries exclude `UNKNOWN`.
- Logs contain no credentials/email bodies.

### 33.3. GreenMail/Mailpit may not be enough

A standard SMTP sandbox is great for happy paths and MIME tests, yet not all of them offer an option to **deliberately drop the final DATA reply after storing the message**. Simulating this risk accurately may require a dedicated fake SMTP server or fault-injecting proxy.

Never induce such faults against production SMTP providers or test against real customer mailboxes.

### 33.4. What does this test prove and not prove?

This test proves **your system does not auto-retry UNKNOWN** in the simulated scenario. It does not prove a real provider behaves identically on every failure, nor does it establish an exactly-once SMTP guarantee.

## 34. Integration test: DB commit failure after acceptance

An even trickier case:

```text
Worker receives final SMTP 250
       |
       v
Provider accepted
       |
       v
DB update outcome fails
       |
       v
Worker crashes
       |
       v
Stale SENDING record remains
```

Test steps:

1. Persist an outbox job as `PENDING`.
2. Claim and create an attempt.
3. Fake SMTP gateway returns accepted.
4. Simulate database failure when persisting `SMTP_ACCEPTED`.
5. Restart the worker against the same DB.
6. Recovery detects stale `SENDING`.
7. Assert **no auto resend**.
8. Route to reconciliation/UNKNOWN.
9. If provider evidence confirms accepted, mark accepted.
10. Without evidence, keep unresolved and follow policy.

### 34.1. Do not trust leases blindly

If a worker loses its lease, another process can pick up the job. Yet leases/heartbeats are worker coordination mechanisms, not confirmation that external side effects did not occur.

### 34.2. Test fencing

An old worker attempting to write an outcome with an expired lease token must not overwrite a newer worker’s outcome. This protects database state; SMTP side effects still require separate management.

## 35. Integration test: multiple recipients and multiple messages

Also test these cases:

- Alice accepted, Bob rejected, Carol accepted.
- One message accepted, then the batch throws an exception on the next message.
- Retry policy does not resend to Alice/Carol.
- A suppressed recipient is still not resent through another provider.
- A message with the same RFC Message-ID is submitted twice and the test server may store two copies.
- Broker redelivery does not bypass outbox state.
- When a worker is paused, in-flight attempts drain per policy.
- When the provider reports deferred, the application creates no new attempt.

If your product sends a separate email per recipient, test idempotency on `(messageKey,recipientId)` rather than a single batch result.

## 36. Security and privacy during reconciliation

Timeouts are no excuse to weaken security.

### 36.1. Keep TLS and hostname verification intact

If timeouts happen after STARTTLS or TLS handshakes fail, fix the endpoint/network/certificate properly. Do not disable:
- `starttls.required` when required by policy;
- `mail.smtp.ssl.checkserveridentity`;
- CA chain verification.

Using `mail.smtp.ssl.trust=*` in production can hide certificate errors and increase MITM risk.

### 36.2. Do not log raw SMTP AUTH

A raw protocol trace can contain email addresses, message bodies, or authentication metadata. Only enable diagnostics under control, redact sensitive data, and restrict access.

### 36.3. Reconciliation dashboards need authorization

Operators inspecting UNKNOWN entries may view:
- recipient;
- subject;
- business reference;
- provider;
- correlation IDs.

Enforce tenant isolation, access auditing, and retention. Never let a tenant A operator view tenant B’s attempts.

### 36.4. Never use resends to bypass suppression

If a recipient has a hard bounce, spam complaint, or unsubscribe, the application must not send via provider B to “fix” provider A’s non-delivery. Consent/suppression policies must be checked at send time.

## 37. Common design mistakes

### “A timeout means unsent”

False. If the timeout occurred after end-of-DATA, the server may have accepted it. An UNKNOWN state is mandatory.

### “MailSendException means the entire email failed”

False. With multiple messages or recipients, there can be partial success or unobserved server-side acceptance. Track per-message/recipient state when the use case requires it.

### “Catch exception and retry three times on the same thread”

Easily creates duplicates, retry storms, and lost attempt history. Classify outcomes and use durable retry policies.

### “Adding @Retryable solves it”

No. Retry frameworks do not know whether the SMTP server accepted DATA. Only retry cases proven safe.

### “Keeping the same Message-ID makes the provider deduplicate”

No such guarantee exists in generic SMTP.

### “The broker delivers only once”

If a consumer crashes before ACK/offset commit, the broker can redeliver. Even without redelivery, an application timeout can still leave the outcome unclear.

### “Transactional outbox gives exactly-once”

An outbox guarantees no-loss and reduces business-layer duplicates, but does not turn SMTP into a transactional participant.

### “Lease expired means the worker never sent”

False. The worker could have received relay acceptance before stopping heartbeats.

### “Provider hasn’t reported delivered yet, so resend”

False. The provider may already be retrying delivery after acceptance; application resubmission creates a second copy.

### “Not found on the dashboard means not accepted”

Uncertain. Dashboards/APIs can lag or miss data. Treat absence as proof only when the provider contract supports that conclusion.

### “After an incident, just reset everything to PENDING”

This is the fastest way to create mass duplicates. Separate accepted, proven rejected, unknown, expired, and cancelled.

### “Increasing timeouts infinitely eliminates ambiguity”

No. Longer timeouts reduce some errors, yet processes, networks, and DBs can still fail. You still need a state machine and reconciliation.

## 38. Pre-production checklist for SMTP retries

### 38.1. Business identity and email identity

- [ ] `messageKey` exists for each logical email.
- [ ] Unique business event/idempotency key exists.
- [ ] Each attempt has its own `attemptId`.
- [ ] Sender, recipient, and provider IDs are kept distinct.
- [ ] Expiration and consent/suppression checks exist.
- [ ] Does not rely on RFC Message-ID as a deduplication guarantee.

### 38.2. SMTP outcome

- [ ] Distinguishes accepted, proven non-accepted, and unknown.
- [ ] Does not infer non-accepted from generic MailException.
- [ ] Timeouts waiting for final DATA reply are treated as UNKNOWN.
- [ ] Final SMTP 250 is distinguished from EHLO/RCPT 250.
- [ ] Provider deferred never triggers an application submission retry.
- [ ] Partial recipients/messages are tracked to the required granularity.

### 38.3. Persistence and recovery

- [ ] Transactional outbox has durable states.
- [ ] Attempt history stores route/time/outcome.
- [ ] Atomic claim with lease/fencing when needed.
- [ ] SMTP send runs outside any DB transaction.
- [ ] Stale SENDING is not blindly reset to PENDING.
- [ ] UNKNOWN is excluded from auto-retry queries.
- [ ] Reconciliation queue/manual review policy exists.
- [ ] DB commit failure after SMTP accepted has been tested.

### 38.4. Retry

- [ ] Retries only when safety evidence exists.
- [ ] Backoff + jitter + max attempts.
- [ ] Provider quotas/concurrency limits enforced.
- [ ] Does not continuously retry permanent failures.
- [ ] Does not bypass suppression, tenant isolation, or From verification.
- [ ] Policy exists for unresolved UNKNOWNs per email type.
- [ ] Never sends expired tokens/emails.

### 38.5. Tests and observability

- [ ] Fake SMTP test accepts DATA then drops final reply.
- [ ] Tests verify no automatic second submission.
- [ ] Tests cover restart recovery from stale SENDING.
- [ ] Tests cover partial recipients/batch outcomes.
- [ ] Tests cover broker redelivery.
- [ ] Tests cover provider accepted followed by delivery deferred.
- [ ] Metrics exist for UNKNOWN/accepted/reconciled.
- [ ] Logs are redacted with no raw credentials/bodies.

## 39. Hands-on exercises

### Exercise 1 — Diagram SMTP stages

Diagram the TCP/TLS/AUTH/MAIL FROM/RCPT TO/DATA/250 sequence. Point out the exact reply confirming the message was accepted.

### Exercise 2 — Timeout after DATA

A fake SMTP relay stores the message and drops the final 250. The client receives a read timeout. Determine the proper attempt state and explain why not to retry immediately.

### Exercise 3 — Connect timeout

The client failed to establish a TCP connection; no SMTP commands were sent. Analyze which conditions allow retrying after backoff and which require waiting for config fixes.

### Exercise 4 — Exception classifier

Design a classifier that returns `PROVEN_NOT_ACCEPTED` only with explicit evidence. Exceptions with unknown phase must return `UNKNOWN`.

### Exercise 5 — Replace the retry loop

Refactor `catch(MailException){ sendAgain(); }` into a workflow recording outbox state, attempt, outcome, and next action.

### Exercise 6 — Database schema

Create `email_outbox` and `email_submit_attempt`. Add unique business keys, lease tokens, statuses, and indexes for due jobs.

### Exercise 7 — Atomic claim

Use PostgreSQL `FOR UPDATE SKIP LOCKED` so two workers never claim the same job. Test two concurrent transactions.

### Exercise 8 — Crash after accepted

Fake gateway returns SMTP accepted while the repository outcome update fails. Restart the worker and assert stale SENDING is not auto-resent.

### Exercise 9 — Message-ID does not deduplicate

Send two test emails with the same RFC Message-ID to an SMTP sandbox and inspect why you cannot claim only one copy is delivered.

### Exercise 10 — Broker redelivery

The broker redelivers a message after a consumer crash before ACK. Use the message key to check outbox state and block resends on accepted/unknown states.

### Exercise 11 — Provider reconciliation

Simulate three lookup outcomes: accepted, proven rejected, no reliable record. Write state transitions and explain why “no record found” is insufficient to retry.

### Exercise 12 — Delivery deferred

The provider accepted and 10 minutes later reports deferred. Ensure the application creates no new attempt and only updates delivery tracking.

### Exercise 13 — Partial recipients

An SMTP submission has three recipients: one receives 550 while two are accepted. Design tracking and retries so the two accepted recipients never receive duplicates.

### Exercise 14 — Batch send

`JavaMailSender.send(MimeMessage...)` submits two messages and fails on the third. Design separate per-message outcome/attempt persistence.

### Exercise 15 — Timeouts and worker leases

SMTP read timeout is 30 seconds while lease is 10 seconds. Analyze stale-worker risks and propose a lease/heartbeat/fencing policy.

### Exercise 16 — Retry deadline

A verification email expires in 15 minutes. The attempt is UNKNOWN and now overdue. Design a policy that never resends the expired token.

### Exercise 17 — Multi-provider failover

Provider A timed out after end-of-DATA while B is healthy. Prove why you cannot immediately fail over to B, even with a verified From domain.

### Exercise 18 — HTTP API idempotency

Pick a provider HTTP API with an explicit idempotency contract. Describe the key’s scope/TTL and how it differs from SMTP Message-ID.

### Exercise 19 — Incident runbook

5,000 emails timed out within 10 minutes. Group attempts by evidence, pause the route, reconcile, resume, and monitor for duplicates.

### Exercise 20 — Monitoring

Build a dashboard showing SMTP accepted, UNKNOWN, stale leases, reconciliation lag, retry rate, and delivery deferred. Add an alert when UNKNOWN spikes suddenly.

## 40. Summary

**Retrying after a timeout without considering whether the server already accepted** is a critical bug in Spring Framework Mail because SMTP has network side effects while the client can lose the confirmation reply.

The most important principles:

1. **Not seeing success does not mean the server did not accept.** The relay may have received all of DATA and returned 250 while the client timed out.
2. **Inspect phase and evidence**, not just exception class. `MailException` or `SocketTimeoutException` does not prove an attempt is safe to retry.
3. **Explicitly distinguish `SMTP_ACCEPTED`, `PROVEN_NOT_ACCEPTED`, and `UNKNOWN`.** Unconfirmed states must be represented honestly.
4. **Never auto-retry UNKNOWN** without a duplicate-risk policy or appropriate reconciliation evidence.
5. **SMTP accepted is not delivered.** Providers may continue retrying delivery; applications should not resend simply because mail is deferred.
6. **Business idempotency, Message-ID, and transactional outboxes do not create exactly-once SMTP.** They protect different layers of the workflow.
7. **Outboxes and attempt histories** preserve state across crashes/restarts, trace providers, and support reconciliation.
8. **Leases/fencing only protect processing ownership and DB state**; they cannot recall an email accepted by a relay.
9. **Never hold DB transactions across SMTP calls.** If persisting the DB outcome fails after acceptance, recovery must treat the attempt as potentially unknown.
10. **Partial recipients and batch sends** require per-recipient/message outcomes so accepted parts are never resent.
11. **Safe retries require evidence, backoff, deadlines, quotas, and consent policies**, not unconditional resend loops.
12. **Fault-injection testing after end-of-DATA** is the most direct way to catch retry logic that creates duplicates in real timeout scenarios.

By establishing clear boundaries between **what is confirmed**, **what was explicitly rejected**, and **what is unknown**, a Spring Mail application can recover from network failures without trading reliability for floods of duplicate emails.
