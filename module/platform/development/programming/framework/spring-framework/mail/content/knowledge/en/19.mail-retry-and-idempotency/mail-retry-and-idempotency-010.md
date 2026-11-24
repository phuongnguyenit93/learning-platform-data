# Recording Attempt Counts and Failure Reasons

## 1. The Problem in Spring Framework Mail

An application sending email via **Spring Framework Mail** can fail while connecting to SMTP, authenticating, preparing a `MimeMessage`, transmitting data, or updating state afterward. Many failures are transient, so the system can retry. Yet without **persisting attempt counts and failure reasons**, workers struggle to answer:

- How many times has this email been tried?
- When and at which stage did the most recent failure happen?
- Is this a temporary error, a permanent error, or an unknown outcome?
- When is it eligible to retry, and how many attempts remain?
- Are two workers processing the same record concurrently?
- Did SMTP already accept the email before the app could update the database?
- When an operator inspects a failed email, is there enough data to decide whether to **redrive** or fix configuration/data first?

If you merely catch exceptions and log:

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    log.error("Cannot send email", ex);
}
~~~

incident details can be lost when logs rotate or processes restart. Another worker will not know when or why the email should be retried. Conversely, retrying infinitely in a tight loop can overload the provider, send duplicate emails, or tie up workers from handling other tasks.

A common design is a **transactional outbox**: persist the send intent in the database within the business transaction, then have workers pick up records to send. This lesson focuses on **recording dispatch attempt history**, classifying failure reasons, and maintaining consistent state so retries and idempotency operate under control.

> **Distinguish from the start:** "Attempted send" is an application-side event; "SMTP accepted message" is a transport outcome; "message reached inbox" is another event altogether. Never use a single `sent` flag to represent all three.

## 2. Precisely Defining One Attempt

"Attempt count" can be interpreted in several ways, so pick one convention and apply it consistently.

Recommended example convention:

**`attempt_count` = the number of times a worker claimed and started a dispatch pass for the outbox record.**

Whenever a worker acquires valid ownership, increment `attempt_count` **once**, right inside the claim transaction. One dispatch pass may:

1. Render the template and `MimeMessage`.
2. Call `JavaMailSender.send(...)`.
3. Persist `SENT`, `RETRY`, `FAILED`, or `UNKNOWN`.

This means:

- A failure while building MIME **still counts as an attempt** under this convention, even before opening an SMTP connection.
- Executor rejections **before claiming** do not increment `attempt_count`; rejections occurring **after claiming** must be recorded and have their lease/state handled.
- A committed claim where the JVM dies right before SMTP send is still a started attempt, even if no bytes were sent.
- If you need to count actual `mailSender.send` calls separately, add `smtp_attempt_count` or an `SMTP_SEND_STARTED` event—do not change the meaning of `attempt_count` ad hoc.

| Counter | Definition | When updated |
| --- | --- | --- |
| `attempt_count` | Total claimed dispatch passes | Inside the claim transaction |
| `smtp_attempt_count` (optional) | Passes that actually began calling transport | Before SMTP call; subject to crash skew |
| `failure_count` (optional) | Passes recorded as failed | When saving failure outcome |
| `consecutive_failure_count` (optional) | Consecutive failures to date | When applying retry policy |

Not every counter is needed. For a single-recipient record stopping at `SENT`, `attempt_count` and an **attempt history table** are usually sufficient. Never derive `failure_count = attempt_count - 1`: crashed or uncertain passes break that arithmetic.

### 2.1. Started Attempts Differ From Completed Attempts

Suppose:

~~~text
attempt_count = 3

Attempt 1: SMTP connection refused -> RETRY
Attempt 2: SMTP timeout after DATA -> UNKNOWN
Attempt 3: Worker claimed, JVM stopped before calling SMTP
~~~

Three claims were started, yet only two passes had enough information to classify an outcome, and it is still unclear how many times the email reached SMTP. Thus, **counts must pair with per-attempt states**, not just a bare total.

## 3. Designing States Suitable for Retries

An outbox row typically has a lifecycle:

| State | Meaning | Eligible for automatic claim? |
| --- | --- | --- |
| `PENDING` | Newly created, not yet dispatched | Yes |
| `PROCESSING` | Worker holds lease and is processing | No, unless lease expired and reclaimed |
| `RETRY` | Failure classified as retryable | Yes, after `next_attempt_at` |
| `SENT` | `JavaMailSender.send` returned success and was recorded | No |
| `FAILED` | Exhausted attempts or hit stop policy | No automatically |
| `UNKNOWN` (optional) | Unclear whether SMTP accepted the message | Per reconciliation / duplicate-risk policy |
| `CANCELLED` (optional) | Business cancelled the send request | No |

Diagram:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: claim
    RETRY --> PROCESSING: due + claim
    PROCESSING --> SENT: SMTP accepted
    PROCESSING --> RETRY: temporary failure
    PROCESSING --> FAILED: permanent/max attempts
    PROCESSING --> UNKNOWN: ambiguous SMTP outcome
    PROCESSING --> PROCESSING: expired lease reclaimed
    PENDING --> CANCELLED: business cancel
    RETRY --> CANCELLED: business cancel
    UNKNOWN --> RETRY: approved retry
    UNKNOWN --> SENT: provider reconciliation
~~~

Not every system needs `UNKNOWN`. If the business accepts at-least-once semantics, ambiguous errors may map to `RETRY`, provided **potential duplicates** are explicitly documented. For highly sensitive emails, a dedicated reconciliation state helps curb unintended duplicates.

### 3.1. Invariant Rules

Important invariants:

1. `attempt_count` never decreases.
2. A record has **at most one valid active owning attempt** at any moment, enforced by database claims/leases/versions.
3. Only the worker holding the current lease updates the outcome.
4. `SENT` never automatically reverts to `RETRY`.
5. `FAILED` never auto-retries forever; redrives require authorization and auditing.
6. Never transition to `SENT` **before** the SMTP call; doing so can lose emails on process shutdown.
7. `SENT` does not mean inbox arrival; bounces/delivery need separate states or event sources.

## 4. Storing Current State and Per-Attempt History

Two basic data models exist:

**Model A — Single outbox table:** holds `attempt_count`, `last_error_code`, `last_error_message`, `next_attempt_at`, and current status. Easy to implement; fits when only the latest failure is needed.

**Model B — Outbox + attempt history:** alongside summary fields, each pass has its own row with start time, end time, worker, failure stage, error code, and outcome. Fits when auditing, recurring-error analysis, or reconciling ambiguous SMTP outcomes is needed.

| Requirement | Outbox table only | Outbox + attempt history |
| --- | --- | --- |
| Worker fetches due jobs | Sufficient | Sufficient |
| Know total attempt count | Sufficient | Sufficient |
| Know most recent error | Sufficient | Sufficient |
| Compare errors across retries | Incomplete | Yes |
| Investigate crash between SMTP and commit | Limited | Better |
| Audit redrives and handling workers | Possible via extra columns | Easy to extend |
| Storage/transaction overhead | Lower | Higher |

For critical transactional emails, persist attempt history or at least an equivalent durable event log. Whichever model is chosen, **attempt counts must be updated atomically** to avoid lost increments under worker contention.

## 5. Designing the mail_outbox Table

PostgreSQL example:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    delivery_key VARCHAR(180) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(160) NOT NULL,
    payload JSONB NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    claim_token UUID,

    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(30),
    last_error_stage VARCHAR(40),
    last_error_summary VARCHAR(500),
    last_failed_at TIMESTAMPTZ,

    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT ck_mail_status CHECK (
        status IN (
            'PENDING', 'PROCESSING', 'RETRY',
            'SENT', 'FAILED', 'UNKNOWN', 'CANCELLED'
        )
    ),
    CONSTRAINT ck_mail_attempts CHECK (
        attempt_count >= 0 AND max_attempts > 0
    ),
    CONSTRAINT ux_mail_delivery_key UNIQUE (delivery_key)
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox (status, next_attempt_at, created_at);

