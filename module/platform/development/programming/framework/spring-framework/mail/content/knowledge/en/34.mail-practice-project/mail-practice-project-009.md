# Building a Retry Worker with State and Dead Letter

A **Spring Framework Mail** application can send emails directly inside an HTTP request using **JavaMailSender.send(...)**. This approach is fine for learning the API, but easily runs into problems when SMTP is slow, a provider throttles requests, a worker restarts, a user clicks send again, or the system needs to know accurately whether a notification is waiting, has been submitted to SMTP, or requires manual handling.

In this **practice project**, we build an **email delivery worker** using **Spring Boot, Spring Mail, Spring JDBC, and PostgreSQL**. The application saves the intent to send in a **transactional outbox**, the worker claims jobs with short transactions, sends MIME mail via JavaMailSender, records outcomes in a state machine, retries failures proven not to have been accepted by the provider, and moves permanent failures or jobs that exhaust their retry budget to **dead letter**. When an SMTP timeout leaves the outcome unknown, the job enters **UNKNOWN** for reconciliation instead of blindly resending duplicates.

This lesson does more than describe concepts. It includes project structure, SQL schema, Java records, repository, service, scheduler, retry policy, SMTP sending code, REST notification creation examples, local run instructions, unit/integration tests, observability, and dead-letter queue (DLQ) handling procedures.

> **Engineering principle:** **ACCEPTED** means the SMTP server/provider accepted the submission according to the response the application received; **it does not mean the email has reached the Inbox**. When a send attempt has an unknown outcome (**UNKNOWN**), blind retries can send duplicates. Dead letter is a place to hold work **that can be inspected and reprocessed**, not a place to delete data or a guarantee of exactly-once delivery.

## 1. Project Goals

After completing the practice project, the system should be able to:

1. Accept an email send request with a **business idempotency key**.
2. Persist a durable **notification job** without sending SMTP inside the database transaction.
3. Claim due jobs with a **lease token** to prevent stale workers from overwriting results.
4. Limit the number of attempts and use **exponential backoff + jitter** on retryable failures.
5. Maintain clear states: **PENDING, IN_FLIGHT, RETRY_WAIT, ACCEPTED, UNKNOWN, DEAD_LETTER, CANCELLED, EXPIRED**.
6. Separate permanent errors, configuration errors, transient errors, and ambiguous SMTP outcomes.
7. Record **attempt history**, state transition reasons, and timestamps.
8. Move jobs that cannot be processed automatically to **dead letter**, allowing operators to inspect and conditionally replay them.
9. Prevent two replicas from submitting the same job concurrently and isolate sensitive emails.
10. Measure backlog, job age, retries, dead letters, and provider failure scenarios.

### Scope

To stay focused, the reference version uses **PostgreSQL as a durable job store**, without requiring Kafka or RabbitMQ. **Dead letter** is represented by a state together with a history table, not necessarily a separate physical queue. When scaling out to a broker, the principles around idempotency, state, and controlling UNKNOWN remain the same.

The code snippets are **implementation templates with explicit contracts**; before running in production, you must add secret management, migrations, authorization, policies, and the parts noted throughout. They do not replace running tests in your project environment.

## 2. Why Not Call SMTP Directly in Business Logic?

Initial example:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<String> confirm(@PathVariable String id) {
    orderService.confirm(id);
    mailSender.send(messageFor(id));
    return ResponseEntity.ok("confirmed");
}
~~~

What can go wrong:

| Incident | Possible Result |
| --- | --- |
| Order commits, SMTP unavailable | Order is confirmed but email is not sent |
| SMTP takes 15 seconds | HTTP request stalls or times out |
| Client retries HTTP because no response arrived | May enqueue or send again |
| JVM crashes after order commit, before send | Send intent is lost |
| Provider accepted then response is lost | Retry can cause duplicates |
| Multiple requests send concurrently | Quota/rate limit is exceeded |

### Proposed Model

~~~text
                 API / Business Event
                         |
                         v
                 Notification Service
                         |
                 BEGIN TRANSACTION
                         |
               +---------+---------+
               |                   |
               v                   v
          Business update     Insert outbox row
               |                   |
               +---------+---------+
                         |
                      COMMIT
                         |
                         v
                    HTTP response

             Separate scheduled worker(s)
                         |
                         v
                 Claim due job (DB)
                         |
                         v
                 Rate / policy checks
                         |
                         v
                   JavaMailSender
                         |
               +---------+----------+
               |         |          |
               v         v          v
           ACCEPTED  RETRY_WAIT    UNKNOWN
                         |          |
                         v          v
                       PENDING   Reconcile
                         |
                         v
                  DEAD_LETTER if exhausted
~~~

If business data and the outbox share the same transaction manager/database, business changes and send intent are committed/rolled back atomically. **SMTP remains outside that transaction**; the worker must classify outcomes and avoid duplicate sends.

## 3. States and Meanings

| State | Meaning | Automatically picked for sending? |
| --- | --- | --- |
| **PENDING** | Job created, no attempt yet | Yes, once available_at is reached |
| **IN_FLIGHT** | Worker claimed job, holds lease/attempt | Other workers cannot claim while lease is valid |
| **RETRY_WAIT** | Retryable failure, waiting for backoff | Yes, once next_attempt_at is reached |
| **ACCEPTED** | Provider/server confirmed submission receipt | Never automatically resent |
| **UNKNOWN** | Unknown whether message was accepted | No auto retry; requires reconciliation |
| **DEAD_LETTER** | Cannot continue automatically: permanent, exhausted tries, or policy | No; only controlled handling/replay |
| **EXPIRED** | Job passed its business deadline | No |
| **CANCELLED** | Decision made to cancel send intent | No |

### State Machine

~~~text
  CREATE
    |
    v
  PENDING ---------------------> CANCELLED / EXPIRED
    |
    | atomic claim + lease
    v
  IN_FLIGHT
    |
    +---- SMTP accepted -------------------> ACCEPTED
    |
    +---- proven retryable failure --------> RETRY_WAIT
    |                                         |
    |                                         | due time
    |                                         v
    |                                       IN_FLIGHT
    |
    +---- permanent / attempts exhausted ---> DEAD_LETTER
    |
    +---- ambiguous SMTP outcome -----------> UNKNOWN
    |
    '-- lease expired / crash -------------> UNKNOWN

  UNKNOWN -- reviewed, proven not accepted --> controlled retry
  UNKNOWN -- evidence accepted ------------> ACCEPTED
  UNKNOWN -- cannot reconcile / policy ----> DEAD_LETTER for review

  DEAD_LETTER -- approved replay ----------> PENDING (new generation)
~~~

Transitioning from **UNKNOWN** back to PENDING is only valid with evidence/approval under policy. Never assume a worker crash is proof that SMTP did not receive the message: the worker may have crashed after the provider accepted and before persisting the outcome.

### State Is Data, Not Just Logs

If you only print **"retrying..."** in logs without persisting state, a JVM restart will not know how many times the job was tried or whether it is in UNKNOWN. State must live in a database or durable queue with clear semantics.

## 4. Four Identifiers Not to Mix Up

~~~text
businessKey        = ORDER:1528:CONFIRMED:customer-7
notificationId     = UUID of one logical notification
attemptId          = UUID of one SMTP attempt
providerMessageId  = ID returned by provider, if any
~~~

- **businessKey** prevents enqueuing two identical logical notifications from the same event.
- **notificationId** is the key of the outbox job, stable across retries.
- **attemptId** changes for each transport attempt.
- **providerMessageId** assists lookup/reconciliation if the provider returns one.

**The email Message-ID header** is not a guarantee of global SMTP deduplication. Two submissions with the same Message-ID can still produce two emails. Do not confuse Message-ID with notificationId.

## 5. Environment Setup

Reference stack:

- **Java 17+**.
- **Spring Boot 3.x** with Jakarta Mail.
- **spring-boot-starter-mail**.
- **spring-boot-starter-jdbc**.
- **spring-boot-starter-web** for the demo API.
- **spring-boot-starter-validation** if DTO validation is needed.
- **PostgreSQL** as the outbox store.
- **Flyway** or your chosen migration tool.
- **JUnit 5**, Spring Boot Test, Testcontainers, and an SMTP test fixture for testing.

You do not need a real email account to complete the worker logic. You can use an isolated test SMTP server that accepts mail without relaying to the Internet.

### Suggested Source Structure

~~~text
src/main/java/com/example/mailworker/
  MailWorkerApplication.java
  api/
    NotificationController.java
    CreateNotificationRequest.java
  domain/
    DeliveryState.java
    MailJob.java
    AttemptResult.java
  persistence/
    MailOutboxRepository.java
    JdbcMailOutboxRepository.java
  service/
    NotificationEnqueueService.java
    DeliveryWorker.java
    RetryPolicy.java
    SubmissionClassifier.java
    DeadLetterService.java
  transport/
    MailTransport.java
    SpringMailTransport.java
  config/
    MailWorkerProperties.java

src/main/resources/
  application.yml
  db/migration/
    V1__mail_worker.sql

src/test/java/com/example/mailworker/
  RetryPolicyTest.java
  MailWorkerIntegrationTest.java
  MailTransportTest.java
~~~

These paths are an **example structure** for a learning project, not a requirement to create extra files in the current article-writing task.

## 6. Dependencies

An illustrative Maven **pom.xml** snippet when the Spring Boot parent is already managed by a BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

In some newer Flyway versions, PostgreSQL support lives in a separate **flyway-database-postgresql** module; the project must add the module matching its dependency graph. Do not assume the pom fragment above is a standalone runnable project: you need the corresponding parent/BOM, plugins, Java target, and build configuration.

## 7. PostgreSQL Schema: Outbox and Attempt History

A durable schema enables classification and reconciliation:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    sender_profile VARCHAR(100) NOT NULL,
    subject TEXT NOT NULL,
    plain_body TEXT NOT NULL,
    html_body TEXT,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    lease_owner VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    provider_message_id VARCHAR(250),
    last_error_code VARCHAR(120),
    last_error_summary TEXT,
    dead_letter_reason VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    CONSTRAINT uq_mail_outbox_business
        UNIQUE (tenant_id, business_key),
    CONSTRAINT ck_mail_outbox_attempts
        CHECK (attempt_count >= 0 AND max_attempts > 0),
    CONSTRAINT ck_mail_outbox_state CHECK (
        state IN (
            'PENDING', 'IN_FLIGHT', 'RETRY_WAIT',
            'ACCEPTED', 'UNKNOWN', 'DEAD_LETTER',
            'EXPIRED', 'CANCELLED'
        )
    )
);

CREATE INDEX idx_mail_outbox_due
ON mail_outbox (next_attempt_at, id)
WHERE state IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease
ON mail_outbox (lease_until)
WHERE state = 'IN_FLIGHT';

CREATE INDEX idx_mail_outbox_dead
ON mail_outbox (updated_at, id)
WHERE state = 'DEAD_LETTER';

CREATE TABLE mail_attempt (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    lease_token UUID NOT NULL,
    provider VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(50) NOT NULL,
    error_code VARCHAR(120),
    error_summary TEXT,
    provider_message_id VARCHAR(250),
    CONSTRAINT uq_mail_attempt_number
        UNIQUE (notification_id, attempt_number)
);

CREATE INDEX idx_mail_attempt_notification
ON mail_attempt (notification_id, attempt_number DESC);

CREATE TABLE mail_dead_letter_audit (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL REFERENCES mail_outbox(id),
    action VARCHAR(40) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40),
    operator_id VARCHAR(120) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### Notes on the Schema

- **UNIQUE (tenant_id, business_key)** prevents creating two identical notifications for the same business rule. Do not use recipient address as the sole unique key: one person can legitimately receive multiple notifications.
- **next_attempt_at** helps the scheduler fetch due jobs.
- **lease_owner + lease_token + lease_until** represent temporary ownership and fencing.
- **attempt_count** increments when claiming an attempt, not on every poll.
- **mail_attempt** separates multiple attempts and each attempt's error.
- **DEAD_LETTER** keeps the record; the audit table adds administrative action history.
- **recipient_address/body** is sensitive data requiring access control, encryption/retention; production systems can store an **opaque reference** instead of full content.

### Do Not Let the Schema Dictate Every Business Policy

For example, max_attempts=5 is an illustrative default. OTPs may have a shorter TTL and fewer attempts; invoice emails have different policies. **Do not modify states arbitrarily in the DB** outside controlled transition services/repositories.

## 8. Spring Boot Application Configuration

Example **application.yml** with illustrative values:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/maildemo
    username: maildemo
    password: example-local-only
  flyway:
    enabled: true
  mail:
    host: 127.0.0.1
    port: 3025
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000

app:
  mail-worker:
    enabled: true
    poll-delay-ms: 1000
    max-jobs-per-poll: 10
    lease-seconds: 45
    base-retry-seconds: 10
    max-retry-seconds: 600
    max-attempts: 5
~~~

**The database password and SMTP host** are for local demo use only. Production must use a secret manager/environment injection, TLS certificate verification, a verified From identity, and an authorized mail provider. When sending to SMTP port 587, configure authentication and STARTTLS per contract; **never send username/password over an unprotected connection**.

### Timeouts Related to Leases

Even with an SMTP connection timeout of 5 seconds and read/write timeouts of 10 seconds, a single attempt can still exceed 10 seconds due to multiple SMTP steps, DNS, attachments, or a slow provider. **A 45-second lease is just an example**, not a guarantee of safety. Production must choose controlled total I/O limits, heartbeat/lease extension, or treat overdue attempts as UNKNOWN when there is doubt whether the server accepted.

### Put Parameters in Typed Configuration

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail-worker")
public record MailWorkerProperties(
        boolean enabled,
        long pollDelayMs,
        int maxJobsPerPoll,
        long leaseSeconds,
        long baseRetrySeconds,
        long maxRetrySeconds,
        int maxAttempts
) {
    public Duration lease() {
        return Duration.ofSeconds(leaseSeconds);
    }
}
~~~

Register properties with **@EnableConfigurationProperties(MailWorkerProperties.class)** or **@ConfigurationPropertiesScan**. For a real project, add Bean Validation for positive numbers and min/max relationships. YAML configuration uses kebab-case names, and Spring Boot binding maps them to the corresponding record components.

## 9. Spring Boot Bootstrap and Scheduler

~~~java
package com.example.mailworker;

import com.example.mailworker.config.MailWorkerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@EnableConfigurationProperties(MailWorkerProperties.class)
public class MailWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MailWorkerApplication.class, args);
    }
}
~~~

