# Log Retention in Java Observability: Designing Retention, Archival, and Deletion Policies

## 1. What is Log Retention?

**Log retention** is the policy that determines **how long log records are kept, where they are stored, at what access level, and when they are archived to cold storage or deleted**. In Java observability, it spans the entire path of an event: from `logger.info(...)`, local files or stdout, collectors, search platforms, and object storage, all the way to snapshots, backups, and exports.

Logs help with error investigation, security, performance measurement, and transaction tracing. However, keeping all logs indefinitely wastes resources, increases the risk of exposing personal data, and makes governance or compliance harder. Conversely, deleting logs too early can destroy evidence when an incident is discovered late.

**The goal of retention** is to balance at least five factors:

1. **Observability and investigation:** having data available long enough to trace root causes of errors and security events.
2. **Query performance:** recent data needs to be searchable quickly, while older data can be queried more slowly.
3. **Cost:** file storage, indexes, replicas, snapshots, object storage, bandwidth, and retrieval fees.
4. **Data security:** enforcing read permissions, encryption, limiting PII/secrets, and controlling data exports.
5. **Business and legal requirements:** audits, legal holds, transaction history, personal data, and deletion workflows.

**There is no single retention period that fits every system.** Debug logs typically have short-term value; security logs or audit trails may need to be kept much longer. The numbers in this article are **design examples**, not mandatory legal deadlines.

## 2. Distinguishing Retention, Rotation, Archival, Expiration, and Deletion

These terms are often conflated, but each has a distinct responsibility:

| Term | Question it answers | What it does not guarantee on its own |
| --- | --- | --- |
| **Rotation / rollover** | When to stop writing to the current file/index and create a new one? | Does not delete stored data by default |
| **Retention** | How long to keep data, by what type and source? | A written policy is not guaranteed to be enforced by every sink |
| **Archival / tiering** | Where is infrequently queried data moved to a cold tier? | Moving tiers does not mean deleted |
| **Expiration / TTL** | When does data become eligible to leave a tier or be deleted? | "Eligible" does not mean deleted immediately |
| **Deletion** | By what mechanism are files/indexes/objects or records destroyed? | Deleting from one sink does not delete all replicas, backups, or exports |
| **Legal hold** | Which records must be preserved despite reaching normal expiration? | Cannot be safely applied without proper authority and evidence |
| **Data minimization** | Should this field be generated or logged at all? | Deleting after a few days does not undo a leaked token |

For example, a Logback appender might rotate files daily and keep up to 14 archive periods. Yet the collector still ships the contents to a backend with a 90-day retention. Deleting local files after 14 days **does not delete the 90 days of data in the backend**. Conversely, if the backend index is deleted after 7 days, the 14-day application files may still contain records that are no longer searchable in the backend.

You must distinguish **searchable duration** from **total data existence duration**. An index that has left the search tier may still reside in a snapshot or an archive bucket.

## 3. Map the Log Lifecycle Before Setting a TTL

```text
Java application
  ├── SLF4J/Logback/Log4j2 → local rolling file
  └── stdout/stderr        → container runtime
                                    │
                                    ▼
                            Collector / Agent
                                    │
                           Buffer / Retry / Queue
                                    │
                   ┌────────────────┴────────────────┐
                   ▼                                 ▼
           Searchable log backend              Archive objects
            (hot → warm → cold)                 (low-cost tier)
                   │                                 │
             Lifecycle delete                 Object expiration
                   │                                 │
                   └─────────► Backups / snapshots ◄┘
                                        │
                                        ▼
                                 Export / download
```

**Every point where data is persisted needs its own answers**: who owns it, how long it is retained, how it is deleted, how it behaves under a legal hold, access permissions, encryption, monitoring, and deletion verification. This is not just about configuring `maxHistory` on a Java logger.

Build an **inventory**:

| Storage location | What data? | Who configures retention? |
| --- | --- | --- |
| Java app rolling files | Application/debug/error logs | Application or platform team |
| Node/container stdout logs | Container stdout/stderr | Kubernetes/kubelet/container runtime |
| Collector buffer | Pending events, retries, spool | Observability team |
| Search index/data stream | JSON logs with index and mapping | Logging backend operations team |
| Object storage archive | Compressed files, JSONL, Parquet, or blobs | Data/platform team |
| Snapshot/backup | Recovery copies of indexes/objects | Backup/DR team |
| Export/dashboard cache | CSVs, notebooks, download links, caches | Product, security, and users |

If a source has not been included in the inventory, you should not claim "logs are completely deleted after 30 days."

## 4. Classifying Logs by Purpose, Sensitivity, and Duration

Good retention starts with the **event kind**, not just the logger level.

| Log kind | Purpose | Illustrative policy example |
| --- | --- | --- |
| `DEBUG` / `TRACE` | Short-term diagnostics, high volume | Hot 2 days, total 7 days |
| `APPLICATION` / `ERROR` | Error hunting, incident troubleshooting | Hot 7 days, total 30 days |
| `HTTP_ACCESS` | Traffic, response, and latency analysis | Hot 7 days, total 30 days |
| `SECURITY_EVENT` | Intrusion detection, investigation | Hot 30 days, total 90 days |
| `AUDIT` | Reconciling critical actions, audit obligations | Hot 90 days, total 365 days or as required |
| `METRIC` / `TRACE` | Time series, distributed traces | Separate retention; does not default to log policy |