CREATE INDEX ix_mail_outbox_expired_lease
    ON mail_outbox (status, lease_until);
~~~

Column meanings:

- `delivery_key`: idempotency key at send-request creation time, matching business rules. If one event notifies multiple people, the key can include event ID, template, and delivery/recipient identity.
- `attempt_count`: number of started claims, not merely exceptions thrown.
- `max_attempts`: retry ceiling per email type or policy.
- `next_attempt_at`: earliest eligible claim time after failure; stops workers from tight-looping.
- `lease_owner` / `lease_until`: time-bounded ownership.
- `claim_token`: unique claim identifier preventing a stale worker from overwriting a newer worker's outcome.
- `last_error_code`: application-normalized error code for filtering and metrics.
- `last_error_kind`: e.g., `TRANSIENT`, `PERMANENT`, `UNKNOWN`.
- `last_error_stage`: where failure occurred, such as `RENDER`, `MIME`, `SMTP_CONNECT`, `SMTP_SEND`, or `STATE_UPDATE`.
- `last_error_summary`: short summary stripped of sensitive data.
- `last_failed_at`: timestamp of most recent recorded failure.

`payload` may hold personal info or tokens; enforce access control, encryption, and retention. Never store passwords, SMTP secrets, or unnecessary content in `payload`.

### 5.1. Do Not Scope delivery_key Incorrectly

For example, `order-confirmed:{orderId}` works if business rules emit only one confirmation email per order. However, if the same email type goes to multiple people or legitimately re-emits on a new order version, that key is too broad.

An intentional format:

~~~text
delivery_key = event_type + ":" + event_id
             + ":" + notification_kind
             + ":" + recipient_identity
~~~

If using recipient email in the key, consider canonicalization, address changes, and PII leakage. You can use a delivery UUID derived from the deduplicated business request, or a keyed hash per policy. Never use email addresses as metric labels.

## 6. The mail_delivery_attempt History Table

Each dispatch pass gets its own row:

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INTEGER NOT NULL,
    claim_token UUID NOT NULL,
    worker_id VARCHAR(120) NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(24) NOT NULL DEFAULT 'STARTED',
    failure_kind VARCHAR(30),
    failure_stage VARCHAR(40),
    error_code VARCHAR(100),
    safe_error_summary VARCHAR(500),
    smtp_reply_code VARCHAR(10),
    duration_ms BIGINT,

    CONSTRAINT ux_mail_attempt_number UNIQUE (
        outbox_id, attempt_no
    ),
    CONSTRAINT ux_mail_attempt_claim UNIQUE (claim_token),
    CONSTRAINT ck_mail_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT ck_mail_attempt_outcome CHECK (
        outcome IN (
            'STARTED', 'SMTP_ACCEPTED',
            'RETRYABLE_FAILURE', 'PERMANENT_FAILURE',
            'UNKNOWN', 'ABANDONED'
        )
    )
);

CREATE INDEX ix_mail_attempt_by_delivery
    ON mail_delivery_attempt(outbox_id, attempt_no DESC);
~~~

**An attempt may stay `STARTED` longer than expected** if a worker died or failed to persist the outcome. That is useful evidence: claimed, outcome undetermined. Never assume every unfinished attempt means "SMTP never sent."

### 6.1. Summary Snapshot and History Must Stay Consistent

The outbox table holds current state for fast worker queries. The attempt table holds history for auditing. When starting a new pass, **increment `attempt_count` and insert the attempt row in the same transaction**. Upon completion, update the outbox and attempt row in the same result transaction.

~~~text
Claim transaction
  UPDATE mail_outbox
    attempt_count = attempt_count + 1
    status = PROCESSING
    claim_token = new token
  INSERT mail_delivery_attempt
    attempt_no = new attempt_count
    outcome = STARTED
  COMMIT
             |
             v
    SMTP send (outside DB transaction)
             |
             v
Result transaction
  UPDATE mail_outbox -> SENT / RETRY / FAILED / UNKNOWN
  UPDATE mail_delivery_attempt -> final outcome
  COMMIT
~~~

Keeping both writes in one transaction avoids states where the outbox reports three attempts while history has only two committed rows, or vice versa.

## 7. Atomic Claim and Incrementing attempt_count

With multiple workers, the following is **unsafe**:

~~~java
MailOutbox row = repository.findPending();
row.setAttemptCount(row.getAttemptCount() + 1);
mailSender.send(message);
repository.save(row);
~~~

Two workers can both read `attempt_count = 0`, increment to one, and send the same email; the last write overwrites the first. This causes both a lost update and duplicate dispatch.

In PostgreSQL, claim using `FOR UPDATE SKIP LOCKED` in a short transaction. Example batch claim query:

~~~sql
WITH selected AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
        AND attempt_count < max_attempts
    )
    OR (
        status = 'PROCESSING'
        AND lease_until < now()
        AND attempt_count < max_attempts
    )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET status = 'PROCESSING',
    attempt_count = o.attempt_count + 1,
    lease_owner = :worker_id,
    lease_until = :lease_until,
    claim_token = gen_random_uuid(),
    updated_at = now(),
    version = o.version + 1
FROM selected
WHERE o.id = selected.id
RETURNING o.id, o.attempt_count, o.claim_token,
          o.lease_owner, o.version, o.payload,
          o.recipient, o.template_name;
~~~

This query is a PostgreSQL example; `gen_random_uuid()` requires UUID support from your database version/configuration. In a real application, the repository must execute the entire claim **inside a transaction**, and right after the `UPDATE` it must insert the attempt row with the returned `attempt_count` as `attempt_no` and `claim_token` before committing.

**Additional case to handle:** when reclaiming an expired-lease `PROCESSING` row, the previous attempt may still be `STARTED`. Mark the old attempt `ABANDONED` or `UNKNOWN` inside the claim transaction per policy, without assuming SMTP did not receive the message. If the final attempt hit `max_attempts` and the worker died, a reconciler/cleanup job must transition the row to `FAILED` or `UNKNOWN`; never leave it stuck in expired `PROCESSING` forever just because the claim condition caps attempts.

### 7.1. Using claim_token to Block Stale Updates

`claim_token` identifies **one ownership claim**, not merely a worker process. Worker A claims token A. If the lease expires and Worker B claims token B, Worker A loses write authority even if it is still running.

Example:

~~~text
12:00 Worker A claims -> token A, attempt 1
12:02 Lease A expires
12:03 Worker B claims -> token B, attempt 2
12:04 Worker A attempts mark SENT with token A -> UPDATE 0 rows
12:05 Worker B records its own result with token B
~~~

Conditional updates by claim token protect **database state**. They cannot recall an email Worker A may have already sent; duplicates still require their own policy.

### 7.2. When to Increment the Counter

If you only increment `attempt_count` **after** SMTP fails, a worker crashing mid-send leaves no attempt trace; the batch could retry endlessly without incrementing the counter. Hence, incrementing at claim and recording `STARTED` before calling SMTP is a more recoverable convention.

If you need an exact count of "transport calls started" vs. "claimed dispatches," also record an `smtp_send_started_at` timestamp/event right before the call. Even that event cannot form an atomic transaction with SMTP: a crash window always exists between the database and external side effects.

## 8. Recording Success Outcomes and Failure Details

An attempt's result has two parts:

- **Outcome** of the attempt: succeeded, retryable failure, permanent failure, uncertain outcome, or abandoned.
- **Decision for the outbox:** transition to `SENT`, `RETRY`, `FAILED`, or `UNKNOWN`.

Do not collapse both concepts into a single exception string. For example, `SMTP_CONNECTION_TIMEOUT` is the cause, `TRANSIENT` is the classification, and `RETRY` is the scheduling decision. They are related, not identical.

### 8.1. Recording Success After JavaMailSender.send

Proper order:

