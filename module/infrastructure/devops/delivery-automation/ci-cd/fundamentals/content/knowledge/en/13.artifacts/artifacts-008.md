# Managing Retention to Support Verification and Rollback

An artifact is a concrete output built from a source code revision, such as a JAR, package, binary, container image, or frontend bundle. After being built and tested, an artifact may be deployed across multiple environments and reused when restoring a stable version. However, if an artifact or its associated evidence is deleted too early, the team may lose the ability to verify a past release or roll back during an incident.

**Retention** is the policy defining how long, where, under what conditions, and when artifacts and related data may be kept or deleted. The goal is to balance verification, recovery, investigation, and compliance needs against storage, security, and operational costs.

In CI/CD, retention must be designed alongside the release lifecycle. An artifact running in production, an artifact approved for rollback, and a temporary pull request artifact each have different retention value. A sound policy distinguishes these categories, binds data to commits and digests, and protects versions still required for operations.

## 1. Why Is a Retention Policy Needed?

If you keep only the latest artifact, the team can run into these problems:

- Inability to revert to a previous stable version when a new release causes failures.
- Inability to confirm whether a deployed binary is truly the binary that passed testing.
- Missing test reports, SBOMs, signatures, or provenance needed to investigate incidents and vulnerabilities.
- Inability to reproduce an issue from an older version because corresponding dependencies or images were deleted.
- Failure to satisfy audit evidence retention or contractual requirements.

Conversely, keeping every artifact indefinitely also creates risks. Old data consumes storage, drives up registry and backup costs, lengthens scan times, and may retain binaries containing vulnerabilities or unnecessary sensitive data.

Retention is an operational decision, not merely a configuration to delete files after a fixed number of days. Policy must answer: which artifacts must remain available, which evidence must accompany them, who is authorized to delete, and under what conditions cleanup is allowed.

## 2. Classifying Artifacts and Data to Retain

Not all pipeline outputs hold equal value. Classify them before setting a TTL (time to live).

| Category | Examples | Retention Purpose |
|---|---|---|
| Release artifacts | Approved JARs, packages, container images, binaries | Redeployment, rollback, distribution, and investigation |
| Intermediate artifacts | Test bundles, build outputs, pull request packages | Short-term debugging or reuse |
| Test evidence | Unit/integration test reports, scan reports, smoke test results | Proving quality conditions were met |
| Provenance and metadata | Commit SHA, pipeline run, toolchain, build parameters, digest | Tracing origin and reconstructing build context |
| SBOMs and signatures | Component lists, signatures, attestations | Supply chain analysis and integrity verification |
| Deployment data | Manifests, Helm charts, release descriptors, migration metadata | Understanding deployed configuration and supporting rollback |
| Related operational logs | Deploy logs, approval records, audit events | Investigating who performed actions and their outcomes |

A release artifact must link to its own evidence. For instance, if an image has digest `sha256:...`, its test report, SBOM, signature, and provenance must point to that digest or an unambiguous corresponding identifier. Storing reports without knowing which artifact they verified greatly diminishes their verification value.

Never store secrets, private keys, tokens, passwords, or unnecessary personal data in artifacts and metadata. If logs accidentally capture secrets, follow incident response and deletion/revocation procedures; routine TTLs do not substitute for leak remediation.

## 3. Determining Retention Periods Based on Purpose

No single retention number fits every system. Required durations depend on release frequency, defect detection speed, recovery time, audit obligations, security policies, and storage costs.

Key questions to answer:

1. **How far back might a rollback need to go?** If issues are often discovered after several days or a traffic cycle, keeping only the immediate prior version may be insufficient.
2. **Where are artifacts deployed?** Every version still running in production or critical environments must remain retrievable.
3. **Are there audit or contractual requirements?** Certain evidence must be retained for periods mandated by organizational or applicable regulatory rules.
4. **Can old artifacts be rebuilt identically?** If older artifacts cannot be reproduced bit-for-bit, retaining the original artifact carries higher value.
5. **Does an artifact pose a security risk?** Vulnerable versions should be quarantined, flagged, or access-restricted, yet evidence may still need to be kept for investigation.
6. **What are the storage costs?** Large artifacts, multi-layer images, and verbose logs may belong in different storage tiers.

