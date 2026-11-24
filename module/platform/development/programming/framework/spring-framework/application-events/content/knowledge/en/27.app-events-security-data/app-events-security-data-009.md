# Retention-Based Data Deletion in Spring Application Events Systems

## 1. The Problem: Data Has Expired Yet Remains in the Event Pipeline

A Spring application may store customer information in a primary database while publishing an `ApplicationEvent` to update caches, create audit records, sync search indexes, forward events to Kafka/RabbitMQ, write to a transactional outbox, or send notifications. After some time, the original record is no longer needed or policy requires deletion. Deleting only the row in the primary database can leave copies of the data lingering elsewhere.

Example:

```text
CustomerService updates profile
      |
      +--> relational DB: email, profile
      |
      +--> publishEvent(ProfileChanged)
                  |
                  +--> cache listener: serialized profile
                  +--> search listener: search document
                  +--> analytics listener: event history
                  +--> outbox -> message broker -> consumer DB
                  +--> logs/traces/DLQ/backups

After 90 days under a HYPOTHETICAL policy:
      DELETE FROM profile WHERE expired ...
      |
      +--> primary DB deleted
      +--> cache, broker log, analytics, backups may still retain copies
```

**Retention-based deletion** is the process of defining which data is kept, for how long, for what purpose, when it becomes eligible for deletion, where it must be deleted, and what evidence proves execution. For event-driven systems, this is a **cross-system data lifecycle problem**, not just a single SQL statement or `@EventListener`.

Core principles:

1. **Data minimization first:** do not put sensitive data into general events when consumers do not genuinely need it.
2. **Predefined retention policies:** never pick day counts by guesswork; durations depend on data type, purpose, contracts, and applicable regulations.
3. **Delete according to legal basis and scope:** expired data may still need to be retained under valid legal obligations or legal holds.
4. **Delete or invalidate all relevant copies:** databases, caches, search indexes, outboxes, queues, dead-letter queues, logs, object storage, analytics, and backups.
5. **Auditable without re-storing PII:** record minimal metadata proving the deletion occurred, without writing the sensitive payload back into audit logs.
6. **Resilient:** deleting the primary source and propagating deletion requests to consumers must have tracking, retries, idempotency, and asynchronous failure handling.

## 2. Distinguishing Retention, Erasure Requests, TTLs, and Domain Events

| Term | Meaning | Common Pitfall |
| --- | --- | --- |
| Retention policy | Rule defining retention duration and deletion conditions | Using the same TTL for every data type |
| Retention expiration | A record has passed the point of eligibility for deletion | Deleting records that still have a valid hold/basis |
| Erasure request | Deletion request under specific rights or workflows | Treating every request as instant deletion without checking conditions/exceptions |
| Cache TTL | How long a cache entry lives | Mistaking cache TTL for deletion in DB/brokers |
| Logical deletion | Setting `deleted=true` or `deletedAt` | PII remains in storage, merely hidden from UI |
| Physical deletion | Deleting or invalidating the actual stored data | Forgetting indexes, replicas, logs, backups, object storage |
| Crypto-erasure | Disabling encryption keys so data can no longer be decrypted per architecture | Failing to check plaintext copies, key backups, or other replicas |
| Deletion event | Signal that "a record/subject was deleted" for other systems | Mistaking publishing an event for proof that consumers succeeded |
| Tombstone in compacted logs | Marker with a key and null value under log-compaction semantics | Assuming tombstones immediately erase all historical copies |

A `ProfileErased` or `RetentionExpired` event reports an **accepted change**; it is not a physical guarantee that every sensitive byte has vanished from every node and backup. Align event names to exact semantics:

- `ErasureRequested`: the request has been recorded, not necessarily completed.
- `PrimaryRecordErased`: the record was deleted in the primary datastore.
- `ConsumerCopyErased`: a consumer reported deleting its copy.
- `ErasureCompleted`: the coordinator verified all policy-required steps.

Never emit `ErasureCompleted` right after calling `repository.delete(...)`.

## 3. Define Retention Policies Before Writing Code

Policies should be governed via versioned documentation and configuration data, rather than scattering `30`, `90`, and `365` days across multiple listeners.

Sample policy table **for illustration only**:

| Data Class | Purpose | Retention Trigger | Deletion Condition | Additional Requirements |
| --- | --- | --- | --- | --- |
| Temporary user profile | Provide feature | End of usage / account closure | `expiresAt <= now`, no valid hold | Clear related caches and indexes |
| Confirmed outbox event | Event delivery | `deliveredAt` | Delivered + past policy retry/audit buffer | Never delete pending events |
| Application logs | Diagnostics | Log creation time | Past log retention limit | Never log secrets/PII in the first place |
| Dead-letter messages | Error investigation | DLQ entry time | Past allowed limit or error resolved | Restrict payload viewing rights |
| Sessions/caches | Serve requests | Session expiry | TTL/explicit invalidation | Never use TTL instead of deleting source data |
| Backups | Disaster recovery | Snapshot timestamp | Approved backup lifecycle | Controls preventing deleted data resurrection |

Each category must specify a **data owner**, storage locations, retention basis, policy approver, policy version, retention start, how `expiresAt` is calculated, exceptions/holds, storage targets, and deletion SLA.

Distinguish three timestamps:

1. **`createdAt`**: when the data was created.
2. **`retentionStartsAt`**: when the retention clock begins; e.g., contract termination or ticket closure, not necessarily equal to `createdAt`.
3. **`expiresAt`**: the calculated and stored/evaluated point when the record becomes eligible for deletion under the active policy.

Use `Instant`/UTC in models to avoid daylight-saving and timezone-conversion bugs; if a policy relies on calendar dates in a specific country, define the exact `ZoneId` and calendar rules when computing `expiresAt` before converting to `Instant`. Never rely on arbitrary JVM local time as a policy basis without tests.

### Legal Considerations and Exceptions

The `storage limitation` principle in GDPR is an international example of limiting personal-data retention to its purpose; the right to erasure carries conditions and exceptions such as legal obligations or legal claims. **Do not assume every Spring app is governed by GDPR, do not invent 30/90-day limits from GDPR, and do not treat a legal hold flipped by any employee as grounds for indefinite retention.** In practice, identify the laws, contracts, and approved policies for the organization, jurisdiction, and data categories handled.

Legal holds require clear justification, scope, approver, review date, revocation capability, and secure audit trails. In code, a boolean `legal_hold` flag is only a minimal model; real systems must record controlled justification/basis and evaluate whether fields outside the hold scope can still be erased.

## 4. Inventory Every Copy Spawned by Events

Once an event is published, identify who can receive and persist copies:

```text
Source DB (original PII)
  |
  +--> Spring @EventListener in the same JVM
  |       +--> local cache
  |       +--> secondary index
  |       +--> file/object storage
  |
  +--> transactional outbox table
  |       +--> relay -> Kafka/RabbitMQ
  |                        +--> consumer database
  |                        +--> retry topic / dead-letter queue
  |                        +--> analytics / data lake
  |
  +--> logging, tracing, APM, exception reports
  |
  +--> replicas, snapshots, backups
```

For each storage location, document:

- How data is stored: plaintext, encrypted field, tokenized reference, hash, or event ID?
- Does it contain direct PII or data linkable to an individual?
- Who manages retention and access controls?
- Can it delete by `subjectRef`/`eventId`, or only by partition/time?
- When the primary record is deleted, must consumers delete too? Who tracks acknowledgements?
- On backup restore or topic replay, how do we prevent **re-ingesting deleted data**?
- Do DLQs/traces/logs retain errors carrying raw payloads?

Every payload duplication increases data-governance cost. If a consumer needs only `customerRef` and `changedFields`, avoid sending a whole `CustomerEntity` with email, address, or credentials. Even a UUID can be indirect personal data if linkable, so it still requires retention and access controls.

## 5. Designing a Retention Deletion Workflow with Application Events

A safe flow can be structured as follows:

```text
Retention policy service / scheduler
        |
        v
Find eligible records by expires_at <= now
        |
        +-- Ineligible? => skip
        +-- Valid legal hold? => skip / review
        |
        v
Transactional deletion unit
        |
        +-- Re-check expiry/hold directly in DELETE
        +-- Delete or anonymize record
        +-- Write outbox erasure notification (if durability required)
        |
        v
COMMIT
        |
        +-- In-process AFTER_COMMIT listener:
        |     invalidate cache / metrics / local update
        |
        +-- Outbox relay:
              send erase command/event to consumers
              await/track acknowledgements
              retry, DLQ, alert if required
        |
        v
Verify required copies erased
        |
        +-- update minimal erasure ledger / evidence
        +-- enforce restore and replay suppression
```

### Re-Check at Deletion Time

Do not merely run `SELECT ref FROM ... WHERE expires_at <= ?` and then delete solely by ID. Between reading and deleting, another transaction might extend retention, place a legal hold, or update policy. Embed the conditions in the `DELETE` statement itself, for example:

```sql
DELETE FROM private_profiles
WHERE ref = ?
  AND expires_at <= ?
  AND legal_hold = FALSE;
```

