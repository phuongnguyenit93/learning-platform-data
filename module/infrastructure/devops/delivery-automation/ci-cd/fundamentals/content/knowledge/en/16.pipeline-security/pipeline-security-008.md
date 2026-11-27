# Separating Approval, Publishing, and Deployment Privileges Where Needed

In a CI/CD process, three actions often appear close together yet carry different meanings and risks: **approving** a change or release, **publishing** an artifact/release so other people or systems can consume it, and **deploying** an artifact into a running environment. If a single account or job can perform all three actions on its own without independent controls, a misconfiguration or compromised pipeline can ship unverified code externally or straight into production.

Separation of privileges limits the blast radius of each identity and establishes independent control points. Approvers decide whether a specific action is permitted to proceed; publishers place the verified artifact into the release repository; deployers push that exact artifact to the target environment with least privilege. Roles may be combined for low-risk changes, but must be separated when blast radius, sensitivity, or audit requirements demand it.

## 1. Distinguishing Approve, Publish, and Deploy

| Action | Question Answered | Primary Inputs | Output or Effect |
|---|---|---|---|
| Approve | Is the stated action authorized given current risk and evidence? | Change/release request, commit, artifact digest, test/scan results, environment, recovery plan | Decision bearing identity, timestamp, scope, and rationale |
| Publish | Should the verified artifact/release be placed in the designated repository or distribution channel? | Artifact, digest, provenance, signature, SBOM, metadata, and release authorization | Artifact becomes downloadable or consumable via registry/package repository/release channel |
| Deploy | Should the specific artifact be activated on the target runtime/environment? | Artifact digest, manifest/config revision, target environment, deployment policy | Running workload or version changes; deployment record created |

For example, a Java library may be built and tested in CI, then published to a package registry for other projects to consume. Publishing does not mean deploying that library to production. For a containerized service, publishing pushes an image to a registry; deploying updates a Kubernetes workload to run that image by digest.

Approvals must also specify what is being approved. Approving a pull request authorizes merging code; approving a publish authorizes releasing a package; approving a deployment authorizes promoting an artifact into an environment. One decision does not automatically substitute for the others when policy requires independence.

## 2. Why Separate Privileges?

If the same identity can edit pipelines, build artifacts, publish packages, self-approve, and deploy to production, a single malicious change or leaked credential can bypass every safeguard within the same flow. Separation of privileges reduces the likelihood that a single failure escalates into a system-wide incident.

Core objectives:

- **Reduce blast radius:** publishers cannot alter production workloads directly; deployers cannot replace published packages.
- **Prevent self-approval:** the person or workflow authoring a change cannot unilaterally authorize high-risk actions when policy requires independence.
- **Protect the supply chain:** only artifacts with matching origin, digest, and evidence are published or deployed.
- **Minimize standing privileges:** each job receives only the credentials needed during its execution window.
- **Improve auditability:** logs clearly show who approved, which identity published, and which identity deployed.
- **Create intentional checkpoints:** releases can be inspected before becoming public or entering production.

```mermaid
flowchart LR
    SRC[Source change] --> V[Verify: tests / scans]
    V --> B[Build artifact]
    B --> E[Evidence: digest / provenance / SBOM]
    E --> PA[Publish approval, when required]
    PA --> PUB[Publisher identity]
    PUB --> REG[Release registry]
    REG --> DA[Deployment approval, when required]
    DA --> DEP[Deployer identity]
    DEP --> ENV[Target environment]
    ENV --> OBS[Post-deploy verification]
```

The diagram shows how the three privileges can be split into distinct steps and identities. For low-risk internal releases, some steps may be automated or orchestrated within one workflow. What matters is that decision authority, artifact write privileges, and runtime modification privileges remain clearly defined.

## 3. When to Combine and When to Separate

Not every project needs three separate teams or three separate systems. The degree of separation should match risk, impact, and compliance requirements.

| Scenario | Appropriate Organization |
|---|---|
| Experimental build on a personal branch, not shared externally | Automated build; no release publish or production approval required |
| Internal snapshot publishing for a small dev team | CI may auto-publish after tests; write permissions scoped strictly to snapshot repository |
| Publishing a shared package consumed by multiple teams | Separate publish privileges from source edit privileges; require provenance, version, and policy checks |
| Releasing a public library or image | Independent release approval, dedicated publisher, signatures, and auditing |
| Automated staging deployment from main branch | Can be automated if artifact and environment are constrained; deploy identity scoped solely to staging |
| Production deployment for a standard service | Policy-based deployment approval, dedicated deployer, or protected environment |
| Data migration, IAM/network change, or high-blast-radius release | Separate author, approver, and operator; include change window, rehearsal, and rollback/restore plan |
| Emergency hotfix/incident | Use narrowly scoped break-glass access with logging and post-incident review instead of disabling all controls |

