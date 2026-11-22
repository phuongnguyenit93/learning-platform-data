# Choosing Retention for Java Logging: How Long to Keep, Where to Store, and How to Delete?

## 1. Retention Is a Design Decision, Not Just a Number of Days

**Log retention** is the policy that defines **how long a log record is kept, in which system, with what access permissions, when it moves between storage tiers, and when it is deleted or hidden from the system**. In a Java architecture, this decision can apply independently to JVM log files, container logs, shippers, Collectors, search databases, object storage, snapshots, archives, and exports.

When designing a logging strategy, the right question is not just "should we keep logs for 30 days or 90 days?". You need to answer:

1. **Why keep them?** Incident diagnostics, security, transaction tracing, auditing, operational investigation, trend analysis?
2. **What types of data are kept?** DEBUG, INFO, ERROR, access logs, security events, audit trails, exceptions, trace-correlated logs?
3. **Who can view and retrieve them?** Developers, SREs, the security team, auditors, tenants, or third parties?
4. **When does the record's age start counting?** Time of event occurrence, ingest time, index close time, or archive creation time?
5. **Which tiers are used for storage?** Local rolling files, Kubernetes nodes, hot indices, warm/cold archives, object storage, snapshots, backups?
6. **What does deletion actually mean?** Disappearing from search results, index deletion, object deletion, snapshot/backup expiration, or data destruction using an appropriate method?
7. **What legal/business exceptions apply?** Legal hold, incident investigation, evidence preservation requirements, data protection regulations?
8. **How is it verified?** Measuring volume, checking rollover and policies, executing dry-runs, confirming deletion, observing cleanup errors?

**Principle:** Retention periods must be based on **processing purpose, risk level, investigation needs, applicable obligations, and operational capacity**. There is no single number of days that is right for every company, every log type, or every country.

## 2. Concepts That Should Not Be Confused

| Term | Meaning | Not Synonymous With |
| --- | --- | --- |
| **Retention period** | Duration a record is allowed/required to be kept per policy | Size of a single file or number of archive files |
| **Rollover/rotation** | Closing an old file/index and starting a new one due to time/size | Wiping out all copies of the log |
| **Local buffer** | Buffer area in the JVM, process, or agent | Durable storage |
| **Hot storage** | Fast-query data, usually higher cost | Total retention time of the entire pipeline |
| **Warm/cold tier** | Infrequently accessed data, may have slower queries/require restore | Deleting data |
| **Archive** | Stored copy for longer-term retrieval per policy | Inherently immutable or allowed to be kept indefinitely |
| **Index deletion** | Deleting an index/partition or search object | All backups/exports having been deleted |
| **Legal hold** | Suspending deletion of data within the scope that must be preserved | Permission to store/read all data forever |
| **Data minimization** | Collecting only necessary fields from the start | Being allowed to keep raw secrets for a short time |
| **Data lifecycle** | Collection → querying → tier transition → deletion → reconciliation | A standalone file-deletion cron job |

A file can be **rotated because it reached 100 MB** while archives are still kept for months; conversely, a backend with a 14-day policy can still lose logs early due to quota or disk full. Rotation controls the **storage unit**, while retention controls the **data lifecycle**.

## 3. Why Should You Not Use the Same Retention Period for All Logs?

Different log types have different purposes and risks:

- **DEBUG/TRACE:** rich in internal details, high volume; usually useful within a short investigation window. Leaving verbose logging on long-term can expose information and drive up costs.
- **Operational INFO:** reflects request/job lifecycles and system events; may need to be kept longer than DEBUG to compare against releases or recurring incidents.
- **WARN/ERROR:** supports incident response and error analysis; retention depends on incident detection, resolution, and post-mortem cycles.
- **Access logs:** help analyze HTTP traffic, security, and performance; may contain IPs, user-agents, URLs, query parameters, and personal data.
- **Security logs:** logins, permission denials, security configuration changes; require evaluating the risk of slow-to-detect attacks and evidence protection requirements.
- **Audit trail:** records who did what, on which object, and with what outcome; may have specific retention and integrity obligations.
- **Job/message logs:** needed for tracing retries and workflows; should not replace a business event store if durable business history must be retained.
- **Platform/Collector logs:** diagnose the transport pipeline itself; may need an independent policy to detect dropped logs.

**Do not assume INFO is audit** or that ERROR must be kept indefinitely. Retention meaning comes from the **event class and purpose**, not just the level.

## 4. Illustrative Retention Table by Purpose

This is a **simulated scenario for learning design**, and is definitely **not** a legal recommendation or mandatory numbers:

| Group | Example Retention | Simulated Rationale | Considerations Before Applying |
| --- | --- | --- | --- |
| DEBUG/TRACE | 3 days | Immediate investigation after errors/deploys | Sampling, sensitive data, high log volume |
| INFO app | 14 days | Short-term operational post-mortem | Incident cycle, detection and query latency |
| WARN/ERROR | 30 days | Error investigation and release comparison | Error codes, stack traces, restricted access |
| Access log | 14–30 days | HTTP/API inspection and system security | IP/query/headers, privacy policy |
| Security event | 90 days or per dedicated policy | Detecting slow-moving anomalies | Threat model, incidents, permissions, and applicable obligations |
| Audit log | Per approved retention schedule | Tracing meaningful actions | Legal/industry requirements, legal hold, integrity, read access |
| Agent/Collector diagnostic | 7 days | Investigating pipeline malfunctions | Need evidence when logs are dropped or exporters fail |
| Archive store | Until the end of total allowed duration | Rare retrieval, controlled recovery | Backups, legal hold, deletion, and cost |

**Do not copy these numbers directly into a production policy.** For example, 90 days does not automatically satisfy a specific regulation; nor is there any basis for assuming keeping audit logs the longest is always legal or necessary. Data owners, security, legal, and operations must approve a **retention schedule** tailored to the actual system, data type, and jurisdiction.

An event type may need to be split into a **less sensitive event summary** for long-term retention, while raw diagnostics are kept only briefly. If an event must be kept for auditing, you do not necessarily have to retain every accompanying request body and stack trace.

## 5. Step-by-Step Process for Choosing Retention

### Step 1 — Inventory Log Sources

