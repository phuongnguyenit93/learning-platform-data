# Data Retention for Java Logging: Retaining, Archiving, and Deleting Logs Under Privacy Policies

## 1. Why Do Logs Need a Retention Period?

Java applications commonly write logs for operations, troubleshooting, security auditing, and business flow analysis. However, a single log line can contain an IP address, user ID, request ID, URL, account name, device information, error data, or even sensitive information accidentally included in a message. **Retaining logs indefinitely is not a safe default**: it increases the data exposure surface, storage costs, and complexity when data subjects request to exercise their rights.

**Data retention** is the complete policy that defines:

- **What to collect:** which event types and fields are genuinely necessary for the defined purpose.
- **How long to keep:** retention periods by data category, purpose, legal/contractual requirements, and risk level.
- **Where to store:** stdout/container nodes, local files, centralized systems, object storage, backups, and exports.
- **Who has access:** role-based access control, audit logging for viewing/exporting, and protective safeguards.
- **When to transition storage tiers:** hot/warm/cold/archive when operationally beneficial.
- **When and how to delete:** determining expiration, deleting expired data, verifying deletion, and tracking execution evidence.
- **Exceptions:** incidents, investigations, legal holds, or other valid retention obligations.
- **When restoring backups:** how to avoid accidentally restoring and reusing logs that should have been deleted or restricted.

The goal is a consistent, verifiable lifecycle—not just setting `maxFileSize` in a logging framework or scheduling a cron job to delete files.

### After This Lesson, You Will Be Able To

1. Distinguish between log rotation, retention, archival, deletion, and legal hold.
2. Design a log classification table by purpose and retention period with designated approvers.
3. Identify personal data boundaries across events, MDC, exceptions, and URLs.
4. Calculate expiration timestamps in Java 17, handling UTC, boundary conditions, and hold exceptions.
5. Apply policies at Logback/FileAppender, containers, and centralized backends within each tool's actual capabilities.
6. Verify deletion across indexes, files, object storage, replicas, snapshots, and backups.
7. Monitor expired data volume, deletion failures, costs, remaining copies, and policy drift.

**There is no single default number—7, 30, 90, or 365 days—that fits every log, every company, and every jurisdiction.** The timeframes in the examples below are for practice only; production retention periods must be determined from the intended purpose, valid requirements, and decisions by the responsible teams.

## 2. Commonly Confused Concepts

| Concept | Definition | What It Does Not Guarantee |
| --- | --- | --- |
| Log rotation | Switching to a new file by date/size, optionally compressing old files | Does not automatically guarantee all copies of a log expire on time |
| Retention period | The duration data is permitted/required to be kept under policy | Does not enforce itself if only written in documentation |
| TTL (time-to-live) | An expiration rule for a record/object/index after a set duration | May delete asynchronously; does not always happen to the exact millisecond |
| Hot storage | Where recent data is easily queried, usually at higher cost | Does not mean data is deleted when moved out of hot storage |
| Archive / cold storage | Longer-term or slower-access storage, potentially for investigations | Not synonymous with anonymizing or deleting data |
| Expiration | Data has become eligible for deletion under policy | Does not guarantee physical deletion or removal of all versions |
| Deletion / purge | Removing data from locations within the processing scope | Must account for backups, replicas, versions, and remaining access |
| Legal hold | Temporarily suspending deletion under an approved basis/condition | Does not mean keeping all data indefinitely |
| Redaction | Removing or masking sensitive fields | Does not replace retention policies for the remaining fields |
| Pseudonymization | Replacing direct identifiers with pseudonyms that can be re-linked under certain conditions | Often still constitutes personal data if re-identification remains possible |
| Anonymization | Processing so individuals are no longer identifiable under applicable standards | Harder than deleting a username; must consider cross-linking risks |

**Size-based rotation is different from time-based retention.** For example, an appender configured to keep only three 20 MB files may cycle through all logs in minutes under high load or hold onto logs for a very long time under low load. It controls local disk usage, **not a commitment to retain data for an exact number of days**.

**Moving to archive is not deletion.** If a log leaves the search index after 14 days but remains in object storage for 2 years, the actual data lifecycle still spans 2 years or more.

## 3. Privacy: Where Does Personal Data Hide in Logs?

An operational or business log can contain direct or indirect identifying data. It is not just usernames that require scrutiny.

| Field or Source | Risk | Recommendation |
| --- | --- | --- |
| user_id/customer_id | Can be linked to an account or individual | Keep only when needed; attach policy and access controls |
| IP, device, user-agent | Can contribute to identification or behavioral profiling | Limit purpose, granularity, and retention period |
| URL, query, HTTP header | May contain emails, tokens, session IDs, or sensitive parameters | Log path templates; filter query/headers via an allowlist |
| Request/response body | May contain full user payloads | Do not log by default; log only safe, necessary fields |
| Exception message / stack trace | May accidentally include user input and identifiers | Use error codes, redaction, and avoid embedding secrets |
| MDC/ThreadContext | Easily accumulates many context fields | Only approved, stable keys; clear/restore per scope |
| Session ID/access token/cookie | Can be abused for session hijacking or unauthorized access | Never log verbatim |
| Database URL/credentials | Can expose infrastructure details or secrets | Never log connection strings containing secrets |
| Trace ID/span ID | Used to correlate events; can link user behavior | Restrict access and retention; do not treat trace IDs as identity |
| Search query logs | May reveal user intent or behavior | Evaluate whether logging the raw query content is truly necessary |

