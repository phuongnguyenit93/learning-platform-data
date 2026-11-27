# Storing Evidence Confirming Deployment Results

A pipeline reporting a successful deploy only shows that the deployment tool finished the steps assigned to it. That does not prove the new version is serving traffic properly, dependencies are working, data has not drifted, or users can complete critical business flows.

After deployment, the system must collect evidence answering specific questions: which artifact was shipped to which environment, who or which workload performed it, how the rollout ended, whether post-deploy checks passed, during which time window, and which data supports that conclusion. Evidence must tie back to a specific release and deployment, have clear provenance, be retained long enough, and remain auditable when an incident occurs.

In CI/CD, post-deployment evidence is part of the release record. It supports decisions to continue rollout, halt, roll back, or mark a release complete; it also helps teams investigate incidents and prove what actually happened.

## 1. What Does Deployment Evidence Prove?

Deployment evidence is data collected from relevant systems confirming what a deployment performed and the outcomes observed afterward.

A record can prove:

- Which identified artifact was deployed.
- Which source revision and build run produced that artifact.
- Which environment, cluster, namespace, or service received the change.
- Which revision or rollout the deployment controller created.
- Which instances ran the new version.
- Which health checks, smoke tests, or synthetic checks ran and their outcomes.
- How key pre- and post-deploy metrics changed.
- Whether migrations or data jobs completed and passed consistency checks.
- Who or which workload executed the action and when.
- Whether the final decision was success, failed, degraded, rolled back, or inconclusive.

Evidence does not necessarily prove every aspect of the system is sound. A passing smoke test only proves the requests and assertions that the test ran during that window. A completed rollout only proves the controller reached its configured rollout state, not that every business flow works.

Therefore, each evidence item should state the scope, source, and limits of its conclusion. Avoid recording "production healthy" if only a single endpoint actually returned HTTP 200.

## 2. Distinguishing Logs, Test Results, and Evidence Records

These datasets are related yet distinct.

| Data type | Purpose | Example |
|---|---|---|
| Execution log | Records tool progress and messages | Deploy command output, controller logs |
| Test result | Records a check and assertions | Smoke test pass, contract test report |
| Telemetry | Observes system state and behavior | Metrics, application logs, distributed traces |
| Evidence record | Links data to a deployment and explains what it proves | Release ID, digest, target, check results, time window, source references |

Logs can be huge and full of noise. A test report may omit which artifact or environment it ran against. Metrics may reflect the system yet lack a link to the deployment just executed.

An evidence record serves as a structured index. It references required logs, reports, metric queries, traces, or state snapshots while recording context and results. You do not need to copy all telemetry into one evidence file; store summaries and links to storage with an appropriate lifecycle.

A single "deploy succeeded" line in a CI log cannot replace an evidence record. It typically lacks artifact digest, target identity, post-deploy observations, and independent verification sources.

## 3. Linking Evidence to the Exact Release and Artifact

The first thing an evidence bundle does is pinpoint exactly what is being attested.

Identifying fields typically needed:

- Service or application name.
- Release ID and version.
- Artifact name and digest.
- Container image repository and digest, if applicable.
- Source repository, commit SHA, and tag.
- Build run ID and pipeline definition revision.
- SBOM or provenance reference, if available.
- Deployment request ID and deployment run ID.

Use immutable digests or identifiers to link artifacts. Tags can move, so recording only an image tag like `latest` or `stable` is insufficient to prove what ran. For JARs or ZIPs, store checksums using an agreed algorithm. For multi-architecture images, record the manifest index digest and per-platform image details when needed.

If the same version is republished with different content, evidence from an earlier deploy can be misinterpreted. Therefore, formal releases should be immutable; new content requires a new version or digest.

## 4. Identifying Target and Deployment State

Evidence must identify the environment the deployment actually modified, not merely the environment an operator intended to deploy to.

Depending on the platform, target identity may include:

- Environment name: development, staging, or production.
- Cloud account, subscription, or project ID.
- Region or zone.
- Cluster endpoint or cluster identity.
- Namespace, tenant, or resource group.
- Service, workload, deployment name.
- Deployment controller revision, rollout ID, or release history entry.
- Resource UID or generation, if provided by the platform.

Context or namespace names can be arbitrary. When strong traceability is required, record reliable API or cloud account identifiers instead of friendly labels alone.

Save both pre- and post-deploy states. For example: old image digest, old deployment generation, previous replica count; followed by new digest, new generation, ready replica count, and rollout completion timestamp. This distinguishes a deployment that actually changed versions from a pipeline rerun that produced no change.

## 5. Identifying Execution Identity and Timestamps

A release record must show who or which workload performed the action. In CI/CD, record the principal or workload identity, role/service account, workflow, job, and run ID.

Useful fields:

- Actor type: human or workload.
- Principal identifier or service account.
- Repository and workflow/pipeline.
- Trigger event, branch, or tag.
- Approval reference and approver, if applicable.
- Deployment job ID.
- Start, completion, and key milestone timestamps.

Use UTC timestamps in a consistent format such as RFC 3339. Runners, clusters, and telemetry backends must keep synchronized clocks to compare events. With large clock skew, event ordering can be misread.

Never store access tokens, private keys, or secret values in evidence. Store only the principal identifier, role, credential issuer, or secret reference needed. When permission audits are required, reference provider audit events.

## 6. Designing an Evidence Bundle

A deployment evidence bundle is the collection of records and data sources tied to a single deployment request. It can be organized into groups:

| Group | Contents |
|---|---|
| Identity | Service, release, artifact, source revision, build run |
| Target | Environment, account, cluster, namespace, workload |
| Execution | Deployment run, controller revision, start/end times, actor |
| Pre-deploy snapshot | Pre-deploy state, current version, health baseline |
| Rollout evidence | Replica/instance readiness, rollout status, events |
| Post-deploy checks | Smoke, synthetic, API, contract, or business checks |
| Observability | Metric window, log queries, trace references, alert state |
| Data evidence | Schema version, migration results, backfill/reconciliation |
| Decision | Pass, fail, degraded, rollback, waiver, or inconclusive |
| Integrity | Digests, signatures, evidence schema version, storage references |

Not every deployment needs every group. A service without a database has no data migration evidence. A static docs deployment may only need artifact identity, CDN verification, and smoke tests. Select evidence by risk, while keeping identity and decision fields consistent.

A good bundle is readable by humans and parseable by automation. Filenames can be friendly, yet internal schemas and identifiers must remain stable.

## 7. Capturing Pre- and Post-Deploy State

Before/after comparison shows what changes the deployment introduced and whether anomalies appeared afterward.

Before deploy, you can record:

- Running artifact digest and version.
- Healthy instance/replica count.
- Baseline error rate, latency, and throughput.
- Active alert and incident states.
- Schema version and migration state.
- Resource capacity or saturation.
- In-flight deployments or recent changes.

After deploy, collect the same types of data over an appropriate observation window:

- Actual workload digest/revision.
- New replicas ready and old instances replaced.
- Error rate, latency, throughput, and saturation.
- Health check and smoke test results.
- Newly triggered alerts.
- Database/schema state and migration results.
- Consumer lag or queue backlog, if applicable.

Baselines require explicit time windows. For instance, compare 15 minutes pre-deploy against 15 minutes after rollout stabilization. Storing only a single average without a time range makes it hard to tell whether data represents the deployment window.

Avoid concluding causation merely because a metric rose after deploy. Traffic, batch schedules, dependency outages, or other infrastructure changes can also contribute. Evidence should record observations and timestamps; root-cause attribution requires further analysis.

## 8. Evidence of Rollout and Actual Running Instances

Deployment controllers may report rollout complete, yet evidence should store enough detail to verify the actual running version.

