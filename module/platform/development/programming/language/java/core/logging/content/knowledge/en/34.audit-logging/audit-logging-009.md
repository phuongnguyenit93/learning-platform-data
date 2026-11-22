# Audit Retention in Java Core Logging

## 1. What Is Audit Retention?

**Audit log retention** is the policy and mechanism that ensures audit records are collected, stored, protected, retrieved, and disposed of only at the right time and under proper authority. The value of auditing does not lie in keeping data as long as possible, but in keeping **sufficient content to prove what happened, for the right duration, and under appropriate controls**.

Audit logs are meant to answer: *who* (or which system) performed *what action*, *on which resource*, *when*, *with what outcome*, *under what authority*, and *whether the history can be verified*. Examples include administrative privilege changes, data exports, critical configuration edits, account deletions, access policy updates, and sensitive transactions. Audit logs generally require higher reliability than diagnostic `DEBUG`/`INFO` logs.

~~~text
Audit event
  -> capture + validate schema/identity
  -> durable ingest/ACK and classification
  -> immutable/protected storage
  -> index/search (if needed)
  -> archive + verify retrievability
  -> expired? check legal hold/exceptions
  -> disposal approval + scoped deletion
  -> inventory/disposal evidence
~~~

**Audit retention does not mean simply creating an `audit.log` file and rotating it.** Rolling helps manage file size and naming, but it does not by itself address integrity, legal hold, access control, copy protection, durability, data recovery, or retention requirements from multiple policies.

### How Do Audit Logs Differ from Application Logs?

| Criterion | Standard Operational Logs | Audit Logs |
| --- | --- | --- |
| Purpose | Troubleshooting, performance monitoring, system observability | Tracing actions and accountability for investigation/auditing |
| Events | Often depends on logger level and debug configuration | Policy-defined event catalog; cannot be disabled arbitrarily |
| Completeness | May sample or drop some `DEBUG` events under load | Must control event loss and define clear handling on write failure |
| Retention period | Based on operational needs; can be short | Based on data classification, applicable obligations, and approved policy |
| Modification/deletion | Can be more flexible | Typically requires tamper/unauthorized-deletion protection and evidence retrieval |
| Access | Developers, SREs, operations based on permissions | Restricted roles, with auditing of viewing/retrieval/disposal |

**Do not use the `INFO` log level as the criterion for deciding whether a record is an audit event.** A privilege change event might be logged at `INFO` yet belong to audit; conversely, an `ERROR` stack trace does not necessarily need to be retained under audit retention rules. It is best to define a dedicated event type or schema for audit events rather than inferring them from message strings.

## 2. Who Decides the Retention Period?

There is no single `30 days`, `90 days`, or `7 years` number that applies to every Java audit log. Retention periods can depend on the **activity type**, legal jurisdiction, industry regulations, contracts, organizational policy, ongoing investigations, and personal data protection obligations.

NIST SP 800-53 (control AU-11) describes the audit retention period as an **organization-defined** value supporting post-incident investigations and organizational retention obligations. OWASP Logging guidance also notes neither destroying records before mandatory periods expire nor keeping them beyond permitted periods without justification. Therefore:

1. Business, security, compliance, and legal teams define the **record types, purpose, basis, and retention period**.
2. Engineering translates those decisions into a **versioned** policy bound to each record or batch.
3. Operations verifies that storage, backup, archive, and deletion actually enforce the policy.
4. Policy changes go through a review mechanism with rules for handling existing records; history is never retroactively altered on its own.

### Sample Policy Table (for design illustration only, not legal retention periods)

| Event Type | Purpose | Retention Anchor | Duration | Exceptions |
| --- | --- | --- | --- | --- |
| `access_granted` / `access_denied` | Access investigation | Policy-defined timestamp | Approved by security/compliance | Incident hold |
| `role_changed` | Privilege change traceability | Effective/recorded timestamp | Specified by policy | Legal hold, investigation |
| `data_exported` | Data export traceability | Contract/policy milestone | Specified by policy | Evidence preservation request |
| `payment_admin_action` | Sensitive action control | Approved business milestone | Per applicable obligations | Other hold/retention rules |
| `debug_trace` | Short-term debugging; not audit by default | Collection time | Separate operational policy | Do not mix into audit |

