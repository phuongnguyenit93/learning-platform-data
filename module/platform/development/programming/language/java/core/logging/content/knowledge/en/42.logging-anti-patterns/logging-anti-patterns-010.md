# Missing a Retention Strategy — Logging Anti-pattern in Java

## 1. What Is Retention and Why Is Missing a Strategy an Anti-pattern?

**Log retention** is the set of rules defining **which types of logs are kept, where they are stored, for how long, who can access them, when they move to another storage tier, and when they must be deleted or undergo end-of-life processing**. A complete strategy also defines exceptions such as legal holds, evidence preservation obligations, personal data erasure requests, backups, snapshots, and how deletion is verified to have actually occurred.

The **“missing a retention strategy” anti-pattern** occurs when an application keeps writing logs without consistent answers to those questions. The consequences can go in either direction:

- **Retaining too long:** full disks, bloated indexes, rising cloud costs, secrets/PII persisting indefinitely, and a larger blast radius during a data incident than necessary.
- **Deleting too early:** loss of evidence for incident investigation, auditing, attack detection, reconciliation, or legal obligations.
- **Inconsistent retention:** application files only keep 7 days while object archives keep 5 years, yet dashboards assume all copies have expired.
- **No clear owner:** nobody knows where the policy came from, who is allowed to change it, or who must handle deletion job failures.
- **No verification:** a “rotate daily” configuration is mistaken for “data deleted on schedule.”

Example:

~~~text
Java service
  |
  +-- application.log (growing forever)
  |
  +-- app.2026-11-01.log.gz (archives forever)
  |
  +-- stdout -> container runtime -> log shipper
                                    |
                                    +--> search index
                                    +--> object storage
                                    +--> backup/snapshot
~~~

Merely setting the log level to INFO or enabling a rolling appender is not an end-to-end retention strategy. If an application writes to both a file and stdout, the two paths can have **independent lifecycles**. What has already been shipped to a collector does not automatically disappear when the application deletes its local copy.

**Goal of this article:** identify gaps, design policies by data category and risk, configure Logback/Log4j 2 appropriately, control lifecycles across collectors/indexes/archives, and test and measure enforcement. Do not use this article as a guide to blindly delete evidence that still needs to be preserved.

## 2. Easily Recognizable Symptoms in Production

Some signs include:

1. The application.log file only grows, with no rotation or archive cleanup.
2. Files like app.2020-...log.gz exist, but nobody knows whether they are still needed.
3. Only a size limit is configured with no retention duration; low-traffic systems may retain data for a very long time.
4. Only a file count limit is configured with no time limit; how many days of logs are kept fluctuates with traffic.
5. Logback maxHistory is configured, but nobody has ever tested whether old archives are actually cleaned up.
6. Log4j 2 has rollover configured, but lacks a Delete action or a matching condition that fits the file names.
7. The search index has an ILM/ISM policy, while archives/snapshots are kept indefinitely.
8. Retention across dev, staging, and production is not version-controlled or consistent by data class.
9. Audit and debug logs are stored under the same policy, even though their purposes and obligations are completely different.
10. There are no alerts for free disk space, index storage, lifecycle errors, or log ingestion failures.
11. A DEBUG/TRACE bug causes log volume to spike, filling the disk in a few hours.
12. A personal data erasure request is marked “completed” simply because files on the server were deleted, even though copies remain in the collector and backups.
13. After restoring a backup, previously deleted logs reappear because there is no deletion ledger/tombstone.
14. Nobody can state the policy version, approver, and deletion completion evidence.
15. An operator has to run manual delete commands directly on the server to reclaim disk space because there is no runbook.

**Do not look only at file count.** A single active file can be massive; an archive with few files can hold years of data, or millions of small objects in object storage can incur significant cost.

## 3. Distinguishing Rotation, Retention, Archival, and Deletion

| Concept | Meaning | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| **Rotation/rollover** | Switches the active file to an archive by date/size | Does not necessarily delete old archives |
| **Retention** | Defines the duration/conditions for keeping or ending lifecycle | Does not prove the deletion job actually ran |
| **Archival** | Moves data to long-term or cheaper storage | Does not mean “allowed to keep forever” |
| **Compression** | Compresses data to save space | Does not limit storage duration |
| **Purge/deletion** | Removes data per policy and backend capabilities | Does not guarantee all copies/versions are handled |
| **Legal hold** | Preserves data with valid grounds even after normal retention expires | Must not be enabled arbitrarily to keep all data |
| **Backup** | Recovery copy for incidents | Does not replace the operational store's policy |
| **Masking/anonymization** | Reduces or removes identifiability | Does not always erase original bytes |

For example, a daily rotation configuration might produce:

~~~text
app.log
app.2026-11-07.log.gz
app.2026-11-08.log.gz
app.2026-11-09.log.gz
...
~~~

However, without a cleanup mechanism or lifecycle limit, data continues to accumulate. Conversely, deleting all archives after exactly one day without assessing needs can cause critical logs to vanish before operations even notices an incident.

A viable policy must answer **when to write**, **when to archive**, **when to transition tiers**, and **when to delete conditionally**. There is no single Java property that applies to all of these steps.

