# Build Once and Promote the Same Artifact Across Environments

> **Chapter:** Software Delivery  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models. This lesson focuses on building an immutable artifact once, verifying its provenance and quality, and promoting that exact artifact across development, staging, and production—while managing configuration, secrets, approvals, deployments, and recovery according to Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the build-once, promote-everywhere principle and why artifacts must be identified by immutable versions or digests.
2. Distinguish between source code, build outputs, packages, container images, deployment bundles, configuration, and runtime state.
3. Design a pipeline that produces reproducible artifacts with provenance, SBOMs, signatures, and test evidence.
4. Separate environment configuration and secrets from artifacts while verifying compatibility before deployment.
5. Design promotion flows, release gates, approvals, progressive delivery, and access controls.
6. Handle database migrations, feature flags, dependencies, and configuration changes without breaking cross-environment consistency.
7. Establish rollback/roll-forward strategies, verify running artifacts, and manage auditable exceptions.

## 1. The Build Once, Promote the Same Artifact Principle

Software is typically deployed across multiple environments: development, test, staging, pre-production, and production. Each environment validates a distinct set of assumptions before the software serves real users.

The **build once, promote the same artifact** principle requires:

- Building the artifact from a single source revision using a controlled pipeline.
- Identifying the artifact by an immutable version or digest.
- Testing and validating that exact artifact.
- Promoting the same artifact across environments without rebuilding it per environment.
- Changing only environment-specific configuration and secrets via managed runtime or configuration mechanisms.
- Storing evidence covering source, build, tests, approvals, and deployments.

For example, the pipeline builds the `booking-api` container image with digest `sha256:abc...`. Staging and production must run the image with that exact same digest. Production must never build a separate image from the same tag or rerun Docker build against newer dependencies.

This enables answering a critical post-incident question: which exact artifact was tested, approved, and running in production?

### 1.1. Why Is Rebuilding per Environment Dangerous?

If each environment runs its own build, outputs can diverge because:

- Dependencies or base images were updated between builds.
- Build tools, compilers, plugins, or runners differ in version.
- Environment variables inadvertently influence compilation or bundling.
- A package registry returns a newer version or a replaced artifact.
- Build scripts pull current timestamps, external data, or non-deterministic outputs.
- Manual patches are applied in only one environment.
- An operator runs a different command than the tested pipeline.

The same source commit does not guarantee identical binaries. The same image tag also does not guarantee unchanged image contents if tags can be overwritten.

### 1.2. Build Once Does Not Mean One Binary Uses Identical Config Everywhere

An immutable artifact still requires environment-appropriate configuration: database endpoints, hostnames, replica counts, resource limits, logging levels, feature flags, and secret references.

The key point is not baking environment-dependent values into the binary or image whenever they can be supplied at deployment or runtime. The artifact stays unchanged; configuration is versioned or managed separately with policies and auditing.

## 2. Distinguishing Software Release Components

| Component | Contents | Changes During Promotion? |
| --- | --- | --- |
| Source revision | Commit/tag and source contents | Input to build, not a substitute for the built release |
| Build recipe | Toolchain, dependency lock, compiler, build instructions | Fixed and versioned |
| Artifact | Binary, package, image, or deployment bundle | **No** |
| Artifact digest | Content identifier via hash | Unchanged if artifact is unchanged |
| Configuration | Endpoints, feature settings, resource profiles, non-secret values | May vary by environment |
| Secret | Passwords, tokens, keys, certificate private keys | Varies by environment; retrieved from secret manager |
| Deployment manifest | How the artifact is deployed onto the platform | May have environment overlays; must be versioned |
| Runtime state | Databases, caches, queues, sessions, volumes | Changes as the application operates |
| Release metadata | Approvals, test evidence, provenance, and deployment history | Appended with each promotion |

A single pipeline may produce multiple artifact types simultaneously: an API image, a worker image, a frontend bundle, a migration package, an SBOM, and a deployment chart. Every artifact needs clear identification and linkage to the same release and source context.

Never bundle secrets into artifacts or commit secrets to configuration repositories. Configurations and deployment manifests may still contain internal endpoints or sensitive operational details, so they also require appropriate access controls.