The scheduler runs periodically, while the repository decides **which job is due and not held under another lease**. There is no need to keep a sleeping thread per notification.

### Scheduler Is Not a Distributed Leader

If you deploy four replicas with **@EnableScheduling**, every replica runs the scheduler. This **does not automatically cause duplicates** when claims are atomic, but you must prevent each replica from independently exceeding provider quota and enforce cluster-wide concurrency/batch-size limits.

## 10. Creating Notifications: Idempotent Enqueue

An API can accept a request:

~~~json
{
  "businessKey": "ORDER:ORD-1528:CONFIRMED:customer-7",
  "recipient": "customer@example.test",
  "subject": "Order confirmation ORD-1528",
  "plainText": "Order ORD-1528 has been confirmed.",
  "html": "<p>Order <strong>ORD-1528</strong> has been confirmed.</p>"
}
~~~

In production, **tenantId and From/senderProfile must not be trusted directly from an unauthenticated client**. Tenant must come from the authentication context; sender profile is restricted by tenant/purpose.

### API Should Clearly Say “Queued”, Not “Sent”

~~~text
POST /notifications
  -> 202 Accepted
  -> { notificationId, state: "PENDING" }
~~~

**HTTP 202 Accepted at the application API** means the server accepted the request for processing, **not SMTP 250 accepted**. Do not tell the user “email delivered successfully” before any attempt has occurred.

### PostgreSQL Deduplicating Insert

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, business_key,
    recipient_address, sender_profile,
    subject, plain_body, html_body,
    state, attempt_count, max_attempts,
    next_attempt_at, expires_at
)
VALUES (
    :id, :tenantId, :businessKey,
    :recipient, :senderProfile,
    :subject, :plainBody, :htmlBody,
    'PENDING', 0, :maxAttempts,
    :availableAt, :expiresAt
)
ON CONFLICT (tenant_id, business_key) DO NOTHING;
~~~

After inserting, if a conflict occurs, read the existing job by tenant/businessKey and return the same ID **only if the logical request is compatible**. If a caller reuses businessKey with a different payload/recipient, return an **idempotency conflict** instead of silently reporting success as if it were the same request.

### Transactional Outbox with Business Logic

~~~text
BEGIN
   UPDATE orders SET status = 'CONFIRMED' ...
   INSERT INTO mail_outbox (...) ON CONFLICT DO NOTHING
COMMIT
~~~

When the business DB and outbox share the same PostgreSQL/transaction manager, the notification intent exists atomically with the order change. If the application is only a mail service receiving API calls, the enqueue transaction only guarantees the outbox is persisted, not another service's transaction.

### Do Not Send Immediately Inside the Enqueue Transaction

~~~java
@Transactional
public UUID enqueue(...) {
    UUID id = repository.insert(...);
    // Do not call mailSender.send(...) here.
    return id;
}
~~~

If network I/O sits inside a DB transaction, locks are held too long and there is still no atomic commit with SMTP. The worker is a separate boundary.

## 11. Java Data Types for the Worker

~~~java
import java.time.Instant;
import java.util.UUID;

public enum DeliveryState {
    PENDING,
    IN_FLIGHT,
    RETRY_WAIT,
    ACCEPTED,
    UNKNOWN,
    DEAD_LETTER,
    EXPIRED,
    CANCELLED
}

public record ClaimedMailJob(
        UUID id,
        String tenantId,
        String recipient,
        String senderProfile,
        String subject,
        String plainBody,
        String htmlBody,
        int attemptCount,
        int maxAttempts,
        Instant expiresAt,
        UUID leaseToken,
        Instant leaseUntil
) {
}
~~~

**attemptCount** here is the number of attempts actually started, not how many times a quota/controller deferred the job. If a job is not yet permitted to send due to quota, reschedule it without incrementing the attempt count.

### Separating claim and beginAttempt

A strict workflow:

1. **Claim:** PENDING/RETRY_WAIT → IN_FLIGHT, issue lease token; not sending yet.
2. **Preflight:** check expiry, sender, content, quota.
3. **Begin attempt:** write mail_attempt and increment attempt_count in a transaction.
4. **Submit:** call SMTP outside the transaction.
5. **Finalize:** update state and attempt outcome if the lease token still matches.

Step 3 ensures accurate attempt tracking. If the worker crashes **after beginAttempt but before submit**, the system still cannot be certain whether transport was called unless there is reliable evidence logging, so lease recovery may conservatively choose UNKNOWN.

## 12. Claiming a Job Atomically with SKIP LOCKED

This is the key step preventing two workers from picking up the same job at the same time. Use a **PostgreSQL CTE + FOR UPDATE SKIP LOCKED**:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= :now
      AND (expires_at IS NULL OR expires_at > :now)
      AND attempt_count < max_attempts
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS job
SET state = 'IN_FLIGHT',
    lease_owner = :workerId,
    lease_token = :leaseToken,
    lease_until = :leaseUntil,
    updated_at = :now
FROM candidate
WHERE job.id = candidate.id
RETURNING
    job.id, job.tenant_id,
    job.recipient_address,
    job.sender_profile,
    job.subject, job.plain_body,
    job.html_body, job.attempt_count,
    job.max_attempts, job.expires_at,
    job.lease_token, job.lease_until;
~~~

### Why SKIP LOCKED?

Two workers looking for jobs concurrently:

~~~text
Worker A locks job 101.
Worker B sees job 101 locked -> skips it.
Worker B claims job 102.
~~~

This is an appropriate queue-like pattern for PostgreSQL with multiple consumers. Important condition: **SELECT and UPDATE must execute in the same statement/transaction**. If the app runs SELECT id in one transaction and an unconditional UPDATE in another, a race still exists.

### Claim Transactions Must Be Short

Do not hold a DB transaction/row lock while calling SMTP. Commit right after claiming. Network I/O happens outside the transaction so you do not exhaust the connection pool or cause lock contention.

### Claim Does Not Increment attempt_count

In the SQL above, attempt_count stays unchanged. This is intentional because quota may reject the job before SMTP starts. The worker calls **beginAttempt** separately when ready to submit.

### Expired Jobs Will Not Be Claimed, But Still Need State Transition

The condition expires_at > now prevents expired jobs from entering an attempt. However, PENDING/RETRY_WAIT rows that have already expired must still be transitioned to **EXPIRED** by housekeeping for clear reporting rather than left behind indefinitely.

## 13. JDBC Repository: Claiming with a Lease Token

An illustrative implementation using **NamedParameterJdbcTemplate**:

~~~java
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcMailOutboxRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcMailOutboxRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<ClaimedMailJob> claimNext(
            String workerId,
            Instant now,
            Duration lease
    ) {
        UUID leaseToken = UUID.randomUUID();
        Instant leaseUntil = now.plus(lease);

        String sql = """
                WITH candidate AS (
                    SELECT id
                    FROM mail_outbox
                    WHERE state IN ('PENDING', 'RETRY_WAIT')
                      AND next_attempt_at <= :now
                      AND (expires_at IS NULL OR expires_at > :now)
                      AND attempt_count < max_attempts
                    ORDER BY next_attempt_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE mail_outbox AS job
                SET state = 'IN_FLIGHT',
                    lease_owner = :worker,
                    lease_token = :token,
                    lease_until = :until,
                    updated_at = :now
                FROM candidate
                WHERE job.id = candidate.id
                RETURNING job.*
                """;

        var params = new MapSqlParameterSource()
                .addValue("now", Timestamp.from(now))
                .addValue("worker", workerId)
                .addValue("token", leaseToken)
                .addValue("until", Timestamp.from(leaseUntil));

        List<ClaimedMailJob> jobs = jdbc.query(
                sql, params,
                (rs, rowNum) -> new ClaimedMailJob(
                        rs.getObject("id", UUID.class),
                        rs.getString("tenant_id"),
                        rs.getString("recipient_address"),
                        rs.getString("sender_profile"),
                        rs.getString("subject"),
                        rs.getString("plain_body"),
                        rs.getString("html_body"),
                        rs.getInt("attempt_count"),
                        rs.getInt("max_attempts"),
                        rs.getTimestamp("expires_at") == null
                                ? null
                                : rs.getTimestamp("expires_at")
                                    .toInstant(),
                        rs.getObject("lease_token", UUID.class),
                        rs.getTimestamp("lease_until").toInstant()
                )
        );

        return jobs.stream().findFirst();
    }
}
~~~

**JdbcMailOutboxRepository.claimNext(...)** is called from another Spring bean so the transaction proxy takes effect. Do not rely on self-invocation within the same class assuming **@Transactional** will create a transaction.

### Claiming Alone Does Not Guarantee Zero Duplicates

If an SMTP call runs longer than the lease, another worker could reclaim the job. Recovery must distinguish **IN_FLIGHT timeout** from **PENDING**: do not grab the stale job and immediately resend because the server may have accepted it. A later section designs recovery to move expired leases to UNKNOWN first, preventing automatic duplicates.

### Clock Note

The example uses the application's **Instant.now(...)**. Across multiple hosts, clock skew can distort leases/processing windows. Production can use consistent DB time or monitor NTP/time synchronization, and avoid overly short leases.

## 14. Recording Attempt Start in a Separate Transaction

Claiming only grants processing rights; the worker may discover quota is not ready and return the job to the wait schedule **without an SMTP attempt**. Only right before calling transport do we increment **attempt_count** and insert a **mail_attempt** row.

Atomic SQL to perform this:

~~~sql
WITH bumped AS (
    UPDATE mail_outbox
    SET attempt_count = attempt_count + 1,
        updated_at = :now
    WHERE id = :notificationId
      AND state = 'IN_FLIGHT'
      AND lease_token = :leaseToken
      AND lease_until > :now
      AND attempt_count < max_attempts
    RETURNING attempt_count
)
INSERT INTO mail_attempt (
    id, notification_id, attempt_number,
    lease_token, provider, started_at, outcome
)
SELECT
    :attemptId,
    :notificationId,
    bumped.attempt_count,
    :leaseToken,
    :provider,
    :now,
    'STARTED'
FROM bumped
RETURNING attempt_number;
~~~

If no row is returned, the worker **must not send**: the lease may have expired, the token may have changed, or max_attempts may have been reached. Never ignore the update result just because a MimeMessage is already built in memory.

### Why Increment Attempts at Start, Not Finish?

Suppose a worker sends via SMTP and then the JVM crashes before writing the result. If attempt_count only incremented after sending, the database would think no attempt ever happened and might send infinitely. Creating the attempt record before the external side effect at least shows the system **started the send path**.

### Does BEGIN ATTEMPT Prove SMTP Was Called?

No. The worker can crash right after the transaction writes STARTED, before actually calling SMTP. During recovery, we have a window of uncertainty. Choosing **UNKNOWN** is safer than confidently resending; stage markers/telemetry can be added, but you should not claim exactly-once.

### Prevent Quota Waits from Counting as Attempts

If the quota controller returns **NO_PERMIT**, the repository transitions **IN_FLIGHT → RETRY_WAIT** and updates next_attempt_at **without incrementing attempt_count**. Otherwise, jobs could end up in dead letter simply from waiting on quota without ever trying to send.

## 15. Finalizing an Attempt with a Fencing Token

After SMTP, the worker needs to update state. But if the lease expired and recovery or an operator already changed the job, the stale worker must not overwrite it.

Example:

~~~sql
UPDATE mail_outbox
SET state = :targetState,
    provider_message_id = :providerMessageId,
    last_error_code = :errorCode,
    last_error_summary = :safeSummary,
    next_attempt_at = COALESCE(
        :nextAttemptAt, next_attempt_at
    ),
    dead_letter_reason = :deadLetterReason,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    accepted_at = CASE
        WHEN :targetState = 'ACCEPTED'
        THEN :now
        ELSE accepted_at
    END,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'IN_FLIGHT'
  AND lease_token = :leaseToken;
~~~

Only when affected rows = **1** is finalization considered successfully persisted. In the same transaction, update the corresponding **mail_attempt** row:

~~~sql
UPDATE mail_attempt
SET finished_at = :now,
    outcome = :attemptOutcome,
    error_code = :errorCode,
    error_summary = :safeSummary,
    provider_message_id = :providerMessageId
WHERE id = :attemptId
  AND notification_id = :notificationId
  AND lease_token = :leaseToken
  AND outcome = 'STARTED';
~~~

If the attempt update does not affect exactly one row, the transaction must roll back and report a conflict. Never allow a transaction to commit an ACCEPTED state with inconsistent history because of a swallowed exception.

### What Does a Fencing Token Solve?

~~~text
10:00 Worker A claimed token A.
10:01 Lease expired / operator changed state.
10:02 Worker A receives an old SMTP response.
10:02 Worker A tries UPDATE WHERE token=A.
10:02 Affected rows=0 -> cannot overwrite newer state.
~~~

However, fencing **does not undo an external side effect that already happened**. If Worker A already submitted successfully, rejecting the DB update cannot “unsend the email”. That is why recovery of expired IN_FLIGHT needs the UNKNOWN policy.

### Repository Should Have Explicit Operations

~~~java
public interface MailJobStore {

    java.util.Optional<ClaimedMailJob> claimNext(
            String workerId,
            java.time.Instant now,
            java.time.Duration lease
    );

    java.util.UUID beginAttempt(
            ClaimedMailJob job,
            String provider,
            java.time.Instant now
    );

    void releaseWithoutAttempt(
            ClaimedMailJob job,
            java.time.Instant nextAt,
            String reason
    );

    void finishAttempt(
            ClaimedMailJob job,
            java.util.UUID attemptId,
            AttemptResolution resolution,
            java.time.Instant now
    );

    int quarantineExpiredLeases(java.time.Instant now);
    int expireUnsentJobs(java.time.Instant now);
}
~~~

Each operation updating the DB must run under the appropriate transaction. When coordinating outbox/attempt updates in the same commit, place the boundary on a clear **repository service bean**, rather than using self-invocation and assuming the Spring proxy always activates.

## 16. Defining Provider-Independent Send Outcomes

Business code should not rely directly on raw SMTP exception text to decide the next state. Create a normalized contract:

~~~java
public enum SubmissionKind {
    ACCEPTED,
    RETRYABLE_NOT_ACCEPTED,
    PERMANENT_NOT_ACCEPTED,
    UNKNOWN
}