## 4. Determining Which Logs to Keep: Classification by Purpose

There is no single retention day count that is “right for every system.” Retention periods must be determined from operational needs, legal/audit requirements, privacy risks, cost, and data availability.

| Log Group | Purpose | Suggested Policy Thinking |
| --- | --- | --- |
| Diagnostic DEBUG/TRACE | Short-term analysis, usually high volume | Keep short, enable with bounds, avoid sensitive payloads |
| Application INFO | Request/operation status, troubleshooting | Keep aligned with support windows and investigation needs |
| ERROR/WARN | Investigating failures and degradation | Needs enough time for detection, tracking, and analysis |
| Access log | HTTP access, network behavior | Consider privacy and security needs |
| Security events | Failed logins, access blocks, permission changes | May require retention/monitoring per regulations and risk |
| Audit trail | Evidence of critical activities | Dedicated integrity, access, duration, and legal hold rules |
| Infrastructure logs | Kubernetes, JVM, OS, proxy, database | Have independent sources, owners, and storage from the app |
| Business event log | Business event data used to reconstruct state | Cannot arbitrarily apply DEBUG log policies |

**Hypothetical example used for learning materials**, not a mandatory rule: DEBUG 2 days, application 14 days, security 30 days, and audit 90 days. These are sample figures to explain the design; an organization **must not apply these numbers to production without domain and compliance approval**.

If laws or contracts require preserving evidence longer, a total storage cap cannot silently delete it early. When capacity is at risk of being exceeded, infrastructure/budget must be adjusted, data moved to another tier, or the policy updated through an authorized process; never break retention obligations just to free disk space.

## 5. Creating a Retention Policy with Clear Ownership

A policy needs at least:

- **Data classification:** log type, service/tenant, and whether PII/secrets are present.
- **Purpose:** why it is stored and who uses it.
- **Retention start:** whether counted from event occurrence, file close, index creation, rollover, ingest, or another milestone; must be explicitly stated.
- **Duration/expiry:** retention period and exceptions; never use “delete when disk is full.”
- **Storage tiers:** local, centralized hot/warm/cold, object/archive, snapshot/backup.
- **Access control:** who can read, export, download, restore, or delete.
- **Hold/exceptions:** grounds for hold, approving owner, review schedule, and scope.
- **Deletion semantics:** deleting records, files, indexes, object versions, or encryption keys; what outcome counts as complete.
- **Verification:** post-action verification; handling job failures or data drift.
- **Ownership:** who is authorized to change the policy and who receives alerts.
- **Change history:** policy version, rationale, effective date, and migration plan for existing data.

Example policy structure (an operational representation only, not a Logback configuration file):

~~~yaml
policyVersion: "logging-retention-v3"
service: "order-service"
classes:
  diagnostic:
    retention: "P2D"
    owner: "platform-observability"
  application:
    retention: "P14D"
    owner: "platform-observability"
  security:
    retention: "P30D"
    owner: "security-operations"
  audit:
    retention: "P90D"
    owner: "compliance-security"
holds:
  requireApproval: true
  storeHoldDecisionsSeparately: true
verification:
  requireDeletionEvidence: true
~~~

**Note:** This YAML does not configure any lifecycle by itself. It is a **versioned specification** to be translated into appender configurations, index lifecycles, archive policies, and operational procedures for each backend.

## 6. Assessing Data Lifecycle at Every Storage Point

An application log may be stored as follows:

~~~text
Java Application
  |
  +--> Logback/Log4j 2 file appender
  |       +--> active file
  |       +--> rolled/compressed archives
  |
  +--> stdout
          |
          v
     container runtime logs
          |
          v
      Filebeat / Fluent Bit / OTel Collector
          |
          +--> buffer/queue/retry
          |
          +--> search index / data stream
          |
          +--> object storage/archive
                    |
                    v
               backup/snapshot/export
~~~

Deleting archives in /var/log/my-service **does not delete** documents already indexed. An ILM policy that deletes an index **does not delete** backups/snapshots, downloaded files, or support team exports. Data can be replayed from archives and **resurrected** after being deleted from the index.

You need a data inventory for each destination:

| Storage Location | Key Questions |
| --- | --- |
| Active application file | Is there a size limit, are file handles open, who is responsible for rotation? |
| Rotated archives | What is the age/size policy? When does cleanup run? |
| Container logs/stdout | Does the runtime/node have its own rotation? What happens to data when a pod is lost? |
| Agent buffers/spool | How long does the disk queue retain data when the collector is offline? |
| Central index | Is ILM/ISM/data stream lifecycle actually applied? |
| Object archive | Are versioning, lifecycle rules, or Object Lock/WORM enabled? |
| Snapshot/backup | Does it have separate retention, and must restores honor deletion requests? |
| Export/manual copy | Do people who export logs have separate deletion policies and access controls? |

An inventory table should not just list paths; it must include owner, access permissions, effective retention, verification method, and exception handling.

## 7. Missing Retention Leads to Uncontrolled Storage Growth

