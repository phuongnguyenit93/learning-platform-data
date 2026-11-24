# Testing Retries and Dead Letters

An email-sending application using **Spring Framework Mail** must know more than how to call `JavaMailSender.send(...)`. In real environments, sending can hit SMTP timeouts, temporary server errors, provider rate limits, mid-flight worker shutdowns, or database failures when persisting results. For critical emails, the application needs **controlled retries**, and when recovery fails, it must move jobs to a **dead-letter** state for monitoring, investigation, or manual handling.

Unit-testing a backoff-seconds calculation alone does not verify the whole mechanism. **Integration testing** must wire real components under controlled boundaries: Spring configuration, repositories, database/outbox, workers, transactions, and retry scheduling. The SMTP sending boundary can be swapped for a **fault-controllable test double** to test database flows deterministically; then add a separate suite against a **test SMTP server** to verify the protocol and transport error mapping.

This guide explains how to design and test **retries and dead letters** for Spring Framework Mail, covering state models, Testcontainers/PostgreSQL, transient and permanent errors, `UNKNOWN` after ambiguous submission outcomes, retry budgets, backoff, concurrency, crash recovery, dead-letter replay, side-effect checks, and operational monitoring.

## 1. Integration Testing Objectives

After this guide, you should be able to test that:

1. An email send request is durably persisted in the outbox.
2. Workers claim only due jobs and do not send jobs that are not yet due.
3. When SMTP submission fails temporarily, the job transitions to `RETRY_WAIT` with a valid next retry timestamp.
4. When due, the worker reuses the **message key** while creating a new **attempt ID**.
5. Once an attempt succeeds, the job transitions to `SMTP_ACCEPTED` and is never re-sent by normal retry schedules.
6. On permanent errors, the job moves to `DEAD_LETTER` without infinite loops.
7. When the **retry budget** is exhausted, the job also moves to dead letter with its final reason and attempt history.
8. When outcomes are uncertain due to timeouts after SMTP `DATA`, the job stays in `UNKNOWN` for reconciliation instead of blind retries.
9. Two concurrent workers never claim the same available job simultaneously.
10. Application restarts never lose retry schedules or dead-letter records.
11. When persisting outcomes fails, the application does not assume resending is safe.
12. Controlled dead-letter replay is possible without erasing history or causing arbitrary duplicate sends.

This tests the **sending and state-persistence workflow**, not Inbox delivery. `SMTP_ACCEPTED` only means the SMTP relay/provider accepted the submission per its contract; delivery, spam filtering, and recipient reads are separate stages.

## 2. The System Landscape Under Test

An architecture using a transactional outbox:

```text
HTTP / business event
         |
         v
Business service + DB transaction
         |
         +--> Business data
         |
         +--> email_outbox(PENDING)
         |
         v
      COMMIT
         |
         v
Outbox worker / scheduler
         |
         +--> Claim due row + lease
         |
         +--> Create email_attempt
         |
         v
Mail submission gateway
         |
         +--> JavaMailSender / SMTP
         |
         +--> Provider API (if available)
         |
         v
Submission outcome
         |
         +--> SMTP_ACCEPTED
         |
         +--> RETRY_WAIT
         |
         +--> DEAD_LETTER
         |
         +--> UNKNOWN -> reconciliation
```

Not every product needs every single one of these states, yet **state names and meanings must be unambiguous**. With only a `sent=true/false` flag, tests struggle to distinguish "not attempted yet", "retrying", "budget exhausted", and "SMTP may have accepted it without the app knowing".

### 2.1. Separating Logical Email, Attempt, and Delivery

| Concept | Example | Preserved Across Retries? |
|---|---|---|
| Business event ID | `order-123-paid` | Usually yes |
| Application message key | `msg-a817` | **Yes**, if it is the same logical email |
| Attempt ID | `attempt-1`, `attempt-2` | **No**; each try gets its own ID |
| RFC Message-ID | `<...@mail.example>` | May differ if MIME is regenerated |
| SMTP queue/provider message ID | `provider-id-...` | Tied to a provider-confirmed submission |
| Delivery event ID | `evt-...` | Tied to a webhook event |

**Retries** of the same logical email preserve the application message key. A fresh user-initiated resend request may be a new logical email. Distinguish them so retries do not spawn swarms of outbox rows.

### 2.2. What Is a Dead Letter?

**Dead letter** is where jobs go when automated processing decides **not to keep retrying immediately via normal retries**. In queue setups this may be a **dead-letter queue (DLQ)**; in outbox database setups it may be a `DEAD_LETTER` status paired with a `mail_dead_letter` detail table.

It does not necessarily mean the email can never be sent under any circumstances. Dead letters can arise because:
- invalid data/sender address;
- SMTP server returned a classified permanent error;
- recipient suppression policy excluded an address;
- max attempts were exhausted or deadline passed;
- job failed template rendering and requires input fixes;
- operators intentionally halted processing for investigation.

A dead-letter entry should capture **message key, log-safe reason, last error, attempt count, and timestamp**, rather than a generic "Failed" string.

## 3. State Model to Verify with Tests

```text
PENDING
   |
   v
SENDING  <-----------------------+
   |                            |
   +--> SMTP_ACCEPTED           |
   |                            |
   +--> RETRY_WAIT --------------+
   |
   +--> DEAD_LETTER
   |
   +--> UNKNOWN
          |
          v
     Reconciliation / operator decision
          |
          +--> SMTP_ACCEPTED
          +--> RETRY_WAIT (if safe)
          +--> DEAD_LETTER / manual review
```

| Status | Meaning | Typical Worker Behavior |
|---|---|---|
| `PENDING` | Not attempted yet | Eligible for claim when due |
| `SENDING` | Claimed and attempting send | Only the lease-holding worker may update |
| `RETRY_WAIT` | Retryable failure; awaiting `next_attempt_at` | Never claimed early |
| `SMTP_ACCEPTED` | Submission accepted upstream | Never retry this job's submission |
| `DEAD_LETTER` | Automatic retries stopped, awaiting other policy | Ignored by regular workers |
| `UNKNOWN` | Uncertain whether upstream accepted it | Reconcile; never resend unconditionally |

You can add `DELIVERED`, `BOUNCED`, or `COMPLAINED` when consuming provider webhooks. Those belong to the **delivery lifecycle**, distinct from the **submission retries** under test here.

### 3.1. Critical Invariants

Integration tests should guard these invariants:

- One message key represents one logical email.
- Each attempt for a message key has a unique sequence number.
- `SMTP_ACCEPTED` or `DEAD_LETTER` jobs never revert to `SENDING` when schedulers rerun.
- `attempt_count` increments only when an attempt genuinely starts/claims per contract.
- `RETRY_WAIT` always has a valid `next_attempt_at` and is never claimed prematurely.
- Once `maxAttempts` is reached, no attempt exceeds the budget.
- Dead letters persist durably in the same transaction as the state transition.
- No two active workers simultaneously hold the same lease token.
- Failures never erase the message key or attempt history.
- `UNKNOWN` outcomes are never coerced into definite `FAILED` without evidence.

Tests should assert not only "final status is right", but also **gateway invocation counts, attempt history, retry schedules, and dead-letter records**.

## 4. Classifying Errors Before Deciding to Retry

Never use one blanket `catch (Exception e) { retry(); }` for every failure.

| Error Category | Examples | Typical Decision |
|---|---|---|
| **Transient / retryable** | SMTP 421/451 before accepting message, safely classified network errors | Wait for backoff, retry within budget |
| **Permanent / non-retryable** | Invalid address, broken template data unfixable automatically, confirmed relay refusal | Move to dead letter or immediate workflow handling |
| **Configuration/auth** | Bad SMTP credentials, TLS hostname/certificate mismatch | Do not hammer retries; alert/fix config |
| **Unknown outcome** | Connection lost after sending DATA, uncertain if relay accepted | `UNKNOWN` and reconciliation |
| **Provider deferred delivery** | Provider accepted submission, destination server deferred | Let provider handle delivery retries; do not resubmit immediately |