~~~java
MimeMessage message = messageFactory.create(claimed);
mailSender.send(message);
stateService.markSent(claimed);
~~~

Update `SENT` only after `send` returns normally. PostgreSQL update example:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    claim_token = NULL,
    last_error_code = NULL,
    last_error_kind = NULL,
    last_error_stage = NULL,
    last_error_summary = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

In **the same transaction** recording success, update the current attempt:

~~~sql
UPDATE mail_delivery_attempt
SET outcome = 'SMTP_ACCEPTED',
    finished_at = now(),
    duration_ms = :elapsed_ms,
    failure_kind = NULL,
    failure_stage = NULL,
    error_code = NULL,
    safe_error_summary = NULL
WHERE outbox_id = :outbox_id
  AND claim_token = :claim_token
  AND outcome = 'STARTED';
~~~

Commit only when both updates match the current attempt. If the outbox update returns 0 rows, the worker lost its lease or state changed; **do not mark the attempt of a stale claim as accepted as if state were synchronized**. Record a separate reconciliation event, because SMTP may indeed have accepted the email.

### 8.2. Recording a Retryable Failure

Suppose the second attempt fails because SMTP is temporarily unavailable. The worker records:

~~~text
outbox.status          = RETRY
outbox.attempt_count   = 2
outbox.next_attempt_at = timestamp computed via backoff
outbox.last_error_code = SMTP_TEMPORARY_UNAVAILABLE
outbox.last_error_kind = TRANSIENT
outbox.last_error_stage = SMTP_CONNECT
outbox.last_failed_at  = failure timestamp

attempt[2].outcome       = RETRYABLE_FAILURE
attempt[2].error_code    = SMTP_TEMPORARY_UNAVAILABLE
attempt[2].failure_stage = SMTP_CONNECT
attempt[2].finished_at   = completion timestamp
~~~

Illustrative SQL:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = :next_attempt_at,
    last_error_code = :error_code,
    last_error_kind = 'TRANSIENT',
    last_error_stage = :error_stage,
    last_error_summary = :safe_summary,
    last_failed_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    claim_token = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

For history:

~~~sql
UPDATE mail_delivery_attempt
SET outcome = 'RETRYABLE_FAILURE',
    finished_at = now(),
    duration_ms = :elapsed_ms,
    failure_kind = 'TRANSIENT',
    failure_stage = :error_stage,
    error_code = :error_code,
    safe_error_summary = :safe_summary,
    smtp_reply_code = :smtp_reply_code
WHERE outbox_id = :outbox_id
  AND claim_token = :claim_token
  AND outcome = 'STARTED';
~~~

Execute both updates inside a short service transaction and verify updated row counts. If either mismatches, roll back and report a conflict rather than letting summary state and history diverge.

### 8.3. Recording Permanent or Exhausted Failures

If template data is invalid, the address is permanently rejected, or the attempt limit is reached:

~~~text
outbox.status = FAILED
attempt.outcome = PERMANENT_FAILURE
outbox.last_error_code = MAIL_TEMPLATE_INVALID
outbox.last_error_kind = PERMANENT
~~~

When attempts exhaust due to repeated temporary failures, record:

~~~text
outbox.status = FAILED
attempt.outcome = RETRYABLE_FAILURE
outbox.last_error_kind = TRANSIENT
outbox.last_error_code = SMTP_TEMPORARY_UNAVAILABLE
terminal_reason = MAX_ATTEMPTS_EXHAUSTED
~~~

The final attempt still had a **temporary cause**, while the system stopped due to **the maximum attempt policy**. Never rewrite the error kind to "permanent" merely because retries ran out. To separate them clearly, add `terminal_reason` to the schema and audit events instead of overwriting `last_error_code` with `MAX_ATTEMPTS` and losing the true SMTP cause.

### 8.4. Keeping Previous Errors in History After SENT

Once sending succeeds after retries, `last_error_*` on the outbox can be cleared to reflect current success. However, **the attempt history table must preserve earlier attempt failures** to investigate SMTP reliability.

Example:

| Attempt | Outcome | Error code |
| --- | --- | --- |
| 1 | `RETRYABLE_FAILURE` | `SMTP_CONNECTION_TIMEOUT` |
| 2 | `RETRYABLE_FAILURE` | `SMTP_SERVER_BUSY` |
| 3 | `SMTP_ACCEPTED` | — |

Current outbox: `SENT`, `attempt_count = 3`, `sent_at` populated. History shows the email took three dispatch passes before acceptance.

## 9. Structuring Failure Reasons

A string like `lastError = exception.toString()` is too unstable for automated processing and may leak personal data. Represent failures with at least:

| Field | Purpose | Example |
| --- | --- | --- |
| `error_code` | Application-controlled code for filtering/alerts | `SMTP_AUTH_FAILED` |
| `failure_kind` | Policy category | `TRANSIENT`, `PERMANENT`, `UNKNOWN` |
| `failure_stage` | Failing processing step | `RENDER`, `MIME`, `SMTP_CONNECT`, `SMTP_SEND`, `STATE_UPDATE` |
| `safe_summary` | Short summary without sensitive data | `SMTP authentication was rejected` |
| `smtp_reply_code` | SMTP code if actually obtained | `421` or `550` |
| `exception_type` (optional) | Exception class name for diagnostics | `MailSendException` |
| `occurred_at` | Failure timestamp | UTC timestamp |
| `attempt_no` | Attempt number where error occurred | `3` |

Not every exception carries an SMTP reply code. For instance, a DNS resolution failure happens before any SMTP response, so `smtp_reply_code` must be nullable. Never "invent" `4xx`/`5xx` codes from exception message text.

### 9.1. Failure Stages Aid Retry Decisions

| Stage | Example | Can we conclude SMTP received the email? |
| --- | --- | --- |
| `VALIDATE` | Missing recipient, invalid subject | SMTP not called yet |
| `RENDER` | Missing template variable, model error | SMTP not called yet |
| `MIME` | Unreadable attachment, `MessagingException` | Usually SMTP not called yet |
| `SMTP_CONNECT` | Unable to connect to SMTP | Usually message not submitted |
| `SMTP_AUTH` | Server rejects authentication | Message not submitted |
| `SMTP_SEND` | Failure during SMTP exchange | Depends on timing; may be uncertain |
| `STATE_UPDATE` | Database error after send | SMTP may have accepted the message |

Stage classification must rely on actual observed events. For instance, if the library throws `MailSendException` after starting SMTP `DATA`, you cannot default the stage to `SMTP_CONNECT`.

### 9.2. Error Codes Are More Stable Than Exception Messages

Exception messages can change across library versions, providers, or locales. Write a classifier translating exceptions into stable error codes:

~~~java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    UNKNOWN
}

public enum FailureStage {
    VALIDATE,
    RENDER,
    MIME,
    SMTP_CONNECT,
    SMTP_AUTH,
    SMTP_SEND,
    STATE_UPDATE
}

public record MailFailure(
        FailureKind kind,
        FailureStage stage,
        String errorCode,
        String safeSummary,
        String smtpReplyCode) {
}
~~~

`MailFailure` is data for **persisting to the database**, not a wrapper holding the raw `Throwable`. Keep full exception stack traces in a separate secure logging system per security policy; never stuff them into a short `VARCHAR` column or use them as logical keys.

## 10. Classifying Exceptions in Spring Framework Mail

`JavaMailSender` and `MimeMessageHelper` expose distinct error types:

| Exception | Typical indication | Classification example |
| --- | --- | --- |
| `MailAuthenticationException` | SMTP authentication failed | `SMTP_AUTH_FAILED`, usually needs operator action |
| `MailSendException` | Error sending message, may wrap nested causes | Inspect reply/phase; may be transient/permanent/unknown |
| `MailPreparationException` | Error preparing mail in application flow | Usually fix data or template |
| `MailParseException` | Error parsing message/address in Spring Mail | Usually do not retry as-is |
| `jakarta.mail.MessagingException` | Checked exception building MIME or Jakarta Mail API | Depends on failing step |
| `org.springframework.mail.MailException` | Runtime base class | Insufficient to conclude retryable |