## 3. Source-to-Production Flow Model

~~~mermaid
flowchart LR
    SRC["Source commit"] --> BUILD["Controlled build"]
    BUILD --> ART["Immutable artifact"]
    BUILD --> META["Provenance + SBOM"]
    ART --> VERIFY["Scan / sign / verify"]
    META --> VERIFY
    VERIFY --> DEV["Deploy development"]
    DEV --> TEST1["Automated tests"]
    TEST1 --> STAGE["Promote same digest to staging"]
    STAGE --> TEST2["Integration / acceptance / performance"]
    TEST2 --> APPROVE["Release approval"]
    APPROVE --> PROD["Promote same digest to production"]
    PROD --> OBS["Health / SLO / audit"]
~~~

Conceptual flow:
1. A developer merges a source revision into a protected branch.
2. CI builds the artifact using locked toolchains and dependencies.
3. The pipeline generates provenance, an SBOM, checksums/digests, and test reports.
4. The artifact is scanned, signed, or attested according to policy.
5. The artifact is deployed to development for early validation.
6. The same digest is promoted to staging for integration and acceptance testing.
7. Release gates verify tests, change records, approvals, and production readiness.
8. The same digest is promoted to production following a rollout strategy.
9. Runtime telemetry, release metadata, and deployment records are stored.

Stage ordering may vary by organization. What must remain invariant is that the promoted artifact is the exact artifact that was verified, and its identity is verifiable at every step.

## 4. Building Immutable Artifacts and Identifying Them Properly

### 4.1. Versions and Digests

Human-readable versions are helpful for release notes, but they are not always sufficient to uniquely identify contents.

Examples:
- Semantic version: `1.8.2`.
- Build version: `1.8.2+build.417`.
- Container reference: `registry.example.com/booking-api:1.8.2`.
- Immutable reference: `registry.example.com/booking-api@sha256:...`.

Tags help locate artifacts; digests identify their exact contents. For production, deploy by digest or an equivalent mechanism guaranteeing immutable identity. Registries need policies preventing overwrites of released artifacts and sufficient retention for rollback and auditing.

### 4.2. Artifact Promotion

Promotion is the act of authorizing an existing artifact for use in a higher environment after satisfying gates. It is not rebuilding the artifact.

A promotion record should capture:
- Artifact URI and digest.
- Source revision and build ID.
- Build recipe/toolchain reference.
- Provenance/attestation and SBOM references.
- Test evidence for the artifact.
- Target environment, configuration revision, and deployment manifest.
- Requester, approver, timestamp, and rationale.
- Rollout results, health checks, and rollback reference.

### 4.3. Immutable Registries

A registry should enforce:
- Separate repositories/projects or environment-scoped access policies.
- Push access restricted to trusted build identities.
- Pull access restricted to authorized deploy identities.
- Immutable release tags or deploy-by-digest enforcement.
- Scanning and retention policies.
- Auditing of push, pull, delete, and replication events.
- Replication of artifacts to DR regions/registries if recovery requires it.
- Prohibition against operators modifying contents behind an approved release tag.

A private registry does not automatically guarantee an artifact is trustworthy. You must verify who built it, from which source, with which dependencies, and whether it was altered after testing.

## 5. Reproducible Builds and Dependency Control

### 5.1. Reproducible Builds

A reproducible build ensures that the same source and defined inputs yield verifiable outputs. Not every system achieves bit-for-bit reproducibility immediately, but uncontrolled sources of variance must be minimized.

Key factors:
- Pin compiler, runtime, build tool, and plugin versions.
- Use lockfiles for dependencies and validate lockfiles in CI.
- Reference base images by digest or immutable version.
- Never fetch floating dependency versions in production builds.
- Record build arguments and toolchain identities.
- Restrict dependencies pulled from untrusted sources.
- Control clocks, locales, timezones, and non-deterministic generation steps.
- Separate build environments from deployment environments.
- Use standardized, patched, least-privilege runners.

### 5.2. Multi-Stage Dockerfile Example

~~~dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine@sha256:REPLACE_WITH_VERIFIED_DIGEST AS build
WORKDIR /src

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run test
RUN npm run build

