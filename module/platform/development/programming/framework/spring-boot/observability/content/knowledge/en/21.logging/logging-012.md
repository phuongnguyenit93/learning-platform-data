# Log Retention in Spring Boot Systems

In the **Logging** chapter of the **SPRING_BOOT_OBSERVABILITY** module, log retention is the policy defining how long logs are kept, where they are stored, at what access level, and how they are deleted upon expiration. An observability system must retain enough logs to investigate errors, analyze incidents, and meet operational requirements, while controlling storage costs, query latency, personal data exposure, and data governance obligations.

Log retention is not merely rolling-file configuration inside an application. Spring Boot can write logs to the console or files, yet when running in containers, logs are usually collected by the runtime/agent and forwarded to a centralized platform. **Application file lifecycles, collector log lifecycles, and backend retention are separate layers.** You must know which layer holds each copy of the data and which layer is responsible for deletion.

In **SPRING_BOOT_OBSERVABILITY**, logs work alongside Micrometer Observation, metrics, and distributed tracing to investigate errors, latency, and application behavior. Retention must balance the ability to search by Correlation ID/Trace ID against storage costs and the risk of retaining sensitive data. Keeping logs longer does not automatically improve observability if logs lack structure, context, or secure governance.

## 1. What Problem Does Log Retention Solve?

A Spring Boot application can emit millions of log events per day. If kept indefinitely, storage and costs climb continuously; if deleted too soon, operations teams lose the data needed to investigate late-detected incidents or compare trends.

A retention policy answers these questions:

- How long must logs of each event category be kept?
- Do logs reside on local disk, volumes, object storage, or a centralized backend?
- Which logs require fast search, and which can move to cheaper archive storage?
- Who is allowed to read, export, delete, or place holds on logs?
- Upon expiration, how is data purged from indexes, object stores, backups, and replicas?
- How do you prove the policy is enforced and storage stays within budget?

Do not apply a single identical expiration to every log. A continuously repeating debug line has different value from a critical audit event, security event, or payment failure. Classify logs before choosing retention.

## 2. Distinguishing Log Storage Layers

A typical log flow:

```text
Spring Boot application
   |
   +--> console/stdout or rolling file
             |
             v
   Container runtime / node agent
             |
             v
      Log collector / shipper
             |
             v
    Centralized log platform
       |          |          |
       v          v          v
    hot index   warm tier  archive
       |          |          |
       +----------+----------+
                  |
             expiration
                  |
              deletion
```

| Layer | Responsibility | Retention considerations |
| --- | --- | --- |
| Application file | Log files written by Logback | Rolling/total size and old-file cleanup schedule |
| Container runtime | Captures stdout/stderr and manages runtime log files | Rotation, node disk space, and file limits |
| Collector/shipper buffer | Buffers logs when backend is temporarily unreachable | Queue capacity, disk buffer, and retries |
| Centralized backend | Search, indexing, dashboards, and alerts | Index/data stream retention or lifecycle |
| Archive/object storage | Longer-term lower-cost storage | Lifecycle expiration and access control |
| Backup/replica | Data recovery capability | Separate retention, cascading deletion, and restore policy |

**Deleting a local file does not mean the log was deleted from the backend.** Similarly, deleting a document from an active index does not necessarily delete archived or backed-up copies. When designing retention, map every copy of the data.

## 3. Classify Logs Before Setting Expiration

| Log group | Examples | Primary value | Notes |
| --- | --- | --- | --- |
| Application operational | Request started/completed, dependency timeout | Operational investigation | Can have high volume |
| Error/exception | Processing errors, connection errors | RCA and bug fixing | Never log raw payloads/secrets |
| Security | Authentication failure, suspicious activity | Security detection and investigation | Enforce strict access control |
| Audit/business event | Critical state transitions | Auditing business activity | Needs dedicated requirements |
| Debug/trace-level application logs | Internal details | Short-term debugging | High volume, usually disabled in production |
| Access log | HTTP method, route, status, duration | Traffic analysis | Avoid raw query strings containing sensitive data |

