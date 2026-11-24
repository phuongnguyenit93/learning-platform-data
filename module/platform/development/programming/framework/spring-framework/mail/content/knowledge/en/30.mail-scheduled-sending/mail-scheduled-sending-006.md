# Distributed Locks for Mail-Sending Workers

In a **Spring Framework Mail** system, email sending is often offloaded to a scheduled worker so HTTP requests do not wait on SMTP and retries can be applied easily when a provider fails temporarily. With a single instance, a method annotated with **@Scheduled** may seem sufficient. When deploying multiple instances for high availability or horizontal scaling, **the same schedule can run concurrently across multiple nodes**, and every node can read the exact same pending email.

If two workers both read a PENDING outbox record and call **JavaMailSender.send(...)**, the recipient can receive two emails. The problem gets harder when workers crash mid-flight, locks expire, networks partition, or the SMTP relay accepts a message before the database updates its state.

**Distributed locking for mail-sending workers** is a set of techniques for coordinating processes across machines, determining who may execute work and when that right expires. In an email system, distinguish three layers carefully:

1. **Distributed scheduler lock**: prevents multiple instances from running the same scheduler dispatch/fetch cycle simultaneously.
2. **Per-job claim or lease**: ensures an outbox job has at most one valid owner during a bounded time window.
3. **SMTP submission and email business logic**: network side effects outside database transactions; locks alone do not deliver exactly-once guarantees.

The first two lock layers address processing contention; the third concerns **correctness under failure** and requires proper retry, idempotency, reconciliation, and observability design.

This lesson presents these patterns in the context of **Scheduled Sending** with Spring Framework Mail: **@Scheduled**, ShedLock, PostgreSQL **FOR UPDATE SKIP LOCKED**, lease/claim tokens, fencing, Redis locks, transaction boundaries, SMTP duplicate windows, dead-lettering, monitoring, and concurrency testing.

## 1. Why Can @Scheduled Across Multiple Instances Send Duplicates?

Suppose two application instances share one database:

~~~text
                 Shared database
                 mail_outbox
                     |
          +----------+----------+
          |                     |
          v                     v
    Application A         Application B
    @Scheduled            @Scheduled
          |                     |
          v                     v
    SELECT PENDING        SELECT PENDING
          |                     |
          +----------+----------+
                     |
               Same mail ID
                     |
          +----------+----------+
          v                     v
   JavaMailSender A      JavaMailSender B
          |                     |
          v                     v
       SMTP relay accepts two submissions
~~~

If workers merely execute:

~~~sql
SELECT *
FROM mail_outbox
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 100;
~~~

and then send and update SENT afterward, both A and B can read the same PENDING rows before either node writes the new status.

### 1.1. Example race-condition timeline

~~~text
10:00:00.000 A reads job #42 -> PENDING
10:00:00.010 B reads job #42 -> PENDING
10:00:00.100 A sends job #42 through SMTP
10:00:00.120 B sends job #42 through SMTP
10:00:00.300 A marks job #42 SENT
10:00:00.310 B marks job #42 SENT
~~~

The database ends up recording **SENT** with no clue that two SMTP submissions occurred, unless the application records attempt history.

### 1.2. @Scheduled is not a distributed mutex

Spring **@Scheduled** triggers a method by cron/fixed delay/fixed rate inside each application process. It does not ensure only one of multiple processes runs.

### 1.3. synchronized and ReentrantLock are also insufficient

~~~java
synchronized void dispatch() {
    // ...
}
~~~

or a **ReentrantLock** coordinates only threads sharing that lock inside the **same JVM**. Application B runs in its own JVM and cannot see A's mutex.

## 2. Two Kinds of Exclusivity to Decide Between

Not every system needs a **global lock** across the entire scheduler cycle. Two common strategies exist:

| Strategy | Unit of exclusivity | Benefits | Limitations |
| --- | --- | --- | --- |
| **Global scheduler lock** | One job trigger, e.g., mail-dispatch | Easy to add for short batch jobs | Can bottleneck throughput |
| **Outbox-row claiming** | Each mail event/job | Multiple workers process distinct jobs in parallel | Requires clear state machine/leases/recovery |
| **Hybrid** | Scheduler trigger + individual jobs | Controls both dispatch and ownership | Higher complexity; not always needed |
| **Broker delivery/consumer groups** | Broker partition/message ownership | Leverages broker mechanics | Still needs ACKs, retries, and side-effect dedup |

### 2.1. When is a scheduler lock enough?

If a short run only performs administrative coordination, such as scanning backlogs and spawning child jobs, a global lock can help. However, if the scheduler holds the lock while sending thousands of emails, all mail throughput gets bottlenecked on one node.

### 2.2. When is per-row claiming a better fit?

With tens of thousands of outbox jobs, multiple workers can claim **distinct rows** to send in parallel. In that case, atomic per-row claiming is the primary coordination mechanism, without forcing only one scheduler to run.

### 2.3. Choosing based on business requirements

- Want each scheduler batch to run once: consider ShedLock.
- Want multiple nodes picking up distinct work without colliding on jobs: use atomic row claiming.
- Want reliable mail dispatch after database commit: use an outbox/durable queue.
- Want exactly-once SMTP: understand that these mechanisms **do not provide that guarantee by themselves**.

## 3. What Does a Distributed Lock Actually Consist Of?

A reliable lock design typically requires:

- **Lock key**: defines the scope of exclusivity.
- **Owner identity**: who currently holds processing rights.
- **Acquisition**: atomic lock acquisition operation.
- **Lease/expiration**: time-bounded lock enabling recovery if the owner dies.
- **Renewal/heartbeat**: extending the lease while work is actively running.
- **Release**: only the valid current owner may release the lock.
- **Ownership check/fencing**: stops a stale owner from writing outcomes after ownership transferred.
- **Recovery policy**: handles jobs still PROCESSING after lease expiration.
- **Observability**: tracks how many locks were acquired, skipped, expired, and reclaimed.

### 3.1. Lock keys must be precise

A key like:

~~~text
mail:dispatcher
~~~

fits allowing only one scheduler dispatcher to run.

A key like:

~~~text
mail:job:42
~~~

ties to a single mail job. However, **avoid creating an unbounded distributed lock object per message** when database row claiming already provides the same effect more efficiently.

### 3.2. Leases differ from infinite mutexes

A lease expires. If a worker dies, other nodes can take over after expiration. That improves availability while introducing the risk of **an old owner still running after its lease expired**.

### 3.3. Never confuse "lock acquired" with "guaranteed single SMTP execution"

Networks can stall, processes can pause, and leases can expire before SMTP finishes. A lock that was valid at acquisition is not guaranteed to remain valid when the external side effect occurs.

## 4. Never Use Separate SELECT Then UPDATE

An anti-pattern:

~~~java
List<MailJob> jobs = repository.findPending();

for (MailJob job : jobs) {
    repository.markProcessing(job.id());
    mailSender.send(build(job));
}
~~~

At **findPending()**, both nodes can read the same record. Calling **markProcessing()** afterward does not prevent races if the update fails to check prior state and ownership.

### 4.1. Atomic claiming is required

The required operation is essentially:

~~~text
IF job is eligible and not owned
THEN atomically assign it to this worker
ELSE this worker does not process it
~~~

This can be implemented via:

- Conditional database UPDATE checking affected row count.
- Transaction with **SELECT ... FOR UPDATE SKIP LOCKED** followed by update.
- Atomic queue claim/ack from a broker.
- A lock manager implemented with proper semantics.

