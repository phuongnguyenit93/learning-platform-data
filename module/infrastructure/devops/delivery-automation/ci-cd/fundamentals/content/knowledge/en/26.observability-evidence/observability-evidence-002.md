# Collecting Test Reports, Analysis Results, and Deployment Information

## Learning Objectives

After this lesson, learners can:

- Explain the role of evidence in deciding whether a change is eligible for release.
- Distinguish between test reports, analysis results, operational telemetry, and deployment records.
- Identify the data that needs to be collected from each job and each pipeline stage.
- Select appropriate report formats and normalize results across multiple tools.
- Link reports to commits, workflow runs, artifact digests, releases, and target environments.
- Design a workflow to aggregate evidence from parallel jobs, even when a job fails or fails to produce a report.
- Protect the integrity, provenance, accessibility, and retention period of evidence.
- Use evidence bundles to support quality gates, release approvals, incident investigations, and audits.

## 1. Why Do Pipelines Need to Collect Evidence?

A pipeline may finish with a green status, yet looking at the overall status alone is not enough to understand what was verified and which artifact was produced.

For example, a run might report success even when:

- A test group was skipped due to misconfiguration.
- The coverage report was not uploaded.
- A security analysis tool did not run because it timed out.
- The artifact was built from a different commit than the one that was tested.
- Deployment succeeded on a subset of instances without completing the rollout.
- There is no information on the actual configuration applied.

Evidence helps answer concrete questions:

- Which source code was tested?
- Which test suites ran and what were the results?
- How many tests passed, failed, were skipped, or errored?
- What scope did security and quality analysis cover?
- Which artifact was produced from that build?
- Is the artifact the exact same one that was tested?
- Who or which workload performed the deployment?
- Which environment did the deployment change, and with what configuration?
- After deployment, did the system verify the version and health?

In CI/CD, **evidence** is structured data or auditable documentation tied to a specific subject and a specific activity. Evidence must indicate who or what tool produced it, when it was generated, which commit/artifact/environment it applies to, and what the result means.

Evidence is not just for dashboards. It is the input to quality gates, release decisions, change traceability, incident investigations, and demonstrating policy compliance.

## 2. Distinguishing Reports, Telemetry, and Deployment Records

These data types are often stored near each other but serve different purposes.

| Data type | Question answered | Example |
|---|---|---|
| Test report | Which tests ran and what were the outcomes? | JUnit XML, TRX, test summary |
| Coverage report | Which code was executed within the test scope? | JaCoCo XML, Cobertura, LCOV |
| Analysis report | What issues did tools detect in source, dependencies, or images? | SARIF, SAST, DAST, dependency scan |
| Build evidence | How was the artifact created and from what inputs? | Build metadata, provenance, SBOM |
| Deployment record | Which artifact and configuration were delivered to which environment? | Release manifest, deployment ID, config revision |
| Runtime telemetry | How does the system behave after deployment? | Metrics, logs, traces, alerts |
| Approval/audit record | Who authorized or performed which action? | Approval event, audit log, change record |

**Reports** typically describe the result of a scoped execution. **Telemetry** reflects system state or behavior over time. A **deployment record** describes a change applied to an environment.

A dashboard may aggregate all three, but a dashboard screenshot should never be treated as the sole evidence. Raw data or structured exports must be stored together with metadata for traceability.

## 3. Evidence Model: Subject, Activity, Result, and Producer

Useful evidence must be tied to a specific subject and an identifiable activity.

A conceptual model can be used:

- **Subject:** the object inspected or changed, such as a commit, artifact digest, image, or environment.
- **Activity:** the action performed, such as unit test, SAST scan, build, signing, or deploy.
- **Producer:** the person, runner, tool, or workload identity that generated the result.
- **Timestamp:** start/end time or report generation time.
- **Context:** workflow revision, run ID, parameters, tool version, and inspection scope.
- **Result:** pass/fail, findings, metrics, deployment status, or verification outcome.
- **Integrity reference:** checksum, signature, or storage ID to detect tampering.