Do not automatically treat every log containing the word "audit" as a legally compliant audit record. If a process requires an audit trail with integrity guarantees, tamper controls, actor identity, and specific retention windows, design a proper audit system. Ordinary application logs can be sampled, rotated, or dropped and should not serve as the sole source of truth.

## 4. Designing Retention by Purpose and Sensitivity

An illustrative starting policy for discussion:

| Classification | Hypothetical retention example | Rationale |
| --- | ---: | --- |
| Verbose debug | 1–3 days | Only needed close to development/incident time |
| Operational logs | 14–30 days | Recent incident and operational analysis |
| Error/security logs | 30–90 days | Investigating rare events and cross-referencing |
| Audit records | Per separately approved policy | Depends on legal and business obligations |
| Infrequently queried archive | Per storage agreement | Cuts cost while preserving records |

These numbers are **technical examples only**, not legal advice or universal defaults. Actual retention must reflect processing purpose, contracts, applicable legal requirements, incident investigation needs, cost, and data-owner decisions.

Define policies by stable attributes such as service, environment, log category, data classification, and retention class. Avoid defining policies by raw Correlation ID or user ID, which fragments into too many groups and complicates operations.

### Separating Production and Non-Production

Dev/test logs can usually be kept shorter and allow higher verbosity inside isolated environments. Production should emit controlled levels and fields; temporarily enabling `DEBUG` needs an expiration, narrow scope, and automatic turn-off mechanism. Never copy sensitive production logs into dev environments to extend retention without proper masking/authorization.

## 5. Rolling Files in Logback Are Not Centralized Retention

Spring Boot normally logs to the console by default unless file logging is configured. You can set:

```yaml
logging:
  file:
    name: /var/log/orders-service/application.log
  logback:
    rollingpolicy:
      max-file-size: 100MB
      max-history: 7
      total-size-cap: 2GB
```

This illustrates configuring file logging and rolling policies in Spring Boot versions supporting those properties. Check the property metadata for your exact version. `max-history`, `total-size-cap`, and rolling behavior depend on the active rolling policy and configuration.

Meaning:

- `logging.file.name` specifies the target log file.
- `max-file-size` caps file size before rolling.
- `max-history` caps retained historical periods/files per the rolling policy.
- `total-size-cap` caps total archived file size when supported by the policy.

Rolling files limit local disk usage, yet do not control logs already shipped to Loki, Elasticsearch/OpenSearch, Splunk, or another backend. The collector may already have read and shipped the data before local files are deleted.

**Do not use rolling files as a substitute for centralized archiving** when cross-service search or long-term retention is required. Local disks are easily lost when pods/nodes are replaced.

### Direct Logback Rolling Policy Example

If explicit Logback configuration is needed, you can use `SizeAndTimeBasedRollingPolicy`:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/orders-service/application.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>
                /var/log/orders-service/archive/application.%d{yyyy-MM-dd}.%i.log.gz
            </fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Adjust examples to match the Logback version managed by your Spring Boot BOM. Do not configure rolling for the same file across multiple appenders simultaneously, or define custom `logback-spring.xml` while expecting every default property to apply identically. Pick one clear configuration source and inspect actual archive files.

## 6. `stdout` Logs in Containers and Kubernetes

In containerized deployments, a common pattern is emitting logs to `stdout`/`stderr` formatted as one event per line; the runtime or node agent captures and ships them to the centralized system.

Advantages:

- Applications do not need to manage persistent log files on container filesystems.
- The platform collects logs uniformly across services.
- Pods can be replaced while shipped logs remain available in the backend.
- Resource metadata such as namespace, pod, container, and node can be enriched by the collector.

However, `stdout` does not guarantee infinite retention. Container runtimes can rotate files, cap node disk usage, or purge logs when pods/nodes are reclaimed. Check runtime and shipper retention/rotation, disk pressure, buffering, and backend policies.

Avoid writing the same content to both `stdout` and rolling files if both are collected by agents; that creates duplicate logs. If a separate audit file is required, explicitly define which collector reads it and how to prevent double ingestion with `stdout`.