public record SubmissionResult(
        SubmissionKind kind,
        String providerMessageId,
        String reasonCode,
        String safeSummary
) {
    public static SubmissionResult accepted(String providerId) {
        return new SubmissionResult(
                SubmissionKind.ACCEPTED, providerId, null, null
        );
    }

    public static SubmissionResult unknown(
            String reasonCode
    ) {
        return new SubmissionResult(
                SubmissionKind.UNKNOWN, null,
                reasonCode, "Submission outcome requires review"
        );
    }
}

public interface MailTransport {
    SubmissionResult submit(ClaimedMailJob job);
}
~~~

**RETRYABLE_NOT_ACCEPTED** is used only when there is reliable evidence that the server **did not accept the content**. For a generic SMTP error, do not infer this solely from a “timeout” message.

### Error Categories

| Error | Meaning | Safe Outcome |
| --- | --- | --- |
| Cannot connect before SMTP dialogue | DATA not sent yet | RETRYABLE_NOT_ACCEPTED if stage is proven |
| Provider returns clear 4xx before acceptance | Temporary rejection | RETRYABLE_NOT_ACCEPTED per provider contract |
| Recipient address deterministically invalid | Cannot send with this data | PERMANENT_NOT_ACCEPTED |
| Wrong SMTP auth | Configuration/provider issue | Pause lane, alert; avoid retry storm |
| Template missing required variable | Render error | Dead letter or review before SMTP |
| Lost response after DATA | Server may have accepted | UNKNOWN |
| API returns success with provider message ID | Submission accepted | ACCEPTED |
| Worker dies mid-send | Cannot know whether completed | UNKNOWN on lease recovery |

### Distinguishing SMTP Errors from Pre-SMTP Errors

If the template parser throws an exception **before MailTransport.submit(...)**, there is no SMTP attempt. Do not mark a deterministic format error as UNKNOWN; handle it as **PREPARATION_FAILED / DEAD_LETTER** per policy. Conversely, if the socket resets while sending is underway, a generic exception does not prove the server never received the content.

## 17. JavaMailSender Adapter with Conservative Classification

The example below uses MIME multipart when both HTML and plain text alternatives are present. It illustrates a conservative policy: **send returns normally → ACCEPTED**, SMTP error without sufficient proof → UNKNOWN.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SpringMailTransport implements MailTransport {

    private final JavaMailSender sender;
    private final SenderProfileResolver senderProfiles;

    public SpringMailTransport(
            JavaMailSender sender,
            SenderProfileResolver senderProfiles
    ) {
        this.sender = sender;
        this.senderProfiles = senderProfiles;
    }

    @Override
    public SubmissionResult submit(ClaimedMailJob job) {
        final MimeMessage mime = sender.createMimeMessage();

        try {
            String from = senderProfiles.verifiedFrom(
                    job.senderProfile(), job.tenantId()
            );

            boolean withHtml = job.htmlBody() != null
                    && !job.htmlBody().isBlank();

            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, withHtml, "UTF-8"
            );
            helper.setFrom(from);
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());

            if (withHtml) {
                helper.setText(
                        job.plainBody(), job.htmlBody()
                );
            } else {
                helper.setText(job.plainBody());
            }
        } catch (MessagingException | IllegalArgumentException e) {
            // Deterministic compose failure before calling SMTP.
            return new SubmissionResult(
                    SubmissionKind.PERMANENT_NOT_ACCEPTED,
                    null,
                    "MAIL_COMPOSITION_FAILED",
                    "Invalid mail payload"
            );
        }

        try {
            sender.send(mime);

            // SMTP transport does not guarantee a provider-issued ID.
            return SubmissionResult.accepted(null);

        } catch (MailAuthenticationException e) {
            return new SubmissionResult(
                    SubmissionKind.PERMANENT_NOT_ACCEPTED,
                    null,
                    "SMTP_AUTH_CONFIGURATION",
                    "SMTP credentials/configuration must be reviewed"
            );
        } catch (MailException e) {
            // Do not assume every MailException means not accepted.
            return SubmissionResult.unknown(
                    "SMTP_OUTCOME_AMBIGUOUS"
            );
        }
    }
}

public interface SenderProfileResolver {
    String verifiedFrom(String profile, String tenantId);
}
~~~

### Why Not Automatically Retry Every MailException?

**MailSendException** can wrap one or more causes, or even partial failures when sending to multiple recipients. Without knowing the SMTP stage and acceptance outcome, sending all of them to RETRY_WAIT risks duplicates. The example chooses UNKNOWN to preserve safety; production can build a provider-specific classifier and add **RETRYABLE_NOT_ACCEPTED** paths when proof exists.

### Authentication Errors Are a Provider-Wide Issue

Sending one job to permanent/quarantine makes sense to avoid infinite retries, but if all SMTP credentials just expired, **you must not dump hundreds of thousands of jobs into the DLQ within minutes**. You need a circuit breaker/provider pause and alert, keeping remaining jobs unattempted until the configuration is fixed.

### Verified From Must Not Come from Free-Form Input

**SenderProfileResolver** must map senderProfile/tenant to a configured, verified address. Never use a From field supplied by an unauthorized user to send on behalf of another tenant.

### Limitations of the Illustrative Adapter

The code above does not yet implement quota limiting, a template registry, attachment streaming, delivery webhooks, SPF/DKIM/DMARC setup, or recipient suppression. Those belong in separate services before/outside transport; **do not pack all business logic into the JavaMailSender adapter**.

## 18. Preparation Stage: Validating Before Spending an Attempt

A production worker can verify:

1. The recipient is validated and still eligible.
2. The tenant/purpose is allowed to send to the recipient.
3. The sender profile exists and is verified.
4. Plain/HTML bodies meet template policy.
5. Subject contains no CR/LF injection.
6. Attachments match provider type/size quotas.
7. The notification has not expired or been cancelled.
8. Template revision/model snapshot is pinned and valid.

### Classifying Validation Failures

~~~text
PERMANENT_INVALID_RECIPIENT
TENANT_SCOPE_VIOLATION
TEMPLATE_REQUIRED_VARIABLE_MISSING
ATTACHMENT_TOO_LARGE
SUPPRESSED_RECIPIENT
EXPIRED_TOKEN
SENDER_PROFILE_NOT_VERIFIED
~~~

Not every reason leads to the DLQ: suppressed recipient may become CANCELLED, expired token becomes EXPIRED, and a bad template model needs review. The key rule is **do not call SMTP to discover a deterministic failure that could have been checked beforehand**.

### Do Not Re-Render Arbitrary Business Data on Every Retry

For example, an invoice was finalized with a total of 250,000 VND. If the worker retries the next day and fetches the **latest order total**, the email might show a newer price. Pin the model snapshot or rendered content per policy, and keep the same template revision across a logical notification.

## 19. Exponential Backoff and Jitter

A worker should not retry immediately after every failure, especially when the provider is throttling. Backoff can be calculated as:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where:

- \(d_0\) is the initial delay.
- \(d_{\max}\) is the maximum delay.
- \(n\) is the number of failed attempts so far.

**Jitter** spreads out retry timestamps across jobs so they do not all wake up at once and cause a spike.

| Attempt just failed | Base delay (d0 = 10s) | 50–100% jitter range |
| --- | --- | --- |
| 1 | 10 seconds | 5–10 seconds |
| 2 | 20 seconds | 10–20 seconds |
| 3 | 40 seconds | 20–40 seconds |
| 4 | 80 seconds | 40–80 seconds |
| 5 | 160 seconds | 80–160 seconds |

These intervals only explain the algorithm; OTPs and short-lived emails need their own deadline policy and do not have to follow this schedule.

### Why Not Retry All at Once?

Suppose the provider has a 2-minute outage and 100,000 jobs use:

~~~text
Fixed retry every 30 seconds:
  100.000 jobs wake at roughly same time
  -> enormous burst
  -> more throttling and backlog
~~~

Jitter + distributed rate limiting reduces synchronization between workers, but **does not eliminate a quota bottleneck** if average load still exceeds provider capacity.

## 20. A Unit-Testable Java RetryPolicy

Separate retry decisions into a class that knows nothing about SMTP or the database:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.function.DoubleSupplier;

public record RetryDecision(
        DeliveryState nextState,
        Instant nextAttemptAt,
        String reasonCode
) {
}

public final class RetryPolicy {

    private final Duration initialDelay;
    private final Duration maxDelay;
    private final DoubleSupplier randomFraction;

    public RetryPolicy(
            Duration initialDelay,
            Duration maxDelay,
            DoubleSupplier randomFraction
    ) {
        if (initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException("Invalid retry delays");
        }
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
        this.randomFraction = randomFraction;
    }

    public RetryDecision afterRetryableFailure(
            int completedAttempts,
            int maxAttempts,
            Instant now,
            Instant expiresAt
    ) {
        if (completedAttempts >= maxAttempts) {
            return new RetryDecision(
                    DeliveryState.DEAD_LETTER,
                    null,
                    "ATTEMPTS_EXHAUSTED"
            );
        }

        long delay = initialDelay.toMillis();
        long cap = maxDelay.toMillis();

        for (int i = 1; i < completedAttempts; i++) {
            // Safe multiply by 2 when near the cap.
            delay = delay >= cap / 2
                    ? cap
                    : Math.min(cap, delay * 2);
        }

        double fraction = Math.max(
                0.0, Math.min(1.0, randomFraction.getAsDouble())
        );
        long jittered = Math.max(
                1L, (long) (delay * (0.5 + fraction * 0.5))
        );
        Instant nextAt = now.plusMillis(jittered);

        if (expiresAt != null && !nextAt.isBefore(expiresAt)) {
            return new RetryDecision(
                    DeliveryState.EXPIRED,
                    null,
                    "RETRY_WOULD_EXCEED_DEADLINE"
            );
        }

        return new RetryDecision(
                DeliveryState.RETRY_WAIT,
                nextAt,
                "TRANSIENT_NOT_ACCEPTED"
        );
    }
}
~~~

### How to Initialize in Spring

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryPolicyConfig {

    @Bean
    RetryPolicy retryPolicy(MailWorkerProperties p) {
        return new RetryPolicy(
                Duration.ofSeconds(p.baseRetrySeconds()),
                Duration.ofSeconds(p.maxRetrySeconds()),
                () -> ThreadLocalRandom.current().nextDouble()
        );
    }
}
~~~

For unit tests, pass **() -> 0.0** or **() -> 1.0** for deterministic delays. Validate base/max in configuration and avoid excessively large Duration values that could overflow when converted to milliseconds.

### Maximum Number of Attempts

If **max_attempts=5**:

~~~text
Attempt 1: fail -> RETRY_WAIT
Attempt 2: fail -> RETRY_WAIT
Attempt 3: fail -> RETRY_WAIT
Attempt 4: fail -> RETRY_WAIT
Attempt 5: fail -> DEAD_LETTER
~~~

If a failure occurs before calling SMTP (over quota, missing template), do not automatically increment transport attempt count. If the outcome is UNKNOWN, the job does not automatically transition to RETRY_WAIT, so it does not loop using this formula.

## 21. Respecting Retry Timing from the Provider

Some ESP HTTP APIs return **429 Too Many Requests** and may include **Retry-After**. SMTP uses its own reply codes, such as 4xx for temporary failures during certain phases; do not treat SMTP 4xx as identical to HTTP 429.

### Rule for Combining Backoff and Provider Feedback

~~~text
local backoff -> 10 seconds
provider says retry after -> 60 seconds

next_attempt_at = max(local backoff, provider retry time)
~~~

However, if the notification expires before 60 seconds, you must decide **EXPIRED** or another business policy rather than continuing to send an expired OTP.

### Provider Temporary Replies Are Not Always Safe to Retry

You must know the SMTP phase and how many recipients the server accepted. When sending to multiple recipients, **partial recipient acceptance** can happen; unconditionally retrying the whole message can send duplicates to some recipients. The demo project should send **one recipient per logical notification** to reduce complexity.

### Do Not Speed Up by Ignoring Throttling

If the provider limits you to 10 recipients/s, configuring 100 threads will not help; you need pacing and a global limiter. A retry storm adds extra cost and may cause the provider to extend its throttling window.

## 22. Decision Rules After SubmissionResult

The worker maps the outcome to a state:

| SubmissionResult | Additional Condition | Next State |
| --- | --- | --- |
| **ACCEPTED** | Valid accepted response | ACCEPTED |
| **RETRYABLE_NOT_ACCEPTED** | Attempts remaining, within deadline | RETRY_WAIT |
| **RETRYABLE_NOT_ACCEPTED** | Reached max_attempts | DEAD_LETTER |
| **RETRYABLE_NOT_ACCEPTED** | Retry would exceed deadline | EXPIRED |
| **PERMANENT_NOT_ACCEPTED** | Data/recipient cannot be auto-fixed | DEAD_LETTER or CANCELLED per policy |
| **UNKNOWN** | No proof of acceptance/rejection | UNKNOWN |
| **No permit granted** | beginAttempt not called yet | RETRY_WAIT without incrementing attempts |

### Retry Is Not a Catch-All

Avoid doing this:

~~~java
try {
    sender.send(mime);
} catch (Exception e) {
    queue.enqueueAgain(job); // may send duplicates!
}
~~~

### Error Classification Should Be an Explicit Policy

Safe error codes and descriptions:

~~~text
SMTP_CONNECT_REFUSED_PRE_DATA
SMTP_TEMPORARY_REJECTION
SMTP_PERMANENT_RECIPIENT_REJECTION
SMTP_AUTH_CONFIG_ERROR
INVALID_TEMPLATE_MODEL
INVALID_RECIPIENT
SMTP_OUTCOME_AMBIGUOUS
WORKER_LEASE_EXPIRED
MAX_ATTEMPTS_EXCEEDED
EXPIRED_NOTIFICATION
~~~

Do not store raw exception stack traces containing recipients or SMTP credentials in **last_error_summary**. Store detailed logs in an access-controlled location with retention; database state only needs a reason code sufficient for decisions.

## 23. Creating AttemptResolution for Consistent Finalization

~~~java
import java.time.Instant;

public record AttemptResolution(
        DeliveryState targetState,
        Instant nextAttemptAt,
        String providerMessageId,
        String errorCode,
        String safeSummary,
        String deadLetterReason
) {
    public static AttemptResolution accepted(String providerId) {
        return new AttemptResolution(
                DeliveryState.ACCEPTED,
                null,
                providerId,
                null,
                null,
                null
        );
    }

    public static AttemptResolution unknown(String code) {
        return new AttemptResolution(
                DeliveryState.UNKNOWN,
                null,
                null,
                code,
                "Submission requires reconciliation",
                null
        );
    }

    public static AttemptResolution deadLetter(String code) {
        return new AttemptResolution(
                DeliveryState.DEAD_LETTER,
                null,
                null,
                code,
                "Manual review required",
                code
        );
    }
}
~~~