~~~mermaid
flowchart LR
    S["Subject: commit / artifact / environment"] --> A["Activity: test / scan / build / deploy"]
    P["Producer: tool / runner / identity"] --> A
    C["Context: run ID / tool version / config"] --> A
    A --> R["Result: report / findings / status"]
    R --> I["Integrity: digest / signature / storage ID"]
    I --> G["Quality gate / approval / audit"]
~~~

For instance, a test report file might state that 120 tests passed. However, without knowing which commit, run, test suite, and tool version produced the report, its traceability value is severely limited.

Avoid reports with generic filenames like test-results.xml that get overwritten across runs. Every report must have an identifier or storage path tied to a specific pipeline run and attempt.

## 4. Collecting Test Reports

Test reports show which tests ran, their results, and failure details. They are a primary source of evidence for quality gates.

Common test categories:

- Unit tests.
- Component tests.
- Integration tests.
- Contract tests.
- API tests.
- End-to-end tests.
- Smoke tests.
- Performance/load tests.
- Compatibility tests.
- Migration or data validation tests.

A test report should contain or link to:

- Project/module name and test suite.
- Test cases or test groups.
- Total number of tests.
- Counts of passed, failed, skipped, aborted, and errored tests.
- Execution duration.
- Appropriate failure messages and stack traces.
- Commit SHA and pipeline run ID.
- Runtime, OS, browser, or test environment.
- Test framework version.
- Links to detailed logs or related artifacts.

Common formats:

| Format | Common purpose | Notes |
|---|---|---|
| JUnit XML | Test reports from many frameworks | Supported by most CI servers |
| TRX | Test results in the Microsoft ecosystem | Can contain test results and diagnostics |
| NUnit XML | Results from NUnit | Requires a compatible parser or publisher |
| Allure results/report | Aggregating test results and history | Both raw results and rendered report should be saved |
| Tool-specific JSON | Structured framework output | Should have a clear schema/version |

Supported formats depend on the CI tool and test framework. If a pipeline uses multiple frameworks, you can retain the raw reports and map them into a shared aggregation model.

Do not store only pass counts in console logs. Logs can be truncated, change format, or be hard to query. Export reports as structured files and publish them as pipeline artifacts.

## 5. Collecting Coverage and Test Quality Signals

Coverage reports provide additional information about which code paths were executed during testing. Common types include:

- Line coverage.
- Statement coverage.
- Branch coverage.
- Function/method coverage.
- Module or package coverage.

Formats may include JaCoCo XML, Cobertura XML, or LCOV. Some platforms support proprietary formats.

Coverage should be linked to:

- Commit SHA.
- Build/test run.
- Source revision.
- Module or package.
- Tool version.
- Included and excluded file scope.

Do not compare two coverage figures if the source scope differs. For example, one run excludes the integration module while another includes it; the percentage may shift without reflecting actual test quality.

High coverage does not guarantee good tests. A line of code may be executed without assertions verifying its behavior. Therefore, coverage is a signal that should be combined with test results, mutation testing, or reviews as needed.

When aggregating coverage across multiple modules, avoid misleadingly averaging percentages. Sum the covered lines/branches and total coverable lines/branches under consistent rules, then compute the ratio over the totals.

## 6. Collecting Source Code and Security Analysis Results

A pipeline may run several analysis tools:

- Static Application Security Testing (SAST).
- Software Composition Analysis (SCA) or dependency scanning.
- Secret scanning.
- License compliance.
- IaC scanning.
- Container/image scanning.
- Dynamic Application Security Testing (DAST).
- API security testing.
- Code quality and maintainability analysis.

An analysis result must indicate:

- Tool and version.
- Analysis type.
- Scanned source, artifact, or image digest.
- Commit SHA and file scope.
- Scan timestamp.
- Rule set, policy, or vulnerability database version if applicable.
- Finding ID, rule ID, and location.
- Severity, confidence, or risk rating.
- Status: new, existing, suppressed, accepted, or resolved.
- Reference to exception/waiver if any.