Even a small team can apply separation of duties using machine identities and policies: build workflows have no deploy permissions; publish jobs use dedicated tokens; production environments require authorized human approval. Separation does not necessarily require multiple departments, yet it must prevent one principal from both altering and self-approving sensitive actions.

## 4. Defining Roles and Permissions for Each Identity

Distinguish human identities from automation identities (workload/service identities). Never share a single token across the entire pipeline.

| Role / Identity | Recommended Permissions | Should Not Have by Default |
|---|---|---|
| Developer/author | Push personal branches, open PRs, view CI results | Publish official releases or deploy directly to production |
| Code reviewer | Review and approve code changes per branch policy | Use publish/deploy credentials merely because they have review rights |
| Release approver | Inspect evidence and approve a specific release candidate | Modify artifacts, self-publish, or self-deploy under the same decision |
| Build job identity | Read source/dependencies and produce artifacts | Write to public release registries or modify production runtime |
| Signing identity | Sign artifacts/provenance that meet policy | Modify source, self-approve, or deploy workloads |
| Publisher identity | Write packages/images to designated repository or release channel | Modify source, read runtime secrets, or access production clusters |
| Deployment approver | Authorize a specific artifact for a specific environment | Self-issue deploy credentials or swap digests after approval |
| Deployer/GitOps identity | Read artifacts and update assigned workloads/resources | Overwrite release registries, publish packages, or administer the entire cluster |
| Runtime workload identity | Access dependencies/secrets needed by the application | Publish artifacts or deploy different versions |

Permissions should be constrained by principal, action, resource, and context. For example, a publisher might have `write` access to `registry.example.com/team/orders/releases` but only `read` access elsewhere; a deployer might `read` images and `patch` Deployments in the `orders-production` namespace, without permission to `push` images.

## 5. Designing Trust Boundaries Between Stages

A secure pipeline should divide along meaningful boundaries:

### Build and Verify

The build job checks out a specific commit, uses defined dependencies/toolchains, and creates the artifact. Tests, scans, SBOMs, and provenance are bound to that commit or artifact. This job typically needs only source read access and write access to temporary storage or the pipeline's artifact store.

### Sign and Attest

A signing service or authorized job signs the digest/provenance according to policy. Signing keys must be protected separately—ideally via KMS/HSM or workload identity—never stored as long-lived files in the repository. Never grant signing key access to jobs executing code from untrusted pull requests.

### Publish

The publisher checks the artifact, digest, evidence, and release metadata before writing to the release registry or distribution channel. It needs write access only to the designated repository/package namespace. When publishing to public registries, verify package name, version, license, metadata, signature, and contents prior to public exposure.

### Deploy

The deployer retrieves the published artifact by digest and applies it to the authorized environment. The deployer needs registry read access and permission to update target workloads. It does not need permission to push new images to the registry or read all application secrets.

### Post-Deploy Verify

Health checks, smoke tests, metrics, and deployment records confirm the outcome. Observation permissions can be separated from runtime modification permissions. If verification fails, the workflow halts rollout or triggers rollback per policy.

## 6. Binding Approvals to the Exact Artifact, Action, and Target

An approval decision is valid only for what the approver actually reviewed. Approval records should bind to:

- Change/release ID and pipeline run ID.
- Repository and commit SHA.
- Artifact name/version and immutable digest.
- Provenance, signatures, SBOM, and relevant test/scan results.
- Authorized action: publish, deploy, promote, or migration.
- Target: package repository, release channel, environment, cluster/namespace, or service.
- Configuration/manifest revision and rollout strategy.
- Approver, role, timestamp, justification, and validity window.

If the artifact digest changes, the target environment changes, or manifest edits alter risk, prior approvals must expire or be re-evaluated. Never allow a pipeline to swap an image tag or package version after approval while retaining the prior decision.

### Separating Publish Approval and Deploy Approval

A library approved for publishing to a package registry is not automatically approved for deployment into every production service. Conversely, an image approved for staging deployment is not automatically authorized for production. Each approval must explicitly state the action and scope.

