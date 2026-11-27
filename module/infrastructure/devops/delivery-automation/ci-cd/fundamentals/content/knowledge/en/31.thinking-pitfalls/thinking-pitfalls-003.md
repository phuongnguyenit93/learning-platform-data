# Assuming a Successful Build Proves Release Readiness

A pipeline reporting a successful build usually means the source code has passed a set of steps such as resolving dependencies, compiling, and packaging. That result is a positive signal, but it is not enough to conclude that the software is secure, compatible, and ready to serve users. An artifact can build cleanly yet still contain business logic bugs, security vulnerabilities, unapproved dependencies, misconfigurations, incompatible migrations, or lack an operational plan when deployment runs into trouble.

We must distinguish **build success** from **release readiness**. Build success confirms that one stage of producing an artifact has completed. Release readiness is a conclusion drawn from a broader set of evidence: the artifact has clear provenance, tests pass, quality and security policies are satisfied, configurations are compatible, the target environment is ready, deployment permissions are valid, and a post-deployment verification plan is prepared.

## 1. What Does a Successful Build Actually Prove?

A build typically performs several tasks:

- Checking out the exact revision of source code.
- Resolving dependencies and plugins.
- Compiling source code.
- Running code-generation or packaging steps.
- Packaging a JAR, WAR, container image, or bundle.
- Possibly running unit tests if the build task is configured to do so.

If a pipeline only runs `mvn package -DskipTests`, a successful outcome does not prove unit tests ran. If a pipeline only builds a container image, it does not yet prove the application can start in a production-like environment. If a build uses unpinned caches or unlocked dependencies, two builds from the same source can produce different outputs.

Therefore, read the actual scope of the build job instead of relying on a green badge in the CI UI.

| Outcome | What Can Be Concluded | What Cannot Yet Be Concluded |
|---|---|---|
| Compile succeeds | Source compiled with this run's toolchain and dependencies | Business logic is correct |
| Package succeeds | Build tool created the package as configured | Package contains no extra files or secrets |
| Unit tests pass | The executed tests passed | All integration flows and production behaviors are correct |
| Image build passes | Container image was built | Image is secure, minimal, or runnable on target |
| Pipeline is green | Jobs configured as required passed under current rules | Full release policy is satisfied and no gate was bypassed |

A pipeline can be green because tests were not enabled, scans are not required checks, or a failing step was configured with `continue-on-error`. Consequently, the pipeline definition and release policy must be treated as part of the evidence.

## 2. Distinguishing Build, Verification, and Release Readiness

A software delivery process should have multiple verification layers, with each layer answering a different question.

| Stage | Question | Evidence Examples |
|---|---|---|
| Build | Can an artifact be produced from source? | Compile log, package checksum |
| Test | Does the tested behavior pass? | Unit, integration, contract, E2E reports |
| Quality analysis | Does the code meet quality standards? | Static analysis, coverage, lint |
| Security verification | Do the artifact and dependencies meet security policy? | SAST, SCA, secret scan, image scan, SBOM |
| Artifact verification | Does the product have valid origin and integrity? | Digest, signature, provenance |
| Compatibility | Are artifact, config, schema, and runtime compatible? | Schema validation, migration test, compatibility report |
| Release authorization | Is the change authorized for release? | Approval, change record, policy result |
| Deployment validation | Does the new version behave well after deploy? | Smoke test, SLI, business checks |

Not every project needs the same number of steps or the same level of control. An internal library, a web application, and a payment service carry different risks. However, every release needs predefined minimum criteria and must never be inferred solely from a build result.

## 3. Establishing Release Criteria Instead of Just Watching Pipeline Status

Release criteria are the set of conditions that must be met before an artifact is promoted or deployed. Criteria should be concrete, verifiable, and tied to product risk.

For example, a release might require:

- The artifact is built from a reviewed commit on a protected branch.
- Required unit, integration, and contract tests all pass.
- Static analysis has no policy blockers.
- Dependency and container scans have no findings exceeding blocking thresholds.
- Secret scanning detects no committed credentials.
- SBOM and provenance are generated and stored with the release.
- Artifact digest matches the build output and registry record.
- Config schemas and database migrations have been tested.
- Target environment and capacity satisfy deployment conditions.
- Approval is complete if required by the environment.
- Rollout strategy, post-deploy checks, and a recovery plan are in place.

Each condition should have an explicit status:

- **Pass:** checked and passed.
- **Fail:** checked and failed.
- **Waived:** approved exception with rationale, owner, and expiration.
- **Not applicable:** does not apply, with explanation.
- **Unknown/Not run:** no evidence yet; must never be treated as pass.

If a required gate fails to run due to a runner outage or a missing report, the release lacks sufficient evidence. Never turn an unknown status into success just to keep the pipeline moving.

## 4. Testing Must Match Risk and Usage Flows

Passing tests are meaningful when they cover critical behaviors and run against configurations close to real-world conditions.

Common test layers:

| Test Type | Scope | Limitations to Understand |
|---|---|---|
| Unit test | Small function, class, or module | Does not verify real integration |
| Component test | Single component with mocked dependencies | May differ from real system behavior |
| Integration test | Real database, queue, cache, or service in test env | May not cover production topology |
| Contract test | API/event compatibility between producer and consumer | Does not prove full business logic |
| End-to-end test | User flow from start to finish | Slow, prone to flakiness, and often covers only a subset |
| Performance/load test | Latency, throughput, saturation under load | Results depend on data and environment configuration |
| Resilience test | Behavior when dependencies fail or time out | Requires scoped blast radius and safe environment |

A green test suite does not mean every behavior is correct. Identify high-impact business flows, such as login, checkout, order creation, authorization, and data writes. For narrow changes, relevant tests plus an appropriate regression suite may suffice; for platform or contract changes, testing scope must be broader.

Do not run tests merely for a coverage number. Coverage signals which code was executed; it does not directly measure assertion quality or scenario completeness.

## 5. Quality Gates Must Reflect Real Policy

Static analysis, linting, coverage, and quality checks can catch defects before release. Yet a quality dashboard does not automatically become a release gate.

You must define:

- Which rules are blockers and which are warnings only.
- Whether thresholds apply to new code or the entire codebase.
- Which baseline governs pre-existing findings.
- Who may grant a waiver and for how long.
- Which gates are mandatory for production.
- Whether a malfunctioning scanner halts the release or follows an exception process.

For example, 82% overall coverage does not prove a new change was adequately tested. A codebase can have high overall coverage while newly added logic has no tests at all. Prioritize quality checks on new code and high-risk areas.

A good quality gate returns evidence traceable to the commit and artifact. Avoid storing only a "Quality: Passed" badge without the underlying report and rule set version used.

## 6. A Successful Build Does Not Prove Security

An application can compile and pass tests while still containing vulnerable dependencies, exposed secrets, or insecure configurations.

Verification layers typically worth considering:

- **SAST:** analyzes source code for security vulnerability patterns.
- **SCA:** checks dependencies, licenses, and known vulnerabilities.
- **Secret scanning:** detects tokens, private keys, or credentials in repositories and artifacts.
- **Container/image scanning:** checks OS packages, libraries, and image configuration.
- **IaC scanning:** checks Terraform, Kubernetes manifests, and infrastructure configuration.
- **DAST/API testing:** tests the running application in an appropriate environment.
- **SBOM:** records software components inside the artifact.
- **Signature/provenance verification:** verifies origin and integrity.

Not all findings carry the same severity. Release policy should consider severity, exploitability, exposure, available patches, and approved exceptions. However, findings above blocking thresholds must not be ignored simply because the build succeeded.

## 7. Verifying the Artifact: Right Content, Right Origin

A build job can produce an artifact, but the release pipeline needs to know the exact artifact being sent for deployment.

For container images, reference them by digest:

~~~text
registry.example.com/payments/api@sha256:...
~~~

For packages or binaries, store the checksum and immutable version in the release manifest.

Verify that:

- The artifact comes from a trusted registry/repository.
- The digest matches the value recorded after build.
- The artifact was produced from an authorized repository, commit, and workflow.
- Signatures are valid if required by policy.
- Provenance identifies the builder, source revision, and build process.
- Scan results and test evidence are bound to that exact digest.

Tags like `latest` or an overwritable version are insufficient to identify content. If staging tests digest A while production pulls a tag that moved to digest B, the pipeline is no longer promoting the same product.

The rule to apply is **build once, verify once, promote the same artifact across environments**. Do not rebuild just because you are moving from staging to production.

## 8. Dependencies and Build Environments Also Affect Reliability

A successful build only reflects the dependencies and toolchain used by the runner at that moment. If dependencies are unlocked, plugins are downloaded from uncontrolled sources, or runners use shifting images, build outputs can become hard to reproduce.

Best practices:

- Commit lockfiles or dependency constraints appropriate to the ecosystem.
- Pin compiler, build tool, and critical action/plugin versions.
- Use managed dependency repositories/registries.
- Verify checksums or signatures where the ecosystem supports them.
- Control caches and never let caches bypass verification steps.
- Record the build environment and toolchain versions.
- Generate an SBOM and provenance for the artifact.

Caching speeds up builds, but a cache is not proof of integrity. When a cache holds compromised dependencies or stale artifacts, a build can still succeed with unintended contents if proper checks are absent.

## 9. Configuration and Secrets Can Break a Release Even with a Valid Artifact

The same artifact can behave differently depending on environment configuration. A green build does not prove production config is valid.

Before release, verify:

- Config schema matches the application version.
- Endpoints and resource references belong to the right environment.
- Feature flags have safe default values.
- Resource requests, timeouts, and connection pools are appropriate.
- Secret references exist and the workload identity has read permissions.
- No plaintext secrets exist in the repository, image, or artifact.
- Config version/checksum matches the reviewed version.

Do not place secret values in release manifests. Store only references or resource identifiers; a secret manager provides values at runtime based on identity and policy.

A production config can be syntactically valid yet point to the staging database or a nonexistent endpoint. Both schema validation and environment-specific semantic checks are needed.

## 10. Database Migrations and Compatibility

An artifact can build and pass tests on a freshly created database yet fail when upgrading a production database that already holds data.

Verify:

- Migration versions and checksums.
- Fresh database migration.
- Upgrade tests from the current schema.
- Backfills and NULL/duplicate data handling.
- Locks, execution time, and storage capacity.
- Compatibility between the older application version and the new schema.
- How to resume if a migration is interrupted.
- A roll-forward or restore plan if data changes are irreversible.

With rolling deployments, old and new application versions can run side by side temporarily. The expand-and-contract strategy preserves compatibility: add the new structure, deploy code supporting both, migrate data and consumers, and remove the old structure in a later release.

Do not treat a successful migration on a small test database as sufficient proof for production. Evaluate data scale, DDL types, and behavior on the exact database engine/version.

## 11. Environment Readiness Is a Separate Gate

A release that qualifies on code can still fail to deploy because the target environment is not ready.

Before deploying, check:

- Target environment, account, region, cluster, and namespace.
- Expected capacity, quotas, and resources.
- Health of dependencies such as databases, caches, queues, and external providers.
- Network policies, DNS, certificates, and ingress.
- Deploy permissions and workload identity.
- Change windows, concurrency locks, and in-progress deployments.
- Backups or point-in-time recovery if the change carries data risk.
- Rollout strategy and fallback capability.

Do not use an overly broad credential to attempt a deploy just to discover whether the target is correct. Target and authorization must be verified before performing actions with side effects.

## 12. Release Authorization and Approval Cannot Be Inferred from Build

A build job typically does not know who is authorized to approve production, whether the change falls within a deployment window, or whether approval is bound to the exact artifact.

The release pipeline must verify:

- Required checks for the commit have passed.
- Branch/tag and source repository comply with policy.
- Artifact digest has not changed since verification.
- Approval is attached to a specific release descriptor.
- The approver holds the right role and scope.
- No expired approvals or approvals invalidated by changed inputs are accepted.
- Environment protection rules have been applied.