SARIF (Static Analysis Results Interchange Format) is a static analysis exchange format supported by many tools. It can carry tool, rule, result, and source location metadata. However, not every scanner emits SARIF or supports all fields.

For dependency scans, also store the dependency manifest/lockfile or related SBOM to know the exact components evaluated. For image scans, bind results to the image digest rather than relying only on a tag.

A scan report must clearly distinguish:

- Zero findings detected.
- Scan completed with findings.
- Scan did not run.
- Scan ran but errored.
- Scan had restricted scope.
- Scan results are stale or no longer match the current artifact.

Never interpret “no report” as “no vulnerabilities.”

## 7. Collecting Build Information and Artifact Provenance

Once tests and analyses pass, the pipeline produces an artifact. Build evidence must enable tracing the artifact back to its source and build process.

Information to collect:

- Repository and source commit.
- Branch/tag or release reference.
- Workflow definition revision.
- Pipeline run ID and attempt.
- Builder/runner identity.
- Build tool and compiler version.
- Dependency lockfile or dependency graph.
- Build parameters and target platform.
- Build timestamp.
- Artifact name, version, and digest.
- SBOM and provenance if required by policy.
- Signatures or attestations if applicable.

Artifacts should be identified by an immutable digest. Tags are convenient for humans, but insufficient to prove content if a tag can be overwritten.

Distinguish two file categories:

- **Deployable artifact:** JAR, package, binary, container image, or bundle that gets deployed.
- **Evidence artifact:** test report, scan report, coverage, build log, SBOM, provenance, and deployment record.

Do not bundle evidence into the runtime artifact in a way that alters the deployable content. Both can be referenced in the same release record or evidence bundle, but their digests and roles must remain distinct.

## 8. Collecting Deployment Information

A deployment record states which specific artifact was delivered to which environment, with what configuration and strategy.

Recommended fields:

| Field | Meaning |
|---|---|
| Release ID | Release identifier across environments |
| Deployment ID | Identifier for a single deployment execution |
| Artifact digest | Actual content deployed |
| Source commit | Commit that produced the artifact |
| Workflow/template revision | Pipeline logic that executed |
| Environment ID | Target environment |
| Config revision/fingerprint | Resolved and applied configuration |
| Migration version | Associated schema/data migration |
| Strategy | Rolling, canary, blue-green, or recreate |
| Actor/workload identity | Who or which workload executed it |
| Approval/change reference | Associated decision and change record |
| Start/end time | Deployment time window |
| Result | Success, failed, partial, cancelled, or rolled back |
| Verification | Results of health, smoke tests, and runtime checks |

A deployment command returning exit code 0 is not enough to prove the system is running the right artifact. Actual state must be verified from the target environment:

- Running image digest or package version.
- Replicas/instances reaching the desired state.
- Applied config revision.
- Routing or traffic shift completion.
- Passing health and smoke tests.
- No unintended old instances remaining from rollout.
- Release ID recorded in telemetry.

If a deployment partially fails, the record must reflect the partial state and modified resources. Do not force every result into binary success/fail if that hides the actual state.

## 9. Linking Evidence with Stable Identifiers

When tests, scans, builds, and deployments run across multiple jobs or systems, a set of identifiers is needed to connect the evidence.

Useful identifiers:

- Repository ID or canonical URL.
- Commit SHA.
- Workflow revision.
- Pipeline run ID and attempt number.
- Artifact digest.
- SBOM digest.
- Provenance/attestation ID.
- Release ID.
- Deployment ID.
- Environment ID.
- Config revision.
- Correlation ID or trace ID for runtime activities.

A typical linkage chain:

~~~text
Repository + Commit SHA
        |
        v
Workflow Revision + Run ID
        |
        +---- Test Reports
        |
        +---- Analysis Reports
        |
        v
Build Artifact Digest
        |
        +---- SBOM / Provenance / Signature
        |
        v
Release ID
        |
        v
Deployment ID + Environment ID + Config Revision
        |
        v
Post-deploy Verification + Runtime Evidence
~~~