SMTP replies:

- **4xx** usually indicates temporary issues, such as a busy server or temporary limit.
- **5xx** usually indicates permanent rejection for the current request, such as a rejected address.
- Yet proper handling also depends on **the SMTP command**, enhanced codes, and provider policies.

If the connection drops after the message is transmitted and before the application receives the final reply, the outcome can be **UNKNOWN**. Retrying can produce duplicate emails; stopping retries can drop emails the server never accepted. This is a policy decision to state explicitly rather than hiding behind a single `catch` statement.

### 10.1. Minimal Classifier Example

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailSendException;

public class MailFailureClassifier {

    public MailFailure classify(MailException error) {
        if (error instanceof MailAuthenticationException) {
            return new MailFailure(
                    FailureKind.PERMANENT,
                    FailureStage.SMTP_AUTH,
                    "SMTP_AUTH_FAILED",
                    "SMTP authentication was rejected",
                    null);
        }

        if (error instanceof MailPreparationException
                || error instanceof MailParseException) {
            return new MailFailure(
                    FailureKind.PERMANENT,
                    FailureStage.MIME,
                    "MAIL_PREPARATION_FAILED",
                    "Cannot prepare outgoing mail",
                    null);
        }

        if (error instanceof MailSendException) {
            // Production: inspect nested causes / SMTP response / phase.
            return new MailFailure(
                    FailureKind.UNKNOWN,
                    FailureStage.SMTP_SEND,
                    "SMTP_SEND_UNCLASSIFIED",
                    "SMTP send outcome needs classification",
                    null);
        }

        return new MailFailure(
                FailureKind.UNKNOWN,
                FailureStage.SMTP_SEND,
                "MAIL_UNCLASSIFIED",
                "Mail transport failed",
                null);
    }
}
~~~

This example intentionally **does not treat every `MailSendException` as a transient failure**. In production, add nested cause and reply code inspection. Authentication failures can be redriven after fixing configuration; `PERMANENT` here means do not auto-retry as-is in the automatic loop.

### 10.2. Exception Messages May Contain PII

Avoid:

~~~java
outbox.setLastErrorMessage(exception.getMessage());
~~~

Reason: messages sometimes contain email addresses, hosts, tokenized URLs, or message details. To retain diagnostics, use normalized error codes and self-constructed safe summaries:

~~~java
MailFailure failure = classifier.classify(mailException);
outboxRepository.recordFailure(
        outboxId,
        failure.errorCode(),
        failure.safeSummary());
~~~

If full stack traces are truly needed, send them to a logging system with proper access control, masking, and retention. Never assume stack traces are safe to surface in dashboards or to end users.

## 11. From Failure Reason to Retry Decision

After recording the classified failure, the worker decides:

- **RETRY:** recoverable error within limits.
- **FAILED:** unrecoverable by retries or attempts exhausted.
- **UNKNOWN:** risk SMTP accepted the message; reconcile or retry per duplicate-tolerance policy.

Do not equate `failure_kind = TRANSIENT` with `status = RETRY`: a temporary failure can still result in `FAILED` if max attempts are exceeded or the business deadline has passed.

### 11.1. Decision Policy Accounting for max_attempts

Example:

~~~java
public enum NextAction {
    RETRY,
    FAIL,
    RECONCILE
}

public record RetryDecision(
        NextAction action,
        Instant nextAttemptAt,
        String terminalReason) {
}

public final class MailRetryPolicy {
    private final int maxAttempts;
    private final Duration initialDelay;
    private final Duration maxDelay;

    public MailRetryPolicy(
            int maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
    }

    public RetryDecision decide(
            int currentAttempt,
            MailFailure failure,
            Instant now,
            Instant businessDeadline) {

        if (failure.kind() == FailureKind.UNKNOWN) {
            return new RetryDecision(
                    NextAction.RECONCILE,
                    null,
                    "SMTP_OUTCOME_UNKNOWN");
        }
        if (failure.kind() == FailureKind.PERMANENT) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "PERMANENT_FAILURE");
        }
        if (currentAttempt >= maxAttempts) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "MAX_ATTEMPTS_EXHAUSTED");
        }

        Duration delay = calculateDelay(currentAttempt);
        Instant nextAttempt = now.plus(delay);

        if (businessDeadline != null
                && nextAttempt.isAfter(businessDeadline)) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "BUSINESS_DEADLINE_EXCEEDED");
        }
        return new RetryDecision(
                NextAction.RETRY,
                nextAttempt,
                null);
    }

    private Duration calculateDelay(int currentAttempt) {
        // Prevent shift/overflow when currentAttempt is very large.
        int exponent = Math.min(currentAttempt - 1, 20);
        long factor = 1L << exponent;
        Duration scaled = initialDelay.multipliedBy(factor);
        return scaled.compareTo(maxDelay) > 0
                ? maxDelay : scaled;
    }
}
~~~

This is an illustrative policy without jitter. Production code must validate `initialDelay`/`maxDelay` and add bounded jitter. `currentAttempt` is the attempt number **that just failed**, already incremented at claim time, making `>= maxAttempts` unambiguous.

### 11.2. Exponential Backoff and Jitter

A common formula:

\[
d_n = \min\left(d_{\max}, d_0 \times 2^{n-1}\right)
\]

Where `n` is the attempt number and `d_0` is the initial delay. Add jitter so workers do not retry in lockstep:

\[
d^\prime_n = \operatorname{random}(0, d_n)
\]

or apply a small jitter band around `d_n`. For short-lived security emails, also check `businessDeadline` so expired links are never sent. Never schedule a retry one hour later when a password reset token expires in 15 minutes.

Illustrative schedule:

| Attempt just failed | Base delay | Action |
| --- | --- | --- |
| 1 | 30 seconds | `RETRY` if transient |
| 2 | 1 minute | `RETRY` |
| 3 | 2 minutes | `RETRY` |
| 4 | 4 minutes | `RETRY` |
| 5 | — | `FAILED` if `max_attempts = 5` |

No single retry schedule fits every provider. Choose based on SLAs, SMTP quotas, email validity windows, and operational policies.

### 11.3. Persist next_attempt_at, Never Sleep in the Worker

Avoid:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    Thread.sleep(60_000); // Ties up worker and is not durable.
    mailSender.send(message);
}
~~~

Instead, update:

~~~text
status = RETRY
attempt_count = 2
next_attempt_at = 2026-11-12T09:00:00Z
last_error_code = SMTP_TEMPORARY_UNAVAILABLE
~~~

The current worker finishes and can process other emails. A scheduler or queue consumer reclaims it after the due time. If the process restarts, the retry schedule remains persisted in the database.

## 12. Spring Example: Separating Claim, Send, and Outcome Persistence

An easily controlled architecture:

~~~text
MailOutboxPoller
        |
        v
OutboxClaimService (@Transactional)
        | claim + attempt_count++ + insert attempt
        v
ClaimedMail (snapshot with claimToken)
        |
        v
MailDispatchWorker (without holding DB transaction)
        | render + JavaMailSender.send
        v
OutboxResultService (@Transactional)
        | markSent / recordFailure / markUnknown
        v
PostgreSQL outbox + attempt history
~~~

Crucially, **SMTP send is never inside the transaction holding outbox locks**. The database cannot roll back an email already accepted by the SMTP server.

### 12.1. DTO for a Claimed Pass

~~~java
package com.example.mail.outbox;

import java.util.UUID;

public record ClaimedMail(
        UUID outboxId,
        UUID claimToken,
        int attemptNumber,
        String recipient,
        String templateName,
        String payloadJson) {
}
~~~

Attempt number and claim token travel with the job throughout one pass. Never fetch the latest `attempt_count` from the database at the end and mistake it for an older worker's attempt.