**Data minimization** should be applied *before writing the log*, rather than storing full payloads and hoping the backend deletes them on time. Even if a log is kept for only one day, logging raw passwords or tokens is generally unacceptable.

### Before and After Example

**Avoid:**

~~~java
// Illustrative snippet: logging the entire request may expose data.
log.info("Checkout request: {}", request);
~~~

**Prefer approved fields:**

~~~java
// SLF4J snippet; requires an application and a declared logger.
log.info("checkout_result order_id={} status={} duration_ms={}",
        orderId, safeStatus, durationMs);
~~~

This is an in-application code snippet assuming the corresponding variables exist, **not a standalone program**. `orderId` may still be a controlled identifier; log it only if the purpose permits. `safeStatus` must be derived from valid application-defined states, never letting users inject arbitrary values into trusted metadata.

## 4. Retention Policies Must Start with Purpose

Identify log categories first, then build a policy for each group. Here is an illustrative table for aligning on requirements:

| Log Category | Purpose | Example Period | Storage Location | Approver |
| --- | --- | --- | --- | --- |
| Detailed DEBUG/TRACE | Short-term diagnostics | 3 days | Hot | Application owner and security |
| APPLICATION INFO/WARN | Operations, troubleshooting | 14 days | Hot | Operations owner |
| SECURITY events | Incident detection and investigation | 90 days | Hot + controlled archive | Security/legal teams if applicable |
| Regulated AUDIT events | Accountability / fulfilling obligations | 365 days | Dedicated store with restricted access | Data owner and compliance |
| Gateway access logs | Access monitoring, service protection | Per separate assessment | Observability backend | Infrastructure and privacy owners |

**The 3, 14, 90, and 365 days here are purely hypothetical examples for learning.** Do not treat this table as a legal rule. An organization may need to retain data for shorter or longer periods, or may lack a valid basis to collect a given category at all.

Each policy row should also document:

- **Policy ID and version:** for example, `retention.application.v3`.
- **Owner:** the person or role authorized to make changes.
- **Purpose and lawful basis where applicable:** why the data is collected and retained.
- **Data class:** which logs are covered and which sensitive fields they contain.
- **Retention start timestamp:** `event_time`, `ingestion_time`, transaction close, or another clearly defined milestone.
- **Maximum period and deletion rules:** TTL, archival schedule, and grace period if approved.
- **Deletion targets:** indexes, collector spools, files, archives, backups, replicas, and exports.
- **Exceptions:** legal holds, incident reviews, or mandatory retention rules.
- **Geographic location and processors:** where data is transferred and who has access.
- **Verification evidence:** metrics, deletion job results, audit trails, and policy review dates.

### Laws and Regulations: A Careful Interpretation

The **storage limitation** principle in GDPR Article 5(1)(e) requires that personal data not be kept in a form that permits identification of data subjects for longer than necessary for the purposes for which it is processed, subject to specific legal exceptions and conditions. This **does not mandate a universal 30-day or 90-day log TTL for every application**. Rules and obligations vary by jurisdiction, data type, contracts, and regulators; implementation must follow decisions from compliance/legal stakeholders.

The OWASP Logging Cheat Sheet also emphasizes that logs, temporary debug logs, copies, and backups should neither be destroyed before required retention periods nor kept beyond permitted periods. The twin goals of **retaining enough when needed** and **deleting properly upon expiration** must go together.

## 5. Data Lifecycle: A Single Log Can Exist in Many Places

A Java event rarely lives in just one file:

~~~text
Java application
    |
    +--> ConsoleAppender / JUL ConsoleHandler
    |          |
    |          v
    |      stdout/stderr
    |          |
    |          v
    |      runtime/node log files --------------+
    |                                           |
    +--> (optional) local rolling file --------+
                                                |
                                                v
                                          Collector / Agent
                                                |
                                                +--> local spool / retry queue
                                                |
                                                v
                                          Transport / Broker
                                                |
                                                +--> buffering / replica
                                                |
                                                v
                                       Search index / log store
                                                |
                                                +--> snapshots
                                                +--> cold archive
                                                +--> object versions
                                                +--> backup / restore copy
                                                +--> analyst export
~~~

**Retention limits must be enforced across every location within the processing scope**, not only in the Search Index. Setting a 14-day index lifecycle while object storage retains data indefinitely is an **incomplete** retention policy.

### How Does Each Layer Typically Retain Data?

| Layer | Can Data Remain After Deletion Elsewhere? | What to Verify |
| --- | --- | --- |
| Logger/async appender | Queue holding unsent events | Queue lifetime, flush/shutdown, behavior when full |
| Files created by Logback/Log4j 2 | Active file + compressed archives | Daily/size rotation, max history, old file cleanup |
| Docker runtime | Local log files per driver | Driver, size limits, node retention, container deletion |
| Kubernetes node | Container logs + rotated segments | Kubelet settings, Pod eviction, node lifecycle |
| Collector | Disk buffer/spool/retry | Maximum age, delivery failures, dead-letter queue |
| Message broker | Partitioned topics, replay | Topic retention and replicas |
| Search backend | Primary/replica/index | Index deletion, TTL, compaction, snapshots |
| Object storage | Objects, versions, replicas | Lifecycle for current and noncurrent versions, locks/holds |
| Backups and snapshots | Point-in-time backup copies | Backup retention schedule, restore controls, post-expiry purge |
| CSV/JSON exports and support tickets | Extracts outside the pipeline | Inventory, access controls, export TTL |
| Monitoring/alert bodies | Event payloads may be copied | Pay special attention to personal data in notifications |