## 7. Retention in Centralized Backends

Centralized log platforms typically offer index lifecycles, data stream lifecycles, retention policies, log buckets, or object lifecycles. Feature names vary, yet conceptual steps are similar:

1. Attach classification/retention class during ingestion or routing.
2. Store fresh logs on a tier optimized for fast search.
3. Move infrequently queried data to cheaper tiers if supported by the backend.
4. Delete data once it exceeds policy expiration.
5. Verify whether replicas, snapshots, archives, and backups follow separate expirations.

```text
Days 0–7       Hot: frequent search, low latency
Days 8–30      Warm: fewer queries, lower cost
Days 31–90     Archive: slower retrieval, longer retention
After Day 90   Expire: deleted per approved policy
```

This is an illustrative tiering model; not every backend has hot/warm/cold tiers, and tier transition times can differ from retention. Check your deployed platform's semantics, including when policies execute, timezones, index rollovers, late-arriving logs, and how delayed ingestion is handled.

### Retention by Index / Data Stream

When backends organize data by index or data stream, policies can bind to log groups by service/environment/classification. Avoid creating a separate index per request or per Correlation ID. Over-partitioning inflates shard, metadata, and management overhead.

When modifying a policy, clarify whether it applies to new data, existing data, or both. Updating a retention setting may affect only indexes/data streams attached to the lifecycle policy; older indexes will not update automatically unless the policy is attached.

## 8. Estimating Storage Volume and Cost

A rough calculation:

\[
\text{Raw log volume/day} =
\text{Events/second} \times
\text{Average bytes/event} \times 86{,}400
\]

For example, a service emitting an average of 200 log events/second at roughly 1 KB per event:

\[
200 \times 1\text{ KB} \times 86{,}400
= 17{,}280{,}000\text{ KB/day}
\]

That equals roughly 17.28 GB/day in decimal units, before compression, index overhead, and replication. Over 30 days, raw volume is roughly 518.4 GB for this service under constant load.

This is not final disk footprint. Backends may compress better or worse depending on data repetition; indexes, inverted indexes, replicas, shard overhead, metadata, and backups alter total usage.

### Cost Drivers

- Events/second and average/p95 event size.
- Ratios of `DEBUG`/`INFO`/`WARN`/`ERROR` and log duplication.
- Compression ratio and index overhead.
- Replica count, shard count, and storage tier.
- Retention duration, snapshots, and backup policies.
- Ingest, query, egress, and archive retrieval fees.

Measure log bytes/day by service, environment, and category. Use real figures across multiple days covering normal traffic, peaks, and incidents; a quiet day does not represent monthly budgets.

## 9. Sampling and Retention Are Two Different Policies

Log sampling decides **which log events are emitted/ingested**. Retention decides **how long stored logs are kept**. They do not substitute for one another.

| Mechanism | Question |
| --- | --- |
| Log level | Does the application emit log events at this level? |
| Log sampling/rate limiting | Among eligible events, which ones are kept? |
| Collector filtering | Which events are accepted, enriched, redacted, or routed? |
| Retention | Until when do stored events persist? |
| Archive lifecycle | When does data move tiers or get deleted? |

For example, cutting `INFO` log sampling by 50% lowers ingest volume while still needing to retain `ERROR` logs per policy. Keeping `ERROR` logs for 90 days does not guarantee every error was logged or the collector dropped nothing. Monitor dropped events, logging levels, sampling rules, and storage expiration independently.

For tracing, Trace ID/Span ID in logs links to traces if those traces were sampled and exported successfully. If a trace is dropped by sampling, logs can still be retained under the log policy. Never infer log retention from trace retention or vice versa.

## 10. Correlation ID, Trace ID, and Sensitive Data