Mapping service:

~~~java
public AttemptResolution resolve(
        SubmissionResult submission,
        ClaimedMailJob job,
        int completedAttempts,
        java.time.Instant now,
        RetryPolicy policy
) {
    return switch (submission.kind()) {
        case ACCEPTED -> AttemptResolution.accepted(
                submission.providerMessageId()
        );
        case UNKNOWN -> AttemptResolution.unknown(
                submission.reasonCode()
        );
        case PERMANENT_NOT_ACCEPTED ->
                AttemptResolution.deadLetter(
                        submission.reasonCode()
                );
        case RETRYABLE_NOT_ACCEPTED -> {
            RetryDecision d = policy.afterRetryableFailure(
                    completedAttempts,
                    job.maxAttempts(),
                    now,
                    job.expiresAt()
            );

            yield new AttemptResolution(
                    d.nextState(),
                    d.nextAttemptAt(),
                    null,
                    d.reasonCode(),
                    "Retry policy applied",
                    d.nextState() == DeliveryState.DEAD_LETTER
                            ? d.reasonCode()
                            : null
            );
        }
    };
}
~~~

The **resolve(...)** method illustrates an application service function; it is not a Spring API. **completedAttempts** must come from **beginAttempt** after the increment, not from the old count in the claim snapshot, or limits will drift.

### When the Result Mapping Is EXPIRED

If the retry time is past the deadline, transition to EXPIRED and record a clear reason. An expired OTP email should not be pushed into the DLQ just so an operator can click replay on an old token; the user should have a flow to generate a new token.

## 24. DeliveryWorker: Connecting Claim, Quota, Transport, and State

To keep boundaries clear, the worker needs these groups of dependencies:

- **MailJobStore**: claim, beginAttempt, release, and finish with token.
- **PreflightValidator**: checks content, recipient, purpose, expiry.
- **MailPermitGate**: acquires an attempt permit according to rate/quota.
- **MailTransport**: submits to SMTP.
- **RetryPolicy / resolver**: decides the next state from the outcome.

Additional interfaces:

~~~java
import java.time.Instant;

public enum PreflightOutcome {
    ELIGIBLE,
    PERMANENT_INVALID,
    CANCELLED_BY_POLICY,
    EXPIRED
}

public record PreflightDecision(
        PreflightOutcome outcome,
        String reasonCode
) {
}

public interface PreflightValidator {
    PreflightDecision check(
            ClaimedMailJob job,
            Instant now
    );
}

public record PermitResult(
        boolean allowed,
        Instant nextEligibleAt,
        String reason
) {
}

public interface MailPermitGate {
    PermitResult tryAcquire(ClaimedMailJob job);
}
~~~

### The Worker Does Not Retry in a Sleep Loop

The worker should **process one job through to persisting its outcome state**, then return. If a retry is needed, next_attempt_at determines when the job next appears in the claim query.

### Example Service

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public final class DeliveryWorker {

    private final MailJobStore jobs;
    private final MailPermitGate permits;
    private final PreflightValidator preflight;
    private final MailTransport transport;
    private final RetryPolicy retryPolicy;
    private final Clock clock;

    public DeliveryWorker(
            MailJobStore jobs,
            MailPermitGate permits,
            PreflightValidator preflight,
            MailTransport transport,
            RetryPolicy retryPolicy,
            Clock clock
    ) {
        this.jobs = jobs;
        this.permits = permits;
        this.preflight = preflight;
        this.transport = transport;
        this.retryPolicy = retryPolicy;
        this.clock = clock;
    }

    public boolean processOne(
            String workerId,
            Duration lease
    ) {
        Optional<ClaimedMailJob> selected =
                jobs.claimNext(
                        workerId,
                        clock.instant(),
                        lease
                );

        if (selected.isEmpty()) {
            return false;
        }

        ClaimedMailJob job = selected.get();
        Instant now = clock.instant();

        PreflightDecision check = preflight.check(job, now);
        if (check.outcome() != PreflightOutcome.ELIGIBLE) {
            jobs.finishWithoutAttempt(
                    job,
                    mapPreflight(check),
                    now
            );
            return true;
        }

        PermitResult permit = permits.tryAcquire(job);
        if (!permit.allowed()) {
            Instant next = permit.nextEligibleAt();
            if (next == null) {
                next = now.plusSeconds(30);
            }
            jobs.releaseWithoutAttempt(
                    job, next, permit.reason()
            );
            return true;
        }

        UUID attemptId = jobs.beginAttempt(
                job, "primary-smtp", now
        );
        int completedAttempts = job.attemptCount() + 1;

        SubmissionResult submitted;
        try {
            submitted = transport.submit(job);
        } catch (RuntimeException e) {
            // Cannot know whether side effects occurred
            // if transport unexpectedly throws an exception.
            submitted = SubmissionResult.unknown(
                    "TRANSPORT_UNEXPECTED_FAILURE"
            );
        }

        AttemptResolution resolution = resolveOutcome(
                submitted,
                job,
                completedAttempts,
                clock.instant()
        );

        jobs.finishAttempt(
                job,
                attemptId,
                resolution,
                clock.instant()
        );

        return true;
    }

    private AttemptResolution mapPreflight(
            PreflightDecision check
    ) {
        return switch (check.outcome()) {
            case PERMANENT_INVALID ->
                    AttemptResolution.deadLetter(
                            check.reasonCode()
                    );
            case CANCELLED_BY_POLICY ->
                    new AttemptResolution(
                            DeliveryState.CANCELLED,
                            null, null,
                            check.reasonCode(),
                            "Notification cancelled by policy",
                            null
                    );
            case EXPIRED ->
                    new AttemptResolution(
                            DeliveryState.EXPIRED,
                            null, null,
                            check.reasonCode(),
                            "Notification expired",
                            null
                    );
            case ELIGIBLE -> throw new IllegalStateException(
                    "Eligible preflight cannot be finalized"
            );
        };
    }

    private AttemptResolution resolveOutcome(
            SubmissionResult result,
            ClaimedMailJob job,
            int completedAttempts,
            Instant now
    ) {
        return switch (result.kind()) {
            case ACCEPTED ->
                    AttemptResolution.accepted(
                            result.providerMessageId()
                    );
            case UNKNOWN ->
                    AttemptResolution.unknown(
                            result.reasonCode()
                    );
            case PERMANENT_NOT_ACCEPTED ->
                    AttemptResolution.deadLetter(
                            result.reasonCode()
                    );
            case RETRYABLE_NOT_ACCEPTED -> {
                RetryDecision next =
                        retryPolicy.afterRetryableFailure(
                                completedAttempts,
                                job.maxAttempts(),
                                now,
                                job.expiresAt()
                        );
                yield new AttemptResolution(
                        next.nextState(),
                        next.nextAttemptAt(),
                        null,
                        next.reasonCode(),
                        "Transient send failure",
                        next.nextState() == DeliveryState.DEAD_LETTER
                                ? next.reasonCode()
                                : null
                );
            }
        };
    }
}
~~~

**Code scope note:** **MailJobStore.finishWithoutAttempt(...)** is additionally used for preflight and must be declared/implemented in the repository interface from section 15 (adding a method taking job, resolution, now). **beginAttempt** in this example returns UUID attemptId, while the new attempt count is computed as job.attemptCount()+1 assuming **at most one beginAttempt per claim** and the atomic increment described earlier. In production, return **AttemptStarted(attemptId, attemptNumber)** directly from the database to avoid relying on an in-memory snapshot.

### Worker Must Handle Database Write Failures

If **finishAttempt** fails to write the outcome after SMTP accepted, never re-run transport inside the same method just because the DB errored. Recovery will find the expired IN_FLIGHT/STARTED record and treat it as UNKNOWN. Database failures should retry **persisting the result** while the lease is still valid, with bounds/telemetry, without generating a new email.

### Permit Gate Must Be Distributed Quota Across Replicas

A per-JVM **Semaphore** only limits local concurrency, not the aggregate rate of 10 pods sharing one SMTP account. Use a distributed limiter or quota allocator when provider quota is shared.

### Worker Must Release Job After Quota Denial

In the snippet above, **releaseWithoutAttempt** records RETRY_WAIT + nextAt and clears the lease. It does not increment attempts; this prevents emails from dying just from waiting for the next quota window.

## 25. Completing the Full MailJobStore Contract

In a real project, the interface should group related operations together:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface MailJobStore {

    Optional<ClaimedMailJob> claimNext(
            String workerId,
            Instant now,
            Duration lease
    );

    UUID beginAttempt(
            ClaimedMailJob job,
            String provider,
            Instant now
    );

    void releaseWithoutAttempt(
            ClaimedMailJob job,
            Instant nextAt,
            String reason
    );

    void finishWithoutAttempt(
            ClaimedMailJob job,
            AttemptResolution resolution,
            Instant now
    );

    void finishAttempt(
            ClaimedMailJob job,
            UUID attemptId,
            AttemptResolution resolution,
            Instant now
    );

    int quarantineExpiredLeases(Instant now);

    int expireUnsentJobs(Instant now);
}
~~~

This interface is a more complete contract than the abbreviated version in section 15. When copying code into a Java project, keep **only one MailJobStore definition**; the earlier excerpts were shown progressively to explain each step, not as multiple duplicate interface files.

### General Implementation Rules

Every method must verify **job.id + lease_token + state** in its UPDATE statement. If affected rows is zero, do not silently treat it as success; raise a **STALE_LEASE**/conflict error for investigation. Never accept recipient, body, state, or lease token from user API input when performing state transitions.

### Begin Attempt and Finish Must Be Transactional

Any method updating mail_outbox and mail_attempt must commit/roll back together. If updating outbox succeeds but inserting/updating attempt fails, the transaction must roll back.

## 26. Scheduler Limiting Work per Poll

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailWorkerScheduler {

    private final DeliveryWorker worker;
    private final MailWorkerProperties properties;

    public MailWorkerScheduler(
            DeliveryWorker worker,
            MailWorkerProperties properties
    ) {
        this.worker = worker;
        this.properties = properties;
    }

    @Scheduled(fixedDelay = 1000)
    public void tick() {
        if (!properties.enabled()) {
            return;
        }

        int limit = Math.max(
                1, properties.maxJobsPerPoll()
        );
        String workerId = "mail-node-1";

        for (int i = 0; i < limit; i++) {
            boolean found = worker.processOne(
                    workerId, properties.lease()
            );
            if (!found) {
                return;
            }
        }
    }
}
~~~

**workerId** in this example is a placeholder. Production needs a unique ID per instance/process/replica rather than the same hard-coded string across nodes. **fixedDelay = 1000** is only an example; to pull it from application properties, use fixedDelayString with a properly configured property expression.

### Do Not Run Multiple SMTP Attempts in One Scheduler Transaction

Do not annotate tick() with **@Transactional**. Each claim, begin, and finalize uses a short DB transaction; SMTP I/O stays outside. If the sender is slow, a scheduler run may take longer, but it must never hold a DB lock for the entire tick.

### Parallelism

The scheduler above processes at most N jobs **sequentially** per tick. When you want parallelism, add a bounded executor and limit concurrent attempts; however, only claim jobs when execution capacity is available, rather than claiming 500 jobs and leaving them waiting until their leases expire.

### Rate and Concurrency Are Two Separate Limits

A limit of 8 worker threads does not mean at most 8 emails/s, and a token bucket of 10 recipients/s does not bound open I/O connections. Providers may limit both connections and rate; you need to coordinate both mechanisms.

## 27. Why Leases and Heartbeats Are Needed

A worker can crash or be killed mid-SMTP I/O:

~~~text
10:00:00 Worker A claims job, lease_until=10:00:45
10:00:02 A records attempt STARTED
10:00:03 A starts SMTP DATA
10:00:10 JVM/process crashes
10:00:45 Lease expires
~~~

If the job remains in IN_FLIGHT forever, the system loses tracking visibility. On the other hand, moving it straight back to PENDING and resending risks duplicates if the server accepted before the crash.

### Safe Handling

**Lease expired → UNKNOWN**. A reconciliation service or operator inspects provider logs and the attempt record before deciding whether to allow a retry.

### Heartbeat/Lease Extension

For long operations (large attachments, high provider timeouts), you can extend the lease:

~~~sql
UPDATE mail_outbox
SET lease_until = :newLeaseUntil,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'IN_FLIGHT'
  AND lease_token = :leaseToken
  AND lease_until > :now;
~~~

Heartbeats do not turn SMTP into an exactly-once transaction. If a worker dies after the provider accepted, UNKNOWN can still occur. But heartbeats prevent false lease timeouts while the worker is alive and progressing a valid attempt.

### Do Not Naively Resurrect an Expired Lease

If a lease already expired and recovery moved the job to UNKNOWN, the old worker must not re-extend the lease simply because it is still running. The condition **state='IN_FLIGHT' AND matching lease_token AND lease_until>now** blocks this behavior.

## 28. Recovering Overdue IN_FLIGHT Jobs

A scheduled recovery job checks:

~~~sql
UPDATE mail_outbox
SET state = 'UNKNOWN',
    last_error_code = 'WORKER_LEASE_EXPIRED',
    last_error_summary =
        'Attempt outcome unknown after lease expiry',
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE state = 'IN_FLIGHT'
  AND lease_until <= :now
RETURNING id, lease_token;
~~~

In this example, **lease_token is retained on the UNKNOWN row** to correlate with attempt history; the old worker cannot finalize because its condition requires state IN_FLIGHT. During replay/reconcile, the transition service can clear or replace the token inside a new audited transaction.

### Record the Attempt Outcome Alongside Recovery

After identifying jobs transitioned to UNKNOWN, update any attempts still in STARTED with matching notificationId/leaseToken to:

~~~text
outcome = UNKNOWN_LEASE_EXPIRED
finished_at = recovery time
error_code = WORKER_LEASE_EXPIRED
~~~

Preferably run the outbox and attempt updates in **the same transaction**, based on the returned rows or an appropriate CTE. Never update only outbox and leave STARTED attempts lingering forever without a reconciliation runbook.

### Recovery Must Handle Crashes Before beginAttempt

A job can be IN_FLIGHT without an attempt record if the worker died before beginAttempt. In that case, it **may** be possible to prove the app never submitted if the execution path guarantees no send path exists before beginAttempt. However, for simplicity and safety, the demo moves expired IN_FLIGHT to UNKNOWN and marks **NO_ATTEMPT_RECORDED**, letting an operator or reconciliation service decide whether to move it back to PENDING.