Document: Java service, framework, env/region, event class, log level, volume, potential data contents, sink, owner, and authorized viewers. Do not overlook logs generated by third-party frameworks, reverse proxies, JDBC drivers, message brokers, and agents.

### Step 2 — Define the Purpose and Questions to Answer

For example: "SREs need to compare errors between two deployed versions within a release cycle" or "Security needs to trace failed login attempts within an approved investigation window." The purpose must be specific enough to verify whether retention is sufficient.

### Step 3 — Determine When Logs Have Value

Incidents are often detected some time after the event occurs. Gather data from operations: **time to detect**, **time to investigate**, release cycles, risk analysis cycles, SLA deadlines, and preservation obligation windows.

### Step 4 — Classify Sensitivity and Protection Boundaries

A log containing tokens or card numbers does not become safe just because it is kept for only three days. **Remove or mask at the source** before calculating retention. Access control, encryption, exports, and geographic region are also part of the policy.

### Step 5 — Check Obligations and Exceptions

Consult those responsible for compliance/legal regarding laws, contracts, customer terms, incident holds, or evidence preservation duties. When requirements conflict, you need a resolution process and approval record—do not simply pick the longest number of days to keep all data.

### Step 6 — Estimate Volume/Cost and Decide on Tiers

Measure **actual** log volume by type and env, compression ratios, index overhead, replicas, data transfer, and query costs. Design hot/warm/cold tiers and local buffers.

### Step 7 — Design Deletion Points for Every Copy

List everywhere logs exist: JVM/files, runtime nodes, agent queues, Collectors, hot indices, cold objects, snapshots, backups, exports. Identify which system is responsible for deletion and what signals confirm it.

### Step 8 — Test, Monitor, and Adjust

Test dry-runs, deletion policies, legal holds, restarts/rotations, and queries; monitor data age, oldest searchable event, deletion lag, storage usage, and failed deletes. Review retention whenever architecture, threats, or obligations change.

## 6. When Does Retention Start Counting?

A log event can have multiple timestamps:

~~~text
event occurredAt:   2026-11-01T10:00:00Z
agent observedAt:  2026-11-01T10:00:05Z
backend ingestedAt:2026-11-01T10:00:09Z
archive createdAt: 2026-11-02T00:00:00Z
~~~

These milestones are **not equivalent**. If a policy specifies "14 days from when the event occurred," using the archive creation date or the `lastModifiedTime` of a copied file may cause data to be kept longer or shorter than intended.

**Rules that need to be defined:**

- **Event time:** logical time of occurrence, preferring UTC and synchronized clocks.
- **Ingest time:** time the backend accepts the event; usable for ingestion-based lifecycles, though not guaranteed to match data obligations.
- **Index creation/rollover time:** index lifecycle may be based on rollover/creation time, which is not the same as the age of each individual document.
- **Archive object created time:** a recently copied/migrated object may carry a newer modification time even though the original logs are old.
- **Date-granularity:** "keep the last day" may be interpreted as keeping the full UTC day, which differs from exactly 14×24 hours calculated per event.

Explicitly choose **inclusive/exclusive boundaries**. For example, the 14-day policy in the Java demo in Section 11 deletes files with a date *before* `today.minusDays(14)`; a file on the exact cutoff date is kept. That is a decision to give tests deterministic output, **not a universal definition for all retention policies**.

For sensitive data with strict time-based deletion requirements, storing multiple days in a shared file may prevent easy per-record deletion. You can choose appropriate partitions/indices/time buckets or a controlled document-level deletion workflow.

## 7. Distinguishing Local Retention from Backend Retention

~~~text
Java Logger
   │
   ▼
[Local rolling file]   ←  limits file count/size/days on the host
   │
   ▼
[Agent / Collector]    ←  queue/buffer/checkpoint, may store copies
   │
   ▼
[Hot index]            ←  kept for fast queries
   │
   ▼
[Warm/Cold/Object]     ←  kept for less frequent access
   │
   ▼
[Delete/purge]         ←  per overall schedule, exceptions, and processing evidence
   │
   └── [Snapshot / backup / export] has its own lifecycle
~~~

A policy of "14 days in Elasticsearch/OpenSearch/Loki" does **not** automatically delete Logback files on the server or snapshots in object storage. Conversely, configuring Logback `maxHistory=7` does not control copies already sent to the backend.

You should have an **ownership matrix**: the Java team is responsible for emitting data safely, the platform team for local shipping and cluster lifecycle, the observability team for index/tier policies, and security/legal for preservation schedules when needed. Paths may differ across companies, but responsibilities must be clear.

Especially with async pipelines, an agent may **not have finished shipping** when a local log is rotated/deleted. If local TTL is too short compared to outage duration and the queue is not durable, there is a risk of losing logs before downstream receives them.

## 8. A Good Retention Policy Can Vary by Environment

| Environment | Practical Need | Precautions |
| --- | --- | --- |
| Local development | Fast debugging, no long-term central store needed | Do not copy production data into local logs |
| CI/Test | Keep logs to diagnose job failures | Artifacts and CI logs also need TTL and access control |
| Staging | Test integration, load, and rollouts | Test data may still contain sensitive information |
| Production | Observability, incidents, security, audit | Scope permissions, retention by event class, cost |
| Disaster recovery | Data recovery aligned with policy | Backups must not turn into indefinite retention |

**Do not assume staging has "no real data."** Copied data or vendor integration data may carry the same protection obligations as production.

If you enable DEBUG temporarily for diagnostics, set a deadline to turn it off and a shorter retention for that stream. Do not let a temporary debug toggle become an unintended long-term collection policy.

## 9. Size-Based and Time-Based Rotation: Different from Retention

An appender can roll over:

- **By size:** creates a new file when reaching an MB threshold.
- **By time:** creates an archive at a new day/hour/week/month.
- **Combined:** multiple files in a single day if log volume is high.

Even so:

- Rollover is **not** a guarantee of deletion across all storage.
- If multiple files contain the same date, deletion by filename/date must process all archives within that period.
- Cleanup tasks may run **only when rollover occurs**, not on a wall-clock cron schedule.
- For low-traffic applications, crossing a time boundary without a new event may not trigger rollover yet.
- Active files are usually distinct from archives; do not delete active files with a generic cron while the app is writing.
- A total size cap can **delete earlier** than time-based retention. Decide whether that is permissible for mandatory events.