For multi-region cloud systems or multiple data processors, you must define who is responsible for deleting copies and what evidence proves deletion is complete. Never report "deleted" if events were merely hidden from the query UI.

## 6. Retention vs. Rotation in Logback

In Java using SLF4J + Logback, a file appender is typically configured with `RollingFileAppender` and a `RollingPolicy`. For example:

**src/main/resources/logback.xml**

~~~xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>
                logs/application.%d{yyyy-MM-dd}.log.gz
            </fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
~~~

This is a **Logback configuration example**, not a standalone Java program. With a compatible backend and Logback version:

- `fileNamePattern` with `%d{yyyy-MM-dd}` specifies daily archive intervals and `.gz` compression.
- `maxHistory=14` limits the number of **rolled-over archive intervals** kept under Logback's policy; it should not be interpreted as deleting each `LogRecord` exactly 14×24 hours after emission.
- `totalSizeCap=1GB` caps the total size of archived history under the policy; exceeding the cap can delete archives **before** 14 days have elapsed. Therefore, "retaining for at least 14 days" is not guaranteed by this parameter pair alone.
- `cleanHistoryOnStart=true` triggers history cleanup when the appender initializes; ongoing cleanup during runtime depends on rollover events and the backend's execution mechanism.
- `logs/application.log` is the **active file**. Cleaning up archives does not mean old events in the active file are deleted immediately.
- If multiple applications or replicas write to the same path, file locking and rotation issues can occur; do not use this configuration as a shared multi-process logging solution.

### When Both Time and Size Limits Are Needed

A daily rolling policy combined with `totalSizeCap` prevents archives from growing unbounded, but a policy of "retain at least 14 days for investigation" can conflict with "maximum 1 GB." When log volume exceeds estimates, you must choose to increase capacity, move to an appropriate archive, or reduce log rate. **Never silently shorten retention for required log categories** just to avoid filling the disk.

### Log4j 2

Log4j 2 provides `RollingFileAppender`, triggering policies, and rollover strategies, and can use delete actions/filters based on file age in an appropriate configuration. However, **filesystem file age (last modified) differs from individual event age**. For example, copying files or updating metadata can alter `mtime`, and a single file contains events from different times.

Always consult the documentation for the exact Log4j 2 version in use, verify the rollover strategy's deletion behavior, and check which files are actually deleted. If retention has strict requirements per record or per data class, enforce it in a backend that supports TTL or index lifecycle management rather than relying solely on file `mtime`.

### File Retention Does Not Replace Centralized Policy

If a service runs in Docker/Kubernetes, it is usually better to log to the console and let a collector handle forwarding; local log files are just one more layer to control. Setting `maxHistory` in Logback has no effect on logs already shipped to OpenSearch, Elasticsearch, Loki, object storage, or a SIEM.

## 7. Container Runtimes and Kubernetes: Node Log Limits Are Not Full Retention

When Java writes to stdout/stderr, Docker or the container runtime collects and stores logs locally according to its logging driver. For example, Docker with the `local` logging driver:

~~~bash
docker run --name sample-service \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  image:tag
~~~

This is an **illustrative runtime configuration command** requiring a real `image:tag` and Docker permissions; it is not meant to be run blindly. `max-size`/`max-file` control local disk usage and file count, not a three-day retention guarantee. The Docker daemon also has a default log driver configuration, though changing daemon settings does not automatically update existing containers.

In Kubernetes, kubelet manages container log rotation on each node. Common settings include:

~~~yaml
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
~~~

This is **kubelet configuration**, not a field in an application's Deployment spec. Kubelet serves node logs for `kubectl logs`; per Kubernetes documentation, `kubectl logs` normally reads only the latest log file, and `--previous` only works if the prior container instance's logs still exist. When a Pod is evicted or a node is lost, node-local logs may disappear.

**Therefore:**

1. Use node/runtime rotation to cap **temporary** local disk usage so the node disk does not fill up.
2. Use a collector to forward important logs to a centralized backend.
3. Configure **time-based and data-class retention** in the backend and archives.
4. Configure lifecycles for spools, dead-letter queues, backups, and exports.
5. Perform final verification that expired events are truly gone and can no longer be queried or restored against policy.

If a collector fails continuously, events may be lost before reaching the backend. Monitor drop rate, queue depth, delivery errors, and buffer capacity; this is an **availability** concern, distinct from how long data is retained after successful ingestion.

## 8. Choosing When the Retention Clock Starts

"Keep for 14 days" is ambiguous without defining the starting point. There are at least three milestones:

- **event_time:** when the event occurred in the application.
- **ingest_time:** when the collector/backend actually received the event.
- **archive_time:** when the object/index was created in another storage tier.

For example, suppose an event occurs on Day 1, the collector experiences an outage, and the backend receives it on Day 10. If the policy starts from `event_time`, the event may already be near or past expiration upon arrival; if it starts from `ingest_time`, it will be kept for the full period in the backend. Both approaches have trade-offs, but the choice must be **approved, documented as a rule, and implemented consistently**.

Structured logs should clearly distinguish these fields:

~~~json
{
  "event_time": "2026-11-01T09:00:00Z",
  "ingested_at": "2026-11-10T09:00:00Z",
  "category": "APPLICATION",
  "retention_class": "APP_STANDARD",
  "event_type": "REQUEST_FINISHED"
}
~~~