### Can Two Recovery Schedulers Run Concurrently?

Yes, if the UPDATE checks state IN_FLIGHT and transactions are controlled. A job is transitioned by only one transaction; later callbacks must use optimistic locking/fencing so they cannot double-transition.

## 29. Housekeeping: Expired Jobs and Retry Budget

Besides handling expired leases, you must scan jobs past their business deadline:

~~~sql
UPDATE mail_outbox
SET state = 'EXPIRED',
    last_error_code = 'NOTIFICATION_EXPIRED',
    updated_at = :now
WHERE state IN ('PENDING', 'RETRY_WAIT')
  AND expires_at IS NOT NULL
  AND expires_at <= :now;
~~~

### Why Not Mark IN_FLIGHT as EXPIRED Immediately?

An IN_FLIGHT job may have sent before expiry and simply be waiting for the SMTP response. Forcing it to EXPIRED prevents the worker from recording acceptance and leaves the state ambiguous. For jobs that already started an attempt, wait for the outcome or move to UNKNOWN after lease timeout; never use the deadline to infer the server did not accept.

### Jobs at max_attempts Still in RETRY_WAIT

Due to a bug, crash, or migration, a RETRY_WAIT row could exist with attempt_count >= max_attempts. Housekeeping should move it to DEAD_LETTER with reason **ATTEMPTS_EXHAUSTED**, rather than leaving it behind where the claim query will always skip it.

### Housekeeping Does Not Delete Data Automatically

EXPIRED and DEAD_LETTER are states that require auditing. Archiving/purging history belongs to a retention policy, not the default behavior of the retry worker.

## 30. What Is Dead Letter in This Project?

In broker-based systems, a **dead-letter queue (DLQ)** is usually a queue/topic holding messages that could not be processed under policy. In this PostgreSQL-based project, we take a simpler approach: **mail_outbox.state = DEAD_LETTER** along with reason, timestamps, attempt history, and audit records.

Both models share the same goals:

- Retain failed notifications rather than silently dropping them.
- Classify failure reasons.
- Stop retrying deterministic failures infinitely.
- Enable review, data/config fixes, and controlled replay decisions.
- Preserve attempt history and provider evidence.

### Cases That Go to Dead Letter

| Reason | Example | Should it be replayed automatically? |
| --- | --- | --- |
| **MAX_ATTEMPTS_EXHAUSTED** | N proven transient failures occurred | No, requires review/adjustment |
| **INVALID_RECIPIENT** | Email address deterministically invalid | No, unless corrected to a valid recipient |
| **TEMPLATE_MODEL_INVALID** | Missing required variable | No, fix producer/template |
| **SENDER_PROFILE_INVALID** | From address is not verified | No, fix configuration |
| **ATTACHMENT_POLICY_VIOLATION** | File too large or blocked | No, adjust content per policy |
| **UNKNOWN_UNRESOLVED** | Ambiguous attempt could not be reconciled | Never automatically; duplicate risk |
| **TENANT_POLICY_REJECTION** | Tenant not permitted to send this email type | No, requires permission/approval |

### When Should a Job Not Go to Dead Letter?

**NO_PERMIT due to exhausted quota** normally waits for a new schedule/quota window, rather than burning through max_attempts and going straight to DLQ. **Expired OTPs** fit EXPIRED better, since replaying a dead OTP is useless. **Suppression/opt-out** is normally CANCELLED/SUPPRESSED, not a technical failure to fix.

### DLQ Is Not a Deletion Mechanism

A DEAD_LETTER record may still hold recipient addresses, bodies, links, or sensitive documents. You must enforce RBAC, encryption, retention, and redaction tools. Do not expose raw dead-letter payloads on a public dashboard.

## 31. Dead-Letter Records and Metadata for Investigation

For an operator to understand an issue, a record needs sufficient context:

~~~text
notification_id
tenant_id
business_key / purpose
recipient_ref (redacted in UI)
state = DEAD_LETTER
dead_letter_reason
attempt_count / max_attempts
first_created_at
last_attempt_at
last_error_code
last_provider
provider_message_id, if any
template_revision, if applicable
safe payload hash / content version
~~~

More detail lives in **mail_attempt**. For example:

| Attempt | Time | Provider | Outcome | Code |
| --- | --- | --- | --- | --- |
| 1 | 10:00 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 2 | 10:01 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 3 | 10:03 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 4 | 10:07 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |
| 5 | 10:15 | SMTP-A | RETRYABLE_NOT_ACCEPTED | SMTP_TEMP_REJECT |

After attempt 5, **DEAD_LETTER / ATTEMPTS_EXHAUSTED**. Reading this history shows the issue is throttling or continuous provider rejection, very different from a bad recipient address.

### Do Not Stuff Full Stack Traces into the DB

Stack traces and raw SMTP diagnostics may contain addresses, internal hostnames, credentials, or message content. Store **errorCode + sanitized summary + opaque trace reference**; when detailed logs are needed, use protected storage with a TTL.

## 32. Querying Dead Letters for Handling

~~~sql
SELECT
    id,
    tenant_id,
    business_key,
    dead_letter_reason,
    attempt_count,
    max_attempts,
    last_error_code,
    updated_at
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
ORDER BY updated_at ASC
LIMIT 100;
~~~

This query is for a paginated operator page. **Do not return plain_body, html_body, or full recipient_address** to every staff member by default.

### Aggregating Failure Groups

~~~sql
SELECT
    dead_letter_reason,
    COUNT(*) AS jobs
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
GROUP BY dead_letter_reason
ORDER BY jobs DESC;
~~~

If many jobs suddenly land in DEAD_LETTER with **SMTP_AUTH_CONFIGURATION**, it is likely a shared account incident; do not replay individual jobs while credentials remain wrong.

### Use Dashboards to Track DLQ Age

A dead-letter backlog sitting for three weeks is very different from a single newly failed job. Add **oldest dead-letter age** and group by purpose/provider/tenant in your metrics, while avoiding high cardinality from recipient IDs.

## 33. Replay Policy: Not Just Resetting to PENDING

An uncontrolled “Replay all dead letters” button can send duplicates, violate consent, or trigger a retry storm.

### Preconditions Before Replay

1. The actor is authenticated/authorized for the tenant and purpose.
2. The **reason** is understood and the root cause is fixed.
3. Verify the job is not **ACCEPTED** and has no unreconciled UNKNOWN attempt.
4. Verify the recipient is still eligible under consent/suppression.
5. Verify the deadline and tokens/links are still valid.
6. Ensure content/template model is accurate and contains no revoked URLs.
7. Decide whether to replay the same payload or create a new notification.
8. Choose batch size, rate/quota budget, and replay schedule.
9. Record an audit entry with operator, reason, and previous attempts.

### Replaying with the Same Notification ID

For a DEAD_LETTER job caused by **proven pre-acceptance failures**, if the payload is unchanged, you can:

- Keep **notificationId** and **businessKey**.
- Keep the entire **mail_attempt** history.
- **Do not reset attempt_count to 0**.
- Increase **max_attempts** in a controlled way, e.g., from 5 to 7.
- Move state back to PENDING with a scheduled next_attempt_at.
- Record an audit entry for the additional attempt budget granted.

Reason: the table constraint **mail_attempt UNIQUE(notification_id, attempt_number)** would conflict if you reset to 0; keeping attempt numbers monotonic keeps history consistent.

### Replay with Changed Payload or Recipient

If you must fix an address, update invoice content, or issue a new link/token, this may be a **new notification**. You can add a **replay_of_notification_id**/correlation column referencing the old one and create a new ID + meaningful business key. Never mutate an already accepted notification and overwrite its content as if it had always been that way.

### Illustrative Replay SQL

~~~sql
UPDATE mail_outbox
SET state = 'PENDING',
    max_attempts = :newMaxAttempts,
    next_attempt_at = :scheduledAt,
    dead_letter_reason = NULL,
    last_error_code = NULL,
    last_error_summary = NULL,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :notificationId
  AND state = 'DEAD_LETTER'
  AND attempt_count < :newMaxAttempts
  AND (expires_at IS NULL OR expires_at > :now);
~~~

**This SQL illustrates an orchestrated transaction**, not an open API for users to run directly. Execute it only after the job is reviewed, the reason is valid, template/recipient policy is verified, and the audit record is inserted **in the same transaction**. Check affected rows = 1 to prevent double replay from a double-click.

### Why Not Replay UNKNOWN Using This SQL?

The starting condition is **state='DEAD_LETTER'**. If an operator manually moves an UNKNOWN job to DEAD_LETTER just to “clean up the screen”, replay must still inspect UNKNOWN history. Never allow status relabeling to bypass duplicate-prevention policy.

## 34. Auditing Replay or Discard

An administrative transition:

~~~text
action: REPLAY
notificationId: ...
oldState: DEAD_LETTER
newState: PENDING
oldMaxAttempts: 5
newMaxAttempts: 7
operator: ops-user-17
reason: SMTP provider recovered and prior errors proven pre-acceptance
time: ...
~~~

If the operator decides not to send anymore:

~~~text
action: CANCEL
oldState: DEAD_LETTER
newState: CANCELLED
reason: recipient requested opt-out
~~~

### Audit in the Same Transaction

When changing state:

~~~sql
INSERT INTO mail_dead_letter_audit (
    id, notification_id,
    action, from_state, to_state,
    operator_id, reason
)
VALUES (
    :auditId, :notificationId,
    :action, :fromState, :toState,
    :operator, :reason
);
~~~

If the state update succeeds but the audit insert fails, **roll back the entire transaction**. Never allow a privileged operation to persist without leaving an audit trail.

### Bulk Replay Needs Throttling

With 10,000 dead letters, do not run 10,000 UPDATE→PENDING statements and immediately open 10,000 SMTP connections. Spread replays across time windows, use a shared scheduler/limiter, and track batch progress with a pause/stop mechanism.

### Idempotency of Replay Operations

A replay request can be retried by the client. Use an operator action ID/request idempotency key or state compare-and-set. If the same action is received twice, execute only one transition and never grant extra retry budget twice.

## 35. UNKNOWN: The Hardest Part of a Retry Worker

**UNKNOWN** differs from **RETRY_WAIT**: the server may already have accepted the email.

~~~text
SMTP session
    |
    +-- MAIL FROM accepted
    +-- RCPT TO accepted
    +-- DATA accepted, body transferred
    +-- server commits message
    '-- response lost before client receives it
                 |
                 v
              UNKNOWN
~~~

If the worker retries as if nothing were sent, the recipient may receive two identical copies. Keeping the same **Message-ID** does not solve this; SMTP does not guarantee deduplication on that header.

### Reconciliation Workflow

~~~text
UNKNOWN job
    |
    v
Check provider request/message ID if available
    |
    +-- Confirmed accepted ------> ACCEPTED
    |
    +-- Proven not accepted -----> Controlled retry
    |
    '-- Cannot determine --------> Manual risk decision
                                     |
                        +------------+-----------+
                        |                        |
                        v                        v
                     Hold / close          Explicit resend
                     with audit            accepting dup risk
~~~

### Limited Information with Plain SMTP

An SMTP sender may lack a provider query API to ask whether the server accepted a message. Without evidence, you must decide based on business importance and recipient impact. For example, an internal report might accept controlled duplicate risk, whereas invoice or login-code emails require stricter policy.

### Message-ID Is Only for Correlation

Recording Message-ID on attempts can be helpful when searching mail logs, but do not treat it as a guaranteed idempotency token. When a provider supports its own idempotency API, follow that provider's exact semantics, TTL, and scope.

### UNKNOWN Is Not DEAD_LETTER by Default

You can keep UNKNOWN for investigation; if SLAs/procedures require closing unverifiable cases, transition them to DEAD_LETTER with reason **UNKNOWN_UNRESOLVED** without auto-replaying. History must preserve the flag that the job was once UNKNOWN.

## 36. Repository Transactions for beginAttempt and finishAttempt

The Java snippet below implements both critical steps with **NamedParameterJdbcTemplate**, based on the schema in section 7. The methods carry **@Transactional** and are invoked by the worker via a **Spring bean**, not self-invocation.