The **retention anchor** is not always `eventTime`. Some policies calculate from when the event occurred, when the transaction completed, when the case closed, when the contract ended, or when the archive was sealed. Do not use client-reported timestamps as the basis for safely deleting records.

### Illustrative Policy Structure

~~~yaml
# Policy documentation example ONLY, NOT a ready-to-use auto-delete configuration.
policyId: audit-access-v3
recordClass: security-access
retention:
  anchor: sealedAt
  duration: P18M       # ISO-8601 Period: 18 calendar months; illustrative value
exceptions:
  legalHold: block_deletion
  pendingInvestigation: require_review
storage:
  immutable: required
  encryptionAtRest: required
  restoreTest: required
disposal:
  approval: security-and-records-owner
  evidence: required
~~~

The code `P18M` represents 18 calendar months in ISO-8601, not a fixed number of seconds. Before deploying to production, you must clearly define the timezone, end-of-month/leap-year handling, boundary inclusivity, policy modification events, and approval owners. Do not treat the sample YAML above as compliance evidence.

## 3. When Does Retention Start and End?

An event can have multiple timestamps:

- **`eventTime`:** when the activity occurred; may come from a client or a source with clock skew.
- **`observedAt`/`receivedAt`:** when a trusted server/collector received the event.
- **`committedAt`:** when the record or manifest was durably stored.
- **`sealedAt`:** when the archive/batch was closed, sealed, and bound to a retention policy.
- **`retainUntil`:** the minimum timestamp before which the object must not be destroyed under policy.
- **`holdUntil`/legal hold:** an independent supplemental retention rule, typically lasting until properly released.

Depending on the policy, `retainUntil` may be calculated from a business milestone rather than the file creation time. Record **`policyId`/`policyVersion`** and the sealing timestamp so the decision can be reconstructed later.

**Distinguishing `Duration` and `Period` in Java:** `Duration.ofDays(30)` is 30 × 24 hours, suitable as an example of fixed elapsed time. `Period.ofMonths(18)` calculates by calendar months when added to a `LocalDate`/`ZonedDateTime`. An "18 months" obligation should not be converted to `18 * 30` days; the result can be wrong across months of varying lengths or timezones with DST.

When computing `retainUntil` for real data, use the approved calendar convention and timezone, and clarify whether expiration means **end of day** or the exact timestamp. Avoid deleting right on the boundary if `retainUntil` semantics are ambiguous, and apply the principle of **never deleting when metadata is uncertain**.

### Illustrative Timeline Example

~~~text
Day 1: event occurs / backend receives it
Day 2: batch is verified complete and sealed
Following month: moved to slower-access archive tier
Before expiration: legal hold request arrives -> blocks deletion
After base expiration: still retained because legal hold is active
After hold is released: re-check policy, all copies, and deletion permissions
When approved: controlled disposal, store disposal evidence
~~~

Moving between storage tiers **must not break committed retrievability**. Discovering an archive that exists only in an inventory list but cannot be decompressed, verified, or restored during an investigation is a failure of the retention mechanism.

## 4. Specifying Audit Records for Retention and Verification

A structured audit schema typically requires:

| Field | Role |
| --- | --- |
| `eventId` | Unique event identifier, supporting transport deduplication |
| `eventType` | Standardized action type: `role_changed`, `data_exported`, etc. |
| `eventTime` and `receivedAt` | Distinguishes when the event occurred vs. when the system received it |
| `actorId` / `actorType` | Who/which system performed the action; minimize direct personal data |
| `action`, `objectType`, `objectId` | Operation and target object |
| `outcome` | Success, failure, denied, partial |
| `tenantId` and `serviceInstance` | Context partitioning and emitting source |
| `requestId` / `traceId` | Context correlation; do not use in place of `eventId` |
| `schemaVersion` | Enables reading records across multiple software versions |
| `policyId` / `retentionClass` | Maps to the appropriate retention policy |
| `ingestionId` or manifest/batch ID | Proof of which ingestion and archive the record belongs to |

