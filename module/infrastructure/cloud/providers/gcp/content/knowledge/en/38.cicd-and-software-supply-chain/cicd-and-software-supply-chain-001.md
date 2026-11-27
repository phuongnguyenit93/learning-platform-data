# Designing Application and Infrastructure Pipelines on GCP

## 1. Objectives of a CI/CD Pipeline

A CI/CD pipeline transforms changes in Git into software or infrastructure versions that are inspectable, traceable, reproducibly deployable, and recoverable during incidents. The pipeline must answer key questions: which source code produced the artifact, which checks ran, who or which system is allowed to deploy, which artifact is running in each environment, and how to roll back to a safe version.

In Google Cloud, a common architecture combines:

- **Cloud Build** to automate builds, run tests, analyze source code, and package artifacts.
- **Artifact Registry** to store container images and packages.
- **Artifact Analysis** to scan for vulnerabilities and manage artifact security metadata.
- **Cloud Deploy** to manage releases, targets, promotions, approvals, and rollouts for supported workloads such as GKE and Cloud Run.
- **Terraform** to describe and deploy infrastructure using Infrastructure as Code (IaC).
- **IAM, Workload Identity Federation, and Secret Manager** to limit permissions and protect credentials.
- **Cloud Monitoring, Cloud Logging, and Cloud Trace** to track deployment outcomes and service impact.

These components do not have to be used together in every organization. Cloud Build can integrate with other CI systems; Cloud Deploy can receive releases from any CI system capable of calling the API or CLI; Terraform can run in Cloud Build or a dedicated IaC platform. Choose tools that fit your existing environment, while preserving the principles of source control, artifacts, permissions, and traceability.

## 2. Overall Design: Two Linked Streams with Separate Permissions

The application pipeline and the infrastructure pipeline share a source repository, review process, and security standards, but perform different types of changes. An application build pipeline produces runnable artifacts; an infrastructure pipeline modifies projects, IAM, VPCs, clusters, databases, or platform configuration. Permissions to build images should not automatically include permissions to modify IAM or delete production resources.

~~~mermaid
flowchart TB
    A[Git repository: application + deployment config] --> B[Pull request checks]
    B --> C{Review and policy checks passed?}
    C -- No --> X[Block merge]
    C -- Yes --> D[Merge into protected branch]
    D --> E[Cloud Build CI]
    E --> F[Build, unit/integration tests, scan]
    F --> G[Artifact Registry: image by digest]
    G --> H[Provenance and attestations]
    H --> I[Cloud Deploy release]
    I --> J[Development / Staging]
    J --> K[Smoke test and verification]
    K --> L[Approval / promotion]
    L --> M[Production rollout]
    M --> N[Cloud Monitoring: SLOs and alerts]
    N --> O{Regression?}
    O -- Yes --> P[Rollback or mitigation]
    O -- No --> Q[Monitor release]

    A --> R[Terraform / IaC pipeline]
    R --> S[Format, validate, policy, plan]
    S --> T[Review plan and approval]
    T --> U[Apply exact saved plan]
    U --> V[Cloud resources and Terraform state]
    V --> N
~~~

The application stream typically flows through build, test, scan, publish artifact, create release, deploy to staging, verification, and promotion. The IaC stream flows through configuration checks, generating an execution plan, change review, approval, and apply. Both streams can be triggered by the same pull request, but they must use appropriate deployment identities and permission scopes.

### 2.1. Division of Responsibilities Across Components

| Component | Responsibility | Artifacts/Records to Retain |
|---|---|---|
| Git repository | Store source code, Dockerfile, manifests, pipeline config, and Terraform | Commit SHA, review, approval |
| Cloud Build | Execute CI according to reproducible configuration | Build ID, logs, test results, image digest |
| Artifact Registry | Store versioned artifacts | Image/package digest, tag, and metadata |
| Artifact Analysis | Analyze artifact vulnerabilities and security metadata | Vulnerability occurrences, scan metadata |
| Cloud Build provenance | Record source and process used to build the artifact | Verifiable provenance |
| Binary Authorization | Enforce trust policies at deploy time on supported runtimes | Decision to allow or deny artifact |
| Cloud Deploy | Manage releases, targets, and rollouts | Release, rollout, approval, verification |
| Terraform | Manage infrastructure using declarative configuration | Saved plan, state, and change history |
| Cloud Monitoring / Logging | Monitor the system post-release | Metrics, logs, traces, and alerts |