The **2/7/30/90/365-day milestones are purely illustrative** of how to structure a policy; they must be adjusted to contracts, business needs, data classification, organizational policy, and applicable laws.

**Do not use severity as the sole retention classification.** An HTTP 500 access event might be logged at INFO level; a failed login security event might not be emitted as ERROR. Conversely, an ERROR containing sensitive information should not necessarily be kept longer than every INFO log.

A suggested schema:

```json
{
  "timestamp": "2026-11-10T03:15:00Z",
  "ingested_at": "2026-11-10T03:15:01Z",
  "kind": "SECURITY_EVENT",
  "event.name": "authorization_denied",
  "service.name": "identity-api",
  "environment": "production",
  "retention.class": "security",
  "schema.version": 1
}
```

**Do not trust `retention.class` supplied by an HTTP client.** Collector/index policy routing must rely on an authenticated source or a server-controlled schema. If a client can choose "audit" or "keep_forever" on its own, it can inflate costs, create long-lived data stores, or hide data in another permission group.

## 5. Policies Must Specify the Age Calculation Reference Point

"Keep for 30 days" is not specific enough. Is age measured from **event time**, **ingestion time**, **file modification time**, **index creation**, **rollover time**, or the date moved to archive?

| Reference point | Advantages | Risks |
| --- | --- | --- |
| Event timestamp | Tied to the business occurrence time | Client/snapshot may write wrong timestamps; late-arriving events |
| Ingestion timestamp | Processing pipeline knows when log arrived | May keep older generated events for an extra period |
| File modification time | Easy to use with rolling files | Copy/restore/append can alter `mtime` |
| Index creation/rollover time | Convenient for index lifecycle | Index age does not equal individual event age |
| Archive upload/object creation time | Bucket-level lifecycle management | A file may contain events of varying ages |

For example, suppose an event occurs on Nov 1, but a network outage delays ingestion until Nov 10. With a 30-day TTL from **ingest**, the backend may keep it until around Dec 10. With a TTL from **event time**, the retention window is shorter. You need clear definitions, synchronized clocks, and handling for late-arriving events and timestamps from untrusted sources.

**Use UTC/`Instant` when calculating age**, rather than naively subtracting local date strings. `Duration.ofDays(1)` is 24 hours; a "calendar day" in a timezone can differ across daylight saving time transitions. If business rules require expiration at the end of a day in a local timezone, use `ZonedDateTime`/`LocalDate` and explicit calendar rules.

**Exact age boundary:** `age >= TTL` makes an item eligible for expiration in many policies; actual sweeping and deletion may run later. Never promise that an event will be deleted at the exact millisecond of day 30 if the tool uses a background sweeper or index-level deletion.

## 6. Estimating Storage Capacity and Retention Budgets

Before choosing hot/warm/cold tiers, measure actual event rates and encoded sizes:

```text
raw_bytes_per_day
  = events_per_second × avg_bytes_per_event × 86,400

raw_retained_bytes
  ≈ raw_bytes_per_day × retained_days

effective_storage_bytes
  ≈ raw_retained_bytes × indexing_compression_replica_factor
```

**Illustrative example:** 1,000 events/s with an average of 500 bytes per event:

- `1,000 × 500 = 500,000 B/s`.
- `500,000 × 86,400 = 43,200,000,000 B/day` ≈ **43.2 GB/day** (decimal GB).
- Retained for 30 days: **1,296 GB ≈ 1.296 TB** of raw data.
- If the effective storage multiplier is **2×** in a given design: roughly **2.592 TB**; excluding snapshots, exports, or replicas outside that multiplier assumption.

This is an **estimate**, not a sizing guarantee: index overhead, compression, extra fields, replicas, shard count, routing metadata, ingest retries, skewed payload sizes, archive compression, and regional storage pricing all affect the actual footprint.

Questions you must answer during capacity planning:

1. Average, p95, peak, and maximum burst event rates?
2. How much volume is DEBUG/INFO/WARN/ERROR, access, audit, and security?
3. Average/p95 JSON event size, and are there large stack traces or nested fields?
4. How long is data kept in **hot**, **warm/cold**, and **archive**?
5. How much extra space do index replicas, snapshots, cross-region replication, and backups consume?
6. Monthly costs for storage, ingest, query, retrieval, network egress, API calls, and deletion?
7. If log volume triples during an incident, can queues, disks, and budgets handle it?

**Data minimization is a major lever:** dropping unnecessary request/response bodies is usually both safer and cheaper than logging everything and relying on compression/long retention. If you sample debug logs, explicitly document that sampling can lose detail and skew statistics; security/audit events have different requirements.

## 7. Hot, Warm, Cold, Frozen, and Archive

Storage tiers are not mandatory product names; they represent **trade-offs between query speed and cost**:

| Tier | Typical usage | Characteristics to consider |
| --- | --- | --- |
| **Hot** | Live dashboards, alerts, ongoing incident investigation | Fast queries, high ingest, high cost |
| **Warm** | Incidents from the past few weeks | Fewer queries, storage/index optimized |
| **Cold / frozen** | Late investigations, rare queries | Higher search/recovery latency |
| **Archive** | Long-term storage, rarely queried or compliance-driven | May not be directly queryable; requires a restore process |
| **Deleted** | Past purpose and eligible for deletion | Copies may still exist in backups/holds/other policies |