SMTP `4xx` usually signals temporary errors and `5xx` permanent errors, yet always examine **command phase**, enhanced status codes, reply text, and provider policies. A timeout does not guarantee the message was rejected.

### 4.1. Do Not Lump All Spring Exceptions Together

Spring Mail may throw `MailSendException`, `MailAuthenticationException`, `MailPreparationException`, or others, with nested causes such as `MessagingException` or socket/TLS failures.

A production classifier should return a safe decision type for workers. Classifier unit tests verify classification logic; **integration tests** verify that decision is durably persisted into outbox and dead-letter storage.

### 4.2. Separating Error Classification from the Worker

You can design:

```java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    UNKNOWN
}

public final class SubmissionFailure
        extends RuntimeException {

    private final FailureKind kind;
    private final String safeCode;

    public SubmissionFailure(
            FailureKind kind,
            String safeCode) {
        super(safeCode);
        this.kind = kind;
        this.safeCode = safeCode;
    }

    public FailureKind kind() {
        return kind;
    }

    public String safeCode() {
        return safeCode;
    }
}
```

`safeCode` is a normalized error code (such as `SMTP_TEMPORARY_451`), **not the raw `ex.getMessage()`** which may expose sensitive SMTP/recipient details.

This model lets tests inject explicitly typed simulated failures without coupling to how an SMTP library formats stack traces. Pair it with dedicated tests verifying the adapter maps real SMTP errors to the right `FailureKind`.

## 5. Two Complementary Integration Test Layers

A high-confidence test suite splits into:

### Layer A - Workflow Integration with Real Database and Controllable Submission Gateway

- Boot a Spring application context with real workers, repositories, and transactions.
- Use PostgreSQL in Testcontainers or a production-equivalent database.
- Replace the **SMTP edge** with a scripted test gateway supporting `ACCEPTED`, `TRANSIENT`, `PERMANENT`, `UNKNOWN`.
- Assert statuses, attempts, leases, `nextAttemptAt`, and dead letters via SQL.
- Control `Clock` to test retry schedules without `sleep`.

This layer proves **Spring workflow + persistence + retry/dead letter** operate together. It does **not** prove real SMTP transport classifies a 451 response properly.

### Layer B - SMTP Transport Integration with a Test Server

- Use a test SMTP server (e.g., GreenMail, Mailpit, or a response-configurable server) permitted in CI.
- Point `JavaMailSenderImpl` to the test endpoint.
- Test connectivity, MIME submission, and valid responses.
- For 4xx/5xx failures, use a **fault-injecting SMTP server** or harness able to reply at the exact protocol phase.
- Test that the adapter translates responses/exceptions into the matching `FailureKind`.

This layer proves the **network/SMTP boundary** works without necessarily booting the whole queue or retry worker system.

### 5.1. Why Not Use a Real SMTP Provider for Every Test?

Real providers involve:
- quotas, anti-spam policies, and rate limits;
- latency and hard-to-reproduce incidents;
- risk of leaking outbound emails;
- credentials/secrets;
- unpredictable asynchronous delivery events;
- 4xx/5xx errors that cannot easily be triggered on demand.

Reserve real providers for controlled smoke/E2E tests rather than making them a dependency of the entire integration suite.

## 6. PostgreSQL Data Model for Testing

An illustrative schema:

```sql
CREATE TABLE mail_outbox (
    message_key UUID PRIMARY KEY,
    recipient VARCHAR(320) NOT NULL,
    subject TEXT NOT NULL,
    plain_text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_mail_attempt_count
        CHECK (attempt_count >= 0),
    CONSTRAINT chk_mail_outbox_status
        CHECK (status IN (
            'PENDING', 'SENDING', 'RETRY_WAIT',
            'SMTP_ACCEPTED', 'DEAD_LETTER', 'UNKNOWN'
        ))
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE TABLE mail_send_attempt (
    attempt_id UUID PRIMARY KEY,
    message_key UUID NOT NULL
        REFERENCES mail_outbox(message_key),
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(32) NOT NULL,
    error_code VARCHAR(120),
    provider_message_id VARCHAR(255),
    CONSTRAINT uq_mail_attempt_number
        UNIQUE (message_key, attempt_number)
);

CREATE TABLE mail_dead_letter (
    message_key UUID PRIMARY KEY
        REFERENCES mail_outbox(message_key),
    failed_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL,
    final_reason VARCHAR(120) NOT NULL,
    operator_note TEXT
);
```

This schema merely illustrates a testable design:
- `mail_outbox` holds the logical email and current state.
- `mail_send_attempt` records every attempt.
- `mail_dead_letter` records why automatic retries stopped.
- Partial index helps workers locate due jobs.
- Unique constraint prevents two attempts with the same sequence number for one message key.

In production, email contents and recipients can be sensitive data: consider encryption, access restrictions, retention, and storing template references/snapshots where appropriate. Test fixtures must use fake addresses and non-sensitive content.

### 6.1. Creating Jobs Inside the Business Transaction

Initial outbox item:

```sql
INSERT INTO mail_outbox (
    message_key, recipient, subject, plain_text,
    status, attempt_count, next_attempt_at,
    created_at, updated_at
)
VALUES (
    :messageKey, :recipient, :subject, :plainText,
    'PENDING', 0, :now, :now, :now
);
```

If an email ties to a unique business event, add a domain constraint such as `(business_event_id, notification_type)` to avoid duplicate logical requests. `message_key` identifies the email, not API-level idempotency across every caller.

### 6.2. Never Delete Rows When Retries Exhaust

When a job dead-letters, keep the outbox row and attempts to:
- investigate past tries;
- correlate against provider logs;
- determine the final failure reason;
- recover via approved procedures;
- measure unprocessable job volumes.

Deleting the job and keeping a single error log line loses details required for support and auditing.

## 7. Atomic Claim: Two Workers Must Never Send the Same Job

A worker must claim due jobs **atomically**. With PostgreSQL, use `FOR UPDATE SKIP LOCKED` inside a short transaction:

```sql
WITH next_job AS (
    SELECT message_key
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox o
SET status = 'SENDING',
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    attempt_count = attempt_count + 1,
    updated_at = :now
FROM next_job n
WHERE o.message_key = n.message_key
RETURNING
    o.message_key,
    o.recipient,
    o.subject,
    o.plain_text,
    o.attempt_count,
    o.lease_token;
```

The claim operation must commit **before calling SMTP**. Never hold a database transaction open across a network call that may stall or time out.

Within the same claim transaction, insert the `mail_send_attempt` row for the new attempt. If recording the attempt fails, roll back the whole claim so no `SENDING` job exists without attempt history.

### 7.1. Lease Tokens and Fencing

When the worker writes outcomes, check the lease token:

```sql
UPDATE mail_outbox
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

If zero rows are updated, the worker may have lost ownership of the job. Fencing protects **database state**, yet **cannot recall an SMTP submission** the old worker already sent. Therefore, concurrency tests must inspect both database state and gateway invocation counts.

### 7.2. An Expired Lease Does Not Prove SMTP Never Sent

A worker may succeed in sending and crash before persisting `SMTP_ACCEPTED`. Moving a job back to `PENDING` and resending immediately merely because a lease expired risks duplicates.

For lease-expired `SENDING` jobs, a conservative design:
- marks the attempt suspicious;
- transitions to `UNKNOWN` or classifies per evidence;
- reconciles with SMTP/provider;
- retries only under an explicit risk policy.

A job claimed where the process crashed **before starting the send** may be handled differently if durable proof exists, yet never infer that solely from lease expiration.

## 8. Retry Policy: Decisions Must Be Observable and Testable

Design a policy taking failure kind, attempt number, and time, returning an explicit decision:

```java
import java.time.Duration;
import java.time.Instant;