Cloud Build is the build execution service. Cloud Deploy manages promoting a release across targets. Artifact Registry stores artifacts. Components can integrate with one another, but they do not replace each other's responsibilities.

## 3. Source Code Management and Trigger Conditions

### 3.1. Standardizing the Repository

Place components that affect deployability under version control:

- Source code and tests.
- Dockerfile or buildpack configuration.
- Cloud Build configuration such as `cloudbuild.yaml`.
- Skaffold and manifests for workloads using Cloud Deploy.
- Cloud Deploy delivery pipeline and target definitions.
- Terraform modules, environment configuration, and policies.
- Database migration scripts, smoke tests, and release notes.
- Operational documentation, SLOs, and rollback instructions.

Separate environments using folders or repositories depending on organization scale. A reference structure:

~~~text
repository/
  app/
    src/
    test/
    Dockerfile
  deploy/
    skaffold.yaml
    clouddeploy.yaml
    manifests/
  infra/
    modules/
    environments/
      dev/
      staging/
      prod/
  ci/
    cloudbuild.yaml
    scripts/
  policies/
  docs/
~~~

Splitting into multiple repositories is not mandatory. What matters is that reviewers can identify which changes affect the application, pipeline, or infrastructure, and that approvers have the appropriate expertise for that scope.

### 3.2. Pull Requests and Protected Branches

A secure pipeline should have at least two trigger groups:

1. **Pull request trigger:** runs fast checks such as formatting, unit tests, static analysis, secret scanning, dependency review, and Terraform validate and plan within allowed scopes. This trigger should not have permission to deploy to production or read production secrets.
2. **Protected branch trigger:** runs release builds after a pull request has been reviewed and merged. This trigger uses a separate service account, produces traceable artifacts, and can initiate releases.

Cloud Build supports triggers based on repository events such as push or pull request, and can filter by branch or change conditions. You must connect the repository to Cloud Build before creating triggers.

Do not allow pull requests from forks or untrusted code to run in a highly privileged build. Anyone with write access to a repository connected to a trigger can influence the source code being built; pull request triggers can also execute content submitted by the PR author. Therefore, separating permissions, controlling event types, and reviewing build configurations are integral parts of pipeline security.

### 3.3. Change-Based Triggers

In a monorepo, it is not necessary to build every service on every commit. You can use path filters or logic that detects modified directories to run only the relevant test suite. However, changes to shared libraries, pipeline configs, base images, or Terraform modules can affect multiple services; declare dependencies so triggers do not miss anything.

Example trigger matrix:

| Event | Checks or Actions |
|---|---|
| Pull request modifying `app/` | Build application, unit tests, static analysis |
| Pull request modifying `infra/` | Terraform fmt, validate, policy check, plan |
| Pull request modifying `deploy/` | Validate manifests, Skaffold, and Cloud Deploy config |
| Merge into `main` | Build release artifact, scan, provenance |
| Create protected release tag | Create release from previously built and verified artifact |
| Scheduled run | Drift detection, dependency scan, policy checks |

## 4. Designing CI with Cloud Build

### 4.1. CI Steps

A CI sequence typically includes:

1. Check out the exact commit and verify the commit SHA.
2. Restore dependencies from trusted repositories.
3. Run formatting checks, linting, and static analysis.
4. Run unit tests.
5. Run integration tests in an appropriate environment.
6. Analyze dependencies, licenses, secrets, and vulnerabilities.
7. Build artifacts from verified source.
8. Push artifacts to Artifact Registry.
9. Record the image digest, build ID, test results, and provenance.
10. Signal CD only when all required gates have passed.

Cloud Build executes steps defined in a build configuration. Each build step runs in its own container; the build config can specify tools such as Maven, Gradle, Docker, Bazel, or self-managed builders. Keeping build scripts in the repository ensures the process is consistent and reviewable.

### 4.2. Cloud Build Configuration Example