**Illustrative** JSON example, using synthetic IDs and containing no secret payloads:

~~~json
{
  "eventId": "evt-2026-000042",
  "eventType": "role_changed",
  "eventTime": "2026-11-10T08:00:00Z",
  "receivedAt": "2026-11-10T08:00:01Z",
  "actorId": "admin-ref-17",
  "actorType": "human",
  "action": "grant_role",
  "objectType": "user",
  "objectId": "user-ref-42",
  "outcome": "success",
  "tenantId": "tenant-a",
  "requestId": "req-8",
  "schemaVersion": 2,
  "retentionClass": "privileged-access",
  "policyId": "audit-access-v3"
}
~~~

**Do not log secrets, passwords, access tokens, cookies, full request/response bodies, or excessive personal data into audit logs** just because records are kept long-term. The longer a record is retained, the larger the exposure window; consider intentional pseudonymization/redaction while still preserving authorized traceability.

Message filtering in a logging framework does not authenticate the actor or action on its own. An audit record is only valuable when the source establishes an authenticated identity and confirms the action actually occurred; never trust client-supplied fields without validation.

## 5. Retention Architecture: From Java Application to Archive

A reference architecture:

~~~text
Java business operation / authorization
    |
    +--> transactional audit record or durable outbox
    |           |
    |           v
    |      reliable publisher / retry
    |           |
    v           v
Validated structured audit event
    |
    v
Collector / ingest (ACK, dedup policy, durable queue)
    |
    +--> Hot searchable storage (authorized personnel only)
    |
    +--> Immutable archive / WORM + manifest, retention policy
                 |
                 v
         Inventory / integrity checks / restore tests
                 |
                 v
       Legal hold / release / disposal approval
~~~

Not every application needs a transactional outbox. However, for audit events tied to critical database state changes, an asynchronous `logger.info("role_changed")` call **is not sufficient proof** that the event was received and durably stored. If the transaction commits and the process crashes before the log is flushed, the audit trail can have gaps.

**One way to improve completeness** is to write the audit record or outbox entry in the same transaction as the business change, then have a publisher deliver the record to an audit sink with ACK/at-least-once semantics and idempotent ingest. Retries and deduplication by `eventId` must be designed properly: at-least-once delivery prevents dropping events on transient transport failures, but can cause **duplicate deliveries**; the idempotency policy ensures the final record is not double-counted.

If the business transaction rolls back, you must decide how to audit **rejected/failed attempts**: recording failed write attempts may require a path independent of the business transaction. Do not assume "transactional outbox solves every case" when auditing also needs to capture uncommitted operations.

### Write Durability

- A successful `logger.info(...)` call usually only means the API accepted the call; an async queue may not have drained yet.
- Flushing a `FileAppender` does not prove a collector shipped the data; the file may not even have been fsynced to meet durability requirements.
- A collector ACK does not guarantee the final store committed the record unless the ACK contract explicitly specifies it.
- When a queue fills up, backends may block or drop according to policy; critical audits need explicit handling, alerting, and no silent record drops.
- On shutdown, stop producers, drain queues, and verify writers/collectors within the allowed timeout. Crashes/`SIGKILL` still require a durable architecture if audit loss is unacceptable.

**Measure each stage** `produced` → `durablyQueued` → `ingested` → `archived` to detect drops or duplicates. Do not use console line counts as proof of complete archiving.

## 6. Protecting Integrity and Immutability During Retention

Audit records must resist unauthorized modification/deletion and enable tamper detection. Protection layers serve distinct roles:

- **Least privilege:** services emitting audits can append/send records but cannot modify or delete old archives; operators reading/investigating have permissions separate from deletion permissions.
- **Encryption in transit and at rest:** TLS for transport; encryption at rest, key rotation, and decryption access control. **Encryption alone does not prevent an authorized user from deleting an object.**
- **Immutable/WORM storage:** write-once/read-many or retention lock mechanisms at the storage layer to block modification/deletion during the protection period, even if an appender misbehaves.
- **Hashes/checksums or signed manifests:** help detect modified, missing, or out-of-order data when designed with source verification and trusted keys. Simply hashing a file with SHA-256 and storing the hash next to the file in a writable directory is **not enough** to stop an attacker from altering both.
- **Replicas and availability:** replication/backups prevent loss from hardware failure; ensure replicas also enforce access and retention policies.
- **Auditing views and deletions:** reading, exporting, placing/releasing holds, changing policies, resetting retention, and disposal must all be recorded in an appropriate independent monitoring channel.

### WORM and Legal Hold

A practical example is **object storage with retention lock**. In Amazon S3 Object Lock, documentation distinguishes between `Governance` and `Compliance` modes: governance mode can be bypassed by special permissions in certain cases; compliance mode enforces stricter restrictions against modifying or deleting protected object versions. A **legal hold** is a separate hold mechanism that does not expire automatically over time; even after the retention date passes, an object with an active hold remains protected.

This is a **technology example**, not a requirement to use Amazon S3. Your choice must follow your threat model, regulations, administrator privileges, key management, and actual storage model. S3 Object Lock protects **object versions**; delete markers, versioning, and lifecycle rules must be understood properly rather than just looking at object names in a bucket.

Even when storage provides WORM, the overall system can still be non-compliant: ingestion may drop events, schemas may be wrong, retention periods misconfigured, backups missing, or read permissions too broad. WORM protects **data already placed in the protected store**, not the upstream capture from the source.

## 7. Logback Rotation Does Not Replace an Audit Retention Policy

A common misconception is setting `maxHistory=30` and claiming "we retain audit logs for 30 days." In Logback, `RollingFileAppender` and `TimeBasedRollingPolicy` manage active/archive files and delete them on rollover; behavior depends on the pattern, date/size, whether events trigger rollover, and operational conditions.

Example **`logback.xml` illustrating rolling for operational logs**, **insufficient** on its own for audits with retention obligations:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Key points to understand:

1. `maxHistory=30` with **daily** rolling generally targets up to 30 archive periods; with a monthly pattern, the meaning changes. It is not a policy that "deletes each audit event after exactly 30×24 hours."
2. `totalSizeCap=1GB` can delete old archives based on total size limits, **even if they are still within the 30 periods**. If used directly for audits requiring longer retention, this creates a premature deletion risk.
3. `cleanHistoryOnStart=true` triggers cleanup when the appender starts; a rollout or restart can delete old archives under rolling rules without any legal hold check.
4. Rolling does not provide WORM, manifests, disposal evidence, backup quotas, separate permissions, restore testing, or legal holds.
5. Active and archived files may be subject to different deletion mechanisms; do not infer archive status from a single configuration alone.

**A safer design:** if you still write intermediate files, use file rotation to manage I/O at the source tier, then **ship** audit events to storage with an independently enforced retention policy and delete source files only after durable delivery to the destination is confirmed per contract. Never rely on `totalSizeCap` or `maxHistory` at the source as the sole audit retention mechanism.

## 8. Standalone Java 17: Evaluating Retention Status Without Deleting Data

The following example illustrates how to **classify archives for review** without deleting any files or objects. The "30 days from `sealedAt`" policy here is **purely hypothetical** to produce verifiable output. In production, the anchor and duration must be approved by the applicable policy.