public enum NextState {
    RETRY_WAIT,
    DEAD_LETTER,
    UNKNOWN
}

public record RetryDecision(
    NextState state,
    Instant nextAttemptAt,
    String reasonCode
) {}

public final class MailRetryPolicy {

    private final int maxAttempts;

    public MailRetryPolicy(int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive"
            );
        }
        this.maxAttempts = maxAttempts;
    }

    public RetryDecision decide(
            FailureKind kind,
            int attemptNumber,
            Instant now,
            String safeCode) {

        if (kind == FailureKind.UNKNOWN) {
            return new RetryDecision(
                NextState.UNKNOWN, null, safeCode
            );
        }

        if (kind == FailureKind.PERMANENT
                || attemptNumber >= maxAttempts) {
            return new RetryDecision(
                NextState.DEAD_LETTER, null, safeCode
            );
        }

        long waitSeconds =
            2L << Math.min(attemptNumber - 1, 12);

        return new RetryDecision(
            NextState.RETRY_WAIT,
            now.plus(Duration.ofSeconds(waitSeconds)),
            safeCode
        );
    }
}
```

With `maxAttempts=3` and continuous transient failures:
- Attempt 1: `RETRY_WAIT`, wait 2 seconds.
- Attempt 2: `RETRY_WAIT`, wait 4 seconds.
- Attempt 3: `DEAD_LETTER`, no attempt 4.

This backoff is **deterministic** for illustration. Production should account for max delay, jitter, rate limits, deadlines, and `Retry-After` when provider HTTP APIs support it. In integration tests, inject a clock and jitter source or use a predictable test policy to avoid nondeterministic outcomes.

### 8.1. How Are Attempts Counted?

In the example, `attempt_count` increments when claiming creates a new attempt. Do not increment it again during failure handling. If a test uses another convention (such as `retry_count` for retries after the initial try), max-attempt expectations shift by one.

Document clearly:
- `attempt_count=0`: not attempted yet.
- `attempt_count=1`: first send attempt started.
- `attempt_count=3`: all three attempts used.

**Never let an off-by-one bug allow attempt 4 when maxAttempts=3.**

### 8.2. Deadlines and Retry Budgets

Beyond attempt counts, time limits may apply:
- verification emails lose usefulness after tokens expire;
- urgent alerts have tight deadlines;
- invoices can wait longer;
- providers enforce distinct quotas or rate limits.

Integration tests should cover:
- budget remains yet deadline expired;
- retry due yet recipient became suppressed;
- worker halts when total retry budget is exhausted;
- never scheduling an attempt after a link's expiration time.

## 9. Decoupling the Sending Gateway to Test Workflows Without a Real Provider

A thin abstraction:

```java
import java.util.UUID;

public record OutboundMail(
    UUID messageKey,
    String recipient,
    String subject,
    String plainText
) {}

public interface MailSubmissionGateway {
    void submit(OutboundMail mail);
}
```

Production adapter using Spring Mail:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailSubmissionGateway
        implements MailSubmissionGateway {

    private final JavaMailSender sender;
    private final MailFailureClassifier classifier;

    public SpringMailSubmissionGateway(
            JavaMailSender sender,
            MailFailureClassifier classifier) {
        this.sender = sender;
        this.classifier = classifier;
    }

    @Override
    public void submit(OutboundMail mail) {
        try {
            MimeMessage mime = sender.createMimeMessage();
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, false, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), false);

            mime.setHeader(
                "X-Application-Message-Key",
                mail.messageKey().toString()
            );

            sender.send(mime);
        } catch (MailException | MessagingException ex) {
            throw classifier.classify(ex);
        }
    }
}
```

`MailFailureClassifier` is application-defined: it maps Spring/Jakarta Mail exceptions into `SubmissionFailure` with the appropriate `FailureKind`. Never lump every `MailException` into transient; a timeout after `DATA` may be `UNKNOWN`.

**Test-double seam:** in workflow integration tests, swap `MailSubmissionGateway` for a scripted version to control outcomes. Repositories, transactions, retry policy, and workers remain real.

### 9.1. Do Not Mock Repositories When Testing Persistence Integration

If both `MailSubmissionGateway` and repositories are mocked, the test only proves in-code call sequences, failing to verify:
- transaction commits;
- unique constraints;
- atomic claims;
- dead-letter row persistence;
- retry due-time queries;
- crash/restart persistence.

For retry/dead-letter integration tests, repositories and databases should be real. Swap only the **external boundary** you need to control for deterministic outcomes.

## 10. Worker Orchestration and Transaction Boundaries

A worker can follow these steps:

1. `claimDue(now)`: short transaction, transitions job to `SENDING`, issues lease, increments attempt count, creates attempt.
2. `gateway.submit(...)`: network I/O **outside the claim transaction**.
3. On success: short transaction, closes attempt and transitions job to `SMTP_ACCEPTED`.
4. On failure: applies retry policy, then in a transaction saves outcome + `RETRY_WAIT`, `DEAD_LETTER`, or `UNKNOWN`.
5. Scheduler scans due jobs or consumer receives queue signals.

Orchestration example:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

public final class MailOutboxProcessor {

    private final MailOutboxRepository repository;
    private final MailSubmissionGateway gateway;
    private final MailRetryPolicy retryPolicy;
    private final Clock clock;

    public MailOutboxProcessor(
            MailOutboxRepository repository,
            MailSubmissionGateway gateway,
            MailRetryPolicy retryPolicy,
            Clock clock) {
        this.repository = repository;
        this.gateway = gateway;
        this.retryPolicy = retryPolicy;
        this.clock = clock;
    }

    public boolean processOne() {
        Instant now = clock.instant();

        Optional<ClaimedMail> candidate =
            repository.claimDue(now);

        if (candidate.isEmpty()) {
            return false;
        }

        ClaimedMail job = candidate.get();

        try {
            gateway.submit(job.mail());
            repository.markAccepted(
                job.messageKey(),
                job.leaseToken(),
                job.attemptId(),
                clock.instant()
            );
        } catch (SubmissionFailure ex) {
            RetryDecision decision = retryPolicy.decide(
                ex.kind(),
                job.attemptNumber(),
                clock.instant(),
                ex.safeCode()
            );

            repository.recordFailure(
                job.messageKey(),
                job.leaseToken(),
                job.attemptId(),
                decision,
                clock.instant()
            );
        }

        return true;
    }
}
```

`MailOutboxRepository` and `ClaimedMail` are application-defined contracts; repository methods must be backed by matching SQL/transactions. This example shows **separation of responsibilities**, not a complete production implementation.

### 10.1. Repository Contract

```java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface MailOutboxRepository {

    Optional<ClaimedMail> claimDue(Instant now);

    void markAccepted(
        UUID messageKey,
        UUID leaseToken,
        UUID attemptId,
        Instant now
    );

    void recordFailure(
        UUID messageKey,
        UUID leaseToken,
        UUID attemptId,
        RetryDecision decision,
        Instant now
    );
}

public record ClaimedMail(
    UUID messageKey,
    UUID leaseToken,
    UUID attemptId,
    int attemptNumber,
    OutboundMail mail
) {}
```

Implementation requirements:
- `claimDue` selects jobs with an atomic query in a short transaction.
- Creates `attemptId` and attempt history inside the same claim transaction.
- `markAccepted` updates attempt and outbox **in the same transaction**, requiring the matching lease token.
- `recordFailure` updates attempt and job in the same transaction; for dead letters, also inserts into `mail_dead_letter` in that transaction.
- Updates failing to find a valid lease must signal a conflict rather than silently overwriting state.
- Never let database exceptions get caught by the `SubmissionFailure` branch, as those are state-persistence infrastructure failures requiring separate handling.

### 10.2. Dead-Letter Commits Must Be Atomic

Conceptual handling for a `DEAD_LETTER` decision:

```text
BEGIN
  verify row status=SENDING AND lease_token=current
  UPDATE mail_send_attempt
     SET outcome='FAILED', error_code=...
  UPDATE mail_outbox
     SET status='DEAD_LETTER', lease_token=NULL,
         last_error_code=..., updated_at=...
  INSERT INTO mail_dead_letter(...)
