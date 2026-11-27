# Revalidating Artifacts or Configurations When Changes Occur After Approval

## Learning objectives

After this lesson, learners will be able to:

- Explain why an approval is valid only for the exact artifact, configuration, environment, and policy that were reviewed.
- Identify changes that render evidence or approval decisions stale.
- Design a way to record artifact and configuration fingerprints in approval records.
- Distinguish changes that affect deployment behavior from purely descriptive edits.
- Organize revalidation and require fresh approval when the release target changes.
- Prevent modifications from occurring between the final check and deployment execution.
- Retain audit trails showing exactly which version was approved and which version was actually deployed.

## 1. Why revalidate after approval?

In a CI/CD workflow, approval is typically granted after an approver reviews the artifact, test results, configuration, and deployment scope. Yet between the moment of approval and the moment of deployment, those components can still change.

Examples:

- The artifact is rebuilt from the same branch and produces a different digest.
- A tag such as `latest` or `release` is repointed to a different image.
- Helm values or deployment manifests are edited.
- A feature flag is toggled on or off.
- A secret is rotated or pointed to a different version.
- A dependency or base image changes.
- The target environment is updated by another pipeline.
- The release policy is modified after the approver reviewed the request.
- Test results or security reports no longer match the artifact about to be deployed.

If the pipeline only checks that the approval status equals `approved` without verifying the current target, the system may deploy a different version than the one the approver reviewed.

This is a workflow integrity failure: the decision was made for one state, while the action is applied to another state.

Core principle:

> An approval must bind to the exact target and scope reviewed. If a meaningful change alters that target, revalidate and determine whether fresh approval is required.

Therefore, an approval must never be a standalone status flag. It requires context, evidence, timestamp, approver identity, and identifiers of the approved contents.

## 2. What is being approved?

A deployment request typically comprises multiple components. Recording only the application version is insufficient when actual behavior also depends on configuration and environment state.

An approval record should identify at minimum:

| Component | Identifier to record | Why it is needed |
|---|---|---|
| Artifact | Digest or immutable ID | Identifies the exact package being deployed |
| Source | Commit SHA and repository | Traces the source code that produced the artifact |
| Build | Pipeline run, toolchain, and provenance | Shows how the artifact was built |
| Deployment manifest | Manifest revision or digest | Identifies resources and deployment parameters |
| Configuration | Resolved configuration revision or fingerprint | Captures expected application behavior |
| Environment | Environment ID and relevant state version | Identifies where the change lands |
| Policy | Policy or rule-set version | Records the approval criteria in effect at the time |
| Evidence | Test, scan, signature, and verification results | Proves conditions were satisfied |
| Approval | Actor, timestamp, scope, and outcome | Establishes who authorized which action |

Not every system can pack all of this into a single digest. Still, the pipeline needs a consolidated record or manifest sufficient to link these identifiers.

This set can be called a **deployment request snapshot**: a versioned snapshot of the deployment request at the moment the approver reviewed it.

For example, an approver does not merely approve application version 2.8.1. They approve the image with a specific digest, the tested staging configuration, a specific deployment manifest, the target production environment, and the corresponding evidence set.

## 3. Artifacts must be immutably identified

The artifact is the central subject of a release. If an approver reviews image A while the pipeline deploys image B, the earlier approval cannot be treated as valid for B.

Avoid mutable tags like `latest`, `stable`, or branch names as final identifiers for production artifacts. Tags help locate versions, yet pipelines should resolve tags to digests and use those digests consistently across checks, approvals, and deployments.

Example:

~~~text
Requested tag: service-api:release
Resolved digest: sha256:abc123...
Approval bound to: sha256:abc123...
Deployment must use: sha256:abc123...
~~~

If the tag is updated to a different digest after approval, the pipeline must detect the mismatch and halt the current run. Operators must review the new artifact.

An immutable artifact also needs provenance evidence:

- The commit that produced the artifact.
- The pipeline run that built the artifact.
- The checks executed on the artifact or matching commit.
- The digest stored in the registry.
- Signatures or provenance if required by policy.
- Revocation status or security advisories if any.

If an artifact is rebuilt from the same commit, never assume the digest will stay identical. Builds can depend on timestamps, dependencies, toolchains, or environment inputs. The new digest is the true identifier of the released payload.

## 4. Configuration is also part of the approved target

Many workflows bind approvals solely to the image or application version. Yet the same artifact can behave very differently when configuration changes.

Examples:

- A timeout limit changes from 2 seconds to 30 seconds.
- A payment provider URL switches from sandbox to the production endpoint.
- A feature flag enables a feature for all users.
- Replica counts jump sharply, altering load or cost.
- A network policy permits an additional access source.
- Helm values change the service account or access permissions.
- Migration settings enable deletion of legacy data.

Therefore, distinguish configuration types:

| Configuration type | Examples | How to track |
|---|---|---|
| Bundled configuration | Default files inside the image | Artifact digest |
| Deployment configuration | Helm values, Kubernetes manifests, Terraform variables | Revision or fingerprint of resolved configuration |
| Runtime configuration | Config service, feature flags, parameters read at runtime | Version or snapshot at approval time |
| Secret references | Secret name, version ID, or secret revision | Reference and version metadata; never store secret values |
| Environment configuration | Network, quotas, policies, dependency endpoints | Environment revision or related state |

Never write secret values into approval records or generate reports containing plaintext secrets. Store safe references, version IDs, or metadata showing which credential version is used.

For dynamic config from a config service, recording a repository filename is not enough. The pipeline must identify the actual resolved revision or configuration snapshot applied to the deployment.

## 5. Distinguishing meaningful changes from non-impacting edits

Not every edit alters release risk. Changing a comment in a config file may not affect behavior. Conversely, changing a single timeout value or permission can have substantial impact.

Establish change classification rules:

| Change type | Examples | Suggested action |
|---|---|---|
| Artifact contents | Image or package digest changed | Mandatory revalidation and new approval |
| Deployment manifest | Replicas, ports, service account, volumes, or network policies changed | Revalidate; re-approve if behavior or permissions are affected |
| Runtime config | Feature flags, endpoints, timeouts, or business limits changed | Revalidate and assess whether re-approval is needed |
| Secret reference/version | Credential or key version changed | Check policy; may require re-approval |
| Environment state | Cluster, schema, quotas, or dependencies changed | Revalidate environment conditions and compatibility |
| Policy | Security rules or release criteria changed | Re-evaluate against the new policy |
| Descriptive metadata | Comments, display labels, or non-functional descriptions | May retain approval if verified not to alter runtime content |

A conservative policy can require fresh approval whenever any revision in the snapshot changes. This is straightforward and reduces the risk of missing something.

As systems mature, semantic diffs can separate impactful changes from non-impacting ones. However, exemption rules must be explicit and auditable. Never assume a change is harmless simply because only a few lines changed.

If you cannot determine with certainty whether a change has impact, treat the old approval as stale and rerun required checks.

## 6. When does an approval become stale?

An approval is considered stale when the conditions underlying the decision have changed or are no longer trustworthy.

Common conditions include:

1. The artifact digest differs from the digest in the approval record.
2. The source commit or provenance no longer matches the approved artifact.
3. The deployment manifest changed after approval.
4. Runtime configuration changed in a field affecting behavior.
5. Secret references or versions changed in a way requiring control under policy.
6. The environment revision changed and broke compatibility assumptions.
7. Test or scan results expired or were revoked.
8. A new policy version introduces different requirements.
9. The approval validity window expired.
10. The approver or approval role is no longer valid under current policy.

Do not use elapsed time alone to determine staleness. A 5-minute-old approval can already be stale if the artifact was just replaced. Conversely, an older approval may remain valid if the entire target, evidence, and policy are verified intact and unexpired.

Two condition groups can be evaluated together:

- **Content freshness:** artifact, configuration, environment, and evidence still match.
- **Time freshness:** approval and evidence remain within policy-permitted time limits.

Both must pass before deployment.

## 7. At which moments should revalidation happen?

Do not validate only once right after the user submits a request. A delivery workflow can span hours, and dependent state can shift while waiting.

Useful checkpoints include:

### 7.1. Before creating the approval request

The pipeline resolves the artifact and configuration, computes fingerprints, verifies tests/scans, and builds the deployment request snapshot.

The objective is to present reviewers with an unambiguous target and matching evidence.

### 7.2. When the approver opens the request

The UI or approval step must display the artifact, environment, config changes, evidence, and blast radius. If the snapshot changed while awaiting review, mark it stale and disallow approving stale data.

### 7.3. Immediately after approval

Record the approval tied to the specific snapshot. If concurrent edits happened while the approver acted, verify which revision the approval actually covers.

### 7.4. Immediately before deploy

This is the most critical check. The pipeline must re-resolve or read the current state and compare it against the approved snapshot.

- If they match, proceed per policy.
- If they differ, halt deployment and mark the approval stale.
- If verification cannot complete, stop in a `blocked` state rather than passing by default.

### 7.5. During and after rollout