Suppose a service generates an average of **5 GB of logs/day**. Over 30 days, a single uncompressed copy is roughly **150 GB**; if the system replicates the same volume across three equivalent physical copies, that is around **450 GB** before accounting for other replication overhead, indexing, snapshots, and actual compression.

This is only a simple model: compression ratios, duplicate log rates, index metadata, replicas, and traffic bursts make real costs differ. Still, it shows why “free disk space remaining” is not a policy.

You need to calculate:

~~~text
Estimated storage
  = average bytes/day
  x target retention days
  x effective copy/replication factor
  + index/metadata overhead
  + reserve for burst and recovery
~~~

Measure **bytes/day by service, level, and destination**, adding scenarios for:

- normal INFO;
- DEBUG/TRACE temporarily enabled for investigation;
- downstream failures causing thousands of ERROR/stack traces per second;
- collector disconnection causing local buffers to grow;
- replay/backfill of historical data;
- backup snapshots or migrations holding two copies simultaneously.

**Capacity is a physical constraint, not a substitute for legal retention.** If data is required to be kept, exceeding budget requires scaling capacity or moving to an appropriate tier, not silently deleting data to stay under a cap.

## 8. Standalone Java 17+: Evaluating Retention Without Deleting Data

The following example teaches how to **classify a log segment as a processing candidate** based on log kind, timestamp, and protection status. The program intentionally **does not read or delete real files**: this is safe for learners and avoids turning an introductory example into an evidence-deletion tool.

Hypothetical data: evaluation time is **2026-11-10T00:00:00Z**, with sample policy DEBUG 2 days, APP 14 days, SECURITY 30 days, AUDIT 90 days. A segment currently open for writing will not be selected for cleanup; a segment under legal hold is kept even if it has passed its normal age threshold.