COMMIT
```

If `INSERT mail_dead_letter` fails, the transaction must roll back so no outbox row claims dead-letter status while missing its detail record.

With an external broker DLQ, atomicity spans both database and broker. Never treat `publish to DLQ` then `ack source message` as atomic without proper transactional/outbox/broker guarantees. Integration tests must cover process crashes between steps.

## 11. Test Environment with PostgreSQL Testcontainers

The goal is running against a database with production-like transaction and locking behavior, especially when using PostgreSQL-specific `FOR UPDATE SKIP LOCKED` and partial indexes.

Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Align versions with your project's dependency management. Use Testcontainers when a Docker/container runtime is available in CI. A real SMTP provider is unnecessary for workflow tests.

### 11.1. Initializing the Container and Datasource

```java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class MailOutboxRetryIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }

    @Autowired JdbcTemplate jdbc;
}
```

In a real project, the test class also autowires `MailOutboxProcessor`, `MailOutboxRepository`, retry policy, and the test gateway. Create schemas via official migrations like Flyway/Liquibase or controlled scripts rather than hard-coding table creation in every test method.

### 11.2. Do Not Accidentally Wrap the Entire Test in @Transactional

If a test method has `@Transactional` and rolls back at completion, it may **fail to reflect real worker transaction boundaries**. If claim/send/outcome run inside an uncommitted test transaction, worker threads or separate connections cannot see the job.

For integration tests verifying durability:
- let application services manage their own transactions;
- create test fixtures and commit before running the worker;
- query state from an independent connection/transaction when needed;
- clean up data between tests;
- never use test rollback to simulate application commits.

### 11.3. Specify Test Schemas Explicitly

Examples:
- Run production migrations in the test profile if safe.
- Or test migrations equivalent to the real schema.
- Avoid using H2 to conclude PostgreSQL `SKIP LOCKED` works properly.
- If production uses a database other than PostgreSQL, test on that engine rather than assuming identical locking behavior.

## 12. Scripted Failure Test Gateway

A simple test double can succeed or throw `SubmissionFailure` in a planned sequence. It **never sends external emails**.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;

public final class ScriptedMailGateway
        implements MailSubmissionGateway {

    public enum Outcome {
        ACCEPTED,
        TRANSIENT,
        PERMANENT,
        UNKNOWN
    }

    private final Deque<Outcome> script = new ArrayDeque<>();
    private final List<OutboundMail> submissions =
        new ArrayList<>();

    public synchronized void plan(Outcome... outcomes) {
        script.clear();
        submissions.clear();
        script.addAll(Arrays.asList(outcomes));
    }

    @Override
    public synchronized void submit(OutboundMail mail) {
        submissions.add(mail);

        if (script.isEmpty()) {
            throw new AssertionError(
                "No scripted SMTP outcome remaining"
            );
        }

        Outcome next = script.removeFirst();

        switch (next) {
            case ACCEPTED -> {
                return;
            }
            case TRANSIENT -> throw new SubmissionFailure(
                FailureKind.TRANSIENT, "SMTP_TEMP_451"
            );
            case PERMANENT -> throw new SubmissionFailure(
                FailureKind.PERMANENT, "SMTP_PERM_550"
            );
            case UNKNOWN -> throw new SubmissionFailure(
                FailureKind.UNKNOWN, "SMTP_RESULT_UNKNOWN"
            );
        }
    }

    public synchronized int invocationCount() {
        return submissions.size();
    }

    public synchronized List<OutboundMail> submitted() {
        return List.copyOf(submissions);
    }
}
```

In production, no gateway generates scripted outcomes like this. It is a **test fault-injection seam**. Simulating `UNKNOWN` does not mean every real timeout is unknown; a dedicated classifier test must verify protocol mapping.

### 12.1. Why Fail When the Script Runs Out?

If the gateway defaulted to success on an empty script, a broken test could silently execute extra unexpected attempts and still pass. Throwing `AssertionError` on script exhaustion catches stray calls.

However, if running tests in parallel or sharing a gateway across multiple workers, make scripting thread-safe and keyed by message key. Avoid a global shared deque causing flakiness.

### 12.2. Dedicated Test Bean and @Primary

With a Spring context:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
public class MailGatewayTestConfiguration {

    @Bean
    @Primary
    ScriptedMailGateway scriptedMailGateway() {
        return new ScriptedMailGateway();
    }
}
```

`ScriptedMailGateway` implements `MailSubmissionGateway`, so marking the bean `@Primary` lets it inject into the processor instead of the production adapter. Import the test configuration with `@Import(MailGatewayTestConfiguration.class)` when needed.

If your project uses other bean wiring, verify the context picks only one gateway for the worker; prevent the real sender from running in a test background scheduler.

## 13. Controlling Time to Test Retries Without Sleep

A retry test should never do:

```java
Thread.sleep(5000);
worker.processOne();
```

That approach:
- slows down CI;
- flakes under CPU load;
- makes multi-attempt testing cumbersome;
- collides with real scheduler timings;
- fails to verify `next_attempt_at` cleanly.

Replace it with a **controllable clock**:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableTestClock extends Clock {

    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    public MutableTestClock(Instant initial) {
        this(
            new AtomicReference<>(initial),
            ZoneOffset.UTC
        );
    }

    private MutableTestClock(
            AtomicReference<Instant> now,
            ZoneId zone) {
        this.now = now;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableTestClock(now, newZone);
    }

    @Override
    public Instant instant() {
        return now.get();
    }

    public void advance(Duration duration) {
        now.updateAndGet(t -> t.plus(duration));
    }

    public void reset(Instant instant) {
        now.set(instant);
    }
}
```

Tests can call `clock.advance(Duration.ofSeconds(2))` to simulate "due time arrived" without waiting 2 real seconds.

### 13.1. Providing the Clock Bean

In test configuration:

```java
@Bean
MutableTestClock mutableTestClock() {
    return new MutableTestClock(
        Instant.parse("2026-11-12T08:00:00Z")
    );
}

@Bean
@Primary
Clock testClock(MutableTestClock clock) {
    return clock;
}
```

If the Spring app defines a real `Clock` bean, ensure the test clock injects cleanly into workers and retry policies. Never scatter `Instant.now()` across repositories and workers if you want deterministic tests.

### 13.2. Disable Schedulers When Tests Invoke Workers Directly

In integration tests, invoke `processor.processOne()` deliberately under test control. If `@Scheduled` also runs, it may claim jobs unexpectedly and destabilize assertions.

Separate scheduled triggers from the processor and disable triggers in the test profile using an application-defined conditional property. Never assume one generic Spring property disables every `@Scheduled` method declared in the app.

## 14. Scenario 1 - Transient Failure Followed by Success

Example with max attempts = 3:

```text
T0: PENDING
 |
 +-- processOne()
 |   -> attempt 1: TRANSIENT
 |   -> RETRY_WAIT; next=T0+2s
 |
 +-- processOne() immediately: not claimed
 |
 +-- advance clock 2s
 |   -> attempt 2: TRANSIENT
 |   -> RETRY_WAIT; next=T0+2s+4s
 |
 +-- advance clock 4s
     -> attempt 3: ACCEPTED
     -> SMTP_ACCEPTED
```

Required assertions:
- Gateway called exactly 3 times.
- All 3 submissions share the **same message key**.
- Attempt IDs/attempt numbers are distinct.
- Status after two failures is `RETRY_WAIT`.
- `next_attempt_at` matches policy.
- Zero premature attempts occur.
- Final status is `SMTP_ACCEPTED`.
- Zero dead-letter entries exist.
- Extra scheduler runs after success do not resend.