~~~java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcMailAttemptWriter {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcMailAttemptWriter(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public StartedAttempt beginAttempt(
            ClaimedMailJob job,
            String provider,
            Instant now
    ) {
        UUID attemptId = UUID.randomUUID();
        String sql = """
            WITH bumped AS (
                UPDATE mail_outbox
                SET attempt_count = attempt_count + 1,
                    updated_at = :now
                WHERE id = :id
                  AND state = 'IN_FLIGHT'
                  AND lease_token = :token
                  AND lease_until > :now
                  AND attempt_count < max_attempts
                RETURNING attempt_count
            )
            INSERT INTO mail_attempt (
                id, notification_id, attempt_number,
                lease_token, provider, started_at, outcome
            )
            SELECT
                :attemptId, :id, bumped.attempt_count,
                :token, :provider, :now, 'STARTED'
            FROM bumped
            RETURNING attempt_number
            """;

        var params = new MapSqlParameterSource()
                .addValue("id", job.id())
                .addValue("token", job.leaseToken())
                .addValue("now", Timestamp.from(now))
                .addValue("provider", provider)
                .addValue("attemptId", attemptId);

        var rows = jdbc.query(
                sql,
                params,
                (rs, rowNum) -> rs.getInt("attempt_number")
        );
        if (rows.size() != 1) {
            throw new IllegalStateException(
                    "Lease lost or retry budget exhausted"
            );
        }

        return new StartedAttempt(
                attemptId, rows.get(0)
        );
    }

    @Transactional
    public void finishAttempt(
            ClaimedMailJob job,
            StartedAttempt attempt,
            AttemptResolution result,
            Instant now
    ) {
        String updateJob = """
            UPDATE mail_outbox
            SET state = :state,
                next_attempt_at = CASE
                    WHEN :state = 'RETRY_WAIT'
                    THEN CAST(:nextAt AS timestamptz)
                    ELSE next_attempt_at
                END,
                provider_message_id = :providerMessageId,
                last_error_code = :errorCode,
                last_error_summary = :summary,
                dead_letter_reason = :deadReason,
                accepted_at = CASE
                    WHEN :state = 'ACCEPTED'
                    THEN :now
                    ELSE accepted_at
                END,
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                updated_at = :now
            WHERE id = :id
              AND state = 'IN_FLIGHT'
              AND lease_token = :token
            """;

        var params = new MapSqlParameterSource()
                .addValue("state", result.targetState().name())
                .addValue("nextAt", result.nextAttemptAt() == null
                        ? null
                        : Timestamp.from(result.nextAttemptAt()))
                .addValue(
                        "providerMessageId",
                        result.providerMessageId()
                )
                .addValue("errorCode", result.errorCode())
                .addValue("summary", result.safeSummary())
                .addValue("deadReason", result.deadLetterReason())
                .addValue("now", Timestamp.from(now))
                .addValue("id", job.id())
                .addValue("token", job.leaseToken())
                .addValue("attemptId", attempt.attemptId());

        int changed = jdbc.update(updateJob, params);
        if (changed != 1) {
            throw new IllegalStateException(
                    "Stale lease: cannot finalize mail attempt"
            );
        }

        String updateHistory = """
            UPDATE mail_attempt
            SET outcome = :state,
                finished_at = :now,
                error_code = :errorCode,
                error_summary = :summary,
                provider_message_id = :providerMessageId
            WHERE id = :attemptId
              AND notification_id = :id
              AND lease_token = :token
              AND outcome = 'STARTED'
            """;

        changed = jdbc.update(updateHistory, params);
        if (changed != 1) {
            throw new IllegalStateException(
                    "Attempt history conflict"
            );
        }
    }
}

public record StartedAttempt(
        UUID attemptId,
        int attemptNumber
) {
}
~~~

### Why Return StartedAttempt Instead of Just UUID?

The worker needs the **actual attemptNumber after the transaction**. If code derives job.attemptCount()+1 from a stale snapshot in a complex design, attempt counts can drift after migration or recovery. Returning attemptNumber from PostgreSQL is more reliable.

### Wiring into the Worker

In a final implementation, **MailJobStore.beginAttempt(...)** can be upgraded to:

~~~java
StartedAttempt beginAttempt(
        ClaimedMailJob job,
        String provider,
        Instant now
);
~~~

and the worker uses:

~~~java
StartedAttempt started = jobs.beginAttempt(
        job, "primary-smtp", clock.instant()
);

SubmissionResult submission = transport.submit(job);

AttemptResolution resolution = resolveOutcome(
        submission,
        job,
        started.attemptNumber(),
        clock.instant()
);

jobs.finishAttempt(
        job,
        started,
        resolution,
        clock.instant()
);
~~~

Earlier excerpts of **MailJobStore** returned UUID to keep the introduction simple. This is an **upgraded variant** using the attempt number from the database; choose **one consistent contract** in your implementation rather than keeping two methods with the same name and different return types in Java.

### JDBC Failure When Finalizing After SMTP Accepted

If the DB is unavailable after the server accepted, **finishAttempt** fails. The worker must not call transport again in the catch block; it should retry **only persisting the outcome** while the lease is still valid, or let recovery transition the job to UNKNOWN for reconciliation. **Never conclude** that because the DB does not show ACCEPTED, the provider did not receive the email.

### Do Not Span Transactions Across SMTP

In the right sequence:

~~~text
Transaction A: claim -> COMMIT
Transaction B: beginAttempt -> COMMIT
No DB transaction: call SMTP
Transaction C: finishAttempt -> COMMIT
~~~

This is the main reason a system needs explicit states and a retry policy: you cannot commit SMTP atomically alongside a database in a simple JDBC transaction.

## 37. Releasing a Claim When Quota Disallows Sending

If a job is claimed but beginAttempt has not run yet, a limiter may say **WAIT**. Return the job to RETRY_WAIT without incrementing the attempt count:

~~~sql
UPDATE mail_outbox
SET state = 'RETRY_WAIT',
    next_attempt_at = :nextAt,
    last_error_code = :reasonCode,
    last_error_summary = 'Waiting for send permit',
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :id
  AND state = 'IN_FLIGHT'
  AND lease_token = :token;
~~~

**Do not insert a mail_attempt** because no real attempt happened. Operators can see reason_code = QUOTA_WAIT, which is not a technical SMTP failure.

### Permit Gate and max_attempts

~~~text
attempt_count=0, state=PENDING
  -> claim -> no permit
attempt_count=0, state=RETRY_WAIT
  -> claim next window -> permit granted
  -> beginAttempt -> attempt_count=1
~~~

Quota waiting never pushes a job to DEAD_LETTER when max_attempts=5.

### Avoiding Granting Permits Before Claiming

If you issue a global token before knowing whether a job claim succeeded, multiple workers can take permits and leave them unused, reducing throughput. If you claim first, release the claim quickly when no permit is available. A well-designed scheduler can use quota capacity to bound claim counts and maintain explicit permit reservation/release semantics.

## 38. Finalizing a Preflight Failure Without an Attempt

A job can be rejected **before SMTP** due to invalid content:

~~~sql
UPDATE mail_outbox
SET state = :targetState,
    dead_letter_reason = :deadReason,
    last_error_code = :code,
    last_error_summary = :safeSummary,
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = :now
WHERE id = :id
  AND state = 'IN_FLIGHT'
  AND lease_token = :token;
~~~

Do not create a **mail_attempt** for this failure. If you want to track all processing operations, you can create a separate **mail_processing_event** table to distinguish a **validation decision** from a **transport attempt**.

### Why Make This Distinction?

A system that logs every validation failure as an SMTP attempt distorts attempt/quota/cost metrics. When investigating 1,000 dead letters caused by a template bug, **mail_send_attempts** might be 0 while **mail_preflight_failures** is 1,000. This separation helps you decide to fix the template instead of raising SMTP quota.

## 39. Database State vs. Physical Dead-Letter Queues

In a larger system, you might move from a PostgreSQL outbox to a message broker:

~~~text
Outbox/CDC
    |
    v
Broker main topic/queue
    |
    v
Mail consumer
    |
    +-- Success -> ack
    +-- Transient -> delayed retry topic/queue
    '-- Permanent -> dead-letter topic/queue
                           |
                           v
                      Operator review
~~~

### Broker DLQs Do Not Automatically Contain Full History

A RabbitMQ DLX or Kafka DLQ typically holds the message and routing metadata, but does not by itself tell you whether SMTP accepted the email. You still need **notificationId, attempt history, submission outcome, and idempotency** in an application-level store.

### Retry Queues Are Not for Holding UNKNOWN for Auto-Resend

If an UNKNOWN attempt is published to a delayed retry topic as a transient error, the next consumer may send a duplicate. Isolate UNKNOWN separately and only leave that state after an evidence/risk decision.

### Do Not Ack Before Persisting a Durable Result

If a consumer receives a job, SMTP accepts, and the broker message is acked before the database records ACCEPTED, audit records can be wrong. If it acks too late, broker redelivery can cause duplicates. Because SMTP sits outside both broker and DB transactions, you still need a conservative flow with durable state and reconciliation; no simple ack operation solves exactly-once email.

## 40. Running the Practice Project with PostgreSQL and a Local SMTP Sink

To avoid sending emails to the Internet, you can run **PostgreSQL** alongside an SMTP test sink such as **Mailpit**. Example **docker-compose.yml**:

~~~yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: maildemo
      POSTGRES_USER: maildemo
      POSTGRES_PASSWORD: example-local-only
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U maildemo -d maildemo"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - maildemo-pg:/var/lib/postgresql/data

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "3025:1025"
      - "8025:8025"

volumes:
  maildemo-pg:
~~~

Run:

~~~bash
docker compose up -d
~~~

Mailpit listens for SMTP at **localhost:3025**, with the test web UI at **http://localhost:8025** according to the illustrative port mapping. These addresses are for local development; **never expose an open relay or public SMTP sink to the Internet**. Production should pin image versions/digests and manage database credentials/secrets per policy; never use the demo password in production.

### Practice Workflow

1. Start PostgreSQL and Mailpit.
2. Create a Spring Boot project with the dependencies from section 6.
3. Put the schema from section 7 into a migration.
4. Configure datasource/SMTP/scheduler.
5. Implement repository, worker, and transport following the contracts presented.
6. Insert a valid notification.
7. Observe state transitions PENDING → IN_FLIGHT → ACCEPTED.
8. Inspect the captured email in the Mailpit UI.
9. Stop Mailpit, test failure scenarios, and observe UNKNOWN/retry behavior per classifier.
10. Run concurrency, replay, and expired-lease tests before trusting the worker in production.

### Inserting a Simple Notification via SQL

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, business_key,
    recipient_address, sender_profile,
    subject, plain_body, html_body,
    state, next_attempt_at, max_attempts
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'demo-tenant',
    'LAB:WELCOME:customer-7',
    'customer@example.test',
    'demo-verified-profile',
    'Welcome',
    'Hello! This is a practice email.',
    '<p>Hello! <strong>This is a practice email.</strong></p>',
    'PENDING',
    CURRENT_TIMESTAMP,
    5
);
~~~

**Note:** **SenderProfileResolver** must map demo-verified-profile internally to a valid From address for the test sink. The example.test recipient is for testing only; Mailpit does not deliver mail to real recipients.

### Inspecting State

~~~sql
SELECT
    id, state, attempt_count, next_attempt_at,
    last_error_code, dead_letter_reason
FROM mail_outbox
WHERE business_key = 'LAB:WELCOME:customer-7';
~~~

With the SMTP sink running and a complete worker, state transitions to ACCEPTED. When the sink is stopped, the conservative SpringMailTransport adapter from section 17 moves the job to UNKNOWN rather than RETRY_WAIT, because the adapter has not proven the failure happened before DATA. To test the retryable branch, use **FakeMailTransport** with explicit outcomes.

## 41. Unit Testing RetryPolicy

Random jitter makes retry timing non-deterministic. That is why the constructor accepts a **DoubleSupplier**, enabling deterministic tests.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    private final Instant now =
            Instant.parse("2026-01-01T00:00:00Z");

    private final RetryPolicy policy = new RetryPolicy(
            Duration.ofSeconds(10),
            Duration.ofMinutes(10),
            () -> 1.0 // full calculated delay
    );

    @Test
    void firstRetryWaitsTenSeconds() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        1, 5, now, null
                );

        assertEquals(
                DeliveryState.RETRY_WAIT,
                decision.nextState()
        );
        assertEquals(
                now.plusSeconds(10),
                decision.nextAttemptAt()
        );
    }

    @Test
    void thirdAttemptUsesFortySecondBackoff() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        3, 5, now, null
                );

        assertEquals(
                now.plusSeconds(40),
                decision.nextAttemptAt()
        );
    }

    @Test
    void maxAttemptsTransitionsToDeadLetter() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        5, 5, now, null
                );

        assertEquals(
                DeliveryState.DEAD_LETTER,
                decision.nextState()
        );
        assertEquals(
                "ATTEMPTS_EXHAUSTED",
                decision.reasonCode()
        );
    }

    @Test
    void retryBeyondDeadlineBecomesExpired() {
        RetryDecision decision =
                policy.afterRetryableFailure(
                        2, 5,
                        now,
                        now.plusSeconds(15)
                );

        assertEquals(
                DeliveryState.EXPIRED,
                decision.nextState()
        );
    }
}
~~~

These tests evaluate only the timing/state policy. They do not prove SMTP actually sent or the database committed. **You can test minimum jitter** with supplier () -> 0.0 and assert the 50% delay bound.

## 42. FakeMailTransport for Testing Retries and Dead Letters

To simulate reliable outcomes without calling a real provider, build a fake that returns outcomes in order:

~~~java
import java.util.ArrayDeque;
import java.util.List;
import java.util.Queue;

public final class FakeMailTransport implements MailTransport {

    private final Queue<SubmissionResult> results;
    private int calls;

    public FakeMailTransport(
            List<SubmissionResult> results
    ) {
        this.results = new ArrayDeque<>(results);
    }

    @Override
    public SubmissionResult submit(ClaimedMailJob job) {
        calls++;
        SubmissionResult result = results.poll();
        if (result == null) {
            throw new IllegalStateException(
                    "No fake result configured"
            );
        }
        return result;
    }

    public int calls() {
        return calls;
    }
}
~~~

### Test Scenario: 2 Failures Then Accepted

~~~text
Fake outcomes:
  RETRYABLE_NOT_ACCEPTED
  RETRYABLE_NOT_ACCEPTED
  ACCEPTED

Expected DB history:
  attempt 1 -> RETRY_WAIT (future nextAttemptAt)
  attempt 2 -> RETRY_WAIT
  attempt 3 -> ACCEPTED

Assertions:
  same notification ID
  three unique attempt IDs
  attempt_count = 3
  no dead-letter row
  no fourth SMTP submission
~~~

### Test Scenario: Max Attempts

~~~text
Fake outcomes:
  5 × RETRYABLE_NOT_ACCEPTED

Expected:
  final state = DEAD_LETTER
  reason = ATTEMPTS_EXHAUSTED
  attempt_count = 5
  no more automatic claims
~~~

### Test Scenario: Invalid Payload

~~~text
Preflight returns PERMANENT_INVALID.

Expected:
  state = DEAD_LETTER
  attempt_count = 0
  fake transport calls = 0
~~~

### Test Scenario: No Quota

~~~text
Permit gate refuses for 60 seconds.

Expected:
  state = RETRY_WAIT
  next_attempt_at = now + 60 sec
  attempt_count unchanged
  transport calls = 0
~~~

To drive scenarios across simulated time, inject **Clock** instead of calling **Instant.now()** directly in services. When test time advances to nextAttemptAt, the worker claims the job again.

## 43. PostgreSQL Integration Test: Two Workers Do Not Claim the Same Job

A critical test has two consumers read concurrently:

~~~text
Given:
  DB has 1 PENDING job
  Worker A and Worker B call claimNext concurrently

When:
  Both use FOR UPDATE SKIP LOCKED in one SQL statement

Then:
  Exactly one worker obtains the job
  Other returns empty
  State = IN_FLIGHT
  One lease token exists
~~~

### Testing with Testcontainers

You can run a PostgreSQL Testcontainer and apply real migrations; do not use H2 to simulate **FOR UPDATE SKIP LOCKED** because SQL and locking semantics differ.

Pseudocode:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Optional<ClaimedMailJob>> claim = () -> {
    start.await();
    return repository.claimNext(
            UUID.randomUUID().toString(),
            fixedClock.instant(),
            Duration.ofSeconds(45)
    );
};

Future<Optional<ClaimedMailJob>> left =
        pool.submit(claim);
Future<Optional<ClaimedMailJob>> right =
        pool.submit(claim);

start.countDown();
var a = left.get();
var b = right.get();