### 12.2. Claim Service With Short Transaction

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxClaimService {

    private final MailOutboxRepository repository;

    public OutboxClaimService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimDue(
            String workerId,
            int batchSize,
            Instant leaseUntil) {

        // Repository must atomically claim and insert attempt
        // in THIS SAME transaction.
        return repository.claimAndCreateAttempts(
                workerId, batchSize, leaseUntil);
    }
}
~~~

`claimAndCreateAttempts` is a repository method implemented with database-appropriate SQL/transactions. It must:

1. Select rows without an active lease whose retry is due.
2. Claim rows atomically, increment the counter, and generate a new claim token.
3. Close/mark old attempts on reclaim per policy.
4. Insert a `STARTED` attempt row for the new pass.
5. Return snapshots with the post-claim attempt number and token.

If any step fails, the entire claim transaction rolls back so another worker can try once the system stabilizes.

### 12.3. Result Service With Its Own Transaction

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxResultService {

    private final MailOutboxRepository repository;

    public OutboxResultService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public boolean recordAccepted(
            ClaimedMail mail, long durationMillis) {

        return repository.markSentAndCompleteAttempt(
                mail.outboxId(),
                mail.claimToken(),
                mail.attemptNumber(),
                durationMillis);
    }

    @Transactional
    public boolean recordFailure(
            ClaimedMail mail,
            MailFailure failure,
            RetryDecision retry,
            long durationMillis) {

        return repository.recordFailureAndCompleteAttempt(
                mail.outboxId(),
                mail.claimToken(),
                mail.attemptNumber(),
                failure,
                retry,
                durationMillis);
    }
}
~~~

The repository **updates the outbox and attempt in one transaction**. Return `true` only when both records matching the claim were updated. If ownership was lost or the claim token changed, roll back, return `false`, and emit a `state_conflict` alert/metric.

Never treat `false` as a reason to call SMTP again immediately. Especially if transport just returned normally, a database conflict does not prove the email was not sent.

### 12.4. Worker Classifying Errors and Recording Outcomes

~~~java
package com.example.mail.outbox;

import java.time.Instant;
import java.util.List;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailDispatchWorker {

    private final JavaMailSender mailSender;
    private final MailMessageFactory messageFactory;
    private final MailFailureClassifier classifier;
    private final MailRetryPolicy retryPolicy;
    private final OutboxResultService resultService;
    private final OutboxClaimService claimService;

    public MailDispatchWorker(
            JavaMailSender mailSender,
            MailMessageFactory messageFactory,
            MailFailureClassifier classifier,
            MailRetryPolicy retryPolicy,
            OutboxResultService resultService,
            OutboxClaimService claimService) {
        this.mailSender = mailSender;
        this.messageFactory = messageFactory;
        this.classifier = classifier;
        this.retryPolicy = retryPolicy;
        this.resultService = resultService;
        this.claimService = claimService;
    }

    public void dispatchBatch(
            String workerId, int batchSize, Instant leaseUntil) {
        List<ClaimedMail> batch =
                claimService.claimDue(workerId, batchSize, leaseUntil);

        for (ClaimedMail mail : batch) {
            dispatchOne(mail);
        }
    }

    private void dispatchOne(ClaimedMail mail) {
        long started = System.nanoTime();
        MimeMessage message;

        try {
            message = messageFactory.create(mail);
        } catch (MessagingException | MailContentException ex) {
            // Preparation error happened before SMTP.
            recordFailure(
                    mail,
                    new MailFailure(
                            FailureKind.PERMANENT,
                            FailureStage.MIME,
                            "MAIL_PREPARATION_FAILED",
                            "Cannot build outgoing MIME message",
                            null),
                    elapsedMillis(started));
            return;
        }

        try {
            mailSender.send(message);
        } catch (MailException ex) {
            recordFailure(
                    mail, classifier.classify(ex),
                    elapsedMillis(started));
            return;
        }

        // SMTP send returned normally.
        // Database error here MUST NOT be treated as an SMTP failure.
        boolean recorded = resultService.recordAccepted(
                mail, elapsedMillis(started));
        if (!recorded) {
            reportStateConflict(
                    mail.outboxId(), "SMTP_ACCEPTED");
        }
    }

    private void recordFailure(
            ClaimedMail mail, MailFailure failure, long durationMs) {
        RetryDecision decision = retryPolicy.decide(
                mail.attemptNumber(),
                failure,
                Instant.now(),
                null);

        boolean recorded = resultService.recordFailure(
                mail, failure, decision, durationMs);
        if (!recorded) {
            reportStateConflict(
                    mail.outboxId(), "FAILURE");
        }
    }

    private static long elapsedMillis(long startNanos) {
        return java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNanos);
    }

    private void reportStateConflict(
            java.util.UUID outboxId, String stage) {
        // Record event/metric/alert with PII controls.
    }
}
~~~

This snippet is an **illustrative skeleton**; `MailMessageFactory`, `MailContentException`, `MailOutboxRepository`, and `UNKNOWN` handling must be implemented per application. Its purpose is highlighting three boundaries:

- MIME construction failures happen **before** SMTP.
- `MailException` in `send` is classified by transport/provider.
- `recordAccepted` or `recordFailure` errors are **state-persistence errors**, not proof SMTP never received the message.

In production, unexpected renderer/serialization errors must also be caught at the worker boundary so rows never stall forever. You can write `FAILED` when certain SMTP was never called; if an error happens after an unclear side effect, use `UNKNOWN` or reconciliation. Never use a single `catch (Exception)` to auto-retry every situation.

### 12.5. @Transactional and Self-Invocation

In Spring, transactions typically apply via proxies. If a method in the same class calls another `@Transactional` method on `this`, the internal call may bypass interception. Separate `OutboxClaimService` and `OutboxResultService` into distinct beans or use `TransactionTemplate` when explicit transactions are needed.

Never invoke partial repository updates outside a shared transaction when the requirement is updating the outbox and attempt history **atomically**.

## 13. Handling Crashes and Unknown SMTP Outcomes

Persisting attempt counts and failure reasons helps post-restart investigation, yet cannot merge SMTP and the database into one transaction.

### 13.1. Crash After Claim, Before SMTP

~~~text
T1: Claim row, attempt_count = 2
T2: Insert attempt #2 STARTED, commit
T3: JVM crashes before JavaMailSender.send
T4: Lease expires
T5: Another worker reclaims and starts attempt #3
~~~

Attempt #2 can be marked `ABANDONED`. However, if the worker died right in the window between starting `send` and writing a separate flag, database state alone cannot confirm whether SMTP received the message. Always record exactly **what the application observed** instead of guessing external outcomes.

### 13.2. Crash After SMTP Accepted, Before Writing SENT

~~~text
T1: Claim row, attempt #2 STARTED
T2: SMTP accepts message
T3: JVM crashes
T4: Outbox still PROCESSING, attempt #2 still STARTED
T5: Lease expires
T6: Another worker retries -> possible duplicate
~~~

This is the core window of the **at-least-once** model. Without retrying, emails can be lost when SMTP did not actually accept them. With retrying, recipients may receive two emails. No counter like `attempt_count` or `Message-ID` can guarantee exactly-once delivery with plain SMTP.

If the provider offers an API supporting idempotency keys, pass the same `delivery_key` across retries within their supported scope and window. Still, **never assume an SMTP server automatically deduplicates by `Message-ID`**.

### 13.3. Crash While Persisting Outcome

If the transaction writing outbox and attempt rolls back, neither `SENT` nor `FAILED` is saved even though the worker observed the result. The next pass may find the old attempt still `STARTED`.

If a state-write error happens **after SMTP succeeded**, logs/alerts must explicitly note:

~~~text
deliveryId = ...
claimToken = ...
attempt = 2
smtpResult = ACCEPTED
stateWriteResult = FAILED
action = RECONCILIATION_REQUIRED
~~~