For Kubernetes, you can collect:

- Deployment name, namespace, and UID.
- Generation and observedGeneration.
- Desired, updated, ready, and available replicas.
- Pod owner references and actual imageIDs.
- New revision or ReplicaSet.
- Rollout-related events.
- Rollout start and completion timestamps.

Illustrative read-only commands:

```bash
kubectl rollout status deployment/orders-api -n production
kubectl get deployment orders-api -n production -o wide
kubectl get pods -n production -l app=orders-api -o wide
```

These commands are examples; label selectors and resource names must match your application. To prove which image digest is running, extract `imageID` from Pod status or the corresponding API, because the `image` field in Pod spec may contain a tag.

Do not dump entire objects if they contain environment variables or sensitive info. Filter required fields, mask sensitive data, and retain resource UID/revision for authorized follow-up lookup.

## 9. Post-Deploy Checks and Recording Results

Evidence can come from multiple check types. Each check needs a name, objective, runner source, target, timestamp, result, and assertion scope.

**Readiness/liveness:** confirms new instances meet the application's health contract. Readiness indicates an instance can accept traffic; liveness helps detect hung processes. Do not substitute liveness for business checks.

**Smoke test:** runs a small request suite confirming core paths work, such as health endpoints, test login, or reading a resource.

**Synthetic check:** simulates user actions from an external vantage point, potentially across multiple regions or network paths.

**Contract/API check:** verifies endpoints, statuses, schemas, and post-deploy integration behavior.

**Business check:** verifies a meaningful business outcome, such as creating a test order and confirming final state in a test system.

Each result must specify whether the test hit the new version. A probe sent to a load balancer can accidentally hit an old instance during a rolling deployment. When verifying per-instance or per-revision, check by appropriate workload identity or deployment label.

## 10. Metrics and SLO Evidence

Metrics show how the system performs over time. After deploy, save queries and observation windows so results can be reproduced.

Commonly used metrics:

- Request rate or throughput.
- Error rate by status class or error type.
- Latency percentiles, such as p50, p95, and p99.
- CPU, memory, disk, and network saturation.
- Queue depth, consumer lag, and retry rate.
- Database connections, query latency, lock waits, and replication lag.
- Cache hit ratio or eviction rate.
- Ready instance count and restart count.

An evidence item can record query reference, metric name, label filters, start/end times, aggregation, and threshold. Do not save only dashboard screenshots, because images are hard to automate and may not reveal which query produced them.

If the deployment has an SLO or error budget policy, record the corresponding evaluation result. For example, error rate in a 10-minute window stayed below threshold and p95 latency did not increase beyond allowed bounds relative to baseline.

Thresholds must be defined before release or in a versioned policy. Never alter thresholds after seeing bad results just to turn a deployment into a pass. If the metrics backend is unreachable, the outcome should be inconclusive rather than pass.

## 11. Evidence from Logs and Distributed Traces

Logs and traces help investigate failures that aggregate metrics cannot explain.

Evidence records can store:

- Log query or saved search identifier.
- Query time range.
- Service, environment, and version filters.
- Correlation IDs or trace IDs from smoke tests.
- Error counts by group or sanitized samples.
- Links to representative traces for failed or slow requests.
- Parser/query version used to aggregate results.

Do not embed millions of log lines into a bundle. Store summaries and references to log systems with proper access controls, retention, and auditing. If logs contain PII, tokens, or sensitive payloads, apply masking and access controls.

For traces, attach deployment version or service version to resource attributes so you can filter requests traversing the new version. Without this attribute, post-deploy traces may mix traffic from multiple revisions and become hard to interpret.

## 12. Migration and Data Evidence

If a deployment includes schema changes or data backfills, evidence must record the data state separately.

Useful fields:

- Database identity or logical target obfuscated per policy.
- Pre- and post-migration schema versions.
- Migration tool and migration run ID.
- List of applied migrations.
- Start/end timestamps.
- Lock waits, duration, and errors.
- Counts of records read, updated, skipped, or failed.
- Final checkpoint and resumable job state.
- Reconciliation results between old and new structures.
- Replication lag or related operational thresholds.

Never record connection strings or database passwords. You can record database aliases and schema identifiers instead of sensitive endpoints.

A migration status of "success" only proves the tool reported completion. When data changes, add count, constraint, checksum, or business invariant checks as appropriate. For example, after a backfill you can verify no valid records are missing target values and total row counts stayed within expectations.

If the migration has not finished while the application is already deployed, evidence must record partial/in-progress status and continuation conditions. Never mark a release complete merely because the application started.

## 13. Defining Observation Windows and Conclusion Criteria

A deployment cannot be confirmed by a single request right after rollout. An observation window may be needed to catch bugs appearing under rising traffic, cold caches, background workers, or batch start times.

Windows may include:

1. **Immediately post-rollout:** check controller, readiness, and smoke tests.
2. **After receiving traffic:** observe error rates, latency, and dependencies.
3. **After one business cycle:** verify critical workers, schedules, or batch jobs.
4. **After a defined stabilization period:** decide whether to continue, halt, or roll back.

Duration depends on the system. Services with continuous traffic may need a window of a few minutes; hourly or daily scheduled jobs may require observing through the next cycle. Never pick an arbitrary duration just to make pipelines finish faster.

Conclusion criteria should be defined upfront:

- Success: all mandatory checks pass and no operational thresholds are breached.
- Degraded: core functionality works, though some metrics or checks miss warning thresholds.
- Failed: functional failures occurred or stop thresholds were breached.
- Rolled back: previous version was restored and post-rollback checks passed.
- Inconclusive: insufficient data or observability sources insufficient to conclude.

If the observation window has not closed, status should remain monitoring/in progress. Do not assign success prematurely only to discover bugs later without updating the release record.

## 14. Evidence for Progressive Delivery and Canaries

For canary or progressive rollouts, evidence must tie results to each phase and traffic cohort.

Example:

- 5% traffic to new revision.
- Observe error rate, latency, and business metrics.
- If thresholds pass, expand to 25%, 50%, then 100%.
- If thresholds breach, halt rollout and roll back or hold traffic per policy.

Each phase should store:

- Revision and digest under test.
- Traffic percentage or instance count.
- Start/end times.
- Metric window and baseline/control cohort.
- Check results and thresholds.
- Decision to promote, pause, or roll back.
- Actor or automation policy making the decision.

Where possible, compare canary against a concurrent control group to reduce noise from overall traffic shifts. Record how cohorts are split and how metrics are computed. If samples are too small, results lack reliability to conclude.

A canary succeeding at 5% traffic does not prove the release is safe at 100%. Evidence must capture every phase and the final state.

## 15. Structuring Evidence Records

Evidence records should include a schema version so consumers can read and upgrade over time. Illustrative JSON example:

```json
{
  "schemaVersion": "1.0",
  "deployment": {
    "id": "deploy-2026-00421",
    "service": "orders-api",
    "environment": "production",
    "target": {
      "account": "prod-account",
      "cluster": "prod-cluster-a",
      "namespace": "orders"
    },
    "actor": {
      "type": "workload",
      "principal": "ci/orders-release"
    },
    "startedAt": "2026-11-18T08:00:00Z",
    "completedAt": "2026-11-18T08:07:30Z"
  },
  "release": {
    "version": "3.8.1",
    "sourceCommit": "a1b2c3d4",
    "buildRun": "build-1842",
    "artifact": {
      "uri": "registry.example.com/orders-api",
      "digest": "sha256:..."
    }
  },
  "rollout": {
    "revision": "42",
    "desiredReplicas": 6,
    "readyReplicas": 6,
    "result": "complete"
  },
  "checks": [
    {
      "name": "smoke-api",
      "result": "pass",
      "startedAt": "2026-11-18T08:08:00Z",
      "completedAt": "2026-11-18T08:08:12Z",
      "evidenceRef": "ci://reports/deploy-2026-00421/smoke"
    }
  ],
  "decision": {
    "status": "success",
    "evaluatedAt": "2026-11-18T08:25:00Z",
    "policyVersion": "production-post-deploy-v3"
  }
}
```

