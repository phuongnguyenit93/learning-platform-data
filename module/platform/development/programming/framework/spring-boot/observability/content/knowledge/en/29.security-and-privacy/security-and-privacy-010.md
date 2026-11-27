# Data Retention for Observability in Spring Boot

Observability continuously generates data: metrics, logs, traces, events, and operational metadata. If everything is stored indefinitely, storage and indexing costs climb, queries slow down, sensitive data persists longer than necessary, and the blast radius of a security incident grows larger. If deleted too soon, operations teams may lose data needed for incident investigation, SLO reconciliation, or audit requirements. **Data retention** defines what data is kept, for how long, where, who has access, and how data is deleted when it expires.

In the **SPRING_BOOT_OBSERVABILITY** module, Data Retention is part of Security and Privacy. Policies must coordinate Micrometer metrics, application logs, distributed traces, exporters, collectors, and backend storage. This lesson focuses on classifying signals, setting purpose-based retention, minimizing data before export, managing TTL and deletion, handling backups/replicas, access control, auditing, testing, and operational runbooks.

## Learning Objectives

1. Explain data retention and why observability needs dedicated policies.
2. Distinguish retention for metrics, logs, traces, and audit records.
3. Define purpose, owner, duration, and storage location for each data category.
4. Distinguish sampling, aggregation, redaction, and retention.
5. Design TTL, rollover, compaction, and deletion in storage backends.
6. Handle backups, replicas, archives, and data exported to third parties.
7. Reduce sensitive data before it leaves the application.
8. Apply access control, auditing, and legal holds.
9. Test retention, deletion, and data recovery according to policy.

## 1. What Is Data Retention?

Data retention is the set of rules defining how long data is kept and how it is handled throughout its lifecycle. For observability, data can be generated in Spring Boot, routed through an agent or Collector, stored in backends, copied to replicas, backups, or archives, and only then deleted.

A complete policy must answer:
- For what purpose is the data collected?
- Who owns the data and who is accountable for the policy?
- Which data is allowed to contain identifying information?
- In which systems and regions is the data stored?
- Does TTL start at creation, ingestion, or partition closure?
- Upon expiry, is data deleted, aggregated, or archived?
- Do backups/replicas share the same deletion schedule?
- How do we prove deletion is complete?

### 1.1. Observability Data Lifecycle

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Collect["Instrumentation / Collector"]
    Collect --> Filter["Filter, redact, sample"]
    Filter --> Store["Metrics / logs / traces backend"]
    Store --> Query["Dashboards and investigation"]
    Store --> Backup["Backup / archive"]
    Store --> Expiry["TTL / retention expiry"]
    Expiry --> Delete["Delete or cryptographic erase"]
    Backup --> ArchiveExpiry["Archive expiry"]
    ArchiveExpiry --> Delete
    Delete --> Audit["Deletion audit evidence"]
~~~

Retention is not merely a TTL setting in the primary backend. Data can persist in queues, caches, replicas, backups, export files, SIEMs, or data lakes. You must map the full data path before claiming a data category has been deleted.

### 1.2. Retention Is Not Backup

Backups serve disaster recovery; retention limits how long data is stored. Backups can retain old copies after data has expired in the primary store. Therefore, backups need their own expiration schedule, access controls, and procedures for handling deletion requests.

## 2. Classifying Observability Data

Do not apply the same TTL to every signal. Each type has different purposes, volumes, cardinality, and sensitivity.

| Data Type | Primary Purpose | Characteristics | Retention Considerations |
| --- | --- | --- | --- |
| Metrics | Trends, SLI/SLO, alerting | Aggregated time series | Long enough for trend analysis |
| Application logs | Event/error investigation | Free-form content, may contain PII | Shorter if containing detailed data |
| Distributed traces | Investigating specific requests | High volume, sampled | Shorter or tiered |
| Audit records | Proving actions/access permissions | Requires integrity and traceability | Per legal/organizational policy |
| Profiles | CPU/memory optimization | Can contain stacks/contexts | Short, restricted access |
| Events | Deployments, configs, incidents | Milestone timeline data | Based on investigation needs |

This table offers design guidance, not default legal periods. Concrete retention periods must be grounded in business needs, applicable laws, contracts, SLOs, cost, and data classification.

### 2.1. Metrics