FROM nginx:stable-alpine@sha256:REPLACE_WITH_VERIFIED_DIGEST AS runtime
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
~~~

The digests in this example must be replaced with verified digests from a trusted registry. Nginx configuration, read/write permissions, non-root ports, health checks, and logging must be tailored to the application. This example illustrates pinning base images and using lockfiles; it is not a complete production Dockerfile for every workload.

### 5.3. Builds Must Not Depend on Production Configuration

Never pass production database passwords into builds. Never fetch production data to compile or build an image. Never bake environment-specific endpoints into source during the build step. If a frontend needs an API endpoint configuration, consider a runtime configuration file or a protected config endpoint so the exact same static bundle can be promoted.

## 6. Provenance, SBOMs, and Artifact Signing

### 6.1. Provenance

Provenance describes an artifact's origin and creation process, such as:
- Source repository and revision.
- Builder and workflow identity.
- Build process and parameters.
- Dependency and source materials.
- Artifact digest and build timestamp.
- Links to build logs and test evidence.

Provenance verifies that an artifact was genuinely built by a trusted pipeline from approved source. It is invaluable when investigating supply-chain incidents or comparing running environments.

### 6.2. SBOM

A Software Bill of Materials lists the software components and dependencies inside an artifact. An SBOM supports:
- Identifying affected products when a library has a vulnerability.
- Tracking direct and transitive dependencies.
- Checking package licenses and origins.
- Supporting risk assessments and audits.

An SBOM must be bound accurately to the artifact digest. An SBOM generated from a different source revision or a different image does not prove the contents of the running image.

### 6.3. Signing and Verification

The pipeline can sign artifacts or attestations using a protected signing identity. The deployment gate verifies:
- The signature is valid and uses a trusted key/identity.
- The digest in the signature matches the artifact being deployed.
- Provenance was generated by an approved builder.
- The build source, branch, and workflow satisfy policy.
- SBOM and scan evidence meet criteria.
- The artifact has not been revoked or quarantined.

~~~mermaid
flowchart TD
    A["Artifact + digest"] --> B["Generate provenance / SBOM"]
    B --> C["Sign artifact or attestation"]
    C --> D["Store in trusted registry"]
    D --> E["Deployment verifier"]
    E --> F{"Identity, digest and policy valid?"}
    F -->|"Yes"| G["Allow promotion"]
    F -->|"No"| H["Block and emit finding"]
~~~

A signature only proves that an artifact was signed by the corresponding identity and that its contents match the signed digest. It does not prove the code is secure or free of vulnerabilities. Combine signing with source review, testing, scanning, policy checks, and runtime monitoring.

## 7. Testing the Exact Artifact Being Promoted

Test reports must be linked to the digest or build ID to prove which object was tested.

Testing layers:
- Unit and component tests.
- Static analysis, linting, and type checks.
- Dependency and vulnerability scanning.
- Container and image scanning.
- Integration tests against compatible services, databases, and brokers.
- Contract tests between producers and consumers.
- End-to-end and acceptance tests.
- Performance and load tests calibrated to risk level.
- Security tests and policy checks.
- Post-deploy smoke tests.
- Migration, restore, and rollback tests when the artifact includes data changes.

### 7.1. Testing the Exact Artifact

A safe workflow:
1. Build the image or package once.
2. Run unit tests in the pipeline against source and build outputs.
3. Scan and sign the artifact.
4. Deploy the image digest into a test environment.
5. Run integration/E2E tests against the image referenced by that exact digest.
6. Promote the tested digest to staging.
7. Run acceptance and performance tests against that same digest.
8. After production deployment, verify the runtime image digest and health.

If staging runs a mutable tag, passing tests do not prove production runs the same image. If production rebuilds, earlier tests may no longer accurately apply to the newly built artifact.

### 7.2. Test Evidence and Release Gates