### 4.2. Do not rely solely on a PROCESSING status

If an UPDATE looks like:

~~~sql
UPDATE mail_outbox
SET status = 'PROCESSING'
WHERE id = :id;
~~~

then both Worker A and Worker B can succeed on the same row because neither prior status nor owner was checked.

At minimum, require a predicate:

~~~sql
UPDATE mail_outbox
SET status = 'PROCESSING'
WHERE id = :id
  AND status = 'PENDING';
~~~

and **only the worker receiving affectedRows = 1 may process it**. Still, proper recovery also requires tokens, leases, and complete state modeling.

## 5. State Machine for the Mail Outbox

A suggested state model:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP call returned successfully --> SENT
   |
   +-- retryable known failure ---------> RETRY_WAIT
   |
   +-- permanent failure ---------------> FAILED
   |
   +-- ambiguous outcome --------------> UNKNOWN_OUTCOME
   |
   +-- worker crashed / lease expired --> ELIGIBLE_FOR_RECOVERY
                                            |
                                            v
                                       PROCESSING
~~~

**ELIGIBLE_FOR_RECOVERY** can be a derived condition (**PROCESSING + expired claim_until**) rather than a stored database enum value.

### 5.1. Distinguishing PENDING and RETRY_WAIT

- **PENDING**: job committed and not yet attempted or ready for first send.
- **RETRY_WAIT**: job previously failed and is eligible for retry starting at `nextAttemptAt`.
- **PROCESSING**: a worker currently holds the lease.
- **SENT**: submission observed as successful by the caller, per system convention.
- **FAILED**: permanent error or retries exhausted.
- **UNKNOWN_OUTCOME**: unclear whether the SMTP relay accepted the message.

### 5.2. SENT does not mean inbox delivered

**JavaMailSender.send(...)** returning normally indicates SMTP submission completed at the transport boundary; it does not prove the email landed in the inbox or was read.

### 5.3. Preserve attempt history

A single outbox row holding only final status cannot tell how many times an email was tried, which provider was used, or whether a duplicate window occurred. Use a **mail_attempts** table or structured audit events.

## 6. Illustrative PostgreSQL Schema

An educational schema for this lesson:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    mail_kind VARCHAR(64) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    claim_owner VARCHAR(128),
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ,
    last_error_category VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mail_outbox_ready
    ON mail_outbox(status, next_attempt_at, id);

CREATE INDEX idx_mail_outbox_expired
    ON mail_outbox(status, claim_until, id);
~~~

This is an **illustrative** schema. In production, columns holding email content may contain private data requiring encryption, retention, and access control. For attachments, typically store references to protected storage rather than raw bytes inside the job table.

### 6.1. claim_owner

Worker identifier, such as an instance alias paired with a random process UUID. Never rely solely on a generic pod hostname across restarts if per-session owner identification is needed.

### 6.2. claim_token

An unpredictable token generated for **each claim round**, checked in conditional UPDATEs. Never allow any worker to update SENT using only the job ID.

### 6.3. claim_version

Monotonically increasing version per claim round. Acts as a **fencing token** for database operations or downstream targets that support ordering checks.

### 6.4. claim_until

Lease expiration timestamp. A worker must never assume it owns a job forever merely because it claimed it once.

### 6.5. Database timestamps

Using PostgreSQL's **now()** inside claim/renew/update operations avoids processes comparing clocks across hosts that may drift.

## 7. Batch Claiming with FOR UPDATE SKIP LOCKED

With PostgreSQL, a batch of jobs can be claimed in **one short transaction**.

SQL example:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        AND next_attempt_at <= now()
    )
    OR (
        status = 'PROCESSING'
        AND claim_until < now()
    )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET status = 'PROCESSING',
    claim_owner = :owner,
    claim_token = :token,
    claim_version = m.claim_version + 1,
    claim_until = now() +
        (:lease_seconds * INTERVAL '1 second'),
    attempts = m.attempts + 1,
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING
    m.id,
    m.recipient,
    m.subject,
    m.body_text,
    m.claim_token,
    m.claim_version;
~~~

This statement uses PostgreSQL syntax; do not copy it verbatim to MySQL/SQL Server/Oracle without verifying equivalent syntax and semantics.

### 7.1. Role of FOR UPDATE

It requests row locks on the selected rows for the transaction. Concurrent transactions cannot trivially claim the same row when the query is designed properly.

### 7.2. Role of SKIP LOCKED

If Worker A already locked a row, Worker B **skips the locked row** rather than waiting and grabbing it afterward. This fits multi-consumer queues where strict global ordering is not the sole goal.

### 7.3. Why must it be a short transaction?

The transaction should:

1. Select eligible jobs.
2. Update status/owner/token/version/lease.
3. Return the claimed rows.
4. Commit.

**Never hold transaction row locks while calling SMTP**. SMTP can take seconds, time out, or hang on network issues; holding DB locks degrades throughput and spikes contention.

### 7.4. Expired PROCESSING rows must also be eligible for recovery

If the query selects only PENDING/RETRY_WAIT, a job whose worker crashed in PROCESSING stays stuck forever. The **status = PROCESSING AND claim_until < now()** branch lets a new worker reclaim it after lease expiry.

### 7.5. Expired does not mean unsent

An expired PROCESSING job might already have been accepted by the SMTP relay before the worker crashed prior to writing SENT. On reclaim, apply policies for potential duplicates; database locks only govern database ownership.

## 8. Notes on SQL Claiming and Throughput

### 8.1. ORDER BY does not guarantee strict ordering

With SKIP LOCKED, locked rows are skipped. Under contention, execution order can diverge from `created_at`/`next_attempt_at` order.

If a notification category requires strict ordering, design explicit ordering/partitioning—never treat SKIP LOCKED as strict FIFO.

### 8.2. Batch size

Claiming thousands of jobs with only a few SMTP worker threads leaves most jobs sitting in PROCESSING until their leases expire. Bound batch sizes to real capacity and allowed concurrency.

### 8.3. Indexes must match queries

Indexes on status, next_attempt_at, and claim_until support job selection; table size, status distribution, and real workload dictate tuning. Never add indexes purely by guesswork without database operations planning.

### 8.4. Never claim too far ahead of actual execution

A node should claim only what it can start processing within a reasonable lease window. If a large buffer is needed, design dedicated queuing/workers rather than holding leases on thousands of jobs sitting idle in memory.

## 9. Claim Service Using Spring Transactions

Java concept:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class MailOutboxClaimRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public MailOutboxClaimRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            String owner,
            UUID claimToken,
            int batchSize,
            int leaseSeconds
    ) {
        String sql = """
            WITH picked AS (
                SELECT id
                FROM mail_outbox
                WHERE (
                    status IN ('PENDING', 'RETRY_WAIT')
                    AND next_attempt_at <= now()
                )
                OR (
                    status = 'PROCESSING'
                    AND claim_until < now()
                )
                ORDER BY next_attempt_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT :batch_size
            )
            UPDATE mail_outbox m
            SET status = 'PROCESSING',
                claim_owner = :owner,
                claim_token = :token,
                claim_version = m.claim_version + 1,
                claim_until = now() +
                    (:lease_seconds * INTERVAL '1 second'),
                attempts = m.attempts + 1,
                updated_at = now()
            FROM picked
            WHERE m.id = picked.id
            RETURNING
                m.id,
                m.recipient,
                m.subject,
                m.body_text,
                m.claim_token,
                m.claim_version
            """;

        var params = new MapSqlParameterSource()
                .addValue("owner", owner)
                .addValue("token", claimToken)
                .addValue("batch_size", batchSize)
                .addValue("lease_seconds", leaseSeconds);

        return jdbc.query(
                sql,
                params,
                (rs, rowNum) -> new ClaimedMail(
                        rs.getObject("id", UUID.class),
                        rs.getString("recipient"),
                        rs.getString("subject"),
                        rs.getString("body_text"),
                        rs.getObject("claim_token", UUID.class),
                        rs.getLong("claim_version")
                )
        );
    }
}