Do not link solely by branch name or version label. Branches can move and tags can be overwritten. Commit SHAs, digests, and per-run IDs are better identifiers for traceability.

If multiple pipelines build artifacts or a downstream pipeline deploys an artifact, pass the artifact digest and release ID through structured inputs/outputs rather than querying for the latest tag.

## 10. Aggregating Evidence from Parallel Jobs

A pipeline can run multiple testing and analysis jobs in parallel. Each job generates one or more report artifacts.

Example:

~~~mermaid
flowchart TD
    A["Source commit"] --> B["Pipeline run"]
    B --> C["Unit tests"]
    B --> D["Integration tests"]
    B --> E["Coverage"]
    B --> F["SAST / dependency scan"]
    C --> G["Evidence collector"]
    D --> G
    E --> G
    F --> G
    G --> H["Normalize and validate"]
    H --> I["Quality gate"]
    I --> J["Build / release evidence bundle"]
~~~

The evidence collector needs to know which reports are mandatory. If a job does not produce a report, the collector must distinguish the cause:

- Job did not run due to a dependency.
- Job was skipped by policy.
- Job failed before exporting the report.
- Report upload failed.
- Report is invalid or uses an unsupported schema.
- Report is missing due to misconfiguration.

For mandatory gates, missing evidence should be treated as failed or unable to evaluate, per policy. Do not silently ignore a missing report just because the pipeline can technically continue.

When jobs run on separate runners, do not assume files live in the same workspace. Each job must upload its reports using CI artifact storage or a shared repository, and the collector downloads them by run ID and job ID.

## 11. Normalizing Data While Preserving Raw Reports

Different tools use different formats, severity names, and calculation methods. An aggregation system can construct a canonical data model for comparison and policy enforcement.

Example canonical test statuses:

- passed
- failed
- skipped
- error
- cancelled
- not_run
- unavailable

Example canonical severities for findings:

- critical
- high
- medium
- low
- info
- unknown

A versioned mapping from tool formats to the shared model is needed. Do not squeeze every tool-specific field into an overly narrow schema that drops critical data.

Store all of the following:

1. Original raw report generated by the tool.
2. Parsed/normalized representation.
3. Metadata about the parser and schema version.
4. Parsing errors or warnings.
5. Links to detailed logs.

If the parser encounters an unknown field or a new report version, explicitly log what could not be processed. Do not silently discard findings.

## 12. Validating Report Completeness and Validity

The mere existence of a file does not mean the report is valid.

The collector should verify:

- File exists and is non-empty.
- Format is parseable.
- Schema/version is supported.
- Report belongs to the correct repository, commit, and run.
- Report timestamp aligns with the current run.
- Tool name and tool version are present.
- Test/scan scope complies with policy.
- Artifact digest matches the subject being evaluated.
- Summary totals match detailed entries.
- No duplicate or overwritten reports exist.

For example, a report from a previous run might remain in the workspace if a job reuses a runner. If the collector searches only by filename, it may accidentally read a stale report. Use clean workspaces or artifact paths tagged with run ID and attempt.

Clearly define report states:

| State | Meaning | Handling |
|---|---|---|
| Valid | Report is valid and matches context | Include in aggregation |
| Missing | Mandatory report not found | Block or mark unable to evaluate |
| Invalid | File exists but fails parsing/schema check | Block per policy and record reason |
| Stale | Report belongs to an old commit/run/artifact | Do not use for current release |
| Partial | Only part of the scope was checked | Evaluate per policy, do not treat as full pass |
| Unavailable | Tool or service could not provide results | Fail closed or require approved exception |
| Optional skipped | Non-mandatory step legitimately skipped | Record reason, does not affect mandatory gate |

## 13. Quality Gates Must Read Semantic Evidence

A quality gate should not only check whether a job has a success status. It needs to inspect the actual results and determine whether they satisfy policy.

For example:

- All mandatory tests ran and have zero failures.
- No unresolved critical findings remain.
- Coverage did not drop below the agreed threshold.
- Dependency scan data meets freshness requirements.
- Artifact digest has valid provenance.
- Approval is bound to the exact release and environment.
- Deployment verification confirms the expected artifact is running.