| Gate | Example Criteria | Evidence |
| --- | --- | --- |
| Source | Review, branch protection, and allowed commit | PR/commit metadata |
| Build | Successful build on a trusted builder | Build ID, logs, provenance |
| Artifact | Valid digest, signature, and SBOM | Registry metadata, attestation |
| Security | No findings exceeding policy thresholds | Scan report, exception reference |
| Functional | Mandatory tests pass | Digest-bound test report |
| Integration | Compatible contracts and dependencies | Integration test results |
| Performance | Within approved regression thresholds | Benchmark report |
| Change | Complete plan, owner, risk assessment, and approval | Change record |
| Deployment | Healthy state, passing SLI/SLOs, and matching runtime digest | Deployment and telemetry records |

Gates require concrete policies, not just pass/fail colors. Security exceptions must link to an exception record with proper authority; never suppress findings by altering scan labels.

## 8. Separating Configuration and Secrets from Artifacts

### 8.1. Environment-Specific Configuration

The same artifact can run across multiple environments using different configurations:

| Attribute | Development | Staging | Production |
| --- | --- | --- | --- |
| API endpoint | Dev service URL | Staging URL | Production URL |
| Database | Test database | Staging dataset | Production database |
| Replicas | Minimal | Near-production profile | Sized for capacity/SLO |
| Logging | Bounded debug | Info/diagnostic | Production policy |
| Feature flags | Experimental | Per release plan | Controlled rollout per approval |
| External providers | Sandbox | Sandbox/pre-prod | Live providers |
| Secrets | Dev secrets | Staging secrets | Isolated production secrets |
| Data | Synthetic/test | Masked or synthetic | Production data per policy |

Configuration should have schemas, types, validation, owners, versions, and audits. Never manually copy configuration files between environments without controls.

### 8.2. Runtime Configuration

An application can read configuration at startup or via a config service. Key decisions include:
- When configuration changes, does the application hot-reload or require a restart?
- Which config version is currently active?
- How is configuration rolled back independently of the artifact?
- Is configuration validated before deployment?
- If the config service is unavailable, does the app fall back to cached config or fail closed?
- Could sensitive config values be logged in startup messages?

Configuration drift between staging and production can explain why the same image behaves differently. Store config revisions and compare behavior-affecting attributes while permitting legitimate differences in endpoints and secrets.

### 8.3. Secrets

Secrets must be managed separately per environment:
- Use a secret manager or vault; never place secrets in source code, image layers, or build arguments.
- Grant read access via workload identity at runtime.
- Keep secrets isolated per environment; staging must never use production credentials.
- Establish rotation and revocation procedures.
- Avoid printing environment variables or sensitive configurations to logs.
- Audit secret retrievals and restrict exports.
- Evaluate injection methods to avoid unnecessary persistence on filesystems.

A secret reference may live in deployment configuration; the secret value itself must never be packaged into the artifact. Secret rotation should not require rebuilding the application when the runtime supports secure secret retrieval.

## 9. Deployment Manifests and Environments

Using the same artifact does not mean every environment requires identical manifests. Replica counts, ingress rules, service accounts, resource requests, network policies, and storage can differ; however, those differences must be managed, reviewed, and validated.

Common approaches include:
- Helm charts with environment-specific values files.
- Kustomize overlays.
- Terraform, Pulumi, or equivalent IaC tools.
- GitOps desired-state repositories.
- Versioned configuration management.

### 9.1. Kubernetes Deployment by Digest Example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api@sha256:REPLACE_WITH_APPROVED_DIGEST
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: APP_ENV
              value: production
            - name: CONFIG_REF
              value: booking-api/production/42
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
~~~

The digest here is a placeholder and must be replaced with a digest that passed release gates. The config reference contains no secrets. Manifests must be validated for user permissions, volumes, writable filesystem paths, network policies, probes, rollout strategies, and workload-appropriate resource values.

### 9.2. Comparing Environment Configurations

Render the final manifest prior to deployment and record a checksum or commit for the configuration. Review diffs between staging and production to catch unintended differences: service accounts, ingress exposure, database migration settings, feature flags, or resource limits.

Do not force production to mirror staging configuration verbatim if doing so causes improper sizing or security posture. The goal is that every difference is intentional, owned, and explainable.

## 10. Promotion Pipelines and Release Gates

### 10.1. Promotion Flow