Approval should not be a generic button click. Approvers need to review the artifact digest, config version, target, migrations, scan results, test evidence, and recovery plan.

If the artifact, config, or target changes after approval, re-verify and require fresh approval per policy. A prior green build does not automatically authorize a new deployment request.

## 13. Release Readiness Must Include an Operational Plan

An artifact can be technically releasable while lacking visibility or recovery options when errors occur. Before release, prepare:

- Dashboards and alerts for key SLIs.
- Logs, traces, and correlation IDs sufficient for investigation.
- Smoke tests or synthetic transactions.
- Guardrails for error rate, latency, and business metrics.
- Rollout stages and observation windows.
- Kill switches or feature flags where appropriate.
- Rollback/roll-forward runbooks.
- Accountable owners and escalation channels.
- Post-recovery verification steps.

If you cannot tell which version is serving traffic or cannot verify business behavior, the team can hardly conclude the release is stable even if the deploy controller reports completion.

## 14. Example: Build Passes, Yet Release Is Not Ready

Suppose a pull request updates a payment service:

| Check | Result | Assessment |
|---|---|---|
| Compile and package | Pass | Artifact produced |
| Unit tests | Pass | Logic verified at unit scope |
| Integration tests | Pass | Test database flow works |
| SAST | Pass | No blockers per rule set |
| SCA | Fail | Dependency has vulnerability exceeding policy threshold |
| Secret scan | Pass | No credentials detected |
| Artifact provenance | Pass | Build origin verified |
| Production config validation | Not run | No config evidence yet |
| Migration upgrade test | Not run | Existing schema not yet verified |
| Approval | Pending | Not yet authorized for production deploy |

In this case, the build succeeded, yet the release is not eligible. The pipeline must block promotion because SCA failed and mandatory gates lack results. The team must update the dependency, re-run checks, and complete the missing verification steps.

Do not use passing unit tests to waive a security scan. The two checks answer different questions.

## 15. Pipeline Example with Gates Between Build and Deploy

The illustrative workflow below separates build, testing, security verification, and production deployment. The scripts represent tooling configured by the organization.