Never call `mailSender.send` again inside the database exception catch block. Any subsequent retry decision must account for duplicate risk and the email type's policy.

### 13.4. Handling Stalled Attempts When Leases Expire

A background reconciler can look up:

~~~sql
SELECT id, attempt_count, claim_token, lease_until
FROM mail_outbox
WHERE status = 'PROCESSING'
  AND lease_until < now();
~~~

For each record:

- If `attempt_count < max_attempts` and policy allows at-least-once, a worker can reclaim atomically.
- If the final attempt already used up the budget, transition the row to `FAILED` or `UNKNOWN` per available evidence.
- If there is evidence the provider already received the message (e.g., provider API report), reconcile before deciding to retry.
- Never let the old worker overwrite the new worker's decision: always check `claim_token`/version.

A `PROCESSING` row with an expired lease is not necessarily an SMTP error; it could be a crash, a hung thread, too short a lease, or a database outage. `failure_stage` should reflect the observed cause—for instance, `WORKER_LEASE_EXPIRED` is **an operational event**, not an SMTP reply.

## 14. Idempotency at Request Creation and Dispatch

Retries and idempotency have two separate boundaries:

**1. When writing to the outbox:** prevent creating multiple records for the same business notification. Use a properly scoped unique `delivery_key`.

~~~sql
INSERT INTO mail_outbox (
    id, delivery_key, recipient,
    template_name, payload, status
)
VALUES (
    :id, :delivery_key, :recipient,
    :template_name, :payload, 'PENDING'
)
ON CONFLICT (delivery_key) DO NOTHING;
~~~

**2. When dispatching to the provider:** if the provider supports idempotency keys, pass a stable key to curb duplicates on client/worker retries; with SMTP alone, accept and manage the duplicate window.

Never change `delivery_key` on retries, or one notification turns into multiple independent deliveries. Conversely, **`claim_token` must change on every attempt** to fence off stale workers.

| Identifier | Fixed across retries? | Purpose |
| --- | --- | --- |
| `outbox.id` | Yes | Delivery identifier |
| `delivery_key` | Yes | Deduplicate business requests |
| `attempt_no` | No, increments | Sequence of dispatch passes |
| `mail_delivery_attempt.id` | No | Identifies one attempt |
| `claim_token` | No | Active worker's update authority |
| `Message-ID` | Depends on creation; not a dedup guarantee | Correlation in mail systems |

### 14.1. One Record per Recipient

If sending the same content to multiple people and you need to know who failed, it is usually best to persist one separate outbox/delivery record per recipient:

~~~text
event order-confirmed-123
  |
  +--> outbox A -> customer@example.net
  |
  +--> outbox B -> accounting@example.net
~~~

Each record tracks its own attempt count, error code, and status. If A is accepted by SMTP while B is rejected, only B needs handling. Sending multiple recipients in one `MimeMessage` risks partial acceptance; collapsing everything into one `SENT`/`FAILED` status is inaccurate.

### 14.2. Redriving Without Breaking Idempotency

If an operator decides to redrive a `FAILED` email, two policies exist:

- **Redrive the same record:** keep `outbox.id`, log a redrive event, and grant a new retry window; define how `max_attempts` and prior history are handled.
- **Create a new delivery:** use a new ID/key with an explicit audit reason; suitable when it is genuinely a valid resend request.

Never delete attempt history or reset `attempt_count = 0` without leaving an audit trail. If granting a "new retry cycle," add a separate `retry_cycle` column or audit event for the redrive.

## 15. Security and Managing Failure Data

Error data helps operations, yet can also contain sensitive information:

- Email addresses, recipient names, subject lines.
- Email bodies, invoice details, reports.
- URLs containing verification or password-reset tokens.
- Internal hostnames and connection details.
- Credentials if a library/proxy accidentally puts them in an exception message.

Practical rules:

1. Persist **normalized error codes** and short application-controlled descriptions instead of raw exception messages.
2. Cap column lengths (`safe_error_summary` does not need tens of KB).
3. Restrict read access to outbox/attempt tables since they hold recipients and payloads.
4. Define history retention windows per audit needs and security regulations.
5. If logging stack traces, use a logging pipeline with proper masking, retention, and access control.
6. Avoid using `recipient`, PII-containing `delivery_key`, or `outbox.id` as metric labels.
7. When surfacing data to dashboards or support tools, show only the minimum needed for investigation.

### 15.1. Never Serialize Full Throwables to JSON

Do not serialize directly:

~~~java
objectMapper.writeValueAsString(exception);
~~~

An exception's object graph can include nested causes, provider-specific fields, huge stack traces, or data unfit for exposure. Instead:

~~~json
{
  "errorCode": "SMTP_AUTH_FAILED",
  "failureKind": "PERMANENT",
  "failureStage": "SMTP_AUTH",
  "safeSummary": "SMTP authentication was rejected",
  "smtpReplyCode": null
}
~~~

For per-attempt error reports, place timestamps and attempt numbers in dedicated columns so SQL can filter and sort cleanly.

## 16. Observability, Dashboards, and Alerting

`last_error_code` alone cannot tell whether the system is degrading or a single email failed. Emit metrics at both the queue level and the attempt level.

| Metric | Meaning |
| --- | --- |
| `mail_outbox_pending_count` | Deliveries waiting for dispatch |
| `mail_outbox_retry_count` | Deliveries waiting for retry |
| `mail_outbox_failed_count` | Deliveries where retries stopped |
| `mail_outbox_unknown_count` | Deliveries needing reconciliation |
| `mail_outbox_oldest_due_age_seconds` | Wait time of oldest due row |
| `mail_attempt_started_total` | Started attempts |
| `mail_attempt_smtp_accepted_total` | Attempts accepted by transport |
| `mail_attempt_failure_total` | Failed attempts by code/kind/stage |
| `mail_attempt_duration_seconds` | Processing duration of one pass |
| `mail_outbox_lease_reclaimed_total` | Expired leases reclaimed |
| `mail_outbox_state_conflict_total` | Updates failing claim token/version match |
| `mail_outbox_retry_exhausted_total` | Rows hitting max attempts |

Group metrics by `template_name`, provider, error category, or environment. Avoid putting recipient IDs, outbox UUIDs, or free-form error text into labels due to high cardinality and leakage risk.

### 16.1. Example Queries for Common Errors

Using attempt history:

~~~sql
SELECT error_code, COUNT(*) AS failures
FROM mail_delivery_attempt
WHERE outcome IN (
    'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', 'UNKNOWN'
)
  AND started_at >= now() - INTERVAL '24 hours'
GROUP BY error_code
ORDER BY failures DESC;
~~~

Viewing deliveries with high retries:

~~~sql
SELECT id, template_name, attempt_count,
       last_error_code, next_attempt_at
FROM mail_outbox
WHERE status IN ('RETRY', 'FAILED', 'UNKNOWN')
ORDER BY attempt_count DESC, updated_at DESC
LIMIT 100;
~~~

Monitoring queries must enforce proper permissions and avoid projecting recipients/payloads when unnecessary.

### 16.2. Actionable Alerts

Examples:

- Sudden spike in `SMTP_AUTH_FAILED`: check credentials and provider policies before redriving.
- Rising `SMTP_CONNECTION_TIMEOUT`: check network, DNS, SMTP timeouts, and connection limits.
- Many `UNKNOWN` outcomes: inspect connectivity and provider reconciliation; avoid blind retries.
- Rising `STATE_CONFLICT`: inspect lease durations, clocks/timeouts, worker concurrency, and claim tokens.
- `PENDING` older than SLA: inspect workers/schedulers, backlog, and capacity.

A useful dashboard separates **attempt failure rate** from **delivery failure rate**. An email failing three times before succeeding creates three failed attempts while no longer being a failed delivery in its final state.

## 17. Testing Attempt Counting and Failure Recording

A retry system rarely breaks on a standalone `mailSender.send` call; bugs hide at the boundaries of **claim, SMTP, outcome persistence, and crashes**. Test suites should cover all of them.