These values are illustrative. Real schemas must specify required fields, data types, status enums, timezones, URI schemes, and how absent values are represented. Never use empty strings for all missing-data states; distinguish `not_applicable`, `not_collected`, `unavailable`, and `failed`.

Evidence records should reference source reports or telemetry using stable URIs. If a source has shorter retention than the evidence record, links can break; align retention policies or snapshot minimal required data.

## 16. Organizing Evidence Bundles and Directory Structure

For file-based storage, bundles can be organized by deployment ID:

```text
evidence/
└── production/
    └── deploy-2026-00421/
        ├── manifest.json
        ├── rollout-summary.json
        ├── checks/
        │   ├── smoke-api.json
        │   └── synthetic-check.json
        ├── telemetry/
        │   ├── metrics-summary.json
        │   └── alert-state.json
        ├── data/
        │   └── migration-summary.json
        ├── references.json
        └── signatures/
            └── manifest.sig
```

This is a logical organization, not a mandatory structure. Some systems store records in a database and reports in object storage; others use a release management or deployment platform as an index.

The manifest should be the single entry point for locating evidence items. Filenames must be stable, containing deployment ID and schema version. Do not rely on mutable display run names.

If a bundle contains multiple files, the manifest must record each file's digest or use a signed manifest to detect file substitution. When appending evidence later, create a new revision or append-only event; never silently modify a signed file without recording history.

## 17. Protecting Evidence Integrity and Provenance

Evidence is valuable when readers trust it came from an identified source and has not been altered without authorization.

Safeguards:

**Digest/checksum:** compute hashes for the manifest and evidence files to detect content changes.

**Signature:** sign the manifest or attestation using a managed workload identity. Consumers verify signatures and signer identity.

**Immutable storage:** use object lock, retention lock, or append-only storage when audit requirements forbid tampering/deletion for a period.

**Audit log:** log who created, read, updated metadata, downloaded, or deleted evidence.

**Source references:** link reports to the originating system, including run IDs, query IDs, or event IDs.

A hash stored alongside a file in the same writable location cannot stop someone able to edit both the file and the hash. For higher assurance, signatures must be protected by keys or workload identities separated from bundle edit permissions; storage needs appropriate auditing and retention.

A signature proves data was signed by an identity and remains unchanged since signing. It does not by itself prove the check was valid or telemetry sources were unmanipulated. You must trust both the evidence-generation pipeline and the data-providing systems.

## 18. Preventing Tampering and Tracking Evidence Updates

A deployment record may need updates when an observation window closes or supplemental results arrive. Distinguish status updates from rewriting history.

You can use an append-only model:

- Create initial record in monitoring state.
- Append `rollout-completed` event.
- Append `smoke-check-passed` event.
- Append `metric-window-evaluated` event.
- Append `decision-success` or `decision-rollback`.
- Each event carries timestamp, actor, source reference, and digest.

The current manifest can summarize the latest state, while event history stays intact to show how state evolved. If an erroneous event must be corrected, append a correction event linking to the prior event and reason; never erase history without a trace.

For object storage without append support, create a new bundle version with a revision number and retain previous versions per retention policy. Explicitly record which revision is current and who created it.

## 19. Access Controls and Data Classification

Evidence can contain internal topology, cluster names, endpoints, approver info, log excerpts, or user data. Do not treat all evidence as public to every developer.

Apply least-privilege access:

- CI publishers can write evidence for their own deployments.
- Release managers can read bundles and gate results.
- On-call responders can read evidence needed for incidents.
- Auditors can read history and audits within scope.
- Cleanup services can delete when policy allows, without altering release record contents.

Apply data classification and masking:

- Never store tokens, passwords, private keys, or raw secrets.
- Remove or mask PII in logs and test reports.
- Avoid storing full request/response bodies unless needed.
- Restrict internal endpoints and detailed topology by role.
- Use secret references or principal IDs instead of credentials.
- Log access and downloads of sensitive data.

If payloads must be kept for investigation, require documented justification, access scope, expiration, and deletion mechanisms. Evidence must suffice for verification without becoming a sensitive-data repository.

## 20. Evidence Retention and Lifecycle

Retention periods should be based on operational needs, release support lifecycles, incident investigations, and audits.

Classification example:

| Evidence type | Purpose | Retention policy |
|---|---|---|
| Deployment manifest and decision | Release traceability | Per support lifecycle and audit policy |
| Smoke/synthetic reports | Functional verification | Per investigation and comparison needs |
| Metric summaries | Before/after comparisons | Retain summaries longer than raw metrics if needed |
| Raw logs/traces | Detailed investigation | Per observability platform retention |
| Migration/backfill reports | Prove data state | Per data governance and audit needs |
| Approval/audit events | Decision traceability | Per governance policy |
| Temporary debug output | Short-term diagnosis | Delete promptly once no longer needed |

Do not retain all raw logs indefinitely. Nor should you delete evidence for releases still deployed or within support windows. Summaries and digests can outlive detailed raw data as long as links and policies are clearly documented.

Cleanup must check deployment and release references before deleting. For incident or audit holds, implement legal/audit hold mechanisms with owners and review dates.

## 21. When Evidence Sources Are Unavailable

Some deployments succeed while the metrics backend, log service, or test endpoint is temporarily unreachable. Pipelines must distinguish system state from evidence-collection availability.

Examples:

- Rollout controller reports complete, yet the metrics backend times out.
- Smoke tests fail to run because the test runner failed to start.
- Synthetic provider lacks data during the observation window.
- Audit API returns errors, preventing actor verification.
- Migration job succeeds yet report upload fails.

Do not automatically mark all such cases as deployment failures, yet do not conclude success if mandatory evidence is missing. Use an `inconclusive` or `evidence-pending` status, and retry collection within policy deadlines.

If mandatory evidence is a precondition for promoting traffic or closing a release, the gate should hold or stop. If evidence is informational only, you may proceed per policy while explicitly logging the unavailable item and reason.

Never fabricate results, reuse reports from a previous deployment, or mark checks passed when they did not run.

## 22. Evidence and Decisions to Continue, Halt, or Roll Back

Evidence is useful only when wired into rule-based decisions.

Example policy rules:

- If rollout does not reach ready replica count within timeout, halt rollout.
- If critical smoke tests fail, do not increase traffic.
- If error rate or latency breaches thresholds during observation, pause or roll back per policy.
- If migration reconciliation fails, do not enable the new read path.
- If mandatory evidence cannot be collected, hold in `inconclusive` state.
- If all mandatory checks pass within the defined window, allow promotion or mark release complete.

Decision records must capture policy version, thresholds, observation windows, evidence items used, and outcome. When humans override automated decisions, record actor, reason, scope, and waiver expiration.

Never let a green dashboard be the sole condition. Store reproducible inputs: metric queries, timestamps, thresholds, and evaluated values.

## 23. Example: Collecting Kubernetes State

A collection step can fetch rollout, Deployment, and Pod status, then extract needed fields into a JSON summary.

Illustrative read-only commands:

```bash
kubectl rollout status deployment/orders-api -n production
kubectl get deployment orders-api -n production -o json
kubectl get pods -n production -l app=orders-api -o json
```

The pipeline can parse JSON output and produce a summary containing:

- Deployment UID, generation, and observedGeneration.
- Desired, updated, ready, and available replicas.
- Pod name, phase, and Ready status per container.
- Actual `imageID` of each container.
- Owner references and ReplicaSet revision.
- Collection timestamp and cluster identity.

Check each command's exit code, handle missing fields, and compute Ready status accurately across all required containers. Do not treat the summary as final proof without comparing `imageID` against the expected digest and running post-deploy checks.

If the API returns errors, do not fabricate a summary with default values like zero or success. Explicitly record the evidence item as unavailable or failed along with the cause.

## 24. Example Pipeline for Collecting and Storing Evidence

A conceptual pipeline can be divided into stages:

```yaml
jobs:
  deploy:
    steps:
      - deploy artifact by immutable digest
      - capture deployment revision and target identity

  verify:
    needs: [deploy]
    steps:
      - wait for rollout completion
      - run smoke and synthetic checks
      - collect metric window and alert state
      - collect migration and data verification result

  assemble-evidence:
    needs: [verify]
    steps:
      - create deployment evidence manifest
      - calculate digest for each evidence file
      - sign manifest with workload identity
      - upload bundle to controlled evidence storage

  decide:
    needs: [assemble-evidence]
    steps:
      - evaluate required evidence against release policy
      - record success, degraded, failed or inconclusive
      - promote, pause or rollback according to policy
```

Step names are conceptual and should be replaced with actions from your actual CI platform and observability stack. If deploy and verify jobs run on separate runners, pass deployment ID and artifact digest through controlled outputs or release records. Never pass secrets or access tokens in outputs.

Uploading evidence should be a verified step. If storage fails, the final decision must follow policy: keep release pending, retry upload, or mark inconclusive. Never report a release complete if mandatory evidence has not been stored.

## 25. Checking Evidence Quality

Evidence should be validated like any other artifact. Before marking a bundle complete, verify:

- Schema version is supported.
- Deployment ID and release ID are valid.
- Artifact digest format is valid.
- Target identity matches the deployment request.
- Timestamps include timezone and follow logical order.
- Check results use defined enums.
- Evidence references are accessible by authorized consumers.
- File digests match actual contents.
- Signatures are valid if required by policy.
- No out-of-scope secrets or sensitive data are present.
- Mandatory checks are neither missing nor left in an unresolved `unavailable` state.

You can validate manifests using JSON Schema or an equivalent schema validator. Schemas should be versioned with compatibility rules when adding fields. Older consumers should safely ignore extension fields or undergo controlled upgrades.

Never allow a bundle missing an artifact digest or target identity to be marked complete merely because the JSON is syntactically valid. Syntactic validation and semantic/business validation are two separate layers.

## 26. Common Anti-Patterns

| Poor practice | Consequence | How to improve |
|---|---|---|
| Saving only a "deploy succeeded" line | Unknown artifact, target, and actual outcome | Evidence manifest tied to release and digest |
| Saving only raw logs | Hard to query, lacks conclusions, may contain secrets | Store structured summaries and log references |
| Checking only a single health endpoint | Does not prove business flows | Combine smoke, synthetic, and business checks |
| Using mutable tags to identify images | Running contents cannot be verified | Record actual runtime digests |
| Omitting target identity | Risk of confusing environments or clusters | Record account, cluster, namespace, and resource UID |
| Recording timestamps without timezones | Hard to order events across systems | Use UTC/RFC 3339 and synchronize clocks |
| Screenshotting dashboards without queries | Evaluations cannot be reproduced | Store queries, filters, windows, and thresholds |
| Recording success despite missing data | Decisions lack grounding | Use `inconclusive`/`evidence-pending` |
| Editing signed bundles without revisions | Loss of history and integrity | Append-only events or bundle revisions |
| Storing raw logs with secrets/PII | Creates a data-leak repository | Masking, access controls, and retention |
| Keeping raw telemetry indefinitely | Rising storage costs and data risk | Tiered retention by type, keep summaries/digests appropriately |
| Not linking migration evidence | Unclear where data state stands | Record schema version, run ID, and reconciliation |