### Tiered Policy Example

The table below is only a starting point for discussion; adjust it to actual operational needs and organizational retention obligations.

| Data Type | Reference Policy Example | Additional Conditions |
|---|---|---|
| Pull request or temporary build artifacts | 7–30 days | Delete earlier upon PR closure if no longer needed for investigation |
| Integration branch artifacts | Keep the last N builds or 14–30 days | Avoid retaining snapshots indefinitely |
| Published release artifacts | 180 days or longer per rollback/audit window | Retain every version still in use by environments or within the rollback set |
| Currently running production artifacts | Do not delete while still referenced | Lift protection only after replacement and expiration of the rollback window |
| Test reports, scan reports, and provenance | At least as long as proof for the corresponding release is required | Linked to commit, digest, and release ID |
| Audit/approval records | Per audit and legal policies | May carry legal holds or immutability requirements |

Do not apply the same TTL to images, reports, and logs solely because they originated in the same pipeline. Artifacts may need longer retention than verbose debug logs; conversely, audit records may outlive temporary artifacts.

## 4. Designing the Rollback Window

The rollback window is the timeframe during which the team commits to being able to revert to an earlier version using stored artifacts and data. It should be determined from risk and operational capability.

A practical way to reason about it:

- Estimate the maximum time typically needed to detect a post-release defect.
- Add time for investigation, approval, and executing the rollback.
- Factor in release cadence: if deploying multiple times a day, keep enough known-good versions to avoid losing the most recent stable baseline.
- Account for compatibility windows of database schemas, message formats, and APIs.
- Include a buffer for cases where a release defect surfaces after several newer releases have shipped.

For example, suppose a team releases weekly and often takes up to two weeks to detect delayed business-logic bugs. The team may need to keep multiple stable releases spanning more than two weeks rather than keeping only the last two artifacts. Final numbers should be grounded in incident history and rehearsed recovery capabilities.

### Do Not Delete Artifacts in Use

A critical rule is that artifacts still referenced by any environment must never enter normal deletion queues. Before deleting, the system must check:

- Is the digest still referenced by any active deployment?
- Is any release currently marked as a rollback candidate?
- Does any rollout, canary, or blue-green deployment still require the old image?
- Are any installations or customers still supported on this version?
- Is there an active investigation, security incident, or legal hold requiring retention?

Without accurate data on active references, err on the side of keeping or moving to a quarantine state pending verification. Never delete artifacts based solely on upload age.

## 5. Immutable Artifacts and Retrieval Identifiers

Retention helps only when the team can locate and retrieve the exact artifact. Every release artifact should carry:

- Product name and artifact type.
- Human-readable version or release ID.
- Source commit SHA.
- Pipeline run ID and build timestamp.
- Content-identifying digest or checksum.
- Corresponding provenance, SBOM, signature, and check results if available.

Tags like `latest`, `stable`, or `production` are typically mutable references. They are convenient for lookups or deployments, but should never be the sole identifier of a verified release. Use digests or checksums when exact content guarantees are required.

Registries should support immutable tags or policies preventing published versions from being overwritten. If an artifact must change, produce a new version/digest. Never edit an old artifact in place, as doing so breaks the link between test evidence, provenance, and the deployed binary.

## 6. Storing Artifacts Alongside Verification Evidence

A release record should allow tracing backward from a running environment to the exact inputs and release decisions. Example:

```text
Release: orders-service 2.7.1
Source commit: 4f2a9c1...
Pipeline run: ci-18452
Artifact: registry.example.com/orders-service
Digest: sha256:...
Test evidence: test-report-18452
Security evidence: scan-report-18452
SBOM: sbom-2.7.1
Provenance: provenance-2.7.1
Deployment: production-eu / deployment-927
```

These values are illustrative. In real systems, use full identifiers and machine-readable links; do not rely on collision-prone filenames or tags.

During an investigation, the team must be able to answer:

- Which commit and pipeline run created the artifact?
- Which toolchain, dependencies, and base image were part of the build?
- Which test and security gates did the artifact pass?
- Who or which process approved promotion?
- Which digest was deployed to each environment?
- Which artifact was the prior stable baseline still usable for rollback?

Retaining reports for a timeframe aligned with the release ensures answers do not disappear while the artifact remains alive. For audit-grade evidence, also retain timestamps, actor identities, and policy change trails.

## 7. Example Retention Policy as Code

Policies can be expressed in registry, pipeline, or artifact management configurations. The example below is pseudocode illustrating classification and protection rules:

```yaml
retention:
  pull_request:
    max_age_days: 14
    keep_if:
      - active_investigation

  branch_build:
    max_age_days: 30
    keep_last: 20

  release:
    min_age_days: 365
    keep_last: 10
    retain_evidence: true

  protected_artifacts:
    keep_if:
      - referenced_by_deployment
      - in_rollback_window
      - legal_hold
      - security_investigation

cleanup:
  dry_run_before_delete: true
  require_audit_record: true
  delete_only_unreferenced: true
```

These keys and values are not a standard schema for a specific registry. Real systems may configure retention by tag pattern, repository, package type, or custom lifecycle rules. Business conditions such as `referenced_by_deployment` and `in_rollback_window` must be translated into automatable checks or approval workflows.

A safe cleanup job typically runs in two phases:

1. **Inventory:** identify expired artifacts and check active references, rollback candidates, holds, and retention policies.
2. **Execute:** delete only qualifying artifacts; record job identity, timestamp, rationale, and the list of deleted digests.

Before enabling automation across an entire registry, run in dry-run mode and review the candidate list. Also verify edge cases such as multiple tags pointing to the same digest and multi-architecture manifests referencing child images.

## 8. Using Appropriate Lifecycles and Storage Tiers

Artifacts differ in access frequency and recovery requirements. Multiple storage tiers can be organized:

- **Hot storage:** actively released, deployed, or within-rollback-window artifacts needing fast downloads.
- **Warm storage:** older releases and evidence accessed infrequently yet still required for investigation or audits.
- **Archive storage:** data retained long-term and rarely accessed; restore times may be longer.
- **Expired/pending deletion:** expired data awaiting reference verification or a final grace period.

Moving between tiers must preserve identifiers, checksums, and metadata. If archive storage requires a restore operation before deployment, rollback procedures must account for restore latency and integrity verification.

Not every registry supports all tiers or lifecycle rules natively. You may need to pair an artifact registry with object storage, a metadata catalog, or an audit system. Avoid creating unmanaged copies that can diverge in digest, access controls, and deletion policies.

## 9. Retention, Backups, and Recoverability

Retention and backups serve different purposes:

- **Retention** governs how long data is kept under lifecycle and business policies.
- **Backup/replication** protects recoverability if a registry, account, storage region, or data is lost or corrupted.

Keeping an artifact for 365 days in a single registry does not guarantee recoverability if the registry is accidentally deleted or an account is compromised. For critical release artifacts, consider replication, metadata backups, separated administrative privileges, and periodic restore drills.

Checksums or digests should be verified after copying or restoring. Signatures and provenance must remain retrievable; if signing keys have rotated or expired, preserve metadata about identity and trust status at signing time per organizational policy.

Test actual restore procedures. A backup that has never been test-restored does not prove the team can recover an artifact within required timeframes.

## 10. Security and Artifact Deletion Permissions

Old artifacts can still contain compiled source code, sensitive configurations, or vulnerable dependencies. Therefore, retention must go hand in hand with access control:

- Grant artifact read permissions only to pipelines and teams that need them.
- Separate publish, promote, delete, and retention-admin permissions.
- Restrict deletion of release artifacts; require approvals or dedicated privileges for destructive actions.
- Encrypt data at rest and in transit according to platform capabilities.
- Scan artifacts and SBOMs on an appropriate schedule; newly disclosed vulnerabilities in older releases require evaluation.
- Mark artifacts no longer permitted for deployment as revoked/quarantined.
- Never use retention as an excuse to keep secrets; revoke exposed credentials and handle sensitive data via dedicated incident procedures.