### 17.1. Testing Counter Increment on Claim

Given an outbox row:

~~~text
id = A
status = PENDING
attempt_count = 0
max_attempts = 5
~~~

After the first claim:

~~~text
outbox.status = PROCESSING
outbox.attempt_count = 1
outbox.claim_token = T1

attempt #1:
    claim_token = T1
    outcome = STARTED
~~~

If another worker simultaneously tries to claim row A, only one worker acquires it. Use a **real database or Testcontainers** to verify locking semantics; mock repositories cannot prove `FOR UPDATE SKIP LOCKED` or concurrent update safety.

### 17.2. Testing Temporary Errors and Retry Schedules

Scenario:

1. Worker claims attempt #1.
2. SMTP throws an error classified as `TRANSIENT`.
3. Worker sets outbox `RETRY` with a future `next_attempt_at`.
4. Attempt #1 records `RETRYABLE_FAILURE` with error code/stage/timestamp.
5. Worker does not claim the row before due time.
6. Once due, attempt #2 starts and the counter increments to 2.

If policy includes jitter, do not assert an exact fixed timestamp; assert the delay lies within the allowed bounds. Inject a `Clock` for time logic so tests do not depend on machine `Instant.now()`.

### 17.3. Testing Permanent Errors

For example, missing template or invalid recipient:

- `attempt_count` already incremented at claim.
- Attempt row records `PERMANENT_FAILURE` and a clear error code.
- Outbox transitions to `FAILED` with no `next_attempt_at` for automatic retry.
- Not resent on the next polling cycle.
- Error summary contains no raw payload or tokens.

### 17.4. Testing Max Attempts Exhaustion

With `max_attempts = 3`:

| Attempt | Error | Decision |
| --- | --- | --- |
| 1 | SMTP temporarily unavailable | `RETRY` |
| 2 | SMTP temporarily unavailable | `RETRY` |
| 3 | SMTP temporarily unavailable | `FAILED`: `MAX_ATTEMPTS_EXHAUSTED` |

History must preserve all three failure causes (even if identical), while the outbox's final state is `FAILED`. Never increment to a fourth attempt without an authorized redrive.

### 17.5. Testing Outcome Write Failures and Race Conditions

An important integration test:

~~~text
Worker A claims -> T1, attempt 1
Lease T1 expires
Worker B claims -> T2, attempt 2
Worker A tries recordFailure(T1)
Expected: update 0 rows; outbox remains owned by T2
~~~

This verifies `claim_token` and version fencing truly work. When Worker A **succeeds over SMTP** and then fails the state update, the system must emit a duplicate-risk alert rather than immediately calling `mailSender.send` again.

### 17.6. Testing Crash Windows

| Stopping point | Possible remaining state | Expected behavior |
| --- | --- | --- |
| Before claim transaction commit | `PENDING`/`RETRY` unchanged | Can be claimed again |
| After claim commit, before SMTP | `PROCESSING` + attempt `STARTED` | Lease expires, handled by reclaim |
| SMTP accepted, before state commit | `PROCESSING` + attempt `STARTED` | Duplicate window recorded |
| Clear SMTP error, before `recordFailure` commit | `PROCESSING` + attempt `STARTED` | Lease expires, reclassified per policy |
| After `recordFailure` commit | `RETRY`/`FAILED` + completed attempt | Scheduler honors new state |
| After `recordAccepted` commit | `SENT` + attempt `SMTP_ACCEPTED` | Not dispatched again |

You cannot prove exactly-once email delivery with a unit test. Tests verify that the application handles known states and protects the database under concurrency.

### 17.7. Unit Test Example for Retry Policy

~~~java
@Test
void thirdAttemptStopsWhenMaxAttemptsIsThree() {
    MailRetryPolicy policy = new MailRetryPolicy(
            3,
            Duration.ofSeconds(30),
            Duration.ofMinutes(10));

    MailFailure failure = new MailFailure(
            FailureKind.TRANSIENT,
            FailureStage.SMTP_CONNECT,
            "SMTP_CONNECTION_TIMEOUT",
            "SMTP connection timed out",
            null);

    RetryDecision decision = policy.decide(
            3,
            failure,
            Instant.parse("2026-11-12T10:00:00Z"),
            null);

    assertEquals(NextAction.FAIL, decision.action());
    assertEquals(
            "MAX_ATTEMPTS_EXHAUSTED",
            decision.terminalReason());
}
~~~

Example uses JUnit 5. The policy class above is illustrative Java code; the test exercises the same `decide` contract. You can add tests for `UNKNOWN`, `PERMANENT`, deadlines, and bounded delays.

## 18. Multi-Attempt Log Example for One Delivery

Suppose an invoice must be sent to `customer@example.net` with `max_attempts = 4`. In the outbox table, state changes as follows:

| Timestamp | Status | Attempts | Details |
| --- | --- | ---: | --- |
| 08:00 | `PENDING` | 0 | Business transaction creates outbox row |
| 08:01 | `PROCESSING` | 1 | Worker claims `T1` |
| 08:01 | `RETRY` | 1 | SMTP connection timeout; retry scheduled 08:02 |
| 08:02 | `PROCESSING` | 2 | Worker claims `T2` |
| 08:02 | `RETRY` | 2 | SMTP `421`; retry scheduled 08:04 |
| 08:04 | `PROCESSING` | 3 | Worker claims `T3` |
| 08:04 | `SENT` | 3 | SMTP accepted; `sent_at` recorded |

Timestamps are illustrative. Real schedules may include jitter, timeouts, and varying delays.

Subsequent attempt history:

| Attempt | Outcome | Kind | Error code |
| --- | --- | --- | --- |
| 1 | `RETRYABLE_FAILURE` | `TRANSIENT` | `SMTP_CONNECTION_TIMEOUT` |
| 2 | `RETRYABLE_FAILURE` | `TRANSIENT` | `SMTP_SERVER_BUSY` |
| 3 | `SMTP_ACCEPTED` | — | — |

The outbox now shows `status = SENT`, `attempt_count = 3`. Do not erase history for attempts #1 and #2 simply because attempt #3 succeeded if the system requires metrics or auditing.

If attempt #3 ended in a timeout **after `DATA`**, history could record `UNKNOWN` instead of `RETRYABLE_FAILURE`. Deciding whether to attempt a fourth send depends not on the exception alone, but on the application's duplicate/reconciliation policy.

## 19. Operations and Redriving Failed Records

A `FAILED` record needs enough information for an operator to understand what happened without reading the full message body:

~~~text
Delivery ID:       8f...
Template:          invoice-ready
Status:            FAILED
Attempt count:     4 / 4
Last failure:      SMTP_AUTH_FAILED
Failure kind:      PERMANENT
Failure stage:     SMTP_AUTH
Last failed at:    2026-11-12T10:00:00Z
Terminal reason:   CONFIGURATION_REQUIRES_ACTION
~~~

Operational workflow:

1. Inspect the error code and attempt timeline.
2. Determine whether the fault lies in the provider, data, template, recipient, or state update.
3. Fix the root cause before redriving, e.g., update credentials.
4. Confirm the email content is still valid; tokens/links may have expired.
5. Decide whether to resend the same delivery or create a new send request.
6. Audit the reason and operator identity.
7. Schedule reprocessing via a conditional transaction without mutating old history directly.

Never provide a "retry all FAILED" button that ignores error types. If the issue is invalid recipient addresses, retrying thousands of times will not improve success rates.

### 19.1. Retention Policies

Outbox and attempt history tables can grow rapidly. Define:

- How long to keep `SENT` records for auditing and deduplication?
- Should `FAILED`/`UNKNOWN` records be retained longer for reconciliation?
- Must payloads containing personal data be deleted, anonymized, or encrypted once no longer needed?
- Can attempt history be archived to cheaper storage?
- How long must unique delivery keys remain active to block duplicate event creation?