~~~mermaid
flowchart TD
    A["Reviewed commit"] --> B["Build once"]
    B --> C["Artifact + digest + provenance"]
    C --> D["Scan / sign / test"]
    D --> E["Development"]
    E --> F["Functional / component tests"]
    F --> G["Staging"]
    G --> H["Integration / acceptance / performance"]
    H --> I{"All release gates pass?"}
    I -->|"No"| J["Block / investigate / rebuild from new source if changed"]
    I -->|"Yes"| K["Approval / change window"]
    K --> L["Production canary"]
    L --> M{"Health and SLO pass?"}
    M -->|"No"| N["Rollback or halt rollout"]
    M -->|"Yes"| O["Progressive rollout"]
    O --> P["Verify deployed digest and record release"]
~~~

When source code changes to fix a defect, a new artifact must be built and re-tested to an appropriate level. Never patch a signed image or package directly and reuse the old digest.

### 10.2. Promotion Policy

Release gates may require:
- The artifact originates from an allowed release train or branch.
- The digest resides in a trusted registry.
- Signatures and provenance are valid.
- Scan reports are fresh within policy windows and contain no threshold-breaching findings.
- Test evidence is bound to the exact digest.
- Config and manifest validation succeeded.
- Database migrations are compatible.
- Change approvals are valid and properly scoped.
- Production capacity and maintenance constraints are satisfied.

### 10.3. Separation of Duties

Code authors should not have permission to alter release evidence or deploy directly to production outside the process. Roles can be separated into:
- Developer: source changes.
- CI builder: builds and attestations.
- Release manager / change approver: authorizes promotion per policy.
- Deploy identity: executes deployments.
- Security gate: verifies artifacts and policies.
- SRE / validator: verifies health and release outcomes.

Small teams may use compensating controls, but permissions, audits, and scope limits must remain clear.

## 11. Database Migrations and Compatibility

Building once and promoting the same artifact does not mean everything in a release is strictly immutable. Database schemas and runtime data evolve through migrations, so they must be managed separately and remain compatible with rollouts.

### 11.1. Expand-and-Contract

For applications requiring rolling deployments, a common strategy is:

1. **Expand:** add new fields, tables, or indexes while keeping old structures operational.
2. Deploy the new application version capable of reading and writing both old and new schemas.
3. Backfill data in controlled batches.
4. Verify all instances and consumers have transitioned to the new fields.
5. **Contract:** remove old fields in a subsequent release once no consumers depend on them.

~~~mermaid
flowchart LR
    A["Schema v1"] --> B["Expand: add new field"]
    B --> C["App v2 reads old + new"]
    C --> D["Backfill and verify"]
    D --> E["All consumers use new field"]
    E --> F["Contract: remove old field"]
~~~

Migrations must never assume rolling back application code automatically rolls back the database. Dropping columns or altering semantics may not be safely reversible. Backups, compatibility tests, migration locks, timeouts, and forward recovery plans are essential.

### 11.2. Migrations as Versioned Release Inputs

Migration scripts and versions should be versioned and published alongside release metadata. However, migrations execute against each environment's live data state, so side effects differ. Record:
- Migration package/version and checksum.
- Before/after schema versions.
- Executing user or workflow.
- Outcome and duration.
- Backfill state and checkpoints.
- Recovery or forward-fix plan.

Never run a production migration using a script that differs from what was reviewed and tested in staging without a change record.

## 12. Feature Flags and Progressive Delivery

An artifact may contain new functionality enabled only for a subset of users or tenants via feature flags. This decouples code deployment from feature release.

Manage the following:
- Flag key, owner, purpose, and expiration/removal date.
- Safe default state.
- Approved targeting rules by tenant, region, or cohort.
- Audit logs of who enabled or disabled flags.
- Dependencies and compatibility if a flag alters schemas or APIs.
- Kill switches for high-risk features.
- Testing both flag-on and flag-off states as well as flag combinations.

Flags do not replace access control. Never use feature flags as authorization mechanisms unless toggling is bound to identity and policy.

### 12.1. Progressive Rollouts

Rollouts can proceed by:
- Internal or canary users.
- 1% → 5% → 25% → 50% → 100% traffic increments.
- A tenant group or region with a small blast radius.
- Blue/green or rolling deployments.