If an organization uses a single release approval covering both publish and deploy, policy must clearly state this, the covered environments, and invariant conditions. For production environments or public packages, dedicated gates—or at minimum an additional verification condition—are typically warranted.

## 7. Publishing Artifacts Safely

A publisher is a principal capable of placing content where others trust and download it. This privilege introduces supply chain risk comparable to deployment access: a forged package or swapped image can impact many downstream systems.

Before publishing, verify:

1. The artifact was built from a known commit/revision by a trusted pipeline.
2. Mandatory tests and quality gates passed.
3. The digest computed from current bytes matches the release manifest digest.
4. Provenance/attestations and signatures are valid per trust policy if required.
5. The SBOM and security scan results bind to the exact digest.
6. Package name, version, repository, and release channel match the target.
7. No secrets, debug files, or non-public data are included.
8. Existing versions are handled according to registry immutability/overwrite policies.

### Using Staging/Candidate and Release Repositories

A helpful pattern builds into a candidate/quarantine area, runs checks, and then promotes the verified artifact to the release repository. Promotion should preserve artifact contents and record the link between candidate and release. For OCI images, copy manifests/layers and verify the digest post-copy; if a tool or process alters contents, the digest changes and must be treated as a new artifact.

Never use mutable tags like `latest` as sole proof of an approved artifact. Use versions/tags for human lookup, while storing digests and deploying by digest. If a registry permits overwriting the same version, enforce policies preventing overwrites or enforce strict auditing.

### Publishers Do Not Need Deploy Permissions

A publisher only needs write access to its assigned registry/package namespace. It does not need production kubeconfigs, cloud admin roles, or database secret access. If platform constraints force publish and deploy into one job, consider separating credentials and minimizing lifetimes; never use a single token with both registry write and production modification rights unnecessarily.

## 8. Deploying Safely After Publishing

Deployment should fetch the published artifact and re-verify its digest/signature/provenance before modifying runtime state. Deployers should accept only approved targets and reviewed configurations.

Critical controls:

- Only protected workflows, branches, or tags may request production deployments.
- Apply environment protections or manual approvals proportional to risk.
- Use workload identity/OIDC or short-lived credentials.
- Grant the deployer only required permissions on the target namespace/service/resource.
- Prevent deployers from overwriting artifacts in the release registry.
- Use controlled rollout strategies: rolling, canary, or blue-green depending on the service.
- Verify health, smoke tests, and metrics before expanding the rollout.
- Record deployment ID, artifact digest, config revision, actor, and outcome.
- Maintain a known rollback target and retain prior artifacts for an appropriate window.

When using GitOps, write access to the production manifest repository is effectively indirect deployment access. Protect branches, reviews, and policies on that repository; the GitOps controller should only have permission to reconcile its assigned namespace/resources.

## 9. Example Privilege Separation in GitLab CI

The example below separates verify/build, publish, and deploy into distinct jobs. Scripts are project-supplied wrappers; adapt registry names, token scopes, artifact paths, and protected environment policies to your actual GitLab configuration.

```yaml
stages:
  - verify
  - build
  - publish
  - deploy

verify:
  stage: verify
  image: eclipse-temurin:21-jdk
  script:
    - ./gradlew test --no-daemon
    - ./ci/run-security-checks.sh

build_candidate:
  stage: build
  needs:
    - verify
  script:
    - ./ci/build-image.sh
    - ./ci/write-release-manifest.sh
  artifacts:
    paths:
      - release-manifest.json

publish_release:
  stage: publish
  needs:
    - job: build_candidate
      artifacts: true
  environment:
    name: release-publish
  rules:
    - if: '$CI_COMMIT_TAG'
  script:
    - ./ci/verify-candidate.sh release-manifest.json
    - ./ci/publish-by-digest.sh release-manifest.json
  artifacts:
    paths:
      - release-manifest.json

deploy_production:
  stage: deploy
  needs:
    - job: publish_release
  environment:
    name: production
  when: manual
  allow_failure: false
  resource_group: production-orders
  script:
    - ./ci/verify-release-digest.sh release-manifest.json
    - ./ci/deploy-by-digest.sh release-manifest.json
    - ./ci/verify-production-health.sh
```

In this example:

- `verify` holds no publish or deploy credentials.
- `build_candidate` creates the artifact and manifest, yet lacks permission to write to the release repository.
- `publish_release` runs only on release tags and uses credentials scoped to the target registry. The protected environment `release-publish` can restrict who is allowed to run the job if GitLab is configured accordingly.
- `deploy_production` is a separate job awaiting manual action and bound to the `production` protected environment. `resource_group` prevents two deployments from modifying the same target concurrently.
- The deployer needs image read and workload update permissions, without permission to push new images.

This is an illustrative skeleton. In GitLab, CI/CD variables can be protected by branch/tag and environment scope; protected environments and deployment approvals depend on edition and configuration. Issue separate tokens for publisher and deployer rather than sharing one pipeline-wide token. Also ensure the manifest is passed reliably via `needs`/artifacts or registry; adjust paths if the deploy job does not receive artifacts directly.

## 10. Example Privilege Separation in GitHub Actions

GitHub Actions can separate jobs using `permissions` and environments. The publish job receives `packages: write`; the deploy job receives only what is needed to fetch artifacts and request an OIDC token. Required reviewers and branch restrictions are configured in Environment settings.

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  verify-build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Verify source
        run: ./ci/run-required-checks.sh
      - name: Build candidate
        run: ./ci/build-candidate.sh
      - name: Upload candidate
        uses: actions/upload-artifact@v4
        with:
          name: release-candidate
          path: |
            dist/
            release-manifest.json

  publish:
    needs: verify-build
    runs-on: ubuntu-latest
    environment: release-publish
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: release-candidate
          path: .
      - name: Verify and publish
        run: ./ci/verify-and-publish.sh dist/ release-manifest.json
      - name: Pass release manifest to deploy job
        uses: actions/upload-artifact@v4
        with:
          name: approved-release-manifest
          path: release-manifest.json

  deploy-production:
    needs: publish
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
      packages: read
    steps:
      - uses: actions/checkout@v4
      - name: Download approved release manifest
        uses: actions/download-artifact@v4
        with:
          name: approved-release-manifest
          path: .release
      - name: Verify approved digest
        run: ./ci/verify-release-digest.sh .release/release-manifest.json
      - name: Deploy
        run: ./ci/deploy-by-digest.sh .release/release-manifest.json
      - name: Verify runtime
        run: ./ci/verify-production-health.sh