### 14.1. Testing Against the Real Repository Contract

In a project implementing `MailOutboxRepository`, you can write:

```java
@Test
void transientFailuresAreRetriedThenAccepted() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.ACCEPTED
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("RETRY_WAIT");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);

    // Must not claim/send before due time.
    assertThat(processor.processOne()).isFalse();
    assertThat(gateway.invocationCount()).isEqualTo(1);

    clock.advance(Duration.ofSeconds(2));
    assertThat(processor.processOne()).isTrue();
    assertThat(queries.attemptCount(key))
        .isEqualTo(2);

    clock.advance(Duration.ofSeconds(4));
    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("SMTP_ACCEPTED");
    assertThat(queries.attemptCount(key))
        .isEqualTo(3);
    assertThat(queries.deadLetterCount(key))
        .isZero();

    assertThat(gateway.invocationCount())
        .isEqualTo(3);

    assertThat(gateway.submitted())
        .extracting(OutboundMail::messageKey)
        .containsOnly(key);

    assertThat(processor.processOne()).isFalse();
}
```

`fixtures` and `queries` are **project-defined test fixture/query helpers**, not Spring APIs. They must write/read against real PostgreSQL. The snippet illustrates test structure; integrate it with your repository implementation and Spring wiring.

### 14.2. Verifying Retry Timestamps with SQL

Do not check status alone:

```sql
SELECT status, attempt_count, next_attempt_at
FROM mail_outbox
WHERE message_key = :messageKey;
```

Tests should compare `next_attempt_at` against the clock and delay policy. Otherwise, an implementation could set `RETRY_WAIT` with a past timestamp, causing the worker to loop continuously.

## 15. Scenario 2 - Exhausting Max Attempts Moves to Dead Letter

Suppose max attempts = 3 and SMTP always returns transient errors:

```text
Attempt 1: TRANSIENT -> RETRY_WAIT
Attempt 2: TRANSIENT -> RETRY_WAIT
Attempt 3: TRANSIENT -> DEAD_LETTER
Attempt 4: MUST NOT OCCUR
```

Assertions:
- `attempt_count=3`.
- Three attempt rows exist.
- Outbox status is `DEAD_LETTER`.
- Dead-letter record matches message key, final reason, and `failed_at`.
- `next_attempt_at` no longer makes workers claim the job.
- Zero 4th attempt occurs even on repeated worker calls.
- Neither the message nor attempt history is deleted.

Example test:

```java
@Test
void maxAttemptsMovesJobToDeadLetter() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT,
        ScriptedMailGateway.Outcome.TRANSIENT
    );

    assertThat(processor.processOne()).isTrue();

    clock.advance(Duration.ofSeconds(2));
    assertThat(processor.processOne()).isTrue();

    clock.advance(Duration.ofSeconds(4));
    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("DEAD_LETTER");
    assertThat(queries.attemptCount(key))
        .isEqualTo(3);
    assertThat(queries.deadLetterCount(key))
        .isEqualTo(1);
    assertThat(queries.finalDeadLetterReason(key))
        .isEqualTo("SMTP_TEMP_451");

    assertThat(gateway.invocationCount()).isEqualTo(3);
    assertThat(processor.processOne()).isFalse();
}
```

**Never assert only that a dead-letter record exists:** if the job remains in `RETRY_WAIT`, the scheduler could still fire a 4th attempt despite a row in the DLQ table.

### 15.1. Deadline Expired Before Max Attempts

You can also test another case:
- `maxAttempts = 5`;
- verification email expires after 10 minutes;
- only 2 attempts used, yet the next retry falls past the deadline.

Policy should transition the job per business rules (e.g., `DEAD_LETTER` with `EXPIRED_NOTIFICATION`) instead of sending an unusable link. Never assume attempt count is the sole limit.

## 16. Scenario 3 - Permanent Failure Moves Immediately to Dead Letter

A clearly classified permanent error need not burn through max attempts.

```text
PENDING
   |
   v
Attempt 1: PERMANENT
   |
   v
DEAD_LETTER
```

Example:

```java
@Test
void permanentFailureGoesToDeadLetterImmediately() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.PERMANENT
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("DEAD_LETTER");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);
    assertThat(queries.deadLetterCount(key))
        .isEqualTo(1);

    assertThat(gateway.invocationCount())
        .isEqualTo(1);

    assertThat(processor.processOne()).isFalse();
}
```

Note: never assume every `MailSendException` is permanent. This test simulates **a failure already classified as permanent**; verifying the classifier against real SMTP belongs in a separate test.

### 16.1. Invalid Address Before SMTP

If validation fails **before the worker creates a send attempt**, the state model may differ:
- business logic rejects creating the outbox row;
- or the outbox is created and immediately dead-lettered with reason `INVALID_RECIPIENT`;
- `attempt_count` may be 0 if SMTP was never tried.

Tests must follow your defined contract; never artificially increment `attempt_count` just to make all cases look uniform.

## 17. Scenario 4 - UNKNOWN Must Never Be Blindly Retried

A hard edge case:

```text
Worker                     SMTP relay
  |---- MIME DATA ----------->|
  |---- end-of-DATA --------->|
  |                           | accepted/enqueued
  |<--- connection lost ------X
  |
  +-- Timeout / IOException
  |
  +-- Unknown whether relay received the message
```

If the app retries immediately, it risks sending two emails. When the outcome is uncertain, policy should store `UNKNOWN`, awaiting reconciliation or a business decision acknowledging duplicate risk.

Test:

```java
@Test
void unknownSubmissionDoesNotAutoRetry() {
    UUID key = fixtures.enqueueMail(
        "customer@example.net",
        clock.instant()
    );

    gateway.plan(
        ScriptedMailGateway.Outcome.UNKNOWN
    );

    assertThat(processor.processOne()).isTrue();

    assertThat(queries.status(key))
        .isEqualTo("UNKNOWN");
    assertThat(queries.attemptCount(key))
        .isEqualTo(1);
    assertThat(queries.deadLetterCount(key))
        .isZero();

    clock.advance(Duration.ofDays(1));

    assertThat(processor.processOne()).isFalse();
    assertThat(gateway.invocationCount())
        .isEqualTo(1);
}
```

You do not necessarily move `UNKNOWN` straight to dead letter, because it represents **needing more information**, not proof that submission failed. Systems may maintain a dedicated reconciliation queue.

### 17.1. When Can UNKNOWN Move Back to Retry?

Only when:
- the provider/API supports an idempotency key per contract;
- logs/provider confirm the message was never accepted;
- or business policy explicitly accepts duplicate risk with clear tracking.

Tests must verify the reconciliation decision is durably persisted before moving `UNKNOWN` to `RETRY_WAIT`.

### 17.2. Database Outage After SMTP Accepted

A special case:
1. `gateway.submit(...)` returns success.
2. `repository.markAccepted(...)` hits a database outage.
3. The job stays `SENDING` and its lease expires.

Tests must simulate **failure to persist outcomes after side effects**, not just `gateway.submit` failures. This is where workflows most easily duplicate sends.

The safe approach is recording the job as potentially accepted for reconciliation rather than immediately resetting all lease-expired rows to pending. Where possible, use gateways/protocols supporting idempotency or an audit/reconciliation mechanism.

## 18. Scenario 5 - Jobs Not Yet Due Must Not Be Claimed

Integration tests should insert two jobs:
- `A`: `RETRY_WAIT` with `next_attempt_at` in the future.
- `B`: `PENDING` and currently due.

Expected:
- Worker picks B.
- A keeps its `attempt_count` unchanged.
- Once the clock advances to A's due time, the worker picks A.
- No busy-loop causes the CPU to repeatedly query the same un-due job.

Tests should use a real database because `WHERE next_attempt_at <= :now`, indexes, and datetime semantics are core parts of the system.

### 18.1. Exact Time Boundary

