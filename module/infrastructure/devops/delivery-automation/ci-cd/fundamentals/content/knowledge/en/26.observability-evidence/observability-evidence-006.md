# Setting Evidence Retention Periods Based on Investigative Needs

## 1. Why Is an Evidence Retention Policy Needed?

CI/CD creates extensive traces throughout the release lifecycle: commits, pipeline runs, test results, build logs, artifacts, SBOMs, signatures, approvals, deployments, environment configurations, and post-deployment signals. When an incident occurs, teams must piece this trail together to answer:

- Which change was introduced into the system?
- Who or which pipeline triggered and approved it?
- Which artifact was actually deployed?
- Which tools and policies verified the artifact?
- How did the environment change before and after the release?
- When did the incident start, and which version or user group was affected?
- In what sequence did recovery actions take place?

If evidence has expired or cannot be retrieved, teams may be unable to determine the root cause, blast radius, and accountability. Conversely, storing every log, trace, and payload forever increases costs, data exposure risk, and governance complexity.

Therefore, retention periods must be based on **investigative needs, incident detection latency, service criticality, audit requirements, and data sensitivity**. No single TTL fits every type of evidence.

Within **DEVOPS_CI_CD_FUNDAMENTALS**, evidence must support traceability from Git events, pipelines as code, and build and test steps to artifacts, environments, quality gates, post-deployment verification, and rollback. A retention policy ensures this evidence remains available long enough for teams to investigate a release after it has completed.

## 2. Distinguishing Operational Telemetry from Release Evidence

Telemetry and evidence are related but answer different questions.

- **Operational telemetry** monitors service health over time: metrics, logs, traces, events, and alerts.
- **Release evidence** records what was checked, approved, built, and deployed: commit SHA, pipeline run, gate outcomes, artifact digest, SBOM, provenance, signatures, and deployment records.
- **Incident evidence** captures the course of events and response decisions: timelines, relevant logs, configuration snapshots, on-call actions, recovery outcomes, and investigation notes.

A metric time series might only be kept briefly for dashboards, whereas release records and artifact digests must remain longer to answer questions about an older version. Conversely, verbose debug logs may contain sensitive data and do not need to be retained long after their investigative purpose ends.

Do not use the logging backend's default retention for every category of evidence. Classify data before assigning TTLs.

## 3. Classifying Evidence in CI/CD

A baseline catalog can include:

| Evidence type | Examples | Investigative need |
|---|---|---|
| Source/change identity | Repository, commit SHA, branch, tag, PR ID | Identify source changes |
| Pipeline execution | Run ID, job status, runner image, workflow version | Reconstruct build/release flow |
| Build/test output | Test reports, coverage, compiler output | Investigate build failures or regressions |
| Security/quality results | SAST, SCA, secret scan, license, policy decision | Explain gate decisions |
| Artifact identity | Package version, image digest, checksum | Identify the exact released binary |
| Supply-chain evidence | SBOM, provenance, signature, attestation | Verify origin and integrity |
| Approval/audit | Approver, timestamp, change request | Verify authorization and process |
| Deployment record | Environment, revision, rollout step, result | Reconstruct environment changes |
| Configuration snapshot | Config version, feature flags, manifests | Compare before/after states |
| Runtime telemetry | Logs, metrics, traces, alerts | Investigate post-deployment impact |
| Recovery evidence | Rollback operation, previous artifact, smoke tests | Verify recovery |

Each type can have a different retention period. For example, verbose job logs may only need short-term retention; release manifests, digests, and approval records may need to be retained for as long as the artifact remains deployed or supported.

## 4. Start from Investigative Questions

Do not choose retention by asking "how many days does the system allow by default?" Start from the scenarios you need to investigate.

Examples:

- A bug that only surfaces during weekend traffic spikes.
- A CVE disclosed months after an artifact was released.
- A customer reporting incorrect data from a transaction that occurred earlier.
- A release rolled back where the team needs to know who approved it.
- A pipeline suspected of using a compromised dependency or runner.
- An audit requiring proof that an artifact was built from an approved commit and workflow.

For each scenario, determine:

1. How long does it typically take to detect the incident?
2. How far back prior to detection does the team need to inspect data?
3. What evidence is required to reconstruct the event?
4. Does the data need to be immediately searchable or only restorable from archive?
5. Who is authorized to access it?
6. When is deletion permitted?

Retention should cover both detection delay and the lookback window needed for investigation. If a defect may only appear after a long business cycle, a retention period shorter than that cycle will cause evidence to disappear before the issue is reported.