Therefore, configure both the **local tier** and the **central tier**. If retention is an audit requirement, a standard rolling appender is not a standalone preservation system.

## 10. Java JUL: `FileHandler` Has File Rotation, Not a Day-Based Retention Schedule

`java.util.logging.FileHandler` in JDK 17 supports `pattern`, `limit` (approximate bytes per file), `count` (number of rotating files), and `append`. For example:

~~~java
// Fragment; requires import java.util.logging.FileHandler;
// may throw IOException/SecurityException.
var handler = new java.util.logging.FileHandler(
        "%t/app-%u.%g.log", 10_000_000, 4, true);
~~~

Meaning: writes files matching the pattern, with an approximate limit of **10 MB per file** and rotating across **4 files**—not keeping 4 days. How long each file survives **depends on the log emission rate**: under high traffic it can be overwritten quickly; under low traffic it may stay around for a long time.

Key assumptions:

- `%t` is the temp directory, `%u` helps avoid conflicts between processes, and `%g` is the generation number.
- There is no built-in day-based policy or legal hold equivalent to a centralized retention management system from `limit`/`count` alone.
- Choose charset/formatter per policy; do not log credentials to local files.
- Ensure file permissions and handle disk full; `FileHandler` can report I/O errors via `ErrorManager`.
- Do not use a rotating `FileHandler` to retain mandatory audit logs if it can overwrite them before the required retention period expires.

If the requirement is "keep 14 days based on event time," choose an appropriate time-based archive/cleanup mechanism or let the backend manage retention; do not infer `limit×count` into a number of days without knowing the log rate.

## 11. Standalone Java 17 Example: Checking File-Based Retention and Legal Hold

To understand **making deletion decisions** without touching real files, the following program:

1. Creates an isolated temporary directory owned by the program itself.
2. Creates 7 fake fixture files: `app`, `debug`, `audit`, and an unrecognized file.
3. Defines **demo-only** retention: `app=14 days`, `debug=3 days`, `audit=90 days`.
4. Uses a fixed `LocalDate` so test results do not depend on the actual run date.
5. Runs a **dry-run** to count files eligible for deletion without deleting them.
6. Runs **apply** and verifies the exact remaining files.
7. Skips files not matching the naming convention and symlinks, and keeps audit files flagged with a **hold**.
8. Deletes all temporary fixtures in `finally`.

**Important:** Do not copy this program verbatim as a production log deletion job. A production implementation requires approved permissions, concurrency handling with appenders/shippers, storage semantics, transactions/auditing for cleanup, distributed holds, timezones, backups, deletion acknowledgments, and protection against TOCTOU/symlink races. The demo intentionally uses date-stamped filenames and a hardcoded legal-hold set, which is not robust enough for real enforcement.

### 11.1. Create RetentionPolicyDemo.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class RetentionPolicyDemo {
    private static final Pattern FILE_NAME = Pattern.compile(
            "^(app|debug|audit)-(\\d{4}-\\d{2}-\\d{2})\\.log$");
    private static final Map<String, Long> DAYS =
            Map.of("app", 14L, "debug", 3L, "audit", 90L);
    private static final Set<String> HOLDS =
            Set.of("audit-2026-01-01.log");

    record Stats(int eligible, int kept, int held, int unrecognized) {}

    static Stats sweep(Path directory, LocalDate today, boolean dryRun)
            throws IOException {
        List<Path> candidates;
        try (Stream<Path> stream = Files.list(directory)) {
            candidates = stream.sorted(Comparator.comparing(
                    path -> path.getFileName().toString())).toList();
        }
        int eligible = 0, kept = 0, held = 0, unrecognized = 0;

        for (Path path : candidates) {
            String name = path.getFileName().toString();
            Matcher matcher = FILE_NAME.matcher(name);
            if (Files.isSymbolicLink(path)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || !matcher.matches()) {
                unrecognized++;
                continue;
            }

            LocalDate fileDate;
            try {
                fileDate = LocalDate.parse(matcher.group(2));
            } catch (DateTimeParseException invalid) {
                unrecognized++;
                continue;
            }

            if (HOLDS.contains(name)) {
                held++;
                continue;
            }

            long days = DAYS.get(matcher.group(1));
            LocalDate cutoff = today.minusDays(days);
            if (fileDate.isBefore(cutoff)) {
                eligible++;
                if (!dryRun) Files.delete(path);
            } else {
                kept++;
            }
        }
        return new Stats(eligible, kept, held, unrecognized);
    }

    public static void main(String[] args) throws Exception {
        Path demoDirectory = Files.createTempDirectory("retention-demo-");
        try {
            List<String> names = List.of(
                    "app-2026-10-20.log",
                    "app-2026-11-01.log",
                    "audit-2026-01-01.log",
                    "audit-2026-10-10.log",
                    "debug-2026-11-01.log",
                    "debug-2026-11-09.log",
                    "readme.txt");
            for (String name : names) {
                Files.writeString(demoDirectory.resolve(name),
                        "FAKE TEST LOG\n", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);
            }

            LocalDate today = LocalDate.of(2026, 11, 10);
            Stats expected = new Stats(2, 3, 1, 1);
            Stats preview = sweep(demoDirectory, today, true);
            if (!preview.equals(expected)) {
                throw new AssertionError("Unexpected dry-run: " + preview);
            }
            System.out.printf(
                    "DRY_RUN eligible=%d held=%d kept=%d unrecognized=%d%n",
                    preview.eligible(), preview.held(), preview.kept(),
                    preview.unrecognized());

            Stats applied = sweep(demoDirectory, today, false);
            if (!applied.equals(expected)) {
                throw new AssertionError("Unexpected apply: " + applied);
            }
            System.out.printf(
                    "APPLY deleted=%d held=%d kept=%d unrecognized=%d%n",
                    applied.eligible(), applied.held(), applied.kept(),
                    applied.unrecognized());

            List<String> remaining;
            try (Stream<Path> stream = Files.list(demoDirectory)) {
                remaining = stream.map(path -> path.getFileName().toString())
                        .sorted().toList();
            }
            List<String> expectedRemaining = List.of(
                    "app-2026-11-01.log",
                    "audit-2026-01-01.log",
                    "audit-2026-10-10.log",
                    "debug-2026-11-09.log",
                    "readme.txt");
            if (!remaining.equals(expectedRemaining)) {
                throw new AssertionError("Unexpected files: " + remaining);
            }
            System.out.println("REMAINING=" + remaining.size());
        } finally {
            try (Stream<Path> stream = Files.list(demoDirectory)) {
                for (Path path : stream.toList()) Files.deleteIfExists(path);
            }
            Files.deleteIfExists(demoDirectory);
        }
    }
}
~~~