public record ClaimedMail(
        UUID id,
        String recipient,
        String subject,
        String bodyText,
        UUID claimToken,
        long claimVersion
) {}
~~~

This example focuses on **atomic claiming and transactions**; it omits full security, validation, outbox schema migrations, and status policies.

### 9.1. Each claim batch needs a fresh token

~~~java
UUID claimToken = UUID.randomUUID();
~~~

The token can be batch-scoped and checked together with **job ID + claim_version**; if per-job identity is desired, generate a token per row.

### 9.2. Transaction proxy

Place the claim method in a dedicated Spring bean repository/service so `@Transactional` activates via the Spring proxy. Calling an annotated method from another method **in the same instance** can bypass the proxy under standard AOP semantics.

### 9.3. Never turn the claim transaction into the place that calls the sender

`claimBatch()` only acquires ownership and commits. Afterward the worker builds MIME and calls `JavaMailSender`, never holding database row locks across SMTP.

## 10. Worker Processing After Claiming

An illustrative orchestration:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxWorker {

    private final MailOutboxClaimRepository claims;
    private final MailOutboxStateRepository states;
    private final JavaMailSender mailSender;

    private final String owner =
            "mail-worker-" + UUID.randomUUID();

    public MailOutboxWorker(
            MailOutboxClaimRepository claims,
            MailOutboxStateRepository states,
            JavaMailSender mailSender
    ) {
        this.claims = claims;
        this.states = states;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "5000")
    public void dispatch() {
        UUID token = UUID.randomUUID();

        List<ClaimedMail> jobs =
                claims.claimBatch(
                        owner,
                        token,
                        10,
                        120
                );

        for (ClaimedMail job : jobs) {
            processOne(job);
        }
    }

    private void processOne(ClaimedMail job) {
        try {
            SimpleMailMessage message =
                    new SimpleMailMessage();

            message.setFrom("notifications@example.org");
            message.setTo(job.recipient());
            message.setSubject(job.subject());
            message.setText(job.bodyText());

            mailSender.send(message);

            states.markSentIfOwned(job);

        } catch (RuntimeException ex) {
            states.handleFailureIfOwned(job, ex);
        }
    }
}
~~~

**MailOutboxStateRepository** is an illustrative application-built component responsible for token/version-checked status updates, error classification, and retries. This code intentionally simplifies the flow to highlight the claim–send–ack boundary.

### 10.1. Production requirements

- Never use raw exception messages as error categories.
- Never mark SENT if owner/token/version is no longer valid.
- If a lease is nearing expiry, consider heartbeating before continuing.
- Never loop indefinitely during an SMTP outage.
- Never put credentials or PII into metric labels or logs.
- Never rely on `fixedDelay` to guarantee only one node runs.
- Never catch `RuntimeException` and blindly retry immediately.
- Check update affected row counts to detect lost ownership.

### 10.2. Sequential batch processing problem

If you claim 10 jobs with a 120-second lease and each send times out at 30 seconds, the 10th job may start after the lease already expired. Another worker can reclaim it while the first worker is still processing.

Solutions: small batches, appropriate concurrency, lease renewal, or claiming right before each item rather than assuming a batch always finishes fast enough.

### 10.3. FixedDelay does not guarantee SLAs

`@Scheduled` fixedDelay runs again after the prior method finishes on that scheduler; if the process crashes or blocks on a slow send, cadence suffers. Monitor oldest pending age and provision sufficient worker capacity.

## 11. Updating SENT via Compare-and-Set

After send returns normally, the worker may update only if it **is still the valid owner**.

PostgreSQL example:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

### 11.1. Check affectedRows

If affectedRows = 1, the database confirmed the matching version/token was updated.

If affectedRows = 0, possible reasons include:

- The lease expired.
- Another worker reclaimed the job and incremented the version.
- The job was cancelled or transitioned.
- Another orchestration operation changed ownership.
- Job ID/token mismatch.

Never report "completed safely" when the update affected zero rows.

### 11.2. Ownership checks protect the database, not reverse SMTP

Even when the update returns 0, **`mailSender.send` may already have executed the email side effect**. CAS prevents an old owner from writing stale state, but cannot pull back an already-sent email.

### 11.3. Never report SENT from logs before the update commits

A log saying "smtp submit success" means the client observed send return normally; "outbox state SENT" should appear only after the conditional update succeeds. These are two separate milestones.

## 12. Fencing Tokens and Stale Workers

A classic hazard:

~~~text
T0  Worker A claims job #42 with lease until T0+60s
T1  Worker A pauses due to long GC/network stall
T2  Lease expires
T3  Worker B reclaims #42, claim_version becomes 8
T4  Worker B starts work
T5  Worker A resumes with old claim_version 7
~~~

Worker A **used to be the valid owner**, but is now a stale owner.

### 12.1. UUID tokens

A random UUID identifies a specific owner round and prevents another worker from accidentally releasing or updating a job using a stale identity.

### 12.2. Fencing versions

A **monotonically increasing `claim_version`** lets the system enforce that newer versions outrank older ones.

Example:

~~~text
Worker A claim_version = 7
Worker B claim_version = 8
Database rejects A's state update
~~~

### 12.3. The target store must enforce fencing

Fencing only stops stale writes if **the target validates the token/version**. A database update with `WHERE claim_version=...` can enforce that.

However, standard SMTP relays **offer no protocol to verify outbox `claim_version` values**. Putting a version into an email header will not make the relay reject an old attempt.

### 12.4. Never advertise fencing as exactly-once SMTP

Fencing protects updates or side effects on targets that verify versions; it **cannot lock out SMTP side effects by itself**. That is a fundamental boundary of distributed locks in email systems.

## 13. Heartbeat Lease Renewal

If work can run longer than the lease duration, a worker can extend the lease while processing.

Example:

~~~sql
UPDATE mail_outbox
SET claim_until =
        now() + INTERVAL '90 seconds',
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

### 13.1. Only the current owner may renew

Verify ID, token, version, and non-expired lease. Never renew a job already reclaimed.

### 13.2. Never renew leases indefinitely

If a worker hangs, an independent renewal loop can hold the job forever even when SMTP makes zero progress. Enforce an **overall attempt deadline**, maximum processing time, and progress monitoring.

### 13.3. Do not use heartbeats to mask missing timeouts

Configure proper `mail.smtp.connectiontimeout`, `mail.smtp.timeout`, and `mail.smtp.writetimeout`. If sockets can hang indefinitely, endlessly extending leases simply stalls the backlog.

### 13.4. Bounded send vs. renewal

It is not easy to cleanly interrupt a blocking SMTP send via a flag. A valid worker can lose its lease while still mid-send. Design job claiming to accept and manage the **ambiguous outcome/duplicate window** instead of assuming heartbeats prevent all duplicates.

## 14. Recovering Expired PROCESSING Jobs

A job in PROCESSING with `claim_until < now()` is a recovery candidate. Two options exist:

1. **Direct reclaim** via SQL matching expired PROCESSING rows.
2. **Recovery sweeper** moving expired-lease jobs to a new pending state after evaluating attempt history.

### 14.1. Never blindly reset all PROCESSING rows

A batch query like:

~~~sql
UPDATE mail_outbox
SET status = 'PENDING'
WHERE status = 'PROCESSING';
~~~

destroys ownership of healthy active workers. Always predicate on lease expiration and status.

### 14.2. Recovery must distinguish failure windows

If we know the worker never opened an SMTP connection, retrying is lower risk. If the worker vanished after transmitting DATA, the outcome is uncertain.

Not every application has telemetry pinpointing the exact pre-crash phase. Thus recovery policies may need to weigh probabilities, email criticality, and reconciliation options.

### 14.3. Time-sensitive events

An OTP or password-reset email may have lost validity while stuck. Recovery must check deadlines/TTL rather than sending stale content merely because a lease expired.

## 15. ShedLock: Locking Scheduled Runs Across Nodes

**ShedLock** is a library commonly used with Spring Scheduling to ensure a named scheduled task does not run concurrently across instances sharing a lock store.

It fits when the goal is **letting only one node execute a scheduler invocation at a time**.

### 15.1. Concept

~~~text
             @Scheduled on Node A
                       |
                       v
                Acquire ShedLock?
                       |
                  YES  |  NO
                       |    |
                       v    v
                Run job  Skip run

             @Scheduled on Node B
                       |
                       v
                Acquire ShedLock?
                       |
                    NO | YES
                       |   |
                       v   v
                  Skip  Run job
~~~

This model is illustrative: a scheduled execution that fails to acquire the lock is typically **skipped**, not automatically queued to run afterward.

### 15.2. Dependencies and versions

Spring Boot projects can use ShedLock's Spring scheduling module and a matching lock provider (e.g., JDBC). Pick versions compatible with your Spring Boot and Java versions.

Gradle example with **versions managed by your project's dependency management**:

~~~groovy
dependencies {
    implementation "net.javacrumbs.shedlock:shedlock-spring"
    implementation "net.javacrumbs.shedlock:shedlock-provider-jdbc-template"
}
~~~

If your project does not manage versions for these two artifacts, declare explicit compatible versions when deploying. This lesson avoids assuming one fixed version across all projects.

## 16. ShedLock JDBC Schema

A common schema:

~~~sql
CREATE TABLE shedlock (
    name VARCHAR(64) NOT NULL PRIMARY KEY,
    lock_until TIMESTAMP(3) NOT NULL,
    locked_at TIMESTAMP(3) NOT NULL,
    locked_by VARCHAR(255) NOT NULL
);
~~~

This table differs from **mail_outbox**. It manages **scheduler-level lock names**, not one row per email.

### 16.1. A stable lock name

Example:

~~~text
mail-outbox-dispatcher
~~~

Every instance running the same scheduled task must use the **same lock name** and the same lock store to contend for execution.

### 16.2. What if two nodes use different databases?

If each node points to its own ShedLock table, each acquires its own lock and no real distributed coordination occurs.

### 16.3. DB time

ShedLock's JDBC provider can use database time to reduce clock skew between instances. When deploying, prefer configuring a consistent time source where supported by the provider.

## 17. Configuring ShedLock with Spring Scheduling

Java example:

~~~java
import javax.sql.DataSource;

import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT2M")
public class MailSchedulerLockConfiguration {

    @Bean
    public LockProvider lockProvider(
            DataSource dataSource
    ) {
        return new JdbcTemplateLockProvider(
                JdbcTemplateLockProvider.Configuration
                        .builder()
                        .withJdbcTemplate(
                                new org.springframework.jdbc.core
                                        .JdbcTemplate(dataSource)
                        )
                        .usingDbTime()
                        .build()
        );
    }
}
~~~

### 17.1. Class and package names

- **@EnableScheduling**: activates Spring's scheduler.
- **@EnableSchedulerLock**: configures locking for annotated scheduled tasks.
- **LockProvider**: abstraction storing/retrieving distributed locks.
- **JdbcTemplateLockProvider**: database-backed implementation via JDBC.
- **usingDbTime()**: prefers the DB clock per JDBC provider capabilities and configuration.

### 17.2. The table must exist

The application does not necessarily auto-create the `shedlock` table. Create it via environment migrations/DDL before the scheduler runs.

### 17.3. Size lockAtMostFor to execution boundaries

If a scheduled job can run longer than 2 minutes, a 2-minute `lockAtMostFor` allows another instance to acquire the lock while the previous worker **is still running**. Design for realistic worst-case runtimes rather than assuming infinite locks.

## 18. Scheduled Methods With @SchedulerLock

Example:

~~~java
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxSchedule {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxSchedule(
            MailOutboxDispatcher dispatcher
    ) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "5000")
    @SchedulerLock(
            name = "mail-outbox-dispatcher",
            lockAtMostFor = "PT2M",
            lockAtLeastFor = "PT3S"
    )
    public void run() {
        dispatcher.dispatchAvailableJobs();
    }
}
~~~

**MailOutboxDispatcher** here is a custom application service; ShedLock does not send emails itself.

### 18.1. lockAtMostFor

Maximum duration a lock stays held if a node dies or fails to release. It is a recovery safety net, **not a timeout that cancels the running method**.

### 18.2. lockAtLeastFor

Minimum lock-hold duration to avoid overly tight back-to-back runs in some setups. It is **not a retry schedule** and must not replace `nextAttemptAt` in the outbox.

### 18.3. What happens when the lock is not acquired?

That scheduled execution is usually **skipped**, not queued waiting for the lock. The next `@Scheduled` tick gets another chance.

### 18.4. Dispatcher runtime must be bounded

If `lockAtMostFor = 2 minutes` while `dispatchAvailableJobs` can block a thread for 10 minutes sending bulk mail, ShedLock no longer prevents overlap after expiry. Bound batch duration or lock only the brief fetch/dispatch coordination step.

## 19. Does ShedLock Replace Row-Level Claiming?

Not necessarily.

Suppose ShedLock ensures only one scheduler runs:

~~~text
Node A holds scheduler lock
        |
        v
Fetch 100 pending emails
        |
        v
Publish tasks to executor
        |
        v
Scheduler releases lock
        |
        v
Node B scheduler starts
        |
        v
Fetch same rows still PENDING
~~~

If A only **enqueued tasks into an executor** without updating ownership in the database, B can pick up the exact same rows after the lock releases.

### 19.1. Lock the right side-effect scope

If ShedLock wraps only enqueueing, durably mark jobs as claimed before releasing the lock.

### 19.2. For high multi-worker throughput

Prefer **atomic outbox claiming**. Nodes can run schedulers concurrently and claim distinct jobs via `SKIP LOCKED` without forcing the whole cluster down to one dispatcher.

### 19.3. When does combining them make sense?

For instance, an exclusive scheduler runs **batch reconciliation or quota allocation**, while actual mail-sending workers use per-row claiming. Those are two distinct scopes.

## 20. Redis Distributed Lock: SET NX PX

Another strategy uses Redis to hold a lock with a TTL.

Example command:

~~~redis
SET mail:dispatcher:lock random-owner-token NX PX 30000
~~~

Meaning:

- **NX**: set the key only if it does not already exist.
- **PX 30000**: TTL in milliseconds.
- **random-owner-token**: unique token identifying the current lock holder.

If Redis returns OK, the client acquired the lock for the Redis lease duration.