```

What this configuration enforces:

- `verify-build` only reads source and builds a candidate; it holds no package write rights or OIDC token permissions.
- `publish` is granted `packages: write` scoped strictly to that job and the `release-publish` environment; only this job can publish.
- `deploy-production` is protected by the `production` environment, which can enforce reviewers per repository settings. It holds only `packages: read` and `id-token: write` to obtain a short-lived deployment identity.
- No job automatically inherits all permissions merely because the workflow was triggered by a tag.

This example is a structural template. Scripts must propagate and verify the exact same digest from build through publish to deploy; never rebuild a different image in the deploy job. In GitHub Actions, `environment` enforces approval gates only when protection rules are configured in repository settings. `id-token: write` does not grant cloud access by itself; cloud trust policies must constrain repository, workflow, and environment. In production systems, pin actions by commit SHA per supply chain policy and grant only genuinely needed permissions.

## 11. Controlling Permission Changes and Credentials

Splitting jobs while sharing one all-powerful credential creates no real boundary. Design credentials by role:

| Credential | Principal Using It | Recommended Scope | Lifetime |
|---|---|---|---|
| Source read token | Verify/build job | Read specific repository | Job duration or short-lived token |
| Candidate write token | Build job if uploading candidates | Write specific candidate repository | Short-lived |
| Release publish identity | Publisher | Write specific package/image repository or release channel | Publish job only |
| Signing identity | Signing service/job | Sign policy-compliant artifacts/provenance, no deploy rights | Provisioned via KMS/HSM or federation |
| Deployment identity | Deployer/GitOps controller | Read artifacts and update target resources | Short-lived or workload identity |
| Runtime identity | Application | Read secrets and call the service's own dependencies | Workload lifecycle, auto-rotated |

Prefer OIDC/workload identity or temporary credentials over long-lived access keys. Trust policies must constrain issuer, audience, and claims such as repository, branch/tag, workflow, or environment. Never keep an `admin` token as a fallback across jobs.

If a token is compromised, you must be able to revoke each principal independently without rotating every credential across the platform. That is a major operational benefit of separating publish and deploy identities.

## 12. Handling Retries, Rollbacks, and Emergencies

Publish and deploy actions have side effects and must be designed to be idempotent or guarded against duplicate execution.

- **Publish retry:** if an upload is interrupted, check whether the package/version already exists and whether the digest matches before retrying. Never overwrite a published version with different content.
- **Deploy retry:** check current state and deployment revision before re-applying. Use immutable digests and lock/concurrency controls for the same target.
- **Rollback:** deployers may be permitted to revert to a previously stored stable digest; rollback privileges do not require permission to publish new artifacts.
- **Emergency release:** use a constrained break-glass procedure recording incident/change ID, approver or incident commander, time limit, and post-incident review.
- **Approval expiry:** if the artifact, target, or configuration changes, require fresh approval instead of reusing an old one.

Never grant a publisher runtime modification permissions merely to support rollbacks. Likewise, never allow a deployer to publish replacement packages on its own when the release registry fails; keep roles and recovery paths distinct.

## 13. Audit Trails and Evidence for Each Action

A release record should link all three actions while keeping each decision distinct:

| Event | Data to Retain |
|---|---|
| Approval | Approval ID, approver, role, authorized action, digest, target, timestamp, rationale, and policy version |
| Publish | Publisher identity, package/repository, version/tag, digest, provenance/signature, pipeline run, and timestamp |
| Deploy | Deployer identity, environment/resource, digest, config revision, deployment ID, rollout strategy, and outcome |
| Verification | Health/smoke results, metrics window, incident link, and confirming operator if needed |
| Rollback | Prior/new digests, rationale, actor, related deployment ID, and verification result |

Send logs to a centralized system with separated read and write permissions. Anyone holding publish or deploy permissions should not be able to edit or delete audit records of their own actions. Never log secrets or tokens; use reference IDs and safe metadata.

## 14. Common Anti-Patterns

- **One job holding build, publish, and deploy rights:** a single script bug can compromise the entire chain.
- **Approvers able to self-publish/deploy with the same identity:** decisions lack independence and auditability.
- **Publishers holding cluster admin permissions:** package write privileges expand into production modification rights.
- **Deployers holding release registry write permissions:** a deploy job can tamper with trusted content.
- **Using mutable tags instead of digests:** the artifact after approval may no longer match what was reviewed.
- **Publishing public packages from any branch:** experimental code or unvetted dependencies can become public releases.
- **Treating merge approval as deployment approval:** the two decisions have different goals and scopes.
- **One all-powerful token shared across every job:** YAML separates stages, while real permissions remain unseparated.
- **Failing to check whether a package/version already exists:** retries can overwrite prior releases.
- **Failing to record who published and who deployed:** hard to establish accountability when an artifact is wrong or production fails.
- **Manual jobs with no restriction on who can trigger them:** provides a button without authorization control.
- **Rebuilding inside the deploy step:** production may run a different artifact from what was tested and published.

## 15. Checklist for Designing Approve, Publish, and Deploy Privileges

When reviewing a pipeline, verify:

1. Are the distinctions between approve, publish, and deploy clearly defined?
2. Does each action have its own principal/identity or equivalent privilege-separation policy?
3. Are change authors prevented from self-approving high-risk actions?
4. Are build/verify jobs kept free of publish and deploy permissions?
5. Do publishers have write access strictly to the designated registry, package namespace, or release channel?
6. Do deployers have permissions strictly to read artifacts and update target environments/resources?
7. Is the signing identity protected separately and restricted to signing policy-compliant artifacts?
8. Are approvals bound to commit, artifact digest, action, target, and expiration?
9. Do changes to digest, target, or config invalidate prior approvals?
10. Do published artifacts include required provenance, SBOMs, signatures, and check results?
11. Do deployments use the exact published and approved digest?
12. Are credentials short-lived, narrowly scoped, separated, and independently revocable?
13. Are protected environments/branches, runner isolation, and workflow trigger restrictions enforced?
14. Do publish/deploy retries enforce idempotency or duplicate-execution guards?
15. Are rollbacks to stable digests and audited break-glass procedures in place?
16. Does the audit trail separately record approver, publisher, deployer, artifact, and deployment outcome?

Privilege separation is not meant to add manual friction to every release. Its purpose is to place authority where it belongs: authorized reviewers decide, publishers release the exact verified artifact, and deployers update only the intended environment. When separation scales with risk and each action carries a clear identity, evidence trail, and scope, CI/CD automates repetitive work while preventing a single bug or leaked credential from traversing the entire release chain.