Include `next_attempt_at == now`, which must be claimable if the convention is `<=`. If code uses `<`, jobs may slip to the next polling cycle. Specify timestamp types (UTC/`TIMESTAMPTZ`) and account for clock skew across nodes.

### 18.2. Jitter Must Be Controllable in Tests

Production backoff adds jitter to avoid thundering herds. In integration tests, inject a fixed-seed random source or mock `RetryDelayStrategy`, then assert ranges/timestamps per contract.

Never call `Math.random()` directly in production code if doing so makes due times unpredictable in tests; likewise, never assert one exact second count when the real policy includes jitter.

## 19. Scenario 6 - Two Workers Running Concurrently

Concurrency is a compelling reason to use **real PostgreSQL** instead of mocked repositories.

Suppose one `PENDING` job exists and two workers call `claimDue(now)` concurrently.

```text
Worker A                 PostgreSQL              Worker B
   |                         |                        |
   |-- claimDue ------------>|<----------- claimDue --|
   |                         |                        |
   |<-- leaseToken=A --------|------ no job --------->|
   |                         |                        |
   +-- submit SMTP           |                        |
   +-- markAccepted -------->|                        |
```

Expected:
- One worker gets the job, the other gets nothing.
- Total gateway submissions equal 1.
- `attempt_count=1`.
- One attempt history row.
- Final status is accurate.
- Zero simultaneous lease owners exist.

### 19.1. Using Barriers/Latches Instead of Thread.sleep

In tests you can use:
- `CountDownLatch` to synchronize when both workers start claiming;
- a two-thread `ExecutorService`;
- `Future.get(...)` with reasonable timeouts;
- database queries after both complete.

Skeleton pattern:

```java
CountDownLatch start = new CountDownLatch(1);
ExecutorService executor = Executors.newFixedThreadPool(2);

try {
    Callable<Boolean> task = () -> {
        start.await();
        return processor.processOne();
    };

    Future<Boolean> first = executor.submit(task);
    Future<Boolean> second = executor.submit(task);

    start.countDown();

    boolean a = first.get(10, TimeUnit.SECONDS);
    boolean b = second.get(10, TimeUnit.SECONDS);

    assertThat((a ? 1 : 0) + (b ? 1 : 0))
        .isEqualTo(1);

    assertThat(gateway.invocationCount())
        .isEqualTo(1);
} finally {
    executor.shutdownNow();
}
```

The wait in `Future.get` is a **timeout guarding against hangs**, not a sleep to "wait for retries". Serious concurrency tests should control transactions/connections so both workers truly contend for the same job. If one finishes too fast sequentially, the test passes without triggering actual contention.

### 19.2. Lease Expiry Mid-Send

A dangerous edge case:
- Worker A claims the job and stalls before writing the outcome.
- The lease expires.
- Worker B starts processing again.
- Worker A finishes SMTP and attempts to persist its result.

Tests must verify:
- A's update using the stale lease token is rejected.
- The database is not overwritten by stale state.
- The system handles the **duplicate submission** risk, since DB fencing cannot stop external SMTP from having accepted the message.

Never automatically let B resend simply because A lost its lease unless a policy exists for uncertain outcomes.

## 20. Scenario 7 - Application Restarts Do Not Lose Retries

A production bug that only surfaces after restarts:
- retries tracked by an in-memory `ScheduledFuture`;
- `next_attempt_at` never persisted;
- process restart wipes out the schedule.

Integration tests should:
1. Insert a job.
2. Run the first attempt, hitting a transient error.
3. Confirm `RETRY_WAIT` and `next_attempt_at` committed.
4. Instantiate a new worker/service or cleanly restart the Spring context.
5. Keep the **same PostgreSQL database**.
6. Advance the clock to due time.
7. Run the new worker and verify attempt 2 executes.

Never rely on an in-memory `@Scheduled` event as the sole source of truth. A database or durable broker must hold retry state.

### 20.1. Another Test: Crash Between Claim and Send

Simulate:
- Job transitions to `SENDING` with a lease.
- Worker stops before invoking the gateway.
- After the lease expires, recovery policy inspects durable data.

If the system has durable proof the gateway was never called, it may retry. If uncertain, keep `UNKNOWN` to reduce duplicate risk. Tests must rely on **real observable data**, never assuming every `SENDING` job was unsent.

### 20.2. Testing Transaction Rollback Failures

Make `recordFailure` hit a database constraint error mid-way. Expected:
- Never commit `DEAD_LETTER` status if inserting the dead-letter record fails.
- Attempt history is not half-written when atomicity is required.
- Operational signals fire to surface outcome-persistence errors.

This is a transaction integration test; it cannot be inferred from Mockito tests verifying two method calls.

## 21. Scenario 8 - Safe Dead-Letter Replay

A dead letter is not "a folder of emails to blindly resend". Uncontrolled replays can trigger duplicates or repeat permanent errors.

A clean workflow might look like:

```text
DEAD_LETTER
     |
     v
Operator reviews reason / recipient / template
     |
     v
Fix root cause + authorize replay
     |
     +--> Requeue same logical message
     |    with new attempt (when policy permits)
     |
     +--> Create a new logical notification
          with explicit relationship (when business requires)
```

Define rules for:
- who is authorized to replay;
- when replay is allowed;
- whether to reuse the message key or create a new logical email;
- whether attempt history is preserved;
- whether budgets reset;
- whether recipients must still be re-validated;
- whether provider suppressions/bounces must be checked;
- requiring reconciliation before replaying `UNKNOWN` cases.

### 21.1. Assertions for Replay

- Regular workers never auto-replay dead letters.
- Only authorized endpoints/commands can requeue.
- Audit records capture actor, timestamp, reason, and original message key.
- Replay never deletes attempt history or dead-letter history.
- When replaying the same logical email, `attempt_number` keeps incrementing instead of colliding on unique keys.
- Explicit rules govern post-replay retry budgets.
- Replaying twice with the same request key never creates two jobs.
- Suppressed or opted-out recipients are not automatically allowed to be re-sent.

### 21.2. Do Not Silently Reset attempt_count

Resetting `attempt_count` to 0 while retaining older attempts makes counts inconsistent. Instead design:
- `attempt_count` as total lifetime attempts for the message, never reset;
- `retry_cycle` or `replay_generation` counting approved replay rounds;
- per-generation budgets with distinct attempt caps.

Any model works as long as it is clearly specified and integration tests protect its invariants.

## 22. SMTP Integration Testing with a Local Test Server

Database workflow tests using a scripted gateway do not prove `JavaMailSenderImpl` speaks SMTP properly. A separate small suite should send into an **SMTP sandbox**.

Options:
- **GreenMail**: Java SMTP/IMAP/POP3 test server library, convenient for Spring/Jakarta Mail integration.
- **Mailpit/MailHog**: test email capture tools via SMTP with UI/API for inspecting messages.
- **Programmable SMTP fake**: server or protocol proxy capable of actively returning `421`, `451`, `550`, closing connections, or timing out at exact phases.
- **Provider sandbox**: used when testing real vendor contracts, subject to separate quotas and rules.

Pick the tool matching what you need to prove. An accept-all SMTP sink is great for happy paths, yet **does not necessarily simulate every SMTP error**.

### 22.1. Example Sending to GreenMail to Verify Real SMTP

Conceptual integration test example with a GreenMail dependency matching your project's Jakarta Mail version:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.assertj.core.api.Assertions.assertThat;

class SmtpSubmissionIntegrationTest {