### 20.1. Never use SETNX without TTL and forget cleanup

If a worker dies holding a non-expiring lock, the entire scheduler stalls. Always use TTLs/leases.

### 20.2. Never use blind DEL to release

If A acquires the lock, its TTL expires, B acquires a new lock under the same key, and A later runs DEL, A deletes B's valid lock.

### 20.3. Release locks by token

An illustrative Lua script:

~~~lua
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
~~~

Clients must pass both the key and **that acquisition's token**. If the token no longer matches, do not delete another owner's lock.

### 20.4. Renewals must also verify the token

Never blindly PEXPIRE a lock solely by key name. Renewal must verify the current token still matches; otherwise a stale worker can extend a new owner's lock.

## 21. Limitations of Redis Locks

Redis TTL locks help with certain coordination tasks, but understand these failure modes:

- Worker pauses longer than the TTL.
- Network partitions between client and Redis.
- Redis primary failover with asynchronous replication.
- Client loses response and does not know whether acquire/release succeeded.
- An old worker continues executing side effects after the lock was granted to a new worker.

### 21.1. Never treat SET NX PX as exactly-once mail

A lock only governs processing rights for a time window. SMTP relays do not check Redis tokens.

### 21.2. Redlock is not a default silver bullet

Multi-node Redis locking algorithms carry specific assumptions around clocks, fault models, and latency. Even with Redlock, you still must solve stale owners, fencing, and **duplicate SMTP side effects**. Never treat an algorithm's name as proof of exactly-once email delivery.

### 21.3. Pick one source of truth

If jobs already live in a relational outbox database, per-row claiming in that database keeps ownership and state transitions simple. Adding Redis just to hold a separate lock introduces cross-system consistency issues.

## 22. Are Database Advisory Locks Suitable?

Some databases support advisory locks (e.g., PostgreSQL). They can help for **a short coordination step**, with caveats:

- Advisory locks carry session- or transaction-level semantics depending on the API.
- Connection pooling affects session lifetimes.
- Holding a lock during SMTP holds a database connection open too long.
- Advisory locks do not replace durable job status.
- Worker crashes and sends do not form an atomic transaction.

### 22.1. Never use advisory locks to paper over a missing state machine

When you need recovery, retries, attempt history, and per-job ownership, **status/claim token/lease** columns in the outbox remain essential.

### 22.2. Scheduler locks and row locks solve different scopes

Advisory locks can serve as scheduler-level locks; atomic row claiming remains better suited when thousands of mail jobs need parallel processing.

## 23. Never Hold a Database Transaction Open While Sending SMTP

A serious anti-pattern:

~~~java
@Transactional
public void processOne(UUID id) {
    MailJob job = repository.lockById(id);

    mailSender.send(buildMime(job));

    repository.markSent(id);
}
~~~

If SMTP takes 15 seconds:

- The transaction holds a DB connection and row lock for 15 seconds.
- Other workers block or skip rows.
- Database deadlocks/timeouts and throughput degrade.
- If the DB transaction rolls back after SMTP accepted, the email was still sent.

### 23.1. Split the flow

~~~text
Transaction A: claim job atomically
              COMMIT
                     |
                     v
               SMTP send
                     |
                     v
Transaction B: update outcome if still owned
              COMMIT
~~~

### 23.2. Two transactions do not create atomicity with SMTP

SMTP sending sits between the two database transactions. There is a crash/timeout window where the database cannot be sure whether the relay accepted the message.

### 23.3. Transaction boundaries must be clear with Spring AOP

Invoke transactional methods through the proper Spring bean/proxy. Avoid assuming an internal self-call to a `@Transactional` method within the same class always opens a new transaction.

## 24. Crash Windows and Duplicate Risk

Table of failure points:

| When worker dies | What is in the database? | What may SMTP have done? | Consequence |
| --- | --- | --- | --- |
| Before claim commit | Job still eligible | Not sent | Another worker can claim |
| After claim commit, before build | PROCESSING | Not sent | Recovered after lease |
| During render/prepare | PROCESSING | Not sent if send wasn't called | Retry/failed per error |
| Before SMTP connect | PROCESSING | Usually not transmitted | May retry after verification |
| During SMTP DATA | PROCESSING | Unclear if relay accepted | Duplicate risk |
| After relay accept, before SENT update | PROCESSING | Likely sent | Retrying can duplicate |
| After SENT update commits | SENT | Caller observed submit success | Outbox does not retry in this state |

### 24.1. Distributed locks cannot eliminate crash windows

Locks only reduce concurrent processing. They cannot merge a database update and SMTP relay acceptance into one atomic commit.

### 24.2. Define acceptable retry tolerance

Low-stakes notifications may tolerate a tiny duplicate probability; payment or security emails may require reconciliation or manual intervention when outcomes are unclear.

### 24.3. Exactly-once processing vs. exactly-once external effect

Even if only one worker picks up a job at a time, the same job can still be reprocessed after a crash. Thus **at-least-once processing** and **best-effort deduplication** are usually more realistic goals.

## 25. Idempotency in the Mail Outbox

To avoid creating multiple send intents for the same business event, use a unique key:

~~~text
business_event_id = ORDER_CONFIRMED:ORDER-1001:VERSION-2
mail_kind         = order_confirmation
recipient_ref     = customer-42
~~~

Define a domain-appropriate unique constraint:

~~~sql
CREATE UNIQUE INDEX ux_mail_business_intent
ON mail_outbox(business_event_id, mail_kind, recipient_key);
~~~

This example assumes the table includes **business_event_id** and **recipient_key** columns per the application schema. It illustrates **business-intent idempotency**, not SQL meant to run verbatim against the simplified schema in section 6.

### 25.1. Idempotent enqueueing

If an event listener receives the same event multiple times, the unique key prevents inserting two outbox rows for the same send intent.

### 25.2. Does not automatically guarantee SMTP idempotency

A unique index stops creating multiple jobs, but does not stop a single job from having multiple send attempts after timeouts or crashes.

### 25.3. Message-ID is not an SMTP idempotency key

A MIME **Message-ID** helps tracing and some client threading, but standard SMTP relays have no contract to reject messages sharing a `Message-ID`. Never use this header in place of a duplicate-handling policy.

## 26. SMTP Errors and Retry Strategies

Even a worker holding a valid lock must classify errors.

| Error category | Example | Handling direction |
| --- | --- | --- |
| **Invalid address** | Malformed recipient syntax | FAILED/DATA_ERROR, do not retry blindly |
| **Missing attachment** | Resource does not exist | Fix source or fail permanently |
| **AUTH error** | 535 invalid credentials | Stop rapid retries, fix account |
| **TLS error** | Invalid certificate/hostname | Fix config, never bypass TLS |
| **SMTP temporary** | Certain 421/450 replies | RETRY_WAIT with backoff |
| **Provider throttling** | Rate limit/quota | Throttle, backoff |
| **Permanent rejection** | Appropriate 5xx reply | Classify by enhanced status code |
| **Timeout before connect** | Could not open connection | Bounded retry |
| **Timeout after DATA** | No final reply received | UNKNOWN_OUTCOME/reconcile |
| **Worker crash** | Lease expired | Recovery policy based on certainty |

### 26.1. Do not treat all 4xx/5xx identically

A 550 may stem from a nonexistent recipient or sender policy; a 421 may mean the provider is temporarily unavailable. Classify using full SMTP reply/cause details.

### 26.2. Bounded retries

Design:

- `maxAttempts`.
- Exponential backoff.
- Jitter.
- `nextAttemptAt`.
- Deadlines/TTL per mail kind.
- Terminal FAILED/dead-letter.
- Manual reconciliation for ambiguous outcomes.

### 26.3. Retrying does not depend on keeping the lock

After updating `RETRY_WAIT` and cleanly releasing ownership, another worker can claim the job when `nextAttemptAt` arrives. Never hold locks across multi-minute backoffs.

## 27. Updating RETRY_WAIT or FAILED Using Tokens

Conceptual example:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :next_attempt_at,
    last_error_category = :category,
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

For terminal failures, transition **status = FAILED** under a similar policy.

### 27.1. Never update by ID alone

A stale worker must never overwrite `SENT` or another worker's newer `PROCESSING` version with `RETRY_WAIT`.

### 27.2. Zero-row updates require logging/metrics

If the lease was lost, never issue an unconditional UPDATE to "fix the state". Record `lost_ownership` and let recovery/the state machine handle it.

### 27.3. UNKNOWN_OUTCOME needs its own policy

Do not blindly turn every transport error into `RETRY_WAIT`. Whenever the SMTP relay might have accepted the message, weigh reconciliation and duplicate risk.

## 28. Schedulers Must Not Claim Beyond Capacity

A system with 10 workers where the SMTP provider allows only 5 concurrent connections needs:

- Bounded worker threads.
- Bounded queue capacity.
- Rate limits per provider/account/tenant.
- Batch claims sized to genuinely free slots.
- No leases held on hundreds of unstarted jobs.

### 28.1. Global scheduler locks are not rate limiters

A scheduler lock only prevents concurrent executions; it does not cap SMTP messages per second inside a batch.

### 28.2. Distributed rate limits need clear scopes

If each node allows 10 emails/sec across 5 nodes, total traffic hits 50 emails/sec. If the provider quota is 10 system-wide, use a shared budget/token bucket or partitioned capacity.

### 28.3. Provider-specific concurrency

With multiple SMTP providers, workers may route per provider/account, each with distinct quotas. Align claiming and rate limiting to the actual quota scopes rather than assuming one global lock suffices.

## 29. Lock Contention and Throughput

If a global ShedLock forces only one node to send all mail per tick, the remaining nodes sit idle or skip scheduler runs.

~~~text
3 application nodes
     |
     +-- 1 node holds global lock and sends 100 mails
     +-- 2 nodes skip
~~~

With atomic row claiming:

~~~text
3 application nodes
     |
     +-- Node A claims jobs 1..10
     +-- Node B claims jobs 11..20
     +-- Node C claims jobs 21..30
~~~

### 29.1. Conditional horizontal scaling

Per-row claiming lets multiple nodes scale throughput as long as the database and SMTP provider have capacity. It does not bypass SMTP quotas or bandwidth/attachment constraints.

### 29.2. Global locks can still be useful

Short coordination tasks, such as computing cluster-wide quotas or running periodic reconciliation, may use a scheduler lock to avoid duplicating administrative work.

### 29.3. Avoid creating one lock per recipient unnecessarily

Per-job ownership is handled efficiently by database row claiming. Creating Redis locks/keys for millions of emails adds cost and complexity without proportional correctness gains.

## 30. Avoiding Clock Skew and Time Drift

In distributed systems, Node A can run seconds ahead of Node B due to clock drift.

### 30.1. DB-based leases

For claim/release in PostgreSQL, using SQL **now()** to compare `claim_until` reduces reliance on individual node clocks.

### 30.2. ShedLock usingDbTime

Configuring DB time when supported by the provider keeps all nodes aligned on expiration timestamps via one shared source.

### 30.3. Redis TTLs

Redis manages TTLs server-side, yet applications still have to handle network delays, pauses, and uncertainty about whether a lock is still held.

### 30.4. Never subtract System.nanoTime across two nodes

`System.nanoTime` measures elapsed time within a single JVM, not wall-clock timestamps for comparing leases across machines. Use clocks/timestamps aligned with the backing store.

## 31. Monitoring and Metrics for Distributed Locks

Suggested metrics:

| Metric | Meaning |
| --- | --- |
| **mail.scheduler.lock.acquired** | Successful scheduler lock acquisitions |
| **mail.scheduler.lock.skipped** | Scheduled runs skipped because lock was busy |
| **mail.outbox.claimed** | Jobs successfully claimed |
| **mail.outbox.claim.conflicts** | Claims/updates that lost ownership |
| **mail.outbox.expired_leases** | PROCESSING jobs past `claim_until` |
| **mail.outbox.pending** | Due PENDING/RETRY_WAIT jobs |
| **mail.outbox.oldest_pending_age** | Age of the oldest waiting job |
| **mail.worker.active** | Workers currently sending |
| **mail.worker.lease_renew.failures** | Rejected/failed heartbeats |
| **mail.smtp.submit.attempts** | Actual SMTP attempts |
| **mail.smtp.submit.call.duration** | Send call duration |
| **mail.outbox.unknown_outcomes** | Ambiguous SMTP outcomes |
| **mail.outbox.terminal_failures** | Terminal failed jobs |
| **mail.outbox.recovered_jobs** | Jobs reclaimed after lease expiry |

Metric names are application-defined; do not assume Spring Framework Mail or ShedLock exports all of these automatically.

### 31.1. Separate lock metrics from SMTP metrics

A claimed job does not equal an SMTP send. A send timeout can happen despite a clean claim; a skipped scheduler run does not mean emails were lost.

### 31.2. Low-cardinality labels

You may use **worker_pool**, **mail_kind**, **outcome**, and **provider_alias** when bounded.

Never put recipients, `mailEventId`, `claimToken`, UUID tokens, or raw exception messages into metric labels.

### 31.3. Structured logs per job

Example:

~~~text
event=mail.outbox.claimed
mailEventId=mail-42
ownerAlias=worker-pool-a
claimVersion=8
claimUntil=...
attempt=2
~~~

Event IDs may appear in access-controlled logs; there is no need to log email bodies or credentials.

## 32. Dashboards and Alerts

A worker dashboard can track:

1. Pending job count and oldest pending age.
2. PROCESSING count and leases nearing expiration.
3. Expired lease counts.
4. Claim and SMTP submit throughput.
5. SMTP success/failure/unknown ratios.
6. Skipped lock acquisition counts.
7. p95/p99 send latency.
8. Frequency of lost ownership/fencing failures.
9. Retry backlogs and time-to-relay acceptance.
10. Worker concurrency load and provider quotas.

### 32.1. Alert on rising expired leases

If `claim_until` repeatedly expires before jobs finish, batches may be too big, SMTP timeouts too high, workers pausing, or renewals failing.

### 32.2. Alert on high pending age

Pending counts may look low while one critical email sits stuck for hours. **Oldest pending age** catches isolated stalls and starved jobs.

### 32.3. Skipped locks are not always an incident

In a multi-node ShedLock setup, skipping scheduled runs because another node holds the lock is normal. What matters is that backlogs still clear within SLA.

### 32.4. Alert on unknown outcomes

If many attempts lose responses after DATA, investigate network/provider issues and duplicate risks rather than simply increasing retry counts.

## 33. Concurrency Testing With Multiple Workers

Single-worker unit tests do not prove atomic claiming works when two nodes run concurrently. You need integration tests against a database with matching semantics.

A scenario:

~~~text
Prepare 100 PENDING outbox rows
Start worker A and B concurrently
Both call claimBatch in separate transactions
Collect claimed IDs from each
Assert no overlap between A and B
Assert each claimed row has valid token/version
~~~