Each step requires sufficient observation time, metric guardrails, and automatic stop conditions. If p95 latency, error rate, business success, or data correctness breaches thresholds, the pipeline must halt or roll back per runbook.

## 13. Rollback, Roll-Forward, and Artifact Retention

### 13.1. Rollbacks Must Use Known-Good Artifacts

Registries must retain old digests in alignment with retention policies and recovery windows. Rolling back means redeploying a previously verified artifact along with compatible configuration and migration states.

Never roll back by rebuilding an older source tag. Dependencies may have shifted, and the newly built artifact will no longer match the historical artifact.

### 13.2. When Is Roll-Forward Better?

Rollback may be unsafe if:
- A database migration has destructively dropped or incompatibly transformed data.
- New API or event schemas are already consumed by downstream services.
- External side effects have already occurred.
- A security vulnerability forbids running the previous artifact.
- Rolling back would lose data written by the new version.

In these cases, you may need to roll forward with a patched release, disable a feature flag, restore data, or run compensating actions. Base the decision on data state and business semantics—not simply on whether the deploy tool offers a rollback button.

### 13.3. Artifact Retention

Artifact retention policies must balance:
- Audit and investigation windows.
- Rollback and DR needs.
- Registry storage capacity and cost.
- Newly disclosed vulnerabilities post-release.
- License, provenance, and SBOM retention obligations.

Artifacts with critical vulnerabilities may need to be quarantined or revoked from promotion even while retained for forensic investigation. Distinguish between keeping evidence and permitting redeployment.

## 14. Supply-Chain and Deployment Environment Security

Artifacts traverse multiple trust boundaries: source repositories, build runners, package registries, image registries, artifact stores, deployment controllers, and runtimes.

Required controls include:
- MFA, branch protection, and code review on repositories.
- Isolated build runners with short-lived, narrowly scoped credentials.
- Dependency pinning, scanning, and policy enforcement.
- SBOMs, provenance, and signing.
- Private, immutable, audited registries.
- Promotion strictly by verified digest.
- Dedicated deploy identities per environment.
- Admission/runtime verification where supported by the platform.
- Secrets managed outside artifacts.
- Auditing of configuration and release changes.
- Incident procedures to revoke signing identities, quarantine artifacts, and redeploy known-good versions.

### 14.1. Protecting Artifacts During Replication and Promotion

When artifacts are replicated across regions or registries:
- Verify digests after replication.
- Validate permissions, retention, and encryption on the target registry.
- Log source, destination, and copy timestamps.
- Never generate new tags by rebuilding.
- If the destination registry mutates contents via conversion or repackaging, treat and test the resulting output as a distinct artifact.

## 15. Observing Releases and Verifying Running Artifacts

A successful release is more than a deployment controller reporting rollout completion.

Verify that:
- Pods, tasks, or VMs are actually running the exact target digest.
- Desired replicas equal available replicas.
- Configuration revisions match the environment and release record.
- Secret references are readable without exposing secret values.
- Readiness, startup, and smoke tests pass.
- SLIs and SLOs show no degradation.
- Error rates, latency, saturation, and dependency health are stable.
- Queues, schemas, and data consistency show no errors.
- Audit logs bind the release ID, actor, and approval.

A release dashboard can display:
- Source commit and build ID.
- Artifact digest and signature status.
- Environment and configuration revision.
- Deployment timestamp and rollout status.
- Test and scan evidence.
- Feature flag states.
- Change and approval references.
- Post-deploy error budget or SLO signals.
- Rollback targets and deployment history.

Never log secret values or personal data to prove configuration accuracy; record only versions/references and verification statuses.

## 16. Practical Scenario: Promoting the Booking API from Development to Production

### 16.1. Context

A booking platform runs:
- A containerized Booking API and Notification worker.
- A Git repository and CI pipeline.
- A private container registry.
- Cloud-hosted development, staging, and production environments.
- Independent database migrations and per-environment secret managers.
- Release requirements covering functional, contract, performance, and security testing.

### 16.2. Recommended Workflow