assertEquals(
        1,
        (a.isPresent() ? 1 : 0)
        + (b.isPresent() ? 1 : 0)
);
pool.shutdown();
~~~

This snippet only illustrates the concurrency part of a JUnit test; a project test still needs repository setup, database migration, test transaction boundaries, imports, cleanup, and timeouts. Note that if the test method runs inside an uncommitted transaction on another thread, worker threads will not see the seeded row; seed and commit before releasing the latch.

### Testing Multiple Jobs

With 100 PENDING jobs and 10 workers:

~~~text
Expected:
  each job claimed at most once per active lease
  no duplicate lease token for the same active job
  no DB deadlocks due to claim ordering
  workers can process other jobs while one row is locked
~~~

**SKIP LOCKED** works well to distribute jobs, though it does not guarantee strict fairness across tenants or purposes. If you have multiple priority lanes, add dedicated scheduling or budgets.

## 44. Fault Injection: Crash After SMTP Accepted

This test separates a safe worker from a dangerous retry loop.

~~~text
1. Worker claims N-101.
2. beginAttempt writes attempt 1 STARTED.
3. Fake provider records email ACCEPTED.
4. Simulate process crash before finishAttempt writes DB.
5. Lease expires.
6. Recovery transitions N-101 to UNKNOWN.
7. Scheduler must not claim N-101 automatically.
8. Operator/provider reconciliation confirms accepted.
9. Record ACCEPTED without sending again.
~~~

Expected:

- **FakeMailTransport call count = 1**.
- Outbox **UNKNOWN** after lease recovery.
- Job is not picked up by the PENDING/RETRY_WAIT claim query.
- After reconciliation, state is ACCEPTED and attempt history records full evidence.
- No new notificationId created, no duplicate send.

### Control Test: Crash Before beginAttempt

If the worker claims a job and crashes before beginAttempt, recovery can verify no attempt record exists and allow requeuing under an approved policy. A conservative demo may still transition to UNKNOWN; that is an availability trade-off to curb duplicates.

### Test: Database Unavailable When Finalizing

If the server accepted but the JDBC update fails, the worker must not call transport again. It can retry the outcome-persistence transaction while the lease remains valid; otherwise move to UNKNOWN and reconcile. Fault injection should confirm submission count does not increase.

### Test: Two Workers and Expired Lease

Worker A starts a very slow SMTP call and its lease expires; recovery transitions to UNKNOWN. Worker B must not automatically reclaim that job. If A later receives accepted, finalizing with a stale token/state must not overwrite UNKNOWN; only an operator/reconciler updates it with an audit entry.

## 45. Monitoring: Measure States Instead of Only Counting send()

If dashboards only show how many times **JavaMailSender.send(...)** was called, the application cannot tell whether backlog is growing, OTPs are about to expire, or dead letters are neglected.

| Logical Metric | Type | Meaning |
| --- | --- | --- |
| **mail_outbox_jobs** | Gauge | Job count by state/purpose |
| **mail_outbox_oldest_pending_age_seconds** | Gauge | Age of oldest PENDING/RETRY_WAIT job |
| **mail_worker_claims_total** | Counter | Successful/failed claim counts |
| **mail_worker_stale_lease_total** | Counter | Worker finalizations with an invalid/expired lease |
| **mail_attempts_total** | Counter | Attempt count by provider/result |
| **mail_attempt_duration_seconds** | Timer | Transport submission duration |
| **mail_retry_scheduled_total** | Counter | Retries scheduled by reason |
| **mail_retry_delay_seconds** | Timer/Histogram | Planned delay before next attempt |
| **mail_dead_letter_total** | Counter | Jobs moved to DLQ by reason |
| **mail_dead_letter_backlog** | Gauge | Jobs currently in DEAD_LETTER |
| **mail_unknown_backlog** | Gauge | Jobs currently in UNKNOWN |
| **mail_lease_expired_total** | Counter | Expired leases caught by recovery |
| **mail_notification_expired_total** | Counter | Notifications past business TTL |
| **mail_quota_denied_total** | Counter | Jobs denied a permit |
| **mail_replay_actions_total** | Counter | Replay/manual actions by outcome |

These names are **application-defined metric suggestions**, not built-in Spring Mail metrics. Prometheus exporters may append a **_total** suffix depending on the meter registry.

### Micrometer Example

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailWorkerMetrics {

    private final MeterRegistry registry;

    public MailWorkerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAttempt(
            String provider,
            String result,
            long elapsedNanos
    ) {
        registry.counter(
                "mail_attempts",
                "provider", provider,
                "result", result
        ).increment();

        registry.timer(
                "mail_attempt_duration",
                "provider", provider,
                "result", result
        ).record(elapsedNanos, java.util.concurrent.TimeUnit.NANOSECONDS);
    }
}
~~~

To use the Micrometer example, add **spring-boot-starter-actuator** or the appropriate meter registry setup. Never attach raw exception text, recipient email addresses, business keys, or notificationIds as metric labels, as that causes high cardinality and leaks information.

### Critical Alerts

- **UNKNOWN backlog rising**: ambiguous outcomes or recovery issues may be occurring; reconcile rather than enabling automatic retry.
- **DEAD_LETTER backlog rising**: template bug, provider config issue, or overly strict retry policy.
- **High oldest pending age**: scheduler, quota, or SMTP is slowing down.
- **Expired leases rising**: worker crashes, leases too short, or SMTP timeouts.
- **Retry storm**: many jobs hitting the same transient failure; needs circuit breaker/backoff.
- **Bulk SMTP auth errors**: pause the provider lane and check secrets.

### Structured Logs

Example:

~~~text
event=mail_attempt_finalized
notification_id=opaque-id
attempt_number=3
tenant_tier=business
provider=primary
old_state=IN_FLIGHT
new_state=RETRY_WAIT
error_code=SMTP_TEMP_REJECT
retry_at=2026-01-01T10:15:00Z
~~~

Do not log raw HTML, plain text, OTPs/tokens, or SMTP credentials. Use opaque IDs to look up details in the database with appropriate permissions.

## 46. Security, Privacy, and Operational Controls

A retry worker with permission to send email is a sensitive component: if abused, it can send spam, exfiltrate data, or damage domain reputation.

### Essential Controls

1. **API authentication:** do not let anonymous requests supply arbitrary senders or recipients.
2. **Tenant authorization:** one tenant must never view or replay another tenant's jobs.
3. **Verified sender profile:** From/Reply-To must come only from verified configuration.
4. **Recipient policy:** consent, suppression, bounces, and unsubscribes enforced per purpose.
5. **Encryption:** TLS with the provider, plus appropriate encryption for DB/object storage.
6. **Secret management:** never put SMTP passwords in code, Git, or logs.
7. **Template trust:** prevent server-side template injection and HTML injection.
8. **URL/token TTL:** verification links must be issued by a trusted service and expire.
9. **Audit:** replay, cancel, reconcile, and quota overrides all record actor and reason.
10. **Rate limiting:** prevent abuse by a tenant or account.
11. **Retention:** email bodies, attempts, DLQ records, and logs each have explicit retention periods.
12. **Webhook verification:** when receiving provider feedback, require signature/replay checks.

### Dead-Letter UI Should Not Return Body by Default

An operator page can display:

~~~text
Notification: 8a...
Tenant: tenant-7
Purpose: ORDER_RECEIPT
Recipient: c***@example.test
State: DEAD_LETTER
Error: TEMPLATE_MODEL_INVALID
Attempts: 0 / 5
Created: ...
~~~

Only with explicit authorization and a business justification should an operator open redacted or full content. Do not turn the DLQ into an easy way to bulk-download PII for all failed emails.

### Do Not Use Manual Replay as a Backdoor Past Suppression

If a user unsubscribed from marketing after an initial email failed, replay must **re-check current suppression/consent**, rather than sending based on stale consent state.

### Transport Configuration Must Be Verified

For example, Spring Mail needs connection/read/write timeouts, TLS/auth, and proper certificate verification. Never enable raw SMTP protocol debug logging in production if logs could capture credentials, addresses, or sensitive content.

## 47. Runbook: Provider Unavailable and Backlog Growing

### Symptoms

~~~text
mail_outbox_oldest_pending_age_seconds increases
mail_attempts_total{result=UNKNOWN} increases
mail_retry_scheduled_total increases
SMTP connection errors / timeouts spike
~~~

### Response Steps

1. Verify provider/network/TLS/auth rather than assuming a quota error.
2. Check whether controlled canary sends still succeed via a test account.
3. Pause the lane or trip the circuit breaker on systemic errors to prevent a retry storm.
4. Inspect attempts marked **ACCEPTED**, **UNKNOWN**, and **proven not accepted**.
5. Adjust backoff, retry budget, and distributed rate limits.
6. Do not move all UNKNOWN jobs to PENDING just to “try again”.
7. Expire stale OTPs/deadlines per policy.
8. When the provider recovers, drain the backlog at an authorized rate.
9. Verify no duplicate notifications were created and attempt history is complete.

### Which Jobs Can Retry Automatically?

Only **RETRY_WAIT** jobs with failures proven not accepted that still have budget and time before their deadline. UNKNOWN jobs need reconciliation; DEAD_LETTER jobs need operator action; EXPIRED/CANCELLED/ACCEPTED jobs are never auto-requeued.

### Do Not Scale Workers Indefinitely

If the provider allows 10 recipients/s and the backlog is 100,000, adding 100 workers will not finish in seconds. Choose an admission, priority, and backlog strategy and estimate drain time.

### Post-Incident

Analyze root cause, outage duration, affected jobs by state, potential duplicate recipients, and reconciliation coverage. Add fault-injection tests where gaps appeared.

## 48. Runbook: Sudden Dead-Letter Spike

**Step 1 — Group by reasonCode.**

~~~sql
SELECT dead_letter_reason, COUNT(*)
FROM mail_outbox
WHERE state = 'DEAD_LETTER'
GROUP BY dead_letter_reason
ORDER BY COUNT(*) DESC;
~~~

**Step 2 — Verify root cause.** If most are TEMPLATE_MODEL_INVALID, do not open more SMTP connections or raise max_attempts; fix the producer/template. If most are SMTP_AUTH_CONFIGURATION, check for secret rotation or sender verification issues.

**Step 3 — Scope the impact.** Tenant, purpose, template revision, provider, time window. Do not bulk-replay simply because one error cleared.

**Step 4 — Segment eligibility.** Some jobs have expired, recipients are suppressed, or content changed. Select only valid jobs for replay.

**Step 5 — Dry run.** A mature system provides a dry-run mode that checks replay eligibility without changing state, returning counts of blocking reasons and estimated traffic.

**Step 6 — Canary replay.** Replay a small safe batch first, ramp within quota/SLO, and keep a batch pause switch ready.

**Step 7 — Audit.** Record actor, job count, policy, reason, old/new attempts, and outcome.

### Dead Letters Replayed That Fail Again

If the root cause was not fixed, jobs return to DEAD_LETTER. Do not just keep bumping max_attempts. Track **replay success rate** and stop if the same error recurs.

### Do Not Delete All Dead Letters After a Fix

You can archive per retention policy, but keep minimal audit/evidence showing which emails were unsent and why. Wiping the DLQ to make dashboards look “green” hides incidents.

## 49. Common Mistakes When Building a Retry Worker

### Mistake 1 — Retrying Every JavaMailSender Exception

**Consequence:** the SMTP server may have accepted before the response was lost; retrying sends duplicates.

**Fix:** distinguish **proven not accepted** from **UNKNOWN**, and reconcile ambiguous outcomes before retrying.

### Mistake 2 — Assuming Message-ID Causes SMTP Deduplication

**Consequence:** two submissions with the same Message-ID can still be delivered twice.

**Fix:** business notification keys, attempt history, and provider-specific idempotency where supported.

### Mistake 3 — Putting SMTP Send Inside @Transactional

**Consequence:** long-held DB locks and still not atomic with SMTP.

**Fix:** short outbox transaction, worker submission outside the transaction.

### Mistake 4 — SELECT PENDING Followed by Unconditional UPDATE

**Consequence:** two workers pick the same notification.

**Fix:** atomic claim with **SKIP LOCKED** or compare-and-set.

### Mistake 5 — Not Using a Fencing Token on Finalize

**Consequence:** a worker with an expired lease overwrites newer state.

**Fix:** WHERE state='IN_FLIGHT' AND lease_token=...; affected rows must equal 1.

### Mistake 6 — Automatically Retrying When a Lease Expires

**Consequence:** the old worker may have submitted successfully before crashing.

**Fix:** expired IN_FLIGHT → UNKNOWN for reconciliation.

### Mistake 7 — Incrementing attempt_count on Quota Denial

**Consequence:** jobs enter the DLQ without ever being submitted to SMTP.

**Fix:** separate claim/permit from beginAttempt.

### Mistake 8 — Having No Attempt History

**Consequence:** no visibility into how many attempts occurred, which errors happened, or via which provider.

**Fix:** persist attemptId, attemptNumber, timestamps, result, provider ID, and error code.

### Mistake 9 — Calling send() Again When DB Finalization Fails

**Consequence:** already accepted, but a DB error causes a duplicate send.

**Fix:** retry only persisting the result while the token is valid, or move to UNKNOWN/reconcile.

### Mistake 10 — Cluster-Wide Synchronized Fixed-Delay Retries

**Consequence:** retry storm after an outage.

**Fix:** exponential backoff, jitter, and a distributed quota rate limiter.

### Mistake 11 — Ignoring Business Deadlines

**Consequence:** expired OTPs or links still get sent.

**Fix:** expiresAt, expiry checks, and deadline-aware retry decisions.

### Mistake 12 — Dead Letter Is Just an Error Log

**Consequence:** jobs vanish and cannot be reviewed or replayed.

**Fix:** store durable state + reason + history + audit.

### Mistake 13 — One-Click Replay All Button

**Consequence:** quota exhaustion, duplicates, sending to opted-out recipients.

**Fix:** RBAC, eligibility re-checks, canary/batch replay, and rate control.

### Mistake 14 — Resetting attempt_count to 0 on Replay

**Consequence:** lost history, UNIQUE(attempt_number) conflicts, poor auditability.

**Fix:** keep prior attempts, raise max_attempts deliberately or create a new notification with lineage.

### Mistake 15 — Allowing UNKNOWN Replay After Relabeling to DEAD_LETTER

**Consequence:** bypasses duplicate-prevention policy.

**Fix:** preserve ambiguous-attempt history; verify evidence before any replay.