Some configurations or environment states can change while a rollout is underway. Verify the running version, applied configuration, and post-deployment health signals.

If the live target differs from the approved target, halt the rollout if possible and trigger appropriate incident response or recovery procedures.

## 8. Preventing TOCTOU bugs between check and deploy

TOCTOU (time-of-check to time-of-use) occurs when state changes after verification but before execution.

Example:

1. The pipeline verifies the digest and configuration.
2. Approval is recorded.
3. Another pipeline updates the manifest or changes the environment.
4. The first pipeline proceeds to deploy using stale check results.

Even though each individual step succeeded, the overall workflow can still deploy an unapproved state.

Risk can be reduced through these mechanisms:

**Deployment lock:** lock the resource scope between the final check and completion of the sensitive action. Locks need an owner, timeout, and safe release mechanism.

**Compare-and-swap or conditional update:** allow deployment only if the current revision still matches the checked revision. If state changed, reject the operation.

**Immutable reference:** use digests and immutable revisions instead of mutable tags or aliases.

**Just-in-time revalidation:** run checks immediately prior to the deploy action, after acquiring required permissions and locks.

**Single deployment controller:** serialize changes targeting the same environment through one coordinator to avoid competing pipeline updates.

Locks do not replace verification. A lock stops other pipelines from mutating resources mid-deploy, yet you still must check state before acquiring the lock and confirm revisions after acquiring it.

## 9. Workflow when post-approval changes are detected

When the pipeline detects that the current snapshot differs from the approved snapshot, behavior must be deterministic.

A reference workflow:

1. Halt before any impactful step.
2. Record which fields changed, the old revision, and the new revision.
3. Classify the change type and applicable policy.
4. Rerun affected checks.
5. Create a new snapshot if the change is accepted.
6. Request a new approval if required by policy.
7. Proceed only when an approval bound to the new snapshot is valid.

~~~mermaid
flowchart TD
    A["Approved deployment request"] --> B["Resolve current state"]
    B --> C["Compare with approval snapshot"]
    C --> D{"Any changes?"}
    D -- "No" --> E["Check freshness and policy"]
    E --> F{"Still valid?"}
    F -- "Yes" --> G["Acquire lock and recheck"]
    G --> H["Deploy exact approved artifact/config"]
    F -- "No" --> X["Block and investigate"]
    D -- "Yes" --> I["Classify change"]
    I --> J["Rerun affected checks"]
    J --> K{"Re-approval required?"}
    K -- "Yes" --> L["Create new snapshot and request new approval"]
    K -- "No" --> M["Record rationale and approval-exemption evidence"]
    L --> N["Wait for new decision"]
    M --> N
    N --> B
    H --> O["Verify and record release evidence"]
~~~

Never automatically carry an old approval forward to a new snapshot just because the pipeline can rerun tests. Fresh test results provide technical evidence; they do not replace an authorized human decision when scope or risk has changed.

## 10. Designing approval snapshots and fingerprints

A snapshot should contain the fields required to compare the approved state with the state about to be deployed.

Illustrative logical structure:

~~~yaml
deployment_request:
  request_id: release-2026-042
  target_environment: production

  artifact:
    repository: registry.example.test/team/service-api
    digest: sha256:abc123
    source_commit: 7f3a91c
    build_run: ci-1842

  deployment:
    manifest_revision: 91bd22a
    values_fingerprint: sha256:def456
    runtime_config_revision: config-218
    secret_references:
      - name: payment-api-key
        version: 12

  evidence:
    test_report: test-run-1842
    security_report: scan-1842
    provenance: provenance-1842

  policy:
    policy_revision: release-policy-18

  approval:
    status: approved
    actor: approver-id-from-platform
    approved_at: timestamp
    expires_at: timestamp
    snapshot_id: snapshot-73
~~~

This is an illustrative model, not a mandatory schema for a specific platform. IDs in the example simply demonstrate the types of data to link.

Configuration fingerprints must be computed from canonicalized contents or resolved state. Hashing only a source file when the system merges multiple files, environment variables, and values from a config service may yield a fingerprint that does not reflect the actual configuration.

Key principles:

- Use a canonical format so key ordering or whitespace does not alter fingerprints without semantic changes.
- Record the version of the fingerprinting tool or algorithm.
- Never put plaintext secrets into snapshots or hash inputs vulnerable to dictionary guessing.
- For secrets, record references and version IDs supplied by the secret manager.
- Bind fingerprints to the specific environment and artifact.
- Store snapshots immutably so auditors can inspect the exact approved content.

If configuration is assembled from multiple sources, record every source and revision involved. For example, Helm values may merge with chart defaults and environment variables injected by the deployment platform.