Metrics are normally aggregated as time series. Raw resolution can help short-term investigations; downsampling preserves long-term trends at lower cost. However, downsampling can obscure short spikes or histogram details if aggregation is poorly chosen.

### 2.2. Logs

Logs can contain request payload fragments, user identifiers, exception messages, SQL text, or headers. This is typically the highest-privacy-risk signal. Minimize content right when logging, set short retention for verbose logs, and archive only log classes with a clear purpose.

### 2.3. Traces

Traces link multiple spans of a single request. They are valuable for investigating latency and dependency failures, but can carry URLs, database attributes, baggage, or custom attributes. Sampling reduces volume before storage; retention defines how long ingested spans are kept.

### 2.4. Audit Records

Audit records have a different goal than application logs. They record accountable actions such as permission changes, data access, or administrative operations. Do not treat application logs as a reliable audit trail if they can be modified, sampled, or purged under short retention. Audit stores require integrity, access controls, and separate policies.

## 3. Building a Retention Policy

A policy should be written by data class rather than storage product name. Example policy record:

| Field | Example |
| --- | --- |
| Data class | Application error logs |
| Purpose | Incident investigation |
| Owner | Service/platform operations |
| Classification | Internal, may contain identifiers |
| Source | Spring Boot application |
| Destination | Central log backend |
| Retention | Per approved schedule |
| Access | Operations role, audited |
| Deletion | TTL and backup expiry |
| Exceptions | Legal hold per approval |

### 3.1. Purpose and Data Minimization

Keep only data needed for the defined purpose. If the goal is measuring HTTP 5xx rates, metrics with status/outcome may suffice; storing full request bodies is unnecessary. If the goal is investigating query latency, normalized statements and durations are more useful than raw bind parameters.

### 3.2. Owner and Review

Each data class needs an accountable owner to:
- approve purpose and retention;
- define access roles;
- review schema/attribute changes;
- verify backends enforce TTL;
- handle exceptions/legal holds;
- confirm deletion and audit evidence.

Review the policy whenever changing exporters, Collectors, backends, cloud regions, data processors, or telemetry types.

### 3.3. Retention by Purpose, Not by Storage Capacity

A backend may permit multi-year retention, but that alone is no justification for keeping data that long. Retention duration must reflect investigation needs, reporting cycles, contracts, and applicable regulations.

## 4. Sampling, Aggregation, and Retention

Three mechanisms are frequently confused:

| Mechanism | Timing | Effect | Affected Data |
| --- | --- | --- | --- |
| Sampling | Before or during trace recording/export | Selects which traces/spans are kept | Trace volume |
| Aggregation/downsampling | In pipeline or storage | Merges data into lower resolution | Metrics/events depending on system |
| Retention/TTL | After data is stored | Deletes data upon expiry | Ingested data |

Sampling is not retention. A trace dropped prior to export cannot be recovered by increasing retention. Conversely, exported traces still need TTLs to bound storage duration.

### 4.1. Head Sampling and Tail Sampling

Head sampling decides early when a trace starts. It saves resources, but can miss error traces if a drop decision is made before the final outcome is known. Tail sampling at the Collector can keep error or high-latency traces if all spans of a trace reach the same pipeline and the Collector has enough data to decide.

Regardless of sampler, backend retention must still be configured independently. Never treat sampling probability as a guarantee of keeping data for a given number of days.

### 4.2. Metrics Downsampling

One strategy keeps high-resolution metrics briefly and stores minute/hour rollups longer. Choose the proper aggregation for each meter type:
- counter: compute rate or sum over a window;
- gauge: pick average/min/max or last value per purpose;
- histogram: merge buckets or compute quantiles per backend capability;
- summary: understand limitations when aggregating percentiles.

Never average independently computed percentiles and call the result a system-wide percentile.

## 5. Retention for Metrics, Logs, and Traces

### 5.1. Metrics Backend

Metrics backends typically provide retention per tenant, workspace, block, or time-series database configuration. When downsampling:
- keep raw data long enough for incident investigation;
- keep rollups long enough for capacity/SLO trends;
- keep histogram buckets required for latency analysis;
- monitor cardinality and series churn;
- check whether retention applies to remote-write replicas and long-term storage.

### 5.2. Log Backend