The actual deleted row count (affected rows) is the proof of change. If `affectedRows = 0`, another worker may have deleted it, extended it, or placed a hold; never publish `ProfileErased` as if deletion succeeded.

With multiple workers, use proper claiming/locking/leasing, batch bounds, and idempotent protection. Never hold a giant `SELECT` open inside a multi-hour transaction.

### Batch Cleanup

Instead of one massive delete holding locks and causing huge replication lag, use bounded batches, short transactions, backpressure, and monitoring. For SQL using `SKIP LOCKED` or row-claiming variants, syntax and semantics depend on the database. Never copy vendor-specific SQL across H2/PostgreSQL/MySQL without testing compatibility and isolation.

When foreign keys/cascades are complex, define explicit deletion ordering and dependency handling. Never leave "orphans" holding PII in child tables. With JPA, remember that bulk deletes like `JpaRepository.deleteAllInBatch(...)` **do not trigger JPA entity lifecycle callbacks** and may bypass cascade semantics; never rely on `@PreRemove` to emit deletion events during bulk deletes.

## 6. Spring: @Scheduled, @TransactionalEventListener, and Transaction Boundaries

### 6.1. @Scheduled Only Triggers a Job; It Does Not Delete Data Itself

Spring provides `@Scheduled` paired with `@EnableScheduling`. Sketch:

```java
// Illustrative excerpt; requires Spring bean, imports, and @EnableScheduling.
@Scheduled(cron = "0 15 2 * * *", zone = "UTC")
public void eraseExpired() {
    retentionService.cleanup(Instant.now());
}
```

Spring cron expressions have **six fields**; the example runs daily at 02:15 UTC. A schedule does not guarantee deletion finishes: jobs can fail, run concurrently across replicas, or miss runs during downtime. Monitor last successful run, backlog, error counts, batch durations, and retry handling.

If multiple instances run with `@EnableScheduling`, every instance can execute the same job. Use leader election, distributed locks, DB claiming, or safe concurrency strategies. Never assume the annotation creates a cluster-wide singleton scheduler.

### 6.2. Transactions and Event Publication Timing

If you delete a record inside a transaction and call `publishEvent(new ProfileErased(...))`, synchronous `@EventListener` methods **may run before commit**; if the transaction rolls back afterward, external side effects do not undo automatically.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is appropriate for reacting **after the associated DB transaction commits successfully**. When the transaction rolls back, this callback does not run. However:

- It does not create a durable queue.
- A crash after commit before the callback runs can drop the external task.
- After commit, a callback error cannot roll back already-committed changes.
- If an after-commit listener needs to **perform additional DB writes**, consider a new transaction (`REQUIRES_NEW` via an appropriate service/proxy), as prior transaction resources may still be bound without committing further writes.

To guarantee downstream systems eventually learn about deletions despite crashes, write a **transactional outbox** *in the same transaction* as the primary deletion. The runnable example below illustrates in-process after-commit behavior for clarity; production outboxes are covered separately.

## 7. Runnable Maven + Java 17 Example: Delete Expired Profiles While Keeping Legal Holds

This example uses **Spring Framework 6.2.8**, `spring-jdbc`, H2 2.3.232, and `TransactionTemplate`. Synthetic data includes three profiles:

- `profile-expired`: expired and **no** legal hold → must be deleted.
- `profile-held`: expired yet **under** legal hold → must not be deleted.
- `profile-future`: not yet expired → must not be deleted.

After deletion succeeds inside the transaction, the program publishes `ProfileErased(opaqueRef, policyCode)`; the `AFTER_COMMIT` listener prints only a notice **containing no ref or email**. A fixed simulated timestamp is used so output does not depend on the actual date run.

This is a demo of deletion decisions, transactions, and application events—**not** a complete system for legal verification, authorization, secure SSD erasure, outboxes, backups, or system auditing.

### 7.1. Structure