## 27. Roadmap for Building Evidence in CI/CD

You can roll this out incrementally:

1. **Standardize deployment identity:** generate deployment ID, release ID, and artifact digest used throughout the pipeline.
2. **Define evidence schema:** specify required fields, statuses, and URI references.
3. **Select data sources:** deployment controller, test runners, metrics, logs, traces, migration tools, and audit APIs.
4. **Capture baseline:** record pre-deploy state and start timestamp.
5. **Collect rollout evidence:** save revision, instance readiness, image digest, and events.
6. **Run post-deploy checks:** risk-appropriate smoke, synthetic, API, and business checks.
7. **Collect telemetry:** store queries, windows, thresholds, and summaries.
8. **Aggregate data evidence:** schema, backfills, and reconciliation if applicable.
9. **Generate and sign manifest:** compute digests, verify provenance, and store bundle.
10. **Evaluate policy:** decide success, degraded, failed, or inconclusive.
11. **Configure retention and access:** protect data, auditing, and cleanup.
12. **Rehearse investigations:** pick an old deployment, retrieve its bundle, and reproduce the conclusion.

Start with a service that deploys frequently. Choose a small evidence set sufficient to identify artifact, target, rollout, and smoke results. Once the workflow stabilizes, expand to metrics, traces, migrations, and signatures.

## 28. Measuring Evidence System Quality

You can track:

- Percentage of deployments with complete evidence bundles.
- Percentage of bundles containing artifact digest and target identity.
- Percentage of mandatory checks with results and source references.
- Time from rollout completion to evidence decision.
- Failure rate of evidence uploads/signatures/validations.
- Percentage of deployments marked `inconclusive` due to missing data sources.
- Time required to retrieve evidence for a past release.
- Percentage of report/telemetry links still accessible within the retention window.
- Incidents needing evidence where bundles lacked sufficient data.
- Detected integrity mismatches or unauthorized access attempts.

Do not optimize bundle completion rate by cutting mandatory checks. The goal is for evidence to reflect true risk and support grounded release decisions.

## 29. Post-Deployment Evidence Checklist

- [ ] Unique deployment ID and release ID exist.
- [ ] Artifact version and digest are recorded.
- [ ] Source commit and build run are linked.
- [ ] Target identity reflects the actual environment.
- [ ] Actor/workload identity and deployment run are recorded.
- [ ] Pre- and post-deploy states are captured.
- [ ] Rollout revision and instance readiness have evidence.
- [ ] Smoke/synthetic/API/business checks have results and timestamps.
- [ ] Metric evidence includes queries, filters, thresholds, and time windows.
- [ ] Log/trace references include correlation IDs and appropriate masking.
- [ ] Migration/backfill evidence is linked if applicable.
- [ ] Observation windows and success/fail criteria are defined.
- [ ] Missing data is represented as `unavailable`/`inconclusive`.
- [ ] Manifest includes a schema version and is validated.
- [ ] Digests/signatures protect integrity per policy.
- [ ] Evidence storage enforces access controls, auditing, and retention.
- [ ] No secrets or unnecessary PII are stored.
- [ ] Bundles can be retrieved and conclusions reproduced for past releases.

## Conclusion

Storing evidence confirming deployment results turns a deployment into a traceable, auditable event. Evidence must link release, artifact digest, source revision, target identity, actor, rollout state, and post-deploy validation results. It should combine structured summaries with references to test reports, telemetry, migration results, and audit events.

A strong record states which data was observed, in which window, from which source, and the limits of the conclusion. When manifests are validated, contents are protected with digests or signatures, and access and retention are governed, teams can decide to promote, pause, or roll back based on evidence and investigate incidents without relying on memory or a single success log line.