The example below illustrates a Java application using Maven and Docker. Replace project, region, repository, and image values for your real environment. In production, pin builder images by digest and manage toolchain versions explicitly.

~~~yaml
steps:
  - id: unit-and-integration-tests
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - verify

  - id: build-container
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - --pull
      - -t
      - ${_IMAGE_URI}:${SHORT_SHA}
      - .

images:
  - ${_IMAGE_URI}:${SHORT_SHA}

substitutions:
  _IMAGE_URI: asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api

options:
  logging: CLOUD_LOGGING_ONLY
  requestedVerifyOption: VERIFIED
~~~

`images` declares the image Cloud Build should push after building. Tagging with the commit SHA makes lookup convenient, though tags can still be changed if the repository allows overwriting. During promotion, reference images by immutable digest.

`requestedVerifyOption: VERIFIED` requests verifiable build provenance according to the mechanism supported by Cloud Build. Check your project's configuration and prerequisites to ensure the build generates the desired provenance.

This example does not yet include complete steps for scanning, signing, policy evaluation, or deployment. Add gates appropriate to the application's sensitivity level. Never put credentials or secrets directly into YAML.

### 4.3. Distinguishing Fast CI from Release Builds

Pull request CI should prioritize fast feedback and least privilege. Post-merge release builds can run additional integration tests, full scans, packaging, provenance, and release creation. Do not use test results from a different commit to authorize a release.

A release must be linked to the exact commit and exact artifact digest that was tested. If source changes after testing, rebuild and re-verify. Rebuilding per environment can cause the staging artifact to differ from the production artifact even under the same tag, which weakens traceability.

## 5. Artifact Registry and Immutable Artifact Management

Artifact Registry stores container images and packages produced by CI. Organize repositories by language, application, environment, or access control boundary depending on governance needs.

Recommended principles:

- Use a separate repository for production artifacts when write and read permissions need to be isolated.
- Use meaningful tags such as commit SHA or release version for lookup.
- Promote by SHA-256 digest, avoiding rebuilds or pointing to a `latest` tag when moving artifacts through staging and production.
- Restrict who can push, delete, or modify repository policies.
- Manage retention and cleanup policies to avoid deleting artifacts still needed for rollback or investigation.
- Inspect external source artifacts and pin dependencies/tool images to immutable versions.
- Record the relationship between commit, build ID, image digest, provenance, and Cloud Deploy release.

Example of an image referenced by digest:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api@sha256:IMAGE_DIGEST
~~~

Tags are useful for humans, while digests are useful for identifying exact content. An image can have multiple tags, whereas a digest identifies a single specific content blob. When creating a release, use the digest of the image that passed testing and security checks.

## 6. Securing the Software Supply Chain

A pipeline must do more than confirm the source code compiles. It must also prove that artifacts come from a trusted source and passed through the defined verification process.

### 6.1. Dependencies and Builders

- Lock dependency versions using lockfiles or appropriate dependency management.
- Verify the download sources for packages and builder images.
- Do not use mutable tags like `latest` for base images or builders in production pipelines.
- Review changes in dependency lockfiles.
- Restrict write permissions to Artifact Registry.
- Use ephemeral, isolated build environments between builds and control input parameters.
- Prevent any build step from modifying scripts or artifacts of another build.

Cloud Build provides managed build environments and build protection features. For workloads requiring private network access, private pools allow customizing the build environment and connecting to a VPC. Private pools are also a prerequisite in certain scenarios when applying VPC Service Controls to builds.

### 6.2. Vulnerability Scanning and Policy Gates

Artifact Analysis can scan container images and packages in Artifact Registry. Results may include vulnerability details, malicious packages, dependencies, and licenses depending on the package type and enabled scanning features.

A policy gate can categorize findings:

| Scan Result | Reference Action |
|---|---|
| No findings above threshold | Allow to proceed |
| Critical vulnerability with available patch and active exploit | Block release, require remediation |
| High vulnerability | Block or require time-bound exception per policy |
| Unpatched finding | Assess exploitability, exposure, and mitigations; assign owner |
| Unknown-origin or flagged malicious package | Block artifact and investigate dependency source |
| Incomplete or stale scan results | Do not assume clean by default; re-run scan or re-verify |