**Hot-to-cold does not automatically reduce total retention.** An event may expire from hot after 7 days, move to archive, and be completely deleted after 90 days. You need a reliable process to verify that the archive has been written/validated before deleting the hot copy if that is the intent.

Archive restore time is part of your **investigation SLO**: if a security incident requires 6-month-old data within 30 minutes, you cannot choose an archive tier whose restores normally take days without planning ahead.

## 8. In Java: Logback Rolling Files Differ from Backend Retention

For example, a Java application using Logback-classic can configure rolling files by **time and size**:

```xml
<configuration>
    <appender name="APPLICATION"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>10GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
    </root>
</configuration>
```

What this means:

- `application.log` is the active file; archives carry the date and index `%i`.
- `maxFileSize=100MB` triggers an additional rollover when the file reaches the threshold; this is **not an absolute total disk quota**.
- `maxHistory=14` with pattern `%d{yyyy-MM-dd}` means keeping roughly **14 daily archive periods**, not that every event deletes itself exactly 14×24 hours after emission.
- `totalSizeCap=10GB` helps cap total archives within what cleanup can enforce, but **should not be treated as a filesystem hard quota**. Active files, files outside the pattern, shared disks, and cleanup timing must be verified separately.
- `cleanHistoryOnStart=true` allows cleaning up archives when the appender starts; normally cleanup also runs during rollover.
- This configuration **does not apply to logs written by a gateway, Tomcat AccessLogValve, or another collector**.
- If the app runs in a Kubernetes container and files live on an ephemeral filesystem, pod deletion can lose files; check volumes and log shipping.
- Do not let multiple pods/processes write to the same regular file path without proper synchronization, file locking, and rotation design.

Logback rotation manages **local files**. When shipping logs to Elasticsearch, Loki, OpenSearch, or object storage, you must configure **backend retention** separately.

**Version note:** rolling policies, encoders, and cleanup behavior vary across Logback versions. Check the documentation for your deployed version, monitor startup status, and test actual rollover before going to production.

## 9. Log4j2 and Archive Cleanup Strategies

If you use Log4j2, `RollingFileAppender` and its rollover strategy can support time/size policies and conditional archive deletion actions. Below is a **conceptual snippet** of a strategy, not a complete Log4j2 configuration file:

```xml
<DefaultRolloverStrategy max="10">
    <Delete basePath="logs" maxDepth="1">
        <IfFileName glob="app-*.log.gz"/>
        <IfLastModified age="P14D"/>
    </Delete>
</DefaultRolloverStrategy>
```

Here:

- `max="10"` in the rollover strategy relates to the strategy's archive index counter and **should not be interpreted as "10-day retention."**
- `IfLastModified age="P14D"` selects old files by **modification time**, not by individual line event timestamps.
- `IfFileName` and `basePath` must be reviewed carefully so you do not accidentally delete files belonging to another service.
- The delete action typically runs during rollover, so exact deletion timing is not guaranteed if the application writes infrequently.
- Apply this only after properly configuring `RollingFileAppender`, policies, file patterns, and the behavior of your **actual Log4j2 version**.

Do not copy deletion rules into a directory shared by multiple applications or tenants without testing on dummy data. **A mistake in a glob or path can cause irreversible log loss.** Organizations often need centralized retention tooling and deletion permissions rather than having each app manipulate shared directories.

## 10. Containers and Kubernetes: Two Different Lifecycles

In a common setup, the Java application writes to `stdout/stderr`, the container runtime buffers logs on the node, and a collector ships them to a backend.

Kubernetes/kubelet manages container log rotation using settings such as `containerLogMaxSize` and `containerLogMaxFiles`. Per Kubernetes documentation, defaults are commonly cited as **10Mi** and **5 files**, though cluster admins may change them. These are **local node log limits**, not a 30- or 90-day backend retention policy.

Practical consequences:

1. `kubectl logs` typically reads only the current/most recent log file exposed by kubelet; it **does not replace a cluster-wide historical query tool**.
2. When a pod is deleted, evicted, or a node is lost, local logs may vanish; you must ship logs to a centralized system if long-term retention is needed.
3. The collector may fall behind before files are rotated/deleted; measure lag and dropped events.
4. Container log retention does not directly govern **files written to a custom volume** if the app uses `RollingFileAppender` inside the pod.
5. Increasing the number of files kept on a node does not replace ILM/TTL configuration in the backend, and can fill up the node disk.
6. Different services have different legal requirements, so you should not rely solely on a shared kubelet configuration.

**Practical strategy:** size the node spool window to buffer short collector outages; give the backend its own retention classes. Test collector outages, pod restarts, deployment rollouts, and disk pressure.

## 11. Elasticsearch ILM and Search Index Lifecycle

On platforms with **Index Lifecycle Management (ILM)**, a data stream or index can move through phases such as **hot, warm, cold, frozen, and delete**. Actions may include rollover, shrinking shard counts, tier migration, snapshotting, or deleting the index.

Key points to understand:

- ILM manages **indexes/backing indexes**; a delete-index action normally deletes **all documents in the index**, without inspecting individual events.
- Phase `min_age` and the age start point follow **index lifecycle/rollover semantics**, not `event.timestamp + N days` by default.
- If an index contains events with widely varying ages, deleting by index age may keep some events longer or shorter than intended on a per-event basis.
- Policies attached to an index template/data stream must be verified on new backing indexes after rollover; do not update a single index and assume future indexes will automatically comply.
- Deleting an index in the search backend does not guarantee that snapshots, archive objects, or exports are deleted at the same time.

A **conceptual** design example:

```text
logs-application-prod
  hot: 0–7 days
  warm: 7–30 days
  delete after 30 days

logs-security-prod
  hot: 0–30 days
  cold/archive: 30–90 days
  delete/hold handling after 90 days

logs-audit-prod
  separate archive and legal-hold policy
  independent permissions and documented retention
```

Across products and versions, phase transition timing may not be exact to the day, and configuration syntax varies. **Design policies at the event-class level first**, then map them to ILM, data stream lifecycle, OpenSearch ISM, or the mechanisms of your chosen backend.

### The Problem of Indexes with Mixed Retention

If DEBUG needs 7 days and AUDIT needs 365 days, **do not dump both into the same index** and expect ILM to handle each event separately. An index-level delete cannot satisfy both requirements accurately at the same time. Route by `kind` and sensitivity into appropriate data streams/indexes, or use document-level deletion with controlled cost and semantics.

## 12. Object Storage, Archives, Snapshots, and Legal Holds

Storing archives as compressed objects can reduce cost, but you must set a separate **bucket/container lifecycle policy**. When designing this:

- Define object key prefixes using `service`, `environment`, `retention.class`, ingest date, and schema version—never use raw user input in paths.
- Produce objects via a controlled process, verifying checksums/counts and readability/decompression before purging hot data if the archive must serve as the primary record.
- Storage-class transitions or object expiration lifecycles must align with recovery times and retrieval costs.
- With versioning enabled, **deleting the current version or placing a delete marker** may not remove historical versions. Check the policy for noncurrent versions.
- Cross-region replication, backups, and snapshots also need retention; do not assume deleting from the source bucket automatically removes replicas.
- Object Lock/WORM, legal holds, or retention locks can prevent early deletion. This is **a protective feature**, but it also changes how you handle personal data deletion requests.
- Encryption at rest/in transit and access control are essential when required by policy; cheap archives that are public or use overly broad shared keys pose a severe risk.

**A legal hold is not a client-supplied flag.** Only an authorized workflow may place or lift a hold; you must audit who acted, the reason, the data scope, and the timestamp. If a hold covers a broad dataset, evaluate both cost and privacy impact.

Never use `rm -rf`, index delete commands, or bulk delete APIs directly in learning examples. For retention, default testing should use **dry-run** and an "eligible" candidate list first, because deletion can be irreversible.

## 13. Standalone Java 17: Safe Retention Policy Simulation

This example uses **plain JDK 17** with no external dependencies. Its goal is to model how decisions are made:

- **HOT:** still within the fast-query window.
- **ARCHIVE:** past the hot window, but within the total retention period.
- **DELETE_ELIGIBLE:** past the total retention period and can be **considered** for deletion.
- **HOLD:** under a valid legal hold and must not be deleted on the normal schedule.
- **REVIEW_TIME:** ingestion timestamp is in the future relative to the observation clock; inspect clock/data instead of deciding to delete.

To avoid log-age errors, the demo uses **`ingestedAt`** established by the collection pipeline rather than a client-supplied event timestamp. The 2/7, 7/30, 30/90, and 90/365 policies are **simulation assumptions** only. The program **does not delete any files, indexes, or objects**.