Create **RetentionPolicyDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public class RetentionPolicyDemo {
    enum Kind { APP, DEBUG, SECURITY, AUDIT }

    record Segment(String name, Kind kind, Instant created,
                   long bytes, boolean legalHold, boolean active) {}

    record Decision(String action, String reason) {}

    // ILLUSTRATIVE VALUES ONLY, NOT MANDATORY RETENTION.
    static final Map<Kind, Duration> POLICY = Map.of(
        Kind.APP, Duration.ofDays(14),
        Kind.DEBUG, Duration.ofDays(2),
        Kind.SECURITY, Duration.ofDays(30),
        Kind.AUDIT, Duration.ofDays(90)
    );

    static Decision evaluate(Segment segment, Instant now) {
        if (segment.active()) {
            return new Decision("SKIP", "active-file");
        }
        if (segment.legalHold()) {
            return new Decision("HOLD", "legal-hold");
        }

        Duration retention = POLICY.get(segment.kind());
        if (retention == null) {
            throw new IllegalArgumentException("No policy");
        }

        Instant expiry = segment.created().plus(retention);
        return now.isBefore(expiry)
            ? new Decision("KEEP", "within-retention")
            : new Decision("CANDIDATE", "expired");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<Segment> samples = List.of(
            new Segment("app-old.log", Kind.APP,
                Instant.parse("2026-10-20T00:00:00Z"),
                2048, false, false),

            new Segment("app-new.log", Kind.APP,
                Instant.parse("2026-11-05T00:00:00Z"),
                1024, false, false),

            new Segment("debug-old.log", Kind.DEBUG,
                Instant.parse("2026-11-01T00:00:00Z"),
                512, false, false),

            new Segment("security-held.log", Kind.SECURITY,
                Instant.parse("2026-09-01T00:00:00Z"),
                8192, true, false),

            new Segment("audit-active.log", Kind.AUDIT,
                Instant.parse("2026-08-01T00:00:00Z"),
                5120, false, true)
        );

        int candidates = 0;
        int keep = 0;
        int holds = 0;
        int skipped = 0;
        long candidateBytes = 0;

        for (Segment segment : samples) {
            Decision decision = evaluate(segment, now);
            System.out.println(segment.name() + " -> "
                    + decision.action() + " ("
                    + decision.reason() + ")");

            switch (decision.action()) {
                case "CANDIDATE" -> {
                    candidates++;
                    candidateBytes += segment.bytes();
                }
                case "KEEP" -> keep++;
                case "HOLD" -> holds++;
                case "SKIP" -> skipped++;
                default ->
                    throw new IllegalStateException("Unexpected action");
            }
        }

        System.out.println("summary candidates=" + candidates
                + " keep=" + keep
                + " holds=" + holds
                + " skipped=" + skipped
                + " candidateBytes=" + candidateBytes);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac RetentionPolicyDemo.java
java RetentionPolicyDemo
~~~

**Deterministic stdout**:

~~~text
app-old.log -> CANDIDATE (expired)
app-new.log -> KEEP (within-retention)
debug-old.log -> CANDIDATE (expired)
security-held.log -> HOLD (legal-hold)
audit-active.log -> SKIP (active-file)
summary candidates=2 keep=1 holds=1 skipped=1 candidateBytes=2560
~~~

### Why These Results?

- **app-old.log:** APP 14 days from Oct 20 is before Nov 10, so it has passed the sample retention period and becomes CANDIDATE.
- **app-new.log:** only 5 days old, not yet at the 14-day mark, so KEEP.
- **debug-old.log:** past the 2-day sample limit, so CANDIDATE.
- **security-held.log:** although old, legalHold=true is active, so HOLD.
- **audit-active.log:** simulates a file currently being written; SKIP to avoid operating on an active writer.

The two candidates total **2048 + 512 = 2560 bytes**. **CANDIDATE does not mean it can be deleted immediately.** Before actual deletion, you must verify owner, retention grounds, snapshots/backups, classification policy, file identity, symlinks, permissions, and the deletion job; this example only classifies.

### Limitations to Understand Clearly

1. The created field is the **segment metadata timestamp in the example**, not proof that every event in the file shares the same date. Real log files can contain records spanning multiple days.
2. Some backends delete by **lastModified** or rollover/index creation time, not necessarily by individual event timestamps. You must use the same semantics as the approved policy.
3. A single boolean legalHold is insufficient for production: holds must be managed by a trusted system with approval, scope, and review periods; never let clients pass the flag themselves.
4. The program does not touch the filesystem, has no concurrent workers, and does not handle object locks, WORM, replicas, or deletion permissions.
5. If the same file mixes mandatory audit logs and debug logs, **you cannot apply a whole-file deletion decision** just because one part expired; you must design separated streams.
6. The 2/14/30/90-day retention values are learning examples only, **not legal recommendations or mandatory standards**.
7. The evaluate function uses a fixed timestamp for reproducible results; real systems must define a trusted clock source and timezone when computing cutoffs.
8. Keep/delete decisions must be **reconciled across every storage destination**, not just an in-memory list of segments.

## 9. Logback: maxHistory, totalSizeCap, and cleanHistoryOnStart

In Java applications using Logback Classic, **RollingFileAppender** combined with **TimeBasedRollingPolicy** can create daily archives and clean up history. Example **logback.xml** specifically for **application logs without long-term retention obligations**:

~~~xml
<configuration>
  <appender name="APP"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>/var/log/my-service/app.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>
        /var/log/my-service/archive/app.%d{yyyy-MM-dd}.log.gz
      </fileNamePattern>
      <maxHistory>14</maxHistory>
      <totalSizeCap>2GB</totalSizeCap>
      <cleanHistoryOnStart>true</cleanHistoryOnStart>
    </rollingPolicy>

    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="APP"/>
  </root>
</configuration>
~~~

**Adjust and test on your actual Logback version**; the path in fileNamePattern can be written on a single line if XML/whitespace handling in your environment produces an unexpected path. When deploying, use verified paths and permissions.

Meaning according to the Logback manual:

- **fileNamePattern** with %d{yyyy-MM-dd} means archiving on a daily cadence per the pattern.
- **maxHistory=14** specifies keeping at most **14 daily history periods** of archives. It does not set retention on collectors/indexes, and it is not a millisecond-exact timer for every record.
- **totalSizeCap=2GB** limits the total size of archives under this policy, deleting older archives when the cap is exceeded. It requires maxHistory to be set, and the time limit is applied before the total size cap. **The cap can delete data earlier than expected** if log volume spikes.
- **cleanHistoryOnStart=true** allows history cleanup to run when the appender starts; normally cleanup runs on rollover. Useful for low-volume jobs, but not a substitute for verification.
- Logback may clean up archives **asynchronously**. Do not treat calling log.info() or seeing a new file as proof that all old archives have been deleted.

**Warning:** if business requirements mandate keeping at least 14 full days, a totalSizeCap that is too small can conflict with that requirement. Provision sufficient storage and an appropriate policy. Do not attach the same APP appender to audit logs that must be kept longer while only retaining 14 periods.

**Rollover is not an absolute cron job.** Logback typically triggers rollover when a new event arrives after the time boundary, so it can be delayed when the application logs infrequently. When deletion deadlines must be strictly enforced, use an independent lifecycle and measure in practice.

## 10. Log4j 2: Rolling and Conditional Delete Actions

Log4j 2 Core supports **RollingFile** with TriggeringPolicy/rollover strategies and actions such as **Delete**. If the pattern creates daily archives without an appropriate deletion condition, data can continue to be retained even as new files are generated.

Example **log4j2.xml** using **DirectWriteRolloverStrategy** with daily files and an action that only selects archive files matching the name and old enough by lastModified:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <RollingFile name="APP"
       filePattern="/var/log/my-service/archive/app.%d{yyyy-MM-dd}.log.gz">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
      <Policies>
        <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
      </Policies>
      <DirectWriteRolloverStrategy>
        <Delete basePath="/var/log/my-service/archive" maxDepth="1">
          <IfFileName glob="app.*.log.gz"/>
          <IfLastModified age="P14D"/>
        </Delete>
      </DirectWriteRolloverStrategy>
    </RollingFile>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="APP"/>
    </Root>
  </Loggers>
</Configuration>
~~~

This is a **technical template for cleanable archives**, and the P14D value carries no legal authority. Verify your exact Log4j 2 version, paths, application permissions, active files, timezone, and rollover scenarios. Before running against real data, test in an isolated directory with dummy files to avoid accidental deletion.

Key points:

- **TimeBasedTriggeringPolicy** determines when to roll over by time; it **is not a log deletion rule by itself**.
- **DirectWriteRolloverStrategy** uses filePattern directly for output files; this example does not declare a separate active fileName.
- **Delete** should be restricted to a **narrow basePath**, paired with IfFileName and IfLastModified conditions; never set basePath to a system directory or broad root.
- **IfLastModified age="P14D"** evaluates the **file's mtime**, not the events inside the file and not legal retention obligations.
- These actions are tied to rollover activity; with low log volume they may not clean up at the expected time and must be tested empirically.
- If using symlinks, recursion, or the followLinks option, assess the risk of Delete escaping its intended scope. In this example configuration, followLinks is not enabled.
- If evidence must be preserved, never allow the Delete action to touch protected audit storage paths.

Log4j 2 can also limit archive counts via **DefaultRolloverStrategy max** in configurations using a %i index, but **limiting file count is not equivalent to days**, especially when volume varies. Read the manual for your specific strategy rather than assuming max="14" means 14 days in every pattern.

## 11. Rolling Policy and Retention Policy Are Not the Same Thing

The same example can be misunderstood:

~~~text
Config A: rotate daily, keep 14 files
Config B: rotate at 100MB, keep 14 files
Config C: daily and max 2GB archives
~~~

A may approximate 14 daily periods **if** the archive logic is genuinely daily. B only limits **file count**, which could equal a few minutes during a log storm or several months when the service is quiet. C caps size, which can delete logs prematurely if throughput increases.

Therefore, a policy must state its objectives clearly:

- **Minimum retention:** how long data **must remain available** when a retention obligation exists.
- **Maximum retention:** how long data **must not be kept beyond** when no grounds exist.
- **Operational capacity cap:** safe maximum storage for local disk/archival tiers.
- **Rollover interval:** file-splitting schedule for operations, not proof of expiry.

When two objectives conflict, you need **escalation and a different tier design**, not “pick the smaller number” and clean up uncontrollably. Mandatory evidence can be shipped to protected storage before local cleanup, then managed under that destination's retention.

## 12. Spring Boot and Containerized Applications

In Spring Boot, properties like logging.level.root=INFO only control log levels, **not** retention duration. Spring Boot may use Logback via its default starter, but actual configuration depends on the backend and files such as **logback-spring.xml**, **log4j2.xml**, environment variables, JVM system properties, or a config server.

**Stdout-only case**: the application writes no local files, while stdout/stderr are captured by the container runtime; retention is governed by the container runtime, node log rotation, collector, and centralized destination. When a pod terminates, local copies may disappear quickly, but ingested records remain in the backend until the backend's policy runs.

**File appender in a container case**: you must know whether files are written to an ephemeral filesystem or a persistent volume, who owns the volume, how the log shipper tails files, and the lifecycle when pods are renamed or restarted. Never assume pod termination deletes all logs or preserves them.

Common risks:

- The runtime keeps old container logs longer than needed because node GC does not follow the policy.
- The app writes to both stdout and a file, and the shipper collects both, causing duplicates.
- A pod restarts while files on a PVC persist, unlike a local ephemeral path.
- Disk/ephemeral storage fills up, leading to pod eviction or application crashes.
- Different replicas run different policies due to inconsistent rollouts.
- A service changes its appender path and the old cleanup policy stops managing the archives.

Operations must verify effective retention **at each hop**, not just by reading application.properties or XML in the source repository.

## 13. Centralized Logging: Elasticsearch ILM and OpenSearch ISM

Once logs enter a search cluster, **local rotation no longer manages index retention**.

### 13.1. Elasticsearch ILM (Index Lifecycle Management)

Elasticsearch ILM has **hot, warm, cold, frozen, and delete** phases depending on the policy. It can roll over indexes/data streams, transition tiers, and delete old indexes. Below is an **illustrative policy JSON**—you must verify version compatibility, index/template names, and permissions before applying:

~~~json
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "25gb"
          }
        }
      },
      "delete": {
        "min_age": "14d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
~~~

This is an **illustrative ILM policy body**; it does not include creating the policy, attaching it to an index template/data stream, or verifying execution. Delete min_age depends on index age semantics and **rollover**; do not interpret it as “each document is deleted exactly 14 days after its event timestamp.” Index age, creation/rollover date, and lifecycle state must be checked against your version's documentation.

Notes:

- **Rollover does not equal delete.** The policy must include a delete action for the lifecycle to delete indexes.
- You must attach the policy to the target template/data stream or indexes; having a JSON file on disk does not mean indexes are being managed.
- If search uses **data streams**, lifecycle behavior may differ from traditional indexes.
- **Elasticsearch Serverless** uses Data Stream Lifecycle instead of ILM in environments where ILM is not available.
- ILM deleting an index **does not delete snapshots/backups/exports** stored outside that index.
- A delete action can delete an entire index, so do not mix data with different protection durations into the same index without a clear strategy.

### 13.2. OpenSearch ISM (Index State Management)

OpenSearch **ISM** supports policies based on states/actions/transitions—for example rollover, read-only, snapshot, and delete when conditions are met. You need the corresponding policy, template or attachment, and monitoring of managed index status.

Do not assume **Elasticsearch ILM** and **OpenSearch ISM** share the same syntax or semantics. When switching backends, read the documentation and test every action. With ISM, policy updates may take until the next evaluation cycle to run, and managed indexes may still be using a cached policy version; check actual runtime state rather than just the newly saved configuration.

**Neither system automatically manages snapshots in object storage or logs exported outside the system.**

## 14. Object Storage, Archives, Snapshots, and Backups

In object storage, retention can rely on **lifecycle rules**, prefixes/tags, object versioning, and immutability mechanisms. An archive can have multiple versions if versioning is enabled. Deleting the “current version” with a delete marker **does not necessarily delete older versions**.

Distinguish between:

- **Standard archive:** can expire via lifecycle rules based on creation/last-modified date depending on the backend.
- **Versioned object:** can have a current version and noncurrent versions that require separate policy handling.
- **Object Lock/WORM:** some objects are restricted from early deletion; do not bypass immutability controls to free disk space.
- **Snapshot/backup:** has its own protection and old-copy deletion policy. Backups can contain multiple log types and data from many subjects.
- **Exported files:** logs downloaded by staff for support/debugging can sit outside automated lifecycle paths.

**Retention across different stores does not align automatically.** For example, 14 days in a search index, 90 days in object archive, and 180 days in backups are only valid if backed by corresponding purposes, grounds, and permissions. Otherwise, it indicates a missing end-to-end policy.

When a personal data erasure request arrives, you must check deletion capabilities across indexes, archives, versions, and restore procedures; never mark “deleted everywhere” without evidence. If backups cannot be edited per event, you need a **restore gate** and a mechanism to replay a deletion ledger/tombstone before restored data is served under policy.

## 15. Legal Hold and Audit Data: Two Cases Requiring Special Consideration

A **legal hold** is a decision to preserve a dataset based on valid legal or investigative grounds, with a defined scope, approver, and review date. It is **not a boolean flag for end users to set themselves** to prevent data deletion.

For mandatory audit/security data:

- Define **which fields truly need to be kept**—do not treat every DEBUG log as “audit.”
- Protected append-only/WORM storage, integrity checks, and strict access controls may be required.
- Local archive cleanup policies must never arbitrarily delete evidence before its retention expires.
- A hold review process is required so data is not kept indefinitely just because nobody turned off a flag.
- Consider using **a dedicated audit channel** with a protection lifecycle separate from application logging.

Conversely, an audit purpose does not mean **all PII in audit logs is allowed to be kept forever**. Unnecessary fields should be excluded at the source, with de-identification/deletion policies applied where appropriate.

A key anti-pattern lesson: **mixing DEBUG, INFO, and security audit logs into the same file/index simply for configuration convenience**. Afterward, the team cannot set a short retention for DEBUG without impacting audit data. Separate channels by purpose from the design stage.

## 16. Data Minimization Makes Retention Easier to Enforce

Retention cannot fix every risk from improperly logged data. If logs contain passwords, bearer tokens, session cookies, full emails, or unnecessary request bodies, even 2-day retention leaves exposure for 2 days and in any exported copies.

Essential practices:

1. **Never log secrets/credentials in the first place.** Do not log raw Authorization/Cookie headers.
2. Avoid logging full URL query strings or payloads containing PII when unnecessary.
3. Use structured logging with eventCode, status, route template, duration, and appropriate technical IDs.
4. Distinguish **pseudonymization** from true anonymization; hashing a userId does not automatically make it anonymous.
5. Restrict DEBUG/TRACE in production using approved feature toggles that auto-expire when needed.
6. Apply masking/redaction at the source and collector; test exception messages from third-party libraries as well.
7. Maintain a data inventory to know where data has traveled.
8. Retention for logs, snapshots, exports, deletion ledgers, and supporting data must be managed accordingly.

The OWASP Logging Cheat Sheet emphasizes that temporary logs, copies, backups, and extractions should not be destroyed **before the required retention period**, nor kept **beyond the defined retention period**. That is why retention must balance availability with data storage limits.

## 17. Age-Based Retention Policies Are Not Size Caps

A common mistake is treating a **size cap** as a complete retention solution.

For example, setting maxHistory 30 and totalSizeCap 1GB for an archive generating 10GB/week can cause the cap to delete files after only a short time. If data is required to be available for 30 days, this policy cannot be considered compliant. Separate these concerns:

| Objective | How to Manage |
| --- | --- |
| Meet minimum retention period | Protected storage with sufficient capacity, legal/compliance retention |
| Do not exceed maximum retention | Lifecycle delete/expiry and verification |
| Prevent local disk full | Size/time rotation, quotas, log volume alerts, tiering |
| Reduce index cost | Hot/warm/cold tiers, data stream/index lifecycle |
| Reduce PII risk | Minimize, redact, access controls, purge all copies |
| Recover from ingest failures | Buffered/durable shipping, controlled replay |

There is no “any order works” rule. Retention obligations and data rights must come first, balanced with capacity and technical design that can satisfy both; when they cannot be met, escalate the risk and investment plan.

## 18. Process for Implementing a Retention Strategy

### Phase A — Inventory and Classification

1. List services, log sources, appenders, stdout/files, and ingest paths.
2. Identify each destination: container runtime, shipper queue, search index, archive, backup, support export.
3. Classify events: DEBUG, application, security, audit, infrastructure.
4. Identify PII/secrets, access permissions, owners, and storage purposes.
5. Assess legal/contractual/investigative obligations, minimum/maximum retention periods, and exceptions.

### Phase B — Design

6. Choose the retention start point, timezone/offset, and target stores.
7. Write a versioned policy with owner and approval.
8. Separate channels with different retention periods, avoiding shared indexes/files where inappropriate.
9. Forecast bytes/day, peak traffic, replication, backups, and budget.
10. Select rotation, archival, and deletion mechanisms suited to each backend.
11. Design legal holds, deletion requests, restore gates, and evidence of deletion.
12. Define metrics, alerts, canary rollouts, and rollback plans.

### Phase C — Testing

13. Generate **synthetic data** in a test environment, including all event types, old/new files, holds, object versions, and snapshots.
14. Run dry-runs or calculate candidate counts/bytes; verify path/index scope.
15. Test daily/size-based rollover, low-event files, and log storm files.
16. Test age calculation by lastModified/createdAt/eventTimestamp to catch discrepancies.
17. Verify cleanup does not delete active files, other tenants' logs, or held archives.
18. Verify collector/index lifecycle, job status, versioning, and snapshots.
19. Test collector interruptions, disk full scenarios, and backup restores.
20. Reconcile the volume of logs actually cleaned up against data that must remain retained.

### Phase D — Rollout and Monitoring

21. Roll out by service/tier with change records and gradually expanding scope.
22. Verify the effective configuration on each replica and index/data stream.
23. Monitor age of oldest log, bytes retained, bytes/day, cleanup errors, and disk free.
24. Verify deleted logs do not reappear through unauthorized replay/restore.
25. Store deletion evidence, the exception/hold registry, and policy review dates.
26. Test periodically; re-evaluate whenever traffic, laws, platforms, or backends change.

Never run a bulk delete command in production to “test if the policy works” without verified scope, backups, authorization, and a recovery plan.

## 19. Monitoring Retention: What to Measure?

Some viable metrics:

~~~text
log_archive_bytes{service,storage_tier}
log_retained_bytes{service,storage_tier}
log_oldest_record_age_seconds{service,storage_tier}
log_ingested_bytes_total{service}
log_rotation_events_total{service,appender}
log_retention_runs_total{service,result}
log_retention_candidates_total{service,category}
log_retention_deleted_total{service,category}
log_retention_failures_total{service,reason}
log_legal_hold_segments{service,category}
log_index_lifecycle_errors{cluster}
node_filesystem_avail_bytes{mountpoint}
~~~

These metric names are **suggestions**, not necessarily built into Logback/Log4j 2 or backend exporters. Build them from your monitoring system, storage/lifecycle APIs, or appropriate operational tooling.

Important alerts:

- Free disk space below safe threshold or sudden spike in disk fill rate.
- Oldest archive/index exceeds maximum policy without a valid hold.
- Cleanup/ILM/ISM repeatedly failing or having no successful runs.
- Active file/log volume surging due to a DEBUG/stack trace loop.
- Collector/backlog growing when downstream storage stops accepting writes.
- Protected audit data at risk of early deletion due to a cap or misconfiguration.
- Object versions/backups violating retention or restores causing data reappearance.

**Do not measure only file count.** An index can be huge; a directory can hold small logs for years with low volume; what you need to track are **age, size, data classification, accessibility, and policy enforcement status**.

Avoid high-cardinality metric labels: do not put requestId, userId, email, random raw filenames, or eventId into standard labels.

## 20. Testing Against Data Loss and Accidental Deletion

| Test Case | Expected Outcome |
| --- | --- |
| Application archive older than policy | Selected accurately within approved scope and policy |
| New file not yet expired | Retained |
| Active file currently being written | Not deleted by archive cleanup operations |
| Segment with valid legal hold | Not cleaned up until the hold is lifted through process |
| Security/audit with different retention than DEBUG | Not subjected to the wrong policy |
| Sudden log traffic spike | Capacity alert triggered; mandatory evidence not silently deleted |
| Low-traffic Logback not triggering rollover | Scheduled/startup cleanup tested; alert if not cleaned up |
| Log4j 2 Delete with wrong glob | Test catches failure to delete target files and no deletion outside basePath |
| Symlink pointing outside directory | Not followed or deleted outside scope |
| Central index with ILM/ISM | Verify managed status, delete phase, and actual errors |
| Archive with versioning | Delete marker not mistaken for deleting all versions |
| Backup holding old copies | Has separate retention and restore gate |
| Subject with erasure request | Validly deleted data is not re-ingested |
| Low-traffic or stopped service | Do not assume absence of events means lifecycle ran |
| Timezone/clock mismatch | No premature deletion due to ambiguous timestamps |
| Two tenants in one file/index | Other tenant's data is not accidentally deleted |
| Policy update/rollback | Affects only intended scope, with audit trail |
| Disk full/permission denied | Cleanup reports monitored error; does not claim success |

A test suite must verify **before/after copies**, retained records, other archive versions, snapshots, and job status. Never mark PASS based only on XML configuration “looking right.”

## 21. Common Misconceptions and Related Anti-patterns

**“Enabling rolling logs means we have retention.”** Rolling only organizes files; cleanup requires separate rules and testing.

**“Logback maxHistory=14 guarantees keeping a full 14×24 hours.”** With a daily pattern, maxHistory manages archive periods; rollover and cleanup depend on appender activity. It is not a per-record deletion timer.

**“Smaller totalSizeCap is always safer.”** A cap that is too small can delete logs before the minimum required retention period. It is a capacity control, not a retention obligation.

**“Log4j 2 max=14 means 14 days.”** In strategies using %i, max can limit the number of archives/indexes. Do not infer days unless proven for the specific policy.

**“At 14 days, IfLastModified automatically deletes on time.”** Delete actions in rolling strategies usually run on rollover; file mtime differs from individual event timestamps. Verify in practice.

**“Deleting files on the server deletes logs everywhere.”** Collectors, indexes, archives, object versions, and backups have independent lifecycles.

**“Only keep ERROR because INFO is unimportant.”** Certain INFO/audit events are needed for investigations; classify by purpose, not just severity.

**“Audit means keep forever.”** Retention obligations have specific durations and grounds; do not use the word audit to justify keeping unnecessary PII indefinitely.

**“Backups are not logs, so they are outside retention.”** Backups can contain logs and resurrect deleted data; they need their own policy.

**“Setting root level=ERROR reduces retention risk.”** Reducing volume does not determine retention duration, copy locations, or audit/security retention.

**“Deleting by filename timestamp is always accurate.”** Filenames can change, metadata timestamps can shift after copy or restore, and events inside may have different timestamps.

**“A cron job running rm -rf on old files in /var/log is good enough.”** It breaks permissions, path safety, symlinks, legal holds, backups, and auditing. Use dedicated lifecycle tooling with dry-run/allowlists and verification.

**“Storage is cheap, so keep everything forever.”** Search costs, privacy, data breach exposure, and deletion obligations still apply even when disk is cheap.

**“Configuring 30-day retention means backups also only keep 30 days.”** You must verify every storage location.

## 22. Implementation Checklist

- [ ] Define retention policies by log type and purpose, rather than picking one day count for everything.
- [ ] Assign approvers, owners, and policy versions; involve legal/compliance where appropriate.
- [ ] Know where data lives across local files, stdout, containers, shippers, indexes, archives, snapshots, backups, and exports.
- [ ] Distinguish rotation from expiry, archival, and deletion.
- [ ] Test Logback maxHistory/totalSizeCap/cleanHistoryOnStart against your actual version.
- [ ] Restrict Log4j 2 rollover strategy and Delete conditions to accurate basePath, file patterns, and age.
- [ ] Give application/debug and security/audit appropriate channels and policies; do not mix them arbitrarily.
- [ ] Verify ILM/ISM/data stream lifecycle is actually applied to the target indexes/clusters.
- [ ] Plan storage capacity for normal traffic, bursts, retries, replays, and backups.
- [ ] Implement a valid legal hold mechanism so evidence is not deleted early.
- [ ] Enforce data minimization, PII redaction, and appropriate access controls.
- [ ] Control backups/versioning/restores so deleted data is not resurrected.
- [ ] Test with dry-runs, candidate classification, active files, symlinks, multi-tenancy, and permission errors.
- [ ] Monitor cleanup failures, oldest age, disk free, retained bytes, index lifecycle, and ingestion health.
- [ ] Maintain recovery runbooks, operation audits, deletion verification, and a periodic review process.

**Conclusion:** Missing a retention strategy is a **serious logging anti-pattern** because it not only wastes storage but can also cause **premature loss of evidence** or **retaining sensitive data too long**. Define policies by purpose, separate log types with different obligations, apply appropriate mechanisms at each storage tier, and **verify with real data**. Rotation, XML configs, policy JSON, or day counts written in docs are not enough without operations, monitoring, and exception handling.

## 23. References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): logging management, protection, retention, and disposal, including backups/copies/extractions.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): TimeBasedRollingPolicy, maxHistory, totalSizeCap, cleanHistoryOnStart, and rollover behavior.
- [Log4j 2 — Rolling File Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): rollover policies, Default/DirectWriteRolloverStrategy, Delete, IfFileName, and IfLastModified.
- [Elasticsearch — Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management): ILM, rollover, and index/data stream retention.
- [Elasticsearch — Index lifecycle phases/actions](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management/index-lifecycle): phase conditions and the delete action.
- [OpenSearch — Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/index/): policies, states, transitions, rollover, and delete.
- [OpenSearch — ISM Policies](https://docs.opensearch.org/latest/im-plugin/ism/policies/): policy management, index templates, and applying to managed indexes.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, resource, and attributes.
- [Oracle Java SE 17 — java.time.Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): duration representation and expiry evaluation methods.
- [Oracle Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): comparing instants and adding Duration.