| Field | Investigation value | Risk / usage |
| --- | --- | --- |
| Correlation ID | Find logs for same request/workflow | Keep as structured field, never a metric label |
| Trace ID/Span ID | Open trace and identify operation | Can appear even if trace was sampled out |
| User/customer ID | Business correlation | Pseudonymize or restrict access per policy |
| Session/token/cookie | Potentially highly sensitive | Never log credentials or secrets |
| Raw URL/query | Useful for finding endpoints | Can contain tokens, emails, or personal data |
| Request/response body | Helpful for certain debugging | Usually avoid or strictly redact/allowlist |

The longer the retention, the longer a sensitive log record remains exposed. Therefore, **filtering/redacting at the source or collector prior to storage** is usually safer than relying solely on expiration cleanup.

Never write passwords, access tokens, refresh tokens, cookies, API keys, authorization headers, or sensitive payment data into logs. When an identifier must be kept, use a pseudonymized/hashed form following an approved security design; hashing does not automatically anonymize data if the value space is small or cross-referenceable.

## 11. Legal Hold, Backups, and Deletion Requirements

Some events may fall under active investigations or approved preservation requests. In those cases, a legal hold or incident hold process can temporarily suspend deletion of a defined log set.

The process should:

- Identify an owner authorized to approve holds.
- Scope narrowly by dataset, service, time window, and purpose.
- Emit audit events for hold creation, extension, and release.
- Set a review deadline to prevent indefinite holds.
- Return data to the normal lifecycle policy once the hold ends.

Backups and snapshots can retain copies longer than active indexes. When deletion is required, understand how the backend/backup executes deletion, expiration, and restores. Restoring an old backup can reintroduce expired data into the system; a post-restore process must re-apply deletion/retention.

Never keep logs longer than policy allows just because they "might be useful later." Likewise, never delete data under an approved hold. Retention windows, holds, and deletions must be decided by authorized data owners/legal/security teams.

## 12. Protecting Log Access and Integrity

Retention is not just an expiration timer. Logs can still be read or tampered with by unauthorized users if access controls are weak.

A control model:

- Application teams access only datasets/services needed for their work.
- Security teams receive escalated access under incident procedures.
- Production log access produces an audit trail.
- Exports/downloads are restricted and purposeful.
- Sensitive fields are redacted prior to or during ingestion.
- Critical audit records have separate tamper/immutability controls.
- Secrets used to export logs are managed as credentials and rotated.

If forensic/integrity guarantees are needed, evaluate immutability, checksums/signatures, access auditing, clock synchronization, and chain of custody. Plain text log files do not inherently provide these properties.

## 13. Deployment and Operations in Spring Boot

### 13.1 Choosing Platform-Appropriate Output

- Local development: console or file for easy inspection.
- VM/bare metal: console/agent or rolling files within a disk budget.
- Container/Kubernetes: structured `stdout` logs usually integrate cleanly with node agents/collectors.
- Specialized audit pipelines: separate streams and storage per approved requirements.

Do not write large files to an ephemeral container filesystem expecting them to survive pod rescheduling. If files are unavoidable, verify volume persistence, permissions, rotation, collector tailing, and disk-pressure behavior.

### 13.2 Using Structured Logging

JSON logs let backends filter accurately by field instead of parsing message strings. Illustrative event:

```json
{
  "timestamp": "2026-11-22T10:15:02.120Z",
  "level": "ERROR",
  "service.name": "orders-service",
  "environment": "production",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "event": "payment.authorization.failed",
  "error.type": "TimeoutException",
  "message": "Payment provider timed out"
}
```

This is an illustrative schema. Field names should follow your chosen convention; avoid having the same field appear as `traceId` in one service, `trace_id` in another, or nested elsewhere. A uniform schema keeps retention routing and queries reliable.

### 13.3 Monitoring Collector Buffers and Shippers

During backend outages, shippers may buffer in memory or on disk. Clarify:

- Buffer capacity and outage duration tolerance.
- When full, does the shipper drop oldest or newest events, block the application, or error out?
- Can file rotation delete files before the shipper finishes reading them?
- Do retries create duplicates?
- After a restart, how are cursors/offsets recovered?

Never let a collector block business requests indefinitely simply because the log backend is slow. Logging generally needs a bounded fail-safe policy; choosing between dropping, buffering, or backpressure depends on log category and agreed requirements.