A gate should record:

- Policy ID and policy version.
- Input evidence IDs.
- Evaluation result of each condition.
- Final decision: pass, fail, blocked, or exception.
- Rationale and related findings.
- Actor who approved an exception, if any.
- Evaluation timestamp.

Do not hard-code thresholds across multiple disparate jobs. Manage policies centrally or via versioned configuration, and record the policy version applied.

Exceptions must specify scope, justification, owner, and expiration. A waiver for a single finding must not turn into disabling the entire scanner on future runs.

## 14. Binding Evidence to Artifacts and Releases

An evidence bundle is a collection of reports and metadata associated with an artifact or release.

A logical structure might look like:

~~~text
release-evidence/
├── manifest.json
├── source/
│   └── revision.json
├── tests/
│   ├── junit-unit.xml
│   ├── junit-integration.xml
│   └── coverage.xml
├── analysis/
│   ├── sast.sarif
│   ├── dependency-report.json
│   ├── image-scan.json
│   └── sbom.json
├── build/
│   ├── build-metadata.json
│   └── provenance.json
├── deployment/
│   ├── staging-deployment.json
│   └── production-deployment.json
└── verification/
    ├── smoke-test.json
    └── post-deploy-health.json
~~~

The manifest can contain:

- Release ID.
- Repository and commit SHA.
- Workflow revision and run ID.
- Artifact name/version/digest.
- List of reports with their digests.
- Tool and schema versions.
- Policy evaluation ID.
- Signature or attestation reference if used.

An evidence bundle does not have to be a single ZIP file. It can be a release record in a release management system, a set of artifacts in CI storage, or objects in an evidence store. What matters is that the manifest links them stably and verifiably.

Do not modify raw reports after they have been used for a release decision. If additional information is needed, create a new version and keep a link to the prior version.

## 15. Evidence Integrity and Provenance

Evidence is only valuable when you can trust it came from the right activity and was not altered without authorization.

Measures include:

- Storing digests for each report.
- Restricting write/delete permissions on the evidence store.
- Recording producer identity and run context.
- Using immutable or retention-locked storage for critical evidence.
- Signing manifests or attestations when high assurance is required.
- Keeping audit logs for uploads, downloads, replacements, and deletions.
- Separating permissions to generate reports from permissions to modify policies or approve releases.
- Verifying signatures and trust roots before relying on evidence.

Checksums detect content tampering against a stored digest, but do not prove the report creator is trustworthy. Signatures verify the signer identity and integrity, though you still must trust the signer, builder, and key issuance process.

Do not allow jobs executing untrusted code to self-assert evidence that a production pipeline treats as authoritative. Control identities and provenance sources.

## 16. Collecting Post-Deployment Evidence

After deployment, the pipeline needs to gather evidence demonstrating the live environment received the exact release and operates as required.

Common checks:

- Running artifact digest.
- Exposed release ID or version.
- Applied config revision.
- Healthy replica/instance count.
- Readiness and startup status.
- Smoke tests or critical user journeys.
- Error rate and latency within the observation window.
- Queue lag, restart count, or dependency failures.
- Traffic shift/canary results if applicable.
- Rollback or recovery outcome if the rollout failed.

An observation window appropriate to the service type is necessary. An immediate post-deploy health check might miss issues that only surface under load or when background jobs run.

If metrics lack sufficient data, the status should be pending/insufficient evidence rather than automatically passing. Define maximum wait times and actions when no conclusion can be reached.

Deployment evidence should store both desired state and observed state. For instance, the pipeline requested image digest X while the cluster is running digest Y; this is drift that must be recorded and addressed.

## 17. Storage, Retention, and Accessibility

Evidence varies in value depending on time and purpose.

Categories may include:

- Temporary raw logs and reports for debugging.
- Release-bound test/scan reports.
- Artifact provenance and SBOMs.
- Approval and deployment audits.
- Evidence for compliance or incident investigation.

Retention policies need to define:

- Evidence type.
- Retention period.
- Storage location.
- Authorized readers/roles.
- Who can delete or replace items.
- Handling of legal holds or incident holds.
- Encryption level and data partitioning.

Do not store all logs indefinitely. That increases cost and the risk of retaining sensitive data. Conversely, do not delete deployment evidence too early if a running version still needs traceability.

Retention should be grounded in operational, contractual, legal, and organizational policy requirements. No single retention duration fits every report type.

## 18. Protecting Sensitive Data in Reports

Test reports, logs, and scan outputs can sometimes contain:

- Emails, phone numbers, or sample customer data.
- Printed access tokens or secrets.
- Internal URLs and hostnames.
- SQL statements or request payloads.
- File paths and system metadata.
- Undisclosed vulnerability details.

Required practices:

- Use synthetic or anonymized test data.
- Mask secrets before logging.
- Never upload environment files or credentials into evidence bundles.
- Enforce role-based access control on security and deployment reports.
- Encrypt data in transit and at rest.
- Establish a revoke/rotate secret procedure if exposure is detected.
- Define retention limits for sensitive data.
- Review report contents before publishing externally.

Secret masking does not guarantee every representation is covered. The safest approach is keeping secrets out of command outputs and test fixtures altogether.

## 19. Example Evidence Collection Pipeline

The following YAML illustrates the general flow:

~~~yaml
pipeline:
  context:
    source_commit: required
    run_id: required
    workflow_revision: required

  jobs:
    unit_tests:
      output:
        - junit-unit.xml

    integration_tests:
      output:
        - junit-integration.xml

    coverage:
      output:
        - coverage.xml

    security_analysis:
      output:
        - sast.sarif
        - dependency-report.json

    build:
      needs:
        - unit_tests
        - integration_tests
        - security_analysis
      output:
        - artifact_digest
        - build-metadata.json
        - provenance.json

    collect_evidence:
      needs:
        - unit_tests
        - integration_tests
        - coverage
        - security_analysis
        - build
      steps:
        - download_reports_by_run_id
        - validate_report_schema_and_context
        - normalize_results
        - calculate_report_digests
        - create_evidence_manifest
        - publish_evidence_bundle

    quality_gate:
      needs:
        - collect_evidence
      input:
        - evidence_manifest
        - policy_revision
      output:
        - gate_decision

    deploy:
      needs:
        - quality_gate
      condition: gate_decision == "pass"
      output:
        - deployment_record.json
        - post_deploy_verification.json
~~~

In practice, if builds can run in parallel with tests, the DAG may allow that. The condition is that the artifact is built from the same source revision and the quality gate waits for all mandatory evidence before permitting deployment.

The collector should not merely download files by static names. It must query by run ID, job ID, and attempt, then verify commit/artifact context.

## 20. Report States to Distinguish

A pipeline must clearly separate individual tool results from aggregated gate outcomes.

Example:

| Report status | Gate interpretation |
|---|---|
| Completed, no findings | Can pass if policy requirements are met |
| Completed, findings present | Evaluate severity and policy |
| Failed | Fails gate or requires investigation |
| Skipped by approved policy | Record scoped exception |
| Skipped unexpectedly | Blocked or failed |
| Missing | Unable to evaluate |
| Invalid schema | Unable to evaluate |
| Stale | Must not be used for current release |
| Partial scope | Accepted only if policy allows |
| Tool unavailable | Blocked or requires approved exception |

Do not collapse every non-success state into a single label if doing so loses information. For example, a test failure differs from a scanner failing to start; both may block a release, but they require different remediation.