Specific thresholds must be based on risk appetite and organizational requirements. Scanning is not guaranteed to detect every vulnerability; it is one control layer among many.

### 6.3. Provenance, SBOM, and Attestation

**Build provenance** records verifiable data about the artifact creation process, such as the artifact digest, source location, build parameters, and execution details. Cloud Build can generate provenance aligned with the SLSA standards supported by the service. Use provenance to answer which artifact was built from which source and by which build.

**Software Bill of Materials (SBOM)** lists the software components inside an artifact. SBOMs aid impact analysis when a library has a vulnerability or when evaluating package origins.

**Attestation** is verifiable evidence that an artifact satisfied a condition, such as being built by a trusted build pipeline or passing a check. Binary Authorization can use attestations and policies to verify artifacts before allowing deployment on supported runtimes such as GKE and Cloud Run.

Illustrative chain of trust:

~~~mermaid
flowchart LR
    A[Reviewed source commit] --> B[Trusted Cloud Build]
    B --> C[Artifact Registry image digest]
    B --> D[Build provenance]
    C --> E[Artifact Analysis scan]
    D --> F[Attestation / verification]
    E --> F
    F --> G[Binary Authorization policy]
    G --> H[Runtime deployment]
~~~

Provenance proves information about the build; scans report analysis results at the time of scanning; attestations record verifiable claims; Binary Authorization enforces policy. No single component alone proves an application is completely secure.

## 7. Managing Pipeline Identities, Permissions, and Secrets

### 7.1. Separating Service Accounts by Responsibility

Do not use a single service account with Owner permissions for the entire pipeline. Separate identities by task:

| Identity | Required Permissions |
|---|---|
| PR validation build | Read source and run tests; no permission to deploy to production or read production secrets |
| Release build | Push artifacts to designated repository, write build logs and required provenance |
| Terraform plan | Read state and query resources needed to generate plan; no apply permission if workflow allows separation |
| Terraform apply | Modify only the resource scope of the approved environment |
| Cloud Deploy execution | Render and deploy to designated targets |
| Runtime service account | Only the permissions the application needs while running |

The service account used to build, the service account used to deploy, and the running workload's service account are distinct identities. This reduces blast radius if a build step or an application is compromised.

Cloud Build allows selecting a user-managed service account for a trigger. When using a trigger, the service account configured on the trigger is the identity used for the build; the service account field in the build config does not override the trigger's identity. Grant least-privilege roles to that service account and audit who has permission to edit triggers or the source repository.

### 7.2. Workload Identity Federation

If the pipeline runs outside Google Cloud, such as GitHub Actions, GitLab SaaS, Azure DevOps, or HCP Terraform, prefer **Workload Identity Federation (WIF)** to exchange OIDC/SAML tokens for short-lived credentials. This avoids storing long-lived service account JSON keys in CI secrets.

WIF configuration must restrict trust using attribute mappings and attribute conditions. For example, with GitHub, you can restrict by organization, repository, branch, or workflow. Do not check only the issuer; verify that the token actually originates from an authorized repository and ref.

A workflow can use `google-github-actions/auth` to generate a credential configuration file. The `id-token: write` permission should only be granted to jobs that need to obtain an OIDC token. When using service account impersonation, the service account must have permissions on the target resources and the provider must allow the appropriate principal to impersonate that account.

### 7.3. Secret Manager

Do not put API keys, database passwords, signing keys, or tokens into source code, Dockerfiles, or build configs. Store secrets in Secret Manager and grant `secretAccessor` only to the build step or workload that needs them.

Cloud Build supports `availableSecrets` and `secretEnv` to inject secrets into specific steps. Limit which steps receive secrets, avoid printing environment variables to logs, and delete temporary files after use. If a secret is exposed, revoke or rotate it according to incident procedures.

## 8. Continuous Delivery with Cloud Deploy

### 8.1. Releases and Targets

Cloud Deploy manages progressing a release through a declared sequence of targets. A **release** represents the content being delivered, including rendering source and image references. A **rollout** is an instance of deploying a release to a specific target.

Example environment progression:

- `dev`: early integration checks.
- `staging`: production-like environment for smoke tests and acceptance tests.
- `production`: target requiring approval and a cautious rollout strategy.

Cloud Deploy uses Skaffold to render and deploy manifests to supported targets. The CI system creates a release via API or CLI after the artifact has been verified. Cloud Deploy snapshots the pipeline instance associated with the release; later changes to pipeline configuration do not retroactively alter already-created release definitions.

### 8.2. Delivery Pipeline and Targets Example

The example below describes a pipeline for GKE with staging and production. Replace project, region, and cluster for your actual environment.

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
  name: orders-api
description: Release orders-api through staging and production
serialPipeline:
  stages:
    - targetId: staging
    - targetId: production
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: staging
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/staging
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: production
requireApproval: true
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/production
~~~

This is an illustrative skeleton; verify the schema, permissions, and Skaffold configuration corresponding to the Cloud Deploy version in use. The production target requires approval before a rollout can proceed.

### 8.3. Creating a Release from a Verified Image

After building and scanning succeed, CI can create a release using the image digest. Example command:

~~~bash
gcloud deploy releases create orders-api-${SHORT_SHA} \
  --delivery-pipeline=orders-api \
  --region=asia-southeast1 \
  --source=. \
  --images=app=asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api@sha256:IMAGE_DIGEST
~~~

The image name `app` must match the image alias in the Skaffold configuration. The source must contain the rendering/deployment configuration needed by the release. Store the release name, commit SHA, and digest in build metadata for investigation or rollback.

### 8.4. Approval, Verification, and Progressive Rollout

Approvals can be required on the production target. Approvers should review the commit, image digest, test results, scan results, provenance, rollout plan, and expected impact.

After deployment, Cloud Deploy can run verification tasks. Verification is typically executed via a team-provided test container; exit code 0 indicates success and non-zero indicates failure. Verification should check health endpoints, smoke tests, dependency connectivity, and critical behaviors.

For workloads needing risk reduction, use progressive rollout/canary when supported by the target and runtime. Only increase traffic or instance count after observing error rate, latency, saturation, and business metrics. Canary helps detect regressions on a subset of traffic; it does not replace pre-deployment testing.

### 8.5. Rollback

When a release causes a regression, roll back to a previously known-good release. Cloud Deploy supports creating a new rollout based on an earlier release. Example:

~~~bash
gcloud deploy targets rollback production \
  --delivery-pipeline=orders-api \
  --region=asia-southeast1
~~~

A specific release can be specified if needed. Rolling back an application does not automatically revert database schema or infrastructure changes. Design migrations to be backward-compatible, use expand-and-contract when possible, and maintain a separate data handling plan.

## 9. Infrastructure Pipelines with Terraform

### 9.1. Separating Plan and Apply

Changes to IAM, VPC, firewall, GKE, Cloud Run, Cloud SQL, and Storage can affect many workloads. Infrastructure pipelines need a clear review step:

1. Check Terraform formatting and version constraints.
2. Run `terraform init` with a reviewed provider lockfile.
3. Run `terraform validate`.
4. Run policy checks and security scanning for IaC.
5. Generate a saved plan using `terraform plan -out=tfplan`.
6. Output the plan contents so owners can review resources to be added, modified, or destroyed.
7. Require approval based on environment and risk scope.
8. Run `terraform apply tfplan` using the exact approved saved plan.
9. Verify resources post-apply and store results alongside the pipeline run.

Do not generate a plan, wait for approval, and then automatically generate a new plan to apply without re-reviewing. The new plan may differ because state or resources have changed.

### 9.2. Remote State and Environment Isolation

Terraform state must be stored in a shared backend with access control and backups. The Google Cloud Storage backend is a common choice for Terraform on GCP. Enable object versioning on the state bucket and restrict read/write permissions; state can contain sensitive data even when values are marked sensitive in Terraform.

Use separate state for dev, staging, and production, or isolate along appropriate governance boundaries. Do not allow multiple pipelines to concurrently apply to the same state. The GCS backend supports state locking to prevent two processes from writing state simultaneously; pipelines should still be organized to avoid overlapping runs and handle lock timeouts safely.