This is an illustrative schema only. `retention_class` must be assigned from a **trusted** policy or configuration, never accepted arbitrarily from a client—otherwise an attacker could pick a longer or shorter class to alter the deletion schedule.

### UTC and Boundary Rules

- Store timestamps with an explicit timezone, typically UTC / ISO 8601.
- For exact duration-based TTLs, you can compute `expires_at = event_time + Duration`.
- **Eligible for deletion when `expires_at` is not after `now`** (`expires_at <= now`), provided no hold or exception applies.
- Distinguish "14 × 24 hours" from "14 calendar days" in a business timezone; the two calculations can differ across Daylight Saving Time (DST) transitions.
- Never use timezone-naive `LocalDateTime` to compare timestamps across services or nodes; avoid inferring ordering from skewed clocks.
- The system clock running retention jobs must be reliable; logs with "future timestamps" must be handled by policy rather than kept indefinitely by accident.

When using daily index lifecycles, deleting an entire index may depend on **index creation date**, size/rollover, and lifecycle polling schedules rather than exact per-event timestamps. If record-level deletion by `event_time` is required, design index partitioning/TTL or field-based deletion supported by the backend.

## 9. Hands-On Java 17: Testably Evaluating KEEP, EXPIRE, and HOLD

This example **does not delete real files or records**. It is a **minimal retention decision engine**: it takes simulated log events, their categories, and a timestamp, then returns a decision based on an example policy. It has no Maven or external library dependencies beyond JDK 17.

The illustrative TTLs used here are DEBUG = 3 days, APPLICATION = 14 days, SECURITY = 90 days, and AUDIT = 365 days. These are **not recommended production periods or legal requirements**.

**File: LogRetentionDemo.java**

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class LogRetentionDemo {
    enum Category { DEBUG, APPLICATION, SECURITY, AUDIT }

    record LogEntry(
            String id,
            Category category,
            Instant occurredAt,
            boolean legalHold) { }

    record Decision(
            String id,
            Category category,
            String action,
            Instant expiresAt) { }

    private static final Map<Category, Duration> POLICY = Map.of(
            Category.DEBUG, Duration.ofDays(3),
            Category.APPLICATION, Duration.ofDays(14),
            Category.SECURITY, Duration.ofDays(90),
            Category.AUDIT, Duration.ofDays(365));

    private static Decision evaluate(LogEntry entry, Instant now) {
        Duration ttl = POLICY.get(entry.category());
        Instant expiresAt = entry.occurredAt().plus(ttl);

        // A valid hold must be processed before the expiration rule.
        if (entry.legalHold()) {
            return new Decision(
                    entry.id(), entry.category(), "HOLD", expiresAt);
        }

        if (!expiresAt.isAfter(now)) {
            return new Decision(
                    entry.id(), entry.category(), "EXPIRE", expiresAt);
        }

        return new Decision(
                entry.id(), entry.category(), "KEEP", expiresAt);
    }

    public static void main(String[] args) {
        // Fix the check timestamp for exact reproducible output.
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<LogEntry> entries = List.of(
                new LogEntry(
                        "debug-old", Category.DEBUG,
                        Instant.parse("2026-11-01T00:00:00Z"), false),
                new LogEntry(
                        "app-current", Category.APPLICATION,
                        Instant.parse("2026-11-01T00:00:00Z"), false),
                new LogEntry(
                        "security-held", Category.SECURITY,
                        Instant.parse("2026-01-01T00:00:00Z"), true),
                new LogEntry(
                        "audit-boundary", Category.AUDIT,
                        Instant.parse("2025-11-10T00:00:00Z"), false));

        for (LogEntry entry : entries) {
            Decision result = evaluate(entry, now);
            System.out.printf(
                    "%s category=%s action=%s expires=%s%n",
                    result.id(), result.category(),
                    result.action(), result.expiresAt());
        }
    }
}
~~~

**Run:**

~~~bash
javac -encoding UTF-8 LogRetentionDemo.java
java LogRetentionDemo
~~~

**Exact stdout:**

~~~text
debug-old category=DEBUG action=EXPIRE expires=2026-11-04T00:00:00Z
app-current category=APPLICATION action=KEEP expires=2026-11-15T00:00:00Z
security-held category=SECURITY action=HOLD expires=2026-04-01T00:00:00Z
audit-boundary category=AUDIT action=EXPIRE expires=2026-11-10T00:00:00Z
~~~

### Explaining the Output

- `debug-old` has timestamp `2026-11-01` and a 3-day TTL, expiring `2026-11-04`; at check time `2026-11-10`, the decision is `EXPIRE`.
- `app-current` has a 14-day TTL, expiring `2026-11-15`; at `2026-11-10`, it remains `KEEP`.
- `security-held` would have expired `2026-04-01` under the example 90-day TTL, but `legalHold=true` results in `HOLD`. This **does not mean the system is allowed to hold data indefinitely**; production must verify basis, scope, authority, and review dates.
- `audit-boundary` has a 365-day TTL, expiring **exactly** at `now` (`2026-11-10`); `!expiresAt.isAfter(now)` yields `EXPIRE` on the exact equality boundary.
- The program does not touch the filesystem, databases, or object storage; it cleanly separates **retention decision** from **deletion execution**. This is a valuable design boundary for testing.

### What Production Needs Beyond This

A real policy engine typically requires:

- Versioned policies loaded from a trusted source, validating classes, valid TTLs, and rejecting missing values.
- Automatic classification from a trusted log source, never self-declared by users.
- Holds managed in a dedicated store/workflow with case IDs, scope, approvers, review timestamps, and release mechanisms.
- A job execution protocol: dry-run → policy confirmation → batching → deletion → verification → audit.
- Transactions, locks, or concurrency controls to avoid deleting data that was just placed on hold.
- Idempotency so jobs can safely rerun after timeouts, with separate failure recording.
- Purge plans across replicas, snapshots, and backups.
- Observability for expiration rates and job lag.
- Policies for handling late-arriving events and malformed timestamps.

Never turn the example above into a cron job that deletes every file matching a category name without scope management, hold checks, permissions, and verification.

## 10. Architecture for Class-Based Retention

A reference architecture:

~~~text
Java application (data minimization, safe logging)
    |
    +--> Local stdout/file: rotation and size limits
    |
    v
Collector: queue TTL + retry policy + dropped-event metrics
    |
    v
Central log store
    |
    +--> HOT index / stream (fast queries)
    |        |
    |        +--> lifecycle / TTL / index deletion
    |
    +--> ARCHIVE (if required)
    |        |
    |        +--> object lifecycle / version cleanup
    |
    +--> snapshots / backups
             |
             +--> backup retention + restore re-apply policy
    |
    v
Retention controller / scheduled process
    |
    +--> policy registry + legal-hold registry
    +--> deletion eligibility / dry-run
    +--> purge + verification
    +--> evidence / alert / exception review
~~~

### Separating Retention Across Log Categories

If `SECURITY` has different obligations than `APPLICATION`, do not dump everything into a single index and delete the index using either the shortest or the longest TTL. You can route streams/indexes by verified `retention_class`. If physical separation is not feasible, the backend must support record-level policies without affecting other data that must be kept.

Separating by category does not mean creating one index per customer or per order: an excessive number of indexes increases cost, metadata overhead, and operational complexity. Usually, partitioning by log category, service, time window, and appropriate scale works best.

### Retention Differs from Long-Term Analytics Systems

You may need to keep aggregated statistics longer than detailed logs—for example, daily totals of successful requests. However, aggregated data does not automatically become anonymous: small cohorts or overly granular dimensions can still allow re-identification. Re-evaluate the purpose, granularity, and access controls for analytics aggregates.

## 11. Deletion in Object Storage: Current vs. Noncurrent Versions

Many systems archive logs to S3 or equivalent object storage. Typically, lifecycle rules transition tiers after one interval and expire objects after another. However, when **versioning is enabled**, "deleting an object" may only add a delete marker while older versions remain intact.

For versioning-enabled Amazon S3, official documentation states:

- Expiration on a current version can create a **delete marker** and turn the previous version into a noncurrent version.
- Removing noncurrent versions requires an appropriate **NoncurrentVersionExpiration** rule.
- Expired object delete markers may also require cleanup.
- Object Lock or legal holds can block deletion of protected versions.
- S3 Lifecycle runs asynchronously; do not promise simultaneous physical deletion across all replicas at the exact millisecond a TTL expires.

This concept is a storage design concern, independent of the Java logger. A pipeline that deletes records from the search index while leaving object versions in the archive has not fulfilled a full-lifecycle purge if policy requires deleting both.

### Example Storage Targets (Not a Ready-to-Deploy Rule)

~~~text
retention_class: APP_STANDARD
hot_search_ttl: 14 days
archive: none
backup_max_age: policy-defined
legal_hold: controlled exception
deletion_evidence: required

retention_class: SECURITY_REVIEW
hot_search_ttl: policy-defined
archive_ttl: policy-defined
backup_max_age: policy-defined
legal_hold: controlled exception
deletion_evidence: required
~~~

This is a **policy documentation template**, not valid configuration syntax for S3, Logback, or any specific backend. Actual periods must be approved beforehand. Never hardcode `APP_STANDARD 14 days` across every project.

## 12. Legal Holds, Investigations, and Exceptions

There are situations where data due for deletion must be temporarily preserved due to a valid obligation, an approved investigation, or a dispute. Treat this as a **governed exception**, not an excuse to abandon retention altogether.

A minimal hold record should include:

| Field | Purpose |
| --- | --- |
| hold_id / case_id | Identifies the request |
| scope | Objects, events, or time range to preserve |
| legal_or_policy_basis | Approved basis and purpose |
| approved_by | Accountable person or role |
| created_at | When the hold began |
| review_at | When the hold must be re-evaluated |
| released_at | When the hold ended |
| action_on_release | Re-evaluate expiration and delete if already overdue |
| audit_history | Who created, modified, and released the hold |

**Operation ordering matters.** If a retention job checks holds at time A, but a new case is placed on hold at time B before the job deletes the data, a race condition occurs. Production needs synchronization/transactions or proper locking/concurrency control between hold creation and deletion. You cannot simply read a boolean, delete immediately, and claim safety.

After releasing a hold, the system should re-evaluate the original expiration timestamp and delete eligible data under policy, rather than automatically extending the full TTL unless rules require it.

Any immutable/WORM storage mechanism requires balance: data must be protected from unauthorized modification or deletion, yet keeping data past its permitted period also introduces risk. Lock and retention mode configurations should be reviewed with security and legal owners before deployment.

## 13. Backups, Replicas, and Exports: The Most Easily Forgotten Places

An event may have disappeared from dashboards yet still exist in:

- Index snapshots.
- Object storage current and noncurrent versions.
- Replicas / cross-region replication.
- Database, VM, or file backups.
- Collector disk spools.
- Analyst JSON/CSV exports.
- Incident tickets, chat/email notifications, and attachments.
- Staging/test environments with accidentally copied production data.

A **data inventory** must document all of these locations. Without an inventory, it is hard to know whether deletion is truly complete.

### Designing Policy for Backups

Backups usually follow their own backup retention cycle. Deleting individual events inside an immutable backup may be infeasible or compromise recovery integrity. In some contexts, an approved approach is to cap backup retention, restrict access, prohibit querying backups directly, and **re-apply deletion rules immediately after a restore**. This must align with applicable requirements; you cannot simply assume "leaving it in backups until they expire" is acceptable.

Restore design must:

1. Know the point-in-time timestamp of the restored snapshot.
2. Reload current policies and holds rather than using stale policies.
3. Flag data that was requested for deletion or has already expired.
4. Block reuse or publication of events due for purge until reconciliation completes.
5. Verify post-restore state and store evidence without copying excessive PII.

### Exports Often Have Separate TTLs

A CSV exported from log search can contain personal data and sits outside index deletion policies. Systems should enforce expiring exports, expiring download links, access controls, access trails, workspace/ticket cleanup, and guidance against uncontrolled forwarding.

## 14. Personal Data Deletion Requests and Log Retention

In certain jurisdictions, data subjects can submit requests for access, erasure, or restriction of processing. For logs, handling these requests requires balancing individual rights against valid retention bases and security/audit obligations.

A coordinated workflow typically includes:

1. Receiving requests through approved channels and verifying the requester as required.
2. Identifying all relevant systems and log classes (not just one index).
3. Checking valid retention bases and exceptions—never assuming every log must be deleted immediately.
4. Selecting the right action: record deletion, identifier removal, redaction, access restriction, or preservation under a valid hold.
5. Executing across all relevant systems, including exports, snapshots, and backups per approved mechanisms.
6. Verifying results, handling copies, and tracking SLAs/exceptions.
7. Recording safe **execution evidence** (policy ID, job ID, counts, status) while avoiding repeating sensitive data in deletion audit logs.

Not all logging systems make searching or deleting by user ID easy. Designing index schemas and log purposes upfront reduces this friction. Avoid writing personal data into stores that cannot be searched or lifecycle-managed.

**Anonymization differs from pseudonymization:** stripping a username while keeping IP addresses, correlated traces, device details, or rare combinations can still allow re-identification. Tokenization with an existing mapping table is not automatically anonymous.

## 15. Deleting Logs: Designing a Safe Workflow

For data eligible for deletion, the deletion pipeline should follow clear steps:

~~~text
Scheduled retention job
    |
    v
Load signed/approved policy version
    |
    v
List candidates by policy scope and age
    |
    v
Check holds / ownership / ingestion lag / exclusions
    |
    v
DRY RUN + estimate count/bytes/time span
    |
    v
Authorized execution: delete / expire / lifecycle
    |
    v
Verify search + archive + versions + replicas
    |
    v
Record safe evidence + alert on mismatch/failure
~~~

### Essential Safeguards

- **Dry-run:** display record/object counts, classes, and oldest/newest dates without writing sensitive data into the deletion job's own logs.
- **Target allowlist:** act only on approved resources, indexes, or prefixes; never use unchecked broad wildcards.
- **Blast radius limits:** process in batches with rate limits and pause/cancel controls before irreversible actions.
- **Hold recheck:** never rely on a stale hold snapshot at deletion execution time.
- **Idempotency:** rerunning after a timeout must not delete outside the intended scope.
- **Minimal audit:** log policy version, job ID, counts, outcomes, errors, and approver; never log raw user data.
- **Verification:** recheck backends, snapshots, and backups against actual state; never treat an HTTP 200 "delete accepted" as proof.
- **Alerts:** missed job schedules, growing expiration backlogs, permission errors, or object locks blocking deletion.
- **Policy changes:** require review and canary/dry-run validation before rolling out across production.

The Java example in Section 9 only evaluates `KEEP`/`EXPIRE`/`HOLD`. **Do not add `Files.walk(...).delete(...)` to that sample** for production directories: file `mtime` differs from event age, a file can contain records with different TTLs, legal holds may apply, and paths might fall outside allowed scope.

## 16. Securing Logs Throughout Their Retention Period

The longer the retention period, the more critical access control and protection become.

**At rest:** encrypt stored logs appropriately for your infrastructure, manage keys properly, enforce access controls, and audit permissions regularly; keep production logs with real data separate from test environments.

**In transit:** use authenticated and encrypted channels between collectors and backends where appropriate; never send sensitive logs to uncontrolled endpoints.

**Access control:** restrict access by role, team, service, or data class; do not let every developer read all `AUDIT` or `SECURITY` logs by default.

**Access logging:** searching, reading, exporting, and modifying retention policies must itself be logged as needed; those access logs need their own retention policy.

**Integrity:** protect against unauthorized modification or deletion to ensure tampering is detectable; do not confuse immutable storage with "keep forever."

**Least privilege for deletion jobs:** grant deletion permissions only on required resources, not broad system-wide admin privileges.

**Encryption keys:** key destruction can be part of a cryptographic erasure strategy when properly designed and approved, but do not assume every copy, cache, replica, or snapshot is erased merely because a key was rotated. Understand key scope and recovery mechanisms.