### 33.1. Use the same database engine in tests

If production uses PostgreSQL **FOR UPDATE SKIP LOCKED**, test against real PostgreSQL in a controlled environment such as Testcontainers, because H2 or mock JDBC may not match lock semantics.

### 33.2. Barriers to create real contention

Use `CountDownLatch`/`CyclicBarrier` so two workers start nearly simultaneously instead of running sequentially and pretending races were tested.

### 33.3. Real SMTP is unnecessary in concurrency tests

Mock `JavaMailSender` or use a fake transport to verify non-overlapping claims. Only use an SMTP capture server when testing network semantics.

### 33.4. What to assert?

- Each claimed job has one valid owner/version.
- No two active claims hold the same row at the same epoch/version.
- While one transaction is uncommitted, another worker skips the locked row.
- After commit, states and leases match expectations.
- Updates with stale tokens affect 0 rows.

**Never claim this test proves exactly-once SMTP**, because the crash window sits outside row claiming.

## 34. Testing Crashes and Lease Expiration

A matrix:

| Scenario | Expectation |
| --- | --- |
| Worker dies before claim commit | Row stays eligible |
| Worker dies after claim commit, before send | Recovered after lease expiry |
| Worker processing, lease valid | Other workers cannot claim |
| Worker pauses past lease | Job can be reclaimed; old owner's state update is rejected |
| Worker renews validly | `claim_until` extended |
| Worker renews with wrong token | 0 rows affected |
| Worker sends successfully, valid SENT update | Job transitions to SENT |
| Worker sends successfully after lease expired | Old owner update rejected; duplicate risk noted |
| Worker fails temporarily | `RETRY_WAIT` and `nextAttemptAt` |
| Worker hits permanent error | `FAILED` per policy |
| Timeout after DATA | `UNKNOWN_OUTCOME`/reconcile |
| Scheduler lock unavailable | Execution skipped, no duplicate jobs dispatched |

### 34.1. Testing stale ownership

1. A claims row and gets version 1.
2. Expire the lease in the test using DB time or fixture timestamps.
3. B reclaims and gets version 2.
4. A calls `markSent` with version 1.
5. Assert `affectedRows = 0`.
6. B can update as the valid owner.

### 34.2. Testing lease renewal

A renewing before expiration succeeds. B cannot claim while the lease remains valid. Once A loses ownership, renewal must fail.

### 34.3. Testing the SMTP duplicate window with a fake

Have a fake mail transport report submission completed, then simulate a crash before the SENT update. After lease expiry, recovery may resend. The test should prove the system recognizes and models the risk rather than claiming duplicates are impossible.

## 35. Testing ShedLock Across Multiple Scheduler Instances

To verify scheduler-level locking:

- Two application contexts sharing the same ShedLock table.
- Same lock name and provider store.
- Tasks using barriers/latches to create overlap.
- Verify only one task runs while the lock is valid.
- Verify the non-holding task skips per expected behavior.
- Simulate node death or `lockAtMostFor` expiration.
- Verify the second task can execute on a subsequent schedule tick.
- Verify clocks and ensure `lockAtMostFor` is not too short.

### 35.1. Do not test only annotation presence

A reflection test checking `@SchedulerLock` does not prove lock-store connectivity, AOP proxies, and scheduling actually coordinate across two nodes.

### 35.2. Avoid Thread.sleep with tight absolute thresholds

Tests relying on sleeping 100 ms and asserting exact race orderings flake in CI. Use latches, controlled clocks, and generous safety margins.

### 35.3. Verify method calls go through the proxy

If a test directly calls a method on a manually instantiated `new` object, scheduler locking integration is bypassed. Tests must invoke via the Spring context/proxy.

## 36. Testing Database and Redis Failures

When the lock store is unavailable:

- Workers must never assume exclusivity.
- Schedulers may skip or fail per policy.
- Outbox state remains the recovery source.
- Errors must be observable.
- Never fall back to unlocked sending if that introduces duplicate risk.

### 36.1. Database unavailable

If rows cannot be claimed, workers **must never call SMTP** on rows that were merely read without confirmed ownership.

### 36.2. Lock provider unavailable

If ShedLock fails to acquire because the store is down, a naive "fail open" policy lets all nodes run together. Define an explicit failure policy that refuses exclusive work when locking cannot be proven.

### 36.3. Redis failover

For Redis locks, test TTLs, release tokens, renewals, and an old owner continuing to run. Let test results drive real ownership/recovery design rather than stopping after seeing `SET NX PX` return OK.

## 37. Tuning Worker Count and Lease Duration

Related parameters:

| Parameter | Impact |
| --- | --- |
| **Worker threads** | Concurrent SMTP attempts |
| **Batch size** | Jobs claimed per round |
| **Lease duration** | Valid ownership window |
| **Heartbeat interval** | Lease renewal frequency |
| **SMTP timeouts** | Network operation wait limits |
| **Retry backoff** | Load during provider errors |
| **Schedule interval** | Discovery latency for new jobs |
| **Provider rate limit** | Throughput ceiling |
| **Oldest pending SLA** | Acceptable business delay |

### 37.1. Leases must not be too short

If p99 send time is 20 seconds, batches hold multiple messages, or workers can pause, a 5-second lease triggers unwanted reclaims.

### 37.2. Overly long leases are also harmful

If a worker dies right after claiming with a 1-hour lease, the job sits stuck for an hour before recovery. Base leases on worst-case runtimes and heartbeats instead of huge timeouts.

### 37.3. Heartbeats are a trade-off

Heartbeats extend leases during normal work but add DB/Redis I/O. They do not strictly prevent duplicate side effects; pair them with watchdogs, deadlines, and state transitions.

### 37.4. Smaller batches can improve effective throughput

When each batch claims more work than finishes before expiration, the system suffers reclaims, duplicates, and contention. Batches sized to capacity outperform oversized batches.

## 38. Comparing the Strategies

| Criterion | ShedLock scheduler | DB row claim SKIP LOCKED | Redis lease |
| --- | --- | --- | --- |
| Typical scope | One scheduled execution | Individual mail job | Per lock key |
| Has job history? | No | Stored in outbox | Not built in |
| Multiple workers handle distinct jobs? | No if locking whole dispatcher | Yes | Yes if keyed per job, with management overhead |
| Crash recovery? | After lock timeout | After lease expiry/recovery | After TTL |
| Uses DB transactions? | Separate lock store | Yes, short claim | Outside DB transactions |
| Checks stale owners? | Must build separately | Token/version in state update | Token + fencing if target supports it |
| Exactly-once SMTP? | No | No | No |
| Best fit when | Single scheduler task | Parallel outbox workers | Dedicated coordination with Redis |
| Source of truth for SENT/RETRY? | No | Outbox database | No |

### 38.1. No single solution fits every system

Low-volume apps with a short cron batch can start with ShedLock. High-load transactional systems typically need an outbox and atomic per-job claims. Redis fits when already present for specific use cases, though it is not simpler if business state lives in SQL.

### 38.2. Choose for correctness, not library name

What matters is testing your invariants: only the valid owner updates rows, nothing sends before commit, no jobs vanish after crashes, retries obey policy, and unknown outcomes are visible.