Backend example:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "ORG_TERRAFORM_STATE"
    prefix = "orders-api/production"
  }
}
~~~

The bucket name and prefix are examples. The state bucket should be created and protected in a separate bootstrap process; do not make the pipeline that creates the state bucket depend on a state that does not yet exist.

### 9.3. Saved Plan and Approval

A `tfplan` file can contain sensitive configuration values. Store it as an internal artifact with access control and short retention. Only apply plans from the exact commit, workspace/state, and pipeline run that was reviewed. If state or resources change and invalidate the plan, generate a new plan and require re-review.

Example job commands:

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false -out=tfplan
terraform show -no-color tfplan
# After approval, in a protected apply job:
terraform apply -input=false tfplan
~~~

This is an illustrative command sequence. Separate plan and apply jobs according to your CI system's artifact/approval mechanism, while preserving the exact commit and state backend. Do not commit plans or state files into the repository.

### 9.4. Policy as Code and Drift Detection

Policy as code can block changes such as:

- Opening SSH/RDP to the entire Internet.
- Creating data buckets without public access prevention.
- Assigning Owner/Editor roles at unauthorized scopes.
- Creating public databases without approval.
- Provisioning resources in regions not approved by the organization.
- Disabling mandatory logging, encryption, or backups.

Run scheduled drift detection to compare actual configuration against IaC. When drift is detected, determine whether the change was a valid operation, an incident, or an out-of-band configuration change. Do not automatically apply to overwrite drift without understanding its impact; doing so could inadvertently revert emergency changes or intentional adjustments.

## 10. Securing Pipelines and Deployment Environments

### 10.1. Separating Projects and Permissions

A common pattern is separating CI/CD management projects, artifact projects, and runtime projects based on security requirements. It is not mandatory to create a separate project for every component; use project/folder boundaries to isolate blast radius, billing, quotas, and permissions.

Minimum controls:

- Build service accounts push only to required repositories.
- Deploy service accounts deploy only to assigned targets.
- Terraform apply identities modify only resources of the corresponding environment.
- Trigger creators do not automatically receive production permissions.
- Only platform/security teams can modify pipeline configs, service accounts, or sensitive policies.
- Use independent approval for production and high-risk IAM/network/database changes.
- Audit log changes to triggers, IAM, pipelines, targets, and policies.

### 10.2. Securing the Build Environment

Build configs and builder images are part of the software supply chain. Attackers may modify build scripts, swap dependencies, exfiltrate credentials from the environment, or alter published artifacts.

Controls:

- Review changes to `cloudbuild.yaml`, Dockerfiles, Skaffold, and Terraform.
- Use controlled builder images, pin versions/digests, and vet sources.
- Use ephemeral build workers, restricting network connectivity and permissions beyond what is needed.
- For builds requiring private network access, consider Cloud Build private pools.
- Separate untrusted PR builds from release builds that hold secrets and deployment permissions.
- Do not pass secrets via command-line arguments or logs.
- Enable provenance and retain build logs according to retention policies.
- Restrict permissions to modify build triggers and trigger service accounts.

### 10.3. Environment and Configuration Separation

Do not share the same project, database, or secrets across dev, staging, and production if doing so compromises isolation. Environment configuration can be passed via substitutions or environment-specific manifests, but arbitrary input variables should not be allowed to change production image digests or service accounts.

A release should preserve the exact same artifact across environments. Only runtime configuration such as hostnames, replica counts, secret references, and quotas should vary by target. Do not rebuild images when promoting from staging to production.

## 11. Database Migrations and Changes Without Simple Rollback

Application deployments often accompany schema migrations. Rolling back a container does not roll back data. A migration that drops a column or alters a data type can break the previous application version.

Use the expand-and-contract process:

1. **Expand:** add new columns or tables in a backward-compatible manner.
2. **Deploy code:** the new application can read/write both old and new structures during the transition period.
3. **Migrate data:** backfill data in batches with verification and checkpoints.
4. **Switch:** transition the application to use the new schema.
5. **Contract:** remove old structures only after confirming no running version depends on them.

For large migrations, run them as controlled jobs with locking or duplicate-run prevention and the ability to resume after failure. Establish a backup/restore plan and verify recovery time. Do not bundle destructive migrations with an application rollout without separate review.