| Step | Action | Artifact / Config / Evidence |
| --- | --- | --- |
| 1. Commit | Merge reviewed commit | Source revision |
| 2. Build | CI builds API and worker once | Image digests |
| 3. Verify | Unit tests, scans, SBOM, provenance, signing | Test reports, attestations |
| 4. Dev | Deploy digest to dev with dev config | Deployment record |
| 5. Staging | Promote same digest with staging config | Integration/acceptance tests |
| 6. Approve | Review changes, migrations, capacity, and risk | Approval record |
| 7. Canary | Deploy same digest to a small cohort | SLIs/SLOs, error rates, traces |
| 8. Expand | Increase traffic behind gates | Rollout history |
| 9. Verify | Check runtime digest, config, and health | Release evidence |
| 10. Close | Link release to change and rollback target | Audit trail |

### 16.3. Artifact Identity Illustration

| Attribute | Development | Staging | Production |
| --- | --- | --- | --- |
| Image digest | `sha256:abc...` | `sha256:abc...` | `sha256:abc...` |
| Source revision | `commit-417` | `commit-417` | `commit-417` |
| Build ID | `build-417` | `build-417` | `build-417` |
| Config revision | `dev-12` | `stg-29` | `prod-83` |
| Secret set | Dev vault references | Staging vault references | Production vault references |
| Release approval | Team policy | Test gate | Production change approval |

Digests and revisions remain identical; configuration and secret references differ per environment. Values shown are illustrative examples.

### 16.4. Investigating When Production Differs from Staging

If staging passes while production fails, first compare:
- Actual runtime artifact digests.
- Configuration revisions and feature flags.
- Secret versions/references and runtime permissions.
- Network routes, DNS, certificates, and firewalls.
- Database schema/versions, data volumes, and query plans.
- Quotas, replica counts, resource limits, and autoscaling behavior.
- External provider modes and rate limits.

Do not conclude the artifact itself is defective before checking environmental differences. However, if the digests do not match, the release violated the promotion principle and the pipeline must be investigated.

## 17. Second Scenario: Emergency Hotfix

A vulnerability in an HTTP library affects the Booking API running in production. The engineering team has a patch and must release rapidly.

Procedure:
1. Identify the exact source revision and updated dependency.
2. Produce a new build; never patch stored images in place or reuse the old digest.
3. Run risk-appropriate security and regression tests, scan dependencies, and generate fresh SBOM and provenance records.
4. Sign the new artifact and link the security finding and incident/change reference.
5. Deploy to staging or an equivalent verification environment.
6. Obtain emergency release approval from the proper authority.
7. Perform a blast-radius-bounded canary rollout while monitoring SLIs.
8. Verify production is actively running the new digest.
9. Quarantine or revoke the affected artifact according to policy.
10. Post-incident, complete any deferred tests, reviews, and evidence; never skip auditing.

Emergencies compress timelines and follow expedited approval paths per policy; they must never sacrifice artifact identity, traceability, or approver accountability.

## 18. Common Mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Building separately per environment | Binaries differ despite identical source | Build once, promote the same digest |
| Deploying with mutable tags | Tags can silently point to new contents | Deploy by digest or immutable version |
| Using `latest` in production | Unclear which artifact is actually running | Pin digests and log release metadata |
| Baking production endpoints/secrets into builds | Artifact tied to environment and risks secret leakage | Use runtime config and a secret manager |
| Testing source but deploying a different image | Test evidence does not prove the running artifact | Bind test reports to digests |
| Rebuilding when promoting staging to production | Breaks consistency and provenance | Promote the existing registry artifact |
| Failing to pin dependencies/base images | Non-reproducible builds | Use lockfiles, digests, and toolchain pinning |
| Scanning source without scanning artifacts | Misses packaged/runtime layers | Scan actual built images and packages |
| Unbound SBOMs | Unclear which artifact an SBOM describes | Bind SBOMs/attestations to digests |
| Modifying images after signing | Signatures and evidence become invalid | Rebuild, resign, and retest new artifacts |
| Blindly copying staging config to production | Wrong endpoints, permissions, or feature flags | Config schemas, versioning, and diff reviews |
| Rolling-incompatible migrations | Old/new app versions fail while coexisting | Expand-and-contract and compatibility tests |
| Rolling back code when schema cannot revert | Data loss or service outages | Forward-compatible schemas and recovery plans |
| Not retaining old artifacts | Cannot roll back to the exact prior binary | Registry retention and DR copies |
| Not verifying runtime digests | Controller reports success while wrong image runs | Runtime inventory and digest verification |
| Generic approvals | Unclear who approved which artifact or scope | Bind approvals to digest, environment, and change |
| Hotfixes bypassing provenance | Difficult investigations and broken supply-chain trust | Emergency pipeline with minimum gates and audit |