## 11. Revalidation does not always mean rerunning the entire pipeline

When one component changes, determine which evidence is affected.

| Change | Checks to rerun |
|---|---|
| Artifact digest changed | Build provenance, relevant tests, artifact scans, policy, and approval |
| Deployment manifest changed | Manifest validation, policy, permissions, resources/quotas, and approval by impact |
| Runtime config changed | Schema/config validation, relevant integration or smoke tests, policy, and approval if needed |
| Secret version changed | Reference checks, permissions, credential status, and appropriate connectivity tests |
| Environment state changed | Readiness, compatibility, capacity, and deployment conflict checks |
| Policy version changed | Re-evaluate every condition required by the new policy |
| Descriptive metadata only | Verify semantic content is unchanged and log audit record |

For example, editing a comment that does not affect runtime content may not require rerunning all unit tests. Yet if the image digest changed, evidence tied to the old artifact is no longer sufficient to deploy the new artifact.

An effective model maps each change category to its dependent check suite. However, whenever exact impact scope cannot be established reliably, rerun a broader test suite or require re-evaluation.

## 12. Time-bound approvals and expiration conditions

Even if contents stay unchanged, an approval can become invalid due to time or policy.

Examples:

- An approval is valid only within a single release window.
- Vulnerability scan reports are accepted only within a freshness period.
- An artifact signing certificate is nearing expiration or was revoked.
- The approver no longer belongs to an authorized group.
- The change window has ended.
- The environment underwent a major change.

Therefore, approval records should carry creation and expiration timestamps. Once an approval expires, the pipeline must return to verification and approval per policy.

Never auto-extend approvals when conditions have changed or the approver no longer holds authority. Extensions must be recorded as deliberate decisions.

## 13. Handling specific change scenarios

### 13.1. Artifact rebuilt after approval

Even if the source commit is unchanged, a fresh build can yield a different digest. The pipeline must treat this as a new artifact, verify provenance and related evidence, and request a new approval if required by policy.

Never swap the digest inside a deployment request while preserving the `approved` status.

### 13.2. Configuration changes while artifact stays unchanged

For example, the image is unchanged, yet a feature flag turns on a new payment flow. The pipeline must inspect the resolved configuration, assess impact, and determine whether integration tests or re-approval are needed.

### 13.3. Secret rotated

Never store secret values in snapshots. Record the secret reference and version metadata. When the version changes, verify the new credential is provisioned to the right workload, remains valid, and works with the target service. Whether re-approval is required depends on security policy and rotation impact.

### 13.4. Environment modified by another pipeline

If another pipeline alters schemas, network policies, or service dependency versions after approval, revalidate environment conditions. If the new state alters risk or compatibility, the old approval may be stale.

### 13.5. Release policy updated

If a new policy introduces an additional required check, prior approval requests must be re-evaluated against the new policy. Records must state explicitly which policy version was applied.

## 14. Audit trail for changes and re-approvals

When an approval is invalidated, preserve history rather than overwriting the old status.

An audit record should capture:

| Field | Contents |
|---|---|
| Approval ID | Identifier of the prior decision |
| Snapshot ID | Target that was approved |
| Current snapshot | Target at revalidation time |
| Changed fields | Which fields or revisions changed |
| Change classification | Artifact, config, environment, policy, or evidence |
| Detection time | Timestamp when drift was detected |
| Validation result | Which checks needed rerunning and their outcomes |
| Approval disposition | Retained validity, stale, revoked, or requires new approval |
| New approval ID | New decision ID if applicable |
| Actor | Person or workload performing the action |
| Deployment ID | Final deployment run |

Never delete an old approval when creating a new one. Retaining history clarifies why the prior decision ceased to apply and who authorized the new state.

Distinguish clearly:

- **Stale:** conditions changed so the old decision no longer applies.
- **Revoked:** an authorized person actively withdrew the decision.
- **Expired:** validity period ended.
- **Superseded:** a newer decision replaced it.

These statuses make reporting and incident investigations far clearer.

## 15. Example pre-deploy validation logic

The following YAML illustrates the general flow. It is not native syntax for GitHub Actions, GitLab CI, or Jenkins:

~~~yaml
release:
  request:
    artifact_digest: required
    source_commit: required
    target_environment: required
    manifest_revision: required
    config_fingerprint: required
    policy_revision: required

  approval:
    bind_to:
      - artifact_digest
      - source_commit
      - target_environment
      - manifest_revision
      - config_fingerprint
      - policy_revision
      - evidence_revision
    require:
      - authorized_approver
      - approval_not_expired

  pre_deploy:
    steps:
      - resolve_current_artifact
      - resolve_current_configuration
      - resolve_current_environment
      - compare_with_approved_snapshot
      - verify_evidence_freshness
      - verify_policy_revision

    on_mismatch:
      - mark_approval_stale
      - record_changed_fields
      - rerun_affected_checks
      - request_new_approval_if_required
      - stop_deployment

    on_match:
      - acquire_environment_lock
      - compare_revision_again
      - deploy_approved_digest
      - verify_running_artifact_and_configuration
      - record_deployment_evidence
~~~

Crucially, the pipeline must re-compare after acquiring coordination rights or locks. If state changes between comparison and deploy execution, conditional updates or additional checks must prevent using the stale approval.

## 16. Common anti-patterns

| Anti-pattern | Risk | How to improve |
|---|---|---|
| Approval stores only an `approved` flag | Unknown what target was actually approved | Bind approvals to snapshots and artifact digests |
| Deploying with mutable tags | Tags may repoint to a different artifact | Resolve to and deploy by digest |
| Checking only source commit | Configuration or images may have changed | Track artifact, manifest, and runtime config together |
| No recheck prior to deploy | TOCTOU can deploy an unapproved state | Revalidate just before execution |
| Changing config post-approval while keeping approval | Runtime behavior differs from what the reviewer saw | Classify changes and invalidate when needed |
| Writing plaintext secrets into snapshots | Credential exposure | Store references and version metadata |
| Rerunning everything for every minor edit | Slow and wasteful pipelines | Map changes to affected check suites |
| Ignoring changes assumed to be trivial | May miss permission or behavioral changes | Use semantic diffs and auditable policies |
| Overwriting old approvals | Loss of decision audit trail | Retain history and link new approvals |
| No locks or conditional deploys | State can shift after the final check | Coordinate and verify revisions atomically |

## 17. Post-approval revalidation checklist

Before deploying an approved release, verify:

- [ ] Approval binds to a specific snapshot.
- [ ] The artifact is identified by an immutable digest or ID.
- [ ] Source commit and provenance match the artifact.
- [ ] Deployment manifests and configs resolve to the exact revision.
- [ ] Runtime config and relevant feature flags still match.
- [ ] Secrets are referenced solely via safe IDs/versions.
- [ ] Environment and dependency state still meet conditions.
- [ ] Tests, scans, and evidence have neither expired nor been revoked.
- [ ] Current policy revision matches the approval.
- [ ] Approval has not expired and the approver still holds authority.
- [ ] Post-approval changes have been classified and handled.
- [ ] Final verification executes immediately prior to deployment.
- [ ] Locks or conditional updates mitigate TOCTOU.
- [ ] Post-deploy verification confirms the actual running artifact and config.
- [ ] Audit trails retain old snapshots, changes, new decisions, and deployment IDs.

## 18. Self-assessment exercise

An API service release was approved for production deployment. The approver reviewed image digest A, manifest revision 12, runtime config revision 31, and scan report S-204. While waiting for the deployment window:

- Another pipeline rebuilt the image from the same commit and produced digest B.
- Operations changed a timeout in runtime config to revision 32.
- Secret manager rotated the payment key from version 7 to version 8.
- Release policy was updated to require a fresher scan.
- Another pipeline updated the production environment's resource quota.

Analyze:

1. Which components definitively invalidate the old approval?
2. Which changes require rerunning technical checks?
3. Does the secret version change require re-approval? What conditions decide this?
4. How do you verify whether image B may replace image A?
5. Is scan S-204 still sufficient evidence for digest B?
6. What checks are needed for runtime config revision 32?
7. How does the new policy affect the prior approval?
8. How do you prevent environment quotas from changing after final revalidation but before deployment?
9. What information must the audit trail retain to explain the final decision?

A solid design never proceeds with deployment simply because an earlier approval holds status `approved`. It compares snapshots, classifies changes, gathers fresh evidence, and requests a new decision whenever scope or risk shifts.

## Conclusion

CI/CD approvals carry meaning only when bound to the exact artifact, configuration, environment, evidence, and policy that were reviewed. If any impactful component changes after approval, the pipeline must detect it, assess impact, and revalidate before deploying.

Use immutable artifact digests and revisions, store approval snapshots, verify evidence freshness, recheck state just before deploy, and prevent concurrent mutations using locks or conditional updates. When an approval becomes stale, preserve history, rerun affected checks, and request fresh approval per policy. This ensures the version actually deployed remains within the scope authorized by accountable decision-makers.