~~~yaml
name: Release candidate

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      digest: ${{ steps.publish.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Build and package
        run: ./mvnw --batch-mode verify

      - name: Build and publish immutable artifact
        id: publish
        run: |
          digest="$(./scripts/publish-artifact.sh)"
          [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
          echo "digest=$digest" >> "$GITHUB_OUTPUT"

  verify:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    steps:
      - uses: actions/checkout@v4
      - name: Verify artifact, provenance and security policy
        env:
          ARTIFACT_DIGEST: ${{ needs.build.outputs.digest }}
        run: ./scripts/verify-release-candidate.sh "$ARTIFACT_DIGEST"

  deploy-production:
    needs: [build, verify]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Deploy verified artifact
        env:
          ARTIFACT_DIGEST: ${{ needs.build.outputs.digest }}
        run: ./scripts/deploy-by-digest.sh "$ARTIFACT_DIGEST"
~~~

This is an illustrative skeleton and does not automatically create full quality gates. The `packages: write` permission in the build job is for publishing to GitHub Packages; if an external registry uses OIDC, grant `id-token: write` on the job requiring authentication along with corresponding policies. The verify job only has package read permission. The publish script should create and store the artifact, SBOM, and provenance according to organizational workflow; the verify script should validate test, security, provenance, config, and migration evidence per policy and return a nonzero exit code if any required gate fails. The production environment must have protection rules configured separately; declaring an environment name in YAML does not automatically create reviewers or approvals.

This example also assumes the publish script returns only a digest confirmed by the registry. In practice, separate tests prior to publishing if needed, generate SBOM/provenance, sign the artifact, and store reports. The deploy job must use the exact verified digest rather than re-resolving a mutable tag.

## 16. Promotion Across Environments Should Not Rebuild

A reliable way to release is promoting the exact same artifact across environments:

1. Build the artifact from a reviewed commit.
2. Run tests and security checks.
3. Publish an immutable artifact, recording its digest and provenance.
4. Deploy that digest to staging.
5. Run smoke, integration, and post-deployment validation.
6. Collect approval and release evidence.
7. Promote the same digest to production.
8. Monitor post-deploy guardrails.

Config and secret references can differ by environment; the artifact digest should stay identical. If you rebuild when moving to production, the result is no longer the exact artifact tested in staging.

A release manifest can store:

~~~yaml
releaseId: payments-2.8.1
sourceCommit: a1b2c3d4
artifact:
  repository: registry.example.com/payments/api
  digest: sha256:0123456789abcdef...
  provenance: attestations/payments-2.8.1
verification:
  unitTests: passed
  integrationTests: passed
  securityPolicy: passed
  configValidation: passed
target:
  environment: staging
~~~

This manifest is an example; statuses should be generated from actual verification system results, never typed manually. Do not put secrets in the manifest. When promoting to production, update the target/deployment record using an immutable or versioned mechanism.

## 17. Handling Waivers and Exceptions Transparently

There are situations where a gate has not passed yet the organization decides to accept bounded risk, such as when a finding has been evaluated as a false positive or no patch is available yet. Exceptions must be documented, never hidden by turning a scanner result into a pass.

A waiver should include:

- The waived gate and finding.
- Scope of artifact/version/environment.
- Rationale and assessment evidence.
- Risk owner and approver.
- Mitigating controls.
- Expiration timestamp.
- Remediation ticket and assignee.

Waivers should not apply broadly to all releases or indefinitely. When the artifact digest changes, the finding is fixed, or the waiver expires, the policy must be re-evaluated.

Some conditions may not permit waivers depending on regulatory and security requirements. Distinguish organizationally approved exceptions from un-audited gate bypasses.

## 18. Recording Release Evidence for Traceability

Every release needs a set of evidence linking source, build, artifact, verification, and deployment.

Minimum information:

- Repository, commit SHA, and pull request.
- Build run ID, toolchain, and timestamp.
- Artifact coordinates, digest, and provenance.
- Test reports and test suite version.
- Quality/security policy results.
- SBOM and signature verification where applicable.
- Config version/checksum and migration version.
- Target environment and deployment revision.
- Approval records and waivers if any.
- Post-deployment validation and final outcome.

Do not store secrets or unnecessary personal data in release evidence. Use IDs, digests, and links to reports with appropriate access controls.

During an incident, release evidence answers: which artifact ran, which commit built it, which gates it passed, who approved it, and which configuration was used. If you only have a green build status, the team lacks enough information to reproduce or investigate the release.

## 19. Release Readiness Checklist

Before promoting or deploying to production, verify:

- [ ] Build succeeded from an identified source revision.
- [ ] Required tests ran and produced reports.
- [ ] Quality gates apply to new code and high-risk areas.
- [ ] Security scans satisfy policy or have valid waivers.
- [ ] Secret scans found no exposed credentials.
- [ ] SBOM, signatures, and provenance are present when required by policy.
- [ ] Artifact digest is verified and unaltered.
- [ ] Dependencies/toolchain are managed and traceable.
- [ ] Config schemas, endpoints, and secret references are valid for the target environment.
- [ ] Database migrations were tested against an appropriate schema.
- [ ] Target, capacity, dependencies, and deploy permissions are ready.
- [ ] Approval is bound to the exact artifact, config, and target.
- [ ] Rollout strategy, observability, guardrails, and recovery plans exist.
- [ ] Post-deployment validation has clear pass/fail criteria.
- [ ] Release evidence is stored and retrievable.

Build success is an important prerequisite for producing an artifact, but release readiness demands far more evidence. When a pipeline cleanly separates build, verification, authorization, deployment, and post-deployment validation, the team does not have to guess that a green checkmark equals safety. Each release is promoted because it satisfies defined criteria and can be traced, explained, or recovered when needed.