Log storage may use index lifecycle, data stream lifecycle, or per-partition TTLs. Designs should cover:
- rollover by size/age;
- hot/warm/cold tiers if available;
- deleting indexes/partitions on expiry;
- shorter retention for debug logs;
- separating security/audit logs from application logs;
- ensuring archives have encryption and access controls.

### 5.3. Trace Backend

Trace backends may store spans by block/partition or TTL. Volume depends on traffic, spans per trace, sampling rate, and attribute size. Measure ingest rate and storage growth, set TTLs per data class, and inspect compaction/deletion in block stores.

### 5.4. Spring Boot Is Not the Sole Place to Configure Retention

Spring Boot/Micrometer emits and exports telemetry; retention is usually managed at the Collector, metrics/logs/traces backends, or storage platform. Do not look for a single universal Spring Boot property to set retention across all backends. Configuration must live where data is actually stored.

## 6. Reducing Data Before Export

Good retention starts by not collecting unnecessary data. Data already exported to multiple systems is far harder to delete synchronously.

Measures:
- allowlist attributes instead of capturing all headers;
- redact `Authorization`, cookies, tokens, and query secrets;
- never log request/response bodies by default;
- never put user/order/request IDs into metric labels;
- normalize SQL and drop bind values;
- cap baggage keys and value lengths;
- standardize exception categories;
- bound event payloads and stack traces.

### 6.1. Redaction in the Application

Example of safe metadata logging:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private static final Logger log =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentMethod, String accountReference) {
        log.info("Payment authorization requested: method={}, accountRefPresent={}",
                paymentMethod, accountReference != null);
        // Perform authorization without logging accountReference itself.
    }
}
~~~

This example records only the validated payment method type and whether a reference is present; it does not log the account reference. If `paymentMethod` comes from the caller, allowlist/normalize it before logging to keep the value set finite.

### 6.2. Redaction at the Collector

Collector processors can filter/drop attributes or redact content before exporting to backends. This is an extra defense layer and should not be the only layer if data has already been written to local logs, queues, or exporter debug output.

### 6.3. Do Not Use High-Cardinality Fields to Identify Records

A Trace ID can help look up a specific request in the trace backend, but it is unsuitable as a metric label. User ID, email, account number, and request payload must be removed or tokenized per policy. Tokenized data remains linkable as long as the mapping exists; protect the mapping separately.

## 7. TTL, Rollover, Compaction, and Deletion

TTL is the duration data is permitted to exist before expiring. Backends may run deletion periodically rather than deleting the exact second TTL elapses.

### 7.1. Determining the TTL Start Clock

Some systems measure TTL from event timestamp; others use ingest time or index creation time. If events arrive late or are replayed from a queue, actual retention can differ from expectations. Policies must state explicitly which timestamp governs TTL.

### 7.2. Rollover and Partitioning

Rollover creates new indexes/blocks by age or size. Daily/weekly partitions simplify deleting expired data by dropping partitions, though overly tiny partitions create metadata and query-planning overhead. Choose granularity based on ingest rate and backend.

### 7.3. Compaction and Tombstones

Some storage engines mark deleted data with tombstones and reclaim disk space later during compaction. Consequently, TTL expiry and physical space reclamation can happen at different times. Monitor compaction backlogs and storage usage; never claim physical erasure the instant a record stops being queryable.

### 7.4. Deletion Evidence

Retain minimal evidence of policy version, data class, deletion job execution time, partition/index scope, and outcome. Audit evidence must not copy the deleted data's contents. For subject-level deletion requests, verify whether the backend supports filter/delete by subject or requires a partition/key strategy upfront.

## 8. Backups, Replicas, Archives, and Downstream Copies

Observability data can be copied to:
- replicas for availability;
- snapshots for disaster recovery;
- object storage for archiving;
- SIEM/data lakes for correlation;
- vendor SaaS for search/alerting;
- local disk buffers or message queues.

Every copy must appear in the data inventory and retention policy.

### 8.1. Backup Expiration

Backups follow their own expiration schedule. If a record has passed its TTL in primary storage yet remains in a snapshot, the policy must specify when the snapshot expires or how restores are handled so expired data is not resurrected.

### 8.2. Restore Behavior

When restoring an older backup, the system should run expiry/deletion reconciliation before opening broad access. Otherwise, expired data can reappear. Test restore workflows using data with expiry timestamps.