## 5. Determining Retention by Risk and Detection Latency

A practical model evaluates each evidence type across multiple factors:

- **Impact:** impact if the evidence is no longer available.
- **Detection delay:** time that can elapse before an incident is detected.
- **Investigation lookback:** time range prior to detection needed for review.
- **Sensitivity:** sensitivity level of the contents.
- **Volume/cost:** generated storage volume and cost.
- **External obligation:** confirmed contractual, audit, regulatory, or internal policy requirements.
- **Reconstruction cost:** difficulty of regenerating the evidence.

An internal scoring rubric can help categorize items, but do not turn scores into a rigid formula applied blindly to every system. A small yet critical release record may need to be retained far longer than massive debug logs.

### 5.1. Illustrative retention tiers

The durations below are discussion starting points, not mandatory standards or legal advice:

| Tier | Examples | Illustrative retention window |
|---|---|---|
| Short-term debug | Verbose job logs, trace sampling for routine triage | 7–14 days |
| Routine operations | Application logs, detailed metrics, deployment telemetry | 30–90 days |
| Release investigation | Pipeline runs, test reports, security findings, deployment records | 90–180 days |
| Long-term traceability | Artifact manifests, digests, SBOMs, provenance, approval/audit records | 1 year or product lifecycle |
| Special incidents | Evidence preserved for open incidents or investigations | Per case closure decision and related policy |

Organizations must adjust these based on defect detection cycles, customer commitments, applicable regulations, and storage capacity. Never treat illustrative figures as legally valid retention limits for every data type.

## 6. Choosing Retention Start and End Milestones

TTLs require an explicit starting point. Common calculation anchors:

- From when the log or event was created.
- From when the pipeline run finished.
- From the date the artifact was published.
- From when the release entered production.
- From when an incident was closed.
- From the end of a contract or support period.

The same type of evidence may need different anchors. For instance, job log retention may start when the job completes. Incident evidence retention may start when the incident closes to ensure the team has enough time to complete its investigation and review.

Policies should explicitly specify:

- **retention_start_event:** event starting the clock.
- **retention_duration:** minimum retention duration.
- **delete_after:** conditions sufficient for deletion.
- **hold_override:** cases requiring longer preservation.
- **archive_transition:** timing for storage-tier transition.

Do not simply state "keep for 90 days" without specifying when those 90 days begin. Also specify whether deletion is automatic after TTL or only occurs after passing legal hold and incident hold checks.

## 7. Tiered Storage: Hot, Warm, and Cold

Not all evidence needs to be queried at the same speed.

- **Hot storage:** recent, frequently queried data; optimized for search and dashboards.
- **Warm storage:** less frequently queried data that still needs relatively fast retrieval.
- **Cold/archive storage:** rarely accessed data; lower cost, though retrieval may take longer or require a restore operation.

A lifecycle may move logs from hot to warm, then to cold before expiration. However, tier transitions must not strip metadata, checksums, or links between pieces of evidence.

### 7.1. Keeping metadata searchable

One way to cut costs is keeping small metadata in the search system longer than large payloads. For example, retain release ID, commit SHA, artifact digest, environment, timestamp, and archive URI even after verbose logs move to cold storage.

During an investigation, teams locate the release via metadata first and restore only the specific evidence set needed. Ensure metadata does not expose sensitive information and that archive URIs remain valid throughout the retention period.

## 8. Retention for Logs, Metrics, and Traces

The three telemetry types have different characteristics.

### 8.1. Logs

Logs are typically large and may contain sensitive data. Separate:

- Operational application logs.
- Audit logs recording privileged actions.
- Pipeline/job logs.
- Security logs.
- Debug or temporary logs.

Audit logs and pipeline decision logs usually require different policies than debug output. Do not extend retention for all logs just because a subset needs long-term retention.

### 8.2. Metrics

Metrics can be retained longer in aggregated or downsampled form while keeping high-resolution data for shorter windows.

For example:
- Keep high-resolution metrics for investigations near release time.
- After an interval, aggregate by minute or hour.
- Retain SLIs/SLOs and error budget trends longer than raw high-cardinality metrics.

Downsampling must preserve investigative meaning. Properly aggregated percentiles are more useful than simple averages; never average pre-computed percentiles and treat the result as an interval-wide percentile.

### 8.3. Traces

Traces are usually sampled to control costs. When investigating rare errors, uniform sampling can miss crucial traces.