Save as **`AuditRetentionDecisionDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

public class AuditRetentionDecisionDemo {
    record AuditArchive(
            String id,
            Instant sealedAt,
            boolean legalHold,
            boolean integrityVerified) {}

    enum Decision {
        RETAIN,
        LEGAL_HOLD,
        REVIEW_METADATA,
        ELIGIBLE_FOR_REVIEW
    }

    static Decision evaluate(
            AuditArchive archive, Instant now, Duration retention) {

        // Legal hold always blocks deletion review, even past the base retention period.
        if (archive.legalHold()) {
            return Decision.LEGAL_HOLD;
        }

        // Missing/invalid or unverified metadata is not eligible for deletion review.
        if (archive.sealedAt() == null
                || archive.sealedAt().isAfter(now)
                || !archive.integrityVerified()) {
            return Decision.REVIEW_METADATA;
        }

        Instant cutoff = now.minus(retention);
        return archive.sealedAt().isBefore(cutoff)
                ? Decision.ELIGIBLE_FOR_REVIEW
                : Decision.RETAIN;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");
        Duration sampleRetention = Duration.ofDays(30);

        List<AuditArchive> archives = List.of(
                new AuditArchive("a-old",
                        Instant.parse("2026-10-01T00:00:00Z"), false, true),
                new AuditArchive("a-recent",
                        Instant.parse("2026-10-20T00:00:00Z"), false, true),
                new AuditArchive("a-hold",
                        Instant.parse("2026-09-01T00:00:00Z"), true, true),
                new AuditArchive("a-future",
                        Instant.parse("2026-11-11T00:00:00Z"), false, true),
                new AuditArchive("a-unknown", null, false, true),
                new AuditArchive("a-unverified",
                        Instant.parse("2026-10-01T00:00:00Z"), false, false)
        );

        for (AuditArchive archive : archives) {
            System.out.println(archive.id() + "="
                    + evaluate(archive, now, sampleRetention));
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac -encoding UTF-8 AuditRetentionDecisionDemo.java
java AuditRetentionDecisionDemo
~~~

**Deterministic stdout**:

~~~text
a-old=ELIGIBLE_FOR_REVIEW
a-recent=RETAIN
a-hold=LEGAL_HOLD
a-future=REVIEW_METADATA
a-unknown=REVIEW_METADATA
a-unverified=REVIEW_METADATA
~~~

The output was verified using Java `java.time` logic executed in JShell. Each line only **classifies**; it performs no filesystem operations. The sample data is synthetic metadata containing no real audit records.

Explanation:

- `record AuditArchive` holds metadata for an archive (which can be interpreted as a sealed batch). `sealedAt` is not inherently a legally valid retention anchor; it is chosen solely for this exercise.
- `Instant.parse(...)` uses UTC time independent of the host timezone. `Instant now` is fixed so stdout does not vary by the date it is run.
- `Duration.ofDays(30)` is 30 × 24 hours; **do not treat this as an actual compliance requirement**.
- `legalHold` is checked before time, so `a-hold` is still retained even though it is very old.
- Future timestamps, missing timestamps, or unverified integrity → `REVIEW_METADATA`; **do not delete**.
- `isBefore(cutoff)` uses strict comparison: an archive exactly at the cutoff remains `RETAIN` in this example. Actual boundary conditions must follow policy.
- `ELIGIBLE_FOR_REVIEW` **does not mean "delete immediately."** Before disposal, you must still read the latest policy, check holds in the storage repository, verify business/investigation status, check replicas, permissions, and the approval workflow.

**Intentional limitation:** In-memory `legalHold` or `integrityVerified` flags in the demo are not sufficient to authorize production deletion. Real decisions require verified metadata from an authoritative store, execution permissions, multiple checks, and audited evidence. The demo does not connect to a DB or object storage; do not add `Files.delete` into this loop as an automatic "next step."

## 9. Legal Holds and Exception-Based Retention

A **legal hold** or preservation hold is a decision to retain records relevant to an investigation, dispute, or legal request, even if the standard retention period has expired. The exact policy is determined by the organization and applicable obligations.

The control workflow should include:

1. **Creating a hold:** define the scope (events, tenant, user, time range, case ID, object version), approver, reason, and timestamp.
2. **Applying the hold across all relevant layers:** hot store, archive, replicas, in-scope backups, and generated exports/copies—not just setting a flag in a single database table.
3. **Blocking disposal:** every disposal job must query hold status **from the authoritative source** immediately before deleting, not rely on a cache from the previous day.
4. **Recording operations:** audit who placed/released holds, scope changes, retrieval requests, and all authorized decisions.
5. **Releasing a hold:** only authorized personnel may release a hold following the defined process; afterward, recalculate any other applicable retention policies.
6. **Handling overlaps:** an object may be subject to multiple policies or holds. If any valid policy still requires retention, it must not be deleted.

Do not assume that once `retainUntil` has passed an object can always be deleted; legal holds, open investigations, or other retention rules may continue to block deletion. Conversely, do not forget the opposite requirement: once all retention bases expire, keeping personal data indefinitely may violate data minimization policies.

## 10. Controlled Audit Disposal

Disposal is an **evidence-backed workflow**, not just a file deletion script.

~~~text
Inventory archives + copies
    |
    v
Determine current retention policy, anchor, retainUntil
    |
    v
Check holds, investigations, obligations, and permissions on object versions
    |
    v
Eligible? -- no/unclear --> RETAIN + alert/review
    |
    v
Dry-run + role-appropriate approval
    |
    v
Execute safe, idempotent, capped disposal
    |
    v
Verify object/version/index/replica/backup per policy
    |
    v
Store minimal disposal evidence without copying PII
~~~

**Distinguish between copies:** deleting a record from a search index does not necessarily delete the object from archives, snapshots, backups, CDNs/caches, or previously sent exports. A delete operation may only add a **delete marker** in a versioned store without removing protected older versions. For backups, you may have to wait for backup expiration schedules or use a dedicated deletion mechanism per policy. If all copies cannot be deleted immediately, the policy must specify isolation mechanisms, execution timelines, and verification methods.

In production design, a disposal job should:

- Run a **dry-run** and output eligible object IDs and eligibility reasons without including sensitive audit payloads in the report.
- Enforce an **upper bound** on the number of objects/bytes that can be deleted so a policy bug cannot wipe the entire store.
- Apply least privilege and separation of duties between who edits retention policies and who approves deletion.
- Re-check **authoritative legal holds and retention locks** immediately before acting to avoid race conditions if a hold is placed while the job is running.
- Use **version-aware** object APIs and handle storage semantics properly; retry idempotently and never auto-bypass governance/holds.
- Emit `deletion_requested`, `deletion_approved`, `deletion_attempted`, and `deletion_verified` events with IDs, timestamps, policy/version, and outcomes.
- Store disposal evidence in a protected system without inadvertently retaining the audit content that was supposed to be deleted.
- Support emergency stop and policy rollback before deletion (never assume deleted data can be recovered).

**Emitting a "delete API sent" event does not mean "all copies have been destroyed."** You must verify using appropriate permissions, APIs, and inventories, while accounting for storage lifecycle delays.

## 11. Long-Term Archives Must Be Searchable and Restorable

A system can store bytes for years and still fail an audit if it cannot locate, decrypt, or reconcile events. Ensure:

- **Inventory:** know which batch/object contains an event, along with its region/tenant, time range, and policy.
- **Manifests and metadata:** checksums/hashes, schema, codec, parser version, encryption key ID, seal timestamp, record count, and chain links where applicable.
- **Search/index:** hot index retention may be shorter than archive retention; provide a process to look up by `eventId`/`requestId` or time/tenant without manually scanning every object.
- **Decryption keys:** key rotation and destruction must align with retention; losing a key prematurely renders data **unretrievable** even though the object still exists.
- **Restore tests:** periodically restore representative samples in a restricted-access environment, verifying checksums, schema, event counts, timestamps, and evidence exportability.
- **Chain of custody:** who exported the data, from which object/version, when, output hash, recipients, and purpose—not just dashboard screenshots.
- **Availability:** replication/backups aligned with recovery requirements; monitor regional outages, IAM permissions, costs, and restore latency from cold/archive tiers.

**Hash chains and digital signatures have limits:** they help detect tampering if roots/signatures/metadata are protected independently. If an attacker controls both the event source and the signing keys, a hash chain alone does not prove an action actually occurred. Use synchronized clocks and receipts from trusted infrastructure to reduce evidence gaps.

## 12. Cost, Capacity, and Operability

Estimate projected capacity before choosing retention durations and storage tiers:

\[
\text{Raw bytes/day} \approx \text{events/sec} \times \text{bytes/event} \times 86400
\]

Then add indexes, metadata, replicas, compression (which can reduce size but cannot be predicted precisely), backups, and multi-tier storage. Do not treat `totalSizeCap` on a source appender as the total retention budget.

Illustrative example:

- 10 audit events/sec at an average of 1 KiB/event → roughly 864,000 events/day, about **844 MiB/day** of raw payload (excluding metadata, replicas, and compression).
- Retaining for 365 days at the same rate → roughly **301 GiB** of raw payload. This is only a steady-state estimate, **not a 365-day retention requirement** or an actual bill.
- Add growth, bursts, large data-export events, and index system overhead; rely on measurements rather than extrapolating from examples.

Tiering strategy:

| Tier | Purpose | Retention Notes |
| --- | --- | --- |
| Hot/searchable | Fast investigation, querying by `eventId`/tenant | Can be shorter than archive retention |
| Warm | Less frequent investigations | Preserve schema and verifiability |
| Cold/archive | Long-term retention, typically lower access cost | Check restore latency, permissions, and WORM |
| Backup/replica | Recovery from data/infrastructure loss | Retention and legal holds must cover copies too |

Moving logs to a cold tier does not mean the job is done. The system must still know **whether retention has expired**, whether retrieval succeeds, and whether unauthorized modification/deletion has occurred.

## 13. Common Failure Modes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `maxHistory=30` as a 30-day audit retention period | Rollover ignores legal holds, different periods, and size-based deletion | Dedicated retention policy at the storage layer |
| Mixing audit and `DEBUG` logs in the same auto-clean mechanism | Loses required audit logs or keeps `DEBUG` logs too long | Separate record classes and lifecycles |
| Deleting based on client `eventTime` | Clock skew or backdating can cause premature deletion | Use a policy-defined authoritative anchor |
| Deleting immediately when `retainUntil` expires | Ignores legal holds, investigations, and exceptions | Review all conditions before disposal |
| Claiming "WORM" after only `chmod`-ing files | Admins can still modify/delete; copies remain unprotected | Verify true immutability capabilities in storage |
| Encrypting data and calling it immutable | Anyone with delete permissions can still delete ciphertext | Combine encryption, WORM, and separate permissions |
| Deleting from the index while backups still hold records | Copies remain retained beyond the permitted period | Inventory and apply lifecycle rules to all copies |
| Logging audits via an async logger configured to discard | Records are lost before reaching the archive | Durable write path, backpressure/alerts/idempotency |
| Logging full user payloads "for complete auditing" | Exposes PII/secrets in long-term archives | Keep only fields needed as proof; redact |
| Destroying encryption keys before retention expires | Records exist but cannot be read | Synchronize key lifecycle with retention |
| Skipping restore tests | Undetected archive corruption or permission loss | Run periodic restore tests and record results |
| Changing policies without versioning | Cannot explain past retain/delete decisions | Store policy ID/version with evidence |
| Using a single cron job with store-wide delete permissions | Code bugs can cause mass destruction | Dry-run, approval, batch caps, least privilege |
| Treating legal hold as a local flag | Can be bypassed by other jobs | Authoritative holds in storage/policy service |

## 14. Testing Retention and Monitoring in Practice

### Functional Testing

1. **Time boundaries:** records before cutoff, at exact cutoff, and after cutoff; across timezones, leap months, month-ends, and rules anchored on event/close/seal.
2. **Legal holds:** expired records with an active hold must not be deleted; overlapping holds where releasing one leaves another active.
3. **Faulty metadata:** missing `sealedAt`, future timestamps, unverified integrity → route to review instead of deletion.
4. **Policy changes:** changing duration/version, tenant migration, legacy schemas; never silently apply a new duration to old records without an explicit decision.
5. **Storage locks:** delete operations before `retainUntil` are rejected; test object versions, governance bypass, delete markers, and legal holds.
6. **Pipeline failures:** full queues, offline collectors, lost ACKs, retries, and duplicate ingests; audit records must not vanish silently.
7. **Restores:** decrypt and verify cold-tier archives; locate specific records via inventory and reconcile manifests/counts.
8. **Security:** developers and read-only analysts cannot edit policies or delete data; restricted admins are also constrained per the chosen model.
9. **Disposal:** dry-run performs no deletions, approval is genuinely required, jobs respect batch caps, re-runs are idempotent, and evidence is recorded.
10. **Backups/exports:** after valid disposal, verify results across all in-scope locations and document constraints of independently scheduled backups.

### Useful Metrics

Track `audit_events_produced`, `audit_events_durably_ingested`, `audit_events_archived`, batch manifest mismatches, backlog age, queue drops/retries, archive/restore errors, records without an assigned policy, overdue objects pending review, active holds, archive access/export counts, and disposal successes/failures.

Alerting should not rely solely on low log volume; when an **audit source stops emitting**, the system must detect missing heartbeats/records for critical flows. Ensure independent alert channels remain operational even when the audit pipeline itself fails.

## 15. Recommended Implementation Process

1. **Build an inventory** of audit event types, owners, and sources. Separate mandatory audit events from diagnostic logs.
2. **Approve a retention matrix:** record classes, anchors, durations, timezones, legal holds, access permissions, and deletion rules; do not guess numbers from technical templates.
3. **Standardize schemas and event IDs**, minimize secrets/PII, and authenticate sources so records are investigable.
4. **Design a durable path** for events requiring high completeness; manage ACKs, retries, idempotency, shutdowns, and queue failures.
5. **Select storage** supporting least privilege, encryption, WORM/retention locks where required, inventories/manifests, and restore capabilities.
6. **Synchronize policies** across hot indexes, archives, replicas, backups, exports, and key lifecycles.
7. **Protect legal holds** using an authoritative source, defaulting to retention when conditions are missing, and auditing all sensitive actions.
8. **Build two-phase disposal:** evaluate/dry-run → approve → capped deletion → verify → store evidence.
9. **Automate tests and drills** covering time boundaries, calendar months, storage failures, legal holds, and restores.
10. **Monitor and periodically review** policies, event coverage, access permissions, archive capacity, costs, and overdue records.

**Remember:** "audit retention" is not about keeping files longer. It is a controlled lifecycle: **complete capture → durable storage → tamper/unauthorized-deletion protection → searchable and verifiable retrieval → policy/hold-based retention → timely, evidence-backed disposal**. In Java, Logback and Log4j 2 are only part of the event emission path; retention durations and audit evidence must be governed at the storage architecture and organizational process levels.

### References

- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): security logging, protection, verification, and disposal.
- NIST — [SP 800-92 Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final), [SP 800-53 Rev. 5: Audit and Accountability / AU-11](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final). These sources provide frameworks; specific durations depend on organizational policy and applicable requirements.
- Logback — [Rolling file appenders, maxHistory, and totalSizeCap](https://logback.qos.ch/manual/appenders-rolling.html).
- Amazon S3 — [Object Lock, retention modes, and legal hold](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) (an example storage solution, not a mandatory requirement).
- Java SE 17 — [Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html), [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html), [Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html).