### Mistake 16 — Failing to Separate Permanent and Transient Errors

**Consequence:** invalid addresses or broken templates retry endlessly.

**Fix:** a classifier with explicit reason codes and terminal decisions.

### Mistake 17 — Sending All Jobs to DLQ on Provider-Wide Auth Errors

**Consequence:** DLQ floods when the root cause is one secret.

**Fix:** provider-level pause/circuit breaker and alert; leave jobs unattempted.

### Mistake 18 — Unbounded Workers/Connections

**Consequence:** resource and provider quota exhaustion.

**Fix:** bounded executor, semaphore, distributed rate limit.

### Mistake 19 — Claiming a Batch Larger Than Send Capacity

**Consequence:** leases expire while jobs sit waiting in memory.

**Fix:** claim up to actual worker/permit capacity; use heartbeats when needed.

### Mistake 20 — Measuring Only ACCEPTED Emails

**Consequence:** blind to pending age, unknown backlog, and dead letters.

**Fix:** metrics by state, reason, latency, and deadline.

### Mistake 21 — Logging Raw Bodies or OTPs on DLQ

**Consequence:** leaks PII, tokens, and internal info.

**Fix:** metadata/safe error codes, access control, and retention.

### Mistake 22 — Accepting Arbitrary Sender Profiles from API

**Consequence:** domain spoofing, violating verified identities.

**Fix:** allowlist sender profiles per tenant and purpose.

### Mistake 23 — Treating ACCEPTED as Delivered to Inbox

**Consequence:** inaccurate delivery reporting; bounces/delivery need a separate system.

**Fix:** separate SMTP acceptance from provider delivery feedback.

### Mistake 24 — Retrying Old Jobs with Newer Business Data

**Consequence:** invoice amounts, links, or codes change between attempts.

**Fix:** pin template revision and model/render snapshot per policy.

### Mistake 25 — Building a Dead-Letter Queue Without an Operator Flow

**Consequence:** thousands of dead jobs sit unhandled.

**Fix:** dashboards, reasons, ownership, SLAs, replay/cancel, and audit.

## 50. Practice Scenarios and Questions

### A. Two Replicas Poll the Same Job Simultaneously

**Input:** two workers see PENDING at the same instant.

**Question:** what mechanism guarantees only one claim succeeds?

**Solution:** PostgreSQL **FOR UPDATE SKIP LOCKED** inside a single UPDATE...RETURNING statement, with a distinct lease token per claim. Unit/integration test with two concurrent calls.

### B. Worker Claims a Job Then Quota Runs Out

**Input:** job is IN_FLIGHT but the permit gate denies sending.

**Question:** should attempt_count be incremented?

**Solution:** no. **releaseWithoutAttempt** moves it to RETRY_WAIT with nextAt without writing mail_attempt.

### C. SMTP Returns a Retryable Error Before DATA

**Input:** provider confirms content was not accepted.

**Question:** what state should be used?

**Solution:** **RETRY_WAIT** if attempts and deadline remain, using backoff+jitter. If tries are exhausted, **DEAD_LETTER**.

### D. Timeout After DATA

**Input:** sender never receives the final response.

**Question:** should it auto-retry?

**Solution:** **UNKNOWN**; reconcile or make an audited risk decision before resubmitting.

### E. Worker Dies Before Finalize

**Input:** attempt is STARTED, provider may have accepted, lease expires.

**Solution:** expired IN_FLIGHT → UNKNOWN, do not auto-reclaim.

### F. Template Missing Order Code Variable

**Input:** preflight fails before SMTP.

**Solution:** **DEAD_LETTER** or review per policy; do not increment transport attempts and do not call the sender.

### G. OTP Expires While Waiting for Retry

**Input:** nextAttemptAt falls after expiresAt.

**Solution:** **EXPIRED**; do not send a dead token—the user needs a flow to request a new code.

### H. Reaching 5/5 Attempts

**Input:** all five failures were proven not accepted.

**Solution:** **DEAD_LETTER / ATTEMPTS_EXHAUSTED**, preserve history, do not retry infinitely.

### I. Operator Wants to Raise max_attempts from 5 to 7

**Input:** DEAD_LETTER job due to transient pre-acceptance failures, provider has recovered.

**Solution:** verify eligibility and evidence, keep attempt_count=5, update max_attempts=7, move to PENDING with an audit entry; do not reset attempts.

### J. Recipient Unsubscribed Before Replay

**Input:** old marketing DEAD_LETTER job.

**Solution:** current suppression/consent wins; do not replay marketing mail that opted out.

### K. Stale Worker Tries to Write ACCEPTED

**Input:** Worker A holds an old token; the job already moved to UNKNOWN.

**Solution:** finalizing with WHERE state='IN_FLIGHT' AND lease_token=A affects 0 rows and reports a stale result. Reconciliation handles the evidence.

### L. Database Down After SMTP Accepted

**Input:** send() returned success, finishAttempt JDBC failed.

**Solution:** do not resend. Retry persistence if possible within the lease; after crash/expiry handle as UNKNOWN and reconcile.

### M. Wrong SMTP Auth for Every Job

**Input:** hundreds of jobs hit MailAuthenticationException.

**Solution:** pause the provider lane/trip the circuit breaker, alert, and fix the secret; do not burn attempts on every job.

### N. One Email Has 3 Recipients

**Input:** sending a single MimeMessage to multiple To/Cc recipients.

**Solution:** partial success and quota tracking become complex; the demo should use one recipient per logical notification. If extending, store per-recipient outcomes and never retry recipients already accepted.

### O. DLQ Spikes After Publishing a New Template

**Input:** many TEMPLATE_MODEL_INVALID errors.

**Solution:** fix producer/template, review pinned revisions, do not scale workers or SMTP quota; replay only valid jobs.

### P. 1,000 Dead-Letter Jobs and Someone Clicks Replay All

**Input:** provider allows only 20 recipients/s.

**Solution:** dry run, canary, bounded batch/rate, maintain audit and a pause switch. Do not fire 1,000 attempts at once.

### Q. Client Retries POST /notifications After Timeout

**Input:** the same businessKey is submitted twice.

**Solution:** **UNIQUE (tenant_id, business_key)** and return the same notification ID if payload matches; if different, return an idempotency conflict.

### R. Email Was Accepted but Provider Reports a Bounce

**Input:** outbox is ACCEPTED, webhook reports hard bounce.

**Solution:** do not automatically turn it into an SMTP retry; update delivery status/suppression via the separate feedback system and consider recipient verification.

### S. Same Message-ID Across Two Attempts

**Input:** the app reuses the same Message-ID header.

**Solution:** not sufficient to prevent duplicates; you still need the state machine, attempt tracking, and reconciliation.

### T. All Logs Lost After Restart

**Input:** worker crashes and old console logs are gone.

**Solution:** outbox + mail_attempt + audit still show the job's state, which token/attempt ran, and what to do next. Logs only add observability; they do not replace durable state.

## 51. Milestone Implementation Roadmap

To build the worker rather than just reading examples, you can split the practice project into milestones:

### Milestone 1 — Persist Durable Notifications

- Create the PostgreSQL migration.
- Write the enqueue service keyed by **tenant + businessKey**.
- Test that two identical POSTs create only one job.
- Return **PENDING** and notificationId; no SMTP yet.

**Done criteria:** restarting the app does not lose jobs and duplicate enqueues do not create two rows.

### Milestone 2 — Worker Claims a Job

- Write atomic claim SQL with SKIP LOCKED.
- Issue leaseToken and leaseUntil.
- Run two workers claiming the same job concurrently.
- Verify only one claim succeeds.

**Done criteria:** no two active leases exist on the same notification at the same time.

### Milestone 3 — Add Transport and Attempt History

- Write SpringMailTransport.
- Call beginAttempt before SMTP.
- Finalize state with leaseToken.
- Use Mailpit/an SMTP fixture to capture mail.
- Observe PENDING → IN_FLIGHT → ACCEPTED.

**Done criteria:** every attempt is recorded with the right number/outcome; accepted jobs are never auto-resent.

### Milestone 4 — Retry Policy

- Enforce maxAttempts.
- Add exponential backoff + jitter.
- Check expiresAt.
- Test fake transport failing twice then succeeding.
- Test the Nth failure transitioning to DEAD_LETTER.

**Done criteria:** no tight retry loop, nextAttemptAt is stored in the DB, and workers are not held in thread sleep.

### Milestone 5 — UNKNOWN and Recovery

- Sweep expired IN_FLIGHT leases.
- Transition to UNKNOWN with no auto retry.
- Inject crashes after send and DB update failures.
- Add audited reconciliation actions.

**Done criteria:** when the fake provider accepted an email but the client lost the response, only **one automatic transport submission** occurs.

### Milestone 6 — Dead Letter and Operator Workflow

- List dead letters by reason.
- View attempt history safely with PII redaction.
- Replay with authorization, audit, state CAS, and maxAttempts budget.
- Canary replay with quota gate.
- Cancel jobs that are no longer valid.

**Done criteria:** operators cannot replay ACCEPTED or unreconciled UNKNOWN jobs and cannot bypass suppression/expiry.

### Milestone 7 — Monitoring and Production Hardening

- Metrics for backlog, age, unknown, dead letter, retries.
- Rate/concurrency limits.
- Provider-level pause/circuit breaker.
- Secure sender profiles, secrets, TLS, retention.
- Test multi-replica, provider outage, and quota exhaustion.

**Done criteria:** failures are observable, sending halts safely, and recovery is controlled.

## 52. Pre-Production Readiness Checklist

### State Machine and Database

- **PENDING, IN_FLIGHT, RETRY_WAIT, ACCEPTED, UNKNOWN, DEAD_LETTER, EXPIRED, CANCELLED** are clearly defined.
- Every transition is validated; no arbitrary state writes from the API.
- Enqueue uses a business idempotency key and unique constraint.
- Claim is atomic, with lease owner/token and fencing.
- BeginAttempt writes durable history before SMTP.
- Finalization and attempt history share a single transaction.
- Expired IN_FLIGHT jobs never auto-retry.
- Terminal statuses are never reclaimed automatically by the scheduler.
- DB migrations/indexes/retention are managed.

### Retry and Dead Letter

- Retries run only for **proven not accepted transient** failures or cases where provider semantics are safe.
- UNKNOWN is separated from RETRY_WAIT.
- Max attempts cannot be exceeded via races or restarts.
- Backoff+jitter and provider-specified retry-after are respected.
- Quota denials do not spend attempts.
- Expired OTPs/tokens are never sent late.
- DLQ retains reasons and history; never auto-deleted.
- Manual replay enforces RBAC, audit, eligibility, and rate limits.
- Replay does not reset attempt numbering or erase history.
- Replaying UNKNOWN requires reconciliation/risk approval.

### SMTP and Content

- JavaMailSender timeouts/TLS/auth are properly configured.
- Sender profiles are verified per tenant.
- Recipients pass validation/suppression/consent checks per purpose.
- Plain/HTML bodies use the same model/template revision.
- Never log SMTP secrets, OTPs, or raw messages.
- Attachment sizes and MIME encoding are controlled.
- Never confuse SMTP accepted with delivered.

### Scaling and Observability

- Worker concurrency is bounded; claims match real capacity.
- Global/distributed rate limits protect shared provider quota.
- Alerts cover pending age, retry storms, UNKNOWN, and DLQ growth.
- Metrics break down by provider/purpose/result without leaking PII.
- Multi-replica schedulers do not double-claim.
- Provider outages do not cause tight send loops.
- Runbooks exist for pause/replay/cancel/reconcile.
- Load testing uses a sandbox/fake provider, never spamming real users.

### Testing

- Unit tests cover RetryPolicy and maxAttempts/expiry boundaries.
- Unit tests cover preflight invalid/consent/recipient checks.
- Integration tests verify claim concurrency against real PostgreSQL.
- Tests verify no-permit does not increment attempts.
- Tests verify SMTP accepted → ACCEPTED.
- Tests verify proven transient → RETRY_WAIT and retry after nextAt.
- Tests verify permanent failure → DEAD_LETTER.
- Tests verify DB failure after SMTP accepted → UNKNOWN, no resend.
- Tests verify crash/lease expiry → UNKNOWN.
- Tests verify replay authorization, audit, and state compare-and-set.
- Tests verify unknown reconciliation and duplicate protection.

## 53. Architectural Summary to Remember

~~~text
Enqueue
  -> write durable PENDING job
  -> dedup by tenant + business key
  -> no SMTP inside business transaction

Claim
  -> SELECT ... FOR UPDATE SKIP LOCKED
  -> IN_FLIGHT with lease token
  -> commit DB transaction

Preflight + quota
  -> validate recipient/template/deadline
  -> if no permit: reschedule WITHOUT attempt

BeginAttempt
  -> increment attempt_count
  -> insert STARTED history
  -> commit BEFORE external SMTP call

Submit
  -> JavaMailSender
  -> outside DB transaction

Finalize
  -> compare state + lease token
  -> update outbox + history atomically

ACCEPTED
  -> no automatic retry
  -> not equal delivered/read

RETRYABLE_NOT_ACCEPTED
  -> exponential backoff + jitter
  -> retry until max attempts / deadline

UNKNOWN
  -> reconcile first, do not blind resend

DEAD_LETTER
  -> durable holding state with reason/history
  -> manual reviewed replay or cancel
  -> not an automatic retry queue

EXPIRED
  -> don't send stale OTP/links

Lease expired
  -> UNKNOWN, not PENDING

Replay
  -> RBAC + audit + compare-and-set
  -> preserve attempt numbers
  -> recheck suppression, deadline and content

Horizontal scale
  -> atomic claims + distributed quota controls

Transactional outbox
  -> durable intent
  != exactly-once SMTP delivery
~~~

**Building a retry worker with state and dead letter** is the step from a single **JavaMailSender.send(...)** call to a durable email delivery mechanism that can be observed and recovered when failures happen. In this practice project, PostgreSQL stores the outbox and attempt history; the worker uses **SKIP LOCKED** to claim jobs, a **lease token** to block overwrites from stale workers, **backoff+jitter** to retry failures proven not accepted, and **DEAD_LETTER** to retain jobs needing investigation. Most importantly, distinguish **RETRY_WAIT** from **UNKNOWN**: an SMTP timeout or JVM crash does not prove an email was not sent. Adding reconciliation, audited manual replay, quota limits, expiry, and crash-after-acceptance tests lets the system scale while curbing duplicates and preserving full visibility into **which notification was tried, when, with what outcome, and what action comes next**.