```text
retention-erasure-demo/
├── pom.xml
└── src/main/java/demo/RetentionErasureDemo.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>retention-erasure-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.RetentionErasureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/java/demo/RetentionErasureDemo.java

```java
package demo;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class RetentionErasureDemo {

    // Contains no email or any sensitive profile value.
    // opaqueRef must still be protected if identity can be looked up from it.
    public record ProfileErased(String opaqueRef, String policyCode) {}

    public static final class RetentionService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher publisher;

        public RetentionService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.publisher = publisher;
        }

        public int cleanup(Instant now) {
            return transactions.execute(status -> {
                List<String> refs = jdbc.query(
                        "select ref from private_profiles " +
                        "where expires_at <= ? and legal_hold = false " +
                        "order by ref",
                        (rs, n) -> rs.getString("ref"),
                        Timestamp.from(now));

                System.out.println("job: candidates=" + refs.size());

                int deleted = 0;
                for (String ref : refs) {
                    // Re-check expiry/hold directly inside the DELETE operation.
                    int affected = jdbc.update(
                            "delete from private_profiles " +
                            "where ref = ? and expires_at <= ? " +
                            "and legal_hold = false",
                            ref, Timestamp.from(now));

                    if (affected == 1) {
                        deleted++;
                        publisher.publishEvent(
                                new ProfileErased(ref, "RETENTION"));
                    }
                }

                System.out.println("job: deleted=" + deleted);
                return deleted;
            });
        }
    }

    public static final class ErasureObserver {
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onErased(ProfileErased event) {
            // Do not log ref or email in events/DB.
            System.out.println(
                    "listener: deletion committed policy="
                            + event.policyCode());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:retention_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        ErasureObserver erasureObserver() {
            return new ErasureObserver();
        }

        @Bean
        RetentionService retentionService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            return new RetentionService(jdbc, transactions, publisher);
        }
    }

    private static void seed(
            JdbcTemplate jdbc,
            String ref,
            String email,
            String expiry,
            boolean legalHold) {
        jdbc.update(
                "insert into private_profiles " +
                "(ref, email, expires_at, legal_hold) " +
                "values (?, ?, ?, ?)",
                ref, email, Timestamp.from(Instant.parse(expiry)),
                legalHold);
    }

    private static boolean exists(JdbcTemplate jdbc, String ref) {
        Integer count = jdbc.queryForObject(
                "select count(*) from private_profiles where ref = ?",
                Integer.class, ref);
        return count != null && count > 0;
    }

    private static int count(JdbcTemplate jdbc) {
        Integer count = jdbc.queryForObject(
                "select count(*) from private_profiles",
                Integer.class);
        return count == null ? 0 : count;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "create table private_profiles (" +
                    "ref varchar(64) primary key," +
                    "email varchar(255) not null," +
                    "expires_at timestamp not null," +
                    "legal_hold boolean not null)");

            seed(jdbc, "profile-expired",
                    "old@example.invalid",
                    "2025-01-01T00:00:00Z", false);
            seed(jdbc, "profile-held",
                    "held@example.invalid",
                    "2025-02-01T00:00:00Z", true);
            seed(jdbc, "profile-future",
                    "future@example.invalid",
                    "2027-01-01T00:00:00Z", false);

            Instant now = Instant.parse(
                    "2026-11-11T00:00:00Z");

            System.out.println("before: rows=" + count(jdbc));
            int deleted = context.getBean(RetentionService.class)
                    .cleanup(now);
            System.out.println("result: deleted=" + deleted);
            System.out.println("after: rows=" + count(jdbc));
            System.out.println("after: held=" +
                    exists(jdbc, "profile-held") +
                    " future=" + exists(jdbc, "profile-future") +
                    " expired=" + exists(jdbc, "profile-expired"));

            int secondRun = context.getBean(RetentionService.class)
                    .cleanup(now);
            System.out.println("again: deleted=" + secondRun);
        }
    }
}
```

### 7.4. Run and Output

Run from the directory containing `pom.xml`, requiring JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Output printed by the program itself (excluding auxiliary Maven output):

```text
before: rows=3
job: candidates=1
job: deleted=1
listener: deletion committed policy=RETENTION
result: deleted=1
after: rows=2
after: held=true future=true expired=false
job: candidates=0
job: deleted=0
again: deleted=0
```

Explanation:

1. `now` is fixed at `2026-11-11T00:00:00Z`. `profile-expired` has `expires_at` before `now` and `legal_hold=false`, so it is eligible. `profile-held` is also past expiry but its hold is active; `profile-future` has not expired yet.
2. `TransactionTemplate` opens a transaction; `SELECT` retrieves one candidate.
3. `DELETE` reapplies the expiry and hold conditions to reduce the risk of accidental deletion if state changed after selection.
4. `ProfileErased` is published only when `affected == 1`; if deletion did not occur, no erasure is claimed.
5. `@TransactionalEventListener(AFTER_COMMIT)` registers a callback in the transaction. It prints after the transaction commits, **before `cleanup(...)` returns**.
6. Queries outside the transaction confirm exactly two records remain; the held record and unexpired record stay intact.
7. The second cleanup run finds no eligible records and returns 0: the task can rerun without emitting extra events for already-deleted records.
8. Synthetic emails use the `example.invalid` domain; the code never prints email data to stdout. **An opaque reference can still be indirect PII** if linkable to a specific person.

**Demo limitations:** In-process listeners are not crash-durable; there is no batch limit or parallel workers; one transaction spans all candidates; and there is no authorization, policy registry/hold approval, outbox, durable audit, backup deletion, or copy verification. For production, extend according to the following sections.

## 8. Propagation: Deleting Data in Consumers Holding Copies

A robust design is a **state-tracked erasure workflow**:

```text
Primary deletion TX
  ├─ delete profile rows
  ├─ insert erasure_outbox(
  |     erasure_id, subject_ref, policy_version,
  |     request_type, status, created_at)
  └─ COMMIT