### 11.2. Run Command and Exact stdout

~~~bash
javac --release 17 RetentionPolicyDemo.java
java RetentionPolicyDemo
~~~

**Standard output (stdout):**

~~~text
DRY_RUN eligible=2 held=1 kept=3 unrecognized=1
APPLY deleted=2 held=1 kept=3 unrecognized=1
REMAINING=5
~~~

**Standard error (stderr):** empty; exit code `0` when all assertions pass.

### 11.3. Explanation

- The demo date is `2026-11-10`. `app` has a cutoff of `2026-10-27`: the file dated 2026-10-20 is selected for deletion, while 2026-11-01 is kept.
- `debug` has a cutoff of `2026-11-07`: the file 2026-11-01 is selected for deletion, while 2026-11-09 is kept.
- `audit` has a cutoff roughly 90 days prior; the file 2026-01-01 is old but **is in `HOLDS`**, so it is kept; 2026-10-10 is also kept.
- `readme.txt` does not match the filename schema so it is skipped; by default, **unrecognized files are left untouched**.
- Running preview returns `eligible=2` without **deleting yet**. Running apply deletes the exact two fixture files; five files remain afterward.
- `Files.isRegularFile(..., NOFOLLOW_LINKS)` and the symlink check are simple guardrails for the demo, not a complete elimination of **race conditions** if another actor can swap files between check and deletion.
- Retention identification relies on the **date in the filename**, not on reading individual event timestamps; for files containing records spanning multiple days, the result may not align with an event-level policy.
- `HOLDS` is just a hardcoded `Set` in code to illustrate preservation precedence; a real legal hold must be managed and enforced by controlled storage/legal systems.

Try changing the cutoff date, keeping the hold intact, or adding a file with a mismatched pattern to observe test failures. Do not change the demo directory to `/var/log` or a real active folder.

## 12. Logback: Configuring Local Rolling Retention

For applications using **SLF4J + Logback Classic**, `RollingFileAppender` can use `TimeBasedRollingPolicy` to manage archive files. The following **logback.xml** example is an **illustrative local policy**, not a long-term storage contract:

~~~xml
<configuration>
    <appender name="DIAGNOSTIC"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/diagnostic.log</file>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/diagnostic.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="DIAGNOSTIC"/>
    </root>
</configuration>
~~~

**What these parameters actually do:**

- `fileNamePattern` with `%d{yyyy-MM-dd}` creates archives on a daily cycle. `maxHistory=7` keeps approximately seven archive **periods** per Logback's mechanism, not a legal policy of "168 hours from each event."
- `totalSizeCap=1GB` caps total archive size; it requires `maxHistory` to be configured. It can cause older archives to be deleted **earlier** than the day-based cycle.
- `cleanHistoryOnStart=true` triggers cleanup when the appender starts, which is important when an application logs infrequently and has not rolled over yet.
- Archive cleanup can run asynchronously; **do not** rely on second-level deletion precision.
- This configuration does not delete data already shipped to a backend, snapshots, or backups, nor does it handle legal holds.
- `logs/diagnostic.log` is the active file being written to; archive cleanup and active files are separate concerns.
- Timezone/default settings and directory permissions must be verified per deployment environment.

If an application produces high log volume in a single day and needs a **per-file** size limit, consider `SizeAndTimeBasedRollingPolicy` with `%d` and `%i`; do not confuse `maxFileSize` with total retention.

**Warning:** Do not apply a small `totalSizeCap` to an audit channel that must be retained in full; a size cap can delete data ahead of schedule. Do not share the same appender for debug and audit logs if they require different retention periods and permissions.

## 13. Log4j 2: Delete Action, IfFileName, and IfLastModified

Log4j 2 Core supports **rolling strategies** and a `Delete` action to clean up archive files conditionally. You can configure a **test mode** before performing actual deletions.

The following **log4j2.xml** example applies only to applications with a compatible Log4j 2 Core:

~~~xml
<Configuration>
    <Appenders>
        <RollingFile name="DIAGNOSTIC"
                     filePattern="logs/diagnostic.%d{yyyy-MM-dd}.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <DirectWriteRolloverStrategy>
                <Delete basePath="logs" testMode="true">
                    <IfFileName glob="diagnostic.*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DirectWriteRolloverStrategy>
            <TimeBasedTriggeringPolicy/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="DIAGNOSTIC"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**How to read this:**

- `DirectWriteRolloverStrategy` uses `filePattern` to place archives; `TimeBasedTriggeringPolicy` triggers time-based rollover.
- `Delete basePath="logs"` evaluates files only within that directory scope. By default, Log4j 2 does not follow symbolic links when traversing paths; **do not enable `followLinks=true` casually**.
- `IfFileName` narrows the scope so files from other applications/channels are not deleted.
- `IfLastModified age="P7D"` uses the **file modification time** per Log4j 2's condition, not individual log event timestamps.
- `testMode="true"` **does not delete**, but instead logs matching files to the Status Logger. Only after verifying paths/targets/holds and obtaining approval should you switch to an enforcing policy; do not disable `testMode` arbitrarily in production.
- If log objects reside in a central store or require a legal hold, local archive deletion policies **do not replace** the lifecycle in that storage.

**Practical risk:** An overly broad `IfFileName` pattern or an incorrect `basePath` can delete unintended files. Test in a temporary directory, use least privilege, keep an audit log of cleanup actions, and monitor for errors.

## 14. Local Rolling Files Do Not Determine Centralized Log Retention

Suppose Logback keeps only 7 daily archives on the host, while OpenSearch keeps INFO logs for 30 days. This is **not a contradiction** if the local file's purpose is short-term buffering and the backend is the primary lookup store.

However, you must verify:

1. Can the agent read all archives before local cleanup runs?
2. If the Collector loses connectivity for two days, do local files/queues hold enough records for replay?
3. Are files rotated via rename or copytruncate tracked properly by the agent?
4. Does an application restart delete old files before the agent reads them?
5. Has the backend actually received the shipped events, or was it just an ACK from a proxy?
6. Are there duplicate logs from shipping **both stdout and files**?
7. If an event is mandatory audit data, is there a dedicated durable recorder instead of best-effort local rotation?

**Do not mechanically set local retention = 1 day** if backend outages can last longer and the shipper lacks a durable buffer. Conversely, do not keep files indefinitely on the host "just in case the backend fails": a full disk can take down the application itself.

A good policy clearly states the **pipeline SLO**, such as maximum shipping delay, durable queue capacity, alerts before disk thresholds, and behavior when limits are exceeded.

## 15. Kubernetes: Kubelet Log Rotation Is Not a Historical Archive

When a Java container writes to stdout/stderr, the container runtime and kubelet manage log files on the node. Kubernetes provides `containerLogMaxSize` and `containerLogMaxFiles` settings to limit log files per container.

Keep in mind:

- This is **node-level local rotation and storage capping**, not a retention schedule for a centralized log backend.
- `kubectl logs` typically shows only the current log file per kubelet's architecture; previously rotated data is not automatically queryable through this API.
- Deleting/evicting a Pod or losing a node can wipe out logs that only existed on that node.
- Kubelet/container runtimes use the CRI format; agents must read, checkpoint, and handle partial records.
- A DaemonSet shipper can collect stdout/stderr and forward them to a Collector or backend, but retention at the destination must be designed separately.
- A sidecar writing the same data to both a file and stdout can create duplicates or increase local storage costs.

When choosing retention **for cross-pod/node incident investigation**, you need a cluster-level logging backend with its own lifecycle. Do not rely on `kubectl logs --previous` as a long-term storage strategy.

## 16. Retention of Collectors, Shippers, and Exporter Queues

**OpenTelemetry Collector** is a log collection/processing/forwarding component, **not a default index/search retention system**. The Collector can use batching, memory limiters, queues/retries, or persistent queues depending on components and configuration; queue retention is strictly a **buffer lifecycle**.

A typical pipeline:

~~~text
Java stdout / OTLP
    → agent/receiver
    → memory limiter + batch/transform
    → queued exporter/retry
    → log backend with storage policy
~~~

If an exporter uses an in-memory queue, a process crash can lose pending records. If the queue uses persistent storage, you must define capacity, permissions, encryption, cleanup, replay conditions, and what happens when the disk fills up.

**Do not say "the Collector keeps logs for 30 days"** just because the backend keeps 30 days or the queue file holds a lot of data. Transport channels and log stores have different contracts. During an outage, queued data can become older than when it started; you need retry expiration/quarantine rules to avoid pushing expired logs into the store.

Telemetry to monitor: accepted/refused records, exporter sent/failed, queue depth, retry failures, dropped logs, and age of the oldest waiting record. Exact metric names depend on the Collector version/distribution.

## 17. Hot, Warm, Cold, and Archive: How to Calculate Total Duration

A multi-tier strategy might look like this (**illustrative**, not mandatory numbers):

~~~text
Day 0            Day 7            Day 30           Day 90
  │                │                │                │
  ├── HOT ─────────┤                │                │
  │                └── WARM ────────┤                │
  │                                 └── COLD ────────┤
  │                                                  └── DELETE
~~~

**Total retention = 90 days**, not `7 + 30 + 90 = 127`, because the milestones represent **"until day X."** If a policy instead states "hot for 7 days, warm for an additional 23 days, cold for an additional 60 days," the result is also 90 days, though phrased differently; you must distinguish milestones from per-stage durations.

**Trade-offs:**

| Tier | Benefits | Costs/Limitations |
| --- | --- | --- |
| Hot | Fast queries, supports ongoing incidents | Storage/indexing is usually more expensive |
| Warm | Balances cost and post-mortem querying | Slower queries, limited resources |
| Cold | Keeps infrequently accessed data at lower cost in some systems | May require restore/slow queries |
| Archive/object | Policy-compliant storage and controlled retrieval | Not directly searchable or requires data restoration |
| Delete | Reduces risk and cost once purpose is fulfilled | Requires confirming multiple copies and handling holds |

**Do not treat WARM/COLD as permission to store longer.** Data must be deleted once the total allowed duration expires, barring valid, properly governed exceptions.

## 18. Backend: Retention of Indices, Streams, Partitions, and Objects

In a centralized log store, retention can use lifecycle policies by index, data stream, partition, or object.

Common mechanisms include:

- **Elasticsearch Index Lifecycle Management (ILM):** transitions lifecycle phases and deletes indices/data stream backing indices per policy; age/rollover milestones must be verified against the actual index configuration.
- **OpenSearch Index State Management (ISM):** states/transitions/actions can manage rollover/deletion conditionally; verify the policy is attached to the right indices.
- **Grafana Loki:** provides retention and compactor mechanisms depending on storage/index schema; merely configuring application labels or query windows **does not automatically** create backend retention.
- **Object storage:** typically offers lifecycle rules to delete objects/versions or transition storage classes; versioning, replication, object locks, and legal holds can prevent immediate deletion.
- **Database partitions:** dropping daily partitions can be faster than deleting millions of rows, but is only accurate if partition boundaries align with the retention contract.

**Warning:** Deleting an index for a single day can delete events still within retention if that same index contains mixed timestamps or if the lifecycle is based on rollover time. Do not use `index age` as a substitute for `event age` without verification.

A backend may "no longer return results in queries" due to closed indices, tier changes, permissions, or query errors; that is not equivalent to the data having been deleted.

## 19. Estimating Retention Capacity and Cost

Estimate from measured data:

~~~text
rawBytesPerDay = eventsPerSecond × averageRawBytesPerEvent × 86400
storedBytesPerDay ≈ rawBytesPerDay × storageMultiplier
hotBytes ≈ storedBytesPerDay × hotDays
totalBytes ≈ sum(bytes in all active tiers + copies/backups as applicable)
~~~

Here `storageMultiplier` is an **empirical factor** encompassing compression, indexing, metadata, replicas, and backend-specific overhead; it can be greater or less than 1, and is **not a universal constant**.

Simulated example:

- 100 events/sec × 600 bytes/event ≈ **5.18 GB raw/day** (decimal).
- If after compression/indexing/replicas you measure 4 GB/day in the hot tier, keeping 7 days requires roughly 28 GB of **average hot data**, excluding peak traffic, watermarks, shard/headroom, snapshots, and buffers.
- Keeping warm/cold tiers requires adding capacity separately based on measured volume in those tiers—do not multiply the full hot size across the entire duration.
- If traffic spikes threefold seasonally, size caps must account for peaks rather than relying on long-term averages as a guarantee.

Cost formulas also need query load, ingest fees, network egress, cross-region replication, and storage class pricing. **Do not cut mandatory audit retention solely due to unexpected costs**; first reduce raw payloads, sample diagnostics, consider tiering, or adjust log emission practices under an approved policy.

## 20. Legal Hold: Preservation Exceptions and Privacy

A **legal hold/incident hold** requires suspending deletion of a specific dataset due to investigation, litigation, preservation orders, or applicable procedures. Not all logs are automatically kept indefinitely.

The design needs:

1. Clear scope: event IDs, permitted actor/resource refs, tenant, time range, index/object, log type.
2. Approver and business/legal basis; audit trail of hold placement and release.
3. Enforcement mechanisms at the **log store and relevant copies**, not just a filename list in an app.
4. Separation of duties: application admins should generally not be able to delete held evidence on their own.
5. Review dates and release conditions.
6. Once a hold is released, recalculate/process retention per policy to avoid defaulting to indefinite storage.
7. Adherence to data minimization and purpose limitation principles; retaining unnecessary information can increase risk.

**WORM/object lock/immutable storage** can support preservation but may conflict with data deletion requirements. Choose policies based on actual obligations and storage capabilities, with proper controls and legal/compliance consultation.

The Java example in Section 11 only uses `Set<String> HOLDS` to illustrate hold precedence before deletion. **That is not** a compliant organizational legal hold workflow.

## 21. Data Deletion: "Not Found" Differs from "Completely Deleted"

When the deletion date arrives:

- A deleted index may no longer be queryable, yet snapshots/backups of that index still exist.
- An unlinked file may still have data on storage media/snapshots or in backups; physical byte erasure depends on the filesystem/hardware.
- Object storage has versioning, replicas, and lifecycles; deleting the current version does not necessarily delete all versions.
- Collector queues, dead-letter/quarantine stores, SIEM exports, and downloaded CSVs can be additional copies.
- Cached/saved queries or in-memory data have different lifecycles.
- Legal holds can prevent timely deletion; the system must record the reason and review status.

**Do not certify secure erasure based solely on `Files.delete(path)`.** Logical deletion, version deletion, crypto-erasure, and physical destruction are distinct mechanisms; choose according to security, compliance, and technology.

A sound deletion workflow includes these states:

~~~text
RETENTION_EXPIRED
   → HOLD_CHECKED
   → DELETE_REQUESTED
   → DELETE_ACCEPTED
   → DELETE_VERIFIED (per each storage API/contract)
   → RECONCILED / EXCEPTION_REVIEW
~~~

**Verification evidence** can include the index no longer existing, object versions deleted per contract, snapshot lifecycles expired, or over-age record counts dropping to allowed levels. It does not necessarily prove data has been physically destroyed on every device.

## 22. Layered Design for Personal Data and Security

Long retention expands the **risk surface**: more logs, more people with viewing access, and more places to protect against unauthorized access or leaks.

Do not log:

- Passwords, OTPs, bearer/refresh tokens, API keys, session cookies, private keys.
- PAN/card data or sensitive documents without a proper purpose and authorization.
- Full HTTP request/response bodies, query strings containing PII, raw DB bind values.
- Exception messages/stack traces that might contain URLs with tokens or user info.
- MDC/ThreadContext or DTO `toString()` outputs that have not been reviewed for safety.

**Choosing retention does not replace data minimization.** If a record contains a real secret, keeping it for 24 hours can still cause severe harm. The first step is always not collecting unnecessary data, allowlisting fields, safe redaction, and testing with synthetic sentinels.

For long-term statistics, consider **aggregate metrics** or non-identifying summaries instead of keeping detailed request-level logs. Pseudonymized data can still be linkable and may fall within the scope of personal data.

You need RBAC permissions, tenant isolation, TLS/mTLS, encryption at rest, log access auditing, and retention for user-generated exports.

## 23. Policy-as-Code: Writing Contracts Separate from Vendor Configuration

An **abstract** policy can be maintained as YAML for teams to review together:

~~~yaml
version: 1
purpose: "example-retention-policy"
timeBasis: "event_timestamp_utc"
classes:
  diagnostics:
    retainFor: "P3D"
    accessRoles: ["dev-oncall", "sre"]
  application:
    retainFor: "P14D"
    accessRoles: ["sre"]
  security:
    retainFor: "P90D"
    accessRoles: ["security"]
  audit:
    retainFor: "requires-approved-schedule"
    accessRoles: ["audit-reviewer"]
exceptions:
  legalHold: "approved-case-specific"
controls:
  dryRunBeforeDelete: true
  alertOnDeleteFailure: true
~~~

**This is not direct configuration YAML for Logback, Log4j 2, Kubernetes, Collector, Loki, or Elasticsearch.** It is an example of expressing organizational intent; to apply it, you must **translate it into concrete lifecycle policies**, verify each backend's capabilities, and create automated drift checks.

A review-worthy policy should include:

- Owner and approver, schema version, effective date.
- Data classes and purposes, approved retention basis.
- Time basis, tier transitions, and total retention.
- Regions/tenants, access control, and encryption.
- Hold/exception approvals, purge procedures, and verification.
- Metrics, alert thresholds, rollback, and change history.
- Mapping from source logs to index/stream/bucket policies.

Avoid letting a Logback config change silently while the backend lifecycle retains old values for months.

## 24. Testing Retention: Time Boundaries and Operational Failures