## 14. Process for Setting and Verifying Retention Policies

1. **Inventory:** list log sources, services, formats, destinations, replicas, and archives.
2. **Classify:** separate operational, error, security, audit, debug, and sensitive data.
3. **Assign owner:** each dataset has an owner accountable for content, access, and retention.
4. **Estimate volume:** measure events/day, bytes/event, compression, replicas, and growth.
5. **Define policy:** hot/warm/archive/expiry durations and approved exceptions.
6. **Configure layers:** rolling file/runtime rotation, collector buffers, backend lifecycles, backup deletion.
7. **Validate expiration:** generate test data with suitable timestamps and verify the right layer deletes it per policy.
8. **Monitor:** track storage, ingest rate, oldest retained event, expired data, and policy errors.
9. **Review:** revisit as traffic, incidents, business needs, and data governance rules evolve.

### Operational Metrics to Watch

| Metric | Purpose |
| --- | --- |
| Log ingest bytes/second and bytes/day | Forecast storage growth |
| Events/second by service/level | Spot high-volume log sources |
| Collector queue/buffer utilization | Detect impending drops |
| Dropped/rejected log records | Measure data loss |
| Storage used and forecast | Control budget |
| Oldest/newest event timestamps | Spot ingest lag and actual retention |
| Expiration/deletion job failures | Verify policies execute properly |
| Unauthorized log access/downloads | Monitor data security |

## 15. Scenario Exercise

A Spring Boot cluster logs an average of 800 events/second, roughly 1.2 KB per event. The system currently retains logs for 30 days on hot storage. The backend is exceeding budget; the team proposes cutting retention to 7 days and deleting all local files every night.

**Questions:**

1. What is the estimated daily raw log volume?
2. Why does deleting local files not ensure the centralized backend keeps only 7 days?
3. Which log classifications should be separated before shortening global retention?
4. Which data layers must be checked to ensure expiration actually occurs?
5. How can costs be cut without losing data needed for investigation?

**Analysis hints:**

- Raw volume: 800 × 1.2 KB × 86,400 = 82,944,000 KB/day, or roughly 82.94 GB/day in decimal units, before compression/indexing/replicas.
- Local files and centralized backends have independent lifecycles; the collector may have already shipped logs before local files were deleted. Backend retention must be configured separately.
- Separate debug/operational/error/security/audit; audit logs may require their own approved policy. Do not cut everything uniformly if needs differ.
- Inspect application rolling files, runtime container logs, collector buffers, backend indexes/data streams, archives, snapshots, and backups.
- Trim verbose/duplicate logs, standardize structured fields, redact data, tier hot/warm/archive, and align retention by purpose rather than deleting blindly.

### Completion Checklist

| Topic | Can explain/verify |
| --- | --- |
| Log lifecycle | Knows local files, runtime, collector, backend, and backups are separate layers |
| Classification | Separates operational, error, security, audit, and debug |
| Rolling files | Distinguishes local rotation from centralized retention |
| Container logs | Understands `stdout`, runtime rotation, and node disk limits |
| Backend lifecycle | Understands hot/warm/archive/expiration |
| Capacity planning | Calculates bytes/day and impact of compression/replicas/indexes |
| Sampling vs retention | Distinguishes emitted events from stored duration |
| Correlation fields | Uses Correlation ID/Trace ID to find logs, never as metric labels |
| Privacy/security | Redacts secrets, restricts access and exports |
| Backups/legal hold | Has policies for holds, deletion, and restores |
| Verification | Monitors ingest, drops, oldest event, and deletion failures |

**Remember:** Log retention defines where logs live, how long they stay, who can access them, and when data must expire. Logback rolling files, container runtime rotation, collector buffers, centralized backend lifecycles, and backup retention are independent layers. Classify logs by purpose, measure volume, configure expiration at every layer holding copies, protect sensitive data, and verify actual deletion. Combining metrics, structured logs, Correlation IDs, and trace context enables effective investigation while controlling cost and data lifecycles.