## 12. Release Operations and Post-Deployment Observability

A tool-level rollout success does not guarantee the application is functioning properly. After each deployment, monitor:

- Request success and error rates by version.
- p50, p95, p99 latency.
- CPU, memory, concurrency, queue depth, and autoscaling.
- Error logs and new exceptions.
- Database connections, query latency, and migration status.
- Quotas and rate limits of GCP APIs.
- Business metrics such as payment success rate or completed job counts.
- SLOs and error budgets.

Use labels or resource metadata to attach release ID, commit SHA, and service version to metrics/logs where appropriate. Avoid creating high-cardinality metric labels such as request ID or user ID.

If a canary exceeds error rate or latency thresholds, halt promotion and evaluate a rollback. When rolling back, record the previous release, the faulty release, the metrics driving the decision, and the post-rollback outcome. If the incident stems from infrastructure or a database migration, an application rollback may not suffice; follow the corresponding playbook.

## 13. Practical Scenario: Releasing a Java API to Cloud Run

A team develops a Java service named `orders-api`. Source code resides in GitHub, images are stored in Artifact Registry, and the workload runs on Cloud Run. Cloud Run infrastructure, service accounts, IAM, and the database are managed with Terraform.

### Pipeline Design

1. A developer opens a pull request. Cloud Build runs Maven verify, static analysis, secret scanning, and Terraform checks if changes touch `infra/`.
2. Reviewers inspect the code, dependency changes, Dockerfile, and Terraform plan. The pull request build has no permission to deploy to production or read production secrets.
3. After merging into the protected branch, the release trigger runs a build from the approved commit. Cloud Build builds the image, runs tests, pushes the image to Artifact Registry, and records the digest.
4. Artifact Analysis scans the image/packages. Build provenance is generated; policies check vulnerabilities and build origin.
5. CI creates a Cloud Deploy release referencing the verified image digest. Cloud Deploy deploys to staging.
6. Verification runs smoke tests: health endpoint, database connectivity, Secret Manager access, and a core business flow.
7. The release is proposed for promotion to production. Authorized approvers review tests, scans, provenance, and the rollout plan.
8. Cloud Deploy deploys according to the chosen strategy. Cloud Monitoring tracks error rate, latency, and business metrics.
9. If the canary misses thresholds, halt promotion and create a rollback rollout to the last known-good release. If the database schema changed, follow the separate migration playbook.
10. Infrastructure changes execute in the Terraform pipeline: plan, review, approval, and apply using a dedicated identity. State is stored in a GCS backend with versioning and restricted permissions.

### Completion Criteria

- Releases can be traced back to commit SHA, build ID, and image digest.
- The production image is the exact same image that passed staging and scanning.
- No long-lived service account keys exist in the repository or CI secrets.
- Untrusted pull requests cannot deploy or read production secrets.
- Terraform plans are reviewed before apply; state is separated by environment.
- Production promotion requires approval and verification.
- Dashboards, alerts, and rollback playbooks are in place.
- Database migrations have compatibility and recovery plans.

## 14. Common Design Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Rebuilding images for each environment | Production artifact differs from staging artifact | Promote the same digest |
| Using the `latest` tag | Cannot determine exact running image | Use digests and commit/release tags |
| Build trigger with Owner permissions | PR code can execute overly broad actions | Use dedicated service accounts with least privilege |
| Storing service account keys in long-lived GitHub secrets | Leakage risk and difficult rotation | Use Workload Identity Federation |
| Not vetting builders and dependencies | Artifacts can be altered via untrusted sources | Pin versions, review sources, scan, and use provenance |
| Applying Terraform directly from a branch | Production changes without plan review | Saved plan, approval, and apply the exact plan |
| Sharing Terraform state across environments | Large blast radius, easy to overwrite wrong environment | Separate state per environment |
| Letting PR builds read production secrets | Untrusted code can exfiltrate secrets | Separate PR validation and release builds |
| No post-deployment verification | Rollout appears green while application fails | Smoke tests, canary, and SLO monitoring |
| Rolling back app while ignoring database | Older version incompatible with new schema | Expand-and-contract and migration playbook |