| Test Case | Data/Action | Expected Outcome |
| --- | --- | --- |
| Just past expiration | File/event before cutoff | Eligible for deletion per time basis |
| Exact cutoff date | Event on boundary | Kept/deleted per defined inclusive clause |
| Recent date | Event after cutoff | Kept |
| Invalid filename/date | File not matching schema | Not blindly deleted; metric/quarantine recorded |
| Legal hold | Expired file with active hold | Not deleted; reason/evidence recorded |
| Hold release | Hold validly lifted | Lifecycle re-evaluated per policy |
| Symlink file | Link pointing elsewhere | Cleanup does not exceed approved scope |
| Open app file | Concurrent rollover/rotation | Active file not deleted or data corrupted |
| Backend index rollover | Index spanning multiple event days | Events still within retention are not deleted |
| Clock skew | JVM/Collector date drift | Age not miscalculated by implicit clocks |
| DST/timezone | Crossing local/UTC day | Consistent boundaries per time basis |
| Disk cap | Volume exceeds threshold before TTL | Alert/buffer/size-policy works, mandatory audit not lost |
| Collector outage | Agent queue backed up for days | Local files not deleted before shipping per contract |
| Backup snapshot | Index already deleted | Snapshots also follow separate lifecycle and holds |
| Archive restore | Old records restored | Does not "restart" retention against policy |
| Delete API failure | Storage rejects cleanup | Controlled retry, alert, and audit |
| Large scale | Millions of events | Queries/lifecycle do not bottleneck the service |
| Multi-tenant | Different policies per tenant | No wrong retention or deletion across tenants |

**Negative assertion:** "Old records not found" must be paired with a **positive assertion** that queries/backends still work and a valid newer record still exists. If search returns 500 errors or an index was accidentally dropped, a test asserting only that expired records are missing can falsely PASS.

**Test production policies in staging or a sandbox**; never run destructive cleanup on real data just to test a regex or path.

## 25. Observability for the Retention Process Itself

Set up telemetry to detect when retention stops working or works incorrectly:

- **Oldest searchable event age** by class/tenant/tier.
- **Count/bytes over retention threshold** and age of the oldest overdue record.
- **Deletion candidates**, dry-run vs actual deleted count.
- **Delete failures**, retry backlog, and deletion completion time.
- **Held records** by case/expiry/review status, without logging sensitive content.
- **Index/partition count** by tier and policy owner.
- **Object versions/snapshot age** compared against policy.
- **Ingest/export backlog**, so local cleanup does not outpace the shipper.
- **Storage utilization**, disk watermark, predicted fill date.
- **Access/export activity** and queries from sensitive roles.
- **Policy drift** between desired configuration and running values.
- **Cost per class/tier**, volume by service, abnormal changes after deploy.

Measuring only "size decreased after delete" **is not enough**: an index might have been dropped by mistake or a policy might be deleting data early that is still needed. You need metrics for both **over-age** data and **prematurely deleted** data in tests/reconciliation.

Canary retention tests can generate synthetic, uniquely identified events, wait for expiration in a sandbox, and then confirm the lifecycle completes properly. Never use canaries containing real tokens or user data.

## 26. Changing Retention on a Running System

Suppose you want to reduce INFO retention from 30 down to 14 days. This can **immediately** delete many indices/files in the 15–30 day range if the policy applies retroactively.

Safe change procedure:

1. Confirm reason, owner, compliance/privacy, and scope.
2. Measure the number of records/bytes to be deleted and list affected indices/objects/versions.
3. Check active incidents, legal holds, audits, and other exceptions.
4. Run a dry-run/preview against the config and test data; review results.
5. Schedule the change with monitoring, possibly batching to avoid I/O spikes.
6. Restrict policy edit permissions and confirm approvals.
7. Apply, and monitor deletion lag, rejections, errors, and query behavior.
8. Verify no in-retention data was lost and expired data was handled.
9. Record an audit entry of the policy change **without secrets**, independent of the deleted data.
10. Assess copies in backups/exports and privacy workflows.

**Do not treat a "retention rollback" as restoring deleted data.** Once an index/object is gone without a valid copy, increasing the day count again will not resurrect the data.

When increasing retention, review purpose basis, privacy, storage cost, index capacity, and contracts. "Increasing just to be safe" is not automatically permissible.

## 27. Scenario: Investigating a Slow-to-Detect Incident

Suppose a bug begins occurring after a deploy and is only detected 10 days later.

- DEBUG is kept for only 3 days: granular code details may already be lost.
- INFO/ERROR is kept for 14–30 days: business-level evidence or error codes remain.
- Aggregate metrics and traces may have different retention, helping pinpoint when errors spiked.
- Required audit events have their own preservation schedule; you should not rely on DEBUG as verifiable history.
- If incident detection time frequently exceeds INFO retention, review SLOs/purpose: extend **necessary** logs, keep summaries longer, or improve early detection.
- You cannot solve this by "recovering logs from the JVM" if all copies were already validly cleaned up.

The lesson is that retention must align with **how far back you actually need to look to investigate**, not just an easy-to-remember number of days.

## 28. Scenario: Too Many Logs, Costs Exceeding Budget

A team discovers DEBUG level was left on continuously and disk/index usage is growing rapidly.

Ordered solutions:

1. Reduce **event volume and redundant data at the source**: disable unnecessary DEBUG, apply controlled diagnostic sampling, avoid dumping raw payloads.
2. Define a lean log event schema, dropping unnecessary fields.
3. Control local file size/rotation so hosts do not fill up, while accounting for shipper/ACKs and data loss.
4. Use backend-appropriate tiering/compression/indexing strategies.
5. Review hot query needs before reducing **total retention**.
6. Evaluate security/audit groups separately; do not use size caps to silently delete them.
7. Create disk-full forecast alerts and have owners approve the new policy.

**Common mistake:** cutting every index to 3 days to save money, only to have an incident 4 days later that requires 2 weeks of data. Design retention around purpose and investigation experience.

## 29. Anti-Patterns When Choosing Retention