## 21. Common Anti-Patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Checking only green pipeline status | Unknown which tests/scans actually ran | Publish structured reports |
| Saving only console logs | Hard to parse and may be truncated | Store raw reports and metadata |
| Using shared filenames across runs | Accidentally reading stale results | Scope paths with run ID and attempt |
| Treating missing reports as pass | Bypasses mandatory checks | Distinguish missing/unavailable and fail gate |
| Storing only coverage percentage | Unknown measurement scope | Store raw coverage and source revision |
| Scan report not tied to artifact digest | Results may belong to another image | Bind digest and scan context |
| Linking releases with mutable tags | Unstable traceability | Use commit SHA and artifact digest |
| Editing reports after release | Loses decision history | Write a new version, preserve the old one |
| Dashboard as sole evidence | Cannot reproduce or audit | Store structured evidence records |
| Retaining logs indefinitely | Cost and sensitive data exposure | Apply retention by evidence type |
| Uploading reports containing secrets | Credential leak | Mask, inspect, and restrict access |
| Treating deploy command success as deploy success | Stale instances or partial rollout may remain | Verify live target state |

## 22. Evidence Collection and Management Checklist

Before putting a pipeline into operation, confirm:

- [ ] Required reports are listed per pipeline and release type.
- [ ] Every report is bound to repository, commit, run ID, and attempt.
- [ ] Test reports include pass/fail/skipped/error counts and failure details.
- [ ] Coverage reports include source revision and measurement scope.
- [ ] Analysis reports include tool/version, scope, severity, and finding IDs.
- [ ] Scan reports are bound to the exact source or artifact digest.
- [ ] Build evidence includes builder, workflow revision, parameters, and artifact digest.
- [ ] Deployment records include release ID, environment, config revision, and actor.
- [ ] Post-deploy evidence verifies the actual running artifact and state.
- [ ] Parallel jobs upload reports individually; collector aggregates by run context.
- [ ] Report schemas and context are validated before the quality gate.
- [ ] Missing, invalid, stale, partial, and unavailable states are distinguished.
- [ ] Raw reports are retained alongside normalized versions.
- [ ] Evidence manifest links reports by ID and digest.
- [ ] Upload, read, modify, and delete permissions are separated.
- [ ] Retention and privacy policies are enforced.
- [ ] Approvals, exceptions, and evidence changes are audited.
- [ ] Production deployments can be traced back to commit and test/scan evidence.

## 23. Self-Assessment Exercise

A payment service pipeline has the following jobs:

- Unit tests running on Java 21 and outputting JUnit XML.
- Integration tests running against a database container and outputting JUnit XML.
- Coverage job outputting JaCoCo XML.
- SAST job outputting SARIF.
- Image scan job outputting a JSON report.
- Build job building a container image and pushing the latest tag.
- Deploy job deploying the latest tag to staging.
- A collector that searches for report files solely by filename in the runner's workspace.

Recent runs exhibited the following issues:

- The integration test report was occasionally a file left over from a previous run.
- The image scan report did not specify the digest of the scanned image.
- The SAST job timed out, yet the pipeline still passed.
- Staging occasionally ran a different image than the one built in the same run.
- The deployment record only saved the timestamp and success status.

Propose a redesigned architecture:

1. Which reports and metadata must each job publish?
2. How does the collector retrieve the exact reports for the current run and attempt?
3. Which fields must be validated before normalizing reports?
4. How do you distinguish a scanner timeout from a completed scan with zero findings?
5. Which artifact digest must the image scan be bound to?
6. Why is the latest tag insufficient to identify the deployed image?
7. What release, config, and environment metadata must be added to the deployment record?
8. What manifest and digests should the evidence bundle contain?
9. How should read permissions for security reports and retention be structured?
10. How should the quality gate handle missing, stale, and invalid reports?

A solid design must enable tracing from a staging deployment back to the image digest, source commit, test reports, scan results, and policy decision that authorized the release.

## Conclusion

Collecting test reports, analysis results, and deployment information enables pipelines to produce auditable evidence rather than simply returning a green/red status. Every report must be tied to the right commit, run, artifact, or environment, and include its producer, timestamp, scope, and a valid format.

Publish reports from each job, aggregate them by run context, normalize while keeping raw originals, validate completeness, and link everything with an evidence manifest. After deployment, record the artifact digest, config revision, environment, actor, and actual verification outcomes. When evidence has proper integrity, retention, and access controls, teams can make consistent release decisions, investigate incidents, and prove exactly what was tested and deployed.