An artifact revoked due to a vulnerability does not always need immediate deletion. You may need to keep an isolated copy with restricted access and a do-not-deploy label for investigation. Deletion decisions must balance security, forensics, and retention obligations.

## 11. Coordinating Retention with Databases and Configuration During Rollback

Rollback is more than picking an older JAR file or container image. A release may have changed:

- Database schemas and data.
- Message formats or event contracts.
- Runtime configuration and feature flags.
- Helm charts, manifests, and infrastructure definitions.
- API contracts with other consumers.
- Secret references or service permissions.

If the old artifact is retained yet a database migration broke backward compatibility, redeploying the old artifact alone may fail to restore the system. Use the expand-and-contract strategy whenever possible: expand the schema so old and new versions operate together, migrate data in a controlled manner, and drop old structures only after the rollback window closes.

A release bundle should retain or reference its corresponding deployment manifests, chart versions, migration metadata, and non-secret configuration. Secrets should not be packaged; use a secret manager and active runtime identities. During rollback, determine explicitly which configuration version must be restored and which secret references remain valid.

## 12. Safe Artifact Cleanup Workflow

A lifecycle job can follow these steps:

1. Build an artifact inventory by repository, type, tag, digest, creation date, and release status.
2. Cross-reference against deployment inventory to see which digests are still running.
3. Flag releases inside the rollback window, under investigation, or under legal hold.
4. Verify mandatory evidence is stored under its respective retention policy.
5. Select artifacts that are expired, unreferenced, and unheld.
6. Run a dry-run, generate a report, and obtain approval if required by policy.
7. Delete in small batches, emit audit records, and verify results.
8. Update catalogs to avoid dangling references to deleted artifacts.

If a registry uses garbage collection, understand how it handles manifests, tags, and shared layers. Deleting a tag does not necessarily delete layers immediately; running garbage collection can affect unreferenced layers. Follow the registry's documentation and assess impact before running against production data.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping only the latest artifact | No stable baseline left for rollback | Retain releases covering the rollback window plus all referenced artifacts |
| Applying one TTL to all artifacts | Deletes vital evidence early or retains too much scratch data | Classify by data type and purpose |
| Deleting by age without checking deployments | Deletes images still running or needed for recovery | Cross-reference digests with environment inventory |
| Keeping binaries while deleting test reports/provenance | Cannot prove which checks the binary passed | Retain evidence on a schedule aligned with the release |
| Using mutable tags as sole identifiers | Uncertain which exact contents were deployed | Store digests/checksums and keep metadata |
| Granting delete access to every pipeline | Broken or compromised jobs can delete releases | Separate publish/promote/delete permissions and audit |
| Retaining artifacts indefinitely | Rising costs and expanded risk surface | Implement lifecycles, tiering, and periodic reviews |
| Assuming an old artifact guarantees rollback | Ignores migrations, configs, or API compatibility | Rehearse rollbacks across the full release context |

## 14. Retention Policy Design Checklist

- [ ] Classify release artifacts, temporary builds, test evidence, provenance, SBOMs, and deployment metadata.
- [ ] Define rollback windows based on defect detection time, release frequency, and recovery capability.
- [ ] Retain every artifact still referenced by an environment or designated as a rollback candidate.
- [ ] Link artifacts to commit SHAs, pipeline runs, digests, and test/security evidence.
- [ ] Use immutable references for release artifacts and prevent content overwrites.
- [ ] Set distinct TTLs by data type, risk, and audit requirements.
- [ ] Support legal/security holds and quarantine/revoked states where needed.
- [ ] Separate publish, promote, delete, and lifecycle-admin permissions.
- [ ] Use dry-runs, reference checks, and audit logs before deleting.
- [ ] Maintain backups/replication and test restores for critical artifacts.
- [ ] Retain manifests, charts, migration metadata, and non-secret configurations needed for rollback.
- [ ] Rehearse rollbacks and verify actual recovery times.

Good retention guarantees the team still has the exact artifacts and evidence required when verification or recovery is needed. When retention periods are tied to release lifecycles, digests, deployment inventories, and rollback windows, cleanup reduces costs without sacrificing CI/CD traceability and recoverability.