## 17. Performance, Cost, and Data Volume

A useful operational question is: "How many logs does the system generate daily, how much are we retaining, and why?"

You can make a rough estimate:

~~~text
Hot capacity (uncompressed) approximately
    events/second × bytes/event × 86,400 × retention days
~~~

This is only a **rough estimate**; you must also account for index overhead, replicas, compression, metadata, hot/warm tiers, traffic spikes, and actual retention ratios. Do not use it for final capacity sizing.

For example, at 100 events/second, averaging 500 bytes/event, retained for 14 days, raw data is roughly:

~~~text
100 × 500 × 86400 × 14 = 60480000000 bytes
≈ 60.48 GB (decimal), excluding replicas/index/overhead
~~~

In real systems, measure events/s, bytes/s, log ratios by level/category, compression ratios, ingest lag, deletion throughput, and archive/backup footprints. Reducing costs by dropping unnecessary fields at the call site is usually safer than "keep everything for a year and figure it out later."

### Sampling Must Not Mechanically Replace Retention

Sampling can reduce `DEBUG`/`TRACE` volume for debugging, but should not blindly drop security events, audit records, or business events that must be retained in full. Retention answers **how long to keep collected records**; sampling answers **whether to collect a record at all**. These are distinct policies and must be evaluated separately.

## 18. Testing Data Retention Policies

### 18.1. Decision-Level Unit Tests

| Scenario | Expected Outcome |
| --- | --- |
| Event newer than TTL | `KEEP` |
| Event older than TTL | `EXPIRE` |
| Event expiring on exact boundary `expires_at == now` | `EXPIRE` |
| Event older than TTL with valid hold | `HOLD` |
| Hold released | Recalculate eligibility and `EXPIRE` if due |
| Future or invalid timestamp | Clear handling policy; never retain indefinitely by accident |
| Policy missing category | Fail closed / alert by design; never pick an arbitrary TTL |
| Client-supplied category name | Must not extend retention without trusted classification |
| Policy version change | Migration, review, and QA by version |
| Late-arriving event | Follow approved `event_time`/`ingest_time` selection rule |

For `LogRetentionDemo.java`, vary `now` before and after `expiresAt` to test each branch. If using `Clock` in production, inject `Clock.fixed` in tests rather than relying on the system clock.

### 18.2. Integration Tests in Backends and Archives

1. Ingest a classified synthetic log set with timestamps before, on, and after the cutoff.
2. Attach an approved legal hold to a subset.
3. Run the retention job in dry-run mode and compare candidate and hold counts.
4. Execute in a test environment; inspect the corresponding indexes and object versions/snapshots.
5. Verify **non-expired** events remain queryable while expired events are no longer within the purge scope.
6. Test when the backend returns accepted for asynchronous deletion: the job must continue verifying completion.
7. Test duplicate job runs, timeouts, and retries to verify idempotency.
8. Test restoring an old backup; verify policies/deletions are re-applied before exposing data to users.
9. Review permissions, error reports, and audit logs to confirm no unnecessary personal data is present.

### 18.3. Metrics to Alert On

| Metric | Operational Value |
| --- | --- |
| retention_job_last_success_time | Detects whether the job stopped running |
| expired_records_pending / expired_bytes_pending | Measures expiration backlog |
| deletion_latency | Delay from eligibility to verified deletion |
| deletion_failures_total | Detects permission, API, or storage errors |
| legal_hold_records | Tracks items currently under hold |
| unclassified_log_events | Detects logs without a policy |
| archive_objects_without_expiration | Detects "orphaned" data |
| backup_restore_reconciliation_failures | Detects restores violating policy |
| log_volume_by_class | Identifies abnormal growth |
| collector_dropped_events | Reveals data lost before storage |

Metrics should track only counts and states—**never embed raw PII or usernames** as metric labels; cardinality will explode and sensitive data may outlive log retention.

## 19. Common Pitfalls

| Symptom | Likely Mistake | Remediation |
| --- | --- | --- |
| Index keeps 14 days, but backups hold 2 years of logs | TTL configured only in search | Inventory and apply backup/archive lifecycles |
| S3 objects deleted, yet storage usage remains | Bucket versioning retains noncurrent versions | Check delete markers, noncurrent lifecycles, and Object Lock |
| Old log files persist despite `maxHistory` | No rollover yet, active file, or cleanup hasn't run | Verify rolling policy, `fileNamePattern`, and cleanup timing |
| Logs kept only a few hours despite 14-day policy | Size cap or early rotation | Reconcile volume, disk quota, and minimum retention |
| PII appears in error logs | Unfiltered exceptions or payloads | Field allowlists, redaction, end-to-end pipeline checks |
| Unable to delete logs for a specific user | No identifier/schema or searchable index | Design data discovery, classification, and workflows early |
| Job deletes events needed for investigation | Hold checked too early or wrong scope | Transaction/concurrency control with the hold registry |
| `event_time` retention drops late-arriving logs | Late ingestion not accounted for | Define retention start point and late-event handling |
| Backup restore resurrects deleted data | Policy not re-applied after restore | Block publication until reconciliation finishes |
| Backups/exports lack owners | Incomplete inventory | Assign owners, TTLs, permissions, and periodic reviews |
| Single TTL configured for all logs | Failing to distinguish purposes and obligations | Group policies and approve each category separately |
| "Delete succeeded," yet records remain in backend | Async deletion, replicas, or snapshots | Add verification and eventual consistency checks |