    @Test
    void realJavaMailSenderCanSubmitToTestServer()
            throws Exception {

        GreenMail smtp = new GreenMail(ServerSetupTest.SMTP);
        smtp.start();

        try {
            JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

            sender.setHost("127.0.0.1");
            sender.setPort(smtp.getSmtp().getPort());

            var message = sender.createMimeMessage();
            var helper = new MimeMessageHelper(
                message, false, "UTF-8"
            );

            helper.setFrom("no-reply@example.com");
            helper.setTo("qa@example.net");
            helper.setSubject("Retry test");
            helper.setText("Hello from SMTP test server.", false);

            sender.send(message);

            assertThat(smtp.getReceivedMessages())
                .hasSize(1);
        } finally {
            smtp.stop();
        }
    }
}
```

Choose port/test setup to avoid collisions in parallel runs; consult your GreenMail version's API for random ports or isolated server instances. The example illustrates **the SMTP happy path**, not SMTP 451/550 or dead-letter policies.

### 22.2. Testing 451 or 550 Replies with Fault Injection

To test real SMTP failures, use a server capable of actively returning:

```text
Client                      SMTP test relay
  |---- EHLO ---------------->|
  |<--- 250 ------------------|
  |---- MAIL FROM ----------->|
  |<--- 250 ------------------|
  |---- RCPT TO ------------->|
  |<--- 451 Temporary failure |
```

And:

```text
Client                      SMTP test relay
  |---- RCPT TO ------------->|
  |<--- 550 No such user -----|
```

Tests must verify:
- which exception Jakarta Mail/Spring throws;
- whether nested SMTP reply/status codes are available;
- that the classifier maps transient vs. permanent accurately;
- that recipients/tokens are not logged outside policy.

Simulating disconnect after `DATA` can yield `UNKNOWN`. Never infer from a bare `SocketException` alone whether the relay accepted or rejected the message.

### 22.3. Avoid Confusing Retry Layers

Once a provider accepts a submission and reports delivery deferred, **the provider** normally retries delivery to the target MX. The worker must not resubmit immediately on a deferred event. In tests, distinguish:
- **submission retries** managed by the Spring worker;
- **delivery retries** managed by the provider/MTA.

A `deferred` webhook must never trigger a second `JavaMailSender.send(...)` call for an already-accepted message.

## 23. Testing Broker Dead-Letter Queues When Not DB-Only

If the system uses RabbitMQ, Kafka, or another broker, dead-letter semantics differ. Do not apply `mail_dead_letter` SQL rules directly and assume the broker works identically.

### 23.1. RabbitMQ and DLX

With RabbitMQ:
- Messages can dead-letter when rejected/nacked without requeue, when TTL expires, or when queue policies trigger.
- Dead-letter exchanges (DLX) and routing keys must be configured properly.
- Brokers may route messages to other queues; verify broker config and consumer acks.
- Prevent unbounded DLQ -> main queue -> DLQ loops.

Integration tests with RabbitMQ Testcontainers can:
1. Publish a job to the source queue.
2. Have the consumer fail processing per policy.
3. Verify the message appears in the DLQ.
4. Verify the source queue has no remaining active job.
5. Verify metadata/attempt count or headers per contract.
6. Test conditional replay and deduplication.

### 23.2. Kafka and DLT

With Kafka, a dead-letter topic (DLT) is typically populated by consumer framework/policy routing unprocessable records to a separate topic. Verify:
- retry counts and backoffs;
- topics/partitions/headers;
- offset commits;
- idempotency across consumer restarts;
- DLT publish failures;
- replay authorization.

Kafka does not share identical default semantics with RabbitMQ DLX. Test with the real broker and matching framework listener containers.

### 23.3. Atomicity Across DB, SMTP, and Broker

No single simple transaction spans all of:
- database transactions;
- non-rollbackable SMTP submissions;
- broker acks/publishes;
- delivery webhooks.

A good test does not promise **exactly-once email delivery**. It proves the system **persists state durably, minimizes duplicates, enforces idempotency, and handles uncertain outcomes** per design contract.

## 24. Testing Operational Observability and Alerts

Retries and dead letters are not just algorithms. During incidents, operations teams need to see what happened.

Useful metrics:

| Metric | Purpose |
|---|---|
| `mail_outbox_pending` | Jobs not yet attempted |
| `mail_outbox_retry_wait` | Jobs waiting for retry |
| `mail_outbox_unknown` | Jobs requiring reconciliation |
| `mail_dead_letter_total` | Total dead-lettered jobs by reason |
| `mail_submit_attempts_total` | Submission attempts by provider/outcome |
| `mail_retry_delay_seconds` | Wait-delay distribution |
| `mail_outbox_oldest_age_seconds` | Detecting aging backlogs |
| `mail_lease_expired_total` | Alerting on abnormal workers/timeouts |
| `mail_send_duplicate_suspected_total` | Tracking suspected duplicate events |

Illustrative structured log:

```json
{
  "event": "mail.dead_letter",
  "messageKey": "msg-123",
  "attemptId": "att-3",
  "attemptNumber": 3,
  "reasonCode": "SMTP_TEMP_451",
  "status": "DEAD_LETTER",
  "retryOwner": "outbox-worker"
}
```

There is no need to log full MIME, recipient addresses, authentication credentials, or attachment bytes for tracing.

### 24.1. Verifying Dead-Letter Events Emit Once

If the application emits a domain event/metric when a job moves to dead letter:
- one dead-letter transition should emit one business event per idempotency policy;
- webhook/worker retries must not re-emit events endlessly;
- logs/metrics must never be the sole source of truth for state;
- if events go to a broker, use a transactional outbox if guaranteed emission on DB commit is needed.

Integration tests can assert the event record persists properly in the database before the worker moves to terminal state. Testing metric exporter formatting belongs to a separate layer.

### 24.2. Prioritized Alerting

Examples:
- Any `UNKNOWN` lingering past threshold likely needs reconciliation.
- Spiking dead letters from `SMTP_AUTH_FAILURE` signals broken config/secrets.
- Growing retry queues with zero successes indicate a provider outage.
- Rising dead letters from invalid recipients may call for data hygiene.
- Backlogs older than SLA must trigger alerts.

Integration tests can verify monitoring queries/data sources return accurate counts without sending real alert notifications during every test run.

## 25. Isolating Test Fixtures and Keeping Suites Deterministic

### 25.1. Isolation Between Tests

When sharing a database container, each test must clean state cleanly:

```sql
TRUNCATE TABLE
    mail_dead_letter,
    mail_send_attempt,
    mail_outbox