Approaches include:
- Tail-based sampling prioritizing traces with errors or high latency.
- Elevated sampling during a release window.
- Retaining incident-related traces by trace ID.
- Storing aggregated error rates and latencies longer than raw traces.

Ensure trace and log retention windows align with how long teams expect to correlate them by trace ID or correlation ID.

## 9. Retention for Pipeline and Build Evidence

Pipeline evidence helps reconstruct how an artifact was built.

Data worth retaining:

- Repository, commit SHA, branch, and tag.
- Workflow/pipeline definition version.
- Pipeline run ID and job ID.
- Runner image, toolchain, and dependency lockfile.
- Non-secret build parameters.
- Test reports and quality gate decisions.
- Scanner/ruleset versions and security findings.
- Artifact digest and storage location.
- Timestamps, statuses, and retry/cancellation reasons.
- Initiating user or identity.

Not all console logs need the same retention period. Test summaries, decision records, and metadata can be kept longer than debug logs. If a build log is the sole evidence for a critical step, retain that log or emit a signed attestation containing the result and a reference to the original log.

Artifacts require their own retention rules. If an artifact is deleted while its release record remains, teams can see what was deployed but cannot redeploy that exact version. Base artifact lifecycles on rollback needs, version support, and distribution policy.

## 10. Retention for SBOMs, Provenance, Signatures, and Attestations

Software supply-chain evidence is typically smaller than logs yet carries high investigative value.

- **SBOM:** inventory of components and versions inside an artifact.
- **Provenance:** description of the source, builder, and process that produced the artifact.
- **Signature:** cryptographic signature confirming identity or publisher.
- **Attestation:** structured statement about a property, such as check results or provenance.
- **Verification record:** outcome of signature verification, issuer, policy, and timestamp.

Keep this evidence at least as long as the artifact may be deployed, supported, audited, or subject to vulnerability investigation. If an artifact is still running in production a year later, deleting its SBOM after 30 days cripples the ability to identify affected components when a new CVE emerges.

An expired signature or revoked certificate does not mean historical verification records should be deleted. Preserve the information needed to explain under what context, at what time, and under which trust policy the signature was verified. Never store private keys in evidence packages.

## 11. Retention for Deployment and Environment Configuration

To investigate a release, you must know how the environment changed.

Recommended to store:

- Release ID, commit SHA, and artifact digest.
- Environment, cluster, region, and namespace.
- Deployment revision and rollout strategy.
- Traffic percentage or canary stage.
- Start time, end time, and each pause/resume event.
- Desired configuration version.
- Relevant feature flag states.
- Approvals and executing identity.
- Health checks, smoke tests, and rollout outcomes.
- Rollback or roll-forward operations.

It is unnecessary to store full copies of every secret or the entire runtime environment. Store secret version/references, configuration names, digests of sanitized snapshots, or sufficient metadata to retrieve details from an access-controlled configuration management system.

If snapshots are required for investigation, clearly define what is captured, how it is redacted, and who can access it. A configuration file may contain tokens, connection strings, or customer data.

## 12. Audit and Approval Evidence

Audit evidence answers who did what, when, and under what authorization.

Examples:

- Who approved a production deployment?
- Who modified a quality gate?
- Who created an exception for a security finding?
- Who re-ran a pipeline or replayed a webhook?
- Who changed a retention policy?
- Who accessed or exported sensitive evidence?

Audit records require stable identity, action, resource, timestamp, outcome, and correlation ID. Avoid storing only display names, as display names can change or collide.

Approval and policy-change records generally carry longer-term value than debug logs. However, retention durations must be grounded in internal, contractual, and regulatory requirements verified by the organization. Never guess a universal legal retention timeframe.

## 13. Retaining Enough Evidence to Reconstruct a Timeline

A surviving set of logs that cannot be linked to a release has minimal investigative value.

Use consistent identifiers end to end:

- `trace_id` or `correlation_id` for a processing flow.
- `event_id` for events.
- `pipeline_run_id` and `job_id`.
- `release_id` or `deployment_id`.
- `commit_sha`.
- `artifact_digest`.
- `environment` and `deployment_revision`.
- `incident_id` when an incident occurs.

Example timeline:

~~~text
09:00  Git event E-42 receives commit C
09:01  Pipeline P-118 starts
09:07  Artifact digest D is published
09:08  Security gate G-19 PASS
09:12  Release R-55 is approved
09:15  Deployment D-77 starts in production
09:18  Canary receives 5% traffic
09:24  Alert A-91 detects error rate increase
09:26  Rollback RB-12 starts
09:30  Smoke test confirms previous version is working
~~~