Outbox relay
  ├─ send erasure command/event with idempotency key
  ├─ retry/backoff on transient consumer error
  ├─ do not re-emit already-erased PII payload
  └─ enforce deadline/escalation if ack is missing

Consumers
  ├─ cache -> invalidate
  ├─ search index -> delete by scoped ID
  ├─ analytics -> erase/anonymize per policy
  ├─ object storage -> delete/version purge per workflow
  └─ return completion/failure acknowledgement

Erasure coordinator
  ├─ reconcile target list and acknowledgements
  ├─ report incomplete if any consumer still fails
  └─ store minimal evidence after all conditions are verified
```

### An Outbox Does Not Perform Deletion by Itself

A transactional outbox ensures the **notification intent** is saved in the same transaction as the primary DB change. If the process dies after commit, the relay can resume. However, the system does not guarantee a consumer has deleted its copy simply because the relay called the broker, nor does it guarantee exactly-once delivery: if publishing succeeds and the relay crashes before marking delivered, the message can be sent again.

Therefore, consumer erasure handlers must be **idempotent**: receiving the same `erasureId` or `subjectRef + policyVersion` multiple times yields the exact same deleted state without resurrecting data or multiplying unintended side effects.

You must also **delete outbox events according to retention** once enough time has passed for retries and audits. Never delete pending events before delivery lest deletion instructions be lost. If an outbox holds user-linkable identifiers, it has its own data lifecycle too; do not retain it forever merely as evidence.

### Do Not Fan Out New Sensitive Data Inside Erasure Events

Erasure-request events should carry only metadata needed for controlled routing: `erasureId`, opaque subject reference, scope, policy version, and reason code when needed. Never attach full emails, profiles, copies of old events, or credentials to deletion notices. Never put linkable IDs into low-cardinality metric tags.

Send messages only to consumers that actually hold copies needing deletion. Do not broadcast to the whole system if the erasure event itself discloses sensitive information about the subject.

## 9. Broker Retention, Log Compaction, Tombstones, and DLQs

### Kafka Retention Is Not Key-Based Individual Erasure

In Kafka, `cleanup.policy=delete` normally deletes old **log segments** by time/size policy. It is not an API guaranteeing immediate erasure of every message with `customerRef=X` anywhere inside a segment.

`cleanup.policy=compact` retains the latest value per key after compaction; a tombstone (a record with a key and null value) can mark a key for removal from a compacted log. Still:

- Compaction **does not happen instantaneously** when writing a tombstone.
- It does not delete copies in other topics, retry topics, DLQs, consumer databases, backups, or system logs.
- If a PII-bearing event uses a different key or embeds data inside a payload without the erased key, tombstones cannot automatically infer those copies.
- Tombstones have their own retention and cleanup settings, such as `delete.retention.ms`; late consumers/replays must be designed around actual log behavior.
- With `cleanup.policy=delete,compact`, retention and compaction rules apply together per configuration.
- Restoring/replaying old events can recreate a previously deleted record unless consumers check an erasure ledger/version.

Thus, a tombstone is only **one technical component** of retention-based deletion, never complete compliance proof.

### RabbitMQ, Queues, and Dead-Letter Queues

For queues, examine message TTLs, dead-letter retention, redeliveries, consumer retries, and copies created by supporting systems. An "acked" message may already sit in another consumer DB, while a message routed to a DLQ may retain full PII payloads longer than intended.

Establish a policy for failed messages: if expired business events retry endlessly, data lingers in retry queues/DLQs beyond retention limits. If DLQs are purged before investigation finishes, operational failure signals are lost. Solutions require clear prioritization, retention, and quarantine/triage workflows.

## 10. Logs, Traces, Analytics, Object Storage, and Backups

### 10.1. Logs and Observability

A listener might log whole events:

```java
// Do not do this with events containing PII/secrets.
log.info("received {}", event);
```

If the event is a Java `record`, default `toString()` prints all fields; JSON loggers or APMs can serialize via accessors. **Not collecting PII** is a stronger defense than collecting it and trying to redact later. Log only allowlisted schemas, reason codes, classified event types, and operational status codes.

Logs/traces rarely support easy selective deletion of individual records. Minimize data upfront and configure log-system retention. Erasure events themselves must never copy the data being deleted into error messages.

### 10.2. Analytics and Materialized Views

Events written to a data warehouse can remain in history tables, materialized views, CSV exports, snapshots, or dashboards. Policies must specify raw tables, derived tables, whether aggregate metrics remain identifiable, and corresponding erasure/anonymization workflows.

Never assume "statistical aggregates" are automatically anonymous: small groups, joins with external data, or stable identifiers can still re-identify individuals. When data is truly irreversibly anonymized under applicable standards, different rules may apply; verify this rather than slapping on a label.

### 10.3. Object Storage and Versioning

`DELETE object` may delete only the current version or place a delete marker in versioned storage. Account for noncurrent versions, object locks/legal holds, replicas, lifecycle policies, and inventories. If files are retained for legal evidence, follow explicit policy rather than ignoring all deletion requests.

### 10.4. Backups: Deleting from Active Systems Does Not Delete from Snapshots

Backups can be immutable and lack per-subject selective deletion. Practical designs may include:

- Limiting backup retention per approved policy.
- Encrypting backups, restricting access, and logging restores.
- On restore, applying an **erasure/revocation ledger** or replay filter before serving data; never resurrect previously deleted data.
- Enforcing procedures to protect and purge expired data in restored copies per applicable obligations.
- Evaluating crypto-erasure if data is encrypted with keys having independent lifecycles and no remaining plaintext or key copies.

Never promise "deleted from all backups immediately" if storage does not support it; equally, never use backup limitations as an excuse to ignore deletion requirements. Workflows must be reviewed by data owners, privacy/security, and legal under actual policies.

## 11. Soft Delete, Hard Delete, and Idempotency

### Soft Delete

An update:

```sql
UPDATE customer_profile
SET deleted_at = CURRENT_TIMESTAMP
WHERE ref = ?;
```

hides UI display or marks a request, yet **PII remains in the database**. It does not complete physical erasure if policy requires deletion. Scrub sensitive columns or delete rows under an approved workflow.

### Hard Delete

A `DELETE` removes the record from the logical table, yet copies may still remain in transaction logs, replicas, snapshots, and low-level storage. Never infer secure physical erasure on storage hardware solely from a SQL `DELETE`.

### Anonymization and Minimization

Some use cases must keep statistics after removing personal links. Use a vetted anonymization process strong enough for the threat model; simply replacing an email with a hash does not guarantee anonymity if the hash can be brute-forced or linked.

### Idempotent Erasure

Good design treats re-deleting an already-absent record as "already in the desired absent state" when appropriate, rather than failing and retrying infinitely. Still, **success acks** must distinguish between:

- Primary source record is absent.
- Mandatory consumer copies are absent.
- Metadata/evidence has been updated per policy.

An API can return `ALREADY_ABSENT` on repeated deletion requests without recreating data or restarting the entire workflow; permission and scope checks are still required.

## 12. Scheduling and Production Operations

### 12.1. Do Not Delete Too Much in One Transaction

When deleting millions of records, long transactions hold locks, inflate WAL/redo/replication lag, and cause timeouts. Use configurable small batches, persisted checkpoints, short transactions, and per-batch metrics. When executing by partition, verify filters are exact so boundary records are never missed.

### 12.2. Multi-Instance Execution and Contention

Never rely solely on `@Scheduled` across multiple pods assuming only one pod runs. Use distributed locks/leader election, row claiming with `SKIP LOCKED` per DB support, or explicit sharding. Conditional deletes are still needed for concurrent changes. In some workflows, claim and delete must share the same transaction/isolation so two workers never process the same record simultaneously.

### 12.3. Errors and Retries

Distinguish transient errors (database timeout, 503) from permanent errors (permission denied, policy conflict, missing schema). Retry with exponential backoff plus jitter, max attempts, deadlines, and lag monitoring. Never blindly retry an entire batch after non-idempotent notifications have fired; track a stable erasure ID and per-target state.

### 12.4. Metrics

Suggested metrics (not provided automatically by `@EventListener`):

| Metric | Interpretation |
| --- | --- |
| `retention.eligible.count` | Eligible record count at measurement time |
| `retention.deleted.count` | Records deleted in primary DB |
| `retention.held.count` | Expired records deferred due to valid holds |
| `retention.job.duration` | Batch cleanup duration |
| `retention.job.failure` | Execution failures |
| `erasure.outbox.pending` | Erasure requests awaiting relay |
| `erasure.consumer.pending` | Consumers not yet acked |
| `erasure.consumer.failed` | Consumer erasure failures |
| `erasure.oldest.pending.age` | Age of oldest pending request |

Metrics and logs must not use `customerRef`, email, or event ID as **low-cardinality tags**. Use data class, policy code, target system, and outcome from finite sets. Trace/log correlation may need IDs, yet must have proper access control, minimization, and retention.

### 12.5. Prove Effectiveness, Not Just "Deleted" Logs

A proper dashboard tracks **coverage of required targets** and verification evidence. "The job ran" does not mean all copies were deleted. When a consumer stops responding, the dashboard must show `PENDING/FAILED` and escalate rather than marking the whole request complete.

## 13. Testing Retention Policies

Test from domain through infrastructure:

1. **Expired:** record with `expires_at < now`, no hold → eligible.
2. **Exact boundary:** record with `expires_at == now` → matches `<=` convention.
3. **Not yet expired:** `expires_at > now` → not deleted.
4. **Legal hold:** expired record with valid hold → not deleted; verify hold audit/approval.
5. **Concurrent change:** hold enabled or expiry extended before delete → `affectedRows = 0`; no erasure event published.
6. **Actual count:** publish `ProfileErased` only when 1 row is actually deleted; never publish when 0 rows deleted.
7. **Rollback:** delete transaction rolls back → `AFTER_COMMIT` listener does not run; no false "erased" state.
8. **Idempotency:** run cleanup twice → second run deletes nothing more and emits no unwarranted events.
9. **Restart:** crash after commit → outbox event persists for relay recovery; in-memory callbacks alone are insufficient.
10. **Fan-out:** cache, search, warehouse, and object storage deleted per scope; mark complete only after mandatory targets ack.
11. **Tombstone/replay:** Kafka replay/backup restore does not recreate deleted records; test old records across schema versions.
12. **DLQ/logs:** no full PII stored in failure reports or dead-letter payloads beyond policy.
13. **Backups:** test restore procedures and erasure ledgers so deleted users are not resurrected.
14. **Volume:** clean millions of records in batches, monitoring locks/replication lag and resources.
15. **Access control:** prevent unauthorized callers from submitting erasure requests to wipe others' data; minimal auditing.
16. **Clock/timezones:** test UTC, calendar dates, and daylight-saving edge cases when policy uses local calendars.

Meaningful assertions:

```java
// Conceptual snippet for integration tests using matching fixtures.
assertEquals(1, retentionService.cleanup(fixedInstant));
assertFalse(profileExists("profile-expired"));
assertTrue(profileExists("profile-held"));
assertTrue(profileExists("profile-future"));
assertEquals(0, retentionService.cleanup(fixedInstant));
```

This snippet requires appropriate classes and test fixtures; it is not a standalone program. For multi-service tests, test end-to-end against real brokers/storage and real acknowledgement tracking.

## 14. Common Mistakes to Avoid

**Mistake 1 — Deleting the primary source and assuming all data is gone.** Events may have copied data into caches, logs, DLQs, analytics, and backups.

**Mistake 2 — Using soft delete as proof of physical erasure.** PII fields remain in the source table.

**Mistake 3 — Believing `@EventListener` fires automatically on SQL `DELETE`.** Spring Application Events do not auto-publish events on arbitrary data deletes. Explicit publishers or configured repo/ORM hooks are required, and bulk deletes can skip lifecycle callbacks.

**Mistake 4 — Publishing `"ErasureCompleted"` before transaction commit.** A subsequent rollback makes the event false.

**Mistake 5 — Using `AFTER_COMMIT` as a durable queue.** Callbacks can be lost if the process dies; use an outbox when recoverability is required.

**Mistake 6 — Using `@Scheduled` without multi-instance coordination.** Multiple replicas can scan/delete concurrently; use claiming/locks/idempotency.

**Mistake 7 — Ignoring legal holds and retention exceptions.** Time-expired data may still be ineligible for deletion under active legal bases.

**Mistake 8 — Putting raw email/PII into erasure events or logs.** The act of deleting creates another copy of sensitive data.

**Mistake 9 — Sending a Kafka tombstone and claiming everything is deleted.** Compaction is not instant and does not erase consumer DBs, backups, or other topics.

**Mistake 10 — Deleting pending outbox rows immediately.** Relays lose retry data; consumers may never receive the deletion request.

**Mistake 11 — Unbounded retries.** Systems can create retry/DLQ storms; enforce policies, timeouts, backoff, and error classification.

**Mistake 12 — Skipping restore/replay testing.** Old snapshots or event histories can resurrect previously deleted data.

**Mistake 13 — Calling data "anonymous" after plain hashing.** Hashes can be linkable or guessed; evaluate real re-identification risk.

**Mistake 14 — Deleting millions of rows in one transaction.** Causes long locks, storage pressure, and replication lag; batch with checkpoints.

**Mistake 15 — Storing deleted values inside audit logs.** Audit evidence should describe the operation and minimal outcome, not re-store sensitive content.

**Mistake 16 — Applying unapproved default retention periods.** Durations and exceptions depend on policies, contracts, and applicable laws; frameworks cannot choose for the organization.

## 15. Design and Implementation Checklist

- [ ] Listed data classes, processing purposes, data owners, target systems, and approved retention periods.
- [ ] Defined retention start trigger, `expiresAt`, timezone, and policy version.
- [ ] Defined legal hold/review/approval mechanisms and lawful exceptions.
- [ ] Minimized PII in events, logs, traces, metrics, and DLQs by design.
- [ ] Implemented conditional deletion directly in the statement; recorded actual affected row counts.
- [ ] Built short-batch, idempotent, fault-tolerant, multi-instance-safe cleanup jobs.
- [ ] Never confused `@Scheduled` with a distributed scheduler or completion-guaranteed job.
- [ ] Distinguished `ErasureRequested`, `PrimaryRecordErased`, and `ErasureCompleted`.
- [ ] Used `AFTER_COMMIT` for post-commit timing and outboxes for durable propagation.
- [ ] Tracked acknowledgements and retries for all consumers holding mandatory copies.
- [ ] Configured retention/tombstones on brokers, DLQs, outboxes, and consumer stores.
- [ ] Defined erasure/anonymization for materialized views, object versions, and logs.
- [ ] Implemented restore/replay suppression so deleted data never resurrects.
- [ ] Defined valid backup retention schedules and backup/restore control procedures.
- [ ] Stored minimal evidence with access control, without re-storing secrets/PII in audits.
- [ ] Tested expiry, holds, rollbacks, retries, crashes, duplicates, replays, and deletion SLAs.
- [ ] Monitored backlogs, oldest-pending-age, deletion failures, and per-target completion.
- [ ] Reviewed whenever adding consumers or event schema fields: every new copy must have a lifecycle.

## 16. Self-Check Questions

1. **Why is deleting one DB row insufficient?** — Because Spring events may have replicated copies to caches, brokers, indexes, logs, consumer DBs, and backups.
2. **How do retention and erasure requests differ?** — Retention is a lifecycle schedule/policy; an erasure request requires verifying grounds and conditions.
3. **Does soft delete mean PII is erased?** — No; data can remain intact in storage.
4. **Does `@Scheduled` guarantee single-instance execution?** — No; cluster coordination is required.
5. **Why re-check expiry and hold inside `DELETE`?** — To avoid deleting if conditions changed since candidates were selected.
6. **Does publishing an event inside a transaction mean the DB has committed?** — No.
7. **Does `@TransactionalEventListener(AFTER_COMMIT)` prevent losing events on a crash?** — No; use an outbox if durability is required.
8. **Why omit emails from erasure events?** — Including them creates yet another copy of the very data being deleted.
9. **Do Kafka tombstones immediately wipe all PII?** — No; compaction is not instant and does not cover other copies.
10. **How do you stop replays from restoring deleted data?** — Use an erasure ledger, filters/versioning/restore controls, and replay tests.
11. **Is re-deleting the same ID necessarily an error?** — No; erasure handlers should be idempotent for retries.
12. **Can scheduled jobs delete data under a legal hold?** — Never automatically bypass valid holds; follow policy and approval.
13. **How do you prove all targets processed deletion?** — Track per-system acknowledgements/verification, not just "published" logs.
14. **Why can't retention periods come from Spring defaults?** — Durations depend on data types, purposes, laws, contracts, and approved policies.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — JpaRepository bulk delete API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)
- [Apache Kafka — Topic configs: cleanup.policy, retention, compaction, tombstones](https://kafka.apache.org/documentation/#topicconfigs)
- [GDPR — Regulation (EU) 2016/679, Article 5 and Article 17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679)
- [European Data Protection Board — Erasure FAQ](https://www.edpb.europa.eu/sme/find-practical-info/faq_en)