RESTART IDENTITY CASCADE;
```

Use this only in a **confirmed test database**, never run such cleanup against production. With multiple test classes running in parallel, use separate schemas/containers or explicit isolation strategies.

Do not let a leftover `RETRY_WAIT` job from a prior test surprise the next test. Reset the scripted gateway and test clock before each case.

### 25.2. Ensure Database Schemas Use Migrations

Never craft ad-hoc schemas differing from production just to pass tests. When production uses Flyway/Liquibase:
- run matching migrations on the PostgreSQL test container;
- execute real repositories;
- verify indexes, unique constraints, and transaction boundaries;
- add extra test data only for scenarios, never alter schema rules.

### 25.3. Use Synthetic Data

Use:
- `customer@example.net`;
- `no-reply@example.com`;
- `ORD-TEST-001`;
- a fresh message-key UUID per test case;
- plaintext containing no real personal data.

Never put real SMTP passwords, reset tokens, or real recipients in fixtures. If the test environment carries provider configs, ensure the fake gateway **cannot accidentally delegate to a real sender**.

### 25.4. Do Not Depend on Wall-Clock Time

When testing retry due times, compare `Instant` values against the test clock. Avoid `Thread.sleep`. When testing concurrency, use barriers/latches and bounded timeouts rather than random waits.

If production policies use jitter, inject a deterministic strategy in tests. Doing so preserves the value of database/worker integration tests.

## 26. Recommended Test Matrix

| Scenario | Expected Outcome |
|---|---|
| New job, immediate SMTP accept | `SMTP_ACCEPTED`, 1 attempt, no DL |
| Transient error then accepted | `RETRY_WAIT` -> `SMTP_ACCEPTED`, on schedule |
| Worker invoked before `next_attempt_at` | Not claimed, not sent |
| Exact due-time boundary | Claimed per `<=` rule |
| Continuous transient failures until max attempts | `DEAD_LETTER`, no attempt past threshold |
| Permanent failure on first attempt | Immediate dead letter |
| Invalid input prior to send | Rejected or dead-lettered per contract, no infinite retries |
| Unknown submission outcome | `UNKNOWN`, no auto-resend |
| Provider deferred after acceptance | No new submission created |
| Two workers claim same job | Only one lease/attempt/gateway submission |
| Stale lease writes outcome after expiry | Fencing rejects stale update |
| DB outage after SMTP accepted | Never assumed safe to resend |
| Dead-letter insert fails | Transaction rolls back; no split state committed |
| Restart between two retries | `RETRY_WAIT` persists; next attempt runs |
| Restart during `SENDING` | Recovers per policy, no blind resend |
| Unauthorized replay | Rejected, state unchanged |
| Authorized replay | Audited, attempt history intact |
| Duplicate replay request | Does not trigger two unintended replays |
| Multi-recipient / partial success | Does not retry whole list and duplicate accepted recipients |
| Changed retry budget | Applied from config, no off-by-one attempt errors |
| SMTP 451/550 from test relay | Adapter classifies by command/context |
| SMTP success via test server | `JavaMailSenderImpl` submits MIME, no Internet traffic |
| Dead letter already exists | Idempotent write/constraint prevents duplicate records |

This matrix helps select test cases for **retry and dead-letter integration**. Hard-to-simulate concurrency/recovery cases require matching test infrastructure; never mock repositories and mark them "integration tested".

## 27. Common Misconceptions

### "Verifying JUnit called send three times is enough"

No. You must prove database states, retry timestamps, attempt history, and dead letters persist accurately. Three mock calls do not reflect real transactions or retry schedules.

### "Every MailException should be retried"

No. Template, credential, certificate, or recipient errors may require fixing root causes. Timeouts with uncertain outcomes need a dedicated state.

### "Dead letter means deleting the job from the system"

No. Preserve history/metadata for reconciliation and replay; a DLQ/dead-letter table is a holding and investigation area, not an anonymous trash bin.

### "Max attempts = 3 means three retries after the initial try"

Not if the contract counts total attempts. Define `attempt_count` clearly and test for off-by-one bugs.

### "Whenever a lease expires, the worker definitely hasn't sent"

No. The worker may have sent and crashed before recording the result, or stalled after the SMTP side effect. You need reconciliation and duplicate-handling policies.

### "Testcontainers PostgreSQL is a unit test"

No. Running a real database in a container is an integration test - exactly what is needed when testing transactions, locking, and due-time queries.

### "If GreenMail passes, the real provider will surely pass"

No. A test SMTP server verifies code paths and protocol under controlled conditions. Real providers add TLS policies, quotas, AUTH, reputation, and routing.

### "SMTP accepted means delivered"

No. That is a submission milestone. Delivery can still defer or bounce, and providers may retry at another layer.

### "Putting @Retryable around send gives reliability"

No. In-memory retries vanish on process restart, obscure `UNKNOWN` outcomes, and risk duplicates. Critical emails require persistence, budgets, and observability.

### "Having a message key makes SMTP deduplicate automatically"

No. Generic SMTP makes no idempotency promise on custom headers. Message keys aid tracing; they do not make email sending exactly-once.

## 28. Practice Exercises

### Exercise 1 - Schema and States

Create `mail_outbox`, `mail_send_attempt`, and `mail_dead_letter` in PostgreSQL Testcontainers. Insert a `PENDING` job and query its status from another connection after commit.

### Exercise 2 - Transient Retry

Build a scripted gateway returning `TRANSIENT` then `ACCEPTED`. Run the processor, advance the clock by exact delay, and verify 2 attempts share one message key with final status `SMTP_ACCEPTED`.

### Exercise 3 - Dead Letter After Max Attempts

Set `maxAttempts=3` with all three returning `TRANSIENT`. Prove the job moves to `DEAD_LETTER`, has one dead-letter entry, and cannot spawn attempt 4.

### Exercise 4 - Permanent Failure

Have the gateway return `PERMANENT` on the first try. Verify immediate dead-lettering, safe error code persistence, and zero retry schedule.

### Exercise 5 - Unknown Outcome

Have the gateway return `UNKNOWN`. Advance the clock by one day and run the worker. Prove zero new submissions occur and the job awaits reconciliation.

### Exercise 6 - Due Time

Insert two jobs with different `next_attempt_at` values. Verify the worker picks only the due job; test the exact `next_attempt_at == now` boundary.

### Exercise 7 - Concurrency

Run two workers against PostgreSQL with a latch/barrier racing to claim one job. Verify one attempt, one lease, and one gateway submission.

### Exercise 8 - Lease Fencing

Simulate Worker A's lease expiring and Worker B acquiring a new lease. Have A call `markAccepted` with the stale token; verify rejection without overwriting state.

### Exercise 9 - Crash/Restart

After the first transient failure, instantiate a new processor against the same database. Rerun when the clock reaches due time and confirm the retry schedule survived.

### Exercise 10 - Atomic Dead-Letter Transaction

Intentionally make the `mail_dead_letter` insert fail in a transaction test. Verify status updates and attempt outcomes do not half-commit.

### Exercise 11 - SMTP Fault Injection

Use a test SMTP server returning `451` on `RCPT TO` and `550` in another case. Test the adapter's error classification rather than testing only the scripted gateway.

### Exercise 12 - Timeout After DATA

Simulate a relay that may have accepted before dropping the connection prior to replying. Record `UNKNOWN` and design a reconciliation test before resending.

### Exercise 13 - Dead-Letter Replay

Design a replay API/command with authorization checks and auditing. Test that duplicate replay requests do not create two jobs and attempt history stays intact.

### Exercise 14 - Provider Deferred

Simulate a `deferred` webhook after submission reached `SMTP_ACCEPTED`. Verify the app updates delivery status if tracked, **without calling `JavaMailSender.send` again**.

### Exercise 15 - Deadline-Based Retry Budget

For a verification email expiring in 10 minutes, simulate a 15-minute provider outage. Even with attempts remaining, test that the job stops on deadline and never sends an expired link.

### Exercise 16 - Observability and Security

For an `SMTP_AUTH_FAILURE` dead letter, verify structured events/metrics contain message key, attempt number, and safe code while excluding SMTP passwords, full MIME bodies, and verification tokens.

## 29. Summary

**Testing retries and dead letters** in Spring Framework Mail must go beyond mocking `send(...)` and counting invocations. The goal is proving **the entire durable workflow**: a logical email is stored in the outbox, workers claim the right job, every attempt is logged, transient errors schedule retries, permanent/budget-exhausted failures move to dead letters, and `UNKNOWN` outcomes are held for reconciliation.

Practical approach:

1. Use **PostgreSQL Testcontainers** or a production-equivalent database to verify transactions, unique constraints, claims, and leases.
2. Control the SMTP layer with a **scripted gateway** in workflow tests; use a test SMTP relay/fault injection in a separate transport integration suite.
3. Inject **`Clock`** and delay strategies to verify due times and backoffs accurately without `Thread.sleep`.
4. Test **happy paths, transient errors, permanent errors, max attempts, `UNKNOWN`, crash recovery, concurrency, atomic dead-letter commits, and replay**.
5. Never equate `SMTP_ACCEPTED` with `DELIVERED` and never resubmit when the provider already accepted and deferred delivery.
6. Preserve **message key, attempt history, dead-letter reasons, and audits**, while keeping sensitive content out of logs.
7. Never claim exactly-once SMTP: when submission outcomes are uncertain, surface duplicate risk and enforce reconciliation/approval.

A strong retry and dead-letter integration suite does more than check that a worker "tried enough times". It proves the system **never loses work, never loops infinitely, never resends when unsafe, and leaves clear operational evidence whenever automated processing must stop**.