## 20. Step-by-Step Retention Rollout for a Java Service

**Step 1 – Inventory:** list all loggers, appenders, files, stdout, backends, indexes, object storage, replicas, backups, and exports.

**Step 2 – Classification:** for each event type, determine its purpose, sensitive fields, and trusted source. Minimize collected data before applying TTLs.

**Step 3 – Policy Approval:** data owners, security, and legal/compliance (as needed) define log categories, periods, bases, exceptions, and request handling.

**Step 4 – Attach Policy to Streams:** use logging categories or trusted `retention_class` routing; prevent clients from controlling retention.

**Step 5 – Configure Each Layer:** local rotation, collector buffer TTL, index lifecycle, object lifecycle, backup retention, and exports.

**Step 6 – Build Hold & Deletion Controllers:** access control, dry-run, locking/concurrency handling, and idempotent auditing.

**Step 7 – End-to-End Testing:** from event emission to archival and deletion; pay attention to versioning, restores, and late events.

**Step 8 – Observability:** implement the metrics above and alert on failed jobs or unclassified logs.

**Step 9 – Periodic Review:** adapt to changing operational needs, data types, cloud architecture, regulations, contracts, and actual log rates.

**Step 10 – Change Control:** whenever adding a new appender, collector, index, or data export, update the inventory and retention policy immediately rather than waiting for the next audit.

### Quick Implementation Checklist

- [ ] Every log class has an owner and a defined purpose.
- [ ] Passwords, tokens, full bodies, and unnecessary data are not logged.
- [ ] TTL is calculated from a clearly defined timestamp.
- [ ] The difference between local log rotation and centralized data policy is understood.
- [ ] Search indexes and archives have valid lifecycles.
- [ ] Current and noncurrent object versions are checked if using versioned storage.
- [ ] Replicas, backups, snapshots, and exports are included in the inventory.
- [ ] Valid hold mechanisms exist with scope, review, release, and audit trails.
- [ ] Deletion jobs have dry-run, least privilege, idempotency, verification, and alerts.
- [ ] Restores do not resurrect purged data against policy.
- [ ] Boundary expiration, late ingestion, and policy changes are tested.
- [ ] Log viewing/export permissions and storage locations are verified.

## 21. Hands-On Exercises

### Exercise 1: Modify TTLs and Test Boundaries

Run `LogRetentionDemo.java` as instructed. Add an `APPLICATION` event exactly at `expiresAt`, one just before the boundary, and one just after; predict `KEEP`/`EXPIRE`. Explain why using `Instant` with UTC avoids timezone ambiguity.

### Exercise 2: Design Retention for a Sample System

Design a policy table for access logs, application `INFO`, `DEBUG`, `SECURITY`, and `AUDIT`. Specify purpose, owner, sensitive fields, storage location, start timestamp, **hypothetical** retention period, exceptions, and deletion method. Explain why one group uses 14 days while others need separate periods, without citing "every company uses 90 days."

### Exercise 3: Logback Rolling Files

In a test application with Logback, configure `maxHistory` and `totalSizeCap`. Generate archives across appropriate test dates and inspect which files remain. Explain why `maxHistory` is not a per-record TTL deletion mechanism, and why `totalSizeCap` can make actual retention shorter than expected.

### Exercise 4: Versioned Object Storage

Simulate an architecture with a short-TTL search index and versioned object archive. After deleting the current object, explain noncurrent versions, delete markers, required lifecycle policies, legal holds, and how to verify no copies remain outside the retention scope.

### Exercise 5: Backup Restoration

An old backup contains logs that were deleted from production under a valid request. Diagram the restore workflow, policy/deletion record reconciliation, blocking access to data undergoing reconciliation, and result verification. Propose metrics and alerts for failures in this step.

### Exercise 6: Legal Hold Racing Against a Retention Job

Two tasks run concurrently: a job scanning expired events and an authorized team placing a hold on a subset. Point out the race condition between candidate selection and deletion. Propose an atomic check/lock/transaction mechanism for a concrete system and a test ensuring validly held events are not deleted.

## 22. Key Takeaways

**Data retention for Java Logging is a data lifecycle, not just a file-logging configuration.** Start with purpose, minimize personal data logged, classify logs reliably, and enforce approved periods. Retention must be enforced across **the entire pipeline**: appenders, containers/nodes, collectors, indexes, archives, object versions, backups, and exports.

A record becoming eligible for deletion does not mean all copies are gone. You need valid hold workflows, controlled deletion, verification, and evidence—while also avoiding premature deletion before mandatory periods end. With Java 17, you can test `KEEP`/`EXPIRE`/`HOLD` logic using `Instant` and `Duration` without touching real data. Never treat illustrative retention periods as legal mandates.

### Official References

- OWASP Logging Cheat Sheet – Data to exclude; Disposal of logs: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- GDPR Regulation (EU) 2016/679, Article 5 – Storage limitation: https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- NIST SP 800-92 – Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final
- Logback Manual – RollingFileAppender/TimeBasedRollingPolicy: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 – RollingFileAppender: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Kubernetes – Logging Architecture, log rotation: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Docker – Configure Logging Drivers: https://docs.docker.com/engine/logging/configure/
- Amazon S3 – Lifecycle expiration with versioning: https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html
- Amazon S3 – Object Lock considerations: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html
- Oracle Java 17 – java.time.Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Oracle Java 17 – java.time.Duration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html