## 39. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Running plain `@Scheduled` on every node | Same job read and double-sent | Distributed coordination |
| Using `synchronized` across JVMs | Fails to lock other nodes | Shared DB/lock store |
| `SELECT PENDING` then sending directly | Race condition | Atomic claim |
| `UPDATE PROCESSING` without `WHERE status` | Multiple owners succeed | Conditional update + affected rows |
| Claiming without storing token/version | Stale worker can overwrite | Owner tokens/fencing |
| Holding transactions during SMTP send | Long row locks/DB connections | Claim/commit before sending |
| No lease expiration | Jobs stay stuck after crash | Leases/recovery |
| Overly short leases | Two workers send concurrently | Bound execution/renewal |
| Batches exceeding capacity | Many leases expire before processing | Claim close to send time |
| ShedLock `lockAtMostFor` too small | Scheduled executions overlap | Size duration appropriately |
| Using ShedLock instead of a durable outbox | Mail lost on crash | Durable outbox/broker |
| Redis `DEL` without checking token | Deletes new owner's lock | Compare-and-delete |
| Redis locks without TTL | System stalls when owner dies | TTLs and recovery |
| Assuming Redlock gives exactly-once | Stale owner/SMTP window remains | Fencing/reconciliation |
| Marking SENT on async enqueue | SMTP has not run yet | Ack only on actual submit result |
| Retrying every timeout immediately | Duplicates after DATA | `UNKNOWN_OUTCOME` policy |
| Treating `Message-ID` as an idempotency guarantee | Relay may accept repeats | Domain dedup/reconciliation |
| Infinite heartbeats | Hung worker holds lease forever | Overall deadline/watchdog |
| Putting job IDs in metric labels | High cardinality/PII leaks | Low-cardinality tags |
| Not testing concurrency on real DB | Misses real lock semantics | PostgreSQL integration tests |
| Failing open when lock store fails | Triggers duplicates | Refuse to send without ownership |

## 40. Frequently Asked Questions

**1. Is a distributed lock needed when running only a single node?**

If you are certain only one process runs with no multi-thread contention, a distributed scheduler lock may not be needed yet. However, atomic claiming and a state machine still help across retries, restarts, and future scaling.

**2. Does `@Scheduled` automatically guarantee only one node runs?**

No. Each instance runs its own scheduler.

**3. Can `synchronized` solve this?**

Not across separate JVMs. It only locks threads sharing a monitor inside one process.

**4. What is ShedLock used for?**

Typically to prevent identically named scheduled tasks from running concurrently across instances sharing a lock store.

**5. Does ShedLock automatically queue skipped scheduled runs?**

Do not assume so. Runs failing to acquire the lock are normally skipped, not queued for later execution.

**6. Does `lockAtMostFor` cancel the running method upon expiration?**

No. It is how long the lock entry is kept in the store, not a cancellation signal for the running method.

**7. Why doesn't ShedLock replace outbox claiming?**

A scheduler lock may protect only the fetch/enqueue step. If jobs are not durably claimed, another worker can still double-process them once the lock releases.

**8. What does `SKIP LOCKED` do?**

It lets a transaction grab rows not locked by another transaction, ideal for multiple workers claiming queued jobs.

**9. Why not hold a `SELECT FOR UPDATE` lock until sending finishes?**

Because SMTP is a potentially slow network side effect that cannot roll back with a DB transaction; holding transactions open causes contention and timeouts.

**10. What is a lease?**

Time-bounded ownership. Once a lease expires, another worker can reclaim the job per policy.

**11. Why are `claim_token` and `claim_version` needed?**

To identify the current owner and block stale owners from mutating state after a job was reclaimed.

**12. Does fencing completely prevent duplicate SMTP sends?**

No. Standard SMTP relays do not validate outbox tokens/versions; fencing only works at targets that enforce those checks.

**13. Should leases use heartbeats?**

Yes for long-running jobs making verifiable progress. Renewals must check owner/token/version and must not run forever if hung.

**14. Is Redis `SET NX PX` safe enough?**

It provides atomic acquisition with TTL on one Redis instance, yet still faces failover, stale owners, and external side-effect hazards. Understand the fault model and recovery policy.

**15. Why not release a Redis lock with a direct `DEL`?**

Because the lock's TTL may have expired and another owner may now hold it. Compare-and-delete by token prevents deleting the new owner's lock.

**16. Does Redlock guarantee exactly-once email delivery?**

No. It cannot merge SMTP submission into one atomic transaction with your database/outbox.

**17. Does an outbox prevent duplicate emails by itself?**

It durably persists send intents and cuts duplicate events via unique keys, yet if SMTP accepts and the worker crashes before saving state, recovery retries can still double-send.

**18. Is `Message-ID` an idempotency key honored by SMTP?**

No universal guarantee exists. Never rely on `Message-ID` to prove a relay will drop duplicate messages.

**19. Does a successful email send mean it reached the inbox?**

No. That only reflects client-side SMTP submission; delivery, bounces, and reads require separate downstream signals.

**20. What if a lease expires mid-send?**

Another worker can reclaim the job while the old worker is still sending; CAS protects the DB update without undoing SMTP. Tune leases, heartbeats, deadlines, and duplicate policies carefully.

**21. How large should batches be?**

Size them to concurrency, per-send duration, lease window, and quotas—never claim more than finishes within the ownership window.

**22. With multiple SMTP providers, should locks be per provider?**

Per-job ownership stays tied to the mail event; quotas and concurrency can be scoped per provider/account. Never use global locks instead of rate limiters when quotas are independent.

**23. Can Redis locks and a DB outbox be combined?**

Yes, though coordinating two systems adds inconsistency edge cases. When a relational DB already holds the outbox, atomic row claiming is usually a simpler starting point.

**24. Is testing concurrency with H2 enough?**

Never assume parity with PostgreSQL `SKIP LOCKED`. Use real PostgreSQL in integration tests whenever production relies on those semantics.

**25. What should we alert on to catch broken distributed locks?**

Rising expired leases, lost ownership, pending age, lock acquisition failures, retry backlogs, unknown outcomes, and divergence between claimed jobs and SMTP attempts/completions.

## 41. Takeaways on Distributed Locks for Mail Workers

**Distributed locks coordinate multiple processes—they do not guarantee exactly-once email delivery.** For scheduled Spring Framework Mail workloads, define the exact scope needing exclusivity: **ShedLock** works well to keep nodes from running the same scheduled task concurrently, whereas **atomic per-job claiming** via database row locks and conditional updates fits better when multiple workers process distinct outbox jobs in parallel.

With PostgreSQL, a short transaction using **FOR UPDATE SKIP LOCKED** selects and claims jobs, committing before calling **JavaMailSender.send(...)**. Store **`claim_token`, `claim_version`, and `claim_until`**, checking ownership on renewals and `SENT`/`RETRY_WAIT`/`FAILED` updates. When leases expire, stale workers must have state updates rejected—yet never assume fencing prevents an SMTP relay from receiving an already-dispatched message.

With Redis, locks require atomic acquisition, TTLs, and token-checked release while still handling worker pauses, failover, and stale ownership. Regardless of mechanism, configure timeouts, batch sizes, concurrency, retry/backoff, recovery, and telemetry properly. Above all, **SMTP may accept `DATA` before a worker crashes prior to writing `SENT`**, so systems need an **`UNKNOWN_OUTCOME`** policy, idempotent business events, and reconciliation when needed.

The right target is not "having a lock guarantees zero duplicates", but **preventing concurrent work on the same job during normal operation, recovering cleanly after failures, protecting state ownership, and transparently managing duplicate side-effect risk**. A sound design is measurable, testable, and scalable as worker counts grow.