## 19. Hands-On Exercise

A team developing the Booking API manages three environments: development, staging, and production. Currently, CI rebuilds the image in each environment; the `stable` tag is used everywhere; staging occasionally passes while production behaves differently. Secrets are passed into a frontend build step. Releases require security checks and database migrations.

Complete the following tasks:

1. Diagram the current pipeline and highlight every point where artifacts or configurations can diverge.
2. Propose a build-once, promote-same-artifact architecture, digest strategy, and immutable registry policy.
3. Construct a build recipe with dependency locking, base image pinning, provenance, SBOM generation, and signing.
4. Design digest-bound test gates; specify which tests run during build, dev, staging, and production canary.
5. Separate configuration and secrets from the artifact; build a table of valid differences across all three environments.
6. Design a promotion record and approval policy; explain how security exceptions are handled.
7. Define an expand-and-contract database migration strategy and backward-compatibility testing plan.
8. Propose feature flags/progressive rollout steps, metric guardrails, and halt conditions.
9. Write a rollback/roll-forward plan for when a migration has executed but the new version fails.
10. Design runtime verification for deployed digests, config revisions, and provenance post-deployment.
11. Write an ADR covering trade-offs, owners, risks, and review triggers.

**Self-Assessment Criteria:** the solution proves staging and production run the exact tested artifact; configuration and secret differences are intentional; artifacts have verifiable provenance; releases enforce gates, approvals, controlled rollouts, and recovery; and artifacts are never rebuilt or modified after signing.

## 20. Pre-Production Promotion Checklist

- [ ] Source revision is reviewed and branch protections are satisfied.
- [ ] Build recipes, toolchains, and dependencies are locked and recorded.
- [ ] Artifacts are built once per release and stored in a trusted registry.
- [ ] Artifacts carry immutable versions/digests; deployments never rely on mutable tags.
- [ ] Provenance, SBOMs, and signatures match the digest and have been verified.
- [ ] Test, scan, and acceptance evidence is bound to the exact artifact.
- [ ] No secrets or production-specific configs exist inside the artifact.
- [ ] Environment configs have schemas, versions, owners, and validation.
- [ ] Secret references resolve from a secret manager via appropriate workload identity.
- [ ] Manifests and IaC are reviewed; differences between staging and production are justified.
- [ ] Migrations are versioned with compatibility, backups, and forward/rollback plans.
- [ ] Feature flags have owners, safe defaults, audit trails, and expiration dates.
- [ ] Release gates, change approvals, and separation of duties are enforced.
- [ ] Rollouts use canary/progressive strategies, stop conditions, and SLO guardrails.
- [ ] Registry retention covers rollback and audit windows; prior artifacts remain retrievable.
- [ ] Production runtime digests are verified post-deployment.
- [ ] Config revisions, release IDs, actors, approvers, and evidence are recorded.
- [ ] A plan exists to quarantine or revoke artifacts if supply-chain issues arise.
- [ ] TCO includes builds, registries, scanning, evidence storage, replication, and operations.
- [ ] Owners and runbooks exist for releases, rollbacks, hotfixes, and incidents.

## Key Takeaways

**Build once, promote the same artifact** ensures every environment validates and executes the exact same software payload with an immutable identity. Artifacts must be bound to their source revision, build process, digest, provenance, SBOM, signature, and test evidence. Configuration and secrets are managed independently per environment with versioning, access control, and auditing.

A reliable release process follows the chain: **reviewed source → controlled build → immutable artifact → verify/test → promote → approve → roll out → verify runtime → observe and recover**. When source changes, build a new artifact and retest it; never modify or rebuild an approved artifact and treat it as the same release.