## 15. Pre-Production Pipeline Checklist

### Source and CI

- [ ] Source, Dockerfile, build config, manifests, and IaC are under version control.
- [ ] Pull requests require review and branch protection.
- [ ] Branch/path triggers are controlled.
- [ ] PR builds have no production permissions or access to production secrets.
- [ ] Unit, integration, static analysis, and dependency checks run automatically.
- [ ] Builder images and dependencies are pinned, reviewed, and source-vetted.

### Artifacts and Supply Chain

- [ ] Artifact Registry repositories have appropriate IAM and retention policies.
- [ ] Artifacts are referenced by immutable digest.
- [ ] Vulnerability scanning is enabled for required artifact types.
- [ ] Build provenance is generated and verifiable.
- [ ] SBOM/attestations are stored when required by policy.
- [ ] Binary Authorization or deployment policies are enforced on supported runtimes.

### Identity and Secrets

- [ ] Build, deploy, Terraform apply, and runtime use separate identities.
- [ ] Service accounts have only necessary permissions.
- [ ] External CI uses Workload Identity Federation where supported.
- [ ] Secrets reside in Secret Manager and are granted only to steps that need them.
- [ ] Tokens, keys, and secrets are never written to logs or artifacts.

### CD and IaC

- [ ] Releases link to commit SHA and artifact digest.
- [ ] Staging verification runs before production.
- [ ] Production requires approval and a rollout strategy.
- [ ] Rollback procedures exist and database migration limits are understood.
- [ ] Terraform always generates a plan first; plans are reviewed and the exact approved plan is applied.
- [ ] Remote state has restricted access, versioning, and locking.
- [ ] Drift detection and policy checks are in place.

### Operations

- [ ] Release ID/version appears in telemetry.
- [ ] Dashboards track error rate, latency, saturation, and business metrics.
- [ ] Alerts are configured for SLOs and error budgets.
- [ ] Playbooks exist to halt rollouts, roll back, and investigate.
- [ ] Procedures exist to revoke credentials and handle artifacts with discovered vulnerabilities.

## 16. Self-Check Questions

1. Why is it necessary to separate pull request validation builds from release builds that have deployment permissions?
2. What distinct responsibilities do Cloud Build, Artifact Registry, and Cloud Deploy handle?
3. Why should promotion from staging to production use the same image digest?
4. What does build provenance tell you, and what does it not prove?
5. What risks does Workload Identity Federation reduce when using GitHub Actions or GitLab?
6. Why does Terraform need a saved plan and approval before apply?
7. If a Terraform plan changes after it has been approved, what should the pipeline do?
8. How do Cloud Deploy verification and canary rollouts help detect regressions?
9. Why might a container rollback fail to restore a database after a destructive migration?
10. Which permissions should be separated among the build service account, deploy service account, and runtime service account?

## References

- [Cloud Build overview](https://docs.cloud.google.com/build/docs/overview)
- [Create and manage Cloud Build triggers](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Run builds with a user-managed service account](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Safeguard builds](https://docs.cloud.google.com/software-supply-chain-security/docs/safeguard-builds)
- [Use secrets from Secret Manager in Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/use-secrets)
- [Generate and validate build provenance](https://docs.cloud.google.com/build/docs/securing-builds/generate-build-provenance)
- [Artifact Analysis package scanning](https://docs.cloud.google.com/artifact-analysis/docs/package-scanning-overview)
- [Software supply chain security overview](https://docs.cloud.google.com/software-supply-chain-security/docs/overview)
- [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Cloud Deploy overview](https://docs.cloud.google.com/deploy/docs/overview)
- [Create Cloud Deploy delivery pipelines and targets](https://docs.cloud.google.com/deploy/docs/create-pipeline-targets)
- [Verify a Cloud Deploy deployment](https://docs.cloud.google.com/deploy/docs/verify-deployment)
- [Promote a release and manage approvals](https://docs.cloud.google.com/deploy/docs/promote-release)
- [Roll back a Cloud Deploy target](https://docs.cloud.google.com/deploy/docs/roll-back)
- [Terraform operations best practices](https://docs.cloud.google.com/docs/terraform/best-practices/operations)