### 8.3. Downstream Processors

If telemetry is forwarded to a SIEM, data lake, or vendor, contracts and processor configurations must govern retention, deletion, region, subprocessors, and notification upon policy changes. You cannot guarantee end-to-end deletion solely by deleting data in the first backend.

## 9. Access Control, Encryption, and Legal Hold

Longer retention extends the window during which data can be accessed. Pair retention with:
- authentication and role-based access;
- tenant/service isolation;
- encryption in transit and at rest;
- audit logs for queries, exports, and admin actions;
- restrictions on bulk exports;
- secrets management for exporter credentials;
- legal holds with an owner, scope, and expiry/review date.

### 9.1. Least Privilege

Developers may need access to their own service's traces; the security team may need audit logs; platform operators manage the backend. Never grant read access to all logs/traces to everyone simply because they can deploy applications.

### 9.2. Legal Holds and Exceptions

A legal hold can pause deletion for a defined data scope. A hold requires a reason, approver, scope, review date, and release condition. Never let a hold turn into indefinite retention by default.

### 9.3. Encryption and Key Lifecycle

Encryption at rest does not replace retention. If using cryptographic erasure, manage keys per data class/tenant and prove all ciphertext copies become undecryptable after key destruction. Backups of keys can defeat erasure goals if left unaddressed.

## 10. Testing Retention and Deletion

Do not only check that a TTL setting exists; verify data actually disappears according to backend semantics.

| Test | Objective | Evidence |
| --- | --- | --- |
| TTL policy test | Correct config per data class | Backend policy/config |
| Expiry integration test | Expired data is no longer queryable | Queries before/after expiry |
| Backup expiry test | Old snapshots deleted on schedule | Inventory/restore test |
| Restore reconciliation | Restore does not resurrect expired data | Expiry reconciliation report |
| Redaction test | Secrets/PII not exported | Captured telemetry assertions |
| Access test | Roles read only authorized scope | Authorization tests/audit |
| Legal hold test | Hold blocks deletion within exact scope | Hold/release audit |
| Deletion audit test | Deletion proof exists | Job logs and backend state |

### 10.1. Testing Redaction Before Export

Use a test exporter or in-memory collector receiver. Emit telemetry containing synthetic markers such as `token-test-value` and synthetic emails, then verify markers never appear in exported attributes, logs, or payloads. Never use real secrets in tests.

### 10.2. Controlled TTL Testing

Use very short retention in a test backend or clock abstraction if supported by the backend. Create a record, query before expiry, wait/advance the clock per the test contract, and verify the record is no longer queryable. Physical storage may be reclaimed later via compaction; tests should distinguish logical deletion from physical reclamation.

### 10.3. Cross-Pipeline Deletion Testing

Create a synthetic record with a dedicated correlation marker in a test environment. Track the marker across primary, replicas, archives, and downstream sinks. After deletion, verify the marker is no longer queryable anywhere in scope. Never distribute real data to test deletion.

## 11. Troubleshooting Data Retention

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Storage grows despite configured TTL | TTL not attached to new indexes or compaction backlog | Check policy attachment, partitions, and compaction |
| Old data remains queryable | TTL measured from ingest time or job has not run | Check timestamp basis and expiry jobs |
| Deleted in primary but remains in backup | Independent backup retention | Schedule snapshot expiry and restore reconciliation |
| Data reappears after restore | Restore skips expiry policy enforcement | Run reconciliation before reopening access |
| PII remains in traces | Attribute capture lacks redaction | Filter before export and test payloads |
| Log backend keeps data longer than expected | Misconfigured index lifecycle policy or archive copy | Inspect full downstream inventory |
| Historical metrics lost too early | Low retention or misconfigured downsampling | Review SLO/reporting needs and tiered storage |
| Trace volume exceeds budget | Sampling insufficient or spans too large | Inspect traffic, spans/trace, and attributes |
| Deletion job runs without freeing space | Tombstones/compaction incomplete | Inspect storage engine reclamation |
| Cannot prove deletion | Missing audit evidence | Record job scope, time, policy version, and result |
| Legal hold retains data indefinitely | No review/expiry owner | Establish review cadence and release process |
| SaaS still holds copies | Vendor policy out of sync | Check contracts, processor settings, and deletion APIs |