Save as **`LogRetentionPolicyDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class LogRetentionPolicyDemo {
    enum Kind {
        DEBUG, ACCESS, SECURITY, AUDIT
    }

    enum Stage {
        HOT, ARCHIVE, DELETE_ELIGIBLE, HOLD, REVIEW_TIME
    }

    record Policy(Duration hot, Duration total) {
        Policy {
            Objects.requireNonNull(hot);
            Objects.requireNonNull(total);
            if (hot.isNegative() || total.isNegative()
                    || total.isZero() || hot.compareTo(total) > 0) {
                throw new IllegalArgumentException("Invalid retention");
            }
        }
    }

    record Entry(
            String id,
            Kind kind,
            Instant ingestedAt,
            boolean legalHold) {}

    private static final Map<Kind, Policy> POLICIES = Map.of(
            Kind.DEBUG,
            new Policy(Duration.ofDays(2), Duration.ofDays(7)),
            Kind.ACCESS,
            new Policy(Duration.ofDays(7), Duration.ofDays(30)),
            Kind.SECURITY,
            new Policy(Duration.ofDays(30), Duration.ofDays(90)),
            Kind.AUDIT,
            new Policy(Duration.ofDays(90), Duration.ofDays(365)));

    private static Stage decide(Entry entry, Instant now) {
        Objects.requireNonNull(entry);
        Objects.requireNonNull(now);
        if (entry.legalHold()) {
            return Stage.HOLD;
        }
        if (entry.ingestedAt().isAfter(now)) {
            return Stage.REVIEW_TIME;
        }

        Policy policy = POLICIES.get(entry.kind());
        Duration age = Duration.between(entry.ingestedAt(), now);

        if (age.compareTo(policy.total()) >= 0) {
            return Stage.DELETE_ELIGIBLE;
        }
        if (age.compareTo(policy.hot()) >= 0) {
            return Stage.ARCHIVE;
        }
        return Stage.HOT;
    }

    private static Entry entry(
            String id, Kind kind, String ingestedAt, boolean hold) {
        return new Entry(id, kind, Instant.parse(ingestedAt), hold);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<Entry> entries = List.of(
            entry("debug_2d", Kind.DEBUG,
                    "2026-11-08T00:00:00Z", false),
            entry("debug_7d", Kind.DEBUG,
                    "2026-11-03T00:00:00Z", false),
            entry("access_10d", Kind.ACCESS,
                    "2026-10-31T00:00:00Z", false),
            entry("security_1d", Kind.SECURITY,
                    "2026-11-09T00:00:00Z", false),
            entry("audit_hold", Kind.AUDIT,
                    "2025-01-01T00:00:00Z", true),
            entry("audit_old", Kind.AUDIT,
                    "2025-09-01T00:00:00Z", false),
            entry("future_time", Kind.ACCESS,
                    "2026-11-11T00:00:00Z", false));

        List<Stage> expected = List.of(
                Stage.ARCHIVE,
                Stage.DELETE_ELIGIBLE,
                Stage.ARCHIVE,
                Stage.HOT,
                Stage.HOLD,
                Stage.DELETE_ELIGIBLE,
                Stage.REVIEW_TIME);

        for (int i = 0; i < entries.size(); i++) {
            Entry item = entries.get(i);
            Stage actual = decide(item, now);
            if (actual != expected.get(i)) {
                throw new AssertionError("Wrong stage: " + item.id());
            }
            System.out.println(item.id() + " -> " + actual);
        }

        boolean invalidPolicyRejected = false;
        try {
            new Policy(Duration.ofDays(10), Duration.ofDays(3));
        } catch (IllegalArgumentException expectedError) {
            invalidPolicyRejected = true;
        }
        if (!invalidPolicyRejected) {
            throw new AssertionError("Invalid policy accepted");
        }

        System.out.println("invalid_policy -> REJECTED");
        System.out.println("ALL POLICY CHECKS PASSED");
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 LogRetentionPolicyDemo.java
java LogRetentionPolicyDemo
```

**Exact stdout:**

```text
debug_2d -> ARCHIVE
debug_7d -> DELETE_ELIGIBLE
access_10d -> ARCHIVE
security_1d -> HOT
audit_hold -> HOLD
audit_old -> DELETE_ELIGIBLE
future_time -> REVIEW_TIME
invalid_policy -> REJECTED
ALL POLICY CHECKS PASSED
```

How to read this:

1. `debug_2d` has just reached the 2×24-hour hot mark, so it transitions to ARCHIVE.
2. `debug_7d` has reached the exact 7-day total mark, so it enters `DELETE_ELIGIBLE`. **Eligible** does not mean already deleted.
3. `access_10d` is past the 7-day hot window but has not reached the 30-day total.
4. `security_1d` is still within the hot window.
5. `audit_hold` is old but under HOLD; normal policy is not allowed to delete it. The example assumes the hold flag was set by an authorized source.
6. `audit_old` is past 365 days with no hold, making it a deletion candidate.
7. `future_time` has an ingestion timestamp after `now`, requiring a clock or metadata check rather than treating it as a 0-day-old log.
8. A policy with 10 hot days and 3 total days is rejected upon construction.

**Intentional limitations:** `LogRetentionPolicyDemo` is only a **policy evaluator/dry-run**; it does not open files, delete data, replace ILM, or decide legal hold authority. In a real system, deletion conditions also include archive integrity, retention regulations, object versioning, deletion audit trails, and error handling.

## 14. From Policy Decision to Safe Deletion Jobs

A real log cleanup worker should not call delete immediately after a time comparison returns true. Use an explicit state machine:

```text
INVENTORY
   │
   ▼
CLASSIFY (kind, owner, sensitivity, retention class)
   │
   ▼
EVALUATE AGE (trusted timestamp + policy version)
   │
   ▼
CHECK EXCEPTIONS (legal hold, investigation, required copies)
   │
   ▼
DRY-RUN CANDIDATES + COUNTS + SIZE
   │
   ▼
APPROVE / SCHEDULE / RATE-LIMIT
   │
   ▼
DELETE / EXPIRE by backend-supported mechanism
   │
   ▼
VERIFY DELETION + RECORD AUDIT RESULT
   │
   ▼
RECONCILE COPIES, BACKUPS, EXPORTS & METRICS
```

For highly sensitive security/audit data, you may require **two-person approval** or a workflow with separated privileges. For general debug logs, a tested lifecycle rule can be automated, though policy changes still need auditing.

**Idempotency** is critical: workers may retry after timeouts. You must distinguish "does not exist because it was already deleted" from "not found due to wrong index/path/permissions." Different backends have different deletion semantics, so do not assume "exactly-once delete" without guarantees.

When errors occur:

- **Unknown policy:** quarantine or skip the candidate and raise an alert; do not fall back to deleting with the shortest default.
- **Clock skew:** halt deletion decisions for items with anomalous timestamps.
- **Unverified archive:** do not delete the sole copy if a mandatory archive is required.
- **Legal hold present:** block deletion and record the controlled reason; do not allow regular operators to clear the flag themselves.
- **Missing delete permissions:** log the error and notify administrators; do not auto-escalate credentials.
- **Delete timeout:** reconcile state before retrying to avoid deleting the wrong object after a rollover.
- **Unusual mass deletion:** cap maximum bytes/indexes per batch and require alerts/approval.

## 15. Retention, Privacy, Security, and Legal Compliance

Logs can contain personal data: IP addresses, request paths, emails, device IDs, user IDs, access patterns, and audit actors. Therefore, retention is not just a storage-capacity issue.

Core principles:

- **Log minimally:** do not log tokens/passwords/cookies, raw request/response bodies, or sensitive queries "just in case."
- **Clear purpose:** retention durations must match debugging, operations, security, or audit purposes; the more sensitive the data, the stricter the review.
- **Access control:** only authorized personnel should view security/audit logs; separate permissions for search/export, changing retention, and deleting.
- **Encryption:** encrypt at rest and in transit where required, manage keys properly, and log access to the store.
- **Retain and delete:** keep data long enough to meet obligations without keeping it forever; handle legal holds and deletion requests through processes approved by legal/security.
- **Do not apply one retention period across all tenants** if contracts, data residency, or data classifications differ; identify owners and namespaces.
- **Account for backups, snapshots, and exports:** copies outside the backend usually need the same policy or a separately documented one.

Never claim that a specific number such as **30, 90, or 365 days is mandatory under GDPR or Vietnamese law** for all log types. Obligations depend on purpose, data subjects, industry, contracts, jurisdiction, and special cases; legal/security teams must review them.

**Conflict between legal hold and data subject deletion:** do not resolve this on your own by deleting everything or keeping everything forever. Establish a workflow with legal basis, clear scope, audited decisions, and the ability to handle each copy appropriately.

## 16. Immutable Retention and Error Correction

Audit logs may be stored in WORM/Object Lock or append-only systems to prevent unauthorized deletion or tampering. Understand the trade-offs:

1. **Retention locks** can block deletion before the scheduled date, even if an event is discovered to contain a secret. This makes **data minimization at the source** even more critical.
2. Do not use a single immutable bucket for DEBUG logs with payloads, access logs, and audit logs combined.
3. When fixing a schema or incorrect information, you can emit a **correction/superseding** event instead of modifying the original record if audit rules require immutability.
4. Changing retention periods or lifting a legal hold must require proper authority, a reason, and an audit trail—not an open application API.
5. If a secret leaks into an immutable log, handle the token/credential (revoke/rotate), access controls, copy scope, and incident policy; do not assume you can immediately physically delete it.

**Immutable ≠ always correct.** No signature or storage lock makes an actor ID taken from a spoofed header authentic. Log accuracy starts at the event source; storage locks only protect what was written.

## 17. Snapshots, Backups, Replicas, and Deletion Cycles

A common mistake: a dashboard no longer finds a log because the index TTL deleted it, and someone declares "the data is completely deleted." Yet the log may still exist in:

- Index snapshots or previous days' backup files.
- Cross-cluster/cross-region replication.
- Object storage versioning and noncurrent versions.
- Collector spools or unrotated application files.
- Exported CSVs, notebooks, BI reports, or ticket attachments.
- Cold archives or data warehouses.
- DR restore environments or test environments.
- Caches with a different TTL than the primary backend.

Define **deletion verification** per layer:

| Layer | Verification question |
| --- | --- |
| Hot index | Are expired indexes/backing indexes or documents still queryable? |
| Archive | Do objects still exist, or are they under hold, versioning, or noncurrent retention? |
| Snapshot | Have snapshots expired under their own policy? |
| Source file/node | Do rolling files or the container runtime still hold copies? |
| Collector buffer | How long do retry/spool events persist? |
| Export | Do users have downloaded links/files, and what is the expiry/revocation? |
| Backup restore | Does expired data reappear during a restore? |

For systems with immutable backups, you may need a policy to **restrict usage or re-process expired data upon restore**, rather than promising every byte vanishes immediately. This process must be documented honestly in operational runbooks.

## 18. Cost Warning: Increasing Retention Is Not Free

Log costs can grow along three axes:

1. **Ingest volume:** events/s × event size; enabling DEBUG or large stack traces drives this up sharply.
2. **Storage duration:** amount of data retained and the cost of the storage tier.
3. **Query & recovery:** many indexes, unoptimized shards, archive restores, and retrieval fees.

**Distinguish optimizing retention from dropping important logs.** You can:

- Reduce unnecessary DEBUG/TRACE logging in production.
- Avoid logging full bodies/headers, especially tokens and PII.
- Choose valuable structured fields and route templates instead of raw URLs.
- Use metrics/aggregates for high-frequency events when individual lines are not needed.
- Tier into hot/cold instead of keeping everything hot.
- Compress and choose archive formats suited to your search/restore tools.
- Use shorter retention for debug events proven to have low value.
- Keep security/audit logs under their own policy; do not arbitrarily sample events that must be preserved.

**Sampling changes statistical meaning.** If you store 100% of errors but only 10% of successful requests, the error rate calculated from stored access logs will be skewed unless you apply weighting or use independent metrics.

## 19. Metrics for Monitoring Retention