| Anti-Pattern | Risk | Fix |
| --- | --- | --- |
| "Keep everything forever just in case" | Increases PII exposure, cost, and access surface | Choose duration based on purpose and obligations |
| "ERROR must be kept indefinitely" | Not all errors need long retention | Classify by purpose, minimize data |
| "Keep DEBUG as long as audit" | Noisy, sensitive logs, wastes storage | Separate channels, shorten diagnostic retention |
| Relying on `FileHandler.count=5` and calling it 5 days | Count is number of files, not time | Time-based lifecycle at the appropriate tier |
| Configuring only Logback `maxHistory` | Backend/backups still keep data long-term | Inventory all copies |
| Using size caps for mandatory audit logs | Can delete early, losing evidence | Dedicated durable audit store/policy |
| Assuming `kubectl logs` is centralized retention | Node/pod logs can be lost | Central aggregation with lifecycle |
| Deleting by `lastModified` without considering copied files | Old data retained past deadline | Consistent time basis |
| Testing delete regex directly on `/var/log` | Deletes wrong files, breaks services | Scope folders, dry-run, allowlist |
| Ignoring legal holds | Deletes evidence that must be preserved | Hold workflow and exemption engine |
| Treating "not found in search" as bytes destroyed | Snapshots/backups/exports still exist | Verify per storage layer |
| Setting TTL shorter than shipping backlog | Loses logs before ingest | Buffering/backpressure and alerts |
| Not separating tenants/regions | Wrongful deletion or data leaks | Scoped policies, RBAC |
| Using retention to handle exposed secrets | Secrets can still be exploited | Incident response and credential rotation |
| Not testing date/timezone boundaries | Early or late deletion | UTC, fixed clock, cutoff tests |
| Not monitoring cleanup jobs | Expired data accumulates silently | Metrics/alerts/delete reconciliation |
| Applying "legally required" days from a blog post | May not fit your industry/region | Review actual applicable legal/contract terms |

## 30. Checklist Before Finalizing a Retention Strategy

1. Do you have an inventory of all Java, container, middleware, and export log sources?
2. Does each class have a clear **retention purpose, owner, and authorized viewers**?
3. Are retention durations justified by business/risk/obligations rather than guesswork?
4. Do you distinguish between DEBUG, operational, security, and audit events?
5. Have you defined **event time vs ingest time vs index rollover time**?
6. Is retention understood as total duration and tier boundaries, avoiding double-counting days?
7. Have you sized for event rate, peaks, compression, indices/replicas, query costs, and backpressure?
8. Are local appender/`FileHandler`/kubelet rotations understood properly rather than mistaken for central retention?
9. Do you document the mapping from intent → backend lifecycle config and check for drift?
10. Are Agent/Collector queues and offline backlogs monitored to prevent premature local deletion?
11. Do you have policies for handling secrets, personal data, redaction, and access/exports?
12. Is there a valid legal hold, review, and release process?
13. Is there a deletion plan across indices, object versions, snapshots, backups, exports, and quarantine?
14. Have you tested boundaries, invalid files, symlinks, live files, rollovers, legal holds, and backend delete errors?
15. Are dry-runs and approvals required before changes that could delete data in bulk?
16. Are there metrics/alerts for oldest record age, deletion failures, queue lag, and storage near capacity?
17. Do you have a 2–4 week post-incident review scenario to verify retention actually supports incident response?
18. Can you prove that records within retention **were not deleted by mistake**?
19. When policies change, do you assess retroactive impact and the impossibility of rollback?
20. Do you distinguish "not queryable" from "deleted per storage contract"?

## 31. Self-Check Questions

1. Why does Logback's `maxHistory=7` not prove data has disappeared from Elasticsearch after 7 days?
2. Is JUL's `FileHandler(limit,count)` based on days or file count/size?
3. Hot 7 days, warm until day 30, cold until day 90: what is the total retention?
4. If local file TTL is 1 day but the Collector can have a 3-day outage, what is the main risk?
5. In Log4j 2, does `IfLastModified` reflect event time or file modification time?
6. Why can an archive copied today cause mtime-based retention to behave incorrectly?
7. What should you do before executing a `Delete` action on a directory containing multiple file types?
8. Does Log4j 2 Delete with `testMode=true` delete files?
9. When an audit event is under a legal hold, can it be auto-deleted because it exceeded normal retention?
10. Does deleting an index guarantee that previous snapshots and exports have been deleted?
11. Why does a 3-day retention period not justify logging passwords?
12. Does an expired log not showing up in a dashboard prove all copies were securely erased?
13. Why can index rollover timestamps not replace event timestamps in every policy?
14. How does the Java 17 demo handle a file on the exact cutoff date?
15. In the demo, why is `audit-2026-01-01.log` still kept despite being very old?
16. If an app's log rate increases tenfold, how does count-based file retention change?
17. Why should you measure `oldest searchable event age` and `delete failures` instead of only disk usage?
18. After reducing retention from 30 to 14 days, does increasing it back to 30 automatically restore deleted data?
19. Does backend retention replace configuring kubelet's `containerLogMaxSize`?
20. What information must be approved before increasing retention for audit/security logs?

**Hints:** (1) different storage/sink; (2) file count and byte limit; (3) 90 days; (4) losing unshipped logs; (5) file mtime; (6) new mtime is not event age; (7) restrict basePath/pattern, dry-run, review; (8) no; (9) validly managed holds must be checked before cleanup; (10) no; (11) secrets should not be logged even briefly; (12) no; (13) an index spans multiple event ages; (14) kept because only dates before the cutoff are deleted; (15) it is in the hold set; (16) rotates faster, actual retention time shrinks; (17) needed to detect retention drift; (18) no; (19) no, two different tiers; (20) purpose, legal/contract, privacy, permissions, and capacity.

## 32. Official References

- [Java SE 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): `limit`, `count`, `pattern`, `append`, and file rotation.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): file operations and cleanup in the example.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): date math, cutoff, and date parsing.
- [Logback — Rolling File Appenders](https://logback.qos.ch/manual/appenders-rolling.html): `TimeBasedRollingPolicy`, `maxHistory`, `totalSizeCap`, `cleanHistoryOnStart`.
- [Apache Log4j 2 — Rolling File Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): `Delete` action, `testMode`, `IfFileName`, `IfLastModified`.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): node-level rotation, `containerLogMaxSize`/`containerLogMaxFiles`, and cluster-level logging.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): receivers, processors, exporters, pipelines, and storage-related extensions where applicable.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): event timestamp, observed timestamp, severity, and resource attributes.
- [Elastic — Index Lifecycle Management](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html): lifecycle phases and delete policies in Elasticsearch.
- [OpenSearch — Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/index/): state-based rollover/delete in OpenSearch.
- [Grafana Loki — Retention](https://grafana.com/docs/loki/latest/operations/storage/retention/): retention, compactor, and backend/schema limits.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data minimization, protection, access, and log storage.