Do not purge `SENT` records too early if the application relies on them to prevent recreating already-sent emails on event replay. If deletion is required by security policy, design a deduplication mechanism with a matching lifecycle.

## 20. Common Mistakes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `attempt_count` stays 0 even when emails fail | Incremented only after send succeeds, or exception rolls back increment | Increment in claim transaction before SMTP |
| Two workers send yet counter increases by 1 | Non-atomic read-modify-write | Atomic claim, row lock/version |
| `PROCESSING` rows stuck forever | Missing leases or no expired-lease sweep | Leases, heartbeats/reclaims, reconciliation |
| `attempt_count` exceeds max | No ceiling check at claim time | Enforce guard and handle terminal state |
| Error codes change across deploys | Relying directly on exception messages | Use a stable error-code taxonomy |
| Empty history despite incremented counter | Attempt insert outside claim transaction | Write atomically and roll back on mismatch |
| Outbox `SENT` while history stays `STARTED` | Both updates not in same transaction | Persist outcome atomically |
| Duplicate emails after SMTP timeout | Server may have accepted before connection dropped | `UNKNOWN` policy, provider idempotency if available |
| All errors retried | No permanent vs. transient classification | Classifier with stage and reply code |
| Previous errors erased so history is lost | Storing only latest snapshot | Keep attempt history table |
| Stale worker overwrites newer state | No claim token/version check | Conditional update / fencing |
| DB error after SMTP called an SMTP error | Wrapping send and state update in one `catch` | Separate transport and persistence boundaries |
| Dashboard exposes addresses/tokens | Storing raw exceptions or PII metric labels | Safe summaries and access control |
| Retries still sent after deadline | Policy ignores business expiration | Check `businessDeadline` before scheduling |

## 21. Frequently Asked Questions

**"Should `attempt_count` be saved when starting to send or after a send fails?"**  
If counting dispatch passes, increment right inside the claim transaction **before** calling SMTP. That leaves a trace if a worker dies mid-flight. If you need a separate count of SMTP calls, use a distinct counter/event with a clear name.

**"Does the attempt count equal the actual number of emails sent?"**  
Not necessarily. A claim pass might crash before SMTP, or time out after the server already accepted the message. `attempt_count` is the number of started processing passes per the app's definition, not proof of how many messages the provider received.

**"Is storing only `last_error_message` enough?"**  
It may suffice for a very simple system, yet makes retry policies, analytics, and history investigations hard. Include `error_code`, `failure_kind`, `failure_stage`, and timestamps. For critical systems, persist attempt history.

**"Should full exception stack traces be saved in the database?"**  
Usually no. Store normalized error codes and stable safe summaries; stack traces belong in a protected logging system. Never expose raw exceptions containing PII/tokens on dashboards.

**"Can an SMTP `421` error always be retried?"**  
`4xx` usually indicates a temporary error, though you must inspect the SMTP stage and provider policy. Retries still require backoff, attempt caps, and deadlines.

**"Should SMTP authentication errors immediately be marked `FAILED`?"**  
Usually stop automatic retries with the same credentials and alert operators. After fixing configuration, eligible deliveries can be redriven per policy. Preserve `SMTP_AUTH_FAILED` for investigation.

**"Why is `claim_token` needed if `lease_owner` already exists?"**  
The same worker can reclaim the same row multiple times. A per-attempt claim token distinguishes an older ownership period from a new one, even when the worker ID is identical.

**"After sending succeeds, can `last_error` be cleared?"**  
It can be cleared on the `SENT` summary record, while keeping prior attempt errors in the history table if auditing is needed. Never delete retry history simply because the final send succeeded.

**"When `max_attempts` is exhausted, should the error kind change to `PERMANENT`?"**  
No. If the last attempt failed transiently, keep `failure_kind = TRANSIENT` and record `terminal_reason = MAX_ATTEMPTS_EXHAUSTED` (or an equivalent audit event). Error kind and the reason retries stopped are distinct concepts.

**"If a worker crashes before calling `recordFailure`, how do we know the error?"**  
You cannot know the exact cause without another durable observation. A `STARTED` attempt lacking `finished_at` is the trace; after lease expiry, a reconciler can record `ABANDONED`/`UNKNOWN` per policy and create a new attempt if permitted.

**"Can a transactional outbox guarantee exactly-once delivery?"**  
Not with plain SMTP. The outbox guarantees the event commits alongside the business transaction, yet SMTP sends and DB state updates share no joint commit. Systems generally execute at-least-once with a duplicate window.

**"Should we retry when updating `SENT` fails?"**  
Do not immediately retry SMTP because the transport may already have received the email. Alert on the state-write failure, reconcile, and redispatch only under a duplicate-aware policy.

**"Can multiple recipients be stored in one outbox row?"**  
Possible, though partial failures are hard to track. When accurate per-recipient retries, auditing, and status are required, a separate delivery row per recipient is usually easier to manage.

**"Should the counter be reset when an operator redrives?"**  
Never reset silently. If starting a new retry cycle, store cycle/audit metadata so total historical dispatches remain visible.

## 22. Implementation Checklist

Before shipping a mail worker to production, clarify:

1. **Attempt definition:** counting claims, transport calls, or failures? Standardize column names and increment timing.
2. **States:** `PENDING`/`PROCESSING`/`RETRY`/`SENT`/`FAILED`, and is `UNKNOWN` needed?
3. **Concurrency:** atomic claims, leases, claim tokens, and updated row count checks.
4. **Transactions:** atomic counter increment + attempt insert; SMTP outside DB transactions; atomic outcome + attempt history writes.
5. **Errors:** store error code, kind, stage, timestamp, safe summary, and SMTP reply code if available.
6. **Retries:** per-mail-type policies, exponential backoff, jitter, max attempts, and deadlines.
7. **Idempotency:** unique delivery key at ingress; never confuse with claim token or `Message-ID`.
8. **Crashes:** handle expired leases, stalled `STARTED` attempts, state-write errors, and duplicate windows.
9. **Security:** never write tokens, credentials, full email bodies, or raw exception messages into unprotected history/logs.
10. **Monitoring:** track backlogs, retry/failed/unknown counts, queue age, lease reclaims, and state conflicts.
11. **Operations:** establish redrive, audit, and retention workflows.
12. **Tests:** cover success, transient, permanent, max attempts, crashes, concurrency, and state-update conflicts.

### Overall Flow

~~~text
Business transaction
    |-- write domain data
    +-- insert outbox (PENDING, attempt_count=0)
                  |
                COMMIT
                  |
                  v
Worker atomic claim
    |-- PROCESSING + lease + claim_token
    |-- attempt_count = attempt_count + 1
    +-- INSERT attempt STARTED
                  |
                COMMIT
                  |
                  v
             Send via SMTP
                  |
         +--------+---------+
         |        |         |
      Accepted  Failure   Unknown
         |        |         |
         v        v         v
        SENT    RETRY/     UNKNOWN /
                FAILED   reconciliation
         |        |         |
         +--------+---------+
                  |
                  v
Transaction writing outbox + attempt outcome
    |-- match claim_token/owner
    |-- update status
    |-- record error code/attempt history
    +-- COMMIT
~~~

## Conclusion

In Spring Framework Mail, **recording attempt counts** is not merely incrementing an integer after catching an exception. Every attempt needs a clear definition, ownership, start time, and matching outcome. **Recording failure reasons** should likewise not just copy exception strings, but capture structured data to classify, decide retries, monitor, and reconcile.

Combining `attempt_count`, per-attempt history, `failure_kind`/`error_code`, `next_attempt_at` schedules, claim tokens, and short transactions enables applications to recover from errors without losing operational visibility. At the same time, acknowledge SMTP's at-least-once limit: a failure or crash after the server accepts a message can still produce duplicates on retry. A sound design **records what was observed**, empowers operators to make the right call, and never equates "attempted send" or "SMTP accepted" with "recipient received the email."