Having a retention policy on paper is not enough; you need to know enforcement is actually running.

| Metric / signal | What it checks |
| --- | --- |
| `logs_ingested_bytes_total` | Ingest volume; detects sudden spikes |
| `logging_events_dropped_total` | Logs lost at producer/collector before retention |
| `retention_candidates_total` | Number of eligible events/indexes/objects |
| `retention_deleted_total` | Count deleted, broken down by class/backend |
| `retention_delete_errors_total` | Permission, timeout, policy, or storage errors |
| `retention_backlog_bytes` | Volume that should have expired but is not yet processed |
| `oldest_expired_item_age` | Lag in cleanup execution |
| `archive_transfer_lag` | Events past hot window not yet properly archived |
| `archive_verify_failures_total` | Transferred objects with checksum/count mismatches |
| `legal_hold_items_total` | Scope of holds and their impact on retention/cost |
| `storage_used_bytes` / `quota_remaining` | Risk of full disk or budget overrun |
| `restore_test_success` | Whether archives can actually be read/restored during an investigation |
| `log_access_export_events` | Who is querying/exporting sensitive data |

Metric names are **schema suggestions**; not every backend exposes them out of the box. When designing labels, never put `request_id`, `trace_id`, `user.id`, or object keys into unbounded-cardinality labels.

### Example SLOs

- "95% of application events are queryable in the hot tier within ≤ 2 minutes of ingest" is an **ingestion/query SLO**, separate from retention.
- "No application index remains expired for more than 24 hours without processing, excluding authorized holds" is an **enforcement SLO**.
- "Restore a sample of last month's archive within 2 hours" is a **recovery SLO**.
- "No event that must be retained is deleted prematurely" is a **safety invariant**, not merely a cost optimization.

These SLO values are illustrative; they must be measured and agreed upon with operations teams.

## 20. Testing Retention Policies with a Fixed Clock

Do not test TTLs by calling `Thread.sleep(...)` for days. Use `Clock.fixed(...)` or pass `Instant now` as in `LogRetentionPolicyDemo`.

Important boundary tests:

| Scenario | Expectation |
| --- | --- |
| Newly ingested log | HOT |
| Age `hot - 1 ms` | Still HOT |
| Age exactly `hot` | ARCHIVE |
| Age `total - 1 ms` | Not yet eligible for deletion |
| Age exactly `total` | DELETE_ELIGIBLE |
| Legal hold present even if very old | HOLD |
| Ingestion time in the future | REVIEW_TIME/quarantine per policy |
| Policy hot greater than total | Validation rejects |
| Event missing `retention.class` | Do not delete under an overly short default |
| Timestamp parse error/clock drift | Alert; do not auto-queue for deletion |
| Late-arriving event | Age rule consistent with ingestion/event time |
| Restore archive before expiration | Data intact and decryptable/decompressible |
| Policy change 30 → 7 days | Dry-run impact check before applying |
| Snapshots/versioned objects present | Deleting hot must not report full deletion |
| Worker retry on timeout | No accidental deletion; idempotent/reconciled |
| Hold lifted with approval | Re-evaluated under current policy without bypassing audit |

Unit tests only evaluate **decision logic**. Integration tests must run against dummy files/indexes/objects in a test namespace, verifying cleanup permissions, schedules, formats, versioning, and restore capability. **Never use real production data to test delete commands.**

### Testing Actual Rollover

With Logback/Log4j2, generate many small dummy events in an isolated environment to trigger rollover:

1. Verify active file and archive patterns are valid.
2. Confirm `maxFileSize`/period rollover matches the backend version in use.
3. Create old archives using fixtures with controlled timestamps/metadata and measure cleanup policy, without multi-day sleeps.
4. Verify files outside the glob or in other directories are not deleted.
5. Test behavior on restart, long periods without rollover, and permission denied.
6. Confirm real files have been shipped by the collector before deletion if required.

## 21. Common Retention Pitfalls

| Symptom | Cause | What to check |
| --- | --- | --- |
| Old Logback files remain past `maxHistory` | Cleanup runs at rollover/startup and hasn't triggered | Check policy, rollover timing, `cleanHistoryOnStart` |
| Disk full despite `totalSizeCap` | Active files, other files, cleanup hasn't run | Measure real disk and quota; do not treat archive cap as hard limit |
| Backend keeps logs longer than expected | ILM/index age differs from event age | Check rollover timing, phases, and index policy |
| Some events lost too early | Index mixes event ages; index-level delete | Split indexes by class/period; account for late arrivals |
| `kubectl logs` misses older logs | Node log rotation or pod deleted | Query centralized backend; do not rely on node history |
| Logs still exposed after index deletion | Snapshots, exports, archives, or backups remain | Inventory all copies and their policies |
| Audit logs kept as briefly as debug | Classified by root logger level | Route by `kind`/approved audit policy |
| Policy deletes wrong bucket/objects | Glob/prefix too broad | Dry-run, least privilege, canary, and approval |
| Delete fails due to hold | Immutable retention/legal hold | Check authority; do not auto-remove hold |
| Newly ingested old event deleted immediately | Aged by event time without late-arrival handling | Pick trusted reference point and late-arrival policy |
| Config changed but new data still wrong | Template/data stream not applied properly | Check bootstrap, rollover, and effective policy |
| Archive exists but cannot be restored | Missing keys, corruption, or wrong codec/schema | Restore drills, checksums, key management |
| Storage saved but evidence missing | Sampling/retention too short | Review incident detection window and audit requirements |
| Hot deletion doesn't free enough space | Replicas, snapshots, tombstones, retention job hasn't run | Measure storage state and reclaim time |
| Retention worker crashes backend | Mass index/object deletion in one batch | Throttle, batch, quota, and monitor |
| Backup restore brings back expired logs | Restore did not re-apply lifecycle | Add post-restore policy re-application/reconciliation step |