Timestamps must include timezone or be standardized in UTC. Clocks across runners, clusters, databases, and logging systems must be synchronized. If clocks drift by even a few minutes, timelines can sort out of order and mislead investigations.

## 14. Ensuring Evidence Integrity and Provenance

Retention only guarantees data still exists; it does not prove the data has not been tampered with.

Measures:

- Generate checksums or hashes for evidence packages.
- Sign manifests using a controlled identity.
- Use storage with versioning or immutability where appropriate.
- Separate write, read, and delete permissions.
- Audit all evidence access and export operations.
- Preserve metadata about producer origin and collection time.
- Verify checksums on archival and on restore.
- Protect signing keys in KMS/HSM or an appropriate key management service.

For evidence preserved for investigations, append-only or WORM storage can be used. Understand retention lock modes carefully: misconfiguration can prevent timely deletion of sensitive data, or allow privileged users to delete data prematurely.

Do not treat a standalone hash as proof of origin. Hashes detect tampering if the reference value is protected; signatures and audit trails add identity and timestamp verification.

## 15. Protecting Sensitive Data in Evidence

Logs and traces can inadvertently contain:

- Access tokens, passwords, or private keys.
- Emails, phone numbers, or user identifiers.
- Request/response bodies with personal data.
- SQL queries containing sensitive values.
- URLs with tokens in query strings.
- Authentication headers or cookies.
- Internal infrastructure details.

Prior to storage, apply data minimization:

1. Do not collect fields unnecessary for investigation.
2. Redact or mask secrets at the source.
3. Use field allowlists for structured logs.
4. Limit payload sizes and data types.
5. Separate sensitive data from searchable metadata.
6. Encrypt in transit and at rest.
7. Restrict permissions by role and purpose.
8. Audit access to sensitive data.

Do not rely solely on log masking in the search UI. If a secret was written to underlying storage, users with lower privileges may still extract the raw data via API or export.

The longer the retention, the larger the blast radius of over-collecting data. If raw payloads are not needed for a full year, retain normalized outcomes and required metadata long term while giving raw payloads a shorter TTL.

## 16. Access Control for Evidence

Not every team member needs to read every piece of evidence.

Permissions can be scoped by:

- Environment: dev, staging, production.
- Service or repository.
- Evidence type: build logs, security findings, audit records, incident packages.
- Sensitivity level.
- Role: developer, SRE, security, auditor, incident commander.
- Purpose: operations, investigation, audit, or customer support.

Principles:

- Enforce least privilege.
- Separate metadata search permissions from raw payload download permissions.
- Grant temporary access for specific investigations.
- Log who accessed or exported data.
- Never share public archive links.
- Periodically review permission groups and service accounts.
- Protect decryption keys separately from metadata read permissions.

An incident commander may need evidence retrieval access for a short period. Grant such access with an expiration and revoke it automatically once the incident concludes.

## 17. Legal Hold and Incident Hold

Routine TTLs must not delete data preserved for an ongoing investigation or an organizationally confirmed hold request.

- **Incident hold:** preserves evidence linked to an open incident or post-incident review.
- **Legal hold:** suspends data deletion upon formal request from legal counsel or an authorized authority.

When applying a hold, record:

- Hold ID and scope.
- Requester/approver.
- Reason and start time.
- Held evidence set or resources.
- Responsible reviewer.
- Hold release criteria.
- Release timestamp and lifecycle resumption.

Never guess when a legal hold should be applied or lifted. Follow organizational procedures and authorized sign-offs.

Once a hold ends, data does not necessarily have to be kept forever. Re-evaluate the original retention policy and resume the lifecycle if no valid preservation reason remains.

## 18. Secure and Verifiable Data Deletion

TTL expiration does not mean data vanishes immediately from every copy. Evidence may still exist in:

- Replicas.
- Backups.
- Snapshots.
- Caches.
- Search indexes.
- Downloaded exports.
- Archive copies.
- Previous object versions.

Deletion policies must specify scope and deletion latency across each system. Some backups may expire on their own schedule; document the maximum window before data leaves backups.

Store minimal deletion records including data type, scope, timestamp, policy version, and outcome. Never copy the deleted payload into the audit log just to prove deletion.