### 11.1. Investigation Workflow

1. Identify the data class and storage purpose.
2. Map source → Collector → backend → replicas/backups/archives/downstream.
3. Determine the TTL clock: event time, ingest time, or index time.
4. Check whether the policy is attached to all new indexes/tenants/streams.
5. Inspect expiry jobs, tombstones, compaction, and physical reclamation.
6. Locate copies outside the primary store.
7. Verify whether a legal hold or exception applies.
8. Inspect deletion evidence and access permissions.
9. Run a synthetic deletion test if end-to-end verification is needed.

## 12. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Complete data inventory | Metrics/logs/traces/audit/backups/downstream |
| Purpose and owner defined | Policy record with accountable owner |
| Retention per data class | Approved and configured TTL |
| Sampling separated from retention | Trace sampling and backend TTL distinct |
| Redaction before export | Tests show no secret/PII markers |
| Sensible metrics downsampling | SLIs/histograms remain analyzable |
| Clear log lifecycle | Rollover, hot/warm/cold, and expiry |
| Clear trace lifecycle | Sampling, TTL, block compaction |
| Backups/replicas have expiry | Restores do not resurrect expired data |
| Downstream processors governed | Contract/retention/deletion scope |
| Access control and encryption | Roles, auditing, at-rest/in-transit |
| Legal holds reviewed | Owner, scope, review/release |
| Deletion evidence | Job result and policy version |
| Retention drift alerted | Storage age/expired data monitoring |
| Restore and deletion tested | Evidence from test environments |

## 13. Hands-On Exercise: Designing a Retention Policy for `order-service`

**Context:** `order-service` exports Micrometer metrics, structured logs, and OpenTelemetry traces to a Collector. Telemetry is stored in metrics, log, and trace backends; some logs are forwarded to a SIEM. Logs currently include request identifiers and traces include database attributes. Storage costs are rising and the security team requires proof that expired data is deleted from all copies.

**Tasks:**

1. Inventory all telemetry sources, Collectors, backends, replicas, backups, and downstream sinks.
2. Classify metrics, logs, traces, and audit records, and define purpose/owner.
3. Propose retention per data class based on organizational policy and investigation needs.
4. Design raw metrics retention alongside downsampling for long-term trends.
5. Assign appropriate TTLs to detailed logs and traces; separate audit records.
6. Verify sampling is not confused with retention.
7. Redact tokens, emails, query values, and identifiers before export.
8. Configure rollover/TTL and verify the policy applies to new indexes/streams.
9. Schedule backup/archive expiry and restore reconciliation.
10. Add access control, encryption, auditing, and legal hold workflows.
11. Create a synthetic marker and test end-to-end deletion across backend/replica/SIEM test sinks.
12. Write runbooks for TTL drift, storage growth, deletion failures, and restores.

**Expected deliverables:** data inventory, retention policy with owner/purpose/TTL, pipeline redaction, backend lifecycle configuration, deletion evidence, and runbooks.

## 14. Takeaways

Data retention defines which observability data is kept, for how long, where, who accesses it, and how it is deleted. Metrics, logs, traces, audit records, and backups have different purposes and sensitivity, so they require distinct policies. Sampling reduces trace volume before storage; aggregation/downsampling lowers resolution; TTL deletes stored data. These three mechanisms do not replace one another.

Minimize data at the source, redact before export, and avoid collecting unnecessary secrets/PII. Track TTLs across primary stores, replicas, queues, backups, archives, and downstream processors. Test logical deletion, physical reclamation, restore reconciliation, and audit evidence. Retention must reflect purpose, organizational/legal requirements, and data classification; no single duration fits every system. Use metrics to monitor storage/expiry, logs to record lifecycle jobs and audits, and traces to investigate requests within the policy-approved window.

**References:**
- [OpenTelemetry — Collector Processors](https://opentelemetry.io/docs/collector/components/processor/)
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Prometheus — Storage](https://prometheus.io/docs/prometheus/latest/storage/)
- [Grafana Loki — Retention](https://grafana.com/docs/loki/latest/operations/storage/retention/)
- [Grafana Tempo — Retention](https://grafana.com/docs/tempo/latest/configuration/manifest/)
- [Elasticsearch — Data Streams and ILM](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