## 22. Managing Retention Changes Safely

Changing retention from 90 days down to 14 days can destroy large volumes of evidence. Do not simply edit a config variable and deploy.

Recommended process:

1. **State the purpose of the change:** cost, investigation needs, regulation, or data tier change.
2. **Inventory storage locations and owners**, classifying security/audit, PII, and copies.
3. **Document current and target policies**, age reference points, and exceptions/holds.
4. **Dry-run** against real metadata to count indexes/objects/GB to be tiered or deleted.
5. **Assess impact on incident windows, restore SLOs, legal holds, and privacy requests**.
6. **Obtain approval** from authorized owners; for audit/immutable storage, verify whether the change can even apply.
7. **Small rollout** in one service/environment/test namespace and verify no unintended deletions.
8. **Monitor** backlog, errors, data reduction, lag, cost, and dropped logs.
9. **Audit** who changed the policy, when, which version, and why.
10. **Post-deployment review** to confirm files, indexes, archives, snapshots, and exports all match the new scope.

When increasing retention, budget and access permissions must also be reviewed. When decreasing retention, the focus is **never accidentally deleting data still under obligation**.

## 23. Example Policy Design for a Java Service

Suppose a `checkout-api` service runs in Kubernetes and sends structured JSONL through a collector to a search backend:

```text
Checkout Java service
  ├─ application/debug log       → logs-app-prod      → hot 7d, total 30d
  ├─ access log                  → logs-access-prod   → hot 7d, total 30d
  ├─ security events             → logs-security-prod → hot 30d, total 90d
  └─ audit events                → audit archive      → separate hold/retention
         │
         └─ stdout on pod → node spool → collector → routed destinations
```

**Sample responsibility matrix:**

| Component | Responsible party | Verification criteria |
| --- | --- | --- |
| Java logger/encoder | Application team | No secrets logged; events have valid `kind`/schema |
| Container stdout rotation | Platform team | Node spool does not fill; collector keeps up |
| Collector routing | Observability team | Correct service/tenant classification; no double ingest |
| Search ILM/data stream | Backend team | Delete phase and index age match class |
| Audit archive/hold | Security/compliance team | Permissions, reconciliation, retention, and holds accurate |
| Backup/snapshot | DR team | Recovery drills and copy TTLs |
| Dashboard/export | Data owner | RBAC, link expiry, and export deletion workflow |

Suppose the p99 incident detection time is a few weeks: 7 days hot may still be reasonable if warm/archive can be queried quickly when needed, or it may be insufficient if responders need instant access to incidents from 20 days ago. **Retention and query availability must be designed together.**

## 24. Implementation Checklist

- [ ] Inventoried every place log data exists: app files/stdout, collector, search, archive, snapshots, exports.
- [ ] Classified logs by purpose/kind, sensitivity, and owner; not solely by severity.
- [ ] Policy specifies hot duration, total duration, TTL start clock, exceptions/holds, and deletion mechanism.
- [ ] Durations approved by business, security, contracts, and legal; example numbers not treated as rules.
- [ ] Calculated raw bytes, index/replica/snapshot factors, and peak ingest.
- [ ] File rotation (Logback/Log4j2) configured and tested in practice.
- [ ] Kubernetes node retention **separated** from backend retention, and both verified.
- [ ] Index/data stream policies match log groups and rollover timing.
- [ ] Archives verified by checksum/count and test-restored before deleting required hot copies.
- [ ] Legal hold/immutable retention has proper authority, auditing, and exception-handling rules.
- [ ] Sensitive data not collected unnecessarily; RBAC, encryption, and export retention in place.
- [ ] Tested expiry boundaries, late arrivals, clock skew, worker retries, and error-handling policies.
- [ ] Delete jobs have dry-run, blast-radius limits, approvals where needed, and change/deletion audit logs.
- [ ] Metrics exist for backlog, delete errors, archive lag, expired data, and storage quotas.
- [ ] Restore/reconcile process ensures expired data does not unintentionally return after disaster recovery.
- [ ] Verified security/audit events are not dropped merely to cut costs.

**Remember:** log retention is a **data lifecycle rule**, not just a file rotation setting. To operate it properly, you must know **which logs to keep, when age starts, how long hot/archive lasts, who can hold or delete, and how every copy is handled**. Use dry-runs, boundary testing, and monitoring to avoid both extremes: deleting too early or keeping data forever.

### References

- [Logback — RollingFileAppender, maxHistory, totalSizeCap, cleanHistoryOnStart](https://logback.qos.ch/manual/appenders-rolling.html)
- [Apache Log4j2 — RollingFile Appender](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [Elastic — Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management)
- [Elastic — Index lifecycle phases](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management/index-lifecycle)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Java 17 — java.time.Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