For data requiring targeted deletion, address copies, indexes, and exports according to approved procedures. When using encryption keys for cryptographic erasure, verify that all copies of the data depend on that key and no plaintext copies exist elsewhere.

## 19. Building a Retention Policy by Evidence Type

A policy should include at least these attributes:

| Attribute | Meaning |
|---|---|
| Evidence type | Category of data |
| Owner | Accountable team |
| Purpose | Reason for collection and storage |
| Classification | Sensitivity level |
| Retention start | Milestone starting the retention clock |
| Duration | Retention period |
| Storage tier | Hot, warm, or cold |
| Access policy | Who is authorized to access |
| Integrity control | Hash, signature, immutability |
| Hold behavior | Handling during incident/legal holds |
| Deletion method | Deletion mechanism and completion window |
| Restore target | Recovery time SLA when needed |

Policies should be versioned and reviewed whenever systems, risks, regulations, or release cycles change.

### 19.1. Example retention matrix

The table below is a starting example; teams must adjust durations based on investigative needs, artifact lifecycles, and confirmed requirements.

| Evidence | Retention start | Example duration | Tier after hot phase |
|---|---|---|---|
| Debug job logs | Job completed | 14 days | Delete |
| Detailed application logs | Event timestamp | 30 days | Warm aggregate for 60 more days |
| Raw traces | Trace timestamp | 14 days | Keep aggregated metrics |
| Pipeline decision/test summaries | Pipeline completed | 180 days | Cold archive if needed |
| Security scan reports | Scan completed | 1 year | Cold archive |
| Release manifests and artifact digests | Release created | Artifact lifecycle and support window | Cold archive |
| SBOM/provenance/signature records | Artifact published | Artifact lifecycle and support window | Cold archive |
| Production approval/audit events | Approval timestamp | Per confirmed audit policy | Immutable archive if required |
| Incident evidence | Incident closed or hold released | Per incident decision/policy | Cold archive |

Do not apply a single rigid duration across all repositories or environments. A service handling critical data may need a longer lookback window than an experimental dev job.

## 20. Example Retention Configuration in Pseudocode

The following example expresses policy conceptually and is not the schema of a specific storage platform:

~~~yaml
evidence_retention:
  policy_version: "2026-01"

  classes:
    pipeline_debug_log:
      owner: platform
      classification: internal
      start_event: pipeline_completed
      hot_days: 7
      archive_days: 7
      delete_after_days: 14
      redact_secrets: true

    pipeline_decision:
      owner: platform
      classification: internal
      start_event: pipeline_completed
      hot_days: 30
      archive_days: 150
      delete_after_days: 180
      integrity:
        checksum: true
        signed_manifest: true

    security_report:
      owner: security
      classification: confidential
      start_event: scan_completed
      hot_days: 30
      archive_days: 335
      delete_after_days: 365
      access:
        roles: [security, incident_commander]

    release_manifest:
      owner: release
      classification: internal
      start_event: artifact_published
      retention: artifact_support_lifecycle
      integrity:
        checksum: true
        signature_reference: true

  holds:
    incident_hold: suspend_deletion
    legal_hold: require_authorized_release

  deletion:
    audit_record: true
    verify_replicas_and_indexes: true
~~~

Fields such as `hot_days`, `archive_days`, and `delete_after_days` only illustrate policy expression. Production systems must define how total duration is computed, start anchors, backup handling, legal holds, and behavior when policies change.

In particular, retention based on `artifact_support_lifecycle` is a lifecycle-driven condition rather than a fixed day count. Define who confirms that an artifact has reached end-of-support or is no longer deployed before deleting related evidence.

## 21. Testing Evidence Retrievability

A policy only has value if the team can locate and restore evidence within the required timeframe.

Rehearse scenarios such as:

- Finding all evidence from a commit SHA.
- Identifying the artifact digest currently running in production.
- Restoring pipeline logs from cold archive.
- Verifying the signature and checksum of an evidence package.
- Reconstructing a timeline from webhook to rollback.
- Retrieving security scan results for an older artifact.
- Identifying who approved a release.
- Applying an incident hold and confirming the lifecycle does not delete data.
- Releasing a hold and verifying deletion resumes per policy.
- Verifying unauthorized users cannot download raw evidence.

Measure search and restore times. If the team needs 12 hours to restore from archive while incident procedures require a decision within 30 minutes, adjust storage tiers or prepare appropriate indexes/metadata.

### 21.1. Periodic restore checks

Periodically select an older evidence set and perform a restore in a test environment:

1. Identify the release ID and archive location.
2. Download the data using a least-privilege identity.
3. Verify checksums or signatures.
4. Correlate with the release manifest and pipeline record.
5. Confirm files are readable by current tools.
6. Record restore duration and outcome.

Do not merely check that an object exists. Formats may have changed, encryption keys may no longer be available, or indexes may have expired.

## 22. Managing Retention Policy Changes

Retention policies are critical configuration and must be controlled.

When changing durations:

- Record the policy version and approver.
- Assess whether existing data will be deleted earlier or retained longer.
- Evaluate impact on cost and queryability.
- Check for open legal/incident holds.
- Test the policy on a small subset first.
- Write an audit entry for the rollout.
- Maintain a rollback path if the lifecycle is misconfigured.

Reducing retention from 180 to 30 days can immediately make older data eligible for deletion as soon as the new policy takes effect, depending on the engine. Increasing retention can also create major costs if applied to high-volume raw data. Simulate the impact before applying changes.

Do not let individual teams set arbitrary TTLs without an owner or review process. Per-service exceptions may be allowed, provided they have a justification, expiration, and accountable owner.

## 23. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| One TTL for all data types | Critical logs lost early or debug logs kept too long | Classify by purpose and risk |
| Anchoring TTL from an unclear point | Unknown when data becomes eligible for deletion | Define explicit retention start events |
| Keeping raw logs long term instead of audit records | Rising costs and sensitive data risk | Create structured decision/audit evidence |
| Deleting SBOM while artifact is still running | Difficult to investigate new CVEs | Retain SBOM for the artifact's lifecycle |
| Keeping metadata without needed archive payloads | Cannot reconstruct incident details | Scope evidence packages by use case |
| Storing traces without correlation IDs | Cannot stitch timelines | Standardize IDs and timestamps |
| Relying on unprotected hashes | Privileged actors can alter both data and hash | Sign manifests and separate duties |
| WORM without hold/release process | May retain sensitive data past limits | Manage immutability and legal holds explicitly |
| Checking only object existence | Restores may fail in practice | Rehearse restores and verify integrity |
| Deleting primary data while forgetting replicas/indexes/exports | Data persists outside policy | Cover every copy in the lifecycle |
| Not auditing evidence access | Unknown who viewed or exported data | Enforce access logging and least privilege |
| Changing TTL without evaluating existing data | Unexpected mass deletion | Simulate and review prior to rollout |

## 24. Evidence Retention Checklist

**Purpose and scope**

- [ ] Investigative scenarios to support are listed.
- [ ] Telemetry, release evidence, and incident evidence are distinguished.
- [ ] Every evidence category has an owner.
- [ ] Classification and collection purpose are documented.
- [ ] Detection delay and investigation lookback are defined.

**Retention and storage**

- [ ] Retention start event and duration are explicit.
- [ ] Durations align with artifact lifecycles and business cycles.
- [ ] Hot/warm/cold tiers are used where appropriate.
- [ ] Metadata is sufficient to locate archives.
- [ ] SBOMs, provenance, signatures, and release records are retained long enough.
- [ ] Backups, replicas, indexes, and exports are included in the lifecycle.

**Integrity and security**

- [ ] Critical evidence has checksums/signatures.
- [ ] Access permissions follow least privilege.
- [ ] Secrets and personal data are redacted or excluded.
- [ ] Data is encrypted in transit and at rest.
- [ ] Access auditing and deletion auditing are enabled.
- [ ] Incident hold and legal hold procedures exist.

**Investigability and deletion**

- [ ] Timestamps and correlation IDs can assemble a timeline.
- [ ] Archive search and restore drills are conducted.
- [ ] Checksums are verified after restore.
- [ ] Restore times meet incident response needs.
- [ ] Deletion policy covers all copies.
- [ ] Retention policy changes are reviewed and versioned.

## 25. Conclusion

Evidence retention periods should be designed around investigative questions, incident detection latency, artifact lifecycles, and data sensitivity. Logs, metrics, traces, pipeline reports, security findings, SBOMs, provenance, approvals, and deployment records carry different values and costs, so they require distinct policies.

A sound lifecycle defines the start milestone, duration, storage tier, access controls, integrity protections, holds, and deletion method. Metadata and correlation IDs stitch timelines together; checksums, signatures, and audit trails protect provenance; restore drills prove the evidence is actually usable. When retention is governed by risk and purpose, teams have the data required to investigate releases and incidents without retaining all pipeline output indefinitely.
